# U1.5 — `vm-nva2` diff summary

**Applied:** `birdc configure` at `2026-08-06T14:46:26Z` ("Reconfiguration in progress").
**Backup:** `/etc/bird/bird.conf.pre-u15.20260806T143555Z`, sha256
`b9c71ec8a35521a5dc9d392ac28892c44841f88816a87dc09195777268016b3d` (identical to live pre-change
file — verified byte-for-byte backup before any write).
**Blocking gate:** `bird -p -c` exit 0 (no output); `birdc 'configure check "/etc/bird/bird.conf.u15"'`
→ `Configuration OK`. **Both passed before apply.**

## Exactly one prefix moved (plus the dead set-C clause, provably zero route delta)

| Surface | Pre (`../pre/`) | Post (`./`) | Result |
|---|---|---|---|
| ARS learned, `RouteServiceRole_IN_0` | `{0.0.0.0/0, 10.30.0.0/27}` | `{0.0.0.0/0}` | `10.30.0.0/27` withdrawn |
| ARS learned, `RouteServiceRole_IN_1` | `{0.0.0.0/0, 10.30.0.0/27, 10.40.0.0/16}` | `{0.0.0.0/0, 10.40.0.0/16}` | `10.30.0.0/27` withdrawn, boomerang unchanged |
| ARS advertised | — | — | byte-identical (`Compare-Object` empty diff) |
| `vpngw-hub2` advertised-to-onprem | — | — | byte-identical |
| `vpngw-onprem` learned | — | — | byte-identical |
| VPN connections (all 4) | `Connected` | `Connected` | unchanged |
| NVA NIC effective routes | `10.30.0.0/27` present | absent | entry removed |
| `ars_hub2_0` / `ars_hub2_1` BGP `Since` | `07:12:17.496` / `07:12:20.643` | **unchanged** `07:12:17.496` / `07:12:20.643` | **no session flap** |
| `ars_poland_0` / `ars_poland_1` | present, `Connect` | **absent from `show protocols all` entirely** | removed |
| `export_to_hub2_ars` set-C prepend clause (`10.31.0.0/24`,`10.32.0.0/24`) | dead (no matching route in `master4`) | removed from filter text | **provably zero route delta** — `10.20.0.0/16`, `10.21.0.0/24`, `10.40.0.0/16` AS-PATHs/communities unchanged in `show route all` |
| `vm-nva2 → vm-nva1` ICMP (8 probes) | — | `0% packet loss`, rtt ~28.4–54.0 ms (one outlier probe, still 0% loss) | data plane undisturbed |

**Nothing else moved.** `0.0.0.0/0`, `10.20.0.64/27`, `10.20.0.0/16`, `10.21.0.0/24`,
`10.20.1.0/27`, and the `10.40.0.0/16` boomerang are byte-identical pre/post on every surface
captured. No rollback trigger was met. **U1.5/nva2 = PASS.**

**U1.5 overall verdict: PASS on both NVAs.** Sequenced `vm-nva1` first (fully verified) then
`vm-nva2`, per the approved method. `systemctl restart bird` was never invoked on either host.
