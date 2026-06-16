# Lab Card — `msee-hairpin-hns-vwan-ipv6`

**Status:** 🔒 AWAITING JOSE GATE (Path A/B/C — see §10)  **Date:** 2026-06-15  **Author:** Morpheus

---

## 1. Mechanism

MSEE hairpins traffic between a hub-and-spoke ER gateway and a Virtual WAN hub ER gateway — both circuits peering at the **Stockholm MSEE** (`swedencentral`) — over dual-stack IPv4+IPv6, no on-prem site, no firewall.

---

## 2. Region

`swedencentral` only. MSEE hairpin requires both circuits at the **same peering location** — multi-region breaks the test structurally.

---

## 3. SKUs & Required Settings

| Resource | SKU |
|---|---|
| ER Direct port (Path A) | 10 Gbps (floor SKU) |
| ER circuits | Local, MeteredData (cheapest; same-region GWs) |
| HnS ER Gateway | `ErGw1AZ` |
| vWAN ER Gateway | 1 scale unit (hub-native) |
| vWAN hub | Standard (no AzFW per spec) |
| VMs (×2) | `Standard_B2als_v2` (confirmed swedencentral 2026-06-15) |

**Hairpin-enabling settings (must be explicit in IaC):**
- HnS ER GW: `allowVirtualWanTraffic=true`, `allowRemoteVnetTraffic=true`
- vWAN ER GW: `allowNonVirtualWanTraffic=true` on the `expressRouteGateway` resource
- IPv6 ER private peering: separate IPv6 BGP session per circuit; /126 peering subnets

---

## 4. ASNs

| Speaker | ASN | Note |
|---|---|---|
| MSEE | 12076 | Fixed |
| HnS ER GW | 65515 | Fixed (VNet GW) |
| vWAN ER GW | 65515 | Fixed (vWAN ER GW; 65520 = inter-hub prepend marker only) |

---

## 5. Address Plan (dual-stack)

| VNet / segment | IPv4 | IPv6 (ULA) |
|---|---|---|
| HnS hub (GatewaySubnet / VM subnet) | `10.1.0.0/16` (`10.1.0.0/27` / `10.1.1.0/24`) | `fd00:1::/48` |
| HnS spoke | `10.2.0.0/24` | `fd00:2::/48` |
| vWAN hub address space | `10.3.0.0/23` | `fd00:3::/48` |
| vWAN spoke | `10.4.0.0/24` | `fd00:4::/48` |
| Circuit 1 (HnS) peering pri/sec | `172.16.1.0/30` / `172.16.1.4/30` | `fd00:f:1::/126` / `fd00:f:1::4/126` |
| Circuit 2 (vWAN) peering pri/sec | `172.16.2.0/30` / `172.16.2.4/30` | `fd00:f:2::/126` / `fd00:f:2::4/126` |

ULA chosen — Azure-to-Azure lab; no globally-routable IPv6 needed.

---

## 6. KV Secrets (`platform-secrets-1138`, `swedencentral`)

| Secret | Used by |
|---|---|
| `default-password` | VM admin password (password auth; no `vm-admin-ssh-public-key` in vault) |

`megaport-api-key` / `megaport-api-secret` present but not needed for Path A. GSA+KV ACL collision applies — coordinate before fetch.

---

## 7. Cost

| Path | Daily (≤45d) | Daily (>45d) | ~6h total | Key drivers |
|---|---|---|---|---|
| **A — ER Direct** ✅ | **~$25–30** | ~$65–75 | **~$7** | 10 Gbps port **$0 first 45 days from provisioning** (then ~$47/day); 2 circuits + 2 ER GWs + vHub apply throughout |
| B — Megaport | ~$35–45 | ~$35–45 | ~$10 | 2 circuits + 2 MCRs + 4 VXCs + 2 ER GWs + vHub |
| C — IPsec VPN | ~$15–20 | ~$15–20 | ~$5 | 2 VPN GWs + vHub; no MSEE hairpin |

**Path A within the $50/day guardrail for any lab ≤ 45 days.** ER Direct port has a 45-day free bring-up window from provisioning — only circuits, ER GWs, and vHub accrue charges during that window. Routine cost approval only.

---

## 8. Scenarios

| # | 1-line |
|---|---|
| S1 | IPv4 ping HnS spoke → vWAN spoke via MSEE hairpin (baseline) |
| S2 | IPv6 ping HnS spoke → vWAN spoke via MSEE hairpin (primary test) |
| S3 | Route-table evidence: each ER GW learns the other's spoke prefixes via MSEE |
| S4 | Disable `allowVirtualWanTraffic`; confirm hairpin breaks (deliberate-break) |
| S5 | *(stretch)* IPsec S2S BGP fallback — same IPv6 reachability without MSEE |

---

## 9. Designs Studied

| | Design | Status | Verdict hypothesis | Evidence |
|---|---|---|---|---|
| **A** | ER Direct — hairpin | ✅ Primary | No Megaport; customer-side BGP not needed — MSEE reflects Azure-side GW sessions only; port free first 45 days from provisioning so lab cost is routine | ER route-tables; `allowVirtualWanTraffic` toggle; BGP peer status |
| **B** | Megaport circuits — hairpin | ⚠️ Fallback | Same hairpin; cheaper port; overrides Jose's explicit "no Megaport" | Route-tables; MCR BGP; VXC state |
| **C** | IPsec VPN — no MSEE | 📚 Anti-pattern / 2nd fallback | Mechanism changes entirely (IKEv2+BGP, not MSEE); IPv6 dual-stack VPN still teachable | VPN GW BGP; effective routes; tunnel show |

**Key technical bet (Path A):** MSEE hairpinning between two Azure ER GWs requires only the Azure-side BGP sessions (GW↔MSEE). No customer-side router on the ER Direct port is needed. The MSEE learns each hub's prefixes from its own GW's BGP session and reflects them to the other circuit. *To be confirmed by Niobe post-deploy.*

---

## 10. Open Question for Jose

> **One gate before Stage 2:**
>
> - **A (ER Direct, ~$18 for 6h):** Respects your "no Megaport" ask. My recommendation.
> - **B (Megaport, ~$10 for 6h):** Cheaper, Megaport dependency returns.
> - **C (IPsec VPN, ~$5 for 6h):** No MSEE hairpin tested.
>
> Reply **A / B / C** to unlock Stage 2. Path A is the recommended choice — port is free for the first 45 days from provisioning, so the lab is well within the $50/day cost guardrail (~$25/day during the free window).

---
*Stage 1 locked — awaiting Jose gate.*
