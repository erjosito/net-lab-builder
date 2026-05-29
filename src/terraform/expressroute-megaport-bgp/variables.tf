variable "location" {
  description = "Azure region for the lab resources."
  type        = string
  default     = "spaincentral"
}

variable "prefix" {
  description = "Short resource naming prefix."
  type        = string
  default     = "erlab"
}

variable "vnet_cidr" {
  description = "Address space for the Azure VNet."
  type        = string
  default     = "10.100.0.0/16"
}

variable "gateway_subnet_cidr" {
  description = "CIDR for GatewaySubnet."
  type        = string
  default     = "10.100.255.0/27"
}

variable "workload_subnet_cidr" {
  description = "CIDR for the workload subnet."
  type        = string
  default     = "10.100.1.0/24"
}

variable "vm_size" {
  description = "Linux validation VM size. The VM is intentionally non-zonal so Azure can place it in an available Spain Central zone."
  type        = string
  default     = "Standard_B2als_v2"
}

variable "admin_username" {
  description = "Linux VM administrator username."
  type        = string
  default     = "azureuser"
}

variable "ssh_public_key_path" {
  description = "Path to the SSH public key used for the Linux validation VM."
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

variable "megaport_location" {
  description = "Megaport Frankfurt PoP location name for the MCR lookup. Equinix Frankfurt FR5 is Megaport location ID 131."
  type        = string
  default     = "Equinix Frankfurt FR5"
}

variable "expressroute_peering_location" {
  description = "Azure ExpressRoute peering location matching the Megaport Madrid PoP."
  type        = string
  default     = "Madrid"
}

variable "vnet_bgp_community" {
  description = "Custom ExpressRoute private peering community for the Azure VNet."
  type        = string
  default     = "12076:20031"
}

variable "mcr_asn" {
  description = "Megaport Cloud Router ASN."
  type        = number
  default     = 64512
}

variable "tags" {
  description = "Tags applied to taggable resources. correlation_id is merged automatically."
  type        = map(string)
  default = {
    lab        = "true"
    lab_name   = "expressroute-megaport-bgp"
    created_by = "copilot-lab"
    owner      = "jose"
    ephemeral  = "true"
  }
}

variable "megaport_access_key" {
  description = "Megaport API access key (for credential passing via Terraform variables)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "megaport_secret_key" {
  description = "Megaport API secret key (for credential passing via Terraform variables)."
  type        = string
  default     = ""
  sensitive   = true
}
