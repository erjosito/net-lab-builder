targetScope = 'resourceGroup'

param location string = 'swedencentral'
param runId string
param suffix string

var names = {
  law: 'law-edge-response-${suffix}'
  plan: 'asp-edge-response-${suffix}'
  app: 'app-edge-response-${suffix}'
  afd: 'afd-edge-response-${suffix}'
  endpoint: 'edge-response-${suffix}'
}

var tags = {
  lab: 'afd-edge-actions-response-behavior'
  created_by: 'copilot-lab'
  ephemeral: 'true'
  run_id: runId
}

resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: names.law
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: names.plan
  location: location
  tags: tags
  kind: 'linux'
  sku: {
    name: 'B1'
    tier: 'Basic'
  }
  properties: {
    reserved: true
  }
}

resource app 'Microsoft.Web/sites@2023-12-01' = {
  name: names.app
  location: location
  tags: tags
  kind: 'app,linux'
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'NODE|20-lts'
      alwaysOn: true
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      appSettings: [
        {
          name: 'WEBSITE_RUN_FROM_PACKAGE'
          value: '1'
        }
        {
          name: 'NODE_ENV'
          value: 'production'
        }
      ]
    }
  }
}

resource afd 'Microsoft.Cdn/profiles@2025-04-15' = {
  name: names.afd
  location: 'global'
  tags: tags
  sku: {
    name: 'Standard_AzureFrontDoor'
  }
}

resource endpoint 'Microsoft.Cdn/profiles/afdEndpoints@2025-04-15' = {
  parent: afd
  name: names.endpoint
  location: 'global'
  tags: tags
  properties: {
    enabledState: 'Enabled'
  }
}

resource originGroup 'Microsoft.Cdn/profiles/originGroups@2025-04-15' = {
  parent: afd
  name: 'og-origin'
  properties: {
    loadBalancingSettings: {
      sampleSize: 4
      successfulSamplesRequired: 3
      additionalLatencyInMilliseconds: 50
    }
    healthProbeSettings: {
      probePath: '/health'
      probeRequestType: 'GET'
      probeProtocol: 'Https'
      probeIntervalInSeconds: 30
    }
    sessionAffinityState: 'Disabled'
  }
}

resource origin 'Microsoft.Cdn/profiles/originGroups/origins@2025-04-15' = {
  parent: originGroup
  name: 'origin-app'
  properties: {
    hostName: app.properties.defaultHostName
    httpPort: 80
    httpsPort: 443
    originHostHeader: app.properties.defaultHostName
    priority: 1
    weight: 1000
    enabledState: 'Enabled'
    enforceCertificateNameCheck: true
  }
}

resource route 'Microsoft.Cdn/profiles/afdEndpoints/routes@2025-04-15' = {
  parent: endpoint
  name: 'rt-all'
  properties: {
    originGroup: {
      id: originGroup.id
    }
    supportedProtocols: [
      'Https'
    ]
    patternsToMatch: [
      '/*'
    ]
    forwardingProtocol: 'HttpsOnly'
    httpsRedirect: 'Enabled'
    linkToDefaultDomain: 'Enabled'
    enabledState: 'Enabled'
  }
  dependsOn: [
    origin
  ]
}

resource afdDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-afd'
  scope: afd
  properties: {
    workspaceId: law.id
    logs: [
      {
        category: 'FrontDoorAccessLog'
        enabled: true
      }
      {
        category: 'FrontDoorHealthProbeLog'
        enabled: true
      }
    ]
  }
}

resource appDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-app'
  scope: app
  properties: {
    workspaceId: law.id
    logs: [
      {
        category: 'AppServiceHTTPLogs'
        enabled: true
      }
      {
        category: 'AppServiceConsoleLogs'
        enabled: true
      }
    ]
  }
}

output lawName string = law.name
output appName string = app.name
output afdProfileName string = afd.name
output endpointName string = endpoint.name
output endpointHostName string = endpoint.properties.hostName
