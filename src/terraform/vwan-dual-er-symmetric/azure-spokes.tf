###############################################################################
# Spoke VNets, NSGs, NICs, VMs (4 total — 2 per region)                       #
###############################################################################

resource "azurerm_virtual_network" "spoke" {
  for_each = local.spokes

  name                = "vnet-${each.value.name}"
  location            = each.value.location
  resource_group_name = azurerm_resource_group.lab.name
  address_space       = [each.value.cidr]
  tags                = local.common_tags
}

resource "azurerm_subnet" "spoke_workload" {
  for_each = local.spokes

  name                            = "snet-workload"
  resource_group_name             = azurerm_resource_group.lab.name
  virtual_network_name            = azurerm_virtual_network.spoke[each.key].name
  address_prefixes                = [each.value.workload]
  default_outbound_access_enabled = false
}

resource "azurerm_network_security_group" "spoke" {
  for_each = local.spokes

  name                = "nsg-${each.value.name}"
  location            = each.value.location
  resource_group_name = azurerm_resource_group.lab.name
  tags                = local.common_tags

  security_rule {
    name                       = "Allow-VNet-Inbound"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "VirtualNetwork"
  }

  security_rule {
    name                       = "Allow-AzureLoadBalancer-Inbound"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "AzureLoadBalancer"
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "spoke" {
  for_each = local.spokes

  subnet_id                 = azurerm_subnet.spoke_workload[each.key].id
  network_security_group_id = azurerm_network_security_group.spoke[each.key].id
}

###############################################################################
# Spoke VNet → vHub connection                                                #
###############################################################################

resource "azurerm_virtual_hub_connection" "spoke" {
  for_each = local.spokes

  name                      = "conn-${each.value.name}"
  virtual_hub_id            = local.hub_ids[each.value.hub_key]
  remote_virtual_network_id = azurerm_virtual_network.spoke[each.key].id
  internet_security_enabled = false

  # NOTE: When routing_intent is configured on the hub, the connection's routing
  # block must be OMITTED — Azure auto-populates route-table associations from
  # the intent. Including any associated_route_table_id / propagated_route_table
  # triggers HTTP 400 ConnectionRoutingConfigConflictsWithRoutingIntent.
  # See deploy-log.md mechanical fix #7 (2026-06-15).

  depends_on = [
    azurerm_virtual_hub_routing_intent.hub1,
    azurerm_virtual_hub_routing_intent.hub2,
  ]
}

###############################################################################
# VM NICs (no public IPs — SSH via az vm run-command or vHub serial)          #
###############################################################################

resource "azurerm_network_interface" "spoke" {
  for_each = local.spokes

  name                = "nic-${each.value.name}-vm"
  location            = each.value.location
  resource_group_name = azurerm_resource_group.lab.name
  tags                = local.common_tags

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = azurerm_subnet.spoke_workload[each.key].id
    private_ip_address_allocation = "Dynamic"
  }
}

###############################################################################
# Linux VMs — password auth, non-zonal per charter SKU-probe ruleset          #
###############################################################################

resource "azurerm_linux_virtual_machine" "spoke" {
  for_each = local.spokes

  name                            = "vm-${each.value.name}"
  location                        = each.value.location
  resource_group_name             = azurerm_resource_group.lab.name
  size                            = each.value.vm_size
  admin_username                  = var.admin_username
  admin_password                  = var.default_password
  disable_password_authentication = false
  network_interface_ids           = [azurerm_network_interface.spoke[each.key].id]
  tags                            = local.common_tags

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
      - nginx
    runcmd:
      - sysctl -w net.ipv4.ip_forward=0
      - echo "vwan-dual-er-symmetric ${each.value.name}" > /var/www/html/index.html
      - systemctl enable --now nginx
      - echo "vwan-dual-er-symmetric ${each.value.name} ready" > /etc/motd
  CLOUD_INIT
  )

  lifecycle {
    ignore_changes = [os_disk[0].storage_account_type]
  }
}
