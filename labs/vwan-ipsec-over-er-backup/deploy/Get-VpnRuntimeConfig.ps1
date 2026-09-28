#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$ResourceGroup,
    [Parameter(Mandatory)] [string]$VirtualWanName,
    [Parameter(Mandatory)] [string]$StorageAccountName,
    [Parameter(Mandatory)] [string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$temp = Join-Path $env:TEMP "vwan-vpn-$([guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $temp | Out-Null
try {
    az storage account create -g $ResourceGroup -n $StorageAccountName -l swedencentral --sku Standard_LRS --kind StorageV2 --allow-blob-public-access false --only-show-errors -o none
    az storage container create --account-name $StorageAccountName -n vpnconfig --auth-mode login --only-show-errors -o none
    $expiry = (Get-Date).ToUniversalTime().AddHours(2).ToString('yyyy-MM-ddTHH:mmZ')
    $sas = az storage blob generate-sas --account-name $StorageAccountName -c vpnconfig -n runtime.json --permissions acw --expiry $expiry --auth-mode login --as-user --full-uri -o tsv
    $siteIds = @(
        (az network vpn-site show -g $ResourceGroup -n site-gcp-er --query id -o tsv),
        (az network vpn-site show -g $ResourceGroup -n site-gcp-inet --query id -o tsv)
    )
    $requestPath = Join-Path $temp 'request.json'
    @{ outputBlobSasUrl = $sas; vpnSites = $siteIds } | ConvertTo-Json | Set-Content $requestPath -Encoding utf8
    az network vpn-site download -g $ResourceGroup --vwan-name $VirtualWanName --request "@$requestPath" --only-show-errors -o none
    Start-Sleep -Seconds 30
    $rawPath = Join-Path $temp 'runtime.json'
    az storage blob download --account-name $StorageAccountName -c vpnconfig -n runtime.json -f $rawPath --auth-mode login --only-show-errors -o none
    if (-not (Test-Path $rawPath)) { throw 'VPN configuration download did not produce a file.' }
    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
    Copy-Item $rawPath (Join-Path $OutputDirectory '.runtime-vpn-config.json') -Force

    $raw = Get-Content $rawPath -Raw | ConvertFrom-Json
    $sanitized = $raw | ConvertTo-Json -Depth 30
    $sanitized = $sanitized -replace '(?i)("PSK"\s*:\s*")[^"]+','$1<REDACTED>'
    $sanitized | Set-Content (Join-Path $OutputDirectory 'vpn-generated-values-sanitized.json') -Encoding utf8
    Write-Output "VPN_RUNTIME_CONFIG_READY=true"
}
finally {
    Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
}
