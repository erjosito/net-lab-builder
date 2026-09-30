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

    $accessKey = if ($env:MEGAPORT_ACCESS_KEY) {
        $env:MEGAPORT_ACCESS_KEY
    } else {
        [Environment]::GetEnvironmentVariable('MEGAPORT_ACCESS_KEY', 'User')
    }
    $secretKey = if ($env:MEGAPORT_SECRET_KEY) {
        $env:MEGAPORT_SECRET_KEY
    } else {
        [Environment]::GetEnvironmentVariable('MEGAPORT_SECRET_KEY', 'User')
    }
    if (-not $accessKey -or -not $secretKey) {
        throw 'Megaport M2M credentials are unavailable through the approved environment path.'
    }

    $basic = [Convert]::ToBase64String(
        [Text.Encoding]::ASCII.GetBytes("${accessKey}:${secretKey}")
    )
    $token = (Invoke-RestMethod -Method Post -Uri 'https://auth-m2m.megaport.com/oauth2/token' `
        -Headers @{ Authorization = "Basic $basic" } `
        -ContentType 'application/x-www-form-urlencoded' `
        -Body 'grant_type=client_credentials').access_token
    if (-not $token) { throw 'Megaport authentication did not return an access token.' }

    $desired = [ordered]@{
        ([string]$inventory.megaport.vxcUids.azurePrimary) = $Primary
        ([string]$inventory.megaport.vxcUids.azureSecondary) = $Secondary
        ([string]$inventory.megaport.vxcUids.gcp) = $Gcp
    }
    foreach ($entry in $desired.GetEnumerator()) {
        $body = "{`"shutdown`":$($entry.Value.ToString().ToLowerInvariant())}"
        $status = & curl.exe --silent --show-error --output NUL --write-out '%{http_code}' `
            --request PUT "https://api.megaport.com/v3/product/vxc/$($entry.Key)/" `
            --header "Authorization: Bearer $token" `
            --header 'Content-Type: application/json' `
            --data $body
        if ($LASTEXITCODE -ne 0 -or $status -notin @('200','202','303')) {
            throw "Megaport VXC update failed for $($entry.Key) (HTTP $status)."
        }
    }

    $deadline = (Get-Date).AddMinutes(10)
    do {
        Start-Sleep -Seconds 15
        $pending = @()
        foreach ($entry in $desired.GetEnumerator()) {
            $product = (Invoke-RestMethod -Method Get `
                -Uri "https://api.megaport.com/v2/product/$($entry.Key)" `
                -Headers @{ Authorization = "Bearer $token" }).data
            if (
                [bool]$product.shutdown -ne $entry.Value -or
                [bool]$product.up -eq $entry.Value
            ) {
                $pending += $product.productName
            }
        }
    } while ($pending.Count -gt 0 -and (Get-Date) -lt $deadline)

    if ($pending.Count -gt 0) {
        throw "Megaport VXC state did not converge: $($pending -join ', ')."
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
