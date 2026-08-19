# afd-edge-actions-jwt-validation — Deployment Manifest
Morpheus · 2026-08-17 · **Phase 4 authorised — deployment-ready**

References:
- [Azure Front Door Edge Actions (official docs)](https://learn.microsoft.com/azure/frontdoor/edge-actions)
- [EdgeActionsSamples (GitHub)](https://github.com/Azure/EdgeActionsSamples)
  - No JWT sample exists in the public repo as of 2026-08-17. Capability probe (S1) is the
    authoritative lab evidence source. See §Confirmed scope boundary.

---

## ⚠️ Confirmed scope boundary (2026-08-19)

Scope clarification (2026-08-19): cryptographic JWT signature validation is outside
the supported scope of Edge Actions public preview. Use origin or gateway validation for all
cryptographic JWT verification.

Lab evidence (S1 probe, 2026-08-17/18): `crypto=undefined`, `fetch=undefined`, `atob=undefined`
in the Edge Action sandbox. Claims-only JWT parsing is the maximum supported EA JWT behaviour in
this release. The origin is the mandatory cryptographic enforcement point.

---

## 1. Objective

Determine whether Azure Front Door Edge Actions v1 can perform cryptographically sound
JWT validation (JWKS fetch, RS256/ES256 signature verify, claim assertions) at the edge,
and document the precise API surface and failure behaviour. Produce evidence covering nine
scenarios under the recommended pre-validation + origin-revalidation architecture.

---

## 2. Designs Studied

### ✅ Recommended: Edge pre-validation + origin revalidation (defence in depth)

Edge Action intercepts every request, performs **claims-only** JWT parsing (the maximum supported EA JWT behaviour in public preview — scope boundary confirmed 2026-08-19), and rejects missing/malformed/expired/wrong-audience/wrong-issuer tokens at the edge. The origin **also validates the token independently** with full RS256 signature verification (`jose` library). Even if the Edge Action fails open (execution timeout, exception), the origin refuses invalid or unsigned requests. This is the only design that is safe in production.

**Confirmed scope boundary (2026-08-19):** Cryptographic JWT
signature validation is outside the supported scope of Edge Actions public preview. Claims-only
parsing is the maximum supported EA JWT behaviour. Full JWKS-fetch + RS256 verification inside an
Edge Action is not within the supported scope of public preview. Origin-side cryptographic
validation is mandatory, not optional defence-in-depth.

**Evidence target:** S2–S9 all exercised against this architecture. S6 (tampered signature) demonstrates the claims-only gap: EA passes, origin rejects.

---

### 📖 Teaching-only: Edge Action as sole enforcement

Edge Action is the **only** enforcement point; the origin has no auth check (or blindly
trusts the `X-Validated-Claims` header injected by the Edge Action). Illustrates the
failure mode when the Edge Action fails open or is bypassed by a direct-origin call.

**Why teaching-only:** Direct origin bypass (S8) trivially defeats this model. The origin
is reachable on its public `.azurewebsites.net` hostname; only AFD service tag + FDID
validation can restrict traffic, but those do not authenticate the bearer. This design
should **never** be used in production.

**Evidence target:** S8 (direct origin bypass) explicitly demonstrates the gap.

---

### 🔬 Control: Origin-only validation or public endpoint route

The `/public` route carries no auth at all (baseline). The `/protected` and `/admin`
routes fall back to origin-only validation when S1-GATE is STOP (crypto APIs absent).
This is the fallback design if Edge Actions cannot perform signature verification.

**Evidence target:** S1 (capability probe) determines which control path applies.

---

## 3. Regions

| Role | Region |
|------|--------|
| AFD profile (endpoint/route/origin group) | Global |
| App Service (origin) | **swedencentral** |
| Log Analytics workspace | swedencentral |
| Entra ID tenant | Tenant home directory (global) |

No VNet, no VPN gateway, no private endpoint. Phase 0 VM SKU/capacity preflight is **inapplicable** — this lab has no VMs.

---

## 4. Resource Inventory

### 4.1 Resource Group

| Name | Region | Tags |
|------|--------|------|
| `rg-afd-edge-jwt-lab` | swedencentral | lab=afd-edge-actions-jwt-validation, env=lab, owner=jose |

---

### 4.2 Log Analytics Workspace

| Name | SKU | Retention |
|------|-----|-----------|
| `law-edge-jwt-lab` | PerGB2018 | 30 days |

Diagnostic settings send `FrontDoorAccessLog`, `FrontDoorWebApplicationFirewallLog`, and
`FrontDoorHealthProbeLog` plus `EdgeActionConsoleLog` to this workspace.

---

### 4.3 Azure Front Door

| Resource | Value |
|----------|-------|
| Profile name | `afd-edge-jwt-lab` |
| SKU | **Standard** (WAF-capable, supports Edge Actions) |
| Endpoint | `edge-jwt-lab-<hash>.azurefd.net` (system-generated) |
| Origin group | `og-appservice` |
| Origin | `app-edge-jwt-lab.azurewebsites.net` |
| Origin protocol | HTTPS only |
| Health probe | HTTPS GET `/health`, 30 s interval |
| Route | `rt-api` — `/*` → og-appservice, HTTPS redirect enabled |

**Edge Actions (three versions; conditional on S1-GATE):**

| Action name | Purpose | Trigger |
|-------------|---------|---------|
| `ea-capability-probe` | Print available global APIs to console log | All requests to `/debug/*` |
| `ea-jwt-validate` | Claims-only JWT parsing (CONDITIONAL mode — confirmed maximum supported in public preview) | All requests to `/protected`, `/admin`, `/edge-only` |
| `ea-execution-filter` | Controlled timeout / deliberate exception — tests fail-open | Requests with header `X-Test-Fail: 1` |

> **Confirmed scope boundary (2026-08-19):** Cryptographic JWT
> signature validation is outside the supported scope of Edge Actions public preview. Lab evidence
> (S1 probe, 2026-08-17/18): `crypto=undefined`, `fetch=undefined`, `atob=undefined`. Claims-only
> JWT parsing is the maximum supported EA JWT behaviour in this release.

---

### 4.4 App Service

| Name | SKU | OS | Region |
|------|-----|----|--------|
| `app-edge-jwt-lab` | **B1** (or Free F1 if quota allows) | Linux (Node 20 or Python 3.12) | swedencentral |

**Routes exposed:**

| Path | Auth | Description |
|------|------|-------------|
| `GET /health` | None | AFD health probe; always 200 |
| `GET /public` | None | No token required; baseline scenario |
| `GET /edge-only` | Edge validates; origin trusts header | Teaching-only scenario (S8 bypass target) |
| `GET /protected` | Edge + origin validate | Defence-in-depth scenario |
| `GET /admin` | Edge + origin validate; role `Lab.Admin` required | RBAC scenario (S7) |
| `GET /debug/request` | None (should be AFD-restricted) | Echo all request headers; used for S1 probe and S8 bypass evidence |

**Origin hardening (authoritative — ARM-native, no application code required):**
1. **App Service Access Restrictions — Rule 100 (health probes):** Allow `AzureFrontDoor.Backend`
   service tag + `X-FD-HealthProbe: 1` header. AFD health probes carry this header but **not**
   `X-Azure-FDID`; a combined FDID rule would block probes.
2. **App Service Access Restrictions — Rule 200 (AFD traffic):** Allow `AzureFrontDoor.Backend`
   service tag + `X-Azure-FDID: <FDID>` header. Both conditions must be true.
3. **Implicit deny-all** (effective once ≥1 allow rule is present).

> **Design correction (Trinity 2026-08-17):** `X-Azure-FDID` header filtering is natively
> supported in App Service access restrictions (`--http-header` on `az webapp config
> access-restriction add`). This is a platform capability — no application code or
> middleware is required. Authority: [App Service access restrictions — Filter by HTTP
> header](https://learn.microsoft.com/azure/app-service/app-service-ip-restrictions#filter-by-http-header)
> and [Secure traffic to origins — App Service tab](https://learn.microsoft.com/azure/frontdoor/origin-security).
> The original claim "X-Azure-FDID validation is performed in application code (not
> ARM-native)" is **incorrect**. App-layer FDID checks are optional defence-in-depth.

> See `design.md §0` and `design.md §2` for exact CLI commands.

---

### 4.5 Entra ID — Two App Registrations

#### Resource / API registration (`app-edge-jwt-api`)

| Property | Value |
|----------|-------|
| Display name | `app-edge-jwt-api` |
| Application ID URI | `api://<app-id>` |
| App roles | `Lab.Admin` (application permission, value `Lab.Admin`) |
| Exposed API (scope) | `Lab.Read` (admin-consent) — optional; client-credentials flow uses app roles |
| Access token version | v2 |

#### Client / service principal (`app-edge-jwt-client`)

| Property | Value |
|----------|-------|
| Display name | `app-edge-jwt-client` |
| Redirect URIs | None (confidential client, daemon) |
| Client secret | Generated at deploy time; **stored in environment variable / test runner — never committed** |
| API permission | `app-edge-jwt-api / Lab.Admin` (application permission) |
| Admin consent | Required; must be granted before token acquisition |

**Token shape (expected):** `iss` = `https://login.microsoftonline.com/<tenant>/v2.0`, `aud` = `api://<app-id>`, `roles` = `["Lab.Admin"]`.

JWKS endpoint: `https://login.microsoftonline.com/<tenant>/discovery/v2.0/keys`

> **No secrets are stored in any committed file.** The client secret is obtained at
> runtime from an environment variable or test script variable and never written to disk
> inside the repo.

---

## 5. Dependencies

```
rg-afd-edge-jwt-lab
  └─ law-edge-jwt-lab               ← must exist before AFD diagnostic settings
  └─ app-edge-jwt-lab               ← must exist and be healthy before AFD origin probe
  └─ afd-edge-jwt-lab
       ├─ diagnostic settings       ← depends on law-edge-jwt-lab
       ├─ ea-capability-probe       ← depends on AFD route
       ├─ ea-jwt-validate           ← depends on S1-GATE GO + Entra ID app registrations
       └─ ea-execution-filter       ← depends on ea-jwt-validate

Entra ID (parallel track):
  └─ app-edge-jwt-api               ← register first; obtain app-id for audience config
  └─ app-edge-jwt-client            ← register after api; assign Lab.Admin role; grant admin consent
```

---

## 6. Cost Shape

| Component | SKU | $/day (est.) |
|-----------|-----|-------------|
| AFD Standard profile | 1 profile, ~$0.75 base | $0.75 |
| AFD data transfer | <1 GB | $0.08 |
| App Service Plan B1 | Linux, swedencentral | $0.05 |
| Log Analytics ingestion | <1 GB/day | $0.25 |
| Entra ID app registrations | Free | $0.00 |
| **Daily total** | | **~$1.13** |
| **4–6 h session** | | **~$0.28–0.35** |

> Within the $50/day guardrail (rule #7). No cost-gate exception required.

---

## 7. Tags (applied to all resources)

```
lab        = afd-edge-actions-jwt-validation
env        = lab
owner      = jose
created-by = morpheus
```

---

## 8. Identity Plan

| Identity | Type | Permissions | Notes |
|----------|------|-------------|-------|
| App Service (system-assigned MI) | Managed Identity | None initially; potential `Monitoring Metrics Publisher` to Log Analytics | Not required for primary scenarios |
| `app-edge-jwt-api` | Entra app registration | Exposes `Lab.Admin` app role | Resource/API registration |
| `app-edge-jwt-client` | Entra service principal | Assigned `Lab.Admin` on `app-edge-jwt-api` | Confidential client; secret held in test runner only |
| Deployer (Jose / pipeline) | User / SP | `Contributor` on `rg-afd-edge-jwt-lab`; `Application Administrator` in Entra | Required for app reg creation and admin consent |

No `Owner`-scoped role assignment is required. No Key Vault is provisioned; the client secret lives only in the shell session or CI environment variable.

---

## 9. Deploy Sequence

```
A0 — Foundation
  az group create --name rg-afd-edge-jwt-lab --location swedencentral
  az monitor log-analytics workspace create -g rg-afd-edge-jwt-lab \
      --workspace-name law-edge-jwt-lab --location swedencentral --retention-time 30
  az webapp create [B1 Linux, swedencentral; deploy app code with FDID middleware]
  az afd profile create --profile-name afd-edge-jwt-lab --sku Standard_AzureFrontDoor \
      -g rg-afd-edge-jwt-lab
  az afd endpoint/origin-group/origin/route create
  az monitor diagnostic-settings create [AFD → law-edge-jwt-lab]

A1 — Entra ID (parallel with A0)
  az ad app create --display-name app-edge-jwt-api [+ Lab.Admin app role]
  az ad app create --display-name app-edge-jwt-client [+ API permission, admin-consent]
  az ad app credential reset --id <client-app-id>   # secret → env var only, never committed

A2 — Capability probe
  Deploy ea-capability-probe to /debug/* route
  GET /debug/request via AFD endpoint
  Pull EdgeActionConsoleLog from Log Analytics

S1-GATE:  crypto APIs present → A3   |   absent → STOP, origin-only path

A3 — JWT Edge Actions (conditional on S1-GATE GO)
  Deploy ea-jwt-validate (JWKS URL, audience, issuer, required role)
  Deploy ea-execution-filter (fail-open test)

A4 — Token acquisition
  CLIENT_SECRET=$(...) curl -X POST \
    "https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token" \
    -d "grant_type=client_credentials&client_id=<>&client_secret=$CLIENT_SECRET&scope=api://<app-id>/.default"

A5 — Run scenarios S1–S9 (see §10)
```

---

## 10. Scenarios, Pass/Fail Criteria, and Evidence

### S1 — Capability Probe (**ALWAYS run first — sets S1-GATE**)

Deploy `ea-capability-probe`; send GET `/debug/request`.  
**Pass (GO):** `EdgeActionConsoleLog` lists available global objects / crypto API presence → proceed to A3.  
**Pass (STOP):** Log shows empty/undefined crypto APIs → document finding; run origin-only / teaching-only paths only.  
**Evidence:** KQL result from `EdgeActionConsoleLog`; screenshot.

---

### S2 — Missing Token

GET `/protected` with no `Authorization` header via AFD endpoint.  
**Pass:** HTTP 401; App Service log shows no inbound request (edge-rejected on GO path).  
**Evidence:** AFD access log; App Service log absence.

---

### S3 — Valid Token

Acquire valid token with `Lab.Admin` role; GET `/protected` and `/admin`.  
**Pass:** HTTP 200; EdgeActionConsoleLog shows `VALIDATED`; App Service log confirms arrival.  
**Evidence:** HTTP response body; AFD access log; console log.

---

### S4 — Expired Token

Backdate `exp` claim or wait for natural expiry; send token.  
**Pass:** HTTP 401 (edge or origin); expiry logged.  
**Evidence:** AFD access log with 401.

---

### S5 — Wrong Audience / Issuer

Token issued for a different `aud` or with forged `iss`.  
**Pass:** HTTP 401; claim mismatch in EdgeActionConsoleLog.  
**Evidence:** AFD log; console log.

---

### S6 — Tampered Token / Signature

Decode valid token; modify payload (e.g. add `Lab.SuperAdmin` role); re-encode without re-signing.  
**Pass:** HTTP 401; console log shows signature failure.  
**Fail:** 200 returned — **critical finding, document immediately**.  
**Evidence:** Response code; EdgeActionConsoleLog.

---

### S7 — Role-Based Authorization (RBAC)

Use client with `Lab.Admin` role removed; GET `/admin`.  
**Pass:** HTTP 403 on `/admin`; `/protected` still 200 (valid token, insufficient role for `/admin` only).  
**Evidence:** HTTP 403; AFD log.

---

### S8 — Direct Origin Bypass

GET `https://app-edge-jwt-lab.azurewebsites.net/protected` directly (bypassing AFD) with valid token.  
**Pass (hardening):** HTTP 403 — AFD service tag restriction blocks direct access.  
**If FAIL:** Service tag restriction did not apply; origin-only validation is sole backstop — document as finding.  
**Evidence:** curl response from `.azurewebsites.net`; AFD endpoint comparison.

---

### S9 — Controlled Runtime Failure / Fail-Open (**Pivotal scenario**)

Send `X-Test-Fail: 1` header triggering `ea-execution-filter` (throw/timeout) on both `/edge-only` and `/protected`.  
**Pass:** `/edge-only` returns 2xx — edge fails open + no origin auth = access granted (**expected teaching-only failure**);  
`/protected` returns 401/403 — origin re-validates and rejects (**expected defence-in-depth success**).  
This proves origin re-validation is mandatory.  
**Evidence:** HTTP responses both paths; EdgeActionConsoleLog showing exception/timeout; App Service log.

---

## 11. Evidence Plan

| Evidence item | Source | Collection method |
|---------------|--------|-------------------|
| EdgeActionConsoleLog | Log Analytics | KQL: `AzureDiagnostics \| where Category == "EdgeActionConsoleLog"` |
| AFD access logs | Log Analytics | KQL: `AzureDiagnostics \| where Category == "FrontDoorAccessLog"` |
| App Service HTTP logs | App Service diagnostics / stdout | Azure Portal → Log stream; or `az webapp log tail` |
| HTTP response codes | curl / test runner | Captured per scenario |
| Direct origin bypass result | curl to `.azurewebsites.net` | Captured in S8 |
| Token claims (decoded) | jwt.io or `jq` offline | Payload section only; no signature portion committed |

All evidence goes to `labs/afd-edge-actions-jwt-validation/evidence/` (one file per scenario). Zero raw subscription IDs or tenant IDs in committed files.

---

## 12. Cleanup Sequence

> **Separately gated — do not execute without explicit Jose approval.**

```
1. Delete Edge Actions from AFD routes
2. az afd profile delete -g rg-afd-edge-jwt-lab --profile-name afd-edge-jwt-lab --yes
3. az webapp delete + az appservice plan delete
4. az monitor log-analytics workspace delete -g rg-afd-edge-jwt-lab --workspace-name law-edge-jwt-lab --yes
5. az ad app delete --id <app-edge-jwt-api app-id>
6. az ad app delete --id <app-edge-jwt-client app-id>
7. az group delete --name rg-afd-edge-jwt-lab --yes --no-wait
```

Verify: `az resource list -g rg-afd-edge-jwt-lab` returns empty.

---

## 13. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Edge Actions v1 has no crypto runtime API | **Confirmed scope boundary (2026-08-19)** — cryptographic JWT signature validation is outside the supported scope of public preview | Claims-only parsing is the maximum supported EA JWT behaviour. Origin must perform cryptographic validation. |
| JWKS fetch not available in EA sandbox | **Confirmed by lab evidence (S1, 2026-08-17/18)** — `fetch=undefined` | No mitigation within EA; origin is the mandatory cryptographic enforcement point. |
| Edge Action execution timeout < JWKS RTT | Medium | ea-execution-filter (S9) tests fail-open behaviour; defence-in-depth backstop |
| App Service service tag restriction ineffective (platform behaviour) | Medium | S8 tests this explicitly; document as finding if bypass succeeds |
| Entra admin consent unavailable in tenant | Medium | Require `Application Administrator` role; pre-check in A1 |
| Official sample repo has no JWT reference | Low (expected — confirmed by lab evidence and scope boundary) | No JWT sample expected; `ea-capability-probe` (S1) is the lab's evidence source. |
| AFD Standard doesn't support Edge Actions (SKU gap) | Low | Verify at A2; Premium_AzureFrontDoor may be required |

---

## 14. Open Questions (resolved)

1. Does Edge Actions v1 expose `crypto.subtle` or equivalent? → **No.** Lab evidence (S1, 2026-08-17/18): `crypto=undefined`. Cryptographic JWT signature validation is outside the supported public-preview scope.
2. Does the Edge Action sandbox allow outbound HTTPS to `login.microsoftonline.com`? → **No.** Lab evidence (S1, 2026-08-17/18): `fetch=undefined`. Scope boundary confirmed (2026-08-19).
3. Is Edge Actions GA or still in preview in swedencentral/globally? → **Public preview** as of 2026-08-17/18. API version `2025-09-01-preview`.
4. Does AFD Standard support Edge Actions, or is Premium required? → **Standard supported** — confirmed by successful lab deployment on Standard SKU.

---

## 15. References

- [Azure Front Door Edge Actions — official docs](https://learn.microsoft.com/azure/frontdoor/edge-actions)
- [EdgeActionsSamples — GitHub](https://github.com/Azure/EdgeActionsSamples) _(no JWT sample as of 2026-08-17)_
- [AFD diagnostic logs](https://learn.microsoft.com/azure/frontdoor/front-door-diagnostics)
- [Entra ID client credentials flow](https://learn.microsoft.com/azure/active-directory/develop/v2-oauth2-client-creds-grant-flow)
- [App Service access restrictions (service tag)](https://learn.microsoft.com/azure/app-service/app-service-ip-restrictions)
- [AFD origin hardening with X-Azure-FDID](https://learn.microsoft.com/azure/frontdoor/origin-security)
