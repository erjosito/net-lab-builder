resource "azurerm_express_route_circuit" "lab" {
  name                     = local.er_circuit_name
  location                 = azurerm_resource_group.lab.location
  resource_group_name      = azurerm_resource_group.lab.name
  service_provider_name    = "Megaport"
  peering_location         = var.expressroute_peering_location
  bandwidth_in_mbps        = 50
  allow_classic_operations = false
  tags                     = local.common_tags

  sku {
    tier   = "Standard"
    family = "MeteredData"
  }
}

resource "azurerm_public_ip" "ergw" {
  name                = local.er_gateway_pip_name
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = local.common_tags

  lifecycle {
    ignore_changes = [ip_tags, zones]
  }
}

resource "azurerm_virtual_network_gateway" "er" {
  name                = local.er_gateway_name
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
  type                = "ExpressRoute"
  sku                 = "Standard"
  tags                = local.common_tags

  ip_configuration {
    name                          = "er-gateway-ipconfig"
    private_ip_address_allocation = "Dynamic"
    subnet_id                     = azurerm_subnet.gateway.id
  }
}

resource "azurerm_virtual_network_gateway_connection" "er" {
  name                       = local.er_connection_name
  location                   = azurerm_resource_group.lab.location
  resource_group_name        = azurerm_resource_group.lab.name
  type                       = "ExpressRoute"
  virtual_network_gateway_id = azurerm_virtual_network_gateway.er.id
  express_route_circuit_id   = azurerm_express_route_circuit.lab.id
  tags                       = local.common_tags

  depends_on = [
    megaport_vxc.primary,
    megaport_vxc.secondary,
  ]
}
