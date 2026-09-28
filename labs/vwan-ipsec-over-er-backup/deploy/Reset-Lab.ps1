#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$Project,
    [Parameter(Mandatory)] [string]$Zone,
    [Parameter(Mandatory)] [string]$CpeName
)

$ErrorActionPreference = 'Stop'
gcloud compute ssh $CpeName --project $Project --zone $Zone --tunnel-through-iap --command `
    "sudo /opt/vwan-lab/fault-control.sh restore; sudo ip xfrm state flush; sudo ip xfrm policy flush; sudo systemctl restart strongswan frr; sudo swanctl --load-all; sudo vtysh -c 'show bgp summary'; sudo swanctl --list-sas"
if ($LASTEXITCODE -ne 0) { throw 'CPE reset failed.' }
