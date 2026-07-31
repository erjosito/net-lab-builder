#!/usr/bin/env bash
# deploy-phase3-firewall.sh
# Phase 3 — Deploy Azure Firewall into hub-eu1 and hub-eu2 (NO routing intent).
# Idempotent: re-running converges, not duplicates.
# Routing Intent is deliberately excluded; enable only after Niobe Gate A passes.
#
# Tags: lab=vwan-routemap-summarization, owner=jose, ephemeral=true
# Cleanup: see cleanup-phase3-firewall.sh
#
# Author: Tank (IaC Engineer)
# Date:   2026-07-30

set -euo pipefail

RG="routemap-test-rg"
POLICY="azfwpol-routemap-lab"
FW_EU1="azfw-eu1"
FW_EU2="azfw-eu2"
HUB_EU1="hub-eu1"
HUB_EU2="hub-eu2"

echo "=== Prerequisites Check ==="
echo "Route tables on hub-eu1:"
az network vhub route-table list -g "$RG" --vhub-name "$HUB_EU1" -o table
echo "Route tables on hub-eu2:"
az network vhub route-table list -g "$RG" --vhub-name "$HUB_EU2" -o table

# Check for VNetConnection next-hops in defaultRouteTable — must be empty
EU1_ROUTES=$(az network vhub route-table show -g "$RG" --vhub-name "$HUB_EU1" -n defaultRouteTable --query "routes" -o tsv)
EU2_ROUTES=$(az network vhub route-table show -g "$RG" --vhub-name "$HUB_EU2" -n defaultRouteTable --query "routes" -o tsv)
if [[ -n "$EU1_ROUTES" || -n "$EU2_ROUTES" ]]; then
  echo "ERROR: Custom routes found in defaultRouteTable(s). Inspect before proceeding."
  echo "hub-eu1 routes: $EU1_ROUTES"
  echo "hub-eu2 routes: $EU2_ROUTES"
  exit 1
fi
echo "Prerequisites PASS: no custom routes in defaultRouteTables."

# Save rollback snapshots
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
az network vhub route-table show -g "$RG" --vhub-name "$HUB_EU1" -n defaultRouteTable -o json \
  | sed 's|/subscriptions/[^/]*/|/subscriptions/<SUBSCRIPTION_ID>/|g' \
  > "$SCRIPT_DIR/hub-eu1-defaultRT-pre-phase3.json"
az network vhub route-table show -g "$RG" --vhub-name "$HUB_EU2" -n defaultRouteTable -o json \
  | sed 's|/subscriptions/[^/]*/|/subscriptions/<SUBSCRIPTION_ID>/|g' \
  > "$SCRIPT_DIR/hub-eu2-defaultRT-pre-phase3.json"
echo "Rollback snapshots saved."

echo ""
echo "=== Step 1: Firewall Policy ==="

# 1a — policy (idempotent: create only if not exists)
if ! az network firewall policy show -g "$RG" -n "$POLICY" -o none 2>/dev/null; then
  az network firewall policy create \
    -g "$RG" \
    -n "$POLICY" \
    --location swedencentral \
    --sku Standard \
    -o none
  echo "Created $POLICY"
else
  echo "$POLICY already exists, skipping."
fi

# 1b — DefaultRuleCollectionGroup
if ! az network firewall policy rule-collection-group show -g "$RG" \
    --policy-name "$POLICY" -n DefaultRuleCollectionGroup -o none 2>/dev/null; then
  az network firewall policy rule-collection-group create \
    -g "$RG" \
    --policy-name "$POLICY" \
    -n DefaultRuleCollectionGroup \
    --priority 100 \
    -o none
  echo "Created DefaultRuleCollectionGroup"
else
  echo "DefaultRuleCollectionGroup already exists, skipping."
fi

# 1c — allow-all-lab rule collection (check if present first)
EXISTING_COLL=$(az network firewall policy rule-collection-group show \
  -g "$RG" --policy-name "$POLICY" -n DefaultRuleCollectionGroup \
  --query "ruleCollections[?name=='allow-all-lab'] | length(@)" -o tsv 2>/dev/null || echo "0")
if [[ "$EXISTING_COLL" == "0" ]]; then
  az network firewall policy rule-collection-group collection add-filter-collection \
    -g "$RG" \
    --policy-name "$POLICY" \
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
  echo "Created allow-all-lab rule collection"
else
  echo "allow-all-lab already exists, skipping."
fi

az network firewall policy show -g "$RG" -n "$POLICY" \
  --query "{name:name,sku:sku,provisioningState:provisioningState}" -o json
echo "Step 1 complete."

echo ""
echo "=== Step 2: Deploy Firewalls (parallel via --no-wait) ==="

# azfw-eu1
if ! az network firewall show -g "$RG" -n "$FW_EU1" -o none 2>/dev/null; then
  az network firewall create \
    -g "$RG" \
    -n "$FW_EU1" \
    --location swedencentral \
    --sku AZFW_Hub \
    --tier Standard \
    --vhub "$HUB_EU1" \
    --public-ip-count 1 \
    --firewall-policy "$POLICY" \
    --no-wait
  echo "$FW_EU1 deploy submitted (no-wait)"
else
  echo "$FW_EU1 already exists, skipping create."
fi

# azfw-eu2
if ! az network firewall show -g "$RG" -n "$FW_EU2" -o none 2>/dev/null; then
  az network firewall create \
    -g "$RG" \
    -n "$FW_EU2" \
    --location westeurope \
    --sku AZFW_Hub \
    --tier Standard \
    --vhub "$HUB_EU2" \
    --public-ip-count 1 \
    --firewall-policy "$POLICY" \
    --no-wait
  echo "$FW_EU2 deploy submitted (no-wait)"
else
  echo "$FW_EU2 already exists, skipping create."
fi

# Poll until both Succeeded
echo "Polling provisioning state (may take 10-45 min)..."
while true; do
  S1=$(az network firewall show -g "$RG" -n "$FW_EU1" --query "provisioningState" -o tsv 2>/dev/null || echo "NotFound")
  S2=$(az network firewall show -g "$RG" -n "$FW_EU2" --query "provisioningState" -o tsv 2>/dev/null || echo "NotFound")
  echo "[$(date '+%H:%M:%S')] $FW_EU1=$S1  $FW_EU2=$S2"
  if [[ "$S1" == "Succeeded" && "$S2" == "Succeeded" ]]; then
    echo "Both firewalls Succeeded."
    break
  elif [[ "$S1" == "Failed" || "$S2" == "Failed" ]]; then
    echo "ERROR: A firewall deployment failed. Inspect and report to Trinity/Jose — do NOT improvise."
    exit 1
  fi
  sleep 120
done

echo ""
echo "=== Step 3: Verify secured-hub state ==="
for hub in "$HUB_EU1" "$HUB_EU2"; do
  echo "=== $hub ==="
  az network vhub show -g "$RG" -n "$hub" \
    --query "{name:name,azureFirewall:azureFirewall.id,sku:sku,provisioningState:provisioningState}" \
    -o json | sed 's|/subscriptions/[^/]*/|/subscriptions/<SUBSCRIPTION_ID>/|g'
done

echo ""
echo "=== Firewall IPs and IDs ==="
for fw in "$FW_EU1" "$FW_EU2"; do
  az network firewall show -g "$RG" -n "$fw" \
    --query "{name:name,privateIP:hubIPAddresses.privateIPAddress,publicIP:hubIPAddresses.publicIPs.addresses[0].address,provisioningState:provisioningState}" \
    -o json
done

echo ""
echo "*** NIOBE GATE A ***"
echo "Both firewalls deployed. Routing Intent NOT enabled."
echo "Niobe: run route-collection checklist (design-phase3.md §8) now."
echo "DO NOT proceed to Step 4 (Routing Intent) without Niobe Gate A sign-off."
