variable "run_id" {
  type = string
}

variable "gcp_project_id" {
  type = string
}

variable "ssh_public_key" {
  type      = string
  sensitive = true
}

variable "megaport_access_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "megaport_secret_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "azure_location" {
  type    = string
  default = "swedencentral"
}

variable "azure_vm_size" {
  type    = string
  default = "Standard_B2ts_v2"
}

variable "gcp_region" {
  type    = string
  default = "europe-north2"
}

variable "gcp_zone" {
  type    = string
  default = "europe-north2-a"
}

variable "gcp_machine_type" {
  type    = string
  default = "e2-small"
}

variable "megaport_location" {
  type    = string
  default = "Equinix Stockholm SK1"
}

variable "mcr_asn" {
  type    = number
  default = 65060

  validation {
    condition     = !contains([65050, 16550, 65515, 12076], var.mcr_asn)
    error_message = "MCR ASN collides with a frozen lab ASN."
  }
}

variable "deploy_megaport" {
  type    = bool
  default = false
}
