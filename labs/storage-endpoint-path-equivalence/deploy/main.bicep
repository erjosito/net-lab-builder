targetScope = 'resourceGroup'

param location string = 'swedencentral'
param correlationId string
param translatorAccountName string
param deployPrivateEndpoint bool = false

var tags = {
  lab: 'true'
  created_by: 'copilot-lab'
  lab_name: 'storage-endpoint-path-equivalence'
  owner: 'jose'
  ephemeral: 'true'
  correlation_id: correlationId
}

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' existing = {
  name: 'vnet-endpoint-path'
}

resource nat 'Microsoft.Network/natGateways@2024-05-01' existing = {
  name: 'nat-client'
}

resource vm 'Microsoft.Compute/virtualMachines@2024-07-01' existing = {
  name: 'vm-client'
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: 'log-sepath'
}

resource nsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: 'nsg-client'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowAzureDNS'
        properties: {
          priority: 100
          direction: 'Outbound'
          access: 'Allow'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '53'
          sourceAddressPrefix: 'VirtualNetwork'
          destinationAddressPrefix: '168.63.129.16/32'
        }
      }
      {
        name: 'AllowIMDS'
        properties: {
          priority: 110
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '80'
          sourceAddressPrefix: 'VirtualNetwork'
          destinationAddressPrefix: '169.254.169.254/32'
        }
      }
      {
        name: 'AllowCognitiveServicesFrontend'
        properties: {
          priority: 120
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: 'VirtualNetwork'
          destinationAddressPrefix: 'CognitiveServicesFrontend'
        }
      }
      {
        name: 'AllowTranslatorPrivateEndpoint'
        properties: {
          priority: 125
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: '10.61.1.0/24'
          destinationAddressPrefix: '10.61.2.4/32'
        }
      }
      {
        name: 'AllowAzureCloudSwedenCentral'
        properties: {
          priority: 130
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: 'VirtualNetwork'
          destinationAddressPrefix: 'AzureCloud.SwedenCentral'
        }
      }
      {
        name: 'DenyOtherOutbound'
        properties: {
          priority: 4000
          direction: 'Outbound'
          access: 'Deny'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

resource clientSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  parent: vnet
  name: 'snet-client'
  properties: {
    addressPrefix: '10.61.1.0/24'
    natGateway: {
      id: nat.id
    }
    networkSecurityGroup: {
      id: nsg.id
    }
    privateEndpointNetworkPolicies: 'Enabled'
    privateLinkServiceNetworkPolicies: 'Enabled'
    serviceEndpoints: []
    serviceEndpointPolicies: []
  }
}

resource translator 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: translatorAccountName
  location: location
  tags: tags
  kind: 'TextTranslation'
  sku: {
    name: 'F0'
  }
  identity: {
    type: 'None'
  }
  properties: {
    customSubDomainName: translatorAccountName
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
      ipRules: []
      virtualNetworkRules: []
    }
  }
}

resource translatorDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-translator-to-log'
  scope: translator
  properties: {
    workspaceId: workspace.id
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

var cognitiveServicesUserRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')

resource translatorUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(translator.id, vm.id, cognitiveServicesUserRoleId)
  scope: translator
  properties: {
    principalId: vm.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: cognitiveServicesUserRoleId
  }
}

resource privateZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.cognitiveservices.azure.com'
  location: 'global'
  tags: tags
}

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = if (deployPrivateEndpoint) {
  name: 'pe-translator'
  location: location
  tags: tags
  properties: {
    customNetworkInterfaceName: 'nic-pe-translator'
    subnet: {
      id: resourceId('Microsoft.Network/virtualNetworks/subnets', vnet.name, 'snet-private-endpoint')
    }
    privateLinkServiceConnections: [
      {
        name: 'translator-account'
        properties: {
          privateLinkServiceId: translator.id
          groupIds: [
            'account'
          ]
        }
      }
    ]
    ipConfigurations: [
      {
        name: 'ipconfig-translator'
        properties: {
          groupId: 'account'
          memberName: 'default'
          privateIPAddress: '10.61.2.4'
        }
      }
    ]
  }
}

resource zoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = if (deployPrivateEndpoint) {
  parent: privateEndpoint
  name: 'translator-zone-group'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'cognitiveservices'
        properties: {
          privateDnsZoneId: privateZone.id
        }
      }
    ]
  }
}

output translatorName string = translator.name
output translatorFqdn string = '${translator.name}.cognitiveservices.azure.com'
output privateEndpointName string = deployPrivateEndpoint ? privateEndpoint.name : ''
output privateEndpointIp string = '10.61.2.4'
output privateDnsZone string = privateZone.name
