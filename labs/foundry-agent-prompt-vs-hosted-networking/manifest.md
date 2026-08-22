# foundry-agent-prompt-vs-hosted-networking — Stage-1 Planning Manifest
Morpheus · 2026-08-20 · **Stage-1 LOCKED — Phase 0 preflight pending; Phase 4 deployment not yet authorized.**

---

## Card Summary

Empirically compare the network-layer behavior of a Foundry prompt agent and a hosted agent using
the same tool endpoints. The reserved-prefix reachability question is answered (see sibling lab);
this lab asks whether tool call source IPs, direct-code egress paths, and DNS resolution contexts
differ between agent types, and whether these differences are measurable at the target VM level.

**IN scope:** Prompt-vs-hosted agent comparison; OpenAPI tool call source IP; Micro VM NIC direct egress;
DNS forwarding chain uniformity; hostname-based tool definitions; programmatic invocation; local debug via
VS Code Foundry Toolkit; source-ZIP hosted agent deployment (no ACR).

**OUT of scope:** Reserved-prefix routing (answered in sibling lab); VPN/BGP; ExpressRoute; vWAN;
container-image hosted agent deployment (ACR); agent-to-agent orchestration; production hardening.

---

## 1. Hypotheses

> **H1 (tool call path):** Prompt agent tool calls and hosted agent OpenAPI tool calls both originate from
> the Foundry single-tenant data proxy. The source IP observed at the target VM is in the same IP range for
> both agent types. The data proxy path is NOT agent-type-specific.
>
> **H2 (direct code egress):** A hosted agent's own Python code that calls `requests.get(...)` directly
> (outside the tool framework) originates from the Micro VM's dedicated NIC. The source IP is in
> `192.168.0.0/24` (AgentSubnet) but is a DIFFERENT value from the data proxy IPs observed in H1.
>
> **H3 (DNS context):** The Foundry VNet DNS resolver applies uniformly to all containers in the VNet
> (data proxy and Micro VM NICs). DNS query source IPs that reach the upstream DNS server are the DNS
> Private Resolver outbound endpoint IP in both cases -- not the individual container IP. DNS resolution
> path does not differ by agent type.

Primary unknowns (OQ1, OQ3 from extension brief): whether Micro VM NIC IPs are distinguishable from data
proxy IPs by value (OQ1), and whether gateway propagation (if any future VPN is added) flows to Micro VM
NICs (OQ3 -- not relevant to this lab's peered topology).

---

## 2. Topology

### Shared prerequisite infrastructure (owned by sibling lab; not redeployed)

| Resource | Location | Purpose |
|----------|----------|---------|
| vnet-foundry (`192.168.0.0/16`) | swedencentral | Foundry platform VNet |
| AgentSubnet (`192.168.0.0/24`) | vnet-foundry | Data proxy + Micro VM NICs |
| PESubnet (`192.168.1.0/24`) | vnet-foundry | Private endpoints |
| MgmtSubnet (`192.168.2.0/27`) | vnet-foundry | vm-diag (`192.168.2.4`) |
| DNSInboundSubnet (`192.168.3.0/28`) | vnet-foundry | DNS resolver inbound EP |
| DNSOutboundSubnet (`192.168.3.16/28`) | vnet-foundry | DNS resolver outbound EP |
| GatewaySubnet (`192.168.255.0/27`) | vnet-foundry | Empty; kept for future use |
| Foundry account + project | swedencentral | Shared; not recreated |
| Model deployment (gpt-4o-mini or fallback) | swedencentral | Shared; not recreated |
| AI Search (Standard S1) | swedencentral | Foundry dep; shared |
| Cosmos DB (Serverless) | swedencentral | Foundry dep; shared |
| Storage account (LRS) | swedencentral | Foundry dep; shared |
| Private endpoints x5 + private DNS zones x6 | swedencentral | Foundry deps; shared |
| vm-diag (`192.168.2.4`) | MgmtSubnet | Diagnostic VM; shared |

### Lab-owned resources (new; not yet deployed)

| Resource | SKU / Tier | Location | IP | Purpose |
|----------|-----------|----------|----|---------|
| vnet-tools | -- | swedencentral | `10.1.0.0/16` | Tools VNet; peered to vnet-foundry |
| EchoSubnet | -- | vnet-tools | `10.1.100.0/24` | vm-tools-echo |
| CtrlSubnet | -- | vnet-tools | `10.1.200.0/24` | vm-tools-ctrl |
| VNet peering | bidirectional | swedencentral | -- | vnet-foundry ↔ vnet-tools; no gateway transit |
| vm-tools-echo | Standard_B2ts_v2 | swedencentral | `10.1.100.4` | Echo service + dnsmasq |
| vm-tools-ctrl | Standard_B2ts_v2 | swedencentral | `10.1.200.4` | Echo service (ctrl label) |
| DNS Private Resolver | -- | swedencentral | see subnets | Inbound EP `192.168.3.4`; outbound EP `192.168.3.20` |
| DNS forwarding ruleset | -- | -- | -- | `tools.lab -> 10.1.100.4:53` |
| Hosted agent (echo-probe-agent) | source-ZIP | swedencentral | -- | In existing Foundry project |

### Address plan

| VNet | Address space | Peered to | Notes |
|------|--------------|-----------|-------|
| vnet-foundry | `192.168.0.0/16` | vnet-tools | No reserved ranges; VPN GW not used |
| vnet-tools | `10.1.0.0/16` | vnet-foundry | No reserved ranges; allowed to peer |

**Peering constraint satisfied:** `10.1.0.0/16` is not a reserved Foundry range. Peering is allowed.
The reserved-prefix restriction (`172.30.0.0/16`) does not appear in either VNet's address space.

### DNS zone: `tools.lab`

Zone name `tools.lab` (not `onprem.lab`) because the target VMs are in a peered tools VNet, not a
simulated on-premises network. Using a distinct zone name prevents confusion with the VPN-era DNS config.

| Approach | Zone type | Records | Cost | Observability |
|----------|-----------|---------|------|--------------|
| Z1 (Azure Private DNS zone) | `tools.lab` linked to vnet-foundry | `echo A 10.1.100.4`, `ctrl A 10.1.200.4` | $0 | Low (no query logs) |
| Z2 (DNS Private Resolver + dnsmasq) | Forwarding ruleset `tools.lab -> 10.1.100.4:53` | dnsmasq on vm-tools-echo | ~$12.08/day | High (dnsmasq logs; OQ5 on resolver query logging) |

**Default: Z2.** DNS is first-class in this lab. Z1 is an authorized fallback if DNS Resolver deployment
is blocked by a Phase 0 preflight finding. Trinity to confirm.

dnsmasq on vm-tools-echo serves:
- `echo.tools.lab A 10.1.100.4`
- `ctrl.tools.lab A 10.1.200.4`

---

## 3. Scenarios

### HS1 -- Prompt agent OpenAPI tool call (hostname-based, data proxy path)

**Setup:** Prompt agent with `echo-reserved-dns.openapi.json` tool pointing to `https://echo.tools.lab/api/echo`.  
**Probe:** Agent run with `msg=probe-hs1-prompt`.  
**PASS:** HTTP 200; `request_url` contains `echo.tools.lab`; `src_ip` in `192.168.0.0/24` (data proxy IPs).  
**FAIL:** HTTP error or DNS resolution failure.  
**Baseline:** Compare `src_ip` to HS2 to test H1/H2.  
**Diagram:** D1 (T1 topology), D3 (agent paths).

---

### HS2 -- Hosted agent direct code call (Micro VM NIC path)

**Setup:** `echo-probe-agent` deployed; `main.py` calls `requests.get("http://echo.tools.lab/api/echo?msg=probe-hs2-code")` directly.  
**Probe:** Invoke `echo-probe-agent` via VS Code Playground or `azd ai agent invoke`.  
**PASS:** HTTP 200; `request_url` contains `echo.tools.lab`; `src_ip` in `192.168.0.0/24` AND DIFFERENT from HS1 data proxy IPs (H2 confirmed).  
**Ambiguous:** `src_ip` matches HS1 IPs (H2 inconclusive; OQ1 open; document as SNAT or shared pool).  
**FAIL:** TCP SYN never arrives at vm-tools-echo (OQ3 -- Micro VM NIC routing context lacks VNet peering routes).  
**Diagram:** D1, D3.

---

### HS3 -- Hosted agent DNS from Micro VM context

**Setup:** `main.py` also calls `requests.get("http://ctrl.tools.lab/api/echo?msg=probe-hs3-dns")`.  
**Pre-condition:** Z2 deployed; dnsmasq running on vm-tools-echo; forwarding ruleset linked to vnet-foundry.  
**PASS:** `ctrl.tools.lab` resolves to `10.1.200.4`; HTTP 200; dnsmasq log shows query from DNSOutboundSubnet SNAT pool (`192.168.3.21–25`), same source pool as prompt agent DNS (H3 hypothesis).
**FAIL:** NXDOMAIN (forwarding rule not propagated to Micro VM DNS context -- would disprove H3).  
**Diagram:** D4 (DNS chain).

---

### HS4 -- Prompt agent DNS forwarding (completing deferred S5)

**Setup:** Prompt agent with `ctrl-dns.openapi.json` tool pointing to `https://ctrl.tools.lab/api/echo`.  
**Pre-condition:** Same as HS3.  
**PASS:** HTTP 200; `request_url` contains `ctrl.tools.lab`; dnsmasq log shows query from `192.168.3.21–25` (DNSOutboundSubnet SNAT pool).
**Fail:** NXDOMAIN or HTTP error.  
**Comparative value:** HS3+HS4 confirm dnsmasq sees same outbound endpoint IP for both agent types -- H3 confirmed.  
**Diagram:** D4.

---

### HS5 -- Programmatic invocation without portal sandbox

**Setup:** `echo-probe-agent` deployed and routing configured.  
**Probe A (vm-diag inside VNet):** Python SDK call from vm-diag using `az vm run-command invoke` → `project.get_openai_client(agent_name="echo-probe-agent").responses.create(input=...)`.  
**Probe B (terminal):** `azd ai agent invoke echo-probe-agent "probe both echo endpoints"`.  
**PASS:** Both probes return a valid response. Note the agent endpoint URL (dedicated, not Foundry project endpoint). Confirm private DNS resolution of Foundry endpoint from vm-diag (C4).  
**FAIL:** 401/403 (RBAC -- Foundry Agent Consumer role missing on caller identity); 404 (wrong endpoint); connection refused (public access disabled and caller outside VNet).  
**Diagram:** D6 (client invocation).

---

## 4. NSG Requirements

### nsg-agentsubnet (applied to AgentSubnet)

No changes to existing rules 100, 200 (platform), 130 (Azure DNS). ADD:

| Priority | Direction | Source | Destination | Port | Protocol | Purpose |
|----------|-----------|--------|-------------|------|----------|---------|
| 110 | Outbound | Any | `10.1.100.0/24` | 80, 443 | TCP | Tool call to vm-tools-echo |
| 120 | Outbound | Any | `10.1.200.0/24` | 80, 443 | TCP | Tool call to vm-tools-ctrl |
| 125 | Outbound | Any | MicrosoftContainerRegistry | 443 | TCP | MCR base container image (ALL deploy modes) |
| 126 | Outbound | Any | AzureActiveDirectory | 443 | TCP | *.login.microsoft.com for Micro VM auth |

Remove (after VPN stack teardown is authorized): existing rules for `172.30.100.0/24` and `10.200.100.0/24`.

### nsg-tools (new; applied to EchoSubnet and CtrlSubnet in vnet-tools)

| Priority | Direction | Source | Destination | Port | Protocol | Purpose |
|----------|-----------|--------|-------------|------|----------|---------|
| 100 | Inbound | `192.168.0.0/16` | `10.1.0.0/16` | 80, 443 | TCP | Data proxy + Micro VM tool calls |
| 110 | Inbound | `192.168.3.16/28` | `10.1.100.0/24` | 53 | UDP+TCP | DNS outbound EP to dnsmasq |
| 200 | Inbound | `192.168.2.0/27` | `10.1.0.0/16` | 22 | TCP | SSH from vm-diag (Run Command) |
| 4000 | Inbound | Any | Any | Any | Any | Deny |
| 100 | Outbound | Any | Any | Any | Any | Allow |

---

## 5. OpenAPI Tool Documents (new; based on sibling lab docs)

| File | Servers URL | Scenarios |
|------|------------|----------|
| `agent-tools/echo-echo-dns.openapi.json` | `http://echo.tools.lab` | HS1 (prompt tool call) |
| `agent-tools/echo-ctrl-dns.openapi.json` | `http://ctrl.tools.lab` | HS4 (prompt tool call) |

Use HTTP (not HTTPS) for the initial run to avoid TLS hostname SAN complexity. HTTPS with updated cert
SANs is a contingency documented in the extension brief; switch only after empirical TLS test.

---

## 6. Phase 0 Preflight

All preflight conditions below must PASS before Phase 4 deployment is approved. Most conditions are satisfied
by the existing deployed sibling lab. New conditions apply only to the sibling lab's new resources.

| Check | Command | Expected |
|-------|---------|---------|
| Foundry account still healthy in swedencentral | Portal: Foundry account overview | Healthy |
| gpt-4o-mini (or fallback) still deployed | Portal: model deployments | Deployed, quota available |
| B2ts_v2 available in swedencentral | `az vm list-skus --location swedencentral --filter Standard_B2ts_v2` | Appears as available |
| `10.1.0.0/16` has no conflicts with existing VNets in the subscription | `az network vnet list --subscription <id>` | No overlap |
| Hosted agent (source-ZIP) support in swedencentral | Portal: Foundry project > Hosted Agents | Create button present |
| AgentSubnet NSG is compatible with new outbound rules | Review existing effective NSG on AgentSubnet | Rules 110/120 can be added |
| McR.microsoft.com + *.login.microsoft.com outbound from AgentSubnet | `az vm run-command invoke` on vm-diag: `curl -sI https://mcr.microsoft.com` for OQ4 diagnostic | HTTP 200. Required for ALL source-code deployments (both remote_build and bundled modes) |

---

## 7. Deployment Sequence

```
Wave 0  vnet-tools + EchoSubnet + CtrlSubnet + nsg-tools
Wave 1  VNet peering: vnet-foundry <-> vnet-tools
Wave 2  vm-tools-echo + vm-tools-ctrl (echo service + dnsmasq config for tools.lab)
Wave 3  DNS Private Resolver (if not already deployed from sibling lab preflight)
        DNS forwarding ruleset: tools.lab -> 10.1.100.4:53 + VNet link to vnet-foundry
Wave 4  AgentSubnet NSG patch: add rules 110, 120 (outbound to 10.1.x.x) + 125 (MicrosoftContainerRegistry) + 126 (AzureActiveDirectory)
Wave 5  Verify: curl http://10.1.100.4/api/echo from vm-diag; nslookup echo.tools.lab from vm-diag
Wave 6  Hosted agent deployment: echo-probe-agent via VS Code Foundry Toolkit (source-ZIP)
Wave 7  Scenario runs HS1 -> HS2 -> HS3/HS4 -> HS5
```

Jose performs Wave 6 manually via VS Code. Repository automation covers Waves 0-5 (Tank). Jose performs
diagnostic commands in Wave 7 (guided by Niobe pass/fail criteria).

---

## 8. Cost Estimate

All PAYG USD/day (confirmed via Azure Retail Prices API — preflight gate 7). Shared infra costs already running; shown for total context.

| Resource | Owner | $/day |
|----------|-------|-------|
| vnet-tools + peering | This lab | $0 |
| vm-tools-echo (B2ts_v2 Linux, $0.01/hr) | This lab | $0.24 |
| vm-tools-ctrl (B2ts_v2 Linux, $0.01/hr) | This lab | $0.24 |
| DNS Private Resolver (2 endpoints, $0.25/hr each) | This lab (optional, Z2) | $12.08 |
| Hosted agent compute (source-ZIP, per session) | This lab | ~$0.10-0.50 |
| **This lab incremental total (with DNS)** | | **~$12.56/day** |
| **This lab incremental total (no DNS, dnsmasq only)** | | **~$0.48/day** |
| | | |
| Shared Foundry infra (already running) | Sibling lab | ~$11.18 |
| VPN stack cleanup candidate (still running) | Sibling lab | ~$11.40 |
| **Total while VPN stack alive** | | **~$35.14/day** |
| **Total after VPN teardown authorized** | | **~$23.74/day** |

Rule 7 ($50/day guardrail): all configurations within guardrail.  
DNS Private Resolver dominates lab cost; set `deployDnsResolver=false` to save ~$12/day when DNS hierarchy testing is not the focus.

---

## 9. Cleanup Gate (this lab)

The sibling lab (reserved-prefix) VPN stack cleanup is governed by a separate gate. This lab's own cleanup:

**Resources owned by this lab (candidates for cleanup after lab completes):**
- vnet-tools, EchoSubnet, CtrlSubnet, nsg-tools
- vm-tools-echo, vm-tools-ctrl (and their NICs, OS disks)
- VNet peering objects
- DNS forwarding ruleset (if not used by other workloads)
- Hosted agent `echo-probe-agent` and its versions

**Resources NOT cleaned up by this lab:** Foundry account, model deployment, AI Search, Cosmos DB,
Storage, private endpoints, private DNS zones, vm-diag, vnet-foundry, DNS Private Resolver (shared).

**Gate conditions (same as sibling lab):** dry-run preview + Jose explicit "DELETE APPROVED".

---

## 10. References

| # | Source | Used for |
|---|--------|---------|
| 1 | Sibling lab: `../foundry-agent-reserved-prefix-reachability/` | Shared infra baseline; H₁ evidence |
| 2 | `.squad/decisions/inbox/morpheus-foundry-hosted-agent-extension.md` (v1.1) | DNS first-class; scenarios HS1-HS5; zone candidates |
| 3 | `.squad/decisions/inbox/morpheus-foundry-vscode-walkthrough.md` | VS Code deployment walkthrough (Wave 6) |
| 4 | `.squad/decisions/inbox/morpheus-foundry-topology-rethink.md` | T1 topology spec; cost analysis; Mermaid D1-D6 |
| 5 | `.squad/decisions/inbox/morpheus-foundry-lab-restructure.md` | Sibling folder decision; cleanup gate |
| 6 | https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agents-networking-deep-dive | Data proxy and Micro VM NIC paths |
| 7 | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/virtual-networks | Peering restriction; shared infra requirements |
