resource "random_id" "correlation" {
  byte_length = 3
}

locals {
  correlation_id = var.correlation_id_override != "" ? var.correlation_id_override : random_id.correlation.hex

  rg_name = "rg-${var.lab_name}-${local.correlation_id}"

  common_tags = {
    lab            = "msee-hairpin-hns-vwan-ipv6"
    lab_id         = "msee-hairpin-${local.correlation_id}"
    owner          = "jose"
    ephemeral      = "true"
    created_by     = "copilot-lab"
    correlation_id = local.correlation_id
  }

  # Naming prefixes
  suffix = local.correlation_id

  # ER Direct & circuit (single circuit — MSEE hairpins between both GW connections)
  er_port_name      = "erp-hairpin-${local.suffix}"
  er_circuit_name   = "er-hns-${local.suffix}"  # kept as-is from initial deploy

  # HnS layer
  vnet_hns_hub_name   = "vnet-hns-hub-${local.suffix}"
  vnet_hns_spoke_name = "vnet-hns-spoke-${local.suffix}"
  pip_ergw_hns_name   = "pip-ergw-hns-${local.suffix}"
  ergw_hns_name        = "ergw-hns-${local.suffix}"
  conn_hns_name        = "conn-hns-${local.suffix}"
  nsg_hns_name         = "nsg-hns-${local.suffix}"
  pip_hns_name         = "pip-hns-${local.suffix}"
  nic_hns_name         = "nic-hns-${local.suffix}"
  vm_hns_name          = "vm-hns-${local.suffix}"

  # vWAN layer
  vwan_name          = "vwan-hairpin-${local.suffix}"
  vhub_name          = "vhub-hairpin-${local.suffix}"
  ergw_vhub_name     = "ergw-vhub-${local.suffix}"
  conn_vhub_er_name  = "conn-vhub-er-${local.suffix}"
  vnet_vwan_name     = "vnet-vwan-spoke-${local.suffix}"
  conn_vhub_vnet_name = "conn-vhub-vnet-${local.suffix}"
  nsg_vwan_name      = "nsg-vwan-${local.suffix}"
  pip_vwan_name      = "pip-vwan-${local.suffix}"
  nic_vwan_name      = "nic-vwan-${local.suffix}"
  vm_vwan_name       = "vm-vwan-${local.suffix}"
}
