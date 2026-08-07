# Command: az network routeserver peering list-learned-routes -g rg-dual-hub-hubless-region-ars-lab3d001 --routeserver ars-poland --name peer-nva1
# Timestamp: 2026-08-05T18:28:50.7204987+02:00

```json
{   "RouteServiceRole_IN_0": [],   "RouteServiceRole_IN_1": [] }
```

# Command: az network routeserver peering list-learned-routes -g rg-dual-hub-hubless-region-ars-lab3d001 --routeserver ars-poland --name peer-nva2

```json
{   "RouteServiceRole_IN_0": [],   "RouteServiceRole_IN_1": [] }
```

## Deviation note: vm-c1-ep is deallocated (powered off)

# Command: az vm get-instance-view -g rg-dual-hub-hubless-region-ars-lab3d001 -n vm-c1-ep --query "instanceView.statuses"

```json
[   {     "code": "ProvisioningState/succeeded",     "displayStatus": "Provisioning succeeded",     "level": "Info",     "time": "2026-08-04T23:50:57.9730981+00:00"   },   {     "code": "PowerState/deallocated",     "displayStatus": "VM deallocated",     "level": "Info"   } ]
```

**Deviation from dry-run Stage 0 assumption:** the dry-run's Stage-0 evidence-capture list included
an `az vm run-command invoke ... ping` reachability test and an effective-route-table dump for
`nic-vm-c1-ep`, implicitly assuming the VM is running. Live state check (this execution) shows
`vm-c1-ep` is **deallocated**, so:
- `az network nic show-effective-route-table` returns `NicMustBeAttachedToRunningVmToGetEffectiveRoutes`
  (captured verbatim in `04-vm-poweroff-deviation-and-skipped-captures.md`).
- The ping reachability test cannot run (no RunCommand on a deallocated VM).

This is **not** a scope/target discrepancy under the STOP conditions in the task (no new dependency,
no missing target, no unexpected replacement, no preserve-object selected) — `vm-c1-ep` is still the
exact named object on the approved delete list, still present, still targeted for deletion. A powered-off
VM does not block or change the deletion plan; it only means two read-only diagnostic captures are
unavailable. Proceeding per the approved list with this deviation documented.
