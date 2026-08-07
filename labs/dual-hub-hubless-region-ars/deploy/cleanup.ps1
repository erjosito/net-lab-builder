<#
.SYNOPSIS
    Cleanup script for dual-hub-hubless-region-ars lab.

.DESCRIPTION
    Deletes lab resources in safe order per manifest §6:
      1  VPN connection objects (4)
      2  ARS BGP peerings — deleted automatically with ARS
      3  ARS instances (3) — 10 min each
      4  VPN gateways (3) — 15-20 min each
      5  VNet peering objects (20)
      6  VMs + NICs + disks (6)
      7  PIPs (9)
      8  RG delete (cascade: VNets, NSGs, route tables)
      9  KV PSK purge (EXPLICIT — NOT covered by RG delete)

    ⚠️ KV purge (Step 9) must run explicitly.
       RG delete does NOT remove secrets from platform-secrets-1138 (separate RG).

.PARAMETER RgName
    Resource group name. Required.

.PARAMETER KvName
    Key Vault name for PSK purge (default: platform-secrets-1138).

.PARAMETER SkipKvPurge
    Skip KV PSK purge (use if PSKs were not written to KV).

.PARAMETER AutoApprove
    Skip confirmation prompts.

.NOTES
    Sub : Resolved via az account show (NOT hardcoded)
    KV  : platform-secrets-1138 / RG platform (separate from lab RG)
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)] [string]$RgName,
    [Parameter()] [string]$KvName       = 'platform-secrets-1138',
    [Parameter()] [switch]$SkipKvPurge,
    [Parameter()] [switch]$AutoApprove
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'

Write-Host ''
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Red
Write-Host " Tank — dual-hub-hubless-region-ars CLEANUP" -ForegroundColor Red
Write-Host " RG: $RgName" -ForegroundColor Red
Write-Host " KV: $KvName" -ForegroundColor Red
Write-Host " Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Red
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Red

if (-not $AutoApprove) {
    $confirm = Read-Host "`nType 'yes' to proceed with cleanup of RG '$RgName'"
    if ($confirm -ne 'yes') { Write-Host 'Aborted.'; exit 0 }
}

# Verify RG exists
$rgCheck = az group show -n $RgName -o json 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warning "RG '$RgName' not found. Nothing to clean up."
    exit 0
}

# ── Step 1: Delete VPN connections ────────────────────────────────────────────
Write-Host ''
Write-Host '[1] Deleting VPN connection objects...' -ForegroundColor Yellow
$connNames = @('conn-hub1-to-onprem', 'conn-onprem-to-hub1', 'conn-hub2-to-onprem', 'conn-onprem-to-hub2')
foreach ($c in $connNames) {
    $exists = az network vpn-connection show -g $RgName -n $c -o none 2>&1
    if ($LASTEXITCODE -eq 0) {
        az network vpn-connection delete -g $RgName -n $c --no-wait -o none
        Write-Host "    Deleting: $c"
    } else {
        Write-Host "    Not found (skip): $c" -ForegroundColor DarkGray
    }
}

# Wait for connections to delete
Write-Host '    Waiting 60s for connection deletes...'
Start-Sleep -Seconds 60

# ── Step 2-3: Delete ARS (BGP peerings deleted automatically) ────────────────
Write-Host ''
Write-Host '[3] Deleting ARS instances (async, ~10 min each)...' -ForegroundColor Yellow
$arsNames = @('ars-hub1', 'ars-hub2', 'ars-poland')
foreach ($a in $arsNames) {
    $exists = az network routeserver show -g $RgName -n $a -o none 2>&1
    if ($LASTEXITCODE -eq 0) {
        az network routeserver delete -g $RgName -n $a --yes --no-wait -o none
        Write-Host "    Deleting (async): $a"
    } else {
        Write-Host "    Not found (skip): $a" -ForegroundColor DarkGray
    }
}

# ── Step 4: Delete VPN gateways ──────────────────────────────────────────────
Write-Host ''
Write-Host '[4] Deleting VPN gateways (async, ~15-20 min each)...' -ForegroundColor Yellow
$gwNames = @('vpngw-hub1', 'vpngw-hub2', 'vpngw-onprem')
foreach ($g in $gwNames) {
    $exists = az network vnet-gateway show -g $RgName -n $g -o none 2>&1
    if ($LASTEXITCODE -eq 0) {
        az network vnet-gateway delete -g $RgName -n $g --no-wait -o none
        Write-Host "    Deleting (async): $g"
    } else {
        Write-Host "    Not found (skip): $g" -ForegroundColor DarkGray
    }
}

Write-Host '    Waiting 30 min for GW + ARS deletes to complete...' -ForegroundColor Yellow
Write-Host '    (Interrupt with Ctrl+C and run Step 8 manually after GWs are gone)'
Start-Sleep -Seconds 1800

# ── Step 5: Delete VNet peerings ─────────────────────────────────────────────
Write-Host ''
Write-Host '[5] Deleting VNet peerings (cascade via RG delete in step 8)...' -ForegroundColor DarkGray
Write-Host '    Peerings will be removed by RG delete in step 8.'

# ── Step 6: Delete VMs ────────────────────────────────────────────────────────
Write-Host ''
Write-Host '[6] Deleting VMs + NICs + disks...' -ForegroundColor Yellow
$vmNames = @('vm-nva1', 'vm-nva2', 'vm-hub1-ep', 'vm-hub2-ep', 'vm-c1-ep', 'vm-onprem-ep')
foreach ($v in $vmNames) {
    $rg_vm = az vm show -g $RgName -n $v --query 'id' -o tsv 2>&1
    if ($LASTEXITCODE -eq 0) {
        az vm delete -g $RgName -n $v --yes --no-wait -o none
        az disk delete -g $RgName -n "osdisk-$v" --yes --no-wait -o none 2>&1 | Out-Null
        az network nic delete -g $RgName -n "nic-$v" --no-wait -o none 2>&1 | Out-Null
        Write-Host "    Deleting: $v"
    } else {
        Write-Host "    Not found (skip): $v" -ForegroundColor DarkGray
    }
}

# ── Step 7: Delete PIPs ───────────────────────────────────────────────────────
Write-Host ''
Write-Host '[7] Deleting Standard PIPs...' -ForegroundColor Yellow
$pipNames = @('pip-gw-hub1-a','pip-gw-hub1-b','pip-gw-hub2-a','pip-gw-hub2-b',
              'pip-gw-onprem-a','pip-gw-onprem-b','pip-ars-hub1','pip-ars-hub2','pip-ars-poland')
foreach ($p in $pipNames) {
    az network public-ip delete -g $RgName -n $p --no-wait -o none 2>&1 | Out-Null
    Write-Host "    Delete queued: $p"
}

# ── Step 8: Delete RG (cascade) ───────────────────────────────────────────────
Write-Host ''
Write-Host '[8] Deleting resource group (cascade)...' -ForegroundColor Yellow
Write-Host "    az group delete -n $RgName --yes --no-wait"
az group delete -n $RgName --yes --no-wait -o none
Write-Host "    RG delete initiated (async)." -ForegroundColor Green

# ── Step 9: KV PSK purge (EXPLICIT — not covered by RG delete) ───────────────
Write-Host ''
if ($SkipKvPurge) {
    Write-Host '[9] Skipping KV PSK purge (--SkipKvPurge).' -ForegroundColor DarkGray
} else {
    Write-Host '[9] Purging PSK secrets from KV (platform-secrets-1138, separate RG)...' -ForegroundColor Yellow
    Write-Host '    ⚠️ RG delete does NOT remove KV secrets. This step is mandatory.' -ForegroundColor Yellow

    $pskSecrets = @('psk-hub1-onprem', 'psk-hub2-onprem')
    foreach ($s in $pskSecrets) {
        $secCheck = az keyvault secret show --vault-name $KvName --name $s -o none 2>&1
        if ($LASTEXITCODE -eq 0) {
            az keyvault secret delete --vault-name $KvName --name $s -o none
            Write-Host "    Soft-deleted: $s"
            Start-Sleep -Seconds 5
            az keyvault secret purge --vault-name $KvName --name $s -o none
            Write-Host "    Purged: $s" -ForegroundColor Green
        } else {
            Write-Host "    Not found (skip): $s" -ForegroundColor DarkGray
        }
    }
}

Write-Host ''
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Green
Write-Host ' Cleanup initiated. Async operations still running.' -ForegroundColor Green
Write-Host " RG '$RgName' will be deleted in background." -ForegroundColor Green
Write-Host ' Poll with: az group show -n <rg> --query provisioningState' -ForegroundColor Green
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Green
