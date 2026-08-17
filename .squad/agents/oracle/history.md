**Archived entries:** see \history-archive.md\

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


📌 2026-08-05T13:43:07.691+02:00 — Scribe merge pass: US10 wording-fix brief recorded in decisions.md; no lab/design file staging occurred.

---


📌 2026-08-05T11:10:29+02:00 — **Inline Mermaid diagrams for US01–US12 (route-map user stories)**

- **Trigger:** Jose Moreno via Niobe — "Adding mermaid diagrams to the user stories would improve
  readability." Niobe had approved US01–US12 and explicitly authorised inline Mermaid authoring.
- **Artifact:** `labs/dual-hub-hubless-region-ars/route-map-user-stories.md` (v5.1, owner Morpheus).
  Sole file changed. No Azure, IaC, README, manifest or live-resource change. No git commit.
- **Delivered:** 19 fenced ```mermaid blocks covering all 17 stable diagram IDs in the §3 index.
  Every story US01–US12 has at least one rendered diagram. Coverage: US01–US09 one block each;
  US10 three (generic normal + generic F1/F4 failure under one anchor, plus the VPN lab analogue);
  US11 three (native peering / direct workloads / static NVA transit); US12 four (normal, two
  failover figures under one anchor, plus the VPN-square lab analogue).
- **Placement:** each block sits immediately after its story's generic reference topology and before
  the detailed mechanism analysis, per the task. Lab-analogue blocks sit at the head of their own
  "current lab" subsection.
- **Per-block furniture:** `<a id="...">` anchor using the index's stable ID, a bold figure caption,
  one concise *What to look for* sentence, and a `%% diagram-id:` comment inside the fence so the ID
  survives copy/paste out of the markdown.
- **Visual grammar (uniform across all 19):** `-->` native connectivity / ordinary forwarding,
  `-.->` control-plane adjacency (BGP) and labelled conditional/backup paths, `==>` primary active
  data path, `-.-` dotted un-arrowed attachment for policy and annotation nodes (never a forwarding
  hop). Azure Route Server appears only on dashed control-plane and dotted policy edges — verified
  mechanically: zero `ars*` node occurrences on any `==>` or `-->` edge across all blocks.
  Shared `classDef` palette: `azure`, `onprem`, `nva`, `policy`, `blocked`, `note`.
- **Overlay terminology (§0.1) honoured:** global VNet peering drawn as underlay/native
  connectivity; NVA-to-NVA BGP drawn as a control-plane adjacency, never as encapsulation;
  GRE/IPsec/VXLAN drawn only where the story requires encapsulation, on a separate labelled edge.
- **Story-specific constraints honoured:** US01 default non-overlay path with the overlay as a greyed
  conditional variant; US06 keeps the desired per-peering attachment *and* the explicit missing-Azure-
  attachment boundary so it does not read as supported; US10 uses both approved IDs, shows no
  association as proven, keeps Route Server off every data hop, and excludes `0.0.0.0/0` and set-C
  from the overlay import/export; US11 uses all three retained IDs and does not imply hub peering
  propagates spoke prefixes; US12 uses `flowchart TB` with four quadrant subgraphs, explicit
  S-A/S-B/S-C/S-D side labels, diagonals present only as a `NOT PRESENT — by design` annotation node
  (no diagonal edges drawn), B2 marked hub-address-space-only under variant N, the failure figure
  showing three surviving sides and stating that full outcome C needs dynamic prefix carriage and
  withdrawal, and Global Reach confined to S-D/B1.
- **Two approved specs required splitting into two fences under a single anchor**, to stay readable
  and near the ~15-node budget without shrinking labels: `US10-bow-tie-generic-er` (normal / failure)
  and `US12-square-hybrid-failover` (S-A lost / S-D lost). Both splits are sanctioned by the specs'
  own "normal + failure inset" and "a second, smaller figure" language, and both preserve the
  one-anchor-per-index-ID invariant. `US12-square-hybrid-normal` is a deliberate 16-node exception:
  splitting the square would destroy the figure's core assertion.
- **Grammar reconciliation recorded:** the US12 spec text says "BGP control plane = `-->`, tunnel =
  `-.->`", which inverts this task's global grammar. I followed the **task's** grammar for
  cross-diagram consistency and stated the mapping explicitly in the US12 `Legend` subgraph. The
  load-bearing US12 constraint (no Route Server on a thick edge) is preserved either way.
- **Validation:** every distinct block extracted and rendered with the already-installed
  `@mermaid-js/mermaid-cli` from the local npx cache (no new tooling installed; the validator was
  first proven meaningful by confirming it exits 1 on deliberately broken syntax). Result **19/19
  PASS**, re-run after the table/index edits — still 19/19. Mechanical checks: 19 open fences / 19
  close fences / 0 unterminated; 17 anchors, exactly one per index ID; every US01–US12 has >= 1
  block; heading count and the 12 story headings unchanged; US06's blocked framing, the
  scenario-retention policy and the retained US10 scenarios all still present.
- **Index/table updates (task items 10):** front summary table `Diagram IDs` cells converted from
  plain code spans to anchor links; §3 diagram index IDs linked to their anchors and a new `Status`
  column added reading **Embedded and validated** with the block count. No other table field touched.
- **Not touched:** architecture, feasibility claims, applicability classifications, story intent,
  validation plans, current-lab deltas, costs, citations, Azure/IaC, README, manifest, live
  resources. No git commit.
- Decision recorded at `.squad/decisions/inbox/oracle-user-story-mermaid.md`.
## 2026-08-05 — Storage endpoint path-equivalence diagram draft

- Created `labs/storage-endpoint-path-equivalence/diagrams/01-topology.drawio`.
- Created `labs/storage-endpoint-path-equivalence/diagrams/02-experiment-comparison.drawio`.
- Created `labs/storage-endpoint-path-equivalence/diagrams/03-performance-methodology.mmd`.
- Used official Azure/draw.io icons with native proportions fitted into uniform 64×64 visual footprints.
- Kept customer-observable facts separate from a deliberately unconnected, opaque Microsoft-underlay band; no physical-route equivalence is implied.
- Live-value placeholders remain for run suffix, target account, VM private IP, NAT public IP, and per-run public Storage IP.

## 2026-08-08 — Translator endpoint diagram replacement finalized

- Replaced the superseded Storage visuals under `labs/storage-endpoint-path-equivalence/diagrams/` with the deployed Azure AI Translator F0 design in Sweden Central.
- Final set covers the switchable topology, all three access modes and customer-observable route differences, the F0-safe performance method, headline measurements, the overall inconclusive verdict, and the 25 ms positive-control PASS (23.29 ms; 95% CI 22.08–24.48 ms).
- Used verified official Azure VM, VNet, NAT Gateway, Private Endpoint, Private DNS, and Translator icons. Icons retain native aspect ratios within uniform 64 px footprints.
- Exported public PNGs with the installed draw.io desktop CLI and cached Mermaid CLI. Both draw.io files parse as XML; both Mermaid sources render successfully.
- Removed Storage/blob/service-endpoint placeholders and sensitive live names/public addresses. Retained only documented private topology addresses needed to explain the deployed paths.
- Decision handoff: `.squad/decisions/inbox/oracle-translator-diagram-replacement.md`.

