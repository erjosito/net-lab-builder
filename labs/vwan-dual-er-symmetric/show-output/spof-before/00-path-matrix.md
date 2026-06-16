# MCR1 SPOF — Path Matrix (before P1+P2)

**Captured:** 2026-06-15T19:24:55+02:00  
**Evidence sources:** ER circuit route tables (files 03–06), GCP Cloud Router status (files 07–08), connectivity tests (file 10)  

## Inferred path matrix — steady state

| Source segment | Destination segment | Path observed | Single MCR in path? |
|---|---|---|---|
| spoke1 (hub1, swedencentral) | gcp-vpc-a (`10.50.1.0/24`) | hub1 → ER1 → MCR1 → GCP VPC-A | **YES — MCR1** |
| spoke1 (hub1, swedencentral) | gcp-vpc-b (`10.50.2.0/24`) | hub1 → hub2 (vWAN) → ER2 → MCR2 → GCP VPC-B | **YES — MCR2** |
| spoke2 (hub1, swedencentral) | gcp-vpc-a (`10.50.1.0/24`) | hub1 → ER1 → MCR1 → GCP VPC-A | **YES — MCR1** |
| spoke2 (hub1, swedencentral) | gcp-vpc-b (`10.50.2.0/24`) | hub1 → hub2 (vWAN) → ER2 → MCR2 → GCP VPC-B | **YES — MCR2** |
| spoke3 (hub2, northeurope) | gcp-vpc-a (`10.50.1.0/24`) | hub2 → hub1 (vWAN) → ER1 → MCR1 → GCP VPC-A | **YES — MCR1** |
| spoke3 (hub2, northeurope) | gcp-vpc-b (`10.50.2.0/24`) | hub2 → ER2 → MCR2 → GCP VPC-B | **YES — MCR2** |
| spoke4 (hub2, northeurope) | gcp-vpc-a (`10.50.1.0/24`) | hub2 → hub1 (vWAN) → ER1 → MCR1 → GCP VPC-A | **YES — MCR1** |
| spoke4 (hub2, northeurope) | gcp-vpc-b (`10.50.2.0/24`) | hub2 → ER2 → MCR2 → GCP VPC-B | **YES — MCR2** |

## Evidence key

- **MCR1 is the sole path for 10.50.1.0/24:** ER1 primary and secondary route tables show `10.50.1.0/24 via 169.254.150.121 / 169.254.150.125` (both MCR1 BGP peers, ASN 65001). ER2 route table has NO entry for `10.50.1.0/24`.
- **MCR2 is the sole path for 10.50.2.0/24:** ER2 primary and secondary route tables show `10.50.2.0/24 via 169.254.148.89 / 169.254.148.93` (both MCR2 BGP peers, ASN 65002). ER1 route table has NO entry for `10.50.2.0/24`.
- **GCP VPC-A has ONE BGP peer (MCR1 at 169.254.159.194, ASN 65001).** No secondary or cross-region peer exists. `bgpPeerStatus[0].state = "Established"`, `numLearnedRoutes = 8` (all Azure prefixes arrive via MCR1 only).
- **GCP VPC-B has ONE BGP peer (MCR2 at 169.254.87.242, ASN 65002).** Symmetric situation.
- **Live ping confirms connectivity:** All 4 cross-product pairs reachable (0% loss). Cross-region paths (spoke3→VPC-A, spoke1→VPC-B) show TTL=58 vs TTL=59 for same-region paths — the extra hub-to-hub hop is visible.

## MCR1 SPOF blast radius (from Trinity §1.6 F-table)

| Failure | Affected flows | All paths through single MCR? |
|---|---|---|
| MCR1 down (F1) | ALL spokes → gcp-vpc-a; gcp-vpc-a → ALL spokes | **YES — 0 alternate paths** |
| MCR1↔ER1 BGP drops (F11) | Same as F1 | **YES** |
| ER1 circuit failure (F3) | Same as F1 (MCR1 loses Azure routes, withdraws from GCP VPC-A) | **YES** |

**F9 / F10 (single VXC failure on ER1) are the only currently mitigated cases** — dual-VXC (primary + secondary) per circuit provides BGP redundancy within ER1. MCR1 itself has no redundancy.

## ASN / peer IP summary (for Oracle diagram labels)

| Entity | ASN | BGP peer IPs |
|---|---|---|
| MCR1 (Frankfurt FR5) | 65001 | MSEE primary: `169.254.150.121`; MSEE secondary: `169.254.150.125`; GCP-facing: `169.254.159.194` |
| MCR2 (Amsterdam AM1) | 65002 | MSEE primary: `169.254.148.89`; MSEE secondary: `169.254.148.93`; GCP-facing: `169.254.87.242` |
| GCP Cloud Router A (VPC-A, europe-west3) | 16550 | Interface: `169.254.159.193`; peer: `169.254.159.194` (MCR1) |
| GCP Cloud Router B (VPC-B, europe-west4) | 16550 | Interface: `169.254.87.241`; peer: `169.254.87.242` (MCR2) |
| Hub1 vWAN BGP (MSEE-facing) | 65515 | MSEE IPs: `10.10.0.12`, `10.10.0.13` |
| Hub2 vWAN BGP (MSEE-facing) | 65515 | MSEE IPs: `10.20.0.12`, `10.20.0.13` |
| vWAN inter-hub propagation (AS-path prepend marker, NOT a peering ASN) | 65520 | Appears twice in the AS-path of any route propagated across hubs — visible in the live captures (`03-er1-primary-route-table.json`: `"path": "65515 65520 65520 E"`). Hub-to-hub itself is vWAN-managed forwarding state, not a BGP session. |
| MSEE (Azure) | 12076 | Reflects Azure prefixes back to MCR secondary sessions |
