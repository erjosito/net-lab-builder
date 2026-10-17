"""Render matched B2B measurements without substituting route selection for traffic."""
import argparse
import csv
import json
import pathlib
import re

import design_b2b
import design_comparison

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "show-output"
PUBLIC = "https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/"
CASES = (
    ("Mixed baseline", "b2b-mixed-baseline-20261017", "baseline"),
    ("All B2B baseline", "b2b-enabled-baseline-20261017", "baseline"),
    ("A, NVA policy only", "b2b-A-20261017", "A"),
    ("A, plus JP workload UDR", "b2b-A-20261017", "A-workload-UDR"),
    ("B1, ExpressRoute initial", "b2b-B1-20261017", "B1"),
    ("B1, JP direct prefix withdrawn", "b2b-B1-20261017", "B1-withdrawn"),
    ("B1, JP direct prefix returned", "b2b-B1-20261017", "B1-returned"),
    ("B1 one-ASN, initial", "b2b-B1-one-ASN-20261017", "B1-one-ASN"),
    ("B1 one-ASN, withdrawn", "b2b-B1-one-ASN-20261017", "B1-one-ASN-withdrawn"),
    ("B1 one-ASN, returned", "b2b-B1-one-ASN-20261017", "B1-one-ASN-returned"),
    ("B1, VPN HRP", "b2b-B1-VPN-20261017", "B1-VPN"),
    ("B2, zero extra EU/US prepends", "b2b-B2-20261017", "B2"),
    ("Original mixed state restored", "b2b-restore-mixed-20261017", "restored"),
    ("Independent original-state verification", "b2b-independent-verify-20261017", "independent-verification"),
)
PRIMARY = {"A": CASES[3], "B1": CASES[6], "B2": CASES[11]}


def load(case):
    _, folder, label = case
    return json.loads((OUTPUT / folder / label / "scenario-result.json").read_text(encoding="utf-8"))


def link(case, name):
    return PUBLIC + case[1] + "/" + case[2] + "/" + name


def selected_details(text, prefix):
    selected = design_comparison.selected_route(text, prefix)
    current, block, active = None, [], False
    for line in text.splitlines():
        match = re.match(r"(\d+\.\d+\.\d+\.\d+/\d+)\s", line)
        if match:
            current = match[1]
        if active and (match or "unicast [" in line):
            break
        if current == prefix and re.search(r"\]\s+[*!]\s+\(", line):
            active = True
        elif active:
            block.append(line.strip())
    resolution = next((x for x in block if x.startswith(("via ", "dev "))), "unresolved")
    hop = next((x.split(":", 1)[1].strip() for x in block if x.startswith("BGP.next_hop:")), "n/a")
    selected.update(resolution=resolution, nextHop=hop)
    return selected


def nva_table(data, site):
    text = data["nvas"][site]["birdRoutes"]["stdout"]
    lines = ["| Prefix | Protocol | BGP next hop | BIRD resolution | ASPath | LP | Marker |",
             "|---|---|---|---|---|---|---|"]
    for original in data["selected"][site]:
        row = selected_details(text, original["prefix"])
        assert all(row[k] == original[k] for k in original)
        path = " ".join(map(str, row["asPath"])) or "n/a"
        lp = row["localPreference"] if row["localPreference"] is not None else "n/a"
        lines.append(f"| `{row['prefix']}` | `{row['protocol']}` | `{row['nextHop']}` | "
                     f"`{row['resolution']}` | `{path}` | {lp} | `{row['selectionMarker']}` |")
    assert len(lines) == 9
    return "\n".join(lines)


def firewall_table(case, site):
    rows = json.loads((OUTPUT / case[1] / case[2] / (case[2] + "-" + site + "-table2.json")).read_text())
    lines = ["| Prefix | ASPath | NextHopType |", "|---|---|---|"]
    for row in rows:
        path = "`" + row["ASPath"] + "`" if row["ASPath"] else "empty"
        lines.append(f"| `{row['Prefix']}` | {path} | {row['NextHopType']} |")
    return "\n".join(lines)


def block(text, marker):
    begin = text.index(marker)
    brace = text.index("{", begin)
    depth = 0
    for i in range(brace, len(text)):
        depth += (text[i] == "{") - (text[i] == "}")
        if depth == 0:
            return text[begin:i + 1]
    raise ValueError("Unclosed BIRD block")


def matrix(data):
    names = {ip: vm.replace("probe-", "").replace("router-", "")
             for vm, ip in design_b2b.ENDPOINTS.items()}
    ips = tuple(names)
    cells = {(c["source"], c["destination"]): c for c in data["traffic"]["cells"]}
    lines = ["| Source / destination | " + " | ".join(names[ip] for ip in ips) + " |",
             "|---|" + "---|" * len(ips)]
    for src in ips:
        values = []
        for dst in ips:
            if src == dst:
                values.append("-")
            else:
                cell = cells[src, dst]
                values.append(("P" if cell["tcp"] == "PASS" else "F") + "/" +
                              ("P" if cell["icmp"] == "PASS" else "F"))
        lines.append("| " + names[src] + " | " + " | ".join(values) + " |")
    return "\n".join(lines)


def summary(cases):
    lines = ["| Measured state | TCP / 42 | ICMP / 42 |", "|---|---|---|"]
    for case in cases:
        data = load(case)["traffic"]
        lines.append(f"| [{case[0]}]({link(case, 'traffic-summary.json')}) | "
                     f"{data['tcpPass']} | {data['icmpPass']} |")
    return "\n".join(lines)


def winners(cases):
    lines = ["| State | EU Japan path | US Japan path |", "|---|---|---|"]
    for case in cases:
        rows = load(case)["firewalls"]["rows"]
        values = []
        for site in ("eu", "us"):
            row = next(r for r in rows if r["observer"] == site and r["prefix"] == "10.130.0.0/24")
            values.append("`" + row["asPath"] + "` (" + row["nextHopType"] + ")")
        lines.append("| " + case[0] + " | " + " | ".join(values) + " |")
    return "\n".join(lines)


def observation_table(cases):
    pairs = (("10.110.0.10", "10.130.0.10"), ("10.130.0.10", "10.110.0.10"),
             ("10.10.0.10", "10.130.0.10"), ("10.130.0.10", "10.10.0.10"))
    lines = ["| State / packet direction | EU | US | JP | CN |", "|---|---|---|---|---|"]
    for case in cases:
        values = json.loads((OUTPUT / case[1] / case[2] / "path-observations.json").read_text())
        for src, dst in pairs:
            entries = []
            for site in ("eu", "us", "jp", "cn"):
                seen = set()
                for key, count in values["router-" + site]["counts"].items():
                    interface, direction, source, destination, protocol = key.split("|")
                    if count and source == src and destination == dst:
                        seen.add(interface + " " + direction)
                entries.append(", ".join(sorted(seen)) or "not observed")
            lines.append("| " + case[0] + f": `{src}` -> `{dst}` | " + " | ".join(entries) + " |")
    return "\n".join(lines)


def design_section(name, case):
    data = load(case)
    lines = [f"## {name}: " + {"A": "Microsoft backbone preferred", "B1": "Customer backbone through HRP",
                              "B2": "Customer backbone through AS-path control"}[name]]
    if name == "A":
        lines.append("All hubs use `ASPath`. The three Azure-facing NVAs accept foreign DC and spoke routes "
                     "from Azure at LP 400. EU/US/JP add three extra own-AS copies for nonlocal DC exports. "
                     "The export source guard prevents feeding an Azure-learned best route back into Azure. "
                     "CN remains mesh-only, so this is not an all-prefix Microsoft-only design.\n\n"
                     "The primary capture includes the five-prefix Japan workload UDR to `10.130.0.4`; "
                     "the policy-only control is measured separately. The UDR covers EU/US DCs and all "
                     "three Azure spokes, not CN's transport endpoint.")
    elif name == "B1":
        lines.append("The primary capture uses `ExpressRoute` on all hubs, the original three extra "
                     "EU/US nonlocal prepends, no extra Japan prepends, and spoke-only Azure imports. "
                     "It is the final state after withdrawing and restoring only Japan's direct "
                     "`10.130.0.0/24` Azure export. Mesh exports and tunnel configurations are unchanged.\n\n"
                     "The initial state, withdrawal, return, one-ASN-difference replay and `VpnGateway` "
                     "HRP control are reported separately below. A final local winner must not be "
                     "presented as proof that the HRP change alone produced it.")
    else:
        lines.append("All hubs use `ASPath`. EU/US nonlocal extra prepends are removed; Japan still has "
                     "no extra prepends. Azure imports remain spoke-only, so NVAs keep foreign DCs on "
                     "their mesh. Removing prepends shortens the local offer; this is not a claim that "
                     "adding prepends everywhere favors the customer backbone.")
    lines.append(f"Matched state: [{case[0]}]({link(case, 'scenario-result.json')}). "
                 "Full BIRD configurations: " + ", ".join(
                     f"[{s.upper()}]({link(case, 'router-' + s + '.conf')})"
                     for s in ("eu", "us", "jp", "cn")) + ".")
    for site in ("eu", "jp"):
        lines.extend([f"### {name}: complete {site.upper()} firewall table", firewall_table(case, site)])
    for site in ("eu", "jp", "cn"):
        lines.extend([f"### {name}: {site.upper()} selected NVA routes", nva_table(data, site)])
    lines.extend([f"### {name}: captured EU export policy",
                  "```bird\n" + block(data["sources"]["eu"]["config"], "filter azure_export {") + "\n```",
                  f"### {name}: all 42 traffic directions", matrix(data)])
    return "\n\n".join(lines)


def validate():
    for case in CASES:
        data = load(case)
        traffic = data["traffic"]
        assert len(traffic["cells"]) == 42 and traffic["expectedDirections"] == 42
        expected = {(a, b) for a in design_b2b.ENDPOINTS.values()
                    for b in design_b2b.ENDPOINTS.values() if a != b}
        assert {(c["source"], c["destination"]) for c in traffic["cells"]} == expected
        assert traffic["tcpPass"] == sum(c["tcp"] == "PASS" for c in traffic["cells"])
        assert traffic["icmpPass"] == sum(c["icmp"] == "PASS" for c in traffic["cells"])
        assert data["wan"]["properties"]["allowBranchToBranchTraffic"] is True
        assert data["firewalls"]["stable"] and data["firewalls"]["minimumSnapshotSpacingSeconds"] >= 120
        expected_keys = {(s, p) for s in ("eu", "us", "jp") for p in design_b2b.comparison.guest_prefixes()}
        assert {(r["observer"], r["prefix"]) for r in data["firewalls"]["rows"]} == expected_keys
        if case not in (CASES[0], CASES[-2], CASES[-1]):
            assert all(h["hub"]["properties"]["allowBranchToBranchTraffic"] is True
                       for h in data["hubs"].values())
        observations = json.loads((OUTPUT / case[1] / case[2] / "path-observations.json").read_text())
        assert all(not v["expired"] and v["counts"] and not any(v["unparsed"])
                   and "0 packets dropped by kernel" in v["stderr"] for v in observations.values())
    before, after = load(CASES[0]), load(CASES[-1])
    assert before["firewalls"]["rows"] == after["firewalls"]["rows"]
    assert all(design_comparison.source_unchanged(before["sources"][s], after["sources"][s])
               for s in design_b2b.snapshot.ALL_SITES)
    for a, b in ((CASES[4], CASES[6]), (CASES[7], CASES[9])):
        initial, returned = load(a), load(b)
        for s in design_b2b.snapshot.ALL_SITES:
            assert design_comparison.source_unchanged(initial["sources"][s], returned["sources"][s])
            assert initial["sources"][s]["config"] == returned["sources"][s]["config"]
        for s in ("eu", "us", "jp"):
            assert initial["hubs"][s]["preference"] == returned["hubs"][s]["preference"]
    power = json.loads((OUTPUT / "b2b-power-stop-20261017" / "power-verdict.json").read_text())
    assert power["verdict"] == "PASS" and power["restored"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blog", type=pathlib.Path)
    args = parser.parse_args()
    validate()
    folder = OUTPUT / "b2b-summary-20261017"
    folder.mkdir(exist_ok=True)
    before, enabled = load(CASES[0]), load(CASES[1])
    identical = before["firewalls"]["rows"] == enabled["firewalls"]["rows"]
    changed = []
    original = {(c["source"], c["destination"]): c for c in before["traffic"]["cells"]}
    for c in enabled["traffic"]["cells"]:
        a = original[c["source"], c["destination"]]
        if (a["tcp"], a["icmp"]) != (c["tcp"], c["icmp"]):
            changed.append((c["source"], c["destination"]))
    introduction = (
        "The matched mixed-setting and all-enabled baselines have "
        f"{'identical' if identical else 'different'} DC-prefix firewall winners and "
        f"**{len(changed)} changed traffic outcomes out of 42 directional cells**. "
        "WAN-level B2B was already enabled; only Japan's hub flag changes from false to true. "
        "Original NVA sources, metadata, HRPs and PrivateTraffic routing intent are held constant. "
        "This isolates the flag for the baseline; it does not prove that the flag is irrelevant "
        "for every route history or supported topology.")
    findings = (
        "**The B1 history dependency also reproduces with B2B enabled on every hub.** "
        "Under ExpressRoute HRP, EU/US initially retain remote Japan length three. Withdrawing "
        "only Japan's direct export selects local length-five paths; returning the export "
        "leaves those longer local paths selected. The separate EU length-four versus remote "
        "length-three control repeats the dependency. Source bytes/metadata and HRPs are identical "
        "between the initial and returned states. The mixed B2B flags therefore do not explain "
        "away that observation.\n\n"
        "Traffic and routing are separate findings: B1's returned three-prepend state still "
        "passes only 28/42 TCP and 32/42 ICMP directions. VPN HRP selects longer local Japan "
        "paths in its measured state, with 32/42 TCP and 34/42 ICMP passes; that sequential "
        "control is not proof of a universal ER/VPN difference independent of route history. "
        "B2 passes 36/42 for both: all six failures are Japan workload <-> Azure spoke directions. "
        "A with the workload UDR passes 38/42 TCP and 40/42 ICMP; EU/US DC -> Japan workload "
        "fails both protocols, and the reverse initiated DC traffic fails TCP but passes ICMP. "
        "None is an all-pairs forwarding success.")
    methodology = (
        "Every measured state has full firewall effective tables for all three hubs, paired stable "
        "DC-prefix winners at least 120 seconds apart, full BIRD sources and selected/alternative routes "
        "on all four routers, and an explicitly sourced 42-direction TCP/ICMP matrix. The seven endpoints "
        "are four synthetic DCs and three Azure spokes: 12 DC-to-DC, 24 DC/spoke and six spoke-to-spoke "
        "directions. TCP requires HTTP 200 on the private port 5201 listener and matching local/remote "
        "addresses; ICMP uses source-bound ping. P/F below means TCP PASS / ICMP FAIL.\n\n"
        "Bounded tcpdump captures on every router observe inner test packets on physical, WireGuard "
        "and XFRM interfaces; management traffic and encrypted transport payloads are not collected. "
        "The interface observations are not a throughput measurement or a complete symmetry proof. "
        "Failed SYNs/ICMP attempts can still appear in a capture. In particular, A's policy-only "
        "EU/JP DC reachability is not proof of the intended Virtual WAN path: the measured EU-to-JP "
        "DC packets appeared on EU's physical interfaces, but the expected Japan NVA/XFRM segment "
        "was not observed; the reverse initiated DC traffic was not observed on the NVAs. "
        "The peered underlay and workload routing must be considered rather than treating an HTTP "
        "success as proof of Microsoft interhub transit. `!` in a BIRD table is a kernel-export "
        "failure marker, not healthy Linux forwarding. A collector verdict of PASS means complete "
        "measurements and exact configuration closure, not 42 successful traffic directions.\n\n"
        "During B1's three-prepend withdrawal, Japan's firewall exposes two equal-length remote "
        "Japan-prefix entries, one through EU and one through US. All twelve hub/prefix keys remain "
        "present, but there are thirteen rows. The inherited single-winner check therefore records "
        "`complete: false`; this flag is retained in raw evidence and does not mean a prefix was "
        "missing in that state.")
    report = "\n\n".join([
        "# Secured all-hub branch-to-branch rerun, 17 October 2026", introduction, findings,
        "## Traffic outcomes", summary(CASES), "## Methodology and limitations", methodology,
        "## B1 Japan-prefix selection sequence", winners(CASES[4:11]),
        "## Packet-interface observations", observation_table((CASES[2], *PRIMARY.values())),
        *(design_section(name, case) for name, case in PRIMARY.items()),
        "## Original state restored",
        "Each policy controller restored the exact BIRD bytes, owner/mode/nanosecond modification time "
        "and original all-enabled hub settings before the next variant. The final controller restored "
        "the pre-test mixed hub flags and HRPs. An independent full capture matched the original BIRD "
        "sources and paired firewall winners. Only VMs started for this rerun were returned to their "
        "original power states. The temporary A route table was removed and its original subnet "
        "association verified. No IPsec or WireGuard configuration was changed.\n\n"
        f"[Independent state evidence]({link(CASES[-1], 'scenario-result.json')}); "
        f"[power restoration]({PUBLIC}b2b-power-stop-20261017/power-verdict.json).",
    ]) + "\n"
    (folder / "README.md").write_text(report, encoding="utf-8")
    with (folder / "traffic.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("state", "source", "destination", "TCP", "ICMP"))
        for case in CASES:
            for cell in load(case)["traffic"]["cells"]:
                writer.writerow((case[0], cell["source"], cell["destination"], cell["tcp"], cell["icmp"]))
    if args.blog:
        post = args.blog / "2026-10-vwan-sdwan-three-hub"
        old = (post / "README.md").read_text(encoding="utf-8")
        topology = old.split("## One topology, two possible backbones\n", 1)[1].split("### How to read the tables", 1)[0]
        commands = old.split("## Commands", 1)[1] if "## Commands" in old else ""
        article = "\n\n".join([
            "# Microsoft or customer backbone? Three Virtual WAN routing designs tested",
            "**A prefers Microsoft's backbone; B1 and B2 prefer the customer backbone.** Azure's hub "
            "exit selection and the NVA's onward selection must agree. This rerun enables branch-to-branch "
            "at WAN level and on all three hubs and measures both routes and workload forwarding.",
            introduction,
            findings,
            "## One topology, two possible backbones\n" + topology.strip(),
            "## What the three designs configure",
            "| Design | All-hub HRP | NVA policy |\n|---|---|---|\n"
            "| A: Microsoft | ASPath | Foreign DC/spoke Azure imports at LP 400; three nonlocal prepends on EU/US/JP; optional JP workload UDR measured separately |\n"
            "| B1: customer | ExpressRoute; VpnGateway measured separately | Spoke-only Azure imports; three extra nonlocal EU/US prepends; JP none |\n"
            "| B2: customer | ASPath | Spoke-only Azure imports; zero extra EU/US/JP prepends |",
            "The [documented HRP ordering](https://learn.microsoft.com/en-us/azure/virtual-wan/about-virtual-hub-routing-preference) "
            "prioritizes locality under ExpressRoute/VPN and path length under ASPath. The B1 initial, "
            "withdrawn and returned states below expose the measured selection history rather than "
            "assuming every HRP update recomputes the same winner.",
            "## Forwarding results, not just routing tables", summary(CASES[:-2]), methodology,
            "## How to read the captured tables",
            "Each design below contains the full EU and Japan firewall table, not a filtered supporting "
            "prefix. US is collected too and available in the matched evidence. EU, Japan and CN NVA "
            "tables include all seven DC/spoke prefixes. BGP next hop and BIRD resolution are distinct "
            "attributes. `n/a` means absent on a static route; `empty` means a blank firewall AS path. "
            "The primary A state includes the workload UDR; primary B1 is the returned three-prepend state.",
            *(design_section(name, case) for name, case in PRIMARY.items()),
            "## B1 initial selection and controlled route return", winners(CASES[4:11]),
            "The three-prepend control offers local length five versus remote length three; "
            "the separate EU two-prepend control offers local four versus remote three. "
            "Only Japan's direct Azure prefix export is withdrawn; mesh exports and tunnels stay up. "
            "The earlier mixed-setting controls demonstrated different winners with identical "
            "configuration before/after re-advertisement. These new all-enabled results must be read "
            "alongside them, not used to invent an Azure-internal race/cache explanation. "
            "The published two-or-more-longer HRP caveat does not by itself explain every one-ASN case.",
            "## Packet-interface evidence", observation_table((CASES[2], *PRIMARY.values())),
            "## Conclusions and boundaries",
            "Enabling Japan's hub flag alone did not change this baseline's firewall winners or traffic "
            "outcomes. The configuration inconsistency therefore was not sufficient to explain those "
            "failures. The per-design traffic matrices above establish exactly which workload "
            "directions passed; selected routes alone do not establish a successful backbone design. "
            "Residual failures and any `!` flags remain failures, not success-shaped exceptions. "
            "No bandwidth advantage was measured. Configuration, original hub settings and original "
            "VM power states were restored after the rerun.",
            "[Full rerun report and raw evidence](" + PUBLIC + "b2b-summary-20261017/README.md). "
            "Earlier mixed-setting results and their original verdicts remain linked in "
            "[references.md](./references.md).",
            ("## Commands" + commands) if commands else
            "## Retrieve effective routes\n\n"
            "With routing intent, query the firewall, not a spoke connection:\n\n"
            "```powershell\naz network vhub get-effective-routes -n $hub -g $rg `\n"
            "  --resource-type 'AzureFirewalls' `\n"
            "  --resource-id $(az network vhub show -g $rg -n $hub --query 'azureFirewall.id' -o tsv) `\n"
            "  --query 'value[].{Prefix:addressPrefixes[0], ASPath:asPath, NextHopType:nextHopType}' -o table\n```\n\n"
            "Without routing intent, query the VNet connection using the singular discriminator:\n\n"
            "```powershell\n$connectionId = az network vhub connection show -g $rg --vhub-name $hub `\n"
            "  -n $connection --query id -o tsv\n"
            "az network vhub get-effective-routes -n $hub -g $rg `\n"
            "  --resource-type 'HubVirtualNetworkConnection' --resource-id $connectionId -o json\n```\n\n"
            "On each NVA, retain `birdc show route table lab4 all`, "
            "`birdc show route export azure_0 all`, `birdc show route export azure_1 all`, "
            "`ip -j route show table main`, and the full BIRD configuration. CN has no Azure peers.",
        ]) + "\n"
        (post / "README.md").write_text(article, encoding="utf-8")
        refs = post / "references.md"
        text = "# References and exact all-hub B2B evidence map\n\n"
        text += "Current measurements: 17 October 2026. Every current A/B1/B2 table and traffic matrix uses the all-enabled rerun, not the historical mixed-setting revision.\n\n"
        text += "[Full rerun report](" + PUBLIC + "b2b-summary-20261017/README.md) and [all 588 directional cells](" + PUBLIC + "b2b-summary-20261017/traffic.csv).\n\n"
        text += "## Primary matched captures\n\n"
        for name, case in PRIMARY.items():
            text += f"### {name}: {case[0]}\n\n"
            text += f"[Full scenario]({link(case, 'scenario-result.json')}); [selected routes]({link(case, 'selected-routes.json')}); [42-direction traffic]({link(case, 'traffic-summary.json')}); [packet observations]({link(case, 'path-observations.json')}).\n\n"
            text += "| Site | Complete BIRD configuration | Full firewall table |\n|---|---|---|\n"
            for s in ("eu", "us", "jp", "cn"):
                firewall = (f"[table2.txt]({link(case, case[2] + '-' + s + '-table2.txt')})"
                            if s != "cn" else "No hub attachment")
                text += f"| {s.upper()} | [router-{s}.conf]({link(case, 'router-' + s + '.conf')}) | {firewall} |\n"
            text += "\nFull firewall JSON is alongside the text with a `.json` suffix. Raw BIRD selections and alternatives are in `router-{site}-bird-routes.txt`; both Azure export views are in `router-{site}-export-azure_{0,1}.txt`. CN has no Azure peers. NVA route snapshots also retain Linux routes, policy rules and lookups. The post renders all EU/JP firewall entries and all seven prefixes on EU/JP/CN, including `!` kernel-export failures.\n\n"
        text += "## Additional controls and closure\n\n"
        for case in CASES:
            text += f"- [{case[0]}]({link(case, 'scenario-result.json')}).\n"
        text += "\n[Original VM power inventory restored](" + PUBLIC + "b2b-power-stop-20261017/power-verdict.json). Exact source bytes/metadata, original mixed hub flags/HRPs and original paired firewall winners were independently restored; traffic returned to 28/42 TCP and 32/42 ICMP. Temporary A route-table cleanup is captured in the A controller's restore evidence.\n\n"
        text += "Collector PASS means complete evidence and exact configuration closure, not all traffic passed. No throughput, failover or universal path-symmetry claim follows. The packet observations explicitly expose cases where reachability does not establish the intended Virtual WAN traversal.\n\n"
        text += "## Historical mixed-setting evidence, not current table sources\n\n"
        for label, path in (
            ("Original A experiment and forwarding limitations", "backbone-policy-design-20261016/README.md"),
            ("Original A/B comparison, including B1 INCONCLUSIVE and B2 BLOCKED verdicts", "ab-design-comparison-20261016/README.md"),
            ("Original three-prepend route-history control", "hrp-reselection-control-20261017/README.md"),
            ("Original one-ASN-difference route-history control", "hrp-one-asn-control-20261017/README.md"),
            ("Independent exact reset after the historical B2 blocked proof", "ab-final-recovery-verification-20261016/verification-verdict.json"),
        ):
            text += f"- [{label}]({PUBLIC + path}).\n"
        text += "\nThose original verdicts are preserved; the later successful controls do not retroactively turn blocked measurements into passes. Their source publication is retained in erjosito/net-lab-builder#13, erjosito/net-lab-builder#14 and erjosito/net-lab-builder#15.\n\n"
        text += "## Commands, implementation and official references\n\n"
        base = "https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/deploy/"
        for name in ("design_b2b.py", "b2b_report.py", "design_backbone.py", "design_snapshot.py", "design_comparison.py"):
            text += f"- [{name}]({base + name}).\n"
        text += "- [Hub routing preference](https://learn.microsoft.com/en-us/azure/virtual-wan/about-virtual-hub-routing-preference).\n"
        text += "- [BGP peering considerations, including branch-to-branch](https://learn.microsoft.com/en-us/azure/virtual-wan/scenario-bgp-peering-hub#benefits-and-considerations).\n"
        text += "- [Routing intent](https://learn.microsoft.com/en-us/azure/virtual-wan/about-routing-intent).\n"
        text += "- [Effective routes](https://learn.microsoft.com/en-us/azure/virtual-wan/effective-routes-virtual-hub).\n"
        text += "- [BIRD 2 documentation](https://bird.network.cz/?get_doc&v=20&f=bird.html).\n\n"
        text += "The diagnostic discriminators remain `AzureFirewalls` (plural) for secured firewall routes and `HubVirtualNetworkConnection` (singular) for unsecured connection routes. The topology SVG is unchanged and represents connectivity, not proof that every drawn path carries test traffic.\n"
        refs.write_text(text, encoding="utf-8")
    print("PASS: complete route/traffic/path evidence rendered; 14 states, 588 directional cells")


if __name__ == "__main__":
    main()
