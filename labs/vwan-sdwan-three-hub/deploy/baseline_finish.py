"""Finish asynchronous B0 route reads and persist the failure verdict."""
import concurrent.futures as futures
import json
import re
import time

import baseline as b
import guest
import effective_routes

b.OUT = b.ROOT.parent / "show-output" / "b0-unsecured-er" / "20261014T180438Z"


def route(site, snap, connection=False):
    return effective_routes.collect(b.az, b.SUB, b.control.RG, site,
                                    f"hub-{site}-{'connection-' if connection else ''}{snap}", connection)


def routers():
    sources = {}
    for site in ("eu", "us", "jp", "cn"):
        commands = """date -u +%FT%TZ
sha256sum /etc/bird/bird.conf /var/lib/threehub/activation-files.json
birdc show protocols all
birdc show route table lab4 all
ip rule show
ip route show table all
wg show all endpoints
wg show all transfer
"""
        if site != "cn":
            commands += "birdc show route export azure_0 all\nbirdc show route export azure_1 all\n"
        if site == "jp":
            commands += "swanctl --list-sas\n"
        if site == "cn":
            for target in b.SPOKES:
                commands += f"""
echo PROBE_BEGIN source=10.140.0.4 target={target}
ip route get {target} from 10.140.0.4
ping -I 10.140.0.4 -c 2 -W 2 {target}; echo ICMP_EXIT=$?
curl --interface 10.140.0.4 --noproxy '*' -sS --connect-timeout 3 --max-time 5 -w '\\nHTTP_CODE=%{{http_code}} LOCAL=%{{local_ip}} REMOTE=%{{remote_ip}}\\n' http://{target}:5201/; echo TCP_EXIT=$?
echo PROBE_END
"""
        for target in b.TARGETS + b.SPOKES:
            commands += f"ip route get {target}\n"
        commands += "ip route get 10.140.0.4 mark 0x200\necho B0_END\n"
        encoded = b.base64.b64encode(commands.encode()).decode()
        sources["router-" + site] = f"""#!/bin/bash
set -o pipefail
echo B0_GZIP_BEGIN
echo '{encoded}' | base64 -d | bash 2>&1 | gzip -9 | base64 -w0
echo
echo B0_GZIP_END
"""
    document, params = guest.managed_template(sources, "b0-small-" + b.OUT.name.lower())
    for resource in document["resources"]:
        resource["properties"]["timeoutInSeconds"] = 120
    template = b.RUNTIME / "b0-small-read.json"
    parameter = b.RUNTIME / "b0-small-read.parameters.json"
    template.write_text(json.dumps(document))
    parameter.write_text(json.dumps(params))
    b.save("router-small-exact-scripts.json", sources)
    b.az(["deployment", "group", "create", "-g", b.control.RG, "--name", "b0-small-read",
          "--template-file", str(template), "--parameters", "@" + str(parameter)], "router-small-read-batch")
    for name in sources:
        response = b.rest(f"https://management.azure.com/subscriptions/{b.SUB}/resourceGroups/{b.control.RG}"
                          f"/providers/Microsoft.Compute/virtualMachines/{name}/runCommands/guest-b0-small-{b.OUT.name.lower()}",
                          f"guest-{name}-small-get", query={"api-version": "2024-03-01", "$expand": "instanceView"})
        b.decode(name, response)


def main():
    before = time.monotonic()
    with futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {site: pool.submit(route, site, "full-snapshot1") for site in ("eu", "us", "jp")}
        router_job = pool.submit(routers)
        initial = {site: job.result() for site, job in jobs.items()}
        router_job.result()
    initial_connections = {site: route(site, "snapshot1", True) for site in ("eu", "us", "jp")}
    before = time.monotonic()
    wait = 125 - (time.monotonic() - before)
    if wait > 0:
        time.sleep(wait)
    with futures.ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {site: pool.submit(route, site, "full-snapshot2") for site in ("eu", "us", "jp")}
        final = {site: job.result() for site, job in jobs.items()}
    final_connections = {site: route(site, "snapshot2", True) for site in ("eu", "us", "jp")}
    matrix, bgp, winners, stability = [], {}, {}, {}
    for name in ["probe-spoke-eu", "probe-spoke-us", "probe-spoke-jp",
                 "probe-dc-eu", "probe-dc-us", "probe-dc-jp", "router-cn"]:
        path = b.OUT / f"guest-{name}.txt"
        text = path.read_text() if path.exists() else ""
        for block in text.split("PROBE_BEGIN ")[1:]:
            block = block.split("PROBE_END")[0]
            source, target = re.search(r"source=(\S+) target=(\S+)", block).groups()
            matrix.append({"source": source, "destination": target, "tcp": "PASS" if "TCP_EXIT=0" in block else "FAIL",
                           "icmp": "PASS" if "ICMP_EXIT=0" in block else "FAIL", "evidence": path.name})
    for site in ("eu", "us", "jp", "cn"):
        path = b.OUT / f"guest-router-{site}.txt"
        text = path.read_text() if path.exists() else ""
        protocols = re.findall(r"^(mesh_\S+|azure_\S+)\s+BGP\s+\S+\s+up\s+\S+\s+Established", text, re.M)
        bgp[site] = {"established": len(protocols), "expected": 3 if site == "cn" else 5}
    for site in ("eu", "us", "jp"):
        value = final[site] or {}
        entries = value.get("value", [])
        if isinstance(entries, dict):
            entries = entries.get("value", [])
        connection = final_connections[site]
        winners[site] = [entry for entry in connection.get("value", []) if
                         any(prefix in b.guest.DC.values() for prefix in entry.get("addressPrefixes", []))]
        stability[site] = {"defaultTableResponsesEqual": initial[site] == final[site],
                           "defaultTableRouteCount": len(entries),
                           "winnerStabilityProven": bool(winners[site]) and initial_connections[site] == final_connections[site]}
    summary = {"timestampUtc": b.utc(), "scenario": "B0", "verdict": "FAIL" if any(cell["tcp"] == "FAIL" or cell["icmp"] == "FAIL" for cell in matrix) else "INCONCLUSIVE",
               "winningRoutes": winners, "winningRouteSource": "HubVirtualNetworkConnection effectiveRoutes",
               "stableSnapshots": stability, "bgp": bgp,
               "routePreferenceVerdict": "PASS" if all(x["winnerStabilityProven"] and len(winners[s]) == 4 for s, x in stability.items()) else "INCONCLUSIVE",
               "traffic": matrix, "tcpPass": sum(cell["tcp"] == "PASS" for cell in matrix),
               "icmpPass": sum(cell["icmp"] == "PASS" for cell in matrix),
               "expectedDirectionalCells": 24, "configurationMutations": 0,
               "packetCaptureVisibility": "UNAVAILABLE: initial router output exceeded instanceView 4096-byte limit; no path/symmetry or no-SNAT claim",
               "competitors": "BIRD full lab4 and exports are ingress evidence, not raw Azure losing paths",
               "restore": "No routing/service/configuration writes. Bounded tcpdump exited before initial batch completion; no children.",
               "children": [], "collectorErrors": b.FAILURES}
    b.save("baseline-verdict.json", summary)
    lease = json.loads(b.LEASE.read_text())
    lease.update(state="completed", verdict=summary["verdict"], completedAtUtc=b.utc(),
                 mutationsUsed=0, children=[], evidence=str(b.OUT.relative_to(b.ROOT.parent)))
    b.LEASE.write_text(json.dumps(lease, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
