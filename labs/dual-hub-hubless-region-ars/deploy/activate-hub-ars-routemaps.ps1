# activate-hub-ars-routemaps.ps1
# Idempotent first-use route-map activation for ars-hub1 and ars-hub2.
# Creates one inert activation-only route map per ARS (no connection associations).
# Triggers the ~30 min route-map tier upgrade on first use.
# API: 2024-10-01  |  Author: Tank  |  Date: 2026-08-05

param(
    [string]$RG = "rg-dual-hub-hubless-region-ars-lab3d001",
    [string]$Hub1 = "ars-hub1",
    [string]$Hub2 = "ars-hub2",
    [string]$ApiVersion = "2024-10-01",
    [string]$Map1Name = "rm-hub1-activate",
    [string]$Map2Name = "rm-hub2-activate",
    [int]$TimeoutMinutes = 45
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$SUB = (az account show --query id -o tsv)
if (-not $SUB) { throw "No active Azure context. Run 'az login' first." }

# Inert body — matches RFC5737 TEST-NET 192.0.2.0/24 only; never associated with a connection
$body = @{
    properties = @{
        rules = @(
            @{
                name = "rule-activate-synthetic"
                matchCriteria = @(@{ matchCondition = "Equals"; routePrefix = @("192.0.2.0/24") })
                actions = @(@{ type = "Add"; parameters = @(@{ asPath = @("64496") }) })
                nextStepIfMatched = "Terminate"
            }
        )
        associatedInboundConnections = @()
        associatedOutboundConnections = @()
    }
} | ConvertTo-Json -Depth 10

$bodyFile = [System.IO.Path]::GetTempFileName() + ".json"
$body | Set-Content $bodyFile

function Invoke-ActivateMap {
    param([string]$ArsName, [string]$MapName)

    $url = "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Network/virtualHubs/$ArsName/routeMaps/$MapName`?api-version=$ApiVersion"

    # Check idempotency: map already exists?
    $existing = az rest --method GET --url $url -o json 2>&1 | ConvertFrom-Json
    if ($existing.properties.provisioningState -eq "Succeeded") {
        $inbound = $existing.properties.associatedInboundConnections.Count
        $outbound = $existing.properties.associatedOutboundConnections.Count
        Write-Host "[$ArsName] $MapName already exists and is Succeeded (inbound=$inbound outbound=$outbound). Skipping create."
        return "already-succeeded"
    }

    Write-Host "[$ArsName] Creating $MapName at $(Get-Date -Format 'HH:mm:ss')..."
    az rest --method PUT --url $url --body "@$bodyFile" -o json | Out-Null
    return "created"
}

# Trigger both — parallel in separate jobs
$start = Get-Date
Write-Host "=== Triggering activation maps ==="
$j1 = Start-Job { param($s,$rg,$a,$m,$bf,$av)
    $url = "https://management.azure.com/subscriptions/$s/resourceGroups/$rg/providers/Microsoft.Network/virtualHubs/$a/routeMaps/$m`?api-version=$av"
    $existing = az rest --method GET --url $url -o json 2>&1 | ConvertFrom-Json
    if ($existing.properties.provisioningState -eq "Succeeded") { return "already-succeeded" }
    az rest --method PUT --url $url --body "@$bf" -o json | Out-Null
    return "created"
} -ArgumentList $SUB, $RG, $Hub1, $Map1Name, $bodyFile, $ApiVersion

$j2 = Start-Job { param($s,$rg,$a,$m,$bf,$av)
    $url = "https://management.azure.com/subscriptions/$s/resourceGroups/$rg/providers/Microsoft.Network/virtualHubs/$a/routeMaps/$m`?api-version=$av"
    $existing = az rest --method GET --url $url -o json 2>&1 | ConvertFrom-Json
    if ($existing.properties.provisioningState -eq "Succeeded") { return "already-succeeded" }
    az rest --method PUT --url $url --body "@$bf" -o json | Out-Null
    return "created"
} -ArgumentList $SUB, $RG, $Hub2, $Map2Name, $bodyFile, $ApiVersion

$j1 | Wait-Job | Out-Null
$j2 | Wait-Job | Out-Null
$r1 = Receive-Job $j1; $r2 = Receive-Job $j2
Write-Host "hub1: $r1  hub2: $r2"

# Poll until Succeeded or timeout
$hub1Done = ($r1 -eq "already-succeeded"); $hub2Done = ($r2 -eq "already-succeeded")

while ((-not $hub1Done -or -not $hub2Done) -and (((Get-Date) - $start).TotalMinutes -lt $TimeoutMinutes)) {
    Start-Sleep -Seconds 60
    $elapsed = [math]::Round(((Get-Date) - $start).TotalMinutes, 1)

    if (-not $hub1Done) {
        $s1 = (az network routeserver show -g $RG -n $Hub1 --query provisioningState -o tsv 2>&1)
        $ms1 = (az rest --method GET --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Network/virtualHubs/$Hub1/routeMaps/$Map1Name`?api-version=$ApiVersion" -o json 2>&1 | ConvertFrom-Json).properties.provisioningState
        Write-Host "[+${elapsed}m] hub1: ARS=$s1 map=$ms1"
        if ($ms1 -eq "Succeeded" -or $ms1 -eq "Failed") { $hub1Done = $true }
    }

    if (-not $hub2Done) {
        $s2 = (az network routeserver show -g $RG -n $Hub2 --query provisioningState -o tsv 2>&1)
        $ms2 = (az rest --method GET --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Network/virtualHubs/$Hub2/routeMaps/$Map2Name`?api-version=$ApiVersion" -o json 2>&1 | ConvertFrom-Json).properties.provisioningState
        Write-Host "[+${elapsed}m] hub2: ARS=$s2 map=$ms2"
        if ($ms2 -eq "Succeeded" -or $ms2 -eq "Failed") { $hub2Done = $true }
    }
}

Remove-Item $bodyFile -Force -ErrorAction SilentlyContinue

$elapsed = [math]::Round(((Get-Date) - $start).TotalMinutes, 1)
Write-Host "=== Done at +${elapsed}m. Verify with:"
Write-Host "  az rest --method GET --url 'https://management.azure.com/subscriptions/<SUB>/resourceGroups/$RG/providers/Microsoft.Network/virtualHubs/$Hub1/routeMaps/$Map1Name?api-version=$ApiVersion'"
