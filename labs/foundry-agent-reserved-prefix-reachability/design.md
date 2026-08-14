# foundry-agent-reserved-prefix-reachability — Network Design
**Trinity (Azure Network SME) · 2026-08-14**  
**Status:** Design only — no Azure resources created. Phase 0 preflight and Phase 4 approval required.

---

## 1. Charter

This document is the authoritative networking specification for the `foundry-agent-reserved-prefix-reachability` lab. It supplements Morpheus's locked Stage-1 manifest with a complete packet-path analysis, route-plane evidence expectations, DNS resolution chain, failure-mode taxonomy, and observation guide for Niobe. No IaC is authored here; no Azure resources are created.

**Binary research question (preserved unchanged):** Does Foundry Agent Service, with VNet injection (BYO VNet), apply a runtime route-plane block on `172.30.0.0/16` when that prefix arrives via VPN BGP, or is the documented restriction scoped exclusively to VNet address-space declarations and peering relationships?

---

## 2. Structural Review of Manifest — Findings and Corrections

### 2.1 Blocking correction: VpnGw1 SKU retired

Manifest §3 specifies `VpnGw1 (non-AA)`. Azure blocked new `VpnGw1`–`VpnGw5` creation effective 2025-11-01. Deployments using these SKUs fail with `NonAzSkusNotAllowedForVPNGateway`. **Correct SKU: `VpnGw1AZ`.** Pricing correction: $0.21/hr × 2 × 24 = **$10.08/day** (vs. manifest's $9.12/day). Lab remains well within the $50/day guardrail. No other resource changes needed.

> _See Trinity history 2026-08-03 (dual-hub lab VpnGw1→VpnGw1AZ root-cause entry) and Microsoft docs gateway-sku-consolidation._

### 2.2 Blocking correction: Dual-NIC confounder in on-prem VM

Manifest §3 places a primary NIC (`172.30.100.4`, WorkloadSubnet) and a secondary NIC (`10.200.100.4`, CtrlSubnet) on `vm-onprem-server`. The comparison between S3 (control — calls `10.200.100.4`) and S4 (primary — calls `172.30.100.4`) is the core evidence pair. **A dual-NIC Linux VM will return responses for connections arriving at the secondary IP via whichever NIC holds the default route (typically primary NIC), producing an asymmetric TCP return path unless OS policy routing is explicitly configured.** This is a confounder: S3 may fail for routing reasons entirely unrelated to the platform reservation, invalidating the control.

**Replacement design (see §5):** Two single-NIC VMs, one per subnet, with identical nginx configurations. Each VM has one NIC, one default gateway, and a symmetric return path via VPN-injected routes. The only intentional variable between S3 and S4 is the destination IP prefix.

### 2.3 Correction: DNS Private Resolver subnet plan

Manifest §3 states "deploy Azure DNS Private Resolver inbound endpoint in PESubnet." DNS Private Resolver inbound and outbound endpoints each require a **dedicated /28 subnet** with a delegation to `Microsoft.Network/dnsResolvers`. They cannot share PESubnet with private endpoints. Two new subnets are added to vnet-foundry (see §4).

### 2.4 Non-blocking gap: Return-path gateway propagation not explicit for on-prem subnets

Manifest §3 enables gateway route propagation on AgentSubnet (vnet-foundry side) but does not specify the same for WorkloadSubnet and CtrlSubnet in vnet-onprem. vnet-foundry's address space (`192.168.0.0/16`) is advertised by vpngw-foundry to vpngw-onprem via BGP. vpngw-onprem injects this into vnet-onprem's route table **only if gateway route propagation is enabled on those subnets**. If propagation is disabled, vm-onprem-echo/ctrl will have no return route to `192.168.0.x` and S3/S4 will fail (no SYN-ACK). **Require: gateway route propagation enabled on all vnet-onprem subnets.** No UDR is needed on vnet-onprem subnets for this lab.

### 2.5 Non-blocking gap: AgentSubnet NSG — Container Apps delegation requirements

AgentSubnet is delegated to `Microsoft.App/environments`. Azure Container Apps in workload-profiles mode (which BYO-VNet Foundry uses) imposes specific NSG requirements. The manifest's NSG note is under-specified. See §7 for the full NSG spec. The key risk: overly restrictive NSG on AgentSubnet can prevent the data proxy from reaching VPN-learned routes, causing S4 to fail for infra reasons.

### 2.6 Non-blocking observation: TLS as a high-probability confounder

Manifest §5 identified TLS certificate validation as a potential confounder. The completed test used HTTPS
with the lab's self-signed certificates, and both calls succeeded. This resolves the confounder for this
specific run, but does not establish a documented Foundry trust-store contract.

---

## 3. Confirmed Topology

```
[Foundry Agent Service — prompt agent]
  Client sends HTTPS request to Foundry endpoint
  Foundry endpoint → Tools Service → Data Proxy (in AgentSubnet, 192.168.0.0/24)
  Data Proxy outbound → tool call → 172.30.100.4:80 (S4) or 10.200.100.4:80 (S3)
            |
     vpngw-foundry (VpnGw1AZ, AS 65010, swedencentral)
            | IKEv2 + BGP (eBGP AS 65010 ↔ AS 65020)
     vpngw-onprem (VpnGw1AZ, AS 65020, norwayeast)
            |
     vnet-onprem (172.30.0.0/16 + 10.200.100.0/24)
     ├── vm-onprem-echo  172.30.100.4  (nginx HTTP port 80, WorkloadSubnet)
     └── vm-onprem-ctrl  10.200.100.4  (nginx HTTP port 80, CtrlSubnet)
```

**What this simulates:** An on-premises network that owns `172.30.0.0/16` as legitimate address space, connected to the Foundry VNet via VPN BGP. The reserved-prefix restriction is documented to cover VNet address spaces and peered VNets only. The VPN route-plane is not mentioned in the restriction.

**What this does not simulate / cannot prove:**
- Physical on-premises hardware (Cisco/Juniper/Fortinet): the "on-prem" here is an Azure VNet; the network path is fully Azure-managed; no physical CPE NAT or IKE interop is tested.
- ExpressRoute connectivity: ER circuit provisioning is ~10× more expensive for this binary test; the route injection mechanism from the Foundry VNet's perspective is identical (BGP-learned route in effective-route table), but the precise path through the Microsoft backbone differs. Foundry platform enforcement — if any — may behave identically; this lab does not prove or disprove ER.
- Hosted agent path: the lab uses a prompt agent; the hosted agent path adds a Micro VM NIC, but tool calls still route through the data proxy per the deep-dive.
- Production BGP peer diversity: single active path, no failover, no ECMP.

---

## 4. Address Plan, Subnet Plan, and ASN

### 4.1 VNet address spaces

| VNet | Region | Address Space | Notes |
|------|--------|--------------|-------|
| vnet-foundry | swedencentral | `192.168.0.0/16` | Class C; universally supported; no reserved ranges |
| vnet-onprem | norwayeast | `172.30.0.0/16`, `10.200.100.0/24` | Owns the reserved prefix; control prefix on second address space |

No peering between vnet-foundry and vnet-onprem. The `172.30.0.0/16` address space on vnet-onprem does NOT appear in Foundry's address-space check because there is no peering relationship.

### 4.2 Subnet plan

**vnet-foundry (swedencentral):**

| Subnet | CIDR | Delegation / Notes |
|--------|------|--------------------|
| AgentSubnet | `192.168.0.0/24` | `Microsoft.App/environments` delegation; /24 per Foundry recommendation |
| PESubnet | `192.168.1.0/24` | Private endpoints only; no delegation; no NSG on PE NICs |
| GatewaySubnet | `192.168.255.0/27` | VPN GW; no UDR, no NSG (Azure hard requirement) |
| MgmtSubnet | `192.168.2.0/27` | vm-diag; no public IP; managed through Azure Run Command |
| DNSInboundSubnet | `192.168.3.0/28` | DNS Private Resolver inbound endpoint; `Microsoft.Network/dnsResolvers` delegation (S5 only) |
| DNSOutboundSubnet | `192.168.3.16/28` | DNS Private Resolver outbound endpoint; `Microsoft.Network/dnsResolvers` delegation (S5 only) |

**vnet-onprem (norwayeast):**

| Subnet | CIDR | Delegation / Notes |
|--------|------|--------------------|
| WorkloadSubnet | `172.30.100.0/24` | vm-onprem-echo primary NIC; gateway route propagation **enabled** |
| CtrlSubnet | `10.200.100.0/24` | vm-onprem-ctrl primary NIC; gateway route propagation **enabled** |
| GatewaySubnet | `172.30.255.0/27` | VPN GW; no UDR, no NSG |

> **Rationale for two single-NIC VMs vs dual-NIC:** Eliminates return-path asymmetry without OS policy routing complexity. Both VMs run identical nginx HTTP configuration. The only variable between S3 and S4 observations is the destination IP prefix. See §2.2.

### 4.3 IP assignments

| Resource | Subnet | IP |
|----------|--------|----|
| vpngw-foundry BGP peer | GatewaySubnet | auto-allocated from `192.168.255.0/27` (e.g., `192.168.255.4`) |
| vm-diag NIC | MgmtSubnet | `192.168.2.4` |
| Private endpoints × 5 | PESubnet | `192.168.1.4` – `192.168.1.9` (auto) |
| DNS inbound endpoint (S5) | DNSInboundSubnet | `192.168.3.4` |
| DNS outbound endpoint (S5) | DNSOutboundSubnet | `192.168.3.20` |
| vpngw-onprem BGP peer | GatewaySubnet | auto-allocated from `172.30.255.0/27` (e.g., `172.30.255.4`) |
| vm-onprem-echo NIC | WorkloadSubnet | `172.30.100.4` |
| vm-onprem-ctrl NIC | CtrlSubnet | `10.200.100.4` |

### 4.4 ASN plan

| Resource | ASN | Notes |
|----------|-----|-------|
| vpngw-foundry | 65010 | eBGP toward vpngw-onprem; Azure VPN GW default is 65515 — changed to avoid conflict with ARS if ever colocated |
| vpngw-onprem | 65020 | eBGP toward vpngw-foundry |

---

## 5. Route Plane: Origins, Advertisements, Effective Routes

### 5.1 BGP session

One eBGP session between vpngw-foundry (AS 65010, peer IP auto-assigned from GatewaySubnet) and vpngw-onprem (AS 65020, peer IP auto-assigned from its GatewaySubnet). IKEv2 S2S tunnel over the public internet. Non-active-active is sufficient; single tunnel, single BGP session.

### 5.2 Route origins and advertisements

**vpngw-onprem advertises to vpngw-foundry:**
- `172.30.0.0/16` — primary reserved address space
- `10.200.100.0/24` — control address space

Azure VPN Gateway advertises the connected VNet's declared address spaces. The target host remains
`172.30.100.4`, but the learned route under test is the full reserved `/16`.

**vpngw-foundry advertises to vpngw-onprem:**
- `192.168.0.0/16` — auto-originated from Foundry VNet address space (Azure VPN GW summarizes VNet address space at GW level)

> **Note:** Azure VPN GW does not advertise sub-prefix /24s individually unless subnets explicitly have propagation enabled AND the GW is configured to advertise them. For the Foundry VNet side, the /16 summary is sufficient — the on-prem VMs only need to return traffic to `192.168.0.x`.

### 5.3 Effective route expectations — AgentSubnet (vnet-foundry)

After BGP convergence, a VM in AgentSubnet (or the data proxy container) should show these entries in its effective route table:

| Prefix | Next Hop Type | Next Hop IP | Source | Required for |
|--------|--------------|-------------|--------|-------------|
| `192.168.0.0/16` | VNetLocal | — | VNet address space | Local VNet communication |
| `172.30.0.0/16` | VirtualNetworkGateway | vpngw-foundry instance IP | BGP via vpngw-foundry | S4 |
| `10.200.100.0/24` | VirtualNetworkGateway | vpngw-foundry instance IP | BGP via vpngw-foundry | S3 |
| `0.0.0.0/0` | Internet | — | Default (Azure) | Internet egress (blocked by NSG if desired) |

No route table is attached to AgentSubnet initially, so gateway route propagation remains at its default.
If a later UDR disables propagation, neither remote address space will be usable.

### 5.4 Effective route expectations — vnet-onprem subnets

After BGP convergence, WorkloadSubnet and CtrlSubnet in vnet-onprem should show:

| Prefix | Next Hop Type | Source | Required for |
|--------|--------------|--------|-------------|
| `172.30.0.0/16` | VNetLocal | VNet address space | Local routing within vnet-onprem |
| `10.200.100.0/24` | VNetLocal | VNet address space (second entry) | CtrlSubnet local |
| `192.168.0.0/16` | VirtualNetworkGateway | BGP via vpngw-onprem | Return path for data proxy source IPs |

**If `192.168.0.0/16` is missing from vnet-onprem effective routes**, vm-onprem-echo/ctrl will drop return traffic and S3/S4 will show SYN-at-server but no response — a return-path failure, not a platform restriction.

### 5.5 Propagation settings summary

| VNet | Subnet | GW Route Propagation | UDR |
|------|--------|---------------------|-----|
| vnet-foundry | AgentSubnet | Default propagation | None |
| vnet-foundry | GatewaySubnet | N/A (no route table on GW subnet) | None |
| vnet-foundry | PESubnet | Not required for this lab | None |
| vnet-onprem | WorkloadSubnet | **ENABLED** | None |
| vnet-onprem | CtrlSubnet | **ENABLED** | None |
| vnet-onprem | GatewaySubnet | N/A | None |

---

## 6. Dual-Prefix Control Design — Verdict and Specification

**Verdict: Replace dual-NIC with two single-NIC VMs.**

The following table shows the comparison between the original design and the corrected design:

| Variable | Dual-NIC design | Two single-NIC VMs (this design) |
|----------|-----------------|----------------------------------|
| Return path | Depends on Linux default route (primary NIC) unless policy routing configured | Each VM uses its own NIC gateway; return path is deterministic |
| NSG | Single NSG covering both IPs | Per-VM NSG; same rules, independently applied |
| nginx | One instance, two listening IPs | Two identical instances, one IP each |
| OS routing config | Policy routing required for correctness | None required beyond default routes |
| OS-level complexity | Medium (requires `ip rule add`, `ip route add default via GW table N`) | None |
| Intended variable isolated | **No** (return-path asymmetry confounds) | **Yes** (destination prefix is the only variable) |

**Specification of vm-onprem-echo and vm-onprem-ctrl:**

Both target VMs: `Standard_B2ts_v2`, Ubuntu 22.04 LTS, Standard SSD. No PIP. Manage them
through Azure Run Command or private SSH from vm-diag.

The Python echo service runs on port 80. Nginx provides HTTPS on port 443 with a self-signed
certificate for later runs. Each response includes the target VM's fixed private IP:
`{"echo":"X","label":"echo|ctrl","server_ip":"<target_ip>","request_url":"<dialed_url>","ts":"…","src_ip":"<remote_addr>"}`.

The response includes both endpoint and source IPs, proving which VM handled the request and that the
TCP connection arrived from the data proxy.

**dnsmasq on vm-onprem-echo only** (dns server for `onprem.lab` zone, used in S5):
- `echo.onprem.lab` → `172.30.100.4`
- `echo-ctrl.onprem.lab` → `10.200.100.4`

No dnsmasq on vm-onprem-ctrl (not needed).

---

## 7. NSG Requirements

### 7.1 nsg-agentsubnet (applied to AgentSubnet)

Container Apps workload-profiles environments (which BYO-VNet Foundry uses) require specific inbound rules. From Container Apps custom VNet docs (learn.microsoft.com/azure/container-apps/custom-virtual-networks):

| Priority | Direction | Protocol | Source | Destination | Port | Action | Notes |
|----------|-----------|----------|--------|-------------|------|--------|-------|
| 100 | Inbound | TCP | AzureLoadBalancer | Any | Any | Allow | Platform health probes |
| 200 | Inbound | Any | VirtualNetwork | VirtualNetwork | Any | Allow | Intra-VNet (PE → data proxy) |
| 4000 | Inbound | Any | Any | Any | Any | Deny | Default deny |
| 100 | Outbound | TCP | Any | `192.168.1.0/24` (PESubnet) | 443 | Allow | Outbound to private endpoints |
| 110 | Outbound | TCP | Any | `172.30.100.0/24` | 80,443 | Allow | Tool call to vm-onprem-echo (S4, S5) |
| 120 | Outbound | TCP | Any | `10.200.100.0/24` | 80,443 | Allow | Tool call to vm-onprem-ctrl (S3) |
| 130 | Outbound | UDP | Any | `168.63.129.16/32` | 53 | Allow | Azure DNS (required by Container Apps) |
| 140 | Outbound | TCP | Any | AzureMonitor | 443 | Allow | Log Analytics egress |
| 4000 | Outbound | Any | Any | Internet | Any | Deny | Block internet egress |

> **Warning:** The AgentSubnet delegation to `Microsoft.App/environments` may impose platform-managed NSG rules. Do not apply rules that contradict these. At deploy time, verify that the data proxy can reach private endpoints and VPN-learned routes. Capture effective NSG on the subnet from the Azure portal or via `az network nic list-effective-nsg` on a VM provisioned in the same subnet.

### 7.2 nsg-workload (applied to WorkloadSubnet in vnet-onprem)

| Priority | Direction | Source | Destination | Port | Action |
|----------|-----------|--------|-------------|------|--------|
| 100 | Inbound | `192.168.0.0/16` | `172.30.100.0/24` | 80, 443 | Allow |
| 200 | Inbound | `192.168.2.0/27` (MgmtSubnet) | `172.30.100.0/24` | 22 | Allow (private SSH from vm-diag) |
| 4000 | Inbound | Any | Any | Any | Deny |
| 100 | Outbound | Any | Any | Any | Allow |

### 7.3 nsg-ctrl (applied to CtrlSubnet in vnet-onprem)

Same as nsg-workload with destination/source adapted for `10.200.100.0/24`.

**Hard requirements: no NSG on GatewaySubnet (both VNets); no NSG on PE NICs in PESubnet.**

---

## 8. Symmetric Return Path Analysis

The data proxy in AgentSubnet calls `172.30.100.4:80` (S4). The source IP is from `192.168.0.0/24` (delegated subnet; exact IP unknown until runtime — capture from tcpdump evidence).

**Forward path (data proxy → vm-onprem-echo):**
1. Data proxy sends TCP SYN from `192.168.0.x` to `172.30.100.4:80`
2. AgentSubnet route selection: `172.30.0.0/16 → VirtualNetworkGateway (vpngw-foundry)`
3. vpngw-foundry encrypts and sends over IKEv2 tunnel to vpngw-onprem
4. vpngw-onprem decrypts; delivers to WorkloadSubnet
5. TCP SYN arrives at vm-onprem-echo (`172.30.100.4`)

**Return path (vm-onprem-echo → data proxy):**
1. vm-onprem-echo sends TCP SYN-ACK from `172.30.100.4` to `192.168.0.x`
2. WorkloadSubnet effective route: `192.168.0.0/16 → VirtualNetworkGateway (vpngw-onprem)` ← **requires gateway propagation on WorkloadSubnet (§5.4)**
3. vpngw-onprem encrypts and sends over tunnel to vpngw-foundry
4. vpngw-foundry decrypts; delivers to AgentSubnet
5. TCP SYN-ACK arrives at data proxy

**Asymmetry risk:** None, provided gateway route propagation is enabled on all vnet-onprem subnets. Both legs use the same VPN tunnel. There is no SNAT on the VPN gateway path; source IPs are preserved end-to-end.

**SNAT consideration from data proxy:** The deep-dive confirms the data proxy is a Container Apps-managed component in the delegated subnet. There is no documented SNAT at the data proxy. However, the platform could theoretically SNAT to a VNet IP. **Instruction to Niobe:** capture the exact source IP observed in `tcpdump` on vm-onprem-echo during S3/S4 runs. If it is outside `192.168.0.0/24`, record as SNAT evidence point.

---

## 9. DNS Resolution Chain for `echo.onprem.lab` (S5)

**Applies only if DNS Private Resolver is deployed (S5 in scope).**

```
[Data proxy in AgentSubnet]
  → DNS query: echo.onprem.lab
  → 168.63.129.16 (Azure DNS, VNet default resolver)
  → Azure DNS Private Resolver: outbound endpoint (192.168.3.20, DNSOutboundSubnet)
  → Forwarding ruleset: zone "onprem.lab" → 172.30.100.4:53
  → dnsmasq on vm-onprem-echo (UDP 53, vnet-onprem WorkloadSubnet)
  → Answer: A 172.30.100.4
  → Returns to outbound endpoint → 168.63.129.16 → data proxy

Data proxy resolves echo.onprem.lab → 172.30.100.4
Then makes tool call to https://echo.onprem.lab/api/echo → same path as S4
```

**Dependencies for S5:**
- DNS Private Resolver provisioned in vnet-foundry; inbound endpoint in DNSInboundSubnet (`192.168.3.4`); outbound endpoint in DNSOutboundSubnet (`192.168.3.20`)
- Forwarding ruleset: rule `onprem.lab → 172.30.100.4:53`
- dnsmasq running on vm-onprem-echo, listening on `172.30.100.4:53`; zones: `echo.onprem.lab A 172.30.100.4`, `echo-ctrl.onprem.lab A 10.200.100.4`
- NSG on WorkloadSubnet must allow UDP 53 inbound from `192.168.3.16/28` (outbound endpoint subnet)
- VNet link: Private DNS Resolver outbound uses VNet-linked private zones; the DNS forwarder ruleset (not a private zone) routes `onprem.lab` to dnsmasq; the ruleset must be associated with DNSOutboundSubnet

**What S5 proves independently of S4:** DNS resolution for a reserved-prefix hostname works through the forwarding chain. S5 does not further test whether `172.30.x.x` is blocked at the route plane; it tests the DNS path. S5 depends on S4 being unblocked (if S4 shows route-plane block, S5 cannot proceed).

**Vault synthesis:** Hybrid DNS pattern (AzureNetworking vault [[Topics/Hybrid-DNS]]) confirms this is the canonical on-prem hostname resolution architecture for BYO VNet scenarios. Private DNS Resolver replaces BIND VMs. Wildcard forwarding rules for `onprem.lab` are supported per vault 2026-05-18 entry.

---

## 10. Agent Probe Legitimacy

**Source:** [Deep dive into Foundry Agent Service networking](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agents-networking-deep-dive) — fetched 2026-08-14.

For a **prompt agent**, the traffic path is:
> Client → Foundry endpoint → Tools Service → **Data Proxy (in AgentSubnet, delegated subnet)** → tool server (via private endpoints or VPN-learned routes)

The deep-dive confirms: "Prompt agents use the single-tenant data proxy for all outbound connectivity." The data proxy "handles outbound connectivity for your agents. Each project gets its own isolated data proxy instance. All tool calls route through the data proxy."

**The probe is legitimate:** The OpenAPI function tool call (`echoReserved` to `https://172.30.100.4/api/echo`) is executed by the data proxy from within AgentSubnet (`192.168.0.0/24`). The network egress originates **inside the delegated subnet, using the VNet's effective route table.** This is precisely the correct origin point to test whether `172.30.0.0/16` VPN-learned routes are usable by the agent's outbound path.

This is distinct from a client-side request to the Foundry endpoint: vm-diag in MgmtSubnet tests the hybrid
path but not the managed data-proxy path. **The tool call, not the client request, is the correct probe origin.**

**Caveat:** The data proxy behavior regarding additional runtime IP-range filtering is not documented in the deep-dive. The deep-dive says: "Monitor data proxy health… via HTTP 5xx errors." If S4 fails, data proxy 5xx errors captured in diagnostic logs (Foundry diagnostic settings → Log Analytics) will distinguish a platform-layer block from a network-layer failure.

---

## 11. Observation Taxonomy

### 11.1 Route-plane observations

| Observation | Command category | Evidence value |
|-------------|-----------------|----------------|
| Foundry-side learned routes | `az network vnet-gateway list-learned-routes --name vpngw-foundry` plus effective routes on `nic-vm-diag` | Confirms `172.30.0.0/16` and `10.200.100.0/24` reached the VNet; the managed data-proxy NIC isn't directly inspectable |
| vpngw-onprem advertised routes | `az network vnet-gateway list-advertised-routes --name vpngw-onprem` | Confirms both address spaces are advertised |
| vpngw-onprem advertised routes | `az network vnet-gateway list-advertised-routes --name vpngw-onprem --peer <bgp-peer-ip>` | Confirms on-prem is originating both prefixes |
| vnet-onprem WorkloadSubnet effective routes | `az network nic show-effective-route-table` on vm-onprem-echo NIC | Confirms `192.168.0.0/16` return route present |
| BGP session state | `az network vnet-gateway show` → bgpSettings; or portal BGP peers view | Must show Connected/Established |

### 11.2 DNS-plane observations (S5 only)

| Observation | Command category | Evidence value |
|-------------|-----------------|----------------|
| Hostname resolution from vm-diag | `nslookup echo.onprem.lab 192.168.3.4` (inbound EP) | Confirms DNS resolver receives and forwards query |
| dnsmasq query log | SSH to vm-onprem-echo → `journalctl -u dnsmasq -f` | Confirms query arrived from DNS resolver outbound IP |
| DNS resolver diagnostics | Azure portal: Private DNS Resolver → Forwarding Rulesets → Metrics | Confirm queries forwarded |

### 11.3 Transport / application-plane observations

| Observation | Command category | Evidence value |
|-------------|-----------------|----------------|
| TCP SYN arrival at vm-onprem-echo | `tcpdump -i any -n 'tcp and port 80 and dst host 172.30.100.4'` on vm-onprem-echo | Critical for distinguishing H₀ vs H₁; see decision matrix |
| TCP SYN arrival at vm-onprem-ctrl | Same, port 80, dst `10.200.100.4` | S3 control; must precede S4 |
| Source IP of arriving SYN | Captured in tcpdump output | Identifies data proxy IP; reveals SNAT if outside `192.168.0.0/24` |
| nginx access log | `tail -f /var/log/nginx/access.log` on both VMs | HTTP 200 or connection-close event |
| HTTP response from diagnostic VM | `curl -v http://172.30.100.4/api/echo?msg=diag-test` from vm-diag | Validates infra before running agent |

### 11.4 Agent-semantic observations

| Observation | Command category | Evidence value |
|-------------|-----------------|----------------|
| Agent run tool call result | `az ai agent run show` or Foundry SDK; full run JSON → `tool_calls[].function.output` | Primary evidence for S3/S4/S5; HTTP status + body |
| Agent run status | Run state: `completed` / `failed` / `requires_action` | Top-level agent success/failure |
| Data proxy errors | Foundry diagnostic settings; discover available categories/tables at runtime | Helps distinguish platform-layer failure without assuming an undocumented log schema |
| Tool call error type | Error message in run JSON | `ConnectionRefused` vs `Timeout` vs `TLSHandshakeFailure` vs `HTTP 5xx` — each implicates a different failure layer |

---

## 12. Failure Localization Guide

Use this tree when S4 fails:

```
S4 FAIL
├── Is 172.30.0.0/16 learned by vpngw-foundry and present on vm-diag?
│   NO → VPN/BGP or VNet propagation issue. Check both connections and gateway learned routes.
│   YES → continue
├── Did TCP SYN arrive at vm-onprem-echo (tcpdump)?
│   NO → Platform or data proxy dropped traffic before egress.
│   │    Check: nsg-agentsubnet outbound rules; data proxy diagnostic logs (5xx type).
│   │    Interpretation: possible H₀ (runtime ACL on reserved prefix). Escalate to Microsoft.
│   YES → TCP arrived. continue
├── Did nginx log an HTTP request?
│   NO → TCP connection dropped before HTTP. Check: nsg-workload inbound rules; TLS handshake (if HTTPS).
│   YES → HTTP request received. continue
├── Did agent tool call return HTTP 200?
│   NO (HTTP error, e.g. 5xx from data proxy) → return-path issue or data proxy layer block.
│   │    Check: vm-onprem-echo effective routes (192.168.0.0/16 return route present?); source IP in tcpdump.
│   YES → Tool call succeeded. H₁ confirmed (record full evidence).
```

**S3/S4 correlation:**

| S3 | S4 | Interpretation |
|----|----|----------------|
| PASS | PASS | H₁ confirmed: VPN-learned reserved prefix is reachable identical to non-reserved prefix |
| PASS | FAIL (no SYN) | H₀ not rejected: platform drops traffic to reserved prefix before egress from data proxy |
| PASS | FAIL (SYN received, no response) | Return-path failure (check vnet-onprem effective routes) OR TLS issue |
| PASS | FAIL (HTTP error in agent) | Data proxy return-layer processing issue; check diagnostic logs |
| FAIL | — | Lab infra issue; fix S3 before running S4 |

---

## 13. Resiliency Analysis

**Single-path lab:** One VPN tunnel, one BGP session, one VPN GW in each region. Single failure domain.

| Failure | Lab impact | Recoverability | Production guidance |
|---------|-----------|----------------|---------------------|
| VPN tunnel drops | S3/S4 fail; routes withdrawn after BGP hold timer (~30–180 s) | Automatic (tunnel re-establishes via IKE DPD) | Active-active VPN GW + redundant tunnels |
| BGP hold timer expires without keepalive | Routes withdrawn from effective route table | Automatic (re-established with tunnel) | Faster KEEPALIVE timers; BFD (not supported on Azure VPN GW) |
| vpngw-foundry GW host maintenance | GW restarts; BGP session drops; ~1–2 min disruption | Automatic | VpnGw1AZ with zone redundancy provides AZ-level HA; non-AA is sufficient for this lab |
| vm-onprem-echo OS crash | S4 fails (TCP SYN arrives but no nginx response) | Manual restart | Two VMs for HA |
| AgentSubnet IP exhaustion | Data proxy cannot scale; HTTP 5xx | N/A (single test session; well below /24 capacity) | /24 subnet per deep-dive recommendation |

**Lab adequacy statement:** This lab uses a non-active-active VPN GW pair. This is adequate for a binary reachability test. The lab does not validate failover, convergence times, or production-scale BGP stability. These are out of scope.

**Do not conflate lab adequacy with production guidance:** A production design connecting an on-premises network owning `172.30.0.0/16` to Foundry would use ExpressRoute (dedicated, lower jitter, higher BGP prefix count) with active-active VPN GW as a backup path, not a single non-AA VPN GW. This lab proves the reachability principle; it does not certify a production architecture.

---

## 14. Known Unknowns and Explicit Uncertainty

The following items are **not known at design time** and may not be known until the lab is executed:

| ID | Unknown | Impact |
|----|---------|--------|
| U1 | **Primary hypothesis outcome** — does Foundry data proxy apply a runtime ACL on `172.30.0.0/16`? | S4 outcome is binary and unknown; do not assume H₁ |
| U2 | **Data proxy TLS enforcement** | Resolved for this run: both self-signed HTTPS endpoints succeeded; broader support contract remains undocumented |
| U3 | **Data proxy source IP** — is the source IP in `192.168.0.0/24` or does the platform SNAT to an unknown IP range? | Affects return-path analysis; capture from tcpdump |
| U4 | **NC-1 / NC-2 enforcement mechanism** — is the reserved-range check at ARM validation time, Foundry RP time, or health-check time? | Determines error message and evidence type for S1/S2 |
| U5 | **Container Apps NSG compatibility with AgentSubnet** — exact platform-managed rules applied by delegation | May supersede or supplement the NSG rules in §7 |
| U6 | **Foundry Agent Service availability in swedencentral** | Phase-0 preflight required; fallback region documented in manifest |

**Do not conclude reachability before validation.** Outcome is unknown.

---

## 15. Deferred Items (Not Executed in This Document)

The following are deferred to Phase 0 preflight or Phase 4 implementation planning:

- Foundry account and model availability checks in swedencentral
- Live price confirmation (all resources)
- IaC authoring (Tank, gated behind Phase-4 approval)
- Azure resource creation of any kind
- Container Apps NSG compatibility testing
- Foundry account creation and agent provisioning

---

## 16. Manifest Corrections Summary (for Morpheus reference)

The following corrections are applied to the manifest by Trinity. Morpheus's card is locked; these corrections apply to IaC authored by Tank and observation specs authored by Niobe:

| ID | Section | Correction | Severity |
|----|---------|-----------|----------|
| C1 | §3 Resource Inventory, §11 Cost | VpnGw1 → VpnGw1AZ; cost $9.12/day → $10.08/day | **Blocking** |
| C2 | §3 Resource Inventory | Replace dual-NIC vm-onprem-server with two single-NIC VMs: vm-onprem-echo (`172.30.100.4`) and vm-onprem-ctrl (`10.200.100.4`) | **Blocking** |
| C3 | §3 DNS Architecture | DNS Private Resolver requires two dedicated /28 subnets (DNSInboundSubnet, DNSOutboundSubnet); cannot share PESubnet | **Blocking if S5 in scope** |
| C4 | §3 Route Tables | Add explicit "gateway route propagation ENABLED" requirement to vnet-onprem WorkloadSubnet and CtrlSubnet | Non-blocking but operationally required |
| C5 | §3 NSGs | AgentSubnet NSG must include Container Apps platform requirements; manifest is under-specified | Non-blocking at design time; verify at deploy time |
| C6 | §5 Agent Workload | TLS was treated as a potential confounder; final HTTPS calls succeeded with the lab self-signed certificates | Resolved for this run |

---

## 17. References

- [Deep dive into Foundry Agent Service networking](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agents-networking-deep-dive) — Fetched 2026-08-14. Source of prompt agent path, data proxy architecture, and subnet sizing.
- [Set up private networking for Foundry Agent Service — Limitations](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/virtual-networks) — Fetched 2026-08-14. Verbatim reservation scope: "address spaces of your VNET… and peered VNETs."
- [Azure VPN Gateway BGP overview](https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-bgp-overview) — BGP configuration and route propagation to VNet effective routes.
- [Container Apps custom virtual networks](https://learn.microsoft.com/azure/container-apps/custom-virtual-networks) — NSG and UDR requirements for delegated subnet.
- [Azure DNS Private Resolver](https://learn.microsoft.com/azure/dns/dns-private-resolver-overview) — Hybrid DNS forwarding architecture.
- AzureNetworking vault [[Topics/Hybrid-DNS]] — Canonical hybrid DNS pattern; Private DNS Resolver replaces BIND VMs; wildcard forwarding rules supported.
- AzureNetworking vault [[Services/VPN-Gateway]] — BGP is mandatory for serious deployments; always use AZ SKU in AZ-supported regions; gateway-sku-consolidation (VpnGw1 retired).
- Trinity history 2026-08-03 — VpnGw1→VpnGw1AZ root cause and fix (dual-hub lab); confirms NonAzSkusNotAllowedForVPNGateway.
