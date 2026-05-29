# Project Context

- **Owner:** Jose Moreno
- **Project:** net-lab-builder — build, document, and tear down ephemeral Azure Networking labs
- **Stack:** Azure networking (VNet, NSG, UDR, peering, gateways, firewall, Private Link, DNS, BGP); Megaport ExpressRoute; cloud-init NVA templates (NAT, BIRD, StrongSwan+BIRD)
- **Created:** 2026-05-28
- **Role:** Azure Network SME — own addressing, NSG, UDR, peering, gateways, firewall, Private Link, DNS, BGP; three-layer route collection (gateway + circuit + MCR); ER & Megaport gotchas

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

📌 2026-05-28 — Project initialized. Charter integrated with azure-lab skill networking reference. ER labs MUST capture routes at gateway + circuit + MCR (with VXC-resource fallback for empty looking-glass). Megaport quirks: nested `associatedVxcs` under MCR; MCR uses `contractTerm`, VXC uses `term`; never include `config: {}` in MCR payload; never manually create Azure peering when Megaport handles the VXC.

📌 2026-05-29 — Vault Stewardship backfill for lab `expressroute-megaport-bgp` (Phase 3.4 close gate). Created: `Labs/2026-05-ExpressRoute-Megaport-BGP.md`, `Services/Megaport.md`. Appended to: `Services/ExpressRoute.md` (list-route-tables false-negative gotcha + personal labs), `Topics/BGP-on-Azure.md` (custom BGP community non-surfacing via VNet API + personal labs). Updated `_Index.md` Recently-added and date. Five anomalies documented; zero forbidden GUID matches confirmed across all 5 touched files.
