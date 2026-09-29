variable "location" {
  description = "Azure region for the lab resources."
  type        = string
  default     = "swedencentral"
}

variable "prefix" {
  description = "Short resource naming prefix."
  type        = string
  default     = "saprise"
}

variable "admin_username" {
  description = "Linux VM administrator username."
  type        = string
  default     = "azurelabuser"
}

variable "ssh_public_key_path" {
  description = "Path to the SSH public key used for all lab Linux VMs. Not used for network access (no public IPs are deployed); required by the VM resource schema and kept for parity with other labs."
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

variable "vm_size" {
  description = "Lab VM size, cheapest-viable per the azure-lab skill / Morpheus SKU policy. Probe with az vm list-skus before deploy; fall back to vm_size_fallback if restricted."
  type        = string
  default     = "Standard_B2als_v2"
}

variable "vm_size_fallback" {
  description = "Fallback VM size if vm_size is restricted in the chosen region."
  type        = string
  default     = "Standard_B2s_v2"
}

variable "use_vm_size_fallback" {
  description = "Set true (via -var) if the vm_size SKU probe found a restriction; switches all lab VMs to vm_size_fallback. Defaulted to true 2026-09-29 after Standard_B2als_v2 hit AllocationFailed (transient capacity, not a subscription restriction) on all 4 VMs in swedencentral during the initial apply - see .squad/decisions/inbox/tank-sap-rise-deploy.md."
  type        = bool
  default     = true
}

# --- Address plan (locked, design.md section 2) ---

variable "hub_vnet_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "gateway_subnet_cidr" {
  type    = string
  default = "10.40.0.0/27"
}

variable "routeserver_subnet_cidr" {
  type    = string
  default = "10.40.0.32/27"
}

variable "hub_nva_subnet_cidr" {
  type    = string
  default = "10.40.1.0/27"
}

variable "hub_nva_private_ip" {
  description = "Static private IP for the hub NVA, referenced by BIRD config and NSG rules (design.md section 7)."
  type        = string
  default     = "10.40.1.4"
}

variable "spoke_vnet_cidr" {
  type    = string
  default = "10.60.0.0/16"
}

variable "spoke_nva_subnet_cidr" {
  type    = string
  default = "10.60.0.0/27"
}

variable "spoke_nva_private_ip" {
  description = "Static private IP for the spoke NVA, referenced by the workload UDR and BIRD static route (design.md section 5/7)."
  type        = string
  default     = "10.60.0.4"
}

variable "workload_subnet_cidr" {
  type    = string
  default = "10.60.1.0/24"
}

# --- Simulated on-prem/CE (Tank deviation - see decision inbox) ---

variable "onprem_sim_vnet_cidr" {
  description = "Address space for the simulated on-prem/CE VNet. Realized as an Azure VM rather than a Megaport MVE or physical CE - see .squad/decisions/inbox/tank-sap-rise-deploy.md for rationale."
  type        = string
  default     = "172.40.100.0/24"
}

variable "onprem_sim_subnet_cidr" {
  type    = string
  default = "172.40.100.0/25"
}

variable "onprem_sim_ce_private_ip" {
  type    = string
  default = "172.40.100.4"
}

# --- ASN plan (locked, design.md section 2 / decisions.md) ---

variable "hub_nva_asn" {
  type    = number
  default = 65001
}

variable "spoke_nva_asn" {
  type    = number
  default = 65002
}

variable "ce_asn" {
  type    = number
  default = 65000
}

# --- Scenario toggles (design.md section 10 hand-off spec) ---

variable "enable_summarized_gateway_prefixes" {
  description = "S2 toggle. When true, sets properties.summarizedGatewayPrefixes on vnet-hub (the corrected placement per design.md section 6.2) to advertise the spoke supernet via the gateway property mechanism. Default false so S1 can be validated first."
  type        = bool
  default     = false
}

variable "summarized_gateway_prefixes" {
  description = "Value applied to vnet-hub's summarizedGatewayPrefixes when enable_summarized_gateway_prefixes is true. Must include the hub's own prefix and the spoke's per design.md section 6.2."
  type        = list(string)
  default     = ["10.40.0.0/16", "10.60.0.0/16"]
}

# --- ExpressRoute / Megaport ---

variable "expressroute_peering_location" {
  description = "Azure ExpressRoute peering location. CHANGED 2026-09-29 from design.md's specified 'Stockholm' to 'Frankfurt': the Megaport account used for this deploy is not entitled to the MEGAPORT_SWEDEN market (validated 400 error on MCR creation targeting a Stockholm PoP), so the MCR and the ER circuit peering location were both moved to the known-good Germany market used successfully by the prior expressroute-megaport-bgp lab. See .squad/decisions/inbox/tank-sap-rise-deploy.md."
  type        = string
  default     = "Frankfurt"
}

variable "megaport_location" {
  description = "Megaport PoP location name for the MCR lookup. CHANGED 2026-09-29 from 'Equinix Stockholm SK1' to 'Equinix Frankfurt FR5' (Megaport location ID 131) after a validation error showed this Megaport account lacks the MEGAPORT_SWEDEN market entitlement. Frankfurt is the same PoP used successfully by src/terraform/expressroute-megaport-bgp."
  type        = string
  default     = "Equinix Frankfurt FR5"
}

variable "mcr_asn" {
  type    = number
  default = 64512
}

variable "megaport_access_key" {
  description = "Megaport API access key (rehydrated from HKCU env var by deploy.ps1)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "megaport_secret_key" {
  description = "Megaport API secret key (rehydrated from HKCU env var by deploy.ps1)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "tags" {
  description = "Tags applied to taggable resources. correlation_id is merged automatically."
  type        = map(string)
  default = {
    lab        = "sap-rise-scoped-peering-fwaas"
    created_by = "copilot-lab"
    owner      = "jose"
    ephemeral  = "true"
  }
}
