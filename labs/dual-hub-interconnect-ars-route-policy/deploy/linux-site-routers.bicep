targetScope = 'resourceGroup'

@description('SSH public key for the site router VMs')
param adminPublicKey string

@description('VM administrator username')
param adminUsername string = 'labadmin'

@description('VM size selected by catalog and live-capacity preflight')
param vmSize string = 'Standard_B2ts_v2'

var tags = {
  lab: 'true'
  created_by: 'copilot-lab'
  run_id: 'lab3d001'
  scenario: 'TP-SQ-LINUX-SITES'
}

var cloudInit = loadTextContent('cloud-init-linux-site-router.yaml')
var routerSecurityRules = [
  {
    name: 'Allow-SSH-2222'
    properties: {
      priority: 100
      direction: 'Inbound'
      access: 'Allow'
      protocol: 'Tcp'
      sourcePortRange: '*'
      destinationPortRange: '2222'
      sourceAddressPrefix: '*'
      destinationAddressPrefix: '*'
    }
  }
  {
    name: 'Allow-IKE'
    properties: {
      priority: 110
      direction: 'Inbound'
      access: 'Allow'
      protocol: 'Udp'
      sourcePortRange: '*'
      destinationPortRanges: [
        '500'
        '4500'
      ]
      sourceAddressPrefix: '*'
      destinationAddressPrefix: '*'
    }
  }
  {
    name: 'Allow-ESP'
    properties: {
      priority: 120
      direction: 'Inbound'
      access: 'Allow'
      protocol: 'Esp'
      sourcePortRange: '*'
      destinationPortRange: '*'
      sourceAddressPrefix: '*'
      destinationAddressPrefix: '*'
    }
  }
  {
    name: 'Allow-ICMP'
    properties: {
      priority: 130
      direction: 'Inbound'
      access: 'Allow'
      protocol: 'Icmp'
      sourcePortRange: '*'
      destinationPortRange: '*'
      sourceAddressPrefix: '*'
      destinationAddressPrefix: '*'
    }
  }
]

resource dc1Vnet 'Microsoft.Network/virtualNetworks@2023-09-01' existing = {
  name: 'vnet-onprem'
}

resource dc2Vnet 'Microsoft.Network/virtualNetworks@2023-09-01' existing = {
  name: 'vnet-onprem2'
}

resource dc1Nsg 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: 'nsg-router-dc1'
  location: 'norwayeast'
  tags: tags
  properties: {
    securityRules: routerSecurityRules
  }
}

resource dc2Nsg 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: 'nsg-router-dc2'
  location: 'polandcentral'
  tags: tags
  properties: {
    securityRules: routerSecurityRules
  }
}

resource dc1Subnet 'Microsoft.Network/virtualNetworks/subnets@2023-09-01' = {
  parent: dc1Vnet
  name: 'snet-router'
  properties: {
    addressPrefix: '10.40.2.0/27'
    networkSecurityGroup: {
      id: dc1Nsg.id
    }
  }
}

resource dc2Subnet 'Microsoft.Network/virtualNetworks/subnets@2023-09-01' = {
  parent: dc2Vnet
  name: 'snet-router'
  properties: {
    addressPrefix: '10.50.2.0/27'
    networkSecurityGroup: {
      id: dc2Nsg.id
    }
  }
}

resource dc1Pip 'Microsoft.Network/publicIPAddresses@2023-09-01' = {
  name: 'pip-router-dc1'
  location: 'norwayeast'
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

resource dc2Pip 'Microsoft.Network/publicIPAddresses@2023-09-01' = {
  name: 'pip-router-dc2'
  location: 'polandcentral'
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

resource dc1Nic 'Microsoft.Network/networkInterfaces@2023-09-01' = {
  name: 'nic-router-dc1'
  location: 'norwayeast'
  tags: tags
  properties: {
    enableIPForwarding: true
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          privateIPAllocationMethod: 'Static'
          privateIPAddress: '10.40.2.4'
          subnet: {
            id: dc1Subnet.id
          }
          publicIPAddress: {
            id: dc1Pip.id
          }
        }
      }
    ]
  }
}

resource dc2Nic 'Microsoft.Network/networkInterfaces@2023-09-01' = {
  name: 'nic-router-dc2'
  location: 'polandcentral'
  tags: tags
  properties: {
    enableIPForwarding: true
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          privateIPAllocationMethod: 'Static'
          privateIPAddress: '10.50.2.4'
          subnet: {
            id: dc2Subnet.id
          }
          publicIPAddress: {
            id: dc2Pip.id
          }
        }
      }
    ]
  }
}

resource dc1Vm 'Microsoft.Compute/virtualMachines@2024-03-01' = {
  name: 'vm-router-dc1'
  location: 'norwayeast'
  tags: tags
  properties: {
    hardwareProfile: {
      vmSize: vmSize
    }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: 'ubuntu-24_04-lts'
        sku: 'server'
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        managedDisk: {
          storageAccountType: 'StandardSSD_LRS'
        }
        diskSizeGB: 30
      }
    }
    osProfile: {
      computerName: 'router-dc1'
      adminUsername: adminUsername
      customData: base64(cloudInit)
      linuxConfiguration: {
        disablePasswordAuthentication: true
        ssh: {
          publicKeys: [
            {
              path: '/home/${adminUsername}/.ssh/authorized_keys'
              keyData: adminPublicKey
            }
          ]
        }
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: dc1Nic.id
        }
      ]
    }
  }
}

resource dc2Vm 'Microsoft.Compute/virtualMachines@2024-03-01' = {
  name: 'vm-router-dc2'
  location: 'polandcentral'
  tags: tags
  properties: {
    hardwareProfile: {
      vmSize: vmSize
    }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: 'ubuntu-24_04-lts'
        sku: 'server'
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        managedDisk: {
          storageAccountType: 'StandardSSD_LRS'
        }
        diskSizeGB: 30
      }
    }
    osProfile: {
      computerName: 'router-dc2'
      adminUsername: adminUsername
      customData: base64(cloudInit)
      linuxConfiguration: {
        disablePasswordAuthentication: true
        ssh: {
          publicKeys: [
            {
              path: '/home/${adminUsername}/.ssh/authorized_keys'
              keyData: adminPublicKey
            }
          ]
        }
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: dc2Nic.id
        }
      ]
    }
  }
}

resource dc1RouteTable 'Microsoft.Network/routeTables@2023-09-01' = {
  name: 'rt-endpoint-dc1'
  location: 'norwayeast'
  tags: tags
  properties: {
    disableBgpRoutePropagation: false
    routes: [
      {
        name: 'private-via-router'
        properties: {
          addressPrefix: '10.0.0.0/8'
          nextHopType: 'VirtualAppliance'
          nextHopIpAddress: '10.40.2.4'
        }
      }
    ]
  }
}

resource dc2RouteTable 'Microsoft.Network/routeTables@2023-09-01' = {
  name: 'rt-endpoint-dc2'
  location: 'polandcentral'
  tags: tags
  properties: {
    disableBgpRoutePropagation: false
    routes: [
      {
        name: 'private-via-router'
        properties: {
          addressPrefix: '10.0.0.0/8'
          nextHopType: 'VirtualAppliance'
          nextHopIpAddress: '10.50.2.4'
        }
      }
    ]
  }
}

output dc1PublicIp string = dc1Pip.properties.ipAddress
output dc2PublicIp string = dc2Pip.properties.ipAddress
output dc1PrivateIp string = '10.40.2.4'
output dc2PrivateIp string = '10.50.2.4'
