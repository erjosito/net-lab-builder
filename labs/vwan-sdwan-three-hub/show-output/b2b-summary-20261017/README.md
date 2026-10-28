# Secured all-hub branch-to-branch rerun, 17 October 2026

The matched mixed-setting and all-enabled baselines have identical DC-prefix firewall winners and **0 changed traffic outcomes out of 42 directional cells**. WAN-level B2B was already enabled; only Japan's hub flag changes from false to true. Original NVA sources, metadata, HRPs and PrivateTraffic routing intent are held constant. This isolates the flag for the baseline; it does not prove that the flag is irrelevant for every route history or supported topology.

**The B1 history dependency also reproduces with B2B enabled on every hub.** Under ExpressRoute HRP, EU/US initially retain remote Japan length three. Withdrawing only Japan's direct export selects local length-five paths; returning the export leaves those longer local paths selected. The separate EU length-four versus remote length-three control repeats the dependency. Source bytes/metadata and HRPs are identical between the initial and returned states. The mixed B2B flags therefore do not explain away that observation.

Traffic and routing are separate findings. Acceptance now covers only the **24 DC <-> Azure-spoke directions**, not DC-to-DC or auxiliary spoke-to-spoke traffic. B1's returned three-prepend state passes 10/24 TCP and 14/24 ICMP. VPN HRP selects longer local Japan paths in its measured state, with 14/24 TCP and 16/24 ICMP passes; that sequential control is not proof of a universal ER/VPN difference independent of route history. B2 without a workload UDR passes 18/24 for both: all six failures are Japan workload <-> Azure spoke directions. **A with its workload UDR passes 24/24 TCP and ICMP** and therefore meets the requested DC/Azure reachability criterion. Its historical DC-to-DC failures are outside that criterion. Reachability acceptance is not by itself proof that every packet used the intended backbone.

## Traffic outcomes

| Measured state | TCP / 24 | ICMP / 24 | DC/Azure reachability |
|---|---|---|---|
| [Mixed baseline](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-mixed-baseline-20261017/baseline/traffic-summary.json) | 10 | 14 | FAIL |
| [All B2B baseline](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-enabled-baseline-20261017/baseline/traffic-summary.json) | 10 | 14 | FAIL |
| [A, NVA policy only](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-A-20261017/A/traffic-summary.json) | 18 | 18 | FAIL |
| [A, plus JP workload UDR](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-A-20261017/A-workload-UDR/traffic-summary.json) | 24 | 24 | PASS |
| [B1, ExpressRoute initial](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-B1-20261017/B1/traffic-summary.json) | 10 | 14 | FAIL |
| [B1, JP direct prefix withdrawn](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-B1-20261017/B1-withdrawn/traffic-summary.json) | 10 | 14 | FAIL |
| [B1, JP direct prefix returned](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-B1-20261017/B1-returned/traffic-summary.json) | 10 | 14 | FAIL |
| [B1 one-ASN, initial](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-B1-one-ASN-20261017/B1-one-ASN/traffic-summary.json) | 12 | 15 | FAIL |
| [B1 one-ASN, withdrawn](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-B1-one-ASN-20261017/B1-one-ASN-withdrawn/traffic-summary.json) | 12 | 15 | FAIL |
| [B1 one-ASN, returned](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-B1-one-ASN-20261017/B1-one-ASN-returned/traffic-summary.json) | 12 | 15 | FAIL |
| [B1, VPN HRP](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-B1-VPN-20261017/B1-VPN/traffic-summary.json) | 14 | 16 | FAIL |
| [B2, zero extra EU/US prepends](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-B2-20261017/B2/traffic-summary.json) | 18 | 18 | FAIL |
| [Original mixed state restored](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-restore-mixed-20261017/restored/traffic-summary.json) | 10 | 14 | FAIL |
| [Independent original-state verification](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-independent-verify-20261017/independent-verification/traffic-summary.json) | 10 | 14 | FAIL |

## Methodology and limitations

Every measured state has full firewall effective tables for all three hubs, paired stable DC-prefix winners at least 120 seconds apart, full BIRD sources and selected/alternative routes on all four routers, and an explicitly sourced historical 42-direction TCP/ICMP matrix. The seven endpoints are four synthetic DCs and three Azure spokes: 12 DC-to-DC, 24 DC/spoke and six spoke-to-spoke directions. **Only the 24 DC/Azure directions determine acceptance.** The twelve DC-to-DC directions are excluded, and the six spoke-to-spoke directions are auxiliary. The raw 42-cell files and their original verdicts remain unchanged; `acceptance.csv` and the tables below derive the requested scope explicitly. TCP requires HTTP 200 on the private port 5201 listener and matching local/remote addresses; ICMP uses source-bound ping. P/F below means TCP PASS / ICMP FAIL.

Bounded tcpdump captures on every router observe inner test packets on physical, WireGuard and XFRM interfaces; management traffic and encrypted transport payloads are not collected. The interface observations are not a throughput measurement or a complete symmetry proof. Failed SYNs/ICMP attempts can still appear in a capture. The peered underlay and workload routing must be considered rather than treating an HTTP success as proof of Microsoft interhub transit. `!` in a BIRD table is a kernel-export warning; inspect Linux routes and actual packets rather than assuming the route is absent or blaming a traffic failure on this marker alone. A collector verdict of PASS means complete measurements and exact configuration closure, not 42 successful traffic directions.

During B1's three-prepend withdrawal, Japan's firewall exposes two equal-length remote Japan-prefix entries, one through EU and one through US. All twelve hub/prefix keys remain present, but there are thirteen rows. The inherited single-winner check therefore records `complete: false`; this flag is retained in raw evidence and does not mean a prefix was missing in that state.

## B1 Japan-prefix selection sequence

| State | EU Japan path | US Japan path |
|---|---|---|
| B1, ExpressRoute initial | `65520-65520-65013` (Remote Hub) | `65520-65520-65013` (Remote Hub) |
| B1, JP direct prefix withdrawn | `65011-65011-65011-65011-65013` (HubBgpConnection) | `65012-65012-65012-65012-65013` (HubBgpConnection) |
| B1, JP direct prefix returned | `65011-65011-65011-65011-65013` (HubBgpConnection) | `65012-65012-65012-65012-65013` (HubBgpConnection) |
| B1 one-ASN, initial | `65520-65520-65013` (Remote Hub) | `65012-65012-65012-65012-65013` (HubBgpConnection) |
| B1 one-ASN, withdrawn | `65011-65011-65011-65013` (HubBgpConnection) | `65012-65012-65012-65012-65013` (HubBgpConnection) |
| B1 one-ASN, returned | `65011-65011-65011-65013` (HubBgpConnection) | `65012-65012-65012-65012-65013` (HubBgpConnection) |
| B1, VPN HRP | `65011-65011-65011-65011-65013` (HubBgpConnection) | `65012-65012-65012-65012-65013` (HubBgpConnection) |

### Start with one destination and two ways to reach it

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
Azure support if a production design depends on deterministic local preference.

## Packet-interface observations

| State / packet direction | EU | US | JP | CN |
|---|---|---|---|---|
| A, NVA policy only: `10.10.0.10` -> `10.130.0.10` | not observed | not observed | enP2749s1 Out, eth0 Out, xfrm42 In | not observed |
| A, NVA policy only: `10.130.0.10` -> `10.10.0.10` | not observed | not observed | not observed | not observed |
| A, NVA policy only: `10.30.0.10` -> `10.130.0.10` | not observed | not observed | enP2749s1 Out, eth0 Out, xfrm42 In | not observed |
| A, NVA policy only: `10.130.0.10` -> `10.30.0.10` | not observed | not observed | not observed | not observed |
| A, plus JP workload UDR: `10.10.0.10` -> `10.130.0.10` | not observed | not observed | enP2749s1 Out, eth0 Out, xfrm41 In, xfrm42 In | not observed |
| A, plus JP workload UDR: `10.130.0.10` -> `10.10.0.10` | not observed | not observed | enP2749s1 In, eth0 In, xfrm42 Out | not observed |
| A, plus JP workload UDR: `10.30.0.10` -> `10.130.0.10` | not observed | not observed | enP2749s1 Out, eth0 Out, xfrm42 In | not observed |
| A, plus JP workload UDR: `10.130.0.10` -> `10.30.0.10` | not observed | not observed | enP2749s1 In, eth0 In, xfrm42 Out | not observed |
| B1, JP direct prefix returned: `10.10.0.10` -> `10.130.0.10` | enP40243s1 In, eth0 In, wgeujp Out | not observed | enP2749s1 Out, eth0 Out, wgeujp In | not observed |
| B1, JP direct prefix returned: `10.130.0.10` -> `10.10.0.10` | not observed | not observed | not observed | not observed |
| B1, JP direct prefix returned: `10.30.0.10` -> `10.130.0.10` | not observed | not observed | enP2749s1 Out, eth0 Out, xfrm41 In, xfrm42 In | not observed |
| B1, JP direct prefix returned: `10.130.0.10` -> `10.30.0.10` | not observed | not observed | not observed | not observed |
| B2, zero extra EU/US prepends: `10.10.0.10` -> `10.130.0.10` | enP40243s1 In, eth0 In, wgeujp Out | not observed | enP2749s1 Out, eth0 Out, wgeujp In | not observed |
| B2, zero extra EU/US prepends: `10.130.0.10` -> `10.10.0.10` | not observed | not observed | not observed | not observed |
| B2, zero extra EU/US prepends: `10.30.0.10` -> `10.130.0.10` | not observed | not observed | enP2749s1 Out, eth0 Out, xfrm42 In | not observed |
| B2, zero extra EU/US prepends: `10.130.0.10` -> `10.30.0.10` | not observed | not observed | not observed | not observed |

## A: Microsoft backbone preferred

All hubs use `ASPath`. The three Azure-facing NVAs accept foreign DC and spoke routes from Azure at LP 400. EU/US/JP add three extra own-AS copies for nonlocal DC exports. The export source guard prevents feeding an Azure-learned best route back into Azure. CN remains mesh-only, so this is not an all-prefix Microsoft-only design.

The primary capture includes the five-prefix Japan workload UDR to `10.130.0.4`; the policy-only control is measured separately. The UDR covers EU/US DCs and all three Azure spokes, not CN's transport endpoint.

Matched state: [A, plus JP workload UDR](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-A-20261017/A-workload-UDR/scenario-result.json). Full BIRD configurations: [EU](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-A-20261017/A-workload-UDR/router-eu.conf), [US](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-A-20261017/A-workload-UDR/router-us.conf), [JP](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-A-20261017/A-workload-UDR/router-jp.conf), [CN](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-A-20261017/A-workload-UDR/router-cn.conf).

### A: complete EU firewall table

| Prefix | ASPath | NextHopType |
|---|---|---|
| `10.210.0.0/24` | empty | Virtual Network Connection |
| `10.10.0.0/24` | empty | Virtual Network Connection |
| `10.110.0.0/24` | `65011` | HubBgpConnection |
| `10.140.0.0/24` | `65011-65011-65011-65011-65014` | HubBgpConnection |
| `10.130.0.0/24` | `65520-65520-65013` | Remote Hub |
| `10.30.0.0/24` | `65520-65520` | Remote Hub |
| `10.220.0.0/24` | `65520-65520` | Remote Hub |
| `10.120.0.0/24` | `65520-65520-65012` | Remote Hub |
| `10.20.0.0/24` | `65520-65520` | Remote Hub |
| `0.0.0.0/0` | empty | Internet |

### A: complete JP firewall table

| Prefix | ASPath | NextHopType |
|---|---|---|
| `10.140.0.0/24` | `65013-65013-65013-65013-65014` | VPN_S2S_Gateway |
| `10.130.0.0/24` | `65013` | VPN_S2S_Gateway |
| `10.10.0.0/24` | `65520-65520` | Remote Hub |
| `10.220.0.0/24` | `65520-65520` | Remote Hub |
| `10.120.0.0/24` | `65520-65520-65012` | Remote Hub |
| `10.20.0.0/24` | `65520-65520` | Remote Hub |
| `10.210.0.0/24` | `65520-65520` | Remote Hub |
| `10.110.0.0/24` | `65520-65520-65011` | Remote Hub |
| `10.30.0.0/24` | empty | Virtual Network Connection |
| `0.0.0.0/0` | empty | Internet |

### A: EU selected NVA routes

| Prefix | Protocol | BGP next hop | BIRD resolution | ASPath | LP | Marker |
|---|---|---|---|---|---|---|
| `10.110.0.0/24` | `own_dc` | `n/a` | `via 10.210.0.1 on eth0` | `n/a` | n/a | `*` |
| `10.120.0.0/24` | `azure_0` | `10.210.0.1` | `via 10.210.0.1 on eth0` | `65515 65520 65520 65012` | 400 | `*` |
| `10.130.0.0/24` | `azure_0` | `10.210.0.1` | `via 10.210.0.1 on eth0` | `65515 65520 65520 65013` | 400 | `*` |
| `10.140.0.0/24` | `mesh_cn` | `172.31.0.10` | `dev wgeucn` | `65014` | 100 | `*` |
| `10.10.0.0/24` | `azure_0` | `10.210.0.1` | `via 10.210.0.1 on eth0` | `65515` | 400 | `*` |
| `10.20.0.0/24` | `azure_0` | `10.210.0.1` | `via 10.210.0.1 on eth0` | `65515 65520 65520` | 400 | `*` |
| `10.30.0.0/24` | `azure_0` | `10.210.0.1` | `via 10.210.0.1 on eth0` | `65515 65520 65520` | 400 | `*` |

### A: JP selected NVA routes

| Prefix | Protocol | BGP next hop | BIRD resolution | ASPath | LP | Marker |
|---|---|---|---|---|---|---|
| `10.110.0.0/24` | `azure_1` | `169.254.21.6` | `via 169.254.21.6 on xfrm42` | `65515 65520 65520 65011` | 400 | `!` |
| `10.120.0.0/24` | `azure_1` | `169.254.21.6` | `via 169.254.21.6 on xfrm42` | `65515 65520 65520 65012` | 400 | `!` |
| `10.130.0.0/24` | `own_dc` | `n/a` | `dev eth0` | `n/a` | n/a | `*` |
| `10.140.0.0/24` | `mesh_cn` | `172.31.0.22` | `dev wgjpcn` | `65014` | 100 | `*` |
| `10.10.0.0/24` | `azure_1` | `169.254.21.6` | `via 169.254.21.6 on xfrm42` | `65515 65520 65520` | 400 | `!` |
| `10.20.0.0/24` | `azure_1` | `169.254.21.6` | `via 169.254.21.6 on xfrm42` | `65515 65520 65520` | 400 | `!` |
| `10.30.0.0/24` | `azure_1` | `169.254.21.6` | `via 169.254.21.6 on xfrm42` | `65515` | 400 | `!` |

### A: CN selected NVA routes

| Prefix | Protocol | BGP next hop | BIRD resolution | ASPath | LP | Marker |
|---|---|---|---|---|---|---|
| `10.110.0.0/24` | `mesh_eu` | `172.31.0.9` | `dev wgeucn` | `65011` | 100 | `*` |
| `10.120.0.0/24` | `mesh_us` | `172.31.0.17` | `dev wguscn` | `65012` | 100 | `*` |
| `10.130.0.0/24` | `mesh_jp` | `172.31.0.21` | `dev wgjpcn` | `65013` | 100 | `*` |
| `10.140.0.0/24` | `own_dc` | `n/a` | `dev eth0` | `n/a` | n/a | `*` |
| `10.10.0.0/24` | `mesh_eu` | `172.31.0.9` | `dev wgeucn` | `65011 65515` | 300 | `*` |
| `10.20.0.0/24` | `mesh_us` | `172.31.0.17` | `dev wguscn` | `65012 65515` | 300 | `*` |
| `10.30.0.0/24` | `mesh_jp` | `172.31.0.21` | `dev wgjpcn` | `65013 65515` | 300 | `*` |

### A: captured EU export policy

```bird
filter azure_export {
  if net ~ [10.110.0.0/24, 10.120.0.0/24, 10.130.0.0/24, 10.140.0.0/24] &&
     (proto = "own_dc" || proto ~ "mesh_*") then {
        if net != 10.110.0.0/24 then {
            bgp_path.prepend(65011);
            bgp_path.prepend(65011);
            bgp_path.prepend(65011);
        }
        accept;
  }
  reject;
}
```

### A: 24 DC/Azure acceptance directions

**DC -> Azure spoke**

| DC / Azure spoke | spoke-eu | spoke-us | spoke-jp |
|---|---|---|---|
| dc-eu | P/P | P/P | P/P |
| dc-us | P/P | P/P | P/P |
| dc-jp | P/P | P/P | P/P |
| cn | P/P | P/P | P/P |

**Azure spoke -> DC**

| DC / Azure spoke | spoke-eu | spoke-us | spoke-jp |
|---|---|---|---|
| dc-eu | P/P | P/P | P/P |
| dc-us | P/P | P/P | P/P |
| dc-jp | P/P | P/P | P/P |
| cn | P/P | P/P | P/P |

## B1: Customer backbone through HRP

The primary capture uses `ExpressRoute` on all hubs, the original three extra EU/US nonlocal prepends, no extra Japan prepends, and spoke-only Azure imports. It is the final state after withdrawing and restoring only Japan's direct `10.130.0.0/24` Azure export. Mesh exports and tunnel configurations are unchanged.

The initial state, withdrawal, return, one-ASN-difference replay and `VpnGateway` HRP control are reported separately below. A final local winner must not be presented as proof that the HRP change alone produced it.

Matched state: [B1, JP direct prefix returned](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-B1-20261017/B1-returned/scenario-result.json). Full BIRD configurations: [EU](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-B1-20261017/B1-returned/router-eu.conf), [US](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-B1-20261017/B1-returned/router-us.conf), [JP](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-B1-20261017/B1-returned/router-jp.conf), [CN](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-B1-20261017/B1-returned/router-cn.conf).

### B1: complete EU firewall table

| Prefix | ASPath | NextHopType |
|---|---|---|
| `10.110.0.0/24` | `65011` | HubBgpConnection |
| `10.210.0.0/24` | empty | Virtual Network Connection |
| `10.10.0.0/24` | empty | Virtual Network Connection |
| `10.130.0.0/24` | `65011-65011-65011-65011-65013` | HubBgpConnection |
| `10.30.0.0/24` | `65520-65520` | Remote Hub |
| `10.220.0.0/24` | `65520-65520` | Remote Hub |
| `10.120.0.0/24` | `65520-65520-65012` | Remote Hub |
| `10.140.0.0/24` | `65520-65520-65013-65014` | Remote Hub |
| `10.20.0.0/24` | `65520-65520` | Remote Hub |
| `0.0.0.0/0` | empty | Internet |

### B1: complete JP firewall table

| Prefix | ASPath | NextHopType |
|---|---|---|
| `10.140.0.0/24` | `65013-65014` | VPN_S2S_Gateway |
| `10.120.0.0/24` | `65013-65012` | VPN_S2S_Gateway |
| `10.110.0.0/24` | `65013-65011` | VPN_S2S_Gateway |
| `10.30.0.0/24` | empty | Virtual Network Connection |
| `10.130.0.0/24` | `65013` | VPN_S2S_Gateway |
| `10.10.0.0/24` | `65520-65520` | Remote Hub |
| `10.220.0.0/24` | `65520-65520` | Remote Hub |
| `10.20.0.0/24` | `65520-65520` | Remote Hub |
| `10.210.0.0/24` | `65520-65520` | Remote Hub |
| `0.0.0.0/0` | empty | Internet |

### B1: EU selected NVA routes

| Prefix | Protocol | BGP next hop | BIRD resolution | ASPath | LP | Marker |
|---|---|---|---|---|---|---|
| `10.110.0.0/24` | `own_dc` | `n/a` | `via 10.210.0.1 on eth0` | `n/a` | n/a | `*` |
| `10.120.0.0/24` | `mesh_us` | `172.31.0.2` | `dev wgeuus` | `65012` | 100 | `*` |
| `10.130.0.0/24` | `mesh_jp` | `172.31.0.6` | `dev wgeujp` | `65013` | 100 | `*` |
| `10.140.0.0/24` | `mesh_cn` | `172.31.0.10` | `dev wgeucn` | `65014` | 100 | `*` |
| `10.10.0.0/24` | `azure_0` | `10.210.0.1` | `via 10.210.0.1 on eth0` | `65515` | 300 | `*` |
| `10.20.0.0/24` | `mesh_us` | `172.31.0.2` | `dev wgeuus` | `65012 65515` | 300 | `*` |
| `10.30.0.0/24` | `mesh_jp` | `172.31.0.6` | `dev wgeujp` | `65013 65515` | 300 | `*` |

### B1: JP selected NVA routes

| Prefix | Protocol | BGP next hop | BIRD resolution | ASPath | LP | Marker |
|---|---|---|---|---|---|---|
| `10.110.0.0/24` | `mesh_eu` | `172.31.0.5` | `dev wgeujp` | `65011` | 100 | `*` |
| `10.120.0.0/24` | `mesh_us` | `172.31.0.13` | `dev wgusjp` | `65012` | 100 | `*` |
| `10.130.0.0/24` | `own_dc` | `n/a` | `dev eth0` | `n/a` | n/a | `*` |
| `10.140.0.0/24` | `mesh_cn` | `172.31.0.22` | `dev wgjpcn` | `65014` | 100 | `*` |
| `10.10.0.0/24` | `mesh_eu` | `172.31.0.5` | `dev wgeujp` | `65011 65515` | 300 | `*` |
| `10.20.0.0/24` | `mesh_us` | `172.31.0.13` | `dev wgusjp` | `65012 65515` | 300 | `*` |
| `10.30.0.0/24` | `azure_1` | `169.254.21.6` | `via 169.254.21.6 on xfrm42` | `65515` | 300 | `!` |

### B1: CN selected NVA routes

| Prefix | Protocol | BGP next hop | BIRD resolution | ASPath | LP | Marker |
|---|---|---|---|---|---|---|
| `10.110.0.0/24` | `mesh_eu` | `172.31.0.9` | `dev wgeucn` | `65011` | 100 | `*` |
| `10.120.0.0/24` | `mesh_us` | `172.31.0.17` | `dev wguscn` | `65012` | 100 | `*` |
| `10.130.0.0/24` | `mesh_jp` | `172.31.0.21` | `dev wgjpcn` | `65013` | 100 | `*` |
| `10.140.0.0/24` | `own_dc` | `n/a` | `dev eth0` | `n/a` | n/a | `*` |
| `10.10.0.0/24` | `mesh_eu` | `172.31.0.9` | `dev wgeucn` | `65011 65515` | 300 | `*` |
| `10.20.0.0/24` | `mesh_us` | `172.31.0.17` | `dev wguscn` | `65012 65515` | 300 | `*` |
| `10.30.0.0/24` | `mesh_jp` | `172.31.0.21` | `dev wgjpcn` | `65013 65515` | 300 | `*` |

### B1: captured EU export policy

```bird
filter azure_export {
  if net ~ [10.110.0.0/24, 10.120.0.0/24, 10.130.0.0/24, 10.140.0.0/24] &&
     (proto = "own_dc" || proto ~ "mesh_*") then {
        if net != 10.110.0.0/24 then {
            bgp_path.prepend(65011);
            bgp_path.prepend(65011);
            bgp_path.prepend(65011);
        }
        accept;
  }
  reject;
}
```

### B1: 24 DC/Azure acceptance directions

**DC -> Azure spoke**

| DC / Azure spoke | spoke-eu | spoke-us | spoke-jp |
|---|---|---|---|
| dc-eu | P/P | F/F | P/P |
| dc-us | F/F | P/P | P/P |
| dc-jp | F/F | F/F | F/F |
| cn | F/F | F/F | P/P |

**Azure spoke -> DC**

| DC / Azure spoke | spoke-eu | spoke-us | spoke-jp |
|---|---|---|---|
| dc-eu | P/P | F/P | P/P |
| dc-us | F/P | P/P | P/P |
| dc-jp | F/F | F/F | F/F |
| cn | F/P | F/P | P/P |

## B2: Customer backbone through AS-path control

All hubs use `ASPath`. EU/US nonlocal extra prepends are removed; Japan still has no extra prepends. Azure imports remain spoke-only, so NVAs keep foreign DCs on their mesh. Removing prepends shortens the local offer; this is not a claim that adding prepends everywhere favors the customer backbone.

Matched state: [B2, zero extra EU/US prepends](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-B2-20261017/B2/scenario-result.json). Full BIRD configurations: [EU](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-B2-20261017/B2/router-eu.conf), [US](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-B2-20261017/B2/router-us.conf), [JP](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-B2-20261017/B2/router-jp.conf), [CN](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-B2-20261017/B2/router-cn.conf).

### B2: complete EU firewall table

| Prefix | ASPath | NextHopType |
|---|---|---|
| `10.110.0.0/24` | `65011` | HubBgpConnection |
| `10.140.0.0/24` | `65011-65014` | HubBgpConnection |
| `10.130.0.0/24` | `65011-65013` | HubBgpConnection |
| `10.120.0.0/24` | `65011-65012` | HubBgpConnection |
| `10.210.0.0/24` | empty | Virtual Network Connection |
| `10.10.0.0/24` | empty | Virtual Network Connection |
| `10.30.0.0/24` | `65520-65520` | Remote Hub |
| `10.220.0.0/24` | `65520-65520` | Remote Hub |
| `10.20.0.0/24` | `65520-65520` | Remote Hub |
| `0.0.0.0/0` | empty | Internet |

### B2: complete JP firewall table

| Prefix | ASPath | NextHopType |
|---|---|---|
| `10.140.0.0/24` | `65013-65014` | VPN_S2S_Gateway |
| `10.120.0.0/24` | `65013-65012` | VPN_S2S_Gateway |
| `10.110.0.0/24` | `65013-65011` | VPN_S2S_Gateway |
| `10.130.0.0/24` | `65013` | VPN_S2S_Gateway |
| `10.10.0.0/24` | `65520-65520` | Remote Hub |
| `10.220.0.0/24` | `65520-65520` | Remote Hub |
| `10.20.0.0/24` | `65520-65520` | Remote Hub |
| `10.210.0.0/24` | `65520-65520` | Remote Hub |
| `10.30.0.0/24` | empty | Virtual Network Connection |
| `0.0.0.0/0` | empty | Internet |

### B2: EU selected NVA routes

| Prefix | Protocol | BGP next hop | BIRD resolution | ASPath | LP | Marker |
|---|---|---|---|---|---|---|
| `10.110.0.0/24` | `own_dc` | `n/a` | `via 10.210.0.1 on eth0` | `n/a` | n/a | `*` |
| `10.120.0.0/24` | `mesh_us` | `172.31.0.2` | `dev wgeuus` | `65012` | 100 | `*` |
| `10.130.0.0/24` | `mesh_jp` | `172.31.0.6` | `dev wgeujp` | `65013` | 100 | `*` |
| `10.140.0.0/24` | `mesh_cn` | `172.31.0.10` | `dev wgeucn` | `65014` | 100 | `*` |
| `10.10.0.0/24` | `azure_0` | `10.210.0.1` | `via 10.210.0.1 on eth0` | `65515` | 300 | `*` |
| `10.20.0.0/24` | `mesh_us` | `172.31.0.2` | `dev wgeuus` | `65012 65515` | 300 | `*` |
| `10.30.0.0/24` | `mesh_jp` | `172.31.0.6` | `dev wgeujp` | `65013 65515` | 300 | `*` |

### B2: JP selected NVA routes

| Prefix | Protocol | BGP next hop | BIRD resolution | ASPath | LP | Marker |
|---|---|---|---|---|---|---|
| `10.110.0.0/24` | `mesh_eu` | `172.31.0.5` | `dev wgeujp` | `65011` | 100 | `*` |
| `10.120.0.0/24` | `mesh_us` | `172.31.0.13` | `dev wgusjp` | `65012` | 100 | `*` |
| `10.130.0.0/24` | `own_dc` | `n/a` | `dev eth0` | `n/a` | n/a | `*` |
| `10.140.0.0/24` | `mesh_cn` | `172.31.0.22` | `dev wgjpcn` | `65014` | 100 | `*` |
| `10.10.0.0/24` | `mesh_eu` | `172.31.0.5` | `dev wgeujp` | `65011 65515` | 300 | `*` |
| `10.20.0.0/24` | `mesh_us` | `172.31.0.13` | `dev wgusjp` | `65012 65515` | 300 | `*` |
| `10.30.0.0/24` | `azure_1` | `169.254.21.6` | `via 169.254.21.6 on xfrm42` | `65515` | 300 | `!` |

### B2: CN selected NVA routes

| Prefix | Protocol | BGP next hop | BIRD resolution | ASPath | LP | Marker |
|---|---|---|---|---|---|---|
| `10.110.0.0/24` | `mesh_eu` | `172.31.0.9` | `dev wgeucn` | `65011` | 100 | `*` |
| `10.120.0.0/24` | `mesh_us` | `172.31.0.17` | `dev wguscn` | `65012` | 100 | `*` |
| `10.130.0.0/24` | `mesh_jp` | `172.31.0.21` | `dev wgjpcn` | `65013` | 100 | `*` |
| `10.140.0.0/24` | `own_dc` | `n/a` | `dev eth0` | `n/a` | n/a | `*` |
| `10.10.0.0/24` | `mesh_eu` | `172.31.0.9` | `dev wgeucn` | `65011 65515` | 300 | `*` |
| `10.20.0.0/24` | `mesh_us` | `172.31.0.17` | `dev wguscn` | `65012 65515` | 300 | `*` |
| `10.30.0.0/24` | `mesh_jp` | `172.31.0.21` | `dev wgjpcn` | `65013 65515` | 300 | `*` |

### B2: captured EU export policy

```bird
filter azure_export {
  if net ~ [10.110.0.0/24, 10.120.0.0/24, 10.130.0.0/24, 10.140.0.0/24] &&
     (proto = "own_dc" || proto ~ "mesh_*") then {
        accept;
  }
  reject;
}
```

### B2: 24 DC/Azure acceptance directions

**DC -> Azure spoke**

| DC / Azure spoke | spoke-eu | spoke-us | spoke-jp |
|---|---|---|---|
| dc-eu | P/P | P/P | P/P |
| dc-us | P/P | P/P | P/P |
| dc-jp | F/F | F/F | F/F |
| cn | P/P | P/P | P/P |

**Azure spoke -> DC**

| DC / Azure spoke | spoke-eu | spoke-us | spoke-jp |
|---|---|---|---|
| dc-eu | P/P | P/P | P/P |
| dc-us | P/P | P/P | P/P |
| dc-jp | F/F | F/F | F/F |
| cn | P/P | P/P | P/P |

## Original state restored

Each policy controller restored the exact BIRD bytes, owner/mode/nanosecond modification time and original all-enabled hub settings before the next variant. The final controller restored the pre-test mixed hub flags and HRPs. An independent full capture matched the original BIRD sources and paired firewall winners. Only VMs started for this rerun were returned to their original power states. The temporary A route table was removed and its original subnet association verified. No IPsec or WireGuard configuration was changed.

[Independent state evidence](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-independent-verify-20261017/independent-verification/scenario-result.json); [power restoration](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/b2b-power-stop-20261017/power-verdict.json).
