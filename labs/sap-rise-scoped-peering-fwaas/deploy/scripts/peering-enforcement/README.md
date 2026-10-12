# Bounded peering-enforcement runner

Run from the repository root. The original complete sequence stopped at G3's
bounded workload-start timeout; it has not been validated end to end. The
separate `direct_comparison.py` sequence completed the direct-isolation
experiment on 2026-10-05 after read-only reconciliation, with both NVAs off.
No import, help, test, or `--plan` command contacts Azure. The runner never
creates or renews a lease and never repairs a guest.

## Invocation and approval

```powershell
$runner = 'labs\sap-rise-scoped-peering-fwaas\deploy\scripts\peering-enforcement\runner.py'
$out = 'labs\sap-rise-scoped-peering-fwaas\show-output\enforcement-NEW-UTC-STAMP'
python -B $runner --phase inventory --lease COORDINATOR-INVENTORY.json --out $out
# Review the fresh originals, then obtain a new lease for EACH invocation:
python -B $runner --phase G1 --lease COORDINATOR-G1.json --out $out --plan --plan-file .\enforcement-G1-plan.json
python -B $runner --phase G1 --lease COORDINATOR-G1.json --out $out
python -B $runner --phase G2 --lease COORDINATOR-G2.json --out $out --ssh-public-key EXISTING-PUBLIC-KEY.pub
python -B $runner --phase G3 --lease COORDINATOR-G3.json --out $out
python -B $runner --phase G4 --lease COORDINATOR-G4.json --out $out --icmp-priority 100
```

`inventory` requires a **new** root. All subsequent invocations use that same
root. `--plan` prints the exact `allowedMutations` labels and resource-write
counts; optional `--plan-file` saves all argv, bodies, before values and inverses.
It does not execute, consume, validate, or change the supplied lease. Plan G2
with the same public key and G4 with the same approved priority used to execute.

**Design correction requiring coordinator approval:** Azure NSG rule priorities
start at **100**, not 90. G4 refuses 90. Choose a free, sufficiently early
priority from the captured three actual NSGs; pass `--icmp-priority N` and put
`"icmpPriority": N` in the G4 lease. There is no silent priority fallback.

Each execution lease needs the existing policy fields plus:

- `taskId`: unique, never reused, including across output roots.
- `subscriptionId`, `phase`, `startedAtUtc`, `expiresAtUtc`.
- `ownerRole`: `Niobe` for `inventory`, every `collect-*`, and `verify`;
  `Tank` otherwise.
- `allowedMutations`: **all** forward and `undo:*` labels printed by the plan.
  Empty for read-only phases and rejected-trial no-op removals.
- `acceptedCheckpoint`: exact preceding phase from the sequence below. The
  coordinator sets this only after accepting that evidence/baseline.
- `state: active`, `maxMutations: 6` (Tank) or `0` (Niobe),
  `maxToolCalls: 25` (Tank) or `15` (Niobe),
  `commandTimeoutSeconds: 600`, `restoreTimeoutMinutes: 5`.

Tank leases are at most 15 minutes, Niobe at most 8. The final five Tank minutes
are rollback-only. Ordinary commands are capped at 120 seconds; VM start and
creation waits at 600; RunCommand at 300, with guest subprocesses at 30.
Three sequential G3 starts share the ten-minute forward window: slow starts
can therefore block rather than silently extend the lease.
The runner closes its supplied lease as `completed` or `blocked`, recording
counts. `completed` means a named checkpoint, **not** original-state restoration.

## Exact order

Use `python -B $runner --phase PHASE --lease FRESH-PHASE-LEASE.json --out $out`
for each row, with the extra G2/G4 arguments above. Do not automate lease
generation or batch all phases under one lease.

```text
inventory
G1                         source table, associated subnet, static NIC
G2                         source VM + explicit OS disk (two writes)
G3                         hub start, spoke start, workload start; CE untouched
G4                         three narrow inbound ICMP rules
collect-viability          four full route tables, NIC identities, local controls/tools
G5                         workload /32 -> spoke; spoke /32 -> hub
collect-return             route-selection checks and read-only NVA guest state
G6-add
collect-bypass             source /32 -> spoke hypothesis
G6-remove
G7-add
collect-vnetlocal          skip guest probe if service rejected the PUT
G7-remove                 verified rejection means zero-write no-op
G8-add
collect-vnetpeering        explicit API 2025-01-01 service attempt, not CLI enum validation
G8-remove                 verified rejection means zero-write no-op
G9                         remove both standing return controls
collect-subnet            no-transit-UDR baseline and original peering scope
G10                        DELETE both exact scoped peers; no-peering checkpoint
G11-add                    CREATE both full peers, preserving names/flags
collect-full              connected/in-sync peers and endpoint /16 route selections
G11-remove                 DELETE both full peers
G12                        CREATE original writable scoped peering bodies
collect-restored          original scope/negative-control evidence before body cleanup
G13                        remove the three ICMP rules
G14                        delete only source VM, then detached named source OS disk
G15                        delete source NIC, subnet, table
G16                        deallocate only the three originals started by G3
verify                     compare fresh original configurations/identities/power
```

G10/G11/G12 must remain separate: type change is delete/recreate, not an update.
Do not touch the unrelated hub peering. G6/G7/G8 add and remove phases remain
separate so Niobe can capture **accepted** routes before deletion.
Successful-path upper bound is 40 submitted resource writes; failed submissions
also count. Each group reserves every inverse, stays within three forward /
six total writes, and reserves enough CLI calls for checks and rollback.
The runner also enforces 150 minutes, 240 CLI calls, and 48 writes across its
state. The coordinator must account for its own external calls against the
same overall budget.

## Evidence, rejection, and failure

`originals.json` contains fresh full VNet/subnet/peering, route table, NSG, NIC,
VM and disk responses, VM power and RG resource identities. `state.json` is the
durable mutation journal, including actual before state, exact inverse, lease,
cost and pending/applied/rejected/unknown/restored status. Each phase has a plan
and individual UTC/argv/raw stdout/stderr/exit-code records. Successful REST
responses retain their complete body; exact success HTTP status is not exposed
by Azure CLI. A structured ARM HTTP 400 trial error is retained as rejection,
then route absence is checked. Other failures remain unknown, never retried.

Both expected rejection and successful application consume the write budget.
A failure rolls back **only that invocation's proven applied entries**, in
reverse order. STOP/expiry disallows even rollback commands. Unknown writes,
incomplete inverses, partial closure, and failed guest controls freeze the
chain as `BLOCKED`. Do not edit the journal to replay it: use a separately
approved recovery objective/owner. Leases are additionally locked/consumed by
task ID under `deploy\.runtime-control`, not just by output directory.

Collectors save all four full NIC route responses without `--query`, following
actual same-subscription/RG continuation links within the budget. NIC identities
come from the first accepted viability capture; subsequent phases do not alter
NICs. Guest transport limits each payload to 2,800 bytes; paging is a blocker
rather than silent evidence truncation. No workload RunCommand is attempted.
Local ICMP control or management/tool failure blocks without guest repair.
The coordinator must review captured filter/NAT/rp_filter state and outbound
NSG policy before accepting the return checkpoint.

**No concurrent packet-capture orchestration is provided.** Parent/Niobe may use
separately bounded SSH captures after source availability. There are no
persistent tcpdump jobs. Route rows, mtr, ping failure, or absent captures alone
do not prove a particular Azure drop or symmetric NVA bypass. Ping/mtr exit
statuses are evidence, not automatically a PASS verdict.

SKU/availability/deployment validation is a separate optional coordinator
preflight; there is no SKU/region fallback. B2ts_v2, Jammy Gen2, Standard SSD,
existing public key and no public IP are fixed. No gateway, ARS, ER, BIRD,
policy-routing, NAT, package-install or broad Terraform mutation exists.

## Offline tests

```powershell
python -B -m unittest discover -s labs\sap-rise-scoped-peering-fwaas\deploy\scripts\peering-enforcement -p 'test_*.py' -v
```

## Direct-isolation recovery experiment

`direct_comparison.py` accepts `--prior` for the immutable initial experiment
and `--out` for a new journal. It inherits only proven source-resource creation
entries, not the failed power phase. It needs fresh leases for every phase:
two endpoint ICMP rules, baseline capture, individual next-hop trials,
subnet/full/subnet peering replacement and capture, then exact cleanup.
Both NVAs and CE must remain deallocated during every traffic capture.
Only the two endpoint NICs have fresh effective-route captures in this mode.

The service's structured `InvalidRequestFormat`/`InvalidJson` rejection of
`VNetPeering` can lack an HTTP-status prefix. The explicit
`collect-reconcile-rejection` phase verifies the preserved rejection and empty
route table without replaying a write. It appends a recovery record while
retaining the original unknown journal entry.

The authoritative outcome is in
`show-output/enforcement-direct-20261005T081250Z/verdict.json` relative to the
lab root. Independent `restore-verification.json` confirms original identities,
configuration and power states. The raw final runner status is retained as
blocked because its original comparison did not recognize the service's
capitalized `LastOwnershipUpdateTime` field; normalization now handles both
casings, without ignoring resource identity changes.
