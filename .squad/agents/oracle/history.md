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

## 2026-06-15 — Lab #2 diagram set: `vwan-dual-er-symmetric`

### Task

Produce the standard 4-diagram set for lab #2 (`vwan-dual-er-symmetric`) ahead of deploy. Morpheus's topology spec: dual-region vWAN, two secured vHubs (ASN 65520, Azure Firewall + routing-intent private), dual MCRs (one per region), dual ER circuits, GCP VPC as simulated on-prem. Symmetry mechanism: per-region prefix affinity at MCRs (Trinity designing).

### Files produced

| # | File | Format | Status |
|---|---|---|---|
| 01 | `labs/vwan-dual-er-symmetric/diagrams/01-topology.drawio` | drawio XML nested swimlanes | ✅ validated via `drawio-mcp-open_drawio_xml` |
| 02 | `labs/vwan-dual-er-symmetric/diagrams/02-bgp-control-plane.mmd` | mermaid `flowchart LR` | ✅ validated via `drawio-mcp-open_drawio_mermaid` |
| 03 | `labs/vwan-dual-er-symmetric/diagrams/03-data-plane-symmetric.mmd` | mermaid `flowchart LR` with 3 subgraphs | ✅ validated |
| 04 | `labs/vwan-dual-er-symmetric/diagrams/04-cleanup-chain.mmd` | mermaid `flowchart TD` | ✅ validated |
| — | `labs/vwan-dual-er-symmetric/README.md` | Markdown with `## Diagrams` section | ✅ created |

### Stencil findings

- **`drawio-search_shapes` not available** in this session's MCP toolkit. Only `drawio-mcp-open_drawio_xml`, `drawio-mcp-open_drawio_mermaid`, and `drawio-mcp-open_drawio_csv` are present. Per charter, fell back to labeled rectangles for any vendor without a confirmed stencil.
- **Azure icons used (same paths as lab #1 precedent):**
  - `img/lib/azure2/networking/Virtual_Network_Gateways.svg` — ER Gateway ✅ (confirmed lab #1)
  - `img/lib/azure2/networking/ExpressRoute_Circuits.svg` — ER Circuit ✅ (confirmed lab #1)
  - `img/lib/azure2/networking/Virtual_Networks.svg` — Spoke VNets (assumed; not confirmed via search_shapes)
  - `img/lib/azure2/networking/Azure_Firewalls.svg` — Azure Firewall (assumed; not confirmed via search_shapes)
- **Megaport MCR:** labeled orange rounded rectangle (`fillColor=#ffe6cc;strokeColor=#d6b656`). No Megaport mxGraph stencil available — same approach as lab #1.
- **GCP VPC:** labeled green rounded rectangle (`fillColor=#e8f5e9;strokeColor=#34a853`). No GCP mxGraph stencil confirmed.
- **vWAN / vHub:** swimlane containers with Azure blue colors. No dedicated vWAN/vHub icon used (swimlane conveys the grouping; good enough at this stage).

### Rendering notes

- All 4 draw.io/mermaid URLs opened successfully — no parse errors detected.
- Nested swimlane containers (vWAN > Region A/B > Hub A/B) render correctly. All cross-container edges declared at `parent="1"`.
- Subgraph approach in diagram 03 (three `subgraph` blocks in one flowchart) validated cleanly in draw.io mermaid renderer.
- PNG render of topology not produced (no PNG export MCP command available). README references `.drawio` source with `[Open in draw.io]` link per charter rule §5.

### TODO labels requiring Trinity/Niobe post-deploy refresh

- MCR1/MCR2 ASNs (65001/65002 TBD) — Trinity to confirm from Megaport BGP config
- GCP ASN (65003 TBD) — Trinity to confirm
- Spoke address spaces (10.1.x.x/TBD, 10.2.x.x/TBD) — Morpheus to lock CIDRs
- vHub address prefixes (/23 TBD) — Morpheus/Trinity
- ER peering location names — Tank to capture post-deploy
- GCP-advertised prefixes (10.100.x.x/TBD) — Morpheus to lock

---

📌 Team update (2026-06-15): Phase 1 manifest design fan-out complete on 2026-06-15; Jose gate pending.
