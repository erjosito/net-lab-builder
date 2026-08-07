# Stage 1 — Remote-side Poland-facing peerings on preserved hub1/hub2 VNets

**Timestamp:** 2026-08-05T18:34:46.1397997+02:00
**RG:** rg-dual-hub-hubless-region-ars-lab3d001

## Commands executed (in order) and results

1. `az network vnet peering delete -g <RG> --vnet-name vnet-hub1 -n peer-hub1-to-poland` -> exit 0
2. `az network vnet peering delete -g <RG> --vnet-name vnet-hub1 -n peer-hub1-to-spoke-c1` -> exit 0
3. `az network vnet peering delete -g <RG> --vnet-name vnet-hub1 -n peer-hub1-to-spoke-c2` -> exit 0
4. `az network vnet peering delete -g <RG> --vnet-name vnet-hub2 -n peer-hub2-to-poland` -> exit 0
5. `az network vnet peering delete -g <RG> --vnet-name vnet-hub2 -n peer-hub2-to-spoke-c1` -> exit 0
6. `az network vnet peering delete -g <RG> --vnet-name vnet-hub2 -n peer-hub2-to-spoke-c2` -> exit 0

## Verification (az network vnet peering list)

- `vnet-hub1` remaining peerings: `peer-hub1-to-spoke-a` (1, expected)
- `vnet-hub2` remaining peerings: `peer-hub2-to-spoke-b` (1, expected)

Result: all 6 objects (#1-6 in cleanup-poland-dry-run.md §2a) deleted successfully, no deviation.
