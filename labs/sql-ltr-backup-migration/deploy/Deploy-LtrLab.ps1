<#
.SYNOPSIS
    Provisions the single-subscription LTR drain lab and seeds it with databases of
    deliberately different sizes and data shapes.

.DESCRIPTION
    The lab exists to calibrate and validate src/powershell/sql-ltr-export/.

    WHY DIFFERENT SIZES: the cost model expresses drain time as

        minutes = FixedOverhead + (PerGb * SizeGb)

    A single database size cannot separate those two terms. Three sizes spanning an order
    of magnitude let you least-squares fit both, and confirm the relationship is actually
    linear rather than merely assumed to be.

    WHY DIFFERENT DATA SHAPES: the model also assumes BACPAC compresses ~4x and native
    backup ~3x. Real ratios depend entirely on the data. Two same-sized probe databases,
    one highly compressible and one incompressible, bracket the true range instead of
    guessing a single number.

    PHASE 1 of the lab. LTR backups cannot be created on demand, so this script seeds and
    then stops. Poll with Watch-LtrLabBackups.ps1 until backups appear (up to 7 days),
    then run the drain scripts.

.EXAMPLE
    .\Deploy-LtrLab.ps1 -ResourceGroup rg-ltr-lab -Location eastus `
        -AdminUser ltrlab -AdminPassword (Read-Host -AsSecureString)
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string] $ResourceGroup,
    [Parameter(Mandatory)][string] $Location,
    [Parameter(Mandatory)][string] $AdminUser,

    # Only used when SQL authentication is permitted. Under -EntraOnlyAuth no SQL login
    # exists at all, so this is deliberately not mandatory.
    [securestring] $AdminPassword,

    # Many tenants deny Microsoft.Sql/servers that permit SQL authentication
    # (policy AzureSQL_WithoutAzureADOnlyAuthentication_Deny, "SFI-ID4.2.2 SQL DB -
    # Safe Secrets Standard"). In that case there is no username-and-password path at
    # all, and BACPAC export must authenticate with a user-assigned managed identity
    # attached at the logical server level. Defaults to the signed-in user as admin.
    [switch] $EntraOnlyAuth,
    [string] $EntraAdminName,
    [string] $EntraAdminSid,
    [string] $EntraAdminType = 'User',

    [string] $Prefix = "ltrlab$(Get-Random -Minimum 1000 -Maximum 9999)",

    # Sizes spanning an order of magnitude. Keep the largest modest: the lab validates
    # mechanics and calibrates slope, it is not a throughput benchmark.
    [int[]]  $CalibrationSizesGb = @(1, 5, 20),

    # Both probes are the same size so the only variable is compressibility.
    [int]    $CompressionProbeGb = 5,

    # Serverless with aggressive auto-pause: the databases must merely EXIST during the
    # multi-day wait for LTR backups to appear, so paying for idle compute is pure waste.
    [string] $DbSku            = 'GP_S_Gen5_1',
    [int]    $AutoPauseMinutes = 60,

    # MI provisioning takes 4-6 hours and dominates lab cost. Opt in explicitly.
    [switch] $IncludeManagedInstance,
    [string] $MiSubnetId,

    [switch] $SkipDataLoad
)

$ErrorActionPreference = 'Stop'

function Invoke-Az {
    param([string[]] $Arguments)
    $out = & az @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "az $($Arguments -join ' ') failed:`n$out" }
    return $out
}

$server         = "$Prefix-sql"
$storageAccount = ($Prefix -replace '[^a-z0-9]', '') + 'sa'
$container      = 'ltr-artifacts'
$identityName   = "$Prefix-umi"
$plainPassword  = if ($AdminPassword) { [System.Net.NetworkCredential]::new('', $AdminPassword).Password } else { $null }

if ($EntraOnlyAuth) {
    if (-not $EntraAdminName -or -not $EntraAdminSid) {
        Write-Host 'Resolving signed-in user as the Entra SQL admin ...' -ForegroundColor DarkGray
        $me = az ad signed-in-user show --query '{upn:userPrincipalName, id:id}' -o json | ConvertFrom-Json
        if (-not $me) { throw 'Could not resolve the signed-in user. Pass -EntraAdminName and -EntraAdminSid explicitly.' }
        if (-not $EntraAdminName) { $EntraAdminName = $me.upn }
        if (-not $EntraAdminSid)  { $EntraAdminSid  = $me.id }
    }
} elseif (-not $AdminPassword) {
    throw 'Provide -AdminPassword, or use -EntraOnlyAuth if the tenant denies SQL authentication.'
}

# Databases under test. 'Shape' drives the generator in Seed-LabData.sql.
$databases = @()
foreach ($gb in $CalibrationSizesGb) {
    $databases += [pscustomobject]@{
        Name   = "$Prefix-calib-${gb}gb"
        SizeGb = $gb
        Shape  = 'mixed'
        Role   = 'calibration'
        Why    = 'Fits FixedOverhead and PerGb slope in the cost model'
    }
}
$databases += [pscustomobject]@{
    Name   = "$Prefix-probe-compressible"
    SizeGb = $CompressionProbeGb
    Shape  = 'compressible'
    Role   = 'compression-probe'
    Why    = 'Upper bound on BACPAC/backup compression ratio'
}
$databases += [pscustomobject]@{
    Name   = "$Prefix-probe-random"
    SizeGb = $CompressionProbeGb
    Shape  = 'random'
    Role   = 'compression-probe'
    Why    = 'Lower bound: incompressible data, worst-case artifact size'
}

Write-Host ''
Write-Host 'Lab plan' -ForegroundColor Cyan
$databases | Format-Table Name, SizeGb, Shape, Role, Why -AutoSize | Out-String -Width 160 | Write-Host
$totalGb = ($databases | Measure-Object SizeGb -Sum).Sum
Write-Host "Total seeded data: $totalGb GB across $($databases.Count) databases" -ForegroundColor Cyan
Write-Host ''

if (-not $PSCmdlet.ShouldProcess($ResourceGroup, 'provision LTR lab')) { return }

# --- Core resources -----------------------------------------------------------
Write-Host "Creating resource group $ResourceGroup ..." -ForegroundColor Cyan
Invoke-Az @('group', 'create', '-n', $ResourceGroup, '-l', $Location, '-o', 'none') | Out-Null

Write-Host "Creating logical server $server (the server itself is free) ..." -ForegroundColor Cyan
if ($EntraOnlyAuth) {
    # A user-assigned managed identity is not optional here. Under Entra-only
    # authentication, BACPAC export must authenticate as a UAMI attached at the LOGICAL
    # SERVER level; a system-assigned identity, a database-scoped identity or a service
    # principal are all unsupported for import/export.
    Write-Host "Creating user-assigned managed identity $identityName ..." -ForegroundColor Cyan
    $umi = Invoke-Az @('identity', 'create', '-g', $ResourceGroup, '-n', $identityName,
                       '-l', $Location, '-o', 'json') | ConvertFrom-Json

    Invoke-Az @('sql', 'server', 'create', '-g', $ResourceGroup, '-n', $server, '-l', $Location,
                '--enable-ad-only-auth',
                '--external-admin-principal-type', $EntraAdminType,
                '--external-admin-name', $EntraAdminName,
                '--external-admin-sid', $EntraAdminSid,
                '--identity-type', 'UserAssigned',
                '--user-assigned-identity-id', $umi.id,
                '--pid', $umi.id,
                '-o', 'none') | Out-Null
} else {
    Invoke-Az @('sql', 'server', 'create', '-g', $ResourceGroup, '-n', $server, '-l', $Location,
                '-u', $AdminUser, '-p', $plainPassword, '-o', 'none') | Out-Null
}

# The BACPAC export service reaches the database from an Azure IP, so the
# allow-Azure-services rule (0.0.0.0) is required, not optional.
Invoke-Az @('sql', 'server', 'firewall-rule', 'create', '-g', $ResourceGroup, '-s', $server,
            '-n', 'AllowAzureServices', '--start-ip-address', '0.0.0.0',
            '--end-ip-address', '0.0.0.0', '-o', 'none') | Out-Null

$myIp = (Invoke-RestMethod 'https://api.ipify.org?format=json').ip
Write-Host "Allowing client IP $myIp ..." -ForegroundColor Cyan
Invoke-Az @('sql', 'server', 'firewall-rule', 'create', '-g', $ResourceGroup, '-s', $server,
            '-n', 'LabClient', '--start-ip-address', $myIp,
            '--end-ip-address', $myIp, '-o', 'none') | Out-Null

Write-Host "Creating artifact storage account $storageAccount ..." -ForegroundColor Cyan
Invoke-Az @('storage', 'account', 'create', '-g', $ResourceGroup, '-n', $storageAccount,
            '-l', $Location, '--sku', 'Standard_LRS', '--kind', 'StorageV2',
            '--min-tls-version', 'TLS1_2', '--allow-blob-public-access', 'false',
            '-o', 'none') | Out-Null

$storageKey = (Invoke-Az @('storage', 'account', 'keys', 'list', '-g', $ResourceGroup,
                           '-n', $storageAccount, '--query', '[0].value', '-o', 'tsv')).Trim()

Invoke-Az @('storage', 'container', 'create', '--account-name', $storageAccount,
            '--account-key', $storageKey, '-n', $container, '-o', 'none') | Out-Null

if ($EntraOnlyAuth) {
    # The export writes the BACPAC as the managed identity, not with the account key, so
    # the identity needs data-plane rights on the container. Role assignments are
    # eventually consistent; a failed export minutes after this line usually means the
    # assignment had not propagated yet rather than that it is wrong.
    $storageId = (Invoke-Az @('storage', 'account', 'show', '-g', $ResourceGroup,
                              '-n', $storageAccount, '--query', 'id', '-o', 'tsv')).Trim()
    Write-Host "Granting $identityName 'Storage Blob Data Contributor' on $storageAccount ..." -ForegroundColor Cyan
    Invoke-Az @('role', 'assignment', 'create', '--assignee-object-id', $umi.principalId,
                '--assignee-principal-type', 'ServicePrincipal',
                '--role', 'Storage Blob Data Contributor',
                '--scope', $storageId, '-o', 'none') | Out-Null
}

# --- Databases ----------------------------------------------------------------
$seedScript = Join-Path $PSScriptRoot 'Seed-LabData.sql'
$serverFqdn = "$server.database.windows.net"

# Connection arguments differ entirely between the two auth models, so build them once.
$sqlAuthArgs = @{}
if ($EntraOnlyAuth) {
    $sqlAuthArgs['AccessToken'] = (Invoke-Az @('account', 'get-access-token',
                                   '--resource', 'https://database.windows.net/',
                                   '--query', 'accessToken', '-o', 'tsv')).Trim()

    # Grant the export identity access to each database WITHOUT 'FROM EXTERNAL PROVIDER',
    # which would require the server to hold Directory Readers in Entra. Creating the
    # user from an explicit SID derived from the identity's client ID needs no directory
    # permission at all. The bytes are the client ID GUID in little-endian .NET order,
    # which is exactly what Guid.ToByteArray produces.
    $umiSidHex = '0x' + (([guid]$umi.clientId).ToByteArray().ForEach({ $_.ToString('X2') }) -join '')
    $grantUmiSql = @"
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'$identityName')
    CREATE USER [$identityName] WITH SID = $umiSidHex, TYPE = E;
ALTER ROLE db_owner ADD MEMBER [$identityName];
"@
} else {
    $sqlAuthArgs['Credential'] = [pscredential]::new($AdminUser, $AdminPassword)
}

foreach ($db in $databases) {
    Write-Host ''
    Write-Host "Creating $($db.Name) ($($db.SizeGb) GB, $($db.Shape)) ..." -ForegroundColor Yellow

    # max-size must exceed the seeded volume with headroom for the log and fill factor.
    $maxSizeGb = [math]::Max(2, [math]::Ceiling($db.SizeGb * 2.5))

    Invoke-Az @('sql', 'db', 'create', '-g', $ResourceGroup, '-s', $server, '-n', $db.Name,
                '--service-objective', $DbSku,
                '--max-size', "${maxSizeGb}GB",
                '--auto-pause-delay', $AutoPauseMinutes,
                '--backup-storage-redundancy', 'Local',
                '-o', 'none') | Out-Null

    if (-not $SkipDataLoad) {
        Write-Host "  seeding $($db.SizeGb) GB of '$($db.Shape)' data..." -ForegroundColor DarkGray
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        Invoke-Sqlcmd -ServerInstance $serverFqdn -Database $db.Name @sqlAuthArgs `
                      -InputFile $seedScript -QueryTimeout 0 -TrustServerCertificate `
                      -Variable @("TargetGb=$($db.SizeGb)", "Shape=$($db.Shape)") | Out-Null
        $sw.Stop()
        Write-Host "  seeded in $([math]::Round($sw.Elapsed.TotalMinutes,1)) min" -ForegroundColor DarkGray
    }

    if ($EntraOnlyAuth) {
        Write-Host "  granting $identityName db_owner (needed for BACPAC export) ..." -ForegroundColor DarkGray
        Invoke-Sqlcmd -ServerInstance $serverFqdn -Database $db.Name @sqlAuthArgs `
                      -Query $grantUmiSql -QueryTimeout 0 -TrustServerCertificate | Out-Null
    }

    # Enabling an LTR policy for the FIRST time copies the most recent PITR full backup
    # into long-term storage, which is the fastest path to a testable LTR backup.
    Write-Host '  enabling LTR policy (weekly, 12 weeks)...' -ForegroundColor DarkGray
    Invoke-Az @('sql', 'db', 'ltr-policy', 'set', '-g', $ResourceGroup, '-s', $server,
                '-n', $db.Name, '--weekly-retention', 'P12W', '-o', 'none') | Out-Null
}

# --- Optional managed instance -------------------------------------------------
$miName = $null
if ($IncludeManagedInstance) {
    if (-not $MiSubnetId) { throw 'Provide -MiSubnetId: an MI requires a delegated subnet.' }
    $miName = "$Prefix-mi"
    Write-Host ''
    Write-Host "Creating managed instance $miName (this takes 4-6 hours) ..." -ForegroundColor Yellow
    $miArgs = @('sql', 'mi', 'create', '-g', $ResourceGroup, '-n', $miName, '-l', $Location,
                '--subnet', $MiSubnetId,
                '--capacity', '4', '--storage', '32GB',
                '--edition', 'GeneralPurpose', '--family', 'Gen5',
                '--no-wait', '-o', 'none')
    # AzureSQLMI_WithoutAzureADOnlyAuthentication_Deny mirrors the logical-server policy,
    # so the instance needs the same treatment.
    if ($EntraOnlyAuth) {
        $miArgs += @('--enable-ad-only-auth',
                     '--external-admin-principal-type', $EntraAdminType,
                     '--external-admin-name', $EntraAdminName,
                     '--external-admin-sid', $EntraAdminSid)
    } else {
        $miArgs += @('-u', $AdminUser, '-p', $plainPassword)
    }
    Invoke-Az $miArgs | Out-Null
    Write-Host '  submitted asynchronously; poll with: az sql mi show' -ForegroundColor DarkGray
}

# --- Lab context ---------------------------------------------------------------
$context = [pscustomobject]@{
    ResourceGroup   = $ResourceGroup
    Location        = $Location
    Server          = $server
    ServerFqdn      = $serverFqdn
    StorageAccount  = $storageAccount
    Container       = $container
    ContainerUri    = "https://$storageAccount.blob.core.windows.net/$container"
    AdminUser       = $AdminUser
    AuthMode        = $(if ($EntraOnlyAuth) { 'EntraOnly' } else { 'Sql' })
    EntraAdminName  = $EntraAdminName
    ExportIdentity  = $(if ($EntraOnlyAuth) { $identityName } else { $null })
    ExportIdentityId = $(if ($EntraOnlyAuth) { $umi.id } else { $null })
    Databases       = $databases
    SeededAtUtc     = (Get-Date).ToUniversalTime().ToString('o')
    ManagedInstance = $miName
}
$contextPath = Join-Path $PSScriptRoot 'lab-context.json'
$context | ConvertTo-Json -Depth 5 | Set-Content $contextPath

Write-Host ''
Write-Host '================================================================' -ForegroundColor Green
Write-Host 'Seed phase complete.' -ForegroundColor Green
Write-Host "Lab context written to $contextPath"
Write-Host ''
Write-Host 'LTR backups are created on Microsoft''s schedule and may take up to 7 days' -ForegroundColor Yellow
Write-Host 'to appear. Do not proceed until they do. Poll with:' -ForegroundColor Yellow
Write-Host "    .\Watch-LtrLabBackups.ps1 -Location $Location -Server $server" -ForegroundColor Cyan
Write-Host ''
Write-Host 'The databases are serverless and auto-pause, so the wait costs storage only.' -ForegroundColor DarkGray
Write-Host '================================================================' -ForegroundColor Green
