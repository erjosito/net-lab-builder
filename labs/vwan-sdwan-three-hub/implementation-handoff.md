# Compact implementation handoff

**Current-state correction, 2026-10-15:** the historical activation below used
outer UDP51820 translation. The generator and running mesh now use direct
per-link UDP51821-51826, with endpoint-scoped inbound/outbound NSG permits and
no outer translation. Reapplying the existing network script restored missing
live rule100/fwmark0x200 and table100 pins without changing BIRD or IPsec.
Fresh paired recovery verification passed; see the current README and
`show-output/restored-mesh-verification/verification-summary.json`.

Design only, no IaC/live work. Objective: per-vHub Azure->DC winner/prepend threshold. BIRD/WireGuard model, not vendor behavior.

Region substitution locked: EU=westeurope and JP/CN=japaneast, Standard_B2ts_v2; US=northcentralus, Standard_B2als_v2. Germany/initial US candidates unavailable/restricted. User authorized geography-preserving substitution. All three live `az vm create --validate` gates passed 2026-10-14 in the new tagged lab RG; JP unzoned. Actual provisioning state is infrastructure-handoff.json; guest configuration requires a subsequent lease.

## Wiring / inventory

### Repeatable guest implementation (current state: activated)

Corrected activation completed 2026-10-14T18:00Z: **10/10 actual managed
command GETs Succeeded, exit0**. Final listener, router and JP probe files
were rewritten before service activation, with checksums and enabled/active
service assertions. All 18 BGP sessions were Established (12 mesh, four
EU/US hub, two JP VPN); this is a smoke snapshot, not scenario validation.
Original bootstrap backups are unchanged. Each guest retains protected
`/var/lib/threehub/activation-files.json`, `activation-files.tar`,
`activation-proof.json` and seekable `activation-routes.save` for subsequent
fault rollback. One ARM mutation; no restore or infrastructure change.
The activation lease is completed with no children. Decisive ignored evidence:
`deploy\.runtime-control\guest-activation-proof.json`.

`deploy\guest.py` generates protected managed Run Command ARM batches;
`deploy\guest.ps1 -Phase stage|activate|smoke|restore -LeaseFile <active lease>`
submits a real batch and waits under the absolute deadline. `-Outputs` retrieves
instanceViews; `-Names @('router-eu','router-jp')` narrows the read. Runtime
parameters and generated X25519 keys remain ignored; the existing ignored
`vpn.parameters.json` supplies JP's PSK. Never replay the blocked guest lease.
See recovery-handoff.md before any new guest deployment. The historical failed
activation/restore leases remain closed; do not replay them.

Four router files preserve protocol-name provenance, strict DC/spoke exports
and seven-prefix kernel forwarding. WireGuard uses three independent interfaces
per VM with unique local UDP socket ports; endpoint-scoped translation exposes
only UDP51820 on the approved physical endpoints. This translates **outer
transport ports only**, never inner private data. Mark0x200 selects underlay
table100 for WireGuard/IPsec; transport pins do not override CN's workload .4
in the main data FIB. Systemd orders underlay, WireGuard, JP IPsec, then BIRD.
The six workload listeners and JP probe routes are persistent.

Local checks: `python -m unittest discover -s deploy -p 'test_*.py' -q`;
shell checks use the existing Ubuntu WSL distribution. Actual guest stage
also runs its installed BIRD parser before any daemon activation. No
experiment, firewall, RI or prepend mutation is part of this implementation.

Nine VNets/ten VMs as card; routers .4/probes .10, SSH keys. EU/US router endpoint lives in transit, JP/CN in DC.

Five hub connections: EU transit+spoke, US transit+spoke, JP spoke. JP DC connects ONLY via S2S, not also as hub VNet connection. EU/US DCs must not attach directly to hubs (system routes would bypass NVA). Default association/Default label propagation everywhere, branch-to-branch enabled; no custom tables/default-table static VNetConnection next hops.

13 peering pairs /26 directed:
- six pairs among four DCs;
- DC-EU/transit-EU, DC-US/transit-US;
- transit-EU/transit-US;
- transit-EU/DC-JP, transit-EU/DC-CN, transit-US/DC-JP, transit-US/DC-CN.
Allow access and forwarded traffic both ways; gateway transit/remote gateways off. Extra endpoint peerings enable private overlay; JP/CN pair already exists. No DC/spoke peering.

PIPs bootstrap only, no public management; JP UDP500/4500 gateway-scoped. Private WireGuard UDP51820 endpoint /32s only. Run Command. Tags lab=true/created_by=copilot-lab/run ID/owner; record exact RG ID. Runtime PSKs/private keys ignored/redacted.

## Overlay / anti-bypass
Six WireGuard /30s 172.31.0.0,.4,.8,.12,.16,.20: EU-US,EU-JP,EU-CN,US-JP,US-CN,JP-CN. First endpoint+1/other+2. MTU1380, verify MSS. AllowedIPs remote DC/three spokes; separate interfaces, automatic routes off, BIRD selects.

Fullmesh eBGP, ASNs65011/12/13/14, hold180/keepalive60 both ends. Pin transport /32s via physical NIC/local Azure gateway; discover interface. No overlay-learned control routes.

EU/US workload UDRs other DCs/three spokes -> own transit .4. JP same-subnet guest routes -> JP .4 plus applicable UDRs; CN probe binds .4/kernel FIB. Never self-route endpoint /32.

FIB own DC connected/via Azure gateway; remote DCs WireGuard. Exact UDR/FIB overrides peering bypass. Linux/NIC forwarding, rp_filter loose/off; no private NAT, Internet-only bootstrap SNAT.

EU/US direct-learned spokes via physical Azure gateway/hub fabric, NOT hub BGP peer packet next hop. Overlay spokes WireGuard; JP direct spokes XFRM. Pin underlay; permit TCP179/private tests.

## BGP tables / provenance / loop filters
Separate Azure-direct, overlay and forwarding tables or explicit equivalent provenance. Never import/export all.
- Overlay DC export own DC /24 only; import exact peer-owned DC /24. Fullmesh needs no overlay transit re-export.
- Overlay Azure export only three spoke /24s learned DIRECTLY from this ingress; preserve path, tag ingress community65011:1 EU,65012:1 US,65013:1 JP. Reject overlay-learned spokes on overlay export.
- Export to Azure exactly all four DC /24s (own plus overlay-origin routes), preserve origin paths. Reject all DC imports from Azure. Never export spokes/transit/hub/tunnel/default/control prefixes back to Azure.
- Kernel export resolved forwarding routes only, never full Azure RIB/peer prefixes. Export-none is insufficient for this forwarding lab.
- Origin-AS loop check remains on; no allowas-in. Check concrete peer export sets, not merely Established.

Baseline spoke localpref: destination-region ingress300/others100, including direct remote-spoke imports. Closest is regional policy, not latency; forward prepend control equalizes localpref first.

EU/US genuine peered-VNet **HubBgpConnection**: BOTH dynamic hub router IPs, local NIC .4, ASN65515, identical exports. Not integrated vendor SD-WAN **VPN_S2S_Gateway**; results don't generalize its semantics. JP TWO VPN tunnels, local169.254.21.1 for BOTH BGP sessions/Azure.2/.6 /32s; validate live/provider fields, minimum-scale IKEv2/XFRM, no private NAT/hard-coded PSK.

## Priority experiment: per-hub return route thresholds
`deploy\vpn_sdwan_boundary.py` runs the separately leased comparison in exact
order: all-zero baseline, Japan +4/+8/restore0, Europe +4/+8/restore0.
It uses **direct action** VM Run Command with protected `--scripts @file`
inputs, not new managed-command resource names (the JP managed-command quota
is already full). Each configuration invocation is counted before submission.
Atomic candidates inherit the original UID/GID/mode **before** replacement;
restore also verifies the original hash and modification timestamp. The real
`birdc configure` reply must contain `Reconfigured`; parser success or CLI
exit0 alone is insufficient. Both Azure exports and 18 BGP/two JP IKE sessions
are checked against the original proof. Every state collects full live
all-hub HRP/routing-state/RI properties and paired connection winners at least
120 seconds apart. default-table queries are no longer part of the decisive collector because
they previously stalled; empty optional output is visibility metadata only.
Evidence is `show-output\vpn-sdwan-aspath-boundaries\sweep-verdict.json`.
An EU first observed switch at +4 brackets the minimum within1–4, not exactly4;
an observed switch only at +8 needs refinement within5–8. Unexposed losing
Azure candidates and data-plane success are never inferred.

`deploy\aspath_sweep.py` implements the separately leased ASPath/JP-only
control-plane sweep. `effective_routes.py` supplies actual `/subscriptions/...`
ARM IDs and waits for completed connection-effective results; both B0 collectors
now capture connections twice. On 2026-10-14, counts **0–3** and restore0 each
produced stable twelve-winner snapshots ≥120 seconds apart. **No winner switched
through3**; count4 was budget-truncated, not measured. Five routing mutations,
exact JP file-hash restore, unchanged four-router hashes, 18 Established BGP
sessions and both JP IKE SAs were verified. ASPath remains the named baseline;
no RI/IPsec/WireGuard/local-pref change or forwarding claim. Evidence:
`show-output\unsecured-aspath-jp\sweep-verdict.json` (**INCONCLUSIVE**, partial).

HRP ExpressRoute/VPN/ASPath; no ER resources. LPM/static first; ER/VPN locality before length, ASPath length before locality; interhub adds65520 twice. Documented ER/VPN race when local path >=2 longer: repeat tie/threshold captures; locality not absolute. Measure peered-NVA/VPN ties and RI changes.

Unsecured baseline each HRP: capture four DC routes at EVERY hub, candidate BGP/source/path/next-hop, chosen effective route. Then for selected ingress EU,US,JP, add additional copies of that ingress ASN to ALL four outbound DC advertisements. Hold other ingresses at0. Sequence0,1,2,4,8, quiesce after each change; capture all three hubs every step. Where winner changes, test intervening integer counts to find smallest switch threshold. Distinguish prefix-origin AS length: local versus remote DC advertisements already differ. Record thresholds per DC prefix AND observer hub; no universal threshold assumed.

Each configuration change separately approved Tank subcase; Niobe full4x3 route matrix is one lease, not whole sweep in30min. Record count/HRP/RI/correlation; source BIRD exports plus observer received routes expose candidates, effective routes winners. Missing competitor visibility=INCONCLUSIVE. Repeat transient/tie boundaries.

After baseline, one-ingress sweeps, restore0 and verify. Under all-three-hub RI, repeat each HRP baseline and adjacent decisive thresholds; if changed, bounded0..8 search under fresh leases. No switch through8 means bounded no-switch, not infinite threshold. Full exhaustive combinations of simultaneous prepends are out of scope.

Forward control separately manipulates ONE ingress's exported direct-learned Azure-spoke path (+8 local-AS copies, equal local preference), NOT DC export; show DC->Azure effects independently. Return control manipulates outbound DC exports only. Secondary matrix TCP initiated DC->spoke and spoke->DC plus ICMP; capture source/router ingress/egress/XFRM/workload inner five-tuple/sequence/timestamps. Record asymmetry explicitly; ping/traceroute success doesn't prove symmetry. No throughput.

Every scenario all-hub effective routes plus BIRD/FIB/NIC/VPN/capture. RI needs next-hop and correlated firewall flow evidence, not routes alone. Serialize Run Command per VM; full captures not truncated stdout. Two stable snapshots>=2min apart. Report data-plane failure alongside control-plane findings.

## Leases / RI sequencing / cleanup
Deployment<=60min/150calls/6 ARM submissions incl RG: suggested RG; base; peers/connections; live VPN binding. Guest config separate counted Tank lease.

Commands<=1200s; managed async<=45min/120s polls/progress; failure/ceiling stops. Stop80% ANY budget, checkpoint15min/25calls; STOP/expiry terminate children/no orphan handoff. Restore<=15min or BLOCKED/new recovery owner.

RI NEW lease: one ARM batch for shared Standard policy and three AZFW_Hub Standard firewalls, then three counted sequential RI updates EU,US,JP after firewalls Succeeded. **Official direct-NVA BGP unsupported for secured hub WITHOUT RI.** Firewall-only state is bounded conversion interruption, NOT “BGP must stay healthy” gate from old VPN-only skill. Full matrix only all three RI converged. No Basic or InternetTraffic RI. Policy scoped private/control prefixes, TCP179/ICMP/test TCP.

Save tables/exports; rollback removes firewall too for unsecured BGP. >15min rollback BLOCKED/new owner; mixed-RI transition only.

Niobe<=30min/75calls/0 config mutations/matrix, verdict<=5min; Tank restore/Niobe proof before next. New-run evidence only. Standing cleanup after saved sanitized evidence; exact created RG ID/run/owner tags, separate bounded lease/firewalls before policy/verify absence.
