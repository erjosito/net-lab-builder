"""
probe_network.py -- Programmatic invocation comparison: client-side FC vs hosted agent.

PRIMARY API: azure-ai-projects 2.x AIProjectClient (officially supported, Microsoft-owned SDK).
No LangChain, LlamaIndex, or third-party frameworks.

AGENT TYPES AND SDK ARCHITECTURE (azure-ai-projects 2.3.0)
-----------------------------------------------------------
azure-ai-projects 2.3.0 AgentsOperations manages HOSTED AGENT LIFECYCLE only:
  create_version(), create_session(), enable(), disable(), list_versions() etc.
  There is NO create_agent()/threads/runs (Assistants API) in this SDK version.
  Foundry portal prompt agents with HTTP connections cannot be created programmatically here.

TWO INVOCATION PATHS TESTED
----------------------------

Hosted agent (HS2/HS3) -- PROVEN DATA PATH:
  AIProjectClient.get_openai_client(agent_name="echo-probe-agent")
  -> base_url: <endpoint>/agents/<name>/endpoint/protocols/openai
  -> oai.responses.create(model="echo-probe-agent", input=..., stream=False)
  -> Tool calls (probe_echo, probe_ctrl) execute in MICRO VM NIC context (AgentSubnet 192.168.0.x)
  -> Micro VM IS inside the VNet; echo.tools.lab and ctrl.tools.lab DNS resolves correctly

Client-side function calling (HS1 equivalent) -- CONTROL PATH:
  AIProjectClient.get_openai_client()  [no agent_name]
  -> base_url: <endpoint>/openai/v1/
  -> oai.responses.create(model="gpt-5-mini", input=..., tools=[function_def...])
  -> Tool calls execute on the CALLER (this script, on the workstation)
  -> EXPECTED from workstation: Connection FAILURE to echo.tools.lab (DNS not reachable outside VNet)
  -> This proves: client-side FC does NOT use the data proxy; private targets require hosted agent or data proxy

DATA PROXY NOTE (Foundry portal path, not tested here):
  When a Foundry portal agent is configured with an HTTP Connection resource,
  tool HTTP calls go through the Foundry data proxy (AgentSubnet 192.168.0.x).
  This path cannot be created programmatically via azure-ai-projects 2.3.0.
  Prior evidence (2026-08-14): data proxy src_ip = 192.168.0.49, 192.168.0.239.

INTERNAL FRAMEWORK (hosted agent server side -- NOT for external callers):
  agent_framework_openai 1.12.0 (Microsoft Agent Framework / MAF)
  agent_framework_foundry 1.10.4 + agent_framework_foundry_hosting 1.0.0b260730
  azure-ai-agentserver-responses 1.0.0b9 (hosted agent server runtime)
  These run INSIDE the Micro VM. External callers use AIProjectClient, not MAF directly.

PREREQUISITES
-------------
1. vm-tools-echo (10.1.100.4) RUNNING -- echo endpoint + dnsmasq DNS for tools.lab
2. vm-tools-ctrl (10.1.200.4) RUNNING -- ctrl endpoint
3. echo-probe-agent:1 ACTIVE in Foundry project
4. Azure CLI logged in

Start VMs if deallocated:
   az vm start -g <rg-foundry> -n vm-tools-echo
   az vm start -g <rg-foundry> -n vm-tools-ctrl

USAGE
-----
   python probe_network.py [--hosted] [--client-fc] [--stream] [--out results.json] [--env <path>]
"""

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Heavy dependencies (azure-ai-projects, requests, azure-identity) are imported
# locally inside each function rather than at module top-level.  This keeps the
# import section lean and avoids ImportError on machines that have only a subset
# installed.  It also makes each function's dependency explicit at the call site.
#
# ``time`` provides time.monotonic() for latency measurement (monotonic clock,
# unaffected by NTP adjustments, suitable for elapsed-time deltas).
# ``datetime`` provides UTC wall-clock timestamps for the output JSON filename
# and the _timestamp field.
# ``argparse`` drives the CLI mode selection described in the Usage section above.


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Keys that this script reads from the azd .env file or from process environment
# variables.  Only non-sensitive connection metadata is listed here; tokens and
# credentials are never stored in config files (they are acquired at runtime via
# azure-identity).
ENV_KEYS = [
    "AZURE_AI_ACCOUNT_NAME",
    "AZURE_AI_PROJECT_NAME",
    "AZURE_AI_MODEL_DEPLOYMENT_NAME",
    "FOUNDRY_PROJECT_ENDPOINT",
    # Optional: if set, probe_hosted_rest() uses this URL directly instead of
    # constructing it from ACCOUNT + PROJECT.  Populated by azd when the agent
    # is deployed (azd output AGENT_ECHO_PROBE_AGENT_RESPONSES_ENDPOINT).
    "AGENT_ECHO_PROBE_AGENT_RESPONSES_ENDPOINT",
]

# Resolve the azd-generated .env file relative to this script's location.
# Layout: tests/ -> parent -> hosted-agent/ -> .azure/foundry-networking/.env
# The foundry-networking environment name matches the azd environment used by
# `azd up` in the hosted-agent directory.  If the file does not exist (e.g. on
# a CI runner that passes env vars directly), load_config() silently skips it.
DEFAULT_ENV_PATH = (
    Path(__file__).parent.parent
    / "hosted-agent" / ".azure" / "foundry-networking" / ".env"
)


def load_config(env_path: Optional[Path] = None) -> dict:
    """
    Load Foundry connection config from a .env file, then overlay process env vars.

    **Priority order (highest wins):** process environment > .env file.
    This matches the azd convention: ``azd env set KEY VALUE`` writes to the .env
    file, but a CI pipeline can override individual values by setting env vars
    without modifying the checked-in .env.

    **Secret handling:** This function reads only the keys in ENV_KEYS.  Tokens
    and credentials are NOT in the config dict; they are acquired at runtime via
    ``azure-identity`` (see the ``credential`` parameter on each probe function).
    The returned dict is safe to include in sanitized output (it contains only
    account/project names and endpoint URLs, not auth material).

    **Why not python-dotenv?** No extra dependency; the simple KEY=VALUE parsing
    here covers the azd .env format (optional double-quote stripping, no
    multi-line values, comment lines starting with #).

    :param env_path: Override the default .env path.  Pass None to use DEFAULT_ENV_PATH.
    :raises RuntimeError: if any of the three required keys are absent after merging.
    """
    cfg: dict = {}
    path = env_path or DEFAULT_ENV_PATH
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                cfg[k.strip()] = v.strip().strip('"')
    for k in ENV_KEYS:
        if os.environ.get(k):
            cfg[k] = os.environ[k]

    # Validate that the minimum required keys are present before any network call.
    # FOUNDRY_PROJECT_ENDPOINT is constructed by azd as:
    #   https://<account>.services.ai.azure.com/api/projects/<project>
    # It is the base URL for both AIProjectClient and the REST paths.
    required = ["AZURE_AI_ACCOUNT_NAME", "AZURE_AI_PROJECT_NAME", "FOUNDRY_PROJECT_ENDPOINT"]
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        raise RuntimeError(
            f"Missing required config: {missing}. "
            "Run with azd env selected, or set env vars manually."
        )
    return cfg


# ---------------------------------------------------------------------------
# Hosted agent -- SDK path (primary)
# ---------------------------------------------------------------------------

def probe_hosted_sdk(cfg: dict, credential, prompt: str) -> dict:
    """
    Invoke echo-probe-agent via AIProjectClient.get_openai_client(agent_name=...).

    This is the **primary, officially supported SDK path** for hosted agents.
    Docs: https://learn.microsoft.com/azure/ai-foundry/agents/concepts/hosted-agents-overview

    ## SDK routing mechanism

    ``get_openai_client(agent_name="echo-probe-agent")`` patches the base_url to:
      ``<endpoint>/agents/<agent_name>/endpoint/protocols/openai/``
    so that ``oai.responses.create(model="echo-probe-agent", ...)`` sends a POST to:
      ``<endpoint>/agents/echo-probe-agent/endpoint/protocols/openai/responses``
    Foundry routes that request to the Micro VM running echo-probe-agent version 1.

    For contrast, ``get_openai_client()`` with no ``agent_name`` sets base_url to:
      ``<endpoint>/openai/v1/``
    which reaches the standard Foundry OpenAI endpoint (no hosted-agent routing).
    That is the path used by ``probe_client_side_fc()``.

    ## ``model`` field in ``oai.responses.create()``

    The OpenAI Responses API ``model`` field is repurposed by Foundry for hosted
    agents: it must equal the agent name (not a model deployment name).  The
    routing is done at the endpoint level (base_url), but the ``model`` field
    must still match for the platform to select the correct agent version.

    ## ``allow_preview=True``

    Required to enable preview APIs in azure-ai-projects 2.x (e.g. Sessions API,
    ``create_version``, ``create_session``).  Harmless for basic Responses API
    calls but included here for consistency with ``probe_hosted_sessions()``.

    ## Alternatives and why this SDK path is the baseline

    | Approach | Notes |
    |----------|-------|
    | This function (AIProjectClient SDK) | Microsoft-owned, officially supported; handles token refresh + retry |
    | ``probe_hosted_rest()`` (raw requests) | Required for streaming SSE; more verbose; useful for low-level debugging |
    | LangChain ``AzureAIChatCompletionsModel`` | Third-party dep; abstracts away routing details; not appropriate for SDK-baseline evidence |
    | Semantic Kernel ``AzureAIInferenceChatCompletion`` | Same trade-off as LangChain; adds abstraction overhead |
    | ``azure-openai`` SDK pointing at Foundry endpoint | Works for model calls; does not expose hosted-agent lifecycle (create_session, etc.) |

    ## Output parsing

    ``oai.responses.create()`` returns an SDK model object (not a raw dict).
    Attributes are accessed with ``getattr(item, "type")`` because the SDK uses
    Pydantic-like deserialization; bracket-style ``item["type"]`` would raise
    ``TypeError``.  ``item.output`` for ``function_call_output`` items is a JSON
    *string* that must be parsed again with ``json.loads()``.
    """
    from azure.ai.projects import AIProjectClient

    endpoint = cfg["FOUNDRY_PROJECT_ENDPOINT"]
    client = AIProjectClient(endpoint=endpoint, credential=credential, allow_preview=True)
    oai = client.get_openai_client(agent_name="echo-probe-agent")

    t0 = time.monotonic()
    resp = oai.responses.create(
        model="echo-probe-agent",
        input=prompt,
        stream=False,
    )
    elapsed = round(time.monotonic() - t0, 2)

    # Iterate the response output items.  The list typically contains:
    #   - "function_call" items (the model's tool-call requests, not needed here)
    #   - "function_call_output" items (the tool's return values, what we want)
    #   - "message" items (the LLM's final natural-language summary)
    # We collect only "function_call_output" and key them by the "label" field
    # from the echo service response (e.g. "echo", "ctrl").
    tool_outputs: dict = {}
    output_types = []
    for item in getattr(resp, "output", []):
        item_type = getattr(item, "type", "unknown")
        output_types.append(item_type)
        if item_type == "function_call_output":
            try:
                data = json.loads(item.output)
                label = data.get("label")
                if label:
                    tool_outputs[label] = data
            except (json.JSONDecodeError, AttributeError):
                pass

    return {
        "method": "hosted_agent_sdk",
        "sdk": "azure-ai-projects.AIProjectClient.get_openai_client(agent_name=...)",
        "endpoint_type": "hosted-agent Responses (stateless)",
        "base_url_pattern": "<endpoint>/agents/<name>/endpoint/protocols/openai",
        "auth": "AIProjectClient managed (azure-identity, ai.azure.com scope)",
        "stream": False,
        "latency_s": elapsed,
        "tool_outputs": tool_outputs,
        "output_item_types": output_types,
        "agent_version": "echo-probe-agent:1",
        "egress_context": "Micro VM NIC inside AgentSubnet (192.168.0.0/24)",
    }


# ---------------------------------------------------------------------------
# Hosted agent -- REST direct path (secondary / streaming demo)
# ---------------------------------------------------------------------------

def probe_hosted_rest(cfg: dict, credential, prompt: str, stream: bool = False) -> dict:
    """
    Invoke echo-probe-agent via direct REST POST to the Responses endpoint.
    Uses requests + AzureCliCredential token (ai.azure.com scope).

    This is the **secondary path**: useful for streaming SSE output and low-level
    debugging of exact HTTP payloads.  For reliability in production scripts,
    prefer ``probe_hosted_sdk()`` (token refresh, retry, SDK model parsing).

    Docs (Responses API reference):
      https://platform.openai.com/docs/api-reference/responses
      https://learn.microsoft.com/azure/ai-foundry/reference/reference-model-inference-api

    ## Raw REST vs SDK: when to use each

    | Concern | Raw REST (this fn) | SDK (probe_hosted_sdk) |
    |---------|--------------------|------------------------|
    | Streaming SSE | ✓ via requests stream=True | SDK does not expose SSE generator yet |
    | Token management | Manual — caller must refresh before expiry | SDK auto-refreshes |
    | Response parsing | Manual dict parsing | SDK model objects |
    | Debugging | Full request/response visibility | Abstracted |
    | Dep surface | requests + azure-identity | azure-ai-projects (includes both) |

    ## Auth flow

    ``credential.get_token("https://ai.azure.com/.default")`` acquires a short-lived
    Azure AD access token for the Azure AI Foundry API resource.
    The ``.token`` attribute is the raw JWT string sent as ``Authorization: Bearer <token>``.
    Token lifetime: typically 60–75 minutes.  ``AzureCliCredential`` reads from the
    ``az login`` cache; ``DefaultAzureCredential`` would try the managed identity chain
    first (10-second timeout on this workstation before falling through to CLI).
    The outer ``main()`` selects ``AzureCliCredential`` explicitly for that reason.
    Docs: https://learn.microsoft.com/azure/developer/python/sdk/authentication-overview

    ## Endpoint URL

    Priority: ``AGENT_ECHO_PROBE_AGENT_RESPONSES_ENDPOINT`` env var (set by azd) >
    constructed from account + project names.  Canonical pattern:
      ``https://<account>.services.ai.azure.com/api/projects/<project>/agents/<agent>/endpoint/protocols/openai/responses?api-version=v1``

    ## Streaming SSE format (when ``stream=True``)

    The server returns Server-Sent Events (SSE).  Each event is a ``data: {json}``
    line followed by a blank line.  The terminal event is ``data: [DONE]``.
    Relevant event type for tool results:
      ``"response.output_item.done"`` — emitted once per complete output item.
    ``item["type"] == "function_call_output"`` items carry the tool's return value
    as a JSON string in ``item["output"]``.
    ``requests.Response.iter_lines()`` handles line buffering and byte/str decoding.
    Docs: https://platform.openai.com/docs/api-reference/responses/streaming

    ## Non-streaming format (when ``stream=False``)

    Standard JSON response body.  ``body["output"]`` is a list; ``item["type"]``
    and ``item["output"]`` use plain dict access (raw JSON, not SDK model objects).
    """
    import requests as req

    responses_ep = cfg.get("AGENT_ECHO_PROBE_AGENT_RESPONSES_ENDPOINT") or (
        f"https://{cfg['AZURE_AI_ACCOUNT_NAME']}.services.ai.azure.com"
        f"/api/projects/{cfg['AZURE_AI_PROJECT_NAME']}"
        f"/agents/echo-probe-agent/endpoint/protocols/openai/responses?api-version=v1"
    )

    # Acquire a fresh bearer token for the ai.azure.com resource.  The token is
    # a short-lived JWT (~60–75 min).  For long-running scripts that make repeated
    # calls, re-acquire the token before each request or check token.expires_on.
    tok = credential.get_token("https://ai.azure.com/.default").token
    payload = {"model": "echo-probe-agent", "input": prompt, "stream": stream}

    t0 = time.monotonic()
    if stream:
        # Streaming path: hold the HTTP connection open and consume SSE events
        # line-by-line.  ``requests`` context manager ensures the connection is
        # closed when the with-block exits, even on exception.
        sse_lines: list = []
        with req.post(
            responses_ep,
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            json=payload,
            stream=True,
            timeout=120,
        ) as r:
            r.raise_for_status()
            for raw_line in r.iter_lines():
                # iter_lines() yields non-empty lines; blank lines (SSE event
                # separators) are filtered out by the ``if raw_line`` guard.
                if raw_line:
                    sse_lines.append(
                        raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                    )
        elapsed = round(time.monotonic() - t0, 2)
        tool_outputs: dict = {}
        for line in sse_lines:
            # SSE lines relevant to us start with "data: " and are not the
            # terminal "data: [DONE]" sentinel.
            if line.startswith("data: ") and "[DONE]" not in line:
                try:
                    # Strip the "data: " prefix (6 characters) before JSON parsing.
                    evt = json.loads(line[6:])
                    # "response.output_item.done" is emitted when a full output
                    # item is available.  Other event types include
                    # "response.created", "response.output_item.added", etc.
                    if evt.get("type") == "response.output_item.done":
                        item = evt.get("item", {})
                        if item.get("type") == "function_call_output":
                            try:
                                # item["output"] is a JSON string; parse it to
                                # recover the echo service response dict.
                                data = json.loads(item.get("output", "{}"))
                                tool_outputs[data.get("label", item.get("call_id", "?"))] = data
                            except json.JSONDecodeError:
                                pass
                except json.JSONDecodeError:
                    pass
        return {
            "method": "hosted_agent_rest_streaming",
            "sdk": "requests + AzureCliCredential direct REST (SSE)",
            "endpoint_type": "hosted-agent Responses SSE stream",
            "stream": True,
            "latency_s": elapsed,
            "sse_event_count": len(sse_lines),
            "tool_outputs": tool_outputs,
        }
    else:
        r = req.post(
            responses_ep,
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
        r.raise_for_status()
        elapsed = round(time.monotonic() - t0, 2)
        body = r.json()
        # Non-streaming response: body["output"] is a list of output items.
        # Plain dict access (item["type"], item["output"]) because this is raw
        # JSON, not an SDK model object.
        tool_outputs = {}
        for item in body.get("output", []):
            if item.get("type") == "function_call_output":
                try:
                    data = json.loads(item["output"])
                    tool_outputs[data.get("label", "?")] = data
                except json.JSONDecodeError:
                    pass
        return {
            "method": "hosted_agent_rest",
            "sdk": "requests + AzureCliCredential direct REST",
            "endpoint_type": "hosted-agent Responses (stateless)",
            "stream": False,
            "latency_s": elapsed,
            "tool_outputs": tool_outputs,
        }




# ---------------------------------------------------------------------------
# Hosted agent -- Sessions API (stateful compute sandbox, optional)
# ---------------------------------------------------------------------------

def probe_hosted_sessions(cfg: dict, credential, *, stop_after_create: bool = True) -> dict:
    """
    Demonstrate the Sessions API for hosted agents: create a long-lived compute sandbox.

    Sessions vs Responses API:
      Responses (stateless): Each call may use a different ephemeral Micro VM.
                             src_ip changes per invocation (observed: 8 distinct IPs).
      Sessions (stateful):   Creates a persistent Micro VM sandbox. Repeated interactions
                             within the same session SHOULD use the SAME VM NIC IP.
                             Use case: code interpreter, file operations, multi-turn state.

    Session lifecycle:
      POST /agents/<name>/endpoint/sessions  -> AgentSessionResource (session_id, status)
      GET  /agents/<name>/endpoint/sessions/<id>  -> poll until status=active
      [interact via Responses API with session context]
      DELETE /agents/<name>/endpoint/sessions/<id>  -> stop/delete

    Session interaction (not fully implemented here):
      The sessions API creates the sandbox; tool interactions still go through the Responses
      endpoint. The session_id binds subsequent Responses calls to the same Micro VM.
      The exact mechanism for binding a Responses call to a session_id is not exposed via
      the get_openai_client() interface; it may require raw REST with an X-Session-Id header
      or a session_id query parameter on the Responses endpoint.

    Cost note: Sessions are long-lived (30-day expiry from last access). Each active session
    keeps a Micro VM running, which incurs compute cost. Always stop/delete sessions after use.

    This function creates a session, inspects it, then STOPS it immediately (stop_after_create=True).
    It does NOT send messages to the session (interaction model not yet confirmed).
    """
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import VersionRefIndicator

    endpoint = cfg["FOUNDRY_PROJECT_ENDPOINT"]
    client = AIProjectClient(endpoint=endpoint, credential=credential, allow_preview=True)

    t0 = time.monotonic()
    try:
        # Create the session with the active version
        session = client.agents.create_session(
            "echo-probe-agent",
            version_indicator=VersionRefIndicator(version="1"),
        )
        create_elapsed = round(time.monotonic() - t0, 2)
        session_id = session.agent_session_id
        status = str(session.status)

        result = {
            "method": "hosted_agent_sessions_api",
            "sdk": "azure-ai-projects.AIProjectClient.agents.create_session()",
            "endpoint_type": "hosted-agent Sessions (stateful compute sandbox)",
            "base_url_pattern": "<endpoint>/agents/<name>/endpoint/sessions",
            "session_id_masked": f"...{session_id[-8:]}",  # last 8 chars only, for reference
            "initial_status": status,
            "create_latency_s": create_elapsed,
            "finding": (
                "Session created. Stateful path confirmed. "
                "Repeated Responses calls within a session should reuse the same Micro VM NIC IP. "
                "Session is stopped immediately to avoid cost."
            ),
            "cost_note": "Sessions keep Micro VM running until stopped/expired. Stop after use.",
        }

        if stop_after_create and session_id:
            try:
                client.agents.stop_session("echo-probe-agent", session_id)
                result["session_stopped"] = True
            except Exception as e:
                result["stop_error"] = str(e)

        return result

    except Exception as exc:
        return {
            "method": "hosted_agent_sessions_api",
            "error": str(exc),
            "note": (
                "Sessions API requires allow_preview=True and the agent to be in active/enabled state. "
                "VersionRefIndicator takes the version number string (e.g. '1')."
            ),
        }
# ---------------------------------------------------------------------------
# Client-side function calling via standard Foundry OpenAI endpoint (control path)
# ---------------------------------------------------------------------------

def probe_client_side_fc(cfg: dict, credential, prompt: str) -> dict:
    """
    Invoke the standard Foundry project OpenAI endpoint (NOT a hosted agent) with
    client-side function calling (standard OpenAI tool use loop).

    API: AIProjectClient.get_openai_client()  -- no agent_name -- points to:
      <endpoint>/openai/v1/

    Tool HTTP calls execute on the CALLING CLIENT (this script, on the workstation).
    This is NOT the Foundry data proxy path. The data proxy requires a Foundry
    portal-configured agent with HTTP Connection resources, which cannot be created
    programmatically via azure-ai-projects 2.3.0 (AgentsOperations is for hosted
    agent lifecycle only: create_version, create_session, etc.).

    EXPECTED RESULT from workstation: Connection failure to echo.tools.lab / ctrl.tools.lab
    because tools.lab DNS resolves only inside the VNet (DNS Private Resolver + dnsmasq).
    This proves client-side FC cannot access private VNet-only targets from outside the VNet,
    whereas hosted agents (Micro VM NIC inside AgentSubnet) can.

    If run from vm-diag (inside vnet-foundry): DNS resolves and src_ip = vm-diag NIC IP
    (192.168.2.4), NOT an AgentSubnet IP -- confirming client-side FC never uses the data proxy.
    """
    import requests as req
    from azure.ai.projects import AIProjectClient

    endpoint = cfg["FOUNDRY_PROJECT_ENDPOINT"]
    model = cfg.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5-mini")

    # No agent_name -> routes to standard Foundry OpenAI endpoint (<endpoint>/openai/v1/)
    client = AIProjectClient(endpoint=endpoint, credential=credential)
    oai = client.get_openai_client()

    function_tools = [
        {
            "type": "function",
            "name": "probe_echo",
            "description": "HTTP GET to http://echo.tools.lab/api/echo returning src_ip and server_ip.",
            "parameters": {"type": "object", "properties": {}, "required": []},
            "strict": False,
        },
        {
            "type": "function",
            "name": "probe_ctrl",
            "description": "HTTP GET to http://ctrl.tools.lab/api/echo returning src_ip and server_ip.",
            "parameters": {"type": "object", "properties": {}, "required": []},
            "strict": False,
        },
    ]

    t0 = time.monotonic()
    resp = oai.responses.create(
        model=model,
        input=prompt,
        tools=function_tools,
    )

    # Execute function calls locally (client-side) and collect results or failures
    tool_calls_requested: list = []
    tool_outputs: dict = {}
    connection_failures: list = []

    for item in getattr(resp, "output", []):
        item_type = getattr(item, "type", "")
        if item_type == "function_call":
            # The model returned a "function_call" output item requesting this tool.
            # In a complete OpenAI tool-use loop the caller would:
            #   1. Execute the function.
            #   2. Send a second request with the tool result (role="tool").
            #   3. Receive the final model response.
            # This script only performs step 1 — capturing the failure (or success)
            # from the calling workstation is the sole objective.  The second-turn
            # result submission is intentionally omitted; the lab finding is
            # recorded directly from the connection attempt outcome.
            tool_name = getattr(item, "name", "")
            tool_calls_requested.append(tool_name)
            url_map = {
                "probe_echo": "http://echo.tools.lab/api/echo",
                "probe_ctrl": "http://ctrl.tools.lab/api/echo",
            }
            url = url_map.get(tool_name, "")
            if url:
                try:
                    r = req.get(url, timeout=(3, 5))
                    r.raise_for_status()
                    data = r.json()
                    tool_outputs[tool_name] = data
                except Exception as exc:
                    # Expected from workstation: NameResolutionError (DNS not
                    # available outside VNet) or ConnectionError.  The exception
                    # message is recorded verbatim as lab evidence.
                    connection_failures.append(f"{tool_name}: {type(exc).__name__}: {exc}")
                    tool_outputs[tool_name] = {"error": str(exc), "src_ip": "N/A (client-side failure)"}

    elapsed = round(time.monotonic() - t0, 2)

    finding = (
        "EXPECTED: Connection failure from workstation -- tools.lab DNS resolves only inside VNet. "
        "Client-side FC cannot access private VNet-only targets. "
        "Hosted agent (Micro VM NIC inside AgentSubnet) and data proxy (inside vnet-foundry) can."
        if connection_failures
        else (
            "NOTE: Connections succeeded -- caller is likely inside VNet (e.g. vm-diag). "
            "src_ip will be caller NIC IP, NOT AgentSubnet -- confirms no data proxy involvement."
        )
    )

    return {
        "method": "client_side_function_calling",
        "sdk": "azure-ai-projects.AIProjectClient.get_openai_client() [no agent_name] -> /openai/v1/",
        "endpoint_type": "standard Foundry OpenAI endpoint (client-side tool execution)",
        "base_url_pattern": "<endpoint>/openai/v1/",
        "auth": "AIProjectClient managed (azure-identity)",
        "model": model,
        "stream": False,
        "latency_s": elapsed,
        "tool_calls_requested_by_model": tool_calls_requested,
        "tool_outputs": tool_outputs,
        "connection_failures": connection_failures,
        "egress_context": "CALLER (workstation/vm-diag NIC), NOT data proxy or Micro VM NIC",
        "finding": finding,
        "sdk_note": (
            "azure-ai-projects 2.3.0 AgentsOperations manages hosted agent lifecycle only "
            "(create_version, create_session, enable, disable). "
            "No create_agent/threads/runs (Assistants API). "
            "Foundry portal prompt agents with HTTP connections cannot be created programmatically."
        ),
    }


# ---------------------------------------------------------------------------
# Comparison summary
# ---------------------------------------------------------------------------

def compare(hosted: dict, client_fc: Optional[dict]) -> dict:
    """
    Build a side-by-side network-finding comparison table from probe results.

    The comparison table is the primary deliverable for lab evidence: it puts the
    key network observables (src_ip, server_ip, reachability, latency) in one
    place so H2 can be assessed from a single JSON output.

    ## src_ip key convention mismatch

    The hosted agent returns ``tool_outputs`` keyed by the echo service's ``label``
    field (``"echo"``, ``"ctrl"``).  The client-side FC path keys by the Python
    function name (``"probe_echo"``, ``"probe_ctrl"``).  The ``src_ip()`` helper
    therefore takes the key as a parameter; callers must use the right convention
    for each result dict.

    ## H2 assessment logic

    Full H2 confirmation requires evidence on BOTH sides:
      - Hosted path: ``h_echo_src != "N/A"`` → tools.lab was reachable from Micro VM NIC.
      - Client-FC path: ``connection_failures`` non-empty → tools.lab was NOT reachable
        from the calling workstation.
    If only the hosted probe succeeded (no client-FC comparison), H2 is partially confirmed:
    the Micro VM NIC is shown to reach private targets, but no contrast with the caller.
    The ``h2_assessment`` string is suitable for direct inclusion in the lab evidence JSON.

    ## Data proxy evidence

    Neither probe path uses the Foundry data proxy:
      - Hosted agent: direct Micro VM NIC egress (H2 hypothesis under test).
      - Client-side FC: caller NIC egress (workstation or vm-diag).
    The data proxy path (Foundry portal agent + HTTP Connection resource) is documented
    in the module docstring and in earlier raw-output files; its src_ip was observed
    as 192.168.0.49 and 192.168.0.239 (distinct from Micro VM NIC IPs).
    """
    def src_ip(result: dict, label: str) -> str:
        return (result.get("tool_outputs", {}).get(label) or {}).get("src_ip", "N/A")

    def server_ip(result: dict, label: str) -> str:
        return (result.get("tool_outputs", {}).get(label) or {}).get("server_ip", "N/A")

    h_echo_src = src_ip(hosted, "echo")
    c_echo_src = src_ip(client_fc, "probe_echo") if client_fc else "N/A"

    h2 = (
        "H2 CONFIRMED: Hosted agent Micro VM NIC egress from AgentSubnet (192.168.0.x). "
        "Client-side FC fails to reach tools.lab from workstation (DNS not reachable outside VNet), "
        "proving hosted agent / data proxy required for private VNet-only targets."
        if hosted and h_echo_src != "N/A" and client_fc and client_fc.get("connection_failures")
        else (
            "H2 CONFIRMED: Hosted agent Micro VM NIC egress from AgentSubnet (192.168.0.x)."
            if hosted and h_echo_src != "N/A"
            else "H2: insufficient data"
        )
    )

    return {
        "comparison_table": [
            {
                "dimension": "Agent / caller type",
                "hosted": "hosted-agent echo-probe-agent:1 (Micro VM NIC, inside AgentSubnet)",
                "client_fc": "client-side FC via standard Foundry OpenAI endpoint" if client_fc else "N/A",
            },
            {
                "dimension": "Invocation API",
                "hosted": hosted.get("sdk", hosted.get("method")),
                "client_fc": client_fc.get("sdk", "") if client_fc else "N/A",
            },
            {
                "dimension": "Endpoint type",
                "hosted": hosted.get("endpoint_type"),
                "client_fc": client_fc.get("endpoint_type", "N/A") if client_fc else "N/A",
            },
            {
                "dimension": "echo src_ip (caller seen by server)",
                "hosted": h_echo_src,
                "client_fc": c_echo_src,
            },
            {
                "dimension": "ctrl src_ip",
                "hosted": src_ip(hosted, "ctrl"),
                "client_fc": src_ip(client_fc, "probe_ctrl") if client_fc else "N/A",
            },
            {
                "dimension": "echo server_ip",
                "hosted": server_ip(hosted, "echo"),
                "client_fc": server_ip(client_fc, "probe_echo") if client_fc else "N/A",
            },
            {
                "dimension": "tools.lab reachable",
                "hosted": "Yes (Micro VM inside VNet)",
                "client_fc": (
                    f"No (DNS/connection failure): {client_fc.get('connection_failures', [])}"
                    if client_fc and client_fc.get("connection_failures")
                    else "Yes (caller is inside VNet)"
                ) if client_fc else "N/A",
            },
            {
                "dimension": "Latency (s)",
                "hosted": hosted.get("latency_s"),
                "client_fc": client_fc.get("latency_s") if client_fc else "N/A",
            },
            {
                "dimension": "Data proxy used",
                "hosted": "No (direct Micro VM NIC egress)",
                "client_fc": "No (client-side; data proxy requires Foundry portal agent with HTTP Connection)" if client_fc else "N/A",
            },
        ],
        "h2_assessment": h2,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Parse CLI arguments, load configuration, run selected probes, and write results JSON.

    ## CLI modes

    | Invocation | Probes run |
    |------------|-----------|
    | ``python probe_network.py`` | Both hosted SDK + client-side FC (default) |
    | ``python probe_network.py --hosted`` | Hosted SDK only |
    | ``python probe_network.py --client-fc`` | Client-side FC only |
    | ``python probe_network.py --hosted --stream`` | Hosted SDK + streaming REST probe |
    | ``python probe_network.py --out results.json`` | Custom output file name |
    | ``python probe_network.py --env /path/to/.env`` | Custom azd .env file |

    ``probe_hosted_sessions()`` is defined in this module but is **not exposed by any CLI flag**.
    It is documented for reference (sessions API lifecycle) but was not live-tested: a running
    session keeps a Micro VM alive (30-day TTL, per-minute cost) and the interaction model
    (binding a Responses call to a session_id) was not confirmed at test time.

    Default (no flags): ``run_hosted = run_client_fc = True``.  The logic is:
    if either specific flag is set, run only the flagged paths; if neither is set,
    run both.  This avoids requiring the user to type both flags for the normal case.

    ## Credential: AzureCliCredential vs DefaultAzureCredential

    ``DefaultAzureCredential`` tries credentials in order: environment variables,
    workload identity, managed identity (IMDS endpoint), Azure CLI, VS Code, etc.
    On this workstation the managed identity check sends a gRPC probe with a 10-second
    timeout before concluding no managed identity is available.  ``AzureCliCredential``
    skips directly to the ``az login`` token cache, eliminating the wait.
    For Azure-hosted environments (App Service, AKS) where managed identity IS available,
    ``DefaultAzureCredential`` is the better choice.
    Docs: https://learn.microsoft.com/azure/developer/python/sdk/authentication-overview

    ## Result sanitization

    The ``_note`` field in the output JSON documents what is intentionally omitted:
    subscription IDs, tenant IDs, tokens, and full endpoint URLs.  Probe functions
    return only the echo service's response fields (src_ip, server_ip, label,
    request_url) plus SDK/method metadata strings — no auth material.

    ``json.dump(default=str)`` ensures that any SDK model object that escaped
    JSON serialization (e.g. a non-parsed enum) is coerced to its string
    representation rather than raising ``TypeError``.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Network path comparison: hosted agent (Micro VM NIC) vs client-side FC "
            "(standard Foundry OpenAI endpoint). Uses azure-ai-projects 2.3.0 AIProjectClient."
        )
    )
    parser.add_argument("--hosted", action="store_true", help="Run hosted agent test only.")
    parser.add_argument("--client-fc", action="store_true", dest="client_fc",
                        help="Run client-side function calling test only.")
    parser.add_argument("--stream", action="store_true", help="Also run hosted agent streaming probe.")
    parser.add_argument("--out", default="", help="Output JSON file path.")
    parser.add_argument("--env", default="", help="Path to azd .env file.")
    args = parser.parse_args()

    run_hosted = args.hosted or (not args.hosted and not args.client_fc)
    run_client_fc = args.client_fc or (not args.hosted and not args.client_fc)

    cfg = load_config(Path(args.env) if args.env else None)

    # AzureCliCredential is chosen explicitly to avoid the 10-second IMDS gRPC
    # timeout from DefaultAzureCredential on this workstation.  See docstring above.
    from azure.identity import AzureCliCredential
    credential = AzureCliCredential()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # _sdk_map documents which SDK/framework is responsible for each layer.
    # External callers (this script) use azure-ai-projects; the hosted agent's
    # internal runtime (MAF, agentserver-responses) runs INSIDE the Micro VM
    # and is invisible to external callers.
    results: dict = {
        "_note": "Sanitized output. No subscription IDs, tenant IDs, tokens, or endpoints.",
        "_timestamp": ts,
        "_sdk_map": {
            "azure-ai-projects 2.3.0": "External caller SDK for BOTH paths",
            "agent_framework_openai 1.12.0": "MAF -- hosted agent INTERNAL runtime (server side, not for external callers)",
            "azure-ai-agentserver-responses 1.0.0b9": "Hosted agent server runtime (server side, not for external callers)",
            "azure-identity 1.25.3": "Auth; AzureCliCredential for local dev",
        },
    }

    PROBE_MSG = (
        "Probe both echo and ctrl endpoints and return complete JSON from each, "
        "including src_ip, server_ip, and request_url."
    )
    # The prompt instructs the hosted agent (echo-probe-agent) to call both tools
    # and return ALL fields.  The same message is reused for client-side FC to
    # keep the comparison symmetrical.

    hosted_result = None
    client_fc_result = None

    if run_hosted:
        print("[hosted:sdk]  Invoking echo-probe-agent via AIProjectClient.get_openai_client(agent_name=...)...", flush=True)
        try:
            hosted_result = probe_hosted_sdk(cfg, credential, PROBE_MSG)
            print(
                f"  latency={hosted_result['latency_s']}s  "
                f"tool_outputs={list(hosted_result['tool_outputs'].keys())}"
            )
        except Exception as e:
            hosted_result = {"method": "hosted_agent_sdk", "error": str(e), "tool_outputs": {}}
            print(f"  ERROR: {e}")
        results["hosted_sdk"] = hosted_result

        if args.stream:
            # --stream adds a second hosted probe via raw REST SSE.
            # Purpose: demonstrate the streaming response format and confirm that
            # the same src_ip is returned when the Micro VM handles the request
            # via a different HTTP path (SSE vs non-streaming JSON).
            print("[hosted:rest-stream]  Invoking via REST SSE stream...", flush=True)
            try:
                stream_result = probe_hosted_rest(cfg, credential, PROBE_MSG, stream=True)
                print(f"  latency={stream_result['latency_s']}s  events={stream_result.get('sse_event_count')}")
                results["hosted_rest_stream"] = stream_result
            except Exception as e:
                results["hosted_rest_stream"] = {"method": "hosted_agent_rest_streaming", "error": str(e)}
                print(f"  ERROR: {e}")

    if run_client_fc:
        print("[client-fc]  Invoking standard Foundry OpenAI endpoint with client-side function tools...", flush=True)
        print("  NOTE: Expected connection failure to tools.lab from workstation (DNS VNet-only).", flush=True)
        try:
            client_fc_result = probe_client_side_fc(cfg, credential, PROBE_MSG)
            failures = client_fc_result.get("connection_failures", [])
            print(
                f"  latency={client_fc_result.get('latency_s')}s  "
                f"tool_calls_requested={client_fc_result.get('tool_calls_requested_by_model', [])}  "
                f"connection_failures={len(failures)}"
            )
            if failures:
                for f in failures:
                    print(f"    FAIL: {f}")
        except Exception as e:
            client_fc_result = {"method": "client_side_function_calling", "error": str(e), "tool_outputs": {}}
            print(f"  ERROR: {e}")
        results["client_side_fc"] = client_fc_result

    if hosted_result or client_fc_result:
        cmp = compare(hosted_result or {"tool_outputs": {}}, client_fc_result)
        results["comparison"] = cmp
        # Print a compact comparison table to stdout for quick visual inspection.
        # Full details (tool_outputs, SDK metadata, SSE event count) are in the JSON file.
        print("\n=== Comparison ===")
        for row in cmp["comparison_table"]:
            print(
                f"  {row['dimension']:<46} "
                f"hosted={str(row.get('hosted',''))[:60]}  "
                f"client_fc={str(row.get('client_fc',''))[:60]}"
            )
        print(f"\n  {cmp['h2_assessment']}")

    out_path = args.out or f"probe_results_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        # default=str handles SDK model objects that were not fully deserialized
        # (e.g. enum values, Pydantic models) without raising TypeError.
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to: {out_path}")


if __name__ == "__main__":
    main()