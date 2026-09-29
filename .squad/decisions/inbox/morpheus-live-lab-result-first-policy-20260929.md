### 2026-09-29T08:49:30.289+02:00: Result-first live-lab governance
**By:** Morpheus

**What:** Adopted `.squad/live-lab-policy.md` as the mandatory contract for the
coordinator and all active agents. Live work now uses one objective, phase,
owner, and bounded lease; Tank mutation and Niobe single-scenario validation
have separate hard budgets; verdicts are returned within five minutes of
decisive output; restore is bounded; STOP drains queued work; child processes
must time out and terminate as a tree; and evidence expansion, diagrams,
documentation, vault backfill, and publication occur only after verdict,
restore, and confirmed owner idle. Ralph monitors checkpoint/cost deadlines,
and incident review is owned separately from live execution.

**Why:** The 2026-09-28 `vwan-ipsec-over-er-backup` incident delayed the
requested result for roughly 20 hours because deployment, remediation,
validation, evidence reconstruction, indexing, documentation, and retries were
queued onto one long-lived agent, including an unbounded child process and
contradictory work after STOP. The new policy preserves full evidence quality
while sequencing it after the requested verdict and safe restore.
