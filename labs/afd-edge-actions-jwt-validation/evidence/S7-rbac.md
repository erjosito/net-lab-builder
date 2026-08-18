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

## S7c — Real Entra Token (PASS — Run 4, 2026-08-18T13:39 UTC+2)

Token: `app-edge-jwt-client` client_credentials, `aud = 623405b7-b4ae-4121-91d2-197ad2424df0` (bare GUID), `roles=["Lab.Admin"]`.
Active EA: `eajwtvalidate3/v1` (bare-GUID `EXPECTED_AUD`, `accessTokenAcceptedVersion=2`).

| Path | HTTP Status | `edge_jwt_status` | EA Log | Origin |
|------|-------------|-------------------|--------|--------|
| `/protected` | **200** | `VALIDATED` | `CLAIMS_ONLY`, `ACCEPT` | `{"route":"protected","sub":"cf2ff0a3-<REDACTED>","roles":["Lab.Admin"]}` |
| `/admin` | **200** | `VALIDATED` | `CLAIMS_ONLY`, `ACCEPT` | `{"route":"admin","sub":"cf2ff0a3-<REDACTED>","roles":["Lab.Admin"]}` |

Full E2E confirmed: client → AFD → EA (claims-only accept) → origin (jose RS256 PASS) → 200.

> **AUD note:** Entra v2 `client_credentials` with `accessTokenAcceptedVersion=2` issues tokens with `aud = bare GUID` (not `api://appId`). EA and origin updated accordingly. A token with `aud = api://...` would now fail AUD_FAIL. See LL-016.

**Evidence source:** Tank `show-output/smoke-test-results.md` Run 4.

## Verdict
- S7a (no role → 403): PASS ✅
- S7b (Lab.User on /protected, EA accepts): PASS ✅
- S7c (real Lab.Admin token, full E2E): PASS ✅ (Run 4, 2026-08-18T13:39 UTC+2)
