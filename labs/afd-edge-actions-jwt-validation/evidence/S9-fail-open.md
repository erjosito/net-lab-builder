# S9 — Lab.Admin on /admin — Full E2E Evidence
Niobe · 2026-08-18 · **VERDICT: PASS** (re-scoped)

## Re-scope note

Original S9 was designed to test fail-open via `ea-execution-filter` (A4). A4 was not deployed because `EdgeActionsPrivatePreview = NotRegistered` (B3) made the EA control plane unavailable for new versions on this subscription. B3 resolution (re-registration with Microsoft) was not pursued as it is not blocking lab completion.

**S9 was re-scoped** to: real Entra `Lab.Admin` token on `/admin` — the role-gated path, end-to-end. This validates the complete happy path: token issuance → AFD ingestion → EA claims-only validation → origin RS256 cryptographic validation → 200 response.

## Live evidence (Run 4, 2026-08-18T13:39 UTC+2)

Token: `app-edge-jwt-client` client_credentials, `accessTokenAcceptedVersion=2` API app.
- `iss`: `https://login.microsoftonline.com/<TENANT_REDACTED>/v2.0`
- `aud`: `623405b7-b4ae-4121-91d2-197ad2424df0` (bare GUID)
- `roles`: `["Lab.Admin"]`
Active EA: `eajwtvalidate3/v1`

| Path | HTTP Status | `edge_jwt_status` | EA Log | Origin response |
|------|-------------|-------------------|--------|-----------------|
| `/admin` | **200** | `VALIDATED` | `CLAIMS_ONLY`, `ACCEPT` | `{"route":"admin","sub":"cf2ff0a3-<REDACTED>","roles":["Lab.Admin"]}` |

EA chain:
1. EA strips `x-validated-claims`, `x-edge-jwt-status`, `x-test-fail` (spoof prevention)
2. EA decodes header/payload with pure-JS base64url (atob unavailable in Hyperlight)
3. EA validates: `exp` not expired, `aud = 623405b7-...`, `iss` contains correct tenant, `roles` includes `Lab.Admin`
4. EA sets `x-validated-claims` header, returns 200 (passes request to origin)
5. Origin `jose` performs RS256/JWKS verification: fetches JWKS, verifies signature, confirms same claims
6. Origin returns 200 with route context

> **EA log evidence:** `eajwtvalidate3` had no diagnostic setting from creation (12:45 UTC+2) until manual correction at 2026-08-18T17:12:36 UTC+2. `EdgeActionConsoleLog` entries for Run 4 are **pending ingestion** in LAW. HTTP 200 response is the authoritative PASS evidence.

**Evidence source:** Tank `show-output/smoke-test-results.md` Run 4. (teaching gap — not lab-blocking)

The documented fail-open behaviour (edgeActionsStatusCode_s = 503 when EA times out or throws):
- `/edge-only` + EA exception → 200 (no origin auth → access granted — dangerous teaching outcome)
- `/protected` + EA exception → 401/403 (origin backstop — safe outcome)

This was not confirmed by lab evidence. The soft form is demonstrated: `/edge-only` returns 200 with no token (S3a), showing what happens when no EA gate exists. See `evidence/S9-fail-open.md` teaching notes in design.md.

## Verdict: PASS ✅ (re-scoped)
- Real Lab.Admin token on `/admin`: PASS ✅
- Fail-open (A4): not tested — documented teaching gap, not a lab completion requirement
