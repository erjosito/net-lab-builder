# D0 deployment — 2026-10-15

**PASS infrastructure / PASS deallocation. Traffic harness pending.**
Lease: `bandwidth-core-initial-deployment-20261015`, Tank, 07:33–08:03Z.
Closed completed at **07:42:07Z**; no owned child process remains running.
No traffic, billing collection, C/NE creation, context switch, provider
registration, installation, cleanup deletion or other lab mutation occurred.

## Gates and actual state

- Local PowerShell parser and ARM JSON/safety assertions passed.
- Explicit subscription and expected tenant equality verified privately.
  Microsoft.Compute and Microsoft.Network were already registered.
- Direct authenticated catalogue completed in **one page**, within its total
  120-second/10-page bound. B1ls and B1s were location restricted; B1ls was
  additionally excluded for its 0.5 GiB TLS/agent memory envelope. B2ts_v2
  was the first viable unrestricted ladder choice. Its zone restriction count
  was zero; deployment was **nonzonal**. No fallback/upgrade outside approval.
- Native ARM `deployment group validate` succeeded in the newly owned RG,
  with a private parameters JSON file. No VM created by validation.
- Actual deployment succeeded: three **Standard_B2ts_v2** Ubuntu 22.04 Gen2
  VMs (A/B/P), three 30 GiB StandardSSD_LRS disks, three NICs/NSGs, two
  Standard static IPv4 PIPs and two unpeered Sweden Central VNets.
  Required ownership tags verified on **all 16 resources**, including OS disks.
- Private inventory captured **07:39:20Z**, retaining resource IDs, creation/
  change timestamps, tags and provisioning state. Private power evidence
  captured **07:41:35Z**: A, B and P each `Succeeded` / `VM deallocated`.
  Actual successful provisioning, not catalogue/validation alone, establishes
  this allocation result.
- All inbound explicitly denied. P private-only; no implicit outbound or
  download bootstrap. No application listener or transfer service was deployed.

## Exact mutation commands (private identifiers substituted)

Every command used the installed CLI Python entry point, explicit
`--subscription <private-subscription>`, `--only-show-errors --output json`,
bounded child-process execution and lease/STOP checks. All deployment
parameters, including SSH key, were passed in JSON, never inline key/value.

```text
1 group create --name <owned-rg> --location swedencentral --tags lab=true created_by=copilot-lab run_id=<private-run>
2 deployment group validate --resource-group <owned-rg> --name <private-run>-validate --template-file <lab>\deploy\main.json --parameters @<lab>\private\deployment.params.json
3 deployment group create --resource-group <owned-rg> --name <private-run>-core --template-file <lab>\deploy\main.json --parameters @<lab>\private\deployment.params.json --mode Incremental
4 vm deallocate --resource-group <owned-rg> --name <private-run>-vm-a
5 vm deallocate --resource-group <owned-rg> --name <private-run>-vm-b
6 vm deallocate --resource-group <owned-rg> --name <private-run>-vm-p
```

**6/6 mutation slots** consumed, conservatively counting ARM validation.
Final owner accounting: **25/100 tool calls**, counting each invoked leaf tool
(not parallel-call containers); 22 at live lease closure, three local
documentation/closure calls afterward. No Azure command ran after closure.
Crossing the 80% mutation cutoff started no new work: the final deallocation
and closure were restoration only. Command timeouts: validation 120 seconds,
deployment 600 seconds, each deallocation 180 seconds. No timeout/retry occurred.
36 Azure CLI invocations total: 30 read-only, six mutation/gate commands;
one additional direct HTTPS catalogue request. CLI commands may internally
make multiple HTTP requests; this is not an HTTP-transaction count.

## Cost and next handoff

No billed-dollar assertion was made. Approved SC B2ts_v2 retail provenance is
$0.0108/VM-hour; the conservative three-slot planning envelope remains
$0.06273/hour, below $0.08/hour / $8 lifetime approval. Compute is now stopped,
but **three disks and two PIPs remain billable**; enforce <=72-hour lifetime.
Deletion is not approved or executed. Cleanup preview defaults safe; a fresh
lease plus explicit owner deletion confirmation is required.

Reproduction and limitations: [deploy/README.md](deploy/README.md).
Private evidence: `private\context.private.json`, `capacity.private.json`,
`gate.private.json`, `deployment.params.json`, `inventory.private.json`,
`power.private.json`; runtime lease is ignored. No names/IDs/keys are published.

Next D0 action requires a fresh scoped lease: implement the pinned-mTLS,
source-allowlisted bounded stream harness and only then open controlled private
443. Verify P management reachability before relying on run-command. A separate
validation lease owns any traffic; no transport or empirical billing claim yet.
