# 📝 The Kid — History

## 2026-05-29 — Blog published: "The route table that didn't lie"

**Lab**: `expressroute-megaport-bgp`  
**Post URL**: `https://github.com/erjosito/azure-networking-blog/tree/main/2026-05-expressroute-megaport-bgp`  
**Commit SHA**: `21e4f1ba59ac2e61197e83005343cebd19536ec2`  
**Word count**: 2,249  
**Artifacts**: README.md, references.md  

### Publication summary
- V2 draft approved by Jose; shipped to public rolling blog `github.com/erjosito/azure-networking-blog`
- Sanitization grep: clean (zero forbidden GUIDs, keys, tokens)
- Back-requests: none
- Repo root README.md created with post listing for discoverability

### Handoff
- Scribe inbox signal created at `.squad/decisions/inbox/2026-05-29-kid-blog-published.md`
- Next action: Niobe backfill of lab README placeholder

---

## 2026-05-29 — Cast & enrolled

- Cast slot: `blog-writer`
- Persistent name: **The Kid** (Matrix universe, registered in `.squad/casting/registry.json`)
- Project: `net-lab-builder` — ephemeral Azure Networking labs
- Owner: Jose Moreno
- Role: Blog Writer & Public Storyteller — convert lab learnings into engaging public posts under `github.com/erjosito`
- Standing authority granted: request scenario changes from Morpheus, additional screenshots from Niobe, additional command outputs from Tank/Trinity, additional or revised diagrams from Oracle. Sign-off (or written waiver) before a lab is "shipped externally."
- Structural commitment: every post follows the inverted-pyramid template (why-it-matters first, then facts most-relevant first).
- Publishing target: `github.com/erjosito` only — public repos. Default pattern: rolling blog repo `azure-networking-blog` with one post per top-level folder. Alternate: per-lab standalone repo `azure-net-blog-<lab-slug>`.
- Sanitization: same forbidden-GUID grep as the rest of the squad; placeholders `<subscription-guid>` / `<tenant-guid>` only.
- Stack context: Azure CLI, Terraform, PowerShell, Megaport API, mermaid, drawio. Lab #1 (`expressroute-megaport-bgp`) is the first post target.

## 2026-05-30 — Blog draft #1 completed

**Lab**: `expressroute-megaport-bgp`  
**Output**: `labs/expressroute-megaport-bgp/blog-draft.md`  
**Word count**: ~2 000 words  
**Structure**: inverted-pyramid (headline finding first, then layers, then gotchas, then reproduce)

### Artifacts consumed
- `manifest.md` (full 300-line design spec)
- `validation.md` (17-item pass/fail; discrepancies noted and resolved against show-output files)
- `lessons-learned.md` (all 7 gotchas from Niobe)
- `README.md` (lab summary + mermaid diagrams)
- `show-output/` files: 04, 04a, 05, 06, 09, 10, 11a, 13, 15, 16, 18, 19, 21

### Key editorial decisions
- **Headline**: BGP `Connected` but learned routes contain only link subnets — no `172.31.100.0/24` — because the MCR route policy was never configured.
- **Secondary finding**: `list-route-tables` returned "no BGP sessions" transiently for ~25 minutes while `list-bgp-peer-status` showed `Connected` throughout. Treated as a teachable timing anomaly.
- **Honest about validation gaps**: `validation.md` items 5, 7, 9 claimed PASS for `172.31.100.0/24`; show-output files (04, 05, 10) refute this. File 13 (VM effective routes) was an error, not a success. Blog uses show-output files as ground truth.
- Used three-layer structure (Gateway → MSEE → Megaport API) to frame the verification sequence.

### Sanitization
- Zero occurrences of subscription GUID `a8fbd8e1-...` — confirmed by grep.
- Zero occurrences of tenant GUID `5ad00b69-...` — confirmed by grep.
- Zero occurrences of Megaport service key `82c05a44-...` — confirmed by grep.
- All Azure resource names, IPs, and ASNs are real (non-sensitive).

### Outstanding items / handoff notes
- `<source-lab-repo-tbd>` placeholder remains: Jose must confirm whether `net-lab-builder` is being made public.
- Publishing URL TBD — `github.com/erjosito/azure-networking-blog/expressroute-megaport-bgp/` once repo is confirmed.
- MCR route policy (prefix injection of `172.31.100.0/24`) was not demonstrated in this lab run. Jose may want to request a second Niobe capture after configuring the MCR route policy, or note this as "Phase 2" in the blog.
- The mermaid diagram in the blog was written fresh from file data (not copied from `diagrams/`). Cross-check against Oracle's canonical diagrams if they differ.

## 2026-05-29 — Blog draft #2 completed (expressroute-megaport-bgp, second pass)

**Lab**: `expressroute-megaport-bgp`  
**Output files**:
- `labs/expressroute-megaport-bgp/blog-draft/README.md` — primary post (~1,600 words)
- `labs/expressroute-megaport-bgp/blog-draft/references.md` — curated link list
- `labs/expressroute-megaport-bgp/blog-draft/DRAFT-NOTES.md` — editorial rationale + ship checklist

### Headline locked

> *Three commands that lied on a working ExpressRoute lab*

Seven candidate headlines evaluated (see DRAFT-NOTES.md). Selected for: concreteness, anomaly-first hook, and verifiability from evidence files.

### Artifacts consumed (this pass)

- `validation.md` (17-item checklist)
- `lessons-learned.md` (7 Niobe entries)
- `manifest.md` (full IaC spec)
- `README.md` (embedded Mermaid diagrams, copied verbatim)
- `show-output/` files: 00, 04, 04a, 06, 07, 09, 10, 11a, 11b, 11c, 13, 15, 15a, 16, 16a, 18, 19, 21 (20+ files)

### Key editorial decisions

- **Actual topology vs planned**: Frankfurt FR5 MCR (Madrid unavailable at deploy), `10.100.0.0/16` VNet CIDR (manifest planned `10.31.0.0/16`). Post uses the actual deployed state.
- **Three API anomalies featured**:
  1. `GET /v2/product/mcr2/{uuid}` → HTTP 405 — fix: polymorphic `/v2/product/{uuid}`
  2. `GET /v2/product/vxc/{uuid}` → HTTP 405 — same fix
  3. MCR looking-glass BGP routes → empty response — fix: Azure-side evidence only
- **BGP proof**: four-layer (ARP, sessions, gateway learned, route table) — control plane verified without needing the VM to be running.
- **Honest gap**: MCR receipt of `12076:20031` community unverified (looking-glass empty). `What we couldn't prove` section added.
- **Stale artifacts excluded**: files 11a/11b (wrong peer IPs) and 11c (old VNet CIDR) treated as evidence-collection mistakes, not anomalies.
- Diagrams 02 and 03 embedded verbatim from `labs/expressroute-megaport-bgp/README.md`.

### Back-request decision: NO

$110–$125/day cost not justified. Control-plane evidence (BGP sessions, AS-PATH, gateway learned routes) is sufficient for all claimed facts. VM would only add NIC-level route tables — not core to the anomaly narrative.

### Sanitization

- Zero occurrences of `<SUBSCRIPTION_ID>` GUID — confirmed by grep.
- Zero occurrences of `<TENANT_ID>` GUID — confirmed by grep.
- Megaport auth token: never extracted to blog files.
- Company UID/name: replaced with `<MEGAPORT_COMPANY_UID>` / `<MEGAPORT_COMPANY_NAME>` in evidence files; not present in blog.

### Ship recommendation

**Ready pending human review** — five items for Jose before publishing:
1. Confirm IPs in embedded Mermaid diagrams are acceptable to expose publicly
2. Confirm MCR UUID and VXC UUIDs are acceptable to expose publicly
3. Verify Mermaid renders correctly on target publishing platform
4. Confirm the "$110–$125/day" figure against actual Megaport invoices
5. Remove the "repo private" disclaimer from `references.md` when `net-lab-builder` goes public

## 2025-07-10 — Blog draft v2 completed (expressroute-megaport-bgp, rescue pass)

**Lab**: `expressroute-megaport-bgp`  
**Reason for this pass**: V1 and v2 were rejected. Both were written from memory or partial file reads and contained multiple factual errors. This pass read all 30 show-output files before writing a single word.

**Output**:
- `labs/expressroute-megaport-bgp/blog-draft/README.md` — v2 post (~2,100 words, all facts sourced from show-output files)
- `labs/expressroute-megaport-bgp/blog-draft/README.v1.md` — preserved copy of the rejected v1 draft
- `.squad/decisions/inbox/kid-blog-v2-angle.md` — Option A decision documented

### Headline locked

> *The route table that didn't lie: diagnosing ExpressRoute BGP with the Azure CLI*

Chosen for: honesty-first framing, tools-forward, and because the central finding is the *absence* of expected prefixes rather than a success story.

### Key factual corrections vs v1

| V1 claim | Ground truth |
|---|---|
| `172.31.100.0/24` in MSEE table | Zero `172.31.*` entries in any captured table |
| BGP community `12076:51013` | Actual: `12076:50057` (file 21) |
| "VLAN 100" on VXCs | QinQ outer VLAN 948, innerVlans [2509, 190] (file 15) |
| `statePfxRcd: 3` includes on-prem | Those 3 are VXC link-locals + reflected VNet |
| Data plane working | `egressBytesTransferred: 0` (file 12) |
| `enableBgp: false` is a bug | Normal for ER connections; BGP managed at peering level |
| Validation.md items 3/4 FAIL (no BGP) | Sessions ARE Connected; items were wrong |

### New findings documented for first time in any draft

1. `az network vnet show` on `GatewaySubnet.ipConfigurations` reveals the two hidden VMSS instances (`.12` at Instance 0, `.13` at Instance 1) with their managed RG
2. `list-route-tables-summary` is the only API that shows sessions to both VMSS instances simultaneously; `list-bgp-peer-status` only returns sessions from one instance
3. Primary MSEE prefers gateway instance `.13` as active next-hop; secondary MSEE prefers `.12` — intentional load distribution, not misconfiguration
4. ARP tables show identical MAC `02cf.2b02.c22b` on both VXC paths → single MCR virtual router underlay
5. AS-PATH `12076-64512` on gateway learned routes confirms the MSEE relay architecture (gateway BGP peers are MSEEs, not MCR directly)
6. Secondary MSEE has 4 routes vs primary's 5: reflected VNet prefix was only on primary VXC session at capture time

### Honest gap (What we could not verify)

- Why `172.31.*` was absent: MCR BGP advertisement config was missing or MCR withdrew prefixes before capture; looking glass returned empty body
- BGP community propagation from MSEE to MCR: looking glass unavailable
- Data-plane connectivity: `egressBytesTransferred: 0`; no VM test before teardown

### Lessons for future labs

- Read every show-output file before writing; do not infer from memory or earlier test runs
- `list-route-tables` at the MSEE is the most authoritative prefix-level view; run it first
- `list-route-tables-summary` is the only single command showing both VMSS instances
- `vnet show` on GatewaySubnet is the easiest CLI path to discover VMSS instance IPs
- `egressBytesTransferred` on the connection object is a definitive data-plane health indicator
- Megaport type-specific GET paths return 405; use `/v2/product/{uuid}` for GET
- MCR looking glass is unreliable near teardown; do not depend on it
- `enableBgp: false` on ER connection objects is normal; document this to prevent false alarms
- `validation.md` may contain errors; cross-check every pass/fail claim against the actual output files

### Sanitization

- All subscription GUIDs replaced with `<SUBSCRIPTION_ID>` in show-output files; none in blog
- Resource names, IPs, ASNs preserved as intended lab outputs

---

📌 Team update (2026-05-29): Phase 3.5 governance close — Kid cast (blog-writer 📝), lab #1 blog published, Tank cleanup complete (19/19 resources), squad v0.9.5. Inbox swept (13 decisions → decisions.md).

## 2026-06-08 — Weekly Topic Scout mode activated

**Trigger**: Jose directive (verbatim): "Hey could you schedule Kid to scout the Internet on a regular basis (weekly, for example) for new potential topics for a blog post, and ask me (via email or Teams) whether I want to go forward with any of them? He should focus on features (new or existing) that are not properly documented or where the documentation is lacking depth. The new topics should not be a regurgitation of existing docs or blog posts or a verification that something works as designed, but should give some added value: how to troubleshoot a certain feature, corner cases of a certain design, etc."

### What changed for me
- New 7th standing authority: autonomous scout self-direction (between labs).
- New charter section: "Weekly Topic Scout (scheduled, between-labs mode)" — source list, quality bar, candidate format, channel design, expected Jose response shapes, scout-specific boundaries.
- Coordinator registered `manage_schedule` with `interval: "1d"` (the tool's hard max — `7d` is rejected) and a 7-day debounce marker at `~/.copilot/session-state/kid-last-scout.txt`. Net cadence: one scout pass per week; six no-op dispatches in between. **Schedule ID: `#1`** (returned 2026-06-08 from `manage_schedule action=create`).
- Notification channel: `agent365-teamsserver-SendMessageToSelf` (primary, no UPN literals in repo) with `agent365-mail-SendEmailWithAttachments` + runtime `agent365-meserver-GetMyDetails` UPN resolution as fallback.

### Quality bar (hard rules)
1. NOT documentation regurgitation (if MS Learn covers it well, skip).
2. NOT "works as designed" verifications (no "yes the docs are right" posts).
3. YES added value via troubleshooting workflow / corner-case behavior / surprising interaction / depth gap.

### Mechanics
- Per scout pass: 3–5 numbered candidates (title, why-it-matters, what's-missing-in-docs, proposed-lab-angle, scout-source-links).
- Jose's reply shapes routed by coordinator: numeric pick(s) → inbox directive + Morpheus dispatch on explicit "go" (Rule #12 unchanged); "skip" → no inbox file; no reply → silent roll to next week.
- No batch-up of stale candidates — under-documented topics naturally resurface; no need to remember.
- Mode-collision guard: scout SKIPPED on any week where I'm actively drafting a post or in pre-gate review for a live lab.

### Governance changes (parallel)
- `.squad/agents/kid/charter.md` — 7th standing authority + new section
- `.squad/ceremonies.md` — "Weekly Blog-Topic Scout (scheduled, between-labs)" ceremony
- `.squad/routing.md` — Rule #18 (scout output handling, mode-collision guard)
- `.squad/team.md` — member-note blockquote
- `.squad/decisions/inbox/2026-06-08-kid-weekly-scout.md` — directive capture for Scribe

### Scope
Azure Networking only. Same scope as my publishing target; non-networking topics are out-of-bounds even if they look juicy.

---

📌 Team update (2026-06-15): Phase 1 manifest design fan-out complete on 2026-06-15; Jose gate pending.

## 2026-06-15 — Pre-gate editorial review: vwan-dual-er-symmetric

**Lab**: `vwan-dual-er-symmetric`
**Dispatch type**: Pre-gate editorial review (routing rule #17)
**Verdict**: **Publishable with extensions** — narrative arc is strong; two evidence gaps and one mechanism misalignment need resolution before deploy.

### Editorial verdict

S1–S4 form a clean before/after arc: symmetric baselines for Region-A, Region-B, and cross-region east-west; then S4 breaks symmetry and captures the stateful AzFW drop. The headline finding is novel and demonstrable. Passes the "not docs regurgitation" bar.

**Critical alignment issue found:** manifest S4 uses `er_bow_tie=yes` (Azure ER-GW cross-connections) as the perturbation, but validation.md S4 uses MCR1 prefix injection (Megaport-side). These are different mechanisms. The MCR injection approach is more reliable at producing the failure because it directly controls GCP's routing table rather than depending on Azure vWAN best-path selection (manifest §9 Risk #3). Morpheus must choose one before deploy.

### Evidence extensions proposed

1. **S4 pre-perturbation baseline**: add `s4-00-azfw-baseline-both-hubs.txt` before any injection — without a timestamped "before" the reader has no contrast.
2. **S4 VM-level tcp-state capture**: `ss -tn state SYN-SENT` on the source VM during failure → `s4-vm-half-open.txt`. Readers can replicate without Log Analytics access; firewall-log-only is indirect.
3. **KQL table standardization**: manifest uses `AZFWNetworkRule` (resource-specific), validation uses legacy `AzureDiagnostics | where Category == "AzureFirewallNetworkRule"`. Align on `AZFWNetworkRule`.

### Learnings for future labs

- **Mechanism misalignment between manifest and validation is a deploy-blocker** — always cross-check S4-class perturbation steps between Morpheus and Niobe docs before gate.
- **Pre-perturbation baselines must be named artifacts**, not implied. "Before" screenshots are structurally essential for any "deliberate failure demo" scenario in a blog post.
- **VM-level tcp-state captures** (`ss -tn`, `netstat`) are cheap adds that make firewall-drop evidence reproducible by readers who lack Log Analytics access. Include in every "stateful drop" scenario.
- **KQL table name** `AZFWNetworkRule` (resource-specific, available since ~2022) is preferred over `AzureDiagnostics | where Category == "AzureFirewallNetworkRule"` — include this as a standing recommendation in evidence templates.
- Mode-collision guard fired: weekly scout skipped this week (active pre-gate review per routing rule #18).

