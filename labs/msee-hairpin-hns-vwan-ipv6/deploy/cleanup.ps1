<#
.SYNOPSIS
    Tears down the msee-hairpin-hns-vwan-ipv6 lab (Tank, lab #3).

.DESCRIPTION
    Belt-and-suspenders cleanup in the correct dependency order:
      ER connections → ER GWs → ER circuits → ER Direct port → rest of RG.

    Steps:
      0. Rehydrate HKCU env vars.
      1. terraform plan -destroy — show dry-run; operator must confirm.
      2. terraform apply tfdestroy.
      3. Belt-and-suspenders: az group delete --yes --no-wait.
      4. Purge soft-deleted KV if any, clean orphan PIPs, check role assignments.
      5. Verify RG gone.

.NOTES
    ER Direct port delete blocks if any circuit references it.
    TF destroy order handles this (circuits depend_on port in graph).
    Manual order if TF fails: connections → ER GWs → peerings → circuits → port.
#>

[CmdletBinding()]
param(
    [Parameter()] [string]$KvName          = "platform-secrets-1138",
    [Parameter()] [string]$KvRg            = "platform",
    [Parameter()] [switch]$AutoApprove,
    [Parameter()] [switch]$SkipTerraform
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..\")
$TfDir    = Join-Path $RepoRoot "src\terraform\msee-hairpin-hns-vwan-ipv6"

if (-not (Test-Path $TfDir)) {
    throw "Terraform directory not found at $TfDir"
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Red
Write-Host " Tank — msee-hairpin-hns-vwan-ipv6 CLEANUP"                  -ForegroundColor Red
Write-Host " Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"             -ForegroundColor Red
Write-Host "============================================================" -ForegroundColor Red

# ---------------------------------------------------------------------------
# Step 0 — Rehydrate HKCU env vars
# ---------------------------------------------------------------------------
Write-Host "[0] Rehydrating HKCU env vars..." -ForegroundColor Yellow
$varsToRehydrate = @(
    'TF_VAR_vm_admin_password',
    'ARM_SUBSCRIPTION_ID',
    'AZURE_SUBSCRIPTION_ID'
)
foreach ($v in $varsToRehydrate) {
    $val = [System.Environment]::GetEnvironmentVariable($v, 'User')
    if ($val) { [System.Environment]::SetEnvironmentVariable($v, $val, 'Process') }
}

# Need password for TF provider auth even during destroy
if (-not $env:TF_VAR_vm_admin_password) {
    Write-Host "    TF_VAR_vm_admin_password not in env — fetching from KV for TF auth..." -ForegroundColor Yellow
    $pw = (az keyvault secret show --vault-name $KvName --name "default-password" --query value -o tsv 2>&1)
    if ($LASTEXITCODE -eq 0 -and $pw) {
        $env:TF_VAR_vm_admin_password = $pw
        $pw = $null
    } else {
        Write-Warning "Could not fetch password from KV — TF destroy may prompt. Proceeding."
    }
}

# ---------------------------------------------------------------------------
# Step 1 — Terraform destroy plan (dry-run) + operator confirmation
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[1] Terraform destroy plan (dry-run)..." -ForegroundColor Yellow

Push-Location $TfDir
try {
    terraform plan -destroy -out=tfdestroy
    if ($LASTEXITCODE -ne 0) { throw "terraform plan -destroy failed." }
} finally {
    Pop-Location
}

if (-not $AutoApprove) {
    Write-Host ""
    Write-Host "⚠️  Review the destroy plan above carefully." -ForegroundColor Red
    Write-Host "    ER Direct port delete WILL fail if circuits are not destroyed first." -ForegroundColor Yellow
    Write-Host "    TF resource graph handles ordering — trust it unless state is corrupt." -ForegroundColor Yellow
    Write-Host ""
    $confirm = Read-Host "    Apply the destroy? [yes/no]"
    if ($confirm -ne "yes") {
        Write-Host "    Aborted by operator." -ForegroundColor Yellow
        exit 0
    }
}

# ---------------------------------------------------------------------------
# Step 2 — Terraform apply destroy
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[2] Terraform apply destroy..." -ForegroundColor Yellow

if (-not $SkipTerraform) {
    Push-Location $TfDir
    try {
        terraform apply tfdestroy
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "terraform apply destroy returned non-zero. Proceeding to belt-and-suspenders cleanup."
        }
    } finally {
        Pop-Location
    }
}

# Determine RG name from TF state if possible; fall back to pattern
Push-Location $TfDir
try {
    $outputJson = terraform output -json 2>$null | ConvertFrom-Json
    $rg = $outputJson.resource_group_name.value
} catch {
    $rg = $null
} finally {
    Pop-Location
}

if (-not $rg) {
    Write-Warning "Could not read RG from TF outputs — attempting to discover from az group list..."
    $rg = (az group list --query "[?starts_with(name,'rg-msee-hairpin-')].name" -o tsv 2>$null | Select-Object -First 1)
}

if (-not $rg) {
    Write-Warning "No RG found matching rg-msee-hairpin-*. Cleanup may already be complete."
}

# ---------------------------------------------------------------------------
# Step 3 — Belt-and-suspenders: az group delete
# ---------------------------------------------------------------------------
if ($rg) {
    Write-Host ""
    Write-Host "[3] Belt-and-suspenders: az group delete -n $rg --yes --no-wait..." -ForegroundColor Yellow
    $exists = (az group exists -n $rg)
    if ($exists -eq "true") {
        az group delete -n $rg --yes --no-wait
        Write-Host "    RG delete issued (async). Monitor with: az group show -n $rg"
    } else {
        Write-Host "    RG $rg already gone." -ForegroundColor Green
    }
}

# ---------------------------------------------------------------------------
# Step 4a — Purge soft-deleted Key Vaults (none expected — belt-and-suspenders)
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[4a] Checking for soft-deleted Key Vaults..." -ForegroundColor Yellow
$deletedKvs = az keyvault list-deleted --query "[].name" -o tsv 2>$null
if ($deletedKvs) {
    Write-Host "    Soft-deleted KVs found:" -ForegroundColor Yellow
    foreach ($kv in ($deletedKvs -split "`n" | Where-Object { $_ })) {
        Write-Host "    Purging: $kv"
        az keyvault purge --name $kv 2>&1 | Out-Null
        Write-Host "    Purged: $kv" -ForegroundColor Green
    }
} else {
    Write-Host "    No soft-deleted KVs. Clean." -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Step 4b — Check for orphan PIPs in subscription matching lab pattern
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[4b] Checking for orphan PIPs (pattern: pip-*-hairpin-* or pip-ergw-hns-*)..." -ForegroundColor Yellow
if ($rg) {
    $rgExists = (az group exists -n $rg)
    if ($rgExists -eq "true") {
        $orphanPips = az network public-ip list -g $rg --query "[?ipConfiguration==null].name" -o tsv 2>$null
        if ($orphanPips) {
            Write-Host "    Orphan PIPs found in $rg:" -ForegroundColor Yellow
            foreach ($pip in ($orphanPips -split "`n" | Where-Object { $_ })) {
                Write-Host "    Deleting: $pip"
                az network public-ip delete -g $rg -n $pip --yes 2>&1 | Out-Null
            }
        } else {
            Write-Host "    No orphan PIPs." -ForegroundColor Green
        }
    } else {
        Write-Host "    RG already gone — no orphan PIPs to check." -ForegroundColor Green
    }
}

# ---------------------------------------------------------------------------
# Step 4c — Check role assignments at subscription scope
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[4c] Checking role assignments at subscription scope (none expected for this lab)..." -ForegroundColor Yellow
$subId = (az account show --query id -o tsv)
$roleAssignments = az role assignment list --scope "/subscriptions/$subId" `
    --query "[?contains(description,'msee-hairpin')].{name:name,role:roleDefinitionName,principal:principalName}" `
    -o table 2>$null
if ($roleAssignments -and $roleAssignments -notmatch "^$") {
    Write-Host "    Role assignments found — review:" -ForegroundColor Yellow
    Write-Host $roleAssignments
} else {
    Write-Host "    No lab-tagged role assignments at subscription scope. Clean." -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Step 5 — Verify RG gone
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[5] Cleanup verification..." -ForegroundColor Yellow
if ($rg) {
    $maxWait = 60  # seconds
    $elapsed = 0
    $gone = $false
    while ($elapsed -lt $maxWait) {
        $rgExists = (az group exists -n $rg)
        if ($rgExists -eq "false") {
            $gone = $true
            break
        }
        Write-Host "    RG $rg still exists — waiting (${elapsed}s / ${maxWait}s)..."
        Start-Sleep -Seconds 10
        $elapsed += 10
    }
    if ($gone) {
        Write-Host "    ✅ RG $rg is gone." -ForegroundColor Green
    } else {
        Write-Host "    ⏳ RG $rg still deleting (async). Re-run: az group exists -n $rg" -ForegroundColor Yellow
        Write-Host "    NOTE: ER Direct port may take extra minutes to release." -ForegroundColor Yellow
    }
} else {
    Write-Host "    RG name unknown — verify manually." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " Cleanup complete (or async in-progress)."                    -ForegroundColor Green
Write-Host " ER port note: if RG delete fails, check circuits are gone." -ForegroundColor Yellow
Write-Host " Order: connections → ER GWs → peerings → circuits → port"   -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Green
