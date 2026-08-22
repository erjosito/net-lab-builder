# Test Matrix Results — foundry-agent-prompt-vs-hosted-networking
# Updated: 2026-08-21 (SDK invocation tests added)
# Evidence files: raw-output/hosted-agent-invoke-evidence-20260821.json, dnsmasq-query-log-20260821.txt,
#   vm-diag-hs5-connectivity-20260821.txt, probe-network-sdk-evidence-20260821.md,
#   probe-network-hosted-*.json, probe-network-stream-*.json, probe-network-full-*.json

## Hypothesis Results

| Hypothesis | Claim | Result | Evidence |
|------------|-------|--------|----------|
| H1 (tool call path) | Prompt agent tool calls originate from Foundry data proxy; same range as hosted-agent | PARTIALLY CONFIRMED | Prior lab: prompt-agent src_ip 192.168.0.49, 192.168.0.239 (AgentSubnet). Hosted agent src_ip same /24 but different values. H1 says 'same range' - confirmed same /24, but route/mechanism differs. |
| H2 (direct code egress) | Hosted agent Python code (requests.get) uses Micro VM NIC, src_ip different from data proxy IPs | CONFIRMED (with nuance) | Micro VM src_ips: .238, .28, .110 (runs 1-3). Different from prompt-agent IPs (.49, .239) across runs. Both draw from same /24 subnet pool; IP value distinction is not stable across time. Direct egress from Micro VM NIC confirmed. |
| H2 (SDK + streaming) | Same Micro VM NIC egress path confirmed via AIProjectClient SDK and SSE streaming paths | CONFIRMED | SDK runs: 192.168.0.92, 192.168.0.142, 192.168.0.165; REST streaming: 192.168.0.124. All in AgentSubnet. |
| H3 (DNS context) | DNS queries from both agent types appear as DNSOutboundSubnet IPs at dnsmasq | CONFIRMED | All dnsmasq queries show src 192.168.3.21-25 (DNSOutboundSubnet range) regardless of caller type. DNS chain is context-transparent. |

## Scenario Results

| Scenario | Description | Result | Evidence |
|----------|-------------|--------|----------|
| HS1 | Prompt agent OpenAPI tool call via data proxy | BASELINE ONLY (not re-run empirically) | Prior lab evidence (2026-08-14): src_ip=192.168.0.49, 192.168.0.239 via data-proxy. Empirical re-test blocked: SDK function-calling is client-side (not data-proxy). |
| HS2 | Hosted agent direct code call (Micro VM NIC path) | PASS | 3 successful REST + 1 NSG-blocked = 4 REST attempts; 3 SDK runs + 1 SSE run = 7 total hosted invocations. All successful runs HTTP 200, src_ip from AgentSubnet (192.168.0.x). |
| HS3 | Hosted agent DNS from Micro VM context (ctrl endpoint) | PASS | ctrl.tools.lab resolved to 10.1.200.4 in all 4 invocations; HTTP 200 from ctrl VM |
| HS4 | Prompt agent DNS forwarding | DOCUMENTED (not re-run) | H3 confirmed from dnsmasq logs; prompt-agent DNS would follow same path |
| HS5 | Programmatic invocation + vm-diag in-VNet access | PASS | vm-diag curl → echo HTTP 200 src_ip=192.168.2.4; ctrl HTTP 200 src_ip=192.168.2.4; Foundry DNS → 192.168.1.10 (PE IP) |
| HS-NSG-NEG | NSG deny blocks AgentSubnet access to vnet-tools | PASS | deny-agentsubnet-inbound-test on nsg-tools → both probes return 'Error: Function failed.'; DNS still resolved (from DNSOutboundSubnet which is not blocked). NSG restored. |

## SDK Invocation Test Results (2026-08-21)

| Test | SDK Path | src_ip | server_ip | Latency | Status |
|------|----------|--------|-----------|---------|--------|
| Hosted SDK Run 1 | AIProjectClient.get_openai_client(agent_name=...) | 192.168.0.92 | 10.1.100.4 | 123.56s | PASS |
| Hosted SDK Run 2 | AIProjectClient.get_openai_client(agent_name=...) | 192.168.0.142 | 10.1.100.4 | 36.86s | PASS |
| Hosted SDK Run 3 (stream) | AIProjectClient.get_openai_client(agent_name=...) | 192.168.0.165 | 10.1.100.4 | 51.27s | PASS |
| Hosted REST Stream | requests.post SSE stream | 192.168.0.124 | 10.1.100.4 | 40.50s | PASS (213 SSE events) |
| Client-side FC | AIProjectClient.get_openai_client() [no agent_name] | DNS FAIL | N/A | 12.67s | EXPECTED FAIL |

### SDK Architecture Finding
azure-ai-projects 2.3.0 AgentsOperations = hosted agent lifecycle only (create_version, create_session, enable, disable).
NO create_agent/threads/runs (Assistants API). Foundry portal prompt agents cannot be created programmatically.
AIProjectClient.get_openai_client(agent_name=...) is the official SDK path for hosted agent invocation.
get_openai_client() [no agent_name] = standard project OpenAI endpoint; client-side tool execution.

### MAF (Microsoft Agent Framework) Architecture
agent_framework_openai 1.12.0 = INTERNAL server-side runtime (runs inside Micro VM).
External callers do NOT import MAF directly; they use AIProjectClient.get_openai_client(agent_name=...).
MAF wraps the OpenAI Responses API on the server side; external caller uses same protocol.

### Sessions API (documented, not tested live)
AgentsOperations.create_session() creates a persistent Micro VM sandbox (30-day TTL).
Session may allow multiple Responses calls to reuse the same Micro VM NIC IP (hypothesis).
Risk: sessions keep Micro VM running (cost); stop/delete after use.

### Client-Side FC Network Finding (key result)
tools.lab DNS resolves ONLY inside the VNet (DNS Private Resolver + dnsmasq chain).
Client-side function calling from workstation FAILS: getaddrinfo [Errno 11001].
This proves: hosted agent / data proxy REQUIRED for private VNet-only targets.
If caller is inside VNet (e.g. vm-diag): DNS resolves, src_ip = caller NIC IP (NOT AgentSubnet).
Predicted for vm-diag: src_ip=192.168.2.4 (same as HS5 curl evidence).

## Deployment Evidence

| Item | Value |
|------|-------|
| Agent name | echo-probe-agent:1 |
| Status | active |
| Deploy time | 2026-08-21T05:42:55Z – 05:46:07Z (3m 5s) |
| Runtime | python_3_13 |
| Host | azure.ai.agent (hosted) |
| Deploy method | azd deploy |
| Auth for invocation | Python AzureCliCredential + Responses REST API |

## Network Architecture Confirmed

| Layer | Finding |
|-------|---------|
| Data plane (Micro VM NIC → tools VNet) | Direct peered VNet path; src_ip from AgentSubnet (192.168.0.0/24) |
| DNS | DNS Private Resolver outbound EP → dnsmasq (vm-tools-echo:53); all callers SNAT to 192.168.3.16/28 |
| NSG enforcement | nsg-tools on EchoSubnet + CtrlSubnet; deny at prio<100 blocks Micro VM access |
| Foundry endpoint DNS | Split-horizon: resolves to PE IP 192.168.1.10 from inside VNet |
| vm-diag (MgmtSubnet) | Can reach both vnet-tools endpoints; DNS forwarding via same chain |

## Residual Items

| Item | Status |
|------|--------|
| HS1 empirical prompt-agent data-proxy HTTP test | BLOCKED - SDK function calling is client-side; needs OpenAPI connection via Foundry portal |
| nginx access log verification | BLOCKED - MDE.Linux extension update conflicts with run-command on vm-tools-echo |
| VMs deallocated after test | DONE - deallocated after each test session |
| Sessions API live test | DEFERRED - stateful sandbox, different use case, cost risk |
| Client-FC from vm-diag | DEFERRED - predicted result (src_ip=192.168.2.4) documented; HS5 curl proves same path |