---
updated_at: 2026-08-03T14:05:00+02:00
focus_area: Lab #3 dual-hub-hubless-region-ars — Stage-1 lab card LOCKED
active_issues:
  - Cost guardrail (rule #7) BREACHED at ~$66–72/day > $50/day — explicit Phase-4 cost approval required from Jose before Tank deploys
  - ARS route maps remain PUBLIC PREVIEW; first activation triggers ~30-min one-time Poland ARS upgrade
---

# What We're Focused On

Lab #3 `labs/dual-hub-hubless-region-ars/manifest.md` — Stage-1 lab card locked 2026-08-03. Design proves one workload-aligned Azure Route Server VNet in `polandcentral` acts as the shared BGP control-plane extension for many spokes toward two remote regional hubs (`swedencentral`/`switzerlandnorth`) with a simulated on-prem in `norwayeast`, without adding a third VPN GW/firewall/NVA stack. Sources: `.squad/decisions/inbox/trinity-third-region-ars-design.md` + `dual-hub-preflight.md` (both dated 2026-08-03).

**Fan-out (parallel):** Trinity → `design.md` (BGP walk, effective-route tables, NVA export filter snippets, Δ3 route-map JSON, S2 injection script) · Niobe → S1–S5 diagnostic gate skeleton · Oracle → topology / control-plane / data-plane / cleanup diagrams from lab-card §Regions/Address/ASN · Tank → queued behind Stage-2 manifest + Phase-4 approval gate. No IaC, no Azure writes, until Jose gates cost.
