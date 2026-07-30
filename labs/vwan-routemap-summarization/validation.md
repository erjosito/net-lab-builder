# vwan-routemap-summarization — validation results

## Summary

Phase 1 lab is deployed and the VPN data plane + BGP control plane are healthy on both hubs. Route-map
summarization is applied on both EU hubs (6 Replace rules each). Repro attempts (rule reorder, three
failover/failback cycles, and a ~670-route scale-up) did **not** reproduce the missing-summary bug —
both hubs consistently advertised all 6 summaries. See `show-output/07-repro-attempts-negative.txt`.

**Phase 2 (VPN over ExpressRoute)** is fully deployed and connected (discovered 2026-07-30):
ER circuits er-eu1 (swedencentral) and er-eu2 (westeurope) both Enabled/Provisioned; ER gateways
ergw-eu1/ergw-eu2 each with an active ER connection (conn-er-eu1 / conn-er-eu2, both `Succeeded`).
Note: initial audit (show-output/10) incorrectly reported connections=null due to a wrong query field
(`connections` vs `expressRouteConnections`) — corrected in show-output/11. README and manifest
updated 2026-07-30 to reflect actual state.

**Failover/failback cycle #4** (Phase 2 state, nva2/hub-eu2 only) run 2026-07-30: CLEAN — 6/6
summaries before and after 45s failover window. nva1 blocked by stuck run-command extension.
See `show-output/12-failover-failback-cycle4-nva2.txt`.

**Phase 3 (Azure Firewall + Routing Intent)** — Firewalls deployed 2026-07-30 by Tank.
azfw-eu1 (hub-eu1, swedencentral) and azfw-eu2 (hub-eu2, westeurope) both Succeeded.
Routing Intent NOT yet enabled (Gate A pre-condition). Gate A validation completed:
hub-eu2 **PASS** (6/6 summaries confirmed, 0 /24 leaks, BGP Established on nva2);
hub-eu1 **INCONCLUSIVE** (all control-plane checks PASS; nva1 NVA-level measurement
blocked by stuck run-command extension — nva1 VM rebuild needed by Tank).
See Phase 3 Gate A section below and show-output/13–20.

## Checklist

| # | Check | Expected | Actual | Status |
|---|-------|----------|--------|--------|
| 1 | VWAN + 3 hubs provisioned | all `Provisioned` | hub-us / hub-eu1 / hub-eu2 provisioned | PASS |
| 2 | 12 US spokes connected to hub-us | 48 contributing /24s | connected | PASS |
| 3 | Both VPN gateways deployed | `Succeeded` | vpngw-eu1 & vpngw-eu2 Succeeded | PASS |
| 4 | nva1 IPsec tunnels | 2 SAs ESTABLISHED/INSTALLED | vng0 + vng1 ESTABLISHED | PASS |
| 5 | nva2 IPsec tunnels | 2 SAs ESTABLISHED/INSTALLED | vng0 + vng1 ESTABLISHED | PASS |
| 6 | nva1 BGP | 2 sessions Established | vpngw0 + vpngw1 Established | PASS |
| 7 | nva2 BGP | 2 sessions Established | vpngw0 + vpngw1 Established | PASS |
| 8 | Baseline routes received | US /24s + hub prefixes | 91 networks each NVA | PASS |
| 9 | AS_PATH sanity | `65515 65520 65520` | confirmed | PASS |
| 10 | `summarize-out` applied both EU hubs | 6 summaries advertised | applied on hub-eu1 & hub-eu2 (6 Replace rules) | PASS |
| 11 | Both hubs advertise all 6 summaries | no missing summary | nva1 & nva2 each show 6/6, 0 /24 leaks | PASS |
| 12 | Rule-reorder / failover / scale repro | reproduce a missing summary | NOT reproduced (see 07) | NO REPRO |
| 13 | Phase 2 ER circuits deployed | er-eu1 + er-eu2 Provisioned | both Enabled/Provisioned | PASS |
| 14 | Phase 2 ER gateways + connections | ergw-eu1/eu2 with active connections | conn-er-eu1/eu2 Succeeded | PASS |
| 15 | Phase 3 firewalls | both EU hubs secured | azfw-eu1 + azfw-eu2 Succeeded, hub secured | PASS |
| 16 | Phase 3 routing intent | RI not yet enabled (Gate A) | all hubs: [] (Gate A: no RI yet) | PASS (pre-condition) |
| 17 | Failover/failback cycle #4 (nva2, Phase 2 state) | 6/6 summaries after failback | CLEAN — 6/6, 0 leaks (see show-output/12) | PASS |

### Repro test matrix (see `show-output/07-repro-attempts-negative.txt`)

| Test | Result |
|------|--------|
| Steady state (orig order) | CLEAN — 6/6 both hubs |
| Failover/failback cycle #1 | CLEAN |
| Rule reorder hub-eu2 (reverse sum6..sum1) | CLEAN |
| Failover/failback cycle #2 | CLEAN |
| Scale-up to ~670 /24 specifics | CLEAN |
| Failover/failback cycle #3 at scale | CLEAN |

### Failover/failback cycle #4 — Phase 2 state (2026-07-30, see `show-output/12-failover-failback-cycle4-nva2.txt`)

| Test | Hub | NVA | Result |
|------|-----|-----|--------|
| Baseline (Phase 2 deployed) | hub-eu2 | nva2 | CLEAN — 6/6, ER routes visible in BIRD table |
| Failover: stop bird + terminate IPsec (45s) | hub-eu2 | nva2 | Full teardown confirmed |
| Failback: restart + swanctl --load-all + XFRM init | hub-eu2 | nva2 | vng0 + vng1 re-established |
| Post-failback route check | hub-eu2 | nva2 | CLEAN — 6/6, 0 /24 leaks |
| hub-eu1 / nva1 | hub-eu1 | nva1 | BLOCKED — stuck run-command extension, untested |

**Note (cycle #4):** NVAs were deallocated at test start. Started for test, restored to deallocated after.
XFRM interfaces (xfrm41/xfrm42) are not persisted across reboots — must be manually recreated or
Tank must add a systemd startup service. `start_action = trap` in swanctl.conf does not auto-initiate;
`swanctl --initiate` must be called manually after load.

**Note:** rule reordering was the customer's *workaround*, not the trigger. The trigger
was the deploy/churn sequence. Phase 1 did not reproduce the missing-summary bug.

## Repro procedure (Scenario 3)

1. Confirm both connections advertise all 6 summaries via
   `az network vhub route-map get-outbound-routes` (or BIRD RIB on each NVA).
2. Reorder `summarize-out` rules on one hub (move a summary to first position); re-check both hubs.
3. Failover: disable the primary connection; confirm secondary carries all 6 summaries.
4. Fail back: re-enable primary; re-check both hubs for a missing summary.
5. Record any hub/order combination where a /16 or /17 summary is absent.

## Phase 3 — Gate A: Firewall deployed, NO Routing Intent

**Date:** 2026-07-30T17:10:00+02:00  
**Validator:** Niobe  
**Gate purpose:** Prove 6/6 summaries intact with AzFW present but before Routing Intent.  
**Pre-condition:** azfw-eu1 (hub-eu1) + azfw-eu2 (hub-eu2) Succeeded; RI = [] on both hubs.

### Measurement checklist

| # | Layer | Measurement | Hub | Pass criteria | Result | Evidence |
|---|-------|-------------|-----|--------------|--------|----------|
| L1a | Control | Hub secured state (AzFW ≠ null + RI = []) | hub-eu1 | azureFirewall ≠ null, RI = [] | **PASS** | [13](show-output/13-phase3-gate-a-l1a-hub-secured-state.txt) |
| L1a | Control | Hub secured state (AzFW ≠ null + RI = []) | hub-eu2 | azureFirewall ≠ null, RI = [] | **PASS** | [13](show-output/13-phase3-gate-a-l1a-hub-secured-state.txt) |
| L1b | Control | get-outbound-routes cx-onprem1 | hub-eu1 | 6 routes, 0 /24 | **UNAVAILABLE** | [17](show-output/17-phase3-gate-a-l1b-get-outbound-routes-api-limitation.txt) |
| L1b | Control | get-outbound-routes cx-onprem2 | hub-eu2 | 6 routes, 0 /24 | **UNAVAILABLE** | [17](show-output/17-phase3-gate-a-l1b-get-outbound-routes-api-limitation.txt) |
| L1c | Control | summarize-out Succeeded + 6 rules bound | hub-eu1 | Succeeded, 6 Replace rules | **PASS** | [15](show-output/15-phase3-gate-a-l1c-routemap-state.txt) |
| L1c | Control | summarize-out Succeeded + 6 rules bound | hub-eu2 | Succeeded, 6 Replace rules | **PASS** | [15](show-output/15-phase3-gate-a-l1c-routemap-state.txt) |
| L1c | Control | prepend-in Succeeded + rule bound | hub-eu2 | Succeeded, 1 Add rule | **PASS** | [15](show-output/15-phase3-gate-a-l1c-routemap-state.txt) |
| L1d | Control | defaultRouteTable = no _policy_PrivateTraffic | hub-eu1 | routes = [] (no RI routes) | **PASS** | [16](show-output/16-phase3-gate-a-l1d-defaultroutetable-diff.txt) |
| L1d | Control | defaultRouteTable = no _policy_PrivateTraffic | hub-eu2 | routes = [] (no RI routes) | **PASS** | [16](show-output/16-phase3-gate-a-l1d-defaultroutetable-diff.txt) |
| L1e | Control | AzFW provisioning state | azfw-eu1 | Succeeded | **PASS** | [14](show-output/14-phase3-gate-a-l1e-firewall-provisioning.txt) |
| L1e | Control | AzFW provisioning state | azfw-eu2 | Succeeded | **PASS** | [14](show-output/14-phase3-gate-a-l1e-firewall-provisioning.txt) |
| L2 | NVA RIB | BIRD: 6/6 summaries, 0 /24 leaks | nva2/hub-eu2 | 6 summaries, 0 leaks | **PASS** | [20](show-output/20-phase3-gate-a-l2-nva2-bird-rib.txt) |
| L2 | NVA RIB | BGP Established | nva2/hub-eu2 | vpngw0+vpngw1 Established | **PASS** | [20](show-output/20-phase3-gate-a-l2-nva2-bird-rib.txt) |
| L2 | NVA RIB | BIRD: 6/6 summaries, 0 /24 leaks | nva1/hub-eu1 | 6 summaries, 0 leaks | **INCONCLUSIVE** | [18](show-output/18-phase3-gate-a-nva1-extension-stuck-finding.txt) |
| L2 | NVA RIB | BGP Established | nva1/hub-eu1 | vpngw0+vpngw1 Established | **INCONCLUSIVE** | [18](show-output/18-phase3-gate-a-nva1-extension-stuck-finding.txt) |

### Summary-count table

| Hub | NVA | Summaries found | Expected | /24 leaks | Expected | BGP state |
|-----|-----|-----------------|----------|-----------|----------|-----------|
| hub-eu2 | nva2 | **6/6** ✅ | 6 | **0** ✅ | 0 | vpngw0+vpngw1 **Established** ✅ |
| hub-eu1 | nva1 | **UNAVAILABLE** ⚠️ | 6 | **UNAVAILABLE** ⚠️ | 0 | NOT established (XFRM not restored) ⚠️ |

### XFRM restore note

Both NVAs were deallocated. nva2 XFRM interfaces (xfrm41/xfrm42) and IPsec tunnels
(vng0/vng1) restored manually via vm_run_command. Evidence: [19](show-output/19-phase3-gate-a-nva2-xfrm-restore-tunnel-initiation.txt).

nva1 run-command extension is terminally stuck — classic invoke returns Conflict/409;
newer persistent API hangs on create/update/delete. Even VM restart did not clear the
extension agent. Tank must rebuild nva1 VM to restore access.
Evidence: [18](show-output/18-phase3-gate-a-nva1-extension-stuck-finding.txt).

### L1b API finding

`az network vhub route-map get-outbound-routes` (virtual-wan preview extension) returns
empty output for all attempts, regardless of BGP session state. Direct REST API calls to
both `/routeMaps/{rm}/getOutboundRoutes` and `/virtualHubs/{hub}/getOutboundRoutes` return
HTTP 404 "No route data was found for this request." This appears to be a platform
limitation in the swedencentral/westeurope regions with secured hubs + route-maps in
preview. L2 BIRD RIB is the authoritative fallback.

### Gate A verdict

| Hub | Verdict | Rationale |
|-----|---------|-----------|
| hub-eu2 | **PASS** | 6/6 summaries confirmed via nva2 BIRD; 0 /24 leaks; BGP Established; all control-plane checks pass |
| hub-eu1 | **INCONCLUSIVE** | All control-plane checks PASS (L1a/L1c/L1d/L1e); nva1 BIRD unavailable (stuck extension + VPN tunnels not restored). Not a FAIL: firewall is not the cause of inability to measure. |

**Overall Gate A: CONDITIONAL PASS**  
hub-eu2 provides strong positive evidence that the firewall deployment did NOT break
route-map summarization (6/6, 0 leaks, BGP up). hub-eu1 shows identical control-plane
configuration (same route-map, same hub state) but nva1 NVA-level measurement is blocked
by a persistent VM extension fault (pre-existing from prior session).

**Recommendation:** Jose may proceed to enable Routing Intent on hub-eu2 first. Routing
Intent on hub-eu1 should wait until nva1 is rebuilt and L2 evidence can be collected.
If Jose needs full PASS on both hubs simultaneously, Tank must rebuild nva1 VM first.

---

## Mandatory command inventory

- `13-phase3-gate-a-l1a-hub-secured-state.txt` — L1a hub secured state (both hubs; AzFW ≠ null, RI = [])
- `14-phase3-gate-a-l1e-firewall-provisioning.txt` — L1e AzFW provisioning state (Succeeded both)
- `15-phase3-gate-a-l1c-routemap-state.txt` — L1c route-map list + summarize-out + prepend-in (intact)
- `16-phase3-gate-a-l1d-defaultroutetable-diff.txt` — L1d defaultRouteTable diff vs pre-phase3 (no RI routes)
- `17-phase3-gate-a-l1b-get-outbound-routes-api-limitation.txt` — L1b API limitation finding
- `18-phase3-gate-a-nva1-extension-stuck-finding.txt` — nva1 stuck extension: diagnostic + impact
- `19-phase3-gate-a-nva2-xfrm-restore-tunnel-initiation.txt` — nva2 XFRM restore procedure + tunnel initiation
- `20-phase3-gate-a-l2-nva2-bird-rib.txt` — L2 nva2 BIRD RIB (PRIMARY EVIDENCE: 6/6, 0 leaks, BGP up)

- `01-resource-list.txt` — deployed inventory
- `02-nva1-ipsec-bgp-status.txt` — nva1 SAs + BGP + route count
- `03-nva2-ipsec-bgp-status.txt` — nva2 SAs + BGP + route count
- `04-nva1-as-path-baseline.txt` — AS_PATH distribution (pre route-map)
- `05-nva1-summaries-after-routemap.txt` — nva1 summaries post route-map
- `06-both-hubs-baseline-clean.txt` — both hubs steady-state comparison
- `07-repro-attempts-negative.txt` — Phase 1 repro attempts (all CLEAN)
- `08-phase3-audit-resource-inventory.txt` — full resource inventory (2026-07-30)
- `09-phase3-audit-firewalls-and-routing-intent.txt` — Phase 3 NOT started evidence
- `10-phase2-audit-er-and-gateways.txt` — Phase 2 audit (initial, incorrect connections query)
- `11-phase2-er-connections-corrected.txt` — Phase 2 corrected: ER connections ARE active
- `12-failover-failback-cycle4-nva2.txt` — Cycle #4 CLEAN (Phase 2 state, nva2)
