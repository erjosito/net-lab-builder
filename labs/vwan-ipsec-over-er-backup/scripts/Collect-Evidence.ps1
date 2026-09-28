#Requires -Version 7.0
<#
.SYNOPSIS
  Read-only route, session and packet evidence collector for vwan-ipsec-over-er-backup.

.DESCRIPTION
  Reads Tank's sanitized deployment inventory and captures one timestamped snapshot.
  It does not create, update, stop, start or delete infrastructure. Fault injection and
  restoration remain Tank-owned operations.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$InventoryPath,

    [Parameter(Mandatory)]
    [ValidatePattern('^[a-z0-9][a-z0-9-]*(?:/[a-z0-9][a-z0-9-]*)*$')]
    [string]$Phase,

    [ValidateRange(5, 120)]
    [int]$CaptureSeconds = 20,

    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$LabRoot = Split-Path -Parent $PSScriptRoot
$InventoryPath = (Resolve-Path $InventoryPath).Path
$Inventory = Get-Content $InventoryPath -Raw | ConvertFrom-Json
$Stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$OutputDir = Join-Path $LabRoot "show-output\$Phase\$Stamp"

function Protect-Text {
    param([AllowEmptyString()][string]$Text)
    $safe = $Text
    $safe = $safe -replace '(?i)(/subscriptions/)[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', '$1<SUBSCRIPTION_ID>'
    $safe = $safe -replace '(?i)(login\.microsoftonline\.com/)[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', '$1<TENANT_ID>'
    $safe = $safe -replace '(?i)("(?:serviceKey|pairingKey|preSharedKey|sharedKey|access_token|client_secret)"\s*:\s*")[^"]+(")', '$1<REDACTED>$2'
    $safe = $safe -replace '(?i)(authorization:\s*bearer\s+)\S+', '$1<REDACTED>'
    if ($Inventory.gcp.projectId -and $Inventory.gcp.projectId -notmatch '^<') {
        $safe = $safe -replace [regex]::Escape([string]$Inventory.gcp.projectId), '<GCP_PROJECT_ID>'
    }
    return $safe
}

function Assert-InventoryValue {
    param([string]$Name, [AllowNull()][object]$Value)
    if (-not $Value -or [string]$Value -match '^<.*>$') {
        throw "Inventory value '$Name' is missing or still a placeholder."
    }
}

function Save-CommandOutput {
    param(
        [string]$FileName,
        [string]$DisplayCommand,
        [scriptblock]$Action
    )
    $display = Protect-Text $DisplayCommand
    if ($DryRun) {
        Write-Host "[DRY-RUN] $FileName :: $display"
        return
    }
    $started = (Get-Date).ToUniversalTime().ToString('o')
    try {
        $global:LASTEXITCODE = 0
        $raw = & $Action 2>&1 | Out-String
        $exit = $LASTEXITCODE
    } catch {
        $raw = $_ | Out-String
        $exit = 1
    }
    $body = @"
# action: read-only evidence capture
# utc_started: $started
# command: $display
# exit_code: $exit
$(Protect-Text $raw)
"@
    Set-Content -Path (Join-Path $OutputDir $FileName) -Value $body -Encoding utf8
}

function Invoke-AzureManagedRouteQuery {
    param(
        [string]$Method,
        [string]$Url,
        [object]$Body,
        [int]$TimeoutSeconds = 300
    )
    $token = az account get-access-token --resource https://management.azure.com/ --query accessToken -o tsv
    if ($LASTEXITCODE -ne 0 -or -not $token) {
        throw 'Failed to acquire an ARM token for the managed-route query.'
    }
    $headers = @{ Authorization = "Bearer $token" }
    $jsonBody = $Body | ConvertTo-Json -Depth 10
    $response = Invoke-WebRequest -Method $Method -Uri $Url -Headers $headers `
        -ContentType 'application/json' -Body $jsonBody -SkipHttpErrorCheck
    if ([int]$response.StatusCode -ge 400) {
        throw "Managed-route request failed with HTTP $([int]$response.StatusCode): $($response.Content)"
    }
    if ([int]$response.StatusCode -ne 202) {
        return $response.Content
    }

    $pollUrl = if ($response.Headers.Location) {
        [string]$response.Headers.Location
    } elseif ($response.Headers.'Azure-AsyncOperation') {
        [string]$response.Headers.'Azure-AsyncOperation'
    } else {
        throw 'Managed-route request returned HTTP 202 without a polling URL.'
    }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Seconds 5
        $poll = Invoke-WebRequest -Method Get -Uri $pollUrl -Headers $headers -SkipHttpErrorCheck
        if ([int]$poll.StatusCode -ge 400) {
            throw "Managed-route poll failed with HTTP $([int]$poll.StatusCode): $($poll.Content)"
        }
        if ([int]$poll.StatusCode -eq 202) { continue }
        if (-not $poll.Content) { continue }
        $parsed = $poll.Content | ConvertFrom-Json
        if ($parsed.status -in @('InProgress', 'Running', 'Accepted')) { continue }
        if ($parsed.status -eq 'Failed') {
            throw "Managed-route operation failed: $($poll.Content)"
        }
        if ($parsed.properties.output) {
            return ($parsed.properties.output | ConvertTo-Json -Depth 20)
        }
        return $poll.Content
    } while ((Get-Date) -lt $deadline)

    throw "Managed-route query did not complete within $TimeoutSeconds seconds."
}

if (-not $DryRun) {
    foreach ($item in @(
        @{ Name = 'azure.resourceGroup'; Value = $Inventory.azure.resourceGroup },
        @{ Name = 'azure.vhubName'; Value = $Inventory.azure.vhubName },
        @{ Name = 'azure.vhubRouteTableId'; Value = $Inventory.azure.vhubRouteTableId },
        @{ Name = 'azure.expressRouteCircuitName'; Value = $Inventory.azure.expressRouteCircuitName },
        @{ Name = 'azure.workloadVmName'; Value = $Inventory.azure.workloadVmName },
        @{ Name = 'azure.workloadNicName'; Value = $Inventory.azure.workloadNicName },
        @{ Name = 'gcp.projectId'; Value = $Inventory.gcp.projectId },
        @{ Name = 'gcp.region'; Value = $Inventory.gcp.region },
        @{ Name = 'gcp.zone'; Value = $Inventory.gcp.zone },
        @{ Name = 'gcp.routerName'; Value = $Inventory.gcp.routerName },
        @{ Name = 'gcp.cpeVmName'; Value = $Inventory.gcp.cpeVmName }
    )) {
        Assert-InventoryValue $item.Name $item.Value
    }
}

if (-not $DryRun) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$rg = [string]$Inventory.azure.resourceGroup
$vhub = [string]$Inventory.azure.vhubName
$routeTableId = [string]$Inventory.azure.vhubRouteTableId
$circuit = [string]$Inventory.azure.expressRouteCircuitName
$peering = [string]$Inventory.azure.expressRoutePeeringName

$resourceIds = [ordered]@{
    '02-vpn-gateway.json' = $Inventory.azure.vpnGatewayId
    '03-private-vpn-site.json' = $Inventory.azure.privateVpnSiteId
    '04-public-vpn-site.json' = $Inventory.azure.publicVpnSiteId
    '05-private-vpn-connection.json' = $Inventory.azure.privateVpnConnectionId
    '06-public-vpn-connection.json' = $Inventory.azure.publicVpnConnectionId
    '07-er-gateway.json' = $Inventory.azure.expressRouteGatewayId
    '08-er-connection.json' = $Inventory.azure.expressRouteConnectionId
}

Save-CommandOutput '01-vhub-effective-routes.json' "az network vhub get-effective-routes -g $rg -n $vhub --resource-type RouteTable --resource-id $routeTableId -o json" {
    az network vhub get-effective-routes -g $rg -n $vhub --resource-type RouteTable --resource-id $routeTableId -o json
}

foreach ($entry in $resourceIds.GetEnumerator()) {
    if (-not $DryRun) {
        Assert-InventoryValue $entry.Key $entry.Value
    }
    $id = [string]$entry.Value
    Save-CommandOutput $entry.Key "az resource show --ids $id -o json" {
        az resource show --ids $id -o json
    }
}

Save-CommandOutput '09-er-circuit.json' "az network express-route show -g $rg -n $circuit -o json" {
    az network express-route show -g $rg -n $circuit -o json
}
Save-CommandOutput '10-er-route-table-primary.json' "az network express-route list-route-tables -g $rg -n $circuit --peering-name $peering --path primary -o json" {
    az network express-route list-route-tables -g $rg -n $circuit --peering-name $peering --path primary -o json
}
Save-CommandOutput '11-er-route-table-secondary.json' "az network express-route list-route-tables -g $rg -n $circuit --peering-name $peering --path secondary -o json" {
    az network express-route list-route-tables -g $rg -n $circuit --peering-name $peering --path secondary -o json
}
Save-CommandOutput '12-workload-nic-effective-routes.json' "az network nic show-effective-route-table -g $rg -n $($Inventory.azure.workloadNicName) -o json" {
    az network nic show-effective-route-table -g $rg -n $Inventory.azure.workloadNicName -o json
}
Save-CommandOutput '12a-workload-kernel-routes.txt' "az vm run-command invoke -g $rg -n $($Inventory.azure.workloadVmName) --command-id RunShellScript --scripts '<ip route and rule capture>'" {
    az vm run-command invoke -g $rg -n $Inventory.azure.workloadVmName --command-id RunShellScript `
        --scripts 'ip -details route show table all; ip rule show' -o json
}

if (-not $Inventory.azure.routeQueries -or @($Inventory.azure.routeQueries).Count -lt 3) {
    if (-not $DryRun) {
        throw 'Inventory must define the private VPN, public VPN and ER route API queries from Trinity/Tank.'
    }
} else {
    foreach ($query in $Inventory.azure.routeQueries) {
        if ([string]$query.name -notmatch '^[a-z0-9][a-z0-9-]+$') {
            throw "Invalid route query name: $($query.name)"
        }
        $fileName = "12b-$($query.name).json"
        $method = [string]$query.method
        $url = [string]$query.url
        $display = "az rest --method $method --url $url --body '<SANITIZED_BODY>' -o json"
        Save-CommandOutput $fileName $display {
            Invoke-AzureManagedRouteQuery -Method $method -Url $url -Body $query.body
        }
    }
}

$azureCapture = "sudo timeout ${CaptureSeconds}s tcpdump -ni any -s 128 -tttt -vv '(tcp or icmp)'"
Save-CommandOutput '12c-workload-packet-capture.json' "az vm run-command invoke -g $rg -n $($Inventory.azure.workloadVmName) --command-id RunShellScript --scripts '<header-only tcpdump>'" {
    az vm run-command invoke -g $rg -n $Inventory.azure.workloadVmName --command-id RunShellScript `
        --scripts $azureCapture -o json
}

$gcpProject = [string]$Inventory.gcp.projectId
$gcpRegion = [string]$Inventory.gcp.region
$gcpZone = [string]$Inventory.gcp.zone
$gcpRouter = [string]$Inventory.gcp.routerName
$gcpAttachment = [string]$Inventory.gcp.attachmentName
$cpe = [string]$Inventory.gcp.cpeVmName

Save-CommandOutput '13-gcp-cloud-router-status.json' "gcloud compute routers get-status $gcpRouter --region $gcpRegion --project $gcpProject --format=json" {
    gcloud compute routers get-status $gcpRouter --region $gcpRegion --project $gcpProject --format=json
}
if ($gcpAttachment -and $gcpAttachment -notmatch '^<') {
    Save-CommandOutput '14-gcp-vlan-attachment.json' "gcloud compute interconnects attachments describe $gcpAttachment --region $gcpRegion --project $gcpProject --format=json" {
        gcloud compute interconnects attachments describe $gcpAttachment --region $gcpRegion --project $gcpProject --format=json
    }
}
Save-CommandOutput '14a-gcp-cpe-instance.json' "gcloud compute instances describe $cpe --zone $gcpZone --project $gcpProject --format=json" {
    gcloud compute instances describe $cpe --zone $gcpZone --project $gcpProject --format=json
}
Save-CommandOutput '14b-gcp-vpc-routes.json' "gcloud compute routes list --project $gcpProject --format=json" {
    gcloud compute routes list --project $gcpProject --format=json
}
Save-CommandOutput '14c-gcp-firewall-rules.json' "gcloud compute firewall-rules list --project $gcpProject --format=json" {
    gcloud compute firewall-rules list --project $gcpProject --format=json
}

$routeChecks = [System.Collections.Generic.List[string]]::new()
foreach ($slot in @($Inventory.generatedTunnelSlots)) {
    if ($slot.ikeEndpoint -and [string]$slot.ikeEndpoint -notmatch '^<') {
        $routeChecks.Add("echo 'slot=$($slot.name) ike'; ip route get $($slot.ikeEndpoint) from 10.250.0.10")
    }
    if ($slot.bgpPeer -and [string]$slot.bgpPeer -notmatch '^<') {
        $routeChecks.Add("echo 'slot=$($slot.name) bgp'; ip route get $($slot.bgpPeer) from $($slot.localBgpSource)")
    }
}
$routeCheckCommand = if ($routeChecks.Count) {
    ($routeChecks -join '; ')
} else {
    'echo "GENERATED_TUNNEL_SLOTS_NOT_POPULATED"'
}
$cpeCommands = [ordered]@{
    '15-cpe-frr-summary.txt' = 'sudo vtysh -c "show bgp summary json"'
    '16-cpe-frr-routes.txt' = 'sudo vtysh -c "show bgp ipv4 unicast json"'
    '17-cpe-bird-protocols.txt' = 'command -v birdc >/dev/null && sudo birdc show protocols all || echo "BIRD_NOT_INSTALLED"'
    '18-cpe-bird-routes.txt' = 'command -v birdc >/dev/null && sudo birdc show route all || echo "BIRD_NOT_INSTALLED"'
    '19-cpe-kernel-routes.txt' = "ip -details route show table all; ip rule show; ip route get 10.241.0.4; $routeCheckCommand"
    '20-cpe-links-xfrm.txt' = 'ip -details link show; ip xfrm state; ip xfrm policy'
    '21-cpe-strongswan.txt' = 'sudo swanctl --list-sas --raw; sudo swanctl --list-conns --raw'
    '22-cpe-sockets.txt' = 'sudo ss -Hlnup; sudo ss -Htnp state established'
    '22a-cpe-nftables.txt' = 'sudo nft list ruleset'
    '22b-cpe-config-hashes.txt' = 'sudo sha256sum /etc/frr/frr.conf /etc/swanctl/conf.d/vwan.conf /etc/vwan-lab/network.env /etc/nftables.d-vwan-lab.conf /etc/systemd/system/vwan-lab-network.service /etc/systemd/system/vwan-lab-ipsec.service 2>&1'
}
foreach ($entry in $cpeCommands.GetEnumerator()) {
    $remote = [string]$entry.Value
    Save-CommandOutput $entry.Key "gcloud compute ssh $cpe --zone $gcpZone --project $gcpProject --command '$remote'" {
        gcloud compute ssh $cpe --zone $gcpZone --project $gcpProject --quiet --command $remote
    }
}

$filter = '(udp port 500 or udp port 4500 or esp or tcp port 179 or icmp)'
$capture = "sudo timeout ${CaptureSeconds}s tcpdump -ni any -s 128 -tttt -vv '$filter'"
Save-CommandOutput '23-cpe-packet-capture.txt' "gcloud compute ssh $cpe --zone $gcpZone --project $gcpProject --command '$capture'" {
    gcloud compute ssh $cpe --zone $gcpZone --project $gcpProject --quiet --command $capture
}

$megaportCollector = [string]$Inventory.megaport.collectorScript
if ($megaportCollector -and $megaportCollector -notmatch '^<') {
    if (-not (Test-Path $megaportCollector)) {
        throw "Tank Megaport collector not found: $megaportCollector"
    }
    $mpOut = Join-Path $OutputDir '24-megaport-mcr-vxcs.json'
    Save-CommandOutput '24-megaport-collector-log.txt' "& $megaportCollector -OutputPath $mpOut -ReadOnly" {
        & $megaportCollector -OutputPath $mpOut -ReadOnly
    }
    if (-not $DryRun -and (Test-Path $mpOut)) {
        Set-Content -Path $mpOut -Value (Protect-Text (Get-Content $mpOut -Raw)) -Encoding utf8
    }
} else {
    Save-CommandOutput '24-megaport-collector-missing.txt' '<Tank read-only Megaport collector required>' {
        'MISSING: Tank must publish a secret-safe read-only MCR/VXC collector.'
    }
}

if (-not $DryRun) {
    & (Join-Path $PSScriptRoot 'Confirm-Sanitization.ps1') -Path $OutputDir
    Write-Host $OutputDir
}
