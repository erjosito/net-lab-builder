###############################################################################
# Virtual WAN Layer                                                           #
###############################################################################

# ---------------------------------------------------------------------------
# vWAN + vHub (dual-stack)
# ---------------------------------------------------------------------------

resource "azurerm_virtual_wan" "hairpin" {
  name                = local.vwan_name
  resource_group_name = azurerm_resource_group.lab.name
  location            = var.location
  type                = "Standard"
  tags                = local.common_tags
}

resource "azurerm_virtual_hub" "hairpin" {
  name                = local.vhub_name
  resource_group_name = azurerm_resource_group.lab.name
  location            = var.location
  address_prefix      = "10.3.0.0/23"
  virtual_wan_id      = azurerm_virtual_wan.hairpin.id
  sku                 = "Standard"
  tags                = local.common_tags

  # IPv6 address space on the hub — inherits into spoke connections
  # NOTE: az_portal sets virtualHub.properties.hubRoutingPreference / v6 space
  # via address_prefix; the azurerm_virtual_hub resource exposes hub_routing_preference
  # and the ipv6_address attribute is not a separate property — the hub dual-stack
  # is signalled by including IPv6 in the spoke VNet address space + peering.
}

# ---------------------------------------------------------------------------
# vHub ER Gateway — 1 scale unit
#
# ⚠️ CRITICAL toggle (design §7):
#   allow_non_virtual_wan_traffic = true  → accepts routes from non-vWAN
#   circuits (Circuit 1 via MSEE hairpin); silent-fail if false.
# ---------------------------------------------------------------------------

resource "azurerm_express_route_gateway" "vhub" {
  name                          = local.ergw_vhub_name
  resource_group_name           = azurerm_resource_group.lab.name
  location                      = var.location
  virtual_hub_id                = azurerm_virtual_hub.hairpin.id
  scale_units                   = 1
  allow_non_virtual_wan_traffic = true
  tags                          = local.common_tags
}

# ---------------------------------------------------------------------------
# vHub ER Connection — same circuit as HnS (MSEE hairpin)
# ---------------------------------------------------------------------------

resource "azurerm_express_route_connection" "vhub_hairpin" {
  name                             = local.conn_vhub_er_name
  express_route_gateway_id         = azurerm_express_route_gateway.vhub.id
  express_route_circuit_peering_id = "${azurerm_express_route_circuit.hairpin.id}/peerings/AzurePrivatePeering"
  internet_security_enabled        = false

  depends_on = [azurerm_express_route_circuit_peering.hairpin]
}

# ---------------------------------------------------------------------------
# vWAN Spoke VNet — dual-stack
# ---------------------------------------------------------------------------

resource "azurerm_virtual_network" "vwan_spoke" {
  name                = local.vnet_vwan_name
  location            = var.location
  resource_group_name = azurerm_resource_group.lab.name
  address_space       = ["10.4.0.0/24", "fd00:4::/48"]
  tags                = local.common_tags
}

resource "azurerm_subnet" "vwan_spoke_vm" {
  name                 = "VmSubnet"
  resource_group_name  = azurerm_resource_group.lab.name
  virtual_network_name = azurerm_virtual_network.vwan_spoke.name
  address_prefixes     = ["10.4.0.0/24", "fd00:4::/64"]
}

# ---------------------------------------------------------------------------
# vHub → vWAN spoke connection
# NOTE: No `routing {}` block — no routing intent configured in this lab.
#       When routing intent IS configured, the routing block must be omitted
#       (lab #2 lesson: HTTP 400 RoutingConfigConflictsWithRoutingIntent).
# ---------------------------------------------------------------------------

resource "azurerm_virtual_hub_connection" "vhub_vnet" {
  name                      = local.conn_vhub_vnet_name
  virtual_hub_id            = azurerm_virtual_hub.hairpin.id
  remote_virtual_network_id = azurerm_virtual_network.vwan_spoke.id
  internet_security_enabled = false
}

# ---------------------------------------------------------------------------
# NSG — vWAN spoke (identical rules to HnS spoke)
# ---------------------------------------------------------------------------

resource "azurerm_network_security_group" "vwan" {
  name                = local.nsg_vwan_name
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

resource "azurerm_subnet_network_security_group_association" "vwan_spoke_vm" {
  subnet_id                 = azurerm_subnet.vwan_spoke_vm.id
  network_security_group_id = azurerm_network_security_group.vwan.id
}

# ---------------------------------------------------------------------------
# vWAN VM public IP + NIC + VM
# ---------------------------------------------------------------------------

resource "azurerm_public_ip" "vwan_vm" {
  name                = local.pip_vwan_name
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

resource "azurerm_network_interface" "vwan" {
  name                = local.nic_vwan_name
  location            = var.location
  resource_group_name = azurerm_resource_group.lab.name
  tags                = local.common_tags

  ip_configuration {
    name                          = "ipconfig-v4"
    subnet_id                     = azurerm_subnet.vwan_spoke_vm.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.vwan_vm.id
    primary                       = true
  }

  ip_configuration {
    name                          = "ipconfig-v6"
    subnet_id                     = azurerm_subnet.vwan_spoke_vm.id
    private_ip_address_allocation = "Dynamic"
    private_ip_address_version    = "IPv6"
  }
}

resource "azurerm_network_interface_security_group_association" "vwan" {
  network_interface_id      = azurerm_network_interface.vwan.id
  network_security_group_id = azurerm_network_security_group.vwan.id
}

resource "azurerm_linux_virtual_machine" "vwan" {
  name                            = local.vm_vwan_name
  location                        = var.location
  resource_group_name             = azurerm_resource_group.lab.name
  size                            = var.vm_size
  admin_username                  = var.vm_admin_username
  admin_password                  = var.vm_admin_password
  disable_password_authentication = false
  network_interface_ids           = [azurerm_network_interface.vwan.id]
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
