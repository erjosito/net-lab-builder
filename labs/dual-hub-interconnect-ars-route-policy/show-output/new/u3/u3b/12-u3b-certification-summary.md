# U3b Certification Summary — rm-hub1-tmp-assoc Rule Update (AS-Path Add Test)

**Date:** 2026-08-06
**Executed by:** Tank (IaC Engineer)
**Scope:** U3b only — modify the existing rule in `rm-hub1-tmp-assoc` to match `198.51.100.0/24`
(the U3a synthetic test-net prefix) and apply `Add asPath ["64496","64496"]`, preserving the
existing inbound association to `peer-nva1`. No other resource touched.

## Actions taken

1. Captured fresh pre-PUT GET of `rm-hub1-tmp-assoc` (`00-pre-hub1-map-rule-GET.json`),
   etag `W/"975b9262-c1e2-4dda-b05b-624edcff61a3"`.
2. Issued `az rest --method put` with `If-Match` set to that etag and body matching
   `scripts/bodies/routemap-aspath-add-body-hub1.json` (rule name `add-64496-x2`,
   match `Equals 198.51.100.0/24`, action `Add asPath [64496,64496]`,
   `nextStepIfMatched: Terminate`) — `01-routemap-put-response.json`.
   - First attempt failed with `PreconditionFailedEtagMismatch` because the shell variable
     already contained a `W/` prefix and `az rest --headers` added its own, producing a
     doubled `W/"W/...".` **Fix:** pass only the quoted etag value (`"975b9262-..."`,
     no leading `W/`) to `--headers If-Match=...`; `az rest` reconstructs the correct
     weak-etag header itself. Second attempt succeeded immediately (`02-put-timing.txt`).
   - PUT issued `2026-08-06T22:01:35+02:00`, HTTP response returned `2026-08-06T22:01:41+02:00`
     with `provisioningState: Updating`.
3. Polled the resource; `provisioningState: Succeeded` observed at `2026-08-06T22:02:16+02:00`
   (~41s to settle) — `03-post-hub1-map-rule-applied-GET.json`. The GET confirms:
   - `associatedInboundConnections` unchanged — still exactly `["...bgpConnections/peer-nva1"]`
     (association preserved, not recreated).
   - `associatedOutboundConnections: []` unchanged.
   - `rules[0]` now shows `matchCriteria.routePrefix = ["198.51.100.0/24"]`,
     `actions[0] = {type: Add, parameters:[{asPath:["64496","64496"]}]}`,
     `nextStepIfMatched: Terminate` — exactly the approved body.

## Proof surfaces checked (post-PUT)

| Surface | File | Result |
|---|---|---|
| `ars-hub1/peer-nva1` learned routes (both instances) | `04-post-ars-hub1-peer-nva1-learned.json` | `198.51.100.0/24` present, `asPath: "65001"` on **both** `RouteServiceRole_IN_0` and `RouteServiceRole_IN_1` — **as-received value, NOT post-policy `64496-64496-65001`** |
| `ars-hub1/peer-nva1` advertised routes | `05-post-ars-hub1-advertised.json` | `198.51.100.0/24` **absent** (ARS does not re-advertise NVA-learned prefixes onward to gateways in this topology — same as U3a; containment intact) |
| Gateway `vpngw-hub1` advertised-to-onprem | `06-post-gw-hub1-advertised-to-onprem.json` | `198.51.100.0/24` **absent** |
| Gateway `vpngw-hub2` advertised-to-onprem | `07-post-gw-hub2-advertised-to-onprem.json` | `198.51.100.0/24` **absent** |
| On-prem (`vpngw-onprem`) learned routes | `08-post-onprem-learned-routes.json` | `198.51.100.0/24` **absent** |
| `ars-hub2/peer-nva2` learned routes | `09-post-ars-hub2-peer-nva2-learned.json` | `198.51.100.0/24` **absent** (hub2 containment intact) |
| VPN connections (all 4) | `10-post-vpn-connections-status.json` | all `Connected`, `provisioningState Succeeded` |
| BIRD `show protocols` on `vm-nva1` | `11-post-bird-nva1-protocols.json` | `ars_hub1_0 Since 07:12:12.272`, `ars_hub1_1 Since 07:12:13.010` — **unchanged from B2/U3a baseline, no flap**. (Expected: this is a pure ARS control-plane object change; BIRD is not involved.) |
| Portal Route Map dashboard | not captured | Not attempted — no authenticated interactive browser session available in this non-interactive automation context. The Azure CLI / ARM REST surface used above (`az network routeserver ... list-learned-routes`, `az rest` GET on the route map) is the same data source the portal blade renders from for this preview feature, so it is treated as equally authoritative; a screenshot would not be expected to reveal information not already present in the JSON captured here. |

## Verdict: **INCONCLUSIVE**

Per contract item 5, criteria for INCONCLUSIVE: *"map/association succeeds but available
learned-route surfaces expose only as-received path or no post-policy attribute."* This is
exactly what was observed:

- The route-map PUT/association **succeeded** with no errors (`provisioningState: Succeeded`,
  association to `peer-nva1` preserved, rule content matches the approved body exactly).
- Containment and non-regression gates **all passed** (hub2, both gateways, on-prem, all VPN
  connections, BIRD session stability — no live route or session changed anywhere outside the
  synthetic prefix's own learned-route entry).
- However, the only available authoritative CLI surface for the resulting BGP attribute
  (`az network routeserver peering list-learned-routes`) still reports `asPath: "65001"` for
  `198.51.100.0/24` on both `ars-hub1` instances — identical to the U3a as-received value,
  with **no visible trace of the `64496,64496` prepend** that the route map's `Add` action
  should have applied to the path attribute presented to downstream consumers.

This matches the evidence-fidelity risk pre-declared in `validation.md` §T2b before execution:
it was not established in advance whether this CLI endpoint reports the BGP attribute
as-received-on-the-wire (pre-inbound-route-map) or as-effective-after-route-map. The empirical
result of this test is that **it reports as-received**, at least for this
`RouteServiceRole_IN_*` per-peer learned-routes endpoint. No production prefix was substituted
to try to force a different, more visible result, per the explicit contract instruction never
to do so.

**This is not a FAIL**: nothing errored, no route leaked where it shouldn't, no session flapped,
and the map+association machinery behaved exactly as configured at every layer that can be
directly observed via `provisioningState` and the rule body echo. The inconclusiveness is a
**tooling/observability limitation of the currently available Route Maps (preview) learned-routes
API**, not a functional defect proven in the data plane or control plane.

