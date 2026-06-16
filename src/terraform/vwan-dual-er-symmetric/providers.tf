provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
  }
}

provider "azapi" {}

provider "megaport" {
  environment           = "production"
  accept_purchase_terms = true
  access_key            = var.megaport_access_key != "" ? var.megaport_access_key : null
  secret_key            = var.megaport_secret_key != "" ? var.megaport_secret_key : null
}

provider "google" {
  project               = var.gcp_project_id
  region                = var.gcp_region_a
  billing_project       = var.gcp_project_id
  user_project_override = true
}

provider "google" {
  alias                 = "region_b"
  project               = var.gcp_project_id
  region                = var.gcp_region_b
  billing_project       = var.gcp_project_id
  user_project_override = true
}
