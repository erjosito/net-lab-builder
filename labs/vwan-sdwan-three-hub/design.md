# Three-hub network handoff

2026-10-14 Trinity. Design only, no live actions/results. Locked Morpheus
topology; one baseline. No ER circuit/vendor NVA/throughput/publication.

## Bindings / gates

| Site | DC / ASN | Router endpoint | Transit; spoke; hub |
|---|---|---|---|
| EU | 10.110.0.0/24 / 65011 | 10.210.0.4 | 10.210.0.0/24;10.10.0.0/24;10.250.0.0/23 |
| US | 10.120.0.0/24 / 65012 | 10.220.0.4 | 10.220.0.0/24;10.20.0.0/24;10.250.2.0/23 |
| JP | 10.130.0.0/24 / 65013 | 10.130.0.4 | none;10.30.0.0/24;10.250.4.0/23 |
| CN logical | 10.140.0.0/24 / 65014 | 10.140.0.4 | none |

Probes .10/CN .4; locked inventory,peering access/forwarding on,transit off.

Regions: EU=westeurope B2ts_v2; JP/CN=japaneast B2ts_v2 **unzoned**.
US unresolved: EastUS/EastUS2/CentralUS catalogs empty; WestUS2 restricted.
Coordinator probes WestUS3/SouthCentralUS/NorthCentralUS. No US lock/geography
change; catalog != capacity.

EU/US HubBgpConnection -> directly connected transit: NIC .4, BOTH live
virtualRouterIps/65515, identical exports,eBGP multihop,180/60.
Default association/label propagation,branch-to-branch on; no custom/static hub routes.

Corrections: no loopback/on-prem/Route Server direct hub peers; no DC hub
attachment (system-route bypass). Peered-VNet BGP != vendor VPN_S2S_Gateway.
Secured/no-RI direct BGP unsupported. **One VPN link has one CPE BGP IP**:
handoff .1/.5 becomes **169.254.21.1 on lo for both sessions**, .5 unused.

## Six WireGuard AllowedIPs contracts

Independent interfaces, direct per-link UDP51821-51826 in table order,
Table=off,MTU1380,keepalive25. Both ends use the same port; no port translation.
S=10.10.0.0/24,10.20.0.0/24,10.30.0.0/24 (expand literally); tunnel +1/+2.

| Pair | /30 | Physical endpoints | First AllowedIPs | Second AllowedIPs |
|---|---|---|---|---|
| EU-US | 172.31.0.0/30 | 10.210.0.4,10.220.0.4 | 172.31.0.2/32,10.120.0.0/24,S | 172.31.0.1/32,10.110.0.0/24,S |
| EU-JP | 172.31.0.4/30 | 10.210.0.4,10.130.0.4 | 172.31.0.6/32,10.130.0.0/24,S | 172.31.0.5/32,10.110.0.0/24,S |
| EU-CN | 172.31.0.8/30 | 10.210.0.4,10.140.0.4 | 172.31.0.10/32,10.140.0.0/24,S | 172.31.0.9/32,10.110.0.0/24,S |
| US-JP | 172.31.0.12/30 | 10.220.0.4,10.130.0.4 | 172.31.0.14/32,10.130.0.0/24,S | 172.31.0.13/32,10.120.0.0/24,S |
| US-CN | 172.31.0.16/30 | 10.220.0.4,10.140.0.4 | 172.31.0.18/32,10.140.0.0/24,S | 172.31.0.17/32,10.120.0.0/24,S |
| JP-CN | 172.31.0.20/30 | 10.130.0.4,10.140.0.4 | 172.31.0.22/32,10.140.0.0/24,S | 172.31.0.21/32,10.130.0.0/24,S |

AllowedIPs checks received source too: S required everywhere; DC owner only.
Overlap across separate interfaces safe with Table=off. eBGP remote tunnel
IP/site ASN,next-hop-self,180/60 both ends; no transit DC re-export.

Discover NIC/gateway G. Pin remote physical router /32s via G/dev NIC in
Linux table100, selected by rule100/fwmark0x200 for outer WireGuard transport.
Keep the same control resolution in BIRD underlay; never self-route.
Hub/IKE control pins remain in the main table. Marked endpoint resolution
stays physical; ordinary remote DC traffic, including CN's .4, goes WG.

## BIRD tables / provenance / forwarding

underlay4=resolution only: NIC/G,WG /30s,control/JP VPN peer /32s,interface-bound
onlink statics; never export. lab4=four DC+S,one IPv4 channel/session.
Never resolve peers through lab4/kernel default; kernel import none.

Import attributes: kind1 own DC,2 peer DC,3 direct S,4 overlay S;
ingress=65011/12/13. Overwrite incoming attributes; protocol-name provenance.

| Source | lab4 import | Export |
|---|---|---|
| own_dc static | Own DC only,kind1; EU/US via G, JP/CN connected | Filters below |
| WG peer | Its exact DC kind2; exact S kind4 only from EU/US/JP, ingress=peer | Own DC kind1 + S kind3 ONLY |
| EU/US hub0/1; JP vpn0/1 | Exact S kind3,ingress=self; reject ALL DCs | Exactly four DCs kinds1/2, identical both peers |
| Kernel | none | Resolved exact seven prefixes only; no control/peer routes |

Azure export exactly **10.110.0.0/24,10.120.0.0/24,10.130.0.0/24,
10.140.0.0/24**, never Azure/default. Preserve origin AS_PATH,no allowas-in.
CN no Azure ingress. Count0 own/remote lengths1/2 (EU->CN=65011 65014).
Counts=additional local-AS copies in Azure export only,same map both peers;
outbound UPDATE verifies implicit insertion if BIRD export omits it.

Next-hop resolution:
- EU/US direct S: bgp_next_hop=G,resolution underlay4/G connected. Linux
  `via G dev NIC`, NOT device-only S or hub BGP peer packet next hop.
- WG: remote /30 neighbor via underlay4.
- JP direct S: Azure peer /32 via xfrm41/42; keep candidates,install winner.
- Own EU/US DC via G/peering; JP/CN connected Linux-owned.

Kernel export resolved data only,distinct protocol/metric; Linux owns pins.
export-all poisons peers; export-none breaks forwarding. Separate resolution
prevents endpoint recursion. S localpref regional300/others100 on all routers,
including direct remote S; DC->Azure only. Forward-prepend control equalizes LP.

## UDRs / NSGs / bootstrap

| Location | Route |
|---|---|
| EU/US DC workload subnet | Other three DCs + S -> own transit .4,VirtualAppliance |
| JP DC shared subnet | NO subnet self-UDR; probe guest six routes via JP .4 |
| CN combined probe | Bind .4; router FIB, no self-UDR |
| Transit routers | No data-prefix UDR to self; retain endpoint fabric routes |
| Spokes | Hub routes, no DC peering/static NVA UDR |

NIC/OS forwarding,rp_filter loose/off,no private SNAT. Ten bootstrap PIPs,
no public management; Run Command/key auth azurelabuser,serialize per VM.
DNS168.63.129.16/IMDS169.254.169.254/agent HTTPS underlay; verify MTU/MSS.

| NSG priority | Inbound permit | Why |
|---|---|---|
| 1000-1005 | Exact remote physical router /32 -> .4 on its link's UDP51821-51826, inbound and outbound | Private WG |
| 110 | Two hub peer /32s -> EU/US .4 TCP179 | Direct BGP |
| 120 | Live gateway public /32s -> JP UDP500/4500 | IKE/NAT-T |
| 130 | Exact DC + S ICMP/TCP5201 | Probe |
| 140 | Exact DC + S forwarded data on router NICs | Inner traffic |
| 4000 | Deny remainder before default AllowVNet | No accidental bypass |

Mirror outbound; guest179 WG/XFRM peers only. Capture proves anti-bypass.
JP router shares probe subnet: subnet UDRs to .4 would recurse WG endpoints.
Use probe guest routes only; kernel export excludes JP/CN connected own DC.

## JP live-binding template (Tank only)

Gateway bgpSettings.bgpPeeringAddresses/site config join by ipconfigurationId,
not array order. Link CPE PIP/65013/.21.1; custom values must preexist.

| Slot | Local BGP | Azure custom BGP | XFRM/if_id | IKE remote |
|---|---|---|---|---|
| 0 | 169.254.21.1/32 lo | 169.254.21.2/32 | xfrm41/41 | `<live instance0 PIP>` |
| 1 | same .1 lo | 169.254.21.6/32 | xfrm42/42 | `<live instance1 PIP>` |

vpnLinkConnection.enableBgp=true; selections
`{ipConfigurationId:<live id>,customBgpIpAddress:<.2 or .6>}`.
StrongSwan local10.130.0.4/identity `<JP PIP>`,runtime PSK,IKEv2,NAT-T;
TS0/0,if_id_in/out41/42,agreed Azure IKE/ESP policy,no automatic broad routes.
Public peers via G,custom /32s via XFRM. BIRD active-open/source .1,multihop.
Azure default-IP SYNs do not disprove custom mapping. Persist XFRM/routes,
swanctl load/initiate then BIRD; VM start alone insufficient.

## Exactly one executable baseline B0

Hypothesis: **no firewall/RI, all hubs ExpressRoute HRP,count0** gives reachable
DC winners EACH hub from verified exports. US/capacity resolved,Tank idle,
six WG/four hub/two VPN sessions stable,pair exports equal,no static conflicts.

Niobe lease<=30min/75calls/zero mutations; command<=600s:
1. Capture bindings/config hashes, BIRD candidates/exports, FIB/NIC routes.
2. Four DC effective routes at EU,US,JP; two stable snapshots>=120s apart.
3. Tiny TCP5201/ICMP from each spoke .10 to each DC probe (CN .4):12 cells.
   Bounded captures correlate inner tuple/sequence,exit/return ingress.

PASS:12 stable winner AS_PATH/ECMP sets,verified exports,12 matching flows/
no bypass; report asymmetry. FAIL:filters/recursion/bypass/forwarding failure.
INCONCLUSIVE:missing winner/path/instability; hidden losers limit explanation.
STOP sentinel/expiry/80% budget/flap/first failed gate; no retry.
Verdict/evidence/restore<=5min. Restore=unchanged hashes/count0/HRP/RI/routes;
drift BLOCKED,new Tank recovery<=15min.

## Evidence reads — every later subcase too

az rest,api-version2026-01-01 (record provider-supported version);
POST reads,202 Location/Retry-After bounded. H=`<hub ARM id>`.

| Read | Request |
|---|---|
| No-RI winner | POST H/effectiveRoutes body `{"resourceId":"H/hubRouteTables/defaultRouteTable","virtualWanResourceType":"RouteTable"}` (expand H) |
| PrivateTraffic RI | ALSO same POST, resourceId=`<firewall-id>`,virtualWanResourceType=`AzureFirewall`; default table aggregates -> firewall, firewall table gives inspected DC exit |
| VPN learned/advertised | POST JP-H/inboundRoutes and /outboundRoutes; body `{"connectionType":"VpnConnection","resourceUri":"<vpnGateway-id>/vpnConnections/<name>"}` |
| Transit connection view | Same inbound/outbound with HubVirtualNetworkConnection/full transit connection id; do NOT assume BGP Adj-RIB-In visibility |
| Bindings | vhub bgpconnection show; vpn-gateway/connection/hub show, JSON |
| BIRD | `show protocols all`; `show route table lab4 all`; `show route export <peer> all`; `show route protocol <peer> all` |
| Guest/fabric | ip route show table all/route get; WG/XFRM/SA state; `az network nic show-effective-route-table` |

No bgpconnection learned-route command; no Route Server/VNet Gateway substitution.
Hub advertisements=BIRD received RIB; learned paths=effective+verified export/
UPDATE. Empty VPN read=unavailable,not zero. Save full value/addressPrefixes/
nextHops/nextHopType/routeOrigin/asPath. Effective tables need not expose losers;
hubs export winners only. Preserve exposed competitors,otherwise label
**reconstructed from verified ingress exports**, conditional on remote selection
and interhub65520 65520, NEVER raw receipt.

Current-correlation manifest:
UTC,correlation,hub,prefix,HRP,RI,ingress,count,peer,command,exit,rawPath,sha256,
visibility(raw/reconstructed/unavailable),assertion.
Bounded full-output retrieval,no truncation/historical scans/secrets.

## Follow-on parameter sweeps ONLY

Fresh (HRP,RI,ingress,prefix,count) lease,others0,pair exports equal.
ExpressRoute/VPN/ASPath; RI off/all-three on; **0,1,2,3,4**,then8 if necessary,
5..7 refine switch. Per-hub/prefix thresholds,repeat ties/ECMP; no switch
through8 bounded,not infinity. LPM/static first,ER/VPN locality,ASPath length;
interhub65520 twice; local>=2 longer locality race. No ER failover claim.

RI: Standard AZFW_Hub/shared scoped policy; snapshot,firewalls Succeeded then
sequential EU/US/JP PrivateTraffic. Mixed/firewall-only transition,not test.
Each subcase all-hub default+firewall routes/flow evidence. Restore0/hashes;
unsecured removes RI AND firewalls; >15min BLOCKED/new owner.

## Resiliency analysis

B0 no firewall; RI no bypass. Production: evaluate correlated failures,
stateful asymmetry/unmeasured convergence; single-router DC gateways NOT HA.

| Failure | Blast radius / response |
|---|---|
| EU/US router | Local DC gateway/ingress lost; others survive; hold180s/restore VM |
| JP/CN router | JP VPN/DC lost; CN isolated; others survive; restore XFRM/BIRD |
| WG/BGP pair | DC through ingress lost,no transit export; hold180s/recover pair |
| Hub session | Other peer survives; transient seconds-minutes/recover |
| JP tunnel/session | Other survives; DPD/hold seconds-minutes/recover |
| Hub/control-plane/region | Local spoke/hub lost; managed/manual minutes |
| RI firewall/policy | Drop,no bypass,possible asymmetry; manual/managed recovery |
| BIRD/agent/config | VM routing/visibility lost; manual bounded recovery |

Dormant P1=boot persistence; P2=failed-ingress withdrawal. Zero cost,DC SPOF
persists; fresh approval/lease,added redundancy needs redesign.

Sources: Learn vWAN BGP/HRP/RI and Virtual Hubs effective/inbound REST,
2026-01-01. Policy/skills/vault guidance read,no vault writes.
