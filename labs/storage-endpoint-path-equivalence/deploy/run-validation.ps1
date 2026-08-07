[CmdletBinding()]
param(
    [string]$RunId = "sepath-validation-$((Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ'))",
    [int]$Samples = 40,
    [int]$Warmup = 20,
    [double]$IntervalSeconds = 0.5,
    [switch]$SkipUpload,
    [switch]$ResumeAfterR4
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$rg = 'rg-storage-sepath-0805175837'
$vm = 'vm-client'
$nic = 'nic-client'
$translator = 'aisepath0805175837'
$endpoint = "https://$translator.cognitiveservices.azure.com"
$vnet = 'vnet-endpoint-path'
$subnet = 'snet-client'
$zone = 'privatelink.cognitiveservices.azure.com'
$stateScript = Join-Path $PSScriptRoot 'set-scenario-state.ps1'
$benchmarkScript = Join-Path $PSScriptRoot 'translator_benchmark.py'
$labDir = Split-Path $PSScriptRoot -Parent
$runDir = Join-Path $labDir "raw-output\$RunId"
$workDir = Join-Path $runDir '.work'
$sanitizer = Join-Path $labDir 'sanitize_results.py'

New-Item -ItemType Directory -Force -Path $runDir, $workDir | Out-Null

function Assert-Az {
    if ($LASTEXITCODE -ne 0) { throw 'Azure CLI command failed.' }
}

function Wait-PowerState([string]$Expected) {
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        $state = (az vm get-instance-view -g $rg -n $vm --query "instanceView.statuses[?starts_with(code, 'PowerState/')].code | [0]" -o tsv).Trim()
        if ($state -eq $Expected) { return }
        Start-Sleep -Seconds 10
    }
    throw "VM did not reach $Expected."
}

function Save-Sanitized([string]$Text, [string]$Path) {
    $temp = Join-Path $workDir ([IO.Path]::GetRandomFileName())
    Set-Content -Path $temp -Value $Text -Encoding utf8
    python $sanitizer $temp $Path
    if ($LASTEXITCODE -ne 0) { throw "Sanitization failed for $Path" }
    Remove-Item $temp -Force
}

function Save-Az([scriptblock]$Command, [string]$Path) {
    $text = (& $Command 2>&1 | Out-String)
    $exit = $LASTEXITCODE
    Save-Sanitized $text $Path
    if ($exit -ne 0) { Write-Warning "Evidence command failed; preserved at $Path" }
}

function Invoke-Vm([string]$Script) {
    $result = az vm run-command invoke -g $rg -n $vm --command-id RunShellScript --scripts $Script -o json | ConvertFrom-Json
    Assert-Az
    $message = $result.value[0].message
    if ($message -match '(?s)\[stdout\]\s*(.*?)\s*\[stderr\]') { return $Matches[1].Trim() }
    return $message.Trim()
}

function Set-State([string]$Mode, [string]$Path) {
    $baseline = (& $stateScript -Mode Public -ResourceGroup $rg -TranslatorName $translator | Out-String)
    Start-Sleep -Seconds 10
    if ($Mode -ne 'Public') {
        $target = (& $stateScript -Mode $Mode -ResourceGroup $rg -TranslatorName $translator | Out-String)
        Start-Sleep -Seconds 15
    } else {
        $target = $baseline
    }
    Save-Sanitized $target $Path
}

function Decode-Benchmark([string]$Encoded) {
    $bytes = [Convert]::FromBase64String($Encoded.Trim())
    $input = [IO.MemoryStream]::new($bytes)
    $gzip = [IO.Compression.GZipStream]::new($input, [IO.Compression.CompressionMode]::Decompress)
    $reader = [IO.StreamReader]::new($gzip)
    try { return $reader.ReadToEnd() } finally { $reader.Dispose(); $gzip.Dispose(); $input.Dispose() }
}

function Invoke-Benchmark(
    [int]$Block, [int]$Seed, [string]$Mode, [string]$Variant,
    [int]$WarmupCount, [int]$SampleCount, [string]$Path
) {
    $command = "sudo resolvectl flush-caches || true; sleep 2; " +
        "/opt/sepath/translator_benchmark.py --endpoint '$endpoint' --mode '$Mode' " +
        "--variant '$Variant' --block $Block --seed $Seed --warmup $WarmupCount " +
        "--samples $SampleCount --interval $IntervalSeconds --gzip-base64"
    $encoded = Invoke-Vm $command
    $json = Decode-Benchmark $encoded
    Save-Sanitized $json $Path
    return ($json | ConvertFrom-Json)
}

function Capture-State([string]$Scenario, [string]$DestinationIp) {
    $dir = Join-Path $runDir "correctness\$Scenario"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Save-Az { az cognitiveservices account show -g $rg -n $translator --query '{name:name,location:location,kind:kind,sku:sku.name,publicNetworkAccess:properties.publicNetworkAccess,defaultAction:properties.networkAcls.defaultAction,vnetRules:properties.networkAcls.virtualNetworkRules,disableLocalAuth:properties.disableLocalAuth}' -o json } (Join-Path $dir 'account-network-state.json')
    Save-Az { az network vnet subnet show -g $rg --vnet-name $vnet -n $subnet --query '{name:name,addressPrefix:addressPrefix,serviceEndpoints:serviceEndpoints,networkSecurityGroup:networkSecurityGroup.id,natGateway:natGateway.id}' -o json } (Join-Path $dir 'subnet-state.json')
    Save-Az { az network nic show-effective-route-table -g $rg -n $nic -o json } (Join-Path $dir 'effective-routes.json')
    Save-Az { az network nic list-effective-nsg -g $rg -n $nic -o json } (Join-Path $dir 'effective-nsg.json')
    Save-Az { az network private-endpoint show -g $rg -n pe-translator --query '{name:name,ipConfigurations:ipConfigurations,connections:privateLinkServiceConnections[].privateLinkServiceConnectionState}' -o json } (Join-Path $dir 'private-endpoint.json')
    Save-Az { az network private-dns link vnet list -g $rg -z $zone --query '[].{name:name,state:virtualNetworkLinkState,registrationEnabled:registrationEnabled}' -o json } (Join-Path $dir 'private-dns-links.json')
    if ($DestinationIp) {
        Save-Az { az network watcher show-next-hop -g $rg --vm $vm --nic $nic --source-ip 10.61.1.4 --dest-ip $DestinationIp -o json } (Join-Path $dir 'next-hop.json')
    }
    $dns = Invoke-Vm "echo '# dig CNAME/A/AAAA'; dig +noall +answer '$translator.cognitiveservices.azure.com' CNAME; dig +noall +answer '$translator.cognitiveservices.azure.com' A; dig +noall +answer '$translator.cognitiveservices.azure.com' AAAA; echo '# getent'; getent ahosts '$translator.cognitiveservices.azure.com'"
    Save-Sanitized $dns (Join-Path $dir 'dns.txt')
}

try {
    Save-Sanitized (@{
        run_id = $RunId
        region = 'swedencentral'
        sku = 'Translator F0'
        concurrency = 1
        warmup_requests_per_variant = $Warmup
        measured_requests_per_variant = $Samples
        blocks = 10
        interval_seconds = $IntervalSeconds
        margins = @{
            latency_p50_ratio = @(0.90, 1.10)
            latency_p95_ratio = @(0.85, 1.15)
            throughput_ratio = @(0.90, 1.10)
            jitter_ratio = @(0.80, 1.20)
            jitter_absolute_ms = 2
            error_rate_absolute = 0.005
            retransmit_rate_absolute = 0.002
        }
        quota_guard = 'Concurrency 1 only; fixed 19-character request; 0.5-second pacing; no 8/32 concurrency or 8-MiB payload.'
    } | ConvertTo-Json -Depth 5) (Join-Path $runDir 'protocol.json')

    az vm start -g $rg -n $vm --no-wait -o none
    Assert-Az
    Wait-PowerState 'PowerState/running'
    if (-not $SkipUpload) {
        $benchmarkText = (Get-Content $benchmarkScript -Raw) -replace "`r`n", "`n"
        $raw = [Text.Encoding]::UTF8.GetBytes($benchmarkText)
        $compressed = [IO.MemoryStream]::new()
        $gzip = [IO.Compression.GZipStream]::new($compressed, [IO.Compression.CompressionMode]::Compress, $true)
        $gzip.Write($raw, 0, $raw.Length)
        $gzip.Dispose()
        $benchmarkB64 = [Convert]::ToBase64String($compressed.ToArray())
        $compressed.Dispose()
        Invoke-Vm "echo '$benchmarkB64' | base64 -d | gunzip | sudo tee /opt/sepath/translator_benchmark.py >/dev/null; sudo chmod 0755 /opt/sepath/translator_benchmark.py; python3 -m py_compile /opt/sepath/translator_benchmark.py" | Out-Null
    }

    if ($ResumeAfterR4) {
        Set-State 'Public' (Join-Path $workDir 'resume-public-state.json')
        $resumeProbe = Invoke-Benchmark 0 8199 'public' 'fresh' 0 1 (Join-Path $workDir 'resume-public-request.json')
        $publicIp = $resumeProbe[0].records[0].remote_ip
    }

    # R1 ordinary public endpoint.
    if (-not $ResumeAfterR4) {
    $r1Dir = Join-Path $runDir 'correctness\R1-public'
    New-Item -ItemType Directory -Force -Path $r1Dir | Out-Null
    Set-State 'Public' (Join-Path $r1Dir 'transition-state.json')
    $r1 = Invoke-Benchmark 0 8101 'public' 'fresh' 0 1 (Join-Path $r1Dir 'request.json')
    $publicIp = $r1[0].records[0].remote_ip
    Capture-State 'R1-public' $publicIp

    # R2 service endpoint; ordinary and pinned-public calls.
    $r2Dir = Join-Path $runDir 'correctness\R2-service-endpoint'
    New-Item -ItemType Directory -Force -Path $r2Dir | Out-Null
    Set-State 'ServiceEndpoint' (Join-Path $r2Dir 'transition-state.json')
    Invoke-Benchmark 0 8102 'service_endpoint' 'fresh' 0 1 (Join-Path $r2Dir 'ordinary-request.json') | Out-Null
    $forced = Invoke-Vm "set +e; TOKEN=`$(curl -fsS -H Metadata:true 'http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fcognitiveservices.azure.com%2F' | jq -r .access_token); BODY='[{`"Text`":`"Network path probe.`"}]'; CODE=`$(curl -sS --http1.1 --resolve '$translator.cognitiveservices.azure.com:443:$publicIp' -o /dev/null -w '{`"http_status`":%{http_code},`"remote_ip`":`"%{remote_ip}`",`"time_total_s`":%{time_total}}' -H `"Authorization: Bearer `$TOKEN`" -H 'Content-Type: application/json' -H 'Ocp-Apim-Subscription-Region: swedencentral' --data `"`$BODY`" '$endpoint/translator/text/v3.0/translate?api-version=3.0&to=fr'); RC=`$?; echo `"`$CODE`"; exit 0"
    Save-Sanitized $forced (Join-Path $r2Dir 'pinned-public-request.json')
    Capture-State 'R2-service-endpoint' $publicIp

    # R3 selected-network positive and rule-removal negative control.
    $r3Dir = Join-Path $runDir 'correctness\R3-restricted-subnet'
    New-Item -ItemType Directory -Force -Path $r3Dir | Out-Null
    Set-State 'Restricted' (Join-Path $r3Dir 'transition-state.json')
    Invoke-Benchmark 0 8103 'service_endpoint' 'fresh' 0 1 (Join-Path $r3Dir 'positive-request.json') | Out-Null
    $subnetId = (az network vnet subnet show -g $rg --vnet-name $vnet -n $subnet --query id -o tsv).Trim()
    az cognitiveservices account network-rule remove -g $rg -n $translator --subnet $subnetId -o none
    Assert-Az
    Start-Sleep -Seconds 15
    Invoke-Benchmark 0 8104 'service_endpoint' 'fresh' 0 1 (Join-Path $r3Dir 'negative-request.json') | Out-Null
    & $stateScript -Mode Restricted -ResourceGroup $rg -TranslatorName $translator | Out-Null
    Start-Sleep -Seconds 15
    Capture-State 'R3-restricted-subnet' $publicIp

    # R4 private endpoint.
    $r4Dir = Join-Path $runDir 'correctness\R4-private-endpoint'
    New-Item -ItemType Directory -Force -Path $r4Dir | Out-Null
    Set-State 'Private' (Join-Path $r4Dir 'transition-state.json')
    $r4 = Invoke-Benchmark 0 8105 'private' 'fresh' 0 1 (Join-Path $r4Dir 'request.json')
    Capture-State 'R4-private-endpoint' '10.61.2.4'
    }

    # R5 public disabled: forced public must fail, ordinary private must succeed.
    $r5Dir = Join-Path $runDir 'correctness\R5-private-only'
    New-Item -ItemType Directory -Force -Path $r5Dir | Out-Null
    $r5State = (& $stateScript -Mode PrivateOnly -ResourceGroup $rg -TranslatorName $translator | Out-String)
    Save-Sanitized $r5State (Join-Path $r5Dir 'transition-state.json')
    Start-Sleep -Seconds 15
    $forced = Invoke-Vm "set +e; TOKEN=`$(curl -fsS -H Metadata:true 'http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fcognitiveservices.azure.com%2F' | jq -r .access_token); BODY='[{`"Text`":`"Network path probe.`"}]'; curl -sS --http1.1 --max-time 30 --resolve '$translator.cognitiveservices.azure.com:443:$publicIp' -o /dev/null -w '{`"http_status`":%{http_code},`"remote_ip`":`"%{remote_ip}`",`"time_total_s`":%{time_total},`"curl_exit`":0}' -H `"Authorization: Bearer `$TOKEN`" -H 'Content-Type: application/json' -H 'Ocp-Apim-Subscription-Region: swedencentral' --data `"`$BODY`" '$endpoint/translator/text/v3.0/translate?api-version=3.0&to=fr'; echo; exit 0"
    Save-Sanitized $forced (Join-Path $r5Dir 'forced-public-request.json')
    Invoke-Benchmark 0 8106 'private' 'fresh' 0 1 (Join-Path $r5Dir 'ordinary-private-request.json') | Out-Null
    Capture-State 'R5-private-only' '10.61.2.4'

    & $stateScript -Mode Public -ResourceGroup $rg -TranslatorName $translator | Out-Null
    Start-Sleep -Seconds 15

    # Ten interleaved blocks. Orders are balanced to within one placement.
    $orders = @(
        @('public','service_endpoint','private'),
        @('service_endpoint','private','public'),
        @('private','public','service_endpoint'),
        @('public','private','service_endpoint'),
        @('private','service_endpoint','public'),
        @('service_endpoint','public','private'),
        @('private','public','service_endpoint'),
        @('public','service_endpoint','private'),
        @('service_endpoint','private','public'),
        @('public','private','service_endpoint')
    )
    $stateModes = @{ public = 'Public'; service_endpoint = 'ServiceEndpoint'; private = 'Private' }
    for ($block = 1; $block -le 10; $block++) {
        if ($block -eq 6) { Start-Sleep -Seconds 1800 }
        $seed = 2026080600 + $block
        foreach ($mode in $orders[$block - 1]) {
            $modeDir = Join-Path $runDir "performance\block-$('{0:D2}' -f $block)\mode-$mode"
            New-Item -ItemType Directory -Force -Path $modeDir | Out-Null
            Set-State $stateModes[$mode] (Join-Path $modeDir 'state.json')
            Invoke-Benchmark $block $seed $mode 'both' $Warmup $Samples (Join-Path $modeDir 'benchmark-both.json') | Out-Null
            Save-Az { az monitor metrics list --resource (az vm show -g $rg -n $vm --query id -o tsv) --metric 'Percentage CPU,CPU Credits Remaining' --interval PT1M --aggregation Average -o json } (Join-Path $modeDir 'vm-metrics.json')
        }
    }

    Save-Az { az network watcher flow-log show -g NetworkWatcherRG -n flow-vnet-endpoint-path --location swedencentral -o json } (Join-Path $runDir 'correctness\flow-log-configuration.json')
    Save-Az { az monitor diagnostic-settings list --resource (az cognitiveservices account show -g $rg -n $translator --query id -o tsv) -o json } (Join-Path $runDir 'correctness\translator-diagnostics.json')
    $workspaceId = (az monitor log-analytics workspace show -g $rg -n log-sepath --query customerId -o tsv).Trim()
    Save-Az { az monitor log-analytics query -w $workspaceId --analytics-query "AzureDiagnostics | where TimeGenerated > ago(6h) | where ResourceProvider == 'MICROSOFT.COGNITIVESERVICES' | project TimeGenerated, OperationName, ResultType, DurationMs, _ResourceId | take 200" -o json } (Join-Path $runDir 'correctness\translator-diagnostic-records.json')
    Save-Az { az monitor log-analytics query -w $workspaceId --analytics-query "AzureNetworkAnalytics_CL | where TimeGenerated > ago(6h) | where DestPort_d == 443 | project TimeGenerated, SrcIP_s, DestIP_s, FlowStatus_s, NSGRule_s | take 200" -o json } (Join-Path $runDir 'correctness\vnet-flow-records.json')

    python (Join-Path $labDir 'analyze_results.py') $runDir | Set-Content (Join-Path $runDir 'analysis\analysis-run.json')
    if ($LASTEXITCODE -ne 0) { throw 'Analysis failed.' }
}
finally {
    try {
        & $stateScript -Mode Public -ResourceGroup $rg -TranslatorName $translator | Out-Null
        az vm deallocate -g $rg -n $vm --no-wait -o none
        Wait-PowerState 'PowerState/deallocated'
    } finally {
        Remove-Item $workDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Validation complete: $runDir"
