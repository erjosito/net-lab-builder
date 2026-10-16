# A ↔ T bounded public-IPv4 transfer

**Current status: live transport PASS, restored baseline PASS, billing
INCONCLUSIVE (updated 2026-10-16 UTC).** See the
[completed cross-tenant result](../results/2026-10-15-cross-tenant-public-ip.md).
The implementation/review phases below were offline; the later live run was not.
Only A (Windows CLI context) and T (native Ubuntu-24.04 WSL CLI context)
participated in that completed headline. The optional one-way C/B control below
is separate: **v4 transport/restoration PASS**, **1 GiB C/NE → B/SC**,
one upload, zero retries; **billing remains pending**. Earlier v1/v2/v3
failures/blocks remain historical; defaults
remain A/T bidirectional. Python 3 standard library; existing OpenSSL
is required locally for certificate generation. No package installation,
SSH, authentication changes, profile copying, or arbitrary endpoints.

## Contract and deliberate concurrency change

Both HTTPS connections originate at A and terminate on T: upload produces
**5,368,709,120 bytes at A**, download produces **5,368,709,120 bytes at T**.
One client invocation runs **exactly two concurrent HTTP requests, one in each
direction**, rather than the old design's concurrency-one sequencing. Each
direction retains the original 20 Mbit/s (2,500,000 bytes/s) rate and 5 GiB cap.
The approximately 35.8-minute bulk interval therefore fits a 60-minute live
lease with restoration reserved; TCP initiator is not the byte producer.

The guest uses mTLS, an ephemeral private CA, IP SAN verification, TLS ≥1.2,
HTTP/1.1, no cache/compression, exact paths and one-use IDs. Payload blocks are
SHAKE256-derived from a fixed seed and block offset, bounded to 64 KiB, streamed
without disk storage. Each endpoint records incremental SHA256 and exact counts.
Upload acknowledgement is written only after the server's private record;
download hash is checked against the server's literal header and final report.
Two worker slots, 32 lifetime connection attempts, 60-second socket timeout,
40-minute total guest deadline, 2,450-second guest process timeout and
2,500-second local RunCommand limit bound execution. These are **tighter** than
the requested 45-minute transfer / 50-minute listener maximums.

Client readiness uses at most 12 authenticated **handshake-only** probes before
either HTTP request. Probe timestamps, statuses and zero payload bytes are
separate from bulk records. The successful handshake's connection is reused for
upload, avoiding an extra probe racing with the two-slot limit. Certificate/TLS
failure stops readiness immediately. Neither bulk request is ever retried. A failed
request cancels its peer and closes both sockets; server errors stop the listener.
Guest commands run in the foreground, not as detached services.
The local wrapper writes a private running heartbeat every 30 seconds during
each long command; the guest socket/total deadlines enforce actual progress.

Each endpoint reads Linux `/sys/class/net/<interface>/statistics/{rx,tx}_bytes`.
Use **A's RX + TX delta once**, never A plus T. Stop at A's 12 GiB aggregate
NIC delta; the same conservative cap is also applied at T. Preserve the core
35 GiB global allowance by supplying its **actual remaining** value; preparation
requires ≥12 GiB remaining. The MSDN 10 GiB payload reserve plus existing overhead
headroom is unchanged; this is not approval to enlarge either $8/$4 budget.

## One-way core positive control

### v4 correction and subsequently verified live result

[Full v4 result and cleanup](../results/2026-10-15-cross-region-control.md):
live **15 October 23:06:00–23:19:39Z**, bulk **23:08:23–23:15:32Z**,
exactly **1,073,741,824 bytes**, matching SHA256, zero retries.
C NIC RX+TX once **1,085,524,745 bytes** corroborates transport, not billing.
Live owner **48 calls / 10 mutations**; independent PASS at **23:25:22Z**,
**11 reads / 0 mutations**, both VMs deallocated, both original NSG policies
and exact associations verified, native children idle.
The corrected source passed **100 WSL tests**; no Windows-suite pass is claimed.

Read-only v3 subnet evidence establishes an additional **B subnet NSG**: no
custom rules, hence default inbound deny at 65500. The temporary NIC allow alone
cannot admit C→B TCP443. C's subnet has no NAT gateway/UDR and permits Internet
outbound through its default rules. Both extra subnet NSG roots and their VNet
parents carry the exact existing lab/creator/run tags; the private inventories
now record those observations, without resource creation, adoption or retagging.

Every new snapshot follows each endpoint NIC's exact subnet reference, verifies
its VNet parent and attached NSG against the authoritative owned inventory, and
binds both original policies, contexts and NIC/subnet associations to readiness
and source hashes. Unknown policy, missing ownership or foreign run fails closed.
The receiver subnet's exact peer `/32` TCP443 allow at priority 100 is installed
and read back `Succeeded` **before** the NIC allow (original NIC deny retained at
200); both gates must pass before either guest is submitted. Restoration follows
fresh bound deallocation proof for both guests, submits once per original NSG
**before polling either layer**, and polls exact semantics, `Succeeded`, tags and
associations within the original shared 900 seconds. Both deallocations and each
layer's authorization/reads/PUT have bounded fair allocations; a failed or timed-out
submission cannot skip the other layer while budget remains. Any failure is logged
and blocks closure, even if another restoration succeeds. No PUT is retried.
A shared NIC/subnet NSG is written only once per phase; an
absent subnet NSG adds no write. A/T receives the same discovery/protection,
without changing historical sources/results or its default payload/budget.
Known service-managed children are not new mutable roots.

Historical explicit v4 preparation (completed later under separate leases;
do not replay after cleanup):

```powershell
python labs\azure-bandwidth-billing\transfers\run.py prepare --control --run control-cb-20261015-v4 --control-payload-bytes 1073741824 --core-remaining-bytes 5368709120
```

`--control-payload-bytes` is prepare/one-way-control only: positive integral bytes
up to the unchanged default 5 GiB. The wire reservation is 120% of payload,
rounded up to whole GiB: **1 GiB payload → 2 GiB cap**, leaving **3 GiB** from a
5 GiB core remainder; default **5 GiB → 6 GiB** is unchanged. At 2,500,000 B/s,
1 GiB takes about **429.5 seconds**, approximately **$0.02147** at $0.02/decimal GB
before overhead. Exact declared count/hash/aliases/legs and wire cap are checked
against the plan, not a fixed 5 GiB count. No new MSDN/A/T bulk budget is enabled.
Fresh preparation, source-bound readiness and snapshot, independent review and
separate authorization were completed for the verified v4 run. Readiness remains six mutations; live expects ten with two
distinct NSGs, at most twelve reserved, including `allow-subnet` and
`restore-subnet-nsg`. The 60-minute/150-call/3000-second lease, named 2500-second
guest bounds, 180-second first-request stop, 90-second read clipping and
3400-second submission/900-second restoration reserves are unchanged. Extra
policy reads/writes spend the same 200-second setup margin and must block if slow.

**C → B expected-charged transport PASS; billing INCONCLUSIVE.**
C was Standard_B2ts_v2 in an isolated North Europe owned RG, now deleted. P's
VM/disk/NIC/dedicated NSG were retired first; shared networking and A/B were
preserved at that point. The original design already planned C in North Europe. The
minimal amendment uses **C (client/producer, North Europe) → B (server/receiver,
Sweden Central)**, default one declared upload leg of **5,368,709,120 bytes**;
v4 explicitly selected **1,073,741,824 bytes**. Both were
Linux guests managed by the existing **Windows native CLI core context**.
C has a **new independently owned/tagged RG**; B keeps its existing PIP.
No fake A/T aliases, WSL subscription, new A bulk or MSDN payload is used.
B returns only bounded JSON acknowledgement plus TLS/TCP/protocol traffic.
The server rejects any undeclared GET before producing bulk. One authenticated
connection is reused for the upload; no HTTP bulk retries. Default A/T callers
continue to declare both legs implicitly. Native CLI platform is bound per
endpoint, not inferred from server role.

**Attribution and budget:** C's isolated RG/day can carry a known-charge
Europe inter-region outbound producer meter without mixing it into A's
headline RG. B's reverse protocol egress remains a small shared-RG contaminant,
not a second 5 GiB bulk leg or a claimed zero. Use C RX+TX once (not C+B) as
corroboration, with a **6 GiB per-endpoint wire hard cap**. Reserve 6 GiB per
default-size attempt: **35 − 12 headline − 6 v1 − 6 v2 = 11 GiB**
was the historical post-v2 remainder. The reconciled pre-v4 remainder was
**5 GiB**; its explicit **2 GiB wire** reserve left **3 GiB
(3,221,225,472 bytes)**. This is reservation accounting, not actual payload
consumption or authority for another transfer. The old
17 GiB remainder was before v2; it must not be reused. This is stricter than the original 12 GiB
per-run ceiling and does not authorize a 12 GiB fallback. At the recorded planning
price $0.02/decimal GB, 5 GiB outbound is approximately $0.1074 before overhead.
Fresh applicable price and whole-core $8 / $0.08-hour checks remain mandatory;
MSDN stays inside its separate $4 cap with no new traffic.

The ~35.8-minute leg retains 20 Mbit/s, mTLS/IP-SAN, one-use IDs, exact counts/
SHA256 at both ends, streaming 64 KiB blocks, 40-minute guest deadline and
2,500-second RunCommand limits. Fresh live lease **at most 60 minutes**,
900-second restore reserve and the original ~200-second setup margin remain.
Stay awake with a named independent recovery owner; local execution cannot
guarantee restoration during laptop sleep. Neither resource TTL nor 12h/slot
allocated-time limits are extended. C shares P's original slot, not a fourth
retained core slot. Stop if there is insufficient inherited slot-hour headroom.
The inherited whole-core envelope was **$7.954831 < $8**, not measured spend.
Pre-control, C had roughly **2h of its inherited slot before deducting readiness and ~5m
setup**; reconcile actual lifecycle records before proposing new work.

### Closed control attempts and independent restoration

| Phase | Outcome | Decisive evidence |
|---|---|---|
| C deployment and P replacement | **PASS** | North Europe C allocated/deallocated; P VM/disk/NIC/dedicated NSG removed, shared network retained. |
| v1 live, 17:28:50–18:13:46Z | **FAIL** | 12 connection/TLS timeouts, zero bulk requests/retries, C RX+TX once **284,630 bytes**. `Updating` alone did not establish causation; later v3 inspection identified B's additional subnet default deny. |
| v2 fresh readiness | **PASS** | Source-bound fresh readiness passed; this is not transport success. |
| v2 guarded live | **BLOCKED before guest commands** | NIC read timeout, no server/client submission, **0 payload**, no guest NIC report; final NSG GET timeout left restore initially unverified. |
| Fresh independent Niobe restoration | **PASS** | **5 reads, 0 mutations**; exact original B NSG policy/all rules `Succeeded`, expected NIC association, B/C deallocated. Native process-idle proof **19:06:07Z**. |
| v3 historical outcome | **Transport FAIL; billing INCONCLUSIVE, unchanged** | Subsequent read-only subnet inspection identified the additional B NSG default deny at 65500; NIC-only allowance was insufficient. |
| v4 live | **Transport/restore PASS; billing pending** | **1 GiB**, one upload, zero retries; original NIC/subnet NSGs restored `Succeeded` at **23:19:00 / 23:19:23Z**. |
| v4 independent Niobe | **PASS** | **11 reads / 0 mutations**, both VMs deallocated, both original policies and exact associations, idle proof **23:25:22Z**. |

No active children or additional transfer is queued. Known-owned cleanup closed
PASS **16 October 00:00:11.806224Z**: 13 remaining original core assets absent,
C/T groups gone, all known VMs/disks/PIPs deleted. **Core RG and an extra
NSG were preserved**, independent creation ownership unproven; do not
adopt/delete. No standalone RG/NSG hourly rent. The historical FAIL/BLOCKED
verdicts are not rewritten. v4 tooling has **100 passing WSL tests**.

### Historical deployment/preflight recipe (not queued work)

**Completed prerequisite:** P's VM/disk/NIC/dedicated NSG are gone, retaining
shared VNet A and all A/B resources. The following recipe records the earlier gates.
`Control.ps1` refuses deployment while any P resource remains; it never deletes
P. Do not run it to redeploy the existing C or reset the inherited slot.
No region/Spot/SKU substitution or extra-cost work is authorized.

Use separate preflight and deployment phases, never this offline build lease.
All commands below run in PowerShell from repository root, with existing native
Windows tokens and explicit subscription through `Common.ps1`. No `az login`,
`account set`, WSL, package installs, or shared profile copying.
Each child command is bounded. The coordinator must activate the named lease
before each phase, check STOP and prior owner/process idle, then close it.

Preflight lease path `deploy\.runtime-control\control-preflight-lease.json`:
30 minutes, <=75 calls, `maxMutations=6` (one `create-c-group`,
up to five explicitly named `validate-<SKU>`), command <=180 seconds; no VM
allocation, payload, NSG changes or deletion. The 80% boundary still applies:
if five submissions are consumed, close and obtain a fresh bounded preflight
lease for the next rank; do not raise the counter budget or recreate the RG.
Catalog and live-capacity evidence must pass **in order**:
`Standard_B1ls → Standard_B1s → Standard_B2ts_v2 → Standard_B2ls_v2 →
Standard_B2s_v2`, all **northeurope**, Ubuntu 22.04. Do not skip cheaper ranks.
D-series or a price/region/lifetime increase needs approval.

```powershell
. .\labs\azure-bandwidth-billing\deploy\Common.ps1
$script:LeasePath = (Resolve-Path 'labs\azure-bandwidth-billing\deploy\.runtime-control\control-preflight-lease.json').Path
$core = Get-Content labs\azure-bandwidth-billing\private\context.private.json -Raw | ConvertFrom-Json
$rid = 'bwb-' + [guid]::NewGuid().ToString('N').Substring(0,12)
$c = @{runId=$rid;resourceGroup="rg-$rid";subscriptionId=$core.subscriptionId;expectedTenantId=$core.expectedTenantId}
$cp = (Join-Path (Resolve-Path labs\azure-bandwidth-billing\private) 'control-context.private.json')
Write-PrivateJson $c $cp
Assert-Context $c
[void](Invoke-Mutation -Context $c -Arguments @('group','create','--name',$c.resourceGroup,'--location','northeurope','--tags','lab=true','created_by=copilot-lab',"run_id=$rid") -TimeoutSeconds 120)
$sku = 'Standard_B1ls' # repeat only next approved rank if this rank's gate fails
$catalog = Invoke-LabAz -SubscriptionId $c.subscriptionId -Arguments @('vm','list-skus','-l','northeurope','--resource-type','virtualMachines','--size',$sku) -TimeoutSeconds 120
Write-PrivateJson $catalog "labs\azure-bandwidth-billing\private\control-catalog-$sku.private.json"
# Inspect exact name and all restrictions. No row or applicable restriction is FAIL.
$key = (Get-Content "$HOME\.ssh\id_rsa.pub" -Raw).Trim()
$capacity = Invoke-Mutation -Context $c -Arguments @('vm','create','-g',$c.resourceGroup,'-n',"$rid-capacity-probe",'-l','northeurope','--image','Ubuntu2204','--size',$sku,'--admin-username','azurelabuser','--ssh-key-values',$key,'--validate') -TimeoutSeconds 120
Write-PrivateJson $capacity "labs\azure-bandwidth-billing\private\control-capacity-$sku.private.json"
```

Do **not** call live validation for a catalog failure. Retain each rank's result/
explicit failure privately in `control-ladder.private.json`, including UTC, exact
SKU, restriction checks, command outcome and selected cheapest passing rank.
The helper validates this schema: `runId`, `subscriptionId`, `region="northeurope"`,
`attempts` in the exact ladder order with no skipped rank; each entry contains
`vmSize`, `observedUtc`, `outcome` (`catalog-failed`, `capacity-failed`, or `passed`),
`catalogPassed` and `capacityPassed` booleans, plus private raw evidence paths.
Only the final selected rank may be `passed`, with both booleans true; earlier
ranks must explicitly fail one gate. All observations must be <=1h old.
Validation is not a guarantee of real allocation: `SkuNotAvailable` on actual
deployment is BLOCKED; inventory and deallocate, no automatic redeployment.
Preflight group must be empty and newly owned; its creation does not reset TTL.

After both gates pass, create these **private** files with `Write-PrivateJson`:

- `control-gate.private.json`: `runId`, `region="northeurope"`, selected `vmSize`,
  `catalogPassedUtc`, `capacityPassedUtc` (both <=1h old, not future),
  absolute `ladderEvidencePath`, current `infraUsdPerHour<=0.08`,
  `lifetimeEnvelopeUsd<=8` (whole core, including existing rent/traffic),
  `slotAllocatedHoursRemaining` in [1,12] from the inherited P/C slot ledger,
  `coreRemainingBytes=24696061952`, and `cleanupDeadlineUtc` set to the
  **earliest original core deadline**, no later than **2026-10-18T07:33:00Z**.
- `control.params.private.json`: standard ARM deployment-parameters document,
  `parameters.runId.value`, `parameters.vmSize.value`, and
  `parameters.adminPublicKey.value=$key`. Always a JSON file, never inline
  deployment `key=value` arguments.

Fresh deployment lease `control-deploy-lease.json`: 30 minutes, <=75 calls,
`maxMutations=3`, `allowedMutations=["validate-c","deploy-c","deallocate-c"]`,
command <=600 seconds (validation120, allocation600, restore180), restore15m.
Helper requires >25 minutes left before beginning, preserving allocation+restore.
The preflight group-create submission is in the **closed prior** lease.

```powershell
.\labs\azure-bandwidth-billing\deploy\Control.ps1 -ContextPath labs\azure-bandwidth-billing\private\control-context.private.json -GatePath labs\azure-bandwidth-billing\private\control-gate.private.json -ParametersPath labs\azure-bandwidth-billing\private\control.params.private.json
```

The helper derives the smallest C template from existing `msdn-main.json`,
changing only suffix/region and the approved B-series ladder. No Spot, bootstrap,
new networking service or inbound allow is added. It checks Windows core context,
owned empty C RG, P retired and A/B deallocated; preserves partial inventory;
attempts owned C deallocation even if deployment fails; verifies deallocation.
Output `private\control-inventory.private.json` schema: `runId`, exact `groupId`,
`cleanupDeadlineUtc`, `createdByThisRun`, resource-list `resources` including
exact IDs/tags/location/name/type, generic ARM `detailedResources`, and
`receiverPublicIP` from B's native PIP show (exact ID, tags, location, `ipAddress`).
The core inventory has no detailed PIP IPs, so this explicit receiver observation
is required; never edit original core/v3 evidence to fill it in.

### Readiness, snapshot and live contract (historical examples)

The examples below describe the closed v1 workflow. Their byte argument is
historical, not the final conservative **3 GiB** reserve; do not replay old run IDs.
Any future proposal needs a new approved owner/lease, reconciled hours/bytes,
fresh source-bound readiness and independent baseline verification.

```powershell
$run = 'control-cb-20261015-v1' # historical one-shot directory; do not replay
python labs\azure-bandwidth-billing\transfers\run.py prepare --control --run $run --core-remaining-bytes 24696061952
```

This offline preparation requires the above real C inventory; it does not fake
resources when C is absent. It generates certificates with B's IP SAN, exact
Windows-native argv and three **inactive** phase templates. Activate each using
the existing coordinator activation procedure below, with `$run` set here.
Use only `transfer-live-lease.json`, never another active lab lease:

| Phase | Owner / time | Exact allowed mutations |
|---|---|---|
| readiness | Tank / 30m, max6 | start-c, start-b, ready-c, ready-b, deallocate-b, deallocate-c |
| snapshot | Niobe / 30m, max0 | none |
| live | fresh Tank / <=60m, max12 | start-c, start-b, allow-subnet (if distinct), allow, server, client, restore-nsg, restore-subnet-nsg (if distinct), deallocate-b, deallocate-c |

```powershell
python labs\azure-bandwidth-billing\transfers\run.py readiness --run $run
# Close/verify readiness, activate separate read-only snapshot lease:
python labs\azure-bandwidth-billing\transfers\run.py snapshot --run $run
# Close snapshot, activate fresh live lease immediately; snapshot age <10m:
python labs\azure-bandwidth-billing\transfers\run.py live --run $run --accept-live-gates
python labs\azure-bandwidth-billing\transfers\run.py verify --run $run
```

Fresh source/context/VM/disk/NIC/route/readiness bindings are mandatory.
Snapshot enforces C=NE, B=SC, equal core tenant/subscription, exact resource IDs/
tags/associations and separate C RG. Only B's owned NIC/subnet NSGs get C/32 TCP443; B/C are
independently deallocated and verified **before** the exact original NSG
rules/metadata are restored; see the bounded-drain gate below.
Restoration submits exactly one PUT per distinct original NSG, then polls read-only at intervals of
at least 30 seconds. Verification requires the exact original NSG identity,
normalized custom rules and metadata, parent and every custom rule `Succeeded`,
and the original receiver NIC's NSG association. The shared 900-second restore
reserve starts before endpoint deallocations; authorization, PUT and polling
must all fit that remaining reserve and the original lease expiry. STOP, a
failed/canceled/unknown state, mismatch, read timeout or insufficient budget
leaves restoration unverified and live closure `blocked`, without a PUT retry.
Unresolved restoration needs a different recovery owner and lease.
Ordinary Azure reads (including native-context authorization and snapshot/
readiness queries) have a **90-second maximum**, not 30 seconds. Allow-gate
NSG/NIC reads use the minimum of 90 seconds, the remaining 180-second gate,
and lease time remaining minus the unchanged 3,400-second submission reserve.
Live setup/guest authorization is clipped to that same submission margin;
each guest submission rechecks the full reserve after authorization and local
preparation. Restore authorization/readback uses at most 90 seconds within
the original shared 900-second deadline and lease closure margin; no clock
is reset. Phase mutations remain bounded at 180 seconds, with no retry.
This source revision invalidates earlier source-bound readiness; historical
reports are unchanged. A new independent offline review must precede any fresh
readiness, snapshot or live phase; this revision does not authorize those phases.
No second bulk in A's RG on 15 October. Live attestation additionally covers
day boundary, measured remaining hours/whole-core prices, no concurrent producer,
earliest TTL and awake/recovery coverage; it is not authority to enlarge limits.

**Decisive billing requirement:** after mature same-offer/feed detail, C must
show attributable inter-region outbound **quantity >0**, correct unit/rate/meter
and reconciled usage dates. Capture C RG/day and sender resource IDs, B reverse
overhead separately. Follow the existing 24/48/72h/day7 cost collection procedure
with C's isolated RG/inventory and actual control usage date. A Windows control
cannot prove MSDN feed completeness; 429 is never empty. No rows, credits, zero
cost or transport PASS alone never prove exemption. Cleanup by the original
deadline and query preserved historical IDs later.

## Offline preparation and tests

The preparation example below is historical, not today's available allowance.
After v2, conservative core remaining was **11 GiB**. The reconciled pre-v4
remainder was **5 GiB**; v4's 2 GiB wire reserve left **3 GiB**.
This is not actual payload use. **Do not execute another A/T
bulk run:** T's approved 10 GiB payload reserve is consumed; more requires approval.

From repository root, PowerShell:

```powershell
python -m unittest discover -s labs\azure-bandwidth-billing\transfers -p test_stream.py -v
python labs\azure-bandwidth-billing\transfers\run.py prepare --run saas-20261015-handoff --core-remaining-bytes 37580963840
```

The prepared `saas-20261015-handoff` directory already exists; preparation
intentionally refuses to overwrite it. Use a new run name if regenerating.
The last argument above is valid only while no earlier core traffic has consumed
the allowance. Preparation makes **zero Azure calls**, reads only approved
private inventories/contexts, and writes only `private\transfers\<run>\`:

- `plan.private.json`: private identities, caps and endpoint bindings;
- `commands.private.json`: exact argv manifests before native path conversion;
- `tls\`: one-day CA/server/client certificates and private keys;
- `readiness-lease-template.private.json`, `snapshot-lease-template.private.json`,
  `live-lease-template.private.json`: three inactive, separate phase templates.

Keys and reports are ignored by the lab's existing `.gitignore`. No actual
identity, IP, key or resource name is present in this directory's source.
Windows uses the installed Azure CLI Python entrypoint with argument arrays;
WSL uses `/usr/bin/az` behind its native bounded `timeout`, with native tokens
remaining in WSL. Every Azure invocation has explicit `--subscription`.

## Incident review and corrected three-phase handoff

The first execution was **BLOCKED before transport**, not a transport failure:
29 read-only calls consumed the initial execution lease; 3,392.904 seconds
remained against the unchanged 2,500 + 900 = 3,400-second requirement.
Guest tools, interface, routing and RunCommand readiness were not yet attested.
There were zero mutations, payload bytes and bulk retries. The prior private
verdict records exact NSG equality and both endpoints deallocated at closure.
Do not reuse that blocked plan as a new live attempt.

**Do not execute under the offline review lease.** Prepare a **new run** using
the unchanged actual remaining wire allowance. This creates the new templates;
old prepared runs do not contain them. All phases use the dedicated
`deploy\.runtime-control\transfer-live-lease.json`, never another lab's lease.
Each preceding owner must be idle, its commands terminated and its lease closed
before the coordinator assigns the next phase. No concurrent lab producer.

The coordinator activates **one** template at a time as follows (PowerShell,
repository root; substitute the new run name). Activation is a coordinator
operation only after the prior lease is closed; it must never clear STOP or
overwrite an active lease:

```powershell
$run = 'saas-20261015-readiness-v2'
$private = "labs\azure-bandwidth-billing\private\transfers\$run"
$control = 'labs\azure-bandwidth-billing\deploy\.runtime-control'
$phase = 'readiness'  # then snapshot, then live, under separate owner dispatches
$minutes = if ($phase -eq 'live') { 60 } else { 30 }
$lease = Get-Content "$private\$phase-lease-template.private.json" -Raw | ConvertFrom-Json
$start = [DateTime]::UtcNow
$lease.startedAtUtc = $start.ToString('o')
$lease.expiresAtUtc = $start.AddMinutes($minutes).ToString('o')
$lease.state = 'active'
$lease | ConvertTo-Json -Depth 10 | Set-Content "$control\transfer-live-lease.json" -Encoding utf8
```

### 1. Guest readiness: separate 30-minute preflight lease

Exact `allowedMutations` and `maxMutations=6`:

```json
["start-a","start-t","ready-a","ready-t","deallocate-t","deallocate-a"]
```

```powershell
python labs\azure-bandwidth-billing\transfers\run.py readiness --run $run
```

This captures owned deallocated VM/NIC/PIP/NSG bindings, starts A/T concurrently,
and submits **one read-only foreground RunShellScript per guest**. The script
checks existing Python ≥3.8, SSL/HTTP imports, GNU `timeout` invocation, `ip -j -4
route get <literal-peer>`, exact chosen interface MAC and route source matching
the Azure NIC's MAC/private IPv4, and current RX/TX counters. It fingerprints
the existing tool executables. There is no package installation, payload,
SSH, NSG PUT, guest file creation or detached process in these probes.
`ip route get` performs a local route lookup, not a network probe.
RunCommand itself is still counted as a mutation submission.

The guest probe is capped at 30 seconds, each local Azure call at 180 seconds;
the existing 900-second restore reserve still applies. In `finally`, both
deallocations are attempted once and verified individually. No NSG write is
needed because the NSGs were never changed. The lease closes completed or
blocked, with process-idle state. The private `readiness.private.json` must
record success, both verified deallocations, reports, actual parallel boot time,
and bindings to run ID, native contexts, VM IDs/storage profiles, NIC identity,
peer addresses, interface and source-code hashes. Evidence expires after 24h;
any binding change requires a new run/readiness phase. A failed readiness
attempt is not retried in place. Unverified deallocation means BLOCKED and a
fresh recovery owner, not permission to proceed.

### 2. Fresh snapshot: separate 30-minute read-only lease

Exact `allowedMutations=[]`, `maxMutations=0`:

```powershell
python labs\azure-bandwidth-billing\transfers\run.py snapshot --run $run
```

Snapshot checks native context, owned resource identities and deallocated
baseline again, prepares the original NSG restore body and captures both metric
baselines. It requires **no guest-tools assertion or guest command**, starts no
VM and writes no Azure resource. Zero-mutation leases are supported explicitly.
It closes its lease completed or blocked. Snapshot freshness is measured from
the beginning of resource observations, **not** the end of metric collection.
Only a completely successful snapshot publishes its timestamp.
Azure Monitor requires an interval of at least one minute: metric queries use
the earlier of the observation start and one minute before the query end.
This bounded lookback is corroborative telemetry, not a guest byte baseline or
a change to snapshot freshness. Query errors remain fatal, preserve the service
error and exact native argv in private error evidence, and publish no snapshot
timestamp; missing metrics are not silently accepted or retried.
Snapshot writes inert guest-script placeholders; `server`/`client` replace
them with checked scripts only after validating persisted readiness. Invoking
an unvalidated placeholder directly fails without starting a payload.

### 3. Live execution: fresh 60-minute lease immediately after snapshot

Reserve **10 mutation submissions**, exact `allowedMutations`:

```json
["start-a","start-t","allow","server","client","restore-nsg","deallocate-t","deallocate-a","emergency-deallocate-t","emergency-deallocate-a"]
```

| Operation | Count |
|---|---:|
| `start-a`, `start-t` | 2 |
| `allow` (one NSG PUT: peer-only 443 at 100, original deny at 200) | 1 |
| `server`, `client` (foreground RunCommand, concurrent) | 2 |
| `restore-nsg`, `deallocate-t`, `deallocate-a` | 3 |
| `emergency-deallocate-t`, `emergency-deallocate-a` recovery reserve | 2 |

Normal path is **8 mutations**, with two explicitly named recovery reserves,
not automatic bulk retries. An emergency is handled by a named recovery owner;
the wrapper does not silently consume those reserves. CLI errors are private.
No new work at 80% of elapsed/call/mutation budget; restore-only operations
remain available while the lease is active and STOP is absent.

```powershell
python labs\azure-bandwidth-billing\transfers\run.py live --run $run --accept-live-gates
```

Live requires the completed readiness evidence with unchanged bindings and a
snapshot <10 minutes old. Only the known single deny-100 baseline is accepted.
T's literal PIP must match its certificate, and A's observed PIP is bound into
the expected-peer check. The two foreground guest scripts rerun the tool hashes,
versions, NIC identity, route/source and stats checks **before materializing
keys or starting any payload process**. Differences fail closed. The current
guest counters become new transfer baselines; preflight counters are never
subtracted across deallocation/reboot.

Before attesting, the live owner must independently confirm:

- A/T ownership, native tenants unequal, both Sweden Central, expected PIP/NIC
  associations and routes; no other bulk producer/RG scenario that UTC day;
- expected source at T is A's PIP; the listener checks the actual source before
  accepting payload (not a claim of a prior observed connection). Literals avoid
  DNS redirects; certificate SAN binds the literal T address;
- A/core and T allocated-hour limits ≤12 each, budgets $8/$4 unchanged,
  ≥12 GiB core wire allowance remaining, enough same-UTC-day time and the
  unchanged 72-hour resource TTL. Include readiness boots in allocated-hour
  and cost accounting;
- successful persisted readiness for the chosen NIC interface (`eth0` by
  default; change private plan `interface_server/interface_client` **before
  readiness**, never attest an unobserved guest tool);
- expected NSG write role from the prior exact-resource deployment. **GET does
  not prove PUT permission**. Actual PUT can fail safely; no new role assignment,
  permission escalation or apt/pip bootstrap is authorized.

The orchestrator starts A/T and installs the independent peer-only T rule
concurrently. The allow branch must then pass the bounded NSG readback gate
below before either guest is submitted. After concurrent server/client execution
and report verification, `finally` attempts both verified deallocations once,
then restores the original NSG once. If a payload may have been submitted and
either deallocation cannot be verified, NSG restoration is blocked pending a
named recovery owner; local CLI completion is not proof of guest quiescence.
It checks exact original security-rule equality and `PowerState/deallocated`.
Metric windows are collected afterward. No A inbound rule is added.
**Quantitative timing gate:** 3,600 − 2,500 − 900 = **200 seconds** are available
for all local setup, boot/NSG submission and per-command authorization before
each RunCommand starts. Read-only snapshot/metrics no longer spend that clock.
Parallel boot/allow removes their additive latency. Each setup branch has a
30-second context check plus a 180-second submission bound, so the conservative
setup bound is 210 seconds, plus up to 30 seconds for RunCommand authorization
and local overhead. **Offline evidence cannot certify this worst case fits.**
Actual setup must finish sufficiently below 200 seconds to leave both
authorizations time; the preflight's measured boot time is useful evidence,
not a guarantee about the subsequent boot or NSG PUT. Plan records actual
`setup_seconds`; guards are checked again before both long commands and after
their authorization, inside the submission lock. Slow setup **BLOCKS**, restores and closes without any
extension or bulk retry. The payload minimum is 5,368,709,120 / 2,500,000 =
2,147.484 seconds concurrently, below the unchanged 2,400-second guest deadline
and 2,450/2,500-second process/local bounds. This correction removes the known
clock misuse; runtime ARM latency remains a real acceptance gate.

### Control incident correction: NSG acceptance and bounded guest drain

The failed historical C→B control recorded zero bulk requests and twelve
connection timeouts. Its NIC NSG PUT returned `Updating`, but the later allow
gate completed. Subsequent exact subnet inspection established the additional
receiver subnet NSG deny described in the offline v4 correction above.
The old control plan, readiness and generated scripts remain historical evidence.
That offline patch alone did not prove transport; the subsequent separately
leased v4 run now demonstrates exact C→B transport PASS.

After each **single** allow PUT, the runner polls the exact receiver NSG
read-only, at 30-second intervals, for at most 180 seconds and never beyond the
remaining setup margin. It requires the NSG and every custom rule to read
`Succeeded`, exact normalized intended rules (including peer `/32`, TCP443
allow at 100 and original deny at 200), unchanged identity/location/tags, and
the exact receiver NIC/subnet associations. Failed/canceled/unknown
state, read timeout, completed-rule mismatch or insufficient time fails closed:
no server/client dispatch, no PUT resubmission or bulk retry. Private
`nsg-gate.private.json` and, when distinct, `subnet-nsg-gate.private.json`
record readbacks, elapsed time and failure/completion.
Both guest actions require fresh matching gates for that run/snapshot.
These are **configured-policy completion and association checks**, not packet
captures or an attestation of every effective subnet/security-admin/guest policy.

The existing **3,400-second submission requirement** remains 2,500 seconds for
the local guest command plus 900 for restoration. Poll reads and waits consume
the same original **200-second** setup allowance; neither the lease nor reserves
are enlarged. Each read is capped by the remaining margin, and submission checks
the full reserve again after native authorization and local preparation.
An NSG that cannot finish within this margin must block, not run speculatively.

Either client-first or server-first failure now persists a transport **FAIL**
and `failed_draining_peers` plan immediately, and emits a flushed CLI diagnostic
**inside** the executor lifetime. It does not wait for executor shutdown before
making failure visible. The owner still drains both bounded foreground commands;
it does **not** cancel a future or kill the local CLI as a substitute for stopping
the guest. A listener without an authenticated, fully validated declared bulk
request exits with failure within **180 seconds** of binding (plus the short
accept-loop scheduling interval). TLS connects, failed/empty probes and invalid
requests do not renew this deadline; tracked handshake/header sockets are shut
down and joined. Once a valid bulk request is claimed, that startup deadline
no longer applies. A legitimate 5-GiB upload still has its existing 2,400-second
total/60-second socket-idle, 2,450-second guest hard timeout and 2,500-second
local bound; 180 + 2,147.484 seconds is below the total deadline. Bidirectional
and one-way declarations and one-shot payload semantics are unchanged.

Failure visibility is immediate, **not** a promise that an active upload returns
immediately: an active peer may drain to its existing hard deadline. Both
explicitly leased normal deallocations are then independently verified before
the original NSG is restored. No new peer-stop mutation, process-name kill or
detached guest is introduced. A lost CLI acknowledgment or failed deallocation
requires BLOCKED/recovery, never a claim that no remote guest remains.

**New readiness is mandatory:** changes to either `run.py` or `stream.py`
invalidate source-bound readiness. Do not recapture or edit readiness in the
failed run. Under separately authorized owners, prepare a **new run**, capture
fresh readiness binding both new source hashes and exact contexts/VM IDs/disks/
NICs/routes/tools, verify both deallocated, obtain a separate fresh read-only
snapshot, then use a new named execution lease with the unchanged allowances
and setup/restore gates. The later v2 readiness passed, but its live guard
blocked before either guest command; it did not demonstrate C→B transport.
A separately authorized, bounded prebulk connectivity
diagnostic may be proposed if needed; this patch adds no diagnostic traffic phase.

Historical first correction validation: **61 tests PASS (47 existing + 14 focused
regressions)**, including NSG pending/completed state, mismatches/read timeouts,
setup reserve after authorization, either peer's failure visibility before
drain, verified-poweroff gating, and unclaimed/active request deadlines.
The implementation test capture is
`private\transfers\control-cb-20261015-v1\implementation-tests.private.txt`.
That offline run reused existing local TLS fixtures and kept guest reports in
memory rather than changing historical reports or recapturing readiness.
The subsequent bounded restore-readback correction brought the suite to
**67 passing existing WSL tests**. This is offline test evidence only, not a
Windows-suite pass or proof of live transport. Restore requires exact original
policy, all-rule/parent `Succeeded`, and NIC association within the existing
bounded reserve; v2's GET timeout correctly remained unverified until the
separate fresh independent read-only verification above.

The v3 read-budget correction passes **77 WSL tests (67 existing + 10 new)**:
slow exact reads, 90-second/deadline clipping, expired-budget no-dispatch,
post-authorization submission reserve, and original restore-clock/NIC checks.
Validation reused existing localhost TLS fixtures and kept report writes in
memory; historical captures were not rewritten. This remains offline evidence:
it preceded the later v4 review/readiness/live acceptance and 100-test suite.

For an explicitly supervised split workflow, the same wrapper exposes
`start-a`, `start-t`, `allow`, `server`, `client`, `restore-nsg`,
`deallocate-t`, `deallocate-a`, `metrics`, `verify`, all with `--run <run>`.
`server` and `client` must overlap; never wait for server completion before
starting client. The split owner must provide its own **finally** restoration
and close its lease; prefer `live`, which attempts both while its local process
can run. A laptop sleep prevents that local finally path from guaranteeing
timely cloud restoration; it is **not automatic cloud cleanup**.

## Evidence, stop criteria and remaining boundaries

Private files include `*-before.private.json`, `*-metrics-baseline.private.json`,
`server.private.json` / `client.private.json` (raw RunCommand responses),
`server-report.private.json` / `client-report.private.json`,
`verdict.private.json`, `nsg-restored.private.json`,
`deallocate-*-verified.private.json`, metric-after windows and final plan.
Guest directories are `/root/bwb-transfer-<id>` with mode-600 material and a
key-removal trap. Only compact final JSON is stdout (RunCommand's ~4 KiB limit);
truncated/missing reports fail closed. Guest report writes precede upload ACK.

Stop on any mismatched peer/hash/count/status, timeout, wire cap, ownership or
budget gate, STOP, stale lease, unavailable tools or unsuccessful restore.
No retry, replacement endpoint, implicit package installation or spending
increase. If restoration cannot be verified inside the reserve, return BLOCKED
and assign a fresh recovery owner; never claim that cancelling a local CLI
necessarily cancels an Azure operation. Guest and native process deadlines are
independent safeguards; verified deallocation is the final kill boundary.

**Transport PASS is not a billing exemption verdict.** This same-region
customer-SaaS case has no same-offer mature inter-region positive control today;
billing remains **INCONCLUSIVE** pending the planned mature quantity/rate
evidence. Azure metrics corroborate traffic only.

Local tests cover mTLS rejection, wrong SAN, exact concurrent hashes, strict
length/chunking bounds, truncation/corruption, idle timeout, two-slot rejection,
one-shot lifecycle, pacing, NIC shape/no double sum, report mismatch/truncation,
lease budget/restore gates and finally restoration. Test payloads are small
localhost-only (32 KiB per successful direction); certificates stay lab-private.
**Original validation: 20 tests PASS**, with the original complete output at
`private\transfers\local-tests\test-results.private.txt`.
The incident correction adds focused read-only-lease, exact 200-second margin,
six-submission readiness/restore, evidence binding/expiry and guest revalidation
tests. **Review validation: 28 tests PASS (20 existing + 8 new)**; complete output:
`private\transfers\local-tests\incident-review-tests.private.txt`.
At that offline review, Azure RunCommand timing, actual guest tool/NIC
availability and ARM restoration remained **live acceptance gates**, not
claims established offline. No Azure calls were made for that review.

### Readiness-v2 snapshot incident (offline correction)

The first baseline query failed with Azure Monitor `BadRequest`: its roughly
26-second window was shorter than the required minute. Neither baseline nor a
snapshot timestamp was produced. Both VM binding mismatches were **only**
resource-group casing changes in `storageProfile.osDisk.managedDisk.id` and
the CLI-derived `managedDisk.resourceGroup`, not missing fields or replaced
VMs/disks. Bindings now canonicalize these case-insensitive ARM identifiers
(also VM ARM ID/VM GUID); the full remaining storage profile is retained.
Nonempty VM/managed OS-disk identifiers are required, and actual VM/disk
replacement or other storage changes still fail closed.

Changing `run.py` invalidates the existing readiness source-hash binding.
**Do not rewrite attestations or restart readiness-v2 in place.** Prepare a new
run with the actual remaining allowance, then obtain separate fresh readiness,
read-only snapshot and live leases in that order. Reconfirm deallocation,
original NSGs, native contexts, no other producer, allocated hours/day/TTL and
the unchanged $8/$4 budgets before any execution. The 200-second live setup
margin and all transport/wire/concurrency/restoration limits are unchanged.

Follow-up validation: **34 tests PASS (28 existing + 6 focused regressions)**.
The complete output and exact incident findings are in
`private\transfers\morpheus-readiness-v2-incident.private\report.private.json`.
Test certificates/reports were generated only within that new private incident
report directory and removed afterward; existing run evidence was not rewritten.

## Completed readiness-v3 run and sleep-recovery boundary

The independent Niobe handoff was persisted **2026-10-15T14:17:09Z** and is the
publication authority. The original blocked local invocation state remains
historical; recovered persisted guest reports establish the later transport PASS.

- **10:04:25.588424–10:40:28.237747Z:** includes three connection-refused,
  zero-payload readiness probes, then successful mTLS readiness. Bulk requests
  began at about **10:04:40.603Z**, not at the first probe.
- A produced **5,368,709,120 bytes** for upload; T produced the same for download.
  All four endpoint/direction records match the expected SHA256 and HTTP 200,
  with **zero bulk retries**. Both requests were initiated by A; TCP initiator
  is not the download's byte producer.
- Count **A RX+TX once: 10,818,818,041 bytes**, including 81,399,801 bytes
  above combined payload for protocol/background traffic. This is not an A+T
  sum and not billed outbound bytes.
- The laptop slept. Guests completed their bounded foreground tasks and saved
  compact reports, but the laptop-side invocation timed out and could not run
  restoration during sleep. **No restart or payload replay was needed.**
- Morpheus recovered reports during **14:02–14:08Z**; restored every original
  T security-rule field, excluding only Azure's service-managed ETag from
  equality; verified T **deallocated 14:07:37Z**, A **14:07:40Z**. Rule changes
  themselves are never ignored. Recovery captures had no owned guest processes.
- Niobe independently rechecked exact baseline and deallocation after 14:09Z
  (fresh A/T power/NSG evidence **14:13:21/14:13:26Z**). Native owned children
  were idle at validation closure; verified deallocation is the final kill boundary.
- Mutation submissions: original live owner **5**, recovery **5** (including
  report-capture RunCommands); readiness **two phases ×6**, plus historical
  deployment baselines **6 core +4 T**. These are operation counts, not HTTP
  requests or additional transfer retries. Validation/publication added no mutations.

Guest deadlines and persisted output provide bounded execution/recoverability;
they do not schedule independent cloud deallocation. Future approved live work
requires an awake supervised owner or a separately designed/approved cloud-side
cleanup mechanism, not reliance on a sleeping laptop's `finally`.

### Tested runner operational corrections (not Cost API findings)

The documented **34 passing tests** include the Monitor-window and binding
regressions above. Monitor metric queries need a **minimum 60-second interval**;
the runner uses a bounded lookback without claiming an earlier guest baseline
or changing snapshot freshness. ARM disk IDs are **case-insensitive**: resource
group casing alone was a false mismatch, corrected by canonical comparison.
Actual replacement/missing identifiers and other storage changes still fail
closed. Recovery added expected disk-size/SKU fields, while all original storage
bindings matched. These corrections do not establish Cost API schema/support.

Keep $8 core/$4 extension caps, <12h/slot and the original resource TTLs.
Conservatively ~4h10m/slot includes readiness/recovery; exact allocation start
is not asserted. Retained disks/PIPs incurred rent until known-owned cleanup.
The 24/48/72h/day-7 billing follow-up targets and historical failed/blocked control
are in the [result](../results/2026-10-15-cross-tenant-public-ip.md).
The **18:22Z historical** refresh had both aggregate
queries **429 ERROR**, Windows details **200 INCOMPLETE** (1,000 unrelated
rows discarded, continuation remaining), WSL details **200 COMPLETE empty**.
Neither is zero-charge proof. v4 later succeeded as expected-charged transport;
the **23:28Z** three-request billing snapshot still has only A's tiny positive
rows totaling **USD 0.0000728753264993429373**, without quantity/unit/rate or
request attribution; C Query no rows/details timeout, T empty. A billed positive
control and invoice-level proof remain pending, not transport.
The practical published same-region pricing answer does not require more payload.

Collect no earlier than **16/17 October 10:40:28Z** under fresh read-only
leases. Known-owned cleanup completed **16 October 00:00:11.806224Z**, before
the original **18 October 07:33Z** deadline; preserve private historical IDs. The
**18 October 10:40:28Z** 72h collection is after deletion; day 7 is
**22 October 10:40:28Z**. **No automatic follow-up/cleanup job is established**.
Control 24/48/72h targets are **16/17/18 October 23:15:33Z**, using actual
15 October usage and historical IDs after cleanup, not additional transfers.
No extra-cost scope, further MSDN payload, or queued transfer is authorized.
