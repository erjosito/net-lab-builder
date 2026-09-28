# vWAN IPsec-over-ER backup - deployment log

> **Status (2026-09-28): DEPLOYED; D2 BGP baseline blocked by the frozen peer-address model.** Azure, GCP, ExpressRoute, Partner Interconnect, Megaport, and all four IPsec SAs are live. Niobe validation is stopped before fault execution.

## Deployment result

| Plane | Result |
|---|---|
| Azure | Standard vWAN and `10.240.0.0/24` vHub with `ASPath`, VPN and ExpressRoute gateways, 50-Mbps Standard Metered circuit, vHub ER connection, workload VNet connection, and `Standard_B2ts_v2` probe VM are deployed in Sweden Central |
| GCP | New isolated billing-linked project, required APIs, custom VPC, Cloud Router ASN `16550`, active Partner attachment, reserved public IP, and forwarding-enabled Ubuntu `e2-small` CPE are deployed in `europe-north2-c` |
| Megaport | 1000-Mbps MCR at Equinix Amsterdam AM1, two 50-Mbps VXCs to distinct Stockholm MSEE paths, and one 50-Mbps GCP VXC are live |
| Underlay | Both MSEE route tables learn only the CPE endpoint `/32`; GCP learns the Azure vHub and workload prefixes through the MCR |
| IPsec | Four IKEv2/ESP SAs are established: two over the ER-carried private endpoints and two over public Internet/NAT-T |
| Overlay BGP | Blocked. Azure sources both path classes from the same two default gateway BGP addresses rather than the four connection-selected custom APIPA addresses |

## Megaport fallback and commitment

Live non-billable validation was performed in distance order. Stockholm, Helsinki, Oslo, Copenhagen, Warsaw, Hamburg, and Berlin did not expose an account-usable 1000-Mbps MCR. Amsterdam was the nearest enabled metro; Equinix Amsterdam AM1 was selected because it supported the MCR, both Stockholm Azure ER endpoints, and a compatible Google endpoint.

The location change preserves Azure Sweden Central, ExpressRoute Stockholm peering, GCP `europe-north2`, product tiers, bandwidths, and topology. It adds an Amsterdam-to-Stockholm provider segment of roughly 1,100 km great-circle distance. No unsupported latency estimate is claimed.

The pre-order rack-rate quote was **EUR 991.80/month**:

| Product | Rack rate |
|---|---:|
| MCR | EUR 600.00/month |
| Azure primary VXC | EUR 135.60/month |
| Azure secondary VXC | EUR 135.60/month |
| GCP VXC | EUR 120.60/month |

The account response displayed a promotional discount, but the rack rate is retained as the conservative live commitment.

## Capacity and deployment recovery

The requested GCP `e2-small` returned explicit capacity/resource failures in `europe-north2-a` and `europe-north2-b`, then deployed successfully in `europe-north2-c`. The authorized `e2-medium` fallback was not used.

Provider and gateway operations were resumed in place rather than rebuilt. Notable corrections were:

- Windows CRLF was removed from Linux runtime files.
- The active StrongSwan service name and canonical multiline `swanctl.conf` syntax were used.
- VPN site-link connections and PSKs were applied with versioned REST API `2025-09-01` because the CLI emitted deprecated parent properties.
- StrongSwan IKE was aligned to Azure's strongest observed compatible default offer: AES-256/SHA-256 with MODP1024. ESP negotiated AES-256/SHA-256.
- Four custom Azure APIPA addresses were configured and selected on the two connection objects, exposing the provider limitation described below.

## Explicit design blocker

The frozen design requires non-APIPA CPE BGP identities `10.250.254.240` and `10.250.254.241`, four unique Azure peer tuples, and one XFRM slot per tuple. The live connection objects correctly select four custom Azure APIPA addresses, but packet capture shows Azure initiating BGP from only its two default gateway-subnet addresses on both the private and public tunnels.

This is documented Azure behavior: when the remote BGP peer uses a regular private address, VPN Gateway uses its automatically assigned gateway BGP address; the corresponding custom Azure APIPA address is used when the remote peer is APIPA. The frozen design also states that the CPE peer cannot be APIPA.

The result triggers `design.md` section 13: generated Azure BGP peer addressing cannot be routed through four distinct XFRM slots without collapsing private and public neighbor identity. No firewall relaxation, duplicate FRR neighbor, route leak, or unapproved APIPA redesign was used to bypass the stop condition.

## Current health and smoke results

- ExpressRoute provider state is provisioned and Azure private peering succeeded.
- Both primary and secondary MSEE route tables carry the expected CPE endpoint route.
- GCP Partner attachment is active and Cloud Router BGP is established.
- The MCR and all three VXCs report live/up; the Azure VXCs terminate on distinct primary and secondary Stockholm endpoints.
- Four StrongSwan connection definitions load and four IKE/ESP SAs establish.
- XFRM packet capture proves BGP SYNs arrive on each intended private/public interface, but their source addresses collapse to two Azure defaults.
- FRR remains non-established by design because accepting those two sources would violate the required four-neighbor model.
- No D1, D2 fault, D3, route-preference, failover, or restore scenario was run.

## Cost exposure

The live lab continues to incur:

- Megaport rack-rate commitment: EUR 991.80/month.
- Azure vWAN VPN gateway, ExpressRoute gateway, vHub, 50-Mbps Standard Metered circuit, VM/disk, public IP, and traffic charges.
- GCP `e2-small`, disk, reserved public IPv4, Partner attachment, and traffic charges.

VM stop schedules run daily at 23:00 Europe/Stockholm, but managed gateways, the ER circuit, Partner attachment, MCR, and VXCs continue billing. Cleanup remains separately approval-gated and was not run.

## Niobe handoff

Do not run the validation fault matrix against the current deployment. Use the ignored `config/inventory.json` only for inspection: it contains the generated IKE endpoints, effective default BGP peers, configured custom APIPA peers, versioned vHub route queries, live provider identifiers, application listeners, and reviewed fault/restore commands.

The deployment is suitable for blocker review and underlay/IPsec inspection. Scenario execution requires an approved design amendment that either pairs APIPA CPE identities with the four custom Azure addresses or changes the four-unique-neighbor requirement to the two effective gateway peers. After amendment, regenerate runtime configuration and inventory, restore a healthy overlay baseline twice, then begin `validation-plan.md`.
