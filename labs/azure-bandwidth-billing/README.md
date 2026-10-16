# Azure public-endpoint bandwidth billing

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
Billing ingestion remains incomplete: this is not yet a billed positive control.
Known-owned cleanup closed PASS at **00:00:11.806224Z, 16 October**:
13 remaining original core assets absent, C/T groups gone, all known lab
VMs/disks/PIPs deleted. **Core RG and one unproven-ownership NSG were preserved**,
not adopted/deleted. No active children or further transfer is queued.
Owner: Morpheus / Jose Moreno. Research retrieved **2026-10-15**.

**16 October 00:29Z billing update:** actual Cost Details CSV extraction now
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
cross-tenant extension are in [costs/README.md](costs/README.md). Both contexts'
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

## Current evidence, budget and next gates

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
