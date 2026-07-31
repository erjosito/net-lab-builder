#!/usr/bin/env bash
# cleanup-phase3-firewall.sh
# Remove Phase 3 Azure Firewalls and Firewall Policy from routemap-test-rg.
# Cleanup order: azfw-eu1 → azfw-eu2 → azfwpol-routemap-lab (firewalls before policy).
# Idempotent: exits cleanly if resources already deleted.
#
# Author: Tank (IaC Engineer)
# Date:   2026-07-30

set -euo pipefail

RG="routemap-test-rg"
POLICY="azfwpol-routemap-lab"

echo "=== Phase 3 Cleanup: Azure Firewalls + Policy ==="
echo "RG: $RG"
echo "Note: Routing Intent (if enabled) must be removed BEFORE the firewalls."

# Remove routing intent (no-op if not present — idempotent)
for ri_args in "--vhub hub-eu1 -n hub-eu1-ri" "--vhub hub-eu2 -n hub-eu2-ri"; do
  if az network vhub routing-intent show -g "$RG" $ri_args -o none 2>/dev/null; then
    echo "Removing routing intent: $ri_args"
    az network vhub routing-intent delete -g "$RG" $ri_args --yes -o none
    echo "Done."
  else
    echo "Routing intent not present ($ri_args) — skipping."
  fi
done

# Delete azfw-eu1 (no-wait, then poll)
if az network firewall show -g "$RG" -n azfw-eu1 -o none 2>/dev/null; then
  echo "Deleting azfw-eu1..."
  az network firewall delete -g "$RG" -n azfw-eu1 --no-wait
  echo "azfw-eu1 delete submitted."
else
  echo "azfw-eu1 not found — already deleted."
fi

# Delete azfw-eu2 (no-wait, then poll)
if az network firewall show -g "$RG" -n azfw-eu2 -o none 2>/dev/null; then
  echo "Deleting azfw-eu2..."
  az network firewall delete -g "$RG" -n azfw-eu2 --no-wait
  echo "azfw-eu2 delete submitted."
else
  echo "azfw-eu2 not found — already deleted."
fi

# Poll until both firewalls are gone
echo "Waiting for both firewalls to be deleted..."
while true; do
  EU1=$(az network firewall show -g "$RG" -n azfw-eu1 --query "provisioningState" -o tsv 2>/dev/null || echo "Deleted")
  EU2=$(az network firewall show -g "$RG" -n azfw-eu2 --query "provisioningState" -o tsv 2>/dev/null || echo "Deleted")
  echo "[$(date '+%H:%M:%S')] azfw-eu1=$EU1  azfw-eu2=$EU2"
  if [[ "$EU1" == "Deleted" && "$EU2" == "Deleted" ]]; then
    echo "Both firewalls deleted."
    break
  fi
  sleep 60
done

# Delete policy AFTER firewalls are gone
if az network firewall policy show -g "$RG" -n "$POLICY" -o none 2>/dev/null; then
  echo "Deleting firewall policy $POLICY..."
  az network firewall policy delete -g "$RG" -n "$POLICY" --yes -o none 2>/dev/null || \
    az network firewall policy delete -g "$RG" -n "$POLICY" -o none
  echo "Policy deleted."
else
  echo "Policy $POLICY not found — already deleted."
fi

echo ""
echo "=== Phase 3 Cleanup Complete ==="
echo "Firewalls and policy removed. Lab is back to Phase 2 state."
echo "To delete the full RG: az group delete -n $RG --yes"
