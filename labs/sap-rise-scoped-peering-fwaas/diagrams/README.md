# Diagrams: SAP RISE Scoped Peering FWaaS Lab

## Overview

This directory contains the visual reference for the SAP RISE scoped subnet-peering lab. All diagrams use **planned values** from the Stage 1 lab card (Morpheus) and will be re-labeled with live values from show-output once deployment is complete.

## Diagram Catalogue

### 01-topology.mmd
**Topology Overview**
- Hub VNet (10.40.0.0/16) and Spoke VNet (10.60.0.0/16) in Azure swedencentral
- **Key visual:** Subnet-level peering connects ONLY snet-hub-nva ↔ snet-spoke-nva (not full VNet peering)
- GatewaySubnet, RouteServerSubnet (ARS, ASN 65515), ER Gateway, MSEE
- Megaport MCR + VXC, simulated on-prem CE (172.40.100.0/24, ASN 65000)
- Three VMs: hub NVA (65001), spoke NVA (65002), workload probe

### 02-bgp-control-plane.mmd
**Control Plane: Two Scenarios**
- **S1 (NVA-driven):** Hub NVA (65001) → ARS (65515) → ER Gateway → MSEE → MCR → CE (65000)
  - Route origin: 10.60.0.0/16 redistributed by hub NVA into eBGP
- **S2 (Advertised Gateway Prefixes):** Spoke VNet `summarizedGatewayPrefixes` property forces ER Gateway to advertise the full /16 supernet
  - No NVA/ARS involvement; pure gateway aggregate config

### 03-route-propagation.mmd
**Sequence Diagram: Route Journey**
- **S1 scenario:** Trace 10.60.0.0/16 from hub NVA through ARS, ER GW, MSEE, MCR to CE receiver
- **S2 scenario:** Trace the same prefix via advertised-gateway-prefixes mechanism
- **Caveat:** ⚠️ S2 fixes BGP control-plane advertisement, but end-to-end data-plane reachability to 10.60.1.0/24 (workload) may require UDR on the spoke workload subnet — this is flagged as the primary teaching point and must be verified during Execute phase

### 04-cleanup-chain.mmd
**Cleanup Dependency Order**
Ordered teardown (9 steps):
1. Disable/delete ER Connection
2. Remove subnet-scoped peering (snet-hub-nva ↔ snet-spoke-nva)
3. Delete VXC (Megaport)
4. Delete MCR
5. Delete ER Gateway
6. Delete Route Server
7. Delete VMs
8. Delete VNets
9. Delete Resource Group

---

## Embedding in Labs README

These diagrams are ready to embed in `labs/sap-rise-scoped-peering-fwaas/README.md` under sections:
- **Topology** → Mermaid fence with `01-topology.mmd` source
- **Control Plane** → Mermaid fence with `02-bgp-control-plane.mmd` source
- **Route Propagation** → Mermaid fence with `03-route-propagation.mmd` source
- **Cleanup Order** → Mermaid fence with `04-cleanup-chain.mmd` source

Use GitHub's native Mermaid rendering (` ```mermaid ` fences). No PNG or `.drawio` needed for this lab.

---

## Labels and Values

All labels use **planned values** from the lab card (Stage 1):
- IP ranges, subnet names, ASNs per scope
- VM names, service names (ARS, MSEE, etc.)

**After deployment (Execute phase):**
Niobe's `show-output/` will provide live captured values (actual IP assignments, peer sessions, routes). Oracle will re-label diagrams with real data at that time.

---

## Validation Status

**Pre-render validation:** Mermaid syntax checked manually against flowchart and sequenceDiagram grammar.
**Full render:** Pending access to diagram rendering tool (not available in this environment).
Commit these sources; rendering will be validated before final README embedding.

---

## Open Questions for Trinity (Networking Design)

**S2 Data-Plane Question (from lab card):**
The `summarizedGatewayPrefixes` configuration is confirmed to fix the control-plane (BGP advertisement of the full /16). However, it is **not yet confirmed** whether it alone restores end-to-end data-plane reachability for addresses in the wider supernet (10.60.1.0/24 workload subnet) that are outside the physically peered NVA subnet (10.60.0.0/27). This will be a primary lesson from Scenario 2 testing.

See diagram caveat in `03-route-propagation.mmd` (note near CE Router in S2 scenario).

---

*Oracle, Documentation & Diagrams*
*Generated: 2026-09-29*
