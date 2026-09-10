<#
.SYNOPSIS
    Starts provisioning the Azure SQL Managed Instance for the LTR lab.

.DESCRIPTION
    Creates the dedicated SQL Managed Instance subnet prerequisites, verifies the
    subnet, then issues az sql mi create with --no-wait. The managed instance
    create normally takes 4-6 hours. This script does not wait for completion.

    It is intentionally scoped to the managed instance and its subnet
    prerequisites. It does not create test databases, run BACKUP TO URL, or change
    the existing SQL logical server or storage account.

    The tenant enforces Entra-only SQL auth. Do not pass --admin-user or
    --admin-password. For external-admin-principal-type Application,
    --external-admin-sid must be the UAMI clientId, not the principalId. Getting
    clientId vs principalId wrong can cost a full managed instance create cycle.

.PARAMETER Subscription
    Azure subscription name or ID. If omitted, AZURE_SUBSCRIPTION_ID is used when
    present, otherwise the active Azure CLI subscription is used.

.PARAMETER ResourceGroup
    Existing resource group that contains the VNet and UAMI.

.PARAMETER Location
    Azure region.

.PARAMETER VNetName
    Existing VNet name.

.PARAMETER MiSubnetName
    Dedicated managed instance subnet name.

.PARAMETER MiSubnetPrefix
    Dedicated managed instance subnet prefix.

.PARAMETER RouteTableName
    Route table associated to the MI subnet. It must remain empty.

.PARAMETER NetworkSecurityGroupName
    NSG associated to the MI subnet. It must have only default rules.

.PARAMETER ManagedInstanceName
    SQL Managed Instance name.

.PARAMETER UamiName
    Existing user-assigned managed identity name.

.PARAMETER UamiClientId
    UAMI clientId. Used as external-admin-sid for Application principal type.

.EXAMPLE
    .\Deploy-LtrLabMi.ps1 -Subscription Litware-MngEnvMCAP642473-jomore
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string] $Subscription = $env:AZURE_SUBSCRIPTION_ID,
    [string] $ResourceGroup = 'rg-ltr-lab',
    [string] $Location = 'swedencentral',
    [string] $VNetName = 'ltrlab-vnet',
    [string] $MiSubnetName = 'snet-mi',
    [string] $MiSubnetPrefix = '10.70.3.0/24',
    [string] $RouteTableName = 'rt-snet-mi',
    [string] $NetworkSecurityGroupName = 'nsg-snet-mi',
    [string] $ManagedInstanceName = 'ltrlab552754-mi',
    [string] $UamiName = 'ltrlab552754-umi',
    [string] $UamiClientId = '9dab92a8-7084-442e-8617-139fda64b1c9',
    [string] $VCoreCapacity = '4',
    [string] $StorageSize = '32GB'
)

$ErrorActionPreference = 'Stop'

# PowerShell 7.x on Windows defaults to Windows argument passing, which can
# silently drop empty-string native command arguments. Standard mode keeps az
# arguments predictable.
$PSNativeCommandArgumentPassing = 'Standard'

function Invoke-Az {
    param([Parameter(Mandatory)][string[]] $Arguments)

    $output = & az @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "az $($Arguments -join ' ') failed:`n$output"
    }

    return $output
}

function Get-AzJsonOrNull {
    param([Parameter(Mandatory)][string[]] $Arguments)

    $output = & az @Arguments 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($output)) {
        return $null
    }

    return $output | ConvertFrom-Json
}

function Set-AzContext {
    if (-not [string]::IsNullOrWhiteSpace($Subscription)) {
        Invoke-Az @('account', 'set', '--subscription', $Subscription) | Out-Null
    }

    return (Invoke-Az @('account', 'show', '--query', 'id', '-o', 'tsv')).Trim()
}

function Test-MiQuota {
    param([Parameter(Mandatory)][string] $SubscriptionId)

    $usageUrl = "https://management.azure.com/subscriptions/$SubscriptionId/providers/Microsoft.Sql/locations/$Location/usages?api-version=2021-11-01"
    $usage = Invoke-Az @('rest', '--method', 'get', '--url', $usageUrl, '-o', 'json') | ConvertFrom-Json
    $standardSeries = $usage.value | Where-Object { $_.name -eq 'SubscriptionSQLManagedInstanceStandardSeriesVCoreQuota' } | Select-Object -First 1

    if (-not $standardSeries) {
        throw 'Could not find SubscriptionSQLManagedInstanceStandardSeriesVCoreQuota in Microsoft.Sql location usage response.'
    }

    $available = [int]$standardSeries.properties.limit - [int]$standardSeries.properties.currentValue
    if ($available -lt [int]$VCoreCapacity) {
        throw "Insufficient SQL MI Standard Series vCore quota in $Location. Available=$available, required=$VCoreCapacity, limit=$($standardSeries.properties.limit), current=$($standardSeries.properties.currentValue)."
    }

    Write-Host "Quota OK: SQL MI Standard Series vCore available=$available required=$VCoreCapacity."
}

function Get-OrCreateRouteTable {
    $existingRouteTable = Get-AzJsonOrNull @('network', 'route-table', 'show', '--resource-group', $ResourceGroup, '--name', $RouteTableName, '-o', 'json')
    if ($existingRouteTable) {
        if ($existingRouteTable.disableBgpRoutePropagation) {
            throw "Route table $RouteTableName has BGP route propagation disabled. Refusing to proceed."
        }

        return $existingRouteTable.id
    }

    $routeTable = Invoke-Az @(
        'network', 'route-table', 'create',
        '--resource-group', $ResourceGroup,
        '--name', $RouteTableName,
        '--location', $Location,
        '--disable-bgp-route-propagation', 'false',
        '-o', 'json'
    ) | ConvertFrom-Json

    $routeTableId = $routeTable.NewRouteTable.id
    if ([string]::IsNullOrWhiteSpace($routeTableId)) {
        $routeTableId = (Invoke-Az @('network', 'route-table', 'show', '--resource-group', $ResourceGroup, '--name', $RouteTableName, '--query', 'id', '-o', 'tsv')).Trim()
    }

    return $routeTableId
}

function Get-OrCreateNetworkSecurityGroup {
    $existingNsg = Get-AzJsonOrNull @('network', 'nsg', 'show', '--resource-group', $ResourceGroup, '--name', $NetworkSecurityGroupName, '-o', 'json')
    if ($existingNsg) {
        return $existingNsg.id
    }

    $nsg = Invoke-Az @(
        'network', 'nsg', 'create',
        '--resource-group', $ResourceGroup,
        '--name', $NetworkSecurityGroupName,
        '--location', $Location,
        '-o', 'json'
    ) | ConvertFrom-Json

    $nsgId = $nsg.NewNSG.id
    if ([string]::IsNullOrWhiteSpace($nsgId)) {
        $nsgId = (Invoke-Az @('network', 'nsg', 'show', '--resource-group', $ResourceGroup, '--name', $NetworkSecurityGroupName, '--query', 'id', '-o', 'tsv')).Trim()
    }

    return $nsgId
}

function Test-MiSubnet {
    param([bool] $RequireEmpty)

    $subnet = Invoke-Az @('network', 'vnet', 'subnet', 'show', '--resource-group', $ResourceGroup, '--vnet-name', $VNetName, '--name', $MiSubnetName, '-o', 'json') | ConvertFrom-Json
    $addressPrefix = if ($subnet.addressPrefix) { $subnet.addressPrefix } else { $subnet.addressPrefixes -join ',' }
    $delegationServiceName = $subnet.delegations[0].serviceName
    $ipConfigurationCount = if ($null -eq $subnet.ipConfigurations) { 0 } else { @($subnet.ipConfigurations).Count }
    $serviceAssociationLinkCount = if ($null -eq $subnet.serviceAssociationLinks) { 0 } else { @($subnet.serviceAssociationLinks).Count }

    $verification = [ordered]@{
        addressPrefix = $addressPrefix
        delegationServiceName = $delegationServiceName
        routeTableId = $subnet.routeTable.id
        networkSecurityGroupId = $subnet.networkSecurityGroup.id
        ipConfigurationsCount = $ipConfigurationCount
        serviceAssociationLinkCount = $serviceAssociationLinkCount
    }

    $verification | ConvertTo-Json -Depth 5 | Write-Host

    if ($addressPrefix -ne $MiSubnetPrefix) { throw "Subnet addressPrefix verification failed: $addressPrefix" }
    if ($delegationServiceName -ne 'Microsoft.Sql/managedInstances') { throw "Subnet delegation verification failed: $delegationServiceName" }
    if ([string]::IsNullOrWhiteSpace($subnet.routeTable.id)) { throw 'Subnet routeTable.id is null.' }
    if ([string]::IsNullOrWhiteSpace($subnet.networkSecurityGroup.id)) { throw 'Subnet networkSecurityGroup.id is null.' }
    if ($RequireEmpty -and $ipConfigurationCount -ne 0) { throw "Subnet is not empty before managed instance create: ipConfigurationsCount=$ipConfigurationCount." }

    return $subnet.id
}

function New-OrVerifyNetworkPrereqs {
    $routeTableId = Get-OrCreateRouteTable
    $nsgId = Get-OrCreateNetworkSecurityGroup

    $existingSubnet = Get-AzJsonOrNull @('network', 'vnet', 'subnet', 'show', '--resource-group', $ResourceGroup, '--vnet-name', $VNetName, '--name', $MiSubnetName, '-o', 'json')
    if ($existingSubnet) {
        Invoke-Az @(
            'network', 'vnet', 'subnet', 'update',
            '--resource-group', $ResourceGroup,
            '--vnet-name', $VNetName,
            '--name', $MiSubnetName,
            '--delegations', 'Microsoft.Sql/managedInstances',
            '--network-security-group', $nsgId,
            '--route-table', $routeTableId,
            '-o', 'none'
        ) | Out-Null
    } else {
        Invoke-Az @(
            'network', 'vnet', 'subnet', 'create',
            '--resource-group', $ResourceGroup,
            '--vnet-name', $VNetName,
            '--name', $MiSubnetName,
            '--address-prefixes', $MiSubnetPrefix,
            '--delegations', 'Microsoft.Sql/managedInstances',
            '--network-security-group', $nsgId,
            '--route-table', $routeTableId,
            '-o', 'none'
        ) | Out-Null
    }

    $subnetId = Test-MiSubnet -RequireEmpty $true

    $routeCount = @(Invoke-Az @('network', 'route-table', 'route', 'list', '--resource-group', $ResourceGroup, '--route-table-name', $RouteTableName, '-o', 'json') | ConvertFrom-Json).Count
    $customNsgRuleCount = @(Invoke-Az @('network', 'nsg', 'rule', 'list', '--resource-group', $ResourceGroup, '--nsg-name', $NetworkSecurityGroupName, '-o', 'json') | ConvertFrom-Json).Count

    if ($routeCount -ne 0) { throw "Route table $RouteTableName is not empty: $routeCount custom routes." }
    if ($customNsgRuleCount -ne 0) { throw "NSG $NetworkSecurityGroupName has custom rules: $customNsgRuleCount." }

    return $subnetId
}

function Start-ManagedInstanceCreate {
    param([Parameter(Mandatory)][string] $SubnetId)

    $umi = Invoke-Az @('identity', 'show', '--resource-group', $ResourceGroup, '--name', $UamiName, '-o', 'json') | ConvertFrom-Json
    if ($umi.clientId -ne $UamiClientId) {
        throw "UAMI clientId mismatch. Expected $UamiClientId, got $($umi.clientId). Refusing to risk wrong external-admin-sid."
    }

    $existingMi = Get-AzJsonOrNull @('sql', 'mi', 'show', '--resource-group', $ResourceGroup, '--name', $ManagedInstanceName, '-o', 'json')
    if ($existingMi) {
        Write-Host "Managed instance $ManagedInstanceName already exists. Not issuing a duplicate create."
        return $existingMi
    }

    if (-not $PSCmdlet.ShouldProcess($ManagedInstanceName, 'start SQL Managed Instance create')) {
        return $null
    }

    Invoke-Az @(
        'sql', 'mi', 'create',
        '--resource-group', $ResourceGroup,
        '--name', $ManagedInstanceName,
        '--location', $Location,
        '--enable-ad-only-auth',
        '--external-admin-principal-type', 'Application',
        '--external-admin-name', $UamiName,
        '--external-admin-sid', $UamiClientId,
        '--assign-identity',
        '--identity-type', 'UserAssigned',
        '--user-assigned-identity-id', $umi.id,
        '--pid', $umi.id,
        '--edition', 'GeneralPurpose',
        '--family', 'Gen5',
        '--capacity', $VCoreCapacity,
        '--storage', $StorageSize,
        '--license-type', 'BasePrice',
        '--backup-storage-redundancy', 'Local',
        '--public-data-endpoint-enabled', 'false',
        '--subnet', $SubnetId,
        '--no-wait'
    ) | Out-Null

    Start-Sleep -Seconds 20
    return Invoke-Az @('sql', 'mi', 'show', '--resource-group', $ResourceGroup, '--name', $ManagedInstanceName, '-o', 'json') | ConvertFrom-Json
}

$subscriptionId = Set-AzContext
Test-MiQuota -SubscriptionId $subscriptionId
$existingManagedInstance = Get-AzJsonOrNull @('sql', 'mi', 'show', '--resource-group', $ResourceGroup, '--name', $ManagedInstanceName, '-o', 'json')
if ($existingManagedInstance) {
    Write-Host "Managed instance $ManagedInstanceName already exists. Not touching network resources because SQL MI network intent policy owns the subnet now."
    Test-MiSubnet -RequireEmpty $false | Out-Null
    $managedInstance = $existingManagedInstance
} else {
    $subnetId = New-OrVerifyNetworkPrereqs
    $managedInstance = Start-ManagedInstanceCreate -SubnetId $subnetId
}

if ($managedInstance) {
    $identityKeys = if ($managedInstance.identity.userAssignedIdentities) {
        @($managedInstance.identity.userAssignedIdentities.PSObject.Properties.Name)
    } else {
        @()
    }

    [ordered]@{
        id = $managedInstance.id
        provisioningState = $managedInstance.provisioningState
        state = $managedInstance.state
        subnetId = $managedInstance.subnetId
        identityType = $managedInstance.identity.type
        userAssignedIdentityIds = $identityKeys
        primaryUserAssignedIdentityId = $managedInstance.primaryUserAssignedIdentityId
        azureAdOnlyAuthentication = $managedInstance.administrators.azureADOnlyAuthentication
        externalAdminPrincipalType = $managedInstance.administrators.principalType
        externalAdminLogin = $managedInstance.administrators.login
        externalAdminSid = $managedInstance.administrators.sid
        pollCommand = "az sql mi show -g $ResourceGroup -n $ManagedInstanceName --query ""{provisioningState:provisioningState,state:state,fullyQualifiedDomainName:fullyQualifiedDomainName}"" -o json"
    } | ConvertTo-Json -Depth 8
}
