// kubenet AKS (Free, 1 node) with the AGIC managed add-on bound to the existing Application Gateway.
param location string = resourceGroup().location
param nodeSize string = 'Standard_D2as_v5'
param kubernetesVersion string = '1.35'
param tags object = {}

var contributor = 'b24988ac-6180-42a0-ab88-20f7382dd24c'
var reader = 'acdd72a7-3385-48ef-bd42-f606fba81ae7'
var networkContributor = '4d97b98b-1d4f-4787-a291-c67834d212e7'

resource idAks 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: 'id-aks'
}

resource vnetSpoke 'Microsoft.Network/virtualNetworks@2024-05-01' existing = {
  name: 'vnet-spoke'
}

resource agw 'Microsoft.Network/applicationGateways@2024-05-01' existing = {
  name: 'agw1'
}

resource aks 'Microsoft.ContainerService/managedClusters@2025-05-01' = {
  name: 'aks1'
  location: location
  tags: tags
  sku: { name: 'Base', tier: 'Free' }
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${idAks.id}': {} }
  }
  properties: {
    dnsPrefix: 'aks1-agic-udr'
    kubernetesVersion: kubernetesVersion
    agentPoolProfiles: [
      {
        name: 'system'
        mode: 'System'
        count: 1
        vmSize: nodeSize
        osType: 'Linux'
        type: 'VirtualMachineScaleSets'
        vnetSubnetID: '${vnetSpoke.id}/subnets/snet-aks'
      }
    ]
    networkProfile: {
      networkPlugin: 'kubenet'
      podCidr: '10.244.0.0/16'
      serviceCidr: '10.0.0.0/16'
      dnsServiceIP: '10.0.0.10'
      loadBalancerSku: 'standard'
      outboundType: 'loadBalancer'
    }
    addonProfiles: {
      ingressApplicationGateway: {
        enabled: true
        config: { applicationGatewayId: agw.id }
      }
    }
  }
}

var agicPrincipalId = aks.properties.addonProfiles.ingressApplicationGateway.identity.objectId

resource raAgw 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(agw.id, 'agic', contributor)
  scope: agw
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', contributor)
    principalId: agicPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource raRg 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, 'agic', reader)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', reader)
    principalId: agicPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource raVnet 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vnetSpoke.id, 'agic', networkContributor)
  scope: vnetSpoke
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', networkContributor)
    principalId: agicPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output clusterName string = aks.name
output nodeResourceGroup string = aks.properties.nodeResourceGroup