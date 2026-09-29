# S2 toggle (design.md section 6.2, corrected placement): summarizedGatewayPrefixes is
# read only from the VNet that contains the gateway subnet/gateway - i.e. vnet-hub, NOT
# the spoke. azurerm's virtual_network resource does not yet expose this property
# (verified against the installed azurerm 4.74 provider schema), so it is applied via
# azapi_update_resource against the ARM property directly, gated behind
# var.enable_summarized_gateway_prefixes so S1 can be validated first with the property
# unset.

resource "azapi_update_resource" "hub_summarized_gateway_prefixes" {
  count       = var.enable_summarized_gateway_prefixes ? 1 : 0
  type        = "Microsoft.Network/virtualNetworks@2025-07-01"
  resource_id = azurerm_virtual_network.hub.id

  body = {
    properties = {
      summarizedGatewayPrefixes = var.summarized_gateway_prefixes
    }
  }

  depends_on = [azurerm_virtual_network_gateway_connection.er]
}
