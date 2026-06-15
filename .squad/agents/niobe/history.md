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

---

## Learnings (2026-06-15T23:32:10+02:00)

**MSEE hairpin IPv6 validation skeleton** — Lab: `msee-hairpin-hns-vwan-ipv6`

**Key insights from charter & charter review:**

1. **IPv6 BGP peer-status capture pattern** — When validating dual-stack ER scenarios, capture HnS ER GW peers separately from vWAN hub BGP connections. HnS uses `az network vnet-gateway list-bgp-peer-status` (old VNet GW API); vWAN uses `az network vhub bgpconnection list` (hub API). Both must show IPv4+IPv6 neighbors up before routing captures are valid.

2. **MSEE hairpin validation layers** — Simpler than multi-hub: only two ER GW layers + two ER circuit layers (no Megaport MCR, no vWAN hub REST inbound/outbound). Route-table captures at ER GW (learned+advertised) + ER circuit (list-route-tables) suffice. Three-layer pattern applies; no fourth (MCR) or fifth (vHub REST) layer needed.

3. **Deliberate-break testing (S4 pattern)** — MSEE hairpin is gated by `allowVirtualWanTraffic` toggle on HnS ER GW. Disabling it drops BGP session within 30–60 sec, breaks both IPv4 and IPv6, then re-enabling restores it symmetrically. This is the critical proof of the hairpin mechanism: hairpin exists ⟺ flag is ON. Evidence: before/after BGP peer state + learned routes + data-plane ping.

4. **Pre-flight gates** — Circuits must be `Provisioned` (not just `Enabled`) and both IPv4+IPv6 peering sub-resources must exist on each circuit. BGP peers must be up before route capture. Path A (ER Direct) also requires ER port status = `Succeeded`.

5. **File count expectation** — ~31 files vs ~35 for vwan-dual-er-symmetric (simpler topology, no MCR BGP, no asymmetric-injection Phase A breakage into cross-region flows). Pre-flight 6 + S1 5 + S2 5 + S3 4 + S4-disable 7 + S4-revert 6 = 33 baseline, minus ~2 for reused evidence paths = ~31.

**Validation skeleton structure:**
- Pre-flight checks (subscription, circuits, ER ports, BGP peers) — 6 files
- S1 IPv4 baseline — 5 files (learned-routes, advertised-routes, NIC routes, ping, circuit route-tables)
- S2 IPv6 primary — 5 files (learned-routes IPv6, advertised-routes IPv6, NIC routes, ping, BGP IPv6 peer)
- S3 route-table mutual distribution — 4 files (reuse S1/S2 evidence; add vWAN GW learned/advertised pair)
- S4 deliberate-break (disable + revert) — 13 files (pre-disable baseline, toggle OFF, verify OFF, BGP down, pings fail, learned-routes empty, toggle ON, verify ON, BGP up, pings restored ×2)
- Total: 18.4 KB skeleton; ~31 show-output files when live

**Designs studied section** — Three rows (Path A ER Direct, Path B Megaport fallback, Path C IPsec VPN) with verdicts TBD; evidence links pending; A is "recommended if S1–S2 pass", B is "not recommended per Jose gate", C is "teaching-only (mechanism differs)". This follows rule #30: every design enumerated by Morpheus gets documented.

**Reuse from vwan-dual-er-symmetric** — Assertion table structure (# | Assertion | Command | Expected | Evidence), three-layer checklist pattern, sanitization checklist, post-deploy validation order, BGP peer-status check pattern. Adapted for simpler topology (no MCR, no vHub REST layers) and dual-stack MSEE-only (no GCP multi-region cross-traffic).
