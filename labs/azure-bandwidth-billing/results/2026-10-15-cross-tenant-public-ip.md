# 15 October 2026: same-region cross-tenant public-IP transfer

**Transport PASS · restored baseline PASS · billing INCONCLUSIVE**

**Current update, 2026-10-16 UTC:** the original **5 GiB each direction**
headline PASS below is unchanged. The later
[C → B v4 control](2026-10-15-cross-region-control.md) is **transport/restore
PASS**, exactly **1 GiB C/NE → B/SC**, one upload, zero retries; independent
PASS **15 October 23:25:22Z**, 11 reads / 0 mutations. v3 read-only inspection
identified B's additional subnet NSG default deny 65500, missed by NIC-only
setup; v4 correctly allowed/restored both owned layers. Earlier v1/v2/v3
failed/blocked records remain historical.
The **23:28Z** billing snapshot still has only A's three tiny daily rows,
**USD 0.0000728753264993429373**, no quantity/unit/rate/request attribution;
C no Query rows/details timeout; T empty. This is **not yet a billed positive
control**, not zero-charge proof or invoice confirmation.
Known-owned cleanup closed PASS **16 October 00:00:11.806224Z**:
13 remaining original core assets absent, C/T groups gone, all known lab
VMs/disks/PIPs deleted. **Core RG and an extra NSG remain preserved**, creation
ownership unproven; do not adopt/delete. No standalone RG/NSG hourly rent.
The detailed earlier observations below are dated history, not current retention.

**Later interpretation, 21:36Z:** [exact billing rows and practical pricing
answer](2026-10-15-billing-verdict.md). For ordinary same-region Azure regional
public endpoints, no additional bandwidth fee is expected just because tenants
differ. This follows the general published rule, not invoice proof. The three
observed rows are tiny positive costs attributed to A; “Intra Continent” is not
an intraregional zero-rated 5 GiB meter. Historical snapshots below are unchanged.

Published from the independent Niobe validation/cost handoff, persisted
**2026-10-15T14:17:09Z**, after live/recovery owners were idle. This publication
was offline: **zero Azure calls, zero Azure mutations, no new transfers,
resources or packages**. Private evidence was projected into this narrative;
no raw reports, identities, endpoint addresses, resource names or keys are included.
Updated offline after the **18:22Z billing refresh** and fresh independent
control-baseline/idle verification at **19:06:07Z**. Headline verdicts stand;
then-observed C→B control outcomes were **v1 FAIL / v2 BLOCKED**, not PASS.
The later v4 PASS is a separate result, not a rewrite of those records.

## What was actually tested

Two newly owned Linux VM endpoints in **Sweden Central**, in unpeered VNets,
communicated through their instance **public IPs** using pinned mTLS:

| Alias | Native management environment | Ownership/model |
|---|---|---|
| A | Windows Azure CLI | Core subscription/tenant, public-IP VM client |
| T | Ubuntu-24.04 WSL Linux Azure CLI | Separate MSDN-alias subscription and tenant, public-IP VM server |

Actual tenant IDs and subscription IDs were independently checked as **unequal**
privately; native contexts remained unchanged. Windows/WSL identify CLI contexts,
not Windows guest versus Linux guest. No token/profile copying, account switching,
SSH opening or package installation was part of the transfer.

Both HTTPS connections were **initiated by A**. Upload was **A → T** bulk
production; download was **T → A** bulk production. TCP initiation must not be
used to assign outbound producer charges.

This is a VM-based regional SaaS endpoint simulator, not a test of a real SaaS
provider's CDN, Front Door, anycast, cross-cloud path or provider fees. PaaS,
Storage, routing-preference and true ASE comparisons remain untested/deferred;
true ASE requires separate cost approval.

## Exact transfer evidence

| Signal | Independently validated result |
|---|---|
| Full client/server interval, UTC | **2026-10-15T10:04:25.588424Z–10:40:28.237747Z** |
| Bulk request starts | Approximately **10:04:40.603Z**, after readiness |
| A → T payload | **5,368,709,120 bytes (5 GiB)** |
| T → A payload | **5,368,709,120 bytes (5 GiB)** |
| Combined payload | **10,737,418,240 bytes (10 GiB)** |
| Endpoint records | Four: both directions at both endpoints, exact counts, expected peer, matching expected SHA256, HTTP 200, success |
| Bulk retries | **0** |
| Readiness | Three connection-refused probes, each **0 payload bytes**, then successful fourth handshake |
| One-endpoint NIC corroboration | **A RX + TX once = 10,818,818,041 bytes** |
| NIC excess above combined payload | **81,399,801 bytes**, protocol/background traffic |

Expected payload SHA256, matched by all four records:

```text
75b8584d16aee90a4bf4ae52b11e3362a6193ba0e5b7a0a595f6b569a381eb3f
```

The two directions ran concurrently, each rate-capped at 20 Mbit/s. Streamed
deterministic payload was incrementally hashed, not buffered as a 5 GiB disk
file. Records were persisted by guests before recovery. Independent validation
reproduced recovered compact report lengths/hashes against the raw captures.

**Accounting boundary:** A's RX+TX counts both traffic directions at one endpoint.
Do not add A and T, call this measured Internet egress, or equate it with billed
outbound. NIC counters include TLS/ACKs and background traffic. Azure metrics
corroborate transport, not meter quantity or charge. No packet capture or
independent guest clock synchronization was available.

## Sleep incident, recovery and final safety state

The laptop slept while the Azure guest tasks continued. They completed and
persisted reports; the original laptop-side invocation timed out and could not
restore the cloud resources while asleep. That local failure was **not a bulk
transport failure**, and the original blocked invocation record was not rewritten.

| UTC, 15 October | Event |
|---|---|
| 10:04:25–10:40:28 | Readiness and completed bidirectional transfer |
| 14:02–14:08 | Morpheus recovery captured guest reports and restored the baseline |
| 14:07:37.110024 | T verified **PowerState/deallocated** |
| 14:07:40.574045 | A verified **PowerState/deallocated** |
| 14:08:17 | Recovery closure: transport/restore PASS, no restart needed |
| After 14:09 | Niobe independently checked recovered records, bindings and restoration |
| 14:13:21.856587 / 14:13:26.899033 | Fresh A/T deallocation and original-rule verification |
| 14:16:56 | Independent validation lease completed; native owned processes idle |
| 14:17:09 | Persistent validation handoff |

Every original T NSG security-rule field matched after recovery except the
Azure service-managed **ETag**. Rule identity, access, protocol, priority, ports,
prefixes, provisioning state and all other fields were compared; rule changes
are **not** excluded. A's original rules matched as JSON objects. No listener
remained in recovery captures; both verified deallocations are the final kill
boundary. B/P were outside the transfer/recovery scope.

The original live owner used **5 mutation submissions**; recovery used **5**,
including two foreground report-capture RunCommands, one NSG restoration and
two deallocations. Prior readiness used **2 × 6**; deployment baselines used
**6 core +4 T**. These are scoped command counts, not HTTP request counts or
bulk retries. Independent Niobe validation used zero mutations/payload.

**Sleep resilience is limited:** bounded foreground guest tasks plus persisted
reports allowed recovery without restarting or replaying payload. A laptop-side
orchestrator cannot guarantee deallocation while the laptop is sleeping.
There was **no automatic cloud cleanup**; an explicit recovery owner restored
the resources hours later.

## Initial billing is not an exemption result

Niobe ran one collector invocation per native producer context, approximately
3.6h after the transfer. Request shape: **ActualCost / Daily /
ResourceGroup AND MeterCategory=Bandwidth / ResourceGroup+Meter /
Sum(PreTaxCost)**. Requested Query envelope was the actual usage day,
**2026-10-15T00:00:00Z–23:59:59Z**, not ingestion day.

| Context | Collection interval UTC | Exact outcome |
|---|---|---|
| Windows / A | 14:14:58.735226–14:15:07.118577 | **HTTP 200, COMPLETE**, one page, zero received/retained rows |
| Native WSL / T | 14:15:07.183049–14:15:11.048326 | **HTTP 429, rate_limited ERROR**, no cost snapshot, completeness not established |

Windows completed the requested pagination, **not billing maturation**. WSL
failed to obtain rows; it was **not a successful empty result**. The collector
permits at most one short eligible Retry-After retry internally; exact HTTP
attempt count is not exposed by the sanitized failure and is not asserted.
There was no second collector invocation, detailed-usage call or extra shape probe.

At that initial collection, billing was **INCONCLUSIVE** because no mature attributable bandwidth
quantity/unit/effective-rate evidence or same-offer/feed known-charge positive
control is available. Empty rows, zero aggregate cost, credits or allowances
cannot establish absence of charge. This Bandwidth-category snapshot also cannot
account for every networking/service processing fee.

Published [Azure bandwidth guidance](https://azure.microsoft.com/en-us/pricing/details/bandwidth/)
indicates same-region Azure-service transfers are not charged; tenant boundary
alone is not an established charging trigger. Public IP alone does not mean
Internet egress, and successful cross-tenant connectivity does not prove
tenant-independent billing. **No experimental exemption is confirmed.**
The public pricing raw HTML was verified at **15 October 15:48Z**. Its exact FAQ:
**“Is data transfer between Azure services located within the same region charged?”**
Answer: **“No. For example, an Azure SQL database in the same region will not have
any additional data transfer costs.”** It does **not** explicitly mention tenants;
this is not a new binding cross-tenant promise.

**Verified exception:** [official custom IP prefix pricing](https://learn.microsoft.com/azure/virtual-network/ip-services/custom-ip-address-prefix#pricing)
states **“All traffic destined to a custom IP prefix range is charged the internet
egress rate”** and says Azure-origin traffic is charged Internet egress for its
source region. Therefore a same-region SaaS blanket-free answer is unsafe until
IP ownership and service architecture are known. This is official product guidance,
not a Microsoft Q&A/community pricing claim; BYOIP itself was not tested here.

### Established API findings, separate from this run's billing outcome

- **Meter grouping works** with ResourceGroup; **MeterId returned HTTP 400**.
- Windows Consumption RG filtering returned unrelated rows in the tested
  modern schema. Client-side inventory/RG/**actual usage UTC** filtering before
  persistence is mandatory; unrelated values are discarded in memory.
- Native MSDN Consumption **2019-10-01 and 2024-08-01** accepted valid past
  usageStart/usageEnd ranges with HTTP 200 empty. Earlier missing/future-date
  errors do not mean the offer is blanket unsupported. Empty responses do
  not prove filter compliance or actual row schema.
- **429 is an error, not empty**. Incomplete pagination is not zero.
  Cumulative snapshots are revisions, never additive independent usage.
- Cost/credit/allowance information cannot alone establish no metering.
  Legacy request date ranges can concern receipt; inspect actual row usage
  dates and authorize bounded past-window expansion for late data.

Runner operational corrections are not Cost API findings: Azure Monitor
metrics require a **minimum 60-second window**, and case-insensitive ARM
managed-disk ID comparison corrected false casing-only binding mismatches.
Actual replacement/storage changes still fail closed. The archived headline
validation used **34 passing tests**. Later one-way control support changes source
hashes and requires fresh readiness for any new run; it does not invalidate or
rewrite the archived independent validation of the completed headline.

## Historical caps, lifecycle and cleanup requirements

User caps remain **$8 core + $4 extension**, with no increase. Transfer/recovery
created no other resources. No actual billed-dollar total is claimed.

- Reserve the full **12 GiB** headline allowance and **6 GiB per control
  attempt**, despite lower measured/no payload use:
  **35 − 12 − 6 − 6 = 11 GiB (11,811,160,064 bytes) core remaining**.
  This is conservative reservation accounting, not actual payload usage;
  the earlier 17 GiB before v2 is not current headroom.
- **Later reconciliation:** 11 GiB was historical post-v2 headroom. Before v4
  it was **5 GiB**; explicit **1 GiB payload / 2 GiB wire** left
  **3 GiB**, not actual payload usage or permission for more tests.
  The default control remains 5 GiB payload / 6 GiB wire.
- T's approved **10 GiB payload reserve is consumed**. No additional T payload
  is approved; no approval is implied by remaining core bytes or time.
- Conservatively allow **about 4h10m per A/T slot including readiness/recovery**,
  not an invented actual allocated-start timestamp. Recompute remaining headroom
  from private lifecycle evidence before any further scenario; hard limit
  remains **<12 allocated hours per slot**.
- Deallocation stops compute but **disks and public IPs remain billable**.
  Their 72h lifetime must not extend for cost-data collection.
- P's VM/disk/NIC/dedicated NSG were retired; shared networking was preserved.
  C deployed in an isolated North Europe owned RG and inherited P's slot.
  A/B/C/T were then deallocated; known-owned assets are now deleted.
  The whole-core planning envelope was
  **$7.954831 < $8**, not an actual bill. Pre-control, C's inherited slot had roughly **2h
  before deducting readiness and ~5m setup**; reconcile lifecycle evidence before
  further proposals. Replacement does not reset hours or TTL.

| Inventory | Resource lifetime cutoff |
|---|---|
| T | RG creation 15 October 08:20:59Z → **18 October 08:20:59Z** |
| Core | Earliest recorded resource creation **15 October 07:38:11.583268Z** → **18 October 07:38:11.583268Z**; RG can be older |
| Conservative core cleanup scheduling | **Before 18 October 07:33Z**, using deployment-lease start +72h pending exact private RG creation check; any earlier actual deadline wins |

The original standing cleanup requirement covered known owned assets: use a fresh
exact-inventory lease and delete absolutely **before 18 October 07:33Z**,
earlier if actual creation requires it. Preserve private historical resource IDs, timestamps and
ownership map first. **Delete before TTL and query historical IDs after deletion**.
Do not keep any VM/disk/IP merely to reach the 72h/day-7 billing follow-ups.
The recorded T TTL and earlier core cutoff both precede the 72h follow-up.
Known-owned deletion completed at **16 October 00:00:11.806224Z**; the core RG
and an unproven-ownership NSG were deliberately preserved for manual review.
The earlier whole-group cleanup BLOCKED history was resolved for exact-owned
roots, not by adopting or deleting unknown resources.

## Dated blockers and safe next work

As of **15 October 19:06:07Z**, headline transport and the independently
verified baseline are PASS; **billing remains INCONCLUSIVE**.

### Later billing refresh and control outcomes

The [18:22Z sanitized refresh](2026-10-15-billing-refresh.json) used one
invocation/HTTP attempt per endpoint/context, no retry and at most one page:

| Context | Aggregate Query | Consumption details |
|---|---|---|
| Windows core | **HTTP 429 ERROR** | **HTTP 200 INCOMPLETE**; 1,000 unrelated rows discarded in memory, 0 retained, continuation remaining |
| Native WSL / T | **HTTP 429 ERROR** | **HTTP 200 COMPLETE empty**; 1 page, 0 rows |

These are not zero charges or a mature feed. Receipt-window predicates cannot
guarantee eventual actual-usage coverage. RG filtering was not honored in the
Windows response; mandatory local inventory/RG/actual-date filtering prevented
unrelated billing retention. Missing quantity/unit/rate/cost remain null,
not zero. No attributable charged positive control was established by that refresh.

The minimal **C/North Europe → B/Sweden Central**, Windows-core, one-way 5 GiB
control was deployed after P retirement, with C's producer RG isolated from
the headline RG. Its actual attempts were:

| Phase | Verdict | Decisive facts |
|---|---|---|
| v1, **17:28:50–18:13:46Z** | **FAIL** | 12 connection/TLS timeouts, 0 bulk requests, 0 bulk retries. C RX+TX once **284,630 bytes**; not bulk payload or billed quantity. |
| v2 fresh readiness | **PASS** | Fresh source-bound readiness, not transport success. |
| v2 guarded live | **BLOCKED before guest commands** | NIC read timeout before server/client submission; **0 payload**. No guest NIC report, so do not invent a zero wire count. Final NSG GET timed out, leaving restoration initially unverified. |
| Fresh independent Niobe check | **PASS** | **5 reads, 0 mutations**; exact original B NSG policy/all rules `Succeeded`, NIC association correct, B/C deallocated. Native idle proof **19:06:07Z**, no active children, no further transfer queued. |

At that time, v1's packet-path cause was unproven. Its saved NSG `Updating`
response alone did **not** establish causation. Later v3 read-only inspection
identified B's additional subnet default deny; v4 corrected both layers.
The corrected runner now requires bounded `Succeeded`/exact intended NSG and
NIC-association setup gates, exact original-policy `Succeeded` readback on
restore, a **180-second first-request deadline**, immediate failure visibility,
bounded peer drain and verified deallocation **before** NSG restore.
**67 existing WSL tests passed** at that correction; the later v4 suite reached
**100 WSL tests**, and separately authorized v4 live transport passed.
No Windows-suite pass is claimed. Later restoration PASS does not rewrite v1/v2
transport verdicts. See [control safeguards](../transfers/README.md#one-way-core-positive-control).

A Windows charged control would not establish MSDN feed completeness.
Closing the experimental invoice proof still needs mature meter quantity/unit/
rate evidence. The FAQ's general same-region rule reasonably applies across
tenant boundaries without enumerating them; the official BYOIP destination
Internet-egress exception above remains.

| Follow-up for 15 October usage | Earliest UTC |
|---|---|
| 24h | **2026-10-16T10:40:28Z** |
| 48h | **2026-10-17T10:40:28Z** |
| 72h | **2026-10-18T10:40:28Z** — after resource cleanup |
| Day 7, if needed | **2026-10-22T10:40:28Z** — historical usage only |

Control 24/48/72h targets are **16/17/18 October 23:15:33Z**; 72h is after
the original **18 October 07:33Z** TTL deadline. All future snapshots use private
historical IDs after known-owned cleanup, not new transfers. No schedules exist.

Each requires a fresh approved read-only cost/API lease, new private per-source
snapshots, bounded calls/pages, native context checks and no background waits.
Use the [existing collector's exact follow-up commands](../costs/README.md#dated-follow-up-commands-for-the-completed-run).
Compare cumulative snapshots; never sum them. If day-7 evidence is still
insufficient, close inconclusive and seek separately authorized billing review.
**No automatic follow-up or cleanup job is established.** These dates are
required next actions, not scheduled automation. Standing own-assets cleanup
authority does not approve extra-cost work or further MSDN payload.

**15 October was the headline same-region cross-tenant day**, replacing the
original private D0 traffic priority. Put other bulk families on distinct UTC
days to preserve producer/day attribution. The next intended known-charge
positive control was initially **16 October, Sweden Central ↔ North Europe**;
the later minimal amendment was **C/North Europe → B/Sweden Central only**.
C was deployed; v1 failed and v2 blocked before bulk. Later v4 succeeded with
**1 GiB** and both NSG layers restored/independently verified, then known-owned
cleanup completed. No additional transfer is needed or queued. Any further proposal must reconcile remaining core bytes/hours,
budgets and cleanup timing and obtain fresh execution/validation leases.
No extra T payload, resource expansion or higher SKU is authorized by this plan.

## References and reproducibility

- [Lab overview and original deployment history](../README.md)
- [Design, official references and verdict criteria](../design.md)
- [Billing reconciliation and attribution](../billing-evidence.md)
- [API matrix, filtering and exact commands](../costs/README.md)
- [Runner contract, operational notes and test history](../transfers/README.md)
- [Azure bandwidth pricing](https://azure.microsoft.com/en-us/pricing/details/bandwidth/)
- [Routing preference](https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/routing-preference-overview)
- [Cost data timing and credit semantics](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data)
- [Query API](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2023-11-01)
- [Consumption Usage Details](https://learn.microsoft.com/en-us/rest/api/consumption/usage-details/list?view=rest-consumption-2024-08-01)
- [Legacy offer usage path](https://learn.microsoft.com/en-us/azure/cost-management-billing/automate/get-usage-details-legacy-customer)

Public findings intentionally omit actual tenant/subscription UUIDs, IP addresses,
resource IDs/names, credentials, customer data and raw private reports.
