###############################################################################
# Lab identity                                                                #
###############################################################################

variable "lab_name" {
  description = "Lab slug used in resource naming and tags."
  type        = string
  default     = "msee-hairpin-hns-vwan-ipv6"
}

variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "swedencentral"
}

variable "correlation_id_override" {
  description = "Optional 6-char hex override for the run correlation ID. Set by deploy.ps1 to keep naming stable across plan/apply re-runs."
  type        = string
  default     = ""
}

###############################################################################
# VM credentials                                                              #
###############################################################################

variable "vm_admin_username" {
  description = "Linux VM admin username."
  type        = string
  default     = "azurelabuser"
}

variable "vm_admin_password" {
  description = "Linux VM admin password. Fetched from Key Vault at deploy time; passed via TF_VAR_vm_admin_password. Never written to a file."
  type        = string
  sensitive   = true
  default     = ""
}

###############################################################################
# Key Vault (platform KV — read-only data source)                             #
###############################################################################

variable "key_vault_name" {
  description = "Platform Key Vault name holding default-password."
  type        = string
  default     = "platform-secrets-1138"
}

variable "key_vault_resource_group" {
  description = "Resource group of the platform Key Vault."
  type        = string
  default     = "platform"
}

###############################################################################
# VM sizing                                                                   #
###############################################################################

variable "vm_size" {
  description = "VM SKU for lab VMs. B2als_v2 is charter default; fall back to B2s_v2 if AMD unavailable."
  type        = string
  default     = "Standard_B2als_v2"
}

###############################################################################
# ExpressRoute                                                                #
###############################################################################

variable "er_port_peering_location" {
  description = "ER Direct port peering location. Must be facility name (NOT the metro 'Stockholm'). Valid Stockholm options: Equinix-Stockholm-SK1, DigitalRealty-Stockholm-STO6, Stockholm-Metro-Direct."
  type        = string
  default     = "Equinix-Stockholm-SK1"
}
