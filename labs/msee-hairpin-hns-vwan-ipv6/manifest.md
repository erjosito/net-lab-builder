# Manifest — `msee-hairpin-hns-vwan-ipv6`

**Version:** Stage 2 (full)  **Date:** 2026-06-15  **Author:** Morpheus  
**Path:** A — ER Direct (no Megaport)  
**Status:** 🔒 Awaiting Phase 4 deploy gate (§8)

---

## §1 Resource Inventory

RG: `rg-msee-hairpin-<corr_id>` · Region: `swedencentral`  
Tags (all resources): `lab=true`, `created_by=copilot-lab`, `lab_id=msee-hairpin-<corr_id>`

### Connectivity — ER Direct & circuits

| # | Name | Type | Key attributes |
|---|---|---|---|
| 1 | `erp-hairpin-<corr_id>` | ER Direct port | 10 Gbps; encapsulation=QinQ; peering location=Stockholm |
| 2 | `er-hns-<corr_id>` | ER circuit (Circuit 1 — HnS) | Local, MeteredData, 10 Gbps; `express_route_port_id` → #1 |
| 3 | `er-vwan-<corr_id>` | ER circuit (Circuit 2 — vWAN) | Local, MeteredData, 10 Gbps; `express_route_port_id` → #1 |
| 4 | Circuit 1 — IPv4 peering | `azurerm_express_route_circuit_peering` | Private; primary `172.16.1.0/30`, secondary `172.16.1.4/30`; peer ASN=65515; VLAN=100 |
| 5 | Circuit 1 — IPv6 peering | `azurerm_express_route_circuit_peering` (IPv6 extension) | `ipv6.primary_peer_address_prefix=fd00:f:1::/126`, secondary=`fd00:f:1::4/126`; same resource as #4 |
| 6 | Circuit 2 — IPv4 peering | `azurerm_express_route_circuit_peering` | Private; primary `172.16.2.0/30`, secondary `172.16.2.4/30`; peer ASN=65515; VLAN=200 |
| 7 | Circuit 2 — IPv6 peering | (IPv6 extension on #6) | `ipv6.primary_peer_address_prefix=fd00:f:2::/126`, secondary=`fd00:f:2::4/126` |

### Hub-and-spoke layer

| # | Name | Type | Key attributes |
|---|---|---|---|
| 8 | `vnet-hns-hub-<corr_id>` | VNet | `10.1.0.0/16` + `fd00:1::/48`; subnets: GatewaySubnet `10.1.0.0/27`+`fd00:1::/64`, vm `10.1.1.0/24`+`fd00:1:1::/64` |
| 9 | `vnet-hns-spoke-<corr_id>` | VNet | `10.2.0.0/24` + `fd00:2::/48`; subnet: `10.2.0.0/24`+`fd00:2::/64` |
| 10 | `peer-hub-to-spoke-<corr_id>` | VNet peering | hub→spoke; `allowGatewayTransit=true`, `allowForwardedTraffic=true` |
| 11 | `peer-spoke-to-hub-<corr_id>` | VNet peering | spoke→hub; `useRemoteGateways=true`, `allowForwardedTraffic=true` |
| 12 | `pip-ergw-hns-<corr_id>` | Standard PIP | Zone-redundant; Static; for ER GW below |
| 13 | `ergw-hns-<corr_id>` | VNet ER GW | ErGw1AZ; dual-stack NIC config (IPv4+IPv6); **`allow_virtual_wan_traffic=true`**; **`allow_remote_vnet_traffic=true`** ⚠️ see Risk R2 |
| 14 | `conn-hns-<corr_id>` | ER GW connection | GW `ergw-hns` ↔ Circuit `er-hns`; type=ExpressRoute |

### Virtual WAN layer

| # | Name | Type | Key attributes |
|---|---|---|---|
| 15 | `vwan-hairpin-<corr_id>` | Virtual WAN | Standard SKU |
| 16 | `vhub-hairpin-<corr_id>` | Virtual Hub | `swedencentral`; IPv4 `10.3.0.0/23`; IPv6 `fd00:3::/48`; Standard |
| 17 | `ergw-vhub-<corr_id>` | vHub ER GW | `azurerm_express_route_gateway`; `scale_units=1`; **`allow_non_virtual_wan_traffic=true`** |
| 18 | `conn-vhub-er-<corr_id>` | vHub ER connection | GW `ergw-vhub` ↔ Circuit `er-vwan`; `enable_internet_security=false` |
| 19 | `vnet-vwan-spoke-<corr_id>` | VNet | `10.4.0.0/24` + `fd00:4::/48`; subnet: `10.4.0.0/24`+`fd00:4::/64` |
| 20 | `conn-vhub-vnet-<corr_id>` | vHub VNet connection | vHub `vhub-hairpin` ↔ VNet `vnet-vwan-spoke`; `enable_internet_security=false` |

### Compute layer

| # | Name | Type | Key attributes |
|---|---|---|---|
| 21 | `nsg-hns-<corr_id>` | NSG | SSH in from `<admin_cidr>`; ICMP+ICMPv6 in+out any |
| 22 | `pip-hns-<corr_id>` | Standard PIP | Static; for HnS spoke VM SSH |
| 23 | `nic-hns-<corr_id>` | NIC | Dual-stack; `vnet-hns-spoke` VM subnet; NSG `nsg-hns`; PIP `pip-hns` |
| 24 | `vm-hns-<corr_id>` | Linux VM | B2als_v2; Ubuntu 22.04; admin=`azurelab`; password from KV `default-password` |
| 25 | `nsg-vwan-<corr_id>` | NSG | SSH in from `<admin_cidr>`; ICMP+ICMPv6 in+out any |
| 26 | `pip-vwan-<corr_id>` | Standard PIP | Static; for vWAN spoke VM SSH |
| 27 | `nic-vwan-<corr_id>` | NIC | Dual-stack; `vnet-vwan-spoke` subnet; NSG `nsg-vwan`; PIP `pip-vwan` |
| 28 | `vm-vwan-<corr_id>` | Linux VM | B2als_v2; Ubuntu 22.04; admin=`azurelab`; password from KV `default-password` |

**Total: 28 named resources + 1 RG = 29**

---

## §2 Deploy Sequence

```
Step 1  (~5 min)   RG  →  ER Direct port erp-hairpin
Step 2  (~3 min)   ER circuits er-hns + er-vwan  [parallel, on port]
                   + IPv4/IPv6 peering configs for both circuits
Step 3  (~2 min)   VNets: hns-hub, hns-spoke, vwan-spoke  [parallel]
                   NSGs: nsg-hns, nsg-vwan  [parallel]
Step 4  (~1 min)   VNet peerings hub↔spoke  [after both HnS VNets ready]
Step 5  (~2 min)   vWAN + vHub  [parallel with Step 3]
Step 6  ★LONG POLE (~20-45 min)  [parallel pair]:
          HnS ER GW ergw-hns + pip-ergw-hns
          vHub ER GW ergw-vhub  (requires vHub from Step 5)
Step 7  (~5 min)   ER connections: conn-hns + conn-vhub-er  [parallel, after Step 6]
Step 8  (~1 min)   vHub VNet connection conn-vhub-vnet  [after vHub ready]
Step 9  (~3 min)   PIPs pip-hns + pip-vwan; NICs; VMs  [parallel]
────────────────────────────────────────────────
Total estimated: 45–60 min  (ER GW pair is the long pole)
```

---

## §3 Cleanup Sequence

```
Step 1   VMs (vm-hns, vm-vwan)
Step 2   NICs + PIPs + NSGs (nic-*, pip-hns, pip-vwan, nsg-*)
Step 3   vHub VNet connection conn-vhub-vnet        ← must precede VNet delete
Step 4   vHub ER connection conn-vhub-er            ← must precede circuit + GW delete
Step 5   HnS ER GW connection conn-hns              ← must precede circuit + GW delete
Step 6   HnS ER GW ergw-hns + pip-ergw-hns          ← after conn-hns deleted
Step 7   vHub ER GW ergw-vhub                       ← after conn-vhub-er deleted
Step 8   ER private peering configs (both circuits) ← before circuit delete
Step 9   ER circuits er-hns + er-vwan               ← ⚠️ blocks if any connection remains
Step 10  ER Direct port erp-hairpin                 ← ⚠️ blocks if any circuit remains
Step 11  vHub vhub-hairpin  →  vWAN vwan-hairpin
Step 12  VNet peerings  →  VNets
Step 13  RG delete (safety net for stragglers)
```

---

## §4 Cost

**Note:** ER Direct port is **free for 45 days from provisioning** (Azure bring-up window). For any lab ≤45 days, the port row is `$0/day`. Port billing (`~$47/day`) only applies after day 46.

| Resource | $/day (≤45d) | $/day (>45d) | Basis |
|---|---|---|---|
| ER Direct port 10 Gbps | **$0** | ~$47 | ~$1,408/month swedencentral; first 45 days free |
| Circuit 1 (HnS, Local) | ~$1 | ~$1 | ~$55/month |
| Circuit 2 (vWAN, Local) | ~$1 | ~$1 | ~$55/month |
| HnS ER GW ErGw1AZ | ~$6 | ~$6 | ~$170/month |
| vHub ER GW 1 scale unit | ~$5 | ~$5 | ~$150/month |
| vWAN hub Standard | ~$6 | ~$6 | $0.25/hr |
| 2× VM B2als_v2 | ~$2 | ~$2 | ~$0.04/hr each |
| 3× Standard PIPs | <$1 | <$1 | $0.005/hr each |
| **Daily total** | **~$22–25** | **~$70** | |
| **6h test total** | **~$6–7** | **~$17.50** | |

---

## §5 Designs Studied

### A — ER Direct hairpin ✅ (Primary)

Two sub-circuits provisioned on a single 10 Gbps ER Direct port in Stockholm. Circuit 1 → HnS ER GW; Circuit 2 → vWAN hub ER GW. Both circuits have IPv4 (/30) and IPv6 (/126) private peering with separate BGP sessions. The MSEE in Stockholm learns HnS spoke prefixes from Circuit 1's Azure-side session and vWAN spoke prefixes from Circuit 2's Azure-side session, then reflects each side's routes to the other — the hairpin. No customer-side (on-prem) BGP session on the port is required; the MSEE-to-ER-GW sessions alone drive prefix exchange. This is the central technical bet: if MSEE route reflection between two Azure-side circuits on the same ER Direct port works without customer-side peers, the lab succeeds. Niobe's S3 route-table captures are the primary evidence. Three non-default GW toggles must be set — without them the hairpin silently fails with no obvious error.

### B — Megaport circuits ⚠️ (Fallback if A's BGP assumption fails)

Replace the ER Direct port + sub-circuits with two standard ER circuits backed by a Megaport MCR in Stockholm (1 MCR, 2 VXCs). The MCR establishes the customer-side BGP sessions that Path A omits, guaranteeing end-to-end BGP on both circuits. Same GW topology, same hairpin mechanism, same GW toggles. Overrides Jose's "no Megaport" preference. Requires `megaport-api-key` + `megaport-api-secret` from `platform-secrets-1138` (coordinate KV access). Cost drops to ~$35-45/day; MCR + VXC provisioning adds ~15 min. Activate only if Path A circuits show empty route tables post-connection.

### C — IPsec VPN 📚 (Anti-pattern / 2nd fallback)

Replace both ER GWs with VPN Gateways (VpnGw1, BGP-enabled, ASN 65010 HnS / ASN 65515 vWAN built-in). Configure BGP-enabled S2S IPsec tunnels (IKEv2, IPv6 traffic selectors) between the HnS VPN GW and the vWAN hub VPN GW. IPv6 dual-stack reachability is still fully testable. The lab teaches BGP-over-IPsec dual-stack, not MSEE hairpinning — a different mechanism. Still publishable as a "how to connect hub-and-spoke to vWAN without ExpressRoute" blog topic. Cost ~$15-20/day. Use only if MSEE hairpin is confirmed infeasible after A and B attempts.

---

## §6 Scenarios

**S1 — IPv4 baseline (MSEE hairpin)**  
With all connections established, SSH to `vm-vwan` and ping `vm-hns` over IPv4 (`10.2.0.4`). Verifies end-to-end forwarding plane before IPv6 test. **Pass:** ≥4/5 replies, RTT<100ms. **Evidence:** `01-s1-ipv4-ping.txt`.

**S2 — IPv6 hairpin (primary test)**  
From `vm-vwan`, ping the IPv6 address of `vm-hns` (`fd00:2::4` or actual assigned address). This is the lab's primary test — hairpin carrying IPv6 between a traditional VNet ER GW and a vWAN hub ER GW. **Pass:** ≥4/5 replies. **Fail:** 0/5 despite S1 passing — indicates IPv6 ER peering session not established or IPv6 GW settings missing. **Evidence:** `02-s2-ipv6-ping.txt`.

**S3 — Route propagation evidence**  
Four captures: (a) `az network vnet-gateway list-learned-routes` on `ergw-hns` — must include `10.4.0.0/24` and `fd00:4::/48` with source=`ExpressRoute`; (b) `az network express-route list-route-tables -n er-hns --path primary` — MSEE must show vWAN spoke prefixes; (c) symmetric repeat for `ergw-vhub` learned routes; (d) `er-vwan` route-table must show HnS spoke prefixes. All four captures must show cross-side prefixes for both IPv4 and IPv6. **Evidence files:** `03` through `06`.

**S4 — Deliberate break: toggle disable**  
After S1/S2 pass, Tank sets `allow_virtual_wan_traffic=false` on `ergw-hns` via Terraform (or `az network vnet-gateway update`). Wait 60s for BGP hold-down. Re-run S1+S2. **Pass (for this scenario):** 0/5 on both pings. Tank re-enables toggle; re-run S1+S2 — must restore to ≥4/5 before lab is closed. Documents the "silent fail" property. **Evidence:** `07-s4-break-ipv4.txt`, `08-s4-break-ipv6.txt`, `09-s4-restore-ipv4.txt`, `10-s4-restore-ipv6.txt`.

**S5 — IPsec VPN stretch (optional)**  
If Path A succeeds and time allows: add `VpnGw1` to `vnet-hns-hub` (BGP ASN 65010) and enable the vWAN hub's built-in VPN GW. Configure S2S BGP connection. Re-run S1+S2 pings over VPN path (remove ER connections first OR add routes). Confirms IPv6 reachability via VPN as the documented fallback path. +20-30 min, +~$4.50/day incremental. **Evidence:** `11-s5-vpn-ipv4.txt`, `12-s5-vpn-ipv6.txt`.

---

## §7 Risks

| # | Risk | Likelihood | Mitigation |
|---|---|---|---|
| R1 | MSEE won't reflect between two Azure-only sessions (customer-side BGP required) | Medium | Monitor ER circuit route-tables immediately post-connection; if empty after 10 min, fall back to Path B (one Megaport MCR on Circuit 1) |
| R2 | `allow_virtual_wan_traffic` / `allow_non_virtual_wan_traffic` not in current azurerm provider | Medium | Tank uses `azapi_update_resource` for these three toggles; behavior identical to native attribute |
| R3 | IPv6 ER peering API changes / dual-stack GW config not GA | Low-Med | Niobe verifies post-deploy; IPv4-only test (S1/S3/S4) still valid if IPv6 peering fails; S2 becomes evidence gap |
| R4 | ER Direct port provision takes >30 min in Stockholm | Low | Tank starts port first, parallel-tracks VNet/vWAN provisioning; flag to Jose if >30 min before circuits |
| R5 | `platform-secrets-1138` KV ACL blocks `default-password` fetch | Known | Coordinate: Path A pause-GSA or Path B ACL-flip with snapshot/restore; single secret needed |

---

## §8 Phase 4 Gate

> **One question before Tank deploys:**
>
> Lab `msee-hairpin-hns-vwan-ipv6` — **Path A (ER Direct, Stockholm)**. Cost: **~$25/day** while ER Direct port is in its 45-day free-provisioning window (only circuits + 2× ER GWs + vHub + VMs accrue); **~$7 for 6h**. Port begins billing at day 46 (~$47/day port + same accrued items ≈ ~$70/day). Reply **"deploy"** to proceed. (Alternative: **"B"** for Megaport ~$40/day, **"C"** for IPsec VPN ~$17/day.)

---
*Manifest word target ≤ 15 KB.*
