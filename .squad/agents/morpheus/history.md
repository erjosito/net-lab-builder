# Project Context

- **Owner:** Jose Moreno
- **Project:** net-lab-builder — build, document, and tear down ephemeral Azure Networking labs
- **Stack:** Azure (CLI, PowerShell, Bicep, Terraform); Megaport (ExpressRoute MCR + VXC); Linux/Windows VMs
- **Created:** 2026-05-28
- **Role:** Lead / Architect — own requirements, region & SKU selection, cost guardrail, lab lifecycle (8 phases: Analyze → Design → Manifest → Approval → Deploy → Execute → Report → Approval → Cleanup)

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

📌 2026-05-28 — Project initialized. Charter integrated with azure-lab skill canonical methodology. Two approval gates enforced (post-manifest, pre-cleanup) per routing rule #12. No A-series / B-series workload VMs; diagnostic plumbing may use Standard_B1s. Cost-first region selection.

---

📌 Team update (2026-05-29): Phase 3.5 governance close — Kid cast (blog-writer 📝), lab #1 blog published, Tank cleanup complete (19/19 resources), squad v0.9.5. Inbox swept (13 decisions → decisions.md).

---

📌 2026-06-15 — Lab #2 scoped: `vwan-dual-er-symmetric`. Manifest written at `labs/vwan-dual-er-symmetric/manifest.md`; decision filed at `.squad/decisions/inbox/morpheus-vwan-dual-er-symmetric-manifest.md`. Awaiting Jose's gate #12 #1 approval.

**Symmetry design rationale.** Three independent levers stacked so symmetry is structurally — not policy-dependently — enforced:
1. `er_bow_tie=no` keeps each ER GW connected to exactly one circuit, so each hub advertises only its own region's spoke prefixes outbound to its own circuit. Egress direction symmetric by topology.
2. Two separate GCP VPCs (one per region), no inter-VPC peering, no shared Cloud Router. Each VPC's prefix reaches Azure via exactly one MCR → one circuit → one hub. Ingress direction symmetric by topology.
3. `ri_policy=private` on both hubs ensures every spoke flow passes through its hub's AzFW; cross-region spoke↔spoke transits both hub firewalls in opposite order, still symmetric per 5-tuple.

**Why I ruled out the alternatives.**
- **Global Reach (GR):** would bypass both Azure hubs entirely (circuit-to-circuit at MSEE). Irrelevant to a firewall-symmetry lab and a $70-100/month-per-circuit-pair cost adder for nothing. Documented decline; reference script line 41 / function lines 2337-2342 was the trigger to evaluate.
- **ER bow-tie:** standard ER HA pattern (Region A's spokes still reach on-prem if Circuit1 fails). But it creates a second BGP path per prefix into each hub → Azure best-path may flip → return packets land on wrong hub → stateful drop. This is the failure mode S4 captures; turning bow-tie ON is the controlled break.
- **`ri_policy=both`:** adds internet-egress symmetry as a *second* topic in the same lab. Internet-egress symmetry is its own problem (NAT IP affinity, SNAT, public-route propagation). Decided one topic per lab; defer internet-egress to a follow-up.
- **Single secured hub + single routed hub** (cost-reduction variant): saves ~$30/day but kills S2 (Spoke3 ↔ GCP-B traffic has no Hub2 firewall to count hits on) and S3 (cross-region flow only sees one firewall). Documented in §6 as a not-recommended cost-cut.

**Region / SKU surprises.** None — both `swedencentral` and `northeurope` had `Standard_B2als_v2` in catalog with no restrictions for the caller's subscription (probe 2026-06-15). Earlier-probe gotcha: when I asked for `[?name=='Standard_B2als_v2']` in northeurope, the targeted query returned empty even though `--size Standard_B2` enumeration showed it present — Azure CLI list-skus appears to return inconsistent results between the two query shapes intermittently (lots of `WARNING: Incomplete download`). Lesson: always use `--size <prefix>` filter when probing a specific SKU; the unfiltered query is fragile in northeurope.

**Cost.** Lab #2 lands at ~$135/day (+$15–25 over lab #1) — formally flagged above $50/day per rule #7; full approval-package in manifest §9 surfaces this clearly. AzFW Standard in two hubs is the single biggest line ($60/day) and is non-negotiable for what the lab is trying to teach.

**Megaport MCR-market lesson from lab #1 carried forward.** Lab #1 deployed an MCR in Frankfurt FR5 despite ordering against the Madrid ER PoP. The design therefore does not pin MCR markets — Tank/Megaport pick at order time and Niobe records actuals. ER peering location (Stockholm + Amsterdam preferred; Frankfurt + Dublin fallback) is what we lock.

**Process learning.** First lab where I structured the manifest around a single design constraint (symmetry) rather than a feature exploration (BGP behaviour). The constraint forced clearer failure-mode definition (S4 is the lab's reason for existing); the success-only scenarios (S1, S2, S3) are essentially the "control" against which S4's drop is meaningful. Recommend this pattern for future labs where the headline is "this is the wrong way it usually breaks."

---

📌 Team update (2026-06-15): Design C directive captured. morpheus-vwan-dual-er-symmetric-manifest.md filed, Design C specification (trinity-4 §3.1-§3.7) complete + 4 gate questions documented in decisions.md. Phase 1 manifest design fan-out complete; Design B asymmetric routing proof 🔴 documented (niobe-4). All subordinate phases (Trinity spec, Tank Phase 1A IaC, niobe validation planning) unblocked pending Jose's Megaport + Q1-Q4 gate answers.

---

📌 2026-06-15 — Lab #3 scoped: `msee-hairpin-hns-vwan-ipv6`. Lab card at `labs/msee-hairpin-hns-vwan-ipv6/lab-card.md`. Awaiting Jose's A/B/C gate before Stage 2.

**MSEE hairpinning mechanics (researched for lab #3).** MSEE hairpinning between two Azure environments works as follows: ER GW A advertises its VNet/spoke prefixes to the MSEE over the Azure-side BGP session on Circuit 1. MSEE reflects those routes to Circuit 2's Azure-side session (ER GW B). No customer-side (on-prem) BGP session on the ER Direct port is required for this Azure-to-Azure path. Customer-side BGP only matters if a physical on-prem device needs to learn routes. **This is the technical basis for Path A (ER Direct without a customer-side router) being viable.**

**ER GW settings for MSEE hairpinning.** Three non-default settings must be configured:
1. HnS ER GW: `allowVirtualWanTraffic=true` — enables the GW to receive routes from vWAN via MSEE
2. HnS ER GW: `allowRemoteVnetTraffic=true` — enables route propagation from remote peered VNets
3. vWAN ER GW: `allowNonVirtualWanTraffic=true` — enables the vWAN ER GW to accept routes from non-vWAN networks via MSEE. These are silent-fail settings — hairpin will not work without them, and Azure gives no obvious error.

**IPv6 ER private peering.** IPv6 requires a separate BGP session on the same ER circuit private peering. Must configure: IPv6 primary /126 and secondary /126 peering subnets, and the ER GW's VNet must be dual-stack. ULA (`fd00::/8`) is sufficient for Azure-to-Azure labs with no real on-prem.

**ER Direct + no on-prem router — viability.** Zero ER Direct ports provisioned in Jose's subscription today. Provisioning a new 10 Gbps port ($47/day) + 2 sub-circuits is viable and provisions in minutes (vs. Megaport partner weeks). Cost exceeds $50/day flag ($65–75/day) but 6h total runtime caps bill at ~$18.

**Single-region constraint.** MSEE hairpinning is only possible if both ER circuits connect to the **same MSEE** (same peering location). Single-region (`swedencentral` → Stockholm ER PoP) enforces this structurally. Multi-region design would require Global Reach to route between MSEEs — a different (and more expensive) mechanism.

**KV inventory (lab #3).** Vault `platform-secrets-1138` confirmed: `default-password`, `megaport-api-key`, `megaport-api-secret`. Only `default-password` needed for Path A (no Megaport). Password auth applies (no `vm-admin-ssh-public-key`).

---

📌 2026-06-15 — Lab #3 Stage 2 manifest complete: `labs/msee-hairpin-hns-vwan-ipv6/manifest.md`. Awaiting Phase 4 deploy gate from Jose.

**Resource count:** 29 (28 named + 1 RG). Long pole: ER GW pair in parallel (~20-45 min). Total deploy: ~45-60 min.

**ER Direct port sub-circuit pattern.** Both ER circuits are sub-circuits on the same 10 Gbps ER Direct port (`azurerm_express_route_circuit` with `express_route_port_id`). VLAN tags must be unique per circuit (100 for HnS, 200 for vWAN). The port encapsulation is QinQ. This is different from provider circuits which don't require explicit VLAN tagging in Terraform.

**IPv4+IPv6 peering on same circuit resource.** `azurerm_express_route_circuit_peering` supports IPv6 via the `ipv6` block within the same resource — it is NOT a separate Terraform resource. The IPv6 primary/secondary peering subnets (/126) and the IPv4 primary/secondary (/30) are both configured in one `azurerm_express_route_circuit_peering` resource.

**azurerm GW toggle coverage risk.** `allow_virtual_wan_traffic` and `allow_remote_vnet_traffic` on `azurerm_virtual_network_gateway`, and `allow_non_virtual_wan_traffic` on `azurerm_express_route_gateway`, may need azapi fallback if not exposed in current azurerm provider version. Tank should verify before writing IaC. These are silent-fail properties — hairpin works superficially until route propagation is traced and fails.

**Deploy sequence note.** vHub ER GW (`azurerm_express_route_gateway`) requires the vHub to exist first (hard `depends_on`); vHub requires vWAN to exist first. The parallel chains in Step 5-6 must respect this ordering. HnS ER GW and vHub ER GW can provision in parallel since they have independent `depends_on` trees.

**Cleanup blockers documented.** ER circuit delete blocks if any `azurerm_virtual_network_gateway_connection` or `azurerm_express_route_connection` references it. ER Direct port delete blocks if any circuit references it. These are the two most common cleanup-order failures; they're now in the manifest §3 cleanup sequence.


📌 Team update (2026-06-15T23:52:53+02:00): **ER Direct 45-day free port window** — Jose directive captured and filed to decisions.md. Azure ER Direct ports include a 45-day free provisioning window (covers cross-connect installation lead-time). For labs <45 days, port cost is \\\. Lab #3 Path A cost estimate corrected from ~\/day to ~\-35/day (well within \/day guardrail). Morpheus owns cost guardrail (routing rule #7) + Phase 4 cost gate; must factor the 45-day free window into every ER Direct cost estimate going forward. Trinity to backfill this fact into the Azure Networking vault during Phase 3.4.

