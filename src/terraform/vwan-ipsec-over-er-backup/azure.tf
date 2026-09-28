resource "azurerm_resource_group" "lab" {
  name     = "rg-vwan-ipsec-over-er-${var.run_id}"
  location = var.azure_location
  tags     = local.tags
}

resource "azurerm_virtual_wan" "lab" {
  name                = "vwan-${local.prefix}"
  resource_group_name = azurerm_resource_group.lab.name
  location            = var.azure_location
  type                = "Standard"
  tags                = local.tags
}

resource "azurerm_virtual_hub" "lab" {
  name                   = "vhub-${local.prefix}"
  resource_group_name    = azurerm_resource_group.lab.name
  location               = var.azure_location
  virtual_wan_id         = azurerm_virtual_wan.lab.id
  address_prefix         = "10.240.0.0/24"
  sku                    = "Standard"
  hub_routing_preference = "ASPath"
  tags                   = local.tags
}

resource "azurerm_express_route_gateway" "lab" {
  name                = "ergw-${local.prefix}"
  resource_group_name = azurerm_resource_group.lab.name
  location            = var.azure_location
  virtual_hub_id      = azurerm_virtual_hub.lab.id
  scale_units         = 1
  tags                = local.tags
}

resource "azurerm_vpn_gateway" "lab" {
  name                = "vpngw-${local.prefix}"
  resource_group_name = azurerm_resource_group.lab.name
  location            = var.azure_location
  virtual_hub_id      = azurerm_virtual_hub.lab.id
  scale_unit          = 1
  routing_preference  = "Microsoft Network"
  tags                = local.tags

  bgp_settings {
    asn         = 65515
    peer_weight = 0

    instance_0_bgp_peering_address {
      custom_ips = ["169.254.21.1", "169.254.21.5"]
    }

    instance_1_bgp_peering_address {
      custom_ips = ["169.254.22.1", "169.254.22.5"]
    }
  }
}

resource "azurerm_express_route_circuit" "lab" {
  name                     = "er-${local.prefix}"
  resource_group_name      = azurerm_resource_group.lab.name
  location                 = var.azure_location
  service_provider_name    = "Megaport"
  peering_location         = "Stockholm"
  bandwidth_in_mbps        = 50
  allow_classic_operations = false
  tags                     = local.tags

  sku {
    tier   = "Standard"
    family = "MeteredData"
  }
}

resource "azurerm_virtual_network" "workload" {
  name                = "vnet-workload-${local.prefix}"
  resource_group_name = azurerm_resource_group.lab.name
  location            = var.azure_location
  address_space       = ["10.241.0.0/24"]
  tags                = local.tags
}

resource "azurerm_subnet" "workload" {
  name                            = "snet-workload"
  resource_group_name             = azurerm_resource_group.lab.name
  virtual_network_name            = azurerm_virtual_network.workload.name
  address_prefixes                = ["10.241.0.0/26"]
  default_outbound_access_enabled = false
}

resource "azurerm_network_security_group" "workload" {
  name                = "nsg-workload-${local.prefix}"
  resource_group_name = azurerm_resource_group.lab.name
  location            = var.azure_location
  tags                = local.tags

  security_rule {
    name                       = "AllowLabPrivate"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefixes    = ["10.240.0.0/24", "10.250.0.0/24", "10.253.0.0/16"]
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "workload" {
  subnet_id                 = azurerm_subnet.workload.id
  network_security_group_id = azurerm_network_security_group.workload.id
}

resource "azurerm_network_interface" "probe" {
  name                = "nic-probe-${local.prefix}"
  resource_group_name = azurerm_resource_group.lab.name
  location            = var.azure_location
  tags                = local.tags

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = azurerm_subnet.workload.id
    private_ip_address_allocation = "Static"
    private_ip_address            = "10.241.0.4"
  }
}

resource "azurerm_linux_virtual_machine" "probe" {
  name                            = "vm-probe-${local.prefix}"
  resource_group_name             = azurerm_resource_group.lab.name
  location                        = var.azure_location
  size                            = var.azure_vm_size
  admin_username                  = "azurelabuser"
  disable_password_authentication = true
  network_interface_ids           = [azurerm_network_interface.probe.id]
  tags                            = local.tags

  admin_ssh_key {
    username   = "azurelabuser"
    public_key = var.ssh_public_key
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

  custom_data = base64encode(<<-CLOUD
    #cloud-config
    runcmd:
      - echo "vwan-ipsec-over-er-backup probe" > /etc/motd
  CLOUD
  )

  lifecycle {
    ignore_changes = [custom_data]
  }
}

resource "azurerm_dev_test_global_vm_shutdown_schedule" "probe" {
  virtual_machine_id    = azurerm_linux_virtual_machine.probe.id
  location              = azurerm_resource_group.lab.location
  enabled               = true
  daily_recurrence_time = "2300"
  timezone              = "W. Europe Standard Time"
  tags                  = local.tags

  notification_settings {
    enabled = false
  }
}

resource "azurerm_virtual_hub_connection" "workload" {
  name                      = "conn-workload"
  virtual_hub_id            = azurerm_virtual_hub.lab.id
  remote_virtual_network_id = azurerm_virtual_network.workload.id
  internet_security_enabled = false
}
