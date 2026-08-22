# Preflight Evidence: dual-hub-vnra-udr-transit

> Generated: 2026-08-19T12:42:00+02:00 | correlation_id: vnra-c7e2a3f1

## Probe: swedencentral -- B-series v2 catalog

Command:
```
az vm list-skus -l swedencentral --resource-type virtualMachines
  --query "[?starts_with(name, 'Standard_B') && contains(name, '_v2')].{...}" -o table
```

Result: Standard_B2ts_v2 listed with NO restrictions (null restrictionType, null reasonCode).

Gate: CATALOG PASS

---

## Probe: northeurope -- B2ts_v2 zone restriction detail

Command:
```
az vm list-skus -l northeurope --resource-type virtualMachines
  --query "[?name=='Standard_B2ts_v2'].{name,zones,restrictionType,blockedZones,reasonCode}" -o json
```

Result:
```json
[{
  "name": "Standard_B2ts_v2",
  "zones": ["3","2","1"],
  "restrictionType": "Zone",
  "blockedZones": ["2","1"],
  "reasonCode": "NotAvailableForSubscription"
}]
```

Interpretation: Zone 1 and Zone 2 blocked for this subscription. Zone 3 free. Non-zonal deployment (no --zone arg) is valid -- Azure auto-places in an available zone. Per charter: restrictionType=Zone with partial zone block is NOT a region block. SKU is available.

Gate: CATALOG PASS (non-zonal deploy)

---

## Probe: swedencentral -- live capacity validation

Command:
```
az vm create -g rg-foundry-reserved-8d532edd -n preflight-probe-vnra -l swedencentral
  --image Ubuntu2204 --size Standard_B2ts_v2 --admin-username azureuser
  --generate-ssh-keys --validate
```

Result: provisioningState=Succeeded
Correlation ID: c86a4504-5207-4ce2-8f36-aea8eb5cade2
Timestamp: 2026-08-19T10:39:02.665052+00:00

Note: --validate is a dry-run; no resources created. Used existing lab RG rg-foundry-reserved-8d532edd.

Gate: LIVE CAPACITY PASS

---

## Probe: northeurope -- live capacity validation

Command:
```
az vm create -g rg-foundry-reserved-8d532edd -n preflight-probe-vnra-ne -l northeurope
  --image Ubuntu2204 --size Standard_B2ts_v2 --admin-username azureuser
  --generate-ssh-keys --validate
```

Result: provisioningState=Succeeded
Correlation ID: 58d95596-41e6-4b85-b818-aeb6df3f9e11
Timestamp: 2026-08-19T10:41:09.440608+00:00

Note: --validate is a dry-run; no resources created. Used existing lab RG rg-foundry-reserved-8d532edd (swedencentral); RG location != VM location is valid for --validate.

Gate: LIVE CAPACITY PASS

---

## Summary

| Gate          | Region        | SKU              | Status |
|---------------|---------------|------------------|--------|
| Catalog       | swedencentral | Standard_B2ts_v2 | PASS   |
| Catalog       | northeurope   | Standard_B2ts_v2 | PASS   |
| Live capacity | swedencentral | Standard_B2ts_v2 | PASS   |
| Live capacity | northeurope   | Standard_B2ts_v2 | PASS   |

All four gates PASSED. SKU locked: Standard_B2ts_v2, non-zonal, both regions.


---

## VNRA Prerequisite Discovery (read-only -- 2026-08-19, Tank v2 revision)

> All probes below are read-only (az rest GET, az provider show, public REST API).
> No provider registration, no resource creation, no subscription IDs in committed artifacts.

### Probe: Microsoft.Network provider state

Command:
```
az provider show --namespace Microsoft.Network --query "{registrationState:registrationState}"
```

Result: registrationState=Registered

Gate: PROVIDER PASS

---

### Probe: virtualNetworkAppliances resource type + API versions

Command:
```
az provider show --namespace Microsoft.Network \
  --query "resourceTypes[?resourceType=='virtualNetworkAppliances'].{apiVersions:apiVersions,locations:locations}"
```

Result: Resource type present. API versions available:
  2025-03-01, 2025-05-01, 2025-07-01, 2025-09-01, 2026-01-01

API version 2025-05-01 (required per Trinity design.md): CONFIRMED AVAILABLE

Supported locations (relevant): Sweden Central (swedencentral), North Europe (northeurope)

Gate: API VERSION PASS

---

### Probe: Existing VNRAs by region (subscription quota check)

Command:
```
az rest --method GET \
  --url "https://management.azure.com/subscriptions/<REDACTED>/providers/Microsoft.Network/virtualNetworkAppliances?api-version=2025-05-01"
```

Result:
  Total VNRAs in subscription: 0
  VNRAs in swedencentral: 0 (limit 2/sub/region)
  VNRAs in northeurope:   0 (limit 2/sub/region)

Lab requires 1 VNRA in each region. Quota available in both.

Gate: QUOTA PASS (swedencentral: 0/2 used; northeurope: 0/2 used)

---

### Probe: VNRA Pricing (Azure Retail Prices API -- public, no auth required)

Command:
```
GET https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview
  &$filter=contains(productName,'Virtual Network Routing Appliance')
```

Result: 4 items returned, product "Virtual Network Routing Appliance" (productId: DZH318XZPG6Q)

| SKU Name | Meter | USD/hr | Unit |
|----------|-------|--------|------|
| Basic Appliance | Basic Appliance Unit | $0.675 | 1 Hour |
| Basic Appliance | Basic Appliance Unit | $3.500 | 1 Hour |
| Standard Appliance | Standard Appliance Standard Unit | $3.375 | 1 Hour |
| Standard Appliance | Standard Appliance Standard Unit | $17.500 | 1 Hour |

Note: Two price points per SKU name, same skuId, same meterName, both type=Consumption.
Likely distinct per-region rows aggregated under "Global" armRegionName.
The ARM API uses virtualNetworkApplianceSku: { name: "VNRA", scalingBandwidth: 50 }.
Mapping from scalingBandwidth=50 to Retail API SKU name (Basic/Standard) is unconfirmed.

Gate: PRICING FOUND -- TIER MAPPING UNCLEAR

---

## Updated Summary

| Gate                   | Region        | Resource              | Status |
|------------------------|---------------|-----------------------|--------|
| Catalog (VM SKU)       | swedencentral | Standard_B2ts_v2      | PASS   |
| Catalog (VM SKU)       | northeurope   | Standard_B2ts_v2      | PASS   |
| Live capacity (VM SKU) | swedencentral | Standard_B2ts_v2      | PASS   |
| Live capacity (VM SKU) | northeurope   | Standard_B2ts_v2      | PASS   |
| Provider registration  | --            | Microsoft.Network     | PASS   |
| API version 2025-05-01 | --            | virtualNetworkAppliances | PASS |
| Location support       | swedencentral | virtualNetworkAppliances | PASS |
| Location support       | northeurope   | virtualNetworkAppliances | PASS |
| Quota                  | swedencentral | VNRA (0/2 used)       | PASS   |
| Quota                  | northeurope   | VNRA (0/2 used)       | PASS   |
| Pricing                | Global        | VNRA pricing meter    | FOUND -- tier mapping unresolved |

All hard gates PASS. Cost guardrail remains UNCLEAR pending tier->price mapping confirmation.
Jose approval required before deployment.