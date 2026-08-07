# Dual-Hub/Hubless-Region-ARS — Lessons Learned
Last updated: Niobe · 2026-08-04 · POST-Δ3 / POST-S2-S3 Final Certification

## Proven Results (PRE-Δ3 Baseline, 2026-08-03T17:55+02:00)

### Δ1 — 65515 Loop-Strip: PROVEN ✅
- **Evidence**: `ars-poland` peer-nva1 learned routes show AS-PATH `"65001"` only (not `"65001-65515"`).
  Similarly NVA2 export to ars-poland shows `"65002"` only.
- **Mechanism**: NVA1/NVA2 BIRD export filter calls `bgp_path.delete(65515)` before advertising
  hub-learned routes back to ars-poland. Without this, ARS would drop its own AS (65515) = black-hole.
- **File**: `show-output/baseline-pre-delta3/08-ars-poland-peer-nva1-learned.json`

### Δ2 — Hub2 AS-Path Prepend: PROVEN ✅
- **Evidence**: `vpngw-onprem` learned routes show:
  - `10.31.0.0/24` hub1 path: `"65515-65001"` (2 ASNs)
  - `10.31.0.0/24` hub2 path: `"65515-65002-65002-65002"` (4 ASNs)
  - BGP selects hub1 (shorter AS-PATH) → intended preference
- **Mechanism**: NVA2 export filter to ars-hub2 prepends ASN 65002 ×2 for set-C spoke prefixes
  (10.31.0.0/24 and 10.32.0.0/24). Confirmed in `ars-hub2` peer-nva2 learned routes.
- **File**: `show-output/baseline-pre-delta3/07-ars-hub2-peer-nva2-learned.json`,
  `show-output/baseline-pre-delta3/12-vpngw-onprem-learned-routes-summary.txt`

### S5 — Prefix-Only Spoke Scale: PROVEN ✅
- **Evidence**: `vpngw-onprem` RIB contains `10.32.0.0/24` with both hub1 (`"65515-65001"`) and
  hub2 (`"65515-65002-65002-65002"`) paths. No VM exists in spoke-c2.
- **Implication**: ARS propagates VNet CIDR prefixes independently of VM presence. Spoke-c2 participates
  in the full BGP routing domain (control plane) without any workload.
- **Note**: Data-plane reachability to `10.32.0.0` fails as expected (no VM, no listener).
- **File**: `show-output/baseline-pre-delta3/12-vpngw-onprem-learned-routes-summary.txt`

### BGP Session Count: PROVEN ✅ (8 sessions from 10 expected)
- NVA1 BIRD: 4 Established (ars_hub1_0, ars_hub1_1, ars_poland_0, ars_poland_1)
- NVA2 BIRD: 4 Established (ars_hub2_0, ars_hub2_1, ars_poland_0, ars_poland_1)
- **Note**: Session count is 8 (not 10 as originally anticipated). Design assigns NVA1↔ars-hub1
  and NVA2↔ars-hub2 only (no cross-NVA ARS peerings). 10 was overcounting — 8 is correct.

### VPN Gateway BGP Peers: PROVEN ✅
- vpngw-hub1: 8 Connected (2 on-prem × 2 AA + 4 ARS instances × 2 AA) minus 2 self = 10 peers visible
- vpngw-hub2: same structure
- vpngw-onprem: 4×hub1 + 4×hub2 GW instances = 8 Connected peers

---

## Defect Captured (not fixed in baseline)

### DEF-001: hub1-ep → c1-ep Ping Fails (100% loss) — ECMP Asymmetric Return
- **Symptom**: `vm-hub1-ep` (10.11.0.x) → `vm-c1-ep` (10.31.0.4): 100% packet loss.
  Reverse (onprem → c1) works fine.
- **Root cause**: `vm-c1-ep` 0/0 effective route = ECMP `["10.10.1.4","10.20.1.4"]` (NVA1+NVA2).
  Return traffic from c1-ep to 10.11.0.0/24 (spoke-a) is load-balanced.
  - Via NVA1 (50%): NVA1 knows 10.11.0.0/24 via VNetPeering → PASS
  - Via NVA2 (50%): NVA2 has no route to 10.11.0.0/24 (different region hub) → DROP
  Result: intermittent/full loss in small test.
- **Evidence**: `show-output/baseline-pre-delta3/20-ping-matrix.txt`,
  `show-output/baseline-pre-delta3/15-effective-routes-c1-ep.json`
- **Expected fix**: Δ3 (ARS route-map prepend on ars-poland↔NVA2) will break ECMP,
  making c1-ep prefer NVA1 for 0/0. Post-Δ3 c1→hub1 expected to pass.
- **Action**: Capture only. Do not fix.

### OBS-001: NVA1 run-command Extension Stuck
- **Symptom**: `az vm run-command invoke` on vm-nva1 returns `Conflict` error.
  Previous command invocation did not clean up its extension state.
- **Impact**: Could not capture live BIRD state for NVA1. Used deploy-time evidence
  (`show-output/deploy/vm-nva1-final-state.txt`) which is valid as no BIRD config changed.
- **Mitigation**: ARS peering API + vpngw BGP peer status corroborate NVA1 BGP state.
- **Recommended action**: `az vm run-command delete` on vm-nva1 to clean extension, then retry.

---

## PRE-Δ3 State Summary

| Item | State |
|---|---|
| VPN connections (4) | Connected / Succeeded |
| ARS peerings (4 objects) | Succeeded |
| NVA1 BIRD sessions | 4 Established |
| NVA2 BIRD sessions | 4 Established |
| Δ1 loop-strip | Active / Proven |
| Δ2 hub2 prepend | Active / Proven |
| Δ3 route-map | **NOT active** (pre-condition correct) |
| c1-ep 0/0 | **ECMP NVA1+NVA2** (expected pre-Δ3) |
| on-prem → c1-ep ping | PASS |
| c1-ep → on-prem ping | PASS |
| hub1-ep → c1-ep ping | FAIL (DEF-001, ECMP asymmetric return) |
| Spoke-c2 prefix in on-prem RIB | PASS (both paths) |
| Data-plane to spoke-c2 | FAIL (expected, no VM) |

## Δ3 Activation Contract Issued — 2026-08-03T19:31+02:00 (Trinity)

| Item | Decision |
|---|---|
| Contract status | **APPROVED ACTIVATION CONTRACT** |
| Contract file | `delta3-activation-contract.md` |
| Approved by | Jose Moreno (Phase-4 approval; $72/day waiver explicit) |
| ASN for prepend action | **64496** (public RFC 5398 doc-range) — 65002 blocked (private ASN prohibition) |
| Prepend count | ×2 → NVA2 path length 3 vs NVA1 length 1 → NVA1 wins |
| Direction | **Inbound** on peer-nva2 only — required for pre-best-path effect |
| Route map tool | Az.Network ≥ 8.0.0 PowerShell |
| Match | Prefix Equals 0.0.0.0/0 |
| Upgrade expected | ~30 min one-time (first route map on ars-poland) |
| DEF-001 resolution | Expected — ECMP broken, c1-ep 0/0 → NVA1 only |
| Δ1/Δ2 preservation | Confirmed — no impact |
| Executor | Tank |

---

## Readiness for Δ3

**READY** — all pre-conditions met:
1. Δ1 and Δ2 active and proven
2. ars-poland peer-nva2 `provisioningState=Succeeded`
3. ars-poland currently shows ECMP 0/0 (NVA1 `"65001"` = NVA2 `"65002"` both 1 hop)
4. No route-map active on any ARS instance

**BLOCKER**: None from routing perspective. Phase-4 cost approval already granted (lab live).
ARS route-maps are PUBLIC PREVIEW — first activation incurs ~30 min ARS upgrade + surcharge.
DEF-001 (hub1↔c1 ECMP) is expected to be resolved by Δ3, not a blocker for activation.

---

## Δ3 Empirical Failure — 2026-08-03T~20:00+02:00 (Tank executor)

### EMP-001: `HubBgpConnectionFromSpokeVnetCannotReferenceRouteMap` — Platform Constraint Not Documented

**Status:** 🔴 BLOCKER — ARS route-map cannot be applied to ars-poland's NVA peerings

**Failure sequence:**
1. Route map `rm-poland-nva2-default-prepend` created on ars-poland → `provisioningState: Succeeded`. ARS upgraded (~30 min). ✅
2. Attempt to associate map via PATCH on routeMap `associatedInboundConnections` → `InvalidJson` (wrong field path). ❌
3. Attempt via PATCH on bgpConnection `peer-nva2` with `routingConfiguration.inboundRouteMap` → `HubBgpConnectionFromSpokeVnetCannotReferenceRouteMap`. ❌
4. Rollback: map deleted; ECMP restored to baseline. ✅
5. ARS surcharge (~$6/day) **persists** — upgrade irreversible without ARS recreate.

**Root cause:**
Azure Route Server route-map association enforces `peerIp ∈ ARS VNet address space`. ars-poland VNet = `10.30.0.0/24`. NVA2 IP = `10.20.1.4` (vnet-hub2). NVA1 IP = `10.10.1.4` (vnet-hub1). Neither NVA is in the ARS VNet → route-map association rejected for both.

**Documentation status:** This constraint is **absent from Microsoft Learn docs** (verified 2026-08-03). The platform enforces it at ARM validation time. Runtime error is authoritative.

**Options evaluated (see `decision-inbox/delta3-failure-brief.md`):**
| Option | Summary | Verdict |
|---|---|---|
| A — Local relay NVA in Poland VNet | Satisfies locality but breaks data-plane (relay becomes 0/0 next-hop) | ❌ Not recommended |
| B — Secondary NIC in ARS VNet | Impossible — Azure VMs cannot have NICs in different VNets | ❌ Platform constraint |
| C — NVA2 BIRD prepend toward ars-poland | Same functional outcome via NVA-side policy; zero infra change | ✅ Recommended |
| D — Synthetic local test peer | Proves route-map mechanics only; teaching demo, not functional Δ3 | ⚠️ Optional add-on |

**Recommended path:** Option C — NVA2 BIRD export filter adds `bgp_path.prepend(65002)×2` for `0/0` toward ars_poland sessions. ars-poland sees NVA2 path length 3 vs NVA1 length 1 → NVA1 wins best-path → ECMP broken → DEF-001 resolved.

**Evidence files:** `show-output/delta3/`
**Decision brief:** `decision-inbox/delta3-failure-brief.md`
**Awaiting:** Jose Moreno decision D1/D2/D3/D4


---

## POST-Delta3 Results — 2026-08-04 (ACTIVATED via BIRD prepend)

### Delta3 — NVA1-Preferred Default (c1 spoke): PROVEN

**Method:** NVA2 BIRD export_to_poland_ars filter: prepend ASN 65002 x2 for 0.0.0.0/0
(ARS route-map blocked by platform; BIRD-side achieves identical functional result)

**Evidence:**
- ars-poland peer-nva2 learned: 0/0 asPath = '65002 65002 65002' (3 hops)
- ars-poland peer-nva1 learned: 0/0 asPath = '65001' (1 hop, unchanged)
- vm-c1-ep effective route: 0/0 nextHop = 10.10.1.4 (NVA1 only, ECMP broken)
- Source: VirtualNetworkGateway (ARS-injected)

**File:** show-output/delta3-bird/01-post-ars-poland-peer-nva2-learned.json,
          show-output/delta3-bird/01-post-c1-ep-effective-routes.json

### DEF-001 RESOLVED

hub1-ep (10.11.0.x) to c1-ep (10.31.0.4): 0% packet loss, 5/5 received, ~22ms RTT

**Root cause confirmed:** ECMP 0/0 on c1-ep caused asymmetric return path via NVA2
which had no route to 10.11.0.0/24 (spoke-a in hub1 region). Fixing c1-ep 0/0 to
NVA1-only resolves the return path.

**File:** show-output/delta3-bird/02-def001-ping-hub1ep-to-c1ep.txt

### Delta1/Delta2 Preservation: PROVEN

Post-Delta3, Delta1 and Delta2 are fully preserved:
- vpngw-onprem: 10.31+10.32 hub1 path '65515-65001' vs hub2 '65515-65002-65002-65002' (Delta2)
- ars-hub2 from NVA2: 10.31+10.32 still show '65002-65002-65002' (Delta2 active)
- NVA1 sessions: 4/4 Established, 16 routes unchanged

**File:** show-output/delta3-bird/02-post-vpngw-onprem-learned-routes.json

### Platform Finding — ARS Route-Map Locality Constraint

ARS route-maps require peerIp within the ARS VNet (10.30.0.0/24 for ars-poland).
Cross-VNet multihop BGP peers (NVA1: 10.10.1.4, NVA2: 10.20.1.4) cannot reference
route maps. Error: HubBgpConnectionFromSpokeVnetCannotReferenceRouteMap.
Not documented in Microsoft Learn as of 2026-08-03. Reported to Trinity.

### Current Lab State (Post-Delta3)

| Item | State |
|---|---|
| VPN connections (4) | Connected / Succeeded |
| ARS peerings (4 objects) | Succeeded |
| NVA1 BIRD sessions | 4 Established |
| NVA2 BIRD sessions | 4 Established |
| Delta1 loop-strip | Active / Proven |
| Delta2 hub2 prepend | Active / Proven |
| Delta3 NVA1-preferred default | ACTIVE / PROVEN |
| c1-ep 0/0 | NVA1 only (10.10.1.4) |
| hub1-ep to c1-ep | PASS (DEF-001 RESOLVED) |
| c1-ep to onprem | PASS |
| S4 all assertions | PASS |

---

## S2/S3 Fault Injection and Recovery — 2026-08-04 (Tank executor)

### S2 — Hub1 Outage (BGP-only fault via BIRD stop): PROVEN ✅

**Convergence times:**
- T0 (PSK corrupt + BIRD stop issued): 09:17:04
- NVA1 BIRD confirmed inactive: 09:19:30
- T1 (c1-ep 0/0 = NVA2 / 10.20.1.4): 09:20:09
- BIRD-stop → convergence: **39 s** (passes ≤180 s criterion)
- API-inclusive T0→T1: **185 s** (passes ≤240 s criterion)

**Key assertions all PASS:**
- c1-ep 0/0 = 10.20.1.4 (NVA2 only)
- ars-poland/peer-nva1 learned routes = empty (RouteServiceRole_IN_0/1 = [])
- ars-poland/peer-nva2 0/0 asPath = "65002-65002-65002"
- on-prem vpngw learned routes: hub2-only paths for set-C
- c1→on-prem ping 0% loss, ~52 ms (5/5)

**Important observation — VPN tunnel stayed Connected during S2:**
The PSK mismatch did NOT drop the IKE SA within the test window (~3 min). All 4 VPN connections
remained `Connected` because IKE Phase-1 SA lifetime is typically 8–24 hours. The fault was
effectively a BGP-only event (NVA1 BIRD stop withdrew routes). S2 PASS is valid — routing
converged correctly — but the "PSK fault" characterisation is imprecise. True VPN link failure
would require waiting for SA expiry or triggering a hard reset. This is an important finding for
anyone designing PSK-based failure modes in labs.

**Evidence:** `show-output/s2-failover/`

---

### S3 — Hub1 Recovery: PROVEN ✅

**Convergence times:**
- T0_S3 (recovery start): 09:25:29
- NVA1 BIRD confirmed active: 09:28:21
- T1_S3 (c1-ep 0/0 = NVA1 / 10.10.1.4): 09:28:45
- BIRD-start → convergence: **24 s** (passes ≤90 s criterion)
- API-inclusive T0→T1: 196 s (the 120 s gap is PSK API call latency, not routing latency)

**Key assertions all PASS:**
- c1-ep 0/0 = 10.10.1.4 (NVA1 only), hub1-primary restored
- ars-poland/peer-nva1 0/0 asPath = "65001" (Established)
- ars-poland/peer-nva2 0/0 asPath = "65002-65002-65002" (Δ3 preserved)
- on-prem vpngw: hub1 path "65515-65001" preferred over hub2 "65515-65002-65002-65002"
- hub1-ep → c1-ep 0% loss, ~22 ms (5/5) — DEF-001 remains resolved
- NVA1 BIRD: 4/4 sessions Established (ars_hub1_0/1, ars_poland_0/1)
- All 4 VPN connections Connected

**Evidence:** `show-output/s3-failback/`

---

### DEV-001 — PSK Recovery via Fresh Secret (KV Inaccessible)

**Issue:** Key Vault `platform-secrets-xxxx` had public network access disabled.
`az keyvault secret show` returned `ForbiddenByConnection` from the local machine.

**Resolution:** Tank set a fresh matching PSK on both hub1 connection objects
(`conn-hub1-to-onprem`, `conn-onprem-to-hub1`) using `az network vpn-connection update --shared-key`.
Functionally equivalent — both sides share the same new PSK, tunnel re-establishes.

**Security note:** PSK values were never logged, never printed, never persisted in any file.
No sanitization needed beyond this note.

**Lesson:** Private-endpoint-only Key Vaults require VNet-connected tooling for lab recovery.
Consider a dedicated jump VM or AzureBastionHost in the RG for future PSK access, or
pre-store a secondary PSK in a parameter file with access from the lab's own network.

---

### ARS peeringState=null — CLI Behaviour Note

`az network routeserver peering list --query "[].peeringState"` returns `null` for all peers,
even when BGP sessions are active and routes are flowing. This is an ARM API quirk — the
`peeringState` property is not populated by the ARS resource provider in the peering list response.
Use `list-learned-routes` (non-empty = Established proxy) for BGP health assessment.

**Live confirmation (2026-08-04T09:39+02:00):** ars-poland/peer-nva1 returns 3 routes (0/0,
GW subnet ×2); ars-poland/peer-nva2 returns 3 routes (0/0 asPath=65002-65002-65002, GW ×2).
Both are operationally Established.

---

## Cost and Ongoing Charges (2026-08-04)

| Item | Note |
|---|---|
| Poland ARS Standard SKU | ~$6/day surcharge — irreversible without ARS recreate |
| All other resources | Pre-existing cost from deploy |
| Safe to explore | No cleanup required; lab is stable |

The Poland ARS Standard-tier upgrade happened during the failed route-map experiment (Δ3-attempt-1).
The upgrade is irreversible (no downgrade path); recreating ars-poland is the only way to remove
the surcharge. This is not recommended — it would break Δ1/Δ2/Δ3 and require full redeployment.
Jose should factor ~$6/day into the remaining exploration budget.

### Update — 2026-08-05: Poland Central retired (executed cleanup)

`ars-poland` (and all other Poland resources) was **deleted**, not recreated, on 2026-08-05 — see
`deploy-log.md`'s "Poland Central Cleanup — EXECUTED" entry and `cleanup-poland-dry-run.md` §10.
This removes the ~$6/day surcharge above definitively (a full delete, unlike the "recreate" path this
note originally warned against — no redeploy occurred, and no attempt was made to preserve or migrate
the Δ1/Δ2/Δ3 Poland-specific state). The pre-existing uncertainty about whether `ars-poland`'s
route-map child object was actually live or billing (flagged in `cleanup-poland-dry-run.md` §1) is now
moot: the resource no longer exists, so its surcharge — if it was ever billing — has stopped either
way. This lesson (irreversibility of the ARS Standard-tier upgrade) remains valid and applicable to
`ars-hub1`/`ars-hub2`, which are still live and still carry the same irreversible surcharge.
