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

## S3c — Valid Real Entra Token (BLOCKED by B1)

A valid `Lab.Admin` token from `app-edge-jwt-client` requires admin consent. **PENDING — B1**.

Expected:
- `/protected`: HTTP 200, `EA_MODE=CLAIMS_ONLY`, `EA_ACCEPT`, origin returns `{"route":"protected","roles":["Lab.Admin"]}`
- `/admin`: HTTP 200, same EA flow, origin returns `{"route":"admin","roles":["Lab.Admin"]}`

Tank smoke tests confirm EA passes correctly-formed tokens: `EA_ACCEPT path=/protected roles=["Lab.Admin"]` visible at 10:31 UTC.

## Verdict
- S3a routes: PASS ✅
- S3b malformed: PASS ✅
- S3c valid Entra token: **PENDING (B1)** ⏸
