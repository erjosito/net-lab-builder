// dual-hub-hubless-region-ars — main deployment template
// Implements: 8 VNets, 3 AA VPN GWs, 3 ARS, 6 VMs, 10 peering pairs,
//             4 VPN V2V connections, 2 UDR route tables, NSGs
// Regions: swedencentral (hub1), switzerlandnorth (hub2),
//          polandcentral (ARS+workload), norwayeast (simulated on-prem)
// charter: no hardcoded sub/tenant IDs; tags on every resource; no PIP on VMs

targetScope = 'resourceGroup'

// ── Parameters ────────────────────────────────────────────────────────────────

@description('Unique correlation ID for tagging and RG name suffix')
param correlationId string

@description('VM admin username')
param adminUsername string = 'labadmin'

@description('SSH public key value for all VMs')
param vmSshPublicKey string

@description('VM size — preflight confirmed Standard_B2ts_v2 in all 4 regions')
param vmSize string = 'Standard_B2ts_v2'

@description('PSK for hub1↔onprem VPN connections')
@secure()
param pskHub1Onprem string

@description('PSK for hub2↔onprem VPN connections')
@secure()
param pskHub2Onprem string

@description('Base64-encoded cloud-init for NVA1 (BIRD ASN 65001)')
param nva1CloudInit string

@description('Base64-encoded cloud-init for NVA2 (BIRD ASN 65002)')
param nva2CloudInit string

// ── Locations ─────────────────────────────────────────────────────────────────

var locHub1    = 'swedencentral'
var locHub2    = 'switzerlandnorth'
var locPoland  = 'polandcentral'
var locOnprem  = 'norwayeast'

// ── Tags ──────────────────────────────────────────────────────────────────────

var tags = {
  lab: 'true'
  created_by: 'copilot-lab'
  lab_name: 'dual-hub-hubless-region-ars'
  owner: 'jose'
  ephemeral: 'true'
  correlation_id: correlationId
}

// ══════════════════════════════════════════════════════════════════════════════
// Wave 0 — 9 Standard Public IPs
// 6 for VPN GW AA (2 per GW) + 3 for ARS (1 each)
// ══════════════════════════════════════════════════════════════════════════════

resource pipGwHub1A 'Microsoft.Network/publicIPAddresses@2023-09-01' = {
  name: 'pip-gw-hub1-a'
  location: locHub1
  tags: tags
  sku: { name: 'Standard' }
  zones: ['1', '2', '3']  // required: VpnGw1AZ mandates zone-enabled PIPs
  properties: { publicIPAllocationMethod: 'Static' }
}
resource pipGwHub1B 'Microsoft.Network/publicIPAddresses@2023-09-01' = {
  name: 'pip-gw-hub1-b'
  location: locHub1
  tags: tags
  sku: { name: 'Standard' }
  zones: ['1', '2', '3']  // required: VpnGw1AZ mandates zone-enabled PIPs
  properties: { publicIPAllocationMethod: 'Static' }
}
resource pipGwHub2A 'Microsoft.Network/publicIPAddresses@2023-09-01' = {
  name: 'pip-gw-hub2-a'
  location: locHub2
  tags: tags
  sku: { name: 'Standard' }
  zones: ['1', '2', '3']  // required: VpnGw1AZ mandates zone-enabled PIPs
  properties: { publicIPAllocationMethod: 'Static' }
}
resource pipGwHub2B 'Microsoft.Network/publicIPAddresses@2023-09-01' = {
  name: 'pip-gw-hub2-b'
  location: locHub2
  tags: tags
  sku: { name: 'Standard' }
  zones: ['1', '2', '3']  // required: VpnGw1AZ mandates zone-enabled PIPs
  properties: { publicIPAllocationMethod: 'Static' }
}
resource pipGwOnpremA 'Microsoft.Network/publicIPAddresses@2023-09-01' = {
  name: 'pip-gw-onprem-a'
  location: locOnprem
  tags: tags
  sku: { name: 'Standard' }
  zones: ['1', '2', '3']  // required: VpnGw1AZ mandates zone-enabled PIPs
  properties: { publicIPAllocationMethod: 'Static' }
}
resource pipGwOnpremB 'Microsoft.Network/publicIPAddresses@2023-09-01' = {
  name: 'pip-gw-onprem-b'
  location: locOnprem
  tags: tags
  sku: { name: 'Standard' }
  zones: ['1', '2', '3']  // required: VpnGw1AZ mandates zone-enabled PIPs
  properties: { publicIPAllocationMethod: 'Static' }
}
// ARS PIPs (1 each — required by SDN management plane)
resource pipArsHub1 'Microsoft.Network/publicIPAddresses@2023-09-01' = {
  name: 'pip-ars-hub1'
  location: locHub1
  tags: tags
  sku: { name: 'Standard' }
  properties: { publicIPAllocationMethod: 'Static' }
}
resource pipArsHub2 'Microsoft.Network/publicIPAddresses@2023-09-01' = {
  name: 'pip-ars-hub2'
  location: locHub2
  tags: tags
  sku: { name: 'Standard' }
  properties: { publicIPAllocationMethod: 'Static' }
}
resource pipArsPoland 'Microsoft.Network/publicIPAddresses@2023-09-01' = {
  name: 'pip-ars-poland'
  location: locPoland
  tags: tags
  sku: { name: 'Standard' }
  properties: { publicIPAllocationMethod: 'Static' }
}

// ══════════════════════════════════════════════════════════════════════════════
// Wave 1 — NSGs (4: nva-hub1, nva-hub2, ep-general, ep-onprem)
// ══════════════════════════════════════════════════════════════════════════════

// NSG for NVA subnets — allow BGP (TCP/179) + ICMP + SSH from mgmt
resource nsgNvaHub1 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: 'nsg-nva-hub1'
  location: locHub1
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'allow-bgp-inbound'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '10.10.0.0/16'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '179'
        }
      }
      {
        name: 'allow-bgp-multihop-inbound'
        properties: {
          priority: 105
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '10.30.0.0/24'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '179'
        }
      }
      {
        name: 'allow-icmp-inbound'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Icmp'
          sourceAddressPrefix: '10.0.0.0/8'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
      {
        name: 'allow-ssh-inbound'
        properties: {
          priority: 120
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '10.0.0.0/8'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '22'
        }
      }
      {
        name: 'deny-other-inbound'
        properties: {
          priority: 4000
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
    ]
  }
}

resource nsgNvaHub2 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: 'nsg-nva-hub2'
  location: locHub2
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'allow-bgp-inbound'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '10.20.0.0/16'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '179'
        }
      }
      {
        name: 'allow-bgp-multihop-inbound'
        properties: {
          priority: 105
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '10.30.0.0/24'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '179'
        }
      }
      {
        name: 'allow-icmp-inbound'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Icmp'
          sourceAddressPrefix: '10.0.0.0/8'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
      {
        name: 'allow-ssh-inbound'
        properties: {
          priority: 120
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '10.0.0.0/8'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '22'
        }
      }
      {
        name: 'deny-other-inbound'
        properties: {
          priority: 4000
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
    ]
  }
}

// NSG for endpoint VMs — allow ICMP + SSH from RFC1918
resource nsgEpGeneral 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: 'nsg-ep-general'
  location: locHub1
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'allow-icmp-inbound'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Icmp'
          sourceAddressPrefix: '10.0.0.0/8'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
      {
        name: 'allow-ssh-inbound'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '10.0.0.0/8'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '22'
        }
      }
      {
        name: 'deny-other-inbound'
        properties: {
          priority: 4000
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
    ]
  }
}

// Common EP NSG security rules (avoid read-only property copy)
var epNsgRules = [
  {
    name: 'allow-icmp-inbound'
    properties: {
      priority: 100
      direction: 'Inbound'
      access: 'Allow'
      protocol: 'Icmp'
      sourceAddressPrefix: '10.0.0.0/8'
      sourcePortRange: '*'
      destinationAddressPrefix: '*'
      destinationPortRange: '*'
    }
  }
  {
    name: 'allow-ssh-inbound'
    properties: {
      priority: 110
      direction: 'Inbound'
      access: 'Allow'
      protocol: 'Tcp'
      sourceAddressPrefix: '10.0.0.0/8'
      sourcePortRange: '*'
      destinationAddressPrefix: '*'
      destinationPortRange: '22'
    }
  }
  {
    name: 'deny-other-inbound'
    properties: {
      priority: 4000
      direction: 'Inbound'
      access: 'Deny'
      protocol: '*'
      sourceAddressPrefix: '*'
      sourcePortRange: '*'
      destinationAddressPrefix: '*'
      destinationPortRange: '*'
    }
  }
]

resource nsgEpHub2 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: 'nsg-ep-hub2'
  location: locHub2
  tags: tags
  properties: { securityRules: epNsgRules }
}
resource nsgEpPoland 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: 'nsg-ep-poland'
  location: locPoland
  tags: tags
  properties: { securityRules: epNsgRules }
}
resource nsgEpOnprem 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: 'nsg-ep-onprem'
  location: locOnprem
  tags: tags
  properties: { securityRules: epNsgRules }
}

// ══════════════════════════════════════════════════════════════════════════════
// Wave 1 — Route Tables (Set-A and Set-B; Set-C has no UDR — ARS injects)
// ══════════════════════════════════════════════════════════════════════════════

// rt-spoke-a: 0/0 → NVA1 (10.10.1.4); BGP propagation disabled
resource rtSpokeA 'Microsoft.Network/routeTables@2023-09-01' = {
  name: 'rt-spoke-a'
  location: locHub1
  tags: tags
  properties: {
    disableBgpRoutePropagation: true
    routes: [
      {
        name: 'default-to-nva1'
        properties: {
          addressPrefix: '0.0.0.0/0'
          nextHopType: 'VirtualAppliance'
          nextHopIpAddress: '10.10.1.4'
        }
      }
    ]
  }
}

// rt-spoke-b: 0/0 → NVA2 (10.20.1.4); BGP propagation disabled
resource rtSpokeB 'Microsoft.Network/routeTables@2023-09-01' = {
  name: 'rt-spoke-b'
  location: locHub2
  tags: tags
  properties: {
    disableBgpRoutePropagation: true
    routes: [
      {
        name: 'default-to-nva2'
        properties: {
          addressPrefix: '0.0.0.0/0'
          nextHopType: 'VirtualAppliance'
          nextHopIpAddress: '10.20.1.4'
        }
      }
    ]
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// Wave 1 — 8 VNets with subnets
// GatewaySubnet and RouteServerSubnet: NO NSG, NO UDR (platform requirements)
// ══════════════════════════════════════════════════════════════════════════════

resource vnetHub1 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: 'vnet-hub1'
  location: locHub1
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: ['10.10.0.0/16'] }
    subnets: [
      // GatewaySubnet: no NSG, no UDR
      { name: 'GatewaySubnet', properties: { addressPrefix: '10.10.0.0/27' } }
      // RouteServerSubnet: no NSG, no UDR (ARS requirement)
      { name: 'RouteServerSubnet', properties: { addressPrefix: '10.10.0.64/27' } }
      {
        name: 'snet-nva'
        properties: {
          addressPrefix: '10.10.1.0/27'
          networkSecurityGroup: { id: nsgNvaHub1.id }
        }
      }
      {
        name: 'snet-endpoint'
        properties: {
          addressPrefix: '10.10.2.0/27'
          networkSecurityGroup: { id: nsgEpGeneral.id }
        }
      }
    ]
  }
}

resource vnetHub2 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: 'vnet-hub2'
  location: locHub2
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: ['10.20.0.0/16'] }
    subnets: [
      { name: 'GatewaySubnet', properties: { addressPrefix: '10.20.0.0/27' } }
      { name: 'RouteServerSubnet', properties: { addressPrefix: '10.20.0.64/27' } }
      {
        name: 'snet-nva'
        properties: {
          addressPrefix: '10.20.1.0/27'
          networkSecurityGroup: { id: nsgNvaHub2.id }
        }
      }
      {
        name: 'snet-endpoint'
        properties: {
          addressPrefix: '10.20.2.0/27'
          networkSecurityGroup: { id: nsgEpHub2.id }
        }
      }
    ]
  }
}

// Poland ARS VNet — RouteServerSubnet ONLY; no GW, no NVA, no NSG
resource vnetPolandArs 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: 'vnet-poland-ars'
  location: locPoland
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: ['10.30.0.0/24'] }
    subnets: [
      { name: 'RouteServerSubnet', properties: { addressPrefix: '10.30.0.0/27' } }
    ]
  }
}

resource vnetOnprem 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: 'vnet-onprem'
  location: locOnprem
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: ['10.40.0.0/16'] }
    subnets: [
      { name: 'GatewaySubnet', properties: { addressPrefix: '10.40.0.0/27' } }
      {
        name: 'snet-endpoint'
        properties: {
          addressPrefix: '10.40.1.0/27'
          networkSecurityGroup: { id: nsgEpOnprem.id }
        }
      }
    ]
  }
}

resource vnetSpokeA 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: 'vnet-spoke-a'
  location: locHub1
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: ['10.11.0.0/24'] }
    subnets: [
      {
        name: 'snet-workload'
        properties: {
          addressPrefix: '10.11.0.0/25'
          routeTable: { id: rtSpokeA.id }
          networkSecurityGroup: { id: nsgEpGeneral.id }
        }
      }
    ]
  }
}

resource vnetSpokeB 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: 'vnet-spoke-b'
  location: locHub2
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: ['10.21.0.0/24'] }
    subnets: [
      {
        name: 'snet-workload'
        properties: {
          addressPrefix: '10.21.0.0/25'
          routeTable: { id: rtSpokeB.id }
          networkSecurityGroup: { id: nsgEpHub2.id }
        }
      }
    ]
  }
}

resource vnetSpokeC1 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: 'vnet-spoke-c1'
  location: locPoland
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: ['10.31.0.0/24'] }
    subnets: [
      {
        // No UDR — ARS injects 0/0 dynamically (Δ3 route-map or Δ2 prepend)
        name: 'snet-workload'
        properties: {
          addressPrefix: '10.31.0.0/25'
          networkSecurityGroup: { id: nsgEpPoland.id }
        }
      }
    ]
  }
}

// spoke-c2: prefix-only, no VM, no NSG needed, ARS learns the VNet prefix
resource vnetSpokeC2 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: 'vnet-spoke-c2'
  location: locPoland
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: ['10.32.0.0/24'] }
    subnets: []
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// Wave 3 — VPN Gateways (AA, BGP, VpnGw1)
// hub1+hub2 ASN=65515 (must match ARS ASN for coexistence)
// onprem ASN=65000
// ══════════════════════════════════════════════════════════════════════════════

module vpngwHub1 'modules/vpngw.bicep' = {
  name: 'vpngw-hub1-deploy'
  params: {
    name: 'vpngw-hub1'
    location: locHub1
    tags: tags
    gatewaySubnetId: resourceId('Microsoft.Network/virtualNetworks/subnets', 'vnet-hub1', 'GatewaySubnet')
    pip1Id: pipGwHub1A.id
    pip2Id: pipGwHub1B.id
    asn: 65515
  }
  dependsOn: [ vnetHub1 ]
}

module vpngwHub2 'modules/vpngw.bicep' = {
  name: 'vpngw-hub2-deploy'
  params: {
    name: 'vpngw-hub2'
    location: locHub2
    tags: tags
    gatewaySubnetId: resourceId('Microsoft.Network/virtualNetworks/subnets', 'vnet-hub2', 'GatewaySubnet')
    pip1Id: pipGwHub2A.id
    pip2Id: pipGwHub2B.id
    asn: 65515
  }
  dependsOn: [ vnetHub2 ]
}

module vpngwOnprem 'modules/vpngw.bicep' = {
  name: 'vpngw-onprem-deploy'
  params: {
    name: 'vpngw-onprem'
    location: locOnprem
    tags: tags
    gatewaySubnetId: resourceId('Microsoft.Network/virtualNetworks/subnets', 'vnet-onprem', 'GatewaySubnet')
    pip1Id: pipGwOnpremA.id
    pip2Id: pipGwOnpremB.id
    asn: 65000
  }
  dependsOn: [ vnetOnprem ]
}

// ══════════════════════════════════════════════════════════════════════════════
// Wave 3 — Azure Route Servers
// ars-hub1 + ars-hub2: b2b=true (ARS+VPN GW coexistence)
// ars-poland: b2b=false (ARS-only VNet, no VPN GW)
// Each needs a Standard PIP (SDN management plane mandatory)
// NVA BGP peerings included in module (ars-poland peers both NVA1 and NVA2)
// ══════════════════════════════════════════════════════════════════════════════

module arsHub1 'modules/ars.bicep' = {
  name: 'ars-hub1-deploy'
  params: {
    name: 'ars-hub1'
    location: locHub1
    tags: tags
    subnetId: resourceId('Microsoft.Network/virtualNetworks/subnets', 'vnet-hub1', 'RouteServerSubnet')
    pipId: pipArsHub1.id
    allowBranchToBranchTraffic: true
    peerName1: 'peer-nva1'
    peerIp1: '10.10.1.4'
    peerAsn1: 65001
  }
  dependsOn: [ vnetHub1, vmNva1 ]
}

module arsHub2 'modules/ars.bicep' = {
  name: 'ars-hub2-deploy'
  params: {
    name: 'ars-hub2'
    location: locHub2
    tags: tags
    subnetId: resourceId('Microsoft.Network/virtualNetworks/subnets', 'vnet-hub2', 'RouteServerSubnet')
    pipId: pipArsHub2.id
    allowBranchToBranchTraffic: true
    peerName1: 'peer-nva2'
    peerIp1: '10.20.1.4'
    peerAsn1: 65002
  }
  dependsOn: [ vnetHub2, vmNva2 ]
}

// ars-poland peers BOTH NVA1 (multi-hop from swedencentral) and NVA2 (from switzerlandnorth)
// Multi-hop sessions: NVA IPs traverse global VNet peering fabric; BIRD sets multihop 4
module arsPoland 'modules/ars.bicep' = {
  name: 'ars-poland-deploy'
  params: {
    name: 'ars-poland'
    location: locPoland
    tags: tags
    subnetId: resourceId('Microsoft.Network/virtualNetworks/subnets', 'vnet-poland-ars', 'RouteServerSubnet')
    pipId: pipArsPoland.id
    allowBranchToBranchTraffic: false
    peerName1: 'peer-nva1'
    peerIp1: '10.10.1.4'
    peerAsn1: 65001
    peerName2: 'peer-nva2'
    peerIp2: '10.20.1.4'
    peerAsn2: 65002
  }
  dependsOn: [ vnetPolandArs, vmNva1, vmNva2 ]
}

// ══════════════════════════════════════════════════════════════════════════════
// Wave 3 — VMs (6 × Standard_B2ts_v2, no PIP, Ubuntu 22.04)
// ══════════════════════════════════════════════════════════════════════════════

module vmNva1 'modules/vm.bicep' = {
  name: 'vm-nva1-deploy'
  params: {
    name: 'vm-nva1'
    location: locHub1
    tags: tags
    subnetId: resourceId('Microsoft.Network/virtualNetworks/subnets', 'vnet-hub1', 'snet-nva')
    privateIpAddress: '10.10.1.4'
    adminUsername: adminUsername
    sshPublicKey: vmSshPublicKey
    vmSize: vmSize
    enableIpForwarding: true
    customData: nva1CloudInit
  }
  dependsOn: [ vnetHub1 ]
}

module vmNva2 'modules/vm.bicep' = {
  name: 'vm-nva2-deploy'
  params: {
    name: 'vm-nva2'
    location: locHub2
    tags: tags
    subnetId: resourceId('Microsoft.Network/virtualNetworks/subnets', 'vnet-hub2', 'snet-nva')
    privateIpAddress: '10.20.1.4'
    adminUsername: adminUsername
    sshPublicKey: vmSshPublicKey
    vmSize: vmSize
    enableIpForwarding: true
    customData: nva2CloudInit
  }
  dependsOn: [ vnetHub2 ]
}

module vmHub1Ep 'modules/vm.bicep' = {
  name: 'vm-hub1-ep-deploy'
  params: {
    name: 'vm-hub1-ep'
    location: locHub1
    tags: tags
    subnetId: resourceId('Microsoft.Network/virtualNetworks/subnets', 'vnet-spoke-a', 'snet-workload')
    adminUsername: adminUsername
    sshPublicKey: vmSshPublicKey
    vmSize: vmSize
  }
  dependsOn: [ vnetSpokeA ]
}

module vmHub2Ep 'modules/vm.bicep' = {
  name: 'vm-hub2-ep-deploy'
  params: {
    name: 'vm-hub2-ep'
    location: locHub2
    tags: tags
    subnetId: resourceId('Microsoft.Network/virtualNetworks/subnets', 'vnet-spoke-b', 'snet-workload')
    adminUsername: adminUsername
    sshPublicKey: vmSshPublicKey
    vmSize: vmSize
  }
  dependsOn: [ vnetSpokeB ]
}

module vmC1Ep 'modules/vm.bicep' = {
  name: 'vm-c1-ep-deploy'
  params: {
    name: 'vm-c1-ep'
    location: locPoland
    tags: tags
    subnetId: resourceId('Microsoft.Network/virtualNetworks/subnets', 'vnet-spoke-c1', 'snet-workload')
    adminUsername: adminUsername
    sshPublicKey: vmSshPublicKey
    vmSize: vmSize
  }
  dependsOn: [ vnetSpokeC1 ]
}

module vmOnpremEp 'modules/vm.bicep' = {
  name: 'vm-onprem-ep-deploy'
  params: {
    name: 'vm-onprem-ep'
    location: locOnprem
    tags: tags
    subnetId: resourceId('Microsoft.Network/virtualNetworks/subnets', 'vnet-onprem', 'snet-endpoint')
    adminUsername: adminUsername
    sshPublicKey: vmSshPublicKey
    vmSize: vmSize
  }
  dependsOn: [ vnetOnprem ]
}

// ══════════════════════════════════════════════════════════════════════════════
// Wave 4 — VNet Peerings (10 logical pairs = 20 objects)
// Flags: AFT=AllowForwardedTraffic AGT=AllowGatewayTransit URG=UseRemoteGateways
// CRITICAL: UseRemoteGateways=true on at most ONE peering per spoke VNet
//           Set-C spokes: URG only on poland-ars peering; hub peerings = false
// ══════════════════════════════════════════════════════════════════════════════

// Pair 1: hub1 ↔ spoke-a (hub1 provides GW+ARS transit)
resource peeringHub1ToSpokeA 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-09-01' = {
  parent: vnetHub1
  name: 'peer-hub1-to-spoke-a'
  properties: {
    remoteVirtualNetwork: { id: vnetSpokeA.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: true    // hub exposes GW + ARS
    useRemoteGateways: false
  }
  dependsOn: [ vpngwHub1 ]
}
resource peeringSpokeAToHub1 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-09-01' = {
  parent: vnetSpokeA
  name: 'peer-spoke-a-to-hub1'
  properties: {
    remoteVirtualNetwork: { id: vnetHub1.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: true      // spoke uses hub1 GW for transit
  }
  dependsOn: [ vpngwHub1 ]
}

// Pair 2: hub2 ↔ spoke-b
resource peeringHub2ToSpokeB 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-09-01' = {
  parent: vnetHub2
  name: 'peer-hub2-to-spoke-b'
  properties: {
    remoteVirtualNetwork: { id: vnetSpokeB.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: true
    useRemoteGateways: false
  }
  dependsOn: [ vpngwHub2 ]
}
resource peeringSpokeBToHub2 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-09-01' = {
  parent: vnetSpokeB
  name: 'peer-spoke-b-to-hub2'
  properties: {
    remoteVirtualNetwork: { id: vnetHub2.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: true
  }
  dependsOn: [ vpngwHub2 ]
}

// Pair 3: poland-ars ↔ spoke-c1 (AGT exposes ARS injection; no VPN GW in Poland)
resource peeringPolandToSpokeC1 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-09-01' = {
  parent: vnetPolandArs
  name: 'peer-poland-to-spoke-c1'
  properties: {
    remoteVirtualNetwork: { id: vnetSpokeC1.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: true    // allows ARS in Poland to inject routes into c1
    useRemoteGateways: false
  }
  dependsOn: [ arsPoland ]
}
resource peeringSpokeC1ToPoland 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-09-01' = {
  parent: vnetSpokeC1
  name: 'peer-spoke-c1-to-poland'
  properties: {
    remoteVirtualNetwork: { id: vnetPolandArs.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: true      // spoke-c1 uses Poland ARS for route injection (sole URG peering)
  }
  dependsOn: [ arsPoland ]
}

// Pair 4: poland-ars ↔ spoke-c2 (prefix-only; same flags as c1)
resource peeringPolandToSpokeC2 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-09-01' = {
  parent: vnetPolandArs
  name: 'peer-poland-to-spoke-c2'
  properties: {
    remoteVirtualNetwork: { id: vnetSpokeC2.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: true
    useRemoteGateways: false
  }
  dependsOn: [ arsPoland ]
}
resource peeringSpokeC2ToPoland 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-09-01' = {
  parent: vnetSpokeC2
  name: 'peer-spoke-c2-to-poland'
  properties: {
    remoteVirtualNetwork: { id: vnetPolandArs.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: true
  }
  dependsOn: [ arsPoland ]
}

// Pair 5: spoke-c1 ↔ hub1 — DATA PLANE ONLY (no transit flags)
// Enables NVA1 IP (10.10.1.x) to be a valid next-hop in set-C fabric
resource peeringSpokeC1ToHub1 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-09-01' = {
  parent: vnetSpokeC1
  name: 'peer-spoke-c1-to-hub1'
  properties: {
    remoteVirtualNetwork: { id: vnetHub1.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false   // no transit — data-plane path only
    useRemoteGateways: false     // URG already set on poland-ars peering
  }
}
resource peeringHub1ToSpokeC1 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-09-01' = {
  parent: vnetHub1
  name: 'peer-hub1-to-spoke-c1'
  properties: {
    remoteVirtualNetwork: { id: vnetSpokeC1.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: false
  }
}

// Pair 6: spoke-c1 ↔ hub2 — DATA PLANE ONLY
resource peeringSpokeC1ToHub2 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-09-01' = {
  parent: vnetSpokeC1
  name: 'peer-spoke-c1-to-hub2'
  properties: {
    remoteVirtualNetwork: { id: vnetHub2.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: false
  }
}
resource peeringHub2ToSpokeC1 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-09-01' = {
  parent: vnetHub2
  name: 'peer-hub2-to-spoke-c1'
  properties: {
    remoteVirtualNetwork: { id: vnetSpokeC1.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: false
  }
}

// Pair 7: spoke-c2 ↔ hub1 — DATA PLANE ONLY
resource peeringSpokeC2ToHub1 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-09-01' = {
  parent: vnetSpokeC2
  name: 'peer-spoke-c2-to-hub1'
  properties: {
    remoteVirtualNetwork: { id: vnetHub1.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: false
  }
}
resource peeringHub1ToSpokeC2 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-09-01' = {
  parent: vnetHub1
  name: 'peer-hub1-to-spoke-c2'
  properties: {
    remoteVirtualNetwork: { id: vnetSpokeC2.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: false
  }
}

// Pair 8: spoke-c2 ↔ hub2 — DATA PLANE ONLY
resource peeringSpokeC2ToHub2 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-09-01' = {
  parent: vnetSpokeC2
  name: 'peer-spoke-c2-to-hub2'
  properties: {
    remoteVirtualNetwork: { id: vnetHub2.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: false
  }
}
resource peeringHub2ToSpokeC2 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-09-01' = {
  parent: vnetHub2
  name: 'peer-hub2-to-spoke-c2'
  properties: {
    remoteVirtualNetwork: { id: vnetSpokeC2.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: false
  }
}

// Pair 9: poland-ars ↔ hub1 — BGP underlay + data plane for NVA1 multi-hop sessions
resource peeringPolandToHub1 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-09-01' = {
  parent: vnetPolandArs
  name: 'peer-poland-to-hub1'
  properties: {
    remoteVirtualNetwork: { id: vnetHub1.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: false
  }
}
resource peeringHub1ToPoland 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-09-01' = {
  parent: vnetHub1
  name: 'peer-hub1-to-poland'
  properties: {
    remoteVirtualNetwork: { id: vnetPolandArs.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: false
  }
}

// Pair 10: poland-ars ↔ hub2 — BGP underlay + data plane for NVA2 multi-hop sessions
resource peeringPolandToHub2 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-09-01' = {
  parent: vnetPolandArs
  name: 'peer-poland-to-hub2'
  properties: {
    remoteVirtualNetwork: { id: vnetHub2.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: false
  }
}
resource peeringHub2ToPoland 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-09-01' = {
  parent: vnetHub2
  name: 'peer-hub2-to-poland'
  properties: {
    remoteVirtualNetwork: { id: vnetPolandArs.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: false
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// Wave 5 — 4 VPN Connection Objects (Vnet2Vnet, BGP enabled)
// PSKs passed as @secure() params — never written to files
// conn pairs: hub1↔onprem (2 objects) + hub2↔onprem (2 objects)
// ══════════════════════════════════════════════════════════════════════════════

resource connHub1ToOnprem 'Microsoft.Network/connections@2023-09-01' = {
  name: 'conn-hub1-to-onprem'
  location: locHub1
  tags: tags
  properties: {
    connectionType: 'Vnet2Vnet'
    virtualNetworkGateway1: { id: vpngwHub1.outputs.id, properties: {} }
    virtualNetworkGateway2: { id: vpngwOnprem.outputs.id, properties: {} }
    sharedKey: pskHub1Onprem
    enableBgp: true
    connectionMode: 'Default'
    routingWeight: 0
  }
}

resource connOnpremToHub1 'Microsoft.Network/connections@2023-09-01' = {
  name: 'conn-onprem-to-hub1'
  location: locOnprem
  tags: tags
  properties: {
    connectionType: 'Vnet2Vnet'
    virtualNetworkGateway1: { id: vpngwOnprem.outputs.id, properties: {} }
    virtualNetworkGateway2: { id: vpngwHub1.outputs.id, properties: {} }
    sharedKey: pskHub1Onprem
    enableBgp: true
    connectionMode: 'Default'
    routingWeight: 0
  }
}

resource connHub2ToOnprem 'Microsoft.Network/connections@2023-09-01' = {
  name: 'conn-hub2-to-onprem'
  location: locHub2
  tags: tags
  properties: {
    connectionType: 'Vnet2Vnet'
    virtualNetworkGateway1: { id: vpngwHub2.outputs.id, properties: {} }
    virtualNetworkGateway2: { id: vpngwOnprem.outputs.id, properties: {} }
    sharedKey: pskHub2Onprem
    enableBgp: true
    connectionMode: 'Default'
    routingWeight: 0
  }
}

resource connOnpremToHub2 'Microsoft.Network/connections@2023-09-01' = {
  name: 'conn-onprem-to-hub2'
  location: locOnprem
  tags: tags
  properties: {
    connectionType: 'Vnet2Vnet'
    virtualNetworkGateway1: { id: vpngwOnprem.outputs.id, properties: {} }
    virtualNetworkGateway2: { id: vpngwHub2.outputs.id, properties: {} }
    sharedKey: pskHub2Onprem
    enableBgp: true
    connectionMode: 'Default'
    routingWeight: 0
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// Outputs — used by deploy.ps1 for post-deploy BIRD config push and validation
// ══════════════════════════════════════════════════════════════════════════════

output rgName string = resourceGroup().name
output nva1Ip string = vmNva1.outputs.privateIp
output nva2Ip string = vmNva2.outputs.privateIp
output arsHub1Id string = arsHub1.outputs.id
output arsHub2Id string = arsHub2.outputs.id
output arsPolandId string = arsPoland.outputs.id
output vpngwHub1Id string = vpngwHub1.outputs.id
output vpngwHub2Id string = vpngwHub2.outputs.id
output vpngwOnpremId string = vpngwOnprem.outputs.id
