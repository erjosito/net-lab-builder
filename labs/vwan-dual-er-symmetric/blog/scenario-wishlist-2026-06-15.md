# Scenario Wishlist — Niobe Evidence Request

**Requested by:** The Kid | **Revised:** 2026-06-16 (editorial pivot: MS Learn update framing)  
**Lab:** `vwan-dual-er-symmetric` | RG: `rg-vwan-symm-103167`

---

## Blind-spot evidence anchors (new section — 2026-06-16)

The blog is now framed as a contemporary update to the MS Learn ER DR article. Each blind spot must be backed by a captured artifact:

| Blind spot | MS Learn claim being updated | Evidence anchor | Status |
|---|---|---|---|
| **#1 Stateful AzFW silent drop** | *"Typically you don't come across stateful entities such as NAT or Firewalls"* | `design-b-phase1-asymmetric-2026-06-15/11-azfw1-kql-results.txt` (AzFW1 allows; AzFW2 silent) + `12-azfw2-kql-results.txt` | ✅ done |
| **#2 No iBGP at partner CE** | *"use local preference on the iBGP session between your BGP routers"* | `design-c-asymmetric-2026-06-15/cr-routes-before-mechc.txt` (single CR, two peers, pure AS-path best-path — no local-pref lever) | 🔄 in-flight (niobedc) |
| **#3 vWAN Route Maps as modern lever** | Article has no mention of vWAN Route Maps | `design.md §4` (Trinity's Mech C1+C2 spec) + `mechc1-active-{date}/azfw1-kql.txt` + `mechc2-active-{date}/azfw1-kql.txt` | 🔄 in-flight (Trinity) + 📋 future (Niobe ×2) |

---

## Priority table

| # | Scenario | Why blog needs it | Probe | Evidence file(s) | Topology | Status |
|---|----------|-------------------|-------|-----------------|----------|--------|
| 1 | **Design B asymmetric — money shot** | **Blind Spot #1 anchor.** AzFW1 allows SYNs; AzFW2 silent — proves stateful AzFW asymmetry kills sessions silently. | spoke1→VM-B TCP/22 | `design-b-phase1-asymmetric-2026-06-15/09-tcp-a-to-b-x5.txt` ⭐ `11-azfw1-kql-results.txt` ⭐ `12-azfw2-kql-results.txt` | Design B | ✅ done |
| 2 | **Design B control test** | Same policy, different path → spoke3→VM-B succeeds. Proves policy is not the blocker. | spoke3→VM-B TCP/22 | `design-b-phase1-asymmetric-2026-06-15/10-tcp-b-to-a-x5.txt` | Design B | ✅ done |
| 3 | **Design C asymmetric baseline** | TCP still fails with single CR — asymmetry now Azure-layer BGP, not GCP regional routing. | spoke1→VM-B TCP/22 + AzFW KQL both hubs | `design-c-asymmetric-2026-06-15/tcp-spoke1-to-vmb.txt` `azfw1-kql.txt` `azfw2-kql.txt` | Design C | 🔄 in-flight (niobedc) |
| 4 | **Design C GCP CR best-path** | **Blind Spot #2 anchor.** Single CR, two peers, pure AS-path best-path decision — no iBGP local-pref lever anywhere in the chain. | `gcloud compute routers get-status router-vwan-symm-a --region europe-west3 --format=json` | `design-c-asymmetric-2026-06-15/cr-routes-before-mechc.txt` | Design C | 🔄 in-flight (niobedc) |
| 5 | **Hub1 + Hub2 effective routes (before Mech C)** | Azure-side: Hub1 prefers MCR1 for 10.50.2.0/24. Pairs with #4 for two-sided view. | `az network vhub get-effective-routes` on Hub1 + Hub2 | `design-c-asymmetric-2026-06-15/hub1-effective-routes.txt` `hub2-effective-routes.txt` | Design C | 🔄 in-flight (niobedc) |
| 6 | **`ss -tn state SYN-SENT` during failure** | Half-open TCP visible without Log Analytics. Add to niobedc's current run. | Run during TCP probe to 10.50.2.2 on vm-spoke1 | `design-c-asymmetric-2026-06-15/vm-spoke1-ss-syn-sent.txt` | Design C | 🔄 in-flight — **add now** |
| 7 | **Mech C1 active/active — TCP fixed** | **Blind Spot #3 closing exhibit (C1).** Both AzFWs log entries — proves active/active outbound Route Maps fix what the article's iBGP advice can't reach. Maps to MS Learn Scenario 2. | spoke1→VM-B TCP/22 + SSH + AzFW KQL both hubs | `mechc1-active-{date}/tcp-spoke1-to-vmb.txt` `azfw1-kql.txt` `azfw2-kql.txt` | Mech-C1-active | 📋 future-needed |
| 8 | **GCP CR routes after Mech C1** | Proves Mech C1 is Azure-only: CR routes IDENTICAL to #4. Must be captured before C2 is applied. | Same gcloud as #4, after C1 route-map apply | `mechc1-active-{date}/cr-routes-after-mechc1.txt` | Mech-C1-active | 📋 future-needed |
| 9 | **Hub1 effective routes after Mech C1** | Before/after at Azure control plane: 10.50.2.0/24 switches from MCR1 to MCR2 as Hub1's preferred next-hop. | `az network vhub get-effective-routes` on Hub1 post-C1 route-map | `mechc1-active-{date}/hub1-effective-routes-after-c1.txt` | Mech-C1-active | 📋 future-needed |
| 10 | **Mech C2 active/passive — TCP fixed** | **Blind Spot #3 closing exhibit (C2).** Proves per-region active/standby via inbound Route Maps. Maps to MS Learn Scenario 1. | spoke1→VM-B TCP/22 + AzFW KQL both hubs | `mechc2-active-{date}/tcp-spoke1-to-vmb.txt` `azfw1-kql.txt` `azfw2-kql.txt` | Mech-C2-active | 📋 future-needed |
| 11 | **Hub1 effective routes after Mech C2** | Shows 10.50.2.0/24 now routes via MCR2 as standby (inbound map applied). Confirms C2 changes Azure-side routing. | `az network vhub get-effective-routes` on Hub1 post-C2 route-map | `mechc2-active-{date}/hub1-effective-routes-after-c2.txt` | Mech-C2-active | 📋 future-needed |
| 12 | **Azure Portal screenshot — Hub1 effective routes** | Visual proof without CLI. Portal → vWAN → Hub1 → Routing → Effective Routes → filter `10.50.2.0/24`. Before C1 / after C1 / after C2. | Portal manual capture (PNG) | `design-c-asymmetric-{date}/portal-hub1-routes-before.png` `mechc1-active-{date}/portal-hub1-routes-after-c1.png` `mechc2-active-{date}/portal-hub1-routes-after-c2.png` | Design C + C1 + C2 | 📋 future-needed |
| 13 | **Mech B removed — ECMP edge case** | Equal-length AS-paths → GCP selects via router-ID. Shows what Mech B covers up. Config-change + revert. | `gcloud compute routers get-status` after removing Axis-1 prepend | `design-c-no-mechb-{date}/cr-routes.txt` | Design C (Mech B removed) | 🟡 nice-to-have |
| 14 | **MCR1 failure — Design C single-path exposure** | Honest trade-off: Design C has no failover at CR level. Resiliency cost of the topology. | spoke1→VM-A TCP before/during MCR1 BGP shutdown | `design-c-mcr1-failure-{date}/tcp-before.txt` `cr-routes-mcr1-down.txt` `tcp-during.txt` | Design C | 🟡 nice-to-have |

---

## Critical gaps for current (niobedc) run

- **#6 (`ss -tn state SYN-SENT`)** — one extra command during probe. High reader value; zero extra cost. **Add to niobedc's active run now.**
- **#4 + #5** — confirm GCP CR routes and Hub effective routes are on niobedc's capture list.

## Critical gaps for post-Mech-C runs

**Two separate Niobe runs needed — C1 first, then C2:**

**C1 run** (apply outbound route maps only): capture #7, #8, #9 before C2 is applied. The #8/#4 comparison (CR routes IDENTICAL to Design C) is the key Blind Spot #3 claim validator.

**C2 run** (add inbound maps + hub preference): capture #10, #11, and re-run the GCP CR routes check — should still be identical to Design C. Capture portal screenshots (#12) at each stage.

## ⭐ Money shots (the four files the blog cannot ship without)

- `design-b-phase1-asymmetric-2026-06-15/11-azfw1-kql-results.txt` — Blind Spot #1: AzFW1 allows; AzFW2 silent
- `design-c-asymmetric-2026-06-15/cr-routes-before-mechc.txt` — Blind Spot #2: no iBGP local-pref in partner-CR chain
- `mechc1-active-{date}/azfw1-kql.txt` + `azfw2-kql.txt` — Blind Spot #3 (C1, active/active): both firewalls lit up — MS Learn Scenario 2
- `mechc2-active-{date}/azfw1-kql.txt` + `azfw2-kql.txt` — Blind Spot #3 (C2, active/passive): both firewalls lit up — MS Learn Scenario 1
