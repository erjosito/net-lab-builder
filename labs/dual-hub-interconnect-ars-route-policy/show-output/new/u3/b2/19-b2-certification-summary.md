# B2 Certified Baseline — U3 entry point (re-captured 2026-08-06, pre-U3a)

Fresh, live, read-only re-capture taken at the start of U3 execution, immediately before U3a. This
is **not** a reuse of `show-output/new/u15-u2/b2/` — every file below was captured live in this
pass and independently byte-compared against the prior session's B2 (`u15-u2/b2/`) to certify no
drift occurred across the session gap.

## Byte-identity vs the prior session's B2 (`u15-u2/b2/`)

| File | Diff count |
|---|---|
| 01-ars-hub1-peer-nva1-learned.json | 0 |
| 02-ars-hub1-peer-nva1-advertised.json | 0 |
| 03-ars-hub2-peer-nva2-learned.json | 0 |
| 04-ars-hub2-peer-nva2-advertised.json | 0 |
| 05-nva1-nic-effective-routes.json | 0 |
| 06-nva2-nic-effective-routes.json | 0 |
| 09-vpngw-onprem-learned-routes.json | 0 |

## Session health (BIRD `Since`, no reset across the session gap)

| Session | Prior B2 `Since` | This capture `Since` | Match |
|---|---|---|---|
| ars_hub1_0 | 07:12:12.272 | 07:12:12.272 | ✅ |
| ars_hub1_1 | 07:12:13.010 | 07:12:13.010 | ✅ |

(`Since` timestamps are wall-clock-since-boot in `birdc`'s own display and are unchanged from the
certified prior baseline — proof that no BGP reset occurred on `vm-nva1` between the prior session
and this one.)

## Route / association state confirmed live

- `ars-hub1` learns from `peer-nva1`: `0.0.0.0/0` (asPath `65001`, both instances) and
  `10.40.0.0/16` (asPath `65001-65000`, `RouteServiceRole_IN_1` only — unchanged, expected
  instance-asymmetric boomerang). **`198.51.100.0/24` absent** (pre-U3a, as expected).
- `ars-hub2` learns from `peer-nva2`: mirrored set (`0.0.0.0/0`, `10.40.0.0/16`), unchanged.
- `peer-nva1` (`17-peer-nva1-routingConfiguration-GET.json`): `routingConfiguration.inboundRouteMap.id`
  = `rm-hub1-tmp-assoc`; `vnetRoutes.staticRoutesConfig` = `{propagateStaticRoutes: true,
  vnetLocalRouteOverrideCriteria: "Contains"}` — preserved byte-for-byte from U2.
- `rm-hub1-tmp-assoc` (`18-rm-hub1-tmp-assoc-GET.json`): single rule `rule-tmp-inert`, match
  `203.0.113.0/24` `Equals`, action `Add asPath ["64496"]`, `associatedInboundConnections` =
  `[peer-nva1]` only. **Still the U2 inert state — not yet modified.**

## VPN / connectivity

- `10-vpn-connections-status.json` (`az network vpn-connection show` ×4, includes
  `tunnelConnectionStatus`): all 4 connections `connectionStatus: Connected`.
- `11-vm-power-states.txt`: `vm-nva1`/`vm-nva2` running; `vm-hub1-ep`, `vm-hub2-ep`,
  `vm-onprem-ep` deallocated — unchanged.

## Data plane

- `16-ping-nva1-to-nva2.txt`: `vm-nva1 → vm-nva2` (10.20.1.4), 0% loss.

## Verdict

**B2 CERTIFIED for U3.** All expected-identical layers are byte-identical to the prior session's
certified B2, both BGP sessions show unchanged `Since` (no flap across the session gap), all 4 VPN
connections `Connected`, `rm-hub1-tmp-assoc` remains in its U2 inert state, and `198.51.100.0/24`
does not exist anywhere. This is the authoritative pre-U3a reference for every diff in `u3a/`,
`u3b/`, `cleanup/`, and `b3/`.
