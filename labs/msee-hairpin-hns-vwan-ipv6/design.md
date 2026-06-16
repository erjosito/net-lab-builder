# Design — `msee-hairpin-hns-vwan-ipv6`

**Date:** 2026-06-15 · **Author:** Trinity · **Status:** Draft — awaiting Jose gate on Path A

---

## 0. TL;DR

Two ER circuits on one ER Direct 10 Gbps port at Stockholm MSEE. Circuit 1 → HnS ER GW
(`ErGw1AZ`); Circuit 2 → vWAN ER GW (1 SU). Three Azure toggles unlock MSEE route reflection
between the circuits. No on-prem router. No firewall. Dual-stack IPv4+IPv6 throughout.
Customer-side BGP on the ER Direct port is **not needed** — Azure GWs supply the BGP endpoints.

---

## 1. Topology

```
  HnS Hub VNet (10.1.0.0/16 · fd00:1::/48)
  ┌────────────────────────────────────────┐
  │  GatewaySubnet 10.1.0.0/27            │
  │    HnS ER GW  (ErGw1AZ)  ─────────── Circuit 1 (VLAN 100/101) ──┐
  │  VmSubnet     10.1.1.0/24             │                           │
  └──────────────────┬─────────────────────┘                          │
      VNet peering   │ allowGatewayTransit=true                     Stockholm MSEE
  ┌──────────────────┴─────────────────────┐                          │  (12076)
  │  HnS Spoke VNet (10.2.0.0/24 · fd00:2::/48)                     │
  │    VmSubnet  vm-hns-spoke              │                           │
  └────────────────────────────────────────┘                          │
                                                                       │
  vWAN Hub  10.3.0.0/23 · fd00:3::/48                                │
  ┌────────────────────────────────────────┐                          │
  │    vWAN ER GW (1 scale unit) ────────── Circuit 2 (VLAN 200/201) ┘
  └──────────────────┬─────────────────────┘
      VNet connection│
  ┌──────────────────┴─────────────────────┐
  │  vWAN Spoke VNet (10.4.0.0/24 · fd00:4::/48)
  │    VmSubnet  vm-vwan-spoke             │
  └────────────────────────────────────────┘
```

### Resource inventory

| Resource | Suggested name | Notes |
|---|---|---|
| Resource Group | `msee-hairpin-rg` | All resources, swedencentral |
| ER Direct port pair | `erdirect-sto-01` | 10 Gbps, Stockholm, Dot1Q |
| ER Circuit 1 | `erc-hns` | On port, Local SKU |
| ER Circuit 2 | `erc-vwan` | On port, Local SKU |
| HnS Hub VNet | `vnet-hub-hns` | swedencentral, dual-stack |
| HnS Spoke VNet | `vnet-spoke-hns` | swedencentral, dual-stack |
| HnS ER GW | `ergw-hns` | ErGw1AZ, in GatewaySubnet |
| HnS GW connection | `cx-hns-erc1` | ergw-hns → erc-hns |
| VNet peering (hub→spoke) | `peer-hub-spoke-hns` | allowGatewayTransit=true |
| VNet peering (spoke→hub) | `peer-spoke-hub-hns` | useRemoteGateways=true |
| vWAN | `vwan-hairpin` | Standard |
| vWAN Hub | `vhub-sto` | swedencentral, /23 |
| vWAN ER GW | `vwan-ergw` | 1 SU, allowNonVirtualWanTraffic=true |
| vWAN ER connection | `cx-vwan-erc2` | vwan-ergw → erc-vwan |
| vWAN Spoke VNet | `vnet-spoke-vwan` | swedencentral, dual-stack |
| vWAN VNet connection | `cx-spoke-vwan` | vnet-spoke-vwan → vhub-sto |
| VM 1 | `vm-hns-spoke` | Standard_B2als_v2, HnS spoke |
| VM 2 | `vm-vwan-spoke` | Standard_B2als_v2, vWAN spoke |
| NSG (HnS spoke) | `nsg-hns-spoke` | Allow ICMP+SSH |
| NSG (vWAN spoke) | `nsg-vwan-spoke` | Allow ICMP+SSH |

---

## 2. Address Plan (dual-stack)

### VNet / Subnet table

| VNet | Subnet | IPv4 prefix | IPv6 prefix | Purpose |
|---|---|---|---|---|
| `vnet-hub-hns` | `GatewaySubnet` | `10.1.0.0/27` | `fd00:1::/64` | HnS ER GW (name is Azure-reserved) |
| `vnet-hub-hns` | `VmSubnet` | `10.1.1.0/24` | `fd00:1:1::/64` | Hub diagnostic VM (optional) |
| `vnet-spoke-hns` | `VmSubnet` | `10.2.0.0/24` | `fd00:2::/64` | Source VM for S1/S2 |
| vWAN hub | *(hub-internal)* | `10.3.0.0/23` | `fd00:3::/48` | vWAN hub address space |
| `vnet-spoke-vwan` | `VmSubnet` | `10.4.0.0/24` | `fd00:4::/64` | Destination VM for S1/S2 |

> **GatewaySubnet sizing:** /27 is the recommended minimum for ER GWs; /28 works but some tooling
> rejects it. Use /27.  
> **vWAN hub sizing:** /23 is the platform minimum. `10.3.0.0/23` per lab card — correct.

### ER peering subnets

| Circuit | Path | IPv4 /30 | IPv6 /126 | Interface IPs |
|---|---|---|---|---|
| Circuit 1 (HnS) | Primary | `172.16.1.0/30` | `fd00:f:1::/126` | Customer .1/::1 · MSEE .2/::2 |
| Circuit 1 (HnS) | Secondary | `172.16.1.4/30` | `fd00:f:1::4/126` | Customer .5/::5 · MSEE .6/::6 |
| Circuit 2 (vWAN) | Primary | `172.16.2.0/30` | `fd00:f:2::/126` | Customer .1/::1 · MSEE .2/::2 |
| Circuit 2 (vWAN) | Secondary | `172.16.2.4/30` | `fd00:f:2::4/126` | Customer .5/::5 · MSEE .6/::6 |

---

## 3. ER Direct Config

| Property | Value | Note |
|---|---|---|
| Port SKU | 10 Gbps | Floor SKU for ER Direct |
| Peering location | `Stockholm` | Maps to swedencentral in Azure |
| Encapsulation | `Dot1Q` | Sufficient for lab; no nested VLAN needed |
| Redundancy | Dual-port pair | Primary + secondary physical path |
| Circuits on port | 2 | Circuit 1 = HnS, Circuit 2 = vWAN |
| Circuit 1 bandwidth | 1 Gbps | Local SKU minimum |
| Circuit 2 bandwidth | 1 Gbps | Local SKU minimum |
| Circuit SKU tier | `Local` | Same-region GWs qualify; saves egress cost |
| Circuit SKU family | `MeteredData` | |
| Provider | None | ER Direct — no third-party provider |

> **ER Direct provisioning sequence:** (1) Provision port pair. (2) No physical cabling needed
> for this lab — no customer CPE. (3) Create circuits referencing the port. (4) Configure private
> peering. (5) Connect circuits to GWs via connection resources.

---

## 4. ER Private Peering Config

REST resource: `Microsoft.Network/expressRouteCircuits/<name>/peerings/AzurePrivatePeering`  
**API version:** `2024-03-01`

| Property | Circuit 1 (erc-hns) | Circuit 2 (erc-vwan) |
|---|---|---|
| `peeringType` | `AzurePrivatePeering` | `AzurePrivatePeering` |
| `peerASN` | `65515` | `65515` |
| `vlanId` (primary) | `100` | `200` |
| `secondaryVlanId` | `101` | `201` |
| `primaryPeerAddressPrefix` | `172.16.1.0/30` | `172.16.2.0/30` |
| `secondaryPeerAddressPrefix` | `172.16.1.4/30` | `172.16.2.4/30` |
| `ipv6PeeringConfig.primaryPeerAddressPrefix` | `fd00:f:1::/126` | `fd00:f:2::/126` |
| `ipv6PeeringConfig.secondaryPeerAddressPrefix` | `fd00:f:1::4/126` | `fd00:f:2::4/126` |
| `ipv6PeeringConfig.state` | `Enabled` | `Enabled` |
| `state` | `Enabled` | `Enabled` |
| `sharedKey` | *(omit — no MD5 for lab)* | *(omit)* |

**IPv6 peering — CLI** (adds IPv6 to existing IPv4 peering):

```bash
az network express-route peering update -g msee-hairpin-rg --circuit-name erc-hns \
  --name AzurePrivatePeering --ip-version ipv6 \
  --primary-peer-subnet fd00:f:1::/126 --secondary-peer-subnet fd00:f:1::4/126

az network express-route peering update -g msee-hairpin-rg --circuit-name erc-vwan \
  --name AzurePrivatePeering --ip-version ipv6 \
  --primary-peer-subnet fd00:f:2::/126 --secondary-peer-subnet fd00:f:2::4/126
```

**Terraform:** `azurerm_express_route_circuit_peering` → `ipv6 { primary_peer_address_prefix = "fd00:f:1::/126"; secondary_peer_address_prefix = "fd00:f:1::4/126"; enabled = true }`

> **IPv6 sequencing:** Add IPv6 address space to VNets + subnets **before** updating circuit
> peering. GW must be dual-stack first.

---

## 5. Gateway Config

### 5.1 HnS ER Gateway — `Microsoft.Network/virtualNetworkGateways`

| Property | Value | Why |
|---|---|---|
| `gatewayType` | `ExpressRoute` | |
| `sku.name` / `sku.tier` | `ErGw1AZ` | Lab SKU; zone-redundant PIPs |
| `vpnType` | `RouteBased` | Required even for ER GW |
| `enableBgp` | `true` | |
| `bgpSettings.asn` | `65515` | Fixed; not configurable for ER GW |
| **`allowVirtualWanTraffic`** | **`true`** | Accepts MSEE-reflected vWAN routes; **default=false; silent-fail if missing** |
| **`allowRemoteVnetTraffic`** | **`true`** | Advertises peered spoke prefixes (10.2.x/fd00:2::) via circuit; **default=false; spoke invisible to MSEE if missing** |
| `gatewayIpConfigurations[*].subnet` | `GatewaySubnet` | Must be named exactly `GatewaySubnet` |
| `gatewayIpConfigurations[*].publicIpAddress.sku` | `Standard` | Required for zone-redundant GW |

> **Dual-stack:** GW inherits dual-stack from GatewaySubnet. Assign `fd00:1::/64` to
> GatewaySubnet before GW creation.

### 5.2 vWAN ER Gateway — `Microsoft.Network/expressRouteGateways`

| Property | Value | Why |
|---|---|---|
| `virtualHub.id` | ref to `vhub-sto` | Hub association |
| `autoScaleConfiguration.bounds.min` | `1` | 1 scale unit for lab |
| `autoScaleConfiguration.bounds.max` | `1` | Pin to 1 SU; avoid auto-scale cost surprise |
| **`allowNonVirtualWanTraffic`** | **`true`** | Accepts routes from non-vWAN circuits (Circuit 1) via MSEE; **default=false; silent-fail if missing** |

> **vWAN ER GW ASN:** Fixed at 65515 — same as HnS GW. Azure's control plane handles same-ASN
> reflection at the MSEE correctly. No BGP loop risk.

> **IPv6 on vWAN hub:** Set `ipv6AddressSpace=fd00:3::/48` on the hub. Spoke VNet connection
> inherits IPv6 from the spoke VNet address space.

---

## 6. BGP Design

### Session table (4 BGP sessions per circuit = 8 total)

| Session | Speaker | MSEE | IPv4 link | IPv6 link |
|---|---|---|---|---|
| C1-v4-Pri | HnS ER GW (65515) | 12076 | 172.16.1.1↔.2 | — |
| C1-v4-Sec | HnS ER GW (65515) | 12076 | 172.16.1.5↔.6 | — |
| C1-v6-Pri | HnS ER GW (65515) | 12076 | — | fd00:f:1::1↔::2 |
| C1-v6-Sec | HnS ER GW (65515) | 12076 | — | fd00:f:1::5↔::6 |
| C2-v4-Pri | vWAN ER GW (65515) | 12076 | 172.16.2.1↔.2 | — |
| C2-v4-Sec | vWAN ER GW (65515) | 12076 | 172.16.2.5↔.6 | — |
| C2-v6-Pri | vWAN ER GW (65515) | 12076 | — | fd00:f:2::1↔::2 |
| C2-v6-Sec | vWAN ER GW (65515) | 12076 | — | fd00:f:2::5↔::6 |

### Expected route exchange (MSEE hairpin)

| Route | Advertised by | Reflected to | Learned by |
|---|---|---|---|
| `10.1.0.0/16` | HnS ER GW (C1) | Circuit 2 | vWAN ER GW |
| `10.2.0.0/24` | HnS ER GW (C1, `allowRemoteVnetTraffic`) | Circuit 2 | vWAN ER GW |
| `fd00:1::/48`, `fd00:2::/64` | HnS ER GW (C1, IPv6) | Circuit 2 | vWAN ER GW |
| `10.3.0.0/23` | vWAN ER GW (C2) | Circuit 1 | HnS ER GW |
| `10.4.0.0/24` | vWAN ER GW (C2, spoke cx) | Circuit 1 | HnS ER GW |
| `fd00:3::/48`, `fd00:4::/64` | vWAN ER GW (C2, IPv6) | Circuit 1 | HnS ER GW |

> Routes carry Microsoft regional community `12076:20xxx` (Sweden Central). MSEE reflects
> routes between circuits only when the three toggles below are set.

---

## 7. Hairpin-Enabling Settings

| Toggle | Resource type | Property | Default | Required value | What breaks if missing |
|---|---|---|---|---|---|
| vWAN routes allowed on HnS GW | `virtualNetworkGateways` | `allowVirtualWanTraffic` | `false` | **`true`** | HnS GW silently drops MSEE-reflected vWAN routes; S1/S2/S3 fail; BGP sessions stay Up — no error |
| Spoke routes advertised by HnS GW | `virtualNetworkGateways` | `allowRemoteVnetTraffic` | `false` | **`true`** | 10.2.0.0/24 and fd00:2::/64 not advertised; vWAN never learns HnS spoke; S1/S2 fail |
| Non-vWAN circuits allowed on vWAN GW | `expressRouteGateways` | `allowNonVirtualWanTraffic` | `false` | **`true`** | vWAN ER GW blocks Circuit 1 routes; HnS spoke routes never reach vWAN spoke; S1/S2 fail |

> S4 (deliberate-break scenario) tests what happens when `allowVirtualWanTraffic` is flipped to
> `false` while the lab is running. Expected: pings fail within ~60 s; BGP sessions remain Up.

---

## 8. NSGs

Minimal. Two NSGs — one per spoke VM subnet. Rules are identical.

### `nsg-hns-spoke` / `nsg-vwan-spoke` (identical rules)

| Priority | Name | Direction | Protocol | Port | Action | Why |
|---|---|---|---|---|---|---|
| 100 | Allow-ICMPv4-In | Inbound | ICMP | * | Allow | S1 ping |
| 110 | Allow-ICMPv6-In | Inbound | Icmpv6 | * | Allow | S2 ping6 |
| 120 | Allow-SSH-In | Inbound | TCP | 22 | Allow | Lab access |
| 65000/65500 | (Azure defaults) | — | — | — | Allow VNet / Deny All | — |

> No Bastion in this lab. VM auth via `default-password` secret from `platform-secrets-1138` KV.
> GSA+KV ACL collision applies — coordinate per history.md before fetching the secret.

---

## 9. Route Propagation (no UDRs)

BGP does all routing. No route tables. No `disableBgpRoutePropagation`.

- **HnS hub ↔ spoke:** VNet peering with `allowGatewayTransit=true` on hub side,
  `useRemoteGateways=true` on spoke side. Spoke's effective routes include ER-learned routes
  from the hub GW.
- **vWAN spoke ↔ hub:** VNet connection. vWAN hub propagates all learned routes (including
  ER-learned) to all connected VNets automatically — no configuration needed.
- **ER route propagation:** Default on both GW types. No route table override needed.

---

## 10. Resiliency Analysis

> **Lab framing:** Single ER Direct port pair + single Stockholm MSEE = SPOF by design. This is
> intentional — the lab isolates the MSEE hairpin mechanism cleanly. **Production reader note:**
> evaluate (a) second ER Direct port at a geographically diverse MSEE location, (b) Global Reach
> as a complementary same-region bypass, (c) VPN GW coexistence for circuit-failure survivability.
> The patch catalogue below describes mitigations; they are **dormant until Jose says "apply Pn."**

### Failure mode table

| # | Component | Failure | Blast radius | Failover time | Operator action |
|---|---|---|---|---|---|
| F1 | ER Direct port pair | Port down (both circuits share one port) | Total: all HnS↔vWAN paths lost (IPv4+IPv6) | None (manual) | MSft support ticket; both circuits recover together |
| F2 | Circuit 1 (erc-hns) | Circuit fails; Circuit 2 intact | HnS GW loses all ER routes; HnS spoke unreachable from vWAN | None | Repair/recreate Circuit 1; reconnect to ergw-hns |
| F3 | Circuit 2 (erc-vwan) | Circuit fails; Circuit 1 intact | vWAN ER GW loses all ER routes; vWAN spoke unreachable from HnS | None | Repair/recreate Circuit 2; reconnect to vWAN GW |
| F4 | HnS ER GW (ergw-hns) | GW platform failure | HnS spoke loses all ER-derived routes; Circuit 1 BGP drops | ~30 min (GW redeploy) | Recreate GW; reconnect cx-hns-erc1; re-set `allowVirtualWanTraffic=true`, `allowRemoteVnetTraffic=true` |
| F5 | vWAN ER GW | GW failure | vWAN spoke loses all ER routes; Circuit 2 BGP drops | ~15 min | Recreate; reconnect cx-vwan-erc2; re-set `allowNonVirtualWanTraffic=true` |
| F6/F7 | IPv4 or IPv6 BGP primary session (either circuit) | Primary session drops | Secondary session takes over; ~30–60 s convergence | ~60 s automatic | None; monitor |
| F8 | Stockholm MSEE | MSEE platform event | Equivalent to F1; both circuits lose BGP | None (MSft-managed) | Support ticket |
| F9 | `allowVirtualWanTraffic` toggled false (S4 test) | HnS GW stops accepting vWAN routes | HnS spoke loses vWAN reach; BGP sessions stay Up | Immediate | Set flag back to `true`; wait ~60 s convergence |
| F10 | `allowNonVirtualWanTraffic` toggled false | vWAN GW blocks non-vWAN routes | vWAN spoke loses HnS reach | Immediate | Set flag back to `true`; wait ~60 s |

### Patch catalogue (dormant)

| Patch | Mitigates | Delta | Cost impact | Residual gap |
|---|---|---|---|---|
| P1 | F1, F2, F3, F8 | Second ER Direct port at diverse MSEE; add circuits on second port; connect second circuits to same GWs | +~$47/day after day 46 (second port is $0 during its own 45-day free-provisioning window) | F4, F5 unmitigated |
| P2 | F4 | Second HnS ER GW in separate AZ; both GWs connected to Circuit 1 | +~$8/day | AZ-level protection only; not circuit-failure protection |
| P3 | F5 | Scale vWAN ER GW to 2 scale units (zone-redundant) | +~$4/day | Same — AZ protection only |

---

## 11. Designs Studied

| | Design | Status | Notes |
|---|---|---|---|
| **A** | ER Direct 10G, 2 circuits on one port, MSEE hairpin | **Primary** | No Megaport; **~$7/6h** during 45-day free port window (~$18/6h after); customer-side BGP not needed |
| **B** | Megaport circuits, MSEE hairpin | Fallback | Same mechanism; ~$10/6h; conflicts with Jose's "no Megaport" preference |
| **C** | IPsec VPN S2S, no MSEE | Anti-pattern / 2nd fallback | Mechanism changes entirely; teachable as comparison |

### Path C — IPsec VPN topology sketch

Replace ER GWs with VPN GWs. HnS hub: `VpnGw1AZ`; vWAN hub: native VPN GW (1 SU). An
IKEv2+BGP S2S connection runs directly between the two VPN GWs (Azure-to-Azure, no MSEE).
Dual-stack requires active-active GW with IPv6 BGP peer addresses. Both GWs use ASN 65515 —
AS override needed on the connection (or use distinct lab ASNs 65501/65502). Separate CHILD_SAs
for `fd00:2::/64` ↔ `fd00:4::/64`. Cost ~$5/6h. Proves IPv6 reachability without MSEE;
loses the hairpin pedagogical point.

---

## 12. Niobe — What's True After Deploy

Pre-run: ER Direct port `Provisioned`; both circuits `Provisioned/Enabled`; private peering `state=Enabled` (IPv4+IPv6); GW connections `Connected`.

### S1 — IPv4 ping HnS spoke → vWAN spoke

```bash
# Confirm route learned
az network vnet-gateway list-learned-routes -g msee-hairpin-rg -n ergw-hns -o json \
  | jq '[.value[] | select(.prefix | startswith("10.4"))]'
# Expected: 10.4.0.0/24 present, source=EBgp

# Connectivity test
az vm run-command invoke -g msee-hairpin-rg --name vm-hns-spoke \
  --command-id RunShellScript --scripts "ping -c4 10.4.0.4"
# Expected: 0% packet loss
```

### S2 — IPv6 ping HnS spoke → vWAN spoke

```bash
az network vnet-gateway list-learned-routes -g msee-hairpin-rg -n ergw-hns -o json \
  | jq '[.value[] | select(.prefix | startswith("fd00:4"))]'
# Expected: fd00:4::/64 present, source=EBgp
az vm run-command invoke -g msee-hairpin-rg --name vm-hns-spoke \
  --command-id RunShellScript --scripts "ping6 -c4 <vm-vwan-spoke-ipv6-addr>"
# Expected: 0% packet loss
```

### S3 — Route-table evidence (three-layer collection)

```bash
# L1a — HnS GW learned & advertised routes (authoritative; use instead of list-route-tables)
az network vnet-gateway list-learned-routes -g msee-hairpin-rg -n ergw-hns -o json
az network vnet-gateway list-advertised-routes -g msee-hairpin-rg -n ergw-hns \
  --peer 172.16.1.2 -o json

# L1b — vWAN hub effective routes for spoke VNet connection
az network vhub get-effective-routes --resource-group msee-hairpin-rg --name vhub-sto \
  --resource-type HubVirtualNetworkConnection --resource-id <cx-spoke-vwan-id> -o json

# L1c — Circuit route tables (always -o json — table output is unreliable; known CLI bug)
az network express-route list-route-tables -g msee-hairpin-rg \
  --name erc-hns --peering-name AzurePrivatePeering --path primary -o json

# L3 — VM NIC effective routes
az network nic show-effective-route-table -g msee-hairpin-rg -n <vm-hns-spoke-nic> -o json
az network nic show-effective-route-table -g msee-hairpin-rg -n <vm-vwan-spoke-nic> -o json
```

### S4 — Deliberate break (`allowVirtualWanTraffic=false`)

```bash
az network vnet-gateway update -g msee-hairpin-rg -n ergw-hns --allow-vwan-traffic false
sleep 90
az vm run-command invoke -g msee-hairpin-rg --name vm-hns-spoke \
  --command-id RunShellScript --scripts "ping -c4 10.4.0.4"
# Expected: 100% packet loss; BGP sessions still Up (routes absent, sessions intact)

az network vnet-gateway update -g msee-hairpin-rg -n ergw-hns --allow-vwan-traffic true
sleep 90  # restore; verify S1 recovers
```

### S5 (stretch) — IPsec fallback (Path C only)

```bash
az network vnet-gateway list-bgp-peer-status -g msee-hairpin-rg -n vpngw-hns -o json
# Expected: BGP peer with vWAN VPN GW IP, state=Connected, IPv4+IPv6 peer addresses visible
az vm run-command invoke -g msee-hairpin-rg --name vm-hns-spoke \
  --command-id RunShellScript --scripts "ping6 -c4 <vm-vwan-spoke-ipv6>"
# Expected: 0% packet loss via IKEv2 tunnel (not MSEE)
```

---

## 13. Tank Handoff

API versions: `2024-03-01` (network) · `2024-07-01` (VMs). All resources in `msee-hairpin-rg`, `swedencentral`.

| Resource | Type (short) | Critical properties |
|---|---|---|
| `erdirect-sto-01` | `expressRoutePorts` | `bandwidthInGbps=10`, `peeringLocation="Stockholm"`, `encapsulation="Dot1Q"` |
| `erc-hns` | `expressRouteCircuits` | `expressRoutePort.id=<port>`, `bandwidthInGbps=1`, `sku={Local_MeteredData}` |
| `erc-vwan` | `expressRouteCircuits` | same shape as erc-hns |
| `erc-hns/AzurePrivatePeering` | `...circuits/peerings` | `peerASN=65515`, `vlanId=100`, pri=`172.16.1.0/30`, sec=`172.16.1.4/30`; `ipv6PeeringConfig` primary=`fd00:f:1::/126` sec=`fd00:f:1::4/126` state=`Enabled` |
| `erc-vwan/AzurePrivatePeering` | `...circuits/peerings` | `peerASN=65515`, `vlanId=200`, pri=`172.16.2.0/30`, sec=`172.16.2.4/30`; ipv6 from `fd00:f:2::/126` / `fd00:f:2::4/126` |
| `vnet-hub-hns` | `virtualNetworks` | `addressSpace=["10.1.0.0/16","fd00:1::/48"]`; GatewaySubnet=`10.1.0.0/27+fd00:1::/64`; VmSubnet=`10.1.1.0/24+fd00:1:1::/64` |
| `vnet-spoke-hns` | `virtualNetworks` | `addressSpace=["10.2.0.0/24","fd00:2::/48"]`; VmSubnet=`10.2.0.0/24+fd00:2::/64` |
| `ergw-hns` | `virtualNetworkGateways` | `gatewayType=ExpressRoute`, `sku=ErGw1AZ`, `allowVirtualWanTraffic=true`, `allowRemoteVnetTraffic=true`, `bgpSettings.asn=65515` |
| `cx-hns-erc1` | `connections` | `connectionType=ExpressRoute`, `virtualNetworkGateway1=<ergw-hns>`, `peer=<erc-hns>` |
| `peer-hub-spoke-hns` / `peer-spoke-hub-hns` | `virtualNetworkPeerings` | hub: `allowGatewayTransit=true`; spoke: `useRemoteGateways=true` |
| `vwan-hairpin` | `virtualWans` | `type=Standard` |
| `vhub-sto` | `virtualHubs` | `addressPrefix=10.3.0.0/23`, `virtualWan.id=<vwan-hairpin>`; set `ipv6AddressSpace=fd00:3::/48` via `az rest` if TF resource doesn't expose it |
| `vwan-ergw` | `expressRouteGateways` | `virtualHub.id=<vhub-sto>`, `autoScaleConfiguration.bounds={min:1,max:1}`, `allowNonVirtualWanTraffic=true` |
| `cx-vwan-erc2` | `...expressRouteGateways/expressRouteConnections` | `expressRouteCircuitPeering.id=<erc-vwan/AzurePrivatePeering>` |
| `vnet-spoke-vwan` | `virtualNetworks` | `addressSpace=["10.4.0.0/24","fd00:4::/48"]`; VmSubnet=`10.4.0.0/24+fd00:4::/64` |
| `cx-spoke-vwan` | `virtualHubs/hubVirtualNetworkConnections` | `remoteVirtualNetwork.id=<vnet-spoke-vwan>` |
| `vm-hns-spoke` / `vm-vwan-spoke` | `virtualMachines` | `size=Standard_B2als_v2`, `adminUsername=azurelabuser`, password from KV `default-password`; NICs in respective VmSubnets |
| `nsg-hns-spoke` / `nsg-vwan-spoke` | `networkSecurityGroups` | Allow ICMPv4 (100), ICMPv6 (110), TCP/22 (120) inbound |

---

## Design Notes

### Open technical question — customer-side BGP on ER Direct

**Morpheus's claim:** Customer-side BGP on the ER Direct port is not needed.

**Finding:** Consistent with standard MSEE hairpin behavior. Azure ER GWs establish BGP with the
MSEE via the circuit connection — the GW **is** the BGP endpoint on the "customer" side. The MSEE
reflects routes between circuits when the three toggles are set. No physical CPE needed.

**Evidence:** MSEE hairpin described as default behavior between two circuits at the same POP in
[adtork/MSEE-Hairpin-Design-Considerations](https://github.com/adtork/MSEE-Hairpin-Design-Considerations).
No counter-evidence in vault or MS Learn. **Confidence: high — flag for Niobe to confirm
post-deploy.** Confirmed when `list-learned-routes` on ergw-hns shows vWAN spoke prefixes.

### Vault index results

- `[[Services/ExpressRoute]]` — Q&A section covers ER-to-ER via MSEE; by default MSEE won't
  propagate routes between circuits; the toggles unlock it. No prior vault page on ER Direct or
  IPv6 ER peering.
- `[[Topics/BGP-on-Azure]]` — vWAN ER GW uses 65515; 65520 is inter-hub internal only.
- No prior vault page on MSEE hairpin lab, ER Direct lab, or dual-stack IPv6 ER peering.

### Known CLI gotcha — `list-route-tables` false negative

`az network express-route list-route-tables` returns `"Gateway does not have any Bgp sessions"`
even when sessions are up (from `[[Services/ExpressRoute]]`, lab #1). Use
`az network vnet-gateway list-learned-routes` as authoritative source. Niobe must use this for S3.

### IPv6 BGP sequencing

Order matters: (1) add fd00:x::/48 to VNets + /64 to subnets; (2) ensure GW is dual-stack
(may require GW recreation); (3) update circuit peering with `ipv6PeeringConfig`;
(4) verify `state=Enabled` in peering show output.

### vWAN hub IPv6 address space

`ipv6AddressSpace` on `virtualHubs` may not be exposed in all TF providers. If missing, use
`az rest --method PATCH --uri .../virtualHubs/vhub-sto?api-version=2024-03-01` to add it.
Flag for Tank to validate during manifest review.

---

*Design v1 · 2026-06-15 · Trinity*
