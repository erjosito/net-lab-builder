# Locked experiment: overlapping, non-peered spoke address spaces

**Owner:** Morpheus. **Requested by:** Jose Moreno. **Locked:** 2026-10-16.
**Status:** architecture gate corrected; direct ARM acceptance experiment approved.
Prior execution stopped before any Azure mutation. Niobe's read-only verification
proved the exact RG absent and prior processes idle; live acceptance is pending.
**Question:** Will Azure accept two simultaneous bidirectional subnet peerings
from one hub when both spokes contain `192.168.0.0/16`, but only their distinct
10.x subnets participate?

## Designs studied / authoritative basis

**D1 — scoped peerings, documented-compatible candidate; live verdict pending.**
Microsoft Learn's [subnet-peering guide](https://learn.microsoft.com/en-us/azure/virtual-network/how-to-configure-subnet-peering#subnet-peering-checks-and-limitations),
retrieved through Microsoft Learn MCP on 2026-10-16, states:
“The participating subnets must be unique and must belong to unique address
spaces across all peering links.” Its example explicitly permits peering unique
subnets in unique parent address spaces even when other VNet address spaces
overlap. Thus the repeated **non-participating** 192.168/16 does not violate
the published checks. This is not permission to overlap participating 10.x
subnets or their parent address spaces, nor a claim of a live PASS.

The [REST create/update reference](https://learn.microsoft.com/en-us/rest/api/virtualnetwork/virtual-network-peerings/create-or-update?view=rest-virtualnetwork-2026-01-01)
was also fetched through Learn MCP. The requested older view redirected to
**2026-01-01**; this plan pins that actually retrieved version, not the
redirected-away 2025-01-01. Request fields are
`properties.peerCompleteVnets`, `localSubnetNames`, `remoteSubnetNames`,
`enableOnlyIPv6Peering`, `remoteVirtualNetwork.id`,
`allowVirtualNetworkAccess`, `allowForwardedTraffic`, `allowGatewayTransit`,
and `useRemoteGateways`. Subnet lists are **names, not CIDRs or resource IDs**.

**D2 — whole-VNet peering / forwarding / isolation tests: out of scope.**
No negative-control mutation, spoke-to-spoke peering, transit, packet probe,
effective-route test, or assertion that excluded subnets are isolated.
Acceptance alone does not demonstrate any of those properties.

## Address plan and resources

Use `swedencentral` from the skill config. Resolve the configured
`azure_subscription_id` locally at execution and verify it matches
`az account show`; never silently switch subscription. Do not publish its ID.
Task ID: read the fresh `taskId` in `deploy\.runtime-control\lease.json`.
The corrected acceptance run has a new correlation ID; the RG name remains locked.
RG: `rg-subnet-overlap-20261016-fde5ecf8`.

| VNet | Exact address spaces | Participating subnet | Excluded subnet |
|---|---|---|---|
| hub | 10.0.0.0/16 | hub10: 10.0.1.0/24 | none |
| spoke1 | 10.10.0.0/16; 192.168.0.0/16 | spoke10: 10.10.1.0/24 | isolated192: 192.168.1.0/24 |
| spoke2 | **10.20.0.0/26**; 192.168.0.0/16 | spoke10: 10.20.0.0/27 | isolated192: 192.168.1.0/24 |

The final user phrase referring collectively to “/16” is shorthand for the
address spaces, **not** authorization to widen spoke2's explicit /26.
The /27 is a subnet inside that /26; neither becomes /16.

Inventory: one new RG, three new VNets, five inline subnet definitions, four
directed peering children. No VMs, NICs, disks, NSGs, public IPs, gateways,
storage, monitoring services, feature registrations, or provider registrations.
Tag RG and VNets `lab=true`, `created_by=copilot-lab`, and
`correlation_id=<taskId>`; subnets/peerings do not expose their own tags.
Phase 0 VM capacity preflight is **inapplicable** because no compute is needed.
Any later data-plane objective requires a separate approved design/lease,
Phase 0 catalog **and live validation** gates before its manifest, and respect
for the guide's supported-generation hardware warning; no VM fallback here.

## Exact request contract (Tank implements, do not run from this document)

All commands below must run inside Tank's timeout/sentinel wrapper, never
unbounded. Each process has a maximum **180 seconds**, including any CLI
internal retries; terminate the specific child process tree on timeout.
Check STOP, lease state/expiry before every write and long command, and after
each long command. No concurrent writes to the same VNet.

Preflight: verify account match, Microsoft.Network already registered, and
**parent `virtualNetworks`** provider metadata lists `2026-01-01`.
Use the official peering REST reference above for the documented child API;
a `virtualNetworks/virtualNetworkPeerings` metadata entry need not exist.
Learn says allowlisting is required;
do not invent a feature-registration name. If enrollment cannot be independently
confirmed read-only, the first subnet-peering response is the capability gate.
An enrollment/authorization/API-version rejection is BLOCKED, not an overlap
failure. Do not register anything or downgrade the API under this lease.
GET the exact RG before creation: only an authenticated 404 is a clean baseline;
an existing RG, 403, or ambiguous error blocks all writes.

### Architecture correction / exact Tank `execute.py` gate recommendation

Replace the mandatory child resource-type metadata check with:
`Microsoft.Network.registrationState == "Registered"` AND
`"2026-01-01" in resourceTypes["virtualNetworks"].apiVersions`, matching the
resource-type name case-insensitively. Require the documented pinned peering
REST contract, not a child metadata entry. Keep all other preflight/STOP,
lease, ownership, accounting, and cleanup gates intact. Do not change the API,
prefixes, selectors, topology, or retry policy.

Evidence: `show-output\api-verification-20261016\gate-recommendation.json`
and `idle-proof.json`. Niobe fetched the official `2026-01-01` peering PUT
reference; authenticated exact-RG and exact-peering GETs returned
`ResourceGroupNotFound`, not an invalid-API error. The absent-RG 404 is
**not** proof of Network RP dispatch, enrollment, schema or overlap acceptance.
The first approved peering PUT remains the feature/enrollment capability gate.
Auth/allowlist/policy/API rejection is BLOCKED: no registration, downgrade,
retry or topology repair. This is a materially corrected architecture
objective, not reviewer rejection of `execute.py`; no rejected-artifact
revision lockout applies. Tank owns implementing this gate correction,
the live exact deployment, evidence, and scoped cleanup.

PowerShell bindings (inside Tank's checked execution context):

```powershell
$api = '2026-01-01'
$rg = 'rg-subnet-overlap-20261016-fde5ecf8'
$base = "https://management.azure.com/subscriptions/$sub/resourceGroups/$rg"
$net = "$base/providers/Microsoft.Network/virtualNetworks"
# $sub comes from the verified config/account match; never inline in shared docs.
```

RG: `PUT ${base}?api-version=2022-09-01` with
`{"location":"swedencentral","tags":{"lab":"true","created_by":"copilot-lab","correlation_id":"<taskId>"}}`.
For each of `hub`, `spoke1`, `spoke2`, use
`PUT ${net}/${name}?api-version=2026-01-01`.
VNet body schema below is exact; substitute rows from the address table and
the same tags. Include excluded subnets from the beginning, not after peering.

```json
{
  "location": "swedencentral",
  "tags": {
    "lab": "true",
    "created_by": "copilot-lab",
    "correlation_id": "<taskId>"
  },
  "properties": {
    "addressSpace": {"addressPrefixes": ["<exact VNet prefix>", "<second prefix only for spokes>"]},
    "subnets": [
      {"name": "<participating subnet name>", "properties": {"addressPrefix": "<participating subnet CIDR>"}},
      {"name": "isolated192", "properties": {"addressPrefix": "192.168.1.0/24"}}
    ]
  }
}
```

For hub omit the second prefix and `isolated192` object entirely. Wait for all
three VNets to be `Succeeded` before the first peering PUT.

Four concrete directed requests; substitute each row in the following body:

| Local VNet / child name | Remote VNet | localSubnetNames | remoteSubnetNames |
|---|---|---|---|
| hub / to-spoke1 | spoke1 | ["hub10"] | ["spoke10"] |
| spoke1 / to-hub | hub | ["spoke10"] | ["hub10"] |
| hub / to-spoke2 | spoke2 | ["hub10"] | ["spoke10"] |
| spoke2 / to-hub | hub | ["spoke10"] | ["hub10"] |

```json
{
  "properties": {
    "remoteVirtualNetwork": {"id": "<remote VNet ARM resource ID>"},
    "peerCompleteVnets": false,
    "localSubnetNames": ["<local name from row>"],
    "remoteSubnetNames": ["<remote name from row>"],
    "enableOnlyIPv6Peering": false,
    "allowVirtualNetworkAccess": true,
    "allowForwardedTraffic": false,
    "allowGatewayTransit": false,
    "useRemoteGateways": false
  }
}
```

Write fully substituted bodies beneath the current correlation directory, then:

```powershell
az rest --method put --url "${net}/${local}/virtualNetworkPeerings/${peer}?api-version=$api" --headers 'Content-Type=application/json' --body "@$bodyFile" --output json
az rest --method get --url "${net}/${local}/virtualNetworkPeerings/${peer}?api-version=$api" --output json
```

Equivalent CLI field spelling is `--peer-complete-vnet false`,
`--local-subnet-names`, `--remote-subnet-names`, `--enable-only-ipv6 false`.
Prefer REST above to avoid local CLI typed-model/flag-version differences.
Do not submit `peeringState`, `peeringSyncLevel`, or address-space projection
fields as desired state. These are observations, not replacements for selectors.

## Smallest decisive sequence / stop conditions

1. Record clean baseline and three VNet GETs proving exact prefixes/subnets.
2. Create hub↔spoke1 pair. GET both until `provisioningState=Succeeded` and
   `peeringState=Connected`; this establishes feature capability with the
   excluded 192.168/16 already present. Initial one-sided `Initiated` is normal.
3. Create hub↔spoke2 pair, then GET **all four** to prove simultaneous acceptance.
   Poll at >=30-second intervals, <=3 minutes per pair. Do not sync/re-PUT/retry
   a failed mutation or “fix” selectors/prefixes.
4. **PASS:** all four are Succeeded/Connected simultaneously; all four return
   `peerCompleteVnets=false` and the exact two selector lists above; GETs prove
   both spokes still contain 192.168/16 and spoke2 retains 10.20.0.0/26.
   If returned peered `localAddressSpace` / `remoteAddressSpace` contain
   192.168/16, do not declare PASS; record INCONCLUSIVE and stop.
   Distinguish these projections from `*VirtualNetworkAddressSpace`, which
   describe the whole VNet and may legitimately include the excluded prefix.
5. **FAIL (acceptance):** a service overlap/selected-address-space rejection of
   these exact bodies, with successful resource creation and capability baseline.
   Preserve exact error code/message; do not generalize into a universal service
   limitation. A first-pair overlap rejection is also evidence of rejection of
   this requested topology, but cannot establish the second-spoke-specific cause.
   **BLOCKED:** auth/allowlist/policy/API issues; **INCONCLUSIVE:** timeout,
   missing selectors, partial connectivity, or ambiguous failure. Stop at first
   failed gate; no alternative topology under this lease.

Evidence only:
`show-output/<taskId>/baseline.json`, `vnets-before.json`, four request bodies,
their PUT outputs/errors, `peerings-final.json`, `vnets-final.json`,
`verdict.json`, `restore.json`, and a compact command/timestamp/exit journal.
Preserve Azure request IDs where returned; never capture tokens or `--debug`.
Return the acceptance verdict and restore state within five minutes of decisive
output, before any expanded documentation or publication.

## Lease, restore, time/cost and handoff

Lease: `deploy\.runtime-control\lease.json` (ignored).
Tank is the **only mutation owner**. Coordinator confirms previous owners and
child processes idle, absence of STOP, and unexpired lease before dispatch.
Max 25 minutes **including** <=10-minute restore, 75 tool calls, six mutation
batches, 180 seconds/command. At 80% of any budget, no new experiment work.
Start restore by minute 15 from lease creation at latest to reserve its full
bound; absolute expiry is creation UTC +25 minutes. Tank must replace the
executor's hard-coded 20-minute reserve and 30-minute checkpoint label with
the lease's 15-minute restore-start and 25-minute total limits before running.

Batch accounting (not a six-resource limit):
1. RG creation (one PUT).
2. Three VNet PUTs with inline subnets (three PUTs).
3. Hub↔spoke1 pair (two PUTs, ordered).
4. Hub↔spoke2 pair (two PUTs, ordered).
5. One scoped RG DELETE for restore (one DELETE).
Nine planned ARM writes in five dependency-bounded batches. Failed submissions
count; journal every individual write and batch. Six is a ceiling, not approval
for a sixth diagnostic/retry batch. Check budgets/sentinel between individual
writes; a partial batch still consumes a batch.

**Cleanup approval gate satisfied:** Jose's existing standing authorization,
already recorded in the prior lease after presenting this exact inventory,
permits automatic cleanup only of task-created resources. It remains valid
for this corrected run; do not ask again. The restore target is solely the
newly created exact RG/resources listed here, with the fresh correlation tag.
Never delete pre-existing resources or treat deployment approval alone as
cleanup approval.

Restore: verify exact RG identity + correlation tag, then one
`az rest --method delete --url "${base}?api-version=2022-09-01"` inside the
bounded wrapper. Poll authenticated GET until 404 (>=30 seconds, <=10 minutes
total including DELETE). An accepted async DELETE is not restoration proof.
No deletion outside this fresh RG; never overwrite/reuse an existing RG.
No retry of DELETE, feature changes, or separate resource-repair writes.
If restore times out or identity is uncertain, BLOCKED/freeze; different owner
needs a new recovery lease. Never clear an existing STOP automatically.
Do not claim this new rollback has been live-tested: baseline absence and
post-delete 404 must be collected by the executor.

Expected execution 5–10 minutes, restore usually 1–5 minutes, hard ceilings as
above. Expected resource/traffic cost **$0**: only virtual-network control-plane
objects, no VM/service-hour meters or generated peering traffic. No paid fallback.
No report repo, GitHub publication, commits, diagrams, or history edits.

After Tank returns verdict + restore proof, closes the lease, and has no active
children/queued work, hand one read-only acceptance/restore verification
objective to Niobe under a separate zero-mutation lease. Tank retains the
pre-delete GET evidence; deletion naturally removes the peerings before that
independent review. No bulk evidence work in the live lease.
