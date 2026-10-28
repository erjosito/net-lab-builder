# SKILL: Live Lab Execution Circuit Breaker

**Version:** 2.1
**Owner:** Lead agent (Morpheus in opt-in Squad mode)
**Created:** 2026-09-28
**Applies to:** Any agent that can mutate a live Azure, GCP, Megaport, or guest-OS lab

---

## Purpose

Enforce `.squad/live-lab-policy.md` so an approved live action cannot turn into
an open-ended deployment, validation, evidence-generation, documentation, or
retry loop. Service-specific approval and cleanup gates still apply.
Honor authorization already granted under `AGENTS.md`; do not create another
approval round solely because execution passes a former Squad role boundary.

## Execution mode

Read `AGENTS.md` and `.squad/live-lab-policy.md`. Single-agent mode is the
default: one lead designs, implements, validates, and restores one bounded
scenario without role handoffs. Optional reviewers are read-only. Squad-only
role separation applies only when the user explicitly requests Squad.
Documentation/vault/publication work is offline and never gates safe restore
or authorized cleanup. Do not load member histories to execute this procedure.

## 1. One lease, one objective

Before live execution, the lead (coordinator in Squad mode) creates an ignored
control directory, after confirming no other owner has active work there:

```text
labs/<lab>/deploy/.runtime-control/
  lease.json
  STOP
```

`STOP` is absent for a new lease. `lease.json` contains:

```json
{
  "taskId": "<unique-id>",
  "ownerRole": "lead",
  "objective": "<one bounded scenario including validation and restore>",
  "allowedMutations": ["<exact operations>"],
  "forbiddenWork": ["unrelated scenarios", "bulk evidence import", "documentation expansion"],
  "rollback": "<tested restore operation>",
  "expiresAtUtc": "<timestamp>",
  "maxToolCalls": 150,
  "maxMutations": 6,
  "commandTimeoutSeconds": 1200,
  "restoreTimeoutMinutes": 15,
  "lastCheckpointUtc": "<timestamp>",
  "state": "active"
}
```

- Single-agent scenario default: **60 minutes, 150 completed tool calls,
  6 mutations**, including required validation and restore.
- Squad Tank mutation uses the same limits; separate read-only validation
  (Niobe in Squad mode) uses **30 minutes, 75 calls, zero mutations**.
- Offline evidence/docs default: **45 minutes, 100 calls, zero live mutations**.
- `ownerRole` identifies the actual owner; retain any lab-specific wrapper's
  required schema. Close the prior lease and prove commands idle before starting
  a new one. Never overwrite another session's lease or clear its STOP file.
- The approved experiment may set lower limits; it may not silently raise them.
- A managed-resource operation expected to exceed 20 minutes must have its own
  explicit timeout and progress criterion in the lease. It does not extend the
  agent-turn ceiling implicitly.
- The agent checks lease state, expiry, and `STOP` immediately before every
  mutation and every command expected to exceed 60 seconds, after every
  long-running command, and before commit.
- The lead/coordinator records a checkpoint at least every 15 minutes or 25 tool
  calls with elapsed time, completed mutations, and remaining budget.
- At 80% of elapsed, tool-call, or mutation budget, stop starting new work.
  Capture state, perform only
  the approved rollback/closure checks, and return a checkpoint.
- At expiry, return immediately after terminating child processes. Do not
  diagnose, retry, document, or continue cleanup. An incomplete restore becomes
  `BLOCKED`. Recovery requires a materially new plan, explicit approval, a
  fresh lease, and confirmed idle. In single-agent mode the same lead may
  execute recovery after user or independent review of the plan; Squad requires
  a different recovery owner.

## 2. Separate live operations from evidence expansion

- **Single-agent scenario:** the lead defines the baseline, decisive signal,
  required evidence, approved mutations, and stop/restore criteria, then
  implements, validates, returns a verdict, and verifies restore within the
  same lease. Routine checks do not require fresh agents or budget resets.
- **Squad-only Trinity turn:** define one scenario, decisive signal, minimal evidence, and
  stop/restore criteria.
- **Squad-only Tank turn:** deploy or mutate, plus the minimum before/action/after evidence
  needed to prove and restore that mutation.
- **Squad-only Niobe turn:** validate exactly one scenario, return its verdict, and verify
  baseline restore after Tank is idle and the mutation lease is closed.
- **Offline audit turn:** historical transcript import, index regeneration,
  corpus sanitization, report updates, and large commits; the same lead may own it.
- **Squad Oracle/Kid/Scribe turns:** only after live mutation is idle and their input
  evidence is stable.
- **Optional independent incident review:** read-only, owned by a reviewer who
  is not the active execution owner (Morpheus or designated reviewer in Squad).
- Do not reconstruct historical sessions or recursively scan the complete
  evidence corpus while a deployment/remediation command is active.
- Generated evidence directories are outputs, never inputs to collectors.
  Sanitization defaults to the newly created correlation directory. A deliberate
  whole-lab scan is a separate offline task with its own file-count and elapsed
  ceilings.
- Within 5 minutes of decisive output, return `PASS`, `FAIL`, `INCONCLUSIVE`, or
  `BLOCKED` with the decisive evidence path and restore state. Documentation
  quality is preserved after this verdict; it may not delay it.

## 3. Command controls

- Every external command must have a timeout within its lease's remaining
  budget. Defaults: 20 minutes for mutation/scenario commands, 10 minutes for
  read-only validation or offline work; a lower approved limit wins.
- A command expected to run longer must be named in the lease with a maximum
  duration and a progress signal. No-progress thresholds remain mandatory.
- Wrappers must not use an unbounded `WaitForExit()`. On timeout they terminate
  the specific child process tree, record exit/timeout state, and enter rollback.
- Detached commands and child processes that continue after final output or
  handoff are forbidden.
- Polling intervals are at least 30 seconds for managed resources. Repeated
  unchanged status does not justify additional probes.
- A failed acceptance gate permits exactly one rollback, not diagnosis plus
  another mutation, unless a new lease is approved after the prior turn ends.

## 4. Stop and queued-message protocol

1. Lead/controller writes `STOP`, changes lease state to `stop-requested`, and
   uses the runtime cancellation primitive if one exists.
2. If a worker was dispatched, send one STOP message only. Send no retry,
   audit expansion, or replacement objective to the same active agent.
3. A delivered message is presumed queued until the agent reports a new turn.
   A final/idle response can describe the prior turn while a queued turn is
   already active; verify both turn number and runtime status.
4. If the agent is still running 5 minutes after STOP, escalate to runtime
   cancellation. At 10 minutes, cancel the containing job/process if available
   and freeze all lab mutations; notify Jose with the last checkpoint.
5. If cancellation is unavailable, do not add messages. Preserve the control
   file, notify the user/controller, and wait for the active command boundary.
   Do not start replacement work without proof that prior commands are idle.

## 5. Relaunch rule

- Do not relaunch an agent for the same failed objective.
- Discard every queued message from an expired/stopped lease.
- Recovery is allowed only after runtime/process state proves prior work idle
  and a materially new plan is explicitly approved with a new lease. The same
  lead may resume after user or independent review; Squad requires a fresh
  agent/different owner and Morpheus approval. STOP still requires explicit
  authorization to resume. Never append new scope to an active lease.
- In single-agent mode, read-only recovery verification and architecture
  correction remain the lead's responsibility; no automatic reviewer dispatch.
  In Squad mode, verification belongs to Niobe and design to Trinity/Morpheus.

## 6. Completion gate

A live turn is complete only when:

- the lease is `completed`, `rolled-back`, or `blocked`;
- no child command remains active;
- the exact mutation count and final state are recorded;
- rollback is verified when required;
- no queued follow-up remains for that agent;
- evidence expansion waits for a separate offline lease, which may have the
  same owner in single-agent mode.

## 7. Checkpoint and verdict output

Report at lease start, every 15 minutes or 25 calls, 80% of any budget, verdict,
restore completion/block, and expiry:

```text
LIVE <taskId> | <phase> | <elapsed>/<limit> | calls <used>/<limit> |
mutations <used>/<limit> | state <running|verdict|restoring|blocked|stopped> |
next <single bounded action>
```

No checkpoint for 15 minutes requires checking owner/command state and freezing
new mutations until it is known. Use bounded commands/runtime controls; this
skill does not itself launch a watchdog. Squad uses Ralph/Morpheus escalation.

## 8. Scenario reset

- Each scenario starts from a named clean baseline and includes a restore plan.
- Restore consumes the same lease and is capped at 15 minutes by default.
- No next scenario starts until the lead (Niobe in Squad mode) verifies baseline
  state. A blocked restore freezes subsequent scenarios until recovery succeeds.
- If restore misses its budget, return `BLOCKED`; do not keep repairing under the
  expired scenario lease.
