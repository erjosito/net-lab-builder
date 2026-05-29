# src/ — Shared Infrastructure as Code & Scripts

> Reusable IaC modules and operational scripts shared across all labs. Lab-specific overrides live under `labs/<lab>/deploy/`.

Owned by **Tank**. Consumed by Tank, Trinity, and Niobe.

## Layout

```
src/
├── bicep/         # Bicep modules (preferred for green-field Azure-only labs)
├── terraform/     # Terraform modules (multi-cloud / Megaport — ER labs that need the Megaport provider)
├── azure-cli/     # az-cli shell scripts (Bash / PowerShell wrappers around `az ...`)
└── powershell/    # Pure PowerShell (Az.* cmdlets, AzAPI calls, Windows VM bootstrap)
```

### When to use which

| Tool          | Use for                                                                              |
|---------------|--------------------------------------------------------------------------------------|
| **Bicep**     | Azure-only resource topology, ARM-native features, fast iteration                    |
| **Terraform** | Multi-provider labs (Megaport + Azure), state-tracked teardown, module reuse         |
| **Azure CLI** | One-shot diagnostics, post-deploy configuration, low-ceremony glue scripts           |
| **PowerShell**| Windows-side bootstrap, AzAPI calls for preview features not yet in Bicep/TF         |

## Conventions

- **Never hardcode subscription or tenant IDs** (routing rule #10). Resolve at runtime: `--subscription` flag → `$AZURE_SUBSCRIPTION_ID` → `az account show --query id -o tsv`.
- **Never commit secrets** (routing rule #11). Megaport API keys and similar live in the user's Key Vault (`platform-secrets-1138`); fetch at deploy time via `az keyvault secret show`.
- **Parameterize everything.** No magic strings for region, SKU, address space, or VM size — all overridable from `labs/<lab>/deploy/`.
- **SKU defaults** (diagnostic plumbing only — workload VMs follow Morpheus's no-A / no-B rule):
  - Linux jump VM: `Standard_B1s`, Ubuntu 22.04 LTS Gen2, 30 GB Standard SSD
  - ER circuit: 50 Mbps Standard MeteredData
  - ER gateway: `Standard`
  - VPN gateway: `VpnGw1`
  - Megaport MCR: 1000 Mbps, 1-month term

## ExpressRoute cleanup discipline

ExpressRoute labs MUST tear down in this order or risk 30–40 minute hangs and HTTP 409 errors:

1. Azure ER connection (gateway-side)
2. Azure ER circuit private peering
3. Megaport VXC(s)
4. Megaport MCR
5. Azure resource group (last)

See `.squad/agents/tank/charter.md` for the full cleanup chain, IaC patterns, and Megaport-specific gotchas.
