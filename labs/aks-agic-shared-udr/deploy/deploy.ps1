<#
 .SYNOPSIS  Deploy/clean up the aks-agic-shared-udr baseline lab (Internet default route; no forced tunnel).
 .EXAMPLE   .\deploy.ps1 -Action Preflight
            .\deploy.ps1 -Action Group
            .\deploy.ps1 -Action Base -WhatIfOnly   # validate + what-if only
            .\deploy.ps1 -Action Base               # validate + what-if + apply
            .\deploy.ps1 -Action Aks
            .\deploy.ps1 -Action App
            .\deploy.ps1 -Action Cleanup            # preview only
            .\deploy.ps1 -Action Cleanup -ConfirmDelete rg-aks-agic-shared-udr
 Uses the current az subscription; no subscription/tenant IDs are stored.
#>
param(
  [Parameter(Mandatory)][ValidateSet('Preflight','Group','Base','Aks','App','Cleanup')][string]$Action,
  [string]$ResourceGroup = 'rg-aks-agic-shared-udr',
  [string]$Location = 'swedencentral',
  [string]$NvaSize = 'Standard_B2ts_v2',
  [string]$SshKeyFile = "$HOME\.ssh\id_rsa.pub",
  [switch]$WhatIfOnly,
  [string]$ConfirmDelete,
  [int]$TimeoutSeconds = 1200
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$ctl = Join-Path $root '.runtime-control'
$logDir = Join-Path $root 'logs'
New-Item -ItemType Directory -Force $ctl, $logDir | Out-Null
function Log($m) { $l = "$(Get-Date -Format u) $m"; Add-Content (Join-Path $logDir 'deploy.log') $l; Write-Host $l }
function Test-Stop { if (Test-Path (Join-Path $ctl 'STOP')) { throw 'STOP file present; refusing to continue.' } }
$tags = @{ lab = 'aks-agic-shared-udr'; ephemeral = 'true'; owner = 'lab-builder' }

function Get-Feature {
  az feature show --namespace Microsoft.Network --name EnableApplicationGatewayNetworkIsolation --query properties.state -o tsv
}
function Wait-Deployment($name) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    Start-Sleep 20
    $s = az deployment group show -g $ResourceGroup -n $name --query properties.provisioningState -o tsv
    Log "deployment $name state=$s"
  } while ($s -in 'Running','Accepted','Creating','Updating' -and (Get-Date) -lt $deadline)
  $s
}
function Invoke-Bicep($file, $name, $paramArgs) {
  $f = Join-Path $root "infra\$file"
  Log "validate $name"
  az deployment group validate -g $ResourceGroup -n $name -f $f @paramArgs -o none
  if ($LASTEXITCODE) { throw "validate failed" }
  Log "what-if $name"
  az deployment group what-if -g $ResourceGroup -n $name -f $f @paramArgs --no-pretty-print --query "changes[].{op:changeType,res:resourceId}" -o tsv | ForEach-Object { Log "  $_" }
  if ($WhatIfOnly) { return }
  Test-Stop
  Log "apply $name"
  az deployment group create -g $ResourceGroup -n $name -f $f @paramArgs --no-wait -o none
  if ($LASTEXITCODE) { throw "create failed" }
  $s = Wait-Deployment $name
  Log "RESULT $name $s"
  if ($s -ne 'Succeeded') { az deployment operation group list -g $ResourceGroup -n $name --query "[?properties.provisioningState=='Failed'].{r:properties.targetResource.resourceName,m:properties.statusMessage}" -o json; throw "$name $s" }
}

switch ($Action) {
  'Preflight' {
    "AppGW network isolation feature: $(Get-Feature)"
    "Default AKS version: $(az aks get-versions -l $Location --query "values[?isDefault].version | [0]" -o tsv)"
  }
  'Group' {
    if ((Get-Feature) -ne 'NotRegistered') { throw 'Network isolation feature is not NotRegistered; pause for owner decision.' }
    Test-Stop
    $t = $tags.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }
    az group create -n $ResourceGroup -l $Location --tags @t -o table
  }
  'Base' {
    if ((Get-Feature) -ne 'NotRegistered') { throw 'Network isolation feature is not NotRegistered; do not create AppGW.' }
    $pf = Join-Path $ctl 'base.parameters.json'
    $p = @{ '$schema' = 'https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#'; contentVersion = '1.0.0.0'
      parameters = @{ sshPublicKey = @{ value = (Get-Content $SshKeyFile -Raw).Trim() }; nvaSize = @{ value = $NvaSize }; tags = @{ value = $tags } } }
    $p | ConvertTo-Json -Depth 6 | Set-Content $pf
    Invoke-Bicep 'base.bicep' 'base' @('--parameters', "@$pf")
  }
  'Aks' {
    $pf = Join-Path $ctl 'aks.parameters.json'
    $p = @{ '$schema' = 'https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#'; contentVersion = '1.0.0.0'
      parameters = @{ tags = @{ value = $tags } } }
    $p | ConvertTo-Json -Depth 6 | Set-Content $pf
    Invoke-Bicep 'aks.bicep' 'aks' @('--parameters', "@$pf")
  }
  'App' {
    Test-Stop
    $kc = Join-Path $ctl 'kubeconfig'
    az aks get-credentials -g $ResourceGroup -n aks1 --file $kc --overwrite-existing -o none
    $env:KUBECONFIG = $kc
    kubectl apply -f (Join-Path $root 'k8s\sample.yaml')
  }
  'Cleanup' {
    Write-Host "PREVIEW: resource group '$ResourceGroup' and everything in it (incl. MC_ node RG) would be deleted:"
    az resource list -g $ResourceGroup --query "[].{name:name,type:type}" -o table
    az group list --query "[?starts_with(name,'MC_${ResourceGroup}_')].name" -o tsv
    if ($ConfirmDelete -ceq $ResourceGroup) { Test-Stop; Log "DELETE $ResourceGroup"; az group delete -n $ResourceGroup --yes --no-wait }
    else { Write-Host "No deletion. Re-run with -ConfirmDelete $ResourceGroup to delete." }
  }
}