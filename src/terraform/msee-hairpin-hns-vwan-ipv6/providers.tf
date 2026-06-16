provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
  }
  # Subscription resolved from caller's `az account show` — no hardcoded ID.
}

# azapi — used exclusively for the three silent-fail GW toggles (design §7)
# that are not yet exposed as native azurerm attributes in v4.x.
provider "azapi" {}
