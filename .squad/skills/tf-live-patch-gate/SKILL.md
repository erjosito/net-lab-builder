# SKILL: tf-live-patch-gate

**Version:** 1.0  
**Author:** Tank  
**Date:** 2026-06-15  
**Evidence:** `labs/vwan-dual-er-symmetric/show-output/design-b-patch/` (Design B patch, lab #2)

---

## What This Skill Does

Safely patch a live Terraform deployment by running a mandatory plan-show gate before apply. Prevents accidental destroy of live infrastructure (especially `random_id` re-roll → full RG cascade).

---

## When to Use

- Applying any patch to a live TF deployment where resources already exist in state
- Any time `correlation_id_override`, `password_override`, or other carry-forward variables must be preserved
- Any multi-provider patch (Azure + GCP + Megaport) where isolated destroy scope must be verified before apply

---

## Pre-flight: Tfvars Carry-Forward Check (MANDATORY)

Before ANY plan on a live lab, verify the active tfvars file contains all live override values:

```powershell
# Check correlation ID in state vs tfvars
terraform state show random_id.correlation | Select-String "hex"
# Verify terraform.auto.tfvars or terraform.tfvars has correlation_id_override = "<live_hex>"

# Check password override
terraform state show random_password.default | Select-String "result"
# Verify tfvars has password_override = "<live_value>"
```

**If either is missing → reconstruct from state BEFORE running plan.**

Missing `correlation_id_override` causes `random_id.correlation` to re-roll → all resources whose names embed the correlation ID (RG, VMs, circuits, VNets) are destroyed and recreated. This is a full lab teardown disguised as a plan output.

---

## The Gate Sequence

```powershell
cd src\terraform\<lab>
# Run plan and capture ANSI-stripped output
terraform plan -out=tfplan 2>&1 | Tee-Object <output_dir>\01-terraform-plan.txt
terraform show tfplan 2>&1 | Tee-Object <output_dir>\02-terraform-show.txt
terraform show tfplan | rg '# .* will be (destroyed|replaced|created)' | Tee-Object <output_dir>\03-destroy-replace-summary.txt
```

**Strip ANSI codes before programmatic inspection:**
```powershell
$raw = Get-Content "03-destroy-replace-summary.txt" -Raw
$clean = $raw -replace '\x1b\[[0-9;]*[mGKHFJsuA-Za-z]', ''
```

---

## Gate Conditions (all must PASS)

Define the expected destroy/replace set before running plan. Gate conditions are lab-specific but always include:

| Condition | How to Check |
|---|---|
| ✅ Destroys match the spec exactly | Strip ANSI, count `-` lines in destroy-replace-summary, verify each matches the expected resource list |
| ✅ ZERO `azurerm_*` in destroy/replace | `$clean \| Select-String 'azurerm.*will be (destroyed\|replaced)'` → empty |
| ✅ ZERO `megaport_mcr` in destroy/replace | `$clean \| Select-String 'megaport_mcr.*will be (destroyed\|replaced)'` → empty |
| ✅ VXC changes are in-place (`~`) not replace (`-/+`) | Check `megaport_vxc.*will be replaced` → empty (or document override if ForceNew is intentional) |
| ✅ `random_id`, `random_pet`, `random_password` NOT in destroy/replace | These re-rolling means names/credentials change → cascade destroys |

**FAIL → STOP. Do NOT apply. Dump plan summary, escalate.**

---

## Engineering Override

Gate failures may be accepted with an engineering override IF:
1. The failure is **intentional** (the resource should be replaced per design)
2. The replacement is **non-cascading** (no downstream resources depend on the replaced resource's ID)
3. The override is **documented** in the gate verdict and deploy log

Example: Megaport `gcp_b` VXC must be replaced (ForceNew on pairing_key change) — intentional, non-cascading, correct end state. Override accepted.

---

## Apply Sequence

```powershell
# Apply from saved plan (guarantees what you inspected is what gets applied)
terraform apply tfplan
```

If fresh plan is needed (state changed since plan): re-run plan → gate → apply.

---

## Common Failure Modes

### 1. `random_id` re-rolls on plan
**Symptom:** Plan shows destroy of RG + all named resources.  
**Cause:** `correlation_id_override` missing from tfvars.  
**Fix:** Check `terraform state show random_id.correlation`, add override to tfvars, re-plan.

### 2. Megaport VXC "must be replaced" (ForceNew)
**Symptom:** `-/+` on `megaport_vxc.<name>` due to pairing_key or b_end_partner_config change.  
**Cause:** Megaport provider 1.10.1 marks `b_end_partner_config` as ForceNew.  
**Options:** (a) Accept with override if intentional; (b) If unintentional, revert pairing_key change in .tf.

### 3. Megaport VXC "ordered but not ready" timeout
**Symptom:** Apply hangs "Still creating..." ~10 min, then fails: "VXC ordered but not ready — UID saved to state."  
**Cause:** Megaport partner port provisioning exceeds TF provider timeout (~10 min). VXC IS ordered in Megaport backend.  
**Fix:** Re-run apply — TF will taint+replace the VXC. If same error recurs, switch to AVAILABILITY_DOMAIN_2 (different Google edge node/port pool).

### 4. Megaport "no available ports for you to connect to"
**Symptom:** VXC creation fails immediately after a previous VXC was destroyed on the same domain.  
**Cause:** Megaport partner port for that Google availability domain is in cooldown or exhausted.  
**Fix:** Destroy the GCP attachment, recreate on AVAILABILITY_DOMAIN_2 (ForceNew → new pairing key from different domain).

### 5. GCP VM blocking subnet deletion
**Symptom:** `terraform apply` fails: "subnet already in use by <vm_name>" (Error 400 resourceInUseByAnotherResource).  
**Cause:** VM's NIC change across VPCs is ForceNew in GCP provider, but TF plans it as in-place when new subnet is `(known after apply)`.  
**Fix:** `terraform destroy "-target=google_compute_instance.<name>"` first, then full apply.

### 6. ANSI codes in output files break PowerShell string search
**Symptom:** `Select-String`, `-match`, `IndexOf` return no results on file content that visually contains the match.  
**Fix:** Strip ANSI before any programmatic check:
```powershell
$clean = (Get-Content file.txt -Raw) -replace '\x1b\[[0-9;]*[mGKHFJsuA-Za-z]', ''
```

---

## Evidence Template

Create `labs/<lab>/show-output/<patch-name>/`:
- `01-terraform-plan.txt` — full plan output (ANSI-stripped)
- `02-terraform-show.txt` — full show output (ANSI-stripped)
- `03-destroy-replace-summary.txt` — gate evidence (`rg '# .* will be (destroyed|replaced|created)'`)
- `04-terraform-apply.txt` — apply log (append across passes)
- `05-post-apply-state-summary.txt` — `terraform state list` after apply
- `06-deploy-log.md` — 1-page summary: files edited, gate verdict, apply duration, deviations

---

## Lab Evidence

- **Lab #2 Design B patch (2026-06-15):** `labs/vwan-dual-er-symmetric/show-output/design-b-patch/`
  - Gate: FAIL condition 4 (gcp_b VXC ForceNew) → Engineering override accepted
  - vpc_a routing_mode REGIONAL→GLOBAL: confirmed IN-PLACE ✅
  - 6 GCP resources destroyed, 4 created, 0 Azure changes ✅
  - Required 4 apply passes due to VXC domain exhaustion (DOMAIN_1 → DOMAIN_2 fix)
