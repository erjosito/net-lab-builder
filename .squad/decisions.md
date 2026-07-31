## Active Decisions

> Active decisions from all agents (merged by Scribe)

### 2026-07-31T09:52:00+02:00: Gate A FULL PASS — vwan-routemap-summarization
**By:** Niobe
**From:** Niobe (Validation)  
**Date:** 2026-07-31T09:52:00+02:00  
**Lab:** vwan-routemap-summarization  
**Re:** Phase 3 Gate A — full re-run verdict (both hubs)

## Decision / Finding

**Gate A: FULL PASS** ✅

Deploying Azure Firewalls (azfw-eu1 + azfw-eu2, Standard SKU, Routing Intent OFF) does **NOT**
break outbound route-map summarization on either EU hub. Both NVAs show 6/6 summaries, 0 /24
leaks, and BGP Established on all 4 sessions.

## Per-Hub Evidence Summary

| Hub | NVA | BGP | Summaries | /24 leaks | Verdict |
|-----|-----|-----|-----------|-----------|---------|
| hub-eu1 (swedencentral) | nva1 | vpngw0+vpngw1 Established | **6/6** | **0** | **PASS** |
| hub-eu2 (westeurope) | nva2 | vpngw0+vpngw1 Established | **6/6** | **0** | **PASS** |

Summaries confirmed on both: 10.0.0.0/16, 10.1.0.0/16, 10.2.0.0/16, 10.3.0.0/16, 10.4.0.0/17, 10.4.128.0/17.

## Context

Previous session (2026-07-30) produced a CONDITIONAL PASS: hub-eu2/nva2 PASS; hub-eu1/nva1
INCONCLUSIVE due to a stuck RunCommandLinux extension. Tank resolved it via `az vm redeploy`
(~90 min in swedencentral). Today's re-run completes the measurement on nva1.

## Recommendation

Gate B may now proceed on **both hubs simultaneously** (enable Routing Intent on hub-eu1 and
hub-eu2). There is no reason to stagger by hub — both have identical PASS state.

## Evidence Location

`labs/vwan-routemap-summarization/show-output/` — files 23–30 (Gate A full re-run).
Primary evidence: 25 (nva1 RIB) and 26 (nva2 RIB).
Full verdict in: `labs/vwan-routemap-summarization/validation.md` → "Phase 3 — Gate A" section.


### 2026-07-31T09:45:00+02:00: nva1 Redeploy Outcome + NVA Restore Results

**Author:** Tank  
**Date:** 2026-07-31T09:45:00+02:00  
**Lab:** vwan-routemap-summarization | **RG:** routemap-test-rg  
**Relevant prior decision:** Gate A CONDITIONAL PASS (2026-07-30T17:15:00+02:00)

---

## Decision / Finding

`az vm redeploy` successfully cleared nva1's terminally stuck RunCommandLinux extension.
Both NVAs are now running with BGP Established on both VPN gateway peers.

**Gate A blocker (nva1 stuck extension) is RESOLVED.**

---

## Evidence

| Item | Result |
|------|--------|
| nva1 pre-redeploy smoke test | 409 Conflict — extension stuck |
| nva1 redeploy duration | ~90 minutes (swedencentral) |
| nva1 post-redeploy smoke test | `VM_ALIVE` — extension cleared |
| nva2 vpngw0/vpngw1 | Established (35 routes / 26 networks) |
| nva1 vpngw0/vpngw1 | Established (37 routes / 27 networks) |

Capture file: `labs/vwan-routemap-summarization/show-output/22-phase3-nva-restart-restore.txt`

---

## Key Observations

1. **Redeploy clears stuck extension** — confirmed. This is the correct remediation for a stuck RunCommandLinux agent. The extension state lives on disk and survives normal dealloc/start cycles; only a host migration (redeploy) clears it.

2. **Redeploy in swedencentral took ~90 min** — much longer than typical (10–15 min). The VM remained in `ProvisioningState: Updating` for the entire duration. Azure API responses were also slow during this window. Flag: swedencentral may have capacity/scheduling pressure. If nva1 gets stuck again, consider a delete+recreate path instead of redeploy.

3. **XFRM tunnels auto-rekeyed** — on both NVAs, `swanctl --initiate` returned "existing duplicate" meaning the Azure VPN GW side had already renegotiated the IPsec SAs after the interfaces came up. The explicit initiate step is still correct (belt-and-suspenders) but may not always be necessary.

---

## Action

- **Niobe:** Proceed with Gate A full re-run for hub-eu1. Run §8 route-collection checklist on nva1 side. Both hubs should now show 6/6 summaries.
- **Tank (deferred, Phase 4):** Implement systemd service for xfrm-persistence to eliminate manual restore on future dealloc/start cycles.
- **Tank (future risk):** If nva1 gets a stuck extension again after another failover cycle, try `az vm redeploy` first. If it takes >90 min again, escalate to delete+recreate (coordinates with Jose for NVA config preservation).


### 2026-07-30T17:15:00+02:00: Niobe Gate A Verdict — Phase 3 (Firewall Deployed, No Routing Intent)

**Author:** Niobe (Lab Validator & Diagnostics)  
**Lab:** vwan-routemap-summarization  
**Gate:** Phase 3 Gate A — firewall deployed, RI NOT yet enabled

**Verdict: CONDITIONAL PASS ⚠️**

**hub-eu2: PASS ✅** — 6/6 summaries confirmed, 0 /24 leaks, BGP Established  
**hub-eu1: INCONCLUSIVE ⚠️** — All control-plane checks PASS; NVA-level blocked by stuck extension

**Key Findings:**

1. **hub-eu2 Control-Plane & Data-Plane PASS:**
   - 6 route-map rules all Succeeded (summarize-out + prepend-in)
   - BIRD RIB confirms all 6 summaries received with correct Replace action (AS path = 65515)
   - Zero /24 specifics leaked into 10.0.0.0/8 space
   - Both BGP sessions (vpngw0, vpngw1) Established
   - AzFW provisioningState = Succeeded
   - defaultRouteTable = [] (no RI routes, as expected pre-RI)

2. **hub-eu1 Control-Plane PASS, L2 Blocked:**
   - Identical route-map config as hub-eu2: all 6 rules Succeeded
   - AzFW provisioningState = Succeeded
   - Control-plane state matches hub-eu2 exactly
   - **Blocker:** nva1 run-command extension terminally stuck (Conflict/409), preventing XFRM restoration and BIRD access
   - This is NOT a firewall-caused failure (pre-dates Phase 3, persisted from prior cycle)
   - Inference: hub-eu1 likely also shows 6/6 summaries (control-plane identical), but unverified

3. **Tool Limitation:** `az network vhub route-map get-outbound-routes` (L1b measurement) non-functional:
   - Returns empty for all attempts, HTTP 404 from preview CLI command
   - L2 BIRD RIB measurement on nva2 is the authoritative fallback
   - Root cause: API/tool limitation, not route-map failure

**Implication for Routing Intent enablement:**
- hub-eu2 is ready: firewall deployment alone does NOT break summaries. Proceed-to-RI is safe.
- hub-eu1 needs nva1 rebuild first (XFRM restoration) for full measurement confirmation before enabling RI per Trinity's sequencing gate (Gate A → Gate B → Gate C).

**Recommendation:** Option A: Tank rebuilds nva1 → Niobe re-runs → full Gate A PASS → enable RI sequentially.  
Or Option B (risk-accepted): Jose enables RI on hub-eu2 first, defers hub-eu1 until nva1 rebuilt.

**Evidence:** show-output/13–20 (L1a–L2 full measurement suite); validation.md Phase 3 Gate A section updated.

### 2026-07-30T21:49:01+02:00: Alternate failover method - Megaport VXC BGP (next session)
**By:** Jose (via Copilot)
**What:** For triggering a leg-down / failover, an easier method than NVA-side teardown (systemctl stop bird + swanctl --terminate) is to disable or misconfigure BGP on one of the Megaport VXCs at the Megaport (L2 fabric) level - IF Megaport API/portal credentials are available.
**Why:** Cleaner, fabric-level failover trigger. Drops a leg at the ExpressRoute/Megaport layer instead of at the NVA, and would exercise the VPN<->ER path-switch dimension noted as still-untested in Phase 2. Requires Megaport credentials - confirm availability before attempting.
**Action:** Next session, check for Megaport credentials. If present, Niobe/Tank can use a Megaport VXC BGP disable/misconfig as the failover trigger for the fabric-level path-switch test.

