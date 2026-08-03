# Dual-Hub/Hubless-Region-ARS Lab

## Overview
This lab validates Azure Route Server (ARS) + VPN Gateway routing topology across 4 regions: two hub regions (Sweden Central, Switzerland North), one hubless region (Poland Central), and an on-premises simulation (Norway East). See [manifest.md](./manifest.md) for full design details.

## Quick Links
- **Topology & Design**: [manifest.md](./manifest.md)
- **Validation Scenarios**: [validation.md](./validation.md)

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
