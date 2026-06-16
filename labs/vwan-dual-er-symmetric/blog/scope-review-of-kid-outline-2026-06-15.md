# vwan-dual-er-symmetric — Morpheus Scope Review of Kid's Blog Outline
**Author:** Morpheus (Lab Director / Scope-keeper)
**Date:** 2026-06-16 (v2 — full review replacing placeholder)
**Lab:** `vwan-dual-er-symmetric`
**Review target:** `labs/vwan-dual-er-symmetric/blog/outline-2026-06-15.md`
**Status:** REVIEWED. 2 ❌ (must-fix before publish), 5 ⚠️ (fix before evidence run or before publish). No scope creep detected. Verdict: **GO-WITH-CAVEAT.**

Key: ✅ In-scope/evidence-anchored | ⚠️ Fix required (dispatch named) | ❌ Must-fix (factual error)

---

## §1 — Opener ✅

Tight. Opens with the verbatim MS Learn disclaimer, immediately drops the AzFW log correlation. Two evidence files (`desb/11-azfw1-kql-results.txt`, `desb/09-tcp-a-to-b-x5.txt`) both exist on disk. Diagram is aspirational — acceptable at outline stage.

**Niobe note:** Satisfied by existing Design B evidence. No new capture needed.

---

## §2 — Official guide summary ✅

Appropriately brief. No evidence file required (correct).

**Minor flag for Kid (editorial):** "Last major update pre-vWAN route maps" is unfalsifiable without a date. Add the MS Learn page's last-reviewed date — keeps the "every claim must be falsifiable" mandate.

---

## §3 — What the lab models ✅

One evidence file (`design-c-phase1b-2026-06-15/README.md`) exists on disk and path is exact. Good topology bridge from article to lab. No scope creep.

---

## §4 — Blind Spot #1: Stateful AzFW ✅

Strong. Four evidence files all from `desb/`, all on disk:
`08-cr-b-status.txt` ✅ · `03-er1-advertised.txt` ✅ · `11-azfw1-kql-results.txt` ✅ (money shot) · `12-azfw2-kql-results.txt` ✅

**Note:** `cr_onprem_b` in `08-cr-b-status.txt` was removed in Design C Phase 1B. Blog text already labels this as Design B topology state — correct as-is. No new evidence needed.

---

## §5 — Blind Spot #2: No iBGP at partner CE ⚠️

Two evidence files both 🔄 in-flight (niobedc). Claim is correct and pedagogically the sharpest insight in the post.

**Issue — naming inconsistency:** Outline uses `desc/cr-status.txt` and `desc/tcp-spoke1-vmb.txt`. Wishlist uses `cr-routes-before-mechc.txt` and `tcp-spoke1-to-vmb.txt`. Convention doc mandates `gcp-cr-status-before-mechc.txt` and `data-spoke1-to-vmb-tcp-01.txt`. **Niobe must use the convention-doc names when committing files; Kid updates §5 references after files land.**

**Dispatch:** niobedc (already running). ~0 additional agent-hours. Naming alignment only.

---

## §6 — Blind Spot #3: vWAN Route Maps ⚠️

Good framing. Mech C1 ↔ Scenario 2 (active/active) / Mech C2 ↔ Scenario 1 (active/passive) confirmed correct against Trinity §4 spec.

**Issue:** Evidence listed as `design.md §4` — that is a design document, not a show-output artifact. Blog mandate requires captured evidence files. Replace with:
- After Tank Phase 2 + Niobe C1: `mechc1-active-{date}/fw-azfw1-kql-01.txt` + `fw-azfw2-kql-01.txt`
- After Tank Phase 3 + Niobe C2: `mechc2-active-{date}/fw-azfw1-kql-01.txt` + `fw-azfw2-kql-01.txt`

**Dispatch:** Kid updates §6 table after evidence runs land. No new agent work.

---

## §7 — Reserved-ASN trick ⚠️

AS_TRANS 23456 rationale confirmed correct (IANA-reserved, 2-byte, not private, not Azure-reserved — per Trinity §4.1).

**Factual flag:** The claim *"vWAN Route Maps strip the reserved ASN from advertisements propagated further"* is **not confirmed by Trinity's spec and is likely incorrect.** Per §4.1, the OUTBOUND map adds 23456×3 before the prefix exits the Azure hub toward the MCR. MCR1 then re-advertises to GCP router_a prepending its own ASN — router_a sees the full `65001 23456 23456 23456 12076` path and uses it for best-path selection. AS_TRANS stays visible at the GCP layer; that is precisely how the mechanism works. If Azure stripped it, Mech C1 would be non-functional.

**Required fix (Kid):** Remove "stripping" claim. Correct statement: *"AS_TRANS 23456 stays in the BGP path all the way to the GCP Cloud Router — that's the whole point. Anyone reading `gcloud compute routers get-status` immediately recognises it as a synthetic engineering prepend."* **Trinity to confirm in one-line §7 annotation in design.md. No new evidence needed.**

---

## §8a — Mech C1 (active/active) ✅ with one gap

Correctly maps to MS Learn Scenario 2. Four future evidence files clearly labeled.

**Gap:** The proof that "Mech C is Azure-only" — `mechc1/cr-routes-after-mechc1.txt` (wishlist row #8) — is absent from §8a's table. This is the critical GCP CR snapshot showing routes are identical before/after C1. Kid must add to §8a:

| File | Caption |
|------|---------|
| `mechc1-active-{date}/gcp-cr-status-after-mechc1.txt` | GCP CR routes: IDENTICAL to Design C — Mech C1 is Azure-only |

---

## §8b — Mech C2 (active/passive) ⚠️

Correctly maps to MS Learn Scenario 1. Three future files. Active/passive framing confirmed against Trinity §4.2.

**Gap:** §8b omits the **failover test evidence** (Trinity §4.5 Step 3.4: att_a BGP down → router_a reconverges within 90s → AzFW2 active). Without this, the blog cannot substantiate "active/standby." Kid must add:

| File | Caption |
|------|---------|
| `mechc2-active-{date}/gcp-cr-status-failover.txt` | att_a down: all Azure prefixes route via MCR2 (7-hop) within 90s |
| `mechc2-active-{date}/data-spoke1-to-vmb-tcp-failover.txt` | TCP succeeds via standby path post-failover |

**Dispatch:** Niobe C2 run (post-Tank Phase 3). ~1 additional agent-hour. Already planned in Trinity §4.5. No extra cloud cost.

---

## §9 — What the article still gets right ✅

Tight, no evidence needed. The "connection weight does NOT fix the AzFW drop" observation is correct and important.

**Minor:** Kid should add one sentence explaining *why* (connection weight governs Azure inbound preference, not GCP's return path routing — the asymmetry lives at the GCP BGP layer, which connection weight cannot reach).

---

## §10 — Reproduce it ❌

**Factual error: The cost claim "~$8–12/day" is wrong by an order of magnitude.**

The lab runs at ~$135/day (2× AzFW Standard ~$60, 2× ER Gateway ~$24, vWAN hubs ~$10, VMs ~$8, Log Analytics ~$4, Megaport ~$26, GCP ~$3). A reader trusting "$8-12/day" and deploying will receive a $135/day bill. This is a reader-harm level error.

**Required fix (Kid):** Replace cost claim with: *"Full lab cost: ~$135/day. The two Azure Firewall Standard instances in secured hubs (~$60/day combined) are the dominant line item — and they're the point of the lab. A stripped variant without AzFW cannot reproduce the stateful-drop finding."*

**Secondary:** Verify that `docs/troubleshooting-commands-linux.md §11 Pattern A` exists before publish. If not, remove the reference.

---

## Wishlist — Row-by-Row

| # | Verdict | Issue |
|---|---------|-------|
| 1 Design B money shot | ✅ | Files on disk, names match |
| 2 Design B control test | ✅ | File on disk |
| 3 Design C async baseline | ✅ | niobedc in-flight; use wishlist names as canonical |
| 4 GCP CR best-path | ⚠️ | Name should be `gcp-cr-status-before-mechc.txt` per convention doc |
| 5 Hub effective routes | ⚠️ | Names should be `ctrl-hub1-effective-routes.txt` / `ctrl-hub2-effective-routes.txt` |
| 6 `ss -tn SYN-SENT` | ✅ | High value, zero extra cost. `data-vm-spoke1-ss-syn-sent.txt`. **Add to niobedc active run now.** |
| 7 Mech C1 TCP fixed | ✅ | Four future files, correctly labeled. `{date}` resolves at Niobe C1 run time |
| 8 GCP CR after C1 | ✅ | **CRITICAL** — must capture before C2 applies. `gcp-cr-status-after-mechc1.txt` |
| 9 Hub1 routes after C1 | ✅ | `ctrl-hub1-effective-routes-after-c1.txt` |
| 10 Mech C2 TCP fixed | ✅ | Add failover pair (see §8b gap) |
| 11 Hub1 routes after C2 | ✅ | `ctrl-hub1-effective-routes-after-c2.txt` |
| 12 Portal screenshots (PNG) | ⚠️ | **Cannot be autopiloted.** Browser capture requires human operator. Defer to Jose-on-return. Remove from autopilot scope. |
| 13 Mech B removed ECMP | 🟡 | Nice-to-have. Requires TF change + revert. **Do NOT run during autopilot** — revert risk if C2 baseline is live. Defer post-C2, explicit Jose authorization required. |
| 14 MCR1 failure | 🟡 | C2 failover test (Step 3.4) covers this implicitly. Megaport API locked = can't gracefully shut MCR. Defer. |

---

## Evidence-Naming Convention ✅

Scheme is clean, greppable, and correctly scoped (Design C onward; Design B names preserved). Approved as-is.

**Morpheus addition:** Add `data-spoke1-to-vmb-tcp-failover` and `gcp-cr-status-failover` to the canonical probe names in the convention doc for C2 failover captures.

---

## Money Shots Completeness

| Money shot | Status |
|-----------|--------|
| `desb/11-azfw1-kql-results.txt` — Blind Spot #1 | ✅ on disk |
| `desc/gcp-cr-status-before-mechc.txt` — Blind Spot #2 | 🔄 niobedc |
| `mechc1-active-{date}/fw-azfw1-kql-01.txt` + `fw-azfw2-kql-01.txt` — Blind Spot #3 C1 | 📋 Tank P2 → Niobe C1 |
| `mechc2-active-{date}/fw-azfw1-kql-01.txt` + `fw-azfw2-kql-01.txt` — Blind Spot #3 C2 | 📋 Tank P3 → Niobe C2 |

All four achievable within the approved autopilot pipeline. No new scope.

---

## Editorial Completion Criteria for Kid

Draft is review-ready when:

1. All 10 sections + §8a + §8b have **prose**. Sections with future evidence may use `[EVIDENCE PENDING — {file}]` placeholders.
2. Every claim references an **on-disk evidence file** (path from repo root). No unanchored claims.
3. **MS Learn cross-references explicit in:** §1 (verbatim quote), §2 (scenario names), §6 (mapping table), §8a ("This is Scenario 2, live"), §8b ("This is Scenario 1, live").
4. **§7 ASN-stripping claim corrected.**
5. **§10 cost figure corrected** to ~$135/day with context.
6. **§8a has `gcp-cr-status-after-mechc1.txt`** reference (Azure-only proof).
7. **§8b has failover test evidence** references.
8. Pull-quote or hero-image candidate identified: §4 (AzFW log correlation) and §8a/§8b (before/after Hub1 effective-routes showing the prepend flip).

**Kid may commit a first prose draft with §8a + §8b as `[EVIDENCE PENDING]`** — this unblocks Jose's structural review while the autopilot pipeline runs. Do not wait for all four money shots before committing prose.

