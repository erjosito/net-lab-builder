<#
.SYNOPSIS
    One-shot recovery for orphaned resources after a hung terraform apply.

.DESCRIPTION
    1. Path B: snapshot KV ACL, allow, fetch 3 secrets, restore ACL.
    2. Query Megaport API for MCRs (find orphan mcr1 if it was created server-side).
    3. Query Azure for vHub1 (known orphan from deploy run #2).
    4. terraform import any orphans.
    5. Leave Megaport creds in env so caller can immediately run terraform apply.
#>

[CmdletBinding()]
param(
    [string]$KvName  = "platform-secrets-1138",
    [string]$KvRg    = "platform",
    [string]$Rg      = "rg-vwan-symm-103167",
    [string]$Mcr1Name = "mcr1-vwan-symm-stockholm",
    [string]$TfDir   = "C:\Users\jomore\Repos\net-lab-builder\src\terraform\vwan-dual-er-symmetric",
    [string]$GcpProjectId = "gcp-vwan-symm-103167",
    [string]$CorrelationId = "103167",
    [switch]$ContinueApply
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " ORPHAN RECOVERY (Path B + Megaport probe + TF import)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# ---- [1] KV Path B: snapshot → allow → fetch → restore ---------------------
$AclState = Join-Path $PSScriptRoot ".akv-state.json"
Write-Host ""
Write-Host "[1] KV Path B: snapshot ACL..." -ForegroundColor Yellow
$snapshotJson = az keyvault show --name $KvName --resource-group $KvRg --query "properties.networkAcls" -o json
if (-not $snapshotJson) { throw "Failed to snapshot KV ACL" }
$snapshot = $snapshotJson | ConvertFrom-Json
Write-Host "    current: defaultAction=$($snapshot.defaultAction), ipRules=$($snapshot.ipRules.Count), vnetRules=$($snapshot.virtualNetworkRules.Count)"

# Pre-flight: defaultAction MUST be Deny (the original lab state).
# If it's Allow, a prior run was killed mid-flow without restoring.
# DO NOT overwrite the snapshot file with this anomalous state.
if ($snapshot.defaultAction -ne "Deny") {
    Write-Host ""
    Write-Host "🛑 KV IS NOT IN ORIGINAL Deny STATE (currently $($snapshot.defaultAction))" -ForegroundColor Red
    Write-Host "   This indicates a prior run was killed mid-flow without restoring." -ForegroundColor Red
    Write-Host "   Refusing to capture this as the new snapshot (would lose original state)." -ForegroundColor Red
    Write-Host ""
    Write-Host "   To recover manually:" -ForegroundColor Yellow
    Write-Host "   az keyvault update --name $KvName --resource-group $KvRg --default-action Deny --bypass None" -ForegroundColor Yellow
    Write-Host "   Then re-run this script."
    throw "KV in non-Deny state; manual recovery required"
}

Set-Content -Path $AclState -Value $snapshotJson -Encoding UTF8
Write-Host "    ✅ snapshot persisted to $AclState"

try {
    Write-Host "    flipping to Allow..."
    az keyvault update --name $KvName --resource-group $KvRg --default-action Allow --output none
    Start-Sleep -Seconds 10

    Write-Host "    fetching 3 secrets..."
    $mpAccess = az keyvault secret show --vault-name $KvName --name "megaport-api-key" --query value -o tsv
    $mpSecret = az keyvault secret show --vault-name $KvName --name "megaport-api-secret" --query value -o tsv
    $defPass  = az keyvault secret show --vault-name $KvName --name "default-password" --query value -o tsv
    if (-not $mpAccess -or -not $mpSecret -or -not $defPass) { throw "Failed to fetch one or more secrets" }

    $env:MEGAPORT_ACCESS_KEY = $mpAccess
    $env:MEGAPORT_SECRET_KEY = $mpSecret
    $env:TF_VAR_megaport_access_key = $mpAccess
    $env:TF_VAR_megaport_secret_key = $mpSecret
    $env:TF_VAR_default_password = $defPass
    Write-Host "    ✅ secrets fetched + env exported"
}
finally {
    Write-Host "    restoring KV ACL..." -ForegroundColor Yellow
    $maxAttempts = 3
    for ($i = 1; $i -le $maxAttempts; $i++) {
        try {
            $bypass = if ($snapshot.bypass) { $snapshot.bypass } else { "None" }
            az keyvault update --name $KvName --resource-group $KvRg --default-action $snapshot.defaultAction --bypass $bypass --output none
            # Re-add ipRules
            foreach ($r in $snapshot.ipRules) {
                az keyvault network-rule add --name $KvName --resource-group $KvRg --ip-address $r.value --output none 2>$null
            }
            foreach ($r in $snapshot.virtualNetworkRules) {
                az keyvault network-rule add --name $KvName --resource-group $KvRg --subnet $r.id --output none 2>$null
            }
            Write-Host "    ✅ ACL restored (attempt ${i})"
            break
        } catch {
            Write-Host "    ⚠️ Restore attempt ${i} failed: $_" -ForegroundColor Red
            if ($i -eq $maxAttempts) { throw "ACL RESTORE FAILED — KV LEFT OPEN — MANUAL FIX REQUIRED" }
            Start-Sleep -Seconds 5
        }
    }
}

# ---- [2] Query Megaport API for orphan mcr1 --------------------------------
Write-Host ""
Write-Host "[2] Megaport API: hunt for orphan MCR1..." -ForegroundColor Yellow
$auth = "Basic " + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("${mpAccess}:${mpSecret}"))
$tokenBody = "grant_type=client_credentials"
$tokenResp = Invoke-RestMethod -Method Post -Uri "https://auth-m2m.megaport.com/oauth2/token" `
    -Headers @{ Authorization = $auth; "Content-Type" = "application/x-www-form-urlencoded" } `
    -Body $tokenBody
$bearer = $tokenResp.access_token
Write-Host "    bearer token acquired (${($bearer.Length)} chars)"

# List all MCRs
$productsResp = Invoke-RestMethod -Method Get -Uri "https://api.megaport.com/v2/products" -Headers @{ Authorization = "Bearer $bearer" }
$allMcrs = $productsResp.data | Where-Object { $_.productType -eq "MCR2" -or $_.productType -eq "MCR" }
Write-Host "    Total MCRs in account: $($allMcrs.Count)"
foreach ($m in $allMcrs) {
    Write-Host "      - $($m.productName)  uid=$($m.productUid)  state=$($m.provisioningStatus)"
}

$orphan = $allMcrs | Where-Object { $_.productName -eq $Mcr1Name }
if ($orphan) {
    Write-Host "    🔎 ORPHAN FOUND: $($orphan.productName)  uid=$($orphan.productUid)" -ForegroundColor Magenta
    $env:RECOVER_MCR1_UID = $orphan.productUid
} else {
    Write-Host "    no orphan mcr1 — TF can recreate cleanly"
}

# ---- [3] Import orphans into TF state --------------------------------------
Write-Host ""
Write-Host "[3] terraform import orphans..." -ForegroundColor Yellow

# Set TF env required for ANY terraform op (validation + provider config)
$env:TF_VAR_gcp_project_id        = $GcpProjectId
$env:TF_VAR_correlation_id_override = $CorrelationId
$env:GOOGLE_OAUTH_ACCESS_TOKEN    = (& gcloud auth print-access-token 2>$null).Trim()
if (-not $env:GOOGLE_OAUTH_ACCESS_TOKEN) {
    throw "Failed to get GCP access token; run 'gcloud auth login'"
}
Write-Host "    GCP token len: $($env:GOOGLE_OAUTH_ACCESS_TOKEN.Length); project=$GcpProjectId"

Push-Location $TfDir

# vHub1 — orphaned from run #2 (might already be in state from earlier import)
$vhub1Id = "/subscriptions/a8fbd8e1-fb5a-4411-804a-4ac80929c93c/resourceGroups/${Rg}/providers/Microsoft.Network/virtualHubs/hub1-swedencentral"
$inState = terraform state list 2>$null
if ($inState -notcontains 'azurerm_virtual_hub.hub1') {
    Write-Host "    importing azurerm_virtual_hub.hub1..."
    terraform import "azurerm_virtual_hub.hub1" $vhub1Id
} else {
    Write-Host "    azurerm_virtual_hub.hub1 already in state — skip"
}

# ER GW hub1 — orphaned from run #3 (created in Azure but not in state when killed)
$ergwHub1Id = "/subscriptions/a8fbd8e1-fb5a-4411-804a-4ac80929c93c/resourceGroups/${Rg}/providers/Microsoft.Network/expressRouteGateways/ergw-hub1"
$ergwExists = (az resource show --ids $ergwHub1Id --query name -o tsv 2>$null)
if ($ergwExists -and ($inState -notcontains 'azurerm_express_route_gateway.hub1')) {
    Write-Host "    importing azurerm_express_route_gateway.hub1..."
    terraform import "azurerm_express_route_gateway.hub1" $ergwHub1Id
} elseif ($inState -contains 'azurerm_express_route_gateway.hub1') {
    Write-Host "    azurerm_express_route_gateway.hub1 already in state — skip"
}

# ER GW hub2 — may be orphaned from current run if killed mid-creation
$ergwHub2Id = "/subscriptions/a8fbd8e1-fb5a-4411-804a-4ac80929c93c/resourceGroups/${Rg}/providers/Microsoft.Network/expressRouteGateways/ergw-hub2"
$ergwHub2Exists = (az resource show --ids $ergwHub2Id --query name -o tsv 2>$null)
if ($ergwHub2Exists -and ($inState -notcontains 'azurerm_express_route_gateway.hub2')) {
    Write-Host "    importing azurerm_express_route_gateway.hub2..."
    terraform import "azurerm_express_route_gateway.hub2" $ergwHub2Id
} elseif ($inState -contains 'azurerm_express_route_gateway.hub2') {
    Write-Host "    azurerm_express_route_gateway.hub2 already in state — skip"
}

# AzFW hub2 — orphaned from run #3
$azfwHub2Id = "/subscriptions/a8fbd8e1-fb5a-4411-804a-4ac80929c93c/resourceGroups/${Rg}/providers/Microsoft.Network/azureFirewalls/azfw-hub2-northeurope"
$azfwExists = (az resource show --ids $azfwHub2Id --query name -o tsv 2>$null)
if ($azfwExists -and ($inState -notcontains 'azurerm_firewall.hub2')) {
    Write-Host "    importing azurerm_firewall.hub2..."
    terraform import "azurerm_firewall.hub2" $azfwHub2Id
} elseif ($inState -contains 'azurerm_firewall.hub2') {
    Write-Host "    azurerm_firewall.hub2 already in state — skip"
}

if ($env:RECOVER_MCR1_UID) {
    if ($inState -notcontains 'megaport_mcr.mcr1') {
        Write-Host "    importing megaport_mcr.mcr1 (uid=$env:RECOVER_MCR1_UID)..."
        terraform import "megaport_mcr.mcr1" $env:RECOVER_MCR1_UID
    } else {
        Write-Host "    megaport_mcr.mcr1 already in state — skip"
    }
}

Pop-Location

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " RECOVERY COMPLETE" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

if ($ContinueApply) {
    Write-Host ""
    Write-Host "[4] terraform apply -auto-approve -parallelism=20 (with TF_LOG=DEBUG)..." -ForegroundColor Cyan
    Push-Location $TfDir
    $tfLogFile = Join-Path $PSScriptRoot "tf-debug.log"
    $env:TF_LOG = "DEBUG"
    $env:TF_LOG_PATH = $tfLogFile
    Write-Host "    TF_LOG=DEBUG → $tfLogFile"
    terraform apply -auto-approve -parallelism=20
    $applyExit = $LASTEXITCODE
    $env:TF_LOG = ""
    $env:TF_LOG_PATH = ""
    Pop-Location
    Write-Host ""
    if ($applyExit -eq 0) {
        Write-Host "✅ APPLY SUCCESS" -ForegroundColor Green
    } else {
        Write-Host "❌ APPLY FAILED (exit $applyExit)" -ForegroundColor Red
        exit $applyExit
    }
} else {
    Write-Host ""
    Write-Host "Next: cd $TfDir; terraform apply -auto-approve -parallelism=20"
}
