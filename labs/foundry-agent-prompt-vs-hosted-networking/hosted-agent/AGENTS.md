# Coding Agent Instructions

This workspace is the **echo-probe-agent** Microsoft Foundry hosted agent for the
`foundry-agent-prompt-vs-hosted-networking` lab. It probes `echo.tools.lab` and
`ctrl.tools.lab` directly from the Micro VM NIC (Approach A, scenario HS2/HS3) to
measure direct-code-egress source IPs in the lab VNet.

The platform handles containerization, hosting, security, scaling, and observability.

## Key files

| File | Purpose |
|------|---------|
| `src/echo-probe-agent/main.py` | Agent logic: two tool functions + ResponsesHostServer on :8088 |
| `src/echo-probe-agent/requirements.txt` | Python dependencies |
| `src/echo-probe-agent/Dockerfile` | Container definition (python:3.13-slim) |
| `src/echo-probe-agent/.env` | Local secrets — NOT committed; copy from `.env.example` |
| `src/echo-probe-agent/.env.example` | Placeholder variable names — safe to commit |
| `azure.yaml` | azd project manifest; runtime python_3_13; no model provisioning |

## Environment setup (local debugging)

```bash
cd src/echo-probe-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows
pip install -r requirements.txt
# Copy .env.example to .env and fill in your values
```

## Development workflow

```bash
# Run locally (port 8088)
azd ai agent run

# Test locally (DNS will fail — expected; confirms code path, not live network)
azd ai agent invoke --local "probe both echo endpoints"

# Deploy to Foundry (requires Gate conditions in hosted-agent-vscode.md §11)
azd deploy
# Do NOT run `azd provision` — the shared Foundry project and model deployment already exist.

# Test deployed agent
azd ai agent invoke "probe both echo endpoints"
```

## F5 debug in VS Code

1. Open the `hosted-agent/` folder as the workspace root.
2. Create and activate `.venv`, install `requirements.txt`.
3. Press **F5** — VS Code starts the agent on port 8088 and opens Agent Inspector automatically.
4. Expected local behavior: both `probe_echo()` and `probe_ctrl()` will fail with a DNS/connection
   error. This is correct — the `tools.lab` zone is only reachable inside the lab VNet.
5. Set breakpoints in `main.py` to inspect tool call arguments and responses.

## Deployment gate

Before deploying, verify ALL conditions in `hosted-agent-vscode.md §11`:
- T1 infrastructure (vnet-tools, VNet peering, DNS resolver) deployed
- MCR + AAD egress open (NSG rules 125/126 on AgentSubnet)
- Tools VM echo services responding (`10.1.100.4` and `10.1.200.4`)
- `DEPLOY APPROVED` from Jose in the squad conversation

## Constraints

- Never hard-code secrets, endpoints, project IDs, or model deployment names.
- Do not run `azd provision` — it would attempt to create a duplicate model deployment.
- Do not change Azure resources until Jose explicitly approves.
- Keep `probe_echo` and `probe_ctrl` as Agent Framework-registered tools (not inline logic)
  so the LLM can call them selectively and tool-call tracing is visible in logs.
- `requests.raise_for_status()` is required; do not swallow HTTP errors silently.

## References

- [Hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- Lab design: `../design.md` (scenarios HS2/HS3, hypotheses H2/H3)
- VS Code guide: `../hosted-agent-vscode.md`