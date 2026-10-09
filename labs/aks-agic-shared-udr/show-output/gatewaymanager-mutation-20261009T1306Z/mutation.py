"""Create-only GatewayManager admission under the exact Tank lease."""
import datetime as dt
import json
import pathlib
import re
import subprocess

OUT = pathlib.Path(__file__).resolve().parent
LAB = OUT.parents[1]
CONTROL = LAB / "deploy" / ".runtime-control"
LEASE = CONTROL / "gatewaymanager-mutation.json"
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
RG = "rg-aks-agic-shared-udr"
processes = []
commands = 0
mutations = 0


def now():
    return dt.datetime.now(dt.timezone.utc)


def redact(text):
    text = re.sub(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}",
                  "<redacted-id>", text)
    return re.sub(
        r'(?i)("(?:accessToken|refreshToken|password|clientSecret|secret|token)"\s*:\s*")[^"]*',
        r"\1<redacted-secret>", text)


def save(name, value):
    (OUT / name).write_text(redact(json.dumps(value, indent=2)) + "\n",
                            encoding="utf-8")


def gate():
    lease = json.loads(LEASE.read_text(encoding="utf-8-sig"))
    expiry = dt.datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
    start = dt.datetime.fromisoformat("2026-10-09T13:06:13+00:00")
    if (CONTROL / "STOP").exists() or lease["state"] != "active":
        raise RuntimeError("STOP or inactive mutation lease")
    if lease["ownerRole"] != "Tank" or lease["taskId"] != "aks-agic-gatewaymanager-mutation-20261009":
        raise RuntimeError("Lease ownership mismatch")
    if now() >= start + (expiry - start) * 0.8:
        raise RuntimeError("80 percent elapsed budget; no new command")
    if commands >= 4 or mutations >= 1:
        # Post-mutation route read is the only permitted remaining work.
        if mutations != 1 or commands != 2:
            raise RuntimeError("Command or mutation budget reached")
    return expiry


def run(name, args, mutation=False):
    global commands, mutations
    expiry = gate()
    if mutation:
        niobe = json.loads((CONTROL / "split-default-validation.json").read_text(
            encoding="utf-8-sig"))
        if not (niobe["state"] == "completed"
                and niobe["verdict"] == "PASS_CONTROL_GATES"
                and niobe["noChildCommandRemains"] is True):
            raise RuntimeError("Niobe control gates or idle confirmation missing")
        if mutations:
            raise RuntimeError("Refusing second mutation")
        gate()
    argv = [AZ, *args, "--only-show-errors", "--output", "json"]
    limit = min(180, int((expiry - now()).total_seconds()) - 1)
    if limit < 1:
        raise RuntimeError("No bounded command time remains")
    record = dict(command=subprocess.list2cmdline(argv),
                  startedAtUtc=now().isoformat(), timeoutSeconds=limit,
                  timedOut=False)
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    processes.append(process)
    commands += 1
    mutations += int(mutation)
    record["pid"] = process.pid
    try:
        stdout, stderr = process.communicate(timeout=limit)
    except subprocess.TimeoutExpired:
        record["timedOut"] = True
        killed = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True, timeout=15)
        record["terminationExitCode"] = killed.returncode
        record["terminationStdout"] = killed.stdout.decode(errors="replace")
        record["terminationStderr"] = killed.stderr.decode(errors="replace")
        stdout, stderr = process.communicate(timeout=15)
    record.update(endedAtUtc=now().isoformat(), exitCode=process.returncode,
                  stdout=stdout.decode("utf-8", errors="replace"),
                  stderr=stderr.decode("utf-8", errors="replace"),
                  childExited=process.poll() is not None)
    save(name + ".json", record)
    print(name, record["endedAtUtc"], "exit", record["exitCode"],
          "timeout", record["timedOut"], flush=True)
    if record["timedOut"]:
        raise RuntimeError("External process timed out; no follow-up work")
    return record


def snapshot(name):
    result = run(name, ["network", "route-table", "show", "-g", RG, "-n", "rt-shared"])
    if result["exitCode"]:
        raise RuntimeError("Route snapshot failed")
    return json.loads(result["stdout"])


def routes(table):
    return {r["name"]: (r["addressPrefix"], r["nextHopType"],
                        r.get("nextHopIpAddress")) for r in table["routes"]}


def associations(table):
    return sorted(s["id"].lower() for s in table.get("subnets", []))


summary = dict(taskId="aks-agic-gatewaymanager-mutation-20261009",
               startedAtUtc=now().isoformat(), verdict="BLOCKED",
               runtimeValidationPerformed=False, resourceChanges=[],
               treatmentStateLeftForNextValidation=False)
try:
    before = snapshot("01-before-route-table")
    baseline = routes(before)
    if "gm" in baseline or any(v[0].lower() == "gatewaymanager"
                               for v in baseline.values()):
        raise RuntimeError("gm or GatewayManager prefix exists unexpectedly; refusing overwrite")
    expected = {
        "default": ("0.0.0.0/0", "Internet", None),
        "nva-lower": ("0.0.0.0/1", "VirtualAppliance", "10.20.1.4"),
        "nva-upper": ("128.0.0.0/1", "VirtualAppliance", "10.20.1.4"),
    }
    if any(baseline.get(k) != v for k, v in expected.items()):
        raise RuntimeError("Split-default baseline mismatch")
    if ("10.244.0.0/24", "VirtualAppliance", "10.21.1.4") not in baseline.values():
        raise RuntimeError("Pod route baseline mismatch")
    if len(associations(before)) != 2 or not all(
            any(s.endswith("/subnets/" + n) for s in associations(before))
            for n in ("snet-aks", "snet-appgw")):
        raise RuntimeError("Subnet association baseline mismatch")
    action = run("02-create-gm", [
        "network", "route-table", "route", "create", "-g", RG,
        "--route-table-name", "rt-shared", "-n", "gm",
        "--address-prefix", "GatewayManager", "--next-hop-type", "Internet",
    ], mutation=True)
    after = snapshot("03-after-route-table")
    current = routes(after)
    preserved = ({k: v for k, v in current.items() if k != "gm"} == baseline
                 and associations(after) == associations(before)
                 and after.get("disableBgpRoutePropagation") == before.get("disableBgpRoutePropagation")
                 and after.get("tags") == before.get("tags"))
    summary.update(originalRoutesPreserved=preserved,
                   subnetAssociationsPreserved=associations(after) == associations(before))
    if action["exitCode"] == 0:
        if not preserved or current.get("gm") != ("GatewayManager", "Internet", None):
            raise RuntimeError("Admission returned success but post-route preservation failed")
        summary.update(verdict="ADMISSION_ACCEPTED", acceptedAtUtc=action["endedAtUtc"],
                       resourceChanges=["gm: GatewayManager -> Internet"],
                       treatmentStateLeftForNextValidation=True,
                       restoreState="Not performed; exact accepted treatment intentionally retained")
    else:
        unchanged = current == baseline and preserved
        summary.update(rejectionDetail=action["stderr"], unchangedBaselineVerified=unchanged)
        if not unchanged:
            raise RuntimeError("Admission command failed but baseline is not unchanged")
        summary.update(verdict="ADMISSION_REJECT",
                       restoreState="No restore required; unchanged split-default baseline verified")
except Exception as error:
    summary["reason"] = str(error)
finally:
    no_children = all(p.poll() is not None for p in processes)
    summary.update(endedAtUtc=now().isoformat(), mutationCount=mutations,
                   commandCount=commands, noChildCommandRemains=no_children,
                   evidenceDirectory=str(OUT.relative_to(LAB.parents[1])))
    if not no_children:
        summary["verdict"] = "BLOCKED"
    lease = json.loads(LEASE.read_text(encoding="utf-8-sig"))
    lease.update(state="completed" if summary["verdict"] in
                 ("ADMISSION_ACCEPTED", "ADMISSION_REJECT") else "blocked",
                 closedAtUtc=summary["endedAtUtc"], lastCheckpointUtc=summary["endedAtUtc"],
                 mutationCount=mutations, commandCount=commands,
                 toolCallsUsed=15, verdict=summary["verdict"],
                 noChildCommandRemains=no_children,
                 evidenceDirectory=summary["evidenceDirectory"])
    LEASE.write_text(json.dumps(lease, indent=2) + "\n", encoding="utf-8")
    save("04-admission-verdict.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
