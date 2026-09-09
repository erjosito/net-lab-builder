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
    CSV with columns: Database, SizeGb, Shape, RestoreMinutes, ExportMinutes, ArtifactGb
    Produced by instrumenting the drain, or assembled from the drain manifests.

.EXAMPLE
    .\Measure-LtrCalibration.ps1 -TimingCsv .\lab-timings.csv
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $TimingCsv,
    [string] $OutputPath = './calibrated-parameters.json'
)

$ErrorActionPreference = 'Stop'

$rows = Import-Csv $TimingCsv | ForEach-Object {
    [pscustomobject]@{
        Database       = $_.Database
        SizeGb         = [double] $_.SizeGb
        Shape          = $_.Shape
        RestoreMinutes = [double] $_.RestoreMinutes
        ExportMinutes  = [double] $_.ExportMinutes
        ArtifactGb     = [double] $_.ArtifactGb
    }
}

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

$restoreFit = Get-LinearFit -X $sizes -Y $restores
$exportFit  = Get-LinearFit -X $sizes -Y $exports

Write-Host ''
Write-Host 'Timing fit (minutes = intercept + slope * SizeGb)' -ForegroundColor Cyan
Write-Host ('=' * 62) -ForegroundColor DarkGray
[pscustomobject]@{
    Measurement = 'Restore'
    FixedMin    = $restoreFit.Intercept
    MinPerGb    = $restoreFit.Slope
    RSquared    = $restoreFit.RSquared
}, [pscustomobject]@{
    Measurement = 'Export'
    FixedMin    = $exportFit.Intercept
    MinPerGb    = $exportFit.Slope
    RSquared    = $exportFit.RSquared
} | Format-Table -AutoSize | Out-String -Width 100 | Write-Host

foreach ($fit in @(@{N='Restore';F=$restoreFit}, @{N='Export';F=$exportFit})) {
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

$calibrated = [pscustomobject]@{
    GeneratedUtc      = (Get-Date).ToUniversalTime().ToString('o')
    Source            = (Resolve-Path $TimingCsv).Path
    RestoreFixedMin   = $restoreFit.Intercept
    RestoreMinPerGb   = $restoreFit.Slope
    RestoreRSquared   = $restoreFit.RSquared
    ExportFixedMin    = $exportFit.Intercept
    ExportMinPerGb    = $exportFit.Slope
    ExportRSquared    = $exportFit.RSquared
    CompressionWorst  = $worst
    CompressionBest   = $best
    SizesTestedGb     = @($calib.SizeGb)
}
$calibrated | ConvertTo-Json -Depth 4 | Set-Content $OutputPath

Write-Host ''
Write-Host "Calibrated parameters written to $OutputPath" -ForegroundColor Green
Write-Host 'Feed them into the estimator:' -ForegroundColor Green
Write-Host ''
Write-Host "  .\Get-LtrExportCostEstimate.ps1 -BackupCount <n> -AvgDatabaseGb <gb> ``" -ForegroundColor Cyan
Write-Host "      -RestoreFixedMin $($restoreFit.Intercept) -RestoreMinPerGb $($restoreFit.Slope) ``" -ForegroundColor Cyan
Write-Host "      -ExportFixedMin $($exportFit.Intercept) -ExportMinPerGb $($exportFit.Slope) ``" -ForegroundColor Cyan
Write-Host "      -BacpacCompression $worst" -ForegroundColor Cyan
Write-Host ''

$calibrated
