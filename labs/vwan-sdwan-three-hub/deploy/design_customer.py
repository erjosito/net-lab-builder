"""Measure the two customer-backbone routing controls with exact restoration."""
import argparse
import hashlib
import json
import re
import time

import aspath_sweep as sweep
import control
import design_backbone as backbone
import design_comparison as comparison
import design_snapshot as snapshot
import guest
import hrp_comparison as hrp
import infra


def policy(text, site, extra):
    if site not in ("eu", "us") or extra not in (0, 2):
        raise ValueError("Expected EU/US customer-first control with zero or two prepends")
    head, separator, tail = text.partition("filter mesh_export {")
    asn = guest.ASNS[site]
    pattern = (r"(?m)^[ \t]*if net != " + re.escape(guest.DC[site]) + r" then \{\n"
               + r"(?:[ \t]*bgp_path\.prepend\(" + str(asn) + r"\);\n){3}[ \t]*\}\n")
    replacement = (f"    if net != {guest.DC[site]} then {{\n"
                   + f"      bgp_path.prepend({asn});\n" * extra + "    }\n") if extra else ""
    head, count = re.subn(pattern, replacement, head)
    if count != 1 or not separator:
        raise ValueError("Expected the preserved user nonlocal three-prepend export block")
    return head + separator + tail


def capture(label):
    sweep.CURRENT = sweep.OUT / label
    hubs = snapshot.metadata(label)
    sources = snapshot.nvas(label + "-source", source=True)
    nvas = snapshot.nvas(label + "-routes")
    firewalls = snapshot.firewall_routes(label, hubs)
    selected = {s: [comparison.selected_route(nvas[s]["birdRoutes"]["stdout"], p)
                    for p in (*comparison.guest_prefixes(), *guest.SPOKE_PREFIXES)]
                for s in snapshot.ALL_SITES}
    sweep.save("selected-routes.json", selected)
    result = dict(hubs=hubs, sources=sources, nvas=nvas, firewalls=firewalls,
                  selected=selected, trafficNotRun=True)
    sweep.save("scenario-result.json", result)
    return result


def assert_customer(result, preference, extra):
    if any(h["preference"] != preference for h in result["hubs"].values()):
        raise RuntimeError("Actual hub preference differs")
    for site in ("eu", "us"):
        row = next(r for r in result["firewalls"]["rows"]
                   if r["observer"] == site and r["prefix"] == guest.DC["jp"])
        expected = "-".join([str(guest.ASNS[site])] * (extra + 1) + ["65013"])
        if row["nextHopType"] != "HubBgpConnection" or row["asPath"] != expected:
            raise RuntimeError(site + ": local customer-mesh Japan path did not win")
    row = next(r for r in result["firewalls"]["rows"]
               if r["observer"] == "jp" and r["prefix"] == guest.DC["eu"])
    if row["nextHopType"] != "VPN_S2S_Gateway" or row["asPath"] != "65013-65011":
        raise RuntimeError("Japan local customer-mesh EU path did not win")
    for site, prefix, protocol in (("eu", guest.DC["jp"], "mesh_jp"),
                                    ("jp", guest.DC["eu"], "mesh_eu"),
                                    ("jp", "10.10.0.0/24", "mesh_eu"),
                                    ("cn", "10.10.0.0/24", "mesh_eu")):
        row = next(r for r in result["selected"][site] if r["prefix"] == prefix)
        if row["protocol"] != protocol:
            raise RuntimeError(site + ": expected mesh selection missing for " + prefix)


def main():
    parser = argparse.ArgumentParser()
    for name in ("lease", "out"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--variant", choices=("baseline", "B1", "B2"), required=True)
    parser.add_argument("--baseline")
    args = parser.parse_args()
    control.LEASE = control.RUNTIME / args.lease
    lease = control.guard(False)
    if lease.get("toolCallsUsed", 0) or lease.get("mutationsUsed", 0):
        raise RuntimeError("Fresh lease required")
    sweep.SUB = control.account_id()
    sweep.OUT = control.ROOT.parent / "show-output" / args.out
    sweep.CURRENT = sweep.OUT / "preflight"
    if sweep.OUT.exists():
        raise RuntimeError("Fresh evidence directory required")
    if args.variant == "baseline":
        if lease["maxMutations"] != 0:
            raise RuntimeError("Read-only baseline lease required")
        sweep.RESTORING = True
        result, errors = {}, []
        try:
            result = capture("baseline")
        except Exception as exc:
            errors.append(str(exc))
        verdict = "PASS" if not errors else "BLOCKED"
        sweep.CURRENT = sweep.OUT
        sweep.save("baseline-verdict.json", dict(verdict=verdict, result=result, errors=errors,
                   timestampUtc=sweep.utc(), interpretation="Routing evidence only; no traffic probes"))
        lease = json.loads(control.LEASE.read_text())
        lease.update(state="completed" if not errors else "blocked", verdict=verdict, children=[])
        control.save(control.LEASE, lease)
        print("FINAL " + verdict + " customer-control baseline", flush=True)
        if errors:
            raise SystemExit("; ".join(errors))
        return
    if not args.baseline or lease["maxMutations"] != 6:
        raise RuntimeError("Accepted baseline and six-mutation lease required")
    baseline = json.loads((control.ROOT.parent / "show-output" / args.baseline /
                           "baseline-verdict.json").read_text().replace("<SUBSCRIPTION_ID>", sweep.SUB))
    if baseline["verdict"] != "PASS":
        raise RuntimeError("Accepted baseline required")
    before = baseline["result"]
    preference, extra = ("ExpressRoute", 2) if args.variant == "B1" else ("ASPath", 0)
    desired = {s: policy(before["sources"][s]["config"], s, extra) for s in ("eu", "us")}
    expected = {s: hashlib.sha256(desired[s].encode()).hexdigest() if s in desired
                else before["sources"][s]["sha256"] for s in snapshot.ALL_SITES}
    dirty, hubs_dirty, restored = [], False, False
    states, errors = {}, []
    try:
        actual = snapshot.metadata("before")
        if any(actual[s]["preference"] != before["hubs"][s]["preference"] for s in sweep.SITES):
            raise RuntimeError("Original hub preferences changed")
        sweep.reserve_restore(control.guard(True))
        for site in ("eu", "us"):
            dirty.append(site)
            backbone.configure(site, before["sources"][site], desired[site])
        hubs_dirty = True
        hrp.set_preference(preference, args.variant + "-hrp")
        states[args.variant] = capture(args.variant)
        for site, source in states[args.variant]["sources"].items():
            if source["sha256"] != expected[site] or source["stat"] != before["sources"][site]["stat"]:
                raise RuntimeError("Expected source bytes or metadata differ: " + site)
        assert_customer(states[args.variant], preference, extra)
        print("OBSERVATION PASS " + args.variant + " local customer paths and NVA mesh selections", flush=True)
    except Exception as exc:
        errors.append(str(exc))
        print("CUSTOMER CONTROL ERROR " + str(exc), flush=True)
    finally:
        sweep.RESTORING = True
        sweep.RESTORE_DEADLINE = time.monotonic() + lease["restoreTimeoutMinutes"] * 60
        sweep.CURRENT = sweep.OUT / "restore"
        try:
            for site in reversed(dirty.copy()):
                backbone.configure(site, before["sources"][site], desired[site], restore=True)
                dirty.remove(site)
            if hubs_dirty:
                sweep.submit(infra.template(comparison.original_hubs(before["hubs"])),
                             {"parameters": {}}, args.variant + "-restore-original-hrps", mutation=True)
                hubs_dirty = False
            sources = snapshot.nvas("restore-source", source=True)
            hubs = snapshot.metadata("restore")
            firewalls = snapshot.firewall_routes("restore", hubs)
            if any(not comparison.source_unchanged(before["sources"][s], sources[s])
                   for s in snapshot.ALL_SITES):
                raise RuntimeError("Original exact NVA source or session state differs")
            if any(hubs[s]["preference"] != before["hubs"][s]["preference"] for s in sweep.SITES):
                raise RuntimeError("Original mixed preferences differ")
            if firewalls["rows"] != before["firewalls"]["rows"]:
                raise RuntimeError("Original paired firewall winners differ")
            states["restore"] = dict(sources=sources, hubs=hubs, firewalls=firewalls)
            restored = not dirty and not hubs_dirty
        except Exception as exc:
            errors.append("RESTORE: " + str(exc))
        verdict = "PASS" if not errors and restored and args.variant in states else "INCONCLUSIVE" if restored else "BLOCKED"
        sweep.CURRENT = sweep.OUT
        sweep.save("customer-verdict.json", dict(verdict=verdict, restored=restored, errors=errors,
                   timestampUtc=sweep.utc(), states=states, variant=args.variant,
                   interpretation="Control-plane configuration and restoration only; forwarding not tested"))
        lease = json.loads(control.LEASE.read_text())
        lease.update(state="completed" if verdict == "PASS" else "rolled-back" if restored else "blocked",
                     verdict=verdict, children=[])
        control.save(control.LEASE, lease)
        print(f"FINAL {verdict} {args.variant} restored={restored}", flush=True)
    if verdict != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
