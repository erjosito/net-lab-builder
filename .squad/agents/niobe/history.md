# Project Context

- **Owner:** Jose Moreno
- **Project:** net-lab-builder — build, document, and tear down ephemeral Azure Networking labs
- **Stack:** Azure CLI (effective routes, flow logs, NSG metrics); Network Watcher; portal screenshots; Bash/PowerShell glue
- **Created:** 2026-05-28
- **Role:** Lab Validator & Diagnostics — own labs/<lab>/{README.md, lessons-learned.md, show-output/, screenshots/, validation.md}; action verb vocabulary; sanitization checklist

**📌 SUMMARIZATION NOTE (2026-07-31):** This file has grown to ~19KB. Pre-Phase 3 learnings archived in `history-archive.md`. Active learnings (Phase 3 Gates A, B, C validation) retained below.

## Learnings (2026-07-31T11:45:00+02:00)

**Phase 3 Gate C — FULL PASS / BUG NOT REPRODUCED — vwan-routemap-summarization**

### Gate C outcome

RI PrivateTraffic enabled on hub-eu2 (Tank). Measured both NVAs immediately after.
RI enablement order: hub-eu1 FIRST (Gate B, ~09:30), hub-eu2 SECOND (Gate C, ~11:30).

| Hub | NVA | RI state | BGP | Summaries | /24 leaks | Verdict |
|-----|-----|----------|-----|-----------|-----------|---------|
| hub-eu1 | nva1 | ON | Established | **6/6** | **0** | **PASS** |
| hub-eu2 | nva2 | ON (new) | Established | **6/6** | **0** | **PASS** |

**Headline: Missing-summary bug NOT reproduced under sequential RI enablement.**

### Key empirical findings

1. **Bug not reproduced.** Sequential RI enablement (stable state, no concurrent churn) did not
   trigger the missing-summary condition at any gate (A, B, or C). All 6 summaries present on
   both NVAs throughout the entire Phase 3 validation sequence.

2. **Route count stable at 37/27 across ALL three gates.** No routes added or lost as RI was
   progressively enabled. NVA BIRD RIB is driven by BGP from the hub VPN GW and is orthogonal
   to RI's forwarding table changes.

3. **BGP transparency across both RI enablements.** nva1's vpngw0/vpngw1 timestamps unchanged
   from Gate A through Gate C (07:37:23/07:37:38 — never reset). nva2's vpngw0 had one brief
   reconvergence at Gate B (hub-eu1 RI provision, 08:57:07), then was stable through Gate C.
   Both RI enablements on hub-eu2 itself were BGP-transparent.

4. **defaultRouteTable both hubs: _policy_PrivateTraffic confirmed.** Both hubs carry RFC1918
   aggregates (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16) → AzFW. This is the full RI state.
   These aggregates did NOT suppress the per-connection route-map advertisement set at any point.

5. **prepend-in AS-path effect is intra-hub.** The prepend-in route-map on hub-eu2 modifies
   routes received FROM nva2 into hub-eu2. This effect is not visible in nva2's received-route
   BIRD table. nva2 sees the hub's outbound (summarize-out) advertisement, not the inbound
   prepend result. Confirmed Succeeded; de-preference mechanism intact at hub level.

6. **Outstanding question for Trinity.** Bug may require concurrent churn: VPN connection
   re-provisioning + RI enablement in the same time window. Not tested in this sequential lab.

### Key file paths

- show-output/43: both hubs secured + RI Succeeded (L1a)
- show-output/44: route-maps intact (L1c); prepend-in confirmed
- show-output/45: both defaultRouteTables with _policy_PrivateTraffic (L1d)
- show-output/46: both firewalls Succeeded (L1e)
- show-output/47: nva2 BGP Established (RI-ON)
- show-output/48: **PRIMARY** nva2 BIRD RIB (6/6, 0 leaks, newly RI-ON hub)
- show-output/49: nva2 route count (37/27)
- show-output/50: nva1 BGP Established (stable since Gate A)
- show-output/51: **PRIMARY** nva1 BIRD RIB (6/6, 0 leaks, both hubs RI-ON)
- show-output/52: nva1 route count (37/27)
- validation.md: Gate C section added (FULL PASS, bug not reproduced)
- decisions/inbox/niobe-gate-c.md: team verdict + repro gap analysis



### Gate B outcome

RI PrivateTraffic enabled on hub-eu1 (swedencentral). Measured both NVAs immediately after.

| Hub | NVA | RI state | BGP | Summaries | /24 leaks | Verdict |
|-----|-----|----------|-----|-----------|-----------|---------|
| hub-eu1 | nva1 | **ON** | vpngw0+vpngw1 Established | **6/6** | **0** | **PASS** |
| hub-eu2 | nva2 | OFF (control) | vpngw0+vpngw1 Established | **6/6** | **0** | **PASS** |

**Overall: FULL PASS.** RI and route-map summaries coexist without interference.

### Key empirical findings

1. **RI does NOT suppress route-map summaries.** The 10.0.0.0/8 aggregate in hub-eu1's
   defaultRouteTable (_policy_PrivateTraffic) is a forwarding-layer construct (AzFW next-hop steering).
   It does not modify the BGP advertisement set outbound to the VPN connection.
   nva1's BIRD RIB: identical structure to Gate A — 6/6 summaries, 37/27, 0 /24 leaks.

2. **RI enablement is BGP-transparent to the branch NVA.** nva1 vpngw0+vpngw1 timestamps
   unchanged (07:37:23 / 07:37:38 from Gate A restore). Sessions not reset during RI enablement.

3. **Brief vpngw0 reconvergence on nva2 (08:57:07).** Expected: when hub-eu1 undergoes
   provisioning, nva2's vpngw0 session briefly reconverged. Not a failure — the RI enablement
   on a peer hub causes a momentary hub-to-hub topology update that ripples to the non-RI hub's
   VPN gateway BGP sessions. vpngw1 on nva2 stayed up continuously.

4. **RIB symmetry confirmed.** nva1 (RI-on hub) and nva2 (RI-off hub) show structurally
   identical RIBs at Gate B — same 6 summaries, same 37/27 count.

### Key file paths

- show-output/34: nva2 birdc show protocols (RI-off control, Established)
- show-output/35: **PRIMARY** nva2 BIRD RIB (6/6 summaries, RI-off)
- show-output/36: nva2 route count (37/27)
- show-output/37: nva1 birdc show protocols (RI-ON hub, Established, timestamps unchanged)
- show-output/38: **PRIMARY** nva1 BIRD RIB (6/6 summaries, RI-ON hub — key evidence)
- show-output/39: nva1 route count (37/27)
- validation.md: Gate B section added (FULL PASS)
- decisions/inbox/niobe-gate-b.md: team verdict



### Gate A full re-run outcome

After Tank rebuilt nva1 via `az vm redeploy` (~90 min in swedencentral, clearing the stuck
RunCommandLinux extension), Niobe completed the full Gate A measurement on both NVAs.

| Hub | NVA | BGP | Summaries | /24 leaks | Verdict |
|-----|-----|-----|-----------|-----------|---------|
| hub-eu1 | nva1 | vpngw0+vpngw1 **Established** | **6/6** | **0** | **PASS** |
| hub-eu2 | nva2 | vpngw0+vpngw1 **Established** | **6/6** | **0** | **PASS** |

**Overall: FULL PASS.** Deploying Azure Firewalls (RI OFF) does NOT break outbound
route-map summarization on either hub. Gate B (RI enable) may proceed on both hubs.

### Key facts

- Both NVAs: 37 routes / 27 networks in BIRD RIB.
- 6 summaries confirmed: 10.0.0.0/16, 10.1.0.0/16, 10.2.0.0/16, 10.3.0.0/16, 10.4.0.0/17, 10.4.128.0/17.
- Non-summary /24s (10.100.0.0/24 GCP, 10.200.0.0/24 nva1 mgmt, 10.201.0.0/24 nva2 mgmt) are infrastructure prefixes outside the route-map scope — not leaks.
- `az network vhub route-map get-outbound-routes` remains non-functional. Correct syntax confirmed: `--resource-uri <ARM_URI>` (not `--connection-name`). Still returns empty (exit 0, no body). L2 BIRD RIB is the authoritative gate.

### Key file paths

- show-output/23: nva1 birdc show protocols (BGP Established)
- show-output/24: nva2 birdc show protocols (BGP Established)
- show-output/25: **PRIMARY** nva1 BIRD RIB (6/6 summaries, 0 leaks)
- show-output/26: **PRIMARY** nva2 BIRD RIB (6/6 summaries, 0 leaks)
- show-output/27: nva1 route count (37/27)
- show-output/28: nva2 route count (37/27)
- show-output/29: get-outbound-routes API gap (--resource-uri syntax confirmed, still empty)
- show-output/30: AzFW Succeeded + RI = [] both hubs re-confirmed
- validation.md: Phase 3 Gate A section updated to FULL PASS
- decisions/inbox/niobe-gate-a-full.md: team verdict

### CLI gotcha: --resource-uri vs --connection-name

`az network vhub route-map get-outbound-routes` requires `--resource-uri <full_ARM_path>`,
NOT `--connection-name`. The ARM URI must include the full vpnGateway/vpnConnections path:
  `/subscriptions/<SUB>/resourceGroups/<RG>/providers/Microsoft.Network/vpnGateways/<gw>/vpnConnections/<conn>`
Even with correct syntax, the API returns empty. Capture this once per gate to document the gap.



### Gate A outcome

- **hub-eu2/nva2: PASS** — 6/6 summaries (10.0.0.0/16, 10.1.0.0/16, 10.2.0.0/16, 10.3.0.0/16, 10.4.0.0/17, 10.4.128.0/17), 0 /24 leaks, BGP Established (vpngw0+vpngw1), firewall did NOT break route-maps.
- **hub-eu1/nva1: INCONCLUSIVE** — All control-plane checks PASS; nva1 NVA-level measurement blocked by terminally stuck RunCommandLinux extension (pre-existing fault, persists across restart/deallocation). VPN tunnels not restored. Not a firewall-caused failure.
- **Overall: CONDITIONAL PASS** — Proceed-to-RI conditionally safe for hub-eu2; Tank must rebuild nva1 before hub-eu1 can be fully measured.

### XFRM restoration procedure (tested, reusable — see .squad/skills/vwan-nva-xfrm-restore/SKILL.md)

Six-step procedure for hub-eu2/nva2 (tested and confirmed):
1. `ip link add xfrm41 type xfrm dev eth0 if_id 41; ip link set xfrm41 up`
2. `ip link add xfrm42 type xfrm dev eth0 if_id 42; ip link set xfrm42 up`
3. `ip route add 192.168.4.12/32 dev xfrm41; ip route add 192.168.4.13/32 dev xfrm42`
4. `swanctl --load-all`
5. `swanctl --initiate --child s2s0 --ike vng0 --timeout 30; swanctl --initiate --child s2s1 --ike vng1 --timeout 30`
6. Wait 75s for BGP convergence
Total time from deallocated → BGP Established: ~3 minutes.

### `get-outbound-routes` API is non-functional in this config

`az network vhub route-map get-outbound-routes` (preview) consistently returns empty. REST API returns HTTP 404 "No route data was found." Use L2 BIRD RIB (`birdc show route`) as the authoritative measurement for all Gates.

### nva1 stuck extension: persistent across restart

The RunCommandLinux extension on nva1 is terminally stuck. Conflict/409 on invoke; newer persistent API hangs on create/update/delete. Even delete of the resource hangs. VM restart/deallocation does not clear it. Tank must `az vm redeploy` or delete+recreate nva1.

### Key file paths

- show-output/13–20: Gate A evidence files
- validation.md: Phase 3 Gate A section added with full checklist
- lessons-learned.md: Phase 3 findings section added
- .squad/decisions/inbox/niobe-phase3-gate-a.md: verdict for Jose
- .squad/skills/vwan-nva-xfrm-restore/SKILL.md: reusable XFRM restore skill

## Learnings (2026-07-30T15:21:56+02:00)

**Documentation review pass — vwan-routemap-summarization**

Reviewed and updated three lab files after the Phase 3 audit and failover/failback session:

- **validation.md** (Niobe's file): corrected stale self-reference about README gap (now fixed); tightened Phase 2 summary sentence to remove "awaiting Tank/Kid correction" since the fix was applied in this session.
- **README.md**: updated "Designs studied" table (Phase 1 → "Deployed/validated" with cycle count; Phase 2 → "Infrastructure deployed, ER connections active"; Phase 3 → "Not started, confirmed 2026-07-30"). Added Phase 2 resources to "Deployed state" section (ER circuits, ER gateways, GCP VPN sites, kv-pe private endpoint, ER connections).
- **manifest.md**: updated resource inventory table with Phase 2 resources (added Phase column); corrected "Out of scope" section (Phase 2 is deployed, Phase 3 not yet started); added Phase 2 NVA operational note (XFRM persistence gap + startup sequence) to Scenario 3.
- **decisions/inbox/niobe-phase3-audit.md**: added Oracle (Docs) routing note with 4 structural items that are prose/diagram rewrites, out of Niobe's factual-correction scope.

**Items routed to Oracle:** README intro paragraph, manifest topology ASCII, manifest §6 scenario walkthroughs (Phase 2 repro), manifest §2 in-scope statement.

---

## Learnings (2026-07-30T13:48:36+02:00)

**Failover/failback cycle #4 + Phase 2 documentation gap — routemap-test-rg**

1. **Phase 2 fully deployed (documentation gap).** First audit incorrectly reported ER gateways as having no connections because the query used `--query "connections"` instead of `--query "expressRouteConnections"`. The correct field for ExpressRoute gateway connections is `expressRouteConnections`. Both ergw-eu1 and ergw-eu2 have active ER connections (conn-er-eu1 / conn-er-eu2, both Succeeded). README and manifest.md show Phase 2 as "Not started" — this is a documentation gap requiring Tank/Kid action.

2. **XFRM interfaces not persistent across deallocation.** After VMs are deallocated/started, XFRM interfaces (xfrm41/xfrm42, type xfrm, if_id 41/42) are NOT recreated automatically. Must run: `ip link add xfrm41 type xfrm dev eth0 if_id 41; ip link set xfrm41 up; ip route add 192.168.4.12/32 dev xfrm41` (and same for xfrm42/42). Also: `swanctl --load-all` is needed since strongswan-starter uses ipsec.conf (empty) not swanctl.conf. And `swanctl --initiate --child s2sX --ike vngX` needed since `start_action = trap` does not auto-connect.

3. **Failover cycle #4 CLEAN.** hub-eu2/nva2: 6/6 summaries before and after 45s IPsec+BGP teardown and restart. Phase 2 ER routes visible in nva2 BIRD table (192.168.2.0/23 with ER AS paths, 10.100.0.0/24 via GCP ER).

4. **CLI gotcha: ER gateway field.** `az network express-route gateway show --query connections` returns empty. Correct field: `expressRouteConnections`. Confirm with `az network express-route gateway show -g <rg> -n <gw> -o json | findstr -i connection` to see actual field names.

5. **nva1 run-command stuck.** A complex multiline shell script with mixed PowerShell/bash syntax got stuck in the Azure VM run-command extension. The extension locked nva1 for the entire session, blocking all subsequent run-command attempts. Avoid multi-line scripts with `2>/dev/null` piped grep patterns in PowerShell — use @' '@ heredoc and simple single-line commands.

---

## Learnings (2026-07-30T13:35:49+02:00)

**Phase 3 audit — routemap-test-rg live state**

Ran a full live audit of `routemap-test-rg` on 2026-07-30 to answer "are we in Phase 3?"

**Key findings:**
1. **Phase 3 NOT started.** No Azure Firewalls (`az network firewall list` → empty), no Firewall Policies, no Routing Intent on any of the 3 hubs. Hub `azureFirewall = null` and `securityProviderName = null` on hub-us, hub-eu1, hub-eu2. All hubs are non-secured virtual hubs.

2. **Phase 2 infrastructure partially deployed (undocumented).** The RG contains 2 ER circuits (er-eu1/swedencentral, er-eu2/westeurope — both Enabled/Provisioned), 2 ER gateways (ergw-eu1, ergw-eu2 — both Succeeded), 4 VPN sites (onprem1/2 + gcp1/2), and a Key Vault private endpoint. However, both ER gateways have `connections = null` — so Phase 2 is infrastructure-deployed but not operationally connected.

3. **Phase 1 substrate intact.** All 3 hubs Provisioned/Succeeded. Route maps `summarize-out` on hub-eu1 and hub-eu2 (Succeeded); `prepend-in` on hub-eu2 (Succeeded).

4. **Sequencing discrepancy.** Jose wants to jump straight to Phase 3 (Azure Firewall + Routing Intent), but docs sequence Phase 2 first. Phase 2 infra already exists with no connections. Team needs to decide: complete Phase 2 first, or clean-skip to Phase 3.

**CLI gotcha:** `az network vhub routing-intent list` requires `--vhub` (short flag), NOT `--vhub-name`. Using `--vhub-name` returns "argument required: --vhub" error.

**Evidence filed:** show-output/08 (resource inventory), 09 (Phase 3 audit), 10 (Phase 2 ER audit).
**Decisions inbox:** `.squad/decisions/inbox/niobe-phase3-audit.md`

---

## Learnings (2026-06-15T23:32:10+02:00)

**MSEE hairpin IPv6 validation skeleton** — Lab: `msee-hairpin-hns-vwan-ipv6`

**Key insights from charter & charter review:**

1. **IPv6 BGP peer-status capture pattern** — When validating dual-stack ER scenarios, capture HnS ER GW peers separately from vWAN hub BGP connections. HnS uses `az network vnet-gateway list-bgp-peer-status` (old VNet GW API); vWAN uses `az network vhub bgpconnection list` (hub API). Both must show IPv4+IPv6 neighbors up before routing captures are valid.

2. **MSEE hairpin validation layers** — Simpler than multi-hub: only two ER GW layers + two ER circuit layers (no Megaport MCR, no vWAN hub REST inbound/outbound). Route-table captures at ER GW (learned+advertised) + ER circuit (list-route-tables) suffice. Three-layer pattern applies; no fourth (MCR) or fifth (vHub REST) layer needed.

3. **Deliberate-break testing (S4 pattern)** — MSEE hairpin is gated by `allowVirtualWanTraffic` toggle on HnS ER GW. Disabling it drops BGP session within 30–60 sec, breaks both IPv4 and IPv6, then re-enabling restores it symmetrically. This is the critical proof of the hairpin mechanism: hairpin exists ⟺ flag is ON. Evidence: before/after BGP peer state + learned routes + data-plane ping.

4. **Pre-flight gates** — Circuits must be `Provisioned` (not just `Enabled`) and both IPv4+IPv6 peering sub-resources must exist on each circuit. BGP peers must be up before route capture. Path A (ER Direct) also requires ER port status = `Succeeded`.

5. **File count expectation** — ~31 files vs ~35 for vwan-dual-er-symmetric (simpler topology, no MCR BGP, no asymmetric-injection Phase A breakage into cross-region flows). Pre-flight 6 + S1 5 + S2 5 + S3 4 + S4-disable 7 + S4-revert 6 = 33 baseline, minus ~2 for reused evidence paths = ~31.

**Validation skeleton structure:**
- Pre-flight checks (subscription, circuits, ER ports, BGP peers) — 6 files
- S1 IPv4 baseline — 5 files (learned-routes, advertised-routes, NIC routes, ping, circuit route-tables)
- S2 IPv6 primary — 5 files (learned-routes IPv6, advertised-routes IPv6, NIC routes, ping, BGP IPv6 peer)
- S3 route-table mutual distribution — 4 files (reuse S1/S2 evidence; add vWAN GW learned/advertised pair)
- S4 deliberate-break (disable + revert) — 13 files (pre-disable baseline, toggle OFF, verify OFF, BGP down, pings fail, learned-routes empty, toggle ON, verify ON, BGP up, pings restored ×2)
- Total: 18.4 KB skeleton; ~31 show-output files when live

**Designs studied section** — Three rows (Path A ER Direct, Path B Megaport fallback, Path C IPsec VPN) with verdicts TBD; evidence links pending; A is "recommended if S1–S2 pass", B is "not recommended per Jose gate", C is "teaching-only (mechanism differs)". This follows rule #30: every design enumerated by Morpheus gets documented.

**Reuse from vwan-dual-er-symmetric** — Assertion table structure (# | Assertion | Command | Expected | Evidence), three-layer checklist pattern, sanitization checklist, post-deploy validation order, BGP peer-status check pattern. Adapted for simpler topology (no MCR, no vHub REST layers) and dual-stack MSEE-only (no GCP multi-region cross-traffic).


---

📌 Team update (2026-07-31T11:01:11Z): **Phase 3 Gates A, B, C FULL PASS — Complete Testing Arc**. Gate A (firewall deploy, RI OFF): 6/6 summaries on both NVAs, 0 /24 leaks, BGP Established. Gate B (RI hub-eu1): 6/6 summaries intact, BGP transparent (session timestamps unchanged from Gate A). Gate C (RI hub-eu2, both hubs now RI-ON): 6/6 summaries survive, BGP stable across all three gates. Missing-summary bug NOT reproduced under sequential stable-state enablement. Root-cause analysis (Trinity): RI operates on data-plane forwarding table; summarize-out operates on BGP advertisement set — orthogonal planes. Gate D concurrent-churn variant designed (dormant) to test race between RI policy-install and VPN connection rekey. Evidence: show-output/23–52. Decisions merged: tank-ri-eu1-enable, tank-ri-eu2-enable, niobe-gate-a/b/c, link-megaport-kv-retrieval, trinity-gate-c-analysis. Next: Jose direction on Gate D concurrent-churn variant.
