# S4 — Expired Token Evidence
Niobe · 2026-08-18 · **VERDICT: PASS**

## Test

`GET /protected` with fake JWT where `exp = now - 3600` (one hour in the past).

Token payload (decoded, no signature): `{"iss":"https://login.microsoftonline.com/TENANT/v2.0","aud":"api://<APP_ID>","exp":<past>,"nbf":<past-100>,"roles":["Lab.Admin"]}`

Note: ISS uses placeholder "TENANT". In production the real tenant ID is substituted. If the token passed the expiry check, it would also fail ISS_FAIL. Expiry check fires first in `ea-jwt-validate.js` (line order: exp → nbf → aud → iss → roles).

## Result

| HTTP Status | X-Azure-Ref (truncated) | EA Log |
|-------------|------------------------|--------|
| **401** | 20260818T102541Z-…1r55 | `EA_REJECT code=401 reason=EXPIRED exp=1787045174` |

EA correctly identifies token as expired before any other claim check.
Origin not reached.

## Verdict: PASS ✅

## Note on natural-expiry testing

Entra tokens have `exp` typically 3600 s from issuance. To test with a real Entra token, acquire at test start and re-submit after 1 hour. Alternatively, set a token lifetime policy on `app-edge-jwt-api` to reduce lifetime to 5–10 minutes. Not tested here due to B1 blocker.
