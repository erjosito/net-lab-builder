# Cleanup Evidence: dual-hub-vnra-udr-transit

| Field | Value |
|-------|-------|
| **Timestamp (deletion started)** | 2026-08-20T12:41:17+02:00 |
| **Timestamp (deletion confirmed)** | 2026-08-20T12:49:11+02:00 |
| **Elapsed deletion time** | ~7 min 54 sec |
| **Authorized by** | Jose Moreno (explicit approval after 22-resource preview) |
| **Executed by** | Tank (deployment/cleanup engineer) |
| **Subscription** | Litware-MngEnvMCAP642473-jomore |
| **Target resource group** | rg-dual-hub-vnra-udr-transit |
| **Pre-delete resource count** | 22 |
| **External provider resources** | None (no ExpressRoute, no Megaport, no MCR) |

---

## Pre-Delete Inventory (22 Resources)

| Resource Name | Type | Location |
|---------------|------|----------|
| hub1-vnet | VirtualNetwork | swedencentral |
| hub2-vnet | VirtualNetwork | northeurope |
| spoke1-vnet | VirtualNetwork | swedencentral |
| spoke2-vnet | VirtualNetwork | northeurope |
| rt-spoke1 | RouteTable | swedencentral |
| rt-spoke2 | RouteTable | northeurope |
| rt-hub1-vnra | RouteTable | swedencentral |
| rt-hub2-vnra | RouteTable | northeurope |
| vnra1 | virtualNetworkAppliances | swedencentral |
| vnra2 | virtualNetworkAppliances | northeurope |
| test1-vmVMNic | NetworkInterface | swedencentral |
| test1-vm | VirtualMachine | swedencentral |
| test1-vm_OsDisk_1_[ID-REDACTED] | Disk | swedencentral |
| test2-vmVMNic | NetworkInterface | northeurope |
| test2-vm | VirtualMachine | northeurope |
| test2-vm_OsDisk_1_[ID-REDACTED] | Disk | northeurope |
| spoke2-vnet-vm-subnet-nsg-northeurope | NetworkSecurityGroup | northeurope |
| spoke1-vnet-vm-subnet-nsg-swedencentral | NetworkSecurityGroup | swedencentral |
| hub2-vnet-VirtualNetworkApplianceSubnet-nsg-northeurope | NetworkSecurityGroup | northeurope |
| hub1-vnet-VirtualNetworkApplianceSubnet-nsg-swedencentral | NetworkSecurityGroup | swedencentral |
| test1-vm/MDE.Linux | VirtualMachineExtension | swedencentral |
| test2-vm/MDE.Linux | VirtualMachineExtension | northeurope |

---

## Deletion Command (IDs redacted)

```bash
az group delete -n rg-dual-hub-vnra-udr-transit --yes --no-wait
# Bounded polling: az group exists -n rg-dual-hub-vnra-udr-transit
# Interval: 30 s | Max wait: 30 min | Actual: ~8 min
```

---

## Final Verification

| Check | Result |
|-------|--------|
| `az group exists -n rg-dual-hub-vnra-udr-transit` | **false** |
| Subscription resource count with resourceGroup == target | **0** |
| Tagged straggler scan (correlation_id: vnra-c7e2a3f1, lab: dual-hub-vnra-udr-transit) | **0 resources** |
| External provider resources (ExpressRoute / Megaport) | **None -- not part of this lab** |

---

## Scope Confirmation

Only `rg-dual-hub-vnra-udr-transit` was deleted. No tag-based or broad deletion commands were used. No other resource groups were touched. No Megaport, MCR, or ExpressRoute resources existed in this lab.

---

## Notes

- The 4 auto-created NSGs and 2 MDE.Linux extensions (Defender for Cloud auto-enrollment) were within the resource group and deleted as part of group deletion.
- VNRA deletion (managed hardware appliances) completed within the ~8-minute window, consistent with Azure VNRA deprovisioning behavior.
- Lab correlation_id `vnra-c7e2a3f1` -- no resources tagged with this ID exist in the subscription post-deletion.
