# vwan-dual-er-symmetric — Lab Scope & Completion Definition (v2)
**Author:** Morpheus (Lab Director / Scope-keeper)
**Date:** 2026-06-16 (updated from v1 2026-06-15 — extended for C1+C2 sequential + autopilot directive)
**Lab:** `vwan-dual-er-symmetric` | RG: `rg-vwan-symm-103167`
**Status:** Scope locked. Completion gate updated. Sign-off **PENDING** Jose acknowledgement.

---

## 1. In-Scope Mechanisms

The blog explains ALL of the following. Each mechanism must have at least one captured evidence artifact before Kid publishes.

### Design A — Per-region isolated VPCs (described, not currently deployed)
📚 Teaching baseline. Two separate GCP VPCs, two CRs, one MCR each. Mechanism A filter lists confirmed working in `show-output/spof-before/`. **Evidence complete.**

### Design B — Single GLOBAL-routing VPC, dual CRs (built; asymmetric evidence ✅)
⚠️ Not recommended. Asymmetric routing proved (niobe-4). Three-tier evidence: control-plane + data-plane TCP timeout + AzFW log correlation (money shot). **Evidence complete.** Folder: `show-output/design-b-phase1-asymmetric-2026-06-15/`.

### Design C — Single Cloud Router, two PARTNER attachments (topology live ✅; evidence in-flight)
✅ Target design. Single CR in eu-w3, `att_a` → MCR1, `att_b_v2` → MCR2. Asymmetric baseline evidence in-flight (`niobedc`). Folder: `show-output/design-c-asymmetric-2026-06-15/`.

### Mechanism A — MCR prefix-filter lists (historical)
📚 Active in Design A spof-before. Deleted from Design B onward. **Evidence complete** (`show-output/spof-before/`).

### Mechanism B — MCR-side AS-PATH prepend (Axis-2; active)
✅ MCR1 prepends `10.50.2.0/24` 3× toward Hub1; MCR2 prepends `10.50.1.0/24` 3× toward Hub2. GCP-layer symmetry lever. Evidence bundled with C1 Niobe run (`gcp-cr-status-after-mechc1.txt` — "Mech C is Azure-only" proof).

### Mechanism C1 — vWAN Route Maps, active/active outbound (↔ MS Learn Scenario 2)
🔧 In design (trinitymc landed). Outbound route maps on Hub1 + Hub2 ER connections. AS_TRANS 23456 × 3 prepend for cross-region prefixes. Maps to MS Learn DR article Scenario 2. **Tank Phase 2 applies this.** Evidence: Niobe C1 run (4-tier methodology).

### Mechanism C2 — vWAN Route Maps, active/passive inbound + hub preference (↔ MS Learn Scenario 1)
🔧 In design (trinitymc landed). Extends C1: adds Hub2 inbound route map + `hub_routing_preference = ASPath` on both hubs. C1 Hub1 outbound map removed (subsumed). Maps to MS Learn DR article Scenario 1. **Tank Phase 3 applies this.** Evidence: Niobe C2 run (4-tier + failover test within 90s).

---

## 2. Out-of-Scope

| Item | Reason |
|------|--------|
| Design D (Linux NVA) | Megaport-unlock contingency superseded by Design C. Design C is live. |
| Any fourth design | Blog narrative capped at A/B/C arc. New design = new lab. Jose go-ahead required. |
| Global Reach | Bypasses both Azure hubs; irrelevant to firewall-symmetry story. ~$70-100/month cost adder. |
| ER bow-tie | Excluded topology pattern — S4 in manifest was the controlled break; enabling it destroys the baseline. |
| Megaport API-dependent scenarios | Jose accepted portal workflow. Programmatic MCR shutdown requires API unlock. |
| Internet-egress symmetry (`ri_policy=both`) | Different topic; deferred to a follow-up lab. |
| Wishlist #12 portal screenshots (autopilot) | Browser capture requires human operator. Deferred to Jose-on-return. |
| Wishlist #13 Mech B removed ECMP | TF change + revert risk post-C2. Defer; explicit Jose authorization required. |
| Wishlist #14 MCR1 failure Design C | C2 failover test (Step 3.4) covers this. Megaport API locked. Defer. |

---

## 3. Cost Envelope

| Layer | Component | Daily cost |
|-------|-----------|-----------|
| Azure | 2 × Azure Firewall Standard (in-hub) | ~$60 |
| Azure | 2 × ER Gateway Scale Unit + circuits | ~$24 |
| Azure | 2 × vWAN hubs + vWAN resource | ~$10 |
| Azure | 4 × B2als_v2 VMs + disks | ~$8 |
| Azure | Log Analytics (AzFW diagnostics) | ~$4 |
| Megaport | 2 × MCRs + 4 × VXCs | ~$26 |
| GCP | 2 × VMs + network egress | ~$3 |
| **TOTAL** | | **~$135/day** |

> ⚠️ **Cost forecast update (v2):** Previously estimated 3-4 additional days. With C1 + C2 both required (sequential: Tank P2 → Niobe C1 → Tank P3 → Niobe C2 → Kid draft), the realistic estimate is **5-6 additional days = $675-810 additional burn**. The autopilot directive (`copilot-directive-autopilot-three-scenarios-2026-06-16.md`) explicitly pre-approves this (~$270-405 stated there; actual may trend higher). **Flag to Jose on return if pipeline extends beyond 6 days.** The C2 vHub reprovision (~10-20 min per hub) is the longest single step; at $135/day it costs ~$1.10 in cloud dollars — not a material cost driver, acceptable for autopilot.

---

## 4. Completion Gate (v2 — extended to 14 items)

- [x] Design B asymmetric evidence captured and verdict in README — **DONE (niobe-4, 2026-06-15)**
- [x] Design C topology live (single CR, `att_a` + `att_b_v2`, both BGP UP) — **DONE (Tank Phase 1B, 2026-06-15)**
- [x] Trinity Mech C spec written (C1 + C2 both alternatives documented) — **DONE (trinitymc, 2026-06-15/16)**
- [ ] Design C asymmetric baseline evidence (niobedc 4-tier: GCP CR best-path, hub routes, TCP, AzFW KQL) — **IN FLIGHT (`niobedc`)**
- [ ] **Tank Phase 2 (C1 apply) clean** — 2 adds, 2 changes, 0 destroys; provisioningState=Succeeded — **PENDING**
- [ ] **Niobe C1 evidence pack (4-tier methodology) verdict SYMMETRIC** — BGP best-path per-prefix split, data-plane TCP success, AzFW both hubs log entries, GCP CR routes unchanged from Design C — **PENDING (post-Tank P2)**
- [ ] **Tank Phase 3 (C2 apply) clean** — 1 add, 3 changes, 1 destroy; both vHubs hub_routing_preference=ASPath, Hub2 INBOUND map Succeeded, Hub1 OUTBOUND map gone — **PENDING (post-Niobe C1)**
- [ ] **Niobe C2 evidence pack (4-tier + failover test) verdict SYMMETRIC + FAILOVER ≤90s** — steady-state BGP all prefixes via MCR1, AzFW1 active, failover test: att_a down → MCR2 active within 90s BGP hold timer — **PENDING (post-Tank P3)**
- [ ] Mechanism B (Axis-2 MCR prepend) evidence captured (bundled with Niobe C1 run — GCP CR routes identical to Design C baseline) — **PENDING (bundles with Niobe C1)**
- [ ] Kid blog draft complete (prose in all 10+§8a+§8b sections; §7 ASN-stripping claim corrected; §10 cost corrected to ~$135/day; all money shots referenced) — **IN FLIGHT (`kidblog`)**
- [ ] Morpheus scope sign-off — **THIS DOCUMENT (closes when Jose acknowledges)**
- [ ] Trinity vault backfill complete (Obsidian write pre-cleanup) — **PENDING**
- [ ] Lab teardown plan ready (Tank `cleanup.ps1` tested dry-run) — **PENDING**
- [ ] **Jose "teardown" explicit word received** — **PENDING (final gate, Phase 8)**

**Sign-off blocker count: 11 items remaining (3 items done).** Critical path: `niobedc` → Tank P2 → Niobe C1 → Tank P3 → Niobe C2 → Kid draft review-ready → Jose teardown.

---

## 5. Autopilot Risk Inventory

| Risk | Severity | Assessment | Recommendation |
|------|----------|-----------|---------------|
| **vHub hub_routing_preference reprovision (C2)** — 10-20 min per hub, expected outage | MEDIUM | Acceptable in autopilot. It's a known, documented, expected behavior. Risk is if TF apply times out without confirming provisioningState. | Tank must poll `provisioningState` before proceeding to Niobe C2. Do NOT treat apply exit code alone as success — check state explicitly. |
| **Megaport API locked — impact on P2/P3** | LOW | **Phase 2 and Phase 3 are Azure-only changes** (route maps + hub routing preference). Zero Megaport API calls required. Megaport lock does NOT block C1 or C2 apply. | Confirmed non-blocker. ✅ |
| **Reserved ASN 23456 conflict** | NEGLIGIBLE | AS_TRANS appears in private ER peering (Megaport MCR ↔ Azure vHub BGP). No real AS owns 23456. It will not propagate beyond the ER private peering BGP session. Zero real-world collision risk. | None required. ✅ |
| **Portal screenshot captures (Wishlist #12)** | LOW | Cannot be automated. | Remove from autopilot scope. Defer to Jose-on-return. |
| **Niobe C1 capture window — must precede C2** | HIGH | GCP CR routes after C1 (`gcp-cr-status-after-mechc1.txt`) must be captured BEFORE Tank Phase 3 applies C2, which changes the AS-path distribution. If Niobe misses this window, the "Mech C is Azure-only" proof is lost. | Niobe C1 run is a hard gate before Tank Phase 3. Tank must NOT proceed to P3 until Niobe signals C1 evidence pack complete. |
| **§7 ASN-stripping claim in Kid's outline** | LOW | Factual error in Kid's draft — does not affect running lab. | Kid corrects before publish. Trinity adds one-line annotation in design.md §4. |

---

## 6. Teardown Trigger

Tank receives cleanup green light when **ALL** of the following are true:

1. Niobe C2 evidence pack complete and committed (failover test verdict = PASS, reconvergence ≤90s).
2. Kid's blog draft committed to `labs/vwan-dual-er-symmetric/blog/` with all money shots referenced (prose complete; `[EVIDENCE PENDING]` placeholders replaced).
3. Trinity vault backfill committed (Obsidian write confirmed).
4. Jose says **"teardown"** or **"cleanup"** explicitly (Phase 8 protocol — Morpheus does NOT unilaterally authorize).

At current burn rate (~$135/day), every idle day post-condition-1 costs ~$135 with no new evidence or blog value. Jose should be prompted immediately once conditions 1-3 are met.
