# D0 infrastructure

## Current fresh A/C/T lifecycle (offline-prepared; not deployed)

`fresh.py` is the **new three-VM deployment/owned-cleanup entry point**. Its
offline `prepare` action adapts `msdn-main.json` into reviewable, pinned bytes;
deployment consumes those approved bytes, not a newly generated template.
It never calls the old deployment scripts,
imports the transfer runner, reads old groups, switches accounts, installs
software, or creates authentication state. The existing template is unchanged.
This source preparation makes **no Azure calls** and is not live approval.

The private preflight handoff supplies exactly three new slots: core A in
Sweden Central, core C in North Europe, and native-WSL MSDN T in Sweden Central.
Its exact context/inventory paths and identifiers are inputs, not public
constants. Only `Standard_B2ts_v2`, nonzonal, regular Ubuntu 22.04 Gen2, 30 GB
StandardSSD_LRS and Standard regional static IPv4 PIPs are accepted.

**Seven actual roots per slot, plus its new RG:** VM, implicit tagged OS disk,
PIP, NIC, unpeered VNet with inline subnet, NIC NSG, and **separate subnet NSG**.
Both NSGs are explicitly owned. The NIC NSG has **one priority-100 inbound
deny-all rule** (all protocols, ports and source/destination addresses); the
separate subnet NSG has **zero custom rules**. NIC NSG names end in `-nsg-a/c/t`;
subnet NSG names use `<runId>-subnet-policy-a/c/t`, never that same suffix.
Two NSGs avoid
unknown policy-injected subnet bindings and duplicate-ID snapshot/restore
races. There is no SSH/public management rule, peering, NAT, LB, CDN, BYOIP,
bootstrap, listener, guest job, traffic, or paid diagnostics. The ARM document
has seven resource declarations: six explicitly created roots plus the disk
tagging extension; the seventh inventory root is the VM-created disk.

### Future-owner invocation

From repository root, using existing Python and already authenticated CLIs:

```powershell
python -B -m unittest discover -s labs\azure-bandwidth-billing\deploy -p test_fresh.py -v

# Private paths assigned by the coordinator; never copy old live contexts.
$sourceHandoff = '<absolute private original read-only fresh-preflight handoff JSON>'
$aligned = '<absolute NEW private planned-input namespace>'
$h = "$aligned\handoff.private.json"
$g = '<absolute private refreshed deployment gate JSON>'
$prep = '<absolute NEW private prepared-input evidence directory>'
$out = '<absolute NEW private deployment evidence directory>'
$l = '<absolute deploy\.runtime-control\fresh deployment lease JSON>'

# OFFLINE ONLY: copy the planned handoff and three contexts, explicitly normalizing
# old vm-<runId>-a/c/t plans to <runId>-vm-a/c/t; never mutate original provenance.
python -B .\labs\azure-bandwidth-billing\deploy\fresh.py align-handoff --handoff $sourceHandoff --output $aligned
# Use this copied handoff for ALL subsequent actions. New inventory paths are
# inside $aligned. It contains original handoff/context byte hashes, canonical
# names, and slotsHash. Copy slotsHash into the NEW gate/lease handoffHash fields.
(Get-Content -Raw -LiteralPath $h | ConvertFrom-Json).slotsHash

# OFFLINE ONLY: gate reviewPassed/deploymentApproved must both still be false.
python -B .\labs\azure-bandwidth-billing\deploy\fresh.py prepare --handoff $h --gate $g --output $prep
# Independently review source, captured template/parameters, contexts, handoff and quotes.
# Then update the gate with preparedInputsPath, approvedInputsHash, fresh approvedAtUtc,
# and explicit reviewPassed=true/deploymentApproved=true. Do not regenerate this capture.
# SHA256 is over the exact approval.private.json bytes, not parsed/canonical JSON:
(Get-FileHash -Algorithm SHA256 -LiteralPath "$prep\approval.private.json").Hash.ToLowerInvariant()

# LIVE: only a later reviewed owner with a newly approved deployment lease may run this.
python -B .\labs\azure-bandwidth-billing\deploy\fresh.py deploy --handoff $h --gate $g --output $out --lease $l

# Each subsequent action requires a NEW matching lease, not the completed deploy lease.
python -B .\labs\azure-bandwidth-billing\deploy\fresh.py inventory --handoff $h --lease '<inventory lease>'
python -B .\labs\azure-bandwidth-billing\deploy\fresh.py preview-cleanup --handoff $h --lease '<preview lease>'
python -B .\labs\azure-bandwidth-billing\deploy\fresh.py cleanup --handoff $h --lease '<cleanup lease>'

# Only on a separate fresh recovery lease explicitly authorizing these three deallocations:
python -B .\labs\azure-bandwidth-billing\deploy\fresh.py restore --handoff $h --lease '<recovery lease>'
```

Native core calls use the **existing CLI's bundled Python**, avoiding Windows
`az.cmd` argument quoting. T uses the handoff's exact
`wsl.exe -d Ubuntu-24.04 --exec /usr/bin/az` backend, wrapped in Linux
`/usr/bin/timeout --kill-after=5s`; the outer process has a separate finite
timeout. Windows paths for ARM files become WSL mount paths. ARM parameters
are **always `--parameters @private-file.json`**, including the existing
`.pub` SSH key. No private key is read/generated.
Both backends explicitly request an ARM token with
`account get-access-token --resource https://management.azure.com/ --subscription <pinned subscription>`.
Enabled account identity, exact token tenant/subscription, nonempty JWT, ARM
audience and actual expiration are checked initially and again before **every**
mutation. Token material is never written to evidence, arguments or stdout;
no login or account switching occurs. These extra CLI calls consume the same
lease's call budget and finite command deadlines.

### Required private live inputs

The handoff must contain `slots` in A/C/T order and the existing
`nativeCoreCli`/`msdnCliArgvPrefix` entries. Each slot supplies `slot`, `region`,
`sku`, `runId`, `resourceGroup`, `vmName`, `subscriptionId`, `tenantId`,
`contextPath`, and its **new** `inventoryPath`. Context files must exactly
match subscription, expected tenant, group and run. Unknown/existing resources
are never adopted. All generated artifacts stay in this lab's ignored
`private` directory; stdout contains no resource identifiers or CLI output.

The VM name must be explicitly `<runId>-vm-<lowercase alias>` in the handoff;
preparation rejects legacy or mismatched names rather than silently renaming
them. `align-handoff` is optional for already canonical plans, requires no
gate/lease, refuses existing output and any source slot with an inventory or
ownership receipt, and creates only a copied handoff plus three copied contexts.
It does not prepare ARM inputs, approve a gate, prove inventory, or authorize
deployment. Preserve the original preflight handoff/contexts read-only and
review the copied names and recorded source hashes. Use a **new unapproved**
gate and a new prepared-input directory after alignment; do not alter or reuse
an already reviewed capture or approved artifact. Gate and lease hashes must
pin the new explicit slots, not the original planned-name handoff.

RG ownership tags are **exactly five**: `lab`, `created_by`, `run_id`,
`createdUtc`, `cleanupDeadlineUtc`. Every root (including the implicit OS disk)
has **exactly three**: `lab=true`, `created_by=copilot-lab`, `run_id=<runId>`.
Expiry and successful creation proof remain bound to the five-tag RG receipt.
Live inventory is saved with its actual tags, never a filtered projection;
extra or missing tags on either RG or roots block readiness and cleanup.

The future owner creates the deployment gate **after review and refreshed
price/FX verification**, never by treating this README as approval:

```json
{
  "reviewPassed": false,
  "deploymentApproved": false,
  "approvedAtUtc": "<fresh UTC timestamp>",
  "preparedInputsPath": "<absolute private prepared-input directory\\approval.private.json>",
  "approvedInputsHash": "<operator-reviewed SHA256 of exact approval.private.json bytes>",
  "pricesVerifiedAtUtc": "<fresh UTC timestamp>",
  "fxVerifiedAtUtc": "<fresh UTC timestamp>",
  "handoffHash": "<fresh.digest(handoff['slots'])>",
  "combinedCapUSD": 45,
  "coreCapUSD": 23,
  "msdnCapUSDEquivalent": 22,
  "msdnCapEUR": 19.62,
  "usdPerEur": 1.1208,
  "coreBillingCurrency": "USD",
  "msdnBillingCurrency": "EUR",
  "wireGBPerContextMaximum": 220,
  "payloadGBPerDirection": 100,
  "allocatedHoursPerSlotMaximum": 12,
  "resourceTTLHoursMaximum": 48,
  "cleanupDeadlineUtc": "2026-10-18T07:33:00Z",
  "sshPublicKeyPath": "<existing public .pub file>",
  "prices": {
    "A": {
      "currency": "USD", "region": "swedencentral", "sku": "Standard_B2ts_v2",
      "computePerHour": 0.0108, "diskPerMonth": 2.4,
      "diskOperationsPer10000": 0.002, "pipPerHour": 0.005,
      "internetWorstPerGB": 0.087
    },
    "C": {
      "currency": "USD", "region": "northeurope", "sku": "Standard_B2ts_v2",
      "computePerHour": 0.0114, "diskPerMonth": 2.4,
      "diskOperationsPer10000": 0.002, "pipPerHour": 0.005,
      "internetWorstPerGB": 0.087
    },
    "T": {
      "currency": "EUR", "region": "swedencentral", "sku": "Standard_B2ts_v2",
      "computePerHour": 0.0095, "diskPerMonth": 2.1119,
      "diskOperationsPer10000": 0.0018, "pipPerHour": 0.0044,
      "internetWorstPerGB": 0.0766
    }
  },
  "evidenceHashes": {
    "<absolute private evidence JSON path>": "<SHA256 of exact file bytes>"
  }
}
```

Prices above are explanatory, **not refreshed quotes**. `evidenceHashes` must
include all ten uniquely named artifacts: `compute-USD.json`,
`compute-EUR.json`, `disk-USD.json`, `disk-EUR.json`, `pip-USD.json`,
`pip-EUR.json`, `bandwidth-USD.json`, `bandwidth-EUR.json`, `fx-source.json`,
and `disk-cap-source.json`, using the original preflight JSON shapes.
All underlying retrieval timestamps and approvals must be on the current UTC
day and <=1 hour old. Retail pagination must be complete. Price selection
checks exact currency/region, Linux PAYG B2ts_v2 (not Spot/Windows), E4 LRS
disk and operations, regional Standard static PIP, and Zone-1 Microsoft-network
internet egress. The ECB reference quote must match the gate FX; a changed
FX can only **lower**, never raise, the EUR cap corresponding to USD 22.

`prepare` needs no lease and performs no Azure/authentication operations. It
accepts only an unapproved gate and an entirely new private output directory.
Its `approval.private.json` records exact hashes of `fresh.py`,
`msdn-main.json`, the complete preflight handoff/backend configuration, all
three original context files, the existing public key, quote evidence, the
adapted template and all three parameter files. Parameters already contain
the pinned A/C/T aliases, regions, run/VM identities, creation timestamp and
unextended deadline. Review both these files and the captured quote/limit
binding before explicitly approving the capture hash in the gate. Preparing
does **not** set approval flags or grant permission to deploy. An edit requires
a new capture and independent approval, never silent regeneration.

Deployment requires that exact approved capture, preparation preceding approval,
and freshness <=1 hour. It rejects drift before any mutation and rechecks all
approved file hashes, full gate bytes/values, backend/context bindings, and
immutable lease approval fields immediately before **each** later mutation,
including after ARM validation and before deployment. Lease counters/checkpoint
timestamps, the bounded restore-start timestamp, and safe diagnostic progress
(`currentCommand`, `lastCommandKind`, `lastRole`) are the only excluded
progress fields. `namedCommandTimeoutSeconds` is an immutable approval field,
not progress: changing it after binding blocks mutations. Each ARM submission receives newly exclusive private snapshot
files copied from the already checked in-memory approved bytes; mutable
preflight/generated input paths are not passed to the CLI. No changed source,
template, parameter, handoff, context or quote is automatically blessed.

The guard recomputes infrastructure using 12 allocated hours/VM, 48 disk/PIP
hours, a conservative 672-hour month, and 61,000 E4 operations/hour for all
48 hours. It reserves 220 decimal GB egress **per context**, with no free-tier
assumption; the T reserve uses the higher of retail EUR or USD converted at
the verified FX. Full envelope must fit USD 45, core USD 23, MSDN USD 22
equivalent/EUR <=19.62, and USD 2.50 infrastructure per context.
These are planning bounds, **not Azure-enforced spend stops**. No traffic is
authorized here; a future traffic owner still needs the measured pilot,
remaining allocated-time accounting, and its own day-boundary cost approval.

### Lease, deployment ordering and failure contract

VM ARM GET `storageProfile.osDisk.managedDisk` can contain only `id`:
`osDisk.diskSizeGB` and `managedDisk.storageAccountType` are not guaranteed
in that reference. Binding verification first requires the exact expected
owned OS disk reference and no data disks, then GETs only that expected
disk using the disk-specific `2024-03-02` API. The authoritative disk must
have the exact owned identity/name/type/tags/region, reciprocal `managedBy`
VM binding, integer 30 GiB size and `StandardSSD_LRS` SKU. Missing or malformed
disk fields block readiness; present VM size/SKU fields must agree. No
template defaults fill missing observations. The binding ID projection and
seven-root inventory contract are unchanged, including transfer/repeat
compatibility. This adds **one read per slot** (six binding GETs instead of
five, three additional reads for A/C/T), within the unchanged lease/call
limits. Offline regression fixtures preserve the actual A/C/T omissions
with synthetic identities and no private response values.

The coordinator supplies an active **Tank** lease directly under
`deploy\.runtime-control`, with: `taskId`, `action` (exact CLI action),
`ownerRole`, `objective`, `state`, `startedAtUtc`, `expiresAtUtc`,
`maxToolCalls`, `actualToolCalls`, `maxMutations`, `actualMutations`,
`commandTimeoutSeconds`, `restoreTimeoutMinutes`, `allowedMutations`,
`handoffHash`, and `ownedProcessesIdle`. Duration <=60 minutes, calls <=150,
command <=1200 seconds (ordinary CLI children remain capped at 120 seconds),
restore <=15 minutes. Deployment requires a fresh zero-counter lease with
**exactly twelve** authorized mutations:
`create-group-a/c/t`, `validate-a/c/t`, `deploy-a/c/t`, `deallocate-a/c/t`
(expand each slash shorthand to three complete strings).
Inventory/preview use zero mutations; recovery restore <=3; cleanup <=6.

For a newly reviewed **bounded-catalog-timeout-recovery** phase, the lease may
explicitly approve the three read-only diagnostics:

```json
"namedCommandTimeoutSeconds": {
  "catalog-a": 600,
  "catalog-c": 600,
  "catalog-t": 600
}
```

Each name applies only to the internally constructed exact command
`vm list-skus --location <approved-slot-region> --resource-type virtualMachines --size Standard_B2ts_v2 --all`
for its own A/C/T slot. These names are **not mutation authority** and never
belong in `allowedMutations`. Unknown names, non-integers (including booleans
and fractions), nonpositive values, and values above 600 are rejected before
launch. The actual command bound is the minimum of its named allowance
(120 seconds if absent), `commandTimeoutSeconds`, and the actual remaining
lease deadline. Other reads and deployment commands remain capped at 120.
No SKU fallback, stale catalog substitution, or whole-command retry is added.
Slow catalog pagination is plausible, not a proven underlying timeout cause.

Every CLI child uses a fixed monotonic deadline and <=2-second `communicate`
polls, draining stdout/stderr without duplicating cumulative timeout output.
Lease/STOP is checked each poll; cancellation, expiry, or command timeout
blocks and terminates the exact child tree. Each invocation is charged once,
not once per poll. WSL retains its bounded `timeout` wrapper at the command
bound minus ten seconds, with `--kill-after=5s`. Diagnostic progress records
only the safe command name/kind, owner role and checkpoint timestamp, never
arguments, identifiers, tokens, service URLs or raw errors.

After all three fresh catalogs and absence checks, before the first ownership
intent and again immediately before the first RG creation submission, at
least **25 minutes** must remain within the explicit <=60-minute phase cap.
The named planning estimates are five minutes for creation/validation/
deployment submission, fifteen for VM polling, and five for restore.
These estimates do not enlarge any hard limit: each VM poll and the shared
restore window retain their existing <=15-minute bounds, and the 80% new-work
boundary still applies. Three 600-second catalogs alone leave 30 minutes;
other checks consuming more than 35 minutes total block before any RG write.
Overall <=150 calls, <=12 mutations, resource/cost caps and cleanup deadlines
are unchanged. This is a new reviewed phase, not an unchanged retry.
Existing captures/pins must not be edited: the future live owner must run a
new offline `prepare`, review the regenerated source/capture hashes and obtain
new approval before execution.

Every command checks active lease/expiry/STOP and reserves a call before
submission. Every mutation reserves its exact operation before submission.
At 80% elapsed/calls/mutations no new work starts; only explicitly authorized
deallocation/closure can use the remaining hard budget, never expiry or STOP.
Deployment submits **all three creates before the three deallocations**:
three RG creations + three validations + three deployments = nine new-work
mutations; the final three are reserved restore exceptions. The shared restore
window starts immediately before deallocation. No hidden retry or allocation
operation exists. Each managed-resource polling loop is bounded to 15 minutes,
>=30-second intervals and a ten-minute unchanged-progress cutoff.

1. Verify each CLI backend's enabled subscription/tenant and fresh ARM token
   identity (no `account set`), and enforce the operator-approved input capture.
   Refresh all three catalog gates, reject fallback, and prove all new RGs
   absent with exact `ResourceGroupNotFound` responses.
2. Recheck each absence, persist ownership **intent before creation**, then
   create/tag and GET-verify its RG. Unknown/failed creation is not success
   and does not authorize deletion. Tags include `lab`, `created_by`,
   `run_id`, `createdUtc`, and the unextended cleanup deadline.
3. Validate all three single-VM ARM templates against their new empty RGs.
   Only then write the final locked deployment manifest. Template validation
   is **not proof of actual allocation**; no successful capacity claim is
   made until all deployments succeed.
4. Submit each deployment once with `--no-wait`; poll the exact deployment
   ID. Deallocate all three owned VMs and verify instance-view power states.
   Export inventories only after checking exact root set/tags, independent
   NSG/subnet/NIC/PIP/disk/VM bindings, nonzonal SKU, the NIC's exact deny-all
   baseline, and the separate subnet NSG's empty custom-rule baseline.
5. Write `resources[]` actual root `id/name/type/location/tags`, `runId`,
   `groupId`, `capturedAtUtc`, ownership hash, and binding IDs to the exact
   handoff inventory paths. Output additional deployed contexts (including
   expected tenant, platform/backend, region, VM and resource IDs) and actual
   IPv4 peer addresses in the new private output directory. The original
   preflight contexts remain unchanged. No transfer approval is synthesized.

On any failure, STOP, expiry, timeout or unknown extra resource: **BLOCKED**,
freeze new mutations and preserve existing inventories, contexts and receipts
byte-for-byte. Bounded partial-resource failure snapshots, when the lease still
permits reads, go only to new `*-blocked-<correlation>.private.json` artifacts
inside this invocation's newly created output directory, and only for groups
whose creation this invocation GET-verified. An intent or unknown PUT outcome
is not a creation/deletion claim. A rejected redeployment never reads old
ownership state to overwrite old inventories. Successful inventory publication
is exclusive/atomic, never a replacement of an existing ready snapshot; a later
read-only `inventory` action writes a separate `*-capture-<correlation>.json`
if its original inventory path already exists. Readiness failures never downgrade
previously verified evidence. No inline
cleanup/retry, detached child or guest job follows. A different recovery owner
gets a fresh lease; an incomplete/unverified RG creation is not cleanup
authority. Deadline is the earliest of creation +48h, the gate deadline and
**2026-10-18 07:33Z**; it is never extended.

### Cleanup ownership contract

Preview is a separate read-only action that persists a hash of exact current
root IDs and ownership tags. Cleanup requires a fresh lease with
`cleanupApproval` equal to
`delete only the fresh task-created exact inventoried groups`,
`allowedMutations` containing only the three `delete-group-a/c/t` strings,
and `previewHashes` mapping A/C/T to the separately reviewed hashes.
The <=30-minute preview must still match live inventory, successful creation
proof, absence proof, slot hash and ownership hash. It is checked again
immediately before each delete. Any extra root, untagged child/extension,
unknown NSG, foreign tag or changed context **blocks whole-RG deletion**.
Owned VM/NIC/VNet/NSG attachment IDs are checked without following external
references; foreign subnet NSGs, disks, peerings, NAT/LB/route attachments or
external associations also block cleanup. Custom rules on the owned NSGs do
not themselves prevent later cleanup.
Nothing unowned is deleted, and no old RG is queried.
Only exact task-created roots may be handed to a separately scoped recovery
owner for individual cleanup; this helper intentionally does not delete a
partially unknown group. Group deletion is submitted once asynchronously and
polled to an exact 404; only recorded verified deletion is idempotent.

## Historical deployment descriptions

The deployment descriptions below are historical. For the current retained
A/B/C/T inventory, failed/blocked control attempts and cleanup **before
2026-10-18 07:33Z**, see the [lab overview](../README.md).

## Windows ownership checks and offline regression tests

`Common.ps1` resolves the first native Azure CLI application, not a shadowing
PowerShell function. Inventory ownership still requires all three lab tags.
Known service-managed VM children (`MDE.Linux` and `RunCommandLinux`) may be
untagged only when their exact parent ID resolves to one uniquely verified
owned VM. They are not retagged, independently managed or counted as lab roots.
Foreign tags, unknown untagged extensions, missing or duplicate owned parents
and malformed child IDs fail closed.

From repository root, these checks use no Azure CLI, authentication or network:

```powershell
.\labs\azure-bandwidth-billing\deploy\test_Common.ps1
.\labs\azure-bandwidth-billing\deploy\Test-Local.ps1
```

## Additional isolated MSDN endpoint T (native WSL)

`msdn.py` + `msdn-main.json` are the separate one-VM deploy/cleanup pair;
they do not modify the Windows A/B/P template or profile. Actual T is
Standard_B1s in Sweden Central, allocated successfully and verified deallocated
2026-10-15 08:22:55Z. Its $0.0108/hour retail rate equals the approved B2ts_v2
ceiling; B1ls is excluded below 1 GiB. Six resources plus a new tagged RG;
all inbound denied, no downloads/harness/extensions.

From the repository root, with an already authenticated Ubuntu-24.04 native
Linux CLI and ignored `private\wsl-cost-context.private.json` containing explicit
`subscriptionId`/`expectedTenantId`:

```powershell
python -B -m unittest discover -s labs\azure-bandwidth-billing\deploy -p test_msdn.py
$checkout = (Get-Location).Path
$mount = '/mnt/' + $checkout.Substring(0, 1).ToLowerInvariant() + $checkout.Substring(2).Replace('\', '/')
$script = "$mount/labs/azure-bandwidth-billing/deploy/msdn.py"
wsl.exe -d Ubuntu-24.04 --exec timeout --kill-after=5s 180s /usr/bin/python3 -B $script preflight
wsl.exe -d Ubuntu-24.04 --exec timeout --kill-after=5s 600s /usr/bin/python3 -B $script deploy --confirm DEPLOY-ONE-MSDN-ENDPOINT
wsl.exe -d Ubuntu-24.04 --exec timeout --kill-after=5s 120s /usr/bin/python3 -B $script preview-cleanup
# Only after separate deletion approval and a NEW cleanup-authorized lease:
wsl.exe -d Ubuntu-24.04 --exec timeout --kill-after=5s 600s /usr/bin/python3 -B $script cleanup --confirm <private-run-id>
```

Adjust only the intrinsic WSL mount path for another checkout. Every live action,
including preview, requires an active `deploy\.runtime-control\msdn-lease.json`
and absent STOP. Deploy consumes four reserved mutation commands, refuses existing
inventory/groups, automatically deallocates even after deployment failure, and
closes its lease completed/blocked. Therefore preview after deployment needs a
fresh read-only lease (the initial live preview preceded lease closure).
Never remove inventory to force a redeployment. `restore` deallocates only the
exact inventoried VM, under an active restore-authorized lease.

Reuse requires fresh cost approval/price verification, a <=30-minute lease with
bounded calls/timeouts, and explicit `allowedMutations` strings matching the
operations in `msdn.py`. Cleanup additionally requires the exact string
`delete the exact inventoried MSDN lab resource group`; the deployment lease
does **not** authorize deletion. Preview compares exact identities, names and
tags against creation inventory; unrecorded/foreign resources block deletion.
Cleanup is idempotent only after a recorded verified deletion. Source/template
contain no keys: an existing native Linux public key, or the existing Windows
`~\.ssh\id_rsa.pub`, is read into an ignored ARM secure-parameter JSON file.
Tokens remain in native WSL memory. No login/account-set/register/config writes.

**$4 additional envelope, max 12 allocated hours and 72 hours disk/PIP lifetime.**
Disk and static PIP still accrue charges after deallocation. Current cleanup
deadline **2026-10-18 08:20:59Z**; no deletion or traffic was authorized/executed.
Full actual facts: [MSDN deployment log](../msdn-deployment-log.md).

## Windows A/B/P infrastructure

`main.json` is native ARM: three non-Spot Ubuntu 22.04 Gen2 VMs (A/B/P),
30 GiB Standard SSD OS disks, two static Standard IPv4 PIPs, three NIC/NSGs,
and two unpeered Sweden Central VNets. A/P share a VNet; P has no public IP or
implicit outbound. Azure's management agent is the intended control channel;
private P run-command reachability is not yet verified. No apt/pip/download
bootstrap, certificates, listener or transfer runner is installed.

**All inbound, including intra-VNet traffic, is explicitly denied.** Opening
private/public 443 is a separate approved harness deployment: require pinned
mTLS, exact peer allowlists, one-use IDs, 5 GiB handlers, 20 Mbit/s, 45-minute
deadlines, streaming hashes and the aggregate 35 GiB wire cap before opening.
Do not mistake infrastructure provisioning for a transport/billing result.
No public SSH rule, operator IP discovery, NAT/LB/peering, C/NE or paid logs.
The tagging extension applies mandatory tags to implicitly created OS disks.

## Reproduction (PowerShell 7, existing installed Azure CLI only)

1. Obtain a fresh active lease and owner approval. Resolve subscription and
   expected tenant privately from the authorized profile/owner; never switch
   CLI context. Privately create `private\context.private.json` with
   `subscriptionId`, `expectedTenantId`, `runId` (`bwb-` plus 12 lowercase
   hexadecimal characters), and matching `resourceGroup` (`rg-` plus runId).
   Never copy tokens or create authentication state for this task.
2. `.\deploy\Test-Local.ps1` — offline only.
3. `.\deploy\Preflight.ps1 -ContextPath .\private\context.private.json -SshPublicKeyPath <existing-public-key>`
   — explicit-subscription identity check, read-only provider state and bounded
   directly authenticated HTTPS catalogue (120 seconds total, <=10 pages).
   No billing requests. Location restrictions block; zone restrictions do not
   prevent a nonzonal request. Walk B1ls/B1s/B2ts_v2/B2ls_v2/B2s_v2 in order;
   exclude B1ls's 0.5 GiB for TLS/agent memory. Current approved price evidence
   covers SC B2ts_v2; another selected size blocks pending a fresh price gate.
4. `.\deploy\Deploy.ps1 -ContextPath .\private\context.private.json` —
   refuses existing RG, requires fresh gate and six reserved mutation slots.
   Creates one RG, performs native ARM `deployment group validate` using a
   parameters JSON file (no VM creation), deploys one template, then deallocates
   each of three VMs and records private inventory/power evidence. Validation
   **does not guarantee capacity**; only successful actual allocation does.
   All errors surface; partial-deployment inventory is retained. Never rerun
   blindly; existing groups are intentionally rejected.
5. Cleanup defaults to preview:
   `.\deploy\Cleanup.ps1 -ContextPath .\private\context.private.json`.
   After separate explicit owner deletion approval and a fresh cleanup lease:
   add `-Confirmed -ConfirmRunId <private-run-id>`. Exact group/run tags and
   created inventory must match; foreign/unrecorded resources freeze deletion.
   Inventory/power/cleanup timestamps and all resource identifiers stay private.

The $0.08/hour / $8 envelope is planning, not an Azure spend hard stop.
Deallocated disks/PIPs remain billable: enforce <=72 hours lifetime and
<=12 allocated hours/slot across the core. No overnight allocation or
unapproved deletion/scheduler. Failure/expiry/STOP requires coordinator handoff;
do not authorize yourself another operation. `Common.ps1` enforces bounded
specific-process execution, explicit subscription, tenant and lease checks.
Deployment restore actions may cross the 80% **new-work** cutoff but never
the mutation maximum or expiry. Every lease here is a 30-minute lease.
