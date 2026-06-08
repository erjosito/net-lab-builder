# Squad Decisions

> Authoritative log of squad governance decisions and mechanisms. Each entry records the trigger, decision, mechanism, and affected files.

---

## 2026-06-08 — Kid weekly blog-topic scout enrollment

**Trigger:** Jose directive (2026-06-08) requested autonomous weekly scouting for under-documented Azure Networking topics to build a pipeline of pre-vetted lab ideas between deployments.

**Decision:** Enroll Kid's weekly topic scout as a permanent background ceremony (schedule ID #1). The scout runs every 7 days (managed via 7-day debounce marker at `~/.copilot/session-state/kid-last-scout.txt` with a daily manage_schedule trigger to enforce weekly cadence), surfaces 3–5 candidate Azure Networking topics filtered against Jose's quality bar (no documentation regurgitation, no "works as designed" verifications — only troubleshooting, corner-cases, or depth gaps), and delivers a digest to Jose's Teams "Notes to Self" (primary channel, no hardcoded UPNs to preserve credential hygiene) with email fallback.

**Why this call:** Lab #1 retrospective showed Kid's biggest contribution to a lab's worth is rigorous topic selection at the phase-1 gate (the Pre-Gate Editorial Review caught a single-source evidence gap that almost shipped a thin post). Shifting topic selection earlier — to topic *discovery* itself — costs one Kid dispatch per week and avoids the much costlier "wrong lab" failure mode downstream. The weekly scout enables Jose to make smarter lab-pick decisions by surfacing candidate topics proactively rather than cold-starting each time.

**Mechanism:**
- Scout fires via `manage_schedule` with `interval: "1d"` (the tool's hard maximum) every day.
- Before each dispatch, Kid checks for a marker file at `~/.copilot/session-state/kid-last-scout.txt` containing the date of the last successful scout run.
- If the marker is older than 7 days (or missing), scout proceeds; otherwise it returns a no-op.
- Scout searches 7 canonical sources: Microsoft Learn Azure Networking (recent features, preview docs, limitations sections), MicrosoftDocs/azure-docs issues (user-flagged depth gaps), Azure updates RSS, Microsoft Tech Community, Stack Overflow (high-vote unanswered questions), respected MVP blogs (Daniel Mauser, Holger Mester, Adam Stuart, Aidan Finn), and GitHub issues on Azure-related repos (cli, bicep, terraform-provider-azurerm).
- Scout produces a digest of 3–5 candidates (each ≤200 words, formatted with Title, Why it matters, What's missing, Proposed lab angle, Scout source(s)).
- Digest lands in Jose's Teams "Notes to Self" via `agent365-teamsserver-SendMessageToSelf` (primary); on Teams failure, resolves Jose's UPN at runtime via `agent365-meserver-GetMyDetails` and sends via email (fallback).
- After successful dispatch, writes current date to marker file for 7-day debounce.

**Quality bar (mandatory pre-send checklist):**
1. NOT documentation regurgitation — if MS Learn or three community posts already cover it well, it's rejected.
2. NOT "works as designed" verification — labs whose only conclusion is "yes, this Azure feature does what the docs say" produce thin posts; rejected.
3. YES added value via at least one of: troubleshooting workflow (diagnostic path when X breaks), corner-case behavior (edge case not in docs), surprising interaction (unexpected feature interplay), depth gap (mechanism the docs hand-wave).

**Jose response routes:**
- Numeric pick (e.g., "1" or "2, 4"): trigger coordinator → file `.squad/decisions/inbox/<YYYY-MM-DD>-blog-topic-<slug>.md` with picked candidate(s) verbatim → Morpheus designs next lab per standard Phase 1–3.
- "skip": no action; scout continues on 7-day cycle.
- No reply within 7 days: treated as "skip"; scout continues.

**Channels:**
- Primary: Jose's Teams "Notes to Self" (visible to Jose only, no UPN hard-coded).
- Fallback: Resolved UPN via `agent365-meserver-GetMyDetails` → email via `agent365-mail-SendEmailWithAttachments`.
- Forbidden: Hard-coded UPN, alias, or email address anywhere in repo (sanitization breach risk on public repo).

**Files touched:**
- `.squad/agents/kid/charter.md` — added "Weekly Topic Scout (scheduled, between-labs mode)" section documenting the ceremony.
- `.squad/ceremonies.md` — added "Weekly Blog-Topic Scout" ceremony entry with trigger, cadence, facilitator, participants, quality bar, and notification channel.
- `.squad/routing.md` — Rule #18 (Scout output handling): Jose's numeric picks route to coordinator → blog-topic inbox filing → Morpheus lab design dispatch.
- `.squad/team.md` — Kid member note extended with scout responsibility and schedule ID #1.
- `.squad/agents/kid/history.md` — Kid's audit entry logging scout enrollment (2026-06-08).

**Schedule registration:** `manage_schedule` call on 2026-06-08 returned schedule ID #1. This ID is the canonical reference for the ceremony in all squad systems.

**Sanitization result:** Pre-merge validation confirmed zero hits on credential/GUID patterns across inbox directive, charter, ceremonies, routing, team, and decision entry. Post-merge grep confirms 5 source files remain clean; this entry and project-journal entry reference patterns only in redacted form.

---
