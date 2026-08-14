# Lessons learned — Translator endpoint path equivalence

## Protocol changes forced by Translator F0

The original Storage workload was not portable to Translator F0. Concurrency 8/32 and 8-MiB transfers would test quota behavior and application processing rather than endpoint-path performance. The approved F0-safe adaptation used concurrency 1, a fixed 19-character request, 0.5-second pacing, and fewer than 5,000 calls. Throughput therefore means successful requests/s and input bytes/s, not bulk-object MiB/s.

## Evidence hierarchy

DNS, actual destination, Azure effective routes, account/subnet authorization, PE state, and the HTTP result are the correctness authorities. Delayed service/flow diagnostics are corroborative. Translator processing time can dominate the network delta, so a wide confidence interval is expected and must be reported as inconclusive rather than “the same.”

## Operational anomaly

The first VM start remained in `ProvisioningState/updating`, and Run Command could not execute. A normal deallocate/start retry did not clear it. A direct ARM redeploy request restored `ProvisioningState/Succeeded`; no topology or benchmark result was changed. The recovery is environmental/configuration-related and occurred before measurements.

Run Command later stalled again while collecting the R2 and R5 forced-public
controls. A subsequent ARM redeploy also remained stuck in `Updating`. Recovery
therefore used only already deployed resources: the existing NAT public IP was
temporarily attached to the VM NIC, SSH was source-restricted, and the same
endpoint FQDN/SNI/Host/body/managed-identity semantics were exercised directly.
R2 returned HTTP 200; R5 returned HTTP 403 on the forced-public address and HTTP
200 on the private address. The public IP, NAT association, NSG, account ACL,
service endpoint, and private-DNS state were then restored to the original safe
public baseline before deallocation.

## Performance interpretation

Persistent connections roughly halved observed latency (about 35 ms p50 versus 60–71 ms for fresh TLS). Reused-connection p50, p95, and throughput commonly met their individual margins, but jitter and retransmission-proxy intervals were too wide. All overall pair verdicts are therefore inconclusive, not different.

## Diagram ownership

The existing Oracle diagrams still describe the superseded Storage workload. Niobe did not alter their geometry. Exact live-value and wording substitutions are in `diagram-replacement-handoff.md`.

## Sensitivity calibration

A known client-side delay is a useful positive control because it answers a
different question from endpoint equivalence: whether the measurement pipeline can
detect a shift larger than its own noise and predeclared margin. The delay must be
inside the timed interval, balanced in order, and removed afterward. It must not be
described as a network-path emulator.

The completed calibration detected a 23.29 ms paired p50 shift (95% bootstrap CI
22.08–24.48 ms) from the predeclared 25 ms injection, across 800 measured
requests with zero errors/timeouts. This validates sensitivity at that scale,
not endpoint equivalence or physical-path identity.

## Nearby-region extension boundary

A `swedencentral` versus `northeurope` Translator comparison may be operationally
interesting, but it changes the account/backend, service region, capacity pool, and
network distance simultaneously. It is a confounded extension, not a cleaner
version of this experiment. It remains undeployed pending separate approval.
