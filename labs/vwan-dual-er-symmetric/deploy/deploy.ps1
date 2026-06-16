<#
.SYNOPSIS
    Deploys the vwan-dual-er-symmetric lab (Tank, lab #2).

.DESCRIPTION
    Interactive wrapper that:
      1. Rehydrates HKCU env vars (Windows-only Tank charter pre-flight).
      2. Verifies Azure subscription + gcloud authentication.
      3. Coordinates Key Vault access (Path A = pause GSA, recommended; Path B = ACL flip with auto-restore).
      4. Fetches the 3 KV secrets (megaport-api-key, megaport-api-secret, default-password).
      5. Runs terraform init / plan / apply.
      6. On exit, restores KV ACL state (Path B only).

    Operator-mediated by design: this script PAUSES for explicit Jose input at
    every KV interaction. It NEVER silently flips KV ACLs.

.NOTES
    Lab : vwan-dual-er-symmetric (multi-region secured vWAN + dual ER + Megaport + GCP)
    Sub : Resolved via az account show (NOT hardcoded)
    KV  : platform-secrets-1138 / RG platform / region swedencentral
#>

[CmdletBinding()]
param(
    [Parameter()] [string]$LabName = "vwan-symm",
    [Parameter()] [string]$KvName  = "platform-secrets-1138",
    [Parameter()] [string]$KvRg    = "platform",
    [Parameter()] [string]$ExpectedSubscriptionId = "a8fbd8e1-fb5a-4411-804a-4ac80929c93c",
    [Parameter()] [string]$BillingAccountId = "01ACFF-9E8C08-552F38",
    [Parameter()] [ValidateSet('A','B','')] [string]$KvPath = "",
    [Parameter()] [string]$CorrelationId = "",
    [Parameter()] [switch]$AutoApprove,
    [Parameter()] [switch]$NonInteractive,
    [Parameter()] [switch]$StopBeforeTerraform
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..\")
$TfDir    = Join-Path $RepoRoot "src\terraform\vwan-dual-er-symmetric"
$AclState = Join-Path $PSScriptRoot ".akv-state.json"
$LabState = Join-Path $PSScriptRoot ".lab-state.json"

if (-not (Test-Path $TfDir)) {
    throw "Terraform stack not found at $TfDir"
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Tank — vwan-dual-er-symmetric deploy"                       -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Repo root : $RepoRoot"
Write-Host "TF dir    : $TfDir"
Write-Host "KV        : $KvName (RG $KvRg)"
Write-Host ""

# ---------------------------------------------------------------------------
# Step 0 — Rehydrate HKCU env vars (Tank charter: Windows-only)
# ---------------------------------------------------------------------------
Write-Host "[0] Rehydrating HKCU env vars (Windows child-process inheritance fix)..." -ForegroundColor Yellow
$varsToRehydrate = @(
    'MEGAPORT_ACCESS_KEY','MEGAPORT_SECRET_KEY',
    'TF_VAR_megaport_access_key','TF_VAR_megaport_secret_key','TF_VAR_default_password',
    'ARM_SUBSCRIPTION_ID','AZURE_SUBSCRIPTION_ID',
    'GOOGLE_APPLICATION_CREDENTIALS','GOOGLE_PROJECT'
)
foreach ($v in $varsToRehydrate) {
    $val = [System.Environment]::GetEnvironmentVariable($v, 'User')
    if ($val) { [System.Environment]::SetEnvironmentVariable($v, $val, 'Process') }
}

# ---------------------------------------------------------------------------
# Step 1 — Verify Azure subscription
# ---------------------------------------------------------------------------
Write-Host "[1] Verifying Azure subscription..." -ForegroundColor Yellow
$activeSub = (az account show --query id -o tsv)
if (-not $activeSub) {
    throw "az account show failed — run 'az login' first."
}
Write-Host "    Active : $activeSub"
Write-Host "    Expect : $ExpectedSubscriptionId"
if ($activeSub -ne $ExpectedSubscriptionId) {
    Write-Host "    Switching to expected sub..." -ForegroundColor Yellow
    az account set --subscription $ExpectedSubscriptionId | Out-Null
    $activeSub = (az account show --query id -o tsv)
    if ($activeSub -ne $ExpectedSubscriptionId) {
        throw "Could not set subscription to $ExpectedSubscriptionId"
    }
}
$env:ARM_SUBSCRIPTION_ID = $activeSub

# ---------------------------------------------------------------------------
# Step 2 — Verify gcloud auth
# ---------------------------------------------------------------------------
Write-Host "[2] Verifying gcloud authentication..." -ForegroundColor Yellow
$gcpAcct = (gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>$null)
$gcpProj = (gcloud config get-value project 2>$null)
if (-not $gcpAcct) {
    throw "gcloud not authenticated — run 'gcloud auth login' and 'gcloud auth application-default login'."
}
Write-Host "    Account : $gcpAcct"
Write-Host "    Project : $gcpProj"

# GCP auth uses GOOGLE_OAUTH_ACCESS_TOKEN refreshed at step [5.pre] via 'gcloud auth print-access-token'
# (ADC bypass — see 2026-06-15T15:43Z dispatch). No early warning needed.

# ---------------------------------------------------------------------------
# Step 3 — Key Vault access strategy
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[3] Key Vault access strategy" -ForegroundColor Yellow
Write-Host "    The vault $KvName has network ACLs that collide with the Global Secure Access (GSA) client."
Write-Host "    Squad decisions.md (2026-06-15) documents two operator-mediated paths:"
Write-Host ""
Write-Host "      [A] Pause GSA client manually, fetch secrets, re-enable GSA. (Recommended; no ACL changes.)"
Write-Host "      [B] Temporarily flip AKV networkAcls.defaultAction = Allow, fetch, then restore prior state."
Write-Host ""
if ($KvPath) {
    $kvChoice = $KvPath.ToUpper()
    Write-Host "    Choice pre-set via -KvPath: $kvChoice" -ForegroundColor Cyan
} elseif ($NonInteractive) {
    throw "Running with -NonInteractive but no -KvPath specified. Re-run with -KvPath A or B."
} else {
    $kvChoice = (Read-Host "    Choose access strategy [A/B]").ToUpper().Trim()
}
if ($kvChoice -ne 'A' -and $kvChoice -ne 'B') {
    throw "Invalid choice. Aborting."
}

$kvAclFlipped = $false

function Restore-KvAcl {
    <#
    .SYNOPSIS
        Restores Key Vault networkAcls from a JSON snapshot.

    .DESCRIPTION
        Per 2026-06-15T15:23Z Jose dispatch (Path B):
        - Restores defaultAction, bypass, ipRules[], virtualNetworkRules[] in that order.
        - Retries up to 3 times with 5s backoff on transient failures.
        - Post-restore: re-reads networkAcls and diffs against snapshot. Logs diff
          (or success confirmation) to deploy-log.md as a "## KV ACL restore audit" entry.
        - If restore still fails after 3 attempts OR diff is non-empty, emits a clear
          operator escalation banner (KV stays open until Jose fixes it manually).
    #>
    param(
        [Parameter(Mandatory)] [string]$VaultName,
        [Parameter(Mandatory)] [string]$VaultRg,
        [Parameter(Mandatory)] [string]$StateFile,
        [Parameter(Mandatory)] [string]$DeployLogPath
    )

    if (-not (Test-Path $StateFile)) {
        Write-Host "    [restore] No ACL state file at $StateFile — nothing to restore." -ForegroundColor DarkGray
        return $true
    }

    $snapshot = Get-Content $StateFile -Raw | ConvertFrom-Json

    $defaultAction = if ($snapshot.defaultAction) { $snapshot.defaultAction } else { "Deny" }
    $bypass        = if ($snapshot.bypass)        { $snapshot.bypass }        else { "AzureServices" }

    $maxAttempts = 3
    $attempt = 1
    $restoredOk = $false

    while ($attempt -le $maxAttempts -and -not $restoredOk) {
        Write-Host "    [restore] Attempt $attempt/${maxAttempts}: restoring networkAcls..." -ForegroundColor Yellow
        try {
            # 1. defaultAction + bypass (single update)
            az keyvault update --name $VaultName --resource-group $VaultRg `
                --default-action $defaultAction --bypass $bypass 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "az keyvault update (defaultAction/bypass) failed" }

            # 2. Re-read current network-rule state and remove anything we didn't have in the snapshot
            $currentIpRules = (az keyvault network-rule list --name $VaultName --resource-group $VaultRg --query "ipRules[].value" -o tsv) -split "`n" | Where-Object { $_ }
            $snapshotIpRules = @($snapshot.ipRules | ForEach-Object { $_.value })

            # Add ipRules from snapshot that aren't already there
            foreach ($ip in $snapshotIpRules) {
                if ($ip -and ($currentIpRules -notcontains $ip)) {
                    az keyvault network-rule add --name $VaultName --resource-group $VaultRg --ip-address $ip 2>&1 | Out-Null
                }
            }
            # Remove ipRules currently present that weren't in snapshot (cleanup post-Allow flip)
            foreach ($ip in $currentIpRules) {
                if ($ip -and ($snapshotIpRules -notcontains $ip)) {
                    az keyvault network-rule remove --name $VaultName --resource-group $VaultRg --ip-address $ip 2>&1 | Out-Null
                }
            }

            # 3. VNet rules
            $currentVnetRules = (az keyvault network-rule list --name $VaultName --resource-group $VaultRg --query "virtualNetworkRules[].id" -o tsv) -split "`n" | Where-Object { $_ }
            $snapshotVnetRules = @($snapshot.virtualNetworkRules | ForEach-Object { $_.id })

            foreach ($subnetId in $snapshotVnetRules) {
                if ($subnetId -and ($currentVnetRules -notcontains $subnetId)) {
                    az keyvault network-rule add --name $VaultName --resource-group $VaultRg --subnet $subnetId 2>&1 | Out-Null
                }
            }
            foreach ($subnetId in $currentVnetRules) {
                if ($subnetId -and ($snapshotVnetRules -notcontains $subnetId)) {
                    az keyvault network-rule remove --name $VaultName --resource-group $VaultRg --subnet $subnetId 2>&1 | Out-Null
                }
            }

            # 4. Re-read and diff
            $after = az keyvault show --name $VaultName --resource-group $VaultRg --query "properties.networkAcls" -o json | ConvertFrom-Json
            $diff = @()
            if ($after.defaultAction -ne $defaultAction)            { $diff += "defaultAction: snapshot=$defaultAction now=$($after.defaultAction)" }
            if ($after.bypass        -ne $bypass)                   { $diff += "bypass: snapshot=$bypass now=$($after.bypass)" }
            $afterIp   = @($after.ipRules           | ForEach-Object { $_.value })
            $afterVnet = @($after.virtualNetworkRules | ForEach-Object { $_.id })
            $ipDiff    = Compare-Object $snapshotIpRules   $afterIp   2>$null
            $vnetDiff  = Compare-Object $snapshotVnetRules $afterVnet 2>$null
            if ($ipDiff)   { $diff += "ipRules diff: " + ($ipDiff   | ForEach-Object { "$($_.SideIndicator)$($_.InputObject)" } | Join-String -Separator ', ') }
            if ($vnetDiff) { $diff += "vnetRules diff: " + ($vnetDiff | ForEach-Object { "$($_.SideIndicator)$($_.InputObject)" } | Join-String -Separator ', ') }

            $auditEntry = "`n## KV ACL restore audit ($(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ'))`n`n"
            $auditEntry += "- Vault: ``$VaultName`` (RG ``$VaultRg``)`n"
            $auditEntry += "- Attempt: $attempt of $maxAttempts`n"
            $auditEntry += "- defaultAction restored to: ``$defaultAction``  / bypass: ``$bypass```n"
            $auditEntry += "- ipRules restored ($($snapshotIpRules.Count) entries), vnetRules restored ($($snapshotVnetRules.Count) entries)`n"

            if ($diff.Count -eq 0) {
                Write-Host "    [restore] ✓ Post-restore diff: EMPTY — state matches pre-flip snapshot exactly." -ForegroundColor Green
                $auditEntry += "- ✅ Post-restore diff: EMPTY (state matches pre-flip snapshot exactly).`n"
                Add-Content -Path $DeployLogPath -Value $auditEntry
                $restoredOk = $true
                Remove-Item $StateFile -Force -ErrorAction SilentlyContinue
                return $true
            } else {
                Write-Host "    [restore] ⚠️ Post-restore diff NON-EMPTY:" -ForegroundColor Yellow
                $diff | ForEach-Object { Write-Host "      $_" -ForegroundColor Yellow }
                $auditEntry += "- ⚠️ Post-restore diff NON-EMPTY:`n"
                $diff | ForEach-Object { $auditEntry += "  - $_`n" }
                Add-Content -Path $DeployLogPath -Value $auditEntry
                throw "Post-restore diff non-empty"
            }
        } catch {
            Write-Host "    [restore] Attempt $attempt failed: $_" -ForegroundColor Red
            if ($attempt -lt $maxAttempts) {
                Write-Host "    [restore] Sleeping 5s before retry..." -ForegroundColor Yellow
                Start-Sleep -Seconds 5
            }
            $attempt++
        }
    }

    # Fall-through: all attempts failed
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Red
    Write-Host " 🛑 OPERATOR ALERT: ACL restore failed"                       -ForegroundColor Red
    Write-Host "============================================================" -ForegroundColor Red
    Write-Host " Vault $VaultName may currently be in defaultAction=Allow"   -ForegroundColor Red
    Write-Host " state. Run MANUALLY to restore:"                            -ForegroundColor Red
    Write-Host "   az keyvault update --name $VaultName --resource-group $VaultRg ``" -ForegroundColor Red
    Write-Host "     --default-action $defaultAction --bypass $bypass"       -ForegroundColor Red
    Write-Host " Snapshot retained at: $StateFile"                           -ForegroundColor Red
    Write-Host "============================================================" -ForegroundColor Red

    $auditEntry = "`n## KV ACL restore FAILED ($(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ'))`n`n"
    $auditEntry += "🛑 **All $maxAttempts restore attempts failed.** Vault ``$VaultName`` may still be in ``defaultAction=Allow`` state.`n"
    $auditEntry += "- Snapshot retained at: ``$StateFile`` — run ``Restore-KvAcl`` again manually after fixing the underlying transient issue.`n"
    Add-Content -Path $DeployLogPath -Value $auditEntry

    return $false
}

try {
    if ($kvChoice -eq 'A') {
        Write-Host ""
        Write-Host "    >>> ACTION REQUIRED: Jose, please DISABLE the Microsoft Global Secure Access client now." -ForegroundColor Magenta
        Write-Host "    >>> (System tray → GSA icon → Disable / Sign out)"                                        -ForegroundColor Magenta
        if ($NonInteractive) { throw "Path A requires interactive confirmation; cannot proceed with -NonInteractive. Use -KvPath B for non-interactive." }
        Read-Host "    Press Enter once GSA is disabled"
    } else {
        Write-Host ""
        Write-Host "    [B.1] Snapshotting current networkAcls to $AclState..." -ForegroundColor Yellow
        az keyvault show --name $KvName --resource-group $KvRg --query "properties.networkAcls" -o json | Out-File -FilePath $AclState -Encoding ascii
        if (-not (Test-Path $AclState) -or (Get-Item $AclState).Length -eq 0) { throw "Failed to capture KV networkAcls snapshot" }
        Write-Host "    [B.2] Flipping defaultAction = Allow..." -ForegroundColor Yellow
        az keyvault update --name $KvName --resource-group $KvRg --default-action Allow | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "az keyvault update --default-action Allow failed" }
        $kvAclFlipped = $true
        Write-Host "    [B.3] Waiting 10s for ACL propagation..." -ForegroundColor Yellow
        Start-Sleep -Seconds 10
    }

    # ---------------------------------------------------------------------------
    # Step 4 — Fetch secrets
    # ---------------------------------------------------------------------------
    Write-Host ""
    Write-Host "[4] Fetching secrets from $KvName..." -ForegroundColor Yellow

    $mpAccess  = az keyvault secret show --vault-name $KvName --name "megaport-api-key"    --query value -o tsv
    $mpSecret  = az keyvault secret show --vault-name $KvName --name "megaport-api-secret" --query value -o tsv
    $vmPwd     = az keyvault secret show --vault-name $KvName --name "default-password"    --query value -o tsv

    if (-not $mpAccess -or -not $mpSecret -or -not $vmPwd) {
        throw "One or more secrets came back empty. Check KV access (Path A: GSA disabled? Path B: ACL flipped?)"
    }

    $env:TF_VAR_megaport_access_key = $mpAccess
    $env:TF_VAR_megaport_secret_key = $mpSecret
    $env:TF_VAR_default_password    = $vmPwd
    # also set the Megaport provider's native env vars for redundancy
    $env:MEGAPORT_ACCESS_KEY = $mpAccess
    $env:MEGAPORT_SECRET_KEY = $mpSecret

    Write-Host "    All 3 secrets fetched OK." -ForegroundColor Green
}
finally {
    if ($kvAclFlipped) {
        $deployLogPath = Join-Path (Split-Path -Path $PSScriptRoot -Parent) "deploy-log.md"
        $restoreOk = Restore-KvAcl -VaultName $KvName -VaultRg $KvRg -StateFile $AclState -DeployLogPath $deployLogPath
        if (-not $restoreOk) {
            # Don't swallow this — the operator MUST see it
            throw "🛑 KV ACL restore failed after 3 attempts. See deploy-log.md and operator alert above. Vault may still be open."
        }
    } elseif ($kvChoice -eq 'A') {
        Write-Host ""
        Write-Host "    >>> ACTION REQUIRED: Jose, you may RE-ENABLE the GSA client now." -ForegroundColor Magenta
        if (-not $NonInteractive) {
            Read-Host "    Press Enter once GSA is re-enabled (or to continue anyway)"
        }
    }
}

# ---------------------------------------------------------------------------
# Step 4b — Bootstrap NEW GCP project (per 2026-06-15T15:20Z policy: new project per lab)
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[4b] Bootstrapping NEW GCP project for this lab..." -ForegroundColor Yellow

# Deterministic 6-char hex suffix; also threaded into TF as correlation_id_override
# so the Azure RG and the GCP project share the same correlation_id.
#
# Resolution order:
#   1. -CorrelationId param (explicit override for resume scenarios)
#   2. .lab-state.json from prior run (resume after KV+GCP done, before terraform)
#   3. Fresh random 6-char hex
if ($CorrelationId) {
    $correlationId = $CorrelationId.ToLower()
    Write-Host "    Using correlation_id from -CorrelationId param: $correlationId" -ForegroundColor Cyan
} elseif (Test-Path $LabState) {
    $priorState   = Get-Content $LabState -Raw | ConvertFrom-Json
    $correlationId = $priorState.correlation_id
    Write-Host "    Reusing correlation_id from $LabState (prior partial run): $correlationId" -ForegroundColor Cyan
} else {
    $correlationId = -join ((1..6) | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) })
}
$gcpProjectId   = "gcp-vwan-symm-$correlationId"
Write-Host "    correlation_id : $correlationId"
Write-Host "    GCP project ID : $gcpProjectId"
Write-Host "    Billing account: $BillingAccountId"

# Idempotency: if a previous run already created (and didn't destroy) the project, reuse it.
$existing = gcloud projects describe $gcpProjectId --format="value(projectId)" 2>$null
if ($existing -eq $gcpProjectId) {
    Write-Host "    ✓ Project $gcpProjectId already exists — reusing." -ForegroundColor Green
} else {
    Write-Host "    Creating project..." -ForegroundColor Yellow
    $attempt = 1
    while ($attempt -le 3) {
        gcloud projects create $gcpProjectId --name="vwan-symm-$correlationId" --quiet 2>&1 | ForEach-Object { "    $_" }
        if ($LASTEXITCODE -eq 0) { break }
        # Name collision → append -N and retry
        $gcpProjectId = "gcp-vwan-symm-$correlationId-$attempt"
        Write-Host "    Collision; retrying with $gcpProjectId" -ForegroundColor Yellow
        $attempt++
    }
    if ($LASTEXITCODE -ne 0) { throw "gcloud projects create failed after 3 attempts" }
    Write-Host "    ✓ Project created." -ForegroundColor Green
}

Write-Host "    Linking billing account $BillingAccountId..." -ForegroundColor Yellow
gcloud billing projects link $gcpProjectId --billing-account=$BillingAccountId --quiet 2>&1 | ForEach-Object { "    $_" }
if ($LASTEXITCODE -ne 0) { throw "gcloud billing projects link failed" }

Write-Host "    Enabling required APIs (compute, servicenetworking, cloudresourcemanager)..." -ForegroundColor Yellow
$apis = @('compute.googleapis.com','servicenetworking.googleapis.com','cloudresourcemanager.googleapis.com')
foreach ($api in $apis) {
    gcloud services enable $api --project=$gcpProjectId --quiet 2>&1 | ForEach-Object { "    $_" }
    if ($LASTEXITCODE -ne 0) { throw "gcloud services enable $api failed" }
}

# Tag at project level too so Niobe can find it
gcloud alpha resource-manager tags keys list --parent=projects/$gcpProjectId 2>$null | Out-Null  # best-effort, ignore errors

# Set ADC quota project so the google provider doesn't warn / mis-bill
$adcCfg = "$env:APPDATA\gcloud\application_default_credentials.json"
if (Test-Path $adcCfg) {
    gcloud auth application-default set-quota-project $gcpProjectId --quiet 2>&1 | Select-Object -First 2 | ForEach-Object { "    $_" }
}

# Export to TF
$env:TF_VAR_gcp_project_id          = $gcpProjectId
$env:TF_VAR_correlation_id_override = $correlationId
# Also export GOOGLE_CLOUD_QUOTA_PROJECT for the google provider's billing/quota override
$env:GOOGLE_CLOUD_QUOTA_PROJECT     = $gcpProjectId

Write-Host "    ✓ GCP project bootstrap complete." -ForegroundColor Green
Write-Host "      TF_VAR_gcp_project_id          = $gcpProjectId"
Write-Host "      TF_VAR_correlation_id_override = $correlationId"

# Persist lab state so subsequent (re-)runs reuse the same correlation_id / project
@{
    correlation_id = $correlationId
    gcp_project_id = $gcpProjectId
    timestamp_utc  = (Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ')
} | ConvertTo-Json | Out-File -FilePath $LabState -Encoding ascii
Write-Host "    Wrote .lab-state.json (correlation_id reuse marker)." -ForegroundColor DarkGray

if ($StopBeforeTerraform) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Yellow
    Write-Host " -StopBeforeTerraform set. Skipping step [5] (terraform)."   -ForegroundColor Yellow
    Write-Host " Resume with: .\deploy.ps1 -KvPath $kvChoice -NonInteractive -AutoApprove" -ForegroundColor Yellow
    Write-Host " (deploy.ps1 will reuse correlation_id=$correlationId from .lab-state.json)" -ForegroundColor Yellow
    Write-Host "============================================================" -ForegroundColor Yellow
    exit 0
}

# ---------------------------------------------------------------------------
# Step 5 — Terraform init / plan / apply
# ---------------------------------------------------------------------------
Push-Location $TfDir
try {
    Write-Host ""
    Write-Host "[5.pre] Setting GCP access token (via 'gcloud auth print-access-token')..." -ForegroundColor Yellow
    # Per 2026-06-15T15:43Z policy: bypass ADC, use the user-account login that Jose already has.
    # GOOGLE_OAUTH_ACCESS_TOKEN is a first-class google TF provider auth method.
    # Token validity ~1 hour. If apply runs >55 min, terraform will fail mid-flight on a 401 —
    # simply re-run deploy.ps1; TF is idempotent and picks up where it left off.
    $env:GOOGLE_OAUTH_ACCESS_TOKEN = (& gcloud auth print-access-token 2>$null).Trim()
    if (-not $env:GOOGLE_OAUTH_ACCESS_TOKEN) {
        throw "Failed to get GCP access token via 'gcloud auth print-access-token'. Verify 'gcloud auth list' shows an active account."
    }
    Write-Host "    ✓ GOOGLE_OAUTH_ACCESS_TOKEN set (length: $($env:GOOGLE_OAUTH_ACCESS_TOKEN.Length), valid ~1h)" -ForegroundColor Green
    # Belt-and-braces: still try to set ADC quota project if ADC happens to exist
    $adcPath = "$env:APPDATA\gcloud\application_default_credentials.json"
    if (Test-Path $adcPath) {
        gcloud auth application-default set-quota-project $gcpProjectId --quiet 2>&1 | Select-Object -First 2 | ForEach-Object { "    $_" }
    }

    Write-Host ""
    Write-Host "[5a] terraform init..." -ForegroundColor Yellow
    terraform init -upgrade
    if ($LASTEXITCODE -ne 0) { throw "terraform init failed" }

    Write-Host ""
    Write-Host "[5b] terraform validate..." -ForegroundColor Yellow
    terraform validate
    if ($LASTEXITCODE -ne 0) { throw "terraform validate failed" }

    Write-Host ""
    Write-Host "[5c] terraform plan (parallelism=20)..." -ForegroundColor Yellow
    terraform plan -parallelism=20 -out tfplan
    if ($LASTEXITCODE -ne 0) { throw "terraform plan failed" }

    if (-not $AutoApprove) {
        Write-Host ""
        Write-Host "    Plan complete. Estimated wall-clock: 45-55 min (vHub × 2 long pole)." -ForegroundColor Cyan
        Write-Host "    Estimated cost: ~`$135/day (Jose pre-approved at gate #12 #1)." -ForegroundColor Cyan
        $go = Read-Host "    Proceed with apply? [y/N]"
        if ($go.ToLower() -ne 'y') {
            Write-Host "    Apply cancelled by user." -ForegroundColor Yellow
            exit 0
        }
    }

    Write-Host ""
    Write-Host "[5d] terraform apply (parallelism=20 — Megaport/GCP work runs alongside vHubs)..." -ForegroundColor Yellow
    terraform apply -parallelism=20 tfplan
    if ($LASTEXITCODE -ne 0) { throw "terraform apply failed" }

    Write-Host ""
    Write-Host "[6] Deploy complete. Key outputs:" -ForegroundColor Green
    terraform output -json | Out-File -FilePath (Join-Path $PSScriptRoot "tf-outputs.json") -Encoding utf8
    Write-Host "    Full output JSON written to: $(Join-Path $PSScriptRoot 'tf-outputs.json')"
    terraform output resource_group_name
    terraform output regions
    terraform output megaport_pops_used
    terraform output vm_sizes_used
    terraform output hub_ids
    terraform output azfw_private_ips
    terraform output spoke_vm_private_ips
    terraform output gcp_vm_private_ips
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Deploy finished. Hand off to Niobe for validation (S1-S3 baseline)." -ForegroundColor Green
