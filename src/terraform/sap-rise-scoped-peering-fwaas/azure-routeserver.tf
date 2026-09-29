# Azure Route Server per design.md section 6.1. Always deployed (fixed cost line item,
# ~$10.80/day per manifest section 6); the S1/S2 scenario toggle is applied at the
# BIRD-config layer on the hub NVA (post-deploy, via deploy.ps1 / az vm run-command), not
# by conditionally creating/destroying ARS itself.

resource "azurerm_route_server" "hub" {
  name                             = local.ars_name
  location                         = azurerm_resource_group.lab.location
  resource_group_name              = azurerm_resource_group.lab.name
  sku                              = "Standard"
  subnet_id                        = azurerm_subnet.routeserver.id
  public_ip_address_id             = azurerm_public_ip.ars.id
  branch_to_branch_traffic_enabled = false
  tags                             = local.common_tags
}

resource "azurerm_public_ip" "ars" {
  name                = "pip-ars-hub"
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = local.common_tags

  lifecycle {
    ignore_changes = [ip_tags, zones]
  }
}

resource "azurerm_route_server_bgp_connection" "hub_nva" {
  name            = "ars-hub-nva-peering"
  route_server_id = azurerm_route_server.hub.id
  peer_asn        = var.hub_nva_asn
  peer_ip         = var.hub_nva_private_ip

  depends_on = [azurerm_network_interface.hub_nva]
}
