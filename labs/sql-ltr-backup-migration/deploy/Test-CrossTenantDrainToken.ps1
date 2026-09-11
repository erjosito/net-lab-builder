<#
.SYNOPSIS
    Verifies that source-side compute can obtain a target-tenant token from its
    managed identity and use it against target-tenant storage.

.DESCRIPTION
    Run this ON the source-side compute (the VM or other Azure host that carries the
    user-assigned managed identity), not from a workstation. It exercises the
    federated credential exchange configured by New-CrossTenantDrainIdentity.ps1.

    The decisive check is not that a token comes back. It is that the token's 'tid'
    claim is the TARGET tenant. A token minted for the source tenant will look
    perfectly valid and will fail against target-tenant storage.

.NOTES
    Verify the result from the target tenant as well. A write that appears to
    succeed from the source side should be listed from target-tenant context
    before it is trusted.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $UmiClientId,
    [Parameter(Mandatory)] [string] $TargetTenantId,
    [Parameter(Mandatory)] [string] $AppId,
    [Parameter(Mandatory)] [string] $TargetStorageAccount,
    [string] $Container = 'drained',
    [switch] $WriteProbeBlob
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'
# '&' is mangled when a URL is passed inline through some Azure tooling, so the
# query string is assembled from a character code rather than written literally.
$amp = [char]38

function Get-ManagedIdentityToken {
    param([Parameter(Mandatory)][string] $Resource)
    $uri = 'http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01' +
           $amp + 'resource=' + $Resource + $amp + 'client_id=' + $UmiClientId
    $response = curl.exe --noproxy '*' -s -H 'Metadata: true' $uri
    if ($LASTEXITCODE -ne 0) { throw 'IMDS call failed. Is this running on the Azure compute that carries the identity?' }
    $parsed = $response | ConvertFrom-Json
    if (-not $parsed.access_token) { throw "IMDS returned no token: $response" }
    return $parsed.access_token
}

function Read-JwtClaims {
    param([Parameter(Mandatory)][string] $Jwt)
    $payload = $Jwt.Split('.')[1].Replace('-', '+').Replace('_', '/')
    while ($payload.Length % 4) { $payload += '=' }
    return [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($payload)) | ConvertFrom-Json
}

Write-Host '== Step 1: managed identity token, audience api://AzureADTokenExchange ==' -ForegroundColor Cyan
$assertion = Get-ManagedIdentityToken -Resource 'api://AzureADTokenExchange'
Write-Host "  obtained, length $($assertion.Length)"

Write-Host '== Step 2: exchange it at the target tenant ==' -ForegroundColor Cyan
$token = (Invoke-RestMethod -Method Post -Uri "https://login.microsoftonline.com/$TargetTenantId/oauth2/v2.0/token" -Body @{
    client_id             = $AppId
    grant_type            = 'client_credentials'
    scope                 = 'https://storage.azure.com/.default'
    client_assertion_type = 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer'
    client_assertion      = $assertion
}).access_token

$claims = Read-JwtClaims -Jwt $token
Write-Host "  tid   = $($claims.tid)"
Write-Host "  appid = $($claims.appid)"
Write-Host "  aud   = $($claims.aud)"

if ($claims.tid -ne $TargetTenantId) {
    throw "Token was issued for tenant $($claims.tid), not the target tenant $TargetTenantId."
}
Write-Host '  CONFIRMED: the token belongs to the target tenant.' -ForegroundColor Green

if (-not $WriteProbeBlob) {
    Write-Host 'Token exchange verified. Re-run with -WriteProbeBlob to test a data-plane write.' -ForegroundColor Yellow
    return
}

Write-Host '== Step 3: data-plane write into the target tenant ==' -ForegroundColor Cyan
$name = "xtenant-probe-$((Get-Date).ToUniversalTime().ToString('yyyyMMddHHmmss')).txt"
$uri  = "https://$TargetStorageAccount.blob.core.windows.net/$Container/$name"
Invoke-RestMethod -Method Put -Uri $uri -Body ([Text.Encoding]::UTF8.GetBytes('cross-tenant drain probe')) -Headers @{
    Authorization    = "Bearer $token"
    'x-ms-version'   = '2023-11-03'
    'x-ms-blob-type' = 'BlockBlob'
} | Out-Null

Write-Host "  wrote $name" -ForegroundColor Green
Write-Host ''
Write-Host 'Now confirm from the TARGET tenant, not from here:' -ForegroundColor Yellow
Write-Host "  az storage blob list --account-name $TargetStorageAccount -c $Container --auth-mode login -o table"
