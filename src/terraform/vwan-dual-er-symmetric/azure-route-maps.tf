###############################################################################
# VWAN Route Maps — Mechanism C2 (Phase 3, active/passive)                    #
#                                                                             #
# Reserved ASN 64496 (RFC 5398 documentation range 64496-64511) — not        #
# private, not Azure-reserved, 2-byte. Preferred over AS_TRANS 23456 because  #
# 23456 has operational meaning during 4-byte ASN transition (old speakers    #
# substitute it for un-representable 4-byte ASNs); 64496 is reserved purely   #
# for docs/examples and carries no transition semantics.                      #
#                                                                             #
# C2 = active/passive. MCR1/ER1/Hub1 is PRIMARY for ALL Azure prefixes;       #
# MCR2/ER2/Hub2 is STANDBY. Three levers:                                     #
#                                                                             #
#  1. Hub2 OUTBOUND (hub2_out_blanket): prepend 64496×5 on ALL Azure          #
#     prefixes toward MCR2 → router_a sees every Azure prefix as 7-hop via    #
#     MCR2 vs 2-hop via MCR1 → MCR1 wins for all. (GCP→Azure axis.)           #
#                                                                             #
#  2. Hub2 INBOUND (hub2_in_depref_gcp): prepend 64496×5 on GCP prefixes      #
#     learned from MCR2 → with hub_routing_preference=ASPath, Hub2 prefers    #
#     the hub-to-hub path (Hub2→Hub1→ER1) for GCP-bound egress. (Azure→GCP    #
#     axis.)                                                                   #
#                                                                             #
#  3. hub_routing_preference = "ASPath" on both hubs (set in azure-vwan.tf) — #
#     required for lever 2 to override the hub's internal ER preference.       #
#                                                                             #
# The Hub1 OUTBOUND route map from C1 is REMOVED: C2's blanket Hub2 outbound  #
# already makes MCR1 win for every prefix, so per-prefix Hub1 de-preference   #
# is redundant.                                                                #
#                                                                             #
# Provider note: AzureRM 4.x uses azurerm_route_map (not                      #
# azurerm_virtual_hub_route_map which was the pre-GA name).                   #
###############################################################################

# Lever 1 — Hub2 OUTBOUND: blanket de-prefer ALL Azure prefixes toward MCR2.
resource "azurerm_route_map" "hub2_out_blanket" {
  name           = "hub2-out-blanket-depref"
  virtual_hub_id = azurerm_virtual_hub.hub2.id

  rule {
    name                 = "prepend-all-azure"
    next_step_if_matched = "Continue"

    match_criterion {
      match_condition = "Contains"
      route_prefix = [
        "10.10.0.0/23", "10.11.0.0/24", "10.12.0.0/24",
        "10.20.0.0/23", "10.21.0.0/24", "10.22.0.0/24",
      ]
    }

    action {
      type = "Add"
      parameter {
        as_path = ["64496", "64496", "64496", "64496", "64496"]
      }
    }
  }
}

# Lever 2 — Hub2 INBOUND: de-prefer GCP prefixes learned from MCR2 so Hub2
# prefers the hub-to-hub path to reach GCP (requires hub_routing_preference=ASPath).
resource "azurerm_route_map" "hub2_in_depref_gcp" {
  name           = "hub2-in-depref-gcp"
  virtual_hub_id = azurerm_virtual_hub.hub2.id

  rule {
    name                 = "prepend-gcp"
    next_step_if_matched = "Continue"

    match_criterion {
      match_condition = "Contains"
      route_prefix    = ["10.50.1.0/24", "10.50.2.0/24"]
    }

    action {
      type = "Add"
      parameter {
        as_path = ["64496", "64496", "64496", "64496", "64496"]
      }
    }
  }
}
