# ExpressRoute HRP: local preference depends on route history

**PASS: the original three-extra-prepend configuration reproduced local
Japan-path preference at both Europe and US after a controlled withdrawal
and re-advertisement of Japan's direct VPN advertisement.**

This is a route-selection experiment, not a traffic test or a declaration
of Azure's internal root cause.

## Controlled sequence

EU/US retained their exact original BIRD files: three extra own-AS prepends
for foreign DC exports, none for their local DC. Japan retained its original
zero-extra-prepend export policy. Foreign DC imports from Azure remained
rejected; the NVAs selected their customer-mesh routes.

| State | HRP, all hubs | JP direct VPN advertisement of `10.130.0.0/24` | Europe firewall winner | US firewall winner |
| --- | --- | --- | --- | --- |
| [er-original](er-original/scenario-result.json) | ExpressRoute | Present | Remote Hub, `65520-65520-65013` | Remote Hub, `65520-65520-65013` |
| [jp-withdrawn](jp-withdrawn/scenario-result.json) | ExpressRoute | Withdrawn from both JP Azure peers; still advertised on the mesh | Local HubBgpConnection, `65011-65011-65011-65011-65013` | Local HubBgpConnection, `65012-65012-65012-65012-65013` |
| [jp-returned](jp-returned/scenario-result.json) | ExpressRoute | Restored on both JP Azure peers | Local HubBgpConnection, `65011-65011-65011-65011-65013` | Local HubBgpConnection, `65012-65012-65012-65012-65013` |

Every state has paired firewall snapshots spaced by at least 120 seconds,
all three full firewall tables, all four BIRD configurations, NVA selected
and alternative routes, Azure export views, and kernel routes/lookups.

The final state restores the original Japan advertisement, not a permanent
withdrawal that removes the competitor. Japan's firewall selects its own
`65013` VPN route, and both Japan Azure export views contain its DC prefix.
All four original configuration bytes and metadata and all three HRPs match
between `er-original` and `jp-returned`, yet EU/US winners differ.

## What this resolves

1. The local peered-NVA routes are eligible: Azure selects them when Japan's
   direct export is absent.
2. ExpressRoute HRP can retain a longer local NVA path when the shorter
   remote VPN advertisement returns. This reproduces the intended behavior.
3. Starting from an already-selected remote path and merely changing HRP
   did not produce the same state in this run. Route history matters.

The [HRP documentation](https://learn.microsoft.com/en-us/azure/virtual-wan/about-virtual-hub-routing-preference)
orders local preference before AS-path length for ExpressRoute and VPN.
It also warns of a race condition when the local path is at least two ASNs
longer than the remote path. Here the original local path is five ASNs and
the remote path three, so that warning is relevant.

**Do not overstate the cause:** no Azure backend tracing was collected, so
this does not identify the internal race or prove that every HRP change
requires a route refresh. The separate 16 October two-extra-prepend case
had a one-ASN difference and remains outside that published condition.
This new result does not rewrite its historical negative verdict.

**Subsequent control:** the [one-ASN follow-up](../hrp-one-asn-control-20261017/README.md)
also demonstrated history dependence with EU path length four versus remote
three. This establishes an additional observation outside the documentation's
published condition, not proof of an identical Azure-internal mechanism.

Only the Japan prefix was controlled. Other foreign DC prefixes were not
individually refreshed, and a successful Japan result is not an automatic
all-prefix customer-first or forwarding guarantee. VPN HRP remains untested.

## Full B1 observation points

Use the final `jp-returned` state for a matched B1 design presentation:

- [EU full firewall table](jp-returned/jp-returned-eu-table2.txt) and
  [Japan full firewall table](jp-returned/jp-returned-jp-table2.txt).
- [EU, Japan, US and China selected routes](jp-returned/selected-routes.json).
- [EU configuration](jp-returned/router-eu.conf),
  [Japan configuration](jp-returned/router-jp.conf) and
  [China configuration](jp-returned/router-cn.conf).

The full earlier states remain available to show how this state was reached.
No IPsec or WireGuard settings, mesh exports, subnet associations or workload
routes changed. BGP session health and Japan's two IKE SAs were checked
throughout. Existing kernel-export warnings are not remediated by this test.

## Restoration and reproducibility

[Original scenario verdict](reselection-verdict.json): **PASS**, outcome
`route-history-sensitive-local-preference`, restored true.
[Independent baseline verification](../hrp-reselection-verify-20261017/verification-verdict.json):
**PASS**, exact source/metadata/session health, original mixed HRPs and
paired original firewall winners restored.
[Power restoration](../hrp-reselection-power-20261017/power-verdict.json):
**PASS**, only the four routers started for this request were deallocated;
six workload probes were untouched. The STOP sentinel was reinstated.

The [controller](../../deploy/design_hrp_reselection.py) requires a fresh
six-mutation lease and accepted fresh baseline. It includes a bounded exact
restore. This run used four mutations: HRP apply, JP prefix withdrawal, JP
prefix restoration and original-HRP restoration. Do not replay closed leases.
