"""Execute the locked experiment; explicit retention leases prohibit all deletion."""

import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import subprocess
import time


ROOT = Path(__file__).resolve().parents[3]
LAB = Path(__file__).resolve().parent.parent
LEASE = LAB / "deploy" / ".runtime-control" / "lease.json"
AZ_PYTHON = Path(r"C:\Program Files\Microsoft SDKs\Azure\CLI2\python.exe")
API = "2026-01-01"
RG = "rg-subnet-overlap-20261016-fde5ecf8"
PREFIXES = {
    "hub": ["10.0.0.0/16"],
    "spoke1": ["10.10.0.0/16", "192.168.0.0/16"],
    "spoke2": ["10.20.0.0/26", "192.168.0.0/16"],
}
SUBNETS = {
    "hub": {"hub10": "10.0.1.0/24"},
    "spoke1": {"spoke10": "10.10.1.0/24", "isolated192": "192.168.1.0/24"},
    "spoke2": {"spoke10": "10.20.0.0/27", "isolated192": "192.168.1.0/24"},
}
PAIRS = [
    ("hub", "to-spoke1", "spoke1", ["hub10"], ["spoke10"]),
    ("spoke1", "to-hub", "hub", ["spoke10"], ["hub10"]),
    ("hub", "to-spoke2", "spoke2", ["hub10"], ["spoke10"]),
    ("spoke2", "to-hub", "hub", ["spoke10"], ["hub10"]),
]


def utc():
    return datetime.now(timezone.utc)


def timestamp():
    return utc().isoformat()


class Gate(Exception):
    def __init__(self, verdict, reason):
        super().__init__(reason)
        self.verdict = verdict


class Job:
    """Windows kill-on-close job: every Azure CLI descendant shares its lifetime."""

    def __init__(self):
        class Basic(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD), ("min_ws", ctypes.c_size_t),
                ("max_ws", ctypes.c_size_t), ("active", wintypes.DWORD),
                ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD),
            ]

        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in
                        ("read_ops", "write_ops", "other_ops", "read", "write", "other")]

        class Extended(ctypes.Structure):
            _fields_ = [
                ("basic", Basic), ("io", IO),
                ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t),
            ]

        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        limits = Extended()
        limits.basic.flags = 0x2000
        if not self.handle or not self.kernel.SetInformationJobObject(
                self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise OSError(ctypes.get_last_error(), "Cannot enforce child job lifetime")

    def assign(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            process.kill()
            process.communicate(timeout=10)
            raise OSError(ctypes.get_last_error(), "Cannot contain Azure process")

    def close(self):
        if getattr(self, "handle", None):
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class Executor:
    def __init__(self):
        self.lease = json.loads(LEASE.read_text(encoding="utf-8-sig"))
        self.retained = self.retention_gate(self.lease)
        self.out = ROOT / self.lease["evidencePath"]
        self.out.mkdir(parents=True, exist_ok=True)
        self.redactions = []
        self.commands = 0
        self.overhead_calls = 20
        self.writes = 0
        self.batches = set()
        self.pids = []
        self.active = set()
        self.created = False
        self.rg_attempted = False
        self.baseline_absent = False
        self.restoring = False
        self.restore_deadline = None
        self.verdict = "BLOCKED"
        self.reason = "Preflight not completed"

    def sanitize(self, text):
        for value in self.redactions:
            text = text.replace(value, "<redacted-guid>")
        return text

    def save(self, name, value):
        text = json.dumps(value, indent=2, ensure_ascii=False)
        (self.out / name).write_text(self.sanitize(text) + "\n", encoding="utf-8")

    def persist(self, **extra):
        current = json.loads(LEASE.read_text(encoding="utf-8-sig"))
        current.update(extra)
        current.update({
            "toolCallsUsed": self.overhead_calls + self.commands,
            "externalCommandsUsed": self.commands,
            "mutationBatchesUsed": len(self.batches), "armWritesUsed": self.writes,
            "lastCheckpointUtc": timestamp(), "childProcessIds": self.pids,
            "runningChildren": sorted(self.active),
        })
        LEASE.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        self.lease = current

    def check(self, mutation=False):
        current = json.loads(LEASE.read_text(encoding="utf-8-sig"))
        if self.retention_gate(current) != self.retained:
            raise Gate("BLOCKED", "Lease retention policy changed during execution")
        if utc() >= datetime.fromisoformat(current["expiresAtUtc"].replace("Z", "+00:00")):
            raise Gate("BLOCKED", "Absolute lease expired")
        if (ROOT / current["sentinelPath"]).exists():
            raise Gate("BLOCKED", "STOP present; no further commands authorized")
        if current["state"] != "active":
            raise Gate("BLOCKED", f"Lease state {current['state']} is not active")
        if self.restore_deadline and time.monotonic() >= self.restore_deadline:
            raise Gate("BLOCKED", "Restore deadline reached")
        if not self.restoring:
            elapsed = (utc() - datetime.fromisoformat(current["createdAtUtc"].replace("Z", "+00:00"))).total_seconds()
            if (elapsed >= current["restoreMustStartByElapsedMinutes"] * 60 or
                    elapsed >= current["maxElapsedMinutes"] * 60 * 0.8 or
                    self.overhead_calls + self.commands >= current["maxToolCalls"] * 0.8):
                raise Gate("INCONCLUSIVE", "Experiment budget reserve reached")
            if mutation and len(self.batches) >= min(5, current["maxMutations"] * 0.8):
                raise Gate("BLOCKED", "No further experiment batches authorized")
        if self.overhead_calls + self.commands >= current["maxToolCalls"]:
            raise Gate("BLOCKED", "Command/tool-call budget exhausted")

    def command(self, name, args, batch=None, body=None):
        if "--method" in args and args[args.index("--method") + 1].lower() == "delete":
            current = json.loads(LEASE.read_text(encoding="utf-8-sig"))
            if self.retained or self.retention_gate(current) or not current.get("cleanupApproval"):
                raise Gate("BLOCKED", "DELETE forbidden without an explicit cleanup lease")
        self.check(mutation=batch is not None)
        if batch is not None:
            self.batches.add(batch)
            self.writes += 1
        self.commands += 1
        self.persist()
        start = timestamp()
        if body is not None:
            self.save(f"{name}-request.json", body)
            args += ["--headers", "Content-Type=application/json", "--body", json.dumps(body)]
        full = [str(AZ_PYTHON), "-IBm", "azure.cli"] + args + ["--only-show-errors", "--output", "json"]
        job = Job()
        proc = None
        error = None
        stdout, stderr = "", ""
        try:
            proc = subprocess.Popen(full, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            job.assign(proc)
            self.pids.append(proc.pid)
            self.active.add(proc.pid)
            deadline = min(time.monotonic() + self.lease["commandTimeoutSeconds"], time.monotonic() +
                           (datetime.fromisoformat(self.lease["expiresAtUtc"].replace("Z", "+00:00")) - utc()).total_seconds())
            while True:
                self.check()
                if time.monotonic() >= deadline:
                    raise Gate("INCONCLUSIVE", f"{name} exceeded bounded process deadline")
                try:
                    raw_out, raw_err = proc.communicate(timeout=min(1, deadline - time.monotonic()))
                    stdout = raw_out.decode("utf-8", errors="replace")
                    stderr = raw_err.decode("utf-8", errors="replace")
                    break
                except subprocess.TimeoutExpired:
                    continue
            if name == "account":
                account = json.loads(stdout) if proc.returncode == 0 else {}
                self.redactions.extend(v for k in ("id", "tenantId", "homeTenantId")
                                       if (v := account.get(k)))
                self.redactions.extend(v for v in (
                    account.get("name"), account.get("user", {}).get("name")) if v)
            self.check()
        except BaseException as exc:
            error = exc
        finally:
            job.close()
            if proc is not None:
                if proc.poll() is None:
                    proc.kill()
                raw_out, raw_err = proc.communicate(timeout=10)
                stdout = raw_out.decode("utf-8", errors="replace")
                stderr = raw_err.decode("utf-8", errors="replace")
                self.active.discard(proc.pid)
            record = {
                "startedAtUtc": start, "completedAtUtc": timestamp(),
                "command": ["az"] + args, "exitCode": proc.returncode if proc else None,
                "pid": proc.pid if proc else None, "batch": batch,
                "stdout": stdout, "stderr": stderr, "wrapperError": str(error) if error else None,
            }
            self.save(f"{name}.json", record)
            with (self.out / "journal.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(self.sanitize(json.dumps({k: v for k, v in record.items()
                                                       if k not in ("stdout", "stderr")})) + "\n")
            self.persist()
        if error:
            raise error
        return record

    def rest(self, name, method, url, batch=None, body=None):
        return self.command(name, ["rest", "--method", method, "--url", url], batch, body)

    def success(self, response, capability=False):
        if response["exitCode"] != 0:
            text = response["stderr"]
            verdict = "BLOCKED"
            if capability and any(word in text.lower() for word in ("overlap", "addressspaceoverlap")):
                verdict = "FAIL"
            raise Gate(verdict, text)
        try:
            return json.loads(response["stdout"]) if response["stdout"].strip() else {}
        except ValueError as exc:
            raise Gate("INCONCLUSIVE", "Non-JSON Azure response") from exc

    @staticmethod
    def absent(response):
        return response["exitCode"] != 0 and (
            "ResourceGroupNotFound" in response["stderr"] or
            ("404" in response["stderr"] and "not found" in response["stderr"].lower()))

    def checkpoint(self, phase, state, next_action):
        minutes = (utc() - datetime.fromisoformat(self.lease["createdAtUtc"].replace("Z", "+00:00"))).total_seconds() / 60
        print(f"LIVE {self.lease['taskId']} | {phase} | {minutes:.1f}/{self.lease['maxElapsedMinutes']}min | "
              f"calls {self.overhead_calls + self.commands}/75 | mutations {len(self.batches)}/6 | "
              f"state {state} | next {next_action}", flush=True)

    def get_vnets(self, name):
        results = {vnet: self.success(self.rest(f"{name}-{vnet}", "get", f"{self.net}/{vnet}?api-version={API}"))
                   for vnet in PREFIXES}
        self.save(f"{name}.json", results)
        for vnet, result in results.items():
            props = result["properties"]
            actual_subnets = {s["name"]: s["properties"].get("addressPrefix") for s in props["subnets"]}
            if set(props["addressSpace"]["addressPrefixes"]) != set(PREFIXES[vnet]) or actual_subnets != SUBNETS[vnet]:
                raise Gate("INCONCLUSIVE", f"Exact VNet address/subnet gate failed: {vnet}")
            if props["provisioningState"] != "Succeeded":
                raise Gate("INCONCLUSIVE", f"VNet is not Succeeded: {vnet}")
        return results

    def peer_url(self, pair):
        return f"{self.net}/{pair[0]}/virtualNetworkPeerings/{pair[1]}?api-version={API}"

    def peers(self, pairs, label):
        deadline = time.monotonic() + 180
        attempt = 0
        while True:
            attempt += 1
            results = []
            for pair in pairs:
                response = self.success(self.rest(f"{label}-{attempt}-{pair[0]}-{pair[1]}", "get", self.peer_url(pair)))
                results.append(response)
            if all(r["properties"].get("provisioningState") == "Succeeded" and
                   r["properties"].get("peeringState") == "Connected" for r in results):
                return results
            if any(r["properties"].get("provisioningState") == "Failed" for r in results):
                raise Gate("INCONCLUSIVE", "Peering provisioning failed")
            if time.monotonic() + 30 >= deadline:
                raise Gate("INCONCLUSIVE", "Peering connection polling exceeded three minutes")
            self.check()
            time.sleep(30)

    @staticmethod
    def retention_gate(lease):
        policy = lease.get("retentionPolicy")
        if policy is not None and policy != "keep_until_explicit_user_cleanup":
            raise Gate("BLOCKED", "Unknown retention policy")
        retained = policy == "keep_until_explicit_user_cleanup"
        if retained and (lease.get("cleanupApproval") or lease.get("restoreTimeoutMinutes") != 0):
            raise Gate("BLOCKED", "Retention lease contradicts cleanup approval or restore budget")
        return retained

    @staticmethod
    def provider_gate(provider):
        types = {r["resourceType"].lower(): r for r in provider.get("resourceTypes", [])}
        if (provider.get("registrationState") != "Registered" or
                API not in types.get("virtualnetworks", {}).get("apiVersions", [])):
            raise Gate("BLOCKED", f"Provider state={provider.get('registrationState')}; "
                       f"parent virtualNetworks must support {API}; no registration or fallback")

    def experiment(self):
        config = json.loads((Path.home() / ".copilot" / "skills" / "azure-lab" / "lab-config.json").read_text(encoding="utf-8-sig"))
        sub = config["azure_subscription_id"]
        self.redactions.append(sub)
        account = self.success(self.command("account", ["account", "show"]))
        if account["id"].lower() != sub.lower() or account.get("state") != "Enabled":
            raise Gate("BLOCKED", "Active account does not match enabled configured subscription")
        self.base = f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{RG}"
        self.net = f"{self.base}/providers/Microsoft.Network/virtualNetworks"
        provider = self.success(self.command("provider", ["rest", "--method", "get", "--url",
            f"https://management.azure.com/subscriptions/{sub}/providers/Microsoft.Network?api-version=2021-04-01",
            "--query", "{registrationState:registrationState,resourceTypes:resourceTypes[?resourceType=='virtualNetworks'].{resourceType:resourceType,apiVersions:apiVersions}}"]))
        self.provider_gate(provider)
        self.save("api-gate.json", {
            "registrationState": provider["registrationState"], "parentApiSupported": True,
            "apiVersion": API, "childMetadataRequired": False,
            "documentedContract": "https://learn.microsoft.com/en-us/rest/api/virtualnetwork/virtual-network-peerings/create-or-update?view=rest-virtualnetwork-2026-01-01",
            "capabilityGate": "First approved peering PUT; no registration or fallback",
        })
        baseline = self.rest("baseline", "get", f"{self.base}?api-version=2022-09-01")
        if not self.absent(baseline):
            existing = self.success(baseline)
            if self.retained:
                tags = existing.get("tags", {})
                if (existing.get("name") != RG or existing.get("location") != "swedencentral" or
                        tags.get("lab") != "true" or tags.get("created_by") != "copilot-lab" or
                        not tags.get("correlation_id")):
                    raise Gate("BLOCKED", "Existing RG ownership mismatch; no overwrites authorized")
                self.get_vnets("existing-vnets")
                self.success(self.rest("existing-inventory", "get",
                                      f"{self.base}/resources?api-version=2021-04-01"))
                raise Gate("BLOCKED", "Unexpected existing RG; inventory captured, no overwrites authorized")
            raise Gate("BLOCKED", "Exact RG baseline is not authenticated ResourceGroupNotFound")
        self.baseline_absent = True
        tags = {"lab": "true", "created_by": "copilot-lab", "correlation_id": self.lease["taskId"]}
        self.rg_attempted = True
        self.success(self.rest("put-rg", "put", f"{self.base}?api-version=2022-09-01", 1,
                               {"location": "swedencentral", "tags": tags}))
        self.created = True
        for vnet in PREFIXES:
            body = {"location": "swedencentral", "tags": tags, "properties": {
                "addressSpace": {"addressPrefixes": PREFIXES[vnet]},
                "subnets": [{"name": name, "properties": {"addressPrefix": prefix}}
                            for name, prefix in SUBNETS[vnet].items()]}}
            self.success(self.rest(f"put-{vnet}", "put", f"{self.net}/{vnet}?api-version={API}", 2, body))
        self.get_vnets("vnets-before")
        for index, pair in enumerate(PAIRS):
            local, peer, remote, local_names, remote_names = pair
            body = {"properties": {
                "remoteVirtualNetwork": {"id": f"{self.net}/{remote}".replace("https://management.azure.com", "")},
                "peerCompleteVnets": False, "localSubnetNames": local_names,
                "remoteSubnetNames": remote_names, "enableOnlyIPv6Peering": False,
                "allowVirtualNetworkAccess": True, "allowForwardedTraffic": False,
                "allowGatewayTransit": False, "useRemoteGateways": False}}
            self.success(self.rest(f"put-{local}-{peer}", "put", self.peer_url(pair),
                                   3 if index < 2 else 4, body), capability=True)
            if index == 1:
                self.save("peerings-first-pair.json", self.peers(PAIRS[:2], "first-pair"))
        peerings = self.peers(PAIRS, "final")
        self.save("peerings-final.json", peerings)
        self.get_vnets("vnets-final")
        if self.retained:
            resource = self.success(self.rest("rg-final", "get", f"{self.base}?api-version=2022-09-01"))
            if resource.get("location") != "swedencentral" or resource.get("tags") != tags:
                raise Gate("INCONCLUSIVE", "Final retained RG location/ownership gate failed")
        for pair, response in zip(PAIRS, peerings):
            props = response["properties"]
            if props.get("peerCompleteVnets") is not False or props.get("localSubnetNames") != pair[3] or props.get("remoteSubnetNames") != pair[4]:
                raise Gate("INCONCLUSIVE", "Returned exact subnet-selector gate failed")
            for field, vnet in (("localAddressSpace", pair[0]), ("remoteAddressSpace", pair[2])):
                projected = props.get(field, {}).get("addressPrefixes")
                selected = ipaddress.ip_network(next(iter(SUBNETS[vnet].values())))
                parent = ipaddress.ip_network(PREFIXES[vnet][0])
                if (not projected or not all(ipaddress.ip_network(p).subnet_of(parent) for p in projected)
                        or not any(selected.subnet_of(ipaddress.ip_network(p)) for p in projected)):
                    raise Gate("INCONCLUSIVE", f"Selected address-space projection missing or outside unique parent: {field}")
                if any(ipaddress.ip_network(p).overlaps(ipaddress.ip_network("192.168.0.0/16")) for p in projected):
                    raise Gate("INCONCLUSIVE", "Excluded prefix present in peered projection")
        self.verdict = "PASS"
        self.reason = "All four peerings simultaneously Succeeded/Connected with exact selectors and unique selected projections; excluded overlap and spoke2 /26 retained. Control plane only."

    def restore(self):
        current = json.loads(LEASE.read_text(encoding="utf-8-sig"))
        if self.retained or self.retention_gate(current) or not current.get("cleanupApproval"):
            raise Gate("BLOCKED", "Restore deletion forbidden by retention or missing cleanup approval")
        self.restoring = True
        self.restore_deadline = time.monotonic() + self.lease["restoreTimeoutMinutes"] * 60
        self.checkpoint("restore", "restoring", "verify ownership and submit one scoped RG DELETE")
        response = self.rest("restore-ownership", "get", f"{self.base}?api-version=2022-09-01")
        if self.absent(response):
            self.save("restore.json", {"restored": True, "authenticated404": True,
                                     "reason": "RG absent after creation attempt", "completedAtUtc": timestamp()})
            return True
        resource = self.success(response)
        if (not self.baseline_absent or resource.get("name") != RG or
                resource.get("id", "").lower() != self.base.replace("https://management.azure.com", "").lower() or
                resource.get("tags", {}).get("correlation_id") != self.lease["taskId"]):
            raise Gate("BLOCKED", "Restore ownership gate failed; no DELETE submitted")
        self.success(self.rest("delete-rg", "delete", f"{self.base}?api-version=2022-09-01", 5))
        attempt = 0
        while True:
            self.check()
            time.sleep(30)
            attempt += 1
            response = self.rest(f"restore-poll-{attempt}", "get", f"{self.base}?api-version=2022-09-01")
            if self.absent(response):
                self.save("restore.json", {"restored": True, "authenticated404": True,
                                         "completedAtUtc": timestamp(), "deleteSubmissions": 1})
                return True
            self.success(response)

    def run(self):
        if self.lease["state"] != "ready" or not (
                self.lease.get("deploymentApproval") if self.retained else self.lease.get("cleanupApproval")):
            raise Gate("BLOCKED", "Lease is not ready with explicit deployment/cleanup policy approval")
        if (ROOT / self.lease["sentinelPath"]).exists() or utc() >= datetime.fromisoformat(self.lease["expiresAtUtc"].replace("Z", "+00:00")):
            raise Gate("BLOCKED", "STOP or stale lease prevents activation")
        self.persist(state="active", startedAtUtc=timestamp())
        self.checkpoint("activation", "running", "account/provider/API/baseline checks")
        restored = False
        try:
            self.experiment()
        except Gate as exc:
            self.verdict, self.reason = exc.verdict, str(exc)
        except Exception as exc:
            self.verdict, self.reason = "BLOCKED", f"Executor error: {type(exc).__name__}: {exc}"
        self.save("verdict.json", {"verdict": self.verdict, "reason": self.reason,
                                  "decisiveAtUtc": timestamp(), "dataPlaneClaim": False})
        self.checkpoint(self.verdict, "verdict", "retain all resources; no DELETE" if self.retained else
                        "approved scoped restore" if self.rg_attempted else "close without mutations")
        if self.retained:
            self.save("retention.json", {
                "retentionPolicy": self.lease["retentionPolicy"], "deletionAuthorized": False,
                "deleteSubmissions": 0, "rgCreationAttempted": self.rg_attempted,
                "partialResourcesPreservedOnFailure": self.verdict != "PASS",
                "completedAtUtc": timestamp(),
            })
        elif self.rg_attempted:
            try:
                restored = self.restore()
            except Exception as exc:
                self.save("restore.json", {"restored": False, "blocked": self.sanitize(str(exc)),
                                         "completedAtUtc": timestamp()})
        else:
            restored = self.baseline_absent
            self.save("restore.json", {"restored": restored, "mutationFree": True,
                                     "reason": "No resources created; no cleanup authorized or required"})
        state = ("rolled-back" if restored and self.rg_attempted else
                 "completed" if self.verdict == "PASS" else "blocked")
        self.save("process-idle.json", {"runningChildren": sorted(self.active),
                                      "allSpawnedProcessesReaped": not self.active,
                                      "childPids": self.pids, "queuedWork": [],
                                      "proof": "Each CLI process communicated/reaped; its kill-on-close Windows job closed",
                                      "recordedAtUtc": timestamp()})
        self.persist(state=state, verdict=self.verdict, verdictPath=str(self.out / "verdict.json"),
                     restored=restored, resourcesRetained=self.retained, queuedWork=[], completedAtUtc=timestamp())
        self.checkpoint("closure", "stopped" if restored or state == "completed" else "blocked", "return; no queued work")
        print(json.dumps({"verdict": self.verdict, "reason": self.reason, "restored": restored,
                          "armWrites": self.writes, "mutationBatches": len(self.batches),
                          "externalCommands": self.commands, "runningChildren": sorted(self.active)}), flush=True)


if __name__ == "__main__":
    Executor().run()
