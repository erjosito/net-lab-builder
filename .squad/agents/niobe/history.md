# Project Context

- **Owner:** Jose Moreno
- **Project:** net-lab-builder — build, document, and tear down ephemeral Azure Networking labs
- **Stack:** Azure CLI (effective routes, flow logs, NSG metrics); Network Watcher; portal screenshots; Bash/PowerShell glue
- **Created:** 2026-05-28
- **Role:** Lab Validator & Diagnostics — own `labs/<lab>/{README.md, lessons-learned.md, show-output/, screenshots/, validation.md}`; action verb vocabulary; sanitization checklist

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

📌 2026-05-28 — Project initialized. Charter integrated with azure-lab skill validation reference. Output mapping: skill's `raw-output/` → `labs/<lab>/show-output/`; skill's `diagrams/` → `labs/<lab>/diagrams/`; skill's repo-root `README.md` → `labs/<lab>/README.md`. Always run sanitization sweep before commit: redact ER service keys, Megaport secrets, VM admin passwords, base64 access keys, subscription IDs → `<SUBSCRIPTION_ID>`, tenant IDs → `<TENANT_ID>`.

📌 2026-05-29 — **Lab 1 README back-fill**: expressroute-megaport-bgp lab README line 3 placeholder replaced with Kid's published post link (title: "The route table that didn't lie: diagnosing ExpressRoute BGP with the Azure CLI", published 2026-05-29, GitHub URL: `https://github.com/erjosito/azure-networking-blog/tree/main/2026-05-expressroute-megaport-bgp`). Sanitization verified: no subscription GUIDs or tenant IDs in lab directory. Back-fill follows coordinator dispatch and charter §"Collaboration → Lab documentation back-fill". Scope: one-line README edit only.

---

📌 Team update (2026-05-29): Phase 3.5 governance close — Kid cast (blog-writer 📝), lab #1 blog published, Tank cleanup complete (19/19 resources), squad v0.9.5. Inbox swept (13 decisions → decisions.md).
