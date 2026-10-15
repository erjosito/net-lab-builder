# Azure public-endpoint bandwidth billing

**Status: D0 A/B/P and the separate MSDN endpoint T deployed on 2026-10-15.
A/B/P were verified deallocated at 07:41:35Z; T at 08:22:55Z.
No experimental traffic or bandwidth-billing results.**
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
not bandwidth attribution. The approved additional endpoint is now deployed
and deallocated; see [msdn-deployment-log.md](msdn-deployment-log.md).

Microsoft's [bandwidth FAQ](https://azure.microsoft.com/en-us/pricing/details/bandwidth/)
says same-region Azure-service transfers are not charged. Public addressing alone
does **not** establish Internet-egress billing. Cross-tenant applicability is a
test hypothesis, not an observed result or an explicit tenant-specific promise.

## Approval card

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
  **do not keep VMs running while waiting for billing**.
- The initial catalogue probe timed out; Sweden Central capacity subsequently
  passed, while North Europe capacity remains a D2 gate. Aggregate and
  detailed billing access succeeded, including quantity/rate schema access.
  The Windows modern detailed endpoint did not honor the tested RG filter: collectors must
  filter rows in memory before saving anything. See [preflight.md](preflight.md).
  Sweden Central B1ls/B1s had location restrictions; B2ts_v2 passed the bounded
  catalogue, native ARM validation and actual provisioning gates. All three
  use **Standard_B2ts_v2**, nonzonal. See [deployment-log.md](deployment-log.md).

## Actual D0 state

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
72-hour resource lifetime and obtain separate explicit cleanup approval.
Next D0 step: implement the bounded pinned-mTLS harness with peer-only 443
rules, then assign fresh execution and validation leases under the approved
core scope and caps. No traffic is authorized under the completed deployment
lease; further user approval is needed only for changes outside that scope.

See [design.md](design.md), [scenarios.json](scenarios.json),
[billing-evidence.md](billing-evidence.md), and
[context-isolation.md](context-isolation.md). Optional PaaS, Storage, routing,
and Internet controls require separate approval and costs. Jose subsequently
approved using the existing authenticated WSL MSDN subscription and the
**additional $4** cross-tenant endpoint, without changing the $8 core.

## Actual MSDN endpoint T

One **Standard_B1s**, nonzonal Ubuntu 22.04 Gen2 VM in Sweden Central, in a new
owned group: one 30 GiB StandardSSD_LRS disk, NIC, NSG, Standard static IPv4
PIP and unpeered VNet/subnet (`10.233.0.0/24`, implicit outbound disabled).
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
**Disks and PIP keep accruing charges**: delete by **2026-10-18 08:20:59Z**
under separate explicit cleanup approval and a new lease. No deletion occurred.

Jose approved the **$8 three-day core subject to prerequisites** on 2026-10-15.
This does not approve optional phases, SKU/cost increases, or unrelated cleanup.
