# Project Context

- **Owner:** Jose Moreno
- **Project:** net-lab-builder — build, document, and tear down ephemeral Azure Networking labs
- **Stack:** Bicep, Terraform, Azure CLI, PowerShell; Megaport API; Azure Key Vault (secret fetch via z keyvault secret show)
- **Created:** 2026-05-28
- **Role:** IaC Engineer — own src/{bicep,terraform,azure-cli,powershell}/ + labs/<lab>/deploy/; SKU defaults; 5-step ER cleanup chain (ER connection → ER private peering → Megaport VXCs → Megaport MCR → Azure RG)

## Summary (2026-06-15)

Tank completed three major infrastructure missions: Lab #1 multi-step cleanup automation (6-step charter-compliant ER teardown, Windows subprocess environment fix, KV access patterns), Lab #2 multi-cloud IaC scaffold (71 TF resources, 11 files, ~3h15m deploy, 6 iterations resolving multi-region SKU drift, routing-intent ordering, GCP ADC bootstrap, Megaport market pre-flight, vWAN ER connection shape conflicts), and patch/iteration learnings (secondary MCR↔ER VXCs for dual-port HA, GLOBAL-routing GCP VPC migration, ANSI code stripping in PowerShell TF output processing).

**Lab #1 (2026-05-28):** Established 6-step mandatory ER cleanup chain; fixed Windows subprocess environment variable isolation (inline HCL ternary-evaluated credentials bypass scope leakage); secured credential files and .gitignore patterns.

**Lab #2 IaC scaffold (2026-06-15):** Deployed fully multi-cloud lab (g-vwan-symm-103167 + gcp-vwan-symm-103167, 71 resources) with per-region VM size variables (SKU catalog drift between swedencentral/northeurope), routing-intent dependency ordering, GCP provider aliasing, Megaport MCR market pre-flight validation, permissive AzFW RFC1918 rules for routing-intent=private flows. **Pre-deploy 	erraform plan with placeholder credentials is a valid graph-validation step** — confirms resource graph, inter-resource references, and conditional resources (bow-tie) build correctly before secrets are injected.

**Lab #2 patches & iterations:** Fixed missing secondary ER VXCs (dual-port MSEE requires 2 VXCs per circuit); migrated GCP vpc_a from REGIONAL to GLOBAL routing (in-place update, pairing key preserved); debugged and resolved Megaport API errors (TF_LOG=DEBUG required — "Still creating..." heartbeats hide 400s for 30+ min), GCP PARTNER attachment constraints (no andwidth field, ASN=16550 mandatory, pairing_key from Terraform google provider), vWAN routing-intent + spoke connection routing block conflict (must be empty; Azure auto-populates), ER GW + connection 409 races (retryable on next apply), PowerShell async wrapper + KV ACL (finally-blocks don't run on Stop-Process — always synchronous for KV-modifying scripts). **Key architectural decision deferred:** Megaport credential variables retained in TF as reusable cleanup pattern (enables faster automation without re-implementing provider modifications).

**Design C Phase 1A deployed:** google_compute_interconnect_attachment.att_b_v2 created in eu-w3 AVAILABILITY_DOMAIN_2 (edge diversity + port exhaustion avoidance). Pairing key captured; megaport.tf untouched (defers VXC cleanup to Phase 1B via state rm pattern). Jose's portal MCR pairing work awaited. Phase 1B destruction (att_b_new + cr_onprem_b) gated on "BGP up" signal.

**Detailed learnings and deployment evidence archived in history-archive.md.**

---

📌 Team update (2026-06-15): Design C Phase 1A deployed. tankc1 created google_compute_interconnect_attachment.att_b_v2 in eu-w3 AVAILABILITY_DOMAIN_2. Plan: +1 resource, 0 changes. Pairing key 326ba0de-2aed-4eb2-aaf4-2df34108dc07/europe-west3/2 captured; Jose's portal work (MCR pairing) awaited. Phase 1B destruction (att_b_new + cr_onprem_b) gated on "BGP up" signal.
