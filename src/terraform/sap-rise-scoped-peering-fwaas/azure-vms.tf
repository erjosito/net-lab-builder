# --- Hub NVA (BIRD, ASN 65001) --- design.md section 7
# BIRD static route + eBGP session peer IPs are injected post-deploy via
# `az vm run-command` (deploy.ps1), since ARS's own peering IPs are only known once
# azurerm_route_server.hub exists. This VM ships with BIRD installed and dormant.

resource "azurerm_network_interface" "hub_nva" {
  name                  = "nic-hub-nva"
  location              = azurerm_resource_group.lab.location
  resource_group_name   = azurerm_resource_group.lab.name
  ip_forwarding_enabled = true
  tags                  = local.common_tags

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = azurerm_subnet.hub_nva.id
    private_ip_address_allocation = "Static"
    private_ip_address            = var.hub_nva_private_ip
  }
}

resource "azurerm_linux_virtual_machine" "hub_nva" {
  name                            = local.vm_hub_nva_name
  location                        = azurerm_resource_group.lab.location
  resource_group_name             = azurerm_resource_group.lab.name
  size                            = local.vm_size
  admin_username                  = var.admin_username
  disable_password_authentication = true
  network_interface_ids           = [azurerm_network_interface.hub_nva.id]
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

  custom_data = filebase64("${path.module}/cloud-init/cloud-init-nva-bird.yaml")

  lifecycle {
    ignore_changes = [os_disk[0].storage_account_type]
  }
}

# --- Spoke NVA (ASN 65002, dormant BGP - forwarding + NAT only) --- design.md section 7

resource "azurerm_network_interface" "spoke_nva" {
  name                  = "nic-spoke-nva"
  location              = azurerm_resource_group.lab.location
  resource_group_name   = azurerm_resource_group.lab.name
  ip_forwarding_enabled = true
  tags                  = local.common_tags

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = azurerm_subnet.spoke_nva.id
    private_ip_address_allocation = "Static"
    private_ip_address            = var.spoke_nva_private_ip
  }
}

resource "azurerm_linux_virtual_machine" "spoke_nva" {
  name                            = local.vm_spoke_nva_name
  location                        = azurerm_resource_group.lab.location
  resource_group_name             = azurerm_resource_group.lab.name
  size                            = local.vm_size
  admin_username                  = var.admin_username
  disable_password_authentication = true
  network_interface_ids           = [azurerm_network_interface.spoke_nva.id]
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

  custom_data = filebase64("${path.module}/cloud-init/cloud-init-nva-base.yaml")

  lifecycle {
    ignore_changes = [os_disk[0].storage_account_type]
  }
}

# --- Workload probe VM (snet-workload) --- diagnostic-only, no forwarding

resource "azurerm_network_interface" "workload_probe" {
  name                = "nic-workload-probe"
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
  tags                = local.common_tags

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = azurerm_subnet.workload.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "workload_probe" {
  name                            = local.vm_workload_name
  location                        = azurerm_resource_group.lab.location
  resource_group_name             = azurerm_resource_group.lab.name
  size                            = local.vm_size
  admin_username                  = var.admin_username
  disable_password_authentication = true
  network_interface_ids           = [azurerm_network_interface.workload_probe.id]
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
      - echo "SAP RISE workload probe VM ready" > /etc/motd
  CLOUD_INIT
  )

  lifecycle {
    ignore_changes = [os_disk[0].storage_account_type]
  }
}

# --- Simulated on-prem/CE (ASN 65000) --- Tank deviation, see azure-network.tf note

resource "azurerm_network_interface" "ce_onprem" {
  name                = "nic-ce-onprem"
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
  tags                = local.common_tags

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = azurerm_subnet.onprem_sim.id
    private_ip_address_allocation = "Static"
    private_ip_address            = var.onprem_sim_ce_private_ip
  }
}

resource "azurerm_linux_virtual_machine" "ce_onprem" {
  name                            = local.vm_ce_onprem_name
  location                        = azurerm_resource_group.lab.location
  resource_group_name             = azurerm_resource_group.lab.name
  size                            = local.vm_size
  admin_username                  = var.admin_username
  disable_password_authentication = true
  network_interface_ids           = [azurerm_network_interface.ce_onprem.id]
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

  custom_data = filebase64("${path.module}/cloud-init/cloud-init-nva-bird.yaml")

  lifecycle {
    ignore_changes = [os_disk[0].storage_account_type]
  }
}
