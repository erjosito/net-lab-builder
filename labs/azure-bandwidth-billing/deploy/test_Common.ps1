[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\Common.ps1"
$nativeInvokeLabAz = ${function:Invoke-LabAz}
$passed = 0

function Require($Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Require-Throws([scriptblock]$Body, [string]$Message) {
    $caught = $null
    try { & $Body | Out-Null } catch { $caught = $_ }
    Require ($null -ne $caught) "Expected rejection: $Message"
    Require ($caught.Exception.Message -like "*$Message*") "Unexpected rejection: $caught"
}

function New-Resource([string]$Name, [string]$Type = 'Microsoft.Compute/virtualMachines') {
    [pscustomobject]@{
        id = "$($group.id)/providers/$Type/$Name"
        name = $Name
        type = $Type
        tags = [pscustomobject]@{ lab = 'true'; created_by = 'copilot-lab'; run_id = $context.runId }
    }
}

function New-Child([string]$Name = 'MDE.Linux') {
    [pscustomobject]@{
        id = "$($vm.id)/extensions/$Name"
        name = "$($vm.name)/$Name"
        type = 'Microsoft.Compute/virtualMachines/extensions'
    }
}

function Test-Case([string]$TestName, [scriptblock]$Body) {
    $context = [pscustomobject]@{
        subscriptionId = 'offline-subscription'
        expectedTenantId = 'offline-tenant'
        runId = 'bwb-123456abcdef'
        resourceGroup = 'rg-bwb-123456abcdef'
    }
    $group = [pscustomobject]@{
        id = "/subscriptions/$($context.subscriptionId)/resourceGroups/$($context.resourceGroup)"
        tags = [pscustomobject]@{ lab = 'true'; created_by = 'copilot-lab'; run_id = $context.runId }
    }
    $vm = New-Resource "$($context.runId)-vm-c"
    $inventoryFixture = @()
    function Read-Lease { [pscustomobject]@{ commandTimeoutSeconds = 1 } }
    function Invoke-LabAz {
        param([string[]]$Arguments, [string]$SubscriptionId, [int]$TimeoutSeconds)
        Require ($SubscriptionId -eq $context.subscriptionId) 'Explicit fixture subscription required.'
        switch ($Arguments -join ' ') {
            'account show' {
                return [pscustomobject]@{
                    id = $context.subscriptionId; tenantId = $context.expectedTenantId; state = 'Enabled'
                }
            }
            "group show --name $($context.resourceGroup)" { return $group }
            "resource list --resource-group $($context.resourceGroup)" { return $inventoryFixture }
            default { throw "Unexpected CLI operation (offline only): $($Arguments -join ' ')" }
        }
    }
    function Invoke-Mutation { throw 'Mutations forbidden in offline tests.' }
    . $Body
    $script:passed++
    Write-Output "PASS: $TestName"
}

Test-Case 'native CLI lookup bypasses Az function and selects only the first application' {
    function Az { throw 'Shadow Az function must never run.' }
    $expectedPython = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'offline-first\python.exe'))
    $calls = [pscustomobject]@{ lookup = 0; path = 0 }
    function Get-Command {
        param([string]$Name, [string]$CommandType, [string]$ErrorAction)
        Require ($Name -eq 'az' -and $CommandType -eq 'Application' -and $ErrorAction -eq 'Stop') 'Native application lookup required.'
        $calls.lookup++
        # Two matches model az.exe/az.cmd without requiring an Azure CLI installation.
        [pscustomobject]@{ Source = (Join-Path $PSScriptRoot 'offline-first\bin\az.exe') }
        [pscustomobject]@{ Source = (Join-Path $PSScriptRoot 'offline-second\bin\az.cmd') }
    }
    function Test-Path {
        param([string]$Path)
        Require ($Path -eq $expectedPython) 'Only the first native application may determine Python.'
        $calls.path++
        return $false
    }
    # Stop before Process.Start: no executable, authentication, or network is used.
    Set-Item Function:Invoke-LabAz $nativeInvokeLabAz
    Require-Throws { Invoke-LabAz -SubscriptionId $context.subscriptionId -Arguments @('account', 'show') } 'Installed Azure CLI Python entry point unavailable'
    Require ($calls.lookup -eq 1 -and $calls.path -eq 1) 'Native lookup and launch barrier must both be exercised.'
}

Test-Case 'owned tags pass and every missing or wrong ownership tag fails safely' {
    Require (Test-OwnedTags $vm $context) 'Owned tags rejected.'
    foreach ($tags in @($null, [pscustomobject]@{})) {
        Require (-not (Test-OwnedTags ([pscustomobject]@{ tags = $tags }) $context)) 'Empty tags accepted.'
    }
    Require (-not (Test-OwnedTags ([pscustomobject]@{}) $context)) 'Absent tags accepted.'
    foreach ($name in @('lab', 'created_by', 'run_id')) {
        $resource = New-Resource 'tag-fixture'
        $resource.tags.PSObject.Properties.Remove($name)
        Require (-not (Test-OwnedTags $resource $context)) "Missing $name accepted."
        $resource = New-Resource 'tag-fixture'
        $resource.tags.$name = 'foreign'
        Require (-not (Test-OwnedTags $resource $context)) "Wrong $name accepted."
    }
}

Test-Case 'owned roots retain identity order and tags' {
    $disk = New-Resource 'disk-c' 'Microsoft.Compute/disks'
    $inventoryFixture = @($vm, $disk)
    $actual = @(Get-OwnedInventory $context)
    Require ($actual.Count -eq 2) 'Owned roots changed.'
    Require ([object]::ReferenceEquals($actual[0], $vm) -and [object]::ReferenceEquals($actual[1], $disk)) 'Owned root identity/order changed.'
    Require ((Test-OwnedTags $vm $context) -and (Test-OwnedTags $disk $context)) 'Ownership tags changed.'
}

Test-Case 'known untagged service children inherit only parent verification and are not managed roots' {
    foreach ($name in @('MDE.Linux', 'RunCommandLinux')) {
        foreach ($shape in @('absent', 'null', 'empty')) {
            $child = New-Child $name
            if ($shape -ne 'absent') {
                $tags = if ($shape -eq 'empty') { [pscustomobject]@{} } else { $null }
                $child | Add-Member tags $tags
            }
            $before = $child | ConvertTo-Json -Depth 10 -Compress
            $inventoryFixture = @($child, $vm)
            $actual = @(Get-OwnedInventory $context 3>$null)
            Require ($actual.Count -eq 1 -and [object]::ReferenceEquals($actual[0], $vm)) 'Service child became an independently managed resource.'
            Require (($child | ConvertTo-Json -Depth 10 -Compress) -eq $before) 'Service child was retagged or modified.'
        }
    }
}

Test-Case 'unknown untagged or foreign children fail closed' {
    foreach ($foreign in @($false, $true)) {
        $child = New-Child 'UnknownExtension'
        if ($foreign) { $child | Add-Member tags ([pscustomobject]@{ run_id = 'foreign' }) }
        $inventoryFixture = @($vm, $child)
        Require-Throws { Get-OwnedInventory $context } 'Foreign or untagged resource'
    }
}

Test-Case 'foreign tags on a known service child fail closed' {
    foreach ($name in @('MDE.Linux', 'RunCommandLinux')) {
        foreach ($tags in @(
            [pscustomobject]@{ lab = 'true'; created_by = 'copilot-lab'; run_id = 'foreign' },
            [pscustomobject]@{ run_id = $context.runId }
        )) {
            $child = New-Child $name
            $child | Add-Member tags $tags
            $inventoryFixture = @($vm, $child)
            Require-Throws { Get-OwnedInventory $context } 'Foreign or untagged resource'
        }
    }
}

Test-Case 'orphan service children fail closed' {
    $inventoryFixture = @(New-Child)
    Require-Throws { Get-OwnedInventory $context } 'no uniquely verified owned parent'
}

Test-Case 'untagged or foreign parents cannot authorize service children' {
    foreach ($foreign in @($false, $true)) {
        $parent = New-Resource $vm.name
        if ($foreign) { $parent.tags.run_id = 'foreign' } else { $parent.PSObject.Properties.Remove('tags') }
        $inventoryFixture = @((New-Child), $parent)
        Require-Throws { Get-OwnedInventory $context } 'no uniquely verified owned parent'
    }
}

Test-Case 'duplicate owned parents cannot authorize service children' {
    $inventoryFixture = @((New-Child), $vm, (New-Resource $vm.name))
    Require-Throws { Get-OwnedInventory $context } 'no uniquely verified owned parent'
}

Test-Case 'malformed child ID cannot authorize service children' {
    $child = New-Child
    $child.id = $vm.id
    $inventoryFixture = @($child, $vm)
    Require-Throws { Get-OwnedInventory $context } 'no uniquely verified owned parent'
}

Write-Output "PASS: $passed offline Common.ps1 regression tests; no Azure CLI, authentication, network, or mutation."
