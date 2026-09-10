<#
.SYNOPSIS
    Provisions the private-endpoint variant of the LTR lab: VNet, NAT gateway,
    private endpoints for SQL and blob, and a jump VM to run sqlpackage.

.DESCRIPTION
    This architecture is required when the tenant forces publicNetworkAccess=Disabled
    on SQL logical servers (silently, even when you request Enabled). In that case
    az sql db export cannot work at all, because it reaches the database over the
    public endpoint. sqlpackage running inside the virtual network is the workaround.

    VERIFIED GOVERNANCE CONSTRAINTS (empirical, not theoretical):
      1. SQL authentication denied tenant-wide by policy
         AzureSQL_WithoutAzureADOnlyAuthentication_Deny in MCAPSGovDenyPolicies.
         Every SQL connection must use an Entra token. Do not use SecurityControl=Ignore.
      2. Public network access on SQL servers is force-disabled, silently. Three separate
         attempts (CLI update, ARM PATCH, fresh create with the flag set) all accepted
         the request, reported success, and came back Disabled.
      3. Storage accounts get allowSharedKeyAccess=false and publicNetworkAccess=Disabled
         force-applied. Account keys still list successfully (trap: az storage account
         keys list returns a key; that key is dead on every data-plane call). Always use
         --auth-mode login.

    TWO GOTCHAS THAT COST REAL TIME:

      GOTCHA 1: $PSNativeCommandArgumentPassing in PowerShell 7.4+
        Default mode is 'Windows', which silently drops empty-string arguments to native
        commands. az vm create --public-ip-address "" silently becomes
        az vm create with no --public-ip-address argument at all, which creates a public
        IP by default. Fix: set $PSNativeCommandArgumentPassing = 'Standard' at the top
        of any script that passes empty strings to az (or any native command).

      GOTCHA 2: account-key trap in storage data-plane calls
        Even after governance force-disables sharedKeyAccess, az storage account keys list
        succeeds and returns a real-looking key. That key fails on every data-plane call
        (container create, blob upload) with a confusing auth error, not the obvious
        "keys disabled" message. The failure mode lands late and looks like permissions.
        Mitigation: never use --account-key. Always use --auth-mode login.

    RESOURCE NAMES match the deployed lab (prefix ltrlab552754):
      Storage account : ltrlab552754sa
      Identity        : ltrlab552754-umi
      SQL server      : ltrlab552754-sql
      VNet            : ltrlab-vnet
      Subnets         : snet-pe (10.70.1.0/24), snet-vm (10.70.2.0/24)
      Private endpoints: pe-sql, pe-blob
      Private DNS     : privatelink.blob.core.windows.net,
                        privatelink.database.windows.net
      NAT             : pip-nat, natgw
      VM              : ltrlab-vm

.PARAMETER ResourceGroup
    Target resource group.

.PARAMETER Location
    Azure region. Defaults to swedencentral.

.PARAMETER Prefix
    Short prefix for all resources. Defaults to ltrlab552754.

.PARAMETER VmAdminUser
    Local admin username for the VM.

.PARAMETER VmAdminPassword
    Local admin password as SecureString. Never stored in any file.

.EXAMPLE
    .\Deploy-LtrLabPrivate.ps1 -ResourceGroup rg-ltr-lab `
        -VmAdminUser labadmin -VmAdminPassword (Read-Host -AsSecureString)

.NOTES
    The companion Remove-LtrLab.ps1 handles teardown. Do not run cleanup until the
    lab's LTR backups have been exported and verified.
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string] $ResourceGroup,
    [string] $Location        = 'swedencentral',
    [string] $Prefix          = 'ltrlab552754',
    [Parameter(Mandatory)][string] $VmAdminUser,
    [Parameter(Mandatory)][securestring] $VmAdminPassword,

    # SQL Entra admin - the UAMI will be used; set these to match your UAMI.
    # The UAMI clientId is used as the external-admin-sid for SQL.
    [string] $UamiName        = 'ltrlab552754-umi',   # must already exist or will be created

    [string] $VNetAddressPrefix  = '10.70.0.0/16',
    [string] $PeSubnetPrefix     = '10.70.1.0/24',
    [string] $VmSubnetPrefix     = '10.70.2.0/24',

    [string] $VmSku           = 'Standard_D4s_v5',
    [string] $VmImage         = 'Win2022Datacenter',
    [int]    $OsDiskGb        = 256
)

$ErrorActionPreference = 'Stop'

# CRITICAL: PowerShell 7.x in Windows mode silently drops empty-string arguments to
# native commands. --public-ip-address "" becomes invisible. Standard mode passes them
# correctly.
$PSNativeCommandArgumentPassing = 'Standard'

function Invoke-Az {
    param([string[]] $Arguments)
    $out = & az @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "az $($Arguments -join ' ') failed:`n$out" }
    return $out
}

$server       = "$Prefix-sql"
$storageAcct  = ($Prefix -replace '[^a-z0-9]', '') + 'sa'
$container    = 'ltr-artifacts'
$vnet         = 'ltrlab-vnet'
$snetPe       = 'snet-pe'
$snetVm       = 'snet-vm'
$pipNat       = 'pip-nat'
$natGw        = 'natgw'
$peSql        = 'pe-sql'
$peBlob       = 'pe-blob'
$dnsZoneSql   = 'privatelink.database.windows.net'
$dnsZoneBlob  = 'privatelink.blob.core.windows.net'
$vmName       = 'ltrlab-vm'
$plainPwd     = [System.Net.NetworkCredential]::new('', $VmAdminPassword).Password

if (-not $PSCmdlet.ShouldProcess($ResourceGroup, 'provision private LTR lab')) { return }

# --- Resource group -----------------------------------------------------------
Write-Host "Resource group $ResourceGroup ..." -ForegroundColor Cyan
Invoke-Az @('group', 'create', '-n', $ResourceGroup, '-l', $Location,
            '--tags', 'lab=sql-ltr-backup-migration', 'owner=jose', 'ephemeral=true',
            '-o', 'none') | Out-Null

# --- User-assigned managed identity ------------------------------------------
Write-Host "Identity $UamiName ..." -ForegroundColor Cyan
$umi = Invoke-Az @('identity', 'create', '-g', $ResourceGroup, '-n', $UamiName,
                   '-l', $Location, '-o', 'json') | ConvertFrom-Json

# --- Storage account ----------------------------------------------------------
# NOTE: the tenant will force-apply allowSharedKeyAccess=false and
# publicNetworkAccess=Disabled regardless of what you request here. That is expected.
# Never use --account-key in any downstream command; use --auth-mode login always.
Write-Host "Storage account $storageAcct ..." -ForegroundColor Cyan
Invoke-Az @('storage', 'account', 'create', '-g', $ResourceGroup, '-n', $storageAcct,
            '-l', $Location, '--sku', 'Standard_LRS', '--kind', 'StorageV2',
            '--min-tls-version', 'TLS1_2', '--allow-blob-public-access', 'false',
            '-o', 'none') | Out-Null

$storageId = (Invoke-Az @('storage', 'account', 'show', '-g', $ResourceGroup,
                          '-n', $storageAcct, '--query', 'id', '-o', 'tsv')).Trim()

Write-Host "Granting $UamiName Storage Blob Data Contributor ..." -ForegroundColor Cyan
Invoke-Az @('role', 'assignment', 'create',
            '--assignee-object-id', $umi.principalId,
            '--assignee-principal-type', 'ServicePrincipal',
            '--role', 'Storage Blob Data Contributor',
            '--scope', $storageId, '-o', 'none') | Out-Null

# --- SQL logical server -------------------------------------------------------
# Entra-only auth required. UAMI clientId is used as the external-admin-sid (not
# principalId). This is the external-admin-principal-type=Application pattern.
Write-Host "SQL server $server (Entra-only, UAMI as admin) ..." -ForegroundColor Cyan
Invoke-Az @('sql', 'server', 'create', '-g', $ResourceGroup, '-n', $server, '-l', $Location,
            '--enable-ad-only-auth',
            '--external-admin-principal-type', 'Application',
            '--external-admin-name', $UamiName,
            '--external-admin-sid', $umi.clientId,
            '--identity-type', 'UserAssigned',
            '--user-assigned-identity-id', $umi.id,
            '--pid', $umi.id,
            '-o', 'none') | Out-Null

# NOTE: do NOT add firewall rules. The tenant forces publicNetworkAccess=Disabled
# regardless of your request, so firewall rules are irrelevant and the 0.0.0.0
# AllowAzureServices rule will fail with DenyPublicEndpointEnabled anyway.

# --- Virtual network ----------------------------------------------------------
Write-Host "VNet $vnet ..." -ForegroundColor Cyan
Invoke-Az @('network', 'vnet', 'create', '-g', $ResourceGroup, '-n', $vnet,
            '--address-prefix', $VNetAddressPrefix, '-o', 'none') | Out-Null

Invoke-Az @('network', 'vnet', 'subnet', 'create', '-g', $ResourceGroup,
            '--vnet-name', $vnet, '-n', $snetPe,
            '--address-prefix', $PeSubnetPrefix,
            '--private-endpoint-network-policies', 'Disabled',
            '-o', 'none') | Out-Null

Invoke-Az @('network', 'vnet', 'subnet', 'create', '-g', $ResourceGroup,
            '--vnet-name', $vnet, '-n', $snetVm,
            '--address-prefix', $VmSubnetPrefix,
            '-o', 'none') | Out-Null

# --- NAT gateway (outbound internet for VM) -----------------------------------
Write-Host "NAT gateway $natGw ..." -ForegroundColor Cyan
Invoke-Az @('network', 'public-ip', 'create', '-g', $ResourceGroup, '-n', $pipNat,
            '-l', $Location, '--sku', 'Standard', '--allocation-method', 'Static',
            '-o', 'none') | Out-Null

Invoke-Az @('network', 'nat', 'gateway', 'create', '-g', $ResourceGroup, '-n', $natGw,
            '-l', $Location, '--public-ip-addresses', $pipNat,
            '--idle-timeout', '10', '-o', 'none') | Out-Null

Invoke-Az @('network', 'vnet', 'subnet', 'update', '-g', $ResourceGroup,
            '--vnet-name', $vnet, '-n', $snetVm,
            '--nat-gateway', $natGw, '-o', 'none') | Out-Null

# --- Private DNS zones --------------------------------------------------------
Write-Host "Private DNS zones ..." -ForegroundColor Cyan
$vnetId = (Invoke-Az @('network', 'vnet', 'show', '-g', $ResourceGroup, '-n', $vnet,
                       '--query', 'id', '-o', 'tsv')).Trim()

foreach ($zone in @($dnsZoneSql, $dnsZoneBlob)) {
    Invoke-Az @('network', 'private-dns', 'zone', 'create', '-g', $ResourceGroup,
                '-n', $zone, '-o', 'none') | Out-Null
    Invoke-Az @('network', 'private-dns', 'link', 'vnet', 'create',
                '-g', $ResourceGroup, '-z', $zone, '-n', "link-$($zone -replace '\.', '-')",
                '-v', $vnetId, '--registration-enabled', 'false', '-o', 'none') | Out-Null
}

# --- Private endpoints --------------------------------------------------------
Write-Host "Private endpoint $peSql (SQL) ..." -ForegroundColor Cyan
$sqlId = (Invoke-Az @('sql', 'server', 'show', '-g', $ResourceGroup, '-n', $server,
                      '--query', 'id', '-o', 'tsv')).Trim()
$peSubnetId = (Invoke-Az @('network', 'vnet', 'subnet', 'show', '-g', $ResourceGroup,
                           '--vnet-name', $vnet, '-n', $snetPe,
                           '--query', 'id', '-o', 'tsv')).Trim()

Invoke-Az @('network', 'private-endpoint', 'create', '-g', $ResourceGroup, '-n', $peSql,
            '--connection-name', 'pe-sql-conn', '--private-connection-resource-id', $sqlId,
            '--group-id', 'sqlServer', '--subnet', $peSubnetId, '-o', 'none') | Out-Null

Invoke-Az @('network', 'private-endpoint', 'dns-zone-group', 'create',
            '-g', $ResourceGroup, '--endpoint-name', $peSql,
            '-n', 'sqlDnsGroup', '--private-dns-zone', $dnsZoneSql,
            '--zone-name', 'sqlZone', '-o', 'none') | Out-Null

Write-Host "Private endpoint $peBlob (blob) ..." -ForegroundColor Cyan
Invoke-Az @('network', 'private-endpoint', 'create', '-g', $ResourceGroup, '-n', $peBlob,
            '--connection-name', 'pe-blob-conn', '--private-connection-resource-id', $storageId,
            '--group-id', 'blob', '--subnet', $peSubnetId, '-o', 'none') | Out-Null

Invoke-Az @('network', 'private-endpoint', 'dns-zone-group', 'create',
            '-g', $ResourceGroup, '--endpoint-name', $peBlob,
            '-n', 'blobDnsGroup', '--private-dns-zone', $dnsZoneBlob,
            '--zone-name', 'blobZone', '-o', 'none') | Out-Null

# --- Virtual machine ----------------------------------------------------------
# No NSG, no public IP. VM gets outbound internet via NAT gateway.
# --public-ip-address "" requires $PSNativeCommandArgumentPassing = 'Standard' (set
# at the top of this script). In Windows mode (PS7 default), the empty string is
# silently dropped and az vm create provisions a public IP.
Write-Host "VM $vmName ..." -ForegroundColor Cyan
$vmSubnetId = (Invoke-Az @('network', 'vnet', 'subnet', 'show', '-g', $ResourceGroup,
                           '--vnet-name', $vnet, '-n', $snetVm,
                           '--query', 'id', '-o', 'tsv')).Trim()

Invoke-Az @('vm', 'create', '-g', $ResourceGroup, '-n', $vmName, '-l', $Location,
            '--image', $VmImage, '--size', $VmSku,
            '--admin-username', $VmAdminUser, '--admin-password', $plainPwd,
            '--subnet', $vmSubnetId,
            '--public-ip-address', '',
            '--nsg', '',
            '--os-disk-size-gb', $OsDiskGb.ToString(),
            '--assign-identity', $umi.id,
            '-o', 'none') | Out-Null

Write-Host ''
Write-Host '================================================================' -ForegroundColor Green
Write-Host 'Private lab deployed.' -ForegroundColor Green
Write-Host "VM: $vmName (no public IP, use az vm run-command for shell access)"
Write-Host "SQL: $server.database.windows.net (private endpoint only)"
Write-Host "Storage: $storageAcct (private endpoint only, --auth-mode login)"
Write-Host ''
Write-Host 'Next: install tooling inside the VM via az vm run-command invoke.' -ForegroundColor Cyan
Write-Host '================================================================' -ForegroundColor Green
