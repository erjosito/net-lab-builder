# U3a — RESULT: PASS

Injected `protocol static u3_doc_test { ipv4; route 198.51.100.0/24 blackhole; }` on `vm-nva1`
only (RFC 5737 TEST-NET-2 documentation prefix). Applied 2026-08-06T19:36:21Z via graceful
`birdc configure` after both mandatory syntax gates passed on a staged file
(`/etc/bird/bird.conf.u3a`), never a direct edit of the live file.

## Backup

`/etc/bird/bird.conf.pre-u3a.20260806T184410Z`, SHA-256
`f7605d5f6c7eb703ff07c941abb756874cc30006130c1d46a5f450a14db2b8d5` — identical to the live file's
own hash at backup time (`00-pre-nva1-bird-conf-backup.txt`).

## Syntax gates (both required, both passed, staged file only)

| Gate | Result |
|---|---|
| `bird -p -c /etc/bird/bird.conf.u3a` (standalone parse-only) | exit 0 |
| `birdc configure check "/etc/bird/bird.conf.u3a"` (live daemon parse check) | `Configuration OK` |

**Tooling note:** `birdc`'s non-interactive argv form (`birdc configure check "<file>"` passed
directly as a shell command) reproducibly fails with `syntax error, unexpected '/', expecting END
or TEXT` on this BIRD 2.0.8 build regardless of quoting style — piping the command through stdin
(`echo 'configure check "<file>"' | birdc`) is the reliable form and is what produced the
`Configuration OK` result above. Recorded as a new tooling finding (see `lessons-learned.md`).

## Apply

`echo 'configure' | sudo birdc` at 2026-08-06T19:36:21Z → `Reconfigured`. Never
`systemctl restart bird`.

## Proof (all captured live, this pass)

- **Presence, both ARS instances, correct AS-PATH:** `198.51.100.0/24` learned by `ars-hub1` from
  `peer-nva1` on **both** `RouteServiceRole_IN_0` and `RouteServiceRole_IN_1`, `asPath "65001"`
  (`04-post-ars-hub1-peer-nva1-learned.json`).
- **No session flap:** `ars_hub1_0` `Since 07:12:12.272`, `ars_hub1_1` `Since 07:12:13.010` —
  byte-identical to the B2 baseline; both still `Established`. The new `u3_doc_test` protocol
  appears as a **separate** entry (`up 19:36:21.538`), confirming BIRD reconfigured in place
  without touching the existing BGP sessions (`03-post-nva1-bird-protocols-all.txt`).
- **Hub2 isolation:** `198.51.100.0/24` absent from `ars-hub2`'s learned set from `peer-nva2`
  (`04b-post-ars-hub2-peer-nva2-learned.json`) — `vm-nva2` was never touched.
- **Containment — gateways/on-prem:** absent from `vpngw-hub1` and `vpngw-hub2`'s
  advertised-to-on-prem sets (both `{"value": []}`) and from `vpngw-onprem`'s learned routes
  (`05-post-vpngw-hub{1,2}-advertised-to-onprem.json`, `05-post-vpngw-onprem-learned-routes.json`).
- **Accepted side effect:** present in `vm-nva1`'s own NIC effective routes, `nextHopIpAddress
  10.10.1.4` (`06-post-nva1-nic-effective-routes.json`) — expected, not a leak; matches the
  `10.30.0.0/27` precedent from U0/U1.5.
- **Spoke-a propagation:** unverified by design — `vm-hub1-ep` stays deallocated
  (`08-containment-note.md`).
- **VPN health:** all 4 `Microsoft.Network/connections` `connectionStatus: Connected`
  (`07-post-vpn-connections-status.json`).
- **Data plane:** `vm-nva1 → vm-nva2` (10.20.1.4) 8/8 received, 0% loss
  (`09-ping-nva1-to-nva2-post-u3a.txt`).

## Verdict

**U3a PASS.** The harmless documentation prefix is BGP-visible at both `ars-hub1` instances with
the expected AS-PATH, contained away from both hub gateways and on-prem, causes no BGP session
reset, and leaves the data plane and all 4 VPN tunnels unaffected. This is the required target for
U3b's route-map rule.
