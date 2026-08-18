# S1 — Capability Probe Evidence
Niobe · 2026-08-18 · **VERDICT: CONDITIONAL**

## Activation

EA resource `eaprobe2` deployed; route `rsedgeprobe/ruleprovedebug` attached to `/debug/*`.
EA `eajwtvalidate` subsequently deployed; route `rsedgejwt/ruleprotected` attached to `/protected`, `/admin`.

## API Probe Results (from EdgeActionConsoleLog, LAW law-edge-jwt-lab)

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
PROBE fetch_skipped=no_fetch_or_promise
```

Source: `EdgeActionConsoleLog` table, workspace `law-edge-jwt-lab`, EA resource `eaprobe2/v1`.
Results confirmed across 10+ probe requests; deterministic across all AFD PoPs.

## Verdict: CONDITIONAL

| API | Result | Impact |
|-----|--------|--------|
| `crypto` | `undefined` | **STOP** — RS256/JWKS signature verification impossible |
| `crypto.subtle` | `N/A` (crypto undefined) | **STOP** — `importKey` / `verify` unavailable |
| `fetch` | `undefined` | **STOP** — JWKS endpoint calls impossible |
| `atob` / `btoa` | `undefined` | **STOP** — browser base64 API unavailable |
| `TextEncoder` | `undefined` | N/A |
| `Promise` | `function` | ✅ Async control flow available |
| `JSON` | `object` | ✅ JSON parse/stringify available |
| `Date` | `function` | ✅ `Date.now()` for exp check |
| `Uint8Array` | `function` | ✅ Available but not needed for pure-JS path |

**CONDITIONAL** — claims-only enforcement is possible using pure-JS base64url decode.
Full RS256/JWKS signature verification is impossible in this sandbox.

## Security Model Confirmed

```
Client → AFD Edge Action (claims-only: iss/aud/exp/nbf/roles) → App Service (jose RS256/JWKS)
```

The **origin is the only cryptographic security boundary.**

## Additional Finding: B3 — Private Preview Access Expired

Discovered during A3 deployment: `Microsoft.Cdn/EdgeActionsPrivatePreview = NotRegistered`.
EA control plane blocked for new resource creation. Existing `eaprobe2` data plane continues.
`ea-jwt-validate.js` deployed via workaround (eajwtvalidate EA, Session 4).

## References

- [Azure Front Door Edge Actions (official docs)](https://learn.microsoft.com/azure/frontdoor/edge-actions)
- [Azure/EdgeActionsSamples — JS API](https://github.com/Azure/EdgeActionsSamples/tree/main/src/edgeactions-js)
- `edge-actions/ea-capability-probe.js` — probe implementation
- `show-output/001-EdgeActionConsoleLog-30min.txt` — raw KQL results
