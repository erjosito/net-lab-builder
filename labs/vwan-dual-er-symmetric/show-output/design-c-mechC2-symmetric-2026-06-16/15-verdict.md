# Mech C2 Evidence Verdict — 2026-06-16

**Captured by:** Niobe (Validation / Observability Engineer)  
**Lab:** vwan-dual-er-symmetric  
**Design:** C — Active/passive VWAN Dual-ER with AS-path de-preference  
**Mechanism:** C2 — Hub1/ER1/MCR1 primary, Hub2/ER2/MCR2 standby with 64496×5 prepends  
**Capture time:** 2026-06-16T10:36–11:33+02:00

---

## Summary Verdict

⚠️ **PARTIAL SYMMETRIC (steady state)** + ✅ **FAILOVER VALIDATED** — C2 makes MCR1 the clean best path, but GCP still installs both /24 paths and ECMP residual remains. The primary-down test succeeded: spoke prefixes moved to MCR2-only in **54.2s**, data plane recovered, and primary restored in **45.4s**.

---

## Tier 1: Control Plane BGP

### Route map configuration (file 03)

| Hub | ER connection | Route maps | Role |
|-----|---------------|------------|------|
| Hub1 | hub1ergw-circuit1 | none | Primary / clean path |
| Hub2 | hub2ergw-circuit2 | outbound `hub2-out-blanket-depref`; inbound `hub2-in-depref-gcp` | Standby / 64496×5 de-preferred |

Both vHubs use `hubRoutingPreference = ASPath`.

### GCP Cloud Router bestRoutes (files 01–02)

| destRange | MCR1 path | MCR2 path | Result |
|-----------|-----------|-----------|--------|
| 10.10.0.0/23 | 65001 12076 | — | MCR1-only ✅ |
| 10.11.0.0/24 | 65001 12076 | 65002 12076 64496×5 | BOTH installed ⚠️ |
| 10.12.0.0/24 | 65001 12076 | 65002 12076 64496×5 | BOTH installed ⚠️ |
| 10.20.0.0/23 | — | 65002 12076 | MCR2-only ✅ |
| 10.21.0.0/24 | 65001 12076 | 65002 12076 64496×5 | BOTH installed ⚠️ |
| 10.22.0.0/24 | 65001 12076 | 65002 12076 64496×5 | BOTH installed ⚠️ |

**Critical finding:** C2 forces the unprepended MCR1 path to be the intended best path for every /24, but GCP Cloud Router still keeps the prepended MCR2 route in `bestRoutes` at priority 0. This is the same residual as C1: unequal AS-path length does not eliminate GCP ECMP on /24s.

---

## Tier 2: Data Plane Probes

| File | Source | Dest | Result | Note |
|------|--------|------|--------|------|
| 04 | vm-spoke1 (10.11.0.4, Hub1) | vm_a (10.50.1.2) | 2/5 TCP:22 succeeded | 3 timeouts = ECMP/asymmetry symptom |
| 05 | vm-spoke2 (10.12.0.4, Hub1) | vm_a | Not run | VM deallocated |
| 06 | vm-spoke3 (10.21.0.4, Hub2) | vm_a | 5/5 TCP:22 succeeded | Current hash landed consistently |
| 07 | vm-spoke4 (10.22.0.4, Hub2) | vm_a | Not run | VM deallocated; no Azure VM state changes made |

---

## Tier 3: AzFW KQL Logs

Window: 2026-06-16T08:40:00Z..09:20:00Z (files 08–10)

| Firewall | Spoke source | Flows | Status |
|----------|--------------|-------|--------|
| AZFW-HUB1-SWEDENCENTRAL | 10.11.0.4 | 11 | Expected primary path |
| AZFW-HUB1-SWEDENCENTRAL | 10.21.0.4 | 5 | Expected C2 primary egress for Hub2 spoke |
| AZFW-HUB2-NORTHEUROPE | 10.21.0.4 | 5 | Residual standby-path/cross-contamination evidence |

Compared to C1's 54→1 baseline, C2 still shows standby firewall hits during steady state. The exact ratio is sample/hash dependent, but the root cause is the same /24 ECMP seen in Cloud Router.

---

## Tier 4: Megaport Product Status

File 11 confirms `/lookingGlass` is not available and both MCRs are LIVE via `/v2/product/{uid}`:

| MCR | ASN | Status | LIVE VXCs |
|-----|-----|--------|-----------|
| mcr1-vwan-symm-103167 | 65001 | LIVE / up ✅ | 3 |
| mcr2-vwan-symm-103167 | 65002 | LIVE / up ✅ | 3 |

---

## Tier 5: Deliberate Primary-Down Failover

| Phase | File | Evidence |
|-------|------|----------|
| Before | 12 | MCR1 and MCR2 peers UP; /24 residual ECMP present |
| Fault | 13 | Disabled MCR1 GCP BGP peer with `gcloud compute routers update-bgp-peer ... --no-enabled` at 11:22:45+02:00 |
| Failover | 13 | Spoke /24s became MCR2-only by 11:23:39+02:00 (**54.2s**) |
| Data plane | 13 | vm-spoke3→vm_a TCP:22 succeeded 5/5 during primary-down |
| Restore | 14 | Re-enabled MCR1 peer at 11:31:55+02:00; MCR1-primary paths returned by 11:32:40+02:00 (**45.4s**) |

During primary-down, GCP installed 10.11/24, 10.12/24, 10.21/24, and 10.22/24 via MCR2 only, with AS-path `65002 12076 64496×5`. `10.10.0.0/23` was absent during the fault, but the deployed spoke /24s were covered and data-plane recovery succeeded.

---

## Final Verdict

**⚠️ PARTIAL for steady-state symmetry; ✅ PASS for active/passive failover.**

C2 buys deterministic standby behavior and clean failover: primary-down converged to MCR2 in **54.2s**, and restoration converged back to MCR1 in **45.4s**. It does **not** fully solve steady-state symmetry because GCP keeps both /24 paths installed despite 64496×5 AS-path prepends.

**Recommendation:** proceed to **Mech C3**: suppress /24 advertisements on the standby circuit / advertise only /23 aggregates, or apply a GCP-side route-selection signal (for example MED) so standby /24s are not ECMP candidates during normal operation.
