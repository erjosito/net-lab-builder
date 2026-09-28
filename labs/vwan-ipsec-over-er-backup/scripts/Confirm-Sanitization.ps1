#Requires -Version 7.0
<#
.SYNOPSIS
  Rejects sensitive values from committed validation evidence.
#>
[CmdletBinding()]
param(
    [string]$Path = (Split-Path -Parent $PSScriptRoot)
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Path = (Resolve-Path $Path).Path
$patterns = [ordered]@{
    'Azure subscription ID' = '(?i)/subscriptions/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}'
    'Unredacted subscription segment' = '(?i)/subscriptions/(?!<)[^/\s"]+'
    'Tenant ID in Entra URL' = '(?i)login\.microsoftonline\.com/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}'
    'Bearer token' = '(?i)authorization:\s*bearer\s+(?!<REDACTED>)\S+'
    'JWT-shaped token' = '(?<![A-Za-z0-9_.-])eyJ[A-Za-z0-9_-]{7,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?![A-Za-z0-9_.-])'
    'Unredacted secret JSON field' = '(?i)"(?:serviceKey|pairingKey|preSharedKey|sharedKey|access_token|client_secret|apiKey|apiSecret)"\s*:\s*"(?!<REDACTED>)[^"]+"'
    'Private key material' = '-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'
    'Unredacted GUID' = '(?i)\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b'
    'Account email' = '(?i)[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}'
    'GCP billing account' = '(?i)billingAccounts/(?!<)[0-9A-Za-z-]+'
    'Billing account argument' = '(?i)--billing-account(?:=|\s+)(?!<)\S+'
    'Shell secret assignment' = '(?i)(?:\$?(?:psk|sharedKey|preSharedKey)|MEGAPORT_(?:API|ACCESS|SECRET)_(?:KEY|SECRET))\s*=\s*(?![<$])(?:"[^"]+"|''[^'']+''|[A-Za-z0-9+/=_-]{16,})'
}

$violations = [System.Collections.Generic.List[string]]::new()
$files = @(Get-ChildItem -Path $Path -Recurse -File -Include '*.txt','*.md','*.json','*.jsonl','*.log' |
    Where-Object {
        $_.FullName -notmatch '\\.git\\' -and
        $_.FullName -notmatch '\\diagrams\\' -and
        $_.FullName -notmatch '\\config\\inventory\.json$'
    })

foreach ($file in $files) {
    $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
    if (-not $content) { continue }
    foreach ($pattern in $patterns.GetEnumerator()) {
        if ($content -match $pattern.Value) {
            $violations.Add("$($pattern.Key): $($file.FullName)")
        }
    }
}

if ($violations.Count -gt 0) {
    $violations | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Host "SANITIZATION PASS: $($files.Count) files scanned."
