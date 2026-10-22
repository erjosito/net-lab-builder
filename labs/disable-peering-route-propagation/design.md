# Design: Disable Peering Route Propagation (`disablePeeringRoute`) in Hub-and-Spoke Topologies

**Lab:** `disable-peering-route-propagation`
**Date:** 2026-10-22
**Region:** `swedencentral`
**Feature under test:** `Microsoft.Network/routeTables.properties.disablePeeringRoute` (`AllowDisablePeeringRoutes` preview)

---

## 1. Problem Statement & Question

In large Azure hub-and-spoke networks with a centralized Network Virtual Appliance (NVA) or Azure Firewall in the hub, administrators often want to force traffic entering the hub (for example, from an on-premises VPN/ExpressRoute gateway or from a spoke) through the hub NVA using a single **summarized User-Defined Route (UDR)** (such as `10.0.0.0/8 -> VirtualAppliance 10.0.1.4`) instead of maintaining a `/16` or `/24` UDR per peered spoke.

However, Azure selects routes based on **Longest Prefix Match (LPM)** before considering route origin (`User` vs `Default`). Every peered spoke VNet injects a system-generated `VNetPeering` route (e.g., `10.1.0.0/16`, `10.2.0.0/16`, ..., `10.10.0.0/16`) into the hub subnets (including `GatewaySubnet`). Because `10.x.0.0/16` is more specific than the summarized `10.0.0.0/8` UDR, traffic from the hub VPN Gateway (or any hub subnet) to a spoke takes the `VNetPeering` system route and **bypasses the hub NVA**.

Historically, the only workaround on `GatewaySubnet` (or hub subnets) was to configure an explicit `/16` (or `/24`) UDR for **every single peered spoke**, consuming the 400-route UDR limit and creating operational toil every time a spoke is added or removed.

The new public preview capability **Disable peering route propagation** (`--disable-peering-route All` on a Route Table, gated by `Microsoft.Network/AllowDisablePeeringRoutes`) suppresses system-generated IPv4 and IPv6 `VNetPeering` routes on subnets associated with the route table while keeping the VNet peering active.

### Key Questions Verified in This Lab

1. **GatewaySubnet scaling & NVA inspection (`rt-gw`):** With 10 spoke VNets peered to the hub and a single summarized `10.0.0.0/8 -> 10.0.1.4 (hub NVA)` UDR on `GatewaySubnet`:
   - When `disablePeeringRoute = None` (default), do the 10 `/16` `VNetPeering` routes override `10.0.0.0/8` via LPM and cause on-prem → spoke traffic to bypass the hub NVA (leading to asymmetric routing when the spoke returns traffic via the NVA)?
   - When `disablePeeringRoute = All`, are all 10 `VNetPeering` routes suppressed on the gateway/probe NIC, allowing the single `10.0.0.0/8` UDR to win and steer on-prem ↔ spoke traffic symmetrically through the hub NVA?
2. **Spoke-to-spoke / Spoke-to-hub preview limitation (`rt-spoke1`):** The public preview documentation states:
   > *"During public preview, the Azure Firewall or NVA next hop must be in the same virtual network as the source workload's network interface. A next hop in a peered virtual network isn't supported."*
   - What actually happens in the control plane (`show-effective-route-table`) and data plane (`ping` / `mtr` / `tcpdump`) if a spoke route table (`rt-spoke1`) has `0.0.0.0/0 -> 10.0.1.4` (NVA in the peered hub VNet) and sets `disablePeeringRoute = All`? Does suppressing the hub `VNetPeering` route invalidate next-hop resolution to the peered hub NVA?

---

## 2. Topology & Address Plan

```text
+-----------------------------------------------------------------------------------+
| On-Premises Simulation VNet: vnet-onprem (172.16.0.0/16, BGP ASN 65010)           |
|   snet-onprem (172.16.1.0/24)                                                     |
|     vm-onprem (172.16.1.4, PIP) — Ubuntu 22.04 + StrongSwan IKEv2 + FRR/BIRD BGP  |
+-----------------------------------------------------------------------------------+
                                         |
                               IPsec S2S + BGP (IKEv2)
                                         |
+-----------------------------------------------------------------------------------+
| Hub VNet: vnet-hub (10.0.0.0/16)                                                  |
|   GatewaySubnet (10.0.0.0/24) — assoc: rt-gw                                      |
|     vpngw-hub (VpnGw1, BGP ASN 65515, BGP IP 10.0.0.254)                          |
|   snet-nva (10.0.1.0/24) — assoc: rt-nva (none / default peering routes active)   |
|     vm-hub-nva (10.0.1.4) — Ubuntu 22.04, IP forwarding enabled                   |
|   snet-hub-probe (10.0.2.0/24) — assoc: rt-gw (mirrors GatewaySubnet effective    |
|     route table for direct NIC inspection alongside packet path verification)     |
|     nic-hub-probe (10.0.2.4)                                                      |
+-----------------------------------------------------------------------------------+
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
| On-Prem VNet | `vnet-onprem` | `172.16.0.0/16` (`snet-onprem` `172.16.1.0/24`) | `swedencentral` |
| Hub VPN Gateway | `vpngw-hub` | `VpnGw1` (Gen2), RouteBased, BGP enabled (`ASN 65515`), 1 Standard PIP | `swedencentral` |
| Local Network Gateway | `lng-onprem` | Peer PIP = `pip-onprem-vm`, BGP ASN `65010`, BGP peer IP `172.16.1.4` | `swedencentral` |
| S2S VPN Connection | `conn-hub-onprem` | IPsec IKEv2, BGP enabled | `swedencentral` |
| On-Prem CPE VM | `vm-onprem` | `Standard_B2ts_v2`, Ubuntu 22.04, `172.16.1.4`, StrongSwan + FRR BGP, SSH on port 2222 | `swedencentral` |
| Hub NVA VM | `vm-hub-nva` | `Standard_B2ts_v2`, Ubuntu 22.04, `10.0.1.4`, IP forwarding enabled (NIC + sysctl), no NAT for RFC1918 | `swedencentral` |
| Spoke 1 Test VM | `vm-spoke1` | `Standard_B2ts_v2`, Ubuntu 22.04, `10.1.1.4` | `swedencentral` |
| Gateway Route Table | `rt-gw` | Associated with `GatewaySubnet` (and `snet-hub-probe`), route `10.0.0.0/8 -> VirtualAppliance 10.0.1.4`, BGP propagation enabled | `swedencentral` |
| Spoke 1 Route Table | `rt-spoke1` | Associated with `vnet-spoke1/snet-workload`, route `172.16.0.0/16 -> VirtualAppliance 10.0.1.4` and `10.0.0.0/8 -> VirtualAppliance 10.0.1.4`, BGP propagation disabled (`disableBgpRoutePropagation=true`) | `swedencentral` |

---

## 3. Designs & Scenarios Studied

### Scenario S1 — Baseline: Default Peering Route Propagation (`disablePeeringRoute = None`) with Summarized UDR
- **Configuration:**
  - `rt-gw` on `GatewaySubnet` (and `snet-hub-probe`) has `disablePeeringRoute = None` and a single summarized UDR `10.0.0.0/8 -> VirtualAppliance 10.0.1.4`.
  - `rt-spoke1` on `vnet-spoke1/snet-workload` has `172.16.0.0/16 -> VirtualAppliance 10.0.1.4` (`disableBgpRoutePropagation = true`, `disablePeeringRoute = None`).
- **Hypothesis:**
  - In `rt-gw`, the 10 system-generated `VNetPeering` routes (`10.1.0.0/16` .. `10.10.0.0/16`) remain `Active`. Because `/16` is more specific than `10.0.0.0/8`, `GatewaySubnet` routes `172.16.1.4 -> 10.1.1.4` **directly** to `vm-spoke1`, bypassing `vm-hub-nva` (`10.0.1.4`).
  - Conversely, `vm-spoke1` routes return traffic (`10.1.1.4 -> 172.16.1.4`) to `vm-hub-nva` (`10.0.1.4`). This creates **asymmetric routing** (and if `vm-hub-nva` acts as a stateful firewall dropping mid-stream SYN-ACKs, traffic fails; with stateless forwarding, `tcpdump` on `vm-hub-nva` sees only 1 direction: `10.1.1.4 -> 172.16.1.4`).
- **Decisive Evidence:**
  - `az network nic show-effective-route-table` showing all 10 `10.x.0.0/16` `VNetPeering` routes `Active` alongside `10.0.0.0/8`.
  - `tcpdump` on `vm-hub-nva` during `ping` / TCP probe from `vm-onprem` (`172.16.1.4`) to `vm-spoke1` (`10.1.1.4`) showing asymmetric path (forward request bypasses `vm-hub-nva`; only echo reply transits `vm-hub-nva`), plus stateful conntrack drop test (`iptables -A FORWARD -m conntrack --ctstate INVALID -j DROP`) proving stateful firewall breakage.

### Scenario S2 — Enable Peering Route Suppression (`disablePeeringRoute = All`) on `rt-gw`
- **Configuration:**
  - Update `rt-gw`: `az network route-table update -g rg-disable-peering-routes-lab -n rt-gw --disable-peering-route All`.
  - Keep the single summarized UDR `10.0.0.0/8 -> VirtualAppliance 10.0.1.4` on `rt-gw`. No `/16` per-spoke UDRs added.
- **Hypothesis:**
  - All 10 system-generated `VNetPeering` routes (`10.1.0.0/16` .. `10.10.0.0/16`) are suppressed on subnets associated with `rt-gw`.
  - The summarized `10.0.0.0/8 -> 10.0.1.4` UDR is now the longest match for all 10 spokes!
  - Meanwhile, `vm-hub-nva` (in `snet-nva`, which does **not** have `disablePeeringRoute = All`) retains all 10 `VNetPeering` routes and forwards inspected packets directly to `vnet-spoke1` (`10.1.1.4`).
  - Both directions of traffic (`172.16.1.4 -> 10.1.1.4` and `10.1.1.4 -> 172.16.1.4`) now transit `vm-hub-nva` symmetrically, and stateful inspection (`--ctstate INVALID -j DROP`) succeeds 5/5!
- **Decisive Evidence:**
  - `az network nic show-effective-route-table` showing all 10 `VNetPeering` routes suppressed/removed on `rt-gw`-associated NIC, while `vm-hub-nva` NIC still has all 10 `VNetPeering` routes `Active`.
  - `mtr` and `tcpdump` on `vm-hub-nva` showing symmetric bidirectional traversal (`172.16.1.4 -> 10.0.1.4 -> 10.1.1.4` and `10.1.1.4 -> 10.0.1.4 -> 172.16.1.4`), and 0% loss with strict stateful firewall rules enabled on `vm-hub-nva`.

### Scenario S3 — Negative / Limitation Test: `disablePeeringRoute = All` on Spoke Route Table (`rt-spoke1`) with Cross-VNet NVA Next Hop
- **Configuration:**
  - Verify the documented preview limitation: *"During public preview, the Azure Firewall or NVA next hop must be in the same virtual network as the source workload's network interface. A next hop in a peered virtual network isn't supported."*
  - Update `rt-spoke1` (associated with `vnet-spoke1/snet-workload`, where `vm-spoke1` uses `10.0.1.4` in peered `vnet-hub` as its VirtualAppliance next hop) to `--disable-peering-route All`.
- **Hypothesis:**
  - Suppressing peering routes on `rt-spoke1` removes the `10.0.0.0/16` `VNetPeering` system route that Azure SDN needs to resolve the cross-VNet next-hop IP `10.0.1.4` (or blackholes traffic destined to `10.0.1.4`).
- **Decisive Evidence:**
  - `az network nic show-effective-route-table` on `vm-spoke1` NIC and live `ping` / `mtr` from `vm-spoke1` before and after setting `--disable-peering-route All` on `rt-spoke1`, followed by immediate restore of `rt-spoke1` to `--disable-peering-route None` and `rt-gw` to the desired validated state.
