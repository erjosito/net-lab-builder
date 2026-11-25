resource "azurerm_resource_group" "lab" {
  name     = "rg-${local.prefix}"
  location = local.location
  tags     = local.tags
}

resource "azurerm_virtual_network" "lab" {
  name                = "vnet-${local.prefix}"
  resource_group_name = azurerm_resource_group.lab.name
  location            = local.location
  address_space       = ["10.244.0.0/16"]
  tags                = local.tags
}

resource "azurerm_subnet" "gateway" {
  name                 = "GatewaySubnet"
  resource_group_name  = azurerm_resource_group.lab.name
  virtual_network_name = azurerm_virtual_network.lab.name
  address_prefixes     = ["10.244.255.0/26"]
}

resource "azurerm_subnet" "workload" {
  name                            = "workload"
  resource_group_name             = azurerm_resource_group.lab.name
  virtual_network_name            = azurerm_virtual_network.lab.name
  address_prefixes                = ["10.244.1.0/24"]
  default_outbound_access_enabled = false
}

resource "azurerm_public_ip" "gateway" {
  for_each            = toset(["vpn0", "vpn1", "er"])
  name                = "pip-${local.prefix}-${each.key}"
  resource_group_name = azurerm_resource_group.lab.name
  location            = local.location
  allocation_method   = "Static"
  sku                 = "Standard"
  zones               = ["1", "2", "3"]
  ip_tags             = { FirstPartyUsage = "/Unprivileged" }
  tags                = local.tags
}

resource "azurerm_virtual_network_gateway" "vpn" {
  name                       = "vpngw-${local.prefix}"
  resource_group_name        = azurerm_resource_group.lab.name
  location                   = local.location
  type                       = "Vpn"
  vpn_type                   = "RouteBased"
  sku                        = "VpnGw1AZ"
  generation                 = "Generation1"
  active_active              = true
  bgp_enabled                = true
  private_ip_address_enabled = true
  tags                       = local.tags

  dynamic "ip_configuration" {
    for_each = ["vpn0", "vpn1"]
    content {
      name                          = ip_configuration.value
      private_ip_address_allocation = "Dynamic"
      public_ip_address_id          = azurerm_public_ip.gateway[ip_configuration.value].id
      subnet_id                     = azurerm_subnet.gateway.id
    }
  }

  bgp_settings {
    asn = 65515
    peering_addresses {
      ip_configuration_name = "vpn0"
      apipa_addresses       = ["169.254.21.2"]
    }
    peering_addresses {
      ip_configuration_name = "vpn1"
      apipa_addresses       = ["169.254.22.2"]
    }
  }

  timeouts {
    create = "45m"
    delete = "45m"
  }
}

resource "azurerm_virtual_network_gateway" "er" {
  name                = "ergw-${local.prefix}"
  resource_group_name = azurerm_resource_group.lab.name
  location            = local.location
  type                = "ExpressRoute"
  sku                 = "ErGw1AZ"
  tags                = local.tags
  depends_on          = [azurerm_virtual_network_gateway.vpn]

  ip_configuration {
    name                          = "er"
    private_ip_address_allocation = "Dynamic"
    subnet_id                     = azurerm_subnet.gateway.id
  }

  timeouts {
    create = "45m"
    delete = "45m"
  }
}

resource "azurerm_express_route_circuit" "lab" {
  name                  = "er-${local.prefix}"
  resource_group_name   = azurerm_resource_group.lab.name
  location              = local.location
  service_provider_name = "Megaport"
  peering_location      = "Stockholm"
  bandwidth_in_mbps     = 50
  tags                  = local.tags
  sku {
    tier   = "Standard"
    family = "MeteredData"
  }
}

resource "azurerm_network_security_group" "probe" {
  name                = "nsg-${local.prefix}"
  resource_group_name = azurerm_resource_group.lab.name
  location            = local.location
  tags                = local.tags
  security_rule {
    name                       = "OverlayPayload"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "10.246.1.0/24"
    destination_address_prefix = "10.244.1.4"
  }
}

resource "azurerm_subnet_network_security_group_association" "probe" {
  subnet_id                 = azurerm_subnet.workload.id
  network_security_group_id = azurerm_network_security_group.probe.id
}

resource "azurerm_network_interface" "probe" {
  name                = "nic-${local.prefix}"
  resource_group_name = azurerm_resource_group.lab.name
  location            = local.location
  tags                = local.tags
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.workload.id
    private_ip_address_allocation = "Static"
    private_ip_address            = "10.244.1.4"
  }
}

resource "azurerm_linux_virtual_machine" "probe" {
  name                                                   = "probe-${local.prefix}"
  resource_group_name                                    = azurerm_resource_group.lab.name
  location                                               = local.location
  size                                                   = "Standard_B2ts_v2"
  patch_mode                                             = "AutomaticByPlatform"
  patch_assessment_mode                                  = "AutomaticByPlatform"
  bypass_platform_safety_checks_on_user_schedule_enabled = true
  admin_username                                         = "azurelabuser"
  network_interface_ids                                  = [azurerm_network_interface.probe.id]
  tags                                                   = local.tags
  admin_ssh_key {
    username   = "azurelabuser"
    public_key = var.ssh_public_key
  }
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

resource "azurerm_virtual_network_gateway_connection" "er" {
  count                      = var.connect_expressroute ? 1 : 0
  name                       = "conn-er-${local.prefix}"
  resource_group_name        = azurerm_resource_group.lab.name
  location                   = local.location
  type                       = "ExpressRoute"
  virtual_network_gateway_id = azurerm_virtual_network_gateway.er.id
  express_route_circuit_id   = azurerm_express_route_circuit.lab.id
  tags                       = local.tags
  depends_on                 = [megaport_vxc.azure, megaport_vxc.gcp]
}
