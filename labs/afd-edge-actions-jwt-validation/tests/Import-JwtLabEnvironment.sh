#!/usr/bin/env bash

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "Source this script so the variables remain in your shell:"
  echo "  source ./Import-JwtLabEnvironment.sh"
  exit 1
fi

vault_name="${1:-kv-jwt-lab-a8fbd8e1}"

if ! az account show >/dev/null 2>&1; then
  az login --identity --allow-no-subscriptions --output none
fi

read_secret() {
  az keyvault secret show \
    --vault-name "$vault_name" \
    --name "$1" \
    --query value \
    --output tsv
}

export TENANT_ID="$(read_secret tenant-id)"
export API_APP_ID="$(read_secret api-app-id)"
export CLIENT_ID="$(read_secret client-id)"
export CLIENT_SECRET="$(read_secret client-secret)"
export AFD_ENDPOINT="$(read_secret afd-endpoint)"

for variable in TENANT_ID API_APP_ID CLIENT_ID CLIENT_SECRET AFD_ENDPOINT; do
  if [[ -z "${!variable}" ]]; then
    echo "Failed to load $variable from $vault_name." >&2
    return 1
  fi
done

echo "Loaded TENANT_ID, API_APP_ID, CLIENT_ID, CLIENT_SECRET, and AFD_ENDPOINT."
echo "Values are available only in this shell and were not printed."
