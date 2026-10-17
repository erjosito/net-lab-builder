# One-ASN-difference HRP route-history control

**PASS, restored true.** Europe reproduced history-dependent Japan-prefix
selection with local AS-path length **four** versus remote length **three**.
This is a separate control outside the documented two-or-more-longer condition.

All hubs used ExpressRoute HRP. Europe used two extra nonlocal prepends,
while US retained its original three as a comparator. Japan used no extra
prepends. No other import, mesh, IPsec, WireGuard or workload policy changed.

| State | Europe firewall, `10.130.0.0/24` | US firewall |
| --- | --- | --- |
| [er-original](er-original/scenario-result.json), Japan direct export present | Remote Hub, `65520-65520-65013` | Remote Hub, `65520-65520-65013` |
| [jp-withdrawn](jp-withdrawn/scenario-result.json), only Japan's direct Azure prefix export withdrawn | Local NVA, `65011-65011-65011-65013` | Local NVA, `65012-65012-65012-65012-65013` |
| [jp-returned](jp-returned/scenario-result.json), original Japan export restored | Local NVA, `65011-65011-65011-65013` | Local NVA, `65012-65012-65012-65012-65013` |

All four BIRD configuration bytes, metadata and session health and all
three HRPs match between the initial and final states. Every state includes
paired stable firewall snapshots spaced by at least 120 seconds, full NVA
routes/exports and sources, and kernel evidence. Japan's direct VPN route
and both original Azure exports are present again in the final state.

This confirms the local candidate is eligible and that ExpressRoute HRP can
retain the longer local path. The static configuration alone does not explain
which state was observed: route history is a demonstrated differentiator.
The [original three-prepend control](../hrp-reselection-control-20261017/README.md)
showed the same before/after pattern at length five versus three.

The documentation's warning about a local route at least two ASNs longer
does not fully describe this four-versus-three case. No Azure backend trace
was collected, so no particular internal race, cache or software defect is
claimed. This does not generalize to all HRP changes, prefixes or NVA types.
The historical 16 October negative control is preserved, not edited into a pass.

## Evidence and exact closure

- [Scenario verdict](reselection-verdict.json): **PASS**, outcome
  `route-history-sensitive-local-preference`, six mutations used.
- [Final EU firewall](jp-returned/jp-returned-eu-table2.txt) and
  [Japan firewall](jp-returned/jp-returned-jp-table2.txt).
- [All NVA selected routes](jp-returned/selected-routes.json), plus
  [EU](jp-returned/router-eu.conf), [Japan](jp-returned/router-jp.conf) and
  [China](jp-returned/router-cn.conf) source configurations.
- [Independent baseline verification](../hrp-one-asn-verify-20261017/verification-verdict.json):
  **PASS**, original three-prepend EU file, all other exact sources/metadata,
  BGP health, IKE SA count, mixed HRPs and original paired firewall winners.
- [Power restoration](../hrp-one-asn-power-20261017/power-verdict.json):
  **PASS**, only started routers deallocated, original full VM inventory
  restored, probes untouched and STOP reinstated.

No forwarding tests were run. Existing kernel-export warnings remain.
The [bounded controller](../../deploy/design_hrp_reselection.py) option
`--eu-extra 2` selects this distinct control; its default remains the original
three-prepend case. Both require fresh leases, accepted baselines and exact
restoration; do not replay closed leases.
