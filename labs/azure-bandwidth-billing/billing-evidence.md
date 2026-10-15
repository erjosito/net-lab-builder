# Billing extraction and reconciliation plan

Reconciliation design plus [executable collectors and tested API matrix](costs/README.md).
Current experimental billing verdict: **INCONCLUSIVE** after completed
same-region cross-tenant transport; no unrelated billing values retained.
Updated 2026-10-15. See the [sanitized result](results/2026-10-15-cross-tenant-public-ip.md).
Latest refresh completed **18:22Z**; independent B/C restoration/idle verification
completed by **19:06:07Z**. C → B v1 **FAIL** and v2 **BLOCKED before bulk**
did not establish a charged positive control.
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
offline contract tests. Cost Details asynchronous generation remains explicitly
unimplemented, not a success-shaped fallback. Windows modern Consumption failed
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

### Latest bounded refresh, 18:22Z

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
zero**. A known-charge positive control is still absent: v1 sent no bulk after
12 connection/TLS timeouts (C NIC RX+TX once 284,630 bytes); v2 blocked before
guest submission, zero payload and no guest NIC report. Do not call its
unmeasured NIC traffic zero.

Closing the tenant-boundary question requires mature attributable meter
quantity/unit/rate and provider policy confirmation. The same-region Azure
services FAQ does not explicitly mention tenants, and the official
[BYOIP destination Internet-egress exception](https://learn.microsoft.com/azure/virtual-network/ip-services/custom-ip-address-prefix#pricing)
continues to apply. Neither transport PASS nor empty Cost API output overrides it.

| Follow-up | Not before UTC | Actual usage day |
|---|---|---|
| 24h | 2026-10-16T10:40:28Z | 2026-10-15 |
| 48h | 2026-10-17T10:40:28Z | 2026-10-15 |
| 72h | 2026-10-18T10:40:28Z | 2026-10-15 |
| Day 7, if needed | 2026-10-22T10:40:28Z | 2026-10-15 |

Use the [exact bounded collector templates](costs/README.md#dated-follow-up-commands-for-the-completed-run)
under a new approved read-only API lease. Each is a new cumulative snapshot:
compare revisions, **never sum repeated snapshots**. Query actual usage UTC,
not ingestion day. Detailed Consumption date predicates can be receipt windows;
avoid future ranges, inspect actual row dates and widen past receipt coverage
only within an approved bound. Partial pages and 429 remain incomplete/errors,
never zero usage.

**No automatic follow-up or cleanup job is established.** The table is an
action calendar, not evidence of scheduled automation. Use fresh bounded
read-only leases for 16/17 October, then historical queries after deletion.
Standing cleanup authority covers only known owned lab assets, under a fresh
exact-inventory lease; delete **before 18 October 07:33Z**, earlier if required
by actual creation time. No extra-cost scope or further MSDN payload is approved.
A/B/C/T are deallocated but retained disks/PIPs still accrue charges.

**Delete before resource TTL even though 72h billing is later:** T's deadline
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
