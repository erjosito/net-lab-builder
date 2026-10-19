# Azure public-endpoint bandwidth billing

## Executive summary — 19 October 2026, 11:08Z (quantity refresh)

**Detailed retrieval PASS; billing reconciliation remains OPEN.** Both
[last-week Cost Details CSVs](results/2026-10-19-last-week-quantity-recovery.json)
completed: fresh C still reports **14.2374728210270405 `1 GB`** at
**USD 0.02**, bulk cost **USD 0.28474945642054081**; historical C still
reports **0.6551259830594063 `1 GB`**, bulk cost **USD 0.013102519661188125**.
These are fresh CSV observations, not quantities inferred from Query.
Neither reconciles its verified **100 GB / 1 GiB** transfer.

The [weekly financial conclusion below](#superseded-executive-summary--19-october-2026-1050z-offline-refresh)
is unchanged: cross-region charges are observed; no bulk-sized charge for
A's same-region, cross-tenant transfer is observed. Polling succeeded this
time without a changed-Location failure; the earlier difference remains
unknown, not fixed or reproduced. See [quantity comparisons and boundaries](billing-evidence.md#latest-snapshot--19-october-2026-1108z-quantity-refresh).
Existing bounded follow-up and the **22 October 23:15:33Z hard stop** remain.

An [offline accounting audit](results/2026-10-19-offline-volume-audit.json)
rechecks all 80 directed proof records and finds **100,838,387,131 C guest
NIC TX bytes** across its 20 completed pairs. The retained report matches
the transfer VM, drops no owned rows by date, and has exact bulk
quantity/price/cost arithmetic. Both transfer days are inside its interval.
No checked local-accounting explanation was found; discarded
inventory/category rows cannot be reaudited from retained evidence.

## Superseded executive summary — 19 October 2026, 10:50Z (offline refresh)

**Financial observation PASS; final billing reconciliation OPEN.**
The [last-week meter retrieval](results/2026-10-19-last-week-bandwidth-meters.json)
returned five HTTP 200 Queries covering fresh A/C/T, historical C and the
shared historical A/B resource group, across both subscriptions. The requested
week is **12–18 October UTC**; the actual serialized interval ends at
**18 October 23:59:59Z**, not the final fractional second. Older historical T
was not refreshed; this does not prevent the fresh two-subscription finding.

**Conclusion: cross-region charges are observed, but no bulk-sized charge
for A's verified same-region 100 GB transfer is observed after this
closed-week Query. Tenant separation alone has not produced an observable
bulk bandwidth charge in this setup.** This is consistent with the published
Azure-to-Azure intra-region rule, not an explicit tenant-boundary FAQ quote,
final invoice, explicit zero-rated record or full-volume reconciliation.

| Fresh source / test role | Returned weekly Bandwidth cost | Interpretation |
|---|---:|---|
| A — same-region-only 100 GB bulk test | USD 0.00000137982331216335287 | Four positive microcharge rows, not a bulk-sized 100 GB charge |
| C — cross-region source | USD 0.28475133349094558918 | USD 0.284749456420541 Intra Continent plus USD 0.00000187707040458918 Standard |
| T — mixed same-region T → A and cross-region T → C roles | EUR 0.244085448265384 | All Intra Continent; cannot allocate to an individual flow |

A's total includes **USD 0.000001374235376715660 Standard** and
**USD 0.00000000558793544769287 Intra Continent**: positive microcharges
are neither zero cost nor automatically attributable to the 100 GB flow.
All **seven fresh day/meter/currency rows** are unchanged from the
18 October 11:51–11:52Z Queries, over **22 hours** later. Fourteen overlapping
rows overall are unchanged; an additional historical-B 16 October row has
no old comparison, so not all historical totals can be called unchanged.

**Still unknown:** Queries return no quantity, unit or rate and no ingestion
watermark. C's **14.2374728210270405 reported `1 GB`** remains the old
18 October 08:15Z CSV, not a fresh quantity. Historical-C's old **0.6551259830594063
reported `1 GB`** control remains unreconciled; T's unit/identity semantics
remain unresolved. No automatic unit/currency conversion is justified.
The conclusion is scoped to verified actual Azure regions and Azure-owned
public IPs, not all SaaS destinations; [BYOIP exceptions and other product
charges remain separate](#policy-handoff-2026-10-18-same-region-cross-tenant-public-ip-egress).

Collection stopped correctly at the **80% new-work gate (5/6 HTTP allowance)**,
leaving historical T unqueried, not because tools or time ran out. The
immutable result keeps its five-request count. This offline refresh made
no live requests or operational changes. **Transport PASS (400 GB), cleanup
PASS (21 owned roots deleted)** and the existing **six-hourly schedule 5 /
22 October 23:15:33Z hard stop** remain unchanged; billing stays open.
See [coverage, exact costs and confidence limits](billing-evidence.md#latest-snapshot--19-october-2026-1050z-offline-refresh).

## Superseded executive summary — 18 October 2026, 12:15Z (offline refresh)

**Transport PASS (400 GB); cleanup PASS (21 owned roots deleted); billing
INCONCLUSIVE and open.** The new [fresh financial comparison](results/2026-10-18-control-financial-comparison-114700.json)
returned **T/A/C Query HTTP 200** at **11:51–11:52Z**, each more than ten
hours after the 01:21Z baseline. A remains **USD
0.00000137982331216335287**; C's all-Bandwidth aggregate increased to **USD
0.28475133349094558918** (**+0.06725686436425906306**); T increased to
**EUR 0.244085448265384** (**+0.078935232962947**). These are aggregate
costs, not new quantities or rates. C's Query is nearly, not exactly, equal
to its 08:15Z CSV all-Bandwidth total; preserve both source precisions.

The [historical-control alternative](results/2026-10-18-historical-control-alternative.json)
adds a timed-out legacy GET and successful historical-C Query: **USD
0.0131025677174329501587**, unchanged from 01:21Z. Historical financial
stability is a **partial mismatch**, not full reconciliation of the verified
1 GiB control. Its quantity/rate remain **STALE: 0.6551259830594063 reported
`1 GB` at USD 0.02**; neither historical detail attempt refreshed them.
Do not assume the entire verified-volume shortfall is ingestion lag.

The latest fresh-C bulk CSV remains **08:15Z: 14.2374728210270405 reported
`1 GB`, USD 0.28474945642054081**, distinct from all-Bandwidth costs.
A's unchanged **08:17Z four positive microquantity rows**, separated by over
six hours, still contain no explicit zero-rated 100 GB record. T's raw
**`1 TB` versus retail `1 GB`**, repeated-ID semantics and asynchronous
**422 cause UNKNOWN** remain unresolved (support issue **#23**); no
same-region charge or service bug is proved.

The original dated result remains **4/6 as of its snapshot**; the linked
alternative records **global 6/6**, four Queries plus generation and legacy
GET, with all owned children idle. Both historical detail timeouts used
the then-fixed **20-second socket timeout / source `2ab6c0ce…`**.
The subsequent offline CLI change adds `--request-timeout-seconds`
(default **20**, explicit **120** available for future bounded calls);
it has **not been rerun live** and does not retroactively fix those failures.
It is not a hard real-time total request deadline or an ingestion guarantee.

See the [dated financial comparison and provenance](billing-evidence.md#latest-snapshot--18-october-2026-1215z-offline-refresh)
and [collector timeout semantics](costs/README.md#latest-actual-cost-answer--18-october-2026-1215z-offline-refresh).
Only existing **six-hourly schedule 5** and its original
**22 October 23:15:33Z hard stop** remain; no budget restart, new timer,
traffic, resources or live calls were made by this offline refresh.
The [same-region policy qualification, BYOIP exception and separate service fees](#policy-handoff-2026-10-18-same-region-cross-tenant-public-ip-egress)
are unchanged. Dated evidence below retains its original as-of claims.

## Superseded executive summary — 18 October 2026, 08:20Z (offline refresh)

**Transport PASS (400 GB); cleanup PASS (21 owned roots deleted); billing
INCONCLUSIVE and open.** The new [separated Cost Details comparison](results/2026-10-18-separated-detail-comparison-081000.json)
completed C/A CSV extraction at **08:15:52Z / 08:17:20Z**. Collection
**PASS, 6/6 requests** means two generations, two polls and two downloads,
not final billing reconciliation. Source is unchanged; the live owner closed
with no matching native billing children at **08:19:14.3125252Z**.
This documentation refresh made no live calls or operational changes.

**C is still changing.** Four 17 October **Intra Continent Data Transfer
Out** rows now total **14.2374728210270405 reported `1 GB`**, effective/unit
price **USD 0.02**, cost **USD 0.28474945642054081**. Against the
17 October 23:01:56Z CSV's **10.8746547754853965 / USD 0.21749309550970793**,
this is **+3.3628180455416440 reported units / +USD 0.06725636091083288**
over **9h13m56.043898s**. Exactly one bulk row and one Standard microquantity
row were added. Three separate Standard rows total **USD
0.0000018770704045891761**; all seven C Bandwidth rows total **USD
0.2847513334909453991761**. The cross-region meter subtotal is not that
all-Bandwidth total, a same-region charge, or a full 100 GB match. No unit
conversion is applied.

**A is unchanged, not proven zero-rated.** Its four original charged
microquantity records on 16–17 October have an unchanged exact-Decimal
multiset and **USD 0.0000013798233121633528712** subtotal. The actual
baseline CSV extraction was **02:02:39.886655Z**; the later operational
receipt was **02:07:34.723864Z**. The new extraction is over six hours after
both (**6h14m40.600578s / 6h09m45.763369s**, respectively). There is still
no bulk-sized same-region line or explicit zero-rated 100 GB record.

**Billing-publication lag is observed empirically:** new 17 October usage
appeared more than nine hours after the prior report. This does not identify
when publication will finish, establish a delivery SLA, or prove stable
reconciliation. Complete extraction is not final ingestion; all nonzero C
rows are dated 17 October, and other days are not explicit zeros. Final
transport verification at **17 October 22:15:17.236880Z** is still under
24 hours old; **18 October 22:15:17.236880Z** is an aging checkpoint, not a
formal ingestion watermark.

No Query was refreshed: the **01:21Z Query baseline remains historical**.
T was not queried; its genuine duplicate service ID, raw **`1 TB`** versus
retail **`1 GB`**, and asynchronous **422 cause UNKNOWN** remain unresolved.
Existing **schedule 5 only** and its original **22 October 23:15:33Z hard
stop** are unchanged. A suggested **~14:19Z** next comparison is not a verified
scheduled due time or new collection authority. No resources or traffic
should be recreated. See [quantities, deltas and coverage](billing-evidence.md#latest-snapshot--18-october-2026-0820z-offline-refresh)
and the [collector status](costs/README.md#latest-actual-cost-answer--18-october-2026-0820z-offline-refresh).

**Policy remains separate:** the published same-region Azure-service rule
does not explicitly qualify tenant boundaries; cross-tenant applicability
remains an interpretation. The [BYOIP Internet-egress exception and separate
product/service charges](#policy-handoff-2026-10-18-same-region-cross-tenant-public-ip-egress)
remain excluded from a blanket no-charge conclusion. The dated snapshots
below retain their original as-of evidence and provenance.

## Superseded executive summary — 18 October 2026, 02:25Z (offline refresh)

**Transport PASS (400 GB); cleanup PASS; billing INCONCLUSIVE and open.**
The [A CSV / T diagnostic baseline](results/2026-10-18-detail-baseline-020010.json)
completed **02:07:34Z**; [T source provenance](results/2026-10-18-t-unit-provenance-021800.json)
completed **02:21:56Z**. A's complete CSV extraction contains **four charged
microquantity rows on 16–17 October**, not a bulk-sized same-region 100 GB
line, an explicit zero-rated record, or mature ingestion. T retains two
owned Bandwidth rows diagnostically, **INCOMPLETE**, despite finished pagination.

T's raw API field **`properties.meterDetails.unitOfMeasure` is `1 TB`**:
the public normalizer faithfully projects it. Both owned rows share the same
service record ID but have different contents; both original hashes are
unchanged. The public parser correctly fails closed with
`conflicting_record_identity`; diagnostic retention is not a complete report.
Their exact **EUR 0.165150215302437** sum equals the independent earlier
Query: strong financial corroboration, **not proof of unique records, unit
meaning, byte attribution, credit treatment or a zero price**.

Independent official Retail Prices metadata for the exact meter reports
**`1 GB`, EUR 0.0176 / USD 0.02**. This contradicts T's raw legacy `1 TB`,
but does not justify dividing by 1,000 or changing the reported quantity.
T's legacy effective price **EUR 0.017329** differs from retail; currency,
date and offer comparability are not established, nor is a negotiated rate.
See [exact rows, provenance and limits](billing-evidence.md#latest-snapshot--18-october-2026-0225z-offline-refresh)
and the [public T reproduction command](costs/README.md#t-date-bounded-consumption-reproduction).

Fresh C's last CSV remains **17 October 23:01:56Z**, not refreshed:
**10.8746547754853965 reported `1 GB` at USD 0.02 =
USD 0.21749309550970793**, a positive partial cross-region charge, not the
full 100 GB leg. “Intra Continent” is not “same region.”

The new manual check now totals **6/6 customer HTTP requests**:
**A 3 + T first parser failure 1 + diagnostic 1 + provenance GET 1**.
The 02:07 artifact remains its immutable **5/6 as-of snapshot**; the new
provenance sidecar records exhaustion. Earlier manual checks are separate.
T's asynchronous-report **422 cause remains UNKNOWN**.

Earliest six-hour comparisons: **Query 07:21:11Z**, **A details 08:07:34Z**;
the T provenance phase began **02:18Z**, so its source comparison is **08:18Z
or later** (completion-based conservative repeat **08:21:56Z**). These are
earliest clocks, not mature/final ingestion guarantees; T's current report
is incomplete. No new collection skips the wait or proves a watermark.
Existing follow-up/hard stop **22 October 23:15:33Z** is unchanged.

**Policy versus measurement:** published same-region Azure-service transfers
are free, but tenant boundaries are unqualified, not explicitly cross-tenant;
the [BYOIP Internet-egress exception and separate service fees](#policy-handoff-2026-10-18-same-region-cross-tenant-public-ip-egress)
still apply. Missing rows are not zeros. This refresh is local-only:
no Azure/authentication, infrastructure, source, git or automated-job changes.

## Superseded executive summary — 18 October 2026, 01:25Z

**Transport PASS (400 GB); cleanup PASS; billing INCONCLUSIVE.**
The [new actual Query collection](results/2026-10-18-query-alternative-011707.json)
completed **01:20:25–01:21:11Z on 18 October**: four Queries, **four HTTP 200
responses / four requests**, nine exact-canonical-VM daily meter rows:

| Safe endpoint alias | Returned usage days | Rows | Query cost total | Currency |
|---|---|---:|---:|---|
| A (fresh, Sweden Central) | 16–17 October | 4 | 0.00000137982331216335287 | USD |
| T (fresh, Sweden Central) | 17 October | 1 | 0.165150215302437 | EUR |
| C (fresh, North Europe) | 17 October | 2 | 0.21749446912668652612 | USD |
| historical-C (older C → B control) | 15–16 October | 2 | 0.0131025677174329501587 | USD |

These totals combine only returned rows within each alias/currency, not
currencies, experiments or refreshes. See the
[exact day/meter split](billing-evidence.md#superseded-snapshot--18-october-2026-0125z).
T's only returned meter is **Intra Continent Data Transfer Out**, not a
same-region meter; T sent both cross-region and same-region traffic, so its
endpoint total cannot prove a charge for T → A. A's tiny positive costs do
not establish the same-region 100 GB leg's billing treatment. Queries report
**cost only: no quantity, unit or rate**; missing rows are not measured zeros.
Historical-C's two-day aggregate is **not** the old single-day
0.6551259830594063 “1 GB” row or its single-row cost: it includes the
15 October microcost as well.

The [earlier manual CSV attempts](results/2026-10-18-manual-billing-011054.json)
ended with **A timeout / T HTTP 422**, no CSV downloads. Accounting remains
**six manual requests total: two CSV generation attempts + four Queries**,
zero retries, no unused budget; this did not reset the budget. The older
23:02 check's separate six-request counter is unchanged. The public collector
safe-header fix is tracked in #19; changed `ClientType` is **not proven causal**
for the later Query success because wall-clock time also changed. No valid
retry hint was supplied; unknown cooldowns are not zero.

The last fresh-C CSV is still the **17 October 23:01:56Z** extraction:
**10.8746547754853965 reported “1 GB” × USD 0.02 =
USD 0.21749309550970793** on Intra Continent Data Transfer Out. It is a
partial cross-region observation, **not a new CSV or a full 100 GB match**.
No fresh A/T quantity/rate evidence or ingestion watermark was obtained.
Final payload verification ended **17 October 22:15:17Z**, only about three
hours before these Queries. The four 100 GB legs / 400 GB verification and
21-root cleanup PASS from #18 stand; **billing work remains open**.

**Next evidence target:** mature, comparable, meter/day/currency-separated
snapshots with quantities, units and rates, at least **six hours apart**,
reconciling fresh A/T/C and the distinct historical control. Using the
01:21:11Z Query completion as baseline, the earliest six-hour repeat is
**18 October 07:21:11Z**. Job 5's saved **~05:02Z** cadence suggestion
(actual due unverified) can collect another baseline, but cannot establish
six-hour stability against 01:21Z. No scheduling change is made here; the
existing **22 October 23:15:33Z hard stop** remains.

**Policy is separate from invoice proof:** the documented rule says transfers
between Azure services in the same Azure region are free; explicit cross-tenant
wording is absent, so applying it across tenants remains an interpretation.
BYOIP/custom-prefix traffic has an explicit Internet-egress exception; other
service processing fees are separate. See the [policy sources and scope](#policy-handoff-2026-10-18-same-region-cross-tenant-public-ip-egress).
This refresh used local artifacts only: no Azure/authentication, resource,
source-code, git or schedule operations.

## Superseded executive summary — 17 October 2026, 23:05Z

**Transport PASS; cleanup PASS; full billing reconciliation INCONCLUSIVE.**
The larger public-IP rerun completed **400,000,000,000 application bytes**:
exactly **100,000,000,000 bytes (100 decimal GB) in each direction** below.

| Leg | Regions | Tenant relationship | Target / verified bytes |
|---|---|---|---:|
| A → T | Sweden Central → Sweden Central | Different tenants | 100,000,000,000 / 100,000,000,000 |
| T → A | Sweden Central → Sweden Central | Different tenants | 100,000,000,000 / 100,000,000,000 |
| C → T | North Europe → Sweden Central | Different tenants | 100,000,000,000 / 100,000,000,000 |
| T → C | Sweden Central → North Europe | Different tenants | 100,000,000,000 / 100,000,000,000 |

All **80 completed directed chunk transfers** have matching producer/consumer
byte counts and SHA256, with **zero payload retries**. Two zero-credited failed
reservations remain in the ledger; this was **not a failure-free execution**.
See the [complete result](results/2026-10-17-large-rerun-complete.json),
[sanitized digest proofs](results/2026-10-17-large-rerun-digest-proofs.json)
and [short report](results/2026-10-17-large-rerun-complete.md).

**Actual billing answer:** the latest
[API-generated Cost Details CSV projection](results/2026-10-17-billing-refresh-230000.json)
contains fresh C's **17 October** `Intra Continent Data Transfer Out`:
**10.8746547754853965 × reported “1 GB” × USD 0.02 =
USD 0.21749309550970793** across three rows. This demonstrates a nonzero
cross-region bandwidth charge, **not reconciliation of the 100 GB C → T leg
or the 400 GB experiment**. “Intra Continent” is not “same region.”
CSV extraction completed at **23:01:56Z**; ingestion is not final and no
`DataIngestionEndMT` watermark was obtained. Three separate ResourceId+Meter
Queries (C, A, T) returned **HTTP 429**, not zero charges.
There is no fresh A/T CSV in this check, so same-region billing remains
inconclusive. The older C → B 1-GiB control's **0.6551259830594063 “1 GB”**
observation is **STALE**, not this new C result. CSVs are downloaded through
the report API, **not portal exports**.

All **21 owned resource roots in three endpoint RGs** were independently
verified absent at **22:49:03Z on 17 October**, before midnight.
The proof is parent-RG absence plus supporting root checks, **not 21 fresh
direct root GETs**. [Cleanup receipt](results/2026-10-17-large-rerun-cleanup.json).
Original disk SKUs were restored before deletion; no retained rerun compute,
disks or public IPs remain. Unknown historical resources were not adopted.
Cleanup job 3 is **STOPPED**. Existing six-hour read-only billing follow-up
is retained with its original **22 October 23:15:33Z hard stop**;
billing is **not complete** and no replacement job was created here.

Measured client-NIC RX+TX, counted once per completed pair, is
**403,432,913,305 bytes**; conservative reserved wire is
**461,173,529,602 bytes**, including failed reservations and bootstrap.
Neither is application volume or billed quantity. The final **470 GB wire /
86,400 seconds per VM (24 hours)** limits were coordinator-selected bounds
under autonomous-completion authority, **not user-selected numeric caps**.
The 25% forecast margin was retained. Money remained monitor-only with
**no fixed monetary cap**; the superseded USD 45 cap does not apply.

This report was prepared offline: no new Azure/billing/authentication calls,
resource changes, git publication or schedule changes.
The dated partial results and stop decisions below are historical, not latest status.

## Historical offline guard-performance recovery, 16 October 23:1xZ

The newly certified successor credits a second independently verified
5 GiB-per-direction A ↔ T pair, despite the historical ledger's terminal
forecast failure. Verified cumulative totals are now **11,811,160,064 bytes
(11 GiB) each A → T/T → A**, and **1,073,741,824 bytes (1 GiB) each
C → T/T → C**: **25,769,803,776 bytes (24 GiB)** total, with
**374,230,196,224 bytes remaining** toward the exact 400 GB target.
Historical ledgers/receipts/pins are untouched; the earlier failed attempt
without guest payload evidence still receives zero credit.

The root performance correction scopes full content-hash ancestry validation
to phase admission, Azure mutations and terminal credit, not runtime polls.
Every poll still checks current lease authority, STOP, expiry, counters and
session state. Future forecast failures preserve verified completion and block
only next work. See the [execution protocol](transfers/README.md#phase-scoped-integrity-and-durable-verified-credit).

The coordinator explicitly selected **24 hours/86,400 seconds per VM for the
new successor**, under autonomous-completion authority; this is not a
user-selected numeric cap. Defaults remain 12 hours, historical 16-hour
configs are immutable, the 25% margin remains, and the original **18 October
07:33Z absolute cleanup deadline always wins**. The conservative refreshed T
forecast is **3,600 + 39,822 + 19,330 = 62,752 seconds**: it retains
both failed attempts' full 5,400-second reservations rather than refunding
the salvaged pair to its shorter measured duration. Whole-schedule reserved
wire remains **449,628,707,842 bytes**, below the approved 460 GB ceiling;
one shared 8 GB bootstrap reserve is retained. Monetary mode remains
monitor-only with no monetary cap.

**Offline preparation only:** no next chunk or live lease was created, no
Azure/authentication operations were performed. Independent review of the
exact new source hashes is required before fresh live readiness/snapshot/batch
authority. Retained assets are not deleted or newly observed by this work.
Billing remains **INCONCLUSIVE**. The section below is historical.

## Historical larger rerun: verified partial result, stopped on 16 October

**16 October 2026, 20:49Z documentation refresh (offline): transport/restoration
PASS for completed chunks; billing INCONCLUSIVE; continuation STOPPED.**
The fresh three-endpoint rerun completed both 1 GiB-per-direction pilots and
one 5 GiB-per-direction A ↔ T batch. These are actual verified payloads,
not the earlier zero-payload blocked attempts:

| Directed leg | Verified application bytes | Completed payload |
|---|---:|---:|
| A → T | 6,442,450,944 | 6 GiB |
| T → A | 6,442,450,944 | 6 GiB |
| C → T | 1,073,741,824 | 1 GiB |
| T → C | 1,073,741,824 | 1 GiB |
| **Total** | **15,032,385,536** | **14 GiB** |

A/T are Sweden Central, in different tenants; C is North Europe in A's tenant.
All six completed directed transfers have agreeing producer/consumer byte
counts and SHA256, with **zero payload retries**. The target remains
**100,000,000,000 bytes per leg, 400,000,000,000 bytes total (decimal GB)**;
it is **not complete**. See the [sanitized partial result](results/2026-10-16-large-rerun-partial.json)
and [execution contract](transfers/README.md).

The first bulk batch's measured lifecycle overhead revises the full-session T
projection to **3,600 + 21,127 + 19,465 = 44,192 seconds (12h16m32s)**,
including the required **25% margin** on both phase forecasts. That exceeds
the unchanged **43,200-second/12-hour allocation cap by 992 seconds**.
Independent offline review found no arithmetic double count: the carry is
included once, concurrent directions are not summed, and full-phase forecasts
already include completed chunks. Actual conservative ledger allocation for T
is **5,521 seconds**, including prior carry; do not add that again to the
full-session forecast. The refreshed forecast is external stop evidence, not
a rewritten public ledger admission result.

**No next chunk or probe is authorized or queued.** A 13-hour cap would require
explicit user approval; none was obtained while the user was unavailable.
The user explicitly removed the former **USD 45 monetary ceiling**:
this session is **monitor-only, with no replacement monetary cap**. That
financial change does not relax the separate 12-hour runtime cap or margin.

Completed receipts verify participating VMs deallocated, original receiver
**NIC and subnet NSGs plus network associations restored**, and owned children
idle. Latest batch closure evidence is dated **20:43:18Z** and was subsequently
reviewed offline; this documentation refresh made no Azure calls. **All three fresh
endpoint resource sets remain retained**, not deleted: disks and public IPs
continue accruing charges pending guarded cleanup **before 18 October 07:33Z**.
No cleanup job or future continuation is established by this update.

Billing still requires attributable quantity/unit/rate evidence. Report dates
are **not ingestion watermarks**. The older C → B 1-GiB control and its
0.6551259830594063 “1 GB” row concern distinct historical IDs/scenarios;
they neither reconcile that control nor establish billing for this rerun.
Root lessons: valid asynchronous power-state responses without a published
power state are **UNPUBLISHED/pending**, never proof of running/deallocation;
keep public leases and receipts immutable after return, and record independent
stop decisions separately.

## Original experiment and historical billing checks

The remaining original-run results and caps below refer to the earlier resource
identities, not the retained fresh rerun assets or its monitor-only money mode.

**Status, 2026-10-16 UTC: same-region cross-tenant public-IP transport PASS;
restoration PASS; bandwidth billing INCONCLUSIVE.** A ↔ T exchanged exactly
5 GiB each direction at 10:04:25–10:40:28 UTC, with matching hashes and no bulk
retries. Following laptop sleep, recovery restored T's original NSG and verified
T/A deallocated at 14:07:37/14:07:40Z; independent validation reconfirmed both.
See the [completed result and dated follow-ups](results/2026-10-15-cross-tenant-public-ip.md).
The later [C → B inter-region control v4](results/2026-10-15-cross-region-control.md)
**transport/restoration PASS**: exactly **1 GiB**, one upload, zero retries.
Read-only v3 inspection identified B's additional subnet NSG default deny at
65500; v4 correctly allowed and restored **both NIC and subnet NSGs**.
Independent validation passed at **23:25:22Z, 15 October** (11 reads, 0 mutations).
Billing quantity reconciliation remains incomplete: this is not yet a fully
reconciled billed positive control.
Known-owned cleanup closed PASS at **00:00:11.806224Z, 16 October**:
13 remaining original core assets absent, C/T groups gone, all known lab
VMs/disks/PIPs deleted. **Core RG and one unproven-ownership NSG were preserved**,
not adopted/deleted. No active children or further transfer is queued.
Owner: Morpheus / Jose Moreno. Research retrieved **2026-10-15**.

**Historical billing check, 16 October 06:50:38Z:** C has an adjacent-day
**16 October** CSV row of **0.6551259830594063 “1 GB”**, effective price
**USD 0.02**, cost **USD 0.013102519661188125**, on
**Intra Continent Data Transfer Out**. Its separate **15 October** row is
**0.000002402812242508 “1 GB”**, cost **USD 4.80562448501586884E-8**.
The substantial charge is consistent with a bulk-sized control, but is **not
yet a full quantity match** to the 1-GiB transfer on 15 October 23:08–23:15Z.
Ingestion, units, coverage and attribution remain unresolved; the report date
is not a receipt date or exact transfer correlation. A has three endpoint rows,
B two (the original A-group query contains five); T now has one **EUR
7.4561667E-8** Query row, without quantity/unit/rate. No headline 5-GiB-scale
A/T charge or zero-rated meter is established. **Billing remains INCONCLUSIVE.**
Both Queries and fresh CSV extraction completed: five of six allowed HTTP
requests, zero retries/mutations, lease closed and native children idle.
See the [current sanitized check](results/2026-10-16-billing-check-0650.json).
That snapshot recorded a six-hour read-only follow-up expected around **12:50Z**,
not evidence here that a later collection ran or a future job is active;
control maturity starts no earlier than **16 October 23:15:33Z**, followed by
two stable comparable snapshots at least six hours apart.

**Historical 16 October 00:29Z billing update:** actual Cost Details CSV extraction now
works, with quantity/unit/effective-price preserved. C reports only
**0.000002291053533554 “1 GB” at USD 0.02** (cost
**USD 4.58210706710815400000E-8**), not the scale of the successful 1-GiB
control. Three source-A daily rows and two original B rows were also projected;
T was not refreshed. Six of 371 rows passed exact inventory/RG/date/Bandwidth
filters. One generation + one poll + one download, no retries/mutations,
contexts unchanged, lease closed/idle. The CSV schema blocker is resolved;
**billing maturity/transfer attribution still blocks a zero-charge conclusion**.
See [latest/history reconciliation](results/2026-10-16-usage-reconciliation.json).

Question: does a customer's VNet pay bandwidth when exchanging data with a
same-region Azure SaaS public endpoint, including another Entra tenant?

**Practical answer:** for ordinary Microsoft-allocated regional Azure public
endpoints in the same Azure billing region, **no additional bandwidth fee is
expected merely because tenants differ**. The published rule is unqualified by
tenant; this policy interpretation is separate from incomplete invoice proof.
The [billing verdict](results/2026-10-15-billing-verdict.md) preserves the
21:36Z Query history and adds the latest actual quantity/unit/rate evidence;
neither snapshot establishes a zero-rated 5 GiB intraregional meter. BYOIP and
service-architecture exceptions still apply.

**Additional deliverable:** discover and reproducibly query the Cost Analysis
APIs, including offer/schema-specific filter restrictions. Executable collectors,
offline contract tests, Windows versus native WSL findings, and the deployed
cross-tenant extension are in [costs/README.md](costs/README.md). Its
[copyable public commands](costs/README.md#commands-powershell-from-repository-root)
provide both daily ResourceId/Meter Query and filtered Cost Details CSV + JSON
workflows, without private wrappers or manually activated agent leases. Both contexts'
aggregate Query access works. WSL Consumption returned HTTP 200/empty with
valid explicit past usageStart/usageEnd dates on both tested versions; RG-only
HTTP 400 required dates, not blanket offer rejection. Empty data proves access,
not bandwidth attribution. The approved additional endpoint was deployed, subsequently tested and
deallocated; its original deployment record is [msdn-deployment-log.md](msdn-deployment-log.md).

Published Azure [bandwidth guidance](https://azure.microsoft.com/en-us/pricing/details/bandwidth/)
indicates same-region Azure-service transfers are not charged. Public addressing alone
does **not** establish Internet-egress billing. Apply the general same-region
rule across tenant boundaries as published-pricing guidance, not a confirmed
experimental exemption or explicit tenant-specific promise. Connectivity alone
does not prove tenant-independent billing.
The verified pricing FAQ asks **“Is data transfer between Azure services located
within the same region charged?”** and answers **“No. For example, an Azure SQL
database in the same region will not have any additional data transfer costs.”**
(Raw HTML verified 15 October 15:48Z.) It does not explicitly mention tenants.
**BYOIP exception:** [Microsoft Learn](https://learn.microsoft.com/azure/virtual-network/ip-services/custom-ip-address-prefix#pricing)
states “All traffic destined to a custom IP prefix range is charged the internet
egress rate”; Azure-origin traffic is charged at its source-region Internet
egress rate. Same-region SaaS is therefore not blanket-free: determine destination
IP ownership, regional placement and service architecture first.

## Policy handoff, 2026-10-18: same-region, cross-tenant public-IP egress

**Historical policy handoff:** its experimental snapshot and next-step wording
below are superseded by the 01:25Z executive summary and current
[billing evidence](billing-evidence.md). Its dated source-verification record
is preserved; no source was re-fetched during the offline 01:25Z refresh.

Bounded re-verification only; no Azure/billing/infra/auth calls made for this
section. Pure addition — no existing dated text above is altered.

**DOCUMENTED POLICY ANSWER.** Two official sources, re-checked this session:

1. [Azure Bandwidth pricing FAQ](https://azure.microsoft.com/en-us/pricing/details/bandwidth/)
   — “Is data transfer between Azure services located within the same region
   charged?” / “No. For example, an Azure SQL database in the same region will
   not have any additional data transfer costs.” Original raw-HTML verification
   timestamp **2026-10-15 ~21:34Z** (recorded above/in
   [results/2026-10-15-billing-verdict.md](results/2026-10-15-billing-verdict.md)).
   This session (**2026-10-18, ~00:xxZ**) a direct re-fetch of the FAQ accordion
   was attempted via both markdown extraction and paginated raw HTML; both only
   returned the static Zone 1/2/3 table, not the FAQ markup (it is client-rendered).
   A search-engine query independently surfaced the same FAQ sentence as still
   indexed/live on this URL — treated as reconfirmation of currency, **not** a
   fresh verbatim capture.
2. [Custom IP prefix (BYOIP) pricing](https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/custom-ip-address-prefix#pricing)
   — re-fetched in full this session via Microsoft Learn MCP (**2026-10-18**,
   exact minute not logged by the fetch tool): “There's no charge to provision
   or use custom IP prefixes… All traffic destined to a custom IP prefix range
   is charged the internet egress rate… Customers [sic] traffic to a custom IP
   prefix address from within Azure are charged internet egress for the source
   region of their traffic. The system charges egress traffic from a custom IP
   address prefix range at the same rate as an Azure public IP from the same
   region.” Matches, and slightly extends, the citation already on file above.

Neither source mentions subscriptions, Microsoft Entra tenants, or billing
accounts. **Do not infer that “same-region is free” by itself clears every
other charge.** It is scoped only to the Azure bandwidth/data-transfer meter.
It does not address, and does not zero out:
- VNet Peering, Private Link/Private Endpoint, NAT Gateway, or Azure Firewall
  public-IP processing fees — each is a **separate billed product**, same-region
  or not.
- Whether traffic stays on Microsoft's backbone inside the region or traverses
  a path a different meter counts as off-region — the FAQ states an outcome,
  not the routing mechanism producing it.
- A **custom (BYOIP) public IP**, explicitly carved out above as Internet egress
  regardless of same-region placement.
- Any destination whose **actual Azure billing region differs from the origin
  VM's region** — a SaaS product's name, DNS hostname, or tenant location does
  not establish its backend region. An unverified-region SaaS is out of scope
  for a same-region claim until its region is independently confirmed.

**Tenant/subscription boundary, explicitly:** neither source states a
tenant-boundary rule. Applying the same-region rule across an Entra tenant or
subscription boundary is this lab's **interpretation of an unqualified
published rule**, not a quote of an explicit cross-tenant statement.

**EXPERIMENTAL VERDICT: INCONCLUSIVE.** Unchanged from the dated results above:
the 400 GB / 4-leg rerun passed transport on all legs, and the C-endpoint
cross-region (`Intra Continent Data Transfer Out`) meter shows a real, nonzero
charge (10.8746547754853965 × “1 GB” × USD 0.02 = USD 0.21749309550970793,
17 October) — proving the billing pipeline *can* register a charge for a
cross-region leg. The matching **same-region A/T CSV rows are still missing**
(three Query attempts returned HTTP 429). **Absence of a same-region A/T row
is not zero-rated proof** — it is missing data, not a measured zero.

What would still be needed to move past INCONCLUSIVE: a mature, HTTP-200,
multi-snapshot (≥6h apart) A/T Cost Details CSV covering the actual
same-region transfer date with quantity/unit/rate present (the shape already
obtained for C's cross-region leg), and a scale-confirmed same-region positive
control whose reported quantity plausibly matches the transferred bytes.

**Can a daily Cost Details CSV, by itself, prove which tenant hosts the SaaS
endpoint? No.** The CSV reports only the caller's own billed meters/quantities;
it carries no field identifying the counterparty's tenant, subscription, or
hosting region. Third-party SaaS tenant/region attribution would require
evidence outside this billing export, which is out of scope here.

**Could a same-region public-IP pair be using an internal/Microsoft-backbone
routing path instead of the public Internet, independent of billing? Unproved,
not assumed.** No IMDS, NIC flow log, or packet capture was collected in this
lab to confirm the actual forwarding path for the A/T legs; the billing outcome
so far (no separate meter yet observed) does not by itself demonstrate the
routing mechanism. This is a capture-path gap, not a “no” finding to rely on.

**Scope note:** this section covers only the ordinary-public-IP, same-region,
cross-tenant case already under test. PaaS-specific billing and any new
deployment are deferred, per the bounded scope of this handoff. Private
summary: [private/policy-handoff-20261018.private.md](private/policy-handoff-20261018.private.md)
(internal only, not published).

## Original core approval card (schedule subsequently reprioritized)

Recommend the three-concurrent-VM staged core: two Sweden Central VMs and one
North Europe VM, plus a short-lived private-control identity replacing the latter
before cross-region testing. Maximum four VM identities created, three concurrent.
Ubuntu 22.04, provisional B-series, 30 GiB Standard SSD, instance Standard IPv4 PIPs.
One new dedicated RG; no peering, NAT, LB, Firewall, gateway or paid log workspace.

- Three isolated UTC billing days; at most **12 allocated hours per VM slot**,
  **72 hours** disk/PIP lifetime. Deallocate between sessions.
- Six directed 5 GiB transfers: **30 GiB payload**, **35 GiB total wire-data cap**.
- Conservative envelope: **$0.08/hour** infrastructure, **$2/day** continuous
  infrastructure; **$8 lifetime** including traffic, disk operations and contingency,
  excluding tax. Not an account-specific quote or platform-enforced budget.
- Collect billing at 24/48/72 hours, final bounded follow-up day 7;
  **do not retain VMs, disks or PIPs while waiting past their resource TTL**.
- The initial catalogue probe timed out; Sweden Central capacity subsequently
  passed; North Europe subsequently passed catalog/allocation gates for C. Aggregate and
  detailed billing access succeeded, including quantity/rate schema access.
  The Windows modern detailed endpoint did not honor the tested RG filter: collectors must
  filter rows in memory before saving anything. See [preflight.md](preflight.md).
  Sweden Central B1ls/B1s had location restrictions; B2ts_v2 passed the bounded
  catalogue, native ARM validation and actual provisioning gates. All three
  use **Standard_B2ts_v2**, nonzonal. See [deployment-log.md](deployment-log.md).

## Historical D0 deployment state (07:42Z, before the transfer)

Only A/B/P in Sweden Central were deployed: three VMs, three 30 GiB Standard SSD
disks, three NICs/NSGs, two Standard IPv4 PIPs and two unpeered VNets, in one new
owned tagged group. A/P share a VNet; P has no PIP or implicit outbound.
All resources have the required ownership tags. No C/North Europe resources.

All inbound is denied, including private traffic; no transfer listener, runner,
bootstrap download or public SSH opening was installed. The reproducible native
ARM and guarded deployment/cleanup scripts are in [deploy](deploy/README.md).
Local parser/safety checks, ARM validation, actual VM provisioning and deallocated
power-state checks passed. This does **not** validate transport or billing.

Six approved mutation commands were used (group create, ARM validation, ARM
deployment, three deallocations); the deployment lease is completed and all
owned child commands exited. **At that historical point, disks and PIPs still incurred rent**; enforce the
72-hour resource lifetime. Standing cleanup authority now covers only known,
owned lab assets under a fresh exact-inventory cleanup lease.
At deployment closure, the next D0 step was to implement the bounded pinned-mTLS harness with peer-only 443
rules, then assign fresh execution and validation leases under the approved
core scope and caps. No traffic is authorized under the completed deployment
lease; further user approval is needed only for changes outside that scope.

See [design.md](design.md), [scenarios.json](scenarios.json),
[billing-evidence.md](billing-evidence.md), and
[context-isolation.md](context-isolation.md). Optional PaaS, Storage, routing,
and Internet controls require separate approval and costs. Jose subsequently
approved using the existing authenticated WSL MSDN subscription and the
**additional $4** cross-tenant endpoint, without changing the $8 core.

## Historical MSDN endpoint T deployment state (08:23Z)

One **Standard_B1s**, nonzonal Ubuntu 22.04 Gen2 VM in Sweden Central, in a new
owned group: one 30 GiB StandardSSD_LRS disk, NIC, NSG, Standard static IPv4
PIP and unpeered VNet/subnet (`<T_PRIVATE_SUBNET_PREFIX>`, implicit outbound disabled).
B1ls is below the 1 GiB minimum; B1s passed the native MSDN catalog and has the
same verified $0.0108/hour retail rate as the approved B2ts_v2 ceiling.
ARM validation and actual allocation succeeded; all six resources are tagged
and provisioned successfully. T was verified **deallocated at 08:22:55Z**.
The WSL tenant/subscription differ from Windows; Windows context stayed unchanged.

All inbound is denied at priority 100; no SSH rule, bootstrap download,
extension, listener or traffic harness was added. Four mutation commands:
group create, ARM validation, deployment and deallocation. The lease is completed
and owned processes are idle. See [deploy/README.md](deploy/README.md) for the
reusable isolated WSL deploy/cleanup pair and ignored private inventory.
**At that historical point, disks and PIP kept accruing charges**: T's individual cutoff was
**2026-10-18 08:20:59Z**, but use the earlier whole-lab cleanup deadline
**before 2026-10-18 07:33Z**, under standing own-assets cleanup authority and
a fresh exact-inventory lease. T was retained then; its group is now deleted.

Jose approved the **$8 three-day core subject to prerequisites** on 2026-10-15.
This does not approve optional phases, SKU/cost increases, or unrelated cleanup.

## Original-run evidence, budget and next gates (historical scope)

The headline A ↔ T public-IP test took priority on **15 October**, instead of
the original D0 private-control traffic. A is in the Windows native context;
T is in native Ubuntu-24.04 WSL, with unequal tenants and subscriptions verified.
Both are Sweden Central Linux VMs; Windows/WSL describe management contexts,
not guest operating systems. Both TCP connections originated at A, while the
download's bulk-byte producer was T. The later C → B v4 control also completed,
without changing this original headline result.

Initial attributed billing collection at 14:14:58–14:15:11Z produced **Windows
HTTP 200 COMPLETE empty**, but **WSL HTTP 429 rate_limited ERROR**, not two
successful empty results. Neither proves free traffic. Mature quantity/unit/rate
evidence and a scale-confirmed known-charge positive control on the relevant
offer/feed remain necessary; tiny A/B/C quantities are now available from the
00:29Z CSV. The **18:22Z refresh** returned HTTP **429 ERROR** for both
aggregates. Windows details were **200 INCOMPLETE**: 1,000 unrelated rows
discarded in memory and a continuation remaining. WSL details were **200
COMPLETE empty**, not zero-charge proof. See the
[sanitized refresh](results/2026-10-15-billing-refresh.json),
[billing reconciliation](billing-evidence.md) and
[collector findings](costs/README.md).

- No budget increase or new resource creation during the transfer/recovery:
  **$8 core + $4 extension** remain the caps.
- Historical reserves left **11 GiB after v2**, then **5 GiB before v4**.
  v4 explicitly reserved **2 GiB wire for 1 GiB payload**, leaving
  **3 GiB (3,221,225,472 bytes)** conservatively reserved. The default
  control remains 5 GiB payload / 6 GiB wire. This is not measured payload use
  or authorization for more transfers. T's approved 10 GiB payload reserve is
  consumed; additional T payload requires approval.
- A/T allocation is conservatively about **4h10m each including readiness and
  recovery**, not a measured actual allocation-start time; hard limit remains
  <12h/slot. Recompute headroom from private lifecycle records before more work.
  Deallocation stopped compute, not retained disk/PIP charges; known assets
  have now been deleted.
- C replaced the retired P slot: P's VM/disk/NIC/dedicated NSG are gone;
  shared networking and A/B were preserved then. C used an isolated
  North Europe owned RG, now deleted. The inherited whole-core planning envelope was
  **$7.954831 < $8**, not an actual bill. Pre-control, C's inherited slot had roughly **2h
  before deducting readiness and ~5m setup**; reconcile lifecycle records before
  proposing further allocation. Neither TTL nor the original slot is reset.
- Collect 15 October usage no earlier than **16/17/18 October 10:40:28Z**
  (24/48/72h); if needed **22 October 10:40:28Z** (day 7).
- **Cleanup completed before late billing:** T's original cutoff was **18 October 08:20:59Z**;
  the earliest recorded core resource expires **18 October 07:38:11Z**,
  and the conservative original core deadline was **18 October 07:33Z**.
  Known-owned cleanup closed **16 October 00:00:11.806224Z**.
  Core RG and an extra NSG remain preserved for manual ownership review;
  they have no standalone hourly rent. Query private historical IDs after deletion.
- **Control v1, 17:28:50–18:13:46Z: FAIL**, 12 connection/TLS timeouts,
  zero bulk requests, C RX+TX once **284,630 bytes**. The saved NSG `Updating`
  response did not prove causation; v3 read-only inspection later identified
  the additional B subnet NSG deny missed by NIC-only setup.
- **Control v2: fresh readiness PASS; guarded live BLOCKED** by a NIC read
  timeout before either guest command, **zero payload**. Final NSG GET also
  timed out; this unverified closure was subsequently resolved by fresh Niobe
  read-only verification (**5 calls, 0 mutations**, idle proof 19:06:07Z).
  See [control safeguards](transfers/README.md#one-way-core-positive-control).
- **v4 PASS**, live **15 October 23:06:00–23:19:39Z**, bulk
  **23:08:23–23:15:32Z**, exactly **1,073,741,824 bytes C/NE → B/SC**,
  one upload/zero retries, matching SHA256. C NIC RX+TX once
  **1,085,524,745 bytes** is not billed quantity. Both original NSGs restored
  `Succeeded`; independent validation PASS. **100 WSL tests passed**.
- All known A/B/C/T VMs/disks/PIPs are deleted. A successful expected-charged
  transport control now exists, but its **billing positive control is pending**.
  The **23:28Z** snapshot made three billing requests: A's same three tiny
  rows (~$0.000072875), no quantity/request attribution; C no Query rows and
  details timeout; T empty. None proves zero cost. Invoice-level confirmation
  needs mature attributable meter quantity/unit/rate evidence; the practical
  published-pricing answer above does not depend on more unapproved payload.
- **Historical 16 October 00:21Z reconciliation was INCONCLUSIVE:** C-only daily
  ActualCost now returns **USD 0.0000000458210706710815**, without quantity,
  unit, effective rate or request attribution. Cost Details generation and a
  memory-only CSV download succeeded, but CSV schema validation blocked
  extraction; offline parser tests do not prove the discarded report parsed.
  Fresh 00:29Z live projection subsequently resolved the schema blocker;
  the reported control quantity remains far below 1 GiB, so billing is still
  INCONCLUSIVE.
  A/T were not refreshed. The bounded billing lease is closed/idle, zero
  mutations/owned native children. See the
  [sanitized reconciliation](results/2026-10-16-usage-reconciliation.json)
  and [collector changes](costs/README.md#cost-details-route-investigation-16-october).
- Control billing targets: **16/17/18 October 23:15:33Z** (24/48/72h);
  the 72h target is after the original **18 October 07:33Z** TTL deadline.
  No more transfers are needed; preserve and query historical IDs.
  Require two stable future cumulative snapshots, both at/after **16 October
  23:15:33Z**, with a scale-confirmed charged control and comparable A/T
  coverage before supporting a scoped **no additional charge observed**
  conclusion. Stability alone does not prove a zero-rated meter or final invoice.
- Standing cleanup authority is limited to known owned assets. **No automatic
  follow-up or cleanup job is established**. These dates are action deadlines,
  not scheduled jobs. No extra-cost scope or further MSDN payload is approved.

The guest's bounded foreground commands and persisted reports enabled recovery,
but a sleeping laptop cannot guarantee cloud deallocation. No automatic
cloud-cleanup guarantee is claimed. This documentation publication made
**zero Azure calls or mutations**.
