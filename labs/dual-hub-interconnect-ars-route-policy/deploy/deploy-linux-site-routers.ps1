[CmdletBinding()]
param(
    [string]$ResourceGroup = 'rg-dual-hub-hubless-region-ars-lab3d001',
    [string]$AdminUsername = 'labadmin',
    [string]$VmSize = 'Standard_B2ts_v2'
)

$ErrorActionPreference = 'Stop'
$template = Join-Path $PSScriptRoot 'linux-site-routers.bicep'
$sshPublicKey = (Get-Content "$HOME\.ssh\id_rsa.pub" -Raw).Trim()

function Invoke-Az {
    param([Parameter(Mandatory)][string[]]$Arguments)

    & az @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI failed: az $($Arguments -join ' ')"
    }
}

function New-RandomPsk {
    $bytes = [byte[]]::new(32)
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return [Convert]::ToHexString($bytes)
}

function Wait-Ssh {
    param([Parameter(Mandatory)][string]$Address)

    $deadline = (Get-Date).AddMinutes(10)
    do {
        & ssh -p 2222 -o BatchMode=yes -o ConnectTimeout=10 `
            -o StrictHostKeyChecking=accept-new "$AdminUsername@$Address" 'cloud-init status --wait' 2>$null
        if ($LASTEXITCODE -eq 0) {
            return
        }
        Start-Sleep -Seconds 15
    } while ((Get-Date) -lt $deadline)

    throw "SSH did not become ready on $Address."
}

function Send-RemoteText {
    param(
        [Parameter(Mandatory)][string]$Address,
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Content
    )

    $normalizedContent = $Content -replace "`r`n", "`n"
    $normalizedContent | & ssh -p 2222 -o BatchMode=yes -o StrictHostKeyChecking=accept-new `
        "$AdminUsername@$Address" "sudo tee '$Path' >/dev/null && sudo sed -i 's/\r$//' '$Path'"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to write $Path on $Address."
    }
}

function Invoke-Remote {
    param(
        [Parameter(Mandatory)][string]$Address,
        [Parameter(Mandatory)][string]$Command
    )

    $normalizedCommand = $Command -replace "`r`n", "`n"
    & ssh -p 2222 -o BatchMode=yes -o StrictHostKeyChecking=accept-new `
        "$AdminUsername@$Address" $normalizedCommand
    if ($LASTEXITCODE -ne 0) {
        throw "Remote command failed on $Address."
    }
}

function Get-HubGateway {
    param([Parameter(Mandatory)][string]$Name)

    $gateway = Invoke-Az -Arguments @(
        'network', 'vnet-gateway', 'show',
        '-g', $ResourceGroup,
        '-n', $Name,
        '-o', 'json'
    ) | ConvertFrom-Json

    return @{
        asn = [int]$gateway.bgpSettings.asn
        tunnelIps = @($gateway.bgpSettings.bgpPeeringAddresses | ForEach-Object {
            $_.tunnelIpAddresses[0]
        })
        bgpIps = @($gateway.bgpSettings.bgpPeeringAddresses | ForEach-Object {
            $_.defaultBgpIpAddresses[0]
        })
    }
}

function Set-ConnectionOutboundRouteMap {
    param(
        [Parameter(Mandatory)][string]$ConnectionName,
        [Parameter(Mandatory)][string]$RouteMapId
    )

    $subscriptionId = Invoke-Az -Arguments @(
        'account', 'show', '--query', 'id', '-o', 'tsv'
    )
    $url = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/" +
        "$ResourceGroup/providers/Microsoft.Network/connections/" +
        "${ConnectionName}?api-version=2024-10-01"
    $current = Invoke-Az -Arguments @(
        'rest', '--method', 'get', '--url', $url, '-o', 'json'
    ) | ConvertFrom-Json

    foreach ($property in @(
        'connectionStatus',
        'egressBytesTransferred',
        'ingressBytesTransferred',
        'packetCaptureDiagnosticState',
        'provisioningState',
        'resourceGuid',
        'tunnelConnectionStatus'
    )) {
        $current.properties.PSObject.Properties.Remove($property)
    }
    $current.properties.routingConfiguration = [pscustomobject]@{
        outboundRouteMap = [pscustomobject]@{ id = $RouteMapId }
    }

    $bodyPath = Join-Path $env:TEMP "$ConnectionName-route-map-$([guid]::NewGuid()).json"
    try {
        [ordered]@{
            location = $current.location
            tags = $current.tags
            properties = $current.properties
        } | ConvertTo-Json -Depth 30 | Set-Content -Path $bodyPath -Encoding utf8

        Invoke-Az -Arguments @(
            'rest', '--method', 'put', '--url', $url,
            '--headers', 'Content-Type=application/json',
            '--body', "@$bodyPath", '-o', 'none'
        )
    }
    finally {
        if (Test-Path $bodyPath) {
            Remove-Item $bodyPath -Force
        }
    }
}

function New-XfrmScript {
    param(
        [Parameter(Mandatory)][hashtable]$Hub,
        [Parameter(Mandatory)][string]$PeerPublicIp,
        [Parameter(Mandatory)][string]$PeerPrivateIp,
        [Parameter(Mandatory)][string]$DefaultGateway,
        [Parameter(Mandatory)][string]$LocalPrefix,
        [Parameter(Mandatory)][string]$LocalPrivateIp
    )

    return @"
#!/bin/bash
set -e
for iface in ipsec0 ipsec1 ipsec2; do
  ip link del "`$iface" 2>/dev/null || true
done
ip link add ipsec0 type xfrm dev eth0 if_id 41
ip link add ipsec1 type xfrm dev eth0 if_id 42
ip link add ipsec2 type xfrm dev eth0 if_id 43
ip link set ipsec0 up
ip link set ipsec1 up
ip link set ipsec2 up
ip route replace $($Hub.bgpIps[0])/32 dev ipsec0
ip route replace $($Hub.bgpIps[1])/32 dev ipsec1
ip route replace $PeerPrivateIp/32 dev ipsec2
ip route replace $($Hub.tunnelIps[0])/32 via $DefaultGateway
ip route replace $($Hub.tunnelIps[1])/32 via $DefaultGateway
ip route replace $PeerPublicIp/32 via $DefaultGateway
ip route replace throw $($Hub.tunnelIps[0])/32 table 220
ip route replace throw $($Hub.tunnelIps[1])/32 table 220
ip route replace throw $PeerPublicIp/32 table 220
iptables -t nat -D POSTROUTING -o eth0 ! -s $LocalPrefix -d $LocalPrefix -j SNAT --to-source $LocalPrivateIp 2>/dev/null || true
iptables -t nat -A POSTROUTING -o eth0 ! -s $LocalPrefix -d $LocalPrefix -j SNAT --to-source $LocalPrivateIp
"@
}

function New-SwanConfig {
    param(
        [Parameter(Mandatory)][string]$LocalPrivateIp,
        [Parameter(Mandatory)][string]$LocalPublicIp,
        [Parameter(Mandatory)][hashtable]$Hub,
        [Parameter(Mandatory)][string]$PeerPublicIp,
        [Parameter(Mandatory)][string]$HubPsk,
        [Parameter(Mandatory)][string]$DciPsk
    )

    return @"
connections {
  hub0 {
    local_addrs = $LocalPrivateIp
    remote_addrs = $($Hub.tunnelIps[0])
    version = 2
    proposals = aes256-sha1-modp1024,aes192-sha256-modp3072,default
    keyingtries = 0
    encap = yes
    local {
      auth = psk
      id = $LocalPublicIp
    }
    remote {
      auth = psk
      id = $($Hub.tunnelIps[0])
      revocation = relaxed
    }
    children {
      hub0-child {
        local_ts = 0.0.0.0/0
        remote_ts = 0.0.0.0/0
        esp_proposals = aes256-sha1,default
        dpd_action = restart
        start_action = trap
        rekey_time = 3600
      }
    }
    if_id_in = 41
    if_id_out = 41
  }
  hub1 {
    local_addrs = $LocalPrivateIp
    remote_addrs = $($Hub.tunnelIps[1])
    version = 2
    proposals = aes256-sha1-modp1024,aes192-sha256-modp3072,default
    keyingtries = 0
    encap = yes
    local {
      auth = psk
      id = $LocalPublicIp
    }
    remote {
      auth = psk
      id = $($Hub.tunnelIps[1])
      revocation = relaxed
    }
    children {
      hub1-child {
        local_ts = 0.0.0.0/0
        remote_ts = 0.0.0.0/0
        esp_proposals = aes256-sha1,default
        dpd_action = restart
        start_action = trap
        rekey_time = 3600
      }
    }
    if_id_in = 42
    if_id_out = 42
  }
  dci {
    local_addrs = $LocalPrivateIp
    remote_addrs = $PeerPublicIp
    version = 2
    proposals = aes256-sha256-modp2048,default
    keyingtries = 0
    encap = yes
    local {
      auth = psk
      id = $LocalPublicIp
    }
    remote {
      auth = psk
      id = $PeerPublicIp
      revocation = relaxed
    }
    children {
      dci-child {
        local_ts = 0.0.0.0/0
        remote_ts = 0.0.0.0/0
        esp_proposals = aes256-sha256,default
        dpd_action = restart
        start_action = start
        rekey_time = 3600
      }
    }
    if_id_in = 43
    if_id_out = 43
  }
}
secrets {
  ike-hub {
    id-0 = $($Hub.tunnelIps[0])
    id-1 = $($Hub.tunnelIps[1])
    secret = "$HubPsk"
  }
  ike-dci {
    id-0 = $PeerPublicIp
    secret = "$DciPsk"
  }
}
"@
}

function New-BirdConfig {
    param(
        [Parameter(Mandatory)][string]$LocalPrivateIp,
        [Parameter(Mandatory)][int]$LocalAsn,
        [Parameter(Mandatory)][string]$LocalPrefix,
        [Parameter(Mandatory)][string]$DefaultGateway,
        [Parameter(Mandatory)][hashtable]$Hub,
        [Parameter(Mandatory)][string]$PeerPrivateIp,
        [Parameter(Mandatory)][int]$PeerAsn
    )

    return @"
log syslog all;
router id $LocalPrivateIp;

protocol device {
  scan time 10;
}

protocol kernel kernel4 {
  learn;
  merge paths on;
  ipv4 {
    import all;
    export all;
  };
}

protocol static site_prefix {
  ipv4;
  route $LocalPrefix via $DefaultGateway;
}

filter export_to_hub {
  if source = RTS_STATIC then accept;
  if proto = "dci" then accept;
  reject;
}

filter export_to_dci {
  if source = RTS_STATIC then accept;
  if proto = "hub0" then accept;
  if proto = "hub1" then accept;
  reject;
}

protocol bgp hub0 {
  local $LocalPrivateIp as $LocalAsn;
  neighbor $($Hub.bgpIps[0]) as $($Hub.asn);
  multihop;
  ipv4 {
    import all;
    export filter export_to_hub;
  };
}

protocol bgp hub1 {
  local $LocalPrivateIp as $LocalAsn;
  neighbor $($Hub.bgpIps[1]) as $($Hub.asn);
  multihop;
  ipv4 {
    import all;
    export filter export_to_hub;
  };
}

protocol bgp dci {
  local $LocalPrivateIp as $LocalAsn;
  neighbor $PeerPrivateIp as $PeerAsn;
  multihop;
  ipv4 {
    import all;
    export filter export_to_dci;
  };
}
"@
}

function Configure-Router {
    param(
        [Parameter(Mandatory)][string]$PublicIp,
        [Parameter(Mandatory)][string]$PrivateIp,
        [Parameter(Mandatory)][int]$Asn,
        [Parameter(Mandatory)][string]$Prefix,
        [Parameter(Mandatory)][string]$DefaultGateway,
        [Parameter(Mandatory)][hashtable]$Hub,
        [Parameter(Mandatory)][string]$PeerPublicIp,
        [Parameter(Mandatory)][string]$PeerPrivateIp,
        [Parameter(Mandatory)][int]$PeerAsn,
        [Parameter(Mandatory)][string]$HubPsk,
        [Parameter(Mandatory)][string]$DciPsk
    )

    Wait-Ssh -Address $PublicIp
    Send-RemoteText -Address $PublicIp -Path '/usr/local/sbin/configure-xfrm.sh' `
        -Content (New-XfrmScript -Hub $Hub -PeerPublicIp $PeerPublicIp `
            -PeerPrivateIp $PeerPrivateIp -DefaultGateway $DefaultGateway `
            -LocalPrefix $Prefix -LocalPrivateIp $PrivateIp)
    Send-RemoteText -Address $PublicIp -Path '/etc/swanctl/swanctl.conf' `
        -Content (New-SwanConfig -LocalPrivateIp $PrivateIp -LocalPublicIp $PublicIp `
            -Hub $Hub -PeerPublicIp $PeerPublicIp -HubPsk $HubPsk -DciPsk $DciPsk)
    Send-RemoteText -Address $PublicIp -Path '/etc/bird/bird.conf' `
        -Content (New-BirdConfig -LocalPrivateIp $PrivateIp -LocalAsn $Asn `
            -LocalPrefix $Prefix -DefaultGateway $DefaultGateway -Hub $Hub `
            -PeerPrivateIp $PeerPrivateIp -PeerAsn $PeerAsn)

    $unit = @'
[Unit]
Description=Create XFRM interfaces and peer routes
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/configure-xfrm.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
'@
    Send-RemoteText -Address $PublicIp -Path '/etc/systemd/system/xfrm-routes.service' -Content $unit
    $swanctlUnit = @'
[Unit]
Description=Load lab swanctl connections after StrongSwan starts
After=network-online.target xfrm-routes.service strongswan-starter.service
Wants=network-online.target
Requires=xfrm-routes.service strongswan-starter.service

[Service]
Type=oneshot
ExecStart=/usr/sbin/swanctl --load-all
RemainAfterExit=yes
Restart=on-failure
RestartSec=2s

[Install]
WantedBy=multi-user.target
'@
    Send-RemoteText -Address $PublicIp -Path '/etc/systemd/system/lab-swanctl-config.service' `
        -Content $swanctlUnit
    Invoke-Remote -Address $PublicIp -Command @'
sudo chmod 700 /usr/local/sbin/configure-xfrm.sh &&
sudo systemctl daemon-reload &&
sudo systemctl enable --now xfrm-routes.service &&
sudo systemctl enable --now lab-swanctl-config.service &&
sudo systemctl restart bird
'@
}

$hub1Psk = New-RandomPsk
$hub2Psk = New-RandomPsk
$dciPsk = New-RandomPsk
$parametersPath = Join-Path $env:TEMP "linux-site-routers-$([guid]::NewGuid()).parameters.json"

try {
    @{
        '$schema' = 'https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#'
        contentVersion = '1.0.0.0'
        parameters = @{
            adminPublicKey = @{ value = $sshPublicKey }
            adminUsername = @{ value = $AdminUsername }
            vmSize = @{ value = $VmSize }
        }
    } | ConvertTo-Json -Depth 10 | Set-Content -Path $parametersPath -Encoding utf8

    & az vm show -g $ResourceGroup -n 'vm-router-dc1' -o none 2>$null
    $dc1Exists = $LASTEXITCODE -eq 0
    & az vm show -g $ResourceGroup -n 'vm-router-dc2' -o none 2>$null
    $dc2Exists = $LASTEXITCODE -eq 0
    if (-not ($dc1Exists -and $dc2Exists)) {
        Invoke-Az -Arguments @(
            'deployment', 'group', 'create',
            '-g', $ResourceGroup,
            '-n', 'linux-site-routers',
            '--template-file', $template,
            '--parameters', "@$parametersPath",
            '-o', 'none'
        )
    }

    $dc1PublicIp = Invoke-Az -Arguments @(
        'network', 'public-ip', 'show', '-g', $ResourceGroup,
        '-n', 'pip-router-dc1', '--query', 'ipAddress', '-o', 'tsv'
    )
    $dc2PublicIp = Invoke-Az -Arguments @(
        'network', 'public-ip', 'show', '-g', $ResourceGroup,
        '-n', 'pip-router-dc2', '--query', 'ipAddress', '-o', 'tsv'
    )
    $hub1 = Get-HubGateway -Name 'vpngw-hub1'
    $hub2 = Get-HubGateway -Name 'vpngw-hub2'

    Configure-Router -PublicIp $dc1PublicIp -PrivateIp '10.40.2.4' -Asn 65000 `
        -Prefix '10.40.0.0/16' -DefaultGateway '10.40.2.1' -Hub $hub1 `
        -PeerPublicIp $dc2PublicIp -PeerPrivateIp '10.50.2.4' -PeerAsn 65003 `
        -HubPsk $hub1Psk -DciPsk $dciPsk
    Configure-Router -PublicIp $dc2PublicIp -PrivateIp '10.50.2.4' -Asn 65003 `
        -Prefix '10.50.0.0/16' -DefaultGateway '10.50.2.1' -Hub $hub2 `
        -PeerPublicIp $dc1PublicIp -PeerPrivateIp '10.40.2.4' -PeerAsn 65000 `
        -HubPsk $hub2Psk -DciPsk $dciPsk

    foreach ($lng in @(
        @{ name = 'lng-hub1-to-router-dc1'; location = 'swedencentral'; pip = $dc1PublicIp; asn = 65000; bgp = '10.40.2.4' },
        @{ name = 'lng-hub2-to-router-dc2'; location = 'switzerlandnorth'; pip = $dc2PublicIp; asn = 65003; bgp = '10.50.2.4' }
    )) {
        Invoke-Az -Arguments @(
            'network', 'local-gateway', 'create',
            '-g', $ResourceGroup,
            '-n', $lng.name,
            '-l', $lng.location,
            '--gateway-ip-address', $lng.pip,
            '--asn', $lng.asn,
            '--bgp-peering-address', $lng.bgp,
            '--tags', 'lab=true', 'created_by=copilot-lab',
            'run_id=lab3d001', 'scenario=TP-SQ-LINUX-SITES',
            '-o', 'none'
        )
    }

    Invoke-Az -Arguments @(
        'network', 'vpn-connection', 'create',
        '-g', $ResourceGroup,
        '-n', 'conn-hub1-to-router-dc1',
        '-l', 'swedencentral',
        '--vnet-gateway1', 'vpngw-hub1',
        '--local-gateway2', 'lng-hub1-to-router-dc1',
        '--enable-bgp',
        '--shared-key', $hub1Psk,
        '--tags', 'lab=true', 'created_by=copilot-lab',
        'run_id=lab3d001', 'scenario=TP-SQ-LINUX-SITES',
        '-o', 'none'
    )
    Invoke-Az -Arguments @(
        'network', 'vpn-connection', 'create',
        '-g', $ResourceGroup,
        '-n', 'conn-hub2-to-router-dc2',
        '-l', 'switzerlandnorth',
        '--vnet-gateway1', 'vpngw-hub2',
        '--local-gateway2', 'lng-hub2-to-router-dc2',
        '--enable-bgp',
        '--shared-key', $hub2Psk,
        '--tags', 'lab=true', 'created_by=copilot-lab',
        'run_id=lab3d001', 'scenario=TP-SQ-LINUX-SITES',
        '-o', 'none'
    )

    $subscriptionId = Invoke-Az -Arguments @(
        'account', 'show', '--query', 'id', '-o', 'tsv'
    )
    $hub2RouteMapId = "/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/" +
        'providers/Microsoft.Network/virtualHubs/ars-hub2/routeMaps/rm-hub2-activate'
    Set-ConnectionOutboundRouteMap -ConnectionName 'conn-hub2-to-router-dc2' `
        -RouteMapId $hub2RouteMapId

    Invoke-Az -Arguments @(
        'network', 'vnet', 'subnet', 'update',
        '-g', $ResourceGroup,
        '--vnet-name', 'vnet-onprem',
        '-n', 'snet-endpoint',
        '--route-table', 'rt-endpoint-dc1',
        '-o', 'none'
    )
    Invoke-Az -Arguments @(
        'network', 'vnet', 'subnet', 'update',
        '-g', $ResourceGroup,
        '--vnet-name', 'vnet-onprem2',
        '-n', 'snet-endpoint',
        '--route-table', 'rt-endpoint-dc2',
        '-o', 'none'
    )

    Write-Output "Linux site routers deployed: DC1 $dc1PublicIp, DC2 $dc2PublicIp."
}
finally {
    if (Test-Path $parametersPath) {
        Remove-Item $parametersPath -Force
    }
    $hub1Psk = $null
    $hub2Psk = $null
    $dciPsk = $null
    [GC]::Collect()
}
