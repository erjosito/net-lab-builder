# sap-rise-scoped-peering-fwaas — Phase 3.1 Manifest (Stage 2)

**Owner:** Morpheus · **Status:** Design complete, stopped at Phase 4 gate. Fan-out (Trinity/Niobe/Oracle) running in parallel off the locked lab card.
**Lab card (Stage 1):** `.squad/decisions/inbox/morpheus-sap-rise-lab-scope.md`
**Do not deploy without explicit gate approval.**

## 0. Gate discipline

Design artifact only — no IaC, no `az network ... create/update/delete`, no Megaport writes. Tank waits for Jose's go. Subscription resolved at runtime (`az account show`), never hardcoded.

## 1. Summary

One region (`swedencentral`), one hub, one SAP RISE spoke, one ER path via one Megaport MCR+VXC, one simulated on-prem CE. Two scenarios test widening a spoke's advertised address space from "peered subnet only" to "full supernet" — via Route Server/BGP redistribution (S1), then via the `summarizedGatewayPrefixes` gateway property (S2) — while all cross-VNet traffic is forced through a subnet-scoped NVA pair using GA subnet-level peering.

## 2. Designs studied

| Design | Status | Description | Evidence |
|---|---|---|---|
| Subnet-level peering (NVA↔NVA only) | ✅ Recommended | GA (Mar 2025) peering scoped to named subnets both sides (`--peer-complete-vnet false`), forcing cross-VNet traffic through the two NVA subnets. | Peering JSON confirming subnet scoping; flow logs showing only NVA-subnet transit; a non-peered-subnet packet dropped (inert forward-route), proving NSGs matter as defense-in-depth. |
| Full VNet peering (contrast anti-pattern) | ⚠️ Not recommended | Whole-VNet peering, documented as a one-time contrast screenshot only — not deployed as a persistent resource. | Side-by-side peering config vs. the scoped design. |
| S1: ARS + NVA eBGP supernet redistribution | ✅ Recommended | Hub NVA (ASN 65001) peers eBGP with ARS (65515, fixed) and redistributes the spoke's full `10.60.0.0/16` toward the ER Gateway. | ARS learned/advertised routes; ER Gateway effective routes; CE-side BGP table showing the supernet, not just the peered `/27`/`/24`. |
| S2: `summarizedGatewayPrefixes` override | ✅ Recommended, with caveat | Gateway connection property forces the ER Gateway to advertise the supernet — control-plane only. | Before/after advertised-routes; CE BGP table; **and** a data-plane probe into supernet space outside the peered subnet, expected to still fail without S1 — this asymmetry is the teaching point. |
| ER Global Reach / dual-circuit HA | 📚 Teaching-only (out of scope) | Mentioned as the natural production follow-up. | None deployed. |

## 3. Resource inventory (~30 items, one RG, `swedencentral`, tags `lab=true`/`created_by=copilot-lab`/`ephemeral=true`/`run_id=<id>`)

**Networking:** RG · Hub VNet `vnet-hub` `10.40.0.0/16` (`GatewaySubnet` `.0/27`, `RouteServerSubnet` `.32/27`, `snet-hub-nva` `10.40.1.0/27`) · Spoke VNet `vnet-sap-rise` `10.60.0.0/16` (`snet-spoke-nva` `.0/27`, `snet-workload` `10.60.1.0/24`) · Subnet-level peering pair (NVA subnets only — **requires subscription allowlisting, verify at deploy, don't assume**) · Azure Route Server, Standard SKU, ASN 65515 · ER virtual network gateway `ErGw1AZ` (zone-redundant) + static public IP · ER circuit (Megaport provider, Standard, MeteredData, 50 Mbps, private peering) + peering config · ER Gateway connection (toggles `summarizedGatewayPrefixes` for S2) · UDR on `snet-workload` only → spoke NVA IP · 3x NSG (hub-nva subnet, spoke-nva subnet, workload subnet).

**Compute:** Hub NVA VM (BIRD/FRR, ASN 65001) · Spoke NVA VM (ASN 65002, dormant BGP) · Workload probe VM · Simulated CE VM/NVA (ASN 65000, advertises `172.40.100.0/24`) — all `Standard_B2als_v2`, Ubuntu 22.04 LTS Gen2, Standard SSD OS disk, no public IP · Azure Bastion (or a single jump-box public IP if Trinity prefers) for operator/Niobe access.

**Megaport:** MCR (1000 Mbps floor, 1-month `contractTerm`, no hourly billing) · Azure VXC (50 Mbps, private peering, nested under MCR).

## 4. Deploy sequence (long pole first)

| Step | Resource(s) | Est. time | Depends on |
|---|---|---|---|
| 1 | RG, both VNets + 5 subnets, NSGs (unattached) | <1 min | — |
| 2 | Megaport MCR request | 5-10 min | — (parallel to 1) |
| 3 | ER circuit (Megaport provider) | 5-15 min | 1, 2 |
| 4 | **ER Gateway `ErGw1AZ` + public IP — long pole** | 20-45 min | 1 |
| 5 | Azure Route Server | 10-20 min (parallel to 4) | 1 |
| 6 | Azure VXC (nested under MCR) | 5-15 min | 2, 3 |
| 7 | ER circuit private peering (Azure side) | 2-5 min | 3, 6 |
| 8 | ER Gateway connection | 2-5 min | 4, 7 |
| 9 | 4x Linux VMs + NICs/disks | 2-5 min each, parallel | 1 |
| 10 | Bastion / jump-box | <1-10 min | 1 |
| 11 | Subnet-level peering — **STOP and escalate if subscription not allowlisted, don't fall back to full-VNet peering silently** | <1 min | 1, 9 |
| 12 | UDR on `snet-workload` | <1 min | 9 |
| 13 | eBGP: hub NVA↔ARS, CE↔MCR | <1 min config + adjacency time | 5, 6, 9 |
| 14 | Attach NSGs | <1 min | 1 |

**Total wall-clock: ~45-70 min**, dominated by step 4 in parallel with steps 2-3-6-7-8 (~20-40 min) and step 5 (10-20 min); VM/peering/NSG steps don't extend the critical path.

## 5. Cleanup sequence (reverse order + ER gotchas)

1. Tear down eBGP sessions. 2. Delete subnet-level peering (both sides, before either VNet). 3. Delete NSGs/UDR. 4. Delete 4x VMs+NICs+disks, Bastion. 5. Delete ER Gateway connection (**must precede circuit de-peer**). 6. Delete Azure-side circuit peering (**circuit must be de-peered before circuit deletion**). 7. Delete ER Gateway + public IP (itself a 10-20 min op). 8. Delete Route Server. 9. Delete Azure VXC **before** the circuit, or Megaport can leave an orphaned billed VXC. 10. Delete ER circuit. 11. Delete MCR (Megaport refuses while a VXC is attached — confirm step 9 first). 12. Delete both VNets. 13. Delete RG (catch-all).

**Order that avoids "resource in use" failures:** de-peer → connection delete → gateway delete → circuit delete → VXC delete → MCR delete. Megaport has no hourly billing, so a delayed cleanup there costs a full extra month, not a few dollars — don't treat it as low-urgency.

## 6. Cost table (24h, `swedencentral` retail)

| Resource | Detail | $/day |
|---|---|---:|
| Networking (VNets/subnets/NSG/UDR/peering) | n/a | $0.00 |
| ER Gateway `ErGw1AZ` | zone-redundant, ~$0.36/hr | ~$8.64 |
| Gateway public IP | Standard static | ~$0.15 |
| ER circuit | Standard/MeteredData, 50 Mbps | ~$1.83 |
| Azure Route Server | Standard SKU, ~$0.45/hr | ~$10.80 |
| 4x Linux VMs | `Standard_B2als_v2`, ~$0.024/hr ea | ~$2.30 |
| 4x OS disks | Standard SSD | ~$0.12 |
| Azure Bastion | Basic, ~$0.19/hr | ~$4.56 |
| Megaport MCR | 1000 Mbps floor, prorated | ~$3.20-$3.50 |
| Megaport VXC | 50 Mbps, prorated | ~$0.20-$0.50 |
| **Azure-only total** | | **~$28.4/day** |
| **Azure + Megaport prorated** | | **~$31.8-$32.5/day** |

**Correction to Stage 1's ~$12-18/day one-liner:** that under-counted Route Server (~$10.80/day, the largest non-Megaport line) and Bastion (~$4.56/day). Corrected: **~$28.4/day Azure burn**, plus a **one-time ~$101-$120 Megaport monthly commitment billed at order time regardless of lab duration** — flag this to Jose as a separate one-time item, not a day-rate. Both remain well under the $50/day guardrail. Trim option: drop Bastion for a jump-box public IP + NSG-scoped SSH (saves ~$4.56/day); Route Server has no cheaper tier and is mandatory for S1's mechanism.

## 7. Region + SKU

Probe swedencentral for `Standard_B2als_v2` before deploy (`az vm list-skus --location swedencentral --resource-type virtualMachines --query "[?starts_with(name,'Standard_B') && contains(name,'_v2')].{name:name,zones:locationInfo[0].zones,restrictionType:restrictions[0].type,blockedZones:restrictions[0].restrictionInfo.zones}" -o table`) — no known prior restriction in this repo's labs, treat as unverified until Tank confirms. Fallback SKU `Standard_B2s_v2`; fallback region `northeurope` (re-verify ER/ARS/Megaport availability there if used). VMs deployed non-zonal; only the ER Gateway needs zone redundancy (a SKU property, not a VM zone pin).

## 8. Scenario assertions

**S1 pass** requires ALL: (a) ER Gateway advertised/effective routes show full `10.60.0.0/16`, not just the peered `/27`/`/24`; (b) CE-side BGP table (MCR routes or CE VM) receives `10.60.0.0/16`; (c) a data-plane probe from CE into supernet space outside the peered subnets succeeds, with NSG flow logs/packet capture confirming transit through both NVA subnets. **Fail:** supernet never reaches CE, or only the peered prefix advertises despite redistribution being configured (flag as lab defect, not a finding).

**S2 pass** requires ALL: (a) baseline capture — pre-`summarizedGatewayPrefixes`, gateway advertises only the peered subnet; (b) post-set — gateway advertised routes and CE BGP table both show the supernet, **with S1's redistribution disabled** so mechanisms aren't conflated; (c) data-plane probe into supernet space outside the peered subnet is actually run and its outcome (expected: still fails without S1) is recorded as evidence, not assumed. **Fail:** advertisement doesn't change post-set (escalate as a CLI/API support-gap, see Risks), or the data-plane probe is skipped.

## 9. Risks

1. **BGP convergence timing** — adjacencies can take minutes; capture must retry/wait, not single-snapshot.
2. **Subnet-level peering is allowlist-gated** — GA but subscription must be Microsoft-allowlisted; verify before deploy, escalate to Jose rather than silently substituting full-VNet peering (would invalidate the "no traffic bypasses the firewalls" premise).
3. **Megaport provisioning flakiness** — real provider workflow, not pure ARM; budget slack beyond estimates, have a fallback peering location ready.
4. **`summarizedGatewayPrefixes` CLI/API support gaps** — newer, narrow property; not all `az` CLI versions or ARM schema versions expose it uniformly. Verify CLI version before deploy; have a raw REST fallback ready.
5. **Inert forward-route gap on subnet peering** — non-peered subnets get a dead route to the peered subnet (expected, not a bug). NSGs are mandatory defense-in-depth; verify attachment before calling any scenario demonstrated, or probe traffic could take an unintended path and produce a false positive.
6. **Megaport monthly vs. Azure hourly billing mismatch** — a short lab still incurs the full ~$101-$120 one-time commitment; call this out separately at the gate so teardown timing doesn't surprise Jose.

## 10. Approval gate (Phase 4 — single confirm-and-go)

- **Resources:** ~30 items — 2 VNets (5 subnets), 1 subnet-level peering pair, 1 Route Server, 1 ER Gateway (`ErGw1AZ`) + circuit + connection, 1 Megaport MCR + VXC, 4 Linux VMs, 1 Bastion/jump path, 3 NSGs, 1 UDR.
- **Region:** `swedencentral` (SKU probe pending, no known blocker).
- **Time:** ~45-70 min to full deploy (ER Gateway 20-45 min is the long pole, parallel with Route Server and the Megaport/circuit chain).
- **Cost:** ~$28.4/day Azure (corrected from Stage 1's ~$12-18/day) + a one-time ~$101-$120 Megaport monthly commitment. Both under the $50/day guardrail; Megaport commitment flagged separately.

**Waiting for Jose's explicit "yes/go/deploy" before Tank touches anything.**
