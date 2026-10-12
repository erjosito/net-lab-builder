"""Create the registered OpenAPI paths used by the dependency networking test.

This script creates two Foundry resources from the same OpenAPI document:

* ``dependency-openapi-prompt`` is a prompt agent whose OpenAPI tool is executed
  by the Foundry Tools Service/data proxy.
* ``dependency-path-toolbox`` stores the same OpenAPI tool for consumption by
  the hosted agent through ``FoundryToolbox``.

Keeping the specification identical removes API-shape differences from the
comparison. Only the requesting agent and execution path change.

SDK references:
https://learn.microsoft.com/azure/foundry/agents/how-to/tools/openapi
https://learn.microsoft.com/azure/foundry/agents/how-to/tools/toolbox
"""

import argparse
import json
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    OpenApiAnonymousAuthDetails,
    OpenApiFunctionDefinition,
    OpenApiTool,
    OpenApiToolboxTool,
    PromptAgentDefinition,
)
from azure.identity import AzureCliCredential

DEFAULT_PROJECT_ENDPOINT = (
    "https://fndrydepkpo2.services.ai.azure.com/api/projects/dependencykpo2"
)
DEFAULT_MODEL = "gpt-5-mini"
PROMPT_AGENT_NAME = "dependency-openapi-prompt"
TOOLBOX_NAME = "dependency-path-toolbox"


def load_spec() -> dict:
    """Load the one checked-in OpenAPI document used by both registered paths."""

    spec_path = (
        Path(__file__).resolve().parent.parent
        / "dependency-function"
        / "openapi.json"
    )
    return json.loads(spec_path.read_text(encoding="utf-8"))


def create_resources(project: AIProjectClient, spec: dict, model: str) -> dict:
    """Create new immutable versions of the toolbox and prompt agent."""

    auth = OpenApiAnonymousAuthDetails()
    definition = OpenApiFunctionDefinition(
        name="dependency_probe",
        spec=spec,
        description=(
            "Call the Azure Function dependency probe and return all target-observed "
            "network metadata without summarizing fields."
        ),
        auth=auth,
    )

    toolbox = project.toolboxes.create_version(
        name=TOOLBOX_NAME,
        description=(
            "Registered OpenAPI Function used to compare hosted Toolbox/data-proxy "
            "egress with hosted direct Python egress."
        ),
        tools=[OpenApiToolboxTool(openapi=definition)],
    )

    prompt_agent = project.agents.create_version(
        agent_name=PROMPT_AGENT_NAME,
        definition=PromptAgentDefinition(
            model=model,
            instructions=(
                "Always call dependency_probe.probeDependencyPath. Return the complete "
                "raw response object and do not omit source-address or URL fields."
            ),
            tools=[OpenApiTool(openapi=definition)],
        ),
    )

    return {
        "toolbox": {
            "name": toolbox.name,
            "version": str(toolbox.version),
        },
        "prompt_agent": {
            "name": prompt_agent.name,
            "version": str(prompt_agent.version),
        },
    }


def invoke_prompt_agent(project: AIProjectClient, agent_name: str) -> dict:
    """Invoke the registered OpenAPI prompt agent through the Responses API."""

    with project.get_openai_client() as openai:
        conversation = openai.conversations.create()
        response = openai.responses.create(
            conversation=conversation.id,
            input=(
                "Call the dependency probe now. Return every field from the raw "
                "registered-tool response."
            ),
            # The model occasionally answers with "I will call..." without
            # executing the sole registered tool. Requiring a tool call removes
            # that nondeterminism from a network test.
            tool_choice="required",
            extra_body={
                "agent_reference": {
                    "name": agent_name,
                    "type": "agent_reference",
                }
            },
        )
        return response.model_dump(mode="json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-endpoint", default=DEFAULT_PROJECT_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--reuse-existing",
        action="store_true",
        help="Invoke the existing prompt agent without creating new versions.",
    )
    args = parser.parse_args()

    credential = AzureCliCredential()
    with AIProjectClient(
        endpoint=args.project_endpoint,
        credential=credential,
    ) as project:
        resources = (
            {
                "toolbox": {"name": TOOLBOX_NAME, "version": "1"},
                "prompt_agent": {"name": PROMPT_AGENT_NAME, "version": "1"},
            }
            if args.reuse_existing
            else create_resources(project, load_spec(), args.model)
        )
        response = invoke_prompt_agent(
            project,
            resources["prompt_agent"]["name"],
        )

    toolbox = resources["toolbox"]
    result = {
        "resources": resources,
        "toolbox_endpoint": (
            f"{args.project_endpoint}/toolboxes/{toolbox['name']}"
            f"/versions/{toolbox['version']}/mcp?api-version=v1"
        ),
        "prompt_response": response,
    }

    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
