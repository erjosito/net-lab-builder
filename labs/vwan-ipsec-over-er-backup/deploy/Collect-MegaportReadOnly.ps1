#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$OutputPath,
    [Parameter()] [string]$InventoryPath = (Join-Path (Split-Path -Parent $PSScriptRoot) 'config\inventory.json'),
    [Parameter(Mandatory)] [switch]$ReadOnly
)

$ErrorActionPreference = 'Stop'
if (-not $ReadOnly) {
    throw 'This collector only supports -ReadOnly.'
}

$inventory = Get-Content (Resolve-Path $InventoryPath) -Raw | ConvertFrom-Json
$uids = [ordered]@{
    mcr = $inventory.megaport.mcrUid
    azurePrimary = $inventory.megaport.vxcUids.azurePrimary
    azureSecondary = $inventory.megaport.vxcUids.azureSecondary
    gcp = $inventory.megaport.vxcUids.gcp
}

if (-not ($uids.Values | Where-Object { $_ })) {
    [ordered]@{
        utc = (Get-Date).ToUniversalTime().ToString('o')
        status = 'not-deployed'
        products = [ordered]@{}
        lookingGlass = @{ status = 'not-requested'; reason = 'MCR UID is unavailable.' }
    } | ConvertTo-Json -Depth 8 | Set-Content -Path $OutputPath -Encoding utf8
    return
}

$accessKey = if ($env:MEGAPORT_ACCESS_KEY) { $env:MEGAPORT_ACCESS_KEY } else {
    [Environment]::GetEnvironmentVariable('MEGAPORT_ACCESS_KEY', 'User')
}
$secretKey = if ($env:MEGAPORT_SECRET_KEY) { $env:MEGAPORT_SECRET_KEY } else {
    [Environment]::GetEnvironmentVariable('MEGAPORT_SECRET_KEY', 'User')
}
if (-not $accessKey -or -not $secretKey) {
    throw 'Megaport M2M credentials are unavailable through the approved environment path.'
}

$basic = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${accessKey}:${secretKey}"))
$tokenResponse = Invoke-RestMethod -Method Post -Uri 'https://auth-m2m.megaport.com/oauth2/token' `
    -Headers @{ Authorization = "Basic $basic" } `
    -ContentType 'application/x-www-form-urlencoded' `
    -Body 'grant_type=client_credentials'
$headers = @{ Authorization = "Bearer $($tokenResponse.access_token)" }

function Get-ProductSummary {
    param([string]$Uid)
    $response = Invoke-RestMethod -Method Get -Uri "https://api.megaport.com/v2/product/$Uid" -Headers $headers
    $data = $response.data
    $bgp = @()
    foreach ($connection in @($data.resources.csp_connection)) {
        foreach ($interface in @($connection.interfaces)) {
            foreach ($session in @($interface.bgpConnections)) {
                $status = $connection.bgp_status.($session.peerIpAddress)
                $bgp += [ordered]@{
                    connectType = $connection.connectType
                    localAsn = $session.localAsn
                    localIpAddress = $session.localIpAddress
                    peerAsn = $session.peerAsn
                    peerIpAddress = $session.peerIpAddress
                    peerType = $session.peerType
                    shutdown = $session.shutdown
                    status = $status
                }
            }
        }
    }
    $pathSelections = @(
        $data.resources.csp_connection |
            ForEach-Object { $_.megaports } |
            Where-Object { $_ } |
            ForEach-Object { $_.type }
    )
    return [ordered]@{
        productName = $data.productName
        productType = $data.productType
        provisioningStatus = $data.provisioningStatus
        up = $data.up
        shutdown = $data.shutdown
        rateLimit = $data.rateLimit
        portSpeed = $data.portSpeed
        location = $data.locationDetail.name
        aEnd = [ordered]@{
            productName = $data.aEnd.productName
            location = $data.aEnd.location
            diversityZone = $data.aEnd.diversityZone
        }
        bEnd = [ordered]@{
            productName = $data.bEnd.productName
            location = $data.bEnd.location
            connectType = $data.bEnd.connectType
            diversityZone = $data.bEnd.diversityZone
        }
        pathSelections = $pathSelections
        bgpConnections = $bgp
    }
}

$products = [ordered]@{}
foreach ($entry in $uids.GetEnumerator()) {
    if ($entry.Value) {
        $products[$entry.Key] = Get-ProductSummary -Uid ([string]$entry.Value)
    }
}

$lookingGlass = [ordered]@{ status = 'not-requested'; routes = @() }
if ($uids.mcr) {
    try {
        $routes = Invoke-RestMethod -Method Get `
            -Uri "https://api.megaport.com/v2/product/mcr2/$($uids.mcr)/diagnostics/routes/bgp" `
            -Headers $headers
        $lookingGlass = [ordered]@{ status = 'available'; routes = @($routes.data) }
    } catch {
        $lookingGlass = [ordered]@{
            status = 'unavailable'
            reason = 'Megaport looking-glass endpoint did not return a usable route table; use VXC BGP state and adjacent provider tables.'
        }
    }
}

[ordered]@{
    utc = (Get-Date).ToUniversalTime().ToString('o')
    status = 'collected'
    products = $products
    lookingGlass = $lookingGlass
} | ConvertTo-Json -Depth 15 | Set-Content -Path $OutputPath -Encoding utf8
