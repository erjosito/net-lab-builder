# Capture 03 — VNet peerings on the Poland-side VNets themselves

**Captured by:** Tank · 2026-08-05T16:00:43+02:00
**Purpose:** Enumerate the peering objects hosted on `vnet-poland-ars`, `vnet-spoke-c1`,
`vnet-spoke-c2` — these are removed automatically when their parent VNet is deleted, but are listed
here individually for the delete-count audit.
**Sanitization:** Subscription ID redacted to `<SUBSCRIPTION_ID>`.

## Command 1
```bash
az network vnet peering list -g rg-dual-hub-hubless-region-ars-lab3d001 --vnet-name vnet-poland-ars -o table
```
### Output
```
Name                       PeeringState    RemoteVnetName
-------------------------  --------------  ---------------
peer-poland-to-hub1        Connected       vnet-hub1
peer-poland-to-hub2        Connected       vnet-hub2
peer-poland-to-spoke-c1    Connected       vnet-spoke-c1
peer-poland-to-spoke-c2    Connected       vnet-spoke-c2
```

## Command 2
```bash
az network vnet peering list -g rg-dual-hub-hubless-region-ars-lab3d001 --vnet-name vnet-spoke-c1 -o table
```
### Output
```
Name                     PeeringState    RemoteVnetName
-----------------------  --------------  ---------------
peer-spoke-c1-to-hub1    Connected       vnet-hub1
peer-spoke-c1-to-hub2    Connected       vnet-hub2
peer-spoke-c1-to-poland  Connected       vnet-poland-ars
```

## Command 3
```bash
az network vnet peering list -g rg-dual-hub-hubless-region-ars-lab3d001 --vnet-name vnet-spoke-c2 -o table
```
### Output
```
Name                     PeeringState    RemoteVnetName
-----------------------  --------------  ---------------
peer-spoke-c2-to-hub1    Connected       vnet-hub1
peer-spoke-c2-to-hub2    Connected       vnet-hub2
peer-spoke-c2-to-poland  Connected       vnet-poland-ars
```

**Finding:** 10 peering objects live on the 3 Poland-side VNets (4 + 3 + 3). All 10 are removed as
a side effect of deleting their parent VNet — no separate delete command is issued for these (doing
so would be redundant with the VNet delete and does not change the dependency-safety of the plan).
