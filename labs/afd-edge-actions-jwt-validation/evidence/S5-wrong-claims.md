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

## S5c — Audience format correction

An earlier Edge Action revision expected an `api://` audience and rejected the bare application
ID. The final Entra v2 configuration and current source use the bare application ID as the exact
audience.

The current check remains strict: any value other than the configured audience is rejected.

## Verdict: PASS ✅

## Teaching note

The simplified source uses strict equality for the complete v2 issuer URL. Tokens from another
tenant or issuer version are rejected.
