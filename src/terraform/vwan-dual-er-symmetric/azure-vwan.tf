###############################################################################
# Resource group                                                              #
###############################################################################

resource "azurerm_resource_group" "lab" {
  name     = local.rg_name
  location = var.location_a
  tags     = local.common_tags
}

###############################################################################
# Virtual WAN + 2 secured hubs                                                #
###############################################################################

resource "azurerm_virtual_wan" "vwan" {
  name                = local.vwan_name
  resource_group_name = azurerm_resource_group.lab.name
  location            = azurerm_resource_group.lab.location
  type                = "Standard"
  tags                = local.common_tags
}

resource "azurerm_virtual_hub" "hub1" {
  name                   = local.hub1_name
  resource_group_name    = azurerm_resource_group.lab.name
  location               = var.location_a
  address_prefix         = var.hub1_prefix
  virtual_wan_id         = azurerm_virtual_wan.vwan.id
  sku                    = "Standard"
  hub_routing_preference = "ASPath"
  tags                   = local.common_tags
}

resource "azurerm_virtual_hub" "hub2" {
  name                   = local.hub2_name
  resource_group_name    = azurerm_resource_group.lab.name
  location               = var.location_b
  address_prefix         = var.hub2_prefix
  virtual_wan_id         = azurerm_virtual_wan.vwan.id
  sku                    = "Standard"
  hub_routing_preference = "ASPath"
  tags                   = local.common_tags
}

###############################################################################
# Azure Firewall — in-hub Standard, one per hub                               #
###############################################################################

resource "azurerm_firewall_policy" "shared" {
  name                = local.azfw_policy_name
  resource_group_name = azurerm_resource_group.lab.name
  location            = azurerm_resource_group.lab.location
  sku                 = "Standard"
  tags                = local.common_tags
}

# Permissive rule collection group so routing-intent flows survive end-to-end
resource "azurerm_firewall_policy_rule_collection_group" "lab_allow_all" {
  name               = "lab-allow-all"
  firewall_policy_id = azurerm_firewall_policy.shared.id
  priority           = 200

  network_rule_collection {
    name     = "allow-private"
    priority = 100
    action   = "Allow"

    rule {
      name                  = "allow-rfc1918-any"
      protocols             = ["Any"]
      source_addresses      = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
      destination_addresses = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
      destination_ports     = ["*"]
    }
  }
}

resource "azurerm_firewall" "hub1" {
  name                = local.azfw1_name
  location            = var.location_a
  resource_group_name = azurerm_resource_group.lab.name
  sku_name            = "AZFW_Hub"
  sku_tier            = "Standard"
  firewall_policy_id  = azurerm_firewall_policy.shared.id
  tags                = local.common_tags

  virtual_hub {
    virtual_hub_id  = azurerm_virtual_hub.hub1.id
    public_ip_count = 1
  }
}

resource "azurerm_firewall" "hub2" {
  name                = local.azfw2_name
  location            = var.location_b
  resource_group_name = azurerm_resource_group.lab.name
  sku_name            = "AZFW_Hub"
  sku_tier            = "Standard"
  firewall_policy_id  = azurerm_firewall_policy.shared.id
  tags                = local.common_tags

  virtual_hub {
    virtual_hub_id  = azurerm_virtual_hub.hub2.id
    public_ip_count = 1
  }
}

###############################################################################
# Routing intent — private only (per manifest §2.3)                           #
###############################################################################

resource "azurerm_virtual_hub_routing_intent" "hub1" {
  name           = "intent-hub1"
  virtual_hub_id = azurerm_virtual_hub.hub1.id

  routing_policy {
    name         = "PrivateTrafficPolicy"
    destinations = ["PrivateTraffic"]
    next_hop     = azurerm_firewall.hub1.id
  }

  depends_on = [
    azurerm_firewall.hub1,
    azurerm_firewall_policy_rule_collection_group.lab_allow_all,
  ]
}

resource "azurerm_virtual_hub_routing_intent" "hub2" {
  name           = "intent-hub2"
  virtual_hub_id = azurerm_virtual_hub.hub2.id

  routing_policy {
    name         = "PrivateTrafficPolicy"
    destinations = ["PrivateTraffic"]
    next_hop     = azurerm_firewall.hub2.id
  }

  depends_on = [
    azurerm_firewall.hub2,
    azurerm_firewall_policy_rule_collection_group.lab_allow_all,
  ]
}

###############################################################################
# Log Analytics workspace (for AzFW diagnostic logs Niobe will query)         #
###############################################################################

resource "azurerm_log_analytics_workspace" "lab" {
  name                = "law-${var.lab_name}-${local.correlation_id}"
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.common_tags
}

resource "azurerm_monitor_diagnostic_setting" "azfw1" {
  name                       = "diag-azfw1"
  target_resource_id         = azurerm_firewall.hub1.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.lab.id

  enabled_log {
    category_group = "allLogs"
  }
}

resource "azurerm_monitor_diagnostic_setting" "azfw2" {
  name                       = "diag-azfw2"
  target_resource_id         = azurerm_firewall.hub2.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.lab.id

  enabled_log {
    category_group = "allLogs"
  }
}
