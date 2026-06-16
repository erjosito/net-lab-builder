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
# P1 (2026-06-15): Mechanism A prefix-filter lists REMOVED — Mech B swap.    #
# megaport_mcr_prefix_filter_list.mcr1_gcp_export + .mcr2_gcp_export deleted.#
# GCP Cloud Router CUSTOM advertise mode (per-VPC subnet only) remains the   #
# authoritative isolation lever for GCP→Azure direction.                      #
# AS-path prepend for automatic failover is applied per-session on cross-     #
# region GCP VXCs (P2 below): `as_path_prepend_count = 3` on MCR2→VPC-A and  #
# MCR1→VPC-B sessions makes them always-inferior to the native sessions.      #
# Standalone prepend-policy resource does not exist in megaport 1.10.1;      #
# fallback: a_end_partner_config.vrouter_config.bgp_connections.              #
###############################################################################

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

###############################################################################
# Design C (2026-06-15): megaport_vxc.gcp_b REMOVED from TF code.           #
# The old VXC (vxc-mcr2-gcp-b-103167, UID 2c2fd022-b0ce-438a-aee9-69f27daa43a2) #
# was deleted via Megaport portal by Jose. New VXC on mcr2→europe-west3 was  #
# created via portal (pairing key 326ba0de-2aed-4eb2-aaf4-2df34108dc07/      #
# europe-west3/2). TF state removed via `terraform state rm megaport_vxc.gcp_b`. #
# Re-import as megaport_vxc.gcp_b_v2 once Megaport API is unlocked.         #
###############################################################################
# Design B (2026-06-15): Cross-region GCP sessions REMOVED.                   #
# gcp_a2 (MCR2→VPC-A) and gcp_b2 (MCR1→VPC-B) were Design A P2 failover     #
# VXCs. In Design B the single GLOBAL-routing vpc_a provides automatic        #
# cross-region routing; separate cross-region VXCs are no longer needed.      #
# Axis-2 MCR→Azure prepend (10.50.2.0/24 3× on circuit1, 10.50.1.0/24 3×    #
# on circuit2) deferred: Megaport TF provider 1.10.1 has no per-prefix        #
# AS-path prepend schema. Implement via Megaport MCR route policy API/portal. #
###############################################################################
