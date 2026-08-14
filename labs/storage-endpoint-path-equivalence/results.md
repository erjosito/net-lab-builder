# Results — Translator endpoint path equivalence

**Run:** `sepath-validation-20260806T133000Z`

## Scope and interpretation

Results apply only to the observed time, `swedencentral`, Translator F0, the deployed account/PE, the single `Standard_B2ts_v2` client, concurrency 1, and the fixed small request. Conditional performance equivalence cannot establish identical Microsoft physical paths.

## Correctness

All five correctness scenarios passed. Focused SSH recovery replaced the two
outputs lost during Azure Run Command stalls: R2's authenticated,
SNI/Host-preserving public pin returned HTTP 200, and R5's equivalent forced
public request returned HTTP 403 while ordinary private DNS returned HTTP 200
from `10.61.2.4`.

## Performance protocol

The predeclared margins are:

| Metric | Equivalence margin |
|---|---|
| p50 latency | ratio 0.90–1.10 |
| p95 latency | ratio 0.85–1.15 |
| successful request throughput | ratio 0.90–1.10 |
| jitter, p95−p50 | ratio 0.80–1.20 and absolute difference ≤2 ms |
| error rate | absolute difference ≤0.5 percentage points |
| TCP retransmission proxy | absolute difference ≤0.2 percentage points |

The primary unit is the paired block aggregate. The analysis uses 10,000 cluster-bootstrap resamples by block and reports 95% confidence intervals. A CI crossing a margin is **inconclusive**, not proof of difference. A result outside a margin is labeled not equivalent only when the interval establishes that conclusion.

## Headline metrics

There were **2,400 measured requests**, **1,200 warm-up requests**, zero measured errors, and zero timeouts.
No block hit an invalidation threshold: maximum recorded VM CPU was 14.52%, and minimum remaining CPU credits were 60.61.

| Connection | Mode | p50 ms | p95 ms | Requests/s |
|---|---|---:|---:|---:|
| Fresh | Public | 64.22 | 158.22 | 1.639 |
| Fresh | Service endpoint | 60.50 | 165.40 | 1.704 |
| Fresh | Private endpoint | 71.44 | 161.49 | 1.669 |
| Reused | Public | 35.44 | 46.67 | 1.855 |
| Reused | Service endpoint | 34.81 | 45.96 | 1.858 |
| Reused | Private endpoint | 35.25 | 45.32 | 1.857 |

Values are geometric means of the ten block aggregates.

## Equivalence verdict

| Variant | Pair | p50 | p95 | Throughput | Overall |
|---|---|---|---|---|---|
| Fresh | Public↔SE | Inconclusive | Equivalent | Equivalent | **Inconclusive** |
| Fresh | Public↔PE | Inconclusive | Equivalent | Equivalent | **Inconclusive** |
| Fresh | SE↔PE | Inconclusive | Equivalent | Equivalent | **Inconclusive** |
| Reused | Public↔SE | Equivalent | Inconclusive | Equivalent | **Inconclusive** |
| Reused | Public↔PE | Equivalent | Equivalent | Equivalent | **Inconclusive** |
| Reused | SE↔PE | Equivalent | Equivalent | Equivalent | **Inconclusive** |

Every pair remained overall inconclusive because jitter and the sparse TCP retransmission proxy did not establish equivalence within their margins. This is a **statistical failure to establish equivalence**, not proof that the endpoint modes differ.

Machine-readable CIs and verdicts: `raw-output/sepath-validation-20260806T133000Z/analysis/equivalence-verdicts.json`.

## Measurement-sensitivity positive control

A zero-cost calibration held the deployed region, service account/backend,
request, identity, VM, public endpoint state, and reused-connection client constant.
It alternated control and a predeclared 25 ms delay inserted inside the measured
timer. Across **800 measured requests** and 400 warm-ups, the paired p50 shift
was **23.29 ms** with a 95% bootstrap CI of **22.08–24.48 ms**. There were zero
errors/timeouts. The CI lower bound exceeded the 5 ms detection floor and the
point estimate was inside the predeclared 20–30 ms range, so the sensitivity
verdict is **PASS**.

The calibration only tests whether this harness can detect a known perturbation.
It does not identify, emulate, or prove an Azure physical path.

Remaining measurement limits are unchanged: overall performance equivalence is
inconclusive because jitter and the sparse retransmission proxy did not meet
their margins; the legacy flow-log query table was absent; physical path
identity is not established.

## Optional nearby-region comparison

`northeurope` is documented as a candidate extension only. A second Translator
account would change both region and backend, making the comparison intentionally
confounded. It requires separate SKU/quota/policy preflight and resource/cost
approval; no cross-region resources were deployed.
