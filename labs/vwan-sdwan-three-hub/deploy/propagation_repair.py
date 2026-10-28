"""Normalize connection labels to the live built-in default table label."""
import argparse
import copy
import json
import time

import aspath_sweep as sweep
import control
import hub_transit
import infra
import vpn_sdwan_boundary as boundary


def connection_resources(collections, label=None):
    resources = []
    for site, collection in zip(sweep.SITES, collections):
        previous = None
        for connection in collection["value"]:
            properties = {k: copy.deepcopy(connection["properties"][k]) for k in
                          ("remoteVirtualNetwork", "allowHubToRemoteVnetTransit",
                           "allowRemoteVnetToUseHubVnetGateways", "enableInternetSecurity",
                           "routingConfiguration")
                          if k in connection["properties"]}
            if label is not None:
                properties["routingConfiguration"]["propagatedRouteTables"]["labels"] = [label]
            resource = dict(type="Microsoft.Network/virtualHubs/hubVirtualNetworkConnections",
                            apiVersion="2024-05-01",
                            name=f"hub-{site}/{connection['name']}", properties=properties)
            if previous:
                resource["dependsOn"] = [previous]
            resources.append(resource)
            previous = connection["id"]
    return resources


def vpn_labels(labels, label):
    return sweep.az([
        "network", "vpn-gateway", "connection", "update", "-g", control.RG,
        "--gateway-name", "vpngw-jp", "-n", "conn-dc-jp", "--labels", *labels,
        "--query", "routingConfiguration"
    ], label, mutation=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lease", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--enable-hub-transit", action="store_true")
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
    before, after, states, errors = {}, {}, {}, []
    original, vpn_original, original_hubs = [], None, []
    dirty_vnets = dirty_vpn = dirty_hubs = False
    complete = False
    try:
        before = boundary.invoke_all("baseline")
        if args.enable_hub_transit:
            metadata = sweep.hub_metadata()
            original_hubs = [sweep.hub_resource(metadata[s]["hub"]) for s in sweep.SITES]
        commands = [(["rest", "--method", "get", "--url",
                      sweep.network_url("virtualHubs", f"hub-{s}/hubVirtualNetworkConnections") +
                      "?api-version=2024-05-01"], f"connections-before-{s}") for s in sweep.SITES]
        commands.append((["rest", "--method", "get", "--url",
                          sweep.network_url("vpnGateways", "vpngw-jp/vpnConnections/conn-dc-jp") +
                          "?api-version=2024-05-01", "--query", "properties.routingConfiguration"],
                         "vpn-routing-before"))
        values = sweep.az_batch(commands)
        original = connection_resources(values[:3])
        if len(original) != 5:
            raise RuntimeError("Expected exactly five task-owned VNet connections")
        vpn_original = values[3]["propagatedRouteTables"]["labels"]
        states["before"] = hub_transit.capture("before")
        sweep.reserve_restore(control.guard(True))
        sweep.CURRENT = sweep.OUT / "normalize"
        if args.enable_hub_transit:
            candidate_hubs = copy.deepcopy(original_hubs)
            for resource in candidate_hubs:
                resource["properties"]["allowBranchToBranchTraffic"] = True
            dirty_hubs = True
            sweep.submit(infra.template(candidate_hubs), {"parameters": {}},
                         "enable-canonical-hub-transit", True)
            actual = sweep.hub_metadata()
            if not all(actual[s]["hub"]["properties"].get("allowBranchToBranchTraffic") is True
                       for s in sweep.SITES):
                raise RuntimeError("Per-hub transit was not accepted")
        dirty_vnets = True
        sweep.submit(infra.template(connection_resources(values[:3], "default")),
                     {"parameters": {}}, "normalize-vnet-labels", True)
        dirty_vpn = True
        vpn_labels(["default"], "normalize-vpn-labels")
        sweep.bounded_wait(120)
        states["normalized"] = hub_transit.capture("normalized")
        if not all(len(v) == 2 for v in states["normalized"]["remoteSpokes"].values()):
            raise RuntimeError("All six remote-spoke routes must become visible")
        sweep.CURRENT = sweep.OUT / "closure"
        after = boundary.invoke_all("closure")
        for site in (*sweep.SITES, "cn"):
            if not boundary.same_source(before[site], after[site]):
                raise RuntimeError(f"{site}: original source/protocol closure differs")
        complete = True
        dirty_vnets = dirty_vpn = dirty_hubs = False
    except Exception as exc:
        errors.append(str(exc))
        print(f"PROPAGATION ERROR {exc}", flush=True)
    finally:
        if dirty_vnets or dirty_vpn or dirty_hubs:
            sweep.RESTORING = True
            sweep.RESTORE_DEADLINE = time.monotonic() + 900
            try:
                sweep.CURRENT = sweep.OUT / "restore"
                if dirty_vnets:
                    sweep.submit(infra.template(original), {"parameters": {}},
                                 "restore-vnet-labels", True)
                    dirty_vnets = False
                if dirty_vpn:
                    vpn_labels(vpn_original, "restore-vpn-labels")
                    dirty_vpn = False
                if dirty_hubs:
                    sweep.submit(infra.template(original_hubs), {"parameters": {}},
                                 "restore-canonical-hub-transit", True)
                    actual = sweep.hub_metadata()
                    if any(actual[s]["hub"]["properties"].get("allowBranchToBranchTraffic") !=
                           original_hubs[i]["properties"].get("allowBranchToBranchTraffic")
                           for i, s in enumerate(sweep.SITES)):
                        raise RuntimeError("Original hub transit flags differ")
                    dirty_hubs = False
                states["restore"] = hub_transit.capture("restore")
                if states["restore"] != states["before"]:
                    raise RuntimeError("Restored route visibility differs")
            except Exception as exc:
                errors.append("RESTORE: " + str(exc))
        restored = not dirty_vnets and not dirty_vpn and not dirty_hubs and not any(
            e.startswith("RESTORE:") for e in errors)
        verdict = "PASS" if complete else "INCONCLUSIVE" if restored else "BLOCKED"
        lease = json.loads(control.LEASE.read_text(encoding="utf-8-sig"))
        sweep.CURRENT = sweep.OUT
        sweep.save("repair-verdict.json", dict(
            timestampUtc=sweep.utc(), verdict=verdict,
            correctedBaselineRetained=complete, rollbackVerified=restored if not complete else None,
            states=states, errors=errors, sourceBefore=before, sourceAfter=after,
            callsUsed=lease["toolCallsUsed"], mutationsUsed=lease.get("mutationsUsed", 0),
            children=[], noDataPlaneClaim=True))
        lease.update(state="completed" if complete else "rolled-back" if restored else "blocked",
                     verdict=verdict, completedAtUtc=sweep.utc(), children=[], evidence=str(sweep.OUT))
        control.save(control.LEASE, lease)
        print(f"FINAL {verdict} correctedBaselineRetained={complete}", flush=True)
    if not complete:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
