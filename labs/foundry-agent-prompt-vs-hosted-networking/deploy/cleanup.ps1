<#
.SYNOPSIS
    T2-ONLY teardown: deletes VPN/on-prem resources from the sibling lab.
    NEVER deletes shared Foundry infrastructure or T1 resources.

.DESCRIPTION
    Default mode: PREVIEW ONLY -- lists exact T2-scoped resources and shows what would be
    deleted. No deletion occurs unless -Delete is explicitly specified AND the exact
    confirmation phrase "DELETE APPROVED" is typed at the prompt.

    T2 resource scope (ONLY these resources are touched):
      conn-foundry-to-onprem, conn-onprem-to-foundry (VPN connections)
      vpngw-foundry, vpngw-onprem (VPN gateways; ~5 min each to delete)
      pip-vpngw-foundry, pip-vpngw-onprem (Standard PIPs)
      vm-onprem-echo + nic-vm-onprem-echo + osdisk-vm-onprem-echo
      vm-onprem-ctrl + nic-vm-onprem-ctrl + osdisk-vm-onprem-ctrl
      nsg-echo-vms
      vnet-onprem
      NSG rules for 172.30.100.0/24 and 10.200.100.0/24 on nsg-agentsubnet

    Resources NOT touched (shared Foundry infrastructure -- must survive):
      vnet-foundry (all subnets), vm-diag, nsg-mgmt,
      Foundry account/project/model, AI Search, Cosmos DB, Storage,
      private endpoints x5, private DNS zones x6,
      DNS Private Resolver (if deployed), GatewaySubnet (kept empty).
      vnet-tools, vm-tools-echo, vm-tools-ctrl (T1 resources, if deployed).

    Dependency-safe deletion order:
      1  VPN connections (~60 s to reach Disconnected)
      2  VPN gateways (~5-10 min each; both async in parallel)
      3  PIPs (after GWs confirmed deleted)
      4  VMs + NICs + OS disks (vm-onprem-echo, vm-onprem-ctrl)
      5  nsg-echo-vms + vnet-onprem
      6  Stale NSG rules on nsg-agentsubnet (172.30.x.x and 10.200.x.x)

.PARAMETER RgName
    Resource group name (REQUIRED).

.PARAMETER Delete
    Switch: execute deletion. Without this, only the resource listing/preview runs.
    Requires Gate A confirmation ("DELETE APPROVED") from Jose Moreno.

.PARAMETER NsgAgentSubnetName
    Name of the AgentSubnet NSG to clean stale outbound rules from (default: nsg-agentsubnet).

.NOTES
    Lab  : foundry-agent-prompt-vs-hosted-networking (T2 cleanup, T1 predecessor)
    Gate A: Jose Moreno must state "DELETE APPROVED" before -Delete is used.
    Do NOT use the sibling lab's cleanup.ps1 with -AutoApprove -- it deletes vm-diag and shared PEs.
    Evidence preservation (pre-teardown JSON files) must be committed BEFORE running -Delete.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$RgName,
    [Parameter()] [switch]$Delete,
    [Parameter()] [string]$NsgAgentSubnetName = 'nsg-agentsubnet'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'

# Exact T2 resource names -- only these will be touched
$T2VpnConns = @('conn-foundry-to-onprem', 'conn-onprem-to-foundry')
$T2VpnGws   = @('vpngw-foundry', 'vpngw-onprem')
$T2Pips     = @('pip-vpngw-foundry', 'pip-vpngw-onprem')
$T2Vms      = @('vm-onprem-echo', 'vm-onprem-ctrl')
$T2Nsg      = 'nsg-echo-vms'
$T2Vnet     = 'vnet-onprem'
# Approximate rule names; script identifies them by destination prefix
$T2NsgRuleDestinations = @('172.30.100.0/24', '10.200.100.0/24')

Write-Host ''
Write-Host '==============================================================' -ForegroundColor Red
Write-Host ' Tank -- T2 Teardown (VPN/on-prem resources only)' -ForegroundColor Red
Write-Host " RG   : $RgName" -ForegroundColor Red
Write-Host " Mode : $(if ($Delete) { 'DELETE (execute)' } else { 'PREVIEW ONLY' })" -ForegroundColor Red
Write-Host " Date : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Red
Write-Host '==============================================================' -ForegroundColor Red

# Verify subscription and RG
$subJson = az account show -o json 2>&1
if ($LASTEXITCODE -ne 0) { throw "az account show failed. Run 'az login' first." }
$subInfo = $subJson | ConvertFrom-Json
Write-Host "    Subscription: $($subInfo.name)" -ForegroundColor Green

$rgCheck = az group show -n $RgName -o json 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "RG '$RgName' not found -- nothing to clean up." -ForegroundColor Yellow
    exit 0
}

# ---- PREVIEW: resolve exact T2 resources and stale NSG rules ----------------

Write-Host ''
Write-Host 'T2 Resource Inventory (what would be deleted):' -ForegroundColor Yellow
Write-Host '  VPN connections:' -ForegroundColor Cyan
foreach ($c in $T2VpnConns) {
    $res = az network vpn-connection show -g $RgName -n $c -o json 2>&1
    if ($LASTEXITCODE -eq 0) {
        $r = $res | ConvertFrom-Json
        Write-Host "    [FOUND]   $c  state=$($r.connectionStatus)" -ForegroundColor White
    } else {
        Write-Host "    [missing] $c" -ForegroundColor DarkGray
    }
}

Write-Host '  VPN gateways:' -ForegroundColor Cyan
foreach ($g in $T2VpnGws) {
    $res = az network vnet-gateway show -g $RgName -n $g -o json 2>&1
    if ($LASTEXITCODE -eq 0) {
        $r = $res | ConvertFrom-Json
        Write-Host "    [FOUND]   $g  sku=$($r.sku.name)  state=$($r.provisioningState)" -ForegroundColor White
    } else {
        Write-Host "    [missing] $g" -ForegroundColor DarkGray
    }
}

Write-Host '  Public IPs:' -ForegroundColor Cyan
foreach ($p in $T2Pips) {
    $res = az network public-ip show -g $RgName -n $p -o json 2>&1
    if ($LASTEXITCODE -eq 0) {
        $r = $res | ConvertFrom-Json
        Write-Host "    [FOUND]   $p  ip=$($r.ipAddress)" -ForegroundColor White
    } else {
        Write-Host "    [missing] $p" -ForegroundColor DarkGray
    }
}

Write-Host '  VMs + NICs + disks:' -ForegroundColor Cyan
foreach ($v in $T2Vms) {
    $vmRes = az vm show -g $RgName -n $v -o json 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    [FOUND]   $v  (will also delete nic-$v, osdisk-$v)" -ForegroundColor White
    } else {
        Write-Host "    [missing] $v" -ForegroundColor DarkGray
    }
}

Write-Host '  NSG (T2 subnet NSG):' -ForegroundColor Cyan
$nsgRes = az network nsg show -g $RgName -n $T2Nsg -o json 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "    [FOUND]   $T2Nsg" -ForegroundColor White
} else {
    Write-Host "    [missing] $T2Nsg" -ForegroundColor DarkGray
}

Write-Host '  VNet (on-prem simulator):' -ForegroundColor Cyan
$vnetRes = az network vnet show -g $RgName -n $T2Vnet -o json 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "    [FOUND]   $T2Vnet" -ForegroundColor White
} else {
    Write-Host "    [missing] $T2Vnet" -ForegroundColor DarkGray
}

Write-Host '  Stale NSG rules on nsg-agentsubnet (by destination):' -ForegroundColor Cyan
$nsgAgentRes = az network nsg show -g $RgName -n $NsgAgentSubnetName --query 'securityRules' -o json 2>&1
if ($LASTEXITCODE -eq 0) {
    $rules = $nsgAgentRes | ConvertFrom-Json
    foreach ($dest in $T2NsgRuleDestinations) {
        $stale = $rules | Where-Object {
            ($_.properties.destinationAddressPrefix -eq $dest) -and ($_.properties.direction -eq 'Outbound')
        }
        if ($stale) {
            foreach ($sr in $stale) { Write-Host "    [STALE]   $($sr.name)  dest=$dest" -ForegroundColor White }
        } else {
            Write-Host "    [clean]   no outbound rule for $dest" -ForegroundColor DarkGray
        }
    }
} else {
    Write-Host "    nsg-agentsubnet '$NsgAgentSubnetName' not found or inaccessible." -ForegroundColor DarkGray
}

if (-not $Delete) {
    Write-Host ''
    Write-Host '==============================================================' -ForegroundColor Yellow
    Write-Host ' PREVIEW ONLY -- no resources deleted.' -ForegroundColor Yellow
    Write-Host ' Gate A: Jose must state "DELETE APPROVED" in squad conversation,' -ForegroundColor Yellow
    Write-Host ' then re-run with -Delete flag.' -ForegroundColor Yellow
    Write-Host " Example: .\cleanup.ps1 -RgName $RgName -Delete" -ForegroundColor Yellow
    Write-Host '==============================================================' -ForegroundColor Yellow
    exit 0
}

# =============================================================================
# DELETE -- runs only when -Delete is passed
# Gate A: Jose Moreno must have stated "DELETE APPROVED" before this runs.
# =============================================================================

Write-Host ''
Write-Host '==============================================================' -ForegroundColor Red
Write-Host ' DELETE -- About to remove T2 VPN/on-prem resources' -ForegroundColor Red
Write-Host ' Shared Foundry infra (vnet-foundry, vm-diag, PEs, etc.) is PRESERVED.' -ForegroundColor Red
Write-Host ' Gate A (DELETE APPROVED) must be on record.' -ForegroundColor Red
Write-Host '==============================================================' -ForegroundColor Red
Write-Host ''
$confirm = Read-Host "Type exactly 'DELETE APPROVED' to proceed"
if ($confirm -ne 'DELETE APPROVED') {
    Write-Host 'Confirmation phrase did not match. Aborted -- no resources deleted.' -ForegroundColor Yellow
    exit 0
}

# ---- Step 1: VPN connections ------------------------------------------------
Write-Host ''
Write-Host '[1] Deleting VPN connections...' -ForegroundColor Yellow
foreach ($c in $T2VpnConns) {
    $chk = az network vpn-connection show -g $RgName -n $c -o none 2>&1
    if ($LASTEXITCODE -eq 0) {
        az network vpn-connection delete -g $RgName -n $c --no-wait -o none
        Write-Host "    Deleting (async): $c"
    } else {
        Write-Host "    Not found (skip): $c" -ForegroundColor DarkGray
    }
}
Write-Host '    Waiting 60s for connections to reach Disconnected...'
Start-Sleep -Seconds 60

# ---- Step 2: VPN gateways (~5-10 min each; parallel async) ------------------
Write-Host ''
Write-Host '[2] Deleting VPN gateways (async; ~5-10 min each)...' -ForegroundColor Yellow
foreach ($g in $T2VpnGws) {
    $chk = az network vnet-gateway show -g $RgName -n $g -o none 2>&1
    if ($LASTEXITCODE -eq 0) {
        az network vnet-gateway delete -g $RgName -n $g --no-wait -o none
        Write-Host "    Deleting (async): $g"
    } else {
        Write-Host "    Not found (skip): $g" -ForegroundColor DarkGray
    }
}
Write-Host '    Polling until both VPN GWs are gone (up to 15 min)...' -ForegroundColor Yellow
$timeout = (Get-Date).AddMinutes(15)
do {
    Start-Sleep -Seconds 30
    $pending = @()
    foreach ($g in $T2VpnGws) {
        $s = az network vnet-gateway show -g $RgName -n $g --query provisioningState -o tsv 2>&1
        if ($LASTEXITCODE -eq 0) { $pending += $g }
    }
    if ($pending.Count -gt 0) {
        Write-Host "    Still deleting: $($pending -join ', ')  ($(Get-Date -Format 'HH:mm:ss'))"
    }
} while ($pending.Count -gt 0 -and (Get-Date) -lt $timeout)

if ($pending.Count -gt 0) {
    Write-Warning "Timeout waiting for VPN GW deletion: $($pending -join ', '). Continue polling manually."
} else {
    Write-Host '    VPN gateways deleted.' -ForegroundColor Green
}

# ---- Step 3: PIPs -----------------------------------------------------------
Write-Host ''
Write-Host '[3] Deleting Standard PIPs...' -ForegroundColor Yellow
foreach ($p in $T2Pips) {
    $chk = az network public-ip show -g $RgName -n $p -o none 2>&1
    if ($LASTEXITCODE -eq 0) {
        az network public-ip delete -g $RgName -n $p --no-wait -o none
        Write-Host "    Deleting: $p"
    } else {
        Write-Host "    Not found (skip): $p" -ForegroundColor DarkGray
    }
}
Start-Sleep -Seconds 15

# ---- Step 4: VMs + NICs + OS disks ------------------------------------------
Write-Host ''
Write-Host '[4] Deleting VMs + NICs + OS disks...' -ForegroundColor Yellow
foreach ($v in $T2Vms) {
    $chk = az vm show -g $RgName -n $v -o none 2>&1
    if ($LASTEXITCODE -eq 0) {
        az vm delete -g $RgName -n $v --yes --no-wait -o none
        Write-Host "    Deleting VM: $v"
    } else {
        Write-Host "    Not found (skip VM): $v" -ForegroundColor DarkGray
    }
    # NICs and disks may have deleteOption=Delete on them; try explicit delete as safety net
    az network nic delete -g $RgName -n "nic-$v" --no-wait -o none 2>&1 | Out-Null
    az disk delete -g $RgName -n "osdisk-$v" --yes --no-wait -o none 2>&1 | Out-Null
}
Write-Host '    Waiting 60s for VM deletes...'
Start-Sleep -Seconds 60

# ---- Step 5: NSG and VNet ---------------------------------------------------
Write-Host ''
Write-Host '[5] Deleting nsg-echo-vms and vnet-onprem...' -ForegroundColor Yellow
$chk = az network nsg show -g $RgName -n $T2Nsg -o none 2>&1
if ($LASTEXITCODE -eq 0) {
    az network nsg delete -g $RgName -n $T2Nsg -o none
    Write-Host "    Deleted: $T2Nsg" -ForegroundColor Green
} else {
    Write-Host "    Not found (skip): $T2Nsg" -ForegroundColor DarkGray
}

$chk = az network vnet show -g $RgName -n $T2Vnet -o none 2>&1
if ($LASTEXITCODE -eq 0) {
    az network vnet delete -g $RgName -n $T2Vnet -o none
    Write-Host "    Deleted: $T2Vnet" -ForegroundColor Green
} else {
    Write-Host "    Not found (skip): $T2Vnet" -ForegroundColor DarkGray
}

# ---- Step 6: Remove stale NSG rules from nsg-agentsubnet --------------------
Write-Host ''
Write-Host "[6] Removing stale outbound rules from '$NsgAgentSubnetName'..." -ForegroundColor Yellow
$nsgAgentRes = az network nsg show -g $RgName -n $NsgAgentSubnetName --query 'securityRules' -o json 2>&1
if ($LASTEXITCODE -eq 0) {
    $rules = $nsgAgentRes | ConvertFrom-Json
    foreach ($dest in $T2NsgRuleDestinations) {
        $stale = $rules | Where-Object {
            ($_.properties.destinationAddressPrefix -eq $dest) -and ($_.properties.direction -eq 'Outbound')
        }
        foreach ($sr in $stale) {
            az network nsg rule delete -g $RgName --nsg-name $NsgAgentSubnetName -n $sr.name -o none
            Write-Host "    Deleted rule: $($sr.name) (dest $dest)" -ForegroundColor Green
        }
        if (-not $stale) {
            Write-Host "    No stale rule for $dest (already clean)." -ForegroundColor DarkGray
        }
    }
} else {
    Write-Host "    '$NsgAgentSubnetName' not found -- skipping rule cleanup." -ForegroundColor DarkGray
}

Write-Host ''
Write-Host '==============================================================' -ForegroundColor Green
Write-Host ' T2 teardown complete.' -ForegroundColor Green
Write-Host ' Poll async operations:' -ForegroundColor Green
Write-Host "   az resource list -g $RgName --query `"[?contains('$($T2VpnGws + $T2Vms -join ','),name)].name`" -o tsv" -ForegroundColor Green
Write-Host '==============================================================' -ForegroundColor Green