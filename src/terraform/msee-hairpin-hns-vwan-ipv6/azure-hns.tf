###############################################################################
# Hub-and-Spoke Layer                                                         #
###############################################################################

# ---------------------------------------------------------------------------
# Hub VNet — dual-stack
# ---------------------------------------------------------------------------

resource "azurerm_virtual_network" "hns_hub" {
  name                = local.vnet_hns_hub_name
  location            = var.location
  resource_group_name = azurerm_resource_group.lab.name
  address_space       = ["10.1.0.0/16", "fd00:1::/48"]
  tags                = local.common_tags
}

resource "azurerm_subnet" "gateway" {
  name                 = "GatewaySubnet"
  resource_group_name  = azurerm_resource_group.lab.name
  virtual_network_name = azurerm_virtual_network.hns_hub.name
  address_prefixes     = ["10.1.0.0/27", "fd00:1::/64"]
}

# ---------------------------------------------------------------------------
# HnS Spoke VNet — dual-stack
# ---------------------------------------------------------------------------

resource "azurerm_virtual_network" "hns_spoke" {
  name                = local.vnet_hns_spoke_name
  location            = var.location
  resource_group_name = azurerm_resource_group.lab.name
  address_space       = ["10.2.0.0/24", "fd00:2::/48"]
  tags                = local.common_tags
}

resource "azurerm_subnet" "hns_spoke_vm" {
  name                 = "VmSubnet"
  resource_group_name  = azurerm_resource_group.lab.name
  virtual_network_name = azurerm_virtual_network.hns_spoke.name
  address_prefixes     = ["10.2.0.0/24", "fd00:2::/64"]
}

# ---------------------------------------------------------------------------
# VNet Peerings — hub ↔ spoke
# ---------------------------------------------------------------------------

resource "azurerm_virtual_network_peering" "hub_to_spoke" {
  name                         = "peer-hub-to-spoke-${local.suffix}"
  resource_group_name          = azurerm_resource_group.lab.name
  virtual_network_name         = azurerm_virtual_network.hns_hub.name
  remote_virtual_network_id    = azurerm_virtual_network.hns_spoke.id
  allow_gateway_transit        = true
  allow_forwarded_traffic      = true
  allow_virtual_network_access = true
}

resource "azurerm_virtual_network_peering" "spoke_to_hub" {
  name                         = "peer-spoke-to-hub-${local.suffix}"
  resource_group_name          = azurerm_resource_group.lab.name
  virtual_network_name         = azurerm_virtual_network.hns_spoke.name
  remote_virtual_network_id    = azurerm_virtual_network.hns_hub.id
  use_remote_gateways          = true
  allow_forwarded_traffic      = true
  allow_virtual_network_access = true

  depends_on = [azurerm_virtual_network_gateway.hns_er]
}

# ---------------------------------------------------------------------------
# ER Gateway PIPs — Standard SKU, zone-redundant (one IPv4, one IPv6)
# ---------------------------------------------------------------------------

resource "azurerm_public_ip" "ergw_hns_v4" {
  name                = local.pip_ergw_hns_name
  location            = var.location
  resource_group_name = azurerm_resource_group.lab.name
  allocation_method   = "Static"
  sku                 = "Standard"
  ip_version          = "IPv4"
  zones               = ["1", "2", "3"]
  tags                = local.common_tags

  lifecycle {
    ignore_changes = [ip_tags]
  }
}

# NOTE: ER GW dual-stack (IPv6) is derived from the GatewaySubnet having an IPv6 prefix.
# No separate IPv6 PIP is needed for ExpressRoute gateways — only VPN GWs in
# active-active mode take a second ip_configuration. The IPv6 PIP was removed.

# ---------------------------------------------------------------------------
# HnS ER Gateway — ErGw1AZ, dual-stack, three silent-fail toggles
#
# ⚠️ CRITICAL toggles (design §7 — silent-fail if missing, no error raised):
#   allow_virtual_wan_traffic  = true  → accepts MSEE-reflected vWAN routes
#   allow_remote_vnet_traffic  = true  → advertises peered spoke prefixes
#                                         (10.2.0.0/24 and fd00:2::/64)
# ---------------------------------------------------------------------------

resource "azurerm_virtual_network_gateway" "hns_er" {
  name                = local.ergw_hns_name
  location            = var.location
  resource_group_name = azurerm_resource_group.lab.name
  type                = "ExpressRoute"
  vpn_type            = "RouteBased"
  sku                 = "ErGw1AZ"
  tags                = local.common_tags

  # azurerm 4.x: public_ip_address_id must NOT be set for ExpressRoute type gateways.
  # Dual-stack (IPv6) is derived from GatewaySubnet having an IPv6 prefix (fd00:1::/64).
  ip_configuration {
    name                          = "ipconfig-v4"
    subnet_id                     = azurerm_subnet.gateway.id
    private_ip_address_allocation = "Dynamic"
  }

  # NOTE: allow_virtual_wan_traffic and allow_remote_vnet_traffic are NOT yet
  # native azurerm 4.x attributes for azurerm_virtual_network_gateway.
  # They are patched via azapi_update_resource in azure-gw-toggles.tf.
  # See design §7, manifest R2.
}

# ---------------------------------------------------------------------------
# HnS ER GW Connection — Circuit 1
# ---------------------------------------------------------------------------

resource "azurerm_virtual_network_gateway_connection" "hns_circuit1" {
  name                       = local.conn_hns_name
  location                   = var.location
  resource_group_name        = azurerm_resource_group.lab.name
  type                       = "ExpressRoute"
  virtual_network_gateway_id = azurerm_virtual_network_gateway.hns_er.id
  express_route_circuit_id   = azurerm_express_route_circuit.hairpin.id
  tags                       = local.common_tags

  depends_on = [azurerm_express_route_circuit_peering.hairpin]
}

# ---------------------------------------------------------------------------
# NSG — HnS spoke (ICMP + ICMPv6 + SSH from anywhere)
# ---------------------------------------------------------------------------

resource "azurerm_network_security_group" "hns" {
  name                = local.nsg_hns_name
  location            = var.location
  resource_group_name = azurerm_resource_group.lab.name
  tags                = local.common_tags

  security_rule {
    name                       = "Allow-ICMPv4-In"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Icmp"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "Allow-ICMPv6-In"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"   # azurerm NSG does not accept "Icmpv6"; "*" covers ICMPv6 for lab
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "Allow-SSH-In"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "hns_spoke_vm" {
  subnet_id                 = azurerm_subnet.hns_spoke_vm.id
  network_security_group_id = azurerm_network_security_group.hns.id
}

# ---------------------------------------------------------------------------
# HnS VM public IP + NIC + VM
# ---------------------------------------------------------------------------

resource "azurerm_public_ip" "hns_vm" {
  name                = local.pip_hns_name
  location            = var.location
  resource_group_name = azurerm_resource_group.lab.name
  allocation_method   = "Static"
  sku                 = "Standard"
  ip_version          = "IPv4"
  tags                = local.common_tags

  lifecycle {
    ignore_changes = [ip_tags]
  }
}

resource "azurerm_network_interface" "hns" {
  name                = local.nic_hns_name
  location            = var.location
  resource_group_name = azurerm_resource_group.lab.name
  tags                = local.common_tags

  ip_configuration {
    name                          = "ipconfig-v4"
    subnet_id                     = azurerm_subnet.hns_spoke_vm.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.hns_vm.id
    primary                       = true
  }

  ip_configuration {
    name                          = "ipconfig-v6"
    subnet_id                     = azurerm_subnet.hns_spoke_vm.id
    private_ip_address_allocation = "Dynamic"
    private_ip_address_version    = "IPv6"
  }
}

resource "azurerm_network_interface_security_group_association" "hns" {
  network_interface_id      = azurerm_network_interface.hns.id
  network_security_group_id = azurerm_network_security_group.hns.id
}

resource "azurerm_linux_virtual_machine" "hns" {
  name                            = local.vm_hns_name
  location                        = var.location
  resource_group_name             = azurerm_resource_group.lab.name
  size                            = var.vm_size
  admin_username                  = var.vm_admin_username
  admin_password                  = var.vm_admin_password
  disable_password_authentication = false
  network_interface_ids           = [azurerm_network_interface.hns.id]
  tags                            = local.common_tags

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
    disk_size_gb         = 30
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
}
