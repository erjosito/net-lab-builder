<#
.SYNOPSIS
    Drains Azure SQL Database LTR backups into BACPAC files in a storage account,
    optionally one in a different subscription.

.DESCRIPTION
    LTR backups cannot be copied, downloaded or moved. The only supported operation is
    "restore into a live database". They are also purged when the subscription is
    deleted. So to preserve them past subscription deletion, each restore point must be
    rehydrated and re-exported:

        LTR backup -> temp database (SAME subscription) -> BACPAC -> blob (ANY subscription)

    The BACPAC destination may live in a different subscription because 'az sql db export'
    authenticates to storage with a key or SAS, not with ARM. That removes the blob-copy hop.

    Every temp database is dropped as soon as its BACPAC lands, so compute is billed only
    for the restore + export window.

    A manifest CSV is written recording the provenance of every artifact, which is the
    part auditors actually care about: which original server/database/restore-point each
    BACPAC came from.

.NOTES
    - The temp database is freshly restored and receives no writes, so the BACPAC is
      transactionally consistent. (BACPAC export is only safe from a quiesced source.)
    - The staging server must be in the SAME subscription as the LTR backups.
    - Storage firewall on the destination account must permit the export service.

.EXAMPLE
    .\Export-SqlDbLtrBackups.ps1 `
        -SourceSubscriptionId 00000000-0000-0000-0000-000000000000 `
        -Location eastus `
        -StagingResourceGroup rg-ltr-drain -StagingServer sql-ltr-staging `
        -StagingAdminUser ltradmin -StagingAdminPassword (Read-Host -AsSecureString) `
        -DestStorageUri 'https://archivesa.blob.core.windows.net/sql-ltr' `
        -DestStorageKey $key -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string] $SourceSubscriptionId,
    [Parameter(Mandatory)][string] $Location,

    # Staging logical server. Must be in $SourceSubscriptionId. The server itself is free.
    [Parameter(Mandatory)][string] $StagingResourceGroup,
    [Parameter(Mandatory)][string] $StagingServer,
    [Parameter(Mandatory)][string] $StagingAdminUser,
    [Parameter(Mandatory)][securestring] $StagingAdminPassword,

    # Destination container URI, e.g. https://acct.blob.core.windows.net/container
    [Parameter(Mandatory)][string] $DestStorageUri,
    [Parameter(Mandatory)][string] $DestStorageKey,
    [ValidateSet('StorageAccessKey', 'SharedAccessKey')]
    [string] $DestStorageKeyType = 'StorageAccessKey',

    # Optional narrowing of which restore points to drain.
    [string]   $ServerFilter,
    [string]   $DatabaseFilter,
    [datetime] $BackupsNewerThan,
    [switch]   $LatestPerDatabaseOnly,

    # Staging SKU. Cheapest tier that still fits the data wins; GP_Gen5 2 vCore is a
    # sane speed/cost balance. Standard S0 is cheaper per hour but exports far slower.
    [string] $Edition  = 'GeneralPurpose',
    [string] $Family   = 'Gen5',
    [int]    $Capacity = 2,

    [string] $ManifestPath = "./ltr-export-manifest-$(Get-Date -Format 'yyyyMMdd-HHmmss').csv",
    [switch] $KeepTempDatabase
)

$ErrorActionPreference = 'Stop'

function Invoke-Az {
    param([string[]] $Arguments)
    $out = & az @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "az $($Arguments -join ' ') failed:`n$out" }
    return $out
}

Write-Host "Selecting source subscription $SourceSubscriptionId" -ForegroundColor Cyan
Invoke-Az @('account', 'set', '--subscription', $SourceSubscriptionId) | Out-Null

# --- 1. Enumerate LTR backups -------------------------------------------------
# --database-state All is essential: it surfaces backups whose source database or
# server has ALREADY been deleted, which is the normal state during a decommission.
$listArgs = @('sql', 'db', 'ltr-backup', 'list', '-l', $Location, '--database-state', 'All', '-o', 'json')
if ($ServerFilter)          { $listArgs += @('--server',   $ServerFilter) }
if ($DatabaseFilter)        { $listArgs += @('--database', $DatabaseFilter) }
if ($LatestPerDatabaseOnly) { $listArgs += '--latest' }

Write-Host "Enumerating LTR backups in $Location ..." -ForegroundColor Cyan
$backups = (Invoke-Az $listArgs | ConvertFrom-Json)

if ($BackupsNewerThan) {
    $backups = $backups | Where-Object { [datetime] $_.backupTime -ge $BackupsNewerThan }
}

if (-not $backups -or $backups.Count -eq 0) {
    Write-Warning 'No LTR backups matched. Nothing to do.'
    return
}

Write-Host "Found $($backups.Count) LTR restore point(s) to drain." -ForegroundColor Green

$plainPassword = [System.Net.NetworkCredential]::new('', $StagingAdminPassword).Password
$manifest = [System.Collections.Generic.List[object]]::new()
$index    = 0

foreach ($backup in $backups) {
    $index++
    $stamp    = ([datetime] $backup.backupTime).ToString('yyyyMMdd-HHmmss')
    # Temp DB names are capped at 128 chars and must be unique on the staging server.
    $tempDb   = "ltr-$($backup.databaseName)-$stamp" -replace '[^A-Za-z0-9\-_]', '-'
    if ($tempDb.Length -gt 100) { $tempDb = $tempDb.Substring(0, 100) }

    $blobName = "$($backup.serverName)/$($backup.databaseName)/$stamp.bacpac"
    $blobUri  = "$($DestStorageUri.TrimEnd('/'))/$blobName"

    Write-Host ''
    Write-Host "[$index/$($backups.Count)] $($backup.serverName)/$($backup.databaseName) @ $($backup.backupTime)" -ForegroundColor Yellow

    if (-not $PSCmdlet.ShouldProcess($blobUri, 'restore LTR backup and export BACPAC')) { continue }

    $record = [pscustomobject]@{
        SourceServer     = $backup.serverName
        SourceDatabase   = $backup.databaseName
        BackupTime       = $backup.backupTime
        BackupExpiry     = $backup.backupExpirationTime
        LtrBackupId      = $backup.id
        BacpacUri        = $blobUri
        TempDatabase     = $tempDb
        Status           = 'pending'
        Error            = ''
        ExportedAtUtc    = ''
    }

    try {
        Write-Host '  -> restoring LTR backup to temp database...' -ForegroundColor DarkGray
        Invoke-Az @(
            'sql', 'db', 'ltr-backup', 'restore',
            '--backup-id',           $backup.id,
            '--dest-database',       $tempDb,
            '--dest-server',         $StagingServer,
            '--dest-resource-group', $StagingResourceGroup,
            '--edition',             $Edition,
            '--family',              $Family,
            '--capacity',            $Capacity,
            '-o', 'none'
        ) | Out-Null

        Write-Host '  -> exporting BACPAC to destination storage...' -ForegroundColor DarkGray
        Invoke-Az @(
            'sql', 'db', 'export',
            '-g', $StagingResourceGroup,
            '-s', $StagingServer,
            '-n', $tempDb,
            '--admin-user',       $StagingAdminUser,
            '--admin-password',   $plainPassword,
            '--storage-uri',      $blobUri,
            '--storage-key',      $DestStorageKey,
            '--storage-key-type', $DestStorageKeyType,
            '-o', 'none'
        ) | Out-Null

        $record.Status        = 'exported'
        $record.ExportedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
        Write-Host "  -> OK  $blobUri" -ForegroundColor Green
    }
    catch {
        $record.Status = 'failed'
        $record.Error  = $_.Exception.Message
        Write-Warning "  -> FAILED: $($_.Exception.Message)"
    }
    finally {
        # Always drop the temp database: it is the only thing actually costing money.
        if (-not $KeepTempDatabase) {
            try {
                Write-Host '  -> dropping temp database...' -ForegroundColor DarkGray
                Invoke-Az @('sql', 'db', 'delete',
                            '-g', $StagingResourceGroup,
                            '-s', $StagingServer,
                            '-n', $tempDb, '--yes', '-o', 'none') | Out-Null
            }
            catch {
                Write-Warning "  -> temp database '$tempDb' could not be dropped; delete it manually or it keeps billing."
            }
        }
        $manifest.Add($record)
        $manifest | Export-Csv -Path $ManifestPath -NoTypeInformation
    }
}

Write-Host ''
Write-Host "Manifest written to $ManifestPath" -ForegroundColor Cyan
$manifest | Group-Object Status | ForEach-Object { Write-Host ("  {0,-10} {1}" -f $_.Name, $_.Count) }
