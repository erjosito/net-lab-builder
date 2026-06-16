# SKILL: Megaport API Auth + KV Path B (Windows PowerShell)

**Version:** 1.0  
**Author:** Niobe  
**Date:** 2026-06-15  
**Applies to:** Any squad task requiring Megaport HTTP API access from Windows PowerShell when credentials live in `platform-secrets-1138` behind KV network ACLs.

---

## Problem

Megaport API credentials are stored in Azure Key Vault behind network restrictions. On Windows, environment variables do NOT persist across PowerShell tool invocations, so a multi-step "lift → fetch → restore → use" workflow will lose the credentials between steps.

## Pattern

**Everything in one script block.** Lift, fetch, restore, and all API calls must run in a single PowerShell process. Use `try/finally` to guarantee restore even on failure.

```powershell
$sub   = "<SUBSCRIPTION_ID>"
$vault = "platform-secrets-1138"

try {
    # 1. Capture current state
    $prior = (az keyvault network-rule list --name $vault --subscription $sub --query "defaultAction" -o tsv).Trim()

    # 2. Lift
    az keyvault update --name $vault --subscription $sub --default-action Allow --output none
    Start-Sleep -Seconds 10   # ACL propagation delay

    # 3. Fetch
    $mpKey    = (az keyvault secret show --vault-name $vault --subscription $sub --name "megaport-api-key"    --query value -o tsv).Trim()
    $mpSecret = (az keyvault secret show --vault-name $vault --subscription $sub --name "megaport-api-secret" --query value -o tsv).Trim()

    # 4. RESTORE IMMEDIATELY (before any API calls that could fail)
    az keyvault update --name $vault --subscription $sub --default-action $prior --output none

    # 5. Megaport auth (form-encoded — JSON body is rejected)
    $formData = "username=$mpKey&password=$mpSecret"
    $authRaw  = & curl.exe -s -X POST "https://api.megaport.com/v2/login" `
        -H "Content-Type: application/x-www-form-urlencoded" `
        -d $formData
    $authObj  = $authRaw | ConvertFrom-Json
    $token    = $authObj.data.session

    if (-not $token -or $token.Length -lt 10) {
        throw "Auth failed: $($authObj.message)"
    }

    # 6. Use token for API calls (never print $token)
    $result = & curl.exe -s -H "X-Auth-Token: $token" "https://api.megaport.com/v2/..."
    Write-Host $result

} finally {
    # Always verify KV is restored
    $final = (az keyvault network-rule list --name $vault --subscription $sub --query "defaultAction" -o tsv).Trim()
    if ($final -ne "Deny") {
        az keyvault update --name $vault --subscription $sub --default-action Deny --output none
    }
    Write-Host "KV_FINAL=$final"
}
```

## Key Gotchas

1. **One-process rule.** Env vars do NOT survive between PowerShell tool calls. If auth and API calls span multiple calls, the token is lost. Wrap everything in one script block.

2. **Restore before API calls, not after.** The `az keyvault update --default-action $prior` call belongs AFTER fetching secrets but BEFORE making Megaport API calls. This minimizes the window the vault is open. If the API call fails, the vault is already closed.

3. **Form-encoded only.** The `/v2/login` endpoint is a Spring Boot controller that requires `Content-Type: application/x-www-form-urlencoded`. JSON body returns `MissingServletRequestParameterException`. Use `curl.exe -d "username=...&password=..."`.

4. **No `--data-urlencode` if credentials contain `+` or `=`.** URL-encoding may corrupt credentials if the API expects them literal. Prefer `-d` with raw concatenation for alphanumeric API keys.

5. **10-attempt lockout.** Failed auth attempts count toward Megaport's 10-attempt lockout. Don't retry blindly. If you get HTTP 401, investigate credential freshness before retrying.

6. **Credential freshness.** KV secrets `megaport-api-key` and `megaport-api-secret` are the Megaport Terraform provider credentials (`access_key` / `secret_key`). These may differ from the raw `/v2/login` credentials if Megaport rotates them independently of the Terraform deploy. Verify key validity in the Megaport portal if auth fails.

## Secret Sanitization (before commit)

- Never write `$token` to any file. Write `X-Auth-Token: <REDACTED>` in captures.
- Never write the raw credentials. Redact as `<REDACTED>` in captures.
- MCR UIDs from Terraform state are NOT secrets — they can appear in filenames/captures.

## Known Auth Error Modes (2026 evidence)

| Date | Error | Root cause |
|------|-------|------------|
| 2026-06-15 | HTTP 401 "Invalid email or password" | Credentials in KV may be expired or the Megaport account auth format changed |
| 2026-05 (lab #1) | Auth succeeded, but `/diagnostics/routes/bgp` returned empty body | Looking-glass endpoint is unreliable (Megaport-side) |
