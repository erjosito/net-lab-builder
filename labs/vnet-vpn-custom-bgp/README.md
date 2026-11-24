# VNet VPN custom BGP coexistence

## Objective

Reproduce the coexistence of two active-active IPsec paths over ExpressRoute
using default Azure BGP addresses and Internet backup using custom APIPA peers.
Use Linux StrongSwan/FRR to isolate Azure behavior. This is not a PAN-OS
reproduction and cannot establish a Palo Alto-specific root cause.

The supplied screenshots identify a VNet VPN Gateway, not Virtual WAN.
They show a connected APIPA peer with received routes while the local address
column and Palo Alto traffic logs show the default Azure address. These are
observations, not proof of the cause of the reported forwarding outage.
`ResponderOnly` controls IKE initiation, not BGP initiation.

## Reported problem and evidence

The requested production pattern is two active-active private IPsec tunnels
over an existing ExpressRoute, plus a third Internet tunnel for automatic
backup. Previously, Internet VPN used static routing. Adding the first
private BGP path required removing those static routes. The second private
tunnel now works, but enabling BGP on Internet backup reportedly interrupts
the private path; disabling backup BGP reportedly restores it immediately.

The proposed solution is dedicated BGP identities per transport, with Azure
custom APIPA peers for Internet. The alternative, private more-specific BGP
prefixes with an Internet static aggregate, is not the selected design.

Six screenshots were supplied in the conversation:

- Internet connection: BGP enabled, custom Azure peers `169.254.21.2` and
  `169.254.22.2`, private Azure tunnel address disabled, default IPsec policy,
  route-based selectors and DPD 45 seconds.
- Gateway peer table: CPE APIPA peer `169.254.21.1` connected on one instance
  with 168 received routes, but the local-address column displays that
  instance's default RFC1918 BGP address. The other instance is connecting.
- Palo Alto PA-5410 traffic logs: allowed TCP/179 from Azure's default
  RFC1918 address to the CPE APIPA peer, ending with server-side TCP reset.
- Learned routes: private and Internet peers advertise the same prefix; the
  Internet path has three occurrences of the CPE ASN, versus one on private.
  The local-address column again displays Azure's default address.
- Repeating the Internet connection configuration with `ResponderOnly`
  reportedly did not change the behavior.
- Microsoft documentation: Azure custom APIPA range is
  `169.254.21.0` through `169.254.22.255`; the CPE must initiate APIPA BGP.

The screenshots do not expose the complete gateway BGP JSON, local network
gateway JSON, CPE peer configuration or PAN-OS version. An established peer
and a default-source log entry do not establish which TCP tuple carries the
learned routes, or why workload forwarding failed. Capture both directions
and every tunnel before attributing this to an Azure platform defect.

## Authorized resource plan

The user approved dedicated Azure, Megaport and Google Cloud costs on
2026-11-24. Do not reuse or alter other labs.

| Component | Plan |
|---|---|
| Azure | Isolated resource group; Sweden Central is the verified VM-capacity fallback |
| VPN | Active-active `VpnGw1AZ`, private tunnel endpoints enabled |
| ExpressRoute | Dedicated `ErGw1AZ`, 50 Mbps Standard/Metered circuit, dual Megaport Azure VXCs |
| Workload | One small Linux probe with Standard SSD |
| GCP | Dedicated billing-linked project, Europe region, Linux `e2-small` CPE, public IPv4, Partner Interconnect |
| Megaport | Dedicated 1000 Mbps MCR on the shortest available contract; one GCP VXC and two Azure VXCs |
| Lifetime | Bounded deployment and validation; automatically remove only task-created resources afterward |

Italy North retail lookup on 2026-11-24 returned VPN gateway $0.21/hour,
ExpressRoute gateway $0.361/hour and Azure B2ts v2 Linux $0.012/hour,
excluding circuit, disks, IPs, traffic, GCP and provider charges.
Provider recurring/termination terms must be recorded before ordering.

The user said region is not important and suggested Europe/Italy North.
Subscription-specific checks rejected both `Standard_B2ts_v2` and
`Standard_D2as_v5` in Italy North (`NotAvailableForSubscription`).
`Standard_B2ts_v2` has no listed restrictions in Sweden Central. This is a
catalog/readiness observation, not an allocation guarantee. Retain the requested
`VpnGw1AZ` rather than silently substituting another gateway SKU.

Candidate nonoverlapping lab space: Azure `10.244.0.0/16`, GatewaySubnet
`10.244.255.0/26`, workload `10.244.1.0/24`, GCP underlay
`10.245.0.0/24`, CPE loopbacks `10.245.254.0/24`, overlay workload
`10.246.1.0/24`. Verify overlaps against the dedicated inventories before use.
Azure ASN `65515`, CPE ASN `64513`, GCP Cloud Router ASN `16550`,
MCR ASN `65060`. Internet Azure peers `169.254.21.2` and `169.254.22.2`;
CPE custom peer `169.254.21.1`. Private peers use gateway-assigned default
addresses and a distinct ordinary CPE loopback.

## Designs studied

| Design | Status | Verdict | Evidence |
|---|---|---|---|
| Default private BGP plus Internet APIPA BGP | Readiness | NOT TESTED | Supplied screenshots; no live reproduction yet |

## Required scenarios

1. Establish two private IPsec/BGP paths and prove bidirectional workload
   traffic crosses IPsec rather than cleartext ER. Capture the clean baseline.
2. Enable Internet APIPA BGP while private sessions remain active. Capture
   per-tunnel TCP/179 packets, FRR peer state, gateway-reported peer state,
   route selection and bidirectional payload. On disruption, capture decisive
   evidence and restore the saved baseline without open-ended troubleshooting.
3. From a verified coexistence baseline, interrupt only the task-created ER
   transport. Prove Internet takeover, route withdrawal, actual payload recovery
   and absence of cleartext bypass. Restore transport, verify failback and
   record measured convergence. Never fault pre-existing provider products.

Every live scenario requires its own bounded control lease. A failed gate
permits bounded restore, not an unlimited retry loop. Missing packet evidence,
failed payload or unavailable provider connectivity is not a passing result.

## Infrastructure actually deployed

**None as of the handoff checkpoint on 2026-11-24.** Every cloud operation so
far has been read-only. No Azure resource group, gateway, circuit or VM; GCP
project, VM or attachment; Megaport MCR or VXC has been created for this lab.
Existing demo resources, including MCRs deployed earlier that day, are unrelated
and must not be changed, reused without review, or cleaned up.

## Current checkpoint and cross-laptop resume

- Azure CLI authentication works. Readiness used the existing lab subscription
  named `Litware-MngEnvMCAP642473-jomore`, with explicit subscription arguments.
  No CLI default was changed. Verify this exact subscription on the next laptop;
  never select a new target merely because it is that laptop's current default.
- GCP: an active account and one open billing account were verified. The
  installed CLI exposes billing operations under `gcloud beta billing`, not
  `gcloud billing`. Its current project belongs to an unrelated demo; use
  explicit project arguments and create a dedicated project for this lab.
- Megaport: **authentication is working** with the inherited API-key environment
  variables against `https://auth-m2m.megaport.com/oauth2/token`, using HTTP Basic
  authentication and form field `grant_type=client_credentials`. Bearer access
  to `https://api.megaport.com/v2/products` succeeded.
- The earlier 401s came from attempts against legacy endpoints
  (`api.megaport.com/v2/oauth/token` and `/v2/login`). They are not evidence of
  invalid current API keys. Do not repeat those attempts or rotate working keys.
- A fallback read from the repository-designated Key Vault was denied because
  public network access is disabled. No ACL, firewall or public-access setting
  was changed. This does not block use of the working environment credentials.
- Megaport location catalog advertises MCR capacity in Stockholm, Amsterdam
  and Milan. Account-specific order validation and pricing are still required.
- Next bounded action: validate/quote a dedicated 1000 Mbps MCR on a one-month
  term, select a supported European PoP, and prepare isolated deployment.
- Restore/resource state: no resource mutations or injected faults to restore.
- Ignored `.runtime-control/` files contain local readiness inventories and
  leases only. They are deliberately **not portable through Git**. Recreate
  fresh leases and reauthenticate on the next laptop; do not copy old tokens,
  credentials, expired leases or another session's local state.
- Before resources exist, choose a portable, access-controlled state strategy
  if Terraform is used. Do not depend on uncommitted local state for next-day
  ownership or cleanup. Record task-created resource names, regions, provider
  order terms and status here after each deployment wave, without secret keys
  or subscription/tenant IDs.

## References

- [Configure BGP](https://learn.microsoft.com/en-us/azure/vpn-gateway/configure-bgp)
- [IPsec over ExpressRoute private peering](https://learn.microsoft.com/en-us/azure/vpn-gateway/site-to-site-vpn-private-peering)
- [Current Megaport API-key authentication](https://docs.megaport.com/api/api-key)
- [MCR order validation and pricing](https://docs.megaport.com/api/api-mcr/)
- Related but different platform: [vWAN lab](../vwan-ipsec-over-er-backup/README.md)
