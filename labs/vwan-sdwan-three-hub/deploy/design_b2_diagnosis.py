"""Reversible B2 Japan-workload steering control, without DC-to-DC probes."""
import argparse
import copy
import datetime as dt
import hashlib
import json
import re
import time

import aspath_sweep as sweep
import control
import design_b2b as b2b
import design_backbone as backbone
import design_comparison as comparison
import design_customer as customer
import design_snapshot as snapshot
import infra

CORRELATION = "b2-diagnosis-20261017"


def workload_evidence(label):
    subnet = sweep.az(["rest", "--method", "get", "--url",
                       sweep.network_url("virtualNetworks", "vnet-dc-jp/subnets/workload") +
                       "?api-version=2024-05-01"], label + "-subnet")
    effective = sweep.az(["network", "nic", "show-effective-route-table", "-g", control.RG,
                          "-n", "nic-probe-dc-jp"], label + "-workload-effective-routes")
    body = """
def run(args):
 p=subprocess.run(args,text=True,capture_output=True,timeout=30)
 assert p.returncode==0,p.stderr
 return p.stdout
result=dict(routes=run(['ip','-j','route','show','table','all']),
 rules=run(['ip','-j','rule']),listener=run(['systemctl','is-active','lab-http']),
 service=run(['systemctl','cat','threehub-probe']),
 lookups={ip:run(['ip','-j','route','get',ip,'from','10.130.0.10'])
          for ip in ('10.10.0.10','10.20.0.10','10.30.0.10')})
"""
    guest = b2b.guest_batch(label + "-workload",
                           {"probe-dc-jp": b2b.python_script(body, "B2_WORKLOAD")}, "B2_WORKLOAD")
    result = dict(subnet=subnet, effectiveRoutes=effective, guest=guest)
    sweep.save("workload-evidence.json", result)
    return result


def measured(label, expected, all_enabled=False):
    result = b2b.capture(label, expected, all_enabled, dc_azure_only=True)
    result["workload"] = workload_evidence(label)
    sweep.save("scenario-result.json", result)
    return result


def experiment(before):
    desired = {s: customer.policy(before["sources"][s]["config"], s, 0) for s in ("eu", "us")}
    working = copy.deepcopy(before["sources"])
    for s, text in desired.items():
        working[s]["sha256"] = hashlib.sha256(text.encode()).hexdigest()
    dirty, hub_dirty, subnet_dirty, table_created = [], False, False, False
    states, errors = {}, []
    subnet = None
    backbone.BACKUP = "/var/lib/threehub/" + CORRELATION + "-baseline.conf"
    backbone.ROUTE_TABLE = CORRELATION + "-jp-spokes"
    backbone.UDR_PREFIXES = tuple(infra.SPOKE_PREFIXES)
    try:
        sweep.reserve_restore(control.guard(True))
        for s, text in desired.items():
            dirty.append(s)
            backbone.configure(s, before["sources"][s], text)
        hub_dirty = True
        b2b.set_hubs(before["hubs"], "ASPath", True, "diagnose-B2")
        states["B2-before"] = measured("B2-before", working, True)
        subnet = states["B2-before"]["workload"]["subnet"]
        if subnet["properties"].get("routeTable"):
            raise RuntimeError("Existing Japan workload route table; refusing overwrite")
        tables = sweep.az(["network", "route-table", "list", "-g", control.RG], "existing-tables")
        if any(t["name"] == backbone.ROUTE_TABLE for t in tables):
            raise RuntimeError("Diagnosis route table already exists")
        sweep.reserve_restore(control.guard(True))
        sweep.CURRENT = sweep.OUT / "B2-with-UDR"
        route_id = sweep.network_url("routeTables", backbone.ROUTE_TABLE).replace(
            "https://management.azure.com", "")
        resource = backbone.subnet_resource(subnet, route_id)
        resource["dependsOn"] = [f"[resourceId('Microsoft.Network/routeTables', '{backbone.ROUTE_TABLE}')]"]
        subnet_dirty = table_created = True
        sweep.submit(infra.template([backbone.route_table(sweep.SUB), resource]),
                     {"parameters": {}}, CORRELATION + "-add-spoke-udr", True)
        states["B2-with-UDR"] = measured("B2-with-UDR", working, True)
        sweep.CURRENT = sweep.OUT / "remove-UDR"
        sweep.submit(infra.template([backbone.subnet_resource(subnet)]), {"parameters": {}},
                     CORRELATION + "-remove-spoke-udr", True)
        subnet_dirty = False
        states["B2-reverted"] = measured("B2-reverted", working, True)
        reference = states["B2-before"]
        for name in ("B2-with-UDR", "B2-reverted"):
            actual = states[name]
            if actual["firewalls"]["rows"] != reference["firewalls"]["rows"]:
                raise RuntimeError("B2 firewall winners changed during steering control")
            if b2b.selection_state(actual["selected"]) != b2b.selection_state(reference["selected"]):
                raise RuntimeError("B2 selected NVA routes changed during steering control")
        sweep.CURRENT = sweep.OUT
        sweep.save("diagnostic-comparison.json", {
            name: dict(traffic=value["traffic"], effectiveRoutes=value["workload"]["effectiveRoutes"])
            for name, value in states.items()})
    except Exception as exc:
        errors.append(str(exc))
        print("DIAGNOSIS ERROR " + str(exc), flush=True)
    finally:
        sweep.RESTORING = True
        sweep.RESTORE_DEADLINE = time.monotonic() + 20 * 60
        sweep.CURRENT = sweep.OUT / "restore"
        try:
            if subnet_dirty:
                sweep.submit(infra.template([backbone.subnet_resource(subnet)]),
                             {"parameters": {}}, CORRELATION + "-restore-subnet", True)
                subnet_dirty = False
            if table_created:
                sweep.az(["network", "route-table", "delete", "-g", control.RG,
                          "-n", backbone.ROUTE_TABLE], "delete-only-diagnosis-route-table", True)
                table_created = False
            for s in reversed(dirty.copy()):
                backbone.configure(s, before["sources"][s], desired[s], restore=True)
                dirty.remove(s)
            if hub_dirty:
                b2b.set_hubs(before["hubs"], label="restore-original")
                hub_dirty = False
            sources = snapshot.nvas("restore-source", True)
            hubs = snapshot.metadata("restore")
            if any(not comparison.source_unchanged(before["sources"][s], sources[s])
                   for s in snapshot.ALL_SITES):
                raise RuntimeError("Exact original BIRD bytes/metadata/peers differ")
            if any((hubs[s]["preference"],
                    hubs[s]["hub"]["properties"]["allowBranchToBranchTraffic"]) !=
                   (before["hubs"][s]["preference"],
                    before["hubs"][s]["hub"]["properties"]["allowBranchToBranchTraffic"])
                   for s in sweep.SITES):
                raise RuntimeError("Original hub HRPs/flags differ")
            firewalls = b2b.reselection.firewall_capture("restore", hubs, complete=False)
            if firewalls["rows"] != before["firewalls"]["rows"]:
                raise RuntimeError("Original stable firewall winners differ")
            actual = workload_evidence("restore")
            if actual["subnet"]["properties"].get("routeTable") != before["workload"]["subnet"]["properties"].get("routeTable"):
                raise RuntimeError("Original Japan subnet route table association differs")
            states["restore"] = dict(sources=sources, hubs=hubs, firewalls=firewalls, workload=actual)
        except Exception as exc:
            errors.append("RESTORE: " + str(exc))
        restored = "restore" in states and not (dirty or hub_dirty or subnet_dirty or table_created)
        verdict = "PASS" if restored and not errors and len(states) == 4 else "INCONCLUSIVE" if restored else "BLOCKED"
        sweep.CURRENT = sweep.OUT
        sweep.save("diagnosis-verdict.json", dict(verdict=verdict, restored=restored, errors=errors,
                   timestampUtc=sweep.utc(), states=states,
                   pending=dict(guests=dirty, hubs=hub_dirty, subnet=subnet_dirty, table=table_created),
                   interpretation="PASS means complete reversible measurement and exact restore, not all traffic passes"))
        lease = json.loads(control.LEASE.read_text(encoding="utf-8"))
        lease.update(state="completed" if verdict == "PASS" else "rolled-back" if restored else "blocked",
                     verdict=verdict, completedAtUtc=sweep.utc(), children=[])
        control.save(control.LEASE, lease)
        print(f"FINAL {verdict} diagnosis restored={restored}", flush=True)
    if verdict != "PASS":
        raise SystemExit(1)


def reconcile(control_folder, baseline_folder, output_folder):
    import b2b_report as report

    root = control.ROOT.parent / "show-output"
    out = root / output_folder
    if out.exists():
        raise RuntimeError("Fresh reconciliation output required")

    def read(folder, file):
        return json.loads((root / folder / file).read_text(encoding="utf-8"))

    original = read(control_folder, "diagnosis-verdict.json")
    expected_error = "B2 selected NVA routes changed during steering control"
    if (original["verdict"] != "INCONCLUSIVE" or not original["restored"] or
            original["errors"] != [expected_error] or any(original["pending"].values())):
        raise RuntimeError("Unexpected original collector verdict; cannot reconcile")
    names = ("B2-before", "B2-with-UDR", "B2-reverted")
    states = {name: read(control_folder, name + "/scenario-result.json") for name in names}
    reference = states[names[0]]
    changes = []
    for index, (name, state) in enumerate(states.items()):
        if b2b.selection_state(state["selected"]) != b2b.selection_state(reference["selected"]):
            raise RuntimeError("Structured route selection changed")
        if state["firewalls"]["rows"] != reference["firewalls"]["rows"]:
            raise RuntimeError("Stable firewall winners changed")
        traffic = report.acceptance(state["traffic"])
        expected = 24 if index == 1 else 18
        if traffic["tcpPass"] != expected or traffic["icmpPass"] != expected:
            raise RuntimeError("Failure/fix/removal traffic sequence differs")
        for site in snapshot.ALL_SITES:
            if not comparison.source_unchanged(reference["sources"][site], state["sources"][site]):
                raise RuntimeError("BIRD source/metadata/peers changed")
            for old, new in zip(reference["selected"][site], state["selected"][site]):
                if old["headline"] == new["headline"]:
                    continue
                stamp = r"\b\d{2}:\d{2}:\d{2}(?:\.\d+)?\b"
                if re.sub(stamp, "<DISPLAY_TIME>", old["headline"]) != re.sub(
                        stamp, "<DISPLAY_TIME>", new["headline"]):
                    raise RuntimeError("Non-timestamp headline content changed")
                old_time, new_time = re.search(stamp, old["headline"]), re.search(stamp, new["headline"])
                if not old_time or not new_time:
                    raise RuntimeError("Expected BIRD display timestamps missing")
                delta = abs((dt.datetime.strptime(old_time[0], "%H:%M:%S.%f") -
                             dt.datetime.strptime(new_time[0], "%H:%M:%S.%f")).total_seconds())
                if delta > 0.001:
                    raise RuntimeError("Headline timestamp difference exceeds one millisecond")
                changes.append(dict(state=name, site=site, prefix=old["prefix"],
                                    before=old["headline"], after=new["headline"],
                                    deltaMilliseconds=round(delta * 1000)))
            for prefix in (*comparison.guest_prefixes(), *infra.SPOKE_PREFIXES):
                old = report.selected_details(reference["nvas"][site]["birdRoutes"]["stdout"], prefix)
                new = report.selected_details(state["nvas"][site]["birdRoutes"]["stdout"], prefix)
                if {k: v for k, v in old.items() if k != "headline"} != {
                        k: v for k, v in new.items() if k != "headline"}:
                    raise RuntimeError("BGP next hop or BIRD resolution changed")
    baseline = read(baseline_folder, "baseline-verdict.json")["result"]
    restored = original["states"]["restore"]
    if restored["firewalls"]["rows"] != baseline["firewalls"]["rows"]:
        raise RuntimeError("Original firewall winners not restored")
    for site in snapshot.ALL_SITES:
        if not comparison.source_unchanged(restored["sources"][site], baseline["sources"][site]):
            raise RuntimeError("Original BIRD bytes/metadata/peers not restored")
    out.mkdir()
    (out / "reconciliation-verdict.json").write_text(json.dumps(dict(
        verdict="PASS", rawCollectorVerdict=original["verdict"], originalErrors=original["errors"],
        restored=True, semanticSelectionsStable=True, nextHopsAndResolutionStable=True,
        headlineTimestampChanges=changes, timestampUtc=sweep.utc(),
        interpretation="Original INCONCLUSIVE verdict is preserved. Its comparison included BIRD display timestamps; "
        "only <=1ms rendering differences changed. Structured selections, BGP hops/resolution, exact sources and "
        "firewall winners are unchanged across the 18/24 -> 24/24 -> 18/24 control."), indent=2) + "\n",
        encoding="utf-8")
    print(f"PASS: reconciled {len(changes)} display-only timestamp differences; original verdict unchanged")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("baseline", "experiment", "verify", "reconcile"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--baseline")
    parser.add_argument("--control")
    args = parser.parse_args()
    if args.mode == "reconcile":
        if not args.control or not args.baseline:
            raise ValueError("Control and original baseline folders required")
        reconcile(args.control, args.baseline, args.out)
        return
    b2b.CORRELATION = CORRELATION
    sweep.SUB = control.account_id()
    sweep.OUT = control.ROOT.parent / "show-output" / args.out
    sweep.CURRENT = sweep.OUT
    control.LEASE = control.RUNTIME / (args.out + ".json")
    if sweep.OUT.exists() or control.LEASE.exists():
        raise RuntimeError("Fresh output and lease required")
    now = dt.datetime.now(dt.timezone.utc)
    control.save(control.LEASE, dict(taskId=args.out, ownerRole="Oracle",
                 objective="Reversible B2 Japan workload steering " + args.mode,
                 startedAtUtc=now.isoformat(), expiresAtUtc=(now + dt.timedelta(minutes=90)).isoformat(),
                 maxToolCalls=220, maxMutations=16, commandTimeoutSeconds=600,
                 restoreTimeoutMinutes=20, state="active", toolCallsUsed=0, mutationsUsed=0))
    sweep.RESTORING, sweep.RESTORE_DEADLINE = False, None
    control.guard(True)
    before = b2b.read_evidence(args.baseline, "baseline-verdict.json")["result"] if args.baseline else None
    if args.mode == "experiment":
        if before is None:
            raise ValueError("Original baseline required")
        experiment(before)
        return
    result = measured("original-baseline" if before is None else "independent-verification",
                      before["sources"] if before else None)
    if before:
        if result["firewalls"]["rows"] != before["firewalls"]["rows"]:
            raise RuntimeError("Independent original firewall winners differ")
        for s in sweep.SITES:
            a, b = result["hubs"][s], before["hubs"][s]
            if (a["preference"], a["hub"]["properties"]["allowBranchToBranchTraffic"]) != (
                    b["preference"], b["hub"]["properties"]["allowBranchToBranchTraffic"]):
                raise RuntimeError("Independent original hub settings differ")
        if result["workload"]["subnet"]["properties"].get("routeTable") != before["workload"]["subnet"]["properties"].get("routeTable"):
            raise RuntimeError("Independent original subnet association differs")
        pairs = lambda data: {(c["source"], c["destination"], c["tcp"], c["icmp"])
                              for c in data["traffic"]["cells"]}
        if pairs(result) != pairs(before):
            raise RuntimeError("Independent original traffic outcomes differ")
    sweep.CURRENT = sweep.OUT
    sweep.save("baseline-verdict.json", dict(verdict="PASS", result=result, timestampUtc=sweep.utc()))
    lease = control.guard(False)
    lease.update(state="completed", completedAtUtc=sweep.utc(), children=[])
    control.save(control.LEASE, lease)


if __name__ == "__main__":
    main()
