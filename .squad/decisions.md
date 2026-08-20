## Active Decisions

> Active decisions from all agents (merged by Scribe)


---


---



---

Foundry Lab Transition Plan — T2 Cleanup and T1 Deployment
**Author:** Trinity (Azure Network SME)
**Filed:** 2026-08-20T09:28:51+02:00
**Status:** DIRECTIONALLY AUTHORIZED by Jose (2026-08-20). No resources have been created or deleted.
**Summary in:** `labs/foundry-agent-prompt-vs-hosted-networking/design.md §14`

---

## Scope

This document governs the transition from the VPN/BGP topology (T2) to the peered tools VNet
topology (T1) for the `foundry-agent-reserved-prefix-reachability` and
`foundry-agent-prompt-vs-hosted-networking` labs.

Two independent gates control execution:

| Gate | Action | Trigger phrase |
|---|---|---|
| **Gate A** | Destroy T2 VPN/on-prem resources | Jose: **"DELETE APPROVED"** |
| **Gate B** | Deploy T1 peered-tools resources (billable) | Jose: **"DEPLOY APPROVED"** |

Neither gate implies the other. Both may be issued in any order or simultaneously.

---

## Gate A — T2 Cleanup (Destructive)

### A1. Evidence Preservation (required before any deletion)

All output files must be committed to the repo before deletion begins. Evidence is permanent
once captured; the live topology will be gone after teardown.

```powershell
# Prerequisites: az login, correct subscription selected.
# Replace <rg> with the actual resource group name (rg-foundry-reserved-<correlationId>).
$rg     = "<rg>"
$outDir = "labs/foundry-agent-reserved-prefix-reachability/raw-output"

# 1. Effective routes on vm-diag — proves 172.30.0.0/16 was learned via VirtualNetworkGateway.
az network nic show-effective-route-table `
  --resource-group $rg --name nic-vm-diag `
  --output json | Out-File "$outDir/pre-teardown-effective-routes.json" -Encoding utf8

# 2. VPN GW learned routes — records BGP table from vpngw-foundry before tunnel drops.
az network vnet-gateway list-learned-routes `
  --resource-group $rg --name vpngw-foundry `
  --output json | Out-File "$outDir/pre-teardown-learned-routes.json" -Encoding utf8

# 3. Advertised routes from vpngw-foundry toward the on-prem BGP peer.
$bgpPeer = az network vnet-gateway show `
  --resource-group $rg --name vpngw-foundry `
  --query "bgpSettings.bgpPeeringAddresses[0].defaultBgpIpAddresses[0]" --output tsv
az network vnet-gateway list-advertised-routes `
  --resource-group $rg --name vpngw-foundry --peer $bgpPeer `
  --output json | Out-File "$outDir/pre-teardown-advertised-routes.json" -Encoding utf8

# 4. VPN connection state.
az network vpn-connection show --resource-group $rg --name conn-foundry-to-onprem `
  --output json | Out-File "$outDir/pre-teardown-vpn-connection.json" -Encoding utf8
```

**Manual portal captures (Tank documents, Jose reviews):**
- VPN GW (`vpngw-foundry`) > Overview: tunnel status, connection name, IP addresses.
- VPN GW (`vpngw-foundry`) > BGP peers: peer IP, ASN, status, learned routes count.
- VPN connection (`conn-foundry-to-onprem`) > Overview: connection state, data transferred.

**Commit command (Tank):**
```bash
git add labs/foundry-agent-reserved-prefix-reachability/raw-output/pre-teardown-*.json
git commit -m "chore: pre-teardown evidence capture for T2 VPN cleanup"
```

---

### A2. Deletion Dry-Run Preview (not destructive)

Run cleanup.ps1 in its default **dry-run mode** (no `-AutoApprove` flag). The script lists
every resource in the RG without deleting anything.

```powershell
.\labs\foundry-agent-reserved-prefix-reachability\deploy\cleanup.ps1 -RgName <rg>
```

Review the output. The listing shows **all resources in the RG** (including shared infra);
it is not filtered to T2-only. Cross-reference against the T2 resource inventory in §A3 to identify
which resources are in scope. Shared resources (`vm-diag`, private endpoints, DNS zones, AI Search,
Cosmos, Storage) will appear in the listing and must be excluded from any deletion.

> **⚠️ cleanup.ps1 cannot be used for T2-only deletion.** Despite the dry-run listing being
> informative, executing cleanup.ps1 with `-AutoApprove` would delete `vm-diag` (shared) and the
> shared private endpoints (Step 4 of that script). It is safe to use for the resource listing
> only. See §A4 for the correct, T2-scoped `az` commands; those commands form the basis for the
> T2-only script that Tank must author and dry-run before Gate A3 is given.

---

### A3. T2 Resource Inventory (exact deletion scope)

Deletion is restricted to these named resources only. All others are preserved.

**VPN/connectivity layer (swedencentral + norwayeast):**

| Resource name | Type | Region | Stop charging |
|---|---|---|---|
| `conn-foundry-to-onprem` | VPN connection | swedencentral | $0.18/day |
| `conn-onprem-to-foundry` | VPN connection | norwayeast | $0.18/day |
| `vpngw-foundry` | VPN GW VpnGw1AZ | swedencentral | $5.04/day |
| `vpngw-onprem` | VPN GW VpnGw1AZ | norwayeast | $5.04/day |
| `pip-vpngw-foundry` | Standard Static PIP | swedencentral | $0.12/day |
| `pip-vpngw-onprem` | Standard Static PIP | norwayeast | $0.12/day |

**On-prem simulator (norwayeast):**

| Resource name | Type | Notes |
|---|---|---|
| `vm-onprem-echo` | VM B2ts_v2 | Delete VM, NIC (`nic-vm-onprem-echo`), OS disk (`osdisk-vm-onprem-echo`) |
| `vm-onprem-ctrl` | VM B2ts_v2 | Delete VM, NIC (`nic-vm-onprem-ctrl`), OS disk (`osdisk-vm-onprem-ctrl`) |
| `nsg-echo-vms` | NSG | Applied to WorkloadSubnet and CtrlSubnet in vnet-onprem |
| `vnet-onprem` | VNet | Subnets: WorkloadSubnet, CtrlSubnet, GatewaySubnet |

**NSG rules to remove from `nsg-agentsubnet` (swedencentral, post-teardown):**

| Rule name (approximate) | Source → Destination | Port | Remove when |
|---|---|---|---|
| allow-outbound-to-echo-onprem | Any → `172.30.100.0/24` | 80,443 | After vm-onprem-echo deleted |
| allow-outbound-to-ctrl-onprem | Any → `10.200.100.0/24` | 80,443 | After vm-onprem-ctrl deleted |

**Resources NOT deleted (shared Foundry infra — preserve):**

`vm-diag`, `nic-vm-diag`, OS disk for vm-diag, `nsg-mgmt`, `vnet-foundry` (all six subnets
including the empty `GatewaySubnet`), `pe-foundry-*` (x5 private endpoints), six private DNS zones
(`privatelink.services.ai.azure.com`, `privatelink.cognitiveservices.azure.com`,
`privatelink.openai.azure.com`, `privatelink.search.windows.net`,
`privatelink.documents.azure.com`, `privatelink.blob.core.windows.net`), Foundry account,
Foundry project, model deployment, AI Search service, Cosmos DB account, Storage account,
DNS Private Resolver (if deployed), DNS forwarding ruleset.

**Gross savings from Gate A:** ~$11.04/day.

---

### A4. Teardown Execution Order

Sequence is dependency-safe. Do not skip steps or reorder.

```
Step 1 — Delete VPN connections (both objects; ~60 s to reach Disconnected)
  az network vpn-connection delete -g <rg> -n conn-foundry-to-onprem --no-wait
  az network vpn-connection delete -g <rg> -n conn-onprem-to-foundry --no-wait
  Start-Sleep -Seconds 60

Step 2 — Delete VPN GWs (async; ~20 min each; both in parallel is safe)
  az network vnet-gateway delete -g <rg> -n vpngw-foundry --no-wait
  az network vnet-gateway delete -g <rg> -n vpngw-onprem --no-wait
  # Poll: az network vnet-gateway show -g <rg> -n vpngw-foundry --query provisioningState

Step 3 — Delete VMs + NICs + OS disks (after VPN GWs confirmed gone)
  az vm delete -g <rg> -n vm-onprem-echo --yes --no-wait
  az vm delete -g <rg> -n vm-onprem-ctrl --yes --no-wait
  az network nic delete -g <rg> -n nic-vm-onprem-echo --no-wait
  az network nic delete -g <rg> -n nic-vm-onprem-ctrl --no-wait
  az disk delete -g <rg> -n osdisk-vm-onprem-echo --yes --no-wait
  az disk delete -g <rg> -n osdisk-vm-onprem-ctrl --yes --no-wait

Step 4 — Delete NSG and VNet (after VMs confirmed gone)
  az network nsg delete -g <rg> -n nsg-echo-vms
  az network vnet delete -g <rg> -n vnet-onprem

Step 5 — Remove stale NSG rules from nsg-agentsubnet
  # Rule names may vary; identify by destination 172.30.100.0/24 and 10.200.100.0/24
  az network nsg rule delete -g <rg> --nsg-name nsg-agentsubnet -n allow-outbound-to-echo-onprem
  az network nsg rule delete -g <rg> --nsg-name nsg-agentsubnet -n allow-outbound-to-ctrl-onprem
```

> **⚠️ Cleanup.ps1 cannot be used as-is for T2-only teardown.** Inspection of `cleanup.ps1` Step 3
> shows `vm-diag` is included in the VM deletion list, and Step 4 deletes the shared private
> endpoints. Step 5 deletes the entire resource group. Executing cleanup.ps1 with `-AutoApprove`
> would destroy shared Foundry infrastructure.
>
> A dedicated, T2-scoped teardown script does not yet exist. Before DELETE APPROVED is given,
> Tank must: (a) author a script that deletes **only** the T2-named resources above, (b) run
> each `az resource delete` with `--dry-run` (or equivalent preview) and share the output for
> Jose review, and (c) confirm no shared resources appear in that preview. Only after that
> review may Gate A3 confirmation be given.

---

### A5. Gate A Confirmation

Gate A execution requires Jose to state, in the squad conversation:

> **"DELETE APPROVED"**

This phrase, in the squad conversation after reviewing the dry-run output and evidence files,
authorizes Tank to execute the T2-scoped teardown using the dedicated T2-only script (see §A2
above). That script must have been authored, reviewed, and dry-run verified before this gate
opens. Tank must not execute any destructive deletion without that script reviewed and this
phrase on record.

> **Do not run `cleanup.ps1 -AutoApprove`.** The existing cleanup.ps1 deletes `vm-diag` and
> shared private endpoints and is not scoped to T2 resources. It is only safe to use for the
> resource-listing dry-run (default mode, no `-AutoApprove`).

---

## Gate B — T1 Deployment (Billable Additions)

### B1. New Resource Plan (exact inventory, not yet created)

| Resource | SKU | Region | IP | Daily cost |
|---|---|---|---|---|
| vnet-tools | — | swedencentral | `10.1.0.0/16` | $0 |
| EchoSubnet | — | vnet-tools | `10.1.100.0/24` | $0 |
| CtrlSubnet | — | vnet-tools | `10.1.200.0/24` | $0 |
| VNet peering: vnet-foundry ↔ vnet-tools | bidirectional, intra-region | swedencentral | — | ~$0 |
| vm-tools-echo | Standard_B2ts_v2, Ubuntu 22.04 | swedencentral | `10.1.100.4` | $0.18 |
| vm-tools-ctrl | Standard_B2ts_v2, Ubuntu 22.04 | swedencentral | `10.1.200.4` | $0.18 |
| nsg-tools (new NSG, applied to both subnets) | — | swedencentral | — | $0 |
| DNS Private Resolver (if not already deployed) | 2 endpoints | swedencentral | inbound `192.168.3.4`; outbound `192.168.3.20` | $3.36 |
| DNS forwarding ruleset + VNet link to vnet-foundry | — | swedencentral | — | $0 |
| Hosted agent `echo-probe-agent` (source-ZIP) | per-session compute | swedencentral | — | ~$0.10–0.50/session |
| **T1 incremental total (with DNS resolver)** | | | | **~$3.72 + sessions** |

NSG rule additions to `nsg-agentsubnet` (outbound TCP 80+443 to `10.1.100.0/24` and
`10.1.200.0/24`, plus MCR and AzureActiveDirectory for hosted agent deploy) are $0 and are
not themselves billable; they are part of the same deploy wave.

### B2. What-If Preview (required before apply)

Tank runs the deploy pipeline in validate-only mode first. The T1 deploy artifacts
(`labs/foundry-agent-prompt-vs-hosted-networking/deploy/`) are staged but not yet authored.
Once staged, Tank runs:

```powershell
# Validate-only (no -Apply flag; no resources created)
.\labs\foundry-agent-prompt-vs-hosted-networking\deploy\deploy.ps1 -RgName <rg>
```

Jose reviews the ARM what-if output listing all resources that would be created before giving
Gate B confirmation.

### B3. Deployment Sequence

Follows `manifest.md §7` Wave 0–7:

```
Wave 0  vnet-tools + EchoSubnet + CtrlSubnet + nsg-tools
Wave 1  VNet peering: vnet-foundry <-> vnet-tools (bidirectional)
Wave 2  vm-tools-echo + vm-tools-ctrl (echo service + dnsmasq)
Wave 3  DNS Private Resolver (if not already deployed) + forwarding ruleset + VNet link
Wave 4  nsg-agentsubnet patch: add rules 110, 120, 125, 126
Wave 5  Connectivity verify: curl http://10.1.100.4/api/echo from vm-diag;
         nslookup echo.tools.lab from vm-diag
Wave 6  Hosted agent echo-probe-agent (Jose deploys via VS Code Foundry Toolkit)
Wave 7  Scenario runs HS1 -> HS2 -> HS3/HS4 -> HS5
```

### B4. Gate B Confirmation

Gate B execution requires Jose to state, in the squad conversation:

> **"DEPLOY APPROVED"**

This phrase authorizes Tank to run the deploy pipeline with `-Apply`. Jose should state this
after reviewing the what-if output from B2 and confirming the cost table in B1 is acceptable.

---

## Cost States Summary

| Gate A | Gate B | Running cost/day | Notes |
|---|---|---|---|
| Not cleared | Not cleared | **~$18.63** | Current state |
| Not cleared | Cleared | **~$18.99** | T1 added; T2 still running (parallel) |
| Cleared | Not cleared | **~$7.59** | T2 gone; T1 not yet deployed; Foundry infra only |
| Cleared | Cleared | **~$7.59** | Optimal; T2 gone, T1 active; shared Foundry infra still running |

Savings from T1 transition (~$11.04/day) are realized only when Gate A completes.

---

## References

| Source | Used for |
|---|---|
| `design.md §14` (this lab) | Gate summary and gate-independence statement |
| `morpheus-foundry-topology-rethink.md §7` | Original teardown sequence (R3 Phase 2) |
| `morpheus-foundry-lab-restructure.md` | Shared infra boundary; original cleanup gate conditions |
| `deploy/cleanup.ps1` | Dry-run (no -AutoApprove) + authorized deletion tool |
| `deploy/deploy.ps1` | Validate-only + authorized deployment tool |
| `raw-output/foundry-chat-evidence-20260814.json` | H1 confirmation; permanent; must survive Gate A |
| `results.md` (sibling lab) | S3/S4 evidence; permanent; must survive Gate A |

---

# Trinity Network Design — Foundry Prompt-vs-Hosted Lab
**Author:** Trinity (Azure Network SME)
**Filed:** 2026-08-20T09:10:41+02:00
**Lab:** `labs/foundry-agent-prompt-vs-hosted-networking/`
**Status:** LOCKED — corrections for Morpheus/Oracle; design.md authoritative

---

## Correction C1 — MCR Firewall Requirement Scope (Blocking)

**Manifest §6 Preflight** states: "McR.microsoft.com outbound from AgentSubnet | curl -sI https://mcr.microsoft.com | HTTP 200 or Trinity decision to use `bundled` mode"

**Precise correction required:** The framing implies `bundled` mode eliminates the MCR requirement. It does not. Microsoft docs (learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent-code, "Firewall requirements for private virtual networks", accessed 2026-08-20) state:

> "All source-code deployments require outbound access to: 1. `mcr.microsoft.com` 2. `*.login.microsoft.com`"

`bundled` mode pre-bundles user Python dependencies into the zip, eliminating the server-side pip install. However, the base container runtime image is pulled from MCR at Micro VM startup regardless of dependency resolution mode. There is no source-code deployment code path that avoids MCR.

**Required manifest change:** Update the preflight row to: "Required for ALL source-code deployments regardless of `--dep-resolution` choice. Verify before Wave 6 with OQ4 diagnostic command." See `design.md §6` for the exact diagnostic command.

**NSG implications:** NSG rules 125 (MicrosoftContainerRegistry, TCP 443) and 126 (AzureActiveDirectory, TCP 443) must be added to nsg-agentsubnet for ALL hosted agent deployments. Design.md §7.2 specifies these rules.

---

## Correction C2 — Extension Brief Zone Names Superseded (Informational)

`morpheus-foundry-hosted-agent-extension.md` (v1.1, filed 2026-08-19) uses zone `onprem.lab` targeting `172.30.100.4`/`10.200.100.4` (T2 VPN topology). This is the sibling lab's DNS config. The `foundry-agent-prompt-vs-hosted-networking` lab uses zone `tools.lab` targeting `10.1.100.4`/`10.1.200.4` (T1 peered topology). The extension brief is a historical planning artifact for the sibling lab extension proposal; it does not govern the new lab.

No manifest change needed. Oracle diagram updates should use `tools.lab` and T1 VNet addresses.

---

## Correction C4 — NSG Rules 125 + 126 Missing from Manifest §4 (Blocking)

**Manifest §4 NSG requirements** (nsg-agentsubnet additions) lists only rules 110 and 120 (outbound
TCP 80+443 to 10.1.100.0/24 and 10.1.200.0/24). It is missing two rules required for any
source-code hosted-agent deployment:

| Priority | Direction | Destination | Port | Purpose |
|---|---|---|---|---|
| 125 | Outbound | `MicrosoftContainerRegistry` (service tag) | 443 | Base container image pull from mcr.microsoft.com (required for BOTH remote_build and bundled) |
| 126 | Outbound | `AzureActiveDirectory` (service tag) | 443 | *.login.microsoft.com for Micro VM authentication |

These rules must be added to nsg-agentsubnet before Wave 6 (hosted agent deployment). They are
not optional and cannot be substituted by switching dep-resolution modes. The preflight check
`curl -sI https://mcr.microsoft.com` from vm-diag (via run-command) must pass before Wave 6.

**Required manifest §4 addition:** Add rows 125 and 126 to the nsg-agentsubnet outbound table.
**Preflight row (§6) correction:** Remove "OR Trinity decision to use `bundled` mode." Replace with
"Required for ALL source-code deploy modes. Apply rules 125+126 if check fails."

---

## Design Decision Summary for Morpheus/Oracle

| Decision | Choice | Rationale |
|---|---|---|
| DNS topology | Z2 (DNS Private Resolver + dnsmasq) | Full query observability; OQ5 empirical gate; Z1 is authorized fallback only |
| HTTP vs HTTPS | HTTP-first on port 80 | Eliminates TLS hostname SAN as a variable; HTTPS upgrade after HTTP baseline confirmed |
| dep-resolution | `bundled` recommended | Deterministic deploy; MCR NSG required regardless |
| peering flags | allVNAccess=true, no gateway transit | No GWs in either VNet; straightforward non-transit peering |
| MCR NSG | NSG rules 125+126 always required | Docs confirm both modes need MCR and AAD |

---

## What design.md Corrects in the Manifest (summary)

The design.md is internally correct; the manifest §6 preflight MCR row requires the wording update described in C1 above. No topology, IP plan, scenario, or cost figures in the manifest are incorrect.



