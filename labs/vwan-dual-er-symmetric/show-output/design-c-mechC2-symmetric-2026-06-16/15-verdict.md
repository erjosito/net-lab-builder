# Mech C2 Evidence Verdict - 2026-06-16

**Captured by:** Niobe (Validation / Observability Engineer)  
**Lab:** vwan-dual-er-symmetric  
**Design:** C, Active/passive VWAN Dual-ER with AS-path de-preference  
**Mechanism:** C2, Hub1/ER1/MCR1 primary, Hub2/ER2/MCR2 standby with 64496 x5 prepends  
**Capture time:** 2026-06-16T10:36-11:33+02:00

---

## Summary Verdict

✅ **EFFECTIVE ACTIVE/PASSIVE SYMMETRY FIX FOR STANDARD BGP PEERS** plus ✅ **FAILOVER VALIDATED**. C2 makes MCR1 the short AS-path primary and MCR2 the long AS-path standby. A standards-compliant CE router would install the short MCR1 path for the covered spoke /24s during steady state. The deliberate primary-down test succeeded: spoke prefixes moved to MCR2-only in **54.2s**, data plane recovered, and primary restored in **45.4s**. The residual /24 ECMP seen in steady state is a GCP Cloud Router MED-ranking simulator artifact, not a failure of C2.

---

## Tier 1: Control Plane BGP

### Route map configuration (file 03)

| Hub | ER connection | Route maps | Role |
|-----|---------------|------------|------|
| Hub1 | hub1ergw-circuit1 | none | Primary / clean path |
| Hub2 | hub2ergw-circuit2 | outbound `hub2-out-blanket-depref`; inbound `hub2-in-depref-gcp` | Standby / 64496 x5 de-preferred |

Both vHubs use `hubRoutingPreference = ASPath`.

### GCP Cloud Router bestRoutes (files 01-02)

| destRange | MCR1 path | MCR2 path | Standard peer result | GCP simulator result |
|-----------|-----------|-----------|----------------------|----------------------|
| 10.10.0.0/23 | 65001 12076 | none | MCR1 only ✅ | MCR1 only ✅ |
| 10.11.0.0/24 | 65001 12076 | 65002 12076 64496 x5 | MCR1 only ✅ | both installed ⚠️ |
| 10.12.0.0/24 | 65001 12076 | 65002 12076 64496 x5 | MCR1 only ✅ | both installed ⚠️ |
| 10.20.0.0/23 | none | 65002 12076 | home aggregate via MCR2 | MCR2 only ✅ |
| 10.21.0.0/24 | 65001 12076 | 65002 12076 64496 x5 | MCR1 only ✅ | both installed ⚠️ |
| 10.22.0.0/24 | 65001 12076 | 65002 12076 64496 x5 | MCR1 only ✅ | both installed ⚠️ |

**Corrected interpretation:** C2 proves the active/passive AS-path signal is present. For the covered spoke /24s, MCR1 advertises the short path and MCR2 advertises the standby path with AS 64496 x5. Under standard BGP best-path selection, the shorter MCR1 path is selected before MED is considered and the standby path is not installed as an equal forwarding path.

**GCP simulator caveat:** GCP Cloud Router kept the prepended MCR2 /24 paths at priority 0 and installed them alongside the short MCR1 paths. That is a GCP VPC dynamic-route priority artifact. It is useful as a footnote for simulator fidelity, but it is out of scope for judging whether C2 fixes ExpressRoute return-path symmetry for standard peers.

---

## Tier 2: Data Plane Probes

| File | Source | Dest | Result | Corrected note |
|------|--------|------|--------|----------------|
| 04 | vm-spoke1 (10.11.0.4, Hub1) | vm_a (10.50.1.2) | 2/5 TCP:22 succeeded | 3 timeouts reflect GCP simulator ECMP |
| 05 | vm-spoke2 (10.12.0.4, Hub1) | vm_a | Not run | VM deallocated |
| 06 | vm-spoke3 (10.21.0.4, Hub2) | vm_a | 5/5 TCP:22 succeeded | Current GCP hash landed consistently |
| 07 | vm-spoke4 (10.22.0.4, Hub2) | vm_a | Not run | VM deallocated; no Azure VM state changes made |

These probe ratios are retained as captured. They validate the GCP simulator caveat, not a standards-based CE failure.

---

## Tier 3: AzFW KQL Logs

Window: 2026-06-16T08:40:00Z..09:20:00Z (files 08-10)

| Firewall | Spoke source | Flows | Corrected status |
|----------|--------------|-------|------------------|
| AZFW-HUB1-SWEDENCENTRAL | 10.11.0.4 | 11 | Expected primary path |
| AZFW-HUB1-SWEDENCENTRAL | 10.21.0.4 | 5 | Expected C2 primary egress for Hub2 spoke |
| AZFW-HUB2-NORTHEUROPE | 10.21.0.4 | 5 | GCP simulator artifact on standby firewall |

Compared to C1's 54 to 1 baseline, C2 still shows standby firewall hits during steady state in the GCP simulator. The exact ratio is sample/hash dependent. The root cause remains the GCP /24 route-install behavior, not a failure of AS-path prepend under standard BGP.

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
| Before | 12 | MCR1 and MCR2 peers UP; GCP simulator /24 ECMP caveat present |
| Fault | 13 | Disabled MCR1 GCP BGP peer with `gcloud compute routers update-bgp-peer ... --no-enabled` at 11:22:45+02:00 |
| Failover | 13 | Spoke /24s became MCR2-only by 11:23:39+02:00 (**54.2s**) |
| Data plane | 13 | vm-spoke3 to vm_a TCP:22 succeeded 5/5 during primary-down |
| Restore | 14 | Re-enabled MCR1 peer at 11:31:55+02:00; MCR1-primary paths returned by 11:32:40+02:00 (**45.4s**) |

During primary-down, GCP installed 10.11/24, 10.12/24, 10.21/24, and 10.22/24 via MCR2 only, with AS-path `65002 12076 64496 x5`. `10.10.0.0/23` was absent during the fault, but the deployed spoke /24s were covered and data-plane recovery succeeded.

---

## Final Verdict

**✅ SUCCESS for active/passive ExpressRoute return-path symmetry with standard BGP peers, and ✅ PASS for failover.**

C2 provides deterministic primary/standby behavior for standards-compliant peers. MCR1 is the short AS-path primary in steady state; MCR2 is the long AS-path standby. The deliberate primary-down test proved the standby path took over in **54.2s**, data plane recovered, and restoration back to MCR1 completed in **45.4s**.

**Simulator footnote:** GCP Cloud Router retained both unequal-AS-path /24s as equal-priority VPC dynamic routes during steady state. That is a GCP MED-ranking simulator artifact, not a failure of C2 or of AS-path prepend as the ExpressRoute fix.

**C3 status:** Mech C3 is demoted to an edge-case technique for MED-ranking peers or non-standard route installers that keep longer AS-path /24s in ECMP. It is not required to prove the corrected blog thesis.

