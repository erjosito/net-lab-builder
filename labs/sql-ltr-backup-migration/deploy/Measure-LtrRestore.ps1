<#
.SYNOPSIS
    Measures Azure SQL Database long term retention (LTR) backup restore duration
    at multiple source sizes and emits raw observations as JSON.

.DESCRIPTION
    Restores each supplied LTR backup into a NEW database on the destination server,
    strictly SEQUENTIALLY, and times each restore from submit to first observed Online.

    Timing method:
      - Submit timestamp is captured immediately BEFORE the az restore call is issued.
      - The restore is issued with --no-wait so the blocking call's wall time is never trusted.
      - Destination state is then polled with 'az sql db show' on a fixed interval.
      - Completion timestamp is captured immediately after the destination first reports Online.
      - Because state is sampled, each observed duration carries a precision bound of
        plus/minus one poll interval.

    This script never deletes any Azure resource.

.NOTES
    Entra-only auth. No SQL authentication is used anywhere. All calls are control plane.
#>
[CmdletBinding()]
param(
    [string] $SubscriptionId   = 'a8fbd8e1-fb5a-4411-804a-4ac80929c93c',
    [string] $ResourceGroup    = 'rg-ltr-lab',
    [string] $Location         = 'swedencentral',
    [string] $Server           = 'ltrlab552754-sql',

    # Lab resource name prefix. Note this is NOT the server name: databases are
    # named '<prefix>-calib-<size>' while the server is '<prefix>-sql'.
    [string] $Prefix           = 'ltrlab552754',

    # Compute for every restore target. Held IDENTICAL across all sizes so the
    # linear fit is not contaminated by mixed compute models. Provisioned is used
    # deliberately: the source databases are serverless (GP_S_Gen5_4) and serverless
    # auto-pause / auto-resume would add non-restore latency to the observations.
    [string] $ServiceObjective = 'GP_Gen5_4',

    [int]    $PollIntervalSec  = 15,
    [int]    $TimeoutMin       = 240,
    [string] $DateSuffix       = '20260911',
    [string] $OutFile
)

$PSNativeCommandArgumentPassing = 'Standard'
$ErrorActionPreference = 'Stop'

function Get-UtcStamp { (Get-Date).ToUniversalTime().ToString('o') }

Write-Host "Subscription : $SubscriptionId"
Write-Host "Server       : $Server ($ResourceGroup / $Location)"
Write-Host "Target SLO   : $ServiceObjective (identical for all restores)"
Write-Host "Poll interval: ${PollIntervalSec}s  ->  precision bound +/- ${PollIntervalSec}s"
Write-Host ''

# ---------------------------------------------------------------------------
# Discover LTR backups. IDs are used verbatim; they are never hand assembled,
# because the ';' separators and the storage tier suffix are significant.
# ---------------------------------------------------------------------------
Write-Host 'Listing LTR backups...'
$backupsJson = az sql db ltr-backup list `
    --location $Location `
    --server $Server `
    --resource-group $ResourceGroup `
    -o json
if ($LASTEXITCODE -ne 0) { throw "az sql db ltr-backup list failed with exit code $LASTEXITCODE" }
$backups = $backupsJson | ConvertFrom-Json

# Ordered smallest to largest so that a slow large restore never blocks the
# small observations from being captured.
$plan = @(
    @{ Source = "$Prefix-calib-1gb";  Short = 'calib-1gb'  }
    @{ Source = "$Prefix-calib-5gb";  Short = 'calib-5gb'  }
    @{ Source = "$Prefix-calib-20gb"; Short = 'calib-20gb' }
)

$results = @()

foreach ($item in $plan) {

    $sourceDb = $item.Source
    $destDb   = "$($item.Short)-ltrrestore-$DateSuffix"

    # Client side filter. Complex JMESPath '[? ]' expressions are avoided because
    # they break quoting under PowerShell.
    $backup = $backups | Where-Object { $_.databaseName -eq $sourceDb } | Sort-Object backupTime | Select-Object -Last 1
    if (-not $backup) { throw "No LTR backup found for source database $sourceDb" }

    Write-Host "=== $sourceDb  ->  $destDb ==="
    Write-Host "    backupTime : $($backup.backupTime)"
    Write-Host "    backupId   : $($backup.id)"

    # -----------------------------------------------------------------------
    # Source size, on the allocated_data_storage basis. This is the same basis
    # ('allocated_8kb_pages') used by the already published export fit, so the
    # restore slope and the export slope remain directly composable.
    # 'storage' (data space used) is also recorded so the basis choice can be
    # re-derived later without re-running anything.
    # -----------------------------------------------------------------------
    $dbResourceId = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Sql/servers/$Server/databases/$sourceDb"
    $metricsJson = az monitor metrics list `
        --resource $dbResourceId `
        --metric storage allocated_data_storage `
        --interval PT5M --aggregation Maximum -o json
    if ($LASTEXITCODE -ne 0) { throw "az monitor metrics list failed for $sourceDb with exit code $LASTEXITCODE" }
    $metrics = $metricsJson | ConvertFrom-Json

    $allocatedBytes = $null
    $usedBytes      = $null
    foreach ($m in $metrics.value) {
        $points = $m.timeseries[0].data | Where-Object { $null -ne $_.maximum }
        $last   = $points | Select-Object -Last 1
        if ($m.name.value -eq 'allocated_data_storage') { $allocatedBytes = $last.maximum }
        if ($m.name.value -eq 'storage')                { $usedBytes      = $last.maximum }
    }

    $allocatedGiB = [math]::Round($allocatedBytes / 1GB, 4)
    $usedGiB      = [math]::Round($usedBytes      / 1GB, 4)
    Write-Host "    allocated  : $allocatedGiB GiB   used: $usedGiB GiB"

    # -----------------------------------------------------------------------
    # Issue the restore. Submit stamp is taken immediately before the call.
    # -----------------------------------------------------------------------
    $submitUtc = Get-UtcStamp
    Write-Host "    submit     : $submitUtc"

    $restoreOut = az sql db ltr-backup restore `
        --backup-id $backup.id `
        --dest-database $destDb `
        --dest-server $Server `
        --dest-resource-group $ResourceGroup `
        --service-objective $ServiceObjective `
        --no-wait 2>&1
    $restoreExit = $LASTEXITCODE

    if ($restoreExit -ne 0) {
        # A failure on one size must not become a verdict about the other sizes.
        # Record it verbatim and continue to the next size.
        $errText = ($restoreOut | Out-String).Trim()
        Write-Warning "Restore submit FAILED for $destDb (exit $restoreExit)"
        Write-Host $errText
        $results += [pscustomobject]@{
            SourceDatabase        = $sourceDb
            DestinationDatabase   = $destDb
            BackupId              = $backup.id
            BackupTimeUtc         = $backup.backupTime
            AllocatedDataBytes    = $allocatedBytes
            AllocatedDataGiB      = $allocatedGiB
            DataSpaceUsedBytes    = $usedBytes
            DataSpaceUsedGiB      = $usedGiB
            ServiceObjective      = $ServiceObjective
            SubmitUtc             = $submitUtc
            OnlineUtc             = $null
            RestoreSeconds        = $null
            RestoreMinutes        = $null
            PollIntervalSec       = $PollIntervalSec
            Succeeded             = $false
            Error                 = $errText
        }
        continue
    }

    # -----------------------------------------------------------------------
    # Poll for Online. The destination legitimately does not exist for the first
    # several polls, so 'not found' is a normal phase and not a failure.
    # -----------------------------------------------------------------------
    $deadline  = (Get-Date).AddMinutes($TimeoutMin)
    $onlineUtc = $null
    $lastState = '(absent)'
    $polls     = 0

    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds $PollIntervalSec
        $polls++

        $showOut = az sql db show --name $destDb --server $Server --resource-group $ResourceGroup -o json 2>$null
        if ($LASTEXITCODE -eq 0 -and $showOut) {
            $db = $showOut | ConvertFrom-Json
            if ($db.status -ne $lastState) {
                $lastState = $db.status
                Write-Host "    [$(Get-UtcStamp)] poll $polls state=$lastState"
            }
            if ($db.status -eq 'Online') {
                $onlineUtc = Get-UtcStamp
                break
            }
        }
        else {
            if ($lastState -ne '(absent)') { $lastState = '(absent)' }
            if ($polls % 8 -eq 0) { Write-Host "    [$(Get-UtcStamp)] poll $polls destination not yet visible" }
        }
    }

    if (-not $onlineUtc) {
        Write-Warning "TIMEOUT after $TimeoutMin min waiting for $destDb to report Online. Resource left in place."
        $results += [pscustomobject]@{
            SourceDatabase        = $sourceDb
            DestinationDatabase   = $destDb
            BackupId              = $backup.id
            BackupTimeUtc         = $backup.backupTime
            AllocatedDataBytes    = $allocatedBytes
            AllocatedDataGiB      = $allocatedGiB
            DataSpaceUsedBytes    = $usedBytes
            DataSpaceUsedGiB      = $usedGiB
            ServiceObjective      = $ServiceObjective
            SubmitUtc             = $submitUtc
            OnlineUtc             = $null
            RestoreSeconds        = $null
            RestoreMinutes        = $null
            PollIntervalSec       = $PollIntervalSec
            Succeeded             = $false
            Error                 = "Timed out after $TimeoutMin minutes. Last observed state: $lastState"
        }
        continue
    }

    $seconds = [math]::Round(([datetime]$onlineUtc - [datetime]$submitUtc).TotalSeconds, 3)
    $minutes = [math]::Round($seconds / 60, 4)
    Write-Host "    online     : $onlineUtc"
    Write-Host "    duration   : $seconds s  ($minutes min)  +/- ${PollIntervalSec}s"
    Write-Host ''

    $results += [pscustomobject]@{
        SourceDatabase        = $sourceDb
        DestinationDatabase   = $destDb
        BackupId              = $backup.id
        BackupTimeUtc         = $backup.backupTime
        AllocatedDataBytes    = $allocatedBytes
        AllocatedDataGiB      = $allocatedGiB
        DataSpaceUsedBytes    = $usedBytes
        DataSpaceUsedGiB      = $usedGiB
        ServiceObjective      = $ServiceObjective
        SubmitUtc             = $submitUtc
        OnlineUtc             = $onlineUtc
        RestoreSeconds        = $seconds
        RestoreMinutes        = $minutes
        PollIntervalSec       = $PollIntervalSec
        Succeeded             = $true
        Error                 = $null
    }
}

# ---------------------------------------------------------------------------
# Ordinary least squares fit of restore minutes against allocated GiB.
# R squared is reported only when the independent column genuinely varies and
# there are at least three points. Otherwise it is reported as null rather than
# a tautological 1.0.
# ---------------------------------------------------------------------------
$ok = @($results | Where-Object { $_.Succeeded })
$fit = [ordered]@{
    Points          = $ok.Count
    SizeBasis       = 'allocated_data_storage (Azure Monitor Maximum), GiB. Identical basis to the published export fit SizeBasis allocated_8kb_pages.'
    FixedMin        = $null
    MinPerGb        = $null
    RSquared        = $null
    RSquaredNote    = $null
}

if ($ok.Count -ge 2) {
    $xs = $ok | ForEach-Object { [double]$_.AllocatedDataGiB }
    $ys = $ok | ForEach-Object { [double]$_.RestoreMinutes }
    $n  = $xs.Count
    $mx = ($xs | Measure-Object -Average).Average
    $my = ($ys | Measure-Object -Average).Average

    $sxx = 0.0; $sxy = 0.0
    for ($i = 0; $i -lt $n; $i++) {
        $dx = $xs[$i] - $mx
        $sxx += $dx * $dx
        $sxy += $dx * ($ys[$i] - $my)
    }

    if ($sxx -eq 0) {
        $fit.RSquaredNote = 'Independent variable column is constant. Slope and R squared are undefined and are reported as null.'
    }
    else {
        $slope     = $sxy / $sxx
        $intercept = $my - ($slope * $mx)
        $fit.MinPerGb = [math]::Round($slope, 6)
        $fit.FixedMin = [math]::Round($intercept, 6)

        if ($n -ge 3) {
            $ssTot = 0.0; $ssRes = 0.0
            for ($i = 0; $i -lt $n; $i++) {
                $pred   = $intercept + ($slope * $xs[$i])
                $ssRes += [math]::Pow($ys[$i] - $pred, 2)
                $ssTot += [math]::Pow($ys[$i] - $my, 2)
            }
            if ($ssTot -eq 0) {
                $fit.RSquaredNote = 'Dependent variable column is constant. R squared is undefined and is reported as null.'
            }
            else {
                $fit.RSquared = [math]::Round(1 - ($ssRes / $ssTot), 6)
                $fit.RSquaredNote = "Genuine R squared over $n non-degenerate points."
            }
        }
        else {
            $fit.RSquaredNote = 'Only two points. R squared would be tautologically 1.0, so it is reported as null.'
        }
    }
}
else {
    $fit.RSquaredNote = 'Fewer than two successful observations. No fit produced.'
}

$payload = [ordered]@{
    GeneratedUtc    = Get-UtcStamp
    Server          = $Server
    ResourceGroup   = $ResourceGroup
    Location        = $Location
    PollIntervalSec = $PollIntervalSec
    PrecisionNote   = "Restore state was sampled every $PollIntervalSec seconds, so each observed duration is accurate to plus or minus $PollIntervalSec seconds."
    Sequential      = $true
    Observations    = $results
    Fit             = $fit
}

$json = $payload | ConvertTo-Json -Depth 8
if ($OutFile) {
    $json | Set-Content -Path $OutFile -Encoding utf8
    Write-Host "Wrote $OutFile"
}
Write-Output $json
