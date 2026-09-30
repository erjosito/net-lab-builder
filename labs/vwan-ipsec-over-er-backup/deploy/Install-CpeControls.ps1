#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$InventoryPath
)

$ErrorActionPreference = 'Stop'
$inventory = Get-Content (Resolve-Path $InventoryPath) -Raw | ConvertFrom-Json
$applyScript = Join-Path $PSScriptRoot 'cpe\apply-design.sh'
$routingScript = Join-Path $PSScriptRoot 'cpe\apply-routing-design.sh'
$faultScript = Join-Path $PSScriptRoot 'cpe\fault-control.sh'
$target = "$($inventory.gcp.cpeVmName):/tmp/"

gcloud compute scp $applyScript $routingScript $faultScript $target --project $inventory.gcp.projectId `
    --zone $inventory.gcp.zone --tunnel-through-iap --quiet
if ($LASTEXITCODE -ne 0) { throw 'CPE control upload failed.' }

gcloud compute ssh $inventory.gcp.cpeVmName --project $inventory.gcp.projectId `
    --zone $inventory.gcp.zone --tunnel-through-iap --quiet --command `
    "sudo install -m 0700 /tmp/apply-design.sh /opt/vwan-lab/apply-design.sh; sudo install -m 0700 /tmp/apply-routing-design.sh /opt/vwan-lab/apply-routing-design.sh; sudo install -m 0700 /tmp/fault-control.sh /opt/vwan-lab/fault-control.sh; rm -f /tmp/apply-design.sh /tmp/apply-routing-design.sh /tmp/fault-control.sh"
if ($LASTEXITCODE -ne 0) { throw 'CPE control installation failed.' }

Write-Output 'CPE_CONTROLS_READY=true'
