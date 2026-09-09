<#
.SYNOPSIS
    Estimates the incremental cost of draining Azure SQL LTR backups into portable
    artifacts (BACPAC / native .bak) before the source subscription is deleted.

.DESCRIPTION
    LTR backups are purged when the subscription is deleted, and Microsoft exposes no
    API to copy the LTR blob directly. The only way out is:

        restore LTR backup -> live database -> export an artifact -> drop the database

    This script models the cost of that drain. It deliberately reports INCREMENTAL cost,
    i.e. cost over and above what you are already paying today, because the dominant
    term depends entirely on whether the staging target already exists:

      * SQL DB : the logical server is free, so every temp database is incremental.
      * SQL MI : if the source MI is still running, restores are free (compute is already
                 paid for) and only storage is incremental. If the MI is already gone,
                 you must stand up a staging MI and its instance-hours dominate everything.

    Prices default to East US pay-as-you-go retail rates pulled from the Azure retail
    price API. Override them with -RefreshPrices to re-query live, or pass them directly.

.PARAMETER BackupCount
    Number of individual LTR restore points to drain.

.PARAMETER AvgDatabaseGb
    Average size of the source database, in GB.

.EXAMPLE
    .\Get-LtrExportCostEstimate.ps1 -BackupCount 60 -AvgDatabaseGb 50 -Path SqlDb

.EXAMPLE
    .\Get-LtrExportCostEstimate.ps1 -BackupCount 60 -AvgDatabaseGb 50 -Path SqlMi -MiAlreadyDeleted
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][int]    $BackupCount,
    [Parameter(Mandatory)][double] $AvgDatabaseGb,

    [ValidateSet('SqlDb', 'SqlMi', 'Both')]
    [string] $Path = 'Both',

    # ---- SQL DB staging tier -------------------------------------------------
    # LTR restore lets you pick the target SKU, so restore into the cheapest tier
    # that still fits the data. GP Gen5 2 vCore is a good speed/cost balance.
    [int]    $StagingVCores       = 2,
    [double] $VCoreHourUsd        = 0.15,

    # ---- SQL MI staging instance ---------------------------------------------
    [int]    $MiVCores            = 4,        # GP Gen5 minimum
    [double] $MiVCoreHourUsd      = 0.15,
    [double] $MiProvisioningHours = 5.0,      # MI create is famously slow, and billed
    [switch] $MiAlreadyDeleted,               # if NOT set, restores ride the existing MI for free
    [switch] $ApplyAhb,                       # Azure Hybrid Benefit on the staging MI

    # ---- Throughput assumptions ----------------------------------------------
    # Deliberately conservative. Measure your first database and re-run.
    [double] $RestoreFixedMin     = 12.0,
    [double] $RestoreMinPerGb     = 0.35,
    [double] $ExportFixedMin      = 6.0,
    [double] $ExportMinPerGb      = 1.20,     # BACPAC export is the slow part
    [double] $NativeBackupMinPerGb= 0.25,     # .bak is much faster than BACPAC

    # ---- Artifact storage -----------------------------------------------------
    [double] $BacpacCompression   = 4.0,      # BACPAC is roughly 4x smaller than the DB
    [double] $BakCompression      = 3.0,
    [double] $BlobGbMonthUsd      = 0.02,     # Cool LRS. Archive is ~0.00099
    [int]    $RetentionMonths     = 84,       # 7 years

    # ---- Staging storage (transient, billed only while the staged DB exists) ---
    [double] $SqlStorageGbMonthUsd = 0.12,    # GP data storage, same rate for DB and MI

    # ---- Bandwidth ------------------------------------------------------------
    # Ingress to storage is free. Subscription is NOT a billing boundary; REGION is.
    # Same region  -> 0.00 /GB
    # Cross-region -> 0.02 /GB  (Standard Inter-Region Data Transfer)
    # Internet     -> ~0.087/GB after the first 100 GB/month free
    [ValidateSet('SameRegion', 'CrossRegion', 'Internet')]
    [string] $ArtifactDestination = 'SameRegion',

    [switch] $RefreshPrices
)

$ErrorActionPreference = 'Stop'

function Get-RetailPrice {
    param([string] $Filter)
    $uri = "https://prices.azure.com/api/retail/prices?`$filter=$([uri]::EscapeDataString($Filter))"
    (Invoke-RestMethod -Uri $uri).Items
}

if ($RefreshPrices) {
    Write-Verbose 'Refreshing prices from the Azure retail price API...'
    $db = Get-RetailPrice "serviceName eq 'SQL Database' and armRegionName eq 'eastus' and priceType eq 'Consumption' and unitOfMeasure eq '1 Hour'" |
            Where-Object { $_.productName -eq 'SQL Database Single/Elastic Pool General Purpose - Compute Gen5' -and $_.skuName -eq '1 vCore' } |
            Select-Object -First 1
    if ($db) { $VCoreHourUsd = [double] $db.retailPrice }

    $mi = Get-RetailPrice "serviceName eq 'SQL Managed Instance' and armRegionName eq 'eastus' and priceType eq 'Consumption' and unitOfMeasure eq '1 Hour'" |
            Where-Object { $_.productName -eq 'SQL Managed Instance General Purpose - Compute Gen5' -and $_.skuName -eq '1 vCore' } |
            Select-Object -First 1
    if ($mi) { $MiVCoreHourUsd = [double] $mi.retailPrice }

    Write-Verbose "SQL DB vCore/hr = $VCoreHourUsd ; SQL MI vCore/hr = $MiVCoreHourUsd"
}

# Azure Hybrid Benefit strips the SQL licence component out of the vCore rate.
# GP Gen5 compute is roughly 55% licence, so AHB lands near a 55% reduction.
if ($ApplyAhb) { $MiVCoreHourUsd = $MiVCoreHourUsd * 0.45 }

$results = [System.Collections.Generic.List[object]]::new()

# Egress rate. Writing INTO blob storage is free; you only pay when the bytes cross a
# region boundary or leave Azure. Crossing a subscription boundary costs nothing.
$egressGbUsd = switch ($ArtifactDestination) {
    'SameRegion'  { 0.00  }
    'CrossRegion' { 0.02  }
    'Internet'    { 0.087 }
}

# ---------------------------------------------------------------------------
# Azure SQL Database path: temp DB per backup, deleted immediately after export
# ---------------------------------------------------------------------------
if ($Path -in 'SqlDb', 'Both') {

    $restoreMin  = $RestoreFixedMin + ($RestoreMinPerGb * $AvgDatabaseGb)
    $exportMin   = $ExportFixedMin  + ($ExportMinPerGb  * $AvgDatabaseGb)
    $perBackupHr = ($restoreMin + $exportMin) / 60.0

    $computeUsd  = $perBackupHr * $StagingVCores * $VCoreHourUsd * $BackupCount

    # The staged database occupies GP storage for the hours it exists. Prorated from a
    # monthly rate this is almost always cents, but it is not structurally zero.
    $stagingStorageUsd = $AvgDatabaseGb * $SqlStorageGbMonthUsd * ($perBackupHr / 730.0) * $BackupCount

    $artifactGb  = ($AvgDatabaseGb / $BacpacCompression) * $BackupCount
    $storageMo   = $artifactGb * $BlobGbMonthUsd
    $egressUsd   = $artifactGb * $egressGbUsd

    $results.Add([pscustomobject]@{
        Path              = 'Azure SQL Database (BACPAC)'
        StagingTarget     = "logical server (free) + GP_Gen5 $StagingVCores vCore temp DB"
        MinutesPerBackup  = [math]::Round($restoreMin + $exportMin, 1)
        TotalComputeHours = [math]::Round($perBackupHr * $BackupCount, 1)
        OneTimeComputeUsd = [math]::Round($computeUsd, 2)
        StagingStorageUsd = [math]::Round($stagingStorageUsd, 2)
        BandwidthUsd      = [math]::Round($egressUsd, 2)
        ArtifactGb        = [math]::Round($artifactGb, 1)
        StorageUsdMonth   = [math]::Round($storageMo, 2)
        StorageUsdTotal   = [math]::Round($storageMo * $RetentionMonths, 2)
        GrandTotalUsd     = [math]::Round($computeUsd + $stagingStorageUsd + $egressUsd + ($storageMo * $RetentionMonths), 2)
    })
}

# ---------------------------------------------------------------------------
# Azure SQL Managed Instance path: all restores share ONE instance lifetime
# ---------------------------------------------------------------------------
if ($Path -in 'SqlMi', 'Both') {

    $restoreMin  = $RestoreFixedMin + ($RestoreMinPerGb * $AvgDatabaseGb)
    $backupMin   = $NativeBackupMinPerGb * $AvgDatabaseGb
    $workHours   = (($restoreMin + $backupMin) / 60.0) * $BackupCount

    if ($MiAlreadyDeleted) {
        # You are paying for a staging instance you would not otherwise have.
        $billedHours = $workHours + $MiProvisioningHours
        $computeUsd  = $billedHours * $MiVCores * $MiVCoreHourUsd
        $target      = "NEW staging MI, GP_Gen5 $MiVCores vCore" + $(if ($ApplyAhb) { ' (AHB)' } else { '' })
        $note        = 'Instance-hours dominate. Batch every database into one instance lifetime.'
    }
    else {
        # The MI is still running and already paid for: restores are free.
        $billedHours = 0
        $computeUsd  = 0
        $target      = 'EXISTING source MI (already paid for)'
        $note        = 'Incremental compute is zero. Drain BEFORE deleting the MI.'
    }

    $artifactGb = ($AvgDatabaseGb / $BakCompression) * $BackupCount
    $storageMo  = $artifactGb * $BlobGbMonthUsd
    $egressUsd  = $artifactGb * $egressGbUsd

    # Staged databases occupy instance storage. On MI this is charged even when the
    # instance is stopped, so do not leave staged copies lying around.
    $stagingStorageUsd = $AvgDatabaseGb * $SqlStorageGbMonthUsd * (($restoreMin + $backupMin) / 60.0 / 730.0) * $BackupCount

    $results.Add([pscustomobject]@{
        Path              = 'Azure SQL MI (native .bak COPY_ONLY)'
        StagingTarget     = $target
        MinutesPerBackup  = [math]::Round($restoreMin + $backupMin, 1)
        TotalComputeHours = [math]::Round($billedHours, 1)
        OneTimeComputeUsd = [math]::Round($computeUsd, 2)
        StagingStorageUsd = [math]::Round($stagingStorageUsd, 2)
        BandwidthUsd      = [math]::Round($egressUsd, 2)
        ArtifactGb        = [math]::Round($artifactGb, 1)
        StorageUsdMonth   = [math]::Round($storageMo, 2)
        StorageUsdTotal   = [math]::Round($storageMo * $RetentionMonths, 2)
        GrandTotalUsd     = [math]::Round($computeUsd + $stagingStorageUsd + $egressUsd + ($storageMo * $RetentionMonths), 2)
        Note              = $note
    })
}

Write-Host ''
Write-Host "LTR drain estimate - $BackupCount backups x $AvgDatabaseGb GB, $RetentionMonths months retention" -ForegroundColor Cyan
Write-Host ('=' * 78) -ForegroundColor DarkGray
$results | Format-List
Write-Host 'Incremental cost only. Excludes the LTR storage you already pay for today.' -ForegroundColor DarkGray
Write-Host "Artifact destination: $ArtifactDestination (egress `$$egressGbUsd/GB)."       -ForegroundColor DarkGray
Write-Host ''

$results
