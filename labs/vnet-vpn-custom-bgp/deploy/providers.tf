terraform {
  required_version = ">= 1.9.0"
  backend "gcs" {}
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    megaport = {
      source  = "megaport/megaport"
      version = "~> 1.0"
    }
  }
}

provider "azurerm" {
  features {}
  resource_provider_registrations = "none"
}

provider "google" {
  project = local.gcp_project
  region  = "europe-north2"
}

provider "megaport" {
  environment           = "production"
  accept_purchase_terms = true
}

variable "billing_account" {
  type      = string
  sensitive = true
}

variable "ssh_public_key" {
  type = string
}

variable "deploy_megaport" {
  type    = bool
  default = false
}

variable "connect_expressroute" {
  type    = bool
  default = false

  validation {
    condition     = !var.connect_expressroute || var.deploy_megaport
    error_message = "ExpressRoute connection requires this lab's provider products."
  }
}

locals {
  prefix      = "vnbgp-20261124"
  gcp_project = "gcp-vnbgp-20261124"
  location    = "swedencentral"
  tags = {
    lab_name   = "vnet-vpn-custom-bgp"
    run_id     = "20261124"
    created_by = "copilot-lab"
    ephemeral  = "true"
  }
}
