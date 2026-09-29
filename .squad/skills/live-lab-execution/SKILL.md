# SKILL: Live Lab Execution Circuit Breaker

**Version:** 2.0
**Owner:** Morpheus
**Created:** 2026-09-28
**Applies to:** Any agent that can mutate a live Azure, GCP, Megaport, or guest-OS lab

---

## Purpose

Enforce `.squad/live-lab-policy.md` so an approved live action cannot turn into
an open-ended deployment, validation, evidence-generation, documentation, or
retry loop. Service-specific approval and cleanup gates still apply.

## 1. One lease, one turn, one objective

Before dispatch, the coordinator creates an ignored control directory:

```text
labs/<lab>/deploy/.runtime-control/
  lease.json
  STOP
```

`STOP` is absent for a new lease. `lease.json` contains:

```json
{
  "taskId": "<unique-id>",
  "ownerRole": "Tank",
  "objective": "<one bounded live action>",
  "allowedMutations": ["<exact operations>"],
  "forbiddenWork": ["validation matrix", "bulk evidence import", "documentation expansion"],
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

- Tank mutation default: **60 minutes, 150 completed tool calls, 6 mutations**.
- Niobe validation default: **30 minutes, 75 calls, zero mutations**.
- Offline evidence/docs default: **45 minutes, 100 calls, zero live mutations**.
- The approved experiment may set lower limits; it may not silently raise them.
- A managed-resource operation expected to exceed 20 minutes must have its own
  explicit timeout and progress criterion in the lease. It does not extend the
  agent-turn ceiling implicitly.
- The agent checks lease state, expiry, and `STOP` immediately before every
  mutation and every command expected to exceed 60 seconds, after every
  long-running command, and before commit.
- The coordinator records a checkpoint at least every 15 minutes or 25 tool
  calls with elapsed time, completed mutations, and remaining budget.
- At 80% of elapsed, tool-call, or mutation budget, stop starting new work.
  Capture state, perform only
  the approved rollback/closure checks, and return a checkpoint.
- At expiry, return immediately after terminating child processes. Do not
  diagnose, retry, document, or continue cleanup. An incomplete restore becomes
  `BLOCKED` and requires a fresh recovery lease owned by another agent.

## 2. Separate live operations from evidence expansion

- **Trinity turn:** define one scenario, decisive signal, minimal evidence, and
  stop/restore criteria.
- **Tank turn:** deploy or mutate, plus the minimum before/action/after evidence
  needed to prove and restore that mutation.
- **Niobe turn:** validate exactly one scenario, return its verdict, and verify
  baseline restore after Tank is idle and the mutation lease is closed.
- **Offline audit turn:** historical transcript import, index regeneration,
  corpus sanitization, report updates, and large commits.
- **Oracle/Kid/Scribe turns:** only after live mutation is idle and their input
  evidence is stable.
- **Incident review:** owned by Morpheus or a designated reviewer who is not the
  active execution owner.
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

- Every external command must have a timeout. Default: 20 minutes.
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

1. Coordinator writes `STOP`, changes lease state to `stop-requested`, and uses
   the runtime cancellation primitive if one exists.
2. Coordinator sends one STOP message only. It sends no retry, audit expansion,
   or replacement objective to the same active agent.
3. A delivered message is presumed queued until the agent reports a new turn.
   A final/idle response can describe the prior turn while a queued turn is
   already active; verify both turn number and runtime status.
4. If the agent is still running 5 minutes after STOP, escalate to runtime
   cancellation. At 10 minutes, cancel the containing job/process if available
   and freeze all lab mutations; notify Jose with the last checkpoint.
5. If cancellation is unavailable, do not add messages. Preserve the control
   file, notify the incident commander, and wait for the active command boundary.

## 5. Relaunch rule

- Do not relaunch an agent for the same failed objective.
- Discard every queued message from an expired/stopped lease.
- A fresh agent is allowed only after runtime and process state prove the prior
  owner idle, and Morpheus defines a materially new, approved objective with a
  new lease. Never append new scope to an active lease.
- Read-only recovery verification is a different objective and belongs to
  Niobe. Architecture correction remains Trinity/Morpheus work.

## 6. Completion gate

A live turn is complete only when:

- the lease is `completed`, `rolled-back`, or `blocked`;
- no child command remains active;
- the exact mutation count and final state are recorded;
- rollback is verified when required;
- no queued follow-up remains for that agent;
- evidence expansion is handed to a separate offline turn.

## 7. Checkpoint and verdict output

Report at lease start, every 15 minutes or 25 calls, 80% of any budget, verdict,
restore completion/block, and expiry:

```text
LIVE <taskId> | <phase> | <elapsed>/<limit> | calls <used>/<limit> |
mutations <used>/<limit> | state <running|verdict|restoring|blocked|stopped> |
next <single bounded action>
```

No checkpoint for 15 minutes triggers Ralph escalation and a freeze on new
dispatches until Morpheus confirms owner state.

## 8. Scenario reset

- Each scenario starts from a named clean baseline and includes a restore plan.
- Restore consumes the same lease and is capped at 15 minutes by default.
- No next scenario starts until Niobe verifies baseline state.
- If restore misses its budget, return `BLOCKED`; do not keep repairing under the
  expired scenario lease.
