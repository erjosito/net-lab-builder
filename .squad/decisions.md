# Squad Decisions

## Active Decisions

### 2026-05-29T11:33:11+02:00: User directive — Trinity ↔ Obsidian vault

**By:** Jose (via Copilot Coordinator)

**What:** Trinity (Network SME) must have read+write access to Jose's personal Obsidian vault about Azure Networking, located in his OneDrive. The relationship is bidirectional:

1. **Read path** — Trinity should consult the vault as a primary knowledge source whenever she designs, reviews, or troubleshoots a lab. The vault is Jose's accumulated Azure Networking notes and supersedes generic public docs when they conflict.
2. **Write path** — Trinity is responsible for backfilling the vault with new findings, troubleshooting tips, gotchas, anomalies, and lessons learned from every lab the squad ships. Backfills happen at lab close (post-validation, pre-cleanup) so the vault grows monotonically.

**Why:** User-requested standing capability. The vault is Jose's curated long-term memory; the squad's labs are short-lived but generate high-value insights that would otherwise be lost at cleanup. Wiring Trinity as the steward keeps the knowledge base in sync with what the squad learns.

**Scope:**
- Trinity's charter (`.squad/agents/trinity/charter.md`) must document the read+write workflow and exact vault path.
- The "lab close" checklist (Niobe or Scribe checkpoint) must include a "vault backfill complete?" gate before cleanup is offered.
- Sanitization rules apply equally to the vault — no subscription IDs, tenant IDs, API keys, or VM passwords in vault content.
- Vault writes happen on the local filesystem; OneDrive sync is opaque to the squad.

**Status:** Merged by Scribe 2026-05-29.
**Cross-links:** [agents/trinity/charter.md](agents/trinity/charter.md) (Vault Stewardship) · [team.md](team.md) (Member Notes) · [routing.md](routing.md) (rule #15) · [ceremonies.md](ceremonies.md) (Vault Backfill)

---

### 2026-05-29T14:18+02:00: User directive — Kid dispatched pre-cleanup for lab #1 blog draft

**By:** Jose (via Copilot Coordinator)

**What:** Kid (blog-writer 📝) dispatched to produce a blog draft for lab #1 (`expressroute-megaport-bgp`) before Tank cleanup. Two-stage workflow: (1) draft complete and committed to `blog-draft/` first; (2) publish to the public rolling repo separately after Jose's review. Rolling blog repo (`github.com/erjosito/azure-networking-blog`) confirmed as default publishing target.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/copilot-directive-20260529T141813-kid-dispatch.md`

---

### 2026-05-29T14:18+02:00: Dispatch confirmed — pre-cleanup timing, draft-only, rolling blog repo default

**By:** Jose (via Copilot Coordinator)

**What:** Confirms the Kid dispatch: pre-cleanup timing is mandatory so the blog draft exists before teardown. Draft-only mode for this run (no direct publish). Rolling blog repo (`azure-networking-blog`) is the standing default publication target for all future labs unless Jose overrides per-lab.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/copilot-directive-20260529T141813.md`

---

### 2026-05-29T14:18+02:00: User directive — Kid's scenario veto authority extended to pre-lab selection

**By:** Jose (via Copilot Coordinator)

**What:** Kid's veto authority extended to the pre-lab *selection* phase, not only post-build revision. Kid may reject or reshape a scenario before Tank deploys if the lab doesn't lend itself to a compelling public post.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/copilot-directive-20260529-1458-blog-scenario-veto.md`

---

### 2026-05-29T14:58+02:00: User directive — blog posts must show actual command output

**By:** Jose (via Copilot Coordinator)

**What:** Standing rule for all future blog posts: every command shown must be accompanied by its actual output (table or `tsv` format) plus an interpretation paragraph. Showing command names without output is not acceptable. Kid and Niobe are jointly responsible for meeting this standard before publication.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/copilot-directive-20260529-1458-blog-command-output.md`

---

### 2026-05-29T14:30+02:00: Kid cast as 8th permanent squad member (blog-writer 📝)

**By:** Coordinator

**What:** The Kid (📝, blog-writer, claude-sonnet-4.6) cast as 8th permanent squad member. Role: convert lab learnings into engaging public posts under `github.com/erjosito`. Seven governance files touched: `registry.json`, `team.md`, `routing.md`, `ceremonies.md`, Kid's `charter.md`, Kid's `history.md`, Kid's routing entry. Squad version bumped v0.9.4 → v0.9.5.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/2026-05-29-kid-casting.md`

---

### 2026-05-29T14:35+02:00: Kid editorial decision — headline for lab #1 blog draft

**By:** The Kid

**What:** After evaluating seven candidate headlines, Kid selected: *"Three commands that lied on a working ExpressRoute lab."* No back-request to Tank or Niobe (cost $110–$125/day not justified; control-plane evidence sufficient). Three deliverables produced: `blog-draft/README.md`, `blog-draft/references.md`, `blog-draft/DRAFT-NOTES.md`.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/kid-20260529-expressroute-megaport-bgp.md`

---

### 2026-05-29T15:00+02:00: Kid v2 blog angle — Option A (rescue with honest framing)

**By:** The Kid

**What:** After v1 draft rejection (multiple factual errors from memory), Kid selected Option A: rescue v1 with honest, anomaly-first framing. New headline: *"The route table that didn't lie: diagnosing ExpressRoute BGP with the Azure CLI."* V1 preserved as `README.v1.md`. V2 sourced entirely from all 30 show-output files before any prose was written.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/kid-blog-v2-angle.md`

---

### 2026-05-29T15:30+02:00: Lab #1 blog post published

**By:** The Kid / Jose

**What:** Lab #1 blog post published at `https://github.com/erjosito/azure-networking-blog/tree/main/2026-05-expressroute-megaport-bgp`. Commit SHA: `21e4f1ba`. Word count: 2,249. Sanitization: zero forbidden GUIDs or credentials. Back-requests: none.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/2026-05-29-kid-blog-published.md`

---

### 2026-05-29T15:35+02:00: Standing rule — blog link in every lab README

**By:** Coordinator / Jose

**What:** Every `labs/<lab>/README.md` must include a blog post link immediately after the H1. Placeholder: `<!-- Blog post: TBD -->` until published; replaced with live URL on publication. Rule applied retroactively to lab #1 (Niobe executed the back-fill).

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/2026-05-29-blog-link-in-lab-readme.md`

---

### 2026-05-29T15:36+02:00: Niobe — lab #1 README blog-link back-fill

**By:** Niobe

**What:** Niobe replaced the placeholder comment (line 3) in `labs/expressroute-megaport-bgp/README.md` with the live blog post URL (*"The route table that didn't lie…"*). Scope: one-line README edit only. Sanitization: no forbidden GUIDs introduced.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/2026-05-29-niobe-lab1-readme-backfill.md`

---

### 2026-05-29T15:40+02:00: Pre-Gate Editorial Review ceremony added (routing rule #17)

**By:** Coordinator / Jose

**What:** New optional ceremony: Kid reviews blog post content with Morpheus (≤300 words) before a lab is marked "shipped externally." Morpheus holds gate authority to pause publication if the post misrepresents findings. Ceremony is optional per lab (waivable for time-sensitive situations). Codified as Routing Rule #17.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/2026-05-29-kid-pre-gate-review.md`

---

### 2026-05-29T15:45+02:00: Layout — Kid's blog repo is a sibling repo, not nested

**By:** Coordinator / Jose

**What:** Kid's blog repo (`azure-networking-blog`) is cloned as a sibling to `net-lab-builder` under the shared `Repos/` folder — NOT nested inside `net-lab-builder`. The `labs/<lab>/blog-draft/` folder inside `net-lab-builder` is a work-in-progress scratchpad only; it is not the canonical blog source.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/2026-05-29-blog-repo-local-layout.md`

---

### 2026-05-29T16:00+02:00: Tank cleanup — lab #1 complete (19/19 resources); two charter amendments

**By:** Tank / Coordinator

**What:** Lab #1 (`expressroute-megaport-bgp`) cleanup completed: 19/19 resources deleted in charter-compliant 6-step order. Root cause of cleanup difficulty: Windows HKCU environment variables are not inherited by Terraform child processes. Workaround: Megaport credentials passed as inline HCL variables. Two charter amendments triggered: (1) env-rehydrate pattern as mandatory Step 0 in all Windows deploy/cleanup scripts; (2) canonical Terraform `.gitignore` lives at repo root — no per-module `.gitignore` files needed for new labs.

**Status:** Merged by Scribe 2026-05-29.
**Source:** `decisions/inbox/2026-05-29-tank-cleanup-lab1.md`

---

### 2026-06-15T09:53:31+02:00: Trinity — vWAN dual-ER symmetry design for lab #2

**By:** Trinity (Azure Network SME)

**What:** Trinity authored the comprehensive design specification for lab #2 (`vwan-dual-er-symmetric`) at `labs/vwan-dual-er-symmetric/design.md`. The lab demonstrates traffic symmetry in a dual-region secured vWAN with two ExpressRoute circuits and GCP on-prem simulation via per-region prefix affinity at the Megaport MCR egress filter. Key decisions: (1) ER bow-tie OFF to enforce per-hub circuit affinity, (2) two separate GCP VPCs (no inter-VPC peering) to pin inbound on-prem prefixes to the correct hub, (3) routing-intent=private on both hubs so all spoke flows traverse the in-hub firewall symmetrically. Trinity probed `platform-secrets-1138` KV and confirmed all three required secrets present (megaport-api-key, megaport-api-secret, default-password). Trinity also identified a critical KV access pattern: Jose's GSA client can collide with the vault's IP-based firewall ACLs, producing 403 "Client address not authorized" errors even when RBAC is correct; two operator-coordinated workarounds documented (Path A: pause GSA; Path B: temporarily flip ACL with snapshot/restore). Design includes a 46-file route-collection plan across three layers (Azure, Megaport, GCP/VMs) and validation checklist for scenarios S1–S4.

**Status:** Merged by Scribe 2026-06-15.
**Source:** `decisions/inbox/trinity-dual-er-symmetry-design.md`
**Files:** `labs/vwan-dual-er-symmetric/design.md`

---

### 2026-06-15T09:53:31+02:00: Niobe — vWAN dual-ER symmetry validation skeleton for lab #2

**By:** Niobe (Lab Validator & Diagnostics)

**What:** Niobe produced the pre-deploy validation skeleton for lab #2 at `labs/vwan-dual-er-symmetric/validation.md`, defining five scenarios (S1–S5) with 31 total assertions. S1 and S2 validate region-specific spoke-to-on-prem paths; S3 validates cross-region symmetry (two-firewall traversal); S4 deliberately breaks symmetry (ER bow-tie injection) to capture firewall drops; S5 is a stretch test (hub-to-hub partition). Expected evidence file count: ~30–35 files (consistent with lab #1's 30 files, but this lab has ~2× topology scope). Validation architecture uses REST API for route queries (`api-version=2025-07-01`), BGP Connection API for advertised/learned routes, and KQL for firewall hit-count analysis. Three blockers identified: Trinity's design.md needed for route-collection plan finalization, Morpheus's manifest.md needed for scenario lock-in and explicit pass/fail criteria, Tank's terraform plan needed for resource name resolution.

**Status:** Merged by Scribe 2026-06-15.
**Source:** `decisions/inbox/niobe-vwan-dual-er-symmetric-validation.md`
**Files:** `labs/vwan-dual-er-symmetric/validation.md`, `.squad/agents/niobe/history.md` (appended)

---

### 2026-06-15T09:53:31+02:00: Oracle — vWAN dual-ER symmetry diagram set for lab #2

**By:** Oracle (Documentation & Diagrams)

**What:** Oracle produced four diagram files for lab #2 under `labs/vwan-dual-er-symmetric/diagrams/`: (1) `01-topology.drawio` — full multi-cloud topology (vWAN, dual secured vHubs, 4 spokes, 2 ER circuits, 2 MCRs, GCP VPC); (2) `02-bgp-control-plane.mmd` — BGP sessions and ASN pairs with prefix-filter symmetry annotation; (3) `03-data-plane-symmetric.mmd` — packet paths for S1, S3, and anti-pattern callout; (4) `04-cleanup-chain.mmd` — 13-step ordered teardown. Also created `labs/vwan-dual-er-symmetric/README.md` skeleton with H1, blog-post placeholder, Diagrams section, and TODO table for TBD label replacement post-deploy. All diagrams validated without parse errors. Icon compromises noted: Megaport MCR and GCP VPC use labeled rectangles (no vendor stencils); Azure Firewall and VNet use assumed Azure2 library paths.

**Status:** Merged by Scribe 2026-06-15.
**Source:** `decisions/inbox/oracle-vwan-dual-er-symmetric-diagrams.md`
**Files:** `labs/vwan-dual-er-symmetric/diagrams/{01,02,03,04}.*`, `labs/vwan-dual-er-symmetric/README.md`

---

### 2026-06-15T10:08:07+02:00: User directive — AKV `platform-secrets-1138` access pattern

**By:** Jose (via Copilot Coordinator)

**What:** The Azure Key Vault `platform-secrets-1138` (RG `platform`, sub `<SUBSCRIPTION_ID>`, swedencentral, RBAC-enabled) contains exactly **three secrets** that the squad consumes for ephemeral-lab work:

1. **Megaport API access key** — for Terraform Megaport provider authentication (deploy + configure MCRs, VXCs, prefix-filter-lists).
2. **Megaport API secret** — pair to the access key above.
3. **Default VM admin password** — reusable for any lab VMs (and other resources) that need a password rather than SSH-key auth.

The vault sits behind **network restrictions** (firewall ACLs). Jose also runs the **Microsoft Global Secure Access (GSA) client** locally, which proxies his outbound traffic through Microsoft's identity-aware network edge and can collide with the vault's IP allow-list, surfacing as `403 Forbidden` / "Access Denied" / "Client address is not authorized" errors on `az keyvault secret show` even when RBAC is correct.

**Standing workarounds — squad picks whichever is least disruptive per dispatch:**

- **Path A (preferred when feasible):** Ask Jose to **temporarily disable the GSA client** for the duration of the secret-fetch step, then re-enable. Squad must be explicit about the window ("disable GSA, I'll read all 3 secrets in one call, then you re-enable").
- **Path B (fallback):** **Temporarily lift the AKV network restrictions** via `az keyvault update --default-action Allow`, fetch the secrets, then **re-apply** with `az keyvault update --default-action Deny` (or whatever the prior state was — capture it with `az keyvault show --query networkAcls` BEFORE flipping). Squad MUST restore the original ACL state in the same dispatch — no leaving the vault open.

**Both paths are operator-mediated (Jose must initiate Path A or authorize Path B).** Squad NEVER silently flips KV network ACLs without explicit per-occurrence approval, even if it has the RBAC role to do so.

**Why:** Captured so Trinity, Tank, and any future agent reading KV `platform-secrets-1138` knows (1) the exact secret count and names to expect, and (2) the specific access-denied root cause that's not RBAC, and the two operator-coordinated workarounds.

**Affects:** Trinity charter (Key Vault probe protocol), Tank deploy workflow (Megaport provider creds fetch + VM password fetch), Niobe (if any validation step requires re-reading a secret).

**Status:** Merged by Scribe 2026-06-15.
**Source:** Direct user input, captured 2026-06-15T10:08:07+02:00 by Coordinator

---

### 2026-06-15T10:15:00+02:00: Morpheus — vWAN dual-ER symmetry lab approval gate for lab #2

**By:** Morpheus (Orchestration & Regional Engineering)

**What:** Morpheus produced the comprehensive manifest for lab #2 (`vwan-dual-er-symmetric`) at `labs/vwan-dual-er-symmetric/manifest.md` and is seeking Jose approval before phase 4 (Tank deploy). Lab scope: dual-region secured vWAN (swedencentral + northeurope) with Azure Firewall Standard in each hub, two ExpressRoute circuits (Standard 50 Mbps via Megaport, no Global Reach, no bow-tie), two MCRs with two GCP VPCs (one per region, no inter-VPC peering), four spoke VNets (two per region, one Linux B2als_v2 VM each), routing-intent=private on both hubs. Daily cost: ~$135/day (~$106 Azure + ~$26 Megaport + ~$3 GCP), **above $50/day flag** requiring explicit Jose approval. Deploy time: ~45–55 min (vHub creation is the long pole at ~30 min each). Lab lifetime: target 24–48 h. Five open questions for Jose: (1) Cost approval for ~$135/day; (2) GCP credential strategy (service-account JSON in KV vs interactive gcloud auth); (3) Lab lifetime (24 h or 48 h); (4) Megaport PoP fallback consent (Stockholm/Amsterdam → Frankfurt/Dublin); (5) Dispatch Kid for pre-gate editorial review or skip. Manifest is paperwork-only; no IaC, no `az create` commands, no Megaport API writes yet.

**Status:** Merged by Scribe 2026-06-15.
**Source:** `decisions/inbox/morpheus-vwan-dual-er-symmetric-manifest.md`
**Files:** `labs/vwan-dual-er-symmetric/manifest.md`, `.squad/skills/dual-er-symmetry/SKILL.md`

---

### 2026-06-15T20:14:00+02:00: User correction — vWAN ASN distinction (65515 vs 65520)

**By:** Jose (via Copilot)

**What:** The vWAN hub's BGP ASN (used by the ER GW / VPN GW for external peering, e.g., MSEE on ER private peering) is **65515**. ASN **65520** is the marker vWAN uses to **prepend** the AS-path of routes that are advertised *across* hubs (inter-hub propagation). Both are vWAN-reserved and non-configurable, but they serve different purposes — confusing them in design docs is a recurring diagramming mistake.

**Why:** User input — *"65520 is not the virtual hub's ASN, but the ASNs that Virtual WAN uses to prepend routes that are advertised across hubs. The hub's ASN is 65515."*

**Scope:** Repo-wide. Lab #2 had 65520 wrongly labeled as the hub's external BGP ASN in multiple locations.

---

### 2026-06-15T15:18:44+02:00: User directive — new GCP project per lab

**By:** Jose (@erjosito) via Copilot coordinator

**What:** "For Google Cloud a new project should be set for each lab, the existing projects should not be used."

**Why:** User policy — each lab gets clean, isolated GCP project; eliminates resource contamination across labs; makes cleanup deterministic (project delete vs resource-by-resource); avoids quota/IAM/billing entanglement with Jose's personal projects.

**Scope:** Repository-wide policy. Applies to ALL labs that use GCP (current lab #2 and all future).

**Implications captured:**
- Morpheus's lab manifest, when GCP is in scope, must specify `create new GCP project per lab` not `use existing project`.
- Tank's IaC must include project creation (Terraform `google_project` resource OR `gcloud projects create` pre-step in `deploy.ps1`).
- New project ID convention: `gcp-<lab-slug-short>-<correlation_id>`.
- Cleanup deletes the project (`gcloud projects delete` OR `terraform destroy` of `google_project`).

---

### 2026-06-15T19:38:55+02:00: User directive — resiliency validation pattern

**By:** Jose (via Copilot)

**What:** For resiliency patches in this repo, the primary validation is **multi-path BGP evidence** (e.g., GCP Cloud Router learns each Azure spoke prefix from 2 MCRs), NOT an active outage / SPOF demonstration. Active fault injection is optional and additive.

**Why:** User input — *"We don't need to run a SPOF test, just to verify that routing should cover for it. For example, that the Google router receives 2 routes for each spoke VNet, one from each MCR."* Deterministic route-table evidence is reproducible; outage tests are slow, risky, and don't add proof beyond what the route table already shows.

**Scope:** Repo-wide. Updates Niobe charter "Resiliency captures" section + routing rule #29 framing.

---

### 2026-06-15T20:06:49+02:00: User directive — every design is valuable, document all of them

**By:** Jose (via Copilot)

**What:** Every network design studied in a lab is valuable — whether it is **recommended** (worth building this way) or **not recommended** (anti-pattern, teaching case, single point of failure, asymmetric, etc.). For every design, Niobe collects evidence, renders a verdict with reasoning grounded in the evidence, and documents it. A lab is never "done" with a single design.

**Why:** User input — *"Every design is valuable. Either because it is a recommended design or because it isn't. For every design Niobe should collect proof of why the design is or is not desirable, document it, and move on."*

**Scope:** Repo-wide. Lab `README.md` MUST have a top-level `## Designs studied` section listing every design candidate (recommended + not recommended) with name, status badge, verdict, evidence link, reasoning.

---

### 2026-06-15T22:46+02:00: User directive — collapse to Design C (single-CR on-prem simulation)

**By:** Jose (@erjosito) (via Copilot)

**What:** Redesign GCP side to use a SINGLE Cloud Router in ONE region, with both Interconnect attachments terminating on it. *"I would like to collapse both CRs into the same region, and even the same CR."*

**Why:** Closer pedagogical match to real-world on-prem topology. Redundancy belongs at the carrier (Megaport) layer, not at the on-prem (GCP) layer.

**Status:** Design C spec drafted by Trinity (blocked on Q1 — Megaport unlock status).

---

### 2026-06-15: Lab decision tiebreaker is pedagogical value (blog post)

**By:** Jose (via Squad coordinator)

**What:** When choosing between options in any lab, the primary tiebreaker is **pedagogical value for the eventual blog post Kid will write**. Speed, operational convenience, and implementation efficiency are secondary.

**Why:** User input — *"As a guideline, always prioritize pedagogical value, or in other words, the value for the blog that Kid will generate (ultimate goal of the lab)."*

**Scope:** Repo-wide. Affects: design selection, validation scope, capture order, phase splits.

---

### 2026-06-15: Kid editorial review — vwan-dual-er-symmetric

**By:** The Kid

**Date:** 2026-06-15

**Verdict:** Publishable with extensions. S1–S3 establish symmetric baselines; S4 breaks symmetry and demonstrates stateful AzFW drop. Two evidence gaps and one mechanism misalignment must be resolved: manifest S4 uses `er_bow_tie=yes` while validation.md S4 uses MCR1 prefix injection — these are different levers. Morpheus must align before Tank deploys.

**Evidence extensions proposed:**
1. S4 pre-perturbation baseline snapshot (before/after comparison)
2. S4 VM-level tcp-state capture showing SYN-SENT stall
3. KQL table standardization (`AZFWNetworkRule` across all docs)

---

### 2026-06-15: Niobe — Asymmetric Routing Evidence (Design B Phase 1)

**By:** Niobe (Lab Validator)

**Verdict: 🔴 ASYMMETRIC ROUTING PROVED**

**What:** With both GCP Cloud Routers advertising both subnets into both MCRs, without the Axis-2 prepend: Hub1 selects MCR1, VM-B returns ALL traffic via cr_onprem_b → MCR2. Result: asymmetric forward via AzFW1, return via AzFW2. AzFW2 drops the return SYN-ACK (no state for original SYN).

**Evidence folder:** `labs/vwan-dual-er-symmetric/show-output/design-b-phase1-asymmetric-2026-06-15/`

**Next step:** Apply Axis-2 prepend; dispatch Niobe post-prepend to validate.

---

### 2026-06-15: Rename troubleshooting-commands.md → troubleshooting-commands-linux.md

**By:** Niobe

**Reason:** Pedagogical symmetry with new Windows/PowerShell companion. All refs in docs/ updated.

---

### 2026-06-15: Niobe gcloud WSL validation — 11 commands tested

**By:** Niobe (Lab Validator)

**Status:** ✅ Complete. Jose's bug report confirmed and fixed.

**What:** Validated hardcoded placeholder `vpc-onprem` in §9.3; it doesn't exist in live lab. Real VPC is `vpc-vwan-symm-a-103167`. Also deprecated gcloud subcommand (`get-effective-firewalls`) replaced with `firewall-rules list`.

**Placeholder convention adopted:** `<YOUR_...>` (e.g., `<YOUR_VPC>`, `<YOUR_ATTACHMENT_NAME>`, `<YOUR_BGP_PEER_NAME>`)

**Files:** `docs/troubleshooting-commands-linux.md` (22.7 KB)

**Evidence:** `labs/vwan-dual-er-symmetric/show-output/gcloud-wsl-validation-2026-06-15/`

---

### 2026-06-15: Niobe → Decisions Inbox: Looking-glass re-test

**From:** Niobe (Lab Validator)

**Subject:** New failure mode on Megaport API auth — credentials may have expired

**What:** Looking-glass test failed at authentication layer (HTTP 401 — "Invalid email or password"). Megaport API credentials in `platform-secrets-1138` were valid at deploy-time but now fail `POST /v2/login`.

**Implication:** Credential rotation externally OR login flow changed. Action needed: verify current Megaport API key status in portal.

**KV ACL Status:** Confirmed `Deny` at end of all passes. No vault left open.

---

### 2026-06-15: Niobe — Windows doc placeholder sync (§8-§9)

**By:** Niobe-3

**Date:** 2026-06-15 23:17 UTC+2

**Scope:** Windows doc `docs/troubleshooting-commands-windows.md` §8-§9 only.

**Changes applied:**
- Added placeholder convention to §0 Conventions
- Fixed 4 placeholder inconsistencies (§8 line 270, §9 lines 285/286/289)
- Replaced deprecated gcloud command
- No validation callouts added (commands ported from validated Linux doc)

**File size:** 29.4 KB (budget ≤30 KB) ✅

---

### 2026-06-15: Windows doc is now self-contained

**By:** Niobe-3

**Status:** ✅ Complete

**Summary:** `docs/troubleshooting-commands-windows.md` restructured to be entirely self-contained. Windows readers no longer need cross-references to the Linux doc.

**Changes:**
- All §1-§9 sections from Linux doc ported with PowerShell conversions
- Section structure mirrors Linux 1:1
- High-value content preserved (backslash callout, credential troubleshooting)

**Metrics:**
- **Final size:** 28.8 KB ✅
- **Sections:** §0-§12 all present
- **Cross-references:** 0

---

### 2026-06-15: MCR prefix filter lists are dead code in vwan-dual-er-symmetric

**By:** Squad (Coordinator) — grep/jq audit

**What:** `megaport_mcr_prefix_filter_list.mcr1_gcp_export` and `megaport_mcr_prefix_filter_list.mcr2_gcp_export` exist in `terraform.tfstate` as named lists, but are NOT REFERENCED from any VXC.

**Why the lab is symmetric today (Design A) WITHOUT the lists doing work:** GCP Cloud Routers are in CUSTOM advertise mode (per-region, one subnet each). Each MCR only LEARNS its own region's prefix. The CRs do the segregation upstream; the filter lists are redundant.

**Implication:** "Mechanism A: MCR prefix-filter lists" claim is incorrect for deployed state. Existing dead filter lists should be DELETED in Design B.

---

### 2026-06-15: Tank — Lab #2 IaC scaffolding decisions (vwan-dual-er-symmetric)

**By:** Tank (IaC)

**Phase:** 4 (Tank IaC + deploy scripts; pre-apply)

**Status:** ✅ Scaffold complete; validated; awaiting Jose to run `deploy.ps1` interactively.

**Decisions made:**
1. VM SKU substitution — `Standard_B2s_v2` in northeurope (B2als_v2 unavailable)
2. VM authentication — password instead of SSH key (using KV secret)
3. GCP credentials — pre-authenticated gcloud ADC (no JSON secret in KV)
4. S4 perturbation surface — both S4a (ER bow-tie) and S4b (MCR prefix injection) wired as TF variables
5. KV access strategy — both Path A and Path B implemented in deploy.ps1
6. Resource group naming — `rg-vwan-symm-<correlation_id>`
7. No public IPs on spoke VMs (access via `az vm run-command` only)

---

### 2026-06-15: Design B Apply — Patterns and Surprises

**By:** Tank (IaC)

**Lab:** vwan-dual-er-symmetric

**Decisions:**

**D1** — Megaport PARTNER VXC pairing_key change is always ForceNew (destroy+create). Accept as part of lifecycle; update design template language.

**D2** — Megaport DOMAIN_1 port exhaustion after rapid VXC ordering cycles. Mitigation: use DOMAIN_2 for alternate attachment. Standard pattern for dual-attachment GCP PARTNER labs.

**D3** — Axis-2 MCR→Azure per-prefix prepend deferred to Megaport portal/API (TF provider limitation).

**D4** — GCP subnet names must be unique per project+region (not just per VPC). Update naming convention: `subnet-<lab_name>-<vpc_id>-<purpose>`.

**D5** — VM's VPC change (ForceNew operation): always use targeted destroy first to avoid dependency ordering issues.

---

### 2026-06-15T22:46+02:00: Tank — Design C Phase 1A complete

**By:** Tank (Deploy/Infra)

**Lab:** vwan-dual-er-symmetric

**What:** GCP-side Phase 1A for Design C complete. One new resource added: `google_compute_interconnect_attachment.att_b_v2`.

**Apply summary:**
- Plan gate ✅ PASSED — 1 to add, 0 to change, 0 to destroy
- Resource added: `google_compute_interconnect_attachment.att_b_v2`
- att_b_v2 initial state: `PENDING_PARTNER`
- Pairing key: `326ba0de-2aed-4eb2-aaf4-2df34108dc07/europe-west3/2`
- Region: `europe-west3` (router_a, eu-w3)
- Domain: `AVAILABILITY_DOMAIN_2`

**Jose Portal Action Items:**
- DELETE: `vxc-mcr2-gcp-b-103167` (old VXC on att_b_new in eu-w4)
- CREATE: new VXC on MCR2 for eu-w3 region with new pairing key

**Phase 1B Prerequisites:**
1. Jose's portal work complete
2. New VXC reaches "Configured" / "Up" state
3. GCP: att_b_v2 transitions PENDING_PARTNER → ACTIVE
4. BGP session on router_a for att_b_v2: ESTABLISHED
5. Jose verbally confirms "BGP is up"

**Status:** Awaiting Jose's portal work.

---

### 2026-06-15: Tank — secondary MCR ↔ ER VXCs patch

**By:** Tank

**Date:** 2026-06-15T18:55:36+02:00

**Lab:** vwan-dual-er-symmetric

**What was missing:** Initial deploy created only 1 VXC per ER circuit (primary port only). Design requires dual VXCs per circuit for dual BGP sessions.

**What was added:**
- `megaport_vxc.azure_circuit1_secondary` (secondary MSEE port → MCR1)
- `megaport_vxc.azure_circuit2_secondary` (secondary MSEE port → MCR2)

**BGP verification:** All 4 sessions Established.

**Charter rule added:** "ER private peering is dual-port; always deploy 2 VXCs per circuit."

---

### 2026-06-15: Design C Spec + 4 Open Questions for Jose

**By:** Trinity (Azure Network SME)

**Date:** 2026-06-15T22:51:42+02:00

**Lab:** vwan-dual-er-symmetric

**Status:** Spec complete. Blocked on Q1 (Megaport unlock). Awaiting Jose gate on Q1–Q4.

**What Design C is:** Single Cloud Router in a single GCP region with two PARTNER Interconnect attachments — one to MCR1, one to MCR2.

**4 Open Questions:**
| # | Question | Trinity recommendation |
|---|---|---|
| Q1 | Megaport portal/API unlock status | If >48 h, recommend Design D |
| Q2 | Consolidated region for single CR | eu-w3 (less churn; att_a unchanged) |
| Q3 | VM topology | Keep both VMs (more interesting BGP) |
| Q4 | Fallback if Megaport locked | Design D (Linux NVA) |

**Key technical facts for Tank:**
- DESTROY: `att_b_new` (eu-w4), `cr_onprem_b` (eu-w4)
- CREATE: `att_c_b` on `router_a` (eu-w3), AVAILABILITY_DOMAIN_2
- Megaport: Update `gcp_b` VXC to new `att_c_b.pairing_key` (portal/API action required)

**No commits until Scribe gates. Jose answers Q1–Q4 → Coordinator dispatches Tank.**

---

### 2026-06-15: Trinity — reserved spare /16 relocated

**By:** Trinity (Azure Network SME)

**Context:** Address plan refresh to match Morpheus manifest.

**What changed:** Reserved spare block `10.50.0.0/16` was set aside for future "anomaly" spokes, but GCP VPC-A is `10.50.1.0/24` and GCP VPC-B is `10.50.2.0/24` — both fall inside the old spare block, creating a false non-overlap claim.

**Resolution:** Reserved spare relocated to **`10.99.0.0/16`**, clear of all assigned Azure prefixes, GCP prefixes, and lab #1 legacy ranges.

**Design implication:** No HCL or BGP logic coupled to old spare. Purely a table correction; Tank needs no IaC change.

---

### 2026-06-15: Trinity — Resiliency Analysis: vwan-dual-er-symmetric

**By:** Trinity (Azure Network SME)

**Date:** 2026-06-15T17:40:37+02:00

**Triggered by:** Jose — *"Trinity should always consider resiliency, and what happens if for example one of the Megaport routers dies."*

**Summary:** Mechanism A (per-region MCR prefix filter) provides NO AUTOMATIC FAILOVER. Analysis catalogued 13 failure modes and proposed 5 mitigations (M1–M5).

**Failure modes (13 total):**
- F1–F4: MCR/ER circuit failures → total loss for affected region
- F5–F8: Hub/AzFW failures → total loss
- F9–F10: VXC failures → NO impact (secondary takes over)
- F11–F13: BGP/GCP CR failures → total loss

**Mitigations:**
| M# | Mitigation | Cost | ROI |
|----|------------|------|-----|
| M1 | Mechanism B (AS-PATH prepend) | $0 | Best — closes 5 gaps, zero cost |
| M2 | Cross-region GCP BGP sessions | +~$1/day | Closes 5 gaps, automatic failover |
| M3 | ER bow-tie | +~$1/day | Covers ER GW failures (F5/F6) |
| M4 | Dual MCR per region | +~$13/day | Over-provisioned |
| M5 | Redundant GCP CR per VPC | +~$1/day | Covers GCP CR failures |

**Recommendation:** v1 baseline unchanged (Tank deploys Mechanism A as designed). Patch catalogue (P1/P2/P3) dormant until Jose authorizes.

---

### 2026-06-15: Design B Verdict + Tank Patch Handoff

**By:** Trinity (Azure Network SME)

**Date:** 2026-06-15T20:30:00+02:00

**Lab:** vwan-dual-er-symmetric

**Status:** Ready for Jose gate → Tank implementation

**Verdict:** Design B (single GLOBAL-routing GCP VPC) achieves automatic bidirectional failover without adding cross-region Megaport circuits. Zero additional Megaport cost.

**Critical findings for Tank:**
1. `routing_mode` REGIONAL→GLOBAL likely in-place; plan confirms
2. Interconnect attachment CANNOT transfer to different Cloud Router — must destroy+recreate
3. `att_a` unchanged if routing_mode in-place
4. Both Cloud Routers must advertise both GCP subnets
5. New MCR→Azure prepend policy: MCR1 prepends 10.50.2.0/24 3×; MCR2 prepends 10.50.1.0/24 3×
6. `correlation_id_override = "103167"` and `password_override` carried forward

**DESTROY list:** vpc_b, router_b, att_b, vm_b, subnets, firewall

**CREATE list:** vpc_onprem_subnet_b, cr_onprem_b, att_b_new, vm_b (lift-and-shift)

**MODIFY list:** vpc_a routing_mode, router_a bgp advertised ranges, megaport_vxc.gcp_b pairing_key, ER circuit prepend policies

**Niobe validation additions post-Tank apply:**
- S2.7: Cross-region TCP assert (zero AzFW drops)
- S2.8: Failover assert (BGP reconvergence ≤120 s)

---

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction


### 2026-06-15T23:25:00Z: Reconciled Design C attachment naming in design.md

**By:** Copilot (coordinator, on behalf of @erjosito)
**What:** Renamed `att_c_a` → `att_a` and `att_c_b` → `att_b_v2` throughout `labs/vwan-dual-er-symmetric/design.md` §3 (Design C section).
**Why:**
- Trinity-4 wrote the spec using `att_c_a` / `att_c_b` as semantic names tied to Design C.
- Tank's Phase 1A actually deployed `google_compute_interconnect_attachment.att_b_v2` in TF state.
- `att_a` was never renamed (still exists from Design B, kept as-is in Design C).
- Spec now matches deployed TF resource names — no future confusion when reading spec vs running gcloud commands.

**Scope:**
- 6 hits of `att_c_a` → `att_a`
- 9 hits of `att_c_b` → `att_b_v2`
- Mechanical rename only. No content changes.

**Not done in this pass (deferred to next Trinity spec update once Design C is live):**
- Cloud Router diagram still says `"cr_onprem"` (line 717) — actual TF resource is `router_a` (kept name from Design B). Update when Design C baseline evidence is captured.
- §3.3 Open questions for Jose still lists Q1-Q4 as TBD. Q1 (Megaport), Q2 (eu-w3 region), Q3 (keep both VMs), Q4 (no fallback needed) are all resolved. Trinity to clean up §3.3 in the post-Phase-1B spec refresh.
- `att_b_new` (Design B) and `cr_onprem_b` references in §3.4 migration plan are still accurate (those resources still exist; Phase 1B will destroy them).


# Decision — Morpheus: Lab #3 MSEE Hairpin Lab Card

**Date:** 2026-06-15  
**By:** Morpheus (Lead / Architect)  
**Status:** Pending Jose gate (A/B/C path selection)

---

## What

Lab card produced for lab #3 (`msee-hairpin-hns-vwan-ipv6`) at `labs/msee-hairpin-hns-vwan-ipv6/lab-card.md`.

**Scope:** Hub-and-spoke VNet (single spoke + ER GW) ↔ Virtual WAN hub (single spoke + ER GW), dual-stack IPv4+IPv6, MSEE hairpinning as the connectivity mechanism, no firewall, single region (`swedencentral`).

---

## Key Design Decisions Made

**Path A (ER Direct) selected as primary.** ER Direct avoids Megaport dependency per Jose's request. Customer-side BGP on the port is not required for Azure-to-Azure MSEE hairpinning — only the Azure-side GW↔MSEE BGP sessions matter. Cost (~$65–75/day rate) exceeds $50/day flag; flagged to Jose with short-runtime mitigation (~$18 for 6h).

**Single region.** `swedencentral` only. MSEE hairpin requires both circuits at the same peering location (Stockholm). Multi-region breaks the mechanism.

**ULA IPv6.** `fd00::/8` for all VNet spaces. No globally routable IPv6 needed for Azure-to-Azure lab.

**GW settings are the pedagogical core.** Three non-default toggles (`allowVirtualWanTraffic`, `allowRemoteVnetTraffic`, `allowNonVirtualWanTraffic`) are the "settings that need to be enabled" Jose referenced. These are silent-fail — no error without them, hairpin just doesn't work.

**Deliberate-break S4.** Toggle `allowVirtualWanTraffic=false` after steady state → confirm hairpin breaks. Matches "every design is valuable" doctrine.

**S5 stretch = Path C as a scenario.** IPsec VPN fallback is preserved as a stretch scenario within Path A deployment, not a separate lab. Cheap to add VPN GW alongside ER GW if hairpin fails.

---

## Paths Declined (documented in lab card §9)

| Path | Why declined as primary |
|---|---|
| B — Megaport | Overrides Jose's explicit "no partner" preference; structurally inferior for this specific question |
| C — IPsec only | Changes the mechanism entirely; lab would teach VPN, not MSEE hairpinning |

---

## Open Gate

Jose must select A / B / C before Stage 2 fan-out. If A: also needs explicit cost approval (>$50/day rate). Stage 2 = full manifest + Trinity/Oracle/Niobe parallel fan-out.


### 2026-06-15T23:52:53+02:00: ExpressRoute Direct port pricing — 45-day free bring-up window

**By:** Jose Moreno (directive, captured by coordinator)

**Scope:** Project-wide — Morpheus + Trinity knowledge base

**Directive (verbatim):** *"ExpressRoute Direct is not charged after 45 days after provisioning. From that perspective, it is quite a safe deployment from a cost angle. Please add this to the knowledge base of the project (not sure if Trinity is the one that should remember this)."*

**Interpretation:** Azure ER Direct ports include a 45-day free provisioning window (intended to cover the cross-connect installation lead-time). For any lab shorter than 45 days, the port itself is $0. Only the ER circuits (Local SKU MeteredData ≈ $0.10/GB), the ER gateways (ErGw1AZ ≈ $0.27/hr ≈ $0.50/day each), the vHub Standard (~$X/day flat), and lab VMs accrue charges.

**Impact on lab #3 (msee-hairpin-hns-vwan-ipv6):**
- Original Path A cost estimate: **~$70/day** (assumed port billing from day 0).
- Corrected Path A cost estimate: **~$25-35/day** (port is $0 within the 45-day window).
- Path A is no longer borderline against the $50/day cost-guardrail flag.

**Who owns this knowledge:**
- **Morpheus (primary):** Owns the cost guardrail (routing rule #7) and the Phase 4 cost gate. Must factor the 45-day free window into every ER Direct cost estimate going forward.
- **Trinity (secondary):** Owns Azure networking SKU lore + vault stewardship. The Azure Networking Obsidian vault should carry this fact under an ER Direct cost note for future reference.

**Status:** Merged by Scribe 2026-06-15.

---

### 2026-06-15T23:52:53+02:00: Morpheus — Lab #3 Full Manifest (Stage 2)

**By:** Morpheus (Lead / Architect)

**Status:** Awaiting Jose Phase 4 deploy gate

**What:** Full manifest written for lab #3 (msee-hairpin-hns-vwan-ipv6) at labs/msee-hairpin-hns-vwan-ipv6/manifest.md. Stage 2 complete.

**Key Decisions Made in Stage 2:**
- **Public IP + NSG over Bastion.** Two Standard PIPs for VM SSH access (NSG-restricted port 22). Bastion adds ~$5/day and is unnecessary for a 6-hour lab.
- **VLAN 100 / 200 assignment.** Circuit 1 (HnS) → VLAN 100; Circuit 2 (vWAN) → VLAN 200. Must be unique per ER Direct port.
- **azapi fallback flagged.** Three hairpin-enabling toggles (llow_virtual_wan_traffic, llow_remote_vnet_traffic, llow_non_virtual_wan_traffic) must be set. If not exposed in current azurerm, use zapi_update_resource.
- **IPv6 peering in single resource.** zurerm_express_route_circuit_peering handles both IPv4 and IPv6 via nested ipv6 block.
- **ER GW dual-stack NIC.** rgw-hns requires dual-stack ip_configuration block — one IPv4 and one IPv6.
- **S5 (IPsec VPN stretch) is optional.** Do not deploy unless Jose explicitly requests it post-S1-S4.

**Phase 4 Gate Text (corrected for 45-day ER Direct free window):** *"Lab msee-hairpin-hns-vwan-ipv6 — Path A (ER Direct, Stockholm). Cost: ~$25-35/day / ~$6.25-8.75 for 6h. Reply **deploy** to proceed."*

**Files:** labs/msee-hairpin-hns-vwan-ipv6/manifest.md (12.1 KB), labs/msee-hairpin-hns-vwan-ipv6/lab-card.md (4.9 KB).

**Status:** Merged by Scribe 2026-06-15.

---

### 2026-06-15T23:52:53+02:00: Trinity — MSEE Hairpin Design Findings (Lab #3)

**By:** Trinity (Network SME)

**Status:** Inbox — merged by Scribe 2026-06-15

**Finding 1: IPv6 ER peering sequencing constraint**
- IPv6 BGP session does NOT establish automatically when ipv6PeeringConfig is added to an ER circuit peering.
- The VNet and GatewaySubnet must have IPv6 address space assigned **before** the GW is created.
- If the GW was created on an IPv4-only subnet, it may need to be recreated (not updated) to become dual-stack.
- **Action:** Tank deploy scripts must enforce this sequencing. Add explicit check in azure-lab SKILL.md under "ExpressRoute gotchas".

**Finding 2: Three hairpin-enabling toggles are silent-fail**
- All three toggles (llowVirtualWanTraffic, llowRemoteVnetTraffic, llowNonVirtualWanTraffic) default to alse.
- When missing, BGP sessions remain Up, circuits show Connected, but routes are simply absent.
- **Action:** Add "hairpin toggle checklist" to lab-card template as a required section whenever HnS ↔ vWAN ER connectivity is in scope.

**Observation 1: vWAN hub IPv6 address space — TF provider gap**
- ipv6AddressSpace on Microsoft.Network/virtualHubs may not be exposed in current stable zurerm TF provider.
- Workaround: z rest --method PATCH.
- Tank should validate during manifest review phase; raise TF provider issue if confirmed.

**Observation 2: Customer-side BGP on ER Direct — unconfirmed hypothesis**
- Lab-card claim: No customer-side BGP needed on ER Direct port for MSEE hairpin.
- Trinity assessment: High-confidence based on MSEE hairpin behavior documentation.
- Flagged for Niobe to confirm post-deploy via list-learned-routes. If confirmed, document as vault entry under [[Services/ExpressRoute]] at Phase 3.4 backfill.

**Status:** Merged by Scribe 2026-06-15.

---

### 2026-06-15T23:52:53+02:00: Oracle — MSEE Hairpin Diagram Pattern & IPv6 ULA Conventions

**By:** Oracle (Documentation & Diagrams)

**Status:** Merged by Scribe 2026-06-15

**Decision: Locked diagram pattern for MSEE hairpinning labs**

**MSEE Hairpin Visual Pattern:**
- The MSEE node is drawn as a single entity with four edges (two ingress, two egress — one per circuit).
- Each edge is labeled with direction (→ advertise / ← learn), ASN (12076), and prefixes.
- This conveys BGP reflection behavior without needing a secondary node.

**IPv6 ULA Peering Conventions in Dual-Stack ER:**
- Peering subnets for IPv4: /30 (e.g., 172.16.1.0/30).
- Peering subnets for IPv6: /126 (e.g., fd00:f:1::/126).
- Each eBGP session is labeled with both families' peer addresses.
- ULA (Unique Local Address) is valid for pure Azure-to-Azure labs where global routing is not required.

**Scope:**
- Applies to all future ER + hairpin labs.
- IPv6 ULA convention applies to any dual-stack ER lab without global routing requirement.
- Diagram files: diagrams/01-topology.mmd, diagrams/02-bgp-control-plane.mmd, etc.

**Checklist for Future Labs:** Identify peering model, address families, routing mechanism, format, and produce four diagrams (Topology, Control Plane, Data Plane, Cleanup Chain).

**Status:** Merged by Scribe 2026-06-15.

---

### 2026-06-15T23:52:53+02:00: Tank — Design C Phase 1B Complete (Lab #2 cleanup)

**By:** Tank (Infrastructure Provisioner)

**Status:** Merged by Scribe 2026-06-15

**Summary:** Design C Phase 1B executed successfully for lab #2 (vwan-dual-er-symmetric). Single-CR GCP-as-on-prem topology is now live and clean.

**Pre-Flight Verification — PASSED:**
- tt-vwan-symm-b-v2 state: **ACTIVE** ✅
- outer-vwan-symm-a BGP peers: **2 peers, both UP** ✅
- GCP Cloud Router "UP" status = established BGP sessions.

**Plan Result:** 0 to add, 0 to change, 2 to destroy (as expected: tt_b_new, cr_onprem_b).

**Apply Duration:** ~30 seconds (2026-06-15, sequential GCP API calls).

**Resources Removed:**
- megaport_vxc.gcp_b from megaport.tf
- google_compute_router.cr_onprem_b from gcp.tf
- google_compute_interconnect_attachment.att_b_new from gcp.tf
- TF state synced via 	erraform state rm megaport_vxc.gcp_b

**Credential Note:** GCP Application Default Credentials (ADC) not set up on Windows. Used gcloud auth print-access-token → GOOGLE_OAUTH_ACCESS_TOKEN env var as workaround. ADC setup recommended for persistent dev use.

**Open Question: megaport_vxc.gcp_b_v2 Import**
- New VXC created via Megaport portal (Jose), paired to tt_b_v2.
- Currently portal-managed and invisible to TF state.
- **Recommendation:** Once Megaport API unlocks, import new VXC to TF state for automated teardown (Option 1 preferred over leaving portal-managed).

**Post-Flight Verification — ALL PASSED:** BGP, Attachments, Routers, Subnets, VMs all intact and clean. Full evidence in labs/vwan-dual-er-symmetric/show-output/design-c-phase1b-2026-06-15/.

---
