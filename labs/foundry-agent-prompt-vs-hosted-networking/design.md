# foundry-agent-prompt-vs-hosted-networking — Network Design
**Trinity (Azure Network SME) · 2026-08-20**
**Status:** Design complete. T1 deployed 2026-08-20/21; scenarios HS1–HS5 + NSG negative complete. VPN cleanup (Gate A) pending.

---

## 1. Charter

Authoritative networking specification for `foundry-agent-prompt-vs-hosted-networking`. Supplements the locked Stage-1 manifest with packet-path analysis, DNS chain, NSG/peering spec, evidence expectations, failure-localization tree, and resiliency analysis. No IaC authored; no Azure resources created.

**Hypotheses under test:** (H1) Prompt and hosted OpenAPI tool calls share the same source IP range. (H2) Hosted-agent direct Python code produces a distinct source IP from the data proxy. (H3) DNS resolution is context-transparent across agent types — the observable difference between contexts is what can be confirmed.

`172.30.0.0/16` (T2 VPN topology) is confirmed historical; cleanup is directionally authorized (Jose, 2026-08-20). Deletion requires Gate A (see §14). T1 resources deployed via Gate B (2026-08-20).

---

## 2. Manifest Corrections

### C1 — MCR firewall requirement scope (blocking)

**Manifest §6** reads: "McR.microsoft.com outbound from AgentSubnet … if remote_build path chosen."

**Correction (authoritative):** Microsoft docs (learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent-code, accessed 2026-08-20) state:

> "Firewall requirements for private virtual networks: All source-code deployments require outbound access to: 1. `mcr.microsoft.com` 2. `*.login.microsoft.com`"

This applies to **both** `remote_build` and `bundled` modes. `bundled` eliminates the server-side pip install but the base container image is still pulled from MCR at Micro VM startup. No source-code deployment path avoids MCR. The preflight check must verify MCR reachability regardless of `--dep-resolution` choice.

Precise correction recorded in `.squad/decisions/inbox/trinity-foundry-network-design.md` for Morpheus/Oracle.

### C2 — Extension brief zone names are superseded (informational)

`morpheus-foundry-hosted-agent-extension.md` uses zone `onprem.lab` (T2 topology). The locked manifest uses `tools.lab` (T1 topology). This design uses `tools.lab` exclusively.

### C3 — dnsmasq host for both records is vm-tools-echo (informational)

The forwarding ruleset rule `tools.lab → 10.1.100.4:53` routes ALL `tools.lab` queries — including `ctrl.tools.lab` — to vm-tools-echo's dnsmasq. vm-tools-ctrl runs no DNS service. Correct as designed.

---

## 3. Topology (T1 — Peered Tools VNet)

```
[Foundry Platform — Microsoft-managed]
  Foundry endpoint (<account>.services.ai.azure.com  private via PE in PESubnet)
  Data Proxy    AgentSubnet 192.168.0.x  (prompt agent + hosted agent tool calls)
  Micro VM NIC  AgentSubnet 192.168.0.y  (hosted agent code calls; y != x at runtime)

vnet-foundry (192.168.0.0/16, swedencentral)
  AgentSubnet       192.168.0.0/24   Microsoft.App/environments delegation
  PESubnet          192.168.1.0/24   Foundry private endpoints (x5)
  MgmtSubnet        192.168.2.0/27   vm-diag 192.168.2.4
  DNSInboundSubnet  192.168.3.0/28   DNS Resolver inbound EP 192.168.3.4
  DNSOutboundSubnet 192.168.3.16/28  DNS Resolver outbound EP 192.168.3.20
  GatewaySubnet     192.168.255.0/27 EMPTY (no VPN GW)

      <-------- bidirectional VNet peering (no gateway transit) -------->

vnet-tools (10.1.0.0/16, swedencentral)
  EchoSubnet  10.1.100.0/24   vm-tools-echo 10.1.100.4  (echo service + dnsmasq)
  CtrlSubnet  10.1.200.0/24   vm-tools-ctrl 10.1.200.4  (echo service only)
```

`172.30.0.0/16` does not appear in either VNet's address space. The T2 VPN/BGP topology is an **active cleanup candidate**; directional authorization granted 2026-08-20. Deletion has not occurred and will not occur until Gate A pre-conditions are met (see §14).

---

## 4. Z1 vs Z2 DNS Decision

**Decision: Z2 (DNS Private Resolver + dnsmasq). Z1 is an authorized fallback only.**

**Why Z2:** Z2 enables dnsmasq timestamped query logs, a realistic hybrid DNS forwarding chain, and the OQ5 probe (DNS Private Resolver diagnostic logs may expose pre-SNAT originating client IP, directly distinguishing data proxy vs Micro VM NIC DNS contexts). Z1 is silent — no query observability.

### What Z2 can and cannot prove

**Documented behavior** (learn.microsoft.com/azure/dns/private-resolver-endpoints-rulesets, accessed 2026-08-20): The DNS Private Resolver forwarding ruleset is linked at the **VNet level**, not the subnet level. All resources in vnet-foundry share the same forwarding chain. The outbound endpoint (`192.168.3.20`) performs SNAT from the `192.168.3.16/28` DNSOutboundSubnet pool; dnsmasq observes query source IPs from `192.168.3.21–25` (the SNAT pool, not the endpoint address itself) regardless of originating container. The chain is context-transparent by design.

| Z2 can prove | Z2 cannot prove (without OQ5 diagnostic logs) |
|---|---|
| DNS resolution works for both agent types (FQDN in request_url) | Which specific container or NIC type initiated the query |
| H3 documented-behavior-confirmed if HS3+HS4 both pass | Pre-SNAT originating IP (hidden by outbound endpoint SNAT) |
| Timing: dnsmasq log timestamp correlates with agent invocation | Whether data proxy vs Micro VM NIC DNS context is distinct |

**OQ5 gate:** At deploy time, check Azure Monitor Diagnostic Settings on the DNS Private Resolver for a query log category. If available, enable it — logs exposing the pre-SNAT client IP would directly confirm or refute H3 with per-context evidence.

**Zone conflict rule:** Do not create an Azure Private DNS zone named `tools.lab`. Private zones take precedence over forwarding rulesets. Existing Foundry zones (`privatelink.*`) use distinct names and do not conflict.

**dnsmasq on vm-tools-echo** (`/etc/dnsmasq.d/tools.lab.conf`):
```
address=/echo.tools.lab/10.1.100.4
address=/ctrl.tools.lab/10.1.200.4
```

---

## 5. HTTP vs HTTPS Decision

**Initial run: HTTP (port 80). HTTPS with hostname SANs is the documented upgrade path.**

The echo service serves HTTP on port 80. A tool call to `http://echo.tools.lab/api/echo` returns `request_url` with the FQDN, proving DNS resolution without any TLS ceremony. This cleanly isolates DNS and routing from TLS trust-store behavior.

**Trust implication:** Sibling lab Lesson 4 (2026-08-14) confirmed the data proxy accepted self-signed IP-SAN certs for IP-addressed HTTPS URLs — observed behavior, not a documented contract. For hostname-based HTTPS (SNI=`echo.tools.lab`), the cert CN/SAN must match. Existing echo VM certs cover IP SANs only; they will likely fail hostname-based validation.

**HTTPS upgrade path** (apply after HTTP baseline succeeds):
```bash
# vm-tools-echo:
openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
  -keyout /etc/nginx/ssl/server.key -out /etc/nginx/ssl/server.crt \
  -subj "/CN=echo.tools.lab" \
  -addext "subjectAltName=DNS:echo.tools.lab,IP:10.1.100.4"
# vm-tools-ctrl: same, substituting ctrl.tools.lab / 10.1.200.4
```
Then update OpenAPI `servers.url` from `http://` to `https://`.

---

## 6. Hosted-Agent Source Deployment Egress

### remote_build vs bundled

| Mode | Behavior | Internet surface |
|---|---|---|
| `remote_build` (default) | Agent Service installs dependencies server-side from requirements.txt | pip + MCR + AAD |
| `bundled` | User pre-installs dependencies into the zip; no server-side pip | MCR + AAD (pip eliminated) |

**Key finding (authoritative, not hypothesis):** Docs state "All source-code deployments require outbound access to: 1. `mcr.microsoft.com` 2. `*.login.microsoft.com`". This is independent of `--dep-resolution`. `bundled` eliminates server-side pip but cannot eliminate the base container image pull from MCR at Micro VM startup. Both modes require the same NSG rules.

**Recommendation: use `bundled`.** The only dependency is `requests` (pure Python, no compiled extensions). Pre-bundling eliminates transient pip failures and makes deployment deterministic. NSG rules 125+126 are required regardless.

**OQ4 diagnostic (run at Phase 0 preflight, before Wave 6):**
```bash
az vm run-command invoke -g <rg> -n vm-diag \
  --command-id RunShellScript \
  --scripts "curl -sI https://mcr.microsoft.com 2>&1 | head -5"
```
PASS: HTTP 200 or 301 headers visible. FAIL: timeout/DNS error — add NSG rule 125 before proceeding.

---

## 7. Peering Flags, NSG, Routes, DNS Ruleset

### 7.1 Peering Flags

| Direction | allowVNAccess | allowForwardedTraffic | allowGatewayTransit | useRemoteGateways |
|---|---|---|---|---|
| vnet-foundry → vnet-tools | true | false | false | false |
| vnet-tools → vnet-foundry | true | false | false | false |

No gateways in either VNet; gateway transit is inapplicable.

### 7.2 NSG — nsg-agentsubnet additions (outbound)

Existing rules 100, 200 (platform inbound), 130 (Azure DNS outbound), and 4000 (deny all inbound) are preserved.

| Priority | Dir | Destination | Port | Proto | Purpose |
|---|---|---|---|---|---|
| 110 | Out | `10.1.100.0/24` | 80,443 | TCP | Tool + code calls to vm-tools-echo |
| 120 | Out | `10.1.200.0/24` | 80,443 | TCP | Tool + code calls to vm-tools-ctrl |
| 125 | Out | MicrosoftContainerRegistry | 443 | TCP | MCR base image (both deploy modes) |
| 126 | Out | AzureActiveDirectory | 443 | TCP | *.login.microsoft.com for hosted agent auth |

Rules for `172.30.100.0/24` and `10.200.100.0/24` are **active cleanup candidates** once T2 resources are deleted. Remove these rules in the same execution pass as T2 teardown (Gate A). They remain in place until then.

### 7.3 NSG — nsg-tools (new; applied to EchoSubnet and CtrlSubnet)

| Priority | Dir | Source | Destination | Port | Proto | Purpose |
|---|---|---|---|---|---|---|
| 100 | In | `192.168.0.0/16` | Any | 80,443 | TCP | Data proxy and Micro VM tool calls |
| 110 | In | `192.168.3.16/28` | `10.1.100.0/24` | 53 | UDP+TCP | DNS outbound EP to dnsmasq |
| 200 | In | `192.168.2.0/27` | Any | 22 | TCP | SSH from vm-diag |
| 4000 | In | Any | Any | Any | Any | Deny |
| 100 | Out | Any | Any | Any | Any | Allow |

Rule 110 is harmless on CtrlSubnet (no dnsmasq process). A single shared nsg-tools applied to both subnets is simplest.

### 7.4 Effective Route Expectations

**AgentSubnet after peering:** `192.168.0.0/16` VNetLocal; `10.1.0.0/16` VNetPeering; `0.0.0.0/0` Internet (blocked by NSG 4000 outbound).
**EchoSubnet/CtrlSubnet after peering:** `10.1.0.0/16` VNetLocal; `192.168.0.0/16` VNetPeering; `0.0.0.0/0` Internet.
No UDRs required. No gateway route propagation relevant (no gateways deployed).

### 7.5 DNS Forwarding Ruleset

| Property | Value |
|---|---|
| Outbound endpoint | `192.168.3.20` (DNSOutboundSubnet) |
| Ruleset rule | `tools.lab.` → `10.1.100.4:53` |
| VNet link | vnet-foundry (applies to ALL subnets: AgentSubnet, MgmtSubnet, etc.) |

Existing Foundry private DNS zone links serve the C4 path (Foundry endpoint via PE) and do not conflict with `tools.lab`.

---

## 8. Distinct Packet Paths

### P1 — Prompt-agent OpenAPI tool call (HS1)

Data proxy (`192.168.0.x`) resolves `echo.tools.lab` via `168.63.129.16` → outbound EP (`192.168.3.20` configured frontend; SNAT pool `192.168.3.21–25` observed at dnsmasq — see §4) → dnsmasq → `A 10.1.100.4`. TCP to `10.1.100.4:80` via VNetPeering. **src_ip at vm-tools-echo:** data proxy IP from `192.168.0.0/24`. Documented behavior.

### P2 — Hosted-agent OpenAPI tool call via Toolbox (HS1 hosted variant)

Same data-plane path as P1. Tool server calls always route through the data proxy regardless of agent type (documented: agents-networking-deep-dive, 2026-08-20). Whether the exact IP value differs from P1 is OQ1.

### P3 — Hosted-agent direct Python code call, Micro VM NIC (HS2/HS3)

Micro VM NIC (`192.168.0.y`, `y != x`) resolves via same forwarding chain (VNet-level ruleset; same outbound EP configured frontend `192.168.3.20`, SNAT pool `192.168.3.21–25` at dnsmasq — see §4). TCP to `10.1.100.4:80` (HS2) or `10.1.200.4:80` (HS3) via VNetPeering. **src_ip at target VM:** Micro VM NIC IP from `192.168.0.0/24`, expected distinct from data proxy IPs (H2 hypothesis — empirical confirmation required by HS2). Ambiguous outcome: if src_ip matches a known data proxy IP, document as OQ1 (SNAT or shared pool); not FAIL.

### P4 — Prompt-agent DNS forwarding for ctrl (HS4)

Same as P1 but target is `ctrl.tools.lab` via `echo-ctrl-dns.openapi.json`. Data proxy resolves `ctrl.tools.lab` → `10.1.200.4` via same forwarding chain.

### P5 — Client-to-private-Foundry ingress (HS5, C4 path)

vm-diag (`192.168.2.4`) resolves `<account>.services.ai.azure.com` via `168.63.129.16` → private DNS zone `privatelink.services.ai.azure.com` (linked to vnet-foundry) → PESubnet A record (`192.168.1.x`). TCP HTTPS to `192.168.1.x:443`. DNS split-horizon: from inside vnet-foundry → PE IP; from internet → public IP or CNAME.

---

## 9. Ingress/Egress Dependency Matrix

### Egress path summary

| Egress source | DNS ctx | DNS query src at dnsmasq | TCP src at target | Scenarios |
|---|---|---|---|---|
| Data proxy (AgentSubnet) | C1 — VNet forwarding ruleset | `192.168.3.21–25` (DNSOutboundSubnet SNAT pool) | `192.168.0.x` | HS1, HS4 |
| Micro VM NIC (AgentSubnet) | C3 — same VNet forwarding ruleset | `192.168.3.21–25` (same SNAT pool; indistinguishable from C1 by dnsmasq alone) | `192.168.0.y` (expected != x; empirical) | HS2, HS3 |
| vm-diag (MgmtSubnet) | C4 — private DNS zones | N/A (private zone, not forwarding) | `192.168.2.4` | HS5 |
| Micro VM startup | N/A | N/A | AgentSubnet → mcr.microsoft.com (internet) | Deploy |

### Coupling and independence

| Choice | Independent of | Coupled to |
|---|---|---|
| Z2 (DNS Private Resolver) | HTTP/HTTPS, deploy mode | NSG rule 110 nsg-tools; outbound EP subnet; ruleset VNet link |
| HTTP-first | DNS topology, peering, deploy mode | OpenAPI tool document `servers.url` scheme |
| bundled mode | Z1/Z2, HTTP/HTTPS | NSG rules 125+126 — required for all source-code deploy modes |
| Bidirectional peering | DNS topology | NSG rules 110+120 in nsg-agentsubnet (routes exist only after peering active) |
| nsg-tools rule 110 (port 53) | Peering, HTTP/HTTPS | Z2: outbound EP must reach dnsmasq; UDP+TCP port 53 must be open |
| Hosted agent RBAC | All network choices | Foundry Project Manager (deploy); Agent Consumer (invoke) |

---

## 10. Scenario Evidence Checklist

### HS1 — Prompt-agent OpenAPI tool call (hostname-based, data proxy path)

Pre-conditions: peering active, dnsmasq running, DNS resolver + ruleset live, NSG rules 110+120 added to nsg-agentsubnet.

| Check | Expected | Failure meaning |
|---|---|---|
| `nslookup echo.tools.lab` from vm-diag | `10.1.100.4` | DNS chain broken; check ruleset VNet link, dnsmasq |
| `request_url` in echo response | Contains `echo.tools.lab` | Foundry not using FQDN; check OpenAPI doc `servers.url` |
| HTTP 200 | Received | Routing or NSG issue; see failure tree |
| `src_ip` | `192.168.0.x` in /24 | Unexpected egress; escalate |
| dnsmasq log | Query from `192.168.3.21–25` (DNSOutboundSubnet SNAT pool) | If absent: nsg-tools rule 110 blocking port 53, or dnsmasq not listening |

### HS2 — Hosted-agent direct code call (Micro VM NIC path)

| Check | Expected | Failure meaning |
|---|---|---|
| Deployment status | `active` | MCR unreachable (add NSG 125) or RBAC missing |
| HTTP 200; FQDN in request_url | Received | Route missing (peering) or NSG 110 absent |
| `src_ip` differs from HS1 data proxy IPs | H2 confirmed | If same IP: OQ1 open; document as SNAT/shared pool; not FAIL |
| tcpdump on vm-tools-echo | Two distinct src IPs (HS1 vs HS2) | Single IP: platform SNAT; document OQ1 |

### HS3 — Hosted-agent DNS from Micro VM context (ctrl.tools.lab)

| Check | Expected | Failure meaning |
|---|---|---|
| HTTP 200; `server_ip=10.1.200.4`; ctrl.tools.lab in request_url | Received | ctrl record missing in dnsmasq or nsg-tools rule 100 not covering CtrlSubnet |
| dnsmasq log | Query for `ctrl.tools.lab` from `192.168.3.21–25` (SNAT pool) | If absent: ruleset rule missing or dnsmasq not responding |
| `src_ip` | Same Micro VM NIC IP as HS2 | If different: NIC IP rotated between sessions; note and document |

### HS4 — Prompt-agent DNS forwarding, ctrl (completing deferred S5)

Same structure as HS3 using prompt agent with `echo-ctrl-dns.openapi.json`. PASS = HTTP 200 from data proxy to ctrl.tools.lab. Combined with HS3: dnsmasq sees source IPs from `192.168.3.21–25` (DNSOutboundSubnet SNAT pool) for both contexts — **H3 documented-behavior-confirmed**.

### HS5 — Programmatic invocation + private Foundry endpoint

| Check | Expected | Failure meaning |
|---|---|---|
| `nslookup <account>.services.ai.azure.com` from vm-diag | PESubnet IP `192.168.1.x` | Private DNS zone not linked to vnet-foundry |
| SDK call from vm-diag | Valid agent response | RBAC (Consumer role missing) or wrong endpoint URL |

---

## 11. Failure-Localization Tree

```
HS1/HS2 FAIL: DNS resolution failure (NXDOMAIN or timeout)
|
+-- nslookup echo.tools.lab from vm-diag returns NXDOMAIN
|   +-- DNS Private Resolver not deployed --> deploy Wave 3 first
|   +-- Forwarding ruleset tools.lab rule absent --> add rule
|   +-- Ruleset not linked to vnet-foundry --> add VNet link
|   +-- dnsmasq not running --> sudo systemctl restart dnsmasq
|
+-- nslookup returns 10.1.100.4 but HTTP times out
|   +-- VNet peering Disconnected --> check peering status; re-create
|   +-- NSG 110/120 absent from nsg-agentsubnet --> add outbound rules
|   +-- nsg-tools rule 100 wrong source CIDR --> verify 192.168.0.0/16
|
+-- HTTP arrives but 5xx
    +-- Echo service not running --> sudo systemctl restart echo-service

HS2 FAIL: Micro VM deployment or routing
|
+-- Deploy never reaches "active"
|   +-- MCR unreachable --> add NSG 125; re-run OQ4 diagnostic
|   +-- login.microsoft.com unreachable --> add NSG 126 (AzureActiveDirectory)
|   +-- RBAC missing --> request Foundry Project Manager at project scope
|
+-- Deploy active but code call fails
|   +-- TCP SYN never arrives (tcpdump confirms)
|   |   +-- Peering not bidirectional --> verify both peering objects Connected
|   |   +-- NSG 110 blocks AgentSubnet outbound to 10.1.0.0/16
|   +-- TCP SYN arrives, no SYN-ACK
|       +-- nsg-tools rule 100 wrong CIDR or proto
|       +-- vnet-tools peering to vnet-foundry absent on tools side

HS5 FAIL
|
+-- nslookup returns public IP --> private DNS zone not linked to vnet-foundry
+-- 401/403 --> Foundry Agent Consumer role missing on invoker identity
+-- Connection refused --> public access disabled; call from inside VNet only
+-- 404 --> wrong endpoint URL; use agent endpoint from azd deploy output
```

---

## 12. Resiliency Analysis and Dormant Patch Catalogue

Analysis is proportional to this teaching lab's short window.

### Failure modes

| ID | Failure | Impact | Recovery |
|---|---|---|---|
| F1 | vm-tools-echo crash | HS1-HS4 all fail (dnsmasq + echo service down) | Restart VM; `sudo systemctl restart dnsmasq && sudo systemctl restart echo-service` |
| F2 | vm-tools-ctrl crash | HS3, HS4 ctrl-path fail only | Restart VM; restart echo service |
| F3 | DNS Private Resolver endpoint unhealthy | All FQDN scenarios fail | Fallback P-D1 (Z1); file support ticket |
| F4 | VNet peering Disconnected or deleted | All cross-VNet traffic fails | Re-create both peering objects; ARM op under 2 minutes |
| F5 | NSG over-restricts AgentSubnet | Tool calls or deploy fail selectively | Identify via NSG flow logs; add targeted exception |
| F6 | MCR unreachable at deploy | Hosted agent deploy fails | Apply P-D2; verify OQ4; re-deploy |

### Dormant patch catalogue

| ID | Patch | When | Effect |
|---|---|---|---|
| P-D1 | Create private DNS zone `tools.lab` linked to vnet-foundry; A records `echo→10.1.100.4`, `ctrl→10.1.200.4` | F3: resolver down | Restores FQDN resolution; loses dnsmasq observability; H3 degrades to documented-behavior-only |
| P-D2 | Add NSG rule 125 (MicrosoftContainerRegistry, TCP 443 outbound from AgentSubnet) | F6: MCR blocked | Enables hosted agent deploy |
| P-D3 | `sudo systemctl restart dnsmasq` on vm-tools-echo | F1: dnsmasq crash | Restores DNS; no Azure API call; configure systemd restart policy as hardening |
| P-D4 | HTTPS cert re-issue on both VMs with hostname SANs (see §5 commands) | TLS hostname mismatch (HTTPS upgrade path only) | Enables hostname-based HTTPS tool calls |

---

## 13. Authoritative Sources

All accessed **2026-08-20**.

| # | URL / Source | Used for |
|---|---|---|
| 1 | https://learn.microsoft.com/azure/foundry/agents/concepts/agents-networking-deep-dive | Micro VM NIC vs data proxy paths; tool call routing (P1-P3 documented basis) |
| 2 | https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent-code | remote_build vs bundled semantics; MCR firewall requirement (C1 correction) |
| 3 | https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks | Reserved prefix scope; VNet injection requirements |
| 4 | https://learn.microsoft.com/azure/dns/private-resolver-endpoints-rulesets | Ruleset at VNet level; SNAT behavior; H3 documented basis |
| 5 | https://learn.microsoft.com/azure/dns/dns-private-resolver-overview | DNS resolution order: private zones before forwarding rulesets; Z1/Z2 conflict rule |
| 6 | `../foundry-agent-reserved-prefix-reachability/results.md` | Data proxy source IPs observed (192.168.0.49, 192.168.0.239); TLS self-signed observation |
| 7 | `.squad/decisions/inbox/morpheus-foundry-topology-rethink.md` (2026-08-20) | T1 topology spec; VPN historical status |
| 8 | `.squad/decisions/inbox/morpheus-foundry-lab-restructure.md` (2026-08-20) | Sibling lab decision; shared infra boundary; cleanup gate |


---

## 14. Transition Gates

Jose authorized the directional change from T2 (VPN/BGP) to T1 (peered tools VNet) on 2026-08-20. No resources have been created or deleted. Two **separate, sequential** confirmation gates govern execution; neither implies the other.

Full detail (evidence commands, dry-run preview, teardown order, resource tables) is in `.squad/decisions/inbox/trinity-foundry-vpn-cleanup-plan.md`.

### Gate A — T2 Cleanup (destructive)

**Status: directionally authorized. Not yet executed.**

All three pre-conditions must be met before deletion begins:

1. **Evidence preservation** — run and commit the capture commands in the cleanup plan (effective routes on vm-diag, learned routes on vpngw-foundry, advertised routes, portal screenshots).
2. **Dry-run preview** — run `cleanup.ps1 -RgName <rg>` (no `-AutoApprove`) to list all resources in the RG. Note: the listing shows every resource in the RG (including shared infra); T2-scoped resources must be identified manually from the list. A dedicated T2-only teardown script does not yet exist. Tank must author, validate (with `az resource delete --dry-run` per resource), and present that script for Jose review before DELETE APPROVED is given. See the cleanup plan for the expected deletion scope.
3. **Explicit confirmation** — Jose states **"DELETE APPROVED"** in the squad conversation after reviewing steps 1–2.

**T2 deletion scope (do not delete shared Foundry infra):**

`conn-foundry-to-onprem`, `conn-onprem-to-foundry`, `vpngw-foundry`, `vpngw-onprem`, `pip-vpngw-foundry`, `pip-vpngw-onprem`, `vm-onprem-echo` (+ NIC + disk), `vm-onprem-ctrl` (+ NIC + disk), `nsg-echo-vms`, `vnet-onprem`, plus NSG rules for `172.30.100.0/24` and `10.200.100.0/24` in `nsg-agentsubnet`. Gross savings: **~$11.04/day**.

**Not deleted:** `vm-diag`, `vnet-foundry` (all subnets incl. empty `GatewaySubnet`), private endpoints (x5), private DNS zones (x6), Foundry account/project, AI Search, Cosmos DB, Storage, DNS Private Resolver.

### Gate B — T1 Deployment (billable additions)

**Status: not yet authorized. T1 resources do not exist.**

Jose states **"DEPLOY APPROVED"** in the squad conversation after reviewing the cost table below.

| New resource | SKU / notes | Daily cost |
|---|---|---|
| vnet-tools + subnets + peering | — | $0 |
| vm-tools-echo + vm-tools-ctrl (B2ts_v2) | Ubuntu 22.04 | $0.36 |
| DNS Private Resolver (if not yet deployed) | 2 endpoints | $3.36 |
| DNS forwarding ruleset + VNet link | — | $0 |
| Hosted agent `echo-probe-agent` (source-ZIP) | per-session | ~$0.10–0.50/session |
| **T1 incremental total (with resolver)** | | **~$3.72 + sessions/day** |

Deployment follows Wave 0–7 in `manifest.md §7`. Tank runs validate + what-if first; Jose reviews the what-if output; final apply only after "DEPLOY APPROVED" is on record.

### Cost states

| Gates cleared | Running cost |
|---|---|
| Neither | ~$18.63/day (current) |
| B only (T1 added, T2 still running) | ~$18.99/day |
| A only (T2 gone, T1 not yet deployed) | ~$7.59/day (Foundry infra only) |
| Both (T2 gone, T1 active) | **~$7.59/day** |

---

## 15. Empirical Results (2026-08-21)

**Status: Gate B executed (DEPLOY APPROVED granted 2026-08-20T12:26Z). T1 fully deployed. Lab scenarios completed.**

### Hypothesis outcomes

| Hypothesis | Claim | Empirical result |
|------------|-------|-----------------|
| H1 (tool call path) | Prompt and hosted tool calls share same source IP range | **BASELINE ONLY** — prior lab (sibling, 2026-08-14) shows data proxy src_ip in 192.168.0.0/24. Hosted agent `requests.get` also from 192.168.0.0/24. Same /24 subnet pool used by both. H1 not re-run in this lab; no raw data-proxy invocation record here (SDK path is client-side FC). |
| H2 (direct code egress) | Hosted agent Python code uses Micro VM NIC; src_ip distinct from data proxy | CONFIRMED — direct egress via Micro VM NIC. src_ips observed: 192.168.0.238, .28, .110 (runs 1-3; change per invocation). Prior data proxy values were .49, .239 — different values, same /24 pool. |
| H3 (DNS context transparent) | DNS query src at dnsmasq is outbound EP IP regardless of caller type | CONFIRMED — all queries arrive at dnsmasq from 192.168.3.21–25 (DNSOutboundSubnet SNAT range) whether caller is Micro VM NIC or vm-diag (MgmtSubnet). Chain is context-transparent by design. |

### Key nuance on H2

Both Micro VM NIC and data proxy draw IP addresses from the same `192.168.0.0/24` (AgentSubnet) pool.
An application-layer `src_ip` value alone cannot reliably distinguish the two paths: the value changes
dynamically per invocation (new container or replica), and the ranges overlap. The distinction between
P3 (Micro VM NIC) and P1 (data proxy) is confirmed by the execution mechanism, not by IP value stability.

### Packet path P3 — empirically confirmed

| Step | Observed |
|------|---------|
| DNS: Micro VM queries `echo.tools.lab` | → DNSOutboundSubnet (192.168.3.x) → dnsmasq → A 10.1.100.4 |
| TCP: Micro VM NIC to 10.1.100.4:80 | src_ip 192.168.0.x (AgentSubnet); HTTP 200 received |
| DNS: Micro VM queries `ctrl.tools.lab` | → same chain → A 10.1.200.4 |
| TCP: Micro VM NIC to 10.1.200.4:80 | src_ip 192.168.0.x (AgentSubnet); HTTP 200 received |
| NSG negative (deny AgentSubnet on nsg-tools) | DNS queries still arrived at dnsmasq (DNSOutboundSubnet not blocked); HTTP blocked → "Function failed." |

### Infrastructure discovery

During testing, `nsg-echo-vms` was identified as the NSG from the **prior lab** (`foundry-agent-reserved-prefix-reachability`), associated with VNET-ONPREM subnets. The active NSG for vnet-tools subnets is `nsg-tools`. This naming collision is a residual from the sibling lab's resource naming.

### Foundry endpoint DNS split-horizon (confirmed from vm-diag)

From MgmtSubnet (192.168.2.4): `<account>.services.ai.azure.com` resolves to **192.168.1.10** (PESubnet private endpoint IP), not the public endpoint. Azure Private DNS zone `privatelink.services.ai.azure.com` linked to vnet-foundry is working correctly.

### Evidence files

| File | Contents |
|------|---------|
| `raw-output/hosted-agent-invoke-evidence-20260821.json` | 4 invocations (3 success + 1 NSG negative); tool outputs, src_ips, timings |
| `raw-output/dnsmasq-query-log-20260821.txt` | Full annotated dnsmasq log; queries from 192.168.3.21–25 across all invocations |
| `raw-output/vm-diag-hs5-connectivity-20260821.txt` | vm-diag HTTP 200 to echo+ctrl; Foundry DNS → PE IP |
| `raw-output/test-matrix-results-20260821.md` | HS1–HS5 + NSG negative pass/fail table |

---

## 16. Programmatic SDK Invocation Results (2026-08-21)

**Invocation API discovery:** `azure-ai-projects 2.3.0` is the primary external-caller SDK for **both** invocation paths. `AgentsOperations` manages hosted agent lifecycle only (no Assistants API / threads / runs in this version).

### Invocation path comparison

| Path | SDK call | endpoint base_url | Tool egress | src_ip |
|------|----------|-------------------|-------------|--------|
| Hosted agent (Responses, stateless) | `AIProjectClient.get_openai_client(agent_name=...).responses.create(...)` | `<endpoint>/agents/<name>/endpoint/protocols/openai` | Micro VM NIC (AgentSubnet) | 192.168.0.x (ephemeral per call) |
| Hosted agent (REST SSE stream) | `requests.post(..., stream=True)` | same endpoint | Micro VM NIC (AgentSubnet) | 192.168.0.x |
| Hosted agent (Sessions, stateful) | `client.agents.create_session(agent_name, version_indicator=VersionRefIndicator("1"))` | `<endpoint>/agents/<name>/endpoint/sessions` | Persistent Micro VM NIC (hypothesis: stable IP per session) | Not tested live |
| Standard endpoint, client-side FC | `AIProjectClient.get_openai_client().responses.create(model=..., tools=[fn...])` | `<endpoint>/openai/v1/` | CALLER (workstation) | DNS FAIL from workstation |
| Foundry portal prompt agent (data proxy) | N/A — not creatable programmatically via this SDK | `<endpoint>/openai/v1/` | Foundry data proxy (AgentSubnet) | 192.168.0.x (prior evidence) |

### SDK invocation results (sanitized)

| Run | Method | echo src_ip | ctrl src_ip | echo server_ip | Latency (s) |
|-----|--------|-------------|-------------|----------------|-------------|
| REST 1 (prior) | Direct REST | 192.168.0.238 | 192.168.0.238 | 10.1.100.4 | ~38 |
| REST 2 (prior) | Direct REST | 192.168.0.28 | 192.168.0.28 | 10.1.100.4 | ~53 |
| REST 3 (prior) | Direct REST | 192.168.0.110 | 192.168.0.110 | 10.1.100.4 | ~59 |
| SDK 1 | `get_openai_client(agent_name=...)` | 192.168.0.92 | 192.168.0.92 | 10.1.100.4 | 123.56 |
| SDK 2 | `get_openai_client(agent_name=...)` | 192.168.0.142 | 192.168.0.142 | 10.1.100.4 | 36.86 |
| SDK 3 | `get_openai_client(agent_name=...)` | 192.168.0.165 | 192.168.0.165 | 10.1.100.4 | 51.27 |
| SSE stream | REST SSE, 213 events | 192.168.0.124 | 192.168.0.124 | 10.1.100.4 | 40.50 |
| Client-FC | `get_openai_client()` + client tools | DNS FAIL | DNS FAIL | N/A | 12.67 |

**echo src_ip = ctrl src_ip** in every invocation — both probes execute in the same Micro VM instance within a single invocation (observed timestamps 5ms apart). IP changes per invocation (ephemeral Micro VM allocation).

### MAF (Microsoft Agent Framework) architecture

`agent_framework_openai 1.12.0` is the **internal server-side runtime** that runs inside the Micro VM and processes function calls (`FunctionTool`, `probe_echo`, `probe_ctrl`). External callers do **NOT** import MAF; they use `AIProjectClient.get_openai_client(agent_name=...)` which speaks the OpenAI Responses protocol to the hosted agent endpoint. MAF wraps the same Responses API on the server side, so external caller behavior is indistinguishable between using MAF directly (internal) and `AIProjectClient` (external).

### Client-side function calling: key network isolation finding

`tools.lab` DNS resolves **only inside the VNet** via the DNS Private Resolver + dnsmasq chain. Client-side function calling from the workstation fails at DNS resolution (`[Errno 11001] getaddrinfo failed`). This empirically proves:
- Hosted agents (Micro VM NIC inside AgentSubnet) **can** access private VNet-only targets.
- External callers using client-side FC **cannot** reach those targets without VNet connectivity.
- The Foundry data proxy (inside vnet-foundry, peered to vnet-tools) also has access — but cannot be created programmatically via `azure-ai-projects 2.3.0`.

### Sessions API (documented, not tested live)

`client.agents.create_session(agent_name, version_indicator=VersionRefIndicator("1"))` creates a persistent compute sandbox. Sessions may allow reuse of the same Micro VM NIC IP across multiple interactions (vs ephemeral IP per Responses call). Cost: sessions keep a Micro VM running until stopped/expired (30-day TTL). Always call `stop_session()` after use. The session-to-Responses binding mechanism (how a session_id is passed to the Responses endpoint) is not exposed via `get_openai_client()` and requires further investigation.

### Test scripts

`tests/probe_network.py` contains all SDK invocation paths:
- `probe_hosted_sdk()` — `get_openai_client(agent_name=...)` + `oai.responses.create()`
- `probe_hosted_rest()` — direct REST + SSE streaming
- `probe_hosted_sessions()` — sessions API documentation function; **not exposed by any CLI flag** (`--hosted`, `--client-fc`, `--stream`) and **not live-tested** (stateful session keeps a Micro VM running; cost concern; deferred)
- `probe_client_side_fc()` — `get_openai_client()` [no agent_name] + client-side tools

---

## 17. Consolidated Prompt-Agent vs Hosted-Agent vs Client-FC Comparison

Evidence-linked table covering both ingress (how callers reach the agent) and egress
(how the agent/tool reaches private targets). Each row is marked `Same`, `Different`,
or `Not tested/predicted`. Ingress rows distinguish caller→agent from agent/tool→private-target.

> For definitions of terms used here (data proxy, Micro VM NIC, AgentSubnet injection, etc.) and
> a concise explanation of all four packet/control paths, see the
> **[Foundry Networking Architecture Primer](README.md#foundry-networking-architecture-primer)**
> in README.md. That section is the recommended starting point for readers new to Foundry networking.

> **Provenance note (H1 / data-proxy rows):** The prompt-agent data-proxy path was observed in the
> sibling lab (2026-08-14, runs S3/S4) and is not a re-run from this lab. The SDK-created
> `client-side FC` path is a control experiment that executes on the caller, not via the data proxy.
> These two paths are architecturally distinct; the SDK path does not replicate or re-confirm the
> data-proxy path.

### Ingress: Caller → Agent endpoint

| Dimension | Prompt agent | Hosted agent | Client-side FC | Same/Different | Evidence / Provenance |
|-----------|-------------|-------------|---------------|----------------|----------------------|
| Caller endpoint URL shape | `<endpoint>/openai/v1/threads` (Assistants API; **documented, not observed in this lab** — [Foundry Threads REST ref](https://learn.microsoft.com/rest/api/microsoft-foundry/azureopenai/threads)) | `<endpoint>/agents/<name>/endpoint/protocols/openai/responses` (Responses API; observed — probe-network-sdk-evidence-20260821.md) | `<endpoint>/openai/v1/` (standard OpenAI endpoint; observed — probe-network-sdk-evidence-20260821.md) | **Different** | design.md §16; probe-network-sdk-evidence-20260821.md |
| DNS resolution (public path) | Public DNS: `<account>.services.ai.azure.com` → public IP | Same public endpoint | Same | Same | endpoint-reachability-doctor-analysis-20260821.md |
| DNS resolution (private path) | Private DNS zone `privatelink.services.ai.azure.com` → PE IP (`192.168.1.10`) | Same PE (shared Foundry account) | Same | Same | vm-diag-hs5-connectivity-20260821.txt; design.md §8 P5 |
| RBAC for invocation | Foundry data-plane role (not managed by this lab; pre-existing) | **Foundry Agent Consumer** at project scope | Standard Foundry project reader role | **Different (hosted agent requires Agent Consumer)** | hosted-agent-vscode.md §15; design.md §9 |
| Invocation protocol | Assistants API (threads/runs) | OpenAI Responses API (`POST /responses`) | OpenAI Chat Completions / Responses (`POST /openai/v1/`) | **Different** | design.md §16; probe_network.py docstring |
| Private-endpoint requirement | Required if public access disabled | Same shared PE | Same shared PE | Same | design.md §8 P5 |

### Ingress: Agent / tool → private target (tool call path)

| Dimension | Prompt-agent data proxy (HS1) | Hosted-agent Micro VM NIC (HS2/HS3) | Client-side FC (workstation) | Same/Different | Evidence / Provenance |
|-----------|------------------------------|--------------------------------------|------------------------------|----------------|----------------------|
| Tool call URL shape | `http://echo.tools.lab/api/echo` (FQDN, HTTP) | Same FQDN | Same FQDN (but DNS fails outside VNet) | Same | hosted-agent-invoke-evidence-20260821.json (run 1-3); design.md §5 |
| Target DNS resolver | DNS Private Resolver outbound EP → dnsmasq on `10.1.100.4:53` | Same chain | **FAILS** from workstation (DNS not reachable outside VNet) | **Different (client-FC fails)** | probe-network-sdk-evidence-20260821.md; dnsmasq-query-log-20260821.txt |
| DNS query source at dnsmasq | `192.168.3.21–25` (DNSOutboundSubnet SNAT pool) | Same pool (SNAT hides originating NIC) | N/A (fails before dnsmasq) | Same (prompt vs hosted) / Different (vs client-FC) | dnsmasq-query-log-20260821.txt; design.md §4 |
| Egress source IP (TCP src at target) | `192.168.0.49`, `.239` (AgentSubnet; 2026-08-14 baseline) | `192.168.0.238`, `.28`, `.110` (AgentSubnet; this lab runs 1-3) | N/A (DNS failure from workstation) | **Same /24 pool; different values** — OQ1 unresolved (SNAT or distinct role) | hosted-agent-invoke-evidence-20260821.json; probe-network-sdk-evidence-20260821.md |
| NSG enforcement on target side | `nsg-tools` (EchoSubnet/CtrlSubnet) blocks or allows `192.168.0.0/24` for both | Same NSG applies equally | N/A | Same | HS-NSG-NEG: NSG deny blocked both agent types equally; test-matrix-results-20260821.md |
| VNet peering required | Yes — vnet-foundry ↔ vnet-tools bidirectional peering | Same peering | N/A | Same (prompt vs hosted) | design.md §3 |
| Target DNS resolver SNAT source | `192.168.3.21–25` (observed at dnsmasq; SNAT pool from DNSOutboundSubnet /28) | Same | N/A | Same | dnsmasq-query-log-20260821.txt |
| Data proxy vs Micro VM NIC | **Data proxy** (shared, inside AgentSubnet; Microsoft-managed) | **Micro VM NIC** (dedicated per session; ephemeral; also inside AgentSubnet) | **Caller NIC** (outside VNet) | **Different (mechanism)** | design.md §8 P1/P3; hosted-agent-vscode.md §2 |

### Egress: Deployment-time vs runtime

| Dimension | Prompt agent | Hosted agent | Client-side FC | Same/Different | Evidence / Provenance |
|-----------|-------------|-------------|---------------|----------------|----------------------|
| Deployment-time egress | None (config-only) | AgentSubnet → `mcr.microsoft.com` (base image pull) + `*.login.microsoft.com` (auth) | None | **Different (hosted agent only)** | design.md §2 C1; hosted-agent-vscode.md §11 |
| Runtime egress path | Data proxy → vnet-tools (tool calls only) | Micro VM NIC → vnet-tools (direct code); data proxy → vnet-tools (Toolbox path; **Not tested/predicted**) | Caller → internet or VNet (if caller is inside VNet) | **Different** | design.md §8 P1/P2/P3 |
| Toolbox/OpenAPI data-proxy path from hosted agent (Approach B) | N/A | **Not tested/predicted** — SDK toolbox creation was not implemented in this lab; OQ1 design uncertainty | N/A | Not tested/predicted | hosted-agent-vscode.md §14; OQ1 |
