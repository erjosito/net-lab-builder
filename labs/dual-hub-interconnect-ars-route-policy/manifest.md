# manifest.md — TP-HH: Dual-Hub Interconnect and Route Server Route-Map Policy

## Lab card

| Field | Value |
|---|---|
| Slug | `dual-hub-interconnect-ars-route-policy` |
| Test program | **Stage 1 — `TP-HH`** — composition of retained `US10-bow-tie-dual-site-regional-affinity` + `US11-hub-to-hub-without-nva-overlay` |
| Roadmap | **Two stages.** Stage 1 = TP-HH (executable under existing gates). **Stage 2 = `TP-SQ`**, the `US12-square-hybrid-connectivity` feasibility study — **written, gated, not executed**. See §Stage 2 below and `design.md` §9–§13 |
| Regions in scope | `swedencentral` (hub1), `switzerlandnorth` (hub2) |
| Adjacent/read-only | `norwayeast` (`vnet-onprem`) |
| Out of scope | `polandcentral` (`ars-poland`, set-C spokes) — entirely |
| Reused SKUs | ARS Standard (both hubs, route-map tier active), `VpnGw1AZ` gateways, **`Standard_B2ts_v2`** for all five VMs (corrected from `B2als_v2`/`B2s_v2` against live state, 2026-08-05 — see §Live-state reconciliation) |
| Reused ASNs | `vpngw-hub1`/`vpngw-hub2` = 65515, `vm-nva1` = 65001, `vm-nva2` = 65002, `vpngw-onprem` = 65000 |
| Address plan (in scope) | `10.10.0.0/16` (hub1), `10.11.0.0/24` (spoke-a), `10.20.0.0/16` (hub2), `10.21.0.0/24` (spoke-b) |
| Address plan (adjacent/read-only) | `10.40.0.0/16` (`vnet-onprem`) |
| Address plan (excluded) | `10.30.0.0/24` (`ars-poland`), `10.31.0.0/24`, `10.32.0.0/24` (set-C) — never a topology dependency here |
| Status | **Nothing deployed or changed by this lab.** All resources reused from the source lab. |

## Ownership contract (reproduced verbatim)

> **Shared live resources — reused, not created.** Every Azure resource this lab exercises was
> deployed by, is documented by, and remains owned by
> [`labs/dual-hub-hubless-region-ars`](../dual-hub-hubless-region-ars/README.md) (resource group
> `rg-dual-hub-hubless-region-ars-lab3d001`, deployed 2026-08-03, certified 2026-08-04). This lab
> creates **no** long-lived resource and holds **no** deployment code.
>
> **Cost.** The running cost of the bed (≈ $84/day, including three irreversible Azure Route Server
> route-map-tier surcharges) is accounted against the original lab. This lab's own cost delta is
> effectively zero: a VNet peering carries no hourly charge, and only inter-region data transfer is
> billed. Any scenario that would create a billable resource (T3's tunnel endpoints, if ever built)
> requires a fresh, explicit cost approval from Jose Moreno before execution.
>
> **Cleanup authority.** Teardown of the shared bed is governed **solely** by
> `../dual-hub-hubless-region-ars/manifest.md` §6 (Cleanup Sequence) and by Jose's Phase-8 approval
> gate. This lab may only roll back its **own** additive deltas (the hub↔hub peering pair, any
> route-map association, any NVA BGP/tunnel configuration) and must leave the original lab's
> certified state byte-comparable to its pre-change baseline. Ownership transfers to this lab only
> if a decision recorded in `.squad/decisions.md` says so explicitly; until then, the original lab
> is the single source of truth for inventory, cost and cleanup.
>
> **No cleanup command in this lab's `scripts/` may target the shared resource group.**
> `scripts/rollback.ps1` only ever reverses this lab's own additive deltas (peering, route-map
> association) — it never deletes, recreates, or tears down `rg-dual-hub-hubless-region-ars-lab3d001`.

## Reused resource ledger — reused, not created

| Resource | Type | Source lab role |
|---|---|---|
| `vnet-hub1` | VNet | hub1, swedencentral |
| `vnet-hub2` | VNet | hub2, switzerlandnorth |
| `vnet-spoke-a` | VNet | spoke, swedencentral |
| `vnet-spoke-b` | VNet | spoke, switzerlandnorth |
| `ars-hub1` | Azure Route Server | route-map tier active (inert), hub1 |
| `ars-hub2` | Azure Route Server | route-map tier active (inert), hub2 |
| `vpngw-hub1` | VPN Gateway | AS 65515, hub1 |
| `vpngw-hub2` | VPN Gateway | AS 65515, hub2 |
| `vm-nva1` | NVA (BIRD) | `10.10.1.4`, AS 65001 — **deallocated** (2026-08-05) |
| `vm-nva2` | NVA (BIRD) | `10.20.1.4`, AS 65002 — **deallocated** (2026-08-05) |
| `vm-hub1-ep` | Endpoint VM | spoke-a workload probe — **deallocated**; not needed by any Stage-1 unit |
| `vm-hub2-ep` | Endpoint VM | spoke-b workload probe — **deallocated**; not needed by any Stage-1 unit |
| `rt-spoke-a`, `rt-spoke-b` | Route tables | single UDR each: `0.0.0.0/0 → 10.10.1.4` / `→ 10.20.1.4`, `VirtualAppliance` |
| hub↔spoke peerings (both hubs) | VNet peering | pre-existing — `peer-hub1-to-spoke-a`, `peer-hub2-to-spoke-b` (`Connected`/`FullyInSync`, `AllowGatewayTransit=true`) |
| `rm-hub1-activate`, `rm-hub2-activate` | ARS route maps | **unassociated and functionally inert — but not empty.** Each carries one rule `rule-activate-synthetic`: match `routePrefix Equals ["192.0.2.0/24"]` → action `Add asPath ["64496"]` → `Terminate`. Created solely to trigger the irreversible route-map tier upgrade. `associatedInbound/OutboundConnections` = `[]` |

*Adjacent/read-only, referenced not owned:* `vnet-onprem`, `vpngw-onprem` (AS 65000).

*Explicitly not reused/not in scope:* `ars-poland`, `vnet-poland-ars`, `vnet-spoke-c1`,
`vnet-spoke-c2`, `vm-c1-ep` — **all deleted 2026-08-05** (Poland cleanup, 29/29 objects).

## Live-state reconciliation — read-only capture 2026-08-05 (post-Poland cleanup)

Verified with `az … show/list`, `az network …/list-learned-routes`, `list-advertised-routes`,
`list-bgp-peer-status`, and `az rest --method get` (api-version `2024-10-01`). Nothing was mutated.
Full record: `.squad/decisions/inbox/trinity-bowtie-activation-plan.md` §1.

| Instrument | Live value | Consequence for TP-HH |
|---|---|---|
| `vnet-hub1`↔`vnet-hub2` peering | **does not exist** — hub1 has only `peer-hub1-to-spoke-a`, hub2 only `peer-hub2-to-spoke-b` | T1/U1's premise confirmed live |
| All 5 VMs | **`VM deallocated`**, all `Standard_B2ts_v2` | **U0 is a hard prerequisite**, not a convenience |
| `ars-hub1 peer-nva1` learned **and** advertised | `{"RouteServiceRole_IN_0": [], "RouteServiceRole_IN_1": []}` | ARS↔NVA sessions **down**; every "byte-comparable learned set" criterion is unevaluable today |
| `vpngw-hub1`/`hub2` BGP peers | `10.40.0.4/.5` (AS 65000) `Connected`, 1 route each; ARS instances `Connecting` | hub↔on-prem tunnels healthy; ARS↔gateway not established |
| `vpngw-onprem list-learned-routes` | only `10.40.0.0/16` + BGP-peer `/32`s | on-prem learns **no** hub or spoke prefix right now |
| `vpngw-hub1 list-advertised-routes --peer 10.40.0.4` | **empty** | hub1 advertises nothing to on-prem in the quiescent state |
| 4 VPN connections | all `Connected`, 4 tunnels each, `routingConfiguration: {}` | see U4 — no ARS↔gateway connection object is exposed |
| `bgpConnections/peer-nva1`,`peer-nva2` | `routingConfiguration` contains **only** `vnetRoutes` | no route map is associated anywhere; association property is absent, not null |
| `rm-hub*-activate` | `Succeeded`, `associatedInboundConnections: []`, one unmatchable rule | **not empty** — see ledger row above |
| `nsg-nva-hub1`/`hub2` | TCP/179 allowed only from the **local** hub `/16`; ICMP + TCP/22 from `10.0.0.0/8`; deny-all at 4000 | `10.10.1.4 ↔ 10.20.1.4` **ICMP needs no NSG change**; an NVA↔NVA **BGP** session (T3/U5) **does** |
| Spoke UDRs | `0/0 → 10.10.1.4` / `→ 10.20.1.4` while both NVAs are deallocated | spoke default route is **black-holed today**; U0 restores it |

**BIRD — live check PENDING (VMs may only be started after approval).** Last captured state
(`show-output/inherited/current-state-2026-08-04/`): BIRD 2.0.8, 16 routes / 10 networks, sessions
`ars_hub*_0/1` and `ars_poland_0/1` all `Established`. Two facts follow:

1. **Route-refresh capability was never captured.** Only `birdc show protocols` (short form) exists
   in either lab; `show protocols all` — the only output that prints the RFC 2918 capability — was
   never taken. BIRD 2.x enables route refresh by default and neither cloud-init disables it, so a
   *soft* refresh is expected, **but this is documentary, not measured**. It must be captured in U0
   before U1 executes.
2. **Both `bird.conf` files still define `ars_poland_0/1` toward `10.30.0.4`/`10.30.0.5`.** Those
   targets and their VNet are deleted, so on restart those two protocols sit in `Connect`/`Active`
   permanently, and `10.30.0.0/24`, `10.31.0.0/24`, `10.32.0.0/24` **never
   reappear**. The Δ2 control signature `65002-65002-65002` at `ars-hub2` is therefore
   **permanently gone** and is retired as a "must not move" criterion — replaced everywhere by a
   fresh post-U0 baseline. BIRD config is hand-edited on the OS disks and is **not** in version
   control; the current on-disk `bird.conf` must be captured before any T4/U5 edit.
   **Correction (2026-08-06, `TANK-001`):** the stray static `route 10.30.0.0/27` **does** reappear
   — it is a `protocol static` route on both NVAs, and the export filters key on AS-PATH, not
   prefix, so it is genuinely re-originated into both Route Servers. It is contained (never reaches
   the gateways or on-prem) and is removed by the new prerequisite unit **U1.5**. The
   "not in version control" gap is closed by `nva-config/` — as-found snapshots plus U1.5 targets —
   which U1.5 makes authoritative.

## Bounded proxy versus the full bow-tie — scope honesty

**Regional affinity cannot be proven with the current topology.** A bow-tie needs *two* on-premises
sites, each with affinity to its nearest hub plus a cross-region backup. This bed has **one** site
(`vnet-onprem`, norwayeast, AS 65000) **dual-homed to both hubs**.

| | Bounded proxy — Stage 1 delivers this | Full bow-tie — Stage 1 cannot deliver this |
|---|---|---|
| Topology | 1 site × 2 hubs | 2 sites × 2 hubs |
| Claim | **hub-path preference** for a single dual-homed site | **site-to-nearest-hub affinity**, per site |
| Failover | bounded, one site | per-site failover onto the other region's hub |
| Missing | — | `vnet-onprem2` (`10.50.0.0/16`), `vpngw-onprem2` (`VpnGw1AZ`, AS 65003 — **$0.21/hr ≈ $5.04/day** retail swedencentral), S-C connection pair, 1 probe VM |
| Governance | Stage 1, existing gates | **Stage 2 / TP-SQ**, gates G1–G4, fresh cost approval G3 |

Stage 1's deliverable is therefore the **"single-site dual-homed hub-preference proxy"**: hub↔hub
peering carriage and non-carriage (U1), route-map association feasibility (U2), and single-prefix
attribute modification (U3). It must never be written up as "bow-tie validated"; the bow-tie verdict
stays *not determined* until Stage 2.

## Phase-4 approval units U0–U5 — Stage 1 activation ledger

Each unit is independently approvable, independently reversible, and maps onto the T-scenarios
above. Placeholders: `<RG>` = `rg-dual-hub-hubless-region-ars-lab3d001`; `<SUBSCRIPTION_ID>` is set
by `az account set` at execution time and never appears in this repository. Full detail:
`.squad/decisions/inbox/trinity-bowtie-activation-plan.md` §3.

| Unit | Scenario | Exact resource change | Timing | Cost delta | Blast radius | Rollback |
|---|---|---|---|---|---|---|
| **U0** | prerequisite | `az vm start` on **`vm-nva1`** + **`vm-nva2`** only — power state, nothing else. Endpoint VMs stay deallocated | 1–3 min boot each; BGP up 30–90 s after boot; **wait 10 min** before baseline | **+$0.024/hr = +$0.58/day** (`$0.0108` sweden + `$0.0132` switzerland, retail USD 2026-08-05). Disks/PIPs already billed | `vnet-hub1`+`vnet-hub2` effective routes and the hub→on-prem advertisement set. **Not a no-op**: BIRD re-originates `0.0.0.0/0` and the RouteServerSubnet `/27` into both ARS | `az vm deallocate` ×2 — 2–5 min, exact return to today's state |
| **U1** | T1 | Create **exactly two** objects: `vnet-hub1/virtualNetworkPeerings/peer-hub1-to-hub2` and `vnet-hub2/virtualNetworkPeerings/peer-hub2-to-hub1`; `AllowVirtualNetworkAccess=true`, `AllowForwardedTraffic=true`, `AllowGatewayTransit=false`, `UseRemoteGateways=false` on both | 30–90 s per object; `Connected`/`FullyInSync` ≤ 2 min; convergence polls 30/60/120/180 s | **$0/hr**. Global VNet peering data transfer `$0.04/GB` egress + `$0.04/GB` ingress → **≈$0.00** for an ICMP probe | hub VNet effective routes only. No gateway, connection, spoke or on-prem object touched | `az network vnet peering delete` ×2 — 30–60 s each, second maintenance window |
| **U1.5** | prerequisite (new, `TANK-001`) | **BIRD config only — no Azure object created, modified or deleted.** On `vm-nva1` and `vm-nva2` remove the retired Poland state: static `route 10.30.0.0/27`, `protocol bgp ars_poland_0`/`ars_poland_1`, `filter export_to_poland_ars`, and (nva2 only) the dead `10.31.0.0/24`/`10.32.0.0/24` prepend clause inside `export_to_hub2_ars`. Applied with **`birdc configure`** (graceful), never `systemctl restart bird`. Contract: `nva-config/README.md` | ~25–40 min total, dominated by `az vm run-command invoke` latency (1.5–3 min/call). `vm-nva1` first, fully verified, then `vm-nva2` | **$0** | control plane of `ars-hub1`/`ars-hub2` only. **Exactly one prefix moves**: `10.30.0.0/27` is withdrawn from both instances of both Route Servers. Gateways and on-prem never saw it, so they must stay byte-identical | `birdc configure undo`, or restore `/etc/bird/bird.conf.pre-u15.<STAMP>` + `birdc configure`; second source in version control at `nva-config/bird-nva{1,2}.as-found-2026-08-06.conf` — **<2 min per NVA** — **EXECUTED 2026-08-06, PASS on both NVAs, not rolled back (no trigger met)** |
| **U2** | T2a (hub1 **only**) | Create `ars-hub1/routeMaps/rm-hub1-tmp-assoc` (1 object, rule matches **`203.0.113.0/24`**) + **PUT** `ars-hub1/bgpConnections/peer-nva1` with `properties.routingConfiguration.inboundRouteMap.id`. **PUT body must be derived from a fresh GET and must preserve `routingConfiguration.vnetRoutes` including `staticRoutesConfig`** — PUT replaces `properties` wholesale. `rm-hub1-activate` and all of `ars-hub2` untouched | map create 1–3 min; association PUT 1–3 min. **No 30-min upgrade** (already done on `ars-hub1`). ~20–30 min end to end | **$0** — the route-map tier surcharge is per-Route-Server, already sunk and irreversible | `ars-hub1`↔NVA1 control plane. A session reset costs `vnet-hub1` its ARS-injected routes for the reset duration; `rt-spoke-a`'s static UDR is unaffected | PUT the saved pre-U2 GET body back (minus `provisioningState`, without `inboundRouteMap`), then DELETE the temp map — 2–5 min — **EXECUTED 2026-08-06, PASS, association LEFT ACTIVE (not rolled back — required precondition for U3a/U3b)** |
| **U3a** | T2b step 1 | **BIRD config only, `vm-nva1` only.** Add `protocol static u3_doc_test { ipv4; route 198.51.100.0/24 blackhole; }` and `birdc configure`. Creates the harmless, actually-advertised target U3b needs. Snippet: `nva-config/bird-nva1.u3a-doctest.snippet.conf` | 5–10 min + 10 min settle before baseline **B3** | **$0** | one new prefix in `ars-hub1`'s RIB, AS-PATH `65001`. Containment (absent from both gateways and on-prem) is part of U3a's own PASS criteria | Remove the block, `birdc configure` (or `birdc configure undo`) — <2 min |
| **U3b** | T2b step 2 | Update `rm-hub1-tmp-assoc` to one rule: match `routePrefix Equals ["198.51.100.0/24"]` → `Add asPath ["64496","64496"]` → `Terminate` | 1–3 min; re-advertisement within seconds, bounded by the 180 s ARS hold. U3a+U3b ~30–45 min | **$0** | one non-routable documentation prefix's AS-PATH inside `vnet-hub1`'s ARS RIB | PUT the map back to the unmatchable `203.0.113.0/24` rule (→ U2 state), then roll back U3a — 2–5 min. **Order: U3b before U3a** |
| **U4** | T5 | **Step 1 only (zero-write):** enumerate ARS → *route maps* → **Apply route maps** verbatim; record `Get-Module -ListAvailable Az.Network`. Step 2 (write) proposed only if Step 1 shows an eligible same-VNet gateway connection | Step 1: minutes, read-only | **$0** | Step 1: none. Step 2 would touch the shared certified `vpngw-hub*`↔`vpngw-onprem` connections | Step 2 only: association back to **None** / `null`; re-verify all four connections `Connected` |
| **U5** | T3 | **Not preapproved. No commands written.** | — | — | Would require **NSG mutation on both NVA subnets** + BIRD mutation on both NVAs | — |

### U0 — why it is mandatory and what it actually changes

Every Stage-1 PASS criterion reads against ARS learned sets and BIRD session uptime; both return
empty today. U0 is the only way to make Stage-1 evidence exist. It is **not** routing-neutral:
starting the NVAs restores `0.0.0.0/0 → 10.10.1.4` / `→ 10.20.1.4` inside the hub VNets, resumes
hub→on-prem advertisement, and un-black-holes the spoke UDRs. No Poland prefix returns.

### U1.5 — new prerequisite unit (finding `TANK-001`, added 2026-08-06)

U0's evidence showed both NVAs' hand-edited `/etc/bird/bird.conf` still carry **retired Poland
state**: dead `ars_poland_0`/`ars_poland_1` BGP protocols stuck in `Connect`, their
`export_to_poland_ars` filters, and a stray static `route 10.30.0.0/27`. That static is **genuinely
re-originated** into each NVA's local Route Server, because `export_to_hub_ars`/`export_to_hub2_ars`
filter by **AS-PATH** (`bgp_path.delete(65515)`), **not by prefix** — so every `protocol static`
route leaks into ARS by construction. It is contained (absent from ARS's advertised-back set, from
both hub gateways and from `vpngw-onprem`; visible only in each NVA's own NIC effective routes) but
it is undocumented state that would pollute every subsequent byte-comparison.

U1.5 removes exactly that state and nothing else. It touches **no Azure object**, costs **$0**, and
is reversible in under two minutes per NVA. It also closes the standing "BIRD is hand-edited and not
in version control" gap: `nva-config/bird-nva{1,2}.as-found-2026-08-06.conf` is the pre-image and
`nva-config/bird-nva{1,2}.u15-target.conf` becomes authoritative afterwards. Exact removals,
backup/restore, the blocking syntax gate, graceful-reload-vs-restart semantics, the L1–L8 proof
matrix and the eight rollback triggers: **`nva-config/README.md`** and `validation.md` §U1.5.

**U1.5 is a hard prerequisite for U2 and U3**, because U2's headline PASS criterion is "the learned
set did **not** change" and U1.5 is precisely a change to the learned set.

### U2 — which map to associate, and why a temporary one is safer

`rm-hub1-activate` **is not empty**. Associating it would be functionally inert (RFC 5737 TEST-NET-1
under `Equals` cannot match any lab prefix), but U3 would then have to mutate its rule set,
destroying the provenance of the tier-activation artefact. A dedicated **`rm-hub1-tmp-assoc`** costs
$0, triggers **no** second upgrade, is deletable at rollback, and leaves `rm-hub1-activate`
byte-identical with its documented purpose intact. **Recommended.**

**Its match prefix is `203.0.113.0/24` (TEST-NET-3), not `192.0.2.0/24` (corrected 2026-08-06).**
`192.0.2.0/24` is already `rm-hub1-activate`'s match prefix; two coexisting maps on the same Route
Server keyed on the same prefix would make any observed — or absent — effect ambiguous about which
artefact caused it. Live read-only capture on 2026-08-06 confirms `203.0.113.0/24` appears nowhere
in `ars-hub1`'s learned or advertised sets, in `vm-nva1`'s BIRD `master4`, or in `vpngw-onprem`'s
learned routes, so under `Equals` **the association is inert by construction**. TEST-NET-2
`198.51.100.0/24` is reserved for U3a and must not be used here.

### U2 — verified API semantics (this supersedes the earlier PATCH wording)

1. The association property is on the **connection**:
   `virtualHubs/ars-hub1/bgpConnections/peer-nva1` → `properties.routingConfiguration.inboundRouteMap.id`.
2. `routeMaps/*.associatedInboundConnections` is a **read-only composite** — live GET returns `[]`,
   and the current `Az.Network` reference for `New-AzRouteMap`/`Update-AzRouteMap` exposes **no**
   `-InboundConnection`/`-OutboundConnection` parameter (the how-to article's prose says otherwise;
   its own Example 2 sets `InboundRouteMap` inside a **connection's** `RoutingConfiguration`). The
   lab's Δ3 finding is **confirmed correct** and must not be regressed.
3. **Verb = `PUT`, not `PATCH`** — `Microsoft.Network/virtualHubs/bgpConnections` defines no PATCH
   operation; the body must carry `peerAsn` + `peerIp` + `routingConfiguration` in full.
4. Documented fallback surface: ARS blade → *route maps* → **Apply route maps**.
5. Bodies always from file (`--body "@<path>.json"`) — inline JSON fails on Windows PowerShell.

### U2 — mandatory PUT body preservation (added 2026-08-06; the earlier placeholder was unsafe)

Because PUT **replaces `properties` wholesale, anything omitted is lost.** The live GET on
2026-08-06 returned a `routingConfiguration.vnetRoutes` that is *not* empty:

```json
"vnetRoutes": {
  "staticRoutes": [],
  "staticRoutesConfig": { "propagateStaticRoutes": true, "vnetLocalRouteOverrideCriteria": "Contains" }
}
```

The previous placeholder bodies omitted `vnetRoutes` entirely and would have silently reset
`propagateStaticRoutes` and `vnetLocalRouteOverrideCriteria` to service defaults — a routing-behaviour
change U2 has no mandate to make and no criterion that would have caught it. The body is therefore
**derived, never authored**:

1. `GET .../bgpConnections/peer-nva1?api-version=2024-10-01`; save verbatim as
   `00-pre-peer-nva1-GET.json` — this file is both evidence and rollback source.
2. Take `response.properties` exactly as returned.
3. Delete **only** the read-only member `provisioningState`.
4. Add `routingConfiguration.inboundRouteMap.id`.
5. Send `{"properties": <that object>}` — no `id`, `name`, `type` or `etag` in the body.
6. Send the GET's `etag` as `If-Match`, so a concurrent change fails the write instead of being
   silently overwritten.

`04-post-peer-nva1-GET.json` must show `vnetRoutes` and `staticRoutesConfig` unchanged. If it does
not, U2 is a **FAIL** and rolls back regardless of what the learned-route sets show.

### U3 — target prefix selection *(rewritten 2026-08-06 — the previous choice was invalid)*

| Candidate | Verdict |
|---|---|
| `0.0.0.0/0` | ⛔ spoke UDR semantics + DEF-001 evidence |
| `10.10.0.0/16`, `10.11.0.0/24` | ⛔ route maps cannot modify the VNet address space ARS advertises (Learn) |
| `10.10.1.0/27` | ⚠️ the NVA's own data path |
| `10.30.0.0/27` | ⛔ removed by U1.5; must not be resurrected to serve as a target |
| `10.40.0.0/16` | ⛔ on-prem prefix; and it is learned on `RouteServiceRole_IN_1` only, so any diff is instance-asymmetric and unfalsifiable |
| **`10.10.0.64/27`** | ⛔ **invalid — proven unlearnable.** It is in `bird.conf` and exported identically to every other static, yet it **never appears** in `ars-hub1`'s learned set: Azure Route Server silently rejects a route matching its own RouteServerSubnet. A map keyed on it could never match; U3 would have returned `Succeeded` and proven nothing while reading as a PASS |
| **`198.51.100.0/24`** | ✅ **chosen** — RFC 5737 TEST-NET-2, globally non-routable, absent from every live surface, deliberately distinct from `192.0.2.0/24` (`rm-hub1-activate`) and `203.0.113.0/24` (U2). Does not exist yet, so **U3a injects it into `vm-nva1`'s BIRD as `blackhole`** — BGP-visible, incapable of carrying traffic — and U3b modifies it |

**ASN `64496`** is the RFC 5398 2-byte documentation ASN: not private (`64512`–`65534`), not on
Azure's reserved list (`8074`, `8075`, `12076`, `65515`, `65517`–`65520`), and from the same block as
`64511` used in Microsoft's own prepend walkthrough. **Never** substitute `65001`/`65002`/`65000`/
`65515` — those are live in this bed.

Softer alternative if even that is judged too close to the ARS control plane: `Community Add
["64496:100"]` on the same prefix — a pure tag that cannot influence best-path selection.

**Evidence-fidelity risk, declared in advance:** it is not established whether
`az network routeserver peering list-learned-routes` reports AS-PATH after inbound route-map
processing or as received on the wire. If the change is not observable there or in the portal Route
Map dashboard while the map reports `Succeeded`, U3b is **INCONCLUSIVE — tooling visibility, not
FAIL**; U2 remains the association proof. Retrying against a production prefix to force visibility is
**forbidden**.

### U4 — why it may not be testable at all

Learn says route maps apply to *"the route server's connection to the VPN gateway in the same
virtual network."* The live model exposes no such object: `ars-hub1` has **no** connection children
beyond `bgpConnections/peer-nva1` and `routeMaps/*`; the only connection resources in the RG are the
four `Microsoft.Network/connections` gateway-to-gateway S2S pairs, whose
`VirtualNetworkGatewayConnection` schema has **no** `inboundRouteMap`/`outboundRouteMap` member and
whose live `routingConfiguration` is `{}`. If Step 1's portal enumeration shows no eligible entry,
record *"RM-C/RM-D unverifiable in this bed — no addressable ARS↔VPN-gateway connection resource"*
and close **G4** on U2's result alone.

### U5 — the precise trigger, and why it stays unapproved

U5 fires **only if** the bow-tie failover contract *requires* at least one of: (1) automatic
propagation of remote-region prefixes to the local hub/spokes with no operator action; (2) automatic
**withdrawal** within the BGP hold window on remote failure; (3) AS-PATH/community preference that
**survives the regional boundary**. If bounded failover is accepted instead, **U5 is not run and the
non-execution is the deliverable**. Additional hard prerequisites, stated so they are never
discovered mid-window: a **new TCP/179 allow rule on both `nsg-nva-hub1` and `nsg-nva-hub2`** (today
each allows 179 only from its own hub `/16`, with deny-all at 4000), a deny-by-default BIRD prefix
policy applied **before** the session comes up, and a captured copy of the current on-disk
`bird.conf` (not in version control). **Do not preapprove.**

## Recommended first tranche — Phase 4

> **STATUS 2026-08-06: U0 + U1 are EXECUTED and PASSED.** The recommendation below is retained for
> provenance; the live recommendation is now the U1.5 + U2 tranche that follows it.

> **Approve U0 + U1 only.**

- U0 is mandatory: without it there is no Stage-1 evidence, only assertions.
- U1 is the cheapest high-value unit — two free objects, headline result is a *non*-effect, deletable
  in under two minutes.
- Together they close the two prerequisites U2/U3 depend on: route-refresh capability and a fresh
  post-cleanup baseline.
- U2's continuous data-plane probe requires U1: both `snet-endpoint` subnets are empty and the
  endpoint VMs are spoke-resident, so `10.10.1.4 ↔ 10.20.1.4` is the only in-hub probe pair.

**Tranche totals:** **+$0.58/day** while the NVAs run, **≈$0.00** data transfer, **≈45–60 min** wall
clock including settle and both capture passes, **< 10 min** full rollback.

**Do not approve U1 and U2 in the same window** — U2's PASS criteria are defined against a settled,
captured U1 baseline that cannot exist yet. **Bundle at zero risk:** U4 **Step 1** (read-only).
**Do not request:** U5.

## Recommended next tranche — Phase 4, post-U0/U1 (2026-08-06)

> **Approve U1.5 + U2 as ONE tranche, executed in TWO separate maintenance windows.**

**Why one tranche.** Both are **$0**. Their blast radii do not overlap: U1.5 is NVA-side (BIRD only,
no Azure object at all), U2 is ARM-side (`ars-hub1` connection + one temporary map). Both are fully
reversible in minutes, with rollback artefacts already in version control. Approving them together
avoids a second approval round-trip for what is really one prerequisite plus one experiment.

**Why they must not share a window.** U1.5's whole purpose is to **change** the ARS learned-route
set (withdraw `10.30.0.0/27`). U2's headline PASS criterion is that the learned-route set **did not
change**. Run in one window, a U2 diff could be attributed to either unit and neither result would be
falsifiable.

**Sequence and baseline checkpoints:**

| # | Window | Unit | Baseline captured at end |
|---|---|---|---|
| 0 | — | *(already done)* U0 + U1 | **B0** = `show-output/new/u0-u1/post-u1/` |
| 1 | **Window A** | **U1.5** — `vm-nva1` first, verified, then `vm-nva2`; settle ~20 min | **B1** = `show-output/new/u15-u2/b1/` (as executed; planned path was `u15-bird-cleanup/`) — **EXECUTED 2026-08-06, PASS** |
| 2 | **Window B** | **U2** — diffed strictly against **B1**, never B0 | **B2** = `show-output/new/u15-u2/b2/` (as executed; planned path was `t2-routemap-assoc/`) — **EXECUTED 2026-08-06, PASS, association left active** |
| 3 | separate approval | **U3a** (BIRD inject) then settle 10 min | **B3** = `show-output/new/u3a-doc-prefix/` |
| 4 | same window as U3a | **U3b** (map rule), diffed against **B3**, then rolled back | — |

**Tranche totals:** **$0** incremental cost (run-rate stays at the existing +$0.58/day for the two
running NVAs), **≈45–70 min** of wall clock across the two windows, **< 5 min** rollback for either
unit independently.

**U3 is not part of this tranche** — it is approved separately, only after U2 passes.


## Delta ledger — what TP-HH creates, each with its rollback

| Delta | Scenario | Rollback | Cost |
|---|---|---|---|
| `vm-nva1` + `vm-nva2` started (power state only) | **U0** (prerequisite) | `az vm deallocate` both — 2–5 min | **+$0.58/day** while running |
| `vnet-hub1`↔`vnet-hub2` global VNet peering (both directions) | T1 / U1 | Delete both peering objects in a second maintenance window | $0/hr; inter-region egress+ingress $0.04/GB each, ≈$0.00 for an ICMP probe |
| Retired Poland BIRD state removed from `vm-nva1` + `vm-nva2` (statics, `ars_poland_*`, filters) | **U1.5** (prerequisite, `TANK-001`) | `birdc configure undo`, or restore `/etc/bird/bird.conf.pre-u15.<STAMP>`; second source at `nva-config/bird-nva{1,2}.as-found-2026-08-06.conf` — <2 min/NVA | $0 (no Azure object touched) |
| `rm-hub1-tmp-assoc` created (match `203.0.113.0/24`) + `inboundRouteMap` association on `ars-hub1`/`peer-nva1` (**hub1 only**) | T2a / U2 | PUT the **saved pre-U2 GET body** back without `inboundRouteMap` (preserving `vnetRoutes`/`staticRoutesConfig`), then delete the temp map | $0 (surcharge already sunk against source lab; no second upgrade) |
| `198.51.100.0/24` documentation prefix injected into `vm-nva1` BIRD as `blackhole` | U3a | Remove the `u3_doc_test` block + `birdc configure` — <2 min | $0 |
| AS-Path `Add` [64496, 64496] on `198.51.100.0/24` | T2b / U3b | Revert the temp map to the unmatchable `203.0.113.0/24` rule, or dissociate entirely; then roll back U3a | $0 |
| NVA-to-NVA eBGP session + conditional encapsulation | T3 (conditional — may not run) | Tear down BGP session/tunnel; restore T1-only state | $0 unless a tunnel endpoint is genuinely created (requires fresh approval) |
| Same intent expressed as a BIRD filter | T4 | Revert BIRD config from version control | $0 |
| `inboundRouteMap`/`outboundRouteMap` association on a VPN GW connection | T5 (optional, separately approved) | PATCH association back to `null`/empty | $0 |

## Cost delta

The three ARS route-map surcharges (~$6/day each = ~$12/day) are **already charged to the source
lab** as of the 2026-08-05 hub1/hub2 upgrade (see source lab `deploy-log.md` §"Hub ARS Route-Map
Upgrade"). This manifest does **not** restate them as TP-HH's own delta.

TP-HH's own delta, priced 2026-08-05 (retail USD, public prices API):

| Item | Rate | TP-HH delta |
|---|---|---|
| `vm-nva1` `Standard_B2ts_v2` Linux, swedencentral | $0.0108/hr | U0 only, while running |
| `vm-nva2` `Standard_B2ts_v2` Linux, switzerlandnorth | $0.0132/hr | U0 only, while running |
| Global VNet peering, swedencentral | $0.04/GB egress + $0.04/GB ingress | ≈$0.00 (ICMP probe < 1 MB) |
| Route maps, peerings, associations | $0 | $0 |
| **U1.5 + U2 (BIRD cleanup + inert association)** | $0 | **$0** — no new billable object; run-rate unchanged |
| **U3a + U3b (documentation prefix + AS-Path)** | $0 | **$0** |
| **Recommended tranche U0+U1** | — | **+$0.024/hr = +$0.58/day, ≈$0.00 data** |

The shared bed's run-rate fell from **~$84/day to ~$66–73/day** after the Poland cleanup
(29/29 objects deleted, 2026-08-05) and remains owned by the source lab's `manifest.md`.
Stage 2's `vpngw-onprem2` (`VpnGw1AZ`, swedencentral $0.21/hr ≈ **$5.04/day**) is **not** in this
delta and is gated behind G3.

## Test program TP-HH — Stage 1 scenario summary

Execution order: **U0 → T1 (U1) → U1.5 (BIRD cleanup) → T2a (U2) → U3a → T2b (U3b) → T4 →
(T3/U5 only if required) → (T5/U4 only if approved)** → **rollback to certified baseline** (which is
Stage 2's gate G1).

### T1 — No-overlay native global-peering baseline *(US11 variant A)*

- **User intent.** "I have two regional hubs. Tell me exactly what I get, and what I do not get,
  from the one thing Azure gives me for free."
- **Change.** `vnet-hub1`↔`vnet-hub2` global VNet peering, both directions —
  `AllowVirtualNetworkAccess=true`, `AllowForwardedTraffic=true`, `AllowGatewayTransit=false`,
  `UseRemoteGateways=false`. No UDR, NSG or BIRD change.
- **Prerequisites.** Fresh pre-change baseline captured (design.md §7); `birdc show protocols all`
  route-refresh capability recorded on both NVAs.
- **Probe endpoints.** `vm-nva1` `10.10.1.4` ↔ `vm-nva2` `10.20.1.4` — the only deployed VMs inside
  the hub address spaces. `vm-hub1-ep`/`vm-hub2-ep` live in spoke VNets and cannot prove this test.
- **PASS.** Peering `Connected` + `FullyInSync` both sides, four flags as specified; `vm-nva1`↔`vm-nva2`
  reachable both directions; effective route tables gain exactly one `GlobalVNetPeering` entry for
  the remote hub prefix and nothing else; `ars-hub1`/`ars-hub2` and `vpngw-hub1`/`vpngw-hub2` learned
  + advertised sets byte-comparable to the pre-change capture; BIRD session uptime unbroken both NVAs.
- **FAIL.** Any ARS or gateway route-set change; a BGP session hard-reset; `10.20.0.0/16` appearing
  in `vpngw-hub1`'s on-premises advertisements (or the mirror); any existing certified flow perturbed.
- **Explicitly not tested (absence is the expected result).** Spoke prefixes, ARS-learned prefixes,
  gateway-learned prefixes crossing the peering — peering is non-transitive.
- **Evidence to create.** `show-output/new/t1-hub-peering/` — fresh pre/post capture pair per §validation.md L1–L6.
- **Rollback ownership.** Tank — delete both peering objects inside a second maintenance window; re-capture and diff.

### T2 — Hub-local ARS↔NVA route-map association *(US10 E-1 / RM-A, RM-B)*

**T2a/U2 EXECUTED and PASSED 2026-08-06 — the first route-map association to succeed anywhere in
this lab family** (see `deploy-log.md` §Change log, `validation.md` §T2a/U2, and Niobe's independent
live verification: `.squad/decisions/inbox/niobe-u15-u2-verification.md`). T2b (U3a/U3b) has not
run.

- **T2a — inert gate (must pass first).**
  - **User intent.** "Prove that attaching a route map to a live Route Server connection is
    possible, and that doing it does not cost an outage."
  - **Change.** Associate a **dedicated temporary map `rm-hub1-tmp-assoc`** (match `203.0.113.0/24`
    Equals — RFC 5737 TEST-NET-3, unmatchable by any lab prefix; **corrected 2026-08-06** from
    `192.0.2.0/24`, which is already `rm-hub1-activate`'s match prefix and would have made any
    observed effect ambiguous between the two maps) inbound on `ars-hub1`/`peer-nva1`
    via `properties.routingConfiguration.inboundRouteMap` on the `bgpConnections/peer-nva1` child
    object, API `2024-10-01`, **verb `PUT`** (this resource type defines no PATCH operation — a
    PATCH is expected to return HTTP 405), body from file (`az rest --body "@file.json"` — inline
    bodies fail on Windows PowerShell, see lessons-learned.md). **The PUT body must be derived from
    a fresh GET, not authored**: PUT replaces `properties` wholesale, so `peerAsn`, `peerIp` **and
    `routingConfiguration.vnetRoutes` including `staticRoutesConfig`** must all survive the round
    trip (§"U2 — mandatory PUT body preservation"). `rm-hub1-activate` is **not**
    reused: it is not empty (see the ledger), and U3 would have to mutate it. Documented fallback
    surface if the PUT is rejected: ARS blade → *route maps* → **Apply route maps**.
  - **Scope narrowing (Phase 4).** T2a runs on **hub1 only**. The `ars-hub2` mirror (T2a′) is a
    separate approval after hub1 passes — this halves the blast radius of a first-ever association.
  - **Result: PASS — confirmed.** Association `Succeeded`; no BIRD session uptime reset; learned/advertised sets
    attribute-identical (byte-identical to B1 across all 9 comparable capture files); zero ping loss on the post-U2 probe.
  - **PASS-with-note.** Association succeeds but a session resets and recovers — record outage
    duration; reclassify the change as "requires maintenance window".
  - **FAIL.** Association rejected (record the error code verbatim), or routing changes despite an inert map.
  - Mirror on `ars-hub2`/`peer-nva2` as T2a'. **Δ2-control retirement (2026-08-05):** the
    `65002-65002-65002` AS-PATH signature at `ars-hub2` no longer exists — it was carried by the
    set-C prefixes `10.31.0.0/24`/`10.32.0.0/24`, which were deleted with Poland and can never
    reappear. That criterion is replaced by "`ars-hub2`'s learned/advertised sets must be
    byte-identical to the **fresh post-U1.5 baseline (B1)**", which is the only valid control from
    now on. U2 must **not** be diffed against the post-U1 baseline B0, because U1.5 legitimately
    changes the learned set between them.
- **T2b — real modification (only after T2a/U2 **and** U3a pass).**
  - Inbound AS-Path `Add` on one named prefix learned from the NVA — **target corrected 2026-08-06
    to `198.51.100.0/24`** (RFC 5737 TEST-NET-2), injected into `vm-nva1`'s BIRD by **U3a** as a
    `blackhole` static so it is BGP-visible but can never carry traffic.
    **The previous target `10.10.0.64/27` is ⛔ invalid**: it is exported by BIRD identically to
    every other static yet never appears in `ars-hub1`'s learned set — Azure Route Server silently
    rejects a route matching its own RouteServerSubnet — so a map keyed on it could never match and
    T2b would have returned `Succeeded` while proving nothing. `0.0.0.0/0` is forbidden (spoke UDR
    semantics + DEF-001 evidence); `10.10.0.0/16`/`10.11.0.0/24` are impossible (route maps cannot
    modify the VNet address space ARS advertises); `10.40.0.0/16` is the on-prem prefix and is
    learned on `RouteServiceRole_IN_1` only, so any diff would be unfalsifiable; `10.30.0.0/27` is
    removed by U1.5 and must not be resurrected; the old set-C targets no longer exist. Attribute:
    documentation ASN 64496 ×2 — private (`64512`–`65534`) and Azure-reserved (`8074`, `8075`,
    `12076`, `65515`, `65517`–`65520`) ASNs are invalid prepend values; `64496` is the RFC 5398
    2-byte documentation ASN, from the same block as the `64511` used in Microsoft's own prepend
    walkthrough, and this is a closed lab with no MSEE and no public routing.
  - **PASS.** Exactly the matched prefix carries the two additional leading ASNs (observed AS-PATH
    `64496-64496-65001`); every other prefix byte-identical to the **B3** capture; endpoint
    effective routes unchanged where the test does not intend a change.
  - **INCONCLUSIVE (not FAIL).** The map reports `Succeeded` but neither
    `az network routeserver peering list-learned-routes` nor the portal Route Map dashboard shows
    the modified AS-PATH — it is not established whether that CLI reports post-map or as-received
    attributes. U2 remains the association proof. **Retrying against a production prefix to force
    visibility is forbidden.**
  - **FAIL.** Any non-matching prefix altered; map `provisioningState != Succeeded`; peering state
    not `Succeeded`; any BIRD uptime reset; any ping loss; `198.51.100.0/24` reaching either hub
    gateway or `vpngw-onprem`.
  - Mirror on `ars-hub2`/`peer-nva2` as T2b'.
- **Evidence to create.** `show-output/new/t2-routemap-assoc/` (plus `show-output/new/u3a-doc-prefix/`
  for the U3a step).
- **Rollback ownership.** Tank — PUT the **saved pre-U2 GET body** back without `inboundRouteMap`
  (never a hand-written body); re-verify against baseline. The route-map tier surcharge does not
  revert (already sunk, not charged to this lab).

### T3 — Dynamic inter-hub NVA BGP/tunnel variant *(US10; conditional)*

- **User intent.** "Do I actually need a second routing fabric between my regions, or am I building
  one because a reference architecture had one?"
- **Run only if** the program claims automatic spoke-wide propagation, automatic withdrawal on
  failure, or AS-PATH/community preference surviving the regional boundary. If none is claimed, T3
  is **not run**, and that non-execution is the deliverable (US11's decision-threshold table is the
  written justification — see design.md §6).
- **Prerequisites.** T1 peering as underlay; deny-by-default prefix policy (design.md §6) configured
  before the session is established.
- **PASS.** Sessions Established; permitted prefixes appear with expected AS-PATH and no 65515;
  `ars-poland`'s two `0/0` copies and `vm-c1-ep`'s `0/0 → 10.10.1.4` unchanged; withdrawal observed
  within the BGP hold window when a side is stopped; failback restores attribute-identical tables.
- **FAIL.** Any set-C or default-route change anywhere; one-directional convergence; a route
  silently absent because it carried 65515.
- **Evidence to create.** `show-output/new/t3-nva-bgp/`.
- **Rollback ownership.** Tank — tear down the eBGP session/tunnel; restore T1-only state; re-verify
  `ars-poland` and `vm-c1-ep` evidence is untouched.

### T4 — Policy placement: ARS route map vs NVA BIRD policy *(US09 + US10 §Maps do not solve)*

- **User intent.** "Same routing outcome, two possible control points. Which one do I put it in, and
  what can each one never do?"
- **Method.** Express one identical intent twice — (a) hub ARS inbound route map (T2b), (b) BIRD
  import/export filter on the same session — and compare observability, blast radius, reversibility,
  version-control story and failure modes.
- **The load-bearing negative result.** A route map cannot strip ASN 65515 and cannot rescue a
  route already discarded, because ARS applies loop prevention before inbound policy runs
  (design.md §5).
- **PASS.** Both control points produce the same RIB outcome for the map-expressible intent, and the
  65515 case is demonstrated as map-inexpressible with the exact error/absence recorded.
- **FAIL.** The comparison is asserted rather than measured, or the BIRD baseline changes without a
  restored-from-version-control diff.
- **Evidence to create.** `show-output/new/t4-policy-placement/`.
- **Rollback ownership.** Tank — revert BIRD config from version control; dissociate the T2b map back to T2a inert state.

### T5 — Local VPN-gateway connection route-map attachment *(US10 E-2 / RM-C, RM-D; OPTIONAL, UNVERIFIED)*

- **Status: unverified. No claim is made in either direction.** The Δ3 attempt proved that
  `associatedInboundConnections` on the route map is a read-only composite property, not the write path.
- **Runs only after T2a passes, and only with separate explicit approval.** **Phase-4 split (U4):**
  **Step 1 is read-only and carries zero write risk** — enumerate the portal *Apply route maps*
  blade verbatim and record `Get-Module -ListAvailable Az.Network`. Step 2 (the write) is proposed
  only if Step 1 shows an eligible same-VNet gateway connection.
- **It may not be testable at all.** The live model exposes no ARS↔VPN-gateway connection object:
  `ars-hub1` has no connection children beyond `bgpConnections/peer-nva1` and `routeMaps/*`, and the
  four `Microsoft.Network/connections` resources use the `VirtualNetworkGatewayConnection` schema,
  which has **no** `inboundRouteMap`/`outboundRouteMap` member (live `routingConfiguration: {}`).
  If Step 1 finds nothing eligible, record *"RM-C/RM-D unverifiable in this bed"* and close G4 on
  T2a's result alone. Note also that the `Az.Network` `New-AzRouteMap`/`Update-AzRouteMap`
  reference exposes **no** `-InboundConnection`/`-OutboundConnection` parameter — the how-to prose
  claiming otherwise is contradicted by its own Example 2, which sets `InboundRouteMap` inside a
  **connection's** `RoutingConfiguration`.
- **PASS.** Association `Succeeded` with the inert TEST-NET map, zero routing effect, all VPN
  connections stay `Connected`.
- **FAIL.** The API rejects it — record the exact error code verbatim; RM-C/RM-D are then
  reclassified as unsupported; the on-prem-facing admission/hygiene function moves to NVA/CPE
  policy; the US10 §2 row in the original catalogue is updated by Oracle, in the original lab.
- **Blast-radius note.** This scenario touches the shared `vpngw-hub1`/`vpngw-hub2`↔`vpngw-onprem`
  connections — the original lab's certified S1/S2/S3 evidence path. It is the one scenario that
  can damage another lab's results, which is why it is last, optional and separately approved.
- **Evidence to create.** `show-output/new/t5-gwconn-assoc/`.
- **Rollback ownership.** Tank — PATCH association back to `null`/empty; re-verify `vpngw-hub1`/`vpngw-hub2`↔`vpngw-onprem` connections stay `Connected` and byte-comparable to baseline.

## Stage 2 — TP-SQ: US12 square-hybrid feasibility study (gated, not executed)

**Status: not started, not approved, not scheduled.** Stage 2 is an **evaluation candidate, not a
recommendation.** The square is retained and studied because the repository rule is that every
design is documented with an evidence-based verdict — the evidence decides, not the expectation.

Canonical story (cross-linked, **not** copied):
[US12 — Square hybrid connectivity: regional DC-to-hub attachment with no diagonals](../dual-hub-hubless-region-ars/route-map-user-stories.md#us12--square-hybrid-connectivity-regional-dc-to-hub-attachment-with-no-diagonals)
(`US12-square-hybrid-connectivity`). Its sides, outcomes, instruments, Global Reach boundary and
residual risks stay canonical there. The **full activation contract lives in
[`design.md` §9–§13](./design.md)**; this section is the ledger-level summary only.

### Topology delta from the Stage-1 **restored** baseline

Four sides, no diagonals: **DC1↔Hub1 (S-A, reused) · Hub1↔Hub2 (S-B, added) · Hub2↔DC2 (S-C, added)
· DC1↔DC2 (S-D, added)**. No DC1↔Hub2 and no DC2↔Hub1 link is ever created.

| Delta | Class | Rollback |
|---|---|---|
| `vnet-onprem2` `10.50.0.0/16` + 2 subnets + 2 zoned PIPs + `vpngw-onprem2` (`VpnGw1AZ`, AS 65003) + 1 `Standard_B2ts_v2` VM | added — **only when approved** | Delete site 2 last (rollback step 8) |
| S-C pair `conn-hub2-to-onprem2` / `conn-onprem2-to-hub2` | added | Delete (step 4) |
| S-D pair `conn-onprem-to-onprem2` / `conn-onprem2-to-onprem`, eBGP 65000↔65003 | added | Delete (step 3) |
| S-B `vnet-hub1`↔`vnet-hub2` global peering — **variant N, no overlay, bounded** | added (Stage-1 T1 delta **re-created**, never inherited) | Delete in a maintenance window (step 5) |
| S-B **variant D** — NVA↔NVA eBGP + encapsulation only under the ARS self-next-hop rule | **conditional** — only if full failover requires **automatic prefix carriage and withdrawal** | Restore BIRD from version control (step 2) |
| **Delete** `conn-hub2-to-onprem` / `conn-onprem-to-hub2` — the diagonal | **disruptive; nothing else is removed** | Recreate with a **fresh matching PSK pair** (DEV-001) — highest-risk step of the program (step 6) |

**Poland is not reused.** `ars-poland`, `vnet-poland-ars`, set-C spokes and `vm-c1-ep` remain out of
scope and appear only as control captures that must not move. `vnet-onprem2` is a *new* VNet with a
*new* address space; US12 places it in `polandcentral` as a **region** choice only, and the region is
not load-bearing (design.md §9.3).

### Possible verdicts and the evidence that chooses one

| Verdict | Chosen when | Evidence required |
|---|---|---|
| **Recommended** | F1–F7 all PASS and no complexity dimension scores 4–5 | Full E0–E6 evidence set; scorecard filled from counted artefacts; bounded-failover contract written *before* the fault and matched |
| **Conditionally viable** | F1–F7 all PASS but a dimension scores 4–5, or the outcome set is sufficient only under stated conditions | The above, plus each condition written as a testable statement traced to its evidence |
| **Technically feasible but operationally unattractive** | **Every** packet-level criterion passes and the burden still exceeds the benefit | The above, plus an explicit "no feasibility criterion failed" statement and the named K-dimensions carrying the verdict |
| **Platform-blocked** | A required behaviour is not offered by the platform | Verbatim API error or documented platform property **with its exact scope** — a same-gateway limitation may not be generalised to the square |

F1–F7 (reachability, failover, failback, symmetry, convergence, route restoration, no collateral
damage) and the 8-dimension complexity scorecard (resource count · routing domains · policy locations
· failure dependencies · operational procedures · observability points · convergence behaviour ·
cost) are defined in `design.md` §12–§13. **Feasibility and desirability are decided separately and
reported separately, even when they disagree.**

### Cost

~**$95+/day floor** against the current ~$84/day run-rate — a floor, not an estimate, until the
`VpnGw1AZ` retail price is looked up for the chosen region. Both figures breach the ~$50/day
guardrail and **the existing $72/day waiver covers neither**. Variant N vs variant D is not a cost
difference of substance (the gateway dominates), so the choice is made on operational burden, not
price.

### Stage-2 activation gates — all four, none waivable

| Gate | Condition |
|---|---|
| **G1** | Stage 1 complete **and** rolled back to the certified baseline, diffed byte-comparable |
| **G2** | Poland cleanup status **known and recorded** in `deploy-log.md` — *status only; explicitly **not** a dependency*. Stage 2 may proceed with Poland running, pending cleanup, or already cleaned; it may not proceed with the status unknown |
| **G3** | **Fresh** cost / resource / **deletion** approval from Jose. Stage 1's approvals do not carry forward |
| **G4** | Exact route-map attachment behaviour known from Stage 1 — T2a `Succeeded` with the working body, or the verbatim error code; plus T5's verdict or an explicit "not run — unverified" |



## Designs studied

**Stage 1 — TP-HH**

| Design | Verdict for TP-HH |
|---|---|
| US11-A (native global peering) | GA, additive — T1 |
| US11-B (direct spoke↔spoke) | GA, additive — referenced context for T1's no-transitivity statement, not separately tested |
| US11-C (static NVA transit via UDR) | Learn-documented, unproven in this subscription — referenced only, not scheduled |
| US10 dynamic NVA-to-NVA overlay | Conditional — T3, run only if justified |
| ARS-map-vs-BIRD placement (US09 + US10) | T4 |

**Stage 2 — TP-SQ** *(candidate status only; no verdict may be recorded before evidence exists)*

| Design | Status |
|---|---|
| [US12 square, S-B variant N — no-overlay bounded](../dual-hub-hubless-region-ars/route-map-user-stories.md#us12--square-hybrid-connectivity-regional-dc-to-hub-attachment-with-no-diagonals) | **Evaluation candidate — default.** Verdict pending E0–E6 evidence; one of `Recommended` / `Conditionally viable` / `Technically feasible but operationally unattractive` / `Platform-blocked` |
| US12 square, S-B variant D — dynamic NVA↔NVA | **Evaluation candidate — conditional.** Admissible only if full failover requires automatic prefix carriage/withdrawal |
| US12 square with the diagonal added (dual-homed sites) | **Retained alternative, out of TP-SQ scope** — the honest answer when steady-state cross-region hybrid reachability is a real requirement; named so the square is not compared against nothing |
| Global Reach as S-B | **Platform-blocked by definition — retained as a documented error to avoid.** Global Reach is an S-D/B1 site-interconnect mechanism; it carries no prefix between hubs and is untestable in this bed (no ER circuit) |

*No entry above is a recommendation. Every one of them is retained regardless of verdict, per
`.squad/routing.md` rule #30.*


## Risks

See `.squad/decisions/inbox/morpheus-us10-us11-extraction.md` §9 for the full risk register
(broken-link risks, evidence-provenance risks, cost double-counting, cross-lab contamination,
overclaim regression). The two highest-severity items carried into this lab's own tracking:

1. **Stale-baseline risk.** Inherited baselines are 2026-08-03/2026-08-04; the live bed has since
   had the 2026-08-05 route-map tier upgrade. T1/T2 must capture a fresh baseline at execution time.
2. **Cross-lab contamination.** T3 leaking `0/0` or set-C prefixes, or T5 disturbing hub↔on-prem
   connections, would invalidate the source lab's certified results — encoded as hard FAIL criteria
   in every scenario above.
3. **Stage-2 evidence-loss risk (deferred, not yet live).** Deleting the hub2↔onprem1 pair removes
   the direct adjacency on which the source lab's Δ2 prepend evidence and S2/S3 timings were
   measured; restoring it requires a fresh matching PSK pair (DEV-001). This is why Stage 2 needs a
   complete E0 baseline before A1, and why the deletion is explicitly named in the G3 approval.
4. **Verdict-prejudgement risk.** The square is widely expected not to be recommended. Recording that
   expectation as a verdict before E0–E6 exist would violate rule #30 and would make the study
   pointless. Every Stage-2 row above is a *candidate status*, never a verdict.

## Approval gate

**Stage 1 — TP-HH, expressed as Phase-4 approval units (2026-08-05)**

Each unit is approved independently. **U0, U1, U1.5 and U2 are EXECUTED and PASSED** (2026-08-06,
approved by Jose Moreno; U1.5/U2 independently verified live by Niobe, read-only —
`.squad/decisions/inbox/niobe-u15-u2-verification.md`); U3–U5 remain **PENDING APPROVAL**.

| Unit | Scenario | Gate |
|---|---|---|
| **U0** | prerequisite | Requires Jose's approval — it is a **cost change** (+$0.58/day) and it is **not routing-neutral** (spoke `0/0` UDRs stop black-holing). Mandatory before any Stage-1 evidence can exist. |
| **U1** | T1 | Standing maintenance-window protocol (design.md §7); $0/hr. Gated on U0's `birdc show protocols all` confirming route-refresh capability. **EXECUTED AND PASSED 2026-08-06.** |
| **U1.5** | prerequisite (`TANK-001`) | Requires Jose's approval — **NVA configuration change**, though $0 and no Azure object. May share an approval **tranche** with U2 but **must not share a maintenance window** with it: U1.5 changes the ARS learned set, U2's headline criterion is that the learned set did not change. `vm-nva1` first, verified, then `vm-nva2`. **`systemctl restart bird` is forbidden** — graceful `birdc configure` only. **EXECUTED 2026-08-06 — PASS on both NVAs.** |
| **U2** | T2a, hub1 only | Requires Jose's approval to schedule the maintenance window — first-ever route-map **association** attempt on a live Route Server in this lab family. **Must not share a window with U1 or U1.5.** Gated on U1.5 passing and settling. The PUT body **must** be derived from a fresh GET with `vnetRoutes`/`staticRoutesConfig` preserved. The `ars-hub2` mirror is a further separate approval. **EXECUTED 2026-08-06 — PASS; association left active, closing gate G4.** |
| **U3a** | T2b step 1 | Runs only after U2 passes. NVA-side BIRD injection of `198.51.100.0/24` on `vm-nva1` only; $0. Its own PASS includes proving containment (prefix must not reach either hub gateway or `vpngw-onprem`). |
| **U3b** | T2b step 2 | Runs only after U3a passes and B3 is captured; no separate cost gate. Prefix **`198.51.100.0/24`** and ASN **`64496`** are fixed by this manifest and may not be changed at execution time. The former target `10.10.0.64/27` is **invalid** (proven unlearnable by ARS) and must never be reinstated. |
| **U4** | T5 | **Step 1** (read-only) may be bundled with U0/U1 at zero risk. **Step 2** requires separate explicit approval on top of U2 passing, due to shared hub↔on-prem gateway blast radius. |
| **U5** | T3 | **Not preapproved and not requested.** Fires only on the failover-contract trigger stated above, and then requires a fresh approval covering **NSG mutation on both NVA subnets** and BIRD mutation. |
| **T4** | T4 | No separate gate; runs after U3b, reusing its association. |

- **Executed 2026-08-06: U1.5 + U2 as one tranche in two separate maintenance windows** — $0
  incremental cost, PASSED on both units; association left active. U3a/U3b are a separate approval,
  now the **next approval gate**. Optionally bundle U4 Step 1 (read-only).
- **Superseded recommendation (2026-08-05): U0 + U1 only** (+$0.58/day, ≈45–60 min, <10 min
  rollback), optionally with U4 Step 1. Retained for provenance.
- **Stage-1 rollback** — mandatory, not optional. Stage 1 is not complete until every applied delta
  is reversed and diffed byte-comparable against the **fresh post-U0 baseline** (the pre-cleanup
  certified baseline is no longer reachable — Poland prefixes and the Δ2 control signature are gone).

**Stage 2 — TP-SQ**

- **Nothing may be created, deleted or scheduled until G1–G4 all pass** (§Stage 2 above).
- G3 is a **fresh** approval covering cost, the resource ledger **and the deletion** of
  `conn-hub2-to-onprem` / `conn-onprem-to-hub2`. No Stage-1 approval, and no prior waiver, carries
  forward into Stage 2.
- The disruptive step (A7) is separately confirmed at execution time even after G3 — the additive
  stage A1–A6 is fully reversible at zero disruption and is the natural stop point if anything in
  E1a–E1d surprises us.
- Variant D requires its own approval on top of G3 if any billable tunnel endpoint would exist.
