# Validation — SAP RISE Scoped Peering + FWaaS

> **Reconciled against deployed reality — 2026-09-29 (Niobe)**
> Cross-checked against `design.md`, `manifest.md`, and `deploy/deployed-resources.md`. Resource
> group is `rg-saprise-swedencentral`. Subnet names, resource names, and CLI syntax below all
> reflect the actual deployed names (`vm-hub-nva`, `vm-spoke-nva`, `vm-ce-onprem`,
> `vm-workload-probe`, `nic-hub-nva`, `nic-spoke-nva`, `nic-workload-probe`, `nic-ce-onprem`,
> `ergw-sap-rise`, `ars-hub`, `er-sap-rise`), not the placeholder names in the original skeleton.
> **No Bastion was deployed** (documented deviation) — every VM-level command below uses
> `az vm run-command invoke --command-id RunShellScript` instead of direct SSH. **S1 diagnostics
> are executed and scored below (see verdict). S2 is NOT yet toggled/tested — `enable_summarized_gateway_prefixes`
> remains `false`; that is a separate follow-up task per the task brief.**
>
> **S1 ORIGINAL VERDICT (2026-09-29, first pass): FAIL.** The redistribution chain (BIRD static
> route → BGP export → ARS → ER Gateway) is not delivering the spoke supernet in either
> direction, for reasons traced to BIRD configuration/behavior on `vm-hub-nva`, not to the
> subnet-peering or NSG/UDR layers (those are all correctly configured and PASS). See
> `show-output/s1-*` for full evidence and root-cause analysis.
>
> **S1 RE-VALIDATION VERDICT (2026-09-29, independent re-run after 5-round BGP fix chain): FAIL,
> but for different reasons than the original run.** Trinity/Tank's four BGP defects (recursive
> static route, `ce_onprem export none`, kernel `export all` poisoning, CE-side timer mismatch)
> are genuinely fixed — I independently confirmed all three BGP sessions (`ce_onprem`,
> `azure_rs_1`, `azure_rs_2`) simultaneously `Established` on `vm-hub-nva`, and ARS independently
> confirmed learning `10.60.0.0/16` from the hub NVA. **However, the critical data-plane test —
> on-prem CE to both the spoke NVA subnet (10.60.0.0/27) and the spoke workload subnet
> (10.60.1.0/24) — still shows 100% packet loss to BOTH targets**, identical to the original
> FAIL's outcome. I traced this to two previously-undiscovered defects that the BGP-focused fix
> chain never touched: (1) Azure Route Server's `allowBranchToBranchTraffic` is `false`, which
> blocks ARS from propagating the NVA-learned route to the ER Gateway (confirmed: ARS has the
> route, ER Gateway's learned-routes table and BGP peer status both still show zero routes
> received from ARS); (2) `vm-hub-nva`'s live kernel `net.ipv4.ip_forward` is `0` — a
> `/etc/sysctl.d/99-ip-forward.conf` drop-in file specifies `1`, but it was never applied at
> runtime, so the hub NVA cannot forward transit packets at all regardless of any route/BGP
> state. See the "S1 Re-validation" subsection below and Open Items for full detail.

---

## Scenario 1: ARS + Hub NVA eBGP Redistribution

**Design claim:** Azure Route Server (ASN 65515) + Linux NVA in hub snet-hub-nva (ASN 65001) via BIRD redistribute the full spoke VNet supernet (10.60.0.0/16) into BGP toward the ER Gateway. ER Gateway learns the /16 via eBGP. On-prem CE receives the /16 via ExpressRoute circuit (Megaport VXC). Data-plane path from on-prem through hub to spoke workload is complete.

### Route Collection — Three-Layer Mandatory

#### Layer 0: Subnet-Scoped Peering (prerequisite check, executed first)

**Assertion S1.P1 — subnet-scoped peering in place, snet-hub-nva ↔ snet-spoke-nva only**
- **What:** `az network vnet peering list -g rg-saprise-swedencentral --vnet-name vnet-hub -o json` and `--vnet-name vnet-sap-rise`.
- **Expected:** `peer-hub-to-sap-rise` / `peer-sap-rise-to-hub` show `peerCompleteVnets: false` with `localSubnetNames`/`remoteSubnetNames` limited to `snet-hub-nva` and `snet-spoke-nva`. `snet-workload` must not appear in any peering scope.
- **Evidence path:** `show-output/s1-01-hub-vnet-peering-list.json`, `show-output/s1-01b-spoke-vnet-peering-list.json`
- **Pass/Fail:** **PASS.** Exactly as designed. (A separate, intentionally full-VNet peering `peer-hub-to-onprem-sim` also exists — that is deviation #1, the simulated on-prem CE being a plain Azure VM peered to `vnet-hub`, and is expected.)

#### Layer 1: ER Gateway Learned & Advertised Routes

**Assertion S1.L1.1 — ER Gateway learned routes**
- **What:** `az network vnet-gateway list-learned-routes -g rg-saprise-swedencentral -n ergw-sap-rise -o json`.
- **Expected:** Routing table contains `10.60.0.0/16` with origin AS 65001 (hub NVA) or AS 65515 (ARS) in path.
- **Evidence path:** `show-output/s1-03-er-gateway-learned-routes.json`
- **Pass/Fail:** **FAIL.** Learned table contains only `10.40.0.0/16` (hub's own network route) and the `169.254.170.152/30` PE link to the Megaport MCR (AS-path `12076-64512`). `10.60.0.0/16` is absent.

**Assertion S1.L1.2 — ER Gateway advertised routes**
- **What:** `az network vnet-gateway list-advertised-routes -g rg-saprise-swedencentral -n ergw-sap-rise --peer 10.40.0.4 -o json` (peer = Megaport MSEE peer IP).
- **Expected:** ER Gateway advertises at least `10.60.0.0/16` outbound toward the ER circuit/MSEE.
- **Evidence path:** `show-output/s1-04-er-gateway-advertised-routes.json`
- **Pass/Fail:** **FAIL.** Only `10.40.0.0/16` is advertised. Consistent with S1.L1.1 — nothing to advertise because nothing was learned.

**Assertion S1.L1.3 — ER Gateway BGP peer status**
- **What:** `az network vnet-gateway list-bgp-peer-status -g rg-saprise-swedencentral -n ergw-sap-rise -o json`.
- **Expected:** BGP session to ARS peers (10.40.0.36/.37, ASN 65515) is **Connected** with non-zero learned route count.
- **Evidence path:** `show-output/s1-02-er-gateway-bgp-peer-status.json`
- **Pass/Fail:** **PARTIAL.** Both ARS sessions and both Megaport MSEE sessions (ASN 12076, IPs 10.40.0.4/.5) show `state: Connected` — BGP adjacency itself is healthy. But `routesReceived: 0` on both ARS sessions confirms the sessions are up while carrying zero routes.

#### Layer 2: ER Circuit Provider Routes (Megaport MCR)

**Assertion S1.L2.1 — ER circuit provisioning state**
- **What:** `az network express-route show -g rg-saprise-swedencentral -n er-sap-rise`.
- **Expected:** `provisioningState == "Succeeded"`, Megaport hand-off confirmed.
- **Evidence path:** `show-output/s1-05-er-circuit-provisioning-state-DEFERRED.txt`
- **Pass/Fail:** **DEFERRED.** `deployed-resources.md` already records the gateway as `Succeeded` and does not flag the circuit as an open item; since the confirmed failure is upstream in BIRD (before any packet reaches the circuit), re-running this capture now would not change the S1 verdict. Re-run alongside the BIRD fix re-validation.

**Assertion S1.L2.2 — Megaport MCR BGP session (looking glass or REST API)**
- **What:** Megaport looking glass / REST API for the VXC attached to this circuit.
- **Pass/Fail:** **NOT RUN.** No Megaport API credentials/looking-glass access exercised in this pass — not needed to reach the S1 verdict, since the failure is confirmed upstream (BIRD never originates the route in the first place, so the circuit-level view would show the same absence). Flagged as an open item if a from-the-wire confirmation is later wanted.

#### Layer 3: Azure Route Server Learned & Advertised Routes

**Assertion S1.L3.1 — ARS learned routes**
- **What:** `az network routeserver peering list-learned-routes -g rg-saprise-swedencentral --routeserver ars-hub -n ars-hub-nva-peering -o json`.
- **Expected:** ARS learns `10.60.0.0/16` from the hub NVA (ASN 65001) peer.
- **Evidence path:** `show-output/s1-06-ars-learned-routes.json`
- **Pass/Fail:** **FAIL.** ARS learns only `172.40.100.0/24` (the on-prem CE's own prefix, redistributed through the hub NVA's `ce_onprem` session). `10.60.0.0/16` never appears.

**Assertion S1.L3.2 — ARS advertised routes back to hub NVA**
- **What:** `az network routeserver peering list-advertised-routes -g rg-saprise-swedencentral --routeserver ars-hub -n ars-hub-nva-peering -o json`.
- **Evidence path:** `show-output/s1-07-ars-advertised-routes.json`
- **Pass/Fail:** **FAIL/EMPTY.** No routes advertised back (expected, since the ER Gateway side has nothing to redistribute either).

**Assertion S1.L3.3 — ARS BGP peering configuration**
- **What:** `az network routeserver peering list -g rg-saprise-swedencentral --routeserver ars-hub -o json`.
- **Evidence path:** `show-output/s1-08-ars-peering-list.json`
- **Pass/Fail:** **PASS.** Single peering `ars-hub-nva-peering` to `10.40.1.4` (ASN 65001), `provisioningState: Succeeded` — matches design exactly. The ARS *resource configuration* is healthy; the failure is not here.

#### Layer 4: Hub NVA (BIRD) Route Table — root-cause layer

**Assertion S1.L4.1 — BIRD route table on hub NVA**
- **What:** `az vm run-command invoke -g rg-saprise-swedencentral -n vm-hub-nva --command-id RunShellScript --scripts "birdc show route"` (no Bastion/SSH — deviation #2).
- **Expected:** BIRD shows `10.60.0.0/16` as a redistributed static route, exported toward the ARS peers.
- **Evidence path:** `show-output/s1-09-bird-protocols-and-routes-poll1.txt`, `show-output/s1-11-bird-conf-and-root-cause.txt`
- **Pass/Fail:** **FAIL.** `10.60.0.0/16` never appears in BIRD's RIB. Root cause identified: the static route `route 10.60.0.0/16 via 10.60.0.4;` uses a recursive next hop, and BIRD requires a route to `10.60.0.4` inside its **own** table before installing it. Azure's subnet-peering fabric delivers packets to `10.60.0.0/27` transparently at the hypervisor/SDN layer (confirmed reachable by direct `ping`, and present in the NIC's Azure-side effective-route table) but never injects a matching route into the guest OS kernel table, so BIRD's `kernel1 { learn; }` protocol has nothing to resolve the static route against. `birdc show route protocol static_bgp all` returns zero routes.

**Assertion S1.L4.2 — BIRD BGP session status**
- **What:** `birdc show protocols` / `show protocols all` via the same `run-command` invocation.
- **Expected:** BGP sessions to ARS peers (10.40.0.36/.37, ASN 65515) and to the on-prem CE are **up**.
- **Evidence path:** `show-output/s1-09-bird-protocols-and-routes-poll1.txt`, `show-output/s1-10-bird-second-poll-flap-evidence.txt`
- **Pass/Fail:** **FAIL (flapping).** Across two polls ~2 minutes apart, `ce_onprem`, `azure_rs_1`, and `azure_rs_2` were each observed both up (Established) and down (Idle, "Hold timer expired" / "Connection reset by peer") — the sessions alternate rather than staying stable. This matches Tank's note in `deployed-resources.md` ("brief alternating flaps... hold-timer resets") but the evidence here shows it is an ongoing pattern, not a one-time convergence transient. **Open item, not fixed by Niobe** — flagged for Trinity/Tank.

### NIC Effective Routes & NSG Analysis

**Assertion S1.E1 — Spoke workload VM NIC effective routes**
- **What:** `az network nic show-effective-route-table -g rg-saprise-swedencentral -n nic-workload-probe -o json`.
- **Expected:** UDR sending default traffic to the spoke NVA (10.60.0.4).
- **Evidence path:** `show-output/s1-15-nic-effective-routes-all-three.txt`
- **Pass/Fail:** **PASS.** UDR `default-via-spoke-nva` (0.0.0.0/0 → VirtualAppliance 10.60.0.4) is present and Active, exactly as designed.

**Assertion S1.E2 — Hub NVA NIC effective routes**
- **What:** `az network nic show-effective-route-table -g rg-saprise-swedencentral -n nic-hub-nva -o json`.
- **Expected:** System route for the peered spoke subnet (10.60.0.0/27), type VNetPeering.
- **Evidence path:** `show-output/s1-15-nic-effective-routes-all-three.txt`
- **Pass/Fail:** **PASS** (fabric-level) with a flag: the route exists at the Azure-fabric level but is invisible inside the guest OS/BIRD — see S1.L4.1.

**Assertion S1.E3 — Spoke NVA NIC effective routes**
- **What:** `az network nic show-effective-route-table -g rg-saprise-swedencentral -n nic-spoke-nva -o json`.
- **Expected:** System route back to snet-hub-nva (10.40.1.0/27), no route to the workload subnet's on-prem destination.
- **Evidence path:** `show-output/s1-15-nic-effective-routes-all-three.txt`
- **Pass/Fail:** **PASS.** Matches design exactly.

### Data-Plane Connectivity — S1 (ARS + NVA eBGP)

**Assertion S1.D1 — On-prem CE to spoke NVA subnet (10.60.0.0/27) AND workload subnet (10.60.1.0/24) — S1 should show BOTH reachable**
- **What:** `az vm run-command invoke -g rg-saprise-swedencentral -n vm-ce-onprem --command-id RunShellScript --scripts "ping -c 3 -W 2 10.60.0.4; ping -c 3 -W 2 10.60.1.4"`.
- **Expected:** Both pings succeed (this is the defining claim of S1 — the "complete fix").
- **Evidence path:** `show-output/s1-13-onprem-to-spoke-and-workload-ping.txt`
- **Pass/Fail:** **FAIL on BOTH.** 100% packet loss to `10.60.0.4` (spoke NVA subnet) AND `10.60.1.4` (workload subnet). This is worse than the asymmetric result S1 is supposed to demonstrate — neither target is currently reachable, because `vm-ce-onprem` has no BGP-learned route to `10.60.0.0/16` at all (its `hub_nva` BGP session was down at test time, and even when up, the hub NVA's `ce_onprem` protocol is configured `export none`, so the CE was never going to receive the route regardless of session state or the recursive-route issue above).

**Assertion S1.D2 — Reverse connectivity: spoke workload to on-prem CE**
- **What:** `az vm run-command invoke -g rg-saprise-swedencentral -n vm-workload-probe --command-id RunShellScript --scripts "ping -c 3 -W 2 172.40.100.4"`.
- **Evidence path:** `show-output/s1-14-workload-to-onprem-ping-and-routes.txt`
- **Pass/Fail:** **FAIL.** 100% packet loss. Workload's UDR to the spoke NVA is correctly in place (confirmed by S1.E1); the failure is downstream at the hub NVA (no return path to the CE) and there is a secondary NAT-related observation (see below).

**Assertion S1.D3 — Azure Network Watcher connectivity check**
- **Pass/Fail:** **NOT RUN.** Given the definitive negative result already captured via direct ping/route evidence (S1.D1/D2), and that Network Watcher connectivity checks would only reconfirm the same failure, this was not additionally run in this pass. Can be added on re-validation after the BIRD fix, for convergence-time comparison.

**Assertion S1.D4 — NSG effective rules on workload VM NIC**
- **What:** `az network nic list-effective-nsg -g rg-saprise-swedencentral -n nic-workload-probe -o json`.
- **Evidence path:** `show-output/s1-17-workload-nic-effective-nsg.json`
- **Pass/Fail:** **PASS.** No NSG is even associated to this NIC (only implicit `AllowVirtualNetwork`/`AllowAzureLoadBalancerInbound` defaults apply) — NSGs are confirmed NOT the cause of the reachability failures.

**Secondary observation (not a formal assertion) — spoke NVA NAT/forwarding**
- `az vm run-command invoke -g rg-saprise-swedencentral -n vm-spoke-nva --command-id RunShellScript --scripts "sysctl net.ipv4.ip_forward; iptables -t nat -L -n -v; ip route show"`.
- **Evidence path:** `show-output/s1-16-spoke-nva-forwarding-and-nat.txt`
- **Finding:** `net.ipv4.ip_forward=1` (correct), but the `SNAT_PUBLIC` iptables chain only `RETURN`s (no NAT) for RFC1918 destinations (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`) and `MASQUERADE`s everything else. The simulated on-prem prefix `172.40.100.0/24` is deliberately a non-RFC1918-looking range, so it falls through to MASQUERADE — traffic from the workload toward the CE gets source-NATted to the spoke NVA's own address on egress. This does not by itself explain the 100% loss (conntrack would still permit the return leg once a route exists) but is a real side effect flagged for Tank/Trinity's attention, independent of the BGP root cause.

---

### S1 Re-validation (2026-09-29, independent re-run after 5-round BGP fix chain)

> Ran by Niobe, independently — not a repeat of Tank's round-5 report. Fresh evidence captured
> to `show-output/s1-revalidation-*` (kept alongside the original `show-output/s1-*` FAIL-pass
> captures for the before/after story). Naming: `s1-revalidation-01` through `-16`.

**Re-validation R1 — BGP session status on vm-hub-nva, independently pulled**
- **What:** `birdc show protocols` via `az vm run-command invoke` (same method as the original FAIL pass).
- **Evidence:** `show-output/s1-revalidation-01-hub-protocols-poll1.json`
- **Result:** **PASS.** All three sessions simultaneously `Established`: `ce_onprem` (since 15:41:25), `azure_rs_1` (since 14:56:49), `azure_rs_2` (since 14:55:56). Confirms the 5-round BGP fix chain's outcome independently — this matches Tank's round-5 report and is a genuine improvement over the original FAIL pass's flapping evidence.

**Re-validation R2 — ARS learned routes from hub NVA**
- **What:** `az network routeserver peering list-learned-routes --routeserver ars-hub -n ars-hub-nva-peering`.
- **Evidence:** `show-output/s1-revalidation-05-ars-learned-routes.json`
- **Result:** **PASS.** ARS learns `10.60.0.0/16` (AS path `65001`) and `172.40.100.0/24` (AS path `65001-65000`) from the hub NVA on both peer IPs (10.40.0.36, 10.40.0.37). This is a genuine fix over the original FAIL pass, where ARS learned nothing but the CE's own prefix.

**Re-validation R3 — BIRD route table on hub NVA**
- **What:** `birdc show route` via `run-command`.
- **Evidence:** `show-output/s1-revalidation-06-bird-route-table-hub.json`
- **Result:** **PASS.** `10.60.0.0/16 unicast [static_bgp] via 10.60.0.4 on eth0 onlink` is present (the `onlink` fix confirmed live), and `10.40.0.0/16` from `azure_rs_1`/`azure_rs_2` is correctly marked `unreachable` (self-origin loop prevention working as intended — no kernel-poisoning regression).

**Re-validation R4 — THE CRITICAL TEST: ER Gateway learned/advertised routes and end-to-end data plane**
- **What:** `az network vnet-gateway list-bgp-peer-status` / `list-learned-routes` (polled twice, ~30s apart, to rule out propagation delay), plus live ping from `vm-ce-onprem` to both `10.60.0.4` (spoke NVA subnet) and `10.60.1.4` (workload subnet).
- **Evidence:** `show-output/s1-revalidation-02/03/07/08` (ER Gateway), `show-output/s1-revalidation-10-onprem-ce-bird-and-ping.json` (ping)
- **Result:** **FAIL on the data plane — unchanged from the original FAIL pass.** ER Gateway's BGP peer status shows `routesReceived: 0` on both ARS sessions (10.40.0.36, 10.40.0.37) on both polls; `list-learned-routes` still shows only `10.40.0.0/16` and the PE-link `169.254.170.152/30` route — `10.60.0.0/16` never appears, despite ARS confirmed holding it (R2). Ping from `vm-ce-onprem` to `10.60.0.4`: **100% packet loss** (4/4 dropped). Ping to `10.60.1.4`: **100% packet loss** (4/4 dropped). **Both S1 data-plane targets remain unreachable, exactly as in the original FAIL pass**, despite the BGP control-plane on the hub NVA being fully fixed and stable.

**Re-validation R5 — Root-cause isolation for the persisting data-plane failure (two independent defects found, neither touched by the 5-round BGP fix chain)**

1. **Defect A — ARS `allowBranchToBranchTraffic` is `false`.** `az network routeserver show -n ars-hub` (`show-output/s1-revalidation-09-ars-config-branch-to-branch.json`) confirms `"allowBranchToBranchTraffic": false`. This setting is required for Azure Route Server to propagate BGP routes learned from an NVA peer (the hub NVA) to a co-resident ExpressRoute/VPN gateway — without it, ARS only exchanges routes directly with each peer and does not act as a route reflector between them. This exactly explains R4: ARS has `10.60.0.0/16` from the hub NVA but never hands it to `ergw-sap-rise`. `design.md` §6.1 explicitly documents this as disabled by design ("not needed — single NVA peer, no VPN branches") and states (same section) that "ARS in turn peers automatically with the ER Gateway... and propagates the learned prefix" — **that second claim is incorrect as configured**; automatic ARS↔gateway route propagation requires branch-to-branch to be on. This is a design/config gap, not something the 5-round BGP investigation was scoped to catch (it validated BGP session state and BIRD route tables, not full route propagation to the gateway).
2. **Defect B — `vm-hub-nva`'s live kernel `ip_forward` is `0`.** Isolated re-check (`show-output/s1-revalidation-15-hub-nva-ipforward-isolated-confirm.json`): `cat /proc/sys/net/ipv4/ip_forward` → `0`; `/etc/sysctl.d/99-ip-forward.conf` contains `net.ipv4.ip_forward = 1` (the intended config), but this was never applied to the running kernel (`sysctl.conf`'s own commented-out line confirms it was never enabled there either). Locally-originated ping from the hub NVA to the spoke NVA (10.60.0.4) succeeds (`show-output/s1-revalidation-12`) because that's self-sourced traffic, not forwarded — but any packet arriving on the hub NVA destined for a different host would be dropped by the kernel, independent of any BGP/route state. This alone would sink the data-plane test even if Defect A were fixed.
3. **Contributing factor — the simulated on-prem CE has no Azure-fabric route to the spoke, even setting aside Defects A/B.** `vm-ce-onprem`'s NIC effective-route table (`show-output/s1-revalidation-11`) shows only `172.40.100.0/24` (VnetLocal) and `10.40.0.0/16` (VNetPeering, hub's own space) — no route to `10.60.0.0/16` at all. `vm-ce-onprem`'s own BIRD RIB does show `10.60.0.0/16` learned via its `hub_nva` BGP session, but a guest-OS BGP route does not program Azure's SDN forwarding plane (the same class of gap as the original Defect 1, just on the CE side of the topology this time). `snet-ce-onprem` has no route table/UDR attached (`show-output/s1-revalidation-16`). Because deviation #1 (simulated CE via full VNet peering, not a real ER-circuit path) bypasses the ER Gateway entirely, VNet peering is not transitive, and ARS only auto-injects routes into subnets of its own VNet (`vnet-hub` — confirmed present on `nic-hub-nva`'s own effective routes, `show-output/s1-revalidation-14`, as a `VirtualNetworkGateway`-type route to `10.60.0.0/16`) — never into a separately-peered VNet like `vnet-onprem-sim`. A UDR on `snet-ce-onprem` routing `10.60.0.0/16` to the hub NVA (10.40.1.4) as a virtual appliance would be needed for this specific simulated-CE test harness to exercise the data plane at all, mirroring what the ER Gateway would do automatically for a real on-prem circuit once Defect A is fixed.

**Overall S1 re-validation verdict: FAIL.** The BGP/BIRD defects (1-4) from the 5-round fix chain are genuinely and independently confirmed fixed — that work was correct and should not be redone. But S1's actual pass bar (end-to-end data-plane reachability to both spoke subnets from on-prem) is not met, and was never re-validated at the data-plane level before this pass — the round 5 verification focused on BGP session stability (`birdc show protocols`), not on whether packets actually flow. Two new, independent, previously-undiscovered defects (A: ARS branch-to-branch disabled; B: hub NVA kernel ip_forward not applied) plus one harness/design gap (C: no UDR path for the simulated CE) must be fixed before S1 can PASS. None of these three require touching the BGP config that Trinity/Tank already fixed.

**S2 readiness:** Not applicable yet. Per the task brief, S2 (`summarizedGatewayPrefixes` toggle) testing should not begin until S1 fully passes — layering S2 on top of a still-broken S1 data path would conflate failure modes, per this doc's own S2 section note below.

---

## Scenario 2: Advertised/Summarized Gateway Prefixes (Supernet Advertisement)

> **STATUS: PENDING — not executed in this pass.** `enable_summarized_gateway_prefixes` remains
> `false` in the deployed Terraform (`deployed-resources.md` confirms this). Toggling it and
> re-running S2 diagnostics is an explicit separate follow-up task, done only after S1's blocker
> (see Open Items below) is reviewed and, ideally, fixed and re-validated — testing S2 on top of a
> known-broken S1 redistribution path would conflate two different failure modes. All assertions
> below remain unscored (`_____`).

**Design claim:** Enable the `summarizedGatewayPrefixes` feature on the ER Gateway (or on the spoke VNet config; exact property location TBD per Trinity's design.md). This forces the ER Gateway to advertise the spoke supernet (10.60.0.0/16) to the ER circuit, even though only the peered subnet (snet-spoke-nva 10.60.0.0/27) is reachable via peering. BGP control-plane learns the /16 on ER side and on-prem CE side. **The open question:** Does the data-plane actually reach the workload subnet (10.60.1.0/24) at spoke, or does the packet drop due to lack of a system route in the spoke hub routing?

### Route Collection — Three-Layer (Identical to S1, Different Assertions on Control-Plane Content)

#### Layer 1: ER Gateway Learned & Advertised Routes (S2)

**Assertion S2.L1.1 — ER Gateway learned routes (S2 should be same as S1)**
- **What:** `az network express-route gateway list-learned-routes --resource-group <rg> --gateway-name <erGwName>`.
- **Expected:** ER Gateway learned table still contains `10.60.0.0/16` (via eBGP from the circuit), but the origin may now appear direct from the ER circuit side rather than from the hub NVA (depends on whether S2 moves the origin of this route in BGP). Interpretation: if `summarizedGatewayPrefixes` works as designed, the source of the /16 in the learned-routes table shifts from "BIRD redistributed by NVA" to "ER circuit advertising it back to the gateway." Trinity's design.md will clarify the expected AS-path.
- **Evidence path:** `show-output/s2-01-er-gateway-learned-routes.json`
- **Pass/Fail:** _____ (post-deploy)

**Assertion S2.L1.2 — ER Gateway advertised routes (S2 critical assertion)**
- **What:** `az network express-route gateway list-advertised-routes --resource-group <rg> --gateway-name <erGwName> --peer-group-name <peerGroup>`.
- **Expected:** With `summarizedGatewayPrefixes` enabled, the ER Gateway advertises the full spoke supernet `10.60.0.0/16` (not just the peered subnet 10.60.0.0/27) toward the ER circuit/MSEE. Compare this directly to S1.L1.2 — if S1 only advertised 10.60.0.0/27 due to subnet peering scope, S2 should now show 10.60.0.0/16.
- **Evidence path:** `show-output/s2-02-er-gateway-advertised-routes.json`
- **Pass/Fail:** _____ (post-deploy)
- **Critical:** This is the primary test of the `summarizedGatewayPrefixes` feature. If the /27 is still advertised instead of the /16, the feature is not working or is misconfigured.

**Assertion S2.L1.3 — ER Gateway BGP peer status (S2 same as S1)**
- **What:** `az network vnet-gateway list-bgp-peer-status --resource-group <rg> --gateway-name <erGwName>`.
- **Expected:** BGP session status unchanged from S1. Session to ARS/NVA peer is **Connected** (or if S2 disables ARS, the session may change; Trinity's design.md must clarify S2's dependencies).
- **Evidence path:** `show-output/s2-03-er-gateway-bgp-peer-status.json`
- **Pass/Fail:** _____ (post-deploy)

#### Layer 2: ER Circuit Provider Routes (S2)

**Assertion S2.L2.1 — ER circuit provisioning state (unchanged)**
- **What:** Same as S1.L2.1.
- **Expected:** `provisioningState == "Provisioned"`, `bgpStatus == "Up"`.
- **Evidence path:** `show-output/s2-04-er-circuit-provisioning-state.json`
- **Pass/Fail:** _____ (post-deploy)

**Assertion S2.L2.2 — Megaport MCR BGP session (S2 critical assertion)**
- **What:** Same Megaport looking glass or REST API query.
- **Expected:** MCR learned route table now includes `10.60.0.0/16` from ER circuit (ER GW advertises the supernet instead of the /27). MCR advertises the /16 to the simulated on-prem CE peer.
- **Evidence path:** `show-output/s2-05-megaport-mcr-bgp-routes.txt`
- **Pass/Fail:** _____ (post-deploy)
- **Interpretation:** If S2 works, this should show the /16 instead of the /27 compared to S1.L2.2. This is where the "summarized" label becomes visible in the provider's learned-routes table.

#### Layer 3: Azure Route Server (S2 variant)

**Assertion S2.L3.1 — ARS state in S2 (design dependent)**
- **What:** `az network vnet-gateway list-learned-routes --resource-group <rg> --gateway-name <arsName>` or ARS may be disabled/removed in S2 depending on Trinity's design.
- **Expected:** **Design-dependent.** If S2 replaces the ARS + NVA redistribution with a simpler mechanism (e.g., just the `summarizedGatewayPrefixes` flag without active NVA BGP), ARS may be removed. If S2 keeps ARS active, ARS still learns from hub NVA and may advertise the supernet in parallel. Trinity's design.md must specify.
- **Evidence path:** `show-output/s2-06-ars-state-s2.json` (or "Not applicable" if ARS removed)
- **Pass/Fail:** _____ (post-deploy)

### NIC Effective Routes & NSG Analysis (S2)

**Assertion S2.E1 — Spoke workload VM NIC effective routes (S2 critical for data-plane question)**
- **What:** `az network nic show-effective-route-table --resource-group <rg> --name <workloadVmNicName>`.
- **Expected:** **This is the crux of the S2 question.** In S1, the workload VM routing was completed by an explicit UDR pointing default traffic to spoke NVA. In S2, if the only change is `summarizedGatewayPrefixes` at the ER GW level, the workload VM's effective routes should STILL require the same UDR (or a system route that allows the spoke NVA to forward toward hub and thus to on-prem). If no such route exists, S2 control-plane (BGP learning) succeeds, but data-plane fails — this is the specific teaching scenario.
- **Evidence path:** `show-output/s2-07-spoke-workload-nic-effective-routes.json`
- **Pass/Fail:** _____ (post-deploy)
- **Note:** Expect this to be IDENTICAL to S1.E1 (same workload VM, no UDR change). If different, document the change in lessons-learned.

**Assertion S2.E2 — Hub NVA NIC effective routes (S2)**
- **What:** Same as S1.E2.
- **Expected:** Unchanged if S2 doesn't alter hub-side topology.
- **Evidence path:** `show-output/s2-08-hub-nva-nic-effective-routes.json`
- **Pass/Fail:** _____ (post-deploy)

**Assertion S2.E3 — Spoke NVA NIC effective routes (S2)**
- **What:** Same as S1.E3.
- **Expected:** Unchanged if S2 doesn't alter spoke-side peering.
- **Evidence path:** `show-output/s2-09-spoke-nva-nic-effective-routes.json`
- **Pass/Fail:** _____ (post-deploy)

### Data-Plane Connectivity — S2 (Summarized Gateway Prefixes)

**Assertion S2.D1 — Ping/traceroute from on-prem CE to spoke workload VM (S2 — THE OPEN QUESTION)**
- **What:** Same test as S1.D1, but executed in S2 deployment state.
- **Expected:**
  - **Optimistic:** Ping succeeds due to S2's supernet advertisement fixing the path implicitly (this is Trinity's hypothesis to be tested).
  - **Pessimistic:** Ping fails or times out because S2 advertises the supernet in control-plane (BGP), but data-plane to the non-peered workload subnet lacks a system route or explicit forwarding rule. This is the "control-plane-only fix" scenario.
  - **Actual:** To be determined by capture. This is why S2 exists as a scenario — to answer this question empirically.
- **Evidence path:** `show-output/s2-10-onprem-to-workload-ping.txt` + `show-output/s2-11-onprem-to-workload-traceroute.txt`
- **Pass/Fail:** _____ (post-deploy)
- **Analysis:** Compare S2.D1 directly to S1.D1. If both pass, S2 is a valid alternative to S1 (control-plane simplification). If S2 fails, S2 teaches why control-plane advertisement alone is insufficient without data-plane routes.

**Assertion S2.D2 — Reverse connectivity: spoke workload to on-prem CE (S2)**
- **What:** Same as S1.D2.
- **Expected:** Outbound from workload should work via the workload VM's UDR (or system route). If inbound (S2.D1) fails but outbound succeeds, document as asymmetry in lessons-learned.
- **Evidence path:** `show-output/s2-12-workload-to-onprem-ping.txt` + `show-output/s2-13-workload-to-onprem-traceroute.txt`
- **Pass/Fail:** _____ (post-deploy)

**Assertion S2.D3 — Azure Network Watcher connectivity check (S2)**
- **What:** Same as S1.D3.
- **Expected:** Connectivity check result (Reachable / Unreachable / Probe limits). Compare to S1.D3 to see if S2 differs.
- **Evidence path:** `show-output/s2-14-network-watcher-connectivity-s2.json`
- **Pass/Fail:** _____ (post-deploy)

**Assertion S2.D4 — NSG effective rules (S2, unchanged expected)**
- **What:** Same as S1.D4.
- **Expected:** NSG rules are unchanged across S1 and S2 (unless Trinity's design includes an NSG relaxation as part of S2). Effective rules should still allow ICMP/TCP/UDP if S1 allowed it.
- **Evidence path:** `show-output/s2-15-workload-nic-effective-nsg.json`
- **Pass/Fail:** _____ (post-deploy)

---

## Open Items / Blockers

### Resolved by the 5-round BGP fix chain (Trinity/Tank, confirmed independently by Niobe on re-validation)

1. ~~Recursive-next-hop static route never resolves~~ — **FIXED.** `onlink` static route confirmed live in `birdc show route` (re-validation R3).
2. ~~`ce_onprem export none` blocking CE advertisement~~ — **FIXED.** CE's `hub_nva` session now receives `10.60.0.0/16` (confirmed in `vm-ce-onprem`'s own BIRD RIB, re-validation R4/evidence `s1-revalidation-10`).
3. ~~BGP session instability / flapping~~ — **FIXED.** All three hub-NVA sessions independently confirmed simultaneously `Established` (re-validation R1); root causes were hub `protocol kernel export all;` poisoning (closed round 3) and CE-side timer mismatch (closed round 5).
4. ~~Secondary NAT observation (spoke NVA `SNAT_PUBLIC` MASQUERADE for non-RFC1918 CE prefix)~~ — not re-tested this pass since the data-plane test fails upstream of the spoke NVA; re-check once Defects A/B below are fixed and packets actually reach the spoke NVA's NAT layer.

### New — flagged for Trinity/Tank, found on this re-validation pass, not fixed by Niobe

**A. ARS `allowBranchToBranchTraffic` is `false`, blocking ARS→ER-Gateway route propagation.**
`az network routeserver show -n ars-hub` shows `"allowBranchToBranchTraffic": false`. This is
required for Azure Route Server to hand NVA-learned routes (like `10.60.0.0/16` from
`vm-hub-nva`) to a co-resident ExpressRoute/VPN gateway. Confirmed effect: ARS has the route
(re-validation R2) but `ergw-sap-rise` shows `routesReceived: 0` from both ARS peers and never
lists `10.60.0.0/16` in its learned-routes table (re-validation R4), on two polls 30s apart.
`design.md` §6.1 both disables this setting by design and separately claims automatic
ARS→gateway propagation happens regardless — those two statements are in tension; recommend
Trinity revisit §6.1/§6.2 and confirm whether `allowBranchToBranchTraffic = true` should be
added to the S1 Terraform config. **Fix:** `az network routeserver update -g rg-saprise-swedencentral -n ars-hub --allow-b2b-traffic true` (or equivalent Terraform property), then re-poll ER Gateway learned routes.

**B. `vm-hub-nva`'s live kernel `net.ipv4.ip_forward` is `0`, despite a sysctl.d file specifying `1`.**
`/etc/sysctl.d/99-ip-forward.conf` contains `net.ipv4.ip_forward = 1`, but the running kernel
value is `0` (`cat /proc/sys/net/ipv4/ip_forward` → `0`). This means the hub NVA cannot forward
any transit packet regardless of route/BGP state — it would only ever serve as a BGP speaker,
not an actual router. Locally-sourced pings from the hub NVA succeed and mask this in any test
that doesn't specifically check forwarded (as opposed to self-originated) traffic. **Fix:**
`sysctl -p /etc/sysctl.d/99-ip-forward.conf` (or `sysctl -w net.ipv4.ip_forward=1`) applied via
`run-command`, and add a boot-time verification step to the VM's cloud-init/deploy process so
this doesn't silently drift again (e.g. after a future reboot if the drop-in file itself is ever
lost or a race with `NetworkManager`/`systemd-sysctl` on this image reverts it).

**C. Harness/design gap — the simulated on-prem CE has no Azure-fabric route to the spoke, independent of A/B.**
`vm-ce-onprem`'s NIC effective-route table has no entry for `10.60.0.0/16` (only its own subnet
and the hub's `/16` via the full-VNet peering); `snet-ce-onprem` has no UDR/route table attached.
Because deviation #1 (CE simulated as a full-VNet-peered Azure VM, not a real ER-circuit path)
bypasses the ER Gateway entirely, ARS's route injection — which only auto-populates subnets
*within* `vnet-hub` itself (confirmed present on `nic-hub-nva`, re-validation evidence
`s1-revalidation-14`) — never reaches `vnet-onprem-sim`, a separately-peered VNet. Fixing A and
B will make a *real* on-prem circuit work end-to-end, but this specific simulated-CE test
harness additionally needs a UDR on `snet-ce-onprem` (`10.60.0.0/16` → VirtualAppliance
`10.40.1.4`) to actually exercise the data plane, since VNet peering is not transitive. Recommend
Trinity decide whether this UDR is an accepted, documented part of the CE-simulation deviation,
or whether the CE should be re-modeled to test through the real ER Gateway/Megaport path instead.

**Recommended next step:** Tank applies fixes A and B (and C if the simulated-CE harness is kept
as-is), then Niobe re-runs the full S1 data-plane test (both target subnets) before S2 is
attempted. Given A/B/C are unrelated to the BGP config already fixed, this should not require
touching `bird.conf` on either VM again.

---

## Summary Comparison Table (Post-Deploy Filling)

> Columns show the **original FAIL pass** result and the **re-validation (post 5-round BGP fix)**
> result side by side, so the before/after story is visible at a glance.

| Assertion | S1 Expected | S1 Result (original) | S1 Result (re-validation) | S2 Result | Notes |
|-----------|------------|----------------------|---------------------------|----------|-------|
| **P1:** Subnet-scoped peering in place | ✓ | **PASS** | **PASS** (unchanged) | n/a | snet-hub-nva ↔ snet-spoke-nva only |
| **L1:** ER GW learned 10.60.0.0/16 | ✓ via NVA | **FAIL** (absent) | **FAIL** (still absent — see Defect A, ARS branch-to-branch) | _____ | Compare AS-path origin |
| **L1:** ER GW advertises 10.60.0.0/16 | ✓ (or /27 if no redistribution) | **FAIL** (absent) | **FAIL** (still absent, same root cause) | _____ | S2 must advertise full /16 |
| **L2:** Megaport sees 10.60.0.0/16 | ✓ | **NOT RUN** | **NOT RUN** (still not needed — failure confirmed upstream at ARS→ERGW hop) | _____ | Learned from ER circuit; deferred |
| **L3:** ARS learns 10.60.0.0/16 | ✓ | **FAIL** (only learns 172.40.100.0/24) | **PASS** (now learns 10.60.0.0/16 from hub NVA, both peer IPs) | _____ | Genuine fix confirmed |
| **L4:** BIRD installs/exports 10.60.0.0/16 | ✓ | **FAIL** (recursive-nexthop resolution) | **PASS** (`onlink` route confirmed live; all 3 BGP sessions Established) | n/a | Genuine fix confirmed |
| **E1:** Workload VM has egress route | ✓ UDR to NVA | **PASS** | **PASS** (not re-tested, no reason to expect regression) | _____ | **Critical for S2 data-plane** |
| **D1:** On-prem → spoke-nva subnet ping | ✓ | **FAIL** (100% loss) | **FAIL** (100% loss, unchanged) | n/a | Root cause now: Defect A + B (see Open Items), not BIRD |
| **D1:** On-prem → workload subnet ping | ✓ | **FAIL** (100% loss) | **FAIL** (100% loss, unchanged) | _____ | **This is what S2 exists to test** — S1 still fails both targets |
| **D2:** Workload → on-prem ping (reverse) | ✓ | **FAIL** (100% loss) | **NOT RE-TESTED** (forward-path fails upstream of the spoke NVA; re-check once A/B fixed) | _____ | Secondary NAT observation still open |
| **D3:** Network Watcher check | ✓ Reachable | **NOT RUN** | **NOT RUN** | _____ | Direct ping evidence already definitive both times |
| **D4:** NSG rules do not block traffic | ✓ | **PASS** (no NSG associated) | **PASS** (not re-tested, no reason to expect regression) | _____ | Confirmed not the blocker |

---

## Evidence Artifact Layout (Post-Deploy)

```
labs/sap-rise-scoped-peering-fwaas/
├── validation.md (this file)
├── README.md (summary + links to evidence)
├── show-output/                                        (S1 — actually captured, this pass)
│   ├── s1-01-hub-vnet-peering-list.json
│   ├── s1-01b-spoke-vnet-peering-list.json
│   ├── s1-02-er-gateway-bgp-peer-status.json
│   ├── s1-03-er-gateway-learned-routes.json
│   ├── s1-04-er-gateway-advertised-routes.json
│   ├── s1-05-er-circuit-provisioning-state-DEFERRED.txt
│   ├── s1-06-ars-learned-routes.json
│   ├── s1-07-ars-advertised-routes.json
│   ├── s1-08-ars-peering-list.json
│   ├── s1-09-bird-protocols-and-routes-poll1.txt
│   ├── s1-10-bird-second-poll-flap-evidence.txt
│   ├── s1-11-bird-conf-and-root-cause.txt
│   ├── s1-12-ce-onprem-bird-and-routes.txt
│   ├── s1-13-onprem-to-spoke-and-workload-ping.txt
│   ├── s1-14-workload-to-onprem-ping-and-routes.txt
│   ├── s1-15-nic-effective-routes-all-three.txt
│   ├── s1-16-spoke-nva-forwarding-and-nat.txt
│   └── s1-17-workload-nic-effective-nsg.json
│   (S2 — not yet captured; pending follow-up task, see Scenario 2 STATUS banner above)
│   ├── s1-16-workload-to-onprem-ping.txt
│   ├── s1-17-workload-to-onprem-traceroute.txt
│   ├── s1-18-network-watcher-connectivity-s1.json
│   ├── s1-19-workload-nic-effective-nsg.json
│   ├── s2-01-er-gateway-learned-routes.json
│   ├── s2-02-er-gateway-advertised-routes.json
│   ├── s2-03-er-gateway-bgp-peer-status.json
│   ├── s2-04-er-circuit-provisioning-state.json
│   ├── s2-05-megaport-mcr-bgp-routes.txt
│   ├── s2-06-ars-state-s2.json
│   ├── s2-07-spoke-workload-nic-effective-routes.json
│   ├── s2-08-hub-nva-nic-effective-routes.json
│   ├── s2-09-spoke-nva-nic-effective-routes.json
│   ├── s2-10-onprem-to-workload-ping.txt
│   ├── s2-11-onprem-to-workload-traceroute.txt
│   ├── s2-12-workload-to-onprem-ping.txt
│   ├── s2-13-workload-to-onprem-traceroute.txt
│   ├── s2-14-network-watcher-connectivity-s2.json
│   └── s2-15-workload-nic-effective-nsg.json
├── screenshots/
│   ├── er-gateway-learned-routes-blade.png
│   ├── network-watcher-topology.png
│   └── (others TBD post-deploy)
└── lessons-learned.md
```

---

## Scoring Rules

- **Pass** (✓): Assertion result matches expected state. Data-plane connectivity confirmed.
- **Fail** (✗): Assertion result does NOT match expected state. Root cause must be documented in lessons-learned and escalated to Trinity for design re-evaluation.
- **Blocked** (⊘): Assertion depends on a prior-layer assertion that failed. Document the dependency.

---

## Post-Deploy Reconciliation Checklist

- [x] Cross-check all subnet CIDRs, NIC names, and resource group against Trinity's final design.md — done via `az resource list -g rg-saprise-swedencentral`; all names match `deployed-resources.md`.
- [x] Verify ASN values (hub NVA 65001, spoke NVA 65002, ARS 65515, on-prem CE 65000) match design — confirmed in BIRD `show protocols all` and ARS peering list captures.
- [ ] If Trinity's design includes ARS features (route policies, summarization rules) beyond basic redistribution, add assertions for those — not applicable to S1 as deployed; revisit for S2.
- [ ] If Trinity's design patches the SPOF (single path in S1) with an alternative BGP neighbor or redundant path, add before/after route captures per Niobe charter — not applicable; S1 has zero working paths currently (see Open Items), no SPOF-patch evidence to compare yet.
- [x] Confirm Megaport VXC service key and API credentials are redacted before commit — no Megaport API calls made in this pass; all `show-output/` files use `<SUBSCRIPTION_ID>` placeholders and contain no VXC service keys.
- [x] If ER circuit provisioning state is not "Provisioned" by deploy time, note delay and re-check — `deployed-resources.md` already records `provisioningState: Succeeded` on the gateway; circuit-level re-check deferred (see S1.L2.1) since it does not affect the S1 verdict.
- [ ] **NEW:** Re-run the full S1 capture set after Tank patches `bird.conf` (see Open Items) — this is the actual blocking item before S1 can be marked ready for teardown.
- [ ] **NEW:** Execute S2 diagnostics once S1 is confirmed working end-to-end (separate follow-up task, out of scope for this pass).

