# Δ3 Activation Contract — ars-poland Inbound Route Map
**Author:** Trinity (Azure Network SME)  
**Date:** 2026-08-03T19:31:59+02:00  
**Approved by:** Jose Moreno (Phase-4 approval on record; $72/day cost guardrail waiver explicit)  
**Status:** ✅ APPROVED ACTIVATION CONTRACT  
**RG:** `rg-dual-hub-hubless-region-ars-lab3d001`  
**Executor:** Tank  
**No IaC authoring, no live changes by Trinity/Morpheus.**

---

## 1. Authoritative Microsoft Learn Findings (retrieved 2026-08-03)

Source: https://learn.microsoft.com/azure/route-server/route-maps-about  
Source: https://learn.microsoft.com/azure/route-server/route-maps-how-to

### 1a. Resource/API shape
Route maps are a **virtual-hub** API object attached to an Azure Route Server.  
PowerShell uses `-VirtualHubName <ars-name>` despite the resource being an ARS.  
Azure CLI uses the same ARS resource and sub-resource path.

**2-step model:**
1. Create `routeMap` object with rules → `provisioningState: Succeeded`
2. Apply map to a specific BGP peering (connection) with an inbound or outbound direction

### 1b. Upgrade trigger
> "The first time you create a route map on an Azure Route Server, the route server undergoes an upgrade that takes approximately **30 minutes**."  
> — learn.microsoft.com/azure/route-server/route-maps-how-to

Since no route map has ever been created on `ars-poland` (baseline confirmed), **one 30-minute upgrade is expected** upon first `New-AzRouteMap` call. Tank must wait for `provisioningState: Succeeded` before applying to peering.

### 1c. Inbound direction semantics
> "Inbound route map: Applied to routes **received** by Azure Route Server from a BGP peering."  
> "Outbound route maps modify route advertisements only and don't influence Azure Route Server's best-path selection, because **path selection happens before outbound route maps are applied**."

**Critical:** Only **inbound** maps affect best-path selection at ars-poland. Outbound would be post-selection and would not break ECMP. Δ3 **must** use inbound direction.

### 1d. Supported match/action for our use case
| Need | Match condition | Action |
|---|---|---|
| Only 0.0.0.0/0 | `Route-prefix` → `Equals` → `0.0.0.0/0` | `AS-Path` → `Add` → `[64496, 64496]` |

`Equals` on prefix matches the exact prefix only — no sub-routes affected. Correct for our scope.  
`Add` on AS-Path **prepends** the listed ASNs in order to the existing AS-PATH.

### 1e. Private-ASN constraint — CRITICAL
From the doc's **Considerations and limitations**:
> "Don't use private ASNs for AS prepending."  
> Private ASNs prohibited: full range 64512–65534 (standard private range)  
> Azure-reserved also blocked: 8074, 8075, 12076, 65515, 65517, 65518, 65519, 65520

**ASN 65002 (NVA2's ASN) is in the private range 64512–65534 → CANNOT be used in route-map actions.**  
**ASN 65001 (NVA1's ASN) — same prohibition.**

✅ **Use public doc-range ASN 64496** (RFC 5398 documentation range 64496–64511, confirmed valid in prior lab).  
The prepended ASN 64496 does NOT need to match any peer's real ASN. Its sole function is to lengthen the AS-PATH so ARS best-path selection prefers NVA1's path (1 hop: `[65002]`) over NVA2's (3 hops: `[65002, 64496, 64496]`).

### 1f. Why 64496 ×2 is sufficient and correct

| Peer | AS-PATH received by ars-poland (pre-map) | AS-PATH after map | AS-PATH length |
|---|---|---|---|
| NVA1 (no map) | `65001` | `65001` | **1** |
| NVA2 (inbound map applied) | `65002` | `65002 64496 64496` | **3** |

BGP best-path step: shorter AS-PATH wins → NVA1 (`[65001]`, length 1) wins over NVA2 (`[65002, 64496, 64496]`, length 3). ECMP is broken. ARS injects `0/0 → 10.10.1.4` (NVA1) only.

Prepending ×1 (length 2 vs 1) is also sufficient for path preference, but ×2 provides headroom consistent with Δ2 design philosophy and NVA2-side prepend in Δ2. ×2 is approved.

---

## 2. Minimal Δ3 Policy Specification

**Scope:** ars-poland BGP peering `peer-nva2` only, inbound direction only.  
**Match:** Prefix `0.0.0.0/0` exact (`Equals`).  
**Action:** AS-Path `Add` `[64496, 64496]`.  
**Next step:** `Terminate` (single rule, no chaining needed).  
**Other routes from NVA2:** NOT affected (ARS VNet-address advertisements are NOT modifiable by route maps per the doc: "You can't use route maps to modify or filter the virtual network address space that Azure Route Server advertises." The hub-subnet prefixes NVA2 advertises — `10.20.0.64/27`, `10.20.1.0/27` — are NVA-originated, not VNet-native. These are also not 0/0, so the `Equals 0.0.0.0/0` match condition will not affect them.  

---

## 3. Exact Resource/Command Contract for Tank

### Variables (set before running)
```bash
RG="rg-dual-hub-hubless-region-ars-lab3d001"
ARS="ars-poland"
PEERING="peer-nva2"
MAP_NAME="rm-poland-nva2-default-prepend"
RULE_NAME="rule-prepend-0-0-64496x2"
```

### STEP 0 — Preflight: Export current ARS state (read-only, ~30 s)
```bash
# Capture current learned routes on peer-nva2 BEFORE any change
az network routeserver peering list-learned-routes \
  -g "$RG" --routeserver "$ARS" -n "$PEERING" \
  -o json > show-output/post-delta3/00-pre-map-ars-poland-peer-nva2-learned.json

# Capture c1-ep effective routes BEFORE change
az network nic show-effective-route-table \
  -g "$RG" -n nic-vm-c1-ep \
  -o json > show-output/post-delta3/00-pre-map-effective-routes-c1-ep.json

# Show existing route maps (should be empty)
az rest --method GET \
  --url "https://management.azure.com/subscriptions/{sub}/resourceGroups/$RG/providers/Microsoft.Network/virtualHubs/$ARS/routeMaps?api-version=2024-05-01" \
  -o json
```
> **Expected:** `list-learned-routes` shows `"asPath":"65002"` for 0.0.0.0/0 from NVA2; effective routes show ECMP `["10.10.1.4","10.20.1.4"]`; no existing route maps.

### STEP 1 — Create Route Map with Rule (PowerShell — recommended for preview feature)
```powershell
# Requires Az.Network >= 8.0.0
Import-Module Az.Network

$criterion = New-AzRouteMapRuleCriterion `
  -MatchCondition "Equals" `
  -RoutePrefix @("0.0.0.0/0")

$actionParam = New-AzRouteMapRuleActionParameter `
  -AsPath @("64496", "64496")

$action = New-AzRouteMapRuleAction `
  -Type "Add" `
  -Parameter @($actionParam)

$rule = New-AzRouteMapRule `
  -Name $RULE_NAME `
  -MatchCriteria @($criterion) `
  -RouteMapRuleAction @($action) `
  -NextStepIfMatched "Terminate"

New-AzRouteMap `
  -ResourceGroupName $RG `
  -VirtualHubName $ARS `
  -Name $MAP_NAME `
  -RouteMapRule @($rule)
```

**Expected output:** `ProvisioningState: Updating` initially → then `Succeeded`. If this is the first route map on `ars-poland`, the ARS itself will go into `Updating` state for **~30 minutes**. This is normal.

### STEP 2 — Monitor ARS Upgrade (poll every 60 s, up to 40 min)
```bash
# Azure CLI poll loop
for i in $(seq 1 40); do
  STATE=$(az network routeserver show -g "$RG" -n "$ARS" --query provisioningState -o tsv)
  MAP_STATE=$(az network routeserver show -g "$RG" -n "$ARS" --query "routeMaps[0].provisioningState" -o tsv 2>/dev/null || echo "checking...")
  echo "$(date -u +%H:%M:%S) ARS: $STATE  Map: $MAP_STATE"
  [ "$STATE" = "Succeeded" ] && break
  sleep 60
done
```

**Do NOT proceed to Step 3 until ARS provisioningState = Succeeded.**

### STEP 3 — Apply Route Map to peer-nva2 Inbound Direction (PowerShell)
```powershell
# Get the route map resource ID
$map = Get-AzRouteMap -ResourceGroupName $RG -VirtualHubName $ARS -Name $MAP_NAME

# Get the BGP peering connection resource ID for peer-nva2
# The connection resource ID format for ARS BGP peering:
#   /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Network/virtualHubs/{ars}/bgpConnections/{peering}
$sub = (Get-AzContext).Subscription.Id
$peeringId = "/subscriptions/$sub/resourceGroups/$RG/providers/Microsoft.Network/virtualHubs/$ARS/bgpConnections/$PEERING"

Update-AzRouteMap `
  -ResourceGroupName $RG `
  -VirtualHubName $ARS `
  -Name $MAP_NAME `
  -InboundConnection @($peeringId)
```

> **Alternative — Azure portal:** Route Server → Settings → route maps → Apply route maps → select `rm-poland-nva2-default-prepend` as Inbound for `peer-nva2` → Save.

### STEP 4 — Wait for Convergence (~5 min after apply)
```bash
sleep 300
```

### STEP 5 — Post-Check (S4 assertions)
```bash
mkdir -p show-output/post-delta3

# A) Verify route map applied and AS-PATH is modified
az network routeserver peering list-learned-routes \
  -g "$RG" --routeserver "$ARS" -n "$PEERING" \
  -o json > show-output/post-delta3/01-post-map-ars-poland-peer-nva2-learned.json

# Expected: 0.0.0.0/0 asPath = "65002 64496 64496" (3 ASNs)

az network routeserver peering list-learned-routes \
  -g "$RG" --routeserver "$ARS" -n "peer-nva1" \
  -o json > show-output/post-delta3/02-post-map-ars-poland-peer-nva1-learned.json

# Expected: 0.0.0.0/0 asPath = "65001" (1 ASN, unchanged)

# B) Verify c1-ep 0/0 now points to NVA1 only (no ECMP)
az network nic show-effective-route-table \
  -g "$RG" -n nic-vm-c1-ep \
  -o json > show-output/post-delta3/03-post-map-effective-routes-c1-ep.json

# Expected: 0.0.0.0/0 nextHopIpAddress = ["10.10.1.4"] (NVA1 only, not ECMP)

# C) Verify DEF-001 resolved: hub1-ep → c1-ep ping should now pass
az vm run-command invoke \
  -g "$RG" -n vm-hub1-ep \
  --command-id RunShellScript \
  --scripts "ping -c 5 10.31.0.4" \
  -o json > show-output/post-delta3/04-ping-hub1ep-to-c1ep-post-delta3.json

# Expected: 0% loss

# D) Confirm Δ1/Δ2 preserved (on-prem still prefers hub1 for set-C spoke prefixes)
az network vnet-gateway list-learned-routes \
  -g "$RG" -n vpngw-onprem \
  -o json > show-output/post-delta3/05-vpngw-onprem-learned-routes-post-delta3.json

# Expected: 10.31.0.0/24 via hub1 "[65515-65001]" still preferred over hub2 "[65515-65002-65002-65002]"
```

### STEP 6 — S4 PASS/FAIL Criteria

| Check | Command | Expected | PASS condition |
|---|---|---|---|
| NVA2 AS-PATH lengthened | `list-learned-routes peer-nva2` | `0.0.0.0/0` asPath = `"65002 64496 64496"` | Exact match |
| NVA1 AS-PATH unchanged | `list-learned-routes peer-nva1` | `0.0.0.0/0` asPath = `"65001"` | Exact match |
| c1-ep 0/0 single next-hop | `show-effective-route-table nic-vm-c1-ep` | `nextHopIpAddress = ["10.10.1.4"]` | Single IP, NVA1 |
| DEF-001 resolved | ping hub1-ep → c1-ep | 0% loss | 0% loss over 5 packets |
| Δ1/Δ2 preserved | `vpngw-onprem list-learned-routes` | 10.31/24 best = hub1 `[65515-65001]` | hub1 preferred |
| ARS provisioningState | `az network routeserver show` | `Succeeded` | Succeeded |

---

## 4. DEF-001 Resolution Analysis

**DEF-001 root cause** (baseline-confirmed): `vm-c1-ep` has ECMP `0/0 → [10.10.1.4, 10.20.1.4]`. Return traffic from c1 (10.31.0.x) to hub1-ep (10.11.0.x) is load-balanced ~50% to NVA2, which has no route to 10.11.0.0/24 (hub1/spoke-a) → DROP.

**Δ3 resolution mechanism:**
1. Inbound map on `peer-nva2` adds `[64496, 64496]` to NVA2's `0/0` AS-PATH
2. ars-poland best-path: NVA1 `[65001]` length 1 < NVA2 `[65002,64496,64496]` length 3 → NVA1 wins
3. ARS injects `0/0 → 10.10.1.4` (NVA1 only) into set-C spoke effective routes
4. All c1-ep return traffic uses NVA1 → NVA1 knows 10.11.0.0/24 (hub1 VNetPeering) → PASS
5. **DEF-001 expected resolved** ✅

**Δ1/Δ2 preservation:** Δ3 operates only on inbound learned-routes at ars-poland from peer-nva2, scoped to prefix `0.0.0.0/0` only. It does not touch:
- NVA-originated hub-subnet prefixes (10.20.0.64/27, 10.20.1.0/27) — not matched
- Any routes in ars-hub1, ars-hub2 — different ARS instances, unaffected
- on-prem VPN GW RIB — Δ2 prepend on NVA2→ars-hub2 for set-C spokes is unchanged
- VNet-native address prefixes — route maps cannot modify these (platform restriction)

**Δ1/Δ2 fully preserved.** ✅

---

## 5. Rollback Contract

If post-check FAILS or unexpected behavior observed:

### Rollback — Remove map from peering (PowerShell)
```powershell
# Detach route map from peer-nva2 inbound (set InboundConnection to empty)
Update-AzRouteMap `
  -ResourceGroupName $RG `
  -VirtualHubName $ARS `
  -Name $MAP_NAME `
  -InboundConnection @()
```

### Rollback — Delete route map entirely
```powershell
Remove-AzRouteMap `
  -ResourceGroupName $RG `
  -VirtualHubName $ARS `
  -Name $MAP_NAME
```

### Post-rollback verification
```bash
az network routeserver peering list-learned-routes \
  -g "$RG" --routeserver "$ARS" -n "$PEERING" -o json
# Expected: 0.0.0.0/0 asPath = "65002" (1 hop, ECMP restored to baseline)

az network nic show-effective-route-table -g "$RG" -n nic-vm-c1-ep -o json
# Expected: 0.0.0.0/0 nextHopIpAddress = ["10.10.1.4","10.20.1.4"] (ECMP restored)
```

**Note:** Removing a route map does NOT trigger another 30-minute upgrade. The ARS stays at the upgraded tier. The ~$6/day route-map surcharge continues while the feature is provisioned (even if maps are detached from peerings). To fully remove surcharge, delete the ARS and re-create — not recommended for live lab.

---

## 6. API Versions and Module Requirements

| Tool | Version | Notes |
|---|---|---|
| Az.Network PowerShell module | **≥ 8.0.0** | Required for `New-AzRouteMap`, `New-AzRouteMapRule*` cmdlets |
| ARM REST API | `2024-05-01` | Latest stable supporting routeMaps sub-resource on virtualHubs |
| Azure CLI `az network routeserver` | Current (2.x) | CLI route map support may be portal/PS-only in preview; use PS |
| `New-AzRouteMapRuleCriterion` | Az.Network 8.0+ | `-MatchCondition "Equals"` for exact prefix |
| `New-AzRouteMapRuleActionParameter` | Az.Network 8.0+ | `-AsPath @("64496","64496")` |
| `New-AzRouteMapRuleAction` | Az.Network 8.0+ | `-Type "Add"` = prepend |
| `New-AzRouteMap` | Az.Network 8.0+ | `-VirtualHubName` = ARS name |
| `Update-AzRouteMap` | Az.Network 8.0+ | Apply via `-InboundConnection` |

**Verify Az.Network version before starting:**
```powershell
Get-Module Az.Network -ListAvailable | Select-Object Name, Version
# Must show 8.0.0 or later. If not: Update-Module Az.Network
```

---

## 7. Cost Note

- Baseline: ~$65.86/day  
- With Δ3 active: ~$72/day (+~$6/day route-map surcharge)  
- Jose Moreno explicitly waived the $50/day guardrail. Approved manifest cost $72/day on record.  
- Once ARS is upgraded (first map created), surcharge persists regardless of rule state. No further approval action needed.

---

## 8. Summary Decision

> **APPROVED ACTIVATION CONTRACT** ✅  
> Δ3 is expected to resolve DEF-001 by breaking ECMP at ars-poland to single-path NVA1.  
> Δ1/Δ2 are fully preserved. on-prem preference for hub1 for set-C spokes is unchanged.  
> Exact PowerShell commands above are ready for Tank to execute as-is.  
> No IaC authored. No live changes made by Trinity.
