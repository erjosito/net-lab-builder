# Reproduction fidelity contract

**Updated:** 2026-11-24 after reading the latest email and its quoted history
through WorkIQ, in addition to the six screenshots supplied in this session.
This is sanitized technical synthesis, not an email archive. Earlier embedded
diagrams were not inspected through WorkIQ. Unknown settings stay unknown.

## Required matches

| Property | Customer evidence | Lab requirement |
|---|---|---|
| Azure platform | Active-active VNet VPN Gateway, not Virtual WAN | Use the prepared VNet gateway resources; no vWAN substitution |
| Gateway SKU | Not established by supplied evidence | Use user-requested `VpnGw1AZ`; label it a test choice, not a confirmed customer match |
| Private underlay | Functioning real ExpressRoute private peering | Dedicated ER circuit through Megaport/GCP Partner Interconnect; peering or Internet-only emulation is insufficient |
| Private IPsec | Two tunnels, one to each private Azure gateway instance endpoint | Both must carry encrypted payload with independent default-address BGP adjacencies |
| Internet backup | A third tunnel on the same on-premises device | Configure exactly one Internet IPsec child/tunnel and one APIPA adjacency in the primary reproduction |
| Device identity | Private and public VPNs terminate on the same device | One Linux CPE, one FRR routing instance and shared forwarding table; do not hide interaction behind separate VMs or VRFs |
| Device implementation | Palo Alto PA-5410; PAN-OS version unknown | Approved Linux StrongSwan/FRR substitution only; no claim to reproduce PAN-OS session handling |
| Azure custom peers | Primary `169.254.21.2`, secondary `169.254.22.2` | Configure both on the gateway and map the Internet connection correctly; activate only the customer-like Internet endpoint on the CPE |
| CPE custom peer | `169.254.21.1` | Use that Internet BGP source and initiate APIPA BGP from the CPE |
| BGP ASNs | Azure `65515`, CPE `64513` in screenshots | Preserve these overlay ASNs; provider/GCP underlay ASNs remain distinct |
| Internet connection | Public Azure outer endpoint, BGP/custom address enabled, IKEv2, default IPsec policy, DPD 45 seconds | Match these effective properties; capture the negotiated proposal rather than asserting it matches PAN-OS |
| Connection mode | Default, then ResponderOnly during troubleshooting | Default for primary reproduction; ResponderOnly is a separate comparison, not a BGP initiation fix |
| Prefix preference | Private AS path has one CPE ASN occurrence; Internet has three | Reproduce total path length of three on backup, meaning two additional prepends, not three additional prepends |
| History | Existing static Internet VPN; private BGP introduced; Internet static routes removed; second private tunnel added; Internet BGP conversion attempted | Preserve the existing Internet connection through that sequence instead of replacing it with a fresh BGP connection |
| Failure/rollback | Enabling backup BGP reportedly interrupts primary traffic; disabling it reportedly restores traffic | Collect before/during/after traffic and BGP evidence; first rollback disables backup BGP without rebuilding the gateway or changing PSKs |

Azure's active-active connection model exposes two Internet endpoint
possibilities. Configuring two custom addresses in Azure does **not** make two
working Internet tunnels mandatory for this customer's three-tunnel topology.
The unused instance must be identified in assertions, not counted as a failure.
A later four-tunnel control is optional and cannot replace the three-tunnel test.

The connected APIPA row in the supplied capture corresponds to the gateway
instance with the higher default address. Discover the new gateway's
instance/IP-configuration mapping and record which endpoint is selected;
do not hardcode the customer's dynamically assigned default addresses.

## Primary sequence and acceptance gates

Run each bounded scenario under the live-lab policy. Save the original
configuration before mutation, verify the clean baseline, preserve decisive
evidence before restore, and stop on a failed gate. Do not silently run this
entire sequence under one expired or repeatedly renewed lease.

1. **Legacy Internet baseline.** Create the Internet connection with BGP
   disabled and static workload prefixes. Establish one Internet IPsec tunnel
   and bidirectional payload. Record LNG address prefixes, connection identity,
   gateway mapping, IPsec SAs and CPE routing.
2. **Private migration.** Bring up the first private IPsec/default-BGP path.
   Record coexistence with legacy static routing before removing the conflicting
   Internet static prefixes. Verify the resulting private encrypted payload,
   then establish the second private path and prove both private paths work.
   Keep the same Internet connection and its single established tunnel.
3. **Customer-like enablement.** Snapshot the healthy two-private-path state.
   On the existing Internet objects, configure CPE APIPA, Azure custom-address
   mapping and BGP, then initiate BGP from the CPE. Keep PSKs and IPsec
   configuration unchanged during this enablement. Record any platform-driven
   SA churn; do not claim the SAs remained unchanged unless observed.
4. **Disruption and minimal rollback.** Capture all TCP/179 on each tunnel
   without filtering exclusively on a default or APIPA address. Record exact
   tuples, BGP uptime and updates/notifications, source-aware FIB lookups, both
   best paths, IPsec counters and bidirectional payload. If traffic breaks,
   disable Internet BGP and verify whether private traffic recovers without
   gateway reset, tunnel replacement or PSK synchronization.
5. **Full-ER failover and failback.** Only after coexistence works, interrupt
   the dedicated ER transport while retaining Internet. Prove payload switches
   to the one public tunnel, measure convergence, restore ER and prove private
   preference returns. Never use an existing demo's MCR/VXC for fault injection.

Static-vs-BGP preference and a route to an IKE/BGP endpoint must not be conflated.
Capture both: the former can change workload forwarding with BGP still up;
the latter can break or misdirect a control session.

## Controls, not substitutes for the primary sequence

Only after a baseline is restored, use separately scoped comparisons:

- Fresh APIPA connection versus in-place static-to-BGP enablement.
- Default versus ResponderOnly IKE connection mode.
- CPE route/source-binding changes, after capturing the original behavior.
- SA re-establishment, only after preserving the failing state and approving
  the bounded comparison.
- Two Internet tunnels rather than one, if required to isolate instance behavior.

Explicit peer host routes and import/export filters belong in the safe lab
configuration. If the customer's actual configuration differs, document that
delta and investigate it as a separate variable. Do not silently "fix" suspected
customer routing before collecting the reproduction evidence.

## Known differences and missing information

The chosen region, `VpnGw1AZ`, small workload VMs, Megaport/GCP transport,
translated lab prefixes and StrongSwan/FRR are test choices. The email does not
establish matching customer gateway SKU, region, provider, PAN-OS version,
gateway software rollout, actual negotiated proposals, route filters, VRF/
virtual-router arrangement, NAT policy, HA behavior or full effective resource
JSON. Do not invent these values.

Keep the approved Linux first pass. If it passes without reproducing the
outage, the next fidelity decision is a supported Palo Alto VM-Series
comparison or customer-assisted captures, not a conclusion that the customer's
problem is resolved. A VM-Series test still would not match PA-5410 hardware
or an unknown PAN-OS release exactly.

## Deployment gate

This contract guides subsequent tunnel configuration and validation. The
current Terraform source creates foundations only; it does not yet implement
the IPsec connections, FRR peers or the migration sequence above.
Do not label the lab customer-matched or ready until these gates are executed
and all remaining deviations are stated in the result.
