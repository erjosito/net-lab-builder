# Billing verdict: same-region Azure public endpoints across tenants

**Practical pricing answer: no additional Azure bandwidth fee is expected merely
because the destination is in another tenant.** For ordinary Microsoft-allocated
regional public IPs serving Azure resources in the **same Azure billing region**,
apply the published same-region Azure-service transfer rule. Public addressing
and a different subscription/Entra tenant do not, by themselves, establish
Internet-egress charging.

**Experimental verdict: transport PASS; invoice-level confirmation INCONCLUSIVE.**
These are different conclusions, not a reason to withhold the practical pricing
answer. The available billing rows are tiny positive charges attributed to A,
**not a measured zero-rated 5 GiB intraregional transfer**.

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

## What the three rows actually say

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

**Remaining evidence gap:** mature, source/day-attributable quantity/unit/
effective-rate records and a **billing-confirmed** known-charge control are needed
for a strong experimental billing confirmation. This gap limits invoice proof;
it does not negate the general published same-region pricing rule. Do not
restart transfers or retain billable resources merely to close the gap.

Headline maturity target: **16 October 10:40:28Z**. Control 24/48/72h targets:
**16/17/18 October 23:15:33Z**, actual usage **15 October**; the last is after
the original **18 October 07:33Z** resource deadline. Query private historical
IDs after completed known-owned cleanup; no more transfers or MSDN tests needed.
No automatic follow-up or cleanup job is established.

**Safety:** this documentation update is offline, zero Azure calls/mutations
or payload. Latest independent v4 verification **23:25:22Z, 15 October**
confirmed both original NSG layers and associations and both guests deallocated,
no owned children; later known-owned cleanup closed **00:00:11.806224Z**.
13 remaining original core assets (17 minus four earlier P retirements) are
absent, C/T groups gone. Core RG and an additional NSG remain out of scope
pending manual creation-ownership review, with no standalone hourly rent;
unknown roots must not be adopted/deleted. Earlier whole-core cleanup BLOCKED
is historical, not a claim that every core root is now deleted.
