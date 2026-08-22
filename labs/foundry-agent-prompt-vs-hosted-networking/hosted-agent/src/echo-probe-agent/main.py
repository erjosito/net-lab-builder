# Copyright (c) Microsoft. All rights reserved.
"""
echo-probe-agent — Foundry hosted-agent for network-path probing (HS2 / HS3)
============================================================================

Lab: foundry-agent-prompt-vs-hosted-networking

## What this file does

This module defines a *hosted agent* using the Microsoft Agent Framework (MAF).
When deployed, Foundry runs this code inside a Micro VM (a lightweight managed
container inside the customer VNet, attached to AgentSubnet) and exposes it via
the OpenAI Responses API.  Callers send a natural-language message; the LLM
decides which Python tool functions to call; the results are returned to the
caller as a structured response.

## Network-path hypotheses under test

This agent is designed to test *hypothesis H2*:
  - **H2 (direct code egress):** HTTP calls made by a hosted agent's own Python
    code originate from the Micro VM's dedicated NIC (an IP in AgentSubnet,
    e.g. 192.168.0.y).  This IP is *different* from the IP used by the data
    proxy (192.168.0.x) that handles OpenAPI tool calls from prompt agents.

The ``src_ip`` field in each target's JSON response is the ground-truth evidence.

## Hosted agent vs prompt agent (architectural contrast)

| Aspect | Prompt agent (HS1) | Hosted agent — this file |
|--------|--------------------|--------------------------|
| Code location | None — tools are OpenAPI endpoints | This module, running in Micro VM |
| Tool execution | Foundry data proxy calls the tool URL | Python code in the Micro VM |
| Network egress | Data proxy IP (shared) | Micro VM NIC IP (dedicated) |
| Deployment unit | Config only | Source ZIP or container image |
| Runtime | Foundry managed | ``ResponsesHostServer`` in this file |

## Deployment approach

Foundry supports two source-code deployment modes
(https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent-code):
  - ``remote_build`` — Foundry pip-installs requirements inside the Micro VM.
  - ``bundled`` — dependencies are bundled in the ZIP; Foundry skips pip install.

Both modes still pull the base container image from ``mcr.microsoft.com`` at
Micro VM startup, so MCR outbound access is required regardless of mode.

Alternative: container-image deployment (ACR) — skips source-code altogether;
the team chose source-ZIP for simplicity (no ACR needed).  See manifest §IN-scope.

## Responses API protocol

``ResponsesHostServer.run()`` listens for POST requests from the Foundry platform
and speaks the OpenAI Responses API protocol
(https://platform.openai.com/docs/api-reference/responses).
The caller sends ``{"model": "<agent-name>", "input": "<message>", "stream": false}``.
The server routes the LLM ↔ tool loop internally and returns a structured JSON
response with ``output`` items of type ``message`` and ``function_call_output``.

Alternative: streaming (``"stream": true``).  This agent uses non-streaming for
simplicity; evidence collection only requires the final values.
"""

import os

# ``requests`` — synchronous HTTP client; used for the direct probe calls.
# Why sync requests (not async httpx): the tool functions are called from the
# MAF event loop which is synchronous.  ``httpx`` would require an async tool
# interface that MAF does not yet mandate.
# Docs: https://docs.python-requests.org/en/latest/
import requests

# ``agent_framework`` — Microsoft Agent Framework (MAF) core.
# ``Agent`` wraps the LLM client, system instructions, and registered tools into
# a single runnable object.  MAF is the Microsoft-first choice for hosted agents
# on Foundry; alternatives include LangChain and Semantic Kernel, but MAF is the
# only framework with first-class Foundry Responses-API hosting support today.
# Docs: https://learn.microsoft.com/azure/foundry/agents/agent-framework-overview
from agent_framework import Agent

# ``FoundryChatClient`` — MAF adapter for Azure AI Foundry.  Wraps the project
# endpoint + credential into the interface that ``Agent`` expects for LLM calls.
# Alternative: raw ``azure.ai.projects.AIProjectClient`` + manual Responses API
# requests.  FoundryChatClient hides the auth header refresh and retry logic.
from agent_framework.foundry import FoundryChatClient

# ``ResponsesHostServer`` — starts the HTTP listener that implements the OpenAI
# Responses API on the Micro VM port.  The Foundry platform forwards incoming
# agent requests to this server.  ``server.run()`` blocks until the process is
# terminated (SIGTERM from the platform on scale-in).
from agent_framework_foundry_hosting import ResponsesHostServer

# ``DefaultAzureCredential`` — tries, in order: env vars, workload identity,
# managed identity (IMDS), Azure CLI, VS Code, etc.
# Inside the Micro VM the relevant path is workload/managed identity (no CLI).
# During local debugging with the VS Code Foundry Toolkit, AzureCliCredential
# is the active leg.
# Docs: https://learn.microsoft.com/azure/developer/python/sdk/authentication-overview
from azure.identity import DefaultAzureCredential

# ``load_dotenv`` reads a local .env file (if present) into os.environ.
# In production the Micro VM injects env vars directly; .env is only used for
# local debugging.  The .env file is listed in .gitignore and .azdignore to
# prevent credential leaks.
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Tool-endpoint URLs and timeouts
# ---------------------------------------------------------------------------
# ``echo.tools.lab`` and ``ctrl.tools.lab`` are resolved by the lab's private
# DNS chain:
#   Micro VM → DNS Private Resolver inbound EP (192.168.3.4)
#            → outbound EP (192.168.3.20; SNAT pool 192.168.3.21–25 observed at dnsmasq)
#            → dnsmasq on vm-tools-echo (10.1.100.4:53)
#            → A records: echo → 10.1.100.4, ctrl → 10.1.200.4
#
# HTTP (not HTTPS): the echo service is a simple lab listener; no TLS is
# configured.  Production workloads should use HTTPS.
#
# Why FQDN instead of hard-coded IP: the FQDN appears verbatim in the target's
# ``request_url`` field, which is part of the lab evidence.  Using FQDNs also
# proves that DNS resolution works end-to-end from the Micro VM NIC.
_ECHO_URL = "http://echo.tools.lab/api/echo"
_CTRL_URL = "http://ctrl.tools.lab/api/echo"

# ``requests`` timeout is a 2-tuple: (connect_timeout, read_timeout) in seconds.
# connect=5s: time to establish TCP; generous for cross-VNet peering which is
# typically sub-millisecond, but allows for Micro VM cold-start latency.
# read=10s: time to receive the first byte after the TCP connection is open;
# the echo handler is trivially fast so this is a safety ceiling.
# Docs: https://docs.python-requests.org/en/latest/user/quickstart/#timeouts
_TIMEOUT = (5, 10)  # (connect_timeout, read_timeout) in seconds


def probe_echo() -> dict:
    """
    Probe the echo endpoint at ``echo.tools.lab`` and return the target JSON.

    **Network path (H2):** This call leaves the Micro VM via its dedicated NIC
    (an IP in AgentSubnet, e.g. 192.168.0.y), crosses the VNet peering to
    vnet-tools, and hits vm-tools-echo at 10.1.100.4.  The ``src_ip`` field in
    the response is the ground-truth source IP for H2 evidence.

    **Return shape** (from the echo service):
    .. code-block:: json

        {
          "label":       "echo",
          "server_ip":   "10.1.100.4",
          "src_ip":      "192.168.0.y",
          "request_url": "http://echo.tools.lab/api/echo"
        }

    The ``label`` distinguishes echo from ctrl in multi-call responses.
    The ``server_ip`` confirms the actual listener (not a load-balancer VIP).

    :raises requests.HTTPError: if the echo service returns a non-2xx status.
    :raises requests.ConnectionError: if the FQDN cannot be resolved or TCP fails.
    :raises requests.Timeout: if connect or read exceeds _TIMEOUT.

    Exceptions are intentionally *not* caught here.  The agent's system prompt
    instructs the LLM to report exception messages verbatim as lab evidence
    (unreachability is itself a meaningful result).
    """
    resp = requests.get(_ECHO_URL, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def probe_ctrl() -> dict:
    """
    Probe the echo endpoint at ``ctrl.tools.lab`` and return the target JSON.

    **Network path:** Same Micro VM NIC egress as ``probe_echo``, but the
    destination is vm-tools-ctrl at 10.1.200.4 (CtrlSubnet).  Both VMs run
    the same echo service; the separate VM lets the lab vary NSG rules or
    routes per-subnet while keeping the echo behaviour identical.

    **Return shape** (from the echo service):
    .. code-block:: json

        {
          "label":       "ctrl",
          "server_ip":   "10.1.200.4",
          "src_ip":      "192.168.0.y",
          "request_url": "http://ctrl.tools.lab/api/echo"
        }

    The ``src_ip`` on both echo and ctrl responses should be the *same* Micro VM
    NIC IP (hypothesis: the Micro VM uses one NIC for all outbound code calls).
    If they differ, that is a lab finding worth recording.

    :raises requests.HTTPError: if the ctrl service returns a non-2xx status.
    :raises requests.ConnectionError: if the FQDN cannot be resolved or TCP fails.
    :raises requests.Timeout: if connect or read exceeds _TIMEOUT.
    """
    resp = requests.get(_CTRL_URL, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def main():
    """
    Build the agent, attach tools, and start the Responses API hosting loop.

    This function is the entry point for the Micro VM process.  It:
    1. Reads configuration from environment variables (injected by Foundry or
       .env for local debugging).
    2. Creates a ``FoundryChatClient`` authenticated with ``DefaultAzureCredential``.
    3. Defines an ``Agent`` with a strict system prompt and registers the two
       probe functions as callable tools.
    4. Wraps the agent in ``ResponsesHostServer`` and blocks on ``server.run()``.

    The function raises ``RuntimeError`` if the model deployment name is not set,
    which prevents a silent misconfiguration from deploying a broken agent.
    """
    model_name = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME") or os.getenv("FOUNDRY_MODEL_NAME")
    if not model_name:
        raise RuntimeError(
            "Model deployment name is not configured. "
            "Set AZURE_AI_MODEL_DEPLOYMENT_NAME or FOUNDRY_MODEL_NAME."
        )

    # ``FoundryChatClient`` combines the Foundry project endpoint with a live
    # credential.  The project endpoint format is:
    #   https://<account>.services.ai.azure.com/api/projects/<project>
    # ``DefaultAzureCredential`` acquires an access token for
    # https://ai.azure.com/.default automatically; tokens are cached and
    # refreshed by the SDK before expiry.
    #
    # Why not ``AIProjectClient`` directly?  FoundryChatClient is the MAF-native
    # adapter and handles the chat-completion loop (tool-call ↔ tool-result
    # message exchange) transparently.
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=model_name,
        credential=DefaultAzureCredential(),
    )

    # ``Agent`` combines the LLM client, system instructions, and a list of
    # callable Python functions (tools).  MAF inspects each function's type
    # annotations and docstring to generate the JSON Schema tool definition
    # that is sent to the model in the API request.
    #
    # System prompt design notes:
    # - "call probe_echo() and probe_ctrl()" — explicit function names prevent
    #   the LLM from hallucinating tool names.
    # - "return ALL of the following fields" — forces complete field coverage;
    #   the LLM would otherwise summarise or omit fields it judges redundant.
    # - "exact values are required for lab evidence" — steers away from prose
    #   paraphrase; the echo service values are the raw measurement output.
    # - Exception verbatim reporting — network unreachability is itself a
    #   meaningful lab result (e.g. NSG blocking, DNS failure, no peering).
    agent = Agent(
        client=client,
        instructions=(
            "You are echo-probe-agent. When asked to probe the echo endpoints, call "
            "probe_echo() and probe_ctrl() and return ALL of the following fields from "
            "each target's JSON response: label, server_ip (the target listener IP), "
            "src_ip (the source IP seen by the target), and request_url (the originally "
            "dialed URL including host header). "
            "Present the results as a table with one row per target. "
            "Do not omit or summarise fields -- exact values are required for lab evidence. "
            "If a tool call raises an exception, report the exception message verbatim -- it "
            "means the lab network is not yet reachable from this endpoint."
        ),
        tools=[probe_echo, probe_ctrl],
        # ``store=False`` disables conversation-history persistence on the
        # Foundry side.  Each invocation is stateless: the caller sends the
        # full message and receives the full response in one round trip.
        # This is correct for a lab probe agent that does not need multi-turn
        # context; it also avoids thread/run management overhead.
        default_options={"store": False},
    )

    # ``ResponsesHostServer`` wraps the Agent in an HTTP server that speaks
    # the OpenAI Responses API protocol.  Foundry routes incoming POST requests
    # to this server inside the Micro VM network namespace.  ``run()`` blocks
    # until the process is terminated (SIGTERM on scale-in or redeploy).
    #
    # Alternative: streaming responses (``"stream": true`` from the caller).
    # This server supports both modes; the lab callers use non-streaming for
    # simplicity.
    server = ResponsesHostServer(agent)
    server.run()


if __name__ == "__main__":
    main()