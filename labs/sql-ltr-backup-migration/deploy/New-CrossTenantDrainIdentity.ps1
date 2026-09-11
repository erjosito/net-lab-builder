<#
.SYNOPSIS
    Creates the identity plumbing required to drain LTR backup artifacts into a
    storage account that lives in a different Microsoft Entra tenant.

.DESCRIPTION
    A managed identity is a single-tenant service principal and cannot hold an RBAC
    role in another tenant. The supported way across that boundary is to have a
    multi-tenant app registration in the source tenant trust the managed identity as
    a federated credential, provision that app into the target tenant, and grant the
    RBAC there. See playbook G in the lab README.

    This script is idempotent. Re-running it verifies the configuration rather than
    duplicating it, so it is safe to use as a check before starting a drain.

.NOTES
    Requires in the SOURCE tenant: Application Administrator, Application Developer,
    Cloud Application Administrator, or ownership of the app registration.
    Requires in the TARGET tenant: rights to provision the app and assign RBAC.
    Limit: an application or user-assigned managed identity accepts at most 20
    federated identity credentials.
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)] [string] $SourceSubscriptionId,
    [Parameter(Mandatory)] [string] $SourceTenantId,
    [Parameter(Mandatory)] [string] $IdentityResourceGroup,
    [Parameter(Mandatory)] [string] $IdentityName,
    [Parameter(Mandatory)] [string] $TargetSubscriptionId,
    [Parameter(Mandatory)] [string] $TargetTenantId,
    [Parameter(Mandatory)] [string] $TargetResourceGroup,
    [Parameter(Mandatory)] [string] $TargetStorageAccount,
    [string] $AppDisplayName = 'ltr-xtenant-drain',
    [string] $FederatedCredentialName = 'ltr-drain-umi',
    [string] $RoleName = 'Storage Blob Data Contributor'
)

$ErrorActionPreference = 'Stop'
# PowerShell 7.6 defaults to 'Windows' argument passing, which silently drops
# empty-string arguments before they reach the Azure CLI.
$PSNativeCommandArgumentPassing = 'Standard'

function Invoke-AzJson {
    param([string[]] $Arguments, [switch] $AllowFailure)
    $raw = & az @Arguments -o json 2>&1
    if ($LASTEXITCODE -ne 0) {
        if ($AllowFailure) { return $null }
        throw "az $($Arguments -join ' ') failed: $raw"
    }
    if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
    return $raw | ConvertFrom-Json
}

Write-Host '== Step 1: read the source managed identity ==' -ForegroundColor Cyan
az account set -s $SourceSubscriptionId
$umi = Invoke-AzJson @('identity', 'show', '-g', $IdentityResourceGroup, '-n', $IdentityName)
Write-Host "  principalId (federated credential subject): $($umi.principalId)"
Write-Host "  clientId (used by the workload at runtime): $($umi.clientId)"

Write-Host '== Step 2: multi-tenant app registration in the source tenant ==' -ForegroundColor Cyan
$apps = Invoke-AzJson @('ad', 'app', 'list', '--display-name', $AppDisplayName)
$app  = $apps | Select-Object -First 1
if (-not $app) {
    if ($PSCmdlet.ShouldProcess($AppDisplayName, 'Create multi-tenant app registration')) {
        $app = Invoke-AzJson @('ad', 'app', 'create', '--display-name', $AppDisplayName,
                               '--sign-in-audience', 'AzureADMultipleOrgs')
        Write-Host "  created appId $($app.appId)"
    }
} else {
    Write-Host "  reusing existing appId $($app.appId)"
    if ($app.signInAudience -ne 'AzureADMultipleOrgs') {
        throw "App '$AppDisplayName' has signInAudience '$($app.signInAudience)'. It must be " +
              "AzureADMultipleOrgs to be provisioned into another tenant."
    }
}

Write-Host '== Step 3: federated credential so the app trusts the managed identity ==' -ForegroundColor Cyan
$issuer   = "https://login.microsoftonline.com/$SourceTenantId/v2.0"
$existing = Invoke-AzJson @('ad', 'app', 'federated-credential', 'list', '--id', $app.id) -AllowFailure
$match    = $existing | Where-Object { $_.subject -eq $umi.principalId -and $_.issuer -eq $issuer }
if ($match) {
    Write-Host "  federated credential already present: $($match.name)"
} else {
    if ($existing -and $existing.Count -ge 20) {
        throw "App '$AppDisplayName' already has $($existing.Count) federated credentials. The limit is 20."
    }
    if ($PSCmdlet.ShouldProcess($FederatedCredentialName, 'Create federated identity credential')) {
        $body = @{
            name      = $FederatedCredentialName
            issuer    = $issuer
            subject   = $umi.principalId
            audiences = @('api://AzureADTokenExchange')
        } | ConvertTo-Json -Compress
        $tmp = New-TemporaryFile
        try {
            # The CLI reads this parameter from a file to avoid shell quoting damage.
            $body | Out-File -FilePath $tmp -Encoding ascii
            Invoke-AzJson @('ad', 'app', 'federated-credential', 'create', '--id', $app.id,
                            '--parameters', "@$tmp") | Out-Null
            Write-Host '  created'
        } finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
    }
}

Write-Host '== Step 4: provision the app into the target tenant ==' -ForegroundColor Cyan
az account set -s $TargetSubscriptionId
$ctx = Invoke-AzJson @('account', 'show')
if ($ctx.tenantId -ne $TargetTenantId) {
    throw "Subscription $TargetSubscriptionId resolves to tenant $($ctx.tenantId), not $TargetTenantId."
}
$sp = Invoke-AzJson @('ad', 'sp', 'show', '--id', $app.appId) -AllowFailure
if (-not $sp) {
    if ($PSCmdlet.ShouldProcess($app.appId, 'Provision service principal in target tenant')) {
        $sp = Invoke-AzJson @('ad', 'sp', 'create', '--id', $app.appId)
        Write-Host "  provisioned, objectId $($sp.id)"
    }
} else {
    Write-Host "  already provisioned, objectId $($sp.id)"
}

Write-Host '== Step 5: grant blob access in the target tenant ==' -ForegroundColor Cyan
$scope = "/subscriptions/$TargetSubscriptionId/resourceGroups/$TargetResourceGroup" +
         "/providers/Microsoft.Storage/storageAccounts/$TargetStorageAccount"
$assigned = Invoke-AzJson @('role', 'assignment', 'list', '--assignee', $sp.id, '--scope', $scope) -AllowFailure
if ($assigned | Where-Object { $_.roleDefinitionName -eq $RoleName }) {
    Write-Host "  '$RoleName' already assigned"
} elseif ($PSCmdlet.ShouldProcess($scope, "Assign '$RoleName'")) {
    Invoke-AzJson @('role', 'assignment', 'create', '--assignee-object-id', $sp.id,
                    '--assignee-principal-type', 'ServicePrincipal',
                    '--role', $RoleName, '--scope', $scope) | Out-Null
    Write-Host '  assigned. Allow up to a few minutes for propagation.'
}

az account set -s $SourceSubscriptionId

Write-Host ''
Write-Host 'Identity plumbing ready. Values needed by the drain workload:' -ForegroundColor Green
[pscustomobject]@{
    UmiClientId    = $umi.clientId
    AppId          = $app.appId
    TargetTenantId = $TargetTenantId
    TargetAccount  = $TargetStorageAccount
} | Format-List

Write-Host 'Verify before relying on it: run Test-CrossTenantDrainToken.ps1 on the' -ForegroundColor Yellow
Write-Host 'source-side compute and confirm the returned token carries tid = target tenant.' -ForegroundColor Yellow
