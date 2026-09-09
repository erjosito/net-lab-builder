<#
.SYNOPSIS
    Polls until LTR backups appear for the lab databases.

.DESCRIPTION
    PHASE 2 of the lab, and the one that cannot be rushed. Microsoft controls LTR backup
    timing; the documentation states it may take up to seven days after a policy is first
    configured before a backup appears. Enabling a policy for the first time copies the
    most recent PITR full backup into long-term storage, which usually makes it much
    faster than that, but there is no supported way to force it.

    Run this detached, or on a schedule, and proceed only once every database reports a
    backup. Also confirms the deleted-source enumeration path, which is the mode the real
    drain will run in.

.EXAMPLE
    .\Watch-LtrLabBackups.ps1 -Location eastus -Server ltrlab1234-sql -IntervalMinutes 60
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $Location,
    [Parameter(Mandatory)][string] $Server,
    [int]    $IntervalMinutes = 60,
    [int]    $TimeoutHours    = 192,   # 8 days: the documented worst case plus margin
    [switch] $Once
)

$ErrorActionPreference = 'Stop'
$deadline = (Get-Date).AddHours($TimeoutHours)

do {
    $raw = & az sql db ltr-backup list -l $Location --server $Server --database-state All -o json 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Enumeration failed:`n$raw" }

    $backups = $raw | ConvertFrom-Json
    $stamp   = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

    if (-not $backups -or $backups.Count -eq 0) {
        Write-Host "[$stamp] no LTR backups yet for $Server" -ForegroundColor DarkGray
    }
    else {
        Write-Host "[$stamp] $($backups.Count) LTR backup(s) present:" -ForegroundColor Green
        $backups |
            Select-Object databaseName, backupTime, backupExpirationTime, backupStorageRedundancy |
            Sort-Object databaseName |
            Format-Table -AutoSize | Out-String -Width 140 | Write-Host

        $distinct = ($backups | Select-Object -ExpandProperty databaseName -Unique).Count
        Write-Host "$distinct distinct database(s) covered." -ForegroundColor Cyan
    }

    if ($Once) { break }
    if ((Get-Date) -gt $deadline) { throw "Timed out after $TimeoutHours hours with no LTR backups." }
    if (-not $backups -or $backups.Count -eq 0) { Start-Sleep -Seconds ($IntervalMinutes * 60) }
}
while (-not $backups -or $backups.Count -eq 0)

Write-Host ''
Write-Host 'LTR backups are available. Next steps:' -ForegroundColor Green
Write-Host '  1. Delete the source databases (and optionally the server) to prove survival.' -ForegroundColor Cyan
Write-Host '  2. Re-run this script: the backups must still be listed.' -ForegroundColor Cyan
Write-Host '  3. Run the drain, then Measure-LtrCalibration.ps1.' -ForegroundColor Cyan
