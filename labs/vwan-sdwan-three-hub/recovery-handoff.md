# Compute recovery — history and current status

## Private mesh after deallocation — Tank, 2026-10-15 — BLOCKED

All four BIRD files retain the initial SHA256, ownership, mode and nanosecond
mtime. Closure readbacks show **8/18 BGP endpoint entries Established**:
two EU–US mesh entries and all six Azure entries. The other ten mesh entries
remain Connect. Japan still has two established IPsec SAs; no IPsec restart
or configuration change was performed.

WireGuard listen ports, public identities, endpoints, marks, table100 pins,
NAT rules and successful startup units were read directly. Packet headers prove
private UDP51820 initiation/response traffic reaches the routers. Failed EU
flows have no NAT mapping, but this does **not** prove the root cause.
An EU-only REDIRECT-to-explicit-DNAT hypothesis failed its 85-second handshake
gate and automatically rolled back. The startup script hash and three original
live REDIRECT rules were independently verified restored. No persistent fix is
claimed. No BIRD restore/reconfigure, cloud NSG change or IPsec write occurred.

Decisive ignored evidence: `show-output/mesh-reboot-recovery/`, especially
`eu-repair.json`, `eu-rollbackproof-parsed.json` and four
`*-mesh-closure-proof.json` files. One mutating Run Command contained the
attempt and bounded rollback; no further correction was attempted.
Lease `mesh-reboot-recovery-20261015.json` is blocked, with no active child.
A fresh owner/lease is required for further live correction.

Offline `restart_recover.py` now distinguishes missing exports from actual
non-baseline AS paths. Only an actual BIRD file hash/metadata difference can
authorize protected-file restoration; route/session loss alone cannot.
Seven targeted restart-recovery tests pass.

## Corrected guest activation — Trinity, 2026-10-14T18:00Z — PASS

One authorized protected ARM batch activated **all ten VMs**. Ten fresh actual
managed-command REST GETs returned Succeeded/exit0, `ACTIVATE_OK` and checksum/
service proofs. Final public listener files (0644, readable parent), WireGuard,
BIRD, JP StrongSwan/XFRM and JP probe-route files were persisted before enabling
their services; every applicable service is enabled and active.

Current router smoke: EU 5/5, US 5/5, JP 5/5, CN 3/3 BGP Established:
12 mesh sessions, four EU/US hub sessions, two JP VPN sessions. Raw BIRD
protocol/routes and JP SAs remain on each router under `/var/lib/threehub/`.
This is not a 4×3 scenario matrix or proof of end-to-end forwarding.

Original bootstrap backups were hash-verified unchanged. Protected final-file
archives/hash manifests, service proofs and seekable route snapshots are also
retained for subsequent fault rollback. No restaging, restore, infrastructure,
NSG/UDR, preference or routing-intent change. 33 regressions passed.
Ignored decisive evidence: `deploy\.runtime-control\guest-activation-proof.json`
and `guest-activate-results.json`. Activation lease completed: one mutation,
17 live CLI calls, owner idle, children zero. Niobe can verify independently
under a new read-only lease; do not reuse this completed activation lease.

## Guest restore recovery — Trinity, 2026-10-14 — COMPLETED

One corrected protected ARM batch **Succeeded on all ten VMs**. Each command
returned exit0, `RESTORE_FILES_OK` and JSON assertions proving archived file
checksums, equality with the original saved route snapshot, and recorded service
enablement. Systemd was reloaded; enabled services are active, router BIRD is
disabled/inactive. Original backups were reused, not replaced.

The original backup schema recorded enablement but **not historical active
states**. Current service states are explicit in
`deploy\.runtime-control\guest-restore-recovery-proof.json`; exact prior active
state cannot be claimed. Existing-route `File exists` messages came from
successful `ip route restore`; the independent snapshot equality assertion passed.

32 regressions passed. No activation, experiment, infrastructure change, new
HTTP gate, or retry. All commands terminal; no child or queued work remains.
The recovery lease is completed; Tank's original lease remains blocked and
his restore evidence is preserved under ignored `tank-guest-restore*` files.
Niobe may now read-only verify the original bootstrap baseline under a new
lease. Guest activation still requires its own fresh approval/lease.

## Guest routing — Tank, 2026-10-14 — BLOCKED, recovery required

Three actual ARM batches: stage **Succeeded** on ten VMs; activate **Failed**
on ten VMs; the single authorized restore **Failed** on ten VMs. Infrastructure
is unchanged. BGP establishment was not measured; do not start Niobe B0.

Actual router staging returned cloud-init done/no errors, package readiness
and successful `bird -p -c` parsing. Activation enabled persistent network,
WireGuard/BIRD and JP IPsec units, but local HTTP readiness returned **404**:
the public listener index was incorrectly mode0600 while its service runs as
`nobody`. The generator now uses0644 for public listener content only.

Restore stopped the services, removed overlay/XFRM/control routes, restored
archived files with checksum checks and restored iptables/sysctl. It then
failed at `ip route restore`: **`ftell: Illegal seek`**, because stdin was a
pipe. Daemon reload/re-enablement was consequently not reached. The generator
now supplies the saved route file as seekable stdin. These two corrections are
**offline regression-tested, not live retried**. No guest command remains
running. Lease is blocked; all ten restore instanceViews are terminal Failed.

Fresh, different recovery owner: finish only that bounded restore from
`/var/lib/threehub/backup.json`, `backup.tar`, and `routes.save`, reload systemd
and restore the recorded service states. Then Niobe may verify the original
bootstrap baseline read-only; guest activation requires its own fresh lease.
Minimal ignored evidence: `deploy\.runtime-control\guest-stage-results.json`,
`guest-activate-results.json`, `guest-restore-results.json`.

## Japan VPN recovery — Tank, 2026-10-14T17:08Z — COMPLETED

Gateway creation, real-instance APIPA update and VPN bindings all **Succeeded**:
three submissions, 59 live CLI calls, 21 targeted tests passing. Prior blocked
leases and ten VMs remain unchanged. Active gateway recovery lease is completed;
no CLI child or queued work remains. Infrastructure handoff contains sanitized
accepted resources and endpoints; this supersedes the binding block below.

Actual gateway-reported `Instance0` maps `169.254.21.2` to public
`20.27.135.137`; `Instance1` maps `169.254.21.6` to `4.190.54.71`.
Join `ipConfigurations[].id` to `bgpPeeringAddresses[].ipconfigurationId`:
each tunnel-address array also includes a private address, not just its PIP.
JP CPE `104.46.220.128`, ASN65013, local BGP `169.254.21.1` for both sessions.
Site/link/connection and gateway-scoped UDP500/4500 NSG rules succeeded.
`NotConnected` is expected until the separate guest objective, not an
infrastructure acceptance failure.

Repeatable controls: `gateway-update` performs one REST PUT using fully merged
live properties; `wait --deployments threehub-vpn-gateway-update` retains its
absolute deadline; `gateway-checkpoint` checks only JP acceptance. Always select
`--lease-file deploy\.runtime-control\gateway-recovery-lease.json` explicitly.
The ignored `deploy\.runtime-control\vpn.parameters.json` is the reusable guest
PSK source; never copy it into handoffs or git.

**Remaining guest objective:** separately lease six private WireGuard links,
filtered BIRD and two JP XFRM/StrongSwan tunnels on existing VMs; verify
installation and persistence only. No scenarios, firewall or routing intent
were executed, and optional guest HTTP readiness was not an infrastructure gate.

## Binding recovery — Trinity, 2026-10-14T16:17Z — BLOCKED

Fresh, scoped deployment exception; prior leases remain closed. **Three exact
ARM submissions**, no cancellation/retry: `threehub-vpn-gateway`,
`threehub-connections`, `threehub-hub-bindings`. No local child remains.

**Completed and directly GET-verified:** all five connections
`hub-eu/conn-transit-eu`, `hub-eu/conn-spoke-eu`,
`hub-us/conn-transit-us`, `hub-us/conn-spoke-us`, `hub-jp/conn-spoke-jp`;
two peers `hub-eu/bgp-router-eu` and `hub-us/bgp-router-us`; EU/US dynamic
NSGs accepted, retaining private WireGuard rules, bootstrap egress and deny-all.
ASN 65515, routing Provisioned on all hubs. Actual router addresses:
EU `10.250.0.69`, `10.250.0.70`; US `10.250.2.70`, `10.250.2.69`;
JP `10.250.4.70`, `10.250.4.69`. No router reset/base/compute resubmission.

**Blocked:** standalone minimum-scale JP gateway passed ARM validation but
failed resource acceptance: `BgpPeeringAddressesCountNotCorrectForVpnGateway`.
Two supplied custom mappings were rejected because gateway IP configuration
count was still zero. Gateway absent from final resource inventory. The
submitted gateway operation had its own deadline **16:53:20Z**, not the
canceled base deadline. It reached Failed; no running operation was inherited.
VPN site/connection were **not submitted**, no runtime PSK generated.

Decisive evidence (ignored): `deploy\.runtime-control\gateway-progress-check.stdout.json`;
accepted connections/peers:
`binding-recovery-deployments.stdout.json`, `binding-final-conn-*.stdout.json`,
`binding-final-bgp-*.stdout.json`. Sanitized current state and endpoint names
are persisted in `infrastructure-handoff.json`. Resources retained.

Generator correction is **offline only, not live validated/submitted**:
initial gateway creation no longer supplies invented `Instance0`/`Instance1`
custom BGP mappings. A **fresh recovery owner/lease** must create only the
gateway first, discover the real IP configuration IDs and tunnel PIPs, then
authorize a separate gateway update assigning custom `.21.2`/`.21.6` to those
actual IDs. After the update succeeds, existing `vpn-bindings` can create
one site/link with local `169.254.21.1`, both selected Azure addresses, and
gateway-scoped JP IKE NSG rules. Reuse its ignored `vpn.parameters.json` for
guest StrongSwan; do not expose PSK in handoffs/git.

`connections` is now a separate endpoint-independent control phase gated only
on routing Provisioned. `bindings` checks connection deployment Succeeded
before fresh BGP discovery. Fourteen targeted tests pass, including nested
ARM IDs, exact REST child paths, dynamic NSG overlay preservation, and absent
deny-only AzurePlatformDNS allows.

Guest bootstrap HTTP stays **INCONCLUSIVE and is not an infrastructure
prerequisite**. Guest BIRD/WireGuard/StrongSwan installation/configuration and
all scenarios/RI/firewalls remain outside this lease. Existing ten VMs/NICs/
NSGs, nine VNets and 26 peerings were not rerun.

## Platform DNS recovery — Tank, 2026-10-14

Removed only the unsupported `Allow AzurePlatformDNS` rule; platform DNS
bypasses normal NSG processing. Explicit deny-all and bootstrap Internet
TCP80/443 controls remain. Nine targeted tests cover the generator and completed
ARM operations with null target resources.

Corrected compute live validation and resource acceptance **PASSED**: ten NSGs,
NICs, VMs and disks, nine VNets, ten PIPs, two UDR tables and 26 directed
peerings. This does **not** establish guest readiness or lab acceptance.

The first bootstrap HTTP probe returned empty Run Command stdout/stderr.
Readiness is **INCONCLUSIVE**, not a proven guest failure. No repair retry was
performed. Actual hub GETs returned `Updating`, routing state `None`, and empty
router IP arrays; hub/VPN bindings were therefore never submitted.

The new NSG recovery lease is **BLOCKED**. One bounded stop canceled the
inherited base deployment, without restarting its 16:24Z deadline. Created
resources remain preserved; previous blocked leases remain unchanged.
`infrastructure-handoff.json` records sanitized IDs and runtime endpoints;
decisive raw output is ignored under `deploy\.runtime-control\`.
All local CLI children terminated. A separate owner/lease must establish
bootstrap command execution/readiness and resume only approved missing
infrastructure. Guest BIRD, WireGuard and StrongSwan configuration remains
missing; no preference experiments, firewall or routing intent occurred.

## Previous compute recovery — Trinity

Trinity, 2026-10-14, separate recovery lease. Original Tank lease preserved blocked.

Corrected compute **live ARM validation passed** before the single compute
submission. Resource acceptance then failed on all ten NSGs:
`SecurityRuleInvalidAccessType` — supplied `Allow`, permitted `Deny`.
No retry, endpoint binding, guest configuration, firewall or routing-intent
mutation followed.

Closure inventory: nine VNets, ten bootstrap PIPs, two UDR tables and 26 directed
peerings succeeded. No NSGs, NICs or VMs provisioned. vWAN exists; base deployment
remains `Running`, with hub operations running and VPN gateway not yet created.
Its inherited absolute deadline remains **2026-10-14T16:24:00Z**; never restart it.
See `infrastructure-handoff.json` for sanitized inventory and operation states.
Full minimal evidence is ignored under `deploy\.runtime-control\`.

Recovery used **one ARM submission**, separate from two prior RG/base mutations.
All local monitor/CLI processes terminated. Resources retained per lease restore
contract; no deletion or follow-up queued.

## Explicit lease selection

`deploy.ps1` accepts `-LeaseFile`; `control.py` accepts `--lease-file`.
Selection is restricted to this lab's `.runtime-control` directory and never
reactivates the original lease. Phases `bindings` and `vpn-bindings` validate
before submission. The VPN PSK is generated only into the ignored parameters
file; tracked templates contain a secure parameter reference, not the key.

The static binding generators require actual hub router IPs/ASN and gateway
instance/custom-address mappings. They create five hub VNet connections and two
correctly named BGP child resources; Japan uses one VPN link, local BGP
`169.254.21.1`, two selected Azure custom addresses, and gateway-scoped IKE rules.
Seven local tests pass. These binding phases have **not** been live validated or
submitted.

## Historical next objectives — superseded by binding recovery above

1. Fresh owner/lease must take over or stop the still-running base operation
   before its unchanged deadline. Resolve the NSG acceptance error and authorize
   a corrected compute live-validation gate before any new submission. Bind
   discovered hub/VPN endpoints only after provisioning succeeds.
2. **Guest lease remains blocked** until that infrastructure gate passes.
   Subsequently configure six private WireGuard links, filtered BIRD forwarding,
   and two JP XFRM/StrongSwan tunnels from discovered endpoints/runtime secrets.
   Verify installation/persistence only; no preference experiment, 4×3 scenario
   matrix, firewall or routing intent in that objective.
