# Ceremonies

> Team meetings that happen before or after work. Each squad configures their own.

## Design Review

| Field | Value |
|-------|-------|
| **Trigger** | auto |
| **When** | before |
| **Condition** | multi-agent task involving 2+ agents modifying shared systems |
| **Facilitator** | lead |
| **Participants** | all-relevant |
| **Time budget** | focused |
| **Enabled** | ✅ yes |

**Agenda:**
1. Review the task and requirements
2. Agree on interfaces and contracts between components
3. Identify risks and edge cases
4. Assign action items

---

## Retrospective

| Field | Value |
|-------|-------|
| **Trigger** | auto |
| **When** | after |
| **Condition** | build failure, test failure, or reviewer rejection |
| **Facilitator** | lead |
| **Participants** | all-involved |
| **Time budget** | focused |
| **Enabled** | ✅ yes |

**Agenda:**
1. What happened? (facts only)
2. Root cause analysis
3. What should change?
4. Action items for next iteration


---

## Retrospective with Enforcement

| Field | Value |
|-------|-------|
| **Trigger** | auto |
| **When** | weekly |
| **Condition** | No *retrospective* log in .squad/log/ within the last 7 days |
| **Facilitator** | lead |
| **Participants** | all |
| **Time budget** | focused |
| **Enabled** | yes |
| **Enforcement skill** | retro-enforcement |

**Agenda:**
1. What shipped this week? (closed issues, merged PRs)
2. What did not ship? (open issues, blockers)
3. Root cause on any failures
4. Action items -- each MUST become a GitHub Issue labeled retro-action

**Coordinator integration:**
At round start, call Test-RetroOverdue (see skill retro-enforcement). If overdue, run this ceremony before the work queue.

**Why GitHub Issues, not markdown:**
Production data: 0% completion across 6 retros using markdown checklists, 100% after switching to GitHub Issues.

---

## Vault Backfill (lab close gate)

| Field | Value |
|-------|-------|
| **Trigger** | auto |
| **When** | after |
| **Condition** | Niobe validation completed; before Phase 3.4 cleanup gate |
| **Facilitator** | Trinity |
| **Participants** | Trinity (writer); Scribe (logs dispatch + project-journal milestone) |
| **Time budget** | focused |
| **Enabled** | ✅ yes |

**Agenda:**
1. Trinity re-reads `<vault>/AGENTS.md` and `_Index.md` to refresh on schema and existing coverage
2. Trinity indexes the vault slice for the lab's topic area (`Services/`, `Topics/`, `Patterns/`, `Labs/`)
3. Trinity triages `labs/<lab>/lessons-learned.md` + `labs/<lab>/validation.md` for vault-worthy items
4. Trinity appends to existing `Services/`/`Topics/` pages **OR** creates a `Labs/YYYY-MM-<LabName>.md` page (lab summary template from vault `AGENTS.md`)
5. Trinity updates `_Index.md` "Recently added" with a one-line entry citing the touched pages
6. Trinity sanitization-checks every touched vault file (PowerShell `Select-String` for the forbidden GUIDs)
7. Trinity returns a JSON envelope to Squad listing every vault path written + the essence per entry
8. Squad flips Phase 3.3.x to `[x]` only after sanitization verification; Scribe logs a project-journal milestone

**Why this is a hard gate:**
Cleanup destroys the live lab — if vault backfill hasn't happened, the lessons disappear with the resources. The vault is the only artifact that survives the ephemeral lab.
