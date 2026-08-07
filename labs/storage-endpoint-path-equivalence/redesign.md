# PaaS redesign — endpoint path equivalence

**Date:** 2026-08-06
**Status:** Approved and deployed; Niobe handoff ready; no cleanup performed

## Decision

Use **Azure AI Translator**, `Microsoft.CognitiveServices/accounts` kind
`TextTranslation`, **F0**, in `swedencentral`.

It is the cheapest policy-compatible service found that supports all three required
states against one custom FQDN:

1. ordinary authenticated public endpoint;
2. classic `Microsoft.CognitiveServices` service endpoint plus a subnet rule, while
   DNS and the destination remain public; and
3. Private Endpoint, where the same custom FQDN resolves to a private address.

Use the VM's managed identity with the `Cognitive Services User` role. Local keys
remain disabled, as required by policy.

## Candidate and policy evidence

The active management-group assignments were read from the subscription's actual
hierarchy. `MCAPSGovDenyPolicies`, `MCAPSGovDeployPolicies`, and
`MCAPSGovAuditPolicies` are enforced in `Default` mode.

| Candidate | Service/PE support | Active policy result | Cost/result |
|---|---|---|---|
| Blob Storage | Yes | `StorageAccount_PublicNetwork_Modify` replaces public access with `Disabled` | Rejected: ordinary public and SE states cannot persist |
| Azure SQL Database | Yes | `AzureSQL_PublicNetwork_Modify` replaces public access with `Disabled`; Entra-only authentication is also denied unless configured | Rejected |
| Key Vault | Yes | `KeyVault_PublicNetwork_Modify` replaces public access with `Disabled` | Rejected |
| Cosmos DB | Yes | `CosmosDB_PublicNetwork_Modify` replaces public access with `Disabled` | Rejected |
| Event Hubs Standard | Yes; Basic explicitly lacks SE/PE | Only local authentication is modified off; public access is not forced off | Viable, but 1 TU is US$0.03/hour plus PE |
| Service Bus Premium | Yes; Premium required | Only local authentication is modified off | Viable, but about US$0.9275/hour plus PE |
| Container Registry Premium | Yes | No applicable public-access modify found | Viable but about US$0.0694/hour plus PE and less clean request semantics |
| App Service | Yes | No applicable public-access modify found | Viable but requires an App Service plan and application deployment |
| **Azure AI Translator F0** | **Yes** | `CognitiveServices_LocalAuth_Modify` sets `disableLocalAuth=true`; `CognitiveServices_Diagnostics_Enable` deploys diagnostics. No active policy forces public access off. | **Selected: no service hourly charge within F0 allowance; PE US$0.01/hour** |

Subscription SKU discovery returned unrestricted `F0` and `S1` Translator SKUs in
`swedencentral`. The deny initiative does not prohibit
`Microsoft.CognitiveServices/accounts`. F0 availability is not permission to fall
back silently: if deployment validation later reports a free-tier quota or PE
restriction, stop and request approval for S1.

First-party documentation confirms that:

- classic service endpoints retain public DNS addresses, install
  `VirtualNetworkServiceEndpoint` routes, and switch service-observed source identity
  to the subnet/private address;
- Foundry Tools support subnet rules through `Microsoft.CognitiveServices` service
  endpoints and Private Endpoints using the same custom endpoint;
- Translator supports Microsoft Entra bearer-token authentication against its custom
  domain; and
- service endpoints have no separate charge.

References:
[service endpoints](https://learn.microsoft.com/azure/virtual-network/virtual-network-service-endpoints-overview),
[Foundry Tools networking](https://learn.microsoft.com/azure/ai-services/cognitive-services-virtual-networks),
[Translator Entra authentication](https://learn.microsoft.com/azure/ai-services/translator/how-to/microsoft-entra-id-auth),
and [Private Endpoint pricing](https://azure.microsoft.com/pricing/details/private-link/).

## Reused topology and resource delta

Retain the resource group, VM, disk, NIC, VNet, both subnets, NAT Gateway/PIP, NSG,
Log Analytics workspace, flow-log account, and VNet flow logging.

**Remove after approval:** two experiment Storage accounts and their containers,
blobs, diagnostic settings, and data-role assignments; the Storage endpoint policy;
the Blob PE/NIC and zone group; and the Blob private DNS zone. The flow-log Storage
account remains. Policy-created security/diagnostic children are not modified
directly; they disappear only with an approved parent-resource deletion.

**Add after approval:** one F0 Translator account with a custom subdomain, one
Translator PE/NIC reusing the PE subnet and `10.61.2.4`, one corresponding private
DNS zone/link/zone group, one Log Analytics diagnostic setting, and one
`Cognitive Services User` assignment for the existing VM identity. Change the
client subnet endpoint from `Microsoft.Storage` to `Microsoft.CognitiveServices`
and replace the NSG Storage destination with the documented nonregional
`CognitiveServicesFrontend` service tag.

Net resource shape: **remove 2 PaaS accounts; add 1 PaaS account; replace, rather
than increase, the single PE and private DNS path.**

## Revised scenarios

Use one fixed, small translation request against the unchanged custom FQDN. Acquire
tokens from IMDS for `https://cognitiveservices.azure.com/`; never use keys.

| Scenario | PASS gate |
|---|---|
| **R1 Public control** | SE off, private zone unlinked, public access allowed; custom FQDN resolves/captures a public address, effective next hop is not `VirtualNetworkServiceEndpoint`, and the Entra-authenticated request succeeds |
| **R2 Service-endpoint route** | Enable only `Microsoft.CognitiveServices`; same FQDN and pinned live public IP remain, request succeeds, and effective next hop changes to `VirtualNetworkServiceEndpoint` |
| **R3 Subnet authorization** | Change the account to selected networks with the client subnet rule; the VM request succeeds, then removing only that subnet rule makes the identical VM/principal request fail; restore the rule before continuing |
| **R4 Private Endpoint** | Disable SE for isolation, link private DNS, flush sockets/DNS; same FQDN resolves/captures `10.61.2.4`, route is VNet-local, and the request succeeds |
| **R5 Exposure negative control** | With public access disabled, a TLS/SNI-preserving forced-public request fails while the ordinary private-DNS request succeeds |

Collect DNS, packet destination, effective routes, account networking state, HTTP
status/request IDs, and available diagnostics. As before, this proves observable
route and authorization differences, not Microsoft physical-path identity.

## Cost, timing, teardown, and limitations

- **Added fixed cost:** Translator F0 US$0/hour within its allowance; one PE
  US$0.01/hour. Because the currently deployed Blob PE is replaced, the steady-state
  fixed delta versus the live lab is approximately **US$0/hour**. Temporary overlap,
  if used, is US$0.01/hour.
- **Usage/logging:** keep the run below 5,000 very small requests. F0 request usage is
  expected to remain free; Log Analytics and network data are low-volume. No paid
  S1 fallback is authorized.
- **Estimated deployment delta:** 10–20 minutes, plus up to 10 minutes for RBAC,
  policy diagnostics, DNS, and endpoint convergence.
- **Total lab run rate:** remains approximately the existing US$0.15–0.30/hour.
- **Teardown:** still delete the single tagged resource group after the separate
  cleanup gate. No new cross-resource dependency changes that order.
- **Limitations:** F0 throttling prevents the former concurrency 8/32 and 8-MiB
  throughput program. Restrict performance work to randomized, low-rate, small-body
  latency/connection observations. Translator processing latency can dominate the
  network delta, so correctness evidence is primary and performance equivalence may
  be inconclusive. No service-endpoint-policy decoy test exists for this service.

## Exact Phase 4 delta approval required

Approve **all** of the following as one bounded delta:

1. delete the two experiment Storage accounts and Storage-specific PE/DNS/endpoint
   policy artifacts listed above, while retaining the flow-log account;
2. create one F0 Translator account, replacement PE/private DNS path, one diagnostic
   setting, and one least-privilege VM identity role assignment;
3. change the client subnet/NSG from Storage to Cognitive Services endpoint tags;
4. permit the five revised scenarios, including temporary public access and the R5
   public-access disable/restore transition; and
5. accept a maximum added fixed cost of US$0.01/hour during any PE overlap, no paid
   SKU fallback, and a 10–20 minute deployment delta.

No deployment, deletion, exemption, tag bypass, policy change, or other billable
operation is authorized by this document.
