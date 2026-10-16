# Reproducible Cost Analysis API deliverable

Read-only Python 3 standard-library collector, tested 2026-10-15. This is a
first-class lab outcome: discover which cost API works for each authenticated
offer, test its filters, and collect attributable bandwidth meters without
retaining other resources' bills. API access is **not a bandwidth billing
verdict**. The later [completed A/T transport](../results/2026-10-15-cross-tenant-public-ip.md)
has initial billing **INCONCLUSIVE**: Windows HTTP 200 COMPLETE empty versus
WSL HTTP 429 rate_limited ERROR, not two successful empty snapshots.

**Current status, 2026-10-16 UTC:** [C → B v4](../results/2026-10-15-cross-region-control.md)
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

**00:29Z live CSV schema validation:** one fresh ActualCost report for October
15–16 receipts completed (POST 202, poll 200, download 200; **three HTTP requests,
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

- `cost_api.py`: `probe`, daily aggregate `query`, and normalized Consumption
  `details`. `cost-details` explicitly returns an unsupported-interface error;
  it never silently substitutes another API or starts an asynchronous report.
- `preflight_compare.py`: bounded, repeatable Windows/native-Linux comparison,
  and optional provider/catalogue preflight. Requires this lab's active API lease.
- `test_cost_api.py`: offline fixtures/mocked HTTP; no Azure access or dependencies.
- `cost_details_csv` in `cost_api.py`: pure memory-only Cost Details CSV
  projection, accepting documented ResourceId/InstanceId and case variants,
  preserving decimals/nulls, filtering inventory/RG/date before retention.
  This helper does **not** implement the CLI's asynchronous `cost-details`
  command. `cost_details_csv_stream` also bounds downloaded/decompressed bytes,
  supports one CSV ZIP member or gzip, captures safe headers before schema
  validation, and requires exact Bandwidth category/service matching.
  The fresh 00:29Z report successfully exercised the actual mixed-case schema;
  the earlier discarded report was not reconstructed.

Current validation: **21 contract tests passed on Windows** (the original 12
also previously passed on native Ubuntu-24.04 Python), including date-error classification, filtering, Decimal/units, name resolution, reordered Query
columns, exact continuation semantics, duplicate identities, truncation,
timeouts/HTTP errors, context pinning, snapshot overwrite rejection, in-memory
token expiry/clock guards, and CSV schema/privacy/row-limit fixtures.

Only the following source artifacts belong to this tooling: these three Python
files and this README. Runtime context, inventories and snapshots must be under
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
75-second collection deadline or turn incomplete pagination into success.
No token is persisted or transferred between environments. Azure CLI rejects simultaneous subscription and tenant parameters on
`get-access-token`; the tool verifies both fields on its response instead.
Windows uses the installed CLI's Python entry point with argv, not `az.cmd`
shell quoting. WSL dispatch runs the same source using Linux `python3` and Linux
`az`, with a bounded GNU `timeout` process group. Tokens never cross profiles.
No login, account switching, configuration, extension or provider changes.

HTTP socket timeout <=20s with a deadline check between bounded reads; CLI <=15s;
invocation defaults to 75s (max 90s), 3 pages
(max 20), <=8 MiB/page. A 429 is retried only once when numeric Retry-After <=2s
fits the deadline; otherwise return rate-limited, not a background wait.
Redirects are rejected. Continuations must contain no raw whitespace/control
characters and must match HTTPS ARM, exact subscription
and API operation path/version; Query repeats POST with the original body,
Consumption follows the original nextLink GET without reconstructing its token.
Page limits, cycles, unattributed lab rows and elapsed/error exits cannot be
reported as a complete successful collection. `COMPLETE` means the requested
snapshot reached its final page, **not** that delayed billing is final.

## Commands (PowerShell, from repository root)

An owner must open a fresh bounded read-only API lease before live commands.
Use existing private contexts or supply `--subscription <id>
--expected-tenant <id>` privately at runtime. Context shape:
`{"subscriptionId":"<private>","expectedTenantId":"<private>"}`.

```powershell
python -m unittest discover -s labs\azure-bandwidth-billing\costs -p test_cost_api.py -v

python labs\azure-bandwidth-billing\costs\preflight_compare.py --environment windows --variant rg-only --output <absolute-lab-private-new-file>
python labs\azure-bandwidth-billing\costs\preflight_compare.py --environment wsl --variant legacy-date --start 2026-10-14 --literal-keys --output <absolute-lab-private-new-file>

python labs\azure-bandwidth-billing\costs\cost_api.py query --context <absolute-lab-private-context> --resource-group <lab-rg> --start 2026-10-15 --end 2026-10-15 --grouping Meter --meter-category Bandwidth --output <absolute-lab-private-new-snapshot>

python labs\azure-bandwidth-billing\costs\cost_api.py details --context <absolute-lab-private-context> --inventory <absolute-lab-private-inventory> --resource-group <lab-rg> --start 2026-10-15 --end 2026-10-15 --max-pages 3 --output <absolute-lab-private-new-snapshot>
```

Add `--transport wsl --distribution Ubuntu-24.04` to `cost_api.py` for native WSL
execution; use the **WSL** private context, never the Windows subscription.
Windows paths must be absolute for WSL dispatch; conversion uses the standard
`/mnt/<drive>` mount. Native Linux execution accepts its Linux paths directly.
WSL discovery in `preflight_compare.py` reads its existing default once, verifies
different tenant **and** subscription from Windows privately, then pins every
subsequent action. Its ignored `wsl-cost-context.private.json` is session context,
not durable authentication or a promise the next session remains signed in.

Inventory input is deliberately narrow:
`{"resourceIds":["<exact VM/NIC/PIP/other lab ARM id>", "..."]}`. Capture all owned
historical IDs before deletion/replacement; the existing deployment inventory
needs an explicit projection to this format. Unknown IDs are discarded.
Modern `instanceName` is accepted as an ID only if canonical; a bare name needs
matching lab RG plus exactly one matching inventory name. Ambiguous names,
wrong RG/subscription, unknown resources, missing dates and wrong usage days
never get saved. Lab rows lacking attribution force INCOMPLETE. Non-lab rows
are discarded in memory; no automatic broad/unfiltered fallback.

### Query dimensions and quantities

Query version `2023-11-01` uses ActualCost, Daily, Sum(PreTaxCost) and an explicit
ResourceGroup dimension filter. Collection groups by ResourceGroup plus one of
`MeterId`, `Meter` or `MeterCategory`. `--grouping none` is probe-only.
The default is the successfully tested `Meter`, not the rejected `MeterId`.
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
sum is requested: it could mix GB, hours and operations. Details retain decimal
quantity, raw unit, effective/unit price (null if missing), meter, currency,
cost, actual usage day and private resource identity. Never infer price=0 from
missing fields or cost=0 from credits/free tier. 5 GiB is 5.36870912 decimal GB.
Reconcile only like meter/unit/currency/day/rate groups.

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

EA/MCA asynchronous route (documented, intentionally **not implemented/invoked**):
POST `/subscriptions/{sub}/providers/Microsoft.CostManagement/generateCostDetailsReport?api-version=2022-05-01`
with `{"metric":"ActualCost","timePeriod":{"start":"<day>","end":"<day>"}}`.
202 requires bounded Location polling honoring Retry-After, then downloading
**all** manifest blobs before expiry, checking partition count/bytes and applying
lab/date predicates before retention. SAS links are secrets, not evidence URLs.
No report generation happened here. Exports also require a separately approved
export/storage mutation; none was created.

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

## Dated follow-up commands for the completed run

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
No automatic collection or cleanup job is established. No extra-cost scope or
additional MSDN payload is approved. The reconciled 5 GiB pre-v4 allowance
minus its 2 GiB wire reservation leaves **3 GiB**, not actual payload use or
permission for another transfer. The $8/$4 caps are not actual bills.
