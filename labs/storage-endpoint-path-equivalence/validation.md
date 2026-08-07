# Validation — Translator endpoint path equivalence

**Run:** `sepath-validation-20260806T133000Z`  
**Observed scope:** Azure AI Translator F0, `swedencentral`, one Ubuntu 22.04 `Standard_B2ts_v2` client, one fixed small translation request.

## Method

Correctness and performance evidence are separate. Each transition first restored the documented public safe baseline, then applied only the requested scenario state. DNS caches and connections were cleared at measurement boundaries. No traceroute result or latency value is used to claim physical-path identity.

Performance used ten interleaved endpoint-order blocks, split into two five-block windows separated by 30 minutes. Every mode/variant used 20 warm-up and 40 measured requests, concurrency 1, a fixed 19-character input, and 0.5-second pacing. Fresh and reused HTTPS connections were measured separately. This F0-safe protocol intentionally omitted the obsolete Storage concurrency 8/32 and 8-MiB workload.

## Correctness checklist

| Scenario | Required observation | Verdict | Evidence |
|---|---|---|---|
| R1 Public | Public DNS/destination, no matching service-endpoint route, authenticated HTTP 200 | **PASS** | `raw-output/sepath-validation-20260806T133000Z/correctness/R1-public/` |
| R2 Service endpoint | Public destination retained; matching effective route becomes `VirtualNetworkServiceEndpoint`; ordinary and pinned requests succeed | **INCONCLUSIVE** — ordinary request and route passed; pinned-control output was lost to a Run Command failure | `raw-output/sepath-validation-20260806T133000Z/correctness/R2-service-endpoint/` |
| R3 Restricted subnet | Allowed subnet succeeds; removing only its rule makes the same principal/request fail; rule restored | **PASS** — HTTP 200 then HTTP 403 | `raw-output/sepath-validation-20260806T133000Z/correctness/R3-restricted-subnet/` |
| R4 Private endpoint | Same FQDN resolves to `10.61.2.4`; VNet-local `InterfaceEndpoint` route; approved PE; HTTP 200 | **PASS** | `raw-output/sepath-validation-20260806T133000Z/correctness/R4-private-endpoint/` |
| R5 Private only | Forced-public request fails while ordinary private-DNS request succeeds | **INCONCLUSIVE** — private request passed with public access disabled; forced-public output was lost to a Run Command failure | `raw-output/sepath-validation-20260806T133000Z/correctness/R5-private-only/` |

## Evidence inventory

- DNS: CNAME, A, AAAA, and `getent`.
- Destination: TLS peer address from the client and forced-public `curl --resolve`.
- Routing: NIC effective route table and Network Watcher next-hop query.
- Security: effective NSG and account network ACL snapshots.
- Private Link: PE connection, IP configuration, DNS link state.
- Service result: HTTP result, response byte count/hash, errors, and timeouts.
- Diagnostics: Translator diagnostic setting/log query and VNet flow-log configuration/query.
- Performance: per-request JSON plus block aggregates, VM CPU/credit snapshots, TCP retransmission proxy, and bootstrap analysis.

All published captures are sanitized. Subscription/tenant IDs, GUIDs, bearer tokens, credentials, account names, resource-group names, and public addresses are replaced with stable placeholders.

Translator diagnostics returned 200 recent rows (195 `Translate`, four `UpdateResource`, one `Vnet`). The configured VNet flow log was enabled and `Succeeded`, but the intended `AzureNetworkAnalytics_CL` query failed because that legacy table was absent; this is a telemetry limitation, not a request failure.

## Reproduction commands

```powershell
.\deploy\run-validation.ps1 -RunId '<RUN_ID>'
python .\analyze_results.py .\raw-output\<RUN_ID>
az network nic show-effective-route-table -g '<RESOURCE_GROUP>' -n nic-client -o json
az network nic list-effective-nsg -g '<RESOURCE_GROUP>' -n nic-client -o json
az network watcher show-next-hop -g '<RESOURCE_GROUP>' --vm vm-client --nic nic-client `
  --source-ip 10.61.1.4 --dest-ip '<DESTINATION_IP>' -o json
```

Scenario transitions are implemented in `deploy/set-scenario-state.ps1`; request generation is in `deploy/translator_benchmark.py`.

## Positive-control sensitivity calibration

The calibration was predeclared in
`raw-output/sepath-validation-20260806T133000Z/calibration/protocol.json` before
execution:

- ordinary public endpoint only; same VM, region, Translator account/backend,
  managed identity, request body, pacing, and reused HTTPS variant;
- 25 ms deterministic client-side delay inserted **inside** the measured interval
  immediately before request transmission;
- ten paired blocks, alternating `control→injected` and `injected→control`;
- 20 warm-up and 40 measured requests per arm, concurrency 1;
- expected p50 shift: 20–30 ms;
- detection requires the paired p50 95% bootstrap-CI lower bound to exceed the
  larger of the observed control noise floor, the 10% p50 equivalence margin, and
  5 ms.

This is a measurement-system positive control. It does not simulate an Azure
network path and cannot support a path-identity claim.

Calibration result: pending live-run analysis.

## Optional nearby-region extension — not deployed

A separately approved extension could compare the current `swedencentral`
Translator account with a new candidate account in `northeurope`, using the same
VM, identity model, request, client, pacing, and randomized account order. This is
**not** an endpoint-path-equivalence control: it changes service region and
backend/account, and therefore confounds network distance, Translator capacity,
regional load, account placement, and potentially SKU/quota.

Before deployment it requires a new Phase 0 SKU/quota/policy preflight and explicit
resource/cost approval. A second F0 allocation may be unavailable; no paid S1
fallback is authorized. No cross-region resource was created in this run.
