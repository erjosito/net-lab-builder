# VNet VPN custom BGP coexistence

## Objective

Reproduce the coexistence of two active-active IPsec paths over ExpressRoute
using default Azure BGP addresses and Internet backup using custom APIPA peers.
Use Linux StrongSwan/FRR to isolate Azure behavior. This is not a PAN-OS
reproduction and cannot establish a Palo Alto-specific root cause.

**Current state, 2026-11-25 15:39 UTC: Google CPE intentionally stopped.**
The user requested saving VM compute costs. Its boot disk and reserved public
IP are preserved; the four-tunnel configuration remains on disk with boot
services enabled, but reboot recovery has not been tested. VPN/BGP and payload
are unavailable while the CPE is stopped. All four adjacencies and private
encrypted payload last passed at 14:27 UTC.
See the [current checkpoint](#current-checkpoint-and-cross-laptop-resume).
The user explicitly requested the final state directly, rather than completing
the historical migration sequence.

See [initial assessment](assessment.md) for the ranked hypotheses, evidence
limitations and decisive tests. It is not a confirmed root cause.
The [customer fidelity contract](customer-fidelity.md) records the original
three-tunnel topology, deferred migration sequence, known substitutions and
user-directed fourth-tunnel extension.
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
| Default private BGP plus Internet APIPA BGP | Two private and two Internet tunnels configured; all four adjacencies established | PASS for four-peer configuration and private encrypted payload; customer migration and failover NOT TESTED | [Four-tunnel evidence](raw-output/four-tunnel-bgp-20261125.json) |
| Temporary static Internet baseline | One Internet tunnel verified before user requested the direct BGP end state | PASS within baseline scope; no longer the configured routing design | [Baseline evidence](raw-output/internet-baseline-20261125.json) |
| Three-overlay converged routing abstraction | Three simulator states evaluated | PASS within abstraction; customer issue INCONCLUSIVE | [Simulator evidence and limits](simulator.md) |

## Reproduction scenarios (deferred)

The user directed on 2026-11-25: go straight to the end state with BGP over
both connections. The sequence below remains a future reproduction plan,
not work required to complete that configuration request or a claim that the
customer's migration has been reproduced.

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

## Infrastructure deployment history

The dated checkpoints below preserve earlier states. Use the newest checkpoint
for current readiness; historical BLOCKED results are not the current verdict.

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

### CPE paused to save compute costs, 2026-11-25 15:39 UTC

**Verdict: PASS for the requested shutdown.** Google instance
`cpe-vnbgp-20261124` in `europe-north2-a` is `TERMINATED` (stopped, not deleted).
Its original boot disk is present and `READY`; its private address and reserved
public address remain preserved. No other Google, Azure or Megaport resource
was stopped, deleted or reconfigured. Their recurring charges, plus retained
disk and static-IP charges, continue.

Before stopping, all seven persistent configuration files matched the
verified four-tunnel renderer, including XFRM/endpoint-route setup, StrongSwan
connections and FRR policies. The `vnbgp-network`, `vnbgp-ipsec`, `strongswan`
and `frr` services were enabled. The two custom oneshot units were inactive
on this boot because installation had run their commands directly; this is
not a completed reboot test. The Google startup script matches source and does
not overwrite the saved VPN/BGP configuration. No configuration change was
needed for shutdown.

The lab's VPN/BGP sessions and end-to-end traffic are intentionally unavailable
until the CPE starts again. The next bounded action, **only when running costs
are authorized again**, is:

```powershell
gcloud.cmd compute instances start cpe-vnbgp-20261124 --project=gcp-vnbgp-20261124 --zone=europe-north2-a
```

Then verify both custom boot units, four IPsec/BGP sessions, private preference
and workload traffic; do not assume recovery has passed just because the VM
is running. Use IAP for SSH (`--tunnel-through-iap`). Do not rerun the full guest
installer or rotate keys as a routine start operation.
See [shutdown evidence](raw-output/cpe-stopped-20261125.json).

### Both Internet instances completed, 2026-11-25 14:27 UTC

**Verdict: PASS.** After the user requested completing the second Internet
instance, `169.254.22.2` is now established alongside `169.254.21.2`.
Azure reports all four customer adjacencies `Connected`, with one received
prefix each. There are still **two Azure connection objects**, now with
**four configured CPE tunnels**:

| Transport / child | Azure outer endpoint | Azure BGP peer | CPE BGP source | Preference |
|---|---|---|---|---|
| Private `private0` | `10.244.255.4` | `10.244.255.7` | `10.245.254.6` | 200 |
| Private `private1` | `10.244.255.5` | `10.244.255.6` | `10.245.254.6` | 200 |
| Internet `internet` | `4.165.162.61` | `169.254.21.2` | `169.254.21.1` | 100 |
| Internet `internet1` | `4.165.90.255` | `169.254.22.2` | `169.254.21.1` | 100 |

Both Internet sessions use the **same CPE APIPA**, as configured on their
shared LNG; do not invent a second CPE source of `169.254.22.1`. The new
capture proves a CPE-initiated handshake from `169.254.21.1:33649` to
`169.254.22.2:179` on `xfrm-internet1`, XFRM ID 104. Its public outer `/32`
is pinned to the physical underlay; its BGP peer `/32` is pinned to the new
XFRM interface. The original interface IDs, IKE identities and PSKs remain.
No Azure, Google or Megaport resource configuration was changed.

The initial full guest update established all four peers but briefly
reconnected private neighbor `10.244.255.6`; the strict continuity gate failed,
so that update was rolled back. An independently reviewed add-only recovery
then added only the new interface/routes and explicit new-neighbor FRR
commands, without replaying old routes or reloading FRR. It caused **no further
reconnects**, confirmed by unchanged counters and increasing uptimes over
the stability observation. The private peer's historical drop counter stays
at one. The earlier reconnection's cause is unresolved, not a demonstrated
Azure or PAN-OS defect.

All four peers exchange their expected prefixes. The two private paths remain
the installed ECMP paths for Azure `10.244.0.0/16`; both Internet paths retain
local preference 100 and two extra AS prepends on export. Ordinary workload
ping passed **5/5**. Persistent file hashes match the four-tunnel renderer,
the existing boot services remain enabled, and no capture remains active.
Reboot persistence, Internet workload takeover and failover timing were not
tested. Resources remain running and billable.

See [sanitized four-tunnel evidence](raw-output/four-tunnel-bgp-20261125.json).
The following older checkpoints describe historical states.

### BGP end state configured, 2026-11-25 13:50 UTC (historical)

**Verdict: PASS for the requested direct BGP configuration and private
encrypted payload.** The user superseded the remaining static-to-BGP migration
sequence. The existing Internet connection and PSK were preserved; no Megaport
product was changed. Resources remain running for inspection and further tests.

| Azure connection | CPE tunnels | Outer transport | BGP identities |
|---|---|---|---|
| `conn-private-vnbgp-20261124` | `private0`, `private1` | Private IPsec over real ER | CPE `10.245.254.6` to Azure `10.244.255.7` and `.6` |
| `conn-internet-vnbgp-20261124` | `internet` only | Public IPsec | CPE `169.254.21.1` to Azure `169.254.21.2` |

Both connection resources report `Succeeded` with BGP enabled. One
active-active private connection supplies the two private instance tunnels;
these are **two Azure connection objects and three configured CPE tunnels**.
The unused second public gateway endpoint is intentional. Its APIPA peer can
appear `Connecting` in Azure and is not a failed required fourth tunnel.

All three CPE BGP sessions are established. The CPE installs the two private
paths for Azure `10.244.0.0/16`, with local preference 200 versus Internet 100.
Azure receives `10.246.1.0/24` with AS path `64513` on private and
`64513-64513-64513` on Internet. The Internet LNG has no remaining static
payload prefix, and the CPE has no static route to the Azure workload.
The local discard route for originating the CPE prefix is not a static VPN
fallback. Google still advertises only the CPE outer `10.245.0.10/32`.

Five ordinary source-bound workload pings passed with no loss. The capture
also shows five requests leaving `xfrm-private0` and all five replies entering
`xfrm-private1`: valid asymmetric ECMP across the private tunnels. A ping
socket bound to only the sending interface reported loss because it filtered
those replies. Do not confuse that tool artefact with a forwarding outage.
The Internet capture proves a CPE-initiated TCP handshake from
`169.254.21.1` to `169.254.21.2:179`. Azure still labels that established
peer with its default local BGP address in API metadata; the packet tuple,
not that column, establishes the working source identity.

State contains **36 managed instances**, and the final overlay-only plan
has **zero changes**. Persistent XFRM/endpoint-route and StrongSwan-loading
services are enabled along with FRR. A reboot was not performed. The Internet
child was explicitly initiated once after the Azure update; the private BGP
sessions remained up. The deployment helper now starts absent existing
children when configuration reload alone does not do so.

See [sanitized final evidence](raw-output/bgp-final-state-20261125.json).
Historical migration reproduction, ER failure/failback timings, final-state
Internet workload takeover and a PAN-OS-specific root cause are **not claimed**.
The default Azure policy negotiated MODP_1024, which is a lab observation,
not a production crypto recommendation. No live command or packet capture
remains active; cleanup has not been run because the configured lab is retained.

### ER underlay reconciled, 2026-11-25 11:55 UTC

**Verdict: PASS for the underlay control plane; IPsec/payload NOT TESTED.**
After explicit approval for a fresh wait-and-reconcile recovery, the existing
`conn-er-vnbgp-20261124` reported `Succeeded`. Its exact gateway/circuit
references were verified and it was imported once into GCS state. No second
create or Megaport update was issued. State now contains **32 managed resource
instances** and no retained lock.

The ER gateway learns `10.245.0.10/32` via both Azure peers, with path
`12076-65060-16550`; both circuit peerings also retain that host route.
Google's established Cloud Router peer learns Azure `10.244.0.0/16` with path
`65060 12076`, while advertising only the CPE outer `/32`. The overlay workload
prefix is absent from direct ER advertisements. These are control-plane
assertions, not proof of packets or encrypted transport.
All four products were rechecked as `LIVE`, up, No Minimum Term, and
`autoRenewTerm=false`. See
[sanitized recovery evidence](raw-output/underlay-reconciled-20261125.json).

The earlier connection timeout and provider-plan limitation remain recorded
below; the connection gate itself is resolved. STOP is absent, the recovery
lease is completed, and all owned commands are idle. Existing resources are
retained for the next scoped action: establish the single static Internet VPN
baseline before the private-BGP migration. The probe is still deallocated;
no IPsec/FRR configuration, payload or failover test has run.

### Provider ready; ER connection pending, 2026-11-25

**Verdict: BLOCKED at the Azure gateway-connection gate.** All four purchased
Megaport products are now `LIVE` and up; fresh reads still verify No Minimum
Term and `autoRenewTerm=false`. Google's attachment is `ACTIVE`, with an
automatically managed Cloud Router peer in `Established` / `UP` state.
The router advertises only the CPE outer `10.245.0.10/32`. Both Azure circuit
peerings learn that host route with AS path `65060 16550`.
See [sanitized underlay checkpoint](raw-output/underlay-readiness-20261125.json).

The connection-stage Terraform review exposed updates to imported Megaport
endpoint/partner fields. None were applied. The runner now rejects Megaport
updates as well as creates; use separately reviewed API operations for those
products. An inventory-only `ignore_changes=all` experiment exposed a provider
invalid-plan error on imported `a_end.requested_product_uid` and was removed.
Do not run a full apply until its provider changes have been safely resolved.

Exactly one Azure-only create was submitted for `conn-er-vnbgp-20261124`,
linking the existing ER gateway and circuit. It exceeded its 600-second command
bound; the owned process tree was stopped. A subsequent read still reports
connection `Updating` and ER gateway `Succeeded`. The new connection has
**not** been imported into Terraform state; its exact IDs and create intent
are retained privately under the ignored runtime controls. No duplicate create
was attempted. STOP is present and the live lease is blocked; all owned
commands are idle.

Next bounded recovery, requiring approval: wait for this existing connection
without recreating it, verify its gateway/circuit identity, import it once into
GCS state if successful, then verify the CPE host route at the ER gateway and
Azure prefixes at Google. The last gateway route read contained only the local
VNet prefix, so bidirectional underlay readiness is not proven. The MCR BGP
diagnostic returned an empty array, which is an observability limitation, not
proof of an empty RIB or a passing path.

No IPsec, FRR, probe-start or failure scenario was run. Existing resources,
including the pending connection, remain provisioned and potentially billable.
The simulator model requirements are tracked in
[erjosito/vwan-visual-topology#463](https://github.com/erjosito/vwan-visual-topology/issues/463);
that issue is not live-lab evidence.

### Megaport PAYG provisioning, 2026-11-25 10:59 UTC

**Verdict: PASS for PAYG / No Minimum Term selection on all four purchased
products; end-to-end connectivity remains NOT TESTED.** The user reaffirmed
that Megaport products must have no minimum contract period.

The exact four-product design was revalidated with real task service keys,
explicit `term=1` and `autoRenewTerm=false` on every product, and fresh
authenticated account-specific quotes. Detailed pricebook documentation
distinguishes the monthly rate from its component fields; promotional metadata
is retained privately and is not treated as a guaranteed free-service invoice.
One API order was submitted, without retries.

Subsequent generic product reads verified **`contractTermMonths=1` and
`autoRenewTerm=false` on the actual MCR and each of the three VXCs**. In
Megaport's API, `1` means No Minimum Term, not a one-month commitment. The
contract/renewal verification gate from earlier checkpoints is resolved.
See [sanitized contract and provisioning evidence](raw-output/provider-payg-verification-20261125.json).

The MCR is live, the primary Azure VXC is configured, and the secondary Azure
and Google VXCs were still `DEPLOYABLE` at the final check. Azure reports the
circuit provider state `Provisioned`; the Google attachment is still
`PENDING_PARTNER`. These states are not evidence of working BGP or payload.
All four purchased products were imported into the existing GCS state, which
now has 31 managed resource instances and no retained lock.

The Google VXC source now explicitly selects the purchased Stockholm partner
port and red availability domain. The runner refuses Terraform Megaport
creates because the locked provider cannot explicitly set renewal: new products
must use a validated explicit PAYG/no-renewal API order followed by import.
Do not run the foundation stage now that provider products exist.

The final **provider-stage** plan has no creates, deletes or replacements,
but it includes unapplied import reconciliation for resource tags, provider
partner/interface fields and previously noted GCP metadata. Review the exact
fields before applying; do not casually rewrite auto-provisioned peering or
interface configuration. No ER gateway connection, IPsec connections, FRR peers
or fault scenarios were added in this provider-only run. The probe remains
deallocated. All owned commands are idle and the provider lease is completed.
Resources remain provisioned and potentially billable for subsequent validation.

### State reconciliation, 2026-11-25 10:50 UTC

**Verdict: PASS for state reconciliation; the end-to-end lab is NOT TESTED.**
The user explicitly approved a new 30-minute state-only recovery. The prior
Terraform process was absent and the ER gateway had completed with `Succeeded`.
The exact retained lock was verified against its creation time and content.
An initial unlock using the embedded JSON UUID was rejected without mutation;
the GCS backend requires the lock object's numeric generation. The unchanged
generation was then verified and unlocked using Terraform's generation-match
guard.

The existing ER gateway, GCP CPE public IP and CPE VM were imported successfully,
without recreating or changing cloud resources. Remote state now contains
27 managed resource instances and no `.tflock` remains. A fresh foundation
plan proposes no creates, deletes or replacements. Its only changes are GCP
labels and the Terraform-side `allow_stopping_for_update` option; these were
reviewed but **not applied** under the state-only authorization.

The prior state-recovery blocker below is resolved. The ER gateway is ready at
the resource API level; the CPE is running and its startup script succeeded.
The probe remains deallocated. There are still no Megaport products, provider
connectivity, IPsec connections, FRR peer configuration or validated traffic
baseline. Existing foundations remain billable. Continue only after resolving
the provider PAYG/no-renewal and effective-charge gates described below; do not
replay imports or foundation creates. All owned commands are idle.

### Approved foundation recovery, 2026-11-25 09:33 UTC

**Verdict: BLOCKED at the configured progress bound, not an Azure failure
verdict.** User approval was received for fresh bounded recovery. The stopped
apply is idle; its STOP sentinel and remote Terraform lock remain preserved.
No Megaport products were purchased and no existing resources were replaced.

The new plan initially proposed replacements due to live drift: the probe disk
is `Standard_LRS`, and all three public IPs carry
`FirstPartyUsage=/Unprivileged`. The probe also has platform-managed patch
settings. The source now explicitly preserves these deployed values rather
than replacing resources or reverting patch settings. Native Google CLI billing
discovery now uses the installed stable command, without requiring the beta
component. The final reviewed plan contained only three creates.

The apply created the GCP CPE public IP and VM. The CPE is `RUNNING`, its public
IP is `IN_USE`, and serial output records `startup-script exit status 0`.
Azure accepted ER gateway creation at 09:13 UTC, but it remained `Updating`
without an observed provisioning advancement past the conservative no-progress
limit. The owned Terraform process was stopped at 09:32 UTC; this does not
cancel the Azure-managed operation, which may still complete.

**Remote-state reconciliation is required before any further apply.** A closure
read found the retained `.tflock`, and the state snapshot did not contain the
new ER gateway or GCP CPE/IP entries. Do not replay their creates. The exact
retained resource IDs and creation evidence are in an ignored private inventory.
Recovery must verify the old operation/owner is idle, inspect the task lock,
reconcile/import these existing resources under a new approved lease, and review
a fresh non-destructive plan. No force-unlock or import was attempted in this
stopped run. The previously deployed probe remains deallocated.

Megaport validation accepted a complete four-product design using the real
task service keys, explicit `term=1` and `autoRenewTerm=false`, with a Google
partner port matching the attachment's region and availability domain.
Account-specific quotes are retained privately. The response omitted contract/
renewal echoes and included promotional and fixed-charge fields whose net-charge
semantics remain unresolved. The locked Terraform provider does not expose
explicit renewal control, and its Google VXC source lacks an explicit partner
port selection. These purchasing gates remain open; do not infer either free
service or safe renewal/port defaults from validation success.

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
StrongSwan/FRR package-install startup script. `overlay.tf` defines the two
LNG/IPsec pairs; `overlay_guest.py` renders persistent CPE routes, four
StrongSwan children and FRR policies. Terraform provider versions are locked.
Gateways are created sequentially to avoid competing gateway-subnet operations.
The source includes a distinct dedicated GCP project and never uses the CLI's
current project as the deployment target. Earlier blockers are historical.

Before any live command, follow the repository live-lab policy and create a
fresh ignored `deploy/.runtime-control/lease.json` with the approved scope,
budgets, expiry and restore plan. The runner refuses expired/inactive leases,
STOP, or a command timeout beyond the remaining lease reserve.

After reauthentication and a scoped lease, the current overlay-only check
from the repository root on Windows is:

```powershell
# Initialize the existing GCS backend only when needed on a new laptop.
python labs\vnet-vpn-custom-bgp\deploy\run_terraform.py init
python -X utf8 labs\vnet-vpn-custom-bgp\deploy\configure_overlay.py plan --stage backup
```

The final plan should be `[]`. For an approved actual change, inspect its
private saved plan before using `apply --stage backup`; the helper rechecks
the actual plan, rejects prerequisite writes, replacements and existing PSK
rotation, and applies serially. It targets only the LNG/IPsec resources to
avoid the known imported-Megaport provider drift. A full apply is still unsafe.
Do not run foundation/provider stages or use the historical `internet` stage
as the final routing design.

`guest --stage backup` installs the persistent CPE end state through pinned
host-key IAP SSH; it is a full installation, not an add-only live update.
For the specific healthy three-tunnel baseline,
`complete-internet --stage backup` writes the persistent four-tunnel files but applies only the new
Internet link/routes and BGP neighbor, without restarting sessions or reloading
FRR. Verify the baseline, existing key/file identities and private backups
before invoking it; retain an exact scoped rollback. The fourth tunnel is
already installed now, so do not replay this completed operation.
`inspect --stage backup` is read-only. This transport requires
the native Windows Google SDK and its PuTTY client. Before guest access on a
new laptop, reconstruct ignored `overlay-inventory.json` from authenticated
gateway/CPE reads (`gateway` and `cpe` objects), and
`cpe-serial-current.txt` from the CPE serial console. Verify its ED25519
fingerprint and authorize a task-local `cpe-key` through IAP; the helper uses
the resulting `cpe-key.ppk`. Do not bypass host-key checking or copy another
laptop's credentials.

The runners are Windows-specific and use Azure CLI, native Windows
`gcloud.cmd` when available (otherwise WSL `gcloud`) and
the foundation runner's Megaport key environment variables. Billing discovery
requires exactly one open GCP billing
account; ambiguity is an explicit error. On a new laptop it recovers the probe's
existing public SSH key from Azure, rather than planning VM replacement.
Missing local VPN keys are read from the existing Azure connections, not
silently regenerated. Only a genuinely new connection gets a generated key.
Tokens, PSKs, SSH keys, plans, raw state and diagnostics remain in ignored
runtime storage and must not be published.

## References

- [Configure BGP](https://learn.microsoft.com/en-us/azure/vpn-gateway/configure-bgp)
- [IPsec over ExpressRoute private peering](https://learn.microsoft.com/en-us/azure/vpn-gateway/site-to-site-vpn-private-peering)
- [Current Megaport API-key authentication](https://docs.megaport.com/api/api-key)
- [MCR order validation and pricing](https://docs.megaport.com/api/api-mcr/)
- Related but different platform: [vWAN lab](../vwan-ipsec-over-er-backup/README.md)
