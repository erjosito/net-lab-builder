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

## 2026-08-18 — Lab #4 diagram refresh: live deployment values + S1 CONDITIONAL verdict

### Trigger

Jose Moreno directive: integrate live deployment names from Tank's output; label synchronous handler,
10 ms fail-open, claims-only edge gate, origin RS256/JWKS enforcement, EdgeActionConsoleLog,
`deployVersionCode` validation side effect, and portal/VS Code attachment caveat.

### Sources read

`deployment-output.json`, `deploy-log.md` (Sessions 2–4), `S1-capability-probe-result.md`,
`S1-capability-probe-blocked.md`, `smoke-test-results.md` (Run 3), `ea-jwt-validate.js`,
`app/server.js` (jose.jwtVerify implementation).

### Key facts integrated

| Fact | Diagram(s) |
|------|-----------|
| Live endpoint: `edge-jwt-lab-hgbdgdh9ccaja2hv.b02.azurefd.net` | 01, 02, 03, 05 |
| EA resource name: `eajwtvalidate` (not `ea-jwt-validate`) | 01, 02, 03, 04, 05 |
| Rule set: `rsedgejwt / ruleprotected` | 01, 05 |
| FDID sanitised: `549954ba-…` | 01, 02, 03 |
| Entra app-id: `623405b7-…` (api), `6f86ab2c-…` (client) | 01, 02, 05 |
| S1 CONDITIONAL: `crypto/fetch/atob/btoa/TextEncoder=undefined` | all |
| EA = synchronous `handler(event)` — no async, no fetch | 01, 02, 03 |
| Claims-only: pure-JS base64url decode + iss/aud/exp/nbf/roles | all |
| Origin = `jose.jwtVerify` RS256/JWKS (only crypto boundary) | 01, 02, 03 |
| EdgeActionConsoleLog via UserLog on EA resource (not AFD profile) | 01, 02 |
| Reason codes confirmed: MISSING_TOKEN/MALFORMED_HEADER/EXPIRED/AUD_FAIL/ISS_FAIL/ROLE_FAIL | 01, 02 |
| `edgeActionsStatusCode=503` on EA overrun | 01, 02, 04 |
| S7-sim/S9-sim: fake sig passes EA, rejected by origin (`ERR_JWKS_MULTIPLE_MATCHING_KEYS`) | 02, 03 |
| Fail-open in CONDITIONAL = ALL claim checking bypassed (not just sig verify) | 04 |
| `deployVersionCode` → ~17 min real validation → portal/VS Code attachment required | 05, README |
| `validationStatus=Succeeded` in ~15s is PREMATURE false positive | 05, README |
| B3 (preview expired) was temporary blocker; resolved before Session 4 | 05 |
| B1 (admin consent) still active; blocks S7/S9 real-token scenarios | 05 |
| `eajwtvalidate` LIVE: provisioningState=Succeeded, rsedgejwt/ruleprotected attached | 05 |

### Diagram changes

- **01:** Removed JWKS fetch from EA; added async JWKS fetch at origin (jose); live names; UserLog label; reason codes on LAW node.
- **02:** Removed JWKS fetch from EA phase; added synchronous note; real reason codes; S7-sim/S9-sim `ERR_JWKS_MULTIPLE_MATCHING_KEYS` branch; FDID in forwarded headers; `edgeActionsStatusCode=503` in fail-open phase.
- **03:** B2 rewritten with full API availability list (unavailable + available); synchronous handler noted; B4 updated with `jose.jwtVerify createRemoteJWKSet`; S8/S7-sim evidence in annotations.
- **04:** CONDITIONAL mode noted; fail-open = ALL claim checking bypassed; `edgeActionsStatusCode=503` explicit; live EA name.
- **05:** Full rewrite — S1-GATE RESOLVED=CONDITIONAL; GO/STOP greyed as dead; `deployVersionCode` + ~17min + portal/VS Code caveat as annotation node; B3 history; B1 active; `eajwtvalidate` live.

### README update

Rewrote to 28 KB with: live deployment reference table, S1 capability verdict table, `deployVersionCode` operational caveat section, updated diagram captions, and complete inline Mermaid embed blocks for Niobe (all 5 diagrams verbatim, ready to paste into root README).

### Validation

All 5 `.mmd` files: diagram-type declaration present, subgraph opens/ends balanced (flowchart),
`alt…end` count balanced (sequenceDiagram — 2 alt / 2 end). Result: **5/5 PASS**.

## 2026-08-17 — Lab #4 diagram set: `afd-edge-actions-jwt-validation`

### Task

Produce the 5-diagram set for lab #4 (AFD Edge Actions JWT validation) from lab-card, manifest, and design.
Fetch official Edge Actions docs before drawing.

### Key findings from docs fetch (learn.microsoft.com/azure/frontdoor/edge-actions)

- Edge Actions **is in preview** as of 2026-08-17.
- JWT validation is listed as a **supported scenario** in the docs.
- Hyperlight sandbox; 10 ms execution budget.
- When execution exceeds 10 ms the platform terminates Edge Action and sends the request **without EA processing** (fail-open is a platform guarantee, not a code path).
- `EdgeActionConsoleLog` schema confirmed; `edgeActionsStatusCode` (200/503) in AFD access log confirmed.
- **EdgeActionsSamples repo has NO JWT/JWKS/crypto sample** — confirmed in manifest and verified against official sample page description. S1 capability probe is the only authoritative source.

### Files produced

| # | File | Format | Subgraph count | Status |
|---|------|--------|---------------|--------|
| 01 | `diagrams/01-topology.mmd` | `flowchart LR` | 3 subgraphs/3 ends | ✅ balanced |
| 02 | `diagrams/02-token-request-flow.mmd` | `sequenceDiagram` | 0 subgraphs; 1 `alt…end` | ✅ balanced |
| 03 | `diagrams/03-trust-boundaries.mmd` | `flowchart TD` | 4 subgraphs/4 ends | ✅ balanced |
| 04 | `diagrams/04-fail-open-comparison.mmd` | `flowchart LR` | 2 subgraphs/2 ends | ✅ balanced |
| 05 | `diagrams/05-capability-gate.mmd` | `flowchart TD` | 0 subgraphs | ✅ balanced |
| — | `diagrams/README.md` | Markdown | reference table + embed handoff | ✅ |

### Render status

No `mmdc` binary available without installing new tooling. All diagrams validated by:
1. PowerShell syntax check: diagram type declaration present, subgraph opens/ends balanced.
2. Manual inspection of `alt…end` in sequenceDiagram (diagram 02 — 1 alt, 1 end ✅).
GitHub native rendering is the delivery mechanism. PNG exports not produced per charter.

### Live-value placeholders

`‹app-id›`, `‹FDID›`, `‹hash›` — replace from Tank's sanitised deployment output after A0/A1.
Resource role names from manifest (`law-edge-jwt-lab`, `afd-edge-jwt-lab`, `app-edge-jwt-lab`)
are stable and do not require replacement.

### Embed handoff

Full embed block provided in `diagrams/README.md §Niobe — Embed Handoff`.
Niobe is explicitly instructed not to edit `.mmd` sources and to request a live-value refresh from Oracle.

### Decision filed

`.squad/decisions/inbox/oracle-afd-edge-jwt-diagrams.md` — visual conventions and no-JWT-sample-reference pattern.

## 2026-08-08 — Translator endpoint diagram replacement finalized

- Replaced the superseded Storage visuals under `labs/storage-endpoint-path-equivalence/diagrams/` with the deployed Azure AI Translator F0 design in Sweden Central.
- Final set covers the switchable topology, all three access modes and customer-observable route differences, the F0-safe performance method, headline measurements, the overall inconclusive verdict, and the 25 ms positive-control PASS (23.29 ms; 95% CI 22.08–24.48 ms).
- Used verified official Azure VM, VNet, NAT Gateway, Private Endpoint, Private DNS, and Translator icons. Icons retain native aspect ratios within uniform 64 px footprints.
- Exported public PNGs with the installed draw.io desktop CLI and cached Mermaid CLI. Both draw.io files parse as XML; both Mermaid sources render successfully.
- Removed Storage/blob/service-endpoint placeholders and sensitive live names/public addresses. Retained only documented private topology addresses needed to explain the deployed paths.
- Decision handoff: `.squad/decisions/inbox/oracle-translator-diagram-replacement.md`.


## 2026-08-20 -- Lab #5 diagram set + VS Code guide: foundry-agent-prompt-vs-hosted-networking

### Task

Produce 6 Mermaid diagrams, one VS Code hands-on guide, and a README update for the new sibling lab
`labs/foundry-agent-prompt-vs-hosted-networking/`. Lab status: Stage-1 locked, no resources deployed.

### Sources read

`manifest.md` (LOCKED), `README.md` (existing stub), `results.md` (sibling lab), `design.md`
(sibling lab, first 60 lines), three morpheus decision-inbox files (hosted-agent-extension,
vscode-walkthrough, topology-rethink), `morpheus-foundry-lab-restructure.md`, `history.md`, `now.md`.

### Key finding: tools.lab vs onprem.lab naming divergence

The three morpheus decision-inbox files all use `onprem.lab` (predating the lab-restructure decision).
The locked manifest uses `tools.lab` with VMs at `10.1.100.4`/`10.1.200.4`. Oracle followed the
manifest. Decision recorded in `.squad/decisions/inbox/oracle-foundry-diagrams.md` (Decision D1).
Morpheus review requested.

### Files produced

| File | Format | Validated |
|------|--------|-----------|
| `diagrams/01-peered-tools-topology.mmd` | `flowchart TB` 3 subgraphs | drawio-mcp PASS |
| `diagrams/02-historical-vpn-reference.mmd` | `flowchart TB` 4 subgraphs | drawio-mcp PASS |
| `diagrams/03-agent-egress-paths.mmd` | `flowchart LR` 3 path subgraphs | drawio-mcp PASS |
| `diagrams/04-dns-resolution-contexts.mmd` | `flowchart TD` 3 context subgraphs | drawio-mcp PASS |
| `diagrams/05-scenario-matrix.mmd` | `flowchart LR` PREREQS subgraph | drawio-mcp PASS |
| `diagrams/06-programmatic-invocation.mmd` | `flowchart LR` 4 subgraphs | drawio-mcp PASS |
| `hosted-agent-vscode.md` | VS Code guide, 16 sections | Content review |
| `README.md` | Updated with diagram table + inline topology embed | Content review |
| `.squad/decisions/inbox/oracle-foundry-diagrams.md` | Decisions/ambiguities record | Filed |

### Visual grammar choices

- `classDef platform fill:#ddf`: Foundry platform (blue-lavender).
- `classDef toolsnet fill:#e8f8e8`: vnet-tools VMs (green).
- `classDef dns fill:#fff8e1`: DNS resolver components (amber).
- `classDef historical fill:#f5f5f5,stroke-dasharray:6 3`: T2/VPN historical items (grey, dashed).
- `classDef scenario fill:#fce4ec`: scenario nodes in matrix (pink).
- `classDef prereq fill:#e8f4f8`: prerequisite nodes in matrix (blue).
- Bidirectional `<-->` edge for VNet peering; `-.->` dashed for informational flows (Run Command, RBAC annotation).

### Diagram 05 deviation from Morpheus spec

Morpheus D5 in topology-rethink was "S1/S2 negative controls topology". Task A item 5 requires
"HS1-HS5 scenario matrix". Oracle implemented the HS1-HS5 dependency graph, not the negative controls.
Reasoning: negative controls are documented in the sibling lab; this lab needs a scenario matrix.
Deviation recorded in oracle-foundry-diagrams.md Decision D2.

### README embed decision

Diagram 01 (T1 topology) embedded inline in README as "Topology overview" for immediate reader
context. Diagrams 02-06 are source-linked only (table). Trade-off: if diagram 01 changes,
README inline block must also be updated (charter rule: minimize duplication but provide immediate
value). Oracle to track.

### VS Code guide conventions

- Pause/checkpoint boxes before deployment (§11) and before billable Toolbox creation (§14 callout).
- Uses `tools.lab` zone and `echo.tools.lab`/`ctrl.tools.lab` FQDNs throughout.
- Approach A (direct code, Micro VM NIC) vs Approach B (Toolbox SDK, data proxy) clearly separated.
- VS Code UI limitation for OpenAPI toolbox explicitly noted with source citation (2026-08-19).
- Placeholders used for subscription/project IDs and endpoints; no secrets.

## 2026-08-20 (follow-up) -- VPN cleanup direction change: wording update

### Trigger

Jose Moreno authorized changing topology direction (2026-08-20). VPN/on-prem resources are now
active cleanup candidates rather than indefinitely retained.

### Files changed

| File | Change |
|------|--------|
| `README.md` | Updated VPN status note from "NOT authorized" to "authorized cleanup candidate, Gate D1 required". Added "Transition and Cleanup Plan" section with all four required elements (evidence preservation, deletion preview, new resource plan, two separate explicit gates). |
| `diagrams/02-historical-vpn-reference.mmd` | Changed HIST node class from `historical` (grey) to `cleanup` (amber, dashed). Changed label from "VPN cleanup pending Jose approval" to "AUTHORIZED CLEANUP CANDIDATE -- not yet deleted / Gate D1 required before any deletion". Added "CLEANUP CANDIDATE" label to GatewaySubnet, VPN subgraph, vnet-onprem subgraph, and all on-prem resource nodes. Updated `%% updated:` header. |

### Diagram 02 re-validated: drawio-mcp PASS.

### Four required documentation elements delivered (README)

1. **Exact evidence preservation:** Two `az` commands with full flags and output paths;
   three portal screenshot subjects specified.
2. **Exact deletion preview:** Ordered table of 8 resources + RG with region and cost;
   dry-run Bicep `what-if` command; explicit exclusion list of shared resources.
3. **Exact new peered-tools resource plan:** Wave 0-7 table with per-wave action and
   verification command.
4. **Two separate explicit confirmation gates:**
   - Gate D1 (destructive cleanup): Jose must say "DELETE APPROVED" after reviewing
     evidence capture and dry-run outputs. Independent of Gate D2.
   - Gate D2 (billable additions): Jose must say "DEPLOY APPROVED" after Phase 0 preflight
     PASS. Independent of Gate D1; T1 deployment may proceed before or after VPN teardown.

### What did NOT change

- `hosted-agent-vscode.md`: VPN references in that file are about workstation connectivity
  (laptop has no VPN route to Azure VNet; P2S for external SDK calls), not the cleanup gate.
  No changes required.
- `manifest.md`, `design.md`: not Oracle's to edit.
- No live Azure actions; no git commit.


📌 Team update (2026-08-20T11:20:05+02:00): Doc audit complete; manifest corrected for MCR+AAD NSG rules; 6 diagrams validated; ready for Jose review — decided by Scribe

## 2026-08-21 — Code annotation: echo-probe-agent (foundry-agent-prompt-vs-hosted-networking)

### Task

Add verbose, learning-oriented comments and docstrings to the stable Python code for the
`foundry-agent-prompt-vs-hosted-networking` lab.  Authorized side quest within Oracle charter.

### Concurrency check

git status: `labs/foundry-agent-prompt-vs-hosted-networking/` is untracked (`??`).
Filesystem scan: only `main.py` (8/20 2:10 PM) and `tests/test_probes.py` (8/20 2:09 PM) exist on disk.
`invoke_test.py`, `invoke_comprehensive.py`, `hs1_test.py`, `list_agents.py`, `check_sdk.py`, `check_sdk2.py`,
`check_beta.py` appeared in the session context window but do NOT exist on the filesystem — deferred.

### Files annotated

| File | What was added |
|------|---------------|
| `hosted-agent/src/echo-probe-agent/main.py` | Rich module docstring (lab context, H2 hypothesis, prompt vs hosted contrast table, MAF vs LangChain/SK, source-code vs container deployment, Responses API protocol, streaming vs non-streaming); import block comments (requests vs httpx, MAF, FoundryChatClient, ResponsesHostServer, DefaultAzureCredential, dotenv); constant comments (DNS chain, FQDN rationale, timeout tuple semantics + docs link); enriched probe function docstrings (network path, return shape, exception contract, why propagation not swallowing); main() docstring; client/agent/server block comments (credential chain, FoundryChatClient vs AIProjectClient direct, Agent tool schema, instructions design rationale, store=False rationale, ResponsesHostServer blocking behavior) |
| `hosted-agent/src/echo-probe-agent/tests/test_probes.py` | Extended module docstring (test strategy, sys.modules.setdefault vs patch.dict with reasons, @patch("main.requests.get") target convention, why HTTPError propagation tests matter); updated stubbing block comment (flat + dotted module key rule, MagicMock attribute access behavior); import alias comment (_main reasoning, noqa explanation) |

### Validation

- Syntax check: `python -c "import ast; ast.parse(open('main.py').read())"` → OK
- Syntax check: `python -c "import ast; ast.parse(open('tests/test_probes.py').read())"` → OK
- Unit tests: `python -m pytest tests/ -v` → **10/10 PASS** (no semantic changes)
- Diff review: all executable lines unchanged; only docstrings and comments added

### Deferred — second pass needed after Tank completes

These files do not yet exist on disk (Task context showed them from a prior session window):
- `invoke_test.py` — basic Responses API caller (HS2 scenario)
- `invoke_comprehensive.py` — multi-run comprehensive caller
- `hs1_test.py` — beta.agents SDK exploration for prompt-agent path
- `list_agents.py` — AIProjectClient agent listing utility
- `check_sdk.py`, `check_sdk2.py`, `check_beta.py` — SDK introspection one-offs

Coordinator should send a follow-up annotation task to Oracle once Tank has created and committed
these caller scripts.

## 2026-08-21 (second pass) — Code annotation: probe_network.py

### Task

Second annotation pass on `labs/foundry-agent-prompt-vs-hosted-networking/tests/probe_network.py`
(finalized caller script, ~660 lines, created by Tank).

### Auth-header inspection result

The content exclusion policy masked `f"Bearer {tok}"` as `f"******"` in all display outputs
(view tool, PowerShell repr, earlier diagnostics).  Raw byte inspection of the actual file content
confirmed `Bearer {tok}` is the correct literal in the file — no bug.  No correctness fix required.

### Files annotated

| File | Lines before → after | Topics added |
|------|----------------------|--------------|
| `tests/probe_network.py` | 660 → 921 | Module-level import rationale (lazy imports, monotonic vs wall-clock); ENV_KEYS/DEFAULT_ENV_PATH secrets-safe pattern; `load_config()` docstring (priority order, no-python-dotenv rationale, FOUNDRY_PROJECT_ENDPOINT format); `probe_hosted_sdk()` docstring (SDK routing via base_url patch, `model` field overloading, `allow_preview`, alternatives table SDK/raw-REST/LangChain/SK/azure-openai, output parsing getattr vs dict); `probe_hosted_rest()` docstring (raw REST vs SDK table, auth flow JWT scope, AzureCliCredential vs DefaultAzureCredential, endpoint URL fallback, SSE format + event type `response.output_item.done`, non-streaming dict access); inline SSE parsing comments; `compare()` docstring (src_ip key convention mismatch, H2 assessment logic, data proxy evidence); `main()` docstring (CLI mode table, AzureCliCredential gRPC-avoidance rationale, result sanitization, json.dump default=str); `--stream` block comment; comparison print comment; `probe_client_side_fc()` tool-call loop comment (why second turn omitted, expected NameResolutionError) |

### Validation

- `python -m py_compile tests/probe_network.py` → OK
- `python -m pytest hosted-agent/src/echo-probe-agent/tests/ -v` → **10/10 PASS**
- AST structure check: 9 functions (load_config, probe_hosted_sdk, probe_hosted_rest,
  probe_hosted_sessions, probe_client_side_fc, compare, main, src_ip, server_ip), 0 classes
- Diff review: all executable lines unchanged; 261 lines of comments/docstrings added only

### Deferred gaps

- Prior session's deferred list (invoke_test.py, invoke_comprehensive.py, etc.) confirmed
  not to exist on disk — not relevant to this pass.
- `probe_hosted_sessions()` already had a very detailed docstring from Tank; only the
  structural context (compare/main) comments were added for completeness.

📌 Team update (2026-08-21T15:35:00+02:00): Foundry hosted-agent code annotations and diagrams complete. Docstrings updated, diagram validation done, cross-references verified. Lab ready for publication. Decided by Scribe (session orchestration).
