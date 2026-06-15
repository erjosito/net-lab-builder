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

**Schedule ID #1** (1-day hard max, 7-day debounce = 1/week cadence)  
**Mode-collision guard**: scout skipped if actively drafting or in pre-gate review

---

## Archived Details

Full narrative, factual corrections table, and scout mechanics preserved in history-archive.md (2026-06-15).

---

📌 **Current status (2026-06-16T00:40:00Z, per Scribe):** Pre-gate editorial review complete. Awaiting Morpheus S4 perturbation alignment decision and Trinity editorial feedback on Mech C cost implications (~$270-405 approved; realistic ~$675-810) before lab deploy authorization.