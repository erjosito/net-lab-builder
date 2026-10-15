# Three-hub SD-WAN / Virtual WAN lab card

**Locked design, 2026-10-14 — Morpheus / Jose Moreno.** Approved. Azure only; no ER/Megaport/GCP/public repo/blog. **Japan East; West Europe; North Central US** selected; live VM validation passed all three on 2026-10-14. Germany West Central and initial US regions unavailable/restricted. Geography-preserving fallbacks authorized. China DC logical in Japan East, not sovereign China/latency simulation.

## Main objective
Measure Azure->DC preference **at each vHub**: local/interhub SD-WAN and JP VPN. Derive **outbound DC AS prepend thresholds** under ExpressRoute (default policy, no circuit), VPN and ASPath, before/after PrivateTraffic routing intent (RI). Bidirectional traffic confirms symmetry; no throughput/speed claims.

Standard vWAN, three hubs/spokes. EU/US BIRD NVAs in hub-connected transit VNets; JP strongSwan+BIRD active-active S2S; China combined router/probe, no ingress. Four DC VNets fully peer with forwarding/UDRs; peering is not transitive. Six private WireGuard tunnels/fullmesh eBGP prevent fabric bypass. EU/US use genuine peered-VNet **HubBgpConnection**, not integrated vendor **VPN_S2S_Gateway** semantics.

## Address plan
| Site | Region | DC; transit; spoke; hub | NVA ASN |
|---|---|---|---|
| EU | westeurope | 10.110.0.0/24; 10.210.0.0/24; 10.10.0.0/24; 10.250.0.0/23 | 65011 |
| US | northcentralus | 10.120.0.0/24; 10.220.0.0/24; 10.20.0.0/24; 10.250.2.0/23 | 65012 |
| JP | japaneast | 10.130.0.0/24; none; 10.30.0.0/24; 10.250.4.0/23 | 65013 |
| CN logical | japaneast | 10.140.0.0/24; none; none; none | 65014 |

Hub ASN65515; overlay172.31.0.0/24; JP BGP169.254.21.0/24. Routers .4/probes .10. Each ingress advertises all four DC /24s identically to both peers; strict filters block Azure re-export loops.

## Resource / cost / time envelope
9 VNets,3 minimum-capacity hubs,5 VNet connections,26 directed peerings;10 Ubuntu22.04 VMs/NICs/StandardSSD disks:4 routers (CN combined),3 DC probes,3 spokes.10 Standard PIPs for bootstrap, no inbound except JP IKE; NSGs/UDRs. One minimum-scale JP VPN gateway/site/link/connection,2 tunnels. RI adds **3 AZFW_Hub Standard firewalls**, shared policy,3 managed PIPs. **Basic unsupported.** No Bastion/LB/NAT Gateway/license.

Validated sizes for routers/probes: JP/EU Standard_B2ts_v2; US Standard_B2als_v2 (B1 catalog empty). JP unzoned (zone2 restricted). All three passed `az vm create --validate` in the tagged lab RG; no probe VMs created. SSH-key Ubuntu22.04, StandardSSD30GB, no Spot. See infrastructure-handoff.json for actual deployment state, not full-lab acceptance.

Indicative baseline ~$1–3/h; secured ~$5–8/h plus processing/peering/egress. Firewalls alone ~$3.75/h, not regional quote. Allow ~$10–32/2–4h. Provision30–60min, RI15–45min, tests60–120min; no overnight hold.

## Four scenarios / decisive evidence
1. **Unsecured policy baseline:** zero extra prepends; ExpressRoute, VPN, ASPath on all hubs in separately leased subcases. Each snapshots all four DCs at all three hubs and runs the 4x3 route matrix.
2. **Unsecured prepend sweep:** select one ingress at a time; add 0,1,2,4,8 copies of its ASN on all four outbound DC routes. Snapshot every hub at each step under each HRP; refine a changed winner's adjacent interval to exact integer threshold. If no switch by8, report bounded no-switch, not infinity. Restore between ingress/HRP runs.
3. **Secured comparison:** restore zero prepends; deploy firewalls then RI sequentially EU/US/JP. Repeat all three HRP baselines and the decisive sweep boundaries from scenario2; bounded extra sweep if thresholds differ.
4. **Direction/symmetry control:** isolate learned Azure-spoke prepend from outbound DC prepend, equalizing overlay local preference before manipulating paths. Show which direction changes; full 4x3 bidirectional TCP/ICMP confirms regional ingress and asymmetric cases.

Every subcase: **effective routes at EACH hub**, competing candidate source/path and winning next hop/path, BIRD/FIB/NIC/VPN evidence. Each4x3 matrix is one validation lease. Missing evidence=INCONCLUSIVE. Interhub adds65520 twice; local paths >=2 longer can race under ER/VPN preference. Capture repeated tie/boundary snapshots; locality is not absolute.

## Ownership / exit
Separate design/Tank mutation/Niobe validation leases. Deploy<=60min/150calls/6 ARM batches; command<=1200s, async<=45min/120s polls/no orphan. Stop80%, checkpoint15min/25calls; restore<=15min or BLOCKED/new owner. **Secured/no-RI NVA BGP unsupported**: firewall-only transition, not baseline. Evidence first; automatic cleanup only created RG, verified run/owner tags.

Learn: [BGP](https://learn.microsoft.com/en-us/azure/virtual-wan/scenario-bgp-peering-hub), [HRP](https://learn.microsoft.com/en-us/azure/virtual-wan/about-virtual-hub-routing-preference), [RI](https://learn.microsoft.com/en-us/azure/virtual-wan/how-to-routing-policies).
