// Azure Route Server (virtualHub kind=RouteServer, Standard PIP required)
// Ref: https://learn.microsoft.com/azure/route-server/route-server-faq

@description('Route Server name')
param name string

param location string
param tags object

@description('Resource ID of RouteServerSubnet (≥/27, no NSG/UDR)')
param subnetId string

@description('Resource ID of Standard PIP (mandatory for SDN management plane)')
param pipId string

@description('Enable branch-to-branch: true for hubs with VPN GW, false for Poland (ARS-only)')
param allowBranchToBranchTraffic bool

resource ars 'Microsoft.Network/virtualHubs@2023-09-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: 'Standard'
    allowBranchToBranchTraffic: allowBranchToBranchTraffic
  }
}

// ARS IP configuration (Standard PIP + RouteServerSubnet) — separate child resource
resource arsIpConfig 'Microsoft.Network/virtualHubs/ipConfigurations@2023-09-01' = {
  parent: ars
  name: 'ipconfigRouteServer'
  properties: {
    publicIPAddress: { id: pipId }
    subnet: { id: subnetId }
  }
}

output id string = ars.id
output name string = ars.name

// NVA BGP peering sub-resources
@description('NVA peer name (e.g. peer-nva1)')
param peerName1 string

@description('NVA IP address for peer 1')
param peerIp1 string

@description('NVA ASN for peer 1')
param peerAsn1 int

@description('NVA peer name for second NVA (empty string = skip)')
param peerName2 string = ''

@description('NVA IP address for peer 2 (if peerName2 set)')
param peerIp2 string = ''

@description('NVA ASN for peer 2 (if peerName2 set)')
param peerAsn2 int = 0

resource bgpPeer1 'Microsoft.Network/virtualHubs/bgpConnections@2023-09-01' = {
  parent: ars
  name: peerName1
  properties: {
    peerIp: peerIp1
    peerAsn: peerAsn1
  }
  dependsOn: [ arsIpConfig ]
}

resource bgpPeer2 'Microsoft.Network/virtualHubs/bgpConnections@2023-09-01' = if (!empty(peerName2)) {
  parent: ars
  name: !empty(peerName2) ? peerName2 : 'placeholder'
  properties: {
    peerIp: peerIp2
    peerAsn: peerAsn2
  }
  dependsOn: [ arsIpConfig ]
}
