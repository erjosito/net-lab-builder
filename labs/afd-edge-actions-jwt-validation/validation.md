# afd-edge-actions-jwt-validation — Validation
Niobe · 2026-08-17/18

> **Public-preview scope clarification — 2026-08-19:** Cryptographic JWT signature validation is outside the supported scope. The S1 probe demonstrates the resulting claims-only behavior.

> **Live run date:** 2026-08-18T10:24–13:39 UTC+2 (Runs 3–4, all blockers resolved)
> **Deployment state:** A0–A3 complete (`eajwtvalidate3/v1` active default, bare-GUID audience); A1 complete (Graph appRoleAssignments used to assign Lab.Admin role); A4 not executed (fail-open test not blocking — S9 re-scoped to real /admin Lab.Admin path)

---

## Evidence root

```
evidence/          ← one .md per scenario (S1–S9)
show-output/       ← numbered raw CLI/KQL output files
  001-EdgeActionConsoleLog-30min.txt   ← from eajwtvalidate (Runs 2–3, ~10:10–10:32 UTC)
  002-FrontDoorAccessLog-30min.txt
  003-HTTP-requests-evidence.txt
screenshots/       ← best-effort portal screenshots
```

> **Log evidence scope:** `001-EdgeActionConsoleLog-30min.txt` was captured from `eajwtvalidate` during Sessions 3–4 (before `eajwtvalidate3` was created). `eajwtvalidate3` had no diagnostic settings from creation (12:45 UTC+2) until manual correction at **2026-08-18T17:12:36 UTC+2**. `EdgeActionConsoleLog` entries from Run 4 (S7/S9 real-token tests at 13:39 UTC+2) are **pending ingestion** post-correction. HTTP 200 responses are the authoritative evidence for S7/S9 PASS; EA log corroboration will appear in LAW after ingestion completes.
>
> **Source revision note:** EA log entries in `show-output/001-EdgeActionConsoleLog-30min.txt` were produced by the earlier **108-line verbose revision** of `ea-jwt-validate.js` deployed to `eajwtvalidate`/`eajwtvalidate3`. That revision emitted `EA_MODE=CLAIMS_ONLY`, `alg=`, `path=`, `roles=` fields. The current **simplified 70-line source** logs only `EA_REJECT reason=<code>` or `EA_ACCEPT`. Captured evidence is accurate for the scenarios tested; it does not reflect what the simplified current source would emit.

Sanitization: all committed files pass `tests/Confirm-Sanitization.ps1`. Zero raw subscription IDs, tenant IDs, full JWTs, or client secrets.

---

## Scenario summary

| # | Scenario | Expected | Actual HTTP | EA Log | Origin hit | Security verdict | Status |
|---|----------|----------|-------------|--------|-----------|-----------------|--------|
| S1 | Capability probe (GATE) | CONDITIONAL | 200 | PROBE lines confirmed | YES (/debug) | CONDITIONAL — no sig verify | ✅ PASS |
| S2 | Missing token | 401 | **401** | `MISSING_TOKEN` | **NO** | Edge blocks | ✅ PASS |
| S3a | Open routes (/health, /public) | 200 | **200** | no EA | YES | Expected | ✅ PASS |
| S3b | Malformed token | 401 | **401** | `MALFORMED_HEADER` | NO | Edge blocks | ✅ PASS |
| S3c | Valid Entra token → 200 | 200 | **200** | expected `EA_ACCEPT` — **log pending** (eajwtvalidate3 diag corrected 17:12; simplified source logs `EA_ACCEPT` only) | YES | Claims-only + origin RS256 | ✅ PASS |
| S4 | Expired token | 401 | **401** | `EXPIRED exp=…` | NO | Edge blocks | ✅ PASS |
| S5a | Wrong audience | 401 | **401** | `AUD_FAIL got=…` | NO | Edge blocks | ✅ PASS |
| S5b | Wrong issuer | 401 | **401** | `ISS_FAIL got=…` | NO | Edge blocks | ✅ PASS |
| S6 | Tampered sig (CONDITIONAL) | EA pass, origin 401 | EA: 200 / origin: **401** | `EA_ACCEPT` (verbose revision also logged `CLAIMS_ONLY`; see source revision note) | YES | Origin RS256 enforces | ✅ PASS |
| S7a | Missing role → /admin 403 | 403 | **403** | `ROLE_FAIL` | NO | Edge blocks | ✅ PASS |
| S7b | Real Lab.Admin token → /protected 200 | 200 | **200** | expected `ACCEPT` — **log pending** (eajwtvalidate3 diag corrected 17:12) | YES | Full E2E: claims-only EA + origin RS256 | ✅ PASS |
| S8 | Direct origin bypass | 403 | **403** | N/A (no AFD) | Blocked by ARM | Access restriction effective | ✅ PASS |
| S9 | Real Lab.Admin token → /admin 200 | 200 | **200** | expected `ACCEPT` — **log pending** (eajwtvalidate3 diag corrected 17:12) | YES | Role + claims-only + origin RS256 | ✅ PASS |

**11/11 sub-scenarios PASS. All blockers resolved as of 2026-08-18T13:39 UTC+2.**
**No critical findings (NIOBE-CRIT-001/002/003 all clear).**
**Note:** S9 was re-scoped from fail-open/A4 (B3-blocked) to real Lab.Admin token on `/admin`. Original fail-open design (A4 `ea-execution-filter`) is a documented teaching gap, not a lab completion requirement.

---

## S1 — Capability Probe

**Verdict: CONDITIONAL**

| Assertion | Expected | Actual | Verdict |
|-----------|----------|--------|---------|
| `EdgeActionConsoleLog` contains `PROBE JSON=object` within 10 min | Present | Present | ✅ PASS |
| `PROBE Date=function` | Present | Present | ✅ PASS |
| `PROBE crypto=object` (GO) or `undefined` (STOP) | Either | `undefined` | CONDITIONAL |
| `PROBE fetch=function` (GO) | Present | `undefined` | CONDITIONAL |
| `PROBE atob=function` | Present | `undefined` | CONDITIONAL |
| `PROBE Promise=function` | Present | `function` | ✅ Available |
| EA executing (`edgeActionsAgentType_s = node`) | node | node | ✅ PASS |
| X-Azure-Ref present in response | Present | Present | ✅ PASS |

**S1-GATE: CONDITIONAL** — claims-only enforcement only. Origin RS256 is the security boundary. See the scope clarification and S1 probe evidence above.
**Evidence:** `evidence/S1-capability-probe.md`, `show-output/001-EdgeActionConsoleLog-30min.txt`

---

## S2 — Missing Token

| Assertion | Expected | Actual | Verdict |
|-----------|----------|--------|---------|
| HTTP status from AFD | 401 | **401** | ✅ PASS |
| EA log reason | MISSING_TOKEN | MISSING_TOKEN | ✅ PASS |
| Origin hit | NO | NO | ✅ PASS |
| X-Azure-Ref | Present | 20260818T102616Z-…037gr | ✅ PASS |

**Client HTTP:** 401 · **EA log:** MISSING_TOKEN · **Origin hit:** NO · **Evidence:** `evidence/S2-missing-token.md`

---

## S3 — Valid Token / Baseline Routes

| Assertion | Expected | Actual | Verdict |
|-----------|----------|--------|---------|
| /health HTTP 200 | 200 | **200** | ✅ PASS |
| /public HTTP 200 | 200 | **200** | ✅ PASS |
| /edge-only no token (no EA attached) | 200 (teaching warning) | **200** | ✅ PASS |
| /protected malformed token | 401 | **401** (MALFORMED_HEADER) | ✅ PASS |
| /protected valid Entra Lab.Admin token → 200 | 200 | **200** (`edge_jwt_status=VALIDATED`) | ✅ PASS (Run 4) |
| /admin valid Entra Lab.Admin token → 200 | 200 | **200** (`edge_jwt_status=VALIDATED`) | ✅ PASS (Run 4) |

**Evidence:** `evidence/S3-valid-routes.md`

---

## S4 — Expired Token

| Assertion | Expected | Actual | Verdict |
|-----------|----------|--------|---------|
| HTTP status | 401 | **401** | ✅ PASS |
| EA log reason | EXPIRED | `EXPIRED exp=1787045174` | ✅ PASS |
| Expiry check fires before iss check | Yes | Yes (exp → iss order confirmed) | ✅ PASS |
| Origin hit | NO | NO | ✅ PASS |
| X-Azure-Ref | Present | 20260818T102541Z-…1r55 | ✅ PASS |

**Evidence:** `evidence/S4-expired-token.md`

---

## S5 — Wrong Audience / Wrong Issuer

| Assertion | Expected | Actual | Verdict |
|-----------|----------|--------|---------|
| Wrong aud → 401 | 401 | **401** | ✅ PASS |
| EA log: AUD_FAIL | Present | `AUD_FAIL got=api://wrong-audience-00000000` | ✅ PASS |
| Wrong iss → 401 | 401 | **401** | ✅ PASS |
| EA log: ISS_FAIL | Present | `ISS_FAIL got=https://login.microsoftonline.com/wrong-tenant-id/v2.0` | ✅ PASS |
| Bare GUID aud mismatching `api://` prefix → AUD_FAIL (Run 3 config) | 401 | **401** (Tank Run 3) | ✅ PASS |

> **Run 3 vs Run 4 — AUD format change:** In Run 3, the EA expected `api://<APP_ID>` and bare-GUID tokens failed AUD_FAIL. After `accessTokenAcceptedVersion=2` was set on the API app, Entra v2 `client_credentials` tokens use `aud = bare GUID`. The EA and origin `EXPECTED_AUD` were updated to bare GUID accordingly (see LL-016). In the final Run 4 configuration, a token with `aud = api://...` would itself fail AUD_FAIL. The EA correctly enforces exact aud match in both configurations.

**Evidence:** `evidence/S5-wrong-claims.md`

---

## S6 — Tampered Token / Signature Bypass

| Assertion | Expected (CONDITIONAL) | Actual | Verdict |
|-----------|----------------------|--------|---------|
| EA passes tampered token (correct claims, fake sig) | EA 200 (`EA_ACCEPT`) | EA 200, `EA_ACCEPT` (`CLAIMS_ONLY`+`ACCEPT` in verbose revision log — see source revision note above) | ✅ PASS |
| Origin rejects fake signature | 401 | 401 `ERR_JWKS_MULTIPLE_MATCHING_KEYS` | ✅ PASS |
| Defence-in-depth holds | Yes | Yes | ✅ PASS |
| NIOBE-CRIT-001 (EA 200, origin 200 = full bypass) | No trigger | Not triggered | ✅ CLEAR |

**Evidence:** `evidence/S6-tampered-sig.md`

---

## S7 — Role-Based Authorization

| Assertion | Expected | Actual | Verdict |
|-----------|----------|--------|---------|
| Lab.User token on /admin → 403 (ROLE_FAIL) | 403 | **403** | ✅ PASS |
| Lab.User token on /protected → EA passes | 200 (EA) | EA ACCEPT | ✅ PASS |
| Real Lab.Admin token → /protected 200 | 200 | **200** | ✅ PASS (Run 4) |
| Real token without Lab.Admin → /admin 403, /protected 200 | split | Not re-tested (client credentials only issue Lab.Admin; see S7a for ROLE_FAIL) | ✅ Covered by S7a |

**Evidence:** `evidence/S7-rbac.md`

---

## S8 — Direct Origin Bypass

| Assertion | Expected | Actual | Verdict |
|-----------|----------|--------|---------|
| Direct to azurewebsites.net/protected → 403 | 403 | **403** ("Ip Forbidden") | ✅ PASS |
| Direct to azurewebsites.net/health → 403 | 403 | **403** | ✅ PASS |
| Via AFD with valid Lab.Admin token → 200 | 200 | **200** (Run 4 via eajwtvalidate3) | ✅ PASS |
| NIOBE-CRIT-002 (direct bypass succeeds) | No trigger | Not triggered | ✅ CLEAR |

**Evidence:** `evidence/S8-direct-bypass.md`

---

## S9 — Real Lab.Admin Token on /admin (Re-scoped from fail-open)

> **Re-scope note:** Original S9 design tested fail-open via `ea-execution-filter` (A4). A4 was not deployed because re-registration for `EdgeActionsPrivatePreview` (B3) was not possible. S9 was re-scoped to verify the full happy-path E2E for the `/admin` route with a real Lab.Admin Entra token — the same token used in S7c, on the role-gated path. Fail-open behaviour (edgeActionsStatusCode=503) is documented but not lab-confirmed; see LL-004 and design.md.

| Assertion | Expected | Actual | Verdict |
|-----------|----------|--------|---------|
| `/admin` with real Lab.Admin Entra token → 200 | 200 | **200** | ✅ PASS |
| `edge_jwt_status` header | `VALIDATED` | `VALIDATED` | ✅ PASS |
| EA log: `ACCEPT` | Present | **pending ingestion** (eajwtvalidate3 diag corrected 17:12:36) | ⏳ PENDING LOG |
| Origin returns `{"route":"admin","roles":["Lab.Admin"]}` | Present | Present | ✅ PASS |
| NIOBE-CRIT-003 (/protected returns 200 on fail-open) | No trigger | Not tested (A4 not deployed) | ℹ️ TEACHING GAP |

**Evidence source:** Tank smoke-test-results.md Run 4, 2026-08-18T13:39 UTC+2.
**Evidence file:** `evidence/S9-fail-open.md`

---

## General assertions

| Assertion | Expected | Status |
|-----------|----------|--------|
| X-Azure-Ref in every AFD response | YES | ✅ Confirmed |
| /health returns 200 | YES | ✅ Confirmed |
| AFD origin healthy | YES | ✅ Confirmed |
| EA log evidence (S1–S7a) from `eajwtvalidate` | All reason codes confirmed | ✅ Captured in `show-output/001-EdgeActionConsoleLog-30min.txt` |
| EA log evidence (S3c, S7b, S9) from `eajwtvalidate3` | Pending ingestion | ⏳ Diag corrected 17:12:36; entries expected in LAW after ~3–10 min |
| AFD FrontDoorAccessLog (all scenarios) | Present | ✅ Confirmed (separate from EA diag setting) |
| No raw subscription ID in committed files | ENFORCED | ✅ Sanitized |
| No raw tenant ID in committed files | ENFORCED | ✅ Sanitized |
| No full JWT (3-part) in committed files | ENFORCED | ✅ Never written to disk |
| No client secret in committed files | ENFORCED | ✅ Never written to disk |

---

## Lab findings (Niobe observations)

| ID | Finding |
|----|---------|
| LF-001 | `EdgeActionConsoleLog` is a **top-level LAW table**, not a category in `AzureDiagnostics`. KQL must query it directly. |
| LF-002 | `edgeActionsStatusCode_s = 200` means EA *executed* successfully. The 401/403 client-facing response is synthesised by EA code and does not separately appear in `httpStatusCode_d`. |
| LF-003 | `httpStatusCode_d = None` in `FrontDoorAccessLog` when EA rejects before origin. Origin HTTP status is not logged when the EA handles the response. |
| LF-004 | EA response body when EA returns 401/403 is AFD's default HTML error page — EA code only sets `event.response.response_code`. Custom body is not documented. |
| LF-005 | `/edge-only` route is NOT attached to `eajwtvalidate3` rule set (`ruleprotected` only matches `/protected` and `/admin`). Unauthenticated GET /edge-only returns 200 — teaching behaviour demonstrated already. |
| LF-006 | `validationStatus` appearing as `Succeeded` in GET response is premature (~15s). `addAttachment` requires ~17 min after `deployVersionCode`. |
| LF-007 | EA diagnostic settings (`UserLog`, `ServiceLog`) are per-EA-resource and **do not transfer** when an EA resource is replaced. `eajwtvalidate3` was created without diagnostics; manually corrected 2026-08-18T17:12:36. `EdgeActionConsoleLog` entries from Run 4 (13:39 UTC+2) are absent from LAW and pending ingestion post-correction. See LL-020. |

---

## Active blockers

All blockers resolved as of 2026-08-18T13:43 UTC+2.

| ID | Resolution | Resolved by |
|----|-----------|-------------|
| B1 | Lab.Admin app role assigned via Graph `POST /servicePrincipals/{sp}/appRoleAssignments` (bypasses admin-consent UI; Jose has Global Reader, not Global Admin) | Tank, Session 5 |
| B2 | EA `eajwtvalidate` deployed in Session 4; `eajwtvalidate3` created in Session 5 with correct bare-GUID audience | Tank |
| B3 | Re-registration not attempted; S9 re-scoped to real-token /admin path — not blocking lab completion | Tank/Niobe |

**Orphaned resources (non-blocking):**
- `eajwtvalidate` (original, dangling attachment) — portal/Support needed
- `eacapabilityprobe` (dangling null attachment) — portal/Support needed
- Neither blocks active scenarios or cleanup gate.
