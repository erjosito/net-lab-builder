# vWAN IPsec-over-ER backup - deployment log

> **Status (2026-09-28): BLOCKED at the Megaport Stockholm market gate.** Azure and GCP foundations are deployed and converged. No Megaport product was ordered, no vHub ExpressRoute connection exists, and VPN sites/connections were intentionally not created.

## Deployment result

| Plane | Result |
|---|---|
| Azure | Standard vWAN, `10.240.0.0/24` vHub with `ASPath` routing preference, VPN gateway, ExpressRoute gateway, 50-Mbps Standard Metered circuit, workload VNet/connection, and `Standard_B2ts_v2` probe VM deployed in Sweden Central |
| GCP | New isolated billing-linked project, required APIs, custom VPC, Cloud Router ASN `16550`, Partner attachment, reserved public IP, and forwarding-enabled Ubuntu CPE deployed in `europe-north2-c` |
| CPE | `e2-small`; StrongSwan, FRR, tcpdump, nftables, forwarding, and the four required alias `/32`s installed |
| Megaport | Not deployed. Non-billable Stockholm order validation failed before purchase |
| Overlay | Not deployed. VPN connections, generated PSKs, XFRM interfaces, and BGP sessions remain pending the provider blocker |

Terraform converged with no destructive actions. The latest closure plan reported **no changes** after the VM safety schedules were applied.

## Capacity and recovery record

The requested `e2-small` size returned explicit capacity/resource failures in `europe-north2-a` and `europe-north2-b`. The same size then deployed successfully in `europe-north2-c`; the authorized `e2-medium` fallback was not used.

The first CPE startup attempt failed because a Windows-authored inline startup script reached Linux with CRLF (`/bin/bash^M`). Startup logic was moved to an external LF-normalized shell file and `*.sh text eol=lf` was added. A second startup issue was fixed by enabling the real `strongswan` service rather than its `strongswan-swanctl` alias. The final startup service is healthy.

## Hard blocker

Megaport OAuth authentication succeeded through the approved credential path. The public location catalog and Terraform data source both exposed `Equinix Stockholm SK1`, but the live non-billable `/v3/networkdesign/validate` request returned:

```text
HTTP 400
Validation failed
Missing markets: Sweden
```

This is a design-review hard stop: catalog visibility does not establish account market entitlement, and substituting Frankfurt or another market would change the explicitly authorized Stockholm design. No MCR or VXC purchase was attempted.

Resume only after one of these decisions:

1. Megaport enables Sweden for the current account, preserving Stockholm.
2. Jose explicitly authorizes a different market/PoP after reviewing the quote and design impact.

## Current provider states

| Check | State |
|---|---|
| vHub | `Succeeded`, `ASPath`, `10.240.0.0/24` |
| vWAN VPN gateway | `Succeeded` |
| vWAN ExpressRoute gateway | `Succeeded` |
| Workload vHub connection | `Succeeded` |
| ExpressRoute circuit | `Enabled`; provider state `NotProvisioned` |
| GCP CPE | `RUNNING`, `e2-small`, IP forwarding enabled |
| GCP Partner attachment | `PENDING_PARTNER` |
| Cloud Router advertisement | Custom mode; only `10.250.0.10/32` |
| Megaport MCR/VXCs | Absent |
| VPN sites/connections | Absent |

The ER and Partner states are expected until the three Megaport VXCs are created and paired.

## Safety controls

- Megaport resources are guarded by `deploy_megaport = false`.
- Azure-generated PSKs are excluded from Terraform and committed files.
- Runtime VPN output, state, plans, rendered configs, and secret-bearing files are ignored.
- Azure and GCP VMs have daily 23:00 Europe/Stockholm stop schedules. Managed vWAN gateways, the ER circuit, and the Partner attachment cannot be paused by those VM schedules.
- Cleanup remains separately approval-gated; `deploy/cleanup.ps1` refuses execution without a future authorized implementation.

## Cost and commitment exposure

These are planning estimates, not invoice values:

| Item | Approximate exposure |
|---|---:|
| Azure vWAN VPN gateway | `$0.361/hour` |
| Azure vWAN ExpressRoute gateway | `$0.42/hour` |
| Azure 50-Mbps Standard Metered ER circuit | about `$55/month` |
| GCP `e2-small` | about `$0.052/hour` while running |
| GCP Partner attachment | about `$0.10/hour` |
| vHub, VM disks, public IP, and minor networking | additional usage |
| Combined live foundation | roughly `$1.2-$1.4/hour` or `$29-$34/day`, excluding traffic and tax |
| Megaport commitment | **`$0`** |

The VM stop schedules reduce compute exposure only. The managed gateways, ER circuit, and Partner attachment continue billing until separately authorized cleanup.

## Smoke results

- Azure vHub, both managed gateways, ER circuit resource, and workload connection report successful control-plane provisioning.
- GCP CPE reports startup success, forwarding `1`, StrongSwan active, FRR active, and required packages installed.
- The CPE NIC has `10.250.254.240/32`, `.241/32`, `.242/32`, and `.250/32`.
- Azure VM Run Command management access succeeded during deployment; NIC addressing/routes and `tcpdump` were present.
- The Azure probe cloud-init run reported an error because the private subnet intentionally has no default outbound access and the original cloud-init attempted package retrieval. IaC no longer requests those packages, but the deployed VM was not replaced solely to clear historical cloud-init state.
- No cross-cloud, IPsec, BGP, route-preference, failover, or D1/D2/D3 validation was run.

## Niobe handoff

**Do not begin final validation.** The required baseline does not exist:

- no MCR or VXCs;
- ER private peering/provider provisioning incomplete;
- GCP attachment unpaired;
- no vHub ER connection;
- no VPN sites/connections or Azure-generated runtime PSKs;
- no XFRM SAs or overlay BGP sessions.

After the Stockholm decision is resolved, Tank must resume provider ordering, wait for both Azure MSEE paths and the GCP attachment, create the vHub ER connection, create the private/public VPN connections, retrieve runtime values, apply the CPE bundle, narrow endpoint filtering, and establish a healthy D2 baseline. Niobe then follows `validation-plan.md` and the reset order in `design.md`; smoke results above are not scenario evidence.
