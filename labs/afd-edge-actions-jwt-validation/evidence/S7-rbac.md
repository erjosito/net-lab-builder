# S7 — Role-Based Authorization Evidence
Niobe · 2026-08-18

## S7a — No Lab.Admin role → /admin blocked (EA)

From Tank Run 3 / EA console log (2026-08-18T10:19 UTC):

Token payload: `{"iss":"<correct>","aud":"api://<APP_ID>","exp":<valid>,"roles":["Lab.User"]}`

EA log:
```
EA_MODE=CLAIMS_ONLY alg=RS256
EA_REJECT code=403 reason=ROLE_FAIL required=Lab.Admin
```

HTTP 403.

## S7b — Lab.User token → /protected succeeds (EA passes)

From the same EA log session:
```
EA_MODE=CLAIMS_ONLY alg=RS256
EA_ACCEPT path=/protected roles=["Lab.User"]
```

HTTP status at origin: 401 (origin also validates, and Lab.User token is fake-signed → origin rejects via RS256).

**Important distinction:**
- EA passes Lab.User token to `/protected` (role not required there by EA logic)
- Origin independently re-validates and rejects fake signature
- In production with valid Entra token: EA would pass → origin would allow (Lab.Admin not required for /protected)

## S7c — Real Entra token (BLOCKED by B1)

Testing real valid token with Lab.Admin absent requires admin consent. **PENDING — B1**.

Expected: `/admin` → 403 from EA; `/protected` → 200 from origin.

## Verdict
- S7a (no role → 403): PASS ✅
- S7b (role not required on /protected): PASS ✅
- S7c (real token split test): **PENDING (B1)** ⏸
