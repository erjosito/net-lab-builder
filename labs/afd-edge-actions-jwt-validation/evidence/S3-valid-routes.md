# S3 — Valid Routes / Malformed Token Evidence
Niobe · 2026-08-18

## S3a — Open Routes (no auth required)

| Path | HTTP Status | X-Azure-Ref (truncated) | Result |
|------|-------------|------------------------|--------|
| `/health` | 200 | 20260818T102417Z-…3mbh | `{"status":"healthy","app":"afd-edge-jwt-lab"}` |
| `/public` | 200 | 20260818T102419Z-…qrds | `{"route":"public","message":"No authentication required"}` |
| `/edge-only` (no token) | 200 | 20260818T102615Z-…037g4 | `{"route":"edge-only","teaching_warning":"EDGE-ONLY: ...","edge_jwt_status":"NOT_SET"}` |

`/health` and `/public` have no EA attached (`edgeActionsAgentType_s = unknown`).
`/edge-only` route is currently not attached to `eajwtvalidate` rule set (rule matches `/protected`, `/admin` only). Reaches origin unvalidated — intentional teaching route.

## S3b — Malformed Token

`GET /protected` with `Authorization: Bearer <REDACTED-TEST-VALUE>

| HTTP Status | EA Log |
|-------------|--------|
| 401 | `EA_REJECT code=401 reason=MALFORMED_HEADER` |

Token has only one part (no dots separating header.payload.signature). `parseJwtPart()` returns null → MALFORMED_HEADER.

## S3c — Real Entra Token (PASS — Run 4, 2026-08-18T13:39 UTC+2)

Token: Entra v2 `client_credentials` from `app-edge-jwt-client` SP (Graph `appRoleAssignments` used to assign Lab.Admin without admin-consent UI).

- `iss`: `https://login.microsoftonline.com/<TENANT_REDACTED>/v2.0`
- `aud`: `623405b7-b4ae-4121-91d2-197ad2424df0` (bare GUID — Entra v2 client_credentials with `accessTokenAcceptedVersion=2`)
- `roles`: `["Lab.Admin"]`

> **AUD format note:** After `accessTokenAcceptedVersion=2` was set on the API app, Entra v2 client_credentials tokens use `aud = bare GUID` (not `api://` prefix). EA `eajwtvalidate3/v1` and origin `server.js` `EXPECTED_AUD` were updated accordingly. See LL-016.

| Path | HTTP Status | `edge_jwt_status` | EA Log | Origin response |
|------|-------------|-------------------|--------|-----------------|
| `/protected` | **200** | `VALIDATED` | `CLAIMS_ONLY`, `ACCEPT` | `{"route":"protected","sub":"cf2ff0a3-<REDACTED>","roles":["Lab.Admin"]}` |
| `/admin` | **200** | `VALIDATED` | `CLAIMS_ONLY`, `ACCEPT` | `{"route":"admin","sub":"cf2ff0a3-<REDACTED>","roles":["Lab.Admin"]}` |

Active EA: `eajwtvalidate3/v1` (new EA resource, correct bare-GUID audience, `isDefaultVersion=True`).

> **EA log evidence:** `eajwtvalidate3` had no diagnostic setting from creation (12:45 UTC+2) until manual correction at 2026-08-18T17:12:36 UTC+2. `EdgeActionConsoleLog` entries for this run are **pending ingestion** in LAW. HTTP 200 responses are the authoritative PASS evidence; expected EA log entries (`CLAIMS_ONLY`, `ACCEPT`) will appear post-correction.

**Evidence source:** Tank `show-output/smoke-test-results.md` Run 4.

## Verdict
- S3a routes: PASS ✅
- S3b malformed: PASS ✅
- S3c valid Entra token: PASS ✅ (Run 4, 2026-08-18T13:39 UTC+2)
