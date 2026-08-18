# vwan-routemap-summarization

**Status (Round 2): 🟢 LAB RUNNING — `routemap-test-rg` (swedencentral/westeurope). Billing active (2× ER gateways, 1× VPN gateway, Megaport MCR+2 VXCs). Tear down when done — see [Teardown](#round-1-teardown-status-2026-07-31).**

This lab reproduces and investigates a customer-reported **Virtual WAN route-map summarization bug**:
a `/16` summary route aggregated from **mixed-origin contributors** intermittently goes **missing**
when advertised to a branch. **Round 2** re-runs the repro with Microsoft's engineering root-cause in
hand (mixed-origin attribute inheritance + Branch-to-Branch disabled).

---

## Round 2 — mixed-origin attribute inheritance (2026-08-18)

### Microsoft's root-cause statement (paraphrased)

> The `10.x.0.0/16` summary is generated from multiple contributing `10.x` routes that have **different
> route origins/attributes**. Some contributors are learned via **ExpressRoute** and carry **AS 12076**
> (the MSEE ASN) in the AS-path; another contributor is on the **VNet/egress** path. During aggregation
> the summary **may inherit the attributes of either contributor**. If it inherits the **VNet** attributes
> it is advertised; if it inherits the **ExpressRoute/branch-learned** attributes it is treated as
> **branch-derived** and **dropped because Branch-to-Branch (b2b) is disabled** — which is why the
> advertisement appears inconsistent across recomputation cycles.
>
> **Recommended mitigation:** a higher-priority outbound route-map rule that **drops the ExpressRoute-learned
> contributors by AS-path (12076)** *before* the summarization rule runs.

### Headline results (Round 2)

> **1. The MS-recommended mitigation is validated and works.** A higher-priority rule matching
> `asPath Contains 12076 → Drop`, placed before the summarization rule, deterministically removes every
> ER-learned contributor from the aggregation input. The summary can then only ever be built from the
> VNet/egress contributor → it can never be classified as branch-derived → never dropped. ✅
>
> **2. Key finding — and an important caveat on what we could observe.** A route-map **`Replace
> route-prefix`** is the **only** way a VWAN route-map can summarize (there is no other aggregation
> action), so the customer's summarization rule is necessarily a **`Replace`**. When it aggregates, the
> hub **strips the BGP Community and AS-PATH** from the summary — documented behaviour, per
> [About Route-maps](https://learn.microsoft.com/en-us/azure/virtual-wan/route-maps-about):
> *"when using Route-maps to summarize a set of routes, the hub router strips the BGP Community and
> AS-PATH attributes from those routes."* Consequently the summary we saw at the VPN branch **always**
> carried the hub ASN `65515` and **never** `12076`, in every case (both contributors, only-ER, b2b on,
> b2b off), and we **could not** make it disappear.
> **Caveat — this does *not* prove `Replace` is immune.** The AS-PATH strip governs the **advertised**
> attributes (the `65515` we observed). Microsoft's bug is about an **internal origin/branch
> classification** the aggregate *inherits* during recomputation, which is **not visible** in that
> stripped AS-PATH — MS explicitly states a Replace-generated `/16` *can* be "treated as branch-derived
> and then dropped". So the advertised AS-PATH is the **wrong signal**: it is always `65515` and can
> never reveal the branch classification. The only valid signal is **presence vs. absence of the `/16`
> at the branch across many recompute cycles**. We built a multi-run sampling harness
> ([`race-sample.ps1`](show-output/round2/71-race-sampling-summary.md)) that forces a fresh hub
> aggregation each cycle (detach/reattach `summarize-out`) and densely polls the branch (30 samples/cycle).
> Result of **N=20 cycles (600 dense samples): the `/16` was present in every single sample — 0 drops,
> 0 anomalies**, MSEE inputs constant (11 contributor rows), branch/`er-eu2`-MSEE agreeing every cycle.
> So at the current **3 ER : 1 VNet** contributor ratio, pure recompute is **deterministic in this
> environment** and we did **not** reproduce the retirement. This is a **negative result, not proof
> `Replace` is immune** — "couldn't reproduce" means "didn't hit a branch-inheriting cycle in 20 tries".
> Next step to raise repro odds: skew the ER:VNet ratio by adding many more onprem `/24`s. The MS
> mitigation (drop AS-12076 before summarize) is the correct deterministic fix regardless, because it
> removes the branch-attributed contributor from the aggregation input entirely.
> (Full evidence: [`71-race-sampling-summary.md`](show-output/round2/71-race-sampling-summary.md).)
>
> **3. Branch-to-Branch gates ER→VPN transit (confirmed).** With b2b **disabled** the ER-learned `/24`s
> (AS 12076) never reach the VPN branch at all; with b2b **enabled** they arrive as
> `65515 12076 133937`. This is the customer condition and the reason the observation point **must be a
> VPN branch** — ER→ER transit is unconditionally blocked, so the second ER circuit (`er-eu2`) could never
> show the b2b-governed behaviour.

### Round 2 topology

Two VWAN hubs, two ExpressRoute circuits in a **bow-tie** via a **Megaport MCR** that injects the
"on-prem" ER prefixes as **free static routes** (the MSEE auto-prepends **AS 12076**, exactly reproducing
the customer's branch-derived attribute — no Google Cloud needed). The observation branch is an **Azure VM
NVA** (StrongSwan + BIRD) attached to `hub-eu1` over **IPsec + BGP**, i.e. a faithful VPN branch.

```
                 Megaport MCR (AS 133937)  —— static routes 10.0.1/2/3.0/24
                   /  bow-tie VXCs (ER private peering, MSEE prepends AS 12076)  \
                  /                                                               \
        [ er-eu1 ] Frankfurt                                         [ er-eu2 ] Amsterdam
                  \                                                               /
     ┌─────────────\─────────────────────┐                 ┌──────────────────────┐
     │   hub-eu1  (swedencentral)         │   bow-tie ER    │  hub-eu2 (westeurope) │
     │   192.168.0.0/23   VWAN Standard   │═════════════════│  192.168.2.0/23       │
     │   b2b = DISABLED (baseline)        │                 └──────────────────────┘
     │                                    │
     │   spoke-eu1  10.0.128.0/24 ────────┼──  VNet/egress contributor (AS 65515)
     │   ER-learned 10.0.1/2/3.0/24 ──────┼──  branch contributor    (AS 12076)
     │                                    │
     │   route-map summarize-out (sum1):  │   match Contains 10.0.0.0/16 → Replace 10.0.0.0/16
     │   vpngw-eu1  ASN 65515             │
     └──────────────┬─────────────────────┘
                    │ IPsec + BGP (xfrm41/42), connection cx-nva1
            [ nva1 ] Azure VM  10.100.0.4  ASN 65001   (StrongSwan + BIRD2 — VPN branch observation)
```

The summary under test is **`10.0.0.0/16`**, aggregated from a **VNet contributor** (`10.0.128.0/24`,
AS 65515) and three **ER-learned contributors** (`10.0.1/2/3.0/24`, AS `65515 12076 133937`).

### Round 2 case matrix (observed at the VPN branch nva1)

| # | Contributors in hub | b2b | Outbound route-map | `10.0.0.0/16` at branch | AS-path | Evidence |
|---|---|---|---|---|---|---|
| **A** | VNet + ER | OFF | `summarize-out` | ✅ present | `65515` (VNet-attributed) | [62](show-output/round2/62-vpnbranch-caseA-both-contributors-b2b-off.txt) |
| **B** | ER only | OFF | `summarize-out` | ✅ present* | `65515` | [63](show-output/round2/63-vpnbranch-caseB-only-ER-b2b-off-cleanrecompute.txt) |
| **D′** | ER only | ON | `summarize-out` | ✅ present | `65515` | [64](show-output/round2/64-vpnbranch-caseD-only-ER-b2b-on.txt) |
| **Base** | VNet + ER | ON | *(none)* | n/a | VNet `65515`; ER `65515 12076 133937` | [65](show-output/round2/65-vpnbranch-mitigation-validation.txt) |
| **Mit-drop** | VNet + ER | ON | `mitigation-drop` (drop 12076) | n/a | ER `/24`s **dropped**, VNet `/24` kept | [65](show-output/round2/65-vpnbranch-mitigation-validation.txt) |
| **Mit-full** | VNet + ER | ON | `mitigation-full` (drop 12076 → summarize) | ✅ present | `65515` (VNet-only source) | [65](show-output/round2/65-vpnbranch-mitigation-validation.txt) |

*\*Case B is the decisive one: with **only** ER contributors and b2b off, a `Replace`-based summary is
**still advertised** as a hub-originated `65515` route (verified after a forced detach/re-attach
recompute — fresh BGP timestamp). This is what proves `Replace` re-originates and is immune to the
branch-derived drop.*

### Mitigation, step by step

`mitigation-full` route-map on the VPN connection outbound:

| Order | Rule | Match | Action | `nextStepIfMatched` |
|---|---|---|---|---|
| 1 | `drop-er-12076` | `asPath Contains 12076` | **Drop** | `Terminate` |
| 2 | `sum1` | `routePrefix Contains 10.0.0.0/16` | **Replace** → `10.0.0.0/16` | — |

Result at the branch: `10.0.0.0/16` present (`65515`), all specifics gone — the summary is provably built
from the VNet contributor alone, so it can never be branch-derived. Full before/after RIB capture in
[show-output/round2/65](show-output/round2/65-vpnbranch-mitigation-validation.txt).

### Round 2 resource inventory

<details>
<summary><strong>Round 2 deployed resources</strong> (click to expand)</summary>

- **Resource group:** `routemap-test-rg` — VWAN `vwan-routemap2` (Standard, b2b currently **disabled**)

| Resource | Name | Region |
|---|---|---|
| Virtual hubs | `hub-eu1` (192.168.0.0/23), `hub-eu2` (192.168.2.0/23) | swedencentral / westeurope |
| ExpressRoute circuits | `er-eu1` (Frankfurt), `er-eu2` (Amsterdam) — Standard 50 Mbps | — |
| ER gateways | `ergw-eu1`, `ergw-eu2` | swedencentral / westeurope |
| ER connections (bow-tie) | `conn-eu1-er1`, `conn-eu1-er2`, `conn-eu2-er2`, `conn-eu2-er1` | — |
| Spoke (VNet contributor) | `spoke-eu1` 10.0.128.0/24 + `spoke-eu1-conn` | swedencentral |
| VPN gateway | `vpngw-eu1` (VpnGw1, ASN 65515) | swedencentral |
| VPN site / connection | `site-nva1` (ASN 65001) / `cx-nva1` (IPsec+BGP) | — |
| NVA (VPN branch) | `nva1` Ubuntu 22.04 B2ts_v2, 10.100.0.4, `nva-vnet` 10.100.0.0/24 | swedencentral |
| Route-maps | `summarize-out` (sum1), `mitigation-drop`, `mitigation-full` | hub-eu1 |
| **Megaport MCR** | `jomore-copilot-mcr-routemap2` (AS 133937, Frankfurt) + 2 VXCs | — |

**On-prem simulation:** Megaport MCR **static routes** (`10.0.1/2/3.0/24`) — free, and sufficient because
the MSEE injects **AS 12076** on any ER-private-peering prefix. No Google Cloud used.

</details>

---

<details>
<summary><strong>Round 1 — secured-hub / Routing-Intent investigation (2026-07, DECOMMISSIONED)</strong> (click to expand)</summary>

**Status: ✅ LAB FULLY DECOMMISSIONED — no running resources, no billing (as of 2026-07-31)**

Round 1 investigated a different framing of the bug: on a secured vWAN hub with outbound
**summarization** route-map rules on a VPN connection, one /16 or /17 summary intermittently went
**missing** after Routing Intent was enabled, in an **order-dependent** way. It did **not** reproduce —
see below. (Round 2 above supersedes it with Microsoft's mixed-origin root cause.)

### Headline result

> **The missing-summary bug did NOT reproduce** under the customer-approximating Phase 3 configuration
> (both EU hubs secured with Azure Firewall Standard + Routing Intent PrivateTraffic, hub-eu1 enabled
> first then hub-eu2). All 6 summaries survived across every gate (A, B, C). Route count stable at
> 37/27 on both NVAs throughout.
>
> **Root cause of non-reproduction (one line):** Routing Intent's RFC1918 aggregate
> (`_policy_PrivateTraffic`) operates at the **data-plane forwarding layer** (defaultRouteTable next-hop
> assignment), while `summarize-out` operates at the **BGP advertisement layer** (per-connection outbound
> advertisement set derived from learned BGP routes) — these planes are orthogonal and, in steady state,
> the forwarding aggregate cannot suppress the /24 specifics the route-map needs to match.

The production bug likely requires **concurrent churn** — VPN connection reconvergence racing with RI
provisioning. That variant is designed but untested (Gate D, dormant). See
[design-phase3.md](design-phase3.md#gate-c-result--gate-d-proposal-concurrent-churn).

---

## Results at a glance

| Phase / Gate | What was tested | NVA / Hub | Outcome | Primary evidence |
|---|---|---|---|---|
| **Phase 1** — plain S2S VPN, non-secured hubs | 4 failover/failback cycles, rule reorder, scale to ~670 routes | nva1 + nva2 | **NO REPRO** — 6/6 summaries clean at every check | [show-output/07](show-output/07-repro-attempts-negative.txt), [show-output/12](show-output/12-failover-failback-cycle4-nva2.txt) |
| **Phase 2** — ER circuits deployed | ER circuits + gateways active, ER connections Succeeded | hub-eu1 + hub-eu2 | Infrastructure validated; ER carries no routes (no on-prem ER side) | [show-output/11](show-output/11-phase2-er-connections-corrected.txt) |
| **Gate A** — AzFW deployed, RI OFF | Does adding Azure Firewall (no RI) break summaries? | nva1 (hub-eu1) + nva2 (hub-eu2) | **FULL PASS** — 6/6 summaries, 0 /24 leaks, BGP Established | [show-output/25](show-output/25-gate-a-full-nva1-bird-rib.txt), [show-output/26](show-output/26-gate-a-full-nva2-bird-rib.txt) |
| **Gate B** — RI ON hub-eu1 only | Does RI PrivateTraffic on hub-eu1 suppress summarize-out? | nva1 (RI-ON) + nva2 (control) | **FULL PASS** — 6/6 both NVAs; BGP never reset; RI + route-map coexist | [show-output/38](show-output/38-gate-b-nva1-bird-rib.txt), [show-output/35](show-output/35-gate-b-nva2-bird-rib.txt) |
| **Gate C** — RI ON BOTH hubs | Full customer topology: both hubs secured + RI | nva1 (hub-eu1) + nva2 (hub-eu2) | **FULL PASS — BUG NOT REPRODUCED** — 6/6 both NVAs; route count 37/27 unchanged A→B→C | [show-output/51](show-output/51-gate-c-nva1-bird-rib.txt), [show-output/48](show-output/48-gate-c-nva2-bird-rib.txt) |

The 6 expected summaries: `10.0.0.0/16`, `10.1.0.0/16`, `10.2.0.0/16`, `10.3.0.0/16`,
`10.4.0.0/17`, `10.4.128.0/17`.

---

## Detailed documentation

| Document | Purpose |
|---|---|
| [validation.md](validation.md) | Full pass/fail checklist + per-gate measurement tables with every evidence file linked |
| [design-phase3.md](design-phase3.md) | Phase 3 design spec: AzFW topology, RI plan, critical analysis, Gate D dormant experiment |
| [manifest.md](manifest.md) | Resource inventory, topology description, scenario walkthroughs, cleanup chain |
| [lessons-learned.md](lessons-learned.md) | Operational gotchas: StrongSwan config, XFRM restore, run-command extension stuck, API gap, BGP layer-separation root cause |

---

## Topology

Three-hub Virtual WAN: `hub-us` (westus2) sources routes from 12 spoke VNets. Two European
secured hubs (`hub-eu1` swedencentral, `hub-eu2` westeurope) each carry Azure Firewall Standard
with Routing Intent PrivateTraffic, a VPN gateway, and an ER gateway. Each EU hub terminates an
IPsec+BGP tunnel to a StrongSwan/BIRD NVA simulating on-premises.

```
                12 spoke VNets (48× /24, 6 summary blocks)
                              |
                         [ hub-us ]  westus2  192.168.0.0/23
                           /       \
               inter-hub (branch-to-branch, +65520 65520 in AS_PATH)
                         /            \
   🔒 [ hub-eu1 ]  swedencentral       🔒 [ hub-eu2 ]  westeurope
      192.168.2.0/23                      192.168.4.0/23
      AzFW Standard + RI PrivateTraffic   AzFW Standard + RI PrivateTraffic
      vpngw-eu1  ASN 65515                vpngw-eu2  ASN 65515
      summarize-out (6 rules)             summarize-out (6 rules) + prepend-in
           |  IPsec+BGP (xfrm41/42)             |  IPsec+BGP (xfrm41/42)
      [ nva1 ]  10.200.0.4              [ nva2 ]  10.201.0.4
      ASN 65001 (on-prem sim)           ASN 65002 (on-prem sim)
```

Diagram source: [diagrams/01-topology.drawio](diagrams/01-topology.drawio)

---

<details>
<summary><strong>Deployed resource inventory</strong> (click to expand)</summary>

- **Resource group:** `routemap-test-rg` — subscription `<SUBSCRIPTION_ID>`
- **Virtual WAN:** `vwan-routemap` (Standard, branch-to-branch enabled)

| Resource | Name | Region | Phase |
|---|---|---|---|
| Virtual WAN | `vwan-routemap` | global | 1 |
| Virtual hubs | `hub-us`, `hub-eu1`, `hub-eu2` | westus2 / swedencentral / westeurope | 1 |
| Spoke VNets (12 baseline + 6 scale) | `spoke-us-{a,b,c,d,e,f}` + `*2` variants | westus2 | 1 |
| VPN gateways | `vpngw-eu1`, `vpngw-eu2` (ASN 65515 each) | swedencentral / westeurope | 1 |
| VPN connections (on-prem) | `cx-onprem1` (eu1), `cx-onprem2` (eu2) | — | 1 |
| NVAs | `nva1`, `nva2` (Ubuntu 24.04, B2ts_v2) | swedencentral / westeurope | 1 |
| Route maps | `summarize-out` (eu1, eu2), `prepend-in` (eu2) | — | 1 |
| ExpressRoute circuits | `er-eu1`, `er-eu2` (Standard) | swedencentral / westeurope | 2 |
| ER gateways | `ergw-eu1`, `ergw-eu2` | swedencentral / westeurope | 2 |
| ER connections | `conn-er-eu1` (ergw-eu1), `conn-er-eu2` (ergw-eu2) — both `Succeeded` | — | 2 |
| VPN sites (GCP) | `site-gcp1`, `site-gcp2` | swedencentral / westeurope | 2 |
| VPN connections (GCP) | `cx-gcp1` (vpngw-eu1), `cx-gcp2` (vpngw-eu2) | — | 2 |
| Key Vault private endpoint | `kv-pe` | swedencentral | 2 |
| Firewall Policy | `azfwpol-routemap-lab` (Standard) | swedencentral | 3 |
| Azure Firewalls | `azfw-eu1`, `azfw-eu2` (Standard, AZFW_Hub) | swedencentral / westeurope | 3 |
| Routing Intent | `hub-eu1-ri`, `hub-eu2-ri` (PrivateTraffic) | swedencentral / westeurope | 3 |
| **Megaport MCR2** | `jomore-copilot-mcr-routemap2` (Milan, locationId=85) | Equinix MI1 | 2 |
| Megaport VXCs | `jomore-copilot-vxc-er-eu1-mcr2`, `jomore-copilot-vxc-er-eu2-mcr2`, `jomore-copilot-vxc-mcr-gcp` | — | 2 |

Full live inventory (2026-07-30): [show-output/08](show-output/08-phase3-audit-resource-inventory.txt)

</details>

<details>
<summary><strong>Route-map summarization scheme</strong> (click to expand)</summary>

Each `summarize-out` rule: `matchCondition: Contains` on the summary prefix → `type: Replace` →
output the same aggregate. `next-step: Continue` on all rules.

| Rule | Summary advertised | Contributing spoke VNets |
|---|---|---|
| sum1 | `10.0.0.0/16` | spoke-us-a, spoke-us-a2 (8× /24) |
| sum2 | `10.1.0.0/16` | spoke-us-b, spoke-us-b2 (8× /24) |
| sum3 | `10.2.0.0/16` | spoke-us-c, spoke-us-c2 (8× /24) |
| sum4 | `10.3.0.0/16` | spoke-us-d, spoke-us-d2 (8× /24) |
| sum5 | `10.4.0.0/17` | spoke-us-e, spoke-us-e2 (8× /24) |
| sum6 | `10.4.128.0/17` | spoke-us-f, spoke-us-f2 (8× /24) |

`hub-eu2` also carries `prepend-in` (inbound on cx-onprem2): adds ASNs `64496 64497 64498` to
routes received from nva2 before propagating them intra-hub. Effect is hub-internal; nva2's own
BIRD RIB does not show the prepended paths.

</details>

<details>
<summary><strong>Evidence index — all 52 show-output files</strong> (click to expand)</summary>

### Baseline / Phase 1 (files 01–12)

| File | Demonstrates |
|---|---|
| [01](show-output/01-resource-list.txt) | Full resource list at baseline |
| [02](show-output/02-nva1-ipsec-bgp-status.txt) | nva1: IPsec SAs + BGP status + route count (baseline, no route-map) |
| [03](show-output/03-nva2-ipsec-bgp-status.txt) | nva2: IPsec SAs + BGP status + route count (baseline) |
| [04](show-output/04-nva1-as-path-baseline.txt) | nva1: AS_PATH analysis pre route-map (`65515 65520 65520` pattern) |
| [05](show-output/05-nva1-summaries-after-routemap.txt) | nva1: BIRD RIB after `summarize-out` applied — 6 summaries visible |
| [06](show-output/06-both-hubs-baseline-clean.txt) | Both hubs: steady-state comparison at baseline |
| [07](show-output/07-repro-attempts-negative.txt) | Phase 1 repro attempts (rule reorder, 3 failover/failback cycles, scale to ~670 routes) — all CLEAN |
| [08](show-output/08-phase3-audit-resource-inventory.txt) | Full resource inventory audit (2026-07-30, pre-Phase 3 start) |
| [09](show-output/09-phase3-audit-firewalls-and-routing-intent.txt) | Phase 3 NOT yet started: all hubs azureFirewall=null, no RI |
| [10](show-output/10-phase2-audit-er-and-gateways.txt) | Phase 2 ER audit — initial (incorrect `connections` field query) |
| [11](show-output/11-phase2-er-connections-corrected.txt) | Phase 2 ER corrected: `conn-er-eu1`/`conn-er-eu2` both `Succeeded` |
| [12](show-output/12-failover-failback-cycle4-nva2.txt) | Failover/failback cycle #4 (Phase 2 state, nva2 only) — CLEAN 6/6 |

### Phase 3 Gate A — initial run + API gap finding (files 13–21)

| File | Demonstrates |
|---|---|
| [13](show-output/13-phase3-gate-a-l1a-hub-secured-state.txt) | L1a: both hubs secured (azfw ≠ null), RI = [] (Gate A pre-condition) |
| [14](show-output/14-phase3-gate-a-l1e-firewall-provisioning.txt) | L1e: azfw-eu1 + azfw-eu2 provisioningState = Succeeded |
| [15](show-output/15-phase3-gate-a-l1c-routemap-state.txt) | L1c: `summarize-out` + `prepend-in` route-maps all Succeeded, 6 rules each |
| [16](show-output/16-phase3-gate-a-l1d-defaultroutetable-diff.txt) | L1d: defaultRouteTable diff — no `_policy_PrivateTraffic` (RI not yet enabled) |
| [17](show-output/17-phase3-gate-a-l1b-get-outbound-routes-api-limitation.txt) | **API GAP**: `get-outbound-routes` returns empty / HTTP 404 for secured hubs — L2 BIRD is authoritative fallback |
| [18](show-output/18-phase3-gate-a-nva1-extension-stuck-finding.txt) | nva1 run-command extension stuck (Conflict/409) — diagnostic + impact |
| [19](show-output/19-phase3-gate-a-nva2-xfrm-restore-tunnel-initiation.txt) | nva2 XFRM interface restore + IPsec tunnel initiation procedure |
| [20](show-output/20-phase3-gate-a-l2-nva2-bird-rib.txt) | L2 nva2 BIRD RIB — Gate A initial: 6/6 summaries, 0 /24 leaks |
| [21](show-output/21-eod-nva-deallocate.txt) | End-of-day NVA deallocation (2026-07-30) |

### Phase 3 Gate A — full re-run (files 22–30)

| File | Demonstrates |
|---|---|
| [22](show-output/22-phase3-nva-restart-restore.txt) | Tank: nva1 `az vm redeploy` (~90 min) + both NVAs XFRM+BGP restore |
| [23](show-output/23-gate-a-full-nva1-bgp-protocols.txt) | nva1 `birdc show protocols` — vpngw0+vpngw1 Established (Gate A full re-run) |
| [24](show-output/24-gate-a-full-nva2-bgp-protocols.txt) | nva2 `birdc show protocols` — vpngw0+vpngw1 Established |
| [25](show-output/25-gate-a-full-nva1-bird-rib.txt) | **PRIMARY** nva1 full BIRD RIB — Gate A: 6/6 summaries, 0 /24 leaks |
| [26](show-output/26-gate-a-full-nva2-bird-rib.txt) | **PRIMARY** nva2 full BIRD RIB — Gate A: 6/6 summaries, 0 /24 leaks |
| [27](show-output/27-gate-a-full-nva1-route-count.txt) | nva1 route count: 37 routes / 27 networks |
| [28](show-output/28-gate-a-full-nva2-route-count.txt) | nva2 route count: 37/27 |
| [29](show-output/29-gate-a-full-get-outbound-routes-api-gap.txt) | API gap re-confirmed with correct `--resource-uri` syntax — still empty |
| [30](show-output/30-gate-a-full-firewall-state-and-ri-check.txt) | L1e AzFW Succeeded + RI = [] both hubs (re-confirmed for Gate A full) |

### Phase 3 Gate B — RI on hub-eu1 (files 31–39)

| File | Demonstrates |
|---|---|
| [31](show-output/31-gate-b-hub-eu1-routetable-PRE-ri.txt) | hub-eu1 defaultRouteTable snapshot **before** RI (Tank, rollback reference) |
| [32](show-output/32-gate-b-hub-eu1-ri-enable.txt) | RI enablement on hub-eu1 (`routing-intent create`, Succeeded) |
| [33](show-output/33-gate-b-hub-eu1-routetable-POST-ri.txt) | hub-eu1 defaultRouteTable **after** RI: `_policy_PrivateTraffic` present (RFC1918 → azfw-eu1) |
| [34](show-output/34-gate-b-nva2-bgp-protocols.txt) | nva2 BGP protocols — Established (RI-off hub-eu2, Gate B control) |
| [35](show-output/35-gate-b-nva2-bird-rib.txt) | **PRIMARY** nva2 BIRD RIB — Gate B: 6/6, 0 leaks (RI-off hub control) |
| [36](show-output/36-gate-b-nva2-route-count.txt) | nva2 route count: 37/27 (unchanged) |
| [37](show-output/37-gate-b-nva1-bgp-protocols.txt) | nva1 BGP protocols — Established (RI-ON hub-eu1); timestamps unchanged since Gate A |
| [38](show-output/38-gate-b-nva1-bird-rib.txt) | **PRIMARY** nva1 BIRD RIB — Gate B: 6/6, 0 leaks on RI-ON hub |
| [39](show-output/39-gate-b-nva1-route-count.txt) | nva1 route count: 37/27 (unchanged) |

### Phase 3 Gate C — RI on BOTH hubs (files 40–52)

| File | Demonstrates |
|---|---|
| [40](show-output/40-gate-c-hub-eu2-routetable-PRE-ri.txt) | hub-eu2 defaultRouteTable **before** RI (Tank, rollback reference) |
| [41](show-output/41-gate-c-hub-eu2-ri-enable.txt) | RI enablement on hub-eu2 (Succeeded) |
| [42](show-output/42-gate-c-hub-eu2-routetable-POST-ri.txt) | hub-eu2 defaultRouteTable **after** RI: `_policy_PrivateTraffic` present |
| [43](show-output/43-gate-c-l1a-hub-secured-state-both-hubs.txt) | L1a: both hubs secured + RI Succeeded (Gate C full state) |
| [44](show-output/44-gate-c-l1c-routemap-state.txt) | L1c: `summarize-out` Succeeded on both hubs; `prepend-in` intact on hub-eu2 |
| [45](show-output/45-gate-c-l1d-defaultroutetable-both-hubs.txt) | L1d: both defaultRouteTables carry `_policy_PrivateTraffic` (RFC1918 → AzFW) |
| [46](show-output/46-gate-c-l1e-firewall-state.txt) | L1e: azfw-eu1 + azfw-eu2 both Succeeded |
| [47](show-output/47-gate-c-nva2-bgp-protocols.txt) | nva2 BGP — Established (hub-eu2 newly RI-ON) |
| [48](show-output/48-gate-c-nva2-bird-rib.txt) | **PRIMARY — GATE C KEY EVIDENCE** nva2 BIRD RIB: 6/6 summaries, 0 leaks, RI-ON |
| [49](show-output/49-gate-c-nva2-route-count.txt) | nva2 route count: 37/27 (identical to Gate A) |
| [50](show-output/50-gate-c-nva1-bgp-protocols.txt) | nva1 BGP — Established; session timestamps unchanged from Gate A (BGP never reset across A→B→C) |
| [51](show-output/51-gate-c-nva1-bird-rib.txt) | **PRIMARY — GATE C KEY EVIDENCE** nva1 BIRD RIB: 6/6 summaries, 0 leaks, both hubs RI-ON |
| [52](show-output/52-gate-c-nva1-route-count.txt) | nva1 route count: 37/27 (stable across entire Phase 3) |

### Teardown (files 50–52, teardown series — concurrent with Gate C files)

| File | Demonstrates |
|---|---|
| [50-teardown](show-output/50-teardown-er-conn-fw.txt) | Step 1: ER connections deleted (conn-er-eu1/eu2 ✅), Routing Intent deleted (hub-eu1-ri/eu2-ri ✅), Azure Firewalls deleted (azfw-eu1/eu2 ✅); Provider-owned ER peerings deferred |
| [51-teardown](show-output/51-teardown-megaport.txt) | Step 3: Megaport teardown — `DELETE` endpoint failed (wrong method); retried with `POST /action/CANCEL_NOW` → all 3 VXCs + MCR2 DECOMMISSIONED; final verification 16:12 confirms all `jomore-copilot-*` products gone |
| [52-teardown](show-output/52-teardown-er-peering.txt) | Step 2: ER private peerings deleted on er-eu1 + er-eu2 ✅ |
| [53-teardown](show-output/53-teardown-azure-rg.txt) | Step 4: `az group delete -n routemap-test-rg` — exit 0, ~39 min; verified ResourceGroupNotFound post-delete; includes VWAN, hubs, firewalls, ER circuits, gateways, spokes, NVAs |
| [54-teardown](show-output/54-teardown-gcp-interconnect.txt) | Step 5: GCP project `vwan-routemap-lab` lifecycle = `DELETE_REQUESTED`; Compute APIs return 404; billing stopped; no per-resource deletion required |

</details>

<details>
<summary><strong>Gate D — concurrent-churn experiment (DORMANT, not yet run)</strong> (click to expand)</summary>

The sequential stable-state methodology leaves one hypothesis untested: the production bug may
require **concurrent churn** — a VPN connection reconvergence racing with RI provisioning on the
same hub. If the hub recomputes its per-connection outbound advertisement set while the NVA's BGP
session is simultaneously tearing down, the /24 specifics may be transiently absent from the
route-map evaluation input; a cached zero-match result would persist after reconvergence.

**Gate D is DORMANT — do not run until Jose says "run Gate D."**

Concise step sequence (Tank + Niobe, ~45 min, ~$0.10 incremental):
1. Confirm 6/6 baseline (Gate C state).
2. Niobe: start BIRD RIB poll on nva2 every 30 s.
3. Tank: `sudo swanctl --terminate` on nva2 to tear down IPsec.
4. Tank (concurrently, < 30 s later): delete + recreate hub-eu2 RI.
5. Niobe: continue polls through reconvergence; re-initiate tunnels after RI Succeeded.
6. **Repro signal:** a summary still absent from nva2 BIRD RIB after vpngw0+vpngw1 re-establish
   AND RI Succeeded. Transient miss during churn = noise; persistent miss = customer bug reproduced.

Full step-by-step specification: [design-phase3.md § Gate C Result + Gate D Proposal](design-phase3.md#gate-c-result--gate-d-proposal-concurrent-churn)

</details>

---

## Round 1 teardown status (2026-07-31)

> Teardown sequence: ER connection → RI + AzFW → ER private peering → Megaport VXC/MCR (CANCEL_NOW) → Azure RG → GCP Interconnect.

| Step | Action | Status | Evidence |
|---|---|---|---|
| 1a | Delete ER gateway connections (conn-er-eu1, conn-er-eu2) | ✅ DONE | [50-teardown](show-output/50-teardown-er-conn-fw.txt) |
| 1b | Delete Routing Intent (hub-eu1-ri, hub-eu2-ri) | ✅ DONE | [50-teardown](show-output/50-teardown-er-conn-fw.txt) |
| 1c | Delete Azure Firewalls (azfw-eu1, azfw-eu2) | ✅ DONE | [50-teardown](show-output/50-teardown-er-conn-fw.txt) |
| 2 | Delete ER private peering (er-eu1, er-eu2) | ✅ DONE | [52-teardown](show-output/52-teardown-er-peering.txt) |
| 3 | CANCEL_NOW Megaport VXCs (vxc-er-eu1-mcr2, vxc-er-eu2-mcr2, vxc-mcr-gcp) + MCR2 | ✅ DONE — all DECOMMISSIONED (16:12 verified) | [51-teardown](show-output/51-teardown-megaport.txt) |
| 4 | Delete Azure resource group `routemap-test-rg` | ✅ DONE — RG deleted, exit 0 (~39 min, ended 17:22); `az group show` + `az network express-route list` both return ResourceGroupNotFound | [53-teardown](show-output/53-teardown-azure-rg.txt) |
| 5 | GCP project `vwan-routemap-lab` cleanup | ✅ DONE — project in `DELETE_REQUESTED` state; all Compute APIs return 404; billing stopped; auto-purge within 30 days | [54-teardown](show-output/54-teardown-gcp-interconnect.txt) |

### Megaport teardown method (for the lab record)

`DELETE /v3/product/<uid>` is not a valid Megaport API endpoint — it returns `"No endpoint DELETE…"`.
The correct method is `POST /v3/product/{uid}/action/CANCEL_NOW` (immediate termination).
Link applied this to all 3 VXCs and MCR2; final verification at 2026-07-31T16:12:00+02:00 confirms
every `jomore-copilot-*` product DECOMMISSIONED. No manual portal action was needed.

---

*Last updated: 2026-07-31 | Trinity (Azure Network SME)*

</details>

---

*Round 2 last updated: 2026-08-18 | mixed-origin attribute-inheritance repro + mitigation validation.*
