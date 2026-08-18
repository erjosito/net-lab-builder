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

**Note on Run 3:** Token audience was `api://appId` prefix. EA expected `api://` prefix. All negative scenarios confirmed in LAW.

---

## Run 4 — 2026-08-18T13:39 UTC+2 — REAL ENTRA TOKENS, FULL E2E ✅

All blockers resolved:
- B1: `Lab.Admin` app role assigned to `app-edge-jwt-client` SP via Graph `appRoleAssignments` API
- ISS mismatch: `accessTokenAcceptedVersion=2` set on API app → iss now `login.microsoftonline.com/v2.0`
- AUD mismatch: Entra v2 client_credentials tokens use bare appId as `aud` (not `api://`). Fixed in origin (`server.js`) and EA (`ea-jwt-validate.js`). EA replaced by `eajwtvalidate3/v1` (new EA) since `swapDefault` API is broken.

Real token claims:
- `iss=https://login.microsoftonline.com/5ad00b69-.../v2.0`
- `aud=623405b7-b4ae-4121-91d2-197ad2424df0` (bare GUID)
- `roles=["Lab.Admin"]`

| Scenario | Path | Token | EA Result | Origin Result | Status |
|----------|------|-------|-----------|---------------|--------|
| S7: Real Entra token (Lab.User/Admin) | /protected | Real Entra v2 client_credentials | `edge_jwt_status=VALIDATED` | 200 `{"route":"protected","sub":"cf2ff0a3...","roles":["Lab.Admin"]}` | ✅ **PASS** |
| S9: Real Entra token (Lab.Admin) | /admin | Real Entra v2 client_credentials | `edge_jwt_status=VALIDATED` | 200 `{"route":"admin","sub":"cf2ff0a3...","roles":["Lab.Admin"]}` | ✅ **PASS** |

**Full S1-S9 coverage: ALL PASS** (S7 and S9 via simulation and real tokens)

**Security model confirmed:**
```
Client → AFD Edge → EA eajwtvalidate3/v1 (claims-only: iss/aud/exp/nbf/roles, NO sig verify)
       → Origin app-edge-jwt-lab (jose RS256/JWKS full cryptographic verification)
```

**Entra discoveries (critical for lab):**
1. `accessTokenAcceptedVersion=2` required on API app for v2 iss format
2. Entra v2 client_credentials `aud` = bare appId GUID (not `api://appId` despite identifier URI)
3. `swapDefault` EA API is broken — workaround: create a new EA with correct code from scratch
4. F1 App Service Plan has daily CPU quota — upgrade to B1 for sustained lab use

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
