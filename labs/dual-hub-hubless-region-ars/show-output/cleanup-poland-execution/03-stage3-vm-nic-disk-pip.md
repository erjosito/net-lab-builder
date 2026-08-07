# Stage 3 — Poland endpoint VM, extensions (auto), NIC, disk, PIP

**Timestamp:** 2026-08-05T19:20:48.1062290+02:00
**RG:** rg-dual-hub-hubless-region-ars-lab3d001

## Commands executed and results

1. `az vm delete -g <RG> -n vm-c1-ep --yes` -> exit 0 (VM was already deallocated at task start;
   deletion also removed `vm-c1-ep/enablevmAccess` and `vm-c1-ep/MDE.Linux` extensions automatically)
2. `az network nic delete -g <RG> -n nic-vm-c1-ep` -> exit 0
3. `az disk delete -g <RG> -n osdisk-vm-c1-ep --yes` -> exit 0
4. `az network public-ip delete -g <RG> -n pip-ars-poland` -> exit 0 (run only after ars-poland
   Route Server fully deleted in Stage 2, per dry-run ordering note)

## Verification

- `az vm list` -> 5 remain: vm-hub2-ep, vm-nva2, vm-onprem-ep, vm-hub1-ep, vm-nva1 (expected 5)
- `az network nic list` -> 5 remain, matching the same 5 VMs (expected)
- `az disk list` -> 5 remain, matching the same 5 VMs (expected)
- `az network public-ip list` -> 8 remain (was 9; pip-ars-poland removed), all hub1/hub2/onprem (expected)

Result: objects #10, #11, #12, #13 in cleanup-poland-dry-run.md §2a deleted successfully, plus
side-effect objects #18-19 (VM extensions) removed automatically with the VM. No deviation.
