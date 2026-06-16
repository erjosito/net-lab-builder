###############################################################################
# Resource Group                                                              #
###############################################################################

resource "azurerm_resource_group" "lab" {
  name     = local.rg_name
  location = var.location
  tags     = local.common_tags
}

###############################################################################
# ER Direct Port — 10 Gbps, Stockholm, Dot1Q                                  #
#                                                                             #
# Port is free for 45 days from provisioning (Azure bring-up window).         #
# Billing (~$47/day) begins at day 46. TF destroy order: circuits first.      #
###############################################################################

resource "azurerm_express_route_port" "hairpin" {
  name                = local.er_port_name
  resource_group_name = azurerm_resource_group.lab.name
  location            = var.location
  peering_location    = var.er_port_peering_location
  bandwidth_in_gbps   = 10
  encapsulation       = "Dot1Q"
  tags                = local.common_tags
}

###############################################################################
# ER Circuit — single circuit on the ER Direct port, connected to BOTH GWs    #
#                                                                             #
# MSEE hairpinning requires the SAME circuit connected to both ER gateways.   #
# The MSEE reflects routes between the two connections on the same circuit.   #
###############################################################################

resource "azurerm_express_route_circuit" "hairpin" {
  name                  = local.er_circuit_name
  resource_group_name   = azurerm_resource_group.lab.name
  location              = var.location
  express_route_port_id = azurerm_express_route_port.hairpin.id
  bandwidth_in_gbps     = 1
  tags                  = local.common_tags

  sku {
    tier   = "Local"
    family = "MeteredData"
  }
}

###############################################################################
# ER Circuit Peering — single private peering (IPv4 + IPv6)                   #
#                                                                             #
# Both the HnS ER GW and vWAN ER GW connect to this same peering.            #
# The MSEE reflects routes between the two gateway connections.               #
###############################################################################

resource "azurerm_express_route_circuit_peering" "hairpin" {
  resource_group_name           = azurerm_resource_group.lab.name
  express_route_circuit_name    = azurerm_express_route_circuit.hairpin.name
  peering_type                  = "AzurePrivatePeering"
  peer_asn                      = 65001
  vlan_id                       = 100
  primary_peer_address_prefix   = "172.16.1.0/30"
  secondary_peer_address_prefix = "172.16.1.4/30"

  ipv6 {
    primary_peer_address_prefix   = "fd00:f:1::/126"
    secondary_peer_address_prefix = "fd00:f:1::4/126"
    enabled                       = true
  }
}
