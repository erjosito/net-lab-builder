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

📌 Team update (2026-06-15): Phase 1 manifest design fan-out complete on 2026-06-15; Jose gate pending.
