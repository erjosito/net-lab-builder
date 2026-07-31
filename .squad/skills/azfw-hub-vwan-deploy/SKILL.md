# SKILL: Deploy Azure Firewall (AZFW_Hub) into a vWAN Secured Hub via CLI

**Author:** Tank  
**Created:** 2026-07-30  
**Applies to:** Any lab deploying Azure Firewall Standard into a Virtual WAN hub (secured hub pattern)

---

## Pattern Summary

Deploy one or more `AZFW_Hub` firewalls into vWAN virtual hubs via Azure CLI, with a shared firewall policy, in parallel using `--no-wait` + polling. Cleanup in firewall-before-policy order.

---

## Prerequisites Check (always run first)

```bash
RG=<resource-group>
HUB=<hub-name>

# Confirm only defaultRouteTable + noneRouteTable (no custom tables that block RI later)
az network vhub route-table list -g $RG --vhub-name $HUB -o table

# Confirm no custom static routes with VNetConnection nextHops
az network vhub route-table show -g $RG --vhub-name $HUB -n defaultRouteTable --query "routes" -o json
# If routes != [], STOP and investigate before proceeding.

# Save rollback snapshot (redact sub ID for repo safety)
az network vhub route-table show -g $RG --vhub-name $HUB -n defaultRouteTable -o json \
  | sed 's|/subscriptions/[^/]*/|/subscriptions/<SUBSCRIPTION_ID>/|g' \
  > hub-${HUB}-defaultRT-pre-deploy.json
```

---

## Step 1 — Firewall Policy

```bash
# Create policy (Standard is minimum tier for vWAN; Basic is NOT supported in vWAN hubs)
az network firewall policy create \
  -g $RG \
  -n <policy-name> \
  --location <region> \
  --sku Standard \
  -o none

# Create rule collection group
az network firewall policy rule-collection-group create \
  -g $RG \
  --policy-name <policy-name> \
  -n DefaultRuleCollectionGroup \
  --priority 100 \
  -o none

# Add allow-all network rule collection
# IMPORTANT: use --ip-protocols (not --protocols) for NetworkRule type
az network firewall policy rule-collection-group collection add-filter-collection \
  -g $RG \
  --policy-name <policy-name> \
  --rule-collection-group-name DefaultRuleCollectionGroup \
  -n allow-all-lab \
  --collection-priority 100 \
  --action Allow \
  --rule-name allow-all \
  --rule-type NetworkRule \
  --ip-protocols Any \
  --source-addresses '*' \
  --destination-addresses '*' \
  --destination-ports '*' \
  -o none
```

**Gotcha:** `--protocols` is for ApplicationRule (PROTOCOL=PORT format). For NetworkRule, use `--ip-protocols Any|TCP|UDP|ICMP`.

---

## Step 2 — Deploy Firewalls (parallel, --no-wait)

```bash
# Submit both in parallel — do NOT run serially; each takes 10–45 min
az network firewall create \
  -g $RG \
  -n <fw-name-1> \
  --location <region-1> \
  --sku AZFW_Hub \
  --tier Standard \
  --vhub <hub-name-1> \
  --public-ip-count 1 \
  --firewall-policy <policy-name> \
  --no-wait

az network firewall create \
  -g $RG \
  -n <fw-name-2> \
  --location <region-2> \
  --sku AZFW_Hub \
  --tier Standard \
  --vhub <hub-name-2> \
  --public-ip-count 1 \
  --firewall-policy <policy-name> \
  --no-wait

# Poll until both Succeeded
while true; do
  S1=$(az network firewall show -g $RG -n <fw-name-1> --query "provisioningState" -o tsv 2>/dev/null || echo "NotFound")
  S2=$(az network firewall show -g $RG -n <fw-name-2> --query "provisioningState" -o tsv 2>/dev/null || echo "NotFound")
  echo "[$(date '+%H:%M:%S')] fw1=$S1  fw2=$S2"
  [[ "$S1" == "Succeeded" && "$S2" == "Succeeded" ]] && break
  [[ "$S1" == "Failed" || "$S2" == "Failed" ]] && { echo "FAILURE — stop and report"; exit 1; }
  sleep 120
done
```

**Key notes:**
- `Start-Job` in PowerShell does NOT persist across fresh shell processes — always use `--no-wait` for parallelism.
- Observed provisioning time: ~12 min (swedencentral + westeurope, 2026-07-30). Design guidance says 30–45 min; actual can be faster.
- vWAN manages firewall subnet allocation from the hub's /23 address prefix. Do NOT create AzureFirewallSubnet.

---

## Step 3 — Verify Secured Hub State

```bash
# Check hub shows azureFirewall != null
az network vhub show -g $RG -n <hub-name> \
  --query "{name:name,azureFirewall:azureFirewall.id,sku:sku,provisioningState:provisioningState}" \
  -o json

# Capture private IP (field name is hubIPAddresses, camelCase 'IP')
az network firewall show -g $RG -n <fw-name> \
  --query "{name:name,privateIP:hubIPAddresses.privateIPAddress,publicIP:hubIPAddresses.publicIPs.addresses[0].address,state:provisioningState}" \
  -o json
```

**Gotcha:** Query field is `hubIPAddresses` (not `hubIpAddresses`). Using wrong case returns null.

---

## Cleanup (MANDATORY ORDER: firewalls before policy)

```bash
# 1. Remove routing intent FIRST if enabled (idempotent)
az network vhub routing-intent delete -g $RG --vhub <hub> -n <ri-name> --yes -o none 2>/dev/null || true

# 2. Delete firewalls (parallel --no-wait)
az network firewall delete -g $RG -n <fw-name-1> --no-wait
az network firewall delete -g $RG -n <fw-name-2> --no-wait

# 3. Poll until both gone
while true; do
  S1=$(az network firewall show -g $RG -n <fw-name-1> --query provisioningState -o tsv 2>/dev/null || echo "Deleted")
  S2=$(az network firewall show -g $RG -n <fw-name-2> --query provisioningState -o tsv 2>/dev/null || echo "Deleted")
  [[ "$S1" == "Deleted" && "$S2" == "Deleted" ]] && break
  sleep 60
done

# 4. Delete policy LAST
az network firewall policy delete -g $RG -n <policy-name> -o none
```

**Policy delete will fail** if any firewall still references it — always wait for firewall deletion to complete first.

---

## Cost Reference

- Azure Firewall Standard in vWAN hub: ~$1.25/hr per firewall
- 2 × Standard firewalls = ~$60/day (infrastructure, no data processing for control-plane-only labs)

---

## Lab Evidence (vwan-routemap-summarization, 2026-07-30)

- azfw-eu1 (swedencentral/hub-eu1): privateIP=192.168.2.132
- azfw-eu2 (westeurope/hub-eu2): privateIP=192.168.4.132
- Policy: azfwpol-routemap-lab (Standard, swedencentral)
- Scripts: `labs/vwan-routemap-summarization/deploy/deploy-phase3-firewall.sh` + `cleanup-phase3-firewall.sh`
