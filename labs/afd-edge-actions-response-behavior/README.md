# Azure Front Door Edge Actions response behavior

Focused public-preview lab for testing documented and undocumented fields on
`event.response`.

## Scope

- Documented `body`, `headers`, `set_cookie_headers`, and response codes.
- Unsupported response codes: 302, 404, 418, and 500.
- Undocumented aliases: `status`, `statusCode`, `content`, `data`, `payload`,
  singular `header`, reason phrase, and body-encoding metadata.
- Evidence showing whether the response came from Edge Actions or the origin.
- Whether the platform tracking reference is available inside the Edge Action
  early enough to copy into a custom response body or header. The client-facing
  `X-Azure-Ref` header is captured independently for comparison.

## Deploy

```powershell
.\deploy\Deploy.ps1
```

Deployment takes approximately 20–30 minutes because Edge Action code
validation and attachment propagation are asynchronous.

## Test

```powershell
.\tests\Invoke-ResponseTests.ps1
```

Results are written to `evidence/response-results.json`.

## Tracking reference result

Front Door automatically includes the tracking reference in the client-facing
`X-Azure-Ref` response header. For Edge Action-generated 401 responses, the
Front Door HTML error page also displays the same value as `x-azure-ref ID`.

The tracking reference was not available to the Edge Action through
`event.context`, so the action could not copy that platform-generated value
into its own custom header or body. The value appears to be assigned after the
Edge Action executes. Applications that need a correlation value inside a
custom response should accept or create a separate request ID; use
`X-Azure-Ref` for Front Door and Edge Action log correlation.

Evidence: `evidence/tracking-reference-result.json`.

## Public and protected route reproduction

The optional JWT route demonstration recreates the original portal structure:

- `/public` uses `rt-all` and matches no Edge Action rule.
- `/protected` and `/admin` use the more-specific `rt-jwt` route.
- `rt-jwt` associates `rsedgejwt/ruleprotected`.
- `ruleprotected` invokes the separate `eajwtvisual` Edge Action.
- A request without a bearer token receives 401.

Deploy it with:

```powershell
.\deploy\Add-JwtRouteDemo.ps1
```

This is intended to make the route distinction visible and testable. It checks
only for the presence of a bearer token and is not cryptographic JWT
authentication.

A separate route is required because the preview currently permits only one
Edge Action rule per route; `rt-all` already hosts `rsresponseprobe`.
The demonstration restricts `rt-all` to `/ea/*`, `/control`, `/public`, and
`/health` so that `/protected` and `/admin` can match only `rt-jwt`.

Verified behavior:

| Request | Result | Processing path |
|---|---:|---|
| `GET /public` | 200 | Origin reached; no JWT Edge Action |
| `GET /protected` without `Authorization` | 401 | Rejected by `eajwtvisual` |
| `GET /protected` with a bearer value | 200 | Edge Action accepted; origin reached |

In the portal, open **Front Door manager** to compare `rt-all` and `rt-jwt`,
then open **Rule sets > rsedgejwt > ruleprotected** to see the `/protected`
and `/admin` condition and the `eajwtvisual` action.

Evidence: `evidence/public-protected-result.json`.

## Cleanup

```powershell
.\deploy\Cleanup.ps1
.\deploy\Cleanup.ps1 -Confirmed
```

Cleanup is separately approval-gated. The script removes the rule reference
before deleting the Edge Action to avoid malformed attachment orphans.
