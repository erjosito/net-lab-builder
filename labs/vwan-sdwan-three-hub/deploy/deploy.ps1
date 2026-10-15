#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('preflight', 'base', 'compute', 'checkpoint', 'connections', 'vpn-gateway', 'gateway-update', 'bindings', 'vpn-bindings', 'wait', 'recovery-checkpoint', 'gateway-checkpoint')]
    [string]$Phase,
    [string]$LeaseFile = "$PSScriptRoot\.runtime-control\lease.json"
)
$ErrorActionPreference = 'Stop'
python "$PSScriptRoot\control.py" $Phase --lease-file $LeaseFile
if ($LASTEXITCODE -ne 0) { throw "Infrastructure phase $Phase failed; lease must remain blocked." }
