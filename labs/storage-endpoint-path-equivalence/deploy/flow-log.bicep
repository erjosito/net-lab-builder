targetScope = 'resourceGroup'

param location string
param correlationId string
param networkWatcherName string
param flowLogName string
param targetResourceId string
param storageId string
param workspaceCustomerId string
param workspaceResourceId string

var tags = {
  lab: 'true'
  created_by: 'copilot-lab'
  lab_name: 'storage-endpoint-path-equivalence'
  owner: 'jose'
  ephemeral: 'true'
  correlation_id: correlationId
}

resource networkWatcher 'Microsoft.Network/networkWatchers@2024-05-01' existing = {
  name: networkWatcherName
}

resource flowLog 'Microsoft.Network/networkWatchers/flowLogs@2024-05-01' = {
  parent: networkWatcher
  name: flowLogName
  location: location
  tags: tags
  properties: {
    enabled: true
    targetResourceId: targetResourceId
    storageId: storageId
    format: {
      type: 'JSON'
      version: 2
    }
    flowAnalyticsConfiguration: {
      networkWatcherFlowAnalyticsConfiguration: {
        enabled: true
        workspaceId: workspaceCustomerId
        workspaceRegion: location
        workspaceResourceId: workspaceResourceId
        trafficAnalyticsInterval: 10
      }
    }
    retentionPolicy: {
      days: 0
      enabled: false
    }
  }
}

output flowLogName string = flowLog.name
