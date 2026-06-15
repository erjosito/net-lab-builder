###############################################################################
# Megaport MCRs — one per region (PoP)                                        #
###############################################################################

resource "megaport_mcr" "mcr1" {
  product_name         = local.mcr1_name
  port_speed           = 1000
  location_id          = data.megaport_location.loc_a.id
  contract_term_months = 1
  asn                  = var.mcr1_asn
  resource_tags        = local.common_tags

  lifecycle {
    ignore_changes = [prefix_filter_lists]
  }
}

resource "megaport_mcr" "mcr2" {
  product_name         = local.mcr2_name
  port_speed           = 1000
  location_id          = data.megaport_location.loc_b.id
  contract_term_months = 1
  asn                  = var.mcr2_asn
  resource_tags        = local.common_tags

  lifecycle {
    ignore_changes = [prefix_filter_lists]
  }
}

###############################################################################
# Prefix-filter lists (Mechanism A — per-region GCP /24)                      #
# MCR1 permits only Region A's GCP /24 by default; injected_prefixes appends. #
###############################################################################

resource "megaport_mcr_prefix_filter_list" "mcr1_gcp_export" {
  mcr_id         = megaport_mcr.mcr1.product_uid
  description    = "${local.mcr1_name}-gcp-export"
  address_family = "IPv4"

  entries = [
    for p in local.mcr1_export_prefixes : {
      action = "permit"
      prefix = p
      ge     = tonumber(split("/", p)[1])
      le     = tonumber(split("/", p)[1])
    }
  ]
}

resource "megaport_mcr_prefix_filter_list" "mcr2_gcp_export" {
  mcr_id         = megaport_mcr.mcr2.product_uid
  description    = "${local.mcr2_name}-gcp-export"
  address_family = "IPv4"

  entries = [
    for p in local.mcr2_export_prefixes : {
      action = "permit"
      prefix = p
      ge     = tonumber(split("/", p)[1])
      le     = tonumber(split("/", p)[1])
    }
  ]
}

###############################################################################
# Azure VXCs — TWO per MCR/circuit pair (primary + secondary MSEE port)      #
# Both port_choice values must be wired for full HA + dual BGP sessions.      #
###############################################################################

resource "megaport_vxc" "azure_circuit1" {
  product_name         = local.vxc1_azure_name
  rate_limit           = var.er_bandwidth_mbps
  contract_term_months = 1
  resource_tags        = local.common_tags

  a_end = {
    requested_product_uid = megaport_mcr.mcr1.product_uid
  }

  b_end = {}

  b_end_partner_config = {
    partner = "azure"
    azure_config = {
      port_choice = "primary"
      service_key = azurerm_express_route_circuit.circuit1.service_key
      peers = [
        {
          type = "private"
        }
      ]
    }
  }
}

resource "megaport_vxc" "azure_circuit1_secondary" {
  product_name         = local.vxc1_azure_secondary_name
  rate_limit           = var.er_bandwidth_mbps
  contract_term_months = 1
  resource_tags        = local.common_tags

  a_end = {
    requested_product_uid = megaport_mcr.mcr1.product_uid
  }

  b_end = {}

  b_end_partner_config = {
    partner = "azure"
    azure_config = {
      port_choice = "secondary"
      service_key = azurerm_express_route_circuit.circuit1.service_key
      peers = [
        {
          type = "private"
        }
      ]
    }
  }
}

resource "megaport_vxc" "azure_circuit2" {
  product_name         = local.vxc2_azure_name
  rate_limit           = var.er_bandwidth_mbps
  contract_term_months = 1
  resource_tags        = local.common_tags

  a_end = {
    requested_product_uid = megaport_mcr.mcr2.product_uid
  }

  b_end = {}

  b_end_partner_config = {
    partner = "azure"
    azure_config = {
      port_choice = "primary"
      service_key = azurerm_express_route_circuit.circuit2.service_key
      peers = [
        {
          type = "private"
        }
      ]
    }
  }
}

resource "megaport_vxc" "azure_circuit2_secondary" {
  product_name         = local.vxc2_azure_secondary_name
  rate_limit           = var.er_bandwidth_mbps
  contract_term_months = 1
  resource_tags        = local.common_tags

  a_end = {
    requested_product_uid = megaport_mcr.mcr2.product_uid
  }

  b_end = {}

  b_end_partner_config = {
    partner = "azure"
    azure_config = {
      port_choice = "secondary"
      service_key = azurerm_express_route_circuit.circuit2.service_key
      peers = [
        {
          type = "private"
        }
      ]
    }
  }
}

###############################################################################
# GCP VXCs — one per MCR / Partner Interconnect attachment                    #
# Pairing key flows: GCP attachment.pairing_key → Megaport VXC google_config  #
###############################################################################

resource "megaport_vxc" "gcp_a" {
  product_name         = local.vxc1_gcp_name
  rate_limit           = var.er_bandwidth_mbps
  contract_term_months = 1
  resource_tags        = local.common_tags

  a_end = {
    requested_product_uid = megaport_mcr.mcr1.product_uid
  }

  b_end = {}

  b_end_partner_config = {
    partner = "google"
    google_config = {
      pairing_key = google_compute_interconnect_attachment.att_a.pairing_key
    }
  }
}

resource "megaport_vxc" "gcp_b" {
  product_name         = local.vxc2_gcp_name
  rate_limit           = var.er_bandwidth_mbps
  contract_term_months = 1
  resource_tags        = local.common_tags

  a_end = {
    requested_product_uid = megaport_mcr.mcr2.product_uid
  }

  b_end = {}

  b_end_partner_config = {
    partner = "google"
    google_config = {
      pairing_key = google_compute_interconnect_attachment.att_b.pairing_key
    }
  }
}
