[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [string]$ResourceGroup = 'rg-aks-agic-shared-udr',
    [string]$KubeconfigPath = (Join-Path $PSScriptRoot '.runtime-control\kubeconfig'),
    [string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) {
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
    $OutputDirectory = Join-Path $root "show-output\scale-two-run-$stamp"
}
$out = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $out) {
    throw "Output directory already exists; refusing to overwrite captures: $out"
}
New-Item -ItemType Directory $out | Out-Null
$kc = [System.IO.Path]::GetFullPath($KubeconfigPath)
$rg = $ResourceGroup
if (-not (Test-Path -LiteralPath $kc -PathType Leaf)) {
    throw "Kubeconfig not found: $kc"
}
$script:n = 0
$uuid = '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
function San($s) {
    if ($null -eq $s) { return '' }
    $s = [regex]::Replace($s, $uuid, '<uuid>')
    return [regex]::Replace($s, '(?i)[A-Z]:\\Users\\[^\s"'';,)}]+', '[LOCAL_PATH_REDACTED]')
}
function Run($name, $exe, $argList, $mutating = $false) {
    $script:n++
    $start = (Get-Date).ToUniversalTime()
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $exe
    foreach ($a in $argList) { [void]$psi.ArgumentList.Add($a) }
    $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true; $psi.UseShellExecute = $false
    $p = [System.Diagnostics.Process]::Start($psi)
    $tOut = $p.StandardOutput.ReadToEndAsync(); $tErr = $p.StandardError.ReadToEndAsync()
    $timedOut = $false
    if (-not $p.WaitForExit(180000)) { $timedOut = $true; try { $p.Kill($true) } catch {} } else { $p.WaitForExit() }
    $rec = [ordered]@{
        seq = $script:n; name = $name; mutating = $mutating
        command = San ("$exe " + ($argList -join ' '))
        startUtc = $start.ToString('o'); endUtc = (Get-Date).ToUniversalTime().ToString('o')
        exitCode = $(if ($timedOut) { $null } else { $p.ExitCode }); timedOut = $timedOut
        stdout = San $tOut.Result; stderr = San $tErr.Result
    }
    $rec | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $out ("{0:00}-{1}.json" -f $script:n, $name)) -Encoding utf8
    return $rec
}
$k = @('--kubeconfig', $kc, '--request-timeout=60s')
function Snap($tag) {
    [void](Run "$tag-pods" 'kubectl' ($k + @('get', 'pods', '-n', 'default', '-l', 'app=web', '-o', 'wide')))
    [void](Run "$tag-endpoints" 'kubectl' ($k + @('get', 'endpoints', 'web', '-n', 'default', '-o', 'wide')))
}
$a = Run 'pre-agw-list' 'az' @('network', 'application-gateway', 'list', '-g', $rg, '--query', '[].name', '-o', 'tsv', '--only-show-errors')
if ($a.exitCode -ne 0) { throw 'Could not list Application Gateways; see captured command output.' }
$agw = ($a.stdout -split "`r?`n" | Where-Object { $_ })[0]
if (-not $agw) { throw 'No Application Gateway was returned; refusing to continue.' }
$poolQ = 'backendAddressPools[].{name:name,addrs:backendAddresses}'
$d = Run 'pre-replicas' 'kubectl' ($k + @('get', 'deploy', 'web', '-n', 'default', '-o', 'jsonpath={.spec.replicas}/{.status.readyReplicas}'))
Snap 'pre'
[void](Run 'pre-nodes' 'kubectl' ($k + @('get', 'nodes', '-o', 'wide')))
[void](Run 'pre-agw-pool' 'az' @('network', 'application-gateway', 'show', '-g', $rg, '-n', $agw, '--query', $poolQ, '-o', 'json', '--only-show-errors'))
[void](Run 'pre-routes' 'az' @('network', 'route-table', 'route', 'list', '-g', $rg, '--route-table-name', 'rt-shared', '-o', 'json', '--only-show-errors'))
$orig = ($d.stdout -split '/')[0].Trim()
$scaled = $false; $scaleUtc = $null
if ($d.exitCode -eq 0 -and $orig -eq '1') {
    if ($PSCmdlet.ShouldProcess("$rg/default/web", 'Scale Kubernetes deployment to two replicas')) {
        $scaleUtc = (Get-Date).ToUniversalTime().ToString('o')
        $s = Run 'scale' 'kubectl' ($k + @('scale', 'deployment', 'web', '-n', 'default', '--replicas=2')) $true
        $scaled = ($s.exitCode -eq 0)
        if ($scaled) {
            [void](Run 'post-rollout' 'kubectl' ($k + @('rollout', 'status', 'deployment/web', '-n', 'default', '--timeout=120s')))
            Snap 'post'
            [void](Run 'post-agw-pool' 'az' @('network', 'application-gateway', 'show', '-g', $rg, '-n', $agw, '--query', $poolQ, '-o', 'json', '--only-show-errors'))
        }
    }
}
$summary = [ordered]@{ originalReplicas = $orig; scaleAttempted = ($null -ne $scaleUtc); scaleAccepted = $scaled; scaleStartUtc = $scaleUtc; agw = $agw; commandCount = $script:n; doneUtc = (Get-Date).ToUniversalTime().ToString('o') }
$summary | ConvertTo-Json | Set-Content (Join-Path $out 'summary.json') -Encoding utf8
$summary | ConvertTo-Json
