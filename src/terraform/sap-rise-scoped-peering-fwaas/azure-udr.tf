# UDR per design.md section 5: only snet-workload needs a route table, since it is not
# in the subnet-peering scope and has no other path to hub/on-prem.

resource "azurerm_route_table" "spoke_workload" {
  name                          = local.route_table_workload_name
  location                      = azurerm_resource_group.lab.location
  resource_group_name           = azurerm_resource_group.lab.name
  bgp_route_propagation_enabled = false
  tags                          = local.common_tags

  route {
    name                   = "default-via-spoke-nva"
    address_prefix         = "0.0.0.0/0"
    next_hop_type          = "VirtualAppliance"
    next_hop_in_ip_address = var.spoke_nva_private_ip
  }
}

resource "azurerm_subnet_route_table_association" "workload" {
  subnet_id      = azurerm_subnet.workload.id
  route_table_id = azurerm_route_table.spoke_workload.id
}
