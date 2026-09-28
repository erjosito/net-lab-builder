#Requires -Version 7.0
<#
.SYNOPSIS
  Executes one approved command and writes an audit-grade evidence bundle.

.DESCRIPTION
  Intended for deployment, configuration, fault, restore, query and assertion
  transcripts. It preserves sanitized command text, stdout, stderr, timestamps,
  context, exit code, expected effect and before/after evidence correlations.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('deployment','configuration','fault','restore','query','assertion')]
    [string]$ActionType,

    [Parameter(Mandatory)]
    [string]$Scenario,

    [Parameter(Mandatory)]
    [string]$QuestionId,

    [Parameter(Mandatory)]
    [ValidateSet('before','action','during','after','assertion')]
    [string]$State,

    [Parameter(Mandatory)]
    [string]$ExpectedEffect,

    [Parameter(Mandatory)]
    [string]$Command,

    [Parameter(Mandatory)]
    [string]$OutputDirectory,

    [string]$CorrelationId = '',
    [string[]]$BeforeEvidence = @(),
    [string[]]$AfterEvidence = @(),
    [string]$ObservedEffect = '',
    [switch]$AllowFailure
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Protect-Text {
    param([AllowEmptyString()][string]$Text)
    $safe = $Text
    $safe = $safe -replace '(?i)(authorization:\s*bearer\s+)\S+', '$1<REDACTED>'
    $safe = $safe -replace '(?i)(--(?:shared-key|psk|password|client-secret|api-key|api-secret)\s+)(?:"[^"]*"|''[^'']*''|\S+)', '$1<REDACTED>'
    $safe = $safe -replace '(?i)("(?:serviceKey|pairingKey|preSharedKey|sharedKey|access_token|client_secret|apiKey|apiSecret)"\s*:\s*")[^"]+(")', '$1<REDACTED>$2'
    $safe = $safe -replace '(?i)(\$?(?:psk|sharedKey|preSharedKey)\s*=\s*)(?:"[^"]*"|''[^'']*''|[^;\s,}''"]+)', '$1<REDACTED>'
    $safe = $safe -replace '(?i)(MEGAPORT_(?:API|ACCESS|SECRET)_(?:KEY|SECRET)\s*=\s*)(?:"[^"]*"|''[^'']*''|[^;\s,}]+)', '$1<REDACTED>'
    $safe = $safe -replace '(?i)(/subscriptions/)[^/\s,\]]+', '$1<SUBSCRIPTION>'
    $safe = $safe -replace '(?i)(--billing-account(?:=|\s+))\S+', '$1<BILLING_ACCOUNT>'
    $safe = $safe -replace '(?i)(billingAccounts/)[0-9A-Za-z-]+', '$1<BILLING_ACCOUNT>'
    $safe = $safe -replace '(?<![A-Za-z0-9_.-])eyJ[A-Za-z0-9_-]{7,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?![A-Za-z0-9_.-])', '<REDACTED_TOKEN>'
    $safe = $safe -replace '(?i)\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b', '<GUID>'
    $safe = $safe -replace '(?i)([\w.+-]+)@([\w.-]+\.[A-Za-z]{2,})', '<ACCOUNT>'
    return $safe
}

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
$slug = "$stamp-$ActionType-$State"
$commandPath = Join-Path $OutputDirectory "$slug.command.txt"
$stdoutPath = Join-Path $OutputDirectory "$slug.stdout.txt"
$stderrPath = Join-Path $OutputDirectory "$slug.stderr.txt"
$metadataPath = Join-Path $OutputDirectory "$slug.metadata.json"

$safeCommand = Protect-Text $Command
Set-Content -Path $commandPath -Value $safeCommand -Encoding utf8

$start = Get-Date
$psi = [System.Diagnostics.ProcessStartInfo]::new()
$psi.FileName = (Get-Command pwsh).Source
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.CreateNoWindow = $true
$psi.ArgumentList.Add('-NoProfile')
$psi.ArgumentList.Add('-NonInteractive')
$psi.ArgumentList.Add('-Command')
$psi.ArgumentList.Add($Command)

$process = [System.Diagnostics.Process]::new()
$process.StartInfo = $psi
$null = $process.Start()
$stdoutTask = $process.StandardOutput.ReadToEndAsync()
$stderrTask = $process.StandardError.ReadToEndAsync()
$process.WaitForExit()
$stdoutTask.Wait()
$stderrTask.Wait()
$end = Get-Date

$stdout = Protect-Text $stdoutTask.Result
$stderr = Protect-Text $stderrTask.Result
Set-Content -Path $stdoutPath -Value $stdout -Encoding utf8
Set-Content -Path $stderrPath -Value $stderr -Encoding utf8

$toolContext = [ordered]@{
    powershell = $PSVersionTable.PSVersion.ToString()
    azureCli = Protect-Text ((az version -o json 2>&1 | Out-String).Trim())
    gcloud = Protect-Text ((gcloud version --format=json 2>&1 | Out-String).Trim())
    terraform = Protect-Text ((terraform version -json 2>&1 | Out-String).Trim())
    git = Protect-Text ((git --version 2>&1 | Out-String).Trim())
    azureAccount = Protect-Text ((az account show --query '{name:name,userType:user.type}' -o json 2>&1 | Out-String).Trim())
    gcpContext = Protect-Text ((gcloud config list core/project --format=json 2>&1 | Out-String).Trim())
}

$metadata = [ordered]@{
    schemaVersion = 1
    correlationId = if ($CorrelationId) { $CorrelationId } else { $stamp }
    scenario = $Scenario
    questionId = $QuestionId
    actionType = $ActionType
    state = $State
    expectedEffect = $ExpectedEffect
    observedEffect = $ObservedEffect
    commandFile = Split-Path $commandPath -Leaf
    stdoutFile = Split-Path $stdoutPath -Leaf
    stderrFile = Split-Path $stderrPath -Leaf
    beforeEvidence = @($BeforeEvidence)
    afterEvidence = @($AfterEvidence)
    utcStarted = $start.ToUniversalTime().ToString('o')
    utcEnded = $end.ToUniversalTime().ToString('o')
    localStarted = $start.ToString('o')
    localEnded = $end.ToString('o')
    timezone = [System.TimeZoneInfo]::Local.Id
    durationMs = [math]::Round(($end - $start).TotalMilliseconds)
    exitCode = $process.ExitCode
    succeeded = ($process.ExitCode -eq 0)
    host = [Environment]::MachineName
    os = [System.Runtime.InteropServices.RuntimeInformation]::OSDescription
    toolContext = $toolContext
    workingDirectory = '<REPOSITORY_ROOT>'
}
Set-Content -Path $metadataPath -Value (Protect-Text ($metadata | ConvertTo-Json -Depth 8)) -Encoding utf8

Write-Host $metadataPath
if ($process.ExitCode -ne 0 -and -not $AllowFailure) {
    exit $process.ExitCode
}
