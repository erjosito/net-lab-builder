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
