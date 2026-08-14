<#
.SYNOPSIS
    Cleanup script for foundry-agent-reserved-prefix-reachability lab.

.DESCRIPTION
    Default mode: DRY RUN — lists resources and shows what would be deleted.
    Pass -AutoApprove to execute deletion.

    Deletion order (safe sequence):
      1  VPN connections (2 objects)
      2  VPN gateways (2 × VpnGw1AZ, ~15-20 min each)
      3  VMs + NICs + OS disks (3)
      4  Private endpoints (3)
      5  RG delete cascade (VNets, NSGs, PIPs, Search, Storage, Cosmos, DNS zones, subnets)
      6  KV PSK purge (explicit, if -KvName provided)

    ⚠️  Step 5 (RG delete) permanently removes all lab resources.
    ⚠️  Step 6 must run explicitly; KV secrets survive RG delete.

.PARAMETER RgName
    Resource group name (required).

.PARAMETER AutoApprove
    Skip confirmation prompt and execute deletion.

.PARAMETER KvName
    Key Vault name for PSK secret purge (optional).

.PARAMETER CorrelationId
    Correlation ID used when naming the PSK secret (optional).

.NOTES
    Lab : foundry-agent-reserved-prefix-reachability
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$RgName,
    [Parameter()] [switch]$AutoApprove,
    [Parameter()] [string]$KvName = '',
    [Parameter()] [string]$CorrelationId = ''
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'

Write-Host ''
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Red
Write-Host " Tank — foundry-agent-reserved-prefix-reachability CLEANUP" -ForegroundColor Red
Write-Host " RG    : $RgName" -ForegroundColor Red
Write-Host " Mode  : $(if ($AutoApprove) { 'AUTO-APPROVE' } else { 'DRY RUN' })" -ForegroundColor Red
Write-Host " Date  : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Red
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Red

# Verify RG exists
$rgCheck = az group show -n $RgName -o json 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "RG '$RgName' not found — nothing to clean up." -ForegroundColor Yellow
    exit 0
}

# DRY RUN: list resources and exit
if (-not $AutoApprove) {
    Write-Host ''
    Write-Host 'DRY RUN — listing resources that would be deleted:' -ForegroundColor Yellow
    az resource list -g $RgName --query '[].{name:name, type:type, location:location}' -o table
    Write-Host ''
    Write-Host 'Re-run with -AutoApprove to execute deletion.' -ForegroundColor Yellow
    Write-Host 'Example: .\cleanup.ps1 -RgName <rg> -AutoApprove'
    exit 0
}

# Confirm
Write-Host ''
$confirm = Read-Host "Type 'yes' to DELETE all resources in '$RgName'"
if ($confirm -ne 'yes') { Write-Host 'Aborted.'; exit 0 }

# ── Step 1: Delete VPN connections ────────────────────────────────────────────
Write-Host ''
Write-Host '[1] Deleting VPN connections...' -ForegroundColor Yellow
$connNames = @('conn-foundry-to-onprem', 'conn-onprem-to-foundry')
foreach ($c in $connNames) {
    $chk = az network vpn-connection show -g $RgName -n $c -o none 2>&1
    if ($LASTEXITCODE -eq 0) {
        az network vpn-connection delete -g $RgName -n $c --no-wait -o none
        Write-Host "    Deleting: $c"
    } else {
        Write-Host "    Not found (skip): $c" -ForegroundColor DarkGray
    }
}
Write-Host '    Waiting 60s for connection deletes...'
Start-Sleep -Seconds 60

# ── Step 2: Delete VPN gateways (~15-20 min each) ─────────────────────────────
Write-Host ''
Write-Host '[2] Deleting VPN gateways (async, ~20 min)...' -ForegroundColor Yellow
$gwNames = @('vpngw-foundry', 'vpngw-onprem')
foreach ($g in $gwNames) {
    $chk = az network vnet-gateway show -g $RgName -n $g -o none 2>&1
    if ($LASTEXITCODE -eq 0) {
        az network vnet-gateway delete -g $RgName -n $g --no-wait -o none
        Write-Host "    Deleting (async): $g"
    } else {
        Write-Host "    Not found (skip): $g" -ForegroundColor DarkGray
    }
}
Write-Host '    Waiting 25 min for GW deletes...' -ForegroundColor Yellow
Write-Host '    (Ctrl+C to interrupt; run Step 5 manually after GWs are gone)'
Start-Sleep -Seconds 1500

# ── Step 3: Delete VMs + NICs + disks ─────────────────────────────────────────
Write-Host ''
Write-Host '[3] Deleting VMs + NICs + OS disks...' -ForegroundColor Yellow
$vmNames = @('vm-onprem-echo', 'vm-onprem-ctrl', 'vm-diag')
foreach ($v in $vmNames) {
    $chk = az vm show -g $RgName -n $v -o none 2>&1
    if ($LASTEXITCODE -eq 0) {
        az vm delete -g $RgName -n $v --yes --no-wait -o none
        az disk delete -g $RgName -n "osdisk-$v" --yes --no-wait -o none 2>&1 | Out-Null
        az network nic delete -g $RgName -n "nic-$v" --no-wait -o none 2>&1 | Out-Null
        Write-Host "    Deleting: $v"
    } else {
        Write-Host "    Not found (skip): $v" -ForegroundColor DarkGray
    }
}

# ── Step 4: Delete private endpoints ──────────────────────────────────────────
Write-Host ''
Write-Host '[4] Deleting private endpoints...' -ForegroundColor Yellow
$peNames = @('pe-storage-blob', 'pe-search', 'pe-cosmos')
foreach ($p in $peNames) {
    $chk = az network private-endpoint show -g $RgName -n $p -o none 2>&1
    if ($LASTEXITCODE -eq 0) {
        az network private-endpoint delete -g $RgName -n $p --no-wait -o none
        Write-Host "    Deleting: $p"
    } else {
        Write-Host "    Not found (skip): $p" -ForegroundColor DarkGray
    }
}
Start-Sleep -Seconds 30

# ── Step 5: Delete RG (cascade) ───────────────────────────────────────────────
Write-Host ''
Write-Host '[5] Deleting resource group (cascade all remaining resources)...' -ForegroundColor Yellow
az group delete -n $RgName --yes --no-wait -o none
Write-Host "    RG delete initiated (async): $RgName" -ForegroundColor Green

# ── Step 6: KV PSK purge (optional) ───────────────────────────────────────────
Write-Host ''
if ($KvName) {
    if (-not $CorrelationId) {
        throw '-CorrelationId is required when -KvName is supplied so the exact PSK secret can be purged.'
    }
    Write-Host '[6] Purging PSK secret from Key Vault...' -ForegroundColor Yellow
    $secretName = "psk-foundry-onprem-$CorrelationId"
    $chk = az keyvault secret show --vault-name $KvName --name $secretName -o none 2>&1
    if ($LASTEXITCODE -eq 0) {
        az keyvault secret delete --vault-name $KvName --name $secretName -o none
        Write-Host "    Soft-deleted: $secretName"
        Start-Sleep -Seconds 5
        az keyvault secret purge --vault-name $KvName --name $secretName -o none
        Write-Host "    Purged: $secretName" -ForegroundColor Green
    } else {
        Write-Host "    Not found (skip): $secretName" -ForegroundColor DarkGray
    }
} else {
    Write-Host '[6] Skipping KV purge (-KvName not provided).' -ForegroundColor DarkGray
}

Write-Host ''
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Green
Write-Host ' Cleanup initiated. Async operations still running.' -ForegroundColor Green
Write-Host " Poll: az group show -n $RgName --query provisioningState" -ForegroundColor Green
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Green
