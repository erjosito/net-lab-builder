[CmdletBinding()]
param(
    [Parameter(Mandatory)] [ValidateSet('Public','ServiceEndpoint','Restricted','Private','PrivateOnly')] [string]$Mode,
    [string]$ResourceGroup = 'rg-storage-sepath-0805175837',
    [string]$TranslatorName = 'aisepath0805175837'
)

$ErrorActionPreference = 'Stop'
$VnetName = 'vnet-endpoint-path'
$ClientSubnet = 'snet-client'
$Zone = 'privatelink.cognitiveservices.azure.com'
$Link = 'translator-vnet-link'
$accountId = (az cognitiveservices account show -g $ResourceGroup -n $TranslatorName --query id -o tsv).Trim()
$subnetId = (az network vnet subnet show -g $ResourceGroup --vnet-name $VnetName -n $ClientSubnet --query id -o tsv).Trim()

function Assert-Az {
    if ($LASTEXITCODE -ne 0) { throw 'Azure CLI command failed.' }
}

function Remove-DnsLink {
    $exists = az network private-dns link vnet show -g $ResourceGroup -z $Zone -n $Link --query name -o tsv 2>$null
    if ($LASTEXITCODE -eq 0 -and $exists) {
        az network private-dns link vnet delete -g $ResourceGroup -z $Zone -n $Link --yes -o none
        Assert-Az
    }
}

function Add-DnsLink {
    $exists = az network private-dns link vnet show -g $ResourceGroup -z $Zone -n $Link --query name -o tsv 2>$null
    if ($LASTEXITCODE -eq 0 -and $exists) { return }
    az network private-dns link vnet create -g $ResourceGroup -z $Zone -n $Link `
        -v $VnetName -e false -o none | Out-Null
    Assert-Az
}

function Disable-ServiceEndpoint {
    az network vnet subnet update -g $ResourceGroup --vnet-name $VnetName -n $ClientSubnet `
        --remove serviceEndpoints -o none | Out-Null
    Assert-Az
}

function Enable-ServiceEndpoint {
    az network vnet subnet update -g $ResourceGroup --vnet-name $VnetName -n $ClientSubnet `
        --service-endpoints Microsoft.CognitiveServices -o none | Out-Null
    Assert-Az
}

function Set-PublicAllow {
    az resource update --ids $accountId `
        --set properties.publicNetworkAccess=Enabled properties.networkAcls.defaultAction=Allow -o none | Out-Null
    Assert-Az
    $rules = @(az cognitiveservices account show -g $ResourceGroup -n $TranslatorName -o json |
        ConvertFrom-Json | ForEach-Object { $_.properties.networkAcls.virtualNetworkRules })
    if ($rules.id -contains $subnetId) {
        az cognitiveservices account network-rule remove -g $ResourceGroup -n $TranslatorName `
            --subnet $subnetId -o none | Out-Null
        Assert-Az
    }
}

function Set-Restricted {
    az cognitiveservices account network-rule add -g $ResourceGroup -n $TranslatorName `
        --subnet $subnetId -o none | Out-Null
    Assert-Az
    az resource update --ids $accountId `
        --set properties.networkAcls.defaultAction=Deny -o none | Out-Null
    Assert-Az
}

switch ($Mode) {
    'Public' {
        Set-PublicAllow
        Remove-DnsLink
        Disable-ServiceEndpoint
    }
    'ServiceEndpoint' {
        Set-PublicAllow
        Remove-DnsLink
        Enable-ServiceEndpoint
    }
    'Restricted' {
        Set-PublicAllow
        Remove-DnsLink
        Enable-ServiceEndpoint
        Set-Restricted
    }
    'Private' {
        Set-PublicAllow
        Disable-ServiceEndpoint
        Add-DnsLink
    }
    'PrivateOnly' {
        Set-PublicAllow
        Disable-ServiceEndpoint
        Add-DnsLink
        az resource update --ids $accountId --set properties.publicNetworkAccess=Disabled -o none | Out-Null
        Assert-Az
    }
}

$account = az cognitiveservices account show -g $ResourceGroup -n $TranslatorName -o json | ConvertFrom-Json
$subnet = az network vnet subnet show -g $ResourceGroup --vnet-name $VnetName -n $ClientSubnet -o json | ConvertFrom-Json
$links = @(az network private-dns link vnet list -g $ResourceGroup -z $Zone -o json | ConvertFrom-Json)
[ordered]@{
    mode = $Mode
    publicNetworkAccess = $account.properties.publicNetworkAccess
    defaultAction = $account.properties.networkAcls.defaultAction
    vnetRuleCount = @($account.properties.networkAcls.virtualNetworkRules | Where-Object { $_ }).Count
    serviceEndpoints = @($subnet.serviceEndpoints.service | Where-Object { $_ })
    privateDnsLinks = @($links.name | Where-Object { $_ })
} | ConvertTo-Json -Depth 4
