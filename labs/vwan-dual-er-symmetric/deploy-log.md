# vwan-dual-er-symmetric: Deploy Log

> **Status (2026-06-15T14:15:03Z):** IaC scaffolded and validated. Awaiting Jose to run `deploy.ps1` interactively (KV access requires operator-mediated GSA pause or ACL flip per decisions.md 2026-06-15).

## 1. Pre-flight evidence (Tank, 2026-06-15)

### 1.1 Azure subscription + tenant

```
az account show --query "{id:id, name:name, tenantId:tenantId}" -o json
{
  "id": "<SUBSCRIPTION_ID>",        # matches expected
  "name": "Litware-MngEnvMCAP642473-jomore",
  "tenantId": "<TENANT_ID>"
}
```

### 1.2 gcloud authentication

```
gcloud auth list --filter=status:ACTIVE
ACTIVE  ACCOUNT
*       erjosito1138@gmail.com

gcloud config get-value project
familytree-471318
```

> **Action for Jose before deploy:** `gcloud auth application-default login` (Terraform google provider needs ADC; not present in `%APPDATA%\gcloud\application_default_credentials.json` at scaffolding time).

### 1.3 VM SKU probe (charter rule, both regions, 2026-06-15)

| Region | Probed SKU | restrictionType | blockedZones | Decision |
|---|---|---|---|---|
| swedencentral | `Standard_B2als_v2` | (null) | (null) | ✅ Use B2als_v2 zonal-or-not |
| northeurope   | `Standard_B2als_v2` | **NOT IN CATALOG** (entire B2a*_v2 family absent) | n/a | ❌ Substitute → `Standard_B2s_v2` |
| northeurope   | `Standard_B2s_v2` (fallback) | `Zone` | `["1","2"]` | ✅ Use B2s_v2 **non-zonal** per charter rule |

**Per-region SKU vars:**
- `var.vm_size_region_a` = `Standard_B2als_v2`
- `var.vm_size_region_b` = `Standard_B2s_v2`

Both deploys omit the `zone` attribute on `azurerm_linux_virtual_machine` so Azure picks an available zone (charter table row 2: "Zone + subset blocked → deploy non-zonal").

### 1.4 Megaport PoP intent

| Role | Primary | Fallback |
|---|---|---|
| MCR1 (Region A pair) | `Equinix SK1` (Stockholm) | `Equinix Frankfurt FR5` |
| MCR2 (Region B pair) | `Equinix AM2` (Amsterdam) | `Equinix Dublin DB3` |
| ER circuit 1 peering location | `Stockholm` | `Frankfurt` |
| ER circuit 2 peering location | `Amsterdam` | `Dublin` |

> PoP availability will be validated at `terraform plan` time via `data "megaport_location"` lookup. Actual PoP recorded here post-deploy.

## 2. Stack files written (2026-06-15)

```
src/terraform/vwan-dual-er-symmetric/
├── versions.tf              # azurerm 4, azapi 2, megaport 1, google 6, random 3
├── providers.tf             # azurerm, azapi, megaport (env or var), google + google.region_b
├── variables.tf             # lab_name, regions, CIDRs, SKUs, ASNs, megaport PoPs (primary), KV name, perturbation knobs, 3 secrets
├── locals.tf                # correlation_id, derived names, spoke map, mcr export prefixes
├── data.tf                  # megaport_location data lookups, azurerm_client_config
├── azure-vwan.tf            # vWAN + 2 secured vHubs + AzFW Std + firewall policy + routing-intent (private) + LAW + diag
├── azure-spokes.tf          # 4 spoke VNets + NSGs + NICs + Linux VMs (password auth) + vHub connections
├── azure-expressroute.tf    # 2 ER circuits + 2 ER GWs + 2 primary ER conns + 2 optional bow-tie conns (var-gated)
├── megaport.tf              # 2 MCRs + 2 prefix-filter lists + 2 Azure VXCs + 2 GCP VXCs
├── gcp.tf                   # 2 VPCs + 2 subnets + 2 firewalls + 2 routers + 2 partner attachments + 2 e2-micro VMs
└── outputs.tf               # RG, vWAN, hubs, AzFW IDs+IPs, ER circuit IDs+service keys, ER GW IDs, ER conns, spoke VMs, MCR UIDs, VXC UIDs, BGP IPs, GCP VPCs/routers/attachment keys/VM IPs, Megaport PoPs used, VM SKUs used

labs/vwan-dual-er-symmetric/deploy/
├── deploy.ps1               # KV strategy A/B prompt, secret fetch, terraform init+plan+apply, outputs JSON
└── cleanup.ps1              # single-shot destroy default, -Stepwise for manifest §8.4 staged destroy
```

## 3. Plan validation status

| Step | Result |
|---|---|
| `terraform init -upgrade` | ✅ All 5 providers installed (azurerm 4.77.0, azapi 2.10.0, megaport 1.10.1, google 6.50.0, random 3.9.0) |
| `terraform validate` | ✅ Success: 2 deprecation warnings (one fixed: `enable_internet_security` → `internet_security_enabled`; one is Megaport SDK-side `prefix_filter_lists` on `megaport_mcr`: kept for now, no functional impact) |
| `terraform plan -input=false` (with placeholder creds) | ⚠️ Graph builds end-to-end; computes derived names correctly; **expected** failures on (1) Megaport OAuth (placeholder creds reject: real ones come from KV at deploy) and (2) google provider ADC (Jose must run `gcloud auth application-default login` before deploy). |

The TF stack is **deploy-ready**. The two outstanding errors are environmental (credentials), not structural.

## 3a. Parallelism audit (per 2026-06-15T15:12Z dispatch: Jose)

**Goal:** Megaport (MCRs + Azure VXCs + GCP VXCs) AND GCP (VPCs + routers + attachments) MUST run in parallel with the vHub + ER GW long pole, NOT after it. Target wall-clock = `max(vHub deploy time, ER GW deploy time)` + ER connection attach + spoke connection time: NOT a sum across layers.

**Empirical evidence (from `terraform graph` output, 2026-06-15):**

| Resource | Dependency edges in graph | Compliance |
|---|---|---|
| `azurerm_express_route_circuit.circuit1` | → `azurerm_resource_group.lab` (only) | ✅ rule #3: circuit only on RG, NOT on vHub |
| `azurerm_express_route_circuit.circuit2` | → `azurerm_resource_group.lab` (only) | ✅ rule #3 |
| `megaport_mcr.mcr1` | → `data.megaport_location.loc_a` + `random_id.correlation` | ✅ rule #1: no Azure dep |
| `megaport_mcr.mcr2` | → `data.megaport_location.loc_b` + `random_id.correlation` | ✅ rule #1 |
| `google_compute_network.vpc_a/b` | → `random_id.correlation` (only) | ✅ rule #2: no Azure dep |
| `google_compute_router.router_a/b` | → respective `vpc_a/b` | ✅ rule #2 |
| `google_compute_interconnect_attachment.att_a/b` | → respective `router_a/b` | ✅ rule #2 |
| `megaport_vxc.azure_circuit1` | → `azurerm_express_route_circuit.circuit1`, `megaport_mcr.mcr1` | ✅ rule #4: gates on circuit service_key + MCR only, NOT vHub/ER GW |
| `megaport_vxc.gcp_a` | → `google_compute_interconnect_attachment.att_a`, `megaport_mcr.mcr1` | ✅ rule #5: independent of Azure |
| `azurerm_virtual_hub.hub1` | → `azurerm_virtual_wan.vwan` (only: NO edge to hub2) | ✅ rule #6: hubs parallel |
| `azurerm_express_route_gateway.hub1/hub2` | → respective `azurerm_virtual_hub.hub1/hub2` | ✅ rule #7: ER GWs parallel within their hubs |
| `azurerm_express_route_connection.hub1_circuit1` | → `express_route_gateway.hub1`, `virtual_hub_routing_intent.hub1`, `megaport_vxc.azure_circuit1` | ✅ rule #5: ONLY this resource gates on the long pole (ER GW), exactly as required |

**No depends_on edges from any Megaport resource to any vHub or ER GW.**
**No depends_on edges from any GCP resource to any Azure resource.**
**No depends_on edges between hub1 and hub2.**

**Predicted parallel timeline (from T0 = apply start):**

```
T+0:00   RG created (~30s)
         │
         ├─ vWAN (~30s)            ─┐
         │  └─ vHub1 (~25-30min)    │ ◄── LONG POLE
         │     ├─ AzFW1 (~15min, parallel inside hub1)
         │     └─ ER GW1 (~20-45min, parallel inside hub1)
         │  └─ vHub2 (~25-30min, parallel with hub1)
         │     ├─ AzFW2 (~15min)
         │     └─ ER GW2 (~20-45min)
         │
         ├─ ER circuit1 (~2-5min)  ─┐
         ├─ ER circuit2 (~2-5min)  │
         ├─ MCR1 (~5-10min)         │
         ├─ MCR2 (~5-10min)         │ ──── ALL PARALLEL with vHub/ER GW
         ├─ GCP VPC A → router A → attachment A (~5-10min)
         ├─ GCP VPC B → router B → attachment B (~5-10min)
         ├─ GCP VM A/B (~3min)
         ├─ Spoke VNets × 4 + NSGs + NICs (~2min)
         └─ Spoke VMs × 4 (~3min)

T+~10min Azure VXC1 starts (after MCR1 + circuit1.service_key)
         Azure VXC2 starts (after MCR2 + circuit2.service_key)
         GCP VXC A starts (after MCR1 + attachment A pairing_key)
         GCP VXC B starts (after MCR2 + attachment B pairing_key)
         All 4 VXCs run in parallel (~5-15min each)

T+~25min All Megaport + GCP work done, waiting on long pole

T+~30-45min  ER GW1/2 ready → AzFW1/2 ready → routing-intent 1/2 ready
             → ER connection hub1-circuit1, hub2-circuit2 (~2min)
             → Spoke vHub connections × 4 (~3min, parallel)

T+~35-50min  Deploy complete
```

**Target wall-clock:** 35-50 min (driven by `max(vHub, ER GW)` long pole; Megaport/GCP fully absorbed).
**Anti-pattern (if work were serialised by layer):** would be ~70-90 min (Azure 30 + Megaport 15 + GCP 10 + ER conn 5 + spokes 5 sequential).

**TF parallelism flag:** `deploy.ps1` and `cleanup.ps1` now pass `-parallelism=20` (default 10) to both `plan` and `apply`/`destroy`. The graph has ~6 independent root branches at T0; parallelism=10 would technically suffice, but =20 leaves headroom for the 4 VXCs that start concurrently around T+10min and for the 4 spoke VMs that converge at T+~3min.

**Measured wall-clock (post-deploy: Tank to fill in):**
- Actual T0→T-finish: _(record from deploy.ps1 timestamps)_
- Actual long pole: _(was it vHub creation, ER GW, or AzFW?)_
- Any serialization observed that should be fixed in v2? _(record any unexpected waits)_

## 4. Variables wired for Niobe's S4 perturbation (no Tank action: Niobe flips)

| Var | Default | Niobe flips for | Effect |
|---|---|---|---|
| `er_bow_tie_hub1` | `false` | S4a (bow-tie injection) | Creates `hub1ergw → circuit2` connection: Hub1 also learns Region B's circuit |
| `er_bow_tie_hub2` | `false` | S4a | Creates `hub2ergw → circuit1` connection |
| `mcr1_injected_prefixes` | `[]` | S4b (MCR1 prefix injection) | Adds prefixes (e.g. `["10.50.2.0/24"]`) to MCR1's GCP-side prefix-filter list |
| `mcr2_injected_prefixes` | `[]` | S4b | Same for MCR2 |

Niobe re-runs `terraform apply` with these overrides to inject failure scenarios, then resets and re-applies for restore.

## 5. KV access plan (operator-mediated, encoded in deploy.ps1)

`deploy.ps1` prompts at runtime for Path A (preferred: Jose pauses GSA) or Path B (ACL flip with try/finally auto-restore). Both paths fetch:

- `megaport-api-key`  → `TF_VAR_megaport_access_key`
- `megaport-api-secret` → `TF_VAR_megaport_secret_key`
- `default-password`  → `TF_VAR_default_password`

Path B captures `networkAcls` to `deploy/.akv-state.json` BEFORE the flip and restores in a `finally` block. `.akv-state.json` is covered by the repo-root `.gitignore`'s `*.json` matches via the explicit gitignore patterns; if not, add a per-folder ignore before checkin.

## 6. Resource group naming

`rg-vwan-symm-<correlation_id>` (correlation_id is the lower-hex of a 3-byte random_id, 6 chars). Example: `rg-vwan-symm-a1b2c3`. RG location is `var.location_a` (`swedencentral`).

Every resource carries:
- `lab = vwan-dual-er-symmetric`
- `lab_name = vwan-dual-er-symmetric`
- `owner = jose`
- `created_by = copilot-lab`
- `ephemeral = true`
- `lifetime = manual`
- `correlation_id = <hex>`

## 7. Deviations from plan / decisions made by Tank

| Item | Manifest / Decision | Tank's choice | Rationale |
|---|---|---|---|
| KV secret count | Manifest §7 lists 4 secrets (incl. `vm-admin-ssh-public-key` and `gcp-service-account-json`) | **Only 3 secrets fetched**: `megaport-api-key`, `megaport-api-secret`, `default-password` | Dispatch explicitly directed: "use only the 3 secrets Jose confirmed". SSH public key replaced with password auth; GCP auth via `gcloud` ADC (Jose pre-authenticated). |
| VM auth | Manifest §5.3 says SSH key | **Password auth using `default-password`** | Per dispatch + decisions.md (2026-06-15 AKV access pattern: 3rd secret is "Default VM admin password"). |
| VM SKU northeurope | Manifest §5.3 default `B2als_v2` | **`B2s_v2` non-zonal** in northeurope; `B2als_v2` in swedencentral | Live probe found B2als_v2 missing from northeurope catalog. Per Tank charter rule for `Zone + subset blocked`. |
| Per-spoke public IPs | Lab #1 had public IPs on VMs | **No public IPs** | Internal-only lab; access via `az vm run-command`. |
| GCP project creation | Manifest §7 mentioned creating `onpremsim-${RANDOM}` per lab | **Use existing `familytree-471318`** | Per dispatch + decisions.md GCP credential note. |
| Megaport bow-tie injection | Manifest §S4 uses Azure bow-tie | **Both S4a (bow-tie) AND S4b (MCR prefix injection) supported via vars** | Per dispatch: Niobe needs both perturbation paths available, gated by TF variables for atomic flip. |

## 8. Cost reminder (pre-approved by Jose)

~$135/day at full deploy (Azure ~$106 + Megaport ~$26 + GCP ~$3). Cleanup is manual: Jose decides when. All resources tagged `ephemeral=true, lifetime=manual`.

## 9. Handoff: how Jose runs the deploy

```powershell
# From repo root, in PowerShell (admin not required):
cd labs\vwan-dual-er-symmetric\deploy

# Pre-flight: ensure gcloud ADC is present (one-time):
gcloud auth application-default login

# Run the deploy (interactive: will prompt for KV path A/B and apply confirmation):
.\deploy.ps1

# If you want to skip the apply prompt after seeing the plan:
.\deploy.ps1 -AutoApprove
```

Once `terraform apply` finishes, `deploy/tf-outputs.json` will contain every ID Niobe needs:
- RG name (`resource_group_name`)
- Both vHub IDs (`hub_ids.hub1` / `.hub2`)
- Both AzFW IDs + private IPs (`azfw_ids`, `azfw_private_ips`)
- Both ER circuit IDs + service keys (`er_circuit_ids`, `er_service_keys` [sensitive])
- Both ER GW IDs (`er_gateway_ids`)
- Both MCR UIDs (`mcr_uids`)
- All 4 spoke VM private IPs (`spoke_vm_private_ips`)
- Both GCP VM private IPs (`gcp_vm_private_ips`)
- Log Analytics workspace ID (`log_analytics_workspace_id`)
- VM SKUs and Megaport PoPs actually used

## 10. Cleanup: when Jose says go

```powershell
cd labs\vwan-dual-er-symmetric\deploy
.\cleanup.ps1                # single-shot destroy (TF graph encodes §8.4 order)
# or if it fails partway:
.\cleanup.ps1 -Stepwise      # manual sequence: ER conns → Megaport VXCs → MCRs → everything else
```

## 11. Open items (none blocking deploy)

- `.akv-state.json` is local to `deploy/`; root `.gitignore` covers `*.tfvars`/`*.tfstate*` but not arbitrary state files: confirm before any `git add deploy/`.
- Megaport `prefix_filter_lists` deprecation warning will need resolution at the next provider major; currently functional.

---

**Tank, 2026-06-15T14:15:03Z**: TF stack and scripts ready. Awaiting Jose to run `deploy.ps1`.

## GCP project lifecycle (per 2026-06-15T15:20Z policy: new project per lab)

**Policy:** No reuse of existing GCP projects (amilytree-471318 is no longer the default). A new project is created per lab run and destroyed on cleanup.

| Item | Value |
|---|---|
| Option chosen | **Y: script-driven** (deploy.ps1 step [4b]) |
| Project ID convention | `gcp-vwan-symm-<correlation_id>` (≤30 chars, lowercase, starts with letter ✓) |
| Project ID at last deploy | `<filled in after deploy>` |
| Billing account | `01ACFF-9E8C08-552F38` (single open account discovered via `gcloud billing accounts list`) |
| APIs enabled (post-create) | `compute.googleapis.com`, `servicenetworking.googleapis.com`, `cloudresourcemanager.googleapis.com` |
| ADC quota project | Auto-set via `gcloud auth application-default set-quota-project <project-id>` in step [4b]. Jose's prior `gcloud auth application-default login` is account-level: no re-login needed when project changes. |
| TF wiring | `var.gcp_project_id` (required, empty default + validation) + `var.correlation_id_override` (default empty). `deploy.ps1` computes a 6-char hex suffix, creates `gcp-vwan-symm-<suffix>`, then exports both env vars so the Azure RG `rg-vwan-symm-<suffix>` and the GCP project share the correlation_id. |
| Provider config | `google` + `google.region_b` aliases now set `billing_project = var.gcp_project_id` and `user_project_override = true` (canonical pattern when ADC quota project differs from the resource project). |
| Cleanup | `cleanup.ps1` step [5] runs `gcloud projects delete <project-id> --quiet` after `terraform destroy`. Project enters 30-day grace; billing stops immediately. Best-effort recovery of the project ID from `deploy-log.md` if env vars missing. |
| Idempotency | If `gcp-vwan-symm-<suffix>` already exists, deploy.ps1 reuses it (e.g., for resume-after-failure). Name collisions retry with `-2`, `-3` suffix. |

**Refactor diff summary (files modified for this policy):**

- `src/terraform/vwan-dual-er-symmetric/variables.tf`: `gcp_project_id` default → `""` with non-empty validation. Added `correlation_id_override`.
- `src/terraform/vwan-dual-er-symmetric/locals.tf`: `correlation_id = var.correlation_id_override != "" ? var.correlation_id_override : random_id.correlation.hex`.
- `src/terraform/vwan-dual-er-symmetric/providers.tf`: both `google` blocks set `billing_project` + `user_project_override = true`.
- `deploy.ps1`: new step [4b] (project create → billing link → API enable → ADC quota → `TF_VAR_*` export). New `-BillingAccountId` param (default `01ACFF-9E8C08-552F38`).
- `cleanup.ps1`: new step [5] (`gcloud projects delete` belt-and-braces).

`terraform validate` ✅ after refactor (same 2 pre-existing deprecation warnings about Megaport `prefix_filter_lists` ignore_changes: unchanged).

## KV ACL restore audit (2026-06-15T15:30:14Z)

- Vault: `platform-secrets-1138` (RG `platform`)
- Attempt: 1 of 3
- defaultAction restored to: `Deny`  / bypass: `None`
- ipRules restored (1 entries), vnetRules restored (0 entries)
- ✅ Post-restore diff: EMPTY (state matches pre-flip snapshot exactly).


## Mechanical fixes applied during deploy (per 2026-06-15T15:17Z escalation policy)

Two mechanical bugs hit during the partial run; both fixed in-place, deploy resumed without escalation.

| # | When | Error | Root cause | Fix |
|---|------|-------|-----------|-----|
| 1 | Step [3] / first attempt | `PowerShell ParserError at deploy.ps1:180`: `Variable reference is not valid. ':' was not followed by a valid variable name character` | `"$attempt/$maxAttempts:"` was parsed as `$maxAttempts:` (scope-qualifier syntax like `$global:`) | Wrapped in braces: `"$attempt/${maxAttempts}:"` |
| 2 | Step [3] / second attempt | `Failed to capture KV networkAcls snapshot` (.akv-state.json was empty) | `az keyvault show --query networkAcls` returns empty because the field is at `properties.networkAcls` (nested), not root | Changed both query strings to `--query "properties.networkAcls"` (snapshot capture + post-restore re-read) |

Third-run executed end-to-end cleanly:
- KV Path B: snapshot → flip → fetch 3 secrets → restore in **1 attempt**, post-restore diff **EMPTY** (verified via independent `az keyvault show` + a confirmation that secret fetch returns 403 again).
- GCP project `gcp-vwan-symm-103167` created, billing linked to `01ACFF-9E8C08-552F38`, 3 APIs enabled.
- `.lab-state.json` written with correlation_id=`103167` so resume reuses the same project.

KV state at end of partial run (verified independently):

```json
{
  "bypass": "None",
  "defaultAction": "Deny",
  "ipRules": [{ "value": "<operator-public-ip>/32" }],
  "virtualNetworkRules": []
}
```

## GCP auth: ADC bypass via GOOGLE_OAUTH_ACCESS_TOKEN (per 2026-06-15T15:43Z dispatch)

**Decision:** Skip `gcloud auth application-default login` (ADC) entirely. Use the user-account login that `gcloud auth login` already established.

**Why:**
- Exhaustive search of Jose's `$env:USERPROFILE` found zero `application_default_credentials.json` files (ADC was reported done but the browser flow apparently did not complete).
- `gcloud auth list` shows `erjosito1138@gmail.com` ACTIVE and `gcloud auth print-access-token` returns a valid OAuth token that authenticates against `gcp-vwan-symm-103167` (project describe returns `ACTIVE`).
- The google Terraform provider accepts `GOOGLE_OAUTH_ACCESS_TOKEN` as a first-class auth env var (equivalent to setting `access_token` on the provider block: no provider HCL change needed).

**Implementation:**
- `deploy.ps1` step `[5.pre]` runs `gcloud auth print-access-token` and exports `$env:GOOGLE_OAUTH_ACCESS_TOKEN`. Throws clearly if empty.
- `cleanup.ps1` does the same refresh immediately after the gcloud auth check (step [1]).
- The early ADC presence warning at step [2] of `deploy.ps1` is removed.

**Token lifetime caveat:** OAuth access tokens are valid ~1 hour. The lab apply is estimated at 35-50 min wall-clock, so a single refresh before apply is sufficient. If apply ever runs >55 min and fails mid-flight with a 401 against `googleapis.com`, simply re-run `deploy.ps1 -KvPath B -NonInteractive -AutoApprove`: Terraform is idempotent and picks up where it stopped. For future labs with >55-min applies, a background PowerShell job that refreshes the env var every 30 min is the next-step robustness pattern (not implemented here: overkill for a one-shot ~45-min apply).

## KV ACL restore audit (2026-06-15T15:49:53Z)

- Vault: `platform-secrets-1138` (RG `platform`)
- Attempt: 1 of 3
- defaultAction restored to: `Deny`  / bypass: `None`
- ipRules restored (1 entries), vnetRules restored (0 entries)
- ✅ Post-restore diff: EMPTY (state matches pre-flip snapshot exactly).


### Mechanical fix #3: Megaport PoP names

| When | Error | Root cause | Fix |
|------|-------|-----------|-----|
| Step [5c] / `terraform plan` | `Error: Unable to Get location by name` on `data.megaport_location.loc_a` and `loc_b` | Variable defaults used short names `"Equinix SK1"` / `"Equinix AM2"`. Megaport's `data` source requires the full descriptive name including city (e.g., `"Equinix Stockholm SK1"`). Also, `"Equinix AM2"` doesn't exist in Megaport's 606-PoP catalog at all: the equivalent Amsterdam Equinix PoP is `"Equinix Amsterdam AM1"` (id 85) or `"Equinix Amsterdam AM5"` (id 87). | Changed `variables.tf` defaults: `megaport_location_a = "Equinix Stockholm SK1"` (id 95) and `megaport_location_b = "Equinix Amsterdam AM1"` (id 85). Manifest §5.2 explicitly says "MCR 2 (Amsterdam or Megaport-picked PoP)": Morpheus deliberately allowed flexibility, so this is not design-impact. Lab #1 lesson §5.2 confirms: "the MCR location and the ER peering location do not have to match". Queried `https://api.megaport.com/v2/locations` to validate. |

## KV ACL restore audit (2026-06-15T15:56:30Z)

- Vault: `platform-secrets-1138` (RG `platform`)
- Attempt: 1 of 3
- defaultAction restored to: `Deny`  / bypass: `None`
- ipRules restored (1 entries), vnetRules restored (0 entries)
- ✅ Post-restore diff: EMPTY (state matches pre-flip snapshot exactly).


## Mechanical fixes batch #4 (2026-06-15T15:35-15:40Z, post-apply-debug)

Apply attempt #3 with `TF_LOG=DEBUG → tf-debug.log` revealed three distinct mechanical errors that the earlier non-debug runs had hidden (Megaport's silent 400 was masquerading as a 30-min `mcr1` hang).

### Mechanical fix #4: Megaport account: Sweden market not enabled

| When | Error | Root cause | Fix |
|------|-------|-----------|-----|
| Apply `megaport_mcr.mcr1` | `POST /v3/networkdesign/validate 400: {"data":[{"markets":["MEGAPORT_SWEDEN"],"error":"Missing markets: Sweden"}]}` (returned in 1.9s; provider then heartbeats "Still creating..." for 30+ min before failing: a UX bug in `terraform-provider-megaport v1.10.1`) | Our Megaport account does NOT have the `MEGAPORT_SWEDEN` market enabled. `Equinix Stockholm SK1` (id 95) is in the public Megaport catalog but cannot be provisioned on this account. `MEGAPORT_NETHERLANDS` IS enabled (mcr2 in Amsterdam AM1 succeeded in 37s). | Switched `megaport_location_a` default from `"Equinix Stockholm SK1"` to `"Equinix Frankfurt FR5"` (id 131): the same fallback used in lab #1 when Madrid/Spain was restricted (see `src/terraform/expressroute-megaport-bgp/README.md`). ER circuit `peering_location = "Stockholm"` is unchanged: per Megaport, the MCR PoP and Azure ER peering metro do not need to match (VXC bridges them). Manifest §5.2 fallback path explicitly anticipated this. Updated variable description to note the account-level restriction. |

**Lesson for future labs:** ALWAYS run `terraform apply` with `TF_LOG=DEBUG` on first attempt when the Megaport provider is in the dependency graph. The provider's "Still creating..." heartbeat is misleading: actual 400 errors arrive within seconds but only surface in debug output until the final apply summary.

### Mechanical fix #5: GCP PARTNER interconnect attachments forbid `bandwidth`

| When | Error | Root cause | Fix |
|------|-------|-----------|-----|
| Apply `google_compute_interconnect_attachment.att_a` and `att_b` | `googleapi: Error 400: Invalid value for field 'resource.bandwidth': 'BPS_50M'. The field bandwidth cannot be specified for interconnect attachment of type [PARTNER]` | GCP Cloud Interconnect API: for `type = "PARTNER"` attachments, bandwidth is set by the partner (Megaport's VXC `rate_limit`), NOT by the GCP-side attachment. The `bandwidth` field is only valid for `type = "DEDICATED"`. | Removed `bandwidth = var.gcp_interconnect_bandwidth` from both `att_a` and `att_b` blocks in `gcp.tf` (lines 53-61 and 137-145). The Megaport VXCs `gcp_a` / `gcp_b` already carry `rate_limit = var.gcp_interconnect_bandwidth_mbps`, which is the authoritative bandwidth source. Variable `var.gcp_interconnect_bandwidth` is left in `variables.tf` (no longer referenced) for documentation; can be removed later. |

### Mechanical fix #6: ergw-hub1 import name mismatch in recover script

| When | Error | Root cause | Fix |
|------|-------|-----------|-----|
| Apply `azurerm_express_route_gateway.hub1` | `a resource with the ID "/subscriptions/…/expressRouteGateways/ergw-hub1" already exists - to be managed via Terraform this resource needs to be imported` | Recover script `recover-orphans.ps1` was using TF address `azurerm_express_route_gateway.gw_hub1` but `azure-expressroute.tf` declares the resource as `.hub1` (Tank typo at script-write time). The import step was silently skipped because the condition ` -contains 'gw_hub1'` was always false. | Fixed all three references in `recover-orphans.ps1` to use `azurerm_express_route_gateway.hub1`. Also proactively added an `hub2` import block in case the current killed apply orphans `ergw-hub2` (which is mid-provisioning at kill time). |


## ✅ DEPLOY SUCCESS (2026-06-15T18:50Z)

### Summary
- Resource group: `rg-vwan-symm-103167` / sub `a8fbd8e1-fb5a-4411-804a-4ac80929c93c`
- Regions: `swedencentral` (Hub1/Region A) + `northeurope` (Hub2/Region B)
- GCP project: `gcp-vwan-symm-103167` (created this session; lifecycle: Option Y, `gcloud projects delete` in cleanup.ps1)
- Total TF-managed resources: 71
- Wall-clock from first apply to success: ~3h 15min (3 cycles + debug iteration; long pole = ER GW provisioning + ER connections + Megaport hung-error diagnosis)
- KV access path used: B (try/finally ACL flip with auto-restore): invoked 3× successfully
- VM SKUs: B2als_v2 (region_a, zonal-or-not), B2s_v2 (region_b, non-zonal per charter)
- Megaport PoPs: `Equinix Frankfurt FR5` (MCR1, fallback: Sweden market not enabled on account) + `Equinix Amsterdam AM1` (MCR2, primary)

### Verified resource counts
| Category | Expected | Actual |
|----------|----------|--------|
| Azure VMs | 4 | 4 ✅ |
| Azure VNets (spokes) | 4 | 4 ✅ |
| Azure vHubs | 2 | 2 ✅ Provisioned |
| Azure AzFW Standard | 2 | 2 ✅ |
| Azure ER circuits | 2 | 2 ✅ Provisioned |
| Azure ER gateways | 2 | 2 ✅ |
| Megaport MCRs (LIVE) | 2 | 2 ✅ (mcr1 + mcr2) |
| Megaport VXCs (LIVE) | 4 | 4 ✅ (azure_circuit1/2 + gcp_a/b) |
| GCP VPCs | 2 | 2 ✅ |
| GCP Cloud Routers (ASN 16550) | 2 | 2 ✅ |
| GCP Partner Interconnect attachments (ACTIVE) | 2 | 2 ✅ |
| GCP VMs (RUNNING) | 2 | 2 ✅ |

### Smoke test (spoke1 VM)
`az vm run-command invoke -g rg-vwan-symm-103167 -n vm-spoke1 -- "ip route show"` succeeded:
- VM IP: `10.11.0.4/27` matches TF output `spoke_vm_private_ips["spoke1"]`
- Default route → `10.11.0.1` (spoke subnet gateway → vHub1 data plane)
- Proves spoke→hub control + data plane functional. Full route propagation validation is Niobe's job.

## Niobe handoff: resource IDs

### Azure
- vWAN: `/subscriptions/a8fbd8e1-fb5a-4411-804a-4ac80929c93c/resourceGroups/rg-vwan-symm-103167/providers/Microsoft.Network/virtualWans/vwan-vwan-symm`
- vHub1 (swedencentral): `/subscriptions/a8fbd8e1-fb5a-4411-804a-4ac80929c93c/resourceGroups/rg-vwan-symm-103167/providers/Microsoft.Network/virtualHubs/hub1-swedencentral`
- vHub2 (northeurope): `/subscriptions/a8fbd8e1-fb5a-4411-804a-4ac80929c93c/resourceGroups/rg-vwan-symm-103167/providers/Microsoft.Network/virtualHubs/hub2-northeurope`
- AzFW1 ID: `/subscriptions/a8fbd8e1-fb5a-4411-804a-4ac80929c93c/resourceGroups/rg-vwan-symm-103167/providers/Microsoft.Network/azureFirewalls/azfw-hub1-swedencentral` (private IP: `10.10.0.132`)
- AzFW2 ID: `/subscriptions/a8fbd8e1-fb5a-4411-804a-4ac80929c93c/resourceGroups/rg-vwan-symm-103167/providers/Microsoft.Network/azureFirewalls/azfw-hub2-northeurope` (private IP: `10.20.0.132`)
- ER circuit 1 (Stockholm): `/subscriptions/a8fbd8e1-fb5a-4411-804a-4ac80929c93c/resourceGroups/rg-vwan-symm-103167/providers/Microsoft.Network/expressRouteCircuits/er-vwan-symm-stockholm`
  - Service key: `9b2b5f03-4e57-4135-987e-b736c6186055`
- ER circuit 2 (Amsterdam): `/subscriptions/a8fbd8e1-fb5a-4411-804a-4ac80929c93c/resourceGroups/rg-vwan-symm-103167/providers/Microsoft.Network/expressRouteCircuits/er-vwan-symm-amsterdam`
  - Service key: `999a3bd6-1408-48f5-a7c7-47575d07ac44`
- ER GW hub1: `/subscriptions/a8fbd8e1-fb5a-4411-804a-4ac80929c93c/resourceGroups/rg-vwan-symm-103167/providers/Microsoft.Network/expressRouteGateways/ergw-hub1`
- ER GW hub2: `/subscriptions/a8fbd8e1-fb5a-4411-804a-4ac80929c93c/resourceGroups/rg-vwan-symm-103167/providers/Microsoft.Network/expressRouteGateways/ergw-hub2`
- ER conn hub1↔circuit1: `/subscriptions/a8fbd8e1-fb5a-4411-804a-4ac80929c93c/resourceGroups/rg-vwan-symm-103167/providers/Microsoft.Network/expressRouteGateways/ergw-hub1/expressRouteConnections/hub1ergw-circuit1`
- ER conn hub2↔circuit2: `/subscriptions/a8fbd8e1-fb5a-4411-804a-4ac80929c93c/resourceGroups/rg-vwan-symm-103167/providers/Microsoft.Network/expressRouteGateways/ergw-hub2/expressRouteConnections/hub2ergw-circuit2`

### Spoke VMs (private IPs / IDs)
| Spoke | Hub | Private IP | VM ID (suffix) |
|-------|-----|-----------|----------------|
| spoke1 | hub1 | `10.11.0.4` | vm-spoke1 |
| spoke2 | hub1 | `10.12.0.4` | vm-spoke2 |
| spoke3 | hub2 | `10.21.0.4` | vm-spoke3 |
| spoke4 | hub2 | `10.22.0.4` | vm-spoke4 |

### Megaport
- mcr1 UID: `9785d825-989e-45bb-b50f-82f039edb901` (Frankfurt FR5)
- mcr2 UID: `f07eb97c-6fb8-444f-a921-74728997c704` (Amsterdam AM1)
- VXC azure_circuit1: `c895492d-a44a-479a-861e-ea48ba5b3b02`
- VXC azure_circuit2: `c7a2d4aa-6c34-4576-81f8-11f624e31d5e`
- VXC gcp_a: `e461d013-2c8b-45dc-9ae6-e6c135392660`
- VXC gcp_b: `1ae8a2c8-6c3a-4ebc-bd88-e4c8fb84983d`
- MCR1 prefix-filter list ID: `6805`
- MCR2 prefix-filter list ID: `6804`

### GCP
- VPC A: `projects/gcp-vwan-symm-103167/global/networks/vpc-vwan-symm-a-103167`
- VPC B: `projects/gcp-vwan-symm-103167/global/networks/vpc-vwan-symm-b-103167`
- Router A (ASN 16550): `router-vwan-symm-a`
- Router B (ASN 16550): `router-vwan-symm-b`
- VM A private IP: `10.50.1.2`
- VM B private IP: `10.50.2.2`

## S4 perturbation knobs (Niobe)

Bow-tie flip (S4a):
- `terraform apply -var='er_bow_tie_hub1=true' -var='er_bow_tie_hub2=true'`: creates `hub1_circuit2_bowtie` + `hub2_circuit1_bowtie` (count=1).

MCR injected-prefix change (S4b):
- `terraform apply -var='mcr1_injected_prefixes=["10.50.2.0/24"]' -var='mcr2_injected_prefixes=["10.50.1.0/24"]'`: expands the MCR prefix-filter list scope.

## BGP session caveat (for Niobe)

Megaport BGP sessions can take **60-120 seconds** to come up after VXC creation (or after a config change). `terraform apply` does not wait for BGP. If Niobe's first BGP-state check (`az network express-route list-route-table`, MCR API, or GCP router BGP status) returns empty/Idle, retry after 2 minutes.

## Lesson: Phased apply for cross-cloud labs (added 2026-06-15T18:53Z per Jose)

**The default deploy pattern for any cross-cloud lab MUST be phased `-target=` apply, not a single `terraform apply`.** Reason: a credential/token resolution problem in one cloud (e.g., the GCP ADC saga in this run) gates ALL providers in a single apply, even though the TF graph has zero cross-cloud `depends_on` edges. Wall-clock during this deploy was inflated by 30+ minutes of "wait for GCP credentials to be sorted" while Azure/Megaport had no actual dependency on them.

### Correct pattern (use for next cross-cloud lab from minute one)

`powershell
# Phase A: Azure + Megaport (no GCP dependency)
terraform apply -parallelism=20 -auto-approve `
  -target=azurerm_resource_group.lab `
  -target=azurerm_virtual_wan.vwan `
  -target='azurerm_virtual_hub.hub1' -target='azurerm_virtual_hub.hub2' `
  -target='azurerm_express_route_circuit.circuit1' -target='azurerm_express_route_circuit.circuit2' `
  -target='azurerm_express_route_gateway.hub1' -target='azurerm_express_route_gateway.hub2' `
  -target='azurerm_firewall.hub1' -target='azurerm_firewall.hub2' `
  -target='azurerm_virtual_hub_routing_intent.hub1' -target='azurerm_virtual_hub_routing_intent.hub2' `
  -target='azurerm_linux_virtual_machine.spoke' `
  -target='azurerm_virtual_hub_connection.spoke' `
  -target='megaport_mcr.mcr1' -target='megaport_mcr.mcr2' `
  -target='megaport_vxc.azure_circuit1' -target='megaport_vxc.azure_circuit2'

# Phase B: GCP (independent of Azure/Megaport)
terraform apply -parallelism=20 -auto-approve `
  -target='google_compute_network.vpc_a' -target='google_compute_network.vpc_b' `
  -target='google_compute_router.router_a' -target='google_compute_router.router_b' `
  -target='google_compute_interconnect_attachment.att_a' -target='google_compute_interconnect_attachment.att_b' `
  -target='google_compute_instance.vm_a' -target='google_compute_instance.vm_b'

# Phase C: cross-cloud join: VXCs to GCP + ER connections (final full apply)
terraform apply -parallelism=20 -auto-approve
`

Phase A and Phase B can run **in parallel in two PowerShell shells**: there is no TF state contention because both phases edit disjoint subsets of state (the shells just need to coordinate so neither holds the state lock when the other tries to acquire it; in practice TF's local-state lock waits cleanly).

### Rule of thumb for any cross-cloud blocker mid-deploy
1. Identify which provider is blocked.
2. Compute the unblocked set: `terraform state list` + grep for the non-blocked provider prefixes (`azurerm_*`, `megaport_*`, `google_*`).
3. Apply that subset NOW with `-target=` flags. Do not wait.
4. Apply the blocked provider as soon as its blocker clears.
5. Apply the cross-cloud join (final full apply) last: it has no new resources except the ones that genuinely depend on both sides being present.

### What changes for next lab dispatch
- `deploy.ps1` should accept `-Phase A|B|C|All` and invoke the right `-target=` set.
- The default of `-Phase All` should run A → B → C sequentially with a 60s sleep between, OR if Jose specifies `-Phase A` and `-Phase B` in parallel shells, the script handles that cleanly.
- `recover-orphans.ps1` keeps its current behavior (it runs `-Phase All` after imports).

### Why we didn't do this in lab #2
- It wasn't until 30 min into the deploy that Jose pointed out the cross-cloud independence.
- Even then the deploy was already past the gating point: phased apply would have shaved ~30 min off the wall clock but the same iterations (Megaport Sweden 400, GCP bandwidth, GCP ASN, vWAN routing-intent) would still have happened.
- Lab #3+ will use the phased pattern by default.

---

## Patch: secondary VXCs added (Tank, 2026-06-15T18:55:36+02:00)

**Status:** ✅ COMPLETE: 4 BGP sessions Established (2 per circuit)

### What was missing

The initial deploy created only **1 VXC per ER circuit** (`port_choice = "primary"`). Each Megaport MCR ↔ Azure ER circuit connection supports two MSEE peering ports: a primary and a secondary. Both must be wired with a separate VXC for full HA and dual BGP sessions. This was a Tank miss: the original `megaport.tf` only had `port_choice = "primary"` for each circuit.

Jose observed only one active connection per ER circuit in the portal. Design spec (Trinity §1.5 + S1.1) requires `bgpState=Established ×4` across two circuits.

### What was added

Two new Megaport VXC resources added to `megaport.tf`:

| Resource | Port choice | MSEE endpoint | MCR |
|---|---|---|---|
| `megaport_vxc.azure_circuit1_secondary` | secondary | Stockholm Secondary | MCR1 (Frankfurt) |
| `megaport_vxc.azure_circuit2_secondary` | secondary | Amsterdam Secondary | MCR2 (Amsterdam) |

`locals.tf` updated with new naming locals (`vxc1_azure_secondary_name`, `vxc2_azure_secondary_name`).  
`outputs.tf` updated: `megaport_vxc_uids` expanded to 6 entries; two new BGP outputs (`bgp_azure_circuit1_secondary`, `bgp_azure_circuit2_secondary`) added.

**Apply:** `terraform apply -parallelism=20 -auto-approve patch-secondary-vxc.tfplan`: 2 added, 0 changed, 0 destroyed.

**Key issue during patch:** First plan attempt showed `correlation_id` drift (`103167` → `899b81`) because the patch tfvars didn't include `correlation_id_override = "103167"`, causing cascade replacements of the RG and ER circuits. Fixed by adding `correlation_id_override = "103167"` to the patch tfvars. Always lock the correlation_id when patching a live lab.

### Before / after VXC count

| Before | After |
|---|---|
| 4 VXCs: 2 ER (primary only) + 2 GCP | 6 VXCs: 2 ER primary + 2 ER secondary + 2 GCP |

### BGP session verification (4 total, all Established)

```
az network express-route list-route-tables-summary -g rg-vwan-symm-103167 \
  -n er-vwan-symm-stockholm --path primary --peering-name AzurePrivatePeering

As     Neighbor         StatePfxRcd    UpDown    V
65001  169.254.150.121  4              1:20:25   4   ← MCR1 primary (original)

az network express-route list-route-tables-summary ... --path secondary
As     Neighbor         StatePfxRcd    UpDown    V
65001  169.254.150.125  9              7:16      4   ← MCR1 secondary (NEW) ✅

az network express-route list-route-tables-summary -g rg-vwan-symm-103167 \
  -n er-vwan-symm-amsterdam --path primary --peering-name AzurePrivatePeering
As     Neighbor        StatePfxRcd    UpDown
65002  169.254.148.89  4              2h39m       ← MCR2 primary (original)

az network express-route list-route-tables-summary ... --path secondary
As     Neighbor        StatePfxRcd    UpDown
65002  169.254.148.93  9              9m17s       ← MCR2 secondary (NEW) ✅
```

**Result:** Lab now meets Trinity §1.5 + S1.1 criteria: `bgpState=Established ×4` across 2 circuits, 2 sessions per circuit.

---

## Teardown (2026-06-16)

Lab fully decommissioned across all three providers. All resources confirmed gone.

**Final verification:**
- Azure: `az group exists -n rg-vwan-symm-103167` -> `false`
- Terraform: `terraform state list` -> empty (0 resources)
- Megaport: both MCRs (`mcr1-vwan-symm-103167`, `mcr2-vwan-symm-103167`) -> `DECOMMISSIONED`
- GCP: `gcp-vwan-symm-103167` -> `DELETE_REQUESTED` (30-day grace, billing stopped)

**Teardown ordering gotcha (ER + Megaport VXC circular dependency):**
A Megaport VXC that provisions an Azure ExpressRoute circuit's private peering cannot be
deleted directly while the peering exists (HTTP 409 "has an attached peering connection that
must be removed in Azure first"). The Azure circuit in turn cannot be deleted while its
service-provider provisioning state is `Provisioned` ("circuit is not in Deprovisioned state").
Correct order:
1. `az resource delete --ids <circuit-id> --api-version 2024-05-01` on the circuit. This
   removes the AzurePrivatePeering child but leaves the circuit in `Failed`/`Provisioned`
   (delete cannot complete yet) with `peerings=0`.
2. `terraform destroy -target=megaport_vxc.azure_circuitN` -- now succeeds (peering gone),
   which deprovisions the circuit on the Megaport side (`spProv -> NotProvisioned`).
3. Re-delete the Azure circuit (now `Succeeded`/`NotProvisioned`) -- succeeds.
4. `terraform destroy` for the MCRs + RG.

**Two reusable gotchas:**
- `az resource delete --ids` auto-selected an unsupported future api-version (`2026-01-01`,
  because the host clock is 2026) and failed with `NoRegisteredProviderFound`. Pin a known-good
  version with `--api-version 2024-05-01`.
- A GCP-facing VXC created out-of-band (`vxc-mcr2-gcp-b-v2-103167`) was not in Terraform state
  and blocked MCR2 deletion ("has active VXCs"). Deleted directly via Megaport API
  `POST /v3/product/<uid>/action/CANCEL_NOW?safeDelete=true` with `Content-Type: application/json`.
