#Requires -Version 7.0
<#
.SYNOPSIS
  Runs timestamped bidirectional application probes without changing infrastructure.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$InventoryPath,

    [Parameter(Mandatory)]
    [ValidatePattern('^[a-z0-9][a-z0-9-]*(?:/[a-z0-9][a-z0-9-]*)*$')]
    [string]$Phase,

    [ValidateSet('D1', 'D2', 'D3')]
    [string]$Design = 'D2',

    [ValidateRange(2, 3600)]
    [int]$DurationSeconds = 120,

    [ValidateRange(1, 60)]
    [int]$IntervalSeconds = 5,

    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$LabRoot = Split-Path -Parent $PSScriptRoot
$Inventory = Get-Content (Resolve-Path $InventoryPath) -Raw | ConvertFrom-Json
$Stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$OutputDir = Join-Path $LabRoot "show-output\$Phase\$Stamp"
$AzureOutputFile = Join-Path $OutputDir 'timed-application-probes-azure-to-gcp.txt'
$GcpOutputFile = Join-Path $OutputDir 'timed-application-probes-gcp-to-azure.txt'
$targets = @($Inventory.probe.designTargets.$Design)

if ($DryRun) {
    Write-Host "[DRY-RUN] Every ${IntervalSeconds}s for ${DurationSeconds}s:"
    foreach ($target in $targets) {
        Write-Host "  Azure VM -> ICMP $($target.ip), HTTP $($target.url)"
    }
    Write-Host "  GCP CPE -> $($Inventory.probe.azureUrlFromGcp)"
    exit 0
}

foreach ($value in @(
    $Inventory.azure.resourceGroup,
    $Inventory.azure.workloadVmName,
    $Inventory.gcp.projectId,
    $Inventory.gcp.zone,
    $Inventory.gcp.cpeVmName,
    $Inventory.probe.azureWorkloadIp,
    $Inventory.probe.azureUrlFromGcp,
    $targets
)) {
    if (-not $value -or [string]$value -match '^<') {
        throw 'Inventory is incomplete; timed probes refuse to run with placeholders.'
    }
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$targetTokens = $targets | ForEach-Object { "'$($_.ip)|$($_.url)'" }
$azureCommand = @"
end=`$((SECONDS+$DurationSeconds))
while [ `$SECONDS -lt `$end ]; do
  for target in $($targetTokens -join ' '); do
    ip=`${target%%|*}
    url=`${target#*|}
    ts=`$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)
    if ping -c 1 -W 2 "`$ip" >/dev/null 2>&1; then icmp=PASS; else icmp=FAIL; fi
    http=`$(curl -sS -o /dev/null --connect-timeout 2 --max-time 4 -w '%{http_code},%{time_connect},%{time_total}' "`$url" 2>&1)
    rc=`$?
    echo "`$ts direction=azure-to-gcp target=`$ip icmp=`$icmp tcp_exit=`$rc http=`$http"
  done
  sleep $IntervalSeconds
done
"@

$sourceTokens = $targets | ForEach-Object { "'$($_.ip)'" }
$gcpCommand = @"
end=`$((SECONDS+$DurationSeconds))
while [ `$SECONDS -lt `$end ]; do
  for source in $($sourceTokens -join ' '); do
    ts=`$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)
    if ping -I "`$source" -c 1 -W 2 "$($Inventory.probe.azureWorkloadIp)" >/dev/null 2>&1; then icmp=PASS; else icmp=FAIL; fi
    http=`$(curl --interface "`$source" -sS -o /dev/null --connect-timeout 2 --max-time 4 -w '%{http_code},%{time_connect},%{time_total}' "$($Inventory.probe.azureUrlFromGcp)" 2>&1)
    rc=`$?
    echo "`$ts direction=gcp-to-azure source=`$source target=$($Inventory.probe.azureWorkloadIp) icmp=`$icmp tcp_exit=`$rc http=`$http"
  done
  sleep $IntervalSeconds
done
"@

$azureJob = Start-Job -ArgumentList @(
    [string]$Inventory.azure.resourceGroup,
    [string]$Inventory.azure.workloadVmName,
    $azureCommand
) -ScriptBlock {
    param($ResourceGroup, $VmName, $Command)
    az vm run-command invoke -g $ResourceGroup -n $VmName --command-id RunShellScript `
        --scripts $Command --query 'value[0].message' -o tsv 2>&1
    Write-Output "collector_exit=$LASTEXITCODE"
}
$gcpJob = Start-Job -ArgumentList @(
    [string]$Inventory.gcp.cpeVmName,
    [string]$Inventory.gcp.zone,
    [string]$Inventory.gcp.projectId,
    $gcpCommand
) -ScriptBlock {
    param($VmName, $Zone, $Project, $Command)
    gcloud compute ssh $VmName --zone $Zone --project $Project --quiet --command $Command 2>&1
    Write-Output "collector_exit=$LASTEXITCODE"
}

Wait-Job -Job $azureJob, $gcpJob | Out-Null
$azureRaw = Receive-Job -Job $azureJob | Out-String
$gcpRaw = Receive-Job -Job $gcpJob | Out-String
Remove-Job -Job $azureJob, $gcpJob -Force

function Protect-ProbeOutput {
    param([string]$Text)
    $safe = $Text -replace '(?i)(/subscriptions/)[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', '$1<SUBSCRIPTION_ID>'
    if ($Inventory.gcp.projectId -and $Inventory.gcp.projectId -notmatch '^<') {
        $safe = $safe -replace [regex]::Escape([string]$Inventory.gcp.projectId), '<GCP_PROJECT_ID>'
    }
    return $safe
}

Set-Content -Path $AzureOutputFile -Value (Protect-ProbeOutput $azureRaw) -Encoding utf8
Set-Content -Path $GcpOutputFile -Value (Protect-ProbeOutput $gcpRaw) -Encoding utf8

& (Join-Path $PSScriptRoot 'Confirm-Sanitization.ps1') -Path $OutputDir
Write-Host $OutputDir
