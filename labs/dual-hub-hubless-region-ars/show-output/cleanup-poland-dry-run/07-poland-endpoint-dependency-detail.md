# Capture 07 — Poland VM/NIC/disk/NSG/PIP dependency detail

**Captured by:** Tank · 2026-08-05T16:00:43+02:00
**Purpose:** Establish the exact dependency chain (what is attached to what) so the deletion order
in `cleanup-poland-dry-run.md` is provably safe, not assumed.
**Sanitization:** Subscription ID redacted to `<SUBSCRIPTION_ID>`.

## Command 1
```bash
az vm show -g rg-dual-hub-hubless-region-ars-lab3d001 -n vm-c1-ep \
  --query "{name:name, size:hardwareProfile.vmSize, nic:networkProfile.networkInterfaces[0].id, tags:tags}" -o json
```
### Output (sanitized)
```json
{
  "name": "vm-c1-ep",
  "size": "Standard_B2ts_v2",
  "nic": "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-dual-hub-hubless-region-ars-lab3d001/providers/Microsoft.Network/networkInterfaces/nic-vm-c1-ep",
  "tags": {
    "correlation_id": "lab3d001", "created_by": "copilot-lab", "ephemeral": "true",
    "lab": "true", "lab_name": "dual-hub-hubless-region-ars", "owner": "jose"
  }
}
```

## Command 2
```bash
az network nic show -g rg-dual-hub-hubless-region-ars-lab3d001 -n nic-vm-c1-ep \
  --query "{name:name, nsg:networkSecurityGroup.id, subnet:ipConfigurations[0].subnet.id}" -o json
```
### Output (sanitized)
```json
{
  "name": "nic-vm-c1-ep",
  "nsg": null,
  "subnet": "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-dual-hub-hubless-region-ars-lab3d001/providers/Microsoft.Network/virtualNetworks/vnet-spoke-c1/subnets/snet-workload"
}
```

## Command 3
```bash
az network nsg show -g rg-dual-hub-hubless-region-ars-lab3d001 -n nsg-ep-poland \
  --query "{name:name, subnets:[subnets[].id], nics:[networkInterfaces[].id]}" -o json
```
### Output (sanitized)
```json
{
  "name": "nsg-ep-poland",
  "nics": [null],
  "subnets": ["/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-dual-hub-hubless-region-ars-lab3d001/providers/Microsoft.Network/virtualNetworks/vnet-spoke-c1/subnets/snet-workload"]
}
```

## Command 4
```bash
az disk show -g rg-dual-hub-hubless-region-ars-lab3d001 -n osdisk-vm-c1-ep --query "{name:name, diskState:diskState}" -o json
```
### Output
```json
{ "name": "osdisk-vm-c1-ep", "diskState": "Reserved" }
```

## Command 5
```bash
az network public-ip show -g rg-dual-hub-hubless-region-ars-lab3d001 -n pip-ars-poland --query "{name:name, ipConfig:ipConfiguration.id}" -o json
```
### Output (sanitized)
```json
{
  "name": "pip-ars-poland",
  "ipConfig": "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-dual-hub-hubless-region-ars-lab3d001/providers/Microsoft.Network/virtualHubs/ars-poland/ipConfigurations/ipconfigRouteServer"
}
```

**Findings that shape the deletion order:**
1. `nic-vm-c1-ep` has **no NIC-level NSG** (`nsg: null`) — the NSG is attached at the **subnet**
   level (`vnet-spoke-c1/snet-workload`), not the NIC. This means `nsg-ep-poland` **cannot** be
   deleted until that subnet association is gone, i.e. **after** `vnet-spoke-c1` is deleted — not
   before it as a naive "NSG before VNet" ordering would assume.
2. `osdisk-vm-c1-ep` is `diskState: Reserved` (attached) — must delete the VM first, or the disk
   delete will fail.
3. `pip-ars-poland`'s only IP configuration is `ars-poland`'s own management-plane config — the PIP
   cannot be released until `ars-poland` itself is deleted.
4. No Poland-scoped `Microsoft.Network/routeTables` exists. `rt-spoke-a` and `rt-spoke-b` are the
   only 2 route tables in the RG and both are Sweden/Switzerland-scoped (spoke-a/spoke-b) — **out of
   Poland delete scope**, confirmed by `main.bicep` (spoke-c1/c2 rely on ARS-injected `0.0.0.0/0`,
   no UDR).
