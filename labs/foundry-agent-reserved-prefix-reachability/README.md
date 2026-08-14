# foundry-agent-reserved-prefix-reachability

> **Status:** Planning only — Phase 0 preflight and Phase 4 deployment approval not yet requested.  
> **Author:** Morpheus · 2026-08-14  
> **Hypothesis state:** Unknown — outcome to be measured, not assumed.

## What This Lab Investigates

Microsoft Foundry Agent Service, when deployed with VNet injection (bring-your-own VNet), explicitly prohibits
`172.30.0.0/16` (and several other ranges) from appearing in the Foundry VNet address space or any **peered** VNet
address space. The published limitation reads:

> *"Ensure that the address spaces of your VNET don't overlap with any existing networks in your Azure environment or
> reserved IP ranges like the following: `169.254.0.0/16`, `172.30.0.0/16`, `172.31.0.0/16`, `192.0.2.0/24`…
> This requirement includes all address spaces you have in your VNET, and if you have more than one, and peered VNETs."*
>
> — [Set up private networking for Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/virtual-networks)

The documentation **does not** extend this prohibition to non-peered remote networks learned through VPN or
ExpressRoute. This lab tests whether an on-premises network that legitimately owns `172.30.0.0/16` and is connected
via a VPN S2S tunnel can be reached by agents running inside the Foundry VNet.

## Headline Hypothesis

> An on-premises network advertising `172.30.0.0/16` via BGP over a Site-to-Site VPN to the Foundry VNet is
> **reachable** by agent tool calls, because the platform's reservation check is scoped to VNet address-space
> declarations and peering relationships — not to dynamically learned route-plane entries.

Outcome is **unknown**. The lab produces binary evidence on this hypothesis.

## Core Topology (summary)

```
[Prompt Agent — Foundry Agent Service]
        |  tool call  |
        v             v
  vnet-foundry      vnet-foundry
  192.168.0.0/16    Private endpoints
  AgentSubnet /24   (Foundry / Search /
  PESubnet /24       CosmosDB / Storage)
  GatewaySubnet /27
        |
   [vpngw-foundry — VpnGw1AZ BGP AS 65010]
        | BGP S2S VPN
   [vpngw-onprem — VpnGw1AZ BGP AS 65020]
        |
  vnet-onprem
  ├── 172.30.0.0/16 → vm-onprem-echo 172.30.100.4
  └── 10.200.100.0/24 → vm-onprem-ctrl 10.200.100.4
```

The on-premises VPN GW advertises the full `172.30.0.0/16` address space and the control
`10.200.100.0/24` address space over BGP.
The Foundry VNet's gateway route propagation injects these into effective routes for the agent subnet.
No peering carries `172.30.x.x` — only the VPN route-plane does.

## Scenarios (overview)

| ID | Name | Outcome |
|----|------|---------|
| S1 | Deployment negative control — local | Expect ARM reject when Foundry VNet address space = `172.30.0.0/16` |
| S2 | Deployment negative control — peered VNet | Expect peering/Foundry validation reject for peered `172.30.0.0/16` |
| S3 | Control — non-reserved remote prefix via VPN | **PASS:** Foundry reached `10.200.100.4`; source observed as `192.168.0.49` in AgentSubnet |
| S4 | **Primary** — reserved prefix via VPN | Agent reaches (or fails to reach) host `172.30.100.4` through learned route `172.30.0.0/16` — **unknown outcome** |
| S5 | DNS plane — on-prem hostname resolution | Agent resolves `echo.onprem.lab` to `172.30.100.4` via forwarded DNS |

## Designs Studied

| Design | Verdict | Rationale |
|--------|---------|-----------|
| D1 — VPN GW in Foundry VNet (this lab) | ✅ Recommended | Cheapest BGP path; no extra hub VNet; GatewaySubnet does not appear in AgentSubnet restriction; single peering concern eliminated |
| D2 — Hub VNet + gateway transit to Foundry VNet | ⚠️ Deferred | Adds hub peering; introduces risk that hub VNet address space triggers a secondary validation; complicates test isolation |
| D3 — ExpressRoute/Megaport | ⚠️ Deferred | Correct for production; adds ~$47+/day ER port cost and Megaport setup time; overkill for this binary hypothesis test |
| D4 — Foundry Managed VNet | ❌ Out of scope | Managed VNet removes the BYO address-space variable; cannot place VPN GW or control route propagation |

## Key Files

| File | Purpose |
|------|---------|
| `manifest.md` | Full Stage-1 lab card — topology, resources, scenarios, cost, approval gate |
| `design.md` | Authoritative packet-path, routing, DNS, and evidence design |
| `deploy/` | Validated Bicep plus deployment and cleanup scripts |
| `portal-foundry-setup.md` | Manual Foundry portal handoff after infrastructure deployment |
| `agent-tools/` | Complete OpenAPI documents for the control and reserved-prefix probes |
| `results.md` | Confirmed results, evidence, lessons learned, and remaining open questions |

## References

- [Set up private networking for Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/virtual-networks)
- [Deep dive into Foundry Agent Service networking](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agents-networking-deep-dive)
