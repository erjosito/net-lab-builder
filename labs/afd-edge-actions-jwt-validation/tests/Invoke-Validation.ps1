<#
.SYNOPSIS
  Validation harness for afd-edge-actions-jwt-validation lab.

.DESCRIPTION
  Executes scenarios S1–S9 against a deployed lab. Reads deployment outputs from
  deploy/deployment-output.json (or environment variables). Acquires Entra ID tokens via
  client-credentials flow without printing or persisting raw tokens. Captures HTTP
  status codes, response headers (with Bearer values redacted), and queries Log Analytics.

  Prerequisites:
    - az CLI authenticated with access to rg-afd-edge-jwt-lab
    - Environment variables: TENANT_ID, CLIENT_ID, CLIENT_SECRET, API_APP_ID
    - deploy/deployment-output.json populated by Tank (or env vars AFD_ENDPOINT, APP_NAME, LAW_WORKSPACE_ID)

  Usage:
    $env:TENANT_ID    = "<tenant-id>"
    $env:CLIENT_ID    = "<client-app-id>"
    $env:CLIENT_SECRET= "<secret>"       # never echoed; never written to disk
    $env:API_APP_ID   = "<api-app-id>"
    .\tests\Invoke-Validation.ps1 -Scenario All

  Single scenario:
    .\tests\Invoke-Validation.ps1 -Scenario S1

  Dry-run (no HTTP calls, structure check only):
    .\tests\Invoke-Validation.ps1 -DryRun

  SECURITY CONTRACT:
    - Tokens are held only in SecureString or as [System.Security.SecureString]-typed
      variables during acquisition. They are converted to plain string only for the
      Authorization header value, which is immediately used and then discarded.
    - The Authorization header value is NEVER written to any file or to the host.
    - Evidence files contain HTTP status codes, response bodies, and response headers
      with the Authorization header stripped and any X-Azure-FDID value truncated.
    - All output files are checked by Confirm-Sanitization.ps1 before the script exits.

.PARAMETER Scenario
  Which scenario to run: S1, S2, S3, S4, S5, S6, S7, S8, S9, or All.

.PARAMETER DryRun
  Print the plan without making any HTTP calls or az CLI calls.

.PARAMETER SkipLogQuery
  Skip Log Analytics queries (useful when logs have not yet ingested).

.PARAMETER LogDelay
  Seconds to wait before querying Log Analytics. Default 600 (10 min).

.NOTES
  Niobe · 2026-08-17
  Do not deploy or modify Azure resources.
  Do not print or write raw bearer tokens.
#>

[CmdletBinding()]
param(
    [ValidateSet('S1','S2','S3','S4','S5','S6','S7','S8','S9','All')]
    [string]$Scenario = 'All',
    [switch]$DryRun,
    [switch]$SkipLogQuery,
    [int]$LogDelay = 600
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
$LabRoot      = Join-Path $PSScriptRoot '..'
$EvidenceDir  = Join-Path $LabRoot 'evidence'
$ShowDir      = Join-Path $LabRoot 'show-output'
$DeployOutput = Join-Path $LabRoot 'deploy\deployment-output.json'

foreach ($d in $EvidenceDir, $ShowDir) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

# ---------------------------------------------------------------------------
# Sequential show-output counter
# ---------------------------------------------------------------------------
$script:ShowCounter = 1
function Save-ShowOutput {
    param([string]$Slug, [string]$Content)
    $n    = $script:ShowCounter.ToString('D3')
    $file = Join-Path $ShowDir "$n-$Slug.txt"
    # Sanitize before write
    $safe = Protect-Output -Text $Content
    Set-Content -Path $file -Value $safe -Encoding UTF8
    $script:ShowCounter++
    return $file
}

# ---------------------------------------------------------------------------
# Sanitization helper (inline; full version in Confirm-Sanitization.ps1)
# ---------------------------------------------------------------------------
function Protect-Output {
    param([string]$Text)
    # Redact Authorization header values (Bearer tokens)
    $out = $Text -replace '(?i)(authorization:\s*bearer\s+)[A-Za-z0-9\-_\.]+(\.[A-Za-z0-9\-_\.]+){1,2}', '$1<REDACTED>'
    # Redact full JWT shapes anywhere in text (header.payload.signature)
    $out = $out -replace '[A-Za-z0-9\-_]{10,}\.[A-Za-z0-9\-_]{10,}\.[A-Za-z0-9\-_]{10,}', '<JWT_REDACTED>'
    # Redact GUID-like strings in known sensitive positions; preserve resource names
    # Subscription IDs appear after /subscriptions/ in resource IDs
    $out = $out -replace '(?<=/subscriptions/)[0-9a-f\-]{36}', '<SUB_ID>'
    # Tenant IDs appear as issuer claim fragment or AAD URL segment
    $out = $out -replace '(?<=login\.microsoftonline\.com/)[0-9a-f\-]{36}', '<TENANT_ID>'
    return $out
}

# ---------------------------------------------------------------------------
# Load deployment outputs
# ---------------------------------------------------------------------------
$cfg = @{}
if (Test-Path $DeployOutput) {
    $json = Get-Content $DeployOutput -Raw | ConvertFrom-Json
    # Deploy-Lab.ps1 output fields: afd_endpoint, app_service_name, law_name
    $cfg.AfdEndpoint    = $json.afd_endpoint     ?? $json.afdEndpointHostname ?? $env:AFD_ENDPOINT    ?? ''
    $cfg.AppName        = $json.app_service_name  ?? $json.appServiceName       ?? $env:APP_NAME         ?? ''
    $cfg.LawWorkspaceId = $json.law_workspace_id  ?? $json.law_name             ?? $env:LAW_WORKSPACE_ID ?? ''
    $cfg.ResourceGroup  = $json.resource_group    ?? 'rg-afd-edge-jwt-lab'
    # Entra IDs from deployment output (non-secret)
    if ($json.entra) {
        if (-not $cfg.TenantId  -and $json.entra.tenant_id)    { $cfg.TenantId  = $json.entra.tenant_id }
        if (-not $cfg.ClientId  -and $json.entra.client_app_id) { $cfg.ClientId  = $json.entra.client_app_id }
        if (-not $cfg.ApiAppId  -and $json.entra.api_app_id)    { $cfg.ApiAppId  = $json.entra.api_app_id }
    }
    Write-Host "[CONFIG] Loaded from deployment-output.json"
} else {
    Write-Warning "[CONFIG] deploy/deployment-output.json not found — falling back to env vars"
    $cfg.AfdEndpoint    = $env:AFD_ENDPOINT    ?? ''
    $cfg.AppName        = $env:APP_NAME         ?? ''
    $cfg.LawWorkspaceId = $env:LAW_WORKSPACE_ID ?? ''
    $cfg.ResourceGroup  = 'rg-afd-edge-jwt-lab'
}

# Entra ID (always from env vars — never from committed files)
$cfg.TenantId   = $env:TENANT_ID   ?? ''
$cfg.ClientId   = $env:CLIENT_ID   ?? ''
$cfg.ApiAppId   = $env:API_APP_ID  ?? ''
# CLIENT_SECRET deliberately NOT stored in $cfg; retrieved inline in Acquire-Token

# ---------------------------------------------------------------------------
# Preflight guard
# ---------------------------------------------------------------------------
function Assert-Config {
    $required = @('AfdEndpoint','AppName','LawWorkspaceId','TenantId','ClientId','ApiAppId')
    $missing  = $required | Where-Object { -not $cfg[$_] }
    if ($missing) {
        Write-Error "Missing required config/env vars: $($missing -join ', '). Deployment must be complete before running scenarios."
        exit 1
    }
}

if (-not $DryRun) { Assert-Config }

# ---------------------------------------------------------------------------
# Token acquisition (never prints token; never writes token to disk)
# ---------------------------------------------------------------------------
function Acquire-Token {
    <#
    Returns a [System.Security.SecureString] containing the access token.
    The plain-text token is materialised only inside the function and in the
    Invoke-Scenario callers immediately before use, then discarded.
    #>
    if (-not $env:CLIENT_SECRET) {
        throw "CLIENT_SECRET environment variable is not set. Token acquisition impossible."
    }

    $body = @{
        grant_type    = 'client_credentials'
        client_id     = $cfg.ClientId
        client_secret = $env:CLIENT_SECRET   # used only here; never logged
        scope         = "api://$($cfg.ApiAppId)/.default"
    }

    $resp = Invoke-RestMethod `
        -Uri    "https://login.microsoftonline.com/$($cfg.TenantId)/oauth2/v2.0/token" `
        -Method Post `
        -Body   $body `
        -ContentType 'application/x-www-form-urlencoded'

    if (-not $resp.access_token) {
        throw "Token acquisition failed — no access_token in response."
    }

    # Return as SecureString so callers must explicitly convert to use it
    return ($resp.access_token | ConvertTo-SecureString -AsPlainText -Force)
}

function Expand-SecureToken {
    param([System.Security.SecureString]$SecureToken)
    $ptr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureToken)
    try {
        return [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($ptr)
    } finally {
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

# ---------------------------------------------------------------------------
# HTTP helper — captures status, headers, body; redacts Authorization header
# ---------------------------------------------------------------------------
function Invoke-AfdRequest {
    param(
        [string]$Uri,
        [hashtable]$Headers = @{},
        [switch]$IncludeAuth,
        [System.Security.SecureString]$Token,
        [string]$Slug
    )

    $reqHeaders = @{}
    foreach ($k in $Headers.Keys) { $reqHeaders[$k] = $Headers[$k] }

    if ($IncludeAuth -and $Token) {
        $plain = Expand-SecureToken -SecureToken $Token
        $reqHeaders['Authorization'] = "Bearer $plain"
        Clear-Variable plain  # discard immediately after header is set
    }

    if ($DryRun) {
        Write-Host "[DRY-RUN] GET $Uri | Headers: $($reqHeaders.Keys -join ', ' | Where-Object {$_ -ne 'Authorization'})"
        return [PSCustomObject]@{ StatusCode = 0; Headers = @{}; Body = '(dry-run)'; AzureRef = '' }
    }

    try {
        $response = Invoke-WebRequest -Uri $Uri -Headers $reqHeaders -Method Get `
            -UseBasicParsing -MaximumRedirection 0 -ErrorAction Stop
    } catch {
        # Non-2xx responses throw in Invoke-WebRequest — capture them
        if ($_.Exception.Response) {
            $response = $_.Exception.Response
            # Re-read as a minimal object
            $sc = [int]$response.StatusCode
            $hdrs = @{}
            if ($response.Headers) {
                $response.Headers | ForEach-Object { $hdrs[$_.Key] = $_.Value -join ',' }
            }
            $result = [PSCustomObject]@{
                StatusCode = $sc
                Headers    = $hdrs
                Body       = "(error response)"
                AzureRef   = $hdrs['X-Azure-Ref'] ?? ''
            }
        } else {
            throw
        }
    }

    if ($response -is [Microsoft.PowerShell.Commands.WebResponseObject]) {
        $hdrs = @{}
        $response.Headers.GetEnumerator() | ForEach-Object { $hdrs[$_.Key] = $_.Value }
        $result = [PSCustomObject]@{
            StatusCode = [int]$response.StatusCode
            Headers    = $hdrs
            Body       = $response.Content
            AzureRef   = $hdrs['X-Azure-Ref'] ?? ''
        }
    }

    # Build safe evidence string (no Authorization value)
    $safeHeaders = ($result.Headers.GetEnumerator() |
        Where-Object { $_.Key -ne 'Authorization' } |
        ForEach-Object { "  $($_.Key): $($_.Value)" }) -join "`n"

    $evidenceText = @"
URI:    $Uri
Status: $($result.StatusCode)
X-Azure-Ref: $($result.AzureRef)
Headers (Authorization stripped):
$safeHeaders
Body:
$($result.Body)
"@

    if ($Slug) {
        Save-ShowOutput -Slug $Slug -Content $evidenceText | Out-Null
    }

    return $result
}

# ---------------------------------------------------------------------------
# KQL helper
# ---------------------------------------------------------------------------
function Invoke-KQL {
    param([string]$Query, [string]$Slug)

    if ($DryRun -or $SkipLogQuery) {
        Write-Host "[DRY-RUN/SKIP] KQL: $Slug"
        return '(skipped)'
    }

    $result = az monitor log-analytics query `
        --workspace $cfg.LawWorkspaceId `
        --analytics-query $Query `
        --output json 2>&1

    if ($Slug) {
        Save-ShowOutput -Slug $Slug -Content ($result | Out-String) | Out-Null
    }
    return $result
}

# ---------------------------------------------------------------------------
# Evidence file writer
# ---------------------------------------------------------------------------
function Write-Evidence {
    param([string]$Scenario, [string]$Content)
    $file = Join-Path $EvidenceDir "$Scenario.md"
    $safe = Protect-Output -Text $Content
    Set-Content -Path $file -Value $safe -Encoding UTF8
    Write-Host "[EVIDENCE] Written: $file"
}

# ---------------------------------------------------------------------------
# Decode JWT payload (header + payload only; never writes signature)
# ---------------------------------------------------------------------------
function Get-TokenPayload {
    param([System.Security.SecureString]$Token)
    $plain  = Expand-SecureToken -SecureToken $Token
    $parts  = $plain -split '\.'
    Clear-Variable plain
    if ($parts.Count -ne 3) { return '(invalid JWT shape)' }
    $pad = $parts[1].Length % 4
    $b64 = $parts[1].Replace('-','+').Replace('_','/')
    if ($pad -eq 2) { $b64 += '==' }
    elseif ($pad -eq 3) { $b64 += '=' }
    try { return [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64)) }
    catch { return '(decode failed)' }
}

# ---------------------------------------------------------------------------
# Build a tampered token (modified payload, original header + sig — sig invalid)
# Does NOT write the full token anywhere
# ---------------------------------------------------------------------------
function New-TamperedToken {
    param(
        [System.Security.SecureString]$ValidToken,
        [hashtable]$PayloadOverrides
    )
    $plain  = Expand-SecureToken -SecureToken $ValidToken
    $parts  = $plain -split '\.'
    Clear-Variable plain

    $pad = $parts[1].Length % 4
    $b64 = $parts[1].Replace('-','+').Replace('_','/')
    if ($pad -eq 2) { $b64 += '==' }
    elseif ($pad -eq 3) { $b64 += '=' }

    $payload = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64)) |
        ConvertFrom-Json -AsHashtable

    foreach ($k in $PayloadOverrides.Keys) { $payload[$k] = $PayloadOverrides[$k] }

    $newPayB64 = [Convert]::ToBase64String(
        [System.Text.Encoding]::UTF8.GetBytes(($payload | ConvertTo-Json -Compress))
    ).Replace('+','-').Replace('/','_').TrimEnd('=')

    # Reassemble with ORIGINAL signature — cryptographically invalid
    $tampered = "$($parts[0]).$newPayB64.$($parts[2])"
    return ($tampered | ConvertTo-SecureString -AsPlainText -Force)
}

# ---------------------------------------------------------------------------
# SCENARIOS
# ---------------------------------------------------------------------------

function Invoke-S1 {
    Write-Host "`n[S1] Capability Probe"
    $afdBase = "https://$($cfg.AfdEndpoint)"

    $r = Invoke-AfdRequest -Uri "$afdBase/debug/request" -Slug 's1-capability-probe-request'

    Write-Host "  HTTP $($r.StatusCode)  X-Azure-Ref: $($r.AzureRef)"

    if (-not $SkipLogQuery) {
        Write-Host "  Waiting $LogDelay s for log ingestion..."
        Start-Sleep -Seconds $LogDelay
    }

    $kql = @"
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.CDN"
| where Category == "EdgeActionConsoleLog"
| where LogMessage startswith "PROBE" or LogMessage startswith "JWKS_FETCH"
| project TimeGenerated, LogMessage
| order by TimeGenerated desc
| take 50
"@
    $kqlResult = Invoke-KQL -Query $kql -Slug 's1-capability-probe-kql'

    Write-Evidence -Scenario 'S1-capability-probe' -Content @"
# S1 — Capability Probe Evidence

HTTP Status: $($r.StatusCode)
X-Azure-Ref: $($r.AzureRef)

## KQL Result (EdgeActionConsoleLog PROBE lines)
$kqlResult

## Verdict
PENDING — populate after reviewing PROBE lines.
GO if: crypto=object AND crypto_subtle=object AND fetch=function
CONDITIONAL if: crypto present but fetch absent
STOP if: ea-capability-probe did not run (no PROBE JSON=function line)
"@
}

function Invoke-S2 {
    Write-Host "`n[S2] Missing Token"
    $r = Invoke-AfdRequest -Uri "https://$($cfg.AfdEndpoint)/protected" -Slug 's2-missing-token'
    Write-Host "  HTTP $($r.StatusCode) — expected 401"
    $pass = $r.StatusCode -eq 401
    Write-Evidence -Scenario 'S2-missing-token' -Content @"
# S2 — Missing Token

HTTP Status: $($r.StatusCode)  (expected: 401)
X-Azure-Ref: $($r.AzureRef)
Verdict: $(if ($pass) { 'PASS' } else { 'FAIL — unexpected status' })
"@
}

function Invoke-S3 {
    Write-Host "`n[S3] Valid Token"
    $token    = Acquire-Token
    $payload  = Get-TokenPayload -Token $token

    $rProt = Invoke-AfdRequest -Uri "https://$($cfg.AfdEndpoint)/protected" `
        -IncludeAuth -Token $token -Slug 's3-valid-token-protected'
    $rAdmin = Invoke-AfdRequest -Uri "https://$($cfg.AfdEndpoint)/admin" `
        -IncludeAuth -Token $token -Slug 's3-valid-token-admin'

    Write-Host "  /protected: HTTP $($rProt.StatusCode) — expected 200"
    Write-Host "  /admin:     HTTP $($rAdmin.StatusCode) — expected 200"

    Write-Evidence -Scenario 'S3-valid-token' -Content @"
# S3 — Valid Token

/protected:  HTTP $($rProt.StatusCode)  X-Azure-Ref: $($rProt.AzureRef)
/admin:      HTTP $($rAdmin.StatusCode)  X-Azure-Ref: $($rAdmin.AzureRef)

## Token claims (payload only — no signature)
$payload

## Verdict
/protected: $(if ($rProt.StatusCode -eq 200) { 'PASS' } else { 'FAIL' })
/admin:     $(if ($rAdmin.StatusCode -eq 200) { 'PASS' } else { 'FAIL' })
"@
}

function Invoke-S4 {
    Write-Host "`n[S4] Expired Token — waiting for natural expiry or use pre-expired token"
    Write-Host "  NOTE: Acquire a token, wait past exp, re-submit. Or pass PRE_EXPIRED_TOKEN env var."

    # If a pre-expired token is provided via env (as base64-of-header.payload only, no sig)
    # this scenario can run immediately. Otherwise it requires waiting.
    if ($env:PRE_EXPIRED_TOKEN) {
        $expiredSec = $env:PRE_EXPIRED_TOKEN | ConvertTo-SecureString -AsPlainText -Force
        $r = Invoke-AfdRequest -Uri "https://$($cfg.AfdEndpoint)/protected" `
            -IncludeAuth -Token $expiredSec -Slug 's4-expired-token'
        Write-Host "  HTTP $($r.StatusCode) — expected 401"
        $pass = $r.StatusCode -eq 401
    } else {
        Write-Host "  [SKIP] PRE_EXPIRED_TOKEN not set. Run after token naturally expires."
        $r     = [PSCustomObject]@{ StatusCode = 0; AzureRef = '' }
        $pass  = $false
    }

    Write-Evidence -Scenario 'S4-expired-token' -Content @"
# S4 — Expired Token

HTTP Status: $($r.StatusCode)  (expected: 401)
X-Azure-Ref: $($r.AzureRef)
PRE_EXPIRED_TOKEN supplied: $(if ($env:PRE_EXPIRED_TOKEN) { 'YES' } else { 'NO — SKIPPED' })
Verdict: $(if ($pass) { 'PASS' } elseif (-not $env:PRE_EXPIRED_TOKEN) { 'SKIPPED' } else { 'FAIL' })
"@
}

function Invoke-S5 {
    Write-Host "`n[S5] Wrong Audience"
    # Construct a JWT with a different aud by tampering the payload
    $token   = Acquire-Token
    $tampered = New-TamperedToken -ValidToken $token -PayloadOverrides @{ aud = 'api://wrong-audience-00000000' }

    $r = Invoke-AfdRequest -Uri "https://$($cfg.AfdEndpoint)/protected" `
        -IncludeAuth -Token $tampered -Slug 's5-wrong-audience'
    Write-Host "  HTTP $($r.StatusCode) — expected 401"

    Write-Evidence -Scenario 'S5-wrong-audience' -Content @"
# S5 — Wrong Audience

HTTP Status: $($r.StatusCode)  (expected: 401)
X-Azure-Ref: $($r.AzureRef)
Method: tampered payload with aud='api://wrong-audience-00000000' (invalid sig)

Verdict: $(if ($r.StatusCode -eq 401) { 'PASS' } else { 'FAIL — CRITICAL if 200' })
Note: On CONDITIONAL (claim-only) path, this still fails at aud check in EA.
      On GO path, signature is also invalid — double rejection.
"@
}

function Invoke-S6 {
    Write-Host "`n[S6] Tampered Signature"
    $token   = Acquire-Token
    $origPayload = Get-TokenPayload -Token $token | ConvertFrom-Json -AsHashtable

    # Add a role that was not granted
    $origRoles = @($origPayload.roles) + @('Lab.SuperAdmin')
    $tampered  = New-TamperedToken -ValidToken $token -PayloadOverrides @{ roles = $origRoles }

    $r = Invoke-AfdRequest -Uri "https://$($cfg.AfdEndpoint)/protected" `
        -IncludeAuth -Token $tampered -Slug 's6-tampered-sig'
    Write-Host "  HTTP $($r.StatusCode) — expected 401 (CRITICAL if 200)"

    $verdict = if ($r.StatusCode -eq 401) { 'PASS' }
               elseif ($r.StatusCode -eq 200) { 'CRITICAL — SIG_BYPASS (NIOBE-CRIT-001)' }
               else { "FAIL — unexpected $($r.StatusCode)" }

    Write-Evidence -Scenario 'S6-tampered-sig' -Content @"
# S6 — Tampered Token / Signature Bypass

HTTP Status: $($r.StatusCode)  (expected: 401)
X-Azure-Ref: $($r.AzureRef)
Modification: roles array extended with Lab.SuperAdmin; original signature reused (invalid)

Verdict: $verdict
"@

    if ($r.StatusCode -eq 200) {
        Write-Warning "*** CRITICAL FINDING NIOBE-CRIT-001 *** Tampered signature accepted. Notify Jose immediately."
    }
}

function Invoke-S7 {
    Write-Host "`n[S7] Role-Based Authorization (no Lab.Admin)"
    Write-Host "  NOTE: Requires token WITHOUT Lab.Admin role."
    Write-Host "  Set NO_ROLE_CLIENT_ID / NO_ROLE_CLIENT_SECRET env vars for a second client without the role."

    if ($env:NO_ROLE_CLIENT_ID -and $env:NO_ROLE_CLIENT_SECRET) {
        $savedId     = $cfg.ClientId
        $savedSecret = $env:CLIENT_SECRET
        $cfg.ClientId          = $env:NO_ROLE_CLIENT_ID
        $env:CLIENT_SECRET     = $env:NO_ROLE_CLIENT_SECRET
        $tokenNoRole = Acquire-Token
        $cfg.ClientId          = $savedId
        $env:CLIENT_SECRET     = $savedSecret

        $rAdmin = Invoke-AfdRequest -Uri "https://$($cfg.AfdEndpoint)/admin" `
            -IncludeAuth -Token $tokenNoRole -Slug 's7-rbac-admin-403'
        $rProt  = Invoke-AfdRequest -Uri "https://$($cfg.AfdEndpoint)/protected" `
            -IncludeAuth -Token $tokenNoRole -Slug 's7-rbac-protected-200'

        Write-Host "  /admin:     HTTP $($rAdmin.StatusCode) — expected 403"
        Write-Host "  /protected: HTTP $($rProt.StatusCode)  — expected 200"

        Write-Evidence -Scenario 'S7-rbac' -Content @"
# S7 — Role-Based Authorization

/admin:     HTTP $($rAdmin.StatusCode)  (expected: 403)
/protected: HTTP $($rProt.StatusCode)   (expected: 200)

Verdict /admin:     $(if ($rAdmin.StatusCode -eq 403) { 'PASS' } else { 'FAIL' })
Verdict /protected: $(if ($rProt.StatusCode -eq 200)  { 'PASS' } else { 'FAIL' })
"@
    } else {
        Write-Host "  [SKIP] NO_ROLE_CLIENT_ID / NO_ROLE_CLIENT_SECRET not set."
        Write-Evidence -Scenario 'S7-rbac' -Content @"
# S7 — Role-Based Authorization

SKIPPED — NO_ROLE_CLIENT_ID / NO_ROLE_CLIENT_SECRET environment variables not set.
To run: register a second client app without Lab.Admin role; set those env vars.
"@
    }
}

function Invoke-S8 {
    Write-Host "`n[S8] Direct Origin Bypass"
    $directUri = "https://$($cfg.AppName).azurewebsites.net/protected"
    $afdUri    = "https://$($cfg.AfdEndpoint)/protected"
    $token     = Acquire-Token

    $rDirect = Invoke-AfdRequest -Uri $directUri -Slug 's8-direct-bypass'
    $rAfd    = Invoke-AfdRequest -Uri $afdUri -IncludeAuth -Token $token -Slug 's8-via-afd'

    Write-Host "  Direct ($directUri): HTTP $($rDirect.StatusCode) — expected 403"
    Write-Host "  Via AFD:              HTTP $($rAfd.StatusCode)    — expected 200"

    $verdict = if ($rDirect.StatusCode -eq 403) { 'PASS' }
               elseif ($rDirect.StatusCode -eq 200) { 'CRITICAL — DIRECT_BYPASS (NIOBE-CRIT-002)' }
               else { "CHECK — unexpected $($rDirect.StatusCode)" }

    Write-Evidence -Scenario 'S8-direct-bypass' -Content @"
# S8 — Direct Origin Bypass

Direct to azurewebsites.net: HTTP $($rDirect.StatusCode)  (expected: 403)
Via AFD endpoint:             HTTP $($rAfd.StatusCode)     (expected: 200 with valid token)

Verdict: $verdict
"@

    if ($rDirect.StatusCode -eq 200) {
        Write-Warning "*** CRITICAL FINDING NIOBE-CRIT-002 *** Direct origin bypass succeeded. Notify Jose immediately."
    }
}

function Invoke-S9 {
    Write-Host "`n[S9] Controlled Fail-Open / Defence-in-Depth (Pivotal)"
    $token = Acquire-Token

    $rEdgeOnly = Invoke-AfdRequest -Uri "https://$($cfg.AfdEndpoint)/edge-only" `
        -IncludeAuth -Token $token `
        -Headers @{ 'X-Test-Fail' = '1' } `
        -Slug 's9-failopen-edgeonly'

    $rProtected = Invoke-AfdRequest -Uri "https://$($cfg.AfdEndpoint)/protected" `
        -IncludeAuth -Token $token `
        -Headers @{ 'X-Test-Fail' = '1' } `
        -Slug 's9-failopen-protected'

    Write-Host "  /edge-only  + X-Test-Fail:1: HTTP $($rEdgeOnly.StatusCode)  — expected 200 (fail-open, teaching gap)"
    Write-Host "  /protected  + X-Test-Fail:1: HTTP $($rProtected.StatusCode) — expected 401/403 (origin backstop)"

    if (-not $SkipLogQuery) {
        Start-Sleep -Seconds ([Math]::Min($LogDelay, 60))
        $kql9 = @"
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.CDN"
| where Category == "FrontDoorAccessLog"
| where requestUri_s contains "/protected" or requestUri_s contains "/edge-only"
| project TimeGenerated, requestUri_s, httpStatusCode_d, edgeActionsStatusCode_s
| order by TimeGenerated desc
| take 20
"@
        $kqlResult = Invoke-KQL -Query $kql9 -Slug 's9-afd-accesslog-kql'
    } else {
        $kqlResult = '(skipped)'
    }

    $verdictEdge = if ($rEdgeOnly.StatusCode -eq 200)   { 'PASS (expected teaching failure)' }
                   elseif ($rEdgeOnly.StatusCode -eq 401) { 'NOTE — edge-only also protected; DID overkill' }
                   else { "CHECK $($rEdgeOnly.StatusCode)" }

    $verdictDid  = if ($rProtected.StatusCode -in 401,403) { 'PASS — origin backstop confirmed' }
                   elseif ($rProtected.StatusCode -eq 200)  { 'CRITICAL — DID_BROKEN (NIOBE-CRIT-003)' }
                   else { "CHECK $($rProtected.StatusCode)" }

    Write-Evidence -Scenario 'S9-fail-open' -Content @"
# S9 — Fail-Open / Defence-in-Depth

/edge-only  + X-Test-Fail:1: HTTP $($rEdgeOnly.StatusCode)   Verdict: $verdictEdge
/protected  + X-Test-Fail:1: HTTP $($rProtected.StatusCode)  Verdict: $verdictDid

## AFD Access Log (edgeActionsStatusCode check)
$kqlResult

Pivotal result: The split outcome proves origin re-validation is mandatory.
"@

    if ($rProtected.StatusCode -eq 200) {
        Write-Warning "*** CRITICAL FINDING NIOBE-CRIT-003 *** /protected returned 200 on fail-open. Defence-in-depth broken. Notify Jose."
    }
}

# ---------------------------------------------------------------------------
# Run requested scenarios
# ---------------------------------------------------------------------------

$run = switch ($Scenario) {
    'All' { 'S1','S2','S3','S4','S5','S6','S7','S8','S9' }
    default { @($Scenario) }
}

Write-Host "`n=== afd-edge-actions-jwt-validation — Validation Harness ==="
Write-Host "Scenario(s): $($run -join ', ')  |  DryRun: $DryRun  |  SkipLogQuery: $SkipLogQuery"
Write-Host "AFD Endpoint : $($cfg.AfdEndpoint)"
Write-Host "App Name     : $($cfg.AppName)"
Write-Host "Log Analytics: $($cfg.LawWorkspaceId)"
Write-Host ""

foreach ($s in $run) {
    switch ($s) {
        'S1' { Invoke-S1 }
        'S2' { Invoke-S2 }
        'S3' { Invoke-S3 }
        'S4' { Invoke-S4 }
        'S5' { Invoke-S5 }
        'S6' { Invoke-S6 }
        'S7' { Invoke-S7 }
        'S8' { Invoke-S8 }
        'S9' { Invoke-S9 }
    }
}

# ---------------------------------------------------------------------------
# Post-run sanitization check
# ---------------------------------------------------------------------------
Write-Host "`n[SANITIZE] Running post-run sanitization check..."
& (Join-Path $PSScriptRoot 'Confirm-Sanitization.ps1') -Path (Join-Path $LabRoot 'evidence') -Verbose:$false
& (Join-Path $PSScriptRoot 'Confirm-Sanitization.ps1') -Path (Join-Path $LabRoot 'show-output') -Verbose:$false

Write-Host "`n=== Validation run complete. Evidence: $EvidenceDir ==="
