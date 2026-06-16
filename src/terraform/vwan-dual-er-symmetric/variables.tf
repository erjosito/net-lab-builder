###############################################################################
# Lab identity                                                                #
###############################################################################

variable "lab_name" {
  description = "Short lab slug used for naming and tagging."
  type        = string
  default     = "vwan-symm"
}

variable "tags" {
  description = "Base tag set merged with correlation_id. correlation_id is appended at apply time."
  type        = map(string)
  default = {
    lab            = "vwan-dual-er-symmetric"
    lab_name       = "vwan-dual-er-symmetric"
    owner          = "jose"
    created_by     = "copilot-lab"
    ephemeral      = "true"
    lifetime       = "manual"
  }
}

###############################################################################
# Azure regions and address plan (from labs/.../manifest.md §2.1)             #
###############################################################################

variable "location_a" {
  description = "Region A — primary region (Hub1)."
  type        = string
  default     = "swedencentral"
}

variable "location_b" {
  description = "Region B — secondary region (Hub2)."
  type        = string
  default     = "northeurope"
}

variable "hub1_prefix" {
  description = "vWAN Hub 1 address space."
  type        = string
  default     = "10.10.0.0/23"
}

variable "hub2_prefix" {
  description = "vWAN Hub 2 address space."
  type        = string
  default     = "10.20.0.0/23"
}

variable "spoke1_cidr" {
  description = "Spoke 1 VNet CIDR (Region A)."
  type        = string
  default     = "10.11.0.0/24"
}

variable "spoke2_cidr" {
  description = "Spoke 2 VNet CIDR (Region A)."
  type        = string
  default     = "10.12.0.0/24"
}

variable "spoke3_cidr" {
  description = "Spoke 3 VNet CIDR (Region B)."
  type        = string
  default     = "10.21.0.0/24"
}

variable "spoke4_cidr" {
  description = "Spoke 4 VNet CIDR (Region B)."
  type        = string
  default     = "10.22.0.0/24"
}

variable "spoke_workload_subnet_newbit" {
  description = "Subnet sizing inside each spoke (/27 from /24 = newbit 3)."
  type        = number
  default     = 3
}

###############################################################################
# VM sizing (cheapest viable per charter; per-region to handle catalog drift) #
###############################################################################

variable "vm_size_region_a" {
  description = "VM SKU for Region A spokes. B2als_v2 confirmed available unrestricted in swedencentral 2026-06-15."
  type        = string
  default     = "Standard_B2als_v2"
}

variable "vm_size_region_b" {
  description = "VM SKU for Region B spokes. B2als_v2 NOT in catalog in northeurope (2026-06-15 probe). Falls back to B2s_v2 (Intel). B2s_v2 has Zone restrictions zones 1+2 in northeurope, hence non-zonal deploy."
  type        = string
  default     = "Standard_B2s_v2"
}

variable "admin_username" {
  description = "Linux VM admin username."
  type        = string
  default     = "azureuser"
}

###############################################################################
# ExpressRoute / Megaport                                                     #
###############################################################################

variable "er_peering_location_a" {
  description = "ExpressRoute peering location for Circuit 1 (Region A). Primary: Stockholm; fallback: Frankfurt."
  type        = string
  default     = "Stockholm"
}

variable "er_peering_location_b" {
  description = "ExpressRoute peering location for Circuit 2 (Region B). Primary: Amsterdam; fallback: Dublin."
  type        = string
  default     = "Amsterdam"
}

variable "megaport_location_a" {
  description = "Megaport PoP name for MCR1. PRIMARY (Sweden) NOT AVAILABLE on this Megaport account → using fallback 'Equinix Frankfurt FR5' (id 131). Same fallback used in lab #1 (Spain market restriction). Manifest §5.2 allows Megaport-picked PoP."
  type        = string
  default     = "Equinix Frankfurt FR5"
}

variable "megaport_location_b" {
  description = "Megaport PoP name for MCR2. Primary: 'Equinix Amsterdam AM1' (id 85; AM2 doesn't exist in Megaport catalog — AM1 is the equivalent); fallback: 'Equinix Dublin DB3'. Manifest §5.2 allows Megaport-picked PoP."
  type        = string
  default     = "Equinix Amsterdam AM1"
}

variable "mcr1_asn" {
  description = "MCR1 ASN."
  type        = number
  default     = 65001
}

variable "mcr2_asn" {
  description = "MCR2 ASN."
  type        = number
  default     = 65002
}

variable "er_bandwidth_mbps" {
  description = "ExpressRoute circuit bandwidth (both circuits)."
  type        = number
  default     = 50
}

###############################################################################
# Symmetry-perturbation knobs (Niobe flips these for S4a/S4b — defaults OFF) #
###############################################################################

variable "er_bow_tie_hub1" {
  description = "When true, Hub1 ER GW also connects to Circuit2 (breaks per-circuit affinity). Default false. Niobe flips for S4a."
  type        = bool
  default     = false
}

variable "er_bow_tie_hub2" {
  description = "When true, Hub2 ER GW also connects to Circuit1 (breaks per-circuit affinity). Default false. Niobe flips for S4a."
  type        = bool
  default     = false
}

variable "mcr1_injected_prefixes" {
  description = "Extra prefixes MCR1 will export toward Azure (beyond its own region's /24). Default empty. Niobe injects e.g. [\"10.50.2.0/24\"] for S4b to force ingress asymmetry."
  type        = list(string)
  default     = []
}

variable "mcr2_injected_prefixes" {
  description = "Extra prefixes MCR2 will export toward Azure. Default empty. Niobe injects e.g. [\"10.50.1.0/24\"] for S4b."
  type        = list(string)
  default     = []
}

###############################################################################
# GCP                                                                         #
###############################################################################

variable "gcp_project_id" {
  description = "GCP project ID. Created by deploy.ps1 (Option Y) — must be set via TF_VAR_gcp_project_id."
  type        = string
  default     = ""

  validation {
    condition     = length(var.gcp_project_id) > 0
    error_message = "gcp_project_id must be set. deploy.ps1 creates the project and exports it as TF_VAR_gcp_project_id."
  }
}

variable "correlation_id_override" {
  description = "Optional override for correlation_id (6-char hex). Set by deploy.ps1 so the suffix matches the GCP project ID created pre-apply. If empty, random_id.correlation.hex is used."
  type        = string
  default     = ""
}

variable "gcp_region_a" {
  description = "GCP region paired with Region A (close to swedencentral)."
  type        = string
  default     = "europe-west3" # Frankfurt
}

variable "gcp_region_b" {
  description = "GCP region paired with Region B (close to northeurope)."
  type        = string
  default     = "europe-west4" # Eemshaven (NL)
}

variable "gcp_vpc_a_subnet" {
  description = "GCP VPC A on-prem subnet CIDR."
  type        = string
  default     = "10.50.1.0/24"
}

variable "gcp_vpc_b_subnet" {
  description = "GCP VPC B on-prem subnet CIDR."
  type        = string
  default     = "10.50.2.0/24"
}

variable "gcp_cloud_router_asn_a" {
  description = "Cloud Router ASN for GCP VPC A. MUST be 16550 for PARTNER Interconnect attachments (GCP API constraint — Google announces 16550 from its edge). Customer-side BGP peer ASN (MCR1) is set separately via mcr1_asn."
  type        = number
  default     = 16550
}

variable "gcp_cloud_router_asn_b" {
  description = "Cloud Router ASN for GCP VPC B. MUST be 16550 for PARTNER Interconnect attachments (GCP API constraint — Google announces 16550 from its edge). Customer-side BGP peer ASN (MCR2) is set separately via mcr2_asn."
  type        = number
  default     = 16550
}

variable "gcp_interconnect_bandwidth" {
  description = "GCP Partner Interconnect bandwidth (must match a supported tier)."
  type        = string
  default     = "BPS_50M"
}

variable "gcp_vm_machine_type" {
  description = "GCP test VM type."
  type        = string
  default     = "e2-micro"
}

###############################################################################
# Key Vault for secret fetch (data block reads only; ACL handled by deploy.ps1)#
###############################################################################

variable "key_vault_name" {
  description = "Existing platform Key Vault holding Megaport credentials and default-password."
  type        = string
  default     = "platform-secrets-1138"
}

variable "key_vault_resource_group" {
  description = "Resource group of the platform Key Vault."
  type        = string
  default     = "platform"
}

###############################################################################
# Secrets (sensitive). Populated by deploy.ps1 from KV via TF_VAR_*           #
# Defaults are empty strings so terraform validate works without secrets.     #
###############################################################################

variable "megaport_access_key" {
  description = "Megaport API access key. Set via TF_VAR_megaport_access_key by deploy.ps1."
  type        = string
  default     = ""
  sensitive   = true
}

variable "megaport_secret_key" {
  description = "Megaport API secret key. Set via TF_VAR_megaport_secret_key by deploy.ps1."
  type        = string
  default     = ""
  sensitive   = true
}

variable "default_password" {
  description = "Default VM admin password fetched from KV secret 'default-password'. Set via TF_VAR_default_password by deploy.ps1."
  type        = string
  default     = ""
  sensitive   = true
}
