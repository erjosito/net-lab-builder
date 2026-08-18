# afd-edge-actions-jwt-validation — Lessons Learned
Niobe · 2026-08-17/18

> Live entries added as evidence is collected. All entries from 2026-08-17/18 are confirmed by live lab evidence.

---

## Edge Actions runtime (confirmed by S1 probe)

### LL-001 — Hyperlight sandbox has no crypto or fetch APIs

**Finding:** `typeof crypto = undefined`, `typeof fetch = undefined`, `typeof atob = undefined` across all tested AFD PoPs. Results are deterministic.

**Impact:** RS256/JWKS signature verification is impossible inside an Edge Action as of 2026-08-17/18. Claims-only parsing is possible (JSON, Date, Uint8Array, Promise all available). Full JWT validation requires origin-side execution.

**Reuse:** Before writing any Edge Action JWT validation code, run the capability probe. Do not assume cryptographic APIs are available in any Hyperlight sandbox release. Check if `crypto.subtle` is available before implementing signature verification.

---

### LL-002 — Pure-JS base64url decode is required and works

**Finding:** `atob` unavailable. The lookup-table base64url decoder in `ea-jwt-validate.js` (lines 30–40) works correctly in the Hyperlight sandbox with `JSON.parse` and `String.fromCharCode`. Validated by successful JWT payload parsing in all test runs.

**Reuse:** Copy the `base64urlDecode()` function verbatim for any Edge Action that needs to read JWT claims. It has no dependencies on unavailable browser APIs.

---

### LL-003 — Edge Action response body is always AFD's HTML default page

**Finding:** When EA sets `event.response.response_code = 401` and returns, the client receives AFD's standard HTML 401 error page — not JSON. EA code cannot set the response body (not documented in `EdgeActionsSamples`).

**Impact:** APIs that return `{"error":{"code":"..."}}` JSON must set this body at the origin, not the EA. The EA is a gate, not a full HTTP response generator.

**Reuse:** If a JSON error body is required for 401/403 responses, ensure the origin produces it. Clients must tolerate HTML from AFD when EA rejects.

---

### LL-004 — `edgeActionsStatusCode_s = 200` means EA executed, not that client got 200

**Finding:** `edgeActionsStatusCode_s` in `FrontDoorAccessLog` is the EA *execution* status (`200` = ran to completion without timeout/exception; `503` = timed out or threw). A client-facing 401 still shows `edgeActionsStatusCode_s = 200`.

**Impact:** Do not use `edgeActionsStatusCode_s` to determine whether the client received a 2xx response. Use `EdgeActionConsoleLog` reason codes to understand EA decisions.

**Reuse:** For production monitoring: alert on `edgeActionsStatusCode_s = 503` (fail-open condition). For business logic monitoring: query `EdgeActionConsoleLog` reason codes.

---

### LL-005 — `EdgeActionConsoleLog` is a top-level LAW table, not AzureDiagnostics category

**Finding:** Querying `AzureDiagnostics | where Category == "EdgeActionConsoleLog"` returns a semantic error. The correct query is `EdgeActionConsoleLog | ...` (top-level table).

**Reuse:** For any LAW workspace with EA diagnostics, always query `EdgeActionConsoleLog` directly. The `EdgeActionServiceLog` table (platform events) is also top-level.

---

### LL-006 — `httpStatusCode_d = None` when EA rejects before origin

**Finding:** When an EA returns 401/403 and the origin is never called, `httpStatusCode_d` in `FrontDoorAccessLog` is `None`. The origin HTTP status code is absent because no origin call was made.

**Impact:** You cannot use `httpStatusCode_d` to distinguish between "EA rejected" and "origin returned 4xx" when EA is active. Use `EdgeActionConsoleLog` reason codes for EA decisions; `httpStatusCode_d` for origin-level status codes.

---

## Edge Actions deployment (confirmed by Tank / deploy-log.md)

### LL-007 — EA resource is RG-level with `global` location and `Standard/Standard` SKU

**Finding:** Initial assumptions were wrong on all three:
- Resource scope: NOT subscription-level → RG-level (`/resourceGroups/…/providers/Microsoft.Cdn/EdgeActions/{name}`)
- Location: NOT origin region → must be `global`
- SKU: NOT `Standard_AzureFrontDoor` → must be `Standard/Standard` (`{"name":"Standard","tier":"Standard"}`)
- Name: alphanumeric only, max 50 chars (no hyphens)

**Reuse:** All future Edge Action deployments must use these exact values. Document in any IaC template.

---

### LL-008 — `deployVersionCode` triggers async validation; `validationStatus=Succeeded` is premature

**Finding:** `validationStatus` appears as `Succeeded` in the GET response ~15 seconds after `deployVersionCode`. However, `addAttachment` (triggered by AFD rule PUT) fails with "default version not in successful state" until ~17 minutes have elapsed.

**Impact:** A deployment script that polls `validationStatus` and proceeds immediately will fail with a misleading error. Wait 17–20 minutes after `deployVersionCode` before creating the AFD rule that triggers attachment.

**Reuse:** Add a 17-minute sleep (with progress polling) between `deployVersionCode` and AFD rule PUT in any EA deployment script.

---

### LL-009 — `swapDefault` is broken; set `isDefaultVersion=true` at upload time

**Finding:** `POST .../versions/{v}/swapDefault` always returns 400 regardless of `validationStatus`. Cannot be used to change the active version.

**Workaround:** Set `isDefaultVersion: true` in the version PUT body at upload time. To change the active version, upload a new version with `isDefaultVersion: true`.

**Reuse:** Do not implement `swapDefault` in deployment automation. Design EA versioning around initial `isDefaultVersion` flag.

---

### LL-010 — `addAttachment` direct call creates dangling null attachments; use AFD rule PUT

**Finding:** Calling `addAttachment` action directly on an EA version creates a null attachment that cannot be removed (400 on removeAttachment). The attachment remains dangling and blocks EA deletion.

**Correct pattern:** Create an AFD rule set rule with `EdgeAction` action type. The rule PUT automatically triggers `addAttachment` correctly.

**Recovery:** Dangling attachment requires Azure Portal manual delete or Support ticket. Cannot be resolved via REST API alone.

---

### LL-011 — `az webapp config access-restriction add` blocks duplicate ServiceTag

**Finding:** The second `az webapp config access-restriction add --service-tag AzureFrontDoor.Backend` call fails because the CLI enforces uniqueness on ServiceTag. The manifest assumed two CLI calls would work.

**Workaround:** Use `az rest --method PATCH` against `/config/web?api-version=2023-12-01` to write the full `ipSecurityRestrictions` array directly. Deploy-Lab.ps1 implements this.

**Reuse:** Whenever two App Service access restriction rules share the same ServiceTag (health probe + FDID pattern), use ARM REST PATCH instead of CLI.

---

### LL-012 — AFD health probes do not carry X-Azure-FDID

**Finding:** AFD health probes carry `X-FD-HealthProbe: 1` but NOT `X-Azure-FDID`. A single combined FDID rule blocks health probes → AFD marks origin unhealthy.

**Required pattern:** Always use separate rules: rule 100 (health probe path: `AzureFrontDoor.Backend + X-FD-HealthProbe=1`) and rule 200 (FDID path: `AzureFrontDoor.Backend + X-Azure-FDID=<FDID>`).

**Reuse:** Document this two-rule pattern as a standard in any lab that uses App Service as an AFD origin.

---

## Security model (confirmed by S6/S8)

### LL-013 — Claims-only JWT parsing is not authentication; origin RS256 is the security boundary

**Finding:** In CONDITIONAL mode, the EA passes any structurally valid JWT with correct iss/aud/exp/roles regardless of signature validity. The origin (`jose` RS256/JWKS) correctly rejects fake-signed tokens with `ERR_JWKS_MULTIPLE_MATCHING_KEYS`.

**Principle:** Do not deploy claims-only EA validation in production without ensuring origin-side cryptographic validation. The EA provides defence-in-depth (early rejection of structurally invalid tokens, role pre-screening) but is NOT the authentication boundary.

---

### LL-014 — Entra token audience requires exact `api://` prefix

**Finding:** A token requested with scope `api://<app-id>/.default` has `aud = "api://<app-id>"`. A token requested with the bare GUID scope has `aud = "<app-id>"` (no prefix). The EA's exact string comparison `aud !== CONFIG.EXPECTED_AUD` fails the bare GUID token with `AUD_FAIL`.

**Reuse:** Always use `api://<app-id>/.default` as the scope. Document that the audience format is `api://` + app ID, not the bare GUID. Test with bare GUID to confirm rejection.

---

## Entra ID

### LL-015 — Application Administrator role required for admin consent; not granted to service principals by default

**Finding:** Admin consent for application permissions (not delegated) requires `Application Administrator` or `Global Administrator` in the Entra tenant. Running `az ad app permission admin-consent` as a non-admin fails with `Authorization_RequestDenied`.

**Impact:** Token acquisition fails until consent is granted. This is a deployment dependency that must be documented and coordinated with tenant administrators.

**Reuse:** Always document admin consent as a separate manual step in any lab using application permissions. Include the exact `az ad app permission admin-consent --id <client-app-id>` command in the deploy guide.

---

## Pre-deployment observations (2026-08-17, retained)

### DESIGN-001 — JWT sample absent from EdgeActionsSamples repo (active gap)
The `Azure/EdgeActionsSamples` repository lists JWT validation as supported but has no sample code as of 2026-08-17. S1 is the only authoritative source of truth.

### DESIGN-002 — Two-rule App Service access restriction is mandatory (C2)
Covered in LL-012.

### DESIGN-003 — X-Azure-FDID filtering is ARM-native, not application code (C1)
Confirmed: App Service access restrictions natively support HTTP header conditions including `X-Azure-FDID`. No middleware code required.

### DESIGN-004 — Edge Action response code contract is narrow (200/401/403 only)
Confirmed by `EdgeActionsSamples` README and design.md §6.1. No 302, 404, or 500 available.
