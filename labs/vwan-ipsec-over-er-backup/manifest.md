# vwan-ipsec-over-er-backup - locked manifest

**Owner:** Morpheus
**Status:** **DEPLOYED / DESIGN BLOCKER RECORDED**
**Locked:** 2026-09-28
**Deployment:** authorized and completed through provider connectivity and four healthy IPsec SAs. D2 overlay BGP is blocked by the effective Azure BGP addressing model described below.

> **Megaport location delta:** Live account validation selected **Equinix Amsterdam AM1**, the nearest enabled practical PoP after Stockholm and closer candidate markets rejected a 1000-Mbps MCR. Azure ExpressRoute still terminates on the Stockholm primary and secondary MSEE paths; Azure remains in Sweden Central and GCP remains in `europe-north2`. The Amsterdam-to-Stockholm provider segment adds roughly 1,100 km great-circle distance; measured provider latency was not claimed.

## 0. Approval and gate record

Jose explicitly waived the normal pre-deployment approval gate and authorized deployment as soon as the implementation is ready.

| Record | Value |
|---|---|
| Approval timestamp | `2026-09-28T11:05:31.452+02:00` |
| Approved scope | This manifest: real ER, vWAN VPN-over-ER private tunnel, Internet backup, one new GCP project, and scenarios S1-S4 |
| Cost acknowledgement | Provider/monthly charges accepted for the authorized run; Tank still records the live Azure, GCP, and Megaport estimates before apply |
| Remaining gates | No architecture approval gate. Runtime creation/billing permissions and provider-generated keys are Wave-0 dependencies; cleanup still requires explicit approval |

## 1. Locked Stage-1 card

**Mechanism:** one GCP Linux CPE reaches one Azure vWAN VPN gateway through private IPsec carried over GCP Partner Interconnect -> Amsterdam Megaport MCR -> Stockholm ExpressRoute, plus public IPsec over the GCP Internet path.

### Locked selections

| Item | Selection |
|---|---|
| Azure region | `swedencentral` |
| Azure vWAN | Standard; one hub `10.240.0.0/24` |
| Azure workload | VNet `10.241.0.0/24`; Ubuntu 22.04 `Standard_B2ts_v2` |
| ExpressRoute | Provider-based Megaport, Stockholm, 50 Mbps, Standard, MeteredData |
| GCP project | New isolated project at deploy time: `gcp-vwan-eripsec-<run-id>` |
| GCP region/VM | `europe-north2`; non-Spot `e2-small`, fallback `e2-medium` |
| GCP network | Subnet `10.250.0.0/24`; Cloud Router ASN `16550` |
| CPE software | Ubuntu, StrongSwan, FRR, tcpdump and low-rate probes |
| Megaport | Equinix Amsterdam AM1 MCR; 1 GCP Partner Interconnect VXC; 2 Azure ER VXCs to Stockholm, one per primary/secondary MSEE path |
| Internet backup | Same GCP CPE, reserved public IPv4; no Megaport Internet product |

Azure-managed vWAN BGP uses ASN `65515`. Trinity assigns the CPE-side VPN ASN and valid, non-overlapping per-tunnel BGP endpoint ranges during detailed design; Tank records gateway-assigned private/public endpoints after provisioning. Provider service/pairing keys and live gateway provisioning are expected deployment dependencies, not blockers.

### Designs studied

| Design | Status hypothesis | Deciding evidence |
|---|---|---|
| D1 - one ordinary BGP adjacency moved between underlays | Pending Trinity recipe: one normal CPE loopback and one Azure default vWAN neighbor keep the same tuple while only the neighbor `/32` switches between ER/private and Internet/public XFRM paths. No custom APIPA is involved. | FRR state, `/32` route before/after evidence, per-XFRM packet capture and route withdrawal/re-establishment during both moves |
| D2 - separate BGP adjacencies with unique endpoints | Recommended candidate: independent health, withdrawal and preference. | Both peers Established, unique tuples, preferred ER path and bounded single-fault convergence |
| D3 - ER/BGP more-specifics plus Internet static covering aggregate | Deterministic but health-blind candidate: longest prefix selects ER; a stale static backup can blackhole. | Full route chain, normal failover, restore and compound-fault evidence |

### Scenarios

1. **S1 baseline:** PASS when Partner Interconnect, MCR, both ER MSEE paths, both IPsec tunnels and probes are healthy with evidence at every layer. FAIL if either ER provider path is missing/degraded or the tunnels cannot be independently identified.
2. **S2 single adjacency movement:** Execute only after Trinity supplies the corrected recipe. PASS when the unchanged ordinary BGP tuple establishes after each reviewed `/32` move and preserves or relearns the expected routes. FAIL when healthy SAs, correct `/32` routing and visible CPE SYNs still do not produce the required session. D2 APIPA observations are out of scope.
3. **S3 separate peers:** PASS when both unique peers establish, ER is preferred, and either tunnel withdrawal removes only its routes and converges through the survivor within the measured target. FAIL on endpoint collision, unintended ECMP/asymmetry, stale routes or sustained probe loss.
4. **S4 prefix hierarchy:** PASS when ER more-specifics win, their withdrawal moves covered probes to the Internet aggregate, and restore returns them to ER. Also run "Internet down first, then ER/BGP withdrawal": either automation withdraws the aggregate or evidence explicitly demonstrates the predicted blackhole. FAIL if normal routing is non-deterministic or contradicts longest-prefix selection.

## 2. Stage-2 topology and resources

```text
Azure workload 10.241.0.0/24
        |
vHub 10.240.0.0/24
  | ER gateway -> real ER circuit -> Azure VXC primary --\
  |                              -> Azure VXC secondary --- Amsterdam AM1 MCR
  |                                                        |
  |                                               GCP Partner VXC
  |                                                        |
  |                                      Cloud Router ASN 16550
  |                                                        |
  |                                         GCP 10.250.0.0/24
  |                                                        |
  +-- vWAN VPN gateway private endpoints <== IPsec/BGP =====+ Linux CPE
      vWAN VPN gateway public endpoints  <== IPsec/BGP/static over Internet
```

### Azure resources

- One resource group named `rg-vwan-ipsec-over-er-<run-id>`, tagged `lab=true`, `created_by=copilot-lab`, `lab_name=vwan-ipsec-over-er-backup`, `run_id=<run-id>`, `ephemeral=true`.
- Standard Virtual WAN and one Sweden Central virtual hub `10.240.0.0/24`.
- Minimum practical vWAN ExpressRoute gateway and site-to-site VPN gateway scale units supported at apply time.
- One 50-Mbps Standard/Metered ExpressRoute circuit with provider Megaport and Stockholm peering location; one vHub ER connection.
- One VPN site representation for the GCP CPE, with distinct private-underlay and public-underlay link definitions as required by the final API model.
- Workload VNet `10.241.0.0/24`, one workload subnet, vHub connection, NSG, NIC and Ubuntu 22.04 `Standard_B2ts_v2` probe VM with Standard SSD.
- No Azure Firewall, secured hub, ER Direct, Global Reach, public Azure workload IP or production throughput target.

### GCP resources

- Create, billing-link and later delete a new isolated project; never reuse the stale configured project.
- Enable at least `compute.googleapis.com`, `serviceusage.googleapis.com` and `cloudresourcemanager.googleapis.com`, plus any Partner Interconnect API dependency discovered by Tank.
- One custom-mode VPC with regional subnet `10.250.0.0/24` in `europe-north2`.
- One Cloud Router ASN `16550`; one Partner Interconnect VLAN attachment and generated pairing key.
- One reserved external IPv4; one Ubuntu `e2-small` CPE with IP forwarding, `e2-medium` only if the live zone catalog/quota blocks `e2-small`.
- StrongSwan route-based IPsec plus FRR. Use separate tunnel interfaces and unique BGP endpoints for D2; D1 deliberately attempts the shared-adjacency model. Firewall rules allow only required IKE/IPsec, BGP-over-tunnel, probes and controlled management.

### Megaport resources

- One Equinix Amsterdam AM1 MCR, 1000 Mbps and one-month term, selected by live enabled-market validation.
- Two distinct Azure VXCs referencing the same ER service key, explicitly selecting primary and secondary MSEE paths.
- One GCP Partner Interconnect VXC referencing the generated GCP pairing key.
- Do not manually create Azure private peering when Megaport owns the VXC/private-peering workflow.
- No Megaport Internet connection.

## 3. Deployment waves and ownership

1. **Wave 0 - Tank prerequisites:** create/link GCP project; verify `e2-small` zone/quota, external IP, Cloud Router and VLAN attachment quotas; record live cost estimates; stop only on failed project/billing permission, unavailable Partner Interconnect, or unsupported gateway/API shape.
2. **Wave 1 - parallel long poles:** create Azure RG/vWAN/vHub/gateways/ER circuit and GCP VPC/Cloud Router/CPE foundations.
3. **Wave 2 - provider keys:** create GCP VLAN attachment to obtain pairing key; use ER service key and pairing key to order the MCR and three VXCs.
4. **Wave 3 - connect:** wait for ER provider state `Provisioned`; create vHub ER connection; obtain vWAN VPN private/public endpoints; configure site links.
5. **Wave 4 - CPE:** install/configure StrongSwan and FRR without committing PSKs or generated keys; configure private and public tunnels.
6. **Wave 5 - baseline:** establish both MSEE BGP paths, Partner Interconnect, both IPsec tunnels and the selected BGP design; run S1 before any fault.
7. **Wave 6 - experiments:** run S2, restore; run S3, restore; run S4 including compound fault, restore; leave all paths healthy.

**Trinity:** exact tunnel/link model, CPE ASN, APIPA/tunnel endpoints, route-policy attributes, prefix hierarchy, GCP firewall rules and failure injections.
**Tank:** one dependency graph across Azure/GCP/Megaport, secret-safe deploy/resume/cleanup, generated-key handoffs, dual Azure VXC enforcement and live cost capture.
**Niobe:** assertions, timed probes, route/session collection, packet captures, sanitized raw output and scenario verdicts.
**Oracle:** editable diagrams for topology, D1/D2 control plane, D3 data plane/failure path and cleanup dependencies.

## 4. Evidence contract

Niobe collects before, during and after each fault:

- Azure resource/provisioning state; vHub effective routes; ER gateway learned/advertised routes when exposed; VPN connection/site route state; probe NIC effective routes.
- ER circuit primary **and** secondary route tables/summaries in JSON; provider/BGP state for both.
- Megaport MCR/VXC inventory and each VXC BGP connection. MCR looking-glass output is supplemental, not sole evidence.
- GCP Cloud Router status, advertised/learned routes, VLAN attachment state, VM routes/rules and forwarding.
- CPE `ip xfrm`, tunnel/link state, `swanctl`, FRR neighbors/RIB, `ip route`, tcpdump around BGP/IKE/ESP and timestamped probes.
- Sanitization removes service keys, pairing keys where sensitive, API credentials, PSKs, tokens and project/billing identifiers not needed for publication.

The authoritative result for D1 is observed control-plane behavior, not an assumed Azure limitation. S2 must identify whether failure occurs at API validation, IKE/link binding, BGP endpoint reachability, duplicate neighbor configuration or route persistence.

## 5. Cost and time envelope

| Plane | Main billable items | Planning treatment |
|---|---|---|
| Azure | vHub, VPN GW scale units, ER GW scale units, 50-Mbps Standard/Metered circuit, B2ts_v2 VM/disk, data | Tank records live retail estimate; gateways dominate hourly Azure cost |
| GCP | e2-small, persistent disk, public IPv4, Partner VLAN attachment and egress | e2-medium is fallback only; project creation is free |
| Megaport | Amsterdam MCR monthly term, 2 Azure VXCs to Stockholm, 1 GCP VXC | Live rack-rate quote captured before ordering: EUR 991.80/month; promotional discount is not treated as guaranteed |

The run is expected to exceed the normal low-cost lab envelope because it uses two managed vWAN gateways, a real ER circuit, Partner Interconnect and three Megaport VXCs. Jose's recorded approval waives the pre-deployment cost gate for this scope; it does not waive cost reporting.

**Deployment/convergence:** approximately 60-120 minutes, with vWAN gateways and provider provisioning as long poles.
**Validation:** 2-4 hours for baseline, three designs, faults, restores and evidence.
**Cleanup:** commonly 30-60+ minutes because managed gateways and provider dependencies delete slowly.

## 6. Risks and stop conditions

- New GCP project creation or billing-link permission fails.
- `e2-small` and fallback `e2-medium` are both unavailable in usable `europe-north2` zones.
- Partner Interconnect/VLAN attachment cannot be created or paired in the selected Stockholm service.
- vWAN does not expose reachable private VPN endpoints through the ER-learned path/API shape required by the experiment.
- Either ER primary or secondary provider path cannot be provisioned; final validation never proceeds in degraded single-path mode.
- Address recheck after GCP project creation discovers overlap with GCP or externally advertised ER routes.

Live Azure gateway allocation, ER/GCP generated keys and provider convergence are expected dependencies. Tank retries/resumes according to provider state; they are not architecture blockers unless they resolve to one of the stop conditions above.

## 7. Cleanup order

Cleanup requires a separate explicit approval. Preview all deletions first.

1. Restore all fault injections and capture final healthy evidence.
2. Remove vHub ER/VPN connections and Azure private peering linkage as required.
3. Delete both Azure VXCs and the GCP VXC; then delete the MCR.
4. Delete the Azure resource group after provider links are released.
5. Delete the isolated GCP project after confirming no shared resources or billing dependencies were introduced.

Do not delete the Azure resource group first: provider linkage and gateway deletion can block Megaport cleanup.
