#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$ResourceGroup,
    [Parameter(Mandatory)] [string]$VpnGatewayName,
    [Parameter(Mandatory)] [string]$PublicCpeIp,
    [Parameter(Mandatory)] [string]$OutputDirectory,
    [Parameter()] [ValidateSet('D1','D2','D3')] [string]$Design = 'D2'
)

$ErrorActionPreference = 'Stop'

function New-SecurePsk {
    $bytes = [byte[]]::new(32)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
}

function Set-ConnectionPsk {
    param(
        [Parameter(Mandatory)] [string]$ConnectionName,
        [Parameter(Mandatory)] [string]$Psk
    )

    $connection = az network vpn-gateway connection show -g $ResourceGroup --gateway-name $VpnGatewayName `
        -n $ConnectionName -o json | ConvertFrom-Json
    if (-not $connection.id -or @($connection.vpnLinkConnections).Count -ne 1) {
        throw "Expected one site-link connection on $ConnectionName."
    }
    $link = $connection.vpnLinkConnections[0]
    $bodyPath = Join-Path $env:TEMP "$ConnectionName-psk-$([guid]::NewGuid().ToString('N')).json"
    try {
        [ordered]@{
            properties = [ordered]@{
                enableInternetSecurity = $false
                remoteVpnSite = [ordered]@{ id = $connection.remoteVpnSite.id }
                vpnLinkConnections = @(
                    [ordered]@{
                        name = $link.name
                        properties = [ordered]@{
                            connectionBandwidth = $link.connectionBandwidth
                            enableBgp = $link.enableBgp
                            enableRateLimiting = $false
                            routingWeight = $link.routingWeight
                            sharedKey = $Psk
                            useLocalAzureIpAddress = $link.useLocalAzureIpAddress
                            usePolicyBasedTrafficSelectors = $false
                            vpnConnectionProtocolType = 'IKEv2'
                            vpnLinkConnectionMode = 'Default'
                            vpnSiteLink = [ordered]@{ id = $link.vpnSiteLink.id }
                            vpnGatewayCustomBgpAddresses = @($link.vpnGatewayCustomBgpAddresses)
                        }
                    }
                )
            }
        } | ConvertTo-Json -Depth 12 | Set-Content $bodyPath -Encoding utf8

        az rest --method put --url "https://management.azure.com$($connection.id)?api-version=2025-09-01" `
            --body "@$bodyPath" --only-show-errors -o none
        if ($LASTEXITCODE -ne 0) { throw "Failed to apply runtime PSK to $ConnectionName." }
    }
    finally {
        Remove-Item $bodyPath -Force -ErrorAction SilentlyContinue
    }
}

$privatePsk = New-SecurePsk
$publicPsk = New-SecurePsk
Set-ConnectionPsk -ConnectionName 'conn-gcp-er' -Psk $privatePsk
Set-ConnectionPsk -ConnectionName 'conn-gcp-inet' -Psk $publicPsk

$privateConnection = az network vpn-gateway connection show -g $ResourceGroup --gateway-name $VpnGatewayName `
    -n conn-gcp-er -o json | ConvertFrom-Json
$publicConnection = az network vpn-gateway connection show -g $ResourceGroup --gateway-name $VpnGatewayName `
    -n conn-gcp-inet -o json | ConvertFrom-Json
$privateBgpPeers = @($privateConnection.vpnLinkConnections[0].vpnGatewayCustomBgpAddresses | Sort-Object ipConfigurationId | ForEach-Object { $_.customBgpIpAddress })
$publicBgpPeers = @($publicConnection.vpnLinkConnections[0].vpnGatewayCustomBgpAddresses | Sort-Object ipConfigurationId | ForEach-Object { $_.customBgpIpAddress })
if ($privateBgpPeers.Count -ne 2 -or $publicBgpPeers.Count -ne 2) {
    throw 'Each VPN connection must select two distinct Azure custom BGP addresses.'
}

$vpnGateway = az network vpn-gateway show -g $ResourceGroup -n $VpnGatewayName -o json | ConvertFrom-Json
$instances = @{}
foreach ($address in $vpnGateway.bgpSettings.bgpPeeringAddresses) {
    $instances[$address.ipconfigurationId] = $address
}
$instance0 = $instances.Instance0
$instance1 = $instances.Instance1
if (-not $instance0 -or -not $instance1) { throw 'VPN gateway active-active endpoint data is incomplete.' }

$private0 = @($instance0.tunnelIpAddresses | Where-Object { $_ -match '^10\.' })[0]
$private1 = @($instance1.tunnelIpAddresses | Where-Object { $_ -match '^10\.' })[0]
$public0 = @($instance0.tunnelIpAddresses | Where-Object { $_ -notmatch '^10\.' })[0]
$public1 = @($instance1.tunnelIpAddresses | Where-Object { $_ -notmatch '^10\.' })[0]

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$runtimePath = Join-Path $OutputDirectory '.runtime.env'
$runtimeContent = @"
DESIGN=$Design
D1_PHASE=private
PRI0_IKE=$private0
PRI1_IKE=$private1
PUB0_IKE=$public0
PUB1_IKE=$public1
PRI0_BGP=$($privateBgpPeers[0])
PRI1_BGP=$($privateBgpPeers[1])
PUB0_BGP=$($publicBgpPeers[0])
PUB1_BGP=$($publicBgpPeers[1])
PUBLIC_CPE_IP=$PublicCpeIp
PRIVATE_PSK=$privatePsk
PUBLIC_PSK=$publicPsk
"@
[System.IO.File]::WriteAllText(
    $runtimePath,
    ($runtimeContent -replace "`r?`n", "`n"),
    [System.Text.UTF8Encoding]::new($false)
)

[ordered]@{
    design = $Design
    privateConnection = 'conn-gcp-er'
    publicConnection = 'conn-gcp-inet'
    privateIkeEndpoints = @($private0, $private1)
    publicIkeEndpoints = @($public0, $public1)
    privateBgpPeers = $privateBgpPeers
    publicBgpPeers = $publicBgpPeers
    pskStorage = 'runtime-only; omitted'
} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $OutputDirectory 'vpn-generated-values-sanitized.json') -Encoding utf8

Write-Output "VPN_RUNTIME_CONFIG_READY=true"
Write-Output "VPN_RUNTIME_ENV=$runtimePath"
