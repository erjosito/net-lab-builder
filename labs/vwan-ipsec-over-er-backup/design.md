# vWAN IPsec-over-ExpressRoute with Internet backup - network design

**Owner:** Trinity | **Status:** authoritative, corrected after live BGP discovery | **Date:** 2026-09-28
**Scope:** design only; no deployment or IaC. `manifest.md` and the Morpheus review remain authoritative for region, products, cost authorization, and provider sequencing.

## 1. Verdict and invariants

**Verdict:** **APPROVE corrected D2** using regular-private BGP on the ER link and custom APIPA BGP on the Internet link. **REJECT D1**; do not mutate live resources to test it. D3 remains approved as a deterministic, health-blind comparison. Live evidence showed that regular private identities on both sites make Azure use the same default peers `10.240.0.12/.13`; custom gateway APIPA addresses are selected only when the corresponding site-link peer is APIPA.

Invariants:

- Standard vWAN, one Sweden Central vHub, one vHub ER gateway, one vHub S2S VPN gateway, one workload VNet connection, and one ER connection.
- One GCP Linux CPE reaches the vHub VPN gateway through two independent underlays: private Partner Interconnect/Megaport/ER and public GCP Internet.
- Use **two Azure VPN Site resources**, each with one link: `site-gcp-er` and `site-gcp-inet`. BGP is site-scoped, so this separation is required for D2/D3 policy.
- Each site link creates two IPsec tunnels, one per active-active vHub VPN gateway instance. Four logical slots remain stable even though Azure endpoint addresses are deployment-discovered.
- Never advertise experiment prefixes on the ER underlay. Never learn an IKE endpoint through the overlay it establishes.
- Hub routing preference is `ASPath`. Both candidate paths are S2S VPN routes at the hub; the ER physical underlay does not make the private overlay an ER route.
- Sources: [[Services/Azure-Virtual-WAN]], [[Services/ExpressRoute]], [[Services/VPN-Gateway]], [[Services/Megaport]], [[Topics/BGP-on-Azure]], [[Topics/UDR-and-Effective-Routes]]. Microsoft Learn confirms: the VPN-over-ER CPE BGP peer **cannot be APIPA**; generic vWAN custom BGP addresses are APIPA-only (`169.254.21.*`/`169.254.22.*`); each gateway instance can own multiple custom addresses; and each `vpnLinkConnection` selects one custom address per gateway IP configuration.

## 2. Exact topology

```text
Azure probe 10.241.0.4/24
  workload VNet 10.241.0.0/24
            |
  vHub 10.240.0.0/24 (HRP=ASPath)
     |                          |
 vHub ER GW                 vHub VPN GW ASN 65515
     |                    / private Instance0/1 (site-gcp-er)
 ER circuit 50 Mbps       \ public  Instance0/1 (site-gcp-inet)
     |
 Azure MSEE primary + secondary
     | two Azure VXCs, same service key, distinct MSEE paths
 Stockholm-compatible Megaport MCR (live ASN)
     |
 one GCP Partner Interconnect VXC
     |
 VLAN attachment + Cloud Router ASN 16550
     |
 GCP VPC 10.250.0.0/24, secondary 10.250.254.0/24
     |
 Linux CPE 10.250.0.10 + reserved public IPv4
 StrongSwan XFRM + FRR ASN 65050
```

Megaport owns Azure private-peering creation. Tank must not create competing Azure private peering. The circuit must be `Provisioned`, both Azure VXC BGP legs established, and the GCP attachment operational before the vHub ER connection is accepted as healthy.

## 3. Address and ASN plan

### Routed and local addresses

| Purpose | Exact value | Advertisement |
|---|---:|---|
| vHub | `10.240.0.0/24` | Azure advertises through ER and VPN as platform behavior |
| Workload VNet/subnet | `10.241.0.0/24` / `10.241.0.0/26` | vWAN advertises; probe uses `10.241.0.4` if available, otherwise Tank records assigned IP |
| GCP VPC subnet / CPE | `10.250.0.0/24` / `10.250.0.10` | ER underlay advertises only `10.250.0.10/32` |
| CPE private peer-identity range | `10.250.254.0/24` | Never advertised through ER or as payload |
| D2 private BGP source | `10.250.254.240/32` | Inside private IPsec only; regular private address required by VPN-over-ER |
| D2 public BGP source | `169.254.22.1/32` | Inside public IPsec only; CPE initiates both BGP sessions |
| FRR router ID | `10.250.254.250` | Identifier only |
| D1 payload | `10.253.1.0/24` | Reserved; D1 rejected and not run |
| D2 payload | `10.253.2.0/24` | Only during D2 |
| D3 aggregate | `10.253.3.0/24` | Internet site static route |
| D3 specifics | `10.253.3.0/25`, `10.253.3.128/25` | Private-site BGP only |

The `.240` and `.250` addresses must be registered GCP alias-IP `/32`s, or an equivalent supported routed construct. `169.254.22.1/32` is assigned locally to the CPE loopback/dummy interface for BGP inside IPsec and is never advertised to GCP.

### ASNs and generated slots

| Plane | ASN/router ID |
|---|---|
| vWAN VPN gateway | `65515` |
| Azure MSEE | `12076` |
| GCP Cloud Router | `16550` |
| Linux CPE overlay | `65050`, router ID `10.250.254.250` |
| Megaport MCR | Deployment-discovered; must not equal `65050`, `16550`, `65515`, or `12076` |

Corrected live/session mapping:

| Slot | CPE endpoint | CPE BGP source | Azure IKE endpoint | Azure BGP peer |
|---|---|---|---|---|
| `pri0` | `10.250.0.10` | `10.250.254.240` | private `Instance0` | default `10.240.0.12` |
| `pri1` | `10.250.0.10` | `10.250.254.240` | private `Instance1` | default `10.240.0.13` |
| `pub0` | reserved public IPv4 via 1:1 NAT | `169.254.22.1` | public `Instance0` | custom `169.254.22.2` |
| `pub1` | reserved public IPv4 via 1:1 NAT | `169.254.22.1` | public `Instance1` | custom `169.254.22.3` |

At gateway scope, add `169.254.22.2` to instance-0's `customBgpIpAddresses` and `169.254.22.3` to instance-1's list. On the public `vpnLinkConnection`, map each gateway `ipConfigurationId` to its address through `vpnGatewayCustomBgpAddresses`. Do not assign custom APIPA to the private ER link.

Managed vWAN therefore exposes four distinct Azure peer IPs, but only two are custom APIPA: `10.240.0.12`, `10.240.0.13`, `169.254.22.2`, and `169.254.22.3`. Four supported custom APIPA peers are impossible because the private VPN-over-ER site cannot use an APIPA CPE peer.

## 4. Underlay isolation and anti-recursion

The CPE has one NIC. GCP selects Partner Interconnect for learned Azure private routes and Internet for public destinations; Linux still pins every control-plane endpoint.

1. Cloud Router custom-advertises only `10.250.0.10/32` toward Partner Interconnect. Do not advertise `10.250.254.0/24` or `10.253.0.0/16`.
2. Before StrongSwan starts, install persistent `/32` routes:
   - each Azure **private** IKE endpoint: `via 10.250.0.1 dev <nic>`, verified by GCP as Partner-Interconnect reachable;
   - each Azure **public** IKE endpoint: `via 10.250.0.1 dev <nic>`, verified as Internet next hop;
   - `10.240.0.12/32 dev xfrm-pri0 src 10.250.254.240`;
   - `10.240.0.13/32 dev xfrm-pri1 src 10.250.254.240`;
   - `169.254.22.2/32 dev xfrm-pub0 src 169.254.22.1`;
   - `169.254.22.3/32 dev xfrm-pub1 src 169.254.22.1`.
3. Endpoint `/32`s must have lower metric than any broader route and survive reboot. A private endpoint covered by `10.240.0.0/24` must still resolve to the physical NIC, never to XFRM.
4. Install persistent FRR `Null0` routes for `10.240.0.0/24` and `10.241.0.0/24` at administrative distance `254`. Overlay eBGP uses distance `20`; D3's public-XFRM static route uses distance `250`; endpoint/peer `/32`s win by LPM. If all overlay routes disappear, payload fails closed instead of following the GCP VPC's direct cleartext ER route.
5. Exclude all Azure IKE endpoint `/32`s, Azure/CPE BGP peer `/32`s, `10.250.254.0/24`, `169.254.22.0/24`, and `10.250.0.10/32` from FRR redistribution and experiment prefix lists.
6. Disable automatic StrongSwan route installation (`install_routes = no` or equivalent). The deployment owns deterministic XFRM peer routes.
7. Required proof per slot:
   - `ip route get <IKE-endpoint> from 10.250.0.10` resolves to the physical NIC;
   - `ip route get <Azure-BGP-peer> from <local-peer-IP>` resolves to the assigned XFRM interface;
   - packet capture shows IKE/ESP or NAT-T on the intended underlay and TCP/179 only inside the intended XFRM path.
   - with all overlay routes intentionally removed, `ip route get 10.241.0.4` resolves to blackhole/unreachable, never the physical NIC/ER path.

Any missing or recursive host route is an implementation defect, not evidence against D2/D3.

## 5. StrongSwan and FRR model

Use route-based IKEv2 with four XFRM interfaces:

| Slot | Interface | XFRM ID | StrongSwan child | FRR neighbor class |
|---|---|---:|---|---|
| `pri0` | `xfrm-pri0` | `410` | `pri0` | private |
| `pri1` | `xfrm-pri1` | `411` | `pri1` | private |
| `pub0` | `xfrm-pub0` | `420` | `pub0` | public |
| `pub1` | `xfrm-pub1` | `421` | `pub1` | public |

Use Azure-generated distinct PSKs per site connection, injected at runtime and never committed or persisted in IaC state. Public tunnels use NAT-T when GCP 1:1 NAT is detected. Permit UDP/500, UDP/4500, and ESP only between the corresponding Azure gateway endpoint(s) and CPE endpoint; permit TCP/179 only for the four corrected neighbor tuples after decapsulation. Azure can initiate the private sessions from `10.240.0.12/.13`; for custom APIPA, Azure accepts but does not initiate, so FRR must actively connect to `169.254.22.2/.3`. Enable NIC and OS IP forwarding. Do not SNAT `10.241.0.0/24` to/from the experiment prefixes.

FRR `zebra`, `bgpd`, and `staticd` are the baseline. BIRD 2 is an acceptable implementation substitution only if Tank keeps the same four-neighbor, source-address, route-filter, and preference semantics; never run FRR and BIRD simultaneously.

- Four eBGP neighbors in D2, all remote ASN `65515`: `10.240.0.12` and `.13` sourced from `10.250.254.240`; `169.254.22.2` and `.3` sourced from `169.254.22.1`.
- Use explicit `update-source`, `ebgp-multihop 2` where required by the generated peer topology, prefix lists, and route maps. No redistribution of connected or kernel routes.
- Permit only the active experiment prefix set outbound. Permit only Azure lab prefixes (`10.240.0.0/24`, `10.241.0.0/24`) inbound.
- Multipath is allowed only within the two equal private-instance sessions or within the two equal public-instance sessions. D2 must never ECMP between private and public path classes.
- Persist XFRM creation/routes and `swanctl --load-all` in separate ordered systemd units; a one-time interactive load is not reboot-safe.

## 6. D1 - rejected

**REJECT.** A single floating identity cannot be expressed while remaining inside the documented support boundary: VPN-over-ER requires a non-APIPA CPE peer, custom vWAN peers require APIPA, and every vWAN link requires a unique BGP peering IP. Reusing one regular private peer makes both connections use the same default Azure peers `10.240.0.12/.13`, losing connection-specific adjacency identity; using APIPA on the ER link violates the VPN-over-ER guidance. Preserve `10.253.1.0/24` only as an unused label and record `d1-rejected-offline`; perform no live D1 mutation.

## 7. D2 - dedicated adjacencies, preferred private overlay

D2 is the recommended design.

**Azure-to-GCP:** advertise `10.253.2.0/24` on private neighbors `10.240.0.12/.13` with natural path `65050`; advertise it on public custom peers `169.254.22.2/.3` with three additional prepends (`65050 65050 65050`). With hub HRP `ASPath`, the private pair wins and the public pair remains eligible standby.

**GCP-to-Azure:** on FRR import, set local preference `200` for private neighbors and `100` for public neighbors. Accept the same Azure prefix lengths on both. Install equal-cost paths only across the two private neighbors; on private withdrawal, install equal-cost paths across the two public neighbors.

Do not use MED as the primary signal and do not depend on Azure recognizing the physical ER underlay. Expected convergence is immediate on explicit TCP/BGP reset and otherwise bounded by observed IKE/DPD plus vWAN BGP timers; record live timers rather than claiming a tighter SLA.

Pass requires four unique neighbor tuples and four Established sessions: two default private plus two custom public. It also requires private preference in both directions, loss of only the faulted neighbor on a single-instance fault, full public takeover when both private neighbors withdraw, no private/public ECMP, and deterministic failback.

## 8. D3 - BGP specifics plus static Internet aggregate

- `site-gcp-er`: BGP enabled; advertise `10.253.3.0/25` and `10.253.3.128/25`.
- `site-gcp-inet`: BGP disabled; Azure site address space is static `10.253.3.0/24`.
- CPE reverse direction: private BGP learns `10.241.0.0/24`; install an Internet-XFRM static route for `10.241.0.0/24` at administrative distance `250`, so eBGP distance `20` wins while healthy.

Normal state uses private `/25`s by longest-prefix match. Withdrawal of both private BGP paths exposes the Internet `/24`; restore returns immediately to `/25`s.

**Health caveat:** Azure public documentation does not guarantee that a VPN site's configured static prefix is withdrawn solely because IKE/DPD is down. Treat that behavior as deployment-discovered. A stale `/24` is a latent blackhole, and a partial data-plane failure with BGP still Established also defeats failover. The CPE XFRM interface remaining administratively up is not health tracking.

The mandatory compound test is: fail public IPsec first, then withdraw private BGP. Pass means either Azure demonstrably withdraws the static aggregate or the predicted blackhole is captured and labeled. Do not claim D3 production-safe without patch P3.

## 9. Reset and contamination controls

Order: `baseline-captured -> d1-rejected-offline -> d2-corrected -> restore -> d3-prefix -> final-healthy`.

Each design is a versioned CPE/Azure configuration bundle with a paired restore operation. Before advancing, Niobe must prove:

- only the next design's `10.253.x.0/24` set exists in FRR, kernel RIB/FIB, vHub effective routes, and probe NIC effective routes;
- no prior neighbor, route map, prepend, static route, XFRM state/policy, child SA, nftables rule, or fault remains;
- both MSEE paths, MCR/VXCs, GCP attachment, both underlays, and baseline probe are healthy;
- baseline passes twice, at least one sampling interval apart.

Failure to restore within 20 minutes stops experiments. Restarting a process is insufficient: compare saved pre/post inventories and hashes of generated CPE configs.

## 10. Fault matrix

| Injection | D2 expected route behavior | D3 expected route behavior | Restore |
|---|---|---|---|
| Stop `pri0` child/BGP | Private ECMP shrinks to `pri1`; public remains standby | One `/25` path copy remains via `pri1` | Reinitiate child; neighbor Established |
| Stop both private children | `/24` withdraws private, installs public pair | `/25`s withdraw; Internet `/24` selected | Reinitiate both; verify failback |
| Stop `pub0`/`pub1` | No steady-state change; standby capacity reduced/lost | Static backup may remain programmed; expose health-blindness | Restore SAs; verify |
| Shut one Azure MSEE VXC | ER/PI remains through other MSEE; private IPsec should stay up | No route change expected | Unshut VXC; both MSEE BGP states |
| Shut both Azure VXCs or ER connection | Both private SAs/BGP peers fail; public takes over | `/25`s withdraw to `/24` if public healthy | Restore provider path then overlay |
| Shut GCP Partner attachment/VXC | Same as full private-underlay loss | Same as full private-underlay loss | Restore attachment/VXC |
| Block public UDP/500/4500 | Private stays primary; public peers fail | Steady state remains private; backup becomes unsafe | Remove rule; restore SAs |
| Stop FRR private neighbors only | D2 moves to public while IKE stays up | `/25`s withdraw; `/24` selected | Start neighbors; verify policy |
| Break one PSK | Only its two site-link tunnels fail | Per affected site; private or backup loss | Reinject original PSK; reset |
| Stop StrongSwan | All four tunnels/BGP sessions fail | All overlay paths fail | Load config, recreate XFRM, initiate |
| Stop CPE VM | Total branch loss | Total branch loss | Boot plus persistence validation |
| Public down, then private BGP withdrawal | Public takeover impossible; no valid route expected | Mandatory blackhole/withdrawal proof | Restore public first, then private |

Niobe records detection, route withdrawal, first successful probe, stable convergence, and failback timestamps. No unbounded troubleshooting: two corrected attempts per fault maximum.

## 11. Resiliency analysis

| Failure | Azure impact | GCP/branch impact | Failover / action |
|---|---|---|---|
| One VPN gateway instance/tunnel | One private and/or public slot may drop; surviving instance carries routes | Reduced tunnel redundancy, no designed outage | Seconds to BGP hold; no action unless not restored |
| Both private overlay slots | D2 uses public; D3 uses aggregate if healthy | Encrypted Internet path carries payload | Detection-dependent; investigate ER/PI |
| One MSEE path | No loss if second VXC is healthy | ER redundancy reduced | Provider convergence; repair failed VXC |
| MCR, GCP attachment, or full ER circuit | Private underlay lost despite dual MSEE | D2 public survives; D3 backup may survive | Up to tunnel/BGP convergence; provider repair |
| Public ISP/NAT path | Primary private remains | No Internet backup | No steady-state outage; repair before next private fault |
| CPE VM/NIC | All paths lost | All experiment prefixes unavailable | Manual VM recovery; architecture SPOF |
| vHub VPN gateway | All IPsec overlays lost | ER underlay may remain but payload is intentionally not sent cleartext | Managed recovery; total overlay outage |
| vHub ER gateway | Private underlay lost | Public overlay survives | Managed recovery |
| Region/vHub loss | Workload and both gateways unavailable | No usable destination | No cross-region protection in v1 |
| D3 stale static aggregate | Azure sends to dead public tunnel after private withdrawal | Blackhole; no automatic safe path | External health automation required |

The lab proves path mechanics, not production regional HA. A production reader must evaluate CPE redundancy, independent provider/PoP diversity, regional vWAN redundancy, failure detection objectives, and whether static fallback without verified withdrawal is acceptable.

### Dormant patch catalogue

Do not apply without Jose explicitly authorizing `P<n>`.

| Patch | Mitigates | Exact delta | Cost / residual gap |
|---|---|---|---|
| P1 dual CPE | CPE VM/NIC SPOF | Second CPE in separate zone, distinct endpoints/peer IPs, HA state and equal policy | Extra VM/IP; shared VPC/region remains |
| P2 dual provider edge | MCR/attachment SPOF | Second MCR and GCP Partner attachment with independent VXCs and controlled prepends | High Megaport/GCP cost; shared Azure circuit unless P2b adds circuit |
| P2b second ER circuit | Circuit/service-key SPOF | Independent ER circuit, dual MSEE VXCs, second vHub ER connection | Highest cost/ops; vHub/region remains |
| P3 D3 health withdrawal | Static blackhole | External watcher validates SA plus end-to-end probe; atomically removes/restores Azure static aggregate and CPE distance-250 route | Automation/control-plane dependency; detection not instantaneous |
| P4 CPE watchdog | Process/reboot persistence | systemd ordering, SA/BGP health watchdog, config-hash alarm, out-of-band management | Low cost; cannot fix provider failure |
| P5 regional DR | vHub/region failure | Second-region vHub/workload and independent connectivity, with application failover | Material redesign/cost; outside v1 |

## 12. Tank deploy-ready specification

Tank implements, without changing intent:

- Azure objects: vWAN, vHub `10.240.0.0/24` with HRP `ASPath`, minimum supported ER/VPN gateway scale, ER circuit/connection, workload VNet/subnet/connection, `site-gcp-er` BGP-on/private-IP connection, `site-gcp-inet` public connection, and per-design configuration bundles.
- GCP objects: isolated project, custom VPC/subnet plus alias secondary range, Cloud Router `16550`, Partner attachment, reserved public IPv4, forwarding-enabled Ubuntu CPE, narrowly scoped firewall.
- Megaport: one MCR, two Azure VXCs selecting primary/secondary MSEE, one GCP VXC.
- CPE: four XFRM slots, persistent endpoint/peer `/32`s, fail-closed Azure aggregate blackholes, FRR policy, nftables, runtime PSK injection, restore commands, and sanitized generated-value inventory.
- Required assertions before baseline: no CIDR overlap; private CPE endpoint ER-advertised/reachable; four Azure endpoint/peer mappings captured; both MSEE sessions established; MCR ASN valid; no secret/state leakage.

### Bounded Tank remediation

No gateway recreation and no IPsec change:

1. Snapshot sanitized gateway, both sites/link connections, XFRM, routes, and FRR.
2. Leave private site peer `10.250.254.240` and neighbors `10.240.0.12/.13` unchanged.
3. Change only the public site-link peer to `169.254.22.1`, ASN `65050`.
4. Add gateway custom IPs `.22.2` on instance 0 and `.22.3` on instance 1; map them on the public `vpnLinkConnection`.
5. Add CPE `169.254.22.1/32`, the two public XFRM `/32` routes, and FRR neighbors `.22.2/.3`; FRR initiates.
6. Expect four Established sessions. If Azure still uses `.12/.13` on the public connection or either custom mapping is lost, restore the captured public site/link state and stop.

## 13. Tank hard blockers

Stop Tank before billable provider order or experiment execution if:

- GCP project/billing/Partner Interconnect permission or usable `europe-north2` attachment is unavailable.
- `10.250.0.10/32` cannot be advertised over PI/ER and reached by the private vHub VPN endpoints.
- Live vWAN API cannot represent the two sites with independent private/public endpoint and BGP policy identity.
- Either Azure MSEE VXC cannot be provisioned, or an overlap exists with any live Azure/GCP/ER route.
- Generated Azure BGP peer addressing cannot be routed through four distinct XFRM slots without recursion.
- Approved private Megaport credential flow is unavailable, or live quote requires an unapproved product/tier/term substitution.

Generated endpoints, service/pairing keys, normal gateway/provider convergence, and MCR placement are deployment-discovered dependencies, not blockers unless terminal or topology-changing.

## 14. Niobe evidence handoff

For baseline, every fault, and every restore, collect:

- Azure: gateway/site/connection state; downloaded VPN configuration sanitized; vHub effective routes; probe NIC effective routes; ER primary and secondary route tables/summaries in JSON.
- Megaport: MCR/VXC inventory and BGP connection state. Looking glass is supplemental because it may be empty/unsupported.
- GCP: Cloud Router status and advertisements, attachment state, VPC routes, firewall rules, CPE alias addresses.
- CPE: `ip -d link`, `ip route`/`ip rule`, endpoint `ip route get`, `ip xfrm state/policy`, `swanctl --list-conns/--list-sas`, `show bgp summary`, neighbor received/advertised routes, RIB/FIB, nftables counters, and scoped packet captures.
- Probes: continuous timestamped ICMP plus TCP from `10.241.0.4` to one host in each active experiment prefix and reverse probes where supported.

The verdict dataset is `baseline-captured`, `d1-rejected-offline`, `d2-corrected`, `restore`, `d3-prefix`, `compound`, and `final-healthy`. Evidence must distinguish Azure validation, underlay, IKE, IPsec, BGP, route selection, and payload failure stages.
