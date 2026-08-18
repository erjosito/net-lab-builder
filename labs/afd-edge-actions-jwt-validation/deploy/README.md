# afd-edge-actions-jwt-validation — Deploy README

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Azure CLI ≥ 2.60 | `az --version` |
| PowerShell ≥ 7.2 | Windows-native pwsh |
| Azure subscription | Contributor role on subscription |
| Entra ID | Application Administrator directory role |
| `az login` done | Current tenant must be the lab tenant |
| `npm` ≥ 10 | For local app package build before zip-deploy |

### Azure providers
`Microsoft.Cdn` — registered automatically by script if not present.

---

## Files

| File | Purpose |
|------|---------|
| `main.bicep` | Stable Azure resources: LAW, App Service Plan+App, AFD profile/endpoint/origins/route, diagnostic settings |
| `Deploy-Lab.ps1` | Full A0→A1→A2 deploy + smoke tests |
| `Cleanup-Lab.ps1` | **Preview only by default.** Pass `-Confirmed` only after Jose's explicit approval |
| `deployment-output.json` | Written at runtime — non-secret outputs (no tenant/sub IDs) |

---

## Usage

### Full deployment (A0/A1/A2)

```powershell
cd labs\afd-edge-actions-jwt-validation\deploy
.\Deploy-Lab.ps1
```

### Skip Entra registration (if A1 already done or manual)

```powershell
.\Deploy-Lab.ps1 -SkipA1
```

### What-if preview

```powershell
.\Deploy-Lab.ps1 -WhatIf
```

### Cleanup preview (lists resources — NO deletion)

```powershell
.\Cleanup-Lab.ps1
```

### Actual cleanup (⚠️ requires Jose's separate explicit approval)

```powershell
.\Cleanup-Lab.ps1 -Confirmed
```

---

## Deployment Sequence

```
A0  Resource group, Log Analytics, App Service Plan+App, AFD profile+endpoint+origin+route,
    diagnostic settings, App Service access restrictions (ARM-native FDID rules)
    App code zip-deployed (Node 20, Express + jose JWT library)

A1  Entra ID: app-edge-jwt-api (API app + Lab.Admin role)
              app-edge-jwt-client (client app + API permission + admin consent)
    CLIENT_SECRET → $env:CLIENT_SECRET only (never written to disk)

A_KV Key Vault for test credentials
    kv-jwt-lab-a8fbd8e1 (Standard SKU, RBAC, swedencentral)
    Key Vault Secrets Officer role assigned to signed-in identity
    Secrets written via ARM management plane (data-plane blocked by tenant policy)
    Secrets: client-secret, tenant-id, api-app-id, client-id, afd-endpoint

A2  ea-capability-probe Edge Action → /debug/* route
    Diagnostic settings `ea-logs` (UserLog + ServiceLog) created on EA immediately after resource creation
    AFD rule set rs-edge-probe created and attached to rt-api route

S1-GATE
    Query EdgeActionConsoleLog after GET /debug/request
    Verdict: GO / CONDITIONAL / STOP  (see design.md §4.3)

A3  (Conditional on S1-GATE GO/CONDITIONAL)
    ea-jwt-validate Edge Action → /edge-only, /protected, /admin routes
    Diagnostic settings `ea-logs` (UserLog + ServiceLog) created on EA immediately after resource creation
    ea-execution-filter Edge Action version (execution filter: X-Test-Fail: 1)

A4  Token acquisition + scenario smoke tests S2-S9
```

---

## Edge Actions API Notes

Edge Actions are a **subscription-level** `Microsoft.Cdn/EdgeActions` resource (not nested under an AFD profile). The deploy script uses `az rest` with the `2025-09-01-preview` API version.

AFD attachment is via a Rules Engine rule set on the AFD profile, with an `InvokeEdgeAction` action.

Code upload is base64-encoded. The portal notes upload can take up to **10 minutes** — the script waits 60 seconds and then proceeds.

---

## Key Vault

**Vault name:** `kv-jwt-lab-a8fbd8e1` (non-secret; committed)  
**Auth mode:** Azure RBAC — Key Vault Secrets Officer on vault scope  
**SKU:** Standard | **Location:** swedencentral

### Network posture (deviation from default)
Tenant policy enforces `publicNetworkAccess=Disabled` on all Key Vaults, overriding any firewall rule or `-PublicNetworkAccess Enabled` flag passed at creation time. Consequence:

- **Data-plane (`vault.azure.net`)** is unreachable from local machines → returns `ForbiddenByConnection`.  
  The error is network-layer, not RBAC — the `Key Vault Secrets Officer` role assignment is correctly in place.
- **ARM management plane** (`management.azure.com`) is unaffected → secrets are written by the deploy script via `PUT .../vaults/{name}/secrets/{secretName}?api-version=2023-07-01`.
- **Reading** secret values requires Azure Cloud Shell (AzureServices bypass, no extra cost) or a private-endpoint network.

### Loading test credentials — run in Azure Cloud Shell

> ⚠️ **Env vars are set in the Cloud Shell process only.** They are NOT transferred to your local machine.  
> Run your tests in the same session immediately after loading.

```bash
# 1. Open https://shell.azure.com  (or use the [>_] button in the Azure portal)
# 2. Clone the repo (first time only):
git clone https://github.com/<org>/net-lab-builder
cd net-lab-builder/labs/afd-edge-actions-jwt-validation/tests

# 3. Load credentials:
pwsh Import-JwtLabEnvironment.ps1

# 4. Optional — inspect names/lengths (no values):
pwsh Import-JwtLabEnvironment.ps1 -PassThru

# 5. Override vault name if needed:
pwsh Import-JwtLabEnvironment.ps1 -VaultName kv-jwt-lab-a8fbd8e1
```

After loading: `$env:TENANT_ID`, `$env:API_APP_ID`, `$env:CLIENT_ID`, `$env:CLIENT_SECRET`, `$env:AFD_ENDPOINT` are set for the lifetime of that Cloud Shell process only.

If you run the script from a local machine, `Import-JwtLabEnvironment.ps1` will detect `ForbiddenByConnection` and emit an actionable error with the exact Cloud Shell commands — no secrets will be printed or transferred.

### Local PowerShell (future option)
If local access becomes required, add a private endpoint for `kv-jwt-lab-a8fbd8e1` in `rg-afd-edge-jwt-lab`. No script changes are needed — the loader will work automatically once data-plane is reachable.

### Credential rotation
`client-secret` expires 7 days from creation. To rotate:

```powershell
# 1. Create a new credential (does NOT delete the old one):
$expiry = (Get-Date).AddDays(7).ToString('yyyy-MM-ddTHH:mm:ssZ')
az ad app credential reset --id <CLIENT_ID> --append `
  --display-name "jwt-lab-kv-$(Get-Date -Format 'yyyyMMdd')" `
  --end-date $expiry
# Password is shown once — store immediately (step 2).

# 2. Re-run A_KV section (or full Deploy-Lab.ps1) to update the KV secret.
#    The password is written to KV in-process and never saved to disk.
```

### Secrets stored
| Secret name | Content type | Notes |
|-------------|--------------|-------|
| `client-secret` | `application/jwt-lab-client-secret` | `app-edge-jwt-client` credential — expires 7d |
| `tenant-id` | `text/plain` | Entra tenant ID |
| `api-app-id` | `text/plain` | `app-edge-jwt-api` appId |
| `client-id` | `text/plain` | `app-edge-jwt-client` appId |
| `afd-endpoint` | `text/plain` | Full AFD HTTPS URL |

---

## Secret Handling

`CLIENT_SECRET` is held in `$env:CLIENT_SECRET` for the lifetime of the deploy shell session only. It is never written to any file, log, or committed artifact. If you need it after the shell exits, re-run `az ad app credential reset` to generate a new secret.

---

## Costs

~$1.13/day while deployed. Within the $50/day guardrail. Session cost for 4–6 h ≈ $0.28–$0.35.

Run `.\Cleanup-Lab.ps1 -Confirmed` (with Jose's approval) to stop billing.

---

## Troubleshooting

| Issue | Check |
|-------|-------|
| `ForbiddenByConnection` from Import-JwtLabEnvironment.ps1 | Run the script in **Azure Cloud Shell** (`bypass=AzureServices`). The script will print exact commands when this error is detected. Do not copy secrets manually. |
| App Service 403 on `/health` | Access restriction rule 100 may have wrong header; verify `az webapp config access-restriction show` |
| `EdgeActionConsoleLog` empty after 10 min | (1) Verify EA is attached to route; check `edgeActionsStatusCode` in FrontDoorAccessLog. (2) Confirm diagnostic settings `ea-logs` exist on the **EA resource** (not the AFD profile): `az monitor diagnostic-settings list --resource /subscriptions/.../providers/Microsoft.Cdn/EdgeActions/<name>` |
| `InvokeEdgeAction` action not found in Rules Engine API | Try `2025-12-01-preview` API version in deploy script |
| Admin consent fails | Verify `Application Administrator` role in Entra portal |
| Code upload slow | Normal — portal docs say up to 10 min; wait and retry |
