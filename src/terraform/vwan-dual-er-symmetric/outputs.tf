###############################################################################
# Identity / lab metadata                                                     #
###############################################################################

output "resource_group_name" {
  description = "Azure resource group name for the lab."
  value       = azurerm_resource_group.lab.name
}

output "correlation_id" {
  description = "8-character run correlation ID."
  value       = local.correlation_id
}

output "regions" {
  description = "Azure regions used."
  value = {
    region_a = var.location_a
    region_b = var.location_b
  }
}

output "vm_sizes_used" {
  description = "VM SKUs deployed per region (charter probe outputs)."
  value = {
    region_a = var.vm_size_region_a
    region_b = var.vm_size_region_b
  }
}

output "megaport_pops_used" {
  description = "Megaport PoP names actually used for MCR1 / MCR2."
  value = {
    mcr1 = var.megaport_location_a
    mcr2 = var.megaport_location_b
  }
}

###############################################################################
# vWAN / hubs / firewalls                                                     #
###############################################################################

output "vwan_id" {
  description = "Virtual WAN resource ID."
  value       = azurerm_virtual_wan.vwan.id
}

output "hub_ids" {
  description = "vHub resource IDs."
  value = {
    hub1 = azurerm_virtual_hub.hub1.id
    hub2 = azurerm_virtual_hub.hub2.id
  }
}

output "azfw_ids" {
  description = "Azure Firewall resource IDs (in-hub Standard)."
  value = {
    hub1 = azurerm_firewall.hub1.id
    hub2 = azurerm_firewall.hub2.id
  }
}

output "azfw_private_ips" {
  description = "Azure Firewall private IPs (vHub-resident)."
  value = {
    hub1 = try(azurerm_firewall.hub1.virtual_hub[0].private_ip_address, null)
    hub2 = try(azurerm_firewall.hub2.virtual_hub[0].private_ip_address, null)
  }
}

output "log_analytics_workspace_id" {
  description = "Log Analytics workspace ID for AzFW diagnostic logs (Niobe KQL target)."
  value       = azurerm_log_analytics_workspace.lab.id
}

###############################################################################
# ExpressRoute                                                                #
###############################################################################

output "er_circuit_ids" {
  description = "ExpressRoute circuit resource IDs."
  value = {
    circuit1 = azurerm_express_route_circuit.circuit1.id
    circuit2 = azurerm_express_route_circuit.circuit2.id
  }
}

output "er_service_keys" {
  description = "ExpressRoute service keys (sensitive — consumed by Megaport VXCs)."
  value = {
    circuit1 = azurerm_express_route_circuit.circuit1.service_key
    circuit2 = azurerm_express_route_circuit.circuit2.service_key
  }
  sensitive = true
}

output "er_gateway_ids" {
  description = "ExpressRoute gateway IDs (hub-resident)."
  value = {
    hub1 = azurerm_express_route_gateway.hub1.id
    hub2 = azurerm_express_route_gateway.hub2.id
  }
}

output "er_connections" {
  description = "ExpressRoute gateway connections (primary + optional bow-tie)."
  value = {
    hub1_circuit1        = azurerm_express_route_connection.hub1_circuit1.id
    hub2_circuit2        = azurerm_express_route_connection.hub2_circuit2.id
    hub1_circuit2_bowtie = try(azurerm_express_route_connection.hub1_circuit2_bowtie[0].id, null)
    hub2_circuit1_bowtie = try(azurerm_express_route_connection.hub2_circuit1_bowtie[0].id, null)
  }
}

###############################################################################
# Spokes / VMs                                                                #
###############################################################################

output "spoke_vm_ids" {
  description = "VM resource IDs keyed by spoke name."
  value       = { for k, v in azurerm_linux_virtual_machine.spoke : k => v.id }
}

output "spoke_vm_private_ips" {
  description = "VM private IPs keyed by spoke name (for Niobe traffic generation)."
  value       = { for k, v in azurerm_network_interface.spoke : k => v.private_ip_address }
}

output "spoke_vnet_ids" {
  description = "Spoke VNet resource IDs."
  value       = { for k, v in azurerm_virtual_network.spoke : k => v.id }
}

###############################################################################
# Megaport                                                                    #
###############################################################################

output "mcr_uids" {
  description = "Megaport MCR product UIDs."
  value = {
    mcr1 = megaport_mcr.mcr1.product_uid
    mcr2 = megaport_mcr.mcr2.product_uid
  }
}

output "megaport_vxc_uids" {
  description = "Megaport VXC product UIDs (6 total: 2 ER primary, 2 ER secondary, 2 GCP)."
  value = {
    azure_circuit1           = megaport_vxc.azure_circuit1.product_uid
    azure_circuit1_secondary = megaport_vxc.azure_circuit1_secondary.product_uid
    azure_circuit2           = megaport_vxc.azure_circuit2.product_uid
    azure_circuit2_secondary = megaport_vxc.azure_circuit2_secondary.product_uid
    gcp_a                    = megaport_vxc.gcp_a.product_uid
    gcp_b                    = megaport_vxc.gcp_b.product_uid
  }
}

output "megaport_prefix_filter_lists" {
  description = "MCR prefix-filter list IDs (Niobe inspects post-S4b)."
  value = {
    mcr1 = megaport_mcr_prefix_filter_list.mcr1_gcp_export.id
    mcr2 = megaport_mcr_prefix_filter_list.mcr2_gcp_export.id
  }
}

output "bgp_azure_circuit1" {
  description = "BGP summary for Azure VXC on Circuit1 primary (Megaport exposes IPs/VLAN)."
  value = {
    azure_ip = try(megaport_vxc.azure_circuit1.csp_connections[0].provider_ip_address, null)
    mcr_ip   = try(coalesce(megaport_vxc.azure_circuit1.csp_connections[0].customer_ip_address, megaport_vxc.azure_circuit1.csp_connections[0].customer_ip4_address), null)
    vlan     = try(megaport_vxc.azure_circuit1.csp_connections[0].vlan, null)
  }
}

output "bgp_azure_circuit1_secondary" {
  description = "BGP summary for Azure VXC on Circuit1 secondary."
  value = {
    azure_ip = try(megaport_vxc.azure_circuit1_secondary.csp_connections[0].provider_ip_address, null)
    mcr_ip   = try(coalesce(megaport_vxc.azure_circuit1_secondary.csp_connections[0].customer_ip_address, megaport_vxc.azure_circuit1_secondary.csp_connections[0].customer_ip4_address), null)
    vlan     = try(megaport_vxc.azure_circuit1_secondary.csp_connections[0].vlan, null)
  }
}

output "bgp_azure_circuit2" {
  description = "BGP summary for Azure VXC on Circuit2 primary."
  value = {
    azure_ip = try(megaport_vxc.azure_circuit2.csp_connections[0].provider_ip_address, null)
    mcr_ip   = try(coalesce(megaport_vxc.azure_circuit2.csp_connections[0].customer_ip_address, megaport_vxc.azure_circuit2.csp_connections[0].customer_ip4_address), null)
    vlan     = try(megaport_vxc.azure_circuit2.csp_connections[0].vlan, null)
  }
}

output "bgp_azure_circuit2_secondary" {
  description = "BGP summary for Azure VXC on Circuit2 secondary."
  value = {
    azure_ip = try(megaport_vxc.azure_circuit2_secondary.csp_connections[0].provider_ip_address, null)
    mcr_ip   = try(coalesce(megaport_vxc.azure_circuit2_secondary.csp_connections[0].customer_ip_address, megaport_vxc.azure_circuit2_secondary.csp_connections[0].customer_ip4_address), null)
    vlan     = try(megaport_vxc.azure_circuit2_secondary.csp_connections[0].vlan, null)
  }
}

###############################################################################
# GCP                                                                         #
###############################################################################

output "gcp_vpc_ids" {
  description = "GCP VPC resource IDs."
  value = {
    vpc_a = google_compute_network.vpc_a.id
    vpc_b = google_compute_network.vpc_b.id
  }
}

output "gcp_router_names" {
  description = "GCP Cloud Router names (for gcloud route inspection)."
  value = {
    router_a = google_compute_router.router_a.name
    router_b = google_compute_router.router_b.name
  }
}

output "gcp_attachment_pairing_keys" {
  description = "GCP Partner Interconnect pairing keys (Niobe diagnostic only; consumed by Megaport)."
  value = {
    att_a = google_compute_interconnect_attachment.att_a.pairing_key
    att_b = google_compute_interconnect_attachment.att_b.pairing_key
  }
  sensitive = true
}

output "gcp_vm_private_ips" {
  description = "GCP VM internal IPs."
  value = {
    vm_a = try(google_compute_instance.vm_a.network_interface[0].network_ip, null)
    vm_b = try(google_compute_instance.vm_b.network_interface[0].network_ip, null)
  }
}
