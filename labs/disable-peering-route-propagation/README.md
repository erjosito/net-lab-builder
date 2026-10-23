# Disable Peering Route Propagation (`disablePeeringRoute`): Hub-and-Spoke with 3 Hybrid Connections (S2S VPN, SD-WAN, ExpressRoute) and NVA

## Status Summary

| Item | Value |
|------|-------|
| **Verdict** | **BLOCKED (Feature Gate) / PASS (3-Hybrid Routing Architecture & Workaround Verified)** |
| **Feature Under Test** | Disable peering route propagation (`az network route-table update --disable-peering-route All` / `Microsoft.Network/AllowDisablePeeringRoutes`) |
| **Region** | `swedencentral` (Azure) + Frankfurt FR5 (Megaport MCR) |
| **Resource Group** | `rg-disable-peering-routes-lab` (**Active / Retained per user instruction**) |
| **Last Verified State** | Live environment up with **3 active hybrid connections** into `vnet-hub` (`10.0.0.0/16`): (1) **S2S VPN** (`vpngw-hub` <-> `vm-onprem` `172.16.0.0/16`, ASN `65010`), (2) **SD-WAN** (`vm-hub-probe` StrongSwan+BIRD `AS65002` <-> `vm-onprem-sdwan` `172.17.0.0/16`, ASN `65020`), and (3) **ExpressRoute** (`ergw-hub` + `er-circuit-hub` <-> Megaport MCR `jomore-copilot-mcr-disable-peering` advertising `172.18.0.0/16`, ASN `65030`). The 10 specific `/16` spoke UDRs have been cleared from `rt-gw`, leaving only the summary `10.0.0.0/8 -> 10.0.1.4` route so all 10 more-specific `VNetPeering` system routes (`10.1.0.0/16`..`10.10.0.0/16`) appear `Active` again. |

| Scenario | Description | Verdict | Evidence |
|----------|-------------|---------|----------|
| **S1: Baseline (`disablePeeringRoute = None`)** | `rt-gw` has only a summarized `10.0.0.0/8 -> 10.0.1.4` UDR; 10 spoke `/16` `VNetPeering` routes override `/8` via LPM and bypass the hub NVA on the forward path. | **PASS** (reproduced asymmetric bypass & stateful NVA failure) | [`s1-nic-vm-hub-probe-routes.txt`](show-output/s1-nic-vm-hub-probe-routes.txt), [`s1-nva-stateless-counters.txt`](show-output/s1-nva-stateless-counters.txt), [`s1-nva-stateful-counters.txt`](show-output/s1-nva-stateful-counters.txt), [`s1-onprem-stateful-test.txt`](show-output/s1-onprem-stateful-test.txt) |
| **S2: Feature Gate & `/16` UDR Comparison (`rt-gw`)** | Attempted `az network route-table update --disable-peering-route All` on `rt-gw`; verified feature registration gate (`ApprovalRequired`), then validated the 10-route `/16` UDR override restoring symmetric NVA traversal. | **BLOCKED** (on PG feature approval) / **PASS** (symmetric NVA path verified) | [`s2-feature-registration-status.json`](show-output/s2-feature-registration-status.json), [`s2-disable-peering-route-error.txt`](show-output/s2-disable-peering-route-error.txt), [`s2-workaround-nic-vm-hub-probe-routes.txt`](show-output/s2-workaround-nic-vm-hub-probe-routes.txt), [`s2-workaround-nva-stateful-counters.txt`](show-output/s2-workaround-nva-stateful-counters.txt) |
| **S3: Cross-VNet Next-Hop Constraint (`rt-spoke1`)** | Verified why `disablePeeringRoute = All` cannot be enabled on a spoke subnet route table whose UDR next hop (`10.0.1.4`) lives in the peered hub VNet (`10.0.0.0/16`). | **BLOCKED** (by S2 feature gate; routing dependency confirmed via `nic-vm-spoke1` effective routes) | [`s1-nic-vm-spoke1-routes.txt`](show-output/s1-nic-vm-spoke1-routes.txt) |
| **S4: Expanded 3-Hybrid-Connection Topology (S2S VPN + SD-WAN + ExpressRoute) with Summary `10.0.0.0/8` Restored** | Repurposed `vm-hub-probe` as an SD-WAN NVA (StrongSwan + BIRD) peered with `vm-onprem-sdwan` (`172.17.0.0/16`), deployed `ergw-hub`, `er-circuit-hub`, and Megaport MCR (`172.18.0.0/16`), cleared the 10 `/16` spoke routes on `rt-gw` to leave only `10.0.0.0/8 -> 10.0.1.4`, and verified all 10 `VNetPeering` routes appear `Active` and cause asymmetric bypass across all hybrid paths. | **PASS** (all 3 hybrid BGP paths + active `VNetPeering` routes + asymmetric counters verified) | [`s3-nic-vm-hub-probe-routes.txt`](show-output/s3-nic-vm-hub-probe-routes.txt), [`s3-ergw-learned-routes.txt`](show-output/s3-ergw-learned-routes.txt), [`s3-er-circuit-routes-primary.txt`](show-output/s3-er-circuit-routes-primary.txt), [`s3-megaport-mcr-vxc-status.json`](show-output/s3-megaport-mcr-vxc-status.json), [`s3-sdwan-hub-probe-status.txt`](show-output/s3-sdwan-hub-probe-status.txt), [`s3-sdwan-onprem-status.txt`](show-output/s3-sdwan-onprem-status.txt), [`s3-s2s-vpn-to-spoke1-test.txt`](show-output/s3-s2s-vpn-to-spoke1-test.txt), [`s3-sdwan-to-spoke1-test.txt`](show-output/s3-sdwan-to-spoke1-test.txt), [`s3-nva-asymmetric-counters.txt`](show-output/s3-nva-asymmetric-counters.txt) |

## Designs studied

| Design / Scenario | Status | Verdict | Rationale (`design.md`) | Evidence |
|-------------------|--------|---------|-------------------------|----------|
| **D1 (Scenarios S1 & S4): Summarized `10.0.0.0/8` UDR on `GatewaySubnet` and SD-WAN NVA subnet (`rt-gw`) with default peering propagation (`disablePeeringRoute = None`)** | Not Recommended | **PASS** (Negative baseline verified across S2S VPN, SD-WAN, and ExpressRoute: 10 `/16` `VNetPeering` routes remain `Active` and bypass the hub NVA on the forward path) | [Section 3: Scenarios S1 & S4](design.md#3-designs--scenarios-studied) | [`s3-nic-vm-hub-probe-routes.txt`](show-output/s3-nic-vm-hub-probe-routes.txt), [`s3-nva-asymmetric-counters.txt`](show-output/s3-nva-asymmetric-counters.txt), [`s1-nva-stateful-counters.txt`](show-output/s1-nva-stateful-counters.txt) |
| **D2a (Scenario S2, Preview Feature): Summarized `10.0.0.0/8` UDR on `rt-gw` with `disablePeeringRoute = All`** | Recommended (when feature flag is approved) | **BLOCKED** (`AllowDisablePeeringRoutes` requires manual PG approval: `approvalType: ApprovalRequired`) | [Section 3: Scenario S2](design.md#3-designs--scenarios-studied) | [`s2-feature-registration-status.json`](show-output/s2-feature-registration-status.json), [`s2-disable-peering-route-error.txt`](show-output/s2-disable-peering-route-error.txt) |
| **D2b (Scenario S2, Production Workaround): Explicit per-spoke `/16` UDRs (`10.1.0.0/16`..`10.10.0.0/16 -> 10.0.1.4`) on `rt-gw`** | Recommended (when `AllowDisablePeeringRoutes` is not yet approved and spoke count $\le 400$) | **PASS** (Invalidates all 10 `VNetPeering` routes; symmetric stateful NVA inspection verified) | [Section 3: Scenario S2](design.md#3-designs--scenarios-studied) | [`s2-workaround-nic-vm-hub-probe-routes.txt`](show-output/s2-workaround-nic-vm-hub-probe-routes.txt), [`s2-workaround-onprem-stateful-test.txt`](show-output/s2-workaround-onprem-stateful-test.txt), [`s2-workaround-nva-stateful-counters.txt`](show-output/s2-workaround-nva-stateful-counters.txt) |
| **D3 (Scenario S3): Enabling `disablePeeringRoute = All` on Spoke Route Tables (`rt-spoke1`) with Cross-VNet Hub NVA Next Hop** | Not Recommended (Unsupported) | **BLOCKED** (Feature gate; architectural next-hop dependency verified on `nic-vm-spoke1`) | [Section 3: Scenario S3](design.md#3-designs--scenarios-studied) | [`s3-nic-vm-spoke1-routes.txt`](show-output/s3-nic-vm-spoke1-routes.txt) |

---

## 1. Objective & Problem Statement

In an Azure hub-and-spoke topology with a central Network Virtual Appliance (NVA) in the hub VNet (`10.0.0.0/16`) and multiple hybrid entry points (Site-to-Site VPN Gateway `vpngw-hub`, ExpressRoute Gateway `ergw-hub` in `GatewaySubnet`, and an SD-WAN appliance `vm-hub-probe` in `snet-hub-probe`), administrators often want to route all ingress traffic from all on-premises locations (`172.16.0.0/16`, `172.17.0.0/16`, `172.18.0.0/16`) to all spokes (`10.1.0.0/16` .. `10.10.0.0/16`) through the central firewall NVA (`10.0.1.4`) using a single summarized UDR on `rt-gw`:

- `10.0.0.0/8 -> VirtualAppliance 10.0.1.4`

However, peering the hub VNet with 10 spoke VNets automatically injects 10 system routes (`Source: Default`, `NextHopType: VNetPeering`) into every hub subnet, one for each spoke's `/16` prefix (`10.1.0.0/16` .. `10.10.0.0/16`). Because `/16` is more specific than `/8` (Longest Prefix Match), the VPN Gateway, ExpressRoute Gateway, and SD-WAN hub appliance all route inbound on-premises-to-spoke packets **directly** to the spoke over VNet peering, bypassing the central firewall NVA (`vm-hub-nva`). Meanwhile, outbound spoke-to-on-premises return traffic follows the spoke's UDRs (`172.16.0.0/16`, `172.17.0.0/16`, `172.18.0.0/16 -> 10.0.1.4`) through `vm-hub-nva`, causing **asymmetric routing** and immediate connection drops on any stateful firewall.

Azure's **Disable peering route propagation** feature (`disablePeeringRoute: All` on a route table, gated by `Microsoft.Network/AllowDisablePeeringRoutes`) solves this by suppressing `VNetPeering` routes on the associated subnets (`GatewaySubnet` and `snet-hub-probe`), allowing the single `10.0.0.0/8` summary UDR to match all spoke prefixes without maintaining $N$ individual `/16` UDRs.

---

## 2. Lab Topology (3 Hybrid Connections: S2S VPN, SD-WAN, and ExpressRoute)

```
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
|                                                                                                                    |
|   GatewaySubnet (10.0.0.0/24)  <--- Route Table: rt-gw (UDR: 10.0.0.0/8 -> 10.0.1.4)                               |
|     [vpngw-hub: VpnGw1AZ | ASN 65515 | BGP IP 10.0.0.254]                                                          |
|     [ergw-hub:  Standard ExpressRoute Gateway | Connected to er-circuit-hub]                                       |
|                                                                                                                    |
|   snet-hub-probe (10.0.2.0/24) <--- Route Table: rt-gw (UDR: 10.0.0.0/8 -> 10.0.1.4)                               |
|     [vm-hub-probe: 10.0.2.4 | Hub SD-WAN NVA: StrongSwan XFRM + BIRD ASN 65002 + Route Observer]                   |
|                                                                                                                    |
|   snet-nva (10.0.1.0/24)       <--- Route Table: rt-nva (172.17.0.0/16 -> 10.0.2.4)                                |
|     [vm-hub-nva: 10.0.1.4 | Central Hub Firewall NVA: IP Forwarding + iptables conntrack/LOG]                      |
+-----+-------+-------+-------+-------+-------+-------+-------+-------+-------+--------------------------------------+
      |       |       |       |       |       |       |       |       |       |
      | VNet Peerings (AllowGatewayTransit = true / UseRemoteGateways = true) |
      v       v       v       v       v       v       v       v       v       v
  +-------+ +---+   +---+   +---+   +---+   +---+   +---+   +---+   +---+  +----+
  |Spoke 1| |S2 |   |S3 |   |S4 |   |S5 |   |S6 |   |S7 |   |S8 |   |S9 |  |S10 |
  |10.1/16| |10.2   |10.3   |10.4   |10.5   |10.6   |10.7   |10.8   |10.9  |10.10
  +---+---+ +---+   +---+   +---+   +---+   +---+   +---+   +---+   +---+  +----+
      |
      +-- snet-workload (10.1.1.0/24) <--- Route Table: rt-spoke1 (BGP prop disabled)
            UDRs: 10.0.0.0/8, 172.16.0.0/16, 172.17.0.0/16, 172.18.0.0/16 -> 10.0.1.4
            [vm-spoke1: 10.1.1.4 | Python HTTP server :80]
```

> **Dual role of `vm-hub-probe` (`snet-hub-probe`):** Because `snet-hub-probe` shares the exact same `rt-gw` route table as `GatewaySubnet`, `nic-vm-hub-probe` both (1) serves as the Hub SD-WAN appliance terminating the IPsec + BIRD eBGP tunnel to `vnet-onprem-sdwan` (`172.17.0.0/16`) and (2) allows us to inspect via `az network nic show-effective-route-table` the exact `Default`, `VNetPeering`, `VirtualNetworkGateway`, and `User` routes evaluated on `rt-gw`.

---

## 3. Experimental Results

### 3.1 Three Hybrid Connections into the Hub (S2S VPN, SD-WAN, ExpressRoute)

All three hybrid connections dynamically exchange the hub (`10.0.0.0/16`) and all 10 peered spoke prefixes (`10.1.0.0/16` .. `10.10.0.0/16`) via eBGP:

1. **Hybrid 1: Site-to-Site VPN (`vm-onprem` `172.16.1.4` ASN `65010` <-> `vpngw-hub` ASN `65515`):**
   - `vm-onprem` establishes a route-based IKEv2 IPsec tunnel (`vti0`) to `vpngw-hub` (`10.0.0.254`), advertises `172.16.0.0/16`, and receives all 11 Azure VNet `/16` prefixes (`10.0.0.0/16` .. `10.10.0.0/16`).
2. **Hybrid 2: SD-WAN Appliance (`vm-onprem-sdwan` `172.17.1.4` ASN `65020` <-> `vm-hub-probe` `10.0.2.4` ASN `65002`):**
   - `vm-hub-probe` and `vm-onprem-sdwan` establish an IKEv2 IPsec tunnel over XFRM interface `xfrm0` (`if_id 42`, `169.254.20.1/30` <-> `169.254.20.2/30`) and run BIRD 2.0.8 eBGP (`show-output/s3-sdwan-hub-probe-status.txt`, `show-output/s3-sdwan-onprem-status.txt`):
     ```text
     Name       Proto      Table      State  Since         Info
     sdwan_ebgp BGP        ---        up     07:35:14.468  Established   
       BGP state:          Established
         Neighbor address: 169.254.20.1
         Neighbor AS:      65002
         Local AS:         65020
         Routes:           11 imported, 1 exported, 11 preferred
     ```
   - `vm-onprem-sdwan` installs kernel routes for `10.0.0.0/16` .. `10.10.0.0/16 via 169.254.20.1 dev xfrm0 proto bird`, and `vm-hub-probe` installs `172.17.0.0/16 via 169.254.20.2 dev xfrm0 proto bird`.
3. **Hybrid 3: ExpressRoute + Megaport MCR (`jomore-copilot-mcr-disable-peering` ASN `65030` <-> `er-circuit-hub` / `ergw-hub`):**
   - Megaport MCR (`639f1881-efd0-44a0-b7c9-9c555f292b5e`) connects to `er-circuit-hub` via primary and secondary VXCs (`169.254.80.216/30` and `169.254.80.220/30`), advertising `172.18.0.0/16` into Azure (`show-output/s3-er-circuit-routes-primary.txt`, `show-output/s3-ergw-learned-routes.txt`):
     ```text
     Network            NextHop    Origin    SourcePeer    AsPath       Weight
     -----------------  ---------  --------  ------------  -----------  --------
     10.0.0.0/16                   Network   10.0.0.12                  32768
     10.1.0.0/16                   Network   10.0.0.12                  32768
     ...
     10.10.0.0/16                  Network   10.0.0.12                  32768
     172.16.0.0/16      10.0.0.5   IBgp      10.0.0.5                   32768
     172.18.0.0/16      10.0.0.6   EBgp      10.0.0.6      12076-65030  32779
     172.18.0.0/16      10.0.0.7   EBgp      10.0.0.7      12076-65030  32779
     ```

### 3.2 Scenarios S1 & S4: Summary `10.0.0.0/8` UDR Restored on `rt-gw` (`disablePeeringRoute = None`)

With the 10 specific `/16` spoke routes cleared from `rt-gw` and only the summary route `to-spokes-summary` (`10.0.0.0/8 -> VirtualAppliance 10.0.1.4`) configured, the effective route table on `rt-gw` (`nic-vm-hub-probe`, `show-output/s3-nic-vm-hub-probe-routes.txt`) shows all 10 `Default` `/16` `VNetPeering` routes **Active** alongside the S2S VPN (`172.16.0.0/16`), ExpressRoute (`172.18.0.0/16`), and User summary (`10.0.0.0/8`) routes:

```text
Source                 State    Address Prefix    Next Hop Type          Next Hop IP
---------------------  -------  ----------------  ---------------------  -----------------------
Default                Active   10.0.0.0/16       VnetLocal
Default                Active   10.1.0.0/16       VNetPeering
Default                Active   10.2.0.0/16       VNetPeering
Default                Active   10.3.0.0/16       VNetPeering
Default                Active   10.4.0.0/16       VNetPeering
Default                Active   10.5.0.0/16       VNetPeering
Default                Active   10.6.0.0/16       VNetPeering
Default                Active   10.7.0.0/16       VNetPeering
Default                Active   10.8.0.0/16       VNetPeering
Default                Active   10.9.0.0/16       VNetPeering
Default                Active   10.10.0.0/16      VNetPeering
VirtualNetworkGateway  Active   172.16.0.0/16     VirtualNetworkGateway  20.240.221.177
VirtualNetworkGateway  Active   172.18.0.0/16     VirtualNetworkGateway  10.2.146.34 10.2.146.35
VirtualNetworkGateway  Active   172.18.1.0/30     VirtualNetworkGateway  10.2.146.35
Default                Active   0.0.0.0/0         Internet
...
User                   Active   10.0.0.0/8        VirtualAppliance       10.0.1.4
```

Because `/16` beats `/8` by Longest Prefix Match, **all three hybrid entry points** (`vpngw-hub`, `ergw-hub`, and `vm-hub-probe`) match `Default 10.1.0.0/16 -> VNetPeering` and forward inbound packets directly to `vm-spoke1` (`10.1.1.4`), bypassing the central firewall NVA (`vm-hub-nva` `10.0.1.4`) on the forward path while return traffic from `vm-spoke1` traverses `vm-hub-nva` via `rt-spoke1` (`show-output/s3-nva-asymmetric-counters.txt`):

```text
Chain FORWARD (policy ACCEPT 0 packets, 0 bytes)
 pkts bytes target     prot opt in     out     source               destination         
    0     0 ACCEPT     all  --  *      *       172.17.0.0/16        10.1.0.0/16         
    8   747 ACCEPT     all  --  *      *       10.1.0.0/16          172.17.0.0/16       
    0     0 ACCEPT     all  --  *      *       172.16.0.0/16        10.1.0.0/16         
    8   747 ACCEPT     all  --  *      *       10.1.0.0/16          172.16.0.0/16       
```

When `vm-hub-nva` enforces stateful inspection (`conntrack` dropping `ctstate INVALID`), this asymmetric bypass causes 100% packet loss (`show-output/s1-onprem-stateful-test.txt`, `show-output/s1-nva-stateful-counters.txt`).

### 3.3 Scenario S2: `AllowDisablePeeringRoutes` Feature Gate & `/16` Override Verification

We registered `Microsoft.Network/AllowDisablePeeringRoutes` and inspected its registration resource via `az feature registration show`:

```json
{
  "name": "AllowDisablePeeringRoutes",
  "properties": {
    "approvalType": "ApprovalRequired",
    "description": "Enabling customers to use newly created feature AllowDisablePeeringRoutes in their routes",
    "providerNamespace": "Microsoft.Network",
    "releaseDate": "2025-08-20T22:51:47.519752+00:00",
    "state": "Pending"
  }
}
```

**Key operational finding:** Unlike self-serve preview flags (`approvalType: AutoApproval`), `Microsoft.Network/AllowDisablePeeringRoutes` has `"approvalType": "ApprovalRequired"` and remains `Pending` until manually approved by the Azure Virtual Network product team. Attempting to set `--disable-peering-route All` while the feature is `Pending` returns:

```text
ERROR: (UnauthorizedClientApplication) Unauthorized client application id DisablePeeringRoute is not supported.
Code: UnauthorizedClientApplication
Message: Unauthorized client application id DisablePeeringRoute is not supported.
```

In Scenario S2 (`show-output/s2-workaround-nic-vm-hub-probe-routes.txt`), we proved that overriding the 10 `/16` `VNetPeering` routes on `rt-gw` marks all 10 `VNetPeering` routes `Invalid` and restores 100% symmetric traversal (`8` forward packets, `8` return packets, `0` drops) through `vm-hub-nva`. Per user instruction for Scenario S4, those 10 `/16` routes were subsequently removed so `rt-gw` now holds only the `10.0.0.0/8` summary route with all 10 `VNetPeering` system routes visible as `Active`.

### 3.4 Scenario S3: Spoke Route Table Next-Hop Constraint (`rt-spoke1`)

Examining `nic-vm-spoke1`'s effective routes (`show-output/s3-nic-vm-spoke1-routes.txt`) confirms why `disablePeeringRoute = All` **must not** be enabled on spoke route tables that point to a hub NVA:

```text
Source    State    Address Prefix    Next Hop Type     Next Hop IP
--------  -------  ----------------  ----------------  -------------
Default   Active   10.1.0.0/16       VnetLocal
Default   Active   10.0.0.0/16       VNetPeering
Default   Active   0.0.0.0/0         Internet
...
User      Active   172.16.0.0/16     VirtualAppliance  10.0.1.4
User      Active   10.0.0.0/8        VirtualAppliance  10.0.1.4
User      Active   172.17.0.0/16     VirtualAppliance  10.0.1.4
User      Active   172.18.0.0/16     VirtualAppliance  10.0.1.4
```

On `vm-spoke1`, the UDR next hop `10.0.1.4` (`vm-hub-nva`) is resolved recursively through the `Default` `10.0.0.0/16 -> VNetPeering` route. If `disablePeeringRoute = All` is enabled on `rt-spoke1`, the `10.0.0.0/16 -> VNetPeering` system route is removed, leaving the Azure SDN fabric in `vnet-spoke1` with no underlay path to reach `10.0.1.4`.

---

## 4. Current Environment State & Next Steps

- **Current state:** All resources in `rg-disable-peering-routes-lab` (`swedencentral`) and the Megaport MCR/VXCs (`jomore-copilot-mcr-disable-peering`) are **running and retained** per user instruction.
  - All 3 hybrid connections (S2S VPN `172.16.0.0/16`, SD-WAN `172.17.0.0/16`, and ExpressRoute `172.18.0.0/16`) are established and exchanging routes via BGP.
  - `rt-gw` has been cleared of the 10 specific `/16` spoke routes and holds only the summary route `to-spokes-summary` (`10.0.0.0/8 -> VirtualAppliance 10.0.1.4`), so the 10 more-specific `VNetPeering` system routes (`10.1.0.0/16`..`10.10.0.0/16`) appear `Active`.
- **Once `AllowDisablePeeringRoutes` is approved on the subscription:**
  1. Run `az provider register --namespace Microsoft.Network`.
  2. Run `az network route-table update -g rg-disable-peering-routes-lab -n rt-gw --disable-peering-route All`.
  3. Re-run `az network nic show-effective-route-table -g rg-disable-peering-routes-lab -n nic-vm-hub-probe` to observe all 10 `VNetPeering` routes disappear completely while `10.0.0.0/8 -> 10.0.1.4` steers all 3 hybrid connections (S2S VPN, SD-WAN, and ExpressRoute) symmetrically through `vm-hub-nva`.
- **Cleanup:** Standing by for user approval before deleting the ExpressRoute connection/peering, Megaport VXCs/MCR, and `rg-disable-peering-routes-lab`.
