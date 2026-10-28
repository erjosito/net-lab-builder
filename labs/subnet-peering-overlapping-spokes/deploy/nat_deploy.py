"""Deploy only the approved retained five-VM template; never repair or delete."""

import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

from execute import AZ_PYTHON, Job

HERE = Path(__file__).resolve().parent
CONTROL = HERE / ".runtime-control"
LEASE = CONTROL / "lease.json"
GUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")


def utc():
    return datetime.now(timezone.utc)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def template_gate(plan, template):
    resources = template["resources"]
    expected = {(kind, t[key]) for t in plan["targets"] for kind, key in (
        ("Microsoft.Network/networkInterfaces", "nic"), ("Microsoft.Compute/virtualMachines", "name"))}
    assert len(resources) == 10 and {(r["type"], r["name"]) for r in resources} == expected
    for target in plan["targets"]:
        nic = next(r for r in resources if r["name"] == target["nic"])
        vm = next(r for r in resources if r["name"] == target["name"])
        assert nic["location"] == vm["location"] == plan["region"] == "swedencentral"
        assert nic["properties"]["enableIPForwarding"] == (target["role"] == "nva")
        assert not nic["properties"].get("networkSecurityGroup")
        configs = nic["properties"]["ipConfigurations"]
        assert len(configs) == (2 if target["role"] == "nva" else 1)
        assert [c["properties"]["privateIPAddress"] for c in configs] == (
            [target["ip"], target["alias"]] if target["role"] == "nva" else [target["ip"]])
        for index, config in enumerate(configs):
            props = config["properties"]
            assert props["primary"] == (index == 0)
            assert props["privateIPAllocationMethod"] == "Static"
            assert not props.get("publicIPAddress")
            portable_id = (
                "[resourceId('Microsoft.Network/virtualNetworks/subnets', "
                f"'{target['vnet']}', '{target['subnet']}')]")
            assert props["subnet"]["id"] == portable_id or props["subnet"]["id"].endswith(
                f"/resourceGroups/{plan.get('resourceGroup')}/providers/Microsoft.Network/"
                f"virtualNetworks/{target['vnet']}/subnets/{target['subnet']}")
        props = vm["properties"]
        assert props["hardwareProfile"]["vmSize"] == plan["vmSize"] == "Standard_D2als_v6"
        assert props["storageProfile"]["imageReference"] == plan["image"]
        disk = props["storageProfile"]["osDisk"]
        assert disk["name"] == target["disk"] and disk["diskSizeGB"] == 30
        assert disk["managedDisk"]["storageAccountType"] == "StandardSSD_LRS"
        assert disk["deleteOption"] == "Detach"
        assert len(props["networkProfile"]["networkInterfaces"]) == 1
        assert props["osProfile"]["linuxConfiguration"]["disablePasswordAuthentication"]
        cloud = json.loads(base64.b64decode(props["osProfile"]["customData"]).decode().split("\n", 1)[1])
        assert cloud["package_update"] is False and cloud["package_upgrade"] is False
        assert not cloud.get("packages")
        files = {f["path"]: f for f in cloud["write_files"]}
        if target["role"] == "nva":
            script = files["/usr/local/sbin/lab-static-nat"]["content"]
            assert files["/usr/local/sbin/lab-static-nat"]["permissions"] == "0755"
            for fragment in (
                f"ip address replace {target['alias']}/32", "net.ipv4.ip_forward=1",
                f"PREROUTING -s 10.0.1.4/32 -d {target['alias']}/32 -j DNAT --to-destination 192.168.1.4",
                f"POSTROUTING -s 10.0.1.4/32 -d 192.168.1.4/32 -j SNAT --to-source {target['ip']}",
                "FORWARD -s 10.0.1.4/32 -d 192.168.1.4/32 -j ACCEPT",
                "FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT",
            ):
                assert fragment in script, fragment
            assert "MASQUERADE" not in script
            unit = files["/etc/systemd/system/lab-static-nat.service"]["content"]
            assert "After=network-online.target" in unit and "RemainAfterExit=yes" in unit
            assert "WantedBy=multi-user.target" in unit
            service = "lab-static-nat"
        elif target["role"] == "backend":
            assert files["/opt/lab-http/index.html"]["content"] == target["identity"] + "\n"
            unit = files["/etc/systemd/system/lab-backend-http.service"]["content"]
            for fragment in ("User=nobody", "WorkingDirectory=/opt/lab-http",
                             "/usr/bin/python3 -m http.server 8080", "WantedBy=multi-user.target"):
                assert fragment in unit
            service = "lab-backend-http"
        else:
            assert not files
            service = None
        if service:
            assert ["systemctl", "enable", "--now", service] in cloud["runcmd"]


def whatif_gate(result, plan):
    assert result.get("status") == "Succeeded", "What-if did not succeed"
    expected = {t[k].lower() for t in plan["targets"] for k in ("name", "nic")}
    created = set()
    for change in result["changes"]:
        kind = change["changeType"]
        name = change["resourceId"].rsplit("/", 1)[-1].lower()
        if kind == "Create":
            assert name in expected, "Unapproved resource creation"
            created.add(name)
        else:
            assert kind in ("NoChange", "Ignore"), "Existing-resource mutation in what-if"
    assert created == expected, "What-if did not create all ten exact resources"


def fingerprint(vnets):
    result = {}
    for vnet in vnets:
        result[vnet["name"]] = {
            "location": vnet["location"], "addressSpace": vnet["addressSpace"],
            "subnets": {s["name"]: {k: s.get(k) for k in (
                "addressPrefix", "addressPrefixes", "defaultOutboundAccess",
                "networkSecurityGroup", "routeTable", "delegations",
                "privateEndpointNetworkPolicies", "privateLinkServiceNetworkPolicies")}
                for s in vnet["subnets"]},
            "peerings": {p["name"]: {k: v for k, v in p.items()
                if k not in ("etag", "resourceGuid")} for p in vnet["virtualNetworkPeerings"]},
        }
    return GUID.sub("<redacted-guid>", json.dumps(result, sort_keys=True))


class Deployment:
    def __init__(self):
        self.lease = read(LEASE)
        self.plan = read(Path(self.lease["planPath"]))
        self.out = HERE.parent / "show-output" / self.lease["taskId"]
        self.out.mkdir(exist_ok=False)
        self.calls = 20
        self.batches = 0
        self.actions = []
        self.active = set()
        self.secrets = []
        self.state = "blocked"
        self.reason = "Gates not completed"

    def save(self, name, value):
        text = json.dumps(value, indent=2)
        for secret in self.secrets:
            text = text.replace(secret, "<redacted>")
        (self.out / name).write_text(GUID.sub("<redacted-guid>", text) + "\n", encoding="utf-8")

    def persist(self, **extra):
        lease = read(LEASE)
        lease.update(extra)
        lease.update(toolCallsUsed=self.calls, mutationBatchesUsed=self.batches,
                     armActions=self.actions, runningChildren=sorted(self.active),
                     queuedWork=[], lastCheckpointUtc=utc().isoformat(),
                     deploymentEvidencePath=str(self.out))
        LEASE.write_text(json.dumps(lease, indent=2) + "\n", encoding="utf-8")
        self.lease = lease

    def check(self):
        lease = read(LEASE)
        assert lease["taskId"] == self.lease["taskId"] and lease["state"] == "active"
        assert lease["retentionPolicy"] == "NEVER DELETE" and lease["cleanupApproval"] is False
        assert not (CONTROL / "STOP").exists(), "STOP present"
        assert utc() < datetime.fromisoformat(lease["expiresAtUtc"]), "Lease expired"
        elapsed = (utc() - datetime.fromisoformat(lease["createdAtUtc"])).total_seconds()
        assert elapsed < 36 * 60 and self.calls < 96 and self.batches < 5, "80% reserve reached"

    def command(self, label, args, timeout=600, action=None):
        self.check()
        assert not any(x.lower() in ("delete", "cleanup", "cancel") for x in args), "Forbidden dispatch"
        if action:
            assert action in ("deployment", "bootstrap-read"), "Unapproved mutation"
            if action == "deployment":
                assert "--mode" in args and args[args.index("--mode") + 1] == "Incremental"
                assert not self.actions, "Deployment retry forbidden"
                self.batches += 1
            self.actions.append({"label": label, "action": action, "atUtc": utc().isoformat()})
        self.calls += 1
        start = utc()
        job, process = Job(), None
        stdout, stderr = "", ""
        try:
            process = subprocess.Popen(
                [str(AZ_PYTHON), "-IBm", "azure.cli", *args, "--only-show-errors", "-o", "json"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            job.assign(process)
            self.active.add(process.pid)
            self.persist()
            deadline = min(time.monotonic() + timeout, time.monotonic() +
                           (datetime.fromisoformat(self.lease["expiresAtUtc"]) - utc()).total_seconds())
            while True:
                self.check()
                assert time.monotonic() < deadline, label + " process deadline"
                try:
                    out, err = process.communicate(timeout=min(1, max(.01, deadline - time.monotonic())))
                    stdout, stderr = out.decode("utf-8", "replace"), err.decode("utf-8", "replace")
                    break
                except subprocess.TimeoutExpired:
                    continue
            assert process.returncode == 0, label + ": " + stderr[-2000:]
            return json.loads(stdout) if stdout.strip() else None
        finally:
            job.close()
            if process:
                if process.poll() is None:
                    process.kill()
                out, err = process.communicate(timeout=10)
                stdout, stderr = out.decode("utf-8", "replace"), err.decode("utf-8", "replace")
                self.active.discard(process.pid)
            # Account output includes personal account information; retain only its gate.
            if label != "account":
                self.save(label + ".json", dict(command=["az", *args], startedAtUtc=start.isoformat(),
                    completedAtUtc=utc().isoformat(), exitCode=process.returncode if process else None,
                    stdout=stdout, stderr=stderr, action=action))
            self.persist()
            self.check()

    def run(self):
        try:
            assert self.lease["state"] == "ready" and not self.lease.get("runningChildren")
            self.persist(state="active")
            template_path = Path(self.plan["templatePath"])
            parameters_path = Path(self.plan["parametersPath"])
            template = read(template_path)
            parameters = read(parameters_path)
            key = parameters["parameters"]["sshPublicKey"]["value"]
            assert len(key.split()) == 2, "SSH public key comment must be absent"
            self.secrets.append(key)
            template_gate(self.plan, template)
            account = self.command("account", ["account", "show"])
            config = read(Path.home() / ".copilot" / "skills" / "azure-lab" / "lab-config.json")
            assert account["id"] == config["azure_subscription_id"], "Active account mismatch"
            for r in template["resources"]:
                if r["type"].endswith("networkInterfaces"):
                    assert all("/subscriptions/" + account["id"] + "/" in c["properties"]["subnet"]["id"]
                               for c in r["properties"]["ipConfigurations"])
            rg = self.plan["resourceGroup"]
            group = self.command("group", ["group", "show", "-n", rg])
            assert group["location"] == self.plan["region"]
            inventory = self.command("inventory-before", ["resource", "list", "-g", rg])
            assert len(inventory) == 3 and all(
                x["type"].lower() == "microsoft.network/virtualnetworks" for x in inventory), "Names not absent"
            baseline = self.command("network-before", ["network", "vnet", "list", "-g", rg])
            previous = read(Path(self.plan["evidencePath"]) / "network-baseline.json")
            assert fingerprint(baseline) == fingerprint(previous), "Network baseline drift"
            assert all(p["allowForwardedTraffic"] is False for v in baseline for p in v["virtualNetworkPeerings"])
            self.save("input-gates.json", dict(passed=True, resourceGroup=rg, region=self.plan["region"],
                namesAbsent=True, sameConfiguredAccount=True, bootstrapRecipe="PASS",
                templateSha256=hashlib.sha256(template_path.read_bytes()).hexdigest(),
                targets=self.plan["targets"], retention="NEVER DELETE"))
            common = ["-g", rg, "-n", self.lease["taskId"], "--template-file", str(template_path),
                      "--parameters", "@" + str(parameters_path), "--mode", "Incremental"]
            whatif = self.command("what-if", ["deployment", "group", "what-if", *common,
                                           "--no-pretty-print"], timeout=600)
            whatif_gate(whatif, self.plan)
            self.save("what-if-gate.json", {"passed": True, "changes": [
                {"name": c["resourceId"].rsplit("/", 1)[-1], "changeType": c["changeType"]}
                for c in whatif["changes"]]})
            # Archive the validated template with portable resource IDs, never credentials.
            archive = json.loads(json.dumps(template))
            for resource in archive["resources"]:
                if resource["type"].endswith("networkInterfaces"):
                    target = next(t for t in self.plan["targets"] if t["nic"] == resource["name"])
                    for c in resource["properties"]["ipConfigurations"]:
                        c["properties"]["subnet"]["id"] = (
                            "[resourceId('Microsoft.Network/virtualNetworks/subnets', "
                            f"'{target['vnet']}', '{target['subnet']}')]")
            (HERE / "nat-template.json").write_text(json.dumps(archive, indent=2) + "\n", encoding="utf-8")
            spec = {k: self.plan[k] for k in ("targets", "region", "vmSize", "image")}
            (HERE / "nat-spec.json").write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
            self.check()
            self.command("deployment-submit", ["deployment", "group", "create", *common, "--no-wait",
                "--query", "{name:name,state:properties.provisioningState}"], action="deployment")
            deadline = time.monotonic() + self.lease["managedDeployment"]["timeoutSeconds"]
            changed = time.monotonic()
            last = None
            progress = []
            while True:
                self.check()
                assert time.monotonic() < deadline, "Managed deployment deadline reached"
                deployment = self.command("deployment-status", ["deployment", "group", "show", "-g", rg,
                    "-n", self.lease["taskId"], "--query",
                    "{name:name,state:properties.provisioningState,timestamp:properties.timestamp,error:properties.error}"],
                    timeout=min(90, max(1, deadline - time.monotonic())))
                operations = self.command("deployment-operations", ["deployment", "operation", "group", "list",
                    "-g", rg, "-n", self.lease["taskId"], "--query",
                    "[].{operation:properties.provisioningOperation,state:properties.provisioningState,"
                    "target:properties.targetResource.resourceName,type:properties.targetResource.resourceType,"
                    "timestamp:properties.timestamp,status:properties.statusMessage}"],
                    timeout=min(90, max(1, deadline - time.monotonic())))
                signal = json.dumps([deployment["state"], sorted(
                    (o.get("target") or "", o["state"]) for o in operations)])
                if signal != last:
                    changed, last = time.monotonic(), signal
                progress.append(dict(atUtc=utc().isoformat(), deployment=deployment, operations=operations))
                self.save("deployment-progress.json", progress)
                if deployment["state"] == "Succeeded":
                    break
                assert deployment["state"] not in ("Failed", "Canceled"), "Deployment failed; partial state retained"
                assert time.monotonic() - changed < 300, "No deployment progress for five minutes"
                time.sleep(min(30, max(0, deadline - time.monotonic())))
            self.save("write-journal.json", dict(deploymentSubmissions=1, mutationBatches=1,
                intendedResourcePuts=[{"type": r["type"], "name": r["name"]} for r in template["resources"]],
                implicitDisks=[t["disk"] for t in self.plan["targets"]], operations=operations,
                configurationActions=0, deleteSubmissions=0))
            readiness = []
            for target in self.plan["targets"]:
                vm = self.command(target["name"] + "-state", ["vm", "get-instance-view", "-g", rg,
                    "-n", target["name"], "--query",
                    "{name:name,size:hardwareProfile.vmSize,state:provisioningState,statuses:instanceView.statuses}"])
                assert vm["state"] == "Succeeded"
                assert any(s["code"] == "PowerState/running" for s in vm["statuses"])
                nic = self.command(target["nic"], ["network", "nic", "show", "-g", rg, "-n", target["nic"],
                    "--query", "{name:name,state:provisioningState,forwarding:enableIPForwarding,"
                    "ips:ipConfigurations[].{ip:privateIPAddress,method:privateIPAllocationMethod,primary:primary}}"])
                assert nic["state"] == "Succeeded"
                assert nic["forwarding"] == (target["role"] == "nva")
                assert [c["ip"] for c in nic["ips"]] == (
                    [target["ip"], target["alias"]] if target["role"] == "nva" else [target["ip"]])
                assert all(c["method"] == "Static" for c in nic["ips"])
                script = "set -eu\ncloud-init status --wait --long\n"
                if target["role"] == "nva":
                    script += (
                        "systemctl is-enabled lab-static-nat\nsystemctl is-active lab-static-nat\n"
                        "test \"$(sysctl -n net.ipv4.ip_forward)\" = 1\n"
                        f"ip -o -4 addr show | grep -F ' {target['alias']}/32 '\n"
                        "iptables -t nat -S\niptables -S FORWARD\n"
                    )
                elif target["role"] == "backend":
                    script += ("systemctl is-enabled lab-backend-http\nsystemctl is-active lab-backend-http\n"
                               "cat /opt/lab-http/index.html\n")
                script += "printf '\\nBOOTSTRAP_READY\\n'\n"
                status = self.command(target["name"] + "-bootstrap", ["vm", "run-command", "invoke",
                    "-g", rg, "-n", target["name"], "--command-id", "RunShellScript", "--scripts", script],
                    action="bootstrap-read")
                assert any("BOOTSTRAP_READY" in v.get("message", "") for v in status["value"]), "Bootstrap failed"
                readiness.append(dict(target=target, vm=vm, nic=nic, bootstrap="READY"))
                self.save("readiness.json", readiness)
            after = self.command("network-after", ["network", "vnet", "list", "-g", rg])
            assert fingerprint(after) == fingerprint(baseline), "Existing network configuration changed"
            self.state, self.reason = "completed", "Five VMs running; cloud-init and services ready; dataplane reserved for Niobe"
        except BaseException as error:
            self.reason = str(error)
        finally:
            self.save("verdict.json", dict(verdict="PASS" if self.state == "completed" else "BLOCKED",
                scope="Deployment and OS bootstrap only", reason=self.reason,
                atUtc=utc().isoformat(), retained=True, deleteSubmissions=0,
                childrenIdle=not self.active, queuedWork=[], actions=self.actions,
                retailDailyUsd=self.plan["retailCost"]["dailyTotal"]))
            self.persist(state=self.state, reason=self.reason, resourcesRetained=True)
            print(json.dumps(dict(state=self.state, reason=self.reason, evidencePath=str(self.out),
                                  childrenIdle=not self.active)))
        return self.state == "completed"


if __name__ == "__main__":
    raise SystemExit(0 if Deployment().run() else 1)
