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


