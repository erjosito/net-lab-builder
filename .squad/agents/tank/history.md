# Project Context

- **Owner:** Jose Moreno
- **Project:** net-lab-builder — build, document, and tear down ephemeral Azure Networking labs
- **Stack:** Bicep, Terraform, Azure CLI, PowerShell; Megaport API; Azure Key Vault (secret fetch via z keyvault secret show)
- **Created:** 2026-05-28
- **Role:** IaC Engineer — own src/{bicep,terraform,azure-cli,powershell}/ + labs/<lab>/deploy/; SKU defaults; 5-step ER cleanup chain (ER connection → ER private peering → Megaport VXCs → Megaport MCR → Azure RG)

**📌 SUMMARIZATION NOTE (2026-07-31):** This file has grown to ~17KB. Pre-Phase 3 learnings archived in `history-archive.md`. Active learnings (Phase 3 RI enablement, NVA restore, firewall ops) retained below.

## Summary (2026-06-15)

Tank completed three major infrastructure missions: Lab #1 multi-step cleanup automation (6-step charter-compliant ER teardown, Windows subprocess environment fix, KV access patterns), Lab #2 multi-cloud IaC scaffold (71 TF resources, 11 files, ~3h15m deploy, 6 iterations resolving multi-region SKU drift, routing-intent ordering, GCP ADC bootstrap, Megaport market pre-flight, vWAN ER connection shape conflicts), and patch/iteration learnings (secondary MCR↔ER VXCs for dual-port HA, GLOBAL-routing GCP VPC migration, ANSI code stripping in PowerShell TF output processing).

**Lab #1 (2026-05-28):** Established 6-step mandatory ER cleanup chain; fixed Windows subprocess environment variable isolation (inline HCL ternary-evaluated credentials bypass scope leakage); secured credential files and .gitignore patterns.

**Lab #2 IaC scaffold (2026-06-15):** Deployed fully multi-cloud lab (
g-vwan-symm-103167 + gcp-vwan-symm-103167, 71 resources) with per-region VM size variables (SKU catalog drift between swedencentral/northeurope), routing-intent dependency ordering, GCP provider aliasing, Megaport MCR market pre-flight validation, permissive AzFW RFC1918 rules for routing-intent=private flows. **Pre-deploy 	erraform plan with placeholder credentials is a valid graph-validation step** — confirms resource graph, inter-resource references, and conditional resources (bow-tie) build correctly before secrets are injected.

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

---

📌 Team update (2026-07-30T16:53:40Z): **Phase 3 Gate A Complete — nva1 Rebuild Action.** Niobe Gate A validation completed with CONDITIONAL PASS. Hub-eu2 (nva2) shows 6/6 route-map summaries, 0 /24 leaks, BGP Established. Hub-eu1 (nva1) control-plane config matches hub-eu2 exactly (all 6 route-map rules Succeeded, AzFW Succeeded) BUT **nva1 run-command extension is terminally stuck (Conflict/409), blocking XFRM restoration and BIRD access.** This is NOT a firewall-caused failure — extension fault pre-dates Phase 3 (persisted from failover/failback cycle #4). **ACTION REQUIRED FOR GATE A FULL PASS:** Rebuild nva1 VM (use `az vm redeploy` or `az vm delete + recreate` to clear stuck extension). After rebuild, Niobe will re-run hub-eu1 L2 measurement to confirm 6/6 summaries (inference: hub-eu1 likely shows same PASS as hub-eu2 given control-plane identity). **Blocking on nva1 rebuild:** Gate A full PASS, then proceed to Gate B (enable Routing Intent on hub-eu1 per Trinity's sequencing mandate). **Recommendation from Niobe:** Also implement the systemd XFRM-persistence service (see .squad/skills/vwan-nva-xfrm-restore/SKILL.md and prior note) to prevent similar extension blockers on next failover cycle. Gate evidence: show-output/13–20; decision merged to .squad/decisions.md; tech spike documented in .squad/skills/vwan-nva-xfrm-restore/SKILL.md.

**2026-07-30T19:11:00Z EOD NVA Shutdown:** Jose requested cost-cutting deallocate of nva1 and nva2 for overnight. Both NVAs deallocated via `az vm deallocate --no-wait` in parallel. nva2 (hub-eu2) reached "VM deallocated" state; nva1 (hub-eu1) in transition (stuck RunCommandLinux extension does not block fabric-level deallocate, will complete asynchronously). All firewalls, gateways, and ER infrastructure left untouched. Confirmation logged to `show-output/21-eod-nva-deallocate.txt`. Estimated daily compute cost savings: ~$65–75/day (both NVAs deallocated = ~$3–5/hr × 24h).

---

## Learnings — Phase 3 NVA Restart + Tunnel Restore (2026-07-31)

**Lab:** vwan-routemap-summarization | **RG:** routemap-test-rg

### nva1 Redeploy Outcome
- **`az vm redeploy` DID clear the stuck RunCommandLinux extension** — confirmed by `echo VM_ALIVE` returning cleanly after redeploy.
- **Duration in swedencentral: ~90 minutes** (far longer than typical ~10–15 min). The VM stayed in `ProvisioningState: Updating` for the full duration. Azure API itself was slow during this window (az vm list taking 30+ seconds). This appears to be infrastructure-level queue congestion in swedencentral, not a VM-specific issue.
- **Stuck extension persisted through dealloc/start cycles** — confirmed: extension state is on-disk and survives normal start/stop. Only a redeploy (host migration) clears it.
- **Post-redeploy run-command behaviour:** First run-command after redeploy took ~90s to return (agent warm-up on new host). Subsequent commands returned in normal ~30–45s.

### XFRM / IPsec State After Restart
- **Both nva1 and nva2:** After `swanctl --load-all`, `swanctl --initiate` returned "existing duplicate" for both CHILD_SAs (s2s0, s2s1). This means strongSwan (or the VPN GW side) had already re-established the tunnels before our explicit initiate. The `start_action=trap` or keepalive on the VPN GW side appears to have triggered rekeying automatically.
- **BGP Established within 75s** of XFRM interface creation + swanctl load on both NVAs — consistent with the skill's timing table.

### Final BGP State (2026-07-31T09:41:00+02:00)
| NVA | Hub | vpngw0 | vpngw1 | Routes |
|-----|-----|--------|--------|--------|
| nva2 | hub-eu2 (westeurope) | Established | Established | 35/26 networks |
| nva1 | hub-eu1 (swedencentral) | Established | Established | 37/27 networks |

### Gate Status
- **Niobe Gate A full re-run:** READY — both NVAs BGP Established. nva1 redeploy cleared blocker. Niobe can now re-run hub-eu1 L2 measurement for full Gate A PASS.

### xfrm-persistence Action Item
- The XFRM interface persistence gap (boot-time service) is still open. Both NVAs survive current cycle, but a systemd service would eliminate the need for manual restore. Deferred to Phase 4 mitigation per prior action item.

### File paths
- Restore capture: `labs/vwan-routemap-summarization/show-output/22-phase3-nva-restart-restore.txt`

---

## Learnings — Phase 3 Gate B: Routing Intent Enable on hub-eu1 (2026-07-31)

**Lab:** vwan-routemap-summarization | **RG:** routemap-test-rg

### RI Enablement Command (worked)
```bash
AZFW_EU1_ID=$(az network firewall show -g routemap-test-rg -n azfw-eu1 --query id -o tsv)
az network vhub routing-intent create \
  -g routemap-test-rg --vhub hub-eu1 -n hub-eu1-ri \
  --routing-policies "[{\"name\":\"PrivateTraffic\",\"destinations\":[\"PrivateTraffic\"],\"nextHop\":\"$AZFW_EU1_ID\"}]"
```
- Policy: **PrivateTraffic only** (NO InternetTraffic) — per design-phase3.md §4 table.
- CLI note: command is flagged `WARNING: This command is in preview` — still fully functional.
- `routing-intent create` is synchronous; returned `provisioningState: Succeeded` in ~6 minutes.

### Route Table Changes (PRE → POST RI)
- **PRE:** `routes: []` — empty. No static routes in defaultRouteTable.
- **POST:** `_policy_PrivateTraffic` entry with RFC1918 aggregates `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` → nextHop = azfw-eu1. Exactly as designed.
- **`propagatingConnections` cleared to `[]`** after RI — RI takes control of propagation; connections no longer appear in this field.

### Timing
- RI create (synchronous, hub reprovision included): ~6 minutes total.
- Both `hub-eu1-ri` provisioningState and `hub-eu1` hub provisioningState: Succeeded immediately after command returned.

### Gate Status
- RI deployed on hub-eu1. **Niobe Gate B: READY** — hand off to Niobe for hub-eu1 validation (6/6 summaries with RI active, BGP TCP through AzFW, no /24 leaks).

### File paths
- PRE-RI route table: `labs/vwan-routemap-summarization/show-output/31-gate-b-hub-eu1-routetable-PRE-ri.txt`
- RI enable output: `labs/vwan-routemap-summarization/show-output/32-gate-b-hub-eu1-ri-enable.txt`
- POST-RI route table: `labs/vwan-routemap-summarization/show-output/33-gate-b-hub-eu1-routetable-POST-ri.txt`

---

## Learnings — Phase 3 Gate C: Routing Intent Enable on hub-eu2 (2026-07-31)

**Lab:** vwan-routemap-summarization | **RG:** routemap-test-rg

### RI Enablement Command (worked)
Same pattern as hub-eu1, azfw-eu2 as nextHop:
```bash
AZFW_EU2_ID=$(az network firewall show -g routemap-test-rg -n azfw-eu2 --query id -o tsv)
az network vhub routing-intent create \
  -g routemap-test-rg --vhub hub-eu2 -n hub-eu2-ri \
  --routing-policies "[{\"name\":\"PrivateTraffic\",\"destinations\":[\"PrivateTraffic\"],\"nextHop\":\"$AZFW_EU2_ID\"}]"
```
- Policy: **PrivateTraffic only** — identical to hub-eu1 config.
- Provisioning time: **~8 minutes** (slightly longer than hub-eu1's ~6 min; both within normal range).

### Route Table Changes (PRE → POST RI)
- **PRE:** `routes: []`, `propagatingConnections` populated (3 connections: cx-onprem2, conn-er-eu2, cx-gcp2).
- **POST:** `_policy_PrivateTraffic` with RFC1918 aggregates (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`) → azfw-eu2. `propagatingConnections` cleared to `[]`. Matches hub-eu1 pattern exactly.

### PRIMARY REPRO STATE REACHED
Both hubs are now RI-enabled (PrivateTraffic). hub-eu2 carries `summarize-out` + `prepend-in` route-maps. This is the order-dependent condition the customer bug investigation requires. **Niobe Gate C** is the validation of whether 6/6 summaries survive with BOTH hubs under RI simultaneously.

### Timing Summary (both hubs)
| Hub | RI Create Time |
|-----|---------------|
| hub-eu1 (swedencentral) | ~6 minutes |
| hub-eu2 (westeurope) | ~8 minutes |

### File paths
- PRE-RI route table: `labs/vwan-routemap-summarization/show-output/40-gate-c-hub-eu2-routetable-PRE-ri.txt`
- RI enable output: `labs/vwan-routemap-summarization/show-output/41-gate-c-hub-eu2-ri-enable.txt`
- POST-RI route table: `labs/vwan-routemap-summarization/show-output/42-gate-c-hub-eu2-routetable-POST-ri.txt`

---

## Learnings — Teardown Step 1: ER Connections + RI + Firewalls (2026-07-31)

**Lab:** vwan-routemap-summarization | **RG:** routemap-test-rg

### ER Gateway Connection Delete
- Command: `az network express-route gateway connection delete --gateway-name <gw> -g <rg> -n <conn>`
- **`--yes` flag is NOT supported** on this command (returns "unrecognized arguments: --yes"). Drop it — command is non-interactive by default in non-TTY contexts.
- Both connections deleted synchronously; conn-er-eu1 ~7 min, conn-er-eu2 ~10 min.
- Verified via `az network express-route gateway connection list` returning `{"value": []}`.

### ER Circuit Peerings (Provider-owned)
- Both `er-eu1/AzurePrivatePeering` and `er-eu2/AzurePrivatePeering` show `lastModifiedBy: Provider`.
- These are Megaport-provisioned objects — **NOT directly deletable**. They clear when the ER circuit is deleted (step 5 RG delete). Leave for RG teardown.

### Routing Intent Teardown Sequence
- RI delete is a prerequisite for AzFW delete (FW cannot be deleted while referenced by RI).
- Use `az network vhub routing-intent delete -g <rg> --vhub <hub> -n <ri-name> --yes`.
- hub-eu1-ri: ~6 min to delete. hub-eu2-ri: ~8 min. Both synchronous operations.

### Firewall Deletion
- Use `az network firewall delete --no-wait` for parallel deletion (both hubs simultaneously).
- Both deleted within ~10 min of issue.
- Cost stop: ~$60/day eliminated.

### Cleanup Order Executed (steps 1 of 5)
| Step | Resource | Status |
|------|----------|--------|
| 1 | ER connections (conn-er-eu1, conn-er-eu2) | ✅ DELETED |
| 2 | ER peerings (Provider-owned) | ⏳ Deferred to RG delete |
| 3 | Megaport VXCs | ⏳ Link's job |
| 4 | Megaport MCR | ⏳ Link's job |
| 5 | Azure RG | ⏳ Final step (after Megaport) |

### File paths
- Evidence: `labs/vwan-routemap-summarization/show-output/50-teardown-er-conn-fw.txt`

---

📌 Team update (2026-07-31T11:01:11Z): **Phase 3 Gates A, B, C FULL PASS — Complete Testing Arc**. Gate A (firewall deploy, RI OFF): 6/6 summaries on both NVAs, 0 /24 leaks, BGP Established. Gate B (RI hub-eu1): 6/6 summaries intact, BGP transparent (session timestamps unchanged from Gate A). Gate C (RI hub-eu2, both hubs now RI-ON): 6/6 summaries survive, BGP stable across all three gates. Missing-summary bug NOT reproduced under sequential stable-state enablement. Root-cause analysis (Trinity): RI operates on data-plane forwarding table; `summarize-out` operates on BGP advertisement set — orthogonal planes. Gateway D concurrent-churn variant designed (dormant) to test race between RI policy-install and VPN connection rekey. Evidence: show-output/23–52. Decisions merged: tank-ri-eu1-enable, tank-ri-eu2-enable, niobe-gate-a/b/c, link-megaport-kv-retrieval, trinity-gate-c-analysis. Next: Jose direction on Gate D concurrent-churn variant.

---

## Learnings — Final Azure RG Teardown: routemap-test-rg (2026-07-31)

**Lab:** vwan-routemap-summarization | **RG:** routemap-test-rg (now DELETED)

### az group delete behaviour with vWAN + ER + AzFW
- `az group delete -n routemap-test-rg --yes` deleted all ~70 resources in a single blocking call.
- **Total elapsed: ~39 minutes** (16:42:51 → 17:22:12 UTC+2). Dominated by vWAN hub deprovision + ER gateway deletion. VPN gateways, ER gateways, and virtual hubs are the slow teardown path.
- ER circuits (`er-eu1`, `er-eu2`) and their provider-owned AzurePrivatePeerings were cleanly deleted by the RG delete (no manual peering teardown required — they were already disconnected from Megaport before this step).
- Azure Firewalls (AZFW_Hub SKU) do NOT appear in `az resource list -g <rg> -o table` output. They ARE present in the hub (confirmed by azureFirewall field on hub show). The RG delete handles them correctly despite the resource-list gap.
- Firewall policy `azfwpol-routemap-lab` IS surfaced by `az resource list`. Policy was deleted by RG delete after the hub firewalls were gone (platform handles dependency ordering automatically in RG delete).

### Prerequisite for clean RG delete (completed before this task)
- Megaport VXCs and MCRs fully decommissioned (by Jose/Link).
- ER gateway connections (`conn-er-eu1`, `conn-er-eu2`) deleted.
- Routing Intent deleted on hub-eu1 and hub-eu2.
- Azure Firewalls `azfw-eu1`, `azfw-eu2` deleted.
- These prerequisites avoided 409/conflict errors that would otherwise block hub/ER-circuit deletion.

### Post-delete verification
- `az group show -n routemap-test-rg` → `ResourceGroupNotFound` (exit 3) ✅
- `az network express-route list -g routemap-test-rg` → `ResourceGroupNotFound` (exit 3) ✅

### Evidence
- `labs/vwan-routemap-summarization/show-output/53-teardown-azure-rg.txt`

---

📌 Team update (2026-07-31T15:35:00Z): **LAB VWAN-ROUTEMAP-SUMMARIZATION FULLY DECOMMISSIONED.** All three clouds torn down in parallel session: Tank deleted Azure RG routemap-test-rg (39 min, ResourceGroupNotFound verified). Link decommissioned Megaport VXCs (CANCEL_NOW API, all jomore-copilot-* circuits gone, billing stopped) and GCP project vwan-routemap-lab (DELETE_REQUESTED, billing stopped). Trinity finalized README with teardown-status table (all rows ✅ DONE) and lab completion confirmation banner. 9 inbox decision files merged to .squad/decisions.md. Lab lifecycle: 2026-06-15 through 2026-07-31 (~6 weeks). Total cost: ~$4,200. Evidence preserved in show-output/ for blog/audit. No ongoing costs. Lab ready for publication and archive.



---

## 2026-08-03 — Lab #4 dual-hub-hubless-region-ars: IaC Authored + Validated

Bicep IaC complete. Preflight all 4 regions PASS. ARM validate PASS. NOT deployed.
Files: deploy/{templates/main.bicep,modules/,nva1/2-cloud-init.yaml,deploy.ps1,cleanup.ps1,parameters/,deploy-log.md}
Key decisions: Bicep; single-RG multi-region; ARS as virtualHubs + ipConfigurations child; PSKs in-process; BIRD multihop 4; VPN GW ASN=65515; b2b=true hub1/hub2 ARS; Δ3 not wired (S4 only).

---

## Learnings — Hub ARS Route-Map Upgrade (ars-hub1/ars-hub2) — 2026-08-05

**Lab:** dual-hub-hubless-region-ars | **RG:** rg-dual-hub-hubless-region-ars-lab3d001

### Route-map upgrade on hub ARS works (contrast with ars-poland failure)
- `ars-hub1` peer-nva1 IP `10.10.1.4` is within `vnet-hub1` (10.10.0.0/16) → same VNet as the ARS. `HubBgpConnectionFromSpokeVnetCannotReferenceRouteMap` does NOT fire.
- `ars-hub2` peer-nva2 IP `10.20.1.4` is within `vnet-hub2` (10.20.0.0/16) → same logic. Route maps are fully usable on hub ARS NVA peerings.
- The locality constraint only blocks cross-VNet multihop BGP peers (as ars-poland demonstrated).

### `az rest` body must use `@file` syntax on Windows
- `az rest --body '{"json":"inline"}'` works on Linux but caused `UnsupportedMediaType: null` errors on Windows PowerShell (Content-Type header not set correctly when body is a raw string).
- Correct pattern: write body to a `.json` file, then `az rest --body "@C:\full\path\to\body.json"`. This sets Content-Type automatically and works on Windows.
- The delta3 show-output `routemap-body.json` was the template to follow — same format works for hub ARS.

### Upgrade timing observed (concurrent triggers, ~30 min each)
- hub1 `Updating → Succeeded`: 22.4 min
- hub2 `Updating → Succeeded`: 25.7 min (triggered 23 seconds after hub1; both converged separately)
- Both within the documented ~30 min window. Triggering in parallel is safe.

### Activation map design (inert, idempotent)
- Map name pattern: `rm-<ars-name>-activate` (e.g. `rm-hub1-activate`)
- Rule: match RFC5737 TEST-NET `192.0.2.0/24` (Equals) → Add AS-Path [64496] → Terminate
- No `associatedInboundConnections` / `associatedOutboundConnections` → inert, no routing effect
- Body omits association arrays — API defaults to `[]`, confirmed in response.
- Idempotency: GET before PUT; if `provisioningState == Succeeded`, skip create.

### API version: 2024-10-01 confirmed required (not 2024-05-01)
- Both hub upgrades used `2024-10-01`. Confirmed as minimum for routeMaps sub-resource on ARS virtualHubs.

### Cost surcharge
- Each hub ARS now incurs route-map surcharge (~$6/day). Two hubs = ~$12/day additional on top of existing lab cost.
- Surcharge is irreversible without ARS recreate. Confirmed by prior ars-poland experience.

### Smoke-check after upgrade
- 4 VPN connections remain Connected ✅
- ARS peering provisioningState = Succeeded ✅
- ars-poland untouched ✅
- Hub learned routes remained empty (BIRD idle between scenarios — same as pre-upgrade, not upgrade-induced)

### Activation script saved
- `labs/dual-hub-hubless-region-ars/deploy/activate-hub-ars-routemaps.ps1` — idempotent, parallel, polls until Succeeded or 45-min timeout.

📌 Team update (2026-08-05T10:26:52.618+02:00): Hub ARS route-map upgrade decision merged; inert activation maps recorded without affecting live routing.
