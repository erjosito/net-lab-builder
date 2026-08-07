# Route Maps Scenario Catalogue — Decision Inbox Note
**Author:** Trinity (Azure Network SME)
**Date:** 2026-08-05T08:37+02:00
**Requested by:** Jose Moreno
**Status:** Analysis only — no Azure or repo code changes

## Summary of Findings

15 route-map scenarios evaluated against the live dual-hub/hubless-region-ars lab.
Full analysis in session output (2026-08-05). Key results:

### Actionable / Supported + Useful
| # | Scenario | Map Location |
|---|---|---|
| 8 | Summarize set-C prefixes toward on-prem | ars-hub1/hub2 outbound VPN GW connection |
| 9 | Community tagging of set-C routes | ars-hub1 inbound NVA1 peer |
| 10 | Filter on-prem route leakage into ARS | ars-hub1 inbound VPN GW connection |
| 11 | Control outbound VPN GW advertisements | ars-hub1/hub2 outbound VPN GW connection |
| 14 | Filter unwanted on-prem prefixes inbound | ars-hub1/hub2 inbound VPN GW connection |
| 2 | Synthetic local peer in vnet-poland-ars | ars-poland inbound local VM peer |
| 15 | Private-ASN prohibition negative test | ars-hub1 inbound NVA1 peer |

### Blocked by Undocumented Locality Constraint
- Scenarios 1, 5: ars-poland cannot reference route maps for cross-VNet peers (NVA1/NVA2).
  Error: `HubBgpConnectionFromSpokeVnetCannotReferenceRouteMap`.
  **Not documented by Microsoft as of 2026-08-03.**

### Structural Non-Starters
- Scenario 3 (cross-hub): no BGP path exists — route maps cannot bridge topology gaps.
- Scenario 6 (inject 0/0 to spokes): spoke peerings are not a route-map connection type.
- Scenario 7 (replace UDRs): UDR > BGP precedence; route maps cannot substitute UDR determinism.

## Recommended Experiments (ranked)
1. Summarization + AS-path compensation on ars-hub1/hub2 outbound VPN GW (Scenario 8)
2. Inbound VPN GW filter to block on-prem GW subnets from ARS (Scenarios 10/14)
3. Synthetic local peer in vnet-poland-ars + route-map proof-of-concept (Scenario 2)
4. Community tagging on Poland spoke prefixes at ars-hub1/NVA1 inbound (Scenario 9)

## Decisions Needed from Jose Moreno
- [ ] Approve any of the above experiments?
- [ ] File undocumented locality constraint with Microsoft (support ticket / feedback)?
- [ ] Proceed with Scenario 2 (synthetic local peer) — requires one additional B2ts_v2 VM (~$0.26/day)?
