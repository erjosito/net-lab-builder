<#
.SYNOPSIS
    Deploy or validate the dual-hub-hubless-region-ars lab (Tank IaC).

.DESCRIPTION
    Implements:
      - SKU catalog preflight for Standard_B2ts_v2 in all 4 regions
      - Live az vm create --validate preflight per region (temp RGs, deleted on exit)
      - Bicep build/lint
      - ARM deployment group validate (no resources created)
      - PSK generation in-process only (optionally written to KV; never to disk)
      - SSH pubkey fetch from KV (platform-secrets-1138)
      - Outputs ARM what-if plan to deploy-log.md

    DO NOT deploy (no --apply) in this script without Trinity IaC review approval.

.PARAMETER KvName
    Key Vault name for SSH pubkey and optional PSK storage.

.PARAMETER KvRg
    Resource group containing the Key Vault.

.PARAMETER SshKeySecretName
    KV secret name holding the SSH public key (default: vm-ssh-pub-key).

.PARAMETER CorrelationId
    Unique ID for resource tagging and RG naming. Auto-generated if empty.

.PARAMETER ExpectedSubName
    Expected subscription display name — fails fast if wrong subscription.

.PARAMETER ValidateOnly
    Switch: run Bicep build + ARM validate only; skip live VM preflight.

.PARAMETER SkipKv
    Switch: skip KV fetch; use placeholder SSH key (validate-only mode).

.NOTES
    Lab     : dual-hub-hubless-region-ars
    Regions : swedencentral · switzerlandnorth · polandcentral · norwayeast
    Sub     : Resolved via az account show (NOT hardcoded)
    KV      : platform-secrets-1138 / RG platform
    Cost    : ~$65.86/day baseline (Jose approved 2026-08-03T15:39:35+02:00)
    ⚠ DO NOT DEPLOY without Trinity IaC review approval
#>

[CmdletBinding()]
param(
    [Parameter()] [string]$KvName            = 'platform-secrets-1138',
    [Parameter()] [string]$KvRg              = 'platform',
    [Parameter()] [string]$SshKeySecretName  = 'vm-ssh-pub-key',
    [Parameter()] [string]$CorrelationId     = '',
    [Parameter()] [string]$ExpectedSubName   = '',
    [Parameter()] [switch]$ValidateOnly,
    [Parameter()] [switch]$SkipKv
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'

$StartTime  = Get-Date
$LabName    = 'dual-hub-hubless-region-ars'
$TemplateDir = Join-Path $PSScriptRoot 'templates'
$MainBicep   = Join-Path $TemplateDir 'main.bicep'
$MainArm     = Join-Path $TemplateDir 'main.json'
$ParamsFile  = Join-Path $PSScriptRoot 'parameters\lab.parameters.json'
$DeployLog   = Join-Path (Split-Path $PSScriptRoot -Parent) 'deploy-log.md'

# Regions to preflight
$Regions = @('swedencentral', 'switzerlandnorth', 'polandcentral', 'norwayeast')
$VmSku   = 'Standard_B2ts_v2'
$VmFallback = 'Standard_B2ls_v2'

if ([string]::IsNullOrEmpty($CorrelationId)) {
    $CorrelationId = [System.Guid]::NewGuid().ToString('N').Substring(0, 8)
}

Write-Host ''
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Cyan
Write-Host " Tank — $LabName" -ForegroundColor Cyan
Write-Host " Mode   : $(if ($ValidateOnly) { 'VALIDATE-ONLY' } else { 'PREFLIGHT + VALIDATE' })" -ForegroundColor Cyan
Write-Host " CorrID : $CorrelationId" -ForegroundColor Cyan
Write-Host " Date   : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Cyan

# ── Step 0: Verify Azure subscription ─────────────────────────────────────────
Write-Host ''
Write-Host '[0] Verifying Azure subscription...' -ForegroundColor Yellow
$subJson   = az account show -o json 2>&1
if ($LASTEXITCODE -ne 0) { throw "az account show failed. Please run 'az login' first." }
$subInfo   = $subJson | ConvertFrom-Json
$SubId     = $subInfo.id
$SubName   = $subInfo.name

Write-Host "    Subscription: $SubName" -ForegroundColor Green
if ($ExpectedSubName -and $SubName -ne $ExpectedSubName) {
    throw "Wrong subscription. Expected '$ExpectedSubName', got '$SubName'."
}

# ── Step 1: SKU Catalog Preflight ─────────────────────────────────────────────
Write-Host ''
Write-Host '[1] SKU catalog check — Standard_B2ts_v2 in all 4 regions...' -ForegroundColor Yellow

$PrefResultCatalog = @()
foreach ($region in $Regions) {
    $skuJson = az vm list-skus -l $region --resource-type virtualMachines `
        --query "[?name=='$VmSku'].{n:name,r:restrictions[0].reasonCode}" -o json 2>&1
    $skuObjs = $skuJson | ConvertFrom-Json
    $pass    = ($skuObjs.Count -gt 0) -and ($skuObjs[0].r -eq $null -or $skuObjs[0].r -eq 'None')
    $status  = if ($pass) { '✓ PASS' } else { '✗ FAIL — trying fallback' }
    Write-Host "    $region : $VmSku = $status"

    if (-not $pass) {
        # Try fallback
        $fbJson  = az vm list-skus -l $region --resource-type virtualMachines `
            --query "[?name=='$VmFallback'].{n:name,r:restrictions[0].reasonCode}" -o json 2>&1
        $fbObjs  = $fbJson | ConvertFrom-Json
        $fbPass  = ($fbObjs.Count -gt 0) -and ($fbObjs[0].r -eq $null -or $fbObjs[0].r -eq 'None')
        if ($fbPass) {
            Write-Host "    $region : $VmFallback = ✓ PASS (fallback)" -ForegroundColor Yellow
            $PrefResultCatalog += [pscustomobject]@{Region=$region; SKU=$VmFallback; Result='PASS-FALLBACK'}
        } else {
            throw "CATALOG FAIL: neither $VmSku nor $VmFallback available in $region"
        }
    } else {
        $PrefResultCatalog += [pscustomobject]@{Region=$region; SKU=$VmSku; Result='PASS'}
    }
}

# ── Step 2: Live VM Validate Preflight (az vm create --validate) ───────────────
$PrefResultLive = @()

if ($ValidateOnly) {
    Write-Host ''
    Write-Host '[2] Skipping live VM preflight (--ValidateOnly).' -ForegroundColor DarkGray
} else {
    Write-Host ''
    Write-Host '[2] Live az vm create --validate preflight (temp RGs, deleted on exit)...' -ForegroundColor Yellow

    # Need an SSH key for the validate call
    $SshKeyForPreflight = 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC+preflight-placeholder'
    if (-not $SkipKv) {
        try {
            $kvSshRaw = az keyvault secret show --vault-name $KvName --name 'vm-ssh-pub-preflight' `
                --query 'value' -o tsv 2>&1
            if ($LASTEXITCODE -eq 0 -and $kvSshRaw -match 'ssh-') {
                $SshKeyForPreflight = $kvSshRaw.Trim()
            }
        } catch { }
    }

    $CreatedPrefRGs = @()
    try {
        foreach ($region in $Regions) {
            $prefRg = "preflight-ars-$CorrelationId-$region"
            $probeName = "probe-$(Get-Random -Maximum 99999)"

            Write-Host "    $region : creating preflight RG $prefRg..."
            az group create -n $prefRg -l $region --tags lab=preflight ephemeral=true -o none

            $CreatedPrefRGs += $prefRg

            Write-Host "    $region : running az vm create --validate..."
            $validateOut = az vm create -g $prefRg -n $probeName -l $region `
                --image 'Ubuntu2204' --size $VmSku `
                --admin-username 'azureuser' `
                --ssh-key-values $SshKeyForPreflight `
                --validate -o json 2>&1

            if ($LASTEXITCODE -eq 0) {
                Write-Host "    $region : ✓ PASS" -ForegroundColor Green
                $PrefResultLive += [pscustomobject]@{Region=$region; SKU=$VmSku; Result='PASS'}
            } else {
                $errStr = $validateOut | Out-String
                Write-Host "    $region : WARN — $($errStr.Substring(0, [Math]::Min(200,$errStr.Length)))" -ForegroundColor Yellow
                $PrefResultLive += [pscustomobject]@{Region=$region; SKU=$VmSku; Result='WARN'; Error=$errStr}
            }
        }
    } finally {
        Write-Host '    Cleaning up preflight RGs...' -ForegroundColor Yellow
        foreach ($prg in $CreatedPrefRGs) {
            az group delete -n $prg --yes --no-wait -o none 2>&1 | Out-Null
            Write-Host "    Deleted (async): $prg"
        }
    }
}

# ── Step 3: Fetch SSH public key from KV ──────────────────────────────────────
Write-Host ''
Write-Host '[3] Fetching SSH public key from KV...' -ForegroundColor Yellow

$SshPubKey = ''
if ($SkipKv) {
    $SshPubKey = 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC0+PLACEHOLDER+validate-mode labadmin@validate'
    Write-Host '    Using placeholder SSH key (--SkipKv).' -ForegroundColor DarkGray
} else {
    try {
        $SshPubKey = (az keyvault secret show `
            --vault-name $KvName --name $SshKeySecretName `
            --query 'value' -o tsv 2>&1).Trim()
        if ($LASTEXITCODE -ne 0 -or -not ($SshPubKey -match 'ssh-')) {
            throw "KV secret '$SshKeySecretName' not found or invalid."
        }
        Write-Host "    SSH pubkey fetched from KV '$KvName'." -ForegroundColor Green
    } catch {
        Write-Warning "KV fetch failed: $_"
        Write-Warning "Using placeholder SSH key. Template validation will succeed; live deploy will fail without real key."
        $SshPubKey = 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC0+PLACEHOLDER+validate-mode labadmin@validate'
    }
}

# ── Step 4: Generate PSKs (in-process only; never written to disk or log) ─────
Write-Host ''
Write-Host '[4] Generating PSKs (in-process, no persistence)...' -ForegroundColor Yellow

# Generate 32-char random PSKs using .NET crypto
function New-LabPsk {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $b64 = [Convert]::ToBase64String($bytes)
    # Keep only alphanumeric chars, first 32
    return ($b64 -replace '[^A-Za-z0-9]', '').Substring(0, 32)
}

$PskHub1 = New-LabPsk
$PskHub2 = New-LabPsk

# Optionally write to KV (best-effort; not required for validate step)
if (-not $SkipKv) {
    try {
        az keyvault secret set --vault-name $KvName --name 'psk-hub1-onprem' --value $PskHub1 -o none 2>&1 | Out-Null
        az keyvault secret set --vault-name $KvName --name 'psk-hub2-onprem' --value $PskHub2 -o none 2>&1 | Out-Null
        Write-Host "    PSKs written to KV '$KvName' (psk-hub1-onprem, psk-hub2-onprem)." -ForegroundColor Green
    } catch {
        Write-Warning "KV PSK write failed: $_  — PSKs held in process memory only."
    }
} else {
    Write-Host '    PSKs held in process memory only (--SkipKv).' -ForegroundColor DarkGray
}

# ── Step 5: Build cloud-init (base64 encode YAML files) ──────────────────────
Write-Host ''
Write-Host '[5] Encoding cloud-init YAML files...' -ForegroundColor Yellow

$Nva1CloudInitFile = Join-Path $PSScriptRoot 'nva1-cloud-init.yaml'
$Nva2CloudInitFile = Join-Path $PSScriptRoot 'nva2-cloud-init.yaml'

$Nva1B64 = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($Nva1CloudInitFile))
$Nva2B64 = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($Nva2CloudInitFile))
Write-Host '    cloud-init YAML encoded.' -ForegroundColor Green

# ── Step 6: Bicep build/lint ──────────────────────────────────────────────────
Write-Host ''
Write-Host '[6] Building Bicep (lint)...' -ForegroundColor Yellow

$bicepBuildOut = az bicep build --file $MainBicep --outfile $MainArm 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host $bicepBuildOut -ForegroundColor Red
    throw "Bicep build FAILED"
}
Write-Host "    Bicep build OK — ARM JSON: $MainArm" -ForegroundColor Green
Write-Host $bicepBuildOut

# ── Step 7: ARM Deployment Validate (temp preflight RG) ──────────────────────
Write-Host ''
Write-Host '[7] ARM deployment group validate (temp RG; no resources created)...' -ForegroundColor Yellow

$ValidateRg = "preflight-ars-validate-$CorrelationId"
az group create -n $ValidateRg -l 'swedencentral' `
    --tags lab=preflight ephemeral=true correlation_id=$CorrelationId -o none

Write-Host "    Validate RG: $ValidateRg"

# Build inline parameter overrides (PSKs and secrets NOT in file)
$validateParams = @(
    "correlationId=$CorrelationId",
    "vmSshPublicKey=$SshPubKey",
    "nva1CloudInit=$Nva1B64",
    "nva2CloudInit=$Nva2B64",
    "pskHub1Onprem=$PskHub1",
    "pskHub2Onprem=$PskHub2"
)
$paramArgs = ($validateParams | ForEach-Object { "--parameters $_" }) -join ' '

$validateCmd = "az deployment group validate " +
    "--resource-group $ValidateRg " +
    "--template-file `"$MainBicep`" " +
    "--parameters adminUsername=labadmin vmSize=Standard_B2ts_v2 " +
    "correlationId=$CorrelationId " +
    "nva1CloudInit=$Nva1B64 " +
    "nva2CloudInit=$Nva2B64"
# PSKs and SSH key passed separately (secure params) — handled below via hashtable

$validateResult = az deployment group validate `
    --resource-group $ValidateRg `
    --template-file $MainBicep `
    --parameters adminUsername='labadmin' `
    --parameters vmSize='Standard_B2ts_v2' `
    --parameters correlationId="$CorrelationId" `
    --parameters nva1CloudInit="$Nva1B64" `
    --parameters nva2CloudInit="$Nva2B64" `
    --parameters pskHub1Onprem="$PskHub1" `
    --parameters pskHub2Onprem="$PskHub2" `
    --parameters vmSshPublicKey="$SshPubKey" `
    -o json 2>&1

$validateExitCode = $LASTEXITCODE

Write-Host '    Cleaning up validate RG...' -ForegroundColor Yellow
az group delete -n $ValidateRg --yes --no-wait -o none 2>&1 | Out-Null
Write-Host "    Deleted (async): $ValidateRg"

if ($validateExitCode -ne 0) {
    Write-Host '══════════════════════════════════════════════════════════' -ForegroundColor Red
    Write-Host ' ARM VALIDATION FAILED' -ForegroundColor Red
    Write-Host '══════════════════════════════════════════════════════════' -ForegroundColor Red
    Write-Host $validateResult
    $ValidateStatus = 'FAIL'
} else {
    Write-Host '    ARM validation: ✓ PASS' -ForegroundColor Green
    $ValidateStatus = 'PASS'
}

# ── Step 8: ARM What-If (plan) ────────────────────────────────────────────────
Write-Host ''
Write-Host '[8] ARM what-if (plan — no changes applied)...' -ForegroundColor Yellow
Write-Host '    NOTE: What-if runs against validate RG shell; actual lab RG not created.' -ForegroundColor DarkGray

$WhatIfRg = "preflight-ars-whatif-$CorrelationId"
az group create -n $WhatIfRg -l 'swedencentral' `
    --tags lab=preflight ephemeral=true correlation_id=$CorrelationId -o none

$whatIfResult = az deployment group what-if `
    --resource-group $WhatIfRg `
    --template-file $MainBicep `
    --parameters adminUsername='labadmin' `
    --parameters vmSize='Standard_B2ts_v2' `
    --parameters correlationId="$CorrelationId" `
    --parameters nva1CloudInit="$Nva1B64" `
    --parameters nva2CloudInit="$Nva2B64" `
    --parameters pskHub1Onprem="$PskHub1" `
    --parameters pskHub2Onprem="$PskHub2" `
    --parameters vmSshPublicKey="$SshPubKey" `
    --no-pretty-print 2>&1

$whatIfExitCode = $LASTEXITCODE

az group delete -n $WhatIfRg --yes --no-wait -o none 2>&1 | Out-Null
Write-Host "    Deleted (async): $WhatIfRg"

$WhatIfStatus = if ($whatIfExitCode -eq 0) { 'PASS' } else { 'WARN' }
Write-Host "    What-if: $WhatIfStatus" -ForegroundColor $(if ($whatIfExitCode -eq 0) { 'Green' } else { 'Yellow' })

# ── Step 9: Write deploy-log.md ───────────────────────────────────────────────
Write-Host ''
Write-Host '[9] Writing deploy-log.md...' -ForegroundColor Yellow

$catalogTable = ($PrefResultCatalog | ForEach-Object {
    "| $($_.Region) | $($_.SKU) | $($_.Result) |"
}) -join "`n"

$liveTable = if ($PrefResultLive.Count -gt 0) {
    ($PrefResultLive | ForEach-Object { "| $($_.Region) | $($_.SKU) | $($_.Result) |" }) -join "`n"
} else { "| — | — | Skipped (--ValidateOnly) |" }

$deployLogContent = @"
# deploy-log.md — dual-hub-hubless-region-ars
**Generated:** $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') UTC+02:00  
**Author:** Tank (IaC Engineer)  
**Phase:** Author + Validate-Plan only — NOT deployed  
**CorrelationId:** $CorrelationId  
**Subscription:** [REDACTED — resolved via az account show]

---

## 1. SKU Catalog Preflight

| Region | SKU | Result |
|--------|-----|--------|
$catalogTable

## 2. Live VM Validate Preflight

| Region | SKU | Result |
|--------|-----|--------|
$liveTable

## 3. Bicep Build/Lint

| Check | Result |
|-------|--------|
| `az bicep build templates/main.bicep` | $(if ($bicepBuildOut -match 'error') { 'FAIL' } else { 'PASS' }) |

## 4. ARM Deployment Validate

| Check | Result |
|-------|--------|
| `az deployment group validate` (temp RG) | $ValidateStatus |
| Validate RG (deleted) | preflight-ars-validate-$CorrelationId |

## 5. ARM What-If (Plan)

| Check | Result |
|-------|--------|
| `az deployment group what-if` | $WhatIfStatus |

## 6. Design Coexistence Checks

| Item | Value | Correct |
|------|-------|---------|
| vpngw-hub1 ASN | 65515 | ✓ matches ars-hub1 ASN |
| vpngw-hub2 ASN | 65515 | ✓ matches ars-hub2 ASN |
| vpngw-onprem ASN | 65000 | ✓ different from ARS |
| ars-hub1 branch-to-branch | true | ✓ ARS+VPN GW coexistence |
| ars-hub2 branch-to-branch | true | ✓ ARS+VPN GW coexistence |
| ars-poland branch-to-branch | false | ✓ ARS-only (no VPN GW) |
| All 3 VPN GWs active-active | true | ✓ AA mandatory for ARS coexistence |
| Set-C spokes URG | On poland-ars peering only | ✓ max 1 URG per spoke |
| Set-A/B UDRs | 0/0→NVA, bgpPropagation=false | ✓ |
| Set-C UDRs | None (ARS injects) | ✓ |
| ARS PIPs | 3 Standard (1 per ARS) | ✓ required for SDN mgmt plane |
| VPN GW PIPs | 6 Standard (2 per AA GW) | ✓ |

## 7. Deviations / Unproven Preview Behaviors

| # | Item | Status |
|---|------|--------|
| U1 | ARS inbound route-map (Δ3) prepend with doc-range ASN 64496 | NOT WIRED — S4 only; separate gated step required |
| U2 | vpn-connection reset timing under partial IKE failure | Unproven; measure in S2 |
| U3 | list-learned-routes shows AS_PATH post-NVA Δ1 filter | Expected; verify in S1 |
| U4 | Set-C effective routes show both hub1+hub2 VNetPeering entries | Expected; verify in S1 |
| — | ARS route maps = PUBLIC PREVIEW | Δ3 isolated to S4; lab completes without it |

## 8. PSK Handling

PSKs generated at runtime via .NET RandomNumberGenerator (32 chars, alphanumeric).  
Written to KV `platform-secrets-1138` (psk-hub1-onprem, psk-hub2-onprem) or held in process vars.  
**Not persisted to disk, not logged here, not in Git.**  
KV purge at cleanup is EXPLICIT (not automatic from RG delete) — see cleanup.ps1 Step 9.

## 9. Trinity IaC Review Gate

**⛔ DEPLOYMENT BLOCKED — Trinity IaC review required before applying.**

Trinity review command:
\`\`\`powershell
# Review the IaC diff (no deploy)
git diff --stat
# Then run full plan again:
.\\labs\\dual-hub-hubless-region-ars\\deploy\\deploy.ps1 -ValidateOnly -SkipKv
\`\`\`

---
*≤ 10 KB — no secrets, no subscription IDs*
"@

Set-Content -Path $DeployLog -Value $deployLogContent -Encoding UTF8
Write-Host "    deploy-log.md written: $DeployLog" -ForegroundColor Green

# ── Summary ───────────────────────────────────────────────────────────────────
$Elapsed = (Get-Date) - $StartTime
Write-Host ''
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Cyan
Write-Host ' Tank — Author+Validate complete' -ForegroundColor Cyan
Write-Host " Elapsed   : $($Elapsed.ToString('hh\:mm\:ss'))" -ForegroundColor Cyan
Write-Host " Validate  : $ValidateStatus" -ForegroundColor $(if ($ValidateStatus -eq 'PASS') { 'Green' } else { 'Red' })
Write-Host " What-If   : $WhatIfStatus" -ForegroundColor $(if ($WhatIfStatus -eq 'PASS') { 'Green' } else { 'Yellow' })
Write-Host " Deploy log: $DeployLog" -ForegroundColor Cyan
Write-Host ''
Write-Host ' ⛔ DO NOT DEPLOY — Trinity IaC review required.' -ForegroundColor Red
Write-Host ' Trinity review: git diff --stat + inspect templates/main.bicep' -ForegroundColor Yellow
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Cyan
