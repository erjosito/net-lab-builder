[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$CorrelationId,
    [switch]$Confirmed
)

$ErrorActionPreference = 'Stop'
$suffix = (($CorrelationId -replace '[^a-zA-Z0-9]', '').ToLower())
if ($suffix.Length -gt 10) { $suffix = $suffix.Substring($suffix.Length - 10) }
$rg = "rg-storage-sepath-$suffix"

if (-not $Confirmed) {
    Write-Host "DRY RUN ONLY — cleanup is not authorized."
    az resource list -g $rg --query '[].{name:name,type:type}' -o table
    Write-Host "To execute only after explicit approval: .\cleanup.ps1 -CorrelationId '$CorrelationId' -Confirmed"
    exit 0
}

az group delete -n $rg --yes --no-wait
Write-Host "Deletion submitted for $rg. Verify completion with: az group exists -n $rg"
