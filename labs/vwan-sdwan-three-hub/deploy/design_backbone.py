"""Bounded ASPath plus NVA-policy experiment, with exact user-state restoration."""
import argparse
import copy
import hashlib
import json
import time

import aspath_sweep as sweep
import control
import design_comparison as comparison
import design_snapshot as snapshot
import guest
import hrp_comparison as hrp
import infra

BACKUP = "/var/lib/threehub/backbone-design-20261016-baseline.conf"
ROUTE_TABLE = "rt-jp-backbone-design-20261016"
UDR_PREFIXES = ("10.110.0.0/24", "10.120.0.0/24", *guest.SPOKE_PREFIXES)


def policy(text, site):
    if site not in sweep.SITES:
        raise ValueError("Only Azure-facing NVAs participate")
    head, separator, tail = text.partition("protocol bgp azure_0 {")
    if not separator or tail.count("export filter azure_export;") != 2:
        raise ValueError("Expected two existing Azure peers")
    old = "if net ~ [" + ", ".join(guest.SPOKE_PREFIXES) + "] then {"
    allowed = [p for s, p in guest.DC.items() if s != site] + list(guest.SPOKE_PREFIXES)
    if tail.count(old) != 2 or tail.count(f"regional_preference({guest.ASNS[site]});") != 2:
        raise ValueError("Existing Azure import policy differs")
    tail = tail.replace(old, "if net ~ [" + ", ".join(allowed) + "] then {")
    tail = tail.replace(f"regional_preference({guest.ASNS[site]});", "bgp_local_pref = 400;")
    if site == "jp":
        old = '(proto = "own_dc" || proto ~ "mesh_*") then accept;'
        if head.count(old) != 1:
            raise ValueError("Expected original Japan export guard")
        head = head.replace(old, '(proto = "own_dc" || proto ~ "mesh_*") then {\n'
                            f'    if net != {guest.DC[site]} then {{\n'
                            + "      bgp_path.prepend(65013);\n" * 3
                            + "    }\n    accept;\n  }")
    return head + separator + tail


def config_script(before, desired, restore=False):
    expected = before["sha256"] if not restore else hashlib.sha256(desired.encode()).hexdigest()
    target = before["config"] if restore else desired
    return f"""#!/bin/bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
import hashlib,json,os,shutil,subprocess
p=Path('/etc/bird/bird.conf');backup=Path({BACKUP!r})
live_hash=hashlib.sha256(p.read_bytes()).hexdigest()
assert live_hash in {([expected, before["sha256"]] if restore else [expected])!r},'Unexpected live BIRD edit'
if not {restore!r}:
 if backup.exists():assert backup.read_bytes()==p.read_bytes(),'Protected backup differs'
 else:shutil.copy2(p,backup);backup.chmod(0o600)
else:
 if backup.exists():assert backup.read_text()=={before['config']!r},'Protected original backup differs'
 else:assert live_hash=={before['sha256']!r},'Protected original backup missing'
candidate=p.with_name('bird.conf.backbone-next')
candidate.write_text({target!r})
check=subprocess.run(['bird','-p','-c',str(candidate)],text=True,capture_output=True,timeout=30)
assert check.returncode==0,check.stderr
metadata={before['stat']!r}
os.chown(candidate,metadata['uid'],metadata['gid']);candidate.chmod(metadata['mode'])
os.utime(candidate,ns=(metadata['mtimeNs'],metadata['mtimeNs']))
os.replace(candidate,p)
configured=subprocess.run(['birdc','configure'],text=True,capture_output=True,timeout=30)
assert configured.returncode==0 and any(x in configured.stdout for x in ('Reconfigured','Reconfiguration in progress')),configured.stdout+configured.stderr
assert hashlib.sha256(p.read_bytes()).hexdigest()=={hashlib.sha256(target.encode()).hexdigest()!r}
print('BACKBONE_CONFIG_COMPLETE '+json.dumps(dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),restore={restore!r},configure=configured.stdout)))
PY
"""


def configure(site, before, desired, restore=False):
    label = ("restore-" if restore else "apply-") + site
    path = control.RUNTIME / ("backbone-" + label + ".sh")
    path.write_text(config_script(before, desired, restore), encoding="utf-8", newline="\n")
    value = sweep.az(["vm", "run-command", "invoke", "-g", control.RG, "-n", "router-" + site,
                      "--command-id", "RunShellScript", "--scripts", "@" + str(path)],
                     label, mutation=True)
    messages = "\n".join(x.get("message", "") for x in value.get("value", []))
    if "BACKBONE_CONFIG_COMPLETE " not in messages:
        raise RuntimeError("Guest configuration did not complete: " + messages[-1500:])


def route_table(sub):
    return dict(type="Microsoft.Network/routeTables", apiVersion="2024-05-01",
                name=ROUTE_TABLE, location="japaneast", tags=control.TAGS,
                properties=dict(disableBgpRoutePropagation=False, routes=[
                    dict(name="backbone-" + str(i), properties=dict(
                        addressPrefix=p, nextHopType="VirtualAppliance", nextHopIpAddress="10.130.0.4"))
                    for i, p in enumerate(UDR_PREFIXES)]))


def subnet_resource(before, route_id=None):
    properties = copy.deepcopy(before["properties"])
    for key in ("provisioningState", "ipConfigurations", "resourceNavigationLinks",
                "serviceAssociationLinks", "purpose"):
        properties.pop(key, None)
    if route_id:
        properties["routeTable"] = {"id": route_id}
    else:
        properties["routeTable"] = before["properties"].get("routeTable")
    return dict(type="Microsoft.Network/virtualNetworks/subnets", apiVersion="2024-05-01",
                name="vnet-dc-jp/workload", properties=properties)


def capture(label, expected):
    sweep.CURRENT = sweep.OUT / label
    hubs = snapshot.metadata(label)
    if any(h["preference"] != "ASPath" for h in hubs.values()):
        raise RuntimeError("All three HRPs must be ASPath")
    sources = snapshot.nvas(label + "-source", source=True)
    if any(sources[s]["sha256"] != expected[s] for s in snapshot.ALL_SITES):
        raise RuntimeError("Applied NVA policy differs")
    firewalls = snapshot.firewall_routes(label, hubs)
    nvas = snapshot.nvas(label + "-routes")
    selected = {s: [comparison.selected_route(nvas[s]["birdRoutes"]["stdout"], p)
                    for p in (*comparison.guest_prefixes(), *guest.SPOKE_PREFIXES)]
                for s in snapshot.ALL_SITES}
    sweep.save("selected-routes.json", selected)
    traffic = snapshot.traffic(label)
    signals = {}
    for site, prefix in (("eu", guest.DC["jp"]), ("us", guest.DC["jp"]), ("jp", guest.DC["eu"])):
        row = next(r for r in selected[site] if r["prefix"] == prefix)
        signals[site + "-to-" + prefix] = row["protocol"].startswith("azure_") and row["localPreference"] == 400
    result = dict(hubs=hubs, sources=sources, firewalls=firewalls, nvas=nvas,
                  selected=selected, traffic=traffic, backboneSelections=signals)
    sweep.save("scenario-result.json", result)
    print("OBSERVATION " + label + " " + json.dumps(dict(backboneSelections=signals, traffic=traffic)), flush=True)
    if not all(signals.values()):
        raise RuntimeError("Required bidirectional EU/Japan and US-to-Japan Azure selections not observed")
    return result


def main():
    parser = argparse.ArgumentParser()
    for name in ("lease", "out", "baseline"):
        parser.add_argument("--" + name, required=True)
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
        raise RuntimeError("Accepted baseline required")
    before = baseline["result"]
    desired = {s: policy(before["sources"][s]["config"], s) for s in sweep.SITES}
    expected = {s: hashlib.sha256(desired[s].encode()).hexdigest() if s in desired
                else before["sources"][s]["sha256"] for s in snapshot.ALL_SITES}
    dirty_guests, dirty_hubs, dirty_subnet, created_table = [], False, False, False
    states, errors = {}, []
    subnet = None
    try:
        actual = snapshot.metadata("before")
        if any(actual[s]["preference"] != before["hubs"][s]["preference"] for s in sweep.SITES):
            raise RuntimeError("Original HRPs changed")
        subnet = sweep.az(["rest", "--method", "get", "--url",
                          sweep.network_url("virtualNetworks", "vnet-dc-jp/subnets/workload") +
                          "?api-version=2024-05-01"], "original-jp-subnet")
        if subnet["properties"].get("routeTable"):
            raise RuntimeError("Japan subnet already has a route table; refusing overwrite")
        tables = sweep.az(["network", "route-table", "list", "-g", control.RG], "existing-route-tables")
        if any(t["name"] == ROUTE_TABLE for t in tables):
            raise RuntimeError("Experiment route table already exists")
        sweep.reserve_restore(control.guard(True))
        dirty_hubs = True
        hrp.set_preference("ASPath", "backbone-aspath")
        for site in sweep.SITES:
            dirty_guests.append(site)
            configure(site, before["sources"][site], desired[site])
        states["nva-policy-only"] = capture("nva-policy-only", expected)
        sweep.reserve_restore(control.guard(True))
        sweep.CURRENT = sweep.OUT / "jp-workload-udr"
        table = route_table(sweep.SUB)
        route_id = sweep.network_url("routeTables", ROUTE_TABLE).replace("https://management.azure.com", "")
        resource = subnet_resource(subnet, route_id)
        resource["dependsOn"] = [f"[resourceId('Microsoft.Network/routeTables', '{ROUTE_TABLE}')]"]
        created_table = dirty_subnet = True
        sweep.submit(infra.template([table, resource]), {"parameters": {}}, "jp-workload-udr", mutation=True)
        states["nva-policy-and-jp-udr"] = capture("nva-policy-and-jp-udr", expected)
    except Exception as exc:
        errors.append(str(exc))
        print("BACKBONE ERROR " + str(exc), flush=True)
    finally:
        sweep.RESTORING = True
        sweep.RESTORE_DEADLINE = time.monotonic() + lease["restoreTimeoutMinutes"] * 60
        sweep.CURRENT = sweep.OUT / "restore"
        try:
            if dirty_subnet:
                sweep.submit(infra.template([subnet_resource(subnet)]), {"parameters": {}},
                             "restore-original-jp-subnet", mutation=True)
                dirty_subnet = False
            for site in reversed(dirty_guests.copy()):
                configure(site, before["sources"][site], desired[site], restore=True)
                dirty_guests.remove(site)
            if dirty_hubs:
                sweep.submit(infra.template(comparison.original_hubs(before["hubs"])),
                             {"parameters": {}}, "restore-user-mixed-hrps", mutation=True)
                dirty_hubs = False
            if created_table:
                sweep.az(["network", "route-table", "delete", "-g", control.RG, "-n", ROUTE_TABLE],
                         "delete-only-created-route-table", mutation=True)
                created_table = False
            sources = snapshot.nvas("restore-source", source=True)
            hubs = snapshot.metadata("restore")
            firewalls = snapshot.firewall_routes("restore", hubs)
            if any(not comparison.source_unchanged(before["sources"][s], sources[s]) for s in snapshot.ALL_SITES):
                raise RuntimeError("Exact original BIRD source, metadata or peers differ")
            if any(hubs[s]["preference"] != before["hubs"][s]["preference"] for s in sweep.SITES):
                raise RuntimeError("Original mixed HRPs differ")
            if firewalls["rows"] != before["firewalls"]["rows"]:
                raise RuntimeError("Original paired firewall winners differ")
            if subnet:
                actual = sweep.az(["rest", "--method", "get", "--url",
                                  sweep.network_url("virtualNetworks", "vnet-dc-jp/subnets/workload") +
                                  "?api-version=2024-05-01"], "verify-original-subnet")
                if actual["properties"].get("routeTable") != subnet["properties"].get("routeTable"):
                    raise RuntimeError("Original Japan subnet association differs")
            states["restore"] = dict(sources=sources, hubs=hubs, firewalls=firewalls)
        except Exception as exc:
            errors.append("RESTORE: " + str(exc))
        restored = "restore" in states and not (dirty_guests or dirty_hubs or dirty_subnet or created_table)
        verdict = "PASS" if restored and not errors and len(states) == 3 else "INCONCLUSIVE" if restored else "BLOCKED"
        sweep.CURRENT = sweep.OUT
        sweep.save("backbone-verdict.json", dict(verdict=verdict, restored=restored, errors=errors,
                   timestampUtc=sweep.utc(), states=states,
                   pending=dict(guests=dirty_guests, hubs=dirty_hubs, subnet=dirty_subnet, table=created_table),
                   interpretation="PASS proves measured control-plane selections and exact restore; traffic cells retain their own outcomes"))
        lease = json.loads(control.LEASE.read_text())
        lease.update(state="completed" if verdict == "PASS" else "rolled-back" if restored else "blocked",
                     verdict=verdict, completedAtUtc=sweep.utc(), children=[])
        control.save(control.LEASE, lease)
        print(f"FINAL {verdict} backbone experiment restored={restored}", flush=True)
    if verdict != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
