# VNet VPN custom BGP coexistence

## Objective

Reproduce the coexistence of two active-active IPsec paths over ExpressRoute
using default Azure BGP addresses and Internet backup using custom APIPA peers.
Use Linux StrongSwan/FRR to isolate Azure behavior. This is not a PAN-OS
reproduction and cannot establish a Palo Alto-specific root cause.

See [initial assessment](assessment.md) for the ranked hypotheses, evidence
limitations and decisive tests. It is not a confirmed root cause.
The [customer fidelity contract](customer-fidelity.md) records the required
three-tunnel topology, migration sequence, known substitutions and acceptance
gates, updated from the email thread retrieved through WorkIQ.
The [simulator assessment](simulator.md) and
[importable topology](simulator-topology.json) cover converged routing only.
They do not reproduce the suspected APIPA control-plane failure.

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
| Default private BGP plus Internet APIPA BGP | Foundation partially deployed; recovery pending | NOT TESTED | [Assessment](assessment.md); no live reproduction yet |
| Three-overlay converged routing abstraction | Three simulator states evaluated | PASS within abstraction; customer issue INCONCLUSIVE | [Simulator evidence and limits](simulator.md) |

## Required scenarios

1. Start with one established static Internet VPN on the same CPE. Introduce
   private BGP, capture the static/BGP coexistence, remove conflicting Internet
   static prefixes, then establish both private IPsec/BGP paths. Prove
   bidirectional encrypted payload, not cleartext ER. Preserve the existing
   Internet connection and capture the clean pre-enablement baseline.
2. Enable Internet APIPA BGP in place while private sessions remain active.
   Keep exactly one Internet tunnel for the primary reproduction. Capture
   per-tunnel TCP/179 packets, FRR peer state, gateway-reported peer state,
   route selection and bidirectional payload. On disruption, capture decisive
   evidence and disable backup BGP as the first rollback; verify private
   forwarding recovery without gateway recreation or gratuitous SA resets.
3. From a verified coexistence baseline, interrupt only the task-created ER
   transport. Prove Internet takeover, route withdrawal, actual payload recovery
   and absence of cleartext bypass. Restore transport, verify failback and
   record measured convergence. Never fault pre-existing provider products.

Every live scenario requires its own bounded control lease. A failed gate
permits bounded restore, not an unlimited retry loop. Missing packet evidence,
failed payload or unavailable provider connectivity is not a passing result.

## Infrastructure actually deployed

**2026-11-24 19:33 UTC: foundation apply stopped, verdict BLOCKED.** The earlier Azure state
bootstrap group `rg-vnbgp-state-20261124` and storage account
`stvnbgp20261124`, with container `tfstate`, were rolled back.
ARM deployment succeeded, but effective account settings were
`publicNetworkAccess=Disabled` and `allowSharedKeyAccess=false`.
Terraform initialization failed with `KeyBasedAuthenticationNotPermitted`;
Entra-authenticated data access was also unavailable from this laptop.

Neither setting was relaxed. After verifying the group contained only the
task-tagged state account, the account and group were deleted. A subsequent
resource-group existence query returned false.

Recovery created dedicated GCP state project `gcp-vnbgp-state-20261124` and
bucket `gcp-vnbgp-state-20261124-tfstate` in `europe-west4`. Bucket metadata
verifies uniform bucket-level access and enforced public-access prevention.
Terraform GCS backend initialization succeeded using a runtime OAuth token.
State prefix is `vnet-vpn-custom-bgp`; Terraform locking is enabled. Keep this
backend until every managed resource has been removed. It is separate from the
managed GCP lab project, so destroying the lab does not destroy its state.

The dedicated Azure group was created through a targeted preflight plan.
Live VM validation passed for Sweden Central `Standard_B2ts_v2`. The subsequent
foundation plan contained 26 creates, no updates/deletes/replacements.

The apply subsequently stopped on two explicit deployment errors, unrelated
to the customer's BGP failure:

1. The installed AzureRM provider rejects `public_ip_address_id` for an
   ExpressRoute gateway. That field has now been removed from the ER gateway.
2. The GCP static address had no dependency on the new project/API resources,
   so creation raced project creation and returned project-not-found (404).
   It now explicitly depends on the enabled project services.

The source fixes pass Terraform format/validation but have **not** been applied.
The failed run is idle and its live lease is blocked. A fresh approved bounded
recovery must inspect a new saved plan before applying, not reuse the failed
plan or silently renew its lease. The allocated `er` public IP is currently
unused; it remains tracked for task-only cleanup and is not attached to the
ER gateway by the corrected source.

| Component | Actual state at handoff |
|---|---|
| Azure state group/account/container | Created, then deleted; group deletion verified |
| GCP state project and private bucket | Created; Terraform backend initialized |
| Azure lab group `rg-vnbgp-20261124` | Created and tracked in GCS state |
| VPN gateway `vpngw-vnbgp-20261124` | Azure API reports `Succeeded`, `VpnGw1AZ` |
| ER circuit, VNet, subnets, PIPs, NSG and NIC | Created and tracked in GCS state; circuit is not provider-connected |
| Probe VM | In GCS state; latest Azure API state `Updating`, not yet accepted as ready |
| ER gateway | Not created, provider validation error above |
| GCP project, APIs, VPC, subnet, Cloud Router and firewall rules | Created and tracked in GCS state |
| GCP Partner attachment | Created, `PENDING_PARTNER` |
| GCP CPE public IP and CPE VM | Not created, dependency error above |
| Megaport MCR and three VXCs | Not purchased |

This is a partial foundation, not a ready or validated test bed. No traffic
baseline existed to restore. Partial resources and the private state backend
are preserved for recovery; cleanup has not been claimed complete.
Existing demo resources, including MCRs deployed earlier that day, are unrelated
and must not be changed, reused without review, or cleaned up.

## Current checkpoint and cross-laptop resume

### Recovery discovery, 2026-11-25

Recovered from `erjosito-custom-bgp-failover` at commit `b18425cf` into
`erjosito-multicloud-lab-recovery`. This recovery performed no cloud mutations,
purchases, fault injection or cleanup. Yesterday's dedicated-cloud cost approval
was recovered from session history; the failed foundation lease is not renewed.

Read-only live checks on this laptop verified:

- The authorized Azure subscription is enabled. The task VPN gateway is
  `Succeeded` with `VpnGw1AZ`; the ER gateway does not exist. The probe is
  provisioned but **deallocated**, not a ready traffic baseline. The task VNet,
  circuit, NIC, NSG and three PIPs exist. A disk and `MDE.Linux` extension are
  also present; ownership and policy management must be reviewed before cleanup.
- Both dedicated GCP projects are active. The state bucket enforces public-access
  prevention and uniform access; the state object is accessible at the recorded
  prefix. No CPE VM exists. The Partner attachment remains `PENDING_PARTNER`.
- Megaport OAuth and product inventory access succeed using the environment's
  `MEGAPORT_ACCESS_KEY` / `MEGAPORT_SECRET_KEY`. No matching task products were
  found. Secrets were not printed or copied.
- Native Windows `gcloud` works. The WSL probe timed out; its owned process is
  no longer active. The runner now prefers native `gcloud.cmd`, retaining WSL
  only as a fallback for laptops without the native SDK. Backend initialization
  succeeded on this laptop and the recovered state contains 24 managed resource
  entries, including the existing Azure/GCP foundations. No apply was run.
- WorkIQ recovered the source thread and found no newer requirements through
  2026-11-25. The substantive report is dated 2026-11-20, with a follow-up on
  2026-11-24. Git holds sanitized synthesis, not raw email or screenshots.
  Shared-device identity remains a question in the latest reply; see the
  corrected [fidelity contract](customer-fidelity.md).

**Provisioning remains BLOCKED pending a fresh bounded recovery approval and
reviewed plan.** Finish only the missing foundation resources using the saved
source fixes, preserving existing resources and remote state. Investigate the
probe's deallocation before starting payload tests. Do not create replacement
GCP projects or redeploy the deleted Azure state bootstrap.

The Megaport purchase gate is separate and still open: verify current endpoint/
provider payloads select **PAYG / No Minimum Term**, with **auto-renewal disabled**,
and obtain account-effective quotes for the MCR and all three VXCs. The prior
"one-month term" wording is not evidence of a committed contract: documented API
value `1` means No Minimum Term. The Terraform source does not explicitly show
auto-renewal control, so provider defaults must not be assumed safe. No purchase
is permitted until actual request semantics and effective charges are verified.
Current official reference: [MCR pricing and contract terms](https://docs.megaport.com/finance/mcr-pricing/).

### Previous laptop handoff (2026-11-24; historical)

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
- Next bounded action: obtain approval for a fresh bounded foundation recovery,
  inspect a new plan using the two source fixes and finish the missing resources.
  Then validate/quote provider connections before any provider purchase.
- Quote result: Stockholm order validation failed because the account lacks
  the Sweden market. Amsterdam AM1 (location 85) validated at EUR 600/month
  rack rate for a 1000 Mbps MCR with a one-month term. The response includes a
  promotional discount; do not assume that discount is guaranteed. VXCs have
  not been quoted or purchased.
- Restore/resource state: original Azure bootstrap rollback verified; GCP state
  recovery completed; foundation apply stopped partially complete. No faults
  have been injected and no Megaport products purchased. Created resources
  remain billable pending recovery or task-only cleanup.
- Ignored `.runtime-control/` files contain local readiness inventories and
  leases only. They are deliberately **not portable through Git**. Recreate
  fresh leases and reauthenticate on the next laptop; do not copy old tokens,
  credentials, expired leases or another session's local state.
- The private GCP recovery is now performed under the existing dedicated-cloud
  deployment approval. The source and runner use GCS, not Azure account keys.
  The original `bootstrap.bicep` is historical only; do not redeploy it or relax
  Azure storage security. Tokens, keys and private IDs remain out of Git.

## Deployment source and resume commands

`deploy/` contains the prepared VNet gateway topology and reuses the existing
StrongSwan/FRR startup script. Terraform provider versions are locked. The
Terraform configuration validates and the GCS backend initializes. Neither
alone constitutes a successful deployment.
Gateways are created sequentially to avoid competing gateway-subnet operations.
The source includes a distinct dedicated GCP project and never uses the CLI's
current project as the deployment target. The two apply-time blockers and
unapplied fixes are recorded above; syntax validation did not catch them.

Before any live command, follow the repository live-lab policy and create a
fresh ignored `deploy/.runtime-control/lease.json` with the approved scope,
budgets, expiry and restore plan. The runner refuses expired/inactive leases,
STOP, or a command timeout beyond the remaining lease reserve.

After reauthentication, fresh recovery approval/lease and confirming the
previous apply is idle, the staged workflow from the repository root on Windows is:

```powershell
python labs\vnet-vpn-custom-bgp\deploy\run_terraform.py init
python labs\vnet-vpn-custom-bgp\deploy\run_terraform.py plan --stage foundation --timeout 120
```

Inspect the printed actions and the saved private plan before applying.
Foundation creates Azure/GCP resources only. Provider and connection stages
are separate: **do not return to a lower stage after a higher stage is
deployed**, because that would propose removing its resources. The runner
refuses deletion/replacement plans.

The current runner is Windows-specific and uses Azure CLI, native Windows
`gcloud.cmd` when available (otherwise WSL `gcloud`) and
Megaport key environment variables. It requires exactly one open GCP billing
account; ambiguity is an explicit error. On a new laptop it recovers the probe's
existing public SSH key from Azure, rather than planning VM replacement.
Tokens, plans and raw diagnostics stay in ignored runtime storage. Do not
publish them.

No IPsec connections, FRR peer configuration or fault tests have been applied.
Those are subsequent work after infrastructure readiness, not outcomes implied
by successful Terraform syntax validation.

## References

- [Configure BGP](https://learn.microsoft.com/en-us/azure/vpn-gateway/configure-bgp)
- [IPsec over ExpressRoute private peering](https://learn.microsoft.com/en-us/azure/vpn-gateway/site-to-site-vpn-private-peering)
- [Current Megaport API-key authentication](https://docs.megaport.com/api/api-key)
- [MCR order validation and pricing](https://docs.megaport.com/api/api-mcr/)
- Related but different platform: [vWAN lab](../vwan-ipsec-over-er-backup/README.md)
