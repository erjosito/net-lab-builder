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

📌 2026-06-15T20:14 — Correction (apply to all future vWAN diagrams)
- vHub external BGP ASN is **65515** (used by ER GW for MSEE peering, VPN GW peering, Route Server peering — same in every hub, vWAN-reserved, non-configurable).
- **65520** is NOT a peering ASN — it is the AS-path marker vWAN PREPENDS onto routes when they are propagated *across* hubs (inter-hub propagation marker).
- Lab #2 diagrams I sketched in the Phase-1 prep referenced ASN 65520 as the hub's BGP ASN; this was wrong. Origin: Jose correction 2026-06-15T20:14.
- Repo memory `azure vwan ASNs` records the canonical distinction.

## 2026-06-15 — Lab #3 diagram set: `msee-hairpin-hns-vwan-ipv6`

### Task

Produce the standard 4-diagram set for lab #3 (`msee-hairpin-hns-vwan-ipv6`) ahead of deploy. Morpheus's lab card: self-managed hub-and-spoke ER gateway + Virtual WAN hub ER gateway, both peering at the same Stockholm MSEE. Dual-stack IPv4+IPv6 BGP. No on-prem router, no Megaport, no GCP. Goal: demonstrate MSEE hairpin mechanism over ER Direct port (10 Gbps, two sub-allocated circuits).

### Files produced

| # | File | Format | Status |
|---|---|---|---|
| 01 | `labs/msee-hairpin-hns-vwan-ipv6/diagrams/01-topology.mmd` | mermaid `flowchart LR` | ✅ created |
| 02 | `labs/msee-hairpin-hns-vwan-ipv6/diagrams/02-bgp-control-plane.mmd` | mermaid `flowchart LR` | ✅ created |
| 03 | `labs/msee-hairpin-hns-vwan-ipv6/diagrams/03-data-plane.mmd` | mermaid `flowchart LR` with 2 subgraphs | ✅ created |
| 04 | `labs/msee-hairpin-hns-vwan-ipv6/diagrams/04-cleanup-chain.mmd` | mermaid `flowchart TD` | ✅ created |
| — | `labs/msee-hairpin-hns-vwan-ipv6/README.md` | Markdown with `## Diagrams` section | ✅ created |

### Key findings — MSEE hairpin visual pattern

1. **Hairpin topology at control plane:** Two eBGP sessions (HnS GW ↔ MSEE, vWAN GW ↔ MSEE) sharing the same MSEE node. Diagram shows dual-direction arrows (→ and ←) on each session, each annotated with the advertised prefixes.
   - HnS ER GW advertises 10.1.x.x + 10.2.x.x, learns 10.3.x.x + 10.4.x.x from MSEE.
   - vWAN ER GW advertises 10.3.x.x + 10.4.x.x, learns 10.1.x.x + 10.2.x.x from MSEE.
   - MSEE is the bridge — same ASN (12076) on both sessions; no VXC configuration; Azure-side BGP sessions only.

2. **IPv6 ULA dual-stack convention:** Dual-stack ER requires separate BGP sessions per address family.
   - IPv4 peering subnets: 172.16.1.0/30 (Circuit 1), 172.16.2.0/30 (Circuit 2).
   - IPv6 peering subnets: fd00:f:1::/126 (Circuit 1), fd00:f:2::/126 (Circuit 2).
   - Both routes advertised on each session (separate address family = separate learned route entries). Diagram labels each session with both address families' peer IPs.

3. **Data plane — dual subgraph encoding:** S1 (IPv4 ping) and S2 (IPv6 ping) share the same topological path but operate independently at the socket/probe level. Encoding as two adjacent `subgraph` blocks in mermaid preserves the "parallel scenarios" narrative without duplicating the path logic.

4. **Cleanup order — ER Direct port timing:** Unlike lab #2 (Megaport, where MCR deletes are bottlenecks), lab #3 bottleneck is the ER Direct port deprovisioning time (~1 hour post-circuit-deletion at provider). Capture that in the cleanup diagram as a separate step with a note on the time SLA.

### TODO labels requiring Tank/Niobe post-deploy refresh

- ER Direct Port resource ID and confirmation of Stockholm region allocation
- Peer IPs on Circuit 1 and Circuit 2 (172.16.1.x, fd00:f:1::x primary/secondary; 172.16.2.x, fd00:f:2::x primary/secondary)
- VM IP addresses in each spoke (10.2.0.x, 10.4.0.x for IPv4; fd00:2::x, fd00:4::x for IPv6)
- MSEE peering location name confirmation (Stockholm)

---

## 2026-08-03 — Lab #4 diagram set: `dual-hub-hubless-region-ars`

### Task

Produce the standard 4-diagram set for lab #4 (`dual-hub-hubless-region-ars`) ahead of deploy. Morpheus's locked manifest: workload-aligned ARS VNet in a hubless Poland Central region acting as shared BGP control-plane extension for Set-C spokes toward two remote hubs (swedencentral = hub1, switzerlandnorth = hub2). On-prem simulated in norwayeast via VPN V2V connections. Three mandatory policy deltas (Δ1 loop-strip, Δ2 AS-path prepend, Δ3 ARS inbound route-map PREVIEW).

### Files produced

| # | File | Format | Status |
|---|---|---|---|
| 01 | `labs/dual-hub-hubless-region-ars/diagrams/01-topology.excalidraw` | Excalidraw JSON v2 · 59 elements | ✅ JSON valid, all IDs unique, all text elements have width+height |
| 02 | `labs/dual-hub-hubless-region-ars/diagrams/02-bgp-control-plane.mmd` | Mermaid `flowchart TD` | ✅ validated via `drawio-mcp-open_drawio_mermaid` |
| 03 | `labs/dual-hub-hubless-region-ars/diagrams/03-steady-failover-failback.mmd` | Mermaid `flowchart TD` with 3 subgraphs (S1/S2/S3) | ✅ validated |
| 04 | `labs/dual-hub-hubless-region-ars/diagrams/04-cleanup-chain.mmd` | Mermaid `flowchart TD` | ✅ validated |

### Layout decisions

- **Excalidraw topology (01):** 4-region column layout (hub1 left, Poland center, hub2 right, Set-C+Norway below Poland). Microsoft/Fluent colors: hub1=#0078D4/CFE4FA, hub2=#5C2D91/E8DAEF, Poland=#107C10/DFF6DD, Norway=#F7630C/FFF4CE. Orange policy-split box (Δ1/Δ2/Δ3) embedded inside Poland container. V2V arrows (strokeWidth=2) from each hub's VPN GW to on-prem. Dashed arrows for BGP sessions; solid arrows for data-plane peerings. 59 elements total.
- **BGP control-plane (02):** Hub-subgraph grouping makes AS 65515 coexistence between ARS and VPN GW explicit. Policy split node inside Poland subgraph. All 10 BGP sessions shown.
- **Steady/failover/failback (03):** Three scenario subgraphs (S1 steady / S2 hub1 outage / S3 recovery) linked by "fault injection" and "recovery" edges. Fault injection and Restore boxes shown with red/green styling respectively.
- **Cleanup (04):** Single `az group delete` as root node capturing all 30+ tagged resources. KV delete + purge as two parallel post-delete steps. Notes box for V2V (no LNG) and SSH pubkey preservation.

### Technical notes

- First lab to use Excalidraw format (v2, source=`claude`) per instruction. Previous labs used draw.io XML for topology.
- Non-ASCII chars (Δ, ·, →, ×) used in `.mmd` files — valid in modern Mermaid renderers. ASCII equivalents used in the draw.io validator call (which was used for syntax-checking only).
- `direction LR` inside subgraphs of a `flowchart TD` outer diagram works cleanly in draw.io Mermaid renderer.
- No live IPs used; all addresses from manifest CIDRs (/27 subnets, /24 spokes, /16 hubs). PSK names referenced without values.
- Set-C spokes triple-peered (Poland ARS + hub1 + hub2 no-transit) captured as a text annotation inside the Set-C leaf node rather than as three separate arrows, to keep the diagram under the arrow-density threshold.

---

## Learnings

- **MSEE hairpin visual pattern:** Shared MSEE node with dual eBGP sessions (one per circuit, same ASN). Data flows through MSEE as a Layer 3 reflection — packet traverses Circuit 1 tunnel → MSEE routes via BGP → Circuit 2 tunnel. Diagram representation: MSEE as a single node with four edges (in + out per circuit), labeled with ASN + advertised prefixes.
- **IPv6 ER peering conventions:** Dual-stack requires separate address families on the same eBGP session. Diagrams label each session with both family notations (e.g., "IPv4: 172.16.1.0/30 / IPv6: fd00:f:1::/126"). ULA is a valid choice for pure Azure-to-Azure labs when global routing is not required.
- **Data-plane multi-scenario encoding in mermaid:** Subgraphs allow parallel scenarios (S1 IPv4 / S2 IPv6) to coexist in one diagram without textual duplication. Keeps the diagram readable and emphasizes that the path topology is identical; only the address families differ.
- **Route-map catalogues should be explicit and repeatable:** When documenting preview routing features, include purpose, attachment point/direction, classification, prerequisite change, expected route effect, safe test outline, evidence, rollback, and operational risk for each numbered scenario. That structure made the Poland route-map note much easier to refine without losing the operational constraints.
- **Route-map attachment locality matters:** For this lab, `ars-poland` can only reference route maps from peers inside the ARS VNet, so remote NVA peers remain blocked regardless of how carefully the rule is written. This is a useful first-check for future ARS route-map docs and prevents misclassifying a topology issue as a policy issue.

📌 Team update (2026-08-05T10:26:52.618+02:00): Route-map scenario catalogue and README link updates merged into shared decisions.

## 2026-08-05 — US10 wording-fix revision (post-Niobe rejection of Tank's revision)

- **Context:** Tank authored the current US10 revision after Morpheus's version was rejected; Niobe
  rejected Tank's revision for four wording-only overclaims. Tank, Morpheus, and Trinity were locked
  out of this revision cycle, so I (Oracle) took it as the eligible replacement author, per Jose's
  direct request. Scope: wording-only accuracy fix in `route-map-user-stories.md`, not a topology
  redesign — no diagrams created, no US01–US09 edits, no Azure/IaC changes, no commit.
- **Four US10 overclaim corrections applied** (all "proven association" → "proven eligibility,
  unassociated"):
  1. Recommended-section prose: replaced "the lab has proven NVA-peering attachment and has *not* yet
     proven gateway-connection attachment" with language stating the lab has proven route-map
     *eligibility* on hub ARS↔NVA peerings (D2 locality rule, upgraded hub Route Servers); no
     association has been executed anywhere; E-1 is the test.
  2. §2 comparison-matrix US10 row: "supporting — proven on ARS↔NVA peerings" → "supporting — eligible
     (unassociated) on ARS↔NVA peerings; gateway-connection attachment unverified; both pending the
     US10 pre-activation gate".
  3. RM-A/RM-B eligibility-status cells: "Proven eligible" → "Eligible, unassociated: peerIp in-VNet
     per D2, ARS route-map tier active, inert map provisioned; association never executed."
  4. `US10-bow-tie-lab-vpn-analogue` diagram spec, thin control-plane edge label: `BGP · map-eligible
     (proven)` → `BGP · map-eligible (D2) · association untested`.
- **Scenario-retention policy added** (Jose's directive: rejected scenarios must never be deleted from
  the file, only explained). Placed in §2 immediately after the "Fifth applicability class" paragraph
  (right before "Cost note."), so it sits next to the applicability/classification explanation it
  governs. States: no scenario is deleted for its applicability classification, a reviewer's rejection
  of draft wording, or a platform limitation; every retained-but-blocked/unverified scenario (US06,
  US10 today) must record blocking reason, residual value, alternatives/conditions, and the evidence
  needed to revisit the classification (e.g. US10's E-1). Explicitly distinguishes "reviewer rejects
  wording" from "scenario deleted" — those are not the same event.
- **Validated** with a targeted `grep` for `proven NVA-peering|proven eligible|map-eligible \(proven\)|
  proven on ARS|association.*proven|proven.*association` across the file after edits: zero remaining
  overclaim hits (the only match is the retention-policy paragraph's own explanatory mention of the
  word "proven" in quotes, describing the anti-pattern, not asserting it).
- **Not touched:** US01–US09 bodies, diagram index prose beyond what the label change required, Azure
  resources/IaC. No diagrams generated this task. No git commit made.
- Decision recorded at `.squad/decisions/inbox/oracle-us10-wording-fix.md`.

---

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
