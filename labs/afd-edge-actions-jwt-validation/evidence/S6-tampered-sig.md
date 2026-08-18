# S6 — Tampered Token / Signature Enforcement Evidence
Niobe · 2026-08-18 · **VERDICT: PASS (CONDITIONAL path confirmed)**

## Architecture reminder

In the CONDITIONAL path, the Edge Action **cannot verify the JWT signature** (`crypto.subtle` unavailable). It performs claims-only validation: iss, aud, exp, nbf, roles. A structurally valid JWT with correct claims but a fake/broken signature **passes the Edge Action** and reaches the origin. The origin (`jose` library) performs full RS256/JWKS signature verification.

## Test (from Tank Run 3, 2026-08-18T10:31 UTC)

JWT constructed with:
- Correct `iss` (real tenant ID, matching EA config)
- Correct `aud = "api://<APP_ID>"`
- Valid `exp` (future)
- `roles = ["Lab.Admin"]`
- **Signature replaced with random bytes** (cryptographically invalid)

## EA Result

```
EA_MODE=CLAIMS_ONLY alg=RS256
EA_ACCEPT path=/protected roles=["Lab.Admin"]
```

EA passes the token (claims-only mode, no sig check). `edgeActionsStatusCode_s = 200`.

## Origin Result

```
HTTP 401 — {"error":{"code":"INVALID_TOKEN","message":"ERR_JWKS_MULTIPLE_MATCHING_KEYS"}}
```

The `jose` library attempts RS256 signature verification against all keys in the JWKS set. None match the fake signature. Origin returns 401.

## Verdict: PASS (CONDITIONAL) ✅

The defence-in-depth model holds even when the Edge Action cannot verify the signature. The origin is the authoritative security boundary.

## Critical security note

In the **teaching-only** path (`/edge-only` route with no origin auth), a tampered token with correct claims would grant access — because the origin trusts the forwarded `x-validated-claims` header and does not independently verify the JWT. This is why `/edge-only` is a teaching-only route that must **never** be used in production.

## My test (TENANT placeholder)

My test used "TENANT" placeholder in the ISS, causing ISS_FAIL at the EA (which correctly rejects). Evidence at 10:25:45: `EA_REJECT code=401 reason=ISS_FAIL got=https://login.microsoftonline.com/TENANT/v2.0`. This demonstrates ISS validation correctly — it is not a failed S6 test but a successful S5b test.

**No critical finding NIOBE-CRIT-001** — the system behaves correctly in all tested paths.

## References

- `app/server.js` — `requireJwt()` middleware using `jose.jwtVerify()`
- `edge-actions/ea-jwt-validate.js` — comment header: "⚠️ EA does NOT verify the JWT signature"
- `show-output/001-EdgeActionConsoleLog-30min.txt` — 10:31 EA_MODE=CLAIMS_ONLY entries
