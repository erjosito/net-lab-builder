# A ↔ T bounded public-IPv4 transfer

**Offline implementation; no Azure commands or Azure traffic were run.**
Only A (Windows CLI context) and T (native Ubuntu-24.04 WSL CLI context)
participate. B/P remain deallocated. Python 3 standard library; existing OpenSSL
is required locally for certificate generation. No package installation,
SSH, authentication changes, profile copying, or arbitrary endpoints.

## Contract and deliberate concurrency change

Both HTTPS connections originate at A and terminate on T: upload produces
**5,368,709,120 bytes at A**, download produces **5,368,709,120 bytes at T**.
One client invocation runs **exactly two concurrent HTTP requests, one in each
direction**, rather than the old design's concurrency-one sequencing. Each
direction retains the original 20 Mbit/s (2,500,000 bytes/s) rate and 5 GiB cap.
The approximately 35.8-minute bulk interval therefore fits a 60-minute live
lease with restoration reserved; TCP initiator is not the byte producer.

The guest uses mTLS, an ephemeral private CA, IP SAN verification, TLS ≥1.2,
HTTP/1.1, no cache/compression, exact paths and one-use IDs. Payload blocks are
SHAKE256-derived from a fixed seed and block offset, bounded to 64 KiB, streamed
without disk storage. Each endpoint records incremental SHA256 and exact counts.
Upload acknowledgement is written only after the server's private record;
download hash is checked against the server's literal header and final report.
Two worker slots, 32 lifetime connection attempts, 60-second socket timeout,
40-minute total guest deadline, 2,450-second guest process timeout and
2,500-second local RunCommand limit bound execution. These are **tighter** than
the requested 45-minute transfer / 50-minute listener maximums.

Client readiness uses at most 12 authenticated **handshake-only** probes before
either HTTP request. Probe timestamps, statuses and zero payload bytes are
separate from bulk records. The successful handshake's connection is reused for
upload, avoiding an extra probe racing with the two-slot limit. Certificate/TLS
failure stops readiness immediately. Neither bulk request is ever retried. A failed
request cancels its peer and closes both sockets; server errors stop the listener.
Guest commands run in the foreground, not as detached services.
The local wrapper writes a private running heartbeat every 30 seconds during
each long command; the guest socket/total deadlines enforce actual progress.

Each endpoint reads Linux `/sys/class/net/<interface>/statistics/{rx,tx}_bytes`.
Use **A's RX + TX delta once**, never A plus T. Stop at A's 12 GiB aggregate
NIC delta; the same conservative cap is also applied at T. Preserve the core
35 GiB global allowance by supplying its **actual remaining** value; preparation
requires ≥12 GiB remaining. The MSDN 10 GiB payload reserve plus existing overhead
headroom is unchanged; this is not approval to enlarge either $8/$4 budget.

## Offline preparation and tests

From repository root, PowerShell:

```powershell
python -m unittest discover -s labs\azure-bandwidth-billing\transfers -p test_stream.py -v
python labs\azure-bandwidth-billing\transfers\run.py prepare --run saas-20261015-handoff --core-remaining-bytes 37580963840
```

The prepared `saas-20261015-handoff` directory already exists; preparation
intentionally refuses to overwrite it. Use a new run name if regenerating.
The last argument above is valid only while no earlier core traffic has consumed
the allowance. Preparation makes **zero Azure calls**, reads only approved
private inventories/contexts, and writes only `private\transfers\<run>\`:

- `plan.private.json`: private identities, caps and endpoint bindings;
- `commands.private.json`: exact argv manifests before native path conversion;
- `tls\`: one-day CA/server/client certificates and private keys;
- `live-lease-template.private.json`: inactive template for the next owner.

Keys and reports are ignored by the lab's existing `.gitignore`. No actual
identity, IP, key or resource name is present in this directory's source.
Windows uses the installed Azure CLI Python entrypoint with argument arrays;
WSL uses `/usr/bin/az` behind its native bounded `timeout`, with native tokens
remaining in WSL. Every Azure invocation has explicit `--subscription`.

## Handoff: exact next live invocation

**Do not execute under the offline build lease.** A fresh owner must create
`deploy\.runtime-control\transfer-live-lease.json` from the private template,
set `state=active`, current `startedAtUtc`, expiry exactly 60 minutes later,
and name the long commands/timeouts. Reserve **10 mutation submissions**:

| Operation | Count |
|---|---:|
| `start-a`, `start-t` | 2 |
| `allow` (one NSG PUT: peer-only 443 at 100, original deny at 200) | 1 |
| `server`, `client` (foreground RunCommand, concurrent) | 2 |
| `restore-nsg`, `deallocate-t`, `deallocate-a` | 3 |
| `emergency-deallocate-t`, `emergency-deallocate-a` recovery reserve | 2 |

Normal path is **8 mutations**, with two explicitly named recovery reserves,
not automatic bulk retries. An emergency is handled by a named recovery owner;
the wrapper does not silently consume those reserves. CLI errors are private.
No new work at 80% of elapsed/call/mutation budget; restore-only operations
remain available while the lease is active and STOP is absent.

```powershell
python labs\azure-bandwidth-billing\transfers\run.py snapshot --run saas-20261015-handoff
```

This read-only stage checks both native account/tenant contexts, exact owned tags,
same region and deallocated baseline; captures A/T VM/NIC/PIP/NSG identities;
binds A's observed PIP into T's peer check; prepares root-only guest scripts and
the exact original NSG restore body. T's PIP must still match its certificate.
It **does not open ports or start VMs**. Snapshot must be <10 minutes old at live
start. Only the known single deny-100 T baseline is accepted.

Before attesting, the live owner must independently confirm:

- A/T ownership, native tenants unequal, both Sweden Central, expected PIP/NIC
  associations and routes; no other bulk producer/RG scenario that UTC day;
- source observed at T must be A's PIP; literals are used, so there is no
  unverified DNS redirect; certificate SAN binds the literal T address;
- A/core and T allocated-hour limits ≤12 each, budgets $8/$4 unchanged,
  ≥12 GiB core wire allowance remaining, and enough same-UTC-day time;
- existing guest Python 3, `timeout`, CA permissions and chosen NIC interface
  (`eth0` by default; edit private plan `interface_server/interface_client`
  **before snapshot** if the baseline establishes another interface);
- guest RunCommand support and NSG PUT authorization; no apt/pip bootstrap.

Then the **single foreground owner invocation** is:

```powershell
python labs\azure-bandwidth-billing\transfers\run.py live --run saas-20261015-handoff --accept-live-gates
```

The orchestrator collects metric baselines, starts A/T, installs the peer-only
T rule, submits server/client concurrently, verifies both reports, and in
`finally` attempts the original NSG PUT and both deallocations exactly once.
It checks exact original security-rule equality and `PowerState/deallocated`.
Metric windows are collected afterward. No A inbound rule is added.
The local 2,500-second bound plus 15-minute restore reserve must fit remaining
lease time: slow start/readiness can safely **BLOCK** rather than extend the lease.

For an explicitly supervised split workflow, the same wrapper exposes
`start-a`, `start-t`, `allow`, `server`, `client`, `restore-nsg`,
`deallocate-t`, `deallocate-a`, `metrics`, `verify`, all with `--run <run>`.
`server` and `client` must overlap; never wait for server completion before
starting client. The split owner must provide its own **finally** restoration
and close its lease; prefer `live`, which does both automatically.

## Evidence, stop criteria and remaining boundaries

Private files include `*-before.private.json`, `*-metrics-baseline.private.json`,
`server.private.json` / `client.private.json` (raw RunCommand responses),
`server-report.private.json` / `client-report.private.json`,
`verdict.private.json`, `nsg-restored.private.json`,
`deallocate-*-verified.private.json`, metric-after windows and final plan.
Guest directories are `/root/bwb-transfer-<id>` with mode-600 material and a
key-removal trap. Only compact final JSON is stdout (RunCommand's ~4 KiB limit);
truncated/missing reports fail closed. Guest report writes precede upload ACK.

Stop on any mismatched peer/hash/count/status, timeout, wire cap, ownership or
budget gate, STOP, stale lease, unavailable tools or unsuccessful restore.
No retry, replacement endpoint, implicit package installation or spending
increase. If restoration cannot be verified inside the reserve, return BLOCKED
and assign a fresh recovery owner; never claim that cancelling a local CLI
necessarily cancels an Azure operation. Guest and native process deadlines are
independent safeguards; verified deallocation is the final kill boundary.

**Transport PASS is not a billing exemption verdict.** This same-region
customer-SaaS case has no same-offer mature inter-region positive control today;
billing remains **INCONCLUSIVE** pending the planned mature quantity/rate
evidence. Azure metrics corroborate traffic only.

Local tests cover mTLS rejection, wrong SAN, exact concurrent hashes, strict
length/chunking bounds, truncation/corruption, idle timeout, two-slot rejection,
one-shot lifecycle, pacing, NIC shape/no double sum, report mismatch/truncation,
lease budget/restore gates and finally restoration. Test payloads are small
localhost-only (32 KiB per successful direction); certificates stay lab-private.
**Latest validation: 20 tests PASS**, with the complete output at
`private\transfers\local-tests\test-results.private.txt`.
Azure RunCommand timing, actual guest tool/NIC availability and ARM restoration
semantics remain **live acceptance gates**, not claims established offline.
