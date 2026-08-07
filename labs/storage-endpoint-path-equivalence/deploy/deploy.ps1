[CmdletBinding()]
param(
    [string]$CorrelationId = 'sepath-20260805-175837',
    [string]$TranslatorName = 'aisepath0805175837',
    [string]$Location = 'swedencentral'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$suffix = (($CorrelationId -replace '[^a-zA-Z0-9]', '').ToLower())
if ($suffix.Length -gt 10) { $suffix = $suffix.Substring($suffix.Length - 10) }
$rg = "rg-storage-sepath-$suffix"
$targetStorage = "stsepatht$suffix"
$decoyStorage = "stsepathd$suffix"
$labDir = Split-Path $PSScriptRoot -Parent
$runDir = Join-Path $labDir "raw-output\$CorrelationId"
$template = Join-Path $PSScriptRoot 'main.bicep'
$runtimeParams = Join-Path $PSScriptRoot '.runtime.parameters.json'
$probe = Join-Path $PSScriptRoot 'translator_probe.py'
$stateScript = Join-Path $PSScriptRoot 'set-scenario-state.ps1'

if ($Location -ne 'swedencentral') { throw 'The approved redesign is locked to swedencentral.' }
if ((az group exists -n $rg -o tsv).Trim() -ne 'true') { throw "Existing approved lab resource group not found: $rg" }
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

function Assert-Az {
    if ($LASTEXITCODE -ne 0) { throw 'Azure CLI command failed.' }
}

function Test-Az([scriptblock]$Command) {
    & $Command 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
}

function Write-Params([bool]$DeployPrivateEndpoint) {
    @{
        '$schema' = 'https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#'
        contentVersion = '1.0.0.0'
        parameters = @{
            location = @{ value = $Location }
            correlationId = @{ value = $CorrelationId }
            translatorAccountName = @{ value = $TranslatorName }
            deployPrivateEndpoint = @{ value = $DeployPrivateEndpoint }
        }
    } | ConvertTo-Json -Depth 8 | Set-Content $runtimeParams -Encoding utf8
}

function Deploy-Translator([bool]$DeployPrivateEndpoint, [string]$Name) {
    Write-Params $DeployPrivateEndpoint
    az deployment group create -g $rg -n $Name --template-file $template `
        --parameters "@$runtimeParams" --only-show-errors -o none
    Assert-Az
}

function Wait-For-Vm([string]$ExpectedCode) {
    for ($attempt = 1; $attempt -le 40; $attempt++) {
        $vm = az vm get-instance-view -g $rg -n vm-client -o json | ConvertFrom-Json
        $code = ($vm.instanceView.statuses | Where-Object code -Like 'PowerState/*').code
        if ($code -eq $ExpectedCode) { return }
        Start-Sleep -Seconds 15
    }
    throw "VM did not reach $ExpectedCode."
}

function Invoke-Vm([string]$Script) {
    $result = az vm run-command invoke -g $rg -n vm-client --command-id RunShellScript `
        --scripts $Script -o json | ConvertFrom-Json
    Assert-Az
    $message = $result.value[0].message
    if ($message -match '\[stderr\]\s*\S') { throw $message }
    return $message
}

try {
    az bicep build --file $template --stdout | Out-Null
    Assert-Az

    # Preserve R1: deploy the account, diagnostics, RBAC, DNS zone, and NSG first,
    # while the service endpoint and private DNS link remain off.
    Deploy-Translator $false 'sepath-translator-baseline'

    az vm start -g $rg -n vm-client --no-wait -o none
    Assert-Az
    Wait-For-Vm 'PowerState/running'

    $probeText = (Get-Content $probe -Raw) -replace "`r`n", "`n"
    $probeB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($probeText))
    Invoke-Vm "set -e; echo '$probeB64' | base64 -d | sudo tee /opt/sepath/translator_probe.py >/dev/null; sudo chmod 0755 /opt/sepath/translator_probe.py; command -v curl jq dig tcpdump python3 >/dev/null; /opt/sepath/translator_probe.py --endpoint https://$TranslatorName.cognitiveservices.azure.com --expect public" | Out-Null

    # Exact redesign deletion scope. The flow-log account is intentionally absent.
    if (Test-Az { az network private-endpoint show -g $rg -n pe-target-blob -o none }) {
        az network private-endpoint delete -g $rg -n pe-target-blob -o none
        Assert-Az
    }
    if (Test-Az { az network private-dns zone show -g $rg -n privatelink.blob.core.windows.net -o none }) {
        az network private-dns zone delete -g $rg -n privatelink.blob.core.windows.net --yes -o none
        Assert-Az
    }
    if (Test-Az { az network service-endpoint policy show -g $rg -n sep-target-only -o none }) {
        az network service-endpoint policy delete -g $rg -n sep-target-only -o none
        Assert-Az
    }
    foreach ($account in @($targetStorage, $decoyStorage)) {
        if (Test-Az { az storage account show -g $rg -n $account -o none }) {
            az storage account delete -g $rg -n $account --yes -o none
            Assert-Az
        }
    }

    Deploy-Translator $true 'sepath-translator-private'
    & $stateScript -Mode Private -ResourceGroup $rg -TranslatorName $TranslatorName | Out-Null
    Invoke-Vm "set -e; sudo resolvectl flush-caches || true; sleep 10; /opt/sepath/translator_probe.py --endpoint https://$TranslatorName.cognitiveservices.azure.com --expect private" | Out-Null

    # Leave Niobe at R1, not at a restrictive transition.
    & $stateScript -Mode Public -ResourceGroup $rg -TranslatorName $TranslatorName | Out-Null
    Invoke-Vm "set -e; sudo resolvectl flush-caches || true; /opt/sepath/translator_probe.py --endpoint https://$TranslatorName.cognitiveservices.azure.com --expect public" | Out-Null

    az vm deallocate -g $rg -n vm-client --no-wait -o none
    Assert-Az
    Wait-For-Vm 'PowerState/deallocated'
    Write-Host "DEPLOYED: $TranslatorName in $rg; VM deallocated; public baseline restored."
}
finally {
    Remove-Item $runtimeParams -Force -ErrorAction SilentlyContinue
}
