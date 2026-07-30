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

🔴 **CRITICAL HARD GATE** (2026-06-16T00:40:00Z, Scribe housekeeping): Tank Phase 3 (C2 apply) must NOT proceed until Niobe confirms **C1 evidence pack completion**. 

**Why this matters:** The GCP Cloud Router snapshot after Tank Phase 2 (C1 apply) is the "Mech C is Azure-only; GCP CR unchanged" proof. This must be captured BEFORE C2 is applied (which adds inbound route maps + hub routing preference, potentially changing CR state). Per Morpheus scope v2 checklist, this is the single highest-severity sequencing risk in the autopilot pipeline.

**Evidence gates required before C2:**
1. Niobe C1 evidence pack: 4-tier symmetric verdict (control-plane, data-plane, AzFW, underlay), with GCP CR snapshot included
2. Explicit Niobe signal: "C1 evidence capture complete"

**Affected**: Tank → must block Phase 3 until gate met. Kid → must flag in blog draft. Trinity → Mech C spec (AS_TRANS, sequential C1→C2) is the trigger for this gate.

---

## Learnings (2026-07-30T15:21:56+02:00)

**Documentation review pass — vwan-routemap-summarization**

Reviewed and updated three lab files after the Phase 3 audit and failover/failback session:

- **validation.md** (Niobe's file): corrected stale self-reference about README gap (now fixed); tightened Phase 2 summary sentence to remove "awaiting Tank/Kid correction" since the fix was applied in this session.
- **README.md**: updated "Designs studied" table (Phase 1 → "Deployed/validated" with cycle count; Phase 2 → "Infrastructure deployed, ER connections active"; Phase 3 → "Not started, confirmed 2026-07-30"). Added Phase 2 resources to "Deployed state" section (ER circuits, ER gateways, GCP VPN sites, kv-pe private endpoint, ER connections).
- **manifest.md**: updated resource inventory table with Phase 2 resources (added Phase column); corrected "Out of scope" section (Phase 2 is deployed, Phase 3 not yet started); added Phase 2 NVA operational note (XFRM persistence gap + startup sequence) to Scenario 3.
- **decisions/inbox/niobe-phase3-audit.md**: added Oracle (Docs) routing note with 4 structural items that are prose/diagram rewrites, out of Niobe's factual-correction scope.

**Items routed to Oracle:** README intro paragraph, manifest topology ASCII, manifest §6 scenario walkthroughs (Phase 2 repro), manifest §2 in-scope statement.

---

## Learnings (2026-07-30T13:48:36+02:00)

**Failover/failback cycle #4 + Phase 2 documentation gap — routemap-test-rg**

1. **Phase 2 fully deployed (documentation gap).** First audit incorrectly reported ER gateways as having no connections because the query used `--query "connections"` instead of `--query "expressRouteConnections"`. The correct field for ExpressRoute gateway connections is `expressRouteConnections`. Both ergw-eu1 and ergw-eu2 have active ER connections (conn-er-eu1 / conn-er-eu2, both Succeeded). README and manifest.md show Phase 2 as "Not started" — this is a documentation gap requiring Tank/Kid action.

2. **XFRM interfaces not persistent across deallocation.** After VMs are deallocated/started, XFRM interfaces (xfrm41/xfrm42, type xfrm, if_id 41/42) are NOT recreated automatically. Must run: `ip link add xfrm41 type xfrm dev eth0 if_id 41; ip link set xfrm41 up; ip route add 192.168.4.12/32 dev xfrm41` (and same for xfrm42/42). Also: `swanctl --load-all` is needed since strongswan-starter uses ipsec.conf (empty) not swanctl.conf. And `swanctl --initiate --child s2sX --ike vngX` needed since `start_action = trap` does not auto-connect.

3. **Failover cycle #4 CLEAN.** hub-eu2/nva2: 6/6 summaries before and after 45s IPsec+BGP teardown and restart. Phase 2 ER routes visible in nva2 BIRD table (192.168.2.0/23 with ER AS paths, 10.100.0.0/24 via GCP ER).

4. **CLI gotcha: ER gateway field.** `az network express-route gateway show --query connections` returns empty. Correct field: `expressRouteConnections`. Confirm with `az network express-route gateway show -g <rg> -n <gw> -o json | findstr -i connection` to see actual field names.

5. **nva1 run-command stuck.** A complex multiline shell script with mixed PowerShell/bash syntax got stuck in the Azure VM run-command extension. The extension locked nva1 for the entire session, blocking all subsequent run-command attempts. Avoid multi-line scripts with `2>/dev/null` piped grep patterns in PowerShell — use @' '@ heredoc and simple single-line commands.

---

## Learnings (2026-07-30T13:35:49+02:00)

**Phase 3 audit — routemap-test-rg live state**

Ran a full live audit of `routemap-test-rg` on 2026-07-30 to answer "are we in Phase 3?"

**Key findings:**
1. **Phase 3 NOT started.** No Azure Firewalls (`az network firewall list` → empty), no Firewall Policies, no Routing Intent on any of the 3 hubs. Hub `azureFirewall = null` and `securityProviderName = null` on hub-us, hub-eu1, hub-eu2. All hubs are non-secured virtual hubs.

2. **Phase 2 infrastructure partially deployed (undocumented).** The RG contains 2 ER circuits (er-eu1/swedencentral, er-eu2/westeurope — both Enabled/Provisioned), 2 ER gateways (ergw-eu1, ergw-eu2 — both Succeeded), 4 VPN sites (onprem1/2 + gcp1/2), and a Key Vault private endpoint. However, both ER gateways have `connections = null` — so Phase 2 is infrastructure-deployed but not operationally connected.

3. **Phase 1 substrate intact.** All 3 hubs Provisioned/Succeeded. Route maps `summarize-out` on hub-eu1 and hub-eu2 (Succeeded); `prepend-in` on hub-eu2 (Succeeded).

4. **Sequencing discrepancy.** Jose wants to jump straight to Phase 3 (Azure Firewall + Routing Intent), but docs sequence Phase 2 first. Phase 2 infra already exists with no connections. Team needs to decide: complete Phase 2 first, or clean-skip to Phase 3.

**CLI gotcha:** `az network vhub routing-intent list` requires `--vhub` (short flag), NOT `--vhub-name`. Using `--vhub-name` returns "argument required: --vhub" error.

**Evidence filed:** show-output/08 (resource inventory), 09 (Phase 3 audit), 10 (Phase 2 ER audit).
**Decisions inbox:** `.squad/decisions/inbox/niobe-phase3-audit.md`

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
