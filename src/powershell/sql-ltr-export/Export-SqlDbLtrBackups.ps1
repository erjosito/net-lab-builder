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
    #
    # IMPORTANT: restoring BETWEEN Hyperscale and non-Hyperscale tiers is not supported.
    # If the source database was Hyperscale you must pass -Edition Hyperscale, and a
    # Hyperscale database cannot be exported to BACPAC at all in some configurations.
    # The chosen tier must also be large enough to hold the source's max data size.
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

function Get-DatabaseUsedGb {
    <#
        Best-effort used-data size of a database, via Azure Monitor.

        Deliberately best-effort: it is instrumentation for the cost model, not part
        of the drain, so it must never fail an export. Metrics are also published on a
        delay, so a freshly restored database can legitimately report nothing yet.

        'storage' is Data space used; 'allocated_data_storage' is Data space allocated.
        Allocated is >= used and is the safer conservative fallback.
    #>
    param([string] $ResourceGroup, [string] $Server, [string] $Database)

    $resourceId = "/subscriptions/$((& az account show --query id -o tsv))/resourceGroups/$ResourceGroup" +
                  "/providers/Microsoft.Sql/servers/$Server/databases/$Database"
    foreach ($metric in @('storage', 'allocated_data_storage')) {
        try {
            $json = & az monitor metrics list --resource $resourceId --metric $metric `
                        --aggregation Maximum --interval PT1M -o json 2>$null
            if ($LASTEXITCODE -ne 0) { continue }
            $bytes = ($json | ConvertFrom-Json).value.timeseries.data |
                     Where-Object { $null -ne $_.maximum } |
                     Measure-Object -Property maximum -Maximum
            if ($bytes.Maximum -gt 0) { return [math]::Round($bytes.Maximum / 1GB, 4) }
        }
        catch { }
    }
    Write-Verbose "Could not determine used size for $Database; leaving SourceGb blank."
    return ''
}

function Get-BlobGb {
    <#
        Size of the exported artifact. This is the numerator of the compression ratio,
        which drives the artifact-storage term that dominates total cost.
    #>
    param([string] $BlobUri, [string] $AccountKey, [string] $KeyType = 'StorageAccessKey')
    try {
        $u = [Uri] $BlobUri
        $account   = $u.Host.Split('.')[0]
        $container = $u.AbsolutePath.Trim('/').Split('/')[0]
        $blob      = $u.AbsolutePath.Trim('/').Substring($container.Length + 1)

        # The same credential the export used: an account key or a SAS token.
        $auth = if ($KeyType -eq 'SharedAccessKey') {
            @('--sas-token', $AccountKey.TrimStart('?'))
        } else {
            @('--account-key', $AccountKey)
        }

        $size = & az storage blob show --account-name $account @auth `
                    --container-name $container --name $blob `
                    --query 'properties.contentLength' -o tsv 2>$null
        if ($LASTEXITCODE -eq 0 -and $size) { return [math]::Round([double]$size / 1GB, 4) }
    }
    catch { }
    Write-Verbose "Could not determine artifact size for $BlobUri."
    return ''
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
        # Instrumentation. These are what Measure-LtrCalibration.ps1 fits against,
        # so the drain doubles as the measurement run rather than needing a separate one.
        SourceGb         = ''
        RestoreMinutes   = ''
        ExportMinutes    = ''
        ArtifactGb       = ''
    }

    try {
        Write-Host '  -> restoring LTR backup to temp database...' -ForegroundColor DarkGray
        $swRestore = [System.Diagnostics.Stopwatch]::StartNew()
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
        $swRestore.Stop()
        $record.RestoreMinutes = [math]::Round($swRestore.Elapsed.TotalMinutes, 3)

        # Used data size of the restored copy. Fit the cost model against this rather
        # than against a nominal size: allocated size routinely diverges from what was
        # written, and it is the slope of the model that suffers.
        $record.SourceGb = Get-DatabaseUsedGb -ResourceGroup $StagingResourceGroup -Server $StagingServer -Database $tempDb

        Write-Host '  -> exporting BACPAC to destination storage...' -ForegroundColor DarkGray
        $swExport = [System.Diagnostics.Stopwatch]::StartNew()
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
        $swExport.Stop()
        $record.ExportMinutes = [math]::Round($swExport.Elapsed.TotalMinutes, 3)
        $record.ArtifactGb    = Get-BlobGb -BlobUri $blobUri -AccountKey $DestStorageKey -KeyType $DestStorageKeyType

        $record.Status        = 'exported'
        $record.ExportedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
        Write-Host ("  -> OK  {0}  (restore {1} min, export {2} min, artifact {3} GB)" -f `
                    $blobUri, $record.RestoreMinutes, $record.ExportMinutes, $record.ArtifactGb) -ForegroundColor Green
    }
    catch {
        $record.Status = 'failed'
        $record.Error  = $_.Exception.Message
        Write-Warning "  -> FAILED: $($_.Exception.Message)"

        # The two failure modes that actually bite in practice both look like generic
        # restore errors, so translate them into something actionable.
        if ($_.Exception.Message -match 'Hyperscale|edition|service objective|tier') {
            Write-Warning "     Hint: the source may be Hyperscale, or -Capacity $Capacity may be too small for its max size."
            Write-Warning "     Restoring between Hyperscale and other tiers is not supported. Re-run these backups with a matching -Edition."
        }
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
