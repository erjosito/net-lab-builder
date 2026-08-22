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

if (-not $Confirmed) {
    Write-Host 'Preview only. Re-run with -Confirmed after explicit approval.'
    return
}

$ruleSetBase = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Cdn/profiles/$($deployment.afdProfile)/ruleSets/rsresponseprobe"
az rest --method DELETE --url "$ruleSetBase/rules/invokeresponseprobe?api-version=$cdnPreviewApi" --output none
az rest --method DELETE --url "$ruleSetBase`?api-version=$cdnPreviewApi" --output none

$eaBase = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Cdn/EdgeActions/$($deployment.edgeActionName)"
for ($attempt = 1; $attempt -le 30; $attempt++) {
    $ea = az rest --method GET --url "$eaBase`?api-version=$eaApi" -o json 2>$null | ConvertFrom-Json
    if (-not $ea.properties.attachments -or $ea.properties.attachments.Count -eq 0) {
        break
    }
    Start-Sleep -Seconds 10
}

az rest --method DELETE --url "$eaBase/versions/v1?api-version=$eaApi" --output none
az rest --method DELETE --url "$eaBase`?api-version=$eaApi" --output none
az group delete --name $ResourceGroup --yes --no-wait
