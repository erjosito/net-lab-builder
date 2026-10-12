"""HTTP dependency used to compare Foundry registered-tool and direct-code paths.

The same anonymous HTTPS endpoint is called in three ways:

1. A prompt agent invokes a Foundry-registered OpenAPI tool.
2. A hosted agent invokes a Foundry-registered tool through the Tools Service.
3. Hosted-agent Python calls the URL directly with ``requests``.

The response deliberately includes the source-address headers added by the
Azure Functions front end. This makes the target, rather than the caller, the
source of truth for which network executor reached it.

Azure Functions Python programming model v2 reference:
https://learn.microsoft.com/azure/azure-functions/functions-reference-python

App Service request-routing and source-IP behavior:
https://learn.microsoft.com/azure/app-service/overview-inbound-outbound-ips
"""

import json
from datetime import datetime, timezone

import azure.functions as func

# Anonymous auth is intentional for this isolated lab endpoint. Authentication
# would add another variable (Function keys or Entra token acquisition) to a
# test whose purpose is DNS, TCP, TLS, and HTTP path selection.
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


def _split_forwarded_for(value: str) -> list[str]:
    """Return the ordered X-Forwarded-For hop list without empty entries.

    Reverse proxies append addresses as a comma-separated chain. The left-most
    value is normally the original client observed by the first trusted proxy,
    while later entries represent proxy hops. We return both the raw header and
    this parsed list so the report does not depend on one interpretation.
    """

    return [item.strip() for item in value.split(",") if item.strip()]


@app.route(route="dependency-probe", methods=["GET"])
def dependency_probe(req: func.HttpRequest) -> func.HttpResponse:
    """Return target-observed network metadata for one HTTPS request.

    ``req.url`` and ``Host`` show which public hostname the caller dialed.
    ``X-Forwarded-For`` is the best target-side evidence for the originating
    data-proxy or Micro VM address after the App Service front end terminates
    TLS. Selected Azure headers are retained for troubleshooting, but no
    authorization, cookie, or arbitrary user headers are echoed.
    """

    forwarded_for = req.headers.get("x-forwarded-for", "")
    payload = {
        "label": "function-dependency",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "method": req.method,
        "request_url": req.url,
        "host": req.headers.get("host"),
        "forwarded_for_raw": forwarded_for,
        "forwarded_for": _split_forwarded_for(forwarded_for),
        "azure_client_ip": req.headers.get("x-azure-clientip"),
        "azure_socket_ip": req.headers.get("x-azure-socketip"),
        "forwarded_proto": req.headers.get("x-forwarded-proto"),
        "request_id": req.headers.get("x-azure-ref")
        or req.headers.get("x-request-id"),
        "user_agent": req.headers.get("user-agent"),
    }

    return func.HttpResponse(
        json.dumps(payload, sort_keys=True),
        status_code=200,
        mimetype="application/json",
    )
