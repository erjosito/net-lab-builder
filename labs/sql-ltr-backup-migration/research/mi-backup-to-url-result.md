# Managed Instance BACKUP TO URL with Managed Identity credential

Date: 2026-09-10T12:16:31+02:00

VERDICT: NOT SUPPORTED for the current lab Managed Instance configuration. The Managed Instance accepted `CREATE CREDENTIAL ... WITH IDENTITY = 'Managed Identity'`, but `BACKUP DATABASE ... TO URL` failed before blob authorization or network access with SQL error 41922: `The backup operation for a database with service-managed transparent data encryption is not supported on SQL Database Managed Instance.`

## Environment tested

- Managed Instance: `ltrlab552754-mi.8a97d4e15d77.database.windows.net`
- Resource group: `rg-ltr-lab`
- Subscription: `a8fbd8e1-fb5a-4411-804a-4ac80929c93c`
- MI identity: User-assigned managed identity `ltrlab552754-umi`
- UAMI clientId: `9dab92a8-7084-442e-8617-139fda64b1c9`
- UAMI principalId: `6ae8e9fe-6b1a-437f-bf94-83430a391337`
- Storage account: `ltrlab552754sa`
- Container: `mi-backups`
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

Finding: The VM in the same VNet resolves the blob endpoint through `privatelink.blob.core.windows.net` to `10.70.1.5` and TCP 443 succeeds. The actual MI-side network path was not observed because BACKUP failed before URL access.

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

## Managed Instance SQL test

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

## Interpretation

Observed:

- Entra-only SQL connectivity to the MI worked using the VM UAMI token from IMDS.
- Test database `mitest` was created and seeded.
- Seeded data occupied 43.1171875 MB reserved and 42.0312500 MB used.
- Database allocated size before backup was 104.0000000 MB.
- `CREATE CREDENTIAL [https://ltrlab552754sa.blob.core.windows.net/mi-backups] WITH IDENTITY = 'Managed Identity'` succeeded.
- `BACKUP DATABASE [mitest] TO URL = 'https://ltrlab552754sa.blob.core.windows.net/mi-backups/mitest.bak' WITH COPY_ONLY, COMPRESSION, STATS = 10` failed with Msg 41922.

Not observed:

- No blob was produced.
- No backup size or compression ratio was measured.
- No blob authorization result was reached.
- No MI-to-blob network result was reached.
- Casing variants such as `IDENTITY = 'MANAGED IDENTITY'` were not tested because the requested identity string was accepted.
- System-assigned MI behavior was not tested because the credential was accepted with the user-assigned identity configuration and the hard blocker was service-managed TDE.

Conclusion: the current MI recommendation cannot rely on native `BACKUP TO URL` in this lab state. The Managed Identity credential syntax is supported enough to create the credential, but the backup itself is blocked on Managed Instance when the database uses service-managed transparent data encryption.
