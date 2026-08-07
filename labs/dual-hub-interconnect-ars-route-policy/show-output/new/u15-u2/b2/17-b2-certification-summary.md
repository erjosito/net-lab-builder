# B2 Certified Baseline — post-U2

Captured as a fresh, single-point-in-time snapshot immediately after U2
(`rm-hub1-tmp-assoc` created and associated with `peer-nva1` on `ars-hub1`,
`provisioningState: Succeeded`). This is the authoritative "current state"
reference going forward, superseding B1 (which remains valid as the
post-U1.5/pre-U2 checkpoint).

## Byte-identity vs B1

`Compare-Object` run file-by-file between `b1/` and `b2/` for every layer not
expected to carry a live/volatile counter (ARS learned/advertised both hubs,
NIC effective routes both NVAs, on-prem learned routes):

| File | Diff count |
|---|---|
| 01-ars-hub1-peer-nva1-learned.json | 0 |
| 02-ars-hub1-peer-nva1-advertised.json | 0 |
| 03-ars-hub2-peer-nva2-learned.json | 0 |
| 04-ars-hub2-peer-nva2-advertised.json | 0 |
| 05-nva1-nic-effective-routes.json | 0 |
| 06-nva2-nic-effective-routes.json | 0 |
| 09-vpngw-onprem-learned-routes.json | 0 |

`07`/`08` (vpngw advertised-to-onprem) are `{"value": []}` in both B1 and pre,
consistent with the established baseline pattern (not a regression).

## Session health (BGP `Since`, no reset)

| Session | B1 Since | B2 Since | Match |
|---|---|---|---|
| ars_hub1_0 | 07:12:12.272 | 07:12:12.272 | ✅ |
| ars_hub1_1 | 07:12:13.010 | 07:12:13.010 | ✅ |
| ars_hub2_0 | 07:12:17.496 | 07:12:17.496 | ✅ |
| ars_hub2_1 | 07:12:20.643 | 07:12:20.643 | ✅ |

No BGP session reset occurred as a result of U2 (route map/association changes
are ARS control-plane objects; they do not touch the eBGP session state on the
NVAs).

## Route state

- `master4` on both nva1 and nva2: **9 of 9 routes for 6 networks** — identical
  count to post-U1.5 (B1); no `10.30.0.0/27` reappearance; no new routes
  introduced by the inert `rm-hub1-tmp-assoc` (its single rule matches
  `203.0.113.0/24`, which does not exist anywhere in this lab).

## Data plane

- Ping `vm-nva1 → vm-nva2`: 8/8 received, 0% loss (16-ping-nva1-to-nva2.txt).

## VPN / connectivity

- `10-vpn-connections-status.json`: all 4 connections `Connected` (sanitized).
- `11-vm-power-states.txt`: `vm-nva1`/`vm-nva2` running, others deallocated —
  unchanged from `pre/`.

## Verdict

**B2 CERTIFIED.** All expected-identical layers are byte-identical to B1, no
session resets, no route regressions, 0% ping loss, VPN fully connected.
Confirms U2 introduced exactly one live change — the `inboundRouteMap`
association metadata on `peer-nva1` — with zero collateral effect on data
plane, control plane sessions, or any other resource.
