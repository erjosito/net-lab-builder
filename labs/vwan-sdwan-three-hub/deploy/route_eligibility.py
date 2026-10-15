"""Withdraw one Japan DC advertisement to test remote path eligibility, then restore."""
import argparse
import time

import aspath_sweep as sweep
import control
import vpn_sdwan_boundary as boundary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lease", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--secured", action="store_true")
    args = parser.parse_args()
    control.LEASE = control.RUNTIME / args.lease
    lease = control.guard(True)
    if lease.get("toolCallsUsed", 0) or lease.get("mutationsUsed", 0):
        raise RuntimeError("Fresh lease required")
    sweep.SUB = control.account_id()
    sweep.OUT = control.ROOT.parent / "show-output" / args.out
    if sweep.OUT.exists():
        raise RuntimeError("Fresh evidence required")
    sweep.CURRENT = sweep.OUT / "preflight"
    firewall_ids = ({
        site: (f"/subscriptions/{sweep.SUB}/resourceGroups/{control.RG}"
               f"/providers/Microsoft.Network/azureFirewalls/fw-{site}")
        for site in sweep.SITES
    } if args.secured else None)
    before, after, states, errors = {}, {}, {}, []
    dirty = False
    try:
        before = boundary.invoke_all("baseline")
        boundary.BASE.update(before)
        states["baseline"] = sweep.capture("baseline", 0, firewall_ids=firewall_ids, parallel=True)
        if states["baseline"]["verdict"] != "PASS":
            raise RuntimeError("Incomplete baseline")
        sweep.reserve_restore(control.guard(True))
        sweep.CURRENT = sweep.OUT / "withdraw-cn-jp"
        dirty = True
        boundary.invoke("jp", "withdraw-cn", count=0, withdraw_cn=True)
        states["withdrawal"] = sweep.capture("withdraw-cn-jp", 0, withdraw_cn=True,
                                            firewall_ids=firewall_ids, parallel=True)
        if states["withdrawal"]["verdict"] != "PASS":
            raise RuntimeError("Unstable withdrawal evidence")
    except Exception as exc:
        errors.append(str(exc))
        print(f"ELIGIBILITY ERROR {exc}", flush=True)
    finally:
        sweep.RESTORING = True
        sweep.RESTORE_DEADLINE = time.monotonic() + 900
        try:
            if dirty:
                sweep.CURRENT = sweep.OUT / "restore"
                proof = boundary.invoke("jp", "restore", restore=True)
                if any(proof[k] != before["jp"][k] for k in ("sha256", "stat", "exports")):
                    raise RuntimeError("Japan exact file/export restore differs")
                dirty = False
                states["restore"] = sweep.capture("restore", 0, firewall_ids=firewall_ids, parallel=True)
                if states["restore"] != states["baseline"]:
                    raise RuntimeError("Restored effective route matrix differs")
            sweep.CURRENT = sweep.OUT / "closure"
            after = boundary.invoke_all("closure")
            for site in (*sweep.SITES, "cn"):
                if any(after[site][k] != before.get(site, {}).get(k)
                       for k in ("sha256", "stat", "exports", "protocols", "ikeEstablished")):
                    raise RuntimeError(f"{site}: closure differs")
        except Exception as exc:
            errors.append("RESTORE: " + str(exc))
        rows = states.get("withdrawal", {}).get("rows", [])
        candidate = [r for r in rows if r["observer"] == "jp" and r["prefix"] == "10.140.0.0/24"]
        restored = not dirty and len(after) == 4 and not any(e.startswith("RESTORE:") for e in errors)
        complete = restored and len(states) == 3 and not errors
        lease = control.guard(False)
        verdict = "PASS" if complete else "INCONCLUSIVE" if restored else "BLOCKED"
        sweep.CURRENT = sweep.OUT
        sweep.save("eligibility-verdict.json", dict(
            timestampUtc=sweep.utc(), verdict=verdict, restored=restored,
            japanRemoteCNRoute=candidate, remoteCNEligible=bool(candidate) if complete else None,
            states=states, errors=errors, sourceBefore=before, sourceAfter=after,
            callsUsed=lease["toolCallsUsed"], mutationsUsed=lease.get("mutationsUsed", 0),
            children=[], noDataPlaneClaim=True))
        lease.update(state="completed" if complete else "rolled-back" if restored else "blocked",
                     verdict=verdict, completedAtUtc=sweep.utc(), children=[], evidence=str(sweep.OUT))
        control.save(control.LEASE, lease)
        print(f"FINAL {verdict} remote CN eligible={bool(candidate) if complete else 'UNKNOWN'} "
              f"restored={restored}", flush=True)
    if not complete:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
