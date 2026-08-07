# design.md — Stage 1 `TP-HH` (bow-tie) + Stage 2 `TP-SQ` (square feasibility): Dual-Hub Interconnect and Route Server Route-Map Policy

**Scope:** `swedencentral` (hub1) + `switzerlandnorth` (hub2) only. `norwayeast` (`vnet-onprem`) is
adjacent/shared/read-only evidence. `polandcentral` is out of scope entirely — no topology
dependency anywhere in this document.

This document is authored fresh for TP-HH. It reproduces squad-canonical tables by reference
(`.squad/decisions.md` D2/D6) and quotes generic, two-region-scoped prose from the source
catalogue with backlinks. It does not fork or restate the 12-story catalogue.

**Two stages.** §1–§8 are **Stage 1** (TP-HH — the bow-tie / regional-affinity test program composed
from US10 + US11, executable under the existing gates). §9–§13 are the **Stage 2 activation
contract** (TP-SQ — the US12 square-hybrid feasibility study), which is written but **not executed**
and cannot start until the four gates in §11 all pass. Stage 2's Poland-region site is *new*
resource, not reuse — see §9.3.

---

## 1. Two-region topology (reused, not created)

| VNet | Region | Address space | Key resources |
|---|---|---|---|
| `vnet-hub1` | swedencentral | `10.10.0.0/16` | `vpngw-hub1` (AS 65515), `ars-hub1`, `vm-nva1` (`10.10.1.4`, AS 65001, BIRD) |
| `vnet-hub2` | switzerlandnorth | `10.20.0.0/16` | `vpngw-hub2` (AS 65515), `ars-hub2`, `vm-nva2` (`10.20.1.4`, AS 65002, BIRD) |
| `vnet-spoke-a` | swedencentral | `10.11.0.0/24` | `vm-hub1-ep` |
| `vnet-spoke-b` | switzerlandnorth | `10.21.0.0/24` | `vm-hub2-ep` |
| `vnet-onprem` *(adjacent, read-only)* | norwayeast | `10.40.0.0/16` | `vpngw-onprem` (AS 65000) |

No hub1↔hub2 data-plane path exists today (D4, `.squad/decisions.md`). TP-HH's T1 is the first time
this lab creates one, and only as a native peering — not a new fabric.

---

## 2. Peering flag matrix — the new hub1↔hub2 pair (T1)

| Flag | Value | Why |
|---|---|---|
| `AllowVirtualNetworkAccess` | `true` | Required for any cross-VNet reachability |
| `AllowForwardedTraffic` | `true` | Required so NVA-forwarded traffic (UDR next hop) can cross; without it, only VM-to-VM direct traffic works |
| `AllowGatewayTransit` | `false` | Neither hub may use the other's gateway — each hub already has its own `vpngw-hub*` |
| `UseRemoteGateways` | `false` | Mirrors `AllowGatewayTransit=false`; both directions |
| Direction | Both (`hub1→hub2` and `hub2→hub1`) | VNet peering is not symmetric by default; both peering objects must be created |

Created/deleted only inside a declared maintenance window (§4). No UDR, NSG or BIRD change
accompanies T1 — it is a pure control-plane-native-routes test.

---

## 3. ARS↔NVA and ARS↔gateway attachment eligibility (D2, reproduced from `.squad/decisions.md`)

> Route maps can only be applied to BGP peers whose peerIp is within the ARS VNet address space.

| ARS instance | NVA peer | peerIp | ARS VNet | Eligible? |
|---|---|---|---|---|
| `ars-hub1` | NVA1 | `10.10.1.4` | `10.10.0.0/16` | ✅ Yes |
| `ars-hub2` | NVA2 | `10.20.1.4` | `10.20.0.0/16` | ✅ Yes |
| `ars-poland` | NVA1 | `10.10.1.4` | `10.30.0.0/24` | ❌ No (`EMP-001`) — *out of scope, contrast only* |
| `ars-poland` | NVA2 | `10.20.1.4` | `10.30.0.0/24` | ❌ No (`EMP-001`) — *out of scope, contrast only* |
| `ars-hub1` | VPN GW connection | (in-VNet) | `10.10.0.0/16` | ✅ Yes |
| `ars-hub2` | VPN GW connection | (in-VNet) | `10.20.0.0/16` | ✅ Yes |

This constraint is **not documented by Microsoft** as of 2026-08-03; the runtime error
(`HubBgpConnectionFromSpokeVnetCannotReferenceRouteMap`, `EMP-001`) is authoritative. It is the
reason hub1/hub2 are the only viable T2 attachment points in this entire lab family — the one
Poland fact this lab must carry, as a single referenced sentence, never as copied `delta3/` evidence.

Full source: `.squad/decisions.md` → *D2 — ARS Route-Map Eligibility Rule (Same-VNet Constraint)*.

## 4. Policy placement rule (D6, reproduced from `.squad/decisions.md`)

> Prefer BIRD for cross-VNet scenarios; use route maps for hub-local eligible connections.

| Scenario type | Preferred tool | Reason |
|---|---|---|
| Cross-VNet BGP peer (`ars-poland`↔NVA1/NVA2) | **BIRD/FRR** | No locality constraint, no upgrade, no surcharge — *out of scope, contrast only* |
| Hub-local BGP peer (`ars-hub1`↔NVA1) | **Route map OR BIRD** | Both eligible; route map adds GUI observability |
| VPN/ER GW connection filtering | **Route map** | No BIRD equivalent; map is the only ARS-native lever |
| Per-spoke policy | **UDR** | Route maps have no per-spoke attachment point |
| Traffic containment | **NSG/firewall** | Route maps are control-plane only |

Full source: `.squad/decisions.md` → *D6 — Prefer BIRD for Cross-VNet Scenarios; Use Route Maps for
Hub-Local Eligible Connections*. T4 (§6 below) is the empirical test of this rule.

---

## 5. The 65515 loop-prevention-before-policy statement

> A route map **cannot** strip ASN 65515 and cannot rescue a route already discarded, because ARS
> applies loop prevention **before** inbound policy runs. The Δ1 strip therefore must live on the
> NVA, permanently.

Source (quoted excerpt, generic/mechanism-level):
[`route-map-user-stories.md` — US10 §"Maps do not solve"](../dual-hub-hubless-region-ars/route-map-user-stories.md#us10--bow-tie-dual-site-regional-affinity-with-cross-region-backup).

This is the load-bearing negative result for T4: it is why the lab's proven Δ1/Δ2/Δ3 policies are
BIRD-side and not map-side, and it is the honest answer to "should we move everything to route
maps". No route-map test in this lab (T2, T4) may claim to repair a 65515-carrying route.

---

## 6. T3 prefix policy — deny by default (non-negotiable)

T3 (the conditional dynamic NVA BGP/tunnel variant) runs **only if** the program claims at least one
of: automatic spoke-wide propagation of remote-region prefixes, automatic withdrawal on failure, or
AS-PATH/community-based preference surviving the regional boundary. If none is claimed, T3 is **not
run**, and that non-execution is itself the deliverable.

If run, the underlay is T1's peering; the overlay is `vm-nva1`↔`vm-nva2` eBGP `65001`↔`65002` with
`bgp_path.delete(65515)` on export. Encapsulation is added **only** when remote prefixes are
redistributed into the local Route Server (the self-next-hop recursion —
`azure/route-server/multiregion` — is the single Azure limitation that necessitates it).

**Deny-by-default prefix policy (both directions):**

| Direction | Permit | Deny |
|---|---|---|
| hub1 → hub2 | `10.10.0.0/16`, `10.11.0.0/24` | everything else |
| hub2 → hub1 | `10.20.0.0/16`, `10.21.0.0/24` | everything else |
| **Both directions, unconditionally** | — | **`0.0.0.0/0`** and **`10.31.0.0/24`** / **`10.32.0.0/24`** (set-C) |

A second copy of the default route or of a set-C prefix would corrupt the original lab's live
Δ3/DEF-001 evidence — the sharpest cross-lab blast-radius risk in this whole program. This is a
filter/exclusion note only; it creates no topology dependency on Poland or set-C.

---

## 7. Maintenance-window / BGP-reset protocol

Every change that touches a Route Server VNet's peering set is treated as a **maintenance window**:
ARS issues a route refresh to all peered NVAs — **soft** reset if BIRD supports RFC 2918 route
refresh, otherwise a **hard** reset with traffic disruption. Before the **first** change of any kind:

1. Record `birdc show protocols all` route-refresh capability on both `vm-nva1` and `vm-nva2`.
2. Capture a **fresh** pre-change baseline (T1/T2 must not rely solely on the inherited
   2026-08-03/2026-08-04 captures — the live bed has since had the 2026-08-05 route-map tier
   upgrade). See `validation.md` for the fresh-baseline requirement.
3. Confirm the original lab's certified evidence (Δ1, Δ2, Δ3-via-BIRD, S2/S3 timings, DEF-001
   resolution) is available for a byte-comparable post-change diff.

Any peering create/delete or route-map association/dissociation in this lab is scheduled and
executed under this protocol — never as an ad hoc change.

---

## 8. No-transitivity scope statement (what T1 deliberately does not prove)

T1 (native global VNet peering) is explicitly **not** a transitivity test. VNet peering is
non-transitive by design. T1's PASS criteria require that the following are **absent** after the
peering is created, and their absence is the expected result, not a failure:

- Spoke prefixes (`10.11.0.0/24`, `10.21.0.0/24`) do not cross the peering.
- ARS-learned prefixes do not cross the peering.
- Gateway-learned prefixes (from `vpngw-onprem` via `vpngw-hub1`/`vpngw-hub2`) do not cross the
  peering.

Only hub address-space reachability (`10.10.0.0/16` ↔ `10.20.0.0/16`) and the `vm-nva1`↔`vm-nva2`
host-terminated probe are in scope for T1. Workload-to-workload or spoke-to-spoke reachability is
US11 variant B territory (`US11-no-overlay-direct-workloads`) and is not exercised by T1.

## 8a. Live-state addendum and association write-path semantics (2026-08-05, post-Poland cleanup)

Read-only reconciliation after the Poland cleanup (29/29 objects deleted) changed three design
premises. Full record: `.squad/decisions/inbox/trinity-bowtie-activation-plan.md`.

**(a) The bed is quiescent, not merely idle.** All five VMs are `VM deallocated`. Consequently
`ars-hub1`/`ars-hub2` learned **and** advertised sets are empty on both instances, the hub gateways
show the ARS neighbours in `Connecting`, `vpngw-onprem` learns no hub or spoke prefix, and the spoke
`0.0.0.0/0` UDRs point at powered-off NVAs. **Every PASS criterion in §1–§8 that reads an ARS
learned set or a BIRD session is unevaluable until the NVAs are started (U0).** U0 is therefore a
design prerequisite, not an operational detail, and it is not routing-neutral: it re-originates
`0.0.0.0/0` and the RouteServerSubnet `/27` into both hubs.

**(b) The association write path — corrected.** §6's maintenance-window protocol stands, but the
mechanics are now verified against the live resource model and the current Learn/`Az.Network`
reference:

- Write target is the **connection**, not the map:
  `virtualHubs/<ars>/bgpConnections/<peer>` → `properties.routingConfiguration.inboundRouteMap.id`.
- `routeMaps/*.associatedInboundConnections` is a **read-only composite** — live GET returns `[]`,
  and `New-AzRouteMap`/`Update-AzRouteMap` expose no `-InboundConnection`/`-OutboundConnection`
  parameter. **This confirms the lab's Δ3 finding; it must not be regressed in any document.**
- **Verb is `PUT`, not `PATCH`** — this child resource type defines no PATCH operation (expect 405)
  — and the body must carry `peerAsn` + `peerIp` + `routingConfiguration` in full, or the peering is
  recreated with defaults. Bodies always from file; inline JSON fails on Windows PowerShell.
- The ~30-minute first-route-map ARS upgrade is **already done** on both hubs (2026-08-05T10:36) and
  will not repeat, so creating a dedicated temporary map costs nothing but a create call.
- Association is performed on **`ars-hub1` only** first (U2); the `ars-hub2` mirror is a separate
  approval. This halves the blast radius of a first-ever association.

**(c) Two controls are permanently gone.** Both `bird.conf` files still define `ars_poland_0/1`
toward the deleted `10.30.0.4/.5`, so those protocols will sit in `Connect`/`Active` forever
(harmless, noisy), and `10.30.0.0/24`, `10.31.0.0/24`, `10.32.0.0/24` will never
reappear **as BGP-learned prefixes from a live Poland peer**. The **Δ2 control signature
`65002-65002-65002` no longer exists** and is retired as a "must not move" criterion. The only valid
Stage-1 control from now on is byte-comparison against a **fresh post-U0 baseline**. BIRD's
route-refresh capability was likewise never captured (`show protocols all` exists nowhere); it is
expected by default in BIRD 2.x but must be measured in U0 before U1 runs. BIRD configs are
hand-edited on the OS disks and are **not** in version control.

**(c-correction, added 2026-08-06 after U0 execution — `TANK-001`, see `lessons-learned.md`).**
Point (c) above is correct for `10.30.0.0/27` arriving *via a live Poland BGP peer* — that can never
happen again. It is **incomplete**: U0 revealed that both NVAs' hand-edited `bird.conf` also carry a
stray `protocol static` route for `10.30.0.0/27` (the Poland RouteServerSubnet shape), exported to
the local hub ARS unfiltered by prefix, so it **does** reappear in `ars-hub1`/`ars-hub2`'s
*learned-routes* set purely from static re-origination, independent of Poland's BGP peer ever
existing again. It is contained (does not reach the gateways, on-prem, or ARS's advertised-back set —
confirmed by evidence) but any future scenario reading "no Poland prefix anywhere" as an ARS
learned-routes check must account for this static source, not just the BGP-peer source. Separately,
`10.10.0.64/27` (NVA1's own RouteServerSubnet, cited in (d) below as T2b's target prefix) was
**not** observed in ARS's learned-routes set at all in this session, despite being present in
`bird.conf` and exported the same way as `10.30.0.0/27` — Azure Route Server appears to implicitly
reject/filter a route matching its own RouteServerSubnet. **This should be re-verified before T2b
(U3) is planned**, since T2b's target prefix may not actually be visible to a route map applied at
the ARS↔NVA connection in the way §8a(d) assumes. Evidence:
`labs/dual-hub-interconnect-ars-route-policy/show-output/new/u0-u1/post-u0/`.

**(d) Approval-unit mapping.** U0 = prerequisite (VM power only) · U1 = T1 · **U1.5 = prerequisite
BIRD cleanup (`TANK-001`)** · U2 = T2a (hub1 only, dedicated `rm-hub1-tmp-assoc`, match
`203.0.113.0/24`) · **U3a = T2b step 1** (inject `198.51.100.0/24` as `blackhole` in `vm-nva1` BIRD)
· **U3b = T2b step 2** (`Add asPath [64496,64496]` on `198.51.100.0/24`) ·
U4 = T5 (Step 1 read-only; Step 2 may be untestable — no ARS↔VPN-gateway connection object exists in
this model) · U5 = T3 (**not preapproved**; would additionally require TCP/179 NSG rules on both NVA
subnets and BIRD mutation). §7's maintenance-window protocol applies unchanged to U1–U4, and U1,
U1.5 and U2 **may not share a window** because U2's criteria are defined against a settled
post-U1.5 baseline.

**(d-correction, 2026-08-06 — supersedes the original (d) mapping.)** Two changes follow directly
from `TANK-001`:

1. **A new prerequisite unit `U1.5` is inserted between U1 and U2.** Both NVAs still carry retired
   Poland BIRD state — `ars_poland_0`/`ars_poland_1` (dead, in `Connect`), their
   `export_to_poland_ars` filters, a stray static `route 10.30.0.0/27`, and on `vm-nva2` a dead
   `10.31.0.0/24`/`10.32.0.0/24` prepend clause. The `10.30.0.0/27` static is genuinely
   re-originated into both Route Servers, because `export_to_hub_ars`/`export_to_hub2_ars` filter by
   **AS-PATH** (`bgp_path.delete(65515)`), never by prefix. U1.5 removes exactly that state, touches
   **no Azure object**, costs **$0**, is applied with graceful `birdc configure` (never
   `systemctl restart bird`), and is reversible in under two minutes per NVA. Contract:
   `nva-config/README.md`; criteria: `validation.md` §U1.5.
2. **The U3 target prefix `10.10.0.64/27` is invalid and is replaced.** It is exported by BIRD
   identically to every other static yet never appears in `ars-hub1`'s learned set — Azure Route
   Server silently rejects a route matching its own RouteServerSubnet. A route map keyed on it could
   never match, so the original U3 would have reported `Succeeded` while proving nothing. Since no
   *already-advertised* prefix is safe to modify (`0.0.0.0/0` = spoke UDR target/DEF-001;
   `10.40.0.0/16` = on-prem prefix and present on one ARS instance only; `10.30.0.0/27` removed by
   U1.5), U3 is split: **U3a** injects the RFC 5737 TEST-NET-2 prefix `198.51.100.0/24` as a
   `blackhole` static on `vm-nva1` — BGP-visible, incapable of carrying traffic — and **U3b**
   applies the AS-Path change to it. The three RFC 5737 blocks are kept deliberately distinct:
   `192.0.2.0/24` = `rm-hub1-activate` (pre-existing), `203.0.113.0/24` = U2's inert rule,
   `198.51.100.0/24` = U3. No piece of evidence is then ambiguous about which artefact produced it.

Also corrected: U2's PUT body must be **derived from a fresh GET**, not authored. The live
`bgpConnections/peer-nva1` carries `routingConfiguration.vnetRoutes.staticRoutesConfig`
(`propagateStaticRoutes: true`, `vnetLocalRouteOverrideCriteria: "Contains"`), and PUT replaces
`properties` wholesale — omitting it would silently reset routing behaviour U2 has no mandate to
change.

**(d-execution, added 2026-08-06).** U1.5 and U2 as designed above were **executed and PASSED** on
2026-08-06 (Tank, approved by Jose Moreno; independently verified live, read-only, by Niobe —
`.squad/decisions/inbox/niobe-u15-u2-verification.md`). `10.30.0.0/27` was withdrawn exactly as
designed with no BGP session flap; `nva-config/bird-nva{1,2}.u15-target.conf` are now authoritative
and match the live configs. The U2 association (`rm-hub1-tmp-assoc` on `ars-hub1`/`peer-nva1`) is
`Succeeded`, has produced no route effect, and is **left active** as the precondition for U3a/U3b.
Full results: `validation.md` §U1.5 and §T2a/U2; `deploy-log.md` §Change log. **U3a/U3b, T2b, T3–T5
(U4/U5) have not run** — U4's gateway-connection attachment remains unverified.

**(e) Scope honesty.** Stage 1 delivers a **single-site dual-homed hub-preference proxy**, not a
bow-tie. The bow-tie needs two on-premises sites; this bed has one (`vnet-onprem`, AS 65000)
dual-homed to both hubs. **Regional affinity cannot be proven without a second on-prem
site/gateway** (`vnet-onprem2` + `vpngw-onprem2`, Stage 2 / gate G3). The bow-tie verdict remains
*not determined*.

---

---

# Stage 2 — TP-SQ: US12 square-hybrid feasibility study (activation contract, not executed)

Everything from §1 to §8 above is **Stage 1** (TP-HH). Sections §9–§13 define **Stage 2**, the
US12 square-hybrid feasibility study. Stage 2 is an **evaluation candidate, not a recommendation**,
and **nothing in §9–§13 is authorization to build anything**. It is the written contract that would
have to be satisfied *before* a build could be proposed, and the evidence that would decide the
verdict afterwards.

Canonical story, cross-linked and deliberately **not** copied here:
[US12 — Square hybrid connectivity: regional DC-to-hub attachment with no diagonals](../dual-hub-hubless-region-ars/route-map-user-stories.md#us12--square-hybrid-connectivity-regional-dc-to-hub-attachment-with-no-diagonals)
(stable ID `US12-square-hybrid-connectivity`). Its side letters (S-A/S-B/S-C/S-D), outcome letters
(A / B1 / B2 / B3 / C / D), instruments (V1–V11), Global Reach boundary, loop-prevention section,
residual-risk table and the *US10 versus US12* comparison are canonical **there**. This document
adds only what the *lab* must do, in *this* bed, and defers to the catalogue for the rest.

---

## 9. Exact topology deltas from the Stage-1 restored baseline

**Reference state.** The delta below is measured from the **Stage-1 restored baseline** — the source
lab's certified state after every TP-HH delta (hub↔hub peering, every route-map association, every
BIRD change) has been rolled back and diffed byte-comparable. It is *not* measured from the
mid-Stage-1 state, and Stage 2 may not "inherit" a still-attached T1 peering or a still-associated
T2 route map. If Stage 1 leaves anything attached, Stage 2 is not eligible to start (§11, gate G1).

In that baseline, `vnet-onprem` is connected to **both** hubs. The attachment matrix is therefore
**not** a square today — it carries a diagonal. Removing that diagonal is the disruptive core of
Stage 2.

### 9.1 The four sides, and only four

| Side | Endpoints | Lab realisation | Class |
|---|---|---|---|
| **S-A** | DC1 ↔ Hub1 | Existing `conn-hub1-to-onprem` / `conn-onprem-to-hub1`, `vpngw-onprem` (AS 65000, `vnet-onprem` `10.40.0.0/16`, norwayeast) ↔ `vpngw-hub1` (AS 65515) | **reused, unchanged** |
| **S-B** | Hub1 ↔ Hub2 | `vnet-hub1`↔`vnet-hub2` global VNet peering pair, flags exactly as §2 — i.e. **Stage 1's T1 delta, re-created**, not inherited | **added (variant N default)** |
| **S-C** | Hub2 ↔ DC2 | **New** `conn-hub2-to-onprem2` / `conn-onprem2-to-hub2` between `vpngw-onprem2` (AS **65003**, `vnet-onprem2` `10.50.0.0/16`) and `vpngw-hub2` (AS 65515) | **added — approval-gated** |
| **S-D** | DC1 ↔ DC2 | **New** `conn-onprem-to-onprem2` / `conn-onprem2-to-onprem` VNet-to-VNet pair with BGP on, eBGP `65000`↔`65003`. The lab analogue of a corporate WAN or a Global Reach interconnect — the bed has no ExpressRoute circuit, so Global Reach itself cannot be exercised here at all | **added — approval-gated** |

### 9.2 Absent by design — the diagonals

There is **no DC1↔Hub2 and no DC2↔Hub1 link of any kind** in the target state. Their absence is the
design, not an omission:

- **Removed at activation:** `conn-hub2-to-onprem`, `conn-onprem-to-hub2`. **Nothing else is removed.**
- **Never created:** any `vpngw-onprem2`↔`vpngw-hub1` connection pair.
- Every cross-region hybrid flow must therefore traverse **two of the four sides**. That is the whole
  design and also the whole constraint.

### 9.3 Poland: region reuse is not resource reuse

**No Poland resource is reused by Stage 2.** `ars-poland`, `vnet-poland-ars`, `vnet-spoke-c1`,
`vnet-spoke-c2`, `vm-c1-ep` and the set-C prefixes `10.31.0.0/24` / `10.32.0.0/24` are **out of scope
entirely**, exactly as in Stage 1: they appear only as *control captures that must not move*.

`vnet-onprem2` is a **new** VNet with a **new** address space (`10.50.0.0/16`) and a **new** gateway.
US12's lab analogue places it in `polandcentral`; that is a *region* choice inherited from the
catalogue, and it creates no dependency on, and no reuse of, anything the existing Poland stack owns.
If the S0 gateway SKU / zone preflight fails in `polandcentral` (see §10.4), the site may be placed in
any other European region without changing anything else in this contract — the region is not
load-bearing, the *absence of diagonals* is.

### 9.4 Exact additive resource ledger (only if and when approved)

- 1 VNet `vnet-onprem2` (`10.50.0.0/16`) + 2 subnets · 2 zoned Standard PIPs · 1 `VpnGw1AZ`
  active-active gateway (ASN 65003) · 1 `Standard_B2ts_v2` VM + NIC + disk · 4 connection objects
  (S-C pair + S-D pair) · 1 global VNet peering pair (S-B). PIP total 9 → 11.
- **Variant D increment only** (§10.5): BIRD multi-hop eBGP policy blocks on both NVAs and, only if
  remote prefixes are redistributed into the local Route Server, one IPsec tunnel `vm-nva1`↔`vm-nva2`.

---

## 10. Constraints that govern the square — same-AS / own-AS and Route Server limits

These are the constraints a Stage-2 build cannot design around. They are the reason the square's
geometry does not imply its failover.

### 10.1 Own-AS / same-AS

| # | Constraint | Consequence for the square |
|---|---|---|
| C1 | **ARS ASN is fixed at 65515**, and all three hub-side VPN gateways also use 65515 | ARS discards any route whose AS-PATH already contains 65515. Any Azure-to-Azure re-advertisement must have 65515 stripped **on the NVA, before** it reaches the peer ARS — the Δ1 strip is load-bearing, permanently, and cannot move into a route map (§5) |
| C2 | **Distinct on-premises ASNs are mandatory** — `vpngw-onprem` 65000, `vpngw-onprem2` **65003** | Same-AS on both sites would make the S-D eBGP session reject the peer's prefixes by own-AS loop prevention; S-D would come up and carry nothing |
| C3 | **NVA ASNs 65001 / 65002 must stay distinct** across the S-B variant-D adjacency | A same-AS NVA pair cannot exchange prefixes over eBGP without explicit `allowas-in`-style overrides, which defeat the loop prevention the design relies on |
| C4 | **Prepend values inside the lab use 64496** (IANA documentation range) | Acceptable **only** because this is a closed lab with no MSEE and no public routing. A real square must prepend with an ASN the enterprise owns; documentation ASNs 64496–64511 must never reach an ExpressRoute circuit |
| C5 | **MSEE AS 12076 own-AS loop prevention** on every ExpressRoute path | Not exercisable in this bed (no ER circuit). Any ER-based statement Stage 2 produces is **analytical, carried by reference from US12**, and must never be recorded as lab-measured evidence |

### 10.2 Route Server limitations that bound the study

| # | Limitation | Effect |
|---|---|---|
| L1 | **D2 — same-VNet route-map eligibility.** A map attaches only to a BGP peer whose `peerIp` is inside the ARS VNet's own address space (§3) | The square's only eligible map attachment points are hub-local: `ars-hub1`↔`vm-nva1`, `ars-hub2`↔`vm-nva2`, and the two in-VNet gateway connections. Nothing site-side and nothing cross-region is map-attachable |
| L2 | **Loop prevention runs before inbound policy** (§5) | A route map cannot rescue a 65515-carrying route. Admission, tagging, preference and de-preference are the only map-expressible functions in the square |
| L3 | **ExpressRoute circuit-to-circuit transit through a Route Server is not supported** | US12 classifies this `Platform-blocked — retained` for the ER framing. In this bed it is untestable; it is carried as a documented platform property, never as a Stage-2 result |
| L4 | **Self-next-hop recursion across regions** (`azure/route-server/multiregion`) | Redistributing *remote-region* prefixes into the local ARS requires an encapsulation. This — not "a reference architecture had one" — is the only thing that buys a tunnel on S-B |
| L5 | **Branch-to-branch** must be on for S-B-learned prefixes to reach a gateway | Outcome C's reverse direction depends on it at the *surviving* hub; it is a prerequisite to verify, not to assume |
| L6 | **180 s hold / 60 s keepalive** on ARS, plus a hold timer on every other hop | The convergence window is a chain property. It is measured per direction, never inferred |
| L7 | **Route refresh on peering create *and* delete** — soft with RFC 2918, otherwise **hard, with data-plane disruption through the NVA** | Both S-B creation and S-B rollback are maintenance windows (§7 applies unchanged to Stage 2) |
| L8 | **VPN gateways do not advertise default routes to other BGP peers** (VPN Gateway FAQ), while BGP transit routing is otherwise supported | S-D can act as transit for site prefixes; it must not be assumed to carry `0/0`, and the reciprocal Azure-to-Azure case stays masked by the 65515 drop until measured |

### 10.3 Prefix policy — deny by default, unchanged from §6

The §6 deny-by-default policy applies to **every** Stage-2 session (S-B variant D, S-C, S-D) without
modification: **`0.0.0.0/0` is denied unconditionally in both directions, and `10.31.0.0/24` /
`10.32.0.0/24` (set-C) are denied unconditionally in both directions.** `ars-poland` currently holds
exactly two default-route copies (`65001` and `65002-65002-65002`); a third copy, or a set-C prefix
taking a new path, corrupts the source lab's certified DEF-001 evidence. This is the sharpest
cross-lab blast-radius risk in the entire two-stage program.

### 10.4 Preflight that has already bitten this lab

`az deployment group validate` and `what-if` catch **neither** `NonAzSkusNotAllowedForVPNGateway`
**nor** `VmssVpnGatewayPublicIpsMustHaveZonesConfigured`. The S0 gate is therefore mandatory before
`vpngw-onprem2` is attempted: `VpnGw1AZ` only, two Standard PIPs with zones `1,2,3` created and
validated **first**, parity-checked against the three deployed gateways, stop-on-failure.

### 10.5 Variant N first; variant D only on a stated requirement

**S-B is a no-overlay bounded native global peering (variant N) by default.** Variant D — the
`vm-nva1`↔`vm-nva2` eBGP adjacency with `bgp_path.delete(65515)` on export, plus encapsulation only
under L4 — is admissible **only** when full failover (outcome C) is claimed *and* that claim
requires **automatic prefix carriage and automatic withdrawal**. Static/UDR carriage is not an
alternative: a static route can carry packets but **cannot withdraw itself** when S-A returns or when
the DCI fails. If outcome C is not claimed, variant D is not run, and its non-execution is a
deliverable in exactly the same way T3's is in Stage 1.

---

## 11. Activation and rollback sequence, with evidence checkpoints

**Nothing below is executed by this document.** Gates first — all four must pass, none may be waived:

| Gate | Condition | Evidence that closes it |
|---|---|---|
| **G1** | Stage 1 complete **and** rolled back to the certified baseline | Every TP-HH delta reversed; post-rollback capture diffed **byte-comparable** against the source lab's certification; `deploy-log.md` change log shows a rollback row for every applied row |
| **G2** | **Poland cleanup status known and recorded** | A one-line status statement in `deploy-log.md` naming whether the Poland/set-C stack is still deployed, and by whose authority. **Explicitly not a dependency** — Stage 2 may proceed with Poland still running, still pending cleanup, or already cleaned. It may **not** proceed with the status *unknown* |
| **G3** | **Fresh** cost / resource / deletion approval from Jose | A dated approval covering: the ~$95+/day floor against the current ~$84/day run-rate (both breach the ~$50/day guardrail; the existing $72/day waiver covers neither), the §9.4 resource ledger, and the **deletion** of `conn-hub2-to-onprem` / `conn-onprem-to-hub2`. Stage 1's approvals do not carry forward |
| **G4** | **Exact route-map attachment behaviour known** | T2a's outcome recorded as either `Succeeded` (with the working request body and the observed reset/no-reset behaviour) or the **verbatim** error code; plus T5's verdict on gateway-connection attachment, or an explicit "T5 not run — attachment remains unverified" |

### 11.1 Activation sequence — additive first, disruptive last

| Step | Action | Checkpoint |
|---|---|---|
| A0 | Capture a **complete fresh pre-activation baseline** at every layer L1–L8, including the Δ2 direct-adjacency AS-PATH form at `vpngw-onprem` and the two `ars-poland` `0/0` copies | **E0** — the only reference the whole stage is diffed against |
| A1 | S0 preflight (§10.4): PIP zones, `VpnGw1AZ` availability, parity check | Stop-on-failure; no resource created if it fails |
| A2 | Create `vnet-onprem2` + subnets + PIPs + `vpngw-onprem2` (AS 65003) + endpoint VM | Long pole, 30–45 min |
| A3 | Create the **S-C** pair `conn-hub2-to-onprem2` / `conn-onprem2-to-hub2`; verify BGP up | **E1a** |
| A4 | Create the **S-D** pair `conn-onprem-to-onprem2` / `conn-onprem2-to-onprem`, eBGP 65000↔65003, deny-by-default filters (§10.3) applied **before** the session establishes | **E1b** |
| A5 | Create the **S-B** global peering pair (§2 flags) inside a maintenance window; route-refresh capability confirmed on both NVAs first | **E1c** |
| A6 | Re-verify that **nothing broke**: all pre-existing connections `Connected`, `ars-poland` unchanged, set-C effective routes unchanged | **E1d** — additive stage is reversible to here at zero disruption |
| A7 | **The disruptive step.** Delete `conn-hub2-to-onprem` and `conn-onprem-to-hub2`. Nothing else | **E2** |
| A8 | Steady-state square evidence: outcomes A, B1, B2 (hub address space only, probed `vm-nva1` `10.10.1.4` ↔ `vm-nva2` `10.20.1.4`), B3 reported **not delivered** under variant N | **E3** |
| A9 | Bounded-failover injection: lose S-A; measure per direction at 30/60/120/180 s | **E4** |
| A10 | Failback and restoration-equality re-run of every instrument | **E5** |
| A11 | Score the complexity scorecard (§12) from E0–E5 evidence and record the verdict (§13) | **E6** |

### 11.2 Rollback sequence — exact reverse, with the recreate risk called out

1. Detach any route map associated during Stage 2; confirm dissociation.
2. Restore BIRD from version control on both NVAs; confirm session uptime and filters.
3. Delete the S-D connection pair.
4. Delete the S-C connection pair.
5. Delete the S-B peering pair **inside a maintenance window** (route refresh on delete, L7).
6. **Recreate `conn-hub2-to-onprem` / `conn-onprem-to-hub2` with a fresh matching PSK pair** —
   DEV-001 applies: the original PSK is not assumed to be readable back from Key Vault, and a fresh
   matching pair is functionally equivalent. **This step is the highest-risk part of the whole
   two-stage program**, because it is the step that must restore another lab's certified evidence path.
7. Confirm Δ2 has returned **in its direct-adjacency form** at `vpngw-onprem`, attribute-identical.
8. Delete `vpngw-onprem2`, its PIPs, the endpoint VM, and `vnet-onprem2`.
9. Final diff of every layer against **E0**; anything that does not return is an incident, recorded
   in `lessons-learned.md` and escalated to the source lab's owner.

### 11.3 Evidence loss that activation deliberately accepts

Deleting the hub2↔onprem1 pair removes the direct adjacency on which the source lab's **Δ2 prepend
evidence and its S2/S3 failover timings were measured**. The corrected post-activation expectation is
`65003-65515-65002-65002-65002` seen at `vpngw-onprem` via `vpngw-onprem2` and the DCI. That
expectation is US10's, is carried here unchanged, and **must be measured, not assumed** — the
reciprocal Azure-to-Azure case remains masked by the 65515 drop. A complete E0 baseline is the only
protection against this loss, which is why A0 precedes everything.

---

## 12. Operational-complexity scorecard (scored only from E0–E6 evidence)

Scored **1 = trivial … 5 = severe**, per dimension, for the Stage-1 restored baseline and for each
Stage-2 variant. A cell may only be filled from captured evidence or from a counted artefact — never
from an impression. The scorecard is the *desirability* instrument; §13 is the *feasibility* one.

| # | Dimension | How it is counted / measured | Baseline | TP-SQ variant N | TP-SQ variant D |
|---|---|---|---|---|---|
| K1 | **Resource count** | Azure resources and connection objects added vs baseline (§9.4), PIP total, VM total | — | — | — |
| K2 | **Routing domains** | Distinct ASNs in the estate and distinct RIBs an operator must reason about (gateways, Route Servers, NVAs, CPEs) | — | — | — |
| K3 | **Policy locations** | Every place a routing decision is expressed: BIRD filters, ARS route maps, UDR/route tables, connection settings, site-side LOCAL_PREF | — | — | — |
| K4 | **Failure dependencies** | Shared failure domains and single points whose loss changes more than one side; explicitly whether S-B and the backup path share one | — | — | — |
| K5 | **Operational procedures** | Distinct runbooks required: maintenance windows, PSK rotation, BGP reset handling, activation, rollback, failback | — | — | — |
| K6 | **Observability points** | Instruments needed for one end-to-end verification (V1–V11 equivalents), counted per direction | — | — | — |
| K7 | **Convergence behaviour** | Measured seconds to converge and to fail back, **per direction**, against the 180 s hold; plus whether withdrawal is automatic or manual | — | — | — |
| K8 | **Cost** | $/day delta vs the ~$84/day baseline, plus any irreversible surcharge, plus the cost of the *rollback* itself | — | — | — |

**Reading rule.** A high total does **not** by itself reject the square — it produces the verdict
`Technically feasible but operationally unattractive` **only when every §13 feasibility criterion
passed**. A design that fails feasibility is never scored as merely unattractive; it is failed on the
criterion it missed.

---

## 13. Feasibility versus desirability — separate verdicts, separate criteria

**Feasibility is a packet question. Desirability is an operations question. They are decided
independently and reported separately, even when they disagree.**

### 13.1 Feasibility criteria — pass/fail, each measured, none inferred

| # | Criterion | PASS | FAIL |
|---|---|---|---|
| F1 | **Technical reachability** | Outcome A holds at both sites (own region via own side, shortest AS-PATH, any DCI-leaked copy strictly longer). B1 (DC1↔DC2) works. B2 works **for hub address space only**, proven `vm-nva1`↔`vm-nva2` with next-hop type `GlobalVNetPeering` in both directions. B3 reported explicitly as *not delivered* under variant N | Any claimed flow that does not pass; a B2 claim evidenced from a spoke-resident VM; an unintended cross-region hairpin from an AS-PATH tie |
| F2 | **Failover** | The observed post-fault behaviour **matches the bounded-failover contract written before the fault**, flow by flow. Under variant N, "outcome C is *not* delivered" is a **PASS** if it was predicted; under variant D, outcome C converges in both directions | Behaviour differs from the written contract in either direction — *including a flow that survives when the contract said it would not*, which is an unpredicted path and therefore a failure of the contract |
| F3 | **Failback** | The direct path wins back automatically on repair, with no operator action, because the backup advertisement is at least one ASN longer on every hop; nothing left pinned by a UDR | Manual intervention required; a backup path that stays preferred; an aggregation that shortened the AS-PATH |
| F4 | **Symmetry** | V7-equivalent **simultaneous two-ended capture** shows forward and reply on the matching interface pair at both ends, corroborated by V8 interface/firewall counters | One-sided counter growth; asymmetry across any stateful device; symmetry argued from traceroute (L7 is indicative only, never proof) |
| F5 | **Convergence** | Converges within the stated window, **measured separately per direction** (site-to-Azure and Azure-to-site are different events with different timers), polled at 30/60/120/180 s | One-directional convergence; a window exceeded; a route silently absent because it carried 65515 |
| F6 | **Route restoration** | Post-restoration tables are **attribute-identical** to E0 at every layer, per direction — AS-PATH, communities, next hop | Any attribute drift. *A path that pings but returns with a different AS-PATH is a FAIL* |
| F7 | **No collateral damage** | `ars-poland`'s two `0/0` copies, set-C effective routes, and every pre-existing certified flow are unchanged throughout, and Δ2 returns in its direct-adjacency form at rollback | Any change to set-C or default-route state anywhere; Δ2 not restored |

### 13.2 Desirability verdict — the operational-complexity judgement

Scored from §12 **after** F1–F7 are decided. The four possible verdicts, and what it takes to choose
each one:

| Verdict | Chosen when | Evidence required |
|---|---|---|
| **Recommended** | All of F1–F7 PASS **and** the §12 scorecard shows no dimension at 4–5, **and** the delivered outcome set matches what a typical operator of this shape actually needs | Complete E0–E6 set; scorecard fully filled from counted artefacts; the bounded-failover contract written *before* the fault and matched by the instruments |
| **Conditionally viable** | All of F1–F7 PASS, but one or more dimensions score 4–5, **or** the outcome set is sufficient only under stated conditions (e.g. "only if outcome C is not required", "only with a genuinely independent DCI") | Everything above, **plus** the conditions written as testable statements, each traced to the specific evidence that makes it a condition rather than a caveat |
| **Technically feasible but operationally unattractive** | **Every** F1–F7 criterion passes — the packets all arrive — and the scorecard nevertheless shows the burden exceeds the benefit for this estate | Everything above, **plus** an explicit statement that no packet-level criterion failed, so the reader cannot mistake this for a technical rejection. The specific K-dimensions carrying the verdict are named |
| **Platform-blocked** | A required behaviour is not offered by the platform, as opposed to being expensive or awkward | The **verbatim** API error, or the documented platform property, with its exact scope. A limitation observed on a *different* attachment point (e.g. same-gateway ER circuit-to-circuit) may **not** be generalised to the square — US12 makes this distinction explicitly and Stage 2 must preserve it |

**Retention rule — repository-wide.** *Every design is documented with an evidence-based verdict; no
design is deleted because its verdict was unfavourable* (routing rule #30; Jose directive
2026-06-15). Whichever verdict the square receives, US12 stays in the catalogue, this contract stays
in this lab, and the reasoning that produced the verdict is the deliverable. A `Platform-blocked` or
`operationally unattractive` square is exactly as valuable a lab result as a recommended one — and if
the study is never run at all, **that non-execution, with its written justification, is itself the
deliverable**, in the same way T3's is.

---

## Backlinks

- [US10 — Bow-tie dual-site regional affinity with cross-region backup](../dual-hub-hubless-region-ars/route-map-user-stories.md#us10--bow-tie-dual-site-regional-affinity-with-cross-region-backup)
- [US11 — Cross-region reachability without an NVA-to-NVA overlay](../dual-hub-hubless-region-ars/route-map-user-stories.md#us11--cross-region-reachability-without-an-nva-to-nva-overlay)
- [US12 — Square hybrid connectivity: regional DC-to-hub attachment with no diagonals](../dual-hub-hubless-region-ars/route-map-user-stories.md#us12--square-hybrid-connectivity-regional-dc-to-hub-attachment-with-no-diagonals)
- `.squad/decisions.md` — D2, D4, D6 · `.squad/routing.md` — rule #30 (design retention)
- [manifest.md](./manifest.md) · [validation.md](./validation.md) · [README.md](./README.md) ·
  [diagrams/HH-stage-roadmap.mmd](./diagrams/HH-stage-roadmap.mmd)
