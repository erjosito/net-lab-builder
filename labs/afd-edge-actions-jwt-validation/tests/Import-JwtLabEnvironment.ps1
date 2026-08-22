# Import-JwtLabEnvironment.ps1
# Reads JWT lab test credentials from Azure Key Vault and sets them as
# PROCESS-SCOPED environment variables in the CURRENT SHELL SESSION ONLY.
#
# ┌─────────────────────────────────────────────────────────────────────────┐
# │  RUN THIS FROM A PRIVATE-ENDPOINT-CONNECTED POWERSHELL HOST              │
# │                                                                         │
# │  The lab vault (kv-jwt-lab-a8fbd8e1) has publicNetworkAccess=Disabled  │
# │  enforced by tenant policy. Data-plane calls from local machines        │
# │  return ForbiddenByConnection regardless of RBAC role assignment.       │
# │                                                                         │
# │  Standard Cloud Shell and local hosts use the blocked public endpoint.  │
# │  The deployed management VM reaches the vault through Private Link.     │
# │                                                                         │
# │  Quick start from a PowerShell host on the management VNet:             │
# │    git clone https://github.com/erjosito/net-lab-builder               │
# │    cd net-lab-builder/labs/afd-edge-actions-jwt-validation/tests        │
# │    pwsh Import-JwtLabEnvironment.ps1                                    │
# │                                                                         │
# │  Environment variables are set in the current process only.             │
# └─────────────────────────────────────────────────────────────────────────┘
#
# Usage:
#   pwsh Import-JwtLabEnvironment.ps1
#   pwsh Import-JwtLabEnvironment.ps1 -VaultName kv-jwt-lab-a8fbd8e1
#   $info = .\Import-JwtLabEnvironment.ps1 -PassThru   # names+lengths only
#
# Environment variables set (current process only — never written to disk):
#   TENANT_ID, API_APP_ID, CLIENT_ID, CLIENT_SECRET, AFD_ENDPOINT
#
# -PassThru returns [ordered]@{} of {Name, Length, Set} — NEVER values.
#
# Credential expiry: CLIENT_SECRET expires 7 days from creation. To rotate:
#   az ad app credential reset --id <CLIENT_ID> --append --end-date <date>
#   Re-store 'client-secret' in KV (re-run Deploy-Lab.ps1 A_KV section),
#   then re-run this script in a fresh private session.

[CmdletBinding()]
param(
    [string]$VaultName,
    [switch]$PassThru
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ─── Verify az login ──────────────────────────────────────────────────────────
$acctJson = az account show -o json 2>$null
if (-not $acctJson) { throw '[KV] Not logged in to Azure. Run: az login' }
$acct = $acctJson | ConvertFrom-Json
if (-not $acct.id)  { throw '[KV] az account show returned no subscription ID.' }
Write-Host "[KV] Authenticated as: $($acct.user.name)" -ForegroundColor Cyan

# ─── Resolve vault name ────────────────────────────────────────────────────────
if (-not $VaultName) {
    $deployOutputPath = Join-Path $PSScriptRoot '..' 'deploy' 'deployment-output.json'
    if (-not (Test-Path $deployOutputPath)) {
        throw "[KV] -VaultName not supplied and deployment-output.json not found at: $deployOutputPath"
    }
    $deployOutput = Get-Content $deployOutputPath -Raw | ConvertFrom-Json
    $VaultName    = $deployOutput.key_vault.kv_name
    if (-not $VaultName) {
        throw "[KV] 'key_vault.kv_name' not found in deployment-output.json. Supply -VaultName explicitly."
    }
    Write-Host "[KV] Vault name resolved from deployment-output.json: $VaultName" -ForegroundColor DarkCyan
}

Write-Host "[KV] Reading secrets from vault: $VaultName"

# ─── Helper: detect ForbiddenByConnection and surface private access guidance
function Test-ForbiddenByConnection {
    param([string]$ErrorText, [string]$SecretName, [string]$Vault)
    if ($ErrorText -match 'ForbiddenByConnection|Public network access is disabled') {
        Write-Host '' -ForegroundColor Red
        Write-Host '╔══════════════════════════════════════════════════════════════════╗' -ForegroundColor Red
        Write-Host '║  BLOCKED: Key Vault data-plane unreachable from this machine     ║' -ForegroundColor Red
        Write-Host '║  Tenant policy enforces publicNetworkAccess=Disabled on all KVs ║' -ForegroundColor Red
        Write-Host '╠══════════════════════════════════════════════════════════════════╣' -ForegroundColor Red
        Write-Host '║  Connect to vm-edge-jwt-management through Azure Bastion.       ║' -ForegroundColor Yellow
        Write-Host '║  That VM uses Private Link and private DNS for vault access.    ║' -ForegroundColor Yellow
        Write-Host '╠══════════════════════════════════════════════════════════════════╣' -ForegroundColor Red
        Write-Host '║  ❌  NOT supported: printing/transferring secret values to       ║' -ForegroundColor Red
        Write-Host '║     bypass network restriction. Do not copy secrets manually.   ║' -ForegroundColor Red
        Write-Host '╚══════════════════════════════════════════════════════════════════╝' -ForegroundColor Red
        throw "[KV] ForbiddenByConnection reading '$SecretName' from '$Vault'. See guidance above."
    }
}

# ─── Read each secret — fails fast with actionable guidance on network error ──
function Read-KvSecret {
    [CmdletBinding()]
    param([string]$Vault, [string]$SecretName)
    $val = az keyvault secret show `
        --vault-name $Vault `
        --name $SecretName `
        --query value -o tsv 2>&1
    if ($LASTEXITCODE -ne 0 -or ($val -is [string] -and $val -match '^ERROR')) {
        # Surface ForbiddenByConnection as a first-class actionable error
        Test-ForbiddenByConnection -ErrorText "$val" -SecretName $SecretName -Vault $Vault
        # Any other failure
        throw "[KV] Failed to read '$SecretName' from '$Vault': $val"
    }
    if ([string]::IsNullOrWhiteSpace($val)) {
        throw "[KV] Secret '$SecretName' returned an empty value from '$Vault'."
    }
    return $val
}

$env:TENANT_ID     = Read-KvSecret -Vault $VaultName -SecretName 'tenant-id'
$env:API_APP_ID    = Read-KvSecret -Vault $VaultName -SecretName 'api-app-id'
$env:CLIENT_ID     = Read-KvSecret -Vault $VaultName -SecretName 'client-id'
$env:CLIENT_SECRET = Read-KvSecret -Vault $VaultName -SecretName 'client-secret'
$env:AFD_ENDPOINT  = Read-KvSecret -Vault $VaultName -SecretName 'afd-endpoint'

# ─── Validate all set ─────────────────────────────────────────────────────────
$requiredVars = @('TENANT_ID','API_APP_ID','CLIENT_ID','CLIENT_SECRET','AFD_ENDPOINT')
foreach ($v in $requiredVars) {
    $val = [System.Environment]::GetEnvironmentVariable($v)
    if ([string]::IsNullOrEmpty($val)) {
        throw "[KV] Environment variable $v is empty after reading from Key Vault."
    }
}

# ─── Print variable names + masked metadata (NEVER values) ────────────────────
Write-Host '' 
Write-Host "[KV] ✅ Environment variables loaded in THIS process (values not shown):" -ForegroundColor Green
Write-Host "[KV]    These are set in the current PowerShell process ONLY." -ForegroundColor DarkGreen
Write-Host "[KV]    They are NOT available on your local machine." -ForegroundColor DarkGreen
$summary = [ordered]@{}
foreach ($v in $requiredVars) {
    $val = [System.Environment]::GetEnvironmentVariable($v)
    $len = $val.Length
    $summary[$v] = [pscustomobject]@{ Name = $v; Length = $len; Set = $true }
    Write-Host ("    {0,-14}  length={1,3}  set=true" -f $v, $len)
}
Write-Host ''
Write-Host "[KV] ⚠️  CLIENT_SECRET expires 7 days from creation. Re-run after rotation." -ForegroundColor DarkYellow
Write-Host "[KV]    Run your tests in this same session before the session ends." -ForegroundColor DarkYellow

# ─── PassThru: return safe object (names/lengths only, NEVER values) ──────────
if ($PassThru) {
    return $summary
}
