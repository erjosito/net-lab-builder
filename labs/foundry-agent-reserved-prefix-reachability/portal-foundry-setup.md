# Portal Foundry Setup — foundry-agent-reserved-prefix-reachability
**Author:** Tank (IaC Engineer) · 2026-08-14  
**Pre-condition:** `deploy.ps1 -Apply` has completed successfully and outputs are available.

---

## Purpose

This document guides Jose through creating the Microsoft Foundry resource manually in the Azure portal.
The IaC (`deploy/main.bicep`) creates all supporting infrastructure (VNets, VPN gateways, private DNS zones,
BYO dependencies) but explicitly omits Foundry account creation so Jose can learn the portal flow.

**What IaC created (your handoff values):**

Run `az deployment group show -g <rg-name> -n deploy-foundry-<corrID> --query properties.outputs` to retrieve
exact values. Key values printed by `deploy.ps1 -Apply`:

| Item | Value |
|------|-------|
| Resource group | `rg-foundry-reserved-<correlationId>` |
| Region | `swedencentral` |
| VNet | `vnet-foundry` (192.168.0.0/16) |
| AgentSubnet ID | (output: `agentSubnetId`) |
| PESubnet ID | (output: `peSubnetId`) |
| Storage account | (output: `storageAccountName`) |
| AI Search | (output: `searchServiceName`) |
| Cosmos DB | (output: `cosmosAccountName`) |

---

## Step 1 — Navigate to Foundry

1. Open [portal.azure.com](https://portal.azure.com).
2. Search for **Foundry**.
3. Select **Create a resource**.

---

## Step 2 — Basics tab

| Field | Value |
|-------|-------|
| Subscription | *(your subscription)* |
| Resource group | `rg-foundry-reserved-<correlationId>` (same RG as IaC resources) |
| Name | Any unique name, e.g. `foundry-lab-<corrID>` |
| Region | **swedencentral** (must match VNet region) |

---

## Step 3 — Storage / Dependencies tab

The wizard has a tab for **Agent service** resources (labelled "Storage", "Agent service", or similar depending on
portal version). On this tab:

1. Select **Use existing** for each BYO dependency.
2. Map as follows:

| Foundry field | Select existing resource |
|--------------|--------------------------|
| Storage account | `stlab…` (output: `storageAccountName`) |
| Azure AI Search | `srch-lab-…` (output: `searchServiceName`) |
| Azure Cosmos DB | `cosmos-lab-…` (output: `cosmosAccountName`) |

If the three existing-resource selectors aren't available, stop rather than accepting auto-created
dependencies. VNet injection with end-to-end isolation requires the existing Storage, AI Search, and Cosmos DB
resources created by this lab.

---

## Step 4 — Networking tab

### Public network access
Set to **Disabled**.

### Private endpoint
Click **+ Add private endpoint**:

| Field | Value |
|-------|-------|
| Name | `pe-foundry-account` |
| Region | `swedencentral` |
| Target sub-resource | `account` |
| Virtual network | `vnet-foundry` |
| Subnet | `PESubnet` (192.168.1.0/24) |
| Integrate with private DNS zone | **Yes** |
| DNS zone for `privatelink.cognitiveservices.azure.com` | Select the pre-created zone `privatelink.cognitiveservices.azure.com` |
| DNS zone for `privatelink.openai.azure.com` | Select the pre-created zone `privatelink.openai.azure.com` |
| DNS zone for `privatelink.services.ai.azure.com` | Select the pre-created zone `privatelink.services.ai.azure.com` |

> 💡 The portal may prompt for multiple sub-resources or offer multiple DNS zone fields. Select all three
> pre-created zones. If `privatelink.services.ai.azure.com` is not shown as a field in this portal release,
> the zone can be linked manually post-creation.

---

## Step 5 — Virtual network injection (AgentSubnet)

Look for a **Virtual network** or **Network injection** section in the Networking tab (may appear as a separate tab
depending on portal version):

| Field | Value |
|-------|-------|
| Virtual network | `vnet-foundry` |
| Subnet | `AgentSubnet` (192.168.0.0/24) |

`AgentSubnet` is pre-delegated to `Microsoft.App/environments` — this is the correct delegation for Foundry
VNet injection. If the portal rejects the subnet delegation, verify:
```bash
az network vnet subnet show -g <rg> --vnet-name vnet-foundry -n AgentSubnet \
  --query 'delegations[].serviceName'
# Expected: ["Microsoft.App/environments"]
```

---

## Step 6 — Role assignments

The Foundry creation wizard assigns the required permissions to the Foundry managed identity on the BYO
dependencies. You need permission to create role assignments, typically **Owner** or **User Access
Administrator** at the resource-group scope. Accept the wizard's requested assignments. If assignment fails,
stop and use the specific error details; Cosmos DB data-plane roles aren't managed through the same IAM blade
as ordinary Azure RBAC roles.

---

## Step 7 — Review + Create

Review the summary. Click **Create**. Foundry account provisioning typically takes 5–15 minutes.

### Portal access after creation

With public network access disabled, your workstation must have private connectivity to `vnet-foundry` to use
Foundry data-plane experiences. The baseline IaC doesn't configure point-to-site VPN.

Choose one:

1. Keep public network access enabled only while creating the model and prompt agent, then disable it before
   S3/S4. This doesn't change the agent's outbound route through AgentSubnet, but it temporarily relaxes inbound
   isolation.
2. Extend the lab with point-to-site VPN on `vpngw-foundry`, connect your workstation, and keep public access
   disabled throughout.

Do not begin S3/S4 until public network access is disabled and the Foundry private endpoint resolves privately.

---

## Step 8 — Create a Prompt Agent

After the Foundry account is created:

1. Open the Foundry resource → **Agents** (left menu).
2. Click **+ New agent**, select **Prompt agent** (NOT Hosted agent — Hosted agent requires ACR and a
   container image, which are not part of this lab).
3. Select the Azure OpenAI model deployment (`gpt-4o-mini` or fallback; deploy the model in the
   **Models + endpoints** section first if not already done).

---

## Step 9 — Deploy the OpenAI Model

In the Foundry portal:

1. Go to **Models + endpoints** → **+ Deploy model**.
2. Select **gpt-4o-mini** (Standard deployment, swedencentral).
3. Note the **deployment name** — you will use it in the agent tool definition.

---

## Step 10 — Add the Echo Tools to the Agent

In the prompt agent definition, add two **OpenAPI tools** using anonymous authentication:

| Tool | OpenAPI document |
|------|------------------|
| S3 control | `agent-tools/echo-control.openapi.json` |
| S4 reserved-prefix probe | `agent-tools/echo-reserved.openapi.json` |

Upload or paste each complete OpenAPI document. The validated definitions use HTTPS on port 443.

---

## ⚠️ TLS / Certificate Note

The on-premises VMs (`vm-onprem-echo`, `vm-onprem-ctrl`) expose HTTPS on port 443 using self-signed
certificates. Both endpoints were successfully invoked by Foundry on 2026-08-14. This is useful lab evidence,
but Microsoft Learn doesn't document it as a trust-store guarantee. Production endpoints should still use a
certificate and hostname that meet the organization's supported TLS policy.

---

## Step 11 — Verify VPN connectivity before running agent

Before running agent experiments, verify the data plane is working:

```bash
# From vm-diag (Azure Run Command):
az vm run-command invoke -g <rg> -n vm-diag \
  --command-id RunShellScript \
  --scripts "curl -s 'http://172.30.100.4/api/echo?msg=diag-probe'"

az vm run-command invoke -g <rg> -n vm-diag \
  --command-id RunShellScript \
  --scripts "curl -s 'http://10.200.100.4/api/echo?msg=diag-ctrl'"
```

Both should return JSON. If either fails, check VPN gateway status and effective routes before running S3/S4.

```bash
# Check vpngw-foundry learned routes (should include 172.30.0.0/16 and 10.200.100.0/24)
az network vnet-gateway list-learned-routes -g <rg> -n vpngw-foundry -o table

# Check effective routes on vm-diag NIC (proxy for vnet-foundry route table)
az network nic show-effective-route-table -g <rg> -n nic-vm-diag -o table
```

---

## Step 12 — Run S3 and S4

**S3 (control — non-reserved):**
```
Call the echo-control tool with message "probe-control". Report the full response verbatim.
```
Expected: `{"echo":"probe-control","label":"ctrl","server_ip":"10.200.100.4","request_url":"https://10.200.100.4/api/echo?msg=probe-control","ts":"…","src_ip":"…"}`

**S4 (primary — reserved prefix):**
```
Call the echo-reserved tool with message "probe-reserved". Report the full response verbatim.
```
Outcome unknown. Capture the full response or error message.

**Evidence to collect for each run:**
- Agent run JSON (tool call result, HTTP status, success/failure)
- `tcpdump -i eth0 -n port 443` output from the target VM (via Run Command) — did a TCP SYN arrive?
- Effective routes on `nic-vm-diag` confirming `172.30.0.0/16` is present

---

## Post-Lab Cleanup

```powershell
.\cleanup.ps1 -RgName rg-foundry-reserved-<corrID> -AutoApprove
```

If PSK was stored in Key Vault, add `-KvName <kv> -CorrelationId <corrID>`.
