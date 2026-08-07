# Capture 01 — Poland Central resource inventory (read-only)

**Captured by:** Tank · 2026-08-05T16:00:43+02:00
**Purpose:** Enumerate every resource whose `location == polandcentral` in the shared RG.
**Sanitization:** Subscription ID redacted to `<SUBSCRIPTION_ID>`.

## Command
```bash
az resource list -g rg-dual-hub-hubless-region-ars-lab3d001 \
  --query "[?location=='polandcentral'].{name:name, type:type, provisioningState:provisioningState}" \
  -o table
```

### Output
```
name                     type                                           provisioningState
-----------------------  ---------------------------------------------  -------------------
osdisk-vm-c1-ep          Microsoft.Compute/disks                        Succeeded
vm-c1-ep                 Microsoft.Compute/virtualMachines              Succeeded
vm-c1-ep/enablevmAccess  Microsoft.Compute/virtualMachines/extensions   Succeeded
vm-c1-ep/MDE.Linux       Microsoft.Compute/virtualMachines/extensions   Succeeded
nic-vm-c1-ep             Microsoft.Network/networkInterfaces            Succeeded
nsg-ep-poland            Microsoft.Network/networkSecurityGroups        Succeeded
pip-ars-poland           Microsoft.Network/publicIPAddresses            Succeeded
ars-poland               Microsoft.Network/virtualHubs                  Succeeded
vnet-poland-ars          Microsoft.Network/virtualNetworks              Succeeded
vnet-spoke-c1            Microsoft.Network/virtualNetworks              Succeeded
vnet-spoke-c2            Microsoft.Network/virtualNetworks              Succeeded
```

**Count:** 11 top-level resources located in `polandcentral`. Matches expected scope from
`manifest.md` §1 (vnet-poland-ars, vnet-spoke-c1, vnet-spoke-c2, ars-poland, pip-ars-poland,
vm-c1-ep + its NIC/disk/NSG). No unexpected Poland-located resource found; no expected resource
missing. VNet peerings are child objects and are NOT listed by `az resource list` — see captures
02-05 for those.
