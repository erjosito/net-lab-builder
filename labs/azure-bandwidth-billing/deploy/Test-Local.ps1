[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$scripts = Get-ChildItem $PSScriptRoot -Filter '*.ps1'
foreach ($file in $scripts) {
    $tokens = $null
    $errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw "$($file.Name): $($errors.Message -join '; ')" }
}
$template = Get-Content (Join-Path $PSScriptRoot 'main.json') -Raw | ConvertFrom-Json -Depth 100
function Require($Condition, $Message) { if (-not $Condition) { throw $Message } }
$vm = $template.resources | Where-Object type -eq 'Microsoft.Compute/virtualMachines'
$nic = $template.resources | Where-Object type -eq 'Microsoft.Network/networkInterfaces'
$pip = $template.resources | Where-Object type -eq 'Microsoft.Network/publicIPAddresses'
$vnet = $template.resources | Where-Object type -eq 'Microsoft.Network/virtualNetworks'
$nsg = $template.resources | Where-Object type -eq 'Microsoft.Network/networkSecurityGroups'
$diskTags = $template.resources | Where-Object type -eq 'Microsoft.Resources/tags'
Require ($template.resources.Count -eq 6) 'Unexpected resource family.'
Require ($vm.copy.count -eq 3 -and $nic.copy.count -eq 3 -and $nsg.copy.count -eq 3) 'Three-VM/NIC/NSG limit.'
Require ($pip.copy.count -eq 2 -and $pip.sku.name -eq 'Standard') 'Exactly two Standard PIPs.'
Require ($vnet.copy.count -eq 2 -and $vnet.properties.subnets[0].properties.defaultOutboundAccess -eq $false) 'Explicit outbound required.'
Require ($template.variables.location -eq 'swedencentral') 'D0 Sweden Central only.'
Require (($template.variables.vnetIndices -join ',') -eq '0,1,0') 'A/P same VNet; B separate.'
Require ($vm.properties.storageProfile.osDisk.diskSizeGB -eq 30 -and $vm.properties.storageProfile.osDisk.managedDisk.storageAccountType -eq 'StandardSSD_LRS') '30 GiB Standard SSD required.'
Require ($vm.properties.storageProfile.imageReference.sku -eq '22_04-lts-gen2') 'Ubuntu 22.04 Gen2 required.'
Require ($vm.properties.osProfile.linuxConfiguration.disablePasswordAuthentication -eq $true) 'SSH key only.'
Require ($template.parameters.adminPublicKey.type -eq 'securestring') 'Do not expose SSH key in ARM deployment history.'
Require ($diskTags.copy.count -eq 3 -and $diskTags.dependsOn[0] -eq 'vms') 'Managed disks must be tagged after creation.'
$rules = @($nsg.properties.securityRules)
Require ($rules.Count -eq 1 -and $rules[0].properties.access -eq 'Deny' -and $rules[0].properties.priority -eq 100) 'No app or SSH endpoint before harness approval.'
Require ($nic.properties.enableAcceleratedNetworking -eq $false -and $nic.properties.enableIPForwarding -eq $false) 'No unnecessary forwarding/acceleration.'
Require ($template.variables.tags.lab -eq 'true' -and $template.variables.tags.created_by -eq 'copilot-lab') 'Owned-resource tags required.'
Require ($template.parameters.vmSize.allowedValues.Count -eq 5) 'No unapproved SKU family.'
Write-Output 'PASS: PowerShell parse and offline infrastructure safety assertions. This is not ARM validation or an allocation test.'
