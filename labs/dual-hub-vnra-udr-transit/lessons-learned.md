# Lessons Learned: dual-hub-vnra-udr-transit

> correlation_id: vnra-c7e2a3f1 | recorded_by: Niobe | date: 2026-08-19 | updated: 2026-08-19 (post-fix final)

---

## L1 -- `allowVirtualNetworkAccess=false` Silently Drops All Traffic in Hub-Spoke VNRA Topologies (ROOT CAUSE OF E1)

**Scenario tested:** Two hub VNets globally peered, one managed VNRA per hub. Spoke UDRs point to local VNRA. Hub VNRA subnet UDRs point to remote VNRA across global peering for transit.

**Initial result:** 100% packet loss both directions. VNRA Azure Monitor metrics showed 0 bytes/packets received (pre-fix retry window). Control plane (route tables, effective routes, peering state/sync) all appeared correct.

**Root cause identified:** All six VNet peering objects had `allowVirtualNetworkAccess=false`. Despite being `Connected/FullyInSync` with `allowForwardedTraffic=true`, the peerings were blocking all data-plane traffic. The Azure SDN fabric silently drops packets destined for the peered address space when this flag is false.

**Fix:** Set `allowVirtualNetworkAccess=true` on all six peerings (retaining `allowForwardedTraffic=true`). After fix: 10/10 packets, 0% loss both directions, avg ~33 ms.

**Key insight:** `allowVirtualNetworkAccess` and `allowForwardedTraffic` serve different purposes:
- `allowForwardedTraffic=true` permits traffic *forwarded from* the remote VNet (needed for spoke-to-hub-to-spoke via UDR)
- `allowVirtualNetworkAccess=true` permits traffic *to* the peered VNet's address space -- this is the base requirement for any connectivity

**Impact:** Any hub-spoke topology using UDR-steered VNRA transit MUST verify `allowVirtualNetworkAccess=true` on every peering leg. The flag defaults can vary by creation method (CLI, Portal, Terraform, ARM template); always verify explicitly post-creation.

**Diagnosis tip:** This misconfiguration is invisible in the peering state (`Connected/FullyInSync` regardless). Only a full peering GET that includes the flags reveals the issue. The condensed peering list commands may omit the flag if not explicitly projected.

---

## L2 -- No Subnet-Scope Effective Route API for VirtualNetworkApplianceSubnet (E2)

**Finding:** POST to `.../subnets/VirtualNetworkApplianceSubnet/effectiveRouteTable` and `.../listEffectiveRoutes` both return HTTP 404 from the regional ARM network backend. The action is not implemented, not merely undocumented.

**Impact:** There is no CLI or REST mechanism to inspect effective routes on the VNRA subnet. The full observability toolkit for managed VNRA is:

| Tool | What it shows |
|------|---------------|
| `az network route-table route list` | Configured UDR entries |
| `az network nic show-effective-route-table` (spoke NIC) | Spoke effective routes |
| `az network watcher show-next-hop` (spoke NIC) | SDN forwarding intent (spoke perspective) |
| `az rest GET .../virtualNetworkAppliances/vnra1` | VNRA state + IPs |
| `az monitor metrics list` | 8 VNRA metrics without diag config |
| End-to-end ping + tracepath | Data-plane proof |
| VNet peering GET (all legs) | `allowVirtualNetworkAccess` + `allowForwardedTraffic` flags |

**Workaround:** Place a diagnostic VM in the VNRA subnet (different subnet in same VNet) and use `az network nic show-effective-route-table` on that NIC to observe system routes the hub VNet has learned. This is an approximation, not a direct VNRA view.

---

## L3 -- VNRA Reserves 5 IPs Per Instance (Undocumented)

**Finding:** Each managed VNRA acquires 5 consecutive IPs from its subnet (primary + 4 secondary). A 50 Gbps VNRA in 10.1.0.0/24 consumed 10.1.0.4-10.1.0.8. This is not documented in the GA overview, create docs, or quota docs as of 2026-08-19.

**Impact:** A /28 subnet (11 usable IPs) can fit at most 2 VNRAs (10 IPs). A /29 (3 usable) cannot fit a single VNRA. Minimum safe subnet for 1 VNRA is /28; for production use /24 as documented.

**Action:** Document in design template. Investigate whether secondary IPs count against subnet quota or are reserved by the platform differently.

---

## L4 -- Network Watcher Cannot Proxy VNRA Forwarding Context

**Finding:** `az network watcher show-next-hop` requires `--source-ip` to match an actual IP on the specified NIC. Passing VNRA1's IP (10.1.0.4) via a spoke VM NIC returns `SourceIpDoesNotMatchNicIp`. There is no way to use NW to simulate VNRA1's forwarding table lookup.

**Impact:** Network Watcher next-hop is only useful for the spoke->VNRA first hop. The VNRA->VNRA2 cross-hub hop is unverifiable via any documented observability tool. Use end-to-end ping/tracepath as the only data-plane proof.

---

## L5 -- Azure Monitor Metrics Available Without Diagnostic Settings (E3 partial)

**Finding:** `az monitor metrics list-definitions` returns 8 metric definitions for `Microsoft.Network/virtualNetworkAppliances` without any diagnostic settings configured. The metrics API returns HTTP 200 for all queries.

**Pre-fix values:** All metric values were zero across the test window (confirmed in `09-vnra1-metrics.json`, `09-vnra2-metrics.json`). These zeros are now definitively explained by E1 failure (`allowVirtualNetworkAccess=false` -- no traffic reached either VNRA).

**Post-fix status:** Metrics were NOT re-queried after the successful ping tests. Whether VNRA metrics reflect active forwarded traffic remains unconfirmed.

**To complete E3:** Run `az monitor metrics list` during active transit (after peering fix is confirmed) and verify BytesSent/BytesReceived/PacketsSent/PacketsReceived are non-zero.

---

## L6 -- VNRA Does Not Respond to ICMP Echo

**Finding:** Pinging VNRA's primary IP (10.1.0.4, 10.2.0.4) from adjacent VMs returns 100% loss. This is expected -- the managed VNRA hardware has no OS and does not process ICMP echo requests.

**Impact on diagnostics:** Direct ICMP reachability of VNRA IPs is not a valid health indicator. Use Azure Monitor metrics and provisioning state instead.

---

## L7 -- traceroute Not Available on Ubuntu Test VMs; Use tracepath

**Finding:** Ubuntu 22.04 minimal images do not ship `traceroute` by default. The command `tracepath` (from iputils) is available and provides equivalent hop-by-hop PMTU discovery. For TTL-based hop tracing, `tracepath -n` or install `traceroute` via `apt`.

---

## L8 -- Auto-Created NSGs on CLI-Provisioned NICs and VNRA Subnets

**Finding:** `az network nic create` without `--network-security-group ""` auto-creates a default NSG on the NIC's subnet. VNRA provisioning also auto-creates NSGs on the VirtualNetworkApplianceSubnet. These NSGs have Azure default rules only.

**Impact:** Default NSGs allow all VirtualNetwork traffic (AllowVnetInBound/AllowVnetOutBound), so they do not block lab traffic. However, they appear as unexpected resources and inflate the resource count.

**Fix:** Pass `--network-security-group ""` to `az network nic create` to prevent spoke NSG creation in future deploys.

---

## L9 -- MDE.Linux Extensions Auto-Deployed by Microsoft Defender for Cloud

**Finding:** After VM creation, Microsoft Defender for Cloud automatically deploys `MDE.Linux` extensions on both VMs. These are not in the design and appear as extra resources. They are policy-driven and cannot be prevented without policy exemption.

**Impact:** None on lab functionality. Minor resource count discrepancy vs. design.

---

## L10 -- rt-spoke detach syntax: use `--route-table null` (not `""` or `None`)

**Finding:** `az network vnet subnet update --route-table ""` returns a CLI argument error. The correct syntax for detaching a route table is `--route-table null`.

---

## L11 -- Managed VNRA Hardware Is TTL-Invisible (Positive Confirmation)

**Finding:** Post-fix tracepath from test1-vm to test2-vm shows exactly one visible hop (10.20.1.4, reached) with no intermediate hop at VNRA IPs (10.1.0.4, 10.2.0.4). This is the definitive empirical proof that managed VNRA hardware forwards packets at L3 without decrementing TTL.

**Value:** This distinguishes managed VNRA from VM NVA (which would appear as an intermediate tracepath hop). In production, this means managed VNRA is transparent to path diagnostics -- the only way to detect it in the path is via Azure control-plane tools (Network Watcher, effective routes) or latency (adds ~15-20 ms for cross-region global peering transit).

---

## Observability Ceiling (Post-Fix State)

| Observable | Available | Tool |
|------------|-----------|------|
| Configured UDR routes | YES | az network route-table route list |
| Effective routes on spoke VM NICs | YES | az network nic show-effective-route-table |
| Effective routes on VNRA subnet | NO | Not implemented (E2 confirmed -- 404) |
| VNRA resource state + IPs | YES | az rest GET .../virtualNetworkAppliances/vnra1 |
| VNet peering flags (all legs) | YES -- **CRITICAL** | az network vnet peering list + GET |
| Azure Monitor metrics (no diagnostic config) | YES (infrastructure), UNCONFIRMED (post-fix values) | az monitor metrics list |
| Network Watcher next-hop (spoke perspective) | YES | az network watcher show-next-hop |
| Network Watcher next-hop (VNRA perspective) | NO | Source-IP mismatch blocks proxy |
| End-to-end ping/tracepath | YES -- primary data-plane proof | az vm run-command invoke |
| ICMP reachability to VNRA IPs | NO | Hardware device, no OS |
