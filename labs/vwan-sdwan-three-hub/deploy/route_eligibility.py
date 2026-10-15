"""Withdraw one Japan DC advertisement to test remote path eligibility, then restore."""
import argparse
import copy
import json
import time

import aspath_sweep as sweep
import control
import infra
import vpn_sdwan_boundary as boundary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lease", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--secured", action="store_true")
    parser.add_argument("--enable-hub-transit", action="store_true")
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
    dirty_hubs = False
    original_hubs = []
    try:
        before = boundary.invoke_all("baseline")
        boundary.BASE.update(before)
        states["baseline"] = sweep.capture("baseline", 0, firewall_ids=firewall_ids, parallel=True)
        if states["baseline"]["verdict"] != "PASS":
            raise RuntimeError("Incomplete baseline")
        if args.enable_hub_transit:
            values = sweep.az_batch([
                (["rest", "--method", "get", "--url",
                  sweep.network_url("virtualHubs", "hub-" + site) +
                  "?api-version=2024-05-01"], "transit-before-" + site)
                for site in sweep.SITES
            ])
            original_hubs = [sweep.hub_resource(v) for v in values]
            candidate = copy.deepcopy(original_hubs)
            for resource in candidate:
                resource["properties"]["allowBranchToBranchTraffic"] = True
            sweep.reserve_restore(control.guard(True))
            dirty_hubs = True
            sweep.submit(infra.template(candidate), {"parameters": {}},
                         "cn-control-enable-transit", True)
            states["transit-enabled"] = sweep.capture(
                "transit-enabled", 0, firewall_ids=firewall_ids, parallel=True)
            metadata = json.loads((sweep.CURRENT / "hub-metadata.json").read_text())
            if (states["transit-enabled"]["verdict"] != "PASS" or
                    not all(metadata["observed"][s]["hub"]["properties"].get(
                        "allowBranchToBranchTraffic") is True for s in sweep.SITES)):
                raise RuntimeError("Transit-enabled baseline incomplete or unaccepted")
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
        changed = dirty or dirty_hubs
        try:
            if dirty:
                sweep.CURRENT = sweep.OUT / "restore"
                proof = boundary.invoke("jp", "restore", restore=True)
                if any(proof[k] != before["jp"][k] for k in ("sha256", "stat", "exports")):
                    raise RuntimeError("Japan exact file/export restore differs")
                dirty = False
            if dirty_hubs:
                sweep.submit(infra.template(original_hubs), {"parameters": {}},
                             "cn-control-restore-transit", True)
                dirty_hubs = False
            if before and changed:
                states["restore"] = sweep.capture("restore", 0, firewall_ids=firewall_ids, parallel=True)
                if (states["restore"]["verdict"] != "PASS" or
                        states["restore"]["rows"] != states["baseline"]["rows"]):
                    raise RuntimeError("Restored effective route matrix differs")
                if original_hubs:
                    metadata = json.loads((sweep.CURRENT / "hub-metadata.json").read_text())
                    if any(metadata["observed"][s]["hub"]["properties"].get(
                            "allowBranchToBranchTraffic") !=
                           original_hubs[i]["properties"].get("allowBranchToBranchTraffic")
                           for i, s in enumerate(sweep.SITES)):
                        raise RuntimeError("Original hub transit flags differ")
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
        baseline_cn = [r for r in states.get("baseline", {}).get("rows", [])
                       if r["observer"] == "jp" and r["prefix"] == "10.140.0.0/24"]
        remote = (len(candidate) == 1 and len(baseline_cn) == 1 and
                  sweep.winning_identity(candidate[0]) != sweep.winning_identity(baseline_cn[0]))
        if candidate and not remote:
            errors.append("Withdrawal still shows the original local winner; remote eligibility unproven")
        restored = not dirty and not dirty_hubs and len(after) == 4 and not any(
            e.startswith("RESTORE:") for e in errors)
        complete = restored and len(states) == (4 if args.enable_hub_transit else 3) and not errors
        # Persist the local verdict even when expiry forbids further live work.
        lease = json.loads(control.LEASE.read_text(encoding="utf-8-sig"))
        verdict = "PASS" if complete else "INCONCLUSIVE" if restored else "BLOCKED"
        sweep.CURRENT = sweep.OUT
        sweep.save("eligibility-verdict.json", dict(
            timestampUtc=sweep.utc(), verdict=verdict, restored=restored,
            japanRemoteCNRoute=candidate, remoteCNEligible=remote if complete else None,
            states=states, errors=errors, sourceBefore=before, sourceAfter=after,
            callsUsed=lease["toolCallsUsed"], mutationsUsed=lease.get("mutationsUsed", 0),
            children=[], noDataPlaneClaim=True))
        lease.update(state="completed" if complete else "rolled-back" if restored else "blocked",
                     verdict=verdict, completedAtUtc=sweep.utc(), children=[], evidence=str(sweep.OUT))
        control.save(control.LEASE, lease)
        print(f"FINAL {verdict} remote CN eligible={remote if complete else 'UNKNOWN'} "
              f"restored={restored}", flush=True)
    if not complete:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
