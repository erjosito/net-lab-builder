# Billing verdict: same-region Azure public endpoints across tenants

**Practical pricing answer: no additional Azure bandwidth fee is expected merely
because the destination is in another tenant.** For ordinary Microsoft-allocated
regional public IPs serving Azure resources in the **same Azure billing region**,
apply the published same-region Azure-service transfer rule. Public addressing
and a different subscription/Entra tenant do not, by themselves, establish
Internet-egress charging.

**Experimental verdict: transport PASS; invoice-level confirmation INCONCLUSIVE.**
These are different conclusions, not a reason to withhold the practical pricing
answer. C now has a substantial adjacent-day charge, but not a full quantity
match to the control; A/B/T still show only microcosts.
**No measured zero-rated 5 GiB intraregional transfer is established.**

**Update, 2026-10-16 UTC:** the separately completed
[C → B v4 inter-region control](2026-10-15-cross-region-control.md) is now
**transport/restoration PASS**, **1 GiB**, one upload, zero retries, independently
verified with 11 reads / 0 mutations. The initial **23:28Z** billing snapshot
still contains only the same A rows below; C Query has no rows and C details
timed out; T Query is empty. **Successful expected-charged transport is not yet
a billed positive control.** No zero-dollar or invoice conclusion follows.
Known-owned cleanup closed PASS **16 October 00:00:11.806224Z**, all known lab
VMs/disks/PIPs deleted; **core RG and one unproven-ownership NSG were preserved**,
not adopted/deleted. The older billing/provenance history below is retained.

## Current quantity evidence: 16 October 06:50:38Z

The [current sanitized check](2026-10-16-billing-check-0650.json) contains:

| Source | CSV usage/purchase date | Meter | Quantity, “1 GB” | Effective price, USD | Reported cost, USD |
|---|---|---|---:|---:|---:|
| C | 2026-10-15 | Intra Continent Data Transfer Out | 0.000002402812242508 | 0.02 | 4.80562448501586884E-8 |
| C | 2026-10-16 | Intra Continent Data Transfer Out | 0.6551259830594063 | 0.02 | 0.013102519661188125 |

The 16-October row first appears in this check, after the successful
**15 October 23:08:23–23:15:32Z** 1-GiB control. Its substantial charge is
consistent with a bulk-sized control, but **not yet a full quantity match**
to roughly 1–1.1 reported GB. Do not call partial ingestion proven: units,
coverage and attribution remain unresolved. No exact transfer-to-invoice
correlation follows from daily dates. No cross-date or cross-snapshot sum
was performed.

Both ActualCost Queries are COMPLETE, covering 15 October through the actual
16 October 06:48Z request cutoffs. A fresh CSV generation/poll/download
returned 202/200/200 for requested 15–16 October dates, retaining seven
Bandwidth rows: exact historical endpoints **A: 3, B: 2, C: 2**. The original
A-group Query scope's **five** rows include B's two; they are not five A rows.
T's complete Query now has one 15-October **Intra Continent Data Transfer Out**
row, **EUR 7.4561667E-8**; it supplies no quantity/unit/rate, and none is
inferred. No 5-GiB-scale headline A/T charge is proven.

Fresh extraction is not proof of final ingestion. The ingestion watermark is
unavailable; report-end inclusivity and day completeness remain unknown.
The CSV date denotes usage/purchase, not receipt. Five of six allowed HTTP
requests, zero retries or infrastructure mutations; contexts unchanged,
lease closed and native children idle. **Experimental verdict remains
INCONCLUSIVE**, about 7.5 hours after the control. Known-owned billable assets
remain deleted; late-arriving usage does not imply continuing resource rent.

## Historical quantity evidence: 16 October 00:29Z

The [historical sanitized reconciliation](2026-10-16-usage-reconciliation.json)
records successful actual Cost Details CSV extraction, superseding the
historical 00:21Z schema failure. One generation, one poll and one download
returned HTTP 202/200/200, with no retries or infrastructure mutations.
Actual headers include `ResourceId`, `resourceGroupName`, `date`, `quantity`,
`unitOfMeasure`, `effectivePrice`, `costInBillingCurrency` and `billingCurrency`.
Six of 371 rows passed exact owned inventory/RG/15-October/Bandwidth filtering;
unrelated rows were discarded before persistence. T was **not refreshed**;
its last empty snapshot is not new zero-charge evidence.

All quantities below are reported in **“1 GB”**, prices in **USD per reported
unit**, with decimal strings preserved directly from the CSV:

| Source | Meter | Quantity | Effective price | Reported cost, USD |
|---|---|---:|---:|---:|
| C | Intra Continent Data Transfer Out | 0.000002291053533554 | 0.02 | 4.58210706710815400000E-8 |
| A | Inter Continent Data Transfer Out - NAM or EU To Any | 0.000966296531260014 | 0.05 | 0.000048314826563000676 |
| A | Intra Continent Data Transfer Out | 0.000003241002559662 | 0.02 | 6.48200511932373042000E-8 |
| A | Standard Data Transfer Out | 0.000295128673315048 | 0.083 | 0.000024495679885149002 |

The other two retained rows belong to original endpoint **B**, not source A;
their exact values remain in the reconciliation. The C microcharge is not a
scale-confirmed billing match to the successful **1 GiB C→B** bulk transfer
on **15 October 23:08:23–23:15:32Z**. These are actual daily usage fields,
not traffic-derived quantities or retail-price estimates. Do not recompute
the cost strings from rounded displayed quantity/rate fields or add successive
Query/CSV snapshots. Requested dates span 15–16 October, but owned usage
dates are only 15 October; that does not establish ingestion completeness.
**Quantity/unit/effective price are now available; billing maturity and
transfer attribution remain the blockers. Experimental verdict: INCONCLUSIVE.**

## Published rule and scope

The [official bandwidth pricing FAQ](https://azure.microsoft.com/en-us/pricing/details/bandwidth/)
was rechecked on **2026-10-15 at approximately 21:34Z**:

> Is data transfer between Azure services located within the same region charged?
>
> No. For example, an Azure SQL database in the same region will not have any
> additional data transfer costs.

The rule is not qualified by tenant or subscription. It is reasonable to apply
that general rule across a tenant boundary; an explicit enumeration of every
identity boundary is not a prerequisite to this pricing interpretation.
This is **high-confidence published-pricing guidance**, not a new contractual
guarantee or an experimentally reconciled invoice.

Check these exceptions before answering for a real SaaS endpoint:

- **BYOIP destination:** [Microsoft's custom-IP-prefix pricing](https://learn.microsoft.com/azure/virtual-network/ip-services/custom-ip-address-prefix#pricing)
  explicitly says all traffic destined to a custom IP prefix range is charged
  the Internet-egress rate, including Azure-origin traffic at its source-region
  rate. Ordinary Azure-assigned addresses and BYOIP are not interchangeable.
- **Actual endpoint placement:** the SaaS marketing region, DNS name, or tenant
  location does not establish the Azure billing region of the actual endpoint.
  Front Door/CDN/anycast, a proxy or a non-Azure destination needs its own analysis.
- **Other fees:** SaaS-provider charges, public-IP rent and service-specific
  processing/transfer charges are separate from this Azure bandwidth rule.

## Historical 21:08Z/21:36Z Query: what the three rows actually say

Both snapshots use **ActualCost**, daily usage **2026-10-15**, API
**2023-11-01**, and the hard intersection **owned core RG AND
MeterCategory=Bandwidth**. Values below are the API's exact decimal cost
representations, parsed without binary-float rounding.

| Meter, exact name | 21:08Z RG+Meter cost, USD | 21:36Z ResourceId+Meter cost, USD | Latest source alias | Quantity | Unit | Effective/unit rate |
|---|---:|---:|---|---|---|---|
| Inter Continent Data Transfer Out - NAM or EU To Any | 0.0000315144192427397 | 0.0000483148265630007 | A, core VM | Not reported | Not reported | Not reported |
| Intra Continent Data Transfer Out | 6.37024641036987E-8 | 6.48200511932373E-8 | A, core VM | Not reported | Not reported | Not reported |
| Standard Data Transfer Out | 0.000024495679885149 | 0.000024495679885149 | A, core VM | Not reported | Not reported | Not reported |

Original retrieval: **21:08:37.120495Z**, request cutoff
**21:08:35.078306Z**; columns `PreTaxCost`, `UsageDate`, `ResourceGroup`,
`Meter`, `Currency`. Resource-attribution retrieval: **21:36:25.901546Z**, request cutoff
**21:36:15.396064Z**; columns `PreTaxCost`, `UsageDate`, `ResourceId`,
`Meter`, `Currency`. Both are **HTTP 200, COMPLETE, one page, three rows**.
The 21:36Z returned resource IDs all match the private owned inventory's **A VM**.
No B or C source is present in these returned rows. The raw resource IDs, group
names, subscription IDs, tenant IDs and addresses are deliberately omitted.

Exact bandwidth-category totals are **USD 0.0000560738015919923987** in the
original snapshot and **USD 0.0000728753264993429373** in the 21:36Z snapshot,
unchanged in the later [23:28Z snapshot](2026-10-15-control-billing.json). These are
**successive cumulative snapshots, not additive charges**, and not the whole-lab
bill or a final invoice. The change illustrates that same-day cost data is still
being revised/ingested.

**“Intra Continent” does not mean “intra region.”** The published bandwidth table
places intra-continental transfer under **Inter Region** pricing (Europe:
$0.02/GB). The inter-continent and standard-out rows likewise are not evidence
of free intraregional quantity. Public retail prices are context, not this
account's verified effective rates; no quantity has been back-calculated from
these costs.

## What can and cannot be attributed

- The successful headline was A ↔ T, both Sweden Central, in different tenants:
  **5,368,709,120 bytes each direction**, matching SHA256, zero bulk retries,
  **10:04:25.588424Z–10:40:28.237747Z**. A produced one direction; T produced the
  other. Both connections being initiated by A does not make A the bulk producer
  for the download.
- Resource-level attribution now removes the earlier A/B shared-RG ambiguity
  **for these three returned rows**. It does not isolate A's headline traffic
  from A's other traffic on the same day. Daily costs have no per-request,
  destination, or experiment identifier here. Management, readiness and background
  traffic remain possible explanations, **not demonstrated causes** of the charges.
- No row reports an explicit same-region meter, 5 GiB quantity, unit or rate.
  Therefore these rows **do not show that the headline was charged**, and also
  **do not prove it was metered at zero**. The tiny positive amounts are not a
  successful known-quantity charged control.
- T's existing native-WSL/MSDN snapshot at **21:09:04.228864Z** was HTTP 200,
  COMPLETE, one page, **zero rows**, same original cutoff/day/filter. This is not
  quantity=0 or proof that its outbound 5 GiB was free. No additional T request
  or context change was needed for this interpretation.
- C → B control v1 made no bulk requests and failed after 12 connection/TLS
  timeouts; v2 blocked on a NIC read before guest submission. Neither transferred
  the intended cross-region 5 GiB. C's isolated RG cannot turn these A rows into
  positive-control evidence.
- Read-only v3 inspection later identified **B's additional subnet NSG default
  inbound deny at priority 65500**, missed by NIC-only allowance. v4 corrected
  both owned NIC/subnet layers, exact tags/policies/associations, with
  **100 WSL tests passed** and both original-policy PUTs submitted once before
  polling within the shared 900-second restoration reserve. Earlier failed/
  blocked records are not rewritten.
- v4 bulk **15 October 23:08:23–23:15:32Z** delivered exactly
  **1,073,741,824 bytes C/NE → B/SC**, same core subscription/tenant.
  C NIC RX+TX once **1,085,524,745 bytes** is not a billing quantity.
  Default control payload remains 5 GiB; explicit 1 GiB used a 2 GiB wire
  reserve, leaving **3 GiB from reconciled 5 GiB**. $8/$4 remain caps, not bills.
- At the Europe **$0.02 per decimal GB planning rate**, 1 GiB =
  1.073741824 GB suggests **~$0.0214748 before overhead**, not actual account
  rate/cost. No missing quantity was back-calculated from observed A costs.
- The **23:28:41Z** snapshot made **three billing HTTP attempts, zero retries
  or mutations**, not three billable transfer requests. Daily A resource
  attribution cannot isolate one headline request; C ingestion remains missing,
  details timeout is ERROR, T empty is not zero-charge proof.

## Bounded follow-up and provenance

One resource-attribution query succeeded at **21:34Z**, before its runner exited
with an unclassified local failure during the subsequent details stage. A second
invocation, used to classify that failure, repeated the same resource query at
**21:36Z** and returned identical costs. This was **two Query requests**, not one
hidden retry; each returned three inventory-matched rows with no continuation.
The second details stage received one HTTP 200 page, then failed on native CLI
authorization timeout before a complete normalized result could be persisted.
Its status is **ERROR/cli_timeout**, not COMPLETE empty. No quantity/rate result,
complete details pagination, or count of all discarded rows is claimed.

The details collection had a **five-page ceiling**, 75-second transport deadline
and 120-second native runner timeout, using the existing in-memory inventory/RG/
actual-usage-date filter. No unrelated row values were retained. There was no
unfiltered bill fallback, installation, account switch, resource operation, VM
start, NSG change or payload restart. Query quantity aggregation was not
invented: the existing verified contract sums only `PreTaxCost`; the documented
Query schema does not itself establish usable `UsageQuantity` for this scope.

Private minimal evidence, under the lab's ignored directory:

- `private\cost-snapshots\throttle-recheck-20261015T210835Z\windows-aggregate.private.json`
- `private\cost-snapshots\throttle-recheck-20261015T210835Z\wsl-aggregate.private.json`
- `private\cost-snapshots\billing-verdict-20261015T213459Z\resource-meter.private.json`
- `private\cost-snapshots\billing-verdict-20261015T213615Z\resource-meter.private.json`
- `private\cost-snapshots\billing-verdict-20261015T213615Z\status.private.json`

**Remaining evidence gap:** the latest CSV now supplies quantity/unit/effective
price, but mature source/day-comparable coverage and a **scale-confirmed,
billing-confirmed** known-charge control are still needed
for a strong experimental billing confirmation. This gap limits invoice proof;
it does not negate the general published same-region pricing rule. Do not
restart transfers or retain billable resources merely to close the gap.

Headline maturity target: **16 October 10:40:28Z**. Control 24/48/72h targets:
**16/17/18 October 23:15:33Z**, actual usage **15 October**; the last is after
the original **18 October 07:33Z** resource deadline. Query private historical
IDs after completed known-owned cleanup; no more transfers or MSDN tests needed.
Require two stable future cumulative snapshots **at least six hours apart**,
both **at/after 16 October 23:15:33Z**, with comparable A/T coverage and the scale-confirmed charged C
control before supporting a scoped **no additional charge observed** finding.
Stable tiny rows alone are insufficient; neither stability nor absence of an
explicit intraregional row proves a zero-rated meter or a final invoice.
Six-hour read-only billing follow-up is active, next expected around
**16 October 12:50Z**. It does not authorize resource recreation or transfers.

**Safety:** this documentation update is offline, zero Azure calls/mutations
or payload. Latest independent v4 verification **23:25:22Z, 15 October**
confirmed both original NSG layers and associations and both guests deallocated,
no owned children; later known-owned cleanup closed **00:00:11.806224Z**.
13 remaining original core assets (17 minus four earlier P retirements) are
absent, C/T groups gone. Core RG and an additional NSG remain out of scope
pending manual creation-ownership review, with no standalone hourly rent;
unknown roots must not be adopted/deleted. Earlier whole-core cleanup BLOCKED
is historical, not a claim that every core root is now deleted.
