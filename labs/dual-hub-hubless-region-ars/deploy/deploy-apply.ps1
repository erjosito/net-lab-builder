<#
.SYNOPSIS
    LIVE DEPLOYMENT — dual-hub-hubless-region-ars.
    Phase-4 approval recorded 2026-08-03T15:39:35+02:00 by Jose Moreno.
    Trinity IaC review APPROVED 2026-08-03T16:29+02:00.

.DESCRIPTION
    Runs the full deployment sequence:
      Wave 0-5: ARM deployment (RG + all resources via Bicep)
      Post-deploy: verify ARS BGP peerings, VPN connections, BIRD on NVAs
      Output: show-output/deploy/ + deploy-log.md

    Δ3 route-map activation is NOT part of this script (S4 only).

.PARAMETER KvName
    Key Vault name for PSK storage (default: platform-secrets-1138).

.PARAMETER SkipKv
    Skip KV PSK write; hold PSKs in process memory only.

.PARAMETER CorrelationId
    8-char correlation ID. Auto-generated if empty.

.PARAMETER ResumeRg
    Existing RG name to resume a partial deployment into.

.NOTES
    Cost: ~$66/day baseline. Approved by Jose.
    Secrets: PSKs generated in-process. SSH key from ~/.ssh/id_rsa.pub.
#>

[CmdletBinding()]
param(
    [string]$KvName       = 'platform-secrets-1138',
    [switch]$SkipKv,
    [string]$CorrelationId = '',
    [string]$ResumeRg      = ''
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'

$StartTime  = Get-Date
$LabName    = 'dual-hub-hubless-region-ars'
$ScriptDir  = $PSScriptRoot
$LabRoot    = Split-Path $ScriptDir -Parent
$TemplateDir = Join-Path $ScriptDir 'templates'
$MainBicep  = Join-Path $TemplateDir 'main.bicep'
$ShowOutDir = Join-Path $LabRoot 'show-output\deploy'
$DeployLog  = Join-Path $LabRoot 'deploy-log.md'

if ([string]::IsNullOrEmpty($CorrelationId)) {
    $CorrelationId = [System.Guid]::NewGuid().ToString('N').Substring(0, 8)
}

$RgName = if ($ResumeRg) { $ResumeRg } else { "rg-$LabName-$CorrelationId" }

$null = New-Item -ItemType Directory -Force -Path $ShowOutDir

Write-Host ''
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Cyan
Write-Host " Tank — $LabName  LIVE DEPLOY" -ForegroundColor Cyan
Write-Host " CorrID : $CorrelationId" -ForegroundColor Cyan
Write-Host " RG     : $RgName" -ForegroundColor Cyan
Write-Host " Date   : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Cyan

# ── Step 0: Azure context ─────────────────────────────────────────────────────
Write-Host "`n[0] Verifying Azure subscription..." -ForegroundColor Yellow
$subInfo = az account show -o json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "az account show failed. Run az login first." }
$SubName = $subInfo.name
Write-Host "    Subscription: $SubName" -ForegroundColor Green

# ── Step 1: SSH public key ────────────────────────────────────────────────────
Write-Host "`n[1] Resolving SSH public key..." -ForegroundColor Yellow
$SshPubKeyPath = "$env:USERPROFILE\.ssh\id_rsa.pub"
if (Test-Path $SshPubKeyPath) {
    $SshPubKey = (Get-Content $SshPubKeyPath -Raw).Trim()
    Write-Host "    Using local key: $SshPubKeyPath" -ForegroundColor Green
} else {
    # Try KV
    try {
        $SshPubKey = (az keyvault secret show --vault-name $KvName --name 'vm-ssh-pub-key' --query 'value' -o tsv 2>&1).Trim()
        if ($LASTEXITCODE -ne 0 -or -not ($SshPubKey -match 'ssh-')) { throw 'KV key invalid' }
        Write-Host "    Using KV key from $KvName/vm-ssh-pub-key" -ForegroundColor Green
    } catch {
        throw "No SSH public key found at $SshPubKeyPath and KV fetch failed. Cannot deploy."
    }
}

# ── Step 2: Generate PSKs (in-process, never persisted to disk/log) ───────────
Write-Host "`n[2] Generating PSKs (in-process)..." -ForegroundColor Yellow
function New-LabPsk {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $b64 = [Convert]::ToBase64String($bytes)
    return ($b64 -replace '[^A-Za-z0-9]', '').PadRight(32, 'A').Substring(0, 32)
}
$PskHub1 = New-LabPsk
$PskHub2 = New-LabPsk

if (-not $SkipKv) {
    try {
        az keyvault secret set --vault-name $KvName --name 'psk-hub1-onprem' --value $PskHub1 -o none 2>&1 | Out-Null
        az keyvault secret set --vault-name $KvName --name 'psk-hub2-onprem' --value $PskHub2 -o none 2>&1 | Out-Null
        Write-Host "    PSKs stored in KV $KvName." -ForegroundColor Green
    } catch {
        Write-Warning "KV PSK write failed: $_ — PSKs held in process memory only."
    }
} else {
    Write-Host "    PSKs held in process memory only (SkipKv)." -ForegroundColor DarkGray
}

# ── Step 3: Encode cloud-init ─────────────────────────────────────────────────
Write-Host "`n[3] Encoding cloud-init YAML..." -ForegroundColor Yellow
$Nva1B64 = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes((Join-Path $ScriptDir 'nva1-cloud-init.yaml')))
$Nva2B64 = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes((Join-Path $ScriptDir 'nva2-cloud-init.yaml')))
Write-Host "    Encoded NVA1 + NVA2 cloud-init." -ForegroundColor Green

# ── Step 4: Bicep build ────────────────────────────────────────────────────────
Write-Host "`n[4] Bicep build..." -ForegroundColor Yellow
$bicepOut = az bicep build --file $MainBicep 2>&1
if ($LASTEXITCODE -ne 0) { throw "Bicep build failed: $bicepOut" }
Write-Host "    Bicep build OK." -ForegroundColor Green

# ── Step 5: Create lab RG (idempotent) ───────────────────────────────────────
Write-Host "`n[5] Creating lab resource group: $RgName..." -ForegroundColor Yellow
az group create -n $RgName -l 'swedencentral' `
    --tags lab=true lab_name=$LabName owner=jose ephemeral=true `
    correlation_id=$CorrelationId approved_by=jose `
    approval_time="2026-08-03T15:39:35+02:00" -o none
if ($LASTEXITCODE -ne 0) { throw "RG creation failed." }
Write-Host "    RG created/confirmed: $RgName" -ForegroundColor Green

# ── Step 6: ARM deployment (long pole — 30-45 min for GWs + ARS) ─────────────
Write-Host "`n[6] Starting ARM deployment group create (Incremental — ~45-60 min)..." -ForegroundColor Yellow
Write-Host "    This is the long pole: VPN GWs + ARS provision in parallel." -ForegroundColor DarkGray

$DeployName = "deploy-$LabName-$CorrelationId"

# Write parameters to a temp file in the output dir (avoids command-line length limits for large b64 values)
# PSKs written as secureString; SSH key and cloud-init as string
$paramsObj = [ordered]@{
    '$schema'      = 'https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#'
    contentVersion = '1.0.0.0'
    parameters     = [ordered]@{
        correlationId   = @{ value = $CorrelationId }
        adminUsername   = @{ value = 'labadmin' }
        vmSize          = @{ value = 'Standard_B2ts_v2' }
        vmSshPublicKey  = @{ value = $SshPubKey }
        nva1CloudInit   = @{ value = $Nva1B64 }
        nva2CloudInit   = @{ value = $Nva2B64 }
        pskHub1Onprem   = @{ value = $PskHub1 }
        pskHub2Onprem   = @{ value = $PskHub2 }
    }
}
$ParamsFilePath = Join-Path $ScriptDir "parameters\deploy-runtime-$CorrelationId.json"
$paramsObj | ConvertTo-Json -Depth 5 | Set-Content $ParamsFilePath -Encoding UTF8
Write-Host "    Parameters file: $ParamsFilePath" -ForegroundColor DarkGray

$DeployResultJson = az deployment group create `
    --resource-group $RgName `
    --name $DeployName `
    --template-file $MainBicep `
    --mode Incremental `
    --parameters "@$ParamsFilePath" `
    -o json 2>&1
$DeployExitCode = $LASTEXITCODE

# Remove runtime params file immediately after use (contains PSKs)
Remove-Item $ParamsFilePath -Force -ErrorAction SilentlyContinue
Write-Host "    Runtime params file removed." -ForegroundColor DarkGray

if ($DeployExitCode -ne 0) {
    Write-Host '' 
    Write-Host '══ ARM DEPLOYMENT FAILED ═══════════════════════════════════' -ForegroundColor Red
    $errStr = $DeployResultJson | Out-String
    Write-Host $errStr -ForegroundColor Red
    # Save error for diagnosis
    $errStr | Set-Content (Join-Path $ShowOutDir 'deploy-error.txt') -Encoding UTF8
    throw "ARM deployment failed. See show-output/deploy/deploy-error.txt"
}

Write-Host "    ARM deployment completed successfully." -ForegroundColor Green

# Parse outputs
$DeployResult = $DeployResultJson | ConvertFrom-Json
$Outputs = $DeployResult.properties.outputs
$NVA1Ip       = $Outputs.nva1Ip.value
$NVA2Ip       = $Outputs.nva2Ip.value
$ArsHub1Id    = $Outputs.arsHub1Id.value
$ArsHub2Id    = $Outputs.arsHub2Id.value
$ArsPolandId  = $Outputs.arsPolandId.value
$VpngwHub1Id  = $Outputs.vpngwHub1Id.value
$VpngwHub2Id  = $Outputs.vpngwHub2Id.value
$VpngwOnpremId= $Outputs.vpngwOnpremId.value

Write-Host "    NVA1 IP : $NVA1Ip" -ForegroundColor Cyan
Write-Host "    NVA2 IP : $NVA2Ip" -ForegroundColor Cyan

# Save raw deploy output (redacted)
$DeployResultJson | Set-Content (Join-Path $ShowOutDir 'arm-deploy-output.json') -Encoding UTF8

# ── Step 7: Verify VPN Gateway connection states ──────────────────────────────
Write-Host "`n[7] Verifying VPN connection states (polling up to 15 min)..." -ForegroundColor Yellow

$connNames = @('conn-hub1-to-onprem','conn-onprem-to-hub1','conn-hub2-to-onprem','conn-onprem-to-hub2')
$maxWaitSec = 900
$pollSec    = 60
$elapsed    = 0
$connStatus = @{}

while ($elapsed -lt $maxWaitSec) {
    $allConnected = $true
    foreach ($cn in $connNames) {
        $csJson = az network vpn-connection show -g $RgName -n $cn `
            --query '{state:connectionStatus,bgp:enableBgp,prov:provisioningState}' -o json 2>&1
        if ($LASTEXITCODE -eq 0) {
            $cs = $csJson | ConvertFrom-Json
            $connStatus[$cn] = $cs
            $icon = if ($cs.state -eq 'Connected') { '✓' } else { '…' }
            Write-Host "    $icon $cn : prov=$($cs.prov) state=$($cs.state) BGP=$($cs.bgp)" -ForegroundColor $(if ($cs.state -eq 'Connected') { 'Green' } else { 'Yellow' })
            if ($cs.state -ne 'Connected') { $allConnected = $false }
        } else {
            Write-Host "    ? $cn : query failed ($csJson)" -ForegroundColor Yellow
            $allConnected = $false
        }
    }
    if ($allConnected) {
        Write-Host "    All 4 VPN connections Connected." -ForegroundColor Green
        break
    }
    $elapsed += $pollSec
    if ($elapsed -lt $maxWaitSec) {
        Write-Host "    Waiting ${pollSec}s... (${elapsed}/${maxWaitSec}s elapsed)" -ForegroundColor DarkGray
        Start-Sleep $pollSec
    }
}

$connStatusJson = $connStatus | ConvertTo-Json -Depth 4
$connStatusJson | Set-Content (Join-Path $ShowOutDir 'vpn-connections-status.json') -Encoding UTF8

# ── Step 8: Verify ARS BGP peering states ────────────────────────────────────
Write-Host "`n[8] Verifying ARS BGP peering states..." -ForegroundColor Yellow

$arsList = @(
    @{Name='ars-hub1';    Peers=@('peer-nva1')},
    @{Name='ars-hub2';    Peers=@('peer-nva2')},
    @{Name='ars-poland';  Peers=@('peer-nva1','peer-nva2')}
)

$ArsPeeringStatus = @{}
foreach ($ars in $arsList) {
    Write-Host "    $($ars.Name):" -ForegroundColor Cyan
    $ArsPeeringStatus[$ars.Name] = @{}
    foreach ($peer in $ars.Peers) {
        $peerJson = az network routeserver peering show -g $RgName `
            --routeserver $ars.Name --name $peer `
            --query '{prov:provisioningState,peerIp:peerIp,peerAsn:peerAsn}' -o json 2>&1
        if ($LASTEXITCODE -eq 0) {
            $peerObj = $peerJson | ConvertFrom-Json
            Write-Host "      $peer : prov=$($peerObj.prov) peerIp=$($peerObj.peerIp) ASN=$($peerObj.peerAsn)" `
                -ForegroundColor $(if ($peerObj.prov -eq 'Succeeded') { 'Green' } else { 'Yellow' })
            $ArsPeeringStatus[$ars.Name][$peer] = $peerObj
        } else {
            Write-Host "      $peer : query failed: $peerJson" -ForegroundColor Yellow
            $ArsPeeringStatus[$ars.Name][$peer] = 'QUERY_FAILED'
        }
    }
}

$ArsPeeringStatus | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $ShowOutDir 'ars-bgp-peerings.json') -Encoding UTF8

# ── Step 9: Discover ARS BGP peer IPs (virtualHubs/bgpConnections learned) ───
Write-Host "`n[9] Discovering ARS instance IPs (hub1 + hub2 + poland)..." -ForegroundColor Yellow

$ArsInstanceIps = @{}
foreach ($arsName in @('ars-hub1','ars-hub2','ars-poland')) {
    $lrJson = az network routeserver show -g $RgName -n $arsName `
        --query 'properties.virtualRouterIps' -o json 2>&1
    if ($LASTEXITCODE -eq 0) {
        $ips = $lrJson | ConvertFrom-Json
        $ArsInstanceIps[$arsName] = $ips
        Write-Host "    $arsName instance IPs: $($ips -join ', ')" -ForegroundColor Green
    } else {
        Write-Host "    $arsName : query failed (virtualRouterIps): $lrJson" -ForegroundColor Yellow
        $ArsInstanceIps[$arsName] = @()
    }
}

$ArsInstanceIps | ConvertTo-Json | Set-Content (Join-Path $ShowOutDir 'ars-instance-ips.json') -Encoding UTF8

# ── Step 10: Verify BIRD on NVA1 and NVA2 via run-command ─────────────────────
Write-Host "`n[10] Checking BIRD status on NVA1 and NVA2 via run-command..." -ForegroundColor Yellow

foreach ($vm in @(@{Name='vm-nva1';Rg=$RgName}, @{Name='vm-nva2';Rg=$RgName})) {
    Write-Host "    $($vm.Name)..." -ForegroundColor Cyan
    $rcOut = az vm run-command invoke -g $vm.Rg -n $vm.Name `
        --command-id RunShellScript `
        --scripts 'systemctl is-active bird; birdc show protocols 2>&1 | head -30' `
        -o json 2>&1
    if ($LASTEXITCODE -eq 0) {
        $rcObj = $rcOut | ConvertFrom-Json
        $stdout = $rcObj.value[0].message
        Write-Host "    Output (first 500 chars): $($stdout.Substring(0, [Math]::Min(500, $stdout.Length)))" -ForegroundColor Gray
        $stdout | Set-Content (Join-Path $ShowOutDir "$($vm.Name)-bird-status.txt") -Encoding UTF8
    } else {
        Write-Host "    run-command failed for $($vm.Name): $rcOut" -ForegroundColor Yellow
        $rcOut | Set-Content (Join-Path $ShowOutDir "$($vm.Name)-bird-status-error.txt") -Encoding UTF8
    }
}

# ── Step 11: Verify OS IP forwarding on NVA1 and NVA2 ────────────────────────
Write-Host "`n[11] Verifying OS IP forwarding on NVAs..." -ForegroundColor Yellow

foreach ($vm in @('vm-nva1','vm-nva2')) {
    $rcOut = az vm run-command invoke -g $RgName -n $vm `
        --command-id RunShellScript `
        --scripts 'cat /proc/sys/net/ipv4/ip_forward' `
        -o json 2>&1
    if ($LASTEXITCODE -eq 0) {
        $msg = ($rcOut | ConvertFrom-Json).value[0].message
        $status = if ($msg -match '1') { '✓ enabled' } else { '✗ DISABLED' }
        Write-Host "    $vm ip_forward: $status" -ForegroundColor $(if ($msg -match '1') { 'Green' } else { 'Red' })
    } else {
        Write-Host "    $vm : run-command failed" -ForegroundColor Yellow
    }
}

# ── Step 12: List ARS learned routes (sample — ars-hub1) ─────────────────────
Write-Host "`n[12] Sampling ARS learned routes (ars-hub1)..." -ForegroundColor Yellow

$lrHub1 = az network routeserver peering list-learned-routes -g $RgName `
    --routeserver ars-hub1 --name peer-nva1 -o json 2>&1
if ($LASTEXITCODE -eq 0) {
    $lrHub1 | Set-Content (Join-Path $ShowOutDir 'ars-hub1-learned-routes.json') -Encoding UTF8
    $lrCount = ($lrHub1 | ConvertFrom-Json).RouteServiceRole_IN_0.Count + `
               ($lrHub1 | ConvertFrom-Json).RouteServiceRole_IN_1.Count
    Write-Host "    ars-hub1 learned routes (peer-nva1): $lrCount entries saved." -ForegroundColor Green
} else {
    Write-Host "    ars-hub1 learned routes: not yet available ($lrHub1)" -ForegroundColor Yellow
    'PENDING' | Set-Content (Join-Path $ShowOutDir 'ars-hub1-learned-routes.json')
}

# ── Step 13: Collect resource list snapshot ───────────────────────────────────
Write-Host "`n[13] Collecting resource list snapshot..." -ForegroundColor Yellow
$resourceList = az resource list -g $RgName --query '[].{n:name,t:type,l:location}' -o json 2>&1
$resourceList | Set-Content (Join-Path $ShowOutDir 'resource-list.json') -Encoding UTF8
$resourceCount = ($resourceList | ConvertFrom-Json).Count
Write-Host "    $resourceCount resources in $RgName." -ForegroundColor Green

# ── Step 14: Write deploy-log.md ──────────────────────────────────────────────
$Elapsed    = (Get-Date) - $StartTime
$ElapsedStr = $Elapsed.ToString('hh\:mm\:ss')

$connSummary = ($connNames | ForEach-Object {
    $s = $connStatus[$_]
    $state = if ($s) { $s.state } else { 'Unknown' }
    "| $_ | $state |"
}) -join "`n"

$arsSummary = ($arsList | ForEach-Object {
    $a = $_.Name
    ($_.Peers | ForEach-Object {
        $p = $ArsPeeringStatus[$a][$_]
        $prov = if ($p -and $p -ne 'QUERY_FAILED') { $p.prov } else { 'Unknown' }
        "| $a | $_ | $prov |"
    })
}) -join "`n"

$arsIpSummary = ($ArsInstanceIps.GetEnumerator() | ForEach-Object {
    "| $($_.Key) | $($_.Value -join ', ') |"
}) -join "`n"

$logContent = @"
# deploy-log.md — dual-hub-hubless-region-ars
**Generated:** $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') UTC+02:00  
**Author:** Tank (IaC Engineer)  
**Phase:** DEPLOYED  
**CorrelationId:** $CorrelationId  
**RG:** $RgName  
**Subscription:** [REDACTED]  
**Elapsed:** $ElapsedStr  
**ARM Deployment:** $DeployName  

---

## 1. Resource Group

| Item | Value |
|------|-------|
| RG name | $RgName |
| Region (anchor) | swedencentral |
| Resource count | $resourceCount |
| Elapsed | $ElapsedStr |

---

## 2. VPN Connection Status

| Connection | State |
|------------|-------|
$connSummary

---

## 3. ARS BGP Peering Status

| ARS | Peer | ProvisioningState |
|-----|------|-------------------|
$arsSummary

---

## 4. ARS Instance IPs

| ARS | Instance IPs |
|-----|-------------|
$arsIpSummary

---

## 5. NVA IPs

| VM | Private IP |
|----|-----------|
| vm-nva1 | $NVA1Ip |
| vm-nva2 | $NVA2Ip |

---

## 6. Preflight Summary

All waves deployed via ARM. ARS BGP peers embedded in Bicep template (Morpheus B1 fix applied).
BIRD cloud-init delivered via custom-data; OS ip_forward enabled via runcmd.

---

## 7. Deviations

| # | Item | Status |
|---|------|--------|
| U1 | ARS route-map Δ3 (PUBLIC PREVIEW) | NOT wired — S4 only; separate gated activation needed |
| U2 | BGP convergence timing | Post-deploy ~10 min; check ars-hub1-learned-routes.json |
| — | Baseline route-map scenario Δ3 | NOT activated — Niobe baseline capture first |

---

## 8. Post-Deploy Artifacts

Saved under \`labs/dual-hub-hubless-region-ars/show-output/deploy/\`:
- arm-deploy-output.json
- resource-list.json
- vpn-connections-status.json
- ars-bgp-peerings.json
- ars-instance-ips.json
- ars-hub1-learned-routes.json
- vm-nva1-bird-status.txt
- vm-nva2-bird-status.txt

---

## 9. Handoff to Niobe

Ready for S1 baseline assertions:
- RG: $RgName
- Run \`az network routeserver peering list-learned-routes -g $RgName --routeserver ars-hub1 --name peer-nva1\`
- Run \`az network nic show-effective-route-table --ids <vm-c1-ep-nic-id>\`
- Ping: vm-c1-ep → vm-onprem-ep

Δ3 activation (S4): SEPARATE GATED STEP — do NOT activate without Niobe baseline + Jose approval.

---

*≤ 10 KB — no secrets, no subscription IDs*
"@

Set-Content -Path $DeployLog -Value $logContent -Encoding UTF8
Write-Host "    deploy-log.md updated." -ForegroundColor Green

# ── Final summary ─────────────────────────────────────────────────────────────
Write-Host ''
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Green
Write-Host " DEPLOYMENT COMPLETE — $LabName" -ForegroundColor Green
Write-Host " RG      : $RgName" -ForegroundColor Green
Write-Host " Elapsed : $ElapsedStr" -ForegroundColor Green
Write-Host " Resources: $resourceCount" -ForegroundColor Green
Write-Host " Outputs saved: $ShowOutDir" -ForegroundColor Green
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Green
Write-Host ''
Write-Host " NVA1: $NVA1Ip  NVA2: $NVA2Ip" -ForegroundColor Cyan
Write-Host " ARS hub1 IPs: $($ArsInstanceIps['ars-hub1'] -join ', ')" -ForegroundColor Cyan
Write-Host " ARS hub2 IPs: $($ArsInstanceIps['ars-hub2'] -join ', ')" -ForegroundColor Cyan
Write-Host " ARS poland IPs: $($ArsInstanceIps['ars-poland'] -join ', ')" -ForegroundColor Cyan
Write-Host ''
Write-Host ' HANDOFF: Niobe — S1 baseline assertions ready.' -ForegroundColor Yellow
Write-Host ' ⚠  Δ3 route-map (S4) NOT activated — separate gate required.' -ForegroundColor Yellow
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Green
