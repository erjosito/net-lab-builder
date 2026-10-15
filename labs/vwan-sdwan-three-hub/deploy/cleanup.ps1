#Requires -Version 7.0
[CmdletBinding()]
param([switch]$Confirmed, [string]$LeaseFile = "$PSScriptRoot\.runtime-control\lease.json")
$ErrorActionPreference = 'Stop'
$arguments = @("$PSScriptRoot\control.py", 'cleanup', '--lease-file', $LeaseFile)
if ($Confirmed) { $arguments += '--confirmed' }
python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Cleanup did not complete; inspect lease and scoped inventory.' }
