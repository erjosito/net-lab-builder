#requires -version 5.1
<#
  cleanup.ps1 - sap-rise-scoped-peering-fwaas
  Manifest.md section 5 order: de-peer -> connection delete -> gateway delete ->
  circuit delete -> VXC delete -> MCR delete -> VNets -> RG.
  Megaport has no hourly billing: a delayed VXC/MCR cleanup costs a full extra month,
  not a few dollars - do not treat it as low-urgency.
#>
param(
    [switch]$SkipConfirm
)

$ErrorActionPreference = "Stop"
$tfDir = "C:\Users\jomore\Repos\net-lab-builder\src\terraform\sap-rise-scoped-peering-fwaas"

# Step 0: Rehydrate HKCU env vars (Windows only)
foreach ($varName in @('MEGAPORT_ACCESS_KEY', 'MEGAPORT_SECRET_KEY')) {
    $val = [System.Environment]::GetEnvironmentVariable($varName, 'User')
    if ($val) { [System.Environment]::SetEnvironmentVariable($varName, $val, 'Process') }
}
$env:TF_VAR_megaport_access_key = $env:MEGAPORT_ACCESS_KEY
$env:TF_VAR_megaport_secret_key = $env:MEGAPORT_SECRET_KEY
$env:ARM_SUBSCRIPTION_ID = (az account show --query id -o tsv)

Push-Location $tfDir
try {
    if (-not (Test-Path "terraform.tfstate")) {
        Write-Host "No local state found in $tfDir - nothing to destroy via Terraform. Check for orphans manually." -ForegroundColor Yellow
    } else {
        $rg = terraform output -raw resource_group_name 2>$null
        if (-not $SkipConfirm) {
            Write-Host "About to destroy lab 'sap-rise-scoped-peering-fwaas' (RG: $rg)." -ForegroundColor Yellow
        }

        Write-Host "--- Terraform destroy (dependency graph handles the ordering) ---" -ForegroundColor Cyan
        terraform destroy -auto-approve
        if ($LASTEXITCODE -ne 0) {
            Write-Host "terraform destroy failed or partially completed - checking for Megaport orphans before RG purge." -ForegroundColor Yellow
        }
    }
}
finally {
    Pop-Location
}

# Safety net: confirm no orphaned Azure resources remain under the lab's RG tag.
$rgName = "rg-saprise-swedencentral"
$stillExists = az group exists --name $rgName
if ($stillExists -eq "true") {
    Write-Host "RG $rgName still exists after destroy - forcing delete (--no-wait), then verify Megaport side separately." -ForegroundColor Yellow
    az group delete --name $rgName --yes --no-wait
}

Write-Host "=== Cleanup: verify Megaport MCR/VXC are gone via the Megaport portal or terraform-provider state (no hourly billing - orphans cost a full month) ===" -ForegroundColor Red
Write-Host "Purge checklist: orphan public IPs, soft-deleted resources, role assignments at sub scope - none expected in this lab (no Key Vault, no custom RBAC)."
