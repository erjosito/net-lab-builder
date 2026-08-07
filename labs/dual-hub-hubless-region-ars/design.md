# dual-hub-hubless-region-ars — Network Design
**Author:** Trinity (Azure Network SME) · **Date:** 2026-08-03 · **Status:** LOCKED — pre-deploy only; no IaC

> ⚠️ **EMPIRICAL AMENDMENT 2026-08-03T20:19+02:00 (Trinity):** Δ3 ARS route-map activation failed at runtime. See §17 for findings and options. **Design unchanged pending Jose Moreno decision.**

---

## 1. Executive Summary

One workload-aligned ARS VNet in **polandcentral** (hubless) is the BGP control-plane extension for set-C spokes toward **swedencentral** hub1 and **switzerlandnorth** hub2. Each set-C spoke is triple-peered: `UseRemoteGateways` to the Poland ARS VNet (route injection) + two data-plane-only peerings to hub1 and hub2 (NVA next-hop reachability without overlay). Set-A/B spokes use classical hub-local gateway transit with explicit `0/0→NVA` UDRs, BGP propagation disabled. Three mandatory policies (Δ1 65515-strip, Δ2 NVA2 prepend, Δ3 ARS route-map preview) produce deterministic hub1-preferred / hub2-standby for set-C.

**Out of scope:** vWAN, Azure Firewall, ExpressRoute, inter-hub NVA overlay, cross-spoke inter-region transit, internet egress via NVA, hub-local failover for sets A/B.

---

## 2. VNets and Subnets

| VNet | Region | Address Space | Subnet | CIDR | Notes |
|---|---|---|---|---|---|
| vnet-hub1 | swedencentral | 10.10.0.0/16 | GatewaySubnet | 10.10.0.0/27 | VPN GW AA — no NSG/UDR |
| | | | RouteServerSubnet | 10.10.0.64/27 | ARS — no NSG/UDR |
| | | | snet-nva | 10.10.1.0/27 | NVA1; IP forwarding ON |
| | | | snet-endpoint | 10.10.2.0/27 | hub1 test VM |
| vnet-hub2 | switzerlandnorth | 10.20.0.0/16 | GatewaySubnet | 10.20.0.0/27 | VPN GW AA — no NSG/UDR |
| | | | RouteServerSubnet | 10.20.0.64/27 | ARS — no NSG/UDR |
| | | | snet-nva | 10.20.1.0/27 | NVA2; IP forwarding ON |
| | | | snet-endpoint | 10.20.2.0/27 | hub2 test VM |
| vnet-poland-ars | polandcentral | 10.30.0.0/24 | RouteServerSubnet | 10.30.0.0/27 | ARS only — no GW/NVA/NSG/UDR |
| vnet-onprem | norwayeast | 10.40.0.0/16 | GatewaySubnet | 10.40.0.0/27 | VPN GW AA — no NSG/UDR |
| | | | snet-endpoint | 10.40.1.0/27 | on-prem test VM |
| vnet-spoke-a | swedencentral | 10.11.0.0/24 | snet-workload | 10.11.0.0/25 | UDR: 0/0→NVA1; bgp-propagation off |
| vnet-spoke-b | switzerlandnorth | 10.21.0.0/24 | snet-workload | 10.21.0.0/25 | UDR: 0/0→NVA2; bgp-propagation off |
| vnet-spoke-c1 | polandcentral | 10.31.0.0/24 | snet-workload | 10.31.0.0/25 | No UDR — ARS injects 0/0 |
| vnet-spoke-c2 | polandcentral | 10.32.0.0/24 | — | 10.32.0.0/24 | Prefix-only |

**PIPs: 9 Standard**

| Resource | Count | PIPs each | Total |
|---|---|---|---|
| ARS hub1 | 1 | 1 | 1 |
| ARS hub2 | 1 | 1 | 1 |
| ARS polandcentral | 1 | 1 | 1 |
| VPN GW hub1 (AA) | 1 | 2 | 2 |
| VPN GW hub2 (AA) | 1 | 2 | 2 |
| VPN GW on-prem (AA) | 1 | 2 | 2 |
| **Total** | | | **9** |

---

## 3. VNet Peering Matrix (all flags explicit)

All peerings are bidirectional. Columns show the flag value on the **listed end** (A→B).

| Peering (A↔B) | `AllowFwdTraffic` A/B | `AllowGwTransit` A/B | `UseRemoteGW` A/B | Notes |
|---|---|---|---|---|
| vnet-hub1 ↔ vnet-spoke-a | true/true | **true**/false | false/**true** | Hub1 = GW+ARS provider; one flag exposes both VPN GW transit and ARS injection. |
| vnet-hub2 ↔ vnet-spoke-b | true/true | **true**/false | false/**true** | Same for hub2. |
| vnet-poland-ars ↔ vnet-spoke-c1 | true/true | **true**/false | false/**true** | Poland ARS = ARS-only provider (no GW); exposes ARS injection only. |
| vnet-poland-ars ↔ vnet-spoke-c2 | true/true | **true**/false | false/**true** | Same, prefix-only spoke. |
| vnet-spoke-c1 ↔ vnet-hub1 | true/true | false/false | false/false | **Data-plane only.** Fabric path to NVA1 IP (10.10.1.x). No gateway transit. |
| vnet-spoke-c1 ↔ vnet-hub2 | true/true | false/false | false/false | **Data-plane only.** Fabric path to NVA2 IP (10.20.1.x). |
| vnet-spoke-c2 ↔ vnet-hub1 | true/true | false/false | false/false | Same as c1↔hub1. |
| vnet-spoke-c2 ↔ vnet-hub2 | true/true | false/false | false/false | Same as c1↔hub2. |
| vnet-poland-ars ↔ vnet-hub1 | true/true | false/false | false/false | BGP underlay + data-plane for NVA1 multi-hop sessions. |
| vnet-poland-ars ↔ vnet-hub2 | true/true | false/false | false/false | Symmetric for NVA2. |

6 VMs `Standard_B2ts_v2` Ubuntu 22.04 Standard SSD, no PIP: hub1 (NVA1 + endpoint), hub2 (NVA2 + endpoint), on-prem (endpoint), spoke-c1 (endpoint). spoke-c2 is prefix-only (no VM).

> ⚠️ **Constraint:** `UseRemoteGateways=true` on at most **one** peering per spoke VNet. Each set-C spoke sets it only on the Poland ARS peering.

---

## 4. ASN / BGP Peer Matrix (all 10 sessions)

| # | Local peer | Local ASN | Remote peer | Remote ASN | Multi-hop | Notes |
|---|---|---|---|---|---|---|
| 1 | NVA1 (10.10.1.4) | 65001 | Poland ARS instance-0 (10.30.0.4) | 65515 | yes (ebgp-multihop ≥4) | Global peering traversal |
| 2 | NVA1 (10.10.1.4) | 65001 | Poland ARS instance-1 (10.30.0.5) | 65515 | yes | Must peer both IPs for ECMP |
| 3 | NVA2 (10.20.1.4) | 65002 | Poland ARS instance-0 (10.30.0.4) | 65515 | yes | Global peering traversal |
| 4 | NVA2 (10.20.1.4) | 65002 | Poland ARS instance-1 (10.30.0.5) | 65515 | yes | Must peer both IPs |
| 5 | NVA1 (10.10.1.4) | 65001 | hub1 ARS instance-0 (10.10.0.68) | 65515 | no (same VNet) | Local; no multihop needed |
| 6 | NVA1 (10.10.1.4) | 65001 | hub1 ARS instance-1 (10.10.0.69) | 65515 | no | Local |
| 7 | NVA2 (10.20.1.4) | 65002 | hub2 ARS instance-0 (10.20.0.68) | 65515 | no | Local |
| 8 | NVA2 (10.20.1.4) | 65002 | hub2 ARS instance-1 (10.20.0.69) | 65515 | no | Local |
| 9 | hub1 VPN GW (10.10.0.4/5) | 65515 | on-prem VPN GW (10.40.0.4/5) | 65000 | — | IPsec tunnel; AA=4 tunnels |
| 10 | hub2 VPN GW (10.20.0.4/5) | 65515 | on-prem VPN GW (10.40.0.4/5) | 65000 | — | IPsec tunnel; AA=4 tunnels |

> ARS instance IPs assigned from RouteServerSubnet .64/27. Actual IPs confirmed post-deployment with `az network routeserver show`. Poland ARS instance IPs: 10.30.0.4–5.

**ARS coexistence requirements (hub1 and hub2 only):**

| Setting | Required value | Reason |
|---|---|---|
| VPN GW mode | active-active | Mandatory for ARS+VPN GW coexistence |
| VPN GW ASN | 65515 | Must match ARS ASN |
| ARS branch-to-branch | **ON** (hub1, hub2) | Enables NVA↔VPN GW route exchange |
| ARS branch-to-branch | **OFF** (Poland) | No VPN GW in Poland |

---

## 5. UDR Specifications

### Set-A workload subnet (10.11.0.0/25)
| Destination | Next-hop type | Next-hop IP | BGP propagation |
|---|---|---|---|
| 0.0.0.0/0 | VirtualAppliance | NVA1 NIC IP (10.10.1.4) | **Disabled** |

### Set-B workload subnet (10.21.0.0/25)
| Destination | Next-hop type | Next-hop IP | BGP propagation |
|---|---|---|---|
| 0.0.0.0/0 | VirtualAppliance | NVA2 NIC IP (10.20.1.4) | **Disabled** |

### Set-C subnets (10.31.x, 10.32.x) — **no UDR**
Poland ARS injects `0/0` dynamically with next-hop = NVA1 or NVA2 IP (best-path selected). UDR would override the ARS injection and break the Δ3 route-map experiment. No route table attached.

> **Why BGP propagation disabled on set-A/B:** Explicit `0/0→NVA` UDR governs; additional injected routes would conflict.

---

## 6. NIC IP Forwarding

| NIC | VM | VNet | IP Forwarding | Reason |
|---|---|---|---|---|
| nic-nva1 | vm-nva1 | vnet-hub1 | **Enabled** | Forwards traffic with dest ≠ own IP (on-prem↔spoke, cross-region) |
| nic-nva2 | vm-nva2 | vnet-hub2 | **Enabled** | Same |
| All endpoint VMs | vm-hub1-ep, vm-hub2-ep, vm-onprem-ep, vm-c1-ep | various | Disabled | Test endpoints only |

---

## 7. NSG Requirements

| Subnet / NIC | NSG required | Rules |
|---|---|---|
| RouteServerSubnet (all three) | **None** — do not attach | Platform-enforced; ARS provisioning fails if NSG present |
| GatewaySubnet (all three) | **None** | VPN GW requirement |
| snet-nva (hub1, hub2) | Recommended minimal | Allow TCP/179 inbound+outbound from ARS instance IPs (.68, .69 of local RS-subnet). Allow ICMP. Allow SSH (22) from mgmt. Deny all other inbound. |
| snet-endpoint (hub1, hub2, on-prem, c1) | Minimal lab NSG | Allow ICMP all. Allow SSH from mgmt. Deny other inbound. |
| snet-workload (spoke-a, spoke-b, spoke-c1, spoke-c2) | Minimal lab NSG | Allow ICMP all (test pings). Allow SSH if VM present. |

---

## 8. Route Policy Split — Δ1, Δ2, Δ3

### Δ1 — 65515 strip (mandatory, NVA1+NVA2, local-ARS-facing sessions)

**Direction:** Outbound NVA → local hub ARS (sessions #5–8).  
**Match:** Any route whose AS_PATH contains 65515.  
**Action:** Strip all 65515 occurrences.  
**Rationale:** Routes from Poland ARS carry `[65515, 65001/65002]`. Without stripping, hub ARS rejects them (loop-prevention). Runs before inbound route-maps in the ARS pipeline.

BIRD snippet (NVA1 → hub1 ARS):
```
filter export_to_hub_ars { bgp_path.delete(65515); accept; }
```

### Δ2 — NVA2 AS-path prepend for set-C spoke prefixes toward hub2 ARS

**Direction:** Outbound NVA2 → hub2 ARS (sessions #7–8).  
**Match:** 10.31.0.0/24, 10.32.0.0/24.  
**Action:** Prepend 65002 ×2.  
**Effect:** on-prem sees set-C via hub1 as `[65515,65001]`, via hub2 as `[65515,65002,65002,65002]`. Hub1 preferred.  
**Why NVA-side:** Classic VPN GW has no per-connection route-map primitive (vWAN-only). BIRD/FRR is the only lever.

BIRD snippet (NVA2 → hub2 ARS):
```
filter export_spoke_prepend_hub2 {
  bgp_path.delete(65515);
  if net ~ [10.31.0.0/24, 10.32.0.0/24] then {
    bgp_path.prepend(65002); bgp_path.prepend(65002); }
  accept;
}
```

### Δ3 — Poland ARS inbound route map on NVA2 BGP peering (**PUBLIC PREVIEW**)

**Direction:** Inbound into Poland ARS from NVA2 (sessions #3–4).
**Match:** Prefix 0.0.0.0/0 exactly.
**Action:** AS-path prepend ×2 (prepend 65002 twice).
**Effect:** Poland ARS evaluates best-path for `0/0`: NVA1 path = `[65001]` (length 1), NVA2 path after map = `[65002, 65002, 65002]` (length 3). Best-path = NVA1. Poland ARS injects `0/0 → NVA1_IP` into set-C spoke effective routes.

> ⚠️ **PUBLIC PREVIEW — surcharge; first activation triggers ~30 min one-off ARS upgrade.** Inbound direction is pre-best-path (outbound is post). The `0/0` is modifiable only when NVA-originated (Poland has no VPN GW — not an issue here). Cited: https://learn.microsoft.com/azure/route-server/route-maps-about
>
> **ASN constraint:** ARS route-map prepend actions reject private ASNs 64512–65534 and Azure-reserved ASNs. 65001 and 65002 are private-range — they cannot be used in the map action. Use doc-range ASN 64496 instead (RFC 5398, validated in prior lab). 🚩 **U1:** Whether prepending 64496 in the map still shifts best-path to NVA1 must be validated in S4. Fallback: implement Δ3 as NVA2-side BIRD filter (prepend 65002×2 before advertising to Poland ARS) — same split-policy result, no preview demo.

---

## 9. Why Set-C Direct Hub Peerings Make Remote NVA Next-Hops Reachable

When Poland ARS injects `0/0 → NVA1_IP` (10.10.1.4, inside hub1 VNet) into a set-C spoke, the Azure SDN fabric must route the packet to 10.10.1.4. VNet peering is **non-transitive** (peering-overview doc): the spoke↔Poland peering does not extend to hub1. Without a direct spoke↔hub1 peering, the fabric silently drops the packet.

The two data-plane-only peerings (spoke-c1/c2 ↔ hub1, spoke-c1/c2 ↔ hub2) add VNetPeering fabric entries for 10.10.0.0/16 and 10.20.0.0/16 into each set-C spoke's effective route table. NVA1_IP and NVA2_IP are now reachable as next-hops. `UseRemoteGateways=false` on these peerings is critical — it prevents hub VPN GW from injecting a second `0/0` that would conflict with the ARS-injected one.

---

## 10. Connection Model — 4-Object VNet-to-VNet

No Local Network Gateways (LNGs). Both GW ends are Azure VPN GW — use V2V connection type. **4 connection objects:**

| Object | Type | Source GW | Destination GW | Shared Key | BGP |
|---|---|---|---|---|---|
| conn-hub1-to-onprem | Vnet2Vnet | vgw-hub1 | vgw-onprem | psk-hub1-onprem (KV: platform-secrets-1138) | Enabled |
| conn-onprem-to-hub1 | Vnet2Vnet | vgw-onprem | vgw-hub1 | psk-hub1-onprem | Enabled |
| conn-hub2-to-onprem | Vnet2Vnet | vgw-hub2 | vgw-onprem | psk-hub2-onprem (KV: platform-secrets-1138) | Enabled |
| conn-onprem-to-hub2 | Vnet2Vnet | vgw-onprem | vgw-hub2 | psk-hub2-onprem | Enabled |

**Validation note:** V2V BGP behavior (PSK, IKE, BGP session, route advertisement) is functionally identical to S2S+LNG — no LNG bookkeeping. This is **documented behavior**, not an unproven assumption.

### PSK Reset Fault Injection (S2)

```bash
az network vpn-connection shared-key update -g <rg> -n conn-hub1-to-onprem --value "WRONG_PSK_A"
az network vpn-connection shared-key update -g <rg> -n conn-onprem-to-hub1 --value "WRONG_PSK_A"
az network vpn-connection reset -g <rg> -n conn-hub1-to-onprem
az network vpn-connection reset -g <rg> -n conn-onprem-to-hub1
ssh vm-nva1 sudo systemctl stop bird
```

**Recovery:** restore PSK from KV, reset connections, `systemctl start bird`. No VM lifecycle events.

> ⚠️ **UNPROVEN (U2):** `vpn-connection reset` timing under partial IKE failure may vary. Validate in S2.

---

## 11. Steady-State and Failure/Recovery Paths

### S1 — Steady State

| Traffic | Forward | Return |
|---|---|---|
| spoke-a → on-prem | UDR→NVA1→hub1 GW→IPsec | on-prem prefers hub1 `[65515,65001]` → hub1→NVA1→spoke-a |
| spoke-b → on-prem | UDR→NVA2→hub2 GW→IPsec | on-prem hub2 `[65515,65002]`→NVA2→spoke-b |
| spoke-c1/c2 → on-prem | ARS `0/0→NVA1_IP` (Δ3)→(peering fabric)→hub1→NVA1→GW→IPsec | on-prem: `[65515,65001]` < `[65515,65002,65002,65002]` → hub1→NVA1 |

**on-prem expected RIB:** 10.11/24 via hub1 `[65515,65001]`; 10.21/24 via hub2 `[65515,65002]`; 10.31/24+10.32/24 hub1 best + hub2 standby.

### S2 — Hub1 Outage (wrong PSK + BIRD stop)

PSK change + reset → IKE fails → hub1 BGP drops → on-prem withdraws (~5–30 s). BIRD stop → NVA1↔Poland ARS drops → Poland ARS shifts `0/0` best-path to NVA2 (0–180 s; immediate on NOTIFICATION, 180 s worst-case silent). Asymmetry window ≤ 180 s. PASS: spoke-c1 effective route `0/0→NVA2_IP`; on-prem set-C only via hub2.

### S3 — Hub1 Recovery

Restore PSK + reset + `systemctl start bird`. NVA1 re-peers; Poland ARS re-selects NVA1. PASS: routes match S1 within 30–90 s.

### S4 — Δ3 Route-Map Preview Activation

Enable inbound map on Poland ARS↔NVA2. PASS: `get-learned-routes` shows NVA1 best-path for `0/0`.

### S5 — Prefix-Only Spoke Scale

10.32.0.0/24 in Poland ARS learned routes + hub1 GW learned routes + on-prem RIB. PASS: ARS scales per-region VNet, not per-VM.

---

## 12. No-Overlay Scope

This lab excludes IPsec/VXLAN overlays between NVA1 and NVA2. Multi-hop eBGP from each NVA to Poland ARS traverses global VNet peering directly (Microsoft backbone). No overlay tunnel is required because: (1) global peering provides full L3 reachability between NVA subnets; (2) BGP TCP/179 traverses with `ebgp-multihop ≥4`; (3) set-C spoke data-plane traffic goes spoke→fabric→NVA (direct peering path) → hub VPN GW, not NVA1↔NVA2.

The no-overlay scope is possible only because the triple-peering model gives each spoke a direct fabric path to each NVA's VNet (as opposed to Fix-A, where an NVA in Poland would need overlays to forward data-plane traffic to hub NVAs).

---

## 13. Resiliency Analysis and Dormant Patches

### Failure mode table

| ID | Failure | Set-C impact | Set-A/B impact | Patch |
|---|---|---|---|---|
| F1 | Poland ARS hang | Existing routes persist; new spokes can't converge | None | Accept (SLA ≥99.9%) |
| F2 | NVA1 VM crash | Flips to NVA2 within 0–180 s | Set-A UDR black-holes (static) | **P1 dormant:** ILB pair in hub1; +~$1.5/day |
| F3 | NVA2 VM crash | No change (NVA1 preferred) | Set-B UDR black-holes | P1 symmetric for hub2 |
| F4 | Hub1 region outage | Reconverges to NVA2 (S2) | Set-A gone (accepted) | None — region = locality boundary |
| F5 | Hub2 region outage | No change (NVA1 preferred) | Set-B gone (accepted) | None |
| F6 | Poland VNet/ARS outage | `0/0` withdrawn; set-C black-holes | None | Accept as workload-region failure |
| F7 | One AA tunnel flap | None | None | Built-in AA behavior |
| F8 | One ARS instance failure | BGP to that IP drops; NVA re-establishes to other | Same | Inherent ARS HA |

**P1 cost/ops (dormant):** 2× Standard_B2ts_v2 + 2× ILB per hub ≈ +$0.56/day per hub. BIRD source-IP must be ILB VIP. Not enabled in v1.

---

## 14. Route Collection Checklist

| Layer | Command | Proves |
|---|---|---|
| Poland ARS learned (nva1) | `az network routeserver peering list-learned-routes --routeserver ars-poland --name peer-nva1` | NVA1 ads at Poland ARS; AS_PATH |
| Poland ARS learned (nva2) | same `--name peer-nva2` | NVA2 ads; Δ3 AS_PATH differential |
| Poland ARS advertised | `list-advertised-routes` | Spoke prefixes Poland ARS pushes to NVAs |
| Hub1 ARS learned (nva1) | `list-learned-routes --routeserver ars-hub1 --name peer-nva1` | Δ1-filtered routes at hub1 ARS |
| Hub2 ARS learned (nva2) | same hub2 | Δ1+Δ2-filtered routes at hub2 ARS |
| Hub1 GW BGP status | `az network vnet-gateway list-bgp-peer-status -n vgw-hub1` + `list-learned-routes` | GW BGP state; branch-to-branch path |
| On-prem GW learned | `az network vnet-gateway list-learned-routes -n vgw-onprem` | on-prem RIB: set-C AS_PATH differential |
| Effective routes (nic-c1-ep) | `az network nic show-effective-route-table -n nic-c1-ep` | ARS-injected `0/0→NVA_IP`; hub1+hub2 VNetPeering entries |
| Effective routes (nic-a-ep) | same | UDR override; bgpPropagation=disabled confirmed |
| NVA BIRD RIB | `birdc show route` + `ip route` | Δ1/Δ2 filter output; kernel FIB |
| on-prem OS | `ip route` on vm-onprem-ep | ECMP or single-path for 10.31.x/10.32.x |
| ICMP matrix | ping c1→onprem, onprem→c1, a→onprem | Data-plane proof |

---

## 15. Unproven Behavior — Flags

| # | Claim | Risk | Resolution |
|---|---|---|---|
| 🚩 U1 | Poland ARS inbound route-map prepend with doc-range ASN 64496 shifts best-path to NVA1 | Medium | Expected behavior (longer AS_PATH → NVA1 wins) but not yet lab-validated. Validate in S4; fallback = NVA2-side BIRD prepend. |
| 🚩 U2 | `vpn-connection reset` forces immediate IKE renegotiation | Low | Documented API; timing may vary. Measure in S2. |
| 🚩 U3 | `list-learned-routes` on Poland ARS shows AS_PATH after NVA-side Δ1 filter | Low | ARS shows routes as received from NVA (post-filter). Wrong output = BIRD filter misconfigured, not ARS behavior. Validate in S1. |
| 🚩 U4 | Set-C effective routes show BOTH hub1 and hub2 VNetPeering entries simultaneously | Low | Expected (each peering adds its remote prefix). Longer-prefix routing applies. Flag for verification. |

---

## 16. Learn References (all retrieved 2026-08-03)

| Topic | URL |
|---|---|
| ARS FAQ | https://learn.microsoft.com/azure/route-server/route-server-faq |
| ARS + VPN GW coexistence | https://learn.microsoft.com/azure/route-server/expressroute-vpn-support |
| ARS inbound route maps (preview) | https://learn.microsoft.com/azure/route-server/route-maps-about |
| ARS multi-region | https://learn.microsoft.com/azure/route-server/multiregion |
| VNet peering overview (gateway flags, transitivity) | https://learn.microsoft.com/azure/virtual-network/virtual-network-peering-overview |
| VPN GW BGP overview | https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-bgp-overview |

---

## 17. Δ3 Empirical Limitation and Options *(added 2026-08-03T20:19+02:00, Trinity)*

> **Design unchanged.** This section records an empirical constraint discovered during S4 activation and documents remediation options for Jose's decision. No IaC change made.

### 17.1 Platform Constraint — Route Map Cannot Reference Remote-VNet BGP Peer

Azure Route Server (standalone, non-vWAN) enforces that a BGP connection can only reference a route map if the peer IP is **within the ARS VNet's address space**. This is enforced at ARM validation time with error code `HubBgpConnectionFromSpokeVnetCannotReferenceRouteMap`.

- ars-poland VNet: `10.30.0.0/24`
- NVA1 peer IP: `10.10.1.4` (vnet-hub1, swedencentral) — **outside ARS VNet ❌**
- NVA2 peer IP: `10.20.1.4` (vnet-hub2, switzerlandnorth) — **outside ARS VNet ❌**

Both peers are multi-hop eBGP sessions from remote VNets peered to ars-poland. Neither satisfies the locality requirement. **ARS route-map cannot be applied to either peer in this topology.**

This constraint is **not documented** in Microsoft Learn as of 2026-08-03 (verified against [route-maps-about](https://learn.microsoft.com/azure/route-server/route-maps-about)). The runtime error is authoritative.

**Additional finding (Attempt 1):** The writable field for associating a map on a BGP connection is `routingConfiguration.inboundRouteMap` on the bgpConnection object, NOT `associatedInboundConnections` on the routeMap object (which is a read-only composite property). The association must be set on the connection resource.

**ARS upgrade state:** The first route-map creation triggers a ~30-minute ARS upgrade. This is permanent and irreversible without ARS recreation. The ~$6/day route-map surcharge persists regardless of whether any maps are active.

### 17.2 Options (evaluated, not selected — pending Jose decision)

| Option | Mechanism | Functional outcome | Data-plane impact | Added cost | Verdict |
|---|---|---|---|---|---|
| **A — Local relay NVA** | VM in ars-poland VNet re-originates 0/0 to ars-poland; relay IP satisfies locality | Route map applies; NVA1 best-path | 0/0 next-hop = relay IP → extra forwarding hop; relay becomes SPOF | +1 VM + complexity | ❌ Not recommended |
| **B — Secondary NIC in ARS VNet** | NVA VM NIC with IP in 10.30.0.0/24 | Route map applies | None | None | ❌ **Impossible — Azure VMs cannot have NICs in different VNets** |
| **C — NVA2 BIRD prepend** | NVA2 export filter adds `bgp_path.prepend(65002)×2` for 0/0 toward ars-poland sessions | ars-poland NVA2 path len=3 vs NVA1 len=1 → NVA1 wins | None — ARS still injects NVA1/NVA2 IPs directly | None | ✅ **Recommended** |
| **D — Synthetic local test peer** | VM in ARS VNet advertises RFC 5737 prefix; route map applied to this local peer only | Proves map mechanics; does not implement functional Δ3 | None | +1 VM ~$0.28/day | ⚠️ Teaching demo only |

### 17.3 Recommended Path (pending Jose decision)

**Option C** achieves all Δ3 functional objectives via NVA-side policy — the same pattern as Δ1 and Δ2. The BIRD filter change is:

```bird
# NVA2 — export filter toward ars_poland_0 and ars_poland_1
filter export_to_poland_ars {
    bgp_path.delete(65515);
    if net = 0.0.0.0/0 then {
        bgp_path.prepend(65002);
        bgp_path.prepend(65002);
    }
    accept;
}
```

ars-poland best-path: NVA1 `[65001]` (len 1) beats NVA2 `[65002,65002,65002]` (len 3). S4 validation: `list-learned-routes peer-nva2` shows `asPath: "65002 65002 65002"` for 0/0; c1-ep effective route 0/0 = single NVA1 IP; DEF-001 resolved.

**Failover (S2) preserved:** When NVA1 drops, ars-poland best-path flips to NVA2 (only remaining path, regardless of path length). Set-C 0/0 → NVA2. Recovery (S3): NVA1 re-peers, shorter path wins again.

**Decision required from Jose:** See `decision-inbox/delta3-failure-brief.md`.

---

*Trinity — design locked 2026-08-03. §17 empirical amendment 2026-08-03T20:19+02:00. No IaC, no CLI, no deployment in this document.*
