"""Bounded, read-only evidence capture for the retained overlapping-spoke lab."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import base64
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import zlib

from execute import AZ_PYTHON, Job, RG, utc
from nat_deploy import fingerprint, read

HERE = Path(__file__).resolve().parent
CONTROL = HERE / ".runtime-control"
TARGETS = read(HERE / "nat-spec.json")["targets"]


def sanitize(text):
    text = re.sub(r"(?i)(/subscriptions/)[0-9a-f-]{36}", r"\1<SUBSCRIPTION_ID>", text)
    text = re.sub(r'(?i)("(?:subscriptionId|tenantId)"\s*:\s*")[^"]+', r"\1<REDACTED_ID>", text)
    text = re.sub(r"(?i)[A-Z]:[\\/]+Users[\\/]+[^\\/\s\"]+", "<LOCAL_USER>", text)
    text = re.sub(r"/home/[^/\s\"]+", "/home/<USER>", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "<EMAIL>", text)
    text = re.sub(r"(?:ssh-rsa|ssh-ed25519|ecdsa-sha2-\S+)\s+[A-Za-z0-9+/=]+[^\r\n]*",
                  "<SSH_PUBLIC_KEY>", text)
    text = re.sub(r'(?i)("(?:customData|adminPassword|accessToken|refreshToken|password)"\s*:\s*)'
                  r'("(?:\\.|[^"])*"|null)', r'\1"<OMITTED>"', text)
    text = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "<TOKEN>", text)
    return text


def identity_matches(target, vm, nic, guest):
    return bool(
        guest["imds"]["name"] == target["name"] and guest["imds"]["vmId"] == vm["vmId"]
        and vm["networkProfile"]["networkInterfaces"][0]["id"] == nic["id"]
        and nic["name"] == target["nic"]
        and any(c["privateIPAddress"] == target["ip"] for c in nic["ipConfigurations"])
        and re.search(r"\b" + re.escape(target["ip"]) + r"/\d+",
                      guest["commands"]["addresses"]["stdout"])
    )


def guest_script(target, stage):
    commands = {
        "hostname": "hostname",
        "addresses": "ip -br -4 addr",
        "routes": "ip -4 route show table all",
        "rules": "ip -4 rule show",
        "cloudInit": "cloud-init status --long",
        "kernel": "uname -a",
        "failedServices": "systemctl --failed --no-pager --no-legend",
        "routeHub": "ip -4 route get 10.0.1.4",
        "routeBackend": "ip -4 route get 192.168.1.4",
    }
    if target["role"] == "nva":
        commands.update(
            iptables="iptables-save -c",
            forwarding="sysctl net.ipv4.ip_forward net.ipv4.conf.all.rp_filter "
                       "net.ipv4.conf.default.rp_filter net.ipv4.conf.eth0.rp_filter",
            natUnit="systemctl cat lab-static-nat --no-pager",
            natScript="cat /usr/local/sbin/lab-static-nat",
            natEnabled="systemctl is-enabled lab-static-nat",
            natActive="systemctl show lab-static-nat --property=ActiveState,SubState,Result",
            versions="iptables --version; ip -Version; python3 --version",
            conntrack="if command -v conntrack >/dev/null; then "
                      "conntrack -L -p tcp --orig-src 10.0.1.4 --orig-dst " + target["alias"] +
                      " --dport 8080; elif test -r /proc/net/nf_conntrack; then "
                      "grep -E 'src=10.0.1.4 dst=" + target["alias"].replace(".", r"\.") +
                      " .*dport=8080' /proc/net/nf_conntrack; else "
                      "echo 'NOT_CAPTURED: conntrack tool/proc interface unavailable'; fi",
            tcpdumpAvailability="if command -v tcpdump >/dev/null; then "
                                "echo 'AVAILABLE; capture omitted: counters/logs suffice'; "
                                "else echo 'NOT_CAPTURED: tcpdump unavailable'; fi",
        )
    elif target["role"] == "backend":
        commands.update(
            backendUnit="systemctl cat lab-backend-http --no-pager",
            backendEnabled="systemctl is-enabled lab-backend-http",
            backendActive="systemctl show lab-backend-http --property=ActiveState,SubState,Result",
            marker="cat /opt/lab-http/index.html",
            markerHash="sha256sum /opt/lab-http/index.html",
            listener="ss -lnt '( sport = :8080 )'",
            backendLogs="journalctl -u lab-backend-http --no-pager -o short-iso -n 20",
        )
    else:
        commands.update(routeAlias1="ip -4 route get 10.10.1.10",
                        routeAlias2="ip -4 route get 10.20.0.10")
    payload = dict(target=target, stage=stage, commands=commands)
    return """python3 - <<'PY'
import base64,datetime,hashlib,http.client,json,subprocess,urllib.request,zlib
p=json.loads(PAYLOAD)
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
o=dict(startedAtUtc=now(),target=p['target']['name'],stage=p['stage'],commands={})
for key,cmd in p['commands'].items():
 try:
  r=subprocess.run(cmd,shell=True,capture_output=True,text=True,timeout=15)
  o['commands'][key]=dict(command=cmd,atUtc=now(),exitCode=r.returncode,stdout=r.stdout,stderr=r.stderr)
 except Exception as e: o['commands'][key]=dict(command=cmd,error=str(e))
o['imds']={}
for key in ['name','vmId','location','vmSize']:
 try:
  req=urllib.request.Request('http://169.254.169.254/metadata/instance/compute/'+key+'?api-version=2021-02-01&format=text',headers={'Metadata':'true'})
  with urllib.request.urlopen(req,timeout=3) as r: o['imds'][key]=r.read().decode()
 except Exception as e: o['imds'][key]=dict(error=str(e))
def request(host,timeout):
 d=dict(startedAtUtc=now(),host=host,port=8080,timeoutSeconds=timeout)
 c=http.client.HTTPConnection(host,8080,timeout=timeout)
 try:
  c.connect()
  d.update(localEndpoint=c.sock.getsockname(),remoteEndpoint=c.sock.getpeername())
  c.request('GET','/',headers={'Connection':'close'})
  r=c.getresponse()
  d.update(status=r.status,body=r.read(1024).decode())
 except Exception as e: d['error']=repr(e)
 finally: c.close()
 d['completedAtUtc']=now()
 return d
if p['target']['role']=='backend': o['localhostHttp']=request('127.0.0.1',3)
if p['target']['role']=='hub':
 o['http']=[request(alias,5) for alias in ['10.10.1.10','10.20.0.10'] for _ in range(3)]
 o['directNegativeControl']=request('192.168.1.4',3)
o['completedAtUtc']=now()
print('EVIDENCE_Z '+base64.b64encode(zlib.compress(json.dumps(o).encode())).decode())
PY
""".replace("PAYLOAD", repr(json.dumps(payload)))


class Capture:
    def __init__(self, resume=None):
        self.start = utc()
        self.task = resume or "nat-evidence-" + self.start.strftime("%Y%m%dT%H%M%SZ")
        self.out = HERE.parent / "show-output" / self.task
        if not resume:
            self.out.mkdir()
        self.lease_path = CONTROL / (self.task + "-lease.json")
        self.lock = threading.RLock()
        self.active = set()
        self.pids = []
        self.calls = 15
        self.results = {}
        self.lease = dict(taskId=self.task, ownerRole="Niobe",
            objective="Fresh comprehensive read-only NAT identity and route evidence",
            createdAtUtc=self.start.isoformat(),
            expiresAtUtc=(self.start + timedelta(minutes=25)).isoformat(),
            maxToolCalls=75, maxMutations=0, maxConfigurationMutations=0,
            commandTimeoutSeconds=180, runCommandTimeoutSeconds=300,
            maxFiles=80, restoreTimeoutMinutes=0, state="active",
            retentionPolicy="NEVER DELETE", configurationMutations=0,
            allowedArmActions=["showEffectiveRouteTable", "listEffectiveNetworkSecurityGroups",
                               "RunCommand read-only guest inspection and HTTP probes"],
            rollback="No writes: retain all resources on any failure",
            forbiddenWork=["deployments", "configuration writes", "packages", "delete", "restart",
                           "deallocate", "old evidence-tree import", "nested agents"],
            runningChildren=[], queuedWork=[])
        if resume:
            prior = read(self.lease_path)
            assert prior["state"] == "blocked" and not prior["runningChildren"]
            self.start = __import__("datetime").datetime.fromisoformat(prior["createdAtUtc"])
            self.lease = prior
            self.lease.update(state="active", localCollectorTransportRecovery=True)
            self.calls = prior["toolCallsUsed"] + 4
            self.save("collector-transport-interruption.json", dict(
                verification=read(self.out / "verification.json"),
                failedCommands={p.name: read(p) for p in self.out.glob("routes-before-*.txt")
                                if not (self.out / (p.stem + ".json")).exists()}))
            index = read(self.out / "file-index.json")
            for entry in index.get("files", []) if isinstance(index, dict) else index:
                name = entry["name"]
                if name.endswith(".json") and name.startswith(("before-vnet-", "before-vms", "nics",
                                                               "routes-before-")):
                    self.results[name[:-5]] = read(self.out / name)
        self.persist()

    def save(self, name, obj):
        text = json.dumps(obj, indent=2, ensure_ascii=False) if not isinstance(obj, str) else obj
        (self.out / name).write_text(sanitize(text) + "\n", encoding="utf-8")

    def persist(self):
        with self.lock:
            self.lease.update(toolCallsUsed=self.calls, runningChildren=sorted(self.active),
                              queuedWork=[], lastCheckpointUtc=utc().isoformat())
            self.lease_path.write_text(json.dumps(self.lease, indent=2) + "\n", encoding="utf-8")

    def gate(self):
        state = read(self.lease_path)
        assert state["state"] == "active" and not (CONTROL / "STOP").exists(), "STOP/lease"
        assert utc() < self.start + timedelta(minutes=20) and self.calls < 60, "80% reserve"
        for name in ("lease.json", "nat-validation-20261016T083150Z-lease.json"):
            old = read(CONTROL / name)
            assert old["state"] == "completed" and not old["runningChildren"] and not old["queuedWork"]
        assert len(list(self.out.iterdir())) < 77, "File reserve"

    def command(self, label, args, timeout=180):
        self.gate()
        if label in self.results:
            return self.results[label]
        allowed = (["network", "nic", "list"], ["network", "nic", "show-effective-route-table"],
                   ["network", "nic", "list-effective-nsg"], ["vm", "list"],
                   ["vm", "run-command", "invoke"], ["resource", "list"])
        assert any(args[:len(p)] == list(p) for p in allowed) or (
            args[:3] == ["rest", "--method", "get"] and RG in args[args.index("--url") + 1])
        with self.lock:
            self.calls += 1
        started, job, process = utc(), Job(), None
        stdout, stderr = b"", b""
        try:
            process = subprocess.Popen([str(AZ_PYTHON), "-IBm", "azure.cli", *args,
                "--only-show-errors", "-o", "json"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            job.assign(process)
            with self.lock:
                self.active.add(process.pid)
                self.pids.append(process.pid)
                self.persist()
            deadline = time.monotonic() + timeout
            while True:
                self.gate()
                assert time.monotonic() < deadline, "Command deadline " + label
                try:
                    stdout, stderr = process.communicate(timeout=1)
                    break
                except subprocess.TimeoutExpired:
                    pass
            value = json.loads(stdout) if stdout.strip() else None
            if args[:3] == ["vm", "run-command", "invoke"] and process.returncode == 0:
                messages = "\n".join(v.get("message", "") for v in value.get("value", []))
                encoded = next(x[11:] for x in messages.splitlines() if x.startswith("EVIDENCE_Z "))
                decoded = json.loads(zlib.decompress(base64.b64decode(encoded)))
                # Decode before sanitizing; never publish hidden encoded identifiers.
                value = dict(armStatus=[{k: v.get(k) for k in ("code", "displayStatus", "level")}
                                        for v in value["value"]], guest=decoded)
                stdout = json.dumps(value).encode()
            self.save(label + ".json", value)
            self.results[label] = value
            print(label + " exit=" + str(process.returncode) + " " + utc().isoformat(), flush=True)
            return json.loads(sanitize(json.dumps(value))) if value is not None else None
        finally:
            job.close()
            if process:
                if process.poll() is None:
                    process.kill()
                extra_out, extra_err = process.communicate(timeout=10)
                if not stdout:
                    stdout = extra_out
                if not stderr:
                    stderr = extra_err
                with self.lock:
                    self.active.discard(process.pid)
                    self.persist()
            self.save(label + ".txt", json.dumps(dict(
                command=["az", *args], startedAtUtc=started.isoformat(),
                completedAtUtc=utc().isoformat(), exitCode=process.returncode if process else None,
                stdout=stdout.decode("utf-8", "replace"), stderr=stderr.decode("utf-8", "replace")),
                indent=2))
            self.gate()

    def guest(self, target, stage):
        return self.command(stage + "-" + target["name"], ["vm", "run-command", "invoke", "-g", RG,
            "-n", target["name"], "--command-id", "RunShellScript",
            "--scripts", guest_script(target, stage)], 300)

    def parallel(self, jobs):
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(lambda job: job(), jobs))

    def networks(self, stage):
        return self.parallel([lambda name=name: self.command(stage + "-vnet-" + name,
            ["rest", "--method", "get", "--url", "/subscriptions/{subscriptionId}/resourceGroups/" +
             RG + "/providers/Microsoft.Network/virtualNetworks/" + name + "?api-version=2026-01-01"])
             for name in ("hub", "spoke1", "spoke2")])

    def vms(self, stage):
        return self.command(stage + "-vms", ["vm", "list", "-g", RG, "-d", "--query",
            "[].{name:name,id:id,vmId:vmId,location:location,powerState:powerState,"
            "provisioningState:provisioningState,hardwareProfile:hardwareProfile,"
            "storageProfile:storageProfile,networkProfile:networkProfile}"])

    def run(self):
        verdict = dict(verdict="INCONCLUSIVE", claims={}, limitations=[
            "TCP 8080 HTTP path only; negative direct HTTP control is not all-protocol isolation.",
            "isolated192 is a label, not an isolation assertion; backend NIC hub routes are observed.",
            "No packet capture performed; conntrack only when already available.",
            "Read-only RunCommand ARM actions produce platform execution bookkeeping and HTTP logs.",
            "Snapshots are sequential within bounded batches, not atomic.",
            "RunCommand compressed transport decoded before sanitization; raw guest command outputs preserved.",
        ])
        try:
            if not (self.out / "lease-start.json").exists():
                self.save("lease-start.json", self.lease)
            before_networks = self.networks("before")
            nics, vms = self.parallel([
                lambda: self.command("nics", ["network", "nic", "list", "-g", RG]),
                lambda: self.vms("before")])
            self.parallel([lambda t=t: self.command("routes-before-" + t["name"],
                ["network", "nic", "show-effective-route-table", "-g", RG, "-n", t["nic"]])
                for t in TARGETS])
            self.parallel([lambda t=t: self.command("effective-nsg-" + t["name"],
                ["network", "nic", "list-effective-nsg", "-g", RG, "-n", t["nic"]])
                for t in TARGETS])
            others = [t for t in TARGETS if t["role"] != "hub"]
            self.parallel([lambda t=t: self.guest(t, "before") for t in others])
            self.guest(TARGETS[0], "hub")
            self.parallel([lambda t=t: self.guest(t, "after") for t in others])
            after_networks = self.networks("after")
            after_vms = self.vms("after")
            self.parallel([lambda t=t: self.command("routes-after-" + t["name"],
                ["network", "nic", "show-effective-route-table", "-g", RG, "-n", t["nic"]])
                for t in TARGETS])
            self.command("inventory-final", ["resource", "list", "-g", RG])
            self.verify(verdict, before_networks, after_networks, nics, vms, after_vms)
        except Exception as exc:
            verdict["error"] = repr(exc)
        finally:
            verdict.update(completedAtUtc=utc().isoformat(), resourcesRetained=True,
                           configurationMutations=0, deleteOperations=0, toolCallsUsed=self.calls)
            self.lease.update(state="completed" if verdict["verdict"] == "PASS" else "blocked",
                              verdict=verdict["verdict"], resourcesRetained=True)
            self.persist()
            self.save("verification.json", verdict)
            self.save("process-idle.json", dict(atUtc=utc().isoformat(), runningChildren=sorted(self.active),
                allChildPids=self.pids, childrenIdle=not self.active, queuedWork=[],
                leaseState=self.lease["state"], containment="Windows kill-on-close jobs; synchronous executor joined",
                priorOwnersIdle=True, configurationMutations=0, deleteOperations=0))
            self.save("lease-final.json", self.lease)
            files = sorted(p for p in self.out.iterdir()
                           if p.name not in ("file-index.json", "sha256-manifest.json"))
            self.save("file-index.json", dict(excludes=["file-index.json", "sha256-manifest.json"],
                files=[dict(name=p.name, bytes=p.stat().st_size) for p in files]))
            files = sorted(p for p in self.out.iterdir() if p.name != "sha256-manifest.json")
            self.save("sha256-manifest.json", {
                "algorithm": "sha256", "excludesSelf": True,
                "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}})
            print(json.dumps(dict(verdict=verdict["verdict"], path=str(self.out),
                files=len(list(self.out.iterdir())), bytes=sum(p.stat().st_size for p in self.out.iterdir()),
                childrenIdle=not self.active, queuedWork=[], error=verdict.get("error"))), flush=True)

    def verify(self, verdict, before_networks, after_networks, nics, vms, after_vms):
        def claim(name, passed, files, details=None):
            verdict["claims"][name] = dict(status="PASS" if passed else "FAIL", files=files, details=details)

        def normalize(vnets):
            return [dict(name=v["name"], location=v["location"], **v["properties"]) for v in vnets]

        claim("vnetsAndPeeringsUnchanged", fingerprint(normalize(before_networks)) ==
              fingerprint(normalize(after_networks)),
              ["before-vnet-" + n + ".json" for n in ("hub", "spoke1", "spoke2")] +
              ["after-vnet-" + n + ".json" for n in ("hub", "spoke1", "spoke2")])
        peers = [p["properties"] for v in after_networks for p in v["properties"]["virtualNetworkPeerings"]]
        claim("fourDirectedPeeringsConnected", len(peers) == 4 and all(
            p["peeringState"] == "Connected" and p["provisioningState"] == "Succeeded" and
            p["peerCompleteVnets"] is False for p in peers),
            ["after-vnet-" + n + ".json" for n in ("hub", "spoke1", "spoke2")])
        claim("allFiveVMsStillRunning", len(after_vms) == 5 and all(
            v["powerState"] == "VM running" for v in after_vms), ["before-vms.json", "after-vms.json"])
        subnets = [s["properties"] for v in after_networks for s in v["properties"]["subnets"]]
        claim("noUDROrSubnetNSG", len(subnets) == 5 and all(
            not s.get("routeTable") and not s.get("networkSecurityGroup") for s in subnets),
            ["after-vnet-" + n + ".json" for n in ("hub", "spoke1", "spoke2")])
        claim("NICAddressesAliasesForwardingAndNoNSG", len(nics) == 5 and all(
            any(n["name"] == t["nic"] and not n.get("networkSecurityGroup") and
                n["enableIPForwarding"] == (t["role"] == "nva") and
                sorted(c["privateIPAddress"] for c in n["ipConfigurations"]) ==
                sorted([t["ip"]] + ([t["alias"]] if t.get("alias") else [])) for n in nics)
            for t in TARGETS), ["nics.json"])
        bindings = []
        for t in TARGETS:
            label = ("hub" if t["role"] == "hub" else "before") + "-" + t["name"]
            g = self.results[label]["guest"]
            vm = next(v for v in vms if v["name"] == t["name"])
            nic = next(n for n in nics if n["name"] == t["nic"])
            bound = identity_matches(t, vm, nic, g)
            if t["role"] == "backend":
                bound = bound and g["localhostHttp"].get("body") == t["identity"] + "\n"
                bound = bound and g["commands"]["marker"]["stdout"] == t["identity"] + "\n"
                bindings.append(dict(vm=t["name"], vmId=vm["vmId"], imds=g["imds"],
                    guestHostname=g["commands"]["hostname"]["stdout"].strip(),
                    AzurePrivateIP=nic["ipConfigurations"][0]["privateIPAddress"],
                    guestAddresses=g["commands"]["addresses"]["stdout"],
                    localhostHttp=g["localhostHttp"], markerSha256=hashlib.sha256(
                        (t["identity"] + "\n").encode()).hexdigest()))
            claim("identityBinding-" + t["name"], bool(bound), [label + ".json", "nics.json", "before-vms.json"])
        claim("bothBackendsExactSameIPIndependentUniqueVMs",
              len(bindings) == 2 and bindings[0]["vmId"] != bindings[1]["vmId"] and
              all(b["AzurePrivateIP"] == "192.168.1.4" for b in bindings),
              ["before-vm-spoke1-isolated192.json", "before-vm-spoke2-isolated192.json",
               "nics.json", "before-vms.json"], bindings)
        hub = self.results["hub-vm-hub-hub10"]["guest"]
        expected = {"10.10.1.10": "spoke1-backend-192.168.1.4\n",
                    "10.20.0.10": "spoke2-backend-192.168.1.4\n"}
        claim("hubThreeExactHTTP200EachAlias", len(hub["http"]) == 6 and all(
            p.get("status") == 200 and p.get("body") == expected[p["host"]] and
            p["localEndpoint"][0] == "10.0.1.4" and p["remoteEndpoint"] == [p["host"], 8080]
            for p in hub["http"]), ["hub-vm-hub-hub10.json"], hub["http"])
        verdict["directNegativeControl"] = hub["directNegativeControl"]
        def counters(text):
            return {m.group(2): int(m.group(1)) for m in
                    re.finditer(r"^\[(\d+):\d+\] (-A (?:PREROUTING|POSTROUTING|FORWARD) .+)$",
                                text, re.MULTILINE)}
        for t in TARGETS:
            if t["role"] != "nva":
                continue
            name = t["name"]
            before = self.results["before-" + name]["guest"]["commands"]["iptables"]["stdout"]
            after = self.results["after-" + name]["guest"]["commands"]["iptables"]["stdout"]
            a, b = counters(before), counters(after)
            delta = {k: v-a.get(k, 0) for k, v in b.items()}
            claim("NATCounterDeltas-" + name,
                  any("--to-destination 192.168.1.4" in k and v == 3 for k, v in delta.items()) and
                  any("--to-source " + t["ip"] in k and v == 3 for k, v in delta.items()) and
                  any("--ctstate" in k and v > 0 for k, v in delta.items()),
                  ["before-" + name + ".json", "after-" + name + ".json"], delta)
            backend = "vm-" + t["vnet"] + "-isolated192"
            logs = self.results["after-" + backend]["guest"]["commands"]["backendLogs"]["stdout"]
            claim("backendLogsSNATSource-" + name, sum(t["ip"] + " - -" in line
                  for line in logs.splitlines()) >= 3, ["after-" + backend + ".json"])
        route_summary = {}
        for t in TARGETS:
            name = t["name"]
            before = self.results["routes-before-" + name]
            after = self.results["routes-after-" + name]
            claim("effectiveRoutesUnchanged-" + name, before == after,
                  ["routes-before-" + name + ".json", "routes-after-" + name + ".json"])
            rows = after.get("value", []) if isinstance(after, dict) else after
            route_summary[name] = {}
            for destination in ("10.0.1.4", "10.10.1.10", "10.20.0.10", "192.168.1.4"):
                matches = [(ipaddress.ip_network(prefix).prefixlen, row) for row in rows
                           if row["state"] == "Active" for prefix in row["addressPrefix"]
                           if ipaddress.ip_address(destination) in ipaddress.ip_network(prefix)]
                route_summary[name][destination] = max(matches, key=lambda p: p[0])[1] if matches else None
        verdict["effectiveRouteBestMatches"] = route_summary
        verdict["effectiveNSGObservations"] = {t["name"]: self.results.get("effective-nsg-" + t["name"])
                                               for t in TARGETS}
        verdict["effectiveNSGLimitation"] = "Empty result is recorded, not a security-policy PASS."
        verdict["verdict"] = "PASS" if all(
            c["status"] == "PASS" for c in verdict["claims"].values()) else "FAIL"
        print("LIVE " + self.task + " | verdict " + verdict["verdict"] +
              " | mutations 0/0 | retained running | " + str(self.out), flush=True)


if __name__ == "__main__":
    Capture(sys.argv[1] if len(sys.argv) > 1 else None).run()
