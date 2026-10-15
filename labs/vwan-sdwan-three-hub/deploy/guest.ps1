#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('stage', 'activate', 'smoke', 'restore')]
    [string]$Phase,
    [string]$LeaseFile = "$PSScriptRoot\.runtime-control\guest-routing-lease.json",
    [switch]$Outputs,
    [string[]]$Names
)
$ErrorActionPreference = 'Stop'
$arguments = @("$PSScriptRoot\guest.py", $Phase, '--lease-file', $LeaseFile)
if ($Outputs) { $arguments += '--outputs' }
if ($Names) { $arguments += '--names'; $arguments += $Names }
python @arguments
if ($LASTEXITCODE -ne 0) { throw "Guest phase $Phase failed; preserve the lease and bounded restore." }
if (-not $Outputs) {
    python "$PSScriptRoot\control.py" wait --deployments "threehub-guest-$Phase" --lease-file $LeaseFile
    if ($LASTEXITCODE -ne 0) { throw "Guest acceptance failed; use only the authorized restore." }
}
