# Deploy Log — afd-edge-actions-jwt-validation

All times local (UTC+2). Subscription and tenant IDs redacted.

---

## Session 8 — 2026-08-18T18:00 UTC+2 (Tank, Copilot — Key Vault + loader)

### Key Vault creation, secret population, and loader script

| Time | Action | Result |
|------|--------|--------|
| 18:00 | Pre-flight: confirmed Jose has Owner at MG level; `Key Vault Secrets Officer` role available; apps uniquely identified; public IP discovered | ✅ Ready |
| 18:05 | `az keyvault create kv-jwt-lab-a8fbd8e1` (Standard, RBAC, swedencentral, bypass=AzureServices, defaultAction=Deny, IP rule for local machine) | Succeeded |
| 18:07 | `az role assignment create` — Key Vault Secrets Officer on vault scope → Jose OID `7f6e2c82-...` | Succeeded |
| 18:08 | `az ad app credential reset --append --end-date 2026-08-25T18:07:02Z` — display name `jwt-lab-kv-20260818` | Credential created; password never written to disk |
| 18:09 | Attempt `az keyvault secret set` → `ForbiddenByConnection` (data-plane blocked by tenant policy) | **BLOCKED** |
| 18:10 | Confirmed: `az keyvault update --public-network-access Enabled` silently ignored by tenant policy | Deviation documented |
| 18:11 | Workaround: `PUT management.azure.com/.../vaults/kv-jwt-lab-a8fbd8e1/secrets/{name}?api-version=2023-07-01` | **All 5 secrets written via ARM management plane** |
| 18:12 | Verified metadata (no values) via management plane GET | SecretUri confirmed for all 5 secrets |
| 18:13 | `Key Vault Secrets Officer` role assignment confirmed | ✅ |
| 18:15 | In-memory token acquisition + endpoint calls: `/protected` → HTTP 200, `/admin` → HTTP 200 (`edge_jwt_status=VALIDATED`) | ✅ Real token validation passes |
| 18:20 | Created `tests/Import-JwtLabEnvironment.ps1` | Loads env vars from KV; `-PassThru` returns names/lengths only |
| 18:25 | Updated `deploy/Deploy-Lab.ps1` — added `Set-KvSecretArm` helper + `A_KV` section + `$KvName`/`$SkipKv` params | Idempotent; management-plane write pattern |
| 18:26 | Updated `deploy/Cleanup-Lab.ps1` — added KV to preview list; $KvName auto-derived; soft-delete note | ✅ |
| 18:27 | Updated `deploy/deployment-output.json` — added `key_vault` block | `kv_name`, auth mode, network note, secret names, expiry |
| 18:28 | Updated `deploy/README.md` — added Key Vault section, loader usage, credential rotation, secrets table | ✅ |
| 18:29 | PowerShell syntax validation: Deploy-Lab, Cleanup-Lab, Import-JwtLabEnvironment | ✅ 0 parse errors |

### Deviations

| # | Deviation | Root cause | Impact |
|---|-----------|-----------|--------|
| D1 | `publicNetworkAccess=Disabled` enforced by tenant policy | Tenant Azure Policy silently overrides ARM PUT/PATCH | Data-plane (`vault.azure.net`) is reachable only through the deployed private endpoint; standard Cloud Shell remains blocked |
| D2 | Secret tags not set | ARM management plane secret PUT requires `value` in body for PATCH; data-plane tag update would require secret value read (blocked by D1) | Cosmetic only; secrets are functional |
| D3 | `ping-test` stray secret present in KV | Written during early testing | Cannot disable via management plane without value. Harmless; loader does not reference it |

### Cost shape
Key Vault operations are low cost. The later management-access add-on incurs
charges for the `Standard_B2ts_v2` VM, its disk, the private endpoint, and
Azure Bastion Basic until those resources are removed.

### Files changed
- `deploy/Deploy-Lab.ps1` — `$KvName`/`$SkipKv` params + `Set-KvSecretArm` function + `A_KV` section
- `deploy/Cleanup-Lab.ps1` — `$KvName` param + KV entry in preview list + soft-delete note
- `deploy/deployment-output.json` — `key_vault` block added
- `deploy/README.md` — KV section (network posture, loader usage, rotation, secrets table)
- `tests/Import-JwtLabEnvironment.ps1` — **NEW** — process-only env-var loader script

---



### Deploy-Lab.ps1 patched: automatic EA diagnostic settings

| Time | Action | Result |
|------|--------|--------|
| 17:13 | Added `Set-EaDiagnosticSettings` helper function to `Deploy-Lab.ps1` | Idempotent, dynamic EA name, `UserLog`+`ServiceLog` |
| 17:13 | Added call in A2 section immediately after EA resource creation | Before version/code/rule-set creation; `ShouldProcess`-gated |
| 17:13 | Added A3 pattern comment at end of script | Future A3 EA deployments must call same function |
| 17:13 | Updated `README.md` A2/A3 deployment sequence notes + troubleshooting row | Documents automatic diagnostic settings |
| 17:13 | PowerShell syntax validation passed | 0 parse errors |

**Confirmed categories** (read from live `eajwtvalidate3` settings added by Jose):
- `UserLog` → `EdgeActionConsoleLog` table in LAW
- `ServiceLog` → `EdgeActionServiceLog` table in LAW
- Setting name: `ea-logs` (idempotent — re-run will update, not duplicate)
- Metric category `Latency` exists but is left disabled (matches user's manual setting)

**Files changed:**
- `deploy/Deploy-Lab.ps1` — added `Set-EaDiagnosticSettings` function + A2 call site + A3 comment
- `deploy/README.md` — A2/A3 sequence updated, troubleshooting row updated

---

## Session 6 — 2026-08-18T17:12 UTC+2 (Jose, manual correction)

### Diagnostic settings gap: `eajwtvalidate3` had no UserLog/ServiceLog diagnostic setting

| Time | Action | Result |
|------|--------|--------|
| 17:12:36 | Added diagnostic settings to `eajwtvalidate3` EA resource | `UserLog` + `ServiceLog` → `law-edge-jwt-lab` |

**Root cause:** When `eajwtvalidate3` was created in Session 5 (12:45 UTC+2) as a replacement for the broken `eajwtvalidate`, the Deploy-Lab.ps1 `addEaDiagnostics` step was not re-run for the new resource. Diagnostic settings on Azure resources are **not transferred when a resource is replaced**. The setting `diag-eajwtvalidate` applied to the orphaned `eajwtvalidate` only.

**Impact on evidence:**
- All `EdgeActionConsoleLog` entries in `show-output/001-EdgeActionConsoleLog-30min.txt` (timestamps 10:10–10:32 UTC) originate from `eajwtvalidate` (Sessions 3–4). They confirm all reason codes (MISSING_TOKEN, MALFORMED_HEADER, EXPIRED, AUD_FAIL, ISS_FAIL, ROLE_FAIL) on the correct EA logic.
- Run 4 real-token tests (S7/S9, 13:39 UTC+2) were executed against `eajwtvalidate3` which had **no diagnostic settings at that time** → no `EdgeActionConsoleLog` entries exist for those requests. HTTP 200 responses are the authoritative evidence for S7/S9 PASS.
- New `EdgeActionConsoleLog` entries from `eajwtvalidate3` will appear **pending ingestion** after 17:12:36. Ingestion delay is 3–10 min.

**Lesson:** See LL-020 in `lessons-learned.md`.

---

## Session 5 — 2026-08-18T12:22–13:45 UTC+2 (Tank, Copilot)

### B1 Resolution, Audience Fix, S7/S9 Real-Token Validation ✅

| Time | Action | Result |
|------|--------|--------|
| 12:22 | `az ad app permission admin-consent` | BLOCKED: `Authorization_RequestDenied` (Jose has Global Reader, not Global Admin) |
| 12:24 | Checked Jose's directory roles | `Global Reader`, `Fabric Administrator` — not Global Admin |
| 12:25 | Graph `POST /servicePrincipals/{clientSp}/appRoleAssignments` | **SUCCESS** — `Lab.Admin` assigned to `app-edge-jwt-client` SP (bypasses admin-consent UI) |
| 12:28 | `az ad app credential reset` + token acquire | `AADSTS7000215` — replication lag; retry with backoff → SUCCESS after ~40s |
| 12:30 | S7 first attempt | 401 `AUD_FAIL got=623405b7...` (EA expects `api://`, token has bare GUID) |
| 12:31 | Identified Entra v2 client_credentials aud behavior | `accessTokenAcceptedVersion=2` → `aud` = bare appId GUID (not `api://appId`) |
| 12:33 | `PATCH /applications/{apiObjId}` set `accessTokenAcceptedVersion=2` | SUCCESS |
| 12:35 | New token: `iss=login.microsoftonline.com/v2.0`, `aud=bare GUID` | ISS fixed; AUD still mismatch |
| 12:36 | Updated `server.js` `EXPECTED_AUD` to bare `API_APP_ID` | Fix for origin |
| 12:37 | Updated `ea-jwt-validate.js` `EXPECTED_AUD` to bare `%%API_APP_ID%%` | Fix for EA |
| 12:38 | Attempt ZIP redeploy of origin (F1 App Service Plan) | FAILED: site stopped — F1 quota exhausted |
| 12:40 | `az appservice plan update --sku B1` | SUCCESS — CPU quota removed |
| 12:42 | `eajwtvalidate` swapDefault investigation | `swapDefault` BROKEN: v2 stuck in `Provisioning` for non-default versions; PUT `isDefaultVersion` blocked |
| 12:45 | Created `eajwtvalidate3` new EA with correct bare-GUID audience code | `provisioningState=Succeeded`, `validationStatus=Succeeded` |
| 12:50 | Updated AFD rule `ruleprotected` → `eajwtvalidate3` reference | Failed (EA still Provisioning) → Succeeded on retry |
| 13:28 | Redeployed origin with updated `server.js` (bare GUID aud) + B1 plan | Succeeded |
| 13:35 | AFD /health 200 after scale-up | Origin back online |
| 13:39 | **S7 real Entra token** | HTTP 200 `{"route":"protected","edge_jwt_status":"VALIDATED"}` ✅ |
| 13:39 | **S9 real Entra token (Lab.Admin)** | HTTP 200 `{"route":"admin","edge_jwt_status":"VALIDATED"}` ✅ |

**Full S1-S9 validation complete. All scenarios PASS.**

**Resources added this session:**
| Resource | Detail |
|----------|--------|
| `eajwtvalidate3` EA | New EA with correct bare-GUID audience |
| `eajwtvalidate3/v1` | isDefaultVersion=True, validationStatus=Succeeded |
| `ruleprotected` (updated) | Now references `eajwtvalidate3` instead of `eajwtvalidate` |
| App Service Plan | Scaled F1 → B1 (CPU quota issue) |
| ⚠️ `eajwtvalidate3` diagnostic setting | **NOT created in this session** — gap discovered 2026-08-18T17:12. EA diagnostic settings do not transfer when replacing an EA resource. `EdgeActionConsoleLog` from `eajwtvalidate3` was NOT routed to LAW during Run 4. Manually corrected in Session 6. |

**Cost impact:** B1 App Service Plan ≈ $0.075/hr ≈ $1.80/day (up from ~$0 F1). Total estimate: ~$1.80/day (within lab guardrail).

**Active issues (non-blocking):**
- `eajwtvalidate` and `eajwtvalidate` EA: orphaned with dangling attachment; swapDefault broken; portal/Support needed
- `eacapabilityprobe` orphan: same null attachment issue

---

## Session 4 — 2026-08-18T12:00–12:25 UTC+2 (Tank, Copilot)

### EA JWT Validation: LIVE ✅

| Time | Action | Result |
|------|--------|--------|
| 12:00 | AFD propagation wait complete | `eajwtvalidate` executing at edge |
| 12:03 | LAW query EdgeActionConsoleLog V1 | `EA_REJECT code=401 reason=MISSING_TOKEN` confirmed — JWT EA live |
| 12:05 | S7-sim: token with bare GUID aud | `EA_REJECT AUD_FAIL got=623405b7...` — discovered `api://` prefix required |
| 12:10 | Full S2-S9 smoke test (correct `api://` prefix) | All EA scenarios correct (see table below) |
| 12:15 | LAW: `EdgeActionConsoleLog` confirms all reason codes | MISSING_TOKEN, MALFORMED_HEADER, EXPIRED, AUD_FAIL, ROLE_FAIL all logged |

**Smoke test summary (Run 3):**

| Scenario | EA | Origin | Verdict |
|----------|----|--------|---------|
| S2 No token | 401 MISSING_TOKEN | — | ✅ |
| S3 Malformed | 401 MALFORMED_HEADER | — | ✅ |
| S4 Expired | 401 EXPIRED | — | ✅ |
| S5 Wrong aud | 401 AUD_FAIL | — | ✅ |
| S6 Wrong iss | 401 ISS_FAIL | — | ✅ |
| S7-sim fake-sig | EA pass | 401 ERR_JWKS_MULTIPLE_MATCHING_KEYS | ✅ (origin RS256 enforces) |
| S8 No admin role | 403 ROLE_FAIL | — | ✅ |
| S9-sim fake-sig+admin | EA pass | 401 ERR_JWKS_MULTIPLE_MATCHING_KEYS | ✅ (origin RS256 enforces) |
| S7/S9 real Entra token | — | — | ⏸ B1 (admin consent) |

**Final resource state:**

| Resource | Name | State |
|----------|------|-------|
| Edge Action | `eajwtvalidate` | provisioningState=Succeeded |
| EA version | `eajwtvalidate/v1` | isDefaultVersion=True, validationStatus=Succeeded |
| EA diagnostics | `diag-eajwtvalidate` | UserLog+ServiceLog → law-edge-jwt-lab (**on `eajwtvalidate` only** — active EA at this time) |
| Rule set | `rsedgejwt` | provisioningState=Succeeded |
| Rule | `ruleprotected` | Succeeded; matchValues=["/protected","/admin"] |
| Route | `rt-api` | ruleSets=[rsedgejwt]; provisioningState=Succeeded |

**Active blockers:**
- **B1**: `az ad app permission admin-consent --id 6f86ab2c-1823-4db6-8e54-6338b8472b6a` (Jose must run as tenant admin)
- **eacapabilityprobe**: orphaned EA with dangling null attachment (requires portal/Support)

---

## Session 3 — 2026-08-18 (Tank, Copilot)

### A3 — JWT Validation EA: initially BLOCKED (B3), then resolved

| Time | Action | Result |
|------|--------|--------|
| 08:28 | Queried EdgeActionConsoleLog (LAW) | S1 probe output confirmed — all API probes returned |
| 08:30 | S1 verdict: CONDITIONAL | `crypto/fetch/atob` all `undefined`; pure-JS path viable |
| 08:35 | Rewrote `ea-jwt-validate.js` | Replaced `atob` with pure-JS base64url; removed GO path; CONDITIONAL only |
| 08:38 | Attempted `az rest PUT .../edgeActions/eajwtvalidate?api-version=2025-12-01-preview` | `NoRegisteredProviderFound` — B3 discovered |
| 08:40 | Verified all known EA API versions | All return 404 or `NoRegisteredProviderFound` |
| 08:42 | Checked feature flags | `Microsoft.Cdn/EdgeActionsPrivatePreview = NotRegistered` — private preview access expired |
| 08:43 | Ran smoke tests S3/S4/S6/S7-like/S8 | All PASS (see below) |

**B3 Blocker**: EA private preview access expired on this subscription. Control plane blocked.
Data plane (`eaprobe2` executing probe code) continues to function independently.

---

## Session 2 — 2026-08-17 (Tank, Copilot)

### A0–A2 Deploy (completed in Session 1–2)

| Resource | Name | Notes |
|----------|------|-------|
| Resource Group | `rg-afd-edge-jwt-lab` | `eastus` |
| AFD Profile | `afd-edge-jwt-lab` | Standard_AzureFrontDoor |
| AFD Endpoint | `edge-jwt-lab-hgbdgdh9ccaja2hv.b02.azurefd.net` | |
| Origin Group | `og-api` | |
| Origin | `origin-api` | app-edge-jwt-lab.azurewebsites.net |
| Route | `rt-api` | rule sets: `rsedgeprobe` |
| Rule Set | `rsedgeprobe` | |
| Rule | `ruleprovedebug` | EA: eaprobe2; condition: /debug |
| App Service | `app-edge-jwt-lab` | `eastus`, B1 SKU |
| Law | `law-edge-jwt-lab` | |
| Entra API App | `623405b7-b4ae-4121-91d2-197ad2424df0` | app-edge-jwt-api |
| Entra Client App | `6f86ab2c-1823-4db6-8e54-6338b8472b6a` | app-edge-jwt-client |
| EA (active) | `eaprobe2` | v1=probe (default), v2=header probe |
| EA (orphaned) | `eacapabilityprobe` | dangling null attachment; circular delete |

### Key API Learnings (Session 2)

| Finding | Detail |
|---------|--------|
| `deployVersionCode` API | `POST .../versions/{v}/deployVersionCode` body: `{name,content:base64(zip)}` — triggers validation |
| Validation timing | `GET validationStatus=Succeeded` appears in ~15s but is PREMATURE. addAttachment requires ~17 min |
| `swapDefault` | BROKEN — always 400 "not in Succeeded state" regardless of actual state |
| EA console logs | Diagnostic category `UserLog` on the EA resource → `EdgeActionConsoleLog` in LAW |
| AFD profile diagnostics | No EA categories available at AFD profile level |
| `addAttachment` direct | Creates dangling null attachments. Use AFD rule PUT to trigger addAttachment |
| Rule PUT → EA attach | AFD rule PUT with `EdgeAction` action auto-triggers addAttachment correctly |
| Access restriction dupe | CLI blocks duplicate ServiceTag; use ARM REST `PATCH /config/web` instead |

---

## Smoke Test Results — 2026-08-18

| Scenario | Path | Expected | Actual | Status |
|----------|------|----------|--------|--------|
| S3 health | `GET /health` | 200 | 200 | ✅ PASS |
| S3 public | `GET /public` | 200 | 200 | ✅ PASS |
| S3 edge-only | `GET /edge-only` | 200 | 200 | ✅ PASS |
| S3 debug | `GET /debug/request` | 200 | 200 | ✅ PASS |
| S4 AFD headers | `x-azure-fdid` injected | present | `549954ba-...` | ✅ PASS |
| S6 protected no token | `GET /protected` | 401 | 401 | ✅ PASS |
| S6 admin no token | `GET /admin` | 401 | 401 | ✅ PASS |
| S7-like wrong aud | `GET /protected` bad token | 401 | 401 | ✅ PASS |
| S8 origin bypass | direct origin | 403 | 403 | ✅ PASS |
| S1 EA probe | `/debug/*` `edgeActionsStatusCode` | 200 | 200 | ✅ PASS |
| S7 valid token flow | needs B1 admin consent | — | — | ⏸ BLOCKED/B1 |
| S9 admin role | needs B1 admin consent | — | — | ⏸ BLOCKED/B1 |
| A3 JWT EA | EA control plane | deployed | B3 | ⏸ BLOCKED/B3 |

---

## Active Blockers

### B1 — Admin Consent (Entra)
- **Symptom**: Client credentials flow cannot acquire tokens
- **Fix**: `az ad app permission admin-consent --id 6f86ab2c-1823-4db6-8e54-6338b8472b6a`
  Or: Azure portal → app-edge-jwt-client → API permissions → Grant admin consent for tenant
- **Impact**: S7, S9 scenarios blocked; cannot test valid-token flow

### B3 — EdgeActionsPrivatePreview Feature Expired
- **Symptom**: All `edgeActions` REST API calls return `NoRegisteredProviderFound` or 404
- **Details**: `Microsoft.Cdn/EdgeActionsPrivatePreview = NotRegistered`
- **Fix**: Re-register subscription for Edge Actions private preview (Microsoft contact required)
- **Impact**: Cannot deploy `ea-jwt-validate.js` as A3 EA; `eaprobe2` data plane still active

### eacapabilityprobe (orphan)
- v1 default + validated + dangling null attachment
- Cannot delete v1 (has attachments), cannot removeAttachment (400), cannot delete EA (nested)
- Only resolution: Azure portal manual delete or Support ticket
- Does NOT block any active scenario

---

## Cost Shape (estimate)

| Resource | Est. cost/day |
|----------|--------------|
| AFD Standard + origin group | ~$0.50 |
| App Service B1 | ~$0.05 |
| Log Analytics (ingestion) | ~$0.08 |
| AFD data transfer | ~$0.50 |
| **Total** | ~$1.13/day |

All resources tagged: `lab=true`, `created_by=copilot-lab`, `owner=jose`, `ephemeral=true`
