# Repository instructions

## Default: one accountable agent

Use a single lead agent for requirements, design, implementation, deployment,
diagnosis, validation, reporting, and cleanup. Complete dependent work directly;
do not dispatch an agent merely because the work crosses a specialist boundary.

Start normal CLI sessions with `copilot`, without `--agent squad`. Squad is an
explicit opt-in for a user-requested team session, not the default for lab work.
Start a fresh session after changing modes; use `/instructions` to inspect the
loaded instructions.

In single-agent mode, this file and `.squad/live-lab-policy.md` define repository
workflow. Legacy Squad routing, ceremonies, role-exclusive permissions, mandatory
handoffs, Scribe/Ralph dispatches, and model defaults do not apply. Technical
references remain useful, but do not reinstate their old orchestration rules.
Do not bulk-load charters, histories, decisions, or evidence archives.

## Optional independent review

Use a reviewer when requested, or for a specific high-risk change, disputed
interpretation, or evidence gap that benefits from an independent perspective.
Review is not a mandatory phase for every edit or command. Give the reviewer a
bounded question, relevant files/evidence, and applicable repository rules.
The reviewer is read-only: no cloud mutations, fixes, nested delegation, or
shared-state writes. The lead resolves findings and remains accountable.

Delegate other work only when substantial, independent work genuinely benefits
from a separate context. Do not create a serial specialist pipeline. Retain one
live mutation owner; never overlap reviewer work with changes to its evidence.
Use existing CLI model preferences unless the user explicitly chooses otherwise.
Do not assume a task's display name establishes a per-agent model setting.

## Plan the smallest decisive experiment

- Work in `labs/<lab-name>/`; reuse shared tooling in `src/`, `scripts/`, and
  `tools/`. Search filenames/headings first and read only relevant references in
  `docs/`, `.squad/skills/`, and prior labs. Invoke matching available skills.
- Before provisioning, record the question, resource/address plan, regions/SKUs,
  cost/lifetime envelope, and scenarios. Each scenario needs a clean baseline,
  hypothesis, decisive assertion, required evidence, stop criteria, and restore.
  Separate optional evidence from the acceptance gate.
- Use the cheapest viable resources and verify subscription-specific availability.
  Do not silently change a requested region, mechanism, or cost envelope.
- Honor deployment authorization already granted for the task. Otherwise present
  the resource list, regions, SKUs, estimated time/cost, and obtain approval.
  New paid scope or external commitments need authorization.
- Before live work, read `.squad/live-lab-policy.md` and its execution skill.
  One bounded scenario may include implementation, validation, and restore by
  the same lead under one budget. Never refresh a lease to hide retries or expiry.

## Evidence and result first

Provisioning success, an established BGP session, or an installed route alone
does not prove an end-to-end outcome. Test the requested traffic and path,
including return traffic and failure/failback where relevant. Distinguish
observations, hypotheses, documented behavior, and unresolved questions.

Capture timestamp/correlation, command, decisive output, assertion, and restore
proof. Return `PASS`, `FAIL`, `INCONCLUSIVE`, or `BLOCKED` promptly with evidence
and current state. Missing data, empty billing results, or failed probes are not
success. Check all required scenarios before claiming completion.

Keep a compact current checkpoint in the lab's existing README or validation
record: objective, last verified state, evidence links, open blockers, next
bounded action, and resource/restore state. Keep private IDs/control files out
of public checkpoints. Do not reconstruct whole transcripts or append the same
update to several agent histories.

## Isolation, secrets, and cleanup

- Preserve unrelated work. Concurrent labs use separate worktrees where practical,
  lab-scoped leases/output paths, explicit subscriptions/projects, and isolated
  authentication contexts. Do not switch another session's cloud defaults,
  change its resources, clear its STOP sentinel, or renew its lease.
- Fetch credentials at runtime; never commit secrets, tokens, private keys,
  passwords, service keys, or credential-bearing state. Sanitize published
  evidence, including subscription and tenant IDs. Keep runtime inventories,
  leases, and sensitive parameters in ignored locations.
- After validation, preview and verify the exact deletion inventory, then
  automatically clean up only resources created for this task under the user's
  standing cleanup authorization. Never delete pre-existing resources used for
  testing. Honor explicit keep-running instructions and narrower authorization;
  ask if ownership or permission is unclear. Verify deletion and residual costs.
- Follow provider dependency order, especially ExpressRoute connections/peering
  before Megaport VXCs/MCRs and final resource-group teardown. Do not delete a
  resource group containing reused or other-session resources.

## Finish offline

After verdict and bounded restore, produce the requested report and diagrams
from stable evidence. Follow `labs/README.md`; every design studied, including
negative results, gets a verdict and evidence link. Screenshots are best-effort;
CLI/API evidence is authoritative. Run the smallest relevant existing checks
for code changes.

Blog publication is opt-in and requires the user's publication approval.
Documentation, editorial requests, screenshots, and vault backfill must not
delay verdict, restore, or authorized cleanup. A new experiment needs new scope,
not an editorial back-request appended to a live run.

For personal knowledge work, invoke `shared-knowledge`, follow the target vault's
`AGENTS.md`, and save only sanitized synthesis. The lead may do this directly;
Trinity is not a mandatory intermediary in single-agent mode.
