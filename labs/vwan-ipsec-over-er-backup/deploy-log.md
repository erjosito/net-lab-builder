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
- Four custom Azure APIPA addresses were configured and selected on the two connection objects, exposing the configuration/API association question described below.

## Explicit design blocker

The frozen design requires non-APIPA CPE BGP identities `10.250.254.240` and `10.250.254.241`, four unique Azure peer tuples, and one XFRM slot per tuple. The live connection objects correctly select four custom Azure APIPA addresses, but packet capture shows Azure initiating BGP from only its two default gateway-subnet addresses on both the private and public tunnels.

This is documented Azure behavior: when the remote BGP peer uses a regular private address, VPN Gateway uses its automatically assigned gateway BGP address; the corresponding custom Azure APIPA address is used when the remote peer is APIPA. The frozen design also states that the CPE peer cannot be APIPA.

The result triggers `design.md` section 13: generated Azure BGP peer addressing cannot be routed through four distinct XFRM slots without collapsing private and public neighbor identity. No firewall relaxation, duplicate FRR neighbor, route leak, or unapproved APIPA redesign was used to bypass the stop condition.

### Bounded APIPA correction attempt

One authorized correction was applied without gateway recreation or IPsec changes. The private site remained on CPE peer `10.250.254.240`; the public site changed to `169.254.22.1`; the public connection selected Azure custom peers `169.254.22.2/.3`; and the CPE received the required APIPA loopback, XFRM host routes, FRR neighbors, and filters.

Azure persisted all requested values and all four IKE/ESP SAs remained established. The acceptance gate still failed: public XFRM captures showed TCP/179 sourced from `10.240.0.12/.13`, while `169.254.22.2/.3` remained in Connect with no received messages. The attempt was stopped without retry.

The public connection, public site, CPE state, and newly added gateway custom addresses were restored. Post-rollback checks confirmed four established SAs, ExpressRoute provider provisioning, Azure private peering, GCP Partner BGP, and the original neighbor definitions.

### Authorized retry after local GSA disablement

One clean repeat used only the corrected successful operation forms from the first attempt. The local WSL GSA warning was absent and Azure/GCP authentication, DNS and REST operations succeeded. All four SAs remained established.

After the same 60-second convergence window, both private peers `10.240.0.12/.13` were established, but public custom peers `169.254.22.2/.3` remained Connect with zero messages. Captures on all four XFRM interfaces again showed public TCP/179 sourced from Azure defaults `.12/.13` toward CPE APIPA `169.254.22.1`.

The retry was rolled back once. Azure and CPE mappings returned to the pre-retry state, four SAs remained established, provider paths remained healthy, and a full authenticated Terraform plan reported no changes. Disabling local GSA changed the WSL warning only; it did not change the observed session outcome.

This result is not classified as a vWAN platform limitation. Custom APIPA is intended for remote APIPA-only devices, and the retry persisted the intended gateway, site-link and connection-link values. CPE SYNs reached `.22.2/.3` without SYN-ACK or RST while Azure independently initiated from `.12/.13`. The configuration/API association is unresolved pending Trinity review. Full active-state GET bodies were not captured before rollback; a later explicit-version full GET records only the restored closure state. No further retry or Niobe fault validation is authorized.

### D1 interpretation correction

D1 is separate from the D2 custom-APIPA investigation. It requires no custom APIPA peer: one normal CPE loopback and one Azure default vWAN BGP neighbor retain the same tuple while only the Azure-neighbor `/32` route moves between the ER/private and Internet/public XFRM paths. Existing APIPA captures remain preserved as D2 evidence and are not negative evidence for D1. D1 was not run and remains blocked pending Trinity's corrected recipe.

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

The deployment is suitable for blocker review and underlay/IPsec inspection. D2 scenario execution requires an approved amendment resolving the custom-peer association or changing the four-unique-neighbor requirement. D1 is an independent ordinary-peer `/32` movement experiment and must await Trinity's corrected recipe. After the applicable amendment, regenerate runtime configuration and inventory, restore a healthy overlay baseline twice, then begin `validation-plan.md`.
