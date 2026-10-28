"""Compare secured hub routing preferences without changing guest configurations."""
import argparse
import copy
import json
import re
import time

import aspath_sweep as sweep
import control
import design_snapshot as snapshot
import hrp_comparison as hrp
import infra


def selected_route(text, prefix):
    current = None
    selected = None
    for line in text.splitlines():
        match = re.match(r"(\d+\.\d+\.\d+\.\d+/\d+)\s", line)
        if match:
            current = match.group(1)
        marker = re.search(r"\]\s+([*!])\s+\(", line)
        if current == prefix and marker:
            protocol = re.search(r"\[([A-Za-z0-9_]+)\s", line)
            if selected is not None:
                raise RuntimeError("Multiple selected BIRD routes for " + prefix)
            selected = dict(prefix=prefix, protocol=protocol.group(1) if protocol else None,
                            headline=line.strip(), asPath=[], localPreference=None,
                            selectionMarker=marker.group(1),
                            kernelExportFailed=marker.group(1) == "!")
        elif current == prefix and selected is not None:
            if "BGP.as_path:" in line:
                selected["asPath"] = [int(x) for x in line.split("BGP.as_path:", 1)[1].split()]
            if "BGP.local_pref:" in line:
                selected["localPreference"] = int(line.split("BGP.local_pref:", 1)[1].strip())
            if re.search(r"\bunicast\s+\[", line):
                break
        elif selected is not None and current != prefix:
            break
    if selected is None:
        raise RuntimeError("Selected BIRD route missing for " + prefix)
    return selected


def source_unchanged(before, after):
    return all(before[k] == after[k] for k in ("sha256", "stat", "protocols"))


def original_hubs(hubs):
    resources = []
    for site in sweep.SITES:
        original = hubs[site]["hub"]
        resource = sweep.hub_resource(copy.deepcopy(original))
        resource["properties"]["hubRoutingPreference"] = original["properties"]["hubRoutingPreference"]
        resources.append(resource)
    return resources


def capture(label, baseline_sources, expected_preference=None):
    sweep.CURRENT = sweep.OUT / label
    hubs = snapshot.metadata(label)
    if expected_preference and any(h["preference"] != expected_preference for h in hubs.values()):
        raise RuntimeError("Actual HRP differs from accepted scenario")
    firewalls = snapshot.firewall_routes(label, hubs)
    nvas = snapshot.nvas(label + "-nva")
    if any(not source_unchanged(baseline_sources[s], nvas[s]) for s in snapshot.ALL_SITES):
        raise RuntimeError("Preserved guest source or peer state differs")
    selected = {s: [selected_route(nvas[s]["birdRoutes"]["stdout"], p)
                    for p in (*guest_prefixes(), *snapshot.guest.SPOKE_PREFIXES)]
                for s in snapshot.ALL_SITES}
    sweep.save(label + "-selected.json", selected)
    traffic = snapshot.traffic(label)
    return dict(hubs=hubs, firewalls=firewalls, nvas=nvas, selected=selected, traffic=traffic)


def guest_prefixes():
    return tuple(snapshot.guest.DC.values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lease", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--baseline", required=True)
    args = parser.parse_args()
    control.LEASE = control.RUNTIME / args.lease
    lease = control.guard(True)
    if lease.get("toolCallsUsed", 0) or lease.get("mutationsUsed", 0):
        raise RuntimeError("Fresh mutation lease required")
    sweep.SUB = control.account_id()
    sweep.OUT = control.ROOT.parent / "show-output" / args.out
    sweep.CURRENT = sweep.OUT / "preflight"
    if sweep.OUT.exists():
        raise RuntimeError("Fresh correlation directory required")
    baseline = json.loads((control.ROOT.parent / "show-output" / args.baseline /
                           "baseline-verdict.json").read_text().replace("<SUBSCRIPTION_ID>", sweep.SUB))
    if baseline["verdict"] != "PASS":
        raise RuntimeError("Independent accepted baseline required")
    before = baseline["result"]
    states, errors = {}, []
    dirty = False
    restored = False
    try:
        actual = snapshot.metadata("before")
        if any(actual[s]["preference"] != before["hubs"][s]["preference"] for s in sweep.SITES):
            raise RuntimeError("User baseline HRPs changed before comparison")
        for preference in ("ExpressRoute", "VpnGateway", "ASPath"):
            sweep.reserve_restore(control.guard(True))
            sweep.CURRENT = sweep.OUT / preference
            dirty = True
            hrp.set_preference(preference, "set-" + preference)
            states[preference] = capture(preference, before["sources"], preference)
            winners = [r for r in states[preference]["firewalls"]["rows"]
                       if r["prefix"] == "10.130.0.0/24"]
            print("OBSERVATION " + preference + " " + json.dumps([
                dict(observer=r["observer"], asPath=r["asPath"], nextHopType=r["nextHopType"])
                for r in winners]), flush=True)
    except Exception as exc:
        errors.append(str(exc))
        print("COMPARISON ERROR " + str(exc), flush=True)
    finally:
        sweep.RESTORING = True
        sweep.RESTORE_DEADLINE = time.monotonic() + 60 * lease["restoreTimeoutMinutes"]
        try:
            if dirty:
                sweep.CURRENT = sweep.OUT / "restore"
                sweep.submit(infra.template(original_hubs(before["hubs"])),
                             {"parameters": {}}, "restore-exact-mixed-hrps", mutation=True)
                final = capture("restore", before["sources"])
                if any(final["hubs"][s]["preference"] != before["hubs"][s]["preference"]
                       for s in sweep.SITES):
                    raise RuntimeError("Exact per-hub original HRPs differ")
                if final["firewalls"]["rows"] != before["firewalls"]["rows"]:
                    raise RuntimeError("Original paired firewall winners differ")
                states["restore"] = final
                dirty = False
            restored = not dirty
        except Exception as exc:
            errors.append("RESTORE: " + str(exc))
        verdict = "PASS" if restored and not errors and len(states) == 4 else (
            "INCONCLUSIVE" if restored else "BLOCKED")
        actual_lease = json.loads(control.LEASE.read_text())
        sweep.CURRENT = sweep.OUT
        sweep.save("comparison-verdict.json", dict(
            timestampUtc=sweep.utc(), verdict=verdict, restored=restored,
            states=states, errors=errors, originalPreferences={s: h["preference"]
                for s, h in before["hubs"].items()}, callsUsed=actual_lease["toolCallsUsed"],
            mutationsUsed=actual_lease["mutationsUsed"], children=[],
            interpretation="PASS means stable measured comparison and exact restore, not an assertion that every traffic cell passed"))
        actual_lease.update(state="completed" if verdict == "PASS" else "rolled-back" if restored else "blocked",
                            verdict=verdict, completedAtUtc=sweep.utc(), children=[])
        control.save(control.LEASE, actual_lease)
        print(f"FINAL {verdict} HRP comparison restored={restored}", flush=True)
    if verdict != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
