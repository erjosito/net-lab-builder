<#
.SYNOPSIS
    Tears down the LTR lab, including the LTR backups themselves.

.DESCRIPTION
    PHASE 5. Deleting the resource group is NOT sufficient: LTR backups deliberately
    outlive their source resources, which is the entire premise of this lab. Left alone
    they keep billing for the full retention period configured during seeding.

    Order matters. Remove LTR policies first so no further backups are generated, then
    delete the existing LTR backups, then the resource group.

.EXAMPLE
    .\Remove-LtrLab.ps1 -ResourceGroup rg-ltr-lab -Location eastus -Server ltrlab1234-sql
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string] $ResourceGroup,
    [Parameter(Mandatory)][string] $Location,
    [Parameter(Mandatory)][string] $Server,
    [string] $ManagedInstance,
    [switch] $KeepResourceGroup
)

$ErrorActionPreference = 'Stop'

function Try-Az {
    param([string[]] $Arguments, [string] $What)
    $out = & az @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { Write-Warning "$What failed: $out"; return $false }
    return $true
}

# --- 1. Stop generating new LTR backups ---------------------------------------
Write-Host 'Clearing LTR policies...' -ForegroundColor Cyan
$dbs = & az sql db list -g $ResourceGroup -s $Server --query "[?name!='master'].name" -o tsv 2>$null
foreach ($db in ($dbs -split "`n" | Where-Object { $_ })) {
    if ($PSCmdlet.ShouldProcess($db.Trim(), 'clear LTR policy')) {
        Try-Az @('sql', 'db', 'ltr-policy', 'set', '-g', $ResourceGroup, '-s', $Server,
                 '-n', $db.Trim(), '--weekly-retention', 'PT0S',
                 '--monthly-retention', 'PT0S', '--yearly-retention', 'PT0S',
                 '-o', 'none') "clear policy on $db" | Out-Null
    }
}

# --- 2. Delete existing LTR backups -------------------------------------------
# These survive resource-group deletion and must be removed explicitly.
Write-Host 'Deleting existing LTR backups...' -ForegroundColor Cyan
$backups = & az sql db ltr-backup list -l $Location --server $Server --database-state All -o json 2>$null | ConvertFrom-Json
foreach ($b in $backups) {
    # Unlike `midb`, `az sql db ltr-backup delete` has no --id/--ids parameter.
    # It requires the location/server/database/name tuple. The name is the
    # composite "<serverGuid>;<backupTimeTicks>;<tier>" returned by the list call.
    $srv = if ($b.serverName) { $b.serverName } else { $Server }
    if ($PSCmdlet.ShouldProcess("$($b.databaseName) @ $($b.backupTime)", 'delete LTR backup')) {
        Try-Az @('sql', 'db', 'ltr-backup', 'delete', '-l', $Location, '-s', $srv,
                 '-d', $b.databaseName, '-n', $b.name, '--yes', '-o', 'none') `
               "delete backup $($b.name)" | Out-Null
    }
}

if ($ManagedInstance) {
    Write-Host 'Deleting MI LTR backups...' -ForegroundColor Cyan
    $miBackups = & az sql midb ltr-backup list -l $Location --mi $ManagedInstance --database-state All -o json 2>$null | ConvertFrom-Json
    foreach ($b in $miBackups) {
        if ($PSCmdlet.ShouldProcess("$($b.databaseName) @ $($b.backupTime)", 'delete MI LTR backup')) {
            Try-Az @('sql', 'midb', 'ltr-backup', 'delete', '--id', $b.id, '--yes', '-o', 'none') `
                   "delete MI backup $($b.id)" | Out-Null
        }
    }
}

# --- 3. Resource group ---------------------------------------------------------
if (-not $KeepResourceGroup -and $PSCmdlet.ShouldProcess($ResourceGroup, 'delete resource group')) {
    Write-Host "Deleting resource group $ResourceGroup ..." -ForegroundColor Cyan
    Try-Az @('group', 'delete', '-n', $ResourceGroup, '--yes', '--no-wait', '-o', 'none') 'delete RG' | Out-Null
}

Write-Host ''
Write-Host 'Teardown submitted. VERIFY the backups are actually gone:' -ForegroundColor Yellow
Write-Host "  az sql db ltr-backup list -l $Location --server $Server --database-state All -o table" -ForegroundColor Cyan
Write-Host 'An empty result is the only acceptable outcome; anything else keeps billing.' -ForegroundColor Yellow
