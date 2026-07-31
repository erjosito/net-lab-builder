# vwan-routemap-summarization — manifest

← Back to [README.md](README.md) | Results: [validation.md](validation.md) | Design: [design-phase3.md](design-phase3.md)

## 0. Gate discipline

Ephemeral lab. Resource group `routemap-test-rg` in subscription `<SUBSCRIPTION_ID>`. Teardown is a
single `az group delete` and requires user sign-off (routing rule #12).

## 1. Lab summary

Reproduce an order-dependent missing-summary bug in Virtual WAN outbound summarization route-maps.
Two European hubs carry identical `summarize-out` rule sets; the customer observed one hub dropping a
single /16 or /17 summary depending on rule order, and reordering the rule for the missing prefix to
the top "fixed" it — which does not inspire confidence and points at a possible platform bug.

## 2. Scope and non-goals

### In scope

- 3-hub VWAN (1 US route source + 2 EU VPN hubs).
- 12 US spoke VNets producing 48 contributing /24 routes across 6 summary blocks.
- 2 Ubuntu NVAs (StrongSwan XFRM + BIRD) simulating on-prem, one per EU hub.
- Outbound summarization route-maps on both EU hubs; inbound AS-path prepend on hub-eu2.
- Control-plane analysis only (outbound routes per connection + BIRD RIB on the NVAs).

### Out of scope

- Data-plane traffic tests (no workload VMs — the bug is control-plane).
- GCP on-premises side: Phase 2 GCP VPN sites (`site-gcp1/2`, `cx-gcp1/2`) are deployed but no
  GCP endpoint was configured; ER circuits carry no routes. Phase 2 infrastructure validation
  confirms connectivity resources; repro focused on the EU VPN→route-map path.
- Gate D (concurrent-churn): designed but not yet run — see [design-phase3.md](design-phase3.md).

## 3. Topology and diagram description

```
                 12 spoke VNets (48x /24, 6 summary blocks)
                             |
                        [ hub-us ]  westus2  192.168.0.0/23
                          /       \
              inter-hub (branch-to-branch, +65520 65520)
                        /            \
   🔒 [ hub-eu1 ] swedencentral    🔒 [ hub-eu2 ] westeurope
      192.168.2.0/23                  192.168.4.0/23
      AzFW Standard + RI Private      AzFW Standard + RI Private
      vpngw-eu1  ASN 65515            vpngw-eu2  ASN 65515
      summarize-out (6 rules)         summarize-out (6 rules) + prepend-in
           |  IPsec+BGP                    |  IPsec+BGP
      [ nva1 ] 10.200.0.4            [ nva2 ] 10.201.0.4
      ASN 65001 (on-prem sim)        ASN 65002 (on-prem sim)
      advertises 14x /16              advertises 14x /16
      (172.16.0.0/16 .. 172.29.0.0/16)
```

See `diagrams/01-topology.drawio`.

## 4. Region decision

`swedencentral` and `westeurope` chosen for the EU hubs because `Standard_B2ts_v2` capacity and VPN
gateway capacity were confirmed available there at preflight — deliberately avoiding North Europe,
where the customer hit VPN gateway capacity issues.

## 5. Resource inventory

| Resource | Name(s) | Region | Phase |
|----------|---------|--------|-------|
| Virtual WAN | `vwan-routemap` | global | 1 |
| Virtual hubs | `hub-us`, `hub-eu1`, `hub-eu2` | westus2 / swedencentral / westeurope | 1 |
| Spoke VNets | `spoke-us-{a,b,c,d,e,f}` + `spoke-us-{a,b,c,d,e,f}2` (12) + 6 scale VNets | westus2 | 1 |
| VPN gateways | `vpngw-eu1`, `vpngw-eu2` (ASN 65515) | swedencentral / westeurope | 1 |
| VPN sites (on-prem) | `site-onprem1`, `site-onprem2` | — | 1 |
| VPN connections (on-prem) | `cx-onprem1` (eu1), `cx-onprem2` (eu2) | — | 1 |
| NVAs | `nva1`, `nva2` (Ubuntu 24.04, B2ts_v2) | swedencentral / westeurope | 1 |
| Route maps | `summarize-out` (eu1, eu2), `prepend-in` (eu2) | — | 1 |
| ExpressRoute circuits | `er-eu1`, `er-eu2` (Standard) | swedencentral / westeurope | 2 |
| ExpressRoute gateways | `ergw-eu1`, `ergw-eu2` | swedencentral / westeurope | 2 |
| ER connections | `conn-er-eu1` (ergw-eu1), `conn-er-eu2` (ergw-eu2) | — | 2 |
| VPN sites (GCP) | `site-gcp1`, `site-gcp2` | swedencentral / westeurope | 2 |
| VPN connections (GCP) | `cx-gcp1` (vpngw-eu1), `cx-gcp2` (vpngw-eu2) | — | 2 |
| Private endpoint | `kv-pe` (Key Vault) | swedencentral | 2 |
| Firewall Policy | `azfwpol-routemap-lab` (Standard) | swedencentral | 3 |
| Azure Firewalls | `azfw-eu1`, `azfw-eu2` (Standard, AZFW_Hub SKU) | swedencentral / westeurope | 3 |
| Routing Intent | `hub-eu1-ri`, `hub-eu2-ri` (PrivateTraffic) | swedencentral / westeurope | 3 |

Full live inventory as of 2026-07-30: `show-output/08-phase3-audit-resource-inventory.txt`.

## 6. Scenario walkthroughs

### Scenario 1 — Baseline (no route-map)

Both NVAs establish 2 IPsec SAs and 2 BGP sessions each, receive ~91 networks including the 48 US
contributing /24s. US VNet routes carry AS_PATH `65515 65520 65520` (hub ASN + double inter-hub
prepend). Evidence: `show-output/02`, `03`, `04`.

### Scenario 2 — Outbound summarization applied

Apply `summarize-out` to both EU VPN connections. Expected: each NVA receives the 6 summaries
(`10.0.0.0/16`, `10.1.0.0/16`, `10.2.0.0/16`, `10.3.0.0/16`, `10.4.0.0/17`, `10.4.128.0/17`) in place
of the 48 contributing /24s. Repro check: compare `get-outbound-routes` on both connections — does
either hub drop a summary?

### Scenario 3 — Rule reorder + failover

Reorder rules (move a summary to first position) and repeat. Then failover: disable the primary
connection, verify the secondary carries all summaries, fail back, and re-check both hubs for a
missing summary. This mirrors the exact customer procedure that surfaced the bug.

**Phase 2 NVA note (operational):** After VM deallocation/restart, NVAs require manual steps to
restore IPsec and BGP: `swanctl --load-all`, `swanctl --initiate --child s2sX --ike vngX`, and
XFRM interface recreation (`ip link add xfrm41 type xfrm dev eth0 if_id 41; ip link set xfrm41 up;
ip route add 192.168.4.12/32 dev xfrm41` — similarly for xfrm42/if_id 42). XFRM interfaces are
not persisted across reboots. See `show-output/12` for full sequence. **Action for Tank:** add a
systemd oneshot service to recreate XFRM interfaces on boot.

## 7. Validation plan

- **Layer 1a** (Azure control plane): hub secured state, RI state, route-map Succeeded, defaultRouteTable diff.
- **Layer 1b** (outbound routes CLI): `az network vhub route-map get-outbound-routes` — **⚠️ non-functional
  for secured hubs in swedencentral/westeurope (HTTP 404, preview API gap)**. See
  [show-output/17](show-output/17-phase3-gate-a-l1b-get-outbound-routes-api-limitation.txt) and
  [show-output/29](show-output/29-gate-a-full-get-outbound-routes-api-gap.txt). Use Layer 2 BIRD instead.
- **Layer 2** (on-prem RIB — **authoritative**): `birdc show route` on both NVAs via
  `az vm run-command` — count 6 summaries, confirm 0 /24 leaks in customer prefix space.

Full per-gate measurement checklists with evidence links: [validation.md](validation.md).

## 8. Cleanup chain

1. Delete route maps (optional — folded into RG delete).
2. `az group delete -n routemap-test-rg` (removes VWAN, hubs, gateways, NVAs, VNets).

Gateways dominate teardown time (~20–40 min each). Requires user sign-off.
