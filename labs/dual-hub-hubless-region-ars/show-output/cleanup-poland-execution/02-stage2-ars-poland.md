# Stage 2 — ARS Poland BGP peerings and Route Server deletion

**Timestamp:** 2026-08-05T19:16:33.8200133+02:00
**RG:** rg-dual-hub-hubless-region-ars-lab3d001

## Commands executed and results

1. `az network routeserver peering delete -g <RG> --routeserver ars-poland -n peer-nva1 --yes` -> exit 0
2. `az network routeserver peering delete -g <RG> --routeserver ars-poland -n peer-nva2 --yes` -> exit 0
3. `az network routeserver delete -g <RG> -n ars-poland --yes` -> exit 0 (waited ~25 min for terminal state, consistent with manifest.md's "~10 min" estimate order of magnitude but longer in practice; command was NOT re-issued or interrupted while waiting)

## Verification

- `az network routeserver list` -> only `ars-hub1`, `ars-hub2` remain (2, expected)

Result: objects #7, #8, #9 in cleanup-poland-dry-run.md §2a deleted successfully, no deviation
except the longer-than-manifest-estimate wait time (documented, not a scope change).
