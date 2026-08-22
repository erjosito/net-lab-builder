# Deploy Log: dual-hub-vnra-udr-transit

> correlation_id: vnra-c7e2a3f1 | deployed_by: Tank (Copilot IaC agent) | date: 2026-08-19
> updated: 2026-08-19 (D4 peering fix applied by Coordinator; deploy.ps1 corrected by Tank)

## Status: COMPLETE -- ALL RESOURCES SUCCEEDED + PEERING FLAGS CORRECTED (D4)

| | |
|---|---|
| RG | rg-dual-hub-vnra-udr-transit (swedencentral) |
| Elapsed | ~88 min wall-clock (sequential CLI, ARM latency ~1 min/resource) |
| VNRA1 | vnra1 -- swedencentral -- 10.1.0.4 -- Succeeded |
| VNRA2 | vnra2 -- northeurope -- 10.2.0.4 -- Succeeded |
| test1-vm | 10.10.1.4 -- swedencentral -- Succeeded |
| test2-vm | 10.20.1.4 -- northeurope -- Succeeded |

---

## Resources Created (20 in RG + RG itself)

| Type | Name | Region | State |
|------|------|--------|-------|
| Resource Group | rg-dual-hub-vnra-udr-transit | swedencentral | Succeeded |
| VNet | hub1-vnet (10.1.0.0/16) | swedencentral | Succeeded |
| VNet | hub2-vnet (10.2.0.0/16) | northeurope | Succeeded |
| VNet | spoke1-vnet (10.10.0.0/16) | swedencentral | Succeeded |
| VNet | spoke2-vnet (10.20.0.0/16) | northeurope | Succeeded |
| Route Table | rt-spoke1 | swedencentral | Succeeded |
| Route Table | rt-spoke2 | northeurope | Succeeded |
| Route Table | rt-hub1-vnra | swedencentral | Succeeded |
| Route Table | rt-hub2-vnra | northeurope | Succeeded |
| **VirtualNetworkAppliances** | **vnra1** | **swedencentral** | **Succeeded** |
| **VirtualNetworkAppliances** | **vnra2** | **northeurope** | **Succeeded** |
| NIC | test1-vmVMNic | swedencentral | Succeeded |
| NIC | test2-vmVMNic | northeurope | Succeeded |
| VM | test1-vm (Standard_B2ts_v2) | swedencentral | Succeeded |
| VM | test2-vm (Standard_B2ts_v2) | northeurope | Succeeded |
| OS Disk | test1-vm_OsDisk_1_... (32GB StandardSSD) | swedencentral | Succeeded |
| OS Disk | test2-vm_OsDisk_1_... (32GB StandardSSD) | northeurope | Succeeded |
| NSG* | spoke1-vnet-vm-subnet-nsg-swedencentral | swedencentral | Auto-created |
| NSG* | spoke2-vnet-vm-subnet-nsg-northeurope | northeurope | Auto-created |
| NSG* | hub1-vnet-VirtualNetworkApplianceSubnet-nsg-swedencentral | swedencentral | Auto-created |
| NSG* | hub2-vnet-VirtualNetworkApplianceSubnet-nsg-northeurope | northeurope | Auto-created |

*\* NSGs were auto-created (see Deviations section below)

---

## Private IPs (confirmed)

| Resource | IP | Subnet |
|---|---|---|
| vnra1 | 10.1.0.4 | hub1-vnet/VirtualNetworkApplianceSubnet |
| vnra2 | 10.2.0.4 | hub2-vnet/VirtualNetworkApplianceSubnet |
| test1-vm | 10.10.1.4 | spoke1-vnet/vm-subnet |
| test2-vm | 10.20.1.4 | spoke2-vnet/vm-subnet |

---

## Route Table Associations (verified)

| Route Table | Subnet | Status |
|---|---|---|
| rt-spoke1 | spoke1-vnet/vm-subnet | ASSOCIATED |
| rt-spoke2 | spoke2-vnet/vm-subnet | ASSOCIATED |
| rt-hub1-vnra | hub1-vnet/VirtualNetworkApplianceSubnet | ASSOCIATED |
| rt-hub2-vnra | hub2-vnet/VirtualNetworkApplianceSubnet | ASSOCIATED |

---

## VNRA API Discovery

The ARM body schema (2025-05-01) uses `properties.bandwidthInGbps` (string) + `properties.subnet.id`.  
The design.md referenced `virtualNetworkApplianceSku` (incorrect for GA API).  
Correct body:
```json
{
  "location": "swedencentral",
  "tags": { "lab": "true", "created_by": "copilot-lab", "correlation_id": "vnra-c7e2a3f1" },
  "properties": {
    "bandwidthInGbps": "50",
    "subnet": { "id": "..." }
  }
}
```

---

## VNRA Pricing (Retail Prices API, queried 2026-08-19)

The ARM `bandwidthInGbps=50` maps to pricing at the Retail Prices API.
Pricing found (productId: DZH318XZPG6Q):

| SKU Name | USD/hr |
|---|---|
| Basic Appliance | $0.675 or $3.50 |
| Standard Appliance | $3.375 or $17.50 |

Exact tier mapping from `bandwidthInGbps=50` to Basic/Standard remains unconfirmed.
Best case: ~$33/day. Worst case: ~$170/day. Jose authorized deployment under this uncertainty.

---

## Deviations from Design

### D1: Auto-created NSGs (4 total)

**What happened:** `az network nic create` auto-creates a default NSG on the NIC's subnet when `--network-security-group` is omitted. The VNRA provisioning created NSGs on both `VirtualNetworkApplianceSubnet` subnets as part of managed-resource setup.

**Impact assessment:** All 4 NSGs have **no custom rules** (only Azure default rules). Default rules allow all `VirtualNetwork` tag traffic inbound and outbound. This tag includes peered VNet prefixes. East-west transit traffic (10.10.x.x <-> 10.20.x.x) is within VirtualNetwork scope.

**Lab impact:** LOW. Default NSGs should not block S2 ICMP/traceroute or S3 effective-route validation. VNRA subnet NSGs are Azure-managed.

**Fix for rerun:** Add `--network-security-group ""` to `az network nic create` in deploy.ps1 to prevent spoke NSG creation.

### D2: S1 test window missed

S1 (baseline non-transitivity, no route tables) requires testing BEFORE route table subnet associations (Step 6). The script proceeds through Steps 1-7 without pause. S1 was not tested in this run.

**Niobe action:** To test S1, temporarily detach rt-spoke1 and rt-spoke2 from vm-subnets, run ping, re-attach.

### D3: ARM field name change (preview -> GA)

Design.md documented `virtualNetworkApplianceSku.scalingBandwidth` (preview field). GA API (2025-05-01) uses `properties.bandwidthInGbps` (string). Updated deploy.ps1 accordingly. Schema confirmed from REST API docs.

---

### D4: allowVirtualNetworkAccess=false on all six peerings (root cause: missing CLI flag)

**Root cause:** `az network vnet peering create` was called with `--allow-forwarded-traffic` but WITHOUT `--allow-vnet-access`. On this tenant/CLI version, omitting `--allow-vnet-access` causes `allowVirtualNetworkAccess` to default to `false`. All six peering objects were created with `allowVirtualNetworkAccess=false`, which silently drops all cross-VNet traffic — ICMP and data plane both — even when `allowForwardedTraffic=true` and route tables are correctly configured. Result: 100% packet loss and zero VNRA metrics during the initial validation run.

**Live correction (Coordinator, 2026-08-19T18:51+02:00):** All six peerings updated via `az network vnet peering update --set allowVirtualNetworkAccess=true` while the lab was live. Peerings immediately converged to `Connected/FullyInSync`.

**Verified peering state after correction:**
All 6 peerings confirmed `allowVirtualNetworkAccess=true`, `allowForwardedTraffic=true`, `peeringState=Connected`, `peeringSyncLevel=FullyInSync`.
Evidence: `show-output/validation/retry-20260819T185118+0200/10-peering-access-correction.json`, `11-peering-access-verified.json`

**deploy.ps1 fix (Tank, 2026-08-19):**
- `--allow-vnet-access` added to `az network vnet peering create` (Step 4).
- Idempotent correction block added: on re-run, if a peering exists with either flag `false`, the script runs `az network vnet peering update --set allowVirtualNetworkAccess=true allowForwardedTraffic=true` before continuing.
- Step 10 added: post-deploy peering assertions that `throw` if any of the 6 peerings has `allowVirtualNetworkAccess != true`, `allowForwardedTraffic != true`, `peeringState != Connected`, or `peeringSyncLevel != FullyInSync`.

---

## Post-Fix Connectivity Results (2026-08-19T18:51+02:00)

| Test | Packets | Loss | avg RTT | Evidence |
|------|---------|------|---------|----------|
| test1-vm (10.10.1.4) -> test2-vm (10.20.1.4) | 10/10 | 0% | 33.094 ms | `retry-20260819T185118+0200/12-after-fix-test1-to-test2.json` |
| test2-vm (10.20.1.4) -> test1-vm (10.10.1.4) | 10/10 | 0% | 31.372 ms | `retry-20260819T185118+0200/13-after-fix-test2-to-test1.json` |

Tracepath from each VM reaches the remote destination in **one visible hop** (TTL=64 preserved) — confirming managed VNRA hardware forwarding is TTL-invisible, consistent with design expectation.

---

## Artifacts

| File | Content |
|---|---|
| `show-output/deployment/01-rg-create.json` | RG creation output |
| `show-output/deployment/02-vnets.json` | VNet list |
| `show-output/deployment/03-route-tables.json` | Route tables + routes |
| `show-output/deployment/04-peerings.json` | hub1 peering list |
| `show-output/deployment/05-vnra1.json` | VNRA1 GET (sanitized) |
| `show-output/deployment/05-vnra2.json` | VNRA2 GET (sanitized) |
| `show-output/deployment/07-test1-vm-create.json` | VM1 create output |
| `show-output/deployment/07-test2-vm-create.json` | VM2 create output |
| `show-output/deployment/09-resource-list.json` | Full RG resource list |
| `show-output/deployment/09-test1-nic.json` | test1-vm NIC + IP |
| `show-output/deployment/09-test2-nic.json` | test2-vm NIC + IP |
| `show-output/deployment/09-routes-final.json` | Final route table state |
| `show-output/deployment/deploy-run.log` | Full timestamped run log |

---

## Smoke Check Results

| Check | Result |
|---|---|
| test1-vm provisioningState | Succeeded |
| test2-vm provisioningState | Succeeded |
| vnra1 provisioningState | Succeeded |
| vnra2 provisioningState | Succeeded |
| rt-spoke1 associated to spoke1-vnet/vm-subnet | OK |
| rt-spoke2 associated to spoke2-vnet/vm-subnet | OK |
| rt-hub1-vnra associated to hub1-vnet/VirtualNetworkApplianceSubnet | OK |
| rt-hub2-vnra associated to hub2-vnet/VirtualNetworkApplianceSubnet | OK |

**Next: Niobe runs S1-S5 validation scenarios.**

---

## Blockers for Niobe

1. **S1 window missed** -- to test baseline non-transitivity, temporarily detach rt-spoke1 and rt-spoke2, run ping, re-attach.
2. **Auto-created NSGs** -- 4 NSGs present, no custom rules. May need to detach spoke NSGs if they interfere with S2; unlikely with default rules.
3. **E1 empirical gate** -- cross-VNRA UDR chaining (S2) unproven at lab creation time. Expected pass.
