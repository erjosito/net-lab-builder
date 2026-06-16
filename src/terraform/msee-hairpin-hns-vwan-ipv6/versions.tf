terraform {
  required_version = ">= 1.6.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    # azapi required for the three silent-fail GW toggles not yet in azurerm 4.x:
    #   allow_virtual_wan_traffic / allow_remote_vnet_traffic (virtualNetworkGateways)
    #   allow_non_virtual_wan_traffic (expressRouteGateways)
    # See design §7 and manifest R2.
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}
