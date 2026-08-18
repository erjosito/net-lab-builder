# S2 — Missing Token Evidence
Niobe · 2026-08-18 · **VERDICT: PASS**

## Test

`GET https://edge-jwt-lab-hgbdgdh9ccaja2hv.b02.azurefd.net/protected`
No `Authorization` header.

`GET https://edge-jwt-lab-hgbdgdh9ccaja2hv.b02.azurefd.net/admin`
No `Authorization` header.

## Results

| Path | HTTP Status | X-Azure-Ref (truncated) | EA Log |
|------|-------------|------------------------|--------|
| `/protected` | **401** | 20260818T102616Z-…037gr | `EA_REJECT code=401 reason=MISSING_TOKEN` |
| `/admin` | **401** | 20260818T102616Z-…037h7 | `EA_REJECT code=401 reason=MISSING_TOKEN` |

## Analysis

- EA `eajwtvalidate` executes on `/protected` and `/admin` routes.
- `event.request.headers['authorization']` is absent (or does not start with `Bearer `).
- EA sets `event.response.response_code = 401` and returns immediately.
- **Origin is never reached** — edge rejection confirmed by no corresponding App Service log entry.
- AFD returns its default 401 HTML error page as the response body.
- `edgeActionsStatusCode_s = 200` in FrontDoorAccessLog — EA *execution* succeeded (no timeout/exception). The 401 is the EA's deliberate response.

## Evidence Files

- `show-output/001-EdgeActionConsoleLog-30min.txt` — EA_REJECT MISSING_TOKEN entries
- `show-output/003-HTTP-requests-evidence.txt` — raw HTTP status

## Verdict: PASS ✅
