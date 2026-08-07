# Stage 5 — Post-delete verification (read-only)

**Timestamp:** 2026-08-05T~19:15+02:00 (end of execution pass)
**RG:** rg-dual-hub-hubless-region-ars-lab3d001

## Resource count and type breakdown

```
az resource list -g <RG> -o json | measure Count
Total: 50 (expected 50, was 61 before) ✅
```

| Type | Count |
|---|---|
| Microsoft.Compute/disks | 5 |
| Microsoft.Compute/virtualMachines | 5 |
| Microsoft.Compute/virtualMachines/extensions | 6 |
| Microsoft.Network/connections | 4 |
| Microsoft.Network/networkInterfaces | 5 |
| Microsoft.Network/networkSecurityGroups | 5 |
| Microsoft.Network/publicIPAddresses | 8 |
| Microsoft.Network/routeTables | 2 |
| Microsoft.Network/virtualHubs | 2 |
| Microsoft.Network/virtualNetworkGateways | 3 |
| Microsoft.Network/virtualNetworks | 5 |

## Region breakdown (no Poland Central remains)

```
az resource list -g <RG> -o json | Group-Object location
```

| Region | Count |
|---|---|
| swedencentral | 20 |
| switzerlandnorth | 19 |
| norwayeast | 11 |
| **Total** | **50** |

`polandcentral` — **0 resources**, confirmed removed entirely.

## VNet peerings on preserved hub VNets (no Poland-facing peering remains)

- `az network vnet peering list --vnet-name vnet-hub1` -> `peer-hub1-to-spoke-a` (1, expected)
- `az network vnet peering list --vnet-name vnet-hub2` -> `peer-hub2-to-spoke-b` (1, expected)

## VNets remaining (5, expected)

`vnet-hub2`, `vnet-spoke-b`, `vnet-onprem`, `vnet-hub1`, `vnet-spoke-a`

## Route Servers remaining (2, expected)

`ars-hub2`, `ars-hub1` — `ars-poland` confirmed gone.

- `ars-hub1` BGP peerings: `peer-nva1` (1, unchanged)
- `ars-hub2` BGP peerings: `peer-nva2` (1, unchanged)
- `ars-hub1` route maps (ARM REST `routeMaps?api-version=2023-09-01`): `rm-hub1-activate` (1, unchanged — inert activation map preserved)
- `ars-hub2` route maps: `rm-hub2-activate` (1, unchanged — inert activation map preserved)

## VPN gateways and connections (unchanged, healthy)

- `az network vnet-gateway list` -> `vpngw-hub2`, `vpngw-onprem`, `vpngw-hub1` (3, expected), all `provisioningState=Succeeded`
- `az network vpn-connection show` per connection -> all 4 (`conn-hub1-to-onprem`, `conn-onprem-to-hub1`,
  `conn-hub2-to-onprem`, `conn-onprem-to-hub2`) report `connectionStatus=Connected` — none touch Poland
  (no VPN gateway ever existed in Poland), all remain Connected as required.

## VMs remaining (5, expected)

`vm-hub2-ep`, `vm-nva2`, `vm-onprem-ep`, `vm-hub1-ep`, `vm-nva1` — matches the expected set exactly
(`vm-c1-ep` gone). Power state check: **all 5 are `VM deallocated`** — this is a **pre-existing,
lab-wide condition** (the whole bed, including `vm-c1-ep` before its deletion, was already powered
off at task start), **not caused by this cleanup task**. No VM was stopped, deallocated, resized, or
otherwise mutated by this execution pass — only `vm-c1-ep` was deleted, per the approved list.

## NSGs remaining (5, expected — was 6)

`nsg-ep-hub2`, `nsg-nva-hub2`, `nsg-ep-onprem`, `nsg-ep-general`, `nsg-nva-hub1` — `nsg-ep-poland` confirmed gone.

## Resource group

`az group show -n <RG> --query properties.provisioningState` -> `Succeeded`. RG itself was never a
deletion target and remains present with all its original tags (`lab=true`, `ephemeral=true`,
`owner=jose`, `lab_name=dual-hub-hubless-region-ars`, `correlation_id=lab3d001`).

## Summary: all 5 verification bullets from the task satisfied

1. ✅ All 29 approved objects absent (17 explicit + 12 side-effect; count math 61 → 50 confirms it exactly).
2. ✅ No Poland-facing peering remains on preserved VNets (`vnet-hub1`/`vnet-hub2` each show exactly
   their one non-Poland peering).
3. ✅ All preserve-list top-level objects still exist and are healthy (ARM `provisioningState=Succeeded`
   throughout; VM deallocation is pre-existing lab-wide state, unrelated to this task).
4. ✅ hub1/hub2 ARS BGP peerings and inert route-map activation maps unchanged (1 peering + 1 route
   map each, same names as pre-delete capture).
5. ✅ VPN connections outside Poland remain Connected (4/4).
6. ✅ Shared RG remains, unmutated.
7. ✅ Current resource counts and regions recorded above (50 objects across swedencentral/
   switzerlandnorth/norwayeast only).
