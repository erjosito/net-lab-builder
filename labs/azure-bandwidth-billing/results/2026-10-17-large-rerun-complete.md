# Large public-IP rerun — 17 October 2026

Snapshot: **23:05Z**. **Transport PASS; cleanup PASS; billing INCONCLUSIVE.**

## What completed

Exactly **100,000,000,000 application bytes per direction** on A ↔ T
(Sweden Central ↔ Sweden Central) and C ↔ T (North Europe ↔ Sweden Central).
Both endpoint pairs are in different tenants; A and C share a tenant.
Total: **400,000,000,000 bytes**, or 400 decimal GB, with zero bytes remaining.

Each leg comprises one 1,073,741,824-byte chunk, eighteen 5,368,709,120-byte
chunks and one 2,289,494,016-byte final chunk. All **80 directed chunk
transfers** have matching producer/consumer counts and SHA256, with **zero
payload retries**. Digests apply to individual chunks, not a concatenated
100 GB stream. The [machine-readable completion](2026-10-17-large-rerun-complete.json)
summarizes each leg; [sanitized public proofs](2026-10-17-large-rerun-digest-proofs.json)
retain each directed chunk's counts, endpoint digests and UTC times.
The offline check recomputed both endpoint legs-object identities against the
ledger before stripping identifiers and peer addresses.

**Not a failure-free execution:** two failed/unknown reservations remain
preserved with zero payload credit; verified recovery records are separate.
The [16 October partial result](2026-10-16-large-rerun-partial.json) remains
unchanged as history, not the final volume.

## Bytes, guardrails and cleanup

Client-NIC RX+TX counted once per completed pair totals **403,432,913,305
measured bytes**. Conservative reserved wire is **461,173,529,602 bytes**,
including failed reservations and the shared bootstrap reserve. These are
different accounting measures, neither equal to billed volume.
The final **470 GB wire ceiling / 86,400 seconds per VM (24 hours)** were
coordinator-selected bounds under autonomous-completion authority, not numeric
limits selected by the user. The 25% forecast margin remained; financial mode
was monitor-only, with **no fixed monetary cap** (the old USD 45 was removed).

[Independent cleanup](2026-10-17-large-rerun-cleanup.json) closed at
**22:49:03Z on 17 October**: three owned RGs absent, all 21 owned resource
roots closed, before midnight and the original 18 October 07:33Z deadline.
Proof uses independent parent-RG absence and supporting root checks, not a
claim of 21 fresh direct root GETs. Original disk SKUs were restored before
deletion; no rerun VMs, disks or public IPs remain. Unknown historical assets
were not adopted or deleted. The exact billing inventory is retained privately.

## What the actual bill currently says

The [23:01–23:02Z collection](2026-10-17-billing-refresh-230000.json) completed
an **API-generated ActualCost Cost Details CSV** download for fresh C,
not a portal export. Three October-17 `Intra Continent Data Transfer Out`
rows total **10.8746547754853965 × reported “1 GB” × USD 0.02 =
USD 0.21749309550970793**. A separate two-row `Standard Data Transfer Out`
total is 0.000016549602150917 “1 GB”, USD 0.0000013736169785261154000000,
at USD 0.083 per reported unit.

**Nonzero cross-region charging is demonstrated, but only partial volume
is reported.** The 100 GB C → T leg and all 400 GB are not reconciled.
“Intra Continent” is not “intra region.” Raw units are preserved; no binary/
decimal conversion or per-chunk billing attribution is assumed.

The separate C/A/T ResourceId+Meter Queries each returned **HTTP 429**, not
zero usage/cost. Fresh A/T CSVs were not refreshed. Missing same-region rows
cannot establish zero price, free transfer, or offer/credit treatment.
CSV extraction `COMPLETE` is not final ingestion; there is no
`DataIngestionEndMT` watermark. The request used actual UTC date October 17,
not future October 18; report midnight endpoints do not prove full-day coverage.
The historical 1-GiB C → B control's 0.6551259830594063 “1 GB” remains
**STALE**, not this fresh-C observation.

Cleanup job 3 is **STOPPED**. Existing six-hour read-only billing follow-up
retains its original **22 October 23:15:33Z hard stop**; it is **not complete**.
This offline preparation made no Azure, billing, authentication, schedule or
source-code changes and performed no git publication.
