# 📝 The Kid — History

## Current Status

**Role:** Blog Writer & Public Storyteller  
**Publishing target:** github.com/erjosito/azure-networking-blog  
**Last session:** 2026-09-30 — SAP RISE baseline verification + Design B live test

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
- No em-dashes in blog posts (commas, periods, parentheses, or restructuring instead)
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
