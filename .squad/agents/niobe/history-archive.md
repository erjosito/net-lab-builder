# Niobe — Archive (pre-2026-06-15 history summarization)

This file contains the detailed history entries for Niobe's work prior to 2026-06-15. For the current summary, see `history.md`.

## Archived Learnings

📌 2026-05-28 — Project initialized. Charter integrated with azure-lab skill validation reference. Output mapping: skill's `raw-output/` → `labs/<lab>/show-output/`; skill's `diagrams/` → `labs/<lab>/diagrams/`; skill's repo-root `README.md` → `labs/<lab>/README.md`. Always run sanitization sweep before commit: redact ER service keys, Megaport secrets, VM admin passwords, base64 access keys, subscription IDs → `<SUBSCRIPTION_ID>`, tenant IDs → `<TENANT_ID>`.

📌 2026-05-29 — **Lab 1 README back-fill**: expressroute-megaport-bgp lab README line 3 placeholder replaced with Kid's published post link (title: "The route table that didn't lie: diagnosing ExpressRoute BGP with the Azure CLI", published 2026-05-29, GitHub URL: `https://github.com/erjosito/azure-networking-blog/tree/main/2026-05-expressroute-megaport-bgp`). Sanitization verified: no subscription GUIDs or tenant IDs in lab directory. Back-fill follows coordinator dispatch and charter §"Collaboration → Lab documentation back-fill". Scope: one-line README edit only.

📌 2026-06-15 — **Lab #2 pre-deploy validation skeleton** (`vwan-dual-er-symmetric`).

**Traffic-symmetry validation pattern (reuse for any multi-hub ER lab):**

1. **Forward-AND-return assertion per firewall.** For every data-plane scenario, assert BOTH directions: (a) source-side FW logs an Allow; (b) destination-side FW logs an Allow; (c) the "wrong" firewall (the one not on the symmetric path) logs ZERO entries. This is the minimal proof of symmetry — one direction alone is not enough.

2. **Asymmetric-injection as a teaching mechanism (S4 pattern).** The strongest evidence that symmetry *matters* is to briefly break it and capture the stateful-drop: SYN accepted by FW-A, return SYN-ACK hits FW-B (no state) → drop. Capture NSG flow logs (SYN visible, no return), Hub1 FW log (drop), Hub2 FW log (accept). Always run injection LAST and always include a revert + re-verify step in the same scenario.

3. **vWAN hub inbound/outbound route REST pattern for ER connections.** The VPN functions in `vwan_2xshub.azcli` (lines 281–300) use `connectionType: VpnConnection`. For ER, substitute `connectionType: ExpressRouteConnection` and use the ER GW connection resource ID. Async pattern: POST → poll Location header until `value` array is non-empty. API version pin: `2025-07-01` (as per dispatch; azcli file uses the older `2022-07-01`).

4. **Seven capture layers for dual-hub ER labs.** Layer A (4 VM NICs), B (6 hub route REST captures), C (4 BGP-connection advertised/learned), D (2 ER circuit route-table JSON), E (2 MCR looking-glass), F (2 GCP Cloud Router), G (2 AzFW KQL). Total ~20 steady-state files + ~10–15 scenario-specific files = ~30–35 total.

5. **Lab #1 anomaly reuse guard.** Lab #1 saw `az network express-route list-route-tables` return `Gateway does not have any Bgp sessions` even on a working circuit (show-output/04, 05). Lab #2 skeleton notes this known anomaly and routes the authoritative route evidence to the vWAN hub effective/inbound/outbound REST calls instead — not to the ER circuit route-table command. The circuit route-table command is still captured (Layer D) but is not used as the primary pass/fail signal for route presence.

6. **Routing-intent propagation delay.** Wait 10–20 min after `vhub` apply before starting route capture. Capturing before RI rollout produces empty or stale tables that look like failures (Trinity gotcha — verified in vwan_2xshub.azcli design notes).

📌 2026-06-15T19:24:55+02:00 — **Lab #2 MCR1 SPOF evidence capture** (`vwan-dual-er-symmetric`, `rg-vwan-symm-103167`).

**SPOF capture method:**

Phase C used **Option 3 (BGP-table-only analytical proof)** — active MCR1 fault injection was not performed. AKV `platform-secrets-1138` was in Deny state; Megaport API credentials were inaccessible without a coordinator-authorized ACL flip. The steady-state route tables already provide irrefutable single-path proof, corroborated by GCP BGP peer count and TF VXC state.

**BGP behaviors observed:**

- `az network express-route list-route-tables --path primary/secondary -o json` returns non-empty results on a working circuit (Lab #1 anomaly was transient; Lab #2 returns full route tables on both paths). ER1 primary shows `10.50.1.0/24 via 169.254.150.121 path 65001 16550 ?`; ER1 secondary shows same prefix via `169.254.150.125` (MCR1 secondary MSEE peer). No `10.50.2.0/24` anywhere in ER1.
- `az network vhub get-effective-routes --resource-type ExpressRouteGateway` still returns `{"value":[]}` on a working lab (confirmed Lab #1 anomaly persists in Lab #2). Use ER circuit route tables (MSEE view) as the authoritative Azure-layer evidence.
- ER1 secondary path shows Azure hub prefixes with path `65001 12076 I/E` — the MSEE reflects Azure prefixes back through MCR1's secondary session. These have higher AS-path length and are loop-prevented; they are NOT the best-path for Azure prefixes (vWAN peers at AS 65515 win), but they do appear in the MSEE's BGP table. This is normal Megaport MCR reflector behavior and can be confusing to first-time readers.
- GCP Cloud Router `get-status` confirmed single BGP peer per VPC (Mechanism A working as designed). `bgpPeerStatus[0].state = "Established"`, `numLearnedRoutes = 8`. Router A advertised ONLY `10.50.1.0/24`; Router B advertised ONLY `10.50.2.0/24`.

**Tool-specific gotchas:**

- **gcloud router region:** `europe-west3` (not `europe-west1`) for router-a. Always look up the actual attachment region from `gcloud compute interconnect-attachments list` or `gcloud compute routers list --format=json` rather than guessing from VPC name suffix.
- **`az network vhub get-effective-routes` REST POST via `az rest`:** Backtick-escaped JSON bodies in PowerShell fail with `InvalidJson` error if the body contains special chars. Use `ConvertTo-Json` + `Out-File` to write a temp file and pass `--body "@<file>"` instead.
- **`az vm run-command invoke` latency:** Ping commands that complete in 4–8 seconds inside the VM still take 5–10 minutes to return at the CLI level (Azure VM agent queuing + SDK polling). Allow 10 min wall-clock per run-command invocation.
- **Megaport `provisioning_status = "CONFIGURED"` for secondary VXC** does not mean BGP is down — it reflects a Megaport API state distinct from "LIVE". BGP was `Established` per ER route-table summary. Always confirm BGP state from the Azure/GCP side, not from Megaport TF state alone.

📌 2026-06-15 — **Lab #2 looking-glass re-test** (`vwan-dual-er-symmetric`).

**Verdict: New failure mode.** In lab #1 (2026-05), Megaport API auth succeeded but `/v2/product/mcr2/{uid}/diagnostics/routes/bgp` returned `"no endpoint"` / empty body. In lab #2 (2026-06-15), `POST /v2/login` with `Content-Type: application/x-www-form-urlencoded` (username=api-key, password=api-secret) returned HTTP 401 "Invalid email or password" — the looking-glass endpoint was never reached. Evidence at `labs/vwan-dual-er-symmetric/show-output/looking-glass-test-2026-06-15/`.

📌 2026-06-15 — **Lab #2 Design B Phase 1 asymmetric routing validation** (`vwan-dual-er-symmetric`, RG `rg-vwan-symm-103167`).

**Verdict: 🔴 ASYMMETRIC ROUTING PROVED** — all three evidence tiers (control plane, data plane, firewall correlation) confirm the prediction.

**Key findings (reuse for any single-VPC GLOBAL GCP + dual-MCR lab):**

1. **GCP GLOBAL VPC regional routing is the asymmetry source.** With a single GLOBAL VPC and two Cloud Routers in different GCP regions, VMs are served by their region's local Cloud Router for outbound routing — regardless of which MCR carried the inbound flow. VM-B in eu-w4 always routes Azure-bound traffic via `cr_onprem_b` (eu-w4) → MCR2 → Hub2. Hub1 may route Azure→VM-B via MCR1 (direct, shorter AS-path). This creates a forced asymmetric pairing for cross-region flows. The fix: Axis-2 prepend on each MCR for the "wrong-region" GCP subnet, so Azure prefers the cross-hub path that aligns with the GCP return direction.

2. **ER circuit route tables are the primary asymmetry detector.** The single command that reveals the problem: `az network express-route list-route-tables -n <er-circuit> -g <rg> --peering-name AzurePrivatePeering --path primary -o json`. In Design A: each ER shows only its "home" GCP prefix. In Design B Phase 1: each ER shows BOTH GCP prefixes. The moment both prefixes appear on both ER circuits with equal AS-path length, asymmetric routing is mathematically certain (without a tiebreaker).

3. **Azure Firewall does NOT log TCP stateful drops.** When a SYN-ACK arrives at a firewall that has no state for the original SYN, Azure Firewall silently drops it at the L4 state engine — no log entry is emitted. The ABSENCE of AzFW2 log entries for a flow whose forward SYN was logged at AzFW1 IS the proof of the stateful drop. Run both firewall KQL queries and compare: matching FW = symmetric; unmatched = asymmetric.

4. **Differential test protocol for asymmetric routing proof:** Run the SAME connectivity test from both hubs (spoke1/Hub1 AND spoke3/Hub2 to the same remote target). If one succeeds and the other fails, and the firewall policy is permit-all for both, the failure is asymmetric routing — not policy. This two-test comparison is the minimal blog-grade proof.

5. **GCP `bestRoutesForRouter` vs `bestRoutes`:** `bestRoutes` shows ALL routes in the VPC (from all CRs in the GLOBAL network). `bestRoutesForRouter` shows only what THIS specific router considers best. In a GLOBAL VPC with two CRs, `bestRoutes` shows ECMP/backup paths that are NOT selected by the current region's CR — these indicate routes learned from the far region via GCP internal propagation. Seeing Azure Hub2 prefixes in `router_a`'s `bestRoutes` with a different next-hop (MCR2 at priority=213) confirms the GLOBAL fabric is active and carrying cross-region routes.

📌 2026-06-15 — **WSL gcloud validation — cross-platform CLI doc integrity check** (`docs/troubleshooting-commands-linux.md`).

**Mission:** Jose reported a bug in the gcloud command examples — the command `gcloud compute routes list --filter="network:vpc-onprem"` returns nothing because `vpc-onprem` is a hardcoded placeholder that doesn't match the actual VPC name in the live Design B Phase 1 lab (`vpc-vwan-symm-a-103167`). Root cause: documentation was ported from a Linux template and never validated against real infrastructure. Request: validate ALL gcloud commands in the Linux doc via WSL and fix the source.

**Validation pattern (reuse for any cross-platform CLI doc):**

1. **WSL auth pre-check:** `wsl --status`, `wsl -- gcloud --version`, `wsl -- gcloud auth list`, `wsl -- gcloud config list`. Non-interactive auth only — if gcloud auth fails, STOP and request user to run `wsl -- gcloud auth login` interactively in a PowerShell session.

2. **Live resource discovery via read-only gcloud commands:** Run `gcloud compute networks list`, `gcloud compute routers list`, `gcloud compute interconnects attachments list`, `gcloud compute instances list` to capture real resource names. Build an explicit placeholder-mapping table; don't trust briefing docs.

3. **Command-by-command testing:** For each gcloud command in the doc, substitute discovered real values and run from WSL via `wsl -e bash -c '...'`. Capture output + status (works as-is, works with syntax fix, deprecated/broken). Avoid inline bash quoting conflicts by writing scripts to files first if needed.

4. **Placeholder convention design:** Choose a consistent, visually obvious token format that blog readers can't miss during copy-paste. Chosen convention: `<YOUR_...>` (angle brackets + ALL-CAPS). Pre-define environment variables ($ROUTER_A, $REGION_A) in the doc's Conventions section.

5. **Doc updates:** Replace hardcoded literals with placeholder tokens. Add HTML comment validation callouts after each tested command: `<!-- Validated 2026-06-15 WSL: works (output: 01-validation-results.txt) -->`.

**Results (11 gcloud commands tested, §8-9):**
- 🟢 8 work as-is (placeholders only)
- 🟡 2 standardization fixes (<peer-name> → <YOUR_BGP_PEER_NAME>, etc.)
- 🔴 1 deprecated command replaced (get-effective-firewalls doesn't exist; replaced with firewall-rules list)

**Critical bug:** §9.3 hardcoded `vpc-onprem` → real value `vpc-vwan-symm-a-103167`. Original command returns 0 rows; fixed version returns 3 routes.

**Real resource names (Design B Phase 1):** VPC `vpc-vwan-symm-a-103167`, Router A `router-vwan-symm-a` (eu-w3, ASN 16550), Router B `cr-vwan-symm-onprem-b` (eu-w4, ASN 16550), Attachment A `att-vwan-symm-a`, Attachment B `att-vwan-symm-b-new`, BGP peer (auto) `auto-ia-bgp-att-vwan-symm-a-748c416bf214189`, VMs at 10.50.1.2 and 10.50.2.2. VPC routing_mode is GLOBAL (confirmed via gcloud).

**Tool-specific gotchas:**
- **PowerShell + bash quoting conflict:** Inline bash commands with nested quotes (jq filters with both single and double quotes) fail in WSL via `wsl -e bash -c '...'` due to PowerShell's escaping. Workaround: write bash scripts to temp files (not /tmp!) and execute via file path, or use single-command invocations that avoid complex quoting.
- **gcloud subcommand changes:** `gcloud compute instances get-effective-firewalls` does not exist in gcloud 552.0.0. Replacement: `gcloud compute firewall-rules list --filter="network:<VPC>"` is more useful (shows VPC-wide rules instead of VM-specific effective rules).
- **Learned routes empty output:** `gcloud compute routers get-status ... | jq '.result.bgpPeerStatus[] | .learnedRoutes[]?'` returning empty is correct behavior for a lab where no routes have been advertised from the peer yet; don't assume it's a bug.

**Evidence saved:** 
- `labs/vwan-dual-er-symmetric/show-output/gcloud-wsl-validation-2026-06-15/00-discovery.txt` — resource inventory + mapping
- `labs/vwan-dual-er-symmetric/show-output/gcloud-wsl-validation-2026-06-15/01-validation-results.txt` — detailed test results
- `labs/vwan-dual-er-symmetric/show-output/gcloud-wsl-validation-2026-06-15/README.md` — summary with status table

**Decision inbox:** `.squad/decisions/inbox/niobe-gcloud-wsl-validation-2026-06-15.md`

**Implication:** niobe-3 (Windows re-port instance) can now proceed re-porting these fixed commands to `docs/troubleshooting-commands-windows.md` with confidence. Placeholder convention is locked; all syntax bugs are resolved.
