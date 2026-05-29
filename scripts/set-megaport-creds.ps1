# scripts/set-megaport-creds.ps1
# Prompts for Megaport API key + secret and stores them at User scope.
# Values are entered via Read-Host -AsSecureString so they never appear in
# chat, terminal history, ps_history.txt, or on disk.
#
# Usage:
#   .\scripts\set-megaport-creds.ps1
#   # then RESTART this CLI session so the new env vars are inherited.

$ErrorActionPreference = 'Stop'

function Read-Plain([string]$prompt) {
  $sec = Read-Host -Prompt $prompt -AsSecureString
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
  try   { return [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

Write-Host "Setting Megaport API credentials at User scope..." -ForegroundColor Cyan
Write-Host "(values will not be echoed)" -ForegroundColor DarkGray

$key    = Read-Plain "MEGAPORT_API_KEY"
$secret = Read-Plain "MEGAPORT_API_SECRET"

if ([string]::IsNullOrWhiteSpace($key) -or [string]::IsNullOrWhiteSpace($secret)) {
  Write-Host "Empty value detected. Aborting without changes." -ForegroundColor Red
  exit 1
}

[Environment]::SetEnvironmentVariable('MEGAPORT_API_KEY',    $key,    'User')
[Environment]::SetEnvironmentVariable('MEGAPORT_API_SECRET', $secret, 'User')

$key    = $null
$secret = $null
[GC]::Collect()

Write-Host ""
Write-Host "OK. Env vars saved at User scope." -ForegroundColor Green
Write-Host "Now RESTART the Copilot CLI (close + reopen) so it inherits them." -ForegroundColor Yellow
Write-Host ""
Write-Host "To verify after restart, ask me: 'check megaport env vars'" -ForegroundColor DarkGray
