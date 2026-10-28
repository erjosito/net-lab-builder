# 15 October 2026: successful inter-region transport control

**Updated 2026-10-16 UTC. Transport PASS · restoration PASS · billing
INCONCLUSIVE · known-owned cleanup PASS, unknown roots preserved.**

The original A ↔ T same-region cross-tenant **5 GiB each direction PASS**
is unchanged. This separate control is **C / North Europe → B / Sweden
Central**, in the same core subscription/tenant, with an isolated producer RG.
It is successful **expected-charged inter-region transport**, not yet a
billed positive control or an invoice-level conclusion.

## Root identified and correction verified

Read-only inspection of the closed v3 network path identified an additional
**B subnet NSG**, with no custom inbound allow and default **DenyAllInBound
at priority 65500**. Allowing C's public source only on B's NIC NSG could not
admit TCP443 through both layers. The earlier `Updating` response alone was
not proof of the cause. v1 FAIL, v2 BLOCKED and v3 transport FAIL
remain historical; the current packet-path blocker is now identified.

The corrected runner binds owned tags, exact NIC/subnet/VNet references and
both NSG policies to fresh source-bound readiness. Both layers receive the
peer-only TCP443 allow and must read `Succeeded` before guest submission.
Restoration submits each original policy **once**, both PUTs before completion
polling, with fair allocations inside one shared **900-second** reserve.
**100 WSL tests passed**; ordinary reads remain bounded at 90 seconds,
setup at 200 seconds, and each guest submission still requires 3,400 seconds
remaining **after authorization**. No reserve or budget was enlarged.

## Exact v4 result

| Signal | Verified evidence, UTC on 15 October |
|---|---|
| Live invocation | **23:06:00.863841–23:19:39.519811**, one invocation |
| Bulk upload | **23:08:23.264113–23:15:32.795274**, 429.531161 seconds |
| Payload at each endpoint | **1,073,741,824 bytes (1 GiB)** |
| Requests / retries | **One upload at each endpoint, zero bulk retries** |
| Rate limit | **2,500,000 bytes/s** |
| C NIC RX+TX counted once | **1,085,524,745 bytes**, not billed quantity; never add B |
| Live owner | **48 calls, 10 mutations**, exited with no owned active commands |
| B / C verified deallocated | **23:16:45 / 23:17:31** |
| Original B NIC / subnet NSG verified | **23:19:00 / 23:19:23**, both `Succeeded` |
| Independent validation | **23:25:22**, PASS, **11 reads, zero mutations**; exact original policies and associations, both VMs deallocated, native children idle |

Matching SHA256 at both endpoints:

```text
e6cbc4b20371fff3ba9a14b0b90e29ba996a786c48b67151ca0e5fbbafa11a2d
```

The default one-way control remains **5 GiB**. v4 explicitly selected **1 GiB**
with a **2 GiB wire reservation**: the reconciled **5 GiB** remaining before
v4 became **3 GiB (3,221,225,472 bytes)** conservatively reserved afterward.
This is reservation accounting, not measured payload use or permission for
another transfer. $8 core / $4 extension remain inherited caps, not actual bills.

At Europe's published **$0.02 per decimal GB planning rate**, 1 GiB is
1.073741824 GB, approximately **$0.0214748 before overhead**. This is neither
an observed account rate nor an actual cost.

## Billing remains pending

The [23:28Z bounded billing snapshot](2026-10-15-control-billing.json) made
**three billing HTTP attempts, zero retries/mutations**. A has the same three
tiny daily positive rows totaling **USD 0.0000728753264993429373**, with no
quantity/unit/rate or per-request attribution. C has **no returned Bandwidth
Query rows** and its details request timed out; T's Query is empty. These are
missing ingestion/attribution evidence, **not zero-dollar proof**. See the
[detailed billing verdict](2026-10-15-billing-verdict.md).

| Target | Earliest UTC |
|---|---|
| Headline 24h | **2026-10-16T10:40:28Z** |
| Control 24h | **2026-10-16T23:15:33Z** |
| Control 48h | **2026-10-17T23:15:33Z** |
| Control 72h | **2026-10-18T23:15:33Z**, after original **18 October 07:33Z** TTL deadline |

These are unscheduled read-only follow-up targets. No more transfers are needed;
query actual **15 October usage** using private historical IDs after cleanup.
A Windows control cannot establish MSDN feed completeness.

## Cleanup closure and preserved exception

Known-owned cleanup ran from **15 October 23:44:50Z** to closure at
**16 October 00:00:11.806224Z** (~15.4 minutes), **76 calls / 11 mutations**,
PASS, no active commands and owned processes idle. The **13 remaining proven
original core assets are verified absent** (original 17 minus four earlier
P retirements); C and T groups are verified absent. All known lab VMs, disks
and public IPs are deleted.

**The core RG was not deleted.** An additional core NSG and that RG were
preserved because independent creation ownership could not be proven.
Observed tags or associations alone do not authorize adoption/deletion.
The NSG associations naturally disappeared with deletion of the owned VNets.
RGs and ordinary NSGs have no standalone hourly rent; no known lab VM/disk/PIP
rent is expected to continue. Unknown roots remain out of scope for future
manual review: this is **known-owned cleanup PASS, not an empty-core-RG claim**.
The earlier whole-core cleanup BLOCKED record remains historical; exact-owned
root cleanup resolved the known-owned assets without deleting unknown roots.

The [independent cleanup recheck](2026-10-16-cleanup.json) at **00:03:17Z**
reported **seven reads / zero mutations** and the same known-owned absences.
Only its final raw response was persisted; the reported call count is not a
complete retained request-by-request audit trace.

Private authority: v3 `network-subnet-inspection.private.json`, v4
`live-closure.private.json` and `v4independent-validation.private.json`, and
`cleanup-owned-roots-20261015T234450Z\closure.private.json`.
This report was prepared offline: no Azure/authentication/package operations
or new payload. Public output excludes actual identities, resource names,
addresses and credentials.
