# Capture 02 — VNet peerings on hub1/hub2 (Sweden/Switzerland) that target Poland

**Captured by:** Tank · 2026-08-05T16:00:43+02:00
**Purpose:** Discover the nested/dependent peering objects that are NOT `location=polandcentral`
but must be removed because they point at Poland VNets — the exact case flagged in the task brief.
**Sanitization:** Subscription ID redacted to `<SUBSCRIPTION_ID>`.

## Command 1
```bash
az network vnet peering list -g rg-dual-hub-hubless-region-ars-lab3d001 --vnet-name vnet-hub1 \
  --query "[].{name:name, remoteVnet:remoteVirtualNetwork.id, state:peeringState, agt:allowGatewayTransit, urg:useRemoteGateways}" -o json
```
### Output (sanitized)
```json
[
  {
    "name": "peer-hub1-to-spoke-c2",
    "remoteVnet": "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-dual-hub-hubless-region-ars-lab3d001/providers/Microsoft.Network/virtualNetworks/vnet-spoke-c2",
    "state": "Connected", "agt": false, "urg": false
  },
  {
    "name": "peer-hub1-to-spoke-c1",
    "remoteVnet": "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-dual-hub-hubless-region-ars-lab3d001/providers/Microsoft.Network/virtualNetworks/vnet-spoke-c1",
    "state": "Connected", "agt": false, "urg": false
  },
  {
    "name": "peer-hub1-to-poland",
    "remoteVnet": "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-dual-hub-hubless-region-ars-lab3d001/providers/Microsoft.Network/virtualNetworks/vnet-poland-ars",
    "state": "Connected", "agt": false, "urg": false
  },
  {
    "name": "peer-hub1-to-spoke-a",
    "remoteVnet": "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-dual-hub-hubless-region-ars-lab3d001/providers/Microsoft.Network/virtualNetworks/vnet-spoke-a",
    "state": "Connected", "agt": true, "urg": false
  }
]
```

## Command 2
```bash
az network vnet peering list -g rg-dual-hub-hubless-region-ars-lab3d001 --vnet-name vnet-hub2 \
  --query "[].{name:name, remoteVnet:remoteVirtualNetwork.id, state:peeringState, agt:allowGatewayTransit, urg:useRemoteGateways}" -o json
```
### Output (sanitized)
```json
[
  {
    "name": "peer-hub2-to-spoke-c1",
    "remoteVnet": "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-dual-hub-hubless-region-ars-lab3d001/providers/Microsoft.Network/virtualNetworks/vnet-spoke-c1",
    "state": "Connected", "agt": false, "urg": false
  },
  {
    "name": "peer-hub2-to-spoke-c2",
    "remoteVnet": "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-dual-hub-hubless-region-ars-lab3d001/providers/Microsoft.Network/virtualNetworks/vnet-spoke-c2",
    "state": "Connected", "agt": false, "urg": false
  },
  {
    "name": "peer-hub2-to-poland",
    "remoteVnet": "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-dual-hub-hubless-region-ars-lab3d001/providers/Microsoft.Network/virtualNetworks/vnet-poland-ars",
    "state": "Connected", "agt": false, "urg": false
  },
  {
    "name": "peer-hub2-to-spoke-b",
    "remoteVnet": "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-dual-hub-hubless-region-ars-lab3d001/providers/Microsoft.Network/virtualNetworks/vnet-spoke-b",
    "state": "Connected", "agt": true, "urg": false
  }
]
```

**Finding:** vnet-hub1 (swedencentral) and vnet-hub2 (switzerlandnorth) each carry **3 Poland-pointing
peerings** (`*-to-spoke-c1`, `*-to-spoke-c2`, `*-to-poland`) that must be deleted even though the
parent VNets themselves are preserved. Each hub's remaining peering (`*-to-spoke-a` / `*-to-spoke-b`)
is out of Poland scope and is preserved untouched.
