# Project Context

- **Owner:** Jose Moreno
- **Project:** net-lab-builder — build, document, and tear down ephemeral Azure Networking labs
- **Stack:** Azure CLI (effective routes, flow logs, NSG metrics); Network Watcher; portal screenshots; Bash/PowerShell glue
- **Created:** 2026-05-28
- **Role:** Lab Validator & Diagnostics — own labs/<lab>/{README.md, lessons-learned.md, show-output/, screenshots/, validation.md}; action verb vocabulary; sanitization checklist

## Summary (2026-06-15)

Niobe completed four distinct missions across lab documentation, validation infrastructure, and CLI integrity:

1. **Lab back-fill & charter integration (2026-05-28 to 2026-05-29):** Established output mapping conventions (skill aw-output/ → labs/<lab>/show-output/), created sanitization sweep patterns for secrets (ER keys, Megaport credentials, VM passwords, base64 tokens → placeholder format), and back-filled Lab 1 README with Kid's published blog post link.

2. **Multi-hub ER symmetry validation skeleton (2026-06-15):** Designed seven-layer capture strategy (VM NICs, hub routes via REST, BGP connections, ER circuit tables, MCR looking-glass, GCP Cloud Routers, Azure Firewall logs) for Lab 2 pre-deploy baseline. Key learnings: Lab 1's get-effective-routes anomaly is persistent; route evidence must flow through ER circuit route-tables (MSEE view, not hub REST); routing-intent rollout requires 10–20 min wait before capture; asymmetric-injection testing (forcing stateful drops) is the strongest evidence of symmetry importance.

3. **Lab 2 MCR SPOF analytical proof (2026-06-15):** Captured steady-state route evidence confirming single-path (ER1 carries all 10.50.1.0/24, ER1 secondary carries only MGP-reflected Azure prefixes; ER2 carries all 10.50.2.0/24). Documented tool gotchas: gcloud region lookup, PowerShell JSON escaping with z rest, 10-min z vm run-command latency, Megaport provisioning_status ≠ BGP state.

4. **WSL gcloud validation pass — CLI doc remediation (2026-06-15):** Discovered critical bug (hardcoded pc-onprem → real pc-vwan-symm-a-103167; returns 0 rows unfixed). Established <YOUR_...> placeholder convention. Validated 11 gcloud commands: 8 work as-is, 2 need standardization (peer-name/vpc tokens), 1 needs replacement (get-effective-firewalls deprecated). Ported validation pattern for reuse on cross-platform CLI docs; identified PowerShell bash-quoting conflicts and solutions (temp files, single-command forms).

**Key outputs:** Lab 2 validation skeleton (§6 pre-deploy requirements), WSL test suite + placeholder mapping (§gcloud-wsl-validation-2026-06-15), Windows doc remediation ready (niobe-3 pass 2 pending Jose handoff). Detailed learnings and evidence archived in history-archive.md.

---

📌 Team update (2026-06-15): Windows troubleshooting doc cleanup complete. niobe-3 Pass 1 fixed §0 Conventions + duplicate heading (§6-§9 → §13-§16). Pass 2 synchronized 4 placeholder fixes from validated Linux doc (niobewsl's gcloud-wsl-validation). docs/troubleshooting-commands-windows.md now 29.4 KB, fully self-contained, ready for Jose's PowerShell validation. History file summarized; detailed entries archived. Awaiting Jose's Megaport portal signal (Phase 1B gating) and tank Phase 1B trigger (att_b_new destruction + cr_onprem_b creation).
