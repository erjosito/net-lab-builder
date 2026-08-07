# TP-SQ reachability and fault evaluation

**Executed:** 2026-08-07  
**Topology:** US12 variant N, four sides and no diagonals  
**Final state:** all faults restored; all six VPN connection objects `Connected`

## Executive verdict

The current square is a valid **transport topology**, but it is not a working **transit topology**
for the requested spoke services.

- DC1↔DC2 works over S-D.
- Hub1↔Hub2 hub-address-space traffic works over global VNet peering.
- Cross-hub spoke-to-spoke, Spoke A↔DC1, Spoke A↔DC2, and DC1↔Spoke B do not work.
- Losing S-A leaves the independent DC1↔DC2 DCI working, but does not provide DC1 access to
  Spoke B.
- Losing S-D partitions DC1 from DC2; the Azure sides do not replace the DCI.

Therefore both requested fault outcomes are **unsupported by variant N**. The failures are not
convergence failures: the necessary routes are absent before the fault.

## Normal-condition matrix

| Flow | Result | Evidence / reason |
|---|---|---|
| Spoke A ↔ Spoke B | **FAIL** | Spoke B→Spoke A returned TTL exceeded from NVA2. Each spoke has only a default UDR to its local NVA; global hub peering is non-transitive and carries neither spoke prefix |
| Spoke A ↔ DC1 | **FAIL** | DC1→Spoke A failed. `vpngw-hub1` advertises an empty route set to its DC1 peer, so DC1 has no return route to Spoke A |
| Spoke A ↔ DC2 | **FAIL** | DC2 receives no Spoke A route; Hub1→DC2 cannot become a bidirectional service without a return advertisement |
| DC1 ↔ Spoke B | **FAIL** | Failed before and during both faults; `vpngw-hub2` advertises an empty route set to DC2, and the DCI cannot carry a route it never receives |
| DC1 ↔ DC2 | **PASS** | Bidirectional ICMP, 0% loss, about 27–30 ms |
| Hub1 NVA ↔ Hub2 NVA | **PASS** | Bidirectional ICMP over global VNet peering, 0% loss, about 30–35 ms |

### Control-plane findings

1. Both hub VPN gateways returned `value: []` from `list-advertised-routes` toward their site peers.
2. `allowBranchToBranchTraffic=true` does not make these VNet-to-VNet gateway pairs advertise
   NVA/Route Server learned spoke summaries.
3. Route Server does not advertise an NVA route equal to or longer than the VNet address space.
   Microsoft documents using a shorter supernet for route injection. The tested bounded `/23`
   summaries were accepted by Route Server, but still were not exported by the hub VPN gateways to
   the simulated sites.
4. The original NVA export filter reflected site routes back to Route Server after deleting ASN
   65515. That created shorter iBGP copies at the gateway and forwarding recursion. The live NVA
   policy now exports only the default plus its bounded local-spoke supernet and rejects all
   gateway/site-learned routes.

## Fault F-S-A — DC1↔Hub1 regional-side loss

**Injection:** changed the PSK on one S-A connection object and invoked the documented
`resetconnection` operation on both directional objects.

| Check | During fault |
|---|---|
| S-A status | One directional object reached `Unknown` |
| DC1↔DC2 | **PASS**, 0% loss over S-D |
| DC1→Spoke B | **FAIL**, 100% loss |

**Verdict:** the DCI is independent of S-A, but the proposed regional-outage service objective
“DC1 retains access to Hub2 spokes” is unsupported.

**Restoration:** set a fresh matching PSK on both S-A objects, reset both, and waited until both
returned `Connected`.

## Fault F-S-D — on-premises partition

**Injection:** changed the PSK on one DCI connection object and reset both S-D objects.

| Check | During fault |
|---|---|
| S-D status | One directional object reached `Unknown` |
| DC1↔DC2 | **FAIL**, 100% loss |
| DC1→Spoke B | **FAIL**, 100% loss |

**Verdict:** the Azure hub sides do not substitute for a failed DCI. This fault condition is also
unsupported by variant N.

**Restoration:** set a fresh matching PSK on both S-D objects, reset both, and verified both
returned `Connected`; DC1↔DC2 returned to 0% loss.

## Configuring the two Hub1→DC2 path preferences

These are target designs, not capabilities delivered by the current native square.

### Preference A — Azure-first

Desired path:

```text
Hub1/Spoke A → NVA1 → inter-hub overlay → NVA2/Hub2 → S-C → DC2
```

Required configuration:

1. Keep global VNet peering as the underlay.
2. Build redundant GRE/IPsec or VXLAN tunnels between regional NVAs.
3. Establish NVA1↔NVA2 eBGP over the overlay.
4. Exchange only approved spoke and site prefixes; reject `0/0`.
5. Remove ASN 65515 before re-advertising remote-region routes to the local Route Server.
6. Use local preference or AS-path prepending so the overlay copy of `10.50.0.0/16` is preferred
   over the copy learned through DC1/S-D.
7. Ensure the real site router receives the spoke return summaries. The present
   Azure-gateway-to-Azure-gateway simulation does not provide that advertisement and should be
   replaced by controllable site routers/NVAs for this test.

This is the Microsoft multi-region Route Server pattern. Encapsulation is required because
advertising a remote prefix back into the local Route Server otherwise programs the NVA itself as
next hop and creates a self-recursive route.

### Preference B — on-premises-first

Desired path:

```text
Hub1/Spoke A → S-A → DC1 → S-D → DC2
```

Required configuration:

1. Keep the DC1-learned route to `10.50.0.0/16` preferred at Hub1.
2. If an NVA overlay also exists, prepend or lower local preference on the overlay copy of the
   DC2 prefix.
3. Advertise a bounded Spoke A return summary from Hub1 toward DC1, and propagate it across S-D to
   DC2.
4. Apply the reciprocal policy for Spoke B when DC1 must reach Hub2 workloads.
5. Use distinct site ASNs and deny default-route propagation.

In a production hybrid network, the enterprise routers provide steps 3–4. In this lab, the
simulated sites are Azure VPN gateways, and the hub gateway advertised-route API returned an empty
set. To test this preference faithfully, replace each simulated site gateway with a router/NVA (or
use actual on-premises/ExpressRoute routing) where import/export policy is controllable.

### Selection rule

| Customer priority | Recommended preference |
|---|---|
| Keep traffic in Azure and minimize dependence on the DCI | Azure-first overlay |
| Treat the enterprise WAN as the authoritative inter-site path | On-premises-first |
| Require either path to survive independently | Deploy both and use explicit BGP preference plus failure-driven withdrawal; variant N alone is insufficient |

## Evidence

- Normal state: `show-output/new/square-faults/normal/`
- NVA policy investigation: `show-output/new/square-faults/policy-fix/`
- S-A fault: `show-output/new/square-faults/fault-sa/`
- S-D fault: `show-output/new/square-faults/fault-sd/`
- Final restored state: `show-output/new/square-faults/restored/`

No PSK was written to evidence or source control.
