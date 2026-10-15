[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ContextPath,
    [switch]$Confirmed,
    [string]$ConfirmRunId
)
. "$PSScriptRoot\Common.ps1"
$context = Get-Content $ContextPath -Raw | ConvertFrom-Json
$inventory = Get-Content (Join-Path $script:LabRoot 'private\inventory.private.json') -Raw | ConvertFrom-Json
if ($inventory.runId -ne $context.runId -or
    $inventory.groupId -ine "/subscriptions/$($context.subscriptionId)/resourceGroups/$($context.resourceGroup)") {
    throw 'Private created inventory and exact owned group do not match.'
}
$actual = @(Get-OwnedInventory $context)
$knownIds = @($inventory.resources | ForEach-Object id)
if (@($actual | Where-Object { $_.id -notin $knownIds }).Count) { throw 'Unrecorded resource present; refuse group deletion.' }
$actual | ForEach-Object { Write-Output "PREVIEW $($_.type) (owned run)" }
if (-not $Confirmed) { Write-Output 'Preview only. Deletion requires explicit owner approval and -Confirmed -ConfirmRunId matching the private run ID.'; return }
if ($ConfirmRunId -cne $context.runId) { throw 'Explicit run confirmation mismatch.' }
[void](Assert-OwnedGroup $context)
[void](Invoke-Mutation -Context $context -Arguments @('group', 'delete', '--name', $context.resourceGroup, '--yes') -TimeoutSeconds 600)
$exists = Invoke-LabAz -SubscriptionId $context.subscriptionId -Arguments @('group', 'exists', '--name', $context.resourceGroup)
if ($exists) { throw 'Deletion not verified within this lease; no retry.' }
Write-PrivateJson @{ runId = $context.runId; deletedUtc = [datetimeoffset]::UtcNow.ToString('o'); deletionVerified = $true } (Join-Path $script:LabRoot 'private\cleanup.private.json')
Write-Output 'Owned resource group deletion verified.'
