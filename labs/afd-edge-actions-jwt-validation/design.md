# afd-edge-actions-jwt-validation — Implementation Design
Trinity · 2026-08-17 · **Contract for Tank (deploy) and Niobe (validate)**

> Phase 4 deployment authorised. Cleanup NOT authorised. Do not deploy, write IaC, or
> create secrets. Do not touch lab-card.md.

---

## 0. Authoritative Corrections to manifest.md

### C1 — X-Azure-FDID header filtering is ARM-native (not application code)

**Manifest claim:** "X-Azure-FDID validation is performed in application code (not ARM-native)."

**Correction:** App Service access restrictions natively support HTTP header filtering
including `X-Azure-FDID` as a condition on the same rule as `AzureFrontDoor.Backend`.
Both conditions must be true. Enforced at the App Service front-end tier — no code change
required. **Authority:**
[App Service access restrictions — Filter by HTTP header](https://learn.microsoft.com/azure/app-service/app-service-ip-restrictions#filter-by-http-header) and
[Secure traffic to origins — App Service tab](https://learn.microsoft.com/azure/frontdoor/origin-security).

**Manifest §4.4 correction:**
> Origin hardening uses **App Service Access Restrictions** (ARM-native):
> - Rule 100: `AzureFrontDoor.Backend` + `X-FD-HealthProbe=1` → Allow (health probes)
> - Rule 200: `AzureFrontDoor.Backend` + `X-Azure-FDID=<FDID>` → Allow (AFD traffic)
> - Implicit deny-all
>
> App-layer FDID re-check is optional (logging), not the authoritative enforcement point.

### C2 — Health probes do not carry X-Azure-FDID

AFD health probes carry `X-FD-HealthProbe: 1` but **not** `X-Azure-FDID`. A single
combined rule would block health probes. The two-rule pattern in C1 is required.

CLI for Tank:
```bash
az webapp config access-restriction add -g rg-afd-edge-jwt-lab -n app-edge-jwt-lab \
  --rule-name afd-healthprobe --action Allow --priority 100 \
  --service-tag AzureFrontDoor.Backend --http-header x-fd-healthprobe=1

FDID=$(az afd profile show -g rg-afd-edge-jwt-lab --profile-name afd-edge-jwt-lab \
  --query frontDoorId -o tsv)
az webapp config access-restriction add -g rg-afd-edge-jwt-lab -n app-edge-jwt-lab \
  --rule-name afd-fdid --action Allow --priority 200 \
  --service-tag AzureFrontDoor.Backend --http-header "x-azure-fdid=${FDID}"
```

---

## 1. Request Flow and Trust Boundaries

### 1.1 Architecture layers

```
Client
  │  HTTPS (any)
  ▼
AFD PoP — Edge Action sandbox (Hyperlight / custom JS runtime)
  │  HTTPS only (forced redirect on route)
  ▼
App Service front-end tier
  │  Access Restriction: AzureFrontDoor.Backend + X-Azure-FDID (ARM-native)
  ▼
App Service worker — route handlers
```

Trust boundaries:
- **B1 (Internet → AFD):** Public TLS; AFD terminates. No auth yet.
- **B2 (AFD Edge → Edge Action):** Hyperlight sandbox; receives `EdgeActionEvent`; can modify headers or synthesise 401/403.
- **B3 (AFD → Origin):** AFD adds `X-Azure-FDID`; reaches origin through `AzureFrontDoor.Backend` IP range; platform access restriction denies others.
- **B4 (Origin app code):** App middleware re-validates JWT and roles. Defence-in-depth backstop.

### 1.2 Per-route flow table

| Route | Edge Action | Origin auth | Notes |
|-------|-------------|-------------|-------|
| `GET /health` | **Bypassed** — attached to separate route rule with no Edge Action | None | Health probe target. Never blocked. |
| `GET /public` | **Bypassed** — separate route, no Edge Action | None | Baseline. No token. Open to any AFD request. |
| `GET /edge-only` | `ea-jwt-validate` invoked | None (trusts forwarded claims) | Teaching-only. Proves fail-open risk. |
| `GET /protected` | `ea-jwt-validate` invoked | App validates JWT independently | Defence-in-depth. Primary valid scenario. |
| `GET /admin` | `ea-jwt-validate` + role=`Lab.Admin` check | App validates JWT + `Lab.Admin` role | RBAC scenario. |
| `GET /debug/request` | `ea-capability-probe` invoked | None (AFD-access-restricted only) | Echo headers. S1 probe. Not exposed to unauthenticated public. |

Route configuration: attach via AFD Rules Engine conditions. `/health` and `/public` → no Edge Action. `/debug/*` → `ea-capability-probe`. `/edge-only`, `/protected`, `/admin` → `ea-jwt-validate` (or teaching variant if CONDITIONAL). Execution filter `X-Test-Fail: 1` → trigger alternate version.

### 1.3 Spoofed-header stripping

Edge Action runs at hook_point = 0 (Client Request), before origin forwarding. Strip from
`event.request.headers` (all keys lowercase):
- `x-validated-claims` — prevents client pre-injecting trusted claims
- `x-edge-jwt-status` — same
- `x-test-fail` — never forward to origin

Note: `X-Azure-FDID` and `X-Forwarded-*` are set by the AFD platform layer and overwrite
any client-supplied values. Do not attempt to set or remove them in Edge Action code.

---

## 2. App Service Origin Hardening — Authoritative Pattern

See §0 for the correction. Summary for Tank:

| Priority | Rule name | Condition | Action |
|----------|-----------|-----------|--------|
| 100 | afd-healthprobe | `AzureFrontDoor.Backend` + `X-FD-HealthProbe=1` | Allow |
| 200 | afd-fdid | `AzureFrontDoor.Backend` + `X-Azure-FDID=<FDID>` | Allow |
| (implicit) | — | everything else | Deny |

Retrieve FDID: `az afd profile show -g rg-afd-edge-jwt-lab --profile-name afd-edge-jwt-lab --query frontDoorId -o tsv`

Health probes match rule 100. Normal AFD requests match rule 200. Direct requests match neither and are denied. S8 tests this explicitly.

---

## 3. Entra ID Two-App Model

### 3.1 Registration shape

**Resource / API app** — `app-edge-jwt-api`

| Property | Value |
|----------|-------|
| Application ID URI | `api://<app-id-of-api-app>` |
| App role | name=`Lab.Admin`, value=`Lab.Admin`, allowedMemberTypes=`Application` |
| Access token version | 2 (manifest: `accessTokenAcceptedVersion: 2`) |
| Exposed scope | `Lab.Read` (optional; client-credentials flow uses app roles, not delegated scopes) |

**Client / daemon app** — `app-edge-jwt-client`

| Property | Value |
|----------|-------|
| Redirect URIs | None — confidential daemon client |
| API permission | `app-edge-jwt-api / Lab.Admin` — **Application** permission type |
| Admin consent | Required before first token; grant with `az ad app permission admin-consent` |
| Secret | Generated at A1; stored in shell env var `CLIENT_SECRET` only; never committed |

### 3.2 Token acquisition (client credentials)

```bash
curl -sX POST "https://login.microsoftonline.com/${TENANT_ID}/oauth2/v2.0/token" \
  -d "grant_type=client_credentials&client_id=${CLIENT_ID}&client_secret=${CLIENT_SECRET}&scope=api://${API_APP_ID}/.default"
```

The `.default` scope delivers all admin-consented Application permissions — `Lab.Admin`.

### 3.3 Expected token shape and endpoints

| Claim | Value |
|-------|-------|
| `iss` | `https://login.microsoftonline.com/<tenant-id>/v2.0` |
| `aud` | `api://<api-app-id>` |
| `roles` | `["Lab.Admin"]` |
| `exp`, `nbf` | Unix timestamps |

- JWKS: `https://login.microsoftonline.com/<tenant-id>/discovery/v2.0/keys`
- OpenID config: `https://login.microsoftonline.com/<tenant-id>/v2.0/.well-known/openid-configuration`

### 3.4 Secret handling

`CLIENT_SECRET` in shell env var only. Never written to disk or committed.
`$TENANT_ID` / `$CLIENT_ID` patterns for non-sensitive IDs.

---

## 4. Capability-Probe Plan (S1)

### 4.1 Purpose

Determine at runtime which JavaScript globals are available in the Hyperlight sandbox.
Cryptographic APIs (`crypto.subtle`, `fetch`, `atob`) are **not listed in official
documentation** as of 2026-08-17. They must be probed.

### 4.2 Probe implementation (ea-capability-probe.js)

```javascript
function handler(event) {
  // Probe all required globals with typeof (never throws)
  const probes = {
    crypto:        typeof crypto,
    crypto_subtle: (typeof crypto !== 'undefined') ? typeof crypto.subtle : 'N/A',
    fetch:         typeof fetch,
    atob:          typeof atob,
    btoa:          typeof btoa,
    Promise:       typeof Promise,
    Uint8Array:    typeof Uint8Array,
    TextEncoder:   typeof TextEncoder,
    JSON:          typeof JSON,
    Date:          typeof Date,
  };
  for (const [k, v] of Object.entries(probes)) console.log(`PROBE ${k}=${v}`);
  for (const [k, v] of Object.entries(event.request.headers)) console.log(`HDR ${k}=${v}`);
  for (const [k, v] of Object.entries(event.context)) console.log(`CTX ${k}=${v}`);
  event.response.response_code = 200;
  return event;
}
```

### 4.3 Verdict criteria

| Finding | Verdict | Next step |
|---------|---------|-----------|
| `crypto=object` AND `crypto_subtle=object` AND `fetch=function` | **GO** | Proceed to A3; implement full RS256/JWKS validation |
| `crypto=object` but `fetch=undefined` | **CONDITIONAL** | JWKS fetch impossible; implement claim-only teaching mode (§5.2) |
| `crypto=undefined` OR `crypto_subtle=undefined` | **CONDITIONAL** | No signature verification; implement claim-only teaching mode |
| Runtime throws / ea-capability-probe fails to load | **STOP** | No JS crypto available; document; deploy origin-only path |

**10 ms budget consideration:** The probe itself does no I/O; it only introspects global
names. Execution time should be < 1 ms. The verdict on `fetch` and `crypto.subtle`
availability tells us whether outbound network calls and crypto are feasible *in
principle* within the 10 ms window — actual JWKS fetch latency requires a separate
timing sub-probe (§4.4).

### 4.4 JWKS latency sub-probe (only if GO verdict)

Include a timed `fetch` to the JWKS endpoint in the capability probe (wrapped in
`try/catch`). Log `JWKS_FETCH status=<N> ms=<elapsed>`. If elapsed ≥ 8 ms → CONDITIONAL.
Mark the block `// REQUIRES_PROBE: async` — whether `async/await` is supported is unknown;
probe `typeof Promise` first. If Promise is undefined, only synchronous-safe code is viable.

---

## 5. Conditional JWT Validation Implementations

### 5.1 Full JWKS + RS256 validation (GO path)

**Condition:** `crypto.subtle` available AND `fetch` available AND JWKS RTT < 8 ms (leaves
2 ms budget for signature verification and claims parsing).

**Implementation pattern (ea-jwt-validate.js — conceptual):**

```
1.  Read event.request.headers["authorization"] → split "Bearer <token>" → 401 if absent/malformed.
2.  Split token on '.' into [hdr_b64, pay_b64, sig_b64]; 401 if not 3 parts.
3.  base64url-decode hdr_b64 → JSON → read kid, alg; 401 if alg !== "RS256".
4.  fetch JWKS endpoint; find JWK matching kid; 401 if not found.
5.  crypto.subtle.importKey("jwk", jwk, {name:"RSASSA-PKCS1-v1_5",hash:"SHA-256"}, false, ["verify"]).
6.  crypto.subtle.verify(..., sig_bytes, utf8(hdr_b64+"."+pay_b64)); 401 + log "SIG_FAIL" if false.
7.  base64url-decode pay_b64 → JSON claims.
8.  Validate exp > Date.now()/1000 → 401 + "EXPIRED". Validate iss, aud → 401 + "ISS/AUD_FAIL".
9.  If path starts with /admin: roles.includes("Lab.Admin") → 403 if absent.
10. Inject event.request.headers["x-validated-claims"] = JSON.stringify({roles,exp}).
11. event.response.response_code = 200; return event.
```

**JWKS micro-cache note:** Each Hyperlight sandbox is fresh per request; no persistent cache exists. Each JWKS branch makes one outbound call to `login.microsoftonline.com`. If JWKS RTT > 8 ms (from sub-probe), fall back to CONDITIONAL path.

### 5.2 Claim-only teaching mode (CONDITIONAL path)

**Condition:** `crypto.subtle` unavailable OR `fetch` unavailable OR JWKS RTT > 8 ms.

**What it does:** Decodes the JWT payload (`base64url` decode, no fetch, no verify),
reads claims, validates `iss`, `aud`, `exp`, `roles`. **Does not verify the signature.**

```javascript
// Claim-only decode — NO signature verification
const parts = token.split('.');
if (parts.length !== 3) { event.response.response_code = 401; return event; }
const payload = JSON.parse(atobUrl(parts[1]));
if (payload.exp < Math.floor(Date.now() / 1000)) { /* 401 */ }
if (payload.iss !== EXPECTED_ISS) { /* 401 */ }
if (payload.aud !== EXPECTED_AUD) { /* 401 */ }

function atobUrl(s) {
  return atob(s.replace(/-/g,'+').replace(/_/,'/') + '=='.slice((s.length%4||4)-2));
}
```

**⚠️ Explicit security disclaimer (must be in code comments and this design):**

> **Parsing JWT claims without verifying the cryptographic signature is NOT
> authentication.** Any attacker who can construct a JWT-shaped string with valid-looking
> `iss`, `aud`, `exp`, and `roles` fields can bypass claim-only validation, because no
> check confirms the token was actually signed by Entra ID. This mode is valid only for
> teaching/demonstration purposes; it explicitly demonstrates the gap that origin
> re-validation closes.
>
> In the CONDITIONAL path, **origin-side validation is the only real enforcement point.**
> The Edge Action in teaching mode provides logging and early header injection but must
> not be relied upon for security.

**Why origin re-validation is mandatory in both paths:**
- **GO path:** EA fails open on timeout — request passes through if origin doesn't re-validate.
- **CONDITIONAL path:** Claim-only decode is trivially forgeable. Origin is the only real enforcement.

---

## 6. Edge Action Response/Header Contracts

### 6.1 Documented response codes

From [EdgeActionsSamples README](https://github.com/Azure/EdgeActionsSamples/tree/main/src/edgeactions-js):

> "Currently AFD supports returning 401 or 403 to reject requests. 200 response code
> indicates that request can continue to be processed with provided modifications on the
> response object. Any other response code is currently considered invalid."

**Implications for Tank's implementation:**
- Return `401` for missing/malformed/expired/wrong-audience/wrong-issuer token.
- Return `403` for valid token but insufficient role (`Lab.Admin` required on `/admin`).
- Return `200` (default) to let the request proceed, with any header modifications applied.
- **Never** return 302, 404, 500, or any other code — behaviour is undocumented and
  treated as invalid by the platform.
- On runtime exception or timeout, the platform **fails open**: the request continues as
  if no Edge Action ran (undocumented fail-open behaviour confirmed by lab-card §Risks
  and verified by S9).

### 6.2 Request header contract

`event.request.headers` is a `{ [key: string]: string }` dictionary.

| Behaviour | Detail |
|-----------|--------|
| All keys are **lowercase** | `authorization`, not `Authorization` |
| Modifications are applied to the forwarded request | Set/delete/modify before returning event |
| Restricted headers | Some platform-reserved headers cannot be modified (undocumented list; probe with S1) |
| `X-Azure-FDID` | Set by AFD platform; do not attempt to set/delete; probe with S1 |

Headers to **inject** outbound (toward origin):
- `x-validated-claims`: JSON-serialised claims summary (only on successful validation).
- `x-edge-jwt-status`: `"VALIDATED"`, `"MISSING"`, `"INVALID"`, `"CLAIMS_ONLY"`.

Headers to **strip** inbound (from client):
- `x-validated-claims` (spoofing prevention)
- `x-edge-jwt-status` (spoofing prevention)
- `x-test-fail` (not forwarded to origin)

### 6.3 Context variable

`event.context` is a string-to-string map of [AFD server variables](https://learn.microsoft.com/azure/frontdoor/rule-set-server-variables) plus `"now"` (UTC), `"country"`, `"deviceType"`. Keys absent on some requests — guard with `?? "unknown"`. Log all keys in `ea-capability-probe` (S1 evidence).

---

## 7. Logging and KQL Plan

### 7.1 Key log columns

**EdgeActionConsoleLog:** `TimeGenerated`, `TrackingReference` (= `X-Azure-Ref`), `LogMessage` (from `console.log`), `EdgeActionVersion`, `ResourceId`.

**FrontDoorAccessLog relevant fields:** `edgeActionsStatusCode` (`200`=success / `503`=EA error), `trackingReference` (correlates with EA log), `httpStatusCode`, `requestUri`, `originResponseStatusCode`.

### 7.2 KQL templates

**Scenario evidence — all Edge Action events:**
```kql
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.CDN"
| where Category == "EdgeActionConsoleLog"
| project TimeGenerated, TrackingReference, LogMessage, EdgeActionVersion
| order by TimeGenerated desc
```

**Correlate EA log with AFD access log:**
```kql
let ref = "<X-Azure-Ref value>";
AzureDiagnostics
| where Category in ("EdgeActionConsoleLog", "FrontDoorAccessLog")
| where TrackingReference == ref or trackingReference_s == ref
| project TimeGenerated, Category, LogMessage, httpStatusCode_d, requestUri_s
| order by TimeGenerated asc
```

**S1 probe output (capability results):**
```kql
AzureDiagnostics
| where Category == "EdgeActionConsoleLog"
| where LogMessage startswith "PROBE" or LogMessage startswith "JWKS_FETCH"
| project TimeGenerated, LogMessage
| order by TimeGenerated desc
```

**S9 fail-open evidence (edgeActionsStatusCode = 503):**
```kql
AzureDiagnostics
| where Category == "FrontDoorAccessLog"
| where requestUri_s contains "/protected" or requestUri_s contains "/edge-only"
| project TimeGenerated, requestUri_s, httpStatusCode_d, edgeActionsStatusCode_s
| order by TimeGenerated desc
```

**Log delay:** 3–10 min before logs appear. Use AFD access log for quick HTTP status.
**X-Azure-Ref:** In every AFD response; joins EdgeActionConsoleLog ↔ FrontDoorAccessLog.

---

## 8. Failure and Resiliency Table

| Failure | Documented behaviour | Ranked mitigations |
|---------|---------------------|-------------------|
| **Edge Action timeout (> 10 ms)** | Platform terminates EA; request **passes to origin without EA processing** (fail-open). `edgeActionsStatusCode = 503`. | ① Origin re-validates JWT (free, backstop). ② Reduce EA complexity. ③ JWKS micro-cache if SDK supports it. |
| **Edge Action JS exception** | Same as timeout — platform fails open. | ① Origin backstop. ② Wrap all EA in try/catch; return 401 on known-bad before exception path. |
| **JWKS endpoint unavailable** | EA cannot fetch key; explicit catch → 401 or fail-open if no catch. | ① Origin backstop (always). ② Explicit catch → 401 (safe fail). |
| **Stale JWKS / key rollover** | kid not in current JWKS → EA returns 401 (correct behaviour). Entra rotates ~6 weeks. | ① Always fetch live JWKS (never pin). ② Re-acquire token after rotation. |
| **AFD PoP failure** | AFD routes to healthy PoP automatically. | ① No mitigation needed (anycast). |
| **Origin (App Service) failure** | AFD returns 502/503. | ① AFD health probe (30 s). ② Lab: single origin; production: multi-origin group. |
| **Direct origin bypass** | Request to `.azurewebsites.net`; Rule 200 requires AFD IP + FDID. | ① ARM-native access restriction. ② Origin JWT validation. |
| **Spoofed X-Azure-FDID** | Source IP won't be in `AzureFrontDoor.Backend`; both conditions required. | ① Service tag enforcement is independent of header content. |
| **Spoofed x-validated-claims** | Attacker injects header to trick origin into trusting forwarded claims. | ① EA strips header on inbound (§6.1). ② Origin validates JWT independently. |
| **Header x-test-fail spoofed** | Attacker triggers execution-filter version. | ① EA strips `x-test-fail` before forwarding. ② Remove filter after lab. |
| **Log ingestion delay** | EdgeActionConsoleLog takes 3–10 min to appear. | ① Wait 10 min before querying. ② Use AFD access log for initial HTTP status check. |

**Mitigation complexity ranking (least to most expensive):**
1. Origin re-validation — free, already designed in
2. Explicit EA try/catch → 401 — code-only change
3. JWKS live-fetch (no pinning) — correct by design
4. ARM access restrictions two-rule pattern — deploy-time config

---

## 9. Validation Assertions for Niobe

### S1 — Capability Probe

**Assertion:** `EdgeActionConsoleLog` within 10 min of `GET /debug/request` via AFD endpoint contains `PROBE` lines for all probed globals. At minimum, `PROBE JSON=function` and `PROBE Date=function` must appear (these are universally available JS globals; absence indicates EA did not run).

**Verdict rules:**
- `PROBE crypto=object` + `crypto_subtle=object` + `fetch=function` → **GO**
- Any other combination → **CONDITIONAL** or **STOP** (§4.3)
- `JWKS_FETCH ms=<N>`: N < 8 → full JWKS viable; N ≥ 8 → CONDITIONAL

**Evidence file:** `evidence/S1-capability-probe.md` — KQL result, X-Azure-Ref, final verdict.

---

### S2–S9 Assertion Table

| Scenario | Input | Expected HTTP | Additional assertion |
|----------|-------|---------------|----------------------|
| **S2 — Missing token** | `GET /protected`, no Auth header | **401** | App Service receives no request (edge-rejected on GO path) |
| **S3 — Valid token** | Valid `Lab.Admin` token, `GET /protected` and `/admin` | **200** both | EdgeActionConsoleLog: `x-edge-jwt-status=VALIDATED` |
| **S4 — Expired token** | Token with `exp` in past | **401** | Log: `EXPIRED` |
| **S5 — Wrong audience** | Token with different `aud` | **401** | Log: `AUD_FAIL` |
| **S6 — Tampered sig ⚠️** | Valid payload, modified `roles`, no re-sign | **401** | Log: `SIG_FAIL`. If **200** → critical finding; document immediately |
| **S6 CONDITIONAL** | Same tampered token (teaching mode) | EA passes; **origin 401/403** | Documents gap: claim-only cannot catch forged tokens |
| **S7 — Wrong role** | Valid token without `Lab.Admin`, `GET /admin` | **403** | `GET /protected` with same token → **200** |
| **S8 — Direct bypass** | `curl https://app-edge-jwt-lab.azurewebsites.net/protected` | **403** | If 200: access restriction not effective — critical finding |
| **S9 — Fail-open (pivotal)** | `X-Test-Fail: 1` + valid token, `/edge-only` | **200** (EA failed open, no origin auth — expected teaching failure) | `edgeActionsStatusCode = 503` in AFD log |
| **S9 defence-in-depth** | `X-Test-Fail: 1` + valid token, `/protected` | **401/403** (origin rejects) | Proves origin re-validation is mandatory |

### General assertions (all scenarios)

- `X-Azure-Ref` header present in every AFD response.
- `/health` returns 200; AFD shows origin healthy.
- No secret, tenant ID, subscription ID, or raw FDID in any committed evidence file.
- Evidence files in `labs/afd-edge-actions-jwt-validation/evidence/`.

---

## 10. References

### Official Microsoft documentation

| Reference | URL | Notes |
|-----------|-----|-------|
| Azure Front Door Edge Actions (Preview) | https://learn.microsoft.com/azure/frontdoor/edge-actions | Primary EA reference. Docs updated 2026-07-27. Preview notice applies. |
| AFD Edge Actions — size/resource limits | Same page, §Limits | 16 KB code, 10 ms execution, 3 versions, 100 actions/sub |
| AFD Edge Actions — fail-open behaviour | Same page, §Important considerations | "service terminates the code execution and sends the request without Edge Action processing" |
| AFD Edge Actions — response codes | Same page (implicit) | 200/401/403 only; see EdgeActionsSamples README |
| AFD Edge Actions — logs | Same page, §Edge Action logs | EdgeActionConsoleLog schema |
| AFD server variables | https://learn.microsoft.com/azure/frontdoor/rule-set-server-variables | context dict keys |
| Secure traffic to origins | https://learn.microsoft.com/azure/frontdoor/origin-security | IP filtering + FDID approach; App Service tab: platform-native header filter |
| App Service access restrictions | https://learn.microsoft.com/azure/app-service/app-service-ip-restrictions | Service tag + HTTP header filter; X-Azure-FDID native support |
| App Service — restrict to specific AFD | Same page, §restrict-access-to-a-specific-azure-front-door-instance | Two-rule pattern (health probe + FDID) |
| AFD diagnostic logs | https://learn.microsoft.com/azure/frontdoor/front-door-diagnostics | FrontDoorAccessLog, EdgeActionConsoleLog, edgeActionsStatusCode |
| Entra ID client credentials flow | https://learn.microsoft.com/azure/active-directory/develop/v2-oauth2-client-creds-grant-flow | Token acquisition, .default scope, app roles |
| AFD billing — Edge Actions | https://learn.microsoft.com/azure/frontdoor/billing#example-7-edge-actions | Pricing model |

### GitHub samples repository

| Resource | URL | Notes |
|----------|-----|-------|
| Azure/EdgeActionsSamples | https://github.com/Azure/EdgeActionsSamples | Community repo; official JS API reference |
| EdgeActionEvent interface | https://github.com/Azure/EdgeActionsSamples/tree/main/src/edgeactions-js | **Authoritative API docs**: request, response, context, origin_data, hook_point |
| Sample JS files | https://github.com/Azure/EdgeActionsSamples/tree/main/src/edgeactions-js | A/B, header manipulation, origin selection, URL redirect/rewrite, request rejection |

**⚠️ No JWT sample exists in the Azure/EdgeActionsSamples repo as of 2026-08-17.**
The Edge Actions page lists "JWT token validation" as a supported scenario, but no
corresponding sample code has been published. `ea-capability-probe` is the only
authoritative source of truth for crypto API availability. Every API used in
`ea-jwt-validate.js` must be validated by S1 before relying on it.
