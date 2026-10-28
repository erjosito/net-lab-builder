"""Matched secured B2B controls, full traffic matrix and bounded path observations."""
import argparse
import base64
import copy
import datetime as dt
import gzip
import hashlib
import json
import re
import time

import aspath_sweep as sweep
import control
import design_backbone as backbone
import design_comparison as comparison
import design_customer as customer
import design_hrp_reselection as reselection
import design_snapshot as snapshot
import infra
import resume_vms

CORRELATION = "b2b-20261017"
ENDPOINTS = {
    "probe-dc-eu": "10.110.0.10", "probe-dc-us": "10.120.0.10",
    "probe-dc-jp": "10.130.0.10", "router-cn": "10.140.0.4",
    "probe-spoke-eu": "10.10.0.10", "probe-spoke-us": "10.20.0.10",
    "probe-spoke-jp": "10.30.0.10",
}


def read_evidence(name, file):
    return json.loads((control.ROOT.parent / "show-output" / name / file).read_text(
        encoding="utf-8").replace("<SUBSCRIPTION_ID>", sweep.SUB))


def unpack(value, marker):
    text = "\n".join(v.get("message", "") for v in value.get("value", []))
    matches = re.findall(r"^" + marker + r" ([A-Za-z0-9+/=]+)\s*$", text, re.M)
    if len(matches) != 1:
        raise RuntimeError("Complete guest output missing: " + text[-1200:])
    return json.loads(gzip.decompress(base64.b64decode(matches[0], validate=True)))


def guest_batch(label, scripts, marker):
    commands = []
    for vm, script in scripts.items():
        path = control.RUNTIME / f"{CORRELATION}-{label}-{vm}.sh"
        path.write_text(script, encoding="utf-8", newline="\n")
        commands.append((["vm", "run-command", "invoke", "-g", control.RG, "-n", vm,
                          "--command-id", "RunShellScript", "--scripts", "@" + str(path)],
                         f"{label}-{vm}"))
    values = sweep.az_batch(commands)
    return {vm: unpack(v, marker) for vm, v in zip(scripts, values)}


def python_script(body, marker):
    return ("#!/bin/bash\nset -euo pipefail\npython3 - <<'PY'\n"
            "import base64,gzip,json,subprocess,time,datetime,os,pathlib,re,signal\n" + body
            + "\npayload=base64.b64encode(gzip.compress(json.dumps(result,separators=(',',':')).encode())).decode()\n"
            "assert len(payload)<3500, 'Split evidence required: '+str(len(payload))\n"
            f"print('{marker} '+payload)\nPY\n")


def traffic_targets(source, dc_azure_only=False):
    if source not in ENDPOINTS.values():
        raise ValueError("Unknown traffic source")
    dc = {ip for vm, ip in ENDPOINTS.items() if not vm.startswith("probe-spoke-")}
    return tuple(ip for ip in ENDPOINTS.values() if ip != source
                 and (not dc_azure_only or (ip in dc) != (source in dc)))


def selection_state(selected):
    return {site: [{key: re.sub(r"\b\d{2}:\d{2}:\d{2}(?:\.\d+)?\b", "<DISPLAY_TIME>", value)
                   if key == "headline" else value for key, value in row.items()}
                   for row in rows] for site, rows in selected.items()}


def traffic_script(source, dc_azure_only=False):
    return python_script(f"""
source={source!r}
def run(args,timeout=15):
 r=subprocess.run(args,text=True,capture_output=True,timeout=timeout)
 return dict(exitCode=r.returncode,stdout=r.stdout.strip(),stderr=r.stderr.strip())
listener=run(['systemctl','is-active','lab-http'])
assert listener['exitCode']==0,listener
cells=[]
for destination in {traffic_targets(source, dc_azure_only)!r}:
 route=run(['ip','-j','route','get',destination,'from',source])
 icmp=run(['ping','-n','-I',source,'-c','2','-W','1',destination])
 tcp=run(['curl','--interface',source,'--noproxy','*','-sS','--connect-timeout','3',
          '--max-time','5','--output','/dev/null','--write-out','%{{http_code}} %{{local_ip}} %{{remote_ip}}',
          'http://'+destination+':5201/'])
 cells.append(dict(source=source,destination=destination,route=route,
  tcp='PASS' if tcp['exitCode']==0 and tcp['stdout']=='200 '+source+' '+destination else 'FAIL',
  icmp='PASS' if icmp['exitCode']==0 else 'FAIL',tcpDetail=tcp,icmpDetail=icmp))
result=dict(timestampUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),cells=cells)
""", "B2B_TRAFFIC")


def capture_script(label, stop=False):
    if not re.fullmatch(r"[A-Za-z0-9-]+", label):
        raise ValueError("Unsafe capture label")
    folder = "/var/tmp/" + CORRELATION + "-" + label
    if not stop:
        body = f"""
p=pathlib.Path({folder!r});p.mkdir(mode=0o700)
out=(p/'packets.txt').open('w');err=(p/'stderr.txt').open('w')
expression='(icmp or tcp port 5201) and ('+' or '.join('host '+x for x in {tuple(ENDPOINTS.values())!r})+')'
proc=subprocess.Popen(['timeout','240','tcpdump','-nn','-l','-i','any','-s','96','-c','10000',expression],
 stdout=out,stderr=err,start_new_session=True)
(p/'pid').write_text(str(proc.pid));ready=False
for i in range(30):
 if proc.poll() is not None:raise RuntimeError((p/'stderr.txt').read_text())
 if 'listening on' in (p/'stderr.txt').read_text():ready=True;break
 time.sleep(.1)
assert ready,'Capture not responsive'
result=dict(pid=proc.pid,ready=True,limitSeconds=240,expression=expression,
 timestampUtc=datetime.datetime.now(datetime.timezone.utc).isoformat())
"""
    else:
        body = f"""
p=pathlib.Path({folder!r});pid=int((p/'pid').read_text())
cmd=pathlib.Path('/proc')/str(pid)/'cmdline'
expired=not cmd.exists() or not cmd.read_bytes()
if not expired:
 text=cmd.read_bytes()
 assert b'timeout' in text and b'tcpdump' in text,'Capture PID identity differs'
 os.killpg(pid,signal.SIGINT)
 for i in range(30):
  if 'packets captured' in (p/'stderr.txt').read_text():break
  time.sleep(.1)
raw=(p/'packets.txt').read_text();counts={{}};samples=[];unparsed=[]
for line in raw.splitlines():
 m=re.search(r'\\s(\\S+)\\s+(In|Out)\\s+IP (\\d+\\.\\d+\\.\\d+\\.\\d+)(?:\\.\\d+)? > (\\d+\\.\\d+\\.\\d+\\.\\d+)(?:\\.\\d+)?:',line)
 if not m:
  if len(unparsed)<3:unparsed.append(line)
  continue
 interface,direction,src,dst=m.groups()
 if src not in {tuple(ENDPOINTS.values())!r} or dst not in {tuple(ENDPOINTS.values())!r}:continue
 kind='ICMP' if 'ICMP' in line else 'TCP'
 key='|'.join((interface,direction,src,dst,kind))
 counts[key]=counts.get(key,0)+1
 if len(samples)<3:samples.append(line)
result=dict(counts=counts,samples=samples,unparsed=unparsed,expired=expired,
 stderr=(p/'stderr.txt').read_text(),lineCount=len(raw.splitlines()),
 interpretation='Interface observations, not throughput or a complete path-symmetry proof')
assert 'packets captured' in result['stderr'],result['stderr']
for name in ('pid','packets.txt','stderr.txt'):(p/name).unlink()
p.rmdir()
"""
    return python_script(body, "B2B_CAPTURE")


def traffic(label, dc_azure_only=False):
    started = guest_batch(label + "-capture-start",
                          {"router-" + s: capture_script(label) for s in snapshot.ALL_SITES},
                          "B2B_CAPTURE")
    sweep.save("capture-start.json", started)
    try:
        results = guest_batch(label + "-traffic",
                              {vm: traffic_script(ip, dc_azure_only) for vm, ip in ENDPOINTS.items()},
                              "B2B_TRAFFIC")
        cells = [c for v in results.values() for c in v["cells"]]
        expected = {(a, b) for a in ENDPOINTS.values() for b in traffic_targets(a, dc_azure_only)}
        if len(cells) != len(expected) or {(c["source"], c["destination"]) for c in cells} != expected:
            raise RuntimeError("Incomplete or duplicate traffic matrix")
        sweep.save("traffic-details.json", results)
        summary = dict(cells=cells, expectedDirections=len(expected),
                       scope="DC-Azure" if dc_azure_only else "all-pairs diagnostic",
                       tcpPass=sum(c["tcp"] == "PASS" for c in cells),
                       icmpPass=sum(c["icmp"] == "PASS" for c in cells))
        summary["verdict"] = "PASS" if summary["tcpPass"] == summary["icmpPass"] == len(expected) else "FAIL"
        sweep.save("traffic-summary.json", summary)
    finally:
        observed = guest_batch(label + "-capture-stop",
                               {"router-" + s: capture_script(label, True) for s in snapshot.ALL_SITES},
                               "B2B_CAPTURE")
        sweep.save("path-observations.json", observed)
    return summary


def capture(label, expected=None, all_enabled=False, dc_azure_only=False):
    sweep.CURRENT = sweep.OUT / label
    wan = sweep.az(["rest", "--method", "get", "--url",
                    sweep.network_url("virtualWans", "vwan-threehub") + "?api-version=2024-05-01"],
                   label + "-wan")
    if wan["properties"].get("allowBranchToBranchTraffic") is not True:
        raise RuntimeError("WAN-level B2B is not enabled")
    hubs = snapshot.metadata(label)
    if all_enabled and any(h["hub"]["properties"].get("allowBranchToBranchTraffic") is not True
                           for h in hubs.values()):
        raise RuntimeError("B2B not enabled on every hub")
    sources = snapshot.nvas(label + "-source", True)
    if expected and any(not comparison.source_unchanged(expected[s], sources[s])
                        for s in snapshot.ALL_SITES):
        raise RuntimeError("Unexpected exact BIRD configuration, metadata or peer state")
    nvas = snapshot.nvas(label + "-routes")
    firewalls = reselection.firewall_capture(label, hubs, complete=False)
    selected = {s: [comparison.selected_route(nvas[s]["birdRoutes"]["stdout"], p)
                    for p in (*comparison.guest_prefixes(), *infra.SPOKE_PREFIXES)]
                for s in snapshot.ALL_SITES}
    sweep.save("selected-routes.json", selected)
    result = dict(wan=wan, hubs=hubs, sources=sources, nvas=nvas, firewalls=firewalls, selected=selected)
    result["traffic"] = traffic(label, dc_azure_only)
    sweep.save("scenario-result.json", result)
    total = result["traffic"]["expectedDirections"]
    print(f"MEASURED {label}: TCP={result['traffic']['tcpPass']}/{total} "
          f"ICMP={result['traffic']['icmpPass']}/{total}", flush=True)
    return result


def set_hubs(hubs, preference=None, enable=False, label="apply"):
    resources = comparison.original_hubs(hubs)
    for r in resources:
        if preference:
            r["properties"]["hubRoutingPreference"] = preference
        if enable:
            r["properties"]["allowBranchToBranchTraffic"] = True
    sweep.submit(infra.template(resources), {"parameters": {}}, CORRELATION + "-" + label, True)


def power(start, baseline_name):
    if start:
        vms = sweep.az(["vm", "list", "-g", control.RG, "--show-details"], "power-before")
        if {v["name"] for v in vms} != resume_vms.EXPECTED:
            raise RuntimeError("Unexpected VM inventory")
        if any(any(v.get("tags", {}).get(k) != x for k, x in control.TAGS.items()) for v in vms):
            raise RuntimeError("VM task ownership tags differ")
        if any(v.get("powerState") not in ("VM running", "VM deallocated") for v in vms):
            raise RuntimeError("Unsupported original power state")
        sweep.save("power-before.json", vms)
        names = [v["name"] for v in vms if v["powerState"] == "VM deallocated"]
        sweep.save("started-vms.json", names)
        if names:
            sweep.az(["vm", "start", "--ids", *[v["id"] for v in vms if v["name"] in names]],
                     "start-owned-vms", True)
        actual = sweep.az(["vm", "list", "-g", control.RG, "--show-details"], "power-running")
        if {v["name"] for v in actual} != resume_vms.EXPECTED or any(
                v["powerState"] != "VM running" for v in actual):
            raise RuntimeError("Not all ten owned VMs are running")
    else:
        vms = read_evidence(baseline_name, "power-before.json")
        names = read_evidence(baseline_name, "started-vms.json")
        if names:
            sweep.az(["vm", "deallocate", "--ids", *[v["id"] for v in vms if v["name"] in names]],
                     "restore-owned-power", True)
        actual = sweep.az(["vm", "list", "-g", control.RG, "--show-details"], "power-restored")
        expected = {v["name"]: v["powerState"] for v in vms}
        if {v["name"]: v["powerState"] for v in actual} != expected:
            raise RuntimeError("Original exact VM power inventory differs")
        sweep.save("power-verdict.json", dict(verdict="PASS", restored=True, actual=actual))


def scenario(variant, before):
    preference = {"A": "ASPath", "B1": "ExpressRoute", "B1-one-ASN": "ExpressRoute",
                  "B1-VPN": "VpnGateway", "B2": "ASPath"}[variant]
    desired = ({s: backbone.policy(before["sources"][s]["config"], s) for s in sweep.SITES}
               if variant == "A" else
               {s: customer.policy(before["sources"][s]["config"], s, 0) for s in ("eu", "us")}
               if variant == "B2" else
               {"eu": customer.policy(before["sources"]["eu"]["config"], "eu", 2)}
               if variant == "B1-one-ASN" else {})
    dirty, hub_dirty, states = [], False, {}
    subnet, table_created, subnet_dirty = None, False, False
    backbone.BACKUP = "/var/lib/threehub/" + CORRELATION + "-baseline.conf"
    working = copy.deepcopy(before["sources"])
    try:
        for s, text in desired.items():
            dirty.append(s)
            backbone.configure(s, before["sources"][s], text)
            working[s]["sha256"] = hashlib.sha256(text.encode()).hexdigest()
        hub_dirty = True
        set_hubs(before["hubs"], preference=preference, enable=True, label=variant)
        states[variant] = capture(variant, working, True)
        if variant == "A":
            sweep.CURRENT = sweep.OUT / "A-workload-UDR"
            subnet = sweep.az(["rest", "--method", "get", "--url",
                              sweep.network_url("virtualNetworks", "vnet-dc-jp/subnets/workload") +
                              "?api-version=2024-05-01"], "original-jp-subnet")
            if subnet["properties"].get("routeTable"):
                raise RuntimeError("Existing Japan route table; refusing overwrite")
            backbone.ROUTE_TABLE = CORRELATION + "-jp-workload"
            tables = sweep.az(["network", "route-table", "list", "-g", control.RG], "existing-tables")
            if any(t["name"] == backbone.ROUTE_TABLE for t in tables):
                raise RuntimeError("Experiment route table already exists")
            route_id = sweep.network_url("routeTables", backbone.ROUTE_TABLE).replace(
                "https://management.azure.com", "")
            resource = backbone.subnet_resource(subnet, route_id)
            resource["dependsOn"] = [f"[resourceId('Microsoft.Network/routeTables', '{backbone.ROUTE_TABLE}')]"]
            subnet_dirty = table_created = True
            sweep.submit(infra.template([backbone.route_table(sweep.SUB), resource]),
                         {"parameters": {}}, CORRELATION + "-jp-workload-udr", True)
            states["A-workload-UDR"] = capture("A-workload-UDR", working, True)
        if variant in ("B1", "B1-one-ASN"):
            withdrawn = reselection.withdraw_japan(before["sources"]["jp"]["config"])
            dirty.append("jp")
            backbone.configure("jp", before["sources"]["jp"], withdrawn)
            changed = copy.deepcopy(working)
            changed["jp"]["sha256"] = hashlib.sha256(withdrawn.encode()).hexdigest()
            states[variant + "-withdrawn"] = capture(variant + "-withdrawn", changed, True)
            backbone.configure("jp", before["sources"]["jp"], withdrawn, restore=True)
            dirty.remove("jp")
            states[variant + "-returned"] = capture(variant + "-returned", working, True)
    finally:
        sweep.RESTORING = True
        sweep.RESTORE_DEADLINE = time.monotonic() + 20 * 60
        sweep.CURRENT = sweep.OUT / "restore"
        if subnet_dirty:
            sweep.submit(infra.template([backbone.subnet_resource(subnet)]), {"parameters": {}},
                         CORRELATION + "-restore-subnet", True)
        if table_created:
            sweep.az(["network", "route-table", "delete", "-g", control.RG,
                      "-n", backbone.ROUTE_TABLE], "delete-only-created-route-table", True)
            actual = sweep.az(["rest", "--method", "get", "--url",
                               sweep.network_url("virtualNetworks", "vnet-dc-jp/subnets/workload") +
                               "?api-version=2024-05-01"], "verify-original-jp-subnet")
            if actual["properties"].get("routeTable") != subnet["properties"].get("routeTable"):
                raise RuntimeError("Original subnet route table association differs")
        for s in reversed(dirty):
            text = desired.get(s) or reselection.withdraw_japan(before["sources"][s]["config"])
            backbone.configure(s, before["sources"][s], text, restore=True)
        if hub_dirty:
            set_hubs(before["hubs"], label="restore-" + variant)
        sources = snapshot.nvas("restore-source", True)
        hubs = snapshot.metadata("restore")
        if any(not comparison.source_unchanged(before["sources"][s], sources[s])
               for s in snapshot.ALL_SITES):
            raise RuntimeError("Exact original guest source restore differs")
        if any(hubs[s]["preference"] != before["hubs"][s]["preference"] or
               hubs[s]["hub"]["properties"]["allowBranchToBranchTraffic"] !=
               before["hubs"][s]["hub"]["properties"]["allowBranchToBranchTraffic"]
               for s in sweep.SITES):
            raise RuntimeError("Exact hub flag/preference restore differs")
        sweep.save("restore-proof.json", dict(sources=sources, hubs=hubs))
    return states


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("power-start", "power-stop", "baseline", "enable",
                                        "scenario", "restore-hubs", "verify"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--baseline")
    parser.add_argument("--variant", choices=("A", "B1", "B1-one-ASN", "B1-VPN", "B2"))
    args = parser.parse_args()
    sweep.SUB = control.account_id()
    sweep.OUT = control.ROOT.parent / "show-output" / args.out
    sweep.CURRENT = sweep.OUT
    if sweep.OUT.exists():
        raise RuntimeError("Fresh evidence directory required")
    control.LEASE = control.RUNTIME / (args.out + ".json")
    if control.LEASE.exists():
        raise RuntimeError("Fresh lease required")
    now = dt.datetime.now(dt.timezone.utc)
    control.save(control.LEASE, dict(taskId=args.out, ownerRole="Oracle",
                 objective="Secured matched B2B control " + args.mode,
                 startedAtUtc=now.isoformat(), expiresAtUtc=(now + dt.timedelta(minutes=90)).isoformat(),
                 maxToolCalls=220, maxMutations=20, commandTimeoutSeconds=600,
                 restoreTimeoutMinutes=20, state="active", toolCallsUsed=0, mutationsUsed=0))
    if args.mode == "power-start":
        stop = control.RUNTIME / "STOP"
        if stop.exists():
            sweep.save("prior-stop.txt", stop.read_text())
            stop.unlink()
    sweep.RESTORING = False
    sweep.RESTORE_DEADLINE = None
    control.guard(True)
    result = {}
    try:
        before = read_evidence(args.baseline, "baseline-verdict.json")["result"] if args.baseline and args.mode != "power-stop" else None
        if args.mode.startswith("power-"):
            power(args.mode == "power-start", args.baseline)
        elif args.mode == "baseline":
            result = capture("baseline")
        elif args.mode == "enable":
            set_hubs(before["hubs"], enable=True, label="enable")
            result = capture("baseline", before["sources"], True)
        elif args.mode == "scenario":
            if not args.variant:
                raise ValueError("Scenario variant required")
            result = scenario(args.variant, before)
        elif args.mode == "restore-hubs":
            set_hubs(before["hubs"], label="restore-mixed")
            result = capture("restored", before["sources"])
        elif args.mode == "verify":
            result = capture("independent-verification", before["sources"])
            for s in sweep.SITES:
                a, b = result["hubs"][s], before["hubs"][s]
                if a["preference"] != b["preference"] or a["hub"]["properties"]["allowBranchToBranchTraffic"] != b["hub"]["properties"]["allowBranchToBranchTraffic"]:
                    raise RuntimeError("Original hub state differs")
            if result["firewalls"]["rows"] != before["firewalls"]["rows"]:
                raise RuntimeError("Original stable firewall winners differ")
        sweep.CURRENT = sweep.OUT
        filename = "baseline-verdict.json" if args.mode in ("baseline", "enable") else "verdict.json"
        sweep.save(filename, dict(verdict="PASS", result=result, timestampUtc=sweep.utc(),
                                 interpretation="PASS means complete evidence/exact configuration closure, not all traffic passed"))
        lease = control.guard(False)
        lease.update(state="completed", verdict="PASS", completedAtUtc=sweep.utc())
        control.save(control.LEASE, lease)
        if args.mode == "power-stop":
            (control.RUNTIME / "STOP").write_text(
                "Matched all-hub B2B controls complete; original configuration and power inventory restored.\n",
                encoding="utf-8")
        print("FINAL PASS " + args.mode, flush=True)
    except Exception as exc:
        sweep.CURRENT = sweep.OUT
        sweep.save("failure.json", dict(error=str(exc), timestampUtc=sweep.utc()))
        lease = json.loads(control.LEASE.read_text())
        lease.update(state="blocked", failure=str(exc))
        control.save(control.LEASE, lease)
        raise


if __name__ == "__main__":
    main()
