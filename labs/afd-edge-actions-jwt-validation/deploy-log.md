# Deploy Log — afd-edge-actions-jwt-validation
Tank · 2026-08-17/18

---

## Change Log

| Timestamp (UTC) | Operation | Resource | State | Elapsed |
|-----------------|-----------|----------|-------|---------|
| 2026-08-17T13:09Z | az group create | rg-afd-edge-jwt-lab | Succeeded | 8s |
| 2026-08-17T13:19Z | Bicep deployment A0 | main.bicep | Succeeded | ~10 min |
| 2026-08-17T13:19Z | App Service access restriction rule 100 | afd-healthprobe | Configured | |
| 2026-08-17T13:19Z | App Service access restriction rule 200 | afd-fdid (via ARM REST) | Configured | |
| 2026-08-17T13:24Z | App Service code deploy (zip) | app-edge-jwt-lab | Succeeded | ~2 min |
| 2026-08-17T13:24Z | Entra app registration | app-edge-jwt-api | Created | |
| 2026-08-17T13:24Z | Entra app ID URI + Lab.Admin role | app-edge-jwt-api | Configured | |
| 2026-08-17T13:25Z | Entra app registration | app-edge-jwt-client | Created | |
| 2026-08-17T13:28Z | Admin consent | app-edge-jwt-client | **FAILED — B1 BLOCKER** | |
| 2026-08-17T13:28Z | Client secret | app-edge-jwt-client | Generated (process-only) | |
| 2026-08-17T13:30Z | Edge Action resource | eacapabilityprobe | Succeeded (SKU=Standard/Standard, location=global) | |
| 2026-08-17T13:33Z | Edge Action version v1 | eacapabilityprobe/versions/v1 | Succeeded (deploymentType=zip) | |
| 2026-08-17T13:33Z | AFD rule set | rsedgeprobe | Succeeded | |
| 2026-08-17T13:43Z | AFD rule | ruleprovedebug | **FAILED repeatedly — B2 BLOCKER** | |
| 2026-08-18T06:00Z | App Service access restriction (ARM REST) | Two-rule FDID pattern | Succeeded | |
| 2026-08-18T06:01Z | Smoke tests | All 4 | PASS | |

---

## Activation Unit Ledger

| Unit | Status | Notes |
|------|--------|-------|
| **A0** | ✅ COMPLETE | RG + LAW + App Service Plan/App + AFD profile/endpoint/origin/route + diag settings + access restrictions |
| **A1** | ⚠️ PARTIAL | App registrations created; Lab.Admin role configured; client secret in process env; admin-consent BLOCKED (B1) |
| **A2** | ⚠️ PARTIAL | EA resource + versions created; rule set + rule created; EA attachment BLOCKED by validation API gap (B2) |
| **S1-GATE** | 🔴 BLOCKED | Cannot collect EdgeActionConsoleLog without EA attachment |
| **A3** | ⏳ NOT_STARTED | Pending S1-GATE |
| **A4** | ⏳ NOT_STARTED | Pending A3 |

---

## Blockers

### B1 — Entra Admin Consent (MEDIUM)
- **Error:** `Authorization_RequestDenied` — Application Administrator role required
- **Impact:** Token acquisition fails; S2-S9 JWT scenarios blocked until resolved
- **Resolution:** Jose or tenant admin runs `az ad app permission admin-consent --id <client-app-id>`
- **Workaround:** Entra-independent smoke tests (S8 direct bypass, /health, /public) pass

### B2 — Edge Action Code Validation (CRITICAL)
- **Error:** `Validation failed: The edge action's default version is not in a successful state`
- **Impact:** EA cannot be attached to AFD route; S1 capability probe cannot run
- **Root cause:** `validationStatus` not populated by REST API; only by portal/VS Code extension
- **API versions tried:** 2025-09-01-preview, 2025-12-01-preview, 2024-07-22-preview
- **Resolution:** Portal upload: Edge Actions → eacapabilityprobe → Versions → re-upload ea-capability-probe.js
- **Evidence:** activity log `addAttachment/action` failed 2026-08-18T06:03:48Z

---

## API Version Reference

| Resource | API Version Used | Notes |
|----------|-----------------|-------|
| Microsoft.Cdn/profiles | 2025-04-15 | AFD profile, endpoint, origin, route |
| Microsoft.Cdn/EdgeActions | 2025-09-01-preview | EA create (SKU=Standard/Standard, location=global) |
| Microsoft.Cdn/EdgeActions/versions | 2025-09-01-preview | Version create (deploymentType=zip, code=b64(zip)) |
| Microsoft.Cdn/profiles/ruleSets | 2025-09-01-preview | Required for EdgeAction action (not in stable CDN API) |
| Microsoft.Web/sites/config | 2023-12-01 | ARM REST for dual-ServiceTag access restriction |
| Microsoft.OperationalInsights | 2023-09-01 | Log Analytics workspace |

---

## Cost Shape (Actual, 2026-08-18)

- AFD Standard: ~$0.75/day (profile active)
- App Service B1: ~$0.05/day (running, no traffic)
- Log Analytics: ~$0.25/day (minimal ingestion)
- Entra app registrations: $0.00
- **Estimated daily total: ~$1.05/day** (within $1.13 estimate, within $50/day guardrail)

---

## Deviations from Design

| ID | Design Assumption | Actual | Impact |
|----|-------------------|--------|--------|
| D1 | `az CLI` supports `az afd edge-action` commands | No such CLI subcommand; all EA ops via `az rest` | Deploy script uses `az rest` correctly |
| D2 | EA is subscription-level resource | EA is RG-level resource | URL pattern corrected |
| D3 | EA location = swedencentral | EA location must be `global` | Corrected |
| D4 | EA SKU = Standard_AzureFrontDoor | EA SKU = `Standard/Standard` | Corrected |
| D5 | EA name = ea-capability-probe | EA name must be alphanumeric: `eacapabilityprobe` | Corrected |
| D6 | Code upload via `code` property (JSON inline) | Works for zip only; file type not inline | Both attempted; zip works for PUT |
| D7 | `validationStatus` auto-triggers after upload | Validation not triggered by REST API | **B2 blocker** |
| D8 | `az webapp config access-restriction add` supports two rules with same ServiceTag | CLI blocks duplicate ServiceTag | Worked around via ARM REST PATCH |
| D9 | AFD rule action = `InvokeEdgeAction` | Correct name = `EdgeAction`, typeName = `DeliveryRuleEdgeActionParameters` | Corrected; rule created successfully |
| D10 | `invocationPoint` not required | Required property — omitting causes BadRequest | Added |

---

## Cleanup Gate

**NOT APPROVED.** Do not run Cleanup-Lab.ps1 until Jose explicitly approves.
Cleanup script is preview-safe (lists only unless -Confirmed is passed).
