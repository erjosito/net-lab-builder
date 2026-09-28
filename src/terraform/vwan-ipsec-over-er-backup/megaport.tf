data "megaport_location" "stockholm" {
  name = var.megaport_location
}

resource "megaport_mcr" "lab" {
  count                = var.deploy_megaport ? 1 : 0
  product_name         = "mcr-${local.prefix}"
  port_speed           = 1000
  location_id          = data.megaport_location.stockholm.id
  contract_term_months = 1
  asn                  = var.mcr_asn
  resource_tags        = local.tags
}

resource "megaport_vxc" "azure_primary" {
  count                = var.deploy_megaport ? 1 : 0
  product_name         = "vxc-azure-primary-${local.prefix}"
  rate_limit           = 50
  contract_term_months = 1
  resource_tags        = local.tags

  a_end = {
    requested_product_uid = megaport_mcr.lab[0].product_uid
  }
  b_end = {}
  b_end_partner_config = {
    partner = "azure"
    azure_config = {
      port_choice = "primary"
      service_key = azurerm_express_route_circuit.lab.service_key
      peers       = [{ type = "private" }]
    }
  }
}

resource "megaport_vxc" "azure_secondary" {
  count                = var.deploy_megaport ? 1 : 0
  product_name         = "vxc-azure-secondary-${local.prefix}"
  rate_limit           = 50
  contract_term_months = 1
  resource_tags        = local.tags

  a_end = {
    requested_product_uid = megaport_mcr.lab[0].product_uid
  }
  b_end = {}
  b_end_partner_config = {
    partner = "azure"
    azure_config = {
      port_choice = "secondary"
      service_key = azurerm_express_route_circuit.lab.service_key
      peers       = [{ type = "private" }]
    }
  }
}

resource "megaport_vxc" "gcp" {
  count                = var.deploy_megaport ? 1 : 0
  product_name         = "vxc-gcp-${local.prefix}"
  rate_limit           = 50
  contract_term_months = 1
  resource_tags        = local.tags

  a_end = {
    requested_product_uid = megaport_mcr.lab[0].product_uid
  }
  b_end = {}
  b_end_partner_config = {
    partner = "google"
    google_config = {
      pairing_key = google_compute_interconnect_attachment.lab.pairing_key
    }
  }
}

resource "azurerm_express_route_connection" "lab" {
  count                            = var.deploy_megaport ? 1 : 0
  name                             = "conn-er"
  express_route_gateway_id         = azurerm_express_route_gateway.lab.id
  express_route_circuit_peering_id = "${azurerm_express_route_circuit.lab.id}/peerings/AzurePrivatePeering"
  internet_security_enabled        = false

  depends_on = [
    megaport_vxc.azure_primary,
    megaport_vxc.azure_secondary,
    megaport_vxc.gcp
  ]
}
