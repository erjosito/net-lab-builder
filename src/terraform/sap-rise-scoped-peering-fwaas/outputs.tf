output "resource_group_name" {
  value = azurerm_resource_group.lab.name
}

output "location" {
  value = var.location
}

output "hub_vnet_id" {
  value = azurerm_virtual_network.hub.id
}

output "spoke_vnet_id" {
  value = azurerm_virtual_network.spoke.id
}

output "onprem_sim_vnet_id" {
  value = azurerm_virtual_network.onprem_sim.id
}

output "er_gateway_name" {
  value = azurerm_virtual_network_gateway.er.name
}

# Azure auto-assigns ("HOBO") the public IP for ExpressRoute-type gateways; it is not a
# managed azurerm_public_ip resource, so it isn't directly readable from state. Look it up
# post-deploy with: az network vnet-gateway list-bgp-peer-status / az network public-ip list.
output "er_gateway_public_ip" {
  value = "auto-assigned by Azure (HOBO); query with 'az network public-ip list -g <rg> --query \"[?contains(id,'ergw')]\"' or the gateway's effective IP configuration"
}

output "er_circuit_name" {
  value = azurerm_express_route_circuit.lab.name
}

output "er_circuit_service_key" {
  value     = azurerm_express_route_circuit.lab.service_key
  sensitive = true
}

output "route_server_name" {
  value = azurerm_route_server.hub.name
}

output "route_server_id" {
  value = azurerm_route_server.hub.id
}

output "megaport_mcr_uid" {
  value = megaport_mcr.lab.product_uid
}

output "megaport_vxc_uid" {
  value = megaport_vxc.azure.product_uid
}

output "megaport_bgp" {
  value = {
    azure_ip  = try(megaport_vxc.azure.csp_connections[0].provider_ip_address, null)
    mcr_ip    = try(coalesce(megaport_vxc.azure.csp_connections[0].customer_ip_address, megaport_vxc.azure.csp_connections[0].customer_ip4_address), null)
    azure_asn = 12076
    mcr_asn   = var.mcr_asn
    vlan      = try(megaport_vxc.azure.csp_connections[0].vlan, null)
  }
}

output "vm_hub_nva_name" {
  value = azurerm_linux_virtual_machine.hub_nva.name
}

output "vm_hub_nva_private_ip" {
  value = azurerm_network_interface.hub_nva.private_ip_address
}

output "vm_spoke_nva_name" {
  value = azurerm_linux_virtual_machine.spoke_nva.name
}

output "vm_spoke_nva_private_ip" {
  value = azurerm_network_interface.spoke_nva.private_ip_address
}

output "vm_workload_probe_name" {
  value = azurerm_linux_virtual_machine.workload_probe.name
}

output "vm_workload_probe_private_ip" {
  value = azurerm_network_interface.workload_probe.private_ip_address
}

output "vm_ce_onprem_name" {
  value = azurerm_linux_virtual_machine.ce_onprem.name
}

output "vm_ce_onprem_private_ip" {
  value = azurerm_network_interface.ce_onprem.private_ip_address
}

output "tags_correlation_id" {
  value = local.correlation_id
}

output "enable_summarized_gateway_prefixes" {
  value = var.enable_summarized_gateway_prefixes
}
