"""Isolate local-route eligibility and route-arrival order under ExpressRoute HRP."""
import argparse
import hashlib
import json
import time

import aspath_sweep as sweep
import control
import design_backbone as backbone
import design_comparison as comparison
import design_customer as customer
import design_snapshot as snapshot
import effective_routes
import guest
import hrp_comparison as hrp
import infra


def withdraw_japan(text):
    marker = "filter azure_export {\n"
    if text.count(marker) != 1 or "export filter azure_export;" not in text:
        raise ValueError("Expected one shared Azure export filter")
    if "if net = 10.130.0.0/24 then reject;" in text:
        raise ValueError("Japan export withdrawal already present")
    return text.replace(marker, marker + "  if net = 10.130.0.0/24 then reject;\n", 1)


def firewall_capture(label, hubs, complete=True):
    def collect(number):
        commands = [(effective_routes.arguments(
            sweep.SUB, control.RG, site, firewall_id=hubs[site]["firewallId"]),
            f"{label}-{site}-snapshot{number}") for site in sweep.SITES]
        values = sweep.az_batch(commands)
        winners = []
        for site, value in zip(sweep.SITES, values):
            if not isinstance(value, dict) or not isinstance(value.get("value"), list):
                raise RuntimeError("Completed firewall effective routes required")
            winners.extend(sweep.normalize(value, site))
            rows = [dict(Prefix=p, ASPath=r.get("asPath"),
                         NextHopType=r.get("nextHopType"))
                    for r in value["value"] for p in r.get("addressPrefixes", [])]
            sweep.save(f"{label}-{site}-table{number}.json", rows)
            sweep.save(f"{label}-{site}-table{number}.txt",
                       "Prefix\tASPath\tNextHopType\n" + "\n".join(
                           f"{r['Prefix']}\t{r['ASPath'] or ''}\t{r['NextHopType'] or ''}"
                           for r in rows))
        sweep.save(f"{label}-winners{number}.json", winners)
        return winners
    first, second = effective_routes.two_snapshots(collect, wait=sweep.bounded_wait)
    if first != second or (complete and not sweep.complete_rows(second)):
        raise RuntimeError("Stable required firewall winners not established")
    result = dict(rows=second, stable=True, complete=sweep.complete_rows(second),
                  minimumSnapshotSpacingSeconds=120)
    sweep.save("firewall-analysis.json", result)
    return result


def capture(label, expected_sources, complete=True):
    sweep.CURRENT = sweep.OUT / label
    hubs = snapshot.metadata(label)
    if any(h["preference"] != "ExpressRoute" for h in hubs.values()):
        raise RuntimeError("ExpressRoute HRP not applied on every hub")
    sources = snapshot.nvas(label + "-source", source=True)
    for site in snapshot.ALL_SITES:
        if not comparison.source_unchanged(expected_sources[site], sources[site]):
            raise RuntimeError("Unexpected source, metadata or session state: " + site)
    nvas = snapshot.nvas(label + "-routes")
    firewalls = firewall_capture(label, hubs, complete)
    selected = {s: [comparison.selected_route(nvas[s]["birdRoutes"]["stdout"], p)
                    for p in (*comparison.guest_prefixes(), *guest.SPOKE_PREFIXES)]
                for s in snapshot.ALL_SITES}
    sweep.save("selected-routes.json", selected)
    result = dict(hubs=hubs, sources=sources, nvas=nvas, firewalls=firewalls,
                  selected=selected, trafficNotRun=True)
    sweep.save("scenario-result.json", result)
    display = {s: {k: r[k] for k in ("prefix", "asPath", "nextHopType")}
               for s, r in japan_winners(result).items()}
    print("OBSERVATION " + label + " " + json.dumps(display), flush=True)
    return result


def japan_winners(result):
    return {s: next(r for r in result["firewalls"]["rows"]
                    if r["observer"] == s and r["prefix"] == guest.DC["jp"])
            for s in ("eu", "us")}


def local_japan(result, eu_extra=3):
    winners = japan_winners(result)
    return all(r["nextHopType"] == "HubBgpConnection"
               and r["asPath"] == "-".join(
                   [str(guest.ASNS[s])] * (eu_extra + 1 if s == "eu" else 4) + ["65013"])
               for s, r in winners.items())


def main():
    parser = argparse.ArgumentParser()
    for name in ("lease", "out", "baseline"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--eu-extra", type=int, choices=(2, 3), default=3)
    args = parser.parse_args()
    control.LEASE = control.RUNTIME / args.lease
    lease = control.guard(False)
    if lease.get("toolCallsUsed", 0) or lease["maxMutations"] != 6:
        raise RuntimeError("Fresh six-mutation lease required")
    sweep.SUB = control.account_id()
    sweep.OUT = control.ROOT.parent / "show-output" / args.out
    sweep.CURRENT = sweep.OUT / "preflight"
    if sweep.OUT.exists():
        raise RuntimeError("Fresh evidence directory required")
    baseline = json.loads((control.ROOT.parent / "show-output" / args.baseline /
                           "baseline-verdict.json").read_text().replace("<SUBSCRIPTION_ID>", sweep.SUB))
    if baseline["verdict"] != "PASS":
        raise RuntimeError("Accepted fresh baseline required")
    before = baseline["result"]
    for site in ("eu", "us"):
        if before["sources"][site]["config"].count(
                f"bgp_path.prepend({guest.ASNS[site]});") != 3:
            raise RuntimeError("Original three-prepend configuration required")
    backbone.BACKUP = "/var/lib/threehub/hrp-reselection-20261017-baseline.conf"
    desired = withdraw_japan(before["sources"]["jp"]["config"])
    dirty, eu_dirty, hubs_dirty, restored = False, False, False, False
    desired_eu = customer.policy(before["sources"]["eu"]["config"], "eu", 2) if args.eu_extra == 2 else None
    working = dict(before["sources"])
    states, errors, outcome = {}, [], None
    try:
        sweep.reserve_restore(control.guard(True))
        if desired_eu is not None:
            eu_dirty = True
            backbone.configure("eu", before["sources"]["eu"], desired_eu)
            working["eu"] = dict(before["sources"]["eu"],
                                 sha256=hashlib.sha256(desired_eu.encode()).hexdigest())
        hubs_dirty = True
        hrp.set_preference("ExpressRoute", "reselection-expressroute")
        states["er-original"] = capture("er-original", working)
        dirty = True
        backbone.configure("jp", before["sources"]["jp"], desired)
        expected = dict(working)
        expected["jp"] = dict(before["sources"]["jp"])
        expected["jp"]["sha256"] = hashlib.sha256(desired.encode()).hexdigest()
        states["jp-withdrawn"] = capture("jp-withdrawn", expected, complete=False)
        if not local_japan(states["jp-withdrawn"], args.eu_extra):
            raise RuntimeError("Local original NVA paths not established with Japan VPN export absent")
        backbone.configure("jp", before["sources"]["jp"], desired, restore=True)
        dirty = False
        states["jp-returned"] = capture("jp-returned", working)
        outcome = ("documented-local-preference-reproduced"
                   if local_japan(states["er-original"], args.eu_extra)
                   and local_japan(states["jp-returned"], args.eu_extra)
                   else "route-history-sensitive-local-preference"
                   if local_japan(states["jp-returned"], args.eu_extra)
                   else "local-candidate-confirmed-discrepancy-persists")
        print("DECISIVE " + outcome, flush=True)
    except Exception as exc:
        errors.append(str(exc))
        print("RESELECTION ERROR " + str(exc), flush=True)
    finally:
        sweep.RESTORING = True
        sweep.RESTORE_DEADLINE = time.monotonic() + lease["restoreTimeoutMinutes"] * 60
        sweep.CURRENT = sweep.OUT / "restore"
        try:
            if dirty:
                backbone.configure("jp", before["sources"]["jp"], desired, restore=True)
                dirty = False
            if eu_dirty:
                backbone.configure("eu", before["sources"]["eu"], desired_eu, restore=True)
                eu_dirty = False
            if hubs_dirty:
                sweep.submit(infra.template(comparison.original_hubs(before["hubs"])),
                             {"parameters": {}}, "restore-original-hrps", mutation=True)
                hubs_dirty = False
            sources = snapshot.nvas("restore-source", source=True)
            hubs = snapshot.metadata("restore")
            firewalls = firewall_capture("restore", hubs)
            if firewalls["rows"] != before["firewalls"]["rows"]:
                if control.guard(False)["mutationsUsed"] + 2 > lease["maxMutations"]:
                    raise RuntimeError("Original winners differ; no mutation budget for restore refresh")
                # Re-establish the saved ASPath winner if HRP switching retained an old best path.
                extra = withdraw_japan(before["sources"]["eu"]["config"])
                try:
                    backbone.configure("eu", before["sources"]["eu"], extra)
                finally:
                    backbone.configure("eu", before["sources"]["eu"], extra, restore=True)
                sources.update(snapshot.nvas("restore-refreshed-source", source=True, sites=("eu",)))
                firewalls = firewall_capture("restore-refreshed", hubs)
            if any(not comparison.source_unchanged(before["sources"][s], sources[s])
                   for s in snapshot.ALL_SITES):
                raise RuntimeError("Exact original source or session state differs")
            if any(hubs[s]["preference"] != before["hubs"][s]["preference"] for s in sweep.SITES):
                raise RuntimeError("Original HRPs differ")
            if firewalls["rows"] != before["firewalls"]["rows"]:
                raise RuntimeError("Original firewall winners differ")
            states["restore"] = dict(sources=sources, hubs=hubs, firewalls=firewalls)
            restored = not dirty and not eu_dirty and not hubs_dirty
        except Exception as exc:
            errors.append("RESTORE: " + str(exc))
        verdict = "PASS" if outcome and not errors and restored else "INCONCLUSIVE" if restored else "BLOCKED"
        sweep.CURRENT = sweep.OUT
        sweep.save("reselection-verdict.json", dict(
            verdict=verdict, outcome=outcome, restored=restored, errors=errors,
            states=states, extraEUPrepends=args.eu_extra, timestampUtc=sweep.utc(), trafficNotRun=True))
        lease = json.loads(control.LEASE.read_text())
        lease.update(state="completed" if verdict == "PASS" else "rolled-back" if restored else "blocked",
                     verdict=verdict, children=[])
        control.save(control.LEASE, lease)
        print(f"FINAL {verdict} {outcome} restored={restored}", flush=True)
    if verdict != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
