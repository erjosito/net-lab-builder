<#
.SYNOPSIS
    Deploys the msee-hairpin-hns-vwan-ipv6 lab (Tank, lab #3).

.DESCRIPTION
    Deploy wrapper for Path A: ER Direct port + 2 sub-circuits + MSEE hairpin
    between HnS hub and vWAN hub, dual-stack IPv4+IPv6.

    Steps:
      0. Rehydrate HKCU env vars (Windows child-process inheritance fix).
      1. Verify az account show returns the expected subscription.
      2. Fetch default-password from KV; set TF_VAR_vm_admin_password in-process.
      3. terraform init.
      4. terraform plan -out=tfplan; safety check for unexpected destroys.
      5. terraform apply tfplan.
      6. Print outputs.
      7. Post-deploy smoke test + Niobe handoff.

.NOTES
    Lab : msee-hairpin-hns-vwan-ipv6 (ER Direct hairpin, dual-stack)
    Sub : Resolved via az account show (NOT hardcoded)
    KV  : platform-secrets-1138 / RG platform / region swedencentral
    Cost: ~$22-25/day during 45-day ER Direct free-provisioning window
#>

[CmdletBinding()]
param(
    [Parameter()] [string]$KvName             = "platform-secrets-1138",
    [Parameter()] [string]$KvRg               = "platform",
    [Parameter()] [string]$ExpectedSubName    = "Litware-MngEnvMCAP642473-jomore",
    [Parameter()] [string]$CorrelationId      = "",
    [Parameter()] [switch]$AutoApprove,
    [Parameter()] [switch]$SkipInit
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"
$StartTime             = Get-Date

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..\")
$TfDir    = Join-Path $RepoRoot "src\terraform\msee-hairpin-hns-vwan-ipv6"

if (-not (Test-Path $TfDir)) {
    throw "Terraform directory not found at $TfDir"
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Tank — msee-hairpin-hns-vwan-ipv6 deploy (Path A)"         -ForegroundColor Cyan
Write-Host " Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"            -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Repo root : $RepoRoot"
Write-Host "TF dir    : $TfDir"
Write-Host "KV        : $KvName (RG $KvRg)"
Write-Host ""

# ---------------------------------------------------------------------------
# Step 0 — Rehydrate HKCU env vars (Tank charter: Windows child-process fix)
# ---------------------------------------------------------------------------
Write-Host "[0] Rehydrating HKCU env vars..." -ForegroundColor Yellow
$varsToRehydrate = @(
    'TF_VAR_vm_admin_password',
    'ARM_SUBSCRIPTION_ID',
    'AZURE_SUBSCRIPTION_ID'
)
foreach ($v in $varsToRehydrate) {
    $val = [System.Environment]::GetEnvironmentVariable($v, 'User')
    if ($val) {
        [System.Environment]::SetEnvironmentVariable($v, $val, 'Process')
        Write-Host "    Rehydrated: $v"
    }
}

# ---------------------------------------------------------------------------
# Step 1 — Verify Azure subscription
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[1] Verifying Azure subscription..." -ForegroundColor Yellow
$subJson = az account show -o json 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "az account show failed — run 'az login' first."
}
$sub = $subJson | ConvertFrom-Json
Write-Host "    Subscription : $($sub.name)"
Write-Host "    State        : $($sub.state)"

if ($sub.name -ne $ExpectedSubName) {
    Write-Warning "    Active subscription '$($sub.name)' differs from expected '$ExpectedSubName'."
    Write-Warning "    Proceeding — if wrong, Ctrl-C now and run: az account set --name '$ExpectedSubName'"
    Start-Sleep -Seconds 5
}
$env:ARM_SUBSCRIPTION_ID = $sub.id

# ---------------------------------------------------------------------------
# Step 2 — Fetch default-password from KV
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[2] Fetching default-password from Key Vault..." -ForegroundColor Yellow
Write-Host "    Vault : $KvName"
Write-Host "    NOTE  : If this fails with ACL error, pause GSA client first (Path A per decisions.md)."

$pw = (az keyvault secret show --vault-name $KvName --name "default-password" --query value -o tsv 2>&1)
if ($LASTEXITCODE -ne 0 -or -not $pw) {
    throw "Failed to fetch 'default-password' from KV '$KvName'. Error: $pw"
}
$env:TF_VAR_vm_admin_password = $pw
Write-Host "    Secret fetched — set as TF_VAR_vm_admin_password (in-process only, never written to file)."
$pw = $null  # Clear from local var

# ---------------------------------------------------------------------------
# Step 3 — Terraform init
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[3] Terraform init..." -ForegroundColor Yellow

if (-not $SkipInit) {
    Push-Location $TfDir
    try {
        terraform init -upgrade
        if ($LASTEXITCODE -ne 0) { throw "terraform init failed." }
    } finally {
        Pop-Location
    }
}

# ---------------------------------------------------------------------------
# Step 4 — Terraform plan
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[4] Terraform plan..." -ForegroundColor Yellow
$PlanFile = Join-Path $TfDir "tfplan"

Push-Location $TfDir
try {
    $planArgs = @("-out=tfplan")
    if ($CorrelationId) {
        $planArgs += "-var=correlation_id_override=$CorrelationId"
    }
    terraform plan @planArgs
    if ($LASTEXITCODE -ne 0) { throw "terraform plan failed." }

    # Safety check: abort if any destroy in a fresh deploy
    Write-Host ""
    Write-Host "    Checking plan for unexpected destroys..." -ForegroundColor Yellow
    $planText = terraform show tfplan
    $destroyLines = $planText | Select-String "will be destroyed"
    if ($destroyLines) {
        Write-Host ""
        Write-Host "⚠️  STOP: terraform plan shows resources will be destroyed:" -ForegroundColor Red
        $destroyLines | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
        Write-Host ""
        Write-Host "This is a fresh deploy — destroys are unexpected (state mismatch?)." -ForegroundColor Red
        Write-Host "Investigate before applying. Aborting." -ForegroundColor Red
        Pop-Location
        exit 1
    }
    Write-Host "    No destroys detected. Plan looks clean." -ForegroundColor Green
} finally {
    Pop-Location
}

# ---------------------------------------------------------------------------
# Step 5 — Terraform apply
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[5] Terraform apply..." -ForegroundColor Yellow

if (-not $AutoApprove) {
    $confirm = Read-Host "    Apply the plan? [yes/no]"
    if ($confirm -ne "yes") {
        Write-Host "    Aborted by operator." -ForegroundColor Yellow
        exit 0
    }
}

Push-Location $TfDir
try {
    terraform apply tfplan
    if ($LASTEXITCODE -ne 0) { throw "terraform apply failed." }
} finally {
    Pop-Location
}

$ApplyDuration = (Get-Date) - $StartTime
Write-Host ""
Write-Host "    Apply complete. Wall-clock: $($ApplyDuration.ToString('hh\:mm\:ss'))" -ForegroundColor Green

# ---------------------------------------------------------------------------
# Step 6 — Print outputs
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[6] Terraform outputs..." -ForegroundColor Yellow
Push-Location $TfDir
try {
    $outputJson = terraform output -json | ConvertFrom-Json
    $rg         = $outputJson.resource_group_name.value
    $corrId     = $outputJson.correlation_id.value
    $erPort     = $outputJson.er_port_name.value
    $erPortId   = $outputJson.er_port_id.value
    $circ1Id    = $outputJson.er_circuit_ids.value.circuit1_hns
    $circ2Id    = $outputJson.er_circuit_ids.value.circuit2_vwan
    $ergwHnsId  = $outputJson.ergw_hns_id.value
    $ergwVhubId = $outputJson.ergw_vhub_id.value
    $vmHnsPub   = $outputJson.vm_hns_public_ip.value
    $vmHnsPriv4 = $outputJson.vm_hns_private_ipv4.value
    $vmHnsPriv6 = $outputJson.vm_hns_private_ipv6.value
    $vmVwanPub  = $outputJson.vm_vwan_public_ip.value
    $vmVwanPriv4= $outputJson.vm_vwan_private_ipv4.value
    $vmVwanPriv6= $outputJson.vm_vwan_private_ipv6.value

    Write-Host ""
    Write-Host "  ┌─────────────────────────────────────────────────────────────┐" -ForegroundColor Cyan
    Write-Host "  │  Lab deploy summary                                         │" -ForegroundColor Cyan
    Write-Host "  ├─────────────────────────────────────────────────────────────┤" -ForegroundColor Cyan
    Write-Host ("  │  RG              : {0,-43} │" -f $rg) -ForegroundColor Cyan
    Write-Host ("  │  Correlation ID  : {0,-43} │" -f $corrId) -ForegroundColor Cyan
    Write-Host ("  │  ER Port         : {0,-43} │" -f $erPort) -ForegroundColor Cyan
    Write-Host ("  │  Circuit 1 (HnS) : {0,-43} │" -f $circ1Id.Split('/')[-1]) -ForegroundColor Cyan
    Write-Host ("  │  Circuit 2 (vWAN): {0,-43} │" -f $circ2Id.Split('/')[-1]) -ForegroundColor Cyan
    Write-Host ("  │  ergw-hns ID     : ...{0,-40} │" -f $ergwHnsId.Substring([Math]::Max(0,$ergwHnsId.Length-40))) -ForegroundColor Cyan
    Write-Host ("  │  ergw-vhub ID    : ...{0,-40} │" -f $ergwVhubId.Substring([Math]::Max(0,$ergwVhubId.Length-40))) -ForegroundColor Cyan
    Write-Host ("  │  vm-hns  pub     : {0,-43} │" -f $vmHnsPub) -ForegroundColor Cyan
    Write-Host ("  │  vm-hns  priv v4 : {0,-43} │" -f $vmHnsPriv4) -ForegroundColor Cyan
    Write-Host ("  │  vm-hns  priv v6 : {0,-43} │" -f $vmHnsPriv6) -ForegroundColor Cyan
    Write-Host ("  │  vm-vwan pub     : {0,-43} │" -f $vmVwanPub) -ForegroundColor Cyan
    Write-Host ("  │  vm-vwan priv v4 : {0,-43} │" -f $vmVwanPriv4) -ForegroundColor Cyan
    Write-Host ("  │  vm-vwan priv v6 : {0,-43} │" -f $vmVwanPriv6) -ForegroundColor Cyan
    Write-Host ("  │  Wall-clock      : {0,-43} │" -f $ApplyDuration.ToString('hh\:mm\:ss')) -ForegroundColor Cyan
    Write-Host "  └─────────────────────────────────────────────────────────────┘" -ForegroundColor Cyan

} finally {
    Pop-Location
}

# ---------------------------------------------------------------------------
# Step 7 — Post-deploy smoke test + Niobe handoff
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[7] Post-deploy smoke test..." -ForegroundColor Yellow
Write-Host "    Querying BGP peer status on ergw-hns (expect peers listed after circuit associate)..."

$bgpStatus = az network vnet-gateway list-bgp-peer-status `
    --resource-group $rg `
    --name ($outputJson.ergw_hns_id.value.Split('/')[-1]) `
    -o table 2>&1

Write-Host $bgpStatus

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " ✅ Niobe — Handoff"                                          -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host " RG      : $rg"
Write-Host " Region  : $($outputJson.location.value)"
Write-Host " ER port : $erPort"
Write-Host " Circ 1  : $($outputJson.er_circuit_names.value.circuit1_hns) (HnS GW)"
Write-Host " Circ 2  : $($outputJson.er_circuit_names.value.circuit2_vwan) (vWAN GW)"
Write-Host " Run validation per labs/msee-hairpin-hns-vwan-ipv6/validation.md"
Write-Host " S1: IPv4 ping vm-vwan → vm-hns ($vmHnsPriv4)"
Write-Host " S2: IPv6 ping vm-vwan → vm-hns ($vmHnsPriv6)"
Write-Host " S3: Route table captures on both GWs"
Write-Host " S4: Toggle disable/restore allowVirtualWanTraffic on ergw-hns"
Write-Host "============================================================" -ForegroundColor Green
