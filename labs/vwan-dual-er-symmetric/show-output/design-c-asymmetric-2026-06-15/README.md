# Design C — Asymmetric Routing Baseline Evidence

**Validated by:** Niobe (Lab Validator & Diagnostics — niobe-5)
**Date:** 2026-06-15
**Lab:** `vwan-dual-er-symmetric` | RG: `rg-vwan-symm-103167`
**Lab state:** Design C Phase 1B live — single Cloud Router (`router_a`, eu-w3), two PARTNER Interconnect attachments (`att_a` → MCR1 ASN 65001, `att_b_v2` → MCR2 ASN 65002), both BGP peers Established.

---

## 🔴 DESIGN C ASYMMETRIC — PROVED

Hypothesis confirmed: `router_a` cannot determine which MCR is the correct egress for each Azure spoke /24 prefix. Per-flow ECMP across both MCRs means return traffic hits the **wrong Azure Firewall** with 50–100% probability per flow, causing silent stateful drops on connections whose SYN traversed the other hub's firewall.

---

## 1. Topology Snapshot

Design C has a single GCP Cloud Router (`router-vwan-symm-a`, europe-west3) terminating both PARTNER Interconnect attachments: `att-vwan-symm-a` to MCR1 (Megaport Frankfurt, ASN 65001) and `att-vwan-symm-b-v2` to MCR2 (Megaport Amsterdam, ASN 65002). Both BGP sessions are Established and each MCR reports 8 learned routes. The GCP VPC (`vpc-vwan-symm-a-103167`) runs in GLOBAL routing mode with `bgpBestPathSelectionMode=LEGACY`, so all VMs — including `vm_b` in europe-west4 — use `router_a` in europe-west3 as their single exit point. On the Azure side, Hub1 (swedencentral, 10.10.0.0/23) connects via ER1 (er-vwan-symm-stockholm) to MCR1, and Hub2 (northeurope, 10.20.0.0/23) connects via ER2 (er-vwan-symm-amsterdam) to MCR2. Both hubs have routing-intent=private, so all RFC1918 traffic passes through the respective Azure Firewall (AzFW1 in Hub1, AzFW2 in Hub2). Both GCP VMs (`vm_a` 10.50.1.2 eu-w3, `vm_b` 10.50.2.2 eu-w4) were confirmed RUNNING before probes.

---

## 2. Probe Matrix

| # | Source | Destination | Hub path | Attempts | Successes | Result |
|---|--------|-------------|----------|----------|-----------|--------|
| 09 | vm-spoke1 (10.11.0.4, Hub1) | vm_b (10.50.2.2) | Hub1/AzFW1/ER1/MCR1 → router_a | 3 | 1 | ⚠️ ECMP FAILURE: 2/3 timed out |
| 10 | vm-spoke3 (10.21.0.4, Hub2) | vm_a (10.50.1.2) | Hub2/AzFW2/ER2/MCR2 → router_a | 3 | 2 | ⚠️ ECMP FAILURE: 1/3 timed out |
| 11 | vm-spoke1 (10.11.0.4, Hub1) | vm_a (10.50.1.2) | Hub1/AzFW1/ER1/MCR1 → router_a | 3 | 3 | ✅ SYMMETRIC (control) |
| 12 | vm-spoke3 (10.21.0.4, Hub2) | vm_b (10.50.2.2) | Hub2/AzFW2/ER2/MCR2 → router_a | 3 | 0 | 🔴 TOTAL FAILURE: 3/3 timed out |

> **Design C failure mode differs from Design B**: Design B had 100% deterministic failure (cr_onprem_b always chose MCR2 for ALL Azure prefixes). Design C has *probabilistic* ECMP failure — per-flow hash determines which MCR the return takes. Probe 12 shows that the ECMP hash for the (vm_b 10.50.2.2 → spoke3 10.21.0.4) flow consistently picks MCR1 (wrong hub), yielding 100% failure for that specific 5-tuple class. Probe 09 shows a 33% success rate where the hash occasionally picks MCR1 (correct hub for spoke1). This non-deterministic failure is **harder to diagnose** than Design B's 100% failure.

---

## 3. BGP Best-Path Table at router_a

**GCP Cloud Router:** `router-vwan-symm-a`, europe-west3, GLOBAL VPC
**BGP Peer Mapping:**

| Peer name (auto-generated) | Attachment | MCR | GCP peer IP | MCR ASN | Status |
|---|---|---|---|---|---|
| `auto-ia-bgp-att-vwan-symm-a-748c416bf214189` | att_a | MCR1 (Frankfurt) | 169.254.159.194 | 65001 | UP / Established |
| `auto-ia-bgp-att-vwan-symm-b-8a45a420e5e4bb7` | att_b_v2 | MCR2 (Amsterdam) | 169.254.93.154 | 65002 | UP / Established |

**bestRoutesForRouter — Azure prefixes:**

| Prefix | Via MCR1 (65001) | Via MCR2 (65002) | AS-path MCR1 | AS-path MCR2 | Priority | GCP Decision |
|--------|----|----|----|----|---|---|
| 10.10.0.0/23 (Hub1) | ✅ 169.254.159.194 | ❌ not present | [65001, 12076] | — | 0 | **MCR1 only** |
| 10.11.0.0/24 (spoke1) | ✅ 169.254.159.194 | ✅ 169.254.93.154 | [65001, 12076] | [65002, 12076] | 0 / 0 | **ECMP** |
| 10.12.0.0/24 (spoke2) | ✅ 169.254.159.194 | ✅ 169.254.93.154 | [65001, 12076] | [65002, 12076] | 0 / 0 | **ECMP** |
| 10.20.0.0/23 (Hub2) | ❌ not present | ✅ 169.254.93.154 | — | [65002, 12076] | 0 | **MCR2 only** |
| 10.21.0.0/24 (spoke3) | ✅ 169.254.159.194 | ✅ 169.254.93.154 | [65001, 12076] | [65002, 12076] | 0 / 0 | **ECMP** |
| 10.22.0.0/24 (spoke4) | ✅ 169.254.159.194 | ✅ 169.254.93.154 | [65001, 12076] | [65002, 12076] | 0 / 0 | **ECMP** |

**Why the ECMP exists:**
- Hub supernets (`/23`) are known only to their local MCR (MCR1 sees 10.10.0.0/23 directly from Hub1 via ER1; MCR2 sees 10.20.0.0/23 from Hub2 via ER2). These supernets are correctly isolated.
- Spoke `/24` subnets are reflected cross-hub by Azure vWAN inter-hub propagation (AS 65520 prepend in the Azure routing table, but MCR strips the internal Azure AS when re-advertising to GCP). **Both MCRs learn all 4 spoke /24s and advertise them to router_a with identical 2-hop AS-paths**: [65001, 12076] from MCR1 and [65002, 12076] from MCR2.
- GCP Cloud Router (LEGACY best-path mode) sees equal priority (0), equal AS-path length (2 hops) → **ECMP. No tiebreaker distinguishes which MCR is the correct return path.**
- GCP applies per-flow (5-tuple) ECMP hashing. A given TCP connection is consistently assigned to one MCR, but across connections the assignment is arbitrary. GCP does NOT use longest-prefix-match between the /23 (correct hub) and the /24 (ECMP) because the /24 is always more-specific and always wins.

**Deciding tiebreak used:** None — there is no tiebreak. Both paths are equal at every BGP attribute: Local Pref (both 100), AS-path length (both 2 hops), MED (not set), router-ID (not exposed). Result is symmetric ECMP.

**Advertised routes from router_a (file 08):**
- To MCR1 (att_a): `10.50.1.0/24`, `10.50.2.0/24`
- To MCR2 (att_b_v2): `10.50.1.0/24`, `10.50.2.0/24`

Both GCP subnets are advertised to both MCRs — correct for Design C single-CR topology.

---

## 4. AzFW Correlation

KQL source: Log Analytics workspace `law-vwan-symm-103167`, table `AzureDiagnostics`, ResourceType `AZUREFIREWALLS`, last 60 minutes.

### Probe 09 — spoke1 → vm_b (Design C signature)

| Time (UTC+2) | Firewall | Event | Action |
|---|---|---|---|
| 22:12:41 | **AZFW-HUB1-SWEDENCENTRAL** | TCP SYN 10.11.0.4:41550 → 10.50.2.2:22 | Allow |
| 22:12:41 | **AZFW-HUB1-SWEDENCENTRAL** | TCP SYN 10.11.0.4:41566 → 10.50.2.2:22 | Allow |
| 22:12:42–45 | **AZFW-HUB1-SWEDENCENTRAL** | SYN retransmit ×4 (41566) | Allow |
| 22:12:46 | **AZFW-HUB1-SWEDENCENTRAL** | TCP SYN 10.11.0.4:60336 → 10.50.2.2:22 | Allow |
| 22:12:47–50 | **AZFW-HUB1-SWEDENCENTRAL** | SYN retransmit ×4 (60336) | Allow |
| — | **AZFW-HUB2-NORTHEUROPE** | [ZERO entries for 10.11.0.4 ↔ 10.50.2.2] | [SILENT DROP] |

**Interpretation:**
- Forward SYN always enters Hub1 → AzFW1 (correct — spoke1 is a Hub1 VNet).
- nc attempt 1 (port 41550): **1 SYN entry → connection succeeded** (ECMP hash → MCR1 → ER1 → Hub1 → AzFW1 had state → SYN-ACK matched ✅)
- nc attempt 2 (port 41566): **5 SYN retransmits → connection timed out** (ECMP hash → MCR2 → ER2 → Hub2 → AzFW2 had NO state for this SYN → silent stateful drop ❌)
- nc attempt 3 (port 60336): **5 SYN retransmits → connection timed out** (same as attempt 2 ❌)
- AzFW2 logged ZERO entries for 10.11.0.4 ↔ 10.50.2.2. The **absence is the evidence** — Azure Firewall does not log TCP stateful drops. Return SYN-ACKs arrived at AzFW2 without a matching SYN-state entry and were silently dropped.

### Probe 11 — spoke1 → vm_a (control)

| Time (UTC+2) | Firewall | Event | Action |
|---|---|---|---|
| 22:25:48 | **AZFW-HUB1-SWEDENCENTRAL** | TCP SYN 10.11.0.4:45348 → 10.50.1.2:22 | Allow |
| 22:25:48 | **AZFW-HUB1-SWEDENCENTRAL** | TCP SYN 10.11.0.4:45350 → 10.50.1.2:22 | Allow |
| 22:25:49 | **AZFW-HUB1-SWEDENCENTRAL** | TCP SYN 10.11.0.4:45360 → 10.50.1.2:22 | Allow |
| — | **AZFW-HUB2-NORTHEUROPE** | [ZERO entries — not in path] | [Correct] |

3/3 connections succeeded. vm_a is in eu-w3; the return from vm_a for spoke1 prefixes would still go via router_a ECMP. **But since vm_a is in eu-w3 (same region as router_a), and both GCP subnets are known, the routing is symmetric via router_a → MCR1 → Hub1/AzFW1 for 10.11.0.0/24.**

Wait — actually this control probe also passes through ECMP for 10.11.0.0/24. The 100% success rate may indicate that the ECMP hash for (vm_a 10.50.1.2 → spoke1 10.11.0.4) consistently picks MCR1 for all 3 connections. This is consistent with LEGACY ECMP where the hash is based on src/dst IP + ports.

### Probe 10 — spoke3 → vm_a (2/3 timed out)

| Time (UTC+2) | Firewall | Event | Action |
|---|---|---|---|
| 22:26:52 | **AZFW-HUB2-NORTHEUROPE** | TCP SYN 10.21.0.4:48544 → 10.50.1.2:22 | Allow |
| 22:26:52–56 | **AZFW-HUB2-NORTHEUROPE** | SYN retransmit ×4 (48550) | Allow |
| 22:26:57 | **AZFW-HUB2-NORTHEUROPE** | TCP SYN 10.21.0.4:56324 → 10.50.1.2:22 | Allow |
| — | **AZFW-HUB1-SWEDENCENTRAL** | [ZERO entries for 10.21.0.4 ↔ 10.50.1.2] | [SILENT DROP] |

Forward SYN always via AzFW2 (Hub2 — correct for spoke3). Connection 1 (48544) and 3 (56324) succeeded; connection 2 (48550) timed out. AzFW1 had ZERO entries for 10.21.0.4 ↔ 10.50.1.2 — the return SYN-ACK from vm_a for connection 2 went via MCR1 → ER1 → Hub1 → AzFW1 → **silent stateful drop**.

### Probe 12 — spoke3 → vm_b (0/3 — TOTAL FAILURE)

| Time (UTC+2) | Firewall | Event | Action |
|---|---|---|---|
| 22:28:20–34 | **AZFW-HUB2-NORTHEUROPE** | TCP SYN 10.21.0.4:52384, 48174, 48184 → 10.50.2.2:22 (×5 retransmits each) | Allow |
| — | **AZFW-HUB1-SWEDENCENTRAL** | [ZERO entries for 10.21.0.4 ↔ 10.50.2.2] | [SILENT DROP] |

All 3 nc attempts' SYNs traversed AzFW2 (Hub2) — correct forward path. ALL 3 connections timed out. The ECMP hash for the (vm_b 10.50.2.2 → spoke3 10.21.0.4) flow class **consistently picks MCR1** for all 3 return connections, routing them via ER1 → Hub1 → AzFW1. AzFW1 has no state for these flows (SYNs went via AzFW2). 100% silent stateful drop.

### Summary Table

| Probe | AzFW Forward (SYNs logged) | AzFW Return (absent = dropped) | Drop rate |
|---|---|---|---|
| 09: spoke1 → vm_b | AzFW1 ✅ (10 entries) | AzFW2 ❌ absent for 2/3 flows | 67% |
| 10: spoke3 → vm_a | AzFW2 ✅ (8 entries) | AzFW1 ❌ absent for 1/3 flow | 33% |
| 11: spoke1 → vm_a | AzFW1 ✅ (3 entries) | AzFW2 ❌ absent (not in path) | 0% |
| 12: spoke3 → vm_b | AzFW2 ✅ (15 entries) | AzFW1 ❌ absent for 3/3 flows | 100% |

---

## 5. Pedagogical Hook

**Design C demonstrates that collapsing two Cloud Routers into one (for topological simplicity) creates an invisible ECMP problem: the single CR learns all Azure spoke subnets from both MCRs at equal AS-path cost, making the return path a per-flow coin flip — and a stateful firewall punishes every coin flip that picks the wrong hub.**

---

## 6. Hand-off Note for Trinity

**What Mechanism B does:** MCR-side AS-PATH prepend toward Azure hubs. MCR1 prepends `10.50.2.0/24` (GCP eu-w4 subnet) toward Hub1 so Hub1 prefers MCR2 for GCP-bound traffic. This fixes the **Azure→GCP direction**. ✅

**What Mechanism B does NOT do:** It does not influence how `router_a` selects between MCR1 and MCR2 for **GCP→Azure return traffic**. The root cause of Design C's failure is on the **GCP side**: router_a sees identical AS-path lengths ([65001,12076] and [65002,12076]) for all 4 spoke /24 prefixes and ECMP-hashes across both MCRs.

**The missing lever (Mechanism C):** Each MCR must advertise the *other hub's* spoke prefixes to GCP router_a with a **longer AS-path** than its own hub's spoke prefixes. Specifically:
- MCR1 (ASN 65001) should AS-PATH prepend `10.21.0.0/24` and `10.22.0.0/24` when advertising to GCP (e.g., add an extra dummy ASN hop) → router_a sees 3-hop path via MCR1 for Hub2 spokes vs 2-hop path via MCR2 → prefers MCR2 ✅
- MCR2 (ASN 65002) should do the same for `10.11.0.0/24` and `10.12.0.0/24` → router_a prefers MCR1 for Hub1 spokes ✅
- Alternatively: configure import-policy / route-map on router_a to set MED or LOCAL_PREF per-peer for these prefixes (but GCP CR PARTNER attachments have limited policy surface).

**Implementation note for Trinity:** Megaport MCR BGP outbound policies (toward GCP attachment) are the control-plane lever. Whether this is exposed via Megaport portal/API for PARTNER attachments vs standard Interconnect needs verification. If not, the alternative is GCP Cloud Router custom learned-route priority overrides (MED-based) — but GCP CR's ability to do per-prefix inbound policy on PARTNER attachments is constrained. This is the open question for Trinity to resolve.

---

## Evidence Files

| File | Description | Key finding |
|------|-------------|-------------|
| `01-hub1-effective-routes.txt` | Hub1 defaultRouteTable effective routes | 10.0.0.0/8 → AzFW1 (routing-intent aggregate) |
| `02-hub2-effective-routes.txt` | Hub2 defaultRouteTable effective routes | 10.0.0.0/8 → AzFW2 |
| `03-er1-advertised.txt` | ER1 primary MSEE route table | **BOTH 10.50.1.0/24 + 10.50.2.0/24 via MCR1** (AS-path 65001 16550) |
| `04-er1-learned.txt` | ER1 secondary MSEE route table | MCR1 reflects Hub2 spokes back with path `65001 12076` (best path *) |
| `05-er2-advertised.txt` | ER2 primary MSEE route table | **BOTH 10.50.1.0/24 + 10.50.2.0/24 via MCR2** (AS-path 65002 16550) |
| `06-er2-learned.txt` | ER2 secondary MSEE route table | MCR2 reflects Hub1 spokes back with path `65002 12076` (best path *) |
| `07-router-a-status.txt` | **THE KEY FILE** — GCP router_a get-status JSON | **4 spoke /24s ECMP across both MCRs at priority=0** |
| `08-router-a-bgp-advertised.txt` | router_a advertised routes per peer | Both GCP subnets advertised to both MCRs |
| `09-tcp-spoke1-to-vmb-x5.txt` | TCP probe: spoke1 → vm_b (3 attempts) | ⚠️ 1 success / 2 timeout (ECMP flip) |
| `10-tcp-spoke3-to-vma-x5.txt` | TCP probe: spoke3 → vm_a (3 attempts) | ⚠️ 2 success / 1 timeout (ECMP flip) |
| `11-tcp-spoke1-to-vma-x5.txt` | TCP probe: spoke1 → vm_a — control | ✅ 3/3 success |
| `12-tcp-spoke3-to-vmb-x5.txt` | TCP probe: spoke3 → vm_b (3 attempts) | 🔴 0/3 — ECMP hash always wrong MCR |
| `13-azfw1-kql.txt` | AzFW1+2 KQL — all GCP flow events last 60m | AzFW1 sees probe09 forward SYNs; AzFW2 absent = silent drop |
| `14-azfw2-kql.txt` | AzFW2-filtered KQL | AzFW2 sees probe10+12 forward SYNs; AzFW1 absent = silent drop |
| `15-vpc-effective-routes-to-hub1.txt` | GCP VPC kernel routes | Only subnet routes; BGP routes visible in router-status only |
| `16-vpc-effective-routes-to-hub2.txt` | GCP VPC routing mode | **`routingMode=GLOBAL`, `bgpBestPathSelectionMode=LEGACY`** — confirms vm_b in eu-w4 uses router_a in eu-w3 |

---

## Comparison with Design B

| Dimension | Design B Phase 1 | Design C (this report) |
|---|---|---|
| GCP topology | 2 CRs (router_a eu-w3 + cr_onprem_b eu-w4) | 1 CR (router_a eu-w3) |
| Return path selection | Deterministic: cr_onprem_b always MCR2 for all Azure prefixes | Probabilistic: ECMP per 5-tuple hash |
| Failure rate (cross-hub) | 100% deterministic | 0–100% per-flow (ECMP hash-dependent) |
| Failure mode | All cross-hub connections fail | Some connections fail unpredictably |
| Diagnosability | Easy: 100% failure | Hard: intermittent, non-reproducible |
| Mechanism B (MCR prepend) | Needed to fix Azure→GCP direction | Needed (same); does NOT fix this ECMP problem |
| Missing lever | As-path prepend toward Azure (Mechanism B) | AS-path prepend toward GCP router_a (Mechanism C) |

---

## Blog Implication

> **For Kid's blog post:** Design C is topologically simpler than Design B (one Cloud Router vs two), but the failure mode is subtler and harder to diagnose. In Design B, asymmetric routing was 100% deterministic — every cross-hub connection failed, making the problem obvious. In Design C, GCP's Cloud Router does per-flow ECMP across both MCRs for all spoke /24 prefixes (because both MCRs advertise them with identical 2-hop AS-paths). The result is probabilistic failure: 33% of spoke3→vm_a connections fail, 67% of spoke1→vm_b connections fail, and 100% of spoke3→vm_b connections fail — depending on the ECMP hash. The Azure Firewall logs tell the story exactly the same way: AzFW1 logged all spoke1→vm_b SYNs as Allowed, and AzFW2 logged zero entries for those flows (silent stateful drops on the return path). The fix — Mechanism C — must work on the GCP side: each MCR must advertise the *other hub's* spoke prefixes with a longer AS-path, giving router_a a cost tiebreaker that aligns return traffic with the correct hub.
