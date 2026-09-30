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

    [switch]$SkipIndex,

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

function Protect-Text {
    param([AllowEmptyString()][string]$Text)
    $safe = $Text
    $safe = $safe -replace '(?i)(authorization:\s*bearer\s+)\S+', '$1<REDACTED>'
    $safe = $safe -replace '(?i)(/subscriptions/)[^/\s,\]]+', '$1<SUBSCRIPTION_ID>'
    $safe = $safe -replace '(?i)(--billing-account(?:=|\s+))\S+', '$1<BILLING_ACCOUNT>'
    $safe = $safe -replace '(?i)(billingAccounts/)[0-9A-Za-z-]+', '$1<BILLING_ACCOUNT>'
    $safe = $safe -replace '(?<![A-Za-z0-9_.-])eyJ[A-Za-z0-9_-]{7,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?![A-Za-z0-9_.-])', '<REDACTED_TOKEN>'
    $safe = $safe -replace '(?i)\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b', '<GUID>'
    $safe = $safe -replace '(?i)([\w.+-]+)@([\w.-]+\.[A-Za-z]{2,})', '<ACCOUNT>'
    if ($Inventory.gcp.projectId -and $Inventory.gcp.projectId -notmatch '^<') {
        $safe = $safe -replace [regex]::Escape([string]$Inventory.gcp.projectId), '<GCP_PROJECT_ID>'
    }
    return $safe
}

function Save-ProbeBundle {
    param(
        [string]$BaseName,
        [string]$Direction,
        [string]$Command,
        [string]$Stdout,
        [string]$Stderr,
        [int]$ExitCode,
        [datetime]$Started,
        [datetime]$Ended
    )
    $parentQuestionId = if ($Phase -match '^d2-corrected/.+(fault|during|restore|after|assertion)') {
        'Q-D2-FAULTS'
    } elseif ($Phase -match '^d2-corrected') {
        'Q-D2-PREFERENCE'
    } elseif ($Phase -match '^(d3-prefix|compound)') {
        'Q-D3-PREFIX-BLACKHOLE'
    } elseif ($Phase -match '^(restore|final-healthy)') {
        'Q-RESET-CONTAMINATION'
    } else {
        'Q-APPLICATION-PROBES'
    }
    $safeCommand = Protect-Text $Command
    $safeStdout = Protect-Text $Stdout
    $safeStderr = Protect-Text $Stderr
    Set-Content (Join-Path $OutputDir "$BaseName.command.txt") $safeCommand -Encoding utf8
    Set-Content (Join-Path $OutputDir "$BaseName.stdout.txt") $safeStdout -Encoding utf8
    Set-Content (Join-Path $OutputDir "$BaseName.stderr.txt") $safeStderr -Encoding utf8
    $metadata = [ordered]@{
        schemaVersion = 1
        correlationId = [string]$Inventory.runId
        scenario = $Phase
        questionId = 'Q-APPLICATION-PROBES'
        parentQuestionId = $parentQuestionId
        plane = 'application'
        actionType = 'query'
        state = ($Phase -split '/')[-1]
        direction = $Direction
        expectedEffect = 'Timestamped ICMP and HTTP results correlate application reachability with the active route and fault state.'
        observedEffect = ''
        commandFile = "$BaseName.command.txt"
        stdoutFile = "$BaseName.stdout.txt"
        stderrFile = "$BaseName.stderr.txt"
        utcStarted = $Started.ToUniversalTime().ToString('o')
        utcEnded = $Ended.ToUniversalTime().ToString('o')
        localStarted = $Started.ToString('o')
        localEnded = $Ended.ToString('o')
        durationMs = [math]::Round(($Ended - $Started).TotalMilliseconds)
        exitCode = $ExitCode
        succeeded = ($ExitCode -eq 0)
        workingDirectory = '<REPOSITORY_ROOT>'
    }
    Set-Content (Join-Path $OutputDir "$BaseName.metadata.json") `
        (Protect-Text ($metadata | ConvertTo-Json -Depth 8)) -Encoding utf8
}

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
$azureCommand = $azureCommand -replace "`r`n", "`n"
$gcpCommand = $gcpCommand -replace "`r`n", "`n"

$probeStarted = Get-Date
$azureJob = Start-Job -ArgumentList @(
    [string]$Inventory.azure.resourceGroup,
    [string]$Inventory.azure.workloadVmName,
    $azureCommand
) -ScriptBlock {
    param($ResourceGroup, $VmName, $Command)
    az vm run-command invoke -g $ResourceGroup -n $VmName --command-id RunShellScript `
        --scripts $Command --query 'value[0].message' -o tsv
    Write-Output "collector_exit=$LASTEXITCODE"
}
$gcpJob = Start-Job -ArgumentList @(
    [string]$Inventory.gcp.cpeVmName,
    [string]$Inventory.gcp.zone,
    [string]$Inventory.gcp.projectId,
    $gcpCommand
) -ScriptBlock {
    param($VmName, $Zone, $Project, $Command)
    gcloud compute ssh $VmName --zone $Zone --project $Project --tunnel-through-iap --quiet --command $Command
    Write-Output "collector_exit=$LASTEXITCODE"
}

Wait-Job -Job $azureJob, $gcpJob | Out-Null
$azureRaw = Receive-Job -Job $azureJob | Out-String
$gcpRaw = Receive-Job -Job $gcpJob | Out-String
$azureError = ($azureJob.ChildJobs[0].Error | Out-String)
$gcpError = ($gcpJob.ChildJobs[0].Error | Out-String)
$probeEnded = Get-Date
$azureExit = if ($azureRaw -match 'collector_exit=(\d+)') { [int]$Matches[1] } else { 1 }
$gcpExit = if ($gcpRaw -match 'collector_exit=(\d+)') { [int]$Matches[1] } else { 1 }
Remove-Job -Job $azureJob, $gcpJob -Force
Set-Content -Path $AzureOutputFile -Value (Protect-Text $azureRaw) -Encoding utf8
Set-Content -Path $GcpOutputFile -Value (Protect-Text $gcpRaw) -Encoding utf8
Save-ProbeBundle -BaseName 'timed-probes-azure-to-gcp' -Direction 'azure-to-gcp' `
    -Command "az vm run-command invoke -g $($Inventory.azure.resourceGroup) -n $($Inventory.azure.workloadVmName) --command-id RunShellScript --scripts '<TIMED_PROBE_SCRIPT>'" `
    -Stdout $azureRaw -Stderr $azureError -ExitCode $azureExit -Started $probeStarted -Ended $probeEnded
Save-ProbeBundle -BaseName 'timed-probes-gcp-to-azure' -Direction 'gcp-to-azure' `
    -Command "gcloud compute ssh $($Inventory.gcp.cpeVmName) --zone $($Inventory.gcp.zone) --project $($Inventory.gcp.projectId) --tunnel-through-iap --command '<TIMED_PROBE_SCRIPT>'" `
    -Stdout $gcpRaw -Stderr $gcpError -ExitCode $gcpExit -Started $probeStarted -Ended $probeEnded

if (-not $SkipIndex) {
    & (Join-Path $PSScriptRoot 'New-EvidenceIndex.ps1') -LabRoot $LabRoot
}
& (Join-Path $PSScriptRoot 'Confirm-Sanitization.ps1') -Path $OutputDir
Write-Host $OutputDir
