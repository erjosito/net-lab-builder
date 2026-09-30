# 📝 The Kid — History (SUMMARIZED)

## Tenure Summary

**Role:** Blog Writer & Public Storyteller (cast 2026-05-29)  
**Authority:** Blog editorial + scenario/output requests from squad; weekly topic scout (scheduled 2026-06-08)  
**Publishing target:** `github.com/erjosito/azure-networking-blog` (public Azure-Networking posts only)  
**Stack:** Azure CLI, Terraform, PowerShell, Megaport API, mermaid, drawio

---

## Major Deliverables

### 2026-05-29: Blog Published ("The route table that didn't lie")
- **Lab**: expressroute-megaport-bgp
- **Word count**: 2,249
- **Key finding**: Three API anomalies (MCR GET 405s, ARP tables reveal MCR virtual router)
- **Status**: ✅ Published to `github.com/erjosito/azure-networking-blog`
- **Sanitization**: Zero forbidden GUIDs/secrets (confirmed by grep)

### 2026-05-30 to 2026-06-08: Draft Iterations (expressroute-megaport-bgp)

**Draft v1 (2026-05-30):** ~2,000 words; rejected for factual gaps (claimed `172.31.100.0/24` without show-output evidence, validation.md/show-output conflicts).

**Draft v2 (2026-05-29):** Inverted-pyramid framing locked; MCR route policy captured; back-request decision: NO (control-plane evidence sufficient).

**Draft v2 "rescue pass" (2026-07-10):** **Complete rewrite from all 30 show-output files** — corrected six major v1 errors:
- Removed false `172.31.*` claims (zero entries in any captured table)
- Corrected BGP community `12076:51013` → `12076:50057`
- Verified VMSS instance discovery via `vnet show`
- Documented honest gaps: MCR looking-glass unavailable, no data-plane test

**Lessons learned:** Read every show-output file before writing; `list-route-tables` at MSEE is definitive; `egressBytesTransferred` is data-plane proof.

### 2026-06-15: Pre-gate Editorial Review (vwan-dual-er-symmetric)
**Lab**: vwan-dual-er-symmetric  
**Verdict**: ✅ **Publishable with extensions** — narrative arc strong; two evidence gaps and one mechanism misalignment require resolution.

**Critical issue found**: S4 perturbation mismatch (manifest uses `er_bow_tie=yes` [Azure-side], validation uses MCR prefix injection [Megaport-side]). MCR injection more reliable. **Morpheus must choose before deploy.**

**Evidence extensions required**:
1. S4 pre-perturbation baseline (timestamped "before" needed for contrast)
2. VM-level tcp-state capture (`ss -tn state SYN-SENT`) for reader reproducibility
3. KQL table standardization: prefer `AZFWNetworkRule` over legacy `AzureDiagnostics`

**Learnings**: Mechanism misalignment is a deploy-blocker; pre-perturbation baselines must be named artifacts; vm-level tcp-state cheap add for firewall-drop scenarios.

---

## Governance & Standing Authority

**Charter sections** (as of 2026-06-15):
- Cast registration + editorial standards (inverted-pyramid template)
- Scenario-change requests (from Morpheus, with sign-off gate)
- **NEW (2026-06-08)**: Weekly Topic Scout — autonomous 1/week pass on Internet for under-documented Azure Networking topics. Quality bar: troubleshooting workflow / corner cases / depth gaps (not docs regurgitation, not "works as designed" verification). Candidates routed to Jose via Teams/email; numeric picks → inbox directives.
## 2026-06-10 — Weekly scout (autonomous, between-labs mode)

**Cadence:** Schedule #1 (1d interval, 7-day debounce marker).
**Candidates surfaced:** 4
**Channel used:** teams-notes-to-self
**Sanitization:** PASS (zero forbidden-GUID hits, zero UPN literals)
**Sources checked:**
- Microsoft Tech Community — Azure Networking Blog (3 posts: private subnets Apr 2026, summarized gateway prefixes May 2026, NSP GA Jun 2026)
- Microsoft Learn — Azure Networking (default outbound access limitations section, NSP concepts)
- Stack Overflow (azure-virtual-network, azure-private-link, azure-application-gateway tags — unanswered + high-vote queries)

### Candidates (full digest)

**Kid weekly scout — 2026-06-10**

**1. Private subnets by default: NVA `nextHopType=Internet` silent break**
_Why:_ NVA/firewall users with Service Tag bypass UDRs silently lose egress when migrating to the new private-subnet default (API 2025-07-01+).
_Gap:_ MS Learn buries the break in a one-line limitations table; no troubleshooting guide exists. Terraform still uses the old default — IaC teams see inconsistent behavior.
_Lab:_ Hub-spoke + NVA with Service Tag UDR → migrate to private subnet → observe silent egress failure → diagnose via effective routes → fix with NAT Gateway.
[MS Learn](https://learn.microsoft.com/en-us/azure/virtual-network/default-outbound-access) · [TC Apr 2026](https://techcommunity.microsoft.com/blog/azurenetworkingblog/private-subnets-by-default-in-azure-virtual-networks-what-changed-and-how-to-use/4513778)

**2. Summarized Gateway Prefixes: what happens when a spoke falls outside the summary range?**
_Why:_ Enterprises near the 1000-prefix ER/VPN limit rely on this new feature (public preview, May 2026); a misconfigured summary can silently black-hole spokes added after the fact.
_Gap:_ One official blog post; zero community follow-up; fallback routing behavior for out-of-range spokes is undocumented.
_Lab:_ Hub-spoke + ER gateway → configure summary prefix → add spoke outside range → inspect on-prem BGP table and spoke VM effective routes.
[TC May 2026](https://techcommunity.microsoft.com/blog/azurenetworkingblog/summarized-gateway-prefixes-for-route-advertisement-in-azure-virtual-networks/4521652)

**3. NSP enforced mode: using transition-mode audit logs to predict what breaks**
_Why:_ Network Security Perimeter just hit GA (Jun 2026); no operational guide exists for converting transition-mode audit logs into a pre-flight deny preview before switching to enforced.
_Gap:_ NSP docs describe both modes but give no "deny-list preview" workflow; the GA blog is announcement-only.
_Lab:_ Storage + Service Bus in NSP transition mode → generate mixed traffic → mine audit logs → switch to enforced → compare predicted vs actual denials.
[MS Learn NSP](https://learn.microsoft.com/en-us/azure/private-link/network-security-perimeter-concepts) · [TC Jun 2026](https://techcommunity.microsoft.com/blog/azurenetworkingblog/ga-of-nsp-for-azure-service-bus--nsp-now-available-in-azure-gov-regions/4526413)

**4. App Gateway session affinity vs browser SameSite/third-party cookie restrictions**
_Why:_ When App Gateway's domain differs from the backend (common with App Service), the affinity cookie is silently dropped by Chrome/Firefox — sessions misroute unpredictably.
_Gap:_ MS App Gateway docs are silent on SameSite=None/Secure requirements; SO question has 567 views, 0 answers.
_Lab:_ App Gateway → multi-domain App Service backends → enable affinity → trace dropped cookie in browser devtools → validate fix via domain alignment or SameSite attribute.

### Outcome (pending Jose reply)

Awaiting Jose's reply. Per Rule #18, his pick (numeric / skip / silence) is handled in a future session by the coordinator.

---

## 2026-06-08 — Weekly Topic Scout mode activated

**Schedule ID #1** (1-day hard max, 7-day debounce = 1/week cadence)  
**Mode-collision guard**: scout skipped if actively drafting or in pre-gate review

---

## Archived Details

Full narrative, factual corrections table, and scout mechanics preserved in history-archive.md (2026-06-15).

---

📌 **Current status (2026-06-16T00:40:00Z, per Scribe):** Pre-gate editorial review complete. Awaiting Morpheus S4 perturbation alignment decision and Trinity editorial feedback on Mech C cost implications (~$270-405 approved; realistic ~$675-810) before lab deploy authorization.

---

### 2026-08-05: Editorial pass — US01–US10 intent reframing (dual-hub-hubless-region-ars)

**Trigger:** Jose flagged US01's story sentence ("I want each hub to learn only an approved subset
of the other's prefixes...") as mechanism-first — asked why an owner would want partial reachability,
whether applications are deliberately isolated, and whether the driver is security. Clarified the ask
is about intent framing, not the formal story definition.

**What I did:** Rewrote every US01–US10 `**Story.**` sentence that led with mechanism instead of
motivation (US01/US03/US04/US05/US06/US07/US08/US09; US02/US10 tightened only), and replaced each
one-line `**Intent.**` with a fixed three-field block — **Why this need exists**, **Desired user
outcome**, **When this story does not apply** — so no story implies route filtering supplies packet
security, and every unsupported/blocked story (US06 per-tenant differentiation, US10's
gateway-connection gap) still states a user-centric reason to exist. Added one shared reading note at
the top of §1 explaining the convention once instead of repeating it. US01 now names concrete drivers
Jose asked about explicitly: intentional application autonomy, fault-domain/change isolation, route
scale, tenant/overlapping address space, regulatory constraints, and security as one driver among
several (with an explicit "filtering is not authorization — NSG/firewall still apply" caveat) plus the
"don't impose this if every app needs full reachability" counter-case.

**Scope discipline:** Touched only Story sentences and Intent blocks across US01–US10, plus the new
§1 note. Left every technical reference topology, attachment point, supported/unsupported
classification, current-lab applicability line, expansion delta, validation plan, rollback, diagram
spec, citation, cost figure, and the §2/§3 matrices untouched. No diagram authored, no Azure/IaC
touched, nothing committed.

**Verdict:** No story's user value remained ambiguous. US09 is flagged (not fixed) as a different
*kind* of story — its stakeholder is the network engineering team avoiding policy drift, not an
application team experiencing a routing outcome — but its intent is not ambiguous.

**Status:** ✅ Editorial pass complete. Brief filed at
`.squad/decisions/inbox/kid-user-story-intents.md`. Awaiting Jose's read before any further US01–US10
wording changes.
---

📌 2026-08-05T13:43:07.691+02:00 — Scribe merge pass: US01–US10 intent-reframing brief recorded in decisions.md; no lab/design file staging occurred.

---

### 2026-08-08: Draft complete — Translator endpoint performance equivalence

**Lab:** `storage-endpoint-path-equivalence`  
**Artifact:** `labs/storage-endpoint-path-equivalence/blog.md`  
**Headline:** Public, service-endpoint, and private-endpoint access showed many equivalent latency/throughput dimensions, but overall equivalence remained inconclusive; persistent HTTPS connection reuse had the clearest performance effect.

Drafted the publication-ready post from the final correctness, benchmark, and sensitivity-calibration evidence. The post reports 2,400 measured benchmark requests, 1,200 warm-ups, all R1–R5 correctness gates passing, and the 25 ms positive control detecting a 23.29 ms p50 shift (95% CI 22.08–24.48 ms). It explicitly separates observable DNS/destination/effective-route differences from the unobservable Microsoft physical underlay and avoids treating inconclusive equivalence as proof of difference.

Editorial and sanitization review passed for the post text and linked final analysis artifacts. No GitHub publication occurred. Publication remains blocked only on Oracle applying `diagram-replacement-handoff.md` to the three stable diagram filenames and validating that the Storage-era labels/workload are gone.

---

### 2026-08-08: Published for review — endpoint performance equivalence

Oracle delivered four validated Translator PNGs. Embedded them in the source
`blog.md`, then published the post, diagrams, and a minimal sanitized reproduction
bundle to `erjosito/azure-networking-blog` on branch
`post/storage-endpoint-path-equivalence`, commit `1921b0d`. Opened public PR #1:
`https://github.com/erjosito/azure-networking-blog/pull/1`.

Recomputed all six headline metric rows from 60 block aggregates, verified 14/18
latency/throughput equivalence verdicts, and verified the 23.29 ms positive-control
shift with 95% CI 22.08–24.48 ms. Relative-link, Python compile, stale-label,
Azure-accuracy, and public-sanitization checks passed. Raw per-request captures and
Azure control-plane dumps were intentionally excluded. No Azure cleanup occurred.


---

### 2026-08-19: Diagram embedding fix — dual-hub-vnra-udr-transit post

**Trigger:** User reported published post contained no visible diagrams; called out the directive for readable, understandable, engaging posts.

**Root cause discovered:** The original post (PR #3, merge commit `ed11bea`) submitted four Mermaid diagram files under `assets/` and referenced them with a footer note pointing to a `diagrams/` folder. GitHub does not support Markdown transclusion or includes — separate `.md` files are never rendered inline in a README. Readers who never opened the individual asset files saw zero diagrams, only prose and tables.

**What I did:** Diagnosed the gap; wrote an updated README with all five Mermaid fenced blocks (`graph TB`, `graph LR` ×2, `graph TD` ×2) embedded directly at narrative-appropriate points:
- Topology overview → after "The Setup" intro paragraph
- Forward and return data-path → after the UDR chain step list
- Observability probe sequence → opening "The Observability Ceiling" section
- Resource dependency / cleanup boundary → in "Full Lab Evidence"

Each diagram is introduced with a brief contextual sentence. All five blocks validated: valid graph types, balanced brackets, outside HTML comments and details tags. Opened PR #5, verified MERGEABLE with no failing checks, squash-merged to main (commit `b89d88097ee40abe070e2182de404fe046c62bfa`), branch deleted.

**Lesson:** Asset files are not diagrams in the post. GitHub renders only what is directly in the README. A Mermaid block in a separate .md file under assets/ is invisible to readers. After every publication, verify inline rendering in the published README on main — not just that diagram files exist in the repo.

**Status:** Fixed. Main now contains 5 inline Mermaid fences. PR: https://github.com/erjosito/azure-networking-blog/pull/5

---

📌 2026-08-19T20:51:00+02:00 — Diagram-embedding gap fixed; team inbox note written at .squad/decisions/inbox/kid-blog-diagrams-must-be-inline.md.

---

### 2026-08-19: Reframe — dual-hub-vnra-udr-transit post (practitioner-centered)

**Trigger:** User directive: post must not center on an error the team made merely because it happened; reassess title, hook, lede, section order, and framing for external Azure Networking practitioner value.

**Old framing:** "Managed VNRA Multi-Region UDR Transit: The Silent Peering Trap" — mistake-chronology narrative. Structural spine was "What Went Wrong": investigation sequence, peering flags as the revelation of a lab error, "The Fix" as the payoff. Team-centric investigation language throughout.

**New framing:** "Azure Managed VNRA: Multi-Region Transit Design, Observability Limits, and the Two Peering Prerequisites" — practitioner design reference. Structure is: what this covers → architecture → UDR transit chain → peering prerequisites (general) → diagnosing silent failure (reusable method, lab as evidence) → observability ceiling → undocumented details → reproduction → design checklist → takeaway.

**Changes made:**
- Title changed in post README and root blog index (both updated in same PR)
- Opening rewritten from mistake-centric hook to practitioner scope statement
- "What Went Wrong" section removed; peering investigation recast as general diagnostic method
- "The Fix and Verification" removed; evidence folded into the diagnostic and prerequisite sections
- All team-centric language removed (zero instances of we/our mistake/initial validation)
- All 5 inline Mermaid diagrams preserved
- PR #6: https://github.com/erjosito/azure-networking-blog/pull/6
- Merge commit: 63982ee48d5b43c741a2ecdc6fadf8abc3333dc4

**External-value test:** Post remains fully valuable with all lab-process references removed. It documents a validated multi-region VNRA design, the exact peering prerequisites for any hub-spoke topology, a reusable diagnostic method for silent data-plane failure, and the observability ceiling specific to managed VNRA hardware.

**Lesson:** When a blog post uses a lab error as the structural center rather than the discovery method, readers who have not made the same error see a post-mortem instead of a design guide. The technical content is the same; only the framing determines external value. Always ask: is the reader's problem this article's organizing principle, or is the team's experience?

---

### 2026-08-19: Final editorial reframe — design/observability lead, peering as closing field note

**Directive (Jose):** Lead with reusable managed-VNRA design lessons and observability/diagnostics model. allowVirtualNetworkAccess must not be the headline, title, hook, or organizing thesis. Move to a short anecdote/footnote at the end. Title must foreground managed VNRA multi-region UDR transit design/observability.

**Title:** "Multi-Region UDR Transit with Azure Managed VNRA: Design Guide and Observability Model"

**What changed:**
- Title: peering flags removed entirely; design guide + observability model foregrounded
- Opening: hardware VNRA brief + two design-relevant distinguishers (UDR chain wiring; observability narrower than VM NVA); no peering flags in hook
- "Peering Prerequisites" and "Diagnosing Silent Data-Plane Failure" sections removed from article body
- New section: "Verifying Transit: TTL Invisibility as the Confirmation Signal" (design concept)
- Observability section promoted to primary mid-article position; renamed to "The Observability Model"; indirect diagnostics methodology added
- Closing field note "Field Note: Connected/FullyInSync Is Not Data-Plane Proof" (~250 words at 78% through article): JSON evidence, fix, generalizable lesson
- Root README index updated to match
- PR #7: https://github.com/erjosito/azure-networking-blog/pull/7
- Merge commit: ff0957e6c98432ab011bead680aa28568c64a48e

**Lesson:** When a technical finding has multiple dimensions (design pattern, observability model, specific gotcha), the article's organizing principle should match what readers are searching for — which is almost always the design/operational model, not the specific error. Gotchas belong as evidence, field notes, or appendices. The title, hook, and section order should serve the majority of readers who want to understand how to build and operate the technology, not the subset who have already hit the specific failure.
---

### 2026-08-22: Draft published for review — Foundry prompt-agent vs hosted-agent networking

**Lab:** `foundry-agent-prompt-vs-hosted-networking`
**Post repo:** `erjosito/azure-networking-blog`
**Branch:** `post/foundry-prompt-vs-hosted-networking`
**PR:** https://github.com/erjosito/azure-networking-blog/pull/8
**Word count:** 4,465
**Inline visuals:** 4 Mermaid diagrams (topology, egress paths, DNS chain, invocation flow)

**Headline finding:** The user-visible private-network reachability and policy experience is largely the same for both agent types (AgentSubnet, NSG, VNet peering, DNS forwarding chain). Prompt-agent tools use a data proxy; hosted-agent code uses an ephemeral Micro VM NIC. Both consume AgentSubnet addressing, obey the same VNet/NSG/DNS controls, and DNS Private Resolver SNAT hides the original agent type from dnsmasq.

**H1 status:** BASELINE ONLY — prompt-agent data-proxy path uses evidence from sibling lab (2026-08-14). `azure-ai-projects 2.3.0` AgentsOperations does not expose an Assistants API; prompt agents with HTTP Connection resources cannot be created programmatically. Explicitly noted in the post.

**H2 confirmed:** 7 hosted-agent invocations (3 REST direct, 3 AIProjectClient SDK, 1 SSE streaming) confirmed Micro VM NIC egress from AgentSubnet (192.168.0.0/24). Ephemeral source IPs change per invocation.

**H3 confirmed:** Dnsmasq log shows all VNet callers (Micro VM NIC, vm-diag) produce queries from DNSOutboundSubnet SNAT pool (192.168.3.21-25) — context-transparent by design.

**Evidence also includes:**
- NSG negative test: TCP deny on nsg-tools produced `"Error: Function failed."` while DNS still resolved (SNAT-pool source allowed separately). Proves DNS and TCP are independent failure modes.
- Client-side FC DNS failure: `[Errno 11001] getaddrinfo failed` from workstation outside VNet.

**Sanitization:** PASS — no GUIDs, no real account hostnames, no credentials.
**Render validation:** PASS — 4 inline Mermaid fenced blocks; no diagram files in assets/.
**Back-requests:** None. All evidence sufficient from committed lab artifacts.
**Ship status:** published (branch pushed, PR open; pending Jose review)


### 2026-08-22 — Morpheus diagram revision applied to PR #8

Niobe approved Morpheus's final diagram revision. Applied to blog PR #8:

- **Diagrams replaced**: 03-agent-egress-paths (318873 bytes; fixes transposed IPs and overclaimed Toolbox path), 04-dns-resolution-contexts, 06-programmatic-invocation — all four formats (PNG/SVG/excalidraw/mmd) for each.
- **Prose fixed**: §3 intro now explicitly labels diagram path 2 (hosted Toolbox) as PREDICTED/INFERRED — not tested in this lab; diagram path 1 as BASELINE; diagram path 3 as CONFIRMED.
- **Alt text corrected**: prompt baseline .49/.239 (sibling lab, no re-run); hosted REST .238/.28/.110, SDK .92/.142/.165, SSE .124 (seven observations); fourth REST attempt NSG-blocked/no src_ip.
- **Commit SHA**: 840c020. **PR #8** remains OPEN, UNMERGED at https://github.com/erjosito/azure-networking-blog/pull/8.
- Three independent diagram revision cycles: Oracle (rejected — transposed IPs, overclaimed Toolbox); Trinity (rejected — same IP issue + invocation count error); Morpheus (approved).

---

## 2026-09-30 — sap-rise-scoped-peering-fwaas (draft) + repo hygiene

**Source lab:** `labs/sap-rise-scoped-peering-fwaas`
**Target repo:** `erjosito/azure-networking-blog`
**Post folder:** `2026-09-sap-rise-scoped-peering-fwaas/`
**PRs opened:** #11 (draft — the post) and #10 (folder rename + naming convention note)
**Word count:** 2573
**Ship status:** draft (S1 data-plane validation still open; Jose to decide final publish timing)

## Learnings

- **Reframing labs that fail validation into architectural comparisons is a repeatable pattern.** When Jose asks for a post about a lab whose reference scenario isn't passing end-to-end, the right move is to pivot the headline from "look what we proved" to "here are the design options for this problem class, and here is the taxonomy of trade-offs." The gotchas the failing lab surfaced (in this case, ARS `allowBranchToBranchTraffic` and Linux runtime `ip_forward`) then become concrete evidence *within* the comparison — teaching material about how a given design silently breaks — rather than a postmortem headline. The post still ends with an honest "here's what this lab has and hasn't proven yet" section, so nothing is speculative.
- **Repo folder naming convention (`YYYY-MM-<slug>`) is now documented in the root README of `azure-networking-blog`.** Every existing folder except one already matched; the one exception (`dual-hub-vnra-udr-transit`) has been renamed to `2026-08-dual-hub-vnra-udr-transit` (2026-08 confirmed via `git log --diff-filter=A`). Future posts must follow this.
- **Separate branches/PRs for post work vs. repo hygiene.** Rename lived on `chore/rename-dual-hub-folder` (PR #10, ready for merge); the draft post lives on `post/sap-rise-scoped-peering-fwaas` (PR #11, draft). Keeps review scope clean.
- **File paths worth remembering:**
  - Blog local clone: `C:\Users\jomore\Repos\azure-networking-blog\`
  - Draft post: `2026-09-sap-rise-scoped-peering-fwaas/`
  - Source lab validation (in-progress S1): `labs/sap-rise-scoped-peering-fwaas/validation.md`
- **User preference (Jose):** default to draft PR (not direct-to-main) when the underlying lab is not yet fully validated end-to-end; flag the status clearly so he can decide publish timing.
- **PERMANENT STYLE RULE: never use em-dashes (—) in blog posts.** Use commas, periods, parentheses, or restructured sentences instead. Applies to titles, headings, and all prose, going forward, in every future post, not just this one.
- **Terminology correction:** use "subnet peering," not "scoped VNet peering" or "scoped peering," when describing subnet-scoped VNet peering (SAP RISE post, corrected 2026-09-30 after Jose flagged it in PR #12).
