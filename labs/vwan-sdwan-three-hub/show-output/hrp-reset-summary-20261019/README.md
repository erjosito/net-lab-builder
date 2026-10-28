## B1 after resetting all six Azure-facing BGP sessions

This follow-up tests the operational hypothesis that B1 only needs a BGP reset after an HRP update. It does **not** restart the BIRD daemon, mesh BGP sessions, strongSwan or WireGuard. Each router runs two Azure-facing BIRD protocols, `azure_0` and `azure_1`: six adjacencies in total across EU, US and Japan.

Each of four independent controls starts from the same original BIRD policy: three extra nonlocal EU/US prepends and no extra Japan prepends. All hub branch flags are enabled. A three-spoke UDR on the Japan workload subnet is applied consistently, so the previously identified workload-steering omission does not confound these captures.

1. Apply ASPath HRP to every hub and capture the remote Japan winner as the initial history.
2. Apply ExpressRoute or VPN HRP and capture the result **before** resetting BGP.
3. Disable both Azure-facing protocols on all three routers. Confirm that all six are down and that every DC-prefix route has withdrawn from the hub firewall views.
4. Re-enable all six, deliberately testing two orders: **Japan first**, then EU/US; or **EU/US first**, then Japan. Each site's two sessions must establish before the next site is enabled. Capture the first-advertiser route state too.
5. Capture full firewall/NVA tables, two stable firewall samples at least 120 seconds apart, and the 24 sourced DC/Azure TCP/ICMP directions with router packet observations.

The intermediate ASPath-seed and HRP-only captures collect routes, not traffic. The 24/24 post-reset measurements therefore establish the combined corrected-workload B1 state; they do not isolate the reset as the cause of every improvement over the older forwarding captures.

The ordering variation matters: a nominally simultaneous restart cannot guarantee simultaneous BGP establishment or route arrival. An operational caveat should not silently depend on the customer path always arriving before the VPN/interhub alternative.

The first VPN/ Japan-first attempt reached the restore reserve before its BGP reset, and the restore/deallocation CLI calls timed out. It is preserved as an unsuccessful control, not counted as a routing result. A separate recovery confirmed that the original hub policies, subnet association, temporary-table absence and ten-VM power inventory were restored before the VPN controls were retried under a fresh baseline. The retry wrapper temporarily prevents host sleep while running; no Azure routing or guest policy is changed by that host-side safeguard.

| HRP / re-enable order | Before reset: EU / US Japan paths | After: EU Japan winner | After: US Japan winner | TCP / 24 | ICMP / 24 |
|---|---|---|---|---|---|
| [ExpressRoute, japan-first](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-expressroute-japan-first-20261019/after-reset/scenario-result.json) | `65520-65520-65013` / `65520-65520-65013` | `65011-65011-65011-65011-65013` (HubBgpConnection) | `65012-65012-65012-65012-65013` (HubBgpConnection) | 24 | 24 |
| [ExpressRoute, nva-first](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-expressroute-nva-first-20261019/after-reset/scenario-result.json) | `65011-65011-65011-65011-65013` / `65012-65012-65012-65012-65013` | `65011-65011-65011-65011-65013` (HubBgpConnection) | `65012-65012-65012-65012-65013` (HubBgpConnection) | 24 | 24 |
| [VpnGateway, japan-first](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-vpngateway-japan-first-retry-20261019/after-reset/scenario-result.json) | `65520-65520-65013` / `65520-65520-65013` | `65011-65011-65011-65011-65013` (HubBgpConnection) | `65012-65012-65012-65012-65013` (HubBgpConnection) | 24 | 24 |
| [VpnGateway, nva-first](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-vpngateway-nva-first-20261019/after-reset/scenario-result.json) | `65011-65011-65011-65011-65013` / `65012-65012-65012-65012-65013` | `65011-65011-65011-65011-65013` (HubBgpConnection) | `65012-65012-65012-65012-65013` (HubBgpConnection) | 24 | 24 |

**ExpressRoute:** both tested re-enable orders produced the expected local Japan winner and identical stable DC-prefix firewall winners. For these two lab trials, the HRP change followed by a complete Azure-facing BGP reset was reproducible. This supports an operational reset caveat for the tested conditions, not a universal Azure guarantee. Both corrected-workload captures pass all 24 TCP and ICMP directions.

**VpnGateway:** both tested re-enable orders produced the expected local Japan winner and identical stable DC-prefix firewall winners. For these two lab trials, the HRP change followed by a complete Azure-facing BGP reset was reproducible. This supports an operational reset caveat for the tested conditions, not a universal Azure guarantee. Both corrected-workload captures pass all 24 TCP and ICMP directions.

This remains a small controlled lab sample, not proof for every future failure/reconvergence sequence. A routing-selection limitation and any remaining forwarding failures are separate findings. **BIRD normally reloads configuration through `birdc configure`; changing `bird.conf` does not inherently require restarting its daemon.** Some configuration changes can restart affected protocols, whereas an export-policy update may be applied without re-establishing a session.

The source report below renders complete matched EU/JP firewall tables and EU/JP/CN NVA selections for every reset order. Full BIRD sources, all three hubs, all four NVAs, intermediate withdrawal/first-advertiser evidence and the packet observations are linked.

**ExpressRoute, japan-first:** [HRP-only, before reset](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-expressroute-japan-first-20261019/HRP-only/scenario-result.json); [after reset](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-expressroute-japan-first-20261019/after-reset/scenario-result.json); [transport invariants](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-expressroute-japan-first-20261019/bgp-reset/transport-invariants.json); [first advertiser](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-expressroute-japan-first-20261019/bgp-reset/first-advertiser-winners.json); [control and exact restore](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-expressroute-japan-first-20261019/reset-verdict.json).

**ExpressRoute, nva-first:** [HRP-only, before reset](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-expressroute-nva-first-20261019/HRP-only/scenario-result.json); [after reset](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-expressroute-nva-first-20261019/after-reset/scenario-result.json); [transport invariants](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-expressroute-nva-first-20261019/bgp-reset/transport-invariants.json); [first advertiser](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-expressroute-nva-first-20261019/bgp-reset/first-advertiser-winners.json); [control and exact restore](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-expressroute-nva-first-20261019/reset-verdict.json).

**VpnGateway, japan-first:** [HRP-only, before reset](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-vpngateway-japan-first-retry-20261019/HRP-only/scenario-result.json); [after reset](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-vpngateway-japan-first-retry-20261019/after-reset/scenario-result.json); [transport invariants](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-vpngateway-japan-first-retry-20261019/bgp-reset/transport-invariants.json); [first advertiser](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-vpngateway-japan-first-retry-20261019/bgp-reset/first-advertiser-winners.json); [control and exact restore](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-vpngateway-japan-first-retry-20261019/reset-verdict.json).

**VpnGateway, nva-first:** [HRP-only, before reset](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-vpngateway-nva-first-20261019/HRP-only/scenario-result.json); [after reset](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-vpngateway-nva-first-20261019/after-reset/scenario-result.json); [transport invariants](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-vpngateway-nva-first-20261019/bgp-reset/transport-invariants.json); [first advertiser](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-vpngateway-nva-first-20261019/bgp-reset/first-advertiser-winners.json); [control and exact restore](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-vpngateway-nva-first-20261019/reset-verdict.json).

Original BIRD bytes/metadata, mixed hub preferences/branch flags and stable firewall winners were restored after each variant. Every temporary workload route table was deleted and its subnet association restored. Independent original-state verification and exact restoration of the ten originally deallocated VMs completed afterward. IPsec configuration hashes, BIRD PIDs and mesh establishment times are unchanged across each reset; both IKE SAs are established at the checks. The IPsec file hashes were compared privately and are redacted from the public captures, including encoded guest output. No IPsec restart is issued; normal timed rekeys are not represented as tunnel restarts.

The first independent original-state check had the same BIRD configuration, hub settings, subnet association, stable firewall winners and TCP count as the baseline, but one formerly passing ICMP direction (`10.30.0.10` to `10.110.0.10`) lost both probes: 13/24 rather than 14/24. That discrepancy is retained, not relabeled. A single bounded independent retry checks the original state again; the four successful corrected-workload B1 captures are separate measurements.

[Independent closure retry](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-independent-retry-20261019/baseline-verdict.json); [first independent capture with ICMP discrepancy](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-independent-20261019/independent-verification/scenario-result.json); [original VM power restoration](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-final-verify-power-stop-20261019/power-verdict.json); [unsuccessful VPN attempt](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-vpngateway-japan-first-20261019/reset-verdict.json); [separate timeout recovery](https://github.com/erjosito/net-lab-builder/blob/main/labs/vwan-sdwan-three-hub/show-output/hrp-reset-timeout-recovery-20261019/recovery-verdict.json).

## Complete matched capture: ExpressRoute, japan-first

### EU firewall

| Prefix | ASPath | NextHopType |
|---|---|---|
| `10.210.0.0/24` | empty | Virtual Network Connection |
| `10.10.0.0/24` | empty | Virtual Network Connection |
| `10.130.0.0/24` | `65011-65011-65011-65011-65013` | HubBgpConnection |
| `10.120.0.0/24` | `65011-65011-65011-65011-65012` | HubBgpConnection |
| `10.140.0.0/24` | `65011-65011-65011-65011-65014` | HubBgpConnection |
| `10.110.0.0/24` | `65011` | HubBgpConnection |
| `10.30.0.0/24` | `65520-65520` | Remote Hub |
| `10.220.0.0/24` | `65520-65520` | Remote Hub |
| `10.20.0.0/24` | `65520-65520` | Remote Hub |
| `0.0.0.0/0` | empty | Internet |

### JP firewall

| Prefix | ASPath | NextHopType |
|---|---|---|
| `10.120.0.0/24` | `65013-65012` | VPN_S2S_Gateway |
| `10.130.0.0/24` | `65013` | VPN_S2S_Gateway |
| `10.140.0.0/24` | `65013-65014` | VPN_S2S_Gateway |
| `10.110.0.0/24` | `65013-65011` | VPN_S2S_Gateway |
| `10.30.0.0/24` | empty | Virtual Network Connection |
| `10.10.0.0/24` | `65520-65520` | Remote Hub |
| `10.220.0.0/24` | `65520-65520` | Remote Hub |
| `10.20.0.0/24` | `65520-65520` | Remote Hub |
| `10.210.0.0/24` | `65520-65520` | Remote Hub |
| `0.0.0.0/0` | empty | Internet |

### EU selected NVA routes

| Prefix | Protocol | BGP next hop | BIRD resolution | ASPath | LP | Marker |
|---|---|---|---|---|---|---|
| `10.110.0.0/24` | `own_dc` | `n/a` | `via 10.210.0.1 on eth0` | `n/a` | n/a | `*` |
| `10.120.0.0/24` | `mesh_us` | `172.31.0.2` | `dev wgeuus` | `65012` | 100 | `*` |
| `10.130.0.0/24` | `mesh_jp` | `172.31.0.6` | `dev wgeujp` | `65013` | 100 | `*` |
| `10.140.0.0/24` | `mesh_cn` | `172.31.0.10` | `dev wgeucn` | `65014` | 100 | `*` |
| `10.10.0.0/24` | `azure_0` | `10.210.0.1` | `via 10.210.0.1 on eth0` | `65515` | 300 | `*` |
| `10.20.0.0/24` | `mesh_us` | `172.31.0.2` | `dev wgeuus` | `65012 65515` | 300 | `*` |
| `10.30.0.0/24` | `mesh_jp` | `172.31.0.6` | `dev wgeujp` | `65013 65515` | 300 | `*` |

### JP selected NVA routes

| Prefix | Protocol | BGP next hop | BIRD resolution | ASPath | LP | Marker |
|---|---|---|---|---|---|---|
| `10.110.0.0/24` | `mesh_eu` | `172.31.0.5` | `dev wgeujp` | `65011` | 100 | `*` |
| `10.120.0.0/24` | `mesh_us` | `172.31.0.13` | `dev wgusjp` | `65012` | 100 | `*` |
| `10.130.0.0/24` | `own_dc` | `n/a` | `dev eth0` | `n/a` | n/a | `*` |
| `10.140.0.0/24` | `mesh_cn` | `172.31.0.22` | `dev wgjpcn` | `65014` | 100 | `*` |
| `10.10.0.0/24` | `mesh_eu` | `172.31.0.5` | `dev wgeujp` | `65011 65515` | 300 | `*` |
| `10.20.0.0/24` | `mesh_us` | `172.31.0.13` | `dev wgusjp` | `65012 65515` | 300 | `*` |
| `10.30.0.0/24` | `azure_1` | `169.254.21.6` | `via 169.254.21.6 on xfrm42` | `65515` | 300 | `!` |

### CN selected NVA routes

| Prefix | Protocol | BGP next hop | BIRD resolution | ASPath | LP | Marker |
|---|---|---|---|---|---|---|
| `10.110.0.0/24` | `mesh_eu` | `172.31.0.9` | `dev wgeucn` | `65011` | 100 | `*` |
| `10.120.0.0/24` | `mesh_us` | `172.31.0.17` | `dev wguscn` | `65012` | 100 | `*` |
| `10.130.0.0/24` | `mesh_jp` | `172.31.0.21` | `dev wgjpcn` | `65013` | 100 | `*` |
| `10.140.0.0/24` | `own_dc` | `n/a` | `dev eth0` | `n/a` | n/a | `*` |
| `10.10.0.0/24` | `mesh_eu` | `172.31.0.9` | `dev wgeucn` | `65011 65515` | 300 | `*` |
| `10.20.0.0/24` | `mesh_us` | `172.31.0.17` | `dev wguscn` | `65012 65515` | 300 | `*` |
| `10.30.0.0/24` | `mesh_jp` | `172.31.0.21` | `dev wgjpcn` | `65013 65515` | 300 | `*` |

### Scoped workload traffic

**DC -> Azure spoke**

| DC / Azure spoke | spoke-eu | spoke-us | spoke-jp |
|---|---|---|---|
| dc-eu | P/P | P/P | P/P |
| dc-us | P/P | P/P | P/P |
| dc-jp | P/P | P/P | P/P |
| cn | P/P | P/P | P/P |

**Azure spoke -> DC**

| DC / Azure spoke | spoke-eu | spoke-us | spoke-jp |
|---|---|---|---|
| dc-eu | P/P | P/P | P/P |
| dc-us | P/P | P/P | P/P |
| dc-jp | P/P | P/P | P/P |
| cn | P/P | P/P | P/P |

## Complete matched capture: ExpressRoute, nva-first

### EU firewall

| Prefix | ASPath | NextHopType |
|---|---|---|
| `10.210.0.0/24` | empty | Virtual Network Connection |
| `10.10.0.0/24` | empty | Virtual Network Connection |
| `10.110.0.0/24` | `65011` | HubBgpConnection |
| `10.140.0.0/24` | `65011-65011-65011-65011-65014` | HubBgpConnection |
| `10.130.0.0/24` | `65011-65011-65011-65011-65013` | HubBgpConnection |
| `10.120.0.0/24` | `65011-65011-65011-65011-65012` | HubBgpConnection |
| `10.30.0.0/24` | `65520-65520` | Remote Hub |
| `10.220.0.0/24` | `65520-65520` | Remote Hub |
| `10.20.0.0/24` | `65520-65520` | Remote Hub |
| `0.0.0.0/0` | empty | Internet |

### JP firewall

| Prefix | ASPath | NextHopType |
|---|---|---|
| `10.30.0.0/24` | empty | Virtual Network Connection |
| `10.130.0.0/24` | `65013` | VPN_S2S_Gateway |
| `10.10.0.0/24` | `65520-65520` | Remote Hub |
| `10.220.0.0/24` | `65520-65520` | Remote Hub |
| `10.120.0.0/24` | `65013-65012` | VPN_S2S_Gateway |
| `10.140.0.0/24` | `65013-65014` | VPN_S2S_Gateway |
| `10.20.0.0/24` | `65520-65520` | Remote Hub |
| `10.210.0.0/24` | `65520-65520` | Remote Hub |
| `10.110.0.0/24` | `65013-65011` | VPN_S2S_Gateway |
| `0.0.0.0/0` | empty | Internet |

### EU selected NVA routes

| Prefix | Protocol | BGP next hop | BIRD resolution | ASPath | LP | Marker |
|---|---|---|---|---|---|---|
| `10.110.0.0/24` | `own_dc` | `n/a` | `via 10.210.0.1 on eth0` | `n/a` | n/a | `*` |
| `10.120.0.0/24` | `mesh_us` | `172.31.0.2` | `dev wgeuus` | `65012` | 100 | `*` |
| `10.130.0.0/24` | `mesh_jp` | `172.31.0.6` | `dev wgeujp` | `65013` | 100 | `*` |
| `10.140.0.0/24` | `mesh_cn` | `172.31.0.10` | `dev wgeucn` | `65014` | 100 | `*` |
| `10.10.0.0/24` | `azure_0` | `10.210.0.1` | `via 10.210.0.1 on eth0` | `65515` | 300 | `*` |
| `10.20.0.0/24` | `mesh_us` | `172.31.0.2` | `dev wgeuus` | `65012 65515` | 300 | `*` |
| `10.30.0.0/24` | `mesh_jp` | `172.31.0.6` | `dev wgeujp` | `65013 65515` | 300 | `*` |

### JP selected NVA routes

| Prefix | Protocol | BGP next hop | BIRD resolution | ASPath | LP | Marker |
|---|---|---|---|---|---|---|
| `10.110.0.0/24` | `mesh_eu` | `172.31.0.5` | `dev wgeujp` | `65011` | 100 | `*` |
| `10.120.0.0/24` | `mesh_us` | `172.31.0.13` | `dev wgusjp` | `65012` | 100 | `*` |
| `10.130.0.0/24` | `own_dc` | `n/a` | `dev eth0` | `n/a` | n/a | `*` |
| `10.140.0.0/24` | `mesh_cn` | `172.31.0.22` | `dev wgjpcn` | `65014` | 100 | `*` |
| `10.10.0.0/24` | `mesh_eu` | `172.31.0.5` | `dev wgeujp` | `65011 65515` | 300 | `*` |
| `10.20.0.0/24` | `mesh_us` | `172.31.0.13` | `dev wgusjp` | `65012 65515` | 300 | `*` |
| `10.30.0.0/24` | `azure_1` | `169.254.21.6` | `via 169.254.21.6 on xfrm42` | `65515` | 300 | `!` |

### CN selected NVA routes

| Prefix | Protocol | BGP next hop | BIRD resolution | ASPath | LP | Marker |
|---|---|---|---|---|---|---|
| `10.110.0.0/24` | `mesh_eu` | `172.31.0.9` | `dev wgeucn` | `65011` | 100 | `*` |
| `10.120.0.0/24` | `mesh_us` | `172.31.0.17` | `dev wguscn` | `65012` | 100 | `*` |
| `10.130.0.0/24` | `mesh_jp` | `172.31.0.21` | `dev wgjpcn` | `65013` | 100 | `*` |
| `10.140.0.0/24` | `own_dc` | `n/a` | `dev eth0` | `n/a` | n/a | `*` |
| `10.10.0.0/24` | `mesh_eu` | `172.31.0.9` | `dev wgeucn` | `65011 65515` | 300 | `*` |
| `10.20.0.0/24` | `mesh_us` | `172.31.0.17` | `dev wguscn` | `65012 65515` | 300 | `*` |
| `10.30.0.0/24` | `mesh_jp` | `172.31.0.21` | `dev wgjpcn` | `65013 65515` | 300 | `*` |

### Scoped workload traffic

**DC -> Azure spoke**

| DC / Azure spoke | spoke-eu | spoke-us | spoke-jp |
|---|---|---|---|
| dc-eu | P/P | P/P | P/P |
| dc-us | P/P | P/P | P/P |
| dc-jp | P/P | P/P | P/P |
| cn | P/P | P/P | P/P |

**Azure spoke -> DC**

| DC / Azure spoke | spoke-eu | spoke-us | spoke-jp |
|---|---|---|---|
| dc-eu | P/P | P/P | P/P |
| dc-us | P/P | P/P | P/P |
| dc-jp | P/P | P/P | P/P |
| cn | P/P | P/P | P/P |

## Complete matched capture: VpnGateway, japan-first

### EU firewall

| Prefix | ASPath | NextHopType |
|---|---|---|
| `10.210.0.0/24` | empty | Virtual Network Connection |
| `10.10.0.0/24` | empty | Virtual Network Connection |
| `10.130.0.0/24` | `65011-65011-65011-65011-65013` | HubBgpConnection |
| `10.120.0.0/24` | `65011-65011-65011-65011-65012` | HubBgpConnection |
| `10.140.0.0/24` | `65011-65011-65011-65011-65014` | HubBgpConnection |
| `10.110.0.0/24` | `65011` | HubBgpConnection |
| `10.30.0.0/24` | `65520-65520` | Remote Hub |
| `10.220.0.0/24` | `65520-65520` | Remote Hub |
| `10.20.0.0/24` | `65520-65520` | Remote Hub |
| `0.0.0.0/0` | empty | Internet |

### JP firewall

| Prefix | ASPath | NextHopType |
|---|---|---|
| `10.120.0.0/24` | `65013-65012` | VPN_S2S_Gateway |
| `10.130.0.0/24` | `65013` | VPN_S2S_Gateway |
| `10.140.0.0/24` | `65013-65014` | VPN_S2S_Gateway |
| `10.110.0.0/24` | `65013-65011` | VPN_S2S_Gateway |
| `10.30.0.0/24` | empty | Virtual Network Connection |
| `10.10.0.0/24` | `65520-65520` | Remote Hub |
| `10.220.0.0/24` | `65520-65520` | Remote Hub |
| `10.20.0.0/24` | `65520-65520` | Remote Hub |
| `10.210.0.0/24` | `65520-65520` | Remote Hub |
| `0.0.0.0/0` | empty | Internet |

### EU selected NVA routes

| Prefix | Protocol | BGP next hop | BIRD resolution | ASPath | LP | Marker |
|---|---|---|---|---|---|---|
| `10.110.0.0/24` | `own_dc` | `n/a` | `via 10.210.0.1 on eth0` | `n/a` | n/a | `*` |
| `10.120.0.0/24` | `mesh_us` | `172.31.0.2` | `dev wgeuus` | `65012` | 100 | `*` |
| `10.130.0.0/24` | `mesh_jp` | `172.31.0.6` | `dev wgeujp` | `65013` | 100 | `*` |
| `10.140.0.0/24` | `mesh_cn` | `172.31.0.10` | `dev wgeucn` | `65014` | 100 | `*` |
| `10.10.0.0/24` | `azure_0` | `10.210.0.1` | `via 10.210.0.1 on eth0` | `65515` | 300 | `*` |
| `10.20.0.0/24` | `mesh_us` | `172.31.0.2` | `dev wgeuus` | `65012 65515` | 300 | `*` |
| `10.30.0.0/24` | `mesh_jp` | `172.31.0.6` | `dev wgeujp` | `65013 65515` | 300 | `*` |

### JP selected NVA routes

| Prefix | Protocol | BGP next hop | BIRD resolution | ASPath | LP | Marker |
|---|---|---|---|---|---|---|
| `10.110.0.0/24` | `mesh_eu` | `172.31.0.5` | `dev wgeujp` | `65011` | 100 | `*` |
| `10.120.0.0/24` | `mesh_us` | `172.31.0.13` | `dev wgusjp` | `65012` | 100 | `*` |
| `10.130.0.0/24` | `own_dc` | `n/a` | `dev eth0` | `n/a` | n/a | `*` |
| `10.140.0.0/24` | `mesh_cn` | `172.31.0.22` | `dev wgjpcn` | `65014` | 100 | `*` |
| `10.10.0.0/24` | `mesh_eu` | `172.31.0.5` | `dev wgeujp` | `65011 65515` | 300 | `*` |
| `10.20.0.0/24` | `mesh_us` | `172.31.0.13` | `dev wgusjp` | `65012 65515` | 300 | `*` |
| `10.30.0.0/24` | `azure_1` | `169.254.21.6` | `via 169.254.21.6 on xfrm42` | `65515` | 300 | `!` |

### CN selected NVA routes

| Prefix | Protocol | BGP next hop | BIRD resolution | ASPath | LP | Marker |
|---|---|---|---|---|---|---|
| `10.110.0.0/24` | `mesh_eu` | `172.31.0.9` | `dev wgeucn` | `65011` | 100 | `*` |
| `10.120.0.0/24` | `mesh_us` | `172.31.0.17` | `dev wguscn` | `65012` | 100 | `*` |
| `10.130.0.0/24` | `mesh_jp` | `172.31.0.21` | `dev wgjpcn` | `65013` | 100 | `*` |
| `10.140.0.0/24` | `own_dc` | `n/a` | `dev eth0` | `n/a` | n/a | `*` |
| `10.10.0.0/24` | `mesh_eu` | `172.31.0.9` | `dev wgeucn` | `65011 65515` | 300 | `*` |
| `10.20.0.0/24` | `mesh_us` | `172.31.0.17` | `dev wguscn` | `65012 65515` | 300 | `*` |
| `10.30.0.0/24` | `mesh_jp` | `172.31.0.21` | `dev wgjpcn` | `65013 65515` | 300 | `*` |

### Scoped workload traffic

**DC -> Azure spoke**

| DC / Azure spoke | spoke-eu | spoke-us | spoke-jp |
|---|---|---|---|
| dc-eu | P/P | P/P | P/P |
| dc-us | P/P | P/P | P/P |
| dc-jp | P/P | P/P | P/P |
| cn | P/P | P/P | P/P |

**Azure spoke -> DC**

| DC / Azure spoke | spoke-eu | spoke-us | spoke-jp |
|---|---|---|---|
| dc-eu | P/P | P/P | P/P |
| dc-us | P/P | P/P | P/P |
| dc-jp | P/P | P/P | P/P |
| cn | P/P | P/P | P/P |

## Complete matched capture: VpnGateway, nva-first

### EU firewall

| Prefix | ASPath | NextHopType |
|---|---|---|
| `10.210.0.0/24` | empty | Virtual Network Connection |
| `10.10.0.0/24` | empty | Virtual Network Connection |
| `10.110.0.0/24` | `65011` | HubBgpConnection |
| `10.140.0.0/24` | `65011-65011-65011-65011-65014` | HubBgpConnection |
| `10.130.0.0/24` | `65011-65011-65011-65011-65013` | HubBgpConnection |
| `10.120.0.0/24` | `65011-65011-65011-65011-65012` | HubBgpConnection |
| `10.30.0.0/24` | `65520-65520` | Remote Hub |
| `10.220.0.0/24` | `65520-65520` | Remote Hub |
| `10.20.0.0/24` | `65520-65520` | Remote Hub |
| `0.0.0.0/0` | empty | Internet |

### JP firewall

| Prefix | ASPath | NextHopType |
|---|---|---|
| `10.30.0.0/24` | empty | Virtual Network Connection |
| `10.130.0.0/24` | `65013` | VPN_S2S_Gateway |
| `10.10.0.0/24` | `65520-65520` | Remote Hub |
| `10.220.0.0/24` | `65520-65520` | Remote Hub |
| `10.120.0.0/24` | `65013-65012` | VPN_S2S_Gateway |
| `10.140.0.0/24` | `65013-65014` | VPN_S2S_Gateway |
| `10.20.0.0/24` | `65520-65520` | Remote Hub |
| `10.210.0.0/24` | `65520-65520` | Remote Hub |
| `10.110.0.0/24` | `65013-65011` | VPN_S2S_Gateway |
| `0.0.0.0/0` | empty | Internet |

### EU selected NVA routes

| Prefix | Protocol | BGP next hop | BIRD resolution | ASPath | LP | Marker |
|---|---|---|---|---|---|---|
| `10.110.0.0/24` | `own_dc` | `n/a` | `via 10.210.0.1 on eth0` | `n/a` | n/a | `*` |
| `10.120.0.0/24` | `mesh_us` | `172.31.0.2` | `dev wgeuus` | `65012` | 100 | `*` |
| `10.130.0.0/24` | `mesh_jp` | `172.31.0.6` | `dev wgeujp` | `65013` | 100 | `*` |
| `10.140.0.0/24` | `mesh_cn` | `172.31.0.10` | `dev wgeucn` | `65014` | 100 | `*` |
| `10.10.0.0/24` | `azure_0` | `10.210.0.1` | `via 10.210.0.1 on eth0` | `65515` | 300 | `*` |
| `10.20.0.0/24` | `mesh_us` | `172.31.0.2` | `dev wgeuus` | `65012 65515` | 300 | `*` |
| `10.30.0.0/24` | `mesh_jp` | `172.31.0.6` | `dev wgeujp` | `65013 65515` | 300 | `*` |

### JP selected NVA routes

| Prefix | Protocol | BGP next hop | BIRD resolution | ASPath | LP | Marker |
|---|---|---|---|---|---|---|
| `10.110.0.0/24` | `mesh_eu` | `172.31.0.5` | `dev wgeujp` | `65011` | 100 | `*` |
| `10.120.0.0/24` | `mesh_us` | `172.31.0.13` | `dev wgusjp` | `65012` | 100 | `*` |
| `10.130.0.0/24` | `own_dc` | `n/a` | `dev eth0` | `n/a` | n/a | `*` |
| `10.140.0.0/24` | `mesh_cn` | `172.31.0.22` | `dev wgjpcn` | `65014` | 100 | `*` |
| `10.10.0.0/24` | `mesh_eu` | `172.31.0.5` | `dev wgeujp` | `65011 65515` | 300 | `*` |
| `10.20.0.0/24` | `mesh_us` | `172.31.0.13` | `dev wgusjp` | `65012 65515` | 300 | `*` |
| `10.30.0.0/24` | `azure_1` | `169.254.21.6` | `via 169.254.21.6 on xfrm42` | `65515` | 300 | `!` |

### CN selected NVA routes

| Prefix | Protocol | BGP next hop | BIRD resolution | ASPath | LP | Marker |
|---|---|---|---|---|---|---|
| `10.110.0.0/24` | `mesh_eu` | `172.31.0.9` | `dev wgeucn` | `65011` | 100 | `*` |
| `10.120.0.0/24` | `mesh_us` | `172.31.0.17` | `dev wguscn` | `65012` | 100 | `*` |
| `10.130.0.0/24` | `mesh_jp` | `172.31.0.21` | `dev wgjpcn` | `65013` | 100 | `*` |
| `10.140.0.0/24` | `own_dc` | `n/a` | `dev eth0` | `n/a` | n/a | `*` |
| `10.10.0.0/24` | `mesh_eu` | `172.31.0.9` | `dev wgeucn` | `65011 65515` | 300 | `*` |
| `10.20.0.0/24` | `mesh_us` | `172.31.0.17` | `dev wguscn` | `65012 65515` | 300 | `*` |
| `10.30.0.0/24` | `mesh_jp` | `172.31.0.21` | `dev wgjpcn` | `65013 65515` | 300 | `*` |

### Scoped workload traffic

**DC -> Azure spoke**

| DC / Azure spoke | spoke-eu | spoke-us | spoke-jp |
|---|---|---|---|
| dc-eu | P/P | P/P | P/P |
| dc-us | P/P | P/P | P/P |
| dc-jp | P/P | P/P | P/P |
| cn | P/P | P/P | P/P |

**Azure spoke -> DC**

| DC / Azure spoke | spoke-eu | spoke-us | spoke-jp |
|---|---|---|---|
| dc-eu | P/P | P/P | P/P |
| dc-us | P/P | P/P | P/P |
| dc-jp | P/P | P/P | P/P |
| cn | P/P | P/P | P/P |
