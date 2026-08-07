# Oracle diagram replacement handoff

Niobe does not edit Oracle-owned diagrams. Apply these exact substitutions without changing geometry or stretching icons.

## `diagrams/01-topology.drawio`

| Existing text | Replacement |
|---|---|
| `Storage endpoint path-equivalence lab — switchable single-client topology` | `Translator endpoint path-equivalence lab — switchable single-client topology` |
| `RG: rg-storage-sepath-<RUN>` | `RG: <RESOURCE_GROUP>` |
| `account, blob` | `Translator account, request payload` |
| `System identity + Blob Data Reader` | `System identity + Cognitive Services User` |
| `Microsoft.Storage service endpoint` | `Microsoft.CognitiveServices service endpoint` |
| `pe-target-blob` | `pe-translator` |
| `privatelink.blob.core.windows.net` | `privatelink.cognitiveservices.azure.com` |
| `Target Storage account` | `Translator F0 account` |
| `<TARGET_STORAGE>` | `<TRANSLATOR_ACCOUNT>` |
| `Blob FQDN unchanged across modes` | `Custom Translator FQDN unchanged across modes` |
| `<PUBLIC_STORAGE_IP_PER_RUN>` | `<PUBLIC_TRANSLATOR_IP>` |
| `StorageBlobLogs source identity/status` | `Translator diagnostics and HTTP result` |
| edge target `storage` labels | Rename the cell ID only if desired; preserve edge geometry |

Live sanitized values: VM `10.61.1.4`, PE `10.61.2.4`, VNet `10.61.0.0/16`, client subnet `10.61.1.0/24`, PE subnet `10.61.2.0/24`, region `swedencentral`.

## `diagrams/02-experiment-comparison.drawio`

Replace all Storage account/blob references with the same Translator account and fixed 19-character translation request. Replace `Microsoft.Storage` with `Microsoft.CognitiveServices`, `<TARGET_STORAGE>` with `<TRANSLATOR_ACCOUNT>`, and `<PUBLIC_STORAGE_IP_PER_RUN>` with `<PUBLIC_TRANSLATOR_IP>`. Use `pe-translator` for the PE label.

For source-identity prose, use: `Service diagnostics may not expose the network source field; DNS, destination, effective route, subnet authorization, and HTTP result are authoritative customer-visible evidence.`

## `diagrams/03-performance-methodology.mmd`

Replace the obsolete Storage workload:

- concurrency: `1` only;
- payload: fixed JSON translation request, 19 input characters;
- repetitions: 10 blocks, 40 measured requests plus 20 warm-up requests per connection variant and mode;
- pacing: 0.5 seconds between calls;
- variants: fresh and reused HTTPS connection;
- throughput: successful requests/s and input bytes/s, not 8-MiB object transfer;
- quota guard: no concurrency 8/32 and no 8-MiB payload under Translator F0.

Keep the predeclared equivalence margins unchanged. Add the limitation that Translator processing latency dominates the small network-path delta and can make equivalence inconclusive.
