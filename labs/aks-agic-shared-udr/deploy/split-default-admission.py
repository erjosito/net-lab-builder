"""One bounded, lease-controlled admission test; no runtime validation."""
import datetime as dt
import json
import pathlib
import re
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parents[3]
LAB = ROOT / "labs" / "aks-agic-shared-udr"
CONTROL = LAB / "deploy" / ".runtime-control"
LEASE = CONTROL / "split-default-mutation.json"
OUTPUT = LAB / "show-output" / "split-default-mutation-20261009T1251Z"
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
RG = "rg-aks-agic-shared-udr"
BASE = ["network", "route-table", "route"]
attempted = []
mutations = 0
commands = 0
restore_deadline = None


def now():
    return dt.datetime.now(dt.timezone.utc)


def sanitize(value):
    value = re.sub(
        r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}",
        "<redacted-id>", value,
    )
    return re.sub(
        r'(?i)("(?:accessToken|refreshToken|password|clientSecret|secret|token)"\s*:\s*")[^"]*',
        r"\1<redacted-secret>", value,
    )


def write(name, value):
    (OUTPUT / name).write_text(
        sanitize(json.dumps(value, indent=2)), encoding="utf-8"
    )


def gate(restore=False):
    lease = json.loads(LEASE.read_text(encoding="utf-8-sig"))
    expiry = dt.datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
    if now() >= expiry:
        raise RuntimeError("Lease expired; no command permitted")
    if restore:
        if restore_deadline is not None and time.monotonic() >= restore_deadline:
            raise RuntimeError("Restore budget expired")
    else:
        if (CONTROL / "STOP").exists() or lease["state"] != "active":
            raise RuntimeError("STOP or inactive lease")
        start = dt.datetime.fromisoformat("2026-10-09T12:51:08+00:00")
        if now() >= start + (expiry - start) * 0.8 or mutations >= 4.8:
            raise RuntimeError("80 percent budget; restore only")
    if commands >= 20:
        raise RuntimeError("Reserved tool/command budget exhausted")
    return expiry


def run(name, args, mutation=False, restore=False):
    global mutations, commands
    expiry = gate(restore)
    limit = min(180, max(1, int((expiry - now()).total_seconds())))
    if restore and restore_deadline is not None:
        limit = min(limit, max(1, int(restore_deadline - time.monotonic())))
    args = [AZ, *args, "--only-show-errors", "-o", "json"]
    record = {
        "command": subprocess.list2cmdline(args),
        "startedAtUtc": now().isoformat(),
        "timeoutSeconds": limit,
        "timedOut": False,
    }
    commands += 1
    if mutation:
        mutations += 1
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    record["pid"] = process.pid
    try:
        stdout, stderr = process.communicate(timeout=limit)
    except subprocess.TimeoutExpired:
        record["timedOut"] = True
        killed = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True, timeout=15,
        )
        record["terminationExitCode"] = killed.returncode
        record["terminationStdout"] = killed.stdout.decode("utf-8", errors="replace")
        record["terminationStderr"] = killed.stderr.decode("utf-8", errors="replace")
        stdout, stderr = process.communicate(timeout=15)
    record.update(
        endedAtUtc=now().isoformat(),
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
        exitCode=process.returncode,
        childExited=process.poll() is not None,
    )
    write(name + ".json", record)
    print(name, record["endedAtUtc"], "exit", process.returncode,
          "timeout", record["timedOut"], flush=True)
    return record


def snapshot(name, restore=False):
    record = run(name, [
        "network", "route-table", "show", "-g", RG, "-n", "rt-shared",
    ], restore=restore)
    if record["exitCode"] != 0 or record["timedOut"]:
        raise RuntimeError("Route snapshot failed: " + name)
    return json.loads(record["stdout"])


def routes(table):
    return {
        r["name"]: (
            r["addressPrefix"], r["nextHopType"], r.get("nextHopIpAddress")
        ) for r in table["routes"]
    }


def associations(table):
    return sorted(s["id"].lower() for s in table.get("subnets", []))


def exact_split(name, table):
    return routes(table).get(name) == (
        "0.0.0.0/1" if name == "nva-lower" else "128.0.0.0/1",
        "VirtualAppliance", "10.20.1.4",
    )


OUTPUT.mkdir(exist_ok=False)
summary = {
    "taskId": "aks-agic-split-default-mutation-20261009",
    "startedAtUtc": now().isoformat(),
    "runtimeValidationPerformed": False,
    "verdict": "BLOCKED",
}
before = None
accepted = False
try:
    before = snapshot("01-before-route-table")
    initial = routes(before)
    if any(n in initial for n in ("nva-lower", "nva-upper")):
        raise RuntimeError("Named split route exists; refusing overwrite")
    if any(v[0] in ("0.0.0.0/1", "128.0.0.0/1") for v in initial.values()):
        raise RuntimeError("Conflicting split prefix exists; refusing mutation")
    if initial.get("default") != ("0.0.0.0/0", "Internet", None):
        raise RuntimeError("Internet default baseline mismatch")
    if not any(v == ("10.244.0.0/24", "VirtualAppliance", "10.21.1.4")
               for v in initial.values()):
        raise RuntimeError("Pod baseline mismatch")
    if len(associations(before)) != 2 or not all(
        any(s.endswith("/subnets/" + n) for s in associations(before))
        for n in ("snet-aks", "snet-appgw")
    ):
        raise RuntimeError("Shared subnet associations mismatch")
    for index, (name, prefix) in enumerate((
        ("nva-lower", "0.0.0.0/1"), ("nva-upper", "128.0.0.0/1")
    ), 2):
        gate()
        attempted.append(name)
        result = run(f"{index:02d}-create-{name}", [
            *BASE, "create", "-g", RG, "--route-table-name", "rt-shared",
            "-n", name, "--address-prefix", prefix,
            "--next-hop-type", "VirtualAppliance",
            "--next-hop-ip-address", "10.20.1.4",
        ], mutation=True)
        if result["exitCode"] or result["timedOut"]:
            summary["verdict"] = (
                "ADMISSION_REJECT"
                if not result["timedOut"] and
                "ApplicationGatewaySubnetUserDefinedRouteNotAllowed" in result["stderr"]
                else "BLOCKED"
            )
            raise RuntimeError("Admission failed: " + name)
        summary[name + "AcceptedAtUtc"] = result["endedAtUtc"]
    after = snapshot("04-after-admission-route-table")
    if not all(exact_split(n, after) for n in attempted):
        raise RuntimeError("Split route snapshot mismatch")
    remaining = {k: v for k, v in routes(after).items() if k not in attempted}
    if remaining != initial or associations(after) != associations(before):
        raise RuntimeError("Original routes or associations changed")
    accepted = True
    summary.update(
        verdict="ADMISSION_ACCEPTED",
        acceptedAtUtc=summary["nva-upperAcceptedAtUtc"],
        state="completed",
        readyForReadOnlyControlGates=True,
        originalRoutesPreserved=True,
        subnetAssociationsPreserved=True,
        resourceChanges=attempted.copy(),
    )
except Exception as error:
    summary["reason"] = str(error)
    summary["readyForReadOnlyControlGates"] = False
    if attempted:
        restore_deadline = time.monotonic() + 300
        try:
            partial = snapshot("05-partial-route-table", restore=True)
            for name in reversed(attempted):
                if name in routes(partial):
                    if not exact_split(name, partial):
                        raise RuntimeError("Unexpected attempted route state; refusing delete")
                    deletion = run("06-restore-delete-" + name, [
                        *BASE, "delete", "-g", RG,
                        "--route-table-name", "rt-shared", "-n", name,
                    ], mutation=True, restore=True)
                    if deletion["exitCode"] or deletion["timedOut"]:
                        raise RuntimeError("Restore deletion failed")
            restored = snapshot("07-restored-route-table", restore=True)
            proof = (
                routes(restored) == routes(before)
                and associations(restored) == associations(before)
            )
            summary["originalInternetBaselineRestored"] = proof
            summary["state"] = "rolled-back" if proof else "blocked"
            summary["resourceChanges"] = [] if proof else ["unverified"]
        except Exception as restore_error:
            summary["state"] = "blocked"
            summary["restoreError"] = str(restore_error)
    else:
        summary["state"] = "blocked"
        summary["resourceChanges"] = []
finally:
    summary.update(
        endedAtUtc=now().isoformat(),
        mutationCount=mutations,
        commandCount=commands,
        noChildCommandRemains=True,
    )
    lease = json.loads(LEASE.read_text(encoding="utf-8-sig"))
    lease.update(
        state=summary["state"],
        lastCheckpointUtc=summary["endedAtUtc"],
        mutationCount=mutations,
        verdict=summary["verdict"],
        evidenceDirectory=str(OUTPUT.relative_to(ROOT)),
        noChildCommandRemains=True,
    )
    LEASE.write_text(json.dumps(lease, indent=2) + "\n", encoding="utf-8")
    write("08-summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
