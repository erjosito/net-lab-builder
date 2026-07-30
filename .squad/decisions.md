System.Object[]

## Active Decisions

> No active decisions currently. See decisions-archive.md for previous decisions.

System.Object[]
### 2026-06-16T08:30:00+02:00: Reserved-ASN choice — switch 23456 → 64496 for VWAN route-map prepend
**By:** Jose (via Copilot)
**What:** Changed the Mech C1 outbound route-map prepend ASN from AS_TRANS (23456) to RFC 5398 documentation ASN 64496 (range 64496-64511).
**Why:** AS 23456 (AS_TRANS, RFC 4893) has operational meaning during 4-byte-ASN transition: 2-byte-only BGP speakers substitute 23456 into AS_PATH for any 4-byte ASN they cannot represent. Artificially prepending 23456 could collide with/confuse that transition machinery and any diagnostics or BGP policy that treats 23456 specially. RFC 5398 ASNs (64496-64511 for 2-byte; 65536-65551 for 4-byte) are reserved purely for documentation and example code, carry zero operational semantics, and are therefore the cleanest pedagogical choice for a lab + blog.
**Validation:**
- Confirmed Azure Route Maps ACCEPTS 64496 (test route map → provisioningState=Succeeded; deleted after test).
- Confirmed live at GCP Cloud Router after TF apply: Hub1 prefixes best via MCR1 (65001 12076, 2 hops), MCR2 path = (65002 12076 64496 64496 64496); Hub2 prefixes best via MCR2, MCR1 path = (65001 12076 64496 64496 64496 65520 65520). Identical routing behavior to 23456.
- TF delta: 0 add, 2 change, 0 destroy (in-place route-map update; ~no hub reprovision; BGP reconverged within ~60s).
**Azure Route Maps ASN constraints (still apply):** 2-byte only; no private (64512-65534); no Azure-reserved (8074, 8075, 12076, 65515, 65517-65520). 64496 satisfies all three.
**Implication for C2:** Use 64496 (×5) for the Mech C2 prepend too — keep ASN consistent across both mechanisms for blog clarity.
**Quote:** "I meant the range 64496–64511. When you have time, could you check if these also work?" + "I wonder whether using 23456 could have negative effects for a later transition to 4-byte ASNs"
# Niobe → Team: Mech C1 Evidence Complete — 2026-06-16

**From:** Niobe (Validation)  
**Date:** 2026-06-16T08:45+02:00  
**Re:** Design C Mech C1 (VWAN outbound route maps, AS-path de-pref) — 4-tier evidence capture  

## Evidence Location

`labs/vwan-dual-er-symmetric/show-output/design-c-mechC1-symmetric-2026-06-16/`

15 files (01–14 + README.md). See `14-verdict.md` for full analysis.

## Verdict Badge

⚠️ **PARTIAL SYMMETRIC**

## Key Findings

### ASN Update (08:55)
Route maps switched from AS 23456 (AS_TRANS — carries 4-byte-ASN transition semantics) to **AS 64496** (RFC 5398 documentation range, semantics-free). Control-plane files 01–04 re-captured post-reconvergence. Mechanism behaviour unchanged.

### 2. AzFW Cross-contamination (KEY METRIC)
| Condition | Hub1 AzFW sees Hub2 spoke | Hub2 AzFW sees Hub1 spoke |
|-----------|--------------------------|--------------------------|
| **Before (asymmetric baseline, 06-15)** | 54 flows | 54 flows |
| **After Mech C1 (06-16)** | **1 flow** | **1 flow** |
| **Change** | **-98%** | **-98%** |

### 2. GCP ECMP Finding (CRITICAL for blog)

GCP Cloud Router does NOT apply AS-path length as a tiebreaker for ECMP. Even with 2 vs 7 hop difference (due to 23456×3 prepend), the router installs BOTH paths in `bestRoutes` for /24 prefixes. Only /23 aggregates are single-path.

Evidence: `01-cr-status-full.json` + `02-cr-routes-summary.txt`

This means:
- /23 supernets (10.10.0.0/23, 10.20.0.0/23): ✅ Single-path, MCR1/MCR2 exclusive
- /24 prefixes (10.11.0.0/24 etc.): ⚠️ ECMP across both MCRs regardless of AS-path length

### 3. Data Plane Impact

spoke3 → vm_a: 2/5 TCP success (vs spoke1 → vm_a: 4/5). The 3 timeouts from spoke3 are data-plane proof of GCP ECMP for /24 routes creating TCP session asymmetry.

### 4. Megaport LG

No looking glass API endpoint exists (HTTP 404 for all tested variants). MCR1 and MCR2 product info captured instead — both LIVE, all active VXCs up.

## Recommendations for Tank Phase 3

To achieve full symmetry (0 cross-contamination), options are:
1. **Mech C2:** GCP-side path preference via BGP MED or local-preference on GCP Cloud Router
2. **Mech C3:** Suppress /24 advertisements from Azure hubs (advertise /23 aggregates only) — prevents GCP from installing /24 ECMP routes
3. **Accept partial:** Document GCP ECMP as a known limitation; for the blog, 98% reduction + single-path supernets may be sufficient to call the mechanism "effective"

## Hand-off Status

Evidence is complete and committed. Niobe signs off on Mech C1 capture. Ready for Tank Phase 3 or blog handoff to Kid.
# niobe-phase3-audit — Live State of routemap-test-rg

**Author:** Niobe  
**Date:** 2026-07-30T13:48:36+02:00  
**Lab:** vwan-routemap-summarization  
**Context:** Jose asked whether we are in Phase 3 (Azure Firewalls + Routing Intent). Niobe audited the live subscription, ran failover/failback cycle #4 on nva2.

---

## Finding 1 — Phase 3 NOT started (confirmed)

No Azure Firewall, no Firewall Policy, and no Routing Intent exists in `routemap-test-rg`.  
All 3 hubs (hub-us, hub-eu1, hub-eu2) are non-secured: `azureFirewall = null`, `securityProviderName = null`.  
Evidence: `show-output/09-phase3-audit-firewalls-and-routing-intent.txt`

**Decision implication:** Phase 3 work cannot begin until the team explicitly decides to start it. Tank/Morpheus must scope it.

---

## Finding 2 — Phase 2 IS fully deployed (documentation gap)

**CRITICAL DOCUMENTATION GAP:** README.md and manifest.md both show Phase 2 as "Not started". This is WRONG.

Phase 2 is fully deployed and connected:
| Resource | State |
|----------|-------|
| er-eu1 (swedencentral) | Enabled / Provisioned |
| er-eu2 (westeurope) | Enabled / Provisioned |
| ergw-eu1 | Succeeded — `conn-er-eu1` CONNECTED |
| ergw-eu2 | Succeeded — `conn-er-eu2` CONNECTED |
| site-gcp1 / site-gcp2 | VPN sites for GCP legs (Succeeded) |

Route evidence: nva2 BIRD table shows routes with ER AS paths (12076/133937) during failback test.

**Root cause of earlier incorrect report:** First audit used `--query "connections"` on ER gateway; the correct field is `expressRouteConnections`. Corrected in `show-output/11`.

**Action needed:** Tank/Kid to update README "Designs studied" table: Phase 2 → "Deployed / validated (Phase 1 NO REPRO)".

---

## Finding 3 — Failover/failback cycle #4: CLEAN

Ran on nva2 (hub-eu2) in Phase 2 state. 6/6 summaries before and after 45s failover window.
Evidence: `show-output/12-failover-failback-cycle4-nva2.txt`

nva1 NOT tested — stuck run-command extension blocked all attempts.

---

## Finding 4 — XFRM persistence gap (action for Tank)

After VM deallocation/restart, XFRM interfaces (xfrm41, xfrm42) are not recreated automatically.
The swanctl.conf uses `if_id_in/if_id_out` requiring XFRM interface type links.
`start_action = trap` does not auto-initiate tunnels without traffic; manual `swanctl --initiate` required.

**Recommended fix:** Tank to add a systemd oneshot service that recreates XFRM interfaces and routes on boot.

---

## Finding 5 — Phase 2-vs-3 sequencing discrepancy

Jose stated the intent is to jump straight to Phase 3, skipping Phase 2 completion.  
Phase 2 infrastructure is fully deployed and connected.  
**Recommendation to Morpheus/Trinity:** Clarify whether Phase 3 should be added on top of the current Phase 2 state (ER + VPN simultaneously) or whether Phase 2 cleanup is needed first. Both ER gateways and VPN gateways exist; Routing Intent will affect ALL traffic paths through the hubs.

---

## Evidence files

- `show-output/08-phase3-audit-resource-inventory.txt` — full resource list with type counts
- `show-output/09-phase3-audit-firewalls-and-routing-intent.txt` — Phase 3 not started
- `show-output/10-phase2-audit-er-and-gateways.txt` — initial ER audit (incorrect query)
- `show-output/11-phase2-er-connections-corrected.txt` — Phase 2 connections confirmed
- `show-output/12-failover-failback-cycle4-nva2.txt` — failover/failback CLEAN

**Author:** Niobe  
**Date:** 2026-07-30T13:35:49+02:00  
**Lab:** vwan-routemap-summarization  
**Context:** Jose asked whether we are in Phase 3 (Azure Firewalls + Routing Intent). Niobe audited the live subscription.

---

## Finding 1 — Phase 3 NOT started

No Azure Firewall, no Firewall Policy, and no Routing Intent exists in `routemap-test-rg`.  
All 3 hubs (hub-us, hub-eu1, hub-eu2) are non-secured: `azureFirewall = null`, `securityProviderName = null`.  
Evidence: `show-output/09-phase3-audit-firewalls-and-routing-intent.txt`

**Decision implication:** Phase 3 work cannot begin until the team explicitly decides to start it. Tank/Morpheus must scope it.

---

## Finding 2 — Phase 2 infrastructure IS partially deployed (undocumented)

The following resources exist in the RG but were NOT documented in the Phase 1 validation or README:

| Resource | Type | Location | State |
|----------|------|----------|-------|
| er-eu1 | Microsoft.Network/expressRouteCircuits | swedencentral | Enabled / Provisioned |
| er-eu2 | Microsoft.Network/expressRouteCircuits | westeurope | Enabled / Provisioned |
| ergw-eu1 | Microsoft.Network/expressRouteGateways | swedencentral | Succeeded |
| ergw-eu2 | Microsoft.Network/expressRouteGateways | westeurope | Succeeded |
| site-gcp1 / site-gcp2 | Microsoft.Network/vpnSites | swedencentral / westeurope | Succeeded |
| kv-pe | Microsoft.Network/privateEndpoints | swedencentral | Succeeded |

ER gateways have **no connections** (connections = null) — circuits provisioned, gateways deployed, but NOT connected.

**Decision implication:** Phase 2 (VPN/ER over ExpressRoute) has been partially deployed — infrastructure exists but no ER connections have been established. The README and validation.md do not reflect this. Tank/Kid should update docs to reflect actual state.

---

## Finding 3 — Phase 2-vs-3 sequencing discrepancy

Jose stated the intent is to jump straight to Phase 3, skipping Phase 2 completion.  
The documented sequence in README.md is: Phase 1 → Phase 2 (ExpressRoute + VPN) → Phase 3 (Secured hubs).  
**Recommendation to Morpheus/Trinity:** Clarify whether Phase 2 should be completed first (connections established, validated) or abandoned/deleted before Phase 3 work begins, since both phases use the same hub infrastructure.

---

## Evidence files

- `show-output/08-phase3-audit-resource-inventory.txt` — full resource list with type counts
- `show-output/09-phase3-audit-firewalls-and-routing-intent.txt` — firewall + routing intent checks
- `show-output/10-phase2-audit-er-and-gateways.txt` — ER circuit + gateway state (initial, incorrect)
- `show-output/11-phase2-er-connections-corrected.txt` — Phase 2 connections confirmed
- `show-output/12-failover-failback-cycle4-nva2.txt` — failover/failback CLEAN

---

## Routing to Oracle (Docs) — items NOT done by Niobe

The following are structural or prose rewrites beyond Niobe's factual-correction scope:

1. **README.md intro paragraph** — "If Phase 1 does not reproduce, Phase 2 moves to VPN over
   ExpressRoute" is stale narrative (Phase 2 IS deployed). The opening paragraph needs a prose
   rewrite. Niobe made only the minimum factual table corrections.

2. **manifest.md §3 Topology diagram** — The ASCII topology shows only Phase 1 (VPN NVAs only).
   Phase 2 adds ER gateways and GCP VPN paths. Oracle/diagram owner should update the ASCII art
   and the draw.io diagram to reflect the Phase 2 topology.

3. **manifest.md §6 Scenario walkthroughs** — Scenarios 1–3 describe Phase 1 only. A new Scenario 4
   (VPN over ER) is needed if Phase 2 repro testing proceeds. Oracle should own that authoring.

4. **manifest.md §2 "In scope" section** — Phase 2 is now deployed but ER-path repro testing has
   not yet been added to the formal scope statement. Oracle should update when the team decides
   to proceed with Phase 2 repro.
# Decision: Phase 3 Azure Firewall Deploy — Routing Intent Deferred

**Date:** 2026-07-30  
**Author:** Tank (IaC Engineer)  
**Status:** DEPLOYED — awaiting Niobe Gate A

---

## What was deployed

Phase 3 Azure Firewalls deployed into vWAN hubs hub-eu1 (swedencentral) and hub-eu2 (westeurope) in RG `routemap-test-rg`.

| Resource | Name | Region | State |
|----------|------|--------|-------|
| Firewall Policy | `azfwpol-routemap-lab` | swedencentral | Succeeded |
| Firewall | `azfw-eu1` | swedencentral (hub-eu1) | Succeeded |
| Firewall | `azfw-eu2` | westeurope (hub-eu2) | Succeeded |

Both hubs are now **secured virtual hubs** (azureFirewall ≠ null). Policy: Standard, allow-all NetworkRule (Any→Any/Any/*).

Provisioning time: ~12 minutes (parallel `--no-wait` submit at 15:56:19 UTC+2, both Succeeded by 16:08:09).

## Routing Intent deliberately NOT enabled

**Jose explicitly authorized deploying the firewall without enabling Routing Intent.**

Routing Intent (PrivateTraffic) is deferred to after Niobe Gate A. The primary research question — whether RI suppresses spoke /24 specifics before the `summarize-out` route-map evaluates them — requires Niobe to validate 6/6 summaries are preserved in the firewall-only state first. This provides a clean causal isolation point.

**Do NOT enable routing intent (Step 4) until Niobe Gate A is signed off.**

## Key resource IDs (subscription redacted)

- **azfw-eu1:**  
  privateIP: `192.168.2.132` | publicIP: `4.223.110.6`  
  ID: `/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/routemap-test-rg/providers/Microsoft.Network/azureFirewalls/azfw-eu1`

- **azfw-eu2:**  
  privateIP: `192.168.4.132` | publicIP: `20.105.195.71`  
  ID: `/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/routemap-test-rg/providers/Microsoft.Network/azureFirewalls/azfw-eu2`

- **azfwpol-routemap-lab:**  
  ID: `/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/routemap-test-rg/providers/Microsoft.Network/firewallPolicies/azfwpol-routemap-lab`

## Cost estimate

Azure Firewall Standard in vWAN hub:
- ~$1.25/hr per firewall (Standard tier, fixed infra cost)
- 2 firewalls × $1.25/hr × 24h = **~$60/day** (infrastructure only, no data processing charges for control-plane-only lab)
- Rounded estimate: **$60–70/day** for both firewalls combined

Previous lab daily cost was ~$135/day (from prior Phase 1/2 resources). Phase 3 firewalls add ~$60/day on top.

## Teardown notes

**Mandatory cleanup order** (idempotent script: `deploy/cleanup-phase3-firewall.sh`):
1. Delete routing intent on hub-eu1 and hub-eu2 (no-op if not present)
2. Delete `azfw-eu1` (--no-wait)
3. Delete `azfw-eu2` (--no-wait)
4. Poll until both firewalls deleted
5. Delete `azfwpol-routemap-lab` (policy must be last — firewalls reference it)

Full lab teardown: `az group delete -n routemap-test-rg --yes` (requires Jose sign-off per routing rule #12).
# Decision: Phase 3 Azure Firewall + Routing Intent Design

**Author:** Trinity  
**Date:** 2026-07-30  
**Lab:** vwan-routemap-summarization  
**For:** Scribe to merge; Tank to execute; Niobe to validate

---

## Which hubs get Azure Firewall

**hub-eu1 (swedencentral) and hub-eu2 (westeurope): YES**  
**hub-us (westus2): NO**

Rationale: The customer's missing-summary bug was observed in a secured-hub environment. The
`summarize-out` route-maps live on the EU hubs. hub-us is a route source only (12 spoke VNets)
and not part of the customer's repro topology. hub-us remaining non-secured is correct per
MS docs: routes from an unsecured remote hub propagate to secured local hubs as long as those
remote connections propagate to the secured hub's defaultRouteTable (default behavior).

---

## Firewall SKU

**Azure Firewall Standard** (AZFW_Hub, tier Standard)

- Azure Firewall Basic is NOT supported in vWAN secured hubs (VNet-only SKU).
- Standard is the cheapest SKU supported in vWAN.
- Premium not needed — this is a control-plane repro lab with no IDPS/TLS inspection requirement.

Shared policy `azfwpol-routemap-lab` (swedencentral) with allow-all network rule collection.
Allow-all is correct for a repro lab: eliminates firewall as a causal variable for route-map bug.

---

## Routing Intent plan

| Hub | InternetTraffic | PrivateTraffic | Next hop |
|-----|-----------------|----------------|----------|
| hub-eu1 | NO | YES | azfw-eu1 |
| hub-eu2 | NO | YES | azfw-eu2 |
| hub-us | N/A | N/A | N/A (no firewall) |

Enable RI sequentially: hub-eu1 first → Niobe gate → hub-eu2 → Niobe gate.

---

## Critical route-map-preservation sequencing

**THE FUNDAMENTAL CONSTRAINT:**

Route-maps (`summarize-out`) operate at the per-connection outbound advertisement layer. Routing
Intent PrivateTraffic installs RFC1918 supernets (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
in the defaultRouteTable for forwarding. Per MS docs, spoke /24s from hub-us (no RI) SHOULD
still be individually propagated to EU hub VPN connections after RI enablement. But this is
EXACTLY WHAT PHASE 3 TESTS — if the RFC1918 aggregate suppresses /24 advertisement before
the route-map evaluates them, the summaries will be absent.

**Required ordering:**
1. Deploy AzFW in both EU hubs (no RI) → **Niobe Gate A**: 6/6 summaries must be present.  
   If Gate A fails, AzFW deployment itself broke route-maps — investigate separately.
2. Enable RI on hub-eu1 → **Niobe Gate B**: check 6/6 on BOTH hubs.  
   If Gate B fails, RI on hub-eu1 is the trigger. Document which summaries missing.
3. Enable RI on hub-eu2 → **Niobe Gate C**: primary repro check on full Phase 3 state.

**DO NOT** enable RI at the same time as deploying the firewall. The gate structure is essential
for isolating which operation causes the repro (if any).

**Note:** RI changes to defaultRouteTable are NOT automatically reversible per MS docs. Save
defaultRouteTable state BEFORE enabling RI. Rollback requires manual restoration.

---

## Design spec location

`labs/vwan-routemap-summarization/design-phase3.md`

Contains: full CLI command shapes, resiliency analysis, subnet requirements, route-collection
checklist for Niobe, and all design rationale.



