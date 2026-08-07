# Dual-Hub/Hubless-Region-ARS Lab

## Overview
This lab validates Azure Route Server (ARS) + VPN Gateway routing topology. It originally spanned 4
regions: two hub regions (Sweden Central, Switzerland North), one hubless region (Poland Central),
and an on-premises simulation (Norway East). **Poland Central was retired on 2026-08-05** (see
[Poland Central retirement](#-poland-central-retirement--executed-2026-08-05) below) — the live bed
is now **3 regions**: Sweden Central, Switzerland North, and Norway East (on-prem simulation). See
[manifest.md](./manifest.md) for full design details; the S4/S5 Poland-dependent scenarios remain
documented in [validation.md](./validation.md) as historical/non-repeatable in this bed.

## Quick Links
- **Topology & Design**: [manifest.md](./manifest.md)
- **Validation Scenarios & Results**: [validation.md](./validation.md)
- **Lessons Learned**: [lessons-learned.md](./lessons-learned.md)
- **Route-map design user stories**: [route-map-user-stories.md](./route-map-user-stories.md)
- **Route-map experiment catalogue**: [route-map-scenarios.md](./route-map-scenarios.md)
- **Baseline Evidence**: [show-output/baseline-pre-delta3/](./show-output/baseline-pre-delta3/)
- **Two-region hub-to-hub / route-map association program (TP-HH, extracted from US10+US11)**: [`../dual-hub-interconnect-ars-route-policy/`](../dual-hub-interconnect-ars-route-policy/README.md)

## ✅ Poland Central retirement — EXECUTED 2026-08-05

Poland Central resources were deleted on 2026-08-05 per the approved 29-object list in
[cleanup-poland-dry-run.md](./cleanup-poland-dry-run.md) (now updated with the executed result in
its §10). `ars-poland`, `vnet-poland-ars`, `vnet-spoke-c1`, `vnet-spoke-c2`, `vm-c1-ep` + its
dependents, `nsg-ep-poland`, and the 6 Poland-facing peerings on `vnet-hub1`/`vnet-hub2` are **gone**.
Command-by-command evidence: [show-output/cleanup-poland-execution/](./show-output/cleanup-poland-execution/).
Post-delete state: **50 resources** (was 61), 3 regions (`swedencentral`, `switzerlandnorth`,
`norwayeast`), 0 in `polandcentral`. All Sweden Central/Switzerland North/Norway East resources and
the shared resource group are unaffected. **S4 (Δ3 Route-Map Preview on Poland ARS)** and **S5
(Prefix-Only Spoke Scale)** in `validation.md` are now permanently non-repeatable in this bed — their
historical results remain recorded, not deleted or rewritten.

## Status — 2026-08-03
**PRE-Δ3 Baseline CAPTURED.** Δ1 (65515 loop-strip) and Δ2 (hub2 AS-path prepend ×2) proven.
- On-prem RIB: hub1 preferred for all set-C prefixes (AS-PATH `65515-65001` < `65515-65002-65002-65002`)
- Poland 0/0: ECMP NVA1+NVA2 (expected; Δ3 will break ECMP → NVA1 preferred)
- Spoke-c2 (10.32.0.0/24, no VM): present in on-prem RIB with dual-hub paths — S5 proven
- One defect captured: hub1-ep↔c1-ep ping fails (ECMP asymmetric return); expected fix by Δ3
- **READY for Δ3 activation** (ARS route-map PUBLIC PREVIEW; ~30 min upgrade + cost surcharge)

## Blog Post
*Placeholder for future publication. Will cover multi-hub ARS-based routing, BGP policy application via Δ1–Δ3 policies, fault injection methodology, and route-map preview feature validation.*

## Designs Studied
This lab builds on:
- [Azure Route Server documentation](https://learn.microsoft.com/en-us/azure/route-server/)
- [VPN Gateway BGP configuration](https://learn.microsoft.com/en-us/azure/vpn-gateway/bgp-howto)
- [Multi-hop eBGP peering patterns](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-network-peering-overview)
- [Route maps public preview](https://learn.microsoft.com/en-us/azure/route-server/) *(feature under evaluation in S4)*

See manifest.md "Designs studied" section for architecture references.

## Screenshots & Evidence
Planned captures (best-effort, collected during execution):
- Portal BGP session state (3 ARS, 3 VPN GWs)
- ARS learned routes CLI output (before/during/after faults)
- VPN Gateway connection state panels
- BIRD route advertisement summary (NVA1, NVA2)
- Endpoint NIC effective routes (verification of routing convergence)
- Route-map preview activation (S4 feature validation)
- Convergence timelines (graphs: S2 fault injection, S3 recovery)

## Sanitization
- Subscription IDs removed (use <rg> placeholders in commands)
- VPN Gateway PSKs redacted (use <CORRECT_PSK> in validation.md)
- Resource names genericized (ars-hub1, vpngw-onprem, etc.)

## Prerequisites & Assumptions
- Azure subscription with Phase-4 approval for cost escalation (→–72/day)
- Azure CLI 2.0+ configured with appropriate authentication
- SSH access to NVA VMs for BIRD management
- Resource group containing all hub, spoke, and on-prem resources

## Next Steps
1. Review [manifest.md](./manifest.md) for topology, BGP policy details, and resource inventory
2. Follow [validation.md](./validation.md) for step-by-step scenario execution (S1–S5)
3. Collect evidence per scenario; store in vidence/ subdirectory
4. Compare actual results against pass criteria documented in validation.md
