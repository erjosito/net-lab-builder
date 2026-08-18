# S9 — Fail-Open / Defence-in-Depth Evidence
Niobe · 2026-08-18 · **VERDICT: NOT EXECUTED — B3 blocker**

## Status

`ea-execution-filter` (A4) was not deployed. The EA control plane (`edgeActions` REST API) returned `NoRegisteredProviderFound` for all tested API versions due to `EdgeActionsPrivatePreview = NotRegistered` (B3).

The `eajwtvalidate` EA does not include the execution filter version. S9 cannot be triggered without A4.

## Documented behaviour (official, not lab-observed)

From [Azure Front Door Edge Actions docs](https://learn.microsoft.com/azure/frontdoor/edge-actions):

> "If the code execution exceeds the time limit of 10 ms, the service terminates the code execution and sends the request without Edge Action processing."

> "If the Edge Action throws an exception, the service sends the request without Edge Action processing."

This is the documented **fail-open** behaviour. In both cases, `edgeActionsStatusCode_s = 503` appears in `FrontDoorAccessLog`.

## Expected test design (pending A4 deployment)

1. Deploy `ea-execution-filter` version to `eajwtvalidate` with `isDefaultVersion=False`
2. Trigger via `X-Test-Fail: 1` header → EA throws a deliberate exception
3. Verify:
   - `/edge-only` + `X-Test-Fail: 1` → HTTP 200 (EA failed open; origin has no auth check)
   - `/protected` + `X-Test-Fail: 1` → HTTP 401/403 (origin re-validates; backstop fires)
4. Confirm `edgeActionsStatusCode_s = 503` in AFD access log

## Verdict: NOT EXECUTED ⏸

Pending:
- B3 resolution (re-register EA private preview)
- A4 deployment
- B1 resolution for valid Entra token needed on `/protected`

## Teaching value (available now)

The `/edge-only` route reaching origin without any JWT check (confirmed by S3a evidence) already demonstrates the fail-open risk in a softer form: when no EA is attached, or when EA is bypassed, the teaching-only route is unprotected. S9 would make this explicit with a deliberate exception.
