###############################################################################
# Outputs — Niobe handoff package                                             #
###############################################################################

output "resource_group_name" {
  description = "Lab resource group name (includes correlation_id)."
  value       = azurerm_resource_group.lab.name
}

output "correlation_id" {
  description = "6-char hex run correlation ID."
  value       = local.correlation_id
}

output "location" {
  description = "Azure region."
  value       = var.location
}

# ---------------------------------------------------------------------------
# ER Direct & Circuits
# ---------------------------------------------------------------------------

output "er_port_name" {
  description = "ER Direct port name."
  value       = azurerm_express_route_port.hairpin.name
}

output "er_port_id" {
  description = "ER Direct port resource ID."
  value       = azurerm_express_route_port.hairpin.id
}

output "er_circuit_name" {
  description = "ER circuit name (single circuit connected to both GWs for MSEE hairpin)."
  value       = azurerm_express_route_circuit.hairpin.name
}

output "er_circuit_id" {
  description = "ER circuit resource ID."
  value       = azurerm_express_route_circuit.hairpin.id
}

output "er_service_key" {
  description = "ER circuit service key."
  sensitive   = true
  value       = azurerm_express_route_circuit.hairpin.service_key
}

# ---------------------------------------------------------------------------
# ER Gateways
# ---------------------------------------------------------------------------

output "ergw_hns_id" {
  description = "HnS ER Gateway resource ID."
  value       = azurerm_virtual_network_gateway.hns_er.id
}

output "ergw_vhub_id" {
  description = "vHub ER Gateway resource ID."
  value       = azurerm_express_route_gateway.vhub.id
}

# ---------------------------------------------------------------------------
# VM IPs — primary Niobe targets
# ---------------------------------------------------------------------------

output "vm_hns_public_ip" {
  description = "HnS spoke VM public IPv4 (SSH access)."
  value       = azurerm_public_ip.hns_vm.ip_address
}

output "vm_hns_private_ipv4" {
  description = "HnS spoke VM private IPv4."
  value       = azurerm_network_interface.hns.private_ip_address
}

output "vm_hns_private_ipv6" {
  description = "HnS spoke VM private IPv6 (from NIC secondary config)."
  value       = try(azurerm_network_interface.hns.ip_configuration[1].private_ip_address, null)
}

output "vm_vwan_public_ip" {
  description = "vWAN spoke VM public IPv4 (SSH access)."
  value       = azurerm_public_ip.vwan_vm.ip_address
}

output "vm_vwan_private_ipv4" {
  description = "vWAN spoke VM private IPv4."
  value       = azurerm_network_interface.vwan.private_ip_address
}

output "vm_vwan_private_ipv6" {
  description = "vWAN spoke VM private IPv6 (from NIC secondary config)."
  value       = try(azurerm_network_interface.vwan.ip_configuration[1].private_ip_address, null)
}

# ---------------------------------------------------------------------------
# Hub / vWAN IDs (for Niobe diagnostic commands)
# ---------------------------------------------------------------------------

output "vwan_id" {
  description = "Virtual WAN resource ID."
  value       = azurerm_virtual_wan.hairpin.id
}

output "vhub_id" {
  description = "Virtual Hub resource ID."
  value       = azurerm_virtual_hub.hairpin.id
}

output "tenant_id" {
  description = "Tenant ID (from caller context)."
  value       = data.azurerm_client_config.current.tenant_id
}
