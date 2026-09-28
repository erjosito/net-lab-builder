#Requires -Version 7.0
<#
.SYNOPSIS
  Enforces design-prefix isolation and healthy-reset evidence before the next experiment.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$InventoryPath,

    [Parameter(Mandatory)]
    [string]$EvidencePath,

    [Parameter(Mandatory)]
    [ValidateSet('D1', 'D2', 'D3')]
    [string]$ExpectedDesign,

    [ValidateRange(1, 100)]
    [int]$MinimumExpectedPrefixObservations = 2
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$assertStarted = Get-Date

$Inventory = Get-Content (Resolve-Path $InventoryPath) -Raw | ConvertFrom-Json
$EvidencePath = (Resolve-Path $EvidencePath).Path
$files = Get-ChildItem -Path $EvidencePath -Recurse -File -Include '*.txt','*.json','*.jsonl'
if (-not $files) {
    throw "No evidence files found under $EvidencePath"
}

$content = ($files | ForEach-Object { Get-Content $_.FullName -Raw }) -join "`n"
$prefixSets = $Inventory.expected.designPrefixes
$expected = @($prefixSets.$ExpectedDesign)
$forbidden = @()
foreach ($design in @('D1', 'D2', 'D3')) {
    if ($design -ne $ExpectedDesign) {
        $forbidden += @($prefixSets.$design)
    }
}

$failures = [System.Collections.Generic.List[string]]::new()
foreach ($prefix in $expected) {
    $count = ([regex]::Matches($content, [regex]::Escape([string]$prefix))).Count
    if ($count -lt $MinimumExpectedPrefixObservations) {
        $failures.Add("Expected prefix $prefix observed $count time(s), minimum is $MinimumExpectedPrefixObservations.")
    }
}
foreach ($prefix in ($forbidden | Sort-Object -Unique)) {
    $count = ([regex]::Matches($content, [regex]::Escape([string]$prefix))).Count
    if ($count -gt 0) {
        $failures.Add("Contamination: forbidden prefix $prefix observed $count time(s).")
    }
}

$healthSignals = [ordered]@{
    providerProvisioned = '(?i)serviceProviderProvisioningState.{0,80}Provisioned'
    bgpEstablished = '(?i)(Established|ESTABLISHED)'
    ipsecInstalled = '(?i)(ESTABLISHED|INSTALLED)'
    primaryPath = '(?i)(primary|Primary)'
    secondaryPath = '(?i)(secondary|Secondary)'
}
foreach ($signal in $healthSignals.GetEnumerator()) {
    if ($content -notmatch $signal.Value) {
        $failures.Add("Missing healthy reset signal: $($signal.Key).")
    }
}

$probeFiles = $files | Where-Object Name -like 'timed-application-probes-*.txt'
if (-not $probeFiles) {
    $failures.Add('Missing timestamped probe files.')
} else {
    $probeContent = ($probeFiles | ForEach-Object { Get-Content $_.FullName -Raw }) -join "`n"
    $successCount = ([regex]::Matches($probeContent, '(?m)icmp=PASS\s+tcp_exit=0')).Count
    if ($successCount -lt 4) {
        $failures.Add("Only $successCount successful ICMP+TCP samples; require at least four across both directions and two intervals.")
    }
}

$verdict = [ordered]@{
    utc = (Get-Date).ToUniversalTime().ToString('o')
    expectedDesign = $ExpectedDesign
    evidencePath = $EvidencePath
    passed = ($failures.Count -eq 0)
    failures = @($failures)
}
$verdictPath = Join-Path $EvidencePath 'reset-gate-verdict.json'
$verdict | ConvertTo-Json -Depth 5 | Set-Content -Path $verdictPath -Encoding utf8
$assertEnded = Get-Date
$command = "pwsh .\scripts\Assert-ResetGate.ps1 -InventoryPath '<RUNTIME_INVENTORY>' -EvidencePath '$EvidencePath' -ExpectedDesign $ExpectedDesign -MinimumExpectedPrefixObservations $MinimumExpectedPrefixObservations"
$stderr = if ($failures.Count) { $failures -join [Environment]::NewLine } else { '' }
$stdout = if ($failures.Count) { 'RESET GATE FAIL' } else { "RESET GATE PASS: $ExpectedDesign; no cross-design prefix contamination found." }
Set-Content (Join-Path $EvidencePath 'reset-gate.command.txt') $command -Encoding utf8
Set-Content (Join-Path $EvidencePath 'reset-gate.stdout.txt') $stdout -Encoding utf8
Set-Content (Join-Path $EvidencePath 'reset-gate.stderr.txt') $stderr -Encoding utf8
$assertMetadata = [ordered]@{
    schemaVersion = 1
    correlationId = [string]$Inventory.runId
    scenario = 'restore'
    questionId = 'Q-RESET-CONTAMINATION'
    plane = 'cross-plane'
    actionType = 'assertion'
    state = 'assertion'
    expectedEffect = "Only $ExpectedDesign experiment prefixes remain and all mandatory health signals and bidirectional probes pass."
    observedEffect = $stdout
    commandFile = 'reset-gate.command.txt'
    stdoutFile = 'reset-gate.stdout.txt'
    stderrFile = 'reset-gate.stderr.txt'
    combinedFile = 'reset-gate-verdict.json'
    utcStarted = $assertStarted.ToUniversalTime().ToString('o')
    utcEnded = $assertEnded.ToUniversalTime().ToString('o')
    localStarted = $assertStarted.ToString('o')
    localEnded = $assertEnded.ToString('o')
    durationMs = [math]::Round(($assertEnded - $assertStarted).TotalMilliseconds)
    exitCode = if ($failures.Count) { 1 } else { 0 }
    succeeded = ($failures.Count -eq 0)
    workingDirectory = '<REPOSITORY_ROOT>'
}
$assertMetadata | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $EvidencePath 'reset-gate.metadata.json') -Encoding utf8

if ($failures.Count -gt 0) {
    $failures | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Host $stdout
