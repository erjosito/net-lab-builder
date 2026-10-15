# Azure public-endpoint bandwidth billing

**Status, 2026-10-15: same-region cross-tenant public-IP transport PASS;
restoration PASS; bandwidth billing INCONCLUSIVE.** A ↔ T exchanged exactly
5 GiB each direction at 10:04:25–10:40:28 UTC, with matching hashes and no bulk
retries. Following laptop sleep, recovery restored T's original NSG and verified
T/A deallocated at 14:07:37/14:07:40Z; independent validation reconfirmed both.
See the [completed result and dated follow-ups](results/2026-10-15-cross-tenant-public-ip.md).
The later **C → B inter-region control failed (v1) / blocked before bulk (v2)**;
neither established a charged positive control. Fresh independent verification
completed at **19:06:07Z**: B's exact original NSG was `Succeeded`, its NIC
association matched, and B/C were deallocated. No active children or further
transfer is queued.
Owner: Morpheus / Jose Moreno. Research retrieved **2026-10-15**.

Question: does a customer's VNet pay bandwidth when exchanging data with a
same-region Azure SaaS public endpoint, including another Entra tenant?

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
does **not** establish Internet-egress billing. Cross-tenant applicability is a
test hypothesis, not a confirmed experimental exemption or explicit
tenant-specific promise. Connectivity does not prove tenant-independent billing.
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
owned child commands exited. **Disks and PIPs still incur rent**; enforce the
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
**Disks and PIP keep accruing charges**: T's individual cutoff is
**2026-10-18 08:20:59Z**, but use the earlier whole-lab cleanup deadline
**before 2026-10-18 07:33Z**, under standing own-assets cleanup authority and
a fresh exact-inventory lease. T remains retained.

Jose approved the **$8 three-day core subject to prerequisites** on 2026-10-15.
This does not approve optional phases, SKU/cost increases, or unrelated cleanup.

## Current evidence, budget and next gates

The headline A ↔ T public-IP test took priority on **15 October**, instead of
the original D0 private-control traffic. A is in the Windows native context;
T is in native Ubuntu-24.04 WSL, with unequal tenants and subscriptions verified.
Both are Sweden Central Linux VMs; Windows/WSL describe management contexts,
not guest operating systems. Both TCP connections originated at A, while the
download's bulk-byte producer was T. No other bulk family has completed successfully.

Initial attributed billing collection at 14:14:58–14:15:11Z produced **Windows
HTTP 200 COMPLETE empty**, but **WSL HTTP 429 rate_limited ERROR**, not two
successful empty results. Neither proves free traffic. Mature quantity/unit/rate
evidence and a known-charge positive control on the relevant offer/feed are
still missing. The **18:22Z refresh** returned HTTP **429 ERROR** for both
aggregates. Windows details were **200 INCOMPLETE**: 1,000 unrelated rows
discarded in memory and a continuation remaining. WSL details were **200
COMPLETE empty**, not zero-charge proof. See the
[sanitized refresh](results/2026-10-15-billing-refresh.json),
[billing reconciliation](billing-evidence.md) and
[collector findings](costs/README.md).

- No budget increase or new resource creation during the transfer/recovery:
  **$8 core + $4 extension** remain the caps.
- Conservatively reserve 12 GiB for the headline plus **6 GiB per control
  attempt**: **35 − 12 − 6 − 6 = 11 GiB core remaining
  (11,811,160,064 bytes)** after v2. This is reservation accounting, not actual
  payload use; do not reuse the earlier 17 GiB remainder. T's approved 10 GiB payload reserve is
  consumed; additional T payload requires approval.
- A/T allocation is conservatively about **4h10m each including readiness and
  recovery**, not a measured actual allocation-start time; hard limit remains
  <12h/slot. Recompute headroom from private lifecycle records before more work.
  Deallocation stops compute, not retained disk/PIP charges.
- C replaced the retired P slot: P's VM/disk/NIC/dedicated NSG are gone;
  shared networking and A/B were preserved. C is deployed in an isolated
  North Europe owned RG. The inherited whole-core planning envelope is
  **$7.954831 < $8**, not an actual bill. C's inherited slot has roughly **2h
  before deducting readiness and ~5m setup**; reconcile lifecycle records before
  proposing further allocation. Neither TTL nor the original slot is reset.
- Collect 15 October usage no earlier than **16/17/18 October 10:40:28Z**
  (24/48/72h); if needed **22 October 10:40:28Z** (day 7).
- **Cleanup precedes late billing:** T expires **18 October 08:20:59Z**;
  the earliest recorded core resource expires **18 October 07:38:11Z**,
  and the core RG may be older. Use standing known-own-assets cleanup authority
  and a fresh exact-inventory lease to delete
  absolutely before **18 October 07:33Z** (core deployment lease start
  plus 72h), checking the private RG creation time for any earlier deadline.
  Preserve historical IDs privately and query billing after deletion.
- **Control v1, 17:28:50–18:13:46Z: FAIL**, 12 connection/TLS timeouts,
  zero bulk requests, C RX+TX once **284,630 bytes**. Cause remains unproven;
  the saved NSG `Updating` response does not prove it caused a drop.
- **Control v2: fresh readiness PASS; guarded live BLOCKED** by a NIC read
  timeout before either guest command, **zero payload**. Final NSG GET also
  timed out; this unverified closure was subsequently resolved by fresh Niobe
  read-only verification (**5 calls, 0 mutations**, idle proof 19:06:07Z).
  See [control safeguards](transfers/README.md#one-way-core-positive-control).
- A/B/C/T remain deallocated; retained disks/PIPs still accrue charges.
  No charged positive control exists. Closing the tenant-boundary question
  needs mature attributable meter quantity/unit/rate evidence and provider
  policy confirmation, not more unapproved payload.
- Standing cleanup authority is limited to known owned assets. **No automatic
  follow-up or cleanup job is established**. These dates are action deadlines,
  not scheduled jobs. No extra-cost scope or further MSDN payload is approved.

The guest's bounded foreground commands and persisted reports enabled recovery,
but a sleeping laptop cannot guarantee cloud deallocation. No automatic
cloud-cleanup guarantee is claimed. This documentation publication made
**zero Azure calls or mutations**.
