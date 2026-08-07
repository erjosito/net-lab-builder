# Project Context

- **Owner:** Jose Moreno
- **Project:** net-lab-builder — build, document, and tear down ephemeral Azure Networking labs
- **Stack:** Azure (CLI, PowerShell, Bicep, Terraform); Megaport (ExpressRoute MCR + VXC); Linux/Windows VMs
- **Created:** 2026-05-28
- **Role:** Lead / Architect — own requirements, region & SKU selection, cost guardrail, lab lifecycle (8 phases: Analyze → Design → Manifest → Approval → Deploy → Execute → Report → Approval → Cleanup)

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

📌 2026-05-28 — Project initialized. Charter integrated with azure-lab skill canonical methodology. Two approval gates enforced (post-manifest, pre-cleanup) per routing rule #12. No A-series / B-series workload VMs; diagnostic plumbing may use Standard_B1s. Cost-first region selection.

---

📌 Team update (2026-05-29): Phase 3.5 governance close — Kid cast (blog-writer 📝), lab #1 blog published, Tank cleanup complete (19/19 resources), squad v0.9.5. Inbox swept (13 decisions → decisions.md).

---

📌 2026-06-15 — Lab #2 scoped: `vwan-dual-er-symmetric`. Manifest written at `labs/vwan-dual-er-symmetric/manifest.md`; decision filed at `.squad/decisions/inbox/morpheus-vwan-dual-er-symmetric-manifest.md`. Awaiting Jose's gate #12 #1 approval.

**Symmetry design rationale.** Three independent levers stacked so symmetry is structurally — not policy-dependently — enforced:
1. `er_bow_tie=no` keeps each ER GW connected to exactly one circuit, so each hub advertises only its own region's spoke prefixes outbound to its own circuit. Egress direction symmetric by topology.
2. Two separate GCP VPCs (one per region), no inter-VPC peering, no shared Cloud Router. Each VPC's prefix reaches Azure via exactly one MCR → one circuit → one hub. Ingress direction symmetric by topology.
3. `ri_policy=private` on both hubs ensures every spoke flow passes through its hub's AzFW; cross-region spoke↔spoke transits both hub firewalls in opposite order, still symmetric per 5-tuple.

**Why I ruled out the alternatives.**
- **Global Reach (GR):** would bypass both Azure hubs entirely (circuit-to-circuit at MSEE). Irrelevant to a firewall-symmetry lab and a $70-100/month-per-circuit-pair cost adder for nothing. Documented decline; reference script line 41 / function lines 2337-2342 was the trigger to evaluate.
- **ER bow-tie:** standard ER HA pattern (Region A's spokes still reach on-prem if Circuit1 fails). But it creates a second BGP path per prefix into each hub → Azure best-path may flip → return packets land on wrong hub → stateful drop. This is the failure mode S4 captures; turning bow-tie ON is the controlled break.
- **`ri_policy=both`:** adds internet-egress symmetry as a *second* topic in the same lab. Internet-egress symmetry is its own problem (NAT IP affinity, SNAT, public-route propagation). Decided one topic per lab; defer internet-egress to a follow-up.
- **Single secured hub + single routed hub** (cost-reduction variant): saves ~$30/day but kills S2 (Spoke3 ↔ GCP-B traffic has no Hub2 firewall to count hits on) and S3 (cross-region flow only sees one firewall). Documented in §6 as a not-recommended cost-cut.

**Region / SKU surprises.** None — both `swedencentral` and `northeurope` had `Standard_B2als_v2` in catalog with no restrictions for the caller's subscription (probe 2026-06-15). Earlier-probe gotcha: when I asked for `[?name=='Standard_B2als_v2']` in northeurope, the targeted query returned empty even though `--size Standard_B2` enumeration showed it present — Azure CLI list-skus appears to return inconsistent results between the two query shapes intermittently (lots of `WARNING: Incomplete download`). Lesson: always use `--size <prefix>` filter when probing a specific SKU; the unfiltered query is fragile in northeurope.

**Cost.** Lab #2 lands at ~$135/day (+$15–25 over lab #1) — formally flagged above $50/day per rule #7; full approval-package in manifest §9 surfaces this clearly. AzFW Standard in two hubs is the single biggest line ($60/day) and is non-negotiable for what the lab is trying to teach.

**Megaport MCR-market lesson from lab #1 carried forward.** Lab #1 deployed an MCR in Frankfurt FR5 despite ordering against the Madrid ER PoP. The design therefore does not pin MCR markets — Tank/Megaport pick at order time and Niobe records actuals. ER peering location (Stockholm + Amsterdam preferred; Frankfurt + Dublin fallback) is what we lock.

**Process learning.** First lab where I structured the manifest around a single design constraint (symmetry) rather than a feature exploration (BGP behaviour). The constraint forced clearer failure-mode definition (S4 is the lab's reason for existing); the success-only scenarios (S1, S2, S3) are essentially the "control" against which S4's drop is meaningful. Recommend this pattern for future labs where the headline is "this is the wrong way it usually breaks."

---

📌 Team update (2026-06-15): Design C directive captured. morpheus-vwan-dual-er-symmetric-manifest.md filed, Design C specification (trinity-4 §3.1-§3.7) complete + 4 gate questions documented in decisions.md. Phase 1 manifest design fan-out complete; Design B asymmetric routing proof 🔴 documented (niobe-4). All subordinate phases (Trinity spec, Tank Phase 1A IaC, niobe validation planning) unblocked pending Jose's Megaport + Q1-Q4 gate answers.

---

📌 2026-06-15 — Lab #3 scoped: `msee-hairpin-hns-vwan-ipv6`. Lab card at `labs/msee-hairpin-hns-vwan-ipv6/lab-card.md`. Awaiting Jose's A/B/C gate before Stage 2.

**MSEE hairpinning mechanics (researched for lab #3).** MSEE hairpinning between two Azure environments works as follows: ER GW A advertises its VNet/spoke prefixes to the MSEE over the Azure-side BGP session on Circuit 1. MSEE reflects those routes to Circuit 2's Azure-side session (ER GW B). No customer-side (on-prem) BGP session on the ER Direct port is required for this Azure-to-Azure path. Customer-side BGP only matters if a physical on-prem device needs to learn routes. **This is the technical basis for Path A (ER Direct without a customer-side router) being viable.**

**ER GW settings for MSEE hairpinning.** Three non-default settings must be configured:
1. HnS ER GW: `allowVirtualWanTraffic=true` — enables the GW to receive routes from vWAN via MSEE
2. HnS ER GW: `allowRemoteVnetTraffic=true` — enables route propagation from remote peered VNets
3. vWAN ER GW: `allowNonVirtualWanTraffic=true` — enables the vWAN ER GW to accept routes from non-vWAN networks via MSEE. These are silent-fail settings — hairpin will not work without them, and Azure gives no obvious error.

**IPv6 ER private peering.** IPv6 requires a separate BGP session on the same ER circuit private peering. Must configure: IPv6 primary /126 and secondary /126 peering subnets, and the ER GW's VNet must be dual-stack. ULA (`fd00::/8`) is sufficient for Azure-to-Azure labs with no real on-prem.

**ER Direct + no on-prem router — viability.** Zero ER Direct ports provisioned in Jose's subscription today. Provisioning a new 10 Gbps port ($47/day) + 2 sub-circuits is viable and provisions in minutes (vs. Megaport partner weeks). Cost exceeds $50/day flag ($65–75/day) but 6h total runtime caps bill at ~$18.

**Single-region constraint.** MSEE hairpinning is only possible if both ER circuits connect to the **same MSEE** (same peering location). Single-region (`swedencentral` → Stockholm ER PoP) enforces this structurally. Multi-region design would require Global Reach to route between MSEEs — a different (and more expensive) mechanism.

**KV inventory (lab #3).** Vault `platform-secrets-1138` confirmed: `default-password`, `megaport-api-key`, `megaport-api-secret`. Only `default-password` needed for Path A (no Megaport). Password auth applies (no `vm-admin-ssh-public-key`).

---

📌 2026-06-15 — Lab #3 Stage 2 manifest complete: `labs/msee-hairpin-hns-vwan-ipv6/manifest.md`. Awaiting Phase 4 deploy gate from Jose.

**Resource count:** 29 (28 named + 1 RG). Long pole: ER GW pair in parallel (~20-45 min). Total deploy: ~45-60 min.

**ER Direct port sub-circuit pattern.** Both ER circuits are sub-circuits on the same 10 Gbps ER Direct port (`azurerm_express_route_circuit` with `express_route_port_id`). VLAN tags must be unique per circuit (100 for HnS, 200 for vWAN). The port encapsulation is QinQ. This is different from provider circuits which don't require explicit VLAN tagging in Terraform.

**IPv4+IPv6 peering on same circuit resource.** `azurerm_express_route_circuit_peering` supports IPv6 via the `ipv6` block within the same resource — it is NOT a separate Terraform resource. The IPv6 primary/secondary peering subnets (/126) and the IPv4 primary/secondary (/30) are both configured in one `azurerm_express_route_circuit_peering` resource.

**azurerm GW toggle coverage risk.** `allow_virtual_wan_traffic` and `allow_remote_vnet_traffic` on `azurerm_virtual_network_gateway`, and `allow_non_virtual_wan_traffic` on `azurerm_express_route_gateway`, may need azapi fallback if not exposed in current azurerm provider version. Tank should verify before writing IaC. These are silent-fail properties — hairpin works superficially until route propagation is traced and fails.

**Deploy sequence note.** vHub ER GW (`azurerm_express_route_gateway`) requires the vHub to exist first (hard `depends_on`); vHub requires vWAN to exist first. The parallel chains in Step 5-6 must respect this ordering. HnS ER GW and vHub ER GW can provision in parallel since they have independent `depends_on` trees.

**Cleanup blockers documented.** ER circuit delete blocks if any `azurerm_virtual_network_gateway_connection` or `azurerm_express_route_connection` references it. ER Direct port delete blocks if any circuit references it. These are the two most common cleanup-order failures; they're now in the manifest §3 cleanup sequence.


📌 Team update (2026-06-15T23:52:53+02:00): **ER Direct 45-day free port window** — Jose directive captured and filed to decisions.md. Azure ER Direct ports include a 45-day free provisioning window (covers cross-connect installation lead-time). For labs <45 days, port cost is \\\. Lab #3 Path A cost estimate corrected from ~\/day to ~\-35/day (well within \/day guardrail). Morpheus owns cost guardrail (routing rule #7) + Phase 4 cost gate; must factor the 45-day free window into every ER Direct cost estimate going forward. Trinity to backfill this fact into the Azure Networking vault during Phase 3.4.



---

📌 2026-08-03 — Lab #3 scoped: `dual-hub-hubless-region-ars`. Stage-1 lab card locked at `labs/dual-hub-hubless-region-ars/manifest.md` (~6.8 KB — mild overrun on the ≤5 KB budget because the mandated content list this time was atypically dense: mechanism, scope in/out, four regions with resource counts, address plan, subnet plan, ASN plan, 10 BGP sessions, full peering + UDR + route-policy split, connection-model decision with justification, secrets flow, five pass/fail scenarios, deployment duration, defensible daily cost breakdown, cleanup boundary, four `## Designs studied` entries, six MS Learn URLs, and lock statement). This is a **new Stage-1 card, not a revision of the rejected initial review** (`morpheus-dual-hub-design-review.md` from 2026-08-03T11:16 stays untouched); the user-approved design pivoted the topology after Trinity's before-DR reviewer pass and the four subsequent locked-intent corrections in this session's prompt.

**Design gist.** One workload-aligned Azure Route Server (ARS) VNet in `polandcentral` (hubless) is the shared BGP control-plane extension for many spokes toward two remote regional hubs `swedencentral` and `switzerlandnorth`, with a simulated on-prem in `norwayeast`. Set-C spokes are triple-peered (Poland ARS VNet + hub1 + hub2) with no transit flags on the two hub peerings — those exist only so the fabric can deliver packets to the NVA next-hop IP the Poland ARS advertises. Both NVAs multi-hop-eBGP into the Poland ARS across direct global VNet peerings; three-way route-policy split (Δ1 65515 strip on both NVAs, Δ2 NVA2 prepends its ASN on set-C prefixes toward hub2 ARS, Δ3 inbound ARS route map preview on Poland ARS↔NVA2 for default-route best-path). Reversible hub1 outage injection via wrong PSK + `vpn-connection reset` on both hub1↔on-prem halves + `systemctl stop bird` on NVA1.

**Regions/SKUs.** Preflight-locked: `swedencentral` hub1, `switzerlandnorth` hub2 (substituted for `germanywestcentral` — entire B-series ladder NOT_FOUND in catalog), `polandcentral` hubless workload, `norwayeast` on-prem sim (substituted for `francecentral` — entire B+D ladder `NotAvailableForSubscription`). All 6 VMs `Standard_B2ts_v2` Ubuntu 22.04 Std SSD no VM PIP, fallback `Standard_B2ls_v2`, every region live-validated (deployment IDs recorded in preflight). 9 Standard PIPs = 3 Route Servers × 1 (SDN mgmt requirement per ARS FAQ) + 3 VPN GW active-active × 2. 10 BGP sessions total.

**Connection model.** V2V (VNet-to-VNet) connection pairs between the three Azure VPN GWs. Same PSK/IPsec/BGP surface as S2S+LNG, no `LocalNetworkGateway` object bookkeeping, and — crucially for S2/S3 — fault-injectable via `az network vpn-connection shared-key update` + `vpn-connection reset` on either half. 4 connection objects total (hub1↔on-prem mirror pair + hub2↔on-prem mirror pair). Documented escalation path to S2S+LNG if Phase-0 exposes hidden route/PSK behaviour.

**Cost.** Anchored against Azure Retail Pricing MCP (2026-08-03, USD, PAYG): 3×VpnGw1 AA $27.36/day + 3×ARS Basic $32.40/day + 6× `B2ts_v2` Linux $1.55/day + 4× VPN S2S conn $1.44/day + 9× Std PIP $1.08/day + misc ≈$2/day = **baseline ~$66/day**; **~$72/day** with Δ3 route-map SKU upgrade + 2× NVA-connection-with-route-maps meters active. **Rule #7 (~$50/day guardrail) BREACHED.** Explicitly flagged to Jose in the lab card; drivers are 3× ARS ($32/day) and 3× VPN GW ($27/day), neither reducible — Basic VPN GW has no BGP/active-active, and Basic is the entry ARS SKU. Route maps stay **PUBLIC PREVIEW** and first activation triggers a **~30-min one-time ARS upgrade** on the Poland ARS (per ARS FAQ) — baked into the deployment-duration estimate.

**Route policy — where each lever lives.** Δ1 must be NVA-side because ARS loop-prevention runs on ingress before inbound route maps (FAQ language). Δ2 kept NVA-side for clean evidence — could theoretically move to an outbound ARS→VPN-GW-connection route map (preview) since set-C prefixes are eBGP-learned into hub2 ARS (not VNet address space) and route-maps preview restricts VNet-address-space rewrites; Trinity's design carries this as a Δ3-bis Phase-0 experiment but the Stage-1 card baseline keeps Δ2 NVA-side. Δ3 uses the preview inbound-map primitive to move Poland ARS best-path for the default onto NVA1 — this is the sole load-bearing preview-feature test in the lab.

**Set A/B framing.** Explicitly not cross-hub failover targets. If their local region/hub dies, the workloads die too — that's the correct model for hub-local application locality and the design honestly reports it rather than pretending set-A can pick up hub2 traffic. Set C is the one failover story the lab proves.

**No inter-hub NVA overlay in baseline.** Not needed for set-C↔on-prem (the traffic hops third-region-spoke → hub-region NVA → hub-region VPN GW → on-prem, not hub1↔hub2). Only required for cross-hub spoke transit or set-A/B failover — both explicitly out of scope. Documented as a P2 dormant patch in Trinity's design.

**Fan-out.** Trinity owns `design.md`; Niobe owns S1–S5 diagnostic gate skeleton; Oracle draws topology / control-plane / data-plane / cleanup diagrams from lab card §Regions/§Address/§ASN; Tank queued behind Stage-2 manifest + Phase-4 cost-gate approval.

**Process learning.** When Trinity owns the disputed-technical-claim doc (as she did here in `trinity-third-region-ars-design.md`), Morpheus does NOT revise the rejected review — the rejected review remains the immutable record of the ceremony, and a fresh Stage-1 card is authored against the user-locked corrected design. This keeps the audit trail honest: the "why we changed course" evidence is one directional link (rejected review → Trinity's before-DR pass → user-locked corrections → Stage-1 card), not a rewritten history. Codify this pattern for future contested design reviews.


---

📌 2026-08-05 — Route-map user stories v2: topology-independent rewrite (`labs/dual-hub-hubless-region-ars/route-map-user-stories.md`).

**What changed.** The v1 artifact was rejected for framing: it treated the caller's illustrative prompt as a literal spec and used the deployed lab as the only topology in which each scenario could exist. v2 inverts that. Every user story now opens on a clean generic reference topology chosen to demonstrate that story, and the live lab appears only in a per-story `Current lab` applicability line plus the §2 matrix. Nine stories: US01 inter-hub selective prefix exchange · US02 primary/backup hybrid egress with matching return path · US03 dynamic default-route injection · US04 inbound on-prem prefix admission · US05 outbound workload-prefix hygiene · US06 per-tenant/per-spoke-group policy · US07 route aggregation for scale · US08 BGP community tagging · US09 NVA-side versus ARS-side policy placement and migration.

**Design lesson — separate the problem topology from the lab topology.** When a scenario catalogue is written against the deployed estate, every story silently inherits that estate's constraints and the reader cannot tell which limitations are the technology's and which are ours. Authoring each story against a purpose-built generic topology first, and only then asking "can our current lab host this test", produces a reusable design guide and a cleaner test plan at the same time. Codify: architecture artifacts lead with the reference topology; applicability to the live lab is a separate, clearly labelled subsection.

**Four-way applicability classification works.** `testable as-is` / `testable with additive expansion` / `requires isolated alternate test bed` / `blocked by platform limitation` forced honest answers. Distribution came out 5 / 2 / 1 / 1. The `requires isolated alternate test bed` label earned its keep on US07: summarization strips AS-PATH, which would destroy the Δ2 hub-preference evidence on the exact `vpngw-onprem` path where that evidence lives — a real reason to build a separate bed rather than perturb a proven lab.

**Cost inflection captured.** All three Route Servers (`ars-poland`, `ars-hub1`, `ars-hub2`) have now completed the first-use route-map upgrade — `ars-poland` during the failed Δ3 association attempt, both hubs on 2026-08-05 (~26 min, both `Succeeded`, inert activation maps `rm-hub1-activate` / `rm-hub2-activate` left unassociated). The ~30-min wait and the per-ARS surcharge are therefore sunk costs. Every `testable as-is` story now carries zero incremental cost, which changes the priority calculus: the cheap experiments are the ones we previously deferred behind an upgrade gate.

**Route-map capability set re-grounded against Microsoft Learn 2026-08-05.** Eligible attachment points are ARS↔NVA BGP peerings and the ARS↔ER/VPN gateway connections *in the Route Server's own VNet*; one map per direction per connection; inbound runs before best-path (can change the winner), outbound runs after (advertisement shaping only); VNet address space is not map-modifiable; no per-VNet-peering attachment object exists; summarization strips AS-PATH and community; no more-specific route creation; no maps on the MSEE side; 2-byte ASNs only; no private/Azure-reserved ASN prepends; the default route is modifiable only when it originates from on-prem or an NVA; ARS discards routes carrying its own 65515 *before* inbound policy, so the strip must happen upstream. The peer-locality restriction (`HubBgpConnectionFromSpokeVnetCannotReferenceRouteMap`) remains undocumented on Learn — our runtime evidence is still the only authority.

**Size discipline note.** Target was ≤25 KB; landed at 40 KB. Nine stories × twelve mandated subsections plus a diagram specification each does not compress below ~40 KB without deleting decision content. Three full rewrites were spent chasing the budget before accepting the trade — the stated tiebreaker was decision usefulness over prose. Next time, negotiate either the story count or the subsection list up front rather than compressing after the fact; a per-story character budget belongs in the brief, not in the edit pass.

**Ownership note.** Trinity authored the rejected v1 and was locked out of this cycle by the caller. I authored the replacement independently rather than routing revisions back to her — consistent with the pattern already recorded for contested design reviews: the rejected artifact is superseded, not rewritten by its original author.


---

📌 2026-08-05 — US10 added to `labs/dual-hub-hubless-region-ars/route-map-user-stories.md` (v3): bow-tie / dual-site regional affinity.

**The ask.** Jose asked for a square / bow-tie ExpressRoute design — two on-prem sites, each attached to one regional hub, no cross-connections — with cross-region connectivity and some failover, testable by adding a second on-prem location and re-pointing the affinity. Treated as direction, not terminology; no debate about the label.

**Generic reference topology.** Diagonal attachment matrix: `dc-1`/`cpe-1` (AS 64500, 10.8.0.0/16) → `er-1` → `ergw-1` → `hub-1` (10.1.0.0/16, `ars-1`, `nva-1` AS 64496) and `dc-2`/`cpe-2` (AS 64501, 10.9.0.0/16) → `er-2` → `ergw-2` → `hub-2` (10.2.0.0/16, `ars-2`, `nva-2` AS 64497). No `cpe-1`→`er-2`, no `cpe-2`→`er-1`. On-prem DCI eBGP 64500↔64501. Azure inter-region = NVA-to-NVA eBGP 64496↔64497 over a `hub-1`↔`hub-2` global peering, with `bgp_path.delete(65515)` on export.

**Why the NVA overlay and not the obvious alternatives.** Global peering alone gives reachability but no BGP attribute to shape and no automatic withdrawal. Global Reach is a real second site-to-site path but joins sites, not hub VNets — it can never provide hub-to-hub transit, and needs Premium circuits across geopolitical regions. vWAN solves it but replaces the Route Server construct. The overlay is the only candidate that both creates the path and provides a BGP policy point on each side, which is exactly where the AS-path hygiene has to live. Two Learn facts make Azure-to-Azure transit through the circuits a non-starter rather than a preference: ExpressRoute cannot be configured as a transit router, and the Route Server FAQ documents that NVA-advertised routes returning through the MSEE are dropped by the second Route Server (the FAQ's own diagram is labelled bow-tie).

**The finding worth keeping — shared-dependency failure domain.** The Azure inter-region overlay is a dependency of *two* nominally independent failure responses: cross-region Azure-to-Azure traffic, and the ER-failure backup that routes a stranded site through the peer site's circuit and back across Azure. If the overlay dies, both die, and the on-prem DCI cannot substitute. Build the overlay redundantly; never document the corporate WAN as its backup.

**The ASN constraint, stated precisely.** All hub-side Azure gateways and all Route Servers use 65515, and route maps cannot remove it — the loop-prevention drop happens before inbound policy runs, and reserved ASNs may not be touched. Consequence in the VPN analogue: site prefixes cross the DCI cleanly (10.40.0.0/16 originates `65000`, becomes `65003 65000`, accepted by `vpngw-hub2`), and the Azure-to-site backup direction is also clean because the on-prem gateways have distinct ASNs. What fails is Azure prefixes making a second Azure entry — re-advertised across the DCI they still carry 65515 and `vpngw-hub2`/`ars-hub2` drop them. So the on-prem DCI backs up *site* prefixes only, never Azure-to-Azure. The ExpressRoute equivalent of the same wall is AS 12076 plus private-ASN stripping at the MSEE.

**Mitigation ranking.** (1) NVA-side 65515 strip on the overlay plus an explicit scope statement — additive, uses the proven Δ1 filter, recommended. (2) Controlled re-origination on an on-prem-side NVA — disruptive: there is no BGP policy point between two Azure VPN gateways, so it means a fourth Route Server or NVA-terminated IPsec (the previously rejected D5). (3) Distinct gateway ASNs — only actionable for gateways that do not coexist with a Route Server, since ARS coexistence pins the hub gateways to 65515. Option 3 is why option 1 works at all: the on-prem gateways were given 65000/65003 at design time.

**New applicability class.** `requires disruptive topology change` — additive staging, disruptive activation. Every new resource (`vnet-onprem2` 10.50.0.0/16 in polandcentral, `vpngw-onprem2` AA ASN 65003, `vm-onprem2-ep`, DCI pair, hub1↔hub2 peering + overlay, hub2↔onprem2 pair) can be staged live, but the affinity pattern is unreachable without deleting `conn-hub2-to-onprem` / `conn-onprem-to-hub2` — the exact path on which Δ2 and the S2/S3 timings were measured. Rounding that down to `testable with additive expansion` on the strength of the staging phase would have been dishonest. Cost +$10-11/day (lab ~$72 → ~$83/day), a further guardrail breach needing fresh approval; ~60-75 min staging plus ~15 min activation; disruption risk high and specific.

**Process note.** The four-class applicability taxonomy from v2 held for nine stories and broke on the tenth. A story that stages additively but activates destructively is a real category, not an edge case, and the honest move was to add the class and document why rather than stretch an existing label. Same reasoning as the v2 lesson about separating the problem topology from the lab topology: the classification exists to stop the reader inheriting our constraints by accident.

**Diagrams.** Two for this story — `US10-bow-tie-generic-er` and `US10-bow-tie-lab-vpn-analogue`. One would have been unreadable. The lab-analogue diagram is the single documented exception to the "diagrams use the generic topology" rule, because its whole purpose is to show the delta including the deleted edges.

---

📌 2026-08-05 — v4 of `labs/dual-hub-hubless-region-ars/route-map-user-stories.md`: overlay audit (Task A) + US11 no-overlay story (Task B).

**The user question that drove it.** Jose: *"Some of the user stories include an overlay between NVA1 and NVA2. If an overlay is really required, please explain why, since it adds significant complexity as compared to non-overlay topologies. That might be another User Story, hub-to-hub without an overlay?"* Both halves were correct. The document was using "overlay" as a single word for three different things, and the no-overlay design genuinely was a missing story rather than a footnote.

**The terminology collapse was the actual defect.** v3 wrote "IPsec overlay carrying eBGP" as one atomic phrase, which hid the fact that three independent layers were in play: the global VNet peering **underlay** (creates the path, natively, no BGP, no header), the NVA-to-NVA **eBGP adjacency** (pure control plane, adds no encapsulation), and the IPsec/VXLAN **encapsulation** (the only part whose necessity has to be argued). Once separated, the answer to Jose falls out immediately: the BGP session is what buys the prefix-level allow-list; the encapsulation buys nothing for policy. Codify: never let a design document name a control-plane session and a data-plane encapsulation with the same noun.

**The one Azure limitation that actually necessitates encapsulation — and it is not reachability.** `azure/route-server/multiregion`: Route Server programs learned routes into *all* subnets in its VNet, including the NVA's own subnet, so the moment remote-region prefixes are redistributed into the local Route Server the local NVA's route to the remote region points back at itself. The tunnel breaks the recursion because its outer destination is the remote NVA's underlay address, still covered by the peering system route. That is the whole justification, and it is conditional: no redistribution into ARS, no loop, no tunnel. The same article documents the escape hatch (disable BGP propagation on the NVA subnets, program static UDRs), which became US11 variant C.

**US01 lost its overlay as a default; US10 kept its overlay with a named requirement.** US01's own premise is "a small approved subset" — which is exactly the condition under which the static/native design suffices, so the overlay became a clearly labelled conditional variant and the story now points at US11 first. US10 retains it because four requirements converge and no non-overlay mechanism meets all four: automatic spoke-wide propagation, **automatic withdrawal** on ExpressRoute failure, AS-PATH/community-based affinity, and a churning prefix set. Requirement two is the decisive one — a static route cannot withdraw itself. Worth remembering as the general test: overlays are bought by *withdrawal and attribute* requirements, not by reachability requirements.

**Three no-overlay variants, deliberately not interchangeable.** A: native hub↔hub global peering, hub address space only. B: direct spoke↔spoke peering or AVNM connectivity configuration (`ConnectedGroup` next hop), which removes the hub hop entirely. C: bounded static NVA transit — global peering as underlay plus UDRs with next hop `VirtualAppliance` = the *remote* NVA IP on each NVA subnet. C carries six constraints that are easy to get wrong: a spoke UDR may never point at the remote NVA (peering is non-transitive, so "direct connectivity" fails); the UDR destination must not contain the next-hop address; `VirtualNetworkGateway` next hop is unavailable in any VNet that hosts a Route Server, because Learn says the Route Server *is* that VNet's gateway; Basic ILB frontends are unreachable across global peering; blanket `disableBgpRoutePropagation` on a brownfield NVA subnet also removes the ARS-injected on-prem routes existing flows depend on. C is written as "to be demonstrated", not "supported".

**The three things people expect global hub peering to do, and it does none of them.** Attached spoke prefixes do not cross; Route Server-learned prefixes do not cross; gateway-learned prefixes do not cross. The Route Server FAQ answers the hub-to-hub case in one sentence — *"Can I peer two Azure Route Servers in two peered virtual networks and enable the NVAs connected to the Route Servers to talk to each other? No… set up a direct connection (for example, an IPsec tunnel) between the NVAs"* — which is simultaneously why US11 exists (the Route Server is not the missing piece) and why US10 keeps its tunnel. A hub with its own gateway and Route Server also cannot enable *Use the remote virtual network's gateway or Route Server*, so that propagation path is closed by construction, not by policy.

**US11 becomes the cheapest experiment in the catalogue and reorders the whole plan.** Its test 1 — one `vnet-hub1`↔`vnet-hub2` global peering pair — creates no billable resource, takes under five minutes, is a prerequisite for both US01's inter-hub work and US10's staging, and its Route Server before/after diff is the cleanest baseline capture available. It moved to priority 1 and the recommended experiment ordering was rewritten around it. The one real caveat is not cost: creating a peering on a Route Server VNet triggers a route refresh to all peered NVAs — soft if BIRD supports RFC 2918, **hard** with traffic disruption if not — so BIRD's route-refresh capability must be confirmed before the change and both hubs treated as a change window.

**Design lesson to carry forward.** The pass/fail criteria for US11 are mostly *non*-effects: no Route Server route set changes, no gateway advertisement changes, no BGP session resets. Writing a test whose primary evidence is "nothing moved" forced better instrumentation than any of the positive-effect stories — before/after diffs of every ARS and gateway RIB, plus Network Watcher next hop as the platform-authoritative forwarding answer instead of traceroute. Worth reusing for every additive change to a live lab.


---

📌 2026-08-05 — v5 of `labs/dual-hub-hubless-region-ars/route-map-user-stories.md`: US12 square hybrid connectivity + front-page story index.

**The correction.** Jose: US10's bow-tie-with-cross-region-backup is useful but is *not* the design he had suggested. The suggested shape is a **square** — two DCs, each attached only to its own regional hub, four sides (DC1↔Hub1, Hub1↔Hub2, Hub2↔DC2, DC2↔DC1), no diagonals. Preserve US10, add US12 separately. Taken as direction; US10 is untouched apart from two cross-reference sentences.

**The distinction that mattered, and why merging them would have been wrong.** US10 and US12 draw the same four corners, so the temptation to merge is real. They are different designs because their *unit of design* differs. US10's unit is the cross-region **backup**: the topology exists to make a stranded site keep working automatically, which is a requirement, which forces a dynamic Azure inter-region path, which (once remote prefixes are redistributed into ARS) forces encapsulation. US12's unit is the **square itself**: four named sides, the inter-hub mechanism deliberately left open and justified separately, and failover written as a *bounded contract* instead of engineered around. Codify: when two designs share a picture, separate them by what the design is judged on, not by what it looks like.

**"Four sides do not imply failover" is the load-bearing sentence.** The commonest failure mode in this shape is reading the four physical sides as four capabilities. US12 splits reachability into four outcomes with per-outcome prerequisites: **A** normal regional affinity (needs nothing at all from the Hub↔Hub side — it is complete with that side absent); **B** cross-region, itself split into B1 DC↔DC, B2 Hub↔Hub, and **B3 DC↔remote-Hub, which is not implied by B1+B2** and has two mutually exclusive realisations; **C** failover after the local ER side fails, with six prerequisites of which two decide feasibility — Azure-side carriage of a *foreign* site prefix, and **automatic withdrawal** (a static UDR forwards but cannot withdraw itself); **D** restoration with attribute-identical tables per direction. With a native-peering inter-hub side, outcome C is simply not delivered, and the honest deliverable is a written *graceful partial degradation* contract, per flow per failure.

**The new hard citation.** `azure/route-server/expressroute-vpn-support`: *"ExpressRoute circuit-to-circuit connectivity isn't supported through Azure Route Server. Routes from one ExpressRoute circuit aren't advertised to another ExpressRoute circuit connected to the same virtual network gateway. For ExpressRoute-to-ExpressRoute connectivity, consider using ExpressRoute Global Reach."* Branch-to-branch covers NVA↔ER, NVA↔VPN and ER↔S2S-VPN — not ER↔ER, and not P2S. That closes the "just hairpin the two circuits" idea as a platform property rather than a preference. The CAF AVS article shows what ER↔ER transit actually costs when you insist: Route Server plus BGP-capable NVAs, **supernets** rather than exact prefixes *"because the exact prefixes are already announced in the opposite direction"*, and *"the BGP-capable NVAs must remove the AS paths to prevent routes from being dropped by BGP loop detection"* (65515 and 12076). Worth remembering as the general shape of every cross-circuit workaround.

**Global Reach is the DCI side, never the Azure side.** Stated once, loudly, because it is drawn wrong constantly. It joins the on-premises sides of two circuits — enabled between the private peering of any two circuits in supported countries created at *different* peering locations, Premium across geopolitical regions — and it can never connect two hub VNets. A diagram with Global Reach as the hub↔hub side is drawing a link that does not exist.

**DCI taxonomy earned its place.** Enterprise WAN/MPLS, SD-WAN, Global Reach and VPN are not interchangeable for this story's reasoning. The SD-WAN case is the interesting one: path selection can be policy-driven rather than BGP-driven, so the "the backup copy is one ASN longer, therefore failback is automatic" argument used everywhere else in the guide does **not** automatically hold. Ask how the SD-WAN expresses backup preference, and prove it.

**Default no overlay, and it stuck.** US12's default inter-hub mechanism is US11's native peering; vWAN is presented as a first-class *native* answer (hubs in one virtual WAN are automatically interconnected; routing intent adds branch-to-branch secure transit) rather than as an afterthought; the NVA/BGP dynamic variant is the answer only when outcome C is claimed, with encapsulation only when remote prefixes are redistributed into the local Route Server. The rule from v4 held under a second, independent story: overlays are bought by *withdrawal and attribute* requirements, never by reachability.

**Front-page story index (Task B).** Twelve rows, one per story: user outcome, design disposition, route-map role, current-lab fit, key delta/blocker, diagram IDs — with the five disposition terms defined immediately above the table and an explicit *"Not a disposition"* paragraph so that a reviewer's rejection of draft wording can never be mistaken for a platform or design rejection. Dispositions came out Accepted 6 / Conditional 5 / Platform-blocked 1, with `Rejected as implementation — retained` and `Pending validation` deliberately at **zero** at whole-story level and used only at sub-scope (US10's UDR-only alternative; US12's ER↔ER transit and diagonal link; US11 variant C). Resisting the urge to fill every term in the legend is the point — a taxonomy that always has a member in each bucket is a taxonomy being fitted to the table.

**Lab delta, reused by reference.** US12's analogue is deliberately thin: `vnet-onprem` stays as DC1, site 2 is US10's exact staged set, the DCI is the two on-premises VPN gateways connected to each other, and the hub↔hub side is offered as two mutually exclusive lanes (variant N native peering, variant D NVA BGP + conditional encapsulation). US10's S0 preflight gate, cost basis, timings and 9-step rollback are cited, not re-typed — about 10 KB of duplication avoided, and more importantly one copy to keep correct. Ordering recommendation changed as a result: run US12 variant N *before* US10, because it shares every staged resource but claims less, so the bounded-failover contract is measurable before any tunnel exists.

**The open question worth chasing.** Does an Azure VPN gateway re-advertise routes learned on one BGP-enabled connection to another, in this configuration? Learn now answers it in principle — VPN Gateway FAQ: *"BGP transit routing is supported, with the exception that VPN gateways don't advertise default routes to other BGP peers"* — which upgrades US10's post-activation set-C assertion from inference to documented-but-unmeasured. This lab has never been able to observe it because the reciprocal Azure-to-Azure case is masked by the 65515 drop at the far hub. It becomes measurable the moment `vpngw-onprem2` exists, and it should be the first assertion checked after staging, before any activation.

---

📌 2026-08-05T13:43:07.691+02:00 — Stage-1 card locked for `storage-endpoint-path-equivalence`.

**Interpretation.** A Storage service endpoint is not a private interface or DNS endpoint: DNS and destination stay public, while Azure installs a `VirtualNetworkServiceEndpoint` route and Storage observes the client's private/VNet identity. A private endpoint changes the same FQDN to a VNet NIC/private destination. Therefore the defensible lab claim is about observable DNS, route, destination, source identity, and authorization deltas — never identical Microsoft physical underlay.

**Experimental pattern.** One VM/subnet/account/FQDN/object is reused sequentially for public, service-endpoint, endpoint-policy, and private-endpoint runs. Fresh TCP connections and unique request IDs prevent connection reuse from polluting paired evidence. DNS + effective routes + PCAP + Storage `CallerIpAddress` logs are authoritative together; VNet flow logs are corroborating; traceroute/latency alone are rejected.

**Phase 0.** In `swedencentral`, `Standard_B1ls` and `Standard_B1s` were catalog misses. `Standard_B2ts_v2` passed catalog and live `az vm create --validate`. The exact tagged preflight RG was verified removed. No billable lab resources were deployed; Phase 4 remains closed.

---

📌 2026-08-05T13:43:07.691+02:00 — Scribe merge pass: storage-endpoint-path-equivalence decision brief recorded in decisions.md; lab-card stays unstaged; Phase 4 remains closed.

---

📌 2026-08-05 — Extraction contract for a two-region hub-to-hub ARS route-policy lab (US10 + US11), no redeployment.

**The ask.** Jose: *"Could we merge US10 and US11 in a new lab? This one was about adding regions, but we wouldn't need region 3 (Poland) for the ARS route map functionality test... just to move the required assets to a new directory in the labs folder"*. Design-only task: slug, composition decision, scenarios, asset plan. No Azure change, no commits, no lab file edited. Output: `.squad/decisions/inbox/morpheus-us10-us11-extraction.md`.

**Slug names the design, not the history.** `dual-hub-interconnect-ars-route-policy` — "Dual-Hub Interconnect and Route Server Route-Map Policy (two regions)". Rejected `third-region-*` (describes the framing Jose abandoned), `us10-us11-merged` (encodes story IDs into a path that breaks on renumbering), `hub-to-hub-overlay` (pre-judges the exact question one scenario exists to answer). Directory slugs should survive the catalogue changing underneath them.

**"Merge" resolved as a test-program composition, not a merged story.** US10 and US11 stay in the canonical catalogue, unchanged, with their stable IDs, dispositions and diagram IDs; the new lab defines a five-scenario program that cites them. The decisive argument is not tidiness — it is that the two stories carry *incompatible dispositions* (US11 Accepted/`additive`, US10 Conditional/`disruptive activation`), so a merged story must collapse to the stricter one and would silently re-gate US11's cheap GA baseline. Second argument: US12 already exists precisely because two designs can share a picture and differ in what they are judged on; merging US10+US11 would contradict that precedent inside the same document. Third: the scenario-retention policy makes catalogue subtraction a governance violation, and a merge is a subtraction of two rows. General rule worth keeping — **compose at the test-program layer, never by editing the story catalogue**.

**Scenarios: the baseline's evidence is a set of non-effects.** T1 (native hub↔hub global peering) passes when nothing moves — ARS and gateway RIBs byte-comparable, BIRD uptime unbroken. Two traps I wrote in explicitly: the probe *must* be `vm-nva1` 10.10.1.4 ↔ `vm-nva2` 10.20.1.4 because the `*-ep` VMs live in spoke VNets and a spoke prefix does not cross a hub↔hub peering; and the absence of spoke/ARS-learned/gateway-learned prefixes is the expected result, not a failed transitivity test. T2 is the first-ever route-map **association** in this lab and stays gated: inert TEST-NET map first, real AS-path modification only after. T3 (dynamic NVA BGP/tunnel) is conditional and runs *only* if withdrawal or attribute requirements are actually claimed — non-execution is itself a valid deliverable. T4 compares route map vs BIRD placement and exists mainly to record the map-inexpressible case: ARS drops a 65515-bearing route *before* inbound policy runs, so the Δ1 strip lives on the NVA permanently. T5 (gateway-connection attachment) stays last, optional, separately approved, and labelled unverified.

**Copy, never move — and the reason is provenance, not caution.** Jose said "move". A literal move breaks a *certified* evidence chain: `lessons-learned.md`, `validation.md` and `deploy-log.md` cite `show-output/**` inline, and Niobe signed the lab off on 2026-08-04. Splitting US10/US11 out of `route-map-user-stories.md` would leave ten dangling anchors. And the evidence is shared-bed evidence — the same live resources back both labs, so a capture is only interpretable while it stays attached to the lab that took it. Plan: extract two-region generic prose and the three US11 Mermaid blocks, copy hub-scoped baselines into `show-output/inherited/` with provenance headers, reference everything mixed-scope, and add exactly one additive line to the original README.

**The three US10 diagrams that must NOT be copied.** `US10-bow-tie-generic-er` (both blocks) is a four-corner ExpressRoute bed with two DCs, two circuits and MSEE AS 12076 — copying it into a two-region VPN lab would assert an ER scope that does not exist. `US10-bow-tie-lab-vpn-analogue` contains `ars-poland`, set-C, `vnet-onprem2` and the S3 deleted-connection annotation — i.e. exactly the excluded scope. One genuinely new figure is needed instead: `HH-two-region-hub-interconnect`, with the hub↔hub side drawn as **two mutually exclusive lanes** (native peering vs NVA BGP + conditional encapsulation), never both at once.

**IaC is the trap with the worst blast radius.** `main.bicep` / `main.json` / `deploy.ps1` describe the full four-region bed. Copied into the new lab they become a template that, if ever run, redeploys a live lab and re-creates Poland. So: reference only, and the new `deploy/` holds nothing but additive change scripts each paired with its rollback, under a README line stating *"This directory contains no deployment code."*

**Sanitization came out clean by construction, and I still made it a check.** Nine files in the original lab carry `/subscriptions/<GUID>` — six under `delta3/`, two under `deploy/`, one under `s2-failover/`. None is on the copy list, because all nine are Poland/failed-Δ3/full-resource-dump artifacts, which are excluded on scope grounds anyway. Scope hygiene and secret hygiene pointed the same way here; I still wrote the scan into the checklist rather than trusting the coincidence.

**Ownership stays put, and the cost line matters.** The live RG, the cleanup sequence and the Phase-8 gate remain with the original lab; the new lab may roll back only its own deltas. The cost statement I insisted on: the three ARS route-map surcharges (~$6/day each, irreversible) are **already** charged to the original lab, so the new lab's own delta is effectively zero — restating ~$84/day as the new lab's cost would double-count the same bed and would make a future approval gate meaningless.

**Handoff.** Tank first (skeleton, `.mmd` extraction, evidence copies with provenance headers, change+rollback scripts, checklist), then Trinity (`design.md`), Niobe (`validation.md`, `README.md`), Oracle (the new diagram), me (`manifest.md` + the Phase-4 wording for T2/T3/T5). Four cheap questions for Jose: confirm the slug before cross-links exist, confirm copy-not-move, confirm T2 may be scheduled as a maintenance window on the shared bed, and decide whether an additive `US13` composition pointer is wanted at all.

---

📌 2026-08-05T16:16+02:00 — Phase-0 refresh and pre-deployment manifest completed for `storage-endpoint-path-equivalence`.

**Phase 0.** Re-ran the canonical `swedencentral` cost ladder: `Standard_B1ls` and `Standard_B1s` remained catalog misses; `Standard_B2ts_v2` passed both catalog and live `az vm create --validate`. Only exact tagged RG `rg-preflight-sepath-20260805-161627` was used, and deletion was verified. No sensitive IDs were retained.

**Manifest.** Added `labs/storage-endpoint-path-equivalence/manifest.md` (13,769 bytes, under the 15 KB cap). It inventories the complete Azure topology, dependencies, tags, safe firewall/endpoint transitions, five executable correctness scenarios, separate correctness/performance evidence, sanitized report/blog handoffs, cleanup ordering, and the closed Phase-4 gate.

**Performance contract.** Predeclared public/SE/PE paired comparisons across concurrency 1/8/32, 64-KiB and 8-MiB payloads, fresh/reused connections, ten randomized balanced Latin-square blocks across two time windows, warm-up, interleaving, invalidation rules, block-level bootstrap confidence intervals, and TOST equivalence margins. Any conclusion is conditional performance equivalence, never Microsoft physical-path identity.

**Reviewer notes incorporated.** Same-region `CallerIpAddress` is supporting rather than sole authority; request IDs cannot be read from encrypted TLS PCAP; endpoint-policy drops may have no Storage resource log; firewall transitions enable SE before deny-by-default enforcement; `show-next-hop` is corroborative and must not be over-read.

**Gate.** No billable lab resources, Megaport/ExpressRoute objects, or IaC were created. Tank remains blocked until Jose explicitly approves Phase 4.

---

📌 2026-08-05T18:05+02:00 — Two-stage roadmap added to `labs/dual-hub-interconnect-ars-route-policy`: bow-tie first (TP-HH), square second (TP-SQ / US12), gated.

**The ask.** After the bow-tie/regional-affinity program, evaluate the square. Jose expects he would probably not recommend it — and asked for **evidence of feasibility and technical complexity rather than a prejudgement**. That distinction is the whole design of this pass: an expectation is recorded as an expectation, never as a verdict.

**Sequencing, and why it is not arbitrary.** Stage 1 (TP-HH: T1 no-overlay baseline, T2a/T2b route-map association gate, T4 policy placement, T3 dynamic variant only where justified, T5 only if approved) answers the three facts Stage 2 depends on: whether an ARS route-map **association** is possible on a live hub connection and at what operational cost; what a native hub↔hub peering actually carries — which *is* US12's default S-B mechanism; and whether the gateway-connection attachment point exists at all. Running the square first would spend a disruptive topology change and ~$95+/day to learn what a $0/day additive test answers. Stage 1 is not "complete" until it is **rolled back** — the restored certified baseline is Stage 2's reference state, and Stage 2 may not inherit a still-attached peering or a still-associated map.

**Square kept as candidate, with a verdict ladder instead of an opinion.** Four verdicts, each with the evidence that chooses it: `Recommended`, `Conditionally viable`, `Technically feasible but operationally unattractive`, `Platform-blocked`. Rule #30 governs: every design is documented with an evidence-based verdict and none is deleted for an unfavourable one. The third verdict is the one this study most likely needs, and it only exists honestly if it carries an explicit "no feasibility criterion failed" statement — otherwise readers will file it as a technical rejection, which would be a different and false result.

**Feasibility separated from desirability — the load-bearing structure.** F1–F7 decide packets: reachability with A/B1/B2/B3 reported separately, failover **against the contract written before the fault**, failback with no operator action, symmetry by two-ended capture and counters (never traceroute), convergence per direction at 30/60/120/180 s, restoration attribute-identical to E0, and no collateral damage to set-C / the two `ars-poland` `0/0` copies / the Δ2 path. An 8-dimension scorecard decides operations: resource count, routing domains, policy locations, failure dependencies, operational procedures, observability points, convergence behaviour, cost — scored only from counted artefacts. A failed criterion is failed on that criterion and never softened into a complexity score.

**One subtlety worth keeping.** Under variant N, "outcome C not delivered" is a **PASS** when it was predicted — and a flow that *survives unexpectedly* is a **FAIL**, because the contract, not the topology, is what is under test. That is the sentence that makes the bounded-failover contract real rather than decorative.

**Activation contract written, not executed.** Exact deltas from the restored baseline: DC1↔Hub1 reused, Hub1↔Hub2 added (T1's delta re-created), Hub2↔DC2 added, DC1↔DC2 added, **no diagonals**; the single disruptive step is deleting `conn-hub2-to-onprem`/`conn-onprem-to-hub2` and nothing else; A0–A11 activation with E0–E6 checkpoints and a 9-step rollback whose step 6 — recreating that pair with a fresh matching PSK (DEV-001) — is the highest-risk act in the whole program because it restores *another lab's* certified evidence path. Poland: region reuse is not resource reuse — `vnet-onprem2` is new, `ars-poland`/set-C stay control-only, and the `polandcentral` placement is not load-bearing.

**Gates G1–G4, all OPEN, tracked in `deploy-log.md`.** Stage 1 complete and rolled back · Poland cleanup status **known and recorded, explicitly not a dependency** (unknown blocks; still-deployed does not) · a **fresh** cost/resource/**deletion** approval with nothing carried forward · and the exact route-map attachment behaviour from T2a/T5, as a working body or a verbatim error code.

**Diagram.** New `diagrams/HH-stage-roadmap.mmd` — a roadmap, deliberately carrying no address space or ASN so it cannot be misread as topology. Validated with the cached `@mermaid-js/mermaid-cli` (no new tooling installed); the README-embedded copy was extracted and validated independently and rendered byte-identically. Temp SVGs removed.

**Boundaries held.** No Azure change, no IaC, no test run, no deletion, no commit. US10/US11/US12 keep their stable IDs, dispositions and text — cross-linked, never copied. Brief at `.squad/decisions/inbox/morpheus-bowtie-square-sequence.md` with six open approval points for Jose.

---

📌 2026-08-06 — Policy-preserving PaaS redesign selected Azure AI Translator F0 for `storage-endpoint-path-equivalence`.

**Selection.** Azure AI Translator (`Microsoft.CognitiveServices/accounts`, `TextTranslation`, F0) is the cheapest viable replacement. It supports a public custom endpoint, classic `Microsoft.CognitiveServices` service endpoint/subnet rule, and Private Endpoint against the same FQDN. The VM uses managed identity and `Cognitive Services User`; local keys remain disabled.

**Live governance evidence.** Root management-group assignments are enforced in `Default` mode. Storage, SQL, Key Vault, and Cosmos DB each have an active `modify` definition that forces public access off, so all were rejected. Cognitive Services has only local-auth disablement and policy-deployed diagnostics; no active policy forces its public endpoint off. Sweden Central reports unrestricted Translator F0/S1 SKUs. Event Hubs Standard is viable but costs US$0.03/hour plus PE; Service Bus Premium and other host-based alternatives cost more.

**Delta.** Reuse the VM/VNet/NAT/NSG/Log Analytics/flow-log bed. After a new Phase 4 approval, remove two experimental Storage accounts and Storage-specific endpoint artifacts; add one F0 Translator account and replace the existing Blob PE/DNS path with the Translator PE/DNS path. The steady-state fixed delta versus the live lab is approximately US$0/hour because one US$0.01/hour PE replaces another. No paid fallback is authorized.

**Evidence scope changed deliberately.** Keep public, SE route, subnet authorization, PE, and forced-public negative-control scenarios. Drop the Storage-only endpoint-policy decoy. F0 throttling and AI processing latency make the former high-concurrency/large-payload performance protocol invalid; correctness is primary and only low-rate small-body latency observations remain.

**Gate.** Wrote `labs/storage-endpoint-path-equivalence/redesign.md` and `.squad/decisions/inbox/morpheus-storage-sepath-paas-redesign.md`. No Azure resource was deployed, changed, exempted, or deleted.
