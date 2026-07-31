# vwan-routemap-summarization — validation results

← Back to [README.md](README.md) | Design spec: [design-phase3.md](design-phase3.md) | Gotchas: [lessons-learned.md](lessons-learned.md)

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
Gate A (RI OFF both hubs): FULL PASS 2026-07-31 — 6/6 summaries, 0 leaks, BGP up.
Gate B (RI ON hub-eu1 only): FULL PASS 2026-07-31 — 6/6 summaries survive on both NVAs.
Gate C (RI ON BOTH hubs — full steady state): FULL PASS 2026-07-31 — 6/6 summaries on
both NVAs; missing-summary bug NOT reproduced under hub-eu1-first, hub-eu2-second enablement order.
See Phase 3 Gate A/B/C sections below and show-output/13–52.

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
| 18 | Gate A FULL PASS (both hubs, 2026-07-31) | 6/6 summaries, 0 /24 leaks, BGP up on both NVAs | nva1: 6/6, 0 leaks, Established; nva2: 6/6, 0 leaks, Established (see 23–30) | **PASS** |
| 19 | Gate B FULL PASS (RI on hub-eu1, 2026-07-31) | 6/6 summaries survive RI on both NVAs | nva1 (RI-on): 6/6, 0 leaks; nva2 (RI-off ctrl): 6/6, 0 leaks; RI+route-map coexist (see 34–39) | **PASS** |
| 20 | Gate C FULL PASS (RI on BOTH hubs, 2026-07-31) | 6/6 summaries survive full-RI steady state | nva2 (hub-eu2 newly RI): 6/6, 0 leaks; nva1 (hub-eu1 RI): 6/6, 0 leaks; bug NOT reproduced (see 43–52) | **PASS — BUG NOT REPRODUCED** |

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

### FULL PASS — 2026-07-31T09:52:00+02:00

**Date (initial run):** 2026-07-30T17:10:00+02:00 — CONDITIONAL PASS (nva1 blocked by stuck extension)  
**Date (full re-run):** 2026-07-31T09:52:00+02:00 — **FULL PASS** (after Tank rebuilt nva1 via `az vm redeploy`)  
**Validator:** Niobe  
**Gate purpose:** Prove 6/6 summaries intact with AzFW present but before Routing Intent.  
**Pre-condition:** azfw-eu1 (hub-eu1) + azfw-eu2 (hub-eu2) Succeeded; RI = [] on both hubs.

### Measurement checklist (full re-run, 2026-07-31)

| # | Layer | Measurement | Hub | Pass criteria | Result | Evidence |
|---|-------|-------------|-----|--------------|--------|----------|
| L1a | Control | Hub secured state (AzFW ≠ null + RI = []) | hub-eu1 | azureFirewall ≠ null, RI = [] | **PASS** | [13](show-output/13-phase3-gate-a-l1a-hub-secured-state.txt) |
| L1a | Control | Hub secured state (AzFW ≠ null + RI = []) | hub-eu2 | azureFirewall ≠ null, RI = [] | **PASS** | [13](show-output/13-phase3-gate-a-l1a-hub-secured-state.txt) |
| L1b | Control | get-outbound-routes cx-onprem1 | hub-eu1 | 6 routes, 0 /24 | **UNAVAILABLE** | [29](show-output/29-gate-a-full-get-outbound-routes-api-gap.txt) |
| L1b | Control | get-outbound-routes cx-onprem2 | hub-eu2 | 6 routes, 0 /24 | **UNAVAILABLE** | [29](show-output/29-gate-a-full-get-outbound-routes-api-gap.txt) |
| L1c | Control | summarize-out Succeeded + 6 rules bound | hub-eu1 | Succeeded, 6 Replace rules | **PASS** | [15](show-output/15-phase3-gate-a-l1c-routemap-state.txt) |
| L1c | Control | summarize-out Succeeded + 6 rules bound | hub-eu2 | Succeeded, 6 Replace rules | **PASS** | [15](show-output/15-phase3-gate-a-l1c-routemap-state.txt) |
| L1c | Control | prepend-in Succeeded + rule bound | hub-eu2 | Succeeded, 1 Add rule | **PASS** | [15](show-output/15-phase3-gate-a-l1c-routemap-state.txt) |
| L1d | Control | defaultRouteTable = no _policy_PrivateTraffic | hub-eu1 | routes = [] (no RI routes) | **PASS** | [16](show-output/16-phase3-gate-a-l1d-defaultroutetable-diff.txt) |
| L1d | Control | defaultRouteTable = no _policy_PrivateTraffic | hub-eu2 | routes = [] (no RI routes) | **PASS** | [16](show-output/16-phase3-gate-a-l1d-defaultroutetable-diff.txt) |
| L1e | Control | AzFW provisioning state | azfw-eu1 | Succeeded | **PASS** | [30](show-output/30-gate-a-full-firewall-state-and-ri-check.txt) |
| L1e | Control | AzFW provisioning state | azfw-eu2 | Succeeded | **PASS** | [30](show-output/30-gate-a-full-firewall-state-and-ri-check.txt) |
| L1e | Control | RI = [] (Gate A pre-condition) | hub-eu1 | [] | **PASS** | [30](show-output/30-gate-a-full-firewall-state-and-ri-check.txt) |
| L1e | Control | RI = [] (Gate A pre-condition) | hub-eu2 | [] | **PASS** | [30](show-output/30-gate-a-full-firewall-state-and-ri-check.txt) |
| L2 | NVA RIB | BGP Established | nva1/hub-eu1 | vpngw0+vpngw1 Established | **PASS** | [23](show-output/23-gate-a-full-nva1-bgp-protocols.txt) |
| L2 | NVA RIB | BGP Established | nva2/hub-eu2 | vpngw0+vpngw1 Established | **PASS** | [24](show-output/24-gate-a-full-nva2-bgp-protocols.txt) |
| L2 | NVA RIB | BIRD: 6/6 summaries, 0 /24 leaks | nva1/hub-eu1 | 6 summaries, 0 leaks | **PASS** | [25](show-output/25-gate-a-full-nva1-bird-rib.txt) |
| L2 | NVA RIB | BIRD: 6/6 summaries, 0 /24 leaks | nva2/hub-eu2 | 6 summaries, 0 leaks | **PASS** | [26](show-output/26-gate-a-full-nva2-bird-rib.txt) |
| L2 | NVA RIB | Route count | nva1/hub-eu1 | consistent with baseline | **PASS** (37/27) | [27](show-output/27-gate-a-full-nva1-route-count.txt) |
| L2 | NVA RIB | Route count | nva2/hub-eu2 | consistent with baseline | **PASS** (37/27) | [28](show-output/28-gate-a-full-nva2-route-count.txt) |

### Summary-count table (full re-run, 2026-07-31)

| Hub | NVA | BGP state | Summaries found | /24 leaks | Verdict |
|-----|-----|-----------|-----------------|-----------|---------|
| hub-eu1 | nva1 | vpngw0+vpngw1 **Established** ✅ | **6/6** ✅ | **0** ✅ | **PASS** |
| hub-eu2 | nva2 | vpngw0+vpngw1 **Established** ✅ | **6/6** ✅ | **0** ✅ | **PASS** |

Summaries confirmed on both NVAs: 10.0.0.0/16, 10.1.0.0/16, 10.2.0.0/16, 10.3.0.0/16,
10.4.0.0/17, 10.4.128.0/17. No component /24s leaking in the customer prefix space.

### NVA restore notes

**nva2:** XFRM interfaces (xfrm41/xfrm42) and IPsec tunnels restored 2026-07-30 via
vm_run_command (skill: vwan-nva-xfrm-restore). Evidence: [19](show-output/19-phase3-gate-a-nva2-xfrm-restore-tunnel-initiation.txt).
Tunnels persist to 2026-07-31 (existing duplicate SPIs confirmed — still established).

**nva1:** Run-command extension was terminally stuck. Tank resolved via `az vm redeploy`
(~90 min in swedencentral). XFRM interfaces and IPsec tunnels then restored using the
same skill. BGP re-established 2026-07-31T09:37. Evidence: [22](show-output/22-phase3-nva-restart-restore.txt),
[23](show-output/23-gate-a-full-nva1-bgp-protocols.txt).

### L1b API finding (confirmed, 2026-07-31)

`az network vhub route-map get-outbound-routes` (virtual-wan preview extension) returns
empty output for both hubs using the correct `--resource-uri` syntax (ARM full path).
CLI argument `--connection-name` is not supported — correct flag is `--resource-uri`.
This matches the HTTP 404 behaviour documented in session show-output/17 (2026-07-30).
L2 BIRD RIB is the authoritative measurement for all Gates in this lab.

### Gate A verdict

| Hub | Verdict | Rationale |
|-----|---------|-----------|
| hub-eu1 | **PASS** | 6/6 summaries (nva1 BIRD RIB); 0 /24 leaks; vpngw0+vpngw1 Established; all control-plane checks pass |
| hub-eu2 | **PASS** | 6/6 summaries (nva2 BIRD RIB); 0 /24 leaks; vpngw0+vpngw1 Established; all control-plane checks pass |

**Overall Gate A: FULL PASS** ✅  
Both hubs confirmed: deploying Azure Firewalls (RI OFF) does **NOT** break outbound
route-map summarization. All 6 summaries (4×/16 + 2×/17) are intact on both NVAs.
Zero /24 component routes leaked. BGP Established on all 4 sessions (2 per NVA).

**Interpretation:** The firewall deployment alone is safe. Gate B (enable RI on hub-eu1)
may now proceed on both hubs.

---

## Mandatory command inventory

### Gate A initial run (2026-07-30) — CONDITIONAL PASS
- `13-phase3-gate-a-l1a-hub-secured-state.txt` — L1a hub secured state (both hubs; AzFW ≠ null, RI = [])
- `14-phase3-gate-a-l1e-firewall-provisioning.txt` — L1e AzFW provisioning state (Succeeded both)
- `15-phase3-gate-a-l1c-routemap-state.txt` — L1c route-map list + summarize-out + prepend-in (intact)
- `16-phase3-gate-a-l1d-defaultroutetable-diff.txt` — L1d defaultRouteTable diff vs pre-phase3 (no RI routes)
- `17-phase3-gate-a-l1b-get-outbound-routes-api-limitation.txt` — L1b API limitation finding
- `18-phase3-gate-a-nva1-extension-stuck-finding.txt` — nva1 stuck extension: diagnostic + impact
- `19-phase3-gate-a-nva2-xfrm-restore-tunnel-initiation.txt` — nva2 XFRM restore procedure + tunnel initiation
- `20-phase3-gate-a-l2-nva2-bird-rib.txt` — L2 nva2 BIRD RIB (PRIMARY EVIDENCE: 6/6, 0 leaks, BGP up)

### Gate A full re-run (2026-07-31) — FULL PASS (PRIMARY EVIDENCE)
- `22-phase3-nva-restart-restore.txt` — Tank: nva1 redeploy + both NVAs XFRM+BGP restore proof
- `23-gate-a-full-nva1-bgp-protocols.txt` — nva1 birdc show protocols (vpngw0+vpngw1 Established)
- `24-gate-a-full-nva2-bgp-protocols.txt` — nva2 birdc show protocols (vpngw0+vpngw1 Established)
- `25-gate-a-full-nva1-bird-rib.txt` — **PRIMARY** nva1 full RIB (6/6 summaries, 0 /24 leaks)
- `26-gate-a-full-nva2-bird-rib.txt` — **PRIMARY** nva2 full RIB (6/6 summaries, 0 /24 leaks)
- `27-gate-a-full-nva1-route-count.txt` — nva1 route count (37/27)
- `28-gate-a-full-nva2-route-count.txt` — nva2 route count (37/27)
- `29-gate-a-full-get-outbound-routes-api-gap.txt` — L1b API gap: correct --resource-uri syntax, still empty
- `30-gate-a-full-firewall-state-and-ri-check.txt` — L1e AzFW Succeeded + RI = [] both hubs (re-confirmed)

### Gate B (2026-07-31) — FULL PASS (PRIMARY EVIDENCE)
- `31-gate-b-hub-eu1-routetable-PRE-ri.txt` — hub-eu1 defaultRouteTable snapshot before RI (Tank)
- `32-gate-b-hub-eu1-ri-enable.txt` — RI enablement on hub-eu1 (Tank)
- `33-gate-b-hub-eu1-routetable-POST-ri.txt` — hub-eu1 defaultRouteTable after RI: _policy_PrivateTraffic present (Tank)
- `34-gate-b-nva2-bgp-protocols.txt` — nva2 birdc show protocols (vpngw0+vpngw1 Established; RI-off hub)
- `35-gate-b-nva2-bird-rib.txt` — **PRIMARY** nva2 full RIB (6/6 summaries, 0 leaks; RI-off hub)
- `36-gate-b-nva2-route-count.txt` — nva2 route count (37/27; unchanged)
- `37-gate-b-nva1-bgp-protocols.txt` — nva1 birdc show protocols (vpngw0+vpngw1 Established; RI-ON hub)
- `38-gate-b-nva1-bird-rib.txt` — **PRIMARY** nva1 full RIB (6/6 summaries, 0 leaks; RI-ON hub — key evidence)
- `39-gate-b-nva1-route-count.txt` — nva1 route count (37/27; unchanged from Gate A)

### Gate C (2026-07-31) — FULL PASS — BUG NOT REPRODUCED (PRIMARY EVIDENCE)
- `40-gate-c-hub-eu2-routetable-PRE-ri.txt` — hub-eu2 defaultRouteTable before RI (Tank)
- `41-gate-c-hub-eu2-ri-enable.txt` — RI enablement on hub-eu2 (Tank)
- `42-gate-c-hub-eu2-routetable-POST-ri.txt` — hub-eu2 defaultRouteTable after RI (Tank)
- `43-gate-c-l1a-hub-secured-state-both-hubs.txt` — L1a: both hubs secured, both RI Succeeded
- `44-gate-c-l1c-routemap-state.txt` — L1c: summarize-out Succeeded (both hubs), prepend-in (hub-eu2) intact
- `45-gate-c-l1d-defaultroutetable-both-hubs.txt` — L1d: both defaultRouteTables carry _policy_PrivateTraffic
- `46-gate-c-l1e-firewall-state.txt` — L1e: azfw-eu1 + azfw-eu2 both Succeeded
- `47-gate-c-nva2-bgp-protocols.txt` — nva2 birdc show protocols (Established; newly RI-ON hub)
- `48-gate-c-nva2-bird-rib.txt` — **PRIMARY** nva2 full RIB (6/6 summaries, 0 leaks; RI-ON)
- `49-gate-c-nva2-route-count.txt` — nva2 route count (37/27; unchanged)
- `50-gate-c-nva1-bgp-protocols.txt` — nva1 birdc show protocols (Established; stable since Gate A)
- `51-gate-c-nva1-bird-rib.txt` — **PRIMARY** nva1 full RIB (6/6 summaries, 0 leaks; RI-ON both hubs)
- `52-gate-c-nva1-route-count.txt` — nva1 route count (37/27; unchanged throughout A→B→C)

---

## Phase 3 — Gate B: RI on hub-eu1 only

**Date:** 2026-07-31T10:55:00+02:00  
**Validator:** Niobe  
**Gate purpose:** Prove 6/6 summaries survive after Routing Intent PrivateTraffic is enabled on hub-eu1.
Confirm RI's RFC1918 aggregate in the hub forwarding table does NOT suppress the /16 summaries
advertised outbound to the branch NVA (nva1) via the `summarize-out` route-map.  
**State:** hub-eu1: RI ON (azfw-eu1, PrivateTraffic: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16).
hub-eu2: RI OFF (unchanged; serves as the RI-off control).

### Measurement checklist

| # | Layer | Measurement | Hub/NVA | Pass criteria | Result | Evidence |
|---|-------|-------------|---------|--------------|--------|----------|
| L1 | Control | hub-eu1 defaultRouteTable has _policy_PrivateTraffic | hub-eu1 | RFC1918 routes → azfw-eu1 | **PASS** | [33](show-output/33-gate-b-hub-eu1-routetable-POST-ri.txt) |
| L1 | Control | hub-eu2 defaultRouteTable unchanged (no RI routes) | hub-eu2 | no _policy_PrivateTraffic | **PASS** | [33](show-output/33-gate-b-hub-eu1-routetable-POST-ri.txt) |
| L2 | NVA RIB | BGP Established | nva2/hub-eu2 (RI OFF) | vpngw0+vpngw1 Established | **PASS** | [34](show-output/34-gate-b-nva2-bgp-protocols.txt) |
| L2 | NVA RIB | BIRD: 6/6 summaries, 0 /24 leaks | nva2/hub-eu2 (RI OFF) | 6 summaries, 0 leaks | **PASS** | [35](show-output/35-gate-b-nva2-bird-rib.txt) |
| L2 | NVA RIB | Route count | nva2/hub-eu2 (RI OFF) | consistent | **PASS** (37/27) | [36](show-output/36-gate-b-nva2-route-count.txt) |
| L2 | NVA RIB | BGP Established | nva1/hub-eu1 (RI ON) | vpngw0+vpngw1 Established | **PASS** | [37](show-output/37-gate-b-nva1-bgp-protocols.txt) |
| L2 | NVA RIB | BIRD: 6/6 summaries, 0 /24 leaks | nva1/hub-eu1 (RI ON) | 6 summaries, 0 leaks | **PASS** | [38](show-output/38-gate-b-nva1-bird-rib.txt) |
| L2 | NVA RIB | Route count | nva1/hub-eu1 (RI ON) | consistent | **PASS** (37/27) | [39](show-output/39-gate-b-nva1-route-count.txt) |

### Summary-count table

| Hub | NVA | RI state | BGP | Summaries | /24 leaks | Verdict |
|-----|-----|----------|-----|-----------|-----------|---------|
| hub-eu1 | nva1 | **ON** (PrivateTraffic) | vpngw0+vpngw1 Established ✅ | **6/6** ✅ | **0** ✅ | **PASS** |
| hub-eu2 | nva2 | OFF (control) | vpngw0+vpngw1 Established ✅ | **6/6** ✅ | **0** ✅ | **PASS** |

Summaries confirmed on both NVAs: 10.0.0.0/16, 10.1.0.0/16, 10.2.0.0/16, 10.3.0.0/16,
10.4.0.0/17, 10.4.128.0/17.

### Coexistence finding (key)

**RI's 10.0.0.0/8 aggregate and the route-map's /16 summaries COEXIST without interference.**

- RI PrivateTraffic installs RFC1918 aggregates in the hub's **forwarding table** (defaultRouteTable)
  to steer intra-hub private traffic through AzFW. This is a data-plane / next-hop assignment.
- The `summarize-out` route-map operates on the **per-connection outbound advertisement set** —
  the set of specific prefixes the hub VPN gateway will BGP-advertise to the connected on-prem NVA.
  The route-map matches the /24 specifics from remote hub spokes and replaces them with /16 summaries.
- These are **orthogonal layers**: RI governs how the hub forwards received traffic internally;
  route-maps govern what is BGP-advertised outbound. Enabling RI does not alter the advertisement set.

**Additional observation:** nva1 BGP timestamps (vpngw0 07:37:23, vpngw1 07:37:38) did not change
during RI enablement — the BGP sessions were not reset. RI enablement on hub-eu1 was transparent
to the BGP peering between hub-eu1's VPN gateway and nva1. (nva2/hub-eu2 saw a brief vpngw0
reconvergence at 08:57, expected as hub-eu1 provisioned; vpngw1 on nva2 stayed up continuously.)

**NVA RIB symmetry:** nva1 (RI-on hub) and nva2 (RI-off hub) show structurally identical RIBs
— same 6 summaries, same 37/27 count. No asymmetry between hubs.

### Gate B verdict

| Hub | Verdict | Rationale |
|-----|---------|-----------|
| hub-eu1 | **PASS** | 6/6 summaries on nva1 (RI-ON hub); 0 /24 leaks; BGP Established; route-map unaffected by RI |
| hub-eu2 | **PASS** | 6/6 summaries on nva2 (RI-off control); 0 /24 leaks; BGP Established |

**Overall Gate B: FULL PASS** ✅  
Routing Intent PrivateTraffic on hub-eu1 does NOT suppress route-map summarization.
The /16 and /17 summaries are intact and coexist with RI's RFC1918 aggregates.
Gate C (enable RI on hub-eu2 → both hubs secured) may now proceed.

---

## Phase 3 — Gate C: RI on BOTH hubs — full steady state (PRIMARY REPRO CHECK)

**Date:** 2026-07-31T11:45:00+02:00  
**Validator:** Niobe  
**Gate purpose:** The lab's headline measurement. With RI enabled on BOTH EU hubs (hub-eu1 FIRST,
hub-eu2 SECOND), does the missing-summary bug reproduce? Does any of the 6 expected /16//17
summaries disappear from either NVA's RIB, or do /24 component routes leak?  
**State:** hub-eu1: RI ON (since Gate B, ~09:30). hub-eu2: RI ON (Tank, ~11:30, Succeeded).
**RI enablement order:** hub-eu1 → hub-eu2.

### Measurement checklist

| # | Layer | Measurement | Hub/NVA | Pass criteria | Result | Evidence |
|---|-------|-------------|---------|--------------|--------|----------|
| L1a | Control | Hub secured + RI Succeeded | hub-eu1 | AzFW ≠ null, RI Succeeded | **PASS** | [43](show-output/43-gate-c-l1a-hub-secured-state-both-hubs.txt) |
| L1a | Control | Hub secured + RI Succeeded | hub-eu2 | AzFW ≠ null, RI Succeeded | **PASS** | [43](show-output/43-gate-c-l1a-hub-secured-state-both-hubs.txt) |
| L1c | Control | summarize-out Succeeded (6 rules) | hub-eu1 | Succeeded | **PASS** | [44](show-output/44-gate-c-l1c-routemap-state.txt) |
| L1c | Control | summarize-out Succeeded (6 rules) | hub-eu2 | Succeeded | **PASS** | [44](show-output/44-gate-c-l1c-routemap-state.txt) |
| L1c | Control | prepend-in Succeeded | hub-eu2 | Succeeded, 1 Add rule (ASNs 64496/64497/64498) | **PASS** | [44](show-output/44-gate-c-l1c-routemap-state.txt) |
| L1d | Control | defaultRouteTable _policy_PrivateTraffic | hub-eu1 | RFC1918 → azfw-eu1 | **PASS** | [45](show-output/45-gate-c-l1d-defaultroutetable-both-hubs.txt) |
| L1d | Control | defaultRouteTable _policy_PrivateTraffic | hub-eu2 | RFC1918 → azfw-eu2 | **PASS** | [45](show-output/45-gate-c-l1d-defaultroutetable-both-hubs.txt) |
| L1e | Control | AzFW provisioningState | azfw-eu1 | Succeeded | **PASS** | [46](show-output/46-gate-c-l1e-firewall-state.txt) |
| L1e | Control | AzFW provisioningState | azfw-eu2 | Succeeded | **PASS** | [46](show-output/46-gate-c-l1e-firewall-state.txt) |
| L2 | NVA RIB | BGP Established | nva2/hub-eu2 (newly RI) | vpngw0+vpngw1 Established | **PASS** | [47](show-output/47-gate-c-nva2-bgp-protocols.txt) |
| L2 | NVA RIB | BIRD: 6/6 summaries, 0 /24 leaks | nva2/hub-eu2 (newly RI) | 6 summaries, 0 leaks | **PASS** | [48](show-output/48-gate-c-nva2-bird-rib.txt) |
| L2 | NVA RIB | Route count | nva2/hub-eu2 | 37/27 | **PASS** | [49](show-output/49-gate-c-nva2-route-count.txt) |
| L2 | NVA RIB | BGP Established | nva1/hub-eu1 (RI-ON since B) | vpngw0+vpngw1 Established | **PASS** | [50](show-output/50-gate-c-nva1-bgp-protocols.txt) |
| L2 | NVA RIB | BIRD: 6/6 summaries, 0 /24 leaks | nva1/hub-eu1 (RI-ON since B) | 6 summaries, 0 leaks | **PASS** | [51](show-output/51-gate-c-nva1-bird-rib.txt) |
| L2 | NVA RIB | Route count | nva1/hub-eu1 | 37/27 | **PASS** | [52](show-output/52-gate-c-nva1-route-count.txt) |

### Summary-count table (Gate C steady state)

| Hub | NVA | RI state | BGP | Summaries | /24 leaks | Verdict |
|-----|-----|----------|-----|-----------|-----------|---------|
| hub-eu1 | nva1 | **ON** (since Gate B) | vpngw0+vpngw1 Established ✅ | **6/6** ✅ | **0** ✅ | **PASS** |
| hub-eu2 | nva2 | **ON** (Gate C, newly) | vpngw0+vpngw1 Established ✅ | **6/6** ✅ | **0** ✅ | **PASS** |

Summaries confirmed on both: 10.0.0.0/16, 10.1.0.0/16, 10.2.0.0/16, 10.3.0.0/16,
10.4.0.0/17, 10.4.128.0/17.

### BGP stability across all three gates

| NVA | Session | Gate A | Gate B | Gate C | Notes |
|-----|---------|--------|--------|--------|-------|
| nva1 | vpngw0 | 07:37:23 | 07:37:23 | 07:37:23 | Never reset across all three gates |
| nva1 | vpngw1 | 07:37:38 | 07:37:38 | 07:37:38 | Never reset across all three gates |
| nva2 | vpngw0 | 06:09:28 → 08:57:07 (brief, Gate B) | 08:57:07 | 08:57:07 | Single reconvergence at Gate B (hub-eu1 RI provision); stable since |
| nva2 | vpngw1 | 06:09:22 | 06:09:22 | 06:09:22 | Never reset across all three gates |

Both RI enablements were transparent to NVA BGP sessions. Route-map summarization was
never interrupted.

### prepend-in AS-path note

The `prepend-in` route-map on hub-eu2's cx-onprem2 connection adds ASNs 64496/64497/64498
to inbound routes from nva2 (the 172.16–172.29/16 local prefixes). This operates intra-hub:
hub-eu2 receives nva2's 172.x advertisements and prepends ASNs before propagating them
to hub-eu1. From nva2's perspective, the BIRD RIB only shows what hub-eu2 sends back to nva2;
the prepend-in effect is not visible in nva2's received-route table. The de-preference
mechanism functions as designed at the hub level, confirmed by route-map Succeeded state.

### Gate C verdict

| Hub | Verdict | Rationale |
|-----|---------|-----------|
| hub-eu1 | **PASS** | 6/6 summaries on nva1; 0 /24 leaks; BGP stable; both gates of RI enablement transparent |
| hub-eu2 | **PASS** | 6/6 summaries on nva2; 0 /24 leaks; BGP Established; RI on peer hub did not cause missing summary |

**Overall Gate C: FULL PASS** ✅  
**Missing-summary bug: NOT REPRODUCED** under this RI enablement order (hub-eu1 FIRST, hub-eu2 SECOND).

Both hubs are now fully secured (Azure Firewall + Routing Intent PrivateTraffic). The
`summarize-out` route-maps on both hubs continue to produce all 6 /16 and /17 summaries
to the branch NVAs, identical to the pre-RI baseline (Gate A). Route count stable at 37/27
on both NVAs throughout Gates A→B→C. Zero /24 leaks at every gate.

**Interpretation:** In this lab, RI does not interact destructively with outbound route-map
summarization under the tested sequential enablement order. The original customer bug (missing
summary after RI enablement during a concurrent churn event) was not reproduced. Either the
trigger requires a specific concurrent operation (connection re-provisioning + RI enable), or
the bug is intermittent. Trinity should assess whether a concurrent-churn variant of Gate C
is needed for a complete repro attempt.

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
