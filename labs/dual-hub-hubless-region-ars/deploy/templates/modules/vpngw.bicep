// Active-Active VPN Gateway (VpnGw1) with BGP
// charter: no hardcoded subscription/tenant IDs; all structural params

@description('Gateway name')
param name string

@description('Azure region')
param location string

param tags object

@description('Resource ID of GatewaySubnet')
param gatewaySubnetId string

@description('Resource ID of first public IP (active instance)')
param pip1Id string

@description('Resource ID of second public IP (standby instance)')
param pip2Id string

@description('BGP ASN')
param asn int

resource vpngw 'Microsoft.Network/virtualNetworkGateways@2023-09-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'VpnGw1AZ'
      tier: 'VpnGw1AZ'
    }
    gatewayType: 'Vpn'
    vpnType: 'RouteBased'
    enableBgp: true
    activeActive: true   // ARS coexistence: AA mandatory
    bgpSettings: {
      asn: asn
    }
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          publicIPAddress: { id: pip1Id }
          subnet: { id: gatewaySubnetId }
          privateIPAllocationMethod: 'Dynamic'
        }
      }
      {
        name: 'ipconfig2'
        properties: {
          publicIPAddress: { id: pip2Id }
          subnet: { id: gatewaySubnetId }
          privateIPAllocationMethod: 'Dynamic'
        }
      }
    ]
    vpnGatewayGeneration: 'Generation1'
  }
}

output id string = vpngw.id
output name string = vpngw.name
