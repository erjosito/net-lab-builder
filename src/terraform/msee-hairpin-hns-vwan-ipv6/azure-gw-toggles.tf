###############################################################################
# azapi patches — three silent-fail GW toggles (design §7, manifest R2)      #
#                                                                             #
# These properties are not yet exposed as native azurerm_* attributes in      #
# azurerm v4.x. azapi_update_resource patches the existing resources in-place #
# after they are created. Behavior is identical to native attribute.          #
#                                                                             #
# Toggle table:                                                               #
#   allow_virtual_wan_traffic   (HnS VNet GW) — accepts MSEE-reflected vWAN  #
#   allow_remote_vnet_traffic   (HnS VNet GW) — advertises peered spoke CIDRs#
#   allow_non_virtual_wan_traffic (vHub ER GW) — accepts non-vWAN ER routes  #
###############################################################################

# ---------------------------------------------------------------------------
# HnS ER GW — patch allowVirtualWanTraffic + allowRemoteVnetTraffic
# ---------------------------------------------------------------------------

resource "azapi_update_resource" "hns_er_gw_toggles" {
  type        = "Microsoft.Network/virtualNetworkGateways@2024-03-01"
  resource_id = azurerm_virtual_network_gateway.hns_er.id

  body = {
    properties = {
      allowVirtualWanTraffic = true
      allowRemoteVnetTraffic = true
    }
  }

  depends_on = [azurerm_virtual_network_gateway.hns_er]
}

# ---------------------------------------------------------------------------
# vHub ER GW — patch allowNonVirtualWanTraffic
# ---------------------------------------------------------------------------

resource "azapi_update_resource" "vhub_er_gw_toggles" {
  type        = "Microsoft.Network/expressRouteGateways@2024-03-01"
  resource_id = azurerm_express_route_gateway.vhub.id

  body = {
    properties = {
      allowNonVirtualWanTraffic = true
    }
  }

  depends_on = [azurerm_express_route_gateway.vhub]
}
