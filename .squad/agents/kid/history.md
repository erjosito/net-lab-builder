# 📝 The Kid - History

## Current Status

**Role:** Blog Writer & Public Storyteller  
**Publishing target:** github.com/erjosito/azure-networking-blog  
**Last session:** 2026-09-30, SAP RISE baseline verification + Design B live test

---

## 2026-09-30 Session

**What I did:**
1. Analyzed Niobe's MSEE evidence showing baseline /27 subnet claim was false (only hub /16 advertised)
2. Corrected design.md with real evidence (commit 72751ca on main)
3. Tested Design B (summarizedGatewayPrefixes) live via REST (CLI command doesn't work against current typed model)
4. Updated blog post (PR #15) with corrected baseline and Design B findings
5. Merged PR #15 to azure-networking-blog (commit 286f22c)

**Key findings:**
- Documented design assumptions must be evidenced before repeating in published work
- z network vnet update --set properties.summarizedGatewayPrefixes=... doesn't work; REST PUT is the workaround
- Design B phantom route behavior confirmed live with real MSEE data

**Permanent rules:**
- No em dashes in blog posts (commas, periods, parentheses, or restructuring instead)
- Use "subnet peering" terminology (not "scoped VNet peering")
- Verify CLI commands against installed version; REST is fallback for newer ARM properties

**Commits landed:**
- net-lab-builder: 72751ca, 55ffea5
- azure-networking-blog: 286f22c (PR #15 merge)

**Pending:**
- Design A regression is open (BGP sessions Connected but routesReceived: 0)
- Lab S1 validation still in progress

---

## Earlier Sessions

Detailed history of 2026-05-29 through 2026-08-22 work archived in history-archive.md.

## Learnings

- 2026-09-30: Confirmed a real evidence gap for the successful "after option-1 fix" checkpoint. The evidence tree contains a genuine ER Gateway learned-routes capture (`s1-dataplane-fix-20260929T163250Z\13-ergw-learned-routes-final.json`), but no genuine post-fix MSEE route-table capture and no genuine post-fix ER Gateway advertised-routes capture.
- 2026-09-30: Final file mapping for the Lab evidence rewrite was baseline `s0-baseline-msee-01/02/03/04`, option 1 `s1-dataplane-fix-20260929T163250Z\13-ergw-learned-routes-final.json` plus an explicit missing-capture note, and option 2 `s2-designB-03/04/05/07`.
- 📌 Team update (2026-09-30T11:12:07Z): Rewrote "After the option-1 fix" MSEE evidence subsection in azure-networking-blog PR #17 using real s1-msee-01/02/03 + s1-reconcile-01/02/03/04 data, explained learned-vs-advertised route distinction, resolved stale caveat, preserved CE-ping issue, merged PR #17 to main. Evidence files committed to net-lab-builder (commit 9deef73, pushed). — Scribe
