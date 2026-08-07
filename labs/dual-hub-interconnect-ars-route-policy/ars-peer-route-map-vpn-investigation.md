# Route Server peer, route-map, and VPN export investigation

**Date:** 2026-08-07
**Scope:** Read-only inspection plus failed validation requests. No live connection, peering, route-map
association, or BIRD configuration was changed.

## Executive result

The three symptoms do not share one missing setting:

| Symptom | Verdict | Root cause |
|---|---|---|
| Add NVA2 to ARS1, or NVA1 to ARS2 | Supported in general, blocked in this topology | A peer in a directly peered VNet requires that VNet to enable **Use remote gateway or Route Server**. Each remote hub already owns a VPN gateway, so Azure cannot enable that setting. |
| Apply a Route Server route map to the VPN connection | Unsupported on the deployed connection type | The six square edges are `Vnet2Vnet` connections. The Network resource provider rejected `routingConfiguration` with `InvalidRoutingConfigurationForConnectionType`. |
| Simulated on-premises gateways receive no Azure routes | Expected limitation of this analogue | The hub VPN gateways learn NVA routes from Route Server, but advertise an empty set toward the `Vnet2Vnet` peers. These Azure gateways are not behaving like customer-controlled S2S BGP routers. |

The portal is therefore showing only the NVA peer because it has no route-map-eligible VPN
connection in this lab.

## 1. NVA in a directly peered VNet

Microsoft documents that Route Server can peer with an NVA in its own VNet or a **directly peered**
VNet:

- [Configure BGP peering between Route Server and an NVA](https://learn.microsoft.com/azure/route-server/peer-route-server-with-virtual-appliance)

After the Route Server route-map upgrade, the API also requires an explicit
`hubVirtualNetworkConnection` representing the existing VNet peering. A direct BGP-connection PUT
without that object failed with:

```text
HubBgpConnectionMustReferenceFullyProvisionedHubVirtualNetworkConnection
```

Creating that missing object for ARS1→Hub2 then failed with the more useful prerequisite:

```text
VNetPeeringInFailedState
Ensure that the spoke VNet .../vnet-hub2 can access and can use the remote gateway
or route server in .../vnet-hub1.
```

The existing global peerings have:

```text
allowVirtualNetworkAccess = true
allowForwardedTraffic     = true
allowGatewayTransit       = false
useRemoteGateways         = false
```

`vnet-hub2` cannot set `useRemoteGateways=true` toward Hub1 because it already contains
`vpngw-hub2`; the mirror constraint applies to Hub1. Thus the public capability is real, but it
does not allow two gateway-owning hub VNets to consume each other's Route Server.

### Supported alternatives

1. Put the remote BGP speaker in a dedicated peered VNet that has no gateway, enable
   **Use remote gateway or Route Server** toward the selected Route Server VNet, and create the
   explicit `hubVirtualNetworkConnection` before the BGP connection.
2. Keep both NVAs hub-local and build an NVA-to-NVA BGP overlay when cross-hub route exchange is
   required.
3. Add a small BGP relay in a dedicated transit VNet rather than trying to make either
   gateway-owning hub consume the other hub's Route Server.

## 2. Route maps on VPN connections

Route maps support NVA BGP peerings, ExpressRoute gateway connections, and VPN gateway connections
in the Route Server VNet:

- [About route maps for Azure Route Server](https://learn.microsoft.com/azure/route-server/route-maps-about)
- [Configure route maps for Azure Route Server](https://learn.microsoft.com/azure/route-server/route-maps-how-to)

For a virtual network gateway, the association is stored on the
`Microsoft.Network/connections` resource in `properties.routingConfiguration`, not on the VPN
gateway resource itself.

The current Azure CLI model does not expose that preview property. A direct REST PUT against
`conn-hub1-to-onprem` with an outbound Route Server map reached the resource provider, which
returned:

```text
InvalidRoutingConfigurationForConnectionType
This RoutingConfiguration is not supported for resource Type Vnet2Vnet.
```

This explains the portal behavior. "VPN gateway connection" in the route-map documentation does
not include the `Vnet2Vnet` connection objects used by this square.

### Supported alternative

Use route-map-capable `IPsec` S2S gateway connections (or ExpressRoute connections). For the
current lab, that means replacing each Azure-to-site `Vnet2Vnet` analogue with Local Network
Gateway-based S2S connections, or replacing the site gateways with router VMs.

## 3. Why the simulated sites receive no Azure routes

The Route Server side is working:

- Both Route Servers have `allowBranchToBranchTraffic=true`.
- Both hub VPN gateways are active-active and use ASN 65515, as required.
- `vpngw-hub1` learns NVA-originated `1.1.1.1/32` with AS path `65001` through ARS1.
- `vpngw-hub2` learns NVA-originated `2.2.2.2/32` with AS path `65002` through ARS2.
- The hub gateways also show their local hub and spoke prefixes in their learned-route views.

The export boundary is the failure:

- `vpngw-hub1` advertises an empty route set to peers `10.40.0.4` and `10.40.0.5`.
- `vpngw-hub2` advertises an empty route set to peers `10.50.0.4` and `10.50.0.5`.
- `vpngw-onprem` and `vpngw-onprem2` consequently learn site/DCI routes and gateway-host `/32`
  routes, but no hub, spoke, or NVA-originated prefixes.

Microsoft documents that branch-to-branch exchanges NVA and virtual-network-gateway routes:

- [Route Server support for ExpressRoute and Azure VPN](https://learn.microsoft.com/azure/route-server/expressroute-vpn-support)

The documented behavior does not override the separate `Vnet2Vnet` connection limitation observed
here. The square's Azure-gateway sites are therefore not a faithful substitute for external S2S
BGP routers.

## Recommended lab correction

For the least ambiguous test:

1. Keep ARS1, ARS2, NVA1, NVA2, Hub1, Hub2, and the spokes.
2. Replace the two simulated-site Azure VPN gateways with Ubuntu router VMs running
   StrongSwan and BIRD/FRR, or rebuild the hub-site edges as true `IPsec` S2S connections through
   Local Network Gateway resources.
3. Apply Route Server route maps to the resulting `Microsoft.Network/connections` S2S objects.
4. Keep NVAs local to their Route Servers. Use an explicit NVA overlay or dedicated transit-VNet
   BGP relays for cross-hub policy.

That redesign requires a separately approved deployment/change window because it creates or
replaces connectivity resources and can interrupt the live square.
