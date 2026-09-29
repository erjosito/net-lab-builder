data "megaport_location" "mcr" {
  name = var.megaport_location
}

resource "megaport_mcr" "lab" {
  product_name         = local.mcr_name
  port_speed           = 1000
  location_id          = data.megaport_location.mcr.id
  contract_term_months = 1
  asn                  = var.mcr_asn
  resource_tags        = local.common_tags

  lifecycle {
    ignore_changes = [prefix_filter_lists]
  }
}

# Single VXC per manifest.md section 3 (this lab is not a dual-ER-symmetry lab; one
# circuit is the locked scope).
resource "megaport_vxc" "azure" {
  product_name         = local.vxc_name
  rate_limit           = 50
  contract_term_months = 1
  resource_tags        = local.common_tags

  a_end = {
    requested_product_uid = megaport_mcr.lab.product_uid
  }

  b_end = {}

  b_end_partner_config = {
    partner = "azure"
    azure_config = {
      port_choice = "primary"
      service_key = azurerm_express_route_circuit.lab.service_key
      peers = [
        {
          type = "private"
        }
      ]
    }
  }
}
