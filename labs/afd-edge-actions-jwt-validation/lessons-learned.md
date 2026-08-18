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

### LL-014 — Entra v2 `client_credentials` token audience depends on `accessTokenAcceptedVersion`

**Finding:** Initial assumption was that the token `aud` would be `api://<app-id>` (matching the Application ID URI). This is incorrect for v2 tokens.

- `accessTokenAcceptedVersion = null` (v1, default): `aud = api://<app-id>` (or the full identifier URI)
- `accessTokenAcceptedVersion = 2` (v2): `aud = <app-id>` (bare GUID, regardless of identifier URI)

In Run 3, the EA expected `api://` prefix and bare-GUID tokens failed AUD_FAIL — that was correct for the v1 configuration. After `PATCH /applications/{id}` set `accessTokenAcceptedVersion=2`, Entra issued `aud = bare GUID`. EA and origin `EXPECTED_AUD` were updated accordingly.

**Reuse:** Before configuring EA/origin audience checks:
1. Determine `accessTokenAcceptedVersion` on the API app (`az ad app show --id ... | jq .accessTokenAcceptedVersion`)
2. If `null` or `1`: expect `api://<app-id>` in token `aud`
3. If `2`: expect bare GUID in token `aud`
4. Test with a real token from your tenant — do not assume from scope alone.

---

## Entra ID

### LL-015 — Application Administrator role required for admin consent; Graph `appRoleAssignments` API is a viable alternative

**Finding (original B1 part):** `az ad app permission admin-consent` requires `Application Administrator` or `Global Administrator`. It fails with `Authorization_RequestDenied` for accounts with `Global Reader` only.

**Lab resolution:** Rather than waiting for tenant admin, Tank used the Microsoft Graph API directly:
```
POST /v1.0/servicePrincipals/{clientSpId}/appRoleAssignments
Body: { principalId, resourceId, appRoleId }
```
This assigns the application role to the client service principal without the admin-consent UI flow. It requires the calling identity to have permission to write `appRoleAssignments` on the target SP — in this lab, the deploying identity had sufficient Graph API access.

**Reuse:** In labs where the deploying identity cannot run admin-consent, use Graph `appRoleAssignments` directly. Document both paths in deployment guides. Note that the Graph approach requires knowing the `appRoleId` (GUID from the API app manifest's `appRoles` array).

---

## Session 5 findings (2026-08-18 — live token validation, all scenarios PASS)

### LL-016 — `accessTokenAcceptedVersion=2` changes token issuer format too

**Finding:** Setting `accessTokenAcceptedVersion=2` on the API app's manifest changes both:
- `aud`: bare GUID (not `api://appId`) — covered in LL-014
- `iss`: `https://login.microsoftonline.com/<tenant>/v2.0` (v2.0 suffix added) — previously `https://login.microsoftonline.com/<tenant>/`

Both the EA and origin must be updated when switching between v1 and v2 token acceptance. In this lab, the EA expected `...v2.0` in the issuer string match (confirmed by ISS_FAIL on wrong-tenant tests in S5 where the expected pattern includes `v2.0`).

**Reuse:** When debugging AUD_FAIL or ISS_FAIL after changing `accessTokenAcceptedVersion`, decode a real token and compare all claim values directly against the EA/origin expected values.

---

### LL-017 — F1 App Service Plan has a daily CPU quota; upgrade to B1 for sustained lab use

**Finding:** The App Service running on F1 Free tier stopped mid-session due to daily CPU quota exhaustion (`az appservice plan update --sku B1` required). The site returned 503 during this period.

**Impact:** F1 is not viable for any lab that does sustained testing across a full day. The token-acquisition retries and debug calls alone can exhaust the F1 quota.

**Reuse:** For any lab with AFD + App Service that requires more than ~10 minutes of sustained HTTP testing, deploy with B1 or higher from the start. The cost difference is negligible at lab scale (~$0.05/day).

---

### LL-018 — `swapDefault` failure requires a new EA resource, not just a new version

**Finding:** LL-009 documents that `swapDefault` is broken (always 400). The additional finding from Session 5 is that the "upload a new version with `isDefaultVersion=true`" workaround is also blocked when the original EA resource has a version stuck in `Provisioning` state (non-default versions can get stuck and block the PUT that would set a different default).

**Workaround (confirmed):** Create a **new EA resource** (`eajwtvalidate3`) with the correct code from scratch, set `isDefaultVersion=true` at upload. Update the AFD rule to reference the new EA resource. The old EA (`eajwtvalidate`) becomes orphaned.

**Reuse:** When a swapDefault-like operation fails, plan for a new EA resource + AFD rule update. Old EA resources with dangling attachments require portal/Support for cleanup.

---

### LL-019 — Entra credential replication lag after `az ad app credential reset`

**Finding:** After resetting the client app credential, token acquisition immediately fails with `AADSTS7000215` (invalid client secret). The credential becomes valid after ~40 seconds of replication lag.

**Reuse:** When scripting credential rotation, add at least a 60-second wait (with retry logic) between `az ad app credential reset` and the first token acquisition attempt.

---

### LL-020 — EA diagnostic settings do not transfer when an EA resource is replaced

**Finding:** When `eajwtvalidate3` was created to replace the broken `eajwtvalidate` EA, no diagnostic settings were applied to the new resource. The `diag-eajwtvalidate` setting remained attached to the orphaned `eajwtvalidate` only. `EdgeActionConsoleLog` and `EdgeActionServiceLog` were not routed to LAW from `eajwtvalidate3` during Run 4 (13:39 UTC+2). The gap was discovered and manually corrected at **2026-08-18T17:12:36 UTC+2** by Jose.

**Why this happens:** Azure Monitor diagnostic settings are properties of the specific resource instance, not the resource type or namespace. Creating a new EA resource (`eajwtvalidate3`) starts with no diagnostic settings, regardless of what the previous resource (`eajwtvalidate`) had configured.

**Impact:** Any EA console log statements (`console.log(...)`) written during the gap period will never appear in LAW — they are lost, not buffered. HTTP-level evidence (response codes) is unaffected.

**The two separate diagnostic settings required for full EA observability:**
1. **EA resource** → `UserLog` + `ServiceLog` → LAW: required for `EdgeActionConsoleLog` (your `console.log()` output) and `EdgeActionServiceLog` (platform events). **Must be re-applied to every new EA resource.**
2. **AFD profile** → `FrontDoorAccessLog` → LAW: required for `edgeActionsStatusCode_s`, `edgeActionsAgentType_s` per-request fields. **Persists independently of EA resource changes.**

**Reuse:** After any EA resource replacement (whether due to broken swapDefault or code changes), immediately run the `addEaDiagnostics` step from `Deploy-Lab.ps1` against the new resource name. Add this as a required post-replacement checklist item. Include in deployment runbook: "When creating a replacement EA resource, apply diagnostic settings before running any validation tests."



### DESIGN-001 — JWT sample absent from EdgeActionsSamples repo (active gap)
The `Azure/EdgeActionsSamples` repository lists JWT validation as supported but has no sample code as of 2026-08-17. S1 is the only authoritative source of truth.

### DESIGN-002 — Two-rule App Service access restriction is mandatory (C2)
Covered in LL-012.

### DESIGN-003 — X-Azure-FDID filtering is ARM-native, not application code (C1)
Confirmed: App Service access restrictions natively support HTTP header conditions including `X-Azure-FDID`. No middleware code required.

### DESIGN-004 — Edge Action response code contract is narrow (200/401/403 only)
Confirmed by `EdgeActionsSamples` README and design.md §6.1. No 302, 404, or 500 available.
