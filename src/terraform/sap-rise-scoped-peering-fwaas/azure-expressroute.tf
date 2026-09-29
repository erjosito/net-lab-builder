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

# NOTE: azurerm provider 4.81 forbids an explicitly-assigned public_ip_address_id on
# ExpressRoute-type gateways (Azure now always auto-assigns a HOBO Standard public IP for
# new ExpressRoute gateways). The azurerm_public_ip resource below is therefore NOT used by
# the gateway; kept removed to avoid an orphaned/unused resource. See:
# https://github.com/hashicorp/terraform-provider-azurerm/issues/31730

# ErGw1AZ per manifest.md section 3/7 (zone-redundant SKU; the manifest is authoritative
# over the skill's generic "Standard" default table).
resource "azurerm_virtual_network_gateway" "er" {
  name                = local.er_gateway_name
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
  type                = "ExpressRoute"
  sku                 = "ErGw1AZ"
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
    megaport_vxc.azure,
  ]
}
