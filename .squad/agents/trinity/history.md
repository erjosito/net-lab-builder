**Archived entries:** see `history-archive.md`

# Project Context

- **Owner:** Jose Moreno
- **Project:** net-lab-builder
- **Role:** Network SME and design owner

## Historical summaries

- **2026-08 dual-hub and Route Server work:** resolved gateway SKU, route-map, and topology questions; documented where Azure Route Server, VPN gateway, peering, and UDR behaviors actually differ from the first design assumptions.
- **2026-08 Foundry networking work:** corrected NSG, MCR, cleanup, and DNS guidance so deployment and teardown matched the real platform behavior.
- **Earlier SAP RISE design work:** locked subnet-scoped peering, separated S1 from S2, and captured the accepted deployment deviations needed for the lab harness.

## Learnings

### 2026-09-29 - Niobe's re-validation correctly reopened S1 after the BGP chain was already fixed

- The first five S1 defects were real and the BGP chain is still considered closed for its own scope.
- Niobe then proved the real pass bar still failed, which exposed data-plane defects A, B, and C: ARS branch-to-branch off, hub `ip_forward` not live, and no CE-side Azure-fabric route to the spoke.
- Design lesson worth keeping: in Azure, proving ARS learned a route is not enough. You still must prove gateway learning, guest forwarding state, and the harness-side Azure fabric route.

### 2026-09-29 - Hub-side residuals D1, D2, and E also exposed a tooling rule

- D1 and D2 were simple hub NSG gaps.
- E was the justified `bird.conf` reopen: export only `static_bgp` into the hub kernel table so the spoke supernet appears in Linux FIB without reintroducing ARS route poisoning.
- The failed retries were mostly an Azure run-command transport problem. For this lab, multiline guest scripts should now be written locally and invoked with `az vm run-command invoke --scripts @file`, with explicit post-change proof required before any apply is trusted.

### 2026-09-29 - Next pickup is the spoke-side residual after F1 and F2

- F1 and F2 were applied and verified present, but the authoritative CE probe to `10.60.0.4` still fails.
- The most important next-step artifact is `labs/sap-rise-scoped-peering-fwaas/show-output/s1-spoke-reachability-fix-20260929T173839Z/`.
- Start with the fallback `tcpdump` and `ip route` evidence from that folder before proposing another change.
