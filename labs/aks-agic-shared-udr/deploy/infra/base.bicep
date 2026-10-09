// Baseline network, NVA, route table, NSGs, identity and Application Gateway (legacy, no network isolation).
param location string = resourceGroup().location
param nvaSize string = 'Standard_B2ts_v2'
param adminUsername string = 'labadmin'
param sshPublicKey string
param tags object = {}

var nvaIp = '10.20.1.4'
var agwPrivateIp = '10.21.2.250'
var networkContributor = '4d97b98b-1d4f-4787-a291-c67834d212e7'

resource nsgNva 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: 'nsg-nva'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'allow-spoke-transit-in'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: '*'
          sourceAddressPrefix: '10.21.0.0/16'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
    ]
  }
}

resource nsgAgw 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: 'nsg-agw'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'allow-gatewaymanager-in'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'GatewayManager'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '65200-65535'
        }
      }
      {
        name: 'allow-internet-http-in'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'Internet'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '80'
        }
      }
      {
        name: 'allow-vnet-http-in'
        properties: {
          priority: 120
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '80'
        }
      }
    ]
  }
}

resource rt 'Microsoft.Network/routeTables@2024-05-01' = {
  name: 'rt-shared'
  location: location
  tags: tags
  properties: {
    disableBgpRoutePropagation: true
  }
}

// Child resource so AKS-written pod routes are not removed by a PUT of the table.
resource rtDefault 'Microsoft.Network/routeTables/routes@2024-05-01' = {
  parent: rt
  name: 'default'
  properties: {
    addressPrefix: '0.0.0.0/0'
    nextHopType: 'Internet'
  }
}

resource vnetHub 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-hub'
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: ['10.20.0.0/16'] }
    subnets: [
      {
        name: 'snet-nva'
        properties: {
          addressPrefix: '10.20.1.0/24'
          networkSecurityGroup: { id: nsgNva.id }
        }
      }
    ]
  }
}

resource vnetSpoke 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-spoke'
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: ['10.21.0.0/16'] }
    subnets: [
      {
        name: 'snet-aks'
        properties: {
          addressPrefix: '10.21.1.0/24'
          routeTable: { id: rt.id }
        }
      }
      {
        name: 'snet-appgw'
        properties: {
          addressPrefix: '10.21.2.0/24'
          routeTable: { id: rt.id }
          networkSecurityGroup: { id: nsgAgw.id }
        }
      }
    ]
  }
  dependsOn: [rtDefault]
}

resource peerHubSpoke 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2024-05-01' = {
  parent: vnetHub
  name: 'hub-to-spoke'
  properties: {
    remoteVirtualNetwork: { id: vnetSpoke.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: false
  }
}

resource peerSpokeHub 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2024-05-01' = {
  parent: vnetSpoke
  name: 'spoke-to-hub'
  properties: {
    remoteVirtualNetwork: { id: vnetHub.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: false
  }
}

resource pipNva 'Microsoft.Network/publicIPAddresses@2024-05-01' = {
  name: 'pip-nva1'
  location: location
  tags: tags
  sku: { name: 'Standard' }
  properties: {
    publicIPAllocationMethod: 'Static'
    publicIPAddressVersion: 'IPv4'
  }
}

resource nicNva 'Microsoft.Network/networkInterfaces@2024-05-01' = {
  name: 'nic-nva1'
  location: location
  tags: tags
  properties: {
    enableIPForwarding: true
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          privateIPAllocationMethod: 'Static'
          privateIPAddress: nvaIp
          subnet: { id: '${vnetHub.id}/subnets/snet-nva' }
          publicIPAddress: { id: pipNva.id }
        }
      }
    ]
  }
}

resource nva 'Microsoft.Compute/virtualMachines@2024-07-01' = {
  name: 'nva1'
  location: location
  tags: tags
  properties: {
    hardwareProfile: { vmSize: nvaSize }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: '0001-com-ubuntu-server-jammy'
        sku: '22_04-lts-gen2'
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        deleteOption: 'Delete'
        managedDisk: { storageAccountType: 'StandardSSD_LRS' }
      }
    }
    osProfile: {
      computerName: 'nva1'
      adminUsername: adminUsername
      customData: loadFileAsBase64('cloud-init-nva.yaml')
      linuxConfiguration: {
        disablePasswordAuthentication: true
        ssh: {
          publicKeys: [
            {
              path: '/home/${adminUsername}/.ssh/authorized_keys'
              keyData: sshPublicKey
            }
          ]
        }
      }
    }
    networkProfile: {
      networkInterfaces: [
        { id: nicNva.id, properties: { primary: true, deleteOption: 'Delete' } }
      ]
    }
  }
}

resource idAks 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-aks'
  location: location
  tags: tags
}

resource snetAks 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' existing = {
  parent: vnetSpoke
  name: 'snet-aks'
}

resource raSubnet 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(snetAks.id, idAks.id, networkContributor)
  scope: snetAks
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', networkContributor)
    principalId: idAks.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource raRt 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(rt.id, idAks.id, networkContributor)
  scope: rt
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', networkContributor)
    principalId: idAks.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource pipAgw 'Microsoft.Network/publicIPAddresses@2024-05-01' = {
  name: 'pip-agw1'
  location: location
  tags: tags
  sku: { name: 'Standard' }
  properties: {
    publicIPAllocationMethod: 'Static'
    publicIPAddressVersion: 'IPv4'
  }
}

var agwId = resourceId('Microsoft.Network/applicationGateways', 'agw1')

resource agw 'Microsoft.Network/applicationGateways@2024-05-01' = {
  name: 'agw1'
  location: location
  tags: tags
  properties: {
    sku: { name: 'Standard_v2', tier: 'Standard_v2' }
    autoscaleConfiguration: { minCapacity: 1, maxCapacity: 2 }
    gatewayIPConfigurations: [
      { name: 'gwip', properties: { subnet: { id: '${vnetSpoke.id}/subnets/snet-appgw' } } }
    ]
    frontendIPConfigurations: [
      { name: 'fe-public', properties: { publicIPAddress: { id: pipAgw.id } } }
      {
        name: 'fe-private'
        properties: {
          privateIPAllocationMethod: 'Static'
          privateIPAddress: agwPrivateIp
          subnet: { id: '${vnetSpoke.id}/subnets/snet-appgw' }
        }
      }
    ]
    frontendPorts: [{ name: 'port80', properties: { port: 80 } }]
    backendAddressPools: [{ name: 'pool-dummy', properties: {} }]
    backendHttpSettingsCollection: [
      { name: 'http-dummy', properties: { port: 80, protocol: 'Http', requestTimeout: 30 } }
    ]
    httpListeners: [
      {
        name: 'listener-public'
        properties: {
          frontendIPConfiguration: { id: '${agwId}/frontendIPConfigurations/fe-public' }
          frontendPort: { id: '${agwId}/frontendPorts/port80' }
          protocol: 'Http'
        }
      }
    ]
    requestRoutingRules: [
      {
        name: 'rule-dummy'
        properties: {
          ruleType: 'Basic'
          priority: 1000
          httpListener: { id: '${agwId}/httpListeners/listener-public' }
          backendAddressPool: { id: '${agwId}/backendAddressPools/pool-dummy' }
          backendHttpSettings: { id: '${agwId}/backendHttpSettingsCollection/http-dummy' }
        }
      }
    ]
  }
  dependsOn: [peerSpokeHub]
}

output nvaPublicIpName string = pipNva.name
output agwPublicIpName string = pipAgw.name
output aksIdentityId string = idAks.id