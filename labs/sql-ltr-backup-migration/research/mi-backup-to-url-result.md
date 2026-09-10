# Managed Instance BACKUP TO URL with Managed Identity credential

Date: 2026-09-10T12:23:44+02:00

## Verdicts

**Verdict A, credential syntax: SUPPORTED.** Azure SQL Managed Instance accepted `CREATE CREDENTIAL [https://...] WITH IDENTITY = 'Managed Identity'`. `sys.credentials` returned `credential_identity = Managed Identity`.

**Verdict B, end-to-end backup to storage using that identity: SUPPORTED, after service-managed TDE is disabled and the database encryption key is dropped.** The backup reached Azure Blob Storage with `allowSharedKeyAccess=false` and `publicNetworkAccess=Disabled`, wrote `mitest.bak`, and the artifact passed `RESTORE HEADERONLY` and `RESTORE VERIFYONLY`.

**Separate TDE caveat confirmation: CONFIRMED.** `BACKUP TO URL` on the original service-managed TDE database failed with Msg 41922 exactly as the README decision tree anticipated. After `ALTER DATABASE [mitest] SET ENCRYPTION OFF`, Managed Instance still required `DROP DATABASE ENCRYPTION KEY`; otherwise `BACKUP WITH COPY_ONLY` failed with Msg 41938.

## Environment tested

- Managed Instance: `ltrlab552754-mi.8a97d4e15d77.database.windows.net`
- Resource group: `rg-ltr-lab`
- Subscription: `a8fbd8e1-fb5a-4411-804a-4ac80929c93c`
- MI identity: User-assigned managed identity `ltrlab552754-umi`
- UAMI clientId: `9dab92a8-7084-442e-8617-139fda64b1c9`
- UAMI principalId: `6ae8e9fe-6b1a-437f-bf94-83430a391337`
- Storage account: `ltrlab552754sa`
- Container: `mi-backups`
- Backup blob: `mitest.bak`
- VM execution host: `ltrlab-vm`, reached only through `az vm run-command invoke`

## Prerequisite checks

### Storage account controls and RBAC

Command:

```powershell
$PSNativeCommandArgumentPassing='Standard'; az storage account show -g rg-ltr-lab -n ltrlab552754sa --subscription a8fbd8e1-fb5a-4411-804a-4ac80929c93c --query "{id:id,allowSharedKeyAccess:allowSharedKeyAccess,publicNetworkAccess:publicNetworkAccess,primaryEndpoints:primaryEndpoints}" -o json; az role assignment list --assignee 6ae8e9fe-6b1a-437f-bf94-83430a391337 --scope /subscriptions/a8fbd8e1-fb5a-4411-804a-4ac80929c93c/resourceGroups/rg-ltr-lab/providers/Microsoft.Storage/storageAccounts/ltrlab552754sa --query "[].{role:roleDefinitionName,scope:scope,principalId:principalId}" -o json
```

Output:

```json
{
  "allowSharedKeyAccess": false,
  "id": "/subscriptions/a8fbd8e1-fb5a-4411-804a-4ac80929c93c/resourceGroups/rg-ltr-lab/providers/Microsoft.Storage/storageAccounts/ltrlab552754sa",
  "primaryEndpoints": {
    "blob": "https://ltrlab552754sa.blob.core.windows.net/",
    "dfs": "https://ltrlab552754sa.dfs.core.windows.net/",
    "file": "https://ltrlab552754sa.file.core.windows.net/",
    "internetEndpoints": null,
    "ipv6Endpoints": null,
    "microsoftEndpoints": null,
    "queue": "https://ltrlab552754sa.queue.core.windows.net/",
    "table": "https://ltrlab552754sa.table.core.windows.net/",
    "web": "https://ltrlab552754sa.z1.web.core.windows.net/"
  },
  "publicNetworkAccess": "Disabled"
}
[
  {
    "principalId": "6ae8e9fe-6b1a-437f-bf94-83430a391337",
    "role": "Storage Blob Data Contributor",
    "scope": "/subscriptions/a8fbd8e1-fb5a-4411-804a-4ac80929c93c/resourceGroups/rg-ltr-lab/providers/Microsoft.Storage/storageAccounts/ltrlab552754sa"
  }
]
```

Finding: `Storage Blob Data Contributor` already existed for principalId `6ae8e9fe-6b1a-437f-bf94-83430a391337` at storage account scope. No RBAC change was needed.

### Workstation data-plane attempt with auth-mode login

Command:

```powershell
$PSNativeCommandArgumentPassing='Standard'; az storage container create --account-name ltrlab552754sa --name mi-backups --auth-mode login --subscription a8fbd8e1-fb5a-4411-804a-4ac80929c93c -o json
```

Output:

```text
ERROR:
The request may be blocked by network rules of storage account. Please check network rule set using 'az storage account show -n accountname --query networkRuleSet'.
If you want to change the default action to apply when no rule matches, please use 'az storage account update'.
```

Finding: `--auth-mode login` was used. The data-plane call was blocked from the workstation because public network access is disabled. Public network access was not enabled.

### Blob private endpoint DNS and TCP from the VNet

Command:

```powershell
$scriptPath = 'C:\Users\jomore\.copilot\session-state\274c5edc-63cc-4553-bbf7-92ba971a0010\files\mi-preflight.ps1'; @'
$ErrorActionPreference = 'Continue'
Write-Output '=== DNS blob endpoint ==='
Resolve-DnsName ltrlab552754sa.blob.core.windows.net | Format-List
Write-Output '=== TCP 443 blob endpoint ==='
Test-NetConnection ltrlab552754sa.blob.core.windows.net -Port 443 | Format-List ComputerName,RemoteAddress,TcpTestSucceeded
Write-Output '=== Tool availability ==='
Get-Command sqlcmd -ErrorAction SilentlyContinue | Select-Object Source,Version | Format-List
Get-Module -ListAvailable SqlServer | Select-Object Name,Version,Path | Format-List
Get-Command azcopy -ErrorAction SilentlyContinue | Select-Object Source,Version | Format-List
Get-Command az -ErrorAction SilentlyContinue | Select-Object Source,Version | Format-List
'@ | Set-Content -Path $scriptPath -Encoding UTF8; $PSNativeCommandArgumentPassing='Standard'; az vm run-command invoke -g rg-ltr-lab -n ltrlab-vm --command-id RunPowerShellScript --scripts "@$scriptPath" --subscription a8fbd8e1-fb5a-4411-804a-4ac80929c93c -o json
```

Output:

```json
{
  "value": [
    {
      "code": "ComponentStatus/StdOut/succeeded",
      "displayStatus": "Provisioning succeeded",
      "level": "Info",
      "message": "=== DNS blob endpoint ===\n\n\nName     : ltrlab552754sa.blob.core.windows.net\nType     : CNAME\nTTL      : 60\nSection  : Answer\nNameHost : ltrlab552754sa.privatelink.blob.core.windows.net\n\n\nName       : ltrlab552754sa.privatelink.blob.core.windows.net\nQueryType  : A\nTTL        : 10\nSection    : Answer\nIP4Address : 10.70.1.5\n\n\n\n=== TCP 443 blob endpoint ===\n\n\nComputerName     : ltrlab552754sa.blob.core.windows.net\nRemoteAddress    : 10.70.1.5\nTcpTestSucceeded : True\n\n\n\n=== Tool availability ===\n\n\nName    : SqlServer\nVersion : 22.4.5.1\nPath    : C:\\Program Files\\WindowsPowerShell\\Modules\\SqlServer\\22.4.5.1\\SqlServer.psd1\n\n\n"
    },
    {
      "code": "ComponentStatus/StdErr/succeeded",
      "displayStatus": "Provisioning succeeded",
      "level": "Info",
      "message": ""
    }
  ]
}
```

Finding: The VM in the same VNet resolves the blob endpoint through `privatelink.blob.core.windows.net` to `10.70.1.5` and TCP 443 succeeds.

### Container creation from the VNet with UAMI OAuth token

Because the workstation data-plane path was blocked, the container was created from inside the VNet using the VM UAMI and Blob REST with a storage OAuth token from IMDS. This did not use shared keys or SAS.

Command:

```powershell
$scriptPath = 'C:\Users\jomore\.copilot\session-state\274c5edc-63cc-4553-bbf7-92ba971a0010\files\mi-container-create.ps1'; @'
$ErrorActionPreference = 'Stop'
$UAMI_CLIENT_ID = '9dab92a8-7084-442e-8617-139fda64b1c9'
$tokenUrl = "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fstorage.azure.com%2F&client_id=$UAMI_CLIENT_ID"
Write-Output '=== Requesting storage token from IMDS ==='
$tokenJson = curl.exe --noproxy "*" -s -H "Metadata: true" $tokenUrl 2>&1
$tokenObj = $tokenJson | ConvertFrom-Json
Write-Output "token_type=$($tokenObj.token_type); expires_on=$($tokenObj.expires_on); resource=$($tokenObj.resource)"
$containerUri = 'https://ltrlab552754sa.blob.core.windows.net/mi-backups?restype=container'
$headers = @{
    Authorization = "Bearer $($tokenObj.access_token)"
    'x-ms-version' = '2023-11-03'
    'x-ms-date' = (Get-Date).ToUniversalTime().ToString('R')
}
Write-Output '=== PUT container mi-backups via Blob REST ==='
try {
    $resp = Invoke-WebRequest -Method Put -Uri $containerUri -Headers $headers -UseBasicParsing
    Write-Output "status=$($resp.StatusCode); description=$($resp.StatusDescription)"
}
catch {
    $ex = $_.Exception
    $statusCode = if ($ex.Response) { [int]$ex.Response.StatusCode } else { 'no-response' }
    $statusDesc = if ($ex.Response) { $ex.Response.StatusDescription } else { $ex.Message }
    Write-Output "status=$statusCode; description=$statusDesc"
    if ($ex.Response) {
        $reader = New-Object System.IO.StreamReader($ex.Response.GetResponseStream())
        $body = $reader.ReadToEnd()
        Write-Output 'body-start'
        Write-Output $body
        Write-Output 'body-end'
        if ($statusCode -ne 409) { throw }
    } else { throw }
}
'@ | Set-Content -Path $scriptPath -Encoding UTF8; $PSNativeCommandArgumentPassing='Standard'; az vm run-command invoke -g rg-ltr-lab -n ltrlab-vm --command-id RunPowerShellScript --scripts "@$scriptPath" --subscription a8fbd8e1-fb5a-4411-804a-4ac80929c93c -o json
```

Output:

```json
{
  "value": [
    {
      "code": "ComponentStatus/StdOut/succeeded",
      "displayStatus": "Provisioning succeeded",
      "level": "Info",
      "message": "=== Requesting storage token from IMDS ===\ntoken_type=Bearer; expires_on=1789121916; resource=https://storage.azure.com/\n=== PUT container mi-backups via Blob REST ===\nstatus=201; description=Created"
    },
    {
      "code": "ComponentStatus/StdErr/succeeded",
      "displayStatus": "Provisioning succeeded",
      "level": "Info",
      "message": ""
    }
  ]
}
```

Finding: `mi-backups` was created successfully from inside the VNet.

## Initial SQL test with service-managed TDE still enabled

Command:

```powershell
$scriptPath = 'C:\Users\jomore\.copilot\session-state\274c5edc-63cc-4553-bbf7-92ba971a0010\files\mi-backup-test.ps1'; @'
$ErrorActionPreference = 'Stop'
$Server = 'ltrlab552754-mi.8a97d4e15d77.database.windows.net'
$UAMI_CLIENT_ID = '9dab92a8-7084-442e-8617-139fda64b1c9'
$CredUrl = 'https://ltrlab552754sa.blob.core.windows.net/mi-backups'
$BackupUrl = 'https://ltrlab552754sa.blob.core.windows.net/mi-backups/mitest.bak'
function Get-DbToken {
    $tokenUrl = "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fdatabase.windows.net%2F&client_id=$UAMI_CLIENT_ID"
    $tokenJson = curl.exe --noproxy "*" -s -H "Metadata: true" $tokenUrl 2>&1
    return (($tokenJson | ConvertFrom-Json).access_token)
}
function Invoke-MiSql {
    param([string]$Database, [string]$Query, [int]$Timeout = 120)
    $token = Get-DbToken
    Invoke-Sqlcmd -ServerInstance $Server -Database $Database -AccessToken $token -Query $Query -TrustServerCertificate -QueryTimeout $Timeout -ErrorAction Stop
}
function Show-SqlError {
    param($ErrorRecord)
    Write-Output "ERROR_TYPE=$($ErrorRecord.Exception.GetType().FullName)"
    Write-Output "ERROR_MESSAGE=$($ErrorRecord.Exception.Message)"
    if ($ErrorRecord.Exception.InnerException) {
        Write-Output "INNER_TYPE=$($ErrorRecord.Exception.InnerException.GetType().FullName)"
        Write-Output "INNER_MESSAGE=$($ErrorRecord.Exception.InnerException.Message)"
    }
    $errors = $ErrorRecord.Exception.Errors
    if ($errors) {
        foreach ($err in $errors) {
            Write-Output "SQL_ERROR Number=$($err.Number); State=$($err.State); Class=$($err.Class); LineNumber=$($err.LineNumber); Procedure=$($err.Procedure); Server=$($err.Server); Message=$($err.Message)"
        }
    }
}
Import-Module SqlServer
Write-Output '=== SQL connectivity ==='
Invoke-MiSql -Database master -Query "SELECT @@SERVERNAME AS ServerName, SYSTEM_USER AS SystemUser, ORIGINAL_LOGIN() AS OriginalLogin, SUSER_SNAME() AS SuserName;" | Format-List
Write-Output '=== Create database mitest ==='
Invoke-MiSql -Database master -Query "IF DB_ID(N'mitest') IS NULL CREATE DATABASE [mitest]; SELECT name, state_desc, create_date FROM sys.databases WHERE name = N'mitest';" -Timeout 300 | Format-List
Write-Output '=== Seed mitest ==='
$seedSql = @"
IF OBJECT_ID(N'dbo.MiBackupPayload', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.MiBackupPayload
    (
        id int IDENTITY(1,1) NOT NULL PRIMARY KEY,
        payload nvarchar(max) NOT NULL,
        random_payload varbinary(8000) NOT NULL,
        created_at datetime2 NOT NULL DEFAULT sysdatetime()
    );
END;
DECLARE @target int = 2500;
WHILE (SELECT COUNT_BIG(*) FROM dbo.MiBackupPayload) < @target
BEGIN
    INSERT dbo.MiBackupPayload(payload, random_payload)
    SELECT REPLICATE(CONVERT(nvarchar(max), N'MI backup managed identity validation row ' + CONVERT(nvarchar(20), v.n)), 80), CRYPT_GEN_RANDOM(4000)
    FROM (VALUES(1),(2),(3),(4),(5),(6),(7),(8),(9),(10),(11),(12),(13),(14),(15),(16),(17),(18),(19),(20),(21),(22),(23),(24),(25),(26),(27),(28),(29),(30),(31),(32),(33),(34),(35),(36),(37),(38),(39),(40),(41),(42),(43),(44),(45),(46),(47),(48),(49),(50)) AS v(n)
    WHERE (SELECT COUNT_BIG(*) FROM dbo.MiBackupPayload) < @target;
END;
SELECT COUNT_BIG(*) AS PayloadRows FROM dbo.MiBackupPayload;
SELECT SUM(reserved_page_count) * 8.0 / 1024.0 AS ReservedMB, SUM(used_page_count) * 8.0 / 1024.0 AS UsedMB FROM sys.dm_db_partition_stats;
"@
Invoke-MiSql -Database mitest -Query $seedSql -Timeout 600 | Format-List
Write-Output '=== Database allocated size before backup ==='
Invoke-MiSql -Database master -Query "SELECT DB_NAME(database_id) AS DbName, SUM(size) * 8.0 / 1024.0 AS AllocatedMB FROM sys.master_files WHERE database_id = DB_ID(N'mitest') GROUP BY database_id;" | Format-List
Write-Output '=== Drop existing test credential if present ==='
Invoke-MiSql -Database master -Query "IF EXISTS (SELECT 1 FROM sys.credentials WHERE name = N'$CredUrl') DROP CREDENTIAL [$CredUrl]; SELECT COUNT(*) AS CredentialCountAfterDrop FROM sys.credentials WHERE name = N'$CredUrl';" | Format-List
Write-Output "=== CREATE CREDENTIAL $CredUrl WITH IDENTITY = 'Managed Identity' ==="
try {
    Invoke-MiSql -Database master -Query "CREATE CREDENTIAL [$CredUrl] WITH IDENTITY = 'Managed Identity'; SELECT name, credential_identity FROM sys.credentials WHERE name = N'$CredUrl';" -Timeout 120 | Format-List
    Write-Output 'CREATE_CREDENTIAL_RESULT=SUCCESS'
}
catch {
    Write-Output 'CREATE_CREDENTIAL_RESULT=FAILED'
    Show-SqlError $_
    Write-Output "=== Retry CREATE CREDENTIAL with IDENTITY = 'MANAGED IDENTITY' ==="
    try {
        Invoke-MiSql -Database master -Query "IF EXISTS (SELECT 1 FROM sys.credentials WHERE name = N'$CredUrl') DROP CREDENTIAL [$CredUrl]; CREATE CREDENTIAL [$CredUrl] WITH IDENTITY = 'MANAGED IDENTITY'; SELECT name, credential_identity FROM sys.credentials WHERE name = N'$CredUrl';" -Timeout 120 | Format-List
        Write-Output 'CREATE_CREDENTIAL_UPPER_RESULT=SUCCESS'
    }
    catch {
        Write-Output 'CREATE_CREDENTIAL_UPPER_RESULT=FAILED'
        Show-SqlError $_
        throw
    }
}
Write-Output "=== BACKUP DATABASE mitest TO URL $BackupUrl ==="
try {
    Invoke-MiSql -Database master -Query "BACKUP DATABASE [mitest] TO URL = '$BackupUrl' WITH COPY_ONLY, COMPRESSION, STATS = 10;" -Timeout 1800 | Format-List
    Write-Output 'BACKUP_RESULT=SUCCESS'
}
catch {
    Write-Output 'BACKUP_RESULT=FAILED'
    Show-SqlError $_
    throw
}
Write-Output '=== Credential after backup ==='
Invoke-MiSql -Database master -Query "SELECT name, credential_identity FROM sys.credentials WHERE name = N'$CredUrl';" | Format-List
'@ | Set-Content -Path $scriptPath -Encoding UTF8; $PSNativeCommandArgumentPassing='Standard'; az vm run-command invoke -g rg-ltr-lab -n ltrlab-vm --command-id RunPowerShellScript --scripts "@$scriptPath" --subscription a8fbd8e1-fb5a-4411-804a-4ac80929c93c -o json
```

Output:

```json
{
  "value": [
    {
      "code": "ComponentStatus/StdOut/succeeded",
      "displayStatus": "Provisioning succeeded",
      "level": "Info",
      "message": "=== SQL connectivity ===\n\n\nServerName    : ltrlab552754-mi.8a97d4e15d77.database.windows.net\nSystemUser    : 9dab92a8-7084-442e-8617-139fda64b1c9@5ad00b69-0386-4c74-8adc-ac7a28649f34\nOriginalLogin : 9dab92a8-7084-442e-8617-139fda64b1c9@5ad00b69-0386-4c74-8adc-ac7a28649f34\nSuserName     : 9dab92a8-7084-442e-8617-139fda64b1c9@5ad00b69-0386-4c74-8adc-ac7a28649f34\n\n\n\n=== Create database mitest ===\n\n\nname        : mitest\nstate_desc  : ONLINE\ncreate_date : 9/10/2026 10:19:42 AM\n\n\n\n=== Seed mitest ===\n\n\nPayloadRows : 2500\n\nReservedMB : 43.1171875\nUsedMB     : 42.0312500\n\n\n\n=== Database allocated size before backup ===\n\n\nDbName      : mitest\nAllocatedMB : 104.0000000\n\n\n\n=== Drop existing test credential if present ===\n\n\nCredentialCountAfterDrop : 0\n\n\n\n=== CREATE CREDENTIAL https://ltrlab552754sa.blob.core.windows.net/mi-backups WITH IDENTITY = 'Managed Identity' ===\n\n\nname                : https://ltrlab552754sa.blob.core.windows.net/mi-backups\ncredential_identity : Managed Identity\n\n\n\nCREATE_CREDENTIAL_RESULT=SUCCESS\n=== BACKUP DATABASE mitest TO URL https://ltrlab552754sa.blob.core.windows.net/mi-backups/mitest.bak ===\nBACKUP_RESULT=FAILED\nERROR_TYPE=Microsoft.SqlServer.Management.PowerShell.SqlPowerShellSqlExecutionException\nERROR_MESSAGE=The backup operation for a database with service-managed transparent data encryption is not supported on SQL Database Managed Instance.\nBACKUP DATABASE is terminating abnormally. \n Msg 41922, Level 16, State 1, Procedure , Line 1.\nINNER_TYPE=Microsoft.Data.SqlClient.SqlException\nINNER_MESSAGE=The backup operation for a database with service-managed transparent data encryption is not supported on SQL Database Managed Instance.\nBACKUP DATABASE is terminating abnormally."
    },
    {
      "code": "ComponentStatus/StdErr/succeeded",
      "displayStatus": "Provisioning succeeded",
      "level": "Info",
      "message": "Invoke-Sqlcmd : The backup operation for a database with service-managed transparent data encryption is not supported \non SQL Database Managed Instance.\nBACKUP DATABASE is terminating abnormally. \n Msg 41922, Level 16, State 1, Procedure , Line 1.\nAt C:\\Packages\\Plugins\\Microsoft.CPlat.Core.RunCommandWindows\\1.1.22\\Downloads\\script18.ps1:14 char:5\n+     Invoke-Sqlcmd -ServerInstance $Server -Database $Database -Access ...\n+     ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n    + CategoryInfo          : InvalidOperation: (:) [Invoke-Sqlcmd], SqlPowerShellSqlExecutionException\n    + FullyQualifiedErrorId : SqlError,Microsoft.SqlServer.Management.PowerShell.GetScriptCommand\n "
    }
  ]
}
```

Interpretation: This is not a negative verdict on Managed Identity credential syntax or blob authorization. It confirms the separate service-managed TDE caveat. The backup failed before URL access.

## Disabling service-managed TDE and first retry

Command:

```powershell
$scriptPath = 'C:\Users\jomore\.copilot\session-state\274c5edc-63cc-4553-bbf7-92ba971a0010\files\mi-backup-retry-after-tdeoff.ps1'; @'
$ErrorActionPreference = 'Stop'
$Server = 'ltrlab552754-mi.8a97d4e15d77.database.windows.net'
$UAMI_CLIENT_ID = '9dab92a8-7084-442e-8617-139fda64b1c9'
$CredUrl = 'https://ltrlab552754sa.blob.core.windows.net/mi-backups'
$BackupUrl = 'https://ltrlab552754sa.blob.core.windows.net/mi-backups/mitest.bak'
function Get-DbToken {
    $tokenUrl = "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fdatabase.windows.net%2F&client_id=$UAMI_CLIENT_ID"
    $tokenJson = curl.exe --noproxy "*" -s -H "Metadata: true" $tokenUrl 2>&1
    return (($tokenJson | ConvertFrom-Json).access_token)
}
function Invoke-MiSql {
    param([string]$Database, [string]$Query, [int]$Timeout = 120)
    $token = Get-DbToken
    Invoke-Sqlcmd -ServerInstance $Server -Database $Database -AccessToken $token -Query $Query -TrustServerCertificate -QueryTimeout $Timeout -ErrorAction Stop
}
function Show-SqlError {
    param($ErrorRecord)
    Write-Output "ERROR_TYPE=$($ErrorRecord.Exception.GetType().FullName)"
    Write-Output "ERROR_MESSAGE=$($ErrorRecord.Exception.Message)"
    if ($ErrorRecord.Exception.InnerException) {
        Write-Output "INNER_TYPE=$($ErrorRecord.Exception.InnerException.GetType().FullName)"
        Write-Output "INNER_MESSAGE=$($ErrorRecord.Exception.InnerException.Message)"
    }
    $errors = $ErrorRecord.Exception.Errors
    if ($errors) {
        foreach ($err in $errors) {
            Write-Output "SQL_ERROR Number=$($err.Number); State=$($err.State); Class=$($err.Class); LineNumber=$($err.LineNumber); Procedure=$($err.Procedure); Server=$($err.Server); Message=$($err.Message)"
        }
    }
}
function Show-TdeState {
    $q = "SELECT DB_NAME(database_id) AS db, encryption_state, percent_complete FROM sys.dm_database_encryption_keys WHERE database_id = DB_ID(N'mitest');"
    $rows = @(Invoke-MiSql -Database master -Query $q -Timeout 120)
    if ($rows.Count -eq 0) {
        Write-Output 'TDE_STATE=NO_DMV_ROW'
        return $true
    }
    foreach ($row in $rows) {
        Write-Output ("TDE_STATE db={0}; encryption_state={1}; percent_complete={2}" -f $row.db, $row.encryption_state, $row.percent_complete)
    }
    return ($rows | Where-Object { $_.encryption_state -ne 1 }).Count -eq 0
}
Import-Module SqlServer
Write-Output '=== Confirm documented service-managed TDE caveat source state ==='
Invoke-MiSql -Database master -Query "SELECT DB_NAME(database_id) AS db, encryption_state, percent_complete FROM sys.dm_database_encryption_keys WHERE database_id = DB_ID(N'mitest');" | Format-List
Write-Output '=== ALTER DATABASE mitest SET ENCRYPTION OFF ==='
try {
    Invoke-MiSql -Database master -Query "ALTER DATABASE [mitest] SET ENCRYPTION OFF;" -Timeout 300 | Format-List
    Write-Output 'ALTER_TDE_OFF_RESULT=SUCCESS'
}
catch {
    Write-Output 'ALTER_TDE_OFF_RESULT=FAILED'
    Show-SqlError $_
    throw
}
Write-Output '=== Poll TDE state until unencrypted or DMV row removed ==='
$ready = $false
for ($i = 1; $i -le 60; $i++) {
    Write-Output "POLL_ATTEMPT=$i"
    $ready = Show-TdeState
    if ($ready) { break }
    Start-Sleep -Seconds 5
}
if (-not $ready) { throw 'Timed out waiting for mitest TDE decryption to complete.' }
Write-Output 'TDE_READY_FOR_BACKUP=True'
Write-Output '=== Confirm credential before backup retry ==='
Invoke-MiSql -Database master -Query "SELECT name, credential_identity FROM sys.credentials WHERE name = N'$CredUrl';" | Format-List
Write-Output "=== BACKUP DATABASE mitest TO URL $BackupUrl after TDE off ==="
try {
    Invoke-MiSql -Database master -Query "BACKUP DATABASE [mitest] TO URL = '$BackupUrl' WITH COPY_ONLY, COMPRESSION, STATS = 10;" -Timeout 1800 | Format-List
    Write-Output 'BACKUP_RESULT=SUCCESS'
}
catch {
    Write-Output 'BACKUP_RESULT=FAILED'
    Show-SqlError $_
    throw
}
'@ | Set-Content -Path $scriptPath -Encoding UTF8; $PSNativeCommandArgumentPassing='Standard'; az vm run-command invoke -g rg-ltr-lab -n ltrlab-vm --command-id RunPowerShellScript --scripts "@$scriptPath" --subscription a8fbd8e1-fb5a-4411-804a-4ac80929c93c -o json
```

Output:

```json
{
  "value": [
    {
      "code": "ComponentStatus/StdOut/succeeded",
      "displayStatus": "Provisioning succeeded",
      "level": "Info",
      "message": "=== Confirm documented service-managed TDE caveat source state ===\n\n\ndb               : mitest\nencryption_state : 3\npercent_complete : 0\n\n\n\n=== ALTER DATABASE mitest SET ENCRYPTION OFF ===\nALTER_TDE_OFF_RESULT=SUCCESS\n=== Poll TDE state until unencrypted or DMV row removed ===\nPOLL_ATTEMPT=1\nTDE_READY_FOR_BACKUP=True\n=== Confirm credential before backup retry ===\n\n\nname                : https://ltrlab552754sa.blob.core.windows.net/mi-backups\ncredential_identity : Managed Identity\n\n\n\n=== BACKUP DATABASE mitest TO URL https://ltrlab552754sa.blob.core.windows.net/mi-backups/mitest.bak after TDE off ===\nBACKUP_RESULT=FAILED\nERROR_TYPE=Microsoft.SqlServer.Management.PowerShell.SqlPowerShellSqlExecutionException\nERROR_MESSAGE=BACKUP WITH COPY_ONLY cannot be performed since database encryption key for the database 'mitest' still exists. Retry command after you drop database encryption key.\nBACKUP DATABASE is terminating abnormally. \n Msg 41938, Level 16, State 1, Procedure , Line 1.\nINNER_TYPE=Microsoft.Data.SqlClient.SqlException\nINNER_MESSAGE=BACKUP WITH COPY_ONLY cannot be performed since database encryption key for the database 'mitest' still exists. Retry command after you drop database encryption key.\nBACKUP DATABASE is terminating abnormally."
    },
    {
      "code": "ComponentStatus/StdErr/succeeded",
      "displayStatus": "Provisioning succeeded",
      "level": "Info",
      "message": "Invoke-Sqlcmd : BACKUP WITH COPY_ONLY cannot be performed since database encryption key for the database 'mitest' \nstill exists. Retry command after you drop database encryption key.\nBACKUP DATABASE is terminating abnormally. \n Msg 41938, Level 16, State 1, Procedure , Line 1.\nAt C:\\Packages\\Plugins\\Microsoft.CPlat.Core.RunCommandWindows\\1.1.22\\Downloads\\script19.ps1:14 char:5\n+     Invoke-Sqlcmd -ServerInstance $Server -Database $Database -Access ...\n+     ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n    + CategoryInfo          : InvalidOperation: (:) [Invoke-Sqlcmd], SqlPowerShellSqlExecutionException\n    + FullyQualifiedErrorId : SqlError,Microsoft.SqlServer.Management.PowerShell.GetScriptCommand\n "
    }
  ]
}
```

Interpretation: `ALTER DATABASE [mitest] SET ENCRYPTION OFF` succeeded and the DMV reached `encryption_state=1`, but Managed Instance still blocked `BACKUP WITH COPY_ONLY` until `DROP DATABASE ENCRYPTION KEY` was run.

## Actual end-to-end Managed Identity backup test after TDE remediation

Command:

```powershell
$scriptPath = 'C:\Users\jomore\.copilot\session-state\274c5edc-63cc-4553-bbf7-92ba971a0010\files\mi-backup-retry-after-dropdek.ps1'; @'
$ErrorActionPreference = 'Stop'
$Server = 'ltrlab552754-mi.8a97d4e15d77.database.windows.net'
$UAMI_CLIENT_ID = '9dab92a8-7084-442e-8617-139fda64b1c9'
$CredUrl = 'https://ltrlab552754sa.blob.core.windows.net/mi-backups'
$BackupUrl = 'https://ltrlab552754sa.blob.core.windows.net/mi-backups/mitest.bak'
function Get-DbToken {
    $tokenUrl = "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fdatabase.windows.net%2F&client_id=$UAMI_CLIENT_ID"
    $tokenJson = curl.exe --noproxy "*" -s -H "Metadata: true" $tokenUrl 2>&1
    return (($tokenJson | ConvertFrom-Json).access_token)
}
function Invoke-MiSql {
    param([string]$Database, [string]$Query, [int]$Timeout = 120)
    $token = Get-DbToken
    Invoke-Sqlcmd -ServerInstance $Server -Database $Database -AccessToken $token -Query $Query -TrustServerCertificate -QueryTimeout $Timeout -ErrorAction Stop -Verbose 4>&1
}
function Show-SqlError {
    param($ErrorRecord)
    Write-Output "ERROR_TYPE=$($ErrorRecord.Exception.GetType().FullName)"
    Write-Output "ERROR_MESSAGE=$($ErrorRecord.Exception.Message)"
    if ($ErrorRecord.Exception.InnerException) {
        Write-Output "INNER_TYPE=$($ErrorRecord.Exception.InnerException.GetType().FullName)"
        Write-Output "INNER_MESSAGE=$($ErrorRecord.Exception.InnerException.Message)"
    }
    $errors = $ErrorRecord.Exception.Errors
    if ($errors) {
        foreach ($err in $errors) {
            Write-Output "SQL_ERROR Number=$($err.Number); State=$($err.State); Class=$($err.Class); LineNumber=$($err.LineNumber); Procedure=$($err.Procedure); Server=$($err.Server); Message=$($err.Message)"
        }
    }
}
Import-Module SqlServer
Write-Output '=== TDE DMV before DROP DATABASE ENCRYPTION KEY ==='
Invoke-MiSql -Database master -Query "SELECT DB_NAME(database_id) AS db, encryption_state, percent_complete FROM sys.dm_database_encryption_keys WHERE database_id = DB_ID(N'mitest');" | Format-List
Write-Output '=== DROP DATABASE ENCRYPTION KEY in mitest ==='
try {
    Invoke-MiSql -Database mitest -Query "DROP DATABASE ENCRYPTION KEY;" -Timeout 300 | Format-List
    Write-Output 'DROP_DEK_RESULT=SUCCESS'
}
catch {
    Write-Output 'DROP_DEK_RESULT=FAILED'
    Show-SqlError $_
    throw
}
Write-Output '=== TDE DMV after DROP DATABASE ENCRYPTION KEY ==='
Invoke-MiSql -Database master -Query "SELECT DB_NAME(database_id) AS db, encryption_state, percent_complete FROM sys.dm_database_encryption_keys WHERE database_id = DB_ID(N'mitest');" | Format-List
Write-Output '=== Confirm credential before backup retry ==='
Invoke-MiSql -Database master -Query "SELECT name, credential_identity FROM sys.credentials WHERE name = N'$CredUrl';" | Format-List
Write-Output "=== BACKUP DATABASE mitest TO URL $BackupUrl after DROP DEK ==="
try {
    Invoke-MiSql -Database master -Query "BACKUP DATABASE [mitest] TO URL = '$BackupUrl' WITH COPY_ONLY, COMPRESSION, STATS = 10;" -Timeout 1800 | Format-List
    Write-Output 'BACKUP_RESULT=SUCCESS'
}
catch {
    Write-Output 'BACKUP_RESULT=FAILED'
    Show-SqlError $_
    throw
}
Write-Output '=== RESTORE HEADERONLY ==='
try {
    Invoke-MiSql -Database master -Query "RESTORE HEADERONLY FROM URL = '$BackupUrl';" -Timeout 300 | Format-List
    Write-Output 'RESTORE_HEADERONLY_RESULT=SUCCESS'
}
catch {
    Write-Output 'RESTORE_HEADERONLY_RESULT=FAILED'
    Show-SqlError $_
    throw
}
Write-Output '=== RESTORE VERIFYONLY ==='
try {
    Invoke-MiSql -Database master -Query "RESTORE VERIFYONLY FROM URL = '$BackupUrl';" -Timeout 600 | Format-List
    Write-Output 'RESTORE_VERIFYONLY_RESULT=SUCCESS'
}
catch {
    Write-Output 'RESTORE_VERIFYONLY_RESULT=FAILED'
    Show-SqlError $_
    throw
}
Write-Output '=== Database allocated size after backup ==='
Invoke-MiSql -Database master -Query "SELECT DB_NAME(database_id) AS DbName, SUM(size) * 8.0 / 1024.0 AS AllocatedMB FROM sys.master_files WHERE database_id = DB_ID(N'mitest') GROUP BY database_id;" | Format-List
'@ | Set-Content -Path $scriptPath -Encoding UTF8; $PSNativeCommandArgumentPassing='Standard'; az vm run-command invoke -g rg-ltr-lab -n ltrlab-vm --command-id RunPowerShellScript --scripts "@$scriptPath" --subscription a8fbd8e1-fb5a-4411-804a-4ac80929c93c -o json
```

Output:

```json
{
  "value": [
    {
      "code": "ComponentStatus/StdOut/succeeded",
      "displayStatus": "Provisioning succeeded",
      "level": "Info",
      "message": "=== TDE DMV before DROP DATABASE ENCRYPTION KEY ===\n\n\ndb               : mitest\nencryption_state : 1\npercent_complete : 0\n\n\n\n=== DROP DATABASE ENCRYPTION KEY in mitest ===\nDROP_DEK_RESULT=SUCCESS\n=== TDE DMV after DROP DATABASE ENCRYPTION KEY ===\n=== Confirm credential before backup retry ===\n\n\nname                : https://ltrlab552754sa.blob.core.windows.net/mi-backups\ncredential_identity : Managed Identity\n\n\n\n=== BACKUP DATABASE mitest TO URL https://ltrlab552754sa.blob.core.windows.net/mi-backups/mitest.bak after DROP DEK ===\nVERBOSE: 11 percent processed.\nVERBOSE: 21 percent processed.\nVERBOSE: 30 percent processed.\nVERBOSE: 40 percent processed.\nVERBOSE: 50 percent processed.\nVERBOSE: 61 percent processed.\nVERBOSE: 71 percent processed.\nVERBOSE: 80 percent processed.\nVERBOSE: 90 percent processed.\nVERBOSE: Processed 7680 pages for database 'mitest', file 'data_0' on file 1.\nVERBOSE: Processed 0 pages for database 'mitest', file 'XTP' on file 1.\nVERBOSE: Processed 2 pages for database 'mitest', file 'log' on file 1.\nVERBOSE: 100 percent processed.\nVERBOSE: BACKUP DATABASE successfully processed 7682 pages in 0.750 seconds (80.015 MB/sec).\nBACKUP_RESULT=SUCCESS\n=== RESTORE HEADERONLY ===\n\n\nBackupName             : \nBackupDescription      : \nBackupType             : 1\nExpirationDate         : \nCompressed             : 1\nPosition               : 1\nDeviceType             : 9\nUserName               : 9dab92a8-7084-442e-8617-139fda64b1c9@5ad00b69-0386-4c74-8adc-ac7a28649f34\nServerName             : ltrlab552754-mi.8a97d4e15d77.database.windows.net\nDatabaseName           : mitest\nDatabaseVersion        : 957\nDatabaseCreationDate   : 9/10/2026 10:19:42 AM\nBackupSize             : 66459648\nFirstLSN               : 53000000018400001\nLastLSN                : 53000000020800001\nCheckpointLSN          : 53000000018400001\nDatabaseBackupLSN      : 52000000885600001\nBackupStartDate        : 9/10/2026 10:25:22 AM\nBackupFinishDate       : 9/10/2026 10:25:23 AM\nSortOrder              : 52\nCodePage               : 0\nUnicodeLocaleId        : 1033\nUnicodeComparisonStyle : 196609\nCompatibilityLevel     : 160\nSoftwareVendorId       : 4608\nSoftwareVersionMajor   : 16\nSoftwareVersionMinor   : 0\nSoftwareVersionBuild   : 4255\nMachineName            : CHNTWUWJ5HZKUYM\nFlags                  : 1536\nBindingID              : 6d604fc0-64f8-4e53-9311-a3ce6f15e8ab\nRecoveryForkID         : b564ead8-1c59-4c1b-acf4-8ebc887a0eb1\nCollation              : SQL_Latin1_General_CP1_CI_AS\nFamilyGUID             : b564ead8-1c59-4c1b-acf4-8ebc887a0eb1\nHasBulkLoggedData      : False\nIsSnapshot             : False\nIsReadOnly             : False\nIsSingleUser           : False\nHasBackupChecksums     : False\nIsDamaged              : False\nBeginsLogChain         : False\nHasIncompleteMetaData  : False\nIsForceOffline         : False\nIsCopyOnly             : True\nFirstRecoveryForkID    : b564ead8-1c59-4c1b-acf4-8ebc887a0eb1\nForkPointLSN           : \nRecoveryModel          : FULL\nDifferentialBaseLSN    : \nDifferentialBaseGUID   : \nBackupTypeDescription  : Database\nBackupSetGUID          : 0e4f4424-f5bb-4b61-b5a2-c6a8abf7c785\nCompressedBackupSize   : 11624952\nContainment            : 0\nKeyAlgorithm           : \nEncryptorThumbprint    : \nEncryptorType          : \nLastValidRestoreTime   : \nTimeZone               : 4\nCompressionAlgorithm   : MS_XPRESS\n\n\n\nRESTORE_HEADERONLY_RESULT=SUCCESS\n=== RESTORE VERIFYONLY ===\nVERBOSE: The backup set on file 1 is valid.\nRESTORE_VERIFYONLY_RESULT=SUCCESS\n=== Database allocated size after backup ===\n\n\nDbName      : mitest\nAllocatedMB : 104.0000000\n\n\n"
    },
    {
      "code": "ComponentStatus/StdErr/succeeded",
      "displayStatus": "Provisioning succeeded",
      "level": "Info",
      "message": ""
    }
  ]
}
```

Finding: This is the actual Managed Identity to blob backup result. It succeeded. The backup was copy-only, compressed, stored at URL, readable by `RESTORE HEADERONLY`, and valid by `RESTORE VERIFYONLY`.

## Blob existence and size

### Requested workstation `az storage blob list --auth-mode login`

Command:

```powershell
$PSNativeCommandArgumentPassing='Standard'; az storage blob list --account-name ltrlab552754sa --container-name mi-backups --auth-mode login --subscription a8fbd8e1-fb5a-4411-804a-4ac80929c93c --query "[?name=='mitest.bak'].{name:name,size:properties.contentLength,lastModified:properties.lastModified,contentType:properties.contentSettings.contentType}" -o json
```

Output:

```text
ERROR:
The request may be blocked by network rules of storage account. Please check network rule set using 'az storage account show -n accountname --query networkRuleSet'.
If you want to change the default action to apply when no rule matches, please use 'az storage account update'.
```

Interpretation: The requested command used `--auth-mode login`, but workstation storage data-plane listing is blocked because public network access is disabled. This does not contradict the backup result.

### VNet Blob REST confirmation with UAMI OAuth token

Command:

```powershell
$scriptPath = 'C:\Users\jomore\.copilot\session-state\274c5edc-63cc-4553-bbf7-92ba971a0010\files\mi-blob-verify.ps1'; @'
$ErrorActionPreference = 'Stop'
$UAMI_CLIENT_ID = '9dab92a8-7084-442e-8617-139fda64b1c9'
$tokenUrl = "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fstorage.azure.com%2F&client_id=$UAMI_CLIENT_ID"
Write-Output '=== Requesting storage token from IMDS ==='
$tokenJson = curl.exe --noproxy "*" -s -H "Metadata: true" $tokenUrl 2>&1
$tokenObj = $tokenJson | ConvertFrom-Json
Write-Output "token_type=$($tokenObj.token_type); expires_on=$($tokenObj.expires_on); resource=$($tokenObj.resource)"
$headers = @{
    Authorization = "Bearer $($tokenObj.access_token)"
    'x-ms-version' = '2023-11-03'
    'x-ms-date' = (Get-Date).ToUniversalTime().ToString('R')
}
Write-Output '=== HEAD blob mitest.bak via Blob REST ==='
$blobUri = 'https://ltrlab552754sa.blob.core.windows.net/mi-backups/mitest.bak'
$head = Invoke-WebRequest -Method Head -Uri $blobUri -Headers $headers -UseBasicParsing
Write-Output "status=$($head.StatusCode); description=$($head.StatusDescription)"
Write-Output "content-length=$($head.Headers['Content-Length'])"
Write-Output "last-modified=$($head.Headers['Last-Modified'])"
Write-Output "etag=$($head.Headers['ETag'])"
Write-Output "blob-type=$($head.Headers['x-ms-blob-type'])"
Write-Output '=== LIST container prefix mitest.bak via Blob REST ==='
$listUri = 'https://ltrlab552754sa.blob.core.windows.net/mi-backups?restype=container&comp=list&prefix=mitest.bak'
$list = Invoke-WebRequest -Method Get -Uri $listUri -Headers $headers -UseBasicParsing
Write-Output "status=$($list.StatusCode); description=$($list.StatusDescription)"
Write-Output 'body-start'
Write-Output $list.Content
Write-Output 'body-end'
'@ | Set-Content -Path $scriptPath -Encoding UTF8; $PSNativeCommandArgumentPassing='Standard'; az vm run-command invoke -g rg-ltr-lab -n ltrlab-vm --command-id RunPowerShellScript --scripts "@$scriptPath" --subscription a8fbd8e1-fb5a-4411-804a-4ac80929c93c -o json
```

Output:

```json
{
  "value": [
    {
      "code": "ComponentStatus/StdOut/succeeded",
      "displayStatus": "Provisioning succeeded",
      "level": "Info",
      "message": "=== Requesting storage token from IMDS ===\ntoken_type=Bearer; expires_on=1789121916; resource=https://storage.azure.com/\n=== HEAD blob mitest.bak via Blob REST ===\nstatus=200; description=OK\ncontent-length=11927552\nlast-modified=Thu, 10 Sep 2026 10:25:23 GMT\netag=\"0x8DF0F25D2E5AF81\"\nblob-type=BlockBlob\n=== LIST container prefix mitest.bak via Blob REST ===\nstatus=200; description=OK\nbody-start\n﻿<?xml version=\"1.0\" encoding=\"utf-8\"?><EnumerationResults ServiceEndpoint=\"https://ltrlab552754sa.blob.core.windows.net/\" ContainerName=\"mi-backups\"><Prefix>mitest.bak</Prefix><Blobs><Blob><Name>mitest.bak</Name><Properties><Creation-Time>Thu, 10 Sep 2026 10:25:22 GMT</Creation-Time><Last-Modified>Thu, 10 Sep 2026 10:25:23 GMT</Last-Modified><Etag>0x8DF0F25D2E5AF81</Etag><Content-Length>11927552</Content-Length><Content-Type>application/octet-stream</Content-Type><Content-Encoding /><Content-Language /><Content-CRC64 /><Content-MD5 /><Cache-Control /><Content-Disposition /><BlobType>BlockBlob</BlobType><AccessTier>Hot</AccessTier><AccessTierInferred>true</AccessTierInferred><LeaseStatus>unlocked</LeaseStatus><LeaseState>available</LeaseState><ServerEncrypted>true</ServerEncrypted></Properties><OrMetadata /></Blob></Blobs><NextMarker /></EnumerationResults>\nbody-end"
    },
    {
      "code": "ComponentStatus/StdErr/succeeded",
      "displayStatus": "Provisioning succeeded",
      "level": "Info",
      "message": ""
    }
  ]
}
```

Finding: Blob `mi-backups/mitest.bak` exists and is a `BlockBlob` with `Content-Length=11927552` bytes.

## Compression ratio

- Database allocated size: 104.0000000 MB.
- `RESTORE HEADERONLY` `BackupSize`: 66,459,648 bytes, 63.38 MiB.
- `RESTORE HEADERONLY` `CompressedBackupSize`: 11,624,952 bytes, 11.09 MiB.
- Blob `Content-Length`: 11,927,552 bytes, 11.38 MiB.
- Ratio using allocated database size vs blob size: 104.00 MiB / 11.38 MiB = 9.14x.
- Ratio using `BackupSize` vs `CompressedBackupSize`: 66,459,648 / 11,624,952 = 5.72x.
- Compression was enabled and observed: `Compressed : 1`, `CompressionAlgorithm : MS_XPRESS`.

## Final interpretation

The Managed Identity credential syntax is supported on Managed Instance, and the end-to-end backup to a private, shared-key-disabled storage account is supported when the MI database is eligible for backup. The observed blocker was not Managed Identity auth. The blockers were service-managed TDE Msg 41922, then residual database encryption key Msg 41938 until `DROP DATABASE ENCRYPTION KEY` was run.
