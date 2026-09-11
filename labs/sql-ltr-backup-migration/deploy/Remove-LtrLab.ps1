<#
.SYNOPSIS
    Tears down the LTR lab, including the LTR backups themselves.

.DESCRIPTION
    PHASE 5. Deleting the resource group is NOT sufficient: LTR backups deliberately
    outlive their source resources, which is the entire premise of this lab. Left alone
    they keep billing for the full retention period configured during seeding.

    Order matters. Remove LTR policies first so no further backups are generated, then
    delete the existing LTR backups, then the resource group.

    Confirmed empirically in this lab: LTR backups survive deletion of the resource
    group and the logical server. They remain enumerable by location alone, without
    the server that produced them. The binding scope is the SUBSCRIPTION, which is
    why a subscription that cannot be moved forces a drain.

    If the lab was extended with the cross-tenant drain, pass -CrossTenantResourceGroup,
    -TargetSubscription and -AppDisplayName. The app registration, its federated
    credential, and the target-tenant service principal live outside every resource
    group, so deleting resource groups alone leaves a working cross-tenant trust in
    place. That is a standing grant, not a stray resource.

.EXAMPLE
    .\Remove-LtrLab.ps1 -ResourceGroup rg-ltr-lab -Location eastus -Server ltrlab1234-sql

.EXAMPLE
    .\Remove-LtrLab.ps1 -ResourceGroup rg-ltr-lab -Location swedencentral -Server ltrlab1234-sql `
        -CrossTenantResourceGroup rg-ltr-xtenant -TargetSubscription $tgtSubId `
        -AppDisplayName ltrlab-xtenant-drain
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string] $ResourceGroup,
    [Parameter(Mandatory)][string] $Location,
    [Parameter(Mandatory)][string] $Server,
    [string] $ManagedInstance,
    [string] $CrossTenantResourceGroup,
    [string] $TargetSubscription,
    [string] $AppDisplayName,
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

# --- 3. Cross-tenant footprint (Playbook G) -----------------------------------
# The app registration, its federated credential, and the target-tenant service
# principal are directory objects. They sit outside every resource group, so
# deleting resource groups leaves a usable cross-tenant trust behind.
if ($CrossTenantResourceGroup -or $AppDisplayName) {
    Write-Host 'Removing cross-tenant footprint...' -ForegroundColor Cyan
    $originalSub = & az account show --query id -o tsv 2>$null

    if ($TargetSubscription) {
        # The service principal lives in the TARGET tenant, so the CLI has to be
        # pointed there before `az ad` will see it.
        if (Try-Az @('account', 'set', '-s', $TargetSubscription) 'switch to target subscription') {
            if ($CrossTenantResourceGroup -and $PSCmdlet.ShouldProcess($CrossTenantResourceGroup, 'delete target resource group')) {
                Try-Az @('group', 'delete', '-n', $CrossTenantResourceGroup, '--yes', '--no-wait', '-o', 'none') `
                       "delete RG $CrossTenantResourceGroup" | Out-Null
            }
            if ($AppDisplayName) {
                $sps = & az ad sp list --display-name $AppDisplayName -o json 2>$null | ConvertFrom-Json
                foreach ($sp in $sps) {
                    if ($PSCmdlet.ShouldProcess($sp.id, 'delete target-tenant service principal')) {
                        Try-Az @('ad', 'sp', 'delete', '--id', $sp.id) "delete SP $($sp.id)" | Out-Null
                    }
                }
            }
        }
    }

    # Back to the source tenant for the application object. Deleting the app also
    # removes its federated identity credential.
    if ($originalSub) { Try-Az @('account', 'set', '-s', $originalSub) 'restore subscription context' | Out-Null }
    if ($AppDisplayName) {
        $apps = & az ad app list --display-name $AppDisplayName -o json 2>$null | ConvertFrom-Json
        foreach ($app in $apps) {
            if ($PSCmdlet.ShouldProcess($app.id, 'delete app registration')) {
                Try-Az @('ad', 'app', 'delete', '--id', $app.id) "delete app $($app.id)" | Out-Null
            }
        }
    }
}

# --- 4. Resource group ---------------------------------------------------------
if (-not $KeepResourceGroup -and $PSCmdlet.ShouldProcess($ResourceGroup, 'delete resource group')) {
    Write-Host "Deleting resource group $ResourceGroup ..." -ForegroundColor Cyan
    Try-Az @('group', 'delete', '-n', $ResourceGroup, '--yes', '--no-wait', '-o', 'none') 'delete RG' | Out-Null
}

Write-Host ''
Write-Host 'Teardown submitted. VERIFY the backups are actually gone:' -ForegroundColor Yellow
Write-Host "  az sql db ltr-backup list -l $Location --server $Server --database-state All -o table" -ForegroundColor Cyan
Write-Host 'An empty result is the only acceptable outcome; anything else keeps billing.' -ForegroundColor Yellow
