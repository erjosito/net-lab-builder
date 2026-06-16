# Evidence Pack: Design C — Mech C1 (Active/Active + AS-Path De-preference)
# Capture date: 2026-06-16
# Captured by: Niobe (Validation / Observability Engineer)

## ⚠️ PARTIAL SYMMETRIC

> Mech C1 reduces AzFW cross-contamination by 98% (54→1 flows per firewall) but does not achieve full symmetry due to GCP Cloud Router ECMP on /24 prefixes.

---

## File Inventory

| # | File | Tier | Contents | Status |
|---|------|------|----------|--------|
| 01 | `01-cr-status-full.json` | T1/BGP | `gcloud compute routers get-status router-vwan-symm-a europe-west3` full JSON | ✅ |
| 02 | `02-cr-routes-summary.txt` | T1/BGP | Formatted route table: destRange, nextHop, AS-path, path-len, winner | ✅ |
| 03 | `03-az-routemap-hub1.json` | T1/BGP | Hub1 outbound route map config (hub1-out-depref-hub2) | ✅ |
| 04 | `04-az-routemap-hub2.json` | T1/BGP | Hub2 outbound route map config (hub2-out-depref-hub1) | ✅ |
| 05 | `05-er-connection-routing.txt` | T1/BGP | ER connection outboundRouteMap IDs for ergw-hub1 and ergw-hub2 | ✅ |
| 06 | `06-probe-spoke1-vma.txt` | T2/Data | vm-spoke1 (10.11.0.4) → vm_a (10.50.1.2): 4/5 TCP:22 success | ✅ |
| 07 | `07-probe-spoke1-vmb.txt` | T2/Data | vm-spoke1 → vm_b (10.50.2.2): NOT DEPLOYED in eu-w4 | ⚠️ |
| 08 | `08-probe-spoke3-vma.txt` | T2/Data | vm-spoke3 (10.21.0.4) → vm_a (10.50.1.2): 2/5 TCP:22 (ECMP evidence) | ⚠️ |
| 09 | `09-probe-spoke3-vmb.txt` | T2/Data | vm-spoke3 → vm_b (10.50.2.2): NOT DEPLOYED in eu-w4 | ⚠️ |
| 10 | `10-azfw1-kql.txt` | T3/AzFW | Hub1 AzFW: 49 Hub1-spoke flows, 1 cross-contamination flow (Hub2 spoke) | ⚠️ |
| 11 | `11-azfw2-kql.txt` | T3/AzFW | Hub2 AzFW: 53 Hub2-spoke flows, 1 cross-contamination flow (Hub1 spoke) | ⚠️ |
| 12 | `12-mcr1-looking-glass.json` | T4/MCR | MCR1 product info (LG endpoint N/A): ASN 65001, LIVE, all VXCs up | ⚠️ |
| 13 | `13-mcr2-looking-glass.json` | T4/MCR | MCR2 product info (LG endpoint N/A): ASN 65002, LIVE, all VXCs up | ⚠️ |
| 14 | `14-verdict.md` | Summary | Full analysis with ECMP finding and cross-contamination metric | ✅ |

---

## Key Metrics

| Metric | Asymmetric baseline (06-15) | Post Mech C1 (06-16) | Verdict |
|--------|----------------------------|----------------------|---------|
| Hub1 AzFW cross-contamination | 54 flows | **1 flow** | ✅ 98% reduction |
| Hub2 AzFW cross-contamination | 54 flows | **1 flow** | ✅ 98% reduction |
| GCP /23 supernets: single-path | ❌ Not confirmed | ✅ MCR1-only / MCR2-only | ✅ Working |
| GCP /24 prefixes: single-path | ❌ ECMP | ❌ ECMP (unchanged) | ❌ Not fixed |
| spoke1→vm_a success rate | 5/5 | 4/5 | ✅ Connected |
| spoke3→vm_a success rate | (not tested) | 2/5 (ECMP impact) | ⚠️ Partial |

---

## Critical ECMP Finding (Blog-worthy)

GCP Cloud Router `router-vwan-symm-a` installs **both paths** in `bestRoutes` for /24 prefixes despite AS-path length differences of **2 vs 5 hops** (Hub1 prefixes) and **2 vs 7 hops** (Hub2 prefixes). GCP does NOT use AS-path length as a tiebreaker to eliminate ECMP — it routes across both paths equally.

This is a significant architectural finding: AS-path de-preference (AS_TRANS prepend ×3) does NOT prevent GCP ECMP for specific /24 routes. The Mech C1 mechanism achieves symmetry only for /23 **aggregate** routes (which are single-path, no ECMP). Specific /24 destinations remain ECMP'd.

**Evidence:** `02-cr-routes-summary.txt` — both 10.11.0.0/24 and 10.21.0.0/24 appear twice in `bestRoutes` with different next-hop IPs (MCR1 and MCR2).

---

## Megaport LG Status

The Megaport API v2 `/v2/product/mcr2/{uid}/lookingGlass` endpoint returns HTTP 404 — the looking-glass feature is not available via API for MCR2 products. Files 12–13 contain product info (operational status only).

Both MCRs are LIVE with all production VXCs operational.

---

## Comparison to Design C Asymmetric Baseline

Evidence folder: `../design-c-asymmetric-2026-06-15/`

The asymmetric baseline showed 54 cross-contamination flows in each direction — every Hub2 spoke TCP flow to GCP appeared in Hub1's AzFW and vice versa, because GCP used whichever MCR it preferred without regard for the spoke's hub affinity.

Post Mech C1: reduced to 1 cross-contamination flow per firewall, matching expected GCP ECMP noise for /24 prefixes.
