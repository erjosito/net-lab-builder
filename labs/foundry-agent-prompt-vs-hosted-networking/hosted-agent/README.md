# echo-probe-agent — Hosted Agent

A Microsoft Foundry hosted agent that directly probes `echo.tools.lab` and `ctrl.tools.lab`
from the Micro VM NIC in AgentSubnet. Part of the **foundry-agent-prompt-vs-hosted-networking**
lab (scenarios HS2 and HS3).

The agent registers two Agent Framework function tools (`probe_echo` and `probe_ctrl`) that
make direct HTTP calls from the Micro VM process. The source IP observed at the target VM comes
from the Micro VM NIC — not the data proxy — which is the key distinction under test (H2).

## How it works

`main.py` registers `probe_echo()` and `probe_ctrl()` as Agent Framework tools and serves them
via `ResponsesHostServer` on port 8088. When asked to probe, the LLM calls both tools, then
returns each target's `label`, `server_ip`, `src_ip`, and `request_url` from the JSON response.

See `AGENTS.md` for the full development workflow and deployment gate conditions.

## Environment setup

```bash
cd src/echo-probe-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # then fill in FOUNDRY_PROJECT_ENDPOINT and model name
```

## F5 local debug (VS Code Foundry Toolkit)

Open `hosted-agent/` as the workspace root, then press **F5**. The agent starts on port 8088
and Agent Inspector opens automatically. The `probe_echo` / `probe_ctrl` tool calls will fail
with a DNS error locally — this is expected and confirms the code path is correct before lab
network connectivity is established.

## Deploy to Foundry

> **Gate required.** All conditions in `hosted-agent-vscode.md §11` must be met first,
> including T1 infrastructure deployed, MCR/AAD egress open, and Jose's explicit approval.

```bash
# From the hosted-agent/ directory (workspace root):
azd deploy
# Do NOT run `azd provision` — the model deployment already exists.
```

> **First-time binding on a new machine:** `azd deploy` requires both Foundry-specific vars **and**
> the standard azd subscription/location vars in the azd environment layer (not just in
> `src/echo-probe-agent/.env`). If `azd deploy` returns "infrastructure has not been provisioned"
> or `azd ai agent doctor` shows failures, run once:
> ```bash
> # Foundry project binding
> azd env set FOUNDRY_PROJECT_ENDPOINT <value-from-src/echo-probe-agent/.env>
> azd env set AZURE_AI_PROJECT_ID /subscriptions/<subscription-id>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>
>
> # Standard azd subscription context (required by azd deploy even without azd provision)
> azd env set AZURE_SUBSCRIPTION_ID $(az account show --query id -o tsv)
> azd env set AZURE_TENANT_ID $(az account show --query tenantId -o tsv)
> azd env set AZURE_RESOURCE_GROUP <rg-foundry>
> azd env set AZURE_LOCATION swedencentral
>
> # Foundry account + project name (used by azure.ai.projects extension predeploy hook)
> azd env set AZURE_AI_ACCOUNT_NAME <account>
> azd env set AZURE_AI_PROJECT_NAME <project>
>
> azd ai agent doctor   # remote checks require lab network / VPN
> ```
> Do **not** run `azd provision` -- this will try to create a new Foundry project.

Or via VS Code: **Foundry Toolkit: Deploy Hosted Agent** → Code (source-ZIP) → `echo-probe-agent`.

## Invoke after deployment

```bash
azd ai agent invoke "probe both echo endpoints and return the results"
```

## Lab reference

- Design + hypotheses: `../design.md`
- VS Code guide: `../hosted-agent-vscode.md`
- Parent manifest: `../manifest.md`