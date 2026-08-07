# `nva-config/` — authoritative BIRD configuration for `vm-nva1` / `vm-nva2`

**Nothing in this directory has been applied. Nothing here executes.** These files exist to close
the gap recorded in `manifest.md` §Live-state reconciliation and `design.md` §8a(c): *"BIRD configs
are hand-edited on the OS disks and are **not** in version control."* They now are.

The live NVAs are owned by `labs/dual-hub-hubless-region-ars`. This lab may only change them through
an approved Phase-4 unit.

| File | Role |
|---|---|
| `bird-nva1.as-found-2026-08-06.conf` | Faithful transcription of `vm-nva1:/etc/bird/bird.conf` as captured by Tank in U0. **Reference only — do not apply.** |
| `bird-nva2.as-found-2026-08-06.conf` | Same for `vm-nva2`. **Reference only — do not apply.** |
| `bird-nva1.u15-target.conf` | The **exact** file U1.5 would write to `vm-nva1`. Retired-Poland state removed, nothing else. |
| `bird-nva2.u15-target.conf` | Same for `vm-nva2`. |
| `bird-nva1.u3a-doctest.snippet.conf` | The U3a overlay block (temporary RFC 5737 TEST-NET-2 documentation prefix), appended to `bird-nva1.u15-target.conf`. `vm-nva1` only. |

Source evidence: `show-output/new/u0-u1/post-u0/02-nva1-bird-conf.txt`, `02-nva2-bird-conf.txt`.

---

## U1.5 — remove retired Poland BIRD state from both NVAs

**Status: NOT APPROVED, NOT EXECUTED.** Prerequisite for U2 and U3.
Trigger: finding `TANK-001` (`lessons-learned.md`).

### 1. Exact statements removed — from the captured config, not from guesswork

Every item below is quoted from `show-output/new/u0-u1/post-u0/02-nva{1,2}-bird-conf.txt`. Protocol
names are BIRD's actual configured names as they appear in `birdc show protocols`, not invented ones.

**`vm-nva1` (10.10.1.4, AS 65001) — 4 removals**

| # | Exact text removed | Kind | Why |
|---|---|---|---|
| 1 | `route 10.30.0.0/27 via 10.10.1.1;` (inside the unnamed `protocol static`, BIRD-generated name `static1`) | one line | Former Poland RouteServerSubnet. **This is the only removal with a route effect.** |
| 2 | `protocol bgp ars_poland_0 { local 10.10.1.4 as 65001; neighbor 10.30.0.4 as 65515; multihop 4; ipv4 { import all; export filter export_to_poland_ars; }; }` | whole block | Peer `10.30.0.4` deleted 2026-08-05; protocol is stuck in `Connect` (evidence: `01-nva1-bird-protocols-all.txt`). |
| 3 | `protocol bgp ars_poland_1 { … neighbor 10.30.0.5 as 65515; … }` | whole block | Peer `10.30.0.5` deleted 2026-08-05; stuck in `Connect`. |
| 4 | `filter export_to_poland_ars { accept; }` | whole block | Unreferenced once #2 and #3 are gone. BIRD would accept an unreferenced filter, but leaving it re-creates exactly the undocumented-state problem U1.5 exists to fix. |

**`vm-nva2` (10.20.1.4, AS 65002) — 5 removals**

| # | Exact text removed | Kind | Why |
|---|---|---|---|
| 1 | `route 10.30.0.0/27 via 10.20.1.1;` (inside `protocol static` → `static1`) | one line | Former Poland RouteServerSubnet. **Only removal with a route effect.** |
| 2 | `protocol bgp ars_poland_0 { … neighbor 10.30.0.4 as 65515; multihop 4; … }` | whole block | Peer deleted. |
| 3 | `protocol bgp ars_poland_1 { … neighbor 10.30.0.5 as 65515; multihop 4; … }` | whole block | Peer deleted. |
| 4 | `filter export_to_poland_ars { if net = 0.0.0.0/0 then { bgp_path.prepend(65002); bgp_path.prepend(65002); } accept; }` | whole block | Unreferenced once #2/#3 are gone. |
| 5 | `if net ~ [ 10.31.0.0/24, 10.32.0.0/24 ] then { bgp_path.prepend(65002); bgp_path.prepend(65002); }` — the clause **inside** `filter export_to_hub2_ars` | 4 lines | The retired Δ2 `65002-65002-65002` signature. Both prefixes were deleted with Poland. **Provably zero route delta:** no route in `master4` matches either prefix (`03-nva2-bird-route-all.txt`), so BIRD's export re-evaluation emits no update. |

**Explicitly NOT removed, on either NVA:**

- `route 0.0.0.0/0 via 10.10.1.1;` / `via 10.20.1.1;` — `rt-spoke-a` / `rt-spoke-b` UDR targets.
- `route 10.10.0.64/27 via 10.10.1.1;` / `route 10.20.0.64/27 via 10.20.1.1;` — the local
  RouteServerSubnet statics. U0 proved ARS silently rejects a route matching its own
  RouteServerSubnet, so these are already inert; removing them is a *different* change and is
  **out of U1.5 scope**.
- `bgp_path.delete(65515);` in `export_to_hub_ars` / `export_to_hub2_ars` — without it hub ARS
  (AS 65515) discards the routes as an AS-PATH loop.
- `protocol device`, `protocol direct`, `protocol kernel`, `ars_hub1_0/1`, `ars_hub2_0/1`.

### 2. Backup and restore method

Per NVA, before any write, via `az vm run-command invoke … --command-id RunShellScript`:

```
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
sudo cp -p /etc/bird/bird.conf /etc/bird/bird.conf.pre-u15.$STAMP
sudo sha256sum /etc/bird/bird.conf.pre-u15.$STAMP /etc/bird/bird.conf
```

Both the filename and both hashes go into
`show-output/new/u15-bird-cleanup/00-pre-nva{1,2}-bird-conf-backup.txt`.
`-p` preserves mode/ownership so the restore is byte- and metadata-identical. The backup lives on
the NVA's own OS disk **and** the pre-image is already in this repository
(`bird-nva{1,2}.as-found-2026-08-06.conf`) — two independent restore sources.

Restore = `sudo cp -p /etc/bird/bird.conf.pre-u15.$STAMP /etc/bird/bird.conf && sudo birdc configure`.

### 3. Syntax validation BEFORE reload — mandatory, blocking

The new config is written to a **staging path first**, never straight over the live file:

```
sudo install -m 0640 -o root -g bird /dev/stdin /etc/bird/bird.conf.u15 <<'EOF'
…contents of bird-nva1.u15-target.conf…
EOF
sudo bird -p -c /etc/bird/bird.conf.u15          # parse-only; exit 0 and no output == valid
sudo birdc configure check "/etc/bird/bird.conf.u15"   # second, independent check
```

`bird -p` parses and exits without touching the running daemon. `birdc configure check <file>`
asks the **running** daemon to parse the file and reports `Configuration OK` without applying it.
**Both must pass.** Only then:

```
sudo cp -p /etc/bird/bird.conf.u15 /etc/bird/bird.conf
sudo birdc configure
```

If either check fails: delete `/etc/bird/bird.conf.u15`, change nothing, abort U1.5. The live
config was never touched, so there is nothing to roll back.

### 4. Graceful reload vs restart — and why the difference decides the blast radius

| Command | Effect on `ars_hub1_0/1` / `ars_hub2_0/1` | Verdict |
|---|---|---|
| `birdc configure` | Protocols whose configuration is **unchanged** are reconfigured in place and **not restarted**. The BGP sessions stay `Established`; their `Since` timestamps do not move. The `static1` protocol reconfigures in place and withdraws only the removed route. The two `ars_poland_*` protocols are shut down and removed — they are in `Connect`, so no established session is lost. | **REQUIRED** |
| `birdc configure soft` | Same, but filter changes are not re-applied to already-accepted routes. Not wanted: `vm-nva2`'s `export_to_hub2_ars` edit should be re-evaluated (and provably produce nothing). | Not used |
| `systemctl restart bird` / `birdc down` | Full daemon restart. **Every** session is torn down and re-established: `vnet-hub1`/`vnet-hub2` lose their ARS-injected routes and both spokes' `0.0.0.0/0` black-holes for the reset duration. | **FORBIDDEN in U1.5.** Last-resort only, and only after an explicit in-window decision. |

`birdc configure undo` reverts to the immediately previous configuration in one command; it is
valid only until the next `configure`. It is the **fast** rollback; the file restore is the
**durable** one. Both are kept.

### 5. Expected route withdrawals and the proof at each layer

The complete expected delta is **one prefix, withdrawn from two ARS instances per hub, plus two
NIC entries** — nothing else may move.

| Layer | Capture | PASS |
|---|---|---|
| **L3 — NVA RIB** | `birdc show route all` on both NVAs | `10.30.0.0/27` absent from `master4`. `0.0.0.0/0` and `10.10.0.64/27`/`10.20.0.64/27` still present as `static1`. |
| **L3 — NVA protocols** | `birdc show protocols all` on both NVAs | `ars_poland_0`/`ars_poland_1` **absent from the output entirely**. `ars_hub*_0/1` still `Established` with **unchanged `Since` timestamps** (this is the no-flap proof). Export-withdraw counter on each hub channel increments by exactly 1. |
| **L2 — ARS** | `az network routeserver peering list-learned-routes --routeserver ars-hub1 -n peer-nva1` (and `ars-hub2`/`peer-nva2`) | `10.30.0.0/27` gone from `RouteServiceRole_IN_0` **and** `_IN_1`. `0.0.0.0/0` present on both with `asPath "65001"`/`"65002"` unchanged. The `10.40.0.0/16` boomerang on `_IN_1` unchanged. |
| **L2 — ARS advertised** | `list-advertised-routes` for both peerings | **Byte-identical** to the post-U1 baseline (`10.10.0.0/16`, `10.11.0.0/24`, `10.40.0.0/16` / `10.20.0.0/16`, `10.21.0.0/24`, `10.40.0.0/16`). |
| **L1 — hub gateways** | `list-bgp-peer-status` + `list-advertised-routes --peer 10.40.0.4` on `vpngw-hub1`/`vpngw-hub2` | **Byte-identical.** Both already lacked the prefix — this proves non-regression, not removal. |
| **L1 — on-prem** | `vpngw-onprem list-learned-routes` | **Byte-identical** to the post-U1 capture. |
| **L4 — NIC** | `az network nic show-effective-route-table` on both NVA NICs | The `10.30.0.0/27` entry (`nextHopType: VirtualNetworkGateway`) is **gone** on both. Everything else, including the U1 `VNetGlobalPeering` entry for the remote hub `/16`, unchanged. **This is the cleanest single proof.** |
| **L6 — data plane** | Continuous `ping 10.20.1.4` from `vm-nva1` spanning both reloads | 0% loss. |
| **L1 — tunnels** | All four `Microsoft.Network/connections` | All `Connected`, 4 tunnels each, throughout. |
| **L8 — timing** | Reload timestamp → withdrawal observed at ARS, sampled at 30/60/120/180 s | Withdrawal within seconds; the 180 s ARS hold is the ceiling, not the expectation. |

### 6. Rollback triggers and the exact rollback

**Roll back immediately if ANY of these is true.** They are checked at T+30 s, T+60 s, T+120 s, T+180 s.

1. Any `ars_hub1_0`, `ars_hub1_1`, `ars_hub2_0` or `ars_hub2_1` session is not `Established`, **or**
   its `Since` timestamp has moved (an unexpected session reset).
2. `0.0.0.0/0` is absent from either ARS's learned set on either instance at T+60 s.
3. `10.10.0.64/27` / `10.20.0.64/27` is absent from the corresponding `birdc show route`.
4. Any non-zero ICMP loss on `vm-nva1` ↔ `vm-nva2`.
5. Any byte change in `vpngw-hub1`/`vpngw-hub2` advertised-to-on-prem, or in `vpngw-onprem`'s
   learned routes.
6. Any of the four VPN connections leaves `Connected`.
7. `birdc configure` returns anything other than a successful reconfiguration.
8. Any prefix other than `10.30.0.0/27` changes anywhere.

**Exact rollback, in order** (per affected NVA):

```
sudo birdc configure undo                       # fast path, only if this was the last configure
# --- or, always valid: ---
sudo cp -p /etc/bird/bird.conf.pre-u15.$STAMP /etc/bird/bird.conf
sudo birdc configure
sudo birdc show protocols                        # ars_hub*_0/1 Established, ars_poland_* back in Connect
```

Then re-capture the full L1–L4 set and byte-compare against the post-U1 baseline; the rollback is
only complete when `10.30.0.0/27` is present again in the ARS learned set on both instances — i.e.
back to the *known* state, stale prefix and all. Expected duration: **under 2 minutes per NVA.**

Last resort, only if the daemon is wedged and `configure` will not run: `sudo systemctl restart
bird`, accepting a full session reset, then re-verify everything. Record it as a deviation.

### 7. Sequencing note

`vm-nva1` first; verify the complete L1–L4 set; only then `vm-nva2`. Two independent single-NVA
changes, never one two-NVA change — if hub1 behaves unexpectedly, hub2 is still untouched and the
comparison is free.
