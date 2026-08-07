# deploy-log.md — dual-hub-hubless-region-ars
## DEPLOYED — Core Lab Complete

**Updated:** 2026-08-03 17:55 UTC+02:00
**Author:** Tank (IaC Engineer)
**Phase:** DEPLOYED — BGP converged — Niobe handoff ready
**CorrelationId:** lab3d001
**RG:** rg-dual-hub-hubless-region-ars-lab3d001
**Subscription:** [REDACTED]
**ARM Deployment:** deploy-dual-hub-hubless-region-ars-lab3d001

---

## 1. Resource Summary

| Item | Value |
|------|-------|
| RG | rg-dual-hub-hubless-region-ars-lab3d001 |
| Total resources | 59 |
| VPN Gateways (VpnGw1AZ AA BGP) | 3 |
| Azure Route Servers (Standard) | 3 |
| VMs (Standard_B2ts_v2) | 6 |
| VPN Connections (V2V BGP) | 4 |
| Standard PIPs (zones 1,2,3 on GW PIPs) | 9 |
| VNets | 8 |

---

## 2. VPN Gateway Connection Status

| Connection | State | BGP |
|------------|-------|-----|
| conn-hub1-to-onprem | Connected | Enabled |
| conn-onprem-to-hub1 | Connected | Enabled |
| conn-hub2-to-onprem | Connected | Enabled |
| conn-onprem-to-hub2 | Connected | Enabled |

---

## 3. ARS BGP Peering Status

| ARS | Peer | IP | ASN | Status |
|-----|------|----|-----|--------|
| ars-hub1 | peer-nva1 | 10.10.1.4 | 65001 | Succeeded |
| ars-hub2 | peer-nva2 | 10.20.1.4 | 65002 | Succeeded |
| ars-poland | peer-nva1 | 10.10.1.4 | 65001 | Succeeded |
| ars-poland | peer-nva2 | 10.20.1.4 | 65002 | Succeeded |

ARS instance IPs: ars-hub1=10.10.0.68/69 · ars-hub2=10.20.0.68/69 · ars-poland=10.30.0.4/5

---

## 4. BIRD NVA Status (All 8 Sessions Established)

| VM | Sessions | Routes | IP-fwd |
|----|----------|--------|--------|
| vm-nva1 (ASN 65001) | 4/4 Established | 16 routes / 10 networks | enabled |
| vm-nva2 (ASN 65002) | 4/4 Established | 16 routes / 10 networks | enabled |

Sessions: ars-hub1/hub2 x2 + ars-poland x2 = 4 per NVA = 8 total BGP sessions.

---

## 5. Route Propagation Verification (S1 Pre-Check)

### ars-hub1 learned from NVA1 (selected)
| Prefix | AS Path |
|--------|---------|
| 10.31.0.0/24 | 65001 |
| 10.32.0.0/24 | 65001 |
| 10.40.0.0/16 | 65001-65000 |

### ars-hub2 learned from NVA2 — Delta2 confirmed
| Prefix | AS Path | Note |
|--------|---------|------|
| 10.31.0.0/24 | 65002-65002-65002 | Delta2 AS-path prepend x2 |
| 10.32.0.0/24 | 65002-65002-65002 | Delta2 AS-path prepend x2 |

### vpngw-onprem set-C routes
| Prefix | Via hub1 | Via hub2 |
|--------|----------|----------|
| 10.31.0.0/24 | 65515-65001 | 65515-65002-65002-65002 |
| 10.32.0.0/24 | 65515-65001 | 65515-65002-65002-65002 |

S1(b) PASS: on-prem sees hub1-preferred shorter path for set-C prefixes.

### vm-c1-ep effective routes
| Prefix | Next-hop | Source |
|--------|----------|--------|
| 0.0.0.0/0 | 10.10.1.4, 10.20.1.4 (ECMP) | VirtualNetworkGateway (ARS) |
| 10.31.0.0/24 | — | Default (connected) |

NOTE: ECMP (both NVAs) is baseline without Delta3. NVA1-preferred requires S4 Delta3 activation.

---

## 6. Operational BIRD Config Deviations

Cloud-init nva{1,2}-cloud-init.yaml had BIRD protocol kernel with 'import all; learn;'
causing Azure VNet peering system routes to be re-exported as kernel unreachable routes.
Applied operational fixes via run-command on deployed VMs (IaC files unchanged in repo):

| Fix | Detail |
|-----|--------|
| kernel protocol | import where net = 0.0.0.0/0; export where source ~ [RTS_BGP, RTS_DEVICE]; |
| hub ARS sessions | Added multihop 2 to all hub ARS BGP sessions |
| static protocol | Added protocol static with ARS-subnet /27 routes + 0.0.0.0/0 via VNet GW |

Reproducibility: if VMs are redeployed, these fixes must be re-applied. Cloud-init YAML has
a latent BIRD kernel protocol issue — recommend IaC revision in next sprint.

---

## 7. Platform Blockers Encountered and Resolved

| Blocker | Error | Fix | Reviewer |
|---------|-------|-----|---------|
| B1: VpnGw1 retired | NonAzSkusNotAllowedForVPNGateway | VpnGw1 to VpnGw1AZ in vpngw.bicep | Trinity |
| B2: GW PIPs need zones | VmssVpnGatewayPublicIpsMustHaveZonesConfigured | zones 1,2,3 on 6 GW PIPs; deleted zone-less PIPs | Trinity |

ARM validate did NOT catch B1 or B2 — both only fail at resource-create time.

---

## 8. Show-output Artifacts

Under labs/dual-hub-hubless-region-ars/show-output/deploy/:
- resource-list-final.json (59 resources)
- vpn-connections-status.json
- ars-bgp-peerings.json / ars-instance-ips.json
- ars-hub1/hub2-peer-nva{1,2}-learned-routes.json
- ars-poland-peer-nva{1,2}-learned-routes.json
- vpngw-onprem-learned-routes.json (82 routes)
- vm-c1-ep-effective-routes.json
- vm-nva1/nva2-final-state.txt
- vm-nva1/nva2-bird-*.txt (patch history)

---

## 9. Niobe Handoff

RG: rg-dual-hub-hubless-region-ars-lab3d001
All S1 pre-conditions met: VPN connected, ARS peerings up, BIRD sessions established,
routes propagating end-to-end with correct AS paths.

Key commands:

  S1(a): az network routeserver peering list-learned-routes -g rg-dual-hub-hubless-region-ars-lab3d001 --routeserver ars-hub1 --name peer-nva1
  S1(b): az network vnet-gateway list-learned-routes -g rg-dual-hub-hubless-region-ars-lab3d001 -n vpngw-onprem
  S1(c): az network nic show-effective-route-table -g rg-dual-hub-hubless-region-ars-lab3d001 -n nic-vm-c1-ep
  S1(d): az vm run-command invoke -g rg-dual-hub-hubless-region-ars-lab3d001 -n vm-c1-ep --command-id RunShellScript --scripts 'ping -c 4 10.40.1.4'

WARNING: Delta3 (Inbound ARS route map, PUBLIC PREVIEW) NOT activated.
S4 is a SEPARATE GATED STEP. Niobe captures baseline FIRST before requesting S4 activation.

---

*10 KB or less — no secrets, no subscription IDs*


---

## Δ3 Activation Attempt — 2026-08-03 19:36 UTC+02:00

### BLOCKED — Platform architectural constraint

| Item | Value |
|------|-------|
| Route map created | rm-poland-nva2-default-prepend |
| Rule | Equals 0.0.0.0/0 -> AS-Path Add [64496,64496] -> Terminate |
| ARS upgrade triggered | Yes (first route map on ars-poland) |
| Upgrade duration | ~23 min |
| Association attempt | FAILED |
| Rollback | Completed — baseline ECMP restored |

### Blocker Error

Code: HubBgpConnectionFromSpokeVnetCannotReferenceRouteMap

Message: BGP connections where peerIp is NOT within the Route Server's own VNet cannot
reference a RouteMap. Route maps are only supported for local-VNet BGP connections
(peerIp within vnet-poland-ars: 10.30.0.0/24).

NVA1 peer IP: 10.10.1.4 (vnet-hub1, 10.10.0.0/16) — NOT in 10.30.0.0/24.
NVA2 peer IP: 10.20.1.4 (vnet-hub2, 10.20.0.0/16) — NOT in 10.30.0.0/24.

Both NVAs are multi-hop cross-VNet BGP peers. Route maps require same-VNet peer IPs.
This restriction was NOT documented in the activation contract (Trinity research gap).

### Rollback State

| Check | Value |
|-------|-------|
| Route maps on ars-poland | 0 (deleted) |
| peer-nva2 0/0 asPath | 65002 (1 hop — baseline restored) |
| vm-c1-ep 0/0 nextHop | 10.10.1.4, 10.20.1.4 (ECMP — baseline) |
| ARS tier | Upgraded (cannot revert — surcharge ~/day continues) |

### API Version Deviation (documented)

Contract pinned 2024-05-01; platform requires minimum 2024-10-01 for route maps.
No semantic change — same body, same policy. Used 2024-10-01.

### Rollback Command (for reference)

Route map was deleted. If recreated, detach before delete:
  az rest --method DELETE --url ".../routeMaps/rm-poland-nva2-default-prepend?api-version=2024-10-01"

### Architecture Fix Options (require reviewer re-gating)

1. Deploy relay NVA within vnet-poland-ars (10.30.0.0/24) — NIC IP in range; BGP session via local peer
2. Add snet-nva in vnet-poland-ars; attach NVA2 secondary NIC with IP in 10.30.0.0/24
3. Alternative policy: NVA2 BIRD export filter to not advertise 0/0 to ars-poland (no route map needed)

Option 3 (BIRD export filter change) would achieve the same result without route maps but
would require IaC change to nva2-cloud-init.yaml. Operational apply via run-command is possible.

### Show-output Artifacts

Under labs/dual-hub-hubless-region-ars/show-output/delta3/:
- 00-pre-* files (baseline before any map)
- 01-create-routemap-response.json
- 03b-apply-via-bgpconn-response.json (blocker error)
- 99-rollback-* files


---

## Delta3 BIRD Implementation — 2026-08-04 08:30 UTC+02:00

### ACTIVATED — NVA2 BIRD export_to_poland_ars prepend (functional replacement)

| Item | Value |
|------|-------|
| Method | NVA2 BIRD export filter: prepend 65002 x2 for 0/0 toward ars-poland |
| Implementation | Operational: birdc configure (graceful reload, no restart) |
| Cloud-init updated | Yes — nva2-cloud-init.yaml export_to_poland_ars filter updated |
| Sessions disrupted | None — all 4 NVA2 sessions remained Established |

### S4 Results

| Assertion | Expected | Actual | Pass |
|-----------|----------|--------|------|
| peer-nva2 0/0 asPath | 65002 65002 65002 | 65002-65002-65002 | PASS |
| peer-nva1 0/0 asPath | 65001 | 65001 | PASS |
| c1-ep 0/0 nextHop | 10.10.1.4 (NVA1 only) | 10.10.1.4 | PASS |
| DEF-001 hub1-ep to c1-ep | 0% loss | 0% loss 5/5 ~22ms | PASS |
| Delta2 preserved 10.31/24 hub1 | 65515-65001 | 65515-65001 | PASS |
| Delta2 preserved 10.31/24 hub2 | 65515-65002-65002-65002 | 65515-65002-65002-65002 | PASS |
| NVA1 sessions | 4 Established | 4 Established | PASS |
| c1-ep to onprem ping | 0% loss | 0% loss 4/4 | PASS |

### Policy Change

Filter on NVA2 bird.conf (was: accept only):
`
filter export_to_poland_ars {
  if net = 0.0.0.0/0 then {
    bgp_path.prepend(65002);
    bgp_path.prepend(65002);
  }
  accept;
}
`

### Deviation Notes

- ARS route-map approach was blocked by platform (HubBgpConnectionFromSpokeVnetCannotReferenceRouteMap)
- BIRD-side prepend achieves identical functional outcome
- All other prefixes from NVA2 toward ars-poland: UNCHANGED
- Export toward ars-hub2 (Delta1+Delta2): UNCHANGED

### Show-output Artifacts

Under labs/dual-hub-hubless-region-ars/show-output/delta3-bird/:
- 00-pre-ars-poland-peer-nva2-learned.json (baseline: asPath=65002)
- 00-pre-ars-poland-peer-nva1-learned.json (baseline: asPath=65001)
- 00-pre-c1-ep-effective-routes.json (baseline: ECMP)
- 00-rollback-nva2-bird-conf.txt (pre-delta3 config for rollback)
- 01-apply-output.txt (patch+syntax+reconfigure output)
- 01-post-ars-poland-peer-nva2-learned.json (post: asPath=65002-65002-65002)
- 01-post-ars-poland-peer-nva1-learned.json (post: asPath=65001 unchanged)
- 01-post-c1-ep-effective-routes.json (post: 10.10.1.4 NVA1 only)
- 02-def001-ping-hub1ep-to-c1ep.txt (DEF-001 RESOLVED)
- 02-post-vpngw-onprem-learned-routes.json (Delta2 preserved)
- 02-post-ars-hub2-peer-nva2-learned.json (Delta1/Delta2 preserved)

---

*No secrets, no subscription IDs*


---

## S2/S3 Fault Injection and Recovery — 2026-08-04 09:17 UTC+02:00

### Pre-fault State
- c1-ep 0/0: 10.10.1.4 (NVA1 only, Delta3 active)
- vpngw-onprem hub1-preferred: 65515-65001 vs 65515-65002-65002-65002
- All 4 VPN connections: Connected / BGP enabled
- All 4 ARS peerings: Succeeded

### S2 — Hub1 Outage (PSK mismatch + NVA1 BIRD stop)

| Metric | Value |
|--------|-------|
| T0 (fault start) | 09:17:04 |
| NVA1 BIRD stopped | 09:19:30 |
| T1 (c1-ep converged to NVA2) | 09:20:09 |
| Convergence: BIRD-stop to T1 | 39s |
| Convergence: T0 to T1 | 185s (incl API overhead) |
| S2 VERDICT | ALL PASS |

S2 assertions:
- c1-ep 0/0 = 10.20.1.4 (NVA2 only): PASS
- ars-poland/nva1 routes = 0 (NVA1 down): PASS
- onprem 10.31/24 hub2-only (65515-65002-65002-65002): PASS
- c1-ep to onprem ping 0% loss via hub2: PASS
- Convergence from BIRD-stop <= 180s: PASS (39s)

### S3 — Hub1 Recovery

| Metric | Value |
|--------|-------|
| T0_S3 (recovery start) | 09:25:29 |
| NVA1 BIRD started | 09:28:21 |
| T1_S3 (c1-ep = NVA1) | 09:28:45 |
| Convergence: BIRD-start to T1 | 24s |
| S3 VERDICT | ALL PASS |

S3 assertions:
- c1-ep 0/0 = 10.10.1.4 (NVA1, Delta3 preserved): PASS
- ars-poland/nva1 0/0 asPath = 65001: PASS
- ars-poland/nva2 0/0 asPath = 65002-65002-65002 (Delta3 active): PASS
- onprem hub1=65515-65001 preferred: PASS
- hub1-ep to c1-ep 0% loss (DEF-001 still resolved): PASS
- Convergence from BIRD-start <= 90s: PASS (24s)
- All 4 VPN connections Connected: PASS
- NVA1 4/4 BIRD sessions Established: PASS

### Deviation
KV platform-secrets-1138 inaccessible from local machine (public network disabled).
S3 used fresh matching PSK on both hub1 connection sides. Tunnel re-established.
PSK values: never logged/printed.

### Artifacts
show-output/s2-failover/ and show-output/s3-failback/

---

*No secrets, no subscription IDs*


---

## Hub ARS Route-Map Upgrade — 2026-08-05T10:36:38+02:00

### SUCCEEDED — ars-hub1 and ars-hub2 route-map tier activated

**Author:** Tank (IaC Engineer)
**Purpose:** First-use route-map activation on hub Route Servers to unlock route-map capability for future scenario testing. Maps are inert (no connection associations).
**API version:** 2024-10-01
**Method:** ARM REST PUT via `az rest`

| Item | Value |
|------|-------|
| RG | rg-dual-hub-hubless-region-ars-lab3d001 |
| ars-hub1 map name | `rm-hub1-activate` |
| ars-hub2 map name | `rm-hub2-activate` |
| Rule (both) | match 192.0.2.0/24 Equals → Add AS-Path [64496] → Terminate |
| Associations (both) | `associatedInboundConnections: []` `associatedOutboundConnections: []` |
| PUT triggered (hub1) | 10:35:37 |
| PUT triggered (hub2) | 10:36:00 |
| hub1 Succeeded at | +22.4 min (10:59:11) |
| hub2 Succeeded at | +25.7 min (11:02:24) |
| ars-poland | Untouched — Succeeded |

### Preflight State (all confirmed before starting)

| Check | Result |
|-------|--------|
| ars-hub1 provisioningState | Succeeded |
| ars-hub2 provisioningState | Succeeded |
| ars-hub1 existing route maps | None |
| ars-hub2 existing route maps | None |
| ars-hub1 peer-nva1 provisioningState | Succeeded |
| ars-hub2 peer-nva2 provisioningState | Succeeded |
| conn-hub1-to-onprem | Connected |
| conn-onprem-to-hub1 | Connected |
| conn-hub2-to-onprem | Connected |
| conn-onprem-to-hub2 | Connected |
| Hub learned routes pre-upgrade | Empty (BIRD idle between scenarios — same as pre-upgrade) |

### Smoke-Check Post-Upgrade

| Check | Result |
|-------|--------|
| conn-hub1-to-onprem | Connected ✅ |
| conn-onprem-to-hub1 | Connected ✅ |
| conn-hub2-to-onprem | Connected ✅ |
| conn-onprem-to-hub2 | Connected ✅ |
| ars-hub1 peer-nva1 provisioningState | Succeeded ✅ |
| ars-hub2 peer-nva2 provisioningState | Succeeded ✅ |
| ars-hub1 rm associations | inbound=0 outbound=0 ✅ |
| ars-hub2 rm associations | inbound=0 outbound=0 ✅ |
| ars-poland | Succeeded, untouched ✅ |
| Hub learned routes post-upgrade | Empty (same as pre — BIRD idle, not upgrade-induced) |

### Route-Map Locality Note (contrast with ars-poland)

Unlike ars-poland (where peerIp 10.10.1.4/10.20.1.4 are cross-VNet), ars-hub1's peer-nva1
IP (10.10.1.4) is within vnet-hub1 (10.10.0.0/16) and ars-hub2's peer-nva2 IP (10.20.1.4)
is within vnet-hub2 (10.20.0.0/16). The HubBgpConnectionFromSpokeVnetCannotReferenceRouteMap
constraint does NOT apply here. Route maps are fully usable on hub1/hub2 NVA peerings.

### Cost Note

Each hub ARS now incurs the route-map surcharge (~$6/day each = ~$12/day total added).
Surcharge is irreversible without ARS recreate. Jose's $72/day waiver covers this.

### Show-output Artifacts

Under labs/dual-hub-hubless-region-ars/show-output/route-map-upgrade/:
- 00-preflight.json
- 01-hub1-create-response.json / 01-hub2-create-response.json
- 02-poll-log.txt (60s interval, 45-min timeout, both Succeeded)
- 03-hub1-final-routemap.json / 03-hub2-final-routemap.json
- 04-post-upgrade-smoke.json
- 05-hub1-learned-routes-post.json / 05-hub2-learned-routes-post.json

## Poland Central Cleanup — EXECUTED — 2026-08-05T~19:15+02:00

### Confirmed and executed: all 29 approved objects deleted

Following the dry-run preview in `cleanup-poland-dry-run.md` (2026-08-05T16:00:43+02:00), a structured
confirmation approving the exact 29-object list was received. Execution ran Stages 1→4b exactly as
proposed in that document's §4, no reordering. Result: **29/29 objects deleted, zero failures, zero
retries.**

| Stage | Deleted | Notes |
|---|---|---|
| 1 | 6 remote-side peerings on `vnet-hub1`/`vnet-hub2` pointing at Poland | All 6 exit 0 |
| 2 | `peer-nva1`, `peer-nva2` (ars-poland BGP peerings), `ars-poland` | Route Server delete took ~25 min (longer than the ~10 min manifest estimate) |
| 3 | `vm-c1-ep` (+2 auto-removed extensions), `nic-vm-c1-ep`, `osdisk-vm-c1-ep`, `pip-ars-poland` | `vm-c1-ep` was already deallocated pre-task (documented, non-blocking) |
| 4 | `vnet-spoke-c1`, `vnet-spoke-c2`, `vnet-poland-ars` (+10 auto-removed nested peerings) | — |
| 4b | `nsg-ep-poland` | Deleted after Stage 4, as planned (subnet-associated, not NIC-associated) |

### Post-delete verification

- Resource count: **50** (was 61) ✅ · Region breakdown: `swedencentral=20`, `switzerlandnorth=19`,
  `norwayeast=11`, `polandcentral=0` ✅
- `vnet-hub1` peerings: `peer-hub1-to-spoke-a` only ✅ · `vnet-hub2` peerings: `peer-hub2-to-spoke-b` only ✅
- Route Servers: `ars-hub1`, `ars-hub2` only, each with unchanged 1 BGP peering + 1 inert route map
  (`rm-hub1-activate`, `rm-hub2-activate`) ✅
- VPN gateways: 3, `Succeeded` ✅ · VPN connections: 4/4 `Connected` ✅
- VMs: 5 remain (`vm-nva1`, `vm-nva2`, `vm-hub1-ep`, `vm-hub2-ep`, `vm-onprem-ep`), all pre-existing
  `deallocated` (lab-wide, not caused by this task) ✅ · NSGs: 5 (was 6) ✅
- **Update (2026-08-06):** `vm-nva1`/`vm-nva2` were subsequently started (`VM running`) by the
  downstream `dual-hub-interconnect-ars-route-policy` lab's approved U0 unit; `vm-hub1-ep`,
  `vm-hub2-ep`, `vm-onprem-ep` remain `deallocated`. This does not change the verification above,
  which is a snapshot as of the 2026-08-05 cleanup; see
  [`../dual-hub-interconnect-ars-route-policy/deploy-log.md`](../dual-hub-interconnect-ars-route-policy/deploy-log.md)
  §Change log for the executor, evidence, and rollback status of that power-state change.
- Resource group: present, `Succeeded`, tags unchanged ✅

### Impact on scenarios

**S4 (Δ3 Route-Map Preview)** and **S5 (Prefix-Only Spoke Scale)** are now permanently
non-repeatable in this bed — both scenarios tested Poland/set-C behaviour specifically. Their
historical results in `validation.md` remain recorded unchanged. S1/S2/S3 (hub1↔hub2 failover/
failback via on-prem) are unaffected — verified unchanged above.

### Show-output Artifacts

Under `labs/dual-hub-hubless-region-ars/show-output/cleanup-poland-execution/`:
- `pre/01-resource-count-baseline.md`, `pre/02-vnet-peering-counts.md`, `pre/03-ars-bgp-peerings-all-three.md`, `pre/04-vm-poweroff-deviation-and-skipped-captures.md`
- `01-stage1-remote-peerings.md`, `02-stage2-ars-poland.md`, `03-stage3-vm-nic-disk-pip.md`, `04-stage4-vnets-and-nsg.md`
- `post/05-post-delete-verification.md`

### Duration

Approximately 65 minutes end-to-end (dominated by the ~25-minute `ars-poland` Route Server delete).

---

*No secrets, no subscription IDs*
