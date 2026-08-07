# Stage 4 / 4b — Poland VNets (with nested peerings) and nsg-ep-poland

**Timestamp:** 2026-08-05T19:23:55.4678352+02:00
**RG:** rg-dual-hub-hubless-region-ars-lab3d001

## Commands executed and results

1. `az network vnet delete -g <RG> -n vnet-spoke-c1` -> exit 0 (also removed subnet
   `snet-workload` and its NSG association to `nsg-ep-poland`, plus 3 local peerings
   peer-spoke-c1-to-hub1/hub2/poland)
2. `az network vnet delete -g <RG> -n vnet-spoke-c2` -> exit 0 (also removed 3 local peerings
   peer-spoke-c2-to-hub1/hub2/poland)
3. `az network vnet delete -g <RG> -n vnet-poland-ars` -> exit 0 (also removed 4 local peerings
   peer-poland-to-hub1/hub2/spoke-c1/spoke-c2)
4. `az network nsg delete -g <RG> -n nsg-ep-poland` -> exit 0 (run AFTER Stage 4 per the
   dry-run's live-evidence ordering correction — NSG was subnet-associated, not NIC-associated;
   deleting the VNet first removed the association so the NSG delete succeeded cleanly)

## Verification

- `az network vnet list` -> 5 remain: vnet-hub2, vnet-spoke-b, vnet-onprem, vnet-hub1, vnet-spoke-a (expected 5)
- `az network nsg list` -> 5 remain: nsg-ep-hub2, nsg-nva-hub2, nsg-ep-onprem, nsg-ep-general, nsg-nva-hub1 (expected 5, was 6)

Result: objects #14, #15, #16, #17 in cleanup-poland-dry-run.md §2a deleted successfully, plus
side-effect objects #20-29 (10 nested VNet peerings) removed automatically with their parent VNets.
No deviation, no reordering required.

## All 29 approved objects — final tally

17 explicit + 12 side-effect = 29 total, all confirmed removed across Stages 1-4b. See
`show-output/cleanup-poland-execution/post/` for the full post-delete verification pass.
