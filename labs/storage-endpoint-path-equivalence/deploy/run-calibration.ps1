[CmdletBinding()]
param(
    [string]$RunId = 'sepath-validation-20260806T133000Z',
    [double]$InjectedDelayMs = 25,
    [int]$Samples = 40,
    [int]$Warmup = 20,
    [double]$IntervalSeconds = 0.5
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$rg = 'rg-storage-sepath-0805175837'
$vm = 'vm-client'
$nic = 'nic-client'
$translator = 'aisepath0805175837'
$endpoint = "https://$translator.cognitiveservices.azure.com"
$labDir = Split-Path $PSScriptRoot -Parent
$runDir = Join-Path $labDir "raw-output\$RunId"
$calibrationDir = Join-Path $runDir 'calibration'
$workDir = Join-Path $calibrationDir '.work'
$stateScript = Join-Path $PSScriptRoot 'set-scenario-state.ps1'
$benchmarkScript = Join-Path $PSScriptRoot 'translator_benchmark.py'
$sanitizer = Join-Path $labDir 'sanitize_results.py'
$uploadScript = Join-Path $PSScriptRoot '.calibration-upload.sh'

New-Item -ItemType Directory -Force -Path $calibrationDir, $workDir | Out-Null

function Assert-Az {
    if ($LASTEXITCODE -ne 0) { throw 'Azure CLI command failed.' }
}

function Wait-PowerState([string]$Expected) {
    for ($attempt = 1; $attempt -le 90; $attempt++) {
        $state = (az vm get-instance-view -g $rg -n $vm --query "instanceView.statuses[?starts_with(code, 'PowerState/')].code | [0]" -o tsv).Trim()
        if ($state -eq $Expected) { return }
        Start-Sleep -Seconds 10
    }
    throw "VM did not reach $Expected."
}

function Save-Sanitized([string]$Text, [string]$Path) {
    $temp = Join-Path $workDir ([IO.Path]::GetRandomFileName())
    Set-Content $temp $Text -Encoding utf8
    python -B $sanitizer $temp $Path
    if ($LASTEXITCODE -ne 0) { throw "Sanitization failed: $Path" }
    Remove-Item $temp -Force
}

function Decode-GzipBase64([string]$Encoded) {
    $bytes = [Convert]::FromBase64String($Encoded.Trim())
    $input = [IO.MemoryStream]::new($bytes)
    $gzip = [IO.Compression.GZipStream]::new($input, [IO.Compression.CompressionMode]::Decompress)
    $reader = [IO.StreamReader]::new($gzip)
    try { return $reader.ReadToEnd() } finally { $reader.Dispose(); $gzip.Dispose(); $input.Dispose() }
}

function Invoke-Vm([string]$Script) {
    $result = az vm run-command invoke -g $rg -n $vm --command-id RunShellScript --scripts $Script -o json | ConvertFrom-Json
    Assert-Az
    $message = $result.value[0].message
    if ($message -match '(?s)\[stdout\]\s*(.*?)\s*\[stderr\]') { return $Matches[1].Trim() }
    return $message.Trim()
}

function Upload-Benchmark {
    $text = (Get-Content $benchmarkScript -Raw) -replace "`r`n", "`n"
    $raw = [Text.Encoding]::UTF8.GetBytes($text)
    $memory = [IO.MemoryStream]::new()
    $gzip = [IO.Compression.GZipStream]::new($memory, [IO.Compression.CompressionMode]::Compress, $true)
    $gzip.Write($raw, 0, $raw.Length)
    $gzip.Dispose()
    $encoded = [Convert]::ToBase64String($memory.ToArray())
    $memory.Dispose()
    @"
echo '$encoded' | base64 -d | gunzip | sudo tee /opt/sepath/translator_benchmark.py >/dev/null
sudo chmod 0755 /opt/sepath/translator_benchmark.py
python3 -m py_compile /opt/sepath/translator_benchmark.py
echo uploaded
"@ | Set-Content $uploadScript -Encoding utf8
    $result = az vm run-command invoke -g $rg -n $vm --command-id RunShellScript --scripts "@$uploadScript" -o json | ConvertFrom-Json
    Assert-Az
    if ($result.value[0].message -notmatch 'uploaded') { throw 'Benchmark upload did not confirm success.' }
}

Save-Sanitized (@{
    schema = 'sepath.translator.calibration.protocol.v1'
    predeclared_before_execution = $true
    mode = 'ordinary public endpoint'
    variant = 'reused HTTPS connection'
    region = 'swedencentral'
    service_sku = 'Translator F0'
    backend_and_request_held_constant = $true
    injected_delay_ms = $InjectedDelayMs
    expected_detectable_p50_shift_ms = @(20, 30)
    blocks = 10
    arm_order = 'control→injected in odd blocks; injected→control in even blocks'
    warmup_requests_per_arm = $Warmup
    measured_requests_per_arm = $Samples
    concurrency = 1
    pacing_seconds = $IntervalSeconds
    primary_detection_rule = '95% bootstrap CI lower bound for paired p50 delta must exceed max(control noise floor, 10% p50 equivalence margin, 5 ms), and point estimate must be 20-30 ms.'
    interpretation_guardrail = 'Calibration proves measurement sensitivity only; it cannot establish path identity.'
} | ConvertTo-Json -Depth 5) (Join-Path $calibrationDir 'protocol.json')

try {
    az vm start -g $rg -n $vm --no-wait -o none
    Assert-Az
    Wait-PowerState 'PowerState/running'
    Upload-Benchmark
    & $stateScript -Mode Public -ResourceGroup $rg -TranslatorName $translator | Out-Null
    Start-Sleep -Seconds 15

    Save-Sanitized (az network nic show-effective-route-table -g $rg -n $nic -o json | Out-String) (Join-Path $calibrationDir 'network-before-routes.json')
    Save-Sanitized (az network nic list-effective-nsg -g $rg -n $nic -o json | Out-String) (Join-Path $calibrationDir 'network-before-nsg.json')

    for ($block = 1; $block -le 10; $block++) {
        $blockDir = Join-Path $calibrationDir "block-$('{0:D2}' -f $block)"
        New-Item -ItemType Directory -Force -Path $blockDir | Out-Null
        $seed = 2026080700 + $block
        $command = "sudo resolvectl flush-caches || true; sleep 2; " +
            "/opt/sepath/translator_benchmark.py --endpoint '$endpoint' --mode public " +
            "--variant reused --block $block --seed $seed --warmup $Warmup --samples $Samples " +
            "--interval $IntervalSeconds --calibration-delay-ms $InjectedDelayMs --gzip-base64"
        $json = Decode-GzipBase64 (Invoke-Vm $command)
        Save-Sanitized $json (Join-Path $blockDir 'calibration.json')
        $vmId = (az vm show -g $rg -n $vm --query id -o tsv).Trim()
        Save-Sanitized (az monitor metrics list --resource $vmId --metric 'Percentage CPU,CPU Credits Remaining' --interval PT1M --aggregation Average -o json | Out-String) (Join-Path $blockDir 'vm-metrics.json')
    }

    Save-Sanitized (az network nic show-effective-route-table -g $rg -n $nic -o json | Out-String) (Join-Path $calibrationDir 'network-after-routes.json')
    Save-Sanitized (az network nic list-effective-nsg -g $rg -n $nic -o json | Out-String) (Join-Path $calibrationDir 'network-after-nsg.json')
    python -B (Join-Path $labDir 'analyze_calibration.py') $runDir | Set-Content (Join-Path $calibrationDir 'analysis-run.json')
    Assert-Az
    python -B $sanitizer (Join-Path $calibrationDir 'calibration-analysis.json') (Join-Path $calibrationDir 'calibration-analysis.json')
    Assert-Az
}
finally {
    try {
        & $stateScript -Mode Public -ResourceGroup $rg -TranslatorName $translator | Out-Null
        az vm deallocate -g $rg -n $vm --no-wait -o none
        Wait-PowerState 'PowerState/deallocated'
    } finally {
        Remove-Item $uploadScript -Force -ErrorAction SilentlyContinue
        Remove-Item $workDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Calibration complete: $calibrationDir"
