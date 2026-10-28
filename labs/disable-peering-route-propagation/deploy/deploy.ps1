# Deploy Lab: Disable Peering Route Propagation (Hub-and-Spoke + 3 Hybrid Connections + NVA)
# Region: swedencentral
# Note: Run this script after registering Microsoft.Network/AllowDisablePeeringRoutes if testing the preview feature directly.

$ErrorActionPreference = "Stop"
$rg = "rg-disable-peering-routes-lab"
$loc = "swedencentral"

Write-Host "1. Registering AllowDisablePeeringRoutes feature flag (note: approvalType is ApprovalRequired)..."
az feature register --namespace Microsoft.Network --name AllowDisablePeeringRoutes -o none

Write-Host "2. Creating resource group $rg in $loc..."
az group create -n $rg -l $loc -o none

Write-Host "3. Creating Hub VNet (10.0.0.0/16), VPN Gateway (VpnGw1AZ, ASN 65515), and ExpressRoute Gateway (Standard)..."
az network vnet create -g $rg -n vnet-hub -l $loc --address-prefixes 10.0.0.0/16 --subnet-name GatewaySubnet --subnet-prefixes 10.0.0.0/24 -o none
az network vnet subnet create -g $rg --vnet-name vnet-hub -n snet-nva --address-prefixes 10.0.1.0/24 -o none
az network vnet subnet create -g $rg --vnet-name vnet-hub -n snet-hub-probe --address-prefixes 10.0.2.0/24 -o none

az network public-ip create -g $rg -n pip-vpngw-hub -l $loc --sku Standard --allocation-method Static --zone 1 2 3 -o none
az network vnet-gateway create -g $rg -n vpngw-hub -l $loc --vnet vnet-hub --public-ip-addresses pip-vpngw-hub --gateway-type Vpn --vpn-type RouteBased --sku VpnGw1AZ --asn 65515 --no-wait

az network public-ip create -g $rg -n pip-ergw-hub -l $loc --sku Standard --allocation-method Static -o none
az network vnet-gateway create -g $rg -n ergw-hub -l $loc --vnet vnet-hub --public-ip-addresses pip-ergw-hub --gateway-type ExpressRoute --sku Standard --no-wait

Write-Host "4. Creating On-Prem S2S VPN VNet (172.16.0.0/16), On-Prem SD-WAN VNet (172.17.0.0/16), and 10 Spoke VNets (10.1.0.0/16 .. 10.10.0.0/16)..."
az network vnet create -g $rg -n vnet-onprem -l $loc --address-prefixes 172.16.0.0/16 --subnet-name snet-onprem --subnet-prefixes 172.16.1.0/24 -o none
az network vnet create -g $rg -n vnet-onprem-sdwan -l $loc --address-prefixes 172.17.0.0/16 --subnet-name snet-onprem-sdwan --subnet-prefixes 172.17.1.0/24 -o none
for ($i = 1; $i -le 10; $i++) {
    az network vnet create -g $rg -n "vnet-spoke$i" -l $loc --address-prefixes "10.$i.0.0/16" --subnet-name snet-workload --subnet-prefixes "10.$i.1.0/24" -o none
}

Write-Host "5. Creating ExpressRoute Circuit (er-circuit-hub, 50 Mbps, Megaport, Frankfurt)..."
az network express-route create -g $rg -n er-circuit-hub -l $loc --bandwidth 50 Mbps --peering-location Frankfurt --provider Megaport --sku-family MeteredData --sku-tier Standard -o none

Write-Host "6. Creating NSG and Route Tables (rt-gw, rt-nva, rt-spoke1)..."
az network nsg create -g $rg -n nsg-lab -l $loc -o none
az network nsg rule create -g $rg --nsg-name nsg-lab -n AllowRFC1918In --priority 100 --direction Inbound --access Allow --protocol "*" --source-address-prefixes 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 --destination-address-prefixes "*" --destination-port-ranges "*" -o none
az network nsg rule create -g $rg --nsg-name nsg-lab -n AllowIPsecIn --priority 110 --direction Inbound --access Allow --protocol Udp --source-address-prefixes "*" --destination-address-prefixes "*" --destination-port-ranges 500 4500 -o none
az network nsg rule create -g $rg --nsg-name nsg-lab -n AllowRFC1918Out --priority 100 --direction Outbound --access Allow --protocol "*" --source-address-prefixes 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 --destination-address-prefixes "*" --destination-port-ranges "*" -o none

az network route-table create -g $rg -n rt-gw -l $loc -o none
az network route-table route create -g $rg --route-table-name rt-gw -n to-spokes-summary --address-prefix 10.0.0.0/8 --next-hop-type VirtualAppliance --next-hop-ip-address 10.0.1.4 -o none

az network route-table create -g $rg -n rt-nva -l $loc -o none
az network route-table route create -g $rg --route-table-name rt-nva -n to-onprem-sdwan --address-prefix 172.17.0.0/16 --next-hop-type VirtualAppliance --next-hop-ip-address 10.0.2.4 -o none

az network route-table create -g $rg -n rt-spoke1 -l $loc --disable-bgp-route-propagation true -o none
az network route-table route create -g $rg --route-table-name rt-spoke1 -n to-onprem --address-prefix 172.16.0.0/16 --next-hop-type VirtualAppliance --next-hop-ip-address 10.0.1.4 -o none
az network route-table route create -g $rg --route-table-name rt-spoke1 -n to-onprem-sdwan --address-prefix 172.17.0.0/16 --next-hop-type VirtualAppliance --next-hop-ip-address 10.0.1.4 -o none
az network route-table route create -g $rg --route-table-name rt-spoke1 -n to-onprem-er --address-prefix 172.18.0.0/16 --next-hop-type VirtualAppliance --next-hop-ip-address 10.0.1.4 -o none
az network route-table route create -g $rg --route-table-name rt-spoke1 -n to-spokes-summary --address-prefix 10.0.0.0/8 --next-hop-type VirtualAppliance --next-hop-ip-address 10.0.1.4 -o none

az network vnet subnet update -g $rg --vnet-name vnet-hub -n GatewaySubnet --route-table rt-gw -o none
az network vnet subnet update -g $rg --vnet-name vnet-hub -n snet-hub-probe --route-table rt-gw --network-security-group nsg-lab -o none
az network vnet subnet update -g $rg --vnet-name vnet-hub -n snet-nva --route-table rt-nva --network-security-group nsg-lab -o none
az network vnet subnet update -g $rg --vnet-name vnet-spoke1 -n snet-workload --route-table rt-spoke1 --network-security-group nsg-lab -o none
az network vnet subnet update -g $rg --vnet-name vnet-onprem -n snet-onprem --network-security-group nsg-lab -o none
az network vnet subnet update -g $rg --vnet-name vnet-onprem-sdwan -n snet-onprem-sdwan --network-security-group nsg-lab -o none

Write-Host "7. Deploying VMs (vm-onprem, vm-onprem-sdwan, vm-hub-nva, vm-hub-probe, vm-spoke1)..."
$sshKey = Join-Path $env:TEMP "id_rsa_disable_peering_lab"
if (-not (Test-Path "$sshKey.pub")) {
    ssh-keygen -t rsa -b 4096 -f $sshKey -N '""' -q
}
$pubKey = Get-Content "$sshKey.pub" -Raw

az network public-ip create -g $rg -n pip-vm-onprem -l $loc --sku Standard --allocation-method Static -o none
az network public-ip create -g $rg -n pip-vm-onprem-sdwan -l $loc --sku Standard --allocation-method Static -o none
az network public-ip create -g $rg -n pip-vm-hub-probe -l $loc --sku Standard --allocation-method Static -o none

az network nic create -g $rg -n nic-vm-onprem -l $loc --vnet-name vnet-onprem --subnet snet-onprem --private-ip-address 172.16.1.4 --public-ip-address pip-vm-onprem --ip-forwarding true --network-security-group nsg-lab -o none
az network nic create -g $rg -n nic-vm-onprem-sdwan -l $loc --vnet-name vnet-onprem-sdwan --subnet snet-onprem-sdwan --private-ip-address 172.17.1.4 --public-ip-address pip-vm-onprem-sdwan --ip-forwarding true --network-security-group nsg-lab -o none
az network nic create -g $rg -n nic-vm-hub-nva -l $loc --vnet-name vnet-hub --subnet snet-nva --private-ip-address 10.0.1.4 --ip-forwarding true --network-security-group nsg-lab -o none
az network nic create -g $rg -n nic-vm-hub-probe -l $loc --vnet-name vnet-hub --subnet snet-hub-probe --private-ip-address 10.0.2.4 --public-ip-address pip-vm-hub-probe --ip-forwarding true --network-security-group nsg-lab -o none
az network nic create -g $rg -n nic-vm-spoke1 -l $loc --vnet-name vnet-spoke1 --subnet snet-workload --private-ip-address 10.1.1.4 --network-security-group nsg-lab -o none

az vm create -g $rg -n vm-onprem -l $loc --nics nic-vm-onprem --image Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest --size Standard_B2ts_v2 --admin-username azureuser --ssh-key-values $pubKey --custom-data "$PSScriptRoot\cloud-init-onprem.yaml" --no-wait
az vm create -g $rg -n vm-onprem-sdwan -l $loc --nics nic-vm-onprem-sdwan --image Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest --size Standard_B2ts_v2 --admin-username azureuser --ssh-key-values $pubKey --no-wait
az vm create -g $rg -n vm-hub-nva -l $loc --nics nic-vm-hub-nva --image Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest --size Standard_B2ts_v2 --admin-username azureuser --ssh-key-values $pubKey --custom-data "$PSScriptRoot\cloud-init-nva.yaml" --no-wait
az vm create -g $rg -n vm-hub-probe -l $loc --nics nic-vm-hub-probe --image Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest --size Standard_B2ts_v2 --admin-username azureuser --ssh-key-values $pubKey --custom-data "$PSScriptRoot\cloud-init-spoke.yaml" --no-wait
az vm create -g $rg -n vm-spoke1 -l $loc --nics nic-vm-spoke1 --image Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest --size Standard_B2ts_v2 --admin-username azureuser --ssh-key-values $pubKey --custom-data "$PSScriptRoot\cloud-init-spoke.yaml" --no-wait

Write-Host "8. Waiting for VPN and ExpressRoute Gateway provisioning to complete..."
az network vnet-gateway wait -g $rg -n vpngw-hub --created
az network vnet-gateway wait -g $rg -n ergw-hub --created

Write-Host "9. Creating VNet peerings for all 10 spokes (AllowGatewayTransit + UseRemoteGateways)..."
for ($i = 1; $i -le 10; $i++) {
    az network vnet peering create -g $rg -n "peer-hub-to-spoke$i" --vnet-name vnet-hub --remote-vnet "vnet-spoke$i" --allow-vnet-access true --allow-forwarded-traffic true --allow-gateway-transit true -o none
    az network vnet peering create -g $rg -n "peer-spoke$i-to-hub" --vnet-name "vnet-spoke$i" --remote-vnet vnet-hub --allow-vnet-access true --allow-forwarded-traffic true --use-remote-gateways true -o none
}

Write-Host "10. Creating Local Network Gateway and S2S VPN Connection (BGP enabled)..."
$onpremPip = az network public-ip show -g $rg -n pip-vm-onprem --query ipAddress -o tsv
$psk = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 24 | ForEach-Object {[char]$_})
az network local-gateway create -g $rg -n lng-onprem -l $loc --gateway-ip-address $onpremPip --local-address-prefixes 172.16.1.4/32 --asn 65010 --bgp-peering-address 172.16.1.4 -o none
az network vpn-connection create -g $rg -n conn-hub-onprem -l $loc --vnet-gateway1 vpngw-hub --local-gateway2 lng-onprem --shared-key $psk --enable-bgp true -o none

Write-Host "Deployment complete. Next: provision Megaport MCR + VXCs for er-circuit-hub and link ergw-hub via conn-hub-er."
