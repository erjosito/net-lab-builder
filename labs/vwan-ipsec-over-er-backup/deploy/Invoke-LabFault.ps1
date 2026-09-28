#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('single-msee-primary','single-msee-secondary','full-er','gcp-vxc','ipsec-pri0','ipsec-private','bgp-pri0','bgp-private','partial-workload-plane-drop','internet')]
    [string]$Fault,

    [Parameter(Mandatory)]
    [ValidateSet('Fault','Restore')]
    [string]$Operation,

    [Parameter(Mandatory)] [string]$InventoryPath,
    [Parameter()] [string]$TerraformDirectory = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\src\terraform\vwan-ipsec-over-er-backup')).Path,
    [Parameter()] [string]$TerraformVarFile = (Join-Path $PSScriptRoot '.runtime.auto.tfvars.json')
)

$ErrorActionPreference = 'Stop'
$inventory = Get-Content (Resolve-Path $InventoryPath) -Raw | ConvertFrom-Json
$isFault = $Operation -eq 'Fault'

function Invoke-CpeAction {
    param([string]$Action)
    gcloud compute ssh $inventory.gcp.cpeVmName --project $inventory.gcp.projectId --zone $inventory.gcp.zone `
        --tunnel-through-iap --quiet --command "sudo /opt/vwan-lab/fault-control.sh $Action"
    if ($LASTEXITCODE -ne 0) { throw "CPE operation failed: $Action" }
}

function Set-VxcState {
    param([bool]$Primary, [bool]$Secondary, [bool]$Gcp)
    foreach ($name in 'MEGAPORT_ACCESS_KEY','MEGAPORT_SECRET_KEY') {
        if (-not [Environment]::GetEnvironmentVariable($name, 'Process')) {
            $value = [Environment]::GetEnvironmentVariable($name, 'User')
            if ($value) { [Environment]::SetEnvironmentVariable($name, $value, 'Process') }
        }
    }
    $env:TF_VAR_megaport_access_key = $env:MEGAPORT_ACCESS_KEY
    $env:TF_VAR_megaport_secret_key = $env:MEGAPORT_SECRET_KEY
    $env:GOOGLE_OAUTH_ACCESS_TOKEN = (gcloud auth print-access-token).Trim()
    if (-not $env:GOOGLE_OAUTH_ACCESS_TOKEN) {
        throw 'Unable to acquire a GCP access token for the fault-state Terraform apply.'
    }
    Push-Location $TerraformDirectory
    try {
        terraform apply -input=false -auto-approve "-var-file=$TerraformVarFile" `
            -var deploy_megaport=true `
            -var "megaport_azure_primary_shutdown=$($Primary.ToString().ToLowerInvariant())" `
            -var "megaport_azure_secondary_shutdown=$($Secondary.ToString().ToLowerInvariant())" `
            -var "megaport_gcp_shutdown=$($Gcp.ToString().ToLowerInvariant())"
        if ($LASTEXITCODE -ne 0) { throw 'Megaport VXC state apply failed.' }
    } finally {
        Pop-Location
    }
}

switch ($Fault) {
    'single-msee-primary' { Set-VxcState -Primary:$isFault -Secondary:$false -Gcp:$false }
    'single-msee-secondary' { Set-VxcState -Primary:$false -Secondary:$isFault -Gcp:$false }
    'full-er' { Set-VxcState -Primary:$isFault -Secondary:$isFault -Gcp:$false }
    'gcp-vxc' { Set-VxcState -Primary:$false -Secondary:$false -Gcp:$isFault }
    'ipsec-pri0' { Invoke-CpeAction $(if ($isFault) { 'stop-pri0' } else { 'restore' }) }
    'ipsec-private' { Invoke-CpeAction $(if ($isFault) { 'stop-private' } else { 'restore' }) }
    'bgp-pri0' { Invoke-CpeAction $(if ($isFault) { 'stop-bgp-pri0' } else { 'restore-bgp-pri0' }) }
    'bgp-private' { Invoke-CpeAction $(if ($isFault) { 'stop-bgp-private' } else { 'restore-bgp-private' }) }
    'partial-workload-plane-drop' { Invoke-CpeAction $(if ($isFault) { 'drop-workload' } else { 'restore-workload' }) }
    'internet' { Invoke-CpeAction $(if ($isFault) { 'block-public' } else { 'restore-public' }) }
}

Write-Output "FAULT_OPERATION=$Fault/$Operation"
