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

## Learnings — Phase 3 vWAN Hub Azure Firewall Deploy (2026-07-30)

**Lab:** vwan-routemap-summarization | **RG:** routemap-test-rg

### AZFW_Hub SKU into vWAN secured hub via CLI
- **SKU flags:** `--sku AZFW_Hub --tier Standard` — these are the only flags that work for vWAN-embedded firewalls. `Basic` is NOT supported in vWAN hubs.
- **No subnet required:** vWAN secured hubs manage firewall IP allocation internally from the hub address prefix (/23). Operator does NOT create AzureFirewallSubnet or AzureFirewallManagementSubnet.
- **Parallel deploy:** Use `az network firewall create --no-wait` for both firewalls, then poll `provisioningState`. `Start-Job` in PowerShell does NOT persist across fresh shell processes — `--no-wait` is the reliable parallelism pattern here.
- **Observed provisioning time:** ~12 minutes for both in parallel (swedencentral + westeurope). Design spec said 30–45 min; actual was significantly faster.
- **`--protocols` vs `--ip-protocols`:** For `az network firewall policy rule-collection-group collection add-filter-collection` with NetworkRule type, use `--ip-protocols Any` (not `--protocols Any`). `--protocols` is PROTOCOL=PORT format for ApplicationRule only.
- **`hubIPAddresses` field name:** The correct JSON field name returned by `az network firewall show` is `hubIPAddresses` (camelCase 'IP', not 'Ip'). Query: `--query "hubIPAddresses.privateIPAddress"`.

### Key resource IDs and IPs (redacted)
- **azfw-eu1:** privateIP=192.168.2.132, publicIP=4.223.110.6
  resourceId: `/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/routemap-test-rg/providers/Microsoft.Network/azureFirewalls/azfw-eu1`
- **azfw-eu2:** privateIP=192.168.4.132, publicIP=20.105.195.71
  resourceId: `/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/routemap-test-rg/providers/Microsoft.Network/azureFirewalls/azfw-eu2`
- **azfwpol-routemap-lab:** Standard, swedencentral (cross-region to hub-eu2 — supported)
  resourceId: `/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/routemap-test-rg/providers/Microsoft.Network/firewallPolicies/azfwpol-routemap-lab`

### Cleanup ordering
- **MANDATORY sequence:** routing-intent delete → azfw-eu1 delete → azfw-eu2 delete → policy delete
- Policy cannot be deleted while firewalls reference it — firewalls must be fully deleted first.
- Use `--no-wait` on firewall deletes and poll until both are gone before attempting policy delete.

### File paths
- Deploy script: `labs/vwan-routemap-summarization/deploy/deploy-phase3-firewall.sh`
- Cleanup script: `labs/vwan-routemap-summarization/deploy/cleanup-phase3-firewall.sh`
- Deploy log: `labs/vwan-routemap-summarization/deploy/phase3-firewall-deploy-log.txt`
- Pre-phase3 route table snapshots: `deploy/hub-eu1-defaultRT-pre-phase3.json`, `deploy/hub-eu2-defaultRT-pre-phase3.json`

### Gate status
- **Niobe Gate A:** READY — both firewalls Succeeded, no routing intent configured. Niobe to run §8 route-collection checklist and validate 6/6 summaries preserved on both hubs before Step 4 (Routing Intent) proceeds.

---

📌 Team update (2026-06-15): Design C Phase 1A deployed. tankc1 created google_compute_interconnect_attachment.att_b_v2 in eu-w3 AVAILABILITY_DOMAIN_2. Plan: +1 resource, 0 changes. Pairing key 326ba0de-2aed-4eb2-aaf4-2df34108dc07/europe-west3/2 captured; Jose's portal work (MCR pairing) awaited. Phase 1B destruction (att_b_new + cr_onprem_b) gated on "BGP up" signal.

---

**Phase 2/3 Sequencing** (2026-06-16T00:40:00Z, Scribe housekeeping):

**Phase 2 (C1 apply):** 2 adds (Azure-side route maps) + 2 changes (ER connections) = ~60 sec BGP flap. Estimated duration: 5–10 min. TF resources gated on Niobe completion of Design C asymmetric baseline evidence.

**Phase 3 (C2 apply) — GATED:** 1 add + 3 changes + 1 destroy = ~10–20 min vHub reprovision (hard gate). **Tank MUST await Niobe C1 evidence completion signal before proceeding.** (Per Trinity Mech C spec and Morpheus scope v2 checklist §6 hard gate.)

**Cost forecast (Team guidance):** Autopilot pre-approved ~$270-405; realistic C1+C2 sequential pipeline ~$675-810 (5-6 additional days at $135/day). Jose to be flagged on return with recommendation to trigger teardown as soon as money shots are captured.

**Key architectural input** (Trinity Mech C spec): Reserved ASN 23456 (AS_TRANS, IANA-reserved, 2-byte-compliant) chosen over private ASNs because it is (a) Route-Maps constraint-compatible, (b) instantly recognizable as intentional engineering marker in GCP and Azure output, (c) zero collision risk.

---

📌 Team update (2026-07-30T14:20:00Z): **XFRM Persistence Action Item from Niobe Audit.** After Phase 3 firewall failover/failback testing, Niobe flagged: NVAs in routemap-test-rg need a boot-time service to reload swanctl configuration and recreate xfrm (IPsec transform) interfaces after VM deallocation/reallocation cycles. Action: Tank to implement systemd service or cloud-init extension for Phase 4 mitigation in vwan-routemap-summarization lab. Affects: xfrm interface persistence, tunnel state recovery post-restart, lab robustness. Priority: Medium (failover scenarios work, but interface recovery automation needed for higher availability testing cycles).
