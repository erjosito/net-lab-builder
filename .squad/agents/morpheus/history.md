**Archived entries:** see `history-archive.md`

# Project Context

- **Owner:** Jose Moreno
- **Project:** net-lab-builder
- **Role:** Lead and orchestrator

## Historical summaries

- **2026-08 Edge Actions and Foundry labs:** locked design scope, corrected deployment assumptions, and documented platform constraints without changing live Azure resources.
- **2026-08 dual-hub Route Server labs:** locked multi-region route-policy topology, cost posture, and failure-injection strategy, then captured follow-up user-story guidance for route-map placement.
- **Prior SAP RISE setup work:** locked the subnet-scoped peering topology, the S1/S2 comparison model, and the accepted deployment deviations needed to get the lab running.

## Learnings

### 2026-09-29 - SAP RISE S1 scope stayed stable while the debugging target moved from BGP to data plane

- The Stage 1 lab card stayed intact through all debugging. No one had to widen peering scope, abandon subnet peering, or reframe S2.
- Tank's live deployment deviations still matter operationally: the CE is an Azure VM in its own VNet, the Megaport PoP is Frankfurt, and the lab is operated entirely through `az vm run-command`.
- The main orchestration lesson is that a "BGP stable" handoff is not the same as an end-to-end pass. Niobe's independent re-validation correctly forced the team to continue until the actual CE-to-spoke path was proven.

### 2026-09-29 - End-of-day status for S1

- Defects A, B, C, D1, D2, E, F1, and F2 were all found and applied in sequence.
- A/B/C and D1/D2/E are confirmed working for their intended hops. The inline Azure run-command quoting issue is also considered closed because the team standardized on `az vm run-command invoke --scripts @file`.
- **Open next-session item:** CE to spoke-NVA reachability still fails. Trinity should start from `labs/sap-rise-scoped-peering-fwaas/show-output/s1-spoke-reachability-fix-20260929T173839Z/` before authoring any new fix.
