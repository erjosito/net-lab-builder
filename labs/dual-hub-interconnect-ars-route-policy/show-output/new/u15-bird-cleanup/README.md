Evidence for **U1.5** (removal of retired Poland BIRD state from `vm-nva1` and `vm-nva2`, finding
`TANK-001`) goes here — see `../../../validation.md#u15--remove-retired-poland-bird-state-from-both-nvas`
and `../../../nva-config/README.md`. **Gated:** nothing may be written here before Jose approves the
U1.5 maintenance window. Empty is the correct state today.

Expected file set at execution time (one NVA at a time, `vm-nva1` first):

```
00-pre-nva1-bird-conf-backup.txt          backup filename + sha256 of backup and live file
00-pre-nva1-bird-protocols-all.txt        ars_hub1_0/1 Established + Since; ars_poland_* in Connect
00-pre-nva1-bird-route-all.txt            10.30.0.0/27 present in master4
00-pre-ars-hub1-peer-nva1-learned.json    10.30.0.0/27 present on IN_0 and IN_1
00-pre-ars-hub1-peer-nva1-advertised.json
00-pre-nva1-nic-effective-routes.json     10.30.0.0/27 VirtualNetworkGateway entry present
00-pre-vpngw-hub1-advertised-to-onprem.json
00-pre-vpngw-onprem-learned-routes.json
00-pre-vpn-connections-status.json
01-nva1-syntax-check.txt                  `bird -p -c` AND `birdc configure check` output
02-nva1-configure-output.txt              `birdc configure` result + timestamp
03-post-nva1-bird-protocols-all.txt       ars_poland_* GONE; ars_hub1_0/1 Since UNCHANGED
03-post-nva1-bird-route-all.txt           10.30.0.0/27 absent; 0.0.0.0/0 + 10.10.0.64/27 present
04-post-ars-hub1-peer-nva1-learned.json   10.30.0.0/27 gone from BOTH instances
04-post-ars-hub1-peer-nva1-advertised.json  byte-identical to 00-pre
05-post-nva1-nic-effective-routes.json    10.30.0.0/27 entry gone
06-post-vpngw-hub1-advertised-to-onprem.json  byte-identical
06-post-vpngw-onprem-learned-routes.json      byte-identical
07-post-vpn-connections-status.json           all Connected, 4 tunnels each
08-ping-nva1-to-nva2-continuous.txt           0% loss spanning the reload
09-timing.txt                                 reload -> withdrawal at 30/60/120/180 s
```

Then the identical set with `nva2`/`ars-hub2`/`vpngw-hub2` substituted, plus:

```
10-diff-summary.md    the ONE prefix that moved, and the byte-identical assertion for everything else
```
