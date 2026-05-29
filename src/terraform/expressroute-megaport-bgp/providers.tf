provider "azurerm" {
  features {}
}

provider "azapi" {}

provider "megaport" {
  environment           = "production"
  accept_purchase_terms = true
  access_key            = var.megaport_access_key != "" ? var.megaport_access_key : null
  secret_key            = var.megaport_secret_key != "" ? var.megaport_secret_key : null
}
