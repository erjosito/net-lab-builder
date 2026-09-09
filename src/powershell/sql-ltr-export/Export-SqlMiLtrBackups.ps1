<#
.SYNOPSIS
    Drains Azure SQL Managed Instance LTR backups into native COPY_ONLY .bak files
    (or BACPACs) in a storage account, optionally one in a different subscription.

.DESCRIPTION
    Same constraint as SQL DB: LTR backups cannot be copied or downloaded, only restored,
    and they are purged with the subscription. So each restore point must be rehydrated
    onto a managed instance and re-exported.

    The MI path differs from the SQL DB path in three important ways:

    1. COST SHAPE. There is no free "logical server" for MI. The restore target must be a
       running instance, and instance-hours dominate every other cost. Therefore:
         * If the SOURCE MI still exists, run this BEFORE deleting it and point
           -DestManagedInstance at it. Incremental compute cost is then effectively zero.
         * If it is already gone, you pay for a staging MI for the whole batch. Batch every
           database into a single instance lifetime rather than creating one per database.

    2. TDE BLOCKS NATIVE BACKUP. Per Microsoft's copy-only backup documentation:
         "In Azure SQL Managed Instance, copy-only backups can't be created for a database
          encrypted with service-managed Transparent Data Encryption (TDE) ... that key
          can't be exported, so you couldn't restore the backup anywhere else."
       TDE is on by default, so -TdeMode controls how this is handled:
         DisableOnStagedCopy : ALTER DATABASE ... SET ENCRYPTION OFF on the throwaway
                               restored copy, then back it up. Produces a plaintext .bak;
                               protect it with immutable storage + service-side encryption.
                               Avoids creating a Key Vault key you must guard for a decade.
         CustomerManagedKey  : assumes the instance is already configured for CMK TDE. The
                               .bak stays encrypted, but you MUST preserve that AKV key for
                               the full retention period, in a vault that outlives the old
                               subscription. Lose the key and every backup is unreadable.

    3. NO MANAGED BACPAC EXPORT. 'az sql midb export' does not exist. BACPAC mode therefore
       shells out to sqlpackage.exe, which needs network line-of-sight to the instance
       (run it on a VM in the MI's VNet, or enable the MI public endpoint).

.NOTES
    Requires the SqlServer PowerShell module for the T-SQL steps:
        Install-Module SqlServer -Scope CurrentUser

.EXAMPLE
    # Cheapest case: drain into the still-running source MI before decommissioning it.
    .\Export-SqlMiLtrBackups.ps1 `
        -SourceSubscriptionId 00000000-0000-0000-0000-000000000000 `
        -Location eastus `
        -DestResourceGroup rg-sql -DestManagedInstance mi-legacy `
        -SqlAdminUser miadmin -SqlAdminPassword (Read-Host -AsSecureString) `
        -DestContainerUri 'https://archivesa.blob.core.windows.net/sql-ltr' `
        -DestContainerSas $sas -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string] $SourceSubscriptionId,
    [Parameter(Mandatory)][string] $Location,

    # Restore target. Prefer the EXISTING source MI while it is still alive: its compute
    # is already paid for, which makes the whole drain nearly free.
    [Parameter(Mandatory)][string] $DestResourceGroup,
    [Parameter(Mandatory)][string] $DestManagedInstance,

    [Parameter(Mandatory)][string]       $SqlAdminUser,
    [Parameter(Mandatory)][securestring] $SqlAdminPassword,

    # Destination container, e.g. https://acct.blob.core.windows.net/container
    [Parameter(Mandatory)][string] $DestContainerUri,

    # Container-scoped SAS with Read/Write/List/Create. Storage may live in ANY
    # subscription: the engine authenticates with the SAS, not with ARM.
    [string] $DestContainerSas,

    [ValidateSet('NativeBak', 'Bacpac')]
    [string] $ArtifactType = 'NativeBak',

    [ValidateSet('DisableOnStagedCopy', 'CustomerManagedKey')]
    [string] $TdeMode = 'DisableOnStagedCopy',

    [string]   $InstanceFilter,
    [string]   $DatabaseFilter,
    [datetime] $BackupsNewerThan,

    [string] $SqlPackagePath = 'sqlpackage.exe',
    [int]    $DecryptTimeoutMinutes = 60,

    # BACKUP TO URL is capped at 195 GB per stripe (50,000 blocks x 4 MB). Larger
    # databases must be striped across multiple URLs, up to 64 of them.
    [int]    $GbPerStripe = 150,
    [int]    $MaxStripes  = 64,

    [string] $ManifestPath = "./mi-ltr-export-manifest-$(Get-Date -Format 'yyyyMMdd-HHmmss').csv",
    [switch] $KeepStagedDatabase
)

$ErrorActionPreference = 'Stop'

function Invoke-Az {
    param([string[]] $Arguments)
    $out = & az @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "az $($Arguments -join ' ') failed:`n$out" }
    return $out
}

if ($ArtifactType -eq 'NativeBak' -and -not $DestContainerSas) {
    throw 'NativeBak mode needs -DestContainerSas: the engine writes to blob using a SAS credential.'
}

Write-Host "Selecting source subscription $SourceSubscriptionId" -ForegroundColor Cyan
Invoke-Az @('account', 'set', '--subscription', $SourceSubscriptionId) | Out-Null

$miFqdn        = (Invoke-Az @('sql', 'mi', 'show', '-g', $DestResourceGroup, '-n', $DestManagedInstance,
                              '--query', 'fullyQualifiedDomainName', '-o', 'tsv')).Trim()
$plainPassword = [System.Net.NetworkCredential]::new('', $SqlAdminPassword).Password
$sqlCred       = [pscredential]::new($SqlAdminUser, $SqlAdminPassword)

function Invoke-Mi {
    param([string] $Query, [string] $Database = 'master', [int] $TimeoutSec = 0)
    Invoke-Sqlcmd -ServerInstance $miFqdn -Database $Database -Credential $sqlCred `
                  -Query $Query -QueryTimeout $TimeoutSec -TrustServerCertificate -ErrorAction Stop
}

# --- Blob credential -----------------------------------------------------------
# MI writes .bak straight to blob storage using a SHARED ACCESS SIGNATURE credential
# whose NAME must exactly match the container URI. The SAS must not include the '?'.
if ($ArtifactType -eq 'NativeBak' -and $PSCmdlet.ShouldProcess($DestContainerUri, 'create SAS credential on instance')) {
    $containerUri = $DestContainerUri.TrimEnd('/')
    $sasSecret    = $DestContainerSas.TrimStart('?')
    Write-Host 'Creating/refreshing blob SAS credential on the instance...' -ForegroundColor Cyan
    Invoke-Mi @"
IF EXISTS (SELECT 1 FROM sys.credentials WHERE name = N'$containerUri')
    DROP CREDENTIAL [$containerUri];
CREATE CREDENTIAL [$containerUri]
    WITH IDENTITY = 'SHARED ACCESS SIGNATURE',
         SECRET   = '$sasSecret';
"@ | Out-Null
}

# --- 1. Enumerate MI LTR backups ----------------------------------------------
$listArgs = @('sql', 'midb', 'ltr-backup', 'list', '-l', $Location, '--database-state', 'All', '-o', 'json')
if ($InstanceFilter) { $listArgs += @('--mi',       $InstanceFilter) }
if ($DatabaseFilter) { $listArgs += @('--database', $DatabaseFilter) }

Write-Host "Enumerating MI LTR backups in $Location ..." -ForegroundColor Cyan
$backups = (Invoke-Az $listArgs | ConvertFrom-Json)

if ($BackupsNewerThan) {
    $backups = $backups | Where-Object { [datetime] $_.backupTime -ge $BackupsNewerThan }
}
if (-not $backups -or $backups.Count -eq 0) {
    Write-Warning 'No MI LTR backups matched. Nothing to do.'
    return
}

Write-Host "Found $($backups.Count) LTR restore point(s) to drain." -ForegroundColor Green
Write-Host "Artifact: $ArtifactType | TDE handling: $TdeMode" -ForegroundColor Green

$manifest = [System.Collections.Generic.List[object]]::new()
$index    = 0

foreach ($backup in $backups) {
    $index++

    # Property names per the ManagedInstanceLongTermRetentionBackup schema. Fall back
    # rather than silently writing blanks into the compliance manifest.
    $srcInstance = if ($backup.managedInstanceName) { $backup.managedInstanceName } else { 'unknown-instance' }
    $srcDatabase = if ($backup.databaseName)        { $backup.databaseName }        else { 'unknown-database' }
    if ($srcInstance -eq 'unknown-instance' -or $srcDatabase -eq 'unknown-database') {
        Write-Warning "Backup $($backup.id) is missing expected name properties; manifest provenance will be incomplete."
    }

    $stamp    = ([datetime] $backup.backupTime).ToString('yyyyMMdd-HHmmss')
    $stagedDb = "ltr_${srcDatabase}_$stamp" -replace '[^A-Za-z0-9_]', '_'
    if ($stagedDb.Length -gt 100) { $stagedDb = $stagedDb.Substring(0, 100) }

    $ext      = if ($ArtifactType -eq 'NativeBak') { 'bak' } else { 'bacpac' }
    $baseUri  = "$($DestContainerUri.TrimEnd('/'))/$srcInstance/$srcDatabase/$stamp"
    $blobUri  = "$baseUri.$ext"

    Write-Host ''
    Write-Host "[$index/$($backups.Count)] $srcInstance/$srcDatabase @ $($backup.backupTime)" -ForegroundColor Yellow

    if (-not $PSCmdlet.ShouldProcess($blobUri, "restore LTR backup and export $ArtifactType")) { continue }

    $record = [pscustomobject]@{
        SourceInstance = $srcInstance
        SourceDatabase = $srcDatabase
        BackupTime     = $backup.backupTime
        BackupExpiry   = $backup.backupExpirationTime
        LtrBackupId    = $backup.id
        ArtifactUri    = $blobUri
        ArtifactType   = $ArtifactType
        Stripes        = 1
        StagedDatabase = $stagedDb
        Verified       = ''
        Status         = 'pending'
        Error          = ''
        ExportedAtUtc  = ''
    }

    try {
        Write-Host '  -> restoring LTR backup onto the instance...' -ForegroundColor DarkGray
        Invoke-Az @(
            'sql', 'midb', 'ltr-backup', 'restore',
            '--backup-id',           $backup.id,
            '--dest-database',       $stagedDb,
            '--dest-mi',             $DestManagedInstance,
            '--dest-resource-group', $DestResourceGroup,
            '-o', 'none'
        ) | Out-Null

        if ($ArtifactType -eq 'NativeBak') {

            if ($TdeMode -eq 'DisableOnStagedCopy') {
                # Service-managed TDE forbids COPY_ONLY backups. The staged database is a
                # throwaway, so decrypt it, back it up, then discard it. The original is
                # untouched. Decryption is asynchronous, so poll until state 1 (unencrypted).
                Write-Host '  -> disabling TDE on the staged copy...' -ForegroundColor DarkGray
                Invoke-Mi "ALTER DATABASE [$stagedDb] SET ENCRYPTION OFF;" | Out-Null

                $deadline = (Get-Date).AddMinutes($DecryptTimeoutMinutes)
                do {
                    Start-Sleep -Seconds 20
                    $state = (Invoke-Mi @"
SELECT COALESCE(MAX(k.encryption_state), 1) AS encryption_state
FROM sys.databases d
LEFT JOIN sys.dm_database_encryption_keys k ON k.database_id = d.database_id
WHERE d.name = N'$stagedDb';
"@).encryption_state
                    Write-Host "     encryption_state = $state" -ForegroundColor DarkGray
                    if ((Get-Date) -gt $deadline) { throw "Timed out waiting for '$stagedDb' to decrypt." }
                } while ($state -ne 1)
            }

            Write-Host '  -> COPY_ONLY backup to blob...' -ForegroundColor DarkGray

            # A single blob caps at 195 GB (50,000 blocks x 4 MB MAXTRANSFERSIZE), so
            # stripe wider databases across multiple URLs. Size the stripe count from the
            # database's actual allocated size, not the compressed backup size, to stay safe.
            $sizeGb = [double] (Invoke-Mi -Database $stagedDb -Query @"
SELECT CAST(SUM(CAST(size AS bigint)) * 8.0 / 1048576.0 AS decimal(18,2)) AS size_gb
FROM sys.database_files WHERE type_desc = 'ROWS';
"@).size_gb

            $stripeCount = [math]::Max(1, [math]::Ceiling($sizeGb / $GbPerStripe))
            if ($stripeCount -gt $MaxStripes) {
                throw "Database is $sizeGb GB and needs $stripeCount stripes, above the $MaxStripes limit. Raise -GbPerStripe."
            }

            if ($stripeCount -eq 1) {
                $urls = @("N'$blobUri'")
            }
            else {
                Write-Host "     $sizeGb GB -> striping across $stripeCount blobs" -ForegroundColor DarkGray
                $urls = 1..$stripeCount | ForEach-Object { "N'$baseUri.part$_-of-$stripeCount.bak'" }
                $record.ArtifactUri = "$baseUri.part{1..$stripeCount}-of-$stripeCount.bak"
            }
            $record.Stripes = $stripeCount
            $urlList = ($urls -join ",`n     URL = ")

            # CHECKSUM makes the artifact independently verifiable years from now.
            Invoke-Mi -TimeoutSec 0 -Query @"
BACKUP DATABASE [$stagedDb]
TO URL = $urlList
WITH COPY_ONLY, COMPRESSION, CHECKSUM, FORMAT, INIT,
     MAXTRANSFERSIZE = 4194304;
"@ | Out-Null

            Write-Host '  -> verifying artifact...' -ForegroundColor DarkGray
            Invoke-Mi -TimeoutSec 0 -Query "RESTORE VERIFYONLY FROM URL = $urlList WITH CHECKSUM;" | Out-Null
            $record.Verified = 'RESTORE VERIFYONLY OK'
        }
        else {
            # No managed export API exists for MI, so drive sqlpackage directly. This host
            # must have network line-of-sight to the instance.
            Write-Host '  -> exporting BACPAC via sqlpackage...' -ForegroundColor DarkGray
            $tempBacpac = Join-Path ([System.IO.Path]::GetTempPath()) "$stagedDb.bacpac"
            & $SqlPackagePath /Action:Export `
                "/SourceServerName:$miFqdn" `
                "/SourceDatabaseName:$stagedDb" `
                "/SourceUser:$SqlAdminUser" `
                "/SourcePassword:$plainPassword" `
                /SourceTrustServerCertificate:True `
                "/TargetFile:$tempBacpac"
            if ($LASTEXITCODE -ne 0) { throw "sqlpackage export failed with exit code $LASTEXITCODE." }

            $dest = if ($DestContainerSas) { "$blobUri`?$($DestContainerSas.TrimStart('?'))" } else { $blobUri }
            & az storage blob upload --blob-url $dest --file $tempBacpac --overwrite true -o none
            if ($LASTEXITCODE -ne 0) { throw 'Uploading the BACPAC to blob storage failed.' }
            Remove-Item $tempBacpac -Force -ErrorAction SilentlyContinue
        }

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
        if (-not $KeepStagedDatabase) {
            try {
                Write-Host '  -> dropping staged database...' -ForegroundColor DarkGray
                Invoke-Az @('sql', 'midb', 'delete',
                            '-g', $DestResourceGroup,
                            '--mi', $DestManagedInstance,
                            '-n', $stagedDb, '--yes', '-o', 'none') | Out-Null
            }
            catch {
                Write-Warning "  -> staged database '$stagedDb' could not be dropped; it consumes instance storage."
            }
        }
        $manifest.Add($record)
        $manifest | Export-Csv -Path $ManifestPath -NoTypeInformation
    }
}

Write-Host ''
Write-Host "Manifest written to $ManifestPath" -ForegroundColor Cyan
$manifest | Group-Object Status | ForEach-Object { Write-Host ("  {0,-10} {1}" -f $_.Name, $_.Count) }
