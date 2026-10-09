import datetime as dt
import json
import pathlib
import re
import shutil
import subprocess
import time

BASE = pathlib.Path(__file__).resolve().parent.parent
CONTROL = BASE / "deploy" / ".runtime-control"
LEASE = CONTROL / "forced-control-mutation.json"
OUT = BASE / "show-output" / "forced-control-mutation-20261009T1241Z"
OUT.mkdir(parents=True, exist_ok=True)
START = time.monotonic()
attempts = 0
mutations = 0
records = []


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sanitize(value):
    return re.sub(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        "<redacted-id>",
        value,
    )


def save(name, value):
    (OUT / name).write_text(
        sanitize(json.dumps(value, indent=2)), encoding="utf-8"
    )


def route_state(routes):
    return sorted(
        (r["name"], r["addressPrefix"], r["nextHopType"], r.get("nextHopIpAddress") or "")
        for r in routes
    )


def guard():
    lease = json.loads(LEASE.read_text(encoding="utf-8-sig"))
    if (CONTROL / "STOP").exists() or lease["state"] != "active":
        raise RuntimeError("STOP or inactive lease")
    if dt.datetime.now(dt.timezone.utc) >= dt.datetime.fromisoformat(
        lease["expiresAtUtc"].replace("Z", "+00:00")
    ):
        raise RuntimeError("Lease expired")
    if time.monotonic() - START >= 240:
        raise RuntimeError("Five-minute execution budget exhausted")
    return lease


def command(name, args):
    lease = guard()
    timeout = min(lease["commandTimeoutSeconds"], max(1, int(240 - (time.monotonic() - START))))
    argv = [shutil.which("az") or "az", *args, "--only-show-errors", "-o", "json"]
    record = {
        "command": subprocess.list2cmdline(argv),
        "startedAtUtc": now(),
        "timeoutSeconds": timeout,
        "timedOut": False,
    }
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    record["pid"] = process.pid
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        record["timedOut"] = True
        kill_start = now()
        kill_args = ["taskkill", "/PID", str(process.pid), "/T", "/F"]
        kill = subprocess.run(kill_args, capture_output=True, text=True, timeout=15)
        records.append({
            "command": subprocess.list2cmdline(kill_args),
            "startedAtUtc": kill_start, "endedAtUtc": now(),
            "timeoutSeconds": 15, "timedOut": False,
            "stdout": kill.stdout, "stderr": kill.stderr, "exitCode": kill.returncode,
        })
        stdout, stderr = process.communicate(timeout=10)
    record.update(
        endedAtUtc=now(), stdout=stdout, stderr=stderr, exitCode=process.returncode
    )
    records.append(record)
    save(name + ".json", record)
    save("commands.json", records)
    if record["timedOut"]:
        raise RuntimeError("External command timeout; no pending child")
    return record, json.loads(stdout) if process.returncode == 0 and stdout.strip() else None


COMMON = ["-g", "rg-aks-agic-shared-udr"]
SHOW = ["network", "route-table", "show", *COMMON, "-n", "rt-shared"]
UPDATE = ["network", "route-table", "route", "update", *COMMON,
          "--route-table-name", "rt-shared", "-n", "default"]
result = {"startedAtUtc": now(), "verdict": "BLOCKED"}
try:
    guard()
    for relative in [
        pathlib.Path(".squad") / "live-lab-policy.md",
        pathlib.Path(".squad") / "agents" / "tank" / "charter.md",
        BASE / "baseline-verdict.md",
        BASE / "design.md",
        LEASE,
    ]:
        started = now()
        text = relative.read_text(encoding="utf-8-sig")
        records.append({
            "command": "Read input " + str(relative), "startedAtUtc": started,
            "endedAtUtc": now(), "stdout": text, "stderr": "", "exitCode": 0,
            "timeoutSeconds": 0, "timedOut": False,
        })
    save("commands.json", records)
    pre_record, pre = command("01-route-table-before", SHOW)
    if pre_record["exitCode"] != 0:
        raise RuntimeError("Pre-snapshot failed")
    routes = pre["routes"]
    default = next(r for r in routes if r["name"] == "default")
    others = [r for r in routes if r["name"] != "default"]
    subnet_names = {s["id"].split("/")[-1] for s in pre["subnets"]}
    if subnet_names != {"snet-aks", "snet-appgw"}:
        raise RuntimeError("Unexpected associated subnets")
    if default["addressPrefix"] != "0.0.0.0/0" or default["nextHopType"] != "Internet":
        raise RuntimeError("Baseline default is not Internet")
    if not any(r["addressPrefix"] == "10.244.0.0/24" and
               r["nextHopType"] == "VirtualAppliance" and
               r["nextHopIpAddress"] == "10.21.1.4" for r in others):
        raise RuntimeError("Expected pod route absent")
    if any(r["addressPrefix"] == "GatewayManager" for r in others):
        raise RuntimeError("GatewayManager route already present")
    guard()
    attempts += 1
    action, _ = command("02-default-to-nva", UPDATE + [
        "--next-hop-type", "VirtualAppliance", "--next-hop-ip-address", "10.20.1.4"
    ])
    result["mutationCommandCompletedAtUtc"] = action["endedAtUtc"]
    post_record, post = command("03-route-table-after", SHOW)
    if post_record["exitCode"] != 0:
        raise RuntimeError("Post-snapshot failed; final state unverified")
    after = next(r for r in post["routes"] if r["name"] == "default")
    unchanged = (
        route_state([r for r in post["routes"] if r["name"] != "default"]) == route_state(others)
        and post["subnets"] == pre["subnets"]
    )
    accepted = (after["addressPrefix"] == "0.0.0.0/0" and
                after["nextHopType"] == "VirtualAppliance" and
                after["nextHopIpAddress"] == "10.20.1.4")
    result.update(podRoutesAndAssociationsUnchanged=unchanged,
                  defaultRoute=after, associatedSubnets=post["subnets"])
    if action["exitCode"] == 0 and accepted and unchanged:
        mutations = 1
        result.update(verdict="ACCEPTED", restoreState="Deliberately left NVA default for Niobe",
                      convergenceClockUtc=action["endedAtUtc"])
    elif action["exitCode"] != 0 and route_state([after]) == route_state([default]) and unchanged:
        result.update(verdict="ADMISSION_REJECT", restoreState="Baseline unchanged; no rollback",
                      admissionError=action["stderr"])
    else:
        mutations = int(route_state([after]) != route_state([default]))
        if mutations:
            guard()
            attempts += 1
            rollback, _ = command("04-rollback-unexpected-partial", UPDATE + [
                "--next-hop-type", "Internet", "--remove", "nextHopIpAddress"
            ])
            mutations += int(rollback["exitCode"] == 0)
            final_record, final = command("05-rollback-route-table", SHOW)
            result["restoreVerified"] = (
                final_record["exitCode"] == 0
                and next(r for r in final["routes"] if r["name"] == "default")["nextHopType"] == "Internet"
                and route_state([r for r in final["routes"] if r["name"] != "default"]) == route_state(others)
                and final["subnets"] == pre["subnets"]
            )
        result["error"] = "Unexpected partial state; bounded rollback only"
except Exception as exc:
    result["error"] = str(exc)
finally:
    result.update(endedAtUtc=now(), mutationCount=mutations,
                  mutationAttempts=attempts, pendingChildren=0)
    save("verdict.json", result)
    lease = json.loads(LEASE.read_text(encoding="utf-8-sig"))
    lease.update(state="completed" if result["verdict"] in ["ACCEPTED", "ADMISSION_REJECT"] else "blocked",
                 mutationCount=mutations, mutationAttempts=attempts, pendingChildren=0,
                 lastCheckpointUtc=now(), verdict=result["verdict"],
                 evidencePath=str(OUT.relative_to(BASE)))
    LEASE.write_text(json.dumps(lease, indent=2), encoding="utf-8")
    print(sanitize(json.dumps(result, indent=2)))
