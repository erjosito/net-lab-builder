"""Six-mutation Japan VPN / Europe peered-NVA ASPath boundary comparison."""
import json
import re
import time

import aspath_sweep as sweep
import control
import guest

OUT = control.ROOT.parent / "show-output" / "vpn-sdwan-aspath-boundaries"
BASE = {}


def script(site, count=None, restore=False, withdraw_cn=False):
    asn = guest.ASNS[site]
    backup = f"/var/lib/threehub/vpn-sdwan-boundary-{site}-baseline.conf"
    expected = BASE.get(site, {}).get("sha256")
    replacement = sweep.FILTER.replace(
        "then accept;", "then {\n" +
        "".join(f"    bgp_path.prepend({asn});\n" for _ in range(count or 0)) +
        "    accept;\n  }")
    if withdraw_cn:
        replacement = replacement.replace(
            "filter azure_export {\n",
            "filter azure_export {\n  if net = 10.140.0.0/24 then reject;\n")
    return f"""#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import hashlib,json,os,re,subprocess
from pathlib import Path
p=Path('/etc/bird/bird.conf')
b=Path({backup!r})
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def metadata(p):
 s=p.stat()
 return dict(uid=s.st_uid,gid=s.st_gid,mode=s.st_mode&0o777,mtimeNs=s.st_mtime_ns)
def run(args):
 r=subprocess.run(args,text=True,capture_output=True,timeout=30)
 if r.returncode: raise RuntimeError(r.stderr or r.stdout)
 return r.stdout
configured=None
if {count is not None or restore!r}:
 if not b.exists():
  assert not {restore!r}, 'Restore backup missing'
  assert digest(p)=={expected!r}, 'Original hash changed before backup'
  m=metadata(p)
  b.write_bytes(p.read_bytes())
  os.chown(b,m['uid'],m['gid']);os.chmod(b,m['mode'])
  os.utime(b,ns=(b.stat().st_atime_ns,m['mtimeNs']))
 assert digest(b)=={expected!r}, 'Protected backup hash differs'
 m=metadata(b)
 assert m=={BASE.get(site, {}).get("stat")!r}, 'Protected metadata differs'
 original=b.read_text()
 assert original.count({sweep.FILTER!r})==1
 assert original.count('export filter azure_export;')==2
 assert 'bgp_path.prepend' not in original
 candidate=b.read_bytes() if {restore!r} else original.replace({sweep.FILTER!r},{replacement!r}).encode()
 n=Path('/etc/bird/bird.conf.boundary-next')
 assert not n.exists(), 'Unexpected candidate file'
 try:
  n.write_bytes(candidate)
  os.chown(n,m['uid'],m['gid']);os.chmod(n,m['mode'])
  os.utime(n,ns=(b.stat().st_atime_ns,m['mtimeNs']))
  run(['bird','-p','-c',str(n)])
  os.replace(n,p)
 finally:
  if n.exists(): n.unlink()
 configured=run(['birdc','configure']).strip()
 assert re.search(r'^Reconfigured\\s*$',configured,re.M), configured
 if {restore!r}: assert digest(p)=={expected!r} and metadata(p)==m
raw=run(['birdc','show','protocols'])
protocols={{}}
for line in raw.splitlines():
 if re.match(r'(mesh_|azure_)',line):
  fields=line.split()
  protocols[fields[0]]=fields[5] if len(fields)>5 else 'Unknown'
exports={{}}
if {site in ("eu","us","jp")!r}:
 for peer in ('azure_0','azure_1'):
  text=run(['birdc','show','route','export',peer,'all'])
  routes={{}};prefix=None
  for line in text.splitlines():
   match=re.match(r'(10\\.\\d+\\.0\\.0/24)\\s',line)
   if match: prefix=match.group(1);routes[prefix]=[]
   if prefix and 'BGP.as_path:' in line:
    routes[prefix]=[int(x) for x in line.split('BGP.as_path:',1)[1].split()]
  exports[peer]=dict(routes=routes,rawSha256=hashlib.sha256(text.encode()).hexdigest())
ike=None
if {site=="jp"!r}:
 ike=len(re.findall(r'ESTABLISHED',run(['swanctl','--list-sas'])))
result=dict(site={site!r},sha256=digest(p),stat=metadata(p),protocols=protocols,
 exports=exports,ikeEstablished=ike,additionalPrepends={count or 0},
 configureOutput=configured,restored={restore!r})
print('BOUNDARY_COMPLETE '+json.dumps(result,separators=(',',':')))
PY
"""


def invoke(site, label, count=None, restore=False, withdraw_cn=False):
    path = control.RUNTIME / f"boundary-{site}-{label}.sh"
    path.write_text(script(site, count, restore, withdraw_cn), encoding="utf-8", newline="\n")
    value = sweep.az(["vm", "run-command", "invoke", "-g", control.RG,
                      "-n", "router-" + site, "--command-id", "RunShellScript",
                      "--scripts", "@" + str(path)],
                     f"direct-{site}-{label}", mutation=count is not None or restore)
    return parse_result(site, label, value, count, withdraw_cn)


def invoke_all(label):
    commands = []
    sites = (*sweep.SITES, "cn")
    for site in sites:
        path = control.RUNTIME / f"boundary-{site}-{label}.sh"
        path.write_text(script(site), encoding="utf-8", newline="\n")
        commands.append((["vm", "run-command", "invoke", "-g", control.RG,
                          "-n", "router-" + site, "--command-id", "RunShellScript",
                          "--scripts", "@" + str(path)], f"direct-{site}-{label}"))
    values = sweep.az_batch(commands)
    return {site: parse_result(site, label, value) for site, value in zip(sites, values)}


def parse_result(site, label, value, count=None, withdraw_cn=False):
    messages = "\n".join(x.get("message", "") for x in value.get("value", []))
    matches = re.findall(r"^BOUNDARY_COMPLETE (\{.*\})$", messages, re.M)
    if len(matches) != 1:
        raise RuntimeError(f"{site}/{label}: explicit guest completion missing: {messages[-1000:]}")
    result = json.loads(matches[0])
    expected = 3 if site == "cn" else 5
    if (len(result["protocols"]) != expected or
            set(result["protocols"].values()) != {"Established"}):
        raise RuntimeError(f"{site}: incomplete Established BGP proof")
    if site == "jp" and result["ikeEstablished"] != 2:
        raise RuntimeError("Japan requires both Established IKE SAs")
    if site in ("jp", "eu", "us"):
        basepaths = {p: ([] if p == guest.DC[site] else [guest.ASNS[s]])
                     for s, p in guest.DC.items()}
        expectedpaths = {p: [guest.ASNS[site]] * (count or 0) + v
                         for p, v in basepaths.items()
                         if not withdraw_cn or p != "10.140.0.0/24"}
        if any(e["routes"] != expectedpaths for e in result["exports"].values()):
            raise RuntimeError(f"{site}: actual two-peer ASPath exports differ")
        if len(result["exports"]) != 2:
            raise RuntimeError("Both Azure peer exports required")
    sweep.save(f"source-{site}-proof.json", result)
    return result


def same_source(before, after):
    """Keep raw CLI hashes as evidence, not invariants of volatile route output."""
    return (all(before[k] == after[k]
                for k in ("sha256", "stat", "protocols", "ikeEstablished")) and
            {peer: export["routes"] for peer, export in before["exports"].items()} ==
            {peer: export["routes"] for peer, export in after["exports"].items()})


def main():
    control.LEASE = control.RUNTIME / "vpn-sdwan-boundary-lease.json"
    lease = json.loads(control.LEASE.read_text(encoding="utf-8-sig"))
    if (lease["ownerRole"] != "Trinity" or lease["state"] != "active" or
            lease.get("toolCallsUsed", 0) or lease.get("mutationsUsed", 0)):
        raise RuntimeError("Fresh accepted Trinity lease required")
    lease.setdefault("startedAtUtc", lease["lastCheckpointUtc"])
    lease.update(toolCallsUsed=0, mutationsUsed=0)
    control.save(control.LEASE, lease)
    control.guard(True)
    if OUT.exists():
        raise RuntimeError("Fresh evidence directory required")
    sweep.SUB = control.account_id()
    sweep.OUT = OUT
    sweep.CURRENT = OUT / "preflight"
    before, after, states, errors = {}, {}, {}, []
    dirty = None
    baseline = None

    def capture(label, site, count):
        result = sweep.capture(label, count, ingress=site.upper() if site else "ALL_ZERO")
        states[label] = result
        if result["verdict"] != "PASS":
            raise RuntimeError(f"{label}: paired twelve-winner matrix incomplete/unstable")
        return result

    def restore(site, label):
        nonlocal dirty
        sweep.RESTORING = True
        sweep.RESTORE_DEADLINE = time.monotonic() + 900
        sweep.CURRENT = OUT / label
        proof = invoke(site, label, restore=True)
        if proof["sha256"] != BASE[site]["sha256"] or proof["stat"] != BASE[site]["stat"]:
            raise RuntimeError(f"{site}: exact hash/ownership/mode/timestamp restore differs")
        dirty = None
        result = capture(label, site, 0)
        if result["rows"] != baseline["rows"]:
            raise RuntimeError(f"{site}: restored winner/path matrix differs from baseline")
        sweep.RESTORING = False
        sweep.RESTORE_DEADLINE = None

    try:
        for site in (*sweep.SITES, "cn"):
            before[site] = invoke(site, "baseline")
            BASE[site] = before[site]
        if before["jp"]["sha256"] != sweep.BASELINE_HASH:
            raise RuntimeError("Japan original hash differs from verified restore")
        baseline = capture("baseline0", None, 0)
        for site in ("jp", "eu"):
            sweep.reserve_restore(control.guard(True))
            for count in (4, 8):
                control.guard(True)
                dirty = site
                label = f"{site}-add{count}"
                sweep.CURRENT = OUT / label
                invoke(site, label, count=count)
                capture(label, site, count)
            restore(site, f"{site}-restore0")
        sweep.RESTORING = True
        sweep.CURRENT = OUT / "closure"
        for site in (*sweep.SITES, "cn"):
            after[site] = invoke(site, "closure")
            if not same_source(before[site], after[site]):
                raise RuntimeError(f"{site}: final hash/metadata/protocol/export proof differs")
    except Exception as exc:
        errors.append(str(exc))
        print(f"BOUNDARY ERROR {exc}", flush=True)
    finally:
        if dirty:
            try:
                restore(dirty, f"{dirty}-restore-error")
            except Exception as exc:
                errors.append("RESTORE: " + str(exc))
        sweep.CURRENT = OUT
        restored = dirty is None and all(
            before.get(s, {}).get("sha256") == after.get(s, {}).get("sha256")
            for s in before) and len(after) == 4
        thresholds = {}
        for site in ("jp", "eu"):
            samples = [states[k] for k in ("baseline0", f"{site}-add4", f"{site}-add8") if k in states]
            thresholds[site] = sweep.summarize(samples)
            for row in thresholds[site]:
                observed = row["firstObservedSwitch"]
                row["exactMinimumThreshold"] = 4 if site == "jp" and observed == 4 else None
                row["thresholdBracket"] = ([1, 4] if site == "eu" and observed == 4 else
                                           [5, 8] if observed == 8 else None)
                row["nextRefinementNeeded"] = row["thresholdBracket"] is not None
                row["historicalJP0Through3NoSwitch"] = site == "jp"
        lease = json.loads(control.LEASE.read_text())
        complete = len(states) == 7 and restored and not errors
        verdict = "PASS" if complete else "INCONCLUSIVE" if restored else "BLOCKED"
        summary = dict(timestampUtc=sweep.utc(), verdict=verdict, completedStates=list(states),
                       states=states, thresholds=thresholds, restored=restored, errors=errors,
                       callsUsed=lease["toolCallsUsed"], mutationsUsed=lease["mutationsUsed"],
                       protocolProofBefore=before, protocolProofAfter=after, children=[],
                       actualHRPProof="All three full hub and RI GETs in every state hub-metadata.json",
                       losingCandidates="Hidden by Azure effectiveRoutes; no inferred candidates",
                       noDataPlaneClaim=True)
        sweep.save("sweep-verdict.json", summary)
        lease.update(state="completed" if complete else "rolled-back" if restored else "blocked",
                     verdict=verdict, completedAtUtc=sweep.utc(), children=[], evidence=str(OUT))
        control.save(control.LEASE, lease)
        print(f"FINAL {verdict} states={list(states)} calls={lease['toolCallsUsed']} "
              f"mutations={lease['mutationsUsed']} restored={restored}", flush=True)


if __name__ == "__main__":
    main()
