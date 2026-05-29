# Squad Decisions

## Active Decisions

### 2026-05-29T11:33:11+02:00: User directive — Trinity ↔ Obsidian vault

**By:** Jose (via Copilot Coordinator)

**What:** Trinity (Network SME) must have read+write access to Jose's personal Obsidian vault about Azure Networking, located in his OneDrive. The relationship is bidirectional:

1. **Read path** — Trinity should consult the vault as a primary knowledge source whenever she designs, reviews, or troubleshoots a lab. The vault is Jose's accumulated Azure Networking notes and supersedes generic public docs when they conflict.
2. **Write path** — Trinity is responsible for backfilling the vault with new findings, troubleshooting tips, gotchas, anomalies, and lessons learned from every lab the squad ships. Backfills happen at lab close (post-validation, pre-cleanup) so the vault grows monotonically.

**Why:** User-requested standing capability. The vault is Jose's curated long-term memory; the squad's labs are short-lived but generate high-value insights that would otherwise be lost at cleanup. Wiring Trinity as the steward keeps the knowledge base in sync with what the squad learns.

**Scope:**
- Trinity's charter (`.squad/agents/trinity/charter.md`) must document the read+write workflow and exact vault path.
- The "lab close" checklist (Niobe or Scribe checkpoint) must include a "vault backfill complete?" gate before cleanup is offered.
- Sanitization rules apply equally to the vault — no subscription IDs, tenant IDs, API keys, or VM passwords in vault content.
- Vault writes happen on the local filesystem; OneDrive sync is opaque to the squad.

**Status:** Merged by Scribe 2026-05-29.
**Cross-links:** [agents/trinity/charter.md](agents/trinity/charter.md) (Vault Stewardship) · [team.md](team.md) (Member Notes) · [routing.md](routing.md) (rule #15) · [ceremonies.md](ceremonies.md) (Vault Backfill)

---

### 2026-05-29T14:18+02:00: User directive — Kid dispatched pre-cleanup for lab #1 blog draft

**By:** Jose (via Copilot Coordinator)

**What:** Kid (blog-writer 📝) dispatched to produce a blog draft for lab #1 (`expressroute-megaport-bgp`) before Tank cleanup. Two-stage workflow: (1) draft complete and committed to `blog-draft/` first; (2) publish to the public rolling repo separately after Jose's review. Rolling blog repo (`github.com/erjosito/azure-networking-blog`) confirmed as default publishing target.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/copilot-directive-20260529T141813-kid-dispatch.md`

---

### 2026-05-29T14:18+02:00: Dispatch confirmed — pre-cleanup timing, draft-only, rolling blog repo default

**By:** Jose (via Copilot Coordinator)

**What:** Confirms the Kid dispatch: pre-cleanup timing is mandatory so the blog draft exists before teardown. Draft-only mode for this run (no direct publish). Rolling blog repo (`azure-networking-blog`) is the standing default publication target for all future labs unless Jose overrides per-lab.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/copilot-directive-20260529T141813.md`

---

### 2026-05-29T14:18+02:00: User directive — Kid's scenario veto authority extended to pre-lab selection

**By:** Jose (via Copilot Coordinator)

**What:** Kid's veto authority extended to the pre-lab *selection* phase, not only post-build revision. Kid may reject or reshape a scenario before Tank deploys if the lab doesn't lend itself to a compelling public post.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/copilot-directive-20260529-1458-blog-scenario-veto.md`

---

### 2026-05-29T14:58+02:00: User directive — blog posts must show actual command output

**By:** Jose (via Copilot Coordinator)

**What:** Standing rule for all future blog posts: every command shown must be accompanied by its actual output (table or `tsv` format) plus an interpretation paragraph. Showing command names without output is not acceptable. Kid and Niobe are jointly responsible for meeting this standard before publication.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/copilot-directive-20260529-1458-blog-command-output.md`

---

### 2026-05-29T14:30+02:00: Kid cast as 8th permanent squad member (blog-writer 📝)

**By:** Coordinator

**What:** The Kid (📝, blog-writer, claude-sonnet-4.6) cast as 8th permanent squad member. Role: convert lab learnings into engaging public posts under `github.com/erjosito`. Seven governance files touched: `registry.json`, `team.md`, `routing.md`, `ceremonies.md`, Kid's `charter.md`, Kid's `history.md`, Kid's routing entry. Squad version bumped v0.9.4 → v0.9.5.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/2026-05-29-kid-casting.md`

---

### 2026-05-29T14:35+02:00: Kid editorial decision — headline for lab #1 blog draft

**By:** The Kid

**What:** After evaluating seven candidate headlines, Kid selected: *"Three commands that lied on a working ExpressRoute lab."* No back-request to Tank or Niobe (cost $110–$125/day not justified; control-plane evidence sufficient). Three deliverables produced: `blog-draft/README.md`, `blog-draft/references.md`, `blog-draft/DRAFT-NOTES.md`.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/kid-20260529-expressroute-megaport-bgp.md`

---

### 2026-05-29T15:00+02:00: Kid v2 blog angle — Option A (rescue with honest framing)

**By:** The Kid

**What:** After v1 draft rejection (multiple factual errors from memory), Kid selected Option A: rescue v1 with honest, anomaly-first framing. New headline: *"The route table that didn't lie: diagnosing ExpressRoute BGP with the Azure CLI."* V1 preserved as `README.v1.md`. V2 sourced entirely from all 30 show-output files before any prose was written.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/kid-blog-v2-angle.md`

---

### 2026-05-29T15:30+02:00: Lab #1 blog post published

**By:** The Kid / Jose

**What:** Lab #1 blog post published at `https://github.com/erjosito/azure-networking-blog/tree/main/2026-05-expressroute-megaport-bgp`. Commit SHA: `21e4f1ba`. Word count: 2,249. Sanitization: zero forbidden GUIDs or credentials. Back-requests: none.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/2026-05-29-kid-blog-published.md`

---

### 2026-05-29T15:35+02:00: Standing rule — blog link in every lab README

**By:** Coordinator / Jose

**What:** Every `labs/<lab>/README.md` must include a blog post link immediately after the H1. Placeholder: `<!-- Blog post: TBD -->` until published; replaced with live URL on publication. Rule applied retroactively to lab #1 (Niobe executed the back-fill).

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/2026-05-29-blog-link-in-lab-readme.md`

---

### 2026-05-29T15:36+02:00: Niobe — lab #1 README blog-link back-fill

**By:** Niobe

**What:** Niobe replaced the placeholder comment (line 3) in `labs/expressroute-megaport-bgp/README.md` with the live blog post URL (*"The route table that didn't lie…"*). Scope: one-line README edit only. Sanitization: no forbidden GUIDs introduced.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/2026-05-29-niobe-lab1-readme-backfill.md`

---

### 2026-05-29T15:40+02:00: Pre-Gate Editorial Review ceremony added (routing rule #17)

**By:** Coordinator / Jose

**What:** New optional ceremony: Kid reviews blog post content with Morpheus (≤300 words) before a lab is marked "shipped externally." Morpheus holds gate authority to pause publication if the post misrepresents findings. Ceremony is optional per lab (waivable for time-sensitive situations). Codified as Routing Rule #17.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/2026-05-29-kid-pre-gate-review.md`

---

### 2026-05-29T15:45+02:00: Layout — Kid's blog repo is a sibling repo, not nested

**By:** Coordinator / Jose

**What:** Kid's blog repo (`azure-networking-blog`) is cloned as a sibling to `net-lab-builder` under the shared `Repos/` folder — NOT nested inside `net-lab-builder`. The `labs/<lab>/blog-draft/` folder inside `net-lab-builder` is a work-in-progress scratchpad only; it is not the canonical blog source.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/2026-05-29-blog-repo-local-layout.md`

---

### 2026-05-29T16:00+02:00: Tank cleanup — lab #1 complete (19/19 resources); two charter amendments

**By:** Tank / Coordinator

**What:** Lab #1 (`expressroute-megaport-bgp`) cleanup completed: 19/19 resources deleted in charter-compliant 6-step order. Root cause of cleanup difficulty: Windows HKCU environment variables are not inherited by Terraform child processes. Workaround: Megaport credentials passed as inline HCL variables. Two charter amendments triggered: (1) env-rehydrate pattern as mandatory Step 0 in all Windows deploy/cleanup scripts; (2) canonical Terraform `.gitignore` lives at repo root — no per-module `.gitignore` files needed for new labs.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/2026-05-29-tank-cleanup-lab1.md`

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
