# U2 Diff Summary — rm-hub1-tmp-assoc creation + peer-nva1 association

**Scope executed:** Trinity U2 plan §2 — create dedicated, inert route map
`rm-hub1-tmp-assoc` on `ars-hub1` matching an absent prefix
(`203.0.113.0/24`), and associate it as the `inboundRouteMap` on
`bgpConnections/peer-nva1` via byte-preserving PUT with `If-Match`.
No changes made to `rm-hub1-activate` or to any `ars-hub2` object.

## Sequence executed

| Step | Action | Result |
|---|---|---|
| 0 | Fresh GET `peer-nva1` | etag `W/"a78c47b3-..."`, properties matched pre-U2 expectation (00-pre-peer-nva1-GET.json) |
| 1 | PUT `routeMaps/rm-hub1-tmp-assoc` (new object) | Succeeded — rule matches `203.0.113.0/24` (absent prefix), action AddASPath 64496 + Terminate (01) |
| 2 | Fresh etag re-GET, PUT `bgpConnections/peer-nva1` with `If-Match`, `inboundRouteMap.id` added, all else preserved | `provisioningState: Updating` → polled to `Succeeded` at 18:01:43Z (02, 02-put-timing.txt) |
| 3 | Post GET `peer-nva1` | `provisioningState: Succeeded`, `inboundRouteMap` present, `vnetRoutes`/`staticRoutesConfig` unchanged (03) |
| 4/5 | ARS hub1 peer-nva1 learned/advertised routes | Byte-identical vs B1 baseline (`Compare-Object` empty diff) |
| 6 | VPN connections status | All 4 `Connected` |
| 7 | BIRD session timeline nva1 | `ars_hub1_0` Since `07:12:12.272`, `ars_hub1_1` Since `07:12:13.010` — **unchanged** vs pre-U1.5/B1 baseline; no session reset |
| 8 | Route-map inventory hub1 | `rm-hub1-activate`: `associatedInboundConnections: []` (untouched); `rm-hub1-tmp-assoc`: `associatedInboundConnections: [peer-nva1]` (association reflected) |
| 9 | Ping vm-nva1 → vm-nva2 | 8/8 received, 0% loss |

## PUT preservation proof

Derived strictly from the fresh pre-PUT GET (`00-pre-peer-nva1-GET.json`), not
from the placeholder scripts/bodies file:

| Field | Pre-U2 | Post-U2 | Preserved? |
|---|---|---|---|
| `peerAsn` | 65001 | 65001 | ✅ unchanged |
| `peerIp` | 10.10.1.4 | 10.10.1.4 | ✅ unchanged |
| `routingConfiguration.vnetRoutes.staticRoutes` | `[]` | `[]` | ✅ unchanged |
| `staticRoutesConfig.propagateStaticRoutes` | `true` | `true` | ✅ unchanged |
| `staticRoutesConfig.vnetLocalRouteOverrideCriteria` | `Contains` | `Contains` | ✅ unchanged |
| `provisioningState` | (removed — read-only) | server-assigned | ✅ correctly dropped from request body |
| `routingConfiguration.inboundRouteMap.id` | absent | `.../routeMaps/rm-hub1-tmp-assoc` | ✅ only intentional addition |

Request used `If-Match` with a freshly re-fetched etag (no PATCH used at any
point). No other property was present in the PUT body.

## PASS criteria (per Trinity plan)

- [x] Association visible on `peer-nva1` (`inboundRouteMap.id` set)
- [x] Map association metadata reflects it (`associatedInboundConnections`)
- [x] All routes byte-identical B1 → B2 (learned/advertised diff empty)
- [x] All `vnetRoutes` unchanged
- [x] Sessions healthy (`ars_hub1_0/1` Established, `Since` unchanged — no reset)
- [x] VPN connections `Connected` (all 4)
- [x] `rm-hub1-activate` and `ars-hub2` untouched

**Verdict: PASS.** Per instructions, the inert association is left in place
(no rollback triggered — plan permits leaving it in place on PASS unless
explicitly told to roll back after evidence, which was not the case here).

## Rollback status

Not exercised. No unexpected delta was observed at any step; `rollback-if-any/`
remains empty by design.
