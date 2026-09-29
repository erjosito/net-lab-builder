# NSG rules per design.md section 4. No Bastion/jump-box/public IPs are deployed in this
# lab (Tank cost-reduction deviation - see decision inbox): all VM management and BIRD
# post-deploy configuration goes through `az vm run-command`, which does not require an
# inbound SSH path. The design's "Allow-SSH-Mgmt" rule is therefore omitted; only the
# data-path allow rules and the explicit deny-all backstop are implemented.

resource "azurerm_network_security_group" "hub_nva" {
  name                = local.nsg_hub_nva_name
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
  tags                = local.common_tags

  security_rule {
    name                       = "Allow-ARS-BGP-In"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "179"
    source_address_prefix      = var.routeserver_subnet_cidr
    destination_address_prefix = "VirtualNetwork"
  }

  security_rule {
    name                       = "Allow-SpokeNVA-In"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = var.spoke_nva_subnet_cidr
    destination_address_prefix = "VirtualNetwork"
  }

  security_rule {
    name                       = "Allow-Workload-In"
    priority                   = 115
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = var.workload_subnet_cidr
    destination_address_prefix = "VirtualNetwork"
  }

  security_rule {
    name                       = "Allow-OnpremSim-BGP-In"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "179"
    source_address_prefix      = var.onprem_sim_vnet_cidr
    destination_address_prefix = "VirtualNetwork"
  }

  security_rule {
    name                       = "Allow-OnpremSim-Data-In"
    priority                   = 125
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = var.onprem_sim_vnet_cidr
    destination_address_prefix = "VirtualNetwork"
  }

  security_rule {
    name                       = "DenyAllInbound"
    priority                   = 4096
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "hub_nva" {
  subnet_id                 = azurerm_subnet.hub_nva.id
  network_security_group_id = azurerm_network_security_group.hub_nva.id
}

resource "azurerm_network_security_group" "spoke_nva" {
  name                = local.nsg_spoke_nva_name
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
  tags                = local.common_tags

  security_rule {
    name                       = "Allow-HubNVA-In"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = var.hub_nva_subnet_cidr
    destination_address_prefix = "VirtualNetwork"
  }

  security_rule {
    name                       = "Allow-Workload-In"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = var.workload_subnet_cidr
    destination_address_prefix = "VirtualNetwork"
  }

  security_rule {
    name                       = "DenyAllInbound"
    priority                   = 4096
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "spoke_nva" {
  subnet_id                 = azurerm_subnet.spoke_nva.id
  network_security_group_id = azurerm_network_security_group.spoke_nva.id
}
