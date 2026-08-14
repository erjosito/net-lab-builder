# foundry-agent-reserved-prefix-reachability — Stage-1 Planning Manifest
Morpheus · 2026-08-14 · **PLANNING ONLY — Phase 0 preflight and Phase 4 deployment approval not yet requested.**

## Card Summary

Test whether Foundry Agent Service, deployed with VNet injection, can route agent-originated tool calls to an
on-premises network advertising `172.30.0.0/16` via BGP over a Site-to-Site VPN. The Foundry VNet and all peered
VNets are clean (no reserved ranges in address spaces); the reserved prefix exists **only** as a remote BGP-learned
route. Negative controls confirm the documented deployment-time validation boundary. Primary outcome is binary and
unknown.

**IN scope:** VNet injection BYO, prompt agent + OpenAPI/function tool, S2S VPN BGP, gateway route propagation,
reserved-prefix route-plane test, DNS forwarding plane, negative-control ARM-validation.  
**OUT of scope:** ExpressRoute, vWAN, Managed VNet, Hosted agent container image, Code Interpreter, internet egress,
multi-region Foundry, Entra conditional access.

---

## 1. Hypothesis

> **H₀ (null):** The platform enforces a runtime route-plane block on `172.30.0.0/16` beyond address-space
> declaration checks, making the prefix unreachable from agent tool calls even when it arrives via VPN BGP.
>
> **H₁ (alternative — expected):** The restriction is scoped to VNet address-space declarations and VNet peering
> relationships only. A non-peered remote prefix learned via VPN BGP is reachable by agent tool calls, identical to
> any other on-premises prefix.

Source of ambiguity: Microsoft Learn states the reserved-range check covers "all address spaces you have in your
VNET, and if you have more than one, and peered VNETs" — no mention of VPN-learned routes. The
[networking deep dive](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agents-networking-deep-dive)
confirms the delegated subnet is a standard Azure Container Apps subnet using its VNet's effective route table.
Whether the data proxy or Micro VM enforces an _additional_ runtime ACL on the reserved range is not documented.

---

## 2. Regions, Address Plan, and ASNs

### Region Selection (⚠️ preflight required)

Primary: **swedencentral** for Foundry/Azure OpenAI (listed in Foundry networking regional support).  
On-prem simulator: **norwayeast** (low-cost, geographically close, no Foundry dependency).  
Preflight must confirm:
- Foundry Agent Service (Standard agent) is available in swedencentral.
- `Microsoft.App/environments` delegation is available in swedencentral.
- Azure OpenAI `gpt-4o-mini` standard deployment is available in swedencentral.
- B2ts_v2 VM SKU is available in both regions.

### VNet Address Plan

| VNet | Region | Address Space | Notes |
|------|--------|--------------|-------|
| vnet-foundry | swedencentral | `192.168.0.0/16` | No reserved range; Class C RFC 1918 |
| vnet-onprem | norwayeast | `172.30.0.0/16` + `10.200.100.0/24` | On-prem owns the reserved range; `10.200.100.0/24` is the control prefix |

### Subnet Plan

| VNet | Subnet | CIDR | Delegation / Notes |
|------|--------|------|--------------------|
| vnet-foundry | AgentSubnet | `192.168.0.0/24` | Delegated to `Microsoft.App/environments`; /24 per recommendation |
| vnet-foundry | PESubnet | `192.168.1.0/24` | Private endpoints; no delegation, no NSG on PE NICs |
| vnet-foundry | GatewaySubnet | `192.168.255.0/27` | VPN GW; no UDR, no NSG |
| vnet-foundry | MgmtSubnet | `192.168.2.0/27` | vm-diag; no public IP; Azure Run Command management |
| vnet-onprem | WorkloadSubnet | `172.30.100.0/24` | vm-onprem-echo single NIC |
| vnet-onprem | CtrlSubnet | `10.200.100.0/24` | vm-onprem-ctrl single NIC (control prefix); matches 2nd vnet-onprem address space |
| vnet-onprem | GatewaySubnet | `172.30.255.0/27` | VPN GW; no UDR, no NSG |

> ⚠️ **Trinity correction C3 (2026-08-14, applies if S5 in scope):** DNS Private Resolver requires two dedicated /28 subnets with `Microsoft.Network/dnsResolvers` delegation; cannot share PESubnet. Add `192.168.3.0/28` (DNSInboundSubnet) and `192.168.3.16/28` (DNSOutboundSubnet) to vnet-foundry. See `design.md` §9.

**Why Class C for Foundry VNet:** Class A (`10.x`) requires specific regional support per the Foundry limitation
(quote: "Private Class A IP address ranges are only supported in specific regions"). Class C is universally
supported. Class B `172.16–31` technically includes 192.168 — only the `172.30/172.31` sub-ranges are reserved; but
to avoid any ambiguity, Class C is the safest choice.

**Why the on-prem VNet has address space `172.30.0.0/16`:** This makes vnet-onprem itself the entity that owns the
reserved prefix as a declared address space, identical to a real on-premises network that cannot be renumbered.
The Foundry VNet does **not** peer with vnet-onprem; the prefix is only reachable via VPN S2S.

### ASN Plan

| Resource | ASN |
|----------|-----|
| vpngw-foundry | 65010 |
| vpngw-onprem | 65020 |

---

## 3. Resource Inventory

### VPN Gateways — 2 × VpnGw1AZ (non-Active-Active, BGP enabled)

> ⚠️ **Trinity correction C1 (2026-08-14):** VpnGw1 creation blocked since 2025-11-01 (`NonAzSkusNotAllowedForVPNGateway`). SKU corrected to **VpnGw1AZ**. See `design.md` §2.1.

| Name | Region | ASN | PIP |
|------|--------|-----|-----|
| vpngw-foundry | swedencentral | 65010 | pip-vpngw-foundry (Standard) |
| vpngw-onprem | norwayeast | 65020 | pip-vpngw-onprem (Standard) |

**Rationale for non-AA:** Single tunnel is sufficient to test reachability. AA adds a second PIP and second BGP
session per GW (~2× cost for VPN GW component). HA is not the lab topic; fault injection is not required.  
**Rationale for VPN over ExpressRoute:** VPN GW VpnGw1AZ ≈ $5.04/day vs. ER GW + circuit ≥ $47/day. VPN BGP
propagates the same routes; platform sees identical effective-route entries. ExpressRoute is deferred as Design D3.

### VMs — 3 × Standard_B2ts_v2 (Ubuntu 22.04 LTS, Standard SSD P4)

> ⚠️ **Trinity correction C2 (2026-08-14):** Original dual-NIC design (`vm-onprem-server` with primary `172.30.100.4` + secondary `10.200.100.4`) replaced with two single-NIC VMs to eliminate return-path confounder. See `design.md` §2.2 and §6.

| Name | VNet / Subnet | IP | Role |
|------|--------------|-----|------|
| vm-onprem-echo | vnet-onprem / WorkloadSubnet | `172.30.100.4` | Python HTTP echo + nginx TLS proxy + dnsmasq; primary test target (S4, S5) |
| vm-onprem-ctrl | vnet-onprem / CtrlSubnet | `10.200.100.4` | Python HTTP echo + nginx TLS proxy; control target (S3) |
| vm-diag | vnet-foundry / MgmtSubnet | `192.168.2.4` | Diagnostic VM; no PIP; access via Azure Run Command |

vm-onprem-echo runs:
- **Python echo service** (HTTP, port 80 primary; nginx provides HTTPS on port 443): `GET /api/echo?msg=X` → `{"echo":"X","label":"echo","server_ip":"172.30.100.4","request_url":"http://172.30.100.4/api/echo?msg=X","ts":"…","src_ip":"<remote_addr>"}`.
- **dnsmasq**: responds to `echo.onprem.lab` → `172.30.100.4`; `echo-ctrl.onprem.lab` → `10.200.100.4`.

vm-onprem-ctrl runs:
- **Python echo service** (identical behavior to vm-onprem-echo, with label `ctrl` and server IP `10.200.100.4`).

### Foundry Platform Resources

| Resource | SKU / Tier | Notes |
|----------|-----------|-------|
| Azure AI Foundry account | Standard | VNet-injected; must be created with network injection (cannot add post-creation for hosted agents — not relevant here but noted) |
| Azure OpenAI deployment | gpt-4o-mini, Standard | Model for prompt agent |
| Azure AI Search | Standard S1 | Required Foundry dependency; private endpoint |
| Azure Cosmos DB | Serverless | Required Foundry dependency; private endpoint |
| Azure Storage account | Standard LRS | Required Foundry dependency; private endpoint |
| Azure Container Registry | Basic | **Not required for prompt agent** — excluded from IaC |
| Foundry prompt agent | — | OpenAPI function tool pointing to echo endpoint |

### Private Endpoints — 5

| Resource | Sub-resource | Private DNS Zone |
|----------|-------------|-----------------|
| Foundry account | account | `privatelink.cognitiveservices.azure.com`, `privatelink.openai.azure.com`, `privatelink.services.ai.azure.com` |
| Azure OpenAI | account | (same zones as Foundry) |
| AI Search | searchService | `privatelink.search.windows.net` |
| Cosmos DB | Sql | `privatelink.documents.azure.com` |
| Storage | blob | `privatelink.blob.core.windows.net` |

All private DNS zones linked to vnet-foundry.

### DNS Architecture

- vnet-foundry DNS server: Azure default (168.63.129.16) — resolves `privatelink.*` zones via linked private DNS zones.
- For S5 (DNS plane test): deploy **Azure DNS Private Resolver** outbound endpoint in `DNSOutboundSubnet` (192.168.3.16/28) + inbound endpoint in `DNSInboundSubnet` (192.168.3.0/28) with
  forwarding ruleset for `onprem.lab` → `172.30.100.4:53` (dnsmasq on vm-onprem-echo). Both subnets are pre-created.
- Azure DNS Private Resolver is optional — deploy only if S5 is in scope; Phase-0 must confirm SKU availability.

### VPN Connections — 1 bidirectional pair (2 connection objects)

| Object | Direction | PSK |
|--------|-----------|-----|
| conn-foundry-to-onprem | vpngw-foundry → vpngw-onprem | generated at deploy time |
| conn-onprem-to-foundry | vpngw-onprem → vpngw-foundry | same PSK |

BGP advertised prefixes from vpngw-onprem:
- `172.30.0.0/16` — full vnet-onprem address space (VPN GW auto-advertises VNet address spaces, not subnet prefixes)
- `10.200.100.0/24` — control prefix (second vnet-onprem address space)

> ⚠️ **Tank correction C4 (2026-08-14):** The gateway advertises the entire VNet address space (`172.30.0.0/16`),
> not only the workload subnet prefix (`172.30.100.0/24`). The reserved prefix in the Foundry route table is
> therefore the full `/16`. This is the correct test condition — the platform sees `172.30.0.0/16` in effective
> routes, which is the documented reserved range. The sub-prefix `/24` would not test the same boundary.

BGP advertised from vpngw-foundry to vpngw-onprem:
- `192.168.0.0/16` — Foundry VNet address space (VPN GW auto-advertises)

### NSGs — 2

| NSG | Applied to | Key rules |
|-----|-----------|-----------|
| nsg-echo-vms | WorkloadSubnet, CtrlSubnet | HTTP/HTTPS from 192.168.0.0/16; SSH from MgmtSubnet; DNS from DNSOutboundSubnet; ICMP from Foundry VNet |
| nsg-mgmt | MgmtSubnet | SSH from MgmtSubnet self (192.168.2.0/27); no public inbound rule |

**No NSG on AgentSubnet initially:** minimize confounders for the route experiment.
Platform may reject NSG on a delegated subnet (`Microsoft.App/environments`) — verify at deploy time.
Do not apply NSG to GatewaySubnet or PESubnet.

### Route Tables

No route table is attached to AgentSubnet initially. Default VPN gateway propagation is preserved to minimize
test confounders.

### Resource Count Summary

2 VNets · 2 VPN GWs · 1 VPN connection pair (2 objects) · 2 Standard PIPs · **3 VMs** · 1 Foundry account ·
1 Azure OpenAI · 1 AI Search · 1 Cosmos DB · 1 Storage account · **no ACR** (prompt agent only) · 3 BYO PE +
pre-created Foundry DNS zones · 6 private DNS zones · 2 NSGs · 1 RG · (optional: 1 DNS Private Resolver)

---

## 4. Deployment Sequence

```
Wave 0  RG + 2 Standard PIPs
Wave 1  vnet-foundry + vnet-onprem + all subnets
Wave 2  Target and management NSGs → associate to subnets
Wave 3  ★ LONG POLE (parallel):
          vpngw-foundry + vpngw-onprem        30-45 min
          vm-onprem-echo + vm-onprem-ctrl + vm-diag  5 min
          Private DNS zones + links            3 min
Wave 4  VPN connection objects (after both GWs provisioned)
         BGP convergence wait ~5 min
Wave 5  Private endpoints (after VNets ready)
Wave 6  AI Search + Cosmos DB + Storage dependencies and private endpoints
Wave 7  Jose manually creates Foundry, model deployment, prompt agent, and tools
Wave 8  Verify: vpngw-foundry learned routes show 172.30.0.0/16 + 10.200.100.0/24
         Verify: vm-diag effective routes include both address spaces
         Verify: vm-diag reaches both single-NIC target VMs
```

---

## 5. Agent Workload Definition

**Agent type:** Prompt agent (no ACR, no container image, no Hosted agent complexity).

**Tools:** Use the complete OpenAPI documents under `agent-tools/`:

- `echo-control.openapi.json` → `http://10.200.100.4`
- `echo-reserved.openapi.json` → `http://172.30.100.4`

Both target VMs also expose self-signed HTTPS for a follow-up experiment. Microsoft Learn doesn't document
a supported custom-CA trust path for the managed data proxy, so HTTP is the primary route-plane test. If the
portal rejects HTTP tool servers, use a private DNS hostname with a publicly trusted certificate.

**Agent prompt for test runs:**
```
Call the echo-onprem tool with message "probe-reserved" and the echo-control tool with message "probe-control".
Report both responses verbatim.
```

The agent response body, tool call success/failure, and HTTP status codes from each tool are the primary semantic evidence.

---

## 6. Negative Controls

### NC-1 — Foundry VNet address-space contains `172.30.0.0/16`
Attempt (without creating the Foundry account first):
```bash
az network vnet create --name vnet-foundry-bad --address-prefixes 172.30.0.0/16 \
  --resource-group rg-foundry-reserved-prefix-<corrID>
# Then attempt to create Foundry account pointing to this VNet
```
**Expected:** ARM or Foundry service returns a deployment validation error citing the reserved range.  
**PASS:** Error message references `172.30.0.0/16` or reserved-range restriction.  
**FAIL:** Deployment succeeds — would be a significant undocumented behavior gap.  
**Cost impact:** Minimal ($0.01); VNet only, no GW provisioned for this control.

### NC-2 — Peered VNet address-space contains `172.30.0.0/16`
After the main Foundry account is deployed on vnet-foundry (192.168.0.0/16):
```bash
az network vnet create --name vnet-peer-bad --address-prefixes 172.30.0.0/16 \
  --resource-group rg-foundry-reserved-prefix-<corrID> --location swedencentral
az network vnet peering create --name peer-foundry-to-bad \
  --vnet-name vnet-foundry --remote-vnet vnet-peer-bad ...
```
**Expected:** Either the peering create call or a subsequent Foundry platform health check rejects this.  
**PASS:** Peering rejected, or Foundry enters a degraded/failed state with error citing reserved range.  
**FAIL:** Peering succeeds and Foundry remains healthy — would contradict the documentation.  
**Cost impact:** Minimal; no GW in the bad VNet.

**Sequencing note:** NC-1 is destructive (cannot reuse bad VNet for main lab). NC-2 runs after main lab is
healthy; the bad VNet is deleted immediately after the negative-control evidence is captured.

---

## 7. Scenarios

### S1 — Deployment Negative Control: Local Reserved Prefix (NC-1)
**Setup:** Create VNet with `172.30.0.0/16`; attempt Foundry account creation pointing to it.  
**PASS:** ARM/Foundry returns a validation error mentioning reserved range; no Foundry account created.  
**FAIL:** Foundry account created successfully.  
**Evidence:** `az deployment operation list` error body · portal activity log.  
**Cleanup:** `az network vnet delete --name vnet-foundry-bad`.

### S2 — Deployment Negative Control: Peered Reserved Prefix (NC-2)
**Setup:** Main Foundry healthy on vnet-foundry; peer vnet-peer-bad (172.30.0.0/16) to vnet-foundry.  
**PASS:** Peering rejected OR Foundry reports a health error with `172.30.0.0/16` citation.  
**FAIL:** Peering succeeds; Foundry remains healthy with 172.30.x.x peered.  
**Evidence:** `az network vnet peering show` provisioningState · Foundry portal health status · `az ai foundry show` output.  
**Cleanup:** `az network vnet peering delete` + `az network vnet delete --name vnet-peer-bad`.

### S3 — Control: Non-Reserved Remote Prefix via VPN
**Setup:** Main lab fully deployed; VPN up; `10.200.100.0/24` advertised via BGP; vm-diag confirms
`10.200.100.4` is pingable from vnet-foundry.  
**Probe:** Agent run with `echo-control` tool → `msg=probe-control`.  
**PASS:** Agent response contains `{"echo":"probe-control","prefix":"10.200.100.0/24"}` (HTTP 200); tool call
shows `success=true` in agent run details.  
**FAIL:** Tool call returns error or timeout; verify VPN route first using vm-diag.  
**Evidence:** Agent run JSON (tool call result + HTTP status) · effective routes on `nic-vm-diag` ·
`az network vnet-gateway list-learned-routes`.

### S4 — Primary: Reserved Prefix via VPN (⚠️ unknown outcome)
**Setup:** Same as S3 (S3 must PASS first); `172.30.0.0/16` is advertised via BGP; vm-diag confirms
`172.30.100.4` is reachable via ping.  
**Probe:** Agent run with `echo-onprem` tool → `msg=probe-reserved`.  
**PASS (H₁ confirmed):** Agent response contains `{"echo":"probe-reserved","prefix":"172.30.100.0/24"}`
(HTTP 200); tool call shows `success=true`. Platform treats reserved prefix as any other VPN-learned route.  
**FAIL (H₀ not rejected):** Tool call returns network error, TCP timeout, or HTTP 5xx from data proxy;
agent reports tool unavailable; HTTP status captured. The data proxy may enforce an additional ACL.  
**Evidence (required for either outcome):**
- Agent run JSON with tool call result and HTTP status.
- `tcpdump` on vm-onprem-echo: did any TCP SYN arrive from any IP in `192.168.x.x` range?
- `az network vnet-gateway list-learned-routes`: is `172.30.0.0/16` present?
- Data proxy 5xx error logs (if accessible via Foundry diagnostic settings → Log Analytics).
- Compare: identical tool call to `10.200.100.4` (S3) for path parity.

### S5 — DNS Plane: On-Premises Hostname Resolution
**Pre-condition:** DNS Private Resolver deployed; forwarding ruleset `onprem.lab → 172.30.100.4:53` active.  
**Probe:** Agent run with tool calling `https://echo.onprem.lab/api/echo?msg=probe-dns`.  
**PASS:** Agent resolves hostname to `172.30.100.4`; echo response received; dnsmasq logs show query from
`192.168.x.x`.  
**FAIL:** DNS resolution fails (NXDOMAIN or timeout); agent reports tool error.  
**Evidence:** Agent run JSON · dnsmasq query log on vm-onprem-echo · DNS resolver query log ·
`nslookup echo.onprem.lab <resolver-inbound-IP>` from vm-diag.  
**Note:** S5 is deferred if DNS Private Resolver is not included in the approved resource set; the primary
hypothesis (S4) does not depend on S5.

---

## 8. Evidence Taxonomy

| Plane | Signal | Tool |
|-------|--------|------|
| Route plane | Foundry-side learned/effective routes | Gateway learned routes plus `az network nic show-effective-route-table` on `nic-vm-diag` |
| Route plane | VPN GW learned routes | `az network vnet-gateway list-learned-routes --name vpngw-foundry` |
| Route plane | BGP advertised routes from on-prem | `az network vnet-gateway list-advertised-routes --name vpngw-onprem` |
| DNS plane | Hostname resolution in Foundry VNet | `nslookup` / `dig` from vm-diag |
| DNS plane | dnsmasq query log | Run Command on vm-onprem-echo → `journalctl -u dnsmasq` |
| TCP/TLS | Connection arrival at target | `tcpdump -i any -n port 443 or port 80` on the selected target VM |
| HTTP | Echo response body and status | Captured in agent run tool call result (JSON) |
| Agent semantic | Agent run output | `az ai agent run show` or Foundry SDK; full run JSON |
| Platform diagnostic | Data proxy errors | Foundry diagnostic settings; discover the emitted table/category at runtime rather than assuming a schema |

---

## 9. Expected Ambiguities and Confounders

| Ambiguity | Impact | Mitigation |
|-----------|--------|-----------|
| Managed data-proxy NIC isn't customer-inspectable | Direct effective-route evidence is unavailable | Correlate gateway learned routes, vm-diag effective routes, and target packet capture |
| Data proxy may enforce TLS certificate validation | Tool call fails even if route is correct | Use HTTP fallback; capture error message to distinguish TLS vs route failure |
| Foundry data proxy may SNAT to an IP outside `192.168.0.0/16` | tcpdump on target shows unexpected source IP | Capture actual SYN source IP in tcpdump as evidence |
| VPN BGP may not propagate `172.30.0.0/16` into vnet-foundry | S4 fails for routing reasons unrelated to platform ACL | Verify gateway learned routes and vm-diag effective routes before S4 |
| Foundry platform may have an undocumented runtime filter for reserved prefixes | S4 fails while S3 passes | Correlate target packet capture, gateway routes, and agent error before attributing the failure |
| `172.30.0.0/16` overlaps with Docker/Kubernetes default bridge ranges; Container Apps platform may assign a conflicting internal range | Asymmetric routing | Captured in agent diagnostic logs; data proxy source IP from tcpdump resolves this |
| gpt-4o-mini may not be available in swedencentral (model availability changes) | Lab blocked at Wave 6 | Phase-0 preflight; fallback model: gpt-35-turbo or gpt-4o-mini in eastus2 with a Foundry account in eastus2 |

### Decision Matrix

| S3 result | S4 result | S5 result | Interpretation |
|-----------|-----------|-----------|----------------|
| PASS | PASS | PASS | H₁ confirmed: reserved prefix is a deployment-time address-space check only; VPN-learned routes are unrestricted. DNS forwarding also works end-to-end. |
| PASS | PASS | FAIL | H₁ confirmed for data-plane; DNS forwarding chain blocked (DNS resolver or dnsmasq config issue — not a platform reservation). |
| PASS | FAIL (SYN at server) | — | Partial block: route is correct, TCP arrives at on-prem, but return path or TLS handshake fails. Investigate: SNAT, certificate, asymmetric routing. |
| PASS | FAIL (no SYN at server) | — | H₀ not rejected: platform or data proxy drops traffic to `172.30.x.x` before egress. Investigate: agent subnet NSG, data proxy ACL, platform-layer block (check diagnostic logs). |
| FAIL | — | — | Lab infra issue: VPN or route propagation not working; S4 cannot be run; fix before proceeding. |
| FAIL (NC-1) | — | — | NC-1 FAIL (unexpected): reserved prefix is not enforced at deployment time; major undocumented gap; escalate to Microsoft. |

---

## 10. Risks and Limitations

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| Foundry Agent Service not available in swedencentral | Medium | Phase-0 preflight; fallback to eastus2 |
| AgentSubnet delegation blocks NSG + route propagation | Medium | Use `az network nic show-effective-route-table` to verify before running agent |
| TLS validation failure masking route-plane result | High | Use HTTP fallback endpoint; distinguish error types explicitly |
| gpt-4o-mini quota not available | Low | Fallback to gpt-35-turbo |
| DNS Private Resolver not available in swedencentral | Low | S5 deferred; DNS resolver is optional |
| Target configuration drift | Low | Keep two single-NIC targets configuration-identical except response label |
| VPN GW BGP session not advertising both prefixes | Low | Verify with `list-advertised-routes` before running scenarios |

---

## 11. Cost Estimate

**Basis:** Azure Retail Pricing PAYG USD 2026-08-14. Confidence: MEDIUM (SKU prices not verified against live catalog).

| Resource | Qty | Unit $/hr | $/day |
|----------|-----|----------|-------|
| VPN GW VpnGw1AZ (non-AA) × 2 | 2 | $0.21 | $10.08 |
| VPN S2S connection objects | 2 | $0.015 | $0.72 |
| Standard PIP × 2 | 2 | $0.005 | $0.24 |
| VM Standard_B2ts_v2 × 3 | 3 | $0.0108–$0.0132 | $0.89 |
| AI Search Standard S1 | 1 | $0.336 | $8.06 |
| Cosmos DB Serverless | 1 | ~$0.04/RU | ~$1.00 |
| Storage LRS | 1 | negligible | $0.10 |
| Private endpoints × 3 | 3 | $0.01 | $0.72 |
| Azure OpenAI gpt-4o-mini | per token | ~$0.15/M in | ~$1.00 |
| DNS Private Resolver endpoints + ruleset (optional) | 2 endpoints + 1 ruleset | monthly meters | ~$11.92 |
| **Baseline (no DNS resolver)** | | | **≈ $21–23/day** |
| **With DNS resolver (S5)** | | | **≈ $33–35/day** |

The Phase-4 approval summary uses live Azure Retail Pricing queries rather than these original planning estimates.

Estimated lab run time: ~3–4 hours.  
Estimated Azure infrastructure cost for a 5-hour run: **≈ $4.50–$7.50**, plus Foundry/model usage created manually.

---

## 12. Phase 0 Preflight Items (Deferred)

The following must be verified before Phase 4 approval is requested:

1. Foundry Agent Service (Standard prompt agent, VNet injection) available in **swedencentral**.
2. `Microsoft.App/environments` subnet delegation available in swedencentral.
3. Azure OpenAI `gpt-4o-mini` Standard deployment available in swedencentral; if not, identify fallback region.
4. `Standard_B2ts_v2` VM SKU available in swedencentral and norwayeast.
5. VpnGw1 available in swedencentral and norwayeast.
6. DNS Private Resolver available in swedencentral (only if S5 is in scope).
7. Live price confirmation for VpnGw1, AI Search S1, DNS Private Resolver in the selected regions.
8. Confirm Foundry account networking: VNet injection must be set at creation time; cannot be added later for
   hosted agents (prompt agents — verify same constraint applies or not).
9. Jose's public IP for MgmtSubnet NSG allowlist (capture at preflight time).

---

## 13. Phase-4 Approval Gate

**TANK AND ALL AGENTS ARE BLOCKED UNTIL JOSE MORENO EXPLICITLY APPROVES — AND UNTIL PHASE-0 PREFLIGHT IS COMPLETE.**

```
PHASE-4 APPROVAL — foundry-agent-reserved-prefix-reachability — Morpheus 2026-08-14
═══════════════════════════════════════════════════════════════════════════════════
RESOURCES (pending preflight confirmation)
  2 VNets · 2 VPN GW VpnGw1AZ (non-AA) · 1 VPN connection pair (2 objects)
  2 Standard PIPs · **3 VMs** (B2ts_v2): vm-onprem-echo, vm-onprem-ctrl, vm-diag
  3 BYO Foundry dependencies (Storage/Search/Cosmos) + 3 private endpoints
  6 private DNS zones (3 BYO + 3 Foundry pre-created)
  2 NSGs · 1 RG · **No ACR** (prompt agent, no container image)
  **Foundry account/OpenAI NOT created by IaC — Jose creates manually (portal-foundry-setup.md)**
  Optional (S5): 1 DNS Private Resolver
  Regions: swedencentral (Foundry) · norwayeast (on-prem simulator)

TIME  ~3-4 hours total (Wave 3 long pole: VPN GWs ~35 min)

COST GUARDRAIL  ✅ WITHIN LIMIT (rule #7, $50/day)
  Baseline ≈ $18.64/day · With DNS resolver ≈ $23.44/day · Confidence: MEDIUM
  Actual run cost ~$5-8 for a 4-5h session

⚠ PHASE-0 PREFLIGHT NOT YET RUN — approval cannot be final until preflight confirms:
  - Foundry availability in swedencentral
  - gpt-4o-mini availability
  - B2ts_v2 + VpnGw1 availability
  - Live price confirmation

SECRETS  PSK generated at deploy time; stored in KV platform-secrets-1138 or
         in-process shell vars. KV purge must run explicitly after cleanup.

APPROVAL REQUIRED FROM: Jose Moreno
  [ ] YES — proceed to Phase 0 preflight, then IaC + deployment
  [ ] NO  — cancel or revise

Morpheus/Tank will NOT deploy until explicit approval is received.
═══════════════════════════════════════════════════════════════════════════════════
```

---

## 14. Microsoft Learn References

- [Set up private networking for Foundry Agent Service — Limitations §](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/virtual-networks)
  — Source of the `172.30.0.0/16` reserved-range prohibition and its scope ("VNET and peered VNETs").
- [Deep dive into Foundry Agent Service networking](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agents-networking-deep-dive)
  — Subnet sizing, IP allocation model, hosted vs prompt agent traffic paths, data proxy architecture.
- [Azure VPN Gateway BGP overview](https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-bgp-overview)
  — BGP configuration for S2S; route propagation to VNet effective routes.
- [Azure Container Apps custom virtual networks](https://learn.microsoft.com/azure/container-apps/custom-virtual-networks)
  — Foundry agent subnet delegation behavior; NSG and UDR constraints.
- [Integrate with Azure Firewall (Container Apps)](https://learn.microsoft.com/azure/container-apps/use-azure-firewall)
  — FQDN allowlist for agent subnet egress; relevant if Azure Firewall is added later.
