# Linux-site replacement certification

**Captured:** 2026-08-08

## Live topology

| Edge | Implementation | State |
|---|---|---|
| Hub1-DC1 | `conn-hub1-to-router-dc1`, LNG-backed `IPsec`, BGP 65515-65000 | Connected; two IKE SAs and two BGP sessions |
| Hub2-DC2 | `conn-hub2-to-router-dc2`, LNG-backed `IPsec`, BGP 65515-65003 | Connected; two IKE SAs and two BGP sessions |
| DC1-DC2 | Direct StrongSwan XFRM tunnel, BGP 65000-65003 | IKE and BGP established |
| Hub1-Hub2 | Existing global VNet peering | Connected |

The former `vpngw-onprem`, `vpngw-onprem2`, their public IPs, all `Vnet2Vnet` connections, and the
temporary gateway-to-gateway LNG objects are absent.

## Management

- DC1 router: `vm-router-dc1`, `20.100.196.162:2222`, private IP `10.40.2.4`
- DC2 router: `vm-router-dc2`, `20.215.212.125:2222`, private IP `10.50.2.4`
- SSH user: `labadmin`, using the existing user SSH public key

## Routing evidence

- Hub1 learned `10.40.0.0/16` with AS path `65000` and `10.50.0.0/16` with
  `65000 65003`.
- Hub2 learned `10.50.0.0/16` with AS path `65003` and `10.40.0.0/16` with
  `65003 65000`.
- DC1 learned Hub1/Spoke A directly and Hub2/Spoke B through DC2.
- DC2 learned Hub2/Spoke B directly and Hub1/Spoke A through DC1.
- Both site endpoint NICs have `10.0.0.0/8` UDRs to their local router.

## Reachability matrix

All probes used three ICMP packets and returned zero loss.

| Source | Destinations | Result |
|---|---|---|
| DC1 endpoint `10.40.1.4` | Spoke A, Spoke B, DC2 endpoint | PASS |
| DC2 endpoint `10.50.1.4` | Spoke A, Spoke B, DC1 endpoint | PASS |
| Spoke A `10.11.0.4` | Spoke B, DC1 endpoint, DC2 endpoint | PASS |
| Spoke B `10.21.0.4` | Spoke A, DC1 endpoint, DC2 endpoint | PASS |

The one-arm site routers apply destination-site SNAT only when forwarding a packet from outside the
site into that site's `/16`. This is required for Azure local endpoint delivery in this simulation.

## Route-map result

`rm-hub2-activate` is associated with `conn-hub2-to-router-dc2` at
`properties.routingConfiguration.outboundRouteMap`. The map is inert for the current live prefixes.
After association:

- Connection provisioning: `Succeeded`
- Connection runtime: `Connected`
- Both DC2 hub-facing BGP sessions: established
- Hub2 and Spoke B prefixes still present on DC2
- Post-change DC2 reachability matrix: PASS

This confirms that Route Server route maps support the replacement `IPsec` S2S connection and that
the earlier `InvalidRoutingConfigurationForConnectionType` failure was specific to `Vnet2Vnet`.
