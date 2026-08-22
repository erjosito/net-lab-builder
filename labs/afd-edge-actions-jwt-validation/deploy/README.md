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
- **Reading** secret values requires a private-endpoint-connected host. Standard
  Cloud Shell uses the public data-plane endpoint and cannot reach this vault.

### Loading test credentials — private management VM

The deployed management path is:

```bash
# Azure portal: vm-edge-jwt-management > Connect > Bastion
# Username: azurelabuser; authentication: local SSH private key
source /usr/local/share/jwt-lab/Import-JwtLabEnvironment.sh
```

The VM has Azure CLI installed and uses its system-assigned managed identity,
which has `Key Vault Secrets User` at vault scope. Private DNS resolves
`kv-jwt-lab-a8fbd8e1.vault.azure.net` to the private endpoint. The variables
remain set only for the current Bash session.

The installed loader is also maintained in the repository as
`tests/Import-JwtLabEnvironment.sh`. The PowerShell loader remains available
for any PowerShell host connected to the same VNet/private DNS path.

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
| `ForbiddenByConnection` from an environment loader | Connect to `vm-edge-jwt-management` through Azure Bastion. Standard Cloud Shell and local hosts use the blocked public endpoint. |
| App Service 403 on `/health` | Access restriction rule 100 may have wrong header; verify `az webapp config access-restriction show` |
| `EdgeActionConsoleLog` empty after 10 min | (1) Verify EA is attached to route; check `edgeActionsStatusCode` in FrontDoorAccessLog. (2) Confirm diagnostic settings `ea-logs` exist on the **EA resource** (not the AFD profile): `az monitor diagnostic-settings list --resource /subscriptions/.../providers/Microsoft.Cdn/EdgeActions/<name>` |
| `InvokeEdgeAction` action not found in Rules Engine API | Try `2025-12-01-preview` API version in deploy script |
| Admin consent fails | Verify `Application Administrator` role in Entra portal |
| Code upload slow | Normal — portal docs say up to 10 min; wait and retry |
