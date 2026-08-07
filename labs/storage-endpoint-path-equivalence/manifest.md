# Lab manifest — `storage-endpoint-path-equivalence`

**Status:** Historical Storage manifest, superseded by the approved Translator deployment in `redesign.md` and `deployment.md` · **Region:** `swedencentral`  
> Do not execute the Storage resource plan below. The live lab now uses Translator F0; current IaC is under `deploy/`.
**Purpose:** Test whether Blob public endpoint, service endpoint (SE), and private endpoint (PE) are conditionally performance-equivalent while separately proving their observable network behavior. This lab cannot prove physical-path identity.

## Phase 0 lock (refreshed 2026-08-05)

Cost ladder in `swedencentral`: `Standard_B1ls` catalog MISS → `Standard_B1s` catalog MISS → `Standard_B2ts_v2` catalog PASS and live `az vm create --validate` PASS. Selected: one non-zonal Ubuntu 22.04 `Standard_B2ts_v2`. Exact tagged temporary RG `rg-preflight-sepath-20260805-161627` was created only for validation and verified removed. No subscription, tenant, deployment, IP, or resource IDs are recorded.

## Resources, dependencies, and tags

All created ARM resources are in one RG, `rg-storage-sepath-<run>`, in `swedencentral` unless stated. Apply `lab=true`, `created_by=copilot-lab`, `lab_name=storage-endpoint-path-equivalence`, and `correlation_id=<run>` to every taggable resource.

| Count | Resource / setting | Depends on |
|---:|---|---|
| 1 | Resource group | — |
| 1 | VNet `vnet-endpoint-path`, `10.61.0.0/16`, Azure DNS | RG |
| 1 | Client subnet `snet-client`, `10.61.1.0/24`; NAT + NSG association; SE changed by scenarios | VNet, NAT, NSG |
| 1 | PE subnet `snet-private-endpoint`, `10.61.2.0/24`; PE policies disabled | VNet |
| 1 | NSG `nsg-client`; outbound DNS/53, IMDS/80, `Storage.SwedenCentral`/443, PE `10.61.2.4:443`, `AzureCloud.SwedenCentral`/443, then deny-all; no custom inbound | RG |
| 1 | Standard static IPv4 PIP `pip-nat` (value never published) | RG |
| 1 | NAT Gateway `nat-client`, Standard, idle timeout 10 min | PIP |
| 1 | NIC `nic-client`, dynamic private IPv4, no PIP, no NIC NSG | Client subnet |
| 1 | VM `vm-client`, Ubuntu 22.04 Gen2, non-zonal, `Standard_B2ts_v2`, system identity, SSH-key auth, no PIP/spot/accelerated networking | NIC |
| 1 | VM OS disk, 30 GiB Standard SSD LRS | VM |
| 3 | GPv2 StorageV2 accounts, Standard_LRS, Hot: target, decoy, and flow-log; unique generated names, TLS 1.2, shared-key access disabled on target/decoy | RG |
| 2 | Private blob containers + one immutable 64 KiB and one immutable 8 MiB blob in each target/decoy account | Storage accounts, RBAC |
| 1 | Blob PE `pe-target-blob`, static `10.61.2.4`, auto-created PE NIC, approved connection | Target, PE subnet |
| 1 | Private DNS zone `privatelink.blob.core.windows.net` | RG |
| 1 | PE DNS zone group/A record for target → `10.61.2.4` | PE, zone |
| 1 | VNet-zone link, initially absent/unlinked; scenario-controlled | Zone, VNet |
| 1 | Storage service-endpoint policy with one definition containing only the target account ARM ID; initially detached | Target, VNet |
| 1 | Log Analytics workspace, `PerGB2018`, 30-day retention | RG |
| 2 | Blob diagnostic settings (target + decoy): read/write/delete and metrics to workspace | Accounts, workspace |
| 1 | VNet flow-log resource, v2, 10-minute aggregation, retention only for lab lifetime, to flow-log account; reuse the subscription's regional Network Watcher (do not create another singleton) | VNet, flow-log account, Network Watcher |
| 2 | `Storage Blob Data Reader` assignments for VM identity at target/decoy scope | VM identity, accounts |

Prerequisites: registered `Microsoft.Compute`, `Microsoft.Network`, `Microsoft.Storage`, `Microsoft.Insights`, and `Microsoft.OperationalInsights`; regional Network Watcher available; caller can create role assignments. Bootstrap `curl`, `jq`, `dnsutils`, `tcpdump`, `python3`, and benchmark tooling before attaching the restrictive NSG.

## Safe state transitions

1. Start with SE off, policy detached, private zone unlinked, and both accounts `publicNetworkAccess=Enabled/defaultAction=Allow`.
2. Create the target VNet rule with `ignoreMissingVnetServiceEndpoint=true` while default action remains Allow; verify an unchanged control request.
3. Enable `Microsoft.Storage`, wait for subnet provisioning, flush DNS, terminate sockets, and verify effective routes. Only then set target `defaultAction=Deny` with the VNet rule retained. This avoids a firewall transition outage.
4. Attach the target-only endpoint policy only after target access through the SE succeeds.
5. Link private DNS only after S3 evidence is complete. For forced-public controls preserve FQDN/SNI with `--resolve`.
6. Roll back in reverse: re-enable public access/default Allow → unlink DNS → detach policy → remove VNet rule → disable SE; flush DNS/sockets at every boundary.

## Executable correctness scenarios

Every request gets `x-ms-client-request-id=sepath-<scenario>-<UTC>-<sequence>`. The ID is visible in client headers and Storage logs, **not inside encrypted TLS PCAP**; join PCAP by synchronized UTC window, source/destination 5-tuple, process timing, and capture filename.

| Scenario / actions | PASS / failure gate |
|---|---|
| **S1 public control:** assert SE/policy off and private zone unlinked; resolve full CNAME/A chain; record NAT egress; select a live public IPv4 and `curl --resolve` the target; capture TCP/443; collect effective routes, NSG, Storage state, headers/logs. | PASS: public destination, successful GET, and no matching `VirtualNetworkServiceEndpoint` route. Same-region Storage `CallerIpAddress` can be platform-dependent and is supporting evidence only; do not fail S1 solely because it is absent or surprising. |
| **S2 SE paired control:** follow transition steps 2–3; revalidate the pinned IP remains in DNS; repeat the identical request/payload. | PASS: same FQDN and public destination, successful GET, and the matching effective route is `VirtualNetworkServiceEndpoint`. Private/VNet identity or authorization in Storage logs supports the result but is not the sole gate. |
| **S3 endpoint-policy authorization:** attach target-only policy; request identical target and decoy blobs over their public answers. | PASS: target succeeds and decoy is denied while both remain public destinations with SE route classification. A policy drop may occur before Storage resource logging, so absent decoy Storage log is allowed; preserve client status/error, policy definition/association, route, DNS, PCAP tuple, and time window. |
| **S4 private endpoint:** keep SE/policy attached; link private zone, flush caches/sockets, use ordinary target FQDN without `--resolve`. | PASS: CNAME terminates at `10.61.2.4`, PCAP destination is `10.61.2.4`, PE connection is approved, VNet-local effective route is selected, GET succeeds. |
| **S5 exposure negative control:** retain private DNS; set target `publicNetworkAccess=Disabled`; run one forced-public `--resolve` request and one ordinary private-DNS request. | PASS: forced-public request fails and private request succeeds. A missing service log for the rejected public attempt is not itself a failure. |

For all scenarios, `az network nic show-effective-route-table` is authoritative for Azure next-hop classification. `show-next-hop` and `ip route get` are corroborative only: PaaS/SDN abstraction can yield `Internet`, `None`, or incomplete detail, so they must not be interpreted as physical-path proof. VNet flow logs are optional corroboration and may be delayed.

## Performance-equivalence protocol

Correctness collection above is completed first and stored separately. Before benchmarking, restore a common permissive account state: `publicNetworkAccess=Enabled/defaultAction=Allow`, policy detached, and identical RBAC. Performance runs exclude transition/convergence samples and use the same VM, identity, FQDN/SNI, payload bytes, Storage account, blob, client version, NSG, and region. Mode definitions are public=SE off/zone unlinked, SE=SE on/zone unlinked, PE=SE off/zone linked. Record VM CPU/credit, memory, retransmits, DNS answer, destination, and account throttling; invalidate a block if VM CPU >80%, credits are depleted, Storage returns throttling, destination changes unexpectedly, or a control-plane transition is incomplete.

### Predeclared design

- Compare pairs **public↔SE, public↔PE, and SE↔PE** at concurrency `1, 8, 32`.
- Payloads: immutable 64 KiB (latency) and 8 MiB (throughput), verified by hash.
- Variants: **fresh connection** (new process/TCP/TLS per request) and **reused connection** (persistent HTTP/1.1 connection; fixed 100 requests/connection). Do not mix variants.
- Ten randomized complete endpoint-order blocks (five in each of two time windows separated by ≥30 minutes). Within each block use a seeded balanced Latin-square order of public/SE/PE; retain the seed. Each mode runs every concurrency/payload/connection cell in a seeded randomized order. Reconfigure only the defined endpoint state, wait for provisioning, flush DNS/sockets, and capture state before measurement.
- Per mode/block: 30-second or 20-request warm-up (whichever is longer). For 64 KiB, measure 200 requests at concurrency 1 and 400 aggregate at concurrency 8/32; for 8 MiB, measure 30/80/160 aggregate requests at concurrency 1/8/32. Cool down 15 seconds. Repeat an invalid block in full, never one arm only.
- Interleave endpoint modes by block rather than running all observations of one mode together. Expected benchmark duration is 6–10 hours, depending on Azure transition and telemetry readiness.
- Client uses OAuth and discards response bodies only after byte count/hash validation. No account keys/SAS. Capture summarized TCP retransmissions; do not run full PCAP for every benchmark request.

### Metrics, margins, and decision rule

Primary unit is the paired block aggregate, preventing thousands of requests from being treated as independent. Compute paired log-ratios and cluster bootstrap by block (10,000 resamples). Report 95% CIs; use two one-sided tests (TOST, α=.05), equivalent to requiring the 90% CI wholly inside each predeclared margin:

| Metric | Statistic | Equivalence margin |
|---|---|---|
| Latency | median and p95 request time | ratio 0.90–1.10 (median); 0.85–1.15 (p95) |
| Throughput | successful payload MiB/s | ratio 0.90–1.10 |
| Jitter | within-block p95−p50 latency | ratio 0.80–1.20 **and** absolute difference ≤2 ms |
| Error rate | DNS/TCP/TLS/HTTP failure proportion | absolute difference ≤0.5 percentage points; paired/cluster-bootstrap CI |
| Loss proxy | TCP retransmitted-segment proportion from socket/pcap summary | absolute difference ≤0.2 percentage points; report separately if too sparse for TOST |

Claim equivalence only for a pair/variant/concurrency/payload when **all primary margins pass** and correctness gates pass. Otherwise label `not equivalent` or `inconclusive` (CI crosses a margin); never convert “no significant difference” into equivalence. Results are conditional on this region, VM/client, load, time window, account tier, and payload—not evidence of identical Microsoft physical paths.

## Outputs and publication handoff

Write `raw-output/<run>/correctness/` and `raw-output/<run>/performance/` separately. Correctness: state snapshots, DNS, sanitized effective routes/NSGs, PCAP metadata/captures, request headers without tokens, Storage/flow-log extracts, and timestamps. Performance: JSONL per request, block metadata/seeds, endpoint state, VM counters, retransmit summaries, CSV aggregates, analysis script output, TOST/bootstrap tables, and plots.

Sanitize subscription/tenant/resource IDs, public/private IPs except documented RFC1918 topology, storage names, tokens, request/response authorization headers, identity IDs, and PIP values. Preserve stable pseudonyms and relative timings. Report handoff: methods, correctness matrix, equivalence tables/CIs, invalidated blocks, limitations, and cleanup proof. Blog handoff: topology, why correctness and performance evidence differ, three endpoint comparisons, confidence intervals, operational implications, and the explicit statement: **conditional performance equivalence does not establish physical-path identity**.

## Cleanup gate and order

After results are reviewed, preview deletion and obtain separate cleanup approval. Then: disable diagnostics/flow log → re-enable target public access and remove DNS link/policy/VNet rule/SE → delete role assignments → PE DNS zone group/PE → DNS link/zone → endpoint policy → blobs/containers → Storage accounts → VM/disk/NIC → NAT/PIP → NSG/subnets/VNet → workspace → tagged RG. Verify the exact tagged RG and all role assignments are gone.

## Phase 4 deployment plan — present verbatim

- **Resource list:** 1 resource group; 1 VNet; 2 subnets; 1 NSG; 1 NAT Gateway with 1 Standard static IPv4; 1 Ubuntu 22.04 `Standard_B2ts_v2` VM with NIC and 30-GiB Standard SSD; 3 GPv2 Standard_LRS Storage accounts; 2 containers with two test blobs each; 1 Blob private endpoint; 1 Private DNS zone, zone group, and VNet link; 1 target-only Storage service-endpoint policy; 1 Log Analytics workspace; 2 Blob diagnostic settings; 1 VNet flow-log resource; and 2 Blob Data Reader role assignments.
- **Region:** `swedencentral` only.
- **Estimated deployment time:** 10–20 minutes; allow another 10–15 minutes for diagnostics/log readiness before testing.
- **Estimated cost:** approximately US$0.15–0.30/hour, under US$3 for a ten-hour lab, plus low-volume Storage transactions, test data, and Log Analytics ingestion.
- **Connectivity statement:** No Megaport or ExpressRoute resources are involved.
- **Approval gate:** Phase 4 was approved. ARM deployment succeeded, but S1–S3 are blocked by enforced Storage public-access disablement. Cleanup remains separately gated.
