#Requires -Version 5.1
<#
.SYNOPSIS
  Deploy dual-hub-vnra-udr-transit lab to Azure.
  correlation_id: vnra-c7e2a3f1
.NOTES
  Author   : Tank (Copilot IaC agent)
  Reviewed : Trinity v2 APPROVED 2026-08-19
  Auth     : Jose Moreno Phase-4

  Order: RG -> VNets+Subnets -> RouteTables+Routes -> Peerings ->
         VNRAs(async+poll) -> RT Associations -> VMs -> Smoke Check
  No PIPs, no NSGs, no gateways, no VM NVAs.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$SCRIPT_DIR   = $PSScriptRoot
$OUTPUT_DIR   = Join-Path $SCRIPT_DIR "show-output\deployment"
$LOG_FILE     = Join-Path $OUTPUT_DIR "deploy-run.log"
$DEPLOY_START = Get-Date
$RG           = "rg-dual-hub-vnra-udr-transit"
$API          = "2025-05-01"
$CORR_ID      = "vnra-c7e2a3f1"
$TAGS_ARR     = @("lab=true", "created_by=copilot-lab", "correlation_id=$CORR_ID")

Write-Host "`n== dual-hub-vnra-udr-transit deployment ==" -ForegroundColor Cyan
$SUB      = az account show --query id -o tsv
$SUB_NAME = az account show --query name -o tsv
if (-not $SUB) { throw "No active subscription. Run: az login" }
Write-Host "Subscription: $SUB_NAME"
$SSH_KEY_PATH = Join-Path $env:USERPROFILE ".ssh\id_rsa.pub"
if (-not (Test-Path $SSH_KEY_PATH)) { throw "SSH key missing: $SSH_KEY_PATH" }
New-Item -ItemType Directory -Force -Path $OUTPUT_DIR | Out-Null

function Log($msg) {
    $line = "[$(Get-Date -Format HH:mm:ss)] $msg"
    Write-Host $line
    $line | Add-Content -Path $LOG_FILE -Encoding UTF8
}
function Log-Step($msg) {
    $line = "`n=== $msg ==="
    Write-Host $line -ForegroundColor Cyan
    $line | Add-Content -Path $LOG_FILE -Encoding UTF8
}
function Log-OK($msg)   { Log "  OK   $msg" }
function Log-Warn($msg) { $m="  WARN $msg"; Write-Host $m -ForegroundColor Yellow; $m | Add-Content -Path $LOG_FILE -Encoding UTF8 }
function Save-Output([string]$fn,[string]$txt) {
    $s = $txt -replace [regex]::Escape($SUB),"<SUBSCRIPTION_ID>" `
               -replace "5ad00b69-0386-4c74-8adc-ac7a28649f34","<TENANT_ID>"
    $s | Set-Content (Join-Path $OUTPUT_DIR $fn) -Encoding UTF8
    Log-OK "Saved: $fn"
}
function Poll-VNRA([string]$Name,[int]$TimeoutSec=600) {
    $url = "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Network/virtualNetworkAppliances/$Name`?api-version=$API"
    $dl  = (Get-Date).AddSeconds($TimeoutSec)
    Write-Host "  Polling $Name" -NoNewline
    while ((Get-Date) -lt $dl) {
        $raw = az rest --method GET --url $url -o json 2>&1
        if ($LASTEXITCODE -eq 0) {
            $o = $raw | ConvertFrom-Json
            $s = $o.properties.provisioningState
            if ($s -eq "Succeeded") { Write-Host " OK" -ForegroundColor Green; return $o }
            if ($s -eq "Failed")    { Write-Host " FAILED" -ForegroundColor Red; throw "VNRA $Name FAILED" }
        }
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 20
    }
    throw "Timeout waiting for VNRA $Name"
}

# Step 1: RG
Log-Step "Step 1: Resource Group"
$rgS = az group show -n $RG --query "properties.provisioningState" -o tsv 2>$null
if ($rgS -eq "Succeeded") {
    Log-OK "RG exists: $RG"
} else {
    Log "Creating RG: $RG"
    $o = az group create --name $RG --location swedencentral --tags @TAGS_ARR -o json 2>&1
    if ($LASTEXITCODE -ne 0) { throw "RG failed: $o" }
    Log-OK "RG created"
    Save-Output "01-rg-create.json" ($o | Out-String)
}

# Step 2: VNets+Subnets
Log-Step "Step 2: VNets + Subnets"
$vnets = @(
    @{n="hub1-vnet";   l="swedencentral"; p="10.1.0.0/16";  s="VirtualNetworkApplianceSubnet"; sp="10.1.0.0/24"  }
    @{n="hub2-vnet";   l="northeurope";   p="10.2.0.0/16";  s="VirtualNetworkApplianceSubnet"; sp="10.2.0.0/24"  }
    @{n="spoke1-vnet"; l="swedencentral"; p="10.10.0.0/16"; s="vm-subnet";                    sp="10.10.1.0/24" }
    @{n="spoke2-vnet"; l="northeurope";   p="10.20.0.0/16"; s="vm-subnet";                    sp="10.20.1.0/24" }
)
foreach ($v in $vnets) {
    $id = az network vnet show -g $RG -n $v.n --query "id" -o tsv 2>$null
    if ($id) { Log-OK "Exists: $($v.n)"; continue }
    Log "Creating VNet $($v.n) ($($v.l), $($v.p))"
    $o = az network vnet create -g $RG -n $v.n --location $v.l --address-prefixes $v.p `
         --subnet-name $v.s --subnet-prefixes $v.sp --tags @TAGS_ARR -o json 2>&1
    if ($LASTEXITCODE -ne 0) { throw "VNet failed $($v.n): $o" }
    Log-OK "Created: $($v.n)"
}
Save-Output "02-vnets.json" ((az network vnet list -g $RG -o json 2>&1) | Out-String)

# Step 3: Route Tables + Routes
Log-Step "Step 3: Route Tables + Routes"
$rts = @(
    @{n="rt-spoke1";    l="swedencentral"; p="10.20.0.0/16"; nh="10.1.0.4"}
    @{n="rt-spoke2";    l="northeurope";   p="10.10.0.0/16"; nh="10.2.0.4"}
    @{n="rt-hub1-vnra"; l="swedencentral"; p="10.20.0.0/16"; nh="10.2.0.4"}
    @{n="rt-hub2-vnra"; l="northeurope";   p="10.10.0.0/16"; nh="10.1.0.4"}
)
foreach ($rt in $rts) {
    $id = az network route-table show -g $RG -n $rt.n --query "id" -o tsv 2>$null
    if ($id) { Log-OK "Exists: $($rt.n)"; continue }
    Log "Creating route table: $($rt.n)"
    $o = az network route-table create -g $RG -n $rt.n --location $rt.l `
         --disable-bgp-route-propagation false --tags @TAGS_ARR -o json 2>&1
    if ($LASTEXITCODE -ne 0) { throw "RT failed $($rt.n): $o" }
    $rname = "to-$($rt.p -replace '/','x' -replace '\.','-')"
    $o2 = az network route-table route create -g $RG --route-table-name $rt.n -n $rname `
          --address-prefix $rt.p --next-hop-type VirtualAppliance --next-hop-ip-address $rt.nh -o json 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Route failed in $($rt.n): $o2" }
    Log-OK "Created: $($rt.n) | $($rt.p) -> $($rt.nh)"
}
Save-Output "03-route-tables.json" ((az network route-table list -g $RG -o json 2>&1) | Out-String)

# Step 4: VNet Peerings
Log-Step "Step 4: VNet Peerings (allowVirtualNetworkAccess=true, allowForwardedTraffic=true, 6 objects)"
$peers = @(
    @{src="hub1-vnet";   dst="spoke1-vnet"; n="hub1-to-spoke1"}
    @{src="spoke1-vnet"; dst="hub1-vnet";   n="spoke1-to-hub1"}
    @{src="hub2-vnet";   dst="spoke2-vnet"; n="hub2-to-spoke2"}
    @{src="spoke2-vnet"; dst="hub2-vnet";   n="spoke2-to-hub2"}
    @{src="hub1-vnet";   dst="hub2-vnet";   n="hub1-to-hub2"}
    @{src="hub2-vnet";   dst="hub1-vnet";   n="hub2-to-hub1"}
)
foreach ($p in $peers) {
    $id = az network vnet peering show -g $RG --vnet-name $p.src -n $p.n --query "id" -o tsv 2>$null
    if ($id) {
        # Idempotent: correct either flag if it landed false on a prior run
        $cur = az network vnet peering show -g $RG --vnet-name $p.src -n $p.n -o json 2>&1 | ConvertFrom-Json
        if (($cur.allowVirtualNetworkAccess -ne $true) -or ($cur.allowForwardedTraffic -ne $true)) {
            Log "Correcting flags on existing peering: $($p.n)"
            $o = az network vnet peering update -g $RG --vnet-name $p.src -n $p.n `
                 --set allowVirtualNetworkAccess=true allowForwardedTraffic=true -o json 2>&1
            if ($LASTEXITCODE -ne 0) { throw "Peering update failed $($p.n): $o" }
            Log-OK "Flags corrected: $($p.n)"
        } else {
            Log-OK "Exists (flags OK): $($p.n)"
        }
        continue
    }
    $rid = az network vnet show -g $RG -n $p.dst --query "id" -o tsv 2>&1
    Log "Peering: $($p.n)"
    $o = az network vnet peering create -g $RG --vnet-name $p.src -n $p.n `
         --remote-vnet $rid --allow-forwarded-traffic --allow-vnet-access -o json 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Peering failed $($p.n): $o" }
    Log-OK "Created: $($p.n)"
}
Save-Output "04-peerings.json" ((az network vnet peering list -g $RG --vnet-name hub1-vnet -o json 2>&1) | Out-String)

# Step 5: VNRAs
Log-Step "Step 5: VNRAs (az rest PUT, scalingBandwidth=50)"
$vnras = @(
    @{n="vnra1"; l="swedencentral"; vnet="hub1-vnet"}
    @{n="vnra2"; l="northeurope";   vnet="hub2-vnet"}
)
foreach ($vnra in $vnras) {
    $url = "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Network/virtualNetworkAppliances/$($vnra.n)?api-version=$API"
    $rs  = az rest --method GET --url $url --query "properties.provisioningState" -o tsv 2>$null
    if ($rs -eq "Succeeded") { Log-OK "Already Succeeded: $($vnra.n)"; continue }
    if ($rs -eq "Creating" -or $rs -eq "Updating") { Log "In-flight, will poll: $($vnra.n)"; continue }
    $sid = "/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Network/virtualNetworks/$($vnra.vnet)/subnets/VirtualNetworkApplianceSubnet"
    # Build JSON body and write to file to avoid Windows arg-passing issues with az rest
    # API 2025-05-01 uses properties.bandwidthInGbps (string) + properties.subnet.id
    # No virtualNetworkApplianceSku field exists in this API version (schema from REST API docs)
    $bodyObj = [ordered]@{
        location   = $vnra.l
        tags       = [ordered]@{lab="true"; created_by="copilot-lab"; correlation_id="vnra-c7e2a3f1"}
        properties = [ordered]@{
            bandwidthInGbps = "50"
            subnet = [ordered]@{id=$sid}
        }
    }
    $bodyJson = $bodyObj | ConvertTo-Json -Depth 6
    $bodyFile = Join-Path $SCRIPT_DIR "$($vnra.n)-body.json"
    $bodyJson | Set-Content -Path $bodyFile -Encoding UTF8
    Log "PUT VNRA $($vnra.n) ($($vnra.l), scalingBandwidth=50)"
    $o = az rest --method PUT --url $url --body "@$bodyFile" -o json 2>&1
    if ($LASTEXITCODE -ne 0) { throw "VNRA PUT failed $($vnra.n): $o" }
    Log-OK "VNRA PUT accepted: $($vnra.n)"
}
Log "Polling VNRA provisioning (may take 2-5 min)..."
$vnra1Obj = Poll-VNRA -Name "vnra1"
$vnra2Obj = Poll-VNRA -Name "vnra2"
$vnra1IP = ($vnra1Obj.properties.ipConfigurations | Where-Object {$_.properties.primary -eq $true} | Select-Object -First 1).properties.privateIPAddress
$vnra2IP = ($vnra2Obj.properties.ipConfigurations | Where-Object {$_.properties.primary -eq $true} | Select-Object -First 1).properties.privateIPAddress
if (-not $vnra1IP) { $vnra1IP = "10.1.0.4" }
if (-not $vnra2IP) { $vnra2IP = "10.2.0.4" }
Log-OK "VNRA1 private IP: $vnra1IP"
Log-OK "VNRA2 private IP: $vnra2IP"
Save-Output "05-vnra1.json" ((az rest --method GET --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Network/virtualNetworkAppliances/vnra1?api-version=$API" -o json 2>&1) | Out-String)
Save-Output "05-vnra2.json" ((az rest --method GET --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Network/virtualNetworkAppliances/vnra2?api-version=$API" -o json 2>&1) | Out-String)

# Step 6: RT Associations
Log-Step "Step 6: Route Table Associations (post-VNRA)"
$assoc = @(
    @{rt="rt-spoke1";    vnet="spoke1-vnet"; snet="vm-subnet"}
    @{rt="rt-spoke2";    vnet="spoke2-vnet"; snet="vm-subnet"}
    @{rt="rt-hub1-vnra"; vnet="hub1-vnet";   snet="VirtualNetworkApplianceSubnet"}
    @{rt="rt-hub2-vnra"; vnet="hub2-vnet";   snet="VirtualNetworkApplianceSubnet"}
)
foreach ($a in $assoc) {
    $cur = az network vnet subnet show -g $RG --vnet-name $a.vnet -n $a.snet --query "routeTable.id" -o tsv 2>$null
    if ($cur -match $a.rt) { Log-OK "Already assoc: $($a.rt)"; continue }
    $rtid = az network route-table show -g $RG -n $a.rt --query "id" -o tsv 2>&1
    Log "Associating $($a.rt) -> $($a.vnet)/$($a.snet)"
    $o = az network vnet subnet update -g $RG --vnet-name $a.vnet -n $a.snet `
         --route-table $rtid -o json 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Assoc failed $($a.rt): $o" }
    Log-OK "Associated: $($a.rt)"
}

# Step 7: Test VMs
Log-Step "Step 7: Test VMs (Standard_B2ts_v2, Ubuntu 22.04, no PIP, no NSG)"
$vms = @(
    @{n="test1-vm"; l="swedencentral"; vnet="spoke1-vnet"; snet="vm-subnet"}
    @{n="test2-vm"; l="northeurope";   vnet="spoke2-vnet"; snet="vm-subnet"}
)
foreach ($vm in $vms) {
    $vs = az vm show -g $RG -n $vm.n --query "provisioningState" -o tsv 2>$null
    if ($vs -eq "Succeeded") { Log-OK "VM exists: $($vm.n)"; continue }
    $nicName = "$($vm.n)VMNic"
    $sid     = "/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Network/virtualNetworks/$($vm.vnet)/subnets/$($vm.snet)"
    $ns = az network nic show -g $RG -n $nicName --query "provisioningState" -o tsv 2>$null
    if ($ns -ne "Succeeded") {
        Log "Creating NIC: $nicName"
        $o = az network nic create -g $RG -n $nicName --location $vm.l `
             --subnet $sid --tags @TAGS_ARR -o json 2>&1
        if ($LASTEXITCODE -ne 0) { throw "NIC failed: ${nicName}: $o" }
        Log-OK "NIC created: $nicName"
    } else {
        Log-OK "NIC exists: $nicName"
    }
    Log "Creating VM: $($vm.n) ($($vm.l))"
    $o = az vm create -g $RG -n $vm.n --location $vm.l `
         --image Ubuntu2204 --size Standard_B2ts_v2 `
         --admin-username azureuser --ssh-key-values $SSH_KEY_PATH `
         --nics $nicName `
         --os-disk-size-gb 32 --storage-sku StandardSSD_LRS `
         --tags @TAGS_ARR -o json 2>&1
    if ($LASTEXITCODE -ne 0) { throw "VM failed: $($vm.n): $o" }
    Log-OK "VM created: $($vm.n)"
    Save-Output "07-$($vm.n)-create.json" ($o | Out-String)
}

# Step 8: Smoke Check
Log-Step "Step 8: Smoke Check"
foreach ($vm in $vms) {
    $s = az vm show -g $RG -n $vm.n --query "provisioningState" -o tsv 2>&1
    if ($s -eq "Succeeded") { Log-OK "VM $($vm.n): Succeeded" } else { Log-Warn "VM $($vm.n): $s" }
}
$v1s = az rest --method GET `
    --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Network/virtualNetworkAppliances/vnra1?api-version=$API" `
    --query "properties.provisioningState" -o tsv 2>&1
$v2s = az rest --method GET `
    --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Network/virtualNetworkAppliances/vnra2?api-version=$API" `
    --query "properties.provisioningState" -o tsv 2>&1
Log-OK "VNRA1: $v1s"
Log-OK "VNRA2: $v2s"
foreach ($a in $assoc) {
    $cur = az network vnet subnet show -g $RG --vnet-name $a.vnet -n $a.snet `
           --query "routeTable.id" -o tsv 2>&1
    $lbl = if ($cur -match $a.rt) {"OK"} else {"MISSING"}
    Log-OK "RT $($a.rt) -> $($a.vnet)/$($a.snet): $lbl"
}

# Step 9: Final outputs
Log-Step "Step 9: Final Outputs"
Save-Output "09-resource-list.json" ((az resource list -g $RG --query "[].{type:type,name:name,location:location}" -o json 2>&1) | Out-String)
Save-Output "09-test1-nic.json" ((az network nic show -g $RG -n test1-vmVMNic --query "{name:name,ip:ipConfigurations[0].privateIPAddress}" -o json 2>&1) | Out-String)
Save-Output "09-test2-nic.json" ((az network nic show -g $RG -n test2-vmVMNic --query "{name:name,ip:ipConfigurations[0].privateIPAddress}" -o json 2>&1) | Out-String)
Save-Output "09-routes-final.json" ((az network route-table list -g $RG --query "[].{n:name,routes:routes[].{p:addressPrefix,nh:nextHopIpAddress,t:nextHopType}}" -o json 2>&1) | Out-String)

# Step 10: Peering Assertions
Log-Step "Step 10: Peering Assertions (post-deploy gate)"
$assertFail = $false
foreach ($p in $peers) {
    $raw = az network vnet peering show -g $RG --vnet-name $p.src -n $p.n -o json 2>&1
    if ($LASTEXITCODE -ne 0) {
        Log-Warn "ASSERT FAIL -- peering not found: $($p.n) on $($p.src)"
        $assertFail = $true; continue
    }
    $pr         = $raw | ConvertFrom-Json
    $vnetAccess = $pr.allowVirtualNetworkAccess
    $fwdTraffic = $pr.allowForwardedTraffic
    $state      = $pr.peeringState
    $sync       = $pr.peeringSyncLevel
    $ok = ($vnetAccess -eq $true) -and ($fwdTraffic -eq $true) -and ($state -eq "Connected") -and ($sync -eq "FullyInSync")
    if ($ok) {
        Log-OK "Peering $($p.n) ($($p.src)): vnetAccess=true fwdTraffic=true $state/$sync"
    } else {
        Log-Warn "ASSERT FAIL -- $($p.n) ($($p.src)): vnetAccess=$vnetAccess fwdTraffic=$fwdTraffic state=$state sync=$sync"
        $assertFail = $true
    }
}
if ($assertFail) { throw "Peering assertion(s) FAILED -- correct flags and rerun." }
Log-OK "All 6 peering assertions passed."

$elapsed = (Get-Date) - $DEPLOY_START
$estr    = "{0:mm}m {0:ss}s" -f $elapsed
Log-Step "DEPLOYMENT COMPLETE"
Log-OK "Elapsed  : $estr"
Log-OK "RG       : $RG"
Log-OK "VNRA1 IP : $vnra1IP"
Log-OK "VNRA2 IP : $vnra2IP"
Log "Next: Niobe runs S1-S5 validation."
@"

=== COMPLETE elapsed=$estr RG=$RG VNRA1=$vnra1IP VNRA2=$vnra2IP corr=$CORR_ID ===
"@ | Add-Content -Path $LOG_FILE -Encoding UTF8



