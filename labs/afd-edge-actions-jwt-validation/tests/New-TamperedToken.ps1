<#
.SYNOPSIS
  Standalone helper to construct tampered JWTs for S5/S6 testing.

.DESCRIPTION
  Builds a syntactically valid JWT with a modified payload but an INVALID signature.
  This is used to test whether the Edge Action (or origin) correctly rejects a token
  whose signature does not match the payload.

  SECURITY CONTRACT:
  - The full three-part tampered JWT is held only in a SecureString.
  - It is NEVER written to disk or echoed to the console.
  - Only the modified payload (decoded JSON) is optionally written to an evidence file.
  - The function returns a SecureString for the caller to use directly in HTTP requests.

.PARAMETER ValidToken
  A [System.Security.SecureString] containing a valid JWT acquired from Acquire-Token.

.PARAMETER PayloadOverrides
  Hashtable of claim overrides to apply to the original payload.
  Examples:
    @{ aud = 'api://wrong-audience' }            → S5 wrong audience
    @{ roles = @('Lab.SuperAdmin') }              → S6 tampered roles
    @{ exp = [int](Get-Date -UFormat %s) - 3600 } → S4 expired (if issuing a pre-expired token)

.OUTPUTS
  [System.Security.SecureString] containing the tampered token.

.EXAMPLE
  $tampered = New-TamperedToken -ValidToken $token -PayloadOverrides @{ aud = 'api://wrong' }
  # Pass $tampered directly to Invoke-AfdRequest -Token $tampered

.NOTES
  Niobe · 2026-08-17
  Intended for lab validation only. Do not use in production pipelines.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [System.Security.SecureString]$ValidToken,

    [Parameter(Mandatory)]
    [hashtable]$PayloadOverrides
)

function ConvertFrom-Base64Url {
    param([string]$Input)
    $pad = $Input.Length % 4
    $b64 = $Input.Replace('-','+').Replace('_','/')
    if ($pad -eq 2) { $b64 += '==' }
    elseif ($pad -eq 3) { $b64 += '=' }
    return [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64))
}

function ConvertTo-Base64Url {
    param([string]$Input)
    return [Convert]::ToBase64String(
        [System.Text.Encoding]::UTF8.GetBytes($Input)
    ).Replace('+','-').Replace('/','_').TrimEnd('=')
}

# Expand the SecureString to plain text transiently
$ptr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($ValidToken)
try {
    $plain = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($ptr)
} finally {
    [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}

$parts = $plain -split '\.'
[System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR(
    [System.Runtime.InteropServices.Marshal]::StringToBSTR($plain)
) 2>$null
$plain = $null

if ($parts.Count -ne 3) {
    throw "Input is not a valid three-part JWT."
}

# Decode original payload
$originalPayload = ConvertFrom-Base64Url -Input $parts[1] | ConvertFrom-Json -AsHashtable

# Apply overrides
foreach ($k in $PayloadOverrides.Keys) {
    $originalPayload[$k] = $PayloadOverrides[$k]
}

# Re-encode payload
$newPayloadJson  = $originalPayload | ConvertTo-Json -Compress -Depth 5
$newPayloadB64   = ConvertTo-Base64Url -Input $newPayloadJson

# Reassemble: original header + modified payload + ORIGINAL (now-invalid) signature
$tamperedToken = "$($parts[0]).$newPayloadB64.$($parts[2])"

# Write only the decoded payload to stdout for evidence (no signature)
Write-Host "`n[NEW-TAMPERED-TOKEN] Modified payload claims:"
Write-Host ($originalPayload | ConvertTo-Json -Depth 5)
Write-Host "(Full token held in memory as SecureString only; not displayed)`n"

# Return as SecureString
return ($tamperedToken | ConvertTo-SecureString -AsPlainText -Force)
