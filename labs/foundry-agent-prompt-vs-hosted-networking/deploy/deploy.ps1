<#
.SYNOPSIS
    Deploy or validate the foundry-agent-prompt-vs-hosted-networking T1 peered-tools topology.

.DESCRIPTION
    Default mode: VALIDATE ONLY -- runs Bicep build + ARM deployment validate + ARM what-if.
    No Azure resources are created unless -Apply is explicitly specified AND the exact
    confirmation phrase "DEPLOY APPROVED" is typed at the prompt.

    Prerequisites (must exist in RG before validate/deploy):
      - vnet-foundry (192.168.0.0/16) with AgentSubnet, DNSInboundSubnet, DNSOutboundSubnet
      - nsg-agentsubnet (only when patchAgentSubnetNsg=true in parameters)
    These are deployed by the sibling lab (foundry-agent-reserved-prefix-reachability).

    Validate + what-if run against the ACTUAL lab RG (not a temp RG) because this template
    references existing resources in the RG. validate and what-if are non-destructive by design.

    Steps (validate-only mode):
      0  Verify Azure subscription
      1  Bicep build / lint
      2  Read SSH public key (placeholder used in validate-only if file absent)
      3  ARM deployment group validate (non-destructive; uses actual RG)
      4  ARM what-if (non-destructive; uses actual RG)

    Additional steps (apply mode only, requires -Apply AND "DEPLOY APPROVED" confirmation):
      5  az deployment group create (incremental; never deletes existing resources)
      6  Print handoff outputs

.PARAMETER Apply
    Switch: perform actual deployment. Without this, only validate + what-if run.
    Requires Gate B confirmation ("DEPLOY APPROVED") from Jose Moreno.

.PARAMETER RgName
    Target resource group name (REQUIRED -- must be the existing lab RG with vnet-foundry).

.PARAMETER RgLocation
    RG metadata region (default: swedencentral).

.PARAMETER CorrelationId
    Correlation ID for tagging (auto-generated if empty).

.PARAMETER AdminUsername
    VM admin username (default: labadmin).

.PARAMETER SshPubKeyPath
    Path to SSH public key file (default: ~/.ssh/id_rsa.pub).

.PARAMETER ExpectedSubName
    Expected subscription display name -- fails fast if wrong subscription is active.

.PARAMETER DeploymentName
    ARM deployment name (default: deploy-tools-<CorrelationId>).

.NOTES
    Lab     : foundry-agent-prompt-vs-hosted-networking
    Region  : swedencentral (all T1 resources)
    Cost    : ~$0.36/day VMs; +$3.36/day with DNS resolver; within $50/day guardrail
    Gate B  : Jose Moreno must state "DEPLOY APPROVED" before -Apply is used
    T2 cleanup: use cleanup.ps1 (separate gate; does not deploy T1 resources)
#>

[CmdletBinding()]
param(
    [Parameter()] [switch]$Apply,
    [Parameter(Mandatory)] [string]$RgName,
    [Parameter()] [string]$RgLocation    = 'swedencentral',
    [Parameter()] [string]$CorrelationId = '',
    [Parameter()] [string]$AdminUsername = 'labadmin',
    [Parameter()] [string]$SshPubKeyPath = '',
    [Parameter()] [string]$ExpectedSubName = '',
    [Parameter()] [string]$DeploymentName  = ''
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'

$LabName     = 'foundry-agent-prompt-vs-hosted-networking'
$TemplateDir = $PSScriptRoot
$MainBicep   = Join-Path $TemplateDir 'main.bicep'
$ParamsFile  = Join-Path $TemplateDir 'parameters\lab.parameters.json'

if ([string]::IsNullOrEmpty($CorrelationId)) {
    $CorrelationId = [System.Guid]::NewGuid().ToString('N').Substring(0, 8)
}
if ([string]::IsNullOrEmpty($SshPubKeyPath)) {
    $SshPubKeyPath = Join-Path $env:USERPROFILE '.ssh\id_rsa.pub'
}
if ([string]::IsNullOrEmpty($DeploymentName)) {
    $DeploymentName = "deploy-tools-$CorrelationId"
}

$Mode = if ($Apply) { 'DEPLOY (apply)' } else { 'VALIDATE-ONLY' }

Write-Host ''
Write-Host '==============================================================' -ForegroundColor Cyan
Write-Host " Tank -- $LabName" -ForegroundColor Cyan
Write-Host " Mode     : $Mode" -ForegroundColor Cyan
Write-Host " RG       : $RgName" -ForegroundColor Cyan
Write-Host " CorrID   : $CorrelationId" -ForegroundColor Cyan
Write-Host " Date     : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
if ($Apply) {
    Write-Host ' WARNING  : APPLY mode -- Azure resources will be created.' -ForegroundColor Yellow
    Write-Host ' WARNING  : Gate B (DEPLOY APPROVED) must be on record before proceeding.' -ForegroundColor Yellow
}
Write-Host '==============================================================' -ForegroundColor Cyan

# -- Step 0: Verify Azure subscription ----------------------------------------
Write-Host ''
Write-Host '[0] Verifying Azure subscription...' -ForegroundColor Yellow
$subJson = az account show -o json 2>&1
if ($LASTEXITCODE -ne 0) { throw "az account show failed. Run 'az login' first." }
$subInfo = $subJson | ConvertFrom-Json
$SubName = $subInfo.name
Write-Host "    Subscription: $SubName  ($($subInfo.id))" -ForegroundColor Green
if ($ExpectedSubName -and $SubName -ne $ExpectedSubName) {
    throw "Wrong subscription. Expected '$ExpectedSubName', got '$SubName'."
}

# Verify the target RG exists (prerequisites must be in place)
$rgCheck = az group show -n $RgName -o json 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Resource group '$RgName' not found. The sibling lab must be deployed first.`nCreate it with: az group create -n $RgName -l $RgLocation"
}
Write-Host "    RG '$RgName' confirmed." -ForegroundColor Green

# -- Step 1: Bicep build / lint -----------------------------------------------
Write-Host ''
Write-Host '[1] Building Bicep template...' -ForegroundColor Yellow
$buildOut = az bicep build --file $MainBicep --only-show-errors 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host $buildOut -ForegroundColor Red
    throw 'Bicep build FAILED'
}
Write-Host '    Bicep build OK.' -ForegroundColor Green

# -- Step 2: Read SSH public key -----------------------------------------------
Write-Host ''
Write-Host '[2] Reading SSH public key...' -ForegroundColor Yellow
$SshPubKey = ''
if (Test-Path $SshPubKeyPath) {
    $SshPubKey = (Get-Content $SshPubKeyPath -Raw).Trim()
    Write-Host "    SSH pubkey loaded from: $SshPubKeyPath" -ForegroundColor Green
} else {
    if (-not $Apply) {
        $SshPubKey = 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC+PLACEHOLDER+validate-only labadmin@validate'
        Write-Host '    Using placeholder SSH key (validate-only; key file not found).' -ForegroundColor Yellow
    } else {
        throw "SSH public key not found at '$SshPubKeyPath'. Provide -SshPubKeyPath or create ~/.ssh/id_rsa.pub."
    }
}

# -- Step 3: ARM deployment validate ------------------------------------------
# Runs against the ACTUAL lab RG (not a temp RG) because existing resource references
# (vnet-foundry, nsg-agentsubnet) must be resolved. validate is non-destructive.
Write-Host ''
Write-Host '[3] ARM deployment validate (non-destructive; existing RG)...' -ForegroundColor Yellow

$validateResult = az deployment group validate `
    --resource-group $RgName `
    --template-file $MainBicep `
    --parameters "@$ParamsFile" `
    --parameters adminUsername="$AdminUsername" `
    --parameters vmSshPublicKey="$SshPubKey" `
    --parameters correlationId="$CorrelationId" `
    --mode Incremental `
    --only-show-errors `
    -o json 2>&1
$validateExit = $LASTEXITCODE

if ($validateExit -ne 0) {
    Write-Host '===========================================================' -ForegroundColor Red
    Write-Host ' ARM VALIDATION FAILED' -ForegroundColor Red
    Write-Host '===========================================================' -ForegroundColor Red
    Write-Host ($validateResult | Out-String)
    throw 'Validation failed -- see output above.'
}
Write-Host '    ARM validation: PASS' -ForegroundColor Green

# -- Step 4: ARM what-if -------------------------------------------------------
Write-Host ''
Write-Host '[4] ARM what-if (plan; shows resources that would be created)...' -ForegroundColor Yellow

$whatIfOut = az deployment group what-if `
    --resource-group $RgName `
    --template-file $MainBicep `
    --parameters "@$ParamsFile" `
    --parameters adminUsername="$AdminUsername" `
    --parameters vmSshPublicKey="$SshPubKey" `
    --parameters correlationId="$CorrelationId" `
    --mode Incremental `
    --only-show-errors `
    --no-pretty-print 2>&1
$whatIfExit = $LASTEXITCODE

if ($whatIfExit -eq 0) {
    Write-Host '    What-if: PASS' -ForegroundColor Green
} else {
    Write-Host '    What-if: WARN (non-blocking -- review output below)' -ForegroundColor Yellow
}
Write-Host $whatIfOut

# -- Exit here if validate-only -----------------------------------------------
if (-not $Apply) {
    Write-Host ''
    Write-Host '==============================================================' -ForegroundColor Green
    Write-Host ' VALIDATE-ONLY complete. No resources created.' -ForegroundColor Green
    Write-Host " Re-run with -Apply to deploy (Gate B: DEPLOY APPROVED required)." -ForegroundColor Green
    Write-Host '==============================================================' -ForegroundColor Green
    exit 0
}

# =============================================================================
# APPLY -- Steps 5-6 run only when -Apply is passed
# Gate B: Jose Moreno must have stated "DEPLOY APPROVED" before this runs.
# =============================================================================

Write-Host ''
Write-Host '==============================================================' -ForegroundColor Red
Write-Host ' APPLY -- About to CREATE Azure resources (incremental)' -ForegroundColor Red
Write-Host "  RG: $RgName  ($RgLocation)" -ForegroundColor Red
Write-Host '  Gate B (DEPLOY APPROVED) must be on record.' -ForegroundColor Red
Write-Host '==============================================================' -ForegroundColor Red
Write-Host ''
$confirm = Read-Host "Type exactly 'DEPLOY APPROVED' to proceed"
if ($confirm -ne 'DEPLOY APPROVED') {
    Write-Host 'Confirmation phrase did not match. Aborted -- no resources created.' -ForegroundColor Yellow
    exit 0
}

# -- Step 5: Deploy -----------------------------------------------------------
Write-Host ''
Write-Host '[5] Deploying T1 resources (incremental mode)...' -ForegroundColor Yellow
$StartTime = Get-Date

$deployOut = az deployment group create `
    --resource-group $RgName `
    --template-file $MainBicep `
    --parameters "@$ParamsFile" `
    --parameters adminUsername="$AdminUsername" `
    --parameters vmSshPublicKey="$SshPubKey" `
    --parameters correlationId="$CorrelationId" `
    --name $DeploymentName `
    --mode Incremental `
    --only-show-errors `
    -o json 2>&1
$deployExit = $LASTEXITCODE
$Elapsed    = (Get-Date) - $StartTime

if ($deployExit -ne 0) {
    Write-Host '===========================================================' -ForegroundColor Red
    Write-Host ' DEPLOYMENT FAILED' -ForegroundColor Red
    Write-Host "  Elapsed: $($Elapsed.ToString('mm\:ss'))" -ForegroundColor Red
    Write-Host '===========================================================' -ForegroundColor Red
    Write-Host $deployOut
    throw "Deployment failed. Check partial resources in '$RgName' before cleanup."
}

$outputsJson = az deployment group show `
    --resource-group $RgName `
    --name $DeploymentName `
    --query properties.outputs `
    --only-show-errors `
    -o json 2>&1
$outputs = ($outputsJson | Out-String) | ConvertFrom-Json

# -- Step 6: Handoff outputs ---------------------------------------------------
Write-Host ''
Write-Host '==============================================================' -ForegroundColor Green
Write-Host " DEPLOYMENT COMPLETE  (elapsed: $($Elapsed.ToString('mm\:ss')))" -ForegroundColor Green
Write-Host '==============================================================' -ForegroundColor Green
Write-Host ''
Write-Host '-- T1 Resources Created ----------------------------'
Write-Host "  vnet-tools ID        : $($outputs.vnetToolsId.value)"
Write-Host "  vm-tools-echo IP     : $($outputs.vmToolsEchoIp.value)"
Write-Host "  vm-tools-ctrl IP     : $($outputs.vmToolsCtrlIp.value)"
Write-Host "  DNS resolver inbound : $($outputs.dnsResolverInboundIp.value)"
Write-Host ''
Write-Host '-- Wave 5 Verification (from vm-diag via Run Command) ------'
Write-Host '  curl http://10.1.100.4/api/echo?msg=wave5-verify'
Write-Host '  nslookup echo.tools.lab'
Write-Host ''
Write-Host '  See README.md for Wave 6 (hosted agent) and scenario steps.'
Write-Host '==============================================================' -ForegroundColor Green
