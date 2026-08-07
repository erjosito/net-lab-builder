# dual-hub-hubless-region-ars — Stage-2 Pre-Deploy Manifest
Morpheus · 2026-08-03 · **STAGE-2 AWAITING PHASE-4 APPROVAL** · sources `trinity-third-region-ars-design.md`, `dual-hub-preflight.md`.

## Card Summary

One workload-aligned ARS VNet (polandcentral) extends BGP control-plane for set-C spokes toward hub1 (swedencentral) and hub2 (switzerlandnorth) — hub1-preferred/hub2-standby to simulated on-prem (norwayeast) — no third VPN GW/NVA stack.  
**IN:** ARS+VPN GW coexistence · `UseRemoteGateways=true` · multi-hop eBGP · 65515 loop-strip · AS-path prepend · inbound ARS route map (**PUBLIC PREVIEW**) · PSK-swap fault injection.  
**OUT:** vWAN · Azure Firewall · ExpressRoute · cross-spoke inter-region transit · hub-local failover for set A/B.

## 1. Resource Inventory

### Address / Subnet / ASN Plan

| VNet | Region | CIDR | GatewaySubnet | RouteServerSubnet | Other |
|---|---|---|---|---|---|
| vnet-hub1 | swedencentral | 10.10.0.0/16 | 10.10.0.0/27 | 10.10.0.64/27 | NVASubnet 10.10.1.0/27 |
| vnet-hub2 | switzerlandnorth | 10.20.0.0/16 | 10.20.0.0/27 | 10.20.0.64/27 | NVASubnet 10.20.1.0/27 |
| vnet-poland-ars | polandcentral | 10.30.0.0/24 | — | 10.30.0.0/27 | ARS-only; no GW |
| vnet-onprem | norwayeast | 10.40.0.0/16 | 10.40.0.0/27 | — | WorkloadSubnet 10.40.1.0/27 |
| vnet-spoke-a | swedencentral | 10.11.0.0/24 | — | — | default /24 |
| vnet-spoke-b | switzerlandnorth | 10.21.0.0/24 | — | — | default /24 |
| vnet-spoke-c1 | polandcentral | 10.31.0.0/24 | — | — | default /24 |
| vnet-spoke-c2 | polandcentral | 10.32.0.0/24 | — | — | prefix-only, no VM |

**ASN plan:** All ARS = 65515 (fixed) · hub VPN GWs = 65515 (ARS coexistence) · vpngw-onprem = 65000 · NVA1 = 65001 · NVA2 = 65002

RouteServerSubnet ≥/27 and GatewaySubnet: no UDR, no NSG.

### VPN Gateways (3 × VpnGw1 Active-Active BGP)

vpngw-hub1 (swedencentral, ASN 65515, b2b ON) · vpngw-hub2 (switzerlandnorth, ASN 65515, b2b ON) · vpngw-onprem (norwayeast, ASN 65000)  
Each AA = 2 Standard PIPs. Ref: [ARS+VPN GW coexistence](https://learn.microsoft.com/azure/route-server/expressroute-vpn-support)

### Azure Route Servers (3)

ars-hub1 (swedencentral, b2b ON) · ars-hub2 (switzerlandnorth, b2b ON) · ars-poland (polandcentral, b2b OFF)  
Each ARS = 1 Standard PIP (SDN mgmt plane, mandatory). Ref: [ARS FAQ](https://learn.microsoft.com/azure/route-server/route-server-faq)

### ✅ Standard Public IPs — Total = **9** (CORRECTED)

3 VPN GW AA × 2 = **6** + 3 ARS × 1 = **3** → **Total = 9**  
Per region: swedencentral 3 (GW×2+ARS×1) · switzerlandnorth 3 · norwayeast 2 (GW×2) · polandcentral 1 (ARS×1).  
*Trinity correction 2026-08-03 14:00: Niobe's claim of 6 PIPs (zero for ARS) was incorrect.*

### VMs — 6 × Standard_B2ts_v2 (Ubuntu 22.04, Standard SSD, no VM PIP)

| Name | Region | IP | Role |
|---|---|---|---|
| vm-nva1 | swedencentral | 10.10.1.4 | NVA BIRD ASN 65001, IP-fwd ON |
| vm-nva2 | switzerlandnorth | 10.20.1.4 | NVA BIRD ASN 65002, IP-fwd ON |
| vm-hub1-ep | swedencentral | 10.11.0.x | Set-A endpoint |
| vm-hub2-ep | switzerlandnorth | 10.21.0.x | Set-B endpoint |
| vm-c1-ep | polandcentral | 10.31.0.x | Set-C1 endpoint |
| vm-onprem-ep | norwayeast | 10.40.1.x | On-prem endpoint |

Fallback: Standard_B2ls_v2 (preflight-confirmed all 4 regions).

### VPN Connection Objects — 4 bidirectional V2V

| # | Name | Local GW → Remote GW | PSK |
|---|---|---|---|
| 1 | conn-hub1-to-onprem | vpngw-hub1 → vpngw-onprem | psk-hub1-onprem |
| 2 | conn-onprem-to-hub1 | vpngw-onprem → vpngw-hub1 | psk-hub1-onprem |
| 3 | conn-hub2-to-onprem | vpngw-hub2 → vpngw-onprem | psk-hub2-onprem |
| 4 | conn-onprem-to-hub2 | vpngw-onprem → vpngw-hub2 | psk-hub2-onprem |

Azure V2V = one object per side; 2 pairs = 4 objects. Same PSK/IPsec/BGP surface as S2S+LNG; no Local Network Gateway. Fault-injectable via `az network vpn-connection shared-key update` + `vpn-connection reset`. No authoritative evidence blocks this model; escalate to S2S+LNG only if Phase-0 reveals hidden PSK/route behaviour. Ref: [VPN GW HA design](https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-highlyavailable)

### Resource Count Summary

8 VNets · 3 VPN GWs · 3 ARS · **9 Standard PIPs** · 4 VPN connections · 2 NVA VMs · 4 endpoint VMs · 2 Route Tables · 4 NSGs · **20 peering objects (10 logical pairs)** · 1 RG

*Trinity correction 2026-08-05: peering count was stated as 26 objects / 13 logical pairs. Evidence — §3 Peering & Connection Matrix lists exactly **10** logical pairs, and `deploy/templates/main.bicep` declares exactly **20** `Microsoft.Network/virtualNetworks/virtualNetworkPeerings` resources. Corrected to 20 objects / 10 pairs. Topology unchanged.*

rt-spoke-a: 0/0→10.10.1.4, GW-prop OFF (spoke-a). rt-spoke-b: 0/0→10.20.1.4, GW-prop OFF (spoke-b). Set-C spokes: no UDR — ARS injects 0/0.

## 2. Deployment Sequence

```
Wave 0  RG + 9 Standard PIPs
Wave 1  8 VNets + all subnets (parallel)
Wave 2  NSGs · Route Tables · associate to subnets
Wave 3  ★ LONG POLE — all parallel:
          vpngw-hub1/hub2/onprem    30-45 min
          ars-hub1/hub2/poland      15-20 min
          6 VMs                      5 min
Wave 4  20 VNet peering objects (after VNets + GWs)
Wave 5  4 VPN connection objects (after all 3 GWs)
Wave 6  8 ARS BGP peerings (after ARS + NVA IPs known)
Wave 7  BIRD Δ1+Δ2 config push to NVAs
         PSK generation → write to KV platform-secrets-1138
Wave 8  BGP convergence wait ~10 min → S1 assertion
```

## 3. Peering & Connection Matrix

Flags: AFT=AllowForwardedTraffic · AGT=AllowGatewayTransit · URG=UseRemoteGateways

| Pair | Hub/ARS side | Spoke/peer side | Purpose |
|---|---|---|---|
| hub1 ↔ spoke-a | AFT+AGT | AFT+URG | Set-A gateway transit |
| hub2 ↔ spoke-b | AFT+AGT | AFT+URG | Set-B gateway transit |
| poland-ars ↔ spoke-c1 | AFT+AGT | AFT+URG | Set-C1 ARS default inject |
| poland-ars ↔ spoke-c2 | AFT+AGT | AFT+URG | Set-C2 prefix-only |
| spoke-c1 ↔ hub1 | AFT only | AFT only | NVA1 data-plane; no transit |
| spoke-c1 ↔ hub2 | AFT only | AFT only | NVA2 data-plane; no transit |
| spoke-c2 ↔ hub1 | AFT only | AFT only | NVA1 data-plane; no transit |
| spoke-c2 ↔ hub2 | AFT only | AFT only | NVA2 data-plane; no transit |
| poland-ars ↔ hub1 | AFT only | AFT only | Multi-hop BGP underlay NVA1 |
| poland-ars ↔ hub2 | AFT only | AFT only | Multi-hop BGP underlay NVA2 |

No hub1↔hub2 peering. No transit flags on set-C↔hub — Poland VNet has no GW (URG requires a remote GW). Ref: [VNet peering](https://learn.microsoft.com/azure/virtual-network/virtual-network-peering-overview)

**BGP sessions (10):** NVA1↔ars-hub1 ×2 inst · NVA2↔ars-hub2 ×2 inst · NVA1↔ars-poland ×2 inst (multi-hop, BIRD `multihop 3`) · NVA2↔ars-poland ×2 inst (multi-hop) · vpngw-hub1↔vpngw-onprem · vpngw-hub2↔vpngw-onprem. Ref: [ARS multi-region](https://learn.microsoft.com/azure/route-server/multiregion)

## 4. Route-Policy Contracts

**Δ1 — 65515 loop-strip (BIRD NVA1+NVA2, mandatory)**  
Export filter on hub-ARS sessions: `bgp_path.delete(65515)` on routes learned from Poland ARS. Without this, ARS (ASN 65515) drops re-advertisements of its own AS, silently blackholing set-C routes.

**Δ2 — Hub2 AS-path prepend (BIRD NVA2, mandatory)**  
Export of 10.31/24+10.32/24 toward ars-hub2: prepend ASN 65002 ×2. On-prem sees `[65515,65001]` via hub1 vs `[65515,65002,65002,65002]` via hub2 → hub1 preferred.

**Δ3 — Inbound ARS route map on ars-poland↔NVA2 (⚠️ PUBLIC PREVIEW — S4 only)**  
Prepends 65002 ×2 on NVA2-originated 0/0. Poland ARS best-path for default = NVA1. Cannot modify ARS-native VNet prefix advertisements. First activation: ~30 min ARS upgrade + surcharge. GA API version wrapping endpoint does NOT make feature GA. Ref: [ARS route maps PREVIEW](https://learn.microsoft.com/azure/route-server/route-maps-about)

## 5. Secret Handling

PSKs **generated at deploy time only** — not stored in manifest, IaC, or Git:

```bash
PSK1=$(openssl rand -base64 32 | tr -dc 'A-Za-z0-9!@#' | head -c 32)
PSK2=$(openssl rand -base64 32 | tr -dc 'A-Za-z0-9!@#' | head -c 32)
az keyvault secret set --vault-name platform-secrets-1138 --name psk-hub1-onprem --value "$PSK1"
az keyvault secret set --vault-name platform-secrets-1138 --name psk-hub2-onprem --value "$PSK2"
```

VM SSH pubkeys (`vm-ssh-pub-*`) pre-existing in KV. **If KV unavailable**, PSKs held in shell-session variables only — no other shared-KV dependency assumed.

## 6. Cleanup Sequence

```
1  Delete 4 VPN connection objects
2  Delete 8 ARS BGP peerings
3  Delete 3 ARS (~10 min each)
4  Delete 3 VPN GWs (~15-20 min each)
5  Delete 20 VNet peering objects
6  Delete 6 VMs
7  Delete 9 Standard PIPs
8  az group delete rg-dual-hub-hubless-region-ars-<corrID> --yes --no-wait
9  az keyvault secret delete psk-hub1-onprem --vault-name platform-secrets-1138
   az keyvault secret purge  psk-hub1-onprem --vault-name platform-secrets-1138
   az keyvault secret delete psk-hub2-onprem --vault-name platform-secrets-1138
   az keyvault secret purge  psk-hub2-onprem --vault-name platform-secrets-1138
```

⚠️ `az group delete` purges only resources in the lab RG. It does **NOT** purge secrets in `platform-secrets-1138` (shared KV, separate RG, outside lab scope). **KV purge (Step 9) must run explicitly and separately.** Do not claim single-RG cleanup removes KV secrets.

## 7. Scenarios

### S1 — Steady State
Setup: all waves deployed, Δ1+Δ2 active, Δ3 NOT active.  
**PASS:** (a) ars-hub1+hub2 `list-learned-routes` include 10.31/24+10.32/24. (b) vpngw-onprem `list-learned-routes` shows hub1 path `[65515,65001]` AND hub2 `[65515,65002,65002,65002]` for each set-C prefix. (c) vm-c1-ep NIC `show-effective-route-table` 0/0 → 10.10.1.4. (d) ping C1→on-prem OK.  
**FAIL:** BGP session down; AS-PATHs equal; set-C1 default → NVA2 IP; ping fails.  
**Evidence:** `list-learned-routes` + `show-effective-route-table` JSON · `run-command` ping.

### S2 — Hub1 Outage / Failover
Inject: wrong PSK on conn-hub1-to-onprem + conn-onprem-to-hub1; reset both; `systemctl stop bird` on vm-nva1 (no VM lifecycle).  
**PASS (≤180 s):** set-C1 effective 0/0 → 10.20.1.4; on-prem RIB = hub2 only; ping resumes.  
**FAIL:** Route not withdrawn at 180 s; ping fails >180 s. Poll at 30/60/120/180 s.  
**Evidence:** `show-effective-route-table` before/after · `list-learned-routes` ars-poland · ping.

### S3 — Hub1 Recovery / Failback
Restore: read original PSK from KV → update both conn objects + reset; `systemctl start bird` on vm-nva1.  
**PASS (≤90 s):** set-C1 effective 0/0 → 10.10.1.4; routes match S1 exactly.  
**FAIL:** No revert at 90 s or state differs from S1.  
**Evidence:** Same CLI as S1.

### S4 — Δ3 Route-Map Preview
Pre-condition: S1 PASS; collect ars-poland baseline `list-learned-routes`. Apply inbound route map (§4 Δ3). Wait ≤30 min ARS upgrade + 5 min convergence.  
**PASS:** ars-poland `list-learned-routes` shows 0/0: NVA1 `[65001]` and NVA2 `[65002,65002,65002]`; ARS best-path = NVA1; set-C1 effective 0/0 → 10.10.1.4.  
**FAIL:** AS-PATHs equal; set-C1 → NVA2 after convergence.  
**Evidence:** `list-learned-routes` before/after · `show-effective-route-table` · `az network routeserver show` provisioningState.

### S5 — Prefix-Only Spoke Scale
**PASS:** vpngw-onprem `list-learned-routes` shows 10.32.0.0/24 via hub1 `[65515,65001]` AND hub2 `[65515,65002,65002,65002]`. No VM in spoke-c2 — ARS propagates per-VNet prefix.  
**FAIL:** 10.32/24 absent; or via one hub only.  
**Evidence:** `list-learned-routes` on vpngw-onprem + ars-hub1 + ars-hub2.

## 8. Designs Studied

| Design | Verdict |
|---|---|
| D1 Workload-aligned ARS extension (this lab) | ✅ Recommended — S1–S5 |
| D2 Classical hub-local baseline (set A/B) | ✅ Validated via S1 effective routes |
| D3 Central ARS in unrelated 4th region | ⚠️ Anti-pattern — independent SPOF; paper analysis only |
| D4 Per-region full-hub production alternative | 📚 Not tested — 3× cost; cost comparison only |
| D5 NVA-terminated IPsec (Morpheus initial) | ❌ Rejected by Trinity — V2V GW model is feasible |

## 9. Risks & Limitations

| Risk | Mitigation |
|---|---|
| ARS route maps PUBLIC PREVIEW — SLA/billing not guaranteed | Δ3 isolated to S4; lab completes without it |
| BGP hold timer 180 s — S2 worst-case convergence 3 min | Documented in S2 PASS criteria |
| Multi-hop BGP NVA↔ars-poland: TTL must be ≥2 | BIRD `multihop 3`; validated vs ARS multi-region docs |
| KV `platform-secrets-1138` is shared infra — Tank needs explicit RBAC | PSK falls back to in-process shell vars |
| Set-C↔set-A/B cross-spoke transit not in scope | Explicitly out; absence ≠ bug |
| Hub-local failover (set A/B) not tested | Accepted: region loss = workload loss |

## 10. Timing

Without S4: **~75–90 min** · With S4 (first-use ARS upgrade): **~105–120 min**  
Wave 3 long pole (GWs+ARS+VMs in parallel): 30–45 min · Waves 4–8: ~15 min · S1–S3+S5: ~25 min · S4 upgrade: +30 min.

## 11. Cost & Confidence

Basis: Azure Retail Pricing PAYG USD 2026-08-03. **Confidence: MEDIUM.**

| Resource | Qty | $/day |
|---|---|---|
| VPN GW VpnGw1 AA (2 billing units/GW) | 6 units | $27.36 |
| Azure Route Server (Standard) | 3 | $32.40 |
| VMs Standard_B2ts_v2 Linux | 6 | $1.58 |
| VPN S2S connection | 4 | $1.44 |
| Standard PIP (idle) | 9 | $1.08 |
| Disks + egress | — | ~$2.00 |
| **Baseline** | | **≈ $65.86/day** |
| Δ3 route map surcharge (when active) | — | +~$6/day |
| **With Δ3 active** | | **≈ $72/day** |

⚠️ **Guardrail rule #7 BREACHED — > $50/day.** No cheaper BGP/AA VPN GW SKU; Basic is entry ARS SKU. **Phase-4 approval required.**

## 12. Microsoft Learn References

All `https://learn.microsoft.com/azure/`: `route-server/route-server-faq` · `route-server/expressroute-vpn-support` · `route-server/route-maps-about` · `route-server/multiregion` · `virtual-network/virtual-network-peering-overview` · `vpn-gateway/vpn-gateway-bgp-overview` · `vpn-gateway/vpn-gateway-highlyavailable`

## 13. Phase-4 Approval Gate

**TANK IS BLOCKED UNTIL JOSE MORENO EXPLICITLY APPROVES.**

```
PHASE-4 APPROVAL — dual-hub-hubless-region-ars — Morpheus 2026-08-03
═══════════════════════════════════════════════════════════════════
RESOURCES
  8 VNets · 3 VPN GW VpnGw1 AA · 3 ARS
  9 Standard PIPs (6 GW + 3 ARS)  ← CORRECTED
  4 VPN connections (2 bidirectional V2V pairs)
  2 NVA + 4 endpoint VMs (B2ts_v2, no PIP)
  2 Route Tables · 20 peering objects · 1 RG   ← CORRECTED (was 26; 10 pairs)
  Regions: swedencentral · switzerlandnorth · polandcentral · norwayeast

TIME  ~75-90 min w/o S4  /  ~105-120 min with S4 (first-use ARS upgrade)

⚠ COST GUARDRAIL BREACHED — rule #7 limit $50/day
  Baseline ≈ $66/day · With Δ3 ≈ $72/day · Confidence: MEDIUM

⚠ ARS route maps = PUBLIC PREVIEW — first use ~30 min upgrade + surcharge

SECRETS  PSKs generated at deploy time; KV platform-secrets-1138 or
         in-process shell vars. KV purge (Step 9) NOT automatic from RG delete.

APPROVAL REQUIRED FROM: Jose Moreno
  [ ] YES — proceed to IaC + deployment
  [ ] NO  — cancel or revise

Morpheus/Tank will NOT deploy until explicit approval is received.
═══════════════════════════════════════════════════════════════════
```


