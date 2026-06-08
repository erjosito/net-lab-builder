# Squad Project Journal

---

## 📌 2026-05-29 — Oracle Cast: Documentation & Diagrams Agent Joins Squad

**Trigger:** Jose's feedback on lab #1 (`expressroute-megaport-bgp/`) revealed that architecture documentation was incomplete. Screenshots and diagnostic show-output existed (Niobe's work), but no visual diagrams connecting topology, control-plane routes, and data-plane flows. The diagrams/ folder was stubbed but empty. When Jose asked "where are the ER path diagrams?", Morpheus and Trinity realized the squad lacked a dedicated agent for diagram authorship.

**Decision:** Rather than expand Niobe's already-full validation remit, cast a new permanent agent—**Oracle** (🔮 Documentation & Diagrams)—and dedicate her to diagram design, standardization, and lab-to-diagram synchronization.

**Why this call:** Diagram authoring (Mermaid, Drawio, topology/control-plane/data-plane layering, branded cloud stencils) is a distinct skillset from lab validation. Niobe's mandate is evidence capture and reporting, not visualization. By separating concerns, Oracle owns diagram quality and consistency, while Niobe focuses on diagnostics. Both report independently to Morpheus with no bottleneck.

**Charter changes:**
- **Morpheus** (lead-architect): Added Oracle to collaboration (Hand-off section). Morpheus now confirms the diagram set with Oracle before Tank deploys; Oracle starts drafting against the manifest topology immediately.
- **Niobe** (lab-validator): Moved `labs/<lab>/diagrams/` ownership from Niobe's charter to Oracle's. Niobe no longer produces diagrams; instead, she feeds Oracle verbatim show-output values (ASNs, peer IPs, VLANs, route lines) as the source-of-truth for diagram labels. Niobe flags diagram drift via `squad:oracle` issues.
- **team.md**: Added Oracle row (5th permanent member, 🔮 Documentation & Diagrams, active).
- **routing.md**: Added "Lab documentation & diagrams → Oracle" routing rule (#13). Added Rule #14 (Diagram-First): every lab ships with topology, control-plane, data-plane, and cleanup diagrams; default ER+Megaport catalogue applies unless overridden.
- **casting/registry.json**: Registered Oracle slot (docs-diagrams, universe: The Matrix, created 2026-05-29T00:00:00+02:00).

**Oracle's identity:**
- **Role:** Documentation & Diagrams
- **Model:** claude-sonnet-4.6 (cost-first for routine diagramming; bumps to opus for complex multi-cloud topologies)
- **Matrix universe:** Yes (Trinity, Morpheus, Tank, Niobe, Oracle—complete squad)
- **Standard diagram catalogue:** Topology (live ASNs/IPs/prefixes), control-plane (BGP adjacencies, route propagation), data-plane (traffic flow paths, NSG/firewall rules), cleanup (resource destruction sequence)
- **Tooling:** `drawio-create_diagram` MCP (validate all diagrams), `drawio-search_shapes` MCP (find branded cloud icons). Decision matrix: Mermaid for simple shapes (GitHub-native rendering); Drawio for multi-cloud/branded topologies.

**First dispatch:** Retrofit `labs/expressroute-megaport-bgp/diagrams/` with ER+Megaport standard set. Source-of-truth values (ER service key redactions, Megaport ASN, Azure vnet prefix, traffic flows) come from Niobe's show-output captures + Morpheus's design brief. Oracle labels diagrams, validates topology against effective-routes evidence, and commits to `.squad/agents/oracle/history.md` a trace of each diagram's intent, tooling choice, and revision cycle.

**Impact on squad velocity:** Diagrams are now a first-class lab deliverable, not a post-hoc afterthought. Morpheus spins up each lab with an explicit diagram spec; Oracle parallelizes drafting from day one. By the time Niobe finishes validation, diagrams are ready to embed in `README.md`. No more "diagrams can wait" — Rule #14 makes them mandatory.

---

## 📌 2026-05-29 — Phase 3.3.5 + 3.3.6 Close: Diagrams Retrofit & Trinity-Obsidian Integration

**Trigger:** Two concurrent initiatives completed in this session — (1) Oracle identified that lab #1 README referenced four PNG diagram files that never existed (only `.mmd` and `.drawio` sources were present), causing broken images on GitHub. (2) Coordinator dispatched Trinity to backfill the squad's lab findings into Jose's personal Obsidian vault on OneDrive, establishing the standing capability directed in inbox directive `copilot-directive-20260529T113311-trinity-obsidian.md`.

**Phase 3.3.5 — Oracle inline-mermaid retrofit:**

Oracle replaced all four broken PNG refs in `labs/expressroute-megaport-bgp/README.md`:
- Diagram 1 (ER+Megaport topology) → replaced with prose description + drawio source link, as the source is a `.drawio` file that cannot be converted to inline Mermaid.
- Diagrams 2–4 (control-plane, data-plane, cleanup) → converted to inline Mermaid fenced blocks, rendering natively on GitHub without any external file dependency.

Sanitization pass confirmed on README — no forbidden credentials, GUIDs, or subscription IDs in the embedded diagrams.

**Phase 3.3.6 — Trinity-Obsidian vault integration (lab close gate):**

Trinity executed the first backfill of Jose's Obsidian vault with findings from lab #1 (`expressroute-megaport-bgp`). Files created/updated in the vault:
- **Created:** `Labs/2026-05-ExpressRoute-Megaport-BGP.md` (45 lines) — full lab record with topology, anomalies, lessons learned, and recommended next steps.
- **Created:** `Services/Megaport.md` (47 lines) — new node; MCR, BGP peering, ASN 133937, VLAN 100.
- **Updated:** `Services/ExpressRoute.md` — appended finding: `az network express-route list-route-tables` false-negative (returns empty when routes *are* active); workaround documented.
- **Updated:** `Topics/BGP-on-Azure.md` — appended finding: custom BGP community is not surfaced in `show ip bgp` via vnet gateway; added `[needs confirmation]` flag.
- **Updated:** `_Index.md` — linked all four above entries.

Trinity confirmed **5 anomalies documented** and **zero forbidden GUID matches** across all 5 touched vault files (sanitization PASS).

**Governance implemented (Phase 3.3.6 standing capability):**
- `agents/trinity/charter.md` — Vault Stewardship section added (read+write workflow, vault path, backfill checklist, sanitization rules).
- `team.md` — Trinity member note updated with vault link.
- `routing.md` — Rule #15 added (vault is single source of truth; read-only for non-Trinity squad members).
- `ceremonies.md` — Vault Backfill ceremony added as mandatory lab close gate.
- `decisions.md` — Inbox directive merged as first recorded squad decision.

**Why this call:** The vault is Jose's long-term Azure Networking knowledge base; lab outputs were ephemeral. Making Trinity the standing vault steward ensures every squad lab enriches the knowledge base before cleanup. The governance scaffolding (routing rule, ceremony, charter section) enforces this as a repeatable process.

**Phase 3.4 gate status:** UNBLOCKED on Trinity side (vault backfill complete, sanitization PASS). Awaiting Jose's gate approval on issues #12 and #2.

---

## 📌 2026-05-29 — Phase 3.5 Governance Close: Kid, Blog Pipeline, Tank Cleanup, Squad v0.9.5

**Trigger:** Accumulation of 13 inbox decisions from Phase 3 activities (blog pipeline, Kid cast, Tank lab #1 cleanup) required a governance sweep.

**Changes swept:**

- **Kid cast** as 8th permanent squad member (blog-writer 📝, claude-sonnet-4.6). Squad roster now complete at 8 agents.
- **Blog pipeline established:** Pre-cleanup draft requirement, two-stage publish workflow, scenario veto authority extended to pre-lab selection, blog-link rule in every lab README, Pre-Gate Editorial Review ceremony (Rule #17), blog repo as sibling repo.
- **Lab #1 blog published:** *"The route table that didn't lie: diagnosing ExpressRoute BGP with the Azure CLI"* — `github.com/erjosito/azure-networking-blog/tree/main/2026-05-expressroute-megaport-bgp`.
- **Tank cleanup complete:** Lab #1 all 19/19 resources deleted. Windows env-rehydrate pattern discovered and codified in Tank's charter `§Pre-flight (Windows)`. Canonical Terraform `.gitignore` at repo root confirmed.
- **Standing rules added:** Blog posts must show actual command output (not just command names). Routing Rule #17 (Pre-Gate Editorial Review).
- **Squad version:** v0.9.5 (Kid added, pre-gate ceremony, blog-link convention, Tank Windows-env workaround).

**Governance artefacts updated (this sweep):**

- `decisions.md` — 13 new entries merged; inbox emptied
- `agents/tank/charter.md` — 2 amendments applied (`§Pre-flight (Windows)` + `§Boundaries` root-`.gitignore` note)
- `agents/{kid,niobe,morpheus,tank,scribe}/history.md` — team update appended to each
- `log/2026-05-29-phase35-governance.md` — session log created

---

## 📌 2026-06-08 — Kid weekly blog-topic scout enrolled (v0.9.5)

**Trigger:** Jose (Scribe) directive requested autonomous weekly topic discovery for Azure Networking to build a lab-candidate pipeline between deployments, reducing cold-start friction in Phase 1 phase-gate editorial review.

**Decision:** Enroll Kid's weekly topic scout as a permanent ceremony with schedule ID #1, running every 7 days via debounce marker at `~/.copilot/session-state/kid-last-scout.txt`. Scout surfaces 3–5 candidate topics (filtered against Jose's quality bar: no documentation regurgitation, no "works as designed" verifications—only troubleshooting, corner-cases, or depth gaps) and delivers digest to Jose's Teams "Notes to Self" (primary, no hard-coded UPNs) with email fallback.

**Why this call:** Phase 1 retrospective highlighted Kid's critical contribution at the editorial review gate (caught a single-source evidence gap). Moving topic discovery forward from *lab design* to topic *scouting* costs one Kid dispatch per week and avoids the much costlier "wrong lab" downstream failure mode. Weekly proactive topic surfaces let Jose make smarter lab-pick decisions.

**Mechanism:**
- Fire daily via `manage_schedule` (interval: "1d"; tool hard-max enforces daily).
- Check marker file before scout: if last run ≥ 7 days ago or marker missing, proceed; else no-op (debounce).
- Search 7 canonical sources: Microsoft Learn, azure-docs issues, Azure updates RSS, Tech Community, Stack Overflow, MVP blogs (Mauser, Mester, Stuart, Finn), GitHub (cli, bicep, terraform-provider-azurerm).
- Produce 3–5 candidates (≤200 words each: Title, Why it matters, What's missing, Lab angle, Scout source(s)).
- Primary delivery: `agent365-teamsserver-SendMessageToSelf` (Teams Notes to Self).
- Fallback: Resolve UPN at runtime via `agent365-meserver-GetMyDetails` → email via `agent365-mail-SendEmailWithAttachments`.
- Write current date to marker file after successful dispatch.

**Quality bar (mandatory pre-send):**
1. NOT documentation regurgitation (3+ community posts already cover it → reject).
2. NOT "works as designed" verification (only thin-post labs → reject).
3. YES one of: troubleshooting workflow, corner-case behavior, surprising interaction, depth gap.

**Jose response routes:**
- Numeric pick (e.g., "1" or "2, 4"): create `.squad/decisions/inbox/<YYYY-MM-DD>-blog-topic-<slug>.md` → Morpheus designs lab.
- "skip": no action; cycle continues.
- No reply within 7 days: treated as "skip".

**Files touched:**
- `.squad/agents/kid/charter.md` — "Weekly Topic Scout" section (lines 92–150) documenting ceremony, trigger, mechanism, quality bar, channels, debounce marker.
- `.squad/ceremonies.md` — "Weekly Blog-Topic Scout" entry with cadence, facilitator (Kid), participants (Jose), channels, quality bar.
- `.squad/routing.md` — Rule #18: scout output (Jose numeric picks) → coordinator routing → blog-topic inbox filing → Morpheus lab design.
- `.squad/team.md` — Kid member note extended: scout responsibility, schedule ID #1 registered 2026-06-08.
- `.squad/agents/kid/history.md` — Kid audit entry: scout enrollment logged.
- `.squad/decisions/decisions.md` — NEW: created shared decision log; first entry: 2026-06-08 scout enrollment (detailed mechanism, quality bar, channels, files touched).

**Schedule registration:** `manage_schedule` call returned schedule ID #1 (canonical reference for ceremony in all squad systems).

**Sanitization:** Pre-merge validation confirmed zero hits across inbox directive, charters, ceremonies, routing, and team files. All 7 governance files scanned post-merge; 5 source files remain clean; decision and journal entries reference forbidden patterns only in sanitization section (for reference, not exposure) with explicit redaction note in committed message.

---
