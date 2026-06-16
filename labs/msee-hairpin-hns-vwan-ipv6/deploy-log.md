# Deploy Log — msee-hairpin-hns-vwan-ipv6

**Date:** 2026-06-16
**Path:** A (ER Direct, single circuit, MSEE hairpin)
**Region:** swedencentral
**RG:** `rg-msee-hairpin-hns-vwan-ipv6-60536c`
**Correlation ID:** `60536c`

## Resource Inventory

| Resource | Name | State |
|----------|------|-------|
| ER Direct Port (10G) | erp-hairpin-60536c | Succeeded |
| ER Circuit (Local/Metered, 1G) | er-hns-60536c | Enabled |
| HnS Hub VNet (dual-stack) | vnet-hns-hub-60536c | Succeeded |
| HnS Spoke VNet (dual-stack) | vnet-hns-spoke-60536c | Succeeded |
| HnS ER GW (ErGw1AZ) | ergw-hns-60536c | Succeeded |
| HnS ER Connection (circuit 1) | conn-hns-60536c | Succeeded |
| vWAN | vwan-hairpin-60536c | Succeeded |
| vHub (Standard) | vhub-hairpin-60536c | Succeeded |
| vHub ER GW (1 scale unit) | ergw-vhub-60536c | Succeeded |
| vHub ER Connection (same circuit!) | conn-vhub-er-60536c | Succeeded |
| vWAN Spoke VNet (dual-stack) | vnet-vwan-spoke-60536c | Succeeded |
| vHub→Spoke Connection | conn-vhub-vnet-60536c | Succeeded |
| HnS VM | vm-hns-60536c | Running |
| vWAN VM | vm-vwan-60536c | Running |

## Key Design Decision: Single Circuit

MSEE hairpinning requires connecting the **same circuit** to both ER gateways.
The MSEE reflects routes between the two connections on that single circuit.
Two circuits (as initially designed) would NOT hairpin, since each circuit has
its own independent MSEE peering session.

## Three Silent-Fail GW Toggles (all applied)

| Gateway | Property | Value | Verified |
|---------|----------|-------|----------|
| HnS ER GW | allowVirtualWanTraffic | true | ✅ |
| HnS ER GW | allowRemoteVnetTraffic | true | ✅ |
| vHub ER GW | allowNonVirtualWanTraffic | true | ✅ |

Applied via `azapi_update_resource` (not yet native in azurerm 4.x for VNet GWs).

## BGP Status

HnS ER GW has 2 BGP peers (MSEE primary + secondary, ASN 12076) in Connected state.

**Learned routes on HnS ER GW:**
- `10.3.0.0/23` via MSEE (AS-path: 12076-12076) — vHub address space
- `10.4.0.0/24` via MSEE (AS-path: 12076-12076) — vWAN spoke
- `fd00:1::/48`, `fd00:2::/48` — locally originated (HnS hub + spoke)

**Effective routes on vWAN spoke NIC:**
- `10.1.0.0/16` via VirtualNetworkGateway — HnS hub (hairpin working!)
- `10.2.0.0/24` via VirtualNetworkGateway — HnS spoke (hairpin working!)

## Connectivity Test Results

| Direction | Protocol | Result | RTT |
|-----------|----------|--------|-----|
| HnS→vWAN (10.2.0.4→10.4.0.4) | IPv4 ICMP | ✅ 3/4 (75%) | 9-17ms |
| vWAN→HnS (10.4.0.4→10.2.0.4) | IPv4 ICMP | ✅ 4/4 (100%) | 9-11ms |
| HnS→vWAN (fd00:2::4→fd00:4::4) | IPv6 ICMP | ❌ 0/4 | N/A |
| vWAN→HnS (fd00:4::4→fd00:2::4) | IPv6 ICMP | ❌ 0/4 | N/A |

## IPv6 Finding — Root Cause Identified

IPv4 MSEE hairpinning works perfectly. IPv6 does NOT work, and the root cause
is NOT the hairpin — it is a fundamental **Azure Virtual WAN limitation: vHubs are IPv4-only.**

**Evidence chain:**
1. HnS ER GW (dual-stack) correctly advertises `fd00:1::/48` and `fd00:2::/48`
   to the MSEE — verified via `list-advertised-routes` (the HnS side does its job).
2. The vHub `defaultRouteTable` effective routes contain ONLY IPv4 prefixes:
   `10.1.0.0/16`, `10.2.0.0/24`, `10.4.0.0/24`. There is **no IPv6 at all** —
   not even the vWAN spoke's own `fd00:4::/48`.
3. The vWAN spoke VM has its IPv6 address (`fd00:4::4`) and a route only to its
   own `/64`; it has no route to `fd00:2::/48`.

**Conclusion (GA, June 2026):** The vHub silently drops IPv6 prefixes even from its own connected
spoke. Because the vHub carries no IPv6, the vWAN ER GW has no IPv6 to advertise
to the MSEE, so the hairpin never sees vWAN IPv6 routes. The vWAN `address_prefix`
property accepts only a single IPv4 prefix; GA vHubs do not support an IPv6 address space.

**Preview status:** An Azure Virtual WAN IPv6 / dual-stack capability is reportedly
in progress with GA targeted for September 2026 (per internal aka.ms/ipv6roadmap).
As of this lab there is **no self-service feature flag** exposed in the subscription
(`az feature list --namespace Microsoft.Network` shows no vWAN-IPv6 AFEC flag), and
the public "What's new in Virtual WAN" page does not yet mention IPv6. This indicates
the preview is **private / allowlist-gated** — the subscription must be explicitly
added by the Virtual WAN product group to test it. Re-test this lab's IPv6 scenarios
once allowlist access is obtained.

**Implication for the lab goal:** With GA Virtual WAN, dual-stack MSEE hairpinning
is only achievable for IPv4. IPv6 either requires the vWAN IPv6 preview allowlist, or
an alternative such as IPsec VPN with IPv6 traffic selectors.

## Deploy Timeline

| Phase | Duration |
|-------|----------|
| ER Direct port | ~2 min |
| ER circuit | ~1 min |
| ER circuit peering (IPv4+IPv6) | ~1 min |
| HnS ER GW (ErGw1AZ) | ~30 min |
| vHub ER GW (1 SU) | ~30 min (deployed overnight) |
| HnS ER connection | ~15 min |
| vHub ER connection | ~30 min |
| GW toggles (azapi) | ~2.5 min |
| VMs | ~3 min |
| **Total** | **~2h** (with restructuring from 2-circuit to 1-circuit) |

## Cost (during 45-day free port window)

- ER Direct port: $0/day (free for 45 days)
- ER circuit (Local): ~$1/day
- HnS ER GW (ErGw1AZ): ~$10/day
- vHub (Standard): ~$6/day
- vHub ER GW (1 SU): ~$4/day
- 2x VMs (B2als_v2): ~$1/day
- **Total: ~$22/day**

## Handoff

Lab is live. Jose asked to keep it running for inspection.
IPv4 hairpin: PROVEN. IPv6 hairpin: NOT WORKING (route propagation gap).

## Teardown (2026-06-16)

Lab deleted via `terraform destroy` after Jose approved cleanup. Deletion order followed the ER Direct dependency graph: connections -> ER GWs -> circuit -> vHub/vWAN -> ER Direct port -> RG. The vHub ER connection delete hit Terraform's 30-min context deadline once (Azure left it in `Failed` state); retried the connection delete via `az network express-route gateway connection delete` (completed), then resumed `terraform destroy` to finish. Verified: RG `rg-msee-hairpin-hns-vwan-ipv6-60536c` no longer exists, no orphaned ER Direct port or circuit remain. Billing stopped.
