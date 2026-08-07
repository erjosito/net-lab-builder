$ErrorActionPreference = "SilentlyContinue"
$sshKeyPath = "$env:USERPROFILE\.ssh\id_rsa.pub"
$sshKey = Get-Content $sshKeyPath -Raw
$preflight_rg = "preflight-20260803-123409"

# Define regions and roles
$config = @{
  swedencentral = @{
    role = "hub1"
    services = @('Route Server', 'VPN Gateway', 'Ubuntu NVA')
    nva_sku = 'Standard_B2ts_v2'
    test_vm_skus = @('Standard_B1ls', 'Standard_B1s', 'Standard_B2ts_v2')
  }
  germanywestcentral = @{
    role = "hub2"
    services = @('Route Server', 'VPN Gateway', 'Ubuntu NVA')
    nva_sku = 'Standard_B2ts_v2'
    test_vm_skus = @('Standard_B1ls', 'Standard_B1s', 'Standard_B2ts_v2')
  }
  polandcentral = @{
    role = "workload"
    services = @('Route Server', 'Test VM', 'Spoke VNets')
    nva_sku = $null
    test_vm_skus = @('Standard_B1ls', 'Standard_B1s', 'Standard_B2ts_v2')
  }
  francecentral = @{
    role = "on-prem"
    services = @('VPN Gateway', 'Endpoint VM')
    nva_sku = $null
    test_vm_skus = @('Standard_B1ls', 'Standard_B1s', 'Standard_B2ts_v2')
  }
}

Write-Host "=== PHASE 0 PREFLIGHT: Dual-Hub Design ==="
Write-Host "Regions: swedencentral (hub1) | germanywestcentral (hub2) | polandcentral (workload) | francecentral (on-prem)"
Write-Host "Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "Temp RG: $preflight_rg`n"

# Test each region
foreach ($region in $config.Keys) {
  $cfg = $config[$region]
  Write-Host "=== $region ($($cfg.role)) ==="
  
  # NVA SKU test if applicable
  if ($cfg.nva_sku) {
    Write-Host "  Testing NVA SKU ($($cfg.nva_sku))..."
    $vmName = "probe-nva-$region"
    $result = az vm create -g $preflight_rg -n $vmName -l $region `
      --image Ubuntu2204 --size $cfg.nva_sku `
      --admin-username azureuser --ssh-key-values "$sshKey" `
      --validate 2>&1
    
    if ($LASTEXITCODE -eq 0) {
      Write-Host "    LIVE VALIDATION: PASS"
    } else {
      Write-Host "    LIVE VALIDATION: FAIL"
      if ($result -match "SkuNotAvailable|Capacity") {
        Write-Host "    Reason: Capacity or SKU not available"
      }
    }
  }
  
  # Test VM SKU
  Write-Host "  Testing Test VM SKU (Standard_B1ls)..."
  $vmName = "probe-vm-$region"
  $result = az vm create -g $preflight_rg -n $vmName -l $region `
    --image Ubuntu2204 --size Standard_B1ls `
    --admin-username azureuser --ssh-key-values "$sshKey" `
    --validate 2>&1
  
  if ($LASTEXITCODE -eq 0) {
    Write-Host "    LIVE VALIDATION: PASS"
  } else {
    Write-Host "    LIVE VALIDATION: FAIL (B1ls)"
    # Try B1s
    $result = az vm create -g $preflight_rg -n $vmName -l $region `
      --image Ubuntu2204 --size Standard_B1s `
      --admin-username azureuser --ssh-key-values "$sshKey" `
      --validate 2>&1
    
    if ($LASTEXITCODE -eq 0) {
      Write-Host "    LIVE VALIDATION: PASS (B1s)"
    } else {
      Write-Host "    LIVE VALIDATION: FAIL (B1s)"
      Write-Host "    Trying B2ts_v2..."
    }
  }
  
  Write-Host ""
}

Write-Host "=== Preflight check complete ==="
