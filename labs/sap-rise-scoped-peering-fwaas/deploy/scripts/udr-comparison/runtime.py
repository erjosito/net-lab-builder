"""Lease-gated CLI transport. Importing this module never contacts Azure."""
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

RG = "rg-saprise-swedencentral"
CONTROL = Path(__file__).resolve().parents[2] / ".runtime-control"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".pending")
    pending.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def utc(value):
    result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Lease timestamps must include timezone")
    return result


class Runtime:
    def __init__(self, args, owner):
        self.args, self.owner = args, owner
        self.lease_path = Path(args.lease)
        self.out = Path(args.out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.audit_path = self.out / ("lease-" + self.lease_path.stem + ".json")
        # One CLI invocation owns a lease's counters at a time. OS releases the
        # lock on exit/crash; retained .lock files are harmless, not stale leases.
        self._lock = self.audit_path.with_suffix(".lock").open("a+b")
        self._lock.write(b"\0")
        self._lock.flush()
        self._lock.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(self._lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.audit = load(self.audit_path) if self.audit_path.exists() else {
            "calls": [], "mutations": 0, "forward": 0, "reserved": 0}
        self.guard()
        az = shutil.which("az")
        if not az:
            raise RuntimeError("Azure CLI missing; no installation performed")
        python = Path(az).parent.parent / "python.exe"
        self.az = [str(python), "-IBm", "azure.cli"] if os.name == "nt" and python.exists() else [az]
        if os.name == "nt" and not python.exists():
            raise RuntimeError("Expected Azure CLI bundled Python; unsafe .cmd fallback refused")

    def guard(self, closing=False, running=False):
        lease = load(self.lease_path)
        now = dt.datetime.now(dt.timezone.utc)
        if (lease["state"] != "active" or lease["ownerRole"] != self.owner
                or lease.get("phase") != self.args.phase
                or (CONTROL / "STOP").exists()
                or (self.lease_path.parent / "STOP").exists()
                or now >= utc(lease["expiresAtUtc"])):
            raise RuntimeError("BLOCKED: lease phase/owner/state/expiry/STOP")
        if not lease.get("taskId") or not lease.get("subscriptionId"):
            raise RuntimeError("Lease needs taskId and subscriptionId")
        if self.audit.get("taskId", lease["taskId"]) != lease["taskId"]:
            raise RuntimeError("Do not reuse a ledger path for another lease")
        self.audit["taskId"] = lease["taskId"]
        if not running:
            used = len(self.audit["calls"]) + lease.get("toolCallsBeforeRunner", 0)
            if used >= lease["maxToolCalls"]:
                raise RuntimeError("Call budget exhausted")
            if not closing:
                duration = (utc(lease["expiresAtUtc"]) - utc(lease["startedAtUtc"])).total_seconds()
                elapsed = (now - utc(lease["startedAtUtc"])).total_seconds()
                if elapsed >= duration * .8 or used >= lease["maxToolCalls"] * .8:
                    raise RuntimeError("80% time/call boundary; closure only")
        return lease

    def command(self, label, argv, cost=0, inverse_cost=0, closing=False, timeout=60):
        lease = self.guard(closing)
        if cost:
            allowed = lease.get("allowedMutations", [])
            if label not in allowed:
                raise RuntimeError("Mutation not named in lease: " + label)
            cap = min(6, lease["maxMutations"])
            if self.args.phase == "restore":
                cap = min(cap, 3)
            if self.audit["mutations"] + cost > cap:
                raise RuntimeError("Mutation budget exhausted")
            if not closing:
                if (self.audit["forward"] + cost > 3
                        or self.audit["mutations"] + self.audit["reserved"] + cost + inverse_cost > cap):
                    raise RuntimeError("Reserve every inverse; maximum three forward operations")
            self.audit["mutations"] += cost
            self.audit["reserved"] += inverse_cost
            if not closing:
                self.audit["forward"] += cost
        remaining = (utc(lease["expiresAtUtc"]) - dt.datetime.now(dt.timezone.utc)).total_seconds()
        timeout = min(timeout, lease["commandTimeoutSeconds"], remaining - 2)
        if timeout <= 0:
            raise RuntimeError("No command time remaining")
        full = self.az + argv + ["--subscription", lease["subscriptionId"], "--only-show-errors", "-o", "json"]
        entry = {"label": label, "argv": argv, "cost": cost, "status": "submitted"}
        self.audit["calls"].append(entry)
        save(self.audit_path, self.audit)
        process = None
        try:
            process = subprocess.Popen(full, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, encoding="utf-8")
            entry["pid"] = process.pid
            deadline = time.monotonic() + timeout
            while True:
                self.guard(closing=True, running=True)
                if time.monotonic() >= deadline:
                    raise TimeoutError(label + ": bounded timeout; remote completion UNKNOWN")
                try:
                    stdout, stderr = process.communicate(timeout=min(1, deadline - time.monotonic()))
                    break
                except subprocess.TimeoutExpired:
                    continue
            entry["exitCode"] = process.returncode
            entry["stderr"] = stderr[-2000:]
            save(self.out / (label.replace(":", "-") + ".json"), {
                "stdout": stdout, "stderr": stderr, "exitCode": process.returncode})
            if process.returncode:
                raise RuntimeError(f"{label}: exit {process.returncode}: {stderr[-500:]}")
            entry["status"] = "succeeded"
            return json.loads(stdout) if stdout.strip() else None
        except BaseException:
            entry["status"] = "unknown" if cost else "failed"
            if process and process.poll() is None:
                if os.name == "nt":
                    subprocess.run(["pwsh", "-NoProfile", "-Command",
                                    f"[System.Diagnostics.Process]::GetProcessById({process.pid}).Kill($true)"],
                                   capture_output=True, timeout=10, check=True)
                else:
                    process.kill()
                process.wait(timeout=10)
            raise
        finally:
            save(self.audit_path, self.audit)

    def guest(self, label, vm, script, **kwargs):
        result = self.command(label, ["vm", "run-command", "invoke", "-g", RG, "-n", vm,
            "--command-id", "RunShellScript", "--scripts", script], timeout=300, **kwargs)
        text = "\n".join(v.get("message", "") for v in result.get("value", []))
        if "UDR_STATUS=0" not in text or any(
                v.get("code", "").endswith("/failed") for v in result.get("value", [])):
            raise RuntimeError(label + ": guest status missing/failed; inspect raw output")
        return text


def arguments(parser):
    parser.add_argument("--lease", required=True, help="Coordinator-issued JSON lease; never generated here")
    parser.add_argument("--out", required=True, help="New correlation evidence directory")
