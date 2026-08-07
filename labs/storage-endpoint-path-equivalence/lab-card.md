# Lab Card — `storage-endpoint-path-equivalence`

**Status:** ✅ TRANSLATOR F0 REDESIGN DEPLOYED — Niobe unblocked; VM deallocated
**Authored:** 2026-08-05T13:43:07.691+02:00 · **Owner:** Morpheus

## Mechanism

Service endpoints keep public DNS/IP, add a `VirtualNetworkServiceEndpoint` route, and extend subnet/private-source identity. Private endpoints change DNS to a VNet NIC/private IP. The lab tests observable forwarding, not Microsoft's physical underlay.

## Phase 0 / region / compute

- Region: `swedencentral`.
- Cost ladder: `Standard_B1ls` catalog miss → `Standard_B1s` catalog miss → `Standard_B2ts_v2` catalog PASS and `az vm create --validate` live-capacity PASS.
- VM: 1× Ubuntu 22.04 `Standard_B2ts_v2`, 30-GiB Standard SSD, non-zonal, no public IP.
- Tagged RG `rg-preflight-sepath-20260805-134307` was used only for validation and verified removed.

## Paired-control design and address plan

One VM/subnet/account/FQDN/object/request is reused sequentially. Each run closes connections and uses a unique request ID; only endpoint/network controls change.

| Network | Prefix / address |
|---|---|
| `vnet-endpoint-path` | `10.61.0.0/16` |
| `snet-client` | `10.61.1.0/24` |
| `snet-private-endpoint` | `10.61.2.0/24`; PE `10.61.2.4` |
| Storage public endpoint | Live DNS result per run; never hard-coded |

## Exact resource inventory

- 1 tagged resource group; 1 VNet; 2 subnets; 1 NSG; 1 NIC; 1 Linux VM + disk.
- 1 NAT Gateway + 1 Standard static IPv4 for stable public-control egress.
- 2 GPv2 Standard_LRS accounts: target and decoy; one test blob each.
- 1 target blob PE + connection; 1 `privatelink.blob.core.windows.net` zone + VNet link.
- 1 target-only Storage service-endpoint policy, associated only during S3.
- 1 flow-log Standard_LRS account + 1 VNet flow-log resource.
- 1 Log Analytics workspace; Blob diagnostic settings on target and decoy.
- VM system identity + least-privilege Blob data role assignments.
- No Bastion, ExpressRoute, Megaport, gateway, firewall, or public VM management port.

## Scenarios — one-line gates

| # | Scenario and pass/fail |
|---|---|
| S1 | **Public control:** SE off/public DNS; PASS if DNS/capture show public Storage IP, route is not `VirtualNetworkServiceEndpoint`, request succeeds, and `CallerIpAddress` is not `10.61.1.x`. |
| S2 | **Service endpoint paired run:** enable `Microsoft.Storage` and target subnet rule; PASS if DNS and captured destination remain public, effective route becomes `VirtualNetworkServiceEndpoint`, request succeeds, and `CallerIpAddress` becomes the VM private IP. |
| S3 | **Endpoint-policy authorization:** attach target-only policy; PASS if target succeeds and decoy fails while both retain public DNS and the same service-endpoint next-hop type. |
| S4 | **Private endpoint:** enable private DNS; PASS if the unchanged FQDN resolves/captures `10.61.2.4`, route is VNet-local, request succeeds, and PE is connected. |
| S5 | **Exposure negative control:** disable target public network access; PASS if forced-public S1/S2-style requests fail while private-DNS S4 succeeds. |

## Evidence contract and limitations

Per run collect: `dig`/CNAMEs, fresh-TCP `tcpdump`, NIC effective routes, `ip route get`, external egress IP, VNet flows if emitted, Storage logs (`CallerIpAddress`, auth, request ID/status), firewall/rule/PE state, and timestamps.

Authority is **DNS + effective next hop + captured destination + service-observed source/authorization**. Flow logs only corroborate. Traceroute is rejected: PaaS hops may not answer and Azure SDN hides the underlay. Equal latency/hops/backbone carriage cannot prove a common physical path. S2's changed next-hop/source or S4's private destination falsifies strict observable equivalence.

## Designs studied

| Design | Hypothesis | Deciding evidence |
|---|---|---|
| ✅ Sequential single-client control | Best isolation; exposes endpoint deltas | DNS, routes, PCAP, Storage logs |
| ⚠️ Three parallel client subnets/VMs | Easier execution but VM/subnet differences confound comparison | Cross-client variance |
| 📚 Forced-tunnel/NVA variant | Teaches SE override of matching UDR/BGP; not needed here | Routes + NVA capture |
| ❌ Traceroute/latency-only | Cannot establish Azure PaaS or Private Link path identity | Opaque/missing hops and non-deterministic latency |

## Cost, time, references, gate

Budget: **~US$0.15–0.30/hour; under US$2/6 hours**, plus test data/log ingestion. Deploy 10–20 min; test 60–90 min; teardown 5–15 min.

Learn: `virtual-network-service-endpoints-overview`, `virtual-networks-udr-overview`, `storage-private-endpoints`, `vnet-flow-logs-overview`, `monitor-blob-storage-reference`.

**Phase 4 was approved and the Translator redesign was deployed.** Niobe completed
the Translator validation run; see `validation.md` and `results.md`. Cleanup
remains separately gated and was not performed.
