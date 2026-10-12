# Azure Function dependency-path extension — 2026-10-12

## Test target

- Function: `https://func-deppath-kpo2.azurewebsites.net/api/dependency-probe`
- Function private endpoint: `192.168.1.27` in `PESubnet`
- Private DNS zone: `privatelink.azurewebsites.net`, linked to `vnet-foundry`
- Agent subnet: `192.168.0.0/24`
- Model: `gpt-5-mini` version `2025-08-07`
- Prompt registered path: `dependency-openapi-prompt:1`
- Hosted registered path: `echo-probe-agent:2` + `dependency-path-toolbox:1`
- Hosted direct path: `echo-probe-agent:2` local DNS/TLS/HTTPS Python tools

The Function returns the target-observed `X-Forwarded-For` chain, request URL, and user agent.
Hosted direct code also records its DNS answer, selected TCP peer, TLS version, HTTP status, and
duration.

## Results

| Phase | Path | DNS / selected peer | Target-observed final caller | HTTP result |
|---|---|---|---|---|
| Public control, no Function PE | Prompt registered OpenAPI | Public App Service frontend | `74.241.192.111:40768` (`azure-agents`) | 200 |
| Public control, no Function PE | Hosted registered Toolbox | Public App Service frontend | `74.241.193.90:56640` (`azure-agents`) | 200 |
| Public control, no Function PE | Hosted direct Python | `51.12.31.6` | `20.91.215.167:31299` (`python-requests`) | 200 |
| Function PE present, public access enabled | Prompt registered OpenAPI | Private Endpoint path | `192.168.0.99` (`azure-agents`) | 200 |
| Function PE present, public access enabled | Hosted registered Toolbox | Private Endpoint path | `192.168.0.99` (`azure-agents`) | 200 |
| Function PE present, public access enabled | Hosted direct Python | DNS + TCP peer `192.168.1.27` | `192.168.0.138` (`python-requests`) | 200 |
| Full lockdown: Function PE present, public access disabled | Workstation control | Public App Service frontend | Workstation public path | **403 Ip Forbidden** |
| Full lockdown | Prompt registered OpenAPI | Private Endpoint path | `192.168.0.80`, repeat `192.168.0.99` (`azure-agents`) | **200, 200** |
| Full lockdown | Hosted registered Toolbox | Private Endpoint path | `192.168.0.99`, repeat `192.168.0.99` (`azure-agents`) | **200, 200** |
| Full lockdown | Hosted direct Python | DNS + TCP peer `192.168.1.27` | `192.168.0.138`, repeat `192.168.0.138` (`python-requests`) | **200, 200** |

For registered tools, `X-Forwarded-For` also contained service-internal `100.100.x.x` and
`100.64.x.x` hops. The final address in the chain is the network executor presented to the Function:
the public Tools Service egress in the no-PE control, or the AgentSubnet data-proxy address after
the Private DNS zone was linked.

## Findings

1. **Prompt and hosted registered tools behaved identically.** Both used the Foundry Tools
   Service/data proxy, the VNet-linked Function private DNS zone, and the Function Private Endpoint.
2. **Hosted direct Python used a distinct executor.** It resolved the same private IP but reached
   the Function from the Micro VM NIC (`192.168.0.138`) rather than the data proxy.
3. **Full Function lockdown succeeded for all managed VNet paths.** Disabling public access blocked
   the workstation with `403 Ip Forbidden` but did not block prompt OpenAPI, hosted Toolbox, or
   hosted direct Python.
4. **The broad sample conclusion is not reproducible in this current configuration.** The
   `19-private-network-agent-tools` account capability host, AgentSubnet injection, and linked
   `privatelink.azurewebsites.net` zone allowed the data proxy to use the Function Private
   Endpoint. A `403` remains the expected symptom when an executor resolves or routes to the public
   frontend after public access is disabled, but it is not an inherent data-proxy limitation.

## Evidence files

- Public prompt registered:
  [`dependency-public-prompt-20261012.json`](dependency-public-prompt-20261012.json)
- Public hosted Toolbox:
  [`dependency-public-hosted-toolbox-20261012.txt`](dependency-public-hosted-toolbox-20261012.txt)
- PE/public prompt registered:
  [`dependency-pe-public-prompt-20261012-r3.json`](dependency-pe-public-prompt-20261012-r3.json)
- PE/public hosted Toolbox:
  [`dependency-pe-public-hosted-toolbox-20261012.txt`](dependency-pe-public-hosted-toolbox-20261012.txt)
- PE/public hosted direct:
  [`dependency-pe-public-hosted-direct-20261012.txt`](dependency-pe-public-hosted-direct-20261012.txt)
- Lockdown prompt registered:
  [`dependency-lockdown-prompt-20261012.json`](dependency-lockdown-prompt-20261012.json),
  [`dependency-lockdown-prompt-20261012-r2.json`](dependency-lockdown-prompt-20261012-r2.json)
- Lockdown hosted Toolbox:
  [`dependency-lockdown-hosted-toolbox-20261012.txt`](dependency-lockdown-hosted-toolbox-20261012.txt),
  [`dependency-lockdown-hosted-toolbox-20261012-r2.txt`](dependency-lockdown-hosted-toolbox-20261012-r2.txt)
- Lockdown hosted direct:
  [`dependency-lockdown-hosted-direct-20261012.txt`](dependency-lockdown-hosted-direct-20261012.txt),
  [`dependency-lockdown-hosted-direct-20261012-r2.txt`](dependency-lockdown-hosted-direct-20261012-r2.txt)
