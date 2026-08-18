<#
.SYNOPSIS
  Sanitization checker for afd-edge-actions-jwt-validation evidence files.

.DESCRIPTION
  Scans all .txt and .md files under the specified path for patterns that would
  indicate a security-sensitive value was committed: subscription IDs, tenant IDs,
  raw JWTs, client secrets, and Authorization Bearer header values.

  Called automatically by Invoke-Validation.ps1 after each run.

.PARAMETER Path
  Directory to scan. Defaults to the lab root.

.PARAMETER FailOnMatch
  Exit with code 1 if any match is found. Default: $true.

.OUTPUTS
  Reports any matches found. Exits 0 if clean, 1 if violations found.

.NOTES
  Niobe · 2026-08-17
#>
[CmdletBinding()]
param(
    [string]$Path = (Join-Path $PSScriptRoot '..'),
    [bool]$FailOnMatch = $true
)

Set-StrictMode -Version Latest

$violations = [System.Collections.Generic.List[string]]::new()

# Patterns to reject in committed text files
$patterns = @(
    @{
        Name    = 'Full JWT (header.payload.signature)'
        Pattern = '[A-Za-z0-9\-_]{10,}\.[A-Za-z0-9\-_]{10,}\.[A-Za-z0-9\-_]{10,}'
        # A three-part base64url string ≥ 30 chars total is JWT-shaped
    },
    @{
        Name    = 'Authorization Bearer header value'
        Pattern = '(?i)authorization:\s*bearer\s+[A-Za-z0-9\-_\.]+'
    },
    @{
        Name    = 'client_secret JSON key with value'
        Pattern = '(?i)"client_secret"\s*:\s*"[^"]+"'
    },
    @{
        Name    = 'Subscription ID in resource path'
        # Matches /subscriptions/<guid> in Azure resource IDs
        Pattern = '/subscriptions/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
    },
    @{
        Name    = 'Tenant ID in AAD URL'
        Pattern = 'login\.microsoftonline\.com/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
    }
)

$files = Get-ChildItem -Path $Path -Recurse -Include '*.md','*.txt','*.json' -File |
    Where-Object {
        $_.FullName -notmatch '\\\.git\\' -and
        $_.FullName -notmatch '\\node_modules\\' -and
        $_.FullName -notmatch '\\diagrams\\'   # Oracle diagram files contain example values
    }

foreach ($file in $files) {
    $content = Get-Content -Path $file.FullName -Raw -ErrorAction SilentlyContinue
    if (-not $content) { continue }

    foreach ($p in $patterns) {
        if ($content -match $p.Pattern) {
            $msg = "VIOLATION [$($p.Name)] in: $($file.FullName)"
            $violations.Add($msg)
            Write-Warning $msg
        }
    }
}

if ($violations.Count -eq 0) {
    Write-Host "[SANITIZE] CLEAN — $($files.Count) files scanned, 0 violations."
    exit 0
} else {
    Write-Warning "[SANITIZE] $($violations.Count) violation(s) found. Fix before committing."
    if ($FailOnMatch) { exit 1 }
}
