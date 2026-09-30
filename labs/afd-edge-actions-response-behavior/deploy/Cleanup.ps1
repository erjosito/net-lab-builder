[CmdletBinding()]
param(
    [string]$ResourceGroup = 'rg-afd-edge-response-lab',
    [switch]$Confirmed
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$outputFile = Join-Path $PSScriptRoot '..\evidence\deployment-output.json'
if (-not (Test-Path $outputFile)) {
    throw "Deployment output not found: $outputFile"
}
$deployment = Get-Content $outputFile -Raw | ConvertFrom-Json
$account = az account show -o json | ConvertFrom-Json
$subscriptionId = $account.id
$eaApi = '2025-12-01-preview'
$cdnPreviewApi = '2025-09-01-preview'

Write-Host "Would delete:"
Write-Host "  Resource group: $ResourceGroup"
Write-Host "  Edge Action: $($deployment.edgeActionName)"
Write-Host "  Edge Action: eajwtvisual"

if (-not $Confirmed) {
    Write-Host 'Preview only. Re-run with -Confirmed after explicit approval.'
    return
}

$cdnApi = '2025-04-15'
$routeUrl = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Cdn/profiles/$($deployment.afdProfile)/afdEndpoints/$($deployment.endpointName)/routes/rt-all?api-version=$cdnApi"
$route = az rest --method GET --url $routeUrl -o json | ConvertFrom-Json
$route.properties.ruleSets = @($route.properties.ruleSets | Where-Object {
    $_.id -notlike '*/ruleSets/rsresponseprobe' -and
    $_.id -notlike '*/ruleSets/rsedgejwt'
})
$routeFile = Join-Path $PSScriptRoot '..\build\cleanup-route.json'
$route | ConvertTo-Json -Depth 20 | Set-Content $routeFile -Encoding utf8
az rest --method PUT --url $routeUrl --body "@$routeFile" --output none

$jwtRouteUrl = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Cdn/profiles/$($deployment.afdProfile)/afdEndpoints/$($deployment.endpointName)/routes/rt-jwt?api-version=$cdnApi"
az rest --method DELETE --url $jwtRouteUrl --output none 2>$null

$ruleSets = @(
    @{ Name = 'rsresponseprobe'; Rule = 'invokeresponseprobe' },
    @{ Name = 'rsedgejwt'; Rule = 'ruleprotected' }
)
foreach ($ruleSet in $ruleSets) {
    $ruleSetBase = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Cdn/profiles/$($deployment.afdProfile)/ruleSets/$($ruleSet.Name)"
    az rest --method DELETE --url "$ruleSetBase/rules/$($ruleSet.Rule)?api-version=$cdnPreviewApi" --output none 2>$null
    az rest --method DELETE --url "$ruleSetBase`?api-version=$cdnPreviewApi" --output none 2>$null
}

$edgeActions = @($deployment.edgeActionName, 'eajwtvisual')
foreach ($edgeAction in $edgeActions) {
    $eaBase = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Cdn/EdgeActions/$edgeAction"
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        $eaJson = az rest --method GET --url "$eaBase`?api-version=$eaApi" -o json 2>$null
        if (-not $eaJson) {
            break
        }
        $ea = $eaJson | ConvertFrom-Json
        if (-not $ea.properties.attachments -or $ea.properties.attachments.Count -eq 0) {
            break
        }
        Start-Sleep -Seconds 10
    }

    $versionsJson = az rest --method GET --url "$eaBase/versions?api-version=$eaApi" -o json 2>$null
    if ($versionsJson) {
        $versions = ($versionsJson | ConvertFrom-Json).value |
            Sort-Object { $_.properties.isDefaultVersion -eq 'True' }
        foreach ($version in $versions) {
            az rest --method DELETE --url "$eaBase/versions/$($version.name)?api-version=$eaApi" --output none
        }
    }
    az rest --method DELETE --url "$eaBase`?api-version=$eaApi" --output none 2>$null
}

az group delete --name $ResourceGroup --yes --no-wait
