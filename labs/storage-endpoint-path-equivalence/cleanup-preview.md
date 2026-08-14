# Cleanup preview — storage endpoint path equivalence

**Generated:** 2026-08-08  
**Mode:** Read-only inventory; no Azure resource was changed or deleted  
**Target:** `rg-storage-sepath-0805175837`, Sweden Central  
**Gate:** READY FOR EXPLICIT DESTRUCTIVE CONFIRMATION

## Live-state checks

- Resource group provisioning state: `Succeeded`; no resource locks.
- Client VM: `PowerState/deallocated`.
- Translator: F0, public safe baseline restored, no subnet rule or private-DNS VNet link.
- Private endpoint: `Succeeded` / `Approved`.
- VNet flow log: enabled and `Succeeded`.
- No ExpressRoute, Megaport, gateway, cross-region, or other provider cleanup is involved.

## Destruction inventory

Deleting the lab resource group will remove these 18 top-level resources:

| Resource | Type / relevant child resources |
|---|---|
| `vm-client` | Ubuntu VM and system identity |
| `vm-client/MDE.Linux` | Defender VM extension |
| `disk-vm-client-os` | Standard SSD managed OS disk |
| `nic-client` | Client NIC |
| `vnet-endpoint-path` | VNet; `snet-client` and `snet-private-endpoint` subnets |
| `nsg-client` | Client NSG and rules |
| `<POLICY_PE_SUBNET_NSG>` | Policy-created private-endpoint-subnet NSG |
| `nat-client` | Standard NAT Gateway |
| `pip-nat` | Standard static IPv4 address |
| `pe-translator` | Translator private endpoint; approved connection and DNS zone group |
| `nic-pe-translator` | Private endpoint NIC |
| `privatelink.cognitiveservices.azure.com` | Private DNS zone and generated record set; no VNet links |
| `<TRANSLATOR_ACCOUNT>` | Translator F0 account |
| `log-sepath` | Log Analytics workspace |
| `<FLOW_STORAGE>` | Standard LRS flow-log/diagnostic storage account |
| `<FLOW_STORAGE_SYSTEM_TOPIC>` | Policy-created Event Grid system topic |
| `<TRAFFIC_ANALYTICS_DCE>` | Traffic Analytics data collection endpoint |
| `<TRAFFIC_ANALYTICS_DCR>` | Traffic Analytics data collection rule |

Nested objects removed with their parents include two Translator diagnostic settings
(lab workspace plus policy storage), one `Cognitive Services User` role assignment,
the VM identity, NSG rules, subnet associations, the private-link connection, and
the private DNS zone group/record. Four successful ARM deployment records are also
removed with the group.

## Lab-owned resource outside the resource group

One tagged lab resource exists in `NetworkWatcherRG` and must also be destroyed:

- `NetworkWatcher_swedencentral/flow-vnet-endpoint-path`
  (`Microsoft.Network/networkWatchers/flowLogs`)

The current `deploy/cleanup.ps1` dry run lists only resources inside the lab resource
group. Its confirmed path must **not** be used alone because it does not remove this
external flow-log child.

Intentionally retained shared/subscription resources:

- Regional `NetworkWatcher_swedencentral` parent.
- Subscription Defender for Servers P2 and Defender for Storage V2 plans/policies.
- Resource providers, Azure Policy assignments, and all unrelated resources.

No lab-owned Azure resource is intentionally retained.

## Required deletion order after approval

1. Delete the lab VNet flow log from `NetworkWatcherRG`; wait until absent.
2. Delete `rg-storage-sepath-0805175837`; Azure removes the remaining dependency
   graph (diagnostics/RBAC/PE before account, NICs before VNet, VM before disk).
3. Verify the resource group is absent, the external flow log is absent, no resource
   with the lab tag remains, and no role assignment remains at a deleted lab scope.

Estimated duration: **10–20 minutes**, allowing up to 30 minutes for policy-created
monitoring resources and resource-group finalization.

## Cost until deletion

Current fixed list-price estimate is approximately **US$0.10/hour**:

- NAT Gateway: $0.045/hour.
- Standard IPv4: $0.005/hour.
- Private endpoint: $0.010/hour.
- Standard SSD E4-class disk and private DNS: about $0.004/hour combined.
- Allocated Defender for Servers P2 and Defender for Storage V2 protection: about
  $0.034/hour when prorated at public monthly list prices.

Translator F0 and the deallocated VM have no compute hourly charge. Storage
capacity/operations, NAT/Private Link data processing, flow-log ingestion, and Log
Analytics are usage-based and currently expected to be negligible while the VM is
deallocated. Actual billed cost can differ with agreement discounts and Defender
metering.

## Artifact and capture gate

- Correctness R1–R5, 2,400 performance requests, and the 800-request sensitivity
  calibration are complete; final Azure state is captured and sanitized.
- The public reproducibility bundle is committed at immutable commit `1921b0d` in
  public PR #1. It contains the protocol, 60 block aggregates, all verdicts,
  calibration result, analysis implementations, and four diagrams.
- Public and local sanitization scans found no raw subscription paths, bearer/JWT
  tokens, private keys, secrets, live resource-group name, or live account names in
  the published bundle.
- Raw per-request and Azure control-plane captures were intentionally excluded from
  publication; the published aggregates are sufficient to audit the reported
  calculations. No further live capture is required.

**Confirmation scope:** approval must explicitly authorize deletion of both the
lab-owned flow log in `NetworkWatcherRG` and the complete lab resource group.
