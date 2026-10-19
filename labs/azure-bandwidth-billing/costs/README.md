# Reproducible Cost Analysis API deliverable

## Latest actual cost answer — 18 October 2026, 12:15Z (offline refresh)

**Transport/cleanup PASS; billing INCONCLUSIVE and open.** New
[fresh T/A/C Queries](../results/2026-10-18-control-financial-comparison-114700.json)
returned HTTP 200 more than ten hours after 01:21Z: **A USD
0.00000137982331216335287 unchanged; C all-Bandwidth USD
0.28475133349094558918 (+0.06725686436425906306); T EUR
0.244085448265384 (+0.078935232962947)**. These are costs, not new
quantities/rates. C nearly, not exactly, matches the 08:15Z CSV aggregate.
The [historical alternative](../results/2026-10-18-historical-control-alternative.json)
adds a timed-out legacy GET and HTTP 200 Query **USD
0.0131025677174329501587**, unchanged: financial stability with a partial
mismatch, not new quantity stability or full 1 GiB reconciliation.
Historical **0.6551259830594063 reported `1 GB` at USD 0.02** remains STALE.
See [exact comparisons and limitations](../billing-evidence.md#latest-snapshot--18-october-2026-1215z-offline-refresh).

The original snapshot stays **4/6**; the alternative closes **global 6/6**,
all owned children idle. Historical generation and GET failures used the
then-fixed **20-second socket timeout / source `2ab6c0ce…`**.
The subsequently reviewed offline patch (**`cbd099e6…`**, coordinator's
independent **82 tests PASS**) makes `--request-timeout-seconds 120`
available for future separately authorized calls, preserving default **20**.
No post-patch live rerun occurred. The flag is a socket timeout, not a hard
real-time total request deadline or ingestion guarantee; token auth remains
separately bounded to **<=15 seconds**. Full semantics and example below
apply to future calls only, not retroactive repair of failed reports.
T's raw-unit/identity issue **#23** and 422 cause remain unresolved.
Only existing **six-hourly schedule 5 / 22 October 23:15:33Z hard stop**
remain; this offline publication creates no request budget or timer.

<a id="latest-actual-cost-answer--18-october-2026-0820z-offline-refresh"></a>

## Superseded actual cost answer — 18 October 2026, 08:20Z (offline refresh)

**Collection PASS; billing INCONCLUSIVE and open.** The new
[separated C/A Cost Details comparison](../results/2026-10-18-separated-detail-comparison-081000.json)
uses **6/6 HTTP requests: two generations, two polls, two downloads**.
Both CSV extractions are COMPLETE, not ingestion-final. Source is unchanged;
the live owner closed with no matching native billing children observed
at **08:19:14.3125252Z**. This documentation refresh used only local artifacts.

**C changed over 9h13m56.043898s:** its **08:15:52.451031Z** extraction
contains four 17 October Intra Continent rows totalling
**14.2374728210270405 reported `1 GB`** at effective/unit price
**USD 0.02**, cost **USD 0.28474945642054081**. The prior 23:01:56Z
extraction had **10.8746547754853965 / USD 0.21749309550970793**:
**+3.3628180455416440 units / +USD 0.06725636091083288**. One bulk row
and one Standard microquantity row were added, not a full 100 GB bill.
Three Standard rows subtotal **USD 0.0000018770704045891761**;
all seven Bandwidth rows total **USD 0.2847513334909453991761**.
Keep the distinct cross-region meter subtotal separate; no unit conversion
or same-region charge attribution is justified.

**A is unchanged, not zero-rated proof:** its **08:17:20.487233Z**
extraction has the same four charged 16–17 October microquantity records,
exact-Decimal multiset unchanged, subtotal **USD 0.0000013798233121633528712**.
It is **6h14m40.600578s** after the actual **02:02:39.886655Z CSV
extraction**, and **6h09m45.763369s** after the **02:07:34.723864Z
operational receipt**. Both separations exceed six hours; neither establishes
a bulk-sized same-region line, explicit zero-rated 100 GB record or finality.

The C report processed **1,536 raw rows**, discarded 1,516 non-inventory
and 13 non-Bandwidth rows in memory, and persisted only seven scoped rows;
**zero raw off-scope rows persisted**. All nonzero C rows are dated
17 October; absent days and echoed report endpoints do not establish
explicit zeros or full-day coverage.
See [exact deltas, A filter counts and limits](../billing-evidence.md#latest-snapshot--18-october-2026-0820z-offline-refresh).

**Empirical billing-publication lag:** additional 17 October usage appeared
more than nine hours after the prior C report. Its completion time cannot
be inferred; no formal delivery SLA or stable reconciliation is established.
Final transport verification at **17 October 22:15:17.236880Z** is still
under 24 hours old; **18 October 22:15:17.236880Z** is an aging checkpoint,
not a formal watermark. The **400 GB transport / 21-root deletion PASS**
is unchanged.

No Query or T request was made: **01:21Z Query costs are not refreshed**.
T still has a genuine duplicate service ID, raw **`1 TB`** versus retail
**`1 GB`**, and asynchronous **422 cause UNKNOWN**. Historical provenance
and the bounded public reproduction below remain unchanged, not new evidence.
Existing **schedule 5 only**, original **22 October 23:15:33Z hard stop**,
and no-new-traffic requirement remain unchanged. Suggested **~14:19Z** is
not a verified scheduler due time or collection authority.
The [same-region policy interpretation](../README.md#policy-handoff-2026-10-18-same-region-cross-tenant-public-ip-egress)
still lacks explicit cross-tenant wording and excludes the BYOIP
Internet-egress exception and separate product/service charges.

### Offline API clarification — 18 October 2026, ~08:45Z

The [clarification and redacted two-row support package](../results/2026-10-18-billing-api-clarification.json)
is **OFFLINE_RESEARCH_NOT_NEW_BILLING_OBSERVATION**, not another collection.
The [Query schema](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2026-06-01)
allows generic aggregation names and at most **two groupings**; `Usage` is
equivalent to `ActualCost`, not proof of quantities. The inspected references
do not establish accepted `UsageQuantity` aggregation or `UnitOfMeasure`
grouping for this scope. Our implemented and observed projection returns
costs, not quantities; this is not a universal API impossibility claim.

The [legacy Usage Details contract](https://learn.microsoft.com/en-us/rest/api/consumption/usage-details/list?view=rest-consumption-2024-08-01)
does not explicitly guarantee top-level `id/name` uniqueness per financial
line. The observed same-ID/different-payload pair remains unresolved, not a
proven contract violation. Keep the conflict guard; neither automatic deduplication
nor local hashes as Microsoft-issued identity is justified. Agreement-specific
price sheets require established agreement/access, not an MSDN alias or Query
success. See [scope, pricing restrictions and official sources](../billing-evidence.md#offline-billing-api-clarification--18-october-2026-0845z).
No further probes or support submission were made. Billing remains open;
published comparison **#22**, schedule **5**, and its original hard stop are unchanged.

## Superseded actual cost answer — 18 October 2026, 02:25Z (offline refresh)

**Transport/cleanup PASS; billing INCONCLUSIVE, still open.** The
[02:07Z A CSV / T diagnostic baseline](../results/2026-10-18-detail-baseline-020010.json)
contains four A charged microquantity rows (16–17 October), with complete
CSV extraction but no bulk-sized same-region 100 GB line or explicit zero.
The [02:21Z T provenance sidecar](../results/2026-10-18-t-unit-provenance-021800.json)
proves raw **`properties.meterDetails.unitOfMeasure = "1 TB"`**, correctly
projected by the public normalizer. Two owned Bandwidth rows have the same
service ID but different contents and unchanged original hashes. Public
`conflicting_record_identity` correctly fails closed; separate diagnostic
retention remains **INCOMPLETE**, not a complete public report.

Their exact **EUR 0.165150215302437** cost sum equals the earlier independent
Query: financial corroboration, not uniqueness, units, conversion or credit
proof. Reported effective price **EUR 0.017329** and `unitPrice = 0`
must both be preserved. Independent official exact-meter retail metadata
reports **`1 GB`, EUR 0.0176 / USD 0.02**, contradicting the legacy raw
unit without proving the cause or a /1,000 conversion. Date/offer/currency
comparability and negotiated pricing are not established.
See [exact rows and source provenance](../billing-evidence.md#latest-snapshot--18-october-2026-0225z-offline-refresh).

Fresh C remains the **17 October 23:01:56Z** CSV, not refreshed:
**10.8746547754853965 reported `1 GB` × USD 0.02 =
USD 0.21749309550970793**, positive partial cross-region evidence only.
T's asynchronous 422 cause remains **UNKNOWN**.
The new manual check is now **6/6 customer calls** (A 3 + T 1 first failure
+ 1 diagnostic + 1 provenance); the frozen 02:07 artifact still records
5/6 as of then. No request budget was reset.

Earliest six-hour clocks: Query **07:21:11Z**, A details **08:07:34Z**,
T provenance **08:18Z+** (conservative completion-based **08:21:56Z**).
These do not make incomplete data mature or prove an ingestion watermark.
No Azure calls, source or automated-job changes in this refresh; the existing
**22 October 23:15:33Z** hard stop remains.

### T date-bounded Consumption reproduction

The ordinary public `details` command needs **no private adapter**. From the
repository root, with existing private T context/inventory paths and a new
output name, use the existing flags below only when separately authorized:

```powershell
$ctxPath = '<ABSOLUTE_PRIVATE_T_CONTEXT_JSON>'
$inventory = '<ABSOLUTE_PRIVATE_T_INVENTORY_JSON>'
$ctx = Get-Content -LiteralPath $ctxPath -Raw | ConvertFrom-Json
$stamp = [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
python labs\azure-bandwidth-billing\costs\cost_api.py details `
  --transport native --context $ctxPath --inventory $inventory --resource-group $ctx.resourceGroup `
  --start 2026-10-15 --end 2026-10-18 --filter-variant legacy-date `
  --max-pages 1 --max-http-requests 1 --max-retries 0 --max-seconds 75 `
  --output "labs\azure-bandwidth-billing\private\reports\t-provenance-repro-$stamp.json"
```

Run natively where T's already-pinned CLI credentials exist (the observed
path was native WSL); do not switch/login/copy credentials. These date
bounds reproduce the ordinary reported route, not the private diagnostic
adapter's actual-now end clamp. Do not use them before the end boundary is
past. They do not guarantee ingestion coverage or exact historical bytes.
For the observed same-ID/different-payload pair, expect **fail-closed
`conflicting_record_identity`**, not a successful two-row COMPLETE result.
No public diagnostic/bypass flag exists or is required for the ordinary
reported path. Keep the failed report frozen; independent diagnostics do
not repair identities or authorize another call. The current check's budget
is exhausted; **this example was not executed**.

## Superseded actual cost answer — 17 October 2026, 23:05Z

**Yes: successful Cost Management Queries return actual money amounts, but
not necessarily quantity/unit/rate.** In the latest collection the three
fresh endpoint Queries instead returned **HTTP 429**, so they provide no
fresh cost answer and must not be interpreted as zero.
The separate asynchronous **ActualCost Cost Details API report download**
did succeed for fresh C. Its filtered CSV is **API-generated, not exported
from the portal**. The [sanitized snapshot](../results/2026-10-17-billing-refresh-230000.json)
reports three October-17 `Intra Continent Data Transfer Out` rows totalling:

**10.8746547754853965 × “1 GB” × USD 0.02 =
USD 0.21749309550970793.**

This is a nonzero cross-region charge on fresh C, not the old C → B control
and not full reconciliation of the new 100 GB C → T leg. Preserve the API's
reported unit; do not infer a binary/decimal conversion. CSV extraction
`COMPLETE` is not final ingestion, a watermark, or a final invoice.
Fresh A/T CSVs were not collected in this check. Missing same-region rows
prove neither zero usage nor zero price.
The [400 GB transport result](../results/2026-10-17-large-rerun-complete.json)
and [cleanup](../results/2026-10-17-large-rerun-cleanup.json) are PASS;
**overall billing remains INCONCLUSIVE**.
The historical 1-GiB C → B observation of 0.6551259830594063 “1 GB” remains
**STALE**, not refreshed or replaced by this fresh-C result.
Existing six-hour read-only billing follow-up retains its original
**22 October 23:15:33Z hard stop**; cleanup job 3 is **STOPPED**.

The dated material below preserves earlier API findings, not latest status.

Read-only Python 3 standard-library collector, tested 2026-10-15. This is a
first-class lab outcome: discover which cost API works for each authenticated
offer, test its filters, and collect attributable bandwidth meters without
retaining other resources' bills. API access is **not a bandwidth billing
verdict**. The later [completed A/T transport](../results/2026-10-15-cross-tenant-public-ip.md)
has initial billing **INCONCLUSIVE**: Windows HTTP 200 COMPLETE empty versus
WSL HTTP 429 rate_limited ERROR, not two successful empty snapshots.

**Historical status, 2026-10-16 UTC:** [C → B v4](../results/2026-10-15-cross-region-control.md)
transport/restoration PASS, **1 GiB / one upload / zero retries**; independent
validation PASS (11 reads / 0 mutations). v3 read-only inspection identified
the additional B subnet NSG default deny 65500, corrected on **both NSG layers**.
**23:28Z billing** made three HTTP attempts: A's same three tiny daily costs
total **USD 0.0000728753264993429373**, no quantity/unit/rate or request
attribution; C Query no rows/details timeout; T empty. This is successful
expected-charged transport, **not yet a billed positive control** or zero-cost
proof. [Snapshot](../results/2026-10-15-control-billing.json).
Known-owned cleanup closed PASS **16 October 00:00:11.806224Z**:
13 remaining original core assets absent, C/T groups gone, all known lab
VMs/disks/PIPs deleted. **Core RG and an extra NSG remain preserved** because
creation ownership is unproven; do not adopt/delete. No standalone RG/NSG rent.

**00:43Z adjacent-date audit:** [sanitized evidence](../results/2026-10-16-date-coverage.json).
The prior report requested October 15 to 16 but locally retained October 15
only. Its persisted date-discard count was **zero**; reusing that operation
and widening local retention to both dates confirms **27 owned rows, all
October 15**, six of them Bandwidth. No owned October-16 row was actually lost
to that filter in this report. One new daily ActualCost Query, restricted to
owned A-core/C groups AND Bandwidth, from October 15 midnight **through the
actual current UTC instant**, also returned six October-15 rows and none for
October 16. C's tiny quantity/cost below is unchanged; the bulk control is
still unproven. Three HTTP requests, no new report generation/retries/mutations.
Report reuse is **not a fresh maturity snapshot**; T was not refreshed.

Microsoft defines CSV `Date` as the
[usage or purchase date](https://learn.microsoft.com/en-us/azure/cost-management-billing/automate/understand-usage-details-fields),
not a receipt date. This report contains no `usageStart`/`usageEnd`.
The [REST reference](https://learn.microsoft.com/en-us/rest/api/cost-management/generate-cost-details-report/create-operation?view=rest-cost-management-2025-03-01)
does not explicitly settle end-date inclusivity; the echoed October-16 end
does not prove full-day coverage or ingestion completeness. `DataIngestionEndMT`
was not captured. Future checks must retain **both October 15 and 16** locally,
keep days/snapshots separate, and bound Query to now rather than a future
end-of-day. After this audit, the coordinator replaced the October-15-only
schedule with a **six-hour read-only follow-up** retaining October 15–16
(logical window October 15 00:00Z to October 17 00:00Z, end exclusive).
Query ends at the actual current UTC instant, never a future timestamp.
Each cycle permits at most **six billing HTTP requests and zero infrastructure
mutations**. Absence on October 16 is not a zero-quantity record, and an
adjacent date alone cannot attribute a control.

**00:29Z live CSV schema validation:** one fresh ActualCost report requesting
October 15 to 16 completed (POST 202, poll 200, download 200; **three HTTP requests,
no retries or infrastructure mutations**). No previous operation URL/ID had been
preserved for reuse. Its 65 mixed-case MCA-compatible columns include actual
`ResourceId`, `resourceGroupName`, `date`, `quantity`, `unitOfMeasure`,
`effectivePrice`, `costInBillingCurrency`, and `billingCurrency`.
Streaming exact-inventory/RG/October-15/Bandwidth projection retained six rows
from 371; 344 non-inventory and 21 non-Bandwidth rows were discarded in memory.
C reports **0.000002291053533554 × “1 GB” at USD 0.02**, cost
**USD 4.58210706710815400000E-8**. This is not the 1-GiB control quantity.
A's three source-VM quantities are **0.000966296531260014** at 0.05,
**0.000003241002559662** at 0.02, and **0.000295128673315048** at 0.083
USD per reported “1 GB”. Two additional rows belong to original endpoint B,
not source A. Latest owned usage date is October 15, a date-only observation
that cannot prove ingestion completeness. **Billing remains INCONCLUSIVE,
maturity-blocked**; T was not refreshed. Original contexts/native default
profile hashes are unchanged; the new lease is closed, idle, with no children.

**Historical 00:21Z quantity-source investigation:** the C-only ActualCost Query now
returns one daily “Intra Continent Data Transfer Out” row,
**USD 0.0000000458210706710815**. Quantity/unit/rate remain NOT_REPORTED;
this is not an attributable 1-GiB billed positive control. The modern Cost
Details report route succeeded (202 → 200 and a 386,097-byte CSV download),
but the runtime parser rejected required CSV columns. The downloaded broad
report was memory-only and was not retained; its exact header mismatch cannot
be reconstructed. No A/T query was refreshed in this phase.
The [new reconciliation](../results/2026-10-16-usage-reconciliation.json)
preserves those distinctions and the exhausted billing budget. No additional
traffic, infrastructure/authentication changes, or background work occurred.

**Historical refresh, 18:22Z:** both aggregates returned **HTTP 429 ERROR**.
Windows details returned **HTTP 200 INCOMPLETE**: 1,000 unrelated rows discarded
in memory, zero retained, continuation remaining. WSL details returned
**HTTP 200 COMPLETE empty**, not zero-charge proof. See the
[sanitized snapshot](../results/2026-10-15-billing-refresh.json).
This reinforces mandatory local inventory/RG/actual-usage-date filtering,
bounded completeness checks and treating 429 as error, never zero usage.
C → B v1 **FAIL** / v2 **BLOCKED before bulk** did not establish a control then;
their historical records, and v3's outcome, are unchanged by v4's later PASS.
Mature, attributable meter quantity/unit/rate remains required for experimental
invoice proof; the latest CSV supplies tiny quantities, not the scale-confirmed
control. Successful transport cannot supply billing proof. The [later exact-row interpretation](../results/2026-10-15-billing-verdict.md)
separately applies the published same-region rule across tenants for ordinary
Azure-assigned regional endpoints. Its tiny positive A-attributed costs are not
an intraregional 5 GiB quantity measurement.

## Executables and privacy contract

- `cost_api.py`: daily aggregate `query`, complete asynchronous `cost-details`
  generation/poll/download to **filtered CSV plus normalized JSON**, historical
  Consumption `details`, and permission `probe`. The public commands below need
  no private wrapper, helper import, or manually activated agent lease.
- `preflight_compare.py`: bounded, repeatable Windows/native-Linux comparison,
  and optional provider/catalogue preflight. Requires this lab's active API lease.
- `test_cost_api.py`: offline fixtures/mocked HTTP; no Azure access or dependencies.
- `cost_details_csv` in `cost_api.py`: pure memory-only Cost Details CSV
  projection, accepting documented ResourceId/InstanceId and case variants,
  preserving decimals/nulls, filtering inventory/RG/date before retention.
  The public `cost-details` command uses this projection before writing outputs.
  `cost_details_csv_stream` also bounds downloaded/decompressed bytes,
  supports one CSV ZIP member or gzip, captures safe headers before schema
  validation, and requires exact Bandwidth category/service matching.
  It preserves the original reported date and optional usage interval fields,
  and counts exact-owned rows by date before date/category filtering. Inclusive
  `start`/`end` already support multiple local usage days; they do not determine
  the report API's end-boundary semantics.
  The fresh 00:29Z report successfully exercised the actual mixed-case schema;
  the earlier discarded report was not reconstructed.

Current validation: **45 offline tests passed on Windows** (the original 12
also previously passed on native Ubuntu-24.04 Python), including date-error classification, filtering, Decimal/units, name resolution, reordered Query
columns, exact continuation semantics, duplicate identities, truncation,
timeouts/HTTP errors, context pinning, snapshot overwrite rejection, in-memory
token expiry/clock guards, CSV schema/privacy/row-limit fixtures, public CLI
leases, report polling, all-blob download, SAS-only authorization, atomic output
failure cleanup and WSL report timeout forwarding. These new CLI workflows were
validated offline; that is not a new live Azure or billing result.

The source artifacts are the collector, preflight and offline test Python files
and this README. Runtime context, inventories and snapshots must be under
the existing ignored `private` directory. Never track their contents. No tokens,
raw API error messages, billing URLs, continuations or SAS URLs are saved.
The collector retains a normalized projection and source-record hash, **not**
the full raw lab row (which could contain opaque URLs/additional information).
Snapshot filenames must be new: successive cumulative reports are never appended.
Do not concatenate snapshots or deduplicate merely similar-looking line items.

Initial authentication and refresh check expected subscription/tenant against
the native CLI and request a subscription-pinned ARM token in that environment.
Each HTTP action still checks its lease/deadline. Within one Transport only,
tokens with a valid UTC `expires_on` epoch are cached in memory until two
minutes before expiry, with monotonic expiry and backwards-wall-clock guards.
Missing/invalid epochs and legacy local `expiresOn` never enable caching.
This avoids two native CLI processes per continuation; it does not extend the
selected collection deadline or turn incomplete pagination into success.
No token is persisted or transferred between environments. Azure CLI rejects simultaneous subscription and tenant parameters on
`get-access-token`; the tool verifies both fields on its response instead.
Windows uses the installed CLI's Python entry point with argv, not `az.cmd`
shell quoting. WSL dispatch runs the same source using Linux `python3` and Linux
`az`, with a bounded GNU `timeout` process group. Tokens never cross profiles.
No login, account switching, configuration, extension or provider changes.
Only Cost Management **Query** requests (including continuations/probes) send
`ClientType: GitHubCopilotForAzure` through the existing authenticated HTTP
adapter. Consumption, report generation/polling and SAS downloads do not send
that header. Native and WSL execute the same implementation. This identifier
does **not** establish quota recovery or authorize retrying an existing 429.

HTTP socket timeout defaults to 20s. `--request-timeout-seconds` accepts a
positive integer for Query, Consumption `details`, and `cost-details`, including
ARM requests and CSV blob downloads in native and WSL execution. Each HTTP
attempt uses the smaller of this value and the remaining workflow/lease time;
guard/deadline checks still run between bounded reads. This is a per-request
socket timeout, **not** an overall deadline or a retry budget, and does not
reset or extend `--max-seconds` or a supplied lease's bounds. Azure CLI account
and token subprocesses remain separately bounded to <=15s and remaining time;
this flag does not govern token acquisition. The overall `--max-seconds`
defaults to 75s for Query/Consumption and 300s for Cost Details, with a maximum
of 1800s. All commands default to six HTTP attempts, configurable with
`--max-http-requests` (maximum 100). Query/Consumption default to three pages
(maximum 20), <=8 MiB/page. Query defaults to one 429 retry only if the longest
known Retry-After/Cost Management retry delay is <=2s and fits the deadline.
Reports default to **zero retries**; `--max-retries 0` explicitly disables them
for any command. Explicit report retries honor the longest known delay only
when it fits the remaining deadline. Report generation is always attempted
once, even when retries are enabled. 429/403 and other failures are never empty
success or a trigger to log in, switch accounts or fall back to another API.

Response diagnostics retain optional `responseMetadata` in each `http` record
and on terminal HTTP failures in the JSON/summary. It contains local UTC
`receivedAtUtc`, allowlisted `safeHeaders`, `retryAfterSeconds`,
`suggestedRetryAtUtc`, and `retrySource` (`known` or `unknown`). The longest
valid, finite, nonnegative hint wins across integer `Retry-After`, HTTP-date
`Retry-After`, and all
`x-ms-ratelimit-microsoft.costmanagement-*-retry-after` headers. Dates are
normalized only after complete HTTP-date syntax validation (IMF-fixdate or
obsolete RFC 850/asctime forms); trailing or combined values are rejected.
RFC 850 two-digit years use the receipt's aware UTC instant and HTTP's rolling
50-year window, not the email parser's fixed century pivot. Dates more than
50 years ahead resolve to the most recent past year with those two digits.
Past HTTP dates are unknown, not permission for an immediate retry; explicit
integer `0` remains valid. Invalid/missing/nonfinite hints are ignored; when
no valid hint remains, they produce null delay/time and `unknown`, **not an invented 30-second Query
cooldown**. A finite delay beyond the UTC datetime range remains `known` with
its full delay and a null suggested instant; it never lets a shorter hint win.
Quota/usage/remaining-request counters are not retry delays.
The 30-second minimum applies only to successful pending-report polling.

Only validated retry hints, normalized response `Date`, and UUID-shaped
`request-id`, `x-ms-request-id`, `x-ms-correlation-request-id` values survive
the header allowlist. Location, signed operation `t/c/s/h`, SAS, credentials,
cookies and arbitrary headers are never persisted or printed. Raw HTTP errors
and `az --debug` output are not used. Query/Consumption request failures now
also save an INCOMPLETE private JSON with any earlier filtered rows and HTTP
history; stdout keeps its existing `ERROR` fields and exit 2. Report failures
keep their existing INCOMPLETE/exit-3 contract.

`httpRequests` and per-operation `httpRequestCounts` count HTTP attempts,
including retries and failures, not usage records. Counts distinguish `query`,
`consumption`, `generation`, `poll`, and `download`; `http` records only
responses actually received. Existing `pages`/`polls` count calls that returned
successfully, and `blobsDownloaded` counts fully processed blobs, so consult
the attempt counts for budgets. A retried poll can consume multiple HTTP
attempts without adding usage or downloaded blobs.

The suggested retry instant is advisory, not a persistent cross-command rate
limiter, evidence of which shared quota bucket was exhausted, or permission to
ignore an existing collection cadence/lease/request budget. Operators must
honor both the server hint and their later existing cadence gate across
invocations. A missing hint gives no proven server cooldown. An RG dataset
filter does not create a separate subscription-level Query quota; changing
ClientType or successfully calling Cost Details does not prove Query recovery.

Redirects are rejected. Continuations must contain no raw whitespace/control
characters and must match HTTPS ARM, exact subscription
and API operation path/version; Query repeats POST with the original body,
Consumption follows the original nextLink GET without reconstructing its token.
Page limits, cycles, unattributed lab rows and elapsed/error exits cannot be
reported as a complete successful collection. `COMPLETE` means the requested
snapshot reached its final page, **not** that delayed billing is final.

## Commands (PowerShell, from repository root)

Both commands below are complete, directly callable workflows for the existing
historical C control. Run them from the repository root. Deleted resources are
fine: the context's saved resource group and deployment inventory identify the
historical records. Each run uses new filenames; do not reuse a snapshot name.
This workflow's Query projection returns money, not quantity/unit/rate;
use the detailed CSV for those fields when available.

```powershell
$ctxPath = 'labs\azure-bandwidth-billing\private\control-context.private.json'
$inventory = 'labs\azure-bandwidth-billing\private\control-inventory.private.json'
$ctx = Get-Content -LiteralPath $ctxPath -Raw | ConvertFrom-Json
$stamp = [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
python labs\azure-bandwidth-billing\costs\cost_api.py query `
  --context $ctxPath --inventory $inventory --resource-group $ctx.resourceGroup `
  --start 2026-10-15 --end 2026-10-16 --group-by ResourceId Meter `
  --meter-category Bandwidth --max-seconds 75 --max-http-requests 3 --max-retries 0 `
  --output "labs\azure-bandwidth-billing\private\reports\control-query-$stamp.json"
if ($LASTEXITCODE -ne 0) { throw 'Query did not complete; inspect its sanitized summary.' }
```

```powershell
$ctxPath = 'labs\azure-bandwidth-billing\private\control-context.private.json'
$inventory = 'labs\azure-bandwidth-billing\private\control-inventory.private.json'
$ctx = Get-Content -LiteralPath $ctxPath -Raw | ConvertFrom-Json
$stamp = [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
python labs\azure-bandwidth-billing\costs\cost_api.py cost-details `
  --context $ctxPath --inventory $inventory --resource-group $ctx.resourceGroup `
  --start 2026-10-15 --end 2026-10-16 --max-seconds 300 --request-timeout-seconds 120 `
  --max-polls 3 --max-http-requests 6 --max-retries 0 `
  --csv-output "labs\azure-bandwidth-billing\private\reports\control-details-$stamp.csv" `
  --output "labs\azure-bandwidth-billing\private\reports\control-details-$stamp.json"
if ($LASTEXITCODE -ne 0) { throw 'Report extraction did not complete; inspect its sanitized summary.' }
```

A longer request timeout does not ensure billing ingestion or report completion.
The example selects 120s for future requests only; earlier public CLI failures
used the then-fixed 20s timeout, even where an orchestration ceiling was 90s or
120s. Those historical attempts are not 120s request-timeout tests.

Normal public CLI use creates its own unique, read-only invocation lease under
ignored `deploy\.runtime-control`, bounded by the invocation deadline and HTTP
budget (never more than 30 minutes). It records active/idle state and HTTP
counters and closes in `finally`. A distinct exclusive ownership file prevents
concurrent public collectors; an existing active billing/API lease or `STOP`
fails closed. The CLI never overwrites somebody else's lease or steals stale
ownership. If interrupted externally, have the coordinator confirm the owning
process has ended before removing that invocation's stale ownership file.
`--lease <path>` attaches an explicitly supplied active bounded read-only lease
in the same runtime directory instead; it never edits or closes that caller's
lease. Its remaining expiry, command timeout and request/tool-call budget can
only lower the invocation's bounds. `preflight_compare.py` retains its existing
coordinator lease contract.

Use existing private contexts or supply `--subscription <id>
--expected-tenant <id>` privately. Context accepts `subscriptionId`,
`expectedTenantId` and optional `resourceGroup`; explicit flags take precedence.
Offline tests require only the existing Windows Python standard library:

```powershell
python -m unittest discover -s labs\azure-bandwidth-billing\costs -p 'test*.py' -v
```

Add `--transport wsl --distribution Ubuntu-24.04` to `cost_api.py` for native WSL
execution; use the **WSL** private context, never the Windows subscription.
Windows paths, including relative context/inventory/output/CSV/lease paths,
are resolved before conversion using the standard `/mnt/<drive>` mount.
The WSL process timeout is the selected deadline **plus 30 seconds** for cleanup,
not a fixed 100-second cutoff. Native WSL execution uses `python3` on this same
source with Linux paths (normally `/mnt/c/Users/...`) and omits `--transport wsl`.
Its native `/usr/bin/az` authentication remains separate and unchanged.
WSL discovery in `preflight_compare.py` reads its existing default once, verifies
different tenant **and** subscription from Windows privately, then pins every
subsequent action. Its ignored `wsl-cost-context.private.json` is session context,
not durable authentication or a promise the next session remains signed in.

Inventory accepts either `{"resourceIds":["<exact owned ARM id>", "..."]}` or
the existing deployment format `{"resources":[{"id":"<exact owned ARM id>"}]}`.
No private adapter is needed for `control-inventory.private.json`. Every ID must
be within the pinned subscription/resource group; IDs are matched
case-insensitively and duplicate IDs are rejected. Capture all owned historical
IDs before deletion/replacement. Unknown report IDs are discarded in memory.
**Fresh rerun gotcha:** A and C share a subscription but occupy separate RGs;
T has its own RG/context. Project the retained owned inventory to **one exact
RG per invocation** and invoke Query/Cost Details separately for each RG.
Passing a combined three-RG cleanup inventory to a single-RG command violates
the inventory contract; an inventory-validation failure is not an empty bill.
Keep historical C → B inventory separate from fresh C inventory after deletion.
Unknown same-RG ResourceId Query rows force INCOMPLETE, not silent success.
Modern `instanceName` is accepted as an ID only if canonical; a bare name needs
matching lab RG plus exactly one matching inventory name. Ambiguous names,
wrong RG/subscription, unknown resources, missing dates and wrong usage days
never get saved. Lab rows lacking attribution force INCOMPLETE. Non-lab rows
are discarded in memory; no automatic broad/unfiltered fallback.

### Query dimensions and quantities

Query version `2023-11-01` uses ActualCost, Daily, Sum(PreTaxCost) and an explicit
ResourceGroup dimension filter. Collection groups by ResourceGroup plus one of
`MeterId`, `Meter` or `MeterCategory`. `--grouping none` is probe-only.
The default remains the successfully tested `Meter`, not the rejected `MeterId`.
`--group-by ResourceId Meter` explicitly selects those two dimensions instead;
it requires inventory input and derives ResourceGroup from the verified
resource ID when no RG column is returned. At most two unique dimensions are
allowed, with either ResourceId or ResourceGroup for verifiable scope.
`--grouping ResourceGroup` retains its old RG-only meaning.
`--meter-category Bandwidth` intersects the lab RG filter with that exact meter
category. First inspect an unfiltered lab-only meter-category snapshot to find
the labels actually used: service-specific transfer/processing meters may use
other categories. Never assume this one category captures every networking fee.
An unsupported dimension returns the real HTTP failure. To change resolution,
explicitly rerun with `--grouping MeterCategory` if
needed, saving a **new** snapshot and documenting the chosen grouping. There is
no silent dimension fallback. An additional explicit `--grouping ResourceGroup`
selects cost-only daily RG totals, with **no meter attribution**. Do not present
that as bandwidth-specific evidence.

Initial live collector smoke tests returned **400 BadRequest for MeterId**, then
**429** for explicit Meter and MeterCategory attempts. A subsequent bounded
Windows query using **Meter + ResourceGroup succeeded** with a COMPLETE,
one-page, zero-row snapshot for the nonexistent lab RG. This verifies the
grouping request, not actual bandwidth charges. Offline fixtures verify the collector's
successful reordered-column/continuation contract. The live one-row details
collector returned **INCOMPLETE**, one received/non-lab row discarded, no retained
rows, and a remaining continuation; this is intentional correct truncation,
not a complete cost result. No retries were queued after these final smoke tests.

The explicit `ResourceGroup AND MeterCategory=Bandwidth` query, grouped by
`ResourceGroup` and `Meter`, subsequently succeeded in **both Windows and native
WSL/MSDN**: COMPLETE, one page, zero rows for the nonexistent lab RG on
2026-10-14. This verifies the executable bandwidth-query request in both
contexts; it is deliberately not evidence that actual test traffic is free.

Columns are mapped by **name**, not fixed position; RG, UsageDate, currency and
cost must be verifiable before any aggregate rows are saved. No UsageQuantity
sum is requested; support for that aggregation is not established by the
inspected documentation, and mixed units must never be summed. Details retain decimal
quantity, raw unit, effective/unit price (null if missing), meter, currency,
cost, actual usage day and private resource identity. Never infer price=0 from
missing fields or cost=0 from credits/free tier. 5 GiB is 5.36870912 decimal GB.
Reconcile only like meter/unit/currency/day/rate groups.

**Legacy Usage Details caveat (2026-10-18):** the default collector fails closed
on `conflicting_record_identity`; retaining distinct original-record hashes for
diagnosis does not reconcile service identities or make extraction COMPLETE.
For the exact inter-region meter checked, the unauthenticated
[Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices)
reported `1 GB`, while retained normalized legacy details reported `1 TB`.
The later [public provenance check](../results/2026-10-18-t-unit-provenance-021800.json)
directly establishes nested `properties.meterDetails.unitOfMeasure = "1 TB"`,
with outer `properties.unitOfMeasure` and nested `meterDetails.unit` absent.
No projection-precedence bug is proven. This discrepancy is not proof of a billing bug
or a conversion factor. Preserve reported quantity, unit, effectivePrice and
unitPrice; public retail prices do not replace customer billing rates.
An exact daily cost sum matching Query corroborates financial aggregation,
not unit correctness, unique billing identities or final ingestion.

### Public Cost Details workflow and output contract

`cost-details` makes one ActualCost generation POST using API `2025-03-01`,
then follows the validated exact ARM Location within the pinned subscription
and approved Cost Management operation/version. It handles empty 202 bodies,
repeated pending responses, or an immediate 200 Completed manifest. Polls wait
at least 30 seconds and at least the longest recognized retry header, only if
that wait fits the remaining deadline. Default poll budget is three.

Every manifest blob is validated and downloaded, or extraction is INCOMPLETE.
Empty manifests, duplicate blob identities, foreign scope/version, changing
operation URLs, failed provisioning, unexpected formats and byte-count/row
truncation fail closed. Downloads use HTTPS public Azure Blob account hosts,
container/blob paths and a SAS signature, **without an ARM Authorization
header**, and never follow redirects. All links remain in memory.
Multiple manifest CSV partitions are supported; each blob may be plain CSV,
gzip, or a ZIP containing exactly one CSV. Multi-member ZIPs are rejected,
never silently reduced to their first member. Total wire and decoded bytes are
each capped at 50 MiB; `--max-rows` defaults/maxes to 100,000 across all blobs.

Only an `operation_location_changed` failure adds optional
`operationLocationComparison` to the original persisted report and sanitized
CLI summary. It contains fixed booleans comparing HTTPS/trusted ARM origin,
exact path, parsed logical subscription scope/operation kind/ID, API version,
query field set and values (independent of field order), and changes to the
fixed `t/c/s/h` components. Parsing uses at most five query fields; malformed
URLs/queries, duplicate or empty query values, or unrecognized operation paths
instead produce `available=false` with a fixed reason. No URL, ID, arbitrary query key
name, value, length or digest is retained by this comparison.
These are diagnostic comparisons, **not validation, root-cause or equivalence
proof**: every differing whole URL is still rejected, including reordered
queries with identical parsed values. The replacement is never followed;
request counts, retry/poll behavior, deadlines and timeouts are unchanged.
Successes, missing replacement Locations and other errors omit this field.

The subscription-wide report is streamed without ever writing raw CSV.
Exact inventory + RG + inclusive local usage dates + Bandwidth category/service
are applied before retaining a row. CSV output contains only the readable
normalized fields: actual day and original date, resource alias/owned ID, meter,
quantity, unit, effective/unit price, cost, currency, optional usage interval
and source hash. Decimal strings are preserved; distinct report rows are never
deduplicated just because they look alike. Normalized JSON additionally records
API/metric, requested/returned periods, generation/completion times, actual
owned usage dates, discard counts and extraction versus ingestion state.

Both output paths must be new files under this lab's ignored `private`.
Filtered data is staged there, fsynced and published exclusively; failed output
publication removes only files owned by that invocation, never preexisting
files. A COMPLETE empty extraction writes an explicit header-only CSV and zero
retained records, **not billing-zero proof**. An INCOMPLETE report exits 3 and
writes only its normalized diagnostic JSON, not a misleading completed CSV.
Input/auth/transport setup errors exit 2. Stdout contains sanitized summary
counts/status and optional allowlisted response metadata, never resource IDs,
tokens, Location or SAS URLs.

Dates 15 and 16 are retained inclusively locally. The report API's end-date
inclusivity remains **unknown**: the script does not shift its end into a future
date or claim full-day coverage. Query is capped at the actual current UTC
instant for today's end date. `extractionComplete=true` and HTTP 200 mean all
returned CSV partitions were processed; `ingestionFinal=false` remains explicit.
No CLI result revises the experiment's 1-GiB positive-control criterion.

### Cost Details route investigation (16 October)

The private bounded runtime tested the documented
`generateCostDetailsReport?api-version=2025-03-01` route for the existing core
subscription and the single receipt date 15 October, ActualCost. No billing
agreement type was inferred from the successful operation alone.
The response echoed optional `billingPeriod`/`invoiceId` null fields; exact
dictionary equality incorrectly rejected otherwise matching request context.
Validation now compares metric, scope and actual dates and rejects nonempty
alternative selectors. A download-container restriction copied from the
documentation's `/armreports/` example was also over-specific: the documented
ARM manifest supplies the blob URL. The private downloader now requires an
HTTPS Azure Blob account host, container/blob path and SAS signature, follows
no redirects, and sends no ARM bearer token to Blob Storage. Links remain
memory-only. Byte counts, one-day context and size/row caps are verified.

The historical final CSV failed the old required-column test; its discarded
header cannot be reconstructed. **A fresh authorized report passed live at
00:29Z**, validating actual mixed-case headers, six owned Bandwidth rows and
the source mapping now recorded in the reconciliation. It included October 16
receipt while retaining only October 15 usage. The previous schema blocker is
resolved, not the billing-maturity/transfer-attribution blocker.
Honor the returned Retry-After and Microsoft's recommendation to request
reports at most daily (reports refresh every four hours); this phase's bounded
schema-debug attempts are not a recommended polling schedule.

Official contracts:
[generate report](https://learn.microsoft.com/en-us/rest/api/cost-management/generate-cost-details-report/create-operation?view=rest-cost-management-2025-03-01),
[field definitions](https://learn.microsoft.com/en-us/azure/cost-management-billing/automate/understand-usage-details-fields),
[availability, refresh and receipt-date semantics](https://learn.microsoft.com/en-us/azure/cost-management-billing/automate/get-small-usage-datasets-on-demand).

## Observed matrix, not a universal filter claim

All Consumption probes: one page, `$top=1`, ActualCost, nonexistent lab RG;
no nextLink followed, returned row values neither printed nor retained.
Query permission probes use 2026-10-14 and no grouping. Future details dates
are 2099-01-01..02, deliberately impossible usage negative controls.
“MSDN” below is Jose's offer alias, **not verified agreement classification**.
Windows modern schema also does not establish EA/MCA agreement type. The table's
date predicate is **not a requested server predicate in the RG-only rows**;
those requests test only the documented RG filter.

| Native environment / API | Version / schema | Filter and encoding | HTTP / predicate outcome |
|---|---|---|---|
| Windows Query | 2023-11-01 / columns | RG + daily prior UTC day | 200, 0 rows, no continuation |
| WSL MSDN Query | 2023-11-01 / columns | same | 200, 0 rows, no continuation |
| Windows Consumption | 2024-08-01 / modern | documented RG-only; percent-encoded `$` keys, `meterDetails` expansion alias | 200, 1 row, RG predicate false; nextLink present |
| Windows Consumption | 2024-08-01 / modern | RG + legacy usageStart/usageEnd future range; encoded keys | 200, 1 row, RG and actual-date predicates false |
| Windows Consumption | 2024-08-01 / modern | RG + exploratory properties/date future range; literal `$` keys, documented properties/meterDetails expansion | 200, 1 row, RG and date predicates false |
| WSL MSDN Consumption | 2024-08-01 / no schema returned | RG-only encoded keys; expansion alias | 400; no row predicates possible |
| WSL MSDN Consumption | 2024-08-01 / no schema returned | RG + legacy future dates; literal keys | 400; no row predicates possible |
| WSL MSDN Consumption | 2024-08-01 / no schema returned | documented RG-only + properties/meterDetails expansion, encoded keys, no date clause | 400; **required usage date range**, not blanket offer rejection |
| WSL MSDN Consumption | 2019-10-01 / empty collection | RG + usageStart/usageEnd, 2026-10-14..15 | **200**, 0 rows, no continuation |
| WSL MSDN Consumption | 2024-08-01 / empty collection | same valid past usageStart/usageEnd range | **200**, 0 rows, no continuation |

One Windows Query attempt was HTTP 429 and was not treated as empty data; a
later bounded invocation succeeded. Initial far-future Query controls returned
400 (do not use those as cost-permission failures). Initial CLI plumbing errors
were fixed before the successful runs; failed metadata is not access proof.
Safe per-invocation metadata remains in ignored `private\cost-probe-*.json`.

**Corrected MSDN interpretation:** later requests captured the actionable error
instead of inferring eligibility from a broad message category. Without dates,
the API says: "Billing Period is not supported in (2024-08-01) API Version for
Subscription Scope With Web Direct Offer. Please provide the UsageStart and
UsageEnd dates in the $filter key as parameters." With a future range, it says:
"Invalid date. Start date (UTC): 2099-01-01 cannot be set in the future".
Both tested API versions returned HTTP 200 for the valid past range. Empty
responses establish access, not the returned schema or filter compliance.
The classifier now gives these date constraints priority over the word "Offer".

**Narrow conclusion:** the tested Windows subscription, API version and modern
schema returned a record violating the RG predicate even with an RG-only
request. Changing dollar-key encoding and modern date syntax did not produce
a scoped response in the tested combinations. These are **not** a full factorial
encoding test, proof all date filters fail, or proof WSL ignored any filter.
Unknown/unsupported syntax must not be conflated with ignored supported syntax.

## Documentation versus observation / route selection

Official references verified 2026-10-15:

1. [Usage Details List 2024-08-01](https://learn.microsoft.com/en-us/rest/api/consumption/usage-details/list?view=rest-consumption-2024-08-01):
   documents RG/resourceId/resourceName and selected other filters; supports
   eq/lt/gt/le/ge/and, **not ne/or/not**. Expansion is properties/meterDetails.
   The list parameter table does not document properties/date. Our modern-date
   attempt is exploratory, not a recommended supported request.
2. [Legacy PAYG/Visual Studio instructions](https://learn.microsoft.com/en-us/azure/cost-management-billing/automate/get-usage-details-legacy-customer):
   explicitly exemplifies usageStart/usageEnd with `2019-10-01` for PAYG; these
   request dates refer to **billing receipt**, not necessarily usage date.
   Carrying those predicates to a modern 2024 schema is not proof of support.
   Exports are recommended for MOSP/Visual Studio; Consumption remains the
   small-dataset option, deprecated for other offers. Unsupported offers can
   still reject it; however, the observed WSL responses here required valid
   explicit dates and were resolved without changing the authenticated offer.
3. [Cost Details instructions](https://learn.microsoft.com/en-us/azure/cost-management-billing/automate/get-small-usage-datasets-on-demand):
   report available to **EA/MCA**, not MSDN/PAYG/Visual Studio. Requires cost-read
   permissions at supported scope and applicable billing visibility policies;
   Resource Contributor alone is not proof of billing visibility.
4. [Query contract](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2023-11-01):
   aggregate Cost Analysis route, not a replacement for meter quantity/rate detail.
5. [Cost data timing and credits](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data):
   daily/offer-dependent delay, credit semantics and currency require explicit
   interpretation; HTTP 200/empty/zero cost never establishes free traffic.

EA/MCA asynchronous route (now implemented by the public `cost-details` command):
POST `/subscriptions/{sub}/providers/Microsoft.CostManagement/generateCostDetailsReport?api-version=2025-03-01`
with `{"metric":"ActualCost","timePeriod":{"start":"<day>","end":"<day>"}}`.
202 requires bounded Location polling honoring Retry-After, then downloading
**all** manifest blobs before expiry, checking partition count/bytes and applying
lab/date predicates before retention. SAS links are secrets, not evidence URLs.
The results Location can include the complete opaque signed query tuple
`t`, `c`, `s`, `h` alongside `api-version`; requiring only `api-version` rejected
the prior working Azure response shape before polling. The validator now accepts
that bounded tuple only for `costDetailsOperationResults/{operation-uuid}` at the
exact subscription, HTTPS management host and report API version. It rejects
unknown/duplicate/blank parameters, malformed identifiers and cross-scope paths.
Location values remain memory-only and must not be logged. This URL-validation
revision passes offline fixtures, not a new live Cost Details/CSV validation;
independent live revalidation requires approval.
The earlier `2022-05-01` documentation-only investigation did not generate a
report. The later private 2025-version runs above did; this public CLI change
was tested offline only. Exports still require a separately approved
export/storage mutation; none is created by these scripts.

Legacy details normalize usageStart/instanceId/usageQuantity/pretaxCost and
meterDetails; modern details normalize date/instanceName/quantity/unitOfMeasure/
costInBillingCurrency. Missing prices stay null. Received-date filters can omit
late records: rerun bounded adjacent receipt windows as authorized, then retain
only actual experiment usage days. Full billing grade still needs a mature,
attributable positive control, complete pages and quantity/rate provenance.
Use the existing 24/48/72h and day-7 schedule; no running VM waits for billing.
These are follow-up targets, **not automatic jobs**; none is established.
The pricing FAQ addresses same-region Azure services, not explicit tenant
boundaries. Preserve the official
[BYOIP destination Internet-egress exception](https://learn.microsoft.com/azure/virtual-network/ip-services/custom-ip-address-prefix#pricing);
empty cost output cannot establish a broader exemption.

### 18 October 422 on T Cost Details generation — cause unknown

[The manual result](../results/2026-10-18-manual-billing-011054.json) records
**T** failing `cost-details` with `reason: "http_error"`, `httpStatus: 422`,
`azureCode: "422"` and no retained `errorCategory` or service message.
**The HTTP 422 is observed; its exact cause is UNKNOWN.** The numeric
`azureCode` does not explain the rejection. A safe classifier category could
help triage, but would not itself be the raw service explanation.
`offerContextAlias: "native-wsl-msdn"` is an alias, not verified agreement or
offer classification. The [documented EA/MCA-only Cost Details restriction](https://learn.microsoft.com/en-us/azure/cost-management-billing/automate/get-small-usage-datasets-on-demand)
makes legacy MOSP/Visual Studio compatibility a **plausible restriction if T's
actual offer type is verified**, not an established or sole cause of this 422.

[The independent Query result](../results/2026-10-18-query-alternative-011707.json)
records T's HTTP 200 and EUR 0.165150215302437 for 17 October. It establishes
working authorization for that Query operation, **not** Cost Details permission,
offer eligibility or acceptance of the report date range. The local
`future_report_date` guard rejects future **calendar dates** only: ending on
18 October, then the current UTC date, passes that guard but does not rule out
backend reporting-period constraints. Neither Query success nor this guard
establishes the cause of the report failure.

**A** independently timed out (`http_timeout`, null HTTP status/code); no
response was recorded. A bounded asynchronous report retry is reasonable
because the historical C report succeeded on the same verified subscription
and tenant as canonical A, not because A's alias proves an agreement type.
That precedent does not guarantee A's next request or date window will succeed.
For T, prefer the previously successful date-bounded Consumption route
(`details --filter-variant legacy-date`) over unbounded identical 422 retries.
The prior valid-past-date HTTP 200 responses demonstrate that explicit
UsageStart/UsageEnd resolved those Consumption date errors, **not** blanket
offer rejection or guaranteed detail availability.

For the next authorized scheduled collection only, this bounded legacy command
uses T's canonical context and inventory (PowerShell, repository root):

```powershell
$ctxPath = 'labs\azure-bandwidth-billing\private\large-rerun-deploy-20261016T112400Z\aligned\t-context.private.json'
$inventory = 'labs\azure-bandwidth-billing\private\large-rerun-deploy-20261016T112400Z\aligned\t-inventory.private.json'
$ctx = Get-Content -LiteralPath $ctxPath -Raw | ConvertFrom-Json
$stamp = [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
python labs\azure-bandwidth-billing\costs\cost_api.py details `
  --transport native --context $ctxPath --inventory $inventory --resource-group $ctx.resourceGroup `
  --start 2026-10-15 --end 2026-10-18 --filter-variant legacy-date `
  --max-pages 1 --max-http-requests 1 --max-retries 0 --max-seconds 75 `
  --output "labs\azure-bandwidth-billing\private\reports\t-legacy-details-$stamp.json"
```

Receipt-window predicates do not replace mandatory local exact inventory/RG
and **actual usage-date** filtering before persistence; inspect normalized
actual dates. A remaining continuation means INCOMPLETE, not zero usage.
The shared manual budget is exhausted (**6/6**); this revision makes no calls.
Keep the existing schedule and honor Retry-After and authorized budgets.
A fresh Query comparison with the 01:21:11Z baseline cannot be six hours apart
before **18 October 07:21:11.187291Z**, even if the scheduled job runs around
05:02Z; elapsed time alone still does not establish completeness or maturity.

## WSL deployment readiness and approved incremental cost

This section records deployment approval/budget provenance, not current traffic
status. The later 15 October A/T test consumed T's approved **10 GiB payload**
reserve. No additional T payload is approved; $8 core/$4 extension caps have
not increased. The initial infrastructure-only lease did not run traffic.

**Billing access prerequisite passed:** a separate enabled subscription and
tenant were verified in-memory; Query and date-bounded Consumption requests
work. Actual detailed bandwidth rows/schema/attribution still need a mature
positive control; exact agreement classification is not established. The
initial optional CLI Sweden Central SKU lookup timed out. The deployment owner
subsequently passed the alternative direct ARM resourceSkus catalog in MSDN
(one page), confirmed Compute/Network already registered, and passed ARM
validation and **actual allocation** on 2026-10-15. No registration or
authentication state changed. The created **Standard_B1s** endpoint T was
verified deallocated at **08:22:55Z**, with six owned resources retained.
Separate live quota enumeration was not needed: successful allocation is the
authoritative result. See [deployment log](../msdn-deployment-log.md).
Jose's **additional $4** approval covers this endpoint's incremental envelope;
the later bounded traffic used its existing approved reserve, not a new budget.

Approved expansion is **additional to**, not silently inside, the approved $8
core: one Sweden Central Linux Standard_B1s (1 GiB; same verified hourly rate
as the proposed Standard_B2ts_v2), 30 GiB Standard SSD
(32 GiB E4 billing tier), NIC, NSG, Standard IPv4 PIP, VNet and dedicated RG.
Target <=4 allocated hours, hard <=12 total; disk/PIP/resource lifetime <=72h.
The originally optional <=5 GiB each direction test was subsequently completed
on 15 October. **No test was run under the deployment lease described here.**

Public [Retail Prices API](https://prices.azure.com/api/retail/prices) reads on
2026-10-15, USD, Sweden Central, Consumption prices, no continuation:

| Component / precise retail selector | Rate | Maximum planned extension |
|---|---:|---:|
| Virtual Machines Bsv2 Series / B2ts v2, not Cloud Services/Windows/Spot | $0.0108/hour | 12h = $0.1296 |
| Actual VM alternative: Virtual Machines BS Series / Standard_B1s, same exclusions | $0.0108/hour | replaces, does not add to, the VM line above |
| Standard SSD Managed Disks / E4 LRS Disk | $2.40/month | 72h / 730h convention = $0.2368 |
| IP Addresses / Standard IPv4 Static Public IP (not prefix/global) | $0.005/hour | 72h = $0.36 |
| NIC, NSG, VNet, RG | no planned hourly rent | $0; exclude optional paid features |
| Conservative traffic reserve, **not a quoted tariff** | $0.20/decimal GB x 10.73741824 GB | $2.1475 |
| Disk operations + contingency | planning reserve | $0.95 |
| **Approved incremental envelope** | excludes tax/credits | **$3.83, <=$4** |

Retail requests filter armRegionName=swedencentral, priceType=Consumption, and
armSkuName=Standard_B2ts_v2 or Standard_B1s / Storage+meterName=E4 LRS Disk /
Virtual Network, then select the exact products above. These are reproducible
public list-price estimates, not account effective rates. Month proration is an
estimate. Stop if actual applicable tariffs, operations or lifetime exceed the
envelope; do not silently substitute a larger SKU or add a paid gateway.

## Historical follow-up command examples

**Superseded date window:** the October-15-only examples below document the
earlier plan, not the active six-hour follow-up. Current collection must retain
October 15–16 separately, use Query October 15 midnight through now, and
preserve source dates and optional usage intervals. Do not run the date-only
CLI examples with a future end-of-day boundary. Billing remains waiting for
scale-confirmed control metering; both stable snapshots must be at/after
**16 October 23:15:33Z**, at least six hours apart, within the existing hard stop.

**Not executed by this offline publication.** Acquire a fresh approved bounded
read-only API lease in the collector's existing runtime-control location first;
the transfer/validation leases are completed and cannot authorize these commands.
Do not bypass the collector's lease checks or reuse the validation owner's
in-memory lease bridge. No auth/profile switching, packages or export resources
are needed. Substitute absolute Windows paths under this lab's ignored private
tree for contexts and **new** output files; use each native source's own context.
Placeholders contain no identities or endpoint addresses.

Run each native-source Query once per due collection, not repeatedly on 429.
The existing collector's bounded short Retry-After handling remains unchanged.
Set `$stamp` to the due collection date, not the usage date. At the earliest
follow-up, **2026-10-16T10:40:28Z**, the entire requested usage day is in the past:

```powershell
$stamp = '20261016-24h' # later: 20261017-48h, 20261018-72h, 20261022-day7
$windowsContext = '<ABSOLUTE_WINDOWS_PRIVATE_CONTEXT>'
$wslContext = '<ABSOLUTE_WSL_PRIVATE_CONTEXT>'
$privateOutput = '<ABSOLUTE_LAB_PRIVATE_COST_DIRECTORY>'
$aLabRg = '<A_LAB_RG>'
$tLabRg = '<T_LAB_RG>'

python labs\azure-bandwidth-billing\costs\cost_api.py query --context $windowsContext --resource-group $aLabRg --start 2026-10-15 --end 2026-10-15 --grouping Meter --meter-category Bandwidth --max-pages 3 --max-seconds 75 --offer-alias windows-main --output "$privateOutput\$stamp-windows-bandwidth.private.json"
python labs\azure-bandwidth-billing\costs\cost_api.py query --transport wsl --distribution Ubuntu-24.04 --context $wslContext --resource-group $tLabRg --start 2026-10-15 --end 2026-10-15 --grouping Meter --meter-category Bandwidth --max-pages 3 --max-seconds 75 --offer-alias wsl-msdn --output "$privateOutput\$stamp-wsl-bandwidth.private.json"
```

Due times are **16/17/18 October 10:40:28Z** and, if needed, **22 October
10:40:28Z**. Date-only CLI inputs become the Query daily envelope
2026-10-15T00:00:00Z–2026-10-15T23:59:59Z; never substitute the ingestion day.
The WSL dispatch converts private Windows paths and uses native Linux CLI/tokens.
Read columns by name and check all pages; COMPLETE is pagination completeness,
not billing maturity. Retain 429 metadata as error, not empty/zero.

The successful control's separate 24/48/72h targets are **16/17/18 October
23:15:33Z**. Use C's private historical RG/inventory with the same
**2026-10-15 actual usage day** and distinct filenames; coalesce due daily
snapshots where appropriate, never sum cumulative snapshots. No extra transfer
is required. Its 1 GiB is **1.073741824 decimal GB**, ~$0.0214748 before
overhead at Europe's $0.02/GB **planning** rate, not actual quantity/rate/cost.

When separately authorized to obtain detail, retain the historical inventory
projection after cleanup and use valid **past** receipt-date coverage. For
example, at/after the 17 October 48h follow-up, this bounded request examines
15–16 October receipt coverage (not a guarantee all late 15 October usage is
present):

```powershell
$windowsInventory = '<ABSOLUTE_WINDOWS_PRIVATE_HISTORICAL_INVENTORY_PROJECTION>'
python labs\azure-bandwidth-billing\costs\cost_api.py details --context $windowsContext --inventory $windowsInventory --resource-group $aLabRg --start 2026-10-15 --end 2026-10-16 --filter-variant legacy-date --max-pages 3 --max-seconds 75 --offer-alias windows-main --output "$privateOutput\$stamp-windows-details.private.json"
```

For T use the analogous command with `--transport wsl --distribution Ubuntu-24.04`,
its own context, RG, inventory and a distinct output. Both tested Consumption
versions accepted valid past ranges in MSDN; errors about missing/future dates
were not blanket offer rejection. Inspect normalized **actual usage UTC** and
request further past receipt windows only under the collection lease if needed.
Windows server RG filtering was observed to return unrelated rows: local
inventory/RG/date filtering **before persistence is mandatory**. A remaining
nextLink at a bound is INCOMPLETE, never zero. No cumulative snapshots are summed.
Meter Query costs lack quantity/unit/effective-rate proof; credits and allowances
cannot prove no charge. Require mature same-offer/feed known-charge positive
control plus detail before a scoped no-charge-observed conclusion.
Require two stable future cumulative snapshots, **both at/after 16 October
23:15:33Z**, with comparable A/T coverage and the scale-confirmed charged C
control. That supports a scoped **no additional charge observed** finding,
not a zero-rated-meter claim or final invoice proof. Twenty-four hours and
stability alone do not guarantee ingestion completeness.

Collections did not delay known-owned deletion: cleanup closed
**16 October 00:00:11.806224Z**, ahead of original **18 October 07:33Z**
core / **08:20:59Z** T cutoffs. All known lab VMs/disks/PIPs are gone;
the core RG and one NSG of unproven creation ownership remain preserved,
not adopted/deleted. Historical IDs are retained privately for **all**
future collections. The control's 72h target, **18 October 23:15:33Z**,
is after the original TTL deadline.
See the [control and cleanup result](../results/2026-10-15-cross-region-control.md).
The earlier plan established no automatic job; the current read-only collection
schedule is described above. No automatic cleanup job is established. No extra-cost scope or
additional MSDN payload is approved. The reconciled 5 GiB pre-v4 allowance
minus its 2 GiB wire reservation leaves **3 GiB**, not actual payload use or
permission for another transfer. The $8/$4 caps are not actual bills.
