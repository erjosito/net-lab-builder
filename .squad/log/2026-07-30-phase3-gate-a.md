# Session Log — Phase 3 Gate A Validation

**Date:** 2026-07-30  
**Topic:** Phase 3 Gate A (Firewall Deployed, RI Deferred)  
**Agent:** Niobe (Lab Validator)

## Summary

Niobe validated Phase 3 Gate A state on vwan-routemap-summarization lab. Firewalls deployed to hub-eu1 and hub-eu2; Routing Intent NOT enabled per Jose's explicit direction.

**Outcome:** CONDITIONAL PASS ⚠️

- **hub-eu2:** PASS — 6/6 summaries confirmed on live BIRD RIB, zero /24 leaks, BGP Established
- **hub-eu1:** INCONCLUSIVE — Control-plane identical to hub-eu2, but nva1 stuck extension prevents L2 measurement

## Key Decisions Merged

Niobe's Gate A verdict added to decisions.md. Firewall deployment (Tank) and Routing Intent design (Trinity) decisions also documented.

## Blocking Issue

nva1 run-command extension terminally stuck (409/Conflict). Requires VM rebuild (az vm redeploy or delete+recreate) to unblock hub-eu1 L2 measurement for full Gate A PASS.

**Documented in Tank's history.md:** Action item to rebuild nva1 + add systemd service for XFRM persistence across deallocation.

## Tool Limitation Discovered

`az network vhub route-map get-outbound-routes` non-functional (HTTP 404, empty response). L2 BIRD RIB is authoritative fallback for all future gates. Documented in lessons-learned.md and validation.md.

## Next Steps

1. Tank rebuilds nva1 (or Jose accepts hub-eu2 PASS, enables RI on hub-eu2 first)
2. Niobe re-runs hub-eu1 L2 measurement (if Option A)
3. Enable Routing Intent sequentially per Trinity's gates (Gate B, Gate C)
