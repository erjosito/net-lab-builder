# Capture 05 — Azure Route Server BGP peerings (all three ARS instances)

**Captured by:** Tank · 2026-08-05T16:00:43+02:00
**Purpose:** Confirm ars-poland's BGP connections (delete scope) and that ars-hub1/ars-hub2's BGP
connections point only at their local NVA — never at Poland — so they are correctly excluded.
**Sanitization:** Subscription ID redacted to `<SUBSCRIPTION_ID>`.

## Command 1
```bash
az network routeserver peering list -g rg-dual-hub-hubless-region-ars-lab3d001 --routeserver ars-poland -o table
```
### Output
```
Name       PeerAsn    PeerIp     ProvisioningState    ResourceGroup
---------  ---------  ---------  -------------------  ---------------------------------------
peer-nva2  65002      10.20.1.4  Succeeded            rg-dual-hub-hubless-region-ars-lab3d001
peer-nva1  65001      10.10.1.4  Succeeded            rg-dual-hub-hubless-region-ars-lab3d001
```

## Command 2
```bash
az network routeserver peering list -g rg-dual-hub-hubless-region-ars-lab3d001 --routeserver ars-hub1 -o table
```
### Output
```
Name       PeerAsn    PeerIp     ProvisioningState    ResourceGroup
---------  ---------  ---------  -------------------  ---------------------------------------
peer-nva1  65001      10.10.1.4  Succeeded            rg-dual-hub-hubless-region-ars-lab3d001
```

## Command 3
```bash
az network routeserver peering list -g rg-dual-hub-hubless-region-ars-lab3d001 --routeserver ars-hub2 -o table
```
### Output
```
Name       PeerAsn    PeerIp     ProvisioningState    ResourceGroup
---------  ---------  ---------  -------------------  ---------------------------------------
peer-nva2  65002      10.20.1.4  Succeeded            rg-dual-hub-hubless-region-ars-lab3d001
```

**Finding:** ars-poland has exactly 2 BGP peerings (`peer-nva1`, `peer-nva2`) — both in delete
scope, both children of ars-poland. ars-hub1 and ars-hub2 each have exactly 1 BGP peering, to their
own local NVA only — **zero Poland references on hub1/hub2 ARS**. Confirms task item 4's exclusion
of hub1/hub2 Route Servers is safe: nothing on them needs to change.
