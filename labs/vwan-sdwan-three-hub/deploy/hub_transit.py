"""Test per-hub branch transit without changing guests, HRP, or VPN state."""
import argparse
import copy
import json
import time

import aspath_sweep as sweep
import control
import effective_routes
import infra
import vpn_sdwan_boundary as boundary


def remote_spokes(values):
    return {
        site: sorted(set(
            prefix for row in value["value"] for prefix in row.get("addressPrefixes", [])
            if prefix in set(infra.SPOKE_PREFIXES) - {infra.SPOKE_PREFIXES[index]}
        ))
        for index, (site, value) in enumerate(zip(sweep.SITES, values))
    }


def capture(label):
    sweep.CURRENT = sweep.OUT / label

    def snapshot(number):
        values = sweep.az_batch([
            (effective_routes.arguments(sweep.SUB, control.RG, site),
             f"{label}-{site}-{number}") for site in sweep.SITES
        ])
        if any(not isinstance(v, dict) or not isinstance(v.get("value"), list)
               for v in values):
            raise RuntimeError("Completed effective-route responses required")
        sweep.save(f"snapshot-{number}.json", values)
        return [dict(value, value=sorted(value["value"], key=lambda r: json.dumps(r, sort_keys=True)))
                for value in values]

    first, second = effective_routes.two_snapshots(snapshot, wait=sweep.bounded_wait)
    result = dict(stable=first == second, remoteSpokes=remote_spokes(second))
    sweep.save("analysis.json", result)
    if not result["stable"]:
        raise RuntimeError("Unstable paired hub transit evidence")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lease", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    control.LEASE = control.RUNTIME / args.lease
    lease = control.guard(True)
    if lease.get("toolCallsUsed", 0) or lease.get("mutationsUsed", 0):
        raise RuntimeError("Fresh lease required")
    sweep.SUB = control.account_id()
    sweep.OUT = control.ROOT.parent / "show-output" / args.out
    if sweep.OUT.exists():
        raise RuntimeError("Fresh evidence directory required")
    sweep.CURRENT = sweep.OUT / "preflight"
    before, after, states, errors, resources = {}, {}, {}, [], []
    dirty = False
    accepted = False
    try:
        before = boundary.invoke_all("baseline")
        metadata = sweep.hub_metadata()
        resources = [sweep.hub_resource(metadata[s]["hub"]) for s in sweep.SITES]
        states["before"] = capture("before")
        sweep.reserve_restore(control.guard(True))
        candidate = copy.deepcopy(resources)
        for resource in candidate:
            resource["properties"]["allowBranchToBranchTraffic"] = True
        sweep.CURRENT = sweep.OUT / "enable"
        dirty = True
        sweep.submit(infra.template(candidate), {"parameters": {}}, "enable-hub-transit", True)
        actual = sweep.hub_metadata()
        accepted = all(actual[s]["hub"]["properties"].get("allowBranchToBranchTraffic") is True
                       for s in sweep.SITES)
        if not accepted:
            raise RuntimeError("Provider did not accept per-hub branch transit")
        states["enabled"] = capture("enabled")
    except Exception as exc:
        errors.append(str(exc))
        print(f"TRANSIT ERROR {exc}", flush=True)
    finally:
        sweep.RESTORING = True
        sweep.RESTORE_DEADLINE = time.monotonic() + 900
        try:
            if dirty:
                sweep.CURRENT = sweep.OUT / "restore"
                sweep.submit(infra.template(resources), {"parameters": {}}, "restore-hub-transit", True)
                actual = sweep.hub_metadata()
                if any(actual[s]["hub"]["properties"].get("allowBranchToBranchTraffic") !=
                       resources[i]["properties"].get("allowBranchToBranchTraffic")
                       for i, s in enumerate(sweep.SITES)):
                    raise RuntimeError("Original per-hub branch-transit flags differ")
                dirty = False
                states["restore"] = capture("restore")
                if states["restore"] != states["before"]:
                    raise RuntimeError("Restored route visibility differs from baseline")
            sweep.CURRENT = sweep.OUT / "closure"
            after = boundary.invoke_all("closure")
            for site in (*sweep.SITES, "cn"):
                if not boundary.same_source(before[site], after[site]):
                    raise RuntimeError(f"{site}: original source closure differs")
        except Exception as exc:
            errors.append("RESTORE: " + str(exc))
        restored = not dirty and len(after) == 4 and not any(e.startswith("RESTORE:") for e in errors)
        complete = restored and accepted and len(states) == 3 and not errors
        verdict = "PASS" if complete else "INCONCLUSIVE" if restored else "BLOCKED"
        lease = json.loads(control.LEASE.read_text(encoding="utf-8-sig"))
        sweep.CURRENT = sweep.OUT
        sweep.save("transit-verdict.json", dict(
            timestampUtc=sweep.utc(), verdict=verdict, restored=restored,
            accepted=accepted, states=states, errors=errors, sourceBefore=before,
            sourceAfter=after, callsUsed=lease["toolCallsUsed"],
            mutationsUsed=lease.get("mutationsUsed", 0), children=[]))
        lease.update(state="completed" if complete else "rolled-back" if restored else "blocked",
                     verdict=verdict, completedAtUtc=sweep.utc(), children=[], evidence=str(sweep.OUT))
        control.save(control.LEASE, lease)
        print(f"FINAL {verdict} accepted={accepted} restored={restored}", flush=True)
    if not complete:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
