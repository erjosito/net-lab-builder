# Deploy Log — afd-edge-actions-jwt-validation

All times local (UTC+2). Subscription and tenant IDs redacted.

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
| EA diagnostics | `diag-eajwtvalidate` | UserLog+ServiceLog → law-edge-jwt-lab |
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
