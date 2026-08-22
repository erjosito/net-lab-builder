# Network Probe Tests -- Prompt Agent vs Hosted Agent

Programmatic invocation comparison scripts for the `foundry-agent-prompt-vs-hosted-networking` lab.

## Purpose

These tests empirically compare network egress paths using the officially supported
`azure-ai-projects 2.3.0` SDK (`AIProjectClient`) for both invocation scenarios.

| Test | SDK Path | Tool Egress | Expected src_ip |
|---|---|---|---|
| **Hosted agent** (HS2/HS3) | `AIProjectClient.get_openai_client(agent_name=...)` | Micro VM NIC (AgentSubnet 192.168.0.x) | 192.168.0.x (VNet-internal) |
| **Client-side FC** (control) | `AIProjectClient.get_openai_client()` [no agent_name] | Caller workstation | Workstation/caller IP OR connection failure |

## Key SDK Finding

`azure-ai-projects 2.3.0` `AgentsOperations` is for **hosted agent lifecycle only**:
`create_version()`, `create_session()`, `enable()`, `disable()`, `list_versions()`.

**There is NO `create_agent()`/threads/runs (Assistants API) in this SDK.**
Foundry portal prompt agents with HTTP connections cannot be created programmatically here.

The Foundry data proxy path (observed in prior UI testing: src_ip 192.168.0.49, 192.168.0.239)
requires a Foundry portal-configured agent with HTTP Connection resources.
The client-side FC path in this script calls the standard Foundry OpenAI endpoint and
executes tool calls on the CALLER -- it does NOT use the data proxy.

## API Architecture

```
External caller (this script)
  azure-ai-projects 2.3.0
    AIProjectClient
      .get_openai_client(agent_name="echo-probe-agent")  -> /agents/<name>/endpoint/protocols/openai
                                                          -> HOSTED AGENT Responses endpoint
                                                          -> tool calls: Micro VM NIC (AgentSubnet)

      .get_openai_client()  [no agent_name]              -> /openai/v1/
                                                          -> standard Foundry OpenAI endpoint
                                                          -> tool calls: CLIENT-SIDE (caller machine)

      .agents.*                                          -> hosted agent lifecycle ONLY
                                                          -> create_version, create_session, enable...
                                                          -> NO create_agent/threads/runs

Hosted agent INTERNAL runtime (runs inside Micro VM -- NOT used by external callers):
  agent_framework_openai 1.12.0      (Microsoft Agent Framework / MAF)
  agent_framework_foundry 1.10.4
  agent_framework_foundry_hosting 1.0.0b260730
  azure-ai-agentserver-responses 1.0.0b9
```

### Why `get_openai_client(agent_name=...)` routes to the hosted agent

`azure.ai.projects._patch.get_openai_client` accepts an optional `agent_name` kwarg.
When provided (and `allow_preview=True` is set on the client), the returned `openai.OpenAI`
client has:

```
base_url = <endpoint>/agents/<agent_name>/endpoint/protocols/openai
```

Calling `oai.responses.create(model="echo-probe-agent", input=..., stream=False)` routes
to the hosted agent Responses endpoint (stateless, no threads needed).

When `agent_name` is omitted, base_url = `<endpoint>/openai/v1/` (standard project endpoint).

## Files

| File | Description |
|---|---|
| `probe_network.py` | Hosted agent SDK path + client-side FC control path comparison |

## Prerequisites

1. **vm-tools-echo** (10.1.100.4) must be **running** -- provides echo HTTP endpoint and dnsmasq DNS for `tools.lab`.
2. **vm-tools-ctrl** (10.1.200.4) must be **running** -- provides ctrl HTTP endpoint.
3. **echo-probe-agent:1** must be **active** in the Foundry project.
4. **Azure CLI** logged in (`az login`).
5. Run from the hosted-agent venv: `src/echo-probe-agent/.venv/Scripts/python.exe`.
   The venv must be Python **3.13** to match the deployed agent runtime (`python_3_13`).
   Running with system Python (e.g. 3.11 or 3.12) may cause import errors from package
   version pins in `requirements.txt`. If the venv was built with a different Python version,
   recreate it: `python3.13 -m venv .venv && pip install -r requirements.txt`.

Start VMs if deallocated:
```bash
az vm start -g <rg-foundry> -n vm-tools-echo
az vm start -g <rg-foundry> -n vm-tools-ctrl
```

Wait ~60 seconds after start for dnsmasq.

## Usage

Run from the repo root using the hosted-agent venv:

```powershell
$py = "labs\foundry-agent-prompt-vs-hosted-networking\hosted-agent\src\echo-probe-agent\.venv\Scripts\python.exe"
$tests = "labs\foundry-agent-prompt-vs-hosted-networking\tests\probe_network.py"

# Both tests (hosted agent + client-side FC)
& $py $tests

# Hosted agent only (fastest, ~40-130s)
& $py $tests --hosted

# Client-side FC only (~10-15s; expected DNS failure from workstation)
& $py $tests --client-fc

# With hosted agent streaming SSE comparison
& $py $tests --hosted --stream

# Custom output path
& $py $tests --out labs\...\raw-output\probe_results_$(Get-Date -Format yyyyMMddTHHmmss).json
```

Output is saved to `probe_results_<timestamp>Z.json` in the current directory.

## Expected Results

### Hosted agent (workstation as caller)
- `echo src_ip`: `192.168.0.x` (Micro VM NIC, AgentSubnet -- inside VNet)
- `ctrl src_ip`: same IP (same Micro VM instance per invocation)
- `echo server_ip`: `10.1.100.4` (vm-tools-echo)
- `ctrl server_ip`: `10.1.200.4` (vm-tools-ctrl)
- Latency: ~30-130s (Micro VM cold start vs warm)

### Client-side FC (workstation as caller)
- Model requests tool calls: `['probe_echo', 'probe_ctrl']`
- Connection failures: DNS resolution failure for both `echo.tools.lab` and `ctrl.tools.lab`
  - `[Errno 11001] getaddrinfo failed` (Windows) or `Name or service not known` (Linux)
- This is **expected** -- tools.lab DNS resolves only inside the VNet (DNS Private Resolver + dnsmasq)

### Client-side FC (from vm-diag inside vnet-foundry)
- Connection succeeds; src_ip = vm-diag NIC IP (192.168.2.4), NOT AgentSubnet
- Proves: client-side FC never uses the data proxy, regardless of where the caller runs

## What It Measures

| Field | Meaning |
|---|---|
| `src_ip` | Caller IP as seen by echo/ctrl server -- reveals egress path |
| `server_ip` | Server self-reported IP -- confirms correct FQDN resolved |
| `connection_failures` | DNS/connection errors -- reveals VNet isolation |
| `latency_s` | Wall-clock time from client call to parsed response |

## Hypotheses Validated

- **H2**: Hosted-agent tool calls egress from the **Micro VM NIC** (AgentSubnet 192.168.0.x).
  Client-side FC fails from workstation -- proves VNet isolation enforced by DNS design.
- **H3**: DNS resolution context transparent for hosted agents. Verified: DNS Private Resolver +
  dnsmasq chain works from AgentSubnet (192.168.0.x) regardless of invocation API used.

## Auth Notes

`AzureCliCredential` is used (not `DefaultAzureCredential`) because `az account get-access-token
--scope "https://management.azure.com/.default"` takes ~15s on this workstation, which exceeds
azd doctor's 10s gRPC timeout. `AIProjectClient` uses a different code path and is not affected.

Long invocations (~120s) may cause AzureCliCredential to fail intermittently due to CLI process
timeout in concurrent contexts. Run hosted agent tests sequentially (one at a time) to avoid.

For CI / managed identity environments:
```python
from azure.identity import DefaultAzureCredential
credential = DefaultAzureCredential()
```

## Empirical Evidence

From confirmed runs (2026-08-21):

| Run | Method | src_ip (echo) | server_ip | Latency |
|---|---|---|---|---|
| REST run 1 | Direct REST | 192.168.0.238 | 10.1.100.4 | ~38s |
| REST run 2 | Direct REST | 192.168.0.28 | 10.1.100.4 | ~53s |
| REST run 3 | Direct REST | 192.168.0.110 | 10.1.100.4 | ~59s |
| SDK run 1 | AIProjectClient SDK | 192.168.0.92 | 10.1.100.4 | 124s |
| SDK run 2 | AIProjectClient SDK | 192.168.0.142 | 10.1.100.4 | 37s |
| Client-FC | Standard endpoint + client tools | N/A (DNS fail) | N/A | 13s |

All Micro VM NIC IPs are in AgentSubnet (192.168.0.0/24) and change per invocation.