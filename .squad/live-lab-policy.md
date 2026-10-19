# Mandatory Live-Lab Operating Policy

**Authority:** Jose Moreno directive, 2026-09-29; single-agent migration, 2026-10-19
**Applies to:** the lead agent, optional reviewers/workers, and opt-in Squad sessions
**Operational procedure:** `.squad/skills/live-lab-execution/SKILL.md`

This policy is mandatory whenever a command can inspect, deploy, mutate,
validate, restore, or delete a live lab. Evidence quality is unchanged; only
the order of work changes so the requested verdict is returned first.

## Execution modes

`AGENTS.md` selects **single-agent mode by default**. The lead owns a bounded
scenario end-to-end: design, implementation, validation, verdict, and restore.
These are sequential steps, not mandatory agent handoffs. Optional independent
review is read-only; the lead resolves its findings. Legacy charter/routing
requirements for fresh phase owners, Scribe/Ralph dispatch, editorial gates,
and pre-cleanup vault backfill do not apply in this mode.

**Squad mode** applies only when the user explicitly requests the Squad team.
Its role-separated dispatch rules below remain available in that mode. Shared
safety requirements apply in both modes. Do not change another session's active
lease or migrate a running operation in place.

## 1. Result first

1. Return the requested scenario verdict before documentation, diagrams,
   historical reconstruction, index generation, sanitization of old evidence,
   or publication.
2. During a live scenario, capture only minimum viable evidence: command,
   timestamp/correlation ID, decisive raw output, pass/fail assertion, and
   restore proof.
3. Within **5 minutes of decisive output**, publish the user-visible verdict:
   `PASS`, `FAIL`, `INCONCLUSIVE`, or `BLOCKED`, with the decisive evidence path
   and restore state.
4. Bulk evidence work starts only after the verdict is visible, the scenario is
   restored or explicitly blocked, live commands are idle, and a separate
   offline lease has been assigned. The same lead may own the offline lease;
   blocked restore never permits more live mutations under an offline lease.

## 2. One objective, one owner, one lease

In single-agent mode, one scenario lease includes only its approved mutations,
required validation, and bounded restore. The lead verifies acceptance and
baseline restoration; a reviewer is optional, not a prerequisite for routine
progress. Unrelated scenarios and bulk offline work require separate leases.

In opt-in Squad mode, the following are separate work units and must not share
one active lease:

| Phase | Owner | Lease scope |
|---|---|---|
| Test design | Trinity | One scenario, minimal test, decisive signal, stop criteria |
| Deployment or mutation | Tank | Exact approved mutations and bounded restore |
| Validation | Niobe | One scenario, read-only commands, verdict, restore verification |
| Evidence import/expansion | Separate offline owner | Bounded new correlation directory only |
| Documentation/diagrams | Oracle or assigned writer | Stable evidence only |
| Publication | Kid | Stable, restored evidence only |
| Incident review | Morpheus or designated reviewer | Never the active execution owner |
| Lease/cost monitoring | Ralph | Independent monitoring and escalation |

- Never append scope to an active live lease.
- Do not split a single-agent scenario into fresh agents for routine readiness,
  mutation, and verification checks. Scope and budgets do not reset between steps.
- In Squad mode, never reuse one agent across unrelated phases merely because
  it has context.
- No bulk evidence, documentation, or publication work runs while live mutation
  is active, regardless of owner.
- When independent incident review is needed, the reviewer is not the live
  execution owner and makes no mutations.

## 3. Hard budgets

Every lease records `expiresAtUtc`, `maxToolCalls`, `maxMutations`,
`commandTimeoutSeconds`, and `restoreTimeoutMinutes`. Defaults are:

| Lease | Elapsed | Tool calls | Mutations | Per command | Restore |
|---|---:|---:|---:|---:|---:|
| Single-agent scenario, including validation/restore | 60 min | 150 | 6 | 20 min | 15 min |
| Read-only validation, or Squad Niobe | 30 min | 75 | 0 | 10 min | verification only |
| Squad Tank deployment/mutation | 60 min | 150 | 6 | 20 min | 15 min |
| Offline evidence/docs | 45 min | 100 | 0 live | 10 min | n/a |

A lower approved scenario limit wins. At **80%** of any budget, start no new
work: finish the current bounded command, capture the checkpoint, restore if
authorized, return, and request a new lease. At expiry, the agent must return;
it may not diagnose, retry, document, or continue cleanup. If restore cannot
finish inside its budget, report `BLOCKED` and freeze mutation. Recovery needs
a materially new plan, explicit approval, a fresh lease, and confirmed prior
process idle; do not silently renew or retry. In single-agent mode the same
lead may execute approved recovery after user or independent review of the
plan. Squad recovery retains the different-owner requirement.

## 4. Checkpoints and user-visible cadence

The live owner reports at:

1. lease start;
2. every **15 minutes or 25 tool calls**, whichever comes first;
3. 80% of any budget;
4. verdict;
5. restore completion or restore block;
6. lease expiry.

Use this exact compact shape:

```text
LIVE <taskId> | <phase> | <elapsed>/<limit> | calls <used>/<limit> |
mutations <used>/<limit> | state <running|verdict|restoring|blocked|stopped> |
next <single bounded action>
```

Silence beyond 15 minutes is an escalation condition, not evidence that work
is healthy. Use bounded commands and runtime timeout/cancellation controls;
do not assume an unlaunched watcher is monitoring the session. The lead reports
the last checkpoint and freezes new mutation until command/owner state is known.
In Squad mode, Ralph alerts Morpheus, who stops new dispatches.

## 5. Process and sentinel safety

- Check lease state, expiry, and `deploy/.runtime-control/STOP` immediately
  before every mutation and every command expected to exceed 60 seconds.
- Every child process has an explicit timeout. On timeout, terminate the
  specific process tree, record timeout state, and enter restore/return.
- Unbounded waits, detached live commands, and background work that survives an
  agent's final output or handoff are forbidden.
- A final response is not complete until all child processes are terminated or
  transferred under a named active lease.

## 6. STOP is queue drain

1. The lead or controlling runtime writes `STOP`, marks the lease
   `stop-requested`, and cancels the owned command. In Squad mode the coordinator
   invokes external cancellation and sends one STOP message.
2. No retry, follow-up, evidence job, or replacement objective may be queued to
   that agent.
3. At 5 minutes without idle confirmation, cancel the agent/runtime externally.
   At 10 minutes, terminate the containing process/job if available, freeze all
   lab mutations, and notify Jose with the last checkpoint.
4. Resuming after STOP requires explicit authorization, a materially new plan,
   a new lease, and runtime/process confirmation that the prior work is idle.
   Squad replacement additionally requires a fresh agent. Queued work from the
   expired lease is discarded, never replayed. If cancellation is unavailable,
   report that limitation and do not start replacement work.

## 7. Scenario reset and evidence boundaries

- Every scenario defines a clean baseline and a bounded restore before it runs.
- Restore is part of the scenario budget, not an unlimited tail.
- The next scenario cannot begin until the lead (Niobe in Squad mode) verifies
  the baseline. A blocked restore freezes further scenarios until approved
  recovery restores and verifies the baseline.
- Never recursively scan a generated evidence tree during live operations.
  Collectors, indexers, and sanitizers target only the current correlation
  directory with explicit file-count and elapsed limits.
- Full-corpus reconstruction, indexing, publication, and durable documentation
  happen after verdict and restore. They may improve presentation, but they may
  not delay or revise the raw verdict without a new validation lease.
