variable "overlay_stage" {
  type    = string
  default = "none"
  validation {
    condition     = contains(["none", "internet", "private", "backup"], var.overlay_stage)
    error_message = "Choose none, internet, private or backup."
  }
}

variable "vpn_psks" {
  type      = map(string)
  sensitive = true
  default   = {}
}

variable "retain_internet_static" {
  type    = bool
  default = false
}

locals {
  overlay_connections = var.overlay_stage == "none" ? toset([]) : (
    var.overlay_stage == "internet" ? toset(["internet"]) : toset(["internet", "private"])
  )
}

data "google_compute_address" "overlay_cpe" {
  name    = "pip-${local.prefix}"
  project = local.gcp_project
  region  = "europe-north2"
}

resource "azurerm_local_network_gateway" "cpe" {
  for_each            = local.overlay_connections
  name                = "lng-${each.key}-${local.prefix}"
  resource_group_name = azurerm_resource_group.lab.name
  location            = local.location
  gateway_address     = each.key == "internet" ? data.google_compute_address.overlay_cpe.address : "10.245.0.10"
  address_space       = each.key == "internet" && (var.overlay_stage == "internet" || var.retain_internet_static) ? ["10.246.1.0/24"] : []
  tags                = local.tags

  dynamic "bgp_settings" {
    for_each = each.key == "private" || var.overlay_stage == "backup" ? [1] : []
    content {
      asn                 = 64513
      bgp_peering_address = each.key == "internet" ? "169.254.21.1" : "10.245.254.6"
    }
  }
}

resource "azurerm_virtual_network_gateway_connection" "overlay" {
  for_each                       = local.overlay_connections
  name                           = "conn-${each.key}-${local.prefix}"
  resource_group_name            = azurerm_resource_group.lab.name
  location                       = local.location
  type                           = "IPsec"
  virtual_network_gateway_id     = azurerm_virtual_network_gateway.vpn.id
  local_network_gateway_id       = azurerm_local_network_gateway.cpe[each.key].id
  shared_key                     = var.vpn_psks[each.key]
  bgp_enabled                    = each.key == "private" || var.overlay_stage == "backup"
  local_azure_ip_address_enabled = each.key == "private"
  connection_protocol            = "IKEv2"
  connection_mode                = "Default"
  dpd_timeout_seconds            = 45
  tags                           = local.tags

  dynamic "custom_bgp_addresses" {
    for_each = each.key == "internet" && var.overlay_stage == "backup" ? [1] : []
    content {
      primary   = "169.254.21.2"
      secondary = "169.254.22.2"
    }
  }
}
