# Deployment — `storage-endpoint-path-equivalence`

**Status:** TRANSLATOR REDESIGN DEPLOYED · VALIDATION COMPLETE WITH TWO EVIDENCE GAPS · VM DEALLOCATED  
**Recorded:** 2026-08-05T17:52:19.278+02:00  
**Run:** `sepath-20260805-175837` · **Region:** `swedencentral`

The approved Azure AI Translator redesign is live. The existing VM, disk, NIC, VNet,
subnets, NAT Gateway/PIP, NSG, Log Analytics workspace, flow-log Storage account,
and VNet flow log were retained. The two blocked experiment Storage accounts and
their Blob PE/DNS and Storage endpoint-policy artifacts were deleted. No cleanup of
the lab was performed.

Niobe completed the live run on 2026-08-06. R1, R3, and R4 passed; R2 and R5 are
inconclusive because Azure Run Command lost the forced-public control outputs.
The 2,400-request performance program completed without measured request errors;
all overall equivalence verdicts are inconclusive. See `validation.md` and
`results.md`.

## Live resource state

- Translator: `aisepath0805175837`, `TextTranslation` F0, custom endpoint
  `https://aisepath0805175837.cognitiveservices.azure.com`.
- Authentication: VM managed identity with `Cognitive Services User`; local
  authentication is disabled. No key is used or stored.
- Translator networking: public access `Enabled`, default action `Allow`, no subnet
  rule. This is the safe R1 handoff state.
- Client subnet: no service endpoint and no endpoint policy.
- Private endpoint: `pe-translator`, Approved, static `10.61.2.4`.
- Private DNS: `privatelink.cognitiveservices.azure.com`; zone group exists, VNet
  link is absent in the R1 handoff state.
- Diagnostics: Translator all-logs/metrics to `log-sepath`; existing VNet flow log
  remains enabled and still uses the retained flow-log Storage account.
- VM: `vm-client`, private IP `10.61.1.4`, deallocated. Harness installed at
  `/opt/sepath/translator_probe.py`.

## Deployment validation

Single-request smoke probes succeeded without exposing credentials:

| Mode | Result |
|---|---|
| Public endpoint | HTTP 200 |
| `Microsoft.CognitiveServices` service endpoint | HTTP 200; effective routes included `VirtualNetworkServiceEndpoint` |
| Selected-network subnet rule | HTTP 200 |
| Private endpoint/private DNS | HTTP 200; DNS mode private and address `10.61.2.4` |
| Restored R1 public baseline | HTTP 200 |

This was deployment validation only, not Niobe's full five-scenario evidence run or
performance benchmark.

## Niobe handoff

Start the VM only for a validation window:

```powershell
az vm start -g 'rg-storage-sepath-0805175837' -n 'vm-client'
```

Converge each scenario state sequentially:

```powershell
$state = '.\labs\storage-endpoint-path-equivalence\deploy\set-scenario-state.ps1'
& $state -Mode Public           # R1
& $state -Mode ServiceEndpoint  # R2
& $state -Mode Restricted       # R3 positive
& $state -Mode Private          # R4
& $state -Mode PrivateOnly      # R5
```

Run the ordinary managed-identity probe after each positive transition:

```powershell
$mode = 'public' # use 'private' for R4/R5 ordinary-DNS probe
az vm run-command invoke -g 'rg-storage-sepath-0805175837' -n 'vm-client' `
  --command-id RunShellScript `
  --scripts "sudo resolvectl flush-caches || true; /opt/sepath/translator_probe.py --endpoint https://aisepath0805175837.cognitiveservices.azure.com --expect $mode"
```

R3 negative control: capture the subnet ID, remove only that rule, repeat the
identical request and require failure, then immediately restore `Restricted`:

```powershell
$subnetId = az network vnet subnet show -g 'rg-storage-sepath-0805175837' `
  --vnet-name 'vnet-endpoint-path' -n 'snet-client' --query id -o tsv
az cognitiveservices account network-rule remove `
  -g 'rg-storage-sepath-0805175837' -n 'aisepath0805175837' --subnet $subnetId
& $state -Mode Restricted
```

For R5's forced-public probe, use the R1-captured live public address with
TLS/SNI-preserving `curl --resolve`; acquire the bearer token from IMDS in memory
and never print or persist it. The ordinary probe must still resolve privately and
succeed.

After Niobe's work, return to R1 and deallocate:

```powershell
& $state -Mode Public
az vm deallocate -g 'rg-storage-sepath-0805175837' -n 'vm-client'
```

Sanitized evidence:
`raw-output/sepath-20260805-175837/11-translator-redesign-deployment.json` and
`12-translator-redesign-inventory.json`.

## Cost and cleanup

Translator F0 adds no hourly service charge within its allowance. The new private
endpoint replaces the deleted Blob private endpoint, so steady-state fixed
incremental cost versus the pre-redesign live lab is approximately **US$0/hour**.
Low-volume requests, network data, flow-log Storage, and Log Analytics remain
usage-based. No paid SKU fallback was used.

Cleanup remains separately gated and was not run. Preview only:

```powershell
.\labs\storage-endpoint-path-equivalence\deploy\cleanup.ps1 -CorrelationId 'sepath-20260805-175837'
```
