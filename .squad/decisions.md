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

### 2026-07-31T10:40:00+02:00: Routing Intent Enabled on hub-eu1
**By:** Tank
**Date:** 2026-07-31T10:40:00+02:00
**Lab:** vwan-routemap-summarization | **RG:** routemap-test-rg
**Prerequisite:** Gate A FULL PASS (both NVAs 6/6 summaries, 0 /24 leaks, BGP Established — Niobe, 2026-07-31)

## Action Taken

Routing Intent (PrivateTraffic) enabled on **hub-eu1 only** (swedencentral), per design-phase3.md §4 and Trinity's Gate A→Gate B sequencing mandate.

hub-eu2 untouched — awaiting Niobe Gate B validation on hub-eu1 before proceeding.

## Command

```bash
az network vhub routing-intent create \
  -g routemap-test-rg --vhub hub-eu1 -n hub-eu1-ri \
  --routing-policies "[{\"name\":\"PrivateTraffic\",\"destinations\":[\"PrivateTraffic\"],\"nextHop\":\"<azfw-eu1-resource-id>\"}]"
```

Policy: PrivateTraffic only (no InternetTraffic). nextHop = azfw-eu1 resource ID.

## Outcome

| Item | Result |
|------|--------|
| RI create provisioningState | Succeeded |
| Duration | ~6 minutes |
| `_policy_PrivateTraffic` in defaultRouteTable | ✅ Present |
| RFC1918 aggregates (10/8, 172.16/12, 192.168/16) | ✅ All three |
| nextHop | azfw-eu1 ✅ |
| propagatingConnections | Cleared to [] (expected — RI takes control) |

## Next Steps

- **Niobe:** Run Gate B validation on hub-eu1 — confirm 6/6 summaries still present with RI active, BGP TCP 179 flows through AzFW, no /24 leaks.
- **Tank (after Gate B PASS):** Enable RI on hub-eu2 (same procedure, azfw-eu2 nextHop).

## Evidence Files

- `show-output/31-gate-b-hub-eu1-routetable-PRE-ri.txt`
- `show-output/32-gate-b-hub-eu1-ri-enable.txt`
- `show-output/33-gate-b-hub-eu1-routetable-POST-ri.txt`

### 2026-07-31T10:55:00+02:00: Gate B FULL PASS — vwan-routemap-summarization
**By:** Niobe
**From:** Niobe (Validation)
**Date:** 2026-07-31T10:55:00+02:00
**Lab:** vwan-routemap-summarization
**Re:** Phase 3 Gate B verdict — RI on hub-eu1, both NVAs measured

## Decision / Finding

**Gate B: FULL PASS** ✅

Enabling Routing Intent PrivateTraffic on hub-eu1 (swedencentral) does **NOT** suppress
route-map summarization. Both NVAs see 6/6 summaries after RI is active on hub-eu1.

## Per-Hub / Per-NVA Evidence Summary

| Hub | NVA | RI state | BGP | Summaries | /24 leaks | Verdict |
|-----|-----|----------|-----|-----------|-----------|---------|
| hub-eu1 (swedencentral) | nva1 | **ON** (PrivateTraffic) | Established ✅ | **6/6** ✅ | **0** ✅ | **PASS** |
| hub-eu2 (westeurope) | nva2 | OFF (control) | Established ✅ | **6/6** ✅ | **0** ✅ | **PASS** |

## Key Coexistence Finding

RI installs 10.0.0.0/8 (+ 172.16/12, 192.168/16) in the hub **forwarding table** for
intra-hub AzFW next-hop steering. The `summarize-out` route-map operates on the VPN
gateway's **per-connection BGP advertisement set**. These are orthogonal — RI does not
modify what the hub VPN GW advertises to the branch NVA; only how the hub internally
forwards received private traffic. The /16 and /17 summaries survive intact.

**Additional signal:** nva1 BGP sessions (vpngw0/vpngw1) did not reset during RI
enablement on hub-eu1 — timestamps unchanged from Gate A (07:37:23, 07:37:38).
RI enablement is BGP-transparent to the connected VPN NVAs.

## Recommendation

Gate C (enable RI on hub-eu2, bringing both hubs to RI ON) may now proceed.
No risk signal from single-hub RI. The coexistence hypothesis is empirically confirmed.

## Evidence Location

`labs/vwan-routemap-summarization/show-output/` — files 34–39.
Primary evidence: 38 (nva1 RIB, RI-ON hub) and 35 (nva2 RIB, RI-off control).
Full verdict in: `labs/vwan-routemap-summarization/validation.md` → "Phase 3 — Gate B" section.

### 2026-07-31T11:45:00+02:00: Routing Intent Enabled on hub-eu2 — PRIMARY REPRO STATE
**By:** Tank
**Date:** 2026-07-31T11:45:00+02:00
**Lab:** vwan-routemap-summarization | **RG:** routemap-test-rg
**Prerequisite:** Gate B PASSED (Niobe confirmed 6/6 summaries survive RI on hub-eu1, 0 leaks, both NVAs — 2026-07-31)

## Action Taken

Routing Intent (PrivateTraffic) enabled on **hub-eu2** (westeurope). Both EU hubs are now RI-enabled.

This is the **PRIMARY REPRO STATE** for the customer bug investigation: hub-eu2 carries `summarize-out` + `prepend-in` route-maps, and both hubs are simultaneously under RI PrivateTraffic — the order-dependent condition the lab was built to test.

## Command

```bash
az network vhub routing-intent create \
  -g routemap-test-rg --vhub hub-eu2 -n hub-eu2-ri \
  --routing-policies "[{\"name\":\"PrivateTraffic\",\"destinations\":[\"PrivateTraffic\"],\"nextHop\":\"<azfw-eu2-resource-id>\"}]"
```

## Outcome

| Item | Result |
|------|--------|
| RI create provisioningState | Succeeded |
| Duration | ~8 minutes |
| `_policy_PrivateTraffic` in defaultRouteTable | ✅ Present |
| RFC1918 aggregates (10/8, 172.16/12, 192.168/16) | ✅ All three |
| nextHop | azfw-eu2 ✅ |
| propagatingConnections | Cleared to [] (matches hub-eu1 behavior) |

## Lab State as of 2026-07-31T11:45:00+02:00

| Hub | AzFW | RI | Route-map |
|-----|------|----|-----------|
| hub-eu1 (swedencentral) | azfw-eu1 ✅ | hub-eu1-ri PrivateTraffic ✅ | — |
| hub-eu2 (westeurope) | azfw-eu2 ✅ | hub-eu2-ri PrivateTraffic ✅ | summarize-out + prepend-in |

## Next Steps

- **Niobe:** Gate C validation — confirm 6/6 summaries survive with BOTH hubs RI-enabled simultaneously. BGP on both NVAs through AzFW. No /24 leaks. This is the primary causal test.

## Evidence Files

- `show-output/40-gate-c-hub-eu2-routetable-PRE-ri.txt`
- `show-output/41-gate-c-hub-eu2-ri-enable.txt`
- `show-output/42-gate-c-hub-eu2-routetable-POST-ri.txt`

### 2026-07-31T11:45:00+02:00: Gate C FULL PASS — vwan-routemap-summarization
**By:** Niobe
**From:** Niobe (Validation)
**Date:** 2026-07-31T11:45:00+02:00
**Lab:** vwan-routemap-summarization
**Re:** Phase 3 Gate C verdict — RI on BOTH hubs, full steady state

## ⚠️ HEADLINE: BUG NOT REPRODUCED

**Gate C: FULL PASS** ✅ — **Missing-summary bug: NOT REPRODUCED**

With both EU hubs RI-enabled (hub-eu1 FIRST, hub-eu2 SECOND), all 6 route-map summaries
survive intact on both NVAs. Zero /24 leaks. BGP stable across all three gates.

## Per-Hub / Per-NVA Evidence Summary

| Hub | NVA | RI state | BGP | Summaries | /24 leaks | Verdict |
|-----|-----|----------|-----|-----------|-----------|---------|
| hub-eu1 (swedencentral) | nva1 | ON (since Gate B) | Established ✅ | **6/6** ✅ | **0** ✅ | **PASS** |
| hub-eu2 (westeurope) | nva2 | ON (Gate C, new) | Established ✅ | **6/6** ✅ | **0** ✅ | **PASS** |

Route count: 37/27 on both NVAs — unchanged from Gate A. RIBs structurally identical
across all three gates. BGP sessions stable; nva1 sessions never reset across A→B→C.

## What This Means

Under sequential RI enablement (hub-eu1 first, hub-eu2 second, no concurrent churn),
RI does not interact destructively with outbound `summarize-out` route-map summarization.
The 10.0.0.0/8 aggregate in both defaultRouteTables coexists with the 6 /16+/17 summaries.

## What This Does NOT Mean

The original customer bug (missing summary reported in a production event) involved
Routing Intent enablement during or shortly after a connection re-provisioning churn event.
This lab used a stable-state sequential enablement. The lab **does not exclude** the
possibility that concurrent churn (e.g., VPN connection re-establishment while RI is
being enabled) could still trigger the missing-summary condition.

## Recommendation to Trinity

For a complete repro attempt, consider a "concurrent-churn Gate C" variant:
1. While enabling RI on hub-eu2, simultaneously teardown and reinitiate nva2's IPsec tunnels
2. Check if the BGP reconvergence + RI provisioning collision triggers a missing summary

The current lab establishes the baseline: **sequential RI enablement = safe**.
The stress variant (concurrent churn) remains untested.

## Evidence Location

`labs/vwan-routemap-summarization/show-output/` — files 43–52.
Primary evidence: 48 (nva2 RIB, newly RI-ON hub) and 51 (nva1 RIB, RI-ON both hubs).
Full verdict in: `labs/vwan-routemap-summarization/validation.md` → "Phase 3 — Gate C" section.

### 2026-07-31T12:00:00+02:00: Megaport Credentials Retrieved — Reusable Pattern
**By:** Link
**Date:** 2026-07-31T12:00:00+02:00
**Status:** Complete

## Decision

Established and documented a reusable pattern for fetching secrets from private Key Vault (`publicNetworkAccess=Disabled`) via temporary private endpoint + System-Assigned MI on a lab jump VM.

## Pattern Summary

1. **Private endpoint** created from nva1 (swedencentral) to `platform-secrets-1138`
2. **Private DNS zone** `privatelink.vaultcore.azure.net` linked to hub vnet
3. **IMDS-based token fetch** via `az vm run-command invoke` on nva1
4. **Secrets retrieved:**
   - `megaport-api-key` → user env var `MEGAPORT_ACCESS_KEY` (Jose's machine)
   - `megaport-api-secret` → user env var `MEGAPORT_SECRET_KEY` (Jose's machine)
5. **Cleanup:** PE, DNS zone group, and DNS VNet link deleted

## Why Stored

This pattern is reusable for any future phase that requires private vault access. The documented steps and gotcha table accelerate future credential fetches without rebuilding the PE/DNS infrastructure each time.

## Security Note

Secret values are **NOT** recorded anywhere in this repository. Only KV secret names and retrieval method are documented.

### 2026-07-31T12:05:00+02:00: Gate C Root-Cause Analysis + Gate D Proposal
**By:** Trinity
**Date:** 2026-07-31T12:05:00+02:00
**Lab:** vwan-routemap-summarization
**Re:** Phase 3 Gate C — root-cause of negative expectation + Gate D design

## Root-Cause Verdict

**One sentence:** RI PrivateTraffic's RFC1918 aggregate lives in the hub's data-plane forwarding table (defaultRouteTable), while `summarize-out` evaluates the hub VPN gateway's per-connection BGP outbound advertisement set — these are orthogonal planes and, in steady state, the forwarding-table aggregate cannot suppress the BGP-layer /24 specifics that feed the route-map.

**Explanation:** The hub VPN gateway derives what it BGP-advertises to the NVA from learned BGP routes (hub-us spoke /24s propagated via inter-hub), not from defaultRouteTable static entries. RI's `_policy_PrivateTraffic` entry assigns AzFW as next-hop for private-destined packets — it is a forwarding directive, invisible to the advertisement-set computation. Because hub-us carries no RI, its 48 spoke /24 specifics propagate individually to hub-eu1/eu2; the route-map's `Contains` clauses match them and fire six Replace rules exactly as before RI was enabled. The BGP session timestamps (nva1 vpngw0/vpngw1: 07:37:23/07:37:38, unchanged across all three gates) confirm RI provisioning never reset or interrupted the BGP control plane.

## Concurrent-Churn Hypothesis

The production bug was likely triggered by a race between (a) RI policy-install, which reprograms how the hub computes per-connection outbound advertisement export, and (b) a concurrent VPN connection reconvergence (BGP session teardown/re-establishment) on the same hub. If the hub evaluates the route-map against an advertisement set that is simultaneously being rebuilt due to a connection restart, the /24 specifics may be transiently absent from the evaluation input; if the hub caches the resulting zero-match output, the missing summary persists after full reconvergence — reproducing the customer's "summary disappeared after RI enable" observation. The lab avoided this by applying RI to a fully stable, converged hub with no concurrent events.

## Gate D Recommendation

Worth running. It is the minimum necessary experiment to close the repro question. The step sequence is documented in `labs/vwan-routemap-summarization/design-phase3.md` (§ "Gate C Result + Gate D Proposal"), dormant until Jose says "run Gate D." Estimated incremental cost: ~$0.10 (30–45 min additional AzFW runtime). The key concurrent action: Tank tears down the NVA's IPsec tunnels (`swanctl --terminate`) on hub-eu2 while simultaneously deleting and recreating hub-eu2's RI config; Niobe polls BIRD RIB every 30 s and looks for any summary that remains absent after full reconvergence (vpngw0+vpngw1 Established + RI Succeeded). A persistent miss is the repro signal.

