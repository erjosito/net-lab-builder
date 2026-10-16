# Secured Virtual WAN: backbone-first hub and NVA policy

**Measured 2026-10-16. Control-plane experiment PASS, exact restore PASS;
forwarding is explicitly partial.** ASPath HRP and nonlocal export prepends
alone are not enough: NVAs must accept the Azure alternatives and select them.
A temporary workload UDR additionally made Japan workload / EU spoke TCP and
ICMP pass in both directions. DC-to-DC failures prevent calling this a
universally working backbone-first design.

## Topology and observation points

![Three secured hubs and private DC mesh](../../diagrams/topology.svg)

The deployed hubs are West Europe, North Central US and Japan East.
EU/US ASN 65011/65012 BIRD routers connect from transit VNets using ordinary
peered-VNet `HubBgpConnection` sessions, not integrated vendor SD-WAN gateways.
Japan ASN 65013 uses two active-active IPsec/BGP tunnels. The logical China
site, ASN 65014, is hosted in Japan East and has no direct hub attachment.
Six WireGuard links model the private inter-DC network. Twelve unique BGP
adjacencies appear as eighteen BIRD endpoint entries.

| Site | DC prefix / probe | Router | Azure spoke / probe |
| --- | --- | --- | --- |
| EU | `10.110.0.0/24`, `.10` | `10.210.0.4` | `10.10.0.0/24`, `.10` |
| US | `10.120.0.0/24`, `.10` | `10.220.0.4` | `10.20.0.0/24`, `.10` |
| Japan | `10.130.0.0/24`, `.10` | `10.130.0.4` | `10.30.0.0/24`, `.10` |
| China logical | `10.140.0.0/24`, `.4` | `10.140.0.4` | None |

All three hubs have Standard Azure Firewall and PrivateTraffic-only routing
intent. Hub ASN is 65515; interhub advertisements add `65520-65520`.
There is no ExpressRoute circuit. ExpressRoute below names an HRP setting.
No throughput or private-network speed advantage was measured.

## Three matched states

1. [User baseline](../hrp-design-live-baseline-20261016/baseline-verdict.json):
   EU/US HRP ASPath, Japan ExpressRoute. EU/US each add three own-AS prepends
   except for their own DC. Japan exports have no additional prepend. Azure
   import filters accept only spokes, not DCs. Corresponding regional spoke
   ingress gets local-pref 300, other imports 100.
2. [NVA policy only](nva-policy-only/scenario-result.json): all three HRPs
   ASPath. Azure imports accept foreign DCs, never their own DC, and all three
   spokes; local-pref is 400. Japan also adds three own-AS prepends for foreign
   DC exports. Existing EU/US prepend policies are preserved.
3. [Same NVA policy plus Japan workload UDR](nva-policy-and-jp-udr/scenario-result.json):
   five routes, for EU/US DCs and the three spokes, point to `10.130.0.4`.
   The UDR excludes `10.140.0.0/24`: China `.4` is also a WireGuard outer
   endpoint, and a shared Japan-subnet route for it would loop outer traffic.
   This variant changes no BIRD, IPsec or WireGuard policy relative to state 2.

Each state's folder contains full `router-*.conf`, BIRD routes and both Azure
peer exports, decoded kernel routes/lookups, all three firewall effective
tables in two snapshots at least 120 seconds apart, and traffic results.
The baseline puts those surfaces in `sources`, `routes`, `firewalls`, `traffic`.
The two experimental states put them alongside `scenario-result.json`.
Raw API/Run Command envelopes retain command and timestamp provenance.
Subscription identifiers, local paths and owner tags are redacted in these
publication copies; the compressed guest payloads contain only synthetic BIRD
and routing evidence, not VPN/WireGuard secrets.

## Firewall winners and NVA decisions

| Observation | User baseline | NVA policy only | Policy plus UDR |
| --- | --- | --- | --- |
| EU firewall, Japan DC | Remote Hub, `65520-65520-65013` | Same | Same |
| US firewall, Japan DC | Remote Hub, `65520-65520-65013` | Same | Same |
| Japan firewall, EU DC | Local VPN, `65013-65011` | Remote Hub, `65520-65520-65011` | Same as policy only |
| EU NVA, Japan DC | `mesh_jp`, `65013`, LP 100 | `azure_0`, `65515-65520-65520-65013`, LP 400 | Same |
| US NVA, Japan DC | `mesh_jp`, `65013`, LP 100 | `azure_1`, `65515-65520-65520-65013`, LP 400 | Same |
| Japan NVA, EU DC | `mesh_eu`, `65011`, LP 100 | `azure_1`, `65515-65520-65520-65011`, LP 400 | Same |
| Japan NVA, EU spoke | `mesh_eu`, `65011-65515`, LP 300 | `azure_1`, `65515-65520-65520`, LP 400 | Same |

Japan's selected Azure routes carry BIRD's **`!`** marker, not the normal
`*`. It indicates a failure pushing the route into the kernel. Kernel
snapshots nevertheless contain the XFRM routes; BIRD logs reported strange
next hops and `File exists`. The underlying issue was not remediated in this
experiment. Do not equate BIRD best-path selection with an unconditionally
healthy FIB or use a successful router probe as a substitute for its workload.

See [`selected-routes.json`](nva-policy-and-jp-udr/selected-routes.json), full
[`Japan BIRD routes`](nva-policy-and-jp-udr/router-jp-bird-routes.txt), and
[`Japan decoded kernel and export evidence`](nva-policy-and-jp-udr/nva-policy-and-jp-udr-routes-jp-decoded.json).

## Policy mechanisms and limitations

The [exact reversible transformation](../../deploy/design_backbone.py)
preserves next-hop resolution and community handling, expands only the Azure
import allowlist, and sets `bgp_local_pref = 400`. The original
`azure_export` guard still permits DC exports only from `own_dc` or `mesh_*`.
Azure-learned DCs cannot be re-exported into the hub.

That guard is essential, but also affects interpretation: once the best route
becomes Azure-learned, its former local foreign-DC advertisement is withdrawn.
These results measure the combined import, local-pref, prepend and export
policy. They do not isolate a prepend-only threshold or prove both original
advertisements remain present after selection changes. Mesh alternatives are
visible in BIRD; no failure/failback test was performed.

For example, the EU export filter keeps its allowlist and uses:

```bird
if net != 10.110.0.0/24 then {
  bgp_path.prepend(65011);
  bgp_path.prepend(65011);
  bgp_path.prepend(65011);
}
accept;
```

Three explicit prepends plus the automatic eBGP local ASN make four copies
on the wire. For Japan's prefix, EU initially advertises a five-ASN path
versus the three-ASN remote VPN path. BIRD's `show route export` displays
the explicit attribute before automatic local-AS insertion.

## Directional forwarding, not an all-pairs success

Each cell below is **TCP/ICMP**. TCP means HTTP status 200 from the synthetic
listener on port 5201, not merely a successful connection to a router.

| Source to destination | Baseline | NVA policy only | Policy plus UDR |
| --- | --- | --- | --- |
| EU spoke to Japan workload | FAIL/FAIL | FAIL/FAIL | PASS/PASS |
| EU spoke to Japan router | FAIL/PASS | PASS/PASS | PASS/PASS |
| EU spoke to China router/workload | FAIL/PASS | PASS/PASS | PASS/PASS |
| EU DC to Japan workload | PASS/PASS | PASS/PASS | FAIL/FAIL |
| EU DC to Japan router | PASS/PASS | FAIL/FAIL | FAIL/FAIL |
| Japan workload to EU DC | PASS/PASS | PASS/PASS | FAIL/PASS |
| Japan workload to EU spoke | FAIL/FAIL | FAIL/FAIL | PASS/PASS |

The successful Japan workload / EU spoke pair demonstrates the requested
on-premises-to-Azure direction under the tested policy. It does not establish
universal DC-to-DC forwarding, physical-path packet traces, convergence time,
throughput, failover behavior or production supportability. In particular,
the remaining DC-to-DC failures and kernel warning need further investigation
before using this configuration as a general design.

## HRP caveat: locality is not unconditional

[Microsoft's HRP algorithm](https://learn.microsoft.com/en-us/azure/virtual-wan/about-virtual-hub-routing-preference)
generally puts local-hub connections before remote-hub connections under
ExpressRoute/VPN HRP; ASPath compares path length first. It also documents a
race condition: with ExpressRoute/VPN HRP, a remote path can win when the
local AS path is at least two ASNs longer. Remote ExpressRoute routes have a
separate documented exception.

The fresh [ExpressRoute firewall snapshots](../hrp-design-matrix-20261016/ExpressRoute/ExpressRoute-winners2.json)
still selected the remote Japan route at EU/US with the current three-extra
prepends. The five-versus-three lengths meet the documented race-condition
condition; this observation does not establish that the race was the cause.
The parent matrix stopped on a capture acceptance problem and is not a
complete HRP comparison. The VPN case was not run. Do not claim that this
fresh experiment replicated an unconditional longer-local-route win, or
derive a minimum prepend threshold from it. The later independent verification
establishes restored current state without rewriting the failed run's verdict.

## Commands closest to the claim

With routing intent, query the owning **firewall**, not just the hub table
that points to it. The resource discriminator is **`AzureFirewalls` plural**:

```powershell
az network vhub get-effective-routes -n $hub -g $rg `
  --resource-type 'AzureFirewalls' `
  --resource-id $(az network vhub show -g $rg -n $hub --query 'azureFirewall.id' -o tsv) `
  --query 'value[].{Prefix:addressPrefixes[0], ASPath:asPath, NextHopType:nextHopType}' -o table
```

Without routing intent, use the relevant VNet connection:

```powershell
$connectionId = az network vhub connection show -g $rg --vhub-name $hub `
  -n $connection --query id -o tsv
az network vhub get-effective-routes -g $rg -n $hub `
  --resource-type HubVirtualNetworkConnection --resource-id $connectionId -o json
```

On each NVA, capture both selection and forwarding:

```bash
sudo cat /etc/bird/bird.conf
sudo birdc show route table lab4 all
sudo birdc show route export azure_0 all
sudo birdc show route export azure_1 all
ip -j route show table main
ip -j rule show
ip route get 10.130.0.10
```

## Restore and cold-start reliability

[`backbone-verdict.json`](backbone-verdict.json) records both states and exact
restore. [Independent verification](../backbone-final-verification-20261016/verification-verdict.json)
confirmed original file bytes and nanosecond metadata, eighteen Established
BIRD endpoint sessions, both Japan IKE SAs, original mixed HRPs and stable
firewall winners. The temporary Japan subnet association was removed and only
the newly created route table deleted.

All ten VMs were initially deallocated and were returned to those exact states
after verification; see [power restore](../backbone-power-restoration-20261016/power-restoration-verdict.json).
No pre-existing resource was deleted. The hub firewalls and gateway are still
deployed and billable.

The cold-start recovery also disabled the competing legacy
`strongswan-starter.service`, leaving the intended `strongswan.service`
charon-systemd/swanctl daemon. Both had bound IKE ports. No PSKs, BIRD source
or swanctl configuration was changed by that recovery. Provisioning now
disables the legacy daemon before activating the intended one.
