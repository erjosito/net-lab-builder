resource "random_id" "correlation" {
  byte_length = 3
}

locals {
  correlation_id = var.correlation_id_override != "" ? var.correlation_id_override : random_id.correlation.hex

  common_tags = merge(var.tags, {
    correlation_id = local.correlation_id
  })

  # --- Resource names ----------------------------------------------------
  rg_name  = "rg-${var.lab_name}-${local.correlation_id}"
  vwan_name = "vwan-${var.lab_name}"

  hub1_name = "hub1-${var.location_a}"
  hub2_name = "hub2-${var.location_b}"

  azfw_policy_name = "azfwpol-${var.lab_name}"
  azfw1_name       = "azfw-hub1-${var.location_a}"
  azfw2_name       = "azfw-hub2-${var.location_b}"

  ergw1_name = "ergw-hub1"
  ergw2_name = "ergw-hub2"

  er_circuit1_name = "er-${var.lab_name}-${lower(replace(var.er_peering_location_a, " ", "-"))}"
  er_circuit2_name = "er-${var.lab_name}-${lower(replace(var.er_peering_location_b, " ", "-"))}"

  ergw1_conn_primary_name   = "hub1ergw-circuit1"
  ergw2_conn_primary_name   = "hub2ergw-circuit2"
  ergw1_conn_bowtie_name    = "hub1ergw-circuit2-bowtie"
  ergw2_conn_bowtie_name    = "hub2ergw-circuit1-bowtie"

  mcr1_name = "mcr1-${var.lab_name}-${local.correlation_id}"
  mcr2_name = "mcr2-${var.lab_name}-${local.correlation_id}"

  vxc1_azure_name           = "vxc-mcr1-circuit1-${local.correlation_id}"
  vxc2_azure_name           = "vxc-mcr2-circuit2-${local.correlation_id}"
  vxc1_azure_secondary_name = "vxc-mcr1-circuit1-secondary-${local.correlation_id}"
  vxc2_azure_secondary_name = "vxc-mcr2-circuit2-secondary-${local.correlation_id}"
  vxc1_gcp_name             = "vxc-mcr1-gcp-a-${local.correlation_id}"
  vxc2_gcp_name             = "vxc-mcr2-gcp-b-${local.correlation_id}"
  # P2 cross-region session names REMOVED in Design B — GLOBAL VPC handles cross-region routing

  # --- Spoke layout -----------------------------------------------------
  spokes = {
    spoke1 = {
      name        = "spoke1"
      location    = var.location_a
      cidr        = var.spoke1_cidr
      workload    = cidrsubnet(var.spoke1_cidr, var.spoke_workload_subnet_newbit, 0)
      vm_size     = var.vm_size_region_a
      hub_key     = "hub1"
    }
    spoke2 = {
      name     = "spoke2"
      location = var.location_a
      cidr     = var.spoke2_cidr
      workload = cidrsubnet(var.spoke2_cidr, var.spoke_workload_subnet_newbit, 0)
      vm_size  = var.vm_size_region_a
      hub_key  = "hub1"
    }
    spoke3 = {
      name     = "spoke3"
      location = var.location_b
      cidr     = var.spoke3_cidr
      workload = cidrsubnet(var.spoke3_cidr, var.spoke_workload_subnet_newbit, 0)
      vm_size  = var.vm_size_region_b
      hub_key  = "hub2"
    }
    spoke4 = {
      name     = "spoke4"
      location = var.location_b
      cidr     = var.spoke4_cidr
      workload = cidrsubnet(var.spoke4_cidr, var.spoke_workload_subnet_newbit, 0)
      vm_size  = var.vm_size_region_b
      hub_key  = "hub2"
    }
  }

  hub_ids = {
    hub1 = azurerm_virtual_hub.hub1.id
    hub2 = azurerm_virtual_hub.hub2.id
  }

  # --- MCR prefix-filter scope (Mechanism A — REMOVED in P1 Mech B swap) ----
  # mcr1_export_prefixes and mcr2_export_prefixes were used by the now-removed
  # megaport_mcr_prefix_filter_list resources. Isolation is now achieved by:
  # 1. GCP Cloud Router CUSTOM advertise mode (per-VPC subnet only).
  # 2. AS-path prepend=3 on cross-region sessions (P2 below).
  # var.mcr1_injected_prefixes / mcr2_injected_prefixes retained in variables.tf
  # as S4b perturbation documentation, but no longer wired to any resource.
}
