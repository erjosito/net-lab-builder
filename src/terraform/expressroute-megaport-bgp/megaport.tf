data "megaport_location" "fra" {
  name = var.megaport_location
}

resource "megaport_mcr" "lab" {
  product_name         = local.mcr_name
  port_speed           = 1000
  location_id          = data.megaport_location.fra.id
  contract_term_months = 1
  asn                  = var.mcr_asn
  resource_tags        = local.common_tags

  lifecycle {
    ignore_changes = [prefix_filter_lists]
  }
}

resource "megaport_mcr_prefix_filter_list" "simulated_onprem" {
  mcr_id         = megaport_mcr.lab.product_uid
  description    = "${local.mcr_name}-simulated-onprem-export"
  address_family = "IPv4"

  entries = [
    {
      action = "permit"
      prefix = "172.31.100.0/24"
      ge     = 24
      le     = 24
    },
    {
      action = "permit"
      prefix = "172.31.101.1/32"
      ge     = 32
      le     = 32
    }
  ]
}

resource "megaport_vxc" "primary" {
  product_name         = local.vxc_primary_name
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

resource "megaport_vxc" "secondary" {
  product_name         = local.vxc_secondary_name
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
      port_choice = "secondary"
      service_key = azurerm_express_route_circuit.lab.service_key
      peers = [
        {
          type = "private"
        }
      ]
    }
  }
}

# TODO: configure 65031:100 on MCR-side BGP outbound if Megaport exposes community tagging in Terraform/API.
# The current provider exposes prefix filters and BGP import/export policy references, but not outbound community mutation.
