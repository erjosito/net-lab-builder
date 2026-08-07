# Capture 08 — Pre-change resource-count baseline (for post-change mutation check)

**Captured by:** Tank · 2026-08-05T16:00:43+02:00
**Purpose:** Record the exact live resource count/state before this dry-run investigation so it can
be compared against the same query taken after, proving zero mutation occurred.
**Sanitization:** Subscription ID redacted to `<SUBSCRIPTION_ID>`.

## Command
```bash
az resource list -g rg-dual-hub-hubless-region-ars-lab3d001 --query "length(@)"
az resource list -g rg-dual-hub-hubless-region-ars-lab3d001 --query "[].type" -o tsv | sort | uniq -c
```

### Output — BEFORE (start of this task)
```
Total top-level resources: 61
  6  Microsoft.Compute/disks
  6  Microsoft.Compute/virtualMachines
  8  Microsoft.Compute/virtualMachines/extensions
  4  Microsoft.Network/connections
  6  Microsoft.Network/networkInterfaces
  6  Microsoft.Network/networkSecurityGroups
  9  Microsoft.Network/publicIPAddresses
  2  Microsoft.Network/routeTables
  3  Microsoft.Network/virtualHubs
  3  Microsoft.Network/virtualNetworkGateways
  8  Microsoft.Network/virtualNetworks
```

### Output — AFTER (end of this task, post-report-writing)
```
Total top-level resources: 61
  6  Microsoft.Compute/disks
  6  Microsoft.Compute/virtualMachines
  8  Microsoft.Compute/virtualMachines/extensions
  4  Microsoft.Network/connections
  6  Microsoft.Network/networkInterfaces
  6  Microsoft.Network/networkSecurityGroups
  9  Microsoft.Network/publicIPAddresses
  2  Microsoft.Network/routeTables
  3  Microsoft.Network/virtualHubs
  3  Microsoft.Network/virtualNetworkGateways
  8  Microsoft.Network/virtualNetworks
```

**Result: IDENTICAL.** No resource created, deleted, updated, stopped, resized, or disassociated by
this task. All 20 VNet peering objects (verified individually in captures 02-04) and all 3 ARS BGP
peerings/10 route-map objects (captures 05-06) were also re-verified unchanged. Only read (`show`,
`list`) and `az rest --method GET` commands were issued throughout this task.
