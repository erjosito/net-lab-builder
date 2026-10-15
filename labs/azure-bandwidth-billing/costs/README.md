# Reproducible Cost Analysis API deliverable

Read-only Python 3 standard-library collector, tested 2026-10-15. This is a
first-class lab outcome: discover which cost API works for each authenticated
offer, test its filters, and collect attributable bandwidth meters without
retaining other resources' bills. It is **not a bandwidth billing result**.

## Executables and privacy contract

- `cost_api.py`: `probe`, daily aggregate `query`, and normalized Consumption
  `details`. `cost-details` explicitly returns an unsupported-interface error;
  it never silently substitutes another API or starts an asynchronous report.
- `preflight_compare.py`: bounded, repeatable Windows/native-Linux comparison,
  and optional provider/catalogue preflight. Requires this lab's active API lease.
- `test_cost_api.py`: offline fixtures/mocked HTTP; no Azure access or dependencies.

Current validation: **12 contract tests passed on Windows and native Ubuntu-24.04
Python**, including date-error classification, filtering, Decimal/units, name resolution, reordered Query
columns, exact continuation semantics, duplicate identities, truncation,
timeouts/HTTP errors, context pinning and snapshot overwrite rejection.

Only the following source artifacts belong to this tooling: these three Python
files and this README. Runtime context, inventories and snapshots must be under
the existing ignored `private` directory. Never track their contents. No tokens,
raw API error messages, billing URLs, continuations or SAS URLs are saved.
The collector retains a normalized projection and source-record hash, **not**
the full raw lab row (which could contain opaque URLs/additional information).
Snapshot filenames must be new: successive cumulative reports are never appended.
Do not concatenate snapshots or deduplicate merely similar-looking line items.

Each HTTP action checks expected subscription/tenant against the native CLI,
requests a subscription-pinned ARM token in that environment, and keeps it in
memory. Azure CLI rejects simultaneous subscription and tenant parameters on
`get-access-token`; the tool verifies both fields on its response instead.
Windows uses the installed CLI's Python entry point with argv, not `az.cmd`
shell quoting. WSL dispatch runs the same source using Linux `python3` and Linux
`az`, with a bounded GNU `timeout` process group. Tokens never cross profiles.
No login, account switching, configuration, extension or provider changes.

HTTP socket timeout <=20s with a deadline check between bounded reads; CLI <=15s;
invocation defaults to 75s (max 90s), 3 pages
(max 20), <=8 MiB/page. A 429 is retried only once when numeric Retry-After <=2s
fits the deadline; otherwise return rate-limited, not a background wait.
Redirects are rejected. Continuations must match HTTPS ARM, exact subscription
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

## WSL deployment readiness and approved incremental cost

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
Jose's **additional $4** approval was consumed for this endpoint, not traffic.

Approved expansion is **additional to**, not silently inside, the approved $8
core: one Sweden Central Linux Standard_B1s (1 GiB; same verified hourly rate
as the proposed Standard_B2ts_v2), 30 GiB Standard SSD
(32 GiB E4 billing tier), NIC, NSG, Standard IPv4 PIP, VNet and dedicated RG.
Target <=4 allocated hours, hard <=12 total; disk/PIP/resource lifetime <=72h.
One optional future test: <=5 GiB each direction. **No test was run here.**

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
