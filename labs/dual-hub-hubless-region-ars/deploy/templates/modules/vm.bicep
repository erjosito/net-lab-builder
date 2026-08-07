// Endpoint or NVA VM — Ubuntu 22.04, Standard SSD, no PIP
// charter: no PIP on VMs; IP forwarding controllable

@description('VM name')
param name string

param location string
param tags object

@description('Resource ID of subnet')
param subnetId string

@description('Static private IP (empty = dynamic)')
param privateIpAddress string = ''

param adminUsername string

@description('SSH public key value (not path)')
param sshPublicKey string

@description('VM size — B2ts_v2 preferred, B2ls_v2 fallback')
param vmSize string = 'Standard_B2ts_v2'

@description('Enable IP forwarding on NIC (NVAs only)')
param enableIpForwarding bool = false

@description('Base64-encoded cloud-init custom data (NVAs only)')
param customData string = ''

var nicName = 'nic-${name}'
var osDiskName = 'osdisk-${name}'

resource nic 'Microsoft.Network/networkInterfaces@2023-09-01' = {
  name: nicName
  location: location
  tags: tags
  properties: {
    enableIPForwarding: enableIpForwarding
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          subnet: { id: subnetId }
          privateIPAllocationMethod: empty(privateIpAddress) ? 'Dynamic' : 'Static'
          privateIPAddress: empty(privateIpAddress) ? null : privateIpAddress
        }
      }
    ]
  }
}

resource vm 'Microsoft.Compute/virtualMachines@2023-09-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    hardwareProfile: { vmSize: vmSize }
    storageProfile: {
      osDisk: {
        name: osDiskName
        createOption: 'FromImage'
        managedDisk: { storageAccountType: 'StandardSSD_LRS' }
      }
      imageReference: {
        publisher: 'Canonical'
        offer: '0001-com-ubuntu-server-jammy'
        sku: '22_04-lts-gen2'
        version: 'latest'
      }
    }
    osProfile: {
      computerName: name
      adminUsername: adminUsername
      customData: empty(customData) ? null : customData
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
        { id: nic.id }
      ]
    }
  }
}

output id string = vm.id
output nicId string = nic.id
output privateIp string = nic.properties.ipConfigurations[0].properties.privateIPAddress
