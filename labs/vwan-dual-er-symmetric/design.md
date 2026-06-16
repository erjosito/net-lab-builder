# vwan-dual-er-symmetric: Phase 3.1 Network Design

**Owner:** Trinity (Azure Network SME)
**Status:** Paperwork-only design. No IaC, no deploys, no Megaport writes.
**Lab folder:** `labs/vwan-dual-er-symmetric/`
**Authored:** 2026-06-15
**Updated:** 2026-06-15: address plan aligned to Morpheus manifest §9; KV inventory locked to 3 secrets; operator pre-deploy checklist added; reserved-spare block relocated (see inbox note). §1.5 resiliency gap tightened; §1.6 resiliency analysis added (13 failure modes, 5 mitigations, S5 recommendation); sections §1.6-§1.8 renumbered to §1.7-§1.9.
**Subscription / tenant hygiene:** Use `<SUBSCRIPTION_ID>` everywhere; resolve at deploy time via `az account show --query id -o tsv`. No GUIDs in this file.

---

## Vault references

Indexed before drafting (vault write at lab close, Rule #15): [[Patterns/Virtual-WAN]], [[Services/Azure-Virtual-WAN]], [[Services/ExpressRoute]], [[Services/Megaport]], [[Topics/BGP-on-Azure]], [[Patterns/Hub-and-Spoke]], [[Labs/2026-05-ExpressRoute-Megaport-BGP]]. Vault gaps for backfill: `Patterns/Dual-Region-Secured-vWAN-with-ER.md`, MCR prefix-filter-list entry in `Services/Megaport.md`, `Topics/Traffic-Symmetry-Stateful-Firewall.md`.

---

## Operator pre-deploy checklist

**(a) KV firewall / GSA:** Before Tank's deploy, either pause GSA (Path A, preferred) or temporarily flip `defaultAction=Allow` with pre-snapshot (Path B). Tank probes `az keyvault secret list --maxresults 1` and halts on 403. Full workaround details: `decisions.md` 2026-06-15T10:15:00+02:00.

**(b) GCP credentials:** Run `gcloud auth list`; confirm `erjosito1138@gmail.com` is active. If session expired, run `gcloud auth login && gcloud auth application-default login`.

**(c) Mechanism stack:** Traffic-symmetry design (Mechanism A: per-region MCR prefix affinity) is described in §1.5.

---

## 1.1 Address-space plan

| Block | Prefix | Region | Notes |
|---|---|---|---|
| Hub1 | `10.10.0.0/23` | A (swedencentral) | vWAN-managed. Includes auto-allocated subnets for `AzureFirewallSubnet`, `RouteServerSubnet`, ER GW infra. |
| Hub2 | `10.20.0.0/23` | B (northeurope) | vWAN-managed. Same shape as Hub1. |
| Spoke1 (Region A) | `10.11.0.0/24` | A | One VM subnet only. |
| Spoke2 (Region A) | `10.12.0.0/24` | A | One VM subnet only. |
| Spoke3 (Region B) | `10.21.0.0/24` | B | One VM subnet only. |
| Spoke4 (Region B) | `10.22.0.0/24` | B | One VM subnet only. |
| GCP on-prem VPC-A | `10.50.1.0/24` | GCP (on-prem sim region A) | Visible to MCR1 → Hub1 by default; in Mechanism A it stays advertised by MCR1 only. No inter-VPC peering on GCP side. |
| GCP on-prem VPC-B | `10.50.2.0/24` | GCP (on-prem sim region B) | Symmetric pair for MCR2 → Hub2. Separate VPC, no peering to VPC-A. |
| Reserved spare /16 | `10.99.0.0/16` | unallocated | For future "anomaly" spokes (asymmetric NVA, third-circuit test, route-server insertion) without re-plumbing. *(Relocated from `10.50.0.0/16`: that block is now consumed by GCP VPC-A/B; see inbox note `trinity-prefix-refresh-spare-relocated`.)* |

**Non-overlap audit:** All Azure prefixes inside `10.10.0.0/23`-`10.22.0.0/24`; GCP `10.50.1.0/24` / `10.50.2.0/24` (distinct from Azure range); reserved spare `10.99.0.0/16` clear of all above; no overlap with lab #1 ranges. BGP regional communities (`12076:<code>`) captured by Niobe at validation time.

## 1.2 Subnet plan per VNet

| VNet | Subnet | Prefix | Purpose |
|---|---|---|---|
| Spoke1 | `vm-subnet` | `10.11.0.0/26` | Lab VM only. NSG attached (default-deny inbound from Internet; permit intra-VNet + intra-hub). |
| Spoke2 | `vm-subnet` | `10.12.0.0/26` | Lab VM only. |
| Spoke3 | `vm-subnet` | `10.21.0.0/26` | Lab VM only. |
| Spoke4 | `vm-subnet` | `10.22.0.0/26` | Lab VM only. |
| Hub1 | (auto) | `10.10.0.0/23` | vWAN allocates `AzureFirewallSubnet`, ER infra subnets internally. Tank does not author hub subnets. |
| Hub2 | (auto) | `10.20.0.0/23` | Same. |

No additional subnets in v1: no Bastion, no `GatewaySubnet` (vWAN handles ER GW), no `AzureFirewallManagementSubnet` (in-hub Azure Firewall in vWAN doesn't need it).

VM access path: SSH via `az vm run-command invoke`. No public IPs on lab VMs. NSG outbound: permit all (default).

## 1.3 Routing intent + hub route tables

| Decision | Value | Source |
|---|---|---|
| Route tables per hub | `defaultRouteTable` and `noneRouteTable` only: **no custom RTs in v1** | Morpheus manifest direction; matches vault [[Services/Azure-Virtual-WAN]] "Routing Intent is the win". |
| Routing intent policy | **`private`** (per Morpheus). No Internet policy in v1. Next-hop: in-hub Azure Firewall. | Confirms Morpheus. If Morpheus's final manifest says `both`, Trinity rolls forward: `private` is the symmetry-critical lever; adding `internet` does not break symmetry. |
| Spoke VNet connections | Association: `defaultRouteTable`. Propagation: `defaultRouteTable` (label `default`). | Standard. With RI=private, vWAN auto-rewrites association/propagation; explicit setting is for clarity / readback. |
| ER GW connections (per hub) | Association: `defaultRouteTable`. Propagation: `defaultRouteTable` (label `default`). | With RI=private vWAN takes over: ER-learned prefixes get redirected so spoke-bound traffic next-hops the firewall, not the ER GW directly. Confirmed pattern in `vwan_2xshub.azcli` lines 2305-2320. |
| SNAT on in-hub firewall (East-West) | **Disabled** for spoke-to-spoke; **enabled** for spoke-to-on-prem (return-path safety per [[Patterns/Virtual-WAN]] Welly Lee Q&A: but that Q&A was for Private Endpoints; for plain VMs SNAT may be safely off: confirm in validation). `[needs confirmation]` | Vault Q&A is PE-specific. Mark as confirmation item for Niobe. |
| Hub-routing-preference | **Default** (`ExpressRoute`): do NOT switch to `ASPath` in v1. | Switching to ASPath flips inter-region preference behavior; the lab's symmetry baseline must be the default before any toggle. |
| Global Reach | **Not configured** | Default per Morpheus; explicitly out-of-scope so dual-ER stays dual. |
| ER bow-tie (ER1↔Hub2 + ER2↔Hub1) | **Not configured** | Default per Morpheus; explicitly out-of-scope. |

**ER GW connection inheritance note (for the design write-up Tank reads):** the `az network express-route gateway connection create` line in lab #1's reference (`vwan_2xshub.azcli:2307`) explicitly passes `--associated-route-table` and `--propagated-route-tables` pointing to `defaultRouteTable`, then `--labels default`. With routing intent private, vWAN overrides the effective behavior: it programs the firewall as the next-hop for spoke prefixes regardless of what the connection's route-table fields say. Tank must still pass the fields (Terraform requires them) but the operative state lives in routing intent.

## 1.4 BGP / ASN map

| Component | ASN | Role / source |
|---|---|---|
| Hub1 firewall (vWAN-internal BGP) | `65520` | vWAN-reserved for in-hub Azure Firewall. Same value used in both hubs. Not configurable. |
| Hub2 firewall (vWAN-internal BGP) | `65520` | Same. |
| Hub1 ER GW (Azure side of MCR1 BGP session) | `12076` | Microsoft public ASN: fixed for all ER private peering. |
| Hub2 ER GW (Azure side of MCR2 BGP session) | `12076` | Same. |
| MCR1 | `65001` | Matches lab #1's MCR default (charter ASN reuse). |
| MCR2 | `65002` | Distinct from MCR1 for trace clarity. |
| GCP Cloud Router | `65003` | New (avoids `16550` GCP default: `16550` is the partner-interconnect ASN; pick a private ASN for the lab's CR-side. Morpheus confirms GCP env. |
| ER private peering /30s (MCR1↔MSEE1, MCR2↔MSEE2) | n/a: auto | Megaport auto-assigns from `169.254.x.x` linknet space; Megaport-managed peering (do **not** author `azurerm_express_route_circuit_peering`). Reference: `vwan_2xshub.azcli:2299` ("Wait 1min more to the private peering to show up") and vault [[Services/Megaport]] "API gotchas". |

**ASN-collision audit:** `12076` is Microsoft-reserved; `65001`/`65002`/`65003` are private ASNs in the 64512-65534 range; `65520` is vWAN-reserved per Morpheus's image. No collisions. Lab #1 used MCR ASN `64512`; this lab uses `65001`/`65002` so trace artifacts from lab #1 won't mask this lab's MCR identity if both happen to be in the show-output captures at the same time.

## 1.5 Traffic-symmetry mechanism (the actual mechanism)

**Recommendation: Mechanism A: per-region prefix affinity at MCR, with Mechanism B (AS-PATH prepend) demonstrated as the documented fallback in Scenario 4.**

### Trade-off table

| Mechanism | Pros | Cons | Recommend? |
|---|---|---|---|
| **A. Per-region prefix affinity at MCR.** MCR1 exports only Region-A Azure prefixes (Hub1 + Spoke1 + Spoke2) to GCP; MCR2 exports only Region-B Azure prefixes (Hub2 + Spoke3 + Spoke4) to GCP. Azure→on-prem direction is already per-region (each Hub ER GW only carries its own circuit's learned prefixes as the preferred path; hub-to-hub via routing intent provides cross-region reachability for spoke-to-spoke without bleeding into the ER path). | Symmetric by construction. No BGP exotica inside Azure. Easy to reason about: the filter is a single declarative list per MCR. Failure mode is loud (a misconfigured filter results in either no advertisement or asymmetric, both visible in BGP table). | **No automatic failover.** If MCR1, ER1, Hub1 ER GW, or the MCR1↔GCP BGP session fails, Region-A prefixes disappear from GCP's routing table entirely. **GCP instances lose all reach to Hub1 (and Spoke1, Spoke2) under these failure modes.** This is acceptable for this lab's purpose: demonstrating steady-state symmetry with both circuits up: but not acceptable for production. See **§1.6** for the complete failure-mode catalogue and ranked mitigations. | **YES: default.** |
| **B. AS-PATH prepend at MCR.** Both MCRs advertise all Azure prefixes to GCP, but each prepends its own ASN N times (e.g., N=3) for the "wrong" region's prefixes. GCP picks the shorter AS-path → traffic from GCP to Region-A Azure prefixes goes via MCR1; to Region-B via MCR2. | Failover works automatically: if MCR1 is down, MCR2's longer-AS-path advertisement wins by default. Aligns with the "prepend with **public** ASN" guidance from [[Services/Azure-Virtual-WAN]] (Adam Stuart `vwan-routemaps-asn` warning): except here we prepend on the **Megaport side**, where private ASNs are *not* stripped by MSEE because the prepend isn't crossing the MSEE peering, so MCR ASN `65001`/`65002` is fine. | GCP may still tie-break unpredictably if AS-path lengths happen to equal at some other layer (MED, router-id). Risk: silent asymmetry that only shows up under specific BGP convergence orderings. Documented as Scenario 4's teachable result. | **Backup: included in v1 as Scenario 4 to demonstrate both work.** |
| **C. Global Reach + collapse to single circuit.** | Trivial. | Defeats the lab's purpose: we WANT to demonstrate dual-circuit symmetric design. | **NO.** |
| **D. BGP community tagging from GCP, action at MCR.** | Carrier-grade flexibility. | Way overscoped for a lab. Adds GCP-side complexity that has nothing to do with Azure networking. | **NO.** |

### Mechanism A: implementation detail Tank uses

**Megaport-side filter shape.** Megaport exposes prefix filtering on MCR BGP sessions via the `megaport_mcr_prefix_filter_list` Terraform resource (provider `megaportnetworks/megaport` v1.x). The list is defined once per MCR, then referenced by name from a VXC's BGP peer config block as `export_filter` (and/or `import_filter`). Concrete shape Tank validates at deploy:

```hcl
# MCR1 (Region A): export filter toward GCP: only Region-A Azure prefixes
resource "megaport_mcr_prefix_filter_list" "mcr1_to_gcp_export" {
  mcr_uid        = megaport_mcr.mcr1.product_uid
  description    = "Export only Region-A Azure prefixes to GCP"
  address_family = "IPv4"
  entries = [
    { action = "permit", prefix = "10.10.0.0/23" },   # Hub1
    { action = "permit", prefix = "10.11.0.0/24" },  # Spoke1
    { action = "permit", prefix = "10.12.0.0/24" },  # Spoke2
    { action = "deny",   prefix = "0.0.0.0/0", ge = 0, le = 32 },
  ]
}
# Reference from MCR1's BGP peer toward GCP CR:
#   bgp_connections = [{ ..., export_filter_list_id = megaport_mcr_prefix_filter_list.mcr1_to_gcp_export.id }]
```

The exact attribute name (`export_filter_list_id` vs `export_policy`) varies across Megaport provider versions: Tank's first deploy must read it back from `terraform plan` and pin the version in `versions.tf`. The MCR-to-ER-circuit BGP session does **not** need a filter (Azure side is the prefix originator we trust).

**Symmetric advertisement plan:**

| BGP session (peers) | Direction | Filter? | Prefixes advertised |
|---|---|---|---|
| MCR1 ↔ Hub1 ER GW (MSEE pair, /30) | MCR1 → Hub1 | none | All GCP prefixes learned (10.50.1.0/24, 10.50.2.0/24). |
| MCR1 ↔ Hub1 ER GW | Hub1 → MCR1 | none | All hub-learned Azure prefixes (Hub1 /23 + Spoke1 + Spoke2 + cross-region Hub2 + Spoke3 + Spoke4 via hub-to-hub). |
| MCR1 ↔ GCP CR | MCR1 → GCP | `mcr1_to_gcp_export` | Only Hub1 + Spoke1 + Spoke2 → **filter is the symmetry knob**. |
| MCR1 ↔ GCP CR | GCP → MCR1 | none | All GCP prefixes (10.50.1.0/24 + 10.50.2.0/24). |
| MCR2 ↔ Hub2 ER GW | MCR2 → Hub2 | none | All GCP prefixes. |
| MCR2 ↔ Hub2 ER GW | Hub2 → MCR2 | none | All hub-learned Azure prefixes. |
| MCR2 ↔ GCP CR | MCR2 → GCP | `mcr2_to_gcp_export` | Only Hub2 + Spoke3 + Spoke4. |
| MCR2 ↔ GCP CR | GCP → MCR2 | none | All GCP prefixes. |

GCP side sees Azure prefixes only via the "correct" MCR. Return path is forced to traverse the same hub's firewall that the outbound path used. ✓

### Mechanism B: fallback (Scenario 4 demonstration)

Drop the filter lists from Mechanism A. Add a Megaport BGP route-policy on each MCR's GCP-bound session that prepends its own ASN three times for the cross-region prefixes:

- MCR1 → GCP: prepend `65001 65001 65001` for `10.20.0.0/23`, `10.21.0.0/24`, `10.22.0.0/24`.
- MCR2 → GCP: prepend `65002 65002 65002` for `10.10.0.0/23`, `10.11.0.0/24`, `10.12.0.0/24`.

GCP CR selects shorter AS-path. Symmetric in steady state; survives MCR-1 failure (GCP picks the prepended path automatically).

**Failure mode to demonstrate in Scenario 4:** equal-length AS-path edge cases (when GCP has its own iBGP making the comparison non-deterministic). Validation captures GCP's `show ip bgp` (or `gcloud compute routers get-status`) to prove which path won.

**Patch path forward (→ §1.6 Patch catalogue).** Mechanism A's resiliency gap is catalogued in §1.6 with three live-environment patches: P1 (Mechanism B swap, $0, ~5 min) delivers automatic GCP→Azure failover; P2 (+~$1/day) closes the Azure→GCP gap; P3 (+~$1/day) covers ER GW failures. All patches are additive against the v1 state file and dormant until Jose authorises.

## 1.6 Resiliency analysis

Mechanism A provides **no automatic failover**. This section answers Jose's question: *"Would the Google instances lose connectivity to any of the hubs?"*: and catalogues every meaningful single-failure mode.

**Legend:** Hub1↔GCP = Spoke1/Spoke2 reach to GCP VPC-A; Hub2↔GCP = Spoke3/Spoke4 reach to GCP VPC-B. ✅ = already protected; ❌ = unmitigated in v1; ~ = degraded (single path).

### F-table: single-failure blast radius

✅ = already protected in v1; ❌ = unmitigated.

| # | Failure | Hub1↔GCP VPC-A | Hub2↔GCP VPC-B | Active FW | Failover | Operator action |
|---|---------|----------------|----------------|-----------|----------|-----------------|
| F1 ❌ | MCR1 entirely down | **TOTAL LOSS** | Unaffected | AzFW2 only | None | Relax MCR2 filter OR switch to Mech B |
| F2 ❌ | MCR2 entirely down | Unaffected | **TOTAL LOSS** | AzFW1 only | None | Symmetric to F1 |
| F3 ❌ | ER1 circuit fails | **TOTAL LOSS** | Unaffected | AzFW2 only | None | Same as F1 (MCR1 loses Azure routes, withdraws from GCP) |
| F4 ❌ | ER2 circuit fails | Unaffected | **TOTAL LOSS** | AzFW1 only | None | Symmetric to F3 |
| F5 ❌ | Hub1 ER GW fails | **TOTAL LOSS** | Unaffected | AzFW2 only | Platform recovery | Open support; no IaC action |
| F6 ❌ | Hub2 ER GW fails | Unaffected | **TOTAL LOSS** | AzFW1 only | Platform recovery | Symmetric to F5 |
| F7 ❌ | Hub1 AzFW fails (RI=private routes all through FW) | **TOTAL LOSS** | Unaffected | AzFW2 only | Platform recovery | Wait for platform; AzFW is zone-redundant if AZs enabled |
| F8 ❌ | Hub2 AzFW fails | Unaffected | **TOTAL LOSS** | AzFW1 only | Platform recovery | Symmetric to F7 |
| F9 ✅ | MCR1↔ER1 **primary** VXC fails (secondary survives) | ~ single path | Unaffected | AzFW1+AzFW2 | ≤ 90 s BGP hold | Monitor + repair |
| F10 ✅ | MCR1↔ER1 **secondary** VXC fails (primary survives) | ~ single path | Unaffected | AzFW1+AzFW2 | ≤ 90 s | Monitor + repair |
| F11 ❌ | MCR1↔GCP CR BGP session drops (MCR1 up) | **TOTAL LOSS** | Unaffected | AzFW2 only | None | Restart BGP on MCR1 GCP-side VXC |
| F12 ❌ | GCP CR in VPC-A fails | **TOTAL LOSS** | Unaffected | AzFW2 only | GCP platform | GCP-side action |
| F13 ❌ | GCP CR in VPC-B fails | Unaffected | **TOTAL LOSS** | AzFW1 only | GCP platform | Symmetric to F12 |

**Direct answer to Jose:** F1, F3, F5, F7, F11, F12 → GCP VPC-A instances lose **all** reach to Hub1 (Spoke1, Spoke2). F2, F4, F6, F8, F13 → GCP VPC-B instances lose all reach to Hub2 (Spoke3, Spoke4). Connectivity is all-or-nothing per region: no partial degradation. **Only F9 and F10 (single-VXC failure within one ER circuit) are protected by the v1 design** via the dual-VXC pair.

### Mitigations (ranked by complexity)

| M# | Mitigation | Failure modes | Mech | Cost (USD/day) | Complexity | Burden |
|----|------------|--------------|------|---------------|-----------|--------|
| M1 | **Mech B (AS-PATH prepend) as default.** Both MCRs advertise all prefixes; prepend 3× for cross-region. GCP reconverges automatically. | F1-F4, F11 | B | $0 | Low: replace 2 filter-list resources with 2 prepend policies | None: BGP auto-failover. Risk: AS-path tie in GCP iBGP. |
| M2 | **Cross-region GCP sessions**: MCR1↔VPC-B + MCR2↔VPC-A (+2 VXCs). Mech A filters tight in steady state; relax on failure. | F1-F4, F11 | A | +~$1 | High: 4 BGP sessions; GCP-side detection or manual flip | Medium: manual filter flip or GCP automation |
| M3 | **ER bow-tie** (ER1↔Hub2 + ER2↔Hub1). Hub2 provides path to MCR1 if Hub1 ER GW fails. | F5, F6 | A | +~$1 | Medium: 2 new ER GW connection resources | Low: vWAN routing intent automatic |
| M4 | **Dual MCR per region** (4 MCRs total). MCR HA eliminates F1/F2. | F1, F2 | A/B | +~$13 | High: doubles Megaport config | Low: automatic |
| M5 | **Redundant GCP Cloud Router per VPC** (2nd CR + 2nd VXC per region). | F12, F13 | Any | +~$1 | Low-medium: 2 CR resources, 2 BGP peers | Low: GCP-side HA |

**M1 is the lowest-effort production mitigation**: zero additional resources, automatic GCP→Azure failover for F1-F4 and F11. Trade-off (AS-path tie-break) is Scenario S4's teachable moment.

### Patch catalogue (apply against live v1 state)

Patches are dormant until Jose authorises. Coordinator dispatches Tank. Each is additive and idempotent: no destructive change to v1. Apply order: P1 before P2; P3 is independent.

**P1: Mechanism B swap: prefix-filter → AS-PATH prepend**
- Mitigates: F1-F4, F11 for the **GCP→Azure direction** (automatic BGP failover when primary MCR/ER path drops). Azure→GCP for the failed region's VPC is a residual gap until P2.
- TF delta: Remove `megaport_mcr_prefix_filter_list.mcr1_to_gcp_export` + `.mcr2_to_gcp_export`; add 2 Megaport BGP prepend route-policy resources (MCR1 prepends `65001 65001 65001` for Hub2/Spoke3/4; MCR2 prepends `65002 65002 65002` for Hub1/Spoke1/2); update GCP VXC BGP peer config `export_filter_list_id` → `export_policy_id`. `terraform apply -target` on 4 affected resources.
- Cost: **$0**. Apply: ~5 min + 90 s BGP reconvergence.

**P2: Cross-region GCP sessions (MCR2↔VPC-A CR + MCR1↔VPC-B CR)**
- Mitigates: F1-F4, F11 **Azure→GCP direction**. P1+P2 = full bidirectional failover. ⚠ Failover path goes Hub1→Hub2 hub-to-hub; AzFW2 is in path (not AzFW1): mid-session TCP flows reset.
- TF delta: 2 new `megaport_vxc` (MCR2→VPC-A CR; MCR1→VPC-B CR); 2 new `google_compute_router_peer`; Mech A-style export filters on each new session. `terraform apply -target` on 4 new resources.
- Cost: **+~$1/day**. Apply: ~10 min.

**P3: ER bow-tie (ER1↔Hub2 + ER2↔Hub1)**
- Mitigates: F5, F6 (ER GW failures). Hub-routing-preference `ExpressRoute` (v1 default) keeps bow-tie non-preferred in steady state.
- TF delta: 2 new `azurerm_express_route_gateway_connection` (`internet_security_enabled = true`). `terraform apply -target` on 2 resources.
- Cost: **+~$1/day**. Apply: ~15-20 min (RI re-propagation).

**After P1+P2+P3, residual unmitigated:** F7/F8 (AzFW failure: platform recovery only), F12/F13 (GCP CR: GCP-side action). No operator-automatable patch for these.

### 1.6.5 Demonstration captures: MCR1 SPOF (before P1+P2)

**Captured:** 2026-06-15T19:24:55+02:00 | **Topology:** rg-vwan-symm-103167 | **Constraint:** single-MCR-per-ER-GW maintained throughout (no bow-tie introduced).

#### Method

Phase A (steady-state route evidence) and Phase B (live data-plane tests) were executed on the live lab. **Phase C (active fault injection): Option 3 applied**: BGP-table-only analytical proof. Active MCR1 shutdown via Megaport API (Option 1) or `terraform destroy -target` (Option 2) was not performed because the AKV `platform-secrets-1138` is in `Deny` state; flipping the ACL requires explicit per-occurrence coordinator authorization (decisions.md 2026-06-15T10:15:00+02:00). The steady-state route map already provides irrefutable single-path proof; Trinity's §1.6 F-table (F1, F3, F11) is the formal analytical claim. No topology change was introduced.

Evidence files: `show-output/spof-before/` (11 files, created 2026-06-15T19:24:55+02:00).

#### Steady-state evidence

Path matrix (full table: `show-output/spof-before/00-path-matrix.md`):

| Source segment | Destination segment | Path observed | Single MCR in path? |
|---|---|---|---|
| spoke1 (hub1, swedencentral) | gcp-vpc-a (`10.50.1.0/24`) | hub1 → ER1 → MCR1 → GCP VPC-A | **YES: MCR1** |
| spoke1 (hub1, swedencentral) | gcp-vpc-b (`10.50.2.0/24`) | hub1 → hub2 (vWAN) → ER2 → MCR2 → GCP VPC-B | **YES: MCR2** |
| spoke3 (hub2, northeurope) | gcp-vpc-a (`10.50.1.0/24`) | hub2 → hub1 (vWAN) → ER1 → MCR1 → GCP VPC-A | **YES: MCR1** |
| spoke3 (hub2, northeurope) | gcp-vpc-b (`10.50.2.0/24`) | hub2 → ER2 → MCR2 → GCP VPC-B | **YES: MCR2** |

**Layer-by-layer summary:**

- **ER circuit route tables** (`show-output/spof-before/03-06`): ER1 (Stockholm) shows `10.50.1.0/24` via `169.254.150.121` / `169.254.150.125` (MCR1 primary/secondary MSEE peers, AS-path `65001 16550 ?`) and **no `10.50.2.0/24` entry**. ER2 (Amsterdam) shows `10.50.2.0/24` via MCR2 (`169.254.148.89` / `169.254.148.93`, AS-path `65002 16550 ?`) and **no `10.50.1.0/24` entry**. Mechanism A prefix filter is working: each prefix is reachable via exactly one MCR.
- **GCP Cloud Router status** (`show-output/spof-before/07-08`): Router-A (VPC-A, europe-west3, ASN 16550) has **one BGP peer only**: MCR1 at `169.254.159.194` (ASN 65001), status `Established`, 8 learned routes, advertising `10.50.1.0/24`. Router-B (VPC-B, europe-west4) has **one BGP peer only**: MCR2 at `169.254.87.242` (ASN 65002). No cross-region sessions exist.
- **Megaport VXC state** (`show-output/spof-before/09`): Three VXCs anchor on MCR1: `azure_circuit1` (LIVE, primary MSEE), `azure_circuit1_secondary` (CONFIGURED, secondary MSEE), `gcp_a` (LIVE, GCP VPC-A). All have `shutdown=false`. MCR1 failure simultaneously kills all three VXC BGP sessions.
- **vHub effective routes** (`show-output/spof-before/01-02`): CLI returns `{"value":[]}`: known Lab #1 anomaly documented in Niobe history (2026-06-15). MSEE route-table evidence (files 03-06) is the authoritative Azure-layer source.

#### Live connectivity (Phase B): `show-output/spof-before/10-connectivity-matrix-steady.md`

| Source | Destination | Result | Avg RTT | TTL |
|---|---|---|---|---|
| vm-spoke1 (`10.11.0.4`) | GCP VM A `10.50.1.2` | ✅ 0% loss | 85 ms | 59 |
| vm-spoke1 (`10.11.0.4`) | GCP VM B `10.50.2.2` | ✅ 0% loss | 149 ms | 58 |
| vm-spoke3 (`10.21.0.4`) | GCP VM A `10.50.1.2` | ✅ 0% loss | 118 ms | 58 |
| vm-spoke3 (`10.21.0.4`) | GCP VM B `10.50.2.2` | ✅ 0% loss | 66 ms | 59 |

TTL=58 for cross-region flows (spoke3→VPC-A, spoke1→VPC-B) vs TTL=59 for same-region flows: the extra hub-to-hub vWAN hop is visible in the TTL decrement.

#### During-fault evidence (Phase C: Option 3: analytical)

No active fault injection was performed (see Method above). The analytical claim, grounded in the steady-state route evidence:

When MCR1 fails (failure modes F1, F3, F11 from §1.6 F-table), all three VXCs anchored on MCR1 lose their BGP sessions simultaneously. ER1 loses both MSEE BGP sessions (primary peer `169.254.150.121` and secondary peer `169.254.150.125`). Hub1 withdraws `10.50.1.0/24` from its routing table. Hub2, which learned this prefix via the hub-to-hub vWAN link from Hub1, also withdraws it. Result: **all Azure spokes: across both hubs: lose reachability to GCP VPC-A (`10.50.1.0/24`)**.

Simultaneously, GCP Cloud Router A loses its only BGP peer (MCR1 at `169.254.159.194`). It withdraws all learned Azure routes, making GCP VPC-A instances unreachable to all Azure spokes from the GCP egress direction as well.

Expected connectivity matrix during MCR1 fault:

| Source | Destination | Expected during MCR1 fault |
|---|---|---|
| vm-spoke1 | GCP VM A `10.50.1.2` | ❌ FAIL: no route to `10.50.1.0/24` |
| vm-spoke1 | GCP VM B `10.50.2.2` | ✅ UNAFFECTED: MCR2/ER2 path intact |
| vm-spoke3 | GCP VM A `10.50.1.2` | ❌ FAIL: cross-hub path also lost |
| vm-spoke3 | GCP VM B `10.50.2.2` | ✅ UNAFFECTED: MCR2/ER2 path intact |

This matches Trinity §1.6 F1 exactly: "Hub1↔GCP VPC-A: TOTAL LOSS; Hub2↔GCP VPC-B: Unaffected."

#### Recovery evidence

No fault was injected, so no recovery sequence applies. When P1+P2 are applied by Tank, re-running Phase A and Phase B with MCR1 shutdown will demonstrate: (a) automatic BGP failover to MCR2 for GCP VPC-A prefixes (P1, Mechanism B), and (b) GCP VPC-A's Cloud Router gaining a cross-region peer via MCR2 (P2). Post-patch evidence should be captured in `show-output/spof-after/` (Niobe post-patch dispatch).

#### Conclusion

The v1 single-MCR-per-region Mechanism A design has a single-MCR SPOF per region. MCR1 failure cuts **all traffic to and from GCP VPC-A across both hubs**: there is no alternate path in the current topology. Spokes on both Hub1 (swedencentral) and Hub2 (northeurope) lose GCP VPC-A reachability simultaneously because Hub2's cross-region path also transits MCR1 via the hub-to-hub vWAN link. This is the unmitigated state that **P1 (Mechanism B swap) + P2 (cross-region GCP sessions) will fix** without changing the physical topology (no bow-tie introduced, single-MCR-per-ER-GW maintained per Jose's non-negotiable constraint).

> **Design.md budget note:** This file is currently 48.9 KB before this addition, already exceeding the 25 KB target. A compress dispatch to the coordinator is recommended before the next major section addition.

## 1.7 Three-layer route-collection plan

Niobe runs these commands and saves output under `labs/vwan-dual-er-symmetric/show-output/<NN>-<name>.txt`. Per charter: **always `-o json`** for `list-route-tables`; table format is empty.

Variables Tank exports at the top of Niobe's collect script (resolved at deploy time, never committed):

```bash
RG=rg-vwan-dual-er-symmetric-<run_id>
HUB1=hub1
HUB2=hub2
ER1_CIRCUIT=er1-<hub1_pop>     # e.g. er1-Madrid
ER2_CIRCUIT=er2-<hub2_pop>     # e.g. er2-Paris
HUB1_ERGW=hub1ergw
HUB2_ERGW=hub2ergw
HUB1_ER_CONN="hub1ergw-${HUB1_POP}"
HUB2_ER_CONN="hub2ergw-${HUB2_POP}"
SUB_ID=$(az account show --query id -o tsv)
API=2024-05-01                    # virtualwan REST api-version; tank bumps if needed
MCR1_UID=<filled-from-megaport>
MCR2_UID=<filled-from-megaport>
VXC1_UID=<filled-from-megaport>
VXC2_UID=<filled-from-megaport>
```

### Layer 1: Azure control plane (10 captures)

| # | What | Verbatim command |
|---|---|---|
| 01 | Resource inventory | `az resource list -g $RG -o table` |
| 02a | ER circuit 1 state | `az network express-route show -n $ER1_CIRCUIT -g $RG -o json` |
| 02b | ER circuit 2 state | `az network express-route show -n $ER2_CIRCUIT -g $RG -o json` |
| 03a | ER circuit 1 route table: primary | `az network express-route list-route-tables -n $ER1_CIRCUIT -g $RG --peering-name AzurePrivatePeering --path primary -o json` |
| 03b | ER circuit 1 route table: secondary | `az network express-route list-route-tables -n $ER1_CIRCUIT -g $RG --peering-name AzurePrivatePeering --path secondary -o json` |
| 03c | ER circuit 2 route table: primary | `az network express-route list-route-tables -n $ER2_CIRCUIT -g $RG --peering-name AzurePrivatePeering --path primary -o json` |
| 03d | ER circuit 2 route table: secondary | `az network express-route list-route-tables -n $ER2_CIRCUIT -g $RG --peering-name AzurePrivatePeering --path secondary -o json` |
| 04a | ER ARP: circuit 1 primary | `az network express-route list-arp-tables -n $ER1_CIRCUIT -g $RG --peering-name AzurePrivatePeering --path primary -o json` |
| 04b | ER ARP: circuit 1 secondary | `az network express-route list-arp-tables -n $ER1_CIRCUIT -g $RG --peering-name AzurePrivatePeering --path secondary -o json` |
| 04c-d | ER ARP: circuit 2 primary/secondary | (mirror of 04a/b, swap `$ER2_CIRCUIT`) |

**Known issue (vault [[Services/ExpressRoute]]):** `list-route-tables` can return `"Gateway does not have any Bgp sessions"` on a working circuit. If both 03a and 03c return that, capture verbatim and **continue**: confirm BGP state via 05 / 09 below instead.

### Layer 1b: vWAN hub effective routes + inbound/outbound (the symmetry gold): 12 captures

Use the REST API shape from `vwan_2xshub.azcli` lines 234-326. CLI wrapper `az network vhub get-effective-routes` exists but the REST path gives inbound/outbound views which are the symmetry-debugging gold.

For each hub `H` in {`hub1`, `hub2`}:

| # | What | Command |
|---|---|---|
| 05-H-a | Effective routes for `defaultRouteTable` | `az network vhub get-effective-routes --resource-type RouteTable --resource-id /subscriptions/$SUB_ID/resourceGroups/$RG/providers/Microsoft.Network/virtualHubs/${H}/hubRouteTables/defaultRouteTable -o json` |
| 05-H-b | Effective routes for the ER connection | `az network vhub get-effective-routes --resource-type ExpressRouteConnection --resource-id <ER conn id> -o json` |
| 05-H-c | **Inbound** routes for the ER connection (REST POST) | `az rest --method post --uri "https://management.azure.com/subscriptions/$SUB_ID/resourceGroups/$RG/providers/Microsoft.Network/virtualHubs/${H}/inboundRoutes?api-version=$API" --body '{"resourceUri":"<ER conn id>","connectionType":"ExpressRouteConnection"}'` (poll `Location` header per `get_async_routes` pattern) |
| 05-H-d | **Outbound** routes for the ER connection (REST POST) | Same URL with `/outboundRoutes`, same body. |
| 05-H-e | Effective routes for each VNet connection (Spoke1/2 under Hub1; Spoke3/4 under Hub2) | `az network vhub get-effective-routes --resource-type HubVirtualNetworkConnection --resource-id <vnet conn id> -o json`: one per spoke connection. |
| 05-H-f | Routing intent readback | `az rest --method get --uri "https://management.azure.com/subscriptions/$SUB_ID/resourceGroups/$RG/providers/Microsoft.Network/virtualHubs/${H}/routingIntent/intent${H}?api-version=$API"` |

Inbound/outbound REST pattern is the canonical symmetry view: "what is this ER conn telling the hub" vs "what is the hub telling this ER conn back."

### Layer 2: Megaport (4 captures per circuit + 2 per MCR)

| # | What | Command |
|---|---|---|
| 06a | MCR1 product JSON (generic endpoint) | `curl -sS -H "X-Auth-Token: $MEGAPORT_TOKEN" "$MEGAPORT_API_URL/v2/product/$MCR1_UID" \| jq .`: use generic `/v2/product/{uid}`; the `mcr2`-typed endpoint may 404 (vault gotcha). |
| 06b | MCR2 product JSON | Same with `$MCR2_UID`. |
| 07a | VXC1 (Azure-side, MCR1↔ER1) product JSON | `curl -sS -H "X-Auth-Token: $MEGAPORT_TOKEN" "$MEGAPORT_API_URL/v2/product/$VXC1_UID" \| jq '.data.resources.csp_connection[0].interfaces[0].bgpConnections'` |
| 07b | VXC2 (Azure-side, MCR2↔ER2) product JSON | Same with `$VXC2_UID`. |
| 08a | MCR1 looking-glass BGP | `curl -sS -H "X-Auth-Token: $MEGAPORT_TOKEN" "$MEGAPORT_API_URL/v2/product/mcr2/$MCR1_UID/diagnostics/routes/bgp"`: **expect 404** per [[Services/Megaport]]; if 404, capture the 404 verbatim and rely on 07a/b. |
| 08b | MCR2 looking-glass BGP | Same. |
| 09a | MCR1 → GCP BGP session detail | Pull the GCP-bound VXC's `bgpConnections` block (separate VXC UID, e.g. `$VXC1_GCP_UID`): use generic `/v2/product/{uid}`. |
| 09b | MCR2 → GCP BGP session detail | Same. |

### Layer 3: VM OS + NIC effective routes (4 VMs × 3 captures)

For each spoke VM `V` in {`vm-spoke1`, `vm-spoke2`, `vm-spoke3`, `vm-spoke4`}:

| # | What | Command |
|---|---|---|
| 10-V-a | NIC effective route table | `az network nic show-effective-route-table --ids <nic id of $V> -o json` |
| 10-V-b | NIC effective NSGs | `az network nic list-effective-nsg --ids <nic id of $V> -o json` |
| 10-V-c | OS-level `ip route` + traceroute | `az vm run-command invoke -g $RG -n $V --command-id RunShellScript --scripts 'ip addr; echo ---; ip route; echo ---; traceroute -n 10.50.1.10 || true; traceroute -n 10.50.2.10 || true; traceroute -n 10.21.0.4 || true'` (adjust target IPs to actual GCP / cross-region spoke VM IPs) |

### GCP-side (4 captures: Niobe runs via `gcloud`)

| # | What | Command |
|---|---|---|
| 11a | GCP CR BGP peers status | `gcloud compute routers get-status <router-name> --region=<gcp-region> --format=json` |
| 11b | GCP CR learned routes from MCR1 | `gcloud compute routers get-router-status <router> --region=<region> --format='value(result.bgpPeerStatus[?name=mcr1].advertisedRoutes)'` |
| 11c | GCP CR learned routes from MCR2 | Same, filter on `mcr2`. |
| 11d | GCP VM `ip route` + traceroute toward Spoke1/3 | `gcloud compute ssh <gcp-vm> --command='ip route; traceroute -n 10.11.0.4; traceroute -n 10.21.0.4'` |

**Total layer-coverage count:** 10 (L1) + 12 (L1b) + 8 (L2) + 12 (L3) + 4 (GCP) = **46 capture files** for full evidence. Worth it: symmetry can only be proven with both directions visible at every layer.

## 1.8 Validation checklist (Trinity → Niobe handoff)

Morpheus's manifest will define scenarios S1-S4 in detail. Trinity provides per-scenario assertions Niobe fills in. Standardized columns: `Assertion` / `Expected` / `Result (PASS/FAIL)` / `Evidence path (relative to labs/vwan-dual-er-symmetric/)`.

### Scenario 1: Vanilla dual-ER bringup (no symmetry stress yet)

| Assertion | Expected | Result | Evidence |
|---|---|---|---|
| Both ER circuits show `serviceProviderProvisioningState=Provisioned` | Provisioned | | `show-output/02a-er-circuit-show.txt`, `02b-` |
| Both MCR↔ER BGP sessions are up (primary + secondary per circuit = 4 sessions) | `bgpState=Established` ×4 | | `07a-vxc-primary.txt`, `07b-vxc-secondary.txt` |
| Each MCR↔GCP BGP session is up | `Established` ×2 | | `09a-mcr1-gcp-bgp.txt`, `09b-mcr2-gcp-bgp.txt` |
| Routing intent active on both hubs | `provisioningState=Succeeded`, `policies[0].destinations=["PrivateTraffic"]`, `nextHop=<firewall id>` | | `05-hub1-f-routingintent.txt`, `05-hub2-f-routingintent.txt` |

### Scenario 2: Per-region prefix affinity (Mechanism A in effect)

| Assertion | Expected | Result | Evidence |
|---|---|---|---|
| **S2.1** Spoke1 VM NIC effective route to `10.50.1.0/24` exists, next-hop is **Hub1 firewall private IP** (not the ER GW directly). | `nextHopType=VirtualAppliance`, `nextHopIpAddress=<hub1 fw private IP>` | | `10-vm-spoke1-a-nic-effective.txt` |
| **S2.2** Hub1 `defaultRouteTable` effective routes for `10.50.1.0/24` show next-hop `<hub1 fw>` and AS-path indicating `12076 → 65001 → 65003`. | matches | | `05-hub1-a-defaultRT.txt` |
| **S2.3** Hub1 **inbound** routes on ER conn for `10.50.1.0/24` are present; Hub1 **outbound** routes on ER conn include Hub1+Spoke1+Spoke2 prefixes. | inbound has GCP prefixes; outbound has all Azure prefixes (hub-to-hub propagation visible). | | `05-hub1-c-inbound.txt`, `05-hub1-d-outbound.txt` |
| **S2.4** Spoke3 VM effective route to `10.50.1.0/24` shows next-hop **Hub2 firewall** (NOT Hub1 firewall via hub-to-hub). | `nextHopIpAddress=<hub2 fw>` | | `10-vm-spoke3-a-nic-effective.txt` |
| **S2.5** GCP CR has `10.11.0.0/24` (Spoke1) learned **only via MCR1**, not via MCR2 (filter working). | `bgpPeerStatus[mcr1].advertisedRoutes` includes `10.11.0.0/24`; `bgpPeerStatus[mcr2].advertisedRoutes` does **not**. | | `11b-gcp-cr-routes-from-mcr1.txt`, `11c-gcp-cr-routes-from-mcr2.txt` |
| **S2.6** Symmetric path proof: Spoke1 → GCP-VM traceroute exits via Hub1 firewall → Hub1 ER GW → MCR1 → GCP CR. Return: GCP-VM → Spoke1 traceroute enters via MCR1 → Hub1 ER GW → Hub1 firewall → Spoke1 VM. Both sides traverse the **same firewall (Hub1)**. | matches | | `10-vm-spoke1-c-os.txt`, `11d-gcp-vm-os.txt` |

### Scenario 3: Spoke1 ↔ Spoke3 cross-region (no ER involvement)

| Assertion | Expected | Result | Evidence |
|---|---|---|---|
| **S3.1** Forward path: Spoke1 VM → Spoke3 VM traceroute shows next-hop Hub1 firewall, then Hub2 firewall, then Spoke3. | 2 firewall hops visible | | `10-vm-spoke1-c-os.txt` |
| **S3.2** Return path: Spoke3 VM → Spoke1 VM traceroute shows next-hop Hub2 firewall, then Hub1 firewall, then Spoke1. **Reverse order of the same two firewalls.** | 2 firewall hops, reversed | | `10-vm-spoke3-c-os.txt` |
| **S3.3** Neither firewall logs an "asymmetric flow / out-of-state TCP" drop during a 30-second curl test. | 0 drops in fw logs | | (Azure Firewall log query: Niobe scripts) |

### Scenario 4: AS-PATH prepend fallback (Mechanism B)

Tank toggles config (drop filters, add prepend policies on MCR). Re-collect. Expect:

| Assertion | Expected | Result | Evidence |
|---|---|---|---|
| **S4.1** GCP CR sees `10.11.0.0/24` learned via BOTH MCRs, but MCR2's advertisement has prepended AS-path `65002 65002 65002 65001 12076`. | both sessions advertise; AS-path lengths differ. | | `11b-`, `11c-` (re-captured) |
| **S4.2** GCP CR best-path for `10.11.0.0/24` is via MCR1. | matches | | `gcloud compute routers get-status ... best=true` filter |
| **S4.3** Forward + return paths for Spoke1↔GCP still hit Hub1 firewall both directions. | symmetric | | re-run S2.6 evidence |
| **S4.4** **Failure simulation:** disable MCR1↔ER1 VXC (admin-down). GCP CR re-converges to MCR2's longer-AS-path advertisement. Spoke1↔GCP still works (now via Hub2 firewall: asymmetric on the Azure side now, but firewall is consistent within each direction). | failover within ≤ BGP hold-time | | (capture pre/post `gcloud get-status`) |

### Patch validation captures (Niobe runs after Tank applies each patch)

| Patch | What to re-capture | Pass criterion |
|-------|-------------------|----------------|
| P1 (Mech B swap) | Re-run `11b-gcp-cr-routes-from-mcr1`, `11c-gcp-cr-routes-from-mcr2`; re-run S2.6 traceroute | Both MCRs advertise all Azure prefixes; MCR2's Hub1 prefixes have longer AS-path; symmetry preserved |
| P2 (cross-region GCP sessions) | Capture `09a/09b` for new VXC BGP state; re-capture `11b`, `11c` for both VPC CRs; `gcloud compute routers get-status` VPC-A and VPC-B | 4 BGP sessions up; each VPC CR sees both Hub1 and Hub2 prefixes; Spoke1 reaches GCP VPC-A after simulated MCR1 down |
| P3 (ER bow-tie) | Re-run `05-hub1-a-defaultRT`, `05-hub2-a-defaultRT`; admin-disable ER1 (TF), re-capture effective routes | Bow-tie paths non-preferred in steady state; after ER1 down, Hub2 carries Hub1 prefixes via bow-tie |

## 1.9 Failure-mode design notes

Trinity calls these out **before** Tank deploys, not after Niobe finds them.

1. **MTU on hub-to-hub**: vWAN's hub-to-hub link runs at 1400 bytes (Microsoft-managed; not user-tunable). If a workload needs 1500 end-to-end, the firewall TCP-MSS-clamps; UDP/ICMP fragment. For lab VM traffic this is invisible (SSH, curl small payloads).
2. **SNAT exhaustion**: Azure Firewall in vWAN hub has limited SNAT ports per backend instance (~2k/instance). For lab traffic levels (a few flows), non-issue. If a follow-up lab tries throughput tests, this will bite: capture as a vault note then.
3. **`AzureLoadBalancer` source-IP gotcha**: N/A in v1 (no LB in path). Listed here so a future "add ILB in front of NVA" follow-up doesn't surprise anyone.
4. **BGP convergence wait**: after any MCR-side filter or prepend change, wait **≥ 90 seconds** before re-collecting. Megaport's MCR BGP timers are stock (keepalive 30s, hold 90s). For routing-intent rollouts, wait **10-20 minutes**: provisioning is async and Azure does not surface progress on the `intent$1` resource until terminal state. Per `vwan_2xshub.azcli:221` (`wait_until_finished_rest`).
5. **`list-route-tables` false negative**: already in vault [[Services/ExpressRoute]]. If both circuits return "no BGP sessions", treat as CLI bug, confirm via vNet-gateway-equivalent (here: `az network vhub get-effective-routes` for the ER conn and the VXC `bgpConnections` blob).
6. **Megaport shared VLAN observation (lab #1)**: both primary and secondary VXCs of lab #1 used VLAN 100. Whether this repeats on a multi-circuit deploy is unknown: Niobe should record VLAN tags per VXC in 07a/b so vault [[Services/Megaport]] gets an updated data point.
7. **Routing intent + private endpoints SNAT Q&A**: vault [[Patterns/Virtual-WAN]] Welly Lee note says **keep SNAT enabled** when PE is in spoke. This lab has no PE in v1. Listed so Tank doesn't blindly disable SNAT (some Terraform templates default disable).
8. **Hub-routing-preference default vs ASPath**: vault [[Services/Azure-Virtual-WAN]] PG note (2026-05-26) gives Route Maps + public-ASN prepend as the official way to influence path. We use the **MCR-side** prepend (Mechanism B) to avoid MSEE stripping. Do **not** add vWAN route maps in v1.
9. **Same firewall ASN in both hubs (65520)**: vWAN-internal only, not exposed externally. No BGP collision risk. Noted because someone reading the design will ask "won't two ASN-65520 firewalls collide over hub-to-hub?": answer: hub-to-hub is not BGP, it's vWAN-managed forwarding state.
10. **Cleanup chain implication**: Mechanism A's per-region filters live as separate Megaport resources. Tank's `terraform destroy` removes them with the MCRs; no manual cleanup step. If the lab is ever split (separate state files), the filters must be destroyed before the MCRs (Megaport may 409 otherwise).

---

## Key Vault secret inventory

Probed `platform-secrets-1138` (RG `platform`, location `swedencentral`, SKU Standard, **RBAC mode**, `publicNetworkAccess=Enabled` but `networkAcls.defaultAction=Deny` with `bypass=None` and a single IP allow-rule for Jose's dev machine). Caller (Jose) confirmed has `get` permission; all three secrets read successfully.

| Secret name | Present? | Used by | Notes |
|---|---|---|---|
| `megaport-api-key` | **yes** (updated 2026-04-27) | Terraform Megaport provider (`access_key`) | Stable. |
| `megaport-api-secret` | **yes** (updated 2026-04-27) | Terraform Megaport provider (`secret_key`) | Stable. |
| `default-password` | **yes** (updated 2026-06-15) | VM admin password: **primary** auth for all four Linux lab VMs (password auth, no SSH key). Also covers Windows lab VMs if any are added. | Jose's Phase 4 approval locked VM auth to password-only. Tank wires this to `admin_password` on all VM resources; no `vm-admin-ssh-public-key` secret is used or expected. |

**Locked secret inventory (Phase 4 approval):** exactly **3 secrets**: `megaport-api-key`, `megaport-api-secret`, `default-password`. No `vm-admin-ssh-public-key` (password auth only). No `gcp-service-account-json` (GCP auth uses out-of-band `gcloud` CLI: see operator pre-deploy checklist above).

**KV access correction (vs lab #1's manifest):** lab #1 §8 said `platform-secrets-1138` is "private-link only and unreachable from the dev machine." Empirical probe today shows: the vault is **public-network-access-Enabled with default-deny IP rules and a single allowlisted dev-machine IP** (not private-link only). Jose's dev machine resolves + authenticates fine; the Terraform `azurerm_key_vault_secret` data-source pattern is therefore viable for lab #2. (This finding goes into Trinity history + vault backfill at lab close.)

### ⚠️ Operator guidance: Microsoft Global Secure Access (GSA) + KV firewall ACL interaction

**Problem.** When the Microsoft Global Secure Access (GSA) client is running on Jose's dev machine (or any operator's machine), the egress IP that hits the KV is **not** the machine's normal public IP: it's a GSA-fronted IP that is **not** in the KV's `networkAcls.ipRules` allowlist. Result: `az keyvault secret list` / `secret show` returns HTTP **403** with `"Client address is not authorized to access this server"` (or similar wording: the exact error string varies between CLI versions).

**This bites Tank's `terraform plan/apply`** too: `data.azurerm_key_vault_secret.megaport_api_key.value` will fail the same way as the raw CLI, because the AzureRM provider goes through the same data-plane endpoint. **Tank must apply one of the two workarounds below before running plan/apply when GSA is active.** This is standing operator guidance, not a one-off Trinity workaround.

**Diagnostic signature (recognize before reacting).** Any of:
- `Caller is not authorized to perform action on resource. ... Client address is not authorized to access this server.`
- `(Forbidden) Client address is not authorized and caller was ignored because bypass is set to None ... Inner error: { "code": "ForbiddenByFirewall" }`
- `403 Client Error: Forbidden for url: https://platform-secrets-1138.vault.azure.net/secrets/...`
- Terraform: `Error: reading Key Vault Secret ... 403`

Confirm by capturing the current external IP via `curl -sS https://api.ipify.org` from the same shell that hit the 403; if it doesn't match the IP listed in `networkAcls.ipRules`, the network ACL is the cause (vs. RBAC, which would say "does not have secrets get permission").

**Empirical detail confirmed live during this design pass (2026-06-15):** GSA-fronted egress IPs are **dynamic per-call**: three consecutive `az keyvault secret show` calls from the same shell logged three different `Client address` values in the 403 (`98.71.102.121` → `98.71.102.193` → `98.71.102.132`). This means **"just add my current GSA IP to `ipRules`" is not a fix**: the next call gets a different IP. The only viable workarounds are Path A (pause GSA so the dev machine's real IP is used) or Path B (temporarily relax `defaultAction`). Do **not** attempt to maintain a static GSA-IP allowlist.

**Always-first step: snapshot the current `networkAcls` so we can restore exact state.**

```powershell
az keyvault show -n platform-secrets-1138 -o json | ConvertFrom-Json |
  Select-Object -ExpandProperty properties |
  Select-Object publicNetworkAccess, networkAcls |
  ConvertTo-Json -Depth 6 |
  Out-File -FilePath .\kv-acl-snapshot-$(Get-Date -Format yyyyMMdd-HHmmss).json
```

Current known-good snapshot at design time (2026-06-15):

```json
{
  "publicNetworkAccess": "Enabled",
  "networkAcls": {
    "bypass": "None",
    "defaultAction": "Deny",
    "ipRules": [{ "value": "<operator-public-ip>/32" }],
    "virtualNetworkRules": []
  }
}
```

#### Path A (preferred: least KV surface change): Jose disables GSA briefly

1. Jose: pause / disconnect the GSA client on the dev machine.
2. Re-run the failed operation (`az keyvault secret show ...` or `terraform plan`).
3. Jose: re-enable GSA.

**Why preferred:** zero change to the KV resource. No risk of accidentally leaving the network ACL in a relaxed state. The GSA pause window is operator-local and short (seconds to minutes).

#### Path B (when Path A isn't possible): temporarily relax `defaultAction`

**Do NOT silently flip the ACL even if you have permissions. Always snapshot first.**

```bash
# 1) Snapshot the current state: capture this BEFORE the flip
az keyvault show -n platform-secrets-1138 --query networkAcls -o json > kv-acl-before.json

# 2) Relax to Allow (data-plane becomes reachable from any IP for the duration)
az keyvault update -n platform-secrets-1138 --default-action Allow

# 3) Run the operation that needed KV access (CLI fetch OR terraform plan/apply that has data.azurerm_key_vault_secret references)
terraform plan   # or az keyvault secret show ...

# 4) IMMEDIATELY restore to the snapshotted state: do not defer
az keyvault update -n platform-secrets-1138 --default-action Deny

# 5) Verify the post-state matches the snapshot
az keyvault show -n platform-secrets-1138 --query networkAcls -o json > kv-acl-after.json
# diff kv-acl-before.json kv-acl-after.json   # should match exactly
```

**Risks of Path B:** while `defaultAction=Allow` is in effect, the KV is reachable from any internet IP that has data-plane RBAC on it. Keep the window as short as possible. If interrupted mid-sequence, immediately re-run step 4: don't leave the vault in `Allow` state.

#### Tank-deploy-time hook

Tank's deploy script must:
1. Probe KV reachability with a no-op `az keyvault secret list --vault-name platform-secrets-1138 --maxresults 1 -o none`.
2. If exit code 0 → proceed with `terraform apply`.
3. If exit code non-zero with 403 in stderr → stop, surface to Jose with both Path A and Path B options, **do not silently flip the ACL**, wait for Jose's explicit pick.
4. Whichever path Jose chooses, Tank logs the chosen path + before/after ACL snapshots into `labs/vwan-dual-er-symmetric/deploy/kv-access.log` (gitignored: secrets-adjacent diagnostic).

This same hook applies to Tank's cleanup step (Terraform may re-read secrets at destroy time).

### Terraform data-source pattern Tank uses

```hcl
data "azurerm_key_vault" "platform_secrets" {
  name                = "platform-secrets-1138"
  resource_group_name = "platform"
}

data "azurerm_key_vault_secret" "megaport_api_key" {
  name         = "megaport-api-key"
  key_vault_id = data.azurerm_key_vault.platform_secrets.id
}
data "azurerm_key_vault_secret" "megaport_api_secret" {
  name         = "megaport-api-secret"
  key_vault_id = data.azurerm_key_vault.platform_secrets.id
}
data "azurerm_key_vault_secret" "default_password" {
  name         = "default-password"
  key_vault_id = data.azurerm_key_vault.platform_secrets.id
}

provider "megaport" {
  access_key            = data.azurerm_key_vault_secret.megaport_api_key.value
  secret_key            = data.azurerm_key_vault_secret.megaport_api_secret.value
  environment           = "production"
  accept_purchase_terms = true
}

# default-password is wired to all four Linux lab VM resources as admin_password.
# Password auth is the primary (and only) VM auth method for this lab: no SSH key secret used.
```

**RBAC role required on the KV:** `Key Vault Secrets User` (read): Jose already has it (verified). If Tank runs deploy under a different principal (e.g., a service principal in CI), that principal must be assigned the same role at the KV scope:

```bash
az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee <principal-object-id> \
  --scope "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/platform/providers/Microsoft.KeyVault/vaults/platform-secrets-1138"
```

**Network ACL note for Tank:** `networkAcls.defaultAction=Deny`, `bypass=None`. Tank deploys from Jose's dev machine (one allowlisted IP). If a CI runner ever runs `terraform plan/apply`, Tank must add the runner's egress IP to the KV firewall first **or** wire the runner to a VNet with a Private Endpoint to the KV. GSA-on-dev-machine path is the more common case today: see operator guidance above.

---

## Spec handoff

This document is the Phase 3.1 networking design spec. **Tank** translates it into Terraform per Morpheus's IaC-choice direction. **Niobe** runs the Layer 1 / 1b / 2 / 3 capture commands and fills the S1-S4 validation tables. **Oracle** draws topology + control-plane + symmetric-data-plane + cleanup-chain diagrams; the per-region affinity arrow from MCR to GCP is the headline visual.

Trinity does not author IaC, does not run validation, does not draw the diagrams. Trinity is on standby for: (a) reviewing Tank's Terraform before deploy (per routing rule); (b) interpreting any anomalous BGP capture Niobe surfaces; (c) backfilling the vault post-validation pre-cleanup (per Rule #15).

---

## 2. Design B: Single-VPC GCP-as-on-prem (single shared VPC with GLOBAL routing)

> ⚠️ **Superseded by Design C as of 2026-06-15.** Design B Phase 1 remains deployed and serves as the asymmetric-evidence baseline for Niobe-4 and niobewsl captures. Do not re-apply or modify Design B TF until Jose gates Design C.

**Authored:** 2026-06-15 | **Status:** DEPLOYED (Phase 1). Superseded as primary design target.

### 2.1 Topology delta

| Component | Design A | Design B |
|---|---|---|
| GCP VPCs | 2: vpc_a (eu-w3, REGIONAL) + vpc_b (eu-w4, REGIONAL) | 1: vpc_onprem (vpc_a renamed, GLOBAL) |
| Subnets | 10.50.1.0/24 in vpc_a; 10.50.2.0/24 in vpc_b | Both in vpc_onprem: eu-w3 10.50.1.0/24 (existing) + eu-w4 10.50.2.0/24 (new) |
| Cloud Routers | router_a (eu-w3/vpc_a) + router_b (eu-w4/vpc_b); ASN 16550 each | router_a (eu-w3/vpc_onprem, unchanged) + cr_onprem_b (eu-w4/vpc_onprem, NEW); ASN 16550 |
| Attachments | att_a (vpc_a/router_a) + att_b (vpc_b/router_b) | att_a unchanged; att_b DESTROY+RECREATE on cr_onprem_b |
| GCP VMs | vm-a eu-w3-a; vm-b eu-w4-a in vpc_b | vm-a unchanged; vm-b lift-and-shift → vpc_onprem eu-w4 subnet |
| Cross-region VXCs | None | None: GLOBAL VPC routing is the cross-region fabric |
| CR advertise mode | CUSTOM, one subnet each | CUSTOM, **both** GCP subnets each (native + remote via GLOBAL routing) |
| Redundancy | F9/F10 only | All single MCR/CR/VXC failures → ⚠️ degraded (auto-failover) |

**Azure + Megaport: ZERO change.** 4 Azure VXCs, 2 MCRs, 2 ER circuits, 2 hubs, 2 AzFWs, 4 spokes untouched.

**NEW: MCR→Azure GCP-prefix prepend (Axis 2):** With both CRs advertising both subnets, Azure needs a tiebreaker. MCR1 prepends 10.50.2.0/24 3× toward Hub1 (Hub1 prefers Hub2/MCR2 for VM-B). MCR2 prepends 10.50.1.0/24 3× toward Hub2 (symmetric). Added to Azure-side VXC BGP peer config. No new VXC resources.

### 2.2 Resiliency analysis: F-table for Design B

**Legend:** ✅ protected / ⚠️ degraded (30-90 s BGP reconvergence; TCP resets) / ❌ lost

| # | Failure | Hub1↔VM-A | Hub1↔VM-B | Hub2↔VM-A | Hub2↔VM-B |
|---|---|---|---|---|---|
| F-A | MCR1 down | ⚠️ | ⚠️ | ⚠️ | ✅ |
| F-B | MCR2 down | ✅ | ⚠️ | ⚠️ | ⚠️ |
| F-C | CR-A down | ⚠️ | ⚠️ | ⚠️ | ✅ |
| F-D | cr_onprem_b down | ✅ | ⚠️ | ⚠️ | ⚠️ |
| F-E | VXC gcp_a/gcp_b down | ⚠️ | ⚠️ | ⚠️ | ✅ (if gcp_a down) |
| F-F | Region-A entirely down | ❌ (VM-A physically down) | ⚠️ | ❌ | ✅ |

Design A equivalent: F-A through F-E = ❌ TOTAL LOSS. Design B = ⚠️ auto-failover (no cross-region VXC). F-F physical down is the only ❌ in B: not a routing problem.

**MCR1 down: GCP routing:** VM-A loses CR-A (MCR1 withdrawn). VPC retains Hub1 routes via CR-B (MCR2's Mechanism B prepend advertisement). VM-A re-converges to CR-B path within ~90 s. Azure→VM-A: MCR2 still advertises 10.50.1.0/24 (from CR-B via GLOBAL VPC) to Hub2 → Hub1 learns via hub-to-hub. **Confirmed: GLOBAL routing provides bidirectional failover equivalent to P1+P2 without cross-region VXCs.**

**Convergence:** GCP hold-timer 90 s + Azure BGP reconvergence 30-90 s = ~2-3 min worst case.

**Cross-region FW asymmetry [Niobe S2.7 required]:** VM-B→Hub1 egresses via CR-A→MCR1 (GCP prefers shorter AS-path for Hub1 prefixes); Hub1→VM-B routes via Hub2→MCR2→CR-B (MCR1 prepend 3× on 10.50.2.0/24). Both directions traverse AzFW1+AzFW2 but in different order per direction. Azure Firewall in vWAN with routing-intent may handle gracefully. **Niobe S2.7 must validate live TCP (Spoke1↔VM-B, Spoke3↔VM-A) with zero FW drops before Design B is declared production-equivalent.**

### 2.3 Symmetry mechanism: 4-quadrant matrix

Mechanism B retained. Prepend in two axes: Axis 1 = MCR→GCP (existing); Axis 2 = MCR→Azure for GCP subnets (new).

| Flow (steady state) | GCP→Azure | Azure→GCP | FW(s) | Symmetric? |
|---|---|---|---|---|
| VM-A → Hub1 | CR-A→MCR1→ER1→Hub1 | Hub1→MCR1→CR-A→VM-A | AzFW1 | ✅ |
| VM-B → Hub2 | CR-B→MCR2→ER2→Hub2 | Hub2→MCR2→CR-B→VM-B | AzFW2 | ✅ |
| VM-A → Hub2 | CR-B→MCR2→Hub2 | Hub2→h2h→Hub1→MCR1→CR-A→VM-A | AzFW2+AzFW1 | ⚠️ [S2.7] |
| VM-B → Hub1 | CR-A→MCR1→Hub1 | Hub1→h2h→Hub2→MCR2→CR-B→VM-B | AzFW1+AzFW2 | ⚠️ [S2.7] |

**MCR1 down failover:** VM-A uses CR-B (Hub1 prefixes with 3× prepend, only path). Hub1→VM-A switches to Hub2→MCR2 path. Both directions now traverse AzFW2. Mid-session flows reset; new flows symmetric on AzFW2. ⚠️

### 2.4 Patch spec for Tank

**Carry-forward:** `correlation_id_override="103167"` and `password_override` unchanged in tfvars.

| Op | Resource |
|---|---|
| **DESTROY** | `google_compute_instance.vm_b`, `google_compute_interconnect_attachment.att_b`, `google_compute_router.router_b`, `google_compute_subnetwork.vpc_b_subnet`, `google_compute_firewall.vpc_b_allow`, `google_compute_network.vpc_b` |
| **MODIFY** | `google_compute_network.vpc_a` routing_mode REGIONAL→GLOBAL; `google_compute_router.router_a` bgp.advertised_ip_ranges add 10.50.2.0/24; `megaport_vxc.gcp_b` pairing_key→att_b_new.pairing_key (in-place); add Axis-2 prepend to `megaport_vxc.azure_circuit1` (10.50.2.0/24 3×) and `azure_circuit2` (10.50.1.0/24 3×) |
| **CREATE** | `google_compute_subnetwork.vpc_onprem_subnet_b` (eu-w4, 10.50.2.0/24); `google_compute_router.cr_onprem_b` (eu-w4, ASN 16550, CUSTOM both subnets); `google_compute_interconnect_attachment.att_b_new` (eu-w4/cr_onprem_b, PARTNER, DOMAIN_1); `google_compute_instance.vm_b` (eu-w4-a, vpc_onprem_subnet_b); extend firewall rule to cover eu-w4 traffic |
| **LIFT-AND-SHIFT** | vm-b: same startup script, same subnet CIDR (10.50.2.0/24), new VPC. IP 10.50.2.2 likely preserved but not pinned: Niobe re-captures post-apply. |

**Megaport:** `gcp_a` VXC = ZERO CHANGE (att_a pairing_key unchanged if vpc_a routing_mode is in-place). `gcp_b` VXC = in-place re-pair only (not destroy).

**Plan-show gate (mandatory):**
```powershell
terraform plan -out=tfplan
terraform show tfplan | rg '(will be destroyed|must be replaced)'
```
Pass: only GCP resources listed above. **Any `azurerm_*` or MCR in destroy = STOP, escalate to Trinity.**

### 2.5 Migration safety

| Question | Finding |
|---|---|
| `vpc_a` routing_mode REGIONAL→GLOBAL: in-place or ForceNew? | **Likely in-place**: GCP API supports PATCH on `routingConfig.routingMode`; GCP provider 4.x+ does not mark ForceNew. **Tank must confirm with `terraform plan`**: if `-/+` appears, create `vpc_onprem` fresh (two-phase: create-then-destroy). If in-place: att_a pairing_key preserved, gcp_a VXC untouched. If ForceNew: full cascade (att_a + vm_a + router_a destroyed → gcp_a VXC re-pair too). |
| Can `att_b` be transferred to a different Cloud Router? | **NO**: GCP hard constraint. att_b bound to router_b at creation. Must destroy+recreate on cr_onprem_b. New pairing_key. `megaport_vxc.gcp_b` re-paired in-place (not destroyed). Brief BGP disruption. |
| VM-B IP post-migration? | 10.50.2.2 expected but not guaranteed. Do not hardcode in validation commands. |
| att_a pairing_key? | Unchanged if routing_mode in-place. `megaport_vxc.gcp_a` needs zero Megaport writes. ✅ |

### 2.6 Verdict

Design B eliminates P2 (cross-region VXCs) from Design A's patch catalogue: the single GLOBAL-routing VPC is itself the cross-region fabric, giving automatic bidirectional failover for all single MCR/CR/VXC failures at zero additional Megaport cost. For Niobe's README `## Designs studied`: **Design B replaces Design A's two isolated REGIONAL VPCs with a single GLOBAL-routing VPC, achieving automatic bidirectional failover for all single-component failures without cross-region Megaport circuits; the mandatory trade-off is destroying vpc_b, recreating att_b (new pairing_key), and adding a second prepend axis on the MCR→Azure GCP-prefix advertisements. Design A's `spof-before/` evidence is the "no-failover" baseline; Design B's `spof-after/` evidence will demonstrate the improvement.**

---

## 3. Design C: Single-CR GCP-as-on-prem ("real on-prem router with two WAN uplinks")

**Authored:** 2026-06-15 | **Status:** Spec-only. Blocked on Megaport unlock (Q1 below). No IaC changes until Jose gates.

### 3.1 Rationale

Jose's directive (verbatim): *"I would like to collapse both CRs into the same region, and even the same CR. Even if we lose redundancy, it is a closer simulation to an onprem environment where a single onprem DC connects to two different circuits. There is no redundancy to the onprem DC, the redundancy starts at the Megaport layer."*

**The pedagogical reframe: what Design C reveals:**

Design B hides a layer of routing magic: each GCP VM naturally preferred its region-local Cloud Router (VM-A co-located with CR-A in eu-w3; VM-B with CR-B in eu-w4). The two CRs each saw only one BGP peer, so there was no best-path selection at the GCP layer: routing was pre-determined by geography. The BGP work happened at the MCR and Azure vHub layers, but GCP itself was a passive forwarder.

Design C collapses to **one Cloud Router with two PARTNER Interconnect attachments**: one to MCR1, one to MCR2. That single CR now performs BGP best-path selection across both uplinks, exactly as a real on-prem router would. The narrative arc becomes:

| Stage | GCP BGP behavior | Azure BGP behavior | Blog value |
|---|---|---|---|
| Design A | 2 CRs, 1 peer each: no best-path selection at GCP | 2 ER GWs, 2 MCRs | Baseline |
| Design B | 2 CRs, 1 peer each: still no best-path at GCP, geography hides it | Same | Transition |
| **Design C** | **1 CR, 2 peers: FULL best-path selection at GCP** | Same | **Lab centerpiece** |
| Design C + Mech C | Same | vHub Route Maps add Azure-layer symmetry control | Finale |

Design C is the point where BGP best-path selection is visible at all three layers simultaneously (GCP CR, Megaport MCR, Azure vHub).

### 3.2 Target topology

```
vpc_a (GLOBAL routing)
│
├── subnet eu-w3  10.50.1.0/24
│   └── vm_a  10.50.1.2
│
├── subnet eu-w4  10.50.2.0/24    [TBD-Jose Q3: keep or collapse]
│   └── vm_b  10.50.2.2
│
└── Cloud Router "cr_onprem"  ← SINGLE CR, region = TBD-Jose (Q2)
    ASN 16550 (GCP PARTNER Interconnect requirement)
    ├── att_a  (PARTNER, DOMAIN_1) ──VXC gcp_a──► MCR1 ASN 65001
    └── att_b_v2  (PARTNER, DOMAIN_2) ──VXC gcp_b──► MCR2 ASN 65002
```

**DOMAIN split:** Use `AVAILABILITY_DOMAIN_1` for att_a and `AVAILABILITY_DOMAIN_2` for att_b_v2. Two attachments on the same CR in the same region must use different availability domains: GCP constraint for PARTNER type.

**Delta from Design B (deployed):**

| Resource | Design B state | Design C action |
|---|---|---|
| `router_a` (eu-w3) | exists | Keep OR rename to `cr_onprem` (TBD-Jose Q2) |
| `cr_onprem_b` (eu-w4) | exists | **DESTROY** |
| `att_a` (eu-w3 / router_a) | exists | Keep (if consolidated region = eu-w3) OR destroy+recreate in eu-w4 |
| `att_b_new` (eu-w4 / cr_onprem_b) | exists | **DESTROY**: recreate in consolidated region on single CR |
| `megaport_vxc.gcp_b` | paired to att_b_new | **Re-pair** to new att_b_v2 pairing_key: requires Megaport portal/API (BLOCKED) |
| `megaport_vxc.gcp_a` | paired to att_a | No change if eu-w3 is consolidated region; re-pair if eu-w4 chosen |
| `vm_b` | eu-w4-a | Keep in place (TBD-Jose Q3) |

### 3.3 Open questions for Jose

| # | Question | Options | Trinity recommendation (awaiting Jose confirmation) |
|---|---|---|---|
| Q1 | Megaport portal/API unlock status? | (a) Unlocking shortly: proceed with Design C spec; (b) Abandoning Megaport: pivot to Design D; (c) Unknown timeline | TBD-Jose. If >48 h delay, recommend Design D (keeps lab moving). |
| Q2 | Consolidated region for single CR? | (a) eu-w3: keep att_a pairing_key → gcp_a VXC unchanged; only att_b_new moves → 1 re-pair | (b) eu-w4: move att_a → both VXCs re-paired | **Rec: eu-w3.** Less churn: only gcp_b VXC re-paired. att_a and gcp_a VXC unchanged. Niobe-2 evidence was collected against eu-w3 infrastructure. |
| Q3 | VM topology post-Design C? | (a) Keep both VMs in current regions (eu-w3 + eu-w4): cross-region routing is more interesting pedagogically; (b) Collapse both VMs to consolidated region: true single-DC simulation | **Rec: keep both.** Two VMs in different regions makes the single-CR routing decision visible: both VMs use the same exit CR, but their return paths differ by hub (AS-path decides). If both VMs collapse to eu-w3, the blog story is simpler but less interesting. |
| Q4 | Fallback if Megaport stays locked? | (a) Leave Design B as-is, capture evidence, close lab; (b) Design D (Linux NVA, see §3.7): no Megaport change required | **Rec: Design D** if Q1 stays blocked >48 h. Design D is independently interesting and avoids the Megaport unlock dependency entirely. |

### 3.4 Migration plan from Design B (assuming eu-w3 consolidated, both VMs kept, Megaport unlocked)

**Precondition:** Megaport portal/API accessible. VXC re-pair requires pairing_key update on gcp_b.

**Ordered steps:**

| Step | Action | Tool | Notes |
|---|---|---|---|
| 1 | `terraform destroy -target google_compute_interconnect_attachment.att_b_new` | TF | Kills BGP session MCR2↔CR-B. Brief loss of MCR2→GCP path. |
| 2 | `terraform destroy -target google_compute_router.cr_onprem_b` | TF | Removes eu-w4 CR. |
| 3 | `terraform apply`: create `att_b_v2` in eu-w3, DOMAIN_2, on `router_a` | TF | New pairing_key generated. BGP not yet up on MCR2 side. |
| 4 | Megaport portal/API: update `megaport_vxc.gcp_b` → new `att_b_v2.pairing_key` | Megaport | **Manual action, BLOCKED until unlock.** |
| 5 | Wait for GCP attachment to reach `ACTIVE` state | GCP | Typically 5-15 min after Megaport partners. |
| 6 | Verify BGP: `gcloud compute routers get-status router-a --region europe-west3`: confirm 2 BGP peers (MCR1 + MCR2), both `Established` | gcloud | Pass gate before re-running validation. |
| 7 | Niobe re-captures GCP CR status + Azure hub effective routes | Niobe | Baseline for Design C evidence. |

**No change to:** vpc_a, att_a, gcp_a VXC, vm_a, vm_b (if keeping both), Azure stack, all Azure VXCs, ER circuits, hubs, AzFWs. Plan-show gate same as §2.4: any `azurerm_*` destroy = STOP.

**Convergence:** MCR2↔single-CR BGP hold-timer 90 s after re-pair. Azure side: Hub2 loses 10.50.x.0/24 via MCR2 during steps 1-5; fails over to Hub1→MCR1 path (prepend fallback). Expect 2-3 min total outage for MCR2 path; MCR1 path continuous.

### 3.5 Expected BGP behavior on the single CR

This is the pedagogical centerpiece. The single Cloud Router (`router_a`, ASN 16550) now has **two eBGP peers** via PARTNER Interconnect:
- **Peer A:** MCR1 (ASN 65001) via att_a → VXC gcp_a
- **Peer B:** MCR2 (ASN 65002) via att_b_v2 → VXC gcp_b

#### What the CR advertises outbound (GCP → Azure direction)

The CR in `CUSTOM` mode advertises both GCP subnets on **both** BGP sessions:

| Advertisement | To MCR1 (att_a) | To MCR2 (att_b_v2) |
|---|---|---|
| 10.50.1.0/24 | ✅ AS-path: `16550` | ✅ AS-path: `16550` |
| 10.50.2.0/24 | ✅ AS-path: `16550` | ✅ AS-path: `16550` |

Both MCRs receive both GCP subnets with identical AS-path length. Both MCRs then advertise these to their respective Azure hubs. Azure routing for GCP prefixes requires Axis-2 MCR prepend (unchanged from Design B: MCR1 prepends 10.50.2.0/24 3× toward Hub1; MCR2 prepends 10.50.1.0/24 3× toward Hub2).

#### What the CR receives inbound (Azure → GCP direction)

With Mechanism B active on the MCRs:

| Prefix | From MCR1 (att_a) | AS-path from MCR1 | From MCR2 (att_b_v2) | AS-path from MCR2 |
|---|---|---|---|---|
| Hub1 (10.10.0.0/23) | ✅ native | `65001 12076` | ✅ prepended 3× | `65002 65002 65002 65002 12076` |
| Spoke1 (10.11.0.0/24) | ✅ native | `65001 12076` | ✅ prepended 3× | `65002 65002 65002 65002 12076` |
| Spoke2 (10.12.0.0/24) | ✅ native | `65001 12076` | ✅ prepended 3× | `65002 65002 65002 65002 12076` |
| Hub2 (10.20.0.0/23) | ✅ prepended 3× | `65001 65001 65001 65001 12076` | ✅ native | `65002 12076` |
| Spoke3 (10.21.0.0/24) | ✅ prepended 3× | `65001 65001 65001 65001 12076` | ✅ native | `65002 12076` |
| Spoke4 (10.22.0.0/24) | ✅ prepended 3× | `65001 65001 65001 65001 12076` | ✅ native | `65002 12076` |

#### BGP best-path selection at the single CR

The CR applies standard BGP best-path. LOCAL_PREF is equal (eBGP default = 100 on both peers). Decision falls to **AS_PATH length:**

| Destination | Winner | Egress attachment | Reasoning |
|---|---|---|---|
| Hub1 / Spoke1 / Spoke2 | MCR1 path | att_a | Shorter: `65001 12076` (2 hops) vs `65002×4 12076` (5 hops) |
| Hub2 / Spoke3 / Spoke4 | MCR2 path | att_b_v2 | Shorter: `65002 12076` (2 hops) vs `65001×4 12076` (5 hops) |

Result: GCP→Azure traffic is symmetric by design: same hub-affinity as before, now driven by pure BGP best-path at the CR instead of geography. **This is the first time BGP best-path selection is visible at the GCP layer.**

**ECMP:** Only possible if two paths have equal AS-path length. With Mechanism B (3× prepend), paths are clearly unequal (2 hops vs 5 hops) for all Azure prefixes. No ECMP in steady state. If Mechanism B is removed (scenario test), equal-length paths → GCP Cloud Router selects via router-ID tiebreak (deterministic but potentially non-symmetric). This is the "hidden asymmetry" that becomes fully visible without prepend.

**MED:** Megaport may set MED on PARTNER Interconnect sessions. Within one ER circuit, primary VXC MED=0 / secondary VXC MED=10. Across different ER circuits (MCR1 vs MCR2), MEDs from different peers are comparable only if MULTI_EXIT_DISC is accepted from both: GCP Cloud Router uses MED as a tiebreaker only after AS_PATH. With Mechanism B in effect, MED is never reached in the tiebreak chain.

**Does Mech C (vHub Route Maps) affect GCP single-CR outbound choice?**

No. vHub Route Maps operate inside Azure's control plane. A Route Map prepending on Hub1's ER inbound changes what Hub1 prefers for return traffic to GCP, but the modified (prepended) AS_PATH is NOT re-exported through MCR1's BGP session back to GCP's CR. The CR only sees what MCR1/MCR2 directly advertise via the PARTNER BGP sessions. Azure's internal prepend is opaque to GCP. **Confirmed: Mech C on Azure does not affect GCP single-CR outbound path selection.** They are independent levers: Mech B controls GCP-layer symmetry, Mech C controls Azure-layer symmetry.

#### What Design B was hiding (the pedagogical delta)

In Design B, CR-A (eu-w3) had only MCR1 as a peer: there was no second path to compare against. CR-A always used MCR1. There was no BGP decision to make. The "best-path" was trivially the only path. The geography (VM-A co-located with CR-A in eu-w3) made this look natural and correct. Design C removes that mask: one CR, two peers, pure BGP. The blog reader sees the actual routing decision happening.

### 3.6 Design comparison table

| Dimension | Design A | Design B | Design C |
|---|---|---|---|
| GCP VPCs | 2 (REGIONAL each) | 1 (GLOBAL) | 1 (GLOBAL) |
| Cloud Routers | 2 (1 per VPC) | 2 (1 per region, shared VPC) | **1** |
| Attachments | 2 (1 per CR) | 2 (1 per CR) | **2 on same CR** |
| CR BGP peers | 1 each | 1 each | **2 on same CR** |
| BGP best-path at GCP layer | None (single path each CR) | None (single path each CR) | **✅ Yes** |
| GCP in-region routing magic | VPC-level (inter-VPC boundary hides routing) | Geography hides per-CR single-path | **Removed: pure BGP** |
| Asymmetry visible at GCP | No | Partially (cross-region VM↔spoke) | **Fully visible** |
| Redundancy model | Per-region independent | VPC-level failover (Design B §2.2) | **None at CR level; redundancy starts at MCR** |
| Failover (single MCR/CR down) | ❌ Total loss | ⚠️ Auto-failover | ❌ Total loss (one path only per hub) |
| Blog narrative purpose | Baseline: "two-VPC naive" | Transition: "collapse to shared VPC" | **Centerpiece: "real on-prem BGP"** |
| Complexity (Tank effort) | Baseline | Medium (vpc_b destroy, att_b re-pair) | Low (1 CR destroy + 1 att re-pair + Megaport re-pair) |

### 3.7 Design D fallback sketch (if Megaport stays locked)

**Trigger:** Jose answers Q1 = locked / abandoning Megaport GCP VXCs.

Design D keeps the existing Design B infrastructure (two CRs, two attachments, two VXCs) and adds a **Linux NVA VM inside vpc_a** (BIRD 2 or FRR) that acts as the single logical "on-prem router" for the GCP VMs. The NVA has routes programmed from both Cloud Routers via VPC routing and redistributes a unified BGP view to the VMs via static routes or OSPF.

**What it achieves:** VMs see one next-hop (NVA) for all Azure traffic. NVA makes the forwarding decision based on its own routing table (informed by both CRs). The pedagogical "single router with two uplinks" behavior is preserved logically, even though the underlying transport still uses two separate CRs.

**What it costs:** Extra hop (VM → NVA → CR → MCR → Azure). Extra failure domain (NVA is now in the critical path; single NVA = new SPOF). NVA HA requires `google_compute_address` for failover IP. No Megaport changes: entirely within GCP.

**What it can't do:** The NVA doesn't have native PARTNER Interconnect BGP sessions; it relies on the Cloud Routers for the PARTNER peering and learns routes from them via the VPC routing table. It can re-advertise but doesn't directly control MCR1/MCR2 BGP policies. This limits how cleanly Mechanism B can be demonstrated at the "single router" layer: the route policy lives at the MCR, not at the NVA.

Design D is a reasonable lab substitute if Megaport stays locked, but the blog narrative is weaker ("we simulated a router with a routing VM") vs Design C ("we deployed a real single-router dual-homed config"). Jose's call (Q4).

---

## 4. Mechanism C: VWAN Route Maps

**Problem:** `router_a` (ASN 65003, PARTNER Interconnect) receives all 6 Azure spoke prefixes from both MCR1 (att_a, ASN 65001) and MCR2 (att_b_v2, ASN 65002) with equal AS-path length. No BGP signal distinguishes which circuit is correct per prefix → best-path falls to router-ID tiebreak → return traffic hits the wrong AzFW → silent drops. Mechanism C injects AS-path differentiation from the Azure vHub layer, independently of Mechanism B (MCR-layer prepend, which governs the Azure→GCP axis).

**Azure Route-Maps constraints (validated 2026-06-15 vs MS Learn):**
- 2-byte ASNs only: 32-bit range not supported
- Private ASNs (64512-65534) MUST NOT be used for prepend
- Azure-reserved ASNs (8074, 8075, 12076, 65515, 65517, 65518, 65519, 65520) MUST NOT be used

Jose directive (2026-06-16T00:15Z): Mech C1 (active/active) first, then Mech C2 (active/passive). Both implemented sequentially: not alternatives.

### 4.1 Mech C1: Active/active per-prefix reserved-ASN prepend (outbound route maps only)

*Modernizes: MS Learn ExpressRoute DR "Scenario 2: active/active using AS-path prepend" at the VWAN layer instead of CE router.*

#### Reserved ASN choice

| Candidate | IANA type | 2-byte? | Azure safe? | Verdict |
|---|---|---|---|---|
| AS 0 | RFC 7607 reserved | Yes | ❌ MUST NOT appear in AS_PATH | REJECT |
| AS 23456 (AS_TRANS) | RFC 6793: 4-byte BGP transition | Yes | ✅ Not private, not Azure-reserved | REJECT: carries 4-byte transition semantics (see below) |
| **AS 64496-64511** | RFC 5398: documentation/example | Yes | ✅ Not private, not Azure-reserved | **PICK (64496)** |
| 64512-65534 | IANA private (RFC 1930) | Yes | ❌ Azure Route-Maps explicitly prohibits | REJECT |
| 4200000000+ | Private 32-bit (RFC 6996) | No | ❌ 2-byte only constraint | REJECT |

**Pick: AS 64496** (RFC 5398 documentation range 64496-64511). 2-byte, not in the private range (64512+), not Azure-reserved, and reserved purely for documentation/examples so it carries no operational meaning. Instantly recognizable in `gcloud compute routers get-status` as an intentional engineering prepend.

**Why not AS 23456 (AS_TRANS)?** Jose flagged (2026-06-16) that 23456 is reserved as the 2-byte placeholder a non-4-byte-capable BGP speaker substitutes for any 4-byte ASN it cannot represent (RFC 6793). Using it as a deliberate prepend value risks ambiguity and unwanted interactions if the lab later transitions to 4-byte ASNs: a real AS_TRANS substitution would be indistinguishable from the engineering prepend. AS 64496 has no such transition semantics. Azure Route Maps was verified to accept 64496 (test route map provisioned `Succeeded`, 2026-06-16).

#### Route map placement: OUTBOUND only

**Direction: OUTBOUND on each hub's ER connection** (hub→MCR direction). OUTBOUND intercepts the hub's advertisement before it leaves Azure; MCR re-advertises the already-prepended AS-path to `router_a`. An INBOUND route map (MCR→hub) only affects what the hub imports: invisible to `router_a`.

| Hub | TF resource | Direction | Match prefixes | Action |
|---|---|---|---|---|
| Hub1 | `hub1_circuit1` | OUTBOUND | 10.20.0.0/23, 10.21.0.0/24, 10.22.0.0/24 (Hub2-region) | Prepend 64496 × 3 |
| Hub2 | `hub2_circuit2` | OUTBOUND | 10.10.0.0/23, 10.11.0.0/24, 10.12.0.0/24 (Hub1-region) | Prepend 64496 × 3 |

#### AS-path at router_a after Mech C1

| Azure prefix | Via att_a (MCR1 65001) | Via att_b_v2 (MCR2 65002) | router_a wins |
|---|---|---|---|
| 10.10.0.0/23 (Hub1) | `65001 12076` (2 hops) | `65002 64496 64496 64496 12076` (5 hops) | **MCR1** |
| 10.11.0.0/24 (Spoke1) | `65001 12076` (2 hops) | `65002 64496 64496 64496 12076` (5 hops) | **MCR1** |
| 10.12.0.0/24 (Spoke2) | `65001 12076` (2 hops) | `65002 64496 64496 64496 12076` (5 hops) | **MCR1** |
| 10.20.0.0/23 (Hub2) | `65001 64496 64496 64496 12076` (5 hops) | `65002 12076` (2 hops) | **MCR2** |
| 10.21.0.0/24 (Spoke3) | `65001 64496 64496 64496 12076` (5 hops) | `65002 12076` (2 hops) | **MCR2** |
| 10.22.0.0/24 (Spoke4) | `65001 64496 64496 64496 12076` (5 hops) | `65002 12076` (2 hops) | **MCR2** |

*Path construction:* Hub OUTBOUND map prepends before the prefix exits the ER GW. MCR adds its own ASN (65001/65002) when advertising to `router_a`. ER GW always appears as 12076 (Microsoft fixed ASN for ER private peering).

#### Prepend count: 3×

LOCAL_PREF equals 100 on both PARTNER Interconnect sessions (eBGP default). GCP CR tiebreaks via AS-path length. 3× gives clear separation (2 hops vs 5 hops) with conventional prepend magnitude. MED is not decisive across different peers.

#### TF sketch

```hcl
resource "azurerm_virtual_hub_route_map" "hub1_out_depref_hub2" {
  name           = "hub1-out-depref-hub2"
  virtual_hub_id = azurerm_virtual_hub.hub1.id
  rule {
    name  = "prepend-hub2-region"
    order = 1
    match_criteria { match_condition = "Contains"
      route_prefix = ["10.20.0.0/23", "10.21.0.0/24", "10.22.0.0/24"] }
    actions { type = "Add"; as_path = ["64496", "64496", "64496"] }
  }
}
# Attach: add routing { outbound_route_map_id } to azurerm_express_route_connection.hub1_circuit1
# Mirror: hub2_out_depref_hub1 (Hub1-region prefixes 3x) → hub2_circuit2 OUTBOUND
```

#### Failover behavior (C1)

MCR1 (att_a) fails: `router_a` loses 2-hop Hub1-prefix paths; MCR2's 5-hop paths become the only available paths → `router_a` installs them (BGP hold timer ≤ 90s). Hub1/Spoke1/Spoke2 traffic reroutes via MCR2/ER2/Hub2/AzFW2. AzFW2 takes over for Hub1 traffic: stateful tables reset (connection outage during convergence only, not steady-state).

---

### 4.2 Mech C2: Active/passive primary-standby (adds inbound route maps + hub routing preference)

*Modernizes: MS Learn ExpressRoute DR "Scenario 1: active/standby using connection weight/local-preference" translated to VWAN Route-Map + hub routing preference levers.*

#### Primary choice: MCR1 / ER1 / Hub1 (swedencentral, eu-w3)

Hub1 collocated with MCR1 and GCP vm_a in eu-w3: lowest latency, lab #1 baseline circuit. MCR2/ER2/Hub2 = standby.

#### C1 → C2 transition: what changes

In C2, MCR1 is primary for ALL Azure prefixes; the C1 per-prefix split is superseded.

| Route map | C1 state | C2 action | Reason |
|---|---|---|---|
| Hub1 OUTBOUND (de-prefer Hub2 prefixes 3×) | Active | **REMOVE** | Redundant: C2's Hub2 blanket OUTBOUND makes MCR1 win for Hub2 prefixes regardless |
| Hub2 OUTBOUND (de-prefer Hub1 prefixes 3×) | Active | **UPDATE → all prefixes, 5×** | Extend scope from Hub1-only to all Azure prefixes; increase prepend for clearer margin |
| Hub2 INBOUND (de-prefer GCP prefixes) | Not present | **ADD** | New: forces Hub2 to prefer hub-to-hub over ER2 for GCP-bound egress |
| `hub_routing_preference` (both hubs) | `ExpressRoute` | **UPDATE → `ASPath`** | Required for Hub2 INBOUND prepend to override internal ER preference at hub layer |

**Net TF delta for C2 apply: 1 add, 3 changes, 1 destroy.**

#### Route map design (C2)

| Hub | Connection | Direction | Match | Action |
|---|---|---|---|---|
| Hub2 | `hub2_circuit2` | **OUTBOUND** | All Azure prefixes (`0.0.0.0/0 le 32`) | Prepend 64496 × 5 |
| Hub2 | `hub2_circuit2` | **INBOUND** | GCP prefixes (10.50.1.0/24, 10.50.2.0/24) | Prepend 64496 × 5 |

**OUTBOUND:** router_a sees all Azure prefixes via MCR2 with 7-hop AS-path; MCR1's 2-hop paths win for every prefix → all GCP→Azure traffic enters via ER1/Hub1/AzFW1.

**INBOUND:** GCP prefixes from MCR2 get 5× prepend at Hub2. With `hub_routing_preference = ASPath`, Hub2 compares 7-hop ER2 path vs 2-3-hop hub-to-hub path (Hub2→Hub1→ER1) and picks hub-to-hub. GCP egress from Hub2 spokes flows Hub2→AzFW2→Hub1→AzFW1→ER1→MCR1. Return: GCP→MCR1→ER1→Hub1→AzFW1→hub-to-hub→AzFW2→Hub2 spoke. Symmetric. ✓

#### Hub routing preference = ASPath (C2)

Both hubs: `hub_routing_preference = "ASPath"` (from `"ExpressRoute"` default). ⚠️ Triggers vHub reprovision (~10-20 min per hub, per §1.6 timing note). Without `ASPath`, Hub2's internal ER preference overrides AS-path length comparison → INBOUND route map has no effect on Hub2's GCP egress forwarding decision.

#### AS-path at router_a after Mech C2 (all Azure prefixes → MCR1)

| Sample | Via att_a (MCR1) | Via att_b_v2 (MCR2) | wins |
|---|---|---|---|
| Any Hub1 prefix | `65001 12076` (2 hops) | `65002 64496×5 12076` (7 hops) | **MCR1** |
| Any Hub2 prefix | `65001 12076` (2 hops) | `65002 64496×5 12076` (7 hops) | **MCR1** |

> ⚠️ **GCP simulator caveat (observed in Mech C1 evidence, 2026-06-16): not a property of the mechanism.** The "wins" column above is correct for any standards-compliant on-prem/CE router: under the standard BGP best-path algorithm, AS-path length is compared **before** MED, and eBGP installs a **single** best path by default, so the shorter home-circuit path wins and the prepend delivers symmetric return traffic. GCP Cloud Router, used here only to **simulate** on-prem, deviates from this: it derives each VPC dynamic-route's priority from **MED, not AS-path length**, so it installs **both** the 2-hop and the 7-hop path for a given /24 at `priority=0` (it ECMPs them despite the unequal AS-path). Only the /23 supernets (10.10.0.0/23, 10.20.0.0/23) resolve to a single path on GCP. Because GCP is a stand-in for on-premises, this deviation is out of scope: a normal CE router (Cisco, Juniper, Arista, MikroTik) would not exhibit it, and C1/C2 are full fixes there. The residual /24 ECMP only matters if your real on-prem peer ranks by MED and ignores AS-path the way GCP does; in that narrow case, advertise only the /23 aggregate on the standby circuit (tracked as **Mech C3**) or set a peer-side MED/priority lever. See `show-output/design-c-mechC1-symmetric-2026-06-16/14-verdict.md`.

#### Failover behavior (C2)

MCR1 (att_a) fails: all 2-hop paths lost. MCR2's 7-hop paths are the only paths → `router_a` installs them within 90s BGP hold timer. All GCP↔Azure traffic reroutes via MCR2/ER2/Hub2/AzFW2. Hub1 spoke traffic uses hub-to-hub during failover. Stateful tables reset: outage = BGP convergence only. Deliberate primary-down test is the prescribed C2 validation method (§4.5 Phase 3 Step 3.4).

---

### 4.3 Implementation ordering & dependency chain

Sequential. C1 is fully live and Niobe-validated before C2 begins.

1. **C1 first (outbound route maps only).** Smallest resource delta (2 adds, 2 changes, 0 destroys). OUTBOUND confirmed in AzureRM 4.x (§4.4). Blast radius if misconfigured: at worst, 3 Azure prefixes route via the wrong circuit on one hub's ER connection: BGP recovers automatically on rollback. No hub reprovision required.

2. **Evidence checkpoint after C1.** Niobe runs: BGP probe on `router_a` (confirms per-prefix AS-path split) + data plane traceroute from vm_a and vm_b + AzFW log capture. Confirms active/active symmetric routing before C2 modifies anything.

3. **C1 → C2 transition.** Hub1 OUTBOUND route map is **removed** (no longer needed; C2's Hub2 blanket outbound makes MCR1 win for all prefixes including Hub2's). Hub2 OUTBOUND route map is **updated** (Hub1-only 3× → all-prefixes 5×). Hub2 INBOUND route map is **added**. Both hubs `hub_routing_preference` updated to `ASPath`. The 10-20 min vHub reprovision is the long pole; route map changes themselves cause only a ~60s BGP flap per connection.

4. **Evidence checkpoint after C2.** Niobe repeats BGP probe + AzFW logs (steady-state confirms active/passive). Then runs **deliberate primary-down test**: take att_a BGP session down, confirm `router_a` falls back to MCR2 paths within 90s, confirm AzFW2 becomes active. Restore att_a session, confirm reconvergence.

---

### 4.4 TF/CLI feasibility: outbound vs inbound route map support

#### azurerm_virtual_hub_route_map

✅ **Confirmed exists** in AzureRM ≥ 3.22.0. Lab uses `~> 4.0`: compatible. Resource represents `Microsoft.Network/virtualHubs/routeMaps` (`2025-01-01` API). Rule schema: `match_criteria` (`match_condition`, `route_prefix` list); `actions` (`type = "Add"`, `as_path` list of 2-byte ASNs).

#### azurerm_express_route_connection routing block

| Direction | TF attribute | AzureRM 4.x | Notes |
|---|---|---|---|
| OUTBOUND (hub→circuit) | `routing.outbound_route_map_id` | ✅ Confirmed | Used by C1 (Hub1 + Hub2) and C2 (Hub2 updated) |
| INBOUND (circuit→hub) | `routing.inbound_route_map_id` | ✅ Confirmed | Used by C2 (Hub2 new) |

**No provider gap for either direction.** Both confirmed in AzureRM 4.x provider docs. Current `azure-expressroute.tf` has no `routing {}` block: adding one is an **in-place update** (no ForceNew). Triggers ~60s BGP flap per ER connection on update.

#### Hub routing preference (C2 only)

`azurerm_virtual_hub.hub_routing_preference`: `"ExpressRoute"` (default), `"VpnGateway"`, `"ASPath"`. In-place update. ⚠️ ~10-20 min vHub reprovision per hub.

#### TF delta summary

| Phase | Adds | Changes | Destroys | Long-pole |
|---|---|---|---|---|
| C1 apply | 2 (Hub1+Hub2 OUTBOUND route maps) | 2 (ER connections add `routing {}`) | 0 | ~60s BGP flap per connection |
| C2 apply | 1 (Hub2 INBOUND route map) | 3 (Hub2 OUTBOUND updated + 2 vHubs hub_routing_preference) | 1 (Hub1 OUTBOUND route map) | ~10-20 min vHub reprovision per hub |

#### CLI fallback (both directions)

```powershell
# C1: create OUTBOUND route map and attach
az network vhub route-map create -g <RG> --vhub-name hub1 --name hub1-out-depref-hub2 `
  --rules '[{"name":"r1","matchCriteria":[{"matchCondition":"Contains","routePrefix":["10.20.0.0/23","10.21.0.0/24","10.22.0.0/24"]}],"actions":[{"type":"Add","asPath":["64496","64496","64496"]}],"nextStepIfMatched":"Continue"}]'
az network express-route gateway connection update -g <RG> --gateway-name <ERGW1> -n <CONN1> `
  --outbound-route-map $(az network vhub route-map show -g <RG> --vhub-name hub1 -n hub1-out-depref-hub2 --query id -o tsv)

# C2: add INBOUND route map on Hub2 (use --inbound-route-map flag)
az network express-route gateway connection update -g <RG> --gateway-name <ERGW2> -n <CONN2> `
  --inbound-route-map $(az network vhub route-map show -g <RG> --vhub-name hub2 -n hub2-in-depref-gcp --query id -o tsv)
```

Requires Azure CLI ≥ 2.40.

---

### 4.5 Migration plan: two phases

**Phase 2 = Mech C1 apply (outbound only: active/active)**

Pre-flight: Niobe's baseline in `show-output/design-c-asymmetric-2026-06-15/` confirms equal AS-path lengths at `router_a` (the problem state).

| Step | Action | Verify | Outage |
|---|---|---|---|
| 2.1 | `terraform apply`: 2 adds, 2 changes, 0 destroys | Both route maps `provisioningState = Succeeded` | ≤ 60s BGP flap per ER connection |
| 2.2 | BGP probe | `gcloud compute routers get-status router-vwan-symm-a --region europe-west3`: Hub1 prefixes best-path via att_a (`65001 12076`); Hub2 prefixes via att_b_v2 (`65002 12076`); losing paths contain 64496 | None |
| 2.3 | Data plane | Traceroute vm_a→10.20.x.x enters ER2; vm_b→10.10.x.x enters ER1 | None |
| 2.4 | AzFW logs | Hub1 AzFW: Hub1-spoke GCP traffic only; Hub2 AzFW: Hub2-spoke GCP traffic only | None |

Niobe hand-off: capture all steps → `show-output/design-c-mech-c1-2026-06-15/`. Signal Trinity + Tank when done.

Rollback: remove `outbound_route_map_id` from both `routing {}` blocks + destroy route maps. `terraform apply` → 0 adds, 2 changes, 2 destroys.

---

**Phase 3 = Mech C2 apply (inbound + hub routing preference: active/passive)**

Pre-flight: Phase 2 evidence confirms active/active symmetric. `hub_routing_preference = ExpressRoute` on both hubs (current state).

| Step | Action | Verify | Outage |
|---|---|---|---|
| 3.1 | `terraform apply`: 1 add, 3 changes, 1 destroy | Hub2 INBOUND map `Succeeded`; Hub1 OUTBOUND map gone; both vHubs `hub_routing_preference = ASPath` | ~60s BGP flap + ~10-20 min vHub reprovision per hub |
| 3.2 | Steady-state BGP probe | All 6 prefixes best-path via att_a: `65001 12076`; MCR2 paths all show 64496×5 | None |
| 3.3 | Steady-state data plane | Traceroutes from vm_a + vm_b → all Azure prefixes enter via ER1; AzFW1 sees all GCP-origin traffic | None |
| 3.4 | **Failover test (deliberate)** | Take att_a BGP session down; within 90s `router_a` installs MCR2 paths; AzFW2 becomes active; restore att_a; confirm reconvergence | BGP hold timer ≤ 90s |

Niobe hand-off: capture Steps 3.2-3.4 → `show-output/design-c-mech-c2-2026-06-15/`. C2 complete when failover test passes.
