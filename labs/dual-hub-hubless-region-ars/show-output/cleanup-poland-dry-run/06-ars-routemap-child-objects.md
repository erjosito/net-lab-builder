# Capture 06 — ARS route-map child objects (cost-surcharge evidence + discrepancy note)

**Captured by:** Tank · 2026-08-05T16:00:43+02:00
**Purpose:** Check whether ars-poland currently carries a live route-map child object, for the cost
estimate in `cleanup-poland-dry-run.md`.
**Sanitization:** Subscription ID redacted to `<SUBSCRIPTION_ID>`.

## Command (repeated per Route Server, ARM REST, api-version 2024-10-01)
```bash
az rest --method GET \
  --url "https://management.azure.com/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-dual-hub-hubless-region-ars-lab3d001/providers/Microsoft.Network/virtualHubs/<ars-name>/routeMaps?api-version=2024-10-01" \
  --query "value[].{name:name, provisioningState:properties.provisioningState}" -o json
```

### ars-hub1
```json
[ { "name": "rm-hub1-activate", "provisioningState": "Succeeded" } ]
```

### ars-hub2
```json
[ { "name": "rm-hub2-activate", "provisioningState": "Succeeded" } ]
```

### ars-poland
```json
[]
```

**Discrepancy vs. `.squad/agents/tank/history.md` B3** ("current run-rate ... 3 × ≈$6/day route-map
surcharge, after `ars-poland`, `ars-hub1`, `ars-hub2` upgrades"): live ARM state shows **zero**
route-map child objects on ars-poland today, while ars-hub1/ars-hub2 each retain one inert
activation map. This is consistent with Tank's own note that the route-map **surcharge is billed
against the one-way virtualHub SKU upgrade**, not the presence of a route-map object (the object
from ars-poland's earlier Δ3/S4 test may have been removed after that test while the underlying
upgrade — and its billing implication — persisted). This capture does **not** resolve the
uncertainty; it is carried into the cost estimate as an explicit approximation, not a precise figure.
