###############################################################################
# Key Vault secret reads — Path A (GSA paused) or Path B (ACL flipped) must  #
# already be in effect when these data sources resolve. deploy.ps1 handles    #
# the operator coordination; Terraform just reads.                            #
###############################################################################

data "azurerm_client_config" "current" {}

# Megaport PoP lookups (deploy-time validation)
data "megaport_location" "loc_a" {
  name = var.megaport_location_a
}

data "megaport_location" "loc_b" {
  name = var.megaport_location_b
}
