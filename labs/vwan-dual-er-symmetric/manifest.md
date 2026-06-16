# vwan-dual-er-symmetric: Phase 3.1 Manifest

**Owner:** Morpheus
**Status:** Paperwork-only design, stopped at approval gate #12 #1
**Lab folder:** `labs/vwan-dual-er-symmetric/`
**Drafted:** 2026-06-15
**Do not deploy from this document without explicit gate approval.**

## 0. Gate discipline

This manifest is the Phase 3.1 design artifact only. It creates no IaC files, runs no `az network … create/update/delete` commands, and makes no Megaport API write calls. Tank must not deploy until Jose approves gate #12 #1 after reviewing this manifest.

Subscription and tenant hygiene are mandatory: scripts resolve the active subscription at runtime with `az account show --query id -o tsv`, or via a caller-supplied `--subscription` / `$env:AZURE_SUBSCRIPTION_ID` / `$env:ARM_SUBSCRIPTION_ID`. No subscription IDs or tenant IDs belong in this repo (routing rule #10). Secrets resolve from Azure Key Vault `platform-secrets-1138` at deploy time (routing rule #11): see §7.

## 1. Executive summary

This lab demonstrates **traffic symmetry across a dual-region Virtual WAN with two ExpressRoute circuits and stateful Azure Firewalls in each hub.** The reader will learn how to design a vWAN secured-hub topology so that: for every flow between an Azure spoke and a simulated on-prem location: the **forward and return packets traverse the same hub firewall**. The headline failure mode this lab surfaces is the **stateful-drop-on-asymmetric-return** problem that classical dual-region ER + redundant firewall designs hit when prefixes leak between regions.

In scope: single Virtual WAN, two secured hubs (one per region), two ExpressRoute circuits via Megaport (one per region, no Global Reach, no ER bow-tie), two Megaport MCRs, two GCP VPCs as the on-prem simulation, four spoke VNets (two per region), four Linux test VMs, routing-intent set to `private` per hub, and one deliberate symmetry-break scenario to capture the dropped-flow failure mode.

Out of scope: internet egress through the firewall (`ri_policy=internet`), VPN branches, SD-WAN NVAs, redundant NVAs, hub-to-hub Global Reach, ER FastPath, ER Direct, MACsec, Private Endpoints, Defender for Cloud network alerts. Each becomes a candidate follow-up lab.

Audience: Azure networking architects evaluating vWAN secured-hub for hybrid connectivity in 2+ regions, particularly anyone who has been bitten by stateful firewalls dropping return traffic on the wrong instance.

## 2. Topology

### 2.1 Address-space plan (non-overlapping with lab #1)

Lab #1 (`expressroute-megaport-bgp`) used `10.31.0.0/16` and `10.100.0.0/16` for Azure, and `172.31.100.0/24` / `172.31.101.1/32` on the on-prem sim side. This lab deliberately uses `10.10.0.0/12` ranges so the two labs can theoretically be live in the same subscription without prefix collision.

| Element | CIDR | Notes |
|---|---|---|
| **Region A: Sweden Central** | | |
| vWAN hub 1 | `10.10.0.0/23` | Hub itself consumes one /23 (vWAN requirement, min /24, /23 recommended for ER + AzFW). |
| Spoke 1 VNet | `10.11.0.0/24` | `10.11.0.0/27` workload subnet; rest reserved. |
| Spoke 2 VNet | `10.12.0.0/24` | Same shape. |
| **Region B: North Europe** | | |
| vWAN hub 2 | `10.20.0.0/23` | |
| Spoke 3 VNet | `10.21.0.0/24` | |
| Spoke 4 VNet | `10.22.0.0/24` | |
| **On-prem simulation (GCP)** | | |
| GCP VPC A subnet | `10.50.1.0/24` | Co-located near Region A; advertised inbound only via MCR1. |
| GCP VPC B subnet | `10.50.2.0/24` | Co-located near Region B; advertised inbound only via MCR2. |
| **Reserved / not used** | `10.30.0.0/16`, `10.100.0.0/16`, `172.31.0.0/16` | Lab #1 ranges: explicitly avoided. |
| **Transit / link-locals** | `169.254.0.0/16` | Managed by Megaport for VXC BGP peering; no design action. |

GCP-on-prem advertised prefixes (`10.50.1.0/24`, `10.50.2.0/24`) do not overlap with any Azure prefix and do not overlap with the lab-#1 sim range `172.31.0.0/16`.

### 2.2 vWAN, hubs, ER, MCRs

```text
                  Single Virtual WAN (Standard)
                      hub-to-hub link auto
       ┌──────────────────────────┴──────────────────────────┐
       ▼                                                       ▼
  ┌────────────────────────┐                           ┌────────────────────────┐
  │  vWAN Hub 1 (Sweden)   │                           │  vWAN Hub 2 (NEurope)  │
  │  10.10.0.0/23          │                           │  10.20.0.0/23          │
  │  AzFW Std (in-hub)     │                           │  AzFW Std (in-hub)     │
  │  ASN 65515 (vWAN BGP)  │                           │  ASN 65515 (vWAN BGP)  │
  │  ER GW (hub-resident)  │                           │  ER GW (hub-resident)  │
  │  routing-intent=private│                           │  routing-intent=private│
  └────┬──────────┬────────┘                           └────┬──────────┬────────┘
       │          │                                          │          │
   Spoke1     Spoke2                                      Spoke3     Spoke4
   10.11/24   10.12/24                                    10.21/24   10.22/24
       │                                                              │
       │ Azure private peering (provider=Megaport, ER pricing zone 1) │
       ▼                                                              ▼
  ┌────────────────────────┐                           ┌────────────────────────┐
  │  ER Circuit 1: Stockholm│                          │ ER Circuit 2: Amsterdam│
  │  Standard, MeteredData │                           │  Standard, MeteredData │
  │  50 Mbps               │                           │  50 Mbps               │
  └────────────┬───────────┘                           └────────────┬───────────┘
               │                                                    │
        Megaport VXC (private peer)                          Megaport VXC
               │                                                    │
  ┌────────────▼───────────┐                           ┌────────────▼───────────┐
  │  MCR 1 (Stockholm or   │  ◄── NO bow-tie ──►       │  MCR 2 (Amsterdam or   │
  │  Megaport-picked PoP)  │  ◄── NO Global Reach ──►  │  Megaport-picked PoP)  │
  │  ASN 65001             │                           │  ASN 65002             │
  └────────────┬───────────┘                           └────────────┬───────────┘
               │                                                    │
       VXC → GCP Interconnect                              VXC → GCP Interconnect
               │                                                    │
  ┌────────────▼───────────┐                           ┌────────────▼───────────┐
  │  GCP VPC A             │  (NO inter-VPC peering)   │  GCP VPC B             │
  │  10.50.1.0/24          │                           │  10.50.2.0/24          │
  │  europe-west1 or w3    │                           │  europe-west4 (Nether) │
  │  Cloud Router ASN 16550│                           │  Cloud Router ASN 16550│
  └────────────────────────┘                           └────────────────────────┘
```

### 2.3 Routing-intent choice

**`ri_policy = private`** on both hubs (PrivateTrafficPolicy only; no InternetTrafficPolicy this lab).

Rationale:
- The lab's headline is firewall symmetry for **east-west and hybrid private** traffic. Internet egress symmetry is its own topic (NAT, public-IP affinity, asymmetric SNAT): deliberately deferred to a future lab.
- `private` forces all spoke↔spoke (within and across hubs) and spoke↔branch (ER) traffic through the in-hub AzFW. This is what makes the symmetry test meaningful: the firewall is in path.
- `both` would also wire internet, which adds two more variables (UDR on the spokes for default route, NAT IP per hub) without sharpening the symmetry lesson.

### 2.4 ExpressRoute bow-tie: **NO**

Defined by the reference script (`vwan_2xshub.azcli` lines 322-332): `er_bow_tie=yes` creates a second ER-GW connection so Hub2 is also attached to Circuit1 and Hub1 also attached to Circuit2.

**We deliberately set `er_bow_tie=no`** for the headline-symmetric design:
- With bow-tie ON, both hubs learn both circuits' on-prem prefixes (e.g., 10.50.1.0/24 appears via Circuit1 AND Circuit2). Azure best-path may install the route via either circuit, and return packets from a spoke can leave through either hub → asymmetric firewall traversal.
- With bow-tie OFF, only Hub1 has a connection to Circuit1; therefore Hub1 is the only Azure-side path for 10.50.1.0/24, and any spoke targeting 10.50.1.0/24 routes via Hub1's AzFW. Symmetry naturally holds.

The trade-off being declined: bow-tie is the standard pattern for ER **HA across regions** (if Region A's ER fails, Region A spokes can still reach on-prem via Region B's circuit). This lab does not test HA failover. Scenario S4 turns bow-tie ON deliberately to demonstrate the asymmetry it introduces.

### 2.5 ExpressRoute Global Reach: **NO**

Global Reach (`global_reach=yes` in reference script line 41 / function lines 2337-2342) connects two ER circuits' private-peering planes directly at the Microsoft edge, bypassing both Azure hubs entirely.

Declined because:
- Global Reach is for **circuit-to-circuit** on-prem-to-on-prem traffic: it would let GCP-VPC-A talk to GCP-VPC-B directly through MSEE, never touching either Azure firewall. Irrelevant to this lab.
- If we ever had GCP1 advertise both prefixes (badly designed import policy), Global Reach would also let Azure spokes reach 10.50.2.0/24 via Circuit1 → Global Reach → Circuit2 → GCP2, creating a third path that breaks firewall affinity.

Documented as a deliberate non-choice; cost of GR (~$70-100/month per circuit pair) is also avoided.

### 2.6 Hub-to-hub: implicit (cannot be disabled in vWAN)

vWAN automatically creates a hub-to-hub link inside the single vWAN: this is what carries cross-region spoke-to-spoke traffic (Spoke1 ↔ Spoke3). Routing-intent=private on both hubs ensures this path is **Spoke1 → Hub1-AzFW → hub-to-hub → Hub2-AzFW → Spoke3**, i.e. both regional firewalls are in path. Symmetric by construction because each direction enters its own region's spoke via the same firewall.

## 3. Traffic-symmetry mechanism (the headline)

The lab achieves symmetry through **per-region prefix affinity in both directions**, enforced by three independent levers stacked. If any one lever fails, the design degrades to a single-firewall-in-path (which is still symmetric, just less defensive); only if *all three* fail simultaneously can asymmetry emerge.

### 3.1 Azure → on-prem direction (egress symmetry)

**Mechanism:** each hub advertises only its own region's spoke prefixes into its co-located ER circuit. Implemented by the vWAN default-route-table behaviour:

- Each ER GW connection (`hub1ergw` → Circuit1, `hub2ergw` → Circuit2) is associated with and propagates from `defaultRouteTable` of its OWN hub only.
- Because `er_bow_tie=no`, there are exactly two ER-GW connections (not four). Hub1 has no connection object pointing to Circuit2, so Hub1's spoke prefixes (10.11/24, 10.12/24) cannot be advertised out Circuit2.
- Hub-to-hub propagation does carry Spoke3/Spoke4 prefixes into Hub1's default RT (and vice versa), but those are not re-advertised back out the OWN-hub ER GW because vWAN suppresses re-advertisement to the ER scope by default.

**Niobe's verification commands (Phase 6):**

```bash
# What Hub1's ER GW is advertising to Circuit1
az network express-route gateway connection show \
  --gateway-name hub1ergw -g <rg> \
  -n hub1ergw-stockholm --query 'enableInternetSecurity'
az network vnet-gateway list-advertised-routes \
  --resource-group <rg> --name hub1ergw --peer <mcr1_bgp_ip>
# Expected: 10.11.0.0/24 and 10.12.0.0/24 only; NOT 10.21.0.0/24, NOT 10.22.0.0/24

# Same for Hub2
az network vnet-gateway list-advertised-routes \
  --resource-group <rg> --name hub2ergw --peer <mcr2_bgp_ip>
# Expected: 10.21.0.0/24 and 10.22.0.0/24 only

# What Circuit1's route-table is exporting toward MCR1
az network express-route list-route-tables \
  -g <rg> --name <circuit1> --peering-name AzurePrivatePeering --path primary -o json
```

Lab #1 lesson learned: the `list-route-tables` CLI returned `Gateway does not have any Bgp sessions` despite the gateway being up: Niobe will fall back to `list-advertised-routes` on the gateway + the Megaport VXC's `bgpConnections` resource.

### 3.2 On-prem → Azure direction (ingress symmetry)

**Mechanism: separate GCP VPCs, one per Azure region, with no VPC peering between them.** Each GCP VPC has its own Cloud Router (ASN 16550) and its own Interconnect attachment to its respective MCR.

- GCP VPC A advertises only its own subnet 10.50.1.0/24 over its Interconnect → MCR1 → Circuit1 → Hub1.
- GCP VPC B advertises only 10.50.2.0/24 → MCR2 → Circuit2 → Hub2.
- Azure spokes that target 10.50.1.0/24 see exactly one path (via Hub1); targets to 10.50.2.0/24 see exactly one path (via Hub2). Asymmetry is structurally impossible.

This is the **simpler design choice** versus running a single GCP VPC and trying to constrain advertisements with route-policy / AS-path prepending on the GCP side. The reference script already separates GCP into `vpc1`/`vpc2` per region (script lines 134-150): we follow that pattern.

**MCR-side belt-and-braces (defence in depth):** even though structurally each MCR only sees its own GCP VPC's prefix, Tank/Trinity will configure the MCR's GCP-VXC import policy to **explicitly deny** prefixes outside the expected /24 (e.g., MCR1 GCP-VXC accepts only `10.50.1.0/24`, denies anything else). Catches future misconfigurations.

**Niobe's verification:**

```bash
# What MCR1 is learning from GCP VPC A
# (queried against Megaport VXC resource bgpConnections; CLI shape from lab #1 working pattern)
az rest --method get \
  --uri "https://api.megaport.com/v2/product/<mcr1_uid>" \
  --headers "Authorization: Bearer $token"
# Expected: 10.50.1.0/24 present, 10.50.2.0/24 absent.
```

### 3.3 Cross-region spoke ↔ spoke (Spoke1 ↔ Spoke3) symmetry

**Mechanism: routing-intent=private on both hubs.** This forces *all* private traffic transiting the hub through the AzFW, regardless of source/destination. Combined with the implicit single-vWAN hub-to-hub link:

- Spoke1 → Spoke3 forward path: `Spoke1 NIC → Hub1 AzFW → hub-to-hub link → Hub2 AzFW → Spoke3 NIC`
- Spoke3 → Spoke1 return path: `Spoke3 NIC → Hub2 AzFW → hub-to-hub link → Hub1 AzFW → Spoke1 NIC`

Both directions traverse the same two firewalls in opposite order. Symmetric.

**Three-firewall-hop is impossible** in this design because there is no third hub: and even if there were, vWAN does not chain hub firewalls; each hub fires its own firewall once for any flow that enters/exits it.

### 3.4 The failure mode the lab will demonstrate

If symmetry is broken (Scenario S4: enable `er_bow_tie=yes`), the following will happen and the lab will capture it:

1. Hub1 now learns 10.50.2.0/24 via two ER paths: directly via Circuit2 (bow-tie added connection) and indirectly via the hub-to-hub link from Hub2. Hub2 likewise learns 10.50.1.0/24 via two paths.
2. vWAN best-path selection may install the direct-circuit path on both hubs (shorter AS-path): Hub1 → Circuit2 → MCR2 → GCP-VPC-B.
3. Spoke1 sends a TCP SYN to 10.50.2.10 → exits Hub1-AzFW (forward path on Circuit2) → reaches GCP-VPC-B → SYN-ACK returns.
4. GCP-VPC-B's return path to 10.11.0.5 (Spoke1) uses its own Cloud Router → MCR2 → Circuit2 → Hub2 (because Circuit2 originates 10.11.0.0/24 via the bow-tied Hub2 connection now).
5. **SYN-ACK hits Hub2-AzFW, which has no prior state for this flow → DROP.** TCP handshake fails. `curl` times out.
6. Niobe captures: KQL on `AZFWNetworkRule` shows SYN egress on Hub1-AzFW and SYN-ACK drop on Hub2-AzFW for the same 5-tuple. Root cause is asymmetric routing.

## 4. Test scenarios

Each scenario lists input, expected output, exact verbatim CLI Niobe will run, and the artifact filename under `labs/vwan-dual-er-symmetric/show-output/`.

### S1: Symmetric flow, Spoke1 ↔ GCP-VPC-A (Region A only)

**Hypothesis:** All packets between Spoke1 (10.11.0.5) and GCP-VPC-A (10.50.1.10) traverse Hub1's AzFW only. Hub2's AzFW sees zero hits for this 5-tuple.

**Input:** `curl -sv --max-time 5 http://10.50.1.10/` from Spoke1 VM, 10 iterations.

**Verification commands (Niobe):**

```bash
# 1. Confirm route on Spoke1's NIC
az network nic show-effective-route-table -g <rg> -n nic-spoke1-vm -o json \
  > show-output/s1-01-spoke1-nic-routes.json
# Expect: 10.50.1.0/24 nextHop=VirtualNetworkGateway (vWAN hub)

# 2. Confirm Hub1 ER GW learned route
az network vnet-gateway list-learned-routes -g <rg> -n hub1ergw -o json \
  > show-output/s1-02-hub1-learned.json
# Expect: 10.50.1.0/24 present, 10.50.2.0/24 absent

# 3. Generate traffic
az vm run-command invoke -g <rg> -n vm-spoke1 --command-id RunShellScript \
  --scripts "for i in 1 2 3 4 5 6 7 8 9 10; do curl -sv --max-time 5 http://10.50.1.10/ 2>&1 | head -3; sleep 1; done" \
  > show-output/s1-03-curl-from-spoke1.txt

# 4. KQL: AzFW Network Rule hits for this 5-tuple, both hubs
# (Niobe runs against the Log Analytics workspace shared by both AzFWs)
az monitor log-analytics query -w <workspace_id> --analytics-query "
AZFWNetworkRule
| where TimeGenerated > ago(10m)
| where SourceIp == '10.11.0.5' and DestinationIp == '10.50.1.10'
| summarize hits=count() by Resource, Action
| order by Resource asc
" -o table > show-output/s1-04-azfw-hits.txt
```

**Pass criteria:** Hub1's AzFW shows ≥10 Allow hits for `10.11.0.5 → 10.50.1.10`. Hub2's AzFW shows **0** hits for this 5-tuple. curl gets HTTP responses (any 2xx/3xx/4xx: connection working is the test).

**Fail criteria:** Hub2's AzFW shows ≥1 hit (asymmetry leak); OR curl times out (firewall rule misconfigured: Trinity to backstop).

### S2: Symmetric flow, Spoke3 ↔ GCP-VPC-B (Region B only)

Same shape as S1, opposite region. Pass = Hub2-AzFW only; Hub1-AzFW = 0 hits.

Artifact prefix: `s2-*`. Source IP `10.21.0.5`, destination `10.50.2.10`.

### S3: Cross-region spoke ↔ spoke, Spoke1 ↔ Spoke3

**Hypothesis:** `curl` from Spoke1 (10.11.0.5) to Spoke3 (10.21.0.5) traverses Hub1-AzFW AND Hub2-AzFW once each per direction, totalling exactly 2 firewalls per packet. No third firewall (GCP) involved.

**Verification:**

```bash
az vm run-command invoke -g <rg> -n vm-spoke1 --command-id RunShellScript \
  --scripts "curl -sv --max-time 5 http://10.21.0.5/ 2>&1" \
  > show-output/s3-01-curl-spoke1-to-spoke3.txt
az vm run-command invoke -g <rg> -n vm-spoke1 --command-id RunShellScript \
  --scripts "traceroute -n -w 2 -q 1 10.21.0.5 2>&1" \
  > show-output/s3-02-traceroute-spoke1-to-spoke3.txt
# KQL: hits on both AzFWs for the same 5-tuple
az monitor log-analytics query -w <workspace_id> --analytics-query "
AZFWNetworkRule
| where TimeGenerated > ago(5m)
| where SourceIp == '10.11.0.5' and DestinationIp == '10.21.0.5'
| summarize hits=count() by Resource, Action
" -o table > show-output/s3-03-azfw-hits-both.txt
```

**Pass:** Both Hub1 and Hub2 AzFWs show hits for `10.11.0.5 → 10.21.0.5` AND the reverse direction for the return packets. Traceroute shows 2 transit hops (one per hub).

**Fail:** Only one AzFW logs hits (single hub in path → routing-intent broken); OR traceroute shows >2 transit hops (route loop or detour through ER).

### S4: Deliberate symmetry break (the failure-mode demo)

**Setup change:** Tank flips `er_bow_tie=no` → `yes` and adds `hub2ergw → Circuit1` + `hub1ergw → Circuit2` connections. ~2 minutes propagation. **No spoke change**, no GCP change.

**Repeat S1's curl** (Spoke1 → GCP-VPC-A 10.50.1.10).

**Pass criteria:** Curl now **fails** with timeout. KQL on `AZFWNetworkRule` shows:
- Hub1-AzFW: Allow on egress SYN `10.11.0.5 → 10.50.1.10`.
- Hub2-AzFW: **Drop** on `10.50.1.10 → 10.11.0.5` return SYN-ACK with reason `No matching rule / Stateful drop`.

Same 5-tuple split across two firewall instances = asymmetric routing confirmed. Artifact `s4-01-azfw-drop-evidence.txt`.

**Restore step (mandatory before S5/cleanup):** Tank removes the bow-tie connections; curl re-succeeds (re-run S1 commands, expect Pass).

### S5: (deferred, document only, do not run)

Hub-disconnect failure simulation. Would require deleting a hub-to-hub link, which vWAN does not expose as a user-controllable knob (the link is auto-created and managed). Not viable as written. Documented as a non-trivial follow-up requiring NSGs / UDR perturbation to simulate.

## 5. Region and VM SKU selection

### 5.1 Region pair (Azure)

**Primary: `swedencentral` (Region A) + `northeurope` (Region B).** Both verified at manifest time with the charter SKU probe against the caller's subscription.

| Region | B2als_v2 catalog? | B2als_v2 restrictions? | Decision |
|---|---|---|---|
| swedencentral | Yes | None | OK |
| northeurope | Yes | None | OK |

Probe ran 2026-06-15. Full output captured in `labs/vwan-dual-er-symmetric/sku-probe.txt` (Tank to write at deploy time as Phase 0 evidence). Subscription used: caller's `az account show` context (Litware-MngEnvMCAP642473-jomore tenant; GUID stays out of the repo per rule #10).

### 5.2 Megaport ER peering locations

Chosen primary pair:
- **Region A (swedencentral) → ER peering location `Stockholm`** (Equinix SK1 / Interxion STO1, ER zone 1, Megaport-enabled per `expressroute-locations-providers`).
- **Region B (northeurope) → ER peering location `Amsterdam`** (Equinix AM2 / Interxion AMS, ER zone 1, Megaport-enabled).

Both are Zone 1 → same per-Mbps price as Madrid / Frankfurt / Paris.

**Fallback PoP pair if Tank hits a capacity / Megaport-account restriction:**
- Region A fallback: `Frankfurt` (lab #1's actual Megaport-picked PoP was Frankfurt despite a Madrid request: Megaport may pivot the MCR market). Frankfurt remains Zone 1 and is well-connected to swedencentral.
- Region B fallback: `Dublin` (Equinix DB3, Zone 1, geographically closer to northeurope than Amsterdam fallback).

> **Tank deploy note (2026-06-15):** MCR1 fallback fired. Our Megaport account does NOT have `MEGAPORT_SWEDEN` enabled: Stockholm SK1 failed with `Missing markets: Sweden`. MCR1 was deployed in `Equinix Frankfurt FR5` (id 131, MEGAPORT_GERMANY). MCR2 in Amsterdam AM1 succeeded as primary. ER peering location for circuit 1 remains "Stockholm": the VXC bridges Frankfurt-MCR ↔ Stockholm-ER peering through the Megaport fabric, exactly as lab #1 (Frankfurt-MCR ↔ Madrid-ER) did.

**Lab-#1 lesson applied:** the MCR location and the ER peering location do not have to match. Lab #1 deployed an MCR in Frankfurt FR5 paired against an ER circuit ordered for Madrid; Azure still learned the routes. We therefore do not pre-commit MCR markets: Tank/Megaport pick them at deploy and Niobe records the actual values.

### 5.3 VM SKU

**`Standard_B2als_v2`** (2 vCPU, 4 GiB, AMD burstable). Cheapest viable Linux lab SKU per charter, available unrestricted in both regions.

Zone strategy: **non-zonal** (no `zones` attribute on the VM resource). This lab is not about zone behaviour; non-zonal lets Azure place the VM in any available zone and sidesteps any future zone-scoped restrictions.

Fallback SKU per region: `Standard_B2as_v2` (4 vCPU, 8 GiB, AMD burstable, also catalog-confirmed both regions): only if at deploy time `B2als_v2` is unexpectedly capacity-blocked.

OS: Ubuntu 22.04 LTS Gen2 (matches lab #1, has `traceroute` and `curl` pre-installed via cloud-init).

Disk: Standard SSD, 30 GiB (smallest supported tier for Ubuntu 22.04 Gen2).

Auth: SSH key only (Linux). No VM admin password needed. Public key sourced from `$env:AZURE_SSH_PUBLIC_KEY` or `$env:AZURE_SSH_PUBLIC_KEY_PATH`.

## 6. Cost estimate (per 24 h)

All figures USD retail, sourced from Azure Pricing Calculator and Megaport public quotes; Megaport quote at order time is authoritative.

| Plane | Resource | SKU / size | Qty | $/24 h | Notes |
|---|---|---|---:|---:|---|
| Azure vWAN | Virtual WAN | Standard | 1 | $0 | Free; pay per hub. |
| Azure vWAN | Virtual Hub (deployment unit) | n/a | 2 | ~$12 | $0.25/hr × 2 hubs. |
| Azure vWAN | ER scale-unit (1 SU per hub) | ER routing infra | 2 | ~$24 | $0.50/hr × 2. |
| Azure vWAN | Secured-hub Azure Firewall | Standard tier, in-hub | 2 | ~$60 | $1.25/hr × 2. **This is the dominant Azure cost.** |
| Azure vWAN | Routing-intent policy | Private | 2 | $0 | No additional charge per policy. |
| Azure ER | ER Circuit | Standard, MeteredData, 50 Mbps, Zone 1 | 2 | ~$3.67 | $55/mo × 2 / 30 days. |
| Azure ER | ER data transfer (egress) | ~50 Mbps test traffic |: | <$0.50 | Negligible at lab volumes. |
| Azure ER | Public IP on ER GW | n/a | 0 | $0 | vWAN ER GW is managed; no user-visible PIP. |
| Azure spoke | VNet | /24 each | 4 | $0 | |
| Azure spoke | NIC | 1 per VM | 4 | $0 | |
| Azure spoke | Linux VM | `Standard_B2als_v2` non-zonal | 4 | ~$3.75 | $0.039/hr × 4 × 24. |
| Azure spoke | OS disk | Standard SSD, 30 GiB | 4 | ~$0.30 | $0.075/disk/day. |
| Azure observ. | Log Analytics workspace (AzFW logs) | Pay-as-you-go | 1 | ~$2 | ~1 GiB/day ingest projection. |
| Azure misc | Storage account (TF state, NSG flow logs) | LRS, hot | 1 | ~$0.10 | |
| Megaport | MCR | 1 Gbps, 1-month `contractTerm` | 2 | ~$6.40 | $0.10/hr × 2 × 24 minimum. **Megaport quote authoritative; 1-month minimum applies.** |
| Megaport | VXC to Azure ER | 50 Mbps × 2 (one per ER) | 2 | ~$10 | $0.10-0.15/hr × 2. Nested under MCR `associatedVxcs`. |
| Megaport | VXC to GCP Interconnect | 50 Mbps × 2 | 2 | ~$10 | |
| GCP | VPC | per region | 2 | $0 | |
| GCP | Cloud Router | per VPC | 2 | $0 | Free below quota. |
| GCP | Partner Interconnect attachment | 50 Mbps × 2 | 2 | ~$2.40 | $0.05/hr × 2 × 24. |
| GCP | VM | e2-micro × 2 | 2 | ~$0.20 | Free tier covers most. |
| GCP | Egress to MCR | ~50 Mbps test |: | <$1 | Inter-region egress; lab volume. |
| **Subtotal Azure** | | | | **~$106** | |
| **Subtotal Megaport** | | | | **~$26** | |
| **Subtotal GCP** | | | | **~$3** | |
| **TOTAL** | | | | **~$135 / day** | |

> ⚠️ **Cost guardrail breach.** This is well above the $50/day flag in routing rule #7. **Morpheus formally flags this for Jose's explicit cost approval at gate #12 #1.**
> Comparison: lab #1 ran at ~$110-$125/day; this lab is roughly +$15-$25/day for the second region's gateway + firewall + circuit + MCR. The AzFW Standard ($60/day) and ER scale-unit ($24/day) are the two biggest reducible levers: but reducing either changes what the lab demonstrates.
> If Jose wants a cheaper variant: dropping to one secured-hub + one routed-hub (`secure_hub=yes` only in hub1) saves ~$30/day but invalidates Scenarios S2 and S3 because Hub2 has no firewall to count hits on. Not recommended.

## 7. Secrets inventory (Key Vault `platform-secrets-1138`)

Vault: `platform-secrets-1138`, RG `platform`, region `swedencentral`, RBAC-enabled. Tank's deploy wrapper resolves secrets at runtime; nothing committed.

| Secret name | Required? | Used by | Purpose / what value goes in |
|---|---:|---|---|
| `megaport-api-key` | **Yes** | Tank's deploy script → Megaport TF provider `MEGAPORT_ACCESS_KEY` env var | Megaport REST API access key. Get from Megaport Portal → Tools → API Keys. |
| `megaport-api-secret` | **Yes** | Tank's deploy script → `MEGAPORT_SECRET_KEY` env var | Paired secret for `megaport-api-key`. Same Portal page. |
| `vm-admin-ssh-public-key` | **Yes** (or env var fallback) | Tank's TF for all 4 Linux VMs | OpenSSH public key (`ssh-ed25519 …` or `ssh-rsa …`). Stored as the public key only. Falls back to `$env:AZURE_SSH_PUBLIC_KEY` if KV not reachable. |
| `gcp-service-account-json` | **Yes** | Tank's deploy wrapper → `GOOGLE_APPLICATION_CREDENTIALS` env var for `gcloud` shell-outs (or for a Terraform google provider if Tank chooses TF for GCP) | Service-account JSON with `roles/compute.networkAdmin` + `roles/compute.instanceAdmin.v1` + `roles/billing.user` scoped to a dedicated lab project. Stored as the full JSON blob, base64-encoded if KV size limits demand. |

**Out of scope (no secret needed):** VM admin password (Linux, key-only). Tenant ID (resolved from `az account show` at runtime). ER service key (generated by Azure at circuit-create time, consumed in-memory by Megaport TF, never written to disk).

**Action for Jose before deploy approval:**

1. Add `megaport-api-key` to KV `platform-secrets-1138` if not already present: value: existing Megaport Portal API access key (the one used for lab #1 should work if it has not been rotated).
2. Add `megaport-api-secret`: value: paired secret from same Portal page.
3. Add `vm-admin-ssh-public-key`: value: contents of `~/.ssh/id_ed25519.pub` (or chosen lab key).
4. Add `gcp-service-account-json`: value: JSON key file for a service account scoped to a new lab GCP project (recommend creating `onpremsim-${RANDOM}` per lab run, matching the pattern in `vwan_2xshub.azcli` line 126). If Jose prefers, the deploy wrapper can instead invoke `gcloud auth login` interactively and skip this secret entirely; flag that decision at gate.

Trinity will produce the matching `data "azurerm_key_vault_secret"` blocks in the Terraform handoff; Tank will wire the deploy wrapper.

**Sanitization mandate:** none of these secret values may appear in any committed file, log, terraform state copy, `show-output/` capture, or screenshot. Niobe redacts `service-key`, `bearerToken`, and `Authorization:` headers from any captured output.

## 8. Deploy and cleanup approach

### 8.1 IaC

**All Terraform**, reusing the lab-#1 pattern under `src/terraform/vwan-dual-er-symmetric/`. Tank picks module reuse boundaries; Morpheus's recommendation:

- Reuse `versions.tf`, `providers.tf` shape from `src/terraform/expressroute-megaport-bgp/` verbatim (already has azurerm, azapi, megaport, random providers pinned).
- Reuse `megaport.tf` MCR + nested `associatedVxcs` pattern.
- Reuse `azure-expressroute.tf` circuit shape; duplicate it parameterised by region.
- New: `vwan.tf` (Virtual WAN + 2 vhubs + AzFW Standard + routing-intent), `spoke-vnets.tf` (4 spoke VNets + VM + NIC + NSG; module per spoke), `gcp.tf` (Google provider + 2 VPCs + Cloud Routers + Interconnect attachments + 2 VMs).
- Single state file, single `terraform apply` invocation. Justification: same as lab #1: multi-provider with cross-provider dependencies (ER service key → Megaport VXC → GCP attachment pairing key) needs one dependency graph.

### 8.2 Subscription handling

`<SUBSCRIPTION_ID>` placeholder in all committed `.tf`, `.tfvars.example`, and README files. Resolution chain at deploy time (Tank's wrapper script):

1. `--subscription` flag on the deploy invocation.
2. `$env:ARM_SUBSCRIPTION_ID` / `$env:AZURE_SUBSCRIPTION_ID`.
3. Output of `az account show --query id -o tsv`.

`tfvars` containing real values stay uncommitted (`labs/vwan-dual-er-symmetric/deploy/terraform.tfvars` git-ignored at the repo root `.gitignore`, per the lab-#1 cleanup decision from 2026-05-29).

### 8.3 Deploy time (long-pole identification)

| Resource | Time | Parallelisable? |
|---|---:|---|
| Resource group | <1 min | n/a |
| VNets, subnets, NSGs, NICs, public IPs (where used) | <2 min | yes |
| Virtual WAN | ~2 min | yes |
| Virtual Hub × 2 | 20-30 min each | **yes: both hubs in parallel** |
| ExpressRoute Circuit × 2 | 2-5 min each (service-key generation) | yes |
| Megaport MCR × 2 | 5-10 min each | yes |
| Megaport VXC × 4 (2 Azure + 2 GCP) | 5-15 min each | yes after MCRs |
| ER GW (hub-resident) × 2 | included in vHub creation timeline | n/a |
| ER GW connection × 2 | 1-2 min each after VXC is up | sequential after VXC |
| AzFW Standard × 2 (in-hub) | 10-15 min each | yes, with hubs |
| GCP project + VPCs + VMs + routers + attachments × 2 | ~10 min total | yes |
| Spoke VNet → vHub connection × 4 | 2-3 min each | sequential after hub up |
| Linux VMs × 4 | 3-5 min each | yes |
| Routing-intent PUT × 2 | 2-3 min each | sequential after AzFW up |

**Estimated wall-clock deploy time: 40-55 minutes** if all parallelisable resources kick off concurrently. The long pole is vHub (30 min) + AzFW (15 min) + routing-intent (3 min) = ~48 min worst case.

### 8.4 Cleanup chain

Order matters: reversing it risks 30-40 min vWAN gateway hangs and Megaport HTTP 409s (lab-#1 lesson learned).

1. **Restore design defaults** if any S4 perturbation is still in place (remove bow-tie ER-GW connections, restore route-table associations).
2. **Spoke connections**: delete each spoke VNet → vHub connection (4 total).
3. **ER GW connections**: delete each ER GW → circuit connection (2 total). Must be gone before circuit delete.
4. **Routing-intent**: delete (PUT to `routingIntent` with empty policies, or DELETE on the intent resource).
5. **Virtual Hubs**: delete each vHub (this also deletes the in-hub ER GW and AzFW). 20-30 min each.
6. **Virtual WAN**: delete after both hubs are gone.
7. **ER Circuits**: delete each circuit. **Must come after** the Megaport VXC delete in step 8 to avoid `serviceProviderProvisioningState=Deprovisioning` race conditions.
8. **Megaport VXCs**: delete each (4 total). Must delete the Azure-side connection (step 3) before deleting the Azure-VXC, and must delete the GCP attachment (step 9) before deleting the GCP-VXC.
9. **GCP Interconnect attachments**: `gcloud compute interconnects attachments partner delete` × 2.
10. **GCP VMs, routers, VPCs, project**: full GCP teardown × 2. Project deletion releases all GCP charges.
11. **Megaport MCRs**: delete each MCR (only after all its VXCs are gone).
12. **Azure resource group**: delete last. Sweeps VNets, NSGs, NICs, VMs, disks, public IPs, Log Analytics workspace.
13. **Soft-deleted KV / disk purge**: N/A this lab (no KV created; KV is platform `platform-secrets-1138`, untouched). Tank confirms no orphaned disks/PIPs.

Cleanup gate #12 #2 is approved per dry-run output before any destructive action.

## 9. Approval-gate package (Phase 4: read me in 30 seconds)

```
LAB SLUG:        vwan-dual-er-symmetric
REGIONS:         swedencentral (Region A) + northeurope (Region B)
HUB PREFIXES:    10.10.0.0/23 (Hub1) | 10.20.0.0/23 (Hub2)
SPOKE PREFIXES:  10.11/24, 10.12/24 (Hub1) | 10.21/24, 10.22/24 (Hub2)
ON-PREM SIM:     2× GCP VPC (10.50.1.0/24, 10.50.2.0/24); no inter-VPC peering
SECURED HUB:     YES: Azure Firewall Standard in both hubs
ROUTING INTENT:  private (both hubs); NO internet policy this lab
ER BOW-TIE:      NO (deliberate: see §2.4)
GLOBAL REACH:    NO (deliberate: see §2.5)

SYMMETRY MECHANISM (one line):
  Each hub advertises only its own region's spoke prefixes into its co-located
  ER circuit, AND each GCP VPC connects to one MCR only (no inter-VPC peering),
  so per-region prefix affinity holds in both directions: verified by AzFW
  hit counts being non-zero on the expected hub and zero on the other.

DAILY COST:      ~$135/day (~$106 Azure + ~$26 Megaport + ~$3 GCP)
                 ⚠️ ABOVE $50/day flag: explicit Jose approval requested.
DEPLOY TIME:     ~45-55 min wall clock (vHub × 2 is the long pole at ~30 min each)
LIFETIME:        Target 24-48 h. Cleanup gate after Niobe validation + Oracle
                 diagrams + Kid blog draft.
SECRETS IN KV:   4: megaport-api-key, megaport-api-secret, vm-admin-ssh-public-key,
                 gcp-service-account-json. Jose to add to platform-secrets-1138
                 before deploy.

RISKS / "this might not behave exactly as documented":
  1. lab-#1 saw Megaport pivot the MCR market (Madrid → Frankfurt). Same may
     happen here; design tolerates it (any Zone-1 PoP works).
  2. lab-#1 saw `az network express-route list-route-tables` return "no BGP
     sessions" despite working BGP: Niobe has fallback evidence path.
  3. vWAN routing-intent + bow-tie interaction is documented but the asymmetry
     in S4 depends on Azure best-path selecting the direct-circuit path; if
     vWAN happens to prefer the hub-to-hub path on both hubs, S4 may not
     produce the expected drop: Niobe will document whichever behaviour
     actually occurs.
  4. AzFW Standard log latency to Log Analytics is typically 3-5 min; Niobe
     waits before running the hit-count KQL.
```

## 10. Editorial review notes

**Kid (pre-gate editorial, 2026-06-15):**

**Q1 (narrative):** S1-S3 establish symmetric baselines for Region-A, Region-B, and cross-region east-west paths; S4 breaks symmetry and captures the stateful drop. The arc is publishable: before/after is explicit, the headline finding (Hub2 AzFW drops the return SYN-ACK on a flow Hub1 forward-passed) is demonstrable and novel, and a reader walks away with a concrete rule: no bow-tie + separate on-prem VPCs = symmetry by construction. **One risk to flag:** manifest §9 Risk #3 acknowledges that if vWAN prefers the hub-to-hub path over the bow-tied direct-circuit path, S4's bow-tie mechanism may not trigger the expected drop, collapsing the narrative. Niobe's validation.md instead uses MCR1 prefix injection to create asymmetry: more reliable because it directly forces GCP's routing table rather than depending on Azure best-path selection. **Morpheus should align manifest S4 and validation S4 on which perturbation mechanism actually runs before deploy.**

**Q2 (evidence):** Evidence for S1-S3 is solid: verbatim commands, named artifacts, AzFW hit-count KQL with explicit pass criteria (Hub-X ≥10, Hub-Y = 0). Three proposed extensions:

1. **S4 pre-perturbation baseline is unnamed.** Add artifact `s4-00-azfw-baseline-both-hubs.txt` capturing both AzFW hit counts *before* injection. Without a timestamped "before" snapshot, the post says "we broke it and it broke": no contrast.

2. **S4 failure visibility is firewall-log-only.** Extend: capture `az vm run-command … --scripts "ss -tn state SYN-SENT 2>&1"` on the injected-flow source VM during the failure window → `s4-vm-half-open.txt`. Shows TCP SYN-SENT stall at the VM level; readers can replicate without Log Analytics access.

3. **KQL table inconsistency.** Manifest uses `AZFWNetworkRule` (resource-specific, lower latency); validation uses legacy `AzureDiagnostics | where Category == "AzureFirewallNetworkRule"`. Standardize on `AZFWNetworkRule` to prevent "no rows" confusion at evidence-collection time.

**Total:** 295 words.

## 11. Open questions for gate #12 #1

1. **Cost approval.** $135/day vs $50/day flag: confirm or revise (drop secured-hub on Hub2 = ~$30/day savings, breaks S2/S3; document choice in approval).
2. **GCP credential strategy.** Service-account JSON in KV, or interactive `gcloud auth login` on Tank's deploy machine?
3. **Lab lifetime.** 24 h or 48 h between deploy and cleanup gate? (Drives whether Niobe + Oracle + Kid have one or two working days.)
4. **Megaport PoP fallback consent.** If Stockholm or Amsterdam are unavailable at order time, OK to fall back to Frankfurt + Dublin (Zone 1, same price)?
5. **Kid pre-gate review.** Dispatch Kid for one async editorial pass on this manifest before gate, or skip?

## 12. Potential follow-up labs

- Internet-egress symmetry (`ri_policy=both`), per-hub NAT IP affinity, public-IP allocation strategy.
- ER HA failover (`er_bow_tie=yes` deliberately, with AS-path prepend to maintain region preference under steady state).
- VPN branch as third on-prem (mix of ER and VPN entry points → MED / local-pref tuning).
- BGP communities for per-spoke route filtering at the ER GW (extends lab-#1's community lessons into vWAN).
- AzFW Premium with TLS inspection on the east-west path (cost-dominant; do only if the test demands it).
- Routing-intent + custom route tables (`vnet_ass=vnet`, `vnet_prop=vnet`): what breaks when both are in play.
