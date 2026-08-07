Evidence for **U3a** (injection of the temporary RFC 5737 TEST-NET-2 documentation prefix
`198.51.100.0/24` on `vm-nva1` only) goes here — see
`../../../validation.md#t3--dynamic-inter-hub-nva-bgptunnel-variant` §T2b/U3 and
`../../../nva-config/bird-nva1.u3a-doctest.snippet.conf`. **Gated:** runs only after U1.5 and U2
have both PASSED, and only with Jose's explicit approval. Empty is the correct state today.

Expected file set:

```
00-pre-nva1-bird-conf-backup.txt              backup filename + sha256 (STAMP = pre-u3a)
00-pre-ars-hub1-peer-nva1-learned.json        the post-U2 baseline this is diffed against
00-pre-vpngw-hub1-advertised-to-onprem.json
00-pre-vpngw-onprem-learned-routes.json
01-nva1-syntax-check.txt                      `bird -p -c` AND `birdc configure check`
02-nva1-configure-output.txt                  `birdc configure` result + timestamp
03-post-nva1-bird-route-all.txt               198.51.100.0/24 present as u3_doc_test (blackhole)
03-post-nva1-bird-protocols-all.txt           ars_hub1_0/1 Since UNCHANGED (no flap)
04-post-ars-hub1-peer-nva1-learned.json       198.51.100.0/24, asPath "65001", BOTH instances
05-post-vpngw-hub1-advertised-to-onprem.json  198.51.100.0/24 MUST NOT appear (containment)
05-post-vpngw-hub2-advertised-to-onprem.json  198.51.100.0/24 MUST NOT appear
05-post-vpngw-onprem-learned-routes.json      198.51.100.0/24 MUST NOT appear
06-post-nva1-nic-effective-routes.json        expected to gain the prefix (accepted side effect)
07-post-vpn-connections-status.json           all Connected
08-containment-note.md                        spoke-a NIC propagation is UNVERIFIED BY DESIGN
                                              (vm-hub1-ep stays deallocated) — record, do not claim
```
