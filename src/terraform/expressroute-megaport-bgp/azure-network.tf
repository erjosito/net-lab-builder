resource "azurerm_resource_group" "lab" {
  name     = local.rg_name
  location = var.location
  tags     = local.common_tags
}

resource "azurerm_virtual_network" "lab" {
  name                = local.vnet_name
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
  address_space       = [var.vnet_cidr]
  bgp_community       = var.vnet_bgp_community
  tags                = local.common_tags
}

resource "azurerm_subnet" "gateway" {
  name                            = "GatewaySubnet"
  resource_group_name             = azurerm_resource_group.lab.name
  virtual_network_name            = azurerm_virtual_network.lab.name
  address_prefixes                = [var.gateway_subnet_cidr]
  default_outbound_access_enabled = false
}

resource "azurerm_subnet" "workload" {
  name                            = local.workload_subnet_name
  resource_group_name             = azurerm_resource_group.lab.name
  virtual_network_name            = azurerm_virtual_network.lab.name
  address_prefixes                = [var.workload_subnet_cidr]
  default_outbound_access_enabled = false
}

resource "azurerm_network_security_group" "workload" {
  name                = local.nsg_name
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
  tags                = local.common_tags

  security_rule {
    name                       = "Allow-VNet-Inbound"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "VirtualNetwork"
  }
}

resource "azurerm_subnet_network_security_group_association" "workload" {
  subnet_id                 = azurerm_subnet.workload.id
  network_security_group_id = azurerm_network_security_group.workload.id
}

resource "azurerm_public_ip" "vm" {
  name                = local.vm_public_ip_name
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = local.common_tags

  lifecycle {
    ignore_changes = [ip_tags, zones]
  }
}

resource "azurerm_network_interface" "vm" {
  name                = local.vm_nic_name
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
  tags                = local.common_tags

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = azurerm_subnet.workload.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.vm.id
  }
}

resource "azurerm_linux_virtual_machine" "test" {
  name                            = local.vm_name
  location                        = azurerm_resource_group.lab.location
  resource_group_name             = azurerm_resource_group.lab.name
  size                            = var.vm_size
  admin_username                  = var.admin_username
  disable_password_authentication = true
  network_interface_ids           = [azurerm_network_interface.vm.id]
  tags                            = local.common_tags

  admin_ssh_key {
    username   = var.admin_username
    public_key = file(pathexpand(var.ssh_public_key_path))
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
    disk_size_gb         = 30
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  custom_data = base64encode(<<-CLOUD_INIT
    #cloud-config
    package_update: true
    packages:
      - bind9-dnsutils
      - curl
      - iproute2
      - jq
      - net-tools
      - tcpdump
      - traceroute
    runcmd:
      - sysctl -w net.ipv4.ip_forward=0
      - echo "ExpressRoute Megaport BGP lab VM ready" > /etc/motd
  CLOUD_INIT
  )

  lifecycle {
    ignore_changes = [os_disk[0].storage_account_type]
  }
}
