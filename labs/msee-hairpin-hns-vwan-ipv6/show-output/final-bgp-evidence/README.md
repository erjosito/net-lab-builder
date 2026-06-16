# Final BGP / routing evidence — captured before teardown

Captured immediately before deleting the live lab (2026-06-16).

## Files

- `01-hns-ergw-learned.json` — HnS ER GW learned routes. Shows the hairpin
  delivers ONLY IPv4 from the vWAN side (`10.3.0.0/23`, `10.4.0.0/24` via
  AS-path `12076-12076`). The only IPv6 present (`fd00:1::/48`, `fd00:2::/48`)
  is HnS-local (`Network` origin), never IPv6 from vWAN.

- `02-hns-ergw-advertised.json` — Routes HnS ER GW advertises to the MSEE.
  Confirms HnS DOES send IPv6 (`fd00:1::/48`, `fd00:2::/48`) toward ExpressRoute.
  So the IPv6 failure is NOT on the HnS side.

- `03-vhub-effective-routes.json` — vHub defaultRouteTable. IPv4 only
  (`10.1.0.0/16`, `10.2.0.0/24` via ExpressRouteGateway; `10.4.0.0/24` via
  the vWAN spoke connection). Zero IPv6 — not even the vWAN spoke's own
  `fd00:4::/48`.

- `../msee-rib-ipv6-evidence/` — MSEE (ER circuit) RIB. The decisive proof:
  the vWAN ER GW injects its IPv4 prefixes but ZERO IPv6 into the MSEE.

## Conclusion

IPv4 MSEE hairpin HnS <-> vWAN: WORKS.
IPv6: blocked because GA Virtual WAN hubs are IPv4-only — the vHub holds no
IPv6 to advertise to the MSEE. A vWAN IPv6 preview is reportedly underway
(GA ~Sept 2026, internal aka.ms/ipv6roadmap), allowlist-gated.
