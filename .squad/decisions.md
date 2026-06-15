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

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
