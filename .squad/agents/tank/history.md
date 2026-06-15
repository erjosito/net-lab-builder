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
