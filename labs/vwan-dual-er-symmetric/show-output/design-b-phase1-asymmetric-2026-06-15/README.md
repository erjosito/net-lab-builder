# Design B Phase 1 — Asymmetric Routing Validation

**Validated by:** Niobe (Lab Validator)  
**Date:** 2026-06-15  
**Lab state:** Design B Phase 1 deployed by Tank-3 on 2026-06-15 (deploy log: `show-output/design-b-patch/06-deploy-log.md`). Axis-2 MCR→Azure prepend **NOT applied** (deferred per deploy log §Deviations).  
**Lab:** `vwan-dual-er-symmetric` | RG: `rg-vwan-symm-103167`

---

## Hypothesis

Design B Phase 1 has both GCP Cloud Routers (`router_a` in eu-w3 and `cr_onprem_b` in eu-w4) advertising BOTH subnets (`10.50.1.0/24` + `10.50.2.0/24`) into BOTH MCRs (MCR1 + MCR2). Without the Axis-2 prepend, each Azure vHub sees each GCP prefix via multiple paths with no tiebreaker. Cross-region traffic (spoke1 10.11.0.4 ↔ VM-B 10.50.2.2) takes asymmetric paths — forward via AzFW1/MCR1, return via AzFW2/MCR2 — and the stateful firewall drops the connection.

---

## 🔴 Verdict: ASYMMETRIC ROUTING PROVED

Three independent evidence tiers all point to the same conclusion.

---

## Evidence Tiers

### Tier 1: Control Plane ✅ COMPLETE

| Check | Result |
|-------|--------|
| Hub1 effective routes | Routing-intent 10.0.0.0/8 → AzFW1 (aggregate). Per-prefix resolved at ER layer. |
| Hub2 effective routes | Same shape. 10.0.0.0/8 → AzFW2. |
| **ER1 primary/secondary** | **BOTH 10.50.1.0/24 AND 10.50.2.0/24 via MCR1** (169.254.150.121/125, AS-path 65001 16550). In Design A: only 10.50.1.0/24. |
| **ER2 primary/secondary** | **BOTH 10.50.1.0/24 AND 10.50.2.0/24 via MCR2** (169.254.148.89/93, AS-path 65002 16550). In Design A: only 10.50.2.0/24. |
| GCP router_a (eu-w3) | Now advertises BOTH prefixes to MCR1. bestRoutes: Hub1 prefixes via MCR1 (priority=0, wins). Hub2 prefixes also via MCR1 (priority=0) — MCR2 backup at priority=213. |
| **GCP cr_onprem_b (eu-w4)** | **NEW router.** ONE BGP peer: MCR2 (169.254.110.226, ASN 65002), Established, 8 learned routes. Advertises BOTH prefixes. bestRoutes: ALL Azure prefixes via MCR2. |

**Control-plane conclusion:** Hub1 BGP-selects 10.50.2.0/24 via MCR1/ER1 (direct, shorter AS-path, no Axis-2 prepend). VM-B in eu-w4 uses cr_onprem_b (GCP GLOBAL VPC regional routing) → MCR2 for all Azure-bound traffic. This creates a forced asymmetric pairing for the spoke1↔VM-B cross-region flow.

### Tier 2: Data Plane ✅ COMPLETE

| Test | Result | RTT |
|------|--------|-----|
| spoke1 (Hub1) → **VM-B** (10.50.2.2) | ❌ **TCP TIMEOUT, 100% ICMP loss** | N/A |
| spoke3 (Hub2) → VM-B (10.50.2.2) | ✅ **SSH succeeded**, 0% loss | avg 68.6ms |
| spoke1 (Hub1) → VM-A (10.50.1.2) | ✅ **SSH succeeded**, 0% loss | avg 85.9ms |

**Data-plane conclusion:** The spoke1→VM-B path FAILS while the identical policy path (spoke3→VM-B) SUCCEEDS and the same-region baseline (spoke1→VM-A) SUCCEEDS. The policy (`allow-rfc1918-any`) is not the blocker — the firewall allows the flow. The failure is caused by the return traffic going via a different firewall that has no connection state.

### Tier 3: Firewall Log Correlation ✅ COMPLETE (Blog Gold)

```
Time     | Firewall                | Event                                    | Action
---------|-------------------------|------------------------------------------|--------
20:41:25 | AZFW-HUB1-SWEDENCENTRAL | TCP SYN: 10.11.0.4:41016 → 10.50.2.2:22 | Allow
20:41:26 | AZFW-HUB1-SWEDENCENTRAL | TCP SYN retransmit (×4 total)             | Allow
20:41:30 | AZFW-HUB1-SWEDENCENTRAL | ICMP Echo: 10.11.0.4 → 10.50.2.2 (×3)   | Allow
         | AZFW-HUB2-NORTHEUROPE   | [NO ENTRIES for 10.11.0.4↔10.50.2.2]    | [SILENT DROP]
---------+-------------------------+------------------------------------------+---------
20:42:20 | AZFW-HUB2-NORTHEUROPE   | TCP SYN: 10.21.0.4:36144 → 10.50.2.2:22 | Allow
20:42:21 | AZFW-HUB2-NORTHEUROPE   | ICMP Echo: 10.21.0.4 → 10.50.2.2        | Allow
         | AZFW-HUB1-SWEDENCENTRAL | [NO ENTRIES for this flow]               | [Not in path]
```

**Firewall correlation conclusion:** AzFW1 (Hub1) saw and **allowed** 5 TCP SYNs + 3 ICMP echoes from spoke1→VM-B. AzFW2 (Hub2) logged **ZERO** entries for this flow — the return SYN-ACK from VM-B arrived at AzFW2 without a matching state entry (SYN had gone via AzFW1) and was silently dropped at the TCP state engine. Azure Firewall does not log TCP stateful drops, hence the absence is the evidence.

---

## Asymmetric Path Diagram

```
FAILED FLOW: spoke1 ↔ VM-B (10.50.2.2)
===========================================

FORWARD (SYN allowed, AzFW1 logs it):
  vm-spoke1 (10.11.0.4)
    │ Hub1/swedencentral
    ▼
  [AzFW1]  ← SYN logged → Allow
    │
    ▼ ER1/Stockholm
  MCR1 (AS 65001, Frankfurt)
    │
    ▼ via router_a (eu-w3) — GCP prefers MCR1 for Hub1 prefixes (priority=0)
  VM-B (10.50.2.2, eu-w4)

RETURN (SYN-ACK silently dropped, AzFW2 has no state):
  VM-B (10.50.2.2, eu-w4)
    │ GCP GLOBAL VPC — eu-w4 region routes via cr_onprem_b
    ▼
  cr_onprem_b (eu-w4) → MCR2 (AS 65002, Amsterdam)
    │
    ▼ ER2/Amsterdam
  Hub2/northeurope
    │ routing-intent 10.0.0.0/8 → AzFW2
    ▼
  [AzFW2]  ← SYN-ACK arrives, NO STATE for original SYN → SILENT DROP ❌
    (would need to reach Hub1→spoke1 but never gets there)

RESULT: TCP timeout. 5 SYN retransmits. 100% ICMP loss.
```

---

## Evidence Files

| File | Description | Key finding |
|------|-------------|-------------|
| `01-hub1-effective-routes.txt` | Hub1 defaultRouteTable effective routes | 10.0.0.0/8 → AzFW1 (routing-intent aggregate) |
| `02-hub2-effective-routes.txt` | Hub2 defaultRouteTable effective routes | 10.0.0.0/8 → AzFW2 |
| `03-er1-advertised.txt` | ER1 primary route table (MSEE view) | **BOTH 10.50.1.0/24 + 10.50.2.0/24 via MCR1** |
| `04-er1-learned.txt` | ER1 secondary route table | Same, via secondary MSEE peer |
| `05-er2-advertised.txt` | ER2 primary route table | **BOTH 10.50.1.0/24 + 10.50.2.0/24 via MCR2** |
| `06-er2-learned.txt` | ER2 secondary route table | Same, via secondary MSEE peer |
| `07-cr-a-status.txt` | GCP router_a status (eu-w3) | Advertises both prefixes; bestRoutes: all Azure via MCR1 |
| `08-cr-b-status.txt` | GCP cr_onprem_b status (eu-w4) **NEW** | Established, bestRoutes: all Azure via MCR2 |
| `09-tcp-a-to-b-x5.txt` | spoke1→VM-B TCP tests | ❌ Timeout; 100% loss |
| `10-tcp-b-to-a-x5.txt` | spoke3→VM-B TCP tests (control) | ✅ SSH succeeded; 68.6ms avg |
| `11-azfw1-kql-results.txt` | All AzFW KQL — correlation table | AzFW1 sees SYN; AzFW2 absent (silent drop) |
| `12-azfw2-kql-results.txt` | AzFW2-specific KQL | Confirms AzFW2 had no entries for spoke1↔VM-B |

---

## Blog Implication

> **For Kid's blog post:** Design B Phase 1 deployed both GCP Cloud Routers (`router_a` eu-w3 and `cr_onprem_b` eu-w4) advertising both GCP subnets into both Megaport MCRs — without the Axis-2 prepend tiebreaker that the design called for. The result was deterministic asymmetric routing: Azure Hub1 used MCR1 for `10.50.2.0/24` (shorter BGP AS-path wins), while GCP's VM-B used `cr_onprem_b`/MCR2 for its Hub1-bound return traffic (GCP GLOBAL VPC regional routing locks eu-w4 VMs to the eu-w4 router). The Azure Firewall logs told the story perfectly: AzFW1 (Hub1) logged 5 TCP SYN retransmits from spoke1 to VM-B — all Allowed — while AzFW2 (Hub2) logged nothing for that flow's return path (silent TCP-state drop). The fix is the Axis-2 prepend: MCR1 must prepend `10.50.2.0/24` 3× toward Hub1, and MCR2 must prepend `10.50.1.0/24` 3× toward Hub2, forcing Azure to prefer the cross-hub path for the "wrong-region" subnet and aligning both direction with the same firewall.

---

## Next Steps

1. **Proceed with Axis-2 prepend** (Mechanism C / vHub Route Maps or Megaport MCR BGP policy)
2. Re-run validation after prepend: expect spoke1→VM-B to succeed via MCR2/Hub2 (both directions)
3. See decision-inbox note: `niobe-asymmetric-evidence-2026-06-15.md`
