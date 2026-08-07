# validation.md — Stage 1 `TP-HH` (T1–T5) + Stage 2 `TP-SQ` (E0–E6): Dual-Hub Interconnect and Route Server Route-Map Policy

## TP-SQ deployed-state certification — 2026-08-07

**Variant N is deployed and ready for manual review.** U3 completed with an INCONCLUSIVE
attribute-observability verdict and was rolled back before TP-SQ. No failure/failback scenario has
been run.

| Check | Result |
|---|---|
| Exact four sides | PASS — S-A DC1↔Hub1, S-B Hub1↔Hub2, S-C Hub2↔DC2, S-D DC1↔DC2 |
| Diagonals absent | PASS — both DC1↔Hub2 connection objects absent; DC2↔Hub1 never created |
| VPN objects | PASS — all six remaining directional connection objects `Connected` / `Succeeded` |
| Hub interconnect | PASS — both global peerings `Connected`, forwarded traffic on, gateway transit/remote gateway off |
| Route Server/NVA | PASS — both local BIRD pairs established; temporary inbound map association absent |
| DC1↔DC2 DCI | PASS — bidirectional ICMP, 0% loss, approximately 27–30 ms |
| Hub1↔Hub2 | PASS — NVA1↔NVA2 bidirectional ICMP, 0% loss, approximately 30–35 ms |
| Site endpoint→hub VNet | **Not delivered under variant N** — both site endpoints received 100% loss to both NVA addresses; effective routes contain the remote site prefix but not a usable hub VNet prefix |
| Failure/failback | NOT RUN — intentionally left for manual review |

Evidence: `show-output/new/square/{e0,preflight,deployment,e1,baseline-cleanup,e2,final}/`.

## Normal reachability and fault results — 2026-08-07

| Scenario | Result |
|---|---|
| Cross-hub spoke-to-spoke | FAIL — TTL loop observed from Spoke B toward Spoke A |
| Spoke A↔DC1 | FAIL — site receives no spoke route |
| Spoke A↔DC2 | FAIL — no return route |
| S-A fault, DC1→Spoke B | FAIL — service absent before and during fault; DC1↔DC2 stayed healthy |
| S-D fault, DC1→Spoke B | FAIL — Azure sides did not replace DCI; DC1↔DC2 also failed |
| Restoration | PASS — all six connection objects `Connected`; DC1↔DC2 restored to 0% loss |

Full analysis: [`square-reachability-and-faults.md`](./square-reachability-and-faults.md).

**Status: U0, T1/U1, U1.5 and T2a/U2 executed and PASSED on 2026-08-06, approved by Jose Moreno.**
U1.5 and T2a/U2 were independently verified live (read-only) by Niobe on 2026-08-06 —
`.squad/decisions/inbox/niobe-u15-u2-verification.md`. T2b–T5 (U3–U5) remain **not run** — see
their sections below. This document's overall scope (full Stage 1 bow-tie) is **not** complete;
only the U0/U1/U1.5/U2 subset has been executed. This document is the evidence plan; results are
populated only after Jose approves each scenario's execution per `manifest.md` §Approval gate.

**Two stages.** Scenarios **T1–T5** are Stage 1 (TP-HH). The **E0–E6 / Q1–Q6** evidence plan for
Stage 2 (TP-SQ — the US12 square-hybrid feasibility study) is at the end of this file and is gated
behind G1–G4; it cannot begin until Stage 1 is complete *and rolled back*.

## Evidence layers (L1–L8)

| Layer | What it captures | Tooling |
|---|---|---|
| L1 | Gateway (`vpngw-hub1`/`vpngw-hub2`/`vpngw-onprem`) BGP peer status + learned routes | `az network vnet-gateway list-bgp-peer-status`, `list-learned-routes` |
| L2 | Route Server (`ars-hub1`/`ars-hub2`) peering state + learned routes | `az network routeserver peering list`, `list-learned-routes` |
| L3 | NVA RIB (BIRD) | `birdc show protocols all`, `birdc show route all` |
| L4 | Effective routes on endpoint NICs | `az network nic show-effective-route-table` |
| L5 | Data-plane forensics | `tcpdump` on NVA subnets; interface + firewall counters |
| L6 | Ping matrix | Continuous probe spanning each change operation |
| L7 | Traceroute — **indicative only, never a symmetry proof** | `traceroute`/`tracepath` |
| L8 | Timing | Captured at 30 / 60 / 120 / 180 s after each change |

**Before/after diff discipline.** Every scenario captures a "before" snapshot immediately before the
change and an "after" snapshot immediately following it; the diff between the two, not a narrative
description, is the evidence. **Non-effect assertions are first-class** — for T1, the primary
evidence is "nothing moved", and the before/after diff must show byte-identical ARS/gateway learned
routes to be a PASS.

**Fresh-baseline requirement — re-anchored 2026-08-05 (post-Poland cleanup).** The files under
`show-output/inherited/` are context, **not** the diff reference, and they are now doubly stale: the
bed has had the 2026-08-05 hub1/hub2 route-map tier upgrade *and* the Poland cleanup (29/29 objects
deleted) since they were captured (2026-08-03 pre-Δ3, 2026-08-04 post-Δ3-via-BIRD). Two specific
consequences:

- **The Δ2 control signature `65002-65002-65002` is retired.** It rode on the set-C prefixes
  `10.31.0.0/24`/`10.32.0.0/24`, which were deleted with Poland and can never reappear. It may no
  longer be used anywhere as a "must not move" control. Its replacement is byte-comparison against
  the fresh post-U0 baseline captured under `show-output/new/u0-vm-start/`.
- **All five VMs are `VM deallocated` as of 2026-08-05**, so every ARS learned/advertised set is
  empty and every BIRD session is down. **No L2 or L3 evidence can be captured until U0 runs.**

T1/U1 and T2/U2 must each still capture their own fresh pre-change baseline at execution time, under
`show-output/new/t1-hub-peering/` and `show-output/new/t2-routemap-assoc/` respectively — but both
are now anchored to the U0 baseline, not to `show-output/inherited/`. *(As executed, U1's evidence
landed under `show-output/new/u0-u1/`, and U1.5/U2's under `show-output/new/u15-u2/` — see §T1 and
§U1.5/§T2a-U2 below for the actual paths.)*

---

## U0 — NVA power-on and fresh post-cleanup baseline (prerequisite to everything)

**Status: EXECUTED 2026-08-06. Result: PASS-with-note.** Executed by Tank, approved by Jose Moreno.
Evidence under `show-output/new/u0-u1/{pre,post-u0}/` (this session used the `u0-u1` evidence tree,
not `u0-vm-start/`, since U0 and U1 were approved and executed together as "U0 + conditional U1").

Scope: `az vm start` on **`vm-nva1` and `vm-nva2` only**. `vm-hub1-ep`, `vm-hub2-ep` and
`vm-onprem-ep` stay deallocated. Wait **10 minutes** after boot before capturing.

| Layer | Evidence file (under `show-output/new/u0-vm-start/`) |
|---|---|
| L0 | `00-pre-vm-power-states.json`, `04-post-vm-power-states.json` (`az vm list -d` power state only) |
| L2 | `01-post-ars-hub1-peer-nva1-learned.json`, `01-post-ars-hub1-peer-nva1-advertised.json`, mirrored for `ars-hub2`/`peer-nva2` — these are the **new reference sets** |
| L3 | `02-post-nva1-bird-show-protocols-all.txt`, `02-post-nva2-bird-show-protocols-all.txt` — **must include the route-refresh capability line**; this is the gate on U1 |
| L3 | `02-post-nva1-bird-conf.txt`, `02-post-nva2-bird-conf.txt` — capture the hand-edited on-disk config, which is **not** in version control |
| L3 | `02-post-nva1-bird-route-table.txt`, `02-post-nva2-bird-route-table.txt` |
| L1 | `03-post-vpngw-hub1-advertised-to-onprem.json`, `03-post-vpngw-hub2-advertised-to-onprem.json`, `03-post-vpngw-onprem-learned.json` |
| L1 | `03-post-vpngw-hub1-bgp-peer-status.json`, `03-post-vpngw-hub2-bgp-peer-status.json` (ARS instances must leave `Connecting`) |
| L4 | `05-post-nva1-nic-effective-routes.json`, `05-post-nva2-nic-effective-routes.json` |
| L8 | `06-timing.txt` (start issued → running → BGP established, per VM) |

**PASS.** Both NVAs `VM running`; `ars_hub*_0/1` BGP sessions `Established`; ARS learned/advertised
sets non-empty on both hubs; `vpngw-onprem` learns hub/spoke prefixes again; route-refresh
capability recorded for both NVAs.

**PASS-with-note.** All of the above except that `ars_poland_0/1` sit in `Connect`/`Active` — this
is **expected** (their peers `10.30.0.4/.5` were deleted) and is not a failure. No Poland prefix may
appear anywhere.

**FAIL.** A VM does not reach `running`; a session does not establish; or route-refresh capability
cannot be read — in which case **U1 does not proceed**.

**Rollback.** `az vm deallocate` on both, 2–5 min, returning exactly to the 2026-08-05 state.

### Actual result (2026-08-06)

**PASS-with-note.** Both `vm-nva1`/`vm-nva2` reached `VM running`. `ars_hub1_0/1` and `ars_hub2_0/1`
BGP sessions reached `Established` within seconds of BIRD daemon start (well under the 30–90 s
estimate). Route-refresh capability confirmed present on both local and neighbor sides for all four
sessions (the U1 gate requirement) — see
`show-output/new/u0-u1/post-u0/01-nva1-bird-protocols-all.txt` and `01-nva2-bird-protocols-all.txt`.
`ars_poland_0/1` sit in `Connect` on both NVAs — expected, harmless, matches this section's own
PASS-with-note clause. All four VPN connections remained `Connected` throughout.

**Note (new finding, not anticipated by this plan):** both NVAs' hand-edited `/etc/bird/bird.conf`
(still not in version control) contain a **stale static route `10.30.0.0/27`** — the former Poland
RouteServerSubnet shape — in addition to the expected `10.10.0.64/27`/`10.20.0.64/27` and `0.0.0.0/0`.
This stale prefix is genuinely re-learned by `ars-hub1`/`ars-hub2` (the export filter only strips
AS 65515, it does not filter by prefix) but is **contained**: it does not appear in ARS's advertised
routes back to the NVA, does not reach `vpngw-hub1`/`vpngw-hub2` (whose BGP session to their local
ARS instance is pre-existing, permanently `Connecting` — not caused by U0/U1), and does not reach
`vpngw-onprem`. It is visible only in each NVA's own NIC effective-route table
(`nextHopType: VirtualNetworkGateway`) within its own hub VNet. Whether it propagates further into
`vnet-spoke-a`/`vnet-spoke-b` could not be verified in this session because the spoke endpoint VMs
were correctly left deallocated per the strict U0/U1 scope — **flagged as an open item for a future,
separately-approved unit**, not a blocker for U0/U1 (see `lessons-learned.md`). This also means the
manifest's assumption that NVA1 "re-originates `10.10.0.64/27`" into ARS does not hold as written:
that prefix does **not** appear in ARS's learned-routes set (Azure Route Server appears to reject a
route matching its own RouteServerSubnet), while the unrelated `10.30.0.0/27` does. This correction
should be reviewed against `manifest.md`'s live-state table before any future T2b work.
**Resolution (Trinity, 2026-08-06):** this finding is `TANK-001`. The stale state is removed by the
new prerequisite unit **U1.5** (§U1.5 below, contract in `nva-config/README.md`), and the dead
`10.10.0.64/27` target has been replaced for U3 by an injected TEST-NET-2 documentation prefix
(§T2b below). Both `manifest.md` and `design.md` §8a have been corrected.
Evidence: `show-output/new/u0-u1/post-u0/` (full bundle, including `bird.conf` captures for both
NVAs) and cross-checked against `pre-u1/` and `post-u1/` (byte-identical ARS/gateway sets — see T1
actual result below).

---

## T1 — No-overlay native global-peering baseline

**Status: EXECUTED 2026-08-06. Result: PASS.** Executed by Tank, approved by Jose Moreno. Evidence
under `show-output/new/u0-u1/{pre-u1,post-u1}/` (used the `u0-u1` combined evidence tree — see U0
note above — rather than `t1-hub-peering/`).

| Layer | Evidence file (under `show-output/new/t1-hub-peering/`) |
|---|---|
| L1 | `00-pre-vpngw-hub1-learned.json`, `00-pre-vpngw-hub2-learned.json`, `01-post-vpngw-hub1-learned.json`, `01-post-vpngw-hub2-learned.json` |
| L2 | `00-pre-ars-hub1-peer-nva1-learned.json`, `00-pre-ars-hub2-peer-nva2-learned.json`, `01-post-ars-hub1-peer-nva1-learned.json`, `01-post-ars-hub2-peer-nva2-learned.json` |
| L3 | `00-pre-nva1-bird-status.txt`, `00-pre-nva2-bird-status.txt`, `01-post-nva1-bird-status.txt`, `01-post-nva2-bird-status.txt` (route-refresh capability recorded here) |
| L4 | `01-post-nva1-nic-effective-routes.json`, `01-post-nva2-nic-effective-routes.json` (exactly one new `GlobalVNetPeering` entry expected) |
| L6 | `02-ping-matrix-continuous.txt` (`vm-nva1` ↔ `vm-nva2`, spanning the peering-create operation) |
| L8 | `03-timing.txt` (peering `Connected`/`FullyInSync` timestamps both sides) |
| Peering objects | `04-peering-hub1-to-hub2.json`, `04-peering-hub2-to-hub1.json` |

**PASS criteria:** see `manifest.md` §T1. **Explicitly not tested:** spoke prefixes, ARS-learned
prefixes, gateway-learned prefixes crossing the peering — their absence is the expected result.

### Actual result (2026-08-06)

**PASS.** `peer-hub1-to-hub2` and `peer-hub2-to-hub1` both created with exactly the four required
flags (`allowVirtualNetworkAccess=true`, `allowForwardedTraffic=true`, `allowGatewayTransit=false`,
`useRemoteGateways=false`) and both reached `peeringState=Connected`/`peeringSyncLevel=FullyInSync`
within ~15–60 s (re-confirmed stable, unchanged, at a T+~20 min re-check).
`vm-nva1` (10.10.1.4) ↔ `vm-nva2` (10.20.1.4) ICMP: 0% loss both directions post-peering (100% loss
confirmed pre-peering). Each NVA NIC's effective-route table gained **exactly one** new
`VNetGlobalPeering` entry for the remote hub's `/16` (`10.20.0.0/16` on nva1, `10.10.0.0/16` on
nva2) — no other route changed. `ars-hub1`/`ars-hub2` learned+advertised sets, `vpngw-hub1`
advertised-to-onprem, and `vpngw-onprem` learned routes were **byte-identical** pre- vs post-peering
— confirms non-transitivity (spoke and ARS/on-prem prefixes did not become reachable via the hub
peering). Both spoke peerings (`peer-hub1-to-spoke-a`, `peer-hub2-to-spoke-b`) unchanged. All four
VPN connections remained `Connected`. No route-map association exists on either `ars-hub1`/`peer-nva1`
or `ars-hub2`/`peer-nva2` (routingConfiguration carries only empty `staticRoutes` — T2/U2 untouched).
BIRD session `Since` timestamps identical from post-U0 through the T+20 min stability check — no
session flap caused by the peering create. Evidence: `show-output/new/u0-u1/pre-u1/`,
`post-u1/` (peering objects, NIC routes, ping tests, diffs, stability re-check).
**Rollback:** not exercised — no rollback-trigger condition was met.

---

## U1.5 — remove retired Poland BIRD state from both NVAs

**Status: EXECUTED 2026-08-06 — PASS on both NVAs.** Approved by Jose Moreno; executed by Tank;
independently verified live (read-only) by Niobe on 2026-08-06 —
`.squad/decisions/inbox/niobe-u15-u2-verification.md`. Prerequisite for U2 and U3, raised by finding
`TANK-001` (`lessons-learned.md`), which U0 discovered and which invalidated the previous U3
target-prefix assumption. Full remediation contract, including the exact statements removed, the
backup/restore method, the syntax-validation gate and the reload semantics: **`nva-config/README.md`
§U1.5**. Evidence directory: `show-output/new/u15-u2/` (`pre/`, `u15-nva1/`, `u15-nva2/`, `b1/`).

**What it changes.** BIRD configuration only, on `vm-nva1` and `vm-nva2`. **No Azure resource is
created, modified or deleted.** Cost delta **$0**.

**Exact removals** — quoted from `show-output/new/u0-u1/post-u0/02-nva{1,2}-bird-conf.txt`, using
BIRD's actual configured protocol names, not guessed ones:

| Host | Removed | Route effect |
|---|---|---|
| `vm-nva1` | `route 10.30.0.0/27 via 10.10.1.1;` (in `protocol static` → `static1`) | **the only one** — withdraws `10.30.0.0/27` from `ars-hub1` |
| `vm-nva1` | `protocol bgp ars_poland_0` (neighbor `10.30.0.4`, multihop 4) | none — stuck in `Connect` |
| `vm-nva1` | `protocol bgp ars_poland_1` (neighbor `10.30.0.5`, multihop 4) | none — stuck in `Connect` |
| `vm-nva1` | `filter export_to_poland_ars { accept; }` | none — unreferenced after the two above |
| `vm-nva2` | `route 10.30.0.0/27 via 10.20.1.1;` | **the only one** — withdraws `10.30.0.0/27` from `ars-hub2` |
| `vm-nva2` | `protocol bgp ars_poland_0`, `protocol bgp ars_poland_1` | none — stuck in `Connect` |
| `vm-nva2` | `filter export_to_poland_ars { if net = 0.0.0.0/0 then { prepend 65002 ×2 } accept; }` | none — unreferenced |
| `vm-nva2` | the clause `if net ~ [ 10.31.0.0/24, 10.32.0.0/24 ] then { prepend 65002 ×2 }` **inside** `filter export_to_hub2_ars` | **provably none** — the retired Δ2 signature; neither prefix exists in `master4`, so export re-evaluation emits no update |

**Never removed:** `route 0.0.0.0/0` (spoke UDR target), `route 10.10.0.64/27` / `10.20.0.64/27`
(out of scope), `bgp_path.delete(65515)`, `device`/`direct`/`kernel`, `ars_hub1_0/1`, `ars_hub2_0/1`.

**Method, in order, per NVA — `vm-nva1` first, fully verified, only then `vm-nva2`:**
backup (`cp -p` + `sha256sum`) → stage to `/etc/bird/bird.conf.u15` → **blocking syntax gate**
(`bird -p -c` *and* `birdc configure check`, both must pass) → `cp -p` over the live file →
**`birdc configure`** (graceful; unchanged protocols are reconfigured in place and do **not**
restart). **`systemctl restart bird` is forbidden** — it resets every session and black-holes both
spokes' `0.0.0.0/0`.

| Layer | Evidence file (under `show-output/new/u15-u2/{pre,u15-nva1,u15-nva2}/`) | PASS |
|---|---|---|
| L3 | `00-pre-nva1-bird-protocols-all.txt`, `03-post-nva1-bird-protocols-all.txt` (+ nva2) | `ars_poland_*` absent post-change; `ars_hub*_0/1` `Established` with **unchanged `Since`** — the no-flap proof |
| L3 | `00-pre-nva1-bird-route-all.txt`, `03-post-nva1-bird-route-all.txt` (+ nva2) | `10.30.0.0/27` gone; `0.0.0.0/0` and the local `/27` still present |
| L3 | `00-pre-nva1-bird-conf-backup.txt`, `01-nva1-syntax-check.txt`, `02-nva1-configure-output.txt` (+ nva2) | backup path + both sha256s recorded; both syntax checks pass **before** any apply |
| L2 | `00-pre-ars-hub1-peer-nva1-learned.json`, `04-post-…-learned.json` (+ hub2) | `10.30.0.0/27` gone from **both** `RouteServiceRole_IN_0` and `_IN_1`; `0.0.0.0/0` unchanged; the `10.40.0.0/16` boomerang on `_IN_1` unchanged |
| L2 | `00-pre-…-advertised.json`, `04-post-…-advertised.json` (+ hub2) | **byte-identical** |
| L1 | `00-pre-/06-post-vpngw-hub{1,2}-advertised-to-onprem.json`, `…-vpngw-onprem-learned-routes.json` | **byte-identical** (non-regression, not removal — the prefix never reached them) |
| L1 | `00-pre-/07-post-vpn-connections-status.json` | all four `Connected`, 4 tunnels each, throughout |
| L4 | `00-pre-/05-post-nva{1,2}-nic-effective-routes.json` | the `10.30.0.0/27` `VirtualNetworkGateway` entry **gone**; the U1 `VNetGlobalPeering` entry unchanged. **Cleanest single proof** |
| L6 | `08-ping-nva1-to-nva2-continuous.txt` | 0% loss spanning both reloads |
| L8 | `09-timing.txt` | reload → withdrawal observed, sampled 30/60/120/180 s |

**Result: PASS on both NVAs — confirmed.** Exactly one prefix moved — `10.30.0.0/27`, withdrawn from
both instances of both Route Servers — and every other captured surface is byte-identical, with **no
BGP session reset** (`ars_hub1_0/1` and `ars_hub2_0/1` `Since` unchanged pre/post). Per-NVA evidence
and PASS confirmation: `show-output/new/u15-u2/u15-nva1/13-diff-summary.md`,
`show-output/new/u15-u2/u15-nva2/13-diff-summary.md`. Independently re-verified live (not just from
files) by Niobe on 2026-08-06.

**PASS-with-note (not triggered).** The rollback trigger for a session reset was not met on either
NVA — both `ars_hub1_0/1` and `ars_hub2_0/1` `Since` timestamps are unchanged from before the change,
confirmed both from capture and from a live re-check.

**FAIL / rollback trigger.** Any of the eight triggers in `nva-config/README.md` §6 — most
importantly: an `ars_hub*` session not `Established`, `0.0.0.0/0` missing from an ARS learned set at
T+60 s, non-zero NVA↔NVA ICMP loss, any gateway/on-prem set changing, or **any** prefix other than
`10.30.0.0/27` moving.

**Rollback.** **Not exercised — no trigger was met.** Would have been `birdc configure undo` (fast)
or restore `/etc/bird/bird.conf.pre-u15.<STAMP>` and `birdc configure` (durable). A second restore
source is in version control: `nva-config/bird-nva{1,2}.as-found-2026-08-06.conf`.

**Durable outcome — confirmed.** After U1.5, `nva-config/bird-nva{1,2}.u15-target.conf` are the
authoritative configs, and match the live `/etc/bird/bird.conf` on each host byte-for-byte (Niobe,
2026-08-06). The "BIRD is hand-edited and not in version control" gap recorded in `manifest.md`
§Live-state reconciliation and `design.md` §8a(c) is closed.

---

## T2 — Hub-local ARS↔NVA route-map association and route modification

**Status: EXECUTED 2026-08-06 — T2a/U2 PASS.** Approved and scheduled in its own maintenance window,
strictly after U1.5 passed and settled (per the rule below). Independently verified live (read-only)
by Niobe on 2026-08-06 — `.squad/decisions/inbox/niobe-u15-u2-verification.md`. T2b (U3a/U3b) and
onward remain **not run**.

**Scope narrowing (Phase 4, revised 2026-08-06).** T2a/U2 runs on **`ars-hub1`/`peer-nva1` only**,
using a dedicated temporary map **`rm-hub1-tmp-assoc`** (not `rm-hub1-activate`, which is not empty
and whose tier-activation provenance must be preserved). The `ars-hub2` mirror (T2a′) is a separate
approval. The write is a **`PUT`** on `virtualHubs/ars-hub1/bgpConnections/peer-nva1` carrying
`peerAsn`, `peerIp` and the **full** `routingConfiguration` — **not** a PATCH, and **not** a write
to the route map's read-only `associatedInboundConnections`.

### T2a/U2 — the association is the experiment; it must have no route effect

**Match prefix changed to `203.0.113.0/24`** (RFC 5737 TEST-NET-3), from `192.0.2.0/24`.
`192.0.2.0/24` is already the match prefix of `rm-hub1-activate`'s `rule-activate-synthetic`; two
coexisting maps on the same Route Server keyed on the same prefix make any observed — or absent —
effect ambiguous about which artefact caused it. TEST-NET-3 was verified absent from every live
surface by read-only capture on 2026-08-06: `ars-hub1` learned from `peer-nva1` =
`{0.0.0.0/0, 10.30.0.0/27, 10.40.0.0/16}`; `ars-hub1` advertised =
`{10.10.0.0/16, 10.11.0.0/24, 10.40.0.0/16}`; `vm-nva1` BIRD `master4` =
`{0.0.0.0/0, 10.11.0.0/24, 10.30.0.0/27, 10.10.0.64/27, 10.10.0.0/16, 10.10.1.0/27, 10.40.0.0/16}`;
`vpngw-onprem` learned = `10.40.0.0/16` + BGP-peer `/32`s. Under `Equals`, nothing in this bed can
ever match — **the association is inert by construction**, and TEST-NET-2 `198.51.100.0/24` is
reserved for U3a and must not be used here.

**PUT body preservation — mandatory, and the reason the previous placeholder was wrong.**
`Microsoft.Network/virtualHubs/bgpConnections` defines **no PATCH operation**, so the PUT body
**replaces `properties` wholesale: anything omitted is lost.** The live GET on 2026-08-06 returned:

```json
"properties": {
  "peerAsn": 65001,
  "peerIp": "10.10.1.4",
  "provisioningState": "Succeeded",
  "routingConfiguration": {
    "vnetRoutes": {
      "staticRoutes": [],
      "staticRoutesConfig": {
        "propagateStaticRoutes": true,
        "vnetLocalRouteOverrideCriteria": "Contains"
      }
    }
  }
}
```

The body is therefore **derived, never authored**:

1. `GET …/bgpConnections/peer-nva1?api-version=2024-10-01`; save the response verbatim as
   `00-pre-peer-nva1-GET.json` — this file is both the evidence and the rollback source.
2. Take `response.properties` exactly as returned.
3. Delete **only** the read-only member `provisioningState`.
4. Add `routingConfiguration.inboundRouteMap.id`.
5. Send `{"properties": <that object>}`. Do **not** put `id`, `name`, `type` or `etag` in the body.
6. Pass the GET's `etag` as an `If-Match` header, so a concurrent change fails the write rather
   than silently overwriting it.

**`vnetRoutes` — including `staticRoutesConfig` — must survive the round trip.** Omitting it would
silently reset `propagateStaticRoutes` and `vnetLocalRouteOverrideCriteria` to service defaults,
which is a routing-behaviour change U2 has no mandate to make and no criterion that would catch.

| Layer | Evidence file (under `show-output/new/u15-u2/u2/`, actual filenames) |
|---|---|
| API | `00-pre-peer-nva1-GET.json` (**the derivation source and the rollback body**), `01-routemap-tmp-assoc-hub1-put-response.json`, `02-bgpconn-assoc-put-response.json` + `02-put-timing.txt`, `03-post-peer-nva1-GET.json` |
| L2 | `04-post-ars-hub1-peer-nva1-learned.json` / `05-post-ars-hub1-peer-nva1-advertised.json` (byte-compared against the **post-U1.5 baseline B1**; the Δ2 `65002-65002-65002` control no longer exists) |
| L3 | `07-bird-session-timeline-nva1.txt` (session `Since` must be unbroken, or the reset duration recorded per PASS-with-note); `08-routemap-inventory-hub1.json` |
| L1 | `06-post-vpn-connections-status.json` (all four still `Connected`) |
| L6 | `09-ping-nva1-to-nva2-post-u2.txt` (zero loss confirmed) |

**Result: PASS — confirmed.** Association `provisioningState: Succeeded`; `ars-hub1`'s learned
**and** advertised sets **byte-identical** to the post-U1.5 baseline B1 (`Compare-Object` across all
9 comparable capture files → 0 differences, re-computed independently by Niobe, not taken on trust);
`03-post-peer-nva1-GET.json` shows `vnetRoutes` and `staticRoutesConfig` unchanged and
`inboundRouteMap` present (`rm-hub1-tmp-assoc`); all four VPN connections `Connected`; `ars_hub1_0/1`
`Since` unchanged — **no session reset**; `rm-hub1-activate` and all of `ars-hub2` untouched.
**API trap avoided:** captured and re-verified with `api-version=2024-10-01`; `2024-05-01` omits
`routingConfiguration` from the response and would make the association look absent. **Route maps
for Azure Route Server are a preview feature** — this result is a preview observation, not a GA
behavioural guarantee. **Association left ACTIVE — not rolled back**, per plan, as the required
precondition for U3a/U3b. Full evidence: `show-output/new/u15-u2/u2/10-diff-summary.md`.

**PASS-with-note (not triggered).** No BGP session reset occurred, so this alternate outcome does not
apply. **FAIL (not triggered).** The API did not reject the write; no route moved; `vnetRoutes`/
`staticRoutesConfig` came back unchanged.

**Rollback.** **Not exercised — the association is intentionally left active** as the required
precondition for U3a/U3b (`rollback-if-any/README.md` records only that the path was prepared, never
invoked). If ever needed: PUT `00-pre-peer-nva1-GET.json`'s `properties` back (minus `provisioningState`,
without `inboundRouteMap`), then DELETE `rm-hub1-tmp-assoc`. `rm-hub1-activate` and all of
`ars-hub2` are never touched. 2–5 min.

### T2b — real modification (only after U2 **and** U3a pass)

**Target prefix changed: `10.10.0.64/27` → `198.51.100.0/24`.** This is the single most important
correction from finding `TANK-001`. `10.10.0.64/27` is present in `vm-nva1`'s `bird.conf` and is
exported through `export_to_hub_ars` identically to every other static, yet it **never appears** in
`ars-hub1`'s learned-route set (`show-output/new/u0-u1/post-u0/`, re-confirmed live 2026-08-06) —
Azure Route Server silently rejects a route matching its own RouteServerSubnet. An inbound route map
keyed on it could therefore **never match**: T2b would have "run", returned `Succeeded`, and proven
nothing, while reading as a PASS. The prefix is **⛔ invalid as a test target** and is retained in
BIRD only because removing it is out of U1.5's scope.

**No already-advertised prefix is a safe substitute.** Post-U1.5 `ars-hub1` learns only
`0.0.0.0/0` — forbidden, it is the spoke UDR target and modifying it risks `DEF-001` — and
`10.40.0.0/16` — forbidden, it is the on-prem prefix and, being present on `RouteServiceRole_IN_1`
only, any observed diff would be instance-asymmetric and unfalsifiable. `10.30.0.0/27` is removed by
U1.5 and must not be resurrected to serve as a target.

**Therefore U3 is split into two approval steps:**

- **U3a — inject a harmless documentation prefix.** On `vm-nva1` only, add
  `protocol static u3_doc_test { ipv4; route 198.51.100.0/24 blackhole; }`
  (`nva-config/bird-nva1.u3a-doctest.snippet.conf`), apply with `birdc configure`, settle, and
  capture baseline **B3**. `198.51.100.0/24` is RFC 5737 TEST-NET-2: globally non-routable, absent
  from every live surface in this bed, and deliberately distinct from both `192.0.2.0/24`
  (`rm-hub1-activate`) and `203.0.113.0/24` (U2) so no piece of evidence is ever ambiguous about
  which artefact produced it. `blackhole` — not `via <gw>` — so the route is BGP-visible but can
  never carry traffic. Evidence: `show-output/new/u3a-doc-prefix/`. **U3a's own PASS requires
  proving containment**: the prefix must appear at both `ars-hub1` instances with AS-PATH `65001`
  and must **not** appear in `vpngw-hub1`/`vpngw-hub2` advertised routes or in `vpngw-onprem`'s
  learned routes.
- **U3b — apply the visible attribute change.** Modify `rm-hub1-tmp-assoc` (already associated by
  U2) to match `198.51.100.0/24` and `Add` AS-Path `[64496, 64496]`, observe, then roll back.

**ASN validity.** `64496` is the RFC 5398 **2-byte documentation** ASN. Route maps accept 2-byte
ASNs only; Azure rejects private (`64512`–`65534`) and reserved (`8074`, `8075`, `12076`, `65515`,
`65517`–`65520`) values for prepending, and `64496` is in neither set. Microsoft's own prepend
walkthrough uses `64511` from the same documentation block. **Do not** substitute `65001`, `65002`,
`65000` or `65515` — those are live in this bed and would corrupt the evidence as well as risk
rejection.

| Layer | Evidence file (under `show-output/new/t2-routemap-assoc/`) |
|---|---|
| L2 | `10-pre-hub1-map-rule.json`, `11-post-hub1-map-rule-applied.json` — AS-Path `Add [64496,64496]` on **`198.51.100.0/24` only**; expected observed AS-PATH **`64496-64496-65001`** on both ARS instances; every other prefix byte-identical to B3 |
| L2 | `13-post-ars-hub1-advertised.json` — the modified prefix must still not be advertised onward |
| L1 | `14-post-vpngw-onprem-learned-routes.json` — `198.51.100.0/24` still absent (containment holds under the map) |
| L4 | `12-post-effective-routes-hub1-ep.json` (NIC-scoped; `vm-hub1-ep` is deallocated, so this is captured from `vm-nva1`'s NIC unless the endpoint VM is separately approved for start) |

**Known evidence-fidelity risk — declare before running, do not rationalise after.** It is **not
established** whether `az network routeserver peering list-learned-routes` reports the AS-PATH
*after* inbound route-map processing or *as received on the wire*. If neither the CLI nor the portal
Route Map dashboard shows `64496-64496-65001` while the map itself reports `Succeeded`, the correct
outcome is **INCONCLUSIVE — tooling visibility, not FAIL**: U2 already stands as the association
proof. **Do not** retry against a production prefix to force visibility. A softer alternative that
carries the same risk but a smaller blast radius is `Add` community `64496:100` instead of AS-Path.

**Rollback.** PUT `10-pre-hub1-map-rule.json` back (restores the inert `203.0.113.0/24` rule → U2
state); then, to reach the U1.5 state, dissociate per T2a rollback and remove the `u3_doc_test`
block from BIRD per `rollback.ps1 -Scenario U3a`. Order matters: roll back U3b **before** U3a.

**PASS/FAIL criteria:** see `manifest.md` §T2. RM-A/RM-B eligibility table (D2) and E-1/E-2
definitions reproduced from the source catalogue, wording preserved verbatim:

> Source: [`route-map-user-stories.md` — US10, RM-A/RM-B rows](../dual-hub-hubless-region-ars/route-map-user-stories.md#us10--bow-tie-dual-site-regional-affinity-with-cross-region-backup) —
> *"Supporting — eligible but unassociated on ARS↔NVA peerings; gateway-connection attachment
> unverified."* This wording (the Oracle overclaim-fix, 2026-08-05) must not regress to "proven
> association" anywhere in this lab's own results.

---

## T3 — Dynamic inter-hub NVA BGP/tunnel variant

**Status: NOT RUN. Conditional — may never run; non-execution is itself a valid deliverable if the
justification test in `design.md` §6 is not met.**

| Layer | Evidence file (under `show-output/new/t3-nva-bgp/`, if run) |
|---|---|
| L2 | `00-pre-ars-poland-peer-nva1-learned.json`, `00-pre-ars-poland-peer-nva2-learned.json` (control captures — must stay unchanged), `01-post-*` |
| L3 | eBGP session state on both NVAs; prefix policy filter config (deny `0.0.0.0/0`, deny `10.31.0.0/24`/`10.32.0.0/24` explicitly verified in the filter, not merely intended) |
| L4 | `02-post-vm-c1-ep-effective-routes.json` (`0.0.0.0/0 → 10.10.1.4` must be unchanged — control capture only, Poland is out of scope) |
| L8 | `03-withdrawal-timing.txt` (BGP hold-window withdrawal + failback timing) |

**Hard FAIL triggers:** any set-C or default-route change anywhere; one-directional convergence; a
route silently absent because it carried 65515.

---

## T4 — Policy placement: ARS route map vs NVA BIRD policy

**Status: NOT RUN.**

| Layer | Evidence file (under `show-output/new/t4-policy-placement/`) |
|---|---|
| L2 | Route-map RIB outcome for the AS-Path Add case (reuses T2b evidence) |
| L3 | BIRD filter RIB outcome for the identical intent, expressed independently |
| — | `01-comparison-table.md` — observability, blast radius, reversibility, version-control story, failure modes, side by side |
| — | `02-65515-map-inexpressible.txt` — the exact error/absence recorded when a route map is asked to strip 65515 or rescue a discarded route |

**PASS criteria:** both control points produce the same RIB outcome for the map-expressible intent;
the 65515 case is demonstrated (not asserted) as map-inexpressible.

---

## T5 — Local VPN-gateway connection route-map attachment

**Status: NOT RUN. Optional. Unverified. Runs only after T2a passes, and only with separate explicit approval.**

**Phase-4 split (U4).** **Step 1 is read-only and may be bundled with U0/U1 at zero write risk:**
enumerate the ARS → *route maps* → **Apply route maps** blade verbatim and record
`Get-Module -ListAvailable Az.Network`. **Step 2 (the write) is proposed only if Step 1 shows an
eligible same-VNet gateway connection**, and it may well not — the live model exposes no
ARS↔VPN-gateway connection object (`ars-hub1` has no connection children beyond
`bgpConnections/peer-nva1` and `routeMaps/*`; the four `Microsoft.Network/connections` resources use
the `VirtualNetworkGatewayConnection` schema, which has no `inboundRouteMap`/`outboundRouteMap`
member, and their live `routingConfiguration` is `{}`).

| Layer | Evidence file (under `show-output/new/t5-gwconn-assoc/`, if run and approved) |
|---|---|
| L1 | `00-pre-vpngw-hub1-connections.json`, `00-pre-vpngw-hub2-connections.json` (all `Connected`) |
| — | `01-api-semantics-probe.md` — **Step 1, read-only**: verbatim portal *Apply route maps* list, `Get-Module -ListAvailable Az.Network` version, and the observed `New-AzRouteMap`/`Update-AzRouteMap` parameter set. Recorded **before** any write is proposed |
| — | `02-assoc-request-response.json` — Step 2 only |
| L1 (post) | `03-post-vpngw-hub1-connections.json`, `03-post-vpngw-hub2-connections.json` (must remain all `Connected`) |

**Unverifiable outcome is a valid result.** If Step 1 finds no eligible connection, write
*"RM-C/RM-D unverifiable in this bed — no addressable ARS↔VPN-gateway connection resource exists"*
into `01-api-semantics-probe.md`, do **not** run Step 2, and close gate G4 on T2a's result alone.

**FAIL handling:** if the API rejects the association, record the exact error code verbatim; RM-C/RM-D
are then reclassified as unsupported in the original lab's catalogue (Oracle's task, not this lab's).

---

## Migration gaps

No named source file from Morpheus's file-action table (§8, rows 14–16 of the extraction contract)
was missing or ambiguous. All 25 files (11 `route-map-upgrade/` + 12 `baseline-pre-delta3/` subset +
2 `delta3-bird/` subset) were found at their exact named paths and copied with provenance headers to
`show-output/inherited/`. **No migration gap to record for this pass.**

If a future scenario execution requires an evidence file not covered by this inheritance (e.g. a
`vpngw-onprem`-side capture), it must be **referenced** from the original lab's `show-output/`
(§4c of the extraction contract), not duplicated — see README.md and the source lab's `deploy-log.md`
for the authoritative location.

**Note on incidental Poland/set-C content inside inherited evidence (sanitization clarification):**
Several of the 12 hub-scoped `baseline-2026-08-03/` captures (e.g. `02-ars-bgp-peerings.json`,
`06-ars-hub1-peer-nva1-learned.json`, `07-ars-hub2-peer-nva2-learned.json`,
`10-vpngw-hub1-learned-routes-summary.txt`, `11-vpngw-hub2-learned-routes-summary.txt`,
`13-effective-routes-hub1-ep.json`, `19-nva1-nic-effective-routes.json`) and two `route-map-upgrade/`
files (`02-nva1-bird-post-delta3.txt`, `02-post-ars-hub2-peer-nva2-learned.json`,
`17-nva1-bird-status.txt`, `18-nva2-bird-status.txt`) legitimately show `10.30.0.0/24`,
`10.31.0.0/24`, and/or `10.32.0.0/24` (set-C) prefixes **inside the raw learned-route/BGP data
they captured**, because those prefixes were genuinely present on the shared hub ARS/BGP sessions
at capture time. This is factual, unmodified evidence content (copied verbatim per the
"no change to underlying evidence content" rule) — **not** a topology dependency introduced by
TP-HH. TP-HH's own design, scripts, and filters (see `design.md` and `apply.ps1`'s T3 filter
policy) explicitly exclude `0.0.0.0/0` and set-C from anything TP-HH originates or re-associates.
No action needed beyond this note.

---

# Stage 2 — TP-SQ: US12 square-hybrid feasibility study (evidence plan, not scheduled)

**Status: NOT STARTED, NOT APPROVED.** Everything above is Stage 1 (TP-HH). This part is the evidence
plan for Stage 2, the [US12](../dual-hub-hubless-region-ars/route-map-user-stories.md#us12--square-hybrid-connectivity-regional-dc-to-hub-attachment-with-no-diagonals)
square-hybrid feasibility study. It may not begin until gates **G1–G4** (manifest §Stage 2,
design.md §11) all pass. The square is an **evaluation candidate**; no verdict may be written here
before the evidence exists.

Instruments are US12's V1–V11, carried by reference, mapped onto this lab's L1–L8 layers. Evidence
lives under `show-output/new/tp-sq/<checkpoint>/` and is created only at execution time.

## Evidence checkpoints E0–E6

| Checkpoint | Taken at | What it must contain | Blocking property |
|---|---|---|---|
| **E0** | Before **any** Stage-2 action (design.md A0) | Complete L1–L8 capture across every gateway, both hub Route Servers, `ars-poland` (control), both NVAs, every endpoint NIC; the **Δ2 direct-adjacency AS-PATH form** at `vpngw-onprem`; the two `ars-poland` `0/0` copies; set-C effective routes | **The only reference the whole stage is diffed against.** Missing E0 = stage cannot start |
| **E1a** | After S-C pair created | `vpngw-onprem2`↔`vpngw-hub2` BGP up; learned/advertised sets both ends; no change anywhere else | Additive only — reversible at zero disruption |
| **E1b** | After S-D pair created | eBGP 65000↔65003 established; **deny-by-default filters proven applied, not merely intended** — explicit evidence that `0.0.0.0/0`, `10.31.0.0/24` and `10.32.0.0/24` are denied in both directions | A filter asserted but not shown in the running config is a FAIL |
| **E1c** | After S-B peering created | Peering `Connected`/`FullyInSync` both sides; route-refresh capability recorded **before** the change; NVA session uptime; continuous ping spanning the operation | Maintenance window; hard reset must be recorded if it occurs |
| **E1d** | Before the disruptive step | Every pre-existing connection still `Connected`; `ars-poland` unchanged; set-C effective routes unchanged; Δ2 still in direct-adjacency form | **Natural stop point.** If anything surprises us here, Stage 2 ends additively and rolls back |
| **E2** | After deleting the diagonal (`conn-hub2-to-onprem` / `conn-onprem-to-hub2`) | Full L1–L8 re-capture; the corrected post-activation expectation `65003-65515-65002-65002-65002` at `vpngw-onprem` **measured, not assumed** | The Δ2 direct-adjacency form is now gone by design; E0 is its only record |
| **E3** | Steady-state square | Outcome A per site; B1 DC1↔DC2; **B2 hub address space only**, probed `vm-nva1` `10.10.1.4` ↔ `vm-nva2` `10.20.1.4`, next-hop type `GlobalVNetPeering` both directions; B3 recorded **not delivered** under variant N | A B2 claim evidenced from `vm-hub1-ep`/`vm-hub2-ep` (spoke-resident) is an automatic FAIL |
| **E4** | Fault injection — S-A lost | Per-direction polls at 30 / 60 / 120 / 180 s; two-ended simultaneous capture + interface counters; outcome C recorded **as predicted by the bounded-failover contract written before the fault** | Under variant N, "outcome C not delivered" is a **PASS** if predicted. An **unpredicted** surviving flow is also a failure of the contract |
| **E5** | Failback and restoration | Re-run of every instrument; tables **attribute-identical** to E0 per direction; nothing left pinned by a UDR | A path that pings but returns with a different AS-PATH is a FAIL |
| **E6** | Scoring | The 8-dimension complexity scorecard (design.md §12) filled **only** from counted artefacts in E0–E5, plus the F1–F7 feasibility results and the chosen verdict with its justification | A scorecard cell filled from impression rather than evidence invalidates the verdict |

## Scenario-to-checkpoint map

| # | Stage-2 scenario | Checkpoints | Status |
|---|---|---|---|
| Q1 | Additive build — site 2, S-C, S-D, S-B (variant N) | E0, E1a–E1d | **Not run — gated** |
| Q2 | Diagonal removal — the disruptive step | E2 | **Not run — gated, separately confirmed at execution time** |
| Q3 | Steady-state square: outcomes A, B1, B2, B3 reported **separately** | E3 | **Not run — gated** |
| Q4 | Bounded failover: S-A loss against the written contract | E4 | **Not run — gated** |
| Q5 | Failback and restoration equality | E5 | **Not run — gated** |
| Q6 | Operational-complexity scorecard and verdict | E6 | **Not run — gated** |
| Q4-D | Variant D increment — dynamic S-B, only if outcome C is required | E4, E5 | **Not run — conditional on top of the gates; non-execution is a valid deliverable** |

## Feasibility verdict worksheet — to be filled only from evidence

| Criterion | Result | Evidence |
|---|---|---|
| F1 technical reachability (A / B1 / B2 / B3 reported separately) | *not determined* | — |
| F2 failover vs the written bounded-failover contract | *not determined* | — |
| F3 failback — direct path wins back with no operator action | *not determined* | — |
| F4 symmetry — two-ended capture + counters, never traceroute | *not determined* | — |
| F5 convergence — per direction, 30/60/120/180 s | *not determined* | — |
| F6 route restoration — attribute-identical to E0 | *not determined* | — |
| F7 no collateral damage — set-C, `0/0` copies, Δ2 restored at rollback | *not determined* | — |
| **Operational-complexity verdict** (`Recommended` / `Conditionally viable` / `Technically feasible but operationally unattractive` / `Platform-blocked`) | *not determined* | — |

**Separation rule.** F1–F7 decide **feasibility**; the scorecard decides **desirability**. A design
whose packets all arrive and whose burden is nevertheless excessive is recorded as *Technically
feasible but operationally unattractive* — with an explicit statement that no feasibility criterion
failed, so no reader mistakes it for a technical rejection. A design that fails a criterion is failed
on that criterion, never softened into a complexity judgement.

---

## Backlinks

[README.md](./README.md) · [manifest.md](./manifest.md) · [design.md](./design.md) ·
[lessons-learned.md](./lessons-learned.md) · source lab
[`validation.md`](../dual-hub-hubless-region-ars/validation.md) (FINAL CERTIFICATION table, referenced not duplicated).
