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

A2  ea-capability-probe Edge Action → /debug/* route
    AFD rule set rs-edge-probe created and attached to rt-api route

S1-GATE
    Query EdgeActionConsoleLog after GET /debug/request
    Verdict: GO / CONDITIONAL / STOP  (see design.md §4.3)

A3  (Conditional on S1-GATE GO/CONDITIONAL)
    ea-jwt-validate Edge Action → /edge-only, /protected, /admin routes
    ea-execution-filter Edge Action version (execution filter: X-Test-Fail: 1)

A4  Token acquisition + scenario smoke tests S2-S9
```

---

## Edge Actions API Notes

Edge Actions are a **subscription-level** `Microsoft.Cdn/EdgeActions` resource (not nested under an AFD profile). The deploy script uses `az rest` with the `2025-09-01-preview` API version.

AFD attachment is via a Rules Engine rule set on the AFD profile, with an `InvokeEdgeAction` action.

Code upload is base64-encoded. The portal notes upload can take up to **10 minutes** — the script waits 60 seconds and then proceeds.

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
| App Service 403 on `/health` | Access restriction rule 100 may have wrong header; verify `az webapp config access-restriction show` |
| EdgeActionConsoleLog empty after 10 min | Verify EA is attached to route; check `edgeActionsStatusCode` in FrontDoorAccessLog |
| `InvokeEdgeAction` action not found in Rules Engine API | Try `2025-12-01-preview` API version in deploy script |
| Admin consent fails | Verify `Application Administrator` role in Entra portal |
| Code upload slow | Normal — portal docs say up to 10 min; wait and retry |
