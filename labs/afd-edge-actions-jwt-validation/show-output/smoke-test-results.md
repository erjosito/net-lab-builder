# Smoke Test Results — afd-edge-actions-jwt-validation

## Run 3 — 2026-08-18T12:15 UTC+2 (post JWT EA propagation — eajwtvalidate LIVE)

Token format: fake-signed JWTs with correct `api://` audience prefix substituted at deploy time.
EA is CONDITIONAL (claims-only). Origin uses `jose` for real RS256/JWKS.

| Scenario | Path | Token/Condition | EA Result | Origin Result | Status |
|----------|------|-----------------|-----------|---------------|--------|
| S2: No token | /protected | — | 401 MISSING_TOKEN | — | ✅ PASS |
| S3: Malformed | /protected | `notavalidtoken` | 401 MALFORMED_HEADER | — | ✅ PASS |
| S4: Expired | /protected | exp in past | 401 EXPIRED | — | ✅ PASS |
| S5: Wrong audience | /protected | aud=wrong-audience | 401 AUD_FAIL | — | ✅ PASS |
| S6: Wrong issuer | /protected | iss=wrong-tenant | 401 ISS_FAIL | — | ✅ PASS |
| S7-sim: Valid claims | /protected | Lab.User, correct iss/aud/exp, **fake sig** | EA passes (200) | 401 ERR_JWKS_MULTIPLE_MATCHING_KEYS | ✅ EXPECTED (origin RS256 rejects fake sig) |
| S8: Missing role | /admin | Lab.User, valid claims | 403 ROLE_FAIL | — | ✅ PASS |
| S9-sim: Lab.Admin | /admin | Lab.Admin, correct claims, **fake sig** | EA passes (200) | 401 ERR_JWKS_MULTIPLE_MATCHING_KEYS | ✅ EXPECTED (origin RS256 rejects fake sig) |
| /public | /public | — | passthrough | 200 {"route":"public"} | ✅ PASS |
| /health | /health | — | passthrough | 200 {"status":"healthy"} | ✅ PASS |
| S7 Real token | /protected | Valid Entra token | — | — | ⏸ BLOCKED/B1 |
| S9 Real admin | /admin | Lab.Admin Entra token | — | — | ⏸ BLOCKED/B1 |

**Confirmed security model:**
```
Client → AFD Edge → EA (claims-only: iss/aud/exp/nbf/roles, NO sig verify) → Origin (jose RS256/JWKS, real crypto)
```
EA intercepts early: S2-S6 and S8 blocked before origin. S7/S9 with real Entra tokens require B1 resolution.

**LAW evidence (EdgeActionConsoleLog, 10:10-10:16 UTC):**
- `EA_REJECT code=401 reason=MISSING_TOKEN` ✅
- `EA_REJECT code=401 reason=MALFORMED_HEADER` ✅
- `EA_REJECT code=401 reason=EXPIRED exp=...` ✅
- `EA_REJECT code=401 reason=AUD_FAIL got=wrong-audience` ✅
- `EA_REJECT code=401 reason=AUD_FAIL got=623405b7...` (bare GUID, not api://) ✅

**B1**: Admin consent not granted → `az ad app permission admin-consent --id 6f86ab2c-1823-4db6-8e54-6338b8472b6a`
**AFD endpoint**: `https://edge-jwt-lab-hgbdgdh9ccaja2hv.b02.azurefd.net`

---

## Run 2 — 2026-08-18 (post S1)

| Test | Path | Expected | Result | Status |
|------|------|----------|--------|--------|
| S3 AFD Health | GET /health | 200 | 200 `{"status":"healthy"}` | ✅ PASS |
| S3 AFD Public | GET /public | 200 | 200 `{"route":"public"}` | ✅ PASS |
| S3 AFD Edge-only | GET /edge-only | 200 | 200 (teaching_warning present) | ✅ PASS |
| S3 AFD Debug | GET /debug/request | 200 | 200 (EA executing) | ✅ PASS |
| S4 AFD x-azure-fdid | GET /debug/request | header present | `549954ba-...` injected | ✅ PASS |
| S1 EA probe executing | /debug agentType | node | edgeActionsAgentType=node | ✅ PASS |
| S6 Protected no token | GET /protected | 401 | 401 MISSING_TOKEN | ✅ PASS |
| S6 Admin no token | GET /admin | 401 | 401 MISSING_TOKEN | ✅ PASS |
| S7-like wrong aud | GET /protected bad token | 401 | 401 (origin rejects) | ✅ PASS |
| S8 Origin bypass | direct origin /health | 403 | 403 Ip Forbidden | ✅ PASS |
| S7 Valid token flow | GET /protected + valid JWT | 200 | — | ⏸ BLOCKED/B1 |
| S9 Admin role | GET /admin + Lab.Admin role | 200 | — | ⏸ BLOCKED/B1 |

**B1**: Admin consent not granted → cannot acquire valid tokens.
**B3**: EA private preview expired → cannot deploy A3 JWT validation EA.

## AFD Endpoint
`https://edge-jwt-lab-hgbdgdh9ccaja2hv.b02.azurefd.net`

## Run 1 — 2026-08-17 (initial)

| Test | Path | Expected | Result | Status |
|------|------|----------|--------|--------|
| AFD Health | GET /health | 200 OK | 200 {"status":"healthy"} | ✅ PASS |
| AFD Public | GET /public | 200 OK | 200 {"route":"public"} | ✅ PASS |
| AFD Protected no token | GET /protected | 401 | 401 {"error":{"code":"MISSING_TOKEN"}} | ✅ PASS |
| S8 Direct origin bypass | GET app-edge-jwt-lab.azurewebsites.net/health | 403 | 403 Forbidden | ✅ PASS |
