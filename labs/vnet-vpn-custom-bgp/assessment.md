# Initial assessment of the reported outage

**Date:** 2026-11-24. **Status:** hypotheses from the supplied screenshots and
the latest email with quoted history retrieved through WorkIQ, not a reproduced
root cause. The Linux lab is not a PAN-OS test.

## Thread findings that change the reproduction

The latest message is a follow-up; the detailed failure report was sent four
days earlier. Earlier quoted messages suggest that private and public tunnels
terminate on the same on-premises device, and describe a prior asymmetric
forwarding problem while legacy Internet static routes remained configured.
That makes shared forwarding/peer reachability a stronger test priority.
The 2026-11-25 WorkIQ recheck found that the latest reply still requests
confirmation for all three tunnels; shared-device identity is not confirmed.

However, the quoted July report also describes unexpected default-source BGP
attempts when custom addresses were tried on the initial private VPN. The
source-address symptom therefore predates the later Internet-backup enablement.
It must not be attributed solely to converting the Internet connection.
The earlier custom addresses and complete configuration are unknown.

A September suggestion to float a single adjacency between tunnels was
explicitly withdrawn in the subsequent reply. Dedicated per-transport peers
were selected instead. Do not revive the superseded suggestion as a supported
fix, or treat the prior vWAN lab as validation of this VNet gateway deployment.

The primary reproduction now follows the customer's migration sequence and
exactly three active tunnels. A fresh APIPA connection is a comparison, not the
primary test. See the [fidelity contract](customer-fidelity.md).

## Bottom line

I would first investigate **peer reachability and bidirectional route selection
when the Internet BGP session is enabled**, rather than conclude that Azure
simply ignores all custom BGP addresses. A platform source-address or
configuration-programming defect remains possible, but the screenshots do not
isolate it.

The strongest clues are that the Internet APIPA peer is shown **Connected with
168 routes**, and the existing private peer is also **Connected with an uptime
of approximately 17 days**, while the Internet peer has approximately 14 minutes.
At that captured instant, the evidence is not a complete loss of both BGP
adjacencies. A traffic outage with established BGP is entirely possible.

## What the evidence does and does not establish

| Observation | Interpretation |
|---|---|
| VNet VPN Gateway, two default local BGP addresses | This is an active-active VNet gateway. Prior vWAN results are background, not proof for this platform. |
| Internet connection selects custom Azure APIPA addresses | This is the intended connection-level setting. Complete effective gateway and local-network-gateway configuration is still missing. |
| APIPA peer Connected and receiving routes | At least one route-exchanging adjacency to that peer is reported. This contradicts a blanket claim that Internet BGP never established. It does not identify its actual local TCP address. |
| Private peer has much longer connected uptime | That private adjacency was not newly re-established in the captured interval. The reported outage may involve forwarding or another instance, rather than loss of this session. Timing relative to the outage is unknown. |
| Palo Alto logs show default-source TCP/179 | Real evidence of traffic involving the default address, but not proof that no APIPA traffic exists. The screenshot's filter explicitly selects the default address, excluding APIPA-only exchanges. |
| Session end reason is server-side reset | Investigate why the receiving CPE rejected/reset those sessions. A traffic-log record is not a packet capture of the BGP OPEN/NOTIFICATION exchange. |
| Azure route export displays the default local address | That field alone does not establish the on-wire TCP source. Do not assume it is either accurate per-session telemetry or merely a cosmetic bug without comparing packet captures. |
| Internet AS path has three CPE ASN occurrences; private has one | Outbound prepending appears intended to prefer private on Azure. It does not establish the CPE's preference for Azure routes in the reverse direction. |
| ResponderOnly did not help | Expected if the problem is BGP or routing: connection mode controls IKE initiation, not which BGP peer initiates TCP. |

## Investigation priority

### 1. Shared peer reachability or recursive routing

The same Azure gateway instances serve both underlays. Adding Internet VPN can
change which tunnel reaches a default Azure BGP address or a covering prefix.
Replies to private BGP might then leave through Internet, or vice versa.
This is a plausible explanation for enabling the backup disrupting a primary.
It is a hypothesis, not a demonstrated property of this Palo Alto configuration.

Check exact CPE FIB lookups, including source address and tunnel interface, for
every default and APIPA peer before and after the change. Pin each peer to its
intended IPsec tunnel, and keep public/private IKE endpoints out of overlay
recursion. Inspect actual ingress/egress tunnel captures and the CPE's BGP
local-address settings. Do not infer the path from an aggregate route alone.

### 2. Forwarding changes without private BGP failure

The longer-lived private session makes this especially important. A new
Internet route can win on the CPE, create unexpected ECMP, or change the return
path while Azure continues preferring private. AS-path prepending on routes
advertised to Azure only controls one direction of preference.

Compare both routing tables and actual payload paths. Use explicit import
preference for private on the CPE and an independently verified export policy
toward Azure. Check firewall drops and session handling if the paths change.
Also exclude a cleartext ER route winning over the encrypted overlay.

### 3. Effective configuration or instance mapping mismatch

Validate all three Azure object layers, not just the portal connection:

- Gateway `bgpSettings.bgpPeeringAddresses`: custom addresses assigned to the
  correct gateway IP configurations.
- Internet local network gateway: CPE ASN and APIPA `bgpPeeringAddress`.
- Internet connection: BGP enabled, expected local network gateway referenced,
  and correct `gatewayCustomBgpIpAddresses` entries with matching
  `ipConfigurationId` values. Private connection must retain its distinct
  ordinary CPE peer and private outer endpoint selection.

Check persisted resource JSON after provisioning succeeds. Verify which
instance corresponds to each default and custom address. Only one public
tunnel may be configured on the CPE even though the Azure connection exposes
two instance endpoints; do not treat the unused instance as a platform failure.

### 4. APIPA initiation, multihop, or CPE peer acceptance

Microsoft requires the CPE to initiate APIPA BGP. Confirm a SYN sourced from
the intended CPE APIPA to the intended Azure APIPA on the intended tunnel,
then SYN-ACK, BGP OPEN and route updates. Confirm CPE peer source binding,
reachability and any required eBGP multihop configuration.

Unexpected default-source attempts might be rejected alongside a different
working session. Conversely, they might expose an incorrect binding. Capture
both source families rather than filtering only the unexpected address.
Do not treat ResponderOnly as a BGP-passive setting.

### 5. Azure listener activation or source-address defect

This becomes the leading explanation only after the effective configuration,
peer routes, session initiation and policies are correct and captured.
Distinguish a newly created APIPA connection from enabling BGP on an existing
static Internet connection with already-established IPsec SAs.

The related vWAN lab recorded a custom-peer reactivation issue after changing
routing modes while keeping SAs established. That is a reason to compare
fresh-create versus in-place enablement here, not evidence that VNet VPN Gateway
has the same defect. Any tunnel restart comparison must be a separate bounded
scenario, not an unrecorded attempt that destroys the failing evidence.

## Decisive lab outcomes

1. Establish two private default-address adjacencies, private best paths and
   bidirectional encrypted payload.
2. Enable APIPA BGP in place on the existing, formerly static Internet
   connection, preserving exactly one Internet tunnel and the two private
   tunnels. Use explicit CPE initiation and independent peer routes. Collect
   all TCP/179 traffic, exact established tuples, both route tables, IPsec
   counters and payload results.
3. From a separately restored baseline, compare this with fresh APIPA
   configuration if needed. Do not replace the customer-like sequence with
   the simpler clean-create case.
4. If adding backup breaks forwarding, capture whether private BGP actually
   withdraws, whether routes change without withdrawal, or whether the CPE
   rejects an unexpected peer. Restore the saved baseline promptly.
5. From a healthy coexistence baseline, fail the dedicated ER transport, prove
   Internet takeover with payload, restore ER and prove failback. Record
   convergence rather than promise an unmeasured recovery interval.

An Azure-only source-address failure with a correct Linux CPE supports platform
escalation with packet evidence, effective configuration and timestamps.
A successful Linux test narrows the issue but does not exonerate Azure for the
customer's gateway version or establish a Palo Alto defect.

## References

- [Azure BGP configuration and APIPA initiation](https://learn.microsoft.com/en-us/azure/vpn-gateway/configure-bgp)
- [BGP multiple-tunnel behavior](https://learn.microsoft.com/en-us/azure/vpn-gateway/vpn-gateway-bgp-overview)
- [Connection API properties](https://learn.microsoft.com/en-us/azure/templates/microsoft.network/connections)
- [IPsec over ER and cleartext route precedence](https://learn.microsoft.com/en-us/azure/vpn-gateway/site-to-site-vpn-private-peering)
- [Different-platform vWAN observations](../vwan-ipsec-over-er-backup/README.md)
