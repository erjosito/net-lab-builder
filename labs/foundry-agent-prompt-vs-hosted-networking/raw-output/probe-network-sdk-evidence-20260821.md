# SDK Invocation Test Evidence -- 20260821

## Overview
Programmatic invocation tests using azure-ai-projects 2.3.0 AIProjectClient.
Run from: workstation (outside VNet).
VMs running: vm-tools-echo (10.1.100.4), vm-tools-ctrl (10.1.200.4).
Agent: echo-probe-agent:1 (ACTIVE).

## Key SDK Finding
azure-ai-projects 2.3.0 AgentsOperations is for HOSTED AGENT LIFECYCLE ONLY.
Methods: create_version(), create_session(), enable(), disable(), list_versions().
NO create_agent()/threads/runs (Assistants API) in this SDK.
Foundry portal prompt agents with HTTP connections CANNOT be created programmatically.

The "prompt agent data proxy" path (HS1) observed during UI testing requires:
  - Foundry portal agent with HTTP Connection resource, OR
  - Older azure-ai-agents package (Assistants API style), which is not present in this venv.
Prior data proxy evidence (2026-08-14): src_ip=192.168.0.49, 192.168.0.239.

## Test Results

### Hosted Agent SDK Path (HS2/HS3)
Method: AIProjectClient.get_openai_client(agent_name="echo-probe-agent")
Base URL: <endpoint>/agents/echo-probe-agent/endpoint/protocols/openai
Auth: AIProjectClient managed (azure-identity, ai.azure.com scope)

Run 1 (20260821T114123Z):
  latency_s: 123.56
  echo src_ip: 192.168.0.92  (Micro VM NIC, AgentSubnet)
  ctrl src_ip: 192.168.0.92  (same Micro VM, same invocation)
  echo server_ip: 10.1.100.4 (vm-tools-echo NIC -- correct)
  ctrl server_ip: 10.1.200.4 (vm-tools-ctrl NIC -- correct)
  STATUS: PASS

Run 2 (20260821T115611Z):
  latency_s: 36.86
  echo src_ip: 192.168.0.142  (different ephemeral Micro VM NIC)
  ctrl src_ip: 192.168.0.142  (same VM, same invocation)
  echo server_ip: 10.1.100.4
  STATUS: PASS

Key: src_ip changes per invocation (ephemeral Micro VM NIC allocation):
  Prior REST calls (runs 1-3): 192.168.0.238, 192.168.0.28, 192.168.0.110
  SDK calls: 192.168.0.92, 192.168.0.142
  All in 192.168.0.0/24 (AgentSubnet)

### Client-Side Function Calling (Control Path)
Method: AIProjectClient.get_openai_client() [no agent_name] -> /openai/v1/
Model: gpt-5-mini (standard Foundry OpenAI endpoint)

Run (20260821T115321Z):
  latency_s: 12.67 (model returned tool calls; connection attempted client-side)
  tool_calls_requested_by_model: ['probe_echo', 'probe_ctrl']
  connection_failures:
    probe_echo: ConnectionError -- Failed to resolve 'echo.tools.lab' ([Errno 11001] getaddrinfo failed)
    probe_ctrl: ConnectionError -- Failed to resolve 'ctrl.tools.lab' ([Errno 11001] getaddrinfo failed)
  STATUS: EXPECTED FAIL (DNS not reachable outside VNet)

Finding: Client-side function calling from workstation CANNOT reach tools.lab.
DNS Private Resolver + dnsmasq chain resolves only inside the VNet.
This proves: hosted agent (Micro VM NIC inside AgentSubnet) is REQUIRED for
accessing private VNet-only targets. Client-side FC is a different egress path entirely.

## Hypothesis Assessment

H2 (Micro VM NIC direct egress):
  STATUS: CONFIRMED (2x SDK invocations, src_ip from AgentSubnet 192.168.0.0/24)
  Key: src_ip is ephemeral per invocation; both echo and ctrl probes use same Micro VM in one run.

H3 (DNS context transparent):
  STATUS: CONFIRMED (from prior dnsmasq log evidence; DNS queries from DNSOutboundSubnet 192.168.3.21-25)
  New: SDK-invoked runs show same resolution behavior as REST-invoked runs.

Client-FC vs Hosted-Agent comparison:
  Hosted agent: tools.lab REACHABLE (Micro VM inside VNet) -- src_ip 192.168.0.0/24
  Client-FC:    tools.lab NOT REACHABLE (workstation DNS failure) -- proves VNet isolation

## Auth Note
AzureCliCredential intermittently fails during long invocations (~120s) due to CLI process
timeout when run in concurrent/parallel context. Run hosted agent tests sequentially to avoid.
Token from prior successful call is cached by azure-identity; quick re-invocations succeed.

## MAF vs External Caller
  agent_framework_openai 1.12.0 = Microsoft Agent Framework (MAF) -- INTERNAL server-side runtime
  azure-ai-agentserver-responses 1.0.0b9 -- hosted agent server runtime
  These run INSIDE the Micro VM. External callers use AIProjectClient.get_openai_client().

## Files Referenced
  probe_results_from_run1: raw-output/probe-network-hosted-20260821T114123.json
  probe_results_from_run2: raw-output/probe-network-hosted2-20260821T115611.json
  full_comparison_run:     raw-output/probe-network-full-20260821T115321.json