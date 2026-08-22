# Network Design: dual-hub-vnra-udr-transit

> Produced by: Trinity | Ref: manifest.md (vnra-c7e2a3f1) | Date: 2026-08-19
> Sources: https://learn.microsoft.com/azure/virtual-network/virtual-network-routing-appliance-overview
>          https://learn.microsoft.com/azure/virtual-network/virtual-network-routing-appliance-create (GA 2026-08-04)
>          https://blog.cloudtrooper.net/2026/03/07/what-is-the-azure-virtual-network-routing-appliance/

---

## Manifest reviewer verdict: REJECT

Blocking reasons (B1-B6) in `.squad/decisions/inbox/trinity-dual-hub-vnra-review.md`.
This document is the corrected specification a replacement manifest must match.

---

## 1. Authoritative VNRA Resource Shape

The user intends the **Azure managed Virtual Network Routing Appliance** -- a top-level Azure
resource backed by purpose-built SDN hardware (AMD DPU / Azure Sirius). It is **not** a Linux VM.

| Property | Managed VNRA | VM NVA (manifest D1) |
|---|---|---|
| Resource type | `Microsoft.Network/virtualNetworkAppliances` | `Microsoft.Compute/virtualMachines` |
| OS / kernel | None (managed hardware) | Ubuntu 22.04 |
| NIC | None (no user NIC) | VM NIC with `enableIPForwarding=true` |
| OS ip_forward | N/A | `net.ipv4.ip_forward=1` (cloud-init) |
| cloud-init | N/A | Required |
| OS disk | None | Standard SSD 32 GB |
| Bandwidth tiers | 50 / 100 / 200 Gbps | Limited by VM SKU |
| GA date | 2026-08-04 | N/A |
| Max per sub/region | 2 | Subscription vCPU quota |
| Pricing | Not published | ~$0.013/hr (B2ts_v2) |
| VNet flow logs | Not supported | Supported |
| Per-flow logging | Not available | Via NSG/VNet flow logs |
| Traceroute visibility | Invisible (hardware forwarding) | Visible as hop |
| ILB in front | Not supported (drops traffic) | Supported |
| Terraform provider | AzAPI only | AzureRM |
| Internet egress | Not supported (private only) | Supported with SNAT |

Key implication: `enableIPForwarding`, cloud-init, OS disks, and
`az network nic show-effective-route-table` do NOT apply to managed VNRAs.

---

## 2. Prerequisites

| Requirement | Value | Notes |
|---|---|---|
| Subnet name (exact) | `VirtualNetworkApplianceSubnet` | Case-sensitive; enforced by ARM |
| Subnet minimum size | Not documented; /28 minimum recommended | 5 Azure-reserved + VNRA IPs |
| Subnet dedication | VNRA-only in this subnet | Managed resource exclusivity |
| VNet peering `allowForwardedTraffic` | `true` on ALL transit peerings | "IP forwarding on relevant peerings" (troubleshoot docs) |
| NIC IP forwarding flag | N/A | No user NIC exists |
| Quota check | Max 2 VNRA per subscription per region | Pre-deploy probe required |
| REST API version | `2025-05-01` | No `az network routing-appliance` CLI subcommand exists |
| Terraform provider | AzAPI | AzureRM does not support VNRA |

---

## 3. Address Plan

Preserved from manifest (no changes required).

| Role   | VNet Name     | Region        | Address Space | Subnet                          | CIDR         |
|--------|---------------|---------------|---------------|---------------------------------|--------------|
| Hub1   | `hub1-vnet`   | swedencentral | 10.1.0.0/16   | `VirtualNetworkApplianceSubnet` | 10.1.0.0/24  |
| Hub2   | `hub2-vnet`   | northeurope   | 10.2.0.0/16   | `VirtualNetworkApplianceSubnet` | 10.2.0.0/24  |
| Spoke1 | `spoke1-vnet` | swedencentral | 10.10.0.0/16  | `vm-subnet`                     | 10.10.1.0/24 |
| Spoke2 | `spoke2-vnet` | northeurope   | 10.20.0.0/16  | `vm-subnet`                     | 10.20.1.0/24 |

VNRA1 private IP: **10.1.0.4** (ARM-assigned from hub1 VirtualNetworkApplianceSubnet)
VNRA2 private IP: **10.2.0.4** (ARM-assigned from hub2 VirtualNetworkApplianceSubnet)

---

## 4. VNet Peerings

| Peering | Scope | allowVirtualNetworkAccess | allowForwardedTraffic | allowGatewayTransit | useRemoteGateways |
|---|---|---|---|---|---|
| hub1-vnet <-> spoke1-vnet | Regional | `true` both ends | `true` both ends | `false` | `false` |
| hub2-vnet <-> spoke2-vnet | Regional | `true` both ends | `true` both ends | `false` | `false` |
| hub1-vnet <-> hub2-vnet | Global | `true` both ends | `true` both ends | `false` | `false` |

`allowVirtualNetworkAccess=true` AND `allowForwardedTraffic=true` mandatory on all six peering objects. Missing from any leg = silent drop. The Azure CLI `az network vnet peering create` does NOT default `allowVirtualNetworkAccess` to `true` when `--allow-vnet-access` is absent; this flag must be passed explicitly.

---

## 5. UDR Tables

| Route Table | Attached Subnet | Prefix | Next Hop Type | Next Hop IP | Purpose |
|---|---|---|---|---|---|
| `rt-spoke1` | spoke1-vnet/vm-subnet | 10.20.0.0/16 | VirtualAppliance | 10.1.0.4 | Spoke1 east-west to VNRA1 |
| `rt-hub1-vnra` | hub1-vnet/VirtualNetworkApplianceSubnet | 10.20.0.0/16 | VirtualAppliance | 10.2.0.4 | VNRA1 cross-hub to VNRA2 [E1] |
| `rt-hub2-vnra` | hub2-vnet/VirtualNetworkApplianceSubnet | 10.10.0.0/16 | VirtualAppliance | 10.1.0.4 | VNRA2 return to VNRA1 [E1] |
| `rt-spoke2` | spoke2-vnet/vm-subnet | 10.10.0.0/16 | VirtualAppliance | 10.2.0.4 | Spoke2 east-west to VNRA2 |

[E1] = Empirical gate; see Section 10. UDR next-hop type for managed VNRA: `VirtualAppliance` + private IP,
identical to VM NVA syntax. Docs state VNRA "provides native support for user-defined routes."
Cross-hub chaining (VNRA1 subnet UDR -> VNRA2 IP via global peering) is analytically expected
but not in any published example as of 2026-08-19.

---

## 6. Data Path Analysis

### Forward: test1-vm (10.10.1.4) -> test2-vm (10.20.1.4)

```
test1-vm
  rt-spoke1: 10.20.0.0/16 -> VirtualAppliance -> 10.1.0.4
    VNRA1 (10.1.0.4, hub1) -- managed hardware, no OS
      rt-hub1-vnra: 10.20.0.0/16 -> VirtualAppliance -> 10.2.0.4  [E1]
      (hub1<->hub2 global peering, allowForwardedTraffic=true)
        VNRA2 (10.2.0.4, hub2) -- managed hardware, no OS
          hub2 system route: 10.20.0.0/16 -> VNetPeering -> spoke2-vnet
            test2-vm (10.20.1.4)  EXPECTED PASS [E1]
```

Return path symmetric: rt-spoke2 -> VNRA2 -> rt-hub2-vnra -> VNRA1 -> hub1 system -> spoke1.

Constraint checklist:
1. allowForwardedTraffic=true all three peerings: YES
2. NIC IP forwarding: N/A for managed VNRA (remove from IaC)
3. OS ip_forward / cloud-init: N/A for managed VNRA (remove from IaC)
4. VirtualAppliance next-hop to cross-VNet IP via global peering: valid (VNet peering docs)
5. ILB not in front of VNRA: confirmed (docs say not supported)
6. Internet egress not via VNRA: no internet UDR (private only)

---

## 7. VNRA Creation Reference

### REST (az rest) -- required; no az network VNRA subcommand exists

```bash
SUB=$(az account show --query id -o tsv)
RG=rg-dual-hub-vnra-udr-transit
API=2025-05-01

# Create VNRA1
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

# Confirm private IP (expect 10.1.0.4)
az rest --method GET \
  --url "https://management.azure.com/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.Network/virtualNetworkAppliances/vnra1?api-version=${API}" \
  | jq -r '.properties.ipConfigurations[] | select(.properties.primary==true) | .properties.privateIPAddress'
```

Request body shape must be validated against the 2025-05-01 ARM spec before deployment.
Reference: https://github.com/erjosito/vnra (Jose's own preview lab code).

### PowerShell (Az.Network module, GA as of 2026-08-04)

```powershell
$subnet = Get-AzVirtualNetworkSubnetConfig -Name "VirtualNetworkApplianceSubnet" `
  -VirtualNetwork (Get-AzVirtualNetwork -Name "hub1-vnet" -ResourceGroupName $RG)
New-AzVirtualNetworkAppliance -Name "vnra1" -ResourceGroupName $RG `
  -Location "swedencentral" -SubnetId $subnet.Id -Bandwidth "50"
```

### Terraform (AzAPI provider -- AzureRM does not support VNRA)

```hcl
resource "azapi_resource" "vnra1" {
  type      = "Microsoft.Network/virtualNetworkAppliances@2025-05-01"
  name      = "vnra1"
  location  = "swedencentral"
  parent_id = azurerm_resource_group.lab.id
  body = jsonencode({
    properties = {
      subnet = { id = azurerm_subnet.hub1_vnra_subnet.id }
      virtualNetworkApplianceSku = { name = "VNRA", scalingBandwidth = 50 }
    }
  })
}
```

---

## 8. NSG Design

Baseline: no NSG on any subnet. Omit to avoid masking failures during S1/S2.

If NSG is added to VirtualNetworkApplianceSubnet (optional):

| Priority | Direction | Source | Dest | Protocol | Action | Purpose |
|---|---|---|---|---|---|---|
| 100 | Inbound | VirtualNetwork | VirtualNetwork | Any | Allow | Transit inbound |
| 200 | Inbound | AzureLoadBalancer | Any | Any | Allow | Health probes |
| 4096 | Inbound | Any | Any | Any | Deny | Default deny |
| 100 | Outbound | VirtualNetwork | VirtualNetwork | Any | Allow | Transit outbound |
| 4096 | Outbound | Any | Any | Any | Deny | Default deny |

Docs note: service endpoints/tunneling through VNRA require NSG with VirtualNetwork
inbound and outbound plus destination service tag on the appliance subnet.

---

## 9. Resource Inventory (corrected)

Total VM count: **2** (test VMs only). VNRA = managed resources, NOT VMs.

| # | Resource Type | Name | Region |
|---|---|---|---|
| 1 | Resource Group | rg-dual-hub-vnra-udr-transit | swedencentral |
| 2 | VNet | hub1-vnet (10.1.0.0/16) | swedencentral |
| 3 | VNet | hub2-vnet (10.2.0.0/16) | northeurope |
| 4 | VNet | spoke1-vnet (10.10.0.0/16) | swedencentral |
| 5 | VNet | spoke2-vnet (10.20.0.0/16) | northeurope |
| 6 | Subnet | hub1-vnet/VirtualNetworkApplianceSubnet 10.1.0.0/24 | swedencentral |
| 7 | Subnet | hub2-vnet/VirtualNetworkApplianceSubnet 10.2.0.0/24 | northeurope |
| 8 | Subnet | spoke1-vnet/vm-subnet 10.10.1.0/24 | swedencentral |
| 9 | Subnet | spoke2-vnet/vm-subnet 10.20.1.0/24 | northeurope |
| 10 | VNet Peering (x2) | hub1-vnet <-> spoke1-vnet | Regional |
| 11 | VNet Peering (x2) | hub2-vnet <-> spoke2-vnet | Regional |
| 12 | VNet Peering (x2) | hub1-vnet <-> hub2-vnet | Global |
| 13 | Route Table | rt-spoke1 | swedencentral |
| 14 | Route Table | rt-spoke2 | northeurope |
| 15 | Route Table | rt-hub1-vnra | swedencentral |
| 16 | Route Table | rt-hub2-vnra | northeurope |
| **17** | **Microsoft.Network/virtualNetworkAppliances** | **vnra1 (10.1.0.4)** | **swedencentral** |
| **18** | **Microsoft.Network/virtualNetworkAppliances** | **vnra2 (10.2.0.4)** | **northeurope** |
| 19 | VM + NIC + OSDisk | test1-vm (Standard_B2ts_v2) | swedencentral |
| 20 | VM + NIC + OSDisk | test2-vm (Standard_B2ts_v2) | northeurope |

Removed from manifest: vnra1-vm, vnra2-vm (Ubuntu VMs with NIC + OSDisk + cloud-init).

---

## 10. Cost Estimate

| Resource | Qty | Unit | Daily |
|---|---|---|---|
| Standard_B2ts_v2 (test VMs) | 2 | ~$0.013/hr | ~$0.63/day |
| Standard SSD OS disk (test VMs) | 2 | ~$0.04/GB-mo x 32 GB | ~$0.09/day |
| VNRA managed resource (50 Gbps) | 2 | Pricing not published | UNKNOWN |

Cost guardrail: UNCLEAR. Manifest declared CLEAR (~$1.50/day) based on 4x B2ts_v2 VMs --
wrong for managed VNRAs. VNRA pricing not on Microsoft Learn overview page (hardware-tier
service). Portal pricing estimate or Retail Pricing API probe required before declaring CLEAR.

---

## 11. Scenarios

### S1 -- Baseline Non-Transitivity

Deploy VNets + peerings only. No VNRA, no route tables.

```bash
az vm run-command invoke -g rg-dual-hub-vnra-udr-transit -n test1-vm \
  --command-id RunShellScript --scripts "ping -c 4 -W 2 10.20.1.4; echo exit=$?"
```

Pass: 100% loss. Fail: any ping success.

---

### S2 -- VNRA + UDR Transit + Managed-Resource Proof

After deploying vnra1, vnra2, and all four route tables.

```bash
az vm run-command invoke -g rg-dual-hub-vnra-udr-transit -n test1-vm \
  --command-id RunShellScript \
  --scripts "ping -c 4 10.20.1.4 && echo PASS || echo FAIL; traceroute -n -w 2 -m 10 10.20.1.4"

az vm run-command invoke -g rg-dual-hub-vnra-udr-transit -n test2-vm \
  --command-id RunShellScript \
  --scripts "ping -c 4 10.10.1.4 && echo PASS || echo FAIL; traceroute -n -w 2 -m 10 10.10.1.4"
```

Pass: 0% loss both directions. Traceroute shows **no intermediate hop at VNRA IPs** -- hardware
forwarding is invisible to TTL-based probes. Absence-of-hop is the definitive proof the managed
VNRA (not a VM) is in the path. A visible VNRA IP hop would indicate VM NVA, not managed VNRA.

Fail: loss > 0%; OR VNRA IP (10.1.0.4 or 10.2.0.4) appears as a traceroute hop.

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

Pass (test1-vm): 10.20.0.0/16 -> User/VirtualAppliance -> 10.1.0.4, Active
Pass (test2-vm): 10.10.0.0/16 -> User/VirtualAppliance -> 10.2.0.4, Active
Fail: UDR absent; Invalid state; transitive spoke route via system route.

---

### S4 -- VNRA Route Table + Network Watcher Proxy (replaces manifest S4)

No user NIC on managed VNRA. `az network nic show-effective-route-table` is N/A.

```bash
az network route-table route list \
  --route-table-name rt-hub1-vnra -g rg-dual-hub-vnra-udr-transit -o table
# Expected: 10.20.0.0/16 / VirtualAppliance / 10.2.0.4

az network route-table route list \
  --route-table-name rt-hub2-vnra -g rg-dual-hub-vnra-udr-transit -o table
# Expected: 10.10.0.0/16 / VirtualAppliance / 10.1.0.4

# Network Watcher next-hop -- indirect proxy from test1-vm NIC with source-ip=VNRA1
az network watcher show-next-hop \
  --resource-group rg-dual-hub-vnra-udr-transit \
  --vm test1-vm --source-ip 10.1.0.4 --dest-ip 10.20.1.4 \
  --nic test1-vmVMNic
# Expected: nextHopType=VirtualAppliance, nextHopIpAddress=10.2.0.4
# Limitation: reflects hub1 routing context from test1-vm NIC, not direct VNRA1 view
```

Pass: route entries correct; Network Watcher returns VA/10.2.0.4.

---

### S5 -- Observability: Subnet-Scope Effective Routes (key investigation)

```bash
SUB=$(az account show --query id -o tsv)
RG=rg-dual-hub-vnra-udr-transit

# Probe A1: subnet effectiveRouteTable -- expect 404 or 405
az rest --method post \
  --url "https://management.azure.com/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.Network/virtualNetworks/hub1-vnet/subnets/VirtualNetworkApplianceSubnet/effectiveRouteTable?api-version=2024-05-01"

# Probe A2: alternate action name
az rest --method post \
  --url "https://management.azure.com/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.Network/virtualNetworks/hub1-vnet/subnets/VirtualNetworkApplianceSubnet/listEffectiveRoutes?api-version=2024-05-01"

# Probe B: VNRA resource GET -- IP and state, NOT effective routes
az rest --method GET \
  --url "https://management.azure.com/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.Network/virtualNetworkAppliances/vnra1?api-version=2025-05-01"

# Probe C: Azure Monitor metrics (primary observability for managed VNRA)
az monitor metrics list \
  --resource "/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.Network/virtualNetworkAppliances/vnra1" \
  --metric "BytesSent" "BytesReceived" "PacketsSent" "PacketsReceived" "InboundFlows" "OutboundFlows" \
  --interval PT1M -o table
# Expected: 200 + non-zero values after S2 traffic
```

Portal check (Niobe screenshot): hub1-vnet -> Subnets -> VirtualNetworkApplianceSubnet.
Document whether an "Effective routes" link appears.

---

## 12. Observability Matrix

| Query type | Tool | VM NVA | Managed VNRA |
|---|---|---|---|
| (a) Configured route table | `az network route-table route list` | YES | YES |
| (b) Effective routes on NIC | `az network nic show-effective-route-table` | YES | NO -- no user NIC |
| (c) Effective routes for managed resource | No documented API | N/A | NO -- no API as of 2026-08-19 |
| (d) Subnet-scope effective routes (REST) | Probes A1/A2 | 404 expected | 404 expected (empirical) |
| (e) Resource GET (IP + state) | `az rest GET .../virtualNetworkAppliances/vnra1` | N/A | YES -- returns IP and state, not routes |
| (f) Azure Monitor throughput | `az monitor metrics list` (BytesSent/Received) | N/A | YES -- built-in, no config |
| (g) Azure Monitor flows | `az monitor metrics list` (InboundFlows/OutboundFlows) | N/A | YES -- built-in |
| (h) Network Watcher next-hop | `az network watcher show-next-hop` | YES (direct) | Indirect (adjacent VM as source proxy) |
| (i) VNet Flow Logs | Flow log on VNRA subnet | YES | NO -- not supported |
| (j) Per-flow 5-tuple logging | NSG / VNet flow logs | YES | NO -- not available per docs |

Production gap: effective-route verification for managed VNRA falls back to (a)+(e)+(f)+(g)+(h)+S2.
Per-flow visibility requires VNet flow logs on workload subnets (spoke vm-subnets), not VNRA subnet.

---

## 13. Resiliency Analysis

| ID | Failure mode | Blast radius | Failover time | Operator action | Lab acceptable? |
|---|---|---|---|---|---|
| F1 | VNRA1 hardware failure | Spoke1 east-west drops | Seconds -- built-in HA, AZ-resilient per docs | None (platform HA) | YES |
| F2 | VNRA2 hardware failure | Spoke2 east-west drops | Seconds -- built-in HA | None | YES |
| F3 | hub1<->hub2 global peering disruption | All cross-region transit broken | No auto-failover | Restore peering; minutes RTO | YES for lab; prod: add IPsec overlay as secondary path |
| F4 | hub1<->spoke1 peering disruption | Spoke1 isolated | No auto-failover | Restore peering | YES for lab |
| F5 | hub2<->spoke2 peering disruption | Spoke2 isolated | No auto-failover | Restore peering | YES for lab |
| F6 | VNRA bandwidth saturation (50 Gbps) | Packet drops | No auto-tier-up | Delete + redeploy at higher tier (immutable) | YES; not a concern for B2ts_v2 test VMs |
| F7 | Subscription quota >2 VNRA/region | VNRA creation fails | Hard limit | Request quota increase | Pre-deploy gate |

Production reader note (F3): global peering is the single transit path. Add IPsec overlay
hub1<->hub2 as secondary path in production.

Patch catalogue (dormant until Jose approves):

| Patch | Mitigates | Delta | Cost impact | Residual gap |
|---|---|---|---|---|
| P1 | F3 | StrongSwan NVA pair hub1<->hub2 IPsec overlay; update hub UDRs with secondary next-hop | +~$0.50/day | BGP convergence ~30s; VNRA still single path per hub |

---

## 14. Empirical Gates

| ID | Question | Why it matters | Pass criterion | Fail action |
|---|---|---|---|---|
| E1 | Does rt-hub1-vnra on VirtualNetworkApplianceSubnet direct managed VNRA1 forwarding to VNRA2 (10.2.0.4) across global peering? | Core dual-hub path; UDR on VNRA subnet documented but cross-VNRA chaining via global peering not in any published example | S2 ping passes AND no VNRA IP hop in traceroute | Redesign: single-VNRA per hub; spoke UDRs route hub2 prefixes directly to VNRA1 using peering system route |
| E2 | What HTTP status does POST .../VirtualNetworkApplianceSubnet/effectiveRouteTable return? | Determines subnet-scope effective route API existence | 404/405 -- gap confirmed; 202 -- undocumented feature | Document status + body; compare with spoke NIC effective routes if 202 |
| E3 | Are VNRA Azure Monitor metrics available immediately without diagnostic config? | Docs claim no configuration required | `az monitor metrics list` returns 200 + series post-S2 | Investigate diagnostic config requirement |
| E4 | Do multiple VNRA instances in same VirtualNetworkApplianceSubnet share load automatically? | ILB unsupported; sharing mechanism undocumented | Both VNRA instances show non-zero BytesSent under load | Scale-out undefined; single VNRA per hub is validated model |

---

## 15. Route Collection Checklist (Niobe)

| Layer | Command | Expected |
|---|---|---|
| test1-vm NIC | `az network nic show-effective-route-table --name test1-vmVMNic -g rg-dual-hub-vnra-udr-transit -o table` | UDR 10.20.0.0/16 -> VA -> 10.1.0.4 Active |
| test2-vm NIC | `az network nic show-effective-route-table --name test2-vmVMNic -g rg-dual-hub-vnra-udr-transit -o table` | UDR 10.10.0.0/16 -> VA -> 10.2.0.4 Active |
| rt-hub1-vnra routes | `az network route-table route list --route-table-name rt-hub1-vnra -g rg-dual-hub-vnra-udr-transit -o table` | 10.20.0.0/16 / VA / 10.2.0.4 |
| rt-hub2-vnra routes | `az network route-table route list --route-table-name rt-hub2-vnra -g rg-dual-hub-vnra-udr-transit -o table` | 10.10.0.0/16 / VA / 10.1.0.4 |
| VNRA1 resource state | `az rest --method GET --url ".../virtualNetworkAppliances/vnra1?api-version=2025-05-01" --query properties.provisioningState` | Succeeded |
| VNRA1 metrics (post-S2) | `az monitor metrics list --resource ".../virtualNetworkAppliances/vnra1" --metric BytesSent --interval PT1M` | Non-zero bytes |
| Subnet effective routes (E2) | `az rest --method post --url ".../VirtualNetworkApplianceSubnet/effectiveRouteTable?api-version=2024-05-01"` | Document HTTP status code |
