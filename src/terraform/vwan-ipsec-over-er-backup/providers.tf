provider "azurerm" {
  features {}
}

provider "google" {
  project               = var.gcp_project_id
  region                = var.gcp_region
  billing_project       = var.gcp_project_id
  user_project_override = true
}

provider "megaport" {
  environment           = "production"
  accept_purchase_terms = true
  access_key            = var.megaport_access_key != "" ? var.megaport_access_key : null
  secret_key            = var.megaport_secret_key != "" ? var.megaport_secret_key : null
}
