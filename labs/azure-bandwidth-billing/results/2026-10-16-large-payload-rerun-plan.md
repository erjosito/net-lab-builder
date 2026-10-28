# Larger ordinary-PIP rerun — 16 October 2026

**NOT DEPLOYED / NOT APPROVED.** Offline; no Azure calls.
azure-lab/squad gates apply. Old $8+$4 are NOT fresh money: T reserve spent,
core 3-GiB wire reserve insufficient. Old VMs/disks/PIPs deleted 16 October
00:00Z. Never touch/reuse old core RG or unknown-ownership NSG.

## Approval package

Three NEW tagged owned RGs:

| Slot | Native management / tenant | Region |
|---|---|---|
| A | Windows core | swedencentral |
| C | Windows core, same tenant as A | northeurope |
| T | WSL MSDN, tenant unequal to A/C | swedencentral |

Each: Ubuntu 22.04 Gen2 nonzonal Standard_B2ts_v2 candidate, 30-GB StandardSSD_LRS
disk (32-GiB tier), NIC, peer-only NSG, unpeered VNet/subnet, ordinary Microsoft
Standard static IPv4 PIP. Total 3 each + 3 RGs.
No peering/NAT/LB/proxy/BYOIP/CDN/private endpoints or auth/profile changes.
Reuse NEW T. Provision 5–15min after catalogue/quota/price/live-capacity gates
in both contexts. NOT manifest-locked; no silent substitutions.

Two phases, separate UTC billing days; four legs:
1. Same-region cross-tenant: **A→T, T→A**.
2. Cross-region cross-tenant: **C→T, T→C**, NOT old same-tenant C→B.

**100 decimal GB/leg = 100,000,000,000 bytes**, 400 GB total; recommended
**150 decimal GB/leg**, 600 GB total. NOT GiB. Pilot 1 GiB/leg INCLUDED, then:
- 100 GB: repeat 5 GiB **18** times + **2,289,494,016** bytes remainder.
- 150 GB: repeat 5 GiB **27** times + **3,971,111,936** bytes remainder.
20/29 requests/leg, pilot included; no retry.

## Money and time gate

[Official pricing](https://azure.microsoft.com/en-us/pricing/details/bandwidth/)
recorded in design.md: same-region zero is a hypothesis. Inter-region $0.02/GB
predicts **2×100×.02=$4 / 2×150×.02=$6**.
Internet 100-GB free tier is **monthly**, NOT daily/inter-region.
100 GB may be masked; 150 exceeds it, not billing proof.
Old C: 0.655125983 GB at $0.02 already billable, quantity unreconciled.

Worst case NO free tier: $.087/GB ALL legs +10% wire/ACK/bootstrap +$5 infra:

| Per leg | Aggregate wire ceiling | Traffic + infra | Proposed NEW cap |
|---|---:|---:|---:|
| 100 GB | 440 GB | $38.28 + $5 = **$43.28** | **$45** ($23 core/$22 MSDN) |
| 150 GB | 660 GB | $57.42 + $5 = **$62.42** | **$65** ($34 core/$31 MSDN) |

USD-equivalent caps; EUR credits require explicit FX.
Verify all-three infra ≤$0.08/h, resource TTL ≤48h,
allocation ≤12h/slot; 48×.08=$3.84 leaves $1.16 operations.
Unknown rates/FX/reserves: STOP. At 2,500,000 B/s per direction, 5 GiB needs
≥35.8min; 100/150 GB needs ≥11.11/16.67h per leg. Concurrent reverse traffic
does not halve a leg's duration. Two sequential bidirectional scenarios need
≥22.22/33.33h for T, excluding setup/hash/restore: neither fits its 12h
allocation limit. A configurable higher rate and a successful measured pilot
are prerequisites, not optional optimizations. No duration promise.

## Trinity: offline implementation handoff

Sources: design.md (labdesign.md absent), README.md,
transfers/{run.py,stream.py,test_stream.py,README.md},
deploy/{Control.ps1,Common.ps1,main.json,msdn-main.json}, costs/README.md.
Blockers: stream.py caps 5 GiB/request, 2,500,000 B/s, 2700s, 12-GiB wire.
run.py: 2400/2450/2500s guest/local bounds, old 35/23-GiB reserves,
same-tenant C→B gates. Control.ps1 requires old A/B, $8/TTL; manifests describe
old topology. Common.ps1 assumes 30-minute lease start.

Keep ≤5-GiB requests. Add an explicit configurable rate with unchanged safe
defaults; a 16-MiB/s-per-direction candidate needs pilot verification.
Add fresh inventory/scenario binding, repeat/remainder
ledger, immutable IDs, durable PRE-reserved wire/cost across restarts.
No failed/unknown refunds or payload resend. Count one endpoint RX+TX/pair,
not both; track producer TX/context; reserve in-flight/counter overshoot.
SHAKE/upfront digest/SHA256/TLS cost CPU; downloads stream 64-KiB reads.
Test repeat/remainder, crash/replay, wire/lease/STOP, unequal tenants, restoration.

## Execution and closure

After scripts finish/processes idle: separate deployment/readiness/
traffic-chunk/validation/cleanup leases; one owner/objective each.
No collector overlap. Traffic lease ≤60min/25 calls, mutations/timeouts explicit,
15min checkpoints, stop new work at 80%, restore ≤15min. Pilot PASS:
peers/count/hash, zero retries, wire margin and measured throughput projecting
completion within TTL/slot/chunk limits; otherwise STOP, not upgrade/retry.

Recheck lease/STOP/bytes/runtime/cost each chunk; Cost APIs cannot enforce spending.
Error/drift/cap risk: drain sockets/processes, remove
listener, restore BOTH NIC/subnet NSGs, deallocate; independent verification
before next chunk. Restore overrun: freeze, fresh recovery owner. No surviving
children; STOP cancel at 5min, terminate/freeze at 10min.

Capture inventory/IDs/reports; preview/delete only NEW RGs with cleanup approval.
Never retain VMs for billing lag.
After cleanup: public Query + Cost Details CLI, native contexts, inventory/UTC
dates, bounded requests at 24/48/72h/day7; two stable snapshots
≥6h apart. Reconcile quantity/unit/rate/currency/producer/day.
Missing meters: INCONCLUSIVE.

Single approval: volume/cap, three slots, pilot/full run and NEW-owned cleanup.
