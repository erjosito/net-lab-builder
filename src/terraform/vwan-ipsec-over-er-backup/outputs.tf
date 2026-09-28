output "resource_group_name" {
  value = azurerm_resource_group.lab.name
}

output "vwan_name" {
  value = azurerm_virtual_wan.lab.name
}

output "vhub_name" {
  value = azurerm_virtual_hub.lab.name
}

output "vpn_gateway_name" {
  value = azurerm_vpn_gateway.lab.name
}

output "er_circuit_name" {
  value = azurerm_express_route_circuit.lab.name
}

output "gcp_project_id" {
  value = var.gcp_project_id
}

output "gcp_cpe_name" {
  value = google_compute_instance.cpe.name
}

output "gcp_cpe_public_ip" {
  value = google_compute_address.cpe.address
}

output "gcp_router_name" {
  value = google_compute_router.lab.name
}

output "gcp_attachment_name" {
  value = google_compute_interconnect_attachment.lab.name
}

output "mcr_uid" {
  value = try(megaport_mcr.lab[0].product_uid, null)
}

output "vxc_uids" {
  value = {
    azure_primary   = try(megaport_vxc.azure_primary[0].product_uid, null)
    azure_secondary = try(megaport_vxc.azure_secondary[0].product_uid, null)
    gcp             = try(megaport_vxc.gcp[0].product_uid, null)
  }
}

output "sensitive_generated_keys" {
  sensitive = true
  value = {
    er_service_key  = azurerm_express_route_circuit.lab.service_key
    gcp_pairing_key = google_compute_interconnect_attachment.lab.pairing_key
  }
}
