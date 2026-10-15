[CmdletBinding()]
param([Parameter(Mandatory)][string]$ContextPath,
      [Parameter(Mandatory)][string]$GatePath,
      [Parameter(Mandatory)][string]$ParametersPath)
. "$PSScriptRoot\Common.ps1"
$script:LeasePath = Join-Path $PSScriptRoot '.runtime-control\control-deploy-lease.json'
Assert-NewWork
$context = Get-Content $ContextPath -Raw | ConvertFrom-Json
$core = Get-Content (Join-Path $script:LabRoot 'private\context.private.json') -Raw | ConvertFrom-Json
$gate = Get-Content $GatePath -Raw | ConvertFrom-Json
$parameters = Get-Content $ParametersPath -Raw | ConvertFrom-Json
Assert-Context $context
$lease = Read-Lease
$ladder = @('Standard_B1ls', 'Standard_B1s', 'Standard_B2ts_v2',
    'Standard_B2ls_v2', 'Standard_B2s_v2')
if ($context.subscriptionId -ne $core.subscriptionId -or
    $context.expectedTenantId -ne $core.expectedTenantId -or
    $context.resourceGroup -eq $core.resourceGroup -or $context.runId -eq $core.runId -or
    $gate.runId -ne $context.runId -or $gate.region -ne 'northeurope' -or
    [datetimeoffset]$gate.catalogPassedUtc -lt [datetimeoffset]::UtcNow.AddHours(-1) -or
    [datetimeoffset]$gate.catalogPassedUtc -gt [datetimeoffset]::UtcNow -or
    [datetimeoffset]$gate.capacityPassedUtc -lt [datetimeoffset]::UtcNow.AddHours(-1) -or
    [datetimeoffset]$gate.capacityPassedUtc -gt [datetimeoffset]::UtcNow -or
    -not $gate.ladderEvidencePath -or -not (Test-Path $gate.ladderEvidencePath) -or
    $gate.infraUsdPerHour -le 0 -or $gate.infraUsdPerHour -gt .08 -or
    $gate.lifetimeEnvelopeUsd -le 0 -or $gate.lifetimeEnvelopeUsd -gt 8 -or
    $gate.slotAllocatedHoursRemaining -lt 1 -or $gate.slotAllocatedHoursRemaining -gt 12 -or
    $gate.coreRemainingBytes -lt 6442450944 -or $gate.coreRemainingBytes -gt 24696061952 -or
    [datetimeoffset]$gate.cleanupDeadlineUtc -gt [datetimeoffset]'2026-10-18T07:33:00Z' -or
    [datetimeoffset]$gate.cleanupDeadlineUtc -le [datetimeoffset]::UtcNow.AddHours(1) -or
    $parameters.parameters.runId.value -ne $context.runId -or
    $parameters.parameters.vmSize.value -ne $gate.vmSize -or
    $lease.maxMutations - $lease.actualMutations -lt 3 -or
    @($lease.allowedMutations).Count -ne 3 -or
    'validate-c' -notin $lease.allowedMutations -or 'deploy-c' -notin $lease.allowedMutations -or
    'deallocate-c' -notin $lease.allowedMutations -or
    [datetimeoffset]::UtcNow.AddMinutes(25) -ge [datetimeoffset]$lease.expiresAtUtc) {
    throw 'Missing, stale, over-budget or inconsistent C preflight/price/lifetime gate.'
}
$evidence = Get-Content $gate.ladderEvidencePath -Raw | ConvertFrom-Json
$selected = [array]::IndexOf($ladder, [string]$gate.vmSize)
if ($selected -lt 0 -or $evidence.runId -ne $context.runId -or
    $evidence.region -ne 'northeurope' -or $evidence.subscriptionId -ne $core.subscriptionId -or
    @($evidence.attempts).Count -ne $selected + 1) { throw 'Invalid ordered capacity evidence.' }
for ($rank = 0; $rank -le $selected; $rank++) {
    $entry = $evidence.attempts[$rank]
    if ($entry.vmSize -ne $ladder[$rank] -or
        [datetimeoffset]$entry.observedUtc -gt [datetimeoffset]::UtcNow -or
        [datetimeoffset]$entry.observedUtc -lt [datetimeoffset]::UtcNow.AddHours(-1)) {
        throw 'Missing, stale or out-of-order ladder rank.'
    }
    if ($rank -lt $selected) {
        if ($entry.outcome -notin @('catalog-failed', 'capacity-failed')) {
            throw 'A cheaper passing rank cannot be skipped.'
        }
    } elseif ($entry.outcome -ne 'passed' -or $entry.catalogPassed -ne $true -or
              $entry.capacityPassed -ne $true) { throw 'Selected rank lacks both capacity gates.' }
}
# P must be removed under separately confirmed cleanup; never delete it here.
$coreItems = @(Get-OwnedInventory $core)
if (@($coreItems | Where-Object { $_.name -match '-(vm|os|nic|nsg)-p$' }).Count) {
    throw 'P retirement approval and exact-inventory cleanup required before adding C.'
}
$power = @(Invoke-LabAz -SubscriptionId $core.subscriptionId -Arguments @(
    'vm', 'list', '--resource-group', $core.resourceGroup, '--show-details'))
if ($power.Count -ne 2 -or @($power | Where-Object { $_.powerState -ne 'VM deallocated' }).Count) {
    throw 'Core A/B must be the only remaining core VMs and both deallocated.'
}
$receiver = Invoke-LabAz -SubscriptionId $core.subscriptionId -Arguments @(
    'network', 'public-ip', 'show', '-g', $core.resourceGroup, '-n', "$($core.runId)-pip-b")
if ($receiver.id -ine "/subscriptions/$($core.subscriptionId)/resourceGroups/$($core.resourceGroup)/providers/Microsoft.Network/publicIPAddresses/$($core.runId)-pip-b" -or
    $receiver.location -ne 'swedencentral' -or $receiver.tags.lab -ne 'true' -or
    $receiver.tags.created_by -ne 'copilot-lab' -or $receiver.tags.run_id -ne $core.runId) {
    throw 'B receiver PIP ownership mismatch.'
}
$group = Assert-OwnedGroup $context
$existing = @(Get-OwnedInventory $context)
if ($existing.Count) { throw 'C preflight group must contain no resources; no redeployment.' }
$templateText = (Get-Content "$PSScriptRoot\msdn-main.json" -Raw).Replace('-t', '-c')
$template = $templateText | ConvertFrom-Json -Depth 100
$template.variables.location = 'northeurope'
$template.parameters.vmSize.allowedValues = $ladder
if ($gate.vmSize -notin $template.parameters.vmSize.allowedValues) {
    throw 'Unapproved SKU; D-series or another region requires new approval.'
}
$templatePath = Join-Path $script:LabRoot 'private\control-main.private.json'
Write-PrivateJson $template $templatePath
$inventoryPath = Join-Path $script:LabRoot 'private\control-inventory.private.json'
Write-PrivateJson @{runId=$context.runId; groupId=$group.id; resources=@();
    cleanupDeadlineUtc=$gate.cleanupDeadlineUtc; createdByThisRun=$true} $inventoryPath
[void](Invoke-Mutation -Context $context -Arguments @('deployment', 'group', 'validate',
    '--resource-group', $context.resourceGroup, '--template-file', $templatePath,
    '--parameters', "@$ParametersPath") -TimeoutSeconds 120)
$attempted = $false
try {
    $attempted = $true
    [void](Invoke-Mutation -Context $context -Arguments @('deployment', 'group', 'create',
        '--resource-group', $context.resourceGroup, '--name', "$($context.runId)-control",
        '--template-file', $templatePath, '--parameters', "@$ParametersPath",
        '--mode', 'Incremental') -TimeoutSeconds 600)
} finally {
    if ($attempted) {
        $items = @(Get-OwnedInventory $context)
        Write-PrivateJson @{runId=$context.runId; groupId=$group.id; resources=$items;
            cleanupDeadlineUtc=$gate.cleanupDeadlineUtc;
            receiverPublicIP=$receiver; createdByThisRun=$true;
            observedUtc=[datetimeoffset]::UtcNow.ToString('o')} $inventoryPath
        $vm = @($items | Where-Object { $_.type -eq 'Microsoft.Compute/virtualMachines' })
        if ($vm.Count -eq 1 -and $vm[0].name -eq "$($context.runId)-vm-c" -and
            $vm[0].id -ieq "/subscriptions/$($context.subscriptionId)/resourceGroups/$($context.resourceGroup)/providers/Microsoft.Compute/virtualMachines/$($context.runId)-vm-c") {
            [void](Invoke-Mutation -Context $context -Restore -Arguments @('vm', 'deallocate',
                '--resource-group', $context.resourceGroup, '--name', $vm[0].name) -TimeoutSeconds 180)
            $view = Invoke-LabAz -SubscriptionId $context.subscriptionId -Arguments @(
                'vm', 'get-instance-view', '-g', $context.resourceGroup, '-n', $vm[0].name)
            if (-not @($view.instanceView.statuses | Where-Object { $_.code -eq 'PowerState/deallocated' }).Count) {
                throw 'C deallocation not verified; fresh recovery owner required.'
            }
        } elseif ($vm.Count) { throw 'Unexpected C VM inventory; freeze mutation.' }
        if ($items.Count -ne 6 -or $vm.Count -ne 1) { throw 'Partial C deployment; inventory preserved.' }
        $details = @()
        foreach ($item in $items) {
            $details += Invoke-LabAz -SubscriptionId $context.subscriptionId -Arguments @(
                'resource', 'show', '--ids', $item.id)
        }
        Write-PrivateJson @{runId=$context.runId; groupId=$group.id; resources=$items;
            detailedResources=$details; cleanupDeadlineUtc=$gate.cleanupDeadlineUtc;
            receiverPublicIP=$receiver; createdByThisRun=$true;
            observedUtc=[datetimeoffset]::UtcNow.ToString('o')} $inventoryPath
    }
}
Write-Output 'C deployed and deallocated; no payload. Close lease; separate readiness owner next.'
