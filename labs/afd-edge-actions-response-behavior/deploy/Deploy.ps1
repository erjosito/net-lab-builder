[CmdletBinding()]
param(
    [string]$ResourceGroup = 'rg-afd-edge-response-lab',
    [string]$Location = 'swedencentral',
    [string]$Suffix = 'a8fbd8e1'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$runId = Get-Date -Format 'yyyyMMddTHHmmssZ'
$labDir = Split-Path $PSScriptRoot -Parent
$buildDir = Join-Path $labDir 'build'
$outputDir = Join-Path $labDir 'evidence'
$appDir = Join-Path $labDir 'app'
$edgeActionFile = Join-Path $labDir 'edge-actions\response-probe.js'
$bicepFile = Join-Path $PSScriptRoot 'main.bicep'
$eaApi = '2025-12-01-preview'
$cdnApi = '2025-04-15'
$cdnPreviewApi = '2025-09-01-preview'
$eaName = 'earesponseprobe'

New-Item -ItemType Directory -Force -Path $buildDir, $outputDir | Out-Null

$account = az account show -o json | ConvertFrom-Json
if (-not $account.id) {
    throw 'Run az login before deploying.'
}
$subscriptionId = $account.id

$featureState = az feature show --namespace Microsoft.Cdn --name EdgeActionsPrivatePreview --query properties.state -o tsv
if ($featureState -ne 'Registered') {
    Write-Warning "Legacy EdgeActionsPrivatePreview feature state is $featureState. Continuing with the public-preview API."
}

az group create --name $ResourceGroup --location $Location `
    --tags lab=afd-edge-actions-response-behavior created_by=copilot-lab ephemeral=true run_id=$runId `
    --output none

$deployment = az deployment group create `
    --resource-group $ResourceGroup `
    --name "edge-response-$runId" `
    --template-file $bicepFile `
    --parameters location=$Location runId=$runId suffix=$Suffix `
    --output json | ConvertFrom-Json

$outputs = $deployment.properties.outputs
$appName = $outputs.appName.value
$lawName = $outputs.lawName.value
$afdProfile = $outputs.afdProfileName.value
$endpointName = $outputs.endpointName.value
$endpointHostName = $outputs.endpointHostName.value

$appZip = Join-Path $buildDir 'origin.zip'
Compress-Archive -Path (Join-Path $appDir '*') -DestinationPath $appZip -Force
az webapp deploy --resource-group $ResourceGroup --name $appName `
    --src-path $appZip --type zip --clean true --restart true --output none

$appHealth = "https://$appName.azurewebsites.net/health"
for ($attempt = 1; $attempt -le 30; $attempt++) {
    try {
        $health = Invoke-RestMethod -Uri $appHealth -TimeoutSec 20
        if ($health.status -eq 'healthy') {
            break
        }
    } catch {
        if ($attempt -eq 30) {
            throw
        }
    }
    Start-Sleep -Seconds 10
}

$eaBase = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Cdn/EdgeActions/$eaName"
$eaCreateFile = Join-Path $buildDir 'ea-create.json'
@{
    location = 'global'
    sku = @{
        name = 'Standard'
        tier = 'Standard'
    }
    properties = @{}
} | ConvertTo-Json -Depth 5 | Set-Content $eaCreateFile -Encoding utf8

az rest --method PUT --url "$eaBase`?api-version=$eaApi" `
    --body "@$eaCreateFile" --output none

$lawId = az monitor log-analytics workspace show `
    --resource-group $ResourceGroup --workspace-name $lawName --query id -o tsv
$eaResourceId = "/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Cdn/EdgeActions/$eaName"
$logs = '[{"category":"UserLog","enabled":true},{"category":"ServiceLog","enabled":true}]'
az monitor diagnostic-settings create --resource $eaResourceId --name ea-logs `
    --workspace $lawId --logs $logs --output none

$versionFile = Join-Path $buildDir 'version-create.json'
@{
    location = 'global'
    properties = @{
        deploymentType = 'zip'
        isDefaultVersion = 'True'
    }
} | ConvertTo-Json -Depth 5 | Set-Content $versionFile -Encoding utf8
az rest --method PUT --url "$eaBase/versions/v1?api-version=$eaApi" `
    --body "@$versionFile" --output none

$handlerFile = Join-Path $buildDir 'handler.js'
$edgeZip = Join-Path $buildDir 'edge-action.zip'
Copy-Item $edgeActionFile $handlerFile -Force
Compress-Archive -Path $handlerFile -DestinationPath $edgeZip -Force
$codeFile = Join-Path $buildDir 'deploy-code.json'
@{
    name = 'handler.js'
    content = [Convert]::ToBase64String([IO.File]::ReadAllBytes($edgeZip))
} | ConvertTo-Json -Compress | Set-Content $codeFile -Encoding utf8
az rest --method POST --url "$eaBase/versions/v1/deployVersionCode?api-version=$eaApi" `
    --body "@$codeFile" --output none

for ($attempt = 1; $attempt -le 40; $attempt++) {
    Start-Sleep -Seconds 30
    $version = az rest --method GET --url "$eaBase/versions/v1?api-version=$eaApi" -o json | ConvertFrom-Json
    Write-Host "Edge Action validation: $($version.properties.validationStatus) ($($attempt * 30)s)"
    if ($version.properties.validationStatus -eq 'Failed') {
        throw 'Edge Action code validation failed.'
    }
    if ($version.properties.validationStatus -eq 'Succeeded' -and $attempt -ge 34) {
        break
    }
}

$ruleSetId = "/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Cdn/profiles/$afdProfile/ruleSets/rsresponseprobe"
$ruleSetUrl = "https://management.azure.com$ruleSetId`?api-version=$cdnPreviewApi"
$emptyPropertiesFile = Join-Path $buildDir 'empty-properties.json'
@{ properties = @{} } | ConvertTo-Json | Set-Content $emptyPropertiesFile -Encoding utf8
az rest --method PUT --url $ruleSetUrl --body "@$emptyPropertiesFile" --output none

$ruleFile = Join-Path $buildDir 'rule.json'
@{
    properties = @{
        order = 1
        conditions = @(
            @{
                name = 'UrlPath'
                parameters = @{
                    typeName = 'DeliveryRuleUrlPathMatchConditionParameters'
                    operator = 'BeginsWith'
                    matchValues = @('/ea/')
                    negateCondition = $false
                    transforms = @()
                }
            }
        )
        actions = @(
            @{
                name = 'EdgeAction'
                parameters = @{
                    typeName = 'DeliveryRuleEdgeActionParameters'
                    invocationPoint = 'ClientRequest'
                    edgeActionReference = @{
                        id = $eaResourceId
                    }
                }
            }
        )
    }
} | ConvertTo-Json -Depth 12 | Set-Content $ruleFile -Encoding utf8
$ruleUrl = "https://management.azure.com$ruleSetId/rules/invokeresponseprobe?api-version=$cdnPreviewApi"
az rest --method PUT --url $ruleUrl --body "@$ruleFile" --output none

$routeUrl = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Cdn/profiles/$afdProfile/afdEndpoints/$endpointName/routes/rt-all?api-version=$cdnApi"
$route = az rest --method GET --url $routeUrl -o json | ConvertFrom-Json
$route.properties.ruleSets = @(@{ id = $ruleSetId })
$routeFile = Join-Path $buildDir 'route.json'
$route | ConvertTo-Json -Depth 20 | Set-Content $routeFile -Encoding utf8
az rest --method PUT --url $routeUrl --body "@$routeFile" --output none

$result = [ordered]@{
    runId = $runId
    resourceGroup = $ResourceGroup
    location = $Location
    appName = $appName
    lawName = $lawName
    afdProfile = $afdProfile
    endpointName = $endpointName
    endpointHostName = $endpointHostName
    edgeActionName = $eaName
    edgeActionVersion = 'v1'
    deployedAt = (Get-Date).ToUniversalTime().ToString('o')
}
$result | ConvertTo-Json | Set-Content (Join-Path $outputDir 'deployment-output.json') -Encoding utf8

Write-Host "Waiting 120 seconds for AFD propagation..."
Start-Sleep -Seconds 120
Write-Host "Deployment complete: https://$endpointHostName"
