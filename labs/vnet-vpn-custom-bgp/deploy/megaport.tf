data "megaport_partner" "gcp" {
  count          = var.deploy_megaport ? 1 : 0
  connect_type   = "GOOGLE"
  location_id    = 98
  product_name   = "Stockholm (arn-zone1-208)"
  diversity_zone = "red"
}

resource "megaport_mcr" "lab" {
  count                = var.deploy_megaport ? 1 : 0
  product_name         = "jomore-${local.prefix}-mcr"
  port_speed           = 1000
  location_id          = 85
  contract_term_months = 1
  asn                  = 65060
  resource_tags        = local.tags
}

resource "megaport_vxc" "azure" {
  for_each             = var.deploy_megaport ? toset(["primary", "secondary"]) : toset([])
  product_name         = "jomore-${local.prefix}-azure-${each.key}"
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
      port_choice = each.key
      service_key = azurerm_express_route_circuit.lab.service_key
      peers       = [{ type = "private" }]
    }
  }
}

resource "megaport_vxc" "gcp" {
  count                = var.deploy_megaport ? 1 : 0
  product_name         = "jomore-${local.prefix}-gcp"
  rate_limit           = 50
  contract_term_months = 1
  resource_tags        = local.tags
  a_end = {
    requested_product_uid = megaport_mcr.lab[0].product_uid
  }
  b_end = {
    requested_product_uid = data.megaport_partner.gcp[0].product_uid
  }
  b_end_partner_config = {
    partner = "google"
    google_config = {
      pairing_key = google_compute_interconnect_attachment.lab.pairing_key
    }
  }
}
