#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$InventoryPath
)

$ErrorActionPreference = 'Stop'
$inventory = Get-Content (Resolve-Path $InventoryPath) -Raw | ConvertFrom-Json
$installer = @'
set -euo pipefail
install -d -m 0755 /opt/vwan-health
printf 'ok\n' >/opt/vwan-health/health
cat >/etc/systemd/system/vwan-health.service <<'EOF'
[Unit]
Description=vWAN lab HTTP health listener
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/python3 -m http.server 8080 --bind 0.0.0.0 --directory /opt/vwan-health
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now vwan-health.service
for attempt in 1 2 3 4 5; do
  if curl -fsS http://127.0.0.1:8080/health; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:8080/health >/dev/null
echo LISTENER_READY
'@
$installer = $installer.Replace("`r`n", "`n")
$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($installer))
$command = "echo '$encoded' | base64 -d >/tmp/install-vwan-health.sh && sudo bash /tmp/install-vwan-health.sh && rm -f /tmp/install-vwan-health.sh"

$commandName = 'install-vwan-health'
$existing = az vm run-command show -g $inventory.azure.resourceGroup --vm-name $inventory.azure.workloadVmName `
    --run-command-name $commandName --query id -o tsv 2>$null
if ($existing) {
    az vm run-command update -g $inventory.azure.resourceGroup --vm-name $inventory.azure.workloadVmName `
        --run-command-name $commandName --script $installer --async-execution false `
        --timeout-in-seconds 300 --no-wait --only-show-errors -o none
} else {
    az vm run-command create -g $inventory.azure.resourceGroup --vm-name $inventory.azure.workloadVmName `
        --run-command-name $commandName --location swedencentral --script $installer `
        --async-execution false --timeout-in-seconds 300 --no-wait --only-show-errors -o none
}
if ($LASTEXITCODE -ne 0) { throw 'Azure workload listener command submission failed.' }

$deadline = (Get-Date).AddMinutes(6)
do {
    $azureResult = az vm run-command show -g $inventory.azure.resourceGroup `
        --vm-name $inventory.azure.workloadVmName --run-command-name $commandName `
        --expand instanceView -o json | ConvertFrom-Json
    if ($azureResult.provisioningState -eq 'Succeeded' -and
        $azureResult.instanceView.executionState -eq 'Succeeded' -and
        $azureResult.instanceView.exitCode -eq 0) {
        break
    }
    Start-Sleep -Seconds 20
} while ((Get-Date) -lt $deadline)
if ($azureResult.provisioningState -ne 'Succeeded' -or
    $azureResult.instanceView.executionState -ne 'Succeeded' -or
    $azureResult.instanceView.exitCode -ne 0) {
    throw 'Azure workload listener installation did not converge successfully.'
}

$gcpResult = gcloud compute ssh $inventory.gcp.cpeVmName --project $inventory.gcp.projectId --zone $inventory.gcp.zone `
    --tunnel-through-iap --quiet --command $command
if ($LASTEXITCODE -ne 0 -or ($gcpResult -join "`n") -notmatch 'LISTENER_READY') {
    throw 'GCP CPE listener installation failed.'
}

Write-Output 'APPLICATION_LISTENERS_READY=true'
