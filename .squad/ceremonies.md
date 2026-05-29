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

## Pre-Gate Editorial Review (pre-deploy gate)

| Field | Value |
|-------|-------|
| **Trigger** | optional |
| **When** | after |
| **Condition** | Morpheus has finalized manifest scenarios + pass/fail criteria; before Phase 4 approval gate. Skipped silently when Jose is not publishing this lab. |
| **Facilitator** | Morpheus |
| **Participants** | Kid (reviewer); Morpheus (decides what to incorporate) |
| **Time budget** | focused (one async pass, no recurring dialogue) |
| **Enabled** | ✅ yes |

**Agenda:**
1. Coordinator notifies Kid that Morpheus's manifest draft is ready for editorial review. Kid is given the manifest path; Kid does NOT re-spec the lab.
2. Kid reads the manifest with two narrow questions in mind: (a) does any scenario surface a teachable result worth publishing? (b) does each scenario's evidence plan produce complete, reproducible artifacts — multiple corroborating sources for the headline finding, primary commands that are known-reliable, deliberate-test framing for any pivots (e.g., region change)?
3. Kid returns ONE async comment (≤300 words) to Morpheus. Allowed: (i) extending a scenario's evidence plan with co-primary sources; (ii) demoting known-unreliable commands to secondary evidence; (iii) framing a manifest decision (e.g., region pivot) as a documented test rather than incidental; (iv) waiving the post for this lab outright (recorded in Kid's `history.md`).
4. Morpheus incorporates compatible suggestions into the manifest, discards bloat, and proceeds to Phase 4 approval gate. Disagreements are recorded in `manifest.md` under "Editorial review notes" — Morpheus's call is final on scope.
5. Scribe logs the dispatch in `project-journal.md` only when Kid actually returns a comment (not when the ceremony is skipped).

**Hard rules (enforced by Morpheus + coordinator):**
- Kid may **extend** an already-justified scenario or evidence plan; Kid may **NOT add a distinct mechanism** (new service, second NVA, additional region, new failure mode) unless Morpheus opens that door.
- Kid does **NOT** speak to region selection, VM SKU, cost guardrails, IaC toolchain, or Terraform layout. Those are Morpheus's domain and Jose's research question stays primary.
- This is **consult-only, no veto.** Morpheus retains scope and Jose retains the approval gate.
- **Optional per lab** — if Jose is not publishing this lab, the ceremony is skipped (no dispatch, no comment, no logged milestone).
- Kid does not read deployed state at this point — there isn't one yet. Kid works from the manifest alone.

**Why this ceremony exists:**
On lab #1 (`expressroute-megaport-bgp`), Scenario 2 (BGP community tagging) listed the MCR looking glass as its sole evidence source — the looking glass returned "no endpoint" in production, leaving the post unable to answer the most teachable question in the lab. Two other documented gaps (an unreliable command listed as primary evidence; a region pivot captured as luck rather than a deliberate test) followed the same pattern. A single pre-gate review pass would have flagged the single-point-of-failure evidence design while Morpheus could still add a co-primary source. The cost of running this ceremony is one async comment; the cost of skipping it is a published post that says "we couldn't confirm this" on the headline finding.

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

---

## Blog Publication (lab close gate)

| Field | Value |
|-------|-------|
| **Trigger** | auto |
| **When** | after |
| **Condition** | Niobe validation completed AND Oracle diagram catalogue published; before Phase 3.4 cleanup gate |
| **Facilitator** | Kid |
| **Participants** | Kid (writer); back-request targets as needed (Morpheus / Tank / Trinity / Niobe / Oracle); Jose (approval); Scribe (logs dispatch + project-journal milestone) |
| **Time budget** | focused |
| **Enabled** | ✅ yes |

**Agenda:**
1. Kid reads `labs/<lab>/manifest.md`, `validation.md`, `lessons-learned.md`, `README.md`, `diagrams/*`, and `show-output/*`.
2. Kid names the **one headline finding** in a single sentence. If no headline emerges, Kid waives publication (recorded in `history.md`) and the lab is cleared for cleanup.
3. Kid runs the quality gate: do I have evidence (screenshot / output) for the headline? Do I have a diagram for the mechanism? Is the scenario rich enough to surprise the reader?
4. If any answer is "no," Kid back-requests from the appropriate squad member (Morpheus for scenario tweaks, Niobe for screenshots/outputs, Tank for re-runs, Oracle for diagrams). Squad treats the request as in-scope; Tank may need to re-deploy (lab is still live at this point).
5. Kid drafts the post using the inverted-pyramid template (charter — "Inverted-Pyramid Template" section).
6. Kid runs sanitization grep on the post directory: forbidden GUIDs, ER service keys, Megaport credentials, VM passwords, customer names. Any hit blocks publication until redacted.
7. Kid presents the draft to Jose for approval (unless Jose has waived review for this post).
8. On Jose's approval: Kid publishes to `github.com/erjosito` — rolling repo (`azure-networking-blog`, new folder) by default, or per-lab standalone repo (`azure-net-blog-<lab-slug>`) when warranted.
9. Kid returns a JSON envelope: `{ lab, post_repo_url, post_path, word_count, assets, back_requests, ship_status: "published" | "waived" | "blocked" }`.
10. Kid appends `history.md` (one entry per post or waiver).
11. Squad flips the lab to "shipped externally" only after Kid returns `ship_status: published` or `ship_status: waived`. Scribe logs a project-journal milestone.
12. **Local README back-fill (Niobe).** Coordinator extracts `post_repo_url` + `post_title` (or `waiver_reason`) from Kid's envelope and dispatches Niobe to replace the "Blog post: pending publication" placeholder at the top of `labs/<lab>/README.md` with a real link (or waiver pointer). Niobe edits the single line, Scribe commits with a conventional message (`docs(lab/<slug>): Link Kid's blog post in local README` or `docs(lab/<slug>): Record Kid's blog-post waiver`). This step preserves Kid's boundary against committing to `net-lab-builder` while satisfying Jose's reverse-discoverability rule (local lab → public blog).

**Why this is a hard gate:**
The lab is ephemeral; the blog post is what survives the cleanup and reaches readers who weren't in the room. Cleanup destroys the live resources — if Kid hasn't drafted (or explicitly waived) by then, requesting a refreshed screenshot or command output requires re-deployment, which is wasteful. Run this ceremony BEFORE Phase 3.4 cleanup approval. The local README back-fill (step 12) is a hard requirement — without it the squad's symmetric discoverability rule fails: Kid's post links back to the lab, but the lab doesn't link forward to the post.
