[CmdletBinding()]
param([Parameter(Mandatory)][string]$ContextPath)
. "$PSScriptRoot\Common.ps1"
Assert-NewWork
$context = Get-Content $ContextPath -Raw | ConvertFrom-Json
Assert-Context $context
$gate = Get-Content (Join-Path $script:LabRoot 'private\gate.private.json') -Raw | ConvertFrom-Json
$parametersPath = Join-Path $script:LabRoot 'private\deployment.params.json'
$parameters = Get-Content $parametersPath -Raw | ConvertFrom-Json
if ($gate.runId -ne $context.runId -or $gate.region -ne 'swedencentral' -or
    [datetimeoffset]$gate.catalogPassedUtc -lt [datetimeoffset]::UtcNow.AddHours(-1) -or
    $gate.infraUsdPerHour -gt .08 -or $gate.lifetimeEnvelopeUsd -gt 8 -or
    $parameters.parameters.runId.value -ne $context.runId -or
    $parameters.parameters.vmSize.value -ne $gate.vmSize) { throw 'Missing, stale or inconsistent catalog/price gate.' }
$exists = Invoke-LabAz -SubscriptionId $context.subscriptionId -Arguments @('group', 'exists', '--name', $context.resourceGroup)
if ($exists) { throw 'Refusing to borrow or redeploy into an existing resource group.' }
$lease = Read-Lease
if ($lease.maxMutations - $lease.actualMutations -lt 6) { throw 'Six mutation slots required, including three deallocations.' }
if ([datetimeoffset]::UtcNow.AddMinutes(20) -ge [datetimeoffset]$lease.expiresAtUtc) { throw 'Insufficient deployment and restore time remaining.' }
$inventoryPath = Join-Path $script:LabRoot 'private\inventory.private.json'
$group = Invoke-Mutation -Context $context -Arguments @('group', 'create', '--name', $context.resourceGroup,
    '--location', 'swedencentral', '--tags', 'lab=true', 'created_by=copilot-lab', "run_id=$($context.runId)")
Write-PrivateJson @{ runId = $context.runId; groupId = $group.id; createdUtc = [datetimeoffset]::UtcNow.ToString('o'); resources = @() } $inventoryPath
[void](Assert-OwnedGroup $context)
# --validate is a control-plane gate, never a guarantee of real allocation.
[void](Invoke-Mutation -Context $context -Arguments @('deployment', 'group', 'validate', '--resource-group', $context.resourceGroup,
    '--name', "$($context.runId)-validate", '--template-file', (Join-Path $PSScriptRoot 'main.json'),
    '--parameters', "@$parametersPath") -TimeoutSeconds 120)
[void](Assert-OwnedGroup $context)
$deploymentStarted = $false
try {
    $deploymentStarted = $true
    [void](Invoke-Mutation -Context $context -Arguments @('deployment', 'group', 'create', '--resource-group', $context.resourceGroup,
        '--name', "$($context.runId)-core", '--template-file', (Join-Path $PSScriptRoot 'main.json'),
        '--parameters', "@$parametersPath", '--mode', 'Incremental') -TimeoutSeconds 600)
} finally {
    if ($deploymentStarted) {
        # Inventory and restore also run after a failed/partially completed ARM deployment.
        [void](Assert-OwnedGroup $context)
        $items = @(Invoke-LabAz -SubscriptionId $context.subscriptionId -Arguments @('resource', 'list', '--resource-group', $context.resourceGroup))
        Write-PrivateJson @{ runId = $context.runId; groupId = $group.id; observedUtc = [datetimeoffset]::UtcNow.ToString('o'); resources = $items } $inventoryPath
        $restoreErrors = @()
        foreach ($alias in @('a', 'b', 'p')) {
            $vmName = "$($context.runId)-vm-$alias"
            $vm = @($items | Where-Object { $_.type -ieq 'Microsoft.Compute/virtualMachines' -and $_.name -eq $vmName })
            if ($vm.Count -eq 0) { continue }
            try {
                [void](Assert-OwnedGroup $context)
                if ($vm[0].id -ine "/subscriptions/$($context.subscriptionId)/resourceGroups/$($context.resourceGroup)/providers/Microsoft.Compute/virtualMachines/$vmName" -or
                    $vm[0].tags.lab -ne 'true' -or $vm[0].tags.created_by -ne 'copilot-lab' -or
                    $vm[0].tags.run_id -ne $context.runId) { throw 'VM identity/tags do not match this created run.' }
                [void](Invoke-Mutation -Context $context -Restore -Arguments @('vm', 'deallocate', '--resource-group', $context.resourceGroup, '--name', $vmName) -TimeoutSeconds 180)
            } catch { $restoreErrors += $_.Exception.Message }
        }
        $status = @(Invoke-LabAz -SubscriptionId $context.subscriptionId -Arguments @('vm', 'list', '--resource-group', $context.resourceGroup, '--show-details'))
        Write-PrivateJson @{ capturedUtc = [datetimeoffset]::UtcNow.ToString('o'); vms = $status } (Join-Path $script:LabRoot 'private\power.private.json')
        if ($restoreErrors.Count) { throw "Restore errors: $($restoreErrors -join '; ')" }
        if (@($status | Where-Object { $_.powerState -ne 'VM deallocated' }).Count) { throw 'Restore blocked: a VM is not deallocated.' }
        if ($status.Count -ne 3) { throw 'Partial allocation: expected exactly three created VMs; inventory preserved.' }
        [void](Get-OwnedInventory $context)
    }
}
Write-Output 'Infrastructure deployed; all created VMs verified deallocated. Transfer harness remains pending; no traffic generated.'
