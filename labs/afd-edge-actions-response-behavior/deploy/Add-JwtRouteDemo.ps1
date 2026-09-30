[CmdletBinding()]
param(
    [string]$ResourceGroup = 'rg-afd-edge-response-lab'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$labDir = Split-Path $PSScriptRoot -Parent
$outputFile = Join-Path $labDir 'evidence\deployment-output.json'
$sourceFile = Join-Path $labDir 'edge-actions\jwt-route-demo.js'
$buildDir = Join-Path $labDir 'build\jwt-route-demo'
$eaApi = '2025-12-01-preview'
$cdnApi = '2025-04-15'
$cdnPreviewApi = '2025-09-01-preview'
$eaName = 'eajwtvisual'

$deployment = Get-Content $outputFile -Raw | ConvertFrom-Json
$subscriptionId = (az account show --query id -o tsv)
$eaBase = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Cdn/EdgeActions/$eaName"

New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

$eaCreateFile = Join-Path $buildDir 'ea-create.json'
@{
    location = 'global'
    sku = @{ name = 'Standard'; tier = 'Standard' }
    properties = @{}
} | ConvertTo-Json -Depth 5 | Set-Content $eaCreateFile -Encoding utf8
az rest --method PUT --url "$eaBase`?api-version=$eaApi" `
    --body "@$eaCreateFile" --output none

$lawId = az monitor log-analytics workspace show `
    --resource-group $ResourceGroup --workspace-name $deployment.lawName --query id -o tsv
$eaResourceId = "/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Cdn/EdgeActions/$eaName"
$logs = '[{"category":"UserLog","enabled":true},{"category":"ServiceLog","enabled":true}]'
az monitor diagnostic-settings create --resource $eaResourceId --name ea-logs `
    --workspace $lawId --logs $logs --output none

$versionJson = az rest --method GET --url "$eaBase/versions/v1?api-version=$eaApi" -o json 2>$null
if (-not $versionJson) {
    $versionFile = Join-Path $buildDir 'version-create.json'
    @{
        location = 'global'
        properties = @{ deploymentType = 'zip'; isDefaultVersion = 'True' }
    } | ConvertTo-Json -Depth 5 | Set-Content $versionFile -Encoding utf8
    az rest --method PUT --url "$eaBase/versions/v1?api-version=$eaApi" `
        --body "@$versionFile" --output none

    $handlerFile = Join-Path $buildDir 'handler.js'
    $edgeZip = Join-Path $buildDir 'edge-action.zip'
    Copy-Item $sourceFile $handlerFile -Force
    Compress-Archive -Path $handlerFile -DestinationPath $edgeZip -Force
    $codeFile = Join-Path $buildDir 'deploy-code.json'
    @{
        name = 'handler.js'
        content = [Convert]::ToBase64String([IO.File]::ReadAllBytes($edgeZip))
    } | ConvertTo-Json -Compress | Set-Content $codeFile -Encoding utf8
    az rest --method POST --url "$eaBase/versions/v1/deployVersionCode?api-version=$eaApi" `
        --body "@$codeFile" --output none
}

for ($attempt = 1; $attempt -le 40; $attempt++) {
    Start-Sleep -Seconds 30
    $version = az rest --method GET --url "$eaBase/versions/v1?api-version=$eaApi" -o json |
        ConvertFrom-Json
    Write-Host "JWT demo provisioning: $($version.properties.provisioningState); validation: $($version.properties.validationStatus)"
    if ($version.properties.provisioningState -eq 'Failed' -or
        $version.properties.validationStatus -eq 'Failed') {
        throw 'JWT route demo Edge Action deployment failed.'
    }
    if ($version.properties.provisioningState -eq 'Succeeded' -and
        $version.properties.validationStatus -eq 'Succeeded') {
        break
    }
}

if ($version.properties.provisioningState -ne 'Succeeded') {
    throw 'JWT route demo Edge Action did not finish provisioning.'
}

$ruleSetId = "/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Cdn/profiles/$($deployment.afdProfile)/ruleSets/rsedgejwt"
$ruleSetUrl = "https://management.azure.com$ruleSetId`?api-version=$cdnPreviewApi"
$emptyPropertiesFile = Join-Path $buildDir 'empty-properties.json'
@{ properties = @{} } | ConvertTo-Json | Set-Content $emptyPropertiesFile -Encoding utf8
az rest --method PUT --url $ruleSetUrl --body "@$emptyPropertiesFile" --output none

$ruleFile = Join-Path $buildDir 'rule.json'
@{
    properties = @{
        order = 2
        conditions = @(
            @{
                name = 'UrlPath'
                parameters = @{
                    typeName = 'DeliveryRuleUrlPathMatchConditionParameters'
                    operator = 'BeginsWith'
                    matchValues = @('/protected', '/admin')
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
                    edgeActionReference = @{ id = $eaResourceId }
                }
            }
        )
    }
} | ConvertTo-Json -Depth 12 | Set-Content $ruleFile -Encoding utf8
$ruleUrl = "https://management.azure.com$ruleSetId/rules/ruleprotected?api-version=$cdnPreviewApi"
az rest --method PUT --url $ruleUrl --body "@$ruleFile" --output none

$baseRouteUrl = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Cdn/profiles/$($deployment.afdProfile)/afdEndpoints/$($deployment.endpointName)/routes/rt-all?api-version=$cdnApi"
$routeUrl = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Cdn/profiles/$($deployment.afdProfile)/afdEndpoints/$($deployment.endpointName)/routes/rt-jwt?api-version=$cdnApi"
$baseRoute = az rest --method GET --url $baseRouteUrl -o json | ConvertFrom-Json
$baseRoute.properties.patternsToMatch = @('/ea/*', '/control', '/public', '/health')
$baseRouteFile = Join-Path $buildDir 'route-base.json'
$baseRoute | ConvertTo-Json -Depth 20 | Set-Content $baseRouteFile -Encoding utf8
az rest --method PUT --url $baseRouteUrl --body "@$baseRouteFile" --output none
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to restrict rt-all patterns.'
}

$route = @{
    properties = @{
        originGroup = $baseRoute.properties.originGroup
        originPath = $baseRoute.properties.originPath
        supportedProtocols = $baseRoute.properties.supportedProtocols
        patternsToMatch = @('/protected', '/protected/*', '/admin', '/admin/*')
        forwardingProtocol = $baseRoute.properties.forwardingProtocol
        linkToDefaultDomain = $baseRoute.properties.linkToDefaultDomain
        httpsRedirect = $baseRoute.properties.httpsRedirect
        enabledState = 'Enabled'
        ruleSets = @(@{ id = $ruleSetId })
    }
}
$routeFile = Join-Path $buildDir 'route.json'
$route | ConvertTo-Json -Depth 20 | Set-Content $routeFile -Encoding utf8
az rest --method PUT --url $routeUrl --body "@$routeFile" --output none
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to create rt-jwt.'
}

Write-Host 'JWT route reproduction deployed. Allow several minutes for edge propagation.'
