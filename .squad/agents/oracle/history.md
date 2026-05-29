# 🔮 Oracle — Session History

> Append-only log. Newest entries at the bottom. Coordinator may also append summary entries.

## 2026-05-29 — Joining the squad

- **Cast** by Squad Coordinator in response to Jose flagging that lab #1 documentation has zero diagrams.
- **Role allocation:** Documentation & Diagrams. Persistent name `Oracle` (Matrix universe — fits the "sees patterns and explains them" archetype).
- **Charter:** see `charter.md` in this folder. Owns `labs/<lab>/diagrams/` end-to-end and the diagram-embed sections of `labs/<lab>/README.md`.
- **Tooling:** `drawio-create_diagram` MCP (render mermaid + drawio), `drawio-search_shapes` MCP (find industry stencil style strings).
- **Default model:** `claude-sonnet-4.6`.

### First task

Retrofit diagrams into the already-built lab `labs/expressroute-megaport-bgp/` (Tank deployed, Niobe validated; missing diagrams across README / validation / lessons-learned). Standard ER + Megaport catalogue:

| # | File | Format | Status |
|---|---|---|---|
| 01 | `topology.drawio` | drawio (Azure + Megaport stencils) | ✅ prose + source link |
| 02 | `bgp-control-plane.mmd` | mermaid `flowchart LR` | ✅ inline mermaid |
| 03 | `route-propagation.mmd` | mermaid `sequenceDiagram` | ✅ inline mermaid |
| 04 | `cleanup-chain.mmd` | mermaid `flowchart TD` | ✅ inline mermaid |

### Inline mermaid retrofit — 2026-05-29 (Jose's choice)

Jose chose to embed mermaid source directly in `README.md` (GitHub renders natively) rather than generating PNGs. All four broken `![...](diagrams/0N-name.png)` references replaced: diagram 1 → prose + drawio source link; diagrams 2–4 → verbatim inline ` ```mermaid ``` ` fenced blocks copied from the `.mmd` source files. Sanitization check passed (no forbidden GUIDs). All three mermaid blocks validated via `drawio-create_diagram`.

### Charter changes applied to other agents on my arrival

- **Morpheus charter** — added Oracle to "Hand off in parallel" + "Collaboration" section. Manifest now expected to spec the diagram set.
- **Niobe charter** — explicitly reassigned `labs/<lab>/diagrams/` ownership to Oracle in her output-layout section. Niobe still owns show-output (my source of truth for diagram labels).
- **`team.md`** — added row.
- **`routing.md`** — added "Lab documentation & diagrams" → Oracle row + new rule #14 (Diagram-first). Added `squad:oracle` issue label.
- **`casting/registry.json`** — added `docs-diagrams` slot mapping to persistent name `Oracle`.
