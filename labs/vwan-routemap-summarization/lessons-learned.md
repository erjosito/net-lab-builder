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
