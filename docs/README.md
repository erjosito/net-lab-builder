# `docs/` — cross-lab knowledge base

This folder is the **cross-lab knowledge base** for `net-lab-builder`. Anything that's true across labs (CLI commands, debugging patterns, gotchas, runbooks, glossaries) lives here, not in `labs/<one-lab>/`.

**Who reads it:**

- **Humans** — you're at a console, you want a known-good command, you don't want to grep a 50 KB `design.md` for it
- **Niobe** — at every validation pass, she reads the pages relevant to the lab's network layers before running captures (so she uses the canonical commands and avoids the documented gotchas)
- **Trinity, Tank, Oracle** — read on demand when the topic intersects their work

**Who writes to it:**

- **Niobe (primary)** — appends every novel gotcha she discovers during validation. Charter mandates this; see her "KB contribution" section.
- **Trinity (occasional)** — adds CLI tricks she discovers when prototyping designs. Cross-cutting design patterns also go to her Obsidian vault (private); the *commands* go here (public).
- **Jose (manual)** — drops in references he wants the squad to consult.

**Who DOESN'T write to it:** Tank, Oracle, Kid. Tank writes IaC and code comments; Oracle writes diagrams; Kid writes blog drafts. None of them should append KB entries.

## Index

| File | Topic | Last updated |
|---|---|---|
| [`troubleshooting-commands-linux.md`](./troubleshooting-commands-linux.md) | Network troubleshooting commands across Azure, Megaport, GCP, Linux NVAs. Focus: jq-piped table output. | 2026-06-15 |
| [`troubleshooting-commands-windows.md`](./troubleshooting-commands-windows.md) | PowerShell-native companion for Windows labs. HTTP APIs, JSON parsing, Windows VM diagnostics, PS functions. | 2026-06-15 |

## Contribution rules

1. **Cross-lab only.** If a command, gotcha, or pattern is only useful in one lab, put it in `labs/<lab>/lessons-learned.md` not here.
2. **Append, don't rewrite.** When you find a new gotcha, append it under the relevant existing section. Don't restructure other authors' content.
3. **Always cite the gotcha source.** A real lab where it bit you (`labs/vwan-dual-er-symmetric/`), a vendor issue URL, or a date you confirmed it (e.g., "Confirmed 2026-06-15 — Megaport API v2"). Undated lore rots fast.
4. **One command per row, table format.** Prose-form references get skimmed past; a table forces conciseness and is searchable.
5. **Commands must be testable as-written.** Use the documented env-var conventions. A reader should be able to set the env vars and copy/paste verbatim.
6. **No secrets, no subscription IDs, no API tokens.** Replace with `<SUBSCRIPTION_ID>`, `$MP_TOKEN`, etc.
7. **Bump the `Last updated` column in the index above** whenever you modify a page.

## Why not put this in `.squad/skills/` or `.copilot/skills/`?

- `.squad/skills/` are **agent skill packages** — pattern-shaped, with a SKILL.md format optimised for agent consumption. Niobe could consume from there, but a human reading it directly is awkward (skills assume the agent context).
- `.copilot/skills/` is **process knowledge** for the coordinator — when to dispatch, how to handle handoffs. Not network reference material.
- `docs/` is **human-first reference material** that agents happen to also read. Different audience, different format.

Skills and `docs/` can cross-link. The `azure-lab` skill's `collect_routes` action should reference `docs/troubleshooting-commands-linux.md` instead of duplicating commands.
