# Project Context

- **Owner:** Jose Moreno
- **Project:** net-lab-builder — build, document, and tear down ephemeral Azure Networking labs
- **Stack:** Bicep, Terraform, Azure CLI, PowerShell; Megaport API; Azure Key Vault (secret fetch via `az keyvault secret show`)
- **Created:** 2026-05-28
- **Role:** IaC Engineer — own `src/{bicep,terraform,azure-cli,powershell}/` + `labs/<lab>/deploy/`; SKU defaults; 5-step ER cleanup chain (ER connection → ER private peering → Megaport VXCs → Megaport MCR → Azure RG)

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

📌 2026-05-28 — Project initialized. Charter integrated with azure-lab skill IaC reference. Subscription resolution order (routing rule #10): `--subscription` flag → `$AZURE_SUBSCRIPTION_ID` → `az account show --query id -o tsv`. NEVER hardcode subscription/tenant IDs. NEVER commit secrets (rule #11) — Megaport API key fetched at deploy time from Key Vault `platform-secrets-1138`. Wrong cleanup order causes 30–40 min hangs + HTTP 409.

## Cleanup Executions

📌 **2026-06-15 — Mandatory 6-Step Cleanup Execution (Charter Compliance)**  
**Status:** ✅ COMPLETE (all 6 steps verified)  
**Root Cause:** Windows subprocess environment variable isolation prevented Terraform child processes from accessing Megaport credentials via environment variables; child processes only inherit system-scope and parent-scope variables, not user-scope (HKCU registry).  
**Solution:** Modified Megaport provider block (providers.tf lines 7–10) to accept inline HCL credential arguments with conditional ternary operators, bypassing subprocess isolation by evaluating credentials at parse time before child process spawning. Added `megaport_access_key` and `megaport_secret_key` sensitive variables to variables.tf for credential passing.  
**Execution Order (Charter-Compliant):**
- Step 1 (ER circuit destruction): 2s, 2 resources deleted, exit code 0 ✅
- Step 2 (ER peering verification): confirmed empty ✅  
- Step 3a (Primary VXC destruction): 1s, 1 resource deleted, exit code 0 ✅  
- Step 3b (Secondary VXC destruction): 1s, 1 resource deleted, exit code 0 ✅  
- Step 4 (Megaport MCR destruction): 2s, 2 resources deleted (MCR + prefix filter), exit code 0 ✅  
- Step 5 (Full terraform destroy): ~180s, 14 resources deleted (all Azure resources), exit code 0 ✅  
- Step 6 (Final verification): terraform state empty, Azure RG deleted ✅  
**Post-Cleanup Security:**  
- destroy.tfvars deleted (credential file removed)  
- .gitignore updated: added `*.tfvars` and `*.tfvars.json` patterns to prevent credential commits  
**Architectural Decision Deferred:** Megaport credential variables retained in variables.tf as reusable cleanup pattern for future labs (enables faster cleanup automation without re-implementing provider modifications). This decision aligns with Tank's long-term cleanup automation strategy (charter lines 140–157).

---

📌 Team update (2026-05-29): Phase 3.5 governance close — Kid cast (blog-writer 📝), lab #1 blog published, Tank cleanup complete (19/19 resources), squad v0.9.5. Inbox swept (13 decisions → decisions.md).

---

📌 Team update (2026-06-15): Phase 1 manifest design fan-out complete on 2026-06-15; Jose gate pending.

---

📌 **2026-06-15 — Lab #2 (`vwan-dual-er-symmetric`) IaC scaffold + plan validation**
**Status:** ✅ TF stack written and validated; awaiting Jose interactive run of `deploy.ps1` (KV requires operator-mediated GSA pause or ACL flip).
**Files produced:**
- `src/terraform/vwan-dual-er-symmetric/` — 11 .tf files (versions, providers, variables, locals, data, azure-vwan, azure-spokes, azure-expressroute, megaport, gcp, outputs).
- `labs/vwan-dual-er-symmetric/deploy/{deploy.ps1, cleanup.ps1}` — interactive deploy with Path A/B KV strategy prompt and finally-block ACL restore; cleanup supports both single-shot (default) and `-Stepwise` per manifest §8.4.
- `labs/vwan-dual-er-symmetric/deploy-log.md` — pre-flight evidence, plan validation status, handoff instructions.

**Key learnings — multi-region secured-vWAN + dual ER + dual MCR + GCP IaC patterns:**

1. **VM SKU catalog drift between regions is real and probe-time only.** `Standard_B2als_v2` is fully available in `swedencentral` but **NOT in the northeurope catalog at all** (entire B2a*_v2 AMD family absent). Manifest §5.3 had asserted "available in both regions" based on an earlier probe; live re-probe at deploy time disagreed. The Tank charter rule for `Zone + subset blocked → deploy non-zonal` extended naturally: when AMD family is missing entirely → fall back to Intel `B2s_v2` per charter SKU table, AND if that has zone restrictions also deploy non-zonal. **Implement per-region VM size variables (`vm_size_region_a`, `vm_size_region_b`) from day 1 in any multi-region lab** — single `var.vm_size` is a code smell once you cross more than one region.

2. **Routing intent must be created BEFORE spoke vHub connections.** The `azurerm_virtual_hub_connection` resource's `routing` block references `defaultRouteTable`, which exists from hub creation, but routing-intent (private) reshapes how that table is populated. Without explicit `depends_on = [azurerm_virtual_hub_routing_intent.hub1, ...hub2]` on the spoke connections, Terraform may apply spoke connections first and then re-evaluate when intent appears — usually fine but produces transient propagation gaps. Pin the dependency.

3. **`enable_internet_security` is renamed to `internet_security_enabled` in azurerm v4.x for `azurerm_express_route_connection`.** Old form still works (deprecation warning), but new labs should use the v5-forward name. **When routing-intent=private is on, ER connections MUST have `internet_security_enabled = true`** — otherwise ER-learned routes bypass AzFW. (This is the vWAN equivalent of toggling "Propagate Default Route" — but for the in-hub firewall path.)

4. **Megaport `b_end_partner_config` schema for Google uses `google_config` nested block with `pairing_key`.** Mirror of `azure_config` for Azure. The pairing_key flows from `google_compute_interconnect_attachment.<name>.pairing_key` (Terraform google provider exposes it as a computed attribute). **Terraform graph correctly orders: GCP attachment → MCR (uid known after MCR creation) → google VXC (consumes pairing_key + mcr uid)**. No manual `depends_on` needed because the value reference is the dependency.

5. **GCP per-region resources need per-region provider aliases.** `provider "google" { region = var.gcp_region_a }` (default) + `provider "google" { alias = "region_b" region = var.gcp_region_b }`. Every Region B resource gets `provider = google.region_b`. Without aliasing, all resources land in the default provider's region, even when `region = var.gcp_region_b` is on the resource — the *provider* still drives some defaults (e.g. zone selection, quota project).

6. **MCR `prefix_filter_lists` is deprecated on `megaport_mcr` v1.10.x.** Use the standalone `megaport_mcr_prefix_filter_list` resource (with `mcr_id = megaport_mcr.<name>.product_uid`) and `lifecycle { ignore_changes = [prefix_filter_lists] }` on the MCR itself. This pattern from lab #1 carries forward cleanly.

7. **Mechanism A "per-region prefix scope" implementation:** Trinity's design language ("MCR1 permits only Region A's /24") translates to a `for_each`-driven `entries` block where the prefix list is `concat([own_region_subnet], var.injected_prefixes)`. `injected_prefixes = []` is the default scope; Niobe flips `mcr1_injected_prefixes = ["10.50.2.0/24"]` for S4b — a single var change triggers re-apply that mutates ONLY the prefix-filter-list resource, no broader churn. **This is the cleanest TF expression of the "expand the scope to break symmetry" perturbation.**

8. **Bow-tie as `count = var ? 1 : 0` conditional ER connections.** `azurerm_express_route_connection.hub1_circuit2_bowtie` with `count = var.er_bow_tie_hub1 ? 1 : 0`. Default off (manifest §2.4). Niobe sets `er_bow_tie_hub1 = true` to inject the connection for S4a. **Always reference these via `try(azurerm_express_route_connection.hub1_circuit2_bowtie[0].id, null)` in outputs** — otherwise the output traversal fails when the connection is absent.

9. **KV access workaround applied:** deploy.ps1 implements both Path A (GSA pause) and Path B (ACL flip with try/finally restore) per decisions.md 2026-06-15. Path A is the default prompt; Path B requires explicit operator authorization in-script. State file `.akv-state.json` is captured BEFORE the flip so the restore is guaranteed even on script crash. **`finally` block + `Restore-KvAcl` helper is the load-bearing pattern.**

10. **Pre-deploy `terraform plan` with placeholder credentials is a valid graph-validation step.** With `TF_VAR_megaport_access_key=placeholder`, plan fails at Megaport API auth but only AFTER computing the full resource graph, derived names, and inter-resource references. Lab #2's plan validated all 50+ resources, 4-spoke for_each, hub1/hub2 ID propagation through locals, and conditional bow-tie resources. **The expected failure pattern at plan time is "Megaport: Unable to Create Megaport API Client → 400" + "google: could not find default credentials" — these confirm the graph builds correctly even when env-time secrets are absent.**

11. **`google` provider Application Default Credentials are a separate step from `gcloud auth login`.** Run `gcloud auth application-default login` (writes `%APPDATA%\gcloud\application_default_credentials.json`) BEFORE invoking terraform; the `gcloud auth list`-active account does NOT satisfy the Terraform google provider. deploy.ps1 detects missing ADC and prompts.

12. **Permissive AzFW policy is required for routing-intent=private flows to survive.** Without an explicit Allow rule covering RFC1918→RFC1918, AzFW's default deny silently drops every east-west and ER-bound packet, looking exactly like a routing failure. Lab #2 ships with `firewall_policy_rule_collection_group.lab_allow_all` permitting Any/Any between RFC1918 ranges — narrow enough that internet egress (deliberately not in scope) is unaffected, broad enough that all symmetry scenarios can be observed.

- **Pre-deploy parallelism audit is cheap and high-signal for multi-cloud labs.** Running `terraform graph` and grepping for cross-cloud edges (`azurerm_* -> megaport_*` or `megaport_* -> google_*`) before apply takes <1min and surfaces accidental serialization that would otherwise add 30-60min to wall-clock. For lab #2, the audit confirmed zero cross-cloud serialization — Megaport (~15min) and GCP (~10min) work runs fully absorbed inside the vHub long pole (~25-30min). `-parallelism=20` flag bumped from default 10 in deploy.ps1 to give headroom for the 4 concurrent VXCs at T+~10min.

## Lab #2 (vwan-dual-er-symmetric) — deploy lessons (2026-06-15)

**Successfully deployed:** RG `rg-vwan-symm-103167`, GCP project `gcp-vwan-symm-103167`, 71 TF resources, ~3h15m wall clock with 6 deploy iterations.

### Major lessons (in order of pain caused)

1. **Megaport TF provider hides API errors as "Still creating..." heartbeats.** `terraform-provider-megaport v1.10.1` returns a 400 from `POST /v3/networkdesign/validate` within ~2 seconds, but the lifecycle then emits `Still creating…` every 10s for 30+ minutes before surfacing the failure. **Always run with `TF_LOG=DEBUG` + `TF_LOG_PATH` when any megaport_mcr/megaport_vxc is in the dependency graph.** The DEBUG log shows the JSON 400 body, which is the only way to diagnose a "hang".

2. **Megaport account market availability is not visible in the public locations catalog.** `Equinix Stockholm SK1` (id 95) is in the public locations API, but creating an MCR there returned `{"data":[{"markets":["MEGAPORT_SWEDEN"],"error":"Missing markets: Sweden"}]}`. Our account does NOT have `MEGAPORT_SWEDEN` enabled. Fallback to `Equinix Frankfurt FR5` (id 131, `MEGAPORT_GERMANY`) succeeded. **Lab #1 hit the same with Madrid/Spain → Frankfurt; this is a recurring pattern.** Pre-flight: try creating a throwaway MCR in the target PoP via API before committing to the design.

3. **GCP PARTNER interconnect attachments forbid the `bandwidth` field.** `google_compute_interconnect_attachment` with `type = "PARTNER"` must NOT set `bandwidth`; bandwidth is set on the Megaport VXC side (`rate_limit`). Setting it triggers `400: Invalid value for field 'resource.bandwidth'`.

4. **GCP PARTNER attachments REQUIRE Cloud Router local ASN = 16550.** `google_compute_router.bgp.asn` must be 16550 for the router to serve PARTNER attachments. Trinity's original 65010/65011 ASNs (intended for the GCP side) were invalid — 16550 is GCP's published ASN for Google's Partner Interconnect edge. Customer-side BGP peer ASN (MCR side via `mcr1_asn` / `mcr2_asn`) is unaffected; lab still has 65001/65002 on the Megaport side.

5. **vWAN routing-intent + spoke vhub_connection: the connection's `routing` block MUST be empty.** When `azurerm_virtual_hub_routing_intent` is configured, any `associated_route_table_id` / `propagated_route_table` in `azurerm_virtual_hub_connection` triggers `HTTP 400 ConnectionRoutingConfigConflictsWithRoutingIntent: Leave Routing configuration empty to auto-populate`. Azure auto-populates the route-table associations from the intent. Update lab #2 design + future lab templates.

6. **ER GW provisioning + ER connection create can hit 409 AnotherOperationInProgress.** When TF parallelism schedules ER connection create immediately after the ER GW finishes its post-create reconciliation, Azure returns 409. **Retry on the next apply** — the next apply re-evaluates and the conflict is gone (TF idempotency saved us here). No need for `time_sleep` if you're OK with one extra apply cycle.

7. **Killing an async `terraform apply` on Windows does NOT reliably run `try/finally`.** Two earlier KV ACL incidents during this lab were caused by killing a PowerShell async wrapper that had flipped the KV ACL to Allow inside a `try`. The `finally` never ran, leaving KV open for ~10 min before I caught it. **Mitigation in place**: pre-flight check in `recover-orphans.ps1` that aborts if KV `defaultAction != Deny` (refuses to capture an anomalous state as the "new" snapshot). Always run KV-modifying scripts SYNCHRONOUSLY when possible; async + Stop-Process = broken finally.

8. **TF imports must use the exact resource address from .tf code.** My `recover-orphans.ps1` used `azurerm_express_route_gateway.gw_hub1` but the code declares `.hub1` — the import was silently skipped because the conditional ` -notcontains 'gw_hub1'` was always true (no resource of that name to find), so import ran and failed (or was skipped). **Always grep the .tf for the exact resource address before writing import logic.**

9. **Hub-and-ER GW orphans are inevitable during iteration.** Across runs #2-#4, I left 3 long-lived orphans (hub1, ergw-hub1, azfw-hub2). The recover script approach (probe-then-import) worked well — but the right pattern is to either (a) use `terraform apply -target=` to provision the expensive resources first in a known good state, then run full apply, or (b) be willing to re-import on every iteration. We chose (b).

10. **deploy.ps1 vs recover-orphans.ps1**: I created the recover script ad-hoc when deploy.ps1 hit its first failure. In retrospect, deploy.ps1 should subsume the recover logic — make it idempotent against orphans by always running an "import-anything-orphaned" step before apply. To-do for next lab: fold these scripts together.

---

📌 **2026-06-15T18:55:36+02:00 — Lab #2 patch: secondary MCR ↔ ER VXCs added**

**Status:** ✅ COMPLETE — 4 BGP sessions Established (2 per circuit × 2 circuits)

**Root cause of miss:** Initial lab #2 deploy created only 1 VXC per ER circuit (`port_choice = "primary"` only). ER private peering is dual-port at the MSEE — each circuit has a primary and secondary peering endpoint (two distinct physical ports). Both must be wired via separate Megaport VXCs for full HA and dual BGP sessions. Jose caught this by observing only one active connection per circuit in the portal.

**Fix:** Added `megaport_vxc.azure_circuit1_secondary` and `megaport_vxc.azure_circuit2_secondary` with `port_choice = "secondary"` to `megaport.tf`. Targeted apply: 2 added, 0 changed, 0 destroyed.

**Tricky issue during patch:** First plan attempt triggered cascade replacements (RG + ER circuits) because the patch tfvars didn't include `correlation_id_override = "103167"`. Without it, Terraform computed `local.correlation_id = random_id.correlation.hex = "899b81"` (the value in state) instead of the live `"103167"` that was used during the original deploy. Always lock `correlation_id_override` when patching a live lab where the correlation was originally overridden.

**Verification:**
- Circuit 1 (Stockholm) secondary: AS 65001 → 169.254.150.125, BGP Established for 7m16s ✅
- Circuit 2 (Amsterdam) secondary: AS 65002 → 169.254.148.93, BGP Established for 9m17s ✅
- Total BGP sessions: 4 (2 primary + 2 secondary) — meets Trinity §1.5 + S1.1 ✅

**Charter rule added:** "ER private peering is dual-port; always deploy 2 VXCs per circuit, never 1. Validate via `bgpState=Established ×4` per dual-circuit lab."
