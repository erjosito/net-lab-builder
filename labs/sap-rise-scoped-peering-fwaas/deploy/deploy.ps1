#requires -version 5.1
<#
  deploy.ps1 - sap-rise-scoped-peering-fwaas
  Deploys the SAP RISE subnet-scoped peering + FWaaS lab (manifest.md / design.md).

  Long pole: ErGw1AZ gateway (~20-45 min), parallel with Route Server (~10-20 min) and
  the Megaport MCR/circuit/VXC chain. Expect ~45-70 min total wall-clock.
#>
param(
    [string]$SubscriptionId = "",
    [switch]$SkipPreflight
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$tfDir = Join-Path (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $root))) "src\terraform\sap-rise-scoped-peering-fwaas"
$tfDir = "C:\Users\jomore\Repos\net-lab-builder\src\terraform\sap-rise-scoped-peering-fwaas"

Write-Host "=== sap-rise-scoped-peering-fwaas deploy ===" -ForegroundColor Cyan

# --- Step 0: Rehydrate HKCU env vars (Windows only; no-op if already set) ---
# PowerShell child processes do not inherit HKCU registry values - Terraform's Megaport
# provider needs these in-process. See .squad/agents/tank/charter.md "Pre-flight (Windows)".
$varsToRehydrate = @(
    'MEGAPORT_ACCESS_KEY', 'MEGAPORT_SECRET_KEY'
)
foreach ($varName in $varsToRehydrate) {
    $val = [System.Environment]::GetEnvironmentVariable($varName, 'User')
    if ($val) { [System.Environment]::SetEnvironmentVariable($varName, $val, 'Process') }
}
$env:TF_VAR_megaport_access_key = $env:MEGAPORT_ACCESS_KEY
$env:TF_VAR_megaport_secret_key = $env:MEGAPORT_SECRET_KEY

if (-not $env:MEGAPORT_ACCESS_KEY -or -not $env:MEGAPORT_SECRET_KEY) {
    throw "Megaport credentials not found in HKCU (MEGAPORT_ACCESS_KEY / MEGAPORT_SECRET_KEY). Aborting."
}

if ($SubscriptionId) {
    az account set --subscription $SubscriptionId
}
$env:ARM_SUBSCRIPTION_ID = (az account show --query id -o tsv)
Write-Host "Subscription: $env:ARM_SUBSCRIPTION_ID"

if (-not $SkipPreflight) {
    Write-Host "--- Preflight: subnet-peering feature registration ---" -ForegroundColor Yellow
    $state = az feature show --namespace Microsoft.Network --name AllowMultiplePeeringLinksBetweenVnets --query "properties.state" -o tsv
    if ($state -ne "Registered") {
        Write-Host "Registering Microsoft.Network/AllowMultiplePeeringLinksBetweenVnets (not pre-registered)..."
        az feature register --namespace Microsoft.Network --name AllowMultiplePeeringLinksBetweenVnets | Out-Null
        $tries = 0
        do {
            Start-Sleep -Seconds 20
            $state = az feature show --namespace Microsoft.Network --name AllowMultiplePeeringLinksBetweenVnets --query "properties.state" -o tsv
            $tries++
        } while ($state -ne "Registered" -and $tries -lt 30)
        if ($state -ne "Registered") {
            throw "STOP: subnet-scoped peering feature did not reach Registered state after ~10 min. Do NOT fall back to full-VNet peering silently - escalate per manifest.md Risk #2."
        }
        az provider register --namespace Microsoft.Network | Out-Null
    }
    Write-Host "Subnet-peering feature: $state"

    Write-Host "--- Preflight: VM SKU probe (swedencentral) ---" -ForegroundColor Yellow
    $restriction = az vm list-skus --location swedencentral --resource-type virtualMachines `
        --query "[?name=='Standard_B2als_v2'].restrictions[0].type" -o tsv
    $useFallback = "false"
    if ($restriction) {
        Write-Host "Standard_B2als_v2 restricted in swedencentral ($restriction) - falling back to Standard_B2s_v2" -ForegroundColor Yellow
        $useFallback = "true"
    } else {
        Write-Host "Standard_B2als_v2 available in swedencentral, no restriction."
    }
    $env:TF_VAR_use_vm_size_fallback = $useFallback
}

Push-Location $tfDir
try {
    terraform init -upgrade
    if ($LASTEXITCODE -ne 0) { throw "terraform init failed" }

    terraform validate
    if ($LASTEXITCODE -ne 0) { throw "terraform validate failed" }

    terraform plan -out=tfplan
    if ($LASTEXITCODE -ne 0) { throw "terraform plan failed" }

    Write-Host "--- Applying (S1 baseline: summarizedGatewayPrefixes unset) ---" -ForegroundColor Cyan
    terraform apply tfplan
    if ($LASTEXITCODE -ne 0) { throw "terraform apply failed" }

    Write-Host "--- Post-deploy: configuring BIRD BGP on hub NVA + simulated CE ---" -ForegroundColor Cyan
    $rg = terraform output -raw resource_group_name
    $hubNva = terraform output -raw vm_hub_nva_name
    $spokeNva = terraform output -raw vm_spoke_nva_name
    $ceVm = terraform output -raw vm_ce_onprem_name
    $hubNvaIp = terraform output -raw vm_hub_nva_private_ip
    $ceIp = terraform output -raw vm_ce_onprem_private_ip
    $spokeNvaIp = terraform output -raw vm_spoke_nva_private_ip
    $arsIps = az network routeserver show --resource-group $rg --name ars-hub --query "virtualRouterIps" -o tsv

    function Assert-IpForwardEnabled {
        param(
            [string]$VmName
        )

        $runCommandRaw = az vm run-command invoke -g $rg -n $VmName --command-id RunShellScript `
            --scripts "cat /proc/sys/net/ipv4/ip_forward" -o json
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: ip_forward verification run-command failed on $VmName." -ForegroundColor Red
            throw "ip_forward verification run-command failed on $VmName."
        }

        $runCommand = $runCommandRaw | ConvertFrom-Json
        $message = (($runCommand.value | ForEach-Object { $_.message }) -join "`n")
        if ($message -notmatch '(?m)^1\s*$') {
            Write-Host "ERROR: $VmName has /proc/sys/net/ipv4/ip_forward != 1 immediately after provisioning." -ForegroundColor Red
            Write-Host $message -ForegroundColor Red
            throw "$VmName failed ip_forward verification."
        }

        Write-Host "$VmName ip_forward verified as 1."
    }

    Assert-IpForwardEnabled -VmName $hubNva
    Assert-IpForwardEnabled -VmName $spokeNva

    if (-not $arsIps -or ($arsIps -split "`n").Count -lt 2) {
        Write-Host "WARNING: could not read 2 ARS peer IPs yet; BIRD config on hub NVA left as placeholder. Re-run this block manually once ARS is fully provisioned." -ForegroundColor Yellow
    } else {
        $ip1, $ip2 = $arsIps -split "`n"
        $birdConf = @"
router id $hubNvaIp;
protocol device {}
protocol direct { interface "eth0"; }
protocol kernel { ipv4 { import all; export all; }; learn; scan time 15; }
protocol static {
    route 10.60.0.0/16 via $spokeNvaIp;
}
template bgp azure_peer {
    local $hubNvaIp as 65001;
    multihop 2;
    ipv4 { import none; export where source = RTS_STATIC; };
    graceful restart on;
    connect retry time 10;
    hold time 60;
    keepalive time 20;
}
protocol bgp ars_1 from azure_peer { neighbor $ip1 as 65515; }
protocol bgp ars_2 from azure_peer { neighbor $ip2 as 65515; }
"@
        $birdConf | Out-File -Encoding ascii "$env:TEMP\bird-hub-nva.conf"
        az vm run-command invoke -g $rg -n $hubNva --command-id RunShellScript `
            --scripts "cat > /etc/bird/bird.conf << 'BIRDEOF'`n$birdConf`nBIRDEOF`nsystemctl restart bird" | Out-Null
        Write-Host "Hub NVA BIRD config applied (ASN 65001 <-> ARS 65515), static route 10.60.0.0/16 exported."
    }

    $ceBirdConf = @"
router id $ceIp;
protocol device {}
protocol direct { interface "eth0"; }
protocol kernel { ipv4 { import all; export all; }; learn; scan time 15; }
protocol static {
    route 172.40.100.0/24 via $ceIp;
}
protocol bgp hub_nva {
    local $ceIp as 65000;
    neighbor $hubNvaIp as 65001;
    multihop 2;
    ipv4 { import none; export where source = RTS_STATIC; };
    graceful restart on;
}
"@
    az vm run-command invoke -g $rg -n $ceVm --command-id RunShellScript `
        --scripts "cat > /etc/bird/bird.conf << 'BIRDEOF'`n$ceBirdConf`nBIRDEOF`nsystemctl restart bird" | Out-Null
    Write-Host "Simulated CE BIRD config applied (ASN 65000), advertising 172.40.100.0/24 toward hub NVA."

    Write-Host "=== Deploy complete. S1 baseline active (summarizedGatewayPrefixes unset). ===" -ForegroundColor Green
    Write-Host "To activate S2 capture: terraform apply -var enable_summarized_gateway_prefixes=true"
    Write-Host "To revert to S1-only: terraform apply -var enable_summarized_gateway_prefixes=false"
}
finally {
    Pop-Location
}
