# Capture 04 — Preserved-side peerings (spoke-a, spoke-b, on-prem) — proof of exclusion

**Captured by:** Tank · 2026-08-05T16:00:43+02:00
**Purpose:** Confirm set-A/set-B spokes and on-prem carry zero Poland-pointing peerings, so no
in-scope object is hidden on the excluded side.
**Sanitization:** Subscription ID redacted to `<SUBSCRIPTION_ID>`.

## Command 1
```bash
az network vnet peering list -g rg-dual-hub-hubless-region-ars-lab3d001 --vnet-name vnet-spoke-a -o table
```
### Output
```
Name                   PeeringState    RemoteVnetName
---------------------  --------------  ---------------
peer-spoke-a-to-hub1   Connected       vnet-hub1
```

## Command 2
```bash
az network vnet peering list -g rg-dual-hub-hubless-region-ars-lab3d001 --vnet-name vnet-spoke-b -o table
```
### Output
```
Name                   PeeringState    RemoteVnetName
---------------------  --------------  ---------------
peer-spoke-b-to-hub2   Connected       vnet-hub2
```

## Command 3
```bash
az network vnet peering list -g rg-dual-hub-hubless-region-ars-lab3d001 --vnet-name vnet-onprem -o table
```
### Output
```
(empty — vnet-onprem has no VNet peerings; it connects via VPN Gateway only)
```

**Finding:** No Poland reference anywhere on the preserved side. `vnet-spoke-a` / `vnet-spoke-b`
each retain exactly 1 peering (to their own hub), unaffected by the Poland cleanup. `vnet-onprem` has
zero VNet peerings (VPN-only), also unaffected.
