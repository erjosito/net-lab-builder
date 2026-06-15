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

---

📌 2026-06-15 — **Lab #2 pre-deploy validation skeleton** (`vwan-dual-er-symmetric`).

**Traffic-symmetry validation pattern (reuse for any multi-hub ER lab):**

1. **Forward-AND-return assertion per firewall.** For every data-plane scenario, assert BOTH directions: (a) source-side FW logs an Allow; (b) destination-side FW logs an Allow; (c) the "wrong" firewall (the one not on the symmetric path) logs ZERO entries. This is the minimal proof of symmetry — one direction alone is not enough.

2. **Asymmetric-injection as a teaching mechanism (S4 pattern).** The strongest evidence that symmetry *matters* is to briefly break it and capture the stateful-drop: SYN accepted by FW-A, return SYN-ACK hits FW-B (no state) → drop. Capture NSG flow logs (SYN visible, no return), Hub1 FW log (drop), Hub2 FW log (accept). Always run injection LAST and always include a revert + re-verify step in the same scenario.

3. **vWAN hub inbound/outbound route REST pattern for ER connections.** The VPN functions in `vwan_2xshub.azcli` (lines 281–300) use `connectionType: VpnConnection`. For ER, substitute `connectionType: ExpressRouteConnection` and use the ER GW connection resource ID. Async pattern: POST → poll Location header until `value` array is non-empty. API version pin: `2025-07-01` (as per dispatch; azcli file uses the older `2022-07-01`).

4. **Seven capture layers for dual-hub ER labs.** Layer A (4 VM NICs), B (6 hub route REST captures), C (4 BGP-connection advertised/learned), D (2 ER circuit route-table JSON), E (2 MCR looking-glass), F (2 GCP Cloud Router), G (2 AzFW KQL). Total ~20 steady-state files + ~10–15 scenario-specific files = ~30–35 total.

5. **Lab #1 anomaly reuse guard.** Lab #1 saw `az network express-route list-route-tables` return `Gateway does not have any Bgp sessions` even on a working circuit (show-output/04, 05). Lab #2 skeleton notes this known anomaly and routes the authoritative route evidence to the vWAN hub effective/inbound/outbound REST calls instead — not to the ER circuit route-table command. The circuit route-table command is still captured (Layer D) but is not used as the primary pass/fail signal for route presence.

6. **Routing-intent propagation delay.** Wait 10–20 min after `vhub` apply before starting route capture. Capturing before RI rollout produces empty or stale tables that look like failures (Trinity gotcha — verified in vwan_2xshub.azcli design notes).

---

📌 Team update (2026-06-15): Phase 1 manifest design fan-out complete on 2026-06-15; Jose gate pending.
