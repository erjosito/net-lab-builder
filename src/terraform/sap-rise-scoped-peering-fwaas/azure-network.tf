resource "azurerm_resource_group" "lab" {
  name     = local.rg_name
  location = var.location
  tags     = local.common_tags
}

# --- vnet-hub ---

resource "azurerm_virtual_network" "hub" {
  name                = local.hub_vnet_name
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
  address_space       = [var.hub_vnet_cidr]
  tags                = local.common_tags
}

resource "azurerm_subnet" "gateway" {
  name                 = "GatewaySubnet"
  resource_group_name  = azurerm_resource_group.lab.name
  virtual_network_name = azurerm_virtual_network.hub.name
  address_prefixes     = [var.gateway_subnet_cidr]
}

resource "azurerm_subnet" "routeserver" {
  name                 = "RouteServerSubnet"
  resource_group_name  = azurerm_resource_group.lab.name
  virtual_network_name = azurerm_virtual_network.hub.name
  address_prefixes     = [var.routeserver_subnet_cidr]
}

resource "azurerm_subnet" "hub_nva" {
  name                 = local.hub_nva_subnet_name
  resource_group_name  = azurerm_resource_group.lab.name
  virtual_network_name = azurerm_virtual_network.hub.name
  address_prefixes     = [var.hub_nva_subnet_cidr]
}

# --- vnet-sap-rise (spoke) ---

resource "azurerm_virtual_network" "spoke" {
  name                = local.spoke_vnet_name
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
  address_space       = [var.spoke_vnet_cidr]
  tags                = local.common_tags
}

resource "azurerm_subnet" "spoke_nva" {
  name                 = local.spoke_nva_subnet_name
  resource_group_name  = azurerm_resource_group.lab.name
  virtual_network_name = azurerm_virtual_network.spoke.name
  address_prefixes     = [var.spoke_nva_subnet_cidr]
}

resource "azurerm_subnet" "workload" {
  name                 = local.workload_subnet_name
  resource_group_name  = azurerm_resource_group.lab.name
  virtual_network_name = azurerm_virtual_network.spoke.name
  address_prefixes     = [var.workload_subnet_cidr]
}

# --- Subnet-scoped peering: the mechanism under test (design.md section 3) ---
# Requires Microsoft.Network/AllowMultiplePeeringLinksBetweenVnets feature registration,
# performed as a deploy.ps1 pre-flight step (Terraform does not manage feature registrations
# for this preview-turned-GA flag reliably across subscriptions).

resource "azurerm_virtual_network_peering" "hub_to_spoke" {
  name                                   = "peer-hub-to-sap-rise"
  resource_group_name                    = azurerm_resource_group.lab.name
  virtual_network_name                   = azurerm_virtual_network.hub.name
  remote_virtual_network_id              = azurerm_virtual_network.spoke.id
  peer_complete_virtual_networks_enabled = false
  local_subnet_names                     = [azurerm_subnet.hub_nva.name]
  remote_subnet_names                    = [azurerm_subnet.spoke_nva.name]
  allow_virtual_network_access           = true
  allow_forwarded_traffic                = true
  allow_gateway_transit                  = false
  use_remote_gateways                    = false
}

resource "azurerm_virtual_network_peering" "spoke_to_hub" {
  name                                   = "peer-sap-rise-to-hub"
  resource_group_name                    = azurerm_resource_group.lab.name
  virtual_network_name                   = azurerm_virtual_network.spoke.name
  remote_virtual_network_id              = azurerm_virtual_network.hub.id
  peer_complete_virtual_networks_enabled = false
  local_subnet_names                     = [azurerm_subnet.spoke_nva.name]
  remote_subnet_names                    = [azurerm_subnet.hub_nva.name]
  allow_virtual_network_access           = true
  allow_forwarded_traffic                = true
  allow_gateway_transit                  = false
  use_remote_gateways                    = false
}

# --- Simulated on-prem/CE VNet (Tank deviation, see decision inbox) ---
# Full VNet peering to vnet-hub, NOT part of the subnet-scoped mechanism under test.
# Realizes the CE as an Azure VM BGP speaker rather than a Megaport MVE (unbudgeted
# commercial vendor licensing) or a physical device (unavailable). BGP advertisement
# evidence (design.md section 8, items 1-4) is fully valid via the real ER
# Gateway/circuit/MCR regardless of this substitution; the CE-to-workload data-plane
# probe validates the hub-NVA/ARS mechanism but does not traverse the physical
# ExpressRoute circuit for that specific hop.

resource "azurerm_virtual_network" "onprem_sim" {
  name                = local.onprem_sim_vnet_name
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
  address_space       = [var.onprem_sim_vnet_cidr]
  tags                = local.common_tags
}

resource "azurerm_subnet" "onprem_sim" {
  name                 = local.onprem_sim_subnet_name
  resource_group_name  = azurerm_resource_group.lab.name
  virtual_network_name = azurerm_virtual_network.onprem_sim.name
  address_prefixes     = [var.onprem_sim_subnet_cidr]
}

resource "azurerm_virtual_network_peering" "onprem_to_hub" {
  name                         = "peer-onprem-sim-to-hub"
  resource_group_name          = azurerm_resource_group.lab.name
  virtual_network_name         = azurerm_virtual_network.onprem_sim.name
  remote_virtual_network_id    = azurerm_virtual_network.hub.id
  allow_virtual_network_access = true
  allow_forwarded_traffic      = true
  allow_gateway_transit        = false
  use_remote_gateways          = false
}

resource "azurerm_virtual_network_peering" "hub_to_onprem" {
  name                         = "peer-hub-to-onprem-sim"
  resource_group_name          = azurerm_resource_group.lab.name
  virtual_network_name         = azurerm_virtual_network.hub.name
  remote_virtual_network_id    = azurerm_virtual_network.onprem_sim.id
  allow_virtual_network_access = true
  allow_forwarded_traffic      = true
  allow_gateway_transit        = false
  use_remote_gateways          = false
}
