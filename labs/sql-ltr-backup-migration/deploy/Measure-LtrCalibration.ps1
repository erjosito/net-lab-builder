<#
.SYNOPSIS
    Turns lab measurements into calibrated parameters for Get-LtrExportCostEstimate.ps1.

.DESCRIPTION
    PHASE 4 of the lab, and the reason the lab seeds databases of different sizes.

    The cost model treats drain time as a straight line:

        minutes = FixedOverhead + (PerGb * SizeGb)

    With one database size those two terms are inseparable: any measurement can be
    explained by a large fixed cost, a large slope, or anything between. With three sizes
    spanning an order of magnitude, an ordinary least-squares fit recovers both, and the
    residuals reveal whether the relationship is even linear. If R-squared is poor, the
    linear model itself is wrong and the estimate should not be trusted.

    The compression probes are handled separately. Because both probe databases are the
    same size and differ only in compressibility, the ratio between their artifact sizes
    is a direct measurement of how much the data shape matters, and bounds the
    BacpacCompression / BakCompression parameters instead of guessing them.

.PARAMETER TimingCsv
    A manifest CSV written by Export-SqlDbLtrBackups.ps1 or Export-SqlMiLtrBackups.ps1.
    The drain scripts instrument themselves, so their manifest is the measurement run;
    no separate timing file needs assembling.

    Column names are matched flexibly, so a hand-written CSV with Database/SizeGb also
    works. Required data: a database name, a source size, restore and export minutes,
    and an artifact size.

.PARAMETER ExcludeDatabase
    Databases to hold out of the fit. Fitting a model and then judging it by how well it
    reproduces its own inputs proves nothing. Hold one size out, fit on the rest, and
    compare the prediction against the measurement that was never used.

.EXAMPLE
    .\Measure-LtrCalibration.ps1 -TimingCsv .\ltr-export-manifest-20250101-120000.csv

.EXAMPLE
    # Held-out validation: fit without the 5 GB database, then check it.
    .\Measure-LtrCalibration.ps1 -TimingCsv .\manifest.csv -ExcludeDatabase calib-5gb
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $TimingCsv,
    [string]   $OutputPath = './calibrated-parameters.json',
    [string[]] $ExcludeDatabase = @()
)

$ErrorActionPreference = 'Stop'

function Get-Field {
    # Manifests and hand-written timing files disagree on column names. Accept both
    # rather than making the caller reshape the CSV.
    param($Row, [string[]] $Names, $Default = $null)
    foreach ($n in $Names) {
        if ($Row.PSObject.Properties.Name -contains $n) {
            $v = $Row.$n
            if ($null -ne $v -and "$v".Trim() -ne '') { return $v }
        }
    }
    return $Default
}

$raw = Import-Csv $TimingCsv

# Only exported rows carry timings. Failed rows have blanks and would poison the fit.
$status = $raw | Where-Object { $_.PSObject.Properties.Name -contains 'Status' }
if ($status) { $raw = $raw | Where-Object { $_.Status -eq 'exported' } }

$rows = $raw | ForEach-Object {
    $name = Get-Field $_ @('Database', 'SourceDatabase', 'StagedDatabase')
    $size = Get-Field $_ @('SizeGb', 'SourceGb')
    $rest = Get-Field $_ @('RestoreMinutes')
    $exp  = Get-Field $_ @('ExportMinutes')
    $art  = Get-Field $_ @('ArtifactGb')
    if ($null -eq $size -or $null -eq $rest -or $null -eq $exp) {
        Write-Warning "Skipping '$name': missing size or timing data."
        return
    }
    [pscustomobject]@{
        Database       = $name
        # Measured size, not requested size. Allocated size diverges from what was
        # written (off-row storage, fill factor), and that bias lands in the slope.
        SizeGb         = [double] $size
        # Shape is a lab concept; infer it from the naming convention when absent so a
        # production manifest still fits.
        Shape          = Get-Field $_ @('Shape') $(
                             if ("$name" -match 'compressible') { 'compressible' }
                             elseif ("$name" -match 'random')   { 'random' }
                             else                               { 'mixed' })
        RestoreMinutes = [double] $rest
        ExportMinutes  = [double] $exp
        ArtifactGb     = if ($null -ne $art) { [double] $art } else { 0 }
    }
}

$holdout = @()
if ($ExcludeDatabase) {
    $holdout = @($rows | Where-Object { $ExcludeDatabase -contains $_.Database })
    $rows    = @($rows | Where-Object { $ExcludeDatabase -notcontains $_.Database })
    Write-Host "Holding out: $($ExcludeDatabase -join ', ')" -ForegroundColor Yellow
}
if (-not $rows) { throw "No usable rows in $TimingCsv." }

if (-not $rows) { throw "No rows found in $TimingCsv." }

function Get-LinearFit {
    <#
        Ordinary least squares for y = intercept + slope*x, plus R-squared so the caller
        can tell whether the linear assumption actually holds.
    #>
    param([double[]] $X, [double[]] $Y)

    $n = $X.Count
    if ($n -lt 2) { throw 'Need at least two distinct sizes to separate fixed cost from slope.' }

    $meanX = ($X | Measure-Object -Average).Average
    $meanY = ($Y | Measure-Object -Average).Average

    $sxx = 0.0; $sxy = 0.0
    for ($i = 0; $i -lt $n; $i++) {
        $dx   = $X[$i] - $meanX
        $sxx += $dx * $dx
        $sxy += $dx * ($Y[$i] - $meanY)
    }
    if ($sxx -eq 0) { throw 'All databases are the same size; the slope is unidentifiable. Seed different sizes.' }

    $slope     = $sxy / $sxx
    $intercept = $meanY - ($slope * $meanX)

    $ssRes = 0.0; $ssTot = 0.0
    for ($i = 0; $i -lt $n; $i++) {
        $pred   = $intercept + ($slope * $X[$i])
        $ssRes += [math]::Pow($Y[$i] - $pred, 2)
        $ssTot += [math]::Pow($Y[$i] - $meanY, 2)
    }
    $r2 = if ($ssTot -eq 0) { 1.0 } else { 1.0 - ($ssRes / $ssTot) }

    [pscustomobject]@{
        Intercept = [math]::Round($intercept, 2)
        Slope     = [math]::Round($slope, 4)
        RSquared  = [math]::Round($r2, 4)
        Points    = $n
    }
}

# --- Timing fit, calibration databases only -----------------------------------
$calib = $rows | Where-Object Shape -eq 'mixed' | Sort-Object SizeGb
if ($calib.Count -lt 2) { throw 'Need at least two mixed-shape calibration databases.' }

$sizes    = [double[]] ($calib.SizeGb)
$restores = [double[]] ($calib.RestoreMinutes)
$exports  = [double[]] ($calib.ExportMinutes)

# Guard: refuse to fit a regression through an all-zero restore column.
# When no LTR restores have been performed yet, RestoreMinutes is 0 for every row.
# A regression through five identical zeros gives intercept=0, slope=0, R-squared=1.0,
# which looks like a perfect fit but is a degenerate case: the model has no data.
# Emitting those zeros would silently drop the restore term from cost estimates.
$restoreMeasured = ($restores | Where-Object { $_ -gt 0 }).Count -gt 0
if (-not $restoreMeasured) {
    Write-Warning "All RestoreMinutes are 0: restore timing has not been measured. Restore fit skipped. Re-run once LTR backups are available and restore durations are captured."
    $restoreFit = $null
} else {
    $restoreFit = Get-LinearFit -X $sizes -Y $restores
}

$exportFit  = Get-LinearFit -X $sizes -Y $exports

Write-Host ''
Write-Host 'Timing fit (minutes = intercept + slope * SizeGb)' -ForegroundColor Cyan
Write-Host ('=' * 62) -ForegroundColor DarkGray

$timingTable = @()
if ($restoreFit) {
    $timingTable += [pscustomobject]@{
        Measurement = 'Restore'
        FixedMin    = $restoreFit.Intercept
        MinPerGb    = $restoreFit.Slope
        RSquared    = $restoreFit.RSquared
    }
} else {
    $timingTable += [pscustomobject]@{
        Measurement = 'Restore'
        FixedMin    = 'N/A (not measured)'
        MinPerGb    = 'N/A'
        RSquared    = 'N/A'
    }
}
$timingTable += [pscustomobject]@{
    Measurement = 'Export'
    FixedMin    = $exportFit.Intercept
    MinPerGb    = $exportFit.Slope
    RSquared    = $exportFit.RSquared
}
$timingTable | Format-Table -AutoSize | Out-String -Width 100 | Write-Host

$fitsToCheck = @(@{N='Export';F=$exportFit})
if ($restoreFit) { $fitsToCheck += @{N='Restore';F=$restoreFit} }
foreach ($fit in $fitsToCheck) {
    if ($fit.F.RSquared -lt 0.90) {
        Write-Warning "$($fit.N): R-squared $($fit.F.RSquared) is poor. The linear model is questionable; add more sizes before trusting the estimate."
    }
    if ($fit.F.Intercept -lt 0) {
        Write-Warning "$($fit.N): negative fixed overhead is unphysical, a sign of too few or too clustered sizes."
    }
}

# --- Compression measurement ---------------------------------------------------
Write-Host 'Compression ratios (source GB / artifact GB)' -ForegroundColor Cyan
Write-Host ('=' * 62) -ForegroundColor DarkGray
$ratios = $rows |
    Where-Object { $_.ArtifactGb -gt 0 } |
    ForEach-Object {
        [pscustomobject]@{
            Database = $_.Database
            Shape    = $_.Shape
            SizeGb   = $_.SizeGb
            Artifact = $_.ArtifactGb
            Ratio    = [math]::Round($_.SizeGb / $_.ArtifactGb, 2)
        }
    }
$ratios | Sort-Object Ratio | Format-Table -AutoSize | Out-String -Width 100 | Write-Host

$worst = ($ratios | Measure-Object Ratio -Minimum).Minimum
$best  = ($ratios | Measure-Object Ratio -Maximum).Maximum
Write-Host "Observed range: ${worst}x (worst) to ${best}x (best)" -ForegroundColor Yellow
Write-Host 'Use the WORST ratio for budgeting. It produces the largest artifacts and' -ForegroundColor DarkGray
Write-Host 'the storage term dominates total cost.' -ForegroundColor DarkGray

# --- Held-out validation ------------------------------------------------------
# The honest test of the model: predict a measurement it never saw.
$holdoutReport = @()
if ($holdout) {
    Write-Host ''
    Write-Host 'Held-out prediction check' -ForegroundColor Cyan
    Write-Host ('=' * 62) -ForegroundColor DarkGray
    foreach ($h in $holdout) {
        # The fit is built from mixed-shape databases only. Holding out a probe reports
        # a comparison against a model that never included its shape, which is not a
        # generalisation test; it mostly measures the compression difference.
        if ($h.Shape -ne 'mixed') {
            Write-Warning "'$($h.Database)' is shape '$($h.Shape)', which is excluded from the fit anyway. Hold out a mixed-shape database for a meaningful test."
        }
        foreach ($phase in @(
            @{ Name = 'Restore'; Fit = $restoreFit; Actual = $h.RestoreMinutes },
            @{ Name = 'Export';  Fit = $exportFit;  Actual = $h.ExportMinutes }
        )) {
            if (-not $phase.Fit) { continue }   # skip unmeasured phases
            $predicted = $phase.Fit.Intercept + ($phase.Fit.Slope * $h.SizeGb)
            $errPct = if ($phase.Actual -ne 0) {
                [math]::Round(100 * ($predicted - $phase.Actual) / $phase.Actual, 1)
            } else { $null }
            $holdoutReport += [pscustomobject]@{
                Database    = $h.Database
                Phase       = $phase.Name
                SizeGb      = $h.SizeGb
                PredictedMin= [math]::Round($predicted, 2)
                ActualMin   = [math]::Round($phase.Actual, 2)
                ErrorPct    = $errPct
            }
        }
    }
    $holdoutReport | Format-Table -AutoSize | Out-String -Width 100 | Write-Host

    $maxErr = ($holdoutReport | Where-Object { $null -ne $_.ErrorPct } |
               ForEach-Object { [math]::Abs($_.ErrorPct) } | Measure-Object -Maximum).Maximum
    if ($maxErr -gt 25) {
        Write-Warning "Held-out error reaches $maxErr%. The linear model does not generalise well; treat estimates as order-of-magnitude only."
    }
    else {
        Write-Host "Worst held-out error: $maxErr%." -ForegroundColor Green
    }
}

$calibrated = [pscustomobject]@{
    GeneratedUtc      = (Get-Date).ToUniversalTime().ToString('o')
    Source            = (Resolve-Path $TimingCsv).Path
    # Restore: null when no LTR restores were performed. Do not use 0 as a default;
    # a zero-valued restore term silently understates the drain timeline.
    RestoreMeasured   = $restoreMeasured
    RestoreFixedMin   = if ($restoreFit) { $restoreFit.Intercept } else { $null }
    RestoreMinPerGb   = if ($restoreFit) { $restoreFit.Slope    } else { $null }
    RestoreRSquared   = if ($restoreFit) { $restoreFit.RSquared } else { $null }
    RestoreNote       = if (-not $restoreMeasured) { 'Restore timing not measured. All RestoreMinutes were 0 in the source CSV. Re-run Measure-LtrCalibration.ps1 once LTR backups are available and restore durations have been captured.' } else { $null }
    ExportFixedMin    = $exportFit.Intercept
    ExportMinPerGb    = $exportFit.Slope
    ExportRSquared    = $exportFit.RSquared
    # ExportEnvironment documents conditions under which this was measured. Export
    # throughput is environment-specific: private endpoint, same-region, and VM SKU
    # all dominate the result. Do not reuse these numbers for a different topology.
    ExportEnvironment = $null   # caller should set; see README
    CompressionWorst  = $worst
    CompressionBest   = $best
    # CompressionBest may include a synthetic upper-bound probe (e.g. repeated-byte
    # data). That value is not a planning input. The safe budgeting value is
    # CompressionWorst. Mixed realistic data typically compresses at ~4x.
    CompressionBestNote = $null  # set by caller if probe-compressible was included
    SizesTestedGb     = @($calib.SizeGb)
    HeldOut           = $holdoutReport
}
$calibrated | ConvertTo-Json -Depth 4 | Set-Content $OutputPath

Write-Host ''
Write-Host "Calibrated parameters written to $OutputPath" -ForegroundColor Green
Write-Host 'Feed them into the estimator:' -ForegroundColor Green
Write-Host ''
Write-Host "  .\Get-LtrExportCostEstimate.ps1 -BackupCount <n> -AvgDatabaseGb <gb> ``" -ForegroundColor Cyan
if ($restoreFit) {
    Write-Host "      -RestoreFixedMin $($restoreFit.Intercept) -RestoreMinPerGb $($restoreFit.Slope) ``" -ForegroundColor Cyan
} else {
    Write-Host "      # -RestoreFixedMin and -RestoreMinPerGb: not measured; omit or supply defaults" -ForegroundColor DarkGray
}
Write-Host "      -ExportFixedMin $($exportFit.Intercept) -ExportMinPerGb $($exportFit.Slope) ``" -ForegroundColor Cyan
Write-Host "      -BacpacCompression $worst" -ForegroundColor Cyan
Write-Host ''

$calibrated
