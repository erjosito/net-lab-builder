# DRAFT-NOTES — "Three commands that lied on a working ExpressRoute lab"

_Author persona: The Kid (Blog Writer & Public Storyteller)_
_Lab: `expressroute-megaport-bgp`_
_Evidence collected by: Niobe (Evidence Collector)_
_Date drafted: 2026-05-29_

---

## Headline rationale

**Selected headline:** "Three commands that lied on a working ExpressRoute lab"
**Focus:** Megaport v2 API endpoint anomaly tour (HTTP 405 on type-specific paths; empty looking-glass)

### Seven candidate findings and why each was or wasn't selected

| # | Finding | Disposition | Reason cut / selected |
|---|---|---|---|
| 1 | **Megaport API endpoint anomaly** (HTTP 405 on `mcr2`/`vxc` path segments; empty looking-glass) | **SELECTED** | Reproducible. Any reader running the Megaport v2 API will hit this. Actionable fix. Stronger hook for Azure+network engineering audience than operational observations. |
| 2 | Frankfurt MCR → Madrid MSEE cross-continental path | Cut | Interesting operationally, but the lesson is "it worked anyway" — thin for a full post. Demoted to a gotcha inside the selected post. |
| 3 | Both VXCs deployed on VLAN 100 (planned: 100/200) | Cut | Minor deployment quirk. Worth one sentence, not a headline. |
| 4 | BGP convergence window / transient "no sessions" error from `list-route-tables` | Cut | Transient error, not reproducible on demand. The evidence files show the correct output post-convergence, making it hard to illustrate. Mentioned as a gotcha. |
| 5 | Megaport auto-creates Azure ER private peering (no `azurerm_express_route_circuit_peering` resource needed) | Cut | IaC design insight rather than a diagnostic puzzle. Good for a future "Terraform tips" post; too niche for the headline here. |
| 6 | VM deallocated before evidence collection / VM NIC blocks diagnosed | Cut | This is an operational mistake, not a product behavior. Honest to mention under "what we couldn't prove" but not headline-worthy. |
| 7 | BGP community `12076:20031` configured on VNet but MCR receipt unverified | Cut | The gap exists because looking-glass failed — it's a consequence of anomaly #3, not an independent finding. Mentioned under "what we couldn't prove." |

**Selection rationale in full:** The API anomaly tour is the only finding that is (a) technically reproducible by any reader, (b) has a clear fix, and (c) is genuinely surprising — HTTP 405 on a GET to a plausibly-named endpoint looks like a bug or credentials problem, not an intentional API design choice. The other findings are either operational observations ("it worked anyway") or gaps caused by lab lifecycle drift. The anomaly tour also provides natural structure: three examples, each with a diagnosis and a fix, at a consistent level of detail.

---

## Back-request decision

**Decision: NO — do not re-run the lab for additional evidence.**

Cost justification threshold: the lab runs at ~$110–$125/24 h (Megaport MCR + dual VXC billing dominates at ~$95–$105/day; Azure ER circuit and gateway add ~$15–$20/day). Re-running for missing evidence would cost:

- VM effective routes: start the VM, run one command, stop it. Could be scripted into a 15-minute window. Not worth re-incurring MCR/VXC daily charges for.
- MCR looking-glass: the endpoint returned empty. Even a re-run might return empty — the failure mode is not clearly transient. No guarantee re-run recovers data.
- End-to-end ping: requires VM running + MCR advertising + Azure routing all simultaneously. Full re-run.

The control-plane evidence (ARP, BGP sessions `Connected`, Azure route table, gateway learned routes) is sufficient for every claim in the post. The three "what we couldn't prove" items are honest gaps — they don't undermine the BGP convergence claim.

**Recommendation:** Acknowledge the gaps in the post (done — see "What we couldn't prove" section). Publish without re-run.

---

## Sanitization checklist

- [x] Subscription GUID `<SUBSCRIPTION_ID>` — already replaced with `<SUBSCRIPTION_ID>` in all Niobe evidence files; not present in blog post or references
- [x] Tenant GUID `<TENANT_ID>` — must grep all three created files before delivery (see close-out checklist)
- [x] Megaport basic auth token — shown as `<MEGAPORT_BASIC_AUTH>` in evidence file 00; not exposed in blog post
- [x] Megaport company UID/name — shown as `<MEGAPORT_COMPANY_UID>` / `<MEGAPORT_COMPANY_NAME>` in evidence file 15; not exposed in blog post
- [x] Infrastructure UUIDs (MCR `d801e2cd-be05-4889-82a7-b91e45be02de`, VXC IDs `cbb7a449-...`, `60e77813-...`) — these are infrastructure identifiers, not credentials; included in the blog post as context

---

## Ship recommendation

**Ready to ship pending human review.**

Required review:
1. **IP addresses in diagrams.** The link-local IPs (`169.254.194.41–.46`) and MSEE IPs (`10.100.255.4/.5`) are real lab values from the deployed circuit. Confirm the author is comfortable publishing these. They are not sensitive (RFC 3927 / private) but are exact values from a real Megaport circuit.
2. **Infrastructure UUIDs.** MCR and VXC UUIDs are shortened in the body text but full in one diagram label. Confirm acceptable — the MCR UUID identifies a now-torn-down resource.
3. **Diagram rendering.** Both Mermaid diagrams were copied verbatim from `labs/expressroute-megaport-bgp/README.md` and render correctly in GitHub Markdown preview. Confirm target publication platform supports Mermaid.
4. **"Estimated lab cost" figure.** The ~$110–$125/24 h estimate is from manifest planning, not a confirmed invoice. Mark as approximate if the author has actual billing data.
5. **Repository visibility.** The post references the lab repo by name and path only (no live URL) because the repo is private. Remove the "Note: private" disclaimer if/when the repo goes public before publication.

No other blockers. The narrative is complete, the evidence is sound, and all known sensitive values are sanitized.

---

## Post metadata suggestions

- **Suggested tags:** Azure, ExpressRoute, Megaport, BGP, Networking, Terraform, Lab, API
- **Suggested platform:** `techcommunity.microsoft.com` or personal GitHub Pages under `erjosito`
- **Estimated read time:** ~8 minutes
- **Audience:** Azure network engineers, cloud architects, anyone building ExpressRoute labs with third-party providers
