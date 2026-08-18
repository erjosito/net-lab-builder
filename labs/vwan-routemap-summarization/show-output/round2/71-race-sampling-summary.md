# 71 — Race-sampling harness: results summary (Round 2)

**Run:** N=20 recompute cycles, 2026-08-18 13:37 → 15:32 (+02:00)
**Harness:** `files/race-sample.ps1` (session workspace)
**Raw evidence:** [`70-race-sampling-run.txt`](70-race-sampling-run.txt) (full log) · [`70-race-sampling.csv`](70-race-sampling.csv) (per-iteration table)
**Lab:** `routemap-test-rg`, VWAN `vwan-routemap2` (b2b **disabled**), route-map `summarize-out` on `cx-nva1`

## Question

Microsoft's engineering root cause is that the `/16` summary, aggregated from **mixed-origin**
contributors (some ER/branch-learned, one VNet/egress), **intermittently inherits** the ER/branch
attributes during recomputation and is then dropped because Branch-to-Branch is disabled. That makes the
bug **nondeterministic** — a race across recompute cycles. A single observation cannot disprove it, so
this harness forces many fresh aggregations and densely samples the branch each time, looking for even one
cycle where the `/16` disappears.

## Method (per iteration)

1. **Force a fresh aggregation** — detach then reattach `outboundRouteMap` (`summarize-out`) on the
   `cx-nva1` VPN connection via `az rest` PUT (api 2023-09-01). Each reattach re-runs hub route
   aggregation. ~203 s/cycle.
2. **Dense branch poll** — 30 on-box samples @ 3 s (≈90 s) of the onprem BIRD RIB via
   `az vm run-command` (base64-wrapped script). Records, per sample, whether `10.0.0.0/16` is present,
   its AS-PATH, and any BGP community.
3. **MSEE input-consistency capture** — both ER circuits (`er-eu1`, `er-eu2`), primary + secondary paths,
   `AzurePrivatePeering` route tables. Confirms the aggregation *inputs* stayed constant across cycles.

Metrics per iteration: `branch_p_min` (fraction of the 30 samples with the `/16` — worst case),
`branch_p_all` (present in all 30?), `anomaly`, `aspath_seen`, `comm_seen`, `msee_contrib_count`.

## Results

| Metric | Value across all 20 iterations |
|---|---|
| Iterations completed | **20 / 20** |
| Branch `/16` present (`branch_p_min`) | **1.0 in every iteration** (600/600 dense samples) |
| Branch drops | **0** |
| Anomalies flagged | **0** |
| Branch AS-PATH | `65515` in every sample (hub ASN — never `12076`) |
| Branch BGP community | none observed |
| MSEE contributor rows (`msee_contrib_count`) | **11, constant** every iteration |
| `er-eu2` MSEE `/16` (`10.0.0.0/16`) | present every iteration (80 rows = 4/iter × 20) |
| `er-eu1` MSEE `/16` | **never** present (0) — only the `/24` contributors |

Harness self-report: `SUMMARY: iterations=20 anomalies=0 branch_drops=0`.

### Branch `/16` vs. `er-eu2` MSEE `/16` — consistency

Both observation points agreed in **every** cycle: whenever the branch showed `10.0.0.0/16 (65515)`, the
`er-eu2` MSEE route table also carried `10.0.0.0/16 (65515)` on both paths. There was **no** cycle where
the aggregate appeared at one point but not the other, and **no** flap. The `er-eu1` MSEE consistently
showed only the specific `/24` contributors (`10.0.1/2/3.0/24`, AS-PATH `133937 ?` from onprem via the
MCR) plus `10.0.128.0/24` — never the aggregate, because `summarize-out` is attached only to
`conn-eu1-er2` (→ `er-eu2` circuit), not to `conn-eu1-er1` (→ `er-eu1` circuit). This asymmetry is
expected and is itself a useful confirmation that the summary is emitted per-connection.

## Interpretation

At the current contributor ratio (**3 ER-learned `/24`s : 1 VNet/egress route**), pure recompute cycling
is **deterministic in this environment** — the `/16` was rebuilt and advertised on all 20 fresh
aggregations, never once inheriting a branch classification that would drop it. **We did not reproduce**
the intermittent retirement.

This is a **negative result**, not proof of safety. Per MS, the drop hinges on an internal
origin/branch-classification flag that the aggregate *inherits* from whichever contributor "wins"
during aggregation. That flag is **not visible** in the advertised AS-PATH (always `65515`, because
summarization strips AS-PATH + Community), so presence/absence of the `/16` is the only external signal —
and it never went absent. "Couldn't reproduce" = "didn't land on a branch-inheriting cycle in 20 tries",
not "`Replace` is immune".

## Follow-up (open)

Raise the **ER : VNet contributor ratio** to increase the probability that a branch-attributed route is
selected for the aggregate: expand the `er-eu1` VXC `ipRoutes` on the MCR from 3 to many `/24`s (e.g.
`10.0.4.0/24 … 10.0.60.0/24`) via the Megaport API, then re-run this harness. The MS mitigation
(`asPath Contains 12076 → Drop` before summarize) remains the correct deterministic fix regardless of
whether the race is ever caught here.
