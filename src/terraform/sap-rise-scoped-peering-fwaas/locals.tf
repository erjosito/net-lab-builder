resource "random_id" "correlation" {
  byte_length = 4
}

locals {
  correlation_id = random_id.correlation.hex

  common_tags = merge(var.tags, {
    correlation_id = local.correlation_id
    run_id         = local.correlation_id
  })

  vm_size = var.use_vm_size_fallback ? var.vm_size_fallback : var.vm_size

  rg_name = "rg-${var.prefix}-${var.location}"

  hub_vnet_name        = "vnet-hub"
  spoke_vnet_name      = "vnet-sap-rise"
  onprem_sim_vnet_name = "vnet-onprem-sim"

  hub_nva_subnet_name    = "snet-hub-nva"
  spoke_nva_subnet_name  = "snet-spoke-nva"
  workload_subnet_name   = "snet-workload"
  onprem_sim_subnet_name = "snet-ce-onprem"

  nsg_hub_nva_name   = "nsg-hub-nva"
  nsg_spoke_nva_name = "nsg-spoke-nva"

  route_table_workload_name = "rt-spoke-workload"

  ars_name = "ars-hub"

  er_gateway_name     = "ergw-sap-rise"
  er_gateway_pip_name = "pip-ergw-sap-rise"
  er_circuit_name     = "er-sap-rise"
  er_connection_name  = "erconn-sap-rise"

  mcr_name = "mcr-saprise-${local.correlation_id}"
  vxc_name = "vxc-saprise-azure-${local.correlation_id}"

  vm_hub_nva_name   = "vm-hub-nva"
  vm_spoke_nva_name = "vm-spoke-nva"
  vm_workload_name  = "vm-workload-probe"
  vm_ce_onprem_name = "vm-ce-onprem"
}
