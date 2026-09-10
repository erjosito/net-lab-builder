# Skill: Operating Azure SQL data services under Entra-only auth and private network

## Context

This skill covers the patterns needed when a tenant enforces ALL of:
1. Entra-only SQL authentication (no SQL logins/passwords)
2. `publicNetworkAccess=Disabled` on SQL logical servers (force-applied, silent)
3. `allowSharedKeyAccess=false` on storage accounts (force-applied)

These three controls together mean: no SQL auth, no `az sql db export`, no storage keys.
Every workaround for one breaks something in another. This skill documents the combination
that actually works.

## Verified constraints (empirical)

### SQL authentication denied

Policy: `AzureSQL_WithoutAzureADOnlyAuthentication_Deny` in `MCAPSGovDenyPolicies` at
the management group. Creating a server without `--enable-ad-only-auth` fails.

**Working pattern for server create:**
```bash
az sql server create -g <rg> -n <server> -l <location> \
    --enable-ad-only-auth \
    --external-admin-principal-type Application \
    --external-admin-name <uami-name> \
    --external-admin-sid <uami-clientId> \
    --identity-type UserAssigned \
    --user-assigned-identity-id <uami-resource-id> \
    --pid <uami-resource-id>
```

Note: `--external-admin-sid` takes the UAMI's **clientId** (not principalId) when
`--external-admin-principal-type Application`.

### publicNetworkAccess force-disabled

`az sql server update --enable-public-network true` reports success but value stays
Disabled. Same for ARM PATCH and server create with the flag. This is enforced silently.

**Consequence:** `az sql db export` is unavailable. The BACPAC export service connects to
the database over the public endpoint, which is denied.

**Workaround:** `sqlpackage` running inside a VM in the same VNet, connected via private
endpoint. Authenticate with `/AccessToken:<token>`.

**Do not add SQL firewall rules.** They fail with `DenyPublicEndpointEnabled`.

### Storage sharedKey force-disabled

`az storage account keys list` still returns a key (trap: it's dead on data-plane calls).
Error from a dead key looks like a permissions error, not "keys disabled".

**Always use `--auth-mode login` for az CLI storage data-plane commands.**
**Use AzCopy with MSI env vars for blob upload from a VM.**

## Patterns

### Get IMDS token from VM (PowerShell 5.1, run-command context)

Correct IMDS path: `/metadata/identity/oauth2/token` (NOT `/imds/identity/oauth2/token`).
Use `curl.exe --noproxy "*"` to bypass any WinHTTP proxy routing:

```powershell
$UAMI_CLIENT_ID = '9dab92a8-7084-442e-8617-139fda64b1c9'  # your UAMI clientId
$url = "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fdatabase.windows.net%2F&client_id=$UAMI_CLIENT_ID"
$tokenJson = curl.exe --noproxy "*" -s -H "Metadata: true" $url 2>&1
$token = ($tokenJson | ConvertFrom-Json).access_token
```

For storage:
```powershell
$url = "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fstorage.azure.com%2F&client_id=$UAMI_CLIENT_ID"
```

### Connect to SQL with Invoke-Sqlcmd using UAMI token

```powershell
Import-Module SqlServer
$token = # ... (from IMDS above)
Invoke-Sqlcmd -ServerInstance 'server.database.windows.net' -Database 'mydb' `
    -AccessToken $token -Query 'SELECT @@VERSION' -TrustServerCertificate -QueryTimeout 60
```

### Create UAMI as contained user without Directory Readers

The UAMI needs Directory Readers to use `CREATE USER ... FROM EXTERNAL PROVIDER`.
Without that role, use the explicit SID pattern (GUID bytes in little-endian .NET order):

```powershell
# CRITICAL: parenthesise the -join BEFORE prepending '0x'
$bytes  = ([guid]$UAMI_CLIENT_ID).ToByteArray()
$hex    = ($bytes | ForEach-Object { $_.ToString('X2') }) -join ''
$sidHex = '0x' + $hex
# WRONG: '0x' + $bytes.ForEach({...}) -join ''  -> produces '0x A8 92 AB ...'
# RIGHT: the pattern above

$sql = "IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'$umiName')
    CREATE USER [$umiName] WITH SID = $sidHex, TYPE = E;
ALTER ROLE db_owner ADD MEMBER [$umiName];"
Invoke-Sqlcmd -ServerInstance $server -Database $db -AccessToken $token -Query $sql `
    -TrustServerCertificate -QueryTimeout 60
```

### Export SQL database with sqlpackage over private endpoint

```powershell
# Get fresh token immediately before the call (tokens are ~1 hour)
$token = # ... (from IMDS above)

& sqlpackage.exe /Action:Export `
    /SourceServerName:server.database.windows.net `
    /SourceDatabaseName:mydb `
    /AccessToken:$token `
    /TargetFile:C:\exports\mydb.bacpac `
    /p:CommandTimeout=0 `
    /p:VerifyExtraction=false
```

### Upload BACPAC to blob storage from VM (AzCopy + MSI)

```powershell
$env:AZCOPY_AUTO_LOGIN_TYPE = 'MSI'
$env:AZCOPY_MSI_CLIENT_ID = '9dab92a8-7084-442e-8617-139fda64b1c9'
# Create container if not exists (idempotent)
& C:\tools\azcopy.exe make 'https://storageacct.blob.core.windows.net/containername'
# Upload
& C:\tools\azcopy.exe copy 'C:\exports\mydb.bacpac' `
    'https://storageacct.blob.core.windows.net/containername/mydb.bacpac'
```

### Create blob container from workstation (data-plane blocked from workstation)

Cannot reach the storage data-plane from a workstation if `publicNetworkAccess=Disabled`.
Create the container from inside the VM via AzCopy or the Blob REST API.

### LTR policies require auto-pause disabled

```bash
# Must do this before ltr-policy set, or get LtrConfigPolicyUnsupportedIfAutoPauseEnabled
az sql db update -g <rg> -s <server> -n <db> --auto-pause-delay -1
az sql db ltr-policy set -g <rg> -s <server> -n <db> --weekly-retention P12W
```

## Measured compression ratios (as of 2026-09-10)

| Data shape | Ratio |
|---|---|
| Mixed realistic (75% repetitive text + 25% random binary) | ~4.0x |
| Highly repetitive (single byte pattern) | ~145x |
| High-entropy binary (CRYPT_GEN_RANDOM) | ~1.04x |

For budgeting: use **1.04x** (worst case). Storage dominates total cost by ~50x.
For typical business data: 4.0x is a reasonable default.

## Environment for measurements

- sqlpackage v170.4.83.3
- Standard_D4s_v5 VM (4 vCPU, 16 GB RAM)
- Same-region private endpoint (swedencentral)
- SQL Server logical server (GP_S_Gen5_4 serverless, auto-pause disabled)

## Known gotchas

1. IMDS path is `/metadata/...`, not `/imds/...`.
2. `az storage account keys list` returns a key that looks valid but fails at data-plane.
3. `publicNetworkAccess=Enabled` is accepted silently, then ignored.
4. `Install-Module ... -AcceptLicense` does not exist on the PSGet version in WS2022.
5. `$PSNativeCommandArgumentPassing` in PS7.4+ Windows mode drops empty-string args.
6. LTR policy + auto-pause: mutually exclusive. Disable auto-pause first.
7. AzCopy container must exist before `azcopy copy`. Use `azcopy make` first.
