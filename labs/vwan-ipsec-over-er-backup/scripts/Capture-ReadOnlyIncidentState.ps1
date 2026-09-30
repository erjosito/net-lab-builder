#Requires -Version 7.0
[CmdletBinding()]
param(
    [string]$InventoryPath = (Join-Path (Split-Path -Parent $PSScriptRoot) 'config\inventory.json'),
    [int]$TcpdumpSeconds = 15
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$labRoot = Split-Path -Parent $PSScriptRoot
$inventoryPath = (Resolve-Path $InventoryPath).Path
$inventory = Get-Content $inventoryPath -Raw | ConvertFrom-Json
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$correlationId = "readonly-live-$stamp"
$outputRoot = Join-Path $labRoot "show-output\live-readonly\$stamp"
$audit = Join-Path $PSScriptRoot 'Invoke-AuditCommand.ps1'
$apiVersion = '2025-09-01'

function Invoke-ReadOnlyAudit {
    param(
        [string]$QuestionId,
        [string]$ExpectedEffect,
        [string]$Command,
        [string]$Name,
        [int]$TimeoutSeconds = 300
    )
    $path = Join-Path $outputRoot $Name
    & $audit `
        -ActionType query `
        -Scenario live-readonly `
        -QuestionId $QuestionId `
        -State action `
        -ExpectedEffect $ExpectedEffect `
        -Command $Command `
        -OutputDirectory $path `
        -CorrelationId $correlationId `
        -TimeoutSeconds $TimeoutSeconds `
        -AllowFailure | Out-Null
}

$vpnGatewayId = [string]$inventory.azure.vpnGatewayId
$privateSiteId = [string]$inventory.azure.privateVpnSiteId
$publicSiteId = [string]$inventory.azure.publicVpnSiteId
$privateConnectionId = [string]$inventory.azure.privateVpnConnectionId
$publicConnectionId = [string]$inventory.azure.publicVpnConnectionId
$erGatewayId = [string]$inventory.azure.expressRouteGatewayId
$rg = [string]$inventory.azure.resourceGroup
$circuit = [string]$inventory.azure.expressRouteCircuitName
$peering = [string]$inventory.azure.expressRoutePeeringName
$project = [string]$inventory.gcp.projectId
$region = [string]$inventory.gcp.region
$zone = [string]$inventory.gcp.zone
$router = [string]$inventory.gcp.routerName
$attachment = [string]$inventory.gcp.attachmentName
$cpe = [string]$inventory.gcp.cpeVmName

Invoke-ReadOnlyAudit `
    -QuestionId 'Q-LIVE-VPN-GATEWAY-BGP' `
    -ExpectedEffect "Return the full VPN gateway JSON, including all customBgpIpAddresses, using API $apiVersion." `
    -Name '01-vpn-gateway-custom-bgp' `
    -Command "az rest --method get --url 'https://management.azure.com${vpnGatewayId}?api-version=$apiVersion' --output json"

$vpnObjectsCommand = @"
Write-Output 'API_VERSION=$apiVersion'
Write-Output 'PRIVATE_SITE'
az rest --method get --url 'https://management.azure.com${privateSiteId}?api-version=$apiVersion' --output json
Write-Output 'PUBLIC_SITE'
az rest --method get --url 'https://management.azure.com${publicSiteId}?api-version=$apiVersion' --output json
Write-Output 'PRIVATE_CONNECTION_AND_LINK_CONNECTION'
az rest --method get --url 'https://management.azure.com${privateConnectionId}?api-version=$apiVersion' --output json
Write-Output 'PUBLIC_CONNECTION_AND_LINK_CONNECTION'
az rest --method get --url 'https://management.azure.com${publicConnectionId}?api-version=$apiVersion' --output json
"@
Invoke-ReadOnlyAudit `
    -QuestionId 'Q-LIVE-VPN-BGP-PROPERTIES' `
    -ExpectedEffect 'Return site/link and connection/link-connection BGP properties and provisioning states without changing them.' `
    -Name '02-vpn-sites-connections-bgp' `
    -Command $vpnObjectsCommand

Invoke-ReadOnlyAudit `
    -QuestionId 'Q-LIVE-IPSEC-SAS' `
    -ExpectedEffect 'Show the currently installed IKE and child SAs for all four tunnel slots.' `
    -Name '03-current-four-sas' `
    -Command "gcloud compute ssh '$cpe' --zone '$zone' --project '$project' --quiet --command 'sudo swanctl --list-sas --raw; echo CONNECTIONS; sudo swanctl --list-conns --raw'"

Invoke-ReadOnlyAudit `
    -QuestionId 'Q-LIVE-FRR' `
    -ExpectedEffect 'Show current FRR neighbor state and IPv4 unicast routes without clearing or refreshing any session.' `
    -Name '04-frr-neighbors-routes' `
    -Command "gcloud compute ssh '$cpe' --zone '$zone' --project '$project' --quiet --command 'sudo vtysh -c `"show bgp summary json`"; echo ROUTES; sudo vtysh -c `"show bgp ipv4 unicast json`"'"

Invoke-ReadOnlyAudit `
    -QuestionId 'Q-LIVE-TCP179' `
    -ExpectedEffect 'Capture only current TCP/179 headers for a bounded interval; timeout exit is expected and preserved.' `
    -Name '05-tcp179-sample' `
    -TimeoutSeconds ($TcpdumpSeconds + 90) `
    -Command "gcloud compute ssh '$cpe' --zone '$zone' --project '$project' --quiet --command 'sudo timeout ${TcpdumpSeconds}s tcpdump -ni any -s 128 -tttt -vv `"tcp port 179`"'"

$erCommand = @"
Write-Output 'ER_GATEWAY_API_VERSION=2024-10-01'
az rest --method get --url 'https://management.azure.com${erGatewayId}?api-version=2024-10-01' --output json
Write-Output 'ER_CIRCUIT'
az network express-route show --resource-group '$rg' --name '$circuit' --output json
Write-Output 'ER_PRIVATE_PEERING'
az network express-route peering show --resource-group '$rg' --circuit-name '$circuit' --name '$peering' --output json
"@
Invoke-ReadOnlyAudit `
    -QuestionId 'Q-LIVE-ER' `
    -ExpectedEffect 'Show current ER gateway, circuit/provider and private-peering state.' `
    -Name '06-er-gateway-circuit-peering' `
    -Command $erCommand

$megaportTemp = Join-Path $env:TEMP "megaport-readonly-$stamp.json"
$collector = [string]$inventory.megaport.collectorScript
$megaportCommand = @"
try {
  & '$collector' -OutputPath '$megaportTemp' -InventoryPath '$inventoryPath' -ReadOnly
  Get-Content '$megaportTemp' -Raw
} finally {
  Remove-Item '$megaportTemp' -Force -ErrorAction SilentlyContinue
}
"@
Invoke-ReadOnlyAudit `
    -QuestionId 'Q-LIVE-MEGAPORT' `
    -ExpectedEffect 'Show current MCR and all three VXC provisioning, up/shutdown, path-selection and BGP state.' `
    -Name '07-megaport-mcr-vxcs' `
    -Command $megaportCommand

$gcpCommand = @"
Write-Output 'PARTNER_ATTACHMENT'
gcloud compute interconnects attachments describe '$attachment' --region '$region' --project '$project' --format=json
Write-Output 'CLOUD_ROUTER_STATUS'
gcloud compute routers get-status '$router' --region '$region' --project '$project' --format=json
"@
Invoke-ReadOnlyAudit `
    -QuestionId 'Q-LIVE-GCP-PARTNER' `
    -ExpectedEffect 'Show current Partner attachment and Cloud Router BGP/route state.' `
    -Name '08-gcp-attachment-router' `
    -Command $gcpCommand

$inventoryCommand = @"
`$root = Get-Content '$inventoryPath' -Raw | ConvertFrom-Json
function Walk([object]`$Value, [string]`$Path) {
  if (`$null -eq `$Value) {
    [pscustomobject]@{ path = `$Path; state = 'null' }
  } elseif (`$Value -is [System.Management.Automation.PSCustomObject]) {
    foreach (`$property in `$Value.PSObject.Properties) {
      Walk `$property.Value (if (`$Path) { "`$Path.`$(`$property.Name)" } else { `$property.Name })
    }
  } elseif (`$Value -is [System.Collections.IEnumerable] -and `$Value -isnot [string]) {
    `$items = @(`$Value)
    if (`$items.Count -eq 0) { [pscustomobject]@{ path = `$Path; state = 'empty-array' } }
    for (`$i = 0; `$i -lt `$items.Count; `$i++) { Walk `$items[`$i] "`$Path[`$i]" }
  } else {
    [pscustomobject]@{ path = `$Path; state = 'non-null'; type = `$Value.GetType().Name }
  }
}
Walk `$root '' | Sort-Object path | ConvertTo-Json -Depth 5
"@
Invoke-ReadOnlyAudit `
    -QuestionId 'Q-LIVE-INVENTORY-COMPLETENESS' `
    -ExpectedEffect 'List every runtime inventory field as null, empty or non-null without emitting its value.' `
    -Name '09-inventory-null-status' `
    -Command $inventoryCommand

$costCommand = @"
`$subscription = az account show --query id -o tsv
`$start = (Get-Date -Day 1).ToString('yyyy-MM-dd')
`$end = (Get-Date).AddDays(1).ToString('yyyy-MM-dd')
`$body = @{
  type = 'ActualCost'
  timeframe = 'Custom'
  timePeriod = @{ from = "`$start`T00:00:00Z"; to = "`$end`T00:00:00Z" }
  dataset = @{
    granularity = 'None'
    aggregation = @{ totalCost = @{ name = 'PreTaxCost'; function = 'Sum' } }
    grouping = @(@{ type = 'Dimension'; name = 'ServiceName' })
    filter = @{ dimensions = @{ name = 'ResourceGroupName'; operator = 'In'; values = @('$rg') } }
  }
}
`$bodyFile = Join-Path `$env:TEMP 'vwan-cost-query.json'
try {
  `$body | ConvertTo-Json -Depth 10 | Set-Content `$bodyFile -Encoding utf8
  Write-Output 'AZURE_MONTH_TO_DATE_ACTUAL_COST'
  az rest --method post --url "https://management.azure.com/subscriptions/`$subscription/providers/Microsoft.CostManagement/query?api-version=2023-11-01" --body "@`$bodyFile" --output json
} finally {
  Remove-Item `$bodyFile -Force -ErrorAction SilentlyContinue
}
Write-Output 'GCP_BILLING_LINK_AND_LIVE_PRODUCTS'
gcloud billing projects describe '$project' --format=json
gcloud compute instances describe '$cpe' --zone '$zone' --project '$project' --format='json(status,machineType,disks,networkInterfaces.accessConfigs)'
gcloud compute interconnects attachments describe '$attachment' --region '$region' --project '$project' --format='json(state,type,bandwidth,edgeAvailabilityDomain)'
Write-Output 'MEGAPORT_COMMITMENT'
Select-String -Path '$(Join-Path $labRoot 'deploy-log.md')' -Pattern 'EUR 991.80/month','managed gateways','continue billing' | ForEach-Object { `$_.Line }
"@
Invoke-ReadOnlyAudit `
    -QuestionId 'Q-LIVE-COST-EXPOSURE' `
    -ExpectedEffect 'Capture available Azure actual cost, GCP billing/resource exposure and the live Megaport monthly commitment without placing an order.' `
    -Name '10-cost-commitment-exposure' `
    -TimeoutSeconds 600 `
    -Command $costCommand

$commitTime = (git show -s --format=%cI f75c1b3).Trim()
$mutationCommand = @"
Write-Output 'ANCHOR_COMMIT=f75c1b3'
Write-Output 'ANCHOR_TIME=$commitTime'
Write-Output 'AZURE_ACTIVITY_WRITES'
az monitor activity-log list --resource-group '$rg' --start-time '$commitTime' --output json --query "[?contains(operationName.value, 'write') || contains(operationName.value, 'delete') || contains(operationName.value, 'action')]"
Write-Output 'GCP_ADMIN_ACTIVITY'
gcloud logging read 'logName:"cloudaudit.googleapis.com%2Factivity" AND timestamp>="$commitTime"' --project '$project' --limit=100 --format=json
Write-Output 'CPE_CONFIG_MTIMES_AND_SERVICE_LOG'
gcloud compute ssh '$cpe' --zone '$zone' --project '$project' --quiet --command 'sudo stat -c "%y %n" /etc/frr/frr.conf /etc/swanctl/conf.d/vwan.conf /etc/vwan-lab/network.env /etc/nftables.d-vwan-lab.conf 2>&1; sudo journalctl --since "$commitTime" -u vwan-lab-network.service -u vwan-lab-ipsec.service -u frr --no-pager'
"@
Invoke-ReadOnlyAudit `
    -QuestionId 'Q-LIVE-POST-F75C1B3-MUTATIONS' `
    -ExpectedEffect 'Determine whether Azure, GCP or CPE logs show a live mutation after commit f75c1b3; Megaport mutation history is not inferred from current state.' `
    -Name '11-post-f75c1b3-mutation-check' `
    -TimeoutSeconds 600 `
    -Command $mutationCommand

& (Join-Path $PSScriptRoot 'Confirm-Sanitization.ps1') -Path $outputRoot
& (Join-Path $PSScriptRoot 'New-EvidenceIndex.ps1') -LabRoot $labRoot | Out-Null
Write-Host $outputRoot
