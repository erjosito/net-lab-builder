"""Compact, complete evidence for secured HRP and NVA policy comparisons."""
import argparse
import base64
import gzip
import json
import re

import aspath_sweep as sweep
import control
import effective_routes
import forwarding_matrix
import guest

ALL_SITES = (*sweep.SITES, "cn")
TARGETS = ("10.130.0.10", "10.130.0.4", "10.140.0.4", "10.10.0.10", "10.20.0.10", "10.30.0.10")


def guest_script(site, source=False):
    return f"""#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import base64,datetime,gzip,hashlib,json,re,subprocess,time
from pathlib import Path
def run(args,required=True):
 r=subprocess.run(args,text=True,capture_output=True,timeout=30)
 if required and r.returncode:raise RuntimeError(r.stderr or r.stdout)
 return dict(command=args,exitCode=r.returncode,stdout=r.stdout,stderr=r.stderr)
p=Path('/etc/bird/bird.conf')
s=p.stat()
health_wait=[]
for attempt in range(13):
 raw=run(['birdc','show','protocols'])
 protocols={{}}
 for line in raw['stdout'].splitlines():
  if re.match(r'(mesh_|azure_)',line):
   f=line.split();protocols[f[0]]=f[5] if len(f)>5 else 'Unknown'
 if len(protocols)=={3 if site=='cn' else 5} and set(protocols.values())=={{'Established'}}:break
 health_wait.append(protocols)
 if attempt<12:time.sleep(10)
assert len(protocols)=={3 if site=='cn' else 5} and set(protocols.values())=={{'Established'}},raw
result=dict(site={site!r},timestampUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
 sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
 stat=dict(uid=s.st_uid,gid=s.st_gid,mode=s.st_mode&0o777,mtimeNs=s.st_mtime_ns),
 protocols=protocols,healthWaitObservations=health_wait)
if {site=='jp'!r}:
 result['ikeEstablished']=len(re.findall('ESTABLISHED',run(['swanctl','--list-sas'])['stdout']))
 assert result['ikeEstablished']==2
if {source!r}:
 result['config']=p.read_text()
 assert not re.search(r'^\\s*(password|secret)\\b',result['config'],re.M|re.I),'Credential-bearing BIRD configuration requires private collection'
else:
 result['birdProtocols']=raw
 result['birdRoutes']=run(['birdc','show','route','table','lab4','all'])
 result['kernelRoutes']=run(['ip','-j','route','show','table','main'])
 result['policyRules']=run(['ip','-j','rule','show'])
 result['lookups']=[run(['ip','-j','route','get',ip],False) for ip in {TARGETS!r}]
 result['exports']={{peer:run(['birdc','show','route','export',peer,'all'])
  for peer in {('azure_0','azure_1') if site!='cn' else ()!r}}}
payload=base64.b64encode(gzip.compress(json.dumps(result,separators=(',',':')).encode())).decode()
assert len(payload)<3500,'Split evidence required; compressed payload bytes='+str(len(payload))
print('DESIGN_SNAPSHOT '+payload)
PY
"""


def decode(value):
    messages = "\n".join(x.get("message", "") for x in value.get("value", []))
    matches = re.findall(r"^DESIGN_SNAPSHOT ([A-Za-z0-9+/=]+)\s*$", messages, re.M)
    if len(matches) != 1:
        raise RuntimeError("Complete bounded guest snapshot missing: " + messages[-1200:])
    return json.loads(gzip.decompress(base64.b64decode(matches[0], validate=True)))


def nvas(label, source=False, sites=ALL_SITES):
    commands = []
    for site in sites:
        path = control.RUNTIME / f"design-{label}-{site}.sh"
        path.write_text(guest_script(site, source), encoding="utf-8", newline="\n")
        commands.append((["vm", "run-command", "invoke", "-g", control.RG,
                          "-n", "router-" + site, "--command-id", "RunShellScript",
                          "--scripts", "@" + str(path)], f"{label}-{site}"))
    values = sweep.az_batch(commands)
    result = {}
    for site, value in zip(sites, values):
        data = decode(value)
        if data["site"] != site:
            raise RuntimeError("Guest observer mismatch")
        result[site] = data
        sweep.save(f"{label}-{site}-decoded.json", data)
        if source:
            sweep.save(f"router-{site}.conf", data["config"])
        else:
            sweep.save(f"router-{site}-bird-routes.txt", data["birdRoutes"]["stdout"])
            for peer, exported in data["exports"].items():
                sweep.save(f"router-{site}-export-{peer}.txt", exported["stdout"])
    return result


def metadata(label):
    commands = []
    for site in sweep.SITES:
        for kind, name, suffix in (
            ("virtualHubs", f"hub-{site}", "hub"),
            ("virtualHubs", f"hub-{site}/routingIntent", "intent"),
        ):
            commands.append((["rest", "--method", "get", "--url",
                              sweep.network_url(kind, name) + "?api-version=2024-05-01"],
                             f"{label}-{site}-{suffix}"))
    values = sweep.az_batch(commands)
    result = {}
    for index, site in enumerate(sweep.SITES):
        hub, intent = values[index*2:index*2+2]
        policies = [p for i in intent.get("value", [])
                    for p in i.get("properties", {}).get("routingPolicies", [])]
        firewall = hub["properties"].get("azureFirewall", {}).get("id")
        if (not firewall or len(policies) != 1 or
                policies[0].get("destinations") != ["PrivateTraffic"] or
                policies[0].get("nextHop", "").lower() != firewall.lower()):
            raise RuntimeError(site + ": actual hub firewall and PrivateTraffic intent differ")
        result[site] = dict(hub=hub, intent=intent, firewallId=firewall,
                            preference=hub["properties"]["hubRoutingPreference"])
    sweep.save(label + "-metadata.json", result)
    return result


def firewall_routes(label, hubs):
    def snapshot(number):
        commands = [(effective_routes.arguments(
            sweep.SUB, control.RG, site, firewall_id=hubs[site]["firewallId"]),
            f"{label}-{site}-snapshot{number}") for site in sweep.SITES]
        values = sweep.az_batch(commands)
        normalized = []
        for site, value in zip(sweep.SITES, values):
            if not isinstance(value, dict) or not isinstance(value.get("value"), list):
                raise RuntimeError("Completed firewall effective-route result required")
            normalized.extend(sweep.normalize(value, site))
            rows = []
            for entry in value["value"]:
                for prefix in entry.get("addressPrefixes", []):
                    rows.append(dict(Prefix=prefix, ASPath=entry.get("asPath"),
                                     NextHopType=entry.get("nextHopType")))
            sweep.save(f"{label}-{site}-table{number}.json", rows)
            table = "Prefix\tASPath\tNextHopType\n" + "\n".join(
                f"{r['Prefix']}\t{r['ASPath'] or ''}\t{r['NextHopType'] or ''}" for r in rows)
            sweep.save(f"{label}-{site}-table{number}.txt", table)
        sweep.save(f"{label}-winners{number}.json", normalized)
        return normalized
    first, second = effective_routes.two_snapshots(snapshot, wait=sweep.bounded_wait)
    result = dict(stable=first == second,
                  complete=sweep.complete_rows(first) and sweep.complete_rows(second),
                  rows=second, minimumSnapshotSpacingSeconds=120)
    sweep.save(label + "-firewall-analysis.json", result)
    if not result["stable"] or not result["complete"]:
        raise RuntimeError("Paired firewall DC-prefix winners incomplete or unstable")
    return result


def traffic(label):
    probes = {
        "probe-spoke-eu": ("10.10.0.10", ["10.130.0.10", "10.130.0.4", "10.140.0.4"]),
        "probe-dc-eu": ("10.110.0.10", ["10.130.0.10", "10.130.0.4"]),
        "probe-dc-jp": ("10.130.0.10", ["10.110.0.10", "10.10.0.10"]),
    }
    commands = []
    for name, (source, destinations) in probes.items():
        path = control.RUNTIME / f"design-traffic-{name}.sh"
        path.write_text(forwarding_matrix.script(source, destinations),
                        encoding="utf-8", newline="\n")
        commands.append((["vm", "run-command", "invoke", "-g", control.RG, "-n", name,
                          "--command-id", "RunShellScript", "--scripts", "@" + str(path)],
                         f"{label}-{name}"))
    values = sweep.az_batch(commands)
    cells = []
    for (name, (source, destinations)), value in zip(probes.items(), values):
        messages = "\n".join(x.get("message", "") for x in value.get("value", []))
        matches = re.findall(r"^FORWARDING_COMPLETE (\{.*\})$", messages, re.M)
        if len(matches) != 1:
            raise RuntimeError(name + ": complete traffic output missing")
        actual = json.loads(matches[0])["cells"]
        if (len(actual) != len(destinations) or
                {(c["source"], c["destination"]) for c in actual} !=
                {(source, d) for d in destinations}):
            raise RuntimeError(name + ": directional cells differ")
        cells.extend(actual)
    sweep.save(label + "-traffic.json", cells)
    return cells


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lease", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    control.LEASE = control.RUNTIME / args.lease
    lease = control.guard(False)
    if lease.get("toolCallsUsed", 0) or lease["maxMutations"] != 0:
        raise RuntimeError("Fresh read-only baseline lease required")
    sweep.SUB = control.account_id()
    sweep.OUT = control.ROOT.parent / "show-output" / args.out
    sweep.CURRENT = sweep.OUT
    if sweep.OUT.exists():
        raise RuntimeError("Fresh correlation directory required")
    sweep.RESTORING = True
    errors, result = [], {}
    try:
        result["hubs"] = metadata("current")
        sweep.CURRENT = sweep.OUT / "sources"
        result["sources"] = nvas("source", True)
        sweep.CURRENT = sweep.OUT / "routes"
        result["nvas"] = nvas("routing")
        sweep.CURRENT = sweep.OUT / "firewalls"
        result["firewalls"] = firewall_routes("current", result["hubs"])
        sweep.CURRENT = sweep.OUT / "traffic"
        result["traffic"] = traffic("current")
    except Exception as exc:
        errors.append(str(exc))
        print("BASELINE ERROR " + str(exc), flush=True)
    finally:
        verdict = "PASS" if not errors else "BLOCKED"
        lease = json.loads(control.LEASE.read_text())
        sweep.CURRENT = sweep.OUT
        sweep.save("baseline-verdict.json", dict(
            timestampUtc=sweep.utc(), verdict=verdict, result=result, errors=errors,
            callsUsed=lease["toolCallsUsed"], mutationsUsed=0, children=[],
            interpretation="PASS is evidence completeness; individual traffic failures remain failures"))
        lease.update(state="completed" if not errors else "blocked", verdict=verdict,
                     completedAtUtc=sweep.utc(), children=[])
        control.save(control.LEASE, lease)
        print("FINAL " + verdict + " read-only current design baseline", flush=True)
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
