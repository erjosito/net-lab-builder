###############################################################################
# ExpressRoute circuits — one per region, Standard MeteredData via Megaport   #
###############################################################################

resource "azurerm_express_route_circuit" "circuit1" {
  name                     = local.er_circuit1_name
  location                 = var.location_a
  resource_group_name      = azurerm_resource_group.lab.name
  service_provider_name    = "Megaport"
  peering_location         = var.er_peering_location_a
  bandwidth_in_mbps        = var.er_bandwidth_mbps
  allow_classic_operations = false
  tags                     = local.common_tags

  sku {
    tier   = "Standard"
    family = "MeteredData"
  }
}

resource "azurerm_express_route_circuit" "circuit2" {
  name                     = local.er_circuit2_name
  location                 = var.location_b
  resource_group_name      = azurerm_resource_group.lab.name
  service_provider_name    = "Megaport"
  peering_location         = var.er_peering_location_b
  bandwidth_in_mbps        = var.er_bandwidth_mbps
  allow_classic_operations = false
  tags                     = local.common_tags

  sku {
    tier   = "Standard"
    family = "MeteredData"
  }
}

###############################################################################
# ExpressRoute gateways (hub-resident; deployed in each vHub)                 #
###############################################################################

resource "azurerm_express_route_gateway" "hub1" {
  name                = local.ergw1_name
  resource_group_name = azurerm_resource_group.lab.name
  location            = var.location_a
  virtual_hub_id      = azurerm_virtual_hub.hub1.id
  scale_units         = 1
  tags                = local.common_tags
}

resource "azurerm_express_route_gateway" "hub2" {
  name                = local.ergw2_name
  resource_group_name = azurerm_resource_group.lab.name
  location            = var.location_b
  virtual_hub_id      = azurerm_virtual_hub.hub2.id
  scale_units         = 1
  tags                = local.common_tags
}

###############################################################################
# ER gateway connections                                                      #
# Primary (always): hub1↔circuit1, hub2↔circuit2                              #
# Bow-tie (var-controlled, default off): hub1↔circuit2, hub2↔circuit1         #
#                                                                             #
# internet_security_enabled = true is required when routing-intent=private is  #
# in effect, so ER-learned routes flow through AzFW.                          #
#                                                                             #
# Megaport provider creates the private peering on each circuit as part of    #
# its azure_config block; we depend on the VXC resource so the peering exists #
# before the ER connection is created.                                        #
###############################################################################

resource "azurerm_express_route_connection" "hub1_circuit1" {
  name                             = local.ergw1_conn_primary_name
  express_route_gateway_id         = azurerm_express_route_gateway.hub1.id
  express_route_circuit_peering_id = "${azurerm_express_route_circuit.circuit1.id}/peerings/AzurePrivatePeering"
  internet_security_enabled         = true

  routing {
    associated_route_table_id = "${azurerm_virtual_hub.hub1.id}/hubRouteTables/defaultRouteTable"

    propagated_route_table {
      labels          = ["none"]
      route_table_ids = ["${azurerm_virtual_hub.hub1.id}/hubRouteTables/noneRouteTable"]
    }
  }

  depends_on = [
    megaport_vxc.azure_circuit1,
    azurerm_virtual_hub_routing_intent.hub1,
  ]
}

resource "azurerm_express_route_connection" "hub2_circuit2" {
  name                             = local.ergw2_conn_primary_name
  express_route_gateway_id         = azurerm_express_route_gateway.hub2.id
  express_route_circuit_peering_id = "${azurerm_express_route_circuit.circuit2.id}/peerings/AzurePrivatePeering"
  internet_security_enabled         = true

  routing {
    associated_route_table_id = "${azurerm_virtual_hub.hub2.id}/hubRouteTables/defaultRouteTable"
    outbound_route_map_id     = azurerm_route_map.hub2_out_blanket.id
    inbound_route_map_id      = azurerm_route_map.hub2_in_depref_gcp.id

    propagated_route_table {
      labels          = ["none"]
      route_table_ids = ["${azurerm_virtual_hub.hub2.id}/hubRouteTables/noneRouteTable"]
    }
  }

  depends_on = [
    megaport_vxc.azure_circuit2,
    azurerm_virtual_hub_routing_intent.hub2,
  ]
}

# Bow-tie — Niobe flips these vars for Scenario S4a
resource "azurerm_express_route_connection" "hub1_circuit2_bowtie" {
  count                            = var.er_bow_tie_hub1 ? 1 : 0
  name                             = local.ergw1_conn_bowtie_name
  express_route_gateway_id         = azurerm_express_route_gateway.hub1.id
  express_route_circuit_peering_id = "${azurerm_express_route_circuit.circuit2.id}/peerings/AzurePrivatePeering"
  internet_security_enabled         = true

  depends_on = [
    megaport_vxc.azure_circuit2,
    azurerm_virtual_hub_routing_intent.hub1,
  ]
}

resource "azurerm_express_route_connection" "hub2_circuit1_bowtie" {
  count                            = var.er_bow_tie_hub2 ? 1 : 0
  name                             = local.ergw2_conn_bowtie_name
  express_route_gateway_id         = azurerm_express_route_gateway.hub2.id
  express_route_circuit_peering_id = "${azurerm_express_route_circuit.circuit1.id}/peerings/AzurePrivatePeering"
  internet_security_enabled         = true

  depends_on = [
    megaport_vxc.azure_circuit1,
    azurerm_virtual_hub_routing_intent.hub2,
  ]
}

