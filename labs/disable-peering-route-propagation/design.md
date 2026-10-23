# Design: Disable Peering Route Propagation (`disablePeeringRoute`) in Hub-and-Spoke Topologies with 3 Hybrid Connections

**Lab:** `disable-peering-route-propagation`
**Date:** 2026-10-23
**Region:** `swedencentral` (Azure) + Frankfurt FR5 (Megaport MCR)
**Feature under test:** `Microsoft.Network/routeTables.properties.disablePeeringRoute` (`AllowDisablePeeringRoutes` preview)

---

## 1. Problem Statement & Question

In large Azure hub-and-spoke networks with a centralized Network Virtual Appliance (NVA) or Azure Firewall in the hub and multiple hybrid connectivity paths (Site-to-Site VPN, SD-WAN NVAs, and ExpressRoute), administrators often want to force traffic entering the hub from on-premises through the central hub firewall NVA using a single **summarized User-Defined Route (UDR)** (such as `10.0.0.0/8 -> VirtualAppliance 10.0.1.4`) instead of maintaining a `/16` or `/24` UDR per peered spoke.

However, Azure selects routes based on **Longest Prefix Match (LPM)** before considering route origin (`User` vs `Default`). Every peered spoke VNet injects a system-generated `VNetPeering` route (e.g., `10.1.0.0/16`, `10.2.0.0/16`, ..., `10.10.0.0/16`) into the hub subnets (including `GatewaySubnet` and any SD-WAN appliance subnet). Because `10.x.0.0/16` is more specific than the summarized `10.0.0.0/8` UDR, traffic from the hub VPN Gateway, ExpressRoute Gateway, or SD-WAN hub appliance to a spoke takes the `VNetPeering` system route and **bypasses the central hub NVA**.

Historically, the only workaround on `GatewaySubnet` (or hub subnets) was to configure an explicit `/16` (or `/24`) UDR for **every single peered spoke**, consuming the 400-route UDR limit and creating operational toil every time a spoke is added or removed.

The new public preview capability **Disable peering route propagation** (`--disable-peering-route All` on a Route Table, gated by `Microsoft.Network/AllowDisablePeeringRoutes`) suppresses system-generated IPv4 and IPv6 `VNetPeering` routes on subnets associated with the route table while keeping the VNet peering active.

---

## 2. Topology & Address Plan

```text
+------------------------------------+  +------------------------------------+  +------------------------------------+
| Hybrid 1: S2S VPN On-Prem          |  | Hybrid 2: SD-WAN On-Prem           |  | Hybrid 3: ExpressRoute On-Prem     |
| vnet-onprem (172.16.0.0/16)        |  | vnet-onprem-sdwan (172.17.0.0/16)  |  | Megaport MCR (Frankfurt FR5)       |
| vm-onprem (172.16.1.4)             |  | vm-onprem-sdwan (172.17.1.4)       |  | jomore-copilot-mcr-disable-peering |
| StrongSwan IKEv2 + FRR ASN 65010   |  | StrongSwan XFRM + BIRD ASN 65020   |  | ASN 65030 | Advertises 172.18.0.0/16|
+-----------------+------------------+  +-----------------+------------------+  +-----------------+------------------+
                  | S2S IPsec (vti0)                      | IPsec (xfrm0)                         | Primary + Secondary VXCs
                  | + eBGP                                | + eBGP (169.254.20.0/30)              | er-circuit-hub (50 Mbps)
                  v                                       v                                       v
+--------------------------------------------------------------------------------------------------------------------+
| Hub VNet: vnet-hub (10.0.0.0/16)                                                                                   |
|   GatewaySubnet (10.0.0.0/24)  - assoc: rt-gw (UDR: 10.0.0.0/8 -> 10.0.1.4)                                        |
|     vpngw-hub (VpnGw1AZ, BGP ASN 65515, BGP IP 10.0.0.254)                                                         |
|     ergw-hub  (Standard ExpressRoute Gateway, connected to er-circuit-hub via conn-hub-er)                         |
|   snet-nva (10.0.1.0/24)       - assoc: rt-nva (UDR: 172.17.0.0/16 -> 10.0.2.4, default peering routes active)     |
|     vm-hub-nva (10.0.1.4)      - Ubuntu 22.04, IP forwarding enabled, central firewall NVA                         |
|   snet-hub-probe (10.0.2.0/24) - assoc: rt-gw (UDR: 10.0.0.0/8 -> 10.0.1.4)                                        |
|     vm-hub-probe (10.0.2.4, PIP) - Hub SD-WAN NVA (StrongSwan XFRM + BIRD ASN 65002) and rt-gw route observer      |
+--------------------------------------------------------------------------------------------------------------------+
       |             |             |            ...            |
   Peering 1     Peering 2     Peering 3                   Peering 10
  (UseRemoteGw) (UseRemoteGw) (UseRemoteGw)               (UseRemoteGw)
       |             |             |                           |
+--------------+ +--------------+ +--------------+       +---------------+
| vnet-spoke1  | | vnet-spoke2  | | vnet-spoke3  |  ...  | vnet-spoke10  |
| 10.1.0.0/16  | | 10.2.0.0/16  | | 10.3.0.0/16  |       | 10.10.0.0/16  |
| snet-workload| | snet-workload| | snet-workload|       | snet-workload |
| 10.1.1.0/24  | | 10.2.1.0/24  | | 10.3.1.0/24  |       | 10.10.1.0/24  |
| vm-spoke1    | | (no VM)      | | (no VM)      |       | (no VM)       |
| (10.1.1.4)   | +--------------+ +--------------+       +---------------+
| assoc:       |
|  rt-spoke1   |
+--------------+
```

### Resource & SKU Inventory

| Resource | Name | Details / SKU | Region |
|---|---|---|---|
| Resource Group | `rg-disable-peering-routes-lab` | Tags: `lab=true`, `created_by=copilot-lab` | `swedencentral` |
| Hub VNet | `vnet-hub` | `10.0.0.0/16` (`GatewaySubnet` `10.0.0.0/24`, `snet-nva` `10.0.1.0/24`, `snet-hub-probe` `10.0.2.0/24`) | `swedencentral` |
| 10 Spoke VNets | `vnet-spoke1` .. `vnet-spoke10` | `10.1.0.0/16` .. `10.10.0.0/16` (`snet-workload` `10.x.1.0/24`), peered with `vnet-hub` (`AllowGatewayTransit` on hub, `UseRemoteGateways` on spokes, `AllowForwardedTraffic` on both) | `swedencentral` |
| On-Prem S2S VPN VNet | `vnet-onprem` | `172.16.0.0/16` (`snet-onprem` `172.16.1.0/24`) | `swedencentral` |
| On-Prem SD-WAN VNet | `vnet-onprem-sdwan` | `172.17.0.0/16` (`snet-onprem-sdwan` `172.17.1.0/24`) | `swedencentral` |
| Hub VPN Gateway | `vpngw-hub` | `VpnGw1AZ`, RouteBased, BGP enabled (`ASN 65515`), Standard PIP | `swedencentral` |
| Hub ExpressRoute Gateway | `ergw-hub` | `Standard` ExpressRoute Gateway in `GatewaySubnet`, Standard PIP | `swedencentral` |
| ExpressRoute Circuit | `er-circuit-hub` | 50 Mbps, Standard, MeteredData, Megaport, Frankfurt, private peering (`169.254.80.216/30` pri, `169.254.80.220/30` sec, VLAN `1115`) | `swedencentral` |
| Megaport MCR + VXCs | `jomore-copilot-mcr-disable-peering` | 1000 Mbps MCR2 (`ASN 65030`, Equinix Frankfurt FR5) + primary/secondary VXCs advertising `172.18.0.0/16` | Frankfurt |
| Local Network Gateway | `lng-onprem` | Peer PIP = `pip-vm-onprem`, BGP ASN `65010`, BGP peer IP `172.16.1.4` | `swedencentral` |
| S2S VPN Connection | `conn-hub-onprem` | IPsec IKEv2, BGP enabled | `swedencentral` |
| ER Gateway Connection | `conn-hub-er` | Links `ergw-hub` to `er-circuit-hub` | `swedencentral` |
| On-Prem S2S CPE VM | `vm-onprem` | `Standard_B2ts_v2`, Ubuntu 22.04, `172.16.1.4`, StrongSwan (`vti0`) + FRR BGP (`ASN 65010`) | `swedencentral` |
| Hub SD-WAN & Probe VM | `vm-hub-probe` | `Standard_B2ts_v2`, Ubuntu 22.04, `10.0.2.4`, PIP `pip-vm-hub-probe`, IP forwarding enabled, StrongSwan (`xfrm0`) + BIRD BGP (`ASN 65002`) | `swedencentral` |
| On-Prem SD-WAN CPE VM | `vm-onprem-sdwan` | `Standard_B2ts_v2`, Ubuntu 22.04, `172.17.1.4`, PIP `pip-vm-onprem-sdwan`, IP forwarding enabled, StrongSwan (`xfrm0`) + BIRD BGP (`ASN 65020`) | `swedencentral` |
| Central Hub Firewall NVA | `vm-hub-nva` | `Standard_B2ts_v2`, Ubuntu 22.04, `10.0.1.4`, IP forwarding enabled (NIC + sysctl), no NAT for RFC1918 | `swedencentral` |
| Spoke 1 Test VM | `vm-spoke1` | `Standard_B2ts_v2`, Ubuntu 22.04, `10.1.1.4` | `swedencentral` |
| Gateway & SD-WAN Route Table | `rt-gw` | Associated with `GatewaySubnet` and `snet-hub-probe`, summary route `to-spokes-summary` (`10.0.0.0/8 -> VirtualAppliance 10.0.1.4`), BGP propagation enabled | `swedencentral` |
| Central NVA Route Table | `rt-nva` | Associated with `snet-nva`, route `to-onprem-sdwan` (`172.17.0.0/16 -> VirtualAppliance 10.0.2.4`), BGP propagation enabled | `swedencentral` |
| Spoke 1 Route Table | `rt-spoke1` | Associated with `vnet-spoke1/snet-workload`, routes `10.0.0.0/8`, `172.16.0.0/16`, `172.17.0.0/16`, `172.18.0.0/16 -> VirtualAppliance 10.0.1.4`, BGP propagation disabled (`disableBgpRoutePropagation=true`) | `swedencentral` |

---

## 3. Designs & Scenarios Studied

### Scenario S1 & S4: Default Peering Route Propagation (`disablePeeringRoute = None`) with Summarized `10.0.0.0/8` UDR Across 3 Hybrid Connections
- **Configuration:**
  - `rt-gw` on `GatewaySubnet` (and `snet-hub-probe`) has `disablePeeringRoute = None` and a single summarized UDR `to-spokes-summary` (`10.0.0.0/8 -> VirtualAppliance 10.0.1.4`).
  - `rt-spoke1` on `vnet-spoke1/snet-workload` has `172.16.0.0/16`, `172.17.0.0/16`, `172.18.0.0/16`, and `10.0.0.0/8 -> VirtualAppliance 10.0.1.4` (`disableBgpRoutePropagation = true`).
  - `rt-nva` on `vnet-hub/snet-nva` has `172.17.0.0/16 -> VirtualAppliance 10.0.2.4` so `vm-hub-nva` forwards SD-WAN return traffic to `vm-hub-probe`, while `172.16.0.0/16` (VPN) and `172.18.0.0/16` (ExpressRoute) are learned dynamically via `VirtualNetworkGateway` BGP propagation.
- **Hypothesis:**
  - In `rt-gw`, the 10 system-generated `VNetPeering` routes (`10.1.0.0/16` .. `10.10.0.0/16`) remain `Active`. Because `/16` is more specific than `10.0.0.0/8`, `GatewaySubnet` (`vpngw-hub` and `ergw-hub`) and `snet-hub-probe` (`vm-hub-probe` SD-WAN NVA) route inbound packets to `10.1.1.4` **directly** to `vm-spoke1`, bypassing `vm-hub-nva` (`10.0.1.4`).
  - Conversely, `vm-spoke1` routes return traffic (`10.1.1.4 -> 172.16.1.4` and `10.1.1.4 -> 172.17.1.4`) through `vm-hub-nva` (`10.0.1.4`). This creates **asymmetric routing** across all hybrid paths.
- **Decisive Evidence:**
  - `az network nic show-effective-route-table` (`show-output/s3-nic-vm-hub-probe-routes.txt`) showing all 10 `10.x.0.0/16` `VNetPeering` routes `Active` alongside `10.0.0.0/8`, `172.16.0.0/16`, and `172.18.0.0/16`.
  - `iptables -L FORWARD -v -n` on `vm-hub-nva` (`show-output/s3-nva-asymmetric-counters.txt`) showing `0` forward packets (`172.16.0.0/16 -> 10.1.0.0/16` and `172.17.0.0/16 -> 10.1.0.0/16`) and `8` return packets each (`10.1.0.0/16 -> 172.16.0.0/16` and `10.1.0.0/16 -> 172.17.0.0/16`).

### Scenario S2: Enable Peering Route Suppression (`disablePeeringRoute = All`) vs. Explicit `/16` UDRs on `rt-gw`
- **Configuration:**
  - Attempt `az network route-table update -g rg-disable-peering-routes-lab -n rt-gw --disable-peering-route All`.
  - Validate the symmetric forwarding behavior by overriding the 10 `/16` routes on `rt-gw`, then clear the 10 `/16` routes per user instruction so `rt-gw` retains only `10.0.0.0/8 -> 10.0.1.4` and the 10 `VNetPeering` system routes remain `Active`.
- **Decisive Evidence:**
  - `show-output/s2-feature-registration-status.json` and `show-output/s2-disable-peering-route-error.txt` confirming `approvalType: ApprovalRequired`.
  - `show-output/s2-workaround-nic-vm-hub-probe-routes.txt` and `show-output/s2-workaround-nva-stateful-counters.txt` confirming symmetric `8/8` forward and return packets when the 10 `VNetPeering` routes are invalidated.

### Scenario S3: Negative / Limitation Test: `disablePeeringRoute = All` on Spoke Route Table (`rt-spoke1`) with Cross-VNet NVA Next Hop
- **Configuration & Evidence:**
  - `show-output/s3-nic-vm-spoke1-routes.txt` proves that `vm-spoke1` (`10.1.1.4`) resolves its `VirtualAppliance` next-hop IP `10.0.1.4` (`vm-hub-nva`) via the `Default` `10.0.0.0/16 -> VNetPeering` system route. Suppressing peering routes on `rt-spoke1` would remove the underlay route to `10.0.1.4`.
