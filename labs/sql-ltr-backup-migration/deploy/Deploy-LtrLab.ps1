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
    [Parameter(Mandatory)][securestring] $AdminPassword,

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
$plainPassword  = [System.Net.NetworkCredential]::new('', $AdminPassword).Password

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
Invoke-Az @('sql', 'server', 'create', '-g', $ResourceGroup, '-n', $server, '-l', $Location,
            '-u', $AdminUser, '-p', $plainPassword, '-o', 'none') | Out-Null

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

# --- Databases ----------------------------------------------------------------
$seedScript = Join-Path $PSScriptRoot 'Seed-LabData.sql'
$serverFqdn = "$server.database.windows.net"
$sqlCred    = [pscredential]::new($AdminUser, $AdminPassword)

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
        Invoke-Sqlcmd -ServerInstance $serverFqdn -Database $db.Name -Credential $sqlCred `
                      -InputFile $seedScript -QueryTimeout 0 -TrustServerCertificate `
                      -Variable @("TargetGb=$($db.SizeGb)", "Shape=$($db.Shape)") | Out-Null
        $sw.Stop()
        Write-Host "  seeded in $([math]::Round($sw.Elapsed.TotalMinutes,1)) min" -ForegroundColor DarkGray
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
    Invoke-Az @('sql', 'mi', 'create', '-g', $ResourceGroup, '-n', $miName, '-l', $Location,
                '-u', $AdminUser, '-p', $plainPassword, '--subnet', $MiSubnetId,
                '--capacity', '4', '--storage', '32GB',
                '--edition', 'GeneralPurpose', '--family', 'Gen5',
                '--no-wait', '-o', 'none') | Out-Null
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
