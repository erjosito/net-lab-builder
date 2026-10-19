"""Test HRP updates followed by Azure-facing BGP resets, preserving mesh/IPsec."""
import argparse
import datetime as dt
import json
import re
import time

import aspath_sweep as sweep
import control
import design_b2b as b2b
import design_b2_diagnosis as diagnosis
import design_backbone as backbone
import design_comparison as comparison
import design_hrp_reselection as reselection
import design_snapshot as snapshot
import effective_routes
import infra

CORRELATION = "hrp-bgp-reset-20261019"
ORDERS = {"japan-first": ("jp", "eu", "us"), "nva-first": ("eu", "us", "jp")}


def session_script(site, action="inspect"):
    if site not in sweep.SITES or action not in ("inspect", "disable", "enable"):
        raise ValueError("Only known Azure-facing protocols may be controlled")
    body = f"""
import hashlib
site={site!r};action={action!r}
def run(args):
 p=subprocess.run(args,text=True,capture_output=True,timeout=30)
 assert p.returncode==0,p.stderr
 return p.stdout
def protocols():
 text=run(['birdc','show','protocols'])
 rows={{}}
 for line in text.splitlines():
  f=line.split()
  if f and f[0].startswith(('mesh_','azure_')):
   rows[f[0]]=dict(state=f[3],since=f[4],info=' '.join(f[5:]))
 return dict(rows=rows,raw=text)
before=protocols();actions=[]
assert len([p for p in before['rows'] if p.startswith('mesh_')])==3
assert all(v['info']=='Established' for k,v in before['rows'].items() if k.startswith('mesh_'))
if action!='inspect':
 for peer in ('azure_0','azure_1'):
  text=run(['birdc',action,peer])
  assert action+'d' in text.lower(),text
  actions.append(dict(peer=peer,output=text))
for attempt in range(91):
 after=protocols()
 azure=[after['rows'].get(p,{{}}) for p in ('azure_0','azure_1')]
 ready=all(p.get('state')=='down' for p in azure) if action=='disable' else all(p.get('info')=='Established' for p in azure)
 if ready:break
 if attempt<90:time.sleep(2)
assert ready,after
assert all(v['info']=='Established' for k,v in after['rows'].items() if k.startswith('mesh_'))
p=pathlib.Path('/etc/bird/bird.conf');s=p.stat()
result=dict(timestampUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
 action=action,before=before,after=after,actions=actions,
 birdPid=int(run(['systemctl','show','bird','--property=MainPID','--value']).strip()),
 sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
 stat=dict(uid=s.st_uid,gid=s.st_gid,mode=s.st_mode&0o777,mtimeNs=s.st_mtime_ns))
if site=='jp':
 text=run(['swanctl','--list-sas'])
 assert len(re.findall('ESTABLISHED',text))==2,text
 result['ipsecStatus']=text
 result['ipsecConfigurationSha256']=hashlib.sha256(pathlib.Path('/etc/swanctl/swanctl.conf').read_bytes()).hexdigest()
"""
    return b2b.python_script(body, "HRP_RESET")


def sessions(label, action="inspect", sites=sweep.SITES):
    results = {}
    for site in sites:
        path = control.RUNTIME / f"{CORRELATION}-{label}-{site}.sh"
        path.write_text(session_script(site, action), encoding="utf-8", newline="\n")
        value = sweep.az(["vm", "run-command", "invoke", "-g", control.RG, "-n", "router-" + site,
                          "--command-id", "RunShellScript", "--scripts", "@" + str(path)],
                         label + "-" + site, mutation=action != "inspect")
        results[site] = b2b.unpack(value, "HRP_RESET")
    sweep.save(label + "-sessions.json", results)
    return results


def assert_transport_unchanged(before, after):
    for site in sweep.SITES:
        a, b = before[site], after[site]
        if any(a[key] != b[key] for key in ("birdPid", "sha256", "stat")):
            raise RuntimeError("BIRD process or exact configuration changed: " + site)
        for peer, state in a["after"]["rows"].items():
            if not peer.startswith("mesh_"):
                continue
            actual = b["after"]["rows"][peer]
            if state["info"] != actual["info"] or actual["info"] != "Established":
                raise RuntimeError("Mesh BGP health changed: " + site + "/" + peer)
            old = dt.datetime.strptime(state["since"], "%H:%M:%S.%f")
            new = dt.datetime.strptime(actual["since"], "%H:%M:%S.%f")
            if abs((old - new).total_seconds()) > 0.025:
                raise RuntimeError("Mesh BGP establishment time changed: " + site + "/" + peer)
    if before["jp"]["ipsecConfigurationSha256"] != after["jp"]["ipsecConfigurationSha256"]:
        raise RuntimeError("IPsec configuration changed")


def capture(label, expected, preference, traffic=False):
    sweep.CURRENT = sweep.OUT / label
    hubs = snapshot.metadata(label)
    if any(h["preference"] != preference or
           h["hub"]["properties"].get("allowBranchToBranchTraffic") is not True for h in hubs.values()):
        raise RuntimeError("Expected all-hub HRP/B2B policy differs")
    sources = snapshot.nvas(label + "-source", True)
    if any(not comparison.source_unchanged(expected[s], sources[s]) for s in snapshot.ALL_SITES):
        raise RuntimeError("Original BIRD configuration/metadata/peer state differs")
    nvas = snapshot.nvas(label + "-routes")
    firewalls = reselection.firewall_capture(label, hubs, complete=False)
    selected = {s: [comparison.selected_route(nvas[s]["birdRoutes"]["stdout"], prefix)
                    for prefix in (*comparison.guest_prefixes(), *infra.SPOKE_PREFIXES)]
                for s in snapshot.ALL_SITES}
    result = dict(hubs=hubs, sources=sources, nvas=nvas, firewalls=firewalls, selected=selected)
    sweep.save("selected-routes.json", selected)
    if traffic:
        result["traffic"] = b2b.traffic(label, dc_azure_only=True)
        result["workload"] = diagnosis.workload_evidence(label)
    sweep.save("scenario-result.json", result)
    print("MEASURED " + label + " " + json.dumps(reselection.japan_winners(result)), flush=True)
    return result


def firewall_now(label, hubs):
    values = sweep.az_batch([
        (effective_routes.arguments(sweep.SUB, control.RG, site,
         firewall_id=hubs[site]["firewallId"]), label + "-" + site)
        for site in sweep.SITES])
    return [row for site, value in zip(sweep.SITES, values) for row in sweep.normalize(value, site)]


def confirm_all_withdrawn(hubs):
    for attempt in range(7):
        rows = firewall_now("all-down-" + str(attempt), hubs)
        sweep.save("all-down-winners-" + str(attempt) + ".json", rows)
        if not rows:
            return
        if attempt < 6:
            sweep.bounded_wait(30)
    raise RuntimeError("DC-prefix routes did not withdraw with all six Azure BGP sessions down")


def experiment(before, preference, order):
    states, errors = {}, []
    hub_dirty, subnet_dirty, table_created = False, False, False
    sessions_dirty, subnet = False, None
    backbone.ROUTE_TABLE = CORRELATION + "-" + preference.lower() + "-" + order
    backbone.UDR_PREFIXES = tuple(infra.SPOKE_PREFIXES)
    try:
        sweep.CURRENT = sweep.OUT / "prepare"
        transport = sessions("original")
        subnet = sweep.az(["rest", "--method", "get", "--url",
                          sweep.network_url("virtualNetworks", "vnet-dc-jp/subnets/workload") +
                          "?api-version=2024-05-01"], "original-jp-subnet")
        if subnet["properties"].get("routeTable"):
            raise RuntimeError("Existing Japan route table; refusing overwrite")
        tables = sweep.az(["network", "route-table", "list", "-g", control.RG], "existing-tables")
        if any(t["name"] == backbone.ROUTE_TABLE for t in tables):
            raise RuntimeError("Temporary route table already exists")
        route_id = sweep.network_url("routeTables", backbone.ROUTE_TABLE).replace(
            "https://management.azure.com", "")
        resource = backbone.subnet_resource(subnet, route_id)
        resource["dependsOn"] = [f"[resourceId('Microsoft.Network/routeTables', '{backbone.ROUTE_TABLE}')]"]
        subnet_dirty = table_created = True
        sweep.submit(infra.template([backbone.route_table(sweep.SUB), resource]),
                     {"parameters": {}}, CORRELATION + "-workload-udr", True)
        sweep.reserve_restore(control.guard(True))
        hub_dirty = True
        b2b.set_hubs(before["hubs"], "ASPath", True, "seed-aspath")
        states["ASPath-seed"] = capture("ASPath-seed", before["sources"], "ASPath")
        if any(row["nextHopType"] != "Remote Hub" for row in
               reselection.japan_winners(states["ASPath-seed"]).values()):
            raise RuntimeError("Initial remote Japan route history not established")
        b2b.set_hubs(before["hubs"], preference, True, "target-hrp")
        states["HRP-only"] = capture("HRP-only", before["sources"], preference)
        sweep.reserve_restore(control.guard(True))
        sweep.CURRENT = sweep.OUT / "bgp-reset"
        sessions_dirty = True
        states["all-disabled"] = sessions("disable-all", "disable")
        confirm_all_withdrawn(states["HRP-only"]["hubs"])
        enabled = {}
        for index, site in enumerate(ORDERS[order]):
            enabled.update(sessions("enable-" + str(index), "enable", (site,)))
            if index == 0:
                sweep.bounded_wait(30)
                sweep.save("first-advertiser-winners.json",
                           firewall_now("first-advertiser", states["HRP-only"]["hubs"]))
        sessions_dirty = False
        assert_transport_unchanged(transport, enabled)
        sweep.save("transport-invariants.json", dict(before=transport, after=enabled,
                   verdict="PASS", interpretation="BIRD PID, exact sources/metadata, mesh establishment "
                   "times and IPsec configuration unchanged; both IPsec IKE SAs established at checks."))
        states["after-reset"] = capture("after-reset", before["sources"], preference, traffic=True)
        states["outcome"] = dict(localJapan=reselection.local_japan(states["after-reset"]),
                                preference=preference, enableOrder=ORDERS[order],
                                traffic=states["after-reset"]["traffic"])
    except Exception as exc:
        errors.append(str(exc))
        print("RESET CONTROL ERROR " + str(exc), flush=True)
    finally:
        sweep.RESTORING, sweep.RESTORE_DEADLINE = True, time.monotonic() + 25 * 60
        sweep.CURRENT = sweep.OUT / "restore"
        try:
            if sessions_dirty:
                sessions("restore-all-azure", "enable")
                sessions_dirty = False
            if subnet_dirty:
                sweep.submit(infra.template([backbone.subnet_resource(subnet)]),
                             {"parameters": {}}, CORRELATION + "-restore-subnet", True)
                subnet_dirty = False
            if table_created:
                sweep.az(["network", "route-table", "delete", "-g", control.RG,
                          "-n", backbone.ROUTE_TABLE], "delete-only-created-route-table", True)
                table_created = False
            if hub_dirty:
                b2b.set_hubs(before["hubs"], label="restore-original")
                hub_dirty = False
            sources = snapshot.nvas("restore-source", True)
            hubs = snapshot.metadata("restore")
            firewalls = reselection.firewall_capture("restore", hubs, complete=False)
            if any(not comparison.source_unchanged(before["sources"][s], sources[s])
                   for s in snapshot.ALL_SITES):
                raise RuntimeError("Exact original BIRD sources/metadata/peers not restored")
            if firewalls["rows"] != before["firewalls"]["rows"]:
                raise RuntimeError("Original firewall winners not restored")
            for site in sweep.SITES:
                a, b = hubs[site], before["hubs"][site]
                if (a["preference"], a["hub"]["properties"]["allowBranchToBranchTraffic"]) != (
                        b["preference"], b["hub"]["properties"]["allowBranchToBranchTraffic"]):
                    raise RuntimeError("Original HRP/branch flag not restored")
            actual = diagnosis.workload_evidence("restore")
            if actual["subnet"]["properties"].get("routeTable") != before["workload"]["subnet"]["properties"].get("routeTable"):
                raise RuntimeError("Original subnet route table association not restored")
            states["restore"] = dict(sources=sources, hubs=hubs, firewalls=firewalls, workload=actual)
        except Exception as exc:
            errors.append("RESTORE: " + str(exc))
        restored = "restore" in states and not (sessions_dirty or hub_dirty or subnet_dirty or table_created)
        verdict = "PASS" if restored and not errors and "outcome" in states else "INCONCLUSIVE" if restored else "BLOCKED"
        sweep.CURRENT = sweep.OUT
        sweep.save("reset-verdict.json", dict(verdict=verdict, restored=restored, states=states,
                   errors=errors, timestampUtc=sweep.utc(),
                   pending=dict(sessions=sessions_dirty, hubs=hub_dirty, subnet=subnet_dirty, table=table_created),
                   interpretation="PASS means complete measured reset and exact restore, not that local routing/traffic passed"))
        lease = json.loads(control.LEASE.read_text())
        lease.update(state="completed" if verdict == "PASS" else "rolled-back" if restored else "blocked",
                     completedAtUtc=sweep.utc(), verdict=verdict)
        control.save(control.LEASE, lease)
        print(f"FINAL {verdict} reset control restored={restored}", flush=True)
    if verdict != "PASS":
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--preference", choices=("ExpressRoute", "VpnGateway"), required=True)
    parser.add_argument("--order", choices=tuple(ORDERS), required=True)
    args = parser.parse_args()
    sweep.SUB = control.account_id()
    sweep.OUT = control.ROOT.parent / "show-output" / args.out
    sweep.CURRENT = sweep.OUT
    control.LEASE = control.RUNTIME / (args.out + ".json")
    if sweep.OUT.exists() or control.LEASE.exists():
        raise RuntimeError("Fresh evidence directory and lease required")
    now = dt.datetime.now(dt.timezone.utc)
    control.save(control.LEASE, dict(taskId=args.out, ownerRole="Oracle",
                 objective="HRP change and BGP-only reset " + args.preference + "/" + args.order,
                 startedAtUtc=now.isoformat(), expiresAtUtc=(now + dt.timedelta(minutes=120)).isoformat(),
                 maxToolCalls=250, maxMutations=24, commandTimeoutSeconds=600,
                 restoreTimeoutMinutes=25, state="active", toolCallsUsed=0, mutationsUsed=0))
    sweep.RESTORING, sweep.RESTORE_DEADLINE, b2b.CORRELATION = False, None, CORRELATION
    control.guard(True)
    before = b2b.read_evidence(args.baseline, "baseline-verdict.json")["result"]
    experiment(before, args.preference, args.order)


if __name__ == "__main__":
    main()
