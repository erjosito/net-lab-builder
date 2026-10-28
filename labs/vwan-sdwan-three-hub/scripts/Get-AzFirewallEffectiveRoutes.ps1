param (
    [Parameter(Mandatory)]
    [string]$SubscriptionId,

    [Parameter(Mandatory)]
    [string]$ResourceGroupName,

    [Parameter(Mandatory)]
    [string]$VirtualHubName,

    [string]$ApiVersion = "2026-01-01",

    [int]$MaxPollAttempts = 60
)

$ErrorActionPreference = "Stop"

Set-AzContext -SubscriptionId $SubscriptionId | Out-Null

$hubResourceId = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroupName/providers/Microsoft.Network/virtualHubs/$VirtualHubName"

$uri = "https://management.azure.com$hubResourceId/effectiveRoutes?api-version=$ApiVersion"

$body = @{
    virtualWanResourceType = "AzureFirewalls"
} | ConvertTo-Json

Write-Host "POST: $uri" -ForegroundColor Cyan
Write-Host "Payload: $body" -ForegroundColor DarkGray

$response = Invoke-AzRestMethod `
    -Method POST `
    -Uri $uri `
    -Payload $body

Write-Host ""
Write-Host "Initial HTTP status: $($response.StatusCode)" -ForegroundColor Yellow

if ($response.Content) {
    Write-Host "Initial response body:"
    Write-Host $response.Content
}

# ============================================================
# Immediate synchronous response
# ============================================================

if ($response.StatusCode -eq 200) {

    Write-Host "Operation completed synchronously." -ForegroundColor Green
    $finalResponse = $response
}

# ============================================================
# Asynchronous response
# ============================================================

elseif ($response.StatusCode -eq 202) {

    $pollUri = $response.Headers.Location

    if (-not $pollUri) {
        throw "HTTP 202 received but Azure did not return a Location header."
    }

    Write-Host ""
    Write-Host "Operation is asynchronous." -ForegroundColor Yellow
    Write-Host "Polling URL:"
    Write-Host $pollUri -ForegroundColor DarkGray

    $retryAfter = 5

    if ($response.Headers.'Retry-After') {
        $retryAfter = [int]$response.Headers.'Retry-After'
    }

    for ($attempt = 1; $attempt -le $MaxPollAttempts; $attempt++) {

        Write-Host ""
        Write-Host "Waiting $retryAfter seconds..."
        Start-Sleep -Seconds $retryAfter

        Write-Host "Poll attempt $attempt/$MaxPollAttempts" -ForegroundColor Cyan

        $pollResponse = Invoke-AzRestMethod `
            -Method GET `
            -Uri $pollUri

        Write-Host "HTTP status: $($pollResponse.StatusCode)"

        if ($pollResponse.Content) {
            Write-Host "Response body:"
            Write-Host $pollResponse.Content
        }
        else {
            Write-Host "Response body: <empty>"
        }

        # ----------------------------------------------------
        # Still processing
        # ----------------------------------------------------

        if ($pollResponse.StatusCode -eq 202) {

            if ($pollResponse.Headers.'Retry-After') {
                $retryAfter = [int]$pollResponse.Headers.'Retry-After'
            }

            if ($pollResponse.Headers.Location) {
                $pollUri = $pollResponse.Headers.Location
            }

            continue
        }

        # ----------------------------------------------------
        # Completed
        # ----------------------------------------------------

        if ($pollResponse.StatusCode -eq 200) {

            Write-Host ""
            Write-Host "Azure reports operation complete." -ForegroundColor Green

            $finalResponse = $pollResponse
            break
        }

        throw "Unexpected polling status: $($pollResponse.StatusCode)"
    }

    if (-not $finalResponse) {
        throw "Operation did not complete after $MaxPollAttempts polling attempts."
    }
}

else {
    throw "Initial request failed with HTTP status $($response.StatusCode): $($response.Content)"
}

# ============================================================
# Examine the final response
# ============================================================

Write-Host ""
Write-Host "================ FINAL RESPONSE ================" -ForegroundColor Magenta

Write-Host "HTTP status: $($finalResponse.StatusCode)"

if (-not $finalResponse.Content) {
    throw "Azure returned HTTP 200 but the response body is empty."
}

$result = $finalResponse.Content | ConvertFrom-Json

Write-Host ""
Write-Host "Raw parsed result:" -ForegroundColor Magenta
$result | ConvertTo-Json -Depth 20

Write-Host ""
Write-Host "================ ROUTES ================" -ForegroundColor Magenta

if ($null -eq $result.value) {

    Write-Warning "The final response does NOT contain a 'value' property."

}
elseif ($result.value.Count -eq 0) {

    Write-Warning "The final response contains a 'value' array, but it contains zero routes."

}
else {

    Write-Host "Returned $($result.value.Count) route entries." -ForegroundColor Green

    $result.value |
        Select-Object `
            @{N='Prefix';E={$_.addressPrefixes -join ', '}}, `
            @{N='NextHopType';E={$_.nextHopType}}, `
            @{N='NextHop';E={$_.nextHops -join ', '}}, `
            @{N='RouteOrigin';E={$_.routeOrigin}}, `
            @{N='ASPath';E={$_.asPath}} |
        Format-Table -AutoSize
}