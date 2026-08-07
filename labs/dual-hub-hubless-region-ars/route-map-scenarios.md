# Route Map Scenarios — Supporting Experiment Catalogue
**Lab:** dual-hub-hubless-region-ars  
**Date:** 2026-08-05  
**Status:** Supporting technical experiment catalogue

## Proven constraints

- `ars-poland` cannot attach route maps to cross-VNet NVA peers (`peer-nva1`, `peer-nva2`).
- Route maps modify existing routes; they do not originate routes or replace UDRs.
- Inbound maps act before best-path; outbound maps act after best-path.
- Route maps cannot modify VNet-native address advertisements.
- Private and Azure-reserved ASNs cannot be prepended.
- ASN `65515` must be stripped by BIRD before ARS receives a route.
- Current `10.31.0.0/24` and `10.32.0.0/24` cannot be safely summarized; the smallest common aggregate is `10.0.0.0/10`.
- Local hub NVA peers and local VPN gateway connections are eligible candidates, but only after live testing confirms the exact attachment point.

## Upgrade prerequisites and cost

- First route-map creation on an ARS triggers an upgrade of about 30 minutes.
- The surcharge remains after maps are deleted; deleting maps does not revert the upgrade.
- Route maps remain in public preview.

## Recommended experiment order

1. **Scenario 2** — safest first experiment; local synthetic peer in `vnet-poland-ars`.
2. **Scenario 9** — after `ars-hub1` upgrade; community tagging on Poland spoke prefixes.
3. **Scenario 10** — after `ars-hub1` upgrade; block on-prem leakage into ARS.
4. **Scenario 15** — after `ars-hub1` upgrade; private-ASN negative test.
5. **Scenario 11** — after `ars-hub2` upgrade; outbound VPN GW advertisement control.
6. **Scenario 14** — after both hub upgrades; block unwanted on-prem prefixes inbound.
7. **Scenario 8** — only if the prefix plan changes; current `10.31/24` + `10.32/24` cannot be summarized safely.

## Scenario catalogue

### 1. ars-poland inbound on `peer-nva1`
- **Purpose:** Try to steer the Poland ARS best-path using the remote hub1 NVA peer.
- **Attachment point / direction:** `ars-poland` → inbound → `peer-nva1`.
- **Classification:** unsupported.
- **Prerequisite / topology change:** none; the peer remains cross-VNet.
- **Expected route effect:** none; the attachment is rejected.
- **Safe test outline:** attempt the association, capture the ARM validation error, confirm the peering stays unchanged.
- **Pass/fail evidence:** fail evidence is `HubBgpConnectionFromSpokeVnetCannotReferenceRouteMap`.
- **Rollback:** none needed; remove any partial association if created.
- **Operational risk:** low to medium; safe because the platform blocks the change.

### 2. Synthetic local peer in `vnet-poland-ars`
- **Purpose:** Prove route-map mechanics with a peer that satisfies the locality rule.
- **Attachment point / direction:** local VM peer in `vnet-poland-ars` → inbound or outbound, depending on the proof.
- **Classification:** supported/useful.
- **Prerequisite / topology change:** add one local B2ts_v2 VM and BGP peer in the ARS VNet.
- **Expected route effect:** the local peer’s learned/advertised prefix changes exactly as the map rules specify.
- **Safe test outline:** advertise a RFC 5737 test prefix, apply a narrow map, confirm the prefix changes without touching production routes.
- **Pass/fail evidence:** pass when the local peer’s route attributes change and no remote routes move; fail if the map cannot attach or affects unrelated prefixes.
- **Rollback:** detach the map, then delete the local test peer VM if no longer needed.
- **Operational risk:** low; safest first experiment.

### 3. Cross-hub route-map bridge
- **Purpose:** Test whether a route map can bridge hub1 and hub2 policy gaps.
- **Attachment point / direction:** any cross-hub path between `ars-hub1` and `ars-hub2`.
- **Classification:** unsupported.
- **Prerequisite / topology change:** would require a BGP path that does not exist.
- **Expected route effect:** none; route maps cannot create topology.
- **Safe test outline:** none beyond documenting that no valid attachment point exists.
- **Pass/fail evidence:** fail by design; no BGP path to attach.
- **Rollback:** none.
- **Operational risk:** none.

### 4. Local relay NVA in `vnet-poland-ars`
- **Purpose:** Use a relay inside the ARS VNet to satisfy locality and observe the side effects.
- **Attachment point / direction:** local relay NVA → inbound.
- **Classification:** supported but conditional.
- **Prerequisite / topology change:** add a relay VM/NVA in `vnet-poland-ars`.
- **Expected route effect:** route-map attachment succeeds; the relay becomes an extra hop for 0/0.
- **Safe test outline:** inject a single test prefix through the relay, confirm the map works, then measure added hop cost.
- **Pass/fail evidence:** pass if the map applies and the relay path appears; fail if the relay breaks forwarding or becomes a SPOF.
- **Rollback:** detach the map and remove the relay VM.
- **Operational risk:** medium; adds complexity and a forwarding hop.

### 5. ars-poland inbound on `peer-nva2`
- **Purpose:** Try the same Poland route-map idea against hub2’s remote NVA peer.
- **Attachment point / direction:** `ars-poland` → inbound → `peer-nva2`.
- **Classification:** unsupported.
- **Prerequisite / topology change:** none; the peer remains cross-VNet.
- **Expected route effect:** none; attachment is rejected for the same locality reason as Scenario 1.
- **Safe test outline:** attempt attachment, capture failure, verify baseline ECMP returns after rollback.
- **Pass/fail evidence:** fail evidence is the same locality error.
- **Rollback:** none needed beyond clearing the attempted association.
- **Operational risk:** low.

### 6. Inject `0/0` to spokes
- **Purpose:** Try to use a route map to inject the default route into spoke peerings.
- **Attachment point / direction:** spoke peering.
- **Classification:** not a route-map function.
- **Prerequisite / topology change:** would need a per-spoke route-map attachment type, which does not exist.
- **Expected route effect:** none; spoke peerings are not valid route-map connections.
- **Safe test outline:** none; document the unsupported object model.
- **Pass/fail evidence:** fail by design.
- **Rollback:** none.
- **Operational risk:** none.

### 7. Replace UDRs with route maps
- **Purpose:** See whether route maps can replace spoke UDR determinism.
- **Attachment point / direction:** any.
- **Classification:** not a route-map function.
- **Prerequisite / topology change:** none.
- **Expected route effect:** none; UDR precedence wins over BGP policy.
- **Safe test outline:** compare effective routes with and without UDRs; the UDR remains authoritative.
- **Pass/fail evidence:** fail by design if the goal is to replace UDRs.
- **Rollback:** none.
- **Operational risk:** none, aside from confusion.

### 8. Summarization + AS-path compensation on hub outbound VPN GW
- **Purpose:** Reduce route noise and compensate with AS-path policy for on-prem preference.
- **Attachment point / direction:** `ars-hub1` / `ars-hub2` → outbound → VPN GW connection.
- **Classification:** supported but conditional.
- **Prerequisite / topology change:** a safe aggregation plan; current `10.31.0.0/24` and `10.32.0.0/24` do not summarize safely.
- **Expected route effect:** fewer prefixes on the VPN GW side, with AS-path still preserving hub1 preference.
- **Safe test outline:** only after a safe aggregate exists; compare pre/post VPN GW learned routes.
- **Pass/fail evidence:** pass only if the aggregate is correct and on-prem still prefers the intended hub; fail if the summary is too broad.
- **Rollback:** remove the summary rule and restore the original prefix list.
- **Operational risk:** medium; a bad summary can overexpose address space.

### 9. Community tagging on Poland spoke prefixes
- **Purpose:** Tag Poland-spoke routes so downstream policy can classify them.
- **Attachment point / direction:** `ars-hub1` → inbound → `peer-nva1`.
- **Classification:** supported/useful.
- **Prerequisite / topology change:** `ars-hub1` must support the route-map attachment; `ars-hub1` upgrade is required.
- **Expected route effect:** community metadata is added without changing prefix reachability.
- **Safe test outline:** apply the smallest possible tag rule to one test prefix and confirm the tag appears in learned routes.
- **Pass/fail evidence:** pass when only the tag changes; fail if reachability or unrelated prefixes change.
- **Rollback:** detach the map and re-read the baseline routes.
- **Operational risk:** low.

### 10. Filter on-prem route leakage into ARS
- **Purpose:** Block on-prem routes that should not enter the ARS control plane.
- **Attachment point / direction:** `ars-hub1` → inbound → VPN GW connection.
- **Classification:** supported/useful.
- **Prerequisite / topology change:** `ars-hub1` upgrade required.
- **Expected route effect:** unwanted on-prem prefixes disappear from ARS learned routes while valid routes remain.
- **Safe test outline:** deny one known leak prefix, verify it vanishes from ARS learned routes, and verify the intended prefixes stay visible.
- **Pass/fail evidence:** pass when the denylist matches only the leak; fail if valid routes are removed.
- **Rollback:** remove the deny rule and restore the baseline learned routes.
- **Operational risk:** medium; a bad denylist can remove needed control-plane reachability.

### 11. Control outbound VPN GW advertisements
- **Purpose:** Shape what the hub advertises to on-prem.
- **Attachment point / direction:** `ars-hub2` (and/or `ars-hub1`) → outbound → VPN GW connection.
- **Classification:** supported/useful.
- **Prerequisite / topology change:** `ars-hub2` upgrade required for hub2-side tests; hub1 upgrade for hub1-side tests.
- **Expected route effect:** selected prefixes are advertised, suppressed, or tagged before they leave Azure.
- **Safe test outline:** use one non-critical prefix and confirm on-prem learns exactly the expected subset.
- **Pass/fail evidence:** pass when the outbound advertisement set matches the rule; fail if extra prefixes leak.
- **Rollback:** clear the outbound map and re-check on-prem learned routes.
- **Operational risk:** medium; mistakes can hide routes from on-prem.

### 12. Hub1 denylist variant for a specific prefix class
- **Purpose:** Refine the inbound policy on hub1 with a narrower denylist.
- **Attachment point / direction:** `ars-hub1` → inbound → VPN GW connection.
- **Classification:** supported but conditional.
- **Prerequisite / topology change:** `ars-hub1` upgrade and a safe test prefix class.
- **Expected route effect:** the chosen prefix class disappears from ARS learned routes without affecting unrelated routes.
- **Safe test outline:** deny a single test prefix, confirm the change, then widen only if needed.
- **Pass/fail evidence:** pass if the denylist is surgical; fail if unrelated prefixes disappear.
- **Rollback:** remove the denylist rule.
- **Operational risk:** medium.

### 13. Hub2 outbound prepend / advertisement variant
- **Purpose:** Shape hub2 advertisements more aggressively for a specific downstream consumer.
- **Attachment point / direction:** `ars-hub2` → outbound → VPN GW connection.
- **Classification:** supported but conditional.
- **Prerequisite / topology change:** `ars-hub2` upgrade and a prefix set that can tolerate the extra prepend.
- **Expected route effect:** downstream learns the same prefix with different path preference.
- **Safe test outline:** prepend one test prefix only, confirm the path-length change, and confirm no other prefixes move.
- **Pass/fail evidence:** pass if only the test prefix changes; fail if the wrong prefix class changes.
- **Rollback:** remove the prepend rule.
- **Operational risk:** medium.

### 14. Filter unwanted on-prem prefixes inbound
- **Purpose:** Keep noisy or unsafe on-prem prefixes out of the hub control plane.
- **Attachment point / direction:** `ars-hub1` / `ars-hub2` → inbound → VPN GW connection.
- **Classification:** supported/useful.
- **Prerequisite / topology change:** both hub upgrades should be complete for full coverage.
- **Expected route effect:** the denied on-prem prefixes never appear in ARS learned routes.
- **Safe test outline:** start with one known harmless prefix, verify it is blocked, and verify the rest of the table is intact.
- **Pass/fail evidence:** pass if the denylist matches only the intended prefixes; fail if the wrong routes vanish.
- **Rollback:** remove the deny rule and re-check learned routes.
- **Operational risk:** medium.

### 15. Private-ASN prepend negative test
- **Purpose:** Confirm that route maps reject private or Azure-reserved ASNs in prepend actions.
- **Attachment point / direction:** `ars-hub1` → inbound → `peer-nva1`.
- **Classification:** supported/useful.
- **Prerequisite / topology change:** `ars-hub1` upgrade and a harmless test prefix.
- **Expected route effect:** none; the attempted prepend is rejected.
- **Safe test outline:** submit a rule that uses a private ASN, capture the validation failure, and confirm no route changes.
- **Pass/fail evidence:** pass when the platform rejects the private ASN; fail if it accepts it.
- **Rollback:** none needed; keep the test rule out of production.
- **Operational risk:** low.
