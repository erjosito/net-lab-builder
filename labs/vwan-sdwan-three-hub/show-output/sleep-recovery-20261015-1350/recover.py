"""One bounded exact-source recovery; no effective-route requests."""
import datetime as dt
import json
from pathlib import Path
import re
import sys
import time

OUT = Path(__file__).resolve().parent
DEPLOY = OUT.parent.parent / "deploy"
sys.path.insert(0, str(DEPLOY))
import control
import aspath_sweep as sweep
import vpn_sdwan_boundary as boundary

HASHES = {
    "jp": "89b67f35ed1750b258c61e3760f9c290da6f865f5580a56b7e6553625d45e006",
    "eu": "20fbaef367e78dd78b3e7d55e791d5c69dbae0a00fbd3c50ee0c2a740bdb4120",
    "us": "5634db09d84a79a68b94ffd9dab64aa9a4e63dc7cdb24379285b04a32328c4cb",
    "cn": "10e5591a16159a4a6e17350cb23f437623372f2ffd635ef20736f133c4738346",
}
TASK = "sleep-recovery-20261015-1350"
control.LEASE = control.RUNTIME / (TASK + "-JapanRecovery.json")
sweep.OUT = OUT
sweep.CURRENT = OUT
sweep.SUB = control.account_id()
before = None
after = {}
errors = []
restore_status = "not attempted"
verdict = "BLOCKED"
lease_created = False


def persist(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


try:
    if control.LEASE.exists() or (OUT / "lease-issued.json").exists():
        raise RuntimeError("Fresh immutable recovery lease required; never replay")
    now = dt.datetime.now(dt.timezone.utc)
    lease = {
        "taskId": TASK,
        "ownerRole": "JapanRecovery",
        "objective": "Verify actual Japan source, restore exact protected original only if different, and close all-four-router source health",
        "allowedMutations": ["Restore exact protected original Japan BIRD file only if current hash or metadata differs"],
        "forbiddenWork": ["effective-route APIs", "new experiments", "documentation", "publication", "IPsec/WireGuard/keys/NSGs/underlay changes"],
        "rollback": "boundary.invoke('jp', restore=True) with original preflight proof and protected boundary backup",
        "startedAtUtc": now.isoformat(),
        "expiresAtUtc": (now + dt.timedelta(minutes=30)).isoformat(),
        "maxToolCalls": 30,
        "maxMutations": 2,
        "commandTimeoutSeconds": 180,
        "restoreTimeoutMinutes": 15,
        "lastCheckpointUtc": now.isoformat(),
        "state": "active",
        "toolCallsUsed": 0,
        "mutationsUsed": 0,
    }
    with control.LEASE.open("x", encoding="utf-8") as handle:
        json.dump(lease, handle, indent=2)
    lease_created = True
    with (OUT / "lease-issued.json").open("x", encoding="utf-8") as handle:
        json.dump(lease, handle, indent=2)
    print(f"LIVE {TASK} | source recovery | 0/30min | calls 0/30 | mutations 0/2 | state running | next actual Japan source", flush=True)
    control.guard(True)
    baseline_path = OUT.parent / "unsecured-cn-eligibility-20261015" / "preflight" / "source-jp-proof.json"
    original = json.loads(baseline_path.read_text(encoding="utf-8-sig"))
    assert original["sha256"] == HASHES["jp"], "Original preflight hash differs"
    assert original["stat"] == dict(uid=113, gid=122, mode=384, mtimeNs=1792000606196722098)
    boundary.BASE["jp"] = original
    persist(OUT / "original-jp-proof.json", original)
    path = control.RUNTIME / (TASK + "-read-jp.sh")
    script = boundary.script("jp").replace(
        "result=dict(site=",
        "result=dict(protectedBackup=dict(sha256=digest(b),stat=metadata(b)),site=",
    )
    path.write_text(script, encoding="utf-8", newline="\n")
    value = sweep.az(
        ["vm", "run-command", "invoke", "-g", control.RG, "-n", "router-jp",
         "--command-id", "RunShellScript", "--scripts", "@" + str(path)],
        TASK + "-actual-jp",
    )
    messages = "\n".join(x.get("message", "") for x in value.get("value", []))
    matches = re.findall(r"^BOUNDARY_COMPLETE (\{.*\})$", messages, re.M)
    assert len(matches) == 1, "Actual Japan guest completion absent"
    before = json.loads(matches[0])
    persist(OUT / "actual-jp-proof.json", before)
    assert before["protectedBackup"] == dict(sha256=original["sha256"], stat=original["stat"]), "Protected original proof differs"
    actual_prefixes = {peer: sorted(proof["routes"]) for peer, proof in before["exports"].items()}
    withdrawal = (len(actual_prefixes) == 2 and all(
        set(prefixes) == set(sweep.PREFIXES) - {"10.140.0.0/24"}
        for prefixes in actual_prefixes.values()
    ))
    differs = any(before[key] != original[key] for key in ("sha256", "stat"))
    print(f"DECISIVE Japan actual sha256={before['sha256']} differsFromOriginal={differs} cnWithdrawnOnBothPeers={withdrawal}", flush=True)
    persist(OUT / "actual-state.json", dict(
        timestampUtc=sweep.utc(), differsFromOriginal=differs,
        cnWithdrawnOnBothPeers=withdrawal, actualPrefixes=actual_prefixes,
    ))
    sweep.RESTORING = True
    sweep.RESTORE_DEADLINE = time.monotonic() + 15 * 60
    if differs:
        control.guard(False)
        sweep.CURRENT = OUT / "restore"
        restore_status = "attempted; not yet verified"
        restored = boundary.invoke("jp", TASK + "-restore", restore=True)
        assert all(restored[key] == original[key] for key in ("sha256", "stat"))
        assert restored["configureOutput"] and re.search(r"^Reconfigured\s*$", restored["configureOutput"], re.M)
        restore_status = "exact original restored and Reconfigured"
        print(f"LIVE {TASK} | exact original restored | calls 2/30 | mutations 1/2 | state restoring | next four-router source closure", flush=True)
    else:
        restore_status = "not necessary; current hash and metadata already original"
    sweep.CURRENT = OUT / "closure"
    after = boundary.invoke_all(TASK + "-closure")
    assert len(after) == 4
    for site, proof in after.items():
        assert proof["sha256"] == HASHES[site], f"{site}: original hash differs"
    assert after["jp"]["stat"] == original["stat"], "Japan exact metadata differs"
    verdict = "PASS"
except Exception as exc:
    errors.append(str(exc))
    print("RECOVERY BLOCKED: " + str(exc), flush=True)
finally:
    if lease_created:
        # Local terminal persistence is unconditional, including after lease expiry.
        final_lease = json.loads(control.LEASE.read_text(encoding="utf-8-sig"))
        child = json.loads((control.RUNTIME / "child-process.json").read_text(encoding="utf-8-sig"))
        no_active_child = child.get("state") == "terminated"
        if not no_active_child:
            verdict = "BLOCKED"
            errors.append("Child termination unverified")
        summary = dict(
            timestampUtc=sweep.utc(), verdict=verdict, objective=final_lease["objective"],
            actualJapanState=before, restoreStatus=restore_status,
            allRouterSourceHealth=after, errors=errors,
            callsUsed=final_lease["toolCallsUsed"], mutationsUsed=final_lease["mutationsUsed"],
            children=[] if no_active_child else child,
            effectiveRouteRequests=0, evidence=str(OUT),
        )
        persist(OUT / "recovery-verdict.json", summary)
        final_lease.update(
            state="completed" if verdict == "PASS" else "blocked",
            verdict=verdict, completedAtUtc=sweep.utc(),
            restoreStatus=restore_status, evidence=str(OUT),
            children=[] if no_active_child else child, errors=errors,
        )
        persist(control.LEASE, final_lease)
        print(f"FINAL {verdict} | restore={restore_status} | calls={summary['callsUsed']}/30 | mutations={summary['mutationsUsed']}/2 | childrenTerminated={no_active_child} | evidence={OUT}", flush=True)
    else:
        persist(OUT / "recovery-verdict.json", dict(timestampUtc=sweep.utc(), verdict="BLOCKED", errors=errors, liveCalls=0))
sys.exit(0 if verdict == "PASS" else 1)
