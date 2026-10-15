"""Read-only, explicitly sourced 4x3 bidirectional TCP/ICMP forwarding checks."""
import argparse
import json
import re

import aspath_sweep as sweep
import control
import vpn_sdwan_boundary as boundary


DC = ["10.110.0.10", "10.120.0.10", "10.130.0.10", "10.140.0.4"]
SPOKES = ["10.10.0.10", "10.20.0.10", "10.30.0.10"]
PROBES = {
    **{f"probe-spoke-{site}": (ip, DC) for site, ip in zip(sweep.SITES, SPOKES)},
    **{f"probe-dc-{site}": (ip, SPOKES) for site, ip in zip(sweep.SITES, DC[:3])},
    "router-cn": (DC[3], SPOKES)
}


def script(source, destinations):
    return f"""#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import datetime,json,subprocess
source={source!r}
cells=[]
for destination in {destinations!r}:
 def run(args,timeout=10):
  r=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
  return dict(exitCode=r.returncode,stdout=r.stdout.strip(),stderr=r.stderr.strip())
 route=run(['ip','-j','route','get',destination,'from',source])
 icmp=run(['ping','-I',source,'-c','2','-W','1',destination])
 tcp=run(['curl','--interface',source,'--noproxy','*','-sS','--connect-timeout','3',
          '--max-time','5','--output','/dev/null','--write-out','%{{http_code}} %{{local_ip}} %{{remote_ip}}',
          'http://'+destination+':5201/'])
 cells.append(dict(source=source,destination=destination,route=route,
  tcp='PASS' if tcp['exitCode']==0 and tcp['stdout']=='200 '+source+' '+destination else 'FAIL',
  icmp='PASS' if icmp['exitCode']==0 else 'FAIL',tcpDetail=tcp,
  icmpExitCode=icmp['exitCode']))
print('FORWARDING_COMPLETE '+json.dumps(dict(timestampUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
 cells=cells),separators=(',',':')))
PY
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lease", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--baseline-proof", action="store_true")
    parser.add_argument("--secured", action="store_true")
    args = parser.parse_args()
    control.LEASE = control.RUNTIME / args.lease
    lease = control.guard(False)
    if lease.get("toolCallsUsed", 0):
        raise RuntimeError("Fresh read-only lease required")
    sweep.SUB = control.account_id()
    sweep.OUT = control.ROOT.parent / "show-output" / args.out
    sweep.CURRENT = sweep.OUT
    if sweep.OUT.exists():
        raise RuntimeError("Fresh evidence required")
    commands, errors, cells = [], [], []
    source_proofs, route_proof = {}, None
    sweep.RESTORING = True
    sweep.RESTORE_DEADLINE = None
    for name, (source, destinations) in PROBES.items():
        path = control.RUNTIME / f"forwarding-{name}.sh"
        path.write_text(script(source, destinations), encoding="utf-8", newline="\n")
        commands.append((["vm", "run-command", "invoke", "-g", control.RG, "-n", name,
                          "--command-id", "RunShellScript", "--scripts", "@" + str(path)],
                         "forwarding-" + name))
    try:
        if args.baseline_proof:
            sweep.CURRENT = sweep.OUT / "baseline"
            source_proofs = boundary.invoke_all("baseline-validation")
            firewall_ids = ({
                site: (f"/subscriptions/{sweep.SUB}/resourceGroups/{control.RG}"
                       f"/providers/Microsoft.Network/azureFirewalls/fw-{site}")
                for site in sweep.SITES
            } if args.secured else None)
            route_proof = sweep.capture("baseline", 0, firewall_ids=firewall_ids, parallel=True)
            if route_proof["verdict"] != "PASS":
                raise RuntimeError("Restored effective routes incomplete or unstable")
            sweep.CURRENT = sweep.OUT
        values = control.az_batch(commands, timeout=300, closure=True)
        for (command, label), value in zip(commands, values):
            sweep.save(label + ".json", dict(command=command, result=value))
            messages = "\n".join(x.get("message", "") for x in (value or {}).get("value", []))
            matches = re.findall(r"^FORWARDING_COMPLETE (\{.*\})$", messages, re.M)
            if len(matches) != 1:
                raise RuntimeError(f"{label}: explicit complete output missing")
            result = json.loads(matches[0])
            name = command[command.index("-n") + 1]
            source, destinations = PROBES[name]
            actual = result["cells"]
            if ({(c["source"], c["destination"]) for c in actual} !=
                    {(source, destination) for destination in destinations} or
                    len(actual) != len(destinations)):
                raise RuntimeError(f"{label}: incomplete or duplicate directional cells")
            cells.extend(actual)
    except Exception as exc:
        errors.append(str(exc))
        print(f"FORWARDING ERROR {exc}", flush=True)
    finally:
        lease = control.guard(False)
        complete = len(cells) == 24 and not errors
        tcp = sum(c["tcp"] == "PASS" for c in cells)
        icmp = sum(c["icmp"] == "PASS" for c in cells)
        verdict = "PASS" if complete and tcp == icmp == 24 else "FAIL" if complete else "INCONCLUSIVE"
        sweep.save("forwarding-verdict.json", dict(
            timestampUtc=sweep.utc(), verdict=verdict, traffic=cells, errors=errors,
            configurationBaselineVerified=(len(source_proofs) == 4 and
                                           route_proof is not None and route_proof["verdict"] == "PASS"),
            sourceProofs=source_proofs, routeProof=route_proof,
            tcpPass=tcp, icmpPass=icmp, expectedDirectionalCells=24,
            callsUsed=lease["toolCallsUsed"], mutationsUsed=0, children=[],
            pathSymmetry="Not established by reachability alone",
            restore="Read-only probes; no configuration changes"))
        lease.update(state="completed", verdict=verdict, completedAtUtc=sweep.utc(),
                     children=[], evidence=str(sweep.OUT))
        control.save(control.LEASE, lease)
        print(f"FINAL {verdict} TCP={tcp}/24 ICMP={icmp}/24", flush=True)


if __name__ == "__main__":
    main()
