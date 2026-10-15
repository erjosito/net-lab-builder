"""Bounded post-restart readback and exact protected-backup recovery only."""
import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import aspath_sweep as sweep
import control
import effective_routes
import guest
import vpn_sdwan_boundary as boundary


def backup_paths(site):
    paths = [f"/var/lib/threehub/vpn-sdwan-boundary-{site}-baseline.conf"]
    if site == "jp":
        paths.append("/var/lib/threehub/aspath-jp-baseline.conf")
    return paths


def read_script(site):
    # Runtime and protected-backup checks precede the actual router proofs.
    preflight = f"""#!/bin/bash
set -euo pipefail
for cmd in python3 bird birdc sha256sum stat; do command -v "$cmd" >/dev/null; done
python3 - <<'PY'
import hashlib,json
from pathlib import Path
backups={{}}
for name in {backup_paths(site)!r}:
 p=Path(name)
 if p.exists():
  s=p.stat()
  backups[name]=dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
   stat=dict(uid=s.st_uid,gid=s.st_gid,mode=s.st_mode&0o777,mtimeNs=s.st_mtime_ns))
print('BACKUPS_COMPLETE '+json.dumps(backups,separators=(',',':')))
PY
"""
    return preflight + boundary.script(site)


def parse_marker(messages, marker):
    matches = re.findall(r"^" + marker + r" (\{.*\})$", messages, re.M)
    if len(matches) != 1:
        raise RuntimeError(f"Missing unique {marker} guest completion")
    return json.loads(matches[0])


def baseline_errors(site, actual, original):
    errors = []
    for key in ("sha256", "stat", "protocols", "ikeEstablished"):
        if actual[key] != original[key]:
            errors.append(f"{site}: {key} differs from recorded original")
    expected_count = 3 if site == "cn" else 5
    if (len(actual["protocols"]) != expected_count or
            set(actual["protocols"].values()) != {"Established"}):
        errors.append(f"{site}: BGP is not fully Established")
    if site in ("eu", "jp"):
        expected = {p: ([] if p == guest.DC[site] else [guest.ASNS[s]])
                    for s, p in guest.DC.items()}
        exports = actual["exports"]
        if set(exports) != {"azure_0", "azure_1"}:
            errors.append(f"{site}: actual two-peer exports are unavailable")
        if any(set(v["routes"]) != set(expected) for v in exports.values()):
            errors.append(f"{site}: actual two-peer exports have missing or unexpected routes")
        if any(path != expected[prefix] for v in exports.values()
               for prefix, path in v["routes"].items() if prefix in expected):
            errors.append(f"{site}: actual two-peer exports are not zero prepend")
    return errors


def configuration_differs(actual, original):
    """Route/session loss is not evidence that the protected file changed."""
    return any(actual[key] != original[key] for key in ("sha256", "stat"))


def restore_script(site, backup, original):
    if backup not in backup_paths(site):
        raise RuntimeError("Explicit protected baseline backup required")
    boundary.BASE[site] = original
    text = boundary.script(site, restore=True)
    return text.replace(repr(backup_paths(site)[0]), repr(backup))


class Recovery:
    def __init__(self, out, read_only_closure=False):
        self.out = out
        self.sub = control.account_id()
        self.restore_deadline = None
        self.read_only_closure = read_only_closure

    def save(self, name, value):
        text = json.dumps(value, indent=2)
        (self.out / name).write_text(text.replace(self.sub, "<SUBSCRIPTION_ID>") + "\n",
                                     encoding="utf-8")

    def checkpoint(self, phase, state, next_action):
        lease = control.guard(False)
        start = dt.datetime.fromisoformat(lease["startedAtUtc"])
        end = dt.datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
        now = dt.datetime.now(dt.timezone.utc)
        print(f"LIVE {lease['taskId']} | {phase} | "
              f"{(now-start).total_seconds()/60:.1f}/{(end-start).total_seconds()/60:.0f}min | "
              f"calls {lease.get('toolCallsUsed', 0)}/{lease['maxToolCalls']} | "
              f"mutations {lease.get('mutationsUsed', 0)}/{lease['maxMutations']} | "
              f"state {state} | next {next_action}", flush=True)

    def az(self, args, label, mutation=False, absent_ok=False):
        if self.read_only_closure and mutation:
            raise RuntimeError("Read-only closure cannot mutate")
        lease = control.guard(not self.read_only_closure and self.restore_deadline is None)
        if lease.get("toolCallsUsed", 0) >= lease["maxToolCalls"]:
            raise RuntimeError("Absolute call budget exhausted")
        expiry = dt.datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
        timeout = min(300 if args[:2] == ["vm", "run-command"] or args[0] == "network" else 120,
                      lease["commandTimeoutSeconds"],
                      (expiry - dt.datetime.now(dt.timezone.utc)).total_seconds())
        if self.restore_deadline is not None:
            timeout = min(timeout, self.restore_deadline - time.monotonic())
        if timeout <= 0:
            raise RuntimeError("Recovery deadline exhausted")
        lease["toolCallsUsed"] = lease.get("toolCallsUsed", 0) + 1
        lease["mutationsUsed"] = lease.get("mutationsUsed", 0) + int(mutation)
        lease["lastCheckpointUtc"] = sweep.utc()
        control.save(control.LEASE, lease)
        began = sweep.utc()
        process = subprocess.Popen([shutil.which("az"), *args, "--subscription", self.sub,
                                    "--only-show-errors", "-o", "json"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        control.save(control.RUNTIME / "child-process.json",
                     dict(pid=process.pid, label=label, state="running"))
        deadline = time.monotonic() + timeout
        out, err = b"", b""
        timed_out = False
        try:
            while True:
                control.guard(False)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(args, timeout)
                try:
                    out, err = process.communicate(timeout=min(10, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
        except (subprocess.TimeoutExpired, RuntimeError):
            timed_out = True
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, timeout=30)
            out, err = process.communicate(timeout=30)
        finally:
            control.save(control.RUNTIME / "child-process.json",
                         dict(pid=process.pid, label=label, state="terminated"))
        stdout, stderr = out.decode(errors="replace"), err.decode(errors="replace")
        absent = (absent_ok and not timed_out and process.returncode != 0 and
                  re.search(r"\b404\b|\(ResourceNotFound\)", stderr) is not None)
        self.save(label + ".json", dict(timestampUtc=began, finishedUtc=sweep.utc(),
                  command=args, exitCode=process.returncode, timedOut=timed_out,
                  stdout=stdout, stderr=stderr, expectedAbsent=absent,
                  stdoutSha256=hashlib.sha256(out).hexdigest()))
        control.guard(False)
        print(f"{label}: exit={process.returncode} expectedAbsent={absent}", flush=True)
        if timed_out or (process.returncode and not absent):
            raise RuntimeError(f"{label}: {'timeout' if timed_out else stderr[-600:]}")
        if absent:
            return {"value": [], "expected404": True}
        return json.loads(stdout or "null")

    def router(self, site, label, backup=None, original=None):
        path = control.RUNTIME / f"restart-{site}-{label}.sh"
        path.write_text(restore_script(site, backup, original) if backup else read_script(site),
                        encoding="utf-8", newline="\n")
        value = self.az(["vm", "run-command", "invoke", "-g", control.RG,
                         "-n", "router-" + site, "--command-id", "RunShellScript",
                         "--scripts", "@" + str(path)], f"{site}-{label}", mutation=bool(backup))
        messages = "\n".join(v.get("message", "") for v in value.get("value", []))
        actual = parse_marker(messages, "BOUNDARY_COMPLETE")
        # The reused script's count argument is not an observation.
        actual.pop("additionalPrepends", None)
        if not backup:
            actual["protectedBackups"] = parse_marker(messages, "BACKUPS_COMPLETE")
        self.save(f"{site}-{label}-proof.json", actual)
        return actual

    def hubs(self):
        result = {}
        for site in sweep.SITES:
            url = (f"https://management.azure.com/subscriptions/{self.sub}"
                   f"/resourceGroups/{control.RG}/providers/Microsoft.Network/virtualHubs/hub-{site}")
            hub = self.az(["rest", "--method", "get", "--url",
                           url + "?api-version=2024-05-01"], f"hub-{site}")
            ri = self.az(["rest", "--method", "get", "--url",
                          url + "/routingIntent?api-version=2024-05-01"],
                         f"routing-intent-{site}", absent_ok=True)
            result[site] = dict(hub=hub, routingIntent=ri, timestampUtc=sweep.utc())
        self.save("hub-metadata.json", result)
        return result

    def snapshot(self, number):
        began = sweep.utc()
        rows = []
        for site in sweep.SITES:
            value = effective_routes.collect(self.az, self.sub, control.RG, site,
                                              f"connection-{site}-snapshot{number}")
            rows.extend(sweep.normalize(value, site))
        self.save(f"winners-snapshot{number}.json",
                  dict(timestampUtc=began, finishedUtc=sweep.utc(), rows=rows))
        return rows


def read_only_closure(args):
    """Record independent visibility when a stopped VM prevents guest recovery."""
    lease = control.guard(False)
    if lease["ownerRole"] != "Trinity" or lease["state"] != "blocked":
        raise RuntimeError("Read-only closure requires the same blocked Trinity lease")
    recovery = Recovery(args.out, read_only_closure=True)
    summary = json.loads((args.out / "recovery-verdict.json").read_text())
    states, actual, rows, hubs = {}, {}, [], {}
    recovery.checkpoint("blocked closure", "blocked", "read-only VM power states and Azure visibility")
    for site in (*sweep.SITES, "cn"):
        try:
            state = recovery.az(["vm", "get-instance-view", "-g", control.RG,
                                 "-n", "router-" + site], f"{site}-instance-view")
            statuses = state.get("instanceView", {}).get("statuses", [])
            states[site] = dict(timestampUtc=sweep.utc(), statuses=statuses)
            running = any(s.get("code") == "PowerState/running" for s in statuses)
            if running:
                actual[site] = recovery.router(site, "closure")
            else:
                summary["errors"].append(f"{site}: guest unavailable; power state is not running")
        except Exception as exc:
            summary["errors"].append(str(exc))
    recovery.save("vm-power-states.json", states)
    for site in sweep.SITES:
        url = (f"https://management.azure.com/subscriptions/{recovery.sub}"
               f"/resourceGroups/{control.RG}/providers/Microsoft.Network/virtualHubs/hub-{site}")
        try:
            hub = recovery.az(["rest", "--method", "get", "--url",
                               url + "?api-version=2024-05-01"], f"closure-hub-{site}")
            ri = recovery.az(["rest", "--method", "get", "--url",
                              url + "/routingIntent?api-version=2024-05-01"],
                             f"closure-routing-intent-{site}", absent_ok=True)
            hubs[site] = dict(timestampUtc=sweep.utc(), hub=hub, routingIntent=ri)
        except Exception as exc:
            summary["errors"].append(str(exc))
        try:
            value = effective_routes.collect(recovery.az, recovery.sub, control.RG, site,
                                              f"closure-connection-{site}")
            rows.extend(sweep.normalize(value, site))
        except Exception as exc:
            summary["errors"].append(str(exc))
    lease = control.guard(False)
    summary.update(timestampUtc=sweep.utc(), verdict="BLOCKED", baselineVerified=False,
                   restoreState="blocked-guest-unavailable", vmPowerStates=states,
                   closureActual=actual, currentWinnerRows=rows, actualHubMetadata=hubs,
                   snapshotCount=1, pairedStable=None, snapshotSpacingMinimumSeconds=None,
                   callsUsed=lease["toolCallsUsed"], mutationsUsed=lease["mutationsUsed"],
                   children=[], baselineClearedForNextExperiment=False)
    recovery.save("hub-metadata.json", hubs)
    recovery.save("winners-snapshot1.json", dict(timestampUtc=sweep.utc(), rows=rows))
    recovery.save("recovery-verdict.json", summary)
    lease.update(state="blocked", verdict="BLOCKED", completedAtUtc=sweep.utc(), children=[])
    control.save(control.LEASE, lease)
    print(f"FINAL BLOCKED guest baseline unavailable rows={len(rows)} "
          f"calls={lease['toolCallsUsed']} mutations={lease['mutationsUsed']} evidence={args.out}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lease", type=Path, required=True)
    parser.add_argument("--original-verdict", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--read-only-closure", action="store_true")
    args = parser.parse_args()
    control.LEASE = args.lease.resolve()
    if args.read_only_closure:
        read_only_closure(args)
        return
    lease = control.guard(False)
    if (lease["ownerRole"] != "Trinity" or lease["state"] != "active" or
            lease.get("toolCallsUsed", 0) or lease.get("mutationsUsed", 0)):
        raise RuntimeError("Existing fresh active Trinity recovery lease required")
    lease.setdefault("startedAtUtc", sweep.utc())
    lease.update(toolCallsUsed=0, mutationsUsed=0)
    control.save(control.LEASE, lease)
    args.out.mkdir(parents=True, exist_ok=False)
    recovery = Recovery(args.out)
    originals = json.loads(args.original_verdict.read_text(encoding="utf-8-sig"))["protocolProofBefore"]
    before, after, errors, hubs, snapshots = {}, {}, [], {}, []
    guest_ok = False
    recovery.checkpoint("start", "running", "four actual read-only guest proofs")
    try:
        for site in (*sweep.SITES, "cn"):
            before[site] = recovery.router(site, "before")
        recovery.save("initial-actual.json", before)
        for site, actual in before.items():
            differences = baseline_errors(site, actual, originals[site])
            if differences:
                if site not in ("eu", "jp"):
                    raise RuntimeError("; ".join(differences))
                if not configuration_differs(actual, originals[site]):
                    raise RuntimeError("; ".join(differences))
                candidates = actual["protectedBackups"]
                backup = next((p for p in backup_paths(site) if p in candidates and
                               candidates[p]["sha256"] == originals[site]["sha256"] and
                               candidates[p]["stat"] == originals[site]["stat"]), None)
                if backup is None:
                    raise RuntimeError(f"{site}: no exact original protected backup")
                if recovery.restore_deadline is None:
                    recovery.restore_deadline = time.monotonic() + 900
                recovery.checkpoint("exact restore", "restoring", f"restore protected {site} baseline")
                recovery.router(site, "restore", backup, originals[site])
                after[site] = recovery.router(site, "after")
            else:
                after[site] = actual
        errors.extend(e for s, a in after.items() for e in baseline_errors(s, a, originals[s]))
        guest_ok = len(after) == 4 and not errors
        recovery.save("guest-baseline-verdict.json",
                      dict(timestampUtc=sweep.utc(), baselineVerified=guest_ok,
                           mutationsUsed=control.guard(False)["mutationsUsed"], actual=after, errors=errors))
        recovery.checkpoint("guest baseline", "verdict" if guest_ok else "blocked",
                            "actual full hub GETs and spoke-connection winner snapshot")
        if not guest_ok:
            raise RuntimeError("Actual guests do not match original zero-prepend baseline")
        # Guest recovery deadline is independent of later read-only API visibility.
        recovery.restore_deadline = None
        hubs = recovery.hubs()
        for site, value in hubs.items():
            if (value["hub"].get("properties", {}).get("hubRoutingPreference") != "ASPath" or
                    value["routingIntent"].get("value") != []):
                errors.append(f"{site}: actual ASPath/no-RI baseline differs")
        snapshots.append(recovery.snapshot(1))
        completed = time.monotonic()
        # Reserve the worst-case three five-minute connection collectors plus spacing.
        lease = control.guard(False)
        expiry = dt.datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
        start = dt.datetime.fromisoformat(lease["startedAtUtc"])
        new_work_limit = start + (expiry - start) * 0.8
        if (new_work_limit - dt.datetime.now(dt.timezone.utc)).total_seconds() >= 1020:
            while time.monotonic() - completed < 120:
                control.guard(False)
                time.sleep(min(10, 120 - (time.monotonic() - completed)))
            snapshots.append(recovery.snapshot(2))
        if not all(sweep.complete_rows(rows) for rows in snapshots):
            errors.append("Current twelve-winner matrix incomplete")
        if len(snapshots) == 2 and snapshots[0] != snapshots[1]:
            errors.append("Paired current winner matrices differ")
    except Exception as exc:
        errors.append(str(exc))
    finally:
        lease = json.loads(control.LEASE.read_text(encoding="utf-8-sig"))
        passed = guest_ok and len(hubs) == 3 and bool(snapshots) and not errors
        verdict = "PASS" if passed else "INCONCLUSIVE" if guest_ok else "BLOCKED"
        summary = dict(timestampUtc=sweep.utc(), verdict=verdict,
                       baselineVerified=guest_ok, restoreState="verified" if guest_ok else "blocked",
                       originalEvidence=str(args.original_verdict), initialActual=before,
                       finalActual=after, currentWinnerRows=snapshots[-1] if snapshots else [],
                       snapshotCount=len(snapshots),
                       pairedStable=(snapshots[0] == snapshots[1]) if len(snapshots) == 2 else None,
                       snapshotSpacingMinimumSeconds=120 if len(snapshots) == 2 else None,
                       actualHubMetadata=hubs, errors=errors,
                       callsUsed=lease["toolCallsUsed"], mutationsUsed=lease["mutationsUsed"],
                       azureFacingBGPSessions=6 if guest_ok else None,
                       uniqueWireGuardAdjacencies=6 if guest_ok else None,
                       defaultRouteTablesQueried=False, newScenarios=0, children=[],
                       noDataPlaneClaim=True)
        recovery.save("recovery-verdict.json", summary)
        lease.update(state="completed" if passed else "blocked", verdict=verdict,
                     completedAtUtc=sweep.utc(), children=[], evidence=str(args.out))
        control.save(control.LEASE, lease)
        print(f"FINAL {verdict} baselineVerified={guest_ok} "
              f"rows={len(summary['currentWinnerRows'])} "
              f"mutations={lease['mutationsUsed']} errors={errors} evidence={args.out}", flush=True)


if __name__ == "__main__":
    main()
