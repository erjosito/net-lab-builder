output "resource_group_name" {
  description = "Azure resource group name."
  value       = azurerm_resource_group.lab.name
}

output "vnet_id" {
  description = "Azure VNet resource ID."
  value       = azurerm_virtual_network.lab.id
}

output "expressroute_circuit_id" {
  description = "ExpressRoute circuit resource ID."
  value       = azurerm_express_route_circuit.lab.id
}

output "expressroute_service_key" {
  description = "ExpressRoute service key consumed by Megaport."
  value       = azurerm_express_route_circuit.lab.service_key
  sensitive   = true
}

output "expressroute_gateway_name" {
  description = "ExpressRoute virtual network gateway name."
  value       = azurerm_virtual_network_gateway.er.name
}

output "expressroute_connection_name" {
  description = "ExpressRoute gateway connection name."
  value       = azurerm_virtual_network_gateway_connection.er.name
}

output "megaport_mcr_uid" {
  description = "Megaport MCR product UID."
  value       = megaport_mcr.lab.product_uid
}

output "megaport_vxc_primary_uid" {
  description = "Primary Megaport Azure VXC product UID."
  value       = megaport_vxc.primary.product_uid
}

output "megaport_vxc_secondary_uid" {
  description = "Secondary Megaport Azure VXC product UID."
  value       = megaport_vxc.secondary.product_uid
}

output "vm_public_ip" {
  description = "Linux validation VM public IP address."
  value       = azurerm_public_ip.vm.ip_address
}

output "vm_admin_user" {
  description = "Linux validation VM admin username."
  value       = var.admin_username
}

output "vm_name" {
  description = "Linux validation VM name."
  value       = azurerm_linux_virtual_machine.test.name
}

output "vm_nic_id" {
  description = "Linux validation VM NIC resource ID."
  value       = azurerm_network_interface.vm.id
}

output "bgp_primary" {
  description = "Primary VXC BGP summary from Megaport CSP connection fields, where exposed by the provider."
  value = {
    azure_ip  = try(megaport_vxc.primary.csp_connections[0].provider_ip_address, null)
    mcr_ip    = try(coalesce(megaport_vxc.primary.csp_connections[0].customer_ip_address, megaport_vxc.primary.csp_connections[0].customer_ip4_address), null)
    azure_asn = 12076
    mcr_asn   = var.mcr_asn
    vlan      = try(megaport_vxc.primary.csp_connections[0].vlan, null)
  }
}

output "bgp_secondary" {
  description = "Secondary VXC BGP summary from Megaport CSP connection fields, where exposed by the provider."
  value = {
    azure_ip  = try(megaport_vxc.secondary.csp_connections[0].provider_ip_address, null)
    mcr_ip    = try(coalesce(megaport_vxc.secondary.csp_connections[0].customer_ip_address, megaport_vxc.secondary.csp_connections[0].customer_ip4_address), null)
    azure_asn = 12076
    mcr_asn   = var.mcr_asn
    vlan      = try(megaport_vxc.secondary.csp_connections[0].vlan, null)
  }
}

output "tags_correlation_id" {
  description = "8-character run correlation ID applied as a tag."
  value       = local.correlation_id
}
