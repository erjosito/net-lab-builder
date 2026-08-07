# Project Context

## 2026-08-06 — dual-hub-interconnect-ars-route-policy U1.5 + U2 EXECUTED (docs-only recovery)

- U1.5 and U2 were technically executed live in a prior turn whose final response/docs write-up was
  lost. Niobe independently verified the live Azure/NVA state as **COMPLETE PASS** (read-only,
  2026-08-06) — `.squad/decisions/inbox/niobe-u15-u2-verification.md`. This entry documents a
  **docs-only recovery**: no Azure CLI/REST command, VM run-command, BIRD command, route-map
  operation, peering mutation, or commit was (re-)run in this pass. Only markdown files and this
  history entry were written.
- **U1.5 result: PASS on both NVAs.** Graceful `birdc configure` on `vm-nva1` (2026-08-06T14:12:35Z)
  then `vm-nva2` (14:46:26Z) removed the retired Poland state — `route 10.30.0.0/27`,
  `protocol bgp ars_poland_0`/`_1`, `filter export_to_poland_ars` on both NVAs, plus the dead
  `10.31.0.0/24`/`10.32.0.0/24` prepend clause in `export_to_hub2_ars` on `vm-nva2` only.
  `systemctl restart bird` was never invoked. Exactly `10.30.0.0/27` was withdrawn from both
  instances of both Route Servers; `ars_hub1_0/1`/`ars_hub2_0/1` BGP `Since` timestamps are
  unchanged (no flap); gateway and on-prem learned/advertised sets are byte-identical; config gates
  (`bird -p -c`, `configure check`) passed before every apply. `nva-config/bird-nva{1,2}.u15-target.conf`
  are now the authoritative configs, matching the live hosts byte-for-byte.
- **U2 result: PASS.** Created `ars-hub1/routeMaps/rm-hub1-tmp-assoc` (rule matches
  `203.0.113.0/24`, an absent prefix) and associated it inbound on
  `ars-hub1/bgpConnections/peer-nva1` via a byte-preserving `PUT` (body derived from a fresh GET,
  `If-Match` etag; `vnetRoutes`/`staticRoutesConfig` preserved). PUT issued 15:52:35Z, `Succeeded`
  ~16:01:43Z. No route effect: B1→B2 diff across all 9 comparable capture files is zero
  (independently re-computed by Niobe). Hub2 and `rm-hub1-activate` untouched; all 4 VPN connections
  `Connected`; the association is **left ACTIVE** (not rolled back), which is required for U3a/U3b.
  **API trap:** `api-version=2024-05-01` omits `routingConfiguration` from the response and would
  make the association look absent — `2024-10-01`+ was used throughout.
- **Gate G4 CLOSED** — U2 produced `Succeeded` with the working body, satisfying G4's exact
  documented condition. **G1 and G3 remain OPEN** (Stage 1 not rolled back; fresh cost/deletion
  approval not requested). **U3–U5 remain not run/not approved**; U4's gateway-connection
  attachment remains separately unverified and is not implied by G4's closure.
- Run-rate unchanged: ≈$66–73/day plus the already-accounted-for +$0.58/day NVA compute increment
  from U0; no new route-map surcharge (the hub tier upgrade was already sunk).
- Docs updated (this pass): `deploy-log.md` (change log rows, approval-unit ledger, G1/G4 gate
  rows), `validation.md` (§U1.5, §T2a/U2 results), `README.md` (status banner, Phase-4 table,
  T1–T5 status table, Quick Links), `manifest.md` (approval-unit table, approval gate ledger, T2a
  narrative), `design.md` (execution addendum after §8a(d-correction)), `lessons-learned.md`
  (`TANK-001` remediation confirmed executed, `TRIN-001` confirmed applied + API-version trap
  noted). No git commit made, per instruction.
- Decision inbox written: `.squad/decisions/inbox/tank-u15-u2-execution.md`, referencing Niobe's
  independent verification. Next approval gate: **U3a/U3b**.

## 2026-08-05 — storage-endpoint-path-equivalence Translator redesign deployed

- Implemented the explicitly approved Azure AI Translator F0 redesign in the existing `rg-storage-sepath-0805175837` lab bed.
- Reused the VM/disk/NIC, VNet/subnets, NAT Gateway/PIP, NSG, Log Analytics workspace, flow-log Storage account, and VNet flow log.
- Deleted only the approved blocked experiment resources: target/decoy Storage accounts, Blob PE/NIC, Blob private DNS artifacts, and Storage service endpoint policy.
- Deployed Translator F0 with local auth disabled, VM `Cognitive Services User` RBAC, diagnostics, replacement PE at `10.61.2.4`, and `privatelink.cognitiveservices.azure.com`.
- Replaced the Storage NSG destination with `CognitiveServicesFrontend` and added idempotent Public/ServiceEndpoint/Restricted/Private/PrivateOnly state transitions.
- Installed a keyless managed-identity probe on the VM. HTTP 200 smoke validation passed for public, service-endpoint, restricted-subnet, and private modes. No full benchmark was run.
- Restored the R1 public baseline and deallocated the VM. Niobe is unblocked. Cleanup was not run.
- Sanitized evidence: `labs/storage-endpoint-path-equivalence/raw-output/sepath-20260805-175837/11-translator-redesign-deployment.json` and `12-translator-redesign-inventory.json`.

## 2026-08-06 — dual-hub-interconnect-ars-route-policy U0 + conditional U1 EXECUTED

- Executed the approved (Jose Moreno) activation `U0 + conditional U1`, strictly scoped: started `vm-nva1` + `vm-nva2` only (U0), validated the U1 hard gate (BIRD route-refresh capability, both ARS peerings Established), and — gate PASSED — created exactly `peer-hub1-to-hub2` / `peer-hub2-to-hub1` (U1) with the exact required flags (`vna=T, fwd=T, gwt=F, urg=F`).
- **U0 result: PASS-with-note.** Both VMs `VM running`; `ars_hub1_0/1`/`ars_hub2_0/1` Established; route-refresh capability confirmed both sides both hubs; all 4 VPN connections Connected; `ars_poland_0/1` in `Connect` as expected. New finding `TANK-001`: both NVAs' hand-edited `bird.conf` (not in version control) re-originate a stale `10.30.0.0/27` (Poland-shaped) static route into ARS — confirmed contained (absent from ARS advertised-back, `vpngw-hub1/2`, and `vpngw-onprem` learned routes) and non-blocking, but it corrects the manifest's assumption that NVA1 "re-originates `10.10.0.64/27`" (that prefix does not actually appear in ARS's learned-routes set).
- **U1 (T1) result: PASS.** Both peerings `Connected`/`FullyInSync`, stable at a T+~20min re-check. `vm-nva1` (10.10.1.4) ↔ `vm-nva2` (10.20.1.4): 0% ICMP loss both directions post-peering (100% pre-peering). Non-transitivity proven via byte-identical pre/post diffs on ARS learned/advertised (both hubs), `vpngw-hub1` advertised-to-onprem, `vpngw-onprem` learned, and VPN connection statuses. Each NVA NIC gained exactly one new `VNetGlobalPeering` route (remote hub `/16`) and nothing else. Confirmed no route-map association exists (T2/U2 untouched).
- Strict scope discipline maintained: no U2–U5, no route-map/BIRD edit, no other VM touched, no VPN connection change, no deletion, no git commit. No rollback triggered — both VMs and both peerings remain live as the approved end-state.
- Cost/timing: +$0.58/day (U0, VM compute) while running; ≈$0.00 incremental data cost (U1); ≈75 min wall clock end-to-end (dominated by `az vm run-command invoke` latency, ~1.5–3+ min per BIRD query); the underlying Azure operations (VM start, peering create) each completed under 3 min.
- Evidence: `labs/dual-hub-interconnect-ars-route-policy/show-output/new/u0-u1/{pre,post-u0,pre-u1,post-u1}/`, one command per file, sanitized (grep-verified zero raw subscription/tenant IDs).
- Docs updated: `validation.md` (§U0/§T1 actual results), `deploy-log.md` (change log, approval-unit ledger, G1 partial-progress note — not claiming full bow-tie), `README.md` (status + Phase-4 table), `design.md` (§8a(c)-correction on the stale-route finding), `lessons-learned.md` (`TANK-001` stale-route finding, `TANK-002` run-command backgrounding limitation, `TANK-003` `az group list --query` parsing quirk), and source lab `dual-hub-hubless-region-ars/deploy-log.md` (VM power-state update note, ownership-contract-respecting).
- Two minor tooling findings for future reference: `az vm run-command invoke` does not properly detach `nohup ... &` background processes (worked around with blocking ping tests instead of a continuous probe); `az group list --query "[?contains(...)]" -o tsv` fails to parse on this Windows setup (worked around with `-o table | Select-String`).
- Next approval gate: **U2/T2a** (inert route-map association on `ars-hub1`/`peer-nva1` only, dedicated `rm-hub1-tmp-assoc`) — remains unapproved, not executed. Recommend Trinity/Morpheus review the `TANK-001` correction to the manifest's `10.10.0.64/27` assumption before U2/T2b is planned.
- Decision inbox written: `.squad/decisions/inbox/tank-u0-u1-execution.md`. No git commit made, per instruction.

## 2026-08-06 — storage-endpoint-path-equivalence redesign hold

- Issued an idempotent deallocation request only for `vm-client` in `rg-storage-sepath-0805175837`; it was already deallocated and remained verified as `VM deallocated` / provisioning `Succeeded`.
- Preserved the OS disk, NIC, VM configuration, all other resources, and all security controls.
- Recorded sanitized evidence in `labs/storage-endpoint-path-equivalence/raw-output/sepath-20260805-175837/vm-client-deallocate-20260806T070053Z.json` and updated `deployment.md`.
- Remaining notable cost sources: NAT Gateway/Public IP, Private Endpoint, managed disk, storage accounts, Log Analytics/flow logs, and potential Defender for Storage charges.

## 2026-08-05 — storage-endpoint-path-equivalence Phase 4

- Implemented Bicep + PowerShell deploy/cleanup tooling under `labs/storage-endpoint-path-equivalence/deploy/`.
- Reconfirmed `Standard_B2ts_v2` in `swedencentral`: catalog PASS and live `az vm create --validate` PASS; temporary preflight RG removed.
- ARM deployment `sepath-0805175837` in `rg-storage-sepath-0805175837` succeeded. VM running; PE Approved; diagnostics and VNet flow log enabled; NSG attached after cloud-init bootstrap.
- Material runtime blocker: Defender for Storage security automation forces both experiment accounts to `publicNetworkAccess=Disabled`. CLI and REST writes could not retain `Enabled`; activity logs identify `StorageAccounts/securityOperators/DefenderForStorageSecurityOperator`.
- Stopped before blob upload and experimental state transitions. SE off, endpoint policy detached, private DNS unlinked. No cleanup. Niobe blocked pending exemption or redesign.
- Sanitized evidence: `labs/storage-endpoint-path-equivalence/raw-output/sepath-20260805-175837/`; status/resume commands: `deployment.md`.

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

---

## Learnings — US10 Bow-Tie Revision (independent replacement author) — 2026-08-05

Rejected artifact `US10-bow-tie-dual-site-regional-affinity` in
`labs/dual-hub-hubless-region-ars/route-map-user-stories.md` rewritten by me after my own review
verdict REJECTED it. Morpheus and Trinity both locked out; neither consulted. Scope: US10 section
plus its comparison-matrix and diagram-index rows only. No Azure changes, no IaC changes, no
diagrams, no experiments, no commit.

### B1 — Route Server is never a forwarding hop
- Learn (Route Server FAQ) is unambiguous: ARS exchanges BGP routes only; data traffic goes directly
  from the NVA to the destination. The rejected draft drew `vpngw-hub2 → ars-hub2 → vm-nva2` in the
  failure inset — an impossible chain.
- Fix: added a **plane convention** table to the story; both diagram specs now mandate **thick
  data-plane edges** vs **thin dashed control-plane edges**, and every path table lists forwarding
  hops only. `ars-*` appears exclusively on thin edges.
- Rule to carry forward: any path table row containing an `ars-` node is a defect, full stop.

### B2 — Poland Central gateway SKU/zone preflight
- `vpngw-onprem2` corrected to **`VpnGw1AZ`**; its two Standard PIPs must be created with
  **zones 1,2,3** *before* the gateway.
- Added a 5-step preflight gate. Key point recorded from deploy-log §7: ARM `validate` / `what-if`
  does **not** catch `NonAzSkusNotAllowedForVPNGateway` or
  `VmssVpnGatewayPublicIpsMustHaveZonesConfigured` — both are create-time-only failures. A green
  what-if is not evidence here.

### B3 — Run-rate corrected
- Stale $72/day figure removed. Current run-rate is **≈ $84/day** (≈ $65.86/day baseline +
  3 × ≈ $6/day route-map surcharge, after `ars-poland`, `ars-hub1`, `ars-hub2` upgrades).
- US10 target stated as **≈ $95+/day**, explicitly a *floor* pending a current `VpnGw1AZ` retail
  lookup for `polandcentral`. No exactness claimed. Fresh explicit approval gate preserved — the
  existing $72/day waiver covers neither figure.

### B4 — ASN discipline separated per test bed
- Generic ER story now **requires a real customer-owned public ASN** for prepending. 64496 (and all
  of 64496–64511) is IANA documentation-only and must never touch an ER AS_PATH; private ASNs are
  stripped by the MSEE anyway (`azure/expressroute/expressroute-routing`).
- Documentation ASN 64496 retained **only** in the closed lab VPN analogue, matching the Δ3
  activation contract and the existing inert `rm-hub1-activate` / `rm-hub2-activate` maps.
- The two test beds are now visually and textually separated so the ASN rules cannot be mixed.

### B5 — Named attachments + mandatory pre-activation experiment
- Candidate maps named explicitly: **RM-A** `ars-hub1`↔`peer-nva1` (proven eligible), **RM-B**
  `ars-hub2`↔`peer-nva2` (proven eligible), **RM-C/RM-D** VPN gateway connections (**unverified**),
  **RM-X** `ars-poland` (proven ineligible — EMP-001 peer-locality constraint).
- New stage **S2 pre-activation experiment**, gated on explicit user approval because association
  may reset BGP: **E-1** inert TEST-NET map on `ars-hub1`↔`peer-nva1`, then **E-2** independent test
  of eligible local VPN gateway connection association using the real resource/API semantics
  (`routingConfiguration.inboundRouteMap` on the ARS bgpConnection child, API `2024-10-01`).
- Explicitly **not** called zero-disruption and **not** executed. No expansion funding and no
  activation proceeds until support is evidenced.
- If gateway-connection association turns out to be unsupported, US10 is retained but Azure-side
  route-map value reclassifies to "ARS↔NVA peerings only", with the on-prem-facing function moved to
  NVA/CPE policy.

### Cautions
1. Global peering create/delete triggers an ARS BGP **soft reset** (hard reset if the NVA lacks route
   refresh — Learn warns this "might cause connectivity disruption"). Maintenance window plus
   before/after/+5 min captures and continuous ping now required.
2. Tunnel import/export prefix policy specified explicitly. **`0.0.0.0/0` excluded unconditionally**
   in both directions, plus set-C 10.31.0.0/24 and 10.32.0.0/24, so Poland's Δ3 default-route
   experiment cannot gain extra copies. Backup-site prefixes permitted but prepended ×2.
3. Set-C behaviour corrected: prefixes can still transit hub2 → `vpngw-onprem2` → DCI → `vpngw-onprem`.
   Both AS paths shown (`65515-65001` unchanged vs `65003-65515-65002-65002-65002`); Δ2 evidence
   *changes shape* (2-vs-4 becomes 2-vs-5) rather than disappearing. Flagged as an assertion to
   measure, with PASS and ALT/FAIL branches — it depends on `vpngw-onprem2` re-advertising between
   its two BGP connections, which this lab has not proven.
4. Citation mapping corrected: the FAQ MSEE bow-tie diagram is a *different* shape and is cited only
   as the reason a shared-MSEE hairpin is not a substitute — never as proof of the separate-circuit
   diagonal design. `as-override` described strictly as the sanctioned mitigation in the dual-homed /
   same-ASN pattern (`azure/route-server/about-dual-homed-network`, plus the 65515 rewrite in
   `azure/route-server/multiregion`). Global Reach preserved as a valid on-prem DCI alternative while
   stating plainly that it joins sites, not hub VNets.
5. Traceroute demoted to secondary/indicative. Primary symmetry proof is now simultaneous NVA packet
   captures on tunnel and LAN interfaces filtered on probe identity, plus interface/firewall counters
   (`ip -s link`, `nft`/`iptables`) correlated at both NVAs, plus gateway/Route Server RIB evidence.
6. Every advertised-route collection line now carries `--peer <bgp-peer-ip>` — it is a **required**
   parameter of `az network vnet-gateway list-advertised-routes`. Peers enumerated first via
   `list-bgp-peer-status`, repeated per peer including both active-active instance peers.

### Classification retained
`requires disruptive topology change` kept, but the stage table now splits it precisely:
S0/S1 additive and fully reversible · S2 pre-activation experiment (approval-gated) ·
S3 the single disruptive step (deleting the `vnet-onprem`↔`vnet-hub2` connection pair that carries
the Δ2 and S2/S3 evidence in its direct-adjacency form) · S4 rollback sequence.

### Diagram IDs (stable, Oracle owns authoring)
`US10-bow-tie-generic-er` · `US10-bow-tie-lab-vpn-analogue`

### Operator notes
- Wrote the replacement section to a scratch file, spliced by line range (kept 1–570 and the
  post-US10 tail verbatim), then deleted the scratch. US01–US09 bodies untouched; only the US10
  matrix row, the applicability/cost-note paragraphs and the two diagram-index rows changed.
- References section gained only what I verified this session: `about-dual-homed-network`,
  `create-zone-redundant-vnet-gateway`, and the CLI `--peer` requirement.
- No citation added for anything unexecuted. No association claimed to work.

📌 Decision inbox written: `.squad/decisions/inbox/tank-us10-revision.md`

---

📌 2026-08-05T13:43:07.691+02:00 — Scribe merge pass: US10 revision brief recorded in decisions.md; no lab/design file staging occurred.

---

## TP-HH two-region extraction build (2026-08-05T16:00)

Executed Morpheus's approved US10+US11 extraction contract plus Jose's broader full-build task:
created `labs/dual-hub-interconnect-ars-route-policy/` as a documentation-only test-program
composition of Sweden Central + Switzerland North retained stories. Zero Azure commands executed,
zero live resources touched, nothing committed.

**Built:** 6 core artifacts (README/manifest/design/validation/lessons-learned/deploy-log), 5 `.mmd`
diagrams (3 extracted verbatim + 2 authored, all validated via cached `mmdc`, no new installs), 25
inherited evidence files (copied with provenance headers, originals untouched — verified via
`git status`), paired gated `apply.ps1`/`rollback.ps1` skeletons (no live `az` commands, all
commented out) + 4 placeholder request-body JSONs, 5 `show-output/new/` scenario placeholders, and
one additive cross-link line in the source lab's README (only edit to the source lab).

**Key fix:** `[CmdletBinding(SupportsShouldProcess = $true)]` auto-injects `-WhatIf`/`-Confirm`;
a custom `[switch]$Confirm` param collides with it at **runtime only** (static `Parser::ParseFile`
does not catch it) — renamed the custom approval gate to `-ApprovalConfirmed` in both scripts and
re-tested all 4 gate cases (wrong RG / placeholder subscription / missing approval / all-gates-pass)
functionally, not just via syntax check.

**Validation:** full sanitization scan (0 subscription/tenant IDs; secret-pattern hits are
descriptive-only, no real values; poland/set-C/10.30-32 hits are all exclusion/contrast/deny-filter
notes or factual unmodified BGP evidence content, none in diagram nodes); 55/55 relative links
resolve; 25/25 evidence files carry provenance headers; no bicep/ARM/parameters copied; no migration
gaps (all 25 files in Morpheus's file-action table found and copied).

📌 Decision inbox written: `.squad/decisions/inbox/tank-two-region-extraction.md`

---

## Poland cleanup deletion preview — DRY RUN ONLY — 2026-08-05T16:00

Jose authorized *investigating and previewing* removal of Poland Central resources from the shared
live RG `rg-dual-hub-hubless-region-ars-lab3d001`. Task was explicit: dry-run only, no mutation.
Executed **zero** delete/update/stop/resize/disassociate/deallocate commands — only `show`, `list`,
and `az rest --method GET` (read-only) against the live subscription. No commit made.

**Live inventory confirmed (read-only):** 61 top-level ARM objects, 20 VNet peerings, 3 ARS with 3
BGP peerings + 2 route-map objects total — cross-checked against `manifest.md`, `main.bicep`, and
`deploy-log.md`. Everything matched expected scope with two flagged discrepancies: (1) no Poland
route table exists (manifest's "2 Route Tables" are `rt-spoke-a`/`rt-spoke-b` only — set-C uses
ARS-injected `0.0.0.0/0`, no UDR); (2) `ars-poland` currently shows **zero** live route-map child
objects via ARM REST (`routeMaps?api-version=2024-10-01`), while `.squad/agents/tank/history.md`'s
own B3 note claims the route-map surcharge already applies to all 3 ARS including poland — carried
into the cost estimate as an unresolved uncertainty (±$6/day), not silently resolved either way.

**Delete-list scope (29 objects, none deleted):** `ars-poland` + its 2 BGP peerings; `vnet-poland-ars`
/ `vnet-spoke-c1` / `vnet-spoke-c2` + their 10 own peerings (auto-removed with the VNet); `vm-c1-ep`
+ NIC + disk + 2 extensions (auto-removed with the VM); `pip-ars-poland`; `nsg-ep-poland`; and the 6
Poland-facing peerings living on the **preserved** `vnet-hub1`/`vnet-hub2` VNets
(`peer-hub1-to-poland`, `peer-hub1-to-spoke-c1`, `peer-hub1-to-spoke-c2`, `peer-hub2-to-poland`,
`peer-hub2-to-spoke-c1`, `peer-hub2-to-spoke-c2`) — the exact nested/dependent case the task flagged.
Confirmed via live peering list that `ars-hub1`/`ars-hub2` BGP connections never reference Poland
(each has exactly 1 peering, to its own local NVA only) — so no hub1/hub2 Route Server, VPN gateway,
NVA, or set-A/set-B spoke needed touching.

**Ordering correction found from live evidence, not assumption:** `nsg-ep-poland` is **subnet-**
associated to `vnet-spoke-c1/snet-workload`, not NIC-associated (`nic-vm-c1-ep`'s `networkSecurityGroup`
field is `null`). This means the NSG delete must come **after** the VNet delete, not before it as a
generic "NSG-then-VNet" template would assume — Azure blocks NSG deletion while a subnet association
exists. Documented explicitly in the deletion-order stage table with the evidence citation.

**Cost estimate (approximate, MEDIUM/LOW confidence):** Poland's share of the current ≈$84/day
run-rate is ≈$11.51-17.51/day (ARS 1/3 share + PIP + VM compute/disk shares, ± the unresolved
route-map surcharge above) — roughly a 14-21% reduction, ≈$345-525/month. Explicitly not claimed as
precise; per-unit shares are lab-wide totals divided by count, not independently retail-priced.

**Artifacts:** `labs/dual-hub-hubless-region-ars/cleanup-poland-dry-run.md` (full delete list,
preserve list, dependency order, impact, rollback reality, cost estimate, hard confirmation gate);
9 sanitized read-only captures under `labs/dual-hub-hubless-region-ars/show-output/
cleanup-poland-dry-run/` (one command per file, provenance headers, subscription ID redacted
everywhere); one-line planned-cleanup callout added to both the source lab README and the two-region
lab README (ownership clarity only — no resource marked deleted).

**Validation no mutation occurred:** pre/post `az resource list` counts identical (61, same type
breakdown); pre/post peering counts on `vnet-hub1` and `vnet-poland-ars` identical (4 each); `git
diff --stat` shows only the two README edits plus new untracked files (the dry-run doc, its
show-output captures, this history entry, the decision inbox) — no existing IaC, manifest,
deploy-log, or evidence file modified. No commit.

📌 Decision inbox written: `.squad/decisions/inbox/tank-poland-cleanup-preview.md`

## Poland cleanup EXECUTED — 2026-08-05T~19:15+02:00

Structured confirmation ("Confirm deletion of the exact 29-object dry-run list" against
`cleanup-poland-dry-run.md`, for `rg-dual-hub-hubless-region-ars-lab3d001`) received and honored.
Executed the exact §2 delete list from the dry-run, Stages 1→4b, no reordering beyond what the
dry-run itself already documented. **Result: 29/29 objects deleted, zero failures, zero retries.**

- Stage 1: 6 remote-side peerings on `vnet-hub1`/`vnet-hub2` pointing at Poland — all exit 0.
- Stage 2: `peer-nva1`/`peer-nva2` (ars-poland BGP peerings), then `ars-poland` itself — all exit 0;
  the Route Server delete took ~25 min (longer than manifest's ~10 min estimate; documented, not a
  scope deviation).
- Stage 3: `vm-c1-ep` (+2 auto-removed extensions), `nic-vm-c1-ep`, `osdisk-vm-c1-ep`,
  `pip-ars-poland` — all exit 0. `vm-c1-ep` (and, discovered live, all 5 other preserved VMs) were
  already `deallocated` at task start — a pre-existing lab-wide condition, documented as a
  non-blocking deviation (Stage-0 ping/effective-route-table captures could not run).
- Stage 4/4b: `vnet-spoke-c1`, `vnet-spoke-c2`, `vnet-poland-ars` (+10 auto-removed nested
  peerings), then `nsg-ep-poland` after the VNets (subnet-associated, not NIC-associated, per the
  dry-run's live-evidence ordering correction) — all exit 0.

**Post-delete verification (all matched expectation exactly):** resource count 61→50; region
breakdown swedencentral=20/switzerlandnorth=19/norwayeast=11/polandcentral=0; `vnet-hub1` and
`vnet-hub2` each retain exactly their one non-Poland peering; `ars-hub1`/`ars-hub2` (2 remain) each
keep their unchanged 1 BGP peering + 1 inert route map (`rm-hub1-activate`/`rm-hub2-activate`); 3
VPN gateways `Succeeded`; 4/4 VPN connections `Connected`; 5 VMs/NICs/disks remain (matching the
expected set); 5 NSGs (was 6); RG present, `Succeeded`, tags unchanged. Duration ≈65 min end-to-end
(dominated by the ARS delete).

**Hard safety rules honored throughout:** RG never targeted; no wildcard/recursive/tag-wide/
location-wide command issued (every command named one resource with `-g/-n` or parent flags); all 6
remote-side peerings were the exact named objects from the approved list; hub1/hub2 Route Servers +
inert route maps, both NVAs, VPN gateways, set-A/set-B spokes, on-prem resources, and the shared RG
were all preserved and independently re-verified healthy post-delete.

**Docs updated (source lab):** `cleanup-poland-dry-run.md` (status → Executed, §10 appended with the
full executed-result record; §0-§9 preserved unedited as the original proposal), `README.md`
("Planned cleanup" callout → "Poland Central retirement — EXECUTED"), `deploy-log.md` (new dated
"Poland Central Cleanup — EXECUTED" section), `lessons-learned.md` (update note on the ARS cost
lesson — surcharge now moot, deletion not recreation), `validation.md` (new top note: S4/S5 now
permanently non-repeatable in this bed; historical results preserved unchanged, not rewritten).
`manifest.md` intentionally **not** edited — its Resource Inventory/Cleanup Sequence/Cost sections
were flagged in the dry-run as a follow-up for a Morpheus/Trinity pass, out of this task's scope.

**Docs updated (two-region `dual-hub-interconnect-ars-route-policy` lab):** `README.md` (Poland
scope note → retired/deleted; cost callout → ≈$66-73/day post-retirement; G2 gate marked satisfied
in prose and in the Mermaid diagram node; G3 gate's "$84/day now" comparator corrected), `deploy-log.md`
(G2 stage-gate row → `CLOSED`, dated, evidenced; G3 row's run-rate comparator corrected). This lab's
own scenarios (T1-T5) were never dependent on Poland and remain unaffected — confirmed by the
post-delete verification.

**Revised run-rate:** ≈$66-73/day (down from ≈$84/day), unchanged from the dry-run's own §7 estimate
— the deletion executed exactly as previewed, so no re-derivation was needed. The previously
unresolved `ars-poland` route-map-surcharge uncertainty is now moot (the resource no longer exists).

**Evidence:** `labs/dual-hub-hubless-region-ars/show-output/cleanup-poland-execution/` — `pre/`
(4 baseline capture files), `01`-`04` (one file per stage, command + result), `post/05` (full
post-delete verification). All sanitized (`<SUBSCRIPTION_ID>` pattern maintained; grep-verified zero
raw subscription/tenant IDs in any new file).

**Stage-2 gate G2 (two-region lab):** can be marked **satisfied/CLOSED** — Poland cleanup status is
now known and recorded (executed), which is all G2 requires; G1/G3/G4 remain open and are unaffected
by this task.

No git commit made, per instruction.

📌 Decision inbox written: `.squad/decisions/inbox/tank-poland-cleanup-executed.md`
