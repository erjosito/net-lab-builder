# Billing access preflight

**Updated 2026-10-15T07:31:25Z: billing access prerequisite PASS, with a
mandatory client-side filtering safeguard. Capacity is still unverified.
The earlier failed CLI probe below is retained as history, not current status.**

Two subsequent direct HTTPS requests avoided shell URL parsing entirely. Both
returned HTTP 200 from Consumption Usage Details. In-memory schema inspection
confirmed the `modern` kind and fields `quantity`, `unitOfMeasure`, `meterId`,
`meterName`, `effectivePrice`, `unitPrice`, `costInBillingCurrency`, `resourceGroup`,
`instanceName`, `additionalInfo`, and `date`. No usage values were printed or
persisted, and no pagination was performed.

**Important observed limitation:** the supplied nonexistent-RG filter did not
exclude the returned record in the Windows modern schema request. This is not
a universal assertion about all date filters or offers. The follow-up
[API matrix and executable collector](costs/README.md) distinguish documented
RG-only syntax, legacy receipt-date examples, exploratory modern-date syntax
and dollar-key encoding. WSL aggregate Query passed, while Consumption returned
an offer-related HTTP 400, not an ignored filter. An authorized collector
must validate every row against the private lab inventory and actual usage date
in memory before persistence, discard all non-lab rows, bound pagination, and
never publish full reports or signed URLs. If complete scoped collection cannot
be established within those limits, the billing verdict remains inconclusive.
An empty result, permission success, or a schema alone is not a charge result.

This resolves endpoint permission and schema access, not agreement classification
or actual lab meter visibility. The first mature cross-region control must still
demonstrate attributable quantities and rate. No Azure resources were created
by these probes; all owned processes exited.

## Earlier probe history

**Scope:** read-only prerequisite verification; no deployment, traffic, export,
Cost Details report generation/download, SKU catalogue retry, provider registration,
or authentication/configuration change.

The current default subscription was resolved privately from read-only profile
metadata and verified with `az account show --subscription <subscription> -o json`.
Account discovery and the successful Query invocation were explicitly pinned
to that same subscription. The details command was constructed with the same
pin, but its batch-file execution was split by Windows shell metacharacters;
the intended filter, limit and explicit subscription argument cannot be
asserted to have reached Azure. This invalidates the details test.
Account discovery exit code: 0. Each CLI process had an enforced timeout (account:
15 seconds; each billing request: 35 seconds) and specific-PID tree termination.
No tokens or non-lab usage were persisted.

## Actual results

```json
{
  "startedUtc": "2026-10-15T07:28:51.500875+00:00",
  "endedUtc": "2026-10-15T07:29:18.449810+00:00",
  "subscriptionPinned": true,
  "accountExitCode": 0,
  "resourceGroupFilter": "rg-bandwidth-billing-preflight",
  "results": [
    {
      "api": "Query",
      "startedUtc": "2026-10-15T07:28:52.679122+00:00",
      "endedUtc": "2026-10-15T07:28:59.618853+00:00",
      "exitCode": 0,
      "httpStatus": 200,
      "timeout": false,
      "rowCount": 0,
      "columns": [
        {
          "name": "PreTaxCost",
          "type": "Number"
        },
        {
          "name": "UsageDate",
          "type": "Number"
        },
        {
          "name": "Currency",
          "type": "String"
        }
      ],
      "nextLinkPresent": false,
      "verdict": "PASS",
      "message": "Endpoint request succeeded; empty data does not prove quantity visibility."
    },
    {
      "api": "Consumption Usage Details",
      "startedUtc": "2026-10-15T07:28:59.619056+00:00",
      "endedUtc": "2026-10-15T07:29:18.449242+00:00",
      "exitCode": 1,
      "httpStatus": null,
      "timeout": false,
      "verdict": "INCONCLUSIVE",
      "error": "'metric' is not recognized as an internal or external command,\noperable program or batch file.\n'%24expand' is not recognized as an internal or external command,\noperable program or batch file.\n'%24filter' is not recognized as an internal or external command,\noperable program or batch file.\n'%24top' is not recognized as an internal or external command,\noperable program or batch file.\n"
    }
  ],
  "azureMutations": 0,
  "ownedProcessesIdle": true
}
```

HTTP status is extracted from Azure CLI verbose response metadata; null means
the CLI did not expose a parseable status, not an assumed denial.

## Reproduction templates (private identifiers omitted)

```powershell
az account show --subscription <subscription> --output json --only-show-errors
az rest --subscription <subscription> --method POST --url 'https://management.azure.com/subscriptions/<subscription>/providers/Microsoft.CostManagement/query?api-version=2023-11-01' --headers 'Content-Type=application/json' --body '@<lab-private-query-body.json>' --output json --verbose
az rest --subscription <subscription> --method GET --url 'https://management.azure.com/subscriptions/<subscription>/providers/Microsoft.Consumption/usageDetails?api-version=2024-08-01&metric=ActualCost&$expand=meterDetails&$filter=<URL-encoded-filter>&$top=1' --output json --verbose
```

Run templates only inside an active lease with enforced process timeouts.
The actual Query body was:

```json
{
  "type": "ActualCost",
  "timeframe": "Custom",
  "timePeriod": {
    "from": "2026-10-14T00:00:00Z",
    "to": "2026-10-14T23:59:59Z"
  },
  "dataset": {
    "granularity": "Daily",
    "aggregation": {
      "totalCost": {
        "name": "PreTaxCost",
        "function": "Sum"
      }
    },
    "filter": {
      "dimensions": {
        "name": "ResourceGroup",
        "operator": "In",
        "values": [
          "rg-bandwidth-billing-preflight"
        ]
      }
    }
  }
}
```

Consumption filter: `properties/resourceGroup eq 'rg-bandwidth-billing-preflight'
and properties/usageStart ge '2026-10-14' and properties/usageEnd le '2026-10-15'`.
No pagination or intentional unfiltered fallback was performed. The failed
details attempt's standard output was discarded without persistence; no returned
usage records were printed or retained. Because the Windows shell split the
URL at ampersands, the scope/filter of any initial request cannot be established.
No retry was made after closing the lease. The unsafe private probe script was
removed to prevent reuse. This date filter concerns
billing receipt dates; it does not establish a test usage-day attribution.

## Historical interpretation and spend gate (superseded by PASS above)

Query success establishes only this aggregate request's permission/support.
Detailed endpoint success with an empty RG establishes endpoint access, not
observed meter quantity/unit, price, or attribution. The schema contract includes
legacy/modern usage details with quantity, effective price and meter fields;
actual first mature cross-region positive-control rows remain mandatory.

**Not eligible to proceed solely on Query success.** If detailed access is not
PASS, the detailed-evidence prerequisite remains BLOCKED pending a supported
lab-isolated detailed path. An HTTP 400/unsupported-offer response is not RBAC
denial; a timeout is INCONCLUSIVE. Agreement/offer was not established from
subscription name or quotaId, and Cost Details report support/access was not
tested by creating a subscription-wide report.

At the end of that earlier failed probe, the proposed next step was a fresh
read-only lease for one correctly encoded and
shell-safe Consumption request, with subscription/RG/date/limit guaranteed to
reach Azure (for example invoke the installed CLI's Python entry point directly
rather than an unquoted `az.cmd` URL). Preserve exact HTTP/error metadata.
If that safely filtered request rejects the offer, obtain owner confirmation
of the agreement/offer and select the supported lab-only details path.
That subsequent access probe has now passed as summarized at the top; do not
repeat it under the deployment lease. No denial or unsupported offer was
established by the earlier client-side failure. Catalogue/native ARM validation
and actual D0 allocation subsequently passed, and A/B/P were deallocated; see
[deployment-log.md](deployment-log.md). This does not establish actual lab usage,
complete future pagination, offer classification or any empirical charge result.

## Authoritative contracts checked (2026-10-15)

- [Query 2023-11-01](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2023-11-01):
  POST scope, dataset/filter/aggregation contract, HTTP 200/204.
- [Usage Details 2024-08-01](https://learn.microsoft.com/en-us/rest/api/consumption/usage-details/list?view=rest-consumption-2024-08-01):
  `properties/resourceGroup` equality filter, meter expansion, `$top` 1–1000.
- [Legacy offer guidance](https://learn.microsoft.com/en-us/azure/cost-management-billing/automate/get-usage-details-legacy-customer):
  MOSP/Visual Studio can use Consumption Usage Details; Cost Details report
  currently unsupported for those offers. EA/MCA should use Cost Details, not
  Consumption. Date filtering and ActualCost are documented.

## Billing-probe final state

Zero Azure mutations. All owned CLI process roots exited; no background command
or child was intentionally left running. No restore required. Lease closed.
This paragraph concerns only the read-only billing probes; later infrastructure
mutations and their restore proof are recorded in [deployment-log.md](deployment-log.md).
