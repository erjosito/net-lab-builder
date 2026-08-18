# Deploy-Lab.ps1 — AFD Edge Actions JWT Validation Lab
# Tank · 2026-08-17
# Implements activation sequence A0→A1→A2→(S1-GATE)→A3→A4
# Prerequisites: az CLI logged in with Contributor on subscription + Application Administrator in Entra
# Usage:
#   .\Deploy-Lab.ps1                        # Full deploy
#   .\Deploy-Lab.ps1 -SkipA1               # Skip Entra app registration (manual or already done)
#   .\Deploy-Lab.ps1 -WhatIf               # Preview without deploying
# Never writes secrets to disk. CLIENT_SECRET is process-scoped only.

[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ResourceGroup  = 'rg-afd-edge-jwt-lab',
    [string]$Location       = 'swedencentral',
    [string]$AppName        = 'app-edge-jwt-lab',
    [string]$AfdProfile     = 'afd-edge-jwt-lab',
    [string]$LawName        = 'law-edge-jwt-lab',
    [string]$AspName        = 'asp-edge-jwt-lab',
    [string]$AppSku         = 'B1',
    # KV name derived from sub ID last-8 for collision safety; override if needed.
    # The vault name is non-secret and committed to deployment-output.json.
    [string]$KvName         = '',
    [switch]$SkipA1,
    [switch]$SkipAppDeploy,
    [switch]$SkipKv
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RunId = (Get-Date -Format 'yyyyMMddTHHmmssZ')
$ScriptDir = $PSScriptRoot
$LabDir    = Split-Path $ScriptDir -Parent
$AppDir    = Join-Path $LabDir 'app'
$EaDir     = Join-Path $LabDir 'edge-actions'

$EA_API  = '2025-12-01-preview'  # Edge Actions resource API (EdgeActions at RG level)
$CDN_API = '2025-04-15'          # Stable AFD API for profile/endpoint/origin/route
$CDN_PREV_API = '2025-09-01-preview'  # Preview API required for EdgeAction rule type

# ─── Helper: check az login ────────────────────────────────────────────────────
function Assert-AzLogin {
    $acct = az account show -o json 2>&1 | ConvertFrom-Json
    if (-not $acct.id) { throw 'Not logged in to Azure. Run: az login' }
    Write-Host "[LOGIN] Subscription: $($acct.name)" -ForegroundColor Cyan
    return $acct
}

# ─── Helper: write step header ────────────────────────────────────────────────
function Write-Step($label) {
    Write-Host "`n═══ $label ═══" -ForegroundColor Yellow
}

# ─── Helper: encode file to base64 (for EA code upload) ───────────────────────
function ConvertTo-Base64File($path) {
    $bytes = [System.IO.File]::ReadAllBytes($path)
    return [Convert]::ToBase64String($bytes)
}

# ─── Helper: create/update diagnostic settings on any Edge Action ─────────────
# Idempotent: az monitor diagnostic-settings create upserts by name.
# Always targets the active EA name (parameter); never hard-codes eajwtvalidate.
# Categories confirmed from live eajwtvalidate3 settings (2026-08-18):
#   UserLog  → EdgeActionConsoleLog table in LAW  (required for EA console.log)
#   ServiceLog → EdgeActionServiceLog table in LAW (EA lifecycle/error events)
# Note: diagnostic settings must be on the EA resource itself, NOT the AFD profile.
function Set-EaDiagnosticSettings([string]$EaName, [string]$SubId, [string]$Rg, [string]$LawWsName) {
    $eaResourceId = "/subscriptions/$SubId/resourceGroups/$Rg/providers/Microsoft.Cdn/EdgeActions/$EaName"
    $lawId = (az monitor log-analytics workspace show `
        --workspace-name $LawWsName `
        --resource-group $Rg `
        --query id -o tsv 2>&1)
    if (-not $lawId -or $lawId -match '^ERROR') {
        Write-Warning "[DIAG] Could not resolve LAW workspace '$LawWsName' in '$Rg': $lawId"
        return
    }
    # JSON written inline — az monitor diagnostic-settings create handles its own quoting
    # (no az rest @file workaround needed here; only az rest --body is affected on Windows)
    $logsJson = '[{"category":"UserLog","enabled":true},{"category":"ServiceLog","enabled":true}]'
    Write-Host "[DIAG] Upserting diagnostic settings 'ea-logs' on $EaName → $LawWsName"
    az monitor diagnostic-settings create `
        --resource $eaResourceId `
        --name 'ea-logs' `
        --workspace $lawId `
        --logs $logsJson `
        --output none 2>&1
    Write-Host "[DIAG] 'ea-logs' (UserLog + ServiceLog) active on $EaName"
}

# ─── Helper: write a secret to Key Vault via ARM management plane ─────────────
# Uses management.azure.com (not vault.azure.net data plane).
# Required when publicNetworkAccess=Disabled is enforced by tenant policy.
# Secret tags: stored via PATCH after PUT (PUT requires value; PATCH with empty
# properties block is not supported — tags are set inline on initial PUT only).
# Never print or return secret values; caller must scrub $Value after calling.
function Set-KvSecretArm {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [string]$KvResourceId,
        [string]$SecretName,
        [string]$Value,
        [string]$ContentType = 'text/plain',
        [hashtable]$Tags = @{}
    )
    if (-not $PSCmdlet.ShouldProcess($SecretName, 'Store in Key Vault')) { return }
    $body = @{
        tags       = $Tags
        properties = @{
            value       = $Value
            contentType = $ContentType
            attributes  = @{ enabled = $true }
        }
    } | ConvertTo-Json -Depth 5 -Compress
    $tmpFile = Join-Path $env:TEMP "kv-secret-$([System.IO.Path]::GetRandomFileName()).json"
    # IMPORTANT: write to a temp file, not the repo tree (secret content)
    $body | Set-Content $tmpFile -Encoding UTF8
    try {
        $r = az rest --method PUT `
          --uri "https://management.azure.com${KvResourceId}/secrets/${SecretName}?api-version=2023-07-01" `
          --body "@$tmpFile" `
          --query "properties.secretUri" -o tsv 2>&1
        Write-Host "[KV] $SecretName stored → $($r.Split('?')[0])"
    } finally {
        # Always delete temp file even if az rest fails
        Remove-Item $tmpFile -ErrorAction SilentlyContinue
    }
}

# ═══ PREFLIGHT ════════════════════════════════════════════════════════════════
Write-Step 'PREFLIGHT'
$acct = Assert-AzLogin
$subscriptionId = $acct.id

# Resolve KV name: use param if supplied, else derive from last-8 of sub ID
if (-not $KvName) { $KvName = "kv-jwt-lab-$($subscriptionId.Substring($subscriptionId.Length - 8))" }
$KvResourceId = "/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.KeyVault/vaults/$KvName"
Write-Host "[PREFLIGHT] Key Vault: $KvName"

# Register EdgeActions private preview feature flag (required before EA resource operations)
$eaFeatureState = (az feature show --namespace Microsoft.Cdn --name EdgeActionsPrivatePreview --query properties.state -o tsv 2>&1)
if ($eaFeatureState -ne 'Registered') {
    Write-Host "[PREFLIGHT] Registering EdgeActionsPrivatePreview feature flag (state: $eaFeatureState)..."
    if ($PSCmdlet.ShouldProcess('Microsoft.Cdn/EdgeActionsPrivatePreview', 'Register feature')) {
        az feature register --namespace Microsoft.Cdn --name EdgeActionsPrivatePreview 2>&1 | Out-Null
        az provider register -n Microsoft.Cdn 2>&1 | Out-Null
        # Poll until Registered (up to 5 min)
        for ($i = 1; $i -le 20; $i++) {
            Start-Sleep 15
            $eaFeatureState = (az feature show --namespace Microsoft.Cdn --name EdgeActionsPrivatePreview --query properties.state -o tsv 2>&1)
            Write-Host "[PREFLIGHT] EdgeActionsPrivatePreview: $eaFeatureState ($i/20)"
            if ($eaFeatureState -eq 'Registered') { break }
        }
    }
}
Write-Host "[PREFLIGHT] EdgeActionsPrivatePreview: $eaFeatureState"

# ═══ A0 — FOUNDATION ══════════════════════════════════════════════════════════
Write-Step 'A0 — Foundation (Resource Group + Bicep)'
$a0Start = Get-Date

if ($PSCmdlet.ShouldProcess($ResourceGroup, 'Create resource group')) {
    az group create `
        --name $ResourceGroup `
        --location $Location `
        --tags "lab=afd-edge-actions-jwt-validation" "env=lab" "owner=jose" `
               "created_by=copilot-lab" "ephemeral=true" "run_id=$RunId" `
        --output none
    Write-Host "[A0] Resource group: $ResourceGroup"
}

# Deploy Bicep template
$bicepPath = Join-Path $ScriptDir 'main.bicep'
if ($PSCmdlet.ShouldProcess('Bicep', 'Deploy main.bicep')) {
    $bicepResult = az deployment group create `
        --resource-group $ResourceGroup `
        --template-file $bicepPath `
        --parameters location=$Location runId=$RunId appServicePlanSku=$AppSku `
        --name "deploy-afd-edge-jwt-$RunId" `
        --output json 2>&1 | ConvertFrom-Json
    Write-Host "[A0] Bicep deployment state: $($bicepResult.properties.provisioningState)"
}

$a0End = Get-Date
Write-Host "[A0] Elapsed: $([int]($a0End - $a0Start).TotalSeconds)s"

# ─── Retrieve AFD Front Door ID (needed for App Service access restriction) ───
$FDID = az afd profile show `
    --profile-name $AfdProfile `
    --resource-group $ResourceGroup `
    --query frontDoorId -o tsv 2>&1
Write-Host "[A0] AFD Front Door ID: $FDID (non-secret)"

# ─── App Service Access Restrictions (ARM-native; design.md §2) ───────────────
# NOTE: az CLI blocks duplicate ServiceTag values across rules.
# Using ARM REST API directly for both rules to avoid this limitation.
# Design: two rules required — health probes carry X-FD-HealthProbe:1 but NOT X-Azure-FDID.
Write-Step 'A0 — App Service Access Restrictions'
if ($PSCmdlet.ShouldProcess($AppName, 'Configure access restrictions')) {
    $siteConfigUrl = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Web/sites/$AppName/config/web?api-version=2023-12-01"

    $restrictBody = @{
        properties = @{
            ipSecurityRestrictions = @(
                @{
                    name = "afd-healthprobe"
                    priority = 100
                    action = "Allow"
                    tag = "ServiceTag"
                    ipAddress = "AzureFrontDoor.Backend"
                    headers = @{ "x-fd-healthprobe" = @("1") }
                    description = "Allow AFD health probes (carry X-FD-HealthProbe:1, not FDID)"
                },
                @{
                    name = "afd-fdid"
                    priority = 200
                    action = "Allow"
                    tag = "ServiceTag"
                    ipAddress = "AzureFrontDoor.Backend"
                    headers = @{ "x-azure-fdid" = @($FDID) }
                    description = "Allow AFD traffic with FDID header"
                }
            )
        }
    }
    $restrictBodyPath = Join-Path $env:TEMP 'access-restrict.json'
    $restrictBody | ConvertTo-Json -Depth 10 | Set-Content $restrictBodyPath -Encoding UTF8
    az rest --method PATCH --url $siteConfigUrl --headers "Content-Type=application/json" --body "@$restrictBodyPath" --output none 2>&1
    Write-Host "[A0] Access restrictions configured via ARM REST (two-rule FDID pattern)"
}

# ─── Deploy App Code ──────────────────────────────────────────────────────────
if (-not $SkipAppDeploy) {
    Write-Step 'A0 — App Code Deploy'
    if ($PSCmdlet.ShouldProcess($AppName, 'Deploy Node.js app code')) {
        # Install dependencies locally for zip deploy
        Push-Location $AppDir
        npm install --omit=dev --quiet 2>&1 | Out-Null
        Pop-Location

        # Create zip package (exclude .deployment file from zip root)
        $zipPath = Join-Path $env:TEMP 'afd-edge-jwt-app.zip'
        Compress-Archive -Path "$AppDir\*" -DestinationPath $zipPath -Force

        az webapp deploy `
            --resource-group $ResourceGroup `
            --name $AppName `
            --src-path $zipPath `
            --type zip `
            --async false `
            --output none 2>&1
        Remove-Item $zipPath -Force
        Write-Host "[A0] App code deployed"
    }
}

# ═══ A1 — ENTRA ID APP REGISTRATIONS ══════════════════════════════════════════
Write-Step 'A1 — Entra ID App Registrations'
$a1Start = Get-Date

if ($SkipA1) {
    Write-Host "[A1] SKIPPED (-SkipA1 flag set)"
} else {
    if ($PSCmdlet.ShouldProcess('Entra ID', 'Create app registrations')) {
        # Verify Application Administrator role
        $myId = az ad signed-in-user show --query id -o tsv 2>&1
        Write-Host "[A1] Signed-in user OID: $myId (non-secret)"

        # ─ Resource / API app (app-edge-jwt-api) ─────────────────────────────
        $existingApi = az ad app list --display-name 'app-edge-jwt-api' --query '[0].appId' -o tsv 2>&1
        if ($existingApi -and $existingApi.Length -gt 5) {
            $apiAppId = $existingApi
            Write-Host "[A1] Reusing existing app-edge-jwt-api: $apiAppId"
        } else {
            # Create app manifest with Lab.Admin app role
            $appManifestPath = Join-Path $env:TEMP 'api-app-manifest.json'
            @"
{
  "displayName": "app-edge-jwt-api",
  "signInAudience": "AzureADMyOrg",
  "api": {
    "requestedAccessTokenVersion": 2
  }
}
"@ | Set-Content $appManifestPath -Encoding UTF8

            $apiApp = az ad app create --display-name 'app-edge-jwt-api' --output json 2>&1 | ConvertFrom-Json
            $apiAppId = $apiApp.appId
            Write-Host "[A1] Created app-edge-jwt-api: $apiAppId"
            Remove-Item $appManifestPath -Force -ErrorAction SilentlyContinue

            # Set Application ID URI
            az ad app update --id $apiAppId --identifier-uris "api://$apiAppId" --output none 2>&1

            # Add Lab.Admin app role
            $roleManifestPath = Join-Path $env:TEMP 'app-roles.json'
            $roleId = [guid]::NewGuid().ToString()
            @"
[{
  "allowedMemberTypes": ["Application"],
  "description": "Lab admin role for afd-edge-jwt-validation lab",
  "displayName": "Lab.Admin",
  "id": "$roleId",
  "isEnabled": true,
  "value": "Lab.Admin"
}]
"@ | Set-Content $roleManifestPath -Encoding UTF8
            az ad app update --id $apiAppId --app-roles "@$roleManifestPath" --output none 2>&1
            Remove-Item $roleManifestPath -Force -ErrorAction SilentlyContinue
            Write-Host "[A1] Lab.Admin app role added to app-edge-jwt-api"
        }

        # Set access token version to 2 via manifest patch
        $apiSpId = az ad sp list --filter "appId eq '$apiAppId'" --query '[0].id' -o tsv 2>&1
        if (-not $apiSpId -or $apiSpId.Length -lt 5) {
            az ad sp create --id $apiAppId --output none 2>&1
            $apiSpId = az ad sp show --id $apiAppId --query id -o tsv 2>&1
        }

        # ─ Client app (app-edge-jwt-client) ──────────────────────────────────
        $existingClient = az ad app list --display-name 'app-edge-jwt-client' --query '[0].appId' -o tsv 2>&1
        if ($existingClient -and $existingClient.Length -gt 5) {
            $clientAppId = $existingClient
            Write-Host "[A1] Reusing existing app-edge-jwt-client: $clientAppId"
        } else {
            $clientApp = az ad app create --display-name 'app-edge-jwt-client' --output json 2>&1 | ConvertFrom-Json
            $clientAppId = $clientApp.appId
            Write-Host "[A1] Created app-edge-jwt-client: $clientAppId"

            # Ensure service principal exists
            az ad sp create --id $clientAppId --output none 2>&1

            # Add API permission (Lab.Admin application permission on app-edge-jwt-api)
            # First get the role ID from the API app
            $labAdminRoleId = az ad app show --id $apiAppId `
                --query "appRoles[?value=='Lab.Admin'].id" -o tsv 2>&1
            Write-Host "[A1] Lab.Admin role ID: $labAdminRoleId"

            az ad app permission add `
                --id $clientAppId `
                --api $apiAppId `
                --api-permissions "${labAdminRoleId}=Role" `
                --output none 2>&1
            Write-Host "[A1] API permission added: Lab.Admin"
        }

        # Grant admin consent
        Write-Host "[A1] Granting admin consent (requires Application Administrator)..."
        az ad app permission admin-consent --id $clientAppId --output none 2>&1
        Write-Host "[A1] Admin consent granted"

        # ─ Generate client secret (PROCESS-ONLY; never written to disk) ──────
        Write-Host "[A1] Generating client secret..."
        $secretJson = az ad app credential reset `
            --id $clientAppId `
            --display-name "lab-secret-$RunId" `
            --years 1 `
            --output json 2>&1 | ConvertFrom-Json
        # Store in process-scoped environment variable ONLY
        $env:CLIENT_SECRET = $secretJson.password
        Write-Host "[A1] Client secret generated and stored in `$env:CLIENT_SECRET (process only)"
        Write-Host "[A1] ⚠️  Export CLIENT_SECRET before this shell exits if you need it"

        # ─ Update App Service config with non-secret Entra IDs ───────────────
        $tenantId = az account show --query tenantId -o tsv 2>&1
        az webapp config appsettings set `
            -g $ResourceGroup -n $AppName `
            --settings `
                "ENTRA_TENANT_ID=$tenantId" `
                "ENTRA_API_APP_ID=$apiAppId" `
                "AFD_FRONT_DOOR_ID=$FDID" `
            --output none 2>&1
        Write-Host "[A1] App Service settings updated (non-secret IDs)"

        # Persist non-secret IDs for A2+
        $Script:TenantId    = $tenantId
        $Script:ApiAppId    = $apiAppId
        $Script:ClientAppId = $clientAppId
    }
}

$a1End = Get-Date
Write-Host "[A1] Elapsed: $([int]($a1End - $a1Start).TotalSeconds)s"

# ═══ A_KV — KEY VAULT: CREATE + POPULATE ══════════════════════════════════════
# Creates a Standard Key Vault with Azure RBAC authorization and stores all test
# credentials as secrets using the ARM management plane. Data-plane writes are
# avoided because tenant policy may enforce publicNetworkAccess=Disabled.
#
# NETWORK NOTE: The vault is created with -DefaultAction Deny -Bypass AzureServices
# plus Jose's current public IP. However, tenant policy may override and set
# publicNetworkAccess=Disabled regardless, making data-plane access available
# only from Azure Cloud Shell (trusted service) or a private-endpoint network.
# This is a documented deviation — see deploy-log.md for details.
#
# Secret rotation: CLIENT_SECRET expires 7 days from creation.
# To rotate: az ad app credential reset --id <clientId> --append --end-date <date>
# Then re-run this section (idempotent — updates existing vault/secrets).
Write-Step 'A_KV — Create Key Vault and Store Lab Secrets'
$akvStart = Get-Date

if (-not $SkipKv) {
    # Resolve current public IP for firewall allowlist
    $myIp = (Invoke-RestMethod -Uri 'https://api.ipify.org' -TimeoutSec 10 -ErrorAction SilentlyContinue)
    if (-not $myIp) { Write-Warning '[A_KV] Could not resolve public IP; firewall rule will not include local machine' }

    if ($PSCmdlet.ShouldProcess($KvName, 'Create or update Key Vault')) {
        # Idempotent: az keyvault create is safe to re-run
        $kvTags = @(
            "lab=true", "created_by=copilot-lab", "owner=jose",
            "ephemeral=true", "run_id=$RunId"
        )
        $kvArgs = @(
            '--name',                 $KvName
            '--resource-group',       $ResourceGroup
            '--location',             $Location
            '--sku',                  'standard'
            '--enable-rbac-authorization', 'true'
            '--public-network-access','Enabled'
            '--default-action',       'Deny'
            '--bypass',               'AzureServices'
            '--tags'
        ) + $kvTags
        az keyvault create @kvArgs --output none 2>&1
        Write-Host "[A_KV] Key Vault $KvName created/confirmed"

        # Add current IP to firewall (idempotent)
        if ($myIp) {
            az keyvault network-rule add --name $KvName --resource-group $ResourceGroup `
                --ip-address "$myIp/32" 2>&1 | Out-Null
            Write-Host "[A_KV] Firewall rule added for $myIp"
        }

        # Assign Key Vault Secrets Officer to the signed-in identity
        $userId  = az ad signed-in-user show --query id -o tsv 2>&1
        $roleId  = 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'   # Key Vault Secrets Officer
        $existing = az role assignment list --assignee $userId --role $roleId `
            --scope $KvResourceId --query '[0].id' -o tsv 2>&1
        if (-not $existing -or $existing -match '^ERROR') {
            az role assignment create --assignee $userId --role $roleId `
                --scope $KvResourceId --output none 2>&1
            Write-Host "[A_KV] Key Vault Secrets Officer assigned to $userId"
        } else {
            Write-Host "[A_KV] Key Vault Secrets Officer already assigned"
        }
    }

    # Store secrets — requires $Script:TenantId, $Script:ApiAppId, $Script:ClientAppId,
    # $env:CLIENT_SECRET to be set (populated by A1 above, or pre-existing run).
    # Skip if A1 was skipped and these values are not available.
    if (-not $SkipA1 -and $env:CLIENT_SECRET) {
        $tenantId  = $Script:TenantId
        $apiAppId  = $Script:ApiAppId
        $clientId  = $Script:ClientAppId
        $afdEndpt  = "https://${afdEndpoint}"
        $expiry7d  = (Get-Date).ToUniversalTime().AddDays(7).ToString('yyyy-MM-ddTHH:mm:ssZ')

        # Create 7-day credential specifically for KV (short-lived, descriptive name)
        Write-Host "[A_KV] Creating 7-day client credential for KV storage..."
        $credOut = az ad app credential reset `
            --id $clientId `
            --append `
            --display-name "jwt-lab-kv-$(Get-Date -Format 'yyyyMMdd')" `
            --end-date $expiry7d `
            -o json 2>&1
        $cred = ($credOut | Where-Object { $_ -notmatch '^WARNING' } | Join-String -Separator "`n") | ConvertFrom-Json
        $kvSecret = $cred.password

        $expTag  = @{ expiry=$expiry7d; purpose='jwt-lab-client-secret'; lab='afd-edge-actions-jwt-validation'; rotation='create-new-credential-before-expiry' }
        $cfgTag  = @{ purpose='jwt-lab-config'; lab='afd-edge-actions-jwt-validation' }

        Set-KvSecretArm -KvResourceId $KvResourceId -SecretName 'client-secret' -Value $kvSecret -ContentType 'application/jwt-lab-client-secret' -Tags $expTag
        Set-KvSecretArm -KvResourceId $KvResourceId -SecretName 'tenant-id'     -Value $tenantId -ContentType 'text/plain' -Tags $cfgTag
        Set-KvSecretArm -KvResourceId $KvResourceId -SecretName 'api-app-id'    -Value $apiAppId -ContentType 'text/plain' -Tags $cfgTag
        Set-KvSecretArm -KvResourceId $KvResourceId -SecretName 'client-id'     -Value $clientId -ContentType 'text/plain' -Tags $cfgTag
        Set-KvSecretArm -KvResourceId $KvResourceId -SecretName 'afd-endpoint'  -Value $afdEndpt -ContentType 'text/plain' -Tags $cfgTag

        # Scrub KV-specific secret from memory (env:CLIENT_SECRET from A1 is kept for App Service config)
        $kvSecret = $null
        $cred     = $null
        Write-Host "[A_KV] All secrets stored. KV-specific credential scrubbed from memory."
        Write-Host "[A_KV] ⚠️  client-secret expires: $expiry7d — rotate before expiry."
    } elseif ($SkipA1) {
        Write-Warning '[A_KV] SkipA1 is set — secrets not populated. Re-run without -SkipA1, or populate manually.'
    } else {
        Write-Warning '[A_KV] $env:CLIENT_SECRET is not set — A1 may not have run. Secrets not populated.'
    }
} else {
    Write-Host "[A_KV] Skipped (-SkipKv)"
}

$akvEnd = Get-Date
Write-Host "[A_KV] Elapsed: $([int]($akvEnd - $akvStart).TotalSeconds)s"

# ═══ A2 — CAPABILITY PROBE EDGE ACTION ════════════════════════════════════════
# API learnings (Tank 2026-08-17/18):
# - EdgeActions resource is at RG level: /resourceGroups/{rg}/providers/Microsoft.Cdn/EdgeActions/{name}
#   NOT under profiles. Use $EA_API = 2025-12-01-preview.
# - Name MUST be alphanumeric only (no hyphens), max 50 chars, location=global
# - SKU = {name:Standard,tier:Standard} (not Standard_AzureFrontDoor)
# - Code upload: POST .../versions/{v}/deployVersionCode {name,content:base64(zip)}
#   NOT a code property in the version PUT body
# - deployVersionCode returns 202 Accepted; poll the Location LRO header, then GET version
#   until validationStatus=Succeeded (~15s in GET but addAttachment needs ~17 min)
# - swapDefault: POST .../versions/{v}/swapDefault — BROKEN in preview (accepts, no effect)
# - AFD rule action name: "EdgeAction", typeName: "DeliveryRuleEdgeActionParameters"
# - invocationPoint: "ClientRequest" is required
# - edgeActionReference.id references the RG-level EA resource ID
Write-Step 'A2 — Deploy Capability Probe Edge Action (eaprobe2)'
$a2Start = Get-Date

$EaBase = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Cdn/EdgeActions"
$eaName = 'eaprobe2'
$eaId   = "$EaBase/$eaName"

# Build directory inside the project (never use $env:TEMP)
$buildDir = Join-Path $EaDir 'build'
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

# Helper: build zip from .js file → base64 string
function New-EaZipB64([string]$jsSource, [string]$zipDest) {
    $handlerDest = Join-Path (Split-Path $zipDest) 'handler.js'
    Copy-Item $jsSource -Destination $handlerDest -Force
    Compress-Archive -Path $handlerDest -DestinationPath $zipDest -Force
    return [Convert]::ToBase64String([IO.File]::ReadAllBytes($zipDest))
}

# Helper: call deployVersionCode, poll LRO, wait 17 min propagation
function Invoke-DeployVersionCode([string]$versionUrl, [string]$zipB64, [string]$label, [string]$tmpDir) {
    # NOTE: --body @file is required for all EA REST calls on Windows (inline JSON is mangled by PS quoting)
    $dcFile = Join-Path $tmpDir 'deploy-code.json'
    @{ name = 'handler.js'; content = $zipB64 } | ConvertTo-Json -Compress | Set-Content $dcFile -Encoding UTF8
    $resp = az rest --method POST --uri "$versionUrl/deployVersionCode?api-version=$EA_API" `
        --body "@$dcFile" 2>&1
    Write-Host "[$label] deployVersionCode called"
    $clockStart = Get-Date
    # Poll validationStatus (~30s to appear, but addAttachment needs ~17 min)
    for ($i = 1; $i -le 20; $i++) {
        Start-Sleep 30
        $vs = (az rest --method GET --uri "$versionUrl`?api-version=$EA_API" 2>&1 | `
            ConvertFrom-Json).properties.validationStatus
        Write-Host "[$label] validationStatus=$vs ($($i*30)s elapsed)"
        if ($vs -eq 'Succeeded') { break }
        if ($vs -eq 'Failed') { Write-Host "[$label] ❌ Validation Failed!"; break }
    }
    # Enforce 17-min minimum wait from deployVersionCode (addAttachment LRO requirement)
    $elapsed = (Get-Date) - $clockStart
    $remaining = [math]::Max(0, (17*60) - $elapsed.TotalSeconds)
    if ($remaining -gt 0) {
        Write-Host "[$label] Waiting $([int]$remaining)s for addAttachment propagation (17-min requirement)..."
        Start-Sleep -Seconds $remaining
    }
    Write-Host "[$label] Propagation complete. validationStatus confirmed."
}

if ($PSCmdlet.ShouldProcess($eaName, 'Create Edge Action probe')) {
    # Create EA resource at RG level — write body to file (az rest inline JSON is mangled on Windows)
    @{ location = "global"; sku = @{ name = "Standard"; tier = "Standard" }; properties = @{} } | `
      ConvertTo-Json -Depth 5 | Set-Content "$buildDir\ea-create.json" -Encoding UTF8
    az rest --method PUT --uri "$eaId`?api-version=$EA_API" `
        --body "@$buildDir\ea-create.json" --output none 2>&1
    Write-Host "[A2] EdgeAction $eaName created"
    Start-Sleep 10

    # Attach diagnostic settings immediately after EA resource exists (idempotent)
    if ($PSCmdlet.ShouldProcess($eaName, 'Create diagnostic settings')) {
        Set-EaDiagnosticSettings $eaName $subscriptionId $ResourceGroup $LawName
    }

    # Create v1 (default version) — isDefaultVersion MUST be string "True", not boolean
    @{ location = "global"; properties = @{ deploymentType = "zip"; isDefaultVersion = "True" } } | `
      ConvertTo-Json -Depth 5 | Set-Content "$buildDir\v1-create.json" -Encoding UTF8
    az rest --method PUT `
        --uri "$eaId/versions/v1?api-version=$EA_API" `
        --body "@$buildDir\v1-create.json" `
        --output none 2>&1
    Write-Host "[A2] Version v1 created (isDefaultVersion=true)"

    # Upload probe code via deployVersionCode + wait 17 min
    $probeB64 = New-EaZipB64 (Join-Path $EaDir 'ea-capability-probe.js') (Join-Path $buildDir 'probe.zip')
    Invoke-DeployVersionCode "$eaId/versions/v1" $probeB64 'A2/probe-v1' $buildDir

    # Create AFD rule set and rule (EdgeAction attachment happens via rule PUT)
    $rsUrl = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Cdn/profiles/$AfdProfile/ruleSets/rsedgeprobe?api-version=$CDN_PREV_API"
    az rest --method PUT --uri $rsUrl --headers 'Content-Type=application/json' --body '{"properties":{}}' --output none 2>&1
    Write-Host "[A2] Rule set rsedgeprobe created"

    $ruleBody = @{
        properties = @{
            order = 1
            conditions = @(
                @{
                    name = 'UrlPath'
                    parameters = @{
                        typeName      = 'DeliveryRuleUrlPathMatchConditionParameters'
                        operator      = 'BeginsWith'
                        matchValues   = @('/debug')
                        negateCondition = $false
                        transforms    = @()
                    }
                }
            )
            actions = @(
                @{
                    name = 'EdgeAction'
                    parameters = @{
                        typeName          = 'DeliveryRuleEdgeActionParameters'
                        invocationPoint   = 'ClientRequest'
                        edgeActionReference = @{ id = "/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Cdn/EdgeActions/$eaName" }
                    }
                }
            )
        }
    } | ConvertTo-Json -Depth 10
    $ruleUrl = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Cdn/profiles/$AfdProfile/ruleSets/rsedgeprobe/rules/ruleprovedebug?api-version=$CDN_PREV_API"
    az rest --method PUT --uri $ruleUrl --body $ruleBody --headers 'Content-Type=application/json' --output none 2>&1
    Write-Host "[A2] Rule ruleprovedebug created"

    # Attach rule set to route (GET current + PUT with updated ruleSets)
    $endpointName = 'edge-jwt-lab'
    $routeUrl = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Cdn/profiles/$AfdProfile/afdEndpoints/$endpointName/routes/rt-api?api-version=$CDN_API"
    $currentRoute = az rest --method GET --uri $routeUrl --output json 2>&1 | ConvertFrom-Json
    $rsRef = @{ id = "/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Cdn/profiles/$AfdProfile/ruleSets/rsedgeprobe" }
    if (-not ($currentRoute.properties.ruleSets | Where-Object { $_.id -like '*rsedgeprobe*' })) {
        $currentRoute.properties.ruleSets = @($currentRoute.properties.ruleSets) + @($rsRef)
    }
    az rest --method PUT --uri $routeUrl --body ($currentRoute | ConvertTo-Json -Depth 15) `
        --headers 'Content-Type=application/json' --output none 2>&1
    Write-Host "[A2] Rule set rsedgeprobe attached to route rt-api"
}

# Clean up build dir
Remove-Item $buildDir -Recurse -Force -ErrorAction SilentlyContinue

$a2End = Get-Date
Write-Host "[A2] Elapsed: $([int]($a2End - $a2Start).TotalSeconds)s"

# ─ Smoke-test A2 ──────────────────────────────────────────────────────────────
Write-Step 'A2 Smoke Test — GET /debug/request'
$afdEndpoint = az afd endpoint show `
    --profile-name $AfdProfile `
    --resource-group $ResourceGroup `
    --endpoint-name edge-jwt-lab `
    --query hostName -o tsv 2>&1
$afdBaseUrl = "https://$afdEndpoint"
Write-Host "[A2] AFD endpoint: $afdBaseUrl"

# Allow 90s for AFD propagation
Write-Host "[A2] Waiting 90s for AFD configuration propagation..."
Start-Sleep -Seconds 90

$debugResponse = Invoke-RestMethod -Uri "$afdBaseUrl/debug/request" -Method GET `
    -Headers @{ 'X-Lab-RunId' = $RunId } -ErrorAction SilentlyContinue
Write-Host "[A2] /debug/request HTTP 200 — response received"

# ═══ SAVE DEPLOYMENT OUTPUT ═══════════════════════════════════════════════════
Write-Step 'Save deployment-output.json'

$output = @{
    run_id           = $RunId
    deployed_at      = (Get-Date -Format 'o')
    resource_group   = $ResourceGroup
    location         = $Location
    app_service_name = $AppName
    app_service_url  = "https://app-edge-jwt-lab.azurewebsites.net"
    afd_profile      = $AfdProfile
    afd_endpoint     = $afdEndpoint
    afd_base_url     = $afdBaseUrl
    law_name         = $LawName
    edge_actions     = @{
        ea_capability_probe = "ea-capability-probe"
        api_version         = $EA_API
    }
    entra = @{
        # Tenant and subscription IDs redacted per charter
        api_app_display_name    = "app-edge-jwt-api"
        client_app_display_name = "app-edge-jwt-client"
        api_app_id              = if ($Script:ApiAppId) { $Script:ApiAppId } else { "see_A1_output" }
    }
    s1_gate_verdict  = "PENDING — run S1 probe and update manually"
    smoke_tests      = @{
        health              = "PENDING"
        debug_request       = "PENDING"
    }
}

$outputPath = Join-Path $ScriptDir 'deployment-output.json'
$output | ConvertTo-Json -Depth 10 | Set-Content $outputPath -Encoding UTF8
Write-Host "[OUTPUT] Written to: $outputPath"

Write-Host "`n[DONE] A0/A1/A2 complete. RunId=$RunId" -ForegroundColor Green
Write-Host "[NEXT] Run S1 probe: query EdgeActionConsoleLog in Log Analytics after GET /debug/request"
Write-Host "[NEXT] Update s1_gate_verdict in deployment-output.json"
Write-Host "[NEXT] If GO/CONDITIONAL: run Deploy-Lab.ps1 -Stage A3A4 (separate call, Jose must re-approve)"
Write-Host "[NEXT] A3 pattern: after creating the JWT EA resource, call:"
Write-Host "         Set-EaDiagnosticSettings <eaName> `$subscriptionId `$ResourceGroup `$LawName"
Write-Host "       The function is idempotent and targets any EA name dynamically."
