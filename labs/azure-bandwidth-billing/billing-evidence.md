# Billing extraction and reconciliation plan

Reconciliation design plus [executable collectors and tested API matrix](costs/README.md).
Current experimental billing verdict: **INCONCLUSIVE** after completed
same-region cross-tenant transport; no unrelated billing values retained.
Updated 2026-10-16 UTC. See the [sanitized result](results/2026-10-15-cross-tenant-public-ip.md).
The [21:36Z interpretation](results/2026-10-15-billing-verdict.md) separates the
practical published-pricing answer (no tenant-boundary surcharge expected for
ordinary same-region Azure endpoints) from incomplete empirical invoice proof.
The historical Query's three returned bandwidth rows are tiny positive USD
costs, all attributed to A by a complete ResourceId+Meter Query; those Query
rows report no quantity, unit or rate. The latest CSV does report those fields,
but not a scale-confirmed intraregional 5 GiB meter.
“Intra Continent” is not “intra region.”
**Current check, 16 October 06:50:38Z:** the
[sanitized Query/CSV snapshot](results/2026-10-16-billing-check-0650.json)
reports C's **16 October** quantity **0.6551259830594063 “1 GB”** at
**USD 0.02**, cost **USD 0.013102519661188125**, on **Intra Continent Data
Transfer Out**. C's separate **15 October** row is **0.000002402812242508
“1 GB”**, cost **USD 4.80562448501586884E-8**. This is substantial
bulk-sized-control evidence, **not a full quantity reconciliation** to the
1-GiB transfer on 15 October 23:08–23:15Z. Partial ingestion is not proven:
unit/coverage/attribution differences remain possible. Ingestion watermark,
end-boundary inclusivity and day completeness are unknown; report dates are
not receipt dates or exact request correlation.

Both daily ActualCost Queries completed, from 15 October through the actual
16 October 06:48Z request cutoffs; fresh Cost Details requested 15–16 October
and retained seven Bandwidth rows. Exact historical VM attribution is **A: 3,
B: 2, C: 2**, not five A rows; original A-group scope has five, C scope two.
T's complete Query now returns one 15-October **EUR 7.4561667E-8** microcost
row, no quantity/unit/rate; none were inferred. No headline-scale A/T charge
is established. Five of six allowed HTTP requests, zero retries/mutations,
contexts unchanged, lease closed, native children idle. **INCONCLUSIVE** after
about 7.5 hours: six-hour read-only follow-up remains active, next around
**12:50Z**, with two stable comparable snapshots at least six hours apart
after the **16 October 23:15:33Z** control maturity threshold. Deleted owned
assets are not retained for billing; late-arriving usage is not continuing rent.

Historical live CSV extraction closed **16 October 00:29:24Z**:
one generation, one poll and one streaming download; three HTTP requests, no
retries/mutations. Actual mixed-case header mapping is now live-validated:
`ResourceId` / `resourceGroupName` / `date` / `quantity` / `unitOfMeasure` /
`effectivePrice` / `costInBillingCurrency` / `billingCurrency`.
The report requested October 15–16; only exact owned October-15
Bandwidth rows survive. Six rows retained (C: one; A source: three; B in original
A group: two), 365 discarded before retention. C's actual quantity is
**0.000002291053533554 “1 GB”**, effective price **USD 0.02**, cost
**USD 4.58210706710815400000E-8**—not a scale-confirmed 1-GiB control.
A's source-VM quantities/rates are **0.000966296531260014 / 0.05**,
**0.000003241002559662 / 0.02**, and **0.000295128673315048 / 0.083**;
all units are reported “1 GB”, rates in USD. No division by expected traffic
or default-zero fields was used. That snapshot's latest owned usage date is October 15 only;
date-only coverage cannot establish completeness. ActualCost reporting is not
a final invoice. **Remaining blocker: billing maturity and transfer attribution**;
T was not refreshed. Context/default-profile bytes unchanged, lease closed/idle,
zero owned native children. Snapshots supersede comparisons; never add them.

Historical quantity-source investigation closed **16 October 00:21Z**:
C's isolated daily Query now returns one tiny positive row, **USD
0.0000000458210706710815**, without quantity/unit/rate. Modern Cost Details
generation/poll/download succeeded, but the runtime CSV schema check rejected
the memory-only report before any rows were retained. The exact header was
not retained; offline case/alias parser improvements are not live extraction
proof. A/T were not refreshed and their prior snapshot is unchanged.
See [reconciliation](results/2026-10-16-usage-reconciliation.json).
That phase exhausted its 12 request reservations (11 reached HTTP, one invalid
continuation failed before HTTP); the 00:29Z validation used its own new lease.
Live lease is closed/idle with zero owned native children and zero mutations.

The prior bounded billing refresh was **15 October 23:28Z**, after
[C → B v4 transport/restoration PASS](results/2026-10-15-cross-region-control.md):
**1 GiB, one upload, zero retries**. The earlier v1/v2/v3 history is unchanged.
Read-only v3 inspection identified B's additional subnet NSG default deny
65500, missed by NIC-only setup; v4 corrected/restored both layers.
Independent validation PASS used **11 reads / zero mutations**, closing
**23:25:22Z**. Successful expected-charged transport is **not yet a billed
positive control**: three billing requests still returned only A's three tiny
daily rows, C no Query rows/details timeout, T empty. No quantity/unit/rate,
per-request attribution or zero-dollar proof exists.
Known-owned cleanup closed PASS **16 October 00:00:11.806224Z**: 13 remaining
original core assets absent, C/T groups gone, all known VMs/disks/PIPs deleted.
**Core RG and one extra NSG were preserved**, independent creation ownership
unproven; no standalone RG/NSG hourly rent, no authority to adopt/delete.
Use **ActualCost** consistently, not AmortizedCost: this experiment measures
consumed bandwidth and its actual meter economics, not reservation allocation.
PAYG Ubuntu avoids new reservation purchases. Existing discounts/credits still
require explicit interpretation. Never merge actual and amortized rows.

## Prerequisite decision tree

1. Privately discover subscription and tenant IDs; pin every CLI invocation with
   `--subscription`. Determine actual agreement/offer from authorized billing
   scope or owner confirmation, not subscription display name or `quotaId` alone.
2. Check Cost Management Reader or equivalent cost-read access, plus applicable
   EA/MCA cost-visibility policy. Resource Reader/Contributor does not establish
   billing access. Cross-tenant tests need visibility on both outbound producers.
3. Query a one-day **lab-filtered** tiny aggregate first. Before creation, use a
   deliberately nonexistent lab RG, never enumerate other resources' usage.
   HTTP success with empty rows proves only this Query permission/request works.
4. **EA/MCA:** use Cost Details report API, one UTC day per request, ActualCost.
   **MOSP/PAYG/MSDN/Visual Studio:** verify exact offer; use supported Consumption
   Usage Details API or portal usage CSV. Exports are recommended by Microsoft
   for supported offers but creating export/storage is a mutation requiring
   separate approval. Do not assume modern Cost Details supports MSDN.
5. Demonstrate a details schema that includes meter quantity/unit and usable
   attribution. A pre-run empty lab has no sample bandwidth row: verify API
   access and schema contract without harvesting unrelated resource billing.
   The first mature cross-region control must validate actual meter visibility.
6. If only aggregate Query is available, agree evidence-grade limitations before
   spend. If a strong billing verdict is required, missing detail access is a
   **BLOCKED prerequisite**, not a reason to run and claim zero charges later.

Current billing-access prerequisite **PASS**: lab-filtered Query and modern
Consumption Usage Details schema access succeeded; see [preflight.md](preflight.md).
These are permission/schema checks, **not lab usage or charge results**.
The tested server RG filter was not honored. Future collectors must apply the
private lab inventory/RG and actual usage-date checks **before persisting any
row**, discard non-lab data in memory, and bound/verify pagination completeness.
No billing request was made during the D0 infrastructure deployment lease.

## API contracts and implemented read-only collector

`costs\cost_api.py` implements bounded Query and Consumption collection with
offline contract tests and a pure in-memory Cost Details CSV projection helper.
The CLI's Cost Details asynchronous command remains explicitly unimplemented,
not a success-shaped fallback; the 16 October private runtime separately
verified live report generation/download/projection at 00:29Z. The discarded
00:21Z report itself was not reparsed.
Windows modern Consumption failed
the tested RG predicates. Earlier WSL Consumption 400s were resolved by
valid explicit past usageStart/usageEnd ranges: **2019-10-01 and 2024-08-01
both returned HTTP 200 empty**. Missing/future-date errors do not establish
blanket offer rejection. See the tested matrix for exact syntax, encoding and limits.
The executable keeps only normalized lab fields and a source-record hash;
it intentionally does not retain full raw rows containing opaque metadata.

Use placeholders resolved in the private run map; no subscription IDs in tracked
artifacts. ARM host is `https://management.azure.com`.

### A. Cost Management Query: aggregate fallback

`POST /subscriptions/{sub}/providers/Microsoft.CostManagement/query?api-version=2023-11-01`

```json
{
  "type": "ActualCost",
  "timeframe": "Custom",
  "timePeriod": {"from": "{day}T00:00:00Z", "to": "{day}T23:59:59Z"},
  "dataset": {
    "granularity": "Daily",
    "aggregation": {"totalCost": {"name": "PreTaxCost", "function": "Sum"}},
    "filter": {
      "dimensions": {
        "name": "ResourceGroup", "operator": "In",
        "values": ["{created-lab-rg-or-preflight-nonexistent-rg}"]
      }
    },
    "grouping": [
      {"type": "Dimension", "name": "ResourceId"},
      {"type": "Dimension", "name": "Meter"}
    ]
  }
}
```

For the initial permission smoke-test omit grouping. The executable collector
uses **ResourceGroup + Meter**, which passed live tests; **MeterId returned
HTTP 400**. The illustrative ResourceId grouping above is not the implemented
collector request or a newly validated dimension. At collection, discover
supported grouping/aggregation dimensions using the API contract/dimensions
endpoint; if `Meter` is unavailable use supported meter category/subcategory.
Honor Query's group-count limits; run separately filtered queries to refine.
Do not assume Query exposes MeterId, quantity, unit or effective price. If
`UsageQuantity` aggregation is supported, request only a single compatible
meter/unit; never sum mixed units. Parse `properties.columns` by **name**, not
positional assumptions. Persist column definitions and currency with rows.
Follow `properties.nextLink` until null, preserving POST/body semantics required
by the Query API. Empty rows do not prove no metering.

### B. EA/MCA detailed report

`POST /subscriptions/{sub}/providers/Microsoft.CostManagement/generateCostDetailsReport?api-version=2022-05-01`

```json
{"metric":"ActualCost","timePeriod":{"start":"{day}","end":"{day}"}}
```

Use a one-day range according to the endpoint's date semantics; verify returned
usage dates and expand boundary dates if needed. A date-limited report may
contain records received by billing during that interval: **request date is not
necessarily usage date**. Inspect row usage interval/date and rerun D-1..D+1
coverage if late rows need it. At final follow-up re-fetch all actual test dates.

Capture HTTP status/request ID, `Location`, `Retry-After`; HTTP 202 is not a
finished report. Poll only the returned ARM operation URL, using Retry-After.
Each collector invocation has <=120-second command timeout and bounded polling;
persist operation state privately and return idle rather than sleeping for hours.
On 429 honor Retry-After and the lease deadline. Do not poll forever or create a
second duplicate report while the first is active.

Download **all** `manifest.blobs`, verify `blobCount`, byte counts and CSV headers;
retain `manifestVersion`, request context and `validTill`. Blob links may be SAS
credentials: never log/commit them; download before expiry to ignored private
storage without exposing query strings. Use no arbitrary untrusted redirect or
token forwarding. A partitioned CSV report is not ARM nextLink pagination.
The report is subscription-scoped; an authorized private collector may receive
non-lab rows. Filter by captured inventory/RG **before persistence of rows**;
never publish, print or retain unrelated resource details. If whole-report
download cannot meet this privacy rule, use a lab-filtered supported export/
portal path or return blocked, not a broad dump.

### C. MOSP/Visual Studio detailed usage

`GET /subscriptions/{sub}/providers/Microsoft.Consumption/usageDetails?api-version=2024-08-01&metric=ActualCost&$expand=meterDetails&$filter={urlencoded-filter}&$top=1000`

Filter at least:
`properties/usageStart ge '{day}' and properties/usageEnd le '{next-day}'`.
Confirm exact supported filters for the offer/schema, add a lab resource-group/
resource filter when available, and inspect returned intervals at the boundary.
Use a one-day request; do not accidentally restrict by billing receipt day alone.
Follow returned **nextLink exactly** (do not reconstruct skip tokens), retaining
private page count/request hashes and rejecting a link outside the expected ARM
host/scope. Apply the same local lab-only privacy filter before any row storage.
Some schemas use `instanceId` and `pretaxCost`, others `resourceId` and
`costInBillingCurrency`; record source API/version/kind before normalization.
The verified modern schema also exposes `instanceName` and `date`; do not
assume `instanceName` is a canonical resource ID. Resolve against the private
inventory and RG, and reject ambiguous attribution. Set explicit page, elapsed
and row-processing bounds. If a nextLink remains at any limit, mark the snapshot
incomplete and billing INCONCLUSIVE; never silently treat bounded truncation as
complete collection.
If meter expansion lacks name/rate, resolve MeterId against authorized price
sheet/rate card and keep provenance. Public Retail API is a comparison, not
proof of an account's effective price. Never guess missing price as zero.

## Required normalized fields

Keep original lab row and normalized row side by side under ignored evidence.
Preserve nulls, precision, decimals and raw units; no blanket rounding.

| Field group | Required fields / aliases |
|---|---|
| Provenance | API/version, metric ActualCost, request scope private alias, retrieved UTC, HTTP request ID, page/partition, row identity/hash, raw schema kind. |
| Meter | MeterId, MeterName, MeterCategory, MeterSubCategory, product/service, meter region, resource location, pricing model, charge type; legacy `meterDetails` equivalents. |
| Quantity | Quantity/usageQuantity, UnitOfMeasure/unit, billing unit multiplier and documented GB/GiB conversion. Missing quantity is not zero. |
| Price/cost | EffectivePrice, UnitPrice, PayGPrice if available, pretax/costInBillingCurrency, billing/pricing currency, exchange-rate context, discount/benefit/credit flags. |
| Attribution | ResourceId/instanceId, RG, subscription private alias, ResourceType, AdditionalInfo/additionalProperties raw JSON, tags if supplied. Never assume bandwidth row ResourceId is VM. |
| Time | Date/usageDate, usageStart/usageEnd if supplied, billing period, service period, invoice metadata when available, original UTC/date convention. |
| Experiment | Scenario/transfer IDs, producer and consumer aliases, tenant equality assertion, source NIC/PIP aliases, endpoint model, payload/wire counters, day attribution confidence. |

Retain MeterId and price effective dates privately for rerating reconciliation;
public report may use sanitized aliases plus meter name/unit/rate and quantities.
Raw subscription/resource IDs and tenant IDs never go in tracked artifacts.

## Attribution and reconciliation algorithm

1. Build private immutable inventory map before deletion: all VM, NIC, PIP,
   bandwidth-related resource IDs and RG, regions, exact creation/deletion times.
   Include P→C replacement so old IDs are not lost.
2. Select **all lab rows**, then classify transfer meters. Do not filter only by
   exact string “Bandwidth”: use MeterId, category/subcategory and price-sheet
   semantics, preserving unknown candidate meters for review. Split compute,
   disk, IP rent, Storage operations, PE/peering processing from bandwidth.
3. Attribute first by exact producer resource / NIC / PIP or explicit identifiers
   in AdditionalInfo, then by its created RG and UTC usage day. IP/bandwidth or
   PaaS plan/service attribution is valid if linked by inventory. Receiver rows
   are checked too. If only RG/day is present use the single-family/day schedule
   and label weaker attribution; if subscription-only rows cannot be isolated
   from concurrent labs, **inconclusive**, not proportional allocation.
4. Join transfer timestamps to **usage** interval, not ingestion timestamp.
   Daily billing cannot separate same-producer, same-day scenarios. Core avoids
   that overlap; new phases must have new sources or new UTC days.
5. Group by producer/day/MeterId/unit/currency/rate/charge type, sum quantity and
   cost only within like units. Convert known units to bytes explicitly. Payload
   5 GiB = 5,368,709,120 bytes; this is 5.36870912 decimal GB, **not 5 GB**.
   Retain counter overhead (TLS/ACK/management), unknowns and tolerance flags.
6. Compare quantity × effective unit price with cost using actual meter scale
   and rounding. Zero cost can mean free tier, allowance, credit, negotiated rate
   or rounding; it does not imply no quantity. MSDN credits can cover invoiced
   dollars without erasing consumed metered quantity. Do not assert every free
   service must emit a zero-rated row: some unbilled usage is absent from Cost
   Management, which is exactly why a mature positive control is essential.
7. Cross-region first: require expected Europe inter-region billable quantity
   and rate, not merely any egress row. The Internet 100 GB/month allowance is
   not the published intra-continental transfer tier. Do not burn >100 GB to
   defeat an allowance; optional Internet test remains inconclusive if masked.
8. Snapshot each collection independently; do not concatenate successive
   cumulative reports and double count. Within a snapshot retain legitimate
   duplicate-looking line items unless unique record identity proves duplication.
   Compare prior snapshot keys/hashes and changed quantities, negative adjustments
   and rerating. Keep results provisional until stable/invoiced as appropriate.

## Evidence grades and verdict rules

- **A:** complete Cost Details/Consumption/usage CSV; meter, unit, quantity,
  effective-rate provenance, cost/currency and source/day attribution; mature
  successful positive control and full transfer records. Supports scoped
  empirical billed/no-charge-observed statement.
- **B:** complete lab-filtered Query with usable meter/quantity if available,
  cost/currency and day isolation, but no detailed pricing or row metadata.
  Corroboration only; report missing fields. Aggregate cost alone cannot prove
  “no metering” or free traffic when allowances/credits can mask charges.
- **C:** application/NIC/Azure metrics only. Proves transport bytes, **not billing**.

Follow design.md's pass/fail/inconclusive definitions. Query success, zero rows,
zero dollars, a traceroute or a public source IP cannot alone pass billing.

## Bounded calendar, retention and teardown

### Actual 15 October run and dated follow-ups

Transport completed **10:04:25–10:40:28 UTC**, 5,368,709,120 bytes each
direction, all four endpoint/direction records matching the expected SHA256.
A's **10,818,818,041-byte RX+TX** delta is corroboration only: count it once,
not A+T, and never label it billed outbound.

Initial ActualCost Query was daily, lab RG AND MeterCategory=Bandwidth,
grouped by ResourceGroup + Meter, Sum(PreTaxCost):

| Producer context | Collection UTC on 15 October | Outcome | Interpretation |
|---|---|---|---|
| Windows / A | 14:14:58–14:15:07 | HTTP 200, COMPLETE, 1 page, 0 received/retained rows | Complete requested pagination, not mature billing or a measured zero charge. |
| Native WSL / T | 14:15:07–14:15:11 | HTTP 429, rate_limited ERROR, no snapshot | No rows obtained and completeness not established; **not an empty result**. |

Only ~3.6h had passed since transport. No mature same-offer/feed inter-region
known-charge positive control, attributable quantity/unit or effective-rate
evidence exists. **INCONCLUSIVE**, not a confirmed SaaS exemption, not “both
queries succeeded,” and not “free.” Credits, allowances and zero aggregate
cost cannot prove absence of charge. Bandwidth-only collection also omits
possible service-specific processing/provider fees.

### Historical bounded refresh, 18:22Z

The [sanitized machine-readable snapshot](results/2026-10-15-billing-refresh.json)
preserves the earlier results rather than replacing their historical meaning.
One invocation/HTTP attempt per endpoint/context, one page maximum, no retries:

| Context | Aggregate | Consumption details | Meaning |
|---|---|---|---|
| Windows core | HTTP 429, ERROR | HTTP 200, **INCOMPLETE**, 1,000 received/unrelated rows discarded in memory, 0 retained, continuation remains | RG predicate did not scope the response; no complete attributable result, not zero usage/cost. |
| Native WSL / T | HTTP 429, ERROR | HTTP 200, **COMPLETE empty**, 1 page | Complete request pagination, not mature billing or zero-charge proof. |

Receipt-date predicates cannot guarantee actual usage coverage. Mandatory
local inventory/RG/actual-date filtering precedes retention; no unrelated raw
billing rows were retained. Missing quantity/unit/rate/cost remain **null, not
zero**. At that time no successful control existed: v1 sent no bulk after
12 connection/TLS timeouts (C NIC RX+TX once 284,630 bytes); v2 blocked before
guest submission, zero payload and no guest NIC report. Do not call its
unmeasured NIC traffic zero.

Closing **invoice-level proof** requires mature attributable meter
quantity/unit/rate and a billed positive control. The practical same-region
pricing answer already follows the published rule, unqualified by tenant.
The official
[BYOIP destination Internet-egress exception](https://learn.microsoft.com/azure/virtual-network/ip-services/custom-ip-address-prefix#pricing)
continues to apply. Neither transport PASS nor empty Cost API output overrides it.

| Follow-up | Not before UTC | Actual usage day |
|---|---|---|
| 24h | 2026-10-16T10:40:28Z | 2026-10-15 |
| 48h | 2026-10-17T10:40:28Z | 2026-10-15 |
| 72h | 2026-10-18T10:40:28Z | 2026-10-15 |
| Day 7, if needed | 2026-10-22T10:40:28Z | 2026-10-15 |

For the successful **1 GiB C→B** control, separate 24/48/72h targets are
**16/17/18 October 23:15:33Z** (actual usage day **15 October**).
Its [23:28Z snapshot](results/2026-10-15-control-billing.json) used three billing
HTTP attempts, no retry/mutation; A's exact total is
**USD 0.0000728753264993429373**, not attributable to one request.
C lacked ingested rows/quantity/rate and details timed out in that historical
snapshot; T was empty. The 16 October 00:29Z CSV above supersedes the C/A
quantity gap, not the missing scale-confirmed control or T coverage.
At $0.02/decimal GB planning only, 1 GiB would be ~$0.0214748 before overhead,
not an observed rate/cost. Do not infer quantity from those retail estimates.

Use the [exact bounded collector templates](costs/README.md#dated-follow-up-commands-for-the-completed-run)
under a new approved read-only API lease. Each is a new cumulative snapshot:
compare revisions, **never sum repeated snapshots**. Query actual usage UTC,
not ingestion day. Detailed Consumption date predicates can be receipt windows;
avoid future ranges, inspect actual row dates and widen past receipt coverage
only within an approved bound. Partial pages and 429 remain incomplete/errors,
never zero usage.

Require **two stable future cumulative snapshots**, both at/after **16 October
23:15:33Z** (24h after the completed control), with comparable A/T source/day
coverage and a scale-confirmed charged C control. Together these can support a
scoped **no additional charge observed** conclusion, not a claim that a
zero-rated meter was emitted or that ActualCost is a final invoice. Reporting
can lag beyond 24h; stable tiny control quantities alone are insufficient.

**No automatic follow-up or cleanup job is established.** The table is an
action calendar, not evidence of scheduled automation. Use fresh bounded
read-only leases for 16/17 October, then historical queries after deletion.
Standing cleanup authority covers only known owned lab assets, under a fresh
exact-inventory lease; delete **before 18 October 07:33Z**, earlier if required
by actual creation time. No extra-cost scope or further MSDN payload is approved.
These were the original cleanup requirements. **Known-owned cleanup is now
complete** at **16 October 00:00:11.806224Z**; all known lab VMs/disks/PIPs
are deleted. The core RG and an additional unproven-ownership NSG remain
preserved for manual review, without standalone hourly rent. Do not adopt/delete
unknown roots. The prior whole-group cleanup BLOCKED record remains historical.

**Historical TTL rationale, satisfied for known-owned assets:** T's deadline
is **2026-10-18T08:20:59Z**. The earliest recorded core-resource creation gives
**2026-10-18T07:38:11Z**; the RG can be older. Conservatively arrange confirmed
core deletion before **07:33Z** that day (deployment lease start +72h), verifying
the private RG timestamp for an earlier deadline. Preserve the private historical
inventory, including deleted resource IDs; historical billing can be queried
after deletion. Do not retain VM/disk/PIP for these follow-ups.

- Collect once at **24, 48 and 72 hours after each test day's final transfer**.
  Coalesce due dates into at most one report request per usage day per calendar
  day. EA/MCA typically 8–24h; PAYG up to 72h, but uncommon delays can be longer.
- At 72h: if positive control absent or relevant rows still changing, return
  INCONCLUSIVE with exact missing evidence. Arrange one bounded **day-7**
  follow-up (not currently scheduled), not an indefinitely running agent. If still absent close inconclusive
  and seek billing support/authorized invoice review as a separate task.
- Keep VMs **deallocated between tests and deleted after confirmed cleanup**.
  Preserve read access and private ID/timestamp map; deletion does not erase
  historical cost records. Do not retain disks/PIPs for a 7-day collection window.
- Privately retain lab snapshots/hashes for 90 days or owner policy; delete
  expired SAS links immediately. Published narrative has sanitized aliases only.
  Cost Management retains data at least seven years, portal/Cost Details access
  covers last 13 months; do not treat this as retention of local raw transfers.

## Official references (retrieved 2026-10-15)

- [Cost Details instructions](https://learn.microsoft.com/en-us/azure/cost-management-billing/automate/get-small-usage-datasets-on-demand):
  “we recommend you query at most once per day”; ActualCost/AmortizedCost,
  asynchronous Location/Retry-After and partitioned blob manifest.
- [Legacy offer path](https://learn.microsoft.com/en-us/azure/cost-management-billing/automate/get-usage-details-legacy-customer):
  “you can also use the Consumption Usage Details API.”
- [Understand data](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data):
  “Costs shown don't include free and prepaid credits”;
  “Cost and usage data files - Rounding doesn't occur”;
  “When cost and usage data becomes available in Cost Management, it gets retained for at least seven years.”
- [Query REST contract](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2023-11-01)
  (contract reference; verify supported dimensions/columns on the target offer).
