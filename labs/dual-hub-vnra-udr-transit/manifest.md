# Lab Card: dual-hub-vnra-udr-transit

> lab: dual-hub-vnra-udr-transit | correlation_id: vnra-c7e2a3f1 | stage: 1-v2 | authored_by: Tank | reviewed_by: Trinity (B1-B6 applied) | cost_guardrail_status: UNCLEAR -- VNRA pricing found; tier mapping unresolved; see Cost section

## Mechanism (one line)

Two hub VNets globally peered; one Azure managed `Microsoft.Network/virtualNetworkAppliances` (VNRA) in each hub's `VirtualNetworkApplianceSubnet`; four route tables chain spoke->VNRA1->VNRA2->spoke for symmetric east-west transit; key investigation: VNRA hardware routing is invisible to traceroute TTL probes (absence of hop proves managed VNRA vs VM NVA), and no user-accessible effective-route API exists for managed VNRA.

---

## Regions and Address Plan

| Role   | VNet Name     | Region        | Address Space | Subnet                          | CIDR         |
|--------|---------------|---------------|---------------|---------------------------------|--------------|
| Hub1   | `hub1-vnet`   | swedencentral | 10.1.0.0/16   | `VirtualNetworkApplianceSubnet` | 10.1.0.0/24  |
| Hub2   | `hub2-vnet`   | northeurope   | 10.2.0.0/16   | `VirtualNetworkApplianceSubnet` | 10.2.0.0/24  |
| Spoke1 | `spoke1-vnet` | swedencentral | 10.10.0.0/16  | `vm-subnet`                     | 10.10.1.0/24 |
| Spoke2 | `spoke2-vnet` | northeurope   | 10.20.0.0/16  | `vm-subnet`                     | 10.20.1.0/24 |

Subnet name `VirtualNetworkApplianceSubnet` is exact and case-sensitive; enforced by ARM.
VNRA1 private IP: **10.1.0.4** (ARM-assigned from hub1 VirtualNetworkApplianceSubnet)
VNRA2 private IP: **10.2.0.4** (ARM-assigned from hub2 VirtualNetworkApplianceSubnet)

---

## SKU Selection -- Test VMs Only (Phase-0 Preflight)

> B2ts_v2 preflight applies to **test VMs only**. VNRAs are managed resources with fixed bandwidth tiers (50/100/200 Gbps), not VM SKUs.

| Gate          | Region        | SKU              | Result                                                                                             |
|---------------|---------------|------------------|----------------------------------------------------------------------------------------------------|
| Catalog       | swedencentral | Standard_B2ts_v2 | PASS -- no restrictions                                                                            |
| Catalog       | northeurope   | Standard_B2ts_v2 | PASS -- restrictionType=Zone, blockedZones=[1,2]; Zone 3 free; non-zonal deploy valid              |
| Live capacity | swedencentral | Standard_B2ts_v2 | PASS -- validate provisioningState=Succeeded (correlationId: c86a4504-5207-4ce2-8f36-aea8eb5cade2) |
| Live capacity | northeurope   | Standard_B2ts_v2 | PASS -- validate provisioningState=Succeeded (correlationId: 58d95596-41e6-4b85-b818-aeb6df3f9e11) |

**Chosen SKU for test VMs: `Standard_B2ts_v2` (2 vCPU, 1 GiB RAM), non-zonal, both regions.**
Fallback: `Standard_B2ls_v2`. Validated via `--validate` dry-run on existing RG `rg-foundry-reserved-8d532edd` -- no resources created.

---

## VNRA Prerequisite / Quota Gates (read-only discovery -- 2026-08-19)

### Provider Registration

| Check | Result |
|-------|--------|
| `Microsoft.Network` registration state | **Registered** |
| `virtualNetworkAppliances` resource type present | **YES** |
| API version `2025-05-01` available | **YES** (confirmed: 2025-03-01 / 2025-05-01 / 2025-07-01 / 2025-09-01 / 2026-01-01) |
| swedencentral in resource type locations | **YES** (Sweden Central) |
| northeurope in resource type locations | **YES** (North Europe) |

### Existing VNRA Quota Probe (read-only az rest GET)

```
az rest --method GET \
  --url "https://management.azure.com/subscriptions/<REDACTED>/providers/Microsoft.Network/virtualNetworkAppliances?api-version=2025-05-01"
```

| Region        | Existing VNRAs | Limit | Room for 1 VNRA |
|---------------|----------------|-------|-----------------|
| swedencentral | 0              | 2     | **YES -- PASS** |
| northeurope   | 0              | 2     | **YES -- PASS** |

Both regions clear. The lab's two VNRAs (one per region) fit within subscription quota.

---

## Resource Inventory (20 top-level resources, 2 VMs)

All resources in one RG: `rg-dual-hub-vnra-udr-transit` (swedencentral)
Required tags on every resource: `lab=true`, `created_by=copilot-lab`, `correlation_id=vnra-c7e2a3f1`

| #  | Resource Type                                  | Name                                          | Region        |
|----|------------------------------------------------|-----------------------------------------------|---------------|
| 1  | Resource Group                                 | rg-dual-hub-vnra-udr-transit                  | swedencentral |
| 2  | VNet                                           | hub1-vnet (10.1.0.0/16)                       | swedencentral |
| 3  | VNet                                           | hub2-vnet (10.2.0.0/16)                       | northeurope   |
| 4  | VNet                                           | spoke1-vnet (10.10.0.0/16)                    | swedencentral |
| 5  | VNet                                           | spoke2-vnet (10.20.0.0/16)                    | northeurope   |
| 6  | Subnet                                         | hub1-vnet/VirtualNetworkApplianceSubnet /24   | swedencentral |
| 7  | Subnet                                         | hub2-vnet/VirtualNetworkApplianceSubnet /24   | northeurope   |
| 8  | Subnet                                         | spoke1-vnet/vm-subnet /24                     | swedencentral |
| 9  | Subnet                                         | spoke2-vnet/vm-subnet /24                     | northeurope   |
| 10 | VNet Peering (x2 objects)                      | hub1-vnet <-> spoke1-vnet                     | Regional      |
| 11 | VNet Peering (x2 objects)                      | hub2-vnet <-> spoke2-vnet                     | Regional      |
| 12 | VNet Peering (x2 objects)                      | hub1-vnet <-> hub2-vnet                       | Global        |
| 13 | Route Table                                    | rt-spoke1                                     | swedencentral |
| 14 | Route Table                                    | rt-spoke2                                     | northeurope   |
| 15 | Route Table                                    | rt-hub1-vnra                                  | swedencentral |
| 16 | Route Table                                    | rt-hub2-vnra                                  | northeurope   |
| 17 | **Microsoft.Network/virtualNetworkAppliances** | **vnra1 (10.1.0.4, 50 Gbps)**                 | **swedencentral** |
| 18 | **Microsoft.Network/virtualNetworkAppliances** | **vnra2 (10.2.0.4, 50 Gbps)**                 | **northeurope**   |
| 19 | VM + NIC + OSDisk (Standard_B2ts_v2, Std SSD) | test1-vm                                      | swedencentral |
| 20 | VM + NIC + OSDisk (Standard_B2ts_v2, Std SSD) | test2-vm                                      | northeurope   |

No gateways. No public IPs. No NSGs in baseline. No ARS. No VM NVAs.

VNRA resources have no user NIC, no OS, no cloud-init, no enableIPForwarding flag, no OS disk.

---

## VNet Peerings

| Peering                   | Scope    | allowVirtualNetworkAccess | allowForwardedTraffic | allowGatewayTransit | useRemoteGateways |
|---------------------------|----------|---------------------------|---------------------|---------------------|-------------------|
| hub1-vnet <-> spoke1-vnet | Regional | true (both ends)          | true (both ends)    | false               | false             |
| hub2-vnet <-> spoke2-vnet | Regional | true (both ends)          | true (both ends)    | false               | false             |
| hub1-vnet <-> hub2-vnet   | Global   | true (both ends)          | true (both ends)    | false               | false             |

`allowVirtualNetworkAccess=true` AND `allowForwardedTraffic=true` are **both required** on all six peering objects. Omitting either flag causes silent packet drop. `allowVirtualNetworkAccess` must be set explicitly — the Azure CLI does not default to `true` when the flag is absent.

---

## UDR Route Tables

| Route Table    | Attached Subnet                         | Prefix       | Next Hop Type    | Next Hop IP | Purpose                        |
|----------------|-----------------------------------------|--------------|------------------|-------------|--------------------------------|
| `rt-spoke1`    | spoke1-vnet/vm-subnet                   | 10.20.0.0/16 | VirtualAppliance | 10.1.0.4    | Spoke1 east-west -> VNRA1      |
| `rt-hub1-vnra` | hub1-vnet/VirtualNetworkApplianceSubnet | 10.20.0.0/16 | VirtualAppliance | 10.2.0.4    | VNRA1 cross-hub -> VNRA2 [E1]  |
| `rt-hub2-vnra` | hub2-vnet/VirtualNetworkApplianceSubnet | 10.10.0.0/16 | VirtualAppliance | 10.1.0.4    | VNRA2 return -> VNRA1 [E1]     |
| `rt-spoke2`    | spoke2-vnet/vm-subnet                   | 10.10.0.0/16 | VirtualAppliance | 10.2.0.4    | Spoke2 east-west -> VNRA2      |

[E1] Cross-VNRA chaining via UDR on VirtualNetworkApplianceSubnet to a cross-VNet IP across global
peering is analytically expected per docs but has no published Microsoft example as of 2026-08-19.

---

## Data Path: spoke1 -> spoke2

```
test1-vm (10.10.1.4)
  rt-spoke1: 10.20.0.0/16 -> VirtualAppliance -> 10.1.0.4
    VNRA1 (10.1.0.4) -- managed hardware; no OS; invisible to TTL probes
      rt-hub1-vnra: 10.20.0.0/16 -> VirtualAppliance -> 10.2.0.4  [E1]
      (hub1<->hub2 global peering, allowForwardedTraffic=true both ends)
        VNRA2 (10.2.0.4) -- managed hardware; no OS; invisible to TTL probes
          hub2 system route: 10.20.0.0/16 -> VNetPeering -> spoke2-vnet
            test2-vm (10.20.1.4)  [EXPECTED PASS, conditional on E1]
```

Return path is symmetric. Traceroute proof: VNRA IPs must NOT appear as traceroute hops.
Hardware forwarding is TTL-invisible. A visible VNRA hop indicates VM NVA, not managed VNRA.

---

## VNRA Creation Reference (no az network subcommand exists)

```bash
SUB=$(az account show --query id -o tsv)
RG=rg-dual-hub-vnra-udr-transit
API=2025-05-01

# Create VNRA1 (swedencentral)
az rest --method PUT \
  --url "https://management.azure.com/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.Network/virtualNetworkAppliances/vnra1?api-version=${API}" \
  --body '{
    "location": "swedencentral",
    "properties": {
      "subnet": {
        "id": "/subscriptions/'"${SUB}"'/resourceGroups/'"${RG}"'/providers/Microsoft.Network/virtualNetworks/hub1-vnet/subnets/VirtualNetworkApplianceSubnet"
      },
      "virtualNetworkApplianceSku": { "name": "VNRA", "scalingBandwidth": 50 }
    }
  }'

# Verify private IP (expect 10.1.0.4)
az rest --method GET \
  --url "https://management.azure.com/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.Network/virtualNetworkAppliances/vnra1?api-version=${API}" \
  | jq -r '.properties.ipConfigurations[] | select(.properties.primary==true) | .properties.privateIPAddress'
```

Repeat for vnra2: location=northeurope, hub2-vnet, vnra2, expected IP 10.2.0.4.
Terraform requires AzAPI provider; AzureRM does not support this resource type.

---

## Scenarios and Pass/Fail Criteria

### S1 -- Baseline Non-Transitivity

Deploy VNets + peerings only. No VNRAs, no route tables.

```bash
az vm run-command invoke -g rg-dual-hub-vnra-udr-transit -n test1-vm \
  --command-id RunShellScript --scripts "ping -c 4 -W 2 10.20.1.4; echo exit=$?"
```

Pass: 100% packet loss. Fail: any ping succeeds -> topology misconfiguration.

---

### S2 -- VNRA + UDR Transit + Managed-Resource Proof [E1]

After deploying vnra1, vnra2, and all four route tables.

```bash
az vm run-command invoke -g rg-dual-hub-vnra-udr-transit -n test1-vm \
  --command-id RunShellScript \
  --scripts "ping -c 4 10.20.1.4 && echo PASS || echo FAIL; traceroute -n -w 2 -m 10 10.20.1.4"

az vm run-command invoke -g rg-dual-hub-vnra-udr-transit -n test2-vm \
  --command-id RunShellScript \
  --scripts "ping -c 4 10.10.1.4 && echo PASS || echo FAIL; traceroute -n -w 2 -m 10 10.10.1.4"
```

Pass: 0% loss both directions. Traceroute shows no intermediate hop at 10.1.0.4 or 10.2.0.4
(hardware forwarding is TTL-invisible; absence-of-hop is definitive managed-VNRA proof).
Fail: loss > 0%; OR any VNRA IP appears as a traceroute hop; OR [E1] fallback triggered.

---

### S3 -- Effective Routes on Spoke VM NICs

```bash
az network nic show-effective-route-table \
  --name test1-vmVMNic -g rg-dual-hub-vnra-udr-transit \
  --query "value[?source=='User'].{prefix:addressPrefix[0],nh:nextHopIpAddress[0],state:state}" -o table

az network nic show-effective-route-table \
  --name test2-vmVMNic -g rg-dual-hub-vnra-udr-transit \
  --query "value[?source=='User'].{prefix:addressPrefix[0],nh:nextHopIpAddress[0],state:state}" -o table
```

Pass (test1-vm): 10.20.0.0/16 -> User/VirtualAppliance -> 10.1.0.4, Active.
Pass (test2-vm): 10.10.0.0/16 -> User/VirtualAppliance -> 10.2.0.4, Active.
Fail: UDR absent; Invalid state; unexpected transitive spoke route via system route.

---

### S4 -- VNRA Route Table + Network Watcher Proxy

No user NIC exists on managed VNRA. az network nic show-effective-route-table is NOT applicable.

```bash
# Configured UDR (not effective routes; system routes not included here)
az network route-table route list \
  --route-table-name rt-hub1-vnra -g rg-dual-hub-vnra-udr-transit -o table
# Expected: 10.20.0.0/16 / VirtualAppliance / 10.2.0.4

az network route-table route list \
  --route-table-name rt-hub2-vnra -g rg-dual-hub-vnra-udr-transit -o table
# Expected: 10.10.0.0/16 / VirtualAppliance / 10.1.0.4

# Network Watcher next-hop -- indirect proxy from test1-vm NIC, source-ip spoofed to VNRA1
az network watcher show-next-hop \
  --resource-group rg-dual-hub-vnra-udr-transit \
  --vm test1-vm --source-ip 10.1.0.4 --dest-ip 10.20.1.4 \
  --nic test1-vmVMNic
# Expected: nextHopType=VirtualAppliance, nextHopIpAddress=10.2.0.4
```

Pass: route entries correct; Network Watcher returns VA/10.2.0.4.
Limitation: reflects hub1 routing context via test1-vm NIC, not a direct view of VNRA1's forwarding table.

---

### S5 -- KEY INVESTIGATION: Subnet-Scope Effective Routes for VirtualNetworkApplianceSubnet

```bash
SUB=$(az account show --query id -o tsv)
RG=rg-dual-hub-vnra-udr-transit

# Probe A1: undocumented subnet effectiveRouteTable REST action (expect 404 or 405)
az rest --method post \
  --url "https://management.azure.com/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.Network/virtualNetworks/hub1-vnet/subnets/VirtualNetworkApplianceSubnet/effectiveRouteTable?api-version=2024-05-01"

# Probe A2: alternate action name
az rest --method post \
  --url "https://management.azure.com/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.Network/virtualNetworks/hub1-vnet/subnets/VirtualNetworkApplianceSubnet/listEffectiveRoutes?api-version=2024-05-01"

# Probe B: VNRA resource GET -- returns IP + provisioning state, NOT effective routes
az rest --method GET \
  --url "https://management.azure.com/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.Network/virtualNetworkAppliances/vnra1?api-version=2025-05-01"

# Probe C: Azure Monitor throughput metrics (primary observability for managed VNRA)
az monitor metrics list \
  --resource "/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.Network/virtualNetworkAppliances/vnra1" \
  --metric "BytesSent" "BytesReceived" --interval PT1M -o table
```

| Probe | Expected | Meaning |
|-------|----------|---------|
| A1/A2 HTTP status | 404 or 405 | No subnet-scope effective route API; NIC is only queryable unit |
| A1/A2 HTTP status | 202 | Undocumented feature; poll Location header and record output |
| B GET state | provisioningState=Succeeded | VNRA operational; IP confirmed |
| C Monitor bytes | Non-zero post-S2 | Built-in metrics active; no diagnostic config needed |

Pass: A1/A2 return 404/405 (gap confirmed); B returns Succeeded; C non-zero after S2 traffic.

---

## Observability Matrix

| Query type | Tool | Managed VNRA result |
|------------|------|---------------------|
| (a) Configured UDR table | az network route-table route list | YES |
| (b) Effective routes on NIC | az network nic show-effective-route-table | NO -- no user NIC |
| (c) Effective routes for managed resource | (no documented API) | NO -- as of 2026-08-19 |
| (d) Subnet-scope REST effective routes | Probe A1/A2 | UNKNOWN -- empirical (S5) |
| (e) Resource GET (IP + state) | az rest GET .../virtualNetworkAppliances/vnra1 | YES |
| (f) Azure Monitor throughput | az monitor metrics list BytesSent/Received | YES -- built-in |
| (g) Azure Monitor flows | az monitor metrics list InboundFlows/OutboundFlows | YES -- built-in |
| (h) Network Watcher next-hop | az network watcher show-next-hop (adjacent VM proxy) | Indirect only |
| (i) VNet Flow Logs on VNRA subnet | Flow log resource | NO -- not supported |
| (j) Per-flow 5-tuple logging | NSG / VNet flow logs on VNRA subnet | NO -- not available |

Production workaround: (a)+(e)+(f)+(g)+(h)+S2 end-to-end ping is the complete observability set.
Per-flow visibility requires flow logs on spoke vm-subnets, not VNRA subnet.

---

## Empirical Gates

| ID | Question | Pass criterion | Fail action |
|----|----------|----------------|-------------|
| E1 | Does UDR on VirtualNetworkApplianceSubnet steer VNRA1 forwarding to VNRA2 (10.2.0.4) across global peering? | S2 ping passes AND no VNRA IP in traceroute | Redesign: single VNRA per hub; spoke UDRs use peering system route directly |
| E2 | What HTTP status does POST .../VirtualNetworkApplianceSubnet/effectiveRouteTable return? | Document status + body (expect 404/405) | If 202: poll and record; compare with rt-hub1-vnra route list |
| E3 | Azure Monitor metrics non-zero post-S2 without diagnostic config? | 200 + non-zero BytesSent/Received | Investigate diagnostic settings requirement |

---

## Cost Estimate

**COST GUARDRAIL STATUS: UNCLEAR -- Jose approval required before deployment.**

| Resource | Qty | Unit price | Daily estimate |
|----------|-----|------------|----------------|
| Standard_B2ts_v2 VM (test VMs) | 2 | ~$0.013/hr | ~$0.63/day |
| Standard SSD OS disk 32 GB (test VMs) | 2 | ~$0.04/GB/mo x 32 GB | ~$0.09/day |
| VNet peering data transfer | -- | lab traffic ~= 0 | ~$0.00 |
| Route tables, NICs | -- | free | $0.00 |
| Microsoft.Network/virtualNetworkAppliances (50 Gbps) | 2 | UNKNOWN tier mapping | $32-$168/day |
| **Total** | | | **~$33-$170/day** |

Pricing evidence found (Azure Retail Prices API, product "Virtual Network Routing Appliance",
productId DZH318XZPG6Q, queried 2026-08-19):

| SKU Name | Meter | USD/hr |
|----------|-------|--------|
| Basic Appliance | Basic Appliance Unit | $0.675 |
| Basic Appliance | Basic Appliance Unit | $3.500 |
| Standard Appliance | Standard Appliance Standard Unit | $3.375 |
| Standard Appliance | Standard Appliance Standard Unit | $17.500 |

Dual price points per SKU name observed (same skuId, same meterName, type=Consumption).
The ARM spec uses virtualNetworkApplianceSku.scalingBandwidth: 50 (minimum 50 Gbps tier).
Mapping from scalingBandwidth to "Basic"/"Standard" Retail API SKU name is unconfirmed.

Best case (2 x $0.675/hr x 24h): ~$32/day VNRAs -> ~$33/day total -- under $50/day guardrail.
Worst case (2 x $3.50/hr x 24h): ~$168/day VNRAs -> ~$170/day total -- EXCEEDS guardrail.

Approval required: Jose must confirm acceptable tier and acknowledge cost uncertainty before
deployment. If VNRAs map to higher price points, a Phase-4 cost escalation is required.

---

## Deployment Order and Time Estimate

| Step | Resources | Duration |
|------|-----------|----------|
| 1 -- RG | rg-dual-hub-vnra-udr-transit | <1 min |
| 2 -- VNets + Subnets (parallel) | hub1-vnet, hub2-vnet, spoke1-vnet, spoke2-vnet | 1-2 min |
| 3 -- Route Tables + Routes (parallel) | rt-spoke1, rt-spoke2, rt-hub1-vnra, rt-hub2-vnra | 1 min |
| 4 -- VNet Peerings (parallel) | hub1<->spoke1, hub2<->spoke2, hub1<->hub2 | 1-2 min |
| 5 -- VNRAs (parallel) | vnra1 (swedencentral), vnra2 (northeurope) -- ARM async | 2-3 min |
| 6 -- Route Table Subnet Associations | Attach 4 route tables to 4 subnets | 1 min |
| 7 -- Test VMs (parallel) | test1-vm (swedencentral), test2-vm (northeurope) | 3-5 min |
| **Total** | | **~10-15 min** |

VNRA provisioning is an ARM async operation. Poll provisioningState via az rest GET before
proceeding to step 6.

---

## Cleanup Boundary

```bash
az group delete --name rg-dual-hub-vnra-udr-transit --yes --no-wait
```

Deletes all 20 top-level resources in one operation. Single RG; no cross-RG or subscription-scope
side-effects. No Key Vaults, no soft-delete resources. VNRAs deleted as part of RG deletion.

---

## Unresolved Approval Risks

| Risk | Severity | Resolution |
|------|----------|------------|
| Cost guardrail UNCLEAR -- pricing found but scalingBandwidth->price mapping unconfirmed | BLOCKER | Jose confirms via portal estimate or billing confirmation before deploy |
| E1 unproven -- cross-VNRA UDR chaining via global peering has no published Microsoft example | Medium | Accept empirical gate; E1 fail triggers defined fallback redesign |
| No effective-route API for managed VNRA (S5 gap) | Low / known | Document as lab finding; not a deployment blocker |
| IaC tooling gap -- no az network subcommand; AzureRM Terraform unsupported | Low / accepted | Use az rest for deployment; AzAPI for Terraform |