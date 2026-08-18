# S5 — Wrong Audience / Wrong Issuer Evidence
Niobe · 2026-08-18 · **VERDICT: PASS**

## S5a — Wrong Audience

`GET /protected` with JWT where `aud = "api://wrong-audience-00000000"`.

| HTTP Status | X-Azure-Ref (truncated) | EA Log |
|-------------|------------------------|--------|
| **401** | 20260818T102543Z-…59y3 | `EA_REJECT code=401 reason=AUD_FAIL got=api://wrong-audience-00000000` |

## S5b — Wrong Issuer

`GET /protected` with JWT where `iss = "https://login.microsoftonline.com/wrong-tenant-id/v2.0"`.

| HTTP Status | X-Azure-Ref (truncated) | EA Log |
|-------------|------------------------|--------|
| **401** | 20260818T102545Z-…8ts | `EA_REJECT code=401 reason=ISS_FAIL got=https://login.microsoftonline.com/wrong-tenant-id/v2.0` |

## S5c — Bare GUID audience (missing `api://` prefix)

From Tank smoke tests: token with `aud = "623405b7-..."` (bare GUID, no `api://` prefix).

EA log: `EA_REJECT code=401 reason=AUD_FAIL got=623405b7-...`

This is a common misconfiguration. The EA checks for exact string equality: `aud !== "api://<APP_ID>"`. A bare GUID fails even if it is the correct app ID.

## Verdict: PASS ✅

## Teaching note

The `iss` check in `ea-jwt-validate.js` uses `indexOf(EXPECTED_ISS_TENANT)` rather than strict equality. This tolerates the v1/v2 endpoint format difference. The tenant ID portion must still be present — a wrong tenant ID fails correctly.
