Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:LabRoot = Split-Path $PSScriptRoot -Parent
$script:LeasePath = Join-Path $PSScriptRoot '.runtime-control\lease.json'

function Read-Lease {
    $lease = Get-Content $script:LeasePath -Raw | ConvertFrom-Json
    if (Test-Path (Join-Path $PSScriptRoot '.runtime-control\STOP')) { throw 'STOP requested.' }
    if ($lease.state -ne 'active' -or [datetimeoffset]::UtcNow -ge [datetimeoffset]$lease.expiresAtUtc) {
        throw 'An active, unexpired lease is required.'
    }
    return $lease
}

function Assert-NewWork {
    $lease = Read-Lease
    $end = [datetimeoffset]$lease.expiresAtUtc
    $start = $end.AddMinutes(-30)
    if ($lease.actualToolCalls -ge .8 * $lease.maxToolCalls -or
        $lease.actualMutations -ge .8 * $lease.maxMutations -or
        [datetimeoffset]::UtcNow -ge $start + (($end - $start) * .8)) {
        throw '80 percent lease boundary reached; restoration only.'
    }
}

function Write-PrivateJson($Object, [string]$Path) {
    $privateRoot = [IO.Path]::GetFullPath((Join-Path $script:LabRoot 'private')) + '\'
    if (-not [IO.Path]::GetFullPath($Path).StartsWith($privateRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Private output must remain inside this lab private directory.'
    }
    $Object | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $Path -Encoding utf8
}

function Invoke-LabAz {
    param([string[]]$Arguments, [string]$SubscriptionId, [int]$TimeoutSeconds = 120)
    $lease = Read-Lease
    if (-not $SubscriptionId) { throw 'Explicit subscription required.' }
    $azPath = (Get-Command az -ErrorAction Stop).Source
    $python = [IO.Path]::GetFullPath((Join-Path (Split-Path $azPath -Parent) '..\python.exe'))
    if (-not (Test-Path $python)) { throw 'Installed Azure CLI Python entry point unavailable; no installation allowed.' }
    $psi = [Diagnostics.ProcessStartInfo]::new($python)
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    foreach ($arg in (@('-m', 'azure.cli') + $Arguments +
        @('--subscription', $SubscriptionId, '--only-show-errors', '--output', 'json'))) {
        $psi.ArgumentList.Add($arg)
    }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $psi
    $started = $false
    try {
        [void]$process.Start()
        $started = $true
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit([Math]::Min($TimeoutSeconds, $lease.commandTimeoutSeconds) * 1000)) {
            $process.Kill($true)
            [void]$process.WaitForExit(5000)
            throw 'Azure CLI command timed out; process tree terminated. Do not retry under this lease.'
        }
        $text = $stdout.GetAwaiter().GetResult()
        $errorText = $stderr.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) { throw "Azure CLI failed: $errorText" }
        [void](Read-Lease)
        if ($text.Trim()) { return ($text | ConvertFrom-Json -Depth 100) }
    } finally {
        if ($started -and -not $process.HasExited) {
            $process.Kill($true)
            [void]$process.WaitForExit(5000)
        }
        $process.Dispose()
    }
}

function Assert-Context($Context) {
    [void](Read-Lease)
    $account = Invoke-LabAz -SubscriptionId $Context.subscriptionId -Arguments @('account', 'show') -TimeoutSeconds 30
    if ($account.id -ne $Context.subscriptionId -or $account.tenantId -ne $Context.expectedTenantId -or $account.state -ne 'Enabled') {
        throw 'Explicit subscription / expected tenant verification failed.'
    }
    if ($Context.resourceGroup -notmatch '^rg-bwb-[a-f0-9]{12}$' -or
        $Context.runId -notmatch '^bwb-[a-f0-9]{12}$' -or
        $Context.resourceGroup -ne "rg-$($Context.runId)") { throw 'Owned RG/run naming mismatch.' }
}

function Assert-OwnedGroup($Context) {
    Assert-Context $Context
    $group = Invoke-LabAz -SubscriptionId $Context.subscriptionId -Arguments @('group', 'show', '--name', $Context.resourceGroup)
    if ($group.id -ine "/subscriptions/$($Context.subscriptionId)/resourceGroups/$($Context.resourceGroup)" -or
        $group.tags.lab -ne 'true' -or $group.tags.created_by -ne 'copilot-lab' -or
        $group.tags.run_id -ne $Context.runId) { throw 'Exact owned RG and tags verification failed.' }
    return $group
}

function Invoke-Mutation {
    param($Context, [string[]]$Arguments, [switch]$Restore, [int]$TimeoutSeconds = 600)
    Assert-Context $Context
    $lease = Read-Lease
    if (-not $Restore) { Assert-NewWork }
    if ($lease.actualMutations -ge $lease.maxMutations) { throw 'Mutation budget exhausted.' }
    # Count before submission: a timeout can still have reached ARM.
    $lease.actualMutations++
    $lease.ownedProcessesIdle = $false
    $lease.lastCheckpointUtc = [datetimeoffset]::UtcNow.ToString('o')
    $lease | ConvertTo-Json -Depth 20 | Set-Content $script:LeasePath -Encoding utf8
    try {
        Invoke-LabAz -SubscriptionId $Context.subscriptionId -Arguments $Arguments -TimeoutSeconds $TimeoutSeconds
    } finally {
        $lease = Get-Content $script:LeasePath -Raw | ConvertFrom-Json
        $lease.ownedProcessesIdle = $true
        $lease | ConvertTo-Json -Depth 20 | Set-Content $script:LeasePath -Encoding utf8
    }
}

function Get-OwnedInventory($Context) {
    [void](Assert-OwnedGroup $Context)
    $items = @(Invoke-LabAz -SubscriptionId $Context.subscriptionId -Arguments @('resource', 'list', '--resource-group', $Context.resourceGroup))
    foreach ($item in $items) {
        if ($item.tags.lab -ne 'true' -or $item.tags.created_by -ne 'copilot-lab' -or
            $item.tags.run_id -ne $Context.runId) { throw 'Foreign or untagged resource in owned group; freeze cleanup.' }
    }
    return $items
}
