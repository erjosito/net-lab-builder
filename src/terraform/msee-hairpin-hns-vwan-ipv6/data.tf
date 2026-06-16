###############################################################################
# Data sources                                                                #
###############################################################################

# Caller's Azure identity — used for tenant/sub discovery only (no hardcoded IDs)
data "azurerm_client_config" "current" {}

# Platform Key Vault — read-only reference for tagging/audit; actual secret
# value is fetched by deploy.ps1 and passed as TF_VAR_vm_admin_password so
# the password does NOT end up in TF state.
data "azurerm_key_vault" "platform" {
  name                = var.key_vault_name
  resource_group_name = var.key_vault_resource_group
}
