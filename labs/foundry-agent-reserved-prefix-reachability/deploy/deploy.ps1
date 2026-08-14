<#
.SYNOPSIS
    Deploy or validate the foundry-agent-reserved-prefix-reachability lab (Tank IaC).

.DESCRIPTION
    Default mode: VALIDATE ONLY — runs Bicep build + ARM deployment validate.
    No Azure resources are created unless -Apply is explicitly specified.

    Steps:
      0  Verify Azure subscription
      1  Bicep build / lint  (az bicep build)
      2  Read SSH public key from ~/.ssh/id_rsa.pub (or KV if -KvName provided)
      3  Generate PSK in-process — never written to disk or logged
      4  ARM deployment group validate  (temp RG; deleted on exit)
      5  ARM what-if  (temp RG; deleted on exit)
      [APPLY only — requires -Apply switch]
      6  Create lab RG with required tags
      7  az deployment group create (actual deploy)
      8  Print outputs (handoff IDs for Jose + Niobe)

    PSK handling: generated in PowerShell process memory using .NET CSPRNG.
    The PSK is passed to ARM as a secure parameter; it is never written to a
    file or emitted to logs. If -KvName is provided the PSK is also stored in
    the specified Key Vault for recovery.

.PARAMETER Apply
    Switch: perform actual deployment. WITHOUT this switch, only validate + what-if run.
    ⚠️ Deploy requires Phase-4 cost approval from Jose Moreno (see manifest §13).

.PARAMETER AutoApprove
    Skip the interactive apply confirmation. Use only when Phase-4 approval is recorded.

.PARAMETER RgName
    Resource group name (default: rg-foundry-reserved-<CorrelationId>).

.PARAMETER RgLocation
    RG metadata region (default: swedencentral).

.PARAMETER CorrelationId
    8-char hex ID for tagging and RG naming. Auto-generated if empty.

.PARAMETER AdminUsername
    VM admin username (default: labadmin).

.PARAMETER SshPubKeyPath
    Path to SSH public key file (default: ~/.ssh/id_rsa.pub).

.PARAMETER DeployDnsResolver
    Deploy optional DNS Private Resolver (S5 scope; default false).

.PARAMETER KvName
    Key Vault name for PSK storage (optional; no KV dependency for validate).

.PARAMETER ExpectedSubName
    Expected subscription display name — fails fast if wrong subscription.

.NOTES
    Lab     : foundry-agent-reserved-prefix-reachability
    Regions : swedencentral (Foundry infra) + norwayeast (on-prem simulator)
    Cost    : ~$21-23/day baseline, ~$33-35/day with DNS resolver (within $50/day guardrail)
    Phase-4 approval gate: Jose Moreno must approve before -Apply is used
    Foundry account: NOT created by IaC — see portal-foundry-setup.md
#>

[CmdletBinding()]
param(
    [Parameter()] [switch]$Apply,
    [Parameter()] [switch]$AutoApprove,
    [Parameter()] [string]$RgName             = '',
    [Parameter()] [string]$RgLocation         = 'swedencentral',
    [Parameter()] [string]$CorrelationId      = '',
    [Parameter()] [string]$AdminUsername      = 'labadmin',
    [Parameter()] [string]$SshPubKeyPath      = '',
    [Parameter()] [switch]$DeployDnsResolver,
    [Parameter()] [string]$KvName             = '',
    [Parameter()] [string]$ExpectedSubName    = ''
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'

$LabName     = 'foundry-agent-reserved-prefix-reachability'
$TemplateDir = $PSScriptRoot
$MainBicep   = Join-Path $TemplateDir 'main.bicep'
$ParamsFile  = Join-Path $TemplateDir 'parameters\lab.parameters.json'

if ([string]::IsNullOrEmpty($CorrelationId)) {
    $CorrelationId = [System.Guid]::NewGuid().ToString('N').Substring(0, 8)
}
if ([string]::IsNullOrEmpty($RgName)) {
    $RgName = "rg-foundry-reserved-$CorrelationId"
}
if ([string]::IsNullOrEmpty($SshPubKeyPath)) {
    $SshPubKeyPath = Join-Path $env:USERPROFILE '.ssh\id_rsa.pub'
}

$Mode = if ($Apply) { 'DEPLOY (apply)' } else { 'VALIDATE-ONLY' }

Write-Host ''
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Cyan
Write-Host " Tank — $LabName" -ForegroundColor Cyan
Write-Host " Mode     : $Mode" -ForegroundColor Cyan
Write-Host " RG       : $RgName" -ForegroundColor Cyan
Write-Host " CorrID   : $CorrelationId" -ForegroundColor Cyan
Write-Host " DNS Res  : $($DeployDnsResolver.IsPresent)" -ForegroundColor Cyan
Write-Host " Date     : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
if ($Apply) {
    Write-Host ' ⚠️  APPLY mode — Azure resources will be created.' -ForegroundColor Yellow
    Write-Host ' ⚠️  Phase-4 cost approval must be on record before proceeding.' -ForegroundColor Yellow
}
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Cyan

# ── Step 0: Verify Azure subscription ─────────────────────────────────────────
Write-Host ''
Write-Host '[0] Verifying Azure subscription...' -ForegroundColor Yellow
$subJson = az account show -o json 2>&1
if ($LASTEXITCODE -ne 0) { throw "az account show failed. Run 'az login' first." }
$subInfo  = $subJson | ConvertFrom-Json
$SubId    = $subInfo.id
$SubName  = $subInfo.name
Write-Host "    Subscription: $SubName  ($SubId)" -ForegroundColor Green
if ($ExpectedSubName -and $SubName -ne $ExpectedSubName) {
    throw "Wrong subscription. Expected '$ExpectedSubName', got '$SubName'."
}

# ── Step 1: Bicep build / lint ────────────────────────────────────────────────
Write-Host ''
Write-Host '[1] Building Bicep template...' -ForegroundColor Yellow
$buildOut = az bicep build --file $MainBicep 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host $buildOut -ForegroundColor Red
    throw 'Bicep build FAILED'
}
Write-Host '    Bicep build OK.' -ForegroundColor Green

# ── Step 2: Read SSH public key ───────────────────────────────────────────────
Write-Host ''
Write-Host '[2] Reading SSH public key...' -ForegroundColor Yellow
$SshPubKey = ''

if ($KvName -and $Apply) {
    try {
        $SshPubKey = (az keyvault secret show --vault-name $KvName --name 'vm-ssh-pub-key' `
            --query 'value' -o tsv 2>&1).Trim()
        if ($LASTEXITCODE -eq 0 -and $SshPubKey -match '^ssh-') {
            Write-Host "    SSH pubkey loaded from KV '$KvName'." -ForegroundColor Green
        } else { $SshPubKey = '' }
    } catch { $SshPubKey = '' }
}

if ([string]::IsNullOrEmpty($SshPubKey)) {
    if (Test-Path $SshPubKeyPath) {
        $SshPubKey = (Get-Content $SshPubKeyPath -Raw).Trim()
        Write-Host "    SSH pubkey loaded from: $SshPubKeyPath" -ForegroundColor Green
    } else {
        if (-not $Apply) {
            $SshPubKey = 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC+PLACEHOLDER+validate-only labadmin@validate'
            Write-Host '    ⚠️  Using placeholder SSH key (validate-only; file not found).' -ForegroundColor Yellow
        } else {
            throw "SSH public key not found at '$SshPubKeyPath'. Provide -SshPubKeyPath or -KvName."
        }
    }
}

# ── Step 3: Generate PSK in-process (never written to disk) ──────────────────
Write-Host ''
Write-Host '[3] Generating PSK (in-process CSPRNG; never written to disk)...' -ForegroundColor Yellow

function New-LabPsk {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $b64 = [Convert]::ToBase64String($bytes)
    return ($b64 -replace '[^A-Za-z0-9]', '').Substring(0, 32)
}
$VpnPsk = New-LabPsk

if ($KvName) {
    try {
        az keyvault secret set --vault-name $KvName --name "psk-foundry-onprem-$CorrelationId" `
            --value $VpnPsk -o none 2>&1 | Out-Null
        Write-Host "    PSK stored in KV '$KvName' as psk-foundry-onprem-$CorrelationId." -ForegroundColor Green
    } catch {
        Write-Warning "KV PSK write failed: $_  PSK held in process memory only."
    }
} else {
    Write-Host '    PSK held in process memory only.' -ForegroundColor DarkGray
    if ($Apply) {
        Write-Host '    ⚠️  If this deploy is interrupted, re-run to generate a new PSK.' -ForegroundColor DarkGray
    }
}

# ── Step 4: ARM deployment validate (temp RG) ─────────────────────────────────
Write-Host ''
Write-Host '[4] ARM deployment group validate (temp RG; no resources created)...' -ForegroundColor Yellow
$ValidateRg = "preflight-foundry-validate-$CorrelationId"

az group create -n $ValidateRg -l $RgLocation `
    --tags lab=preflight ephemeral=true correlation_id=$CorrelationId -o none
Write-Host "    Validate RG: $ValidateRg"

try {
    $validateResult = az deployment group validate `
        --resource-group $ValidateRg `
        --template-file $MainBicep `
        --parameters "@$ParamsFile" `
        --parameters adminUsername="$AdminUsername" `
        --parameters vmSshPublicKey="$SshPubKey" `
        --parameters correlationId="$CorrelationId" `
        --parameters vpnPsk="$VpnPsk" `
        --parameters deployDnsResolver="$($DeployDnsResolver.IsPresent.ToString().ToLower())" `
        -o json 2>&1
    $validateExitCode = $LASTEXITCODE
} finally {
    az group delete -n $ValidateRg --yes --no-wait -o none 2>&1 | Out-Null
    Write-Host "    Validate RG queued for deletion: $ValidateRg"
}

if ($validateExitCode -ne 0) {
    Write-Host '══════════════════════════════════════════════════════════' -ForegroundColor Red
    Write-Host ' ARM VALIDATION FAILED' -ForegroundColor Red
    Write-Host '══════════════════════════════════════════════════════════' -ForegroundColor Red
    Write-Host ($validateResult | Out-String)
    throw 'Validation failed — see output above.'
}
Write-Host '    ARM validation: ✓ PASS' -ForegroundColor Green

# ── Step 5: ARM what-if (plan, temp RG) ───────────────────────────────────────
Write-Host ''
Write-Host '[5] ARM what-if (plan; temp RG)...' -ForegroundColor Yellow
$WhatIfRg = "preflight-foundry-whatif-$CorrelationId"

az group create -n $WhatIfRg -l $RgLocation `
    --tags lab=preflight ephemeral=true correlation_id=$CorrelationId -o none

try {
    $whatIfOut = az deployment group what-if `
        --resource-group $WhatIfRg `
        --template-file $MainBicep `
        --parameters "@$ParamsFile" `
        --parameters adminUsername="$AdminUsername" `
        --parameters vmSshPublicKey="$SshPubKey" `
        --parameters correlationId="$CorrelationId" `
        --parameters vpnPsk="$VpnPsk" `
        --parameters deployDnsResolver="$($DeployDnsResolver.IsPresent.ToString().ToLower())" `
        --no-pretty-print 2>&1
    $whatIfExit = $LASTEXITCODE
} finally {
    az group delete -n $WhatIfRg --yes --no-wait -o none 2>&1 | Out-Null
    Write-Host "    What-if RG queued for deletion: $WhatIfRg"
}

if ($whatIfExit -eq 0) {
    Write-Host '    What-if: ✓ PASS' -ForegroundColor Green
    Write-Host $whatIfOut
} else {
    Write-Host '    What-if: ⚠️  WARN (non-blocking)' -ForegroundColor Yellow
    Write-Host $whatIfOut
}

# ── Exit here if validate-only ────────────────────────────────────────────────
if (-not $Apply) {
    Write-Host ''
    Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Green
    Write-Host ' VALIDATE-ONLY complete. No resources created.' -ForegroundColor Green
    Write-Host " Re-run with -Apply to deploy (requires Phase-4 approval)." -ForegroundColor Green
    Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Green
    exit 0
}

# ══════════════════════════════════════════════════════════════════════════════
# APPLY — Steps 6-8 run only when -Apply switch is passed
# ⚠️  Phase-4 cost approval from Jose Moreno must be on record
# ══════════════════════════════════════════════════════════════════════════════

Write-Host ''
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Red
Write-Host ' ⚠️  APPLY — About to CREATE AZURE RESOURCES' -ForegroundColor Red
Write-Host "     RG: $RgName  ($RgLocation)" -ForegroundColor Red
Write-Host '     Confirm Phase-4 cost approval is on record.' -ForegroundColor Red
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Red
if (-not $AutoApprove) {
    $confirm = Read-Host "Type 'yes' to proceed"
    if ($confirm -ne 'yes') { Write-Host 'Aborted.'; exit 0 }
}

# ── Step 6: Create lab RG ─────────────────────────────────────────────────────
Write-Host ''
Write-Host "[6] Creating lab resource group '$RgName'..." -ForegroundColor Yellow
az group create -n $RgName -l $RgLocation `
    --tags lab=true created_by=copilot-lab `
           "lab_name=$LabName" ephemeral=true `
           correlation_id=$CorrelationId -o none
if ($LASTEXITCODE -ne 0) { throw "Failed to create RG '$RgName'." }
Write-Host "    RG created: $RgName" -ForegroundColor Green

# ── Step 7: Deploy ────────────────────────────────────────────────────────────
Write-Host ''
Write-Host '[7] Deploying lab template (Wave 3 GWs ~30-45 min)...' -ForegroundColor Yellow
$StartTime = Get-Date

$deployOut = az deployment group create `
    --resource-group $RgName `
    --template-file $MainBicep `
    --parameters "@$ParamsFile" `
    --parameters adminUsername="$AdminUsername" `
    --parameters vmSshPublicKey="$SshPubKey" `
    --parameters correlationId="$CorrelationId" `
    --parameters vpnPsk="$VpnPsk" `
    --parameters deployDnsResolver="$($DeployDnsResolver.IsPresent.ToString().ToLower())" `
    --name "deploy-foundry-$CorrelationId" `
    -o json 2>&1

$deployExit = $LASTEXITCODE
$Elapsed    = (Get-Date) - $StartTime

# Clear PSK from memory
$VpnPsk = $null

if ($deployExit -ne 0) {
    Write-Host '══════════════════════════════════════════════════════════' -ForegroundColor Red
    Write-Host ' DEPLOYMENT FAILED' -ForegroundColor Red
    Write-Host "  Elapsed: $($Elapsed.ToString('mm\:ss'))" -ForegroundColor Red
    Write-Host '══════════════════════════════════════════════════════════' -ForegroundColor Red
    Write-Host $deployOut
    throw "Deployment failed. RG '$RgName' may contain partial resources — review before cleanup."
}

$outputsJson = az deployment group show `
    --resource-group $RgName `
    --name "deploy-foundry-$CorrelationId" `
    --query properties.outputs `
    -o json 2>&1
if ($LASTEXITCODE -ne 0) {
    throw 'Deployment succeeded, but retrieving deployment outputs failed.'
}
$outputs = ($outputsJson | Out-String) | ConvertFrom-Json

# ── Step 8: Print handoff outputs ─────────────────────────────────────────────
Write-Host ''
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Green
Write-Host " DEPLOYMENT COMPLETE  (elapsed: $($Elapsed.ToString('mm\:ss')))" -ForegroundColor Green
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Green
Write-Host ''
Write-Host '── Resource Group ───────────────────────────────────────────'
Write-Host "  Name   : $RgName"
Write-Host "  Region : swedencentral (Foundry) / norwayeast (on-prem)"
Write-Host "  CorrID : $CorrelationId"
Write-Host ''
Write-Host '── Foundry Portal Handoff ───────────────────────────────────'
Write-Host "  VNet Foundry ID   : $($outputs.vnetFoundryId.value)"
Write-Host "  AgentSubnet ID    : $($outputs.agentSubnetId.value)"
Write-Host "  PESubnet ID       : $($outputs.peSubnetId.value)"
Write-Host "  Storage name      : $($outputs.storageAccountName.value)"
Write-Host "  Search name       : $($outputs.searchServiceName.value)"
Write-Host "  Cosmos name       : $($outputs.cosmosAccountName.value)"
Write-Host ''
Write-Host '── VPN Gateways ─────────────────────────────────────────────'
Write-Host "  vpngw-foundry PIP : $($outputs.pipVpngwFoundryIp.value)"
Write-Host "  vpngw-onprem  PIP : $($outputs.pipVpngwOnpremIp.value)"
Write-Host ''
Write-Host '── VM IPs ────────────────────────────────────────────────────'
Write-Host "  vm-onprem-echo  : $($outputs.vmOnpremEchoIp.value)"
Write-Host "  vm-onprem-ctrl  : $($outputs.vmOnpremCtrlIp.value)"
Write-Host "  vm-diag         : $($outputs.vmDiagIp.value)"
Write-Host ''
Write-Host '── DNS Resolver ─────────────────────────────────────────────'
Write-Host "  Inbound EP IP   : $($outputs.dnsResolverInboundIp.value)"
Write-Host ''
Write-Host '  ➜ See portal-foundry-setup.md for next steps.'
Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Green
