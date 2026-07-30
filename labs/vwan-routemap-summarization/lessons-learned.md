# vwan-routemap-summarization — lessons learned

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
