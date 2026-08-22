[CmdletBinding()]
param(
    [string]$DeploymentOutput = (Join-Path $PSScriptRoot '..\evidence\deployment-output.json')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$deployment = Get-Content $DeploymentOutput -Raw | ConvertFrom-Json
$baseUrl = "https://$($deployment.endpointHostName)"
$evidenceDir = Split-Path $DeploymentOutput -Parent

$paths = @(
    '/control',
    '/ea/tracking-reference',
    '/ea/body-401',
    '/ea/body-403',
    '/ea/body-200',
    '/ea/header-401',
    '/ea/header-200',
    '/ea/cookie-401',
    '/ea/location-403',
    '/ea/unsupported-302',
    '/ea/unsupported-404',
    '/ea/unsupported-418',
    '/ea/unsupported-500',
    '/ea/alias-status',
    '/ea/alias-status-code',
    '/ea/alias-content',
    '/ea/alias-data',
    '/ea/alias-payload',
    '/ea/alias-header',
    '/ea/metadata',
    '/ea/body-object',
    '/ea/body-null',
    '/ea/body-empty'
)

$handler = [Net.Http.HttpClientHandler]::new()
$handler.AllowAutoRedirect = $false
$client = [Net.Http.HttpClient]::new($handler)
$client.Timeout = [TimeSpan]::FromSeconds(30)

$results = foreach ($path in $paths) {
    $response = $client.GetAsync("$baseUrl$path").GetAwaiter().GetResult()
    $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    $headers = [ordered]@{}
    foreach ($header in $response.Headers) {
        $headers[$header.Key] = @($header.Value)
    }
    foreach ($header in $response.Content.Headers) {
        $headers[$header.Key] = @($header.Value)
    }

    [ordered]@{
        path = $path
        status = [int]$response.StatusCode
        reasonPhrase = $response.ReasonPhrase
        originReached = $headers['x-origin-reached'] -contains 'true'
        edgeTestHeader = @($headers['x-ea-test']) -join ','
        edgeContextTrackingReference = @($headers['x-ea-context-tracking-reference']) -join ','
        location = @($headers['Location']) -join ','
        setCookie = @($headers['Set-Cookie'])
        contentType = @($headers['Content-Type']) -join ','
        azureRef = @($headers['X-Azure-Ref']) -join ','
        body = $body
        headers = $headers
    }
}

$results | ConvertTo-Json -Depth 10 |
    Set-Content (Join-Path $evidenceDir 'response-results.json') -Encoding utf8

$results |
    Select-Object path, status, originReached, edgeTestHeader, contentType, location, @{
        Name = 'body'
        Expression = {
            if ($_.body.Length -gt 100) {
                $_.body.Substring(0, 100)
            } else {
                $_.body
            }
        }
    } |
    Format-Table -AutoSize

$client.Dispose()
$handler.Dispose()
