#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter()] [string]$OutputPath = (Join-Path (Split-Path -Parent $PSScriptRoot) 'config\inventory.json')
)

$ErrorActionPreference = 'Stop'
$state = Get-Content (Join-Path $PSScriptRoot '.lab-state.json') -Raw | ConvertFrom-Json
$prefix = "ver-$($state.run_id)"
$resourceGroup = "rg-vwan-ipsec-over-er-$($state.run_id)"
$subscription = az account show --query id -o tsv
$vhub = az network vhub show -g $resourceGroup -n "vhub-$prefix" -o json | ConvertFrom-Json
$vpnGateway = az network vpn-gateway show -g $resourceGroup -n "vpngw-$prefix" -o json | ConvertFrom-Json
$erGateway = az network express-route gateway show -g $resourceGroup -n "ergw-$prefix" -o json | ConvertFrom-Json
$workloadVm = az vm show -g $resourceGroup -n "vm-probe-$prefix" -o json | ConvertFrom-Json
$workloadNic = az network nic show -g $resourceGroup -n "nic-probe-$prefix" -o json | ConvertFrom-Json
$privateSite = az network vpn-site show -g $resourceGroup -n site-gcp-er -o json | ConvertFrom-Json
$publicSite = az network vpn-site show -g $resourceGroup -n site-gcp-inet -o json | ConvertFrom-Json
$privateConnection = az network vpn-gateway connection show -g $resourceGroup --gateway-name $vpnGateway.name `
    -n conn-gcp-er -o json | ConvertFrom-Json
$publicConnection = az network vpn-gateway connection show -g $resourceGroup --gateway-name $vpnGateway.name `
    -n conn-gcp-inet -o json | ConvertFrom-Json
$terraformRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\src\terraform\vwan-ipsec-over-er-backup')).Path
$mcrUid = terraform "-chdir=$terraformRoot" output -raw mcr_uid
$vxcUids = terraform "-chdir=$terraformRoot" output -json vxc_uids | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Unable to read non-secret provider identifiers from Terraform output.' }

$instances = @{}
foreach ($address in $vpnGateway.bgpSettings.bgpPeeringAddresses) {
    $instances[$address.ipconfigurationId] = $address
}
$instance0 = $instances.Instance0
$instance1 = $instances.Instance1
$instance0PrivateIke = @($instance0.tunnelIpAddresses | Where-Object { $_ -match '^10\.' })[0]
$instance0PublicIke = @($instance0.tunnelIpAddresses | Where-Object { $_ -notmatch '^10\.' })[0]
$instance1PrivateIke = @($instance1.tunnelIpAddresses | Where-Object { $_ -match '^10\.' })[0]
$instance1PublicIke = @($instance1.tunnelIpAddresses | Where-Object { $_ -notmatch '^10\.' })[0]
$privateCustomPeers = @(
    $privateConnection.vpnLinkConnections[0].vpnGatewayCustomBgpAddresses |
        Sort-Object ipConfigurationId |
        ForEach-Object { $_.customBgpIpAddress }
)
$publicCustomPeers = @(
    $publicConnection.vpnLinkConnections[0].vpnGatewayCustomBgpAddresses |
        Sort-Object ipConfigurationId |
        ForEach-Object { $_.customBgpIpAddress }
)
$privateConnectionId = $privateConnection.id
$publicConnectionId = $publicConnection.id
$expressRouteConnectionId = "$($erGateway.id)/expressRouteConnections/conn-er"
$routeUrl = "https://management.azure.com$($vhub.id)/effectiveRoutes?api-version=2025-09-01"
$collector = (Resolve-Path (Join-Path $PSScriptRoot 'Collect-MegaportReadOnly.ps1')).Path
$faultScript = (Resolve-Path (Join-Path $PSScriptRoot 'Invoke-LabFault.ps1')).Path

$inventory = [ordered]@{
    schemaVersion = 2
    runId = $state.run_id
    deploymentStatus = 'deployed-ipsec-healthy-d2-bgp-blocked'
    blocker = [ordered]@{
        code = 'azure-custom-apipa-requires-apipa-remote-peer'
        detail = 'The site BGP peers are regular private addresses, so Azure uses its two default gateway BGP addresses rather than the four connection-selected custom APIPA addresses.'
        validationAuthorized = $false
    }
    azure = [ordered]@{
        resourceGroup = $resourceGroup
        vhubName = $vhub.name
        vhubRouteTableId = "$($vhub.id)/hubRouteTables/defaultRouteTable"
        vpnGatewayId = $vpnGateway.id
        privateVpnSiteId = $privateSite.id
        publicVpnSiteId = $publicSite.id
        privateVpnConnectionId = $privateConnectionId
        publicVpnConnectionId = $publicConnectionId
        expressRouteGatewayId = $erGateway.id
        expressRouteConnectionId = $expressRouteConnectionId
        expressRouteCircuitName = "er-$prefix"
        expressRoutePeeringName = 'AzurePrivatePeering'
        workloadVmName = $workloadVm.name
        workloadNicName = $workloadNic.name
        routeQueries = @(
            [ordered]@{ name='vpn-private-routes'; method='POST'; url=$routeUrl; body=[ordered]@{ resourceId=$privateConnectionId; virtualWanResourceType='VpnConnection' } },
            [ordered]@{ name='vpn-public-routes'; method='POST'; url=$routeUrl; body=[ordered]@{ resourceId=$publicConnectionId; virtualWanResourceType='VpnConnection' } },
            [ordered]@{ name='er-connection-routes'; method='POST'; url=$routeUrl; body=[ordered]@{ resourceId=$expressRouteConnectionId; virtualWanResourceType='ExpressRouteConnection' } }
        )
    }
    gcp = [ordered]@{
        projectId = $state.gcp_project_id
        region = $state.gcp_region
        zone = 'europe-north2-c'
        routerName = "cr-$prefix"
        attachmentName = "att-$prefix"
        cpeVmName = "cpe-$prefix"
    }
    generatedTunnelSlots = @(
        [ordered]@{ name='pri0'; ikeEndpoint=$instance0PrivateIke; bgpPeer=$instance0.defaultBgpIpAddresses[0]; configuredCustomBgpPeer=$privateCustomPeers[0]; localBgpSource='10.250.254.240'; xfrmInterface='xfrm-pri0'; xfrmId=410; effectivePeerClass='default-shared-with-pub0' },
        [ordered]@{ name='pri1'; ikeEndpoint=$instance1PrivateIke; bgpPeer=$instance1.defaultBgpIpAddresses[0]; configuredCustomBgpPeer=$privateCustomPeers[1]; localBgpSource='10.250.254.240'; xfrmInterface='xfrm-pri1'; xfrmId=411; effectivePeerClass='default-shared-with-pub1' },
        [ordered]@{ name='pub0'; ikeEndpoint=$instance0PublicIke; bgpPeer=$instance0.defaultBgpIpAddresses[0]; configuredCustomBgpPeer=$publicCustomPeers[0]; localBgpSource='10.250.254.241'; xfrmInterface='xfrm-pub0'; xfrmId=420; effectivePeerClass='default-shared-with-pri0' },
        [ordered]@{ name='pub1'; ikeEndpoint=$instance1PublicIke; bgpPeer=$instance1.defaultBgpIpAddresses[0]; configuredCustomBgpPeer=$publicCustomPeers[1]; localBgpSource='10.250.254.241'; xfrmInterface='xfrm-pub1'; xfrmId=421; effectivePeerClass='default-shared-with-pri1' }
    )
    megaport = [ordered]@{
        collectorScript = $collector
        mcrUid = $mcrUid
        vxcUids = [ordered]@{
            azurePrimary = $vxcUids.azure_primary
            azureSecondary = $vxcUids.azure_secondary
            gcp = $vxcUids.gcp
        }
    }
    operations = [ordered]@{
        faultScript = $faultScript
        partialWorkloadPlaneDrop = 'partial-workload-plane-drop'
        reviewed = @(
            [ordered]@{ scenarioId='single-msee-vxc'; faultName='single-msee-primary'; faultCommand="& '$faultScript' -Fault single-msee-primary -Operation Fault -InventoryPath '$OutputPath'"; restoreCommand="& '$faultScript' -Fault single-msee-primary -Operation Restore -InventoryPath '$OutputPath'" },
            [ordered]@{ scenarioId='single-msee-vxc'; faultName='single-msee-secondary'; faultCommand="& '$faultScript' -Fault single-msee-secondary -Operation Fault -InventoryPath '$OutputPath'"; restoreCommand="& '$faultScript' -Fault single-msee-secondary -Operation Restore -InventoryPath '$OutputPath'" },
            [ordered]@{ scenarioId='full-er'; faultName='full-er'; faultCommand="& '$faultScript' -Fault full-er -Operation Fault -InventoryPath '$OutputPath'"; restoreCommand="& '$faultScript' -Fault full-er -Operation Restore -InventoryPath '$OutputPath'" },
            [ordered]@{ scenarioId='ipsec-only'; faultName='ipsec-pri0'; faultCommand="& '$faultScript' -Fault ipsec-pri0 -Operation Fault -InventoryPath '$OutputPath'"; restoreCommand="& '$faultScript' -Fault ipsec-pri0 -Operation Restore -InventoryPath '$OutputPath'" },
            [ordered]@{ scenarioId='bgp-only'; faultName='bgp-pri0'; faultCommand="& '$faultScript' -Fault bgp-pri0 -Operation Fault -InventoryPath '$OutputPath'"; restoreCommand="& '$faultScript' -Fault bgp-pri0 -Operation Restore -InventoryPath '$OutputPath'" },
            [ordered]@{ scenarioId='partial-workload-plane-drop'; faultName='partial-workload-plane-drop'; faultCommand="& '$faultScript' -Fault partial-workload-plane-drop -Operation Fault -InventoryPath '$OutputPath'"; restoreCommand="& '$faultScript' -Fault partial-workload-plane-drop -Operation Restore -InventoryPath '$OutputPath'" },
            [ordered]@{ scenarioId='internet'; faultName='internet'; faultCommand="& '$faultScript' -Fault internet -Operation Fault -InventoryPath '$OutputPath'"; restoreCommand="& '$faultScript' -Fault internet -Operation Restore -InventoryPath '$OutputPath'" },
            [ordered]@{ scenarioId='d3-internet-then-primary'; faultName='internet-then-bgp-private'; faultCommand="Run internet/Fault, verify the static aggregate, then run bgp-private/Fault."; restoreCommand="Run bgp-private/Restore first, then internet/Restore, then Reset-Lab.ps1 and the full reset gate." }
        )
    }
    probe = [ordered]@{
        azureWorkloadIp = $workloadNic.ipConfigurations[0].privateIpAddress
        azureUrlFromGcp = "http://$($workloadNic.ipConfigurations[0].privateIpAddress):8080/health"
        designTargets = [ordered]@{
            D1 = @([ordered]@{ ip='10.253.1.10'; url='http://10.253.1.10:8080/health' })
            D2 = @([ordered]@{ ip='10.253.2.10'; url='http://10.253.2.10:8080/health' })
            D3 = @(
                [ordered]@{ ip='10.253.3.10'; url='http://10.253.3.10:8080/health' },
                [ordered]@{ ip='10.253.3.138'; url='http://10.253.3.138:8080/health' }
            )
        }
    }
    expected = [ordered]@{
        baselinePrefix = '10.241.0.0/24'
        designPrefixes = [ordered]@{
            D1 = @('10.253.1.0/24')
            D2 = @('10.253.2.0/24')
            D3 = @('10.253.3.0/24','10.253.3.0/25','10.253.3.128/25')
        }
    }
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputPath) | Out-Null
$inventory | ConvertTo-Json -Depth 15 | Set-Content -Path $OutputPath -Encoding utf8
Write-Output $OutputPath
