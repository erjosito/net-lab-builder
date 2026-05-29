resource "random_id" "correlation" {
  byte_length = 4
}

locals {
  correlation_id = random_id.correlation.hex

  common_tags = merge(var.tags, {
    correlation_id = local.correlation_id
  })

  rg_name              = "rg-${var.prefix}-${var.location}"
  vnet_name            = "vnet-${var.prefix}-${var.location}"
  workload_subnet_name = "snet-${var.prefix}-workload"
  nsg_name             = "nsg-${var.prefix}-workload"
  vm_public_ip_name    = "pip-${var.prefix}-vm"
  vm_nic_name          = "nic-${var.prefix}-vm"
  vm_name              = "vm-${var.prefix}-test"
  er_circuit_name      = "er-${var.prefix}-madrid"
  er_gateway_pip_name  = "pip-${var.prefix}-ergw"
  er_gateway_name      = "ergw-${var.prefix}-${var.location}"
  er_connection_name   = "erconn-${var.prefix}"
  mcr_name             = "mcr-${var.prefix}-frankfurt-${local.correlation_id}"
  vxc_primary_name     = "vxc-${var.prefix}-azure-primary-${local.correlation_id}"
  vxc_secondary_name   = "vxc-${var.prefix}-azure-secondary-${local.correlation_id}"
}
