# U3a — containment note

`vm-hub1-ep` (the spoke-a endpoint VM) remains **deallocated** throughout U3a and is not started as
part of this unit — starting it is out of scope for U3 and was not approved. Consequently,
propagation of `198.51.100.0/24` into `vnet-spoke-a`'s NIC effective routes (via
`peer-hub1-to-spoke-a`'s gateway transit, which the design document flags as *"very likely"*) is
**UNVERIFIED BY DESIGN** in this evidence set. This is recorded as an open, unverified data point,
not as a claim of either propagation or non-propagation.

What **is** verified (live, this pass):

- `198.51.100.0/24` present at both `ars-hub1` Route Server instances, learned from `peer-nva1`,
  `asPath "65001"` (`04-post-ars-hub1-peer-nva1-learned.json`).
- `198.51.100.0/24` **absent** from `ars-hub2`'s learned set from `peer-nva2`
  (`04b-post-ars-hub2-peer-nva2-learned.json`) — hub2 is untouched, as expected (U3a only modified
  `vm-nva1`).
- `198.51.100.0/24` **absent** from `vpngw-hub1`'s and `vpngw-hub2`'s advertised-to-on-prem sets
  (`05-post-vpngw-hub{1,2}-advertised-to-onprem.json`, both `{"value": []}`).
- `198.51.100.0/24` **absent** from `vpngw-onprem`'s learned routes
  (`05-post-vpngw-onprem-learned-routes.json`).
- `198.51.100.0/24` **present** in `vm-nva1`'s own NIC effective routes
  (`06-post-nva1-nic-effective-routes.json`, `nextHopIpAddress: 10.10.1.4`) — this is the expected,
  accepted side effect noted in the design (the NVA's own static route is programmed back onto its
  NIC by Azure's route-table reconciliation), not a leak.

This matches the U0/U1.5 precedent exactly: an NVA-originated static of this shape reaches the local
ARS and the NVA's own NIC, but does not reach either hub gateway's advertised-to-on-prem set or
on-prem itself. Containment holds on every surface that is actually testable in this window.
