---
name: "dual-er-symmetry"
description: "Checklist for designing multi-region Azure Virtual WAN labs where stateful firewalls in each hub must see symmetric forward and return traffic. Use when scoping any vWAN-with-secured-hub topology that has more than one ER circuit or more than one on-prem entry point."
domain: "azure-networking-lab-design"
confidence: "medium"
source: "earned — derived from lab #2 (vwan-dual-er-symmetric) manifest design, 2026-06-15, building on lab #1 ER + Megaport learnings"
---

## Context

This skill applies whenever a lab includes **all of**:

- Azure Virtual WAN with **two or more secured hubs** (Azure Firewall as the in-hub NVA).
- **More than one ExpressRoute circuit** (or more than one on-prem entry path — VPN, SD-WAN, ER mix).
- Stateful packet inspection in path (AzFW Standard or Premium, third-party NVA in routing-intent next-hop slot).

The risk being managed: stateful firewalls drop return packets that hit a different instance than the one that saw the forward packet. With redundant on-prem paths in 2+ regions, this is the default outcome unless the design deliberately enforces per-flow firewall affinity. Symptom = TCP handshakes time out for some flows and not others; root cause = asymmetric routing.

Skip this skill for: single-hub labs, route-server labs (different routing model), VPN-only labs at <2 branches (no path-multiplicity), or non-stateful inspection (NSG-only).

## Patterns

### Pattern 1 — Three independent symmetry levers; stack at least two

Symmetry rests on three structural levers. Each works independently; stack them so a single misconfiguration cannot break symmetry alone.

| Lever | Mechanism | What it prevents |
|---|---|---|
| **Per-circuit advertisement scope** | `er_bow_tie=no` — each ER GW connects to exactly one circuit. | Azure best-path flipping between circuits and changing the egress hub. |
| **Per-region on-prem origination** | Separate per-region on-prem networks (separate GCP VPCs / separate physical on-prem sites), no cross-network peering between them. | Single on-prem prefix appearing on two MCRs and being installed on the wrong hub. |
| **Routing-intent forces all private traffic through AzFW** | `ri_policy=private` on every hub. | A spoke-to-spoke flow taking a hub-bypass path that skips the firewall, looking "symmetric" but actually unevaluated. |

### Pattern 2 — Decline Global Reach and ER bow-tie deliberately

For a symmetry-focused lab, **both** features are anti-features. Document the decline explicitly in the manifest so the next reader doesn't "fix" the topology by adding HA.

- **Global Reach** creates an MSEE-to-MSEE circuit-to-circuit path that bypasses both hubs entirely. Asymmetry-irrelevant *and* hub-firewall-irrelevant.
- **ER bow-tie** creates a second BGP path per prefix into each hub. Azure best-path will pick one — but a config change, a circuit flap, or a route-table label tweak can flip the pick, and the flip is invisible until traffic starts dropping.

Both have legitimate uses (HA across regions, on-prem-to-on-prem direct path); a symmetry lab is not one of them.

### Pattern 3 — Make the failure mode a scenario, not a footnote

Every symmetry lab needs at least one scenario that **deliberately breaks symmetry** and captures the dropped flow as evidence. The "everything works" scenarios are only meaningful against the contrast of a broken-on-purpose scenario.

Standard break recipe:
1. Steady-state validation passes (all expected hits on expected hub, zero hits on the other).
2. Tank applies a single perturbation (turn ER bow-tie ON / peer the two on-prem VPCs / remove a route-policy filter).
3. Re-run the same generator. KQL on `AZFWNetworkRule` for the same 5-tuple now shows:
   - Forward direction: Allow on Hub A.
   - Return direction: Drop on Hub B with reason indicating no stateful match.
4. Tank reverts the perturbation; validation must re-pass before cleanup.

### Pattern 4 — Cost-tier the secured hubs honestly

Two secured hubs with AzFW Standard is ~$60/day on top of the ER + MCR + spoke costs. Cost-cuts that "save the firewall" change what the lab demonstrates:

- Drop AzFW from one hub → lose the symmetric-cross-region scenario (no firewall to count hits on).
- Drop AzFW to Premium-on-one-only → tier-mismatch confound on log structure.
- Use a third-party NVA → out of scope for a vWAN-native symmetry lab; defer to a separate NVA-routing-intent lab.

If $60/day for two AzFW Standard is too much, the right answer is "this is a different lab," not "secure one hub and not the other."

## Examples

- **Lab #2 — `vwan-dual-er-symmetric`** (`labs/vwan-dual-er-symmetric/manifest.md`). Canonical implementation of all three patterns. Three symmetry levers stacked; Global Reach and bow-tie declined with documented rationale; Scenario S4 is the deliberate-break demo.
- **Reference script — `C:\Users\jomore\Repos\azcli\vwan_2xshub.azcli`.** Jose's working CLI script that already encodes the levers as `secure_hub`, `routing_intent`, `er_bow_tie`, `global_reach`, `deploy_gcp` variables. Lines 39–42 are the control switches; lines 167–222 are the routing-intent PUT function; lines 2300–2342 are the ER GW + bow-tie + Global Reach branches.
- **Lab #1 lesson carryover.** `az network express-route list-route-tables` may return `Gateway does not have any Bgp sessions` even when BGP is up. For symmetry labs, fall back to `az network vnet-gateway list-advertised-routes` and the Megaport VXC's `bgpConnections` resource as primary evidence.

## Anti-Patterns

- **Documenting symmetry as "should work because of routing-intent."** Routing-intent alone does not enforce symmetry — it enforces *firewall-in-path*. Symmetry depends on which hub the path lands on, which routing-intent does not control. If you find yourself writing "the firewall handles it," reconsider.
- **Mixing internet-egress symmetry into the same lab.** Internet egress through AzFW has its own asymmetry mode (NAT IP affinity, SNAT port exhaustion, public-IP allocation). Combining it with private-traffic symmetry doubles the variable count without sharpening either lesson.
- **Pinning a Megaport MCR market in the design.** Lab #1 asked for Madrid and got Frankfurt. The MCR market is Megaport's call. Pin the ER peering location (which is Azure-side) and let Megaport pick the MCR PoP; verify after deploy.
- **Using bow-tie "for HA" then trying to symmetrise with AS-path prepending.** Works in production with mature ops; flaky in a one-shot lab because BGP convergence + AzFW state TTL drift make repro hard. Save AS-path-prepend-for-HA for its own dedicated lab.
- **Asking for symmetry on cross-region spoke-to-spoke without `routing-intent=private`.** Cross-region traffic without routing-intent uses vWAN's default route table which may or may not steer through AzFW depending on hub configuration. Don't assume; set `private` explicitly.

## IaC patterns (Tank, added 2026-06-15 from lab #2 build)

These are the Terraform-specific patterns that make a dual-ER symmetric vWAN lab actually deployable. They live here (not in a generic Tank doc) because they only apply when you're stacking the three symmetry levers.

### IaC.1 — Per-region VM size variable from day 1

When the lab spans two regions, declare `var.vm_size_region_a` and `var.vm_size_region_b` separately, not a single `var.vm_size`. Catalog drift between regions is real: `Standard_B2als_v2` was available in `swedencentral` but **entirely absent from the northeurope catalog** at lab #2's deploy-prep probe (no B2a*_v2 AMD SKUs). A per-region variable absorbs the substitution (B2s_v2 fallback) without restructuring locals or for_each loops over a `spokes` map.

### IaC.2 — Symmetry-perturbation knobs as TF variables (not separate apply targets)

Bow-tie and prefix injection are S4 scenarios that Niobe runs *after* steady-state baseline. Express them as:

```hcl
variable "er_bow_tie_hub1"        { type = bool         default = false }
variable "mcr1_injected_prefixes" { type = list(string) default = [] }

resource "azurerm_express_route_connection" "hub1_circuit2_bowtie" {
  count = var.er_bow_tie_hub1 ? 1 : 0
  # ...
}

locals {
  mcr1_export_prefixes = concat([var.gcp_vpc_a_subnet], var.mcr1_injected_prefixes)
}
```

Niobe runs `terraform apply -var er_bow_tie_hub1=true` for S4a or `-var 'mcr1_injected_prefixes=["10.50.2.0/24"]'` for S4b. Restore = plain `terraform apply` with defaults. **Atomic, idempotent, and the diff is visible in plan before any change lands.** All outputs that reference the optional resources must use `try(<ref>[0].id, null)`.

### IaC.3 — `internet_security_enabled = true` is mandatory when routing-intent=private

For `azurerm_express_route_connection` (and `azurerm_virtual_hub_connection`) — without this, ER-learned and spoke-originated routes bypass the in-hub AzFW even with routing-intent=private set on the hub. Renamed from `enable_internet_security` in azurerm v4.x; both still work but use the new name in new labs.

### IaC.4 — Explicit `depends_on` from spoke connections to routing-intent

`azurerm_virtual_hub_connection.spoke[*]` should declare `depends_on = [azurerm_virtual_hub_routing_intent.hub1, ...hub2]`. The `defaultRouteTable` exists from hub creation, but routing-intent reshapes how it's populated; without the dependency, Terraform may create connections before intent and produce transient propagation gaps that confuse the first round of Niobe's validation queries.

### IaC.5 — Permissive AzFW policy is required, not optional

Routing-intent=private routes every spoke and ER flow through the AzFW. Without an explicit Allow rule covering RFC1918→RFC1918, AzFW's default deny silently drops every east-west and ER-bound packet — looking exactly like a routing failure in `traceroute`. Ship a `firewall_policy_rule_collection_group` with a `network_rule_collection { rule { source/destination = ["10.0.0.0/8","172.16.0.0/12","192.168.0.0/16"] protocols = ["Any"] destination_ports = ["*"] } }` baked in.

### IaC.6 — Single-state, multi-provider apply (no module-per-cloud split)

vWAN + ER + Megaport + GCP need one dependency graph: ER service key → Megaport Azure VXC; GCP attachment pairing key → Megaport google VXC; Megaport VXC → ER connection. Splitting into per-cloud TF roots forces hand-passing of service keys/pairing keys, breaks single-shot destroy ordering, and reintroduces every cleanup gotcha lab #1 fixed. One root, multiple providers, multiple `.tf` files (one per concern).

### IaC.7 — GCP `provider "google"` aliasing per region

`provider "google"` (default, `region = var.gcp_region_a`) and `provider "google" { alias = "region_b" region = var.gcp_region_b }`. Every Region B resource gets `provider = google.region_b`. Without aliasing, the provider's default region drives zone selection and quota project resolution even when the resource's `region` attribute is set explicitly.

### Pattern 5 — Always include a resiliency table in any dual-circuit design

A dual-circuit design that documents steady-state symmetry but not failure modes is incomplete teaching material. Any time you ship a design with ≥ 2 ER circuits (or ≥ 2 MCRs), the design spec MUST include:

1. **An F-table** (failure modes × blast radius columns). Minimum columns: failure description, already protected?, each region's connectivity status, active firewall(s) in path, failover time, operator action.
2. **A direct answer to "does the on-prem side lose reach to any hub?"** — stated per-failure-mode, not hedged.
3. **Mitigations ranked by complexity** with cost impact and operator burden, even if none are implemented in v1. Readers need the decision matrix, not just the recommendation.

**Why this is a pattern and not a one-off:** Mechanism A (tight prefix filters) is the symmetric-steady-state default; but "symmetric" refers to the forward+return path pairing within a hub, not to survivability. These are orthogonal properties. A design can be perfectly symmetric and perfectly fragile — the lab must teach both.

**Trigger in the design workflow:** After §1.5 (symmetry mechanism section), before the route-collection plan. The resiliency table should exist as §1.6 in every dual-circuit lab design.md.



### IaC.8 — Dual-VXC per ER circuit is mandatory; single-VXC deploys give degraded ER HA and miss the secondary BGP session that resiliency validation depends on.

Each ER circuit has two MSEE peering ports (primary + secondary). Wire both via separate `megaport_vxc` resources with `port_choice = "primary"` and `port_choice = "secondary"`. Validate via `bgpState=Established ×4` (2 per circuit) across a dual-circuit lab. Lab #2 was initially deployed with single VXC per circuit and caught by Jose at validation time (patch applied 2026-06-15T18:55:36+02:00).

The platform KV firewall + GSA collision is an operator workflow problem, not a Terraform problem. Don't add `data "azurerm_key_vault_secret"` blocks that fight the ACL; fetch secrets in `deploy.ps1` (Path A: pause GSA; Path B: `try`/`finally` ACL flip with `.akv-state.json` snapshot), export as `TF_VAR_*`, and let Terraform see plain `variable` blocks. **The `finally` block is load-bearing — ACL must restore on script crash too.**
