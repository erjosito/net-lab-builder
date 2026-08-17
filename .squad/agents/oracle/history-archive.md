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

