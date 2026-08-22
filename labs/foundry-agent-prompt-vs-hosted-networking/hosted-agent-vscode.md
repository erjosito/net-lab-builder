# Hosted Agent — VS Code Hands-on Guide
**Lab:** foundry-agent-prompt-vs-hosted-networking  
**Author:** Oracle (Documentation & Diagrams)  
**Date:** 2026-08-20  
**Audience:** Jose Moreno  
**Status:** Documentation. Deployment complete (2026-08-21). Scenarios HS2/HS3/HS5 confirmed.

> **Scope:** This guide covers the VS Code Foundry Toolkit workflow for creating, debugging, and
> deploying a hosted agent. It maps directly to the lab's scenarios HS1–HS5. No executable sample
> code is provided beyond illustrative snippets required by the scaffold structure.

---

## Contents

1. [Why your existing agent is a prompt agent](#1-why-your-existing-agent-is-a-prompt-agent)
2. [What a hosted agent is — and what it is not](#2-what-a-hosted-agent-is--and-what-it-is-not)
3. [Two equivalents of your OpenAPI tools](#3-two-equivalents-of-your-openapi-tools)
4. [Prerequisites](#4-prerequisites)
5. [Step 1 — Install and sign in: VS Code Foundry Toolkit](#5-step-1--install-and-sign-in-vs-code-foundry-toolkit)
6. [Step 2 — Connect to the existing Foundry project](#6-step-2--connect-to-the-existing-foundry-project)
7. [Step 3 — Scaffold the hosted agent project](#7-step-3--scaffold-the-hosted-agent-project)
8. [Step 4 — Inspect the scaffold before editing](#8-step-4--inspect-the-scaffold-before-editing)
9. [Step 5 — Add two direct HTTP calls (echo and ctrl)](#9-step-5--add-two-direct-http-calls-echo-and-ctrl)
10. [Step 6 — Local F5 debug with Agent Inspector](#10-step-6--local-f5-debug-with-agent-inspector)
11. [⚠️ Checkpoint: before deployment](#11-%EF%B8%8F-checkpoint-before-deployment)
12. [Step 7 — Deploy to Foundry (source-ZIP, no ACR)](#12-step-7--deploy-to-foundry-source-zip-no-acr)
13. [Step 8 — Invoke and capture evidence](#13-step-8--invoke-and-capture-evidence)
14. [Advanced: OpenAPI toolbox via SDK (Approach B)](#14-advanced-openapi-toolbox-via-sdk-approach-b)
15. [Programmatic invocation from a network-connected client](#15-programmatic-invocation-from-a-network-connected-client)
16. [Troubleshooting reference](#16-troubleshooting-reference)

---

## 1. Why your existing agent is a prompt agent

Four independent sources confirm the existing agent is a **prompt agent**, not a hosted agent:

| Source | Evidence |
|--------|---------|
| `portal-foundry-setup.md` Step 8 | Explicitly instructs: "Select **Prompt agent** (NOT Hosted agent)." |
| `design.md` §10 | "For a prompt agent, the traffic path is: Client → Foundry endpoint → Tools Service → Data Proxy (in AgentSubnet)." |
| `results.md` | Tool calls invoked from Foundry chat; no container image, no `azd`, no dedicated agent endpoint URL. |
| `manifest.md` §1 scope | "Hosted agent container image" listed as OUT OF SCOPE for sibling lab. |

A prompt agent has no runtime container and no code you write — its behavior is fully declarative
(system instructions + OpenAPI tool definitions). The platform's Tools Service handles tool invocation
through the single-tenant **data proxy** in AgentSubnet.

---

## 2. What a hosted agent is — and what it is not

A hosted agent is **not** a clone of a prompt agent with a different deployment model. The
differences are architectural:

| Dimension | Prompt agent | Hosted agent |
|-----------|-------------|-------------|
| Agent logic | Declarative: instructions + tool config | Code: Python `main.py` that implements a protocol |
| Tool invocation | Platform calls your OpenAPI endpoints via data proxy | Two options (see §3) |
| Runtime | Fully managed; no container you control | Your code runs in a **Micro VM** in AgentSubnet |
| Ingress URL | Foundry project endpoint (Assistants API) | Dedicated agent endpoint (Responses protocol) |
| Portal chat | Yes — Agents Playground | No portal chat; use VS Code Playground tab or SDK |
| Local debug | Not possible | Yes — F5, breakpoints in `main.py`, Agent Inspector |
| Source IP of tool calls | Data proxy IP in `192.168.0.0/24` | Data proxy IP if using Toolbox; **Micro VM NIC IP** if calling directly from code |

The Micro VM receives a dedicated NIC in AgentSubnet. It is ephemeral (one per session) and has its
own routing context — the key question this lab tests (scenarios HS1–HS3).

---

## 3. Two equivalents of your OpenAPI tools

Your prompt agent uses OpenAPI JSON tool definitions (files in `agent-tools/`) that point to
`http://echo.tools.lab/api/echo` and `http://ctrl.tools.lab/api/echo`. A hosted agent can replicate
the network behavior of those tool calls in two ways:

### Approach A — Direct code call (lab-preferred, tests HS2)

Your Python `main.py` calls `requests.get("http://echo.tools.lab/api/echo")` directly.  
- **Source IP at target VM:** Micro VM NIC IP — different from the data proxy IPs in HS1.  
- **Why interesting:** this is the headline network difference the lab tests.  
- **Complexity:** minimal — just `import requests` and one HTTP call.

### Approach B — Foundry Toolbox with OpenAPI definition (advanced — predicted, not tested in this lab)

You would create a Foundry Toolbox via Python SDK and attach an OpenAPI tool definition pointing at
`http://echo.tools.lab`. The agent code calls the toolbox endpoint; the platform would route the actual
HTTP call through the **data proxy**.

> ⚠️ **Not implemented or tested in this lab.** Approach B was not deployed. The source IP prediction
> below is based on platform documentation, not empirical evidence from this lab. See OQ1 in
> [design.md](design.md) for the design uncertainty.

- **Source IP at target VM (predicted):** same data proxy IP range as the prompt agent's tool calls — both would use AgentSubnet `192.168.0.0/24`. Whether the exact IP value differs from the Micro VM NIC IPs is an open question (OQ1).
- **Why interesting:** would prove the data proxy path is agent-type-independent (i.e., H1 applies to hosted agents using Toolbox, not just prompt agents).
- **Complexity:** requires SDK toolbox creation and `azure.yaml` modification.
- **VS Code UI limitation:** the Foundry Toolkit VS Code UI does **not** support adding OpenAPI tools
  to a toolbox (confirmed from docs 2026-08-19). You must use the Python SDK or `azd` CLI.

**Start with Approach A.** Add Approach B after the initial deploy succeeds (see §14).

---

## 4. Prerequisites

Verify all of the following before opening VS Code:

| Item | Verification command | Expected |
|------|---------------------|---------|
| VS Code 1.90+ | `code --version` | 1.90 or later |
| Python 3.13+ | `python --version` | 3.13.x or later |
| Azure CLI authenticated | `az account show` | Your subscription + tenant |
| `azd` CLI 1.27.1+ | `azd version` | 1.27.1+ |
| `azd microsoft.foundry` extension | `azd ext show microsoft.foundry` | 1.0.0-beta.4+ |
| Foundry account and project | Portal: `ai.azure.com` → your project | swedencentral, healthy |
| Model deployment | Portal: project → Model deployments | gpt-5-mini (or fallback), deployed |
| **Foundry Project Manager** role at project scope | Portal: Project → Access control (IAM) | Assigned to your identity |

If the `azd microsoft.foundry` extension is missing:
```
azd ext install microsoft.foundry
```

> **Role note:** `Foundry Project Manager` at project scope is required to deploy a hosted agent
> from source. Subscription `Owner` or `Contributor` are ARM control-plane roles and are not
> sufficient for Foundry data-plane deployment permissions. Request the role from your subscription
> administrator if it is missing.

> **Note on ACR:** Source-ZIP deployment does **not** require Azure Container Registry. Do not create an ACR for this lab.

> **Required network egress for any hosted-agent deployment (both `remote_build` and `bundled` modes):** Outbound TCP 443 from AgentSubnet to `mcr.microsoft.com` (base container image) and `*.login.microsoft.com` (authentication) is required regardless of how Python dependencies are packaged. NSG rules 125 (`MicrosoftContainerRegistry` service tag) and 126 (`AzureActiveDirectory` service tag) must be open before deploying. The preflight check in §11 verifies this. **Switching to `bundled` mode does not remove these requirements.**

---

## 5. Step 1 — Install and sign in: VS Code Foundry Toolkit

**Jose performs this step. It cannot be automated.**

1. Open VS Code.
2. Open the Extensions panel (`Ctrl+Shift+X`).
3. Search for **`Microsoft Foundry Toolkit`**. Install it. If it is not in the stable channel,
   right-click the extension entry and select **Switch to Pre-Release Version**.  
   Direct link: <https://aka.ms/foundrytk>
4. After installation, select the **Foundry Toolkit** icon in the Activity Bar (left sidebar).
5. Sign in to Azure when prompted. Use the same identity that has `Foundry Project Manager` on the
   project. The extension uses VS Code's Azure Account extension, which feeds `DefaultAzureCredential`
   in local runs.

---

## 6. Step 2 — Connect to the existing Foundry project

**Jose performs this step. Do NOT create a new Foundry project.**

1. In the Foundry Toolkit sidebar, open the project picker.
2. Select the subscription containing the existing Foundry account (swedencentral).
3. Select the existing Foundry project (the one used in the sibling lab).
4. Verify the sidebar shows: **Hosted Agents**, **Tools**, and the gpt-5-mini model deployment.

---

## 7. Step 3 — Scaffold the hosted agent project

**Jose performs this step.**

1. Open the Command Palette (`Ctrl+Shift+P`).
2. Type and select **`Foundry Toolkit: Create new Hosted Agent`**.
3. Fill in the prompts:

   | Prompt | Value |
   |--------|-------|
   | Language | **Python** |
   | Framework | **Agent Framework** |
   | Protocol type | **Responses API** |
   | Sample code | **Basic** |
   | Folder | `labs/foundry-agent-prompt-vs-hosted-networking/hosted-agent/` |
   | Agent name | `echo-probe-agent` |
   | Environment setup | **Set up with Microsoft Foundry** |

4. Select **Create**. A new VS Code window opens with the project as the active workspace.

The scaffold creates this structure:

```
hosted-agent/
  main.py            -- Responses protocol server on port 8088
  requirements.txt   -- azure-ai-projects, agent-framework, etc.
  .env               -- FOUNDRY_PROJECT_ENDPOINT, AZURE_AI_MODEL_DEPLOYMENT_NAME
  azure.yaml         -- azd project manifest (codeConfiguration: remote_build)
```

> **Note:** The actual source layout nests the agent under `src/echo-probe-agent/`:
> `src/echo-probe-agent/main.py`, `src/echo-probe-agent/requirements.txt`.
> The scaffold may vary by toolkit version; verify the actual tree in VS Code Explorer.

---

## 8. Step 4 — Inspect the scaffold before editing

**Read before modifying.** The scaffolded `main.py`:

1. Starts a web server on port 8088 at `/responses` (the Responses protocol endpoint).
2. Handles `POST /responses` with `{"input": "...", "stream": false}`.
3. Uses Agent Framework to call the Foundry model for reasoning.
4. Returns a structured Responses-protocol response.

**Key API difference from the prompt agent:** The prompt agent is invoked at the Foundry project
endpoint (`/threads`, `/runs`). A hosted agent has its own **dedicated endpoint** (shown in VS Code
Foundry Toolkit after deployment) and is called with `POST /responses`. Callers need to discover
this endpoint after deployment.

Also inspect:
- `.env`: confirm `FOUNDRY_PROJECT_ENDPOINT` is populated from your project.
- `azure.yaml`: confirm `codeConfiguration: remote_build` is present (source-ZIP, no ACR needed).
- `requirements.txt`: note the existing packages; you will add `requests` in the next step.

---

## 9. Step 5 — Add two direct HTTP calls (echo and ctrl)

**Jose inserts the calls.** The repository stages a helper file at
`agent-tools/hosted-agent-scaffold/echo_probe_patch.py` with ready-to-use stubs. Copy the relevant
lines into `main.py`.

What to add inside the agent's response handler, **before returning**:

```python
import requests  # add to the imports section at the top

# Probe functions (register each as an Agent Framework tool):
def probe_echo() -> dict:
    resp = requests.get("http://echo.tools.lab/api/echo", timeout=(5, 10))
    resp.raise_for_status()   # raises requests.HTTPError on 4xx/5xx
    return resp.json()

def probe_ctrl() -> dict:
    resp = requests.get("http://ctrl.tools.lab/api/echo", timeout=(5, 10))
    resp.raise_for_status()
    return resp.json()
```

Also add `requests` to `requirements.txt`.

> Use `http://` (not `https://`) for the initial run. TLS hostname validation behavior with the
> lab's self-signed certs and hostname FQDNs is an open question; HTTP avoids that confounder
> until the first empirical test. Trinity will confirm whether to switch to `https://` based on
> the result of HS2.

> **Local run expectation:** The `requests.get("http://echo.tools.lab/...")` call will **fail
> locally** because your laptop has no route to `10.1.100.4` and `tools.lab` is not resolvable
> from your workstation. The call raises `requests.ConnectionError` (DNS failure). This is expected
> — the connectivity test happens only after deployment, when the Micro VM NIC gets the VNet routing
> context from AgentSubnet. Do **not** catch and swallow the exception; let it propagate so the
> agent can report the exact error to the caller.

---

## 10. Step 6 — Local F5 debug with Agent Inspector

**Jose performs this step.**

1. Create and activate a virtual environment:
   ```
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
2. Press **F5** to start the agent in debug mode. VS Code starts the Responses protocol server on
   port 8088 and opens the **Agent Inspector** automatically.
3. In the Agent Inspector, type:
   ```
   probe both echo endpoints and return the results
   ```
4. The agent calls gpt-5-mini for reasoning, then executes the probe tool calls.
   - The model reasoning appears in the Agent Inspector.
   - The HTTP calls return errors (DNS failure locally). This is expected.
5. Set a breakpoint on the `requests.get(...)` line and step through it. Inspect the exception
   message — it confirms the DNS failure is a name resolution error, not a code error.

This local run validates the agent protocol and LLM reasoning **before** touching any Azure resources.

---

## 11. ⚠️ Checkpoint: before deployment

**Stop here and verify the following before deploying:**

| Gate | Required condition | Owner |
|------|--------------------|-------|
| T1 deployed | vnet-tools, VNet peering, vm-tools-echo, vm-tools-ctrl, DNS resolver, nsg-tools all PASS in preflight | Tank/Trinity |
| Wave 5 complete | `curl http://10.1.100.4/api/echo` from vm-diag returns 200 | Jose (guided by Niobe) |
| Z2 DNS working | `nslookup echo.tools.lab` from vm-diag returns `10.1.100.4` | Jose |
| MCR + AAD egress open | `curl -sI https://mcr.microsoft.com` from AgentSubnet (via `az vm run-command invoke` on vm-diag) returns 200. **Required for all deploy modes; `bundled` does not bypass this.** NSG rules 125 + 126 must be applied if the check fails. | Tank/Trinity |
| AgentSubnet NSG patched | Rules 110/120 (outbound to 10.1.100.0/24, 10.1.200.0/24) added | Tank/Jose |
| **Jose explicit approval** | "DEPLOY APPROVED" message in squad conversation | Jose |

> **Billable action:** Deployed hosted agents incur compute charges per session. Estimated
> ~$0.10–$0.50/day depending on invocation frequency. Confirm with Azure AI Foundry pricing before
> running extended tests.

---

## 12. Step 7 — Deploy to Foundry (source-ZIP, no ACR)

**Jose performs this step. All gate conditions in §11 must be met first.**

### Via VS Code (preferred)

1. Open the Command Palette (`Ctrl+Shift+P`).
2. Select **`Foundry Toolkit: Deploy Hosted Agent`**.
3. Fill in:

   | Field | Value |
   |-------|-------|
   | Deployment method | **Code** (source-ZIP, no ACR) |
   | Package mode | **Remote** (`remote_build`) or **Bundled** — design.md §6 recommends `bundled` for this lab (only `requests` dependency; avoids transient pip failures). MCR + AAD egress is required in both cases. |
   | Agent name | `echo-probe-agent` (auto-populated) |

4. Select **Next**, review the summary, then select **Deploy**.
5. Monitor progress in the VS Code Output panel (select the `Foundry Toolkit` channel). Deployment
   takes 3–8 minutes.
6. When complete, `echo-probe-agent` appears under **Hosted Agents** in the sidebar.
   Note the dedicated agent endpoint URL.

### Via terminal (alternative)

```bash
azd ai agent init --no-prompt --project-id <your-project-id> \
    --deploy-mode code --runtime python_3_13 --entry-point main.py
azd deploy
```

> If deployment fails referencing `mcr.microsoft.com`, the AgentSubnet NSG is blocking the base
> container image pull. This affects **both** `remote_build` and `bundled` modes. Apply NSG rules
> 125 (`MicrosoftContainerRegistry`) and 126 (`AzureActiveDirectory`) — Tank has these staged —
> and retry. Switching to `bundled` will not resolve an MCR connectivity failure.

---

## 13. Step 8 — Invoke and capture evidence

**Three invocation surfaces. Run all three for complete HS2/HS5 evidence.**

### Surface 1: VS Code Playground tab (HS2 primary)

1. In the Foundry Toolkit sidebar, expand **Hosted Agents** → `echo-probe-agent`.
2. Select the **Playground** tab.
3. Send: `probe both echo endpoints and return the results`.
4. Capture the full JSON response. Look for `echo_data.src_ip` and `ctrl_data.src_ip`.
5. Compare `echo_data.src_ip` with the data proxy IPs observed in the sibling lab
   (`192.168.0.49`, `192.168.0.239`). If different, H2 is confirmed. If the same, OQ1 remains open.

### Surface 2: Terminal (`azd` CLI)

```bash
azd ai agent invoke echo-probe-agent "probe both echo endpoints"
```

### Surface 3: Python SDK from vm-diag (HS5)

Run via `az vm run-command invoke` on vm-diag:

```python
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

project = AIProjectClient(
    endpoint="https://<FOUNDRY_ACCOUNT>.services.ai.azure.com/api/projects/<PROJECT>",
    credential=DefaultAzureCredential(),
)
client = project.get_openai_client(agent_name="echo-probe-agent")
response = client.responses.create(input="probe both echo endpoints")
print(response.output_text)
```

> Replace `<FOUNDRY_ACCOUNT>` and `<PROJECT>` with your values. Do not commit these to the repo.  
> `DefaultAzureCredential` on vm-diag uses the VM's system-assigned managed identity. Verify that
> the managed identity has **Foundry Agent Consumer** at project scope before running.

**Evidence to capture for each surface:**
- `echo_data.src_ip` and `ctrl_data.src_ip` in the response payload.
- Whether `request_url` contains `echo.tools.lab` (FQDN, not a raw IP) — confirms DNS worked.
- dnsmasq log on vm-tools-echo: `sudo journalctl -u dnsmasq --since "5 minutes ago"` — check query
  source IPs from `192.168.3.21–25` (DNSOutboundSubnet SNAT pool; confirms H3 — same pool for all agent types).
- tcpdump on vm-tools-echo: `sudo tcpdump -n -i eth0 'tcp port 80 and src net 192.168.0.0/24'` — note src_ip.

---

## 14. Advanced: OpenAPI toolbox via SDK (Approach B)

This section documents how to replicate the prompt agent's **data proxy egress path** from a hosted
agent using a Foundry Toolbox. It is a follow-up to the initial HS2 run.

**VS Code UI limitation (confirmed 2026-08-19):** The Foundry Toolkit VS Code UI does **not** support
adding OpenAPI tools to a toolbox. The capability matrix in the official toolbox docs shows
`Foundry Toolkit: No` for OpenAPI tool creation. You must use the Python SDK.

### Why this matters (design intent — not yet validated)

When a hosted agent calls `requests.get(...)` directly (Approach A), the source IP is the
Micro VM NIC IP. **If** Approach B were implemented, the Toolbox call would route through the
**data proxy** — the same path as a prompt agent's OpenAPI tool call. This would allow a direct
comparison of `src_ip` at vm-tools-echo between the two paths (Approach A vs B) to empirically
confirm or refute H1 from within a single lab run. **This comparison was not performed in this lab.**
OQ1 (whether data proxy and Micro VM NIC IPs are distinguishable by value) remains open.

### Toolbox creation (Python SDK — repository stages `agent-tools/create-echo-toolbox.py`)

The repository stages a script at `agent-tools/create-echo-toolbox.py`. Jose runs it once:

```python
# Illustrative structure only — do not commit credentials or IDs
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
import json

project = AIProjectClient(
    endpoint="https://<FOUNDRY_ACCOUNT>.services.ai.azure.com/api/projects/<PROJECT>",
    credential=DefaultAzureCredential(),
)
with open("agent-tools/echo-echo-dns.openapi.json") as f:
    spec = json.load(f)

toolbox_version = project.toolboxes.create_version(
    name="echo-toolbox",
    description="Echo endpoint toolbox for prompt-vs-hosted lab",
    tools=[{
        "type": "openapi",
        "name": "echoTools",
        "spec": spec,
        "auth": {"type": "anonymous"},
    }],
)
print(f"Toolbox: {toolbox_version.name}  version: {toolbox_version.version}")
```

After creating the toolbox, reference it in `azure.yaml` (Tank prepares this addition) and add a
second call in `main.py` that uses the Toolbox SDK instead of `requests` directly. The agent code
makes a Toolbox call → platform data proxy → `echo.tools.lab`. Compare the resulting `src_ip` with
the direct `requests.get()` `src_ip` from HS2.

> **⚠️ Billable action:** Creating a toolbox version incurs Foundry data-plane charges. Verify
> pricing before running this step in a loop.

---

## 15. Programmatic invocation from a network-connected client

This section covers the private endpoint and RBAC requirements for invoking the hosted agent from
within or outside the VNet. See also [diagram 06](diagrams/06-programmatic-invocation.mmd).

### From inside vnet-foundry (vm-diag — HS5)

| Requirement | Detail |
|-------------|--------|
| DNS resolution | Private DNS zone `privatelink.services.ai.azure.com` linked to vnet-foundry. Verify: `nslookup <account>.services.ai.azure.com` from vm-diag returns a `192.168.1.x` (PESubnet) IP. |
| Network path | HTTPS to private endpoint in PESubnet. The NSG on MgmtSubnet must allow outbound TCP 443 to PESubnet. |
| RBAC | Caller identity (vm-diag managed identity) must have **Foundry Agent Consumer** at project scope. |
| Endpoint URL | Dedicated agent endpoint (not the project endpoint). Find it in VS Code Foundry Toolkit → Hosted Agents → `echo-probe-agent` → endpoint URL. |

### From Jose's workstation (public path)

This path only works if the Foundry account has public network access enabled.

| Requirement | Detail |
|-------------|--------|
| DNS resolution | Public DNS resolves `<account>.services.ai.azure.com` to a public IP. |
| RBAC | Same: **Foundry Agent Consumer** at project scope. |
| Authentication | `DefaultAzureCredential` via VS Code account or `az login`. |

### From an external automated client (private path, not in scope for this lab)

Would require P2S VPN or ExpressRoute to vnet-foundry to reach the private endpoint. Out of scope.

---

## 16. Troubleshooting reference

| Symptom | Likely cause | Resolution |
|---------|-------------|-----------|
| `echo_data = {"error": "...Connection refused"}` | T1 not deployed or NSG blocking port 80 | Verify Wave 5 preflight; check nsg-tools rule 100 |
| `echo_data = {"error": "...Name or service not known"}` | Z2 DNS not deployed or dnsmasq not running | Check DNS resolver, forwarding ruleset, dnsmasq service on vm-tools-echo |
| Deployment fails with `mcr.microsoft.com` pull error | AgentSubnet NSG blocks base container image pull — affects both `remote_build` and `bundled` modes | Apply NSG rules 125 (`MicrosoftContainerRegistry`, TCP 443) and 126 (`AzureActiveDirectory`, TCP 443). Switching to `bundled` does not resolve this. |
| 401 on SDK invoke from vm-diag | Missing `Foundry Agent Consumer` role on managed identity | Assign role at project scope; allow ~2 minutes for propagation |
| `src_ip` in HS2 matches HS1 data proxy IPs | Platform SNAT or shared IP pool (OQ1) | Document as AMBIGUOUS; record both IPs; do not assume failure |
| Deployment times out after 10+ minutes | `remote_build` build queue or transient failure | Check VS Code Output → Foundry Toolkit; retry `azd deploy`; inspect container logs with `azd ai agent monitor echo-probe-agent` |
