# expressroute-megaport-bgp — Phase 3.1 Manifest

**Owner:** Morpheus  
**Status:** Paperwork-only design, stopped at approval gate #12 #1  
**Lab folder:** `labs/expressroute-megaport-bgp/`  
**Do not deploy from this document without explicit gate approval.**

## 0. Gate discipline

This manifest is the Phase 3.1 design artifact only. It intentionally creates no IaC files, runs no `az network ... create/update/delete` commands, and makes no Megaport API write calls. Tank must not deploy until Jose approves gate #12 #1 after reviewing this manifest.

Subscription and tenant hygiene are mandatory: scripts must resolve the active subscription at runtime with `az account show --query id -o tsv`, or use a caller-supplied `--subscription` / `$env:AZURE_SUBSCRIPTION_ID`. No subscription IDs or tenant IDs belong in this repo.

## 1. Lab summary

This lab demonstrates an ephemeral Azure ExpressRoute private peering path fronted by a Megaport Cloud Router (MCR). The reader will learn how a provider-based ExpressRoute circuit is handed to Megaport, how Azure and the MCR exchange routes over BGP, and what BGP community metadata survives in each direction. The lab deliberately focuses on a small, teachable topology: one Azure VNet, one ExpressRoute circuit, one MCR, one VXC, and one Linux VM for route/reachability checks.

## 2. Scope and non-goals

### In scope

1. Provider-based ExpressRoute circuit, 50 Mbps, Standard tier, Metered Data.
2. Megaport MCR + Azure VXC using Megaport-managed private peering.
3. Vanilla BGP route exchange: Azure VNet prefix to MCR, simulated on-prem prefix from MCR to Azure.
4. BGP community observation:
   - Azure-originated community tags visible on the MCR side.
   - MCR-originated community tags tested toward Azure; if Azure strips or ignores them, record that as the lesson.
5. Three-layer route evidence: Azure control plane, MCR/Megaport, and VM OS.

### Out of scope for this lab

- Route filters.
- ExpressRoute Global Reach.
- Dual-port HA / multiple circuits.
- MED, AS-path prepending, or complex BGP best-path manipulation.
- Microsoft peering.
- ExpressRoute Direct.
- Virtual WAN.

These are listed again as potential follow-up labs.

## 3. Topology and diagram description

Trinity's Phase 3.3 diagram should show the following path left-to-right:

```text
Simulated on-prem prefixes / MCR route policy
        |
Megaport Cloud Router (MCR, Madrid market)
        |
Megaport Azure VXC, private peer, 50 Mbps
        |
Azure ExpressRoute circuit, provider Megaport, peering location Madrid
        |
ExpressRoute virtual network gateway
        |
Azure VNet in Spain Central
        |
Linux validation VM
```

Diagram callouts to include:

- BGP ASNs: Microsoft AS `12076`; MCR/customer ASN to be assigned or confirmed by Megaport during VXC provisioning.
- Route arrows:
  - Azure advertises `10.31.0.0/16` toward MCR.
  - MCR advertises `172.31.100.0/24` and, if supported, `172.31.101.1/32` as the simulated on-prem/loopback test prefix.
- Community arrows:
  - Azure VNet community `12076:20031` plus Azure regional community, as observed after deployment.
  - MCR test community `65031:100` on the simulated on-prem prefix.
- Evidence locations: Azure effective routes, ExpressRoute route table JSON, MCR BGP routes/neighbors, VM `ip route` / `traceroute`.

## 4. Region and peering-location decision

**Chosen ExpressRoute peering location:** `Madrid` (`Digital Realty/Interxion MAD1`)  
**Chosen Azure region:** `spaincentral` / Spain Central  
**Provider:** Megaport  
**ExpressRoute pricing zone:** Zone 1

The canonical Microsoft Learn provider table lists Madrid as a Zone 1 ExpressRoute peering location with local Azure region `Spain Central`, ER Direct support, and Megaport as a connectivity provider: <https://learn.microsoft.com/en-us/azure/expressroute/expressroute-locations-providers>. This is the best proximity choice for a Madrid-based user and avoids paying for a farther European meet-me point when the same Zone 1 ExpressRoute circuit price applies. If Tank finds that the Megaport account cannot order MCR/VXC in Madrid, the preferred fallback is `Paris` + `francecentral` because Paris is also Zone 1, Megaport-enabled, close to Madrid, and has documented regional BGP community values.

Read-only SKU probes found the current subscription may have zone-specific VM restrictions in Spain Central for small B/D SKUs. Because this lab needs only one diagnostic VM and the ExpressRoute/Megaport resources dominate cost, Tank should verify the final VM SKU at deploy planning time and use the smallest available Linux SKU, preferring `Standard_D2s_v5` if `Standard_B2s_v2` is not usable.

## 5. Resource inventory and rough 24h cost

All Azure resources live in one resource group named for the lab, for example `rg-expressroute-megaport-bgp-<run_id>`, with tags `lab=true`, `lab_name=expressroute-megaport-bgp`, `created_by=copilot-lab`, `owner=jose`, `ephemeral=true`, and `run_id=<run_id>`.

| Plane | Resource | Planned SKU / size | Quantity | Rough 24h cost | Notes |
|---|---:|---|---:|---:|---|
| Azure | Resource group | n/a | 1 | $0 | Cleanup container. |
| Azure | VNet | `10.31.0.0/16`, BGP community enabled | 1 | $0 | Custom community target `12076:20031`. |
| Azure | Subnet | `workload-subnet` `10.31.1.0/24` | 1 | $0 | VM subnet. |
| Azure | GatewaySubnet | `10.31.255.0/27` | 1 | $0 | Required for ER gateway. |
| Azure | NSG | Minimal VM subnet NSG | 1 | $0 | No inbound Internet required; use Run Command for evidence. |
| Azure | ExpressRoute circuit | 50 Mbps, Standard, MeteredData, provider Megaport, peering `Madrid` | 1 | ~$1.83 | Azure Retail: Zone 1 Standard Metered Data 50 Mbps is $55/month. |
| Azure | ER VNet gateway | `Standard` | 1 | ~$4.56 | Retail meter is about $0.19/hour. Fallback `ErGw1AZ` only if Standard is unavailable. |
| Azure | Gateway public IP | Standard static | 1 | ~$0.10 | Required by VNet gateway. |
| Azure | ER gateway connection | Gateway to ER circuit | 1 | $0 | Delete first during cleanup. |
| Azure | Linux validation VM | Prefer `Standard_D2s_v5`; downgrade to smallest available Linux SKU if approved | 1 | ~$2.57 | Ubuntu 22.04 LTS Gen2, SSH key auth. |
| Azure | NIC | VM NIC | 1 | $0 | Effective route evidence source. |
| Azure | OS disk | Standard SSD, 30-64 GiB | 1 | ~$0.07-$0.15 | Smallest supported Standard SSD tier. |
| Megaport | MCR | 1000 Mbps, 1-month `contractTerm` | 1 | ~$95-$105 minimum | Megaport quote is authoritative; billed by Megaport. |
| Megaport | Azure VXC | 50 Mbps, private peer, 1-month `term` | 1 logical VXC | ~$5-$15 minimum | Must be nested under MCR `associatedVxcs`. |

**Planning total for a 24h run:** about **$110-$125**, with the Azure portion around **$9-$11/day** and the Megaport portion dominated by the one-month MCR/VXC minimum. Gate #12 #1 should block if the Megaport order quote exceeds the accepted ~$100-$120 burn envelope.

## 6. BGP scenario walkthroughs

### Scenario 1 — Vanilla ExpressRoute ↔ Azure BGP baseline

**Configuration intent**

- Create the Azure ExpressRoute circuit with Megaport as provider, 50 Mbps, Standard/MeteredData, peering location `Madrid`.
- Create the MCR and the Azure VXC using Megaport's nested `associatedVxcs` format.
- Let Megaport auto-create/configure Azure private peering. Do **not** create an `azurerm_express_route_circuit_peering` or manual Azure private peering resource.
- Link the VNet to the ExpressRoute circuit through an ExpressRoute virtual network gateway and connection.
- Have the MCR advertise a simulated on-prem route, planned as `172.31.100.0/24`; if Megaport supports a pingable loopback/static test interface, also advertise `172.31.101.1/32`.

**Evidence to collect**

- Azure circuit provider state: `Provisioned` / circuit enabled; service key redacted.
- Megaport VXC state: deployed, BGP neighbors up on both primary and secondary paths. Prefer VXC resource `resources.csp_connection[0].interfaces[0].bgpConnections` because MCR looking glass can return empty.
- Azure receives MCR routes:
  - `az network express-route list-route-tables -o json` shows `172.31.100.0/24` and optional `172.31.101.1/32`.
  - `az network nic show-effective-route-table` for the VM NIC shows the same prefixes with next hop `VirtualNetworkGateway`.
- MCR receives Azure routes:
  - MCR BGP table or VXC BGP neighbor details show `10.31.0.0/16` or the VNet-advertised prefix.
- Reachability:
  - VM `ip route` includes the MCR-advertised prefixes.
  - VM `traceroute -n 172.31.101.1` / `ping 172.31.101.1` if a pingable MCR-side loopback is available.
  - If no pingable MCR test endpoint exists, record route exchange as the authoritative pass condition and use Megaport/MCR ping toward the Azure VM as optional reverse evidence.

**Pass criteria**

- Circuit is provider-provisioned.
- BGP sessions are established on both VXC paths.
- Azure route tables contain the MCR-advertised route.
- MCR route evidence contains the Azure VNet route.
- VM effective route table points MCR prefixes to the virtual network gateway.

**Failure criteria**

- Circuit remains `Enabled` but not `Provisioned`.
- BGP sessions remain idle/down.
- Azure private peering values are manually mismatched with Megaport-assigned values.
- VM effective routes do not include the MCR-advertised prefix after convergence.

### Scenario 2 — BGP community tagging and survival

**Configuration intent**

Azure to MCR:

- Configure the VNet with a custom ExpressRoute private-peering community value: `12076:20031`.
- After deployment, retrieve the VNet `bgpCommunities` object. The `VirtualNetworkCommunity` should match `12076:20031`; the `RegionalCommunity` should be recorded from Azure rather than hardcoded because Spain Central may not yet appear in all public community tables.
- Validate on the MCR side that Azure-advertised VNet routes carry the custom community and, if Azure emits it, the regional community.

MCR to Azure:

- Configure the MCR route policy for the simulated on-prem prefix to attach community `65031:100`.
- Advertise `172.31.100.0/24` to Azure with that tag.
- Query Azure route evidence to see whether the prefix is visible and whether any community metadata is exposed.
- Microsoft Learn currently states that Microsoft does not honor community values tagged on routes advertised to Microsoft. Therefore, the expected teaching result is likely: Azure accepts the prefix but strips/does not expose or act on the inbound community. If the community is visible in any Azure route-table output, capture it; if it is absent, document that as the confirmed behavior.

**Evidence to collect**

- VNet `bgpCommunities` before/after setting `12076:20031`.
- MCR BGP table or route detail for `10.31.0.0/16`, showing Azure-originated communities.
- MCR route policy / advertised-route output for `172.31.100.0/24`, showing `65031:100` before handoff.
- Azure ER route table/effective route output for `172.31.100.0/24`, noting whether community metadata is absent or present.

**Pass criteria**

- Azure-originated route communities are visible on the MCR side.
- The MCR-originated prefix is accepted by Azure.
- The lab clearly records whether Azure preserves, exposes, ignores, or strips the MCR-originated community.

**Failure criteria**

- Custom VNet community cannot be set or is not reflected in Azure resource metadata.
- MCR route table cannot show community fields and no fallback portal/API evidence exists.
- MCR route policy cannot attach a community; in that case Tank must stop before deployment and ask whether to proceed with Azure-to-MCR only.

## 7. IaC plan

**Decision:** use **all Terraform** for the deployable implementation in Phase 3.2.

**Why:** this lab is multi-provider by definition. The Azure ExpressRoute circuit produces a service key consumed by Megaport, and Megaport VXC state feeds back into validation and cleanup order. A single Terraform state gives Tank one dependency graph and one destroy plan. Bicep is excellent for Azure-only resources, but it cannot model Megaport resources; splitting Bicep and Terraform would add handoff risk around service keys, private peering ownership, and cleanup sequencing.

**Planned file layout — not created in Phase 3.1:**

```text
src/terraform/expressroute-megaport-bgp/
├── versions.tf            # azurerm, azapi if needed, megaport provider pins
├── providers.tf           # Azure CLI auth; Megaport reads env vars
├── variables.tf           # lab_name, region, peering_location, CIDRs, SKUs, tags
├── locals.tf              # naming, run_id, common tags
├── azure-network.tf       # RG, VNet, subnets, NSG, NIC, VM
├── azure-expressroute.tf  # ER circuit, gateway public IP, ER gateway, ER connection
├── azure-bgp-community.tf # VNet bgpCommunities via azurerm or azapi if needed
├── megaport.tf            # MCR + associatedVxcs nested Azure VXC
├── route-policy.tf        # MCR advertised prefixes and community-tag policy, if provider supports it
├── outputs.tf             # sanitized IDs/names, no service key in committed output
└── README.md              # Tank deploy/cleanup notes, created later if needed
```

Lab-specific overrides can later live under:

```text
labs/expressroute-megaport-bgp/deploy/
└── terraform.tfvars.example
```

**Azure-side Terraform resources**

- `azurerm_resource_group`
- `azurerm_virtual_network` or `azapi_update_resource` for `bgpCommunities` if AzureRM lacks the property needed for `12076:20031`
- `azurerm_subnet` for workload and `GatewaySubnet`
- `azurerm_network_security_group` and associations
- `azurerm_network_interface`
- `azurerm_linux_virtual_machine`
- `azurerm_public_ip` for the gateway
- `azurerm_virtual_network_gateway` with `type = "ExpressRoute"`, SKU `Standard`
- `azurerm_express_route_circuit` with provider Megaport, peering location `Madrid`, bandwidth 50 Mbps, Standard/MeteredData
- `azurerm_virtual_network_gateway_connection` linking the gateway to the circuit

**Do not create:** `azurerm_express_route_circuit_peering` for Azure private peering. Megaport owns private peering configuration for this lab.

**Megaport-side Terraform/API resources**

- MCR order in Madrid market, 1000 Mbps, `contractTerm = 1`.
- Azure VXC as nested `associatedVxcs` under the parent MCR, bandwidth 50 Mbps, `term = 1`.
- VXC peer block with `peers = [{ type = "private" }]` or the provider-equivalent shape that causes Megaport to auto-configure private peering.
- Route/prefix policy for simulated on-prem routes and community `65031:100`, if exposed by the provider/API.

**Megaport non-negotiables from Trinity/Tank**

- Use nested `associatedVxcs`; do not use standalone `productType: "VXC"` order shape.
- MCR uses `contractTerm`; nested VXC uses `term`.
- Do not include `config: {}` in the MCR payload.
- Do not manually configure Azure private peering when Megaport auto-creates it.
- Read auto-assigned BGP details from the VXC resource, especially `resources.csp_connection[0].interfaces[0].bgpConnections`.

## 8. Credential and runtime plan

### Required before deploy

| Variable / prerequisite | Required? | Used by | Notes |
|---|---:|---|---|
| Active Azure CLI login | Yes | AzureRM provider / scripts | `az account show` must work. |
| Active subscription set with `az account set` | Yes | AzureRM provider / scripts | Resolve dynamically; do not commit the ID. |
| `$env:MEGAPORT_API_KEY` | Yes | Megaport provider/API | Primary source because Key Vault is private-link only. |
| `$env:MEGAPORT_API_SECRET` | Yes | Megaport provider/API | Primary source; never write to disk. |
| `$env:MEGAPORT_API_URL` | Optional | Megaport provider/API | Default production API unless testing against another Megaport environment. |
| `$env:AZURE_SSH_PUBLIC_KEY` or `$env:AZURE_SSH_PUBLIC_KEY_PATH` | Yes | Linux VM | Public key only. No VM password for this Linux lab. |
| `$env:ARM_SUBSCRIPTION_ID` | Script-set | AzureRM provider | Tank should set this from `az account show --query id -o tsv` at runtime if the provider version requires it. |

### Not used unless the implementation changes

- No VM admin password is needed; use Linux SSH key auth.
- No hardcoded tenant ID.
- No committed service principal secret. If a future CI pipeline needs service-principal auth, it must use env vars such as `$env:ARM_CLIENT_ID`, `$env:ARM_CLIENT_SECRET`, and `$env:ARM_TENANT_ID`, injected outside the repo.

### Key Vault fallback

`platform-secrets-1138` is private-link only and unreachable from the dev machine. This lab uses Megaport env vars as the primary credential source. Key Vault can be a future fallback only when the deployment runner executes from inside the vault's reachable VNet.

## 9. Validation plan

Niobe should save sanitized command output under `labs/expressroute-megaport-bgp/show-output/` and screenshots under `labs/expressroute-megaport-bgp/screenshots/`. Strip service keys, subscription IDs, tenant IDs, Megaport credentials, and any tokens before committing.

### Layer 1 — Azure control plane

Collect:

- ExpressRoute circuit state and provider provisioning state.
- ExpressRoute route tables in JSON, not table format:
  - `az network express-route list-route-tables ... -o json`
- ExpressRoute gateway learned and advertised routes:
  - `az network vnet-gateway list-learned-routes ...`
  - `az network vnet-gateway list-advertised-routes ...`
- VM NIC effective route table:
  - `az network nic show-effective-route-table ...`
- VNet BGP community metadata using Azure PowerShell or `az rest` if CLI does not expose the property.

Expected Azure observations:

- VM effective routes include `172.31.100.0/24` with next hop `VirtualNetworkGateway`.
- ExpressRoute route table shows MCR-advertised prefixes.
- VNet metadata shows `VirtualNetworkCommunity = 12076:20031`.

### Layer 2 — Megaport / MCR

Collect:

- MCR product state.
- VXC product state and BGP neighbor/session detail from the VXC resource.
- MCR BGP route table / looking glass output if available.
- Route policy / prefix advertisement output for the MCR-side community test.

Expected Megaport observations:

- Both BGP sessions are established.
- MCR sees Azure VNet prefix `10.31.0.0/16`.
- MCR route detail shows Azure-originated custom community `12076:20031` and any Azure regional community emitted for Spain Central.
- MCR advertised prefix `172.31.100.0/24` is tagged with `65031:100` before handoff.

Known issue: the MCR looking-glass BGP route endpoint can return an empty array even when BGP is up. If that happens, use VXC BGP neighbor/session details plus portal route-table screenshots as fallback evidence.

### Layer 3 — VM operating system

Run through `az vm run-command`:

```bash
ip addr
ip route
traceroute -n 172.31.100.1 || true
traceroute -n 172.31.101.1 || true
ping -c 4 172.31.101.1 || true
```

Expected VM observations:

- Kernel route lookup for `172.31.100.0/24` exits via the Azure VNet gateway path.
- If an MCR-side loopback/test endpoint is available, ping/traceroute reaches it.
- If no pingable endpoint is available, the documented pass condition is route convergence, not ICMP success.

### Screenshot checklist for Niobe

- Azure ExpressRoute circuit Overview: provider `Provisioned` with service key redacted.
- Azure ExpressRoute Peerings page: private peering present; note Megaport-managed ownership.
- Azure VNet Gateway connection: connected/succeeded state.
- Azure VM NIC effective routes: MCR/on-prem prefixes via virtual network gateway.
- Azure VNet BGP community property page or equivalent metadata output.
- Megaport MCR overview: deployed/active.
- Megaport VXC details: BGP sessions up, primary and secondary path details.
- Megaport MCR route table showing Azure prefix and communities, if portal exposes them.
- Megaport route policy/community configuration for `65031:100`, if portal/API exposes it.

## 10. Cleanup chain

Cleanup must run in this order. Reversing it risks a 30-40 minute Azure gateway/RG hang and Megaport HTTP 409 failures while Azure peering still references the service key.

1. **Azure ER connection** — delete the VNet gateway to ExpressRoute circuit connection first.
2. **Azure ER private peering** — this manifest does not create private peering explicitly; Megaport normally owns it. If Azure exposes a removable private peering object that must be deleted to release the service key, remove it here. Otherwise record that this step is skipped because Megaport owns the peering.
3. **Megaport VXC(s)** — delete the Azure VXC after the Azure-side connection/peering reference is gone.
4. **Megaport MCR** — delete only after all associated VXCs are gone.
5. **Azure resource group** — delete last so the gateway, circuit, VM, NIC, NSG, VNet, disk, and public IP clean up together.

Tank should dry-run/list these resources before cleanup approval gate #12 #2, then wait for explicit approval before destructive actions.

## 11. Open questions for gate #12 #1

1. **Megaport credentials:** confirm `$env:MEGAPORT_API_KEY` and `$env:MEGAPORT_API_SECRET` are set on Tank's deploy machine. If the Terraform provider in use expects different environment variable aliases, approve Tank mapping those aliases from these two env vars at runtime.
2. **IaC style:** approve the recommended all-Terraform implementation, or request a Bicep-for-Azure + Terraform-for-Megaport split. Morpheus recommends all-Terraform to keep the service key, VXC, and cleanup chain in one state graph.
3. **Location:** approve `Madrid` peering + `spaincentral` VNet. Also approve fallback to `Paris` + `francecentral` if the Megaport account lacks Madrid MCR/VXC ordering rights or if required Azure SKUs are blocked in Spain Central.
4. **Cost guardrail:** confirm deployment should proceed only if the Megaport quote keeps the 24h lab within roughly `$100-$120`; otherwise stop and re-plan.
5. **Community test endpoint:** confirm it is acceptable for the baseline reachability test to be route-table authoritative if Megaport MCR cannot expose a pingable loopback/test IP.

## 12. Potential follow-up labs

- ExpressRoute route filters and Microsoft peering.
- ExpressRoute Global Reach between two MCR-backed circuits.
- Dual-port / dual-location HA with path failover.
- MED, AS-path prepending, and local preference manipulation.
- ExpressRoute FastPath and gateway-bypass behavior.
- ExpressRoute Direct with MACsec.
- Virtual WAN with ExpressRoute and route intent.
- Comparing ExpressRoute Local vs Standard from Madrid/Spain Central.
