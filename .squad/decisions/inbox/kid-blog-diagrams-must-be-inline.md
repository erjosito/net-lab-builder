---
type: team-decision
agent: Kid (Blog Writer & Public Storyteller)
date: 2026-08-19
status: active
audience: all-agents
---

# Blog Diagrams Must Be Verified Inline in the Rendered Post

## Decision

**Blog diagrams must appear inline in the published README — not merely as separate asset files in the repository.**

## Background

The dual-hub-vnra-udr-transit post (PR #3) was shipped with four Mermaid diagram files
correctly placed under `dual-hub-vnra-udr-transit/assets/` and a footer note referencing
them. The README itself contained no Mermaid fenced blocks. When the post published to main,
readers saw zero diagrams because GitHub does not support Markdown transclusion or includes
of any kind (no `!include`, no `[!include]`, no `{! file.md }`).

The post was flagged by the user as unreadable and unengaging.

## Required Practice (effective immediately)

1. **Embed all diagrams inline.** Every Mermaid diagram that adds explanatory value must
   appear as a fenced code block (`\\\mermaid ... \\\`) directly in the post README.
   Oracle-authored asset files under `assets/` serve as source/archive; the post author
   (Kid) must copy the validated Mermaid source into the README before opening the PR.

2. **Verify rendered output on main.** After merge, open the GitHub web view of the README
   on main and confirm each diagram renders visually (not just that fences exist in source).
   This is a post-merge gate, not just a pre-merge check.

3. **No diagram isolation.** Do not place Mermaid fences inside HTML comments (`<!-- -->`)
   or collapsed `<details>` blocks unless explicitly requested. Hidden diagrams are
   equivalent to absent diagrams.

4. **Each diagram needs a brief introduction.** One sentence before the diagram block
   contextualizes what the reader is about to see. Do not dump diagrams without framing.

5. **Oracle handoff must include embeddable source.** When Oracle delivers diagrams,
   they must be in a form (Mermaid fenced block or GitHub-supported image) that Kid can
   paste directly into README. PNG images require a hosted URL or repo-relative path.
   Mermaid source is preferred for maintenance.

## Impact on Workflow

| Agent | Change |
|-------|--------|
| Kid | Embed fenced blocks before PR; verify rendering on main post-merge |
| Oracle | Deliver Mermaid source as copyable fenced blocks, not just standalone .md files |
| Squad | Pre-publication review checklist must include "README contains at least one visible diagram" |

## Incident Reference

- Post: `dual-hub-vnra-udr-transit/README.md`
- Original PR (no inline diagrams): #3
- Fix PR: https://github.com/erjosito/azure-networking-blog/pull/5
- Fix merge commit: `b89d88097ee40abe070e2182de404fe046c62bfa`

---

**Recorded by:** Kid
**Timestamp:** 2026-08-19T20:51:00+02:00