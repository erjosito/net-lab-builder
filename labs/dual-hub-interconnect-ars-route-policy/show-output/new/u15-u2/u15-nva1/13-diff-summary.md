# U1.5 — `vm-nva1` diff summary

**Applied:** `birdc configure` at `2026-08-06T14:12:35Z` ("Reconfiguration in progress").
**Backup:** `/etc/bird/bird.conf.pre-u15.20260806T124403Z`, sha256
`f38ebcce157d7a46e4e3cf8b9a920c6508d1c24bb657e733295e0baced7701f6` (identical to live pre-change
file — verified byte-for-byte backup before any write).
**Blocking gate:** `bird -p -c` exit 0 (no output); `birdc 'configure check "/etc/bird/bird.conf.u15"'`
→ `Configuration OK`. **Both passed before apply.**

## Exactly one prefix moved

| Surface | Pre (`../pre/`) | Post (`./`) | Result |
|---|---|---|---|
| ARS learned, `RouteServiceRole_IN_0` | `{0.0.0.0/0, 10.30.0.0/27}` | `{0.0.0.0/0}` | `10.30.0.0/27` withdrawn |
| ARS learned, `RouteServiceRole_IN_1` | `{0.0.0.0/0, 10.30.0.0/27, 10.40.0.0/16}` | `{0.0.0.0/0, 10.40.0.0/16}` | `10.30.0.0/27` withdrawn, boomerang unchanged |
| ARS advertised | — | — | byte-identical (`Compare-Object` empty diff) |
| `vpngw-hub1` advertised-to-onprem | — | — | byte-identical |
| `vpngw-onprem` learned | — | — | byte-identical |
| VPN connections (all 4) | `Connected` | `Connected` | unchanged; only byte-counters and one `lastConnectionEstablishedUtcTime` (pre-existing tunnel keepalive, not a reset caused by this change) differ, as expected of live counters |
| NVA NIC effective routes | `10.30.0.0/27` present (`VirtualNetworkGateway`) | absent | entry removed |
| `ars_hub1_0` / `ars_hub1_1` BGP `Since` | `07:12:12.272` / `07:12:13.010` | **unchanged** `07:12:12.272` / `07:12:13.010` | **no session flap** |
| `ars_poland_0` / `ars_poland_1` | present, `Connect` | **absent from `show protocols all` entirely** | removed |
| `static1` protocol | `Import withdraws: 0` | `Import withdraws: 1` | exactly one route withdrawn |
| `ars_hub1_0`/`_1` export channel | `Export withdraws: 0` | `Export withdraws: 1` (both) | exactly one route withdrawn per session |
| `vm-nva1 → vm-nva2` ICMP (8 probes) | — | `0% packet loss`, rtt ~28.5–30.9 ms | data plane undisturbed |

**Nothing else moved.** `0.0.0.0/0`, `10.10.0.64/27`, `10.10.0.0/16`, `10.11.0.0/24`,
`10.10.1.0/27`, and the `10.40.0.0/16` boomerang are byte-identical pre/post on every surface
captured. No rollback trigger was met. **U1.5/nva1 = PASS.**
