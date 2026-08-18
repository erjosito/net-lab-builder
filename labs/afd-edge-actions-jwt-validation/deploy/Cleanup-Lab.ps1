# Cleanup-Lab.ps1 — AFD Edge Actions JWT Validation Lab
# Tank · 2026-08-17
#
# IMPORTANT: This script will NOT delete any resources unless -Confirmed is passed
# AND Jose Moreno has given explicit separate approval.
#
# By default: PREVIEW ONLY — lists what would be deleted.
# To actually delete: .\Cleanup-Lab.ps1 -Confirmed
#   (requires separate explicit approval from Jose)

[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ResourceGroup = 'rg-afd-edge-jwt-lab',
    [string]$AfdProfile    = 'afd-edge-jwt-lab',
    [string]$SubscriptionId = '',
    [string]$KvName        = '',   # Auto-derived from sub ID if empty
    # ⚠️ Must be explicitly passed by Jose — not a default
    [switch]$Confirmed
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $Confirmed) {
    Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Yellow
    Write-Host '  CLEANUP PREVIEW MODE — NO RESOURCES WILL BE DELETED' -ForegroundColor Yellow
    Write-Host '  Pass -Confirmed for actual deletion (requires Jose approval)' -ForegroundColor Yellow
    Write-Host '══════════════════════════════════════════════════════════════' -ForegroundColor Yellow
}

$acct = az account show -o json 2>&1 | ConvertFrom-Json
if (-not $SubscriptionId) { $SubscriptionId = $acct.id }
if (-not $KvName)         { $KvName = "kv-jwt-lab-$($SubscriptionId.Substring($SubscriptionId.Length - 8))" }
$EA_API = '2025-09-01-preview'

Write-Host "`n[PREVIEW] Resources that would be deleted:`n"

# 1. Edge Actions (subscription-level)
$eas = @('ea-capability-probe', 'ea-jwt-validate', 'ea-execution-filter')
foreach ($ea in $eas) {
    Write-Host "  [EA]    Microsoft.Cdn/EdgeActions/$ea"
    if ($Confirmed -and $PSCmdlet.ShouldProcess($ea, 'Delete Edge Action')) {
        $url = "https://management.azure.com/subscriptions/$SubscriptionId/providers/Microsoft.Cdn/EdgeActions/${ea}?api-version=$EA_API"
        az rest --method DELETE --url $url --output none 2>&1
        Write-Host "    DELETED: $ea"
    }
}

# 2. AFD Profile (cascades: endpoints, origins, rule sets, routes)
Write-Host "  [AFD]   $ResourceGroup/$AfdProfile (AFD Standard profile + all children)"
if ($Confirmed -and $PSCmdlet.ShouldProcess($AfdProfile, 'Delete AFD profile')) {
    az afd profile delete -g $ResourceGroup --profile-name $AfdProfile --yes --output none 2>&1
    Write-Host "    DELETED: $AfdProfile"
}

# 3. App Service + Plan
Write-Host "  [APP]   $ResourceGroup/app-edge-jwt-lab (App Service)"
Write-Host "  [ASP]   $ResourceGroup/asp-edge-jwt-lab (App Service Plan)"
if ($Confirmed -and $PSCmdlet.ShouldProcess('app-edge-jwt-lab', 'Delete App Service')) {
    az webapp delete -g $ResourceGroup -n app-edge-jwt-lab --output none 2>&1
    az appservice plan delete -g $ResourceGroup -n asp-edge-jwt-lab --yes --output none 2>&1
    Write-Host "    DELETED: app-edge-jwt-lab + asp-edge-jwt-lab"
}

# 4a. Key Vault (must be deleted before resource group; soft-delete may require purge)
Write-Host "  [KV]    $ResourceGroup/$KvName (Key Vault — contains lab secrets)"
Write-Host "  [KV]    Note: soft-delete is enabled; purge separately if needed after deletion."
if ($Confirmed -and $PSCmdlet.ShouldProcess($KvName, 'Delete Key Vault')) {
    az keyvault delete --name $KvName --resource-group $ResourceGroup --output none 2>&1
    Write-Host "    DELETED (soft): $KvName"
    Write-Host "    To purge: az keyvault purge --name $KvName --location swedencentral"
}

# 4b. Log Analytics Workspace
Write-Host "  [LAW]   $ResourceGroup/law-edge-jwt-lab (Log Analytics)"
if ($Confirmed -and $PSCmdlet.ShouldProcess('law-edge-jwt-lab', 'Delete Log Analytics workspace')) {
    az monitor log-analytics workspace delete `
        -g $ResourceGroup --workspace-name law-edge-jwt-lab --yes --output none 2>&1
    Write-Host "    DELETED: law-edge-jwt-lab"
}

# 5. Entra app registrations
Write-Host "  [ENTRA] app-edge-jwt-api (Entra app registration)"
Write-Host "  [ENTRA] app-edge-jwt-client (Entra app registration)"
if ($Confirmed -and $PSCmdlet.ShouldProcess('Entra apps', 'Delete app registrations')) {
    $apiId = az ad app list --display-name 'app-edge-jwt-api' --query '[0].appId' -o tsv 2>&1
    $clientId = az ad app list --display-name 'app-edge-jwt-client' --query '[0].appId' -o tsv 2>&1
    if ($apiId)    { az ad app delete --id $apiId    --output none 2>&1; Write-Host "    DELETED: app-edge-jwt-api" }
    if ($clientId) { az ad app delete --id $clientId --output none 2>&1; Write-Host "    DELETED: app-edge-jwt-client" }
}

# 6. Resource group (cascades remaining resources)
Write-Host "  [RG]    $ResourceGroup (resource group — cascades all)"
if ($Confirmed -and $PSCmdlet.ShouldProcess($ResourceGroup, 'Delete resource group')) {
    az group delete --name $ResourceGroup --yes --no-wait --output none 2>&1
    Write-Host "    DELETE INITIATED (async): $ResourceGroup"
}

if (-not $Confirmed) {
    Write-Host "`n[PREVIEW COMPLETE] To delete: .\Cleanup-Lab.ps1 -Confirmed" -ForegroundColor Yellow
    Write-Host "[REMINDER] Jose must explicitly approve cleanup before -Confirmed is passed." -ForegroundColor Red
} else {
    # Verify
    Write-Host "`n[VERIFY] Remaining resources in $ResourceGroup :"
    az resource list -g $ResourceGroup -o table 2>&1
}
