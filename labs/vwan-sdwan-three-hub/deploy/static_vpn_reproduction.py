"""Bounded secured static-VPN versus unreachable local peered-BGP comparison."""
import argparse
import json
import pathlib
import re
import time

import aspath_sweep as sweep
import control
import effective_routes
import forwarding_matrix
import guest
import vpn_sdwan_boundary as boundary

TARGET = "10.130.0.100/32"
ADDRESS = TARGET.split("/")[0]
SOURCE_PROBES = {"eu": "10.10.0.10", "jp": "10.30.0.10"}


def config_changes(site, prepends=0):
    if site == "jp":
        return [], """
protocol static ri_static_spokes {
  ipv4 { table lab4; };
""" + "".join(f'  route {prefix} via "xfrm41";\n'
              for prefix in guest.SPOKE_PREFIXES) + "}\n"
    if site != "eu" or prepends not in (0, 3):
        raise ValueError("Only Japan static routes and Europe zero/three prepends are supported")
    injection = (f"filter azure_export {{\n  if net = {TARGET} then {{\n" +
                 f"    bgp_path.prepend({guest.ASNS['eu']});\n" * prepends +
                 "    accept;\n  }\n")
    return [("filter azure_export {\n", injection),
            ("    export filter {\n",
             f"    export filter {{\n      if net = {TARGET} then accept;\n")], f"""
protocol static ri_unreachable_target {{
  ipv4 {{ table lab4; }};
  route {TARGET} blackhole;
}}
"""


def guest_script(site, baseline, prepends=0, restore=False):
    replacements, addition = config_changes(site, prepends)
    return f"""#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import hashlib,json,os,re,subprocess,time
from pathlib import Path
def run(args):
 r=subprocess.run(args,text=True,capture_output=True,timeout=30)
 if r.returncode: raise RuntimeError(r.stderr or r.stdout)
 return r.stdout
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def metadata(p):
 s=p.stat()
 return dict(uid=s.st_uid,gid=s.st_gid,mode=s.st_mode&0o777,mtimeNs=s.st_mtime_ns)
p=Path('/etc/bird/bird.conf')
b=Path('/var/lib/threehub/static-vpn-reproduction-{site}-baseline.conf')
original_sha={baseline['sha256']!r}
original_stat={baseline['stat']!r}
addresses=json.loads(run(['ip','-j','address','show','dev','lo']))
present=any(a.get('local')=={ADDRESS!r} for x in addresses for a in x['addr_info'])
if {site=='jp'!r} and not {restore!r}:assert not present,'Synthetic target already exists'
if not b.exists():
 assert not {restore!r}, 'Missing restore backup'
 assert digest(p)==original_sha and metadata(p)==original_stat
 assert not present, 'Target address already exists'
 b.write_bytes(p.read_bytes())
 os.chown(b,original_stat['uid'],original_stat['gid'])
 os.chmod(b,original_stat['mode'])
 os.utime(b,ns=(b.stat().st_atime_ns,original_stat['mtimeNs']))
assert digest(b)==original_sha and metadata(b)==original_stat
original=b.read_text()
candidate=b.read_bytes()
if not {restore!r}:
 if {site=='eu'!r}:
  assert original.count({sweep.FILTER!r})==1
 candidate=original
 for search,replacement in {replacements!r}:
  assert candidate.count(search)==1, 'Expected unique original export filter'
  candidate=candidate.replace(search,replacement,1)
 candidate=(candidate+{addition!r}).encode()
n=Path('/etc/bird/bird.conf.static-vpn-next')
assert not n.exists()
try:
 n.write_bytes(candidate)
 os.chown(n,original_stat['uid'],original_stat['gid']);os.chmod(n,original_stat['mode'])
 os.utime(n,ns=(b.stat().st_atime_ns,original_stat['mtimeNs']))
 run(['bird','-p','-c',str(n)])
 if {site=='jp'!r} and not {restore!r} and not present:
  run(['ip','address','add',{TARGET!r},'dev','lo'])
 os.replace(n,p)
 if {restore!r} and {site=='jp'!r} and present:
  run(['ip','address','del',{TARGET!r},'dev','lo'])
 configured=run(['birdc','configure'])
 assert re.search(r'^(Reconfigured|Reconfiguration in progress)\\s*$',configured,re.M),configured
 deadline=time.monotonic()+120
 while True:
  protocol_text=run(['birdc','show','protocols'])
  protocol_name={'ri_static_spokes' if site == 'jp' else 'ri_unreachable_target'!r}
  protocol_present=bool(re.search(r'^'+protocol_name+r'\\s',protocol_text,re.M))
  if protocol_present != {restore!r}:break
  assert time.monotonic()<deadline,'BIRD configuration did not converge'
  time.sleep(2)
 if {restore!r}:
  assert digest(p)==original_sha and metadata(p)==original_stat
finally:
 if n.exists():n.unlink()
time.sleep(2)
exports={{}}
for peer in ('azure_0','azure_1'):
 routes={{}};prefix=None
 for line in run(['birdc','show','route','export',peer,'all']).splitlines():
  match=re.match(r'(\\d+\\.\\d+\\.\\d+\\.\\d+/\\d+)\\s',line)
  if match:
   prefix=match.group(1)
   if prefix=={TARGET!r}:routes[prefix]=[]
  if prefix=={TARGET!r} and 'BGP.as_path:' in line:
   routes[prefix]=[int(x) for x in line.split('BGP.as_path:',1)[1].split()]
 exports[peer]=routes
ike=len(re.findall('ESTABLISHED',run(['swanctl','--list-sas']))) if {site=='jp'!r} else None
if {site=='jp'!r}:assert ike==2,'Both original IKE SAs required'
protocols={{}}
for line in run(['birdc','show','protocols']).splitlines():
 if re.match(r'(mesh_|azure_)',line):
  fields=line.split();protocols[fields[0]]=fields[5] if len(fields)>5 else 'Unknown'
assert len([p for p,s in protocols.items() if p.startswith('mesh_') and s=='Established'])==3
if {site=='eu'!r}:assert len(protocols)==5 and set(protocols.values())=={{'Established'}}
addresses=json.loads(run(['ip','-j','address','show','dev','lo']))
present=any(a.get('local')=={ADDRESS!r} for x in addresses for a in x['addr_info'])
routes=[r for r in json.loads(run(['ip','-j','route','show']))
 if r.get('dst') in {([TARGET] + guest.SPOKE_PREFIXES)!r}]
payload=json.dumps(dict(site={site!r},sha256=digest(p),stat=metadata(p),
 configureOutput=configured,exports=exports,protocols=protocols,
 ikeEstablished=ike,targetAddressPresent=present,routes=routes,restored={restore!r}),separators=(',',':'))
assert len(payload.encode())<3500,'Run Command proof exceeds safe output bound'
print('STATIC_VPN_COMPLETE '+payload)
PY
"""


def completed(value, marker):
    messages = "\n".join(v.get("message", "") for v in value.get("value", []))
    matches = re.findall(r"^" + re.escape(marker) + r" (\{.*\})$", messages, re.M)
    if len(matches) != 1:
        raise RuntimeError(f"{marker}: explicit complete guest output missing: {messages[-1000:]}")
    return json.loads(matches[0])


def mutate_guest(site, baseline, label, prepends=0, restore=False):
    path = control.RUNTIME / f"static-vpn-{site}-{label}.sh"
    path.write_text(guest_script(site, baseline, prepends, restore),
                    encoding="utf-8", newline="\n")
    value = sweep.az(["vm", "run-command", "invoke", "-g", control.RG,
                      "-n", "router-" + site, "--command-id", "RunShellScript",
                      "--scripts", "@" + str(path)], label, mutation=True)
    result = completed(value, "STATIC_VPN_COMPLETE")
    sweep.save(label + "-proof.json", result)
    if restore:
        if result["sha256"] != baseline["sha256"] or result["stat"] != baseline["stat"]:
            raise RuntimeError("Guest original bytes/metadata not restored")
        if site == "jp" and result["targetAddressPresent"]:
            raise RuntimeError("Synthetic loopback address not removed")
    elif site == "eu":
        validate_injection(result, prepends)
    elif (not result["targetAddressPresent"] or
          {r.get("dst") for r in result["routes"] if r.get("dev") == "xfrm41"} !=
          set(guest.SPOKE_PREFIXES)):
        raise RuntimeError("Japan target address or actual static VPN return routes missing")
    return result


def validate_injection(result, prepends):
    if not any(r.get("dst") == TARGET and r.get("type") == "blackhole" for r in result["routes"]):
        raise RuntimeError("Target blackhole not installed in actual kernel FIB")
    if set(result["exports"]) != {"azure_0", "azure_1"}:
        raise RuntimeError("Both actual Azure exports required")
    for routes in result["exports"].values():
        if routes != {TARGET: [guest.ASNS["eu"]] * prepends}:
            raise RuntimeError("Actual target export AS path differs from requested prepends")


def read_settings(label):
    return sweep.az_batch([
        (["rest", "--method", "get", "--url",
          sweep.network_url("vpnSites", "site-dc-jp") + "?api-version=2024-05-01",
          "--query", "properties.addressSpace"], label + "-site"),
        (["rest", "--method", "get", "--url",
          sweep.network_url("vpnGateways", "vpngw-jp/vpnConnections/conn-dc-jp") +
          "?api-version=2024-05-01", "--query",
          "properties.{links:vpnLinkConnections[].{name:name,bgp:properties.enableBgp,"
          "policies:properties.ipsecPolicies,customBgp:properties.vpnGatewayCustomBgpAddresses},"
          "routing:routingConfiguration}"], label + "-connection")
    ])


def set_bgp(enabled, label):
    sweep.az(["network", "vpn-gateway", "connection", "update", "-g", control.RG,
              "--gateway-name", "vpngw-jp", "-n", "conn-dc-jp", "--set",
              "vpnLinkConnections[0].enableBgp=" + str(enabled).lower(),
              "--query", "vpnLinkConnections[].{name:name,bgp:enableBgp}"],
             label, mutation=True)


def target_rows(value, site):
    return [dict(observer=site, prefix=TARGET, asPath=e.get("asPath"),
                 origin=e.get("routeOrigin"), nextHopType=e.get("nextHopType"),
                 nextHops=e.get("nextHops"))
            for e in value["value"] if TARGET in e.get("addressPrefixes", [])]


def is_remote_vpn(row):
    identity = json.dumps([row.get("origin"), row.get("nextHops")]).lower()
    return ("/vpngw-jp" in identity or
            (row.get("nextHopType") == "Remote Hub" and "/virtualhubs/hub-jp" in identity))


def require_target_absent(directory):
    for site in sweep.SITES:
        for number in (1, 2):
            value = json.loads((directory / f"effective-{site}-snapshot{number}.json").read_text())
            if target_rows(value["result"], site):
                raise RuntimeError("Synthetic target unexpectedly remains in firewall routes")


def collect_target(label):
    sweep.CURRENT = sweep.OUT / label
    sweep.hub_metadata("ExpressRoute", True)

    def snapshot(number):
        commands = [(effective_routes.arguments(
            sweep.SUB, control.RG, site, firewall_id=(
                f"/subscriptions/{sweep.SUB}/resourceGroups/{control.RG}"
                f"/providers/Microsoft.Network/azureFirewalls/fw-{site}")),
            f"{label}-{site}-{number}") for site in sweep.SITES]
        values = sweep.az_batch(commands)
        rows = []
        for site, value in zip(sweep.SITES, values):
            if not isinstance(value, dict) or not isinstance(value.get("value"), list):
                raise RuntimeError("Completed firewall route response required")
            rows.extend(target_rows(value, site))
        sweep.save(f"target-snapshot{number}.json", rows)
        return rows
    first, second = effective_routes.two_snapshots(snapshot, wait=sweep.bounded_wait)
    result = dict(stable=first == second, rows=second,
                  complete=len(second) == 3 and {r["observer"] for r in second} == set(sweep.SITES))
    sweep.save("target-analysis.json", result)
    return result


def probe_target(label):
    commands = []
    for site, source in SOURCE_PROBES.items():
        path = control.RUNTIME / f"static-vpn-probe-{site}.sh"
        path.write_text(forwarding_matrix.script(source, [ADDRESS]),
                        encoding="utf-8", newline="\n")
        commands.append((["vm", "run-command", "invoke", "-g", control.RG,
                          "-n", "probe-spoke-" + site, "--command-id", "RunShellScript",
                          "--scripts", "@" + str(path)], label + "-probe-" + site))
    values = sweep.az_batch(commands)
    cells = []
    for (site, source), value in zip(SOURCE_PROBES.items(), values):
        result = completed(value, "FORWARDING_COMPLETE")
        actual = result["cells"]
        if len(actual) != 1 or actual[0]["source"] != source or actual[0]["destination"] != ADDRESS:
            raise RuntimeError("Incomplete or unexpected target probe")
        cells.extend(actual)
    sweep.save(label + "-traffic.json", cells)
    return cells


def summarize(results):
    summary = []
    for prepends in (0, 3):
        result = results.get(f"unreachable-local-add{prepends}")
        if not result or "traffic" not in result:
            continue
        rows = [r for r in result["routes"]["rows"] if r["observer"] == "eu"]
        eu = [c for c in result["traffic"] if c["source"] == SOURCE_PROBES["eu"]]
        jp = [c for c in result["traffic"] if c["source"] == SOURCE_PROBES["jp"]]
        summary.append(dict(
            additionalPrepends=prepends, advertisedWireAsPath=result["advertisedWireAsPath"],
            euWinner=rows[0] if len(rows) == 1 else None,
            euTraffic=eu[0] if len(eu) == 1 else None,
            jpControlTraffic=jp[0] if len(jp) == 1 else None,
            localSelected=(len(rows) == 1 and rows[0]["nextHopType"] == "HubBgpConnection"),
            limitation="Bounded observations, not proof of unconditional local preference"))
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lease", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--baseline-proof", required=True)
    args = parser.parse_args()
    control.LEASE = control.RUNTIME / args.lease
    lease = control.guard(True)
    if lease.get("toolCallsUsed", 0) or lease.get("mutationsUsed", 0):
        raise RuntimeError("Fresh bounded mutation lease required")
    sweep.SUB = control.account_id()
    sweep.OUT = control.ROOT.parent / "show-output" / args.out
    if sweep.OUT.exists():
        raise RuntimeError("Fresh evidence directory required")
    verified = json.loads(pathlib.Path(args.baseline_proof).read_text())
    if verified.get("verdict") != "PASS" or not verified.get("baselineVerified"):
        raise RuntimeError("Independently accepted baseline proof required")
    sweep.CURRENT = sweep.OUT / "preflight"
    before, settings, baseline, results, errors = {}, None, None, {}, []
    dirty = set()
    restored = False
    try:
        tags = sweep.az(["group", "show", "-n", control.RG, "--query", "tags"], "ownership")
        if any(tags.get(k) != v for k, v in control.TAGS.items()):
            raise RuntimeError("Task resource-group ownership tags differ")
        sweep.hub_metadata("ExpressRoute", True)
        before = boundary.invoke_all("static-vpn-before")
        if any(not boundary.same_source(verified["sourceProofs"][s], before[s]) for s in before):
            raise RuntimeError("Original independent source baseline differs")
        boundary.BASE.update(before)
        settings = read_settings("before")
        if settings[1]["links"] != [dict(settings[1]["links"][0], name="link-jp", bgp=True)]:
            raise RuntimeError("Exactly one original BGP-enabled link-jp required")
        if settings[0] is not None:
            raise RuntimeError("Original VPN site unexpectedly has static address space")
        firewall_ids = {s: (f"/subscriptions/{sweep.SUB}/resourceGroups/{control.RG}"
                           f"/providers/Microsoft.Network/azureFirewalls/fw-{s}") for s in sweep.SITES}
        baseline = sweep.capture("original-baseline", 0, preference="ExpressRoute",
                                 firewall_ids=firewall_ids, parallel=True)
        if baseline["verdict"] != "PASS":
            raise RuntimeError("Original twelve-winner baseline incomplete")
        require_target_absent(sweep.CURRENT)
        sweep.reserve_restore(control.guard(True))
        sweep.CURRENT = sweep.OUT / "prepare"
        dirty.add("jp")
        mutate_guest("jp", before["jp"], "prepare-jp")
        dirty.add("site")
        sweep.az(["network", "vpn-site", "update", "-g", control.RG, "-n", "site-dc-jp",
                  "--address-prefixes", TARGET, "--query", "addressSpace"],
                 "set-static-prefix", mutation=True)
        dirty.add("link")
        set_bgp(False, "disable-link-bgp")
        current = read_settings("static-accepted")
        expected_connection = json.loads(json.dumps(settings[1]))
        expected_connection["links"][0]["bgp"] = False
        if current != [{"addressPrefixes": [TARGET]}, expected_connection]:
            raise RuntimeError("Static prefix/BGP state unaccepted or unrelated VPN fields changed")
        results["static"] = collect_target("static-vpn-only")
        if (not results["static"]["stable"] or not results["static"]["complete"] or
                not all(is_remote_vpn(r) for r in results["static"]["rows"])):
            raise RuntimeError("Exact static VPN prefix is not a stable eligible path at every firewall")
        results["static"]["traffic"] = probe_target("static-vpn-only")
        if any(c["tcp"] != "PASS" or c["icmp"] != "PASS" for c in results["static"]["traffic"]):
            raise RuntimeError("Static VPN target baseline is not reachable from both test spokes")
        for prepends in (0, 3):
            sweep.reserve_restore(control.guard(True))
            label = f"unreachable-local-add{prepends}"
            sweep.CURRENT = sweep.OUT / label
            dirty.add("eu")
            results[label] = {"source": mutate_guest("eu", before["eu"], label, prepends)}
            results[label]["advertisedWireAsPath"] = [guest.ASNS["eu"]] * (prepends + 1)
            results[label]["routes"] = collect_target(label)
            if not results[label]["routes"]["stable"] or not results[label]["routes"]["complete"]:
                raise RuntimeError("Injected target firewall routes incomplete or unstable")
            results[label]["traffic"] = probe_target(label)
    except Exception as exc:
        errors.append(str(exc))
        print("STATIC VPN ERROR " + str(exc), flush=True)
    finally:
        sweep.RESTORING = True
        sweep.RESTORE_DEADLINE = time.monotonic() + 60 * lease["restoreTimeoutMinutes"]
        try:
            sweep.CURRENT = sweep.OUT / "restore"
            for site in ("eu", "jp"):
                if site in dirty:
                    mutate_guest(site, before[site], "restore-" + site, restore=True)
                    dirty.remove(site)
            if "link" in dirty:
                set_bgp(True, "restore-link-bgp")
                dirty.remove("link")
            if "site" in dirty:
                sweep.az(["network", "vpn-site", "update", "-g", control.RG, "-n", "site-dc-jp",
                          "--remove", "addressSpace", "--query", "addressSpace"],
                         "restore-site-prefixes", mutation=True)
                dirty.remove("site")
            if settings is not None and read_settings("restored") != settings:
                raise RuntimeError("Original VPN configuration not restored")
            if baseline is not None:
                sweep.bounded_wait(120)
                original = sweep.capture("restore", 0, preference="ExpressRoute",
                                         firewall_ids=firewall_ids, parallel=True)
                if original["verdict"] != "PASS" or original["rows"] != baseline["rows"]:
                    raise RuntimeError("Original paired firewall winners not restored")
                require_target_absent(sweep.CURRENT)
            if before:
                sweep.CURRENT = sweep.OUT / "closure"
                after = boundary.invoke_all("static-vpn-closure")
                if any(not boundary.same_source(before[s], after[s]) for s in before):
                    raise RuntimeError("Original router source and protocol state not restored")
            restored = bool(before) and not dirty
        except Exception as exc:
            errors.append("RESTORE: " + str(exc))
        verdict = "PASS" if restored and not errors else "INCONCLUSIVE" if restored else "BLOCKED"
        sweep.CURRENT = sweep.OUT
        actual_lease = json.loads(control.LEASE.read_text())
        sweep.save("reproduction-verdict.json", dict(
            timestampUtc=sweep.utc(), verdict=verdict, target=TARGET,
            targetLimitation="Synthetic loopback on the VPN router; not a fix for Japan workload VM failures",
            restored=restored, results=results, errors=errors, dirty=sorted(dirty),
            observations=summarize(results),
            callsUsed=actual_lease["toolCallsUsed"], mutationsUsed=actual_lease["mutationsUsed"],
            children=[], interpretation="PASS means bounded experiment completed; inspect winners and traffic for the hypothesis"))
        actual_lease.update(state="completed" if verdict == "PASS" else "rolled-back" if restored else "blocked",
                            verdict=verdict, completedAtUtc=sweep.utc(), children=[])
        control.save(control.LEASE, actual_lease)
        print(f"FINAL {verdict} static VPN comparison restored={restored}; evidence={sweep.OUT}", flush=True)
    if verdict != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
