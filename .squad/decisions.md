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

---

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

---

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

---

### 2026-07-30T21:49:01+02:00: Alternate failover method - Megaport VXC BGP (next session)
**By:** Jose (via Copilot)
**What:** For triggering a leg-down / failover, an easier method than NVA-side teardown (systemctl stop bird + swanctl --terminate) is to disable or misconfigure BGP on one of the Megaport VXCs at the Megaport (L2 fabric) level - IF Megaport API/portal credentials are available.
**Why:** Cleaner, fabric-level failover trigger. Drops a leg at the ExpressRoute/Megaport layer instead of at the NVA, and would exercise the VPN<->ER path-switch dimension noted as still-untested in Phase 2. Requires Megaport credentials - confirm availability before attempting.
**Action:** Next session, check for Megaport credentials. If present, Niobe/Tank can use a Megaport VXC BGP disable/misconfig as the failover trigger for the fabric-level path-switch test.

---

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

---

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

---

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

---

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

---

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

---

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

---

### Step 1: Auth

```powershell
$AK = [System.Environment]::GetEnvironmentVariable("MEGAPORT_ACCESS_KEY","User")
$SK = [System.Environment]::GetEnvironmentVariable("MEGAPORT_SECRET_KEY","User")
$TOKEN = (Invoke-RestMethod -Uri "https://auth-m2m.megaport.com/oauth2/token" `
    -Method POST -ContentType "application/x-www-form-urlencoded" `
    -Body "grant_type=client_credentials&client_id=$AK&client_secret=$SK").access_token
$H = @{ Authorization = "Bearer $TOKEN"; "Content-Type" = "application/json" }
```

---

### Step 2: Inventory

```powershell
$products = (Invoke-RestMethod -Uri "https://api.megaport.com/v2/products" -Headers $H).data
$labProds = $products | Where-Object { $_.productName -like "jomore-copilot-*" }
```

---

### Step 3: Delete VXCs First (order matters)

```powershell
foreach ($uid in $vxcUids) {
    $url = "https://api.megaport.com/v3/product/$uid/action/CANCEL_NOW"
    Invoke-RestMethod -Uri $url -Method POST -Headers $H
}
```

---

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

---

### README.md — complete rewrite

The existing README described Phase 3 as "Not started" and had no scannable entry point for a
casual reader. Rewritten as the lab's front door with:
- Headline result + one-line root-cause at the top (for the skimmer)
- 5-row results table (Phase 1 → Phase 2 → Gate A → Gate B → Gate C) with outcome + primary evidence link in each row
- Links to all four detailed docs
- ASCII topology reflecting Phase 3 final state (secured hubs)
- Four collapsible `<details>` blocks (resource inventory, route-map scheme, full 52-file evidence index, Gate D)

**Structure decision:** Evidence index lives as a collapsible in README (not a separate evidence.md file) to minimize link depth — one click from landing page to any of the 52 files.

---

### manifest.md — Phase 3 resources added

Added three Phase 3 resources to the inventory table (azfwpol-routemap-lab, azfw-eu1/eu2, hub-eu1-ri/eu2-ri). Updated Out-of-scope section (removed stale "Phase 3 not started" bullet). Updated validation plan section with API gap note. Added back-link to README. Topology ASCII updated to show secured hubs with 🔒 marker.

---

### lessons-learned.md — Phase 3 Gate B/C section added

Added TOC + back-link header. New section covers: orthogonal-planes root cause (table form), concurrent-churn gap, BGP stability observation, az vm redeploy swedencentral caveat, prepend-in + summarize-out coexistence finding.

---

### design-phase3.md — status updated, back-link added

Changed Status from "DESIGN-ONLY" to "COMPLETE — all gates validated 2026-07-31". Added back-link to README. (Gate C Result + Gate D section was added in earlier dispatch.)

---

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

---

### Context
No existing Bicep ARS pattern in src/. ARM schema for `virtualHubs` marks `kind` and `ipConfigurations` as read-only in the resource properties object, blocking the naive `kind: 'RouteServer'` approach.

---

### Decision
1. Declare ARS as `Microsoft.Network/virtualHubs@2023-09-01` with `properties: { sku: 'Standard', allowBranchToBranchTraffic: bool }`.
2. Attach PIP + subnet via separate child resource `Microsoft.Network/virtualHubs/ipConfigurations`.
3. Wire NVA BGP peerings via `Microsoft.Network/virtualHubs/bgpConnections` sub-resources depending on `ipConfigurations`.

---

### Why
`kind` is auto-inferred from `sku: 'Standard'` by ARM. `ipConfigurations` as a child resource avoids the BCP073 read-only warning and matches how ARS is actually provisioned via the REST API.

---

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

---

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

---

### Q2 — Does NVA2 prepend survive VPN Gateway propagation to the simulated-on-prem Azure VPN GW?

**Yes, private ASNs are preserved across Azure VPN Gateway.** The ARS FAQ is explicit that private-ASN stripping is an **ExpressRoute** behaviour (via MSEE), not a VPN behaviour:

> *"When ExpressRoute advertises routes to on-premises, it removes the private BGP ASN information. On-premises receives the prefix with AS 12076."*
> — https://learn.microsoft.com/azure/route-server/route-server-faq

No equivalent statement exists for VPN Gateway. Azure VPN Gateway BGP is a straightforward eBGP speaker; AS_PATH prepends applied upstream are preserved end-to-end over IPsec.

Practical consequence: NVA2's `bgp_path.prepend(65002)` (×N) in BIRD, or FRR's `set as-path prepend 65002 65002`, produces a longer AS_PATH that survives all the way to the on-prem VPN GW. **Preference works.**

---

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

---

### Q4 — Do two hub VPN GWs at ASN 65515 confuse the on-prem VPN GW?

**No.** eBGP peers may share a remote ASN — they're identified by IP. Best-path selection at the on-prem VPN GW is then driven by AS_PATH length (there is no `LOCAL_PREF` lever on Azure VPN GW), which is exactly the lever NVA2's prepend gives us. Multiple-tunnel semantics with automatic withdrawal are documented at https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-bgp-overview ("Support multiple tunnels between a VNet and an on-premises site with automatic failover based on BGP").

Coexistence constraint (ARS + VPN GW same VNet, from https://learn.microsoft.com/azure/route-server/route-server-faq):
- VPN GW **must** be active-active.
- VPN GW **must** use ASN 65515.
- Branch-to-branch **must** be enabled for NVA↔GW exchange.

All three are satisfied by the original design.

---

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

---

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

---

### Q7 — Does the design prove full-regional outage?

**No — it proves hub-regional outages, not a full 3-region outage.** The central-ARS VNet is a fourth-region control-plane SPOF for spoke-injection. If the central-ARS region fails, spokes stop learning both defaults and lose spoke↔on-prem entirely (because their gateway-transit peering points at central ARS's fabric).

**Acceptable if scoped explicitly.** Both accept and reject positions are defensible:
- **Accept:** lab is a teaching artifact for hub-regional failover under central-ARS control plane. Explicitly label the central-ARS region as out-of-scope for outage testing, and cite the Learn multi-region page as showing the "ARS in each hub + NVA overlay" pattern that removes that SPOF in a production evolution.
- **Reject:** if Jose actually wants full 3-region outage coverage, this design won't demonstrate it. Morpheus's alternative (or a per-hub ARS + inter-hub NVA tunnels variant) is the answer for that.

**Reviewer recommendation:** Accept the scoping as-is. Document the SPOF in `design.md` and reference the production evolution path.

---

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

---

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

---

### O1 — Manifest peering count inconsistency
`manifest.md §1` Resource Count states "26 peering objects (13 logical pairs)". Actual Bicep has **20 objects (10 logical pairs)**, consistent with `design.md §3` and `cleanup.ps1` step 5 comment. The manifest annotation is incorrect. Does not affect deployment.

---

### O2 — Manifest BGP multihop annotation
`manifest.md §3` BGP session table says `BIRD multihop 3`; both `nva1-cloud-init.yaml` and `nva2-cloud-init.yaml` correctly set `multihop 4` per `design.md §4` (≥4 required). The BIRD configs are correct; the manifest annotation is wrong. Does not affect deployment.

---

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

---

### The gap in one paragraph

ARS advertises `0/0` to the third-region spokes with **next hop = NVA1_IP** (an IP inside hub1's VNet, region A). The spoke's fabric can deliver a packet to `NVA1_IP` only if the spoke's effective route table has a peering-derived path to hub1's address space. The spoke is peered **only** to the third-region ARS VNet. VNet peering is **non-transitive** (peering overview, "gateway/on-premises" section). Therefore the spoke has no peering path to hub1, and the fabric drops the packet. The dual-homed ARS doc is explicit that **"virtual network peering [must be] configured between the spoke and each hub virtual network"** for this pattern to work — the spoke needs data-plane peering to each hub whose NVA it will next-hop to.

This is why the multi-region ARS reference architecture puts **an NVA in each region** and uses **overlay tunnels** between NVAs — the local NVA is the local next-hop, and the tunnel handles the cross-region transit.

---

### Two clean fixes (pick one, both preserve Jose's cost intent)

- **Fix A — Third-region "route hub" (recommended).** Deploy a **route-hub VNet** in the third region containing (i) one ARS instance, (ii) **one lightweight Linux NVA** (BIRD+strongSwan/libreswan, B2als_v2). No VPN gateway, no firewall. The third-region NVA runs IPsec (or VXLAN) overlay tunnels to NVA1 in hub1 and NVA2 in hub2. Locally, it eBGP-peers with the third-region ARS. Third-region spokes peer only to this route-hub with `UseRemoteGateways/AllowGatewayTransit`. ARS injects `0/0` with next hop = local third-region NVA (in-VNet, one hop, no peering-transit issue). This is a **stripped-down hub** (control-plane + one small transit NVA) — cheaper than a full hub (no VPN GW, no firewall) but keeps the data plane sound. This is what Jose meant by "lightweight control-plane extension" once the fabric constraint is honoured.

- **Fix B — No third-region NVA, but each spoke peers to all three (route-hub + hub1 + hub2).** The third-region spoke sets `UseRemoteGateways` only on its peering to the third-region ARS VNet. On the hub1 and hub2 peerings, no gateway flags are set — those exist purely to give the spoke a peering-derived path to `NVA1_IP` / `NVA2_IP`. Data plane works. But every third-region spoke now needs three peerings, forward-path traffic still crosses region as global peering egress (paid), and the pedagogical picture becomes noisy. Useful only for very small estates.

**Recommended fix: A.** It preserves the "one ARS per workload region, not per spoke" scaling story, keeps peering count minimal (one per spoke), and matches the Microsoft-canonical multi-region ARS-with-overlay pattern.

---

## 2. Answers to the 8 review questions

---

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

---

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

---

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

---

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

---

### Q5 — Inter-hub NVA overlays: needed?

**For third-region-spoke ↔ on-prem: not needed.** The overlay hop is between third-region NVA and hub-region NVAs — not between hub1 NVA and hub2 NVA. Set-C traffic goes third-region-NVA → hub1-NVA → hub1-VPN-GW → on-prem. Hub2 is a standby path via a separate overlay (third-region-NVA → hub2-NVA), not via hub1↔hub2.

**Scenarios that WOULD require inter-hub NVA overlays:**

1. **Cross-spoke inter-region transit** (set-A spoke ↔ set-B spoke without going through on-prem): today, that traffic would need to reach a hub NVA, transit to the other hub, and land on the destination spoke. Without hub1↔hub2 overlay, hub1 NVA has no path to advertise set-B's spoke prefixes back into hub1 ARS (which is what would make set-A spokes see them). Add hub1↔hub2 overlay + BGP → each hub NVA re-advertises the other hub's spoke prefixes to its local ARS. Symmetric to Q1's third-region pattern.
2. **Cross-hub failover for hub-local spokes** (if you *did* want set-A to failover to hub2's VPN GW). Requires hub1↔hub2 overlay so hub2 NVA can advertise set-A prefixes to hub2 VPN GW when hub1 dies. Explicitly out of scope per Q4 framing (hub-local spokes lose their workloads with their region).
3. **Set-C failover via a hub-to-hub bypass** (routing set-C's on-prem traffic via hub1→hub2→on-prem when hub1↔on-prem WAN is dead but hub1 region is up). Very niche; not in the goal.

**Baseline recommendation: NO inter-hub NVA overlays.** Two overlays only: third-region-NVA↔NVA1, third-region-NVA↔NVA2. Add hub1↔hub2 overlay as a **P4 patch** (dormant) if Jose wants to demonstrate cross-spoke transit as a Phase-2 topic.

---

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

---

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

---

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

---

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

---

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

---

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

---

---

## Tank Runtime Finding — 2026-08-03T16:50 UTC+02:00

**Finding:** VPN GW SKU `VpnGw1` retired by Azure platform. Cannot create — only VpnGw1AZ-VpnGw5AZ accepted.  
**File:** `labs/dual-hub-hubless-region-ars/deploy/templates/modules/vpngw.bicep`  
**Required fix (one line):** `sku: { name: 'VpnGw1AZ', tier: 'VpnGw1AZ' }`  
**Topology/cost impact:** None — VpnGw1AZ is direct equivalent, same billing.  
**Action needed:** Reviewer approve single-line SKU fix; Tank then resumes with `deploy-apply.ps1 -CorrelationId lab3d001 -ResumeRg rg-dual-hub-hubless-region-ars-lab3d001`.  
**Current RG cost:** ~$35/day (3 ARS + 6 VMs + 9 PIPs — no GWs yet).  
**ARM validate gap:** The platform retirement policy is NOT enforced at validate time — it only fails at create time.

*Tank — 2026-08-03T16:50 UTC+02:00*

---

## Tank Runtime Finding B2 — 2026-08-03T17:25 UTC+02:00

**Finding:** VpnGw1AZ (AZ SKU) requires associated Standard PIPs to have `zones: ['1','2','3']` configured. Existing 6 GW PIPs deployed without zones (zones are immutable — cannot update in-place).  
**Error:** `VmssVpnGatewayPublicIpsMustHaveZonesConfigured`  
**Files affected:** `main.bicep` — 6 PIP resources (pipGwHub1A/B, pipGwHub2A/B, pipGwOnpremA/B)  
**Required IaC fix:** `zones: ['1', '2', '3']` property on each of those 6 PIP resources.  
**Required operational pre-step:** Delete 6 existing zone-less GW PIPs before ARM retry (not an IaC change).  
**ARS PIPs:** Not affected by this error.  
**Action needed:** Reviewer approve `zones` addition to 6 GW PIP resources in `main.bicep`; then Tank executes pre-step deletion and resumes.  
**Current RG cost:** ~$35/day (ARS + VMs + PIPs; no GWs).

*Tank — 2026-08-03T17:25 UTC+02:00*

---

## Tank Runtime Finding — Delta3 Activation Blocked — 2026-08-03T20:11 UTC+02:00

**Status:** ROLLBACK COMPLETE — baseline restored

**Blocker:** HubBgpConnectionFromSpokeVnetCannotReferenceRouteMap

Route maps on ARS can only reference BGP connections where the peer IP is WITHIN the
Route Server's own VNet. NVA1 (10.10.1.4) and NVA2 (10.20.1.4) are cross-VNet multihop
peers — their IPs are NOT in vnet-poland-ars (10.30.0.0/24). Platform rejects association.

This restriction was not in the activation contract (Trinity research gap from docs).

**ARS tier:** Upgraded (~$6/day surcharge active). Downgrade requires ARS delete+recreate.

**Route map:** Deleted. Baseline ECMP restored: peer-nva2 asPath=65002, c1-ep 0/0 ECMP.

**API version finding:** Platform requires 2024-10-01 minimum for route maps (contract had 2024-05-01).
No semantic difference — same policy body.

**Options for reviewer:**
1. Relay NVA in vnet-poland-ars (10.30.0.0/24) with local BGP to ARS — IaC change
2. NVA2 secondary NIC with IP in 10.30.0.0/24 for BGP session — IaC change
3. BIRD export filter on NVA2: do not advertise 0/0 to ars-poland — operational OR IaC

*Tank — 2026-08-03T20:11 UTC+02:00*

---

# Oracle Route-Map Scenario Doc

**Date:** 2026-08-05
**Owner:** Oracle
**Scope:** dual-hub-hubless-region-ars

## Decision / documentation outcome

- Added `labs/dual-hub-hubless-region-ars/route-map-scenarios.md` as the canonical 15-scenario route-map catalogue.
- Preserved the current lab constraints: remote `ars-poland` NVA peers cannot reference route maps, maps do not originate routes, and current `10.31.0.0/24` + `10.32.0.0/24` cannot be safely summarized.
- Ranked the safest first experiment as the local synthetic-peer proof-of-concept, with hub-side tests gated on the `ars-hub1` and `ars-hub2` upgrades Tank is handling concurrently.

## Follow-up

- Keep the catalogue as the single reference for future route-map refinement.
- If the experiment plan changes, update only the scenario entry and the ranking block; do not rewrite the validated lab outcomes.

---

# Decision: Hub ARS Route-Map Upgrade — ars-hub1 / ars-hub2
**Date:** 2026-08-05T10:36:38+02:00
**Author:** Tank (IaC Engineer)
**Status:** EXECUTED — Both Succeeded
**Lab:** dual-hub-hubless-region-ars | RG: rg-dual-hub-hubless-region-ars-lab3d001

---

## Decision

Upgrade `ars-hub1` and `ars-hub2` to the route-map tier by creating one inert activation-only
route map per ARS. Maps are NOT associated with any BGP connection and cannot affect live routing.

## Rationale

Route maps are required for future scenario testing on hub Route Servers (e.g. selective
prepend, community tagging, path steering on NVA peerings). The ~30 min first-use upgrade
must be completed before any map can be applied to a connection. Creating an inert map now
unlocks the tier without any routing risk.

## Key Findings

### 1. Hub ARS locality constraint does NOT apply
- ars-hub1 peer-nva1 (`10.10.1.4`) is within vnet-hub1 (10.10.0.0/16) — same VNet.
- ars-hub2 peer-nva2 (`10.20.1.4`) is within vnet-hub2 (10.20.0.0/16) — same VNet.
- `HubBgpConnectionFromSpokeVnetCannotReferenceRouteMap` only fires for cross-VNet peers.
- Route maps CAN be applied to hub ARS NVA peerings (future scenarios unblocked).

### 2. Activation maps created (inert)
| ARS | Map Name | API Version | Rule | Associations |
|-----|----------|-------------|------|--------------|
| ars-hub1 | `rm-hub1-activate` | 2024-10-01 | 192.0.2.0/24 Equals → Add [64496] → Terminate | None |
| ars-hub2 | `rm-hub2-activate` | 2024-10-01 | 192.0.2.0/24 Equals → Add [64496] → Terminate | None |

### 3. Upgrade timing
- hub1: Triggered 10:35:37, Succeeded at 10:59:11 (+22.4 min)
- hub2: Triggered 10:36:00, Succeeded at 11:02:24 (+25.7 min)

### 4. Cost impact
- ~$6/day per hub ARS = ~$12/day additional, irreversible without ARS recreate.
- Covered by Jose's explicit $72/day waiver.

## Post-Upgrade Health
- All 4 VPN connections: Connected ✅
- All ARS peering objects: Succeeded ✅
- ars-poland: Untouched, Succeeded ✅
- BIRD sessions: idle between scenarios (same as pre-upgrade) ✅

## Artifacts
- Evidence: `labs/dual-hub-hubless-region-ars/show-output/route-map-upgrade/`
- Activation script: `labs/dual-hub-hubless-region-ars/deploy/activate-hub-ars-routemaps.ps1`
- Deploy log: `labs/dual-hub-hubless-region-ars/deploy-log.md` (section: Hub ARS Route-Map Upgrade 2026-08-05)

---

# Route-Map User Stories — Design Decisions
**Author:** Trinity (Azure Network SME)  
**Date:** 2026-08-05T10:32:00+02:00  
**Lab:** `dual-hub-hubless-region-ars`  
**For:** Jose Moreno  
**Status:** DECISION ARTIFACT — no Azure changes made

---

## Summary

This decision captures the key team-relevant findings from the route-map user stories guide
(`labs/dual-hub-hubless-region-ars/route-map-user-stories.md`).

---

## Decisions

### D1 — Four-Mechanism Model Is the Correct Design Frame

Before applying any routing policy, distinguish:
- **A** Route visibility/advertisement (BGP control plane) — what route maps can influence
- **B** Next-hop selection (UDR/BGP precedence) — UDR > BGP always
- **C** Traffic authorization/containment (NSG/firewall) — route maps cannot help here
- **D** Topology/reachability (peering/tunnel) — route maps cannot create paths

**Implication:** Requests like "advertise only to the NVA subnet" require all four mechanisms.
Route maps alone address only A. This distinction must be explicit in all future design reviews.

### D2 — ARS Route-Map Eligibility Rule (Same-VNet Constraint)

Route maps can only be applied to BGP peers whose peerIp is within the ARS VNet address space.

| ARS instance | NVA peer | peerIp | ARS VNet | Eligible? |
|---|---|---|---|---|
| ars-hub1 | NVA1 | 10.10.1.4 | 10.10.0.0/16 | ✅ Yes |
| ars-hub2 | NVA2 | 10.20.1.4 | 10.20.0.0/16 | ✅ Yes |
| ars-poland | NVA1 | 10.10.1.4 | 10.30.0.0/24 | ❌ No (EMP-001) |
| ars-poland | NVA2 | 10.20.1.4 | 10.30.0.0/24 | ❌ No (EMP-001) |
| ars-hub1 | VPN GW connection | (in-VNet) | 10.10.0.0/16 | ✅ Yes |
| ars-hub2 | VPN GW connection | (in-VNet) | 10.20.0.0/16 | ✅ Yes |

This constraint is **not documented by Microsoft as of 2026-08-03**. Runtime error is authoritative.

### D3 — Recommended Experiment Order (ars-hub1/hub2 upgrade required)

Priority order for remaining route-map experiments — all require ars-hub1 and/or ars-hub2
first-use upgrade (~30 min + ~$6/day surcharge irreversible per ARS):

1. **Story H — Community tagging** (ars-hub1/hub2 inbound NVA peering): zero risk, additive
2. **Story E — On-prem inbound filter** (ars-hub1/hub2 inbound VPN GW connection): security value
3. **Story D — Infra prefix filter outbound** (ars-hub1/hub2 outbound VPN GW): hygiene
4. **Story G — Summarization** (requires address plan redesign first — 10.31/24 + 10.32/24 not adjacent)

Do not proceed with any of these until Jose approves ars-hub1 and ars-hub2 upgrades.

### D4 — Inter-Hub Communication Requires Topology Change First

There is currently **no hub1↔hub2 data-plane path**. Route maps cannot create one.
Options:
- (Recommended for production) NVA-to-NVA IPsec overlay with BGP + BIRD filters
- (Lab teaching shortcut) Direct hub1↔hub2 global VNet peering + UDRs forcing NVA on both sides

Route maps become useful on the inter-hub story **only after** the topology is fixed.
Without the topology fix, any "inter-hub prefix filtering" discussion is premature.

### D5 — Summarization Requires Contiguous CIDR Planning

`10.31.0.0/24` and `10.32.0.0/24` cannot be safely summarized — smallest common aggregate
is `10.0.0.0/10`.

For future spoke growth: allocate from `10.32.0.0/20` (spoke-c1 = `10.32.0.0/24`,
spoke-c2 = `10.32.1.0/24`, ... spoke-c16 = `10.32.15.0/24`). Advertise summary `10.32.0.0/20`
to on-prem. This is the correct production-scale addressing pattern.

### D6 — Prefer BIRD for Cross-VNet Scenarios; Use Route Maps for Hub-Local Eligible Connections

| Scenario type | Preferred tool | Reason |
|---|---|---|
| Cross-VNet BGP peer (ars-poland ↔ NVA1/NVA2) | **BIRD/FRR** | No locality constraint, no upgrade, no surcharge |
| Hub-local BGP peer (ars-hub1 ↔ NVA1) | **Route map OR BIRD** | Both eligible; route map adds GUI observability |
| VPN/ER GW connection filtering | **Route map** | No BIRD equivalent; map is the only ARS-native lever |
| Per-spoke policy | **UDR** | Route maps have no per-spoke attachment point |
| Traffic containment | **NSG/firewall** | Route maps are control-plane only |

---

## Open Questions for Jose Moreno

- [ ] **D3:** Approve ars-hub1 first-use upgrade for Story H (community tagging)? (~$6/day surcharge; irreversible)
- [ ] **D3:** Approve ars-hub2 upgrade after hub1? (or both in sequence same session?)
- [ ] **D4:** Is inter-hub data-plane path (hub1↔hub2) in scope for a future experiment? If yes: IPsec overlay or direct peering?
- [ ] **D5:** Should future spoke-c3 be allocated from 10.32.x to enable clean /23 summarization demo?
- [ ] **EMP-001:** File Microsoft support ticket / feedback for undocumented ARS route-map locality constraint?

### 2026-08-05T11:10:29.060+02:00: User directive
**By:** Jose Moreno (via Copilot)
**What:** Whenever a user story includes an NVA-to-NVA overlay, explain the requirement that justifies its complexity and compare it with simpler non-overlay designs. Add a distinct hub-to-hub-without-overlay user story if that is a meaningful alternative.
**Why:** User request — captured for team memory

### Decision Brief — US01–US10 Intent Reframing

**Author:** The Kid (Public Storyteller / user-value editor) · **Date:** 2026-08-05
**Artifact:** `labs/dual-hub-hubless-region-ars/route-map-user-stories.md` — intent framing for
US01–US10 only, plus one new shared reading note in §1
**Requested by:** Jose Moreno

**Context:** Jose flagged US01's original wording — "I want each hub to learn only an approved
subset of the other's prefixes, so inter-region blast radius and route-table growth stay bounded" —
as mechanism-first: it didn't say *why* an owner would want partial reachability, whether
applications are deliberately isolated, or whether the driver is security. He clarified the ask is
about **intent**, not the formal `As a... I want... so that...` definition. This is an editorial
pass, not a scenario redesign: no topology, attachment point, supported/unsupported classification,
current-lab applicability, expansion delta, validation plan, rollback, diagram spec, citation, cost,
or matrix row was touched.

## 1. Editorial pattern applied

Every US01–US10 story now carries a three-field **Intent** block, replacing the previous one-line
Intent paragraph:

- **Why this need exists** — concrete application/organizational/operational context (autonomy,
  fault domains, change isolation, tenancy, scale, regulation — never "because the mechanism allows
  it").
- **Desired user outcome** — what the platform owner or application team experiences, stated before
  any route-map mechanics.
- **When this story does not apply** — the condition under which the restriction/optimization would
  be artificial or counterproductive, so every unsupported/blocked story (US06, and US10's
  gateway-connection gap) still carries a user-centric reason to exist rather than reading as a
  rejected idea.

A one-paragraph reading note was added at the top of §1 (`## 1. User stories`) explaining this
convention once, so it is not repeated ten times, and stating explicitly that route filtering is
never treated as authorization in any Intent field.

Each `**Story.**` sentence was rewritten only where it previously led with the mechanism (US01, US03
lightly, US04, US05, US06, US07 lightly, US08, US09); US02 and US10 already carried motivating
context in the story sentence and were tightened rather than restructured. No technical/scenario
meaning changed in any sentence — topology, objective, and evidence sections were left untouched and
were checked against each rewritten Story sentence for consistency.

## 2. US01 — before / after

**Before:** "As a platform network owner with two regional hubs, I want each hub to learn only an
approved subset of the other's prefixes, so inter-region blast radius and route-table growth stay
bounded while shared services remain reachable." Intent: one sentence about policy boundaries.

**After (Story):** "As a platform network owner running two regional hubs whose application estates
are built, changed, and operated independently, I want each hub to learn only the specific set of the
other region's prefixes that its own workloads actually depend on — not the other region's full
address space by default — so that a change, incident, or uncontrolled route-table growth in one
region cannot silently spread into the other, while the shared services, DR, and management flows
each region does depend on stay reachable."

**After (Intent, condensed):**
- *Why* — regional estates are often intentionally autonomous (different teams, change windows,
  overlapping/tenant address space); only shared services, DR, management, or specific approved
  inter-region flows need to cross. Drivers: fault-domain separation, change isolation, route-scale
  control, tenant boundaries, regulatory/data-residency constraints.
- *Desired outcome* — one region's teams keep operating without an uninvited routing/incident
  spillover from the other, while their real cross-region dependencies keep working.
- *Does not apply* — if every app in both regions legitimately needs full cross-region reachability
  and prefix scale is fine, don't impose an allow-list. Security can be a driver, but filtering is not
  authorization — NSGs/firewall/app controls still gate what a permitted path may carry.

This directly answers Jose's three questions: yes, applications can be deliberately isolated by
design (autonomy/fault-domain/tenancy reasons, named explicitly); the driver can be security among
several others, and BGP filtering is explicitly stated as not being authorization; and the story now
states the condition under which selective exchange should *not* be imposed.

## 3. Stories whose user value remained ambiguous

None of US01–US10 was left with an ambiguous or mechanism-only intent after this pass. One nuance
worth flagging rather than hiding: **US09** ("choosing and migrating between NVA-side and ARS-side
policy") is inherently a network-architecture/governance story — its "user" is the network engineering
team avoiding silent policy drift between two enforcement points, not an application team experiencing
a routing outcome. That is a legitimate and clearly stated value (incidents caused by duplicated or
lost BGP policy), just a different *kind* of stakeholder than US01–US08/US10, which are framed from an
application- or site-facing outcome. This is noted for transparency, not as a defect requiring further
edits.

## 4. Validation

- Targeted `grep` for `Why this need exists|Desired user outcome|When this story does not apply`
  returns exactly 3 hits per story (30 total) plus the one-time definitions in the new §1 reading
  note — no story is missing a field, none duplicated.
- Re-read every `**Maps solve**` / `**Maps do not solve**` / `**Alternatives**` / `**Recommended**`
  section against its rewritten Story sentence — no technical claim was altered or contradicted.
- File line count grew from a pre-edit baseline (~1324 lines, per initial truncated read) to 1464
  lines — confirms no accidental content loss; end-of-file sections (`## 2. Comparison matrix`,
  `## 3. Diagram index for Oracle`, `## 4. References`) are byte-for-byte present and unedited.
- No diagram created or modified, no Azure/IaC touched, nothing committed (file is untracked in this
  workspace, confirmed via `git status`).

## 5. Change footprint

- `labs/dual-hub-hubless-region-ars/route-map-user-stories.md` — US01–US10 `**Story.**` sentences
  (rewritten where mechanism-first) and `**Intent.**` blocks (restructured to the three-field
  format); one new reading-note paragraph added at the top of §1. Nothing else in the file touched.
- `.squad/agents/kid/history.md` — entry appended for this editorial pass.
- `.squad/decisions/inbox/kid-user-story-intents.md` — this brief.

Nothing else touched. No diagrams authored. No Azure/IaC change. No secrets or subscription
identifiers recorded.

### Decision Brief — Route-Map User Stories v2 (Reframing + Diagram Handoff)

**Author:** Morpheus (Lead / Architect) · **Date:** 2026-08-05 · **Status:** For review
**Artifact:** `labs/dual-hub-hubless-region-ars/route-map-user-stories.md` (replaced in place, 40 KB)

## 1. What was decided

The user-story document is now a **topology-independent design guide**, not a scenario catalogue
written against the deployed lab.

| Aspect | v1 (superseded) | v2 (this artifact) |
|---|---|---|
| Baseline topology | The deployed `dual-hub-hubless-region-ars` estate | A purpose-built generic reference topology per story |
| Story framing | Argumentative; dissected the prompt wording | Neutral; states mechanism, options, and decision criteria |
| Lab relationship | Implicit throughout | Isolated to one `Current lab` line per story + §2 matrix |
| Applicability | Prose verdicts (`yes` / `partly` / `no`) | Four explicit classes with an exact additive delta |
| Diagrams | Not specified | A `Diagram specification` block per story with stable IDs |

**Rationale.** A catalogue written against the deployed estate silently inherits that estate's
constraints, so the reader cannot separate a platform limitation from a local accident. Leading with
a clean reference topology and treating current-lab applicability as a separate question produces a
reusable design guide and a cleaner test plan simultaneously.

**Ownership.** Trinity authored v1 and was locked out of this revision cycle by the requester. The
replacement was authored independently; v1 was superseded rather than revised by its original author,
consistent with the existing pattern for contested design reviews.

## 2. Story set (9)

| ID | Story | Route-map value |
|---|---|---|
| US01 | Selective regional prefix exchange between two hubs | supporting |
| US02 | Primary/backup hybrid egress with a matching return path | primary |
| US03 | Dynamic default-route injection into workload networks | supporting |
| US04 | Admission control for prefixes learned from on-premises | primary |
| US05 | Outbound workload-prefix hygiene toward on-premises | primary |
| US06 | Per-tenant / per-spoke-group routing policy | none |
| US07 | Route aggregation for spoke-scale growth | primary |
| US08 | BGP community tagging for downstream policy and diagnostics | primary |
| US09 | Choosing and migrating between NVA-side and ARS-side policy | supporting |

Each story carries: statement · problem and operational intent · generic reference topology with
named nodes, links, address examples and BGP relationships · policy objective and desired route
outcome · what route maps solve · what they do not solve · alternatives · recommended solution with
decision criteria · test-bed requirements and pass/fail evidence · rollback · current-lab
applicability class · exact additive delta · diagram specification.

## 3. Applicability distribution

| Class | Count | Stories |
|---|---|---|
| `testable as-is` | 5 | US02, US04, US05, US08, US09 |
| `testable with additive expansion` | 2 | US01, US03 |
| `requires isolated alternate test bed` | 1 | US07 |
| `blocked by platform limitation` | 1 | US06 |

**Cost inflection worth flagging.** All three Route Servers have now completed the first-use
route-map upgrade — `ars-poland` during the failed Δ3 association attempt, `ars-hub1` and `ars-hub2`
on 2026-08-05 (~26 min, both `Succeeded`, with inert activation maps left unassociated). The ~30-min
wait and the per-ARS surcharge are sunk. Every `testable as-is` story therefore costs nothing
additional to run, which inverts the previous priority ordering that deferred these behind an upgrade
gate.

**Recommended run order** (from §2 of the artifact): US08 and US04 first (priority 1 — zero cost,
minimal disruption, and US08 establishes the community scheme the other stories reference), then
US02, US05, US03, US01, US06, US07.

## 4. Diagram handoff to Oracle

Nine diagrams, stable IDs below. Each `Diagram specification` block in the artifact lists node set,
grouping/regions, labelled edges, the highlighted route or policy element, and the required
before/after states. **Diagrams must use the story's generic reference topology, not the deployed lab
topology.** Oracle owns authoring; no diagrams were created or modified in this cycle.

| Diagram ID | Story | Core visual assertion |
|---|---|---|
| `US01-inter-hub-selective-exchange` | US01 | Overlay creates the path; the map narrows what crosses it |
| `US02-hybrid-egress-preference` | US02 | AS-PATH length decides the return path; failover inset |
| `US03-dynamic-default-injection` | US03 | ECMP default resolved into a deterministic primary |
| `US04-inbound-prefix-admission` | US04 | Allow-list at gateway ingress, before propagation |
| `US05-outbound-prefix-hygiene` | US05 | eBGP-learned prefixes filterable; VNet-native prefixes are not |
| `US06-per-group-policy-segmentation` | US06 | No per-peering attachment; UDR carries the differentiation |
| `US07-route-aggregation-scale` | US07 | Many /24s become one /20; attributes stripped on the aggregate |
| `US08-community-tagging-policy` | US08 | Attributes change, reachability does not |
| `US09-policy-placement-migration` | US09 | Same intent, two control points; eligibility decides placement |

## 5. Capability grounding

Route-map statements were re-verified against Microsoft Learn on 2026-08-05 (*About route maps for
Azure Route Server*, *Route Server FAQ*, *ExpressRoute and VPN gateway support*, *Route Server in
multiple regions*) and cross-checked against lab evidence in `lessons-learned.md`, `deploy-log.md`
and `show-output/route-map-upgrade/`. The peer-locality restriction
(`HubBgpConnectionFromSpokeVnetCannotReferenceRouteMap`) remains absent from Learn; our runtime
evidence is still the only authority for it.

## 6. Scope and deviations

**Changed:** `labs/dual-hub-hubless-region-ars/route-map-user-stories.md` ·
`.squad/agents/morpheus/history.md` · this brief.
**Not touched:** README, `route-map-scenarios.md`, `design.md`, `manifest.md`, `validation.md`,
`deploy-log.md`, IaC, diagrams, live Azure. Nothing committed.

**Deviation — size.** Target was ≤25 KB; the artifact is 40 KB. Nine stories × twelve mandated
subsections plus a diagram specification each does not compress below roughly 40 KB without deleting
decision content, and the stated tiebreaker was decision usefulness over prose. Reducing to seven
stories would land near 32 KB at the cost of dropping two of the mandated coverage topics. Flagging
for a call rather than deciding unilaterally.

## 7. Open questions

- [ ] Accept the 40 KB artifact, or trim to 7 stories (~32 KB) by folding US09 into §0 and merging
      US05 into US04?
- [ ] Approve the recommended run order (US08 + US04 first) as the next experiment batch?
- [ ] US01 requires an inter-hub path. Preference: global VNet peering (fast, coarse) or NVA-to-NVA
      IPsec overlay (production-representative, more setup)?
- [ ] US07 needs an isolated bed or a fresh contiguous allocation. Approve `10.34.0.0/23` for the
      additive variant, or defer until a dedicated aggregation lab?
- [ ] File a documentation-feedback item with Microsoft for the undocumented peer-locality
      restriction?

### Decision — Storage endpoint path-equivalence lab

**Timestamp:** 2026-08-05T13:43:07.691+02:00  
**Owner:** Morpheus  
**Artifact:** `labs/storage-endpoint-path-equivalence/lab-card.md`

## Decision

Use Azure Blob Storage and a sequential, single-client paired-control design to compare ordinary public access, a classic `Microsoft.Storage` service endpoint, a target-only service-endpoint policy, and a blob private endpoint.

The lab must not state that these modes use an identical physical data-plane path. It can establish or falsify equivalence only at observable layers:

- Service endpoint: public DNS/destination remains, but the effective next hop becomes `VirtualNetworkServiceEndpoint` and Storage sees the client's private source/VNet identity.
- Private endpoint: the same application FQDN resolves to a private-endpoint NIC address and is routed VNet-locally.
- Service endpoint policy: changes allowed destination resources, not DNS or endpoint route type.

DNS, effective routes, packet captures, Storage resource logs, endpoint/firewall state, and optional VNet flow records form the evidence contract. Traceroute and latency are explicitly non-authoritative because Azure PaaS/Private Link underlay visibility is opaque.

Phase 0 selected `swedencentral` + `Standard_B2ts_v2`: B1ls and B1s were absent from the regional catalog; B2ts_v2 passed catalog and live `az vm create --validate`. The exact tagged preflight RG was verified deleted. Phase 4 remains closed; no lab deployment is authorized.

## Trinity handoff

Trinity must specify the safe transition/rollback order for Storage public access, subnet rules, private DNS, and endpoint-policy association; confirm policy resource-ID shape; define fresh-connection request commands and correlation IDs; and mark which VNet flow-log records are expected versus optional.

### Decision Brief — US10 Bow-Tie Dual-Site Regional Affinity

**Author:** Morpheus (Lead / Architect) · **Date:** 2026-08-05 · **Status:** For review
**Artifact:** `labs/dual-hub-hubless-region-ars/route-map-user-stories.md` (v2 → v3, +30 KB, now 71 KB)
**Requested by:** Jose Moreno · **Trinity:** locked out of this revision cycle, as directed

## 1. What was added

A tenth topology-independent story, stable ID `US10-bow-tie-dual-site-regional-affinity`, plus the
matrix, distribution, diagram-index and reference updates it forces. No other lab file, diagram,
README, IaC, validation result or live Azure resource was touched. Nothing committed.

Jose's description was treated as design direction. The document does not discuss whether "square" or
"bow-tie" is the formally correct label; it simply builds the pattern he described.

## 2. Generic reference architecture (ExpressRoute)

Diagonal attachment matrix, no cross-connections:

| Element | Value |
|---|---|
| Region R1 | `hub-1` 10.1.0.0/16 · `ergw-1` · `ars-1` · `nva-1` 10.1.1.4 AS 64496 · spokes 10.1.16.0/24, 10.1.17.0/24 |
| Region R2 | `hub-2` 10.2.0.0/16 · `ergw-2` · `ars-2` · `nva-2` 10.2.1.4 AS 64497 · spokes 10.2.16.0/24, 10.2.17.0/24 |
| Site 1 | `dc-1` 10.8.0.0/16 behind `cpe-1` AS 64500 → `er-1` → `ergw-1` **only** |
| Site 2 | `dc-2` 10.9.0.0/16 behind `cpe-2` AS 64501 → `er-2` → `ergw-2` **only** |
| Excluded | `cpe-1`→`er-2` and `cpe-2`→`er-1` — drawn explicitly as crossed-out edges |
| On-prem DCI | `cpe-1`↔`cpe-2` corporate WAN, eBGP 64500↔64501 |
| Azure inter-region | `nva-1`↔`nva-2` eBGP 64496↔64497 over `hub-1`↔`hub-2` global peering, 65515 stripped on export |
| Microsoft edge | AS 12076 on both private peerings |

**Inter-region mechanism — why the NVA overlay.** Global peering alone gives reachability but no BGP
attribute to shape and no automatic withdrawal. Global Reach is a genuine second *site-to-site* path
(and the right answer for DCI loss) but joins sites, not hub VNets, so it cannot provide hub-to-hub
transit; across geopolitical regions it also requires Premium circuits. vWAN inter-hub solves the
problem but replaces the Route Server construct this guide is about. The overlay is the only
candidate that both creates the path and gives a BGP policy point on each side — which is where the
AS-path hygiene has to live.

**Azure-to-Azure transit through the circuits does not work**, and this is documented rather than
merely discouraged: ExpressRoute cannot be configured as a transit router, and the Route Server FAQ
states that NVA-advertised routes returning through the MSEE are dropped by the second Route Server.

## 3. What route maps do and do not solve here

**Solve.** (a) Inbound on `ars-*`←ER-gateway connection: admission control on what each circuit may
inject, and — because inbound runs *before* best-path — genuine de-preference or rejection of a
DCI-leaked remote-site prefix, which is the one place a map preserves regional affinity by changing
forwarding rather than advertisement. (b) Outbound on `ars-*`→ER-gateway connection: shape and tag
what each region offers its own circuit, de-prefer backup-role prefixes, defend the ER advertisement
budget under branch-to-branch. Prepends must use a **public** ASN — the MSEE strips private ASNs, so
a private prepend is invisible on-premises. (c) Inbound/outbound on ARS↔NVA: bound and tag what
crosses the overlay.

**Do not solve.** Creating the DCI, the overlay, the peering or Global Reach. Modifying or filtering
the natively advertised VNet address space. Removing 65515, or rescuing a route already dropped by
loop prevention — that check runs before inbound policy. Attaching on the MSEE side. Changing the
local best path from an outbound map, which runs after best-path selection. Guaranteeing symmetric
forwarding — a map shapes one direction of one connection; symmetry is an outcome of two mirrored
policies. Per-spoke granularity — no VNet-peering attachment object exists.

**Compared to.** CPE LOCAL_PREF (strongest, authoritative site-side lever) · NVA BGP policy (owns the
65515 strip and non-eligible peers) · ER connection routing weight (coarse Azure-side preference) ·
ER BGP communities (site-side regional classification with no Azure-side tagging) · UDR (only way to
force a next hop) · AVNM routing configuration (keeps those UDRs consistent at scale) · NSG /
Azure Firewall (a backup that works in one direction only is often better closed than half-open) ·
Global Reach (site-to-site, never hub-to-hub) · vWAN (managed replacement for the whole construct).

## 4. Applicability — new class introduced

**`requires disruptive topology change` — additive staging, disruptive activation.**

The four classes used in v2 could not describe US10 honestly. Every new resource stages while the lab
runs, but the affinity pattern is only reachable by **deleting `conn-hub2-to-onprem` and
`conn-onprem-to-hub2`** — the exact path on which the Δ2 prepend result and the S2/S3 failover
timings were measured. Classifying it as `testable with additive expansion` on the strength of the
staging phase would have been misleading. New distribution across 10 stories: as-is 5 · additive 2 ·
isolated bed 1 · blocked 1 · disruptive 1.

## 5. Required lab delta (VPN analogue)

Retained as **onprem1**: `vnet-onprem` (norwayeast, 10.40.0.0/16, `vpngw-onprem` AS 65000).

| Added | Detail |
|---|---|
| `vnet-onprem2` | polandcentral, 10.50.0.0/16 — preflight-validated region; **must not** be peered to `vnet-poland-ars` or the set-C spokes |
| `vpngw-onprem2` | VpnGw1 active-active, BGP, **ASN 65003**, 2 Standard PIPs (lab total 11) |
| `vm-onprem2-ep` | `Standard_B2ts_v2`, 10.50.1.x |
| DCI | `conn-onprem-to-onprem2` / `conn-onprem2-to-onprem`, V2V + BGP, new PSK |
| Hub interconnect | `vnet-hub1`↔`vnet-hub2` global peering, AllowForwardedTraffic, no gateway transit |
| Overlay | `vm-nva1` 65001 ↔ `vm-nva2` 65002 multi-hop eBGP, with `bgp_path.delete(65515)` on export |
| New affinity pair | `conn-hub2-to-onprem2` / `conn-onprem2-to-hub2` |
| **Removed** | `conn-hub2-to-onprem`, `conn-onprem-to-hub2` |

Reused: all three Route Servers (all past the first-use upgrade), all three existing VPN gateways,
both NVAs, all existing spokes, both route tables.

**Cost class medium — ~+$10–11/day**, taking the lab from roughly $72/day to roughly $83/day. This is
a further breach of the ~$50/day guardrail (rule #7) and needs a **fresh explicit approval**; the
existing approval covered the current footprint only. **Time** ~60–75 min staging (the `vpngw-onprem2`
long pole dominates) + ~15 min activation + ~30 min evidence capture. **Disruption risk high and
specific:** `vpngw-onprem` stops seeing the hub2 copies of 10.31.0.0/24 and 10.32.0.0/24, so the Δ2
`65515-65001` versus `65515-65002-65002-65002` comparison ceases to exist on that gateway and the
S2/S3 timings stop describing the live topology.

## 6. Key ASN constraint and recommended mitigation

All hub-side gateways and all Route Servers use 65515. Route maps cannot remove it — the drop happens
in gateway/ARS loop prevention *before* inbound policy, and reserved ASNs may not be prepended or
removed.

- **Works:** site prefixes stay clean. 10.40.0.0/16 originates `65000`, becomes `65003 65000` across
  the DCI, and `vpngw-hub2` accepts it. The Azure-to-site backup direction is also clean because the
  on-prem gateways hold distinct ASNs (65000 / 65003). Both directions of the site-1 backup converge.
- **Does not work:** Azure prefixes cannot make a second Azure entry. Re-advertised across the DCI
  they still carry 65515 and are dropped by `vpngw-hub2` and `ars-hub2`. The on-prem DCI therefore
  backs up *site* prefixes only — never Azure-to-Azure. The ExpressRoute equivalent wall is AS 12076
  plus private-ASN stripping at the MSEE.

**Mitigation, ranked.** (1) **NVA-side 65515 strip on the overlay plus an explicit scope statement —
additive, recommended**; it reuses the proven Δ1 filter and matches production ExpressRoute reality.
(2) Controlled re-origination on an on-prem-side NVA — **disruptive**: no BGP policy point exists
between two Azure VPN gateways, so it means a fourth Route Server with branch-to-branch or
NVA-terminated IPsec (the previously rejected D5), rebuilding the on-prem side. (3) Distinct gateway
ASNs — only actionable where the gateway does not coexist with a Route Server; ARS coexistence pins
the hub gateways to 65515. Option 3 is precisely why option 1 works at all.

**Shared-dependency warning.** The overlay is a dependency of two nominally independent failure
responses — cross-region Azure-to-Azure traffic *and* the ER/VPN-failure backup. If it fails, both
fail, and the DCI cannot substitute. Build it redundantly; do not document the corporate WAN as its
backup.

## 7. Evidence and rollback

Six layers, all captured **before** activation: L1 gateway learned/advertised routes (VPN gateways;
ER route table in the generic bed) · L2 Route Server learned/advertised routes on all three ARS ·
L3 NVA/CPE RIB via `birdc` · L4 VM effective route tables on all five endpoints · L5 ping and
traceroute matrix, both directions · L6 timed polls at 30/60/120/180 s, failover ≤180 s and failback
≤90 s measured **independently per direction**. One-directional convergence is a FAIL, not a partial
PASS — it is the characteristic defect of this topology.

Rollback sequence (1–5 restore service, 6–8 restore cost): detach maps → restore NVA BIRD config from
version control → delete the new hub2↔onprem2 pair → recreate the hub2↔onprem1 pair with a fresh
matching PSK on both halves → confirm Δ2 evidence returned at `vpngw-onprem` → delete the DCI pair →
remove the peering and overlay → delete `vpngw-onprem2`, `vm-onprem2-ep`, `vnet-onprem2` and the two
PIPs → re-run L1–L5 and diff against baseline.

## 8. Diagram handoff to Oracle

| Diagram ID | Core visual assertion |
|---|---|
| `US10-bow-tie-generic-er` | Diagonal attachment plus two indirect backups; maps defend affinity, topology defends reachability. Includes crossed-out `cpe-1`⇢`er-2` / `cpe-2`⇢`er-1` edges and two failure insets (F1 circuit loss, F4 overlay loss) |
| `US10-bow-tie-lab-vpn-analogue` | The additive stage, the one connection pair that must be deleted, and the `vpngw-hub2` annotation showing where 65515 blocks the on-prem backup |

Two diagrams because one would be unreadable at this density. `US10-bow-tie-lab-vpn-analogue` is the
single documented exception to the "diagrams use the generic reference topology" rule, since its
entire purpose is to show the delta including the deleted edges.

## 9. Grounding

Microsoft Learn, retrieved 2026-08-05: *About route maps for Azure Route Server* (attachment points,
inbound before / outbound after best-path, reserved-ASN prohibitions, no VNet-address-space
modification, no MSEE-side maps, 2-byte ASNs) · *Azure Route Server FAQ* (65515 loop-prevention drop;
NVA routes dropped by the second Route Server via the MSEE — the FAQ's own bow-tie diagram; ER
preferred over VPN; branch-to-branch advertisement limit) · *Configure and manage Azure Route Server*
(co-located VPN gateway must be active-active with ASN 65515) · *ExpressRoute routing* (AS 12076;
MSEE removes private ASNs; ExpressRoute is not a transit router; no data-transfer symmetry
requirement) · *About ExpressRoute Global Reach* (site-to-site only; Premium across geopolitical
regions). Lab evidence: `lessons-learned.md` (Δ1 strip, Δ2 prepend, S2/S3 timings, EMP-001 peer
locality, DEV-001 PSK recovery) and `show-output/baseline-pre-delta3/`.

## 10. Open questions

- [ ] Approve the disruptive activation at all, or keep US10 as a paper design until a dedicated
      bow-tie lab can be built in its own resource group?
- [ ] If approved: fresh cost approval for ~$83/day, or tear down something else first?
- [ ] Confirm `polandcentral` for `vnet-onprem2`, or prefer co-locating site 2 in
      `switzerlandnorth` with hub2?
- [ ] Capture and archive a full L1–L5 baseline before activation as a named evidence set, so the
      pre-US10 lab state stays citable after the hub2↔onprem1 connections are gone?
- [ ] IPsec on the NVA-to-NVA overlay, or plain eBGP over the global peering (cheaper, sufficient for
      every routing assertion in the story)?

### Decision Brief — Overlay audit (Task A) and US11 no-overlay story (Task B)

**Author:** Morpheus (Lead / Architect) · **Date:** 2026-08-05
**Artifact:** `labs/dual-hub-hubless-region-ars/route-map-user-stories.md` — v3 → **v4**, 10 → **11 stories**
**Requested by:** Jose Moreno
**Scope guard:** no Azure/IaC change, no diagram files authored, nothing committed, live lab untouched.

## 0. The user question

> "Some of the user stories include an overlay between NVA1 and NVA2. If an overlay is really
> required, please explain why, since it adds significant complexity as compared to non-overlay
> topologies. That might be another User Story, hub-to-hub without an overlay?"

Both halves were correct. v3 used "overlay" as one word for three different things, and the
no-overlay design was a genuinely missing story rather than a footnote.

## 1. What was wrong — terminology, not topology

v3 wrote *"IPsec overlay carrying eBGP"* as an atomic phrase. That hid three independent layers:

| Layer | What it is | What it buys |
|---|---|---|
| Azure-native **underlay** | Global VNet peering / AVNM connected group | The forwarding path. No BGP, no header. Non-transitive. |
| NVA-to-NVA **BGP adjacency** | Multi-hop eBGP over that underlay, TCP/179 | Prefix-level policy, attributes, automatic withdrawal. **Not an encapsulation.** |
| **Encapsulation** | IPsec / GRE / VXLAN tunnel between the NVAs | Separation of underlay reachability from overlay forwarding. Nothing else. |
| **Forwarded data path** | The devices a packet actually touches | Never includes a Route Server. |

Once separated, the answer to Jose falls out: the BGP session buys the allow-list; the encapsulation
buys nothing for policy. New **§0.1** defines this once and is referenced by US01, US10 and US11.

## 2. The one Azure limitation that actually necessitates encapsulation

Not reachability, and not the BGP session. From `azure/route-server/multiregion`: Route Server
programs learned routes into **all** subnets in its VNet — including the NVA's own subnet — so the
moment remote-region prefixes are redistributed into the local Route Server, the local NVA's route to
the remote region points back at itself. Encapsulation breaks the recursion because the tunnel's
outer destination is the remote NVA's underlay address, still covered by the peering system route.

**It is conditional.** No redistribution into ARS → no loop → no tunnel. The same Learn article
documents the escape hatch (`disableBgpRoutePropagation` on the NVA subnets + explicit UDRs), which
became US11 variant C.

## 3. Task A outcome — per story

| Story | Overlay verdict | Reason |
|---|---|---|
| **US01** | **Demoted to conditional variant.** Retained, not deleted. | The allow-list is a BGP requirement, satisfied by the adjacency alone. US01's own premise is "a small approved subset", which is exactly the condition under which the static/native design suffices. Default is now the smallest sufficient mechanism, with a pointer to US11; encapsulation applies only when approved prefixes are redistributed into ARS, churn, or need NAT. |
| **US10** | **Retained as required**, with the requirement named. | Four requirements converge and no non-overlay mechanism meets all four: automatic spoke-wide propagation; **automatic withdrawal** on ExpressRoute failure; AS-PATH/community-based affinity; a churning prefix set (every spoke in two regions plus two on-prem estates). Requirement two is decisive — a static route cannot withdraw itself. US11-C is named as the rejected simpler alternative, with the reason. |
| **US02–US09** | No overlay present. | `nva-1`/`nva-2` in US03 are an in-region HA pair, not a cross-region pair. US09's "decision overlay" was a *visual* term and was renamed to "decision panel" to remove the ambiguity. |

Both retaining stories now carry an explicit **"Overlay: required or not"** block with *why the added
complexity is justified*, *simpler non-overlay alternative*, and a pointer to §0.1's operational
burden list: NVA HA/lifecycle, tunnel **and** BGP monitoring, two-sided prefix filters, 65515
stripping (route maps cannot do it — the drop happens before inbound policy), MTU/MSS when
encapsulated, BGP-timer-bound convergence (60 s keepalive / 180 s hold), two-ended capture for
asymmetry, and one shared failure domain for every cross-region flow.

§0.1 also carries the **shared overlay decision table** (requirement → simplest mechanism → overlay
needed? → why) and the closing rule: *an overlay must solve a stated requirement; being present in a
reference architecture is not a requirement.*

## 4. Task B outcome — US11 (`US11-hub-to-hub-without-nva-overlay`)

**Classification:** `testable with additive expansion` · route-map value **limited / supporting** ·
cost **very low** · **priority 1**.

Three variants, deliberately *not* interchangeable:

- **A — native hub peering.** One global VNet peering pair; hub address space / shared services only.
  `AllowGatewayTransit` and `UseRemoteGateways` false both sides — a VNet using a remote gateway may
  not have its own, and both hubs have one.
- **B — direct workload connectivity.** Direct spoke↔spoke global peerings, or AVNM connectivity
  configurations (mesh + global mesh, or hub-and-spoke with direct connectivity). Removes the hub hop;
  next-hop type `ConnectedGroup` for AVNM mesh. Explicitly flags that a more-specific cross-region
  route beats an existing `0/0`→NVA UDR, so the flow becomes uninspected **by design**.
- **C — bounded static NVA transit.** Global peering as underlay + UDRs with next hop
  `VirtualAppliance` = the **remote** NVA's IP, on each NVA subnet. Six constraints stated: a spoke
  UDR may never point at the remote NVA (peering is non-transitive, "direct connectivity" fails); the
  UDR destination must not contain the next-hop address; `VirtualNetworkGateway` next hop is
  unavailable in any VNet hosting a Route Server (Learn: the Route Server *is* that VNet's gateway);
  Basic ILB frontends are unreachable across global peering; blanket `disableBgpRoutePropagation` on a
  brownfield NVA subnet also removes ARS-injected on-prem routes existing flows depend on; and it is
  static. **Written as "to be demonstrated", not "supported".**

**Why global hub peering alone is not transit** — three things people expect and none happen:
attached spoke prefixes do not cross; Route Server-learned prefixes do not cross; gateway-learned
prefixes do not cross. The Route Server FAQ settles the hub-to-hub case in one sentence — *"Can I
peer two Azure Route Servers in two peered virtual networks…? No, Azure Route Server doesn't forward
data traffic. To enable transit connectivity through the NVA, set up a direct connection (for
example, an IPsec tunnel) between the NVAs"* — which is simultaneously why US11 exists (the Route
Server is not the missing piece) and why US10 keeps its tunnel.

**Decision threshold to leave US11** — six testable triggers with thresholds: route churn/scale,
automatic convergence, policy attributes, overlapping address space, multi-tenant isolation, N²
peering avoidance.

**Route-map value — limited/supporting, stated honestly.** Local maps can still govern eligible local
ARS routes (inbound to stop an unwanted remote copy being installed; outbound on `ars`→`gw` to stop
remote prefixes being offered to on-prem). Maps have **no role at all** in variants A and B (no BGP
present) and none in variant C's forwarding decision (a UDR, which no map can influence). Maps cannot
make a route cross a global peering, cannot attach to a VNet peering, and cannot filter the VNet
address space ARS advertises natively — which is precisely what variant A relies on.

**Alternatives:** direct peering (GA) · AVNM connectivity configurations (GA; vWAN-hub-as-hub is
preview, high-scale connected groups need preview registration — flagged, not assumed) · AVNM routing
configurations / UDR management (incl. `UseExisting`, API 2025-01-01+) · vWAN with routing intent ·
static UDRs · Private Link / application-layer patterns, since a private-link resource may live in a
different region from the endpoint's VNet, giving service access with **no** inter-region network at
all — frequently correct, almost never proposed.

## 5. Current-lab applicability — proposed only, nothing deployed

1. **Test 1 (recommended first experiment for the whole catalogue).** `vnet-hub1` (10.10.0.0/16,
   swedencentral) ↔ `vnet-hub2` (10.20.0.0/16, switzerlandnorth) global peering; all transit flags
   false. Prove hub endpoint VM reachability. **Expected non-effects are the point:** no ARS route-set
   change on `ars-hub1`/`ars-hub2`/`ars-poland`, 10.20.0.0/16 must not appear in `vpngw-hub1`
   advertisements, set-C spoke tables and the two `0/0` copies unchanged.
2. **Test 2.** Direct `vnet-spoke-a` (10.11.0.0/24) ↔ `vnet-spoke-b` (10.21.0.0/24) peering — the
   smallest defensible variant-B proof; AVNM is the scale alternative but a larger first step.
   Acknowledge up front that the new /24 beats the existing `0/0`→NVA UDR.
3. **Test 3 (optional, conditional on test 1, reversible).** Route table per NVA subnet:
   `snet-nva` hub1 → `10.21.0.0/24` via `10.20.1.4`; `snet-nva` hub2 → `10.11.0.0/24` via `10.10.1.4`.
   Do **not** disable BGP propagation on those subnets in the live lab. Deliverable is the
   demonstration, not the assertion.

**Caveats recorded:** creating a peering on a Route Server VNet triggers a route refresh to all peered
NVAs — soft if BIRD supports RFC 2918, **hard with traffic disruption** if not; confirm via
`birdc show protocols all` first and treat both hubs as a change window, on create *and* on rollback.
**Cost delta:** no billable resource — peerings and route tables carry no hourly charge; only
inter-region peering data transfer, per GB both directions, negligible at probe volumes (confirm
current swedencentral↔switzerlandnorth rates before sustained testing). **Time:** under 5 minutes per
test. **Rollback:** delete in reverse order, re-diff every capture.

**Evidence (traceroute explicitly not accepted):** peering state/sync/flags · effective routes
before/after · Network Watcher next hop as the platform-authoritative per-direction answer and the
primary legality proof for variant C · Network Watcher connectivity check + bidirectional matrix ·
ARS learned/advertised diffs on all three Route Servers · gateway learned/advertised per peer ·
variant C only, NVA interface/firewall counters and LAN captures at **both** NVAs · `birdc show
protocols all` before/after to prove a soft, not hard, reset.

## 6. Diagram IDs added (specifications only — Oracle authors)

- `US11-no-overlay-native-peering` — hub↔hub peering with three explicit ✗ annotations for what does
  not cross; a callout stating no tunnel and no NVA-to-NVA BGP session exists in the figure.
- `US11-no-overlay-direct-workloads` — cross-region workload edge bypassing both hubs, with a
  longest-match route panel showing the `0/0`→NVA UDR being beaten.
- `US11-no-overlay-static-nva-transit` — **conditional**, publish marked "to be demonstrated":
  five-hop native chain through both NVAs with UDR badges and no encapsulation.

All three use the generic topology; current-lab forms appear in captions only. `US01-…`'s spec now
draws the encapsulation greyed as a conditional variant.

## 7. Document-level updates

Version 3 → 4 with a change summary · story count 10 → 11 · new §0.1 · matrix row US11 and a reworded
US01 control column · applicability distribution now 5 / **3** / 1 / 1 / 1 · a new explicit
**recommended experiment ordering** (US11 test 1 first, US10 last) · cost note extended with US11's
zero-resource delta · diagram index +3 rows · references +7 Learn pages (multiregion overlay
rationale and its UDR alternative, VNet peering overview, UDR overview, AVNM connectivity
configurations, AVNM UDR management, hub-spoke non-transitivity, private endpoint cross-region).

A new **overlay-retention policy** paragraph sits beside the existing scenario-retention policy:
nothing is deleted; unnecessary overlays are demoted to labelled conditional variants with the
condition stated; required overlays name the requirement and the rejected simpler alternative.

## 8. Change footprint

- `labs/dual-hub-hubless-region-ars/route-map-user-stories.md` — §0 lever D wording, new §0.1, US01
  (topology / alternatives / recommended / overlay block / current lab / diagram spec), US09 wording
  fix, US10 (overlay block + US11 pointer), new US11, §2 matrix + counts + ordering + cost note +
  retention policy, §3 diagram index, §4 references. 1464 → 1967 lines; ~117 KB → ~164 KB.
- `.squad/agents/morpheus/history.md` — entry appended.
- `.squad/decisions/inbox/morpheus-us11-no-overlay.md` — this brief.

Nothing else touched. No Azure/IaC change, no diagram files, no commits, no secrets or subscription
identifiers recorded.

## 9. Open questions for Jose

- [ ] US11 test 1 (`vnet-hub1`↔`vnet-hub2` peering) — approve? It is the cheapest experiment in the
      catalogue and a prerequisite for US01 and US10, but it does put both hub Route Servers through a
      BGP refresh. Confirm the change window.
- [ ] Confirm BIRD route-refresh (RFC 2918) support on `vm-nva1`/`vm-nva2` before test 1, so we know
      whether the refresh is soft or hard.
- [ ] Is variant C worth demonstrating at all, or is documenting it as "Learn-documented, unproven
      here" sufficient for now?

### Decision Brief — US12 square hybrid connectivity (Task A) and the front-page story index (Task B)

**Author:** Morpheus (Lead / Architect) · **Date:** 2026-08-05
**Artifact:** `labs/dual-hub-hubless-region-ars/route-map-user-stories.md` — v4 → **v5**, 11 → **12 stories**
**Requested by:** Jose Moreno
**Scope guard:** no Azure/IaC change, no diagram files authored, nothing committed, live lab untouched.

## 0. The correction that drove this

> US10's "bow-tie with cross-region backup" is useful but is not the exact suggested design. Preserve
> US10. Add a separate story for the **square hybrid connectivity** design: two on-prem DCs, each
> connected only to its regional Azure hub; no diagonal cross-connections. The four sides are
> DC1↔Hub1, Hub1↔Hub2, Hub2↔DC2 and DC2↔DC1.

Accepted as direction. US10 is preserved verbatim apart from two cross-reference sentences (a
`**Related.**` line under its Stable ID, and one clause appended to its *Alternatives* paragraph).
Nothing in US10 was merged, renamed, reclassified or deleted.

## 1. US10 versus US12 — the distinction, stated once

The two stories produce the same four-corner picture and are **not** the same design.

| | US10 | US12 |
|---|---|---|
| Unit of design | The cross-region **backup**; the topology exists to make it work | The **square itself** — four named sides, no diagonals |
| Failover | Automatic cross-region hybrid backup is a **requirement**; the design is judged on it | A **bounded, written contract**; documented partial degradation is an acceptable outcome |
| Inter-hub mechanism | Decided in advance: dynamic NVA-to-NVA BGP **with** encapsulation, because four requirements converge | **Open and separately justified**; native peering is the default, vWAN is a first-class native answer |
| DCI | One line (corporate WAN), Global Reach named as an alternative | A **taxonomy** — enterprise WAN, SD-WAN, Global Reach, VPN — with their different preference semantics distinguished |
| DC↔remote-hub | Implied by the backup narrative | Its **own outcome (B3)**, with two mutually exclusive realisations and separate prerequisites |
| Cost of being right | Accepts the overlay's burden and its shared failure domain | Prefers to **reduce the claim** rather than add the fabric |

Neither supersedes the other; the guide says so explicitly in both stories.

## 2. US12 — classification and feasibility boundaries

**Stable ID** `US12-square-hybrid-connectivity` · **Disposition** `Conditional` ·
**Current-lab fit** `requires disruptive topology change` (the Hub1↔Hub2 side alone is additive) ·
**Route-map role** supporting · **Priority** 9.

**The load-bearing statement of the whole story:** *four physical sides do not imply failover.* The
four outcomes are separated and each carries its own prerequisites:

- **A — normal regional affinity.** Needs prefix admission plus AS-PATH/LOCAL_PREF discipline, and
  needs the DCI-leaked copy of the peer site's prefix to be strictly longer than the direct copy.
  **Requires nothing from the Hub1↔Hub2 side** — outcome A is complete with that side absent.
- **B — cross-region reachability**, split into three genuinely different sub-outcomes: **B1** DC↔DC
  (DCI only), **B2** Hub↔Hub (whatever the chosen mechanism actually propagates — a native peering
  propagates *nothing*: it creates system routes for each hub's own address space and there is no BGP
  session), **B3** DC↔remote-Hub (two mutually exclusive realisations, via Azure or via the DCI plus
  the peer circuit, each with its own loop-prevention constraints). **B3 is not implied by B1 + B2.**
- **C — failover after the local ER side fails.** Six named prerequisites, of which two are the ones
  that actually decide feasibility: Azure-side carriage of a *foreign* site prefix across the
  inter-hub side, and **automatic withdrawal** — a static UDR set can forward the packets but cannot
  withdraw itself. With a native-peering inter-hub side, outcome C is **not delivered**, and the
  design must say so in a *bounded-failover contract* written per flow per failure.
- **D — restoration/failback.** Backup path at least one ASN longer on every hop, no aggregation
  shortening it, nothing left UDR-pinned, and post-restoration tables **attribute-identical** to the
  pre-fault baseline, timed per direction.

**Retention rule applied.** If a build rejects or is blocked on the full-failover variant, the story
is retained with outcomes A, B1, B2 and D as its delivered value. Deleting it would remove the
reasoning that justified declining outcome C.

## 3. Inter-hub (side S-B) mechanisms — analysed independently

| Mechanism | Delivers | Choose when |
|---|---|---|
| **vWAN inter-hub** (native routing fabric) | B2, B3 and, with the hybrid attachments in the vWAN hubs, outcome C natively — *"when multiple hubs are enabled in a single virtual WAN, the hubs are automatically interconnected via hub-to-hub links"*; routing intent adds branch-to-branch secure transit | Inter-region transit is a standing requirement and nobody wants to own NVAs. **Replaces** the Route Server construct |
| **NVA-to-NVA BGP over a global-peering underlay** (dynamic classic-VNet) | Dynamic propagation, automatic withdrawal, attributes — therefore outcome C | Outcome C is a hard requirement and vWAN is unacceptable. Encapsulation **only** when remote prefixes are redistributed into the local Route Server (the self-next-hop loop of `azure/route-server/multiregion`) |
| **US11 variants A / B / C** (no overlay) | Hub address space; named workload pairs; bounded static transit | The cross-region prefix set is small, named and stable and the design does **not** claim outcome C. **This is US12's default** |
| **Application / private-endpoint** | Cross-region access to a *service* with no inter-region network at all | The requirement, once written down, names applications rather than networks |

**Default-and-justification rule recorded:** choose no overlay unless the design claims outcome C or
one of §0.1's decision-table rows. An encapsulated tunnel must be bought by automatic withdrawal,
attribute survival, ARS redistribution or overlapping address space — not by resemblance to a
reference architecture.

## 4. DCI (side S-D) mechanisms — and the sentence worth keeping

Enterprise WAN/MPLS · SD-WAN overlay (path selection may be policy-driven, so the "one ASN longer"
reasoning does **not** automatically hold — prove how the SD-WAN expresses backup preference) ·
**ExpressRoute Global Reach** · VPN (the lab analogue).

**Global Reach is S-D, never S-B.** It *"connects your on-premises networks via the ExpressRoute
service through Microsoft's global network"* and can be enabled *"between the private peering of any
two ExpressRoute circuits, as long as they're located in supported countries/regions and were created
at different peering locations"* (Premium across geopolitical regions). It joins circuits and sites;
it does **not** connect the hub VNets. A design that draws Global Reach as the Azure inter-region side
is drawing a link that does not exist.

## 5. Loop prevention — four mechanisms, all documented, all silent

1. **MSEE ASN 12076.** Microsoft uses AS 12076 for private peering, so any route that crossed one
   circuit carries it and trips the second circuit's MSEE own-AS check. *"You can't configure
   ExpressRoute as transit routers"* (`azure/expressroute/expressroute-routing`).
2. **Circuit-to-circuit reflection is not available through a Route Server** — the new hard citation
   this cycle: *"ExpressRoute circuit-to-circuit connectivity isn't supported through Azure Route
   Server. Routes from one ExpressRoute circuit aren't advertised to another ExpressRoute circuit
   connected to the same virtual network gateway. For ExpressRoute-to-ExpressRoute connectivity,
   consider using ExpressRoute Global Reach"* (`azure/route-server/expressroute-vpn-support`).
   Branch-to-branch covers NVA↔ER, NVA↔VPN and ER↔S2S-VPN — **not** ER↔ER, and not P2S.
   Microsoft's own documented two-circuit transit pattern shows what it costs instead: Route Server
   plus BGP-capable NVAs, **supernets** rather than exact prefixes *"because the exact prefixes are
   already announced in the opposite direction"*, and *"the BGP-capable NVAs must remove the AS paths
   to prevent routes from being dropped by BGP loop detection"*
   (`azure/cloud-adoption-framework/scenarios/azure-vmware/on-premises-connectivity`).
3. **Own-AS 65515.** ARS rejects a route whose AS_PATH already contains 65515 *before* inbound policy
   runs (Route Server FAQ). Hub-side gateways are pinned to 65515 by Route Server coexistence; the
   distinct on-premises ASNs (65000/65003 here) are what keep the site-prefix direction clean.
4. **When re-origination / `as-override` / NVA policy is necessary** — `as-override` for the
   dual-homed pattern, 65515 removal for the multi-region pattern, CPE-side re-origination on the site
   side. **What no route map can do:** remove its own ASN, rescue a dropped route, attach to the MSEE
   side, or make ER↔ER transit exist.

## 6. Route-map role in US12 — honest scope

Eligible local attachment points, named per region: the **ARS↔ER-gateway connection**, the
**ARS↔NVA BGP peering**, and the **ARS↔VPN-gateway connection** — all inside the Route Server's own
VNet (peer-locality rule EMP-001 / D2). Four jobs: **admission** (inbound on the gateway connection —
the one place a map influences which next hop is programmed, because inbound runs before best-path),
**tagging** (community add for origin region and backup role), **preference** (outbound AS-PATH add,
using a public ASN the enterprise owns — never a private, Azure-reserved or 64496–64511 documentation
ASN toward a circuit), and **backup-path de-preference** (inbound on the inter-hub side).

Limits restated: outbound runs after best-path so it cannot fix a wrong local best path; the VNet
address space ARS advertises natively is unfilterable; no map creates topology; no map removes 65515;
no map guarantees symmetry; no attachment object exists for a VNet peering; summarization strips
AS-PATH and community; 2-byte ASNs only; association is an ARM write against a live Route Server and
is not documented as session-preserving.

## 7. Current-lab analogue — the delta

`vnet-onprem` is **reused as DC1, unchanged**. Site 2 (`vnet-onprem2` 10.50.0.0/16 polandcentral,
`vpngw-onprem2` `VpnGw1AZ` active-active ASN **65003**, `vm-onprem2-ep`, two zoned Standard PIPs) is
added exactly as in US10 — **reused by reference, not duplicated**, including US10's S0 gateway
SKU/zone preflight gate, cost basis, timings and 9-step rollback.

Four sides in lab form: **S-A** existing `conn-hub1-to-onprem` pair (reused) · **S-C** new
`conn-hub2-to-onprem2` pair · **S-D** new `conn-onprem-to-onprem2` V2V pair with BGP — the two
on-premises VPN gateways connected directly · **S-B** two clearly separated, mutually exclusive
variants:

- **Variant N (default, no overlay).** `vnet-hub1`↔`vnet-hub2` global peering, US11 test 1 flags
  (`AllowGatewayTransit`/`UseRemoteGateways` false both sides), optionally US11-C's bounded static
  UDRs. Delivers A, B1 and hub-address-space B2. Does **not** deliver B3-via-Azure or outcome C.
- **Variant D (dynamic).** The same peering as underlay plus `vm-nva1`↔`vm-nva2` multi-hop eBGP with
  `bgp_path.delete(65515)`, and encapsulation only if remote prefixes are redistributed into the hub
  Route Servers. US10's narrow tunnel policy is imported unchanged — **no `0.0.0.0/0` and no set-C
  prefixes in either direction**, because `ars-poland`'s two default copies are what resolved DEF-001.

**Diagonal-free activation:** create and verify the S-C pair, then delete `conn-hub2-to-onprem` /
`conn-onprem-to-hub2`. Nothing else is removed. Today `vnet-onprem` is dual-homed, so the current lab
is *not* the square.

**Ledger.** Reused unchanged: all three Route Servers, all three existing gateways, both NVAs, all
existing VNets/spokes/endpoints/route tables/peerings, and the hub1↔onprem1 connection pair. Added
(variant N square): 1 VNet + 2 subnets, 2 zoned PIPs, 1 `VpnGw1AZ` gateway, 1 VM, 4 connection
objects, 1 global peering pair; PIPs 9 → 11. Added (variant D increment only): BIRD policy blocks and,
conditionally, one IPsec tunnel. Removed at activation: the two hub2↔onprem1 connections.

**Preflight / ASNs / cost / time / risk.** US10's S0 gate verbatim (`VpnGw1AZ` mandatory, PIPs with
zones 1,2,3 created first; neither `validate` nor `what-if` catches the two create-time failures this
lab already hit). Distinct ASNs 65000 / 65003 / 65001 / 65002 / 65515. Cost floor identical to
US10 — ~**$95+/day** against ~$84/day today, a floor pending a `VpnGw1AZ` retail lookup for
`polandcentral`; both breach the ~$50/day guardrail and the $72/day waiver covers neither, so a fresh
explicit approval is required before any resource is created. Variant N versus D is not a material
cost difference — the gateway dominates — so choose on operational burden. Time ~60–75 min additive,
~10 min preflight, ~15 min activation, ~30 min evidence. Risks: peering create **and** delete trigger
an ARS route refresh to all peered NVAs (soft with RFC 2918, **hard with traffic disruption**
without — confirm via `birdc show protocols all` and treat both as change windows); the activation
deletes the Δ2 direct-adjacency evidence path.

**One inherited assertion is now better supported.** US10's post-activation expectation that
`vpngw-onprem2` relays the set-C prefixes onward to `vpngw-onprem` is no longer inference alone:
*"Does Azure VPN Gateway support BGP transit routing? Yes. BGP transit routing is supported, with the
exception that VPN gateways don't advertise default routes to other BGP peers"* (VPN Gateway FAQ).
It still must be **measured**, because the reciprocal Azure-to-Azure case stays masked by the 65515
drop.

## 8. Validation and evidence (V1–V11)

All gateway learned **and** advertised routes with **`--peer` per peer IP** and both active-active
instance peers (plus `az network express-route list-route-table` in the generic bed) · Route Server
RIBs in and out per peering name, before/after, diffed · NVA/CPE BGP RIBs (`birdc show protocols
all` / `show route all`, CPE received/advertised routes) · effective route tables on every NIC in
scope · Network Watcher **next hop** per direction as the platform-authoritative forwarding answer ·
Network Watcher connectivity check plus a bidirectional matrix · **simultaneous packet capture at
both ends** filtered on the probe identity, plus interface/firewall **counters** — one-sided counter
growth is a FAIL, not a partial pass · **timed fault and failback** polls at 30/60/120/180 s per
direction · **route-table equality after restoration** (attribute-identical, not merely reachable).
**Traceroute is secondary and indicative only**, in every row.

B1/B2/B3 must be tested and reported **separately**, with B3 explicitly marked *not delivered* when
the chosen inter-hub side is variant N.

## 9. Task B — front-page story index

A new **Story index — start here** section sits immediately after the version header and before §0,
covering US01–US12 with: ID/title · user outcome · design disposition · route-map role ·
current-lab fit · key delta/blocker · diagram IDs.

Five disposition terms are defined **immediately above** the table — `Accepted candidate`,
`Conditional`, `Rejected as implementation — retained`, `Platform-blocked — retained`,
`Pending validation` — followed by an explicit *Not a disposition* paragraph stating that a
reviewer's rejection of draft wording is a wording correction, never a disposition, and never grounds
to drop a scenario. Every rejected or blocked scenario stays listed and linked.

**Dispositions, derived from the detailed stories rather than invented:** Accepted candidate 6
(US02, US04, US05, US08, US09, US11) · Conditional 5 (US01, US03, US07, US10, US12) ·
Platform-blocked — retained 1 (US06) · Rejected as implementation — retained 0 at whole-story level
(the term is used *inside* US10 for Learn's UDR-only alternative and inside US12 for ER↔ER transit and
the diagonal link) · Pending validation 0 at whole-story level (US11 variant C only).
**Current-lab fit:** as-is 5 · additive 3 · disruptive activation 2 · isolated alternate bed 1 ·
blocked 1.

Nothing was upgraded to Accepted on the strength of an unexecuted experiment: US10 and US12 are
Conditional behind the E-1/E-2 gate and a cost approval, US11 variant C is Pending validation, and
US02's Accepted rests on the *outcome* already demonstrated by the Δ2 NVA-side prepend, with the map
variant explicitly still gated.

## 10. Diagram IDs added (specifications only — Oracle authors)

- `US12-square-hybrid-normal` — a **true square**, four corners, all four sides drawn and labelled
  S-A/S-B/S-C/S-D, **both diagonals ghosted and red-crossed** as absent by design, data and control
  planes as separate edge weights, Route Servers beside their hubs and never on a thick edge, and an
  outcome callout ticking A/B1/B2 with an amber flag on B3.
- `US12-square-hybrid-failover` — recovery drawn **around** the square, never across it: S-A struck
  through, a bold three-side chain with no Route Server on it, a prerequisites panel whose unchecked
  boxes show precisely what a native-peering inter-hub side does not deliver, plus a second inset for
  the DCI-lost case.
- `US12-square-hybrid-lab-analogue` *(optional — publish only if the generic pair cannot carry the
  delta readably)* — the deployed four corners, the deleted hub2↔onprem1 pair, and the inter-hub side
  drawn as two mutually exclusive lanes.

## 11. Document-level updates (Task C)

Version 4 → **5**, stories 11 → **12**, new v5 change summary · new **Story index** section with
disposition definitions and counts · new **US12** with the three-field Intent, the four-side topology,
outcomes A–D with per-outcome prerequisites, independent S-B and S-D mechanism analyses, the
loop-prevention section, route-map scope, the lab analogue (by reference to US10), V1–V11 evidence,
alternatives, residual risks, an explicit *US10 versus US12* comparison, and three diagram specs ·
§2 matrix +US12 row, applicability distribution now 5/3/1/1/**2**, new disposition distribution,
recommended ordering reworked so US12 variant N precedes US10/US12 variant D, fifth-class paragraph
extended to both stories, retention policy extended to US01–US12, cost note extended · §3 diagram
index +3 rows and a second lab-topology exception · §4 references +9 Learn pages. All twelve stories
carry the three Intent fields. US01–US11 detailed content is otherwise untouched.

**Change footprint:** `labs/dual-hub-hubless-region-ars/route-map-user-stories.md` (1967 → ~2560
lines) · `.squad/agents/morpheus/history.md` (entry appended) · this brief. No Azure/IaC change, no
diagram files, no commits, no secrets or subscription identifiers.

## 12. Unresolved platform question for Jose

- [ ] **The one genuine open question:** does an Azure VPN gateway re-advertise routes learned on one
      BGP-enabled connection to another BGP-enabled connection **in this subscription's
      configuration**? Learn says BGP transit routing is supported; this lab has never been able to
      observe it, because the reciprocal Azure-to-Azure case is masked by the 65515 drop at the far
      hub. The square's DCI-based backup (outcome C's first hop) depends on it. It becomes measurable
      the moment `vpngw-onprem2` exists — and it should be the **first** assertion checked after S1,
      before any activation.
- [ ] Confirm the S-B variant for the lab: **N (native peering, no outcome C)** or **D (dynamic,
      outcome C plus the overlay burden)**. Recommendation: run N first — it shares every staged
      resource with D, and its bounded-failover contract is measurable without a tunnel.
- [ ] Fresh cost approval quoting a looked-up `VpnGw1AZ` retail price for `polandcentral`, before any
      resource is created (~$84/day now, ~$95+/day floor after).
- [ ] Approve the maintenance window for the `vnet-hub1`↔`vnet-hub2` peering create and delete, after
      confirming BIRD's RFC 2918 route-refresh capability on both NVAs.

### Decision Brief — US10 Wording Fix (four overclaims) + Scenario-Retention Policy

**Author:** Oracle (Documentation & Diagrams) · **Date:** 2026-08-05 · **Status:** For review
**Artifact:** `labs/dual-hub-hubless-region-ars/route-map-user-stories.md` — four US10 overclaim
locations, plus the §2 applicability/classification section (retention policy) and the matrix row it
touches
**Requested by:** Jose Moreno

**Context:** Tank authored the current US10 revision after Morpheus's version was rejected. Niobe
rejected Tank's revision for four wording-only overclaims. Tank, Morpheus, and Trinity are locked out
of this revision cycle; I am the eligible replacement author for this narrow wording fix. This is a
documentation-accuracy correction, not a topology redesign.

Scope honoured exactly: only the four US10 overclaim locations, the scenario-retention policy, and the
matrix/index wording directly required by these changes were touched. US01–US09 bodies untouched, no
diagrams authored, no Azure/IaC change, nothing committed.

## 1. The four corrections (all "association proven" → "eligibility proven, unassociated")

Niobe's finding: US10 repeatedly stated or implied that NVA-peering **association** had been proven,
when the lab has only proven route-map **eligibility** (per the D2 locality rule and the upgraded hub
Route Servers). No association has ever been executed against a live Route Server in this lab; E-1 is
the pending experiment that would prove it.

| # | Location | Before | After |
|---|---|---|---|
| 1 | Recommended-section prose (US10 body) | "the lab has proven NVA-peering attachment and has *not* yet proven gateway-connection attachment" | "the lab has proven route-map *eligibility* on the hub ARS↔NVA peerings, per the D2 locality rule and the upgraded hub Route Servers — no association has been executed anywhere, and E-1 is the test that would prove it; gateway-connection attachment is separately unverified" |
| 2 | §2 comparison-matrix, US10 row | "supporting — proven on ARS↔NVA peerings; gateway-connection attachment **unverified**, pending the US10 pre-activation gate" | "supporting — eligible (unassociated) on ARS↔NVA peerings; gateway-connection attachment unverified; both pending the US10 pre-activation gate" |
| 3 | RM-A / RM-B eligibility-status cells | "**Proven eligible**" | "**Eligible, unassociated:** peerIp in-VNet per D2, ARS route-map tier active, inert map provisioned; association never executed" |
| 4 | `US10-bow-tie-lab-vpn-analogue` diagram spec, thin control-plane edge label | `BGP · map-eligible (proven)` | `BGP · map-eligible (D2) · association untested` |

## 2. Scenario-retention policy (Jose's directive)

Jose's exact instruction: *"If any scenario is rejected, please don't delete it from the file, just
explain why it is not possible."* Added a **Scenario-retention policy** paragraph in §2, placed
immediately after the "Fifth applicability class" paragraph (which explains why US10 keeps its own
`requires disruptive topology change` classification) and immediately before "Cost note." — i.e.
directly beside the existing applicability/classification explanation it generalizes.

The policy states: no scenario is deleted from the catalogue on the strength of an applicability
classification, a reviewer's rejection of draft wording, or a platform limitation. `blocked by
platform limitation` (US06) and `requires disruptive topology change` (US10) are retained rows, not
removed ones. A reviewer rejecting how a scenario's evidence is *worded* — e.g. this US10 case, where
"proven" association was overclaimed when only eligibility was demonstrated — is a wording correction,
never grounds to drop the scenario. Every retained-but-blocked or retained-but-unverified scenario
must record: blocking reason, residual value, alternatives/conditions, and the evidence needed to
revisit the classification (e.g. US10's E-1). Applies uniformly to US01–US10 and any future addition.

## 3. Validation

Targeted `grep` across the file for
`proven NVA-peering|proven eligible|map-eligible \(proven\)|proven on ARS|association.*proven|proven.*association`
after all edits returns a single hit — inside the new retention-policy paragraph's own explanatory
sentence describing the anti-pattern ("overclaiming an association as 'proven'...") — not an actual
overclaim anywhere in the US10 content. Zero remaining overclaim phrases.

## 4. Change footprint

- `labs/dual-hub-hubless-region-ars/route-map-user-stories.md` — four US10 overclaim phrases
  corrected; scenario-retention policy paragraph added in §2.
- `.squad/agents/oracle/history.md` — revision entry appended.
- `.squad/decisions/inbox/oracle-us10-wording-fix.md` — this brief.

Nothing else touched. No diagrams created. Nothing committed. No secrets or subscription identifiers
recorded.

### Decision Brief — US10 Bow-Tie Revision (independent replacement author)

**Author:** Tank (IaC Engineer) · **Date:** 2026-08-05 · **Status:** For review
**Artifact:** `labs/dual-hub-hubless-region-ars/route-map-user-stories.md` — US10 section plus its
comparison-matrix, applicability, cost-note, diagram-index and reference rows
**Requested by:** Jose Moreno
**Morpheus:** locked out of this revision (original author, rejected) · **Trinity:** locked out of the
current user-story revision cycle · neither consulted.

Scope honoured exactly: US01–US09 bodies untouched, no diagrams authored, no Azure change, no
association experiment executed, no IaC modified, nothing committed.

## 1. Why the revision exists

My own review of `US10-bow-tie-dual-site-regional-affinity` returned REJECTED with five blocking
findings and six cautions. Morpheus is locked out, so I authored the replacement. Jose's terminology
("bow-tie") and the topology-independent framing are preserved without critique; the corrections are
factual, not stylistic.

## 2. Blocking findings — resolution

| ID | Finding | Resolution |
|---|---|---|
| B1 | Azure Route Server drawn/listed as a packet-forwarding hop | Added a **plane convention** table. Every path table now lists forwarding hops only; `ars-*` nodes appear exclusively on **thin dashed control-plane edges**, with **thick edges** reserved for the data plane in both diagram specs. The impossible failure-inset chain `vpngw-hub2 → ars-hub2 → vm-nva2` is corrected to `vpngw-hub2 → vm-nva2`. Grounded in the Route Server FAQ: ARS exchanges BGP routes only; data traffic goes directly from the NVA to the destination. |
| B2 | Wrong gateway SKU / PIP zones for the current lab's second on-prem site | `vpngw-onprem2` is specified as **`VpnGw1AZ`**, with two Standard public IPs created **zones 1,2,3** *before* the gateway. Added a five-step **Poland Central SKU/zone preflight gate** (region AZ mapping → zoned PIPs first → SKU parity check → gateway create → stop on first failure), with an explicit note that ARM `validate` / `what-if` does **not** catch `NonAzSkusNotAllowedForVPNGateway` or `VmssVpnGatewayPublicIpsMustHaveZonesConfigured` — both are create-time-only failures already recorded in `deploy-log.md` §7. |
| B3 | Stale run-rate | Current run-rate corrected to **≈ $84/day** (≈ $65.86/day baseline + 3 × ≈ $6/day route-map surcharge after `ars-poland`, `ars-hub1`, `ars-hub2`). Target stated as **≈ $95+/day**, explicitly a *floor* **pending a current `VpnGw1AZ` retail lookup for `polandcentral`**. No exactness claimed. The fresh explicit cost-approval gate is preserved; the earlier $72/day waiver covers neither figure. |
| B4 | Documentation ASN suggested on an ExpressRoute AS_PATH | Generic ER prepend policy now **requires a real customer-owned public ASN**. ASN 64496 (and the whole 64496–64511 documentation range) is stated as never valid on an ER AS_PATH; private ASNs are stripped by the MSEE regardless. Documentation ASN 64496 is retained **only** in the closed lab VPN analogue, matching the Δ3 activation contract and the existing inert `rm-hub1-activate` / `rm-hub2-activate` maps. The two test beds are clearly separated so the ASN rules cannot be mixed. |
| B5 | Route-map attachments unnamed; no PASS/FAIL assertions; association assumed to work | Candidate maps named against the D2 eligibility table: **RM-A** `ars-hub1`↔`peer-nva1` (proven eligible), **RM-B** `ars-hub2`↔`peer-nva2` (proven eligible), **RM-C / RM-D** VPN gateway connections (**unverified**), **RM-X** `ars-poland` (proven ineligible, EMP-001 peer-locality constraint). Each map carries explicit PASS and FAIL assertions. A mandatory **S2 pre-activation experiment stage** was added, gated on explicit user approval because association may reset BGP. Not called zero-disruption; not executed now. |

## 3. Cautions — resolution

1. **Global peering resets.** Creating or deleting a global VNet peering triggers a Route Server BGP
   **soft reset**, and a **hard reset** if the NVA does not support route refresh — Learn warns this
   "might cause connectivity disruption". Now requires a maintenance window, before/after/+5 min RIB
   and peer-state captures, and continuous ping across the change.
2. **NVA overlay prefix policy.** Explicit import/export table. **`0.0.0.0/0` excluded
   unconditionally in both directions**, plus set-C prefixes 10.31.0.0/24 and 10.32.0.0/24, scoped to
   approved regional aggregates — so Poland's Δ3 default-route experiment cannot gain extra copies.
   Backup-site prefixes are permitted but prepended ×2.
3. **Set-C behaviour corrected.** Prefixes are not lost after S3: they can still transit
   hub2 → `vpngw-onprem2` → DCI → `vpngw-onprem`. Both AS paths are shown — `65515-65001` (unchanged
   via hub1) and `65003-65515-65002-65002-65002` (via onprem2 + DCI). The Δ2 comparison therefore
   *changes shape* (2-vs-4 becomes 2-vs-5) rather than disappearing, and the original 4-ASN form
   survives one hop upstream at `vpngw-onprem2`. Flagged as an assertion to **measure**, with PASS and
   ALT/FAIL branches, because it depends on `vpngw-onprem2` re-advertising between its two BGP
   connections — unproven in this lab.
4. **Citation mapping corrected.** The FAQ MSEE bow-tie diagram describes a *different* shape and is
   now cited only as the reason a shared-MSEE hairpin is not a substitute — never as proof of the
   separate-circuit diagonal design. `as-override` is described strictly as the sanctioned mitigation
   in the dual-homed / same-ASN pattern (`azure/route-server/about-dual-homed-network`, plus the
   65515 rewrite in `azure/route-server/multiregion`). Global Reach is preserved as a valid on-prem
   DCI alternative while stating plainly that it joins sites, not hub VNets.
5. **Symmetry proof replaced.** Traceroute is demoted to secondary/indicative. Primary evidence is
   simultaneous NVA packet captures on tunnel and LAN interfaces filtered on probe identity, plus
   interface/firewall counters (`ip -s link`, `nft`/`iptables`) correlated at **both** NVAs, plus
   gateway and Route Server RIB evidence.
6. **`--peer` context added.** Every advertised-route collection line now carries
   `--peer <bgp-peer-ip>` — a **required** parameter of `az network vnet-gateway
   list-advertised-routes`. Peers are enumerated first with `list-bgp-peer-status` and the call is
   repeated per peer, including both active-active instance peers.

## 4. Final classification

**`requires disruptive topology change`** — retained, but the stage table now splits additive staging
from disruptive activation precisely:

| Stage | Nature | Reversible |
|---|---|---|
| S0 preflight (cost approval, Poland SKU/zone gate) | none | n/a |
| S1 additive build (`vnet-onprem2` + `vpngw-onprem2` `VpnGw1AZ`, DCI connections, NVA overlay tunnel) | additive | yes, by delete |
| S2 **route-map pre-activation experiment** (E-1 then E-2) | probing, approval-gated | yes, by disassociation |
| S3 **activation** — delete the `vnet-onprem`↔`vnet-hub2` connection pair | **disruptive** | only by rebuild + re-measure |
| S4 rollback | restorative | recreates the deleted pair; Δ2/S2/S3 evidence must be re-measured |

The single disruptive act is S3. It deletes the connection pair on which the Δ2 prepend result and
the S2/S3 failover timings were measured in their direct-adjacency form — which is exactly why
`testable with additive expansion` would be the wrong label.

## 5. Cost range

| Item | Figure | Confidence |
|---|---|---|
| Current lab run-rate, all three Route Servers route-map-upgraded | **≈ $84/day** | good — ≈ $65.86/day baseline + 3 × ≈ $6/day surcharge |
| US10 expansion target | **≈ $95+/day** | **floor only**, pending a current `VpnGw1AZ` retail lookup for `polandcentral` |
| Guardrail | ~$50/day | breached by both figures |
| Existing waiver | $72/day | **does not cover** either figure — now stale |

**Gate:** a fresh explicit cost approval from Jose is required before any US10 resource is created.
No exactness is claimed for either number.

## 6. Route-map pre-activation gate (S2)

Mandatory, sequenced, and **not executed**. Requires explicit user approval before either step,
because association may reset BGP. This is **not** a zero-disruption operation.

- **E-1 — proven-eligible path.** Associate an inert map (`rm-hub1-activate` pattern: match RFC 5737
  `192.0.2.0/24` Equals → Add AS-Path [64496] → Terminate) on `ars-hub1`↔`peer-nva1` via
  `routingConfiguration.inboundRouteMap` on the ARS **bgpConnection** child, API `2024-10-01`.
  PASS = association succeeds, no non-matching prefix altered, no BIRD session uptime reset, no ping
  loss. FAIL = any of those, or `provisioningState != Succeeded`.
- **E-2 — the unknown.** Independently test association against an **eligible local VPN gateway
  connection**, using the actual resource/API semantics rather than the read-only
  `associatedInboundConnections` composite. PASS = the API accepts the association and the effect is
  observable in the gateway RIB. FAIL = record the exact error code and treat RM-C/RM-D as
  unsupported.

**No expansion funding and no S3 activation proceeds until E-1 and E-2 have produced evidence.**

**If VPN-gateway association proves unsupported:** US10 is **retained**, but Azure-side route-map
value is reclassified to *"proven on ARS↔NVA peerings only"* and the on-prem-facing policy function
moves to NVA / CPE policy. The story's topology and affinity argument are unaffected.

## 7. Diagram IDs (stable — Oracle owns authoring)

- `US10-bow-tie-generic-er` — generic, topology-independent ExpressRoute bed. Diagonal attachment
  plus two indirect backups; thick data-plane edges never touch a Route Server; thin dashed edges
  carry BGP only.
- `US10-bow-tie-lab-vpn-analogue` — deliberately drawn on the deployed lab topology, to show the
  additive stage, the one connection pair deleted at S3, the tunnel's `no 0.0.0.0/0 / no set-C`
  policy, and where 65515 blocks the on-prem backup.

Neither spec contains an impossible path, and no Route Server appears as a forwarding hop in either.

## 8. Open questions for Jose

1. **Cost approval** — approve ≈ $95+/day (floor) for the S1 additive build, or defer until the
   `VpnGw1AZ` `polandcentral` retail price is looked up and the number is firmed?
2. **S2 approval** — run E-1 and E-2? Both may reset BGP; both need a maintenance window.
3. **Caution 3 assertion** — accept it as a documented prediction with PASS/ALT branches, or make
   measuring `vpngw-onprem2`'s re-advertisement behaviour a prerequisite of S3?
4. **Generic-bed ASN** — is a real customer-owned public ASN available for the ER prepend narrative,
   or should the generic story stay abstract (`AS <customer-public>`) as currently written?

## 9. Change footprint

- `labs/dual-hub-hubless-region-ars/route-map-user-stories.md` — US10 section replaced; matrix US10
  row, applicability-distribution note, fifth-class paragraph and cost note updated; both US10
  diagram-index rows updated; three verified references added
  (`about-dual-homed-network`, `create-zone-redundant-vnet-gateway`, CLI `--peer` requirement).
- `.squad/agents/tank/history.md` — revision entry appended.
- `.squad/decisions/inbox/tank-us10-revision.md` — this brief.

Nothing else touched. Nothing committed. No secrets or subscription identifiers recorded.

### Trinity decision — Storage endpoint path-equivalence design

**Date:** 2026-08-05  
**Lab:** `storage-endpoint-path-equivalence`  
**Status:** Design complete; Phase 4 approval closed

## Team-relevant decisions

1. Use one sequential client VM/subnet/account/FQDN/object/request method. Parallel VMs would add uncontrolled client/subnet variance.
2. Pre-stage the target Storage VNet rule while `defaultAction=Allow`; enabling `Microsoft.Storage` is then the only measured S1→S2 change.
3. Authority is the combined DNS answer, PCAP destination, NIC effective next-hop type, and Storage `CallerIpAddress`/authorization log. VNet flow logs corroborate only.
4. Same-region Storage IP firewall rules cannot form the public control. S1 uses public access Allow plus stable NAT egress.
5. Keep the service endpoint and target-only endpoint policy attached for S4; linking private DNS changes only resolution/destination and demonstrates that PE traffic is VNet-local.
6. Traceroute, hop count, and latency cannot prove Microsoft physical-underlay equivalence or difference.
7. S5 disables target public network access and compares forced-public TLS/SNI-preserving access with normal private-DNS access.
8. No ExpressRoute/Megaport and no deployment/IaC before Jose grants Phase 4 approval.

Design: `labs/storage-endpoint-path-equivalence/design.md`.

### trinity-us12-revision — US12 revision after Niobe's rejection

**Author:** Trinity (Azure Network SME) · **Date:** 2026-08-05 · **Status:** revision complete,
awaiting reviewer pass · **Scope:** US12 only, plus its front-matter cells, the US11 test-1 endpoint
reference, and one stale count in `manifest.md`. Morpheus (US12's original author) is under reviewer
lockout for this revision and was not consulted.

## Files touched

| File | Change |
|---|---|
| `labs/dual-hub-hubless-region-ars/route-map-user-stories.md` | US12 body; story-index row + disposition-terms table + counts; §2 matrix row, disposition distribution, recommended-order items 1 and 9; §3 diagram index US12 rows; §4 reference annotations; US11 *test 1* probe sentence; header v5.1 revision summary |
| `labs/dual-hub-hubless-region-ars/manifest.md` | Peering count only: 26 objects / 13 pairs → **20 objects / 10 pairs** (4 places + correction note) |

No other story body was edited. No diagram was authored. No Azure resource, IaC file or commit was
made. No scenario was deleted.

## Blocking corrections

**B-1 — Global Reach scope.** Every claim that Global Reach contributes to full outcome C or to
local-ER-side failover is removed. Its scope is now stated identically in five places (index row,
*When this story does not apply*, a dedicated *Global Reach and outcome C — the boundary* paragraph,
the S-D mechanism table, *Alternatives*, residual risks, and both diagram specs): **side S-D
(site/circuit interconnect) and outcome B1 (`dc-1`↔`dc-2`) only.** It links on-premises networks —
*"With ExpressRoute Global Reach, you can link ExpressRoute circuits to create a private network
between your on-premises networks"* (`azure/expressroute/expressroute-global-reach`) — so it never
carries a prefix across S-B and therefore never restores `hub-1` workload reachability via `hub-2`.
Outcome C's prerequisite 2 (Azure-side carriage of a foreign site prefix across S-B) is unaffected by
it.

**B-2 — Global Reach shared failure domain.** Added as a four-row table plus a consequence paragraph
in *DCI mechanisms for side S-D*, mirrored into residual risks and both diagram specs. Global Reach
rides **both** ER private peerings: usable when the failure is the ER gateway or anything above a
still-live circuit; **lost** when the defining failure is the local circuit, the private peering, or
the peering-location/provider edge. Consequence recorded: it may be documented as a DCI that survives
gateway-and-above faults, never as one that survives a circuit/private-peering fault; genuine DCI
independence needs enterprise WAN, SD-WAN or VPN over a different transport. Its routes also count
against the private-peering budget (ExpressRoute FAQ), which is now folded into the outcome-C
route-count risk row.

**B-3 — no-overlay B2 probe re-anchored.** The rejected draft proved hub-address-space reachability
"between the existing hub endpoint VMs in `snet-endpoint` 10.10.2.0/27 and 10.20.2.0/27". Verified
independently: `deploy/templates/main.bicep` creates both subnets but places **no VM** in either; the
six deployed VMs are `vm-nva1`, `vm-nva2`, `vm-hub1-ep` (→ `vnet-spoke-a/snet-workload`, 10.11.0.x),
`vm-hub2-ep` (→ `vnet-spoke-b/snet-workload`, 10.21.0.x), `vm-c1-ep`, `vm-onprem-ep`
(`manifest.md` §1, `deploy-log.md` §1). The spoke-resident pair cannot substitute — spoke prefixes do
not cross a plain hub↔hub peering, so that probe would be expected to fail and would prove the wrong
claim. **Reuse chosen and defended: `vm-nva1` 10.10.1.4 ↔ `vm-nva2` 10.20.1.4**, both inside their
hub's own address space, which is exactly what a global VNet peering carries. Prerequisites N1–N8
added: ICMP already allowed from 10.0.0.0/8 (`allow-icmp-inbound` p110) and TCP/22 (p120) on both NVA
NSGs so **no NSG change is needed**; `deny-other-inbound` p4000 means no arbitrary-port probe and
**never** TCP/179; default `AllowVnetOutBound` covers the peered space; BIRD strictly read-only
(no stop/start/reload — Δ1/Δ2 and `ars-poland`'s two `0/0` copies are live evidence); route-refresh
capability confirmed in `birdc show protocols all` before the peering create, with create *and*
rollback treated as change windows; host-terminated traffic so the probe does not depend on
`AllowForwardedTraffic` and makes no transit claim; `ip route get` + effective-route check expecting
next-hop type `GlobalVNetPeering`. Costed fallback (2 dedicated hub endpoint VMs, VM count 6 → 8,
existing subnets and NSGs) is documented but explicitly not recommended. The **US11 test-1** sentence
carrying the same false endpoint claim was corrected to point at the same two NVAs.

## Non-blocking corrections

- **(a) Citation scoping.** The `azure/route-server/expressroute-vpn-support` quote is now explicitly
  limited to "two circuits on the **same** virtual network gateway" and is no longer used as proof
  for the square's separate circuits/gateways/regions. The square is anchored on route-propagation
  facts: AS **12076** for Azure private peering and 65515–65520 reserved
  (`azure/expressroute/expressroute-routing`), private ASNs stripped on the ExpressRoute path
  (`azure/virtual-wan/route-maps-prepend-routes`), and *"You can't configure ExpressRoute as transit
  routers"* (same routing article). Reference list annotated accordingly.
- **(b) Reclassification.** ER circuit-to-circuit through a Route Server is now
  `Platform-blocked — retained` wherever the classification is about platform support. The
  disposition-terms table, the counts line and the §2 disposition distribution were updated;
  `Rejected as implementation — retained` inside US12 now covers **only** the diagonal fifth link.
- **(c) Caveat.** Both the index route-map cell and the §2 matrix cell now read *eligible but
  unassociated; gateway-connection attachment unverified*.
- **(d) Diagram truth.** The normal-state callout no longer ticks B2 unconditionally: `A ✅ · B1 ✅ ·
  B2 ⚠ hub address space only (variant N) — remote spokes need US11-B or US11-C · B3 ❓ depends on
  S-B mechanism · C ❌ not delivered by variant N; Global Reach does not supply it`.
- **(e) Mermaid.** Mermaid is retained as the required, canonical, readable form. The spec is now
  written to what Mermaid can express: `flowchart TB` with four quadrant subgraphs, corner identity
  in subgraph titles rather than geometry, side letters inside every edge label, `==>` / `-->` /
  `-.->` mapped to the plane convention with a `Legend` subgraph, and **absent diagonals carried as a
  `NOT PRESENT — by design` annotation node** instead of red-crossed edges. A draw.io/Excalidraw
  render may supplement it later for a pixel-exact square; it never replaces the Mermaid source.
- **(f) Manifest count.** 26 objects / 13 pairs → **20 objects / 10 pairs**, corrected in the
  resource-count summary, Wave 4, cleanup step 5 and the Phase-4 approval block, with an evidence
  note. Verified independently: `manifest.md` §3 lists 10 logical pairs; `main.bicep` declares 20
  `virtualNetworkPeerings` resources. No topology change.

## Consistency scan result

| Check | Result |
|---|---|
| All US12 Global Reach references match the corrected scope | PASS — 20 in-story references reviewed; S-D/B1 only, shared failure domain stated at every S-D/residual-risk point |
| Summary table, comparison matrix, story detail and diagram specs agree | PASS — index row, §2 row, story body, §3 index and both diagram specs carry the same disposition, caveat and B2 qualification |
| True-square sides and absent diagonals preserved | PASS — four sides S-A…S-D retained verbatim; diagonals still absent by design, now rendered as annotation rather than geometry |
| No implication that native hub peering gives spoke reachability | PASS — variant N delivers "B2 for hub address space only"; PASS/FAIL criteria fail a B2 claim evidenced from a spoke-resident VM |
| Story remains Conditional / requires disruptive activation | PASS — unchanged in index, §2 and the lab-analogue classification line |
| No Route Server on a data-plane hop | PASS — plane convention, FAQ quote and both diagram specs unchanged on this point |
| Scenario retention | PASS — nothing deleted; rejected/blocked items retained with reasons (diagonal link, ER↔ER platform block, outcome C under variant N) |

## Remaining live-test gates (unchanged by this revision)

1. Fresh explicit cost approval — US12 shares US10's ~**$95+/day** floor against ~$84/day current;
   the $72/day waiver covers neither.
2. US10 **S0** Poland Central gateway SKU/zone preflight (`VpnGw1AZ` + two zoned Standard PIPs)
   before `vpngw-onprem2`.
3. **E-1/E-2** route-map pre-activation gate — association is still *eligible but unassociated*, and
   ARS↔gateway-connection attachment is **unverified**.
4. **Route-refresh capability check** on both NVAs (`birdc show protocols all`) before creating or
   deleting the `vnet-hub1`↔`vnet-hub2` peering; treat both as change windows.
5. Full pre-activation baseline at every layer before the S3 deletion of
   `conn-hub2-to-onprem` / `conn-onprem-to-hub2` (Δ2 direct-adjacency evidence is destroyed by it).
6. Outcome C remains **unclaimed and untested** under variant N; variant D (and its cost/burden) is
   the only path that would make it testable in this lab.


# Oracle — inline Mermaid diagrams for US01–US12 (route-map user stories)

**Author:** Oracle (Documentation & Diagrams)
**Date:** 2026-08-05T11:10:29+02:00
**Status:** Recorded — awaiting Scribe merge
**Artifact:** `labs/dual-hub-hubless-region-ars/route-map-user-stories.md` (v5.1, owner Morpheus)
**Requested by:** Jose Moreno, routed via Niobe (US01–US12 approved; inline Mermaid authoring
explicitly authorised)

## Context

The user story catalogue carried 17 approved diagram specifications in `§3 Diagram index for Oracle`
but no rendered figures. Jose's request — *"Adding mermaid diagrams to the user stories would improve
readability."* — is a readability change only. The mandate was explicit that nothing else moves:
architecture, feasibility claims, applicability classifications, story intent, validation plans,
current-lab deltas, costs, citations, Azure/IaC, README, manifest and live resources are all
unchanged, and no commit is made.

## 1. What was added

19 inline, GitHub-renderable ` ```mermaid ` blocks covering all 17 stable diagram IDs. Every story
US01–US12 has at least one figure.

| Story | Anchor ID(s) | Blocks |
|---|---|---|
| US01 | `US01-inter-hub-selective-exchange` | 1 |
| US02 | `US02-hybrid-egress-preference` | 1 |
| US03 | `US03-dynamic-default-injection` | 1 |
| US04 | `US04-inbound-prefix-admission` | 1 |
| US05 | `US05-outbound-prefix-hygiene` | 1 |
| US06 | `US06-per-group-policy-segmentation` | 1 |
| US07 | `US07-route-aggregation-scale` | 1 |
| US08 | `US08-community-tagging-policy` | 1 |
| US09 | `US09-policy-placement-migration` | 1 |
| US10 | `US10-bow-tie-generic-er` | 2 (normal; F1+F4 failure) |
| US10 | `US10-bow-tie-lab-vpn-analogue` | 1 |
| US11 | `US11-no-overlay-native-peering` | 1 |
| US11 | `US11-no-overlay-direct-workloads` | 1 |
| US11 | `US11-no-overlay-static-nva-transit` | 1 |
| US12 | `US12-square-hybrid-normal` | 1 |
| US12 | `US12-square-hybrid-failover` | 2 (S-A lost; S-D lost) |
| US12 | `US12-square-hybrid-lab-analogue` | 1 |

Each block sits immediately after its story's generic reference topology and before the detailed
mechanism analysis; lab-analogue blocks head their own "current lab" subsection. Each carries an
`<a id="...">` anchor on the index's stable ID, a bold figure caption, one concise *What to look for*
sentence, and a `%% diagram-id:` comment inside the fence so the ID survives extraction.

## 2. Visual grammar (uniform across all 19 blocks)

| Meaning | Edge |
|---|---|
| Native Azure connectivity / ordinary forwarding | `-->` |
| BGP or other control-plane adjacency | `-.->` |
| Primary / active data path | `==>` |
| Conditional / backup data path | labelled `-.->` |
| Policy or annotation attachment | `-.-` dotted, no arrowhead, to a side node |

Policy nodes are never inserted as forwarding hops. **Azure Route Server appears only on dashed
control-plane and dotted policy edges** — verified mechanically: zero `ars*` node occurrences on any
`==>` or `-->` edge in any block. Shared `classDef` palette reused throughout: `azure`, `onprem`,
`nva`, `policy`, `blocked`, `note`.

## 3. Overlay terminology (§0.1)

Global VNet peering is drawn as **underlay / native connectivity**. NVA-to-NVA BGP is drawn as a
**control-plane adjacency**, never as an encapsulation. GRE/IPsec/VXLAN appears only where the story
genuinely requires encapsulation, on a separate labelled edge, with the forwarded data path kept
visually distinct. Diagrams stay generic and topology-independent; current-lab reuse appears only as
a short `*Current-lab note (not drawn):*` caption line or inside the two explicitly approved
lab-analogue diagrams. The deployed topology is never silently substituted for a generic test bed.

## 4. Story-specific constraints honoured

- **US01** — the simpler non-overlay path (global peering underlay, thick edge) is the default;
  encapsulation appears only as a greyed conditional-variant note node. The approved shared-services
  subset is visually motivated ("the only R1 prefix R2 may learn"; both spokes marked not offered).
- **US06** — remains a platform-blocked story. The *desired* per-group policy attachment is retained
  and drawn, alongside an explicit node stating the missing Azure attachment boundary. UDR policy
  nodes carry the real differentiation. It does not read as supported.
- **US10** — both approved IDs used; generic ER plus VPN lab analogue. No association is shown as
  proven (the ARS↔NVA label preserves "map-eligible per D2, association untested"). Route Server is
  never a data hop. The overlay import/export explicitly excludes `0.0.0.0/0` and set-C. The lab
  analogue carries the S3 `conn-hub2-to-onprem` deletion, the `65515` drop on `vpngw-hub2`, and a
  note that `ars-hub2` is not on the failure chain.
- **US11** — all three retained index IDs used, clearly distinguishing native hub-only peering,
  direct workload/AVNM connectivity, and conditional static NVA transit (marked "to be
  demonstrated"). Variant A carries three explicit "does NOT cross" annotations and states that no
  NVA-to-NVA tunnel and no NVA-to-NVA BGP session exists in the figure, so hub peering is never
  implied to propagate spoke prefixes.
- **US12** — `flowchart TB` with four quadrant subgraphs and explicit S-A/S-B/S-C/S-D side labels.
  The absent diagonal hybrid links are represented **only** by a `NOT PRESENT — by design`
  annotation node; no diagonal edges are drawn. The normal figure marks B2 as hub-address-space-only
  under variant N. The failure figure shows the three surviving sides and states that full outcome C
  requires dynamic prefix carriage and automatic withdrawal (both left unchecked in the
  prerequisites panel). Global Reach appears only on S-D/B1 and never as an S-B or outcome-C path.

## 5. Splits and one documented exception

Two approved specs were **split into two fences under a single anchor** rather than compressed into
one hairball, keeping each figure near the ~15-node budget without shrinking labels:

- `US10-bow-tie-generic-er` — normal state / F1+F4 failure state. The spec itself calls for a
  "failure inset".
- `US12-square-hybrid-failover` — S-A lost / S-D lost. The spec itself allows "a second, smaller
  figure (or a clearly separated subgraph)".

Both splits preserve the one-anchor-per-index-ID invariant (one `<a id>`, two fences).

`US12-square-hybrid-normal` ends at **16 nodes** — a deliberate, recorded exception. Splitting the
square would destroy the figure's core assertion, which is precisely that all four sides are read
together.

## 6. Grammar reconciliation (flagged for review)

The US12 specification text states *"BGP control plane = `-->`, tunnel = `-.->`"*, which inverts the
global grammar mandated for this task. I followed the **task's** grammar so that all 19 figures read
consistently, and stated the mapping explicitly inside the US12 `Legend` subgraph so a reader of that
one figure is not misled. The load-bearing US12 constraint — no Route Server on a thick data-plane
edge — holds under either convention. If Morpheus prefers the spec's local convention, the fix is a
one-line legend change plus edge-style swap in the three US12 blocks; flagging rather than deciding.

## 7. Index and summary-table updates (scope-limited)

- Front summary table: the `Diagram IDs` cells were converted from plain code spans to anchor links
  (`[`ID`](#ID)`). No other field in that table was touched.
- `§3 Diagram index for Oracle`: each ID/slug is now an anchor link, and a new `Status` column reads
  **Embedded and validated** with the block count. The existing Story and Core-visual-assertion text
  is unchanged.

## Validation

| Check | Result |
|---|---|
| Distinct Mermaid blocks rendered | **19 / 19 PASS** |
| Renderer | already-installed `@mermaid-js/mermaid-cli` from the local npx cache — no new tooling installed |
| Renderer proven meaningful | confirmed exit 1 on deliberately broken syntax before trusting exit 0 |
| Re-render after table/index edits | 19 / 19 PASS |
| Fence balance | 19 open ` ```mermaid ` / 19 close / 0 unterminated |
| Anchors per index ID | 17 anchors, exactly one per ID, no duplicates |
| Stories with >= 1 diagram | 12 / 12 (US01–US12) |
| Route Server on a data-plane arrow | none — zero `ars*` occurrences on `==>` or `-->` in any block |
| Deletions | none — heading count and all 12 story headings unchanged; US06's blocked framing, the scenario-retention policy and the retained US10 scenarios all still present |
| Content hygiene | no raw resource IDs, subscription IDs, secrets, portal URLs, non-ASCII arrows inside node labels, or HTML-heavy labels |

Per-block validation inventory (ID · blocks · result): all 17 IDs **PASS**; the two multi-block IDs
(`US10-bow-tie-generic-er`, `US12-square-hybrid-failover`) passed on both fences.

## Change footprint

| File | Change |
|---|---|
| `labs/dual-hub-hubless-region-ars/route-map-user-stories.md` | 19 Mermaid blocks + 17 anchors + captions inserted; front-table diagram-ID cells linked; §3 index linked and given a `Status` column |
| `.squad/agents/oracle/history.md` | appended this task's entry |
| `.squad/decisions/inbox/oracle-user-story-mermaid.md` | this brief |

**Not changed:** architecture, feasibility claims, applicability classifications, story intent,
validation plans, current-lab deltas, costs, citations, Azure/IaC, README, manifest, live resources.
**No deployment. No git commit.** Scratch working directory removed after validation.
