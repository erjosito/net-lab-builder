"""Bounded HRP comparison with direct guest commands and exact baseline restore."""
import argparse
import json
import time

import aspath_sweep as sweep
import control
import infra
import vpn_sdwan_boundary as boundary


def set_preference(preference, label):
    if preference not in ("ASPath", "VpnGateway", "ExpressRoute"):
        raise ValueError("Unsupported ARM hubRoutingPreference")
    resources = []
    for site in sweep.SITES:
        actual = sweep.rest(sweep.network_url("virtualHubs", "hub-" + site),
                            f"{label}-before-{site}")
        resource = sweep.hub_resource(actual)
        resource["properties"]["hubRoutingPreference"] = preference
        resources.append(resource)
    sweep.submit(infra.template(resources), {"parameters": {}}, label, mutation=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lease", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--secured", action="store_true")
    parser.add_argument("--ingress", choices=("eu", "jp"), default="eu")
    parser.add_argument("--preferences-only", action="store_true")
    args = parser.parse_args()
    control.LEASE = control.RUNTIME / args.lease
    lease = control.guard(True)
    if lease.get("toolCallsUsed", 0) or lease.get("mutationsUsed", 0):
        raise RuntimeError("A fresh lease is required")
    sweep.SUB = control.account_id()
    sweep.OUT = control.ROOT.parent / "show-output" / args.out
    if sweep.OUT.exists():
        raise RuntimeError("Refusing to overwrite evidence")
    sweep.CURRENT = sweep.OUT / "preflight"
    before, after, states, errors = {}, {}, {}, []
    dirty_guest, dirty_hubs = False, False
    baseline = None
    ingress = args.ingress
    firewall_ids = ({
        site: (f"/subscriptions/{sweep.SUB}/resourceGroups/{control.RG}"
               f"/providers/Microsoft.Network/azureFirewalls/fw-{site}")
        for site in sweep.SITES
    } if args.secured else None)
    prefix = "aspath-" + ingress

    def capture(label, preference="ASPath", count=0):
        result = sweep.capture(label, count, ingress=ingress.upper() if count else "ALL_ZERO",
                               preference=preference, firewall_ids=firewall_ids,
                               parallel=True)
        states[label] = result
        if result["verdict"] != "PASS":
            raise RuntimeError(f"{label}: incomplete or unstable effective routes")
        return result

    def restore_guest(label):
        nonlocal dirty_guest
        sweep.CURRENT = sweep.OUT / label
        proof = boundary.invoke(ingress, label, restore=True)
        if any(proof[k] != before[ingress][k] for k in ("sha256", "stat", "exports")):
            raise RuntimeError(f"{ingress}: exact restore differs")
        dirty_guest = False

    try:
        before = boundary.invoke_all("baseline")
        boundary.BASE.update(before)
        baseline = capture("aspath-zero")
        if not args.preferences_only:
            sweep.reserve_restore(control.guard(True))
            sweep.CURRENT = sweep.OUT / (prefix + "-add8")
            dirty_guest = True
            boundary.invoke(ingress, "add8", count=8)
            capture(prefix + "-add8", count=8)
            restore_guest(ingress + "-restore-proof")
            restored = capture(prefix + "-restore")
            if restored["rows"] != baseline["rows"]:
                raise RuntimeError("Restored ASPath winner matrix differs")
        for preference, label in (("VpnGateway", "vpn-zero"), ("ExpressRoute", "er-zero")):
            sweep.reserve_restore(control.guard(True))
            sweep.CURRENT = sweep.OUT / label
            dirty_hubs = True
            set_preference(preference, label)
            capture(label, preference=preference)
    except Exception as exc:
        errors.append(str(exc))
        print(f"COMPARISON ERROR {exc}", flush=True)
    finally:
        sweep.RESTORING = True
        sweep.RESTORE_DEADLINE = time.monotonic() + 900
        try:
            if dirty_guest:
                restore_guest(ingress + "-error-restore")
            if dirty_hubs:
                sweep.CURRENT = sweep.OUT / "hub-restore"
                set_preference("ASPath", "restore-aspath")
                dirty_hubs = False
                restored = capture("aspath-final-restore")
                if baseline is None or restored["rows"] != baseline["rows"]:
                    raise RuntimeError("Final ASPath matrix differs from baseline")
            sweep.CURRENT = sweep.OUT / "closure"
            after = boundary.invoke_all("closure")
            for site in (*sweep.SITES, "cn"):
                if any(after[site][k] != before.get(site, {}).get(k)
                       for k in ("sha256", "stat", "exports", "protocols", "ikeEstablished")):
                    raise RuntimeError(f"{site}: exact source closure differs")
        except Exception as exc:
            errors.append("RESTORE: " + str(exc))
        restored_ok = (not dirty_guest and not dirty_hubs and len(after) == 4 and
                       not any(e.startswith("RESTORE:") for e in errors))
        complete = restored_ok and len(states) == (4 if args.preferences_only else 6) and not errors
        verdict = "PASS" if complete else "INCONCLUSIVE" if restored_ok else "BLOCKED"
        # Persist the local verdict even when expiry forbids further live work.
        lease = json.loads(control.LEASE.read_text(encoding="utf-8-sig"))
        sweep.CURRENT = sweep.OUT
        summary = dict(timestampUtc=sweep.utc(), verdict=verdict, restored=restored_ok,
                       states=states, sourceBefore=before, sourceAfter=after, errors=errors,
                       callsUsed=lease["toolCallsUsed"], mutationsUsed=lease["mutationsUsed"],
                       noDataPlaneClaim=True, children=[])
        sweep.save("comparison-verdict.json", summary)
        lease.update(state="completed" if complete else "rolled-back" if restored_ok else "blocked",
                     verdict=verdict, completedAtUtc=sweep.utc(), children=[],
                     evidence=str(sweep.OUT))
        control.save(control.LEASE, lease)
        print(f"FINAL {verdict} restored={restored_ok} states={list(states)}", flush=True)
    if not complete:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
