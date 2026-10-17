"""Render matched B2B measurements without substituting route selection for traffic."""
import argparse
import csv
import hashlib
import ipaddress
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
DIAGNOSIS = (
    ("B2, before workload UDR", "b2-diagnosis-control-20261017", "B2-before"),
    ("B2, three-spoke workload UDR", "b2-diagnosis-control-20261017", "B2-with-UDR"),
    ("B2, workload UDR removed again", "b2-diagnosis-control-20261017", "B2-reverted"),
)
PRIMARY = {"A": CASES[3], "B1": CASES[6], "B2": DIAGNOSIS[1]}


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


def retained_section(text, title):
    marker = "## " + title + "\n"
    if marker not in text:
        raise ValueError("Missing article section: " + title)
    return re.split(r"(?m)^## ", text.split(marker, 1)[1], maxsplit=1)[0].strip()


def acceptance(traffic):
    expected = {(a, b) for a in design_b2b.ENDPOINTS.values()
                for b in design_b2b.traffic_targets(a, True)}
    cells = [c for c in traffic["cells"] if (c["source"], c["destination"]) in expected]
    if len(cells) != 24 or {(c["source"], c["destination"]) for c in cells} != expected:
        raise ValueError("Incomplete or duplicate DC-Azure acceptance matrix")
    if any(c[k] not in ("PASS", "FAIL") for c in cells for k in ("tcp", "icmp")):
        raise ValueError("Invalid traffic verdict")
    tcp = sum(c["tcp"] == "PASS" for c in cells)
    icmp = sum(c["icmp"] == "PASS" for c in cells)
    return dict(cells=cells, expectedDirections=24, tcpPass=tcp, icmpPass=icmp,
                verdict="PASS" if tcp == icmp == 24 else "FAIL")


def matrix(data):
    names = {ip: vm.replace("probe-", "").replace("router-", "")
             for vm, ip in design_b2b.ENDPOINTS.items()}
    dc = tuple(ip for vm, ip in design_b2b.ENDPOINTS.items() if not vm.startswith("probe-spoke-"))
    spokes = tuple(ip for ip in names if ip not in dc)
    cells = {(c["source"], c["destination"]): c for c in acceptance(data["traffic"])["cells"]}
    tables = []
    for reverse in (False, True):
        lines = ["| DC / Azure spoke | " + " | ".join(names[ip] for ip in spokes) + " |",
                 "|---|" + "---|" * len(spokes)]
        for site in dc:
            values = []
            for spoke in spokes:
                cell = cells[(spoke, site) if reverse else (site, spoke)]
                values.append(("P" if cell["tcp"] == "PASS" else "F") + "/" +
                              ("P" if cell["icmp"] == "PASS" else "F"))
            lines.append("| " + names[site] + " | " + " | ".join(values) + " |")
        tables.append(("**Azure spoke -> DC**" if reverse else "**DC -> Azure spoke**") +
                      "\n\n" + "\n".join(lines))
    return "\n\n".join(tables)


def summary(cases):
    lines = ["| Measured state | TCP / 24 | ICMP / 24 | DC/Azure reachability |", "|---|---|---|---|"]
    for case in cases:
        data = acceptance(load(case)["traffic"])
        lines.append(f"| [{case[0]}]({link(case, 'traffic-summary.json')}) | "
                     f"{data['tcpPass']} | {data['icmpPass']} | {data['verdict']} |")
    return "\n".join(lines)


def effective_match(effective, address):
    candidates = [(ipaddress.ip_network(prefix).prefixlen, row)
                  for row in effective["value"] if row["state"] == "Active"
                  for prefix in row["addressPrefix"]
                  if ipaddress.ip_address(address) in ipaddress.ip_network(prefix)]
    if not candidates:
        raise ValueError("No active effective route for " + address)
    longest = max(length for length, _ in candidates)
    matches = [row for length, row in candidates if length == longest]
    if len(matches) != 1:
        raise ValueError("Ambiguous active effective route for " + address)
    return matches[0]


def diagnosis_section():
    verdict = json.loads((OUTPUT / DIAGNOSIS[0][1] / "diagnosis-verdict.json").read_text())
    reconciled = json.loads((OUTPUT / "b2-diagnosis-reconciled-20261017" / "reconciliation-verdict.json").read_text())
    assert verdict["verdict"] == "INCONCLUSIVE" and verdict["restored"]
    assert reconciled["verdict"] == "PASS" and reconciled["restored"]
    assert reconciled["originalErrors"] == verdict["errors"]
    assert reconciled["semanticSelectionsStable"] and reconciled["nextHopsAndResolutionStable"]
    assert len(reconciled["headlineTimestampChanges"]) == 18
    assert not any(verdict["pending"].values())
    power = json.loads((OUTPUT / "b2-diagnosis-verify-power-stop-20261017" / "power-verdict.json").read_text())
    assert power["verdict"] == "PASS" and power["restored"]
    assert len(power["actual"]) == 10 and all(v["powerState"] == "VM deallocated" for v in power["actual"])
    independent = json.loads((OUTPUT / "b2-diagnosis-independent-20261017" / "baseline-verdict.json").read_text())
    baseline = json.loads((OUTPUT / "b2-diagnosis-baseline-20261017" / "baseline-verdict.json").read_text())
    assert independent["verdict"] == baseline["verdict"] == "PASS"
    a, b = independent["result"], baseline["result"]
    assert a["firewalls"]["rows"] == b["firewalls"]["rows"]
    assert acceptance(a["traffic"])["tcpPass"] == 10 and acceptance(a["traffic"])["icmpPass"] == 14
    for site in design_b2b.snapshot.ALL_SITES:
        assert design_comparison.source_unchanged(a["sources"][site], b["sources"][site])
    states = [load(case) for case in DIAGNOSIS]
    japan = "10.130.0.10"
    spokes = ("10.10.0.10", "10.20.0.10", "10.30.0.10")
    missing = {(a, b) for spoke in spokes for a, b in ((japan, spoke), (spoke, japan))}
    for index, state in enumerate(states):
        expected = 24 if index == 1 else 18
        traffic = acceptance(state["traffic"])
        assert traffic["tcpPass"] == traffic["icmpPass"] == expected
        assert state["traffic"]["expectedDirections"] == 24
        for protocol in ("tcp", "icmp"):
            failed = {(c["source"], c["destination"]) for c in traffic["cells"] if c[protocol] == "FAIL"}
            assert failed == (set() if index == 1 else missing)
        assert state["firewalls"]["rows"] == states[0]["firewalls"]["rows"]
        assert design_b2b.selection_state(state["selected"]) == design_b2b.selection_state(states[0]["selected"])
        assert all(h["preference"] == "ASPath" and
                   h["hub"]["properties"]["allowBranchToBranchTraffic"] is True
                   for h in state["hubs"].values())
        for site in design_b2b.snapshot.ALL_SITES:
            assert design_comparison.source_unchanged(states[0]["sources"][site], state["sources"][site])
            source = state["sources"][site]
            assert source["sha256"] == hashlib.sha256(source["config"].encode()).hexdigest()
        case = DIAGNOSIS[index]
        observations = json.loads((OUTPUT / case[1] / case[2] / "path-observations.json").read_text())
        assert all(not v["expired"] and v["counts"] and not any(v["unparsed"])
                   and "0 packets dropped by kernel" in v["stderr"] for v in observations.values())
        seen = {(parts[3], parts[4]) for key, count in observations["router-jp"]["counts"].items()
                if count and (parts := key.split("|"))[2] == japan and parts[3] in spokes}
        assert seen == ({(spoke, protocol) for spoke in spokes for protocol in ("TCP", "ICMP")}
                        if index == 1 else set())
    before, after = states[0], states[1]
    lines = ["## B2's six Japan-workload failures: a workload steering fault, not an AS-path fault",
             "A focused reversible control sends **only the 24 requested DC/Azure directions**. "
             "The B2 BIRD sources, established peers, HRPs, branch flags, selected NVA routes and "
             "paired firewall winners stay unchanged while we add, then remove, three Azure UDRs:",
             summary(DIAGNOSIS),
             "### The missing route was outside BIRD",
             "The Japan probe's Linux `ip route get` already says `via 10.130.0.4` for each spoke. "
             "But the **Azure NIC effective route table is a separate forwarding layer**. "
             "Without a subnet UDR, its longest matching active route for all three spoke addresses "
             "is `10.0.0.0/8`, next hop `None`. Azure documents `None` as a drop route. "
             "A guest-only static route does not replace that Azure subnet route.\n\n"
             "This explains why looking only at the guest route or at BIRD was misleading. "
             "The emulated on-premises workload is itself an Azure VM, so Azure must also be told "
             "to steer its spoke-bound traffic to the emulated router. This is a lab workload "
             "steering requirement, not evidence that the B2 hub AS-path selection is wrong."]
    route_lines = ["| State | Destination | Active fabric prefix | Source | NextHopType | Next hop IP |",
                   "|---|---|---|---|---|---|"]
    for case, state in zip(DIAGNOSIS, states):
        for address in ("10.10.0.10", "10.20.0.10", "10.30.0.10"):
            row = effective_match(state["workload"]["effectiveRoutes"], address)
            if case == DIAGNOSIS[1]:
                assert row["source"] == "User" and row["nextHopType"] == "VirtualAppliance"
                assert row["nextHopIpAddress"] == ["10.130.0.4"]
            else:
                assert row["addressPrefix"] == ["10.0.0.0/8"] and row["nextHopType"] == "None"
            route_lines.append("| " + case[0] + " | `" + address + "` | `" +
                               ", ".join(row["addressPrefix"]) + "` | " + row["source"] + " | " +
                               row["nextHopType"] + " | " + (", ".join(row["nextHopIpAddress"]) or "-") + " |")
    lines.append("\n".join(route_lines))
    for state in states:
        guest = state["workload"]["guest"]["probe-dc-jp"]
        for address, raw in guest["lookups"].items():
            assert json.loads(raw)[0]["gateway"] == "10.130.0.4", address
    lines.extend([
        "### A minimal, reversible fix",
        "Associate a route table with `vnet-dc-jp/workload` containing only:\n\n"
        "| Destination prefix | Next hop type | Next hop |\n|---|---|---|\n"
        "| `10.10.0.0/24` | VirtualAppliance | `10.130.0.4` |\n"
        "| `10.20.0.0/24` | VirtualAppliance | `10.130.0.4` |\n"
        "| `10.30.0.0/24` | VirtualAppliance | `10.130.0.4` |\n\n"
        "These /24 routes are more specific than the system /8 drop route. No DC prefix is redirected; "
        "in particular CN's WireGuard transport endpoint remains untouched. This focused B2 table "
        "is not A's earlier five-prefix table.",
        "All six Japan-workload/spoke directions change from FAIL to PASS for TCP and ICMP. "
        "Removing the association reproduces the six failures, while the original guest routes "
        "still point to the Japan NVA. The other eighteen requested directions keep passing.",
        "### Packet observations distinguish the layers",
        observation_table(DIAGNOSIS),
        "Before the UDR, EU/US-spoke packets are observed across the customer WireGuard mesh and "
        "leaving Japan's NVA toward the workload; Japan-spoke packets use the Japan XFRM interface. "
        "No Japan-workload-to-spoke packets are observed on the routers. With the UDR, those reverse "
        "packets appear too, and endpoint TCP/HTTP and ICMP succeed. The paired firewall winners "
        "and NVA selections do not change. Thus this intervention repairs workload steering "
        "without changing B2's route-preference design.\n\n"
        "Japan's BIRD `!` warning for its local spoke remains visible even in the passing state, "
        "and Linux already contains that XFRM route. The warning is worth investigating separately, "
        "but it was not the blocking cause of these six failures. This is a reachability and "
        "packet-interface result, not a throughput measurement or a universal path-symmetry proof.",
        "### Exact evidence and closure",
        "The original collector records **INCONCLUSIVE**, and that raw verdict is preserved. "
        "Its strict comparison included BIRD's displayed route timestamps: eighteen headline "
        "comparisons differ by only one millisecond. A separate offline reconciliation verifies "
        "that no non-timestamp headline content changed and that selected protocols, AS paths, "
        "local preferences, kernel markers, BGP next hops and BIRD interface resolution stayed "
        "the same. The comparator is corrected for future runs; no measurement or original "
        "verdict is rewritten. The reconciliation and independent restoration evidence below "
        "are what support the conclusions, not a claim that the original collector returned PASS.",
        "\n\n".join(f"**{case[0]}:** [complete state]({link(case, 'scenario-result.json')}), "
                   f"[workload guest and NIC routes]({link(case, 'workload-evidence.json')}), "
                   f"[24-direction traffic]({link(case, 'traffic-summary.json')}), "
                   f"[router packet observations]({link(case, 'path-observations.json')})."
                   for case in DIAGNOSIS),
        "The temporary route table was deleted after removing the association. Original BIRD "
        "bytes/metadata, hub preferences/branch flags and stable firewall winners were restored; "
        "an independent original-state capture repeated the original 10/24 TCP and 14/24 ICMP "
        "outcomes. Only the ten owned VMs started for this control were returned to their original "
        "deallocated states. No IPsec or WireGuard configuration changed.\n\n"
        f"[Original collector and exact restoration verdict]({PUBLIC}{DIAGNOSIS[0][1]}/diagnosis-verdict.json); "
        f"[display-timestamp reconciliation]({PUBLIC}b2-diagnosis-reconciled-20261017/reconciliation-verdict.json); "
        f"[independent verification]({PUBLIC}b2-diagnosis-independent-20261017/baseline-verdict.json); "
        f"[final power restoration]({PUBLIC}b2-diagnosis-verify-power-stop-20261017/power-verdict.json).\n\n"
        "Reference: [Azure system routes, None next hop and user-defined routes]"
        "(https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-udr-overview).",
    ])
    assert design_b2b.selection_state(before["selected"]) == design_b2b.selection_state(after["selected"])
    return "\n\n".join(lines)


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


def b1_explanation():
    return """### Start with one destination and two ways to reach it

Consider an Azure VM in the EU spoke sending to the Japan DC workload, `10.130.0.10`.
A **prefix** is a range of addresses: the route for `10.130.0.0/24` covers this workload.
The EU hub can learn two BGP routes for that same prefix. They deliver packets to the same
destination, but enter the on-premises network at different places:

| Candidate at the EU hub | Where Azure learns it | Onward forwarding | AS path seen by the EU firewall | Length |
|---|---|---|---|---|
| Local | EU NVA's BGP connection to the EU hub | EU NVA -> customer mesh -> Japan NVA -> Japan workload | `65011 65011 65011 65011 65013` | 5 |
| Remote | Japan VPN connection to the Japan hub, then advertised to EU | Microsoft interhub backbone -> Japan VPN -> Japan NVA -> Japan workload | `65520 65520 65013` | 3 |

**Local means learned through a connection to the hub making the decision.** It does not mean
the destination is physically nearby: Japan's prefix is local to the EU hub when the EU NVA
advertises it there. Conversely, the Japan VPN's advertisement is remote from EU's perspective.
The same reasoning applies at the US hub.

An **AS path** lists autonomous-system numbers carried with a BGP route. **Prepending** repeats
an ASN to make an advertisement less attractive under a shortest-path policy. Here the EU NVA
adds three extra copies of `65011` for nonlocal DC prefixes. Those repeated numbers do not
mean traffic traverses four EU appliances. Azure adds `65520 65520` when the Japan route is
advertised between hubs.

With **HRP = ASPath**, the length-three remote route should win over length five: this is the
Microsoft-backbone direction. With **HRP = ExpressRoute or VPN**, the documented ordering checks
local-versus-remote *before* AS-path length. The expected B1 winner is therefore the longer
local NVA route, which leaves Azure in EU and uses the customer mesh to Japan. ExpressRoute is
the preference's name; this lab has no ExpressRoute circuit.

### What "history-dependent" means, step by step

The surprising observation is not that a longer route can win under B1. That is expected.
It is that changing the preference did not always move an already-selected remote route:

| Step | What we change | What stays available | Measured EU/US winner for Japan |
|---|---|---|---|
| 1. Start with the remote route already selected | Establish the initial route history | Local length 5 and remote length 3 advertisements | Remote length 3 |
| 2. Apply ExpressRoute HRP | Hub routing preference, not the NVA advertisements | Both candidates; local is expected to take priority | Remote length 3 remains selected |
| 3. Remove only the competing direct Japan advertisement | Withdraw `10.130.0.0/24` from Japan's Azure export | EU/US local mesh advertisements; VPN/BGP sessions and tunnels remain up | Local length 5 becomes selected |
| 4. Put the Japan advertisement back exactly as it was | Restore Japan's original export configuration | Both candidates again | Local length 5 remains selected |

Compare steps 2 and 4 carefully. The hub preferences and BIRD configuration bytes, ownership,
permissions and modification times are the same, and both advertisements are present again.
Nevertheless the selected route differs. Step 3 also demonstrates that the local advertisement
is eligible: it can be installed when its remote competitor disappears. Thus "B1's dependency"
means **the observed winner depends on the preceding route-selection history**, not just the
final static policy. It is not a prerequisite service, a DC-to-DC reachability requirement, or
a claim that the longer path is inherently invalid. We checked stable firewall snapshots at
least 120 seconds apart rather than relying on a single update-time screenshot.

### Is this the race condition in Microsoft's documentation?

It may be related, but **we have not proved Azure's internal cause**. The
[HRP documentation](https://learn.microsoft.com/en-us/azure/virtual-wan/about-virtual-hub-routing-preference)
warns that ExpressRoute/VPN preference can select a remote route in a race condition when the
local AS path is at least two entries longer. Our length-five versus length-three example
matches that published condition. A race condition generally means that the order or timing
of competing updates influences the resulting state; we did not instrument Azure's backend
or identify an internal cache, timing window or particular implementation defect.

The separate control is important: reducing EU's extra prepends from three to two creates a
**local length-four versus remote length-three** comparison. It repeats the before/withdraw/
return history dependence even though the gap is only one. Consequently the documented
two-or-more-longer warning alone does not explain every measurement. Both controls reproduce
with branch-to-branch enabled at WAN level and on every hub, so the former mixed flag setting
is not a sufficient explanation either.

The withdrawal is a **bounded lab diagnostic**, not a supported production workaround or a
guarantee of a particular winner after future reconvergence. B1 should not be presented as
"set HRP and every existing route immediately switches." Validate the effective routes after
policy changes and route return, and treat this observation as something to investigate with
Azure support if a production design depends on deterministic local preference."""


def observation_table(cases):
    pairs = (("10.10.0.10", "10.130.0.10"), ("10.130.0.10", "10.10.0.10"),
             ("10.30.0.10", "10.130.0.10"), ("10.130.0.10", "10.30.0.10"))
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
                     "presented as proof that the HRP change alone produced it.\n\n"
                     "B1's traffic capture predates the focused workload UDR correction. It has not "
                     "been repeated with that correction, so its 10/24 TCP and 14/24 ICMP results "
                     "must not be compared with corrected A/B2 as an HRP-only forwarding experiment.")
    else:
        lines.append("All hubs use `ASPath`. EU/US nonlocal extra prepends are removed; Japan still has "
                     "no extra prepends. Azure imports remain spoke-only, so NVAs keep foreign DCs on "
                     "their mesh. Removing prepends shortens the local offer; this is not a claim that "
                     "adding prepends everywhere favors the customer backbone.\n\n"
                     "The primary capture now includes the three-spoke Japan workload UDR to "
                     "`10.130.0.4` and passes 24/24 DC/Azure directions. The no-UDR and UDR-removal "
                     "controls below isolate the previous six failures without changing BGP policy.")
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
                  f"### {name}: 24 DC/Azure acceptance directions", matrix(data)])
    return "\n\n".join(lines)


def validate():
    for case in CASES:
        data = load(case)
        traffic = data["traffic"]
        acceptance(traffic)
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
    diagnosis = diagnosis_section()
    folder = OUTPUT / "b2b-summary-20261017"
    folder.mkdir(exist_ok=True)
    before, enabled = load(CASES[0]), load(CASES[1])
    identical = before["firewalls"]["rows"] == enabled["firewalls"]["rows"]
    changed = []
    original = {(c["source"], c["destination"]): c for c in before["traffic"]["cells"]}
    for c in acceptance(enabled["traffic"])["cells"]:
        a = original[c["source"], c["destination"]]
        if (a["tcp"], a["icmp"]) != (c["tcp"], c["icmp"]):
            changed.append((c["source"], c["destination"]))
    introduction = (
        "The matched mixed-setting and all-enabled baselines have "
        f"{'identical' if identical else 'different'} DC-prefix firewall winners and "
        f"**{len(changed)} changed traffic outcomes out of 24 DC/Azure directional cells**. "
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
        "Traffic and routing are separate findings. Acceptance now covers only the **24 DC <-> "
        "Azure-spoke directions**, not DC-to-DC or auxiliary spoke-to-spoke traffic. B1's returned "
        "three-prepend state passes 10/24 TCP and 14/24 ICMP. VPN HRP selects longer local Japan "
        "paths in its measured state, with 14/24 TCP and 16/24 ICMP passes; that sequential "
        "control is not proof of a universal ER/VPN difference independent of route history. "
        "B2 without a workload UDR passes 18/24 for both: all six failures are Japan workload "
        "<-> Azure spoke directions. **A with its workload UDR passes 24/24 TCP and ICMP** and "
        "therefore meets the requested DC/Azure reachability criterion. Its historical DC-to-DC "
        "failures are outside that criterion. Reachability acceptance is not by itself proof "
        "that every packet used the intended backbone.\n\n"
        "**The new reversible B2 control identifies the missing Japan workload subnet UDR.** "
        "With three spoke-prefix routes to `10.130.0.4`, B2 passes **24/24 TCP and ICMP**. "
        "Removing those routes restores 18/24. BIRD policy, NVA selections and firewall winners "
        "remain unchanged; the workload NIC changes from the system `10.0.0.0/8 -> None` drop "
        "route to the explicit NVA next hops.")
    methodology = (
        "Every measured state has full firewall effective tables for all three hubs, paired stable "
        "DC-prefix winners at least 120 seconds apart, full BIRD sources and selected/alternative routes "
        "on all four routers. The historical rerun has an explicitly sourced 42-direction TCP/ICMP "
        "matrix; the new B2 steering control sends only the 24 requested DC/Azure directions. The seven endpoints "
        "are four synthetic DCs and three Azure spokes: 12 DC-to-DC, 24 DC/spoke and six spoke-to-spoke "
        "directions. **Only the 24 DC/Azure directions determine acceptance.** The twelve DC-to-DC "
        "directions are excluded, and the six spoke-to-spoke directions are auxiliary. The raw "
        "42-cell files and their original verdicts remain unchanged; `acceptance.csv` and the "
        "tables below derive the requested scope explicitly. TCP requires HTTP 200 on the private "
        "port 5201 listener and matching local/remote addresses; ICMP uses source-bound ping. "
        "P/F below means TCP PASS / ICMP FAIL.\n\n"
        "Bounded tcpdump captures on every router observe inner test packets on physical, WireGuard "
        "and XFRM interfaces; management traffic and encrypted transport payloads are not collected. "
        "The interface observations are not a throughput measurement or a complete symmetry proof. "
        "Failed SYNs/ICMP attempts can still appear in a capture. The peered underlay and workload "
        "routing must be considered rather than treating an HTTP success as proof of Microsoft "
        "interhub transit. `!` in a BIRD table is a kernel-export warning; inspect Linux routes and "
        "actual packets rather than assuming the route is absent or blaming a traffic failure "
        "on this marker alone. A collector verdict of PASS means complete "
        "measurements and exact configuration closure, not 42 successful traffic directions.\n\n"
        "During B1's three-prepend withdrawal, Japan's firewall exposes two equal-length remote "
        "Japan-prefix entries, one through EU and one through US. All twelve hub/prefix keys remain "
        "present, but there are thirteen rows. The inherited single-winner check therefore records "
        "`complete: false`; this flag is retained in raw evidence and does not mean a prefix was "
        "missing in that state.")
    report = "\n\n".join([
        "# Secured all-hub branch-to-branch rerun, 17 October 2026", introduction, findings,
        "## Traffic outcomes", summary((*CASES, *DIAGNOSIS)), "## Methodology and limitations", methodology,
        "## B1 Japan-prefix selection sequence", winners(CASES[4:11]),
        b1_explanation(),
        "## Packet-interface observations", observation_table((CASES[2], *PRIMARY.values())),
        *(design_section(name, case) for name, case in PRIMARY.items()),
        diagnosis,
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
    with (folder / "acceptance.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("state", "source", "destination", "TCP", "ICMP"))
        for case in (*CASES, *DIAGNOSIS):
            for cell in acceptance(load(case)["traffic"])["cells"]:
                writer.writerow((case[0], cell["source"], cell["destination"], cell["tcp"], cell["icmp"]))
    if args.blog:
        post = args.blog / "2026-10-vwan-sdwan-three-hub"
        old = (post / "README.md").read_text(encoding="utf-8")
        topology = retained_section(old, "One topology, two possible backbones")
        commands = (retained_section(old, "Retrieve effective routes")
                    if "## Retrieve effective routes\n" in old else
                    retained_section(old, "Commands") if "## Commands\n" in old else "")
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
            "| A: Microsoft | ASPath | Foreign DC/spoke Azure imports at LP 400; three nonlocal prepends on EU/US/JP; JP workload UDR needed for observed 24/24 reachability; policy-only control measured separately |\n"
            "| B1: customer | ExpressRoute; VpnGateway measured separately | Spoke-only Azure imports; three extra nonlocal EU/US prepends; JP none |\n"
            "| B2: customer | ASPath | Spoke-only Azure imports; zero extra EU/US/JP prepends; three-spoke JP workload UDR |",
            "The [documented HRP ordering](https://learn.microsoft.com/en-us/azure/virtual-wan/about-virtual-hub-routing-preference) "
            "prioritizes locality under ExpressRoute/VPN and path length under ASPath. The B1 initial, "
            "withdrawn and returned states below expose the measured selection history rather than "
            "assuming every HRP update recomputes the same winner.",
            "## Forwarding results, not just routing tables", summary((*CASES[:-2], *DIAGNOSIS)), methodology,
            "## How to read the captured tables",
            "Each design below contains the full EU and Japan firewall table, not a filtered supporting "
            "prefix. US is collected too and available in the matched evidence. EU, Japan and CN NVA "
            "tables include all seven DC/spoke prefixes. BGP next hop and BIRD resolution are distinct "
            "attributes. `n/a` means absent on a static route; `empty` means a blank firewall AS path. "
            "The primary A state includes the workload UDR; primary B1 is the returned three-prepend state.",
            *(design_section(name, case) for name, case in PRIMARY.items()),
            "## B1 initial selection and controlled route return", winners(CASES[4:11]),
            b1_explanation(),
            diagnosis,
            "## Packet-interface evidence", observation_table((CASES[2], *PRIMARY.values())),
            "## Conclusions and boundaries",
            "Enabling Japan's hub flag alone did not change this baseline's firewall winners or traffic "
            "outcomes. The configuration inconsistency therefore was not sufficient to explain those "
            "failures. The per-design traffic matrices above establish exactly which workload "
            "directions passed; selected routes alone do not establish a successful backbone design. "
            "DC-to-DC results are not success criteria; A plus its workload UDR passes all 24 "
            "requested DC/Azure directions, as does B2 with the focused three-spoke workload UDR. "
            "B2's six earlier failures reproduce when that UDR is removed, without changing its "
            "hub/NVA route selections. BIRD `!` warnings remain visible but are not equated "
            "with a proven packet-drop cause. "
            "No bandwidth advantage was measured. Configuration, original hub settings and original "
            "VM power states were restored after the rerun.",
            "[Full rerun report and raw evidence](" + PUBLIC + "b2b-summary-20261017/README.md). "
            "Earlier mixed-setting results and their original verdicts remain linked in "
            "[references.md](./references.md).",
            ("## Retrieve effective routes\n\n" + commands) if commands else
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
        text += "Acceptance is the 24 DC/Azure directions per state: [408 scoped cells across 17 states](" + PUBLIC + "b2b-summary-20261017/acceptance.csv). DC-to-DC is excluded and spoke-to-spoke is auxiliary; historical raw 42-cell verdicts are preserved, not used as the new success criterion. The focused B2 UDR control sends only the requested 24 directions.\n\n"
        text += "B2 now uses the passing three-spoke-UDR capture. Its before/UDR/removal evidence, fabric drop routes and exact closure are mapped in the post's B2 diagnosis section and the source report.\n\n"
        text += "## Primary matched captures\n\n"
        for name, case in PRIMARY.items():
            text += f"### {name}: {case[0]}\n\n"
            text += f"[Full scenario]({link(case, 'scenario-result.json')}); [selected routes]({link(case, 'selected-routes.json')}); [raw traffic]({link(case, 'traffic-summary.json')}); [packet observations]({link(case, 'path-observations.json')}).\n\n"
            text += "| Site | Complete BIRD configuration | Full firewall table |\n|---|---|---|\n"
            for s in ("eu", "us", "jp", "cn"):
                firewall = (f"[table2.txt]({link(case, case[2] + '-' + s + '-table2.txt')})"
                            if s != "cn" else "No hub attachment")
                text += f"| {s.upper()} | [router-{s}.conf]({link(case, 'router-' + s + '.conf')}) | {firewall} |\n"
            text += "\nFull firewall JSON is alongside the text with a `.json` suffix. Raw BIRD selections and alternatives are in `router-{site}-bird-routes.txt`; both Azure export views are in `router-{site}-export-azure_{0,1}.txt`. CN has no Azure peers. NVA route snapshots also retain Linux routes, policy rules and lookups. The post renders all EU/JP firewall entries and all seven prefixes on EU/JP/CN, including `!` kernel-export failures.\n\n"
        text += "## Additional controls and closure\n\n"
        for case in (*CASES, *DIAGNOSIS):
            text += f"- [{case[0]}]({link(case, 'scenario-result.json')}).\n"
        text += "\n[Original VM power inventory restored](" + PUBLIC + "b2b-power-stop-20261017/power-verdict.json). Exact source bytes/metadata, original mixed hub flags/HRPs and original paired firewall winners were independently restored; traffic returned to 28/42 TCP and 32/42 ICMP. Temporary A route-table cleanup is captured in the A controller's restore evidence.\n\n"
        text += "The focused B2 follow-up preserves its [original INCONCLUSIVE collector verdict](" + PUBLIC + "b2-diagnosis-control-20261017/diagnosis-verdict.json). Its [separate display-timestamp reconciliation](" + PUBLIC + "b2-diagnosis-reconciled-20261017/reconciliation-verdict.json) verifies that only eighteen one-millisecond headline differences triggered the comparison; routing attributes, BGP next hops and interface resolution are unchanged. [Independent original-state verification](" + PUBLIC + "b2-diagnosis-independent-20261017/baseline-verdict.json) repeats 10/24 TCP and 14/24 ICMP, followed by [final original-power restoration](" + PUBLIC + "b2-diagnosis-verify-power-stop-20261017/power-verdict.json). No historical verdict is rewritten.\n\n"
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
        for name in ("design_b2b.py", "design_b2_diagnosis.py", "b2b_report.py", "design_backbone.py", "design_snapshot.py", "design_comparison.py"):
            text += f"- [{name}]({base + name}).\n"
        text += "- [Hub routing preference](https://learn.microsoft.com/en-us/azure/virtual-wan/about-virtual-hub-routing-preference).\n"
        text += "- [BGP peering considerations, including branch-to-branch](https://learn.microsoft.com/en-us/azure/virtual-wan/scenario-bgp-peering-hub#benefits-and-considerations).\n"
        text += "- [Routing intent](https://learn.microsoft.com/en-us/azure/virtual-wan/about-routing-intent).\n"
        text += "- [Effective routes](https://learn.microsoft.com/en-us/azure/virtual-wan/effective-routes-virtual-hub).\n"
        text += "- [Azure subnet system routes, None drop next hop and UDRs](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-udr-overview).\n"
        text += "- [BIRD 2 documentation](https://bird.network.cz/?get_doc&v=20&f=bird.html).\n\n"
        text += "The diagnostic discriminators remain `AzureFirewalls` (plural) for secured firewall routes and `HubVirtualNetworkConnection` (singular) for unsecured connection routes. The topology SVG is unchanged and represents connectivity, not proof that every drawn path carries test traffic.\n"
        refs.write_text(text, encoding="utf-8")
    print("PASS: complete route/traffic/path evidence rendered; 17 states, 408 acceptance cells; original 588 historical cells preserved")


if __name__ == "__main__":
    main()
