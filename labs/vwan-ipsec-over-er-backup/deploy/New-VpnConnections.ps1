#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$ResourceGroup,
    [Parameter(Mandatory)] [string]$VirtualWanName,
    [Parameter(Mandatory)] [string]$VpnGatewayName,
    [Parameter(Mandatory)] [string]$PublicCpeIp,
    [Parameter()] [ValidateSet('D1','D2','D3')] [string]$Design = 'D2',
    [Parameter()] [switch]$ReplaceExisting
)

$ErrorActionPreference = 'Stop'
$privatePeer = if ($Design -eq 'D1') { '10.250.254.242' } else { '10.250.254.240' }
$publicPeer  = if ($Design -eq 'D1') { '10.250.254.242' } else { '10.250.254.241' }
$privatePrefixes = if ($Design -eq 'D1') { @('10.253.1.0/24') } elseif ($Design -eq 'D3') { @('10.253.3.0/25','10.253.3.128/25') } else { @('10.253.2.0/24') }
$publicPrefixes  = if ($Design -eq 'D1') { @('10.253.1.0/24') } elseif ($Design -eq 'D3') { @('10.253.3.0/24') } else { @('10.253.2.0/24') }
$publicBgp = $Design -ne 'D3'
$tags = @('lab=true','created_by=copilot-lab','lab_name=vwan-ipsec-over-er-backup')

$existingConnections = @(
    az network vpn-gateway connection list -g $ResourceGroup --gateway-name $VpnGatewayName `
        --query "[?name=='conn-gcp-er' || name=='conn-gcp-inet'].name" -o tsv
)
$existingSites = @(
    az network vpn-site list -g $ResourceGroup `
        --query "[?name=='site-gcp-er' || name=='site-gcp-inet'].name" -o tsv
)
if (($existingConnections.Count -gt 0 -or $existingSites.Count -gt 0) -and -not $ReplaceExisting) {
    throw 'Existing lab VPN objects found. Re-run with -ReplaceExisting for an explicit D1/D2/D3 bundle switch.'
}
if ($ReplaceExisting) {
    foreach ($name in $existingConnections) {
        az network vpn-gateway connection delete -g $ResourceGroup --gateway-name $VpnGatewayName `
            -n $name --only-show-errors -o none
        if ($LASTEXITCODE -ne 0) { throw "Failed to delete VPN connection $name" }
    }
    foreach ($name in $existingSites) {
        az network vpn-site delete -g $ResourceGroup -n $name --only-show-errors -o none
        if ($LASTEXITCODE -ne 0) { throw "Failed to delete VPN site $name" }
    }
}

function Ensure-Site {
    param([string]$Name,[string]$Ip,[string]$Peer,[string[]]$Prefixes,[bool]$EnableBgp)
    $existing = az network vpn-site show -g $ResourceGroup -n $Name --query id -o tsv 2>$null
    if (-not $existing) {
        $args = @('network','vpn-site','create','-g',$ResourceGroup,'-n',$Name,'--virtual-wan',$VirtualWanName,'--location','swedencentral','--ip-address',$Ip,'--address-prefixes') + $Prefixes + @('--with-link','true','--link-speed','50','--device-vendor','Linux','--device-model','StrongSwan-FRR','--tags') + $tags
        if ($EnableBgp) { $args += @('--asn','65050','--bgp-peering-address',$Peer) }
        az @args --only-show-errors -o none
        if ($LASTEXITCODE -ne 0) { throw "Failed to create VPN site $Name" }
    }
}

Ensure-Site -Name 'site-gcp-er' -Ip '10.250.0.10' -Peer $privatePeer -Prefixes $privatePrefixes -EnableBgp $true
Ensure-Site -Name 'site-gcp-inet' -Ip $PublicCpeIp -Peer $publicPeer -Prefixes $publicPrefixes -EnableBgp $publicBgp

$privateSite = az network vpn-site show -g $ResourceGroup -n site-gcp-er -o json | ConvertFrom-Json
$publicSite = az network vpn-site show -g $ResourceGroup -n site-gcp-inet -o json | ConvertFrom-Json

function Ensure-Connection {
    param([string]$Name,[object]$Site,[bool]$EnableBgp,[bool]$UsePrivateAzureIp)
    $existing = az network vpn-gateway connection show -g $ResourceGroup --gateway-name $VpnGatewayName -n $Name --query id -o tsv 2>$null
    if ($existing) { return }
    $link = $Site.vpnSiteLinks[0]
    az network vpn-gateway connection create -g $ResourceGroup --gateway-name $VpnGatewayName -n $Name `
        --remote-vpn-site $Site.id --with-link false --enable-bgp $EnableBgp --protocol-type IKEv2 `
        --only-show-errors -o none
    if ($LASTEXITCODE -ne 0) { throw "Failed to create VPN connection $Name" }

    az network vpn-gateway connection vpn-site-link-conn add -g $ResourceGroup --gateway-name $VpnGatewayName `
        --connection-name $Name -n "$Name-link" --vpn-site-link $link.id --enable-bgp $EnableBgp `
        --use-local-azure-ip-address $UsePrivateAzureIp --vpn-connection-protocol-type IKEv2 `
        --connection-bandwidth 50 --only-show-errors -o none
    if ($LASTEXITCODE -ne 0) { throw "Failed to add link connection for $Name" }
}

Ensure-Connection -Name 'conn-gcp-er' -Site $privateSite -EnableBgp $true -UsePrivateAzureIp $true
Ensure-Connection -Name 'conn-gcp-inet' -Site $publicSite -EnableBgp $publicBgp -UsePrivateAzureIp $false

Write-Output "VPN_CONNECTIONS_READY=true"
Write-Output "VPN_DESIGN=$Design"
