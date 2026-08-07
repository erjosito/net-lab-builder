# deploy-log.md — TP-HH: Dual-Hub Interconnect and Route Server Route-Map Policy

## Pre-existing bed — owned by the source lab

This lab deploys nothing of its own. Every resource exercised by TP-HH's scenarios was deployed by
`labs/dual-hub-hubless-region-ars` on **2026-08-03** and certified on **2026-08-04**
("FINAL CERTIFICATION — READY FOR JOSE TO EXPLORE", Niobe). The hub1/hub2 ARS route-map tier
(inert, unassociated) was activated on **2026-08-05T10:36:38+02:00** — see the source lab's
[`deploy-log.md` §"Hub ARS Route-Map Upgrade"](../dual-hub-hubless-region-ars/deploy-log.md).

| Item | Value |
|---|---|
| Owning lab | [`dual-hub-hubless-region-ars`](../dual-hub-hubless-region-ars/deploy-log.md) |
| Resource group | `rg-dual-hub-hubless-region-ars-lab3d001` |
| Deployed | 2026-08-03 |
| Certified | 2026-08-04 |
| Route-map tier activated (inert) | 2026-08-05T10:36:38+02:00 |
| This lab's own deployment | **None.** No `main.bicep`, no ARM template, no deployment code of any kind lives under this directory. |

**Cleanup authority remains with the source lab.** See `manifest.md` §Ownership contract. No command
in this lab's `scripts/` may target `rg-dual-hub-hubless-region-ars-lab3d001` for deletion or recreation.

---

## Change log — TP-HH's own deltas

**No fabricated entries.** This table is populated only as each scenario is actually executed, with
a real timestamp, a real executor, and a real evidence path. It is empty at creation time
(2026-08-05).

| Timestamp | Change | Executor | Rollback | Evidence path |
|---|---|---|---|---|
| 2026-08-06T09:12:43+02:00 | U0: `az vm start` on `vm-nva1` + `vm-nva2` (async issue ~09:09, both `VM running` confirmed 09:12:43) | Tank (approved by Jose Moreno) | Not exercised — U0 PASS-with-note, no rollback trigger met | `show-output/new/u0-u1/pre/`, `show-output/new/u0-u1/post-u0/` |
| 2026-08-06T10:01:47+02:00 | U1: `az network vnet peering create` × 2 — `vnet-hub1/peer-hub1-to-hub2`, `vnet-hub2/peer-hub2-to-hub1` (vna=T, fwd=T, gwt=F, urg=F); both `Connected`/`FullyInSync` within ~15–60s, re-confirmed stable at T+~20min | Tank (approved by Jose Moreno) | Not exercised — T1/U1 PASS, no rollback trigger met | `show-output/new/u0-u1/pre-u1/`, `show-output/new/u0-u1/post-u1/` |
| 2026-08-06T14:12:35Z (nva1) / 2026-08-06T14:46:26Z (nva2) | U1.5: graceful `birdc configure` on `vm-nva1` then `vm-nva2` — removed `route 10.30.0.0/27`, `protocol bgp ars_poland_0`/`_1`, `filter export_to_poland_ars` (both NVAs) and the dead `10.31.0.0/24`/`10.32.0.0/24` prepend clause inside `export_to_hub2_ars` (nva2 only); `systemctl restart bird` never invoked | Tank (approved by Jose Moreno) | Not exercised — U1.5 PASS on both NVAs, no rollback trigger met | `show-output/new/u15-u2/pre/`, `show-output/new/u15-u2/u15-nva1/`, `show-output/new/u15-u2/u15-nva2/`, `show-output/new/u15-u2/b1/` |
| 2026-08-06T15:52:35Z (association PUT issued) → `Succeeded` ~16:01:43Z | U2: created `ars-hub1/routeMaps/rm-hub1-tmp-assoc` (rule matches `203.0.113.0/24`, absent prefix) + `PUT` `ars-hub1/bgpConnections/peer-nva1` with `routingConfiguration.inboundRouteMap.id` set — body derived from a fresh GET (etag `If-Match`), `vnetRoutes`/`staticRoutesConfig` preserved byte-for-byte; `rm-hub1-activate` and all of `ars-hub2` untouched | Tank (approved by Jose Moreno) | Not exercised — U2 PASS; association **left active** (not rolled back), consistent with plan for proceeding to U3a | `show-output/new/u15-u2/u2/`, `show-output/new/u15-u2/b2/` |

### Phase-4 approval-unit ledger (Stage 1)

Populated only when a unit is actually approved and executed. **U0, U1, U1.5 and U2 executed and
PASSED on 2026-08-06** (U1.5/U2 independently verified live by Niobe, read-only, on 2026-08-06 —
`.squad/decisions/inbox/niobe-u15-u2-verification.md`) — remaining rows stay PENDING/NOT REQUESTED
as of 2026-08-06. Plan of record:
`../../.squad/decisions/inbox/trinity-bowtie-activation-plan.md`; Phase-4 refinement after finding
`TANK-001` (insertion of U1.5, U2 body-preservation rules, U3 prefix change):
`../../.squad/decisions/inbox/trinity-u15-u2-refinement.md`.

| Unit | Scenario | Exact objects touched | Cost delta | Status |
|---|---|---|---|---|
| **U0** | prerequisite | `vm-nva1`, `vm-nva2` — power state only (`az vm start`) | +$0.58/day while running | **EXECUTED 2026-08-06 — PASS-with-note** (see `validation.md` §U0; stale `10.30.0.0/27` static-route finding documented, contained, not a blocker) |
| **U1** | T1 | `vnet-hub1/virtualNetworkPeerings/peer-hub1-to-hub2`, `vnet-hub2/virtualNetworkPeerings/peer-hub2-to-hub1` (vna=T, fwd=T, gwt=F, urg=F) | $0/hr; ≈$0.00 data | **EXECUTED 2026-08-06 — PASS** (see `validation.md` §T1) |
| **U1.5** | prerequisite (`TANK-001`) | **No Azure object.** `vm-nva1` + `vm-nva2` `/etc/bird/bird.conf`: remove `route 10.30.0.0/27`, `protocol bgp ars_poland_0`, `protocol bgp ars_poland_1`, `filter export_to_poland_ars`, and (nva2 only) the `10.31.0.0/24`/`10.32.0.0/24` prepend clause in `export_to_hub2_ars`; apply with `birdc configure` | $0 | **EXECUTED 2026-08-06 — PASS on both NVAs.** Exactly `10.30.0.0/27` withdrawn from both instances of both Route Servers; no BGP session flap (`Since` unchanged pre/post on all four `ars_hub*` sessions); gateway/on-prem sets byte-identical; `nva-config/bird-nva{1,2}.u15-target.conf` are now the authoritative configs. See `validation.md` §U1.5, `show-output/new/u15-u2/{pre,u15-nva1,u15-nva2,b1}/` |
| **U2** | T2a | `ars-hub1/routeMaps/rm-hub1-tmp-assoc` (create, match `203.0.113.0/24`) + `PUT ars-hub1/bgpConnections/peer-nva1` with `routingConfiguration.inboundRouteMap` — body derived from a fresh GET, `vnetRoutes`/`staticRoutesConfig` preserved | $0 | **EXECUTED 2026-08-06 — PASS.** `rm-hub1-tmp-assoc` (match `203.0.113.0/24`) associated inbound on `ars-hub1`/`peer-nva1`; no route effect (B1→B2 zero differences across all 9 comparable capture files); `vnetRoutes`/`staticRoutesConfig` preserved; hub2 unchanged; all 4 VPN connections `Connected`. Association **left ACTIVE**, not rolled back. Api version `2024-10-01` used throughout (`2024-05-01` omits `routingConfiguration`). See `validation.md` §T2a/U2, `show-output/new/u15-u2/{u2,b2}/` |
| **U3a** | T2b step 1 | **No Azure object.** `vm-nva1` `/etc/bird/bird.conf`: add `protocol static u3_doc_test { ipv4; route 198.51.100.0/24 blackhole; }`; apply with `birdc configure` | $0 | **PENDING APPROVAL** — only after U2 passes |
| **U3b** | T2b step 2 | `rm-hub1-tmp-assoc` rule → match `198.51.100.0/24`, `Add asPath [64496,64496]` | $0 | **PENDING APPROVAL** — only after U3a passes. *(Previous target `10.10.0.64/27` withdrawn: proven never learned by ARS)* |
| **U4** | T5 | Step 1: read-only probe. Step 2: one `Microsoft.Network/connections` object — **may be unavailable** | $0 | **PENDING APPROVAL** — Step 1 bundleable at zero risk |
| **U5** | T3 | Would additionally require TCP/179 NSG rules on `nsg-nva-hub1`+`nsg-nva-hub2` and BIRD mutation on both NVAs | TBD | **NOT REQUESTED, NOT PREAPPROVED** |

---

## Stage gate ledger

Populated with real values only as each gate is genuinely closed. **No gate may be marked closed
from intent.** Stage 2 (TP-SQ) cannot begin until all four rows read `CLOSED`.

| Gate | Condition | Status | Closed by / evidence |
|---|---|---|---|
| **G1** | Stage 1 (T1–T5, with T3/T5 either run or explicitly waived with a recorded reason) complete **and** rolled back to the certified baseline, diffed byte-comparable | **OPEN — partially advanced.** T1/U1, U1.5 and T2a/U2 executed and PASSED 2026-08-06 (evidence: `show-output/new/u0-u1/`, `show-output/new/u15-u2/`), but **not rolled back** — both new peerings, both NVAs' cleaned BIRD config, and the U2 route-map association all remain live as the approved end-state of these units. U3–U5 (T2b, T3, T5) **not run**; U4 gateway attachment remains unverified. G1 cannot close until the remaining scenarios run and Stage 1 is rolled back to a byte-comparable baseline; this row must **not** be read as "Stage 1 complete" | `show-output/new/u0-u1/`, `show-output/new/u15-u2/` |
| **G2** | Poland / set-C cleanup status **known and recorded**. *Status only — explicitly **not** a dependency.* Stage 2 may proceed with Poland still deployed, pending cleanup, or already cleaned; it may **not** proceed with the status unknown | **CLOSED — 2026-08-05.** Poland Central was **executed/retired**: `ars-poland`, `vnet-poland-ars`, `vnet-spoke-c1`, `vnet-spoke-c2`, `vm-c1-ep` + dependents, and the 6 Poland-facing peerings on `vnet-hub1`/`vnet-hub2` are deleted (29/29 approved objects). Teardown was governed by, and evidenced in, `../dual-hub-hubless-region-ars/cleanup-poland-dry-run.md` §10 and `deploy-log.md`. This gate closes on status-known, not on the deletion outcome — recorded here per that rule | `../dual-hub-hubless-region-ars/cleanup-poland-dry-run.md#10-executed-result--2026-08-05`, `../dual-hub-hubless-region-ars/show-output/cleanup-poland-execution/` |
| **G3** | **Fresh** cost / resource / **deletion** approval from Jose — covering the ~$95+/day floor vs the current ~$66-73/day run-rate (post-Poland-retirement, down from ~$84/day), the site-2 resource ledger, and the deletion of `conn-hub2-to-onprem` / `conn-onprem-to-hub2`. No Stage-1 approval or prior waiver carries forward | **OPEN** — not requested | — |
| **G4** | Exact route-map attachment behaviour known from Stage 1: T2a `Succeeded` (with the working request body and the observed reset/no-reset behaviour) **or** the verbatim error code; plus T5's verdict or an explicit "T5 not run — attachment remains unverified" | **CLOSED — 2026-08-06.** T2a/U2 produced `Succeeded`: `rm-hub1-tmp-assoc` associated inbound on `ars-hub1`/`peer-nva1` via a byte-preserving `PUT` (etag `If-Match`), with no reset (`ars_hub1_0`/`_1` `Since` unchanged) and no route effect. **T5/U4 gateway attachment remains separately unverified** — Step 2 has not been requested or run; this does not block G4, which closes on T2a's outcome alone per the closing note below | `show-output/new/u15-u2/u2/02-bgpconn-assoc-put-response.json`, `show-output/new/u15-u2/u2/03-post-peer-nva1-GET.json` |

**G4 closing note (added 2026-08-05, applied 2026-08-06).** G4 closes on **U2's outcome** — either
the accepted `PUT` body and response, **or** the verbatim rejection error — recorded under
`show-output/new/u15-u2/u2/`. **U4 is not required to close G4:** if U4 Step 1 shows no
addressable ARS↔VPN-gateway connection resource, G4 closes with T5 recorded as *"unverifiable in
this bed"*, which is an explicit verdict, not an open item. G4 may **not** be closed from the
`rm-hub*-activate` maps existing — creation is not association. **U4 (T5, gateway-connection
attachment) is a distinct, still-open verification item** — it is not implied or satisfied by G4's
closure and remains "not run — attachment unverified" until U4 Step 2 is separately approved and
executed.

**G1 note (added 2026-08-05).** G1's "certified baseline" is re-anchored to the **fresh post-U0
baseline** (`show-output/new/u0-vm-start/`). The pre-cleanup certified baseline is no longer
reachable: the Poland/set-C prefixes and the Δ2 `65002-65002-65002` control signature are gone
permanently.

---

## Change log — TP-SQ (Stage 2) deltas

The user explicitly instructed autonomous deployment through a manually reviewable square on
2026-08-07. Execution stopped after steady-state certification; no failure injection or cleanup was
performed.

| Timestamp | Step | Change | Executor | Rollback | Evidence path |
|---|---|---|---|---|---|
| 2026-08-07 08:16–08:17 CEST | A1 | Poland Central `Standard_B2ts_v2` catalog/live-capacity and quota checks passed; created and verified two zonal Standard PIPs | Copilot | Delete only with TP-SQ cleanup approval | `show-output/new/square/preflight/` |
| 2026-08-07 08:18–08:38 CEST | A2 | Deployed `vnet-onprem2`, `nsg-ep-onprem2`, `vpngw-onprem2` (`VpnGw1AZ`, active-active, ASN 65003), and `vm-onprem2-ep` 10.50.1.4 | Copilot | Delete additive site after its connection pairs | `show-output/new/square/deployment/` |
| 2026-08-07 08:40–08:51 CEST | A3/A4 | Created S-C and S-D connection pairs using generated, non-persisted PSKs; all four objects reached `Connected` | Copilot | Delete S-D, then S-C | `show-output/new/square/e1/` |
| 2026-08-07 08:52–08:57 CEST | Baseline cleanup | Removed the temporary inbound route-map association from `ars-hub1/peer-nva1`; preserved `vnetRoutes`; started all six lab VMs | Copilot | Association intentionally remains absent | `show-output/new/square/baseline-cleanup/` |
| 2026-08-07 09:03–09:07 CEST | A7 | Deleted only `conn-hub2-to-onprem` and `conn-onprem-to-hub2`, forming the exact diagonal-free square | Copilot | Recreate with a fresh matching PSK pair if rolling back | `show-output/new/square/e2/` |
| 2026-08-07 09:08–09:15 CEST | A8 subset | Certified six VPN objects `Connected`, hub peering connected, NVA BGP established, DCI and hub-to-hub probes successful; captured bounded variant-N non-reachability from sites to hub VNet prefixes | Copilot | No mutation | `show-output/new/square/final/` |
| 2026-08-07 (fault-test session) | Normal matrix | Probed cross-spoke and hybrid paths; found route feedback/TTL loops and zero hub-gateway advertisements toward simulated sites. Changed NVA export to deny-by-default and bounded local-spoke `/23` summaries using graceful BIRD reconfiguration | Copilot | Restore prior BIRD backup if required; no daemon restart used | `show-output/new/square-faults/{normal,policy-fix,normal-fixed}/` |
| 2026-08-07 (fault-test session) | F-S-A | Injected S-A PSK mismatch and reset both directional objects; DC1↔DC2 survived, DC1→Spoke B remained unavailable; restored both objects with a fresh matching key | Copilot | Completed — both S-A objects `Connected` | `show-output/new/square-faults/fault-sa/` |
| 2026-08-07 (fault-test session) | F-S-D | Injected DCI PSK mismatch and reset both directional objects; DC1 lost DC2 and Spoke B; restored both objects with a fresh matching key | Copilot | Completed — both S-D objects `Connected` | `show-output/new/square-faults/fault-sd/` |
| 2026-08-07 (fault-test session) | Restored certification | All six VPN objects `Connected`/`Succeeded`; DC1↔DC2 0% loss; unsupported DC1→Spoke B unchanged | Copilot | Current live state | `show-output/new/square-faults/restored/` |

---

## Backlinks

[README.md](./README.md) · [manifest.md](./manifest.md) · [validation.md](./validation.md) ·
source lab [`deploy-log.md`](../dual-hub-hubless-region-ars/deploy-log.md) (full deployment history,
referenced not duplicated).
