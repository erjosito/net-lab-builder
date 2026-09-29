# SAP RISE Scoped Peering + FWaaS

> 📝 **Blog post:** _pending publication_ (Kid)

---

## Designs studied

This lab investigates two control-plane and data-plane strategies for bridging a SAP RISE spoke VNet to on-premises over ExpressRoute when only a narrow NVA subnet is peered to the hub, not the full spoke address space.

### Design 1: ARS + Hub NVA eBGP Redistribution — _pending evidence_

**Status:** ✅ Recommended (baseline)

**Verdict:** _To be determined post-deploy. Expected: ARS + BIRD redistribution ensures ER Gateway learns the full spoke supernet via eBGP, enabling end-to-end connectivity from on-prem through hub NVA to spoke workloads. This is the "control-plane mastery" approach — explicit BGP routing solves subnet-peering scope limits._

**What it is:**
Azure Route Server in the hub accepts eBGP routes from a Linux NVA (BIRD, ASN 65001) running in the peered hub NVA subnet. The NVA is configured to redistribute the locally-learned spoke VNet prefix (10.60.0.0/16) into BGP toward ARS (ASN 65515). ARS then advertises this supernet toward the ER Gateway. The ER Gateway sends the supernet outbound to the on-prem site via the Megaport MCR and ER circuit. Spoke-side, the workload subnet has an explicit UDR routing default traffic through the spoke NVA, completing the return path.

**Evidence:**
- `validation.md` § Scenario 1 assertions (S1.L1–S1.D4) — route captures, BGP session status, data-plane connectivity checks.
- `show-output/s1-*.{txt,json}` — three-layer route collection (ER GW, ER circuit/Megaport, ARS, BIRD, NIC effective routes, NSG rules, ping/traceroute, Network Watcher).
- `screenshots/` — ER Gateway BGP peer status, Network Watcher topology (pending).

**Why this verdict:** _Pending post-deploy evidence. The mechanism is well-established (ARS + eBGP redistribution is the standard approach for multi-hub or multi-spoke scenarios in Azure). The test outcome will confirm that BIRD successfully injects the supernet and that spoke workloads receive packets from on-prem via the NVA._

**Use this design when:**
- You need explicit, granular control over what prefixes are advertised from spoke networks.
- You are comfortable running and monitoring active BGP routing on NVA VMs (BIRD/Quagga/FRR).
- You have multiple spoke VNets or dynamic prefix requirements that favor a centralized ARS + NVA architecture.

**Avoid this design when:**
- You want minimal operational complexity (ARS + NVA add runtime dependencies).
- ER circuit provisioning is on a tight timeline; BGP convergence adds 1–3 min to readiness.

---

### Design 2: Advertised/Summarized Gateway Prefixes (Supernet Advertisement) — _pending evidence_

**Status:** ⚠️ Not recommended (open question on data-plane completeness)

**Verdict:** _To be determined post-deploy. The design is under investigation to answer whether the `summarizedGatewayPrefixes` feature on the ER Gateway or spoke VNet can advertise the full spoke supernet to on-prem even when only the NVA subnet is peered. Control-plane evidence is expected (ER Gateway advertises /16 instead of /27). Data-plane evidence (workload VM connectivity) is the open question — S2 may prove to be control-plane-only, requiring a companion UDR to complete the path._

**What it is:**
Enable the `summarizedGatewayPrefixes` feature at the ER Gateway or spoke VNet level. This forces the gateway to advertise the full spoke VNet supernet (10.60.0.0/16) toward the ER circuit, independent of the subnet-peering scope restriction (which normally limits ER to advertising only 10.60.0.0/27, the peered NVA subnet). On-prem CE receives the /16 in BGP. The hypothesis: this simplifies control-plane (no NVA BGP routing needed) while data-plane connectivity is restored implicitly.

**Evidence:**
- `validation.md` § Scenario 2 assertions (S2.L1–S2.D4) — route captures (ER GW, Megaport, ARS state), data-plane connectivity checks.
- `show-output/s2-*.{txt,json}` — side-by-side comparison to S1 captures; the critical assertions are S2.L1.2 (ER GW advertised routes, must show /16 not /27) and S2.D1 (ping/traceroute from on-prem to workload, must succeed if S2 alone fixes the path).
- `screenshots/` — ER Gateway advertised-routes blade (pending).

**Why this verdict:** _Pending post-deploy data-plane evidence._ The Morpheus decision document (`.squad/decisions/inbox/morpheus-sap-rise-lab-scope.md`) explicitly flags S2's data-plane behavior as an open question: `summarizedGatewayPrefixes` is confirmed to fix control-plane (ER advertises the /16), but it is NOT yet confirmed whether it alone restores end-to-end data-plane to non-peered subnets (workload VM reachable from on-prem). If the workload VM requires an explicit UDR even with S2 enabled, then S2 is control-plane-only and S1 remains the full solution.

**Use this design when:**
- **NOT recommended at this time.** Await post-deploy evidence from this lab. If post-deploy shows that S2 is data-plane-complete (workload connectivity succeeds without UDR), S2 could be used to simplify hub-side routing (no NVA BGP redistribution required). If S2 is control-plane-only, it may serve as a teaching example of control-plane vs. data-plane decoupling but not as a standalone solution.

**Avoid this design when:**
- You need guaranteed end-to-end spoke-to-on-prem connectivity without additional UDR or route injection. Until this lab confirms data-plane completeness, S2 should not be used in production in place of S1.

---

## Lab topology and scope

**Regions:** swedencentral (single region, all resources co-located)

**Key components:**
- Hub VNet: `vnet-hub` (10.40.0.0/16) with GatewaySubnet, RouteServerSubnet, and NVA subnet snet-hub-nva (10.40.1.0/27).
- Spoke VNet: `vnet-sap-rise` (10.60.0.0/16) with peered NVA subnet snet-spoke-nva (10.60.0.0/27) and workload subnet snet-workload (10.60.1.0/24).
- **Subnet-level peering** between snet-hub-nva and snet-spoke-nva only (not full VNet peering). This restricts ER advertisement scope naturally in the baseline (S1 compensates via NVA eBGP; S2 tests forcing supernet advertisement).
- VMs: 3× Standard_B2als_v2 Linux (hub NVA, spoke NVA, workload probe).
- Megaport: single MCR with one VXC for ER circuit.
- ER Gateway: ErGw1AZ (single zone, swedencentral).
- Azure Route Server: ASN 65515 (co-located with ER Gateway).
- Simulated on-prem: 172.40.100.0/24 (test route/VPN endpoint).

**Connectivity design:**
- S1: Explicit BGP redistribution (hub NVA + ARS).
- S2: ER Gateway supernet advertisement feature.

---

## Validation summary

See `validation.md` for the full three-layer route collection checklist, NSG/effective-route assertions, and data-plane connectivity tests for both S1 and S2.

**Key open question (S2 data-plane):** _Pending evidence._

---

## Deployment & evidence artifacts

Once Tank deploys and Niobe captures evidence:

- **Route captures:** `show-output/s1-*/` and `show-output/s2-*/` — raw Azure CLI and Megaport API output.
- **Connectivity tests:** `show-output/s1-1[4-9]*/` and `show-output/s2-1[0-5]*/` — ping, traceroute, Network Watcher results.
- **Portal screenshots:** `screenshots/` — effective routes, BGP peer status, Network Watcher topology (best-effort).
- **Lessons learned:** `lessons-learned.md` — operational insights, surprises, timing observations.

---

## References & links

- Morpheus scope: `.squad/decisions/inbox/morpheus-sap-rise-lab-scope.md`
- Trinity design (expected soon): `.squad/agents/trinity/...` (pending)
- Niobe validation checklist: `validation.md` (this repo)
- Megaport API: [Megaport Portal](https://portal.megaport.com/) (credentials handled per security charter)
- Azure ExpressRoute: [ExpressRoute documentation](https://learn.microsoft.com/en-us/azure/expressroute/)
- Azure Route Server: [ARS documentation](https://learn.microsoft.com/en-us/azure/route-server/)

---

**Status:** Pre-deploy skeleton completed. Awaiting Trinity's design.md and Tank's IaC deployment.

**Next steps:**
1. Trinity finalizes design.md (exact commands, resource naming, BGP timers, resiliency patches if any).
2. Niobe reconciles validation.md against design.md (cross-check subnet names, ASNs, expected route counts).
3. Tank deploys IaC.
4. Niobe captures live evidence, completes validation.md pass/fail, writes lessons-learned.md.
5. Morpheus coordinates teardown with Tank.

