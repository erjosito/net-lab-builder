targetScope = 'resourceGroup'

@description('SSH public key value for the DC2 endpoint VM')
param vmSshPublicKey string

@description('VM admin username')
param adminUsername string = 'labadmin'

@description('VM size selected by the mandatory capacity preflight')
param vmSize string = 'Standard_B2ts_v2'

var location = 'polandcentral'
var tags = {
  lab: 'true'
  created_by: 'copilot-lab'
  run_id: 'lab3d001'
  scenario: 'TP-SQ'
}

resource pipA 'Microsoft.Network/publicIPAddresses@2023-09-01' existing = {
  name: 'pip-gw-onprem2-a'
}

resource pipB 'Microsoft.Network/publicIPAddresses@2023-09-01' existing = {
  name: 'pip-gw-onprem2-b'
}

resource nsg 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: 'nsg-ep-onprem2'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'allow-icmp-from-private'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Icmp'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: '10.0.0.0/8'
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'allow-ssh-from-private'
        properties: {
          priority: 120
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '22'
          sourceAddressPrefix: '10.0.0.0/8'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: 'vnet-onprem2'
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.50.0.0/16'
      ]
    }
    subnets: [
      {
        name: 'GatewaySubnet'
        properties: {
          addressPrefix: '10.50.0.0/27'
        }
      }
      {
        name: 'snet-endpoint'
        properties: {
          addressPrefix: '10.50.1.0/27'
          networkSecurityGroup: {
            id: nsg.id
          }
        }
      }
    ]
  }
}

resource gateway 'Microsoft.Network/virtualNetworkGateways@2023-09-01' = {
  name: 'vpngw-onprem2'
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
    activeActive: true
    bgpSettings: {
      asn: 65003
    }
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          publicIPAddress: {
            id: pipA.id
          }
          subnet: {
            id: resourceId('Microsoft.Network/virtualNetworks/subnets', vnet.name, 'GatewaySubnet')
          }
          privateIPAllocationMethod: 'Dynamic'
        }
      }
      {
        name: 'ipconfig2'
        properties: {
          publicIPAddress: {
            id: pipB.id
          }
          subnet: {
            id: resourceId('Microsoft.Network/virtualNetworks/subnets', vnet.name, 'GatewaySubnet')
          }
          privateIPAllocationMethod: 'Dynamic'
        }
      }
    ]
    vpnGatewayGeneration: 'Generation1'
  }
}

resource nic 'Microsoft.Network/networkInterfaces@2023-09-01' = {
  name: 'nic-vm-onprem2-ep'
  location: location
  tags: tags
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          subnet: {
            id: resourceId('Microsoft.Network/virtualNetworks/subnets', vnet.name, 'snet-endpoint')
          }
          privateIPAllocationMethod: 'Static'
          privateIPAddress: '10.50.1.4'
        }
      }
    ]
  }
}

resource vm 'Microsoft.Compute/virtualMachines@2023-09-01' = {
  name: 'vm-onprem2-ep'
  location: location
  tags: tags
  properties: {
    hardwareProfile: {
      vmSize: vmSize
    }
    storageProfile: {
      osDisk: {
        name: 'osdisk-vm-onprem2-ep'
        createOption: 'FromImage'
        managedDisk: {
          storageAccountType: 'StandardSSD_LRS'
        }
      }
      imageReference: {
        publisher: 'Canonical'
        offer: '0001-com-ubuntu-server-jammy'
        sku: '22_04-lts-gen2'
        version: 'latest'
      }
    }
    osProfile: {
      computerName: 'vm-onprem2-ep'
      adminUsername: adminUsername
      linuxConfiguration: {
        disablePasswordAuthentication: true
        ssh: {
          publicKeys: [
            {
              path: '/home/${adminUsername}/.ssh/authorized_keys'
              keyData: vmSshPublicKey
            }
          ]
        }
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: nic.id
        }
      ]
    }
  }
}

output gatewayId string = gateway.id
output gatewayAsn int = gateway.properties.bgpSettings.asn
output endpointPrivateIp string = nic.properties.ipConfigurations[0].properties.privateIPAddress
