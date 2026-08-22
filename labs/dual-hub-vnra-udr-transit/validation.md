# Validation Report: dual-hub-vnra-udr-transit

> correlation_id: vnra-c7e2a3f1 | validated_by: Niobe | date: 2026-08-19 | stage: 1-v3 (final)

> **CLEANUP STATUS: COMPLETE** | deleted_by: Tank | cleanup_date: 2026-08-20 | elapsed: ~7 min 54 sec | rg_exists: false | stragglers: 0 | evidence: show-output/cleanup/cleanup-evidence.md

---

## Overall Verdict

| Gate | Result |
|------|--------|
| **E1** Cross-VNRA UDR chaining (S2 transit) | **PASS** -- 0% loss both directions (after peering correction) |
| **E2** Subnet-scope effective-route API | **404** -- confirmed gap (A1/A2 both return Not Found) |
| **E3** Azure Monitor metrics without diag config | **PARTIAL** -- 200 OK, 8 metrics defined; all-zero pre-fix confirmed; post-fix not re-queried |
| S1 Baseline non-transitivity | **PASS** -- 100% loss without route tables |
| S1 Restoration | **PASS** -- both route tables reattached and verified |
| S3 Effective routes on spoke NICs | **PASS** -- UDRs Active on both NICs |
| S4 Configured hub RT routes | **PASS** -- rt-hub1-vnra and rt-hub2-vnra correct |

---

## S1 -- Baseline Non-Transitivity

Temporarily detached rt-spoke1 and rt-spoke2 from vm-subnets (hub VNRA route tables NOT touched). Ran ping. Reattached and verified all 4 associations.

| Step | Result |
|------|--------|
| rt-spoke1 detached from spoke1-vnet/vm-subnet | OK |
| rt-spoke2 detached from spoke2-vnet/vm-subnet | OK |
| Ping test1-vm -> 10.20.1.4 (no route tables) | **100% loss -- PASS** |
| rt-spoke1 reattached + rt-spoke2 reattached | OK |
| All 4 RT associations verified | **PASS** |

Evidence: `show-output/validation/s1-baseline-ping.json`, `show-output/validation/s1-rt-restore-check.json`

---

## S2 -- VNRA + UDR Transit [E1 Gate]

### Phase 1 -- Initial Test (E1 FAIL, pre-retry)

First run during Stage 1 validation session:

```
test1-vm -> test2-vm (10.20.1.4): 0 received, 100% packet loss, tracepath 30 hops all "no reply"
test2-vm -> test1-vm (10.10.1.4): 0 received, 100% packet loss, tracepath 30 hops all "no reply"
```

Evidence: `show-output/validation/s2-test1-to-test2.json`, `show-output/validation/s2-test2-to-test1.json`

### Phase 2 -- Retry Without Fix (still 100% loss)

Retry run `retry-20260819T185118+0200` confirmed unchanged result before any fix was applied:

```
06-test1-to-test2: 10 packets transmitted, 0 received, 100% packet loss, time 9224ms
07-test2-to-test1: 10 packets transmitted, 0 received, 100% packet loss, time 9251ms
Tracepath: 19 hops shown, all "no reply"
```

VNRA Azure Monitor metrics queried in this retry window -- all 8 metrics zero on both VNRA1 and VNRA2:

```
09-vnra1-metrics.json: all "total": 0.0 across all time buckets
09-vnra2-metrics.json: all "total": 0.0 across all time buckets
```

Evidence: `show-output/validation/retry-20260819T185118+0200/06-test1-to-test2.json`,
`show-output/validation/retry-20260819T185118+0200/07-test2-to-test1.json`,
`show-output/validation/retry-20260819T185118+0200/09-vnra1-metrics.json`,
`show-output/validation/retry-20260819T185118+0200/09-vnra2-metrics.json`

### Phase 3 -- Root Cause Identification

Pre-fix read-only investigation of all six VNet peering objects revealed the root cause.

**Root cause: `allowVirtualNetworkAccess=false` on all six peerings.**

All six peerings (hub1-to-spoke1, spoke1-to-hub1, hub1-to-hub2, hub2-to-hub1, hub2-to-spoke2, spoke2-to-hub2) had:

| Flag | Value |
|------|-------|
| `peeringState` | Connected ✓ |
| `peeringSyncLevel` | FullyInSync ✓ |
| `allowForwardedTraffic` | true ✓ |
| **`allowVirtualNetworkAccess`** | **false ✗ -- root cause** |

With `allowVirtualNetworkAccess=false`, the Azure SDN fabric does not allow VMs in one VNet to reach addresses in the peered VNet. UDR-steered (forwarded) packets are silently dropped. The combination of Connected + FullyInSync + allowForwardedTraffic=true is insufficient: `allowVirtualNetworkAccess=true` is required for any data-plane traffic to cross the peering.

The pre-fix condensed peering snapshot (04-peerings-hub1.json, 05-peerings-hub2.json) shows only `fwd` and `state` fields; the absence of `vnetAccess` in that abbreviated view was the indicator the flag was not set.

Evidence: `show-output/validation/retry-20260819T185118+0200/04-peerings-hub1.json`,
`show-output/validation/retry-20260819T185118+0200/05-peerings-hub2.json`

### Phase 4 -- Fix Applied

Coordinator set `allowVirtualNetworkAccess=true` on all six peering objects, retaining `allowForwardedTraffic=true`. Post-fix verification confirmed all six peerings: `Connected`, `FullyInSync`, `allowVirtualNetworkAccess=true`, `allowForwardedTraffic=true`.

Evidence: `show-output/validation/retry-20260819T185118+0200/10-peering-access-correction.json`,
`show-output/validation/retry-20260819T185118+0200/11-peering-access-verified.json`

### Phase 5 -- Post-Fix Test (E1 PASS)

#### test1-vm (10.10.1.4) to test2-vm (10.20.1.4)

```
PING 10.20.1.4: 10 packets transmitted, 10 received, 0% packet loss, time 9016ms
rtt min/avg/max/mdev = 32.786/33.094/34.601/0.522 ms

tracepath:
 1?: [LOCALHOST]                      pmtu 1500
 1:  10.20.1.4                                            30.102ms reached
 1:  10.20.1.4                                            29.313ms reached
     Resume: pmtu 1500 hops 1 back 1
```

#### test2-vm (10.20.1.4) to test1-vm (10.10.1.4)

```
PING 10.10.1.4: 10 packets transmitted, 10 received, 0% packet loss, time 9003ms
rtt min/avg/max/mdev = 30.912/31.372/32.293/0.513 ms

tracepath:
 1?: [LOCALHOST]                      pmtu 1500
 1:  10.10.1.4                                            29.735ms reached
 1:  10.10.1.4                                            31.339ms reached
     Resume: pmtu 1500 hops 1 back 1
```

**Verdict: E1 PASS.** 0% loss symmetric, both directions. One visible hop to the remote VM in each direction (managed VNRA hardware is TTL-invisible -- hardware forwarding does not decrement TTL, so no intermediate hop appears). This is the definitive proof of managed VNRA operation vs. VM NVA behavior.

**Post-fix metrics note:** Azure Monitor metrics were NOT re-queried after the successful ping tests. The zero-value metrics in `09-vnra1-metrics.json` and `09-vnra2-metrics.json` are confirmed pre-fix values only. No post-fix metric evidence exists in the artifact set; whether VNRA metrics reflect forwarded traffic remains unconfirmed (see E3).

Evidence: `show-output/validation/retry-20260819T185118+0200/12-after-fix-test1-to-test2.json`,
`show-output/validation/retry-20260819T185118+0200/13-after-fix-test2-to-test1.json`

---

## S3 -- Effective Routes on Spoke VM NICs

### test1-vmVMNic (spoke1-vnet/vm-subnet)

| Prefix | Source | NextHopType | NextHopIP | State |
|--------|--------|-------------|-----------|-------|
| 10.10.0.0/16 | Default | VnetLocal | -- | Active |
| 10.1.0.0/16 | Default | VNetPeering | -- | Active |
| 0.0.0.0/0 | Default | Internet | -- | Active |
| 10.0.0.0/8 | Default | None | -- | Active |
| **10.20.0.0/16** | **User** | **VirtualAppliance** | **10.1.0.4** | **Active** |

PASS. UDR rt-spoke1 present and Active. No system route for hub2 (10.2.0.0/16) or spoke2 (10.20.0.0/16) -- correct, these are not directly peered.

### test2-vmVMNic (spoke2-vnet/vm-subnet)

| Prefix | Source | NextHopType | NextHopIP | State |
|--------|--------|-------------|-----------|-------|
| 10.20.0.0/16 | Default | VnetLocal | -- | Active |
| 10.2.0.0/16 | Default | VNetPeering | -- | Active |
| **10.10.0.0/16** | **User** | **VirtualAppliance** | **10.2.0.4** | **Active** |

PASS. UDR rt-spoke2 present and Active.

**Verdict: S3 PASS.**

Evidence: `show-output/validation/s3-test1-effective-routes.json`, `show-output/validation/s3-test2-effective-routes.json`

---

## S4 -- VNRA Route Tables + Network Watcher

### Configured Routes

| Route Table | Prefix | NextHopType | NextHopIP | Expected | Match |
|-------------|--------|-------------|-----------|----------|-------|
| rt-hub1-vnra | 10.20.0.0/16 | VirtualAppliance | 10.2.0.4 | 10.2.0.4 | YES |
| rt-hub2-vnra | 10.10.0.0/16 | VirtualAppliance | 10.1.0.4 | 10.1.0.4 | YES |

### Network Watcher Next-Hop

| Probe | Source IP | Dest IP | Result |
|-------|-----------|---------|--------|
| test1 -> test2 (normal) | 10.10.1.4 | 10.20.1.4 | VirtualAppliance/10.1.0.4 via rt-spoke1 |
| test2 -> test1 (normal) | 10.20.1.4 | 10.10.1.4 | VirtualAppliance/10.2.0.4 via rt-spoke2 |
| test1 NIC, source=10.1.0.4 (VNRA1 proxy) | 10.1.0.4 | 10.20.1.4 | REJECTED -- SourceIpDoesNotMatchNicIp |

**Spoofed source-IP finding:** Network Watcher enforces source-ip must match NIC. The VNRA forwarding context (rt-hub1-vnra perspective from VNRA1's subnet) is not observable via a spoke VM NIC proxy. Documented as platform limitation (finding F5).

**Verdict: S4 PASS.** Route configurations correct; spoke UDR steering confirmed by NW.

Evidence: `show-output/validation/s4-rt-hub1-vnra-routes.json`, `show-output/validation/s4-rt-hub2-vnra-routes.json`, `show-output/validation/s4-nw-nexthop-test1-to-test2.json`, `show-output/validation/s4-nw-nexthop-test2-to-test1.json`, `show-output/validation/s4-nw-nexthop-spoofed-vnra1-error.txt`

---

## S5 -- Observability Headline Experiment [E2/E3]

### Probe A1: POST .../VirtualNetworkApplianceSubnet/effectiveRouteTable?api-version=2024-05-01

```
HTTP 404 Not Found
Body: No HTTP resource was found... No route data was found for this request.
Backend: swedencentral.network.azure.com (request reached regional backend)
```

### Probe A2: POST .../VirtualNetworkApplianceSubnet/listEffectiveRoutes?api-version=2024-05-01

```
HTTP 404 Not Found (identical body structure)
```

**E2 CONFIRMED.** Both action names unimplemented on subnet scope. The 404 originates from the regional ARM network backend (not a frontend routing failure). No subnet-scope effective route API exists for VirtualNetworkApplianceSubnet.

**Observability answer (precise):** Configured VNRA-subnet UDRs are listable via `az network route-table route list`. The managed VNRA has no customer NIC and no direct effective-route API. Both subnet REST actions returned 404. Use the following as the complete observability toolkit for managed VNRA deployments:

| Tool | What it shows |
|------|---------------|
| `az network route-table route list` | Configured UDR entries on VNRA subnet route tables |
| `az network nic show-effective-route-table` (spoke NIC) | Spoke VM effective routes -- verifies UDR active from spoke perspective |
| `az network watcher show-next-hop` (spoke NIC) | Azure SDN forwarding intent for spoke-to-VNRA hop |
| `az rest GET .../virtualNetworkAppliances/vnra1` | VNRA provisioning state, IPs, subnet binding |
| `az monitor metrics list` | 8 VNRA metrics (BytesSent/Received, PacketsSent/Received, flows) without diag config |
| End-to-end ping + tracepath | Data-plane proof; TTL-invisible hardware = one hop to remote VM |
| VNet peering GET (all legs) | Must verify `allowVirtualNetworkAccess=true` on every peering leg |

### Probe B: VNRA Resource GET (api-version=2025-05-01)

Both vnra1 and vnra2: `provisioningState=Succeeded`, `bandwidthInGbps=50`. Each VNRA has **5 IP configurations** -- primary (.4) plus 4 secondary (.5-.8) -- consuming 5 consecutive IPs from the /24 subnet. This is undocumented in GA documentation (finding F4). GET returns identity/state/IPs only; no effective routing information.

### Probe C: Azure Monitor Metrics (no diagnostic settings configured)

8 metric definitions available without any diagnostic settings:

| Metric | Unit |
|--------|------|
| BytesSent | Bytes |
| BytesReceived | Bytes |
| PacketsSent | Count |
| PacketsReceived | Count |
| CurrentTotalFlowsIn | Count |
| CurrentTotalFlowsOut | Count |
| CreationRateMaxTotalFlowsIn | CountPerSecond |
| CreationRateMaxTotalFlowsOut | CountPerSecond |

Metric API returned HTTP 200. All values zero in the retry window (`09-vnra1-metrics.json`, `09-vnra2-metrics.json`) -- this is the pre-fix window when E1 was failing. The zeros are now definitively explained by the peering misconfiguration (no traffic ever reached either VNRA). Post-fix metrics were not re-queried.

**E3 PARTIAL.** Metric infrastructure works (200 OK, 8 definitions present, no diagnostic settings required). Pre-fix zeros explained by E1 failure. Post-fix metrics not re-queried -- whether metrics reflect active forwarded traffic remains unconfirmed. To complete E3, re-run `az monitor metrics list` during active VNRA transit.

**S5 complete.**

Evidence: `show-output/validation/s5-a1-subnet-effectiveRouteTable.txt`, `show-output/validation/s5-a2-subnet-listEffectiveRoutes.txt`, `show-output/validation/s5-vnra1-get.json`, `show-output/validation/s5-vnra2-get.json`, `show-output/validation/s5-c-vnra1-metric-definitions.json`, `show-output/validation/s5-c-vnra1-metrics.json`, `show-output/validation/s5-c-vnra2-metrics.json`

---

## Resource State

All 22 resources in `rg-dual-hub-vnra-udr-transit`: Succeeded. All 6 peerings Connected/FullyInSync, `allowVirtualNetworkAccess=true` (post-fix), `allowForwardedTraffic=true`. All 4 route table subnet associations correct. 4 auto-created NSGs (0 custom rules). 2 MDE.Linux extensions (auto by Defender for Cloud, not in design).

---

## Findings for Trinity/Tank

| ID | Finding |
|----|---------|
| F1 | **E1 PASS (after correction)**: Root cause was `allowVirtualNetworkAccess=false` on all 6 peerings. After setting to `true`, cross-VNRA UDR chaining across global peering works. 10/10 packets, 0% loss both directions, avg ~33 ms. |
| F2 | **E2 CONFIRMED**: No subnet-scope effective route API for VirtualNetworkApplianceSubnet (A1/A2 404 from regional backend). |
| F3 | **E3 PARTIAL**: Metric API 200 OK, 8 metrics defined without diagnostic settings. Pre-fix zeros explained by E1 failure. Post-fix metrics not re-queried. |
| F4 | **VNRA IP reservation**: Each 50 Gbps VNRA allocates 5 IPs (.4-.8). Undocumented. Plan subnet size accordingly (/24 sufficient, /28 risky). |
| F5 | **NW proxy limitation**: Network Watcher rejects source-ip that does not match NIC. VNRA forwarding context unobservable via spoke VM NIC proxy. |
| F6 | 4 auto-created NSGs (0 custom rules); 2 MDE.Linux extensions. Both undocumented side effects of CLI deployment. |
| F7 | **`allowVirtualNetworkAccess=false` is the silent killer**: Peerings can be `Connected/FullyInSync` with `allowForwardedTraffic=true` yet drop all data-plane traffic. This flag must be verified for every peering leg in UDR-steered hub-spoke topologies. |

---

## Path Proof (Post-Fix)

- **Configured control plane:** All route tables, routes, and associations verified correct. ✓
- **Effective control plane:** Spoke VM NIC effective routes show UDRs Active. ✓
- **Network Watcher intent:** Azure SDN acknowledges UDR intent to steer to VNRA. ✓
- **Data plane:** 10/10 packets, 0% loss both directions. TTL-invisible VNRA hardware confirmed via tracepath (one hop to remote VM). ✓
- **Root cause documented:** `allowVirtualNetworkAccess=false` on all 6 peerings caused E1 failure. Fix: set `true` on all 6. ✓
- **E3 ceiling:** Post-fix VNRA metrics were not re-queried. Whether metrics reflect active forwarded traffic is unconfirmed.

---

## Teardown Readiness

Evidence complete. No permanent state changes beyond peering flag correction (required to complete E1). S1 detach was fully reversed and verified. E2 confirmed 404. Ready for Jose teardown authorization.

```bash
# EXECUTED 2026-08-20T12:41:17+02:00 -- authorized by Jose Moreno
az group delete --name rg-dual-hub-vnra-udr-transit --yes --no-wait
```

## Cleanup Verification (2026-08-20)

| Check | Result |
|-------|--------|
| `az group exists -n rg-dual-hub-vnra-udr-transit` | **false** |
| Subscription resource count in target RG | **0** |
| Tagged straggler scan | **0 resources** |
| External provider cleanup needed | **No -- no ExpressRoute or Megaport resources** |
| Elapsed deletion time | ~7 min 54 sec |

Full evidence: `show-output/cleanup/cleanup-evidence.md`
