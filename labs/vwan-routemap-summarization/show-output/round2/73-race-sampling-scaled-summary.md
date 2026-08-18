# Scaled race-sampling run (63 : 1) — results

**Run:** `race-sample2.ps1`, N=30 recompute cycles, b2b disabled, observation at **both** the VPN
branch (`nva1`) and the `er-eu2` MSEE route table.
**Contributor ratio:** 63 ER-learned `/24`s (`10.0.1.0/24 … 10.0.63.0/24`, AS 12076 via MCR) : 1
VNet/egress contributor (`10.0.128.0/24`, AS 65515).
**Evidence:** `72-race-sampling-scaled.csv`, `72-race-sampling-scaled-run.txt`.
**Harness summary line:** `iterations=30 anomalies=21 branch_drops=0 er2_16_drops=21`.

## Headline

**The intermittent summary retirement was NOT reproduced at 63 : 1.** At the valid observation
point — the VPN branch — the `/16` summary was present in **every one of the 30 × 30 = 900 dense
samples** (`branch_p_all=1` in all 30 iterations, `branch_drops=0`). Skewing the ER:VNet contributor
ratio from 3:1 to 63:1 did not trigger the mixed-origin aggregation race in this environment.

## The er-eu2 "drops" are contamination, not a repro

The harness flagged `ANOMALY=YES` on 21 of 30 iterations because the `/16` disappeared from the
`er-eu2` MSEE route table (`er2_16_primary=0`, `er2_16_secondary=0`) from **iteration 10 onward** and
never returned. This is **not** the customer's race. It is a direct consequence of an **out-of-band
topology change**: the ExpressRoute connection **`conn-eu1-er2`** — the only connection carrying a
summarizing route-map toward `er-eu2` — was **deleted** mid-run (for an unrelated ExpressRoute
Standard→Local circuit test). Once that connection was gone, nothing generated the `/16` toward
`er-eu2`; the remaining `conn-eu2-er2` has no route-map. Verified against the authoritative layer:

```powershell
az network express-route list-route-tables -g routemap-test-rg -n er-eu2 \
  --path primary --peering-name AzurePrivatePeering -o json
# er-eu2 holds only 192.168.2.0/23 (AS 65515) — no /16, no specifics
```

The connection enumeration confirmed the deletion — `conn-eu1-er2` no longer exists; the ER
connections are now `conn-eu1-er1`, `conn-eu2-er1`, `conn-eu2-er2`, none with a route-map.

| Metric | Iterations 1–9 | Iterations 10–30 |
|---|---|---|
| Branch `/16` present (`branch_p_all`) | 1 (all) | 1 (all) |
| `er-eu2` `/16` present (pri/sec) | 1 / 1 | **0 / 0** ← contamination begins |
| `er-eu1` `/16` leak | 0 | 0 |
| onprem specifics @ er-eu1 | 63 | 63 |
| Cause of er-eu2 change | — | `conn-eu1-er2` deleted out-of-band |

So the only trustworthy signal in this run is `branch_drops`, and it is **0**.

## Scale-up method (for reproducibility)

Two lockstep changes on the Megaport MCR were required to grow the ER-learned contributor set from
3 to 63 `/24`s (see `lessons-learned.md` for the full gotcha):

1. **VXC `ipRoutes`** expanded 3 → 63 (`PUT /v3/product/vxc/{uid}`, re-sending the entire aEnd
   interface incl. the full BGP config, or the session tears down).
2. **BGP export prefix-filter-list `7589`** expanded 3 → 63 permit entries
   (`PUT /v2/product/mcr2/{mcrID}/prefixList/7589`). This allow-list gates which prefixes the MCR
   advertises to Azure; adding `ipRoutes` alone is silently insufficient.

Verified via the authoritative MSEE table (`er-eu1`): all 63 `/24`s learned, AS-PATH `133937 ?`.

## Conclusion

- **No reproduction of the retirement** at 63 : 1 — consistent with the N=20 (3 : 1) result. Pure
  recompute remained deterministic at the branch across 30 cycles.
- The `er-eu2` anomalies are an **artifact of an out-of-band connection deletion**, caught by
  cross-checking the authoritative MSEE route table — a reminder that a harness anomaly flag is a
  hypothesis, not a finding, and that long sampling runs are fragile to concurrent environment change.
- The **Microsoft-recommended mitigation remains the correct deterministic fix** (drop AS 12076 before
  the `Replace` summarization rule), independent of whether the race can be triggered.
