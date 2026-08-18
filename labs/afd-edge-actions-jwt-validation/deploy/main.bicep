// afd-edge-actions-jwt-validation — Foundation Bicep (A0)
// Tank · 2026-08-17
// Deploys: Resource Group (via CLI), Log Analytics, App Service Plan + App, AFD Standard profile,
//          AFD endpoint / origin group / origin / route, and diagnostic settings.
// Edge Actions (A2+) and Entra app registrations (A1) are deployed via PowerShell/az-rest
// in Deploy-Lab.ps1 because they use preview APIs not modelled in stable Bicep providers.

targetScope = 'resourceGroup'

@description('Azure region for all resources')
param location string = 'swedencentral'

@description('Correlation run ID — set by deploy script')
param runId string = 'manual'

@description('App Service Plan SKU — B1 (or F1 if quota allows)')
@allowed(['B1', 'F1'])
param appServicePlanSku string = 'B1'

// ─── Tags applied to every resource ───────────────────────────────────────────
var commonTags = {
  lab: 'afd-edge-actions-jwt-validation'
  env: 'lab'
  owner: 'jose'
  'created-by': 'copilot-lab'
  ephemeral: 'true'
  'run-id': runId
}

// ─── Log Analytics Workspace ──────────────────────────────────────────────────
resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'law-edge-jwt-lab'
  location: location
  tags: commonTags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// ─── App Service Plan ─────────────────────────────────────────────────────────
resource asp 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: 'asp-edge-jwt-lab'
  location: location
  tags: commonTags
  kind: 'linux'
  sku: {
    name: appServicePlanSku
    tier: appServicePlanSku == 'F1' ? 'Free' : 'Basic'
  }
  properties: {
    reserved: true  // Linux
  }
}

// ─── App Service ──────────────────────────────────────────────────────────────
resource app 'Microsoft.Web/sites@2023-12-01' = {
  name: 'app-edge-jwt-lab'
  location: location
  tags: commonTags
  kind: 'app,linux'
  properties: {
    serverFarmId: asp.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'NODE|20-lts'
      alwaysOn: appServicePlanSku != 'F1'
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      http20Enabled: true
      appSettings: [
        // Non-secret config only. Entra IDs are injected by deploy script after A1.
        {
          name: 'WEBSITE_RUN_FROM_PACKAGE'
          value: '1'
        }
        {
          name: 'NODE_ENV'
          value: 'production'
        }
        {
          name: 'LAB_RUN_ID'
          value: runId
        }
      ]
    }
  }
}

// ─── AFD Standard Profile ────────────────────────────────────────────────────
resource afdProfile 'Microsoft.Cdn/profiles@2025-04-15' = {
  name: 'afd-edge-jwt-lab'
  location: 'global'
  tags: commonTags
  sku: {
    name: 'Standard_AzureFrontDoor'
  }
}

// ─── AFD Endpoint ─────────────────────────────────────────────────────────────
resource afdEndpoint 'Microsoft.Cdn/profiles/afdEndpoints@2025-04-15' = {
  parent: afdProfile
  name: 'edge-jwt-lab'
  location: 'global'
  tags: commonTags
  properties: {
    enabledState: 'Enabled'
  }
}

// ─── Origin Group ─────────────────────────────────────────────────────────────
resource originGroup 'Microsoft.Cdn/profiles/originGroups@2025-04-15' = {
  parent: afdProfile
  name: 'og-appservice'
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

// ─── Origin ───────────────────────────────────────────────────────────────────
resource origin 'Microsoft.Cdn/profiles/originGroups/origins@2025-04-15' = {
  parent: originGroup
  name: 'app-edge-jwt-lab'
  properties: {
    hostName: 'app-edge-jwt-lab.azurewebsites.net'
    httpPort: 80
    httpsPort: 443
    originHostHeader: 'app-edge-jwt-lab.azurewebsites.net'
    priority: 1
    weight: 1000
    enabledState: 'Enabled'
    enforceCertificateNameCheck: true
  }
}

// ─── AFD Route (all paths → App Service) ──────────────────────────────────────
resource afdRoute 'Microsoft.Cdn/profiles/afdEndpoints/routes@2025-04-15' = {
  parent: afdEndpoint
  name: 'rt-api'
  properties: {
    originGroup: {
      id: originGroup.id
    }
    supportedProtocols: ['Https']
    patternsToMatch: ['/*']
    forwardingProtocol: 'HttpsOnly'
    httpsRedirect: 'Enabled'
    linkToDefaultDomain: 'Enabled'
    enabledState: 'Enabled'
  }
  dependsOn: [origin]
}

// ─── AFD Diagnostic Settings → Log Analytics ─────────────────────────────────
resource afdDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-afd-edge-jwt-lab'
  scope: afdProfile
  properties: {
    workspaceId: law.id
    logs: [
      {
        category: 'FrontDoorAccessLog'
        enabled: true
        retentionPolicy: { enabled: false, days: 0 }
      }
      {
        category: 'FrontDoorWebApplicationFirewallLog'
        enabled: true
        retentionPolicy: { enabled: false, days: 0 }
      }
      {
        category: 'FrontDoorHealthProbeLog'
        enabled: true
        retentionPolicy: { enabled: false, days: 0 }
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
        retentionPolicy: { enabled: false, days: 0 }
      }
    ]
  }
}

// ─── App Service Diagnostic Settings → Log Analytics ─────────────────────────
resource appDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-app-edge-jwt-lab'
  scope: app
  properties: {
    workspaceId: law.id
    logs: [
      {
        category: 'AppServiceHTTPLogs'
        enabled: true
        retentionPolicy: { enabled: false, days: 0 }
      }
      {
        category: 'AppServiceConsoleLogs'
        enabled: true
        retentionPolicy: { enabled: false, days: 0 }
      }
      {
        category: 'AppServiceAppLogs'
        enabled: true
        retentionPolicy: { enabled: false, days: 0 }
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
        retentionPolicy: { enabled: false, days: 0 }
      }
    ]
  }
}

// ─── Outputs ──────────────────────────────────────────────────────────────────
output appServiceName string = app.name
output appServiceDefaultHostname string = app.properties.defaultHostName
output afdProfileName string = afdProfile.name
output afdEndpointHostname string = afdEndpoint.properties.hostName
output lawId string = law.id
output lawName string = law.name
