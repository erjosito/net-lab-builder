# Tank Archive — Detailed Learnings (2026-05-28 to 2026-06-15)

## Lab #1 Cleanup & Charter Integration (2026-05-28)

**6-Step Cleanup Execution Pattern (Charter-Compliant):**

- **Step 1 — ER circuit destruction:** 2s, 2 resources deleted, exit code 0 ✅
- **Step 2 — ER peering verification:** confirmed empty ✅
- **Step 3a — Primary VXC destruction:** 1s, 1 resource deleted, exit code 0 ✅
- **Step 3b — Secondary VXC destruction:** 1s, 1 resource deleted, exit code 0 ✅
- **Step 4 — Megaport MCR destruction:** 2s, 2 resources deleted (MCR + prefix filter), exit code 0 ✅
- **Step 5 — Full terraform destroy:** ~180s, 14 resources deleted (all Azure resources), exit code 0 ✅
- **Step 6 — Final verification:** terraform state empty, Azure RG deleted ✅

**Root Cause Insight:** Windows subprocess environment variable isolation prevented Terraform child processes from accessing Megaport credentials via environment variables; child processes only inherit system-scope and parent-scope variables, not user-scope (HKCU registry).

**Solution Implemented:** Modified Megaport provider block (providers.tf lines 7–10) to accept inline HCL credential arguments with conditional ternary operators, bypassing subprocess isolation by evaluating credentials at parse time before child process spawning. Added megaport_access_key and megaport_secret_key sensitive variables to variables.tf for credential passing.

**Security:** destroy.tfvars deleted; .gitignore updated with *.tfvars and *.tfvars.json patterns.

---

## Lab #2 (vwan-dual-er-symmetric) — IaC Scaffold & Multi-Region Patterns (2026-06-15)

**Files Produced:**
- src/terraform/vwan-dual-er-symmetric/ — 11 .tf files (versions, providers, variables, locals, data, azure-vwan, azure-spokes, azure-expressroute, megaport, gcp, outputs)
- labs/vwan-dual-er-symmetric/deploy/{deploy.ps1, cleanup.ps1} — interactive deploy with Path A/B KV strategy prompt and finally-block ACL restore
- labs/vwan-dual-er-symmetric/deploy-log.md — pre-flight evidence, plan validation status, handoff instructions

**Key IaC Learnings:**

1. **VM SKU catalog drift between regions:** Standard_B2als_v2 available in swedencentral but **NOT in northeurope** (entire B2a*_v2 AMD family absent). **Implement per-region VM size variables (m_size_region_a, m_size_region_b) from day 1 in multi-region labs** — single ar.vm_size is a code smell.

2. **Routing intent dependency ordering:** Must create routing intent BEFORE spoke vHub connections. Explicit depends_on = [azurerm_virtual_hub_routing_intent.hub1, ...hub2] on spoke connections prevents transient propagation gaps.

3. **ER connection naming in v4.x-v5.x:** nable_internet_security renamed to internet_security_enabled for zurerm_express_route_connection. New labs use v5-forward name. **When routing-intent=private is on, ER connections MUST have internet_security_enabled = true** — otherwise ER-learned routes bypass AzFW.

4. **Megaport _end_partner_config for Google:** Uses google_config nested block with pairing_key. Pairing key flows from google_compute_interconnect_attachment.<name>.pairing_key. TF graph correctly orders: GCP attachment → MCR (uid known after MCR creation) → google VXC (consumes pairing_key + mcr uid). No manual depends_on needed.

5. **GCP per-region provider aliasing:** provider "google" { region = var.gcp_region_a } (default) + provider "google" { alias = "region_b" region = var.gcp_region_b }. Every Region B resource gets provider = google.region_b. Without it, all resources land in default provider's region.

6. **MCR prefix_filter_lists deprecation:** Use standalone megaport_mcr_prefix_filter_list resource with mcr_id = megaport_mcr.<name>.product_uid and lifecycle { ignore_changes = [prefix_filter_lists] } on the MCR. Per-region prefix scope via or_each-driven entries: concat([own_region_subnet], var.injected_prefixes). **Cleanest TF expression of "expand scope to break symmetry" perturbation.**

7. **Bow-tie (conditional ER connections):** zurerm_express_route_connection.hub1_circuit2_bowtie with count = var.er_bow_tie_hub1 ? 1 : 0. Default off. **Always reference via 	ry(azurerm_express_route_connection.hub1_circuit2_bowtie[0].id, null) in outputs** — prevents traversal failures when connection is absent.

8. **KV access workaround patterns:** deploy.ps1 implements both Path A (GSA pause) and Path B (ACL flip with try/finally restore). State file .akv-state.json captured BEFORE flip to guarantee restore even on script crash. **inally block + Restore-KvAcl helper is load-bearing.**

9. **Pre-deploy terraform plan with placeholder credentials:** With TF_VAR_megaport_access_key=placeholder, plan fails at Megaport API auth AFTER computing full resource graph, derived names, and inter-resource references. **Expected failure pattern: "Megaport: Unable to Create Megaport API Client → 400" + "google: could not find default credentials"** — these confirm graph builds correctly even when env-time secrets are absent.

10. **GCP Application Default Credentials (ADC):** Separate step from gcloud auth login. Run gcloud auth application-default login (writes %APPDATA%\gcloud\application_default_credentials.json) BEFORE Terraform. gcloud auth list-active account does NOT satisfy Terraform google provider. deploy.ps1 detects missing ADC and prompts.

11. **Permissive AzFW policy requirement:** Routing-intent=private flows require explicit Allow rules covering RFC1918→RFC1918. Default deny silently drops east-west and ER-bound packets, looking exactly like routing failure. Lab #2 ships with irewall_policy_rule_collection_group.lab_allow_all.

12. **Pre-deploy parallelism audit:** Running 	erraform graph and grepping for cross-cloud edges (zurerm_* -> megaport_*, megaport_* -> google_*) takes <1min and surfaces accidental serialization adding 30–60min to wall-clock. Lab #2 confirmed zero cross-cloud serialization. -parallelism=20 flag bumped from default 10 to give headroom for 4 concurrent VXCs at T+~10min.

---

## Lab #2 — Deploy & Patch Lessons (2026-06-15)

**Successfully deployed:** RG g-vwan-symm-103167, GCP project gcp-vwan-symm-103167, 71 TF resources, ~3h15m wall clock with 6 deploy iterations.

### Major Lessons (in order of pain caused)

1. **Megaport TF provider hides API errors as "Still creating..." heartbeats.** 	erraform-provider-megaport v1.10.1 returns 400 from POST /v3/networkdesign/validate within ~2s, but lifecycle emits Still creating… every 10s for 30+ minutes before surfacing failure. **Always run with TF_LOG=DEBUG + TF_LOG_PATH** — DEBUG log shows JSON 400 body (only way to diagnose).

2. **Megaport account market availability is not visible in public locations catalog.** Equinix Stockholm SK1 in public API, but creating MCR there returned {"data":[{"markets":["MEGAPORT_SWEDEN"],"error":"Missing markets: Sweden"}]}. Account lacks MEGAPORT_SWEDEN. Fallback to Equinix Frankfurt FR5 (id 131, MEGAPORT_GERMANY) succeeded. Lab #1 hit same (Madrid/Spain → Frankfurt). **Pre-flight: try throwaway MCR in target PoP via API before committing.**

3. **GCP PARTNER interconnect attachments forbid andwidth field.** google_compute_interconnect_attachment with 	ype = "PARTNER" MUST NOT set andwidth; bandwidth set on Megaport VXC side (ate_limit). Setting it triggers 400: Invalid value for field 'resource.bandwidth'.

4. **GCP PARTNER attachments REQUIRE Cloud Router local ASN = 16550.** google_compute_router.bgp.asn must be 16550 for PARTNER attachments. Trinity's original 65010/65011 ASNs (intended for GCP side) were invalid — 16550 is GCP's published ASN for Partner Interconnect edge. Customer-side MCR ASN (65001/65002) unaffected.

5. **vWAN routing-intent + spoke vhub_connection: connection's outing block MUST be empty.** When zurerm_virtual_hub_routing_intent is configured, any ssociated_route_table_id / propagated_route_table in connection triggers HTTP 400 ConnectionRoutingConfigConflictsWithRoutingIntent. Azure auto-populates from intent. Update future lab templates.

6. **ER GW provisioning + ER connection create can hit 409 AnotherOperationInProgress.** TF parallelism may schedule ER connection create immediately after ER GW post-create reconciliation, returning 409. **Retry on next apply** — conflict is gone (TF idempotency saves). No 	ime_sleep needed if OK with one extra apply cycle.

7. **Killing async 	erraform apply on Windows does NOT reliably run 	ry/finally.** Two KV ACL incidents during this lab: killing PowerShell async wrapper that flipped KV ACL to Allow left inally unexecuted, opening KV for ~10min. **Mitigation:** Pre-flight check in ecover-orphans.ps1 aborts if KV defaultAction != Deny. **Run KV-modifying scripts SYNCHRONOUSLY when possible.**

8. **TF imports must use exact resource address from .tf code.** ecover-orphans.ps1 used zurerm_express_route_gateway.gw_hub1 but code declares .hub1 — import silently skipped. **Always grep .tf for exact resource address before import logic.**

9. **Hub-and-ER GW orphans are inevitable during iteration.** Across runs #2–#4, left 3 long-lived orphans (hub1, ergw-hub1, azfw-hub2). Recover script approach (probe-then-import) worked well. **Right pattern:** (a) use 	erraform apply -target= to provision expensive resources first in known good state, then full apply, or (b) be willing to re-import on every iteration. Chose (b). **To-do for next lab:** fold deploy.ps1 + recover-orphans.ps1 together (make deploy idempotent against orphans via import-first step).

10. **ANSI escape codes in Tee-Object output files break PowerShell string operations.** 	erraform plan/show piped through Tee-Object to file still includes ANSI codes. -match, IndexOf, -like, Select-String on raw file content silently fail. **Strip before processing:** $raw -replace '\x1b\[[0-9;]*[mGKHFJsuA-Za-z]', ''.

11. **KV secret names in platform-secrets-1138 are megaport-api-key, megaport-api-secret, default-password** — NOT abbreviated forms. Using mp-api-key or mp-api-secret returns 3-char error values. Always z keyvault secret list to verify names before fetching.

---

## Lab #2 Patch: Secondary MCR ↔ ER VXCs (2026-06-15T18:55:36+02:00)

**Status:** ✅ COMPLETE — 4 BGP sessions Established (2 per circuit × 2 circuits)

**Root Cause:** Initial lab #2 deploy created only 1 VXC per ER circuit (port_choice = "primary" only). ER private peering is dual-port at MSEE — each circuit has primary and secondary peering endpoint. Both must be wired via separate Megaport VXCs for full HA and dual BGP sessions.

**Fix:** Added megaport_vxc.azure_circuit1_secondary and megaport_vxc.azure_circuit2_secondary with port_choice = "secondary". Targeted apply: 2 added, 0 changed, 0 destroyed.

**Tricky Issue:** First plan attempt triggered cascade replacements (RG + ER circuits) because patch tfvars lacked correlation_id_override = "103167". Without it, Terraform computed local.correlation_id = random_id.correlation.hex = "899b81" (state value) instead of live "103167". **Always lock correlation_id_override when patching live lab where correlation was originally overridden.**

**Verification:**
- Circuit 1 secondary: AS 65001 → 169.254.150.125, BGP Established for 7m16s ✅
- Circuit 2 secondary: AS 65002 → 169.254.148.93, BGP Established for 9m17s ✅

**Charter Rule Added:** "ER private peering is dual-port; always deploy 2 VXCs per circuit, never 1. Validate via gpState=Established ×4 per dual-circuit lab."

---

## Lab #2 Design B Patch: GCP Single GLOBAL-Routing VPC + 2 CRs (2026-06-15)

**Status:** ✅ COMPLETE — 4 apply passes; all 6 GCP resources destroyed; 4 created; Azure ZERO changes.

**Routing-mode in-place migration confirmed:** pc_a REGIONAL→GLOBAL was ~ update in-place in TF plan — critical migration uncertainty resolved favorably. att_a pairing_key preserved; megaport_vxc.gcp_a untouched.

---

## Tool Gotchas & Windows-Specific Patterns

**PowerShell subprocess isolation with Terraform & Megaport:** Environment variables leak scope at child process boundary; ternary-evaluated HCL inline creds bypass this by evaluating at parse time (before child process spawn).

**GCP ADC vs gcloud auth:** Two separate sign-in flows; skipping gcloud auth application-default login is a common miss that delays troubleshooting by 30+ min.

**Megaport market availability and MCR provisioning:** Always pre-flight-test throwaway MCR creation in target PoP via API before committing design.

**vWAN routing-intent ASN/connection/firewall interdependencies:** Missing any of (intent creation before spoke connections, ER.internet_security_enabled, AzFW permissive RFC1918 rules) silently breaks east-west flows with identical symptoms to routing failures.

**TF state file corruption patterns during KV-modifying scripts:** Async wrapper + Stop-Process bypasses inally blocks; pre-flight state snapshot + synchronous execution mitigates.

---

## Design C Insights

Design C represents a "consolidated single-CR migration" pattern: add same-region replacement attachment BEFORE destroying old path to maintain rollback capability.

**Key lessons:**
- **Consolidated migration pattern:** (1) Add tt_b_v2 on router_a (new pairing key, old tt_b_new untouched); (2) Jose re-pairs VXC in portal; (3) verify BGP; (4) THEN destroy old path (Phase 1B). Clean rollback if new pairing fails.
- **AVAILABILITY_DOMAIN_2 on second attachment:** Two benefits — edge diversity AND port exhaustion avoidance. tt_a uses DOMAIN_1; tt_b_v2 DOMAIN_2 means each attachment terminates on different Google edge node. Avoids DOMAIN_1 port exhaustion from recent VXC churn.
- **megaport.tf stays UNTOUCHED in Phase 1A:** state rm pattern defers VXC cleanup to Phase 1B. After Jose manually deletes old VXC and creates new one in portal, Megaport-side VXC no longer represented in TF state. Phase 1B: 	erraform state rm megaport_vxc.gcp_b removes orphaned entry; new resource (or renamed) targets tt_b_v2 pairing key. Touching megaport.tf in Phase 1A triggers VXC destroy+recreate via locked API — hard failure.
- **GOOGLE_OAUTH_ACCESS_TOKEN env var as ADC bypass:** Reliable when ADC file is absent. gcloud auth print-access-token returns short-lived Bearer. Setting $env:GOOGLE_OAUTH_ACCESS_TOKEN satisfies Terraform google provider (~1 hour lifespan; refresh before long-running apply).

**Design C Phase 1A Status:** google_compute_interconnect_attachment.att_b_v2 created in eu-w3 AVAILABILITY_DOMAIN_2, state PENDING_PARTNER. Pairing key: 326ba0de-2aed-4eb2-aaf4-2df34108dc07/europe-west3/2. Jose's portal work (MCR pairing) awaited. Phase 1B destruction (att_b_new + cr_onprem_b) gated on "BGP up" signal.
