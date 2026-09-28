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
$routeUrl = "https://management.azure.com$($vhub.id)/effectiveRoutes?api-version=2025-09-01"
$collector = (Resolve-Path (Join-Path $PSScriptRoot 'Collect-MegaportReadOnly.ps1')).Path
$faultScript = (Resolve-Path (Join-Path $PSScriptRoot 'Invoke-LabFault.ps1')).Path

$inventory = [ordered]@{
    schemaVersion = 1
    runId = $state.run_id
    deploymentStatus = 'foundation-only-provider-blocked'
    azure = [ordered]@{
        resourceGroup = $resourceGroup
        vhubName = $vhub.name
        vhubRouteTableId = "$($vhub.id)/hubRouteTables/defaultRouteTable"
        vpnGatewayId = $vpnGateway.id
        privateVpnSiteId = $null
        publicVpnSiteId = $null
        privateVpnConnectionId = $null
        publicVpnConnectionId = $null
        expressRouteGatewayId = $erGateway.id
        expressRouteConnectionId = $null
        expressRouteCircuitName = "er-$prefix"
        expressRoutePeeringName = 'AzurePrivatePeering'
        workloadVmName = $workloadVm.name
        workloadNicName = $workloadNic.name
        routeQueries = @(
            [ordered]@{ name='vpn-private-routes'; method='POST'; url=$routeUrl; body=[ordered]@{ resourceId=$null; virtualWanResourceType='VpnConnection' } },
            [ordered]@{ name='vpn-public-routes'; method='POST'; url=$routeUrl; body=[ordered]@{ resourceId=$null; virtualWanResourceType='VpnConnection' } },
            [ordered]@{ name='er-connection-routes'; method='POST'; url=$routeUrl; body=[ordered]@{ resourceId=$null; virtualWanResourceType='ExpressRouteConnection' } }
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
        [ordered]@{ name='pri0'; ikeEndpoint=$instance0PrivateIke; bgpPeer=$instance0.defaultBgpIpAddresses[0]; localBgpSource='10.250.254.240'; xfrmInterface='xfrm-pri0'; xfrmId=410 },
        [ordered]@{ name='pri1'; ikeEndpoint=$instance1PrivateIke; bgpPeer=$instance1.defaultBgpIpAddresses[0]; localBgpSource='10.250.254.240'; xfrmInterface='xfrm-pri1'; xfrmId=411 },
        [ordered]@{ name='pub0'; ikeEndpoint=$instance0PublicIke; bgpPeer=$instance0.defaultBgpIpAddresses[0]; localBgpSource='10.250.254.241'; xfrmInterface='xfrm-pub0'; xfrmId=420 },
        [ordered]@{ name='pub1'; ikeEndpoint=$instance1PublicIke; bgpPeer=$instance1.defaultBgpIpAddresses[0]; localBgpSource='10.250.254.241'; xfrmInterface='xfrm-pub1'; xfrmId=421 }
    )
    megaport = [ordered]@{
        collectorScript = $collector
        mcrUid = $null
        vxcUids = [ordered]@{ azurePrimary=$null; azureSecondary=$null; gcp=$null }
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
