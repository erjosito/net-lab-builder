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

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
