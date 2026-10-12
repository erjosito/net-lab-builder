"""Bounded transport; imports and planning never execute Azure commands."""
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time


def sibling(name):
    path = Path(__file__).resolve().parent.parent / "udr-comparison" / (name + ".py")
    spec = importlib.util.spec_from_file_location("enforcement_legacy_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


legacy = sibling("runtime")
load, save, utc = legacy.load, legacy.save, legacy.utc
RG, CONTROL = legacy.RG, legacy.CONTROL


def now():
    return dt.datetime.now(dt.timezone.utc)


class Blocked(RuntimeError):
    pass


def explicit_rejection(stderr):
    # Only an explicit service-side 400 is a trial rejection. Authentication,
    # connectivity, timeout and CLI argument errors are NOT experiment results.
    status = re.search(r"\bBad Request\b|HTTP(?: status)?[ :]+400\b|\bStatus Code: 400\b", stderr, re.I)
    if status and re.search(r'"error"\s*:\s*\{.*?"code"\s*:\s*"[^"]+"', stderr, re.S):
        return True
    start = stderr.find('{"error":')
    if start < 0:
        return False
    try:
        payload, _ = json.JSONDecoder().raw_decode(stderr[start:])
    except json.JSONDecodeError:
        return False
    error = payload.get("error", {})
    return (
        error.get("code") == "InvalidRequestFormat"
        and any(d.get("code") == "InvalidJson"
                and "NextHopType" in d.get("message", "")
                and "VNetPeering" in d.get("message", "")
                for d in error.get("details", []))
    )


class Lock:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open("a+b")
        self.file.write(b"\0")
        self.file.flush()
        self.file.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def close(self):
        self.file.close()


class Transport:
    def __init__(self, args, state):
        self.args, self.state = args, state
        self.owner = "Niobe" if args.phase == "inventory" or args.phase == "verify" or args.phase.startswith("collect") else "Tank"
        self.lease_path = Path(args.lease)
        self.initial = load(self.lease_path)
        self.out = Path(args.out)
        digest = hashlib.sha256(self.initial["taskId"].encode()).hexdigest()[:24]
        self.lock = Lock(CONTROL / ("enforcement-" + digest + ".lock"))
        self.ledger_path = CONTROL / ("enforcement-" + digest + ".json")
        if self.ledger_path.exists():
            self.lock.close()
            raise Blocked("Lease already consumed; fresh coordinator lease required")
        self.audit = {"taskId": self.initial["taskId"], "phase": args.phase, "calls": 0,
                      "mutations": 0, "forward": 0, "reserved": 0, "status": "active"}
        self.guard()
        az = shutil.which("az")
        bundled = Path(az).parent.parent / "python.exe" if az else Path("missing")
        if os.name == "nt":
            if not az or not bundled.is_file():
                raise Blocked("Bundled Azure CLI Python required; az.cmd fallback forbidden")
            self.az = [str(bundled), "-IBm", "azure.cli"]
        elif az:
            self.az = [az]
        else:
            raise Blocked("Azure CLI missing; no installation attempted")
        self.persist()
        self.checkpoint("start")

    def persist(self):
        save(self.ledger_path, self.audit)
        save(self.out / "state.json", self.state)

    def checkpoint(self, status):
        lease = load(self.lease_path)
        elapsed = int((now() - utc(lease["startedAtUtc"])).total_seconds())
        limit = int((utc(lease["expiresAtUtc"]) - utc(lease["startedAtUtc"])).total_seconds())
        text = (f"LIVE {lease['taskId']} | {self.args.phase} | {elapsed}/{limit}s | "
                f"calls {self.audit['calls']}/{lease['maxToolCalls']} | "
                f"mutations {self.audit['mutations']}/{lease['maxMutations']} | "
                f"state {status} | next return-or-approved-checkpoint")
        self.audit["lastCheckpointUtc"] = now().isoformat()
        self.audit["checkpoint"] = text
        self.persist()
        print(text)

    def guard(self, closing=False, running=False):
        lease = load(self.lease_path)
        if any(lease.get(k) != self.initial.get(k) for k in
               ("taskId", "phase", "ownerRole", "subscriptionId", "startedAtUtc",
                "expiresAtUtc", "maxMutations", "maxToolCalls", "commandTimeoutSeconds",
                "allowedMutations", "restoreTimeoutMinutes")):
            raise Blocked("Lease scope changed after start")
        if (lease.get("state") != "active" or lease.get("phase") != self.args.phase
                or lease.get("ownerRole") != self.owner or not lease.get("subscriptionId")
                or (CONTROL / "STOP").exists() or (self.lease_path.parent / "STOP").exists()
                or now() >= utc(lease["expiresAtUtc"])):
            raise Blocked("STOP, expiry, owner or phase guard")
        if now().timestamp() >= getattr(self, "restore_deadline", float("inf")):
            raise Blocked("Restore time ceiling")
        duration = (utc(lease["expiresAtUtc"]) - utc(lease["startedAtUtc"])).total_seconds()
        elapsed = (now() - utc(lease["startedAtUtc"])).total_seconds()
        if duration <= 0 or elapsed < 0 or duration > (480 if self.owner == "Niobe" else 900):
            raise Blocked("Lease duration must be <=8m Niobe / <=15m Tank")
        if lease["maxToolCalls"] > (15 if self.owner == "Niobe" else 25):
            raise Blocked("Lease call ceiling exceeds scenario")
        if lease["maxMutations"] > (0 if self.owner == "Niobe" else 6):
            raise Blocked("Lease mutation ceiling exceeds scenario")
        if not 0 < lease["restoreTimeoutMinutes"] <= 15:
            raise Blocked("Invalid restore timeout")
        if (now() - utc(self.state["startedAtUtc"])).total_seconds() >= 9000:
            raise Blocked("Overall 150-minute ceiling")
        if not running:
            used = self.audit["calls"] + lease.get("toolCallsBeforeRunner", 0)
            if used >= lease["maxToolCalls"] or self.state["calls"] >= 240:
                raise Blocked("Call ceiling")
            if not closing and (elapsed >= duration * .8 or used >= lease["maxToolCalls"] * .8
                                or (self.audit["mutations"] and self.audit["mutations"] >= lease["maxMutations"] * .8)):
                raise Blocked("80% boundary; no new forward commands")
        return lease

    def authorize(self, operations):
        lease = self.guard()
        labels = []
        forward = inverse = 0
        for op in operations:
            labels.append(op["label"])
            forward += op["cost"]
            inverse += sum(x["cost"] for x in op["inverse"])
            labels.extend(x["label"] for x in op["inverse"])
        if forward > 3 or forward + inverse > min(6, lease["maxMutations"]):
            raise Blocked("Plan exceeds three forwards plus complete inverse reservation")
        if not set(labels).issubset(lease.get("allowedMutations", [])):
            raise Blocked("Lease must name every forward and inverse: " + ", ".join(labels))
        if self.state["mutations"] + forward + inverse > 48:
            raise Blocked("Overall 48-mutation ceiling including reserved rollback")
        calls = sum((3 if op.get("power") else 4) + op.get("additionalReads", 0) for op in operations)
        calls += sum(2 if inv.get("power") else 3 for op in operations for inv in op["inverse"])
        if calls + self.audit["calls"] + lease.get("toolCallsBeforeRunner", 0) > lease["maxToolCalls"]:
            raise Blocked("Insufficient calls reserved for forward checks and all inverses")
        self.audit["reserved"] = inverse
        self.persist()

    def command(self, label, argv, cost=0, closing=False, timeout=120, trial=False):
        lease = self.guard(closing)
        remaining = (utc(lease["expiresAtUtc"]) - now()).total_seconds()
        if closing:
            remaining = min(remaining, getattr(self, "restore_deadline", float("inf")) - now().timestamp())
        if not closing and self.owner == "Tank":
            remaining -= 300
        timeout = min(timeout, lease["commandTimeoutSeconds"], remaining - 2)
        if timeout <= 0:
            raise Blocked("Final five minutes reserved for rollback")
        if cost:
            if label not in lease.get("allowedMutations", []):
                raise Blocked("Unapproved mutation: " + label)
            if self.audit["mutations"] + cost > lease["maxMutations"] or self.state["mutations"] + cost > 48:
                raise Blocked("Mutation ceiling")
            if not closing and self.audit["forward"] + cost > 3:
                raise Blocked("Three-forward ceiling")
            self.audit["mutations"] += cost
            self.state["mutations"] += cost
            if closing:
                self.audit["reserved"] = max(0, self.audit["reserved"] - cost)
            else:
                self.audit["forward"] += cost
        self.audit["calls"] += 1
        self.state["calls"] += 1
        entry = {"label": label, "argv": argv, "utc": now().isoformat(), "cost": cost,
                 "timeoutSeconds": timeout, "status": "submitted"}
        target = self.out / self.args.phase / (f"{self.audit['calls']:02d}-" + label.replace(":", "-") + ".json")
        save(target, entry)
        self.persist()
        process = None
        try:
            process = subprocess.Popen(self.az + argv + ["--subscription", lease["subscriptionId"],
                "--only-show-errors", "-o", "json"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", start_new_session=os.name != "nt")
            entry["pid"] = process.pid
            save(target, entry)
            deadline = time.monotonic() + timeout
            while True:
                self.guard(closing=True, running=True)
                if time.monotonic() >= deadline:
                    raise TimeoutError("Local timeout; remote completion UNKNOWN")
                try:
                    stdout, stderr = process.communicate(timeout=min(1, deadline - time.monotonic()))
                    break
                except subprocess.TimeoutExpired:
                    continue
            entry.update(stdout=stdout, stderr=stderr, exitCode=process.returncode)
            if process.returncode:
                if trial and explicit_rejection(stderr):
                    entry["status"] = "rejected"
                    entry["httpStatus"] = 400
                    return {"_rejected": True}
                raise Blocked("Command failed; inspect " + str(target))
            self.guard(closing=True, running=True)
            entry["status"] = "succeeded"
            return json.loads(stdout) if stdout.strip() else None
        except BaseException:
            entry["status"] = "unknown" if cost else "failed"
            if process and process.poll() is None:
                if os.name == "nt":
                    subprocess.run(["pwsh", "-NoProfile", "-Command",
                        f"[System.Diagnostics.Process]::GetProcessById({process.pid}).Kill($true)"],
                        timeout=10, capture_output=True, check=True)
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate(timeout=10)
                entry.update(stdout=stdout, stderr=stderr)
            raise
        finally:
            entry["finishedAtUtc"] = now().isoformat()
            save(target, entry)
            self.persist()

    def finish(self, status):
        self.audit["status"] = status
        lease = load(self.lease_path)
        if lease.get("taskId") == self.initial["taskId"]:
            lease.update(state=status, lastCheckpointUtc=now().isoformat(),
                         mutationCount=self.audit["mutations"], toolCallCount=self.audit["calls"])
            save(self.lease_path, lease)
        self.checkpoint(status)
        self.lock.close()
