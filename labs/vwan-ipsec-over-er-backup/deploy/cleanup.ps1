#Requires -Version 7.0
[CmdletBinding()]
param([switch]$Confirmed)

if (-not $Confirmed) {
    Write-Output 'Cleanup is separately approval-gated. Re-run with -Confirmed only after explicit approval.'
    exit 2
}
throw 'Cleanup execution intentionally remains disabled until the separately gated cleanup run is authorized.'
