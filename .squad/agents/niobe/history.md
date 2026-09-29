**Archived entries:** see `history-archive.md`

# Project Context

- **Owner:** Jose Moreno
- **Project:** net-lab-builder
- **Role:** Validator and diagnostics owner

## Historical summaries

- **2026-07 to 2026-08 validation work:** built repeatable PASS/FAIL gates for vWAN, translator, Edge Actions, and Foundry labs, with emphasis on independent re-runs and evidence preservation.
- **General validator rule reinforced:** do not accept a fix claim based only on one layer of evidence when the scenario's published pass bar lives at another layer.

## Learnings

### 2026-09-29 - Independent re-validation must follow the real pass bar, not the fix team's intermediate bar

- I confirmed the entire earlier BGP fix chain was genuinely working before reopening S1. All three BGP sessions were stable and ARS had the expected `10.60.0.0/16` learning.
- Even so, the actual data-plane pass bar still failed, which exposed defects A, B, and C that the BGP-only rounds had not exercised.
- This is the right validator pattern for routing labs: re-check the control plane independently, then still run the real packet path end to end.

### 2026-09-29 - Current open item for next validation round

- A, B, C, D1, D2, E, F1, and F2 have now all been applied and individually verified by the implementer or designer for their intended hops.
- **S1 is still not pass-ready** because the authoritative CE-to-spoke-NVA ping remains down.
- When the next round starts, begin from Trinity's analysis of `labs/sap-rise-scoped-peering-fwaas/show-output/s1-spoke-reachability-fix-20260929T173839Z/` rather than re-running the old BGP checks first.
