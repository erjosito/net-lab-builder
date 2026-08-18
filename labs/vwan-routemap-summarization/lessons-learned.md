# vwan-routemap-summarization — lessons learned

← Back to [README.md](README.md) | Results: [validation.md](validation.md)

## Table of contents

- [StrongSwan swanctl.conf: one setting per line](#strongswan-swanctlconf-requires-one-setting-per-line)
- [Reading BGP AS_PATH in BIRD](#reading-bgp-as_path-in-bird-vs-the-summary-line)
- [az vm run-command script delivery on Windows/PowerShell](#az-vm-run-command-script-delivery-on-windowspowershell)
- [vWAN route-map control-plane operations are slow](#vwan-route-map-control-plane-operations-are-slow)
- [Preflight capacity check](#preflight-capacity-check-paid-off)
- [Phase 3 Gate A: get-outbound-routes API gap](#az-network-vhub-route-map-get-outbound-routes-is-non-functional-in-secured-hub--route-map-config)
- [Phase 3 Gate A: XFRM restore after deallocation](#xfrm-interfaces-are-not-auto-restored-after-vm-deallocationrestart-confirmed-again)
- [Phase 3 Gate A: stuck run-command extension](#nva1-run-command-extension-is-terminally-stuck-persists-across-reboots)
- [Phase 3 Gate B/C: root cause — orthogonal planes](#root-cause-ri-privatetrafic-and-summarize-out-operate-on-orthogonal-planes)
- [Phase 3 Gate B/C: concurrent-churn gap](#the-concurrent-churn-gap-what-was-not-tested)
- [Phase 3 Gate B/C: BGP stability](#bgp-stability-observation)
- [Phase 3: az vm redeploy in swedencentral](#az-vm-redeploy-as-stuck-extension-recovery-swedencentral-caveat)
- [Phase 3: prepend-in + summarize-out coexistence](#prepend-in-and-summarize-out-coexistence)

---

## StrongSwan `swanctl.conf` requires one setting per line

Compressing a section onto a single line — e.g. `local { auth = psk id = 51.12.82.214 }` — makes the
strongSwan parser read `auth`'s value as the whole remainder (`psk id = 51.12.82.214`), producing the
misleading errors:

```
loading connection 'vng0' failed: invalid value for: auth, config discarded
missing secret in 'ike-1', ignored
```

Fix: keep every `key = value` on its own line inside `local {}`, `remote {}`, `children {}` and
`secrets {}`, exactly as in the `erjosito/azure-nvas/ubuntu2404` reference. The many
`plugin '...' failed to load` lines on Ubuntu's strongSwan are cosmetic and are **not** the cause.

## Reading BGP AS_PATH in BIRD vs the summary line

The `birdc show route` **summary line** shows `[AS65520e]` — that is BIRD's *source-AS* tag (the
leftmost inter-hub AS, plus `e` for eBGP), **not** the full path. Looking only at the summary makes it
appear routes carry "only 65520". The full path is under `show route <prefix> all`:

```
BGP.as_path: 65515 65520 65520
```

BIRD prints AS_PATH left-to-right as *nearest → origin*. So `65515` (hub / VPN-gateway ASN) is nearest
and the `65520 65520` double prepend is the inter-hub segment. Confirmed by NVA2's own advertisement
looping back as `65515 65520 65520 65002` (origin 65002 = NVA2, at the rightmost). Nothing has changed
in VWAN behaviour: hub ASN is still 65515 and inter-hub routes still get 65520 prepended twice.

## `az vm run-command` script delivery on Windows/PowerShell

- `--scripts @("$env:TEMP\file.sh")` does **not** read the file — PowerShell passes the literal path
  with backslashes stripped, so the VM reports `C:Users...: not found` and the script never runs.
- Robust fix: base64-encode the script locally and decode on the VM:
  `az vm run-command invoke ... --scripts "echo <b64> | base64 -d > /tmp/cfg.sh && sudo bash /tmp/cfg.sh"`.
  This sidesteps all quoting/escaping between PowerShell, `az.cmd`, and bash.

## VWAN route-map control-plane operations are slow

Each `az network vhub route-map rule add` is an individual hub deployment (~1–2 min). Adding 6 rules to
two hubs runs for many minutes; batch waits accordingly and do not poll aggressively.

## Preflight capacity check paid off

`Standard_B2ts_v2` and VPN gateway capacity were verified in swedencentral and westeurope before
deploy, deliberately avoiding North Europe where the customer hit VPN gateway capacity limits.

---

## Phase 3 Gate A findings (2026-07-30)

### `az network vhub route-map get-outbound-routes` is non-functional in secured hub + route-map config

The `get-outbound-routes` CLI command (from the `virtual-wan` preview extension, WARNING: in preview)
consistently returns **empty output** (exit code 0) for secured vWAN hubs with route-maps, regardless
of whether BGP sessions are active or not. Direct REST calls to both
`/virtualHubs/{hub}/routeMaps/{rm}/getOutboundRoutes` and `/virtualHubs/{hub}/getOutboundRoutes`
return HTTP 404 "No route data was found for this request." in both swedencentral and westeurope.

**Workaround:** Use L2 BIRD RIB (`birdc show route`) on the NVA as the primary route-advertisement
measurement. The BIRD table is the ground truth for what the hub is actually advertising.
This is the authoritative measurement for Gate A/B/C — `get-outbound-routes` cannot be relied upon.

**Note for future:** If Microsoft fixes this API, `get-outbound-routes` would be a cleaner
control-plane measurement. For now, treat it as unavailable for this lab configuration.

### XFRM interfaces are NOT auto-restored after VM deallocation/restart (CONFIRMED AGAIN)

After `az vm start`, XFRM interfaces (xfrm41/xfrm42, type xfrm, if_id 41/42) are absent.
strongSwan swanctl.conf connections are not loaded. IPsec tunnels are not established.
BGP sessions stay down until manual restoration.

**Confirmed working XFRM restore procedure (6-step, tested on nva2 Gate A):**
```
1. ip link add xfrm41 type xfrm dev eth0 if_id 41 && ip link set xfrm41 up
2. ip link add xfrm42 type xfrm dev eth0 if_id 42 && ip link set xfrm42 up
3. ip route add <hub-vpngw-Instance0-bgp-ip>/32 dev xfrm41
   ip route add <hub-vpngw-Instance1-bgp-ip>/32 dev xfrm42
   (hub-eu1: 192.168.2.12 / 192.168.2.13; hub-eu2: 192.168.4.12 / 192.168.4.13)
4. swanctl --load-all
5. swanctl --initiate --child s2s0 --ike vng0 --timeout 30
   swanctl --initiate --child s2s1 --ike vng1 --timeout 30
6. Wait ~75 seconds for BGP convergence
```

Deliver this as a vm_run_command in a single compact line (semicolon-separated) to avoid
the stuck-extension failure mode. Do NOT use complex multiline scripts with 2>/dev/null piped grep.

**Tank action:** Add a systemd oneshot startup service that runs steps 1–5 above automatically.
This eliminates the manual restoration step and prevents NVA-level evidence gaps at every gate.

### nva1 run-command extension is terminally stuck (PERSISTS ACROSS REBOOTS)

The classic RunCommand extension on nva1 is stuck from a previous session's complex multiline script.
After VM restart + deallocation + restart, the extension agent remains locked:
- `az vm run-command invoke` returns Conflict/409 "execution in progress"
- Newer `az vm run-command create/update/delete` hangs indefinitely (>5 min, killed)
- Even delete of the run-command resource hangs

**Resolution:** Tank must rebuild nva1 VM (delete + recreate, or `az vm redeploy`) to clear the
extension agent. Without this, nva1 NVA-level measurements are permanently unavailable.

**Lesson:** Avoid complex multiline scripts (especially with bash-incompatible characters from
PowerShell string interpolation) in `az vm run-command invoke`. Use a single compact semicolon-
separated command string. Test with `echo NVA_TEST` before submitting any complex script.

---

## Phase 3 Gate B/C findings (2026-07-31)

### Root-cause: RI PrivateTraffic and summarize-out operate on orthogonal planes

The missing-summary bug did **NOT** reproduce under sequential stable-state RI enablement. The
reason is architectural: these two mechanisms operate at completely different layers and do not share
an input.

| Layer | Mechanism | Plane |
|-------|-----------|-------|
| RI `_policy_PrivateTraffic` | RFC1918 aggregates (10/8, 172.16/12, 192.168/8) inserted in hub defaultRouteTable → next-hop AzFW | **Data-plane forwarding** |
| `summarize-out` route-map | Evaluated per-connection during BGP outbound advertisement set computation; input = specific /24 prefixes learned via inter-hub BGP from hub-us | **Control-plane BGP advertisement** |

The hub VPN gateway's outbound advertisement set is derived from **learned BGP routes** (hub-us
spoke /24s propagated via inter-hub BGP). RI's defaultRouteTable aggregate is a static route for
forwarding purposes; it does not participate in the per-connection BGP advertisement computation.
hub-us carries no RI, so its spoke /24 specifics propagate individually to hub-eu1/eu2 →
`Contains` matching fires → summaries produced. Enabling RI on the EU hubs does not change this
input chain in steady state.

**Empirical confirmation:** nva1 BGP session timestamps (vpngw0: 07:37:23, vpngw1: 07:37:38) were
identical across Gates A, B, and C — RI provisioning never reset the BGP control plane.

### The concurrent-churn gap (what was NOT tested)

The lab used sequential stable-state RI enablement. The production bug likely requires concurrent
churn: a VPN connection reconvergence event racing with RI provisioning. If the hub recomputes the
per-connection advertisement set while the NVA's BGP session is simultaneously tearing down, the
/24 specifics may be transiently absent from the route-map evaluation input. A cached zero-match
result could persist → missing summary after reconvergence.

Gate D (concurrent-churn experiment) is designed and dormant. See
[design-phase3.md](design-phase3.md#gate-c-result--gate-d-proposal-concurrent-churn).

### BGP stability observation

BGP sessions between the hub VPN gateway and the NVAs were **never reset** across any of the three
Phase 3 gates, even while RI was being provisioned (10–20 min provisioning window). RI enablement
is transparent to the BGP peering in stable state. nva2/vpngw0 had a single brief reconvergence at
Gate B (hub-eu1 RI provision triggered a brief hub-level event); all other sessions were continuous.

### `get-outbound-routes` API gap (confirmed across multiple attempts)

`az network vhub route-map get-outbound-routes` returns empty output (exit code 0) for **both
secured and non-secured** vWAN hubs in swedencentral/westeurope when route-maps are active.
HTTP 404 "No route data was found" from the underlying preview API. This is a Microsoft
CLI/API limitation, not a route-map failure. BIRD RIB on the NVA is the only reliable
measurement available in this lab configuration.

If Microsoft fixes this API, it would be a cleaner control-plane measurement — until then,
treat `get-outbound-routes` as unavailable for secured-hub + route-map configurations.

### `az vm redeploy` as stuck-extension recovery (swedencentral caveat)

`az vm redeploy` successfully cleared nva1's terminally stuck RunCommandLinux extension (which had
persisted across `deallocate`/`start` cycles). However, in swedencentral the redeploy took
~90 minutes (vs typical 10–15 min). Flag for future operations: if swedencentral nva1 gets stuck
again, plan for a 90 min redeploy window; escalate to delete+recreate if it exceeds 2 hours.

### prepend-in and summarize-out coexistence

hub-eu2 carries both `prepend-in` (inbound on cx-onprem2) and `summarize-out` (outbound). These
two route-maps operate on different directions of the VPN connection BGP session and do not
interfere. Gate C confirmed both Succeeded with no cross-contamination. The `prepend-in`
AS-path addition (ASNs 64496/64497/64498) is a hub-internal inbound operation; it does not appear
in nva2's own BIRD RIB (nva2 only sees what hub-eu2 sends back to it, not how hub-eu2 manipulates
inbound routes for inter-hub propagation).

---

# Round 2 lessons (2026-08-18) — mixed-origin attribute inheritance

### `Replace route-prefix` route-maps RE-ORIGINATE the summary with the hub ASN

The single most important finding. A VWAN route-map rule `match routePrefix Contains 10.0.0.0/16 ->
Replace routePrefix 10.0.0.0/16` produces an aggregate that carries the **hub BGP ASN (65515)**, NOT
the contributor's AS-path. **Replace is also the *only* way a route-map can summarize** (no other
aggregation action exists), so a customer summarizing via route-map is necessarily using Replace.
Verified across every case — both contributors, only-ER contributors, b2b on, b2b off: the summary is
always advertised as `65515`, never `12076`. This matches **documented behaviour**: per
[About Route-maps](https://learn.microsoft.com/en-us/azure/virtual-wan/route-maps-about),
*"when using Route-maps to summarize a set of routes, the hub router strips the BGP Community and AS-PATH
attributes from those routes"* (applies to both inbound and outbound).

**Caveat — this does NOT prove Replace is immune (correction to an earlier overclaim).** The AS-PATH
strip governs the **advertised** attributes (the `65515` we saw). Microsoft's bug is about an **internal
origin/branch classification** the aggregate *inherits* during recomputation, which is **not visible** in
that stripped AS-PATH — MS explicitly states a Replace-generated `/16` *can* be "treated as branch-derived
and then dropped". So the advertised AS-PATH is the **wrong observation signal**: it is always `65515`
and can never reveal the branch classification. The only valid signal is **presence vs. absence of the
`/16` at the VPN branch across many recompute cycles**. We saw it present in every sampled cycle, but
that is a **small sample of a nondeterministic** behaviour — "couldn't reproduce" means "didn't hit a
branch-inheriting cycle", not "Replace is safe". The MS mitigation (drop AS-12076 before summarize) is
the correct deterministic fix regardless.

### Two different "Drop" controls in a route-map rule — they are NOT the same

The portal exposes Drop in two places, with different semantics (confirmed in the
[route-maps-about](https://learn.microsoft.com/en-us/azure/virtual-wan/route-maps-about) "Actions" and
"Route modifications" tables):

- **Top-level `Action on matched routes` = Drop** (radio: Drop | Modify). Drops the **entire set**
  chosen by the **match conditions** — and match conditions can be **Route-prefix, Community, or
  AS-Path**. This is the **only** way to drop by AS-Path/Community, and is exactly what the MS mitigation
  and our `mitigation-drop` route-map use (`match asPath Contains 12076 -> Drop`). It is terminal: dropped
  routes receive no further modification.

### Multi-run sampling result — the recompute race did NOT reproduce at 3:1 (2026-08-18)

To test Microsoft's *nondeterministic* root cause (the `/16` aggregate intermittently inheriting an
ER/branch classification and being dropped under b2b-off), a single observation is insufficient — the
mechanism is a race across recompute cycles. Harness `race-sample.ps1` was run **N=20**: each iteration
forces a fresh hub aggregation (detach/reattach `summarize-out` on `cx-nva1`, ~203 s) then densely polls
the onprem branch RIB (30 samples @ 3 s), and captures both ER MSEE route tables for input-consistency.

**Result — negative (no repro):**

| Metric | Value |
|---|---|
| Iterations | 20 / 20 |
| Branch `10.0.0.0/16` present | **600 / 600 dense samples** (`branch_p_min = 1.0` every iteration) |
| Branch drops / anomalies | **0 / 0** |
| Branch AS-PATH / community | `65515` always / none (summarization strips both) |
| MSEE contributor rows | 11, constant every cycle |
| `er-eu2` MSEE `/16` vs branch `/16` | agreed every cycle (no flap); `er-eu1` MSEE never showed the `/16` (only the `/24`s) — expected, `summarize-out` is only on the er2 connection |

At the current **3 ER-learned `/24` : 1 VNet/egress** contributor ratio, pure recompute cycling was
**deterministic in this environment** — the summary was rebuilt and advertised on every fresh aggregation
and never once inherited a branch classification. **"Couldn't reproduce" ≠ "`Replace` is immune"**: the
branch-classification flag is internal and invisible in the (stripped) AS-PATH, so presence/absence of the
`/16` is the only external signal, and it never went absent in 20 tries. **Next step to raise repro odds:**
skew the ratio by expanding the onprem `/24` set (Megaport MCR `ipRoutes` on the er-eu1 VXC) so a
branch-attributed contributor is more likely to "win" aggregation, then re-run the harness. The MS
mitigation (`asPath Contains 12076 -> Drop` before summarize) is the correct deterministic fix regardless.

Evidence: [`show-output/round2/71-race-sampling-summary.md`](show-output/round2/71-race-sampling-summary.md)
· raw [`70-race-sampling-run.txt`](show-output/round2/70-race-sampling-run.txt) /
[`70-race-sampling.csv`](show-output/round2/70-race-sampling.csv).
- **`Modify` -> Route modifications -> Route-prefix, Action = Drop** (vs Replace). Drops only the
  specific **prefix values** listed in the modification, **prefix-only** (cannot match AS-Path/Community),
  and can be **combined** with other modifications on the remaining matched routes in the same rule
  (e.g. drop a couple of prefixes and summarize/prepend the rest).

Takeaway: to drop ER-learned contributors by AS-Path 12076 you must use the **top-level Drop** with an
AS-Path match — the route-modification Drop can't see AS-Path.

### VWAN caches the per-connection outbound advertisement — force a recompute

Changing hub inputs (e.g. deleting a spoke/VNet contributor) does **not** reliably trigger the hub to
recompute a connection's outbound advertisement when the route-map output prefix is unchanged. Symptom:
`birdc show route all` shows the summary with an **unchanged timestamp** even after the input changed,
and `birdc reload in all` (route-refresh) does not help because the hub re-sends the same cached
Adj-RIB-Out. **Fix:** detach the outbound route-map from the connection (PUT routingConfiguration without
`outboundRouteMap`, wait Succeeded), then re-attach it. That forces a clean recompute — confirmed by a
fresh BGP timestamp on the branch. Do this between every case or your results are stale.

### The observation branch MUST be a VPN branch, not a second ER circuit

ER→ER transit in VWAN is **unconditionally blocked** regardless of b2b, so a second ER circuit
(`er-eu2`) can only ever show the VNet-attributed aggregate — it can never exhibit the b2b-governed
branch-derived behaviour. Only an ER→VPN path is gated by branch-to-branch. Deploy an Azure VM NVA
(StrongSwan + BIRD) as a VPN branch and observe there.

### Free on-prem ER prefixes via MCR static routes (no Google Cloud)

Static routes on the Megaport MCR, advertised over the ER private peering, arrive in the hub with
**AS 12076** auto-prepended by the MSEE (path `65515 12076 133937`, community `65517:65517`). That is
exactly the "branch-derived" attribute the repro needs — GCP VPCs add nothing and cost money.

### VWAN route-map create/update is slow; connection route-map only via `az rest`

Route-map create/update LROs can sit in `Updating` for many minutes — poll `provisioningState`, don't
panic-delete. The Azure CLI `az network vpn-gateway connection` has **no** `--outbound-route-map` flag;
set it by PUTting the connection sub-resource with `az rest` (api-version 2023-09-01), adding
`properties.routingConfiguration.outboundRouteMap.id`. Rules JSON for `az network vhub route-map create
--rules @file` must be a JSON **array** (PowerShell `ConvertTo-Json` collapses a single-element array to
an object — write the array literally).

### Testing mechanism correction — single snapshots cannot see a race; sample densely, many times

The customer only saw the summary retired under **certain circumstances**, which points to a
**nondeterministic / race condition** in how the aggregate inherits attributes across recompute cycles.
Our earlier method took **one snapshot per case** and read the **advertised AS-PATH** — both are wrong
for a race:

- **The advertised AS-PATH is the wrong signal.** Summarization strips Community and AS-PATH
  ([docs](https://learn.microsoft.com/en-us/azure/virtual-wan/route-maps-about)), so the branch always
  sees `65515` regardless of the internal branch/VNet classification. The classification that drives the
  branch-to-branch drop is an **internal "hidden flag"** — plausibly the inherited **BGP community**
  (ER-learned contributors arrive tagged `65517:65517`; the VNet contributor does not). Even though that
  community is stripped from the *advertised* summary, the hub's *internal* drop decision can still key
  off it. So the only valid external signal is **presence vs. absence of the `/16` at the observation
  point**, sampled across **many independent recompute events**.

- **Corrected harness** (`files/race-sample.ps1`): for each of N iterations it (1) forces a genuine fresh
  aggregation by **detaching then re-attaching** the outbound route-map on `cx-nva1` (each re-attach
  re-runs the Replace/summarize against the current RIB — a fresh aggregation event, ~200 s/cycle), then
  (2) **densely polls the branch on-box** via `birdc` (30 samples @ 3 s ≈ 90 s) to catch transient
  retirements, capturing presence + AS-PATH + community each sample, and (3) snapshots **both MSEE route
  tables** (`az network express-route list-route-tables`, primary+secondary) to prove the *input*
  contributors stay constant while the *output* is sampled. Any iteration where the `/16` goes absent,
  gains AS 12076, or shows a community is flagged as an anomaly.

- **Two observation points for the same summary.** `hub-eu1` applies `summarize-out` on **two** outbound
  connections: the VPN branch (`cx-nva1`) *and* the ER connection to the `er-eu2` circuit
  (`conn-eu1-er2`). So `er-eu1`'s MSEE sees the specific `/24`s (no route-map on `conn-eu1-er1`) while
  `er-eu2`'s MSEE sees `10.0.0.0/16` — a built-in **cross-point consistency check**: compare the `/16` at
  the VPN branch against the `/16` at the `er-eu2` MSEE each cycle.

- **`az vm run-command` + multi-line bash:** passing a multi-line script via `--scripts` corrupts under
  `dash` (CRLF and newline/positional splitting → `Syntax error ... expecting "done"`). **Fix:**
  base64-encode the script in PowerShell and run `echo <b64> | base64 -d | bash`. Single-line `;`-joined
  scripts also mangle command substitutions — base64 is the only robust path.

### Scaling onprem contributors on the MCR — the export-whitelist gotcha (2026-08-18)

To raise the probability of the mixed-origin race (more ER-learned contributors → higher chance one is
branch-classified and "wins" the aggregate's attributes), the onprem `/24` set advertised via the Megaport
MCR was scaled from **3 to 63** (`10.0.1.0/24 … 10.0.63.0/24`, avoiding the VNet/egress contributor
`10.0.128.0/24`) — a **63 : 1** ER : VNet ratio. Two independent changes are **both** required, or the
new routes silently fail to appear at the Azure MSEE:

1. **MCR static routes (`ipRoutes`)** — gives the MCR a route to advertise. Update path:
   `PUT /v3/product/vxc/{vxcUid}` with body `{"aEndConfig": {"interfaces": [ <full interface> ]}}`. The
   `aEndConfig` is a **full replacement** of the A-End interface, so you must re-send the *entire*
   interface (`ipAddresses`, `vlan`, `ipMtu`, and the complete `bgpConnections` entry) alongside the
   expanded `ipRoutes` — omitting `bgpConnections` would tear down the BGP session. Read the live values
   from `get_product(vxc).resources.csp_connection[0].interfaces[0]` first and reconstruct faithfully.
2. **BGP export prefix-filter-list (`exportWhitelist`)** — the er-eu1 BGP connection carries
   `exportWhitelist: 7589`, a prefix list that **permits only the specific prefixes it lists**. It was
   scoped to the original 3 `/24`s, so any new `ipRoutes` would be installed on the MCR but **filtered out
   of the BGP advertisement** to Azure. Must be expanded in lockstep:
   `PUT /v2/product/mcr2/{mcrUid}/prefixList/{id}` with the full `{description, addressFamily, entries:[{prefix,action}]}`
   (also a full replacement of entries).

**Verification (authoritative = Azure side, not Megaport):** after the update, Megaport's VXC
`bgp_status` field read `0` (session down) for several minutes — but this field is **unreliable** (same
class of issue as the empty looking-glass). The trustworthy check is the Azure MSEE route table:
`az network express-route list-route-tables -g <rg> -n er-eu1 --path primary --peering-name AzurePrivatePeering -o json`
showed **all 63** onprem `/24`s (AS-PATH `133937 ?`), and er-eu2 still showed a single clean `10.0.0.0/16`
with no specifics leaking — i.e. summarization still works unchanged at 63 contributors. Always validate
MCR route changes from Azure, not from the Megaport `bgp_status`/looking-glass.

Helper scripts (session workspace): `mcr-expand-prefixlist.py`, `mcr-expand-iproutes.py`,
`mcr-prefixlists.py`. The scaled sampling harness is `race-sample2.ps1` (adds per-iteration `/16`
presence tracking at **both** the VPN branch and the er-eu2 ER MSEE; anomaly if the summary drops at
either). Empirical results of the scaled run are recorded separately once complete
(`show-output/round2/73-race-sampling-scaled-summary.md`).
