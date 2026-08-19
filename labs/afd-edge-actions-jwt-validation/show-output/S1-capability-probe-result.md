# S1 — Edge Action Capability Probe Result

**Date**: 2026-08-18  
**EA resource**: `eaprobe2` / `v1`  
**AFD profile**: `afd-edge-jwt-lab`  
**Rule**: `rsedgeprobe` / `ruleprovedebug` (condition: `UrlPath BeginsWith /debug`)  
**Verdict**: ⚠️ **CONDITIONAL** — claim-only enforcement only; signature verification impossible

> **Scope clarification — 2026-08-19:** Cryptographic JWT signature validation is outside the supported public-preview scope. The probe below records the observed runtime behavior.

---

## Runtime Confirmation

| Field | Value |
|-------|-------|
| `edgeActionsAgentType_s` | `node` ← EA executing |
| `edgeActionsStatusCode_s` | `200` (success), `500` (one error before diagnostics active) |
| `EdgeActionConsoleLog` entries | Confirmed populated in LAW |

The Edge Action IS executing. The runtime is Node.js (Hyperlight sandbox, `agentType=node`).

---

## API Availability (from `EdgeActionConsoleLog`, LAW)

| API | `typeof` result | Assessment |
|-----|-----------------|-----------|
| `crypto` | `undefined` | ❌ No Web Crypto API |
| `crypto.subtle` | `N/A` (crypto undefined) | ❌ No RS256/JWKS verify |
| `fetch` | `undefined` | ❌ No HTTP calls possible |
| `atob` | `undefined` | ❌ No browser base64 |
| `btoa` | `undefined` | ❌ No browser base64 |
| `TextEncoder` | `undefined` | ❌ No text encoding |
| `Promise` | `function` | ⚠️ Present; `crypto` / `fetch` still absent (probe) — origin RS256/JWKS required |
| `JSON` | `object` | ✅ Available |
| `Date` | `function` | ✅ Available |
| `Uint8Array` | `function` | ✅ Available |

---

## Verdict: CONDITIONAL

### STOP (impossible in this sandbox):
- RS256/JWKS signature verification (`crypto` + `crypto.subtle` unavailable)
- JWKS endpoint fetch (`fetch` unavailable)  
- Base64 decode using browser APIs (`atob/btoa` unavailable)

### CONDITIONAL (possible with pure-JS implementation):
- JWT structural parsing (pure-JS base64url decode — confirmed working)
- Standard claim validation: `iss`, `aud`, `exp`, `nbf`
- Role claim check: `roles[]` contains `Lab.Admin`
- Header strip: remove spoofed `x-validated-claims`, `x-edge-jwt-status`
- Header inject: `x-validated-claims` (claim summary), `x-edge-jwt-status` (VALIDATED/MISSING)

---

## Security Model (CONDITIONAL path)

```
Client → AFD Edge → EA (claims-only) → Origin (RS256/JWKS cryptographic)
```

The EA provides:
- **Defense-in-depth**: blocks missing/structurally invalid tokens before they reach origin
- **Header injection**: passes validated claim summary to origin via `x-validated-claims`
- **Role pre-screening**: blocks wrong-role requests for `/admin` early

The **origin** (`app-edge-jwt-lab`, using `jose` library) performs:
- Full RS256 signature verification against JWKS endpoint
- Issuer/audience validation
- Expiry/nbf validation
- Role enforcement for `/admin`

The origin is the ONLY cryptographic security boundary.

---

## Additional Blocker: B3 (EA Control Plane)

**Discovered 2026-08-18**: `Microsoft.Cdn/EdgeActionsPrivatePreview` feature flag = `NotRegistered`.

The subscription's private preview access has expired. The ARM control plane API (`2025-12-01-preview` and all tested variants) now returns `NoRegisteredProviderFound` or `404` for all `edgeActions` operations.

**Impact**: Cannot create new EA resources or versions.  
**Mitigation**: Existing `eaprobe2` data plane continues executing (data plane is independent).  
**A3 status**: BLOCKED by B3 — see `deploy-log.md` for full blocker record.

---

## Log Samples (EdgeActionConsoleLog, LAW)

```
PROBE btoa=undefined
PROBE crypto_subtle=N/A
PROBE JSON=object
PROBE fetch=undefined
PROBE Date=function
PROBE crypto=undefined
PROBE Uint8Array=function
PROBE atob=undefined
PROBE Promise=function
PROBE TextEncoder=undefined
```

Consistent across all PoPs and all 10+ probe requests. Results are deterministic.
