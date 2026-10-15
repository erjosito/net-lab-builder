[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ContextPath,
    [Parameter(Mandatory)][string]$SshPublicKeyPath
)
. "$PSScriptRoot\Common.ps1"
Assert-NewWork
$context = Get-Content $ContextPath -Raw | ConvertFrom-Json
Assert-Context $context
foreach ($provider in @('Microsoft.Compute', 'Microsoft.Network')) {
    $result = Invoke-LabAz -SubscriptionId $context.subscriptionId -Arguments @('provider', 'show', '--namespace', $provider)
    if ($result.registrationState -ne 'Registered') { throw "$provider is not registered; no registration is authorized." }
}
$tokenResult = Invoke-LabAz -SubscriptionId $context.subscriptionId -Arguments @('account', 'get-access-token', '--resource', 'https://management.azure.com/')
$headers = @{ Authorization = 'Bearer ' + $tokenResult.accessToken }
$tokenResult = $null
$deadline = [datetimeoffset]::UtcNow.AddSeconds(120)
$uri = "https://management.azure.com/subscriptions/$($context.subscriptionId)/providers/Microsoft.Compute/skus?api-version=2021-07-01&%24filter=location%20eq%20%27swedencentral%27"
$ladder = @('Standard_B1ls', 'Standard_B1s', 'Standard_B2ts_v2', 'Standard_B2ls_v2', 'Standard_B2s_v2')
$candidates = @()
$pages = 0
try {
    do {
        [void](Read-Lease)
        if (++$pages -gt 10 -or [datetimeoffset]::UtcNow -ge $deadline) { throw 'Catalogue completeness bound exceeded.' }
        $link = [uri]$uri
        if ($link.Scheme -ne 'https' -or $link.Host -ne 'management.azure.com' -or
            -not $link.AbsolutePath.StartsWith("/subscriptions/$($context.subscriptionId)/", [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Untrusted catalogue pagination link.'
        }
        $remaining = [Math]::Max(1, [int]($deadline - [datetimeoffset]::UtcNow).TotalSeconds)
        $page = Invoke-RestMethod -Uri $uri -Headers $headers -TimeoutSec $remaining -MaximumRetryCount 0
        $candidates += @($page.value | Where-Object { $_.resourceType -eq 'virtualMachines' -and $_.name -in $ladder })
        $uri = if ($page.PSObject.Properties['nextLink']) { $page.nextLink } else { $null }
    } while ($uri)
} finally { $headers.Clear() }
$summary = foreach ($name in $ladder) {
    $sku = @($candidates | Where-Object name -eq $name)
    $restrictions = @($sku | ForEach-Object { $_.restrictions })
    $locationRestricted = @($restrictions | Where-Object {
        $_.type -eq 'Location' -and
        ('swedencentral' -in $_.values -or 'swedencentral' -in $_.restrictionInfo.locations)
    })
    [pscustomobject]@{
        name = $name
        present = $sku.Count -gt 0
        locationRestricted = $locationRestricted.Count -gt 0
        zoneRestrictions = @($restrictions | Where-Object type -eq 'Zone').Count
        viableMemory = $name -ne 'Standard_B1ls'
    }
}
Write-PrivateJson @{ retrievedUtc = [datetimeoffset]::UtcNow.ToString('o'); pages = $pages; complete = $true; candidates = @($summary) } (Join-Path $script:LabRoot 'private\capacity.private.json')
$choice = $summary | Where-Object { $_.present -and -not $_.locationRestricted -and $_.viableMemory } | Select-Object -First 1
if (-not $choice) { throw 'No viable unrestricted approved B-series size in Sweden Central.' }
# Existing approved SC retail provenance covers B2ts_v2 only; other choices need a fresh price gate.
if ($choice.name -ne 'Standard_B2ts_v2') { throw "Selected $($choice.name) requires a current bounded price gate before spending." }
$key = (Get-Content -LiteralPath $SshPublicKeyPath -Raw).Trim()
if ($key -notmatch '^ssh-(rsa|ed25519) ') { throw 'An existing RSA/Ed25519 SSH public key is required.' }
$parameters = @{
    '$schema' = 'https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#'
    contentVersion = '1.0.0.0'
    parameters = @{ runId = @{value = $context.runId}; vmSize = @{value = $choice.name}; adminPublicKey = @{value = $key} }
}
Write-PrivateJson $parameters (Join-Path $script:LabRoot 'private\deployment.params.json')
Write-PrivateJson @{
    runId = $context.runId; subscriptionVerified = $true; tenantVerified = $true
    catalogPassedUtc = [datetimeoffset]::UtcNow.ToString('o')
    vmSize = $choice.name; region = 'swedencentral'; nonzonal = $true
    infraUsdPerHour = 0.06273; lifetimeEnvelopeUsd = 8
    rationale = 'B1ls excluded for 0.5 GiB TLS/agent memory; first viable unrestricted ladder size. Catalog is not allocation proof.'
} (Join-Path $script:LabRoot 'private\gate.private.json')
Write-Output "Catalogue complete: $($choice.name), nonzonal; price envelope within approval. No live allocation performed."
