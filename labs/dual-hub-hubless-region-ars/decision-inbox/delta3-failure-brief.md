# Decision Brief: Δ3 Route-Map Failure — ARS Poland `HubBgpConnectionFromSpokeVnetCannotReferenceRouteMap`

**Author:** Trinity (Azure Network SME)  
**Date:** 2026-08-03T20:19+02:00  
**Status:** ✅ RESOLVED — Option C executed; Δ3 active via NVA2 BIRD prepend  
**Resolution date:** 2026-08-04 (Tank)  
**Certified:** 2026-08-04T09:39+02:00 (Niobe)  
**RG:** `rg-dual-hub-hubless-region-ars-lab3d001`  
**Evidence:** `show-output/delta3/`

---

## 1. Failure Reconstruction — What Actually Happened

Tank executed the activation contract to the letter. The sequence and its outcome:

| Step | Outcome | Evidence file |
|---|---|---|
| Preflight: no pre-existing route maps | ✅ Confirmed empty | `00-pre-existing-routemaps.json` |
| Preflight: `peer-nva2` learned 0.0.0.0/0 asPath=`65002`, nextHop=`10.20.1.4` | ✅ Baseline confirmed | `00-pre-map-ars-poland-peer-nva2-learned.json` |
| Create route map `rm-poland-nva2-default-prepend` on ars-poland | ✅ `provisioningState: Updating` then `Succeeded` | `01-create-routemap-response.json`, `03-apply-routemap-assoc-response.json` |
| ~30 min ARS upgrade completed (first route map → upgrade trigger) | ✅ ARS upgraded; surcharge active | Implicit from Succeeded state |
| **Attempt 1:** PATCH routeMap `associatedInboundConnections` = `[peer-nva2 ID]` | ❌ **`InvalidJson` — `inboundConnections` field not found** | `03-apply-routemap-inbound-response.json` |
| **Attempt 2:** PATCH bgpConnection `peer-nva2` with `routingConfiguration.inboundRouteMap` | ❌ **`HubBgpConnectionFromSpokeVnetCannotReferenceRouteMap`** | `03b-apply-via-bgpconn-response.json` |
| Rollback: deleted route map | ✅ Route map removed; ECMP restored | `99-rollback-final-routemaps.json` (empty), `99-rollback-verify-peer-nva2-learned.json` |

**Key detail from Attempt 2 error:**
```
HubBgpConnection .../bgpConnections/peer-nva2 from spoke Vnet 
with PeerIp 10.20.1.4 cannot have RouteMap.
RouteMap can only be reference on HubBgpConnections with peerIp 
within RouteServer Vnet .../virtualNetworks/vnet-poland-ars.
```

NVA2 IP is `10.20.1.4` — inside `10.20.1.0/27` (vnet-hub2). ars-poland VNet is `10.30.0.0/24`. **Both NVAs are remote (spoke-VNet peers), so the platform rejects route-map association on both.**

---

## 2. Failure Validation — Is the Error Authoritative?

### 2a. Documentation gap (pre-existing)

The official [route-maps-about](https://learn.microsoft.com/azure/route-server/route-maps-about) docs list supported connections as BGP peerings, ExpressRoute GW, and VPN GW — **no mention of the peerIp-in-ARS-VNet requirement**. This constraint is **not documented** in the public Learn content (verified 2026-08-03).

### 2b. Runtime error is authoritative

Azure Resource Manager validation is the ground truth for preview API behavior. The error `HubBgpConnectionFromSpokeVnetCannotReferenceRouteMap` is a first-class ARM error code (not a timeout, transient, or config error). It is deterministic and repeatable. **Treating it as authoritative is correct.**

### 2c. Root-cause interpretation

ARS route maps were originally designed for **vWAN Virtual Hub** BGP connections where peers are co-located in the hub VNet. The standalone ARS (`Microsoft.Network/virtualHubs`) re-uses the same API surface but enforces peerIp locality: the BGP peer IP must be within the ARS VNet's address space. Because the design intentionally places NVA1 (10.10.1.4) and NVA2 (10.20.1.4) in their respective hub VNets — which is the correct and workload-aligned topology — **neither peer qualifies for route-map association with ars-poland under the current platform constraint**.

### 2d. Attempt 1 — wrong field name

`associatedInboundConnections` is the ARM read-property name. The writable property on the BGP connection object is `routingConfiguration.inboundRouteMap`. Attempt 1 failed on JSON parse before the locality check. Attempt 2 used the correct path and surfaced the real constraint.

**Summary: Failure is real, deterministic, and fully platform-enforced. The constraint is absent from docs but present in the RP.**

---

## 3. Options Evaluation (A / B / C + synthetic peer)

### Option A — Local Relay NVA in ars-poland VNet

**Concept:** Deploy a third NVA (`vm-relay`) with IP in `10.30.0.0/24`. NVA2 peers to vm-relay, which re-originates the `0/0` to ars-poland. The relay NVA's IP is inside the ARS VNet → route-map association succeeds.

**Control-plane trace:**
```
NVA2 (10.20.1.4) →[eBGP, multi-hop]→ vm-relay (10.30.x.x) →[eBGP, local]→ ars-poland
```
Route-map applies inbound at ars-poland on the relay peering. ✅ Locality constraint satisfied.

**Data-plane consequence (critical problem):**
ARS injects `0/0 → 10.30.x.x` (relay NVA IP) into set-C spoke effective routes. The relay NVA is **not** a forwarding NVA — it has no route to on-prem (no IPsec, no VPN GW). All default-routed traffic from set-C spokes would black-hole at the relay.

To avoid the black-hole:
- Option A1: relay adds a static default `0.0.0.0/0 → NVA2` in its kernel FIB (IP forwarding enabled). Traffic flows `spoke-c1 → relay → NVA2 → hub2 GW → on-prem`. This adds a **hairpin hop** through the relay VNet.
- Option A2: relay re-originates `0/0` with next-hop set to NVA1 or NVA2 via BGP NEXT_HOP manipulation. This requires the relay to advertise a synthesized next-hop IP that is reachable from set-C spokes — achievable via route-map outbound on relay→ars-poland. Highly complex.

**Problems with Option A:**
1. **ARS-injected 0/0 next-hop = relay IP**, not NVA1/NVA2. Set-C data-plane path changes fundamentally.
2. Extra hop: latency + VMSS cost.
3. Relay becomes a new SPOF for set-C default routing.
4. **Compromises the workload-aligned ARS scaling claim:** The design's strength is that ARS injects NVA IPs directly into spokes, matching the NVA placement. A relay in ars-poland VNet breaks this alignment.
5. Required additions: 1× Standard_B2ts_v2 VM in Poland VNet, peering ars-poland↔relay VNet, new BIRD/FRR config, UDR on relay subnet, possibly a new VNet (if relay can't coexist with RouteServerSubnet-only design).
6. **Added cost:** +~$0.28/day (VM) + potential VNet peering + labor. Minor in isolation but adds permanent operational complexity.

**Verdict: ❌ Do not implement. Changes data-plane topology, undermines design principle, introduces SPOF, and adds permanent complexity for a transient validation goal.**

---

### Option B — Secondary NIC on NVA1/NVA2 in ars-poland VNet Address Space

**Concept:** Attach a secondary NIC to an existing NVA VM with an IP in `10.30.x.x`, satisfying the peerIp-in-ARS-VNet constraint.

**Explicit Azure platform constraint — NIC attachment to different VNet:**
> **Azure VMs cannot have NICs in different VNets.** All NICs on a VM must belong to the same VNet. (Source: [Azure VM networking docs](https://learn.microsoft.com/azure/virtual-network/virtual-network-network-interface-vm), confirmed behavior.) A NIC is allocated from a subnet, which belongs to a VNet. You cannot allocate a NIC from `vnet-poland-ars` and attach it to a VM in `vnet-hub1` or `vnet-hub2`.

**This option is architecturally impossible on Azure.** No workaround exists.

**Verdict: ❌ Eliminated. Verified against platform constraint — not supported.**

---

### Option C — Suppress NVA2 Default via BIRD (NVA-side prepend)

**Concept:** On NVA2, modify the existing BIRD export filter toward ars-poland to prepend ASN 65002×2 for the `0/0` prefix before advertising. ars-poland receives NVA2 path as `[65002, 65002, 65002]` (length 3) vs NVA1 path `[65001]` (length 1). NVA1 wins best-path. **No route map required.**

**Control-plane trace:**
```
NVA2 BIRD filter: export to ars_poland_0/ars_poland_1 {
  bgp_path.delete(65515);
  if net = 0.0.0.0/0 then {
    bgp_path.prepend(65002); bgp_path.prepend(65002); }
  accept;
}
```
ars-poland receives `0/0` from NVA2 with AS-PATH `[65002, 65002, 65002]`.

**Effect on ars-poland best-path:**
- NVA1: `[65001]` — length 1
- NVA2: `[65002, 65002, 65002]` — length 3
- Winner: NVA1 ✅

**ARS injects:** `0/0 → 10.10.1.4` (NVA1 only) into set-C spoke effective routes. **DEF-001 resolved.**

**Control-plane preservation:**
- Δ1 (65515 strip): unchanged — still runs in same filter.
- Δ2 (NVA2 prepend toward hub2 ARS): unchanged — applies on sessions toward ars-hub2, not ars-poland.
- S2 failover: when NVA1 drops, ars-poland best-path flips to NVA2 (`[65002, 65002, 65002]` — only path). Set-C 0/0 → NVA2. ✅ Failover preserved.
- S3 recovery: NVA1 re-peers, NVA1 path wins again. ✅

**Data-plane:** No change. ARS still injects NVA1/NVA2 IPs directly. No relay hop.

**Cost:** Zero additional Azure resources. BIRD config change on NVA2 only (SSH + `birdc configure`).

**What this does NOT provide:** Azure portal/ARM route-map demonstration. S4's stated goal was to prove ARS route-map preview behavior. Option C achieves the **same functional outcome** without a route map.

**Verdict: ✅ Functionally complete. Lowest cost, no added complexity, preserves all design principles. Does not demo ARS route-maps but achieves the routing policy objective.**

---

### Option D — Synthetic Local BGP Test Peer (teaching validation only)

**Concept:** Deploy a minimal VM (`vm-test-peer`) inside `vnet-poland-ars` (or a new /29 subnet added to it). Configure it to peer with ars-poland and advertise a **synthetic test prefix** (e.g., `192.0.2.0/24`, RFC 5737 documentation range). Apply the route map inbound on this local peering to prove map behavior on ars-poland.

**What this proves:**
- Route map creation, ARS upgrade, and association mechanics: ✅
- AS-PATH modification applied to a matched prefix: ✅
- AS-PATH after map visible in `list-learned-routes`: ✅

**What this does NOT prove:**
- Functional Δ3 policy for `0/0` on NVA2 sessions: ❌ (different peer, synthetic prefix)
- DEF-001 resolution: ❌ (synthetic prefix, not 0/0 from NVA2)
- Real NVA2 session route-map behavior: ❌

**This is a teaching/lab demo option** — it validates that the route-map API works on ars-poland for locally-peered connections, which is useful to confirm the platform supports maps in principle. It does **not** validate Δ3 policy.

**Cost:** +1 VM (`Standard_B2ts_v2`) ~+$0.28/day while running. Subnet addition to `vnet-poland-ars` (non-destructive, VNet address space has room: 10.30.0.0/24 has only 10.30.0.0/27 used).

**Verdict: ⚠️ Optional. Useful only if Jose wants to separately validate route-map mechanics as a lab exercise. Must be clearly labeled "teaching demo, not functional Δ3." Does not replace Option C for functional design.**

---

## 4. Impact on S1–S5, DEF-001, Failover, Cost

### If Option C (NVA2 BIRD prepend) is implemented:

| Item | Impact |
|---|---|
| S1 Steady State | ✅ Unchanged — NVA1 still preferred via BIRD-side prepend instead of ARS map |
| S2 Hub1 Outage | ✅ Preserved — NVA2 path (now `[65002,65002,65002]`) becomes sole path → ARS injects 0/0→NVA2 |
| S3 Hub1 Recovery | ✅ Preserved — NVA1 shorter path wins on re-peer |
| S4 Route-Map Demo | ❌ Not demonstrated (ARS route-map not used for functional Δ3) |
| S5 Prefix-Only Spoke | ✅ Unaffected — spoke-c2 prefix propagation unchanged |
| DEF-001 | ✅ **Resolved** — ECMP broken, set-C 0/0 → NVA1 only |
| Failover semantics | ✅ Identical to planned Δ3 — Poland ARS flips to NVA2 on NVA1 loss |
| Cost | ✅ No change from current baseline (~$65.86/day; ARS surcharge persists regardless) |
| Route-map surcharge | ⚠️ **Persists** — ARS already upgraded; ~$6/day continues until ARS is deleted/recreated |
| ARS upgrade state | Irreversible within current deployment — no action needed |

### DEF-001 resolution path (Option C):

The root cause is ECMP `0/0 → [NVA1, NVA2]` at ars-poland. Whether the AS-PATH differential is injected via ARS route-map (Δ3 as designed) or via BIRD-side prepend (Option C), the ars-poland best-path computation is identical. The functional outcome is indistinguishable.

---

## 5. Recommendation

### Primary: **Implement Option C — NVA2 BIRD prepend toward ars-poland**

**Rationale:**
- Achieves Δ3 functional objective (NVA1 preferred, DEF-001 resolved) by NVA-side policy, which is already the pattern for Δ1 and Δ2.
- Zero added infrastructure, zero added cost.
- Fully supported, no platform constraints, no preview caveats.
- Does not compromise any design principle.
- BIRD config change only: add `bgp_path.prepend(65002); bgp_path.prepend(65002);` for `0/0` in NVA2's export filter toward ars_poland_0 and ars_poland_1.

**What changes in design documentation:**
- Δ3 description updated: ARS route-map (preview) blocked by `HubBgpConnectionFromSpokeVnetCannotReferenceRouteMap`; platform requires peerIp in ARS VNet; NVAs are remote peers → route-map cannot be associated.
- Δ3 implemented as NVA2-side BIRD prepend (same functional outcome).
- S4 validation updated: prove via `list-learned-routes` showing NVA2 asPath = `65002 65002 65002` and effective-route c1-ep 0/0 = single NVA1 IP.

### Optional: **Add Option D (synthetic local peer) as a separate S4b sub-scenario**

Only if Jose wants a live ARS route-map demo. Clearly labeled "S4b: route-map mechanics demo (teaching)" — separate from functional Δ3. Adds ~$0.28/day for duration of test VM. Can be created and deleted within a single session.

### Do not implement: Options A or B.

---

## 6. Jose Decision Request

**Please confirm one:**

- [ ] **D1 — Option C only:** Implement NVA2 BIRD prepend; document route-map incompatibility; S4 validates functional outcome only. No new Azure resources.
- [ ] **D2 — Option C + D:** Implement BIRD prepend AND add synthetic local test peer for S4b route-map demo. +1 VM, +~$0.28/day.
- [ ] **D3 — Redesign with relay (Option A):** Accepted with understanding that data-plane topology changes (extra hop, relay SPOF). Not recommended.
- [ ] **D4 — Accept ECMP as-is:** Leave DEF-001 unresolved; document as known limitation. Not recommended.

**Trinity's recommendation: D1.**

---

## 7. Cleanup Note

The ARS route-map upgrade is permanent for this deployment. Removing the (already-deleted) route map does not revert the ARS tier. The ~$6/day surcharge persists. This has no operational impact since the lab cleanup will delete the entire RG. No action required.

---

*Trinity — 2026-08-03T20:19+02:00*
