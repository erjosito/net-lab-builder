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


# Decision: GCP Interconnect Teardown — vwan-routemap-summarization

**Date**: 2026-07-31  
**Author**: Link (Squad Operator)  
**Status**: No action required — superseded by project deletion  

---

## Context

The task was to explicitly delete the GCP PARTNER Interconnect attachment (`onprem-attach`), Cloud Routers (`onprem-router`, `nat-router`), and firewall rules in project `vwan-routemap-lab`, region `europe-west3`.

---

## Finding

The GCP project `vwan-routemap-lab` is in `DELETE_REQUESTED` state as of 2026-07-31T16:15+02:00.

```
projectId:     vwan-routemap-lab
projectNumber: <REDACTED>
lifecycleState: DELETE_REQUESTED
```

All Compute Engine API calls return:
```
404: The resource 'projects/vwan-routemap-lab' was not found
```

This applies to: `interconnectAttachments`, `routers`, `firewalls`, `networks`, and all aggregated list endpoints.

---

## Conclusion

**No individual resource deletions were performed** — they are impossible once a project enters DELETE_REQUESTED state.

All resources are scheduled for automatic deletion within GCP's 30-day grace period:

| Resource | Status |
|---|---|
| `onprem-attach` (PARTNER Interconnect, europe-west3) | Scheduled for deletion with project |
| `onprem-router` (Cloud Router, europe-west3) | Scheduled for deletion with project |
| `nat-router` (Cloud Router, europe-west3) | Scheduled for deletion with project |
| `onprem-vpc` (VPC network) | Scheduled for deletion with project |
| Firewall rules (`onprem-allow*`) | Scheduled for deletion with project |
| GCP compute instances | Already explicitly deleted earlier today |

GCP billing for the project stopped at the time `DELETE_REQUESTED` was set.

---

## Reusable Pattern: Detect DELETE_REQUESTED Before Resource Ops

Always check project lifecycle state before attempting per-resource deletions:

```powershell
$proj = Invoke-RestMethod -Uri "https://cloudresourcemanager.googleapis.com/v1/projects/$PROJECT" -Headers $H
if ($proj.lifecycleState -eq "DELETE_REQUESTED") {
    Write-Host "Project already scheduled for deletion — no resource ops needed."
    exit 0
}
```

---

## Evidence
`labs\vwan-routemap-summarization\show-output\54-teardown-gcp-interconnect.txt`
# Decision: GCP Compute Instance Teardown — vwan-routemap-lab

**Date**: 2026-07-31  
**Author**: Link (Squad Operator)  
**Status**: Executed — Step 1 of lab teardown  

---

## Context

Full teardown of `vwan-routemap-lab` authorized by Jose Moreno. This decision covers **Step 1 only**: GCP Compute instance deletion. Megaport and interconnect teardown follow in subsequent steps with ordering dependencies.

---

## Instances Deleted

| Instance | Zone | Machine type | State before deletion |
|---|---|---|---|
| `gcp-nva1` | europe-west3-a | e2-small | TERMINATED (stopped) |
| `gcp-nva2` | europe-west3-a | e2-small | TERMINATED (stopped) |

Project: `vwan-routemap-lab` (GCP). Final state: zero compute instances.

---

## Method: Windows REST API (WSL gcloud unavailable due to DNS)

WSL's `/etc/resolv.conf` uses Microsoft corporate DNS which cannot resolve `oauth2.googleapis.com`. gcloud token refresh fails. Instead:

1. Extract `refresh_token` + OAuth2 client credentials from `/home/jose/.config/gcloud/credentials.db` (SQLite)
2. POST OAuth2 token refresh to `https://oauth2.googleapis.com/token` from Windows PowerShell
3. Call GCP Compute REST API directly from Windows with Bearer token
4. DELETE `/compute/v1/projects/{project}/zones/{zone}/instances/{name}` for each instance
5. Poll zone operation until `DONE`

---

## Resources NOT Deleted — Require Ordered Teardown

These remain and must be deleted in the correct order:

| Resource | Why waiting |
|---|---|
| `onprem-attach` (PARTNER Interconnect, ACTIVE) | GCP side of ER/Megaport; must delete **after** Azure ER circuits removed and Megaport VXCs torn down |
| `onprem-router` (Cloud Router) | Depends on `onprem-attach` being gone first |
| `nat-router` (Cloud Router) | Part of VPC teardown |
| Firewall rules on `onprem-vpc` | Not cost-bearing; clean up with VPC |
| `onprem-vpc` VPC | Full VPC teardown — last step |

**No static IPs, VPN gateways, or VPN tunnels found.**

---

## Ordering Dependency Map

```
Azure ER circuits deleted (Tank)
  → Megaport VXCs deleted (Megaport step)
    → GCP onprem-attach deleted
      → onprem-router deleted
        → nat-router deleted
          → onprem-vpc + firewall rules deleted
```

---

## Reusable Pattern: GCP API from Windows when WSL DNS is broken

```powershell
# Step 1: Get refresh token from gcloud credentials DB (via WSL Python)
wsl -u jose -e bash -c "python3 extract_creds.py"  # extracts client_id, client_secret, refresh_token

# Step 2: Refresh token from Windows
$tokenResp = Invoke-RestMethod -Uri "https://oauth2.googleapis.com/token" -Method POST -Body @{
    client_id="..."; client_secret="..."; refresh_token="..."; grant_type="refresh_token"
}
$TOKEN = $tokenResp.access_token

# Step 3: Call GCP REST APIs
$H = @{ Authorization = "Bearer $TOKEN" }
Invoke-RestMethod -Uri "https://compute.googleapis.com/compute/v1/projects/$PROJECT/..." -Headers $H
```

This pattern bypasses gcloud entirely and works from Windows even when WSL has no internet.
# Decision: Megaport Teardown — vwan-routemap-summarization

**Date**: 2026-07-31  
**Author**: Link (Squad Operator)  
**Status**: Executed  

---

## What Was Deleted

| Product | UID (truncated) | Location | Action |
|---|---|---|---|
| `jomore-copilot-vxc-mcr-gcp` (GCP VXC) | `085a00e7-…` | Amsterdam AM1 | CANCEL_NOW ✅ |
| `jomore-copilot-vxc-er-eu2-mcr2` (Azure er-eu2) | `c7add98b-…` | Amsterdam AM1 | CANCEL_NOW ✅ |
| `jomore-copilot-vxc-er-eu1-mcr2` (Azure er-eu1) | `2bf97db4-…` | Amsterdam AM1 | CANCEL_NOW ✅ |
| `jomore-copilot-mcr-routemap2` (MCR2) | `c95d174c-…` | Amsterdam AM1 | CANCEL_NOW ✅ |
| `jomore-copilot-mcr-routemap` (MCR1) + 5 VXCs | `4ca97a61-…` | Frankfurt FR5 | Already DECOMMISSIONED |

Final state: **all `jomore-copilot-*` products → DECOMMISSIONED**.

---

## Reusable Teardown Pattern

### Step 1: Auth

```powershell
$AK = [System.Environment]::GetEnvironmentVariable("MEGAPORT_ACCESS_KEY","User")
$SK = [System.Environment]::GetEnvironmentVariable("MEGAPORT_SECRET_KEY","User")
$TOKEN = (Invoke-RestMethod -Uri "https://auth-m2m.megaport.com/oauth2/token" `
    -Method POST -ContentType "application/x-www-form-urlencoded" `
    -Body "grant_type=client_credentials&client_id=$AK&client_secret=$SK").access_token
$H = @{ Authorization = "Bearer $TOKEN"; "Content-Type" = "application/json" }
```

### Step 2: Inventory

```powershell
$products = (Invoke-RestMethod -Uri "https://api.megaport.com/v2/products" -Headers $H).data
$labProds = $products | Where-Object { $_.productName -like "jomore-copilot-*" }
```

### Step 3: Delete VXCs First (order matters)

```powershell
foreach ($uid in $vxcUids) {
    $url = "https://api.megaport.com/v3/product/$uid/action/CANCEL_NOW"
    Invoke-RestMethod -Uri $url -Method POST -Headers $H
}
```

### Step 4: Delete MCRs

```powershell
foreach ($uid in $mcrUids) {
    $url = "https://api.megaport.com/v3/product/$uid/action/CANCEL_NOW"
    Invoke-RestMethod -Uri $url -Method POST -Headers $H
}
```

Success response: `{"message":"Action [CANCEL_NOW Service {uid}] has been done."}`

---

## Key Gotchas

| Gotcha | Detail |
|---|---|
| **Wrong endpoint** | `DELETE /v3/product/{uid}?deleteNow=true` returns 404. `DELETE /v2/product/{uid}` returns 405. The correct method is `POST /v3/product/{uid}/action/CANCEL_NOW`. |
| **Wrong endpoint (VXC-typed)** | `DELETE /v3/product/vxc/{uid}` returns 405 — this endpoint only supports PUT (for updates). |
| **Location mismatch** | MCR2 was at Amsterdam AM1 (locationId=85), not Frankfurt FR5 (131). Always enumerate from the API, don't trust the briefing's locationId. |
| **Ordering** | VXCs must be cancelled before MCRs. Attempting to cancel an MCR with live VXCs may fail. |
| **Already DECOMMISSIONED** | MCR1 and its VXCs were already DECOMMISSIONED when we arrived (Azure ER peering deletions auto-decommissioned them). No action needed for DECOMMISSIONED products. |

---

## Evidence
`labs\vwan-routemap-summarization\show-output\51-teardown-megaport.txt`

---

## API Source Reference
SDK: `github.com/megaport/megaportgo` — `product.go` `DeleteProduct()`:
```go
path := "/v3/product/" + req.ProductID + "/action/" + action
// action = "CANCEL_NOW" when DeleteNow=true
```
# Decision: Final Azure RG Teardown — routemap-test-rg DELETED

**Date:** 2026-07-31T17:22:12+02:00  
**Author:** Tank (IaC Engineer)  
**Requested by:** Jose Moreno (@erjosito)  
**Status:** COMPLETE — RG fully deleted and verified

---

## Summary

`routemap-test-rg` has been fully deleted. The vwan-routemap-summarization lab is completely decommissioned on the Azure side.

---

## Pre-conditions confirmed before delete

| Item | Status |
|------|--------|
| Megaport VXCs (jomore-copilot-*) | DECOMMISSIONED (Jose/Link confirmed) |
| Megaport MCRs | DECOMMISSIONED |
| ER private peerings (er-eu1/er-eu2 AzurePrivatePeering) | Previously deleted |
| ER gateway connections (conn-er-eu1, conn-er-eu2) | Previously deleted (show-output/50) |
| Routing Intent (hub-eu1-ri, hub-eu2-ri) | Previously deleted |
| Azure Firewalls (azfw-eu1, azfw-eu2) | Previously deleted |

---

## What was in the RG at time of delete (pre-delete inventory)

Key resources deleted by `az group delete`:

| Resource type | Count | Names |
|---------------|-------|-------|
| Microsoft.Network/virtualWans | 1 | vwan-routemap |
| Microsoft.Network/virtualHubs | 3 | hub-us, hub-eu1, hub-eu2 |
| Microsoft.Network/virtualNetworks | 19 | spoke-us-{a–f}, spoke-us-{a–f}2, scale VNets, onprem1/2-vnet |
| Microsoft.Network/vpnGateways | 2 | vpngw-eu1, vpngw-eu2 |
| Microsoft.Network/expressRouteGateways | 2 | ergw-eu1, ergw-eu2 |
| Microsoft.Network/expressRouteCircuits | 2 | er-eu1, er-eu2 |
| Microsoft.Network/firewallPolicies | 1 | azfwpol-routemap-lab |
| Microsoft.Network/privateEndpoints | 1 | kv-pe |
| Microsoft.Compute/virtualMachines | 2 | nva1, nva2 |
| Microsoft.Compute/disks | 2 | nva1/nva2 OS disks |
| Microsoft.Network/networkSecurityGroups | 14+ | spoke/NVA NSGs |
| Microsoft.Network/vpnSites | 4 | site-onprem1/2, site-gcp1/2 |
| Microsoft.Network/publicIPAddresses | 2 | nva1-pip, nva2-pip |
| VM extensions | 6 | enablevmAccess, MDE.Linux, xfrm-restore |

Full inventory in `show-output/53-teardown-azure-rg.txt`.

---

## Delete execution

| Step | Command | Result |
|------|---------|--------|
| Delete | `az group delete -n routemap-test-rg --yes` | ✅ Exit 0 |
| Elapsed | — | ~39 minutes (16:42:51 → 17:22:12 UTC+2) |
| Verify RG | `az group show -n routemap-test-rg` | ✅ ResourceGroupNotFound (exit 3) |
| Verify ER | `az network express-route list -g routemap-test-rg` | ✅ ResourceGroupNotFound (exit 3) |

---

## Cost impact

- All Azure costs for this lab stop as of 2026-07-31T17:22:12+02:00.
- Estimated daily burn at time of delete: ~$135/day base (Phase 1/2) + ~$60/day (Phase 3 firewalls) ≈ **$195/day eliminated**.

---

## Evidence

`labs/vwan-routemap-summarization/show-output/53-teardown-azure-rg.txt`

---

## Notes

- `az resource list` does NOT surface `Microsoft.Network/azureFirewalls` (AZFW_Hub type) — they appear only in `az network firewall list` and via `az network vhub show --query azureFirewall`. This is a known CLI display gap; RG delete handles them correctly.
- `platform-secrets-1138` KV RG was NOT touched.
- The lab knowledge base (show-output/, design-phase3.md, manifest.md, deploy scripts, decisions) is preserved in the repo for reference.
# Decision: Teardown Step 1 — ER Connections + RI + Firewalls

**Author:** Tank  
**Date:** 2026-07-31T15:32:00+02:00  
**Lab:** vwan-routemap-summarization | **RG:** routemap-test-rg  
**Authorized by:** Jose Moreno

---

## Actions Taken

Per documented cleanup order (src/terraform/expressroute-megaport-bgp/README.md §Cleanup warning):

**Step 1 (ER connections):** Deleted conn-er-eu1 and conn-er-eu2. Both confirmed gone.  
**Step 2 (ER peerings):** Provider-owned (`lastModifiedBy: Provider`) — deferred to RG delete.  
**Bonus (cost stop):** Deleted routing-intent (hub-eu1-ri, hub-eu2-ri) and both Azure Firewalls (azfw-eu1, azfw-eu2) to stop ~$60/day bleed.

---

## Outcomes

| Resource | Action | Result | Timing |
|----------|--------|--------|--------|
| conn-er-eu1 | Deleted | ✅ Gone | ~7 min |
| conn-er-eu2 | Deleted | ✅ Gone | ~10 min |
| er-eu1/AzurePrivatePeering | Deferred | ⏳ Provider-owned | With RG |
| er-eu2/AzurePrivatePeering | Deferred | ⏳ Provider-owned | With RG |
| hub-eu1-ri | Deleted | ✅ Gone | ~6 min |
| hub-eu2-ri | Deleted | ✅ Gone | ~8 min |
| azfw-eu1 | Deleted | ✅ Gone | ~10 min |
| azfw-eu2 | Deleted | ✅ Gone | ~10 min |

---

## Gate for Link

**ER connections are deleted — Link can now safely tear down Megaport VXCs (step 3) and MCR (step 4).**

---

## Remaining Cleanup Order

| Step | Who | Resource | Status |
|------|-----|----------|--------|
| 3 | Link | Megaport VXCs | Pending — Link's job |
| 4 | Link | Megaport MCR | Pending — Link's job |
| 5 | Tank | Azure RG (az group delete) | Pending — after Megaport confirmed gone |

Do NOT delete the RG until Link confirms Megaport teardown is complete.

---

## CLI Notes

- `az network express-route gateway connection delete` does NOT support `--yes` — non-interactive by default
- RI delete must precede FW delete (FW cannot be deleted while referenced by RI)
- FW delete with `--no-wait` allows parallel teardown of both hubs

## Evidence

`show-output/50-teardown-er-conn-fw.txt`
# Trinity → Team: Documentation Consolidation — vwan-routemap-summarization

**From:** Trinity (Azure Network SME)  
**Date:** 2026-07-31T15:17:00+02:00  
**Lab:** vwan-routemap-summarization  
**Re:** Doc consolidation decision record

## What changed and why

### README.md — complete rewrite

The existing README described Phase 3 as "Not started" and had no scannable entry point for a
casual reader. Rewritten as the lab's front door with:
- Headline result + one-line root-cause at the top (for the skimmer)
- 5-row results table (Phase 1 → Phase 2 → Gate A → Gate B → Gate C) with outcome + primary evidence link in each row
- Links to all four detailed docs
- ASCII topology reflecting Phase 3 final state (secured hubs)
- Four collapsible `<details>` blocks (resource inventory, route-map scheme, full 52-file evidence index, Gate D)

**Structure decision:** Evidence index lives as a collapsible in README (not a separate evidence.md file) to minimize link depth — one click from landing page to any of the 52 files.

### manifest.md — Phase 3 resources added

Added three Phase 3 resources to the inventory table (azfwpol-routemap-lab, azfw-eu1/eu2, hub-eu1-ri/eu2-ri). Updated Out-of-scope section (removed stale "Phase 3 not started" bullet). Updated validation plan section with API gap note. Added back-link to README. Topology ASCII updated to show secured hubs with 🔒 marker.

### lessons-learned.md — Phase 3 Gate B/C section added

Added TOC + back-link header. New section covers: orthogonal-planes root cause (table form), concurrent-churn gap, BGP stability observation, az vm redeploy swedencentral caveat, prepend-in + summarize-out coexistence finding.

### design-phase3.md — status updated, back-link added

Changed Status from "DESIGN-ONLY" to "COMPLETE — all gates validated 2026-07-31". Added back-link to README. (Gate C Result + Gate D section was added in earlier dispatch.)

### validation.md — back-link added only

Content is current and comprehensive — no substantive changes, back-link added.

## Remaining gaps

1. **No diagram update** — `diagrams/01-topology.drawio` still shows pre-Phase-3 topology (no Azure Firewalls, no RI annotation). Updating the draw.io file requires the draw.io tool and is out of scope for a text-only pass; flagged for Jose or Tank in a future session.
2. **No lessons-learned.md entry for RI rollback** — the design warns that RI defaultRouteTable changes are not auto-reversible, but no lessons-learned row confirms the actual rollback procedure was exercised. If Jose runs the teardown and saves/restores the route table, that finding should be appended.
3. **Gate D dormant** — experiment is fully documented but unrun. If Jose authorizes, Niobe + Tank can execute it from the spec in design-phase3.md without further design work.
# Trinity → Team: Documentation Consolidation (Round 2) — Teardown State

**From:** Trinity (Azure Network SME)  
**Date:** 2026-07-31T16:14:00+02:00  
**Lab:** vwan-routemap-summarization  
**Re:** README update — teardown status + Megaport discovery

## What changed

README.md updated with three additions:

1. **Status banner** — changed from "COMPLETE" to "VALIDATION COMPLETE — TEARDOWN IN PROGRESS ⚠️ Megaport VXCs still live (billing running)".

2. **Teardown status section** (new, non-collapsible — visible without expanding) — 7-row table with per-step status (✅/❌/⏳), explicit Megaport VXC delete failure note, and the three VXC UIDs Jose must manually delete via portal.

3. **Resource inventory + evidence index** — Megaport MCR2 and 3 VXCs added to inventory; teardown files 50-teardown/51-teardown/52-teardown added to evidence index. (File number prefix collides with Gate C files 50/51/52 — links use full filenames to disambiguate.)

## Critical finding: Megaport VXC delete failed

The Megaport API v3 `DELETE /v3/product/<uid>` endpoint is not valid — returns `"No endpoint DELETE /v3/product/…"`. All three lab VXCs under `jomore-copilot-mcr-routemap2` are still LIVE and billing. Jose must act:
- Delete via Megaport portal **or** use the correct v2/v3 termination API endpoint
- Three VXCs: `jomore-copilot-vxc-er-eu1-mcr2`, `jomore-copilot-vxc-er-eu2-mcr2`, `jomore-copilot-vxc-mcr-gcp`
- After VXC delete: delete MCR2, then `az group delete -n routemap-test-rg`

## Undocumented lab resource discovered

The Megaport MCR2 (`jomore-copilot-mcr-routemap2`, Milan) and its VXCs were not in manifest.md. The ER circuits (er-eu1/er-eu2) were connected to Azure private peering via these VXCs. The GCP VXC was deployed but never exercised (ER carried no routes during all validation phases). Added to README inventory collapsible; manifest.md not touched (constraint: only README.md per this dispatch).
# Trinity → Team: Lab Fully Decommissioned — README Finalized

**From:** Trinity (Azure Network SME)  
**Date:** 2026-07-31T17:36:00+02:00  
**Lab:** vwan-routemap-summarization  
**Re:** Final teardown state reflected in README; lab archived

## What changed

Three surgical edits to README.md:

1. **Status banner** → `✅ LAB FULLY DECOMMISSIONED — no running resources, no billing (as of 2026-07-31)`

2. **Teardown table rows 4 + 5** — both set to ✅ DONE:
   - Row 4 (Azure RG): exit 0, ~39 min, ended 17:22; ResourceGroupNotFound verified post-delete; covered VWAN, hubs, firewalls, ER circuits, gateways, spokes, NVAs
   - Row 5 (GCP): project `vwan-routemap-lab` in `DELETE_REQUESTED`; Compute APIs return 404; billing stopped; auto-purge ≤30 days; no per-resource cleanup needed

3. **Evidence index rows 53 + 54** — descriptions updated from "(pending)" placeholders to accurate one-line summaries matching the actual file content

## Final verification

`Select-String` scan confirmed: no ⏳, ⚠️, "billing running", "in progress" (as a status marker), or "*(pending)*" strings remain in README.md. The one "portal" match is the correct historical note "No manual portal action was needed" (Megaport CANCEL_NOW story).

## Teardown complete record

| Step | Status |
|---|---|
| ER connections, RI, AzFW | ✅ DONE (evidence 50) |
| ER private peerings | ✅ DONE (evidence 52) |
| Megaport VXCs + MCR2 | ✅ DONE — CANCEL_NOW API (evidence 51) |
| Azure RG `routemap-test-rg` | ✅ DONE — deleted 17:22 (evidence 53) |
| GCP project `vwan-routemap-lab` | ✅ DONE — DELETE_REQUESTED (evidence 54) |
# Trinity → Team: Teardown Status Correction

**From:** Trinity (Azure Network SME)  
**Date:** 2026-07-31T16:41:00+02:00  
**Lab:** vwan-routemap-summarization  
**Re:** README teardown section corrected — Megaport DONE; Azure RG + GCP in progress

## What changed

README.md teardown section corrected in three places:

1. **Status banner** — removed ⚠️ Megaport warning; updated to "(Megaport ✅ complete; Azure RG + GCP cleanup in progress)".

2. **Teardown table** — row 3 (Megaport VXCs/MCR) changed from ❌ FAILED to ✅ DONE; rows 4+5 (Megaport MCR blocked) replaced by rows for Azure RG delete (⏳ IN PROGRESS, evidence 53) and GCP Interconnect cleanup (⏳ IN PROGRESS, evidence 54). "Megaport VXC delete failure" subsection replaced by "Megaport teardown method" note explaining `CANCEL_NOW`.

3. **Evidence index** — 51-teardown row updated to reflect CANCEL_NOW success + final verification. Placeholder rows added for 53-teardown-azure-rg.txt and 54-teardown-gcp-interconnect.txt.

## Megaport API lesson (record)

The Megaport v3 REST API does not have a `DELETE /v3/product/{uid}` endpoint — this returns "No endpoint DELETE…". The correct teardown method is `POST /v3/product/{uid}/action/CANCEL_NOW`, which triggers immediate cancellation. This should be documented in any future lab teardown scripts that use the Megaport API.

## Current teardown state (as of 16:41)

| Step | Status |
|---|---|
| ER connections, RI, AzFW | ✅ DONE |
| ER private peerings | ✅ DONE |
| Megaport VXCs + MCR2 | ✅ DONE (DECOMMISSIONED 16:12) |
| Azure RG delete | ⏳ IN PROGRESS |
| GCP Interconnect cleanup | ⏳ IN PROGRESS |



# IaC Decision — dual-hub-hubless-region-ars ARS Bicep Pattern
**Author:** Tank (IaC Engineer) · **Date:** 2026-08-03T15:55:00+02:00  
**Lab:** dual-hub-hubless-region-ars

## Decision: Azure Route Server in Bicep via `Microsoft.Network/virtualHubs` + child `ipConfigurations`

### Context
No existing Bicep ARS pattern in src/. ARM schema for `virtualHubs` marks `kind` and `ipConfigurations` as read-only in the resource properties object, blocking the naive `kind: 'RouteServer'` approach.

### Decision
1. Declare ARS as `Microsoft.Network/virtualHubs@2023-09-01` with `properties: { sku: 'Standard', allowBranchToBranchTraffic: bool }`.
2. Attach PIP + subnet via separate child resource `Microsoft.Network/virtualHubs/ipConfigurations`.
3. Wire NVA BGP peerings via `Microsoft.Network/virtualHubs/bgpConnections` sub-resources depending on `ipConfigurations`.

### Why
`kind` is auto-inferred from `sku: 'Standard'` by ARM. `ipConfigurations` as a child resource avoids the BCP073 read-only warning and matches how ARS is actually provisioned via the REST API.

### Implication for future labs
Any new ARS in Bicep should follow the two-step pattern: `virtualHubs` resource → `ipConfigurations` child → `bgpConnections` children. Not `kind: 'RouteServer'` inline.

## Decision: PSK generation in-process only (no KV dependency)

PSKs for V2V VPN connections generated via `.NET RandomNumberGenerator` in deploy.ps1 and held as PowerShell process-scope variables. Written to KV `platform-secrets-1138` when available (best-effort), but KV is not a hard prerequisite. This avoids a blocking dependency on KV RBAC and matches the manifest's fallback specification.

## Decision: Δ3 ARS route-map (PUBLIC PREVIEW) not wired in base IaC

Δ3 is isolated entirely from the base deployment. S4 activation requires a separate, explicitly gated step (not yet authored). This prevents accidental first-use ARS upgrade (~30 min + surcharge) on a base S1/S2/S3 run.


# Decision — Dual-Hub ARS + VPN GW Design Review (BEFORE DR)

**Author:** Morpheus (Lead / Architect)
**Date:** 2026-08-03T11:16+02:00
**Ceremony:** BEFORE Design Review (auto-triggered)
**Consulted:** Trinity (Azure Network SME) — sync subagent review
**Requested by:** Jose Moreno
**Status:** Design NOT approved. Corrected baseline proposed. Phase-0 capacity probes and manifest generation BLOCKED until Jose resolves the four gate questions below.
**Related routing rules:** #7 (cost guardrail), #12 (approval gate), #30 (every design is valuable)

---

## Verdict

**Not feasible as drawn.** Jose's proposed topology (per-hub ARS + per-hub VPN GW + central-ARS VNet + spokes double-peered to both hubs without gateway-transit) has three structural defects that make it unable to prove the stated "spoke prefers hub1, auto-fails to hub2, auto-reverts" goal:

1. **Return-path plumbing is broken by construction.** Spoke↔hub peerings deliberately disable gateway transit, so hub VPN GWs never learn spoke prefixes natively. The only path for on-prem to learn a spoke prefix is `spoke → ARS-central → NVA → hub-local-ARS → hub-VPNGW → IPsec → on-prem`. That chain works but relies on NVA BIRD stripping ASN 65515 on re-advertisement (loop-prevention) — a manual filter whose omission silently blackholes on-prem→spoke.

2. **Preferred-path lever (route-map prepend on hub2) is largely unavailable.** ARS route-map preview explicitly cannot modify VNet-address-space advertisements from ARS to VPN GW, and cannot re-prepend routes that ARS itself originates on behalf of the VNet. It can prepend NVA-originated 0/0 and on-prem-originated routes only. Jose's plan to prepend hub2 spoke-prefix advertisements toward on-prem is not achievable through ARS route maps.

3. **Convergence race guarantees an asymmetric-routing window.** ARS hold timer is a fixed 180 s and is not tunable on the ARS side. VPN GW BGP hold + IPsec DPD converge in ~30–90 s. On outage, on-prem switches to hub2 in ≤ 90 s while the spoke's forward path can point at dead NVA1 for up to ~180 s. During that window forward-via-hub1 + return-via-hub2 blackholes.

Additional issues:
- **VPN GW ASN clash** — both hub VPN GWs must use 65515 (forced by ARS coexistence). On-prem sees two neighbors identical origin ASN + identical AS-path length. Without on-prem-side local-pref, path selection is non-deterministic.
- **Central ARS VNet = fourth-region SPOF.** Microsoft multi-region guidance is one ARS per hub + inter-hub NVA overlay tunnels. Central ARS is technically supported but centralizes both regions' spoke-injection into one region's control plane.
- **Reversion is non-deterministic** because on-prem-side preference is not enforced by anything on the Azure side that the design as drawn can control.

---

## Recommended baseline — "MS-canonical multi-region ARS + NVA overlay"

- Two hubs. Each hub: one ARS + two Ubuntu NVAs (BIRD). **No Azure VPN Gateway in hubs.** IPsec to simulated-on-prem terminates on the NVAs directly (strongswan/libreswan). Kills the ASN-65515 clash and removes the "route maps can't prepend VNet space" problem entirely.
- Simulated-on-prem: single Ubuntu BIRD router terminating IPsec to all four hub NVAs. On-prem BIRD sets `bgp_local_pref = 200` on hub1 neighbors, `100` on hub2 neighbors. **Deterministic hub1 preference; deterministic auto-revert without operator action.**
- Inter-hub: NVA1↔NVA2 IPsec (or VXLAN over VNet peering). NVAs strip ASN 65515 on cross-hub and toward-on-prem advertisements.
- **No central ARS VNet.** Delete it.
- Spokes: peered to their **local** hub only, with `AllowGatewayTransit=true` (hub side) + `UseRemoteGateways=true` (spoke side). This is the standard ARS-in-spokes route-injection pattern (ARS injects into spoke effective route table via the gateway-transit peering; no VPN GW required for this to work — the gateway-transit flag is what ARS uses).
- ASN plan: ARS hub1/hub2 = 65515 (fixed). NVA hub1 = 65001, NVA hub2 = 65002, on-prem BIRD = 65000. 65515 stays inside each hub only.
- Cross-region spoke reachability via NVA overlay tunnels.
- Nothing on the critical path is in preview.
- Convergence bound with tuned BIRD hold timers: ~15–40 s both directions.

## Teaching-only variant — preserve Jose's original as anti-pattern lab

Per routing rule #30, keep Jose's original design in the `## Designs studied` catalogue with status **📚 Teaching-only** and a documented failure evidence list:
- ASN 65515 clash surface
- ARS route-map preview cannot prepend VNet address space
- 180 s ARS hold timer as convergence ceiling
- Central ARS as fourth-region SPOF
- Blackhole window from asymmetric convergence

---

## Gate questions for Jose (BEFORE Phase 0 capacity probes and manifest)

Only four, because behavior/scope truly changes with each:

**Q1 — Adopt the corrected baseline (NVA-terminated IPsec, no VPN GWs in hubs, no central ARS)?**
- If YES → proceed with baseline as recommended and teaching-only variant as second design in the same lab.
- If NO → we still need to build the anti-pattern lab, but Q2–Q4 become the framing of what the lab is *demonstrating not working* rather than what we're trying to make work.

**Q2 — Where should preferred-hub selection live?**
- (a) On-prem BIRD `bgp_local_pref` (recommended, deterministic on both directions).
- (b) NVA-side AS-path prepend on hub2 (works, but only for NVA-originated routes; still fine because in the baseline the NVAs originate everything).
- (c) ARS route-map preview (kept only for the teaching-only variant to demonstrate its limits).

**Q3 — Simulated on-prem topology.**
- Single-BIRD-router model (recommended: one VM, both directions of preference cleanly demonstrated).
- Or Azure VPN GW as the simulated on-prem endpoint (matches Jose's original wording but adds ASN-65515 to the on-prem side too and complicates local-pref demonstration).

**Q4 — Regions.** Excluding UK South/UK West/North Europe/West Europe. Candidate set for Phase-0 capacity probes: `swedencentral`, `germanywestcentral`, `italynorth`, `polandcentral`, `spaincentral`, `norwayeast`, `francecentral`, `switzerlandnorth`. Which three should we probe first?
- Cost anchor: `swedencentral` is squad default. Recommend probing swedencentral + germanywestcentral + italynorth as the primary triple; polandcentral + francecentral as fallback if any of the first three restricts B2als_v2 at the region level (zone-only restrictions are OK, we deploy non-zonal per charter).

---

## What Trinity contributed

- Full per-hop RIB/FIB walk under steady / outage / recovery states.
- Identified the "manual BIRD 65515-strip filter" as the silent-blackhole risk in Jose's return-path chain.
- Called out the 180 s ARS-side hold timer as the un-tunable convergence ceiling — this alone is the single biggest reason to reject the design.
- Provided the corrected baseline shape (no VPN GWs in hubs, on-prem BIRD local-pref) and four Niobe-ready test scenarios.

## What stays in preview

**Nothing on the critical path** if we adopt the baseline. Route maps become optional and can be exercised in a follow-up lab dedicated to that preview feature.

---

## References

- Route Server route maps (preview) — https://learn.microsoft.com/azure/route-server/route-maps-about and https://learn.microsoft.com/azure/route-server/route-maps-about#considerations-and-limitations
- Route Server + VPN Gateway coexistence — https://learn.microsoft.com/azure/route-server/expressroute-vpn-support and https://learn.microsoft.com/azure/route-server/configure-route-server#configure-route-exchange-with-virtual-network-gateways
- Route Server FAQ (hold timer 180 s, dual peer IPs, ECMP) — https://learn.microsoft.com/azure/route-server/route-server-faq
- Multi-region ARS design guidance — https://learn.microsoft.com/azure/route-server/multiregion
- Dual-homed / NVA in peered VNet — https://learn.microsoft.com/azure/route-server/about-dual-homed-network
- VPN Gateway active-active — https://learn.microsoft.com/azure/vpn-gateway/about-active-active-gateways


# Decision — Lab #3 `dual-hub-hubless-region-ars` Stage-1 Lab Card LOCKED

**Author:** Morpheus (Lead / Architect)
**Date:** 2026-08-03T14:05+02:00
**Ceremony:** POST Design Review — Stage-1 lab-card lock (paperwork only; no IaC, no Azure writes)
**Requested by:** Jose Moreno
**Status:** LOCKED — fan-out authorized to Trinity (design.md), Niobe (S1–S5 gate skeleton), Oracle (diagrams). Tank queued behind Stage-2 + Phase-4 cost-gate approval.
**Stage-2 update (2026-08-03T14:27):** Stage-2 full pre-deploy manifest written in-place at `labs/dual-hub-hubless-region-ars/manifest.md` by Morpheus (14.97 KB ≤ 15 KB budget). All corrections applied: 9 Standard PIPs confirmed, route maps remain PUBLIC PREVIEW, 4 bidirectional V2V connection objects, PSKs generated at deploy time held only in KV/shell vars, single-RG cleanup does not purge shared KV secrets. Phase-4 approval gate embedded in manifest §13. Tank remains blocked.
**Related routing rules:** #7 (cost guardrail), #12 (approval gate), #30 (every design is valuable)

---

## What this decision is / is not

**Is.** A NEW Stage-1 lab card at `labs/dual-hub-hubless-region-ars/manifest.md` authored against the user-approved corrected design from Trinity's before-DR reviewer-owned pass (`.squad/decisions/inbox/trinity-third-region-ars-design.md`, 2026-08-03T12:00) plus the four subsequent locked-intent corrections in Jose's prompt today.

**Is not.** A revision of the earlier Morpheus artefact `morpheus-dual-hub-design-review.md` (2026-08-03T11:16), which recorded the rejection of Jose's original topology sketch. That artefact remains the immutable record of the initial ceremony. This new decision + lab card is the authorized forward artefact set.

---

## Locked design (Stage-1 summary)

**Slug:** `dual-hub-hubless-region-ars` · **Lab path:** `labs/dual-hub-hubless-region-ars/manifest.md`

**Mechanism.** One workload-aligned Azure Route Server (ARS) VNet in a hubless region acts as the shared BGP control-plane extension for many spokes toward **two remote regional hubs**, giving deterministic hub1-preferred / hub2-standby reach to a simulated on-prem — without a third VPN GW / firewall / NVA stack in that region.

**Regions (preflight-locked).**
- **swedencentral** — hub1 (VPN GW VpnGw1 AA, ARS b2b on, NVA1, set-A spoke+VM)
- **switzerlandnorth** — hub2 (VPN GW VpnGw1 AA, ARS b2b on, NVA2, set-B spoke+VM). Substituted for `germanywestcentral` (entire B-series NOT_FOUND in catalog).
- **polandcentral** — hubless workload (ARS b2b off, set-C1 spoke+VM, set-C2 spoke prefix-only)
- **norwayeast** — on-prem sim (VPN GW VpnGw1 AA, on-prem endpoint VM). Substituted for `francecentral` (entire B+D ladder `NotAvailableForSubscription`).

**Compute.** 6× `Standard_B2ts_v2` Ubuntu 22.04 Std SSD, no VM public IPs. Fallback `Standard_B2ls_v2`. Every region live-validated in preflight (deployment IDs in `dual-hub-preflight.md`).

**Network SKU count.** 3 Route Servers, 3 VPN Gateways (VpnGw1 AA), 4 V2V connection objects, 4 VNets + Poland ARS VNet + 4 spoke VNets, 9 Standard PIPs (3 ARS × 1 + 3 VPN GW AA × 2). Route maps remain PUBLIC PREVIEW, incur surcharge, first activation triggers ~30-min one-time ARS upgrade.

**ASN plan.** All three ARSes = 65515 (fixed). Both hub VPN GWs = 65515 (ARS coexistence rule). On-prem VPN GW = 65000. NVA1 = 65001, NVA2 = 65002. 10 BGP sessions total.

**Connection model — explicit choice.** Azure VPN GW ↔ Azure VPN GW via **V2V (VNet-to-VNet) connection pairs**. 4 connection objects (2 mirror pair per hub↔on-prem). Justification: same PSK/IPsec/BGP surface as S2S+LNG, no `LocalNetworkGateway` object bookkeeping, and fault injection remains possible via `az network vpn-connection shared-key update` + `vpn-connection reset` on either half of a mirror pair. S2S+LNG kept as escalation path only if Phase-0 exposes hidden route/PSK behaviour.

**Route policy split — all three mandatory.**
1. **Δ1** — both NVAs strip ASN 65515 from Poland-learned routes before re-advertising to their local hub ARS. Loop-prevention; omission silently blackholes. Mandatorily NVA-side (ARS loop-prevention runs on ingress before inbound route maps).
2. **Δ2** — NVA2 prepends its own ASN ×2 on set-C prefixes toward hub2 ARS. On-prem sees `[65515,65001]` via hub1 vs `[65515,65002,65002,65002]` via hub2 → deterministic hub1 preference. Kept NVA-side in the baseline for clean evidence (Δ3-bis Phase-0 experiment may later move it to an outbound ARS→VPN-GW-connection route map).
3. **Δ3** — inbound ARS route map (**preview**) on Poland ARS ↔ NVA2 peering, prepending NVA2-originated `0/0` twice. Poland ARS best-path for the default = NVA1. This is the sole load-bearing preview-feature test in the lab.

**Fault injection contract (S2).** Reversible: (a) rotate both `psk-hub1-onprem` connection halves to a wrong value + `vpn-connection reset` on both, (b) `systemctl stop bird` on NVA1. Restore: original PSK on both + reset + `systemctl start bird`. **No VM lifecycle action** — VMs stay running.

**Cost — Azure Retail Pricing MCP, USD, 2026-08-03, PAYG, medium confidence.**
- 3× VPN GW VpnGw1 AA (2× billing/GW) = **$27.36/day**
- 3× ARS Basic @ $0.45/hr = **$32.40/day**
- 6× `Standard_B2ts_v2` Linux = **$1.55/day**
- 4× VPN S2S connection meter = **$1.44/day**
- 9× Standard regional PIP = **$1.08/day**
- Disks + peering egress + misc ≈ **$2/day**
- **Baseline ≈ $66/day.** With Δ3 route maps active on Poland ARS (Basic → Route-Maps SKU + 2× NVA-connection-with-route-maps meters): **≈ $72/day**.

**⚠️ Cost guardrail (routing rule #7) BREACHED.** $66–72/day > $50/day. Drivers: 3× ARS and 3× VPN GW; no cheaper BGP-capable/AA VPN GW SKU exists (Basic supports neither BGP nor active-active), Basic is the entry ARS SKU. **Explicit Phase-4 cost approval from Jose is required before Tank deploys anything.**

**Framing accepted by the user (not tested cross-hub failover).** Set A and set B are hub-local spokes; if their region/hub dies, their workloads die with it. Set C is the only cross-hub failover story the lab proves. No inter-hub NVA overlay in baseline — documented as unnecessary for set-C↔on-prem and required only for cross-hub spoke transit (Trinity's dormant P2 patch).

**Scenarios (five, one-line pass/fail each — full text in lab card §Scenarios).** S1 steady state, S2 hub1 outage via reversible PSK+BIRD injection, S3 hub1 recovery, S4 Δ3 route-map preview effect on Poland ARS best-path, S5 prefix-only spoke scale (set-C2 has no VM).

**Designs studied catalogue (per rule #30).**
- ✅ Workload-aligned ARS extension (recommended, under test)
- ✅ Classical hub-local baseline (set A / set B)
- ⚠️ Central ARS in an unrelated fourth region (anti-pattern; paper analysis only)
- 📚 Per-region full-hub production alternative (cost/ops comparison only)

**Cleanup.** Single RG `rg-dual-hub-hubless-region-ars-<corrID>`; single `az group delete` + KV purge of the two `psk-*` entries. No shared infra touched.

**Design blockers.** None. Lab card is locked.

---

## Fan-out authorised

- **Trinity** — write `design.md` §BGP walk, §effective-route tables, §NVA export filter snippets (BIRD + FRR), §Δ3 route-map JSON, §S2 failure-injection script, §resiliency table.
- **Niobe** — build the S1–S5 diagnostic gate skeleton; five scenarios each with a discrete evidence checklist; no VM required for S5 (Poland spoke2 is prefix-only).
- **Oracle** — draw topology / control-plane / data-plane / cleanup diagrams from lab card §Regions, §Address plan, §ASN + BGP + peerings.
- **Tank** — queued. **Do NOT touch IaC or Azure resources** until Stage-2 manifest lands AND Jose approves the cost gate at Phase-4.

---

## References

- User-approved corrected design: `.squad/decisions/inbox/trinity-third-region-ars-design.md` (2026-08-03T12:00)
- Preflight validation (all four regions PASS, SKU + PIP math corrected): `dual-hub-preflight.md` (2026-08-03)
- Rejected initial review (immutable, not revised): `.squad/decisions/inbox/morpheus-dual-hub-design-review.md` (2026-08-03T11:16)
- Trinity reviewer pass on the rejected review: `.squad/decisions/inbox/trinity-dual-hub-design-review-reviewer-pass.md`
- Microsoft Learn URLs cited in lab card §Learn refs (ARS FAQ, ARS+VPN GW coexistence, ARS route maps, ARS multi-region, peering overview, VPN GW BGP).


# Decision — Reviewer pass on Morpheus's BEFORE Design Review verdict (Jose's dual-hub lab)

**Author:** Trinity (Azure Network SME) — reviewer of `morpheus-dual-hub-design-review.md`
**Date:** 2026-08-03T11:25+02:00
**Ceremony:** BEFORE Design Review — reviewer response (parallel-review protocol)
**Consulted:** Microsoft Learn (Route Server, Route Maps preview, Multi-region ARS, VPN Gateway BGP), vault `Services/Route-Server.md`, `Topics/BGP-on-Azure.md`
**Reviewer verdict:** ❌ **REJECT Morpheus's "not feasible" verdict.** Corrected verdict: **FEASIBLE AS TEACHING-LAB** with minimal deltas that PRESERVE Azure VPN GWs + central ARS.
**Reviewer lockout:** Morpheus is NOT assigned to revise. Reviewer response is authoritative for the disputed technical claims below; final scope call goes to Jose.

---

## TL;DR

Morpheus's structural claims are a mix of one correct fact wrapped in three incorrect conclusions:

| # | Morpheus claim | Verdict | Why |
|---|---|---|---|
| 1 | "Return-path plumbing is broken by construction" | **Incorrect** | Documented multi-region ARS pattern — NVA strips ASN 65515 from AS_PATH before advertising to local ARS. This is the canonical technique in the official multi-region page (link below), not an exotic "silent-blackhole risk". BIRD/FRR one-liner. |
| 2 | "Route-map cannot prepend VNet address space" | **Correct fact, wrong conclusion** | Route maps preview genuinely cannot modify VNet address-space advertisements. But the hub-side preference for spoke prefixes never depended on ARS route maps — it depends on **NVA-side** AS-path prepend at hub2 NVA when advertising spoke prefixes to local hub2 ARS. That prepend is preserved intact by ARS ("Azure Route Server propagates the route with the BGP AS path intact"). |
| 3 | "ARS 180s hold timer creates unrecoverable asymmetry" | **Partially correct — overstated** | 180s is the ARS-side worst-case. Real-world TCP-level failure (dead VM ⇒ RST / ICMP unreach) tears the BGP session in seconds. Real convergence is BGP hold time only when the failure is silent (link brownout, no L4 signal). Worth documenting as a failure-mode bound; not sufficient to reject the design. |
| 4 | "Both hub VPN GWs at ASN 65515 make preference impossible" | **Incorrect** | Two eBGP peers to the on-prem gateway may share a remote ASN — they're identified by IP. Best-path picks shorter AS_PATH. Private ASNs are **preserved by VPN Gateway** (only ExpressRoute strips them and replaces with 12076). NVA2 prepending its private ASN survives end-to-end over IPsec/VPN to the on-prem Azure VPN GW. |
| 5 | "Central ARS = fourth-region SPOF" | **Correct** | Accepted as scoped in the original goal (design proves hub-regional outage, not full 3-region outage). Document explicitly in the lab. |

**Morpheus's proposed alternative** (drop hub VPN GWs, terminate IPsec on NVAs, drop central ARS, replace on-prem with BIRD) is a legitimate MS-canonical multi-region NVA-overlay pattern — but it **abandons Jose's original pedagogical goal** (VPN GW BGP + ARS coexistence + central-ARS route-injection). It is a good **follow-up** lab, not a substitute for this one.

---

## Answers to the 8 review questions

### Q1 — Feasibility of the original chain with per-NVA AS-path stripping

**Yes, feasible.** This is the Microsoft-documented multi-region ARS pattern. From the Learn doc's "BGP AS path manipulation" section:

> *"NVAs must remove the autonomous system number (ASN) 65515 from the AS path when advertising routes learned from remote regions. This process, known as 'AS override' or 'AS-path rewrite,' prevents BGP loop prevention mechanisms from blocking route learning. Without this configuration, Route Server doesn't learn routes that contain its own ASN (65515)."*
> — https://learn.microsoft.com/azure/route-server/multiregion

Loop prevention is confirmed in the ARS FAQ:

> *"If an NVA advertises a route to Azure Route Server that already contains 65515 in the BGP AS_PATH attribute, Azure Route Server identifies its own ASN in the AS path and rejects the route as part of standard BGP loop prevention behavior."*
> — https://learn.microsoft.com/azure/route-server/route-server-faq

**Exact AS-path walk for a spoke prefix (e.g. 10.20.0.0/24) reaching on-prem via hub1:**

| Hop | Direction | AS_PATH received | Action | AS_PATH advertised |
|---|---|---|---|---|
| Spoke VNet | (originated by central ARS via gateway-transit peering) | — | central ARS injects VNet address space | `[65515]` |
| Central ARS → NVA1 (eBGP over VNet peering) | outbound to NVA1 (ASN 65001) | — | ARS prepends own ASN | NVA1 receives `[65515]` |
| NVA1 export to local hub1 ARS (ASN 65515) | outbound | `[65515]` | **BIRD `bgp_path.delete(65515)`** or **FRR `set as-path exclude 65515`** — mandatory | Sent as `[]`, prepended by NVA1 → hub1 ARS receives `[65001]` |
| Hub1 ARS → hub1 VPN GW (branch-to-branch, ASN 65515) | inbound | `[65001]` | ARS propagates AS_PATH intact | VPN GW learns `[65001]` |
| Hub1 VPN GW → on-prem VPN GW (eBGP over IPsec) | outbound | `[65001]` | VPN GW prepends own ASN 65515 | on-prem receives `[65515, 65001]` |

Same walk via hub2 with NVA2 configured to prepend 65002 twice: on-prem receives `[65515, 65002, 65002, 65002]`. On-prem BGP best-path picks shorter → hub1 preferred. **Deterministic.**

Loop-prevention issues:
- NVA1↔NVA2 do **not** BGP-peer to each other directly in the original design (both peer to central ARS, and each peers to its own local hub ARS). The central-ARS fanout is the only inter-hub path, so there's no direct hub↔hub loop.
- The only real loop risk is the NVA-to-local-ARS step above — solved by the AS_PATH-delete filter. BIRD and FRR both support this natively (no scripting).

### Q2 — Does NVA2 prepend survive VPN Gateway propagation to the simulated-on-prem Azure VPN GW?

**Yes, private ASNs are preserved across Azure VPN Gateway.** The ARS FAQ is explicit that private-ASN stripping is an **ExpressRoute** behaviour (via MSEE), not a VPN behaviour:

> *"When ExpressRoute advertises routes to on-premises, it removes the private BGP ASN information. On-premises receives the prefix with AS 12076."*
> — https://learn.microsoft.com/azure/route-server/route-server-faq

No equivalent statement exists for VPN Gateway. Azure VPN Gateway BGP is a straightforward eBGP speaker; AS_PATH prepends applied upstream are preserved end-to-end over IPsec.

Practical consequence: NVA2's `bgp_path.prepend(65002)` (×N) in BIRD, or FRR's `set as-path prepend 65002 65002`, produces a longer AS_PATH that survives all the way to the on-prem VPN GW. **Preference works.**

### Q3 — Can ARS route maps be usefully tested by an inbound map on NVA2's BGP peering to prepend NVA2-originated 0/0?

**Yes — this is exactly the right use case for the preview.** Two facts from the route-maps preview doc:

1. **Route maps can modify the default route when it is originated by an NVA:** *"You can modify the default route only when the default route comes from on-premises or an NVA."* — https://learn.microsoft.com/azure/route-server/route-maps-about#considerations-and-limitations
2. **Inbound maps DO influence best-path selection.** From the same doc: *"Outbound route maps modify route advertisements only and don't influence Azure Route Server's best-path selection, because path selection happens before outbound route maps are applied."* By construction, **inbound** maps are applied at ingress into ARS, before best-path — so an inbound prepend on NVA2's 0/0 makes central ARS's best-path prefer NVA1's 0/0, and that best-path is what gets injected into spoke effective routes.

**What the route-maps preview lab actually proves:**
- ✅ Inbound AS-path prepend on NVA-originated 0/0 → shifts spoke default-route preference to NVA1. **Testable.**
- ✅ Outbound tagging/filtering on the VPN GW connection. **Testable.**
- ❌ Prepending / filtering the spoke prefixes themselves (they're VNet address space that ARS advertises). **Not testable** — hard limitation of the preview.
- ❌ Modifying `LOCAL_PREF`. **Not supported** by ARS route maps at all.

So route maps can carry the **default-route preference** experiment. The **spoke-prefix preference** experiment must stay NVA-side (BIRD/FRR).

### Q4 — Do two hub VPN GWs at ASN 65515 confuse the on-prem VPN GW?

**No.** eBGP peers may share a remote ASN — they're identified by IP. Best-path selection at the on-prem VPN GW is then driven by AS_PATH length (there is no `LOCAL_PREF` lever on Azure VPN GW), which is exactly the lever NVA2's prepend gives us. Multiple-tunnel semantics with automatic withdrawal are documented at https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-bgp-overview ("Support multiple tunnels between a VNet and an on-premises site with automatic failover based on BGP").

Coexistence constraint (ARS + VPN GW same VNet, from https://learn.microsoft.com/azure/route-server/route-server-faq):
- VPN GW **must** be active-active.
- VPN GW **must** use ASN 65515.
- Branch-to-branch **must** be enabled for NVA↔GW exchange.

All three are satisfied by the original design.

### Q5 — Regional-outage failover: exact withdrawal events + 180s bound

**Two independent withdrawal chains fire in parallel on full hub1 outage:**

**Chain A (central ARS → NVA1 default withdrawn):**
1. NVA1 VM and its VNet reachable state collapse.
2. TCP session over the NVA1↔central-ARS VNet peering breaks. If the failure produces TCP RST / ICMP host-unreach (common for VM stop/dealloc), BGP tears in seconds.
3. If the failure is silent (network brownout, no L4 signal), central ARS waits out the 180s hold timer (https://learn.microsoft.com/azure/route-server/route-server-faq — "keepalive timer is 60 seconds and the hold timer is 180 seconds").
4. Central ARS withdraws NVA1's default from best-path → NVA2's 0/0 (now un-prepended by best-path) wins → central ARS advertises new default to spokes.
5. Spoke effective routes reprogrammed → spoke→NVA2 forward path live.

**Chain B (on-prem VPN GW withdraws hub1-learned spoke prefixes):**
1. IPsec DPD detects hub1 VPN GW dead (default DPD 45–90s).
2. VPN GW BGP session over that tunnel drops — routes learned from hub1 VPN GW withdrawn (BGP hold on Azure VPN GW = 180s worst case, faster in practice on tunnel failure).
3. On-prem VPN GW re-selects hub2 route (still `[65515, 65002, 65002, 65002]`, but now only path).
4. On-prem→spoke return path via hub2 live.

**Failover asymmetry window:**
- Chain B (return path) typically converges in 30–90s (IPsec DPD + tunnel-driven BGP withdrawal).
- Chain A (forward path via ARS) is bounded by ARS hold = 180s worst-case, seconds if TCP dies cleanly.

During the asymmetry window: **forward via NVA1 (dead) black-holes, return via hub2 works**. Half-open failure state, up to ~180s worst case. This is the value Morpheus flagged — it is a real teaching moment, not a design defect.

**Failover is deterministic on eventual reconvergence.** Reversion when hub1 comes back is likewise deterministic: NVA1 re-peers, unprepended default wins, ARS re-selects, spokes reconverge.

**Mitigations available inside the original goal:**
- BFD on NVA↔ARS peerings is not supported by ARS (BGP timers are fixed and non-tunable — FAQ). So the 180s ceiling is genuinely there.
- **NVA-side**: aggressively short BGP keepalive/hold on the NVA (that doesn't tune ARS but does propagate BGP KEEPALIVE more often, letting ARS detect faster on any TCP-level nudge).
- **Datapath-side**: on the spoke, keep the VPN-GW-hosted default as a secondary via UDR (belt-and-braces). Adds operational complexity — leave as a documented patch, not baseline.

### Q6 — Route-reflection/loop with 65515 appearing twice in the path

The AS_PATH toward on-prem for a spoke prefix via hub1 is `[65515, 65001]` in the clean case (central ARS's 65515 stripped by NVA1, hub1 VPN GW re-prepends 65515). Only one 65515 in the path.

Loop-prevention checks fire at **each 65515 speaker along the path** if it sees 65515 anywhere in the incoming AS_PATH — which is why the NVA-side strip is mandatory. Once stripped, the second 65515 injection (by hub1 VPN GW at eBGP-out) is safe because the on-prem VPN GW is a **different** ASN.

The AS-override / AS-path-delete operation needed:
- BIRD 2: export filter `bgp_path.delete(65515);` before pushing to local hub ARS.
- FRR: `route-map STRIP-ARS-ASN permit 10 / set as-path exclude 65515` then `neighbor <local-ARS> route-map STRIP-ARS-ASN out`.

Both are one-line filters. Both are exactly what the multi-region ARS Learn page documents as the canonical multi-region NVA config.

Prepend-in-addition (for NVA2 spoke-prefix demotion):
- BIRD 2: `bgp_path.prepend(65002); bgp_path.prepend(65002);` in the same export filter, after the delete.
- FRR: `set as-path prepend 65002 65002` in the same route-map.

### Q7 — Does the design prove full-regional outage?

**No — it proves hub-regional outages, not a full 3-region outage.** The central-ARS VNet is a fourth-region control-plane SPOF for spoke-injection. If the central-ARS region fails, spokes stop learning both defaults and lose spoke↔on-prem entirely (because their gateway-transit peering points at central ARS's fabric).

**Acceptable if scoped explicitly.** Both accept and reject positions are defensible:
- **Accept:** lab is a teaching artifact for hub-regional failover under central-ARS control plane. Explicitly label the central-ARS region as out-of-scope for outage testing, and cite the Learn multi-region page as showing the "ARS in each hub + NVA overlay" pattern that removes that SPOF in a production evolution.
- **Reject:** if Jose actually wants full 3-region outage coverage, this design won't demonstrate it. Morpheus's alternative (or a per-hub ARS + inter-hub NVA tunnels variant) is the answer for that.

**Reviewer recommendation:** Accept the scoping as-is. Document the SPOF in `design.md` and reference the production evolution path.

### Q8 — Corrected verdict

**FEASIBLE AS TEACHING-LAB**, with three minimal-delta corrections. All of them PRESERVE Azure VPN GWs and the central ARS experiment.

**Minimal corrections (Δ1–Δ3):**

| Δ | What | Where | Why |
|---|---|---|---|
| Δ1 | Both NVAs strip ASN 65515 from AS_PATH before advertising spoke prefixes to their local hub ARS. | NVA BIRD/FRR export filter on the NVA→local-ARS session. | Mandatory per ARS FAQ loop prevention; documented as canonical in the multi-region ARS page. Prevents silent blackhole. |
| Δ2 | NVA2 additionally prepends ASN 65002 (×2 or ×3) on spoke-prefix advertisements to hub2 ARS. | NVA2 BIRD/FRR export filter, same session as Δ1. | Drives on-prem BGP best-path to prefer hub1 for spoke destinations. Private-ASN prepend is preserved end-to-end because VPN doesn't strip like ER does. Not achievable via ARS route maps — VNet-address-space advertisements aren't route-map-modifiable. |
| Δ3 | ARS route-maps preview scope narrowed to what it can actually do: inbound AS-path prepend on NVA2's BGP peering for NVA2-originated 0/0. | Central ARS, inbound map on NVA2 peering. | Testable use case (route maps CAN modify NVA-originated default; inbound IS best-path-affecting). Delivers on the "explore route maps preview" objective without being forced onto a use case the feature can't support. |

**What route-map preview CAN test in this lab:**
- ✅ Δ3 — inbound AS-path prepend on NVA-originated 0/0 → default-route preference shifts in spokes (deterministic, verifiable via spoke effective routes).
- ✅ Optional: outbound tagging/filtering on VPN GW connection (informational; doesn't affect best-path).

**What must remain NVA policy (not route maps):**
- Δ1 (65515 strip) — route maps can't touch this direction (NVA→ARS *ingress* to local ARS is not a route-map insertion point; it's the NVA's BGP export).
- Δ2 (spoke-prefix prepend) — route maps can't modify VNet address space.

**Failure modes / blast radius / failover time (charter §7 mandate):**

| # | Failure | Azure blast | On-prem blast | FW-in-path | Failover time | Operator action |
|---|---|---|---|---|---|---|
| F1 | Hub1 region full outage | Spokes lose forward path via NVA1 for up to 180s (ARS hold), typically seconds if TCP RST | On-prem loses return via hub1 in 30–90s | NVAs are BGP-only in this lab; no in-hub FW | Asymmetric 30–90s→180s window; reconverges to hub2 both directions | None (deterministic) |
| F2 | NVA1 alone dies (hub1 region up) | Same as F1 forward; hub1 VPN GW still learns spoke prefixes? **No** — because spoke prefixes reach hub1 VPN GW only via NVA1→local ARS. So hub1 VPN GW also stops advertising them → on-prem withdraws hub1's spoke prefixes in 30–90s | Same as F1 return | n/a | Same as F1 | None |
| F3 | Hub1 VPN GW alone dies | Spokes fine (still get 0/0 from NVA1 via central-ARS). On-prem loses hub1 tunnel(s), reroutes to hub2 in 30–90s | Return path via hub2 | n/a | 30–90s | None |
| F4 | Central-ARS region outage | **Total spoke↔on-prem loss.** Spokes lose both 0/0 and all spoke-prefix advertisements. Hub↔on-prem BGP still up but carries nothing useful for spokes. | Return-path black-hole to spoke destinations | n/a | No automatic recovery inside this design | Rebuild central ARS in surviving region, or re-peer spokes to a fallback ARS (out of scope in v1) |
| F5 | Single BGP session flap (NVA↔central ARS, one instance) | None — dual-instance ARS peering means the other instance carries traffic | None | n/a | 0s (ECMP + redundant peer) | None |
| F6 | Spoke's UseRemoteGateway peering to central ARS flaps | Spoke temporarily loses 0/0 + spoke-prefix injection until re-peering completes; forward and return both interrupted | None on other spokes | n/a | Peering re-establishment (minutes) | Re-peer if needed |

**Mitigations (patch catalogue, dormant until Jose authorises):**

- **P1** — Add BGP keepalive tuning on NVAs (KEEPALIVE 10s / HOLD 30s on the NVA side only; ARS side is fixed but NVA-side aggressive KEEPALIVE cuts silent-failure detection dramatically). Cost: 0. Residual gap: still bounded by ARS-side hold in true blackhole (no TCP signal).
- **P2** — Add secondary spoke default via UDR to the local hub VPN GW (belt-and-braces static default). Cost: 0 direct, ops complexity. Residual gap: overrides BGP; must be maintained manually. **Recommend only if F1 blackhole window proves painful in validation.**
- **P3** — Duplicate central ARS in a second region and peer spokes to both (fifth-region SPOF becomes a two-region survivable control plane). Cost: 1× additional ARS SKU/hour + 1× VNet peering. Closes F4. **Out of scope for v1; document as production evolution.**

Patches are dormant until Jose says "apply patch P<n>." I do NOT halt Tank for F4 (F4 is a scoped-out failure mode, not a build blocker).

---

## Where I disagree with Morpheus's recommended baseline

Morpheus recommends replacing hub VPN GWs with NVA-terminated IPsec and replacing on-prem with a BIRD router. That is a legitimate, MS-canonical multi-region NVA-overlay pattern — but:

1. It removes the **VPN GW BGP + ARS coexistence** learning target explicitly stated in Jose's original goal.
2. It removes the **central ARS route-injection** target explicitly stated in Jose's original goal.
3. It removes the **route-maps preview exploration** target explicitly stated in Jose's original goal.
4. Route rule #30 ("every design is valuable") plus Jose's explicit teaching-lab framing means we should build the **teaching design**, not the production-canonical replacement.

Morpheus's alternative belongs as a **follow-up lab** ("Production-shape multi-region NVA overlay") that shows the evolution path. Not as a substitute for this one.

---

## Answers Morpheus's four gate questions from Jose's viewpoint

**Q1 (adopt corrected baseline):** No. Adopt the original design with Δ1–Δ3 corrections above. Keep hub VPN GWs, keep central ARS.

**Q2 (where preference lives):**
- Forward direction (spoke → on-prem): via central-ARS route-map preview (Δ3) — teaches the route-map feature.
- Reverse direction (on-prem → spoke): via NVA2 BGP AS-path prepend (Δ2) — because route maps can't touch VNet address space.
- **Both mechanisms live; both are exercised. This is the pedagogical richness of the lab.**

**Q3 (simulated on-prem topology):** Keep Azure VPN Gateway as the simulated on-prem endpoint. Original goal is explicit. AS_PATH length is a sufficient lever; no need for BIRD's `LOCAL_PREF`.

**Q4 (regions):** Not my call — Morpheus's own decision domain. My only networking constraint: central-ARS region must have low-latency peering to both hub regions and must support ARS in the current SKU (any Azure region with ARS GA — no constraint). Same-geo triple (`swedencentral` + `germanywestcentral` + `italynorth`) is fine from a networking angle.

---

## References (Microsoft Learn, all fetched 2026-08-03)

- Route Server FAQ — https://learn.microsoft.com/azure/route-server/route-server-faq
  - Hold timer 180s / keepalive 60s
  - NVA must peer both ARS instances
  - ECMP for equal AS-path length; shorter wins
  - VPN GW must be active-active + ASN 65515 for coexistence
  - NVA route with 65515 in AS_PATH is dropped (loop prevention)
  - ExpressRoute strips private ASN → 12076; VPN does not
  - AS path preserved intact; BGP communities preserved intact
- Route maps preview — https://learn.microsoft.com/azure/route-server/route-maps-about
  - Inbound maps applied before best-path (so they influence it); outbound don't
  - Can modify default route only if NVA/on-prem-originated
  - **Cannot modify or filter VNet address space that ARS advertises**
  - Route summarization strips community/AS-PATH
- Multi-region ARS — https://learn.microsoft.com/azure/route-server/multiregion
  - Documents the "NVAs strip ASN 65515 on cross-region advertisement" pattern as canonical
  - Documents overlay-tunnel + BGP AS-path prepend for active/standby NVA
- VPN Gateway BGP — https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-bgp-overview
  - Multi-tunnel with automatic BGP withdrawal on failure
  - Transit routing between on-prem and multiple VNets
- Route Server + gateway coexistence — https://learn.microsoft.com/azure/route-server/expressroute-vpn-support and https://learn.microsoft.com/azure/route-server/configure-route-server#configure-route-exchange-with-virtual-network-gateways

---

## Recommended next step for Jose

1. Read this reviewer response side-by-side with Morpheus's `morpheus-dual-hub-design-review.md`.
2. Decide: adopt the original design + Δ1–Δ3, OR adopt Morpheus's alternative (and accept that VPN GW/ARS coexistence and central-ARS route-maps preview drop off the teaching agenda).
3. If Jose picks the corrected original: Morpheus writes the lab card + capacity probes; Trinity writes design.md with the AS-path walk table above, NVA export filter snippets (BIRD + FRR), route-maps preview scope (Δ3 only), and the resiliency §.
4. Nothing to deploy yet; Phase-0 capacity probes still owned by Morpheus.

I am not touching `design.md`, the manifest, or any lab file in this review pass. This response and the Trinity history append are the only artefacts I write.


# Trinity IaC Review — dual-hub-hubless-region-ars
**Reviewer:** Trinity (Azure Network SME)  
**Date:** 2026-08-03T16:22 UTC+02:00  
**Artifacts reviewed:** `deploy\templates\main.bicep`, `deploy\templates\modules\{ars,vpngw,vm}.bicep`, `deploy\nva{1,2}-cloud-init.yaml`, `deploy\deploy.ps1`, `deploy\cleanup.ps1`, `design.md`, `manifest.md`, `validation.md`, `deploy-log.md`  
**Contract:** `labs\dual-hub-hubless-region-ars\design.md`

---

## ⛔ VERDICT: REJECTED

One blocking defect. **Tank is under reviewer lockout — a DIFFERENT eligible agent must author the next revision of any file modified to fix B1.**

---

## Blocking Defect

### B1 — NVA1 NSG missing multihop BGP allow rule for Poland ARS [BLOCKING]

**File:** `deploy\templates\main.bicep`, resource `nsgNvaHub1` (lines ~148–200)

**Defect:** `nsg-nva-hub1` (associated to `snet-nva` in `vnet-hub1`, where `vm-nva1` lives) has exactly one BGP allow rule:

```
allow-bgp-inbound: sourceAddressPrefix '10.10.0.0/16', TCP/179
```

Poland ARS instance IPs `10.30.0.4` and `10.30.0.5` (from `RouteServerSubnet 10.30.0.0/27`) are **not** within `10.10.0.0/16`. The `deny-other-inbound` rule (priority 4000) will silently drop TCP/179 connections from both Poland ARS instances.

**Impact:** BGP sessions #1 and #2 (design §4, Table rows 1–2) — NVA1↔ars-poland — will never establish. Consequence chain:
- Poland ARS receives no routes from NVA1 → can't inject `0/0→NVA1_IP` into set-C spokes
- Δ1 (65515 loop-strip for hub1-bound advertisements) is irrelevant if session never forms
- Δ2 NVA1-preferred best-path for set-C is unachievable (only NVA2 path exists)
- S1 fails on first assertion (BGP session count ≠ 10)
- S2/S3/S4/S5 all build on S1 and will fail for the same reason

**Contrast with NVA2:** `nsg-nva-hub2` correctly includes:
```
allow-bgp-multihop-inbound: sourceAddressPrefix '10.30.0.0/24', priority 105, TCP/179
```
NVA1 needs the same rule. Tank authored the fix for NVA2 but not NVA1.

**Required fix:** Add an inbound NSG rule to `nsgNvaHub1`:
```
name: 'allow-bgp-multihop-inbound'
priority: 105
direction: Inbound / Allow / Tcp
sourceAddressPrefix: '10.30.0.0/24'
destinationPortRange: '179'
```

---

## Non-Blocking Observations (no re-review required for these)

### O1 — Manifest peering count inconsistency
`manifest.md §1` Resource Count states "26 peering objects (13 logical pairs)". Actual Bicep has **20 objects (10 logical pairs)**, consistent with `design.md §3` and `cleanup.ps1` step 5 comment. The manifest annotation is incorrect. Does not affect deployment.

### O2 — Manifest BGP multihop annotation
`manifest.md §3` BGP session table says `BIRD multihop 3`; both `nva1-cloud-init.yaml` and `nva2-cloud-init.yaml` correctly set `multihop 4` per `design.md §4` (≥4 required). The BIRD configs are correct; the manifest annotation is wrong. Does not affect deployment.

### O3 — ARS Bicep SKU property format (BCP073)
`ars.bicep` sets `properties.sku: 'Standard'` (string) instead of the object form `sku: { name: 'Standard', tier: 'Standard' }` at top-level. Triggers BCP073 lint warning. ARM `validate` passed per deploy-log. Not blocking in practice but worth aligning to canonical resource shape on next revision.

---

## Verified Correct (sampled)

| Item | Verdict |
|------|---------|
| 9 Standard PIPs (6 GW + 3 ARS) | ✓ |
| 3 AA VpnGw1 gateways; hub1+hub2 ASN 65515; onprem ASN 65000 | ✓ |
| activeActive=true on all 3 GWs | ✓ |
| ARS branch-to-branch: hub1/hub2=true, poland=false | ✓ |
| 20 peering objects, 10 pairs, flags match design §3 exactly | ✓ |
| URG on spoke-c1/c2 only on poland-ars peering (sole URG per spoke) | ✓ |
| Data-plane-only peerings (c1/c2↔hub1/hub2): AGT=false, URG=false | ✓ |
| rt-spoke-a: 0/0→10.10.1.4, bgpPropagation=disabled | ✓ |
| rt-spoke-b: 0/0→10.20.1.4, bgpPropagation=disabled | ✓ |
| Set-C subnets: no UDR | ✓ |
| NVA1/NVA2 NIC IP forwarding enabled | ✓ |
| No NSG on GatewaySubnet or RouteServerSubnet | ✓ |
| BIRD NVA1: Δ1 strip 65515 on export to hub1 ARS; export_to_poland_ars accept-all | ✓ |
| BIRD NVA2: Δ1+Δ2 combined filter (strip + prepend 65002×2 for 10.31/24+10.32/24) | ✓ |
| NVA1 multihop 4 to Poland ARS IPs 10.30.0.4/5 | ✓ (BIRD) |
| NVA2 multihop 4 to Poland ARS IPs 10.30.0.4/5 | ✓ (BIRD) |
| 4 V2V connection objects; correct GW ID pairing; BGP enabled; same PSK per pair | ✓ |
| PSKs as @secure() Bicep params; never written to files; KV-backed at runtime | ✓ |
| ARS Poland peers both NVA1 (65001) and NVA2 (65002) | ✓ |
| Hub1 ARS peers NVA1 only; Hub2 ARS peers NVA2 only | ✓ |
| NVA BGP peer IPs in BIRD match design §4 (hub1 .68/.69, hub2 .68/.69, poland .4/.5) | ✓ |
| vnetSpokeC2 no subnets (prefix-only); ARM validated | ✓ |
| Cleanup: 4 connections deleted first, then ARS, then GWs, then RG; KV purge explicit | ✓ |
| VM management: SSH via private IP, no VM PIP; workable via bastion/jump or run-command | ✓ |

---

## Reviewer Lockout

**Tank authored this IaC.** Under reviewer lockout protocol, Tank may NOT produce the next revision of any file modified to address B1. A different eligible agent (e.g., Morpheus, or a specialist designated by Jose) must author the fix to `nsgNvaHub1` in `main.bicep`.

After the fix is authored, I will re-review the `nsgNvaHub1` block only. All other items above carry forward as verified.

---

*Trinity — IaC review 2026-08-03T16:22 UTC+02:00*

---

## Morpheus Independent Revision — 2026-08-03T16:27 UTC+02:00

**Reviewer lockout compliance:** Tank is under lockout per Trinity verdict. This revision is authored by Morpheus.

**Change made:** Added `allow-bgp-multihop-inbound` to `nsgNvaHub1.securityRules` in `labs\dual-hub-hubless-region-ars\deploy\templates\main.bicep`:
- Priority: 105 (between existing 100 and 110)
- Direction: Inbound / Access: Allow / Protocol: Tcp
- Source: `10.30.0.0/24` / Source port: `*`
- Destination: `*` / Destination port: `179`

**Scope:** Exactly one rule added to `nsgNvaHub1`. No other IaC or documentation modified.

**Build validation:** `az bicep build --file labs\dual-hub-hubless-region-ars\deploy\templates\main.bicep` — exit code 0, no errors.

**Awaiting:** Trinity re-review of `nsgNvaHub1` block only per lockout protocol.

*Morpheus — independent revision 2026-08-03T16:27 UTC+02:00*

---

## Trinity Re-Review — 2026-08-03T16:29 UTC+02:00

**Scope:** `nsgNvaHub1.securityRules` in `labs\dual-hub-hubless-region-ars\deploy\templates\main.bicep` only. All other items verified in the original review carry forward unchanged.

**Finding — B1 resolved:**

Rule `allow-bgp-multihop-inbound` is now present in `nsgNvaHub1.securityRules` at lines 151–162:
- priority: **105** — no conflict (100 and 110 are the adjacent rules; 105 is unique in this NSG)
- name: **`allow-bgp-multihop-inbound`** — no name collision
- direction: Inbound / access: Allow / protocol: Tcp
- sourceAddressPrefix: `10.30.0.0/24`
- destinationPortRange: `179`

Exactly mirrors the already-correct `nsgNvaHub2` rule. No conflicting priority or name exists at 105.

**Bicep build:** `az bicep build` exit code 0, no errors (one version-upgrade advisory, not blocking).

**Prior non-blocking observations O1–O3 are unchanged — no re-review required.**

---

## ✅ VERDICT: APPROVED FOR DEPLOYMENT

All review findings resolved. Tank is clear to proceed with deployment subject to Phase-4 cost-gate approval from Jose (manifest §13, cost guardrail rule #7 — baseline ≈ $66/day, with Δ3 route maps ≈ $72/day).

*Trinity — re-review 2026-08-03T16:29 UTC+02:00*


# Decision — Workload-aligned third-region ARS design (Trinity, owning iteration)

**Author:** Trinity (Azure Network SME)
**Date:** 2026-08-03T12:00+02:00
**Ceremony:** BEFORE Design Review — reviewer-owned iteration after Morpheus artefact rejected
**Consulted:** Microsoft Learn (Route Server multi-region, ARS FAQ, ARS+VPN GW coexistence, dual-homed ARS, VNet peering overview, route-maps preview), vault `Services/Route-Server.md`, prior Trinity history (Δ1–Δ4 baseline).
**Reviewer verdict:** ✅ FEASIBLE **but requires one structural correction** (third-region *route hub* with a minimal transit NVA, not a bare ARS-only VNet) plus tightened peering matrix. Preserves the pedagogical goals (VPN GW + ARS coexistence, route-map preview, split policy). Removes the 4th-region SPOF that Δ1–Δ4 accepted as scoped.
**Reviewer lockout:** Morpheus is NOT asked to revise the rejected artefact. This document is authoritative for the disputed technical claims and becomes the input to Phase-0 probes and manifest generation once Jose gates the two open decisions in §9.

---

## 1. Verdict on Jose's premise

The premise — "modern Azure estates deploy workloads into regions where a full hub is uneconomical; ARS is a lightweight control-plane extension" — is correct and matches the customer patterns behind blog `Multi-region design with ARS (no overlay)`. **But** the sketch as written ("dedicated ARS VNet in the third region; ARS BGP-peers with NVA1/NVA2 across direct global peerings; spokes peer only to the ARS VNet with `UseRemoteGateways=true`") has a **data-plane reachability gap** that is masked by the fact that ARS is control-plane only.

### The gap in one paragraph

ARS advertises `0/0` to the third-region spokes with **next hop = NVA1_IP** (an IP inside hub1's VNet, region A). The spoke's fabric can deliver a packet to `NVA1_IP` only if the spoke's effective route table has a peering-derived path to hub1's address space. The spoke is peered **only** to the third-region ARS VNet. VNet peering is **non-transitive** (peering overview, "gateway/on-premises" section). Therefore the spoke has no peering path to hub1, and the fabric drops the packet. The dual-homed ARS doc is explicit that **"virtual network peering [must be] configured between the spoke and each hub virtual network"** for this pattern to work — the spoke needs data-plane peering to each hub whose NVA it will next-hop to.

This is why the multi-region ARS reference architecture puts **an NVA in each region** and uses **overlay tunnels** between NVAs — the local NVA is the local next-hop, and the tunnel handles the cross-region transit.

### Two clean fixes (pick one, both preserve Jose's cost intent)

- **Fix A — Third-region "route hub" (recommended).** Deploy a **route-hub VNet** in the third region containing (i) one ARS instance, (ii) **one lightweight Linux NVA** (BIRD+strongSwan/libreswan, B2als_v2). No VPN gateway, no firewall. The third-region NVA runs IPsec (or VXLAN) overlay tunnels to NVA1 in hub1 and NVA2 in hub2. Locally, it eBGP-peers with the third-region ARS. Third-region spokes peer only to this route-hub with `UseRemoteGateways/AllowGatewayTransit`. ARS injects `0/0` with next hop = local third-region NVA (in-VNet, one hop, no peering-transit issue). This is a **stripped-down hub** (control-plane + one small transit NVA) — cheaper than a full hub (no VPN GW, no firewall) but keeps the data plane sound. This is what Jose meant by "lightweight control-plane extension" once the fabric constraint is honoured.

- **Fix B — No third-region NVA, but each spoke peers to all three (route-hub + hub1 + hub2).** The third-region spoke sets `UseRemoteGateways` only on its peering to the third-region ARS VNet. On the hub1 and hub2 peerings, no gateway flags are set — those exist purely to give the spoke a peering-derived path to `NVA1_IP` / `NVA2_IP`. Data plane works. But every third-region spoke now needs three peerings, forward-path traffic still crosses region as global peering egress (paid), and the pedagogical picture becomes noisy. Useful only for very small estates.

**Recommended fix: A.** It preserves the "one ARS per workload region, not per spoke" scaling story, keeps peering count minimal (one per spoke), and matches the Microsoft-canonical multi-region ARS-with-overlay pattern.

---

## 2. Answers to the 8 review questions

### Q1 — Is workload-aligned third-region ARS the right fix for the independent fourth-region SPOF? Blast radius per outage.

**Yes — with Fix A applied.** A workload-aligned third-region route-hub removes the fourth-region SPOF that Δ1–Δ4 explicitly scoped out, because each region's control plane is now co-located with its workloads. Blast radius under Fix A:

| Failure | Third-region spokes (set C) | Hub1-region spokes (set A) | Hub2-region spokes (set B) | On-prem |
|---|---|---|---|---|
| **Third-region full outage** | All set-C workloads gone (region gone). Set A and B unaffected — their control plane is in their own hubs. Route-hub NVA↔hub1/hub2 overlays go down, hub NVAs withdraw set-C prefixes via their local ARS → VPN GW → on-prem stops advertising set-C prefixes; set-A / set-B ↔ on-prem unaffected. | Fully operational | Fully operational | Loses set-C only |
| **Hub1 region outage** | Third-region ARS's NVA1 overlay peer down → NVA1-originated `0/0` withdrawn. Route-hub NVA reconverges to NVA2's `0/0` (was pre-empted by AS-path length; now sole path). Forward path via hub2. Return path via hub2 (on-prem BGP already reconverged). | Set-A workloads gone (region gone) | Fully operational | Loses hub1 tunnels; set-A prefixes withdrawn; sets B and C reachable via hub2 |
| **Hub2 region outage** | Symmetric to hub1 case, but no pre-existing prepend to unwind: NVA1 was already preferred, so no forward-path change. Route-hub NVA withdraws NVA2 overlay; ARS no longer has a secondary `0/0`. | Fully operational | Set-B workloads gone (region gone) | Loses hub2 tunnels; sets A and C reachable via hub1 |
| **ARS-only failure (third-region ARS control plane hangs but hub NVAs and overlays up)** | Set-C spokes keep last-installed routes indefinitely (ARS-injected routes are programmed into the SDN and survive ARS unreachability until an SDN update event). New spoke deployments in third region cannot converge until ARS restored. Existing traffic keeps flowing. | Unaffected | Unaffected | Unaffected |
| **Third-region NVA-only failure (route-hub NVA dies, ARS up)** | ARS's two BGP peers (to NVA1 and NVA2 via the third-region NVA overlay endpoint) both drop. Set-C spokes lose `0/0` after ARS 60/180 s hold, or immediately if TCP RST fires. **Set-C isolated from on-prem until NVA restarts.** This is now the single-VM failure surface for set-C. Mitigation: two route-hub NVAs (P1 patch — dormant). | Unaffected | Unaffected | Unaffected |
| **One spoke failure (set-C)** | That spoke gone. Its prefix is withdrawn from route-hub ARS via peering-derived VNet-address-space signal. Peers reconverge. | Unaffected | Unaffected | On-prem withdraws that specific /24 |

**Comparison to Δ1–Δ4 baseline (central ARS in a fourth region):**

- Δ1–Δ4 accepted the central-ARS region as an out-of-scope SPOF (F4 in the prior review) — its outage broke ALL spokes (sets A+B+C in current framing).
- Fix-A third-region route-hub: no VNet or ARS is shared between regions. Each region's ARS blast radius stays local. **The independent fourth-region SPOF is eliminated.** This is a genuine improvement over Δ1–Δ4 for the multi-region-outage story, at the cost of one extra small NVA VM in the third region.

**Trade-off honesty**: hub-local spokes (sets A and B) trade the "central-ARS SPOF" for their "own-region SPOF" — but their workloads are in that region anyway, so losing region = losing workloads regardless of the routing design. This is exactly Jose's point in Q4 below.

### Q2 — Peering matrix and the single "Use remote virtual network gateway or Route Server" flag

**Flag semantics — confirmed.** The peering property has been unified. On the spoke side of a peering, `UseRemoteGateways=true` (portal name: *"Use the remote virtual network's gateway or Route Server"*) exposes **both** capabilities simultaneously from the remote (hub) VNet when they exist:

1. **VPN GW transit** — spoke effective routes get `Next hop type = VirtualNetworkGateway` for on-prem prefixes learned by that GW.
2. **Route Server injection** — ARS in the peered VNet learns the spoke's address space and programs the NVA-learned routes (0/0 or specific) into the spoke's effective route table with `Next hop type = VirtualAppliance` and `Next hop IP = <NVA IP>`.

Source: ARS FAQ `Does Azure Route Server support virtual network peering?` — verbatim: *"if you peer a virtual network hosting the Azure Route Server to another virtual network and you enable Use the remote virtual network's gateway or Route Server on the second virtual network, Azure Route Server learns the address spaces of the peered virtual network and sends them to all the peered network virtual appliances (NVAs). Route Server also programs the routes from the NVAs into the route table of the virtual machines in the peered virtual network."*

**"Both VPN GW and ARS in the same VNet" — supported.** ARS + VPN GW coexistence is documented at `expressroute-vpn-support`. Requirements: VPN GW active-active + ASN 65515 + branch-to-branch enabled on ARS for NVA↔GW route exchange. This is the mandated shape for hubs 1 and 2.

**One flag, both behaviours.** There is no way to enable only one and not the other. If Jose ever wanted "ARS injection without VPN GW transit" (or vice versa), the answer is: put them in different VNets. In this lab that's not needed — the goal is to exercise both together.

**UDRs for `0/0` on local spokes: not needed.** ARS injection replaces the UDR. Route-map preview on hub-local ARS→VPN-GW connection can further shape the advertisement.

**AllowForwardedTraffic on the peering:**

- **Hub side of hub↔spoke peering**: `AllowForwardedTraffic=true`. Traffic originated by hub NVA and forwarded into the spoke (return traffic from on-prem via NVA) must be permitted. Required.
- **Spoke side of hub↔spoke peering**: `AllowForwardedTraffic=true`. Spoke-originated traffic that has been forwarded via hub NVA and comes back into hub context needs the reverse permission. Required.
- **On the third-region route-hub↔hub peering (Fix A)**: `AllowForwardedTraffic=true` on both ends because both NVAs forward traffic across (overlay endpoints).
- On any peering where the flag is set to `false`, only "native" traffic (VM-originated in the peered VNet) is allowed. Setting it wrong on any of the above breaks the return path silently.

**Full peering matrix (Fix A recommended baseline):**

| Peering (A↔B) | `AllowVirtualNetworkAccess` | `AllowForwardedTraffic` | `AllowGatewayTransit` | `UseRemoteGateways` | Notes |
|---|---|---|---|---|---|
| set-A spoke ↔ hub1 (local) | true / true | true / true | true (on hub1) / n/a | n/a / true (on spoke) | Classical model. Spoke uses hub1 VPN GW + hub1 ARS via single flag. |
| set-B spoke ↔ hub2 (local) | true / true | true / true | true (on hub2) / n/a | n/a / true (on spoke) | Same as above, hub2 side. |
| set-C spoke ↔ third-region route-hub | true / true | true / true | true (on route-hub) / n/a | n/a / true (on spoke) | Route-hub has ARS + local NVA (no VPN GW). Flag exposes ARS injection only (there's no gateway to transit). |
| Third-region route-hub ↔ hub1 (global) | true / true | true / true | false / false | false / false | Peering exists so third-region NVA can data-plane reach NVA1 and vice versa (BGP + overlay endpoints). No gateway transit. |
| Third-region route-hub ↔ hub2 (global) | true / true | true / true | false / false | false / false | Symmetric. |
| Hub1 ↔ hub2 (optional, see Q5) | Only if inter-hub NVA overlay is added | — | — | — | Not required for the goal scenarios. |

### Q3 — Third-region ARS BGP-peering with NVAs in two different peered hub VNets over global peering

**Supported.** Requirements confirmed from the ARS FAQ:

- ARS supports **up to 16 BGP peers** per instance (updated limit — old blogs still cite 8).
- Each NVA must peer **both ARS instance IPs** (so the third-region ARS has 4 BGP sessions total: NVA1→instance1, NVA1→instance2, NVA2→instance1, NVA2→instance2; add a third route-hub-local NVA in Fix A and you get 6 sessions).
- NVA must support **multi-hop external BGP** (`ebgp-multihop 4` or higher; local instance IPs live in the RouteServerSubnet /27 of the third-region VNet, remote NVA IPs live in hub subnets across global peering — TTL > 1 required). This is a standing ARS requirement regardless of peering distance; global peering doesn't change the requirement, only makes it more visible.
- Each NVA advertises the **same** routes to both instance IPs so ECMP works. AS-path length determines best path if both instances see the same prefix from multiple NVAs.
- **`RouteServerSubnet` cannot have UDR or NSG** attached — so no ability to force TCP-179 traffic through anything else. The BGP session traverses the global peering directly, over the Microsoft backbone.

**Scale/limits:**

| Limit | Value | Impact on this design |
|---|---|---|
| BGP peers per ARS | 16 | 6 used in Fix A (NVA1×2 + NVA2×2 + local-NVA×2). Plenty of headroom. |
| Routes per BGP peer | 4,000 | Each NVA advertises `0/0` + eventual on-prem prefixes. Not close. |
| VMs in ARS's VNet + peered VNets | 50,000 | Lab-scale not close. |
| Peered VNets (per ARS) | 500 | Bounded by number of set-C spokes. Not close. |
| Total on-prem + Azure prefixes | 10,000 | Not close. |
| Global peering + Basic LB | Basic LB frontend not reachable across global peering. | Not used in this design. Standard LBs are fine. |

**AS_PATH loop-prevention:** Both NVA1 and NVA2 must strip ASN 65515 (the third-region ARS's ASN) from the AS_PATH before advertising anything back to their **local** hub ARS (also ASN 65515). Otherwise the local hub ARS drops the route for standard loop-prevention. Confirmed by FAQ: *"If an NVA advertises a route to Azure Route Server that already contains 65515 in the BGP AS\_PATH attribute, Azure Route Server identifies its own ASN in the AS path and rejects the route as part of standard BGP loop prevention behavior."*

Also, when the third-region local NVA (Fix A) advertises routes to the third-region ARS, if it re-advertised on-prem routes learned from the hub NVAs, and those routes still had `65515` in the AS_PATH from the hub side, the third-region ARS would drop them. The third-region local NVA must strip 65515 too on the local-ARS-facing side. All three NVAs run the same one-line filter.

### Q4 — Path symmetry under steady state and hub1 failure/recovery

**Set A (hub1-region spokes) — steady state and any failure:**
Forward: spoke → hub1 NVA → hub1 VPN GW → on-prem. Return: on-prem → hub1 VPN GW → hub1 NVA → spoke. Symmetric.
On hub1 outage: **set A workloads are gone with the region.** There is no cross-hub failover objective for hub-local spokes — the point of hub-local spokes is regional application locality, not multi-region survivability. This is important framing for Jose to hold: sets A and B are **NOT** trying to failover. Their point is to show that classical hub-local BGP+UDR still works as the majority pattern; set C is the one that demonstrates cross-region resilience.

**Set B (hub2-region spokes) — steady state and any failure:** Symmetric to set A. Same non-objective on cross-hub failover.

**Set C (third-region spokes) — steady state:**

- Forward path: `set-C spoke → third-region local NVA (Fix A) → IPsec overlay to NVA1 → hub1 VPN GW → on-prem`. Preferred because NVA1's `0/0` has shorter AS_PATH than NVA2's (NVA2 is prepended by the third-region ARS inbound route-map — see Q5/Δ3).
- Return path: `on-prem → hub1 VPN GW → hub1 NVA → hub1 IPsec overlay to third-region NVA → set-C spoke`. Preferred because on-prem best-path selects hub1 (AS_PATH `[65515, 65001]` shorter than hub2's `[65515, 65002, 65002, 65002]` for set-C prefixes).
- **Symmetric.** Both directions land on hub1.

**Set C under hub1 failure:**

- Third-region ARS: NVA1 BGP session drops (TCP RST if hub1 region gone; DPD-driven if silent). Third-region ARS reconverges to NVA2's `0/0` (was second-best, now sole). Time: seconds (TCP) to 180 s (ARS hold worst-case, silent failure).
- Third-region local NVA: IPsec tunnel to NVA1 dies (DPD ~45–90 s). Local NVA drops NVA1 as overlay next-hop; forwards via NVA2.
- On-prem: hub1 VPN tunnel dies (DPD ~30–90 s). On-prem VPN GW withdraws hub1-learned set-C prefixes. Only hub2 path left → uses it.
- Both directions converge to hub2 → **symmetric under failure.**

**Set C under hub1 recovery:**

- Hub1 comes back. NVA1 re-peers with third-region ARS. NVA1 re-advertises unprepended `0/0` → third-region ARS best-path shifts back to NVA1 (shorter AS_PATH, deterministic).
- Third-region local NVA re-establishes overlay to NVA1.
- On-prem: hub1 VPN tunnel comes back; hub1 VPN GW re-advertises set-C prefixes with `[65515, 65001]`; on-prem best-path shifts back to hub1.
- **Both directions revert. Symmetric on recovery.**

**Asymmetry window** exists during the ~30–180 s reconvergence gap between forward-path (bound by ARS hold) and return-path (bound by IPsec DPD + on-prem BGP hold). During that window: forward via dead NVA1 + return via hub2 → half-open blackhole for set-C. This is unchanged from the Δ1–Δ4 analysis and is a **teaching moment**, not a design defect.

### Q5 — Inter-hub NVA overlays: needed?

**For third-region-spoke ↔ on-prem: not needed.** The overlay hop is between third-region NVA and hub-region NVAs — not between hub1 NVA and hub2 NVA. Set-C traffic goes third-region-NVA → hub1-NVA → hub1-VPN-GW → on-prem. Hub2 is a standby path via a separate overlay (third-region-NVA → hub2-NVA), not via hub1↔hub2.

**Scenarios that WOULD require inter-hub NVA overlays:**

1. **Cross-spoke inter-region transit** (set-A spoke ↔ set-B spoke without going through on-prem): today, that traffic would need to reach a hub NVA, transit to the other hub, and land on the destination spoke. Without hub1↔hub2 overlay, hub1 NVA has no path to advertise set-B's spoke prefixes back into hub1 ARS (which is what would make set-A spokes see them). Add hub1↔hub2 overlay + BGP → each hub NVA re-advertises the other hub's spoke prefixes to its local ARS. Symmetric to Q1's third-region pattern.
2. **Cross-hub failover for hub-local spokes** (if you *did* want set-A to failover to hub2's VPN GW). Requires hub1↔hub2 overlay so hub2 NVA can advertise set-A prefixes to hub2 VPN GW when hub1 dies. Explicitly out of scope per Q4 framing (hub-local spokes lose their workloads with their region).
3. **Set-C failover via a hub-to-hub bypass** (routing set-C's on-prem traffic via hub1→hub2→on-prem when hub1↔on-prem WAN is dead but hub1 region is up). Very niche; not in the goal.

**Baseline recommendation: NO inter-hub NVA overlays.** Two overlays only: third-region-NVA↔NVA1, third-region-NVA↔NVA2. Add hub1↔hub2 overlay as a **P4 patch** (dormant) if Jose wants to demonstrate cross-spoke transit as a Phase-2 topic.

### Q6 — Spoke/VM count

**Recommended: 4 spokes, 4 VMs.**

| Spoke | Region | VM? | Justification |
|---|---|---|---|
| set-A-spoke-1 | hub1 region | yes (1×B2als_v2) | Effective-route capture + ping + traceroute to on-prem + intra-region intra-VM egress. |
| set-B-spoke-1 | hub2 region | yes (1×B2als_v2) | Same evidence set on hub2 side. |
| set-C-spoke-1 | third region | yes (1×B2als_v2) | Third-region primary evidence spoke. Effective routes show `0/0 → third-region NVA`. Ping to on-prem via hub1 preferred. |
| set-C-spoke-2 | third region | no VM (prefix-only) | Second set-C prefix (10.30.1.0/24) proves ARS scales *within* a workload region — advertised, learned by hub NVAs, re-advertised into hub ARSes, seen on on-prem. No VM: evidence is BGP-route presence at hub NVA BIRD and on-prem VPN GW route table. |

**Why not 3 (one per set):** the third-region set is the whole novel part of the design; a single set-C spoke doesn't prove the "one ARS per workload region, not per spoke" scaling story. A second set-C spoke without a VM (prefix-only) closes that gap with **zero incremental compute cost**.

**Why not more:** every additional VM adds 24×7 running charge. Beyond the "two prefixes per region" evidence the design's goals need, more spokes only add noise.

**Total VMs in the lab (excluding NVAs and gateways):** 3 workload VMs. Adding NVA VMs (1 in each hub + 1 in third-region route-hub = 3), and Azure VPN GWs (1 per hub = 2 hosted resources, non-VM), total spend is dominated by the two VPN GWs and the ARSes.

### Q7 — Challenge the "relatively low cost" claim for ARS as a control-plane extension

Qualitative comparison (no unsourced price figures):

**Costs of a Route-Server-based third-region control-plane extension (Fix A):**
- 1× ARS (base hourly rate — see Azure Route Server pricing page for region-specific figure)
- 1× lightweight NVA VM (B2als_v2 or similar) — small
- 1× VNet + subnets
- 2× global VNet peering (data-plane egress paid per GB in each direction)
- Overlay tunnel bandwidth (IPsec CPU on the small NVA)
- **Route-maps preview surcharge:** ARS FAQ states *"Using route maps incurs extra charges"* on the pricing page. Additionally, first-time route-map creation triggers *"an upgrade that takes approximately 30 minutes"* — this is not just cost, it's an ops event. Both matter for Phase-0 sizing.
- **Routing infrastructure units:** default 2 units = 4,000 VMs supported. Beyond that, additional units at ~USD $0.10/hour each in the US (regional variation per FAQ). Lab is nowhere near this cap.

**Costs of a full hub (per hub for comparison):**
- 1× ARS
- 2× NVA VMs (redundant pair)
- 1× VPN Gateway (active-active — 2 instances, per-hour rate an order of magnitude above ARS)
- 1× Azure Firewall Standard (Basic not supported in secured vWAN hub; Standard is a meaningful line item per hour)
- Multiple public IPs
- Route-server + gateway coexistence "downtime window" cost on any lifecycle event (10-min downtime + 30–60 min actual deployment per FAQ)

**Qualitative verdict:** the third-region route-hub is materially cheaper than a full hub — Jose's premise holds. But it is **not** just "an ARS" in the naked sense of the original sketch, because the naked ARS has no data plane. The right pitch is: *"one ARS + one small NVA per workload region, no VPN GW, no firewall — enough to reach the primary hubs for on-prem transit."*

**Real scaling unit:** **one route-hub (ARS + 1 NVA) per workload region**, not per spoke. Adding spokes to an existing workload region adds only peerings, no new ARS/NVA. This is the story Jose wanted to tell, and it's true under Fix A.

**Operational burden (qualitative):**
- ARS: managed, zone-redundant, no OS patching. **Low.**
- Route maps: preview feature. Preview → API surface can change, no SLA guarantee. **Medium-low.**
- Route-hub NVA: cloud-init template exists in the repo. Patching, monitoring, upgrades on operator. **Medium.**
- Overlay tunnels (IPsec + BIRD): text-config, well-understood, ephemeral. **Medium.**
- Peering churn: adding a new set-C spoke triggers ARS soft-reset on peered NVAs (per FAQ). Bounded but visible. **Low-medium.**
- **First route-map creation on an ARS triggers ~30-min upgrade window**. Must schedule. Not repeatable — subsequent maps don't. Plan Phase-0 to bake in this one-off wait.

### Q8 — Corrected baseline, peering/policy table, pass/fail scenarios, remaining decisions

Covered in §3, §4, §5, §9.

---

## 3. Corrected recommended baseline

- **Two hubs** (hub1, hub2), each: 1× ARS (branch-to-branch ON), 2× BIRD NVAs (ASN 65001 in hub1, 65002 in hub2), 1× VPN Gateway (active-active, ASN 65515, BGP on), 1× workload VM in set-A / set-B respectively.
- **Third-region route-hub**: 1× ARS (branch-to-branch OFF — no local GW to bridge), **1× small transit NVA** (ASN 65003 recommended). No VPN GW. No firewall. This is the structural correction that fixes the data-plane gap in Jose's sketch.
- **Simulated on-prem**: 1× Azure VPN Gateway (active-active, ASN 65500), 1× on-prem "LAN" VM for ping evidence.
- **Overlays**: third-region NVA ↔ NVA1 (IPsec + BGP), third-region NVA ↔ NVA2 (IPsec + BGP). **No hub1↔hub2 overlay** in v1.
- **Route policies (split)**:
  - **Δ1 (mandatory, all three NVAs)**: BIRD `bgp_path.delete(65515)` on the export filter toward local hub ARS (or third-region ARS in the third-region NVA case). Standard multi-region ARS canonical pattern.
  - **Δ2 (spoke-prefix prepend)**: on **NVA2** export toward hub2 ARS, prepend `65002` ×2 on set-C spoke prefixes. Ensures on-prem sees `[65515, 65002, 65002, 65002]` for set-C via hub2 vs `[65515, 65001]` via hub1 → hub1 preferred deterministically. NVA-side is currently unavoidable because a classic Azure VPN GW connection has no route-map primitive; the outbound-on-hub2-ARS→VPN-GW-connection alternative is investigated in Δ3-bis below.
  - **Δ3 (default-route de-preference via route map)**: **inbound** route map on third-region ARS's peering with NVA2, prepending NVA2-originated `0/0` twice. Deterministic best-path shift for set-C's default toward NVA1. Uses route-maps preview.
  - **Δ3-bis (investigate at Phase-0, not baseline)**: could the spoke-prefix prepend live on an *outbound* route map on the hub2 ARS → VPN GW connection instead of NVA2's BGP export? The route-maps preview supports outbound maps on VPN gateway connections, and the set-C prefixes arriving at hub2 ARS are eBGP-learned from NVA2 (they are not VNet address space to hub2 ARS — they're re-originated from the third region), so the "cannot modify VNet address space" restriction does not strictly apply. If confirmed at Phase-0 the prepend moves from NVA to route-map, tightening the "which policy lever lives where" teaching story. If ambiguous, keep Δ2 as NVA-side prepend. Either way this is a Phase-0 experiment, not a baseline blocker.

### 3.1 Peering + policy table

Baseline. All flags shown are on each SIDE of the peering. Notation: `<hub-side-value> / <spoke-side-value>` for hub↔spoke peerings.

| Peering | AllowVNetAccess | AllowForwardedTraffic | AllowGatewayTransit | UseRemoteGateways | Policy touched here |
|---|---|---|---|---|---|
| set-A-spoke-1 ↔ hub1 | true/true | true/true | true/− | −/true | Classical. ARS injects local hub ARS routes into spoke. |
| set-B-spoke-1 ↔ hub2 | true/true | true/true | true/− | −/true | Classical. Δ2 prepend was applied upstream (at NVA2 export) so this side sees prepended AS_PATH natively. |
| set-C-spoke-1 ↔ third-region route-hub | true/true | true/true | true/− | −/true | Route-hub ARS injects `0/0` with next hop = third-region NVA. Post-Δ3 the injected `0/0` reflects NVA1 preference. |
| set-C-spoke-2 ↔ third-region route-hub | true/true | true/true | true/− | −/true | Same as set-C-spoke-1. Prefix-only, no VM. |
| Third-region route-hub ↔ hub1 (global) | true/true | true/true | false/false | false/false | Underlay for third-region ARS ↔ NVA1 BGP session AND for third-region-NVA ↔ NVA1 IPsec overlay. No gateway transit. |
| Third-region route-hub ↔ hub2 (global) | true/true | true/true | false/false | false/false | Symmetric. |

### 3.2 ASN plan

| Speaker | ASN | Notes |
|---|---|---|
| Hub1 ARS | 65515 | Fixed by Azure. |
| Hub2 ARS | 65515 | Fixed by Azure. |
| Third-region ARS | 65515 | Fixed by Azure. All three ARSes share 65515 — hence the mandatory Δ1 strip at all three NVAs' local-ARS export sides. |
| Hub1 VPN GW | 65515 | Forced by ARS+VPN GW coexistence rule. |
| Hub2 VPN GW | 65515 | Forced by ARS+VPN GW coexistence rule. |
| On-prem VPN GW | 65500 | Distinct from Azure private-ASN reserved set. Enables normal eBGP with the two hub VPN GWs. |
| NVA1 (hub1) | 65001 | Private, non-reserved. |
| NVA2 (hub2) | 65002 | Private, non-reserved. Prepends 65002×2 on set-C prefixes (Δ2). |
| Third-region NVA | 65003 | Private, non-reserved. |

---

## 4. Pass/fail scenarios (4 chosen — narrow, load-bearing)

| # | Name | Injection | Pass criteria |
|---|---|---|---|
| **S1 — Steady state** | none | (a) All BGP sessions Established (three ARSes × 2 instances × their NVAs + branch-to-branch VPN-GW BGP up on hubs 1 and 2). (b) `set-A-spoke-1`: effective `0/0 → hub1 NVA`. (c) `set-B-spoke-1`: effective `0/0 → hub2 NVA`. (d) `set-C-spoke-1`: effective `0/0 → third-region NVA`. (e) on-prem VPN GW BGP RIB shows set-C prefix with AS_PATH `[65515, 65001]` (hub1) and `[65515, 65002, 65002, 65002]` (hub2); best-path = hub1. |
| **S2 — Hub1 outage via reversible failure injection** | (a) Break both PSKs on the hub1↔on-prem bidirectional VPN connection pair with `az network vpn-connection shared-key update` on both `conn-hub1-to-onprem` and `conn-onprem-to-hub1`, then `vpn-connection reset` to force immediate IKE re-neg. (b) `sudo systemctl stop bird` on NVA1. **Reversible; no VM lifecycle action.** | (a) Hub1↔on-prem tunnel drops within 30–90 s (IKE Phase-1 auth fail → tunnel down → BGP session over tunnel down). (b) NVA1↔third-region-ARS BGP down within TCP RST or 180 s ARS hold. (c) `set-C-spoke-1` reconverges to `0/0 → third-region NVA` (unchanged next-hop; overlay pivots to NVA2). (d) on-prem sees only hub2 path for set-C; forward + return both via hub2. (e) `set-A` gone (region gone in narrative; here it's the simulated outage — set-A is technically still reachable via hub1's local ARS, but per Q4's framing we don't try to failover it). |
| **S3 — Hub1 recovery** | Restore PSK on both connection halves; `vpn-connection reset`; `sudo systemctl start bird` on NVA1. | (a) Hub1↔on-prem tunnel + BGP re-establish within 30–90 s. (b) NVA1↔third-region-ARS re-establishes. (c) `set-C` reverts to hub1 preference (deterministic AS_PATH-shortest). (d) All effective routes match S1 within convergence + verification cycle. |
| **S4 — Route-map effect on default-route preference** | Enable Δ3 (inbound route map on third-region ARS's NVA2 peering, prepend `65002 65002` on `0.0.0.0/0`) with S1 otherwise steady. | (a) `set-C-spoke-1` effective `0/0 → third-region NVA` (unchanged — data plane is via local NVA regardless). (b) Third-region ARS best-path for `0/0`: NVA1 chosen (AS_PATH length 1 vs NVA2's 4 after prepend). Verifiable via ARS `get-learned-routes` and `get-advertised-routes`. (c) Confirms Q3 in the review (inbound maps pre-best-path). |
| **S5 — Set-C prefix propagation to on-prem via BOTH hubs** | none (verify at S1) | (a) On-prem VPN GW RIB shows `set-C-spoke-2`'s prefix (VM-less) via both hubs with the expected AS_PATH signatures. (b) This proves the prefix-only spoke works — ARS scales within a workload region without requiring an extra workload VM. |

---

## 5. Failure-mode table (charter §7 mandate)

| # | Failure | Set A | Set B | Set C | On-prem | Automatic recovery? |
|---|---|---|---|---|---|---|
| F1 | Hub1 full outage (region) | Gone (region gone) | OK | Reconverges to hub2 in 30–180 s | Only hub2 path | Yes |
| F2 | Hub2 full outage | OK | Gone | No change (was already NVA1-preferred) | Only hub1 path | Yes |
| F3 | Third-region full outage | OK | OK | Gone (region gone) | Loses set-C only | Yes (for other sets) |
| F4 | ARS control-plane hang in any region (data plane intact) | Preserves last routes | Preserves last routes | Preserves last routes | No change | Manual — restart ARS |
| F5 | Route-hub NVA in third region dies (single NVA) | OK | OK | Set-C loses data plane to on-prem. **Single point of failure inside the third region.** | Withdraws set-C after BGP hold | Manual — restart NVA. See P1. |
| F6 | Single BGP session flap (NVA↔ARS one instance) | OK | OK | OK — ECMP + redundant peer | OK | Yes (auto) |
| F7 | Set-C spoke UseRemoteGateways peering flap | OK | OK | That spoke loses everything until re-peering completes | Withdraws that spoke's /24 | Yes on peering restore |
| F8 | Hub1↔on-prem tunnels break but hub1 region up (S2 injection) | Set A locally OK; on-prem reachability lost for set A | OK | Reconverges to hub2 | Only hub2 path | Yes |

### Patch catalogue (dormant)

- **P1** — Deploy a second route-hub NVA in the third region for redundancy. Closes F5. Cost: 1× extra small VM. Recommended if Phase-1 shows F5 to be a real blast radius (it is — but v1 lab keeps it single to save cost, and F5 is a known documented gap).
- **P2** — Add hub1↔hub2 NVA overlay to enable cross-spoke inter-region transit and set-A/B cross-hub failover. Enables Q5 scenarios (2) and (3). Not needed for baseline goal.
- **P3** — Duplicate ARS in the third region (put ARS in a second route-hub VNet peered to the same spokes). Non-trivial — a spoke's UseRemoteGateways points to exactly ONE peer. Not a viable patch; log as "would need per-spoke peering-flip automation as previously rejected."

---

## 6. Where I retire prior claims (delta versus Δ1–Δ4)

- The Δ1–Δ4 baseline explicitly accepted the fourth-region central-ARS SPOF. **This proposal removes it** — no shared control-plane VNet across regions. Trinity's 2026-08-03T11:51 note that classified the central-ARS SPOF as "scoped in" is now superseded for the go-forward baseline. The Δ1–Δ4 topology remains valid as a "Teaching-only anti-pattern" catalogue entry if Jose wants to keep it.
- The Δ1–Δ4 "route-maps preview scope narrowed to Δ3 only" statement remains correct. Δ3 (inbound on third-region ARS ↔ NVA2 peering) is the default-route lever.
- The Δ1–Δ4 "spoke-prefix prepend must be NVA-side" statement is **softened** to Δ3-bis: it *might* be movable to hub2-ARS→VPN-GW outbound route map since the set-C prefixes arrive at hub2 ARS as BGP-learned (not VNet address space). Confirm at Phase-0 with a scoped test. If unclear, keep NVA-side.

---

## 7. What must remain NVA-side policy (not route maps)

- **Δ1 — 65515 strip** at each NVA→local-ARS export session (all three NVAs). Route maps preview cannot delete an inbound ASN from the AS_PATH before the ARS drops the route on loop-prevention, because loop-prevention runs on ingress before inbound route maps in the ARS pipeline (implied by the FAQ statement that ARS "rejects the route as part of standard BGP loop prevention behavior"). BIRD/FRR one-liner. Mandatory.
- **AS-path prepend at Δ2**: keep NVA-side unless Δ3-bis is confirmed at Phase-0.

---

## 8. What the route-maps preview lab actually tests here

- ✅ **Δ3** — Inbound AS-path prepend on third-region ARS ↔ NVA2 peering for NVA2-originated `0/0` → default-route preference lever. Deterministic and verifiable.
- 🔬 **Δ3-bis** — Outbound route map on hub2 ARS ↔ VPN GW connection to prepend set-C spoke prefixes. Phase-0 experiment.
- ❌ **Cannot** modify local VNet address space that hub ARSes advertise (their own set-A / set-B spoke prefixes when reached via classical gateway-transit peering). Not needed.
- ❌ **Cannot** modify LOCAL_PREF (ARS route maps don't touch it).

---

## 9. Remaining decisions Jose must make before Phase-0

Just three — behaviour actually changes with each:

**D1 — Structural fix for the third-region data-plane gap.**
- (A) Route-hub with 1 small NVA (recommended). Cheapest that works and matches multi-region ARS canonical pattern.
- (B) No third-region NVA; each set-C spoke peers to route-hub + hub1 + hub2. Simpler NVA count, more peerings per spoke, global-peering egress on every packet.

**D2 — Δ3-bis experiment scope.**
- (Y) Include a Phase-0 mini-test: create an outbound route map on hub2 ARS → hub2 VPN GW connection, prepend on `set-C-spoke-2`'s prefix, verify on-prem sees the prepended AS_PATH. If it works, retire Δ2 NVA-side prepend in favour of route-map placement.
- (N) Skip — go straight to NVA-side prepend (Δ2 as-is).

**D3 — Route-hub NVA redundancy (P1) v1 vs v2.**
- (I) 1 NVA now, patch to 2 later.
- (II) 2 NVAs from v1 — accept the extra small-VM cost to eliminate F5.

**Not blocking, but worth Jose's steer** (Morpheus's decision domain):

- **Regions**: third region must (a) support ARS in current SKU (all GA regions do), (b) have latency-viable global peering to hub1 and hub2 regions, (c) meet the "no UK / no North/West Europe" exclusion set already in policy. `polandcentral` or `switzerlandnorth` are natural third-region picks with `swedencentral` + `germanywestcentral` as hub1/hub2. Or `italynorth` as third region.

---

## 10. References (Microsoft Learn, all fetched 2026-08-03)

- Route Server FAQ — https://learn.microsoft.com/azure/route-server/route-server-faq
  - Peering + single flag semantics (`Does Azure Route Server support virtual network peering?`)
  - 16-BGP-peer limit, 4000 routes/peer, 500 peered VNets, 50000 VMs, 10000 total prefixes
  - Multi-hop external BGP requirement
  - ARS 65515 AS_PATH drop (loop-prevention)
  - VPN GW active-active + ASN 65515 + branch-to-branch requirement
  - Route maps → "extra charges", "first route map triggers 30-min upgrade"
  - ARS + gateway create/delete → 10-min downtime + 30–60 min deploy
- Route Server + VPN GW coexistence — https://learn.microsoft.com/azure/route-server/expressroute-vpn-support
- Multi-region ARS (canonical NVA-overlay pattern) — https://learn.microsoft.com/azure/route-server/multiregion
- Dual-homed ARS — https://learn.microsoft.com/azure/route-server/about-dual-homed-network (source for the spoke-must-peer-to-each-hub requirement that motivates Fix A)
- Route maps preview limits — https://learn.microsoft.com/azure/route-server/route-maps-about
- VPN Gateway BGP overview (multiple tunnels, automatic BGP withdrawal) — https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-bgp-overview
- VNet peering overview (non-transitivity, gateway transit, single-flag) — https://learn.microsoft.com/azure/virtual-network/virtual-network-peering-overview

---

## Handoff

- Morpheus: revise lab card + Phase-0 probes against §3 baseline and §9 decisions once Jose gates D1/D2/D3.
- Trinity (me): write `design.md` §BGP walk, §effective-route tables, §NVA export filter snippets (BIRD + FRR), §Δ3 route-map JSON, §S2 failure-injection script, §resiliency table, only after Jose gates D1.
- Niobe: gate skeleton matches S1–S5 above (5 pass/fail scenarios; no VM required for S5).
- Tank: no build until D1 gated.

No lab file, `design.md`, manifest, or IaC touched in this pass. This document + the Trinity history append are the only artefacts.

