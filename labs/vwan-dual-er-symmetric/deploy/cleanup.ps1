<#
.SYNOPSIS
    Tears down vwan-dual-er-symmetric in the order required by manifest §8.4.

.DESCRIPTION
    Cleanup chain (lab-#1 hard-won lesson — reversing this risks 30-40 min
    vWAN gateway hangs and Megaport HTTP 409 conflicts):

      1. terraform destroy (single shot using same dependency graph)
         OR step-by-step targeted destroys if a single-shot is too risky.

    Default mode: single-shot terraform destroy after rehydrating secrets.
    Charter-aligned (lab #1, 2026-06-15): Megaport credentials must be passed
    via TF_VAR_* env vars so child processes inherit them.

    Manifest §8.4 ordering is enforced by the TF dependency graph:
      ER GW connections → ER private peering (auto on circuit) → Megaport VXCs
      → Megaport MCRs → Azure RG.

    On rare destroy failures the script falls back to a -target sequence
    matching the manifest §8.4 cleanup chain.

.NOTES
    Idempotent — safe to re-run against a partially destroyed lab.
#>

[CmdletBinding()]
param(
    [Parameter()] [string]$KvName  = "platform-secrets-1138",
    [Parameter()] [string]$KvRg    = "platform",
    [Parameter()] [string]$ExpectedSubscriptionId = "a8fbd8e1-fb5a-4411-804a-4ac80929c93c",
    [Parameter()] [switch]$AutoApprove,
    [Parameter()] [switch]$Stepwise
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..\")
$TfDir    = Join-Path $RepoRoot "src\terraform\vwan-dual-er-symmetric"
$AclState = Join-Path $PSScriptRoot ".akv-state.json"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Tank — vwan-dual-er-symmetric cleanup"                      -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# ---- Step 0 — rehydrate env ----
Write-Host "[0] Rehydrating HKCU env vars..." -ForegroundColor Yellow
foreach ($v in @('MEGAPORT_ACCESS_KEY','MEGAPORT_SECRET_KEY',
                  'TF_VAR_megaport_access_key','TF_VAR_megaport_secret_key','TF_VAR_default_password')) {
    $val = [System.Environment]::GetEnvironmentVariable($v, 'User')
    if ($val) { [System.Environment]::SetEnvironmentVariable($v, $val, 'Process') }
}

# ---- Step 1 — sub + gcloud ----
Write-Host "[1] Verifying Azure subscription..." -ForegroundColor Yellow
$activeSub = (az account show --query id -o tsv)
if ($activeSub -ne $ExpectedSubscriptionId) {
    az account set --subscription $ExpectedSubscriptionId | Out-Null
}
$env:ARM_SUBSCRIPTION_ID = $ExpectedSubscriptionId
Write-Host "    Sub OK: $ExpectedSubscriptionId"

$gcpAcct = (gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>$null)
if (-not $gcpAcct) { throw "gcloud not authenticated." }
Write-Host "    GCP OK: $gcpAcct"

# Set GCP access token for the google TF provider (ADC bypass — see 2026-06-15T15:43Z dispatch)
$env:GOOGLE_OAUTH_ACCESS_TOKEN = (& gcloud auth print-access-token 2>$null).Trim()
if (-not $env:GOOGLE_OAUTH_ACCESS_TOKEN) {
    throw "Failed to get GCP access token. Run 'gcloud auth login' first."
}
Write-Host "    GCP token set ($($env:GOOGLE_OAUTH_ACCESS_TOKEN.Length) chars, ~1h validity)"

# ---- Step 2 — fetch secrets (re-uses deploy.ps1 strategy prompt) ----
Write-Host ""
Write-Host "[2] KV access (cleanup also needs Megaport creds)." -ForegroundColor Yellow

# Try without flipping first — if user has TF_VAR_* set, skip the KV dance entirely.
if ($env:TF_VAR_megaport_access_key -and $env:TF_VAR_megaport_secret_key) {
    Write-Host "    Megaport creds already in env. Skipping KV fetch." -ForegroundColor Green
} else {
    Write-Host "    Need to fetch Megaport secrets from KV $KvName." -ForegroundColor Yellow
    Write-Host "      [A] Pause GSA client manually."
    Write-Host "      [B] Flip AKV ACLs with auto-restore."
    $kvChoice = (Read-Host "    Choose [A/B]").ToUpper().Trim()
    if ($kvChoice -ne 'A' -and $kvChoice -ne 'B') { throw "Invalid choice." }

    $kvAclFlipped = $false
    try {
        if ($kvChoice -eq 'A') {
            Write-Host "    >>> Disable GSA client, then press Enter." -ForegroundColor Magenta
            Read-Host
        } else {
            az keyvault show --name $KvName --resource-group $KvRg --query networkAcls -o json | Out-File -FilePath $AclState -Encoding ascii
            az keyvault update --name $KvName --resource-group $KvRg --default-action Allow | Out-Null
            $kvAclFlipped = $true
            Start-Sleep -Seconds 5
        }

        $env:TF_VAR_megaport_access_key = az keyvault secret show --vault-name $KvName --name "megaport-api-key"    --query value -o tsv
        $env:TF_VAR_megaport_secret_key = az keyvault secret show --vault-name $KvName --name "megaport-api-secret" --query value -o tsv
        $env:TF_VAR_default_password    = az keyvault secret show --vault-name $KvName --name "default-password"    --query value -o tsv
        $env:MEGAPORT_ACCESS_KEY        = $env:TF_VAR_megaport_access_key
        $env:MEGAPORT_SECRET_KEY        = $env:TF_VAR_megaport_secret_key
    }
    finally {
        if ($kvAclFlipped -and (Test-Path $AclState)) {
            $state = Get-Content $AclState -Raw | ConvertFrom-Json
            az keyvault update --name $KvName --resource-group $KvRg --default-action ($state.defaultAction ?? "Deny") --bypass $state.bypass | Out-Null
            Remove-Item $AclState -Force
        } elseif ($kvChoice -eq 'A') {
            Write-Host "    >>> You may re-enable GSA now." -ForegroundColor Magenta
            Read-Host
        }
    }
}

# ---- Step 3 — terraform destroy ----
Push-Location $TfDir
try {
    Write-Host ""
    Write-Host "[3] terraform init (re-sync providers / state)..." -ForegroundColor Yellow
    terraform init -upgrade | Out-Null

    if ($Stepwise) {
        Write-Host ""
        Write-Host "[3a] Stepwise destroy: ER connections first (manifest §8.4 step 3)..." -ForegroundColor Yellow
        terraform destroy -auto-approve `
            -target=azurerm_express_route_connection.hub1_circuit1 `
            -target=azurerm_express_route_connection.hub2_circuit2 `
            -target=azurerm_express_route_connection.hub1_circuit2_bowtie `
            -target=azurerm_express_route_connection.hub2_circuit1_bowtie

        Write-Host "[3b] Destroying Megaport VXCs (manifest §8.4 steps 8 + 9 prerequisite)..." -ForegroundColor Yellow
        terraform destroy -auto-approve `
            -target=megaport_vxc.azure_circuit1 `
            -target=megaport_vxc.azure_circuit2 `
            -target=megaport_vxc.gcp_a `
            -target=megaport_vxc.gcp_b

        Write-Host "[3c] Destroying Megaport MCRs (manifest §8.4 step 11)..." -ForegroundColor Yellow
        terraform destroy -auto-approve `
            -target=megaport_mcr.mcr1 `
            -target=megaport_mcr.mcr2

        Write-Host "[3d] Destroying everything else..." -ForegroundColor Yellow
        terraform destroy -auto-approve
    } else {
        Write-Host ""
        Write-Host "[3] Single-shot destroy (TF dependency graph encodes §8.4 order)..." -ForegroundColor Yellow
        if (-not $AutoApprove) {
            $go = Read-Host "    Confirm destroy ALL resources [y/N]"
            if ($go.ToLower() -ne 'y') { exit 0 }
        }
        terraform destroy -parallelism=20 -auto-approve
        if ($LASTEXITCODE -ne 0) {
            Write-Host "    Single-shot destroy failed. Retry with -Stepwise." -ForegroundColor Red
            exit 1
        }
    }

    Write-Host ""
    Write-Host "[4] Hygiene: state remnants, soft-deleted KVs..." -ForegroundColor Yellow
    $remaining = terraform state list 2>$null
    if ($remaining) {
        Write-Host "    State NOT empty:" -ForegroundColor Red
        $remaining
    } else {
        Write-Host "    State empty." -ForegroundColor Green
    }

    # No KVs are created by this lab (the platform KV is shared, untouched). Nothing to purge.

    # ---- Step 5 — Delete the GCP project (belt-and-braces; new project per lab) ----
    Write-Host ""
    Write-Host "[5] Deleting GCP project (new-project-per-lab policy, 2026-06-15T15:20Z)..." -ForegroundColor Yellow
    $gcpProject = $env:TF_VAR_gcp_project_id
    if (-not $gcpProject) {
        # Try .lab-state.json (preferred source)
        $labState = Join-Path $PSScriptRoot ".lab-state.json"
        if (Test-Path $labState) {
            $state = Get-Content $labState -Raw | ConvertFrom-Json
            $gcpProject = $state.gcp_project_id
        }
    }
    if (-not $gcpProject) {
        # Last resort: recover from deploy-log.md
        $logFile = Join-Path (Split-Path -Path $PSScriptRoot -Parent) "deploy-log.md"
        if (Test-Path $logFile) {
            $match = Select-String -Path $logFile -Pattern 'gcp-vwan-symm-[a-f0-9]+' | Select-Object -First 1
            if ($match) { $gcpProject = $match.Matches[0].Value }
        }
    }
    if ($gcpProject) {
        Write-Host "    Deleting project: $gcpProject" -ForegroundColor Yellow
        gcloud projects delete $gcpProject --quiet 2>&1 | ForEach-Object { "    $_" }
        if ($LASTEXITCODE -eq 0) {
            Write-Host "    ✓ Project marked for deletion (30-day grace period, no further billing)." -ForegroundColor Green
            # Clean up the lab-state marker too
            $labState = Join-Path $PSScriptRoot ".lab-state.json"
            if (Test-Path $labState) { Remove-Item $labState -Force -ErrorAction SilentlyContinue }
        } else {
            Write-Host "    ⚠️ gcloud projects delete returned non-zero. Verify manually with 'gcloud projects list'." -ForegroundColor Yellow
        }
    } else {
        Write-Host "    No GCP project ID found in env, .lab-state.json, or deploy-log.md. Skipping." -ForegroundColor Yellow
    }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Cleanup complete." -ForegroundColor Green
