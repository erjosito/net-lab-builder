# Phase 3 Design Spec — Secured Hubs + Routing Intent
## vwan-routemap-summarization

← Back to [README.md](README.md) | Results: [validation.md](validation.md)

**Author:** Trinity (Azure Network SME)  
**Date:** 2026-07-30  
**Status:** COMPLETE — all gates validated 2026-07-31.

---

## 0. Executive summary

Phase 3 converts hub-eu1 and hub-eu2 to secured virtual hubs (Azure Firewall Standard) and enables
Routing Intent (PrivateTraffic) on both. hub-us stays non-secured; it is a route source only and
not part of the customer's repro topology. The primary research question this phase answers:

> **Does enabling Routing Intent PrivateTraffic on a vWAN hub that carries a `summarize-out`
> route-map preserve the 6/6 summaries advertised to on-prem, or does the RFC1918 aggregate route
> installed by RI suppress the specific spoke /24s before the route-map evaluates them?**

Deploy firewall first (no RI). Niobe gates at each step. RI is enabled last, one hub at a time.

---

## 1. Which hubs get an Azure Firewall

| Hub | Region | Gets AzFW? | Rationale |
|-----|--------|------------|-----------|
| hub-eu1 | swedencentral | **YES** | Carries `summarize-out`; customer repro was on secured EU hub |
| hub-eu2 | westeurope | **YES** | Carries `summarize-out` + `prepend-in`; identical customer topology |
| hub-us | westus2 | **NO** | Route source only (spoke VNets); not part of customer's repro scenario; inter-hub routes still propagate from unsecured hub to secured EU hubs per RI documentation |

**Minimal-but-representative:** securing both EU hubs mirrors the exact customer topology (two regional
hubs with the same firewall placement). hub-us without a firewall is deliberately unsecured; the MS
docs confirm that routes from an unsecured remote hub propagate to secured local hubs when those remote
connections propagate to the secured hub's defaultRouteTable (which is the default behavior).

---

## 2. Firewall SKU

| Attribute | Decision |
|-----------|----------|
| SKU | **Standard** |
| Tier | **Standard** |
| Justification | Basic Azure Firewall is NOT supported in vWAN secured hubs — it is a VNet-only SKU. Standard is the cheapest SKU that works in vWAN. Premium adds IDPS and TLS inspection; this is a control-plane repro lab with no data-plane traffic, so Premium adds no value and ~2× cost. |

Reference: [vWAN feature matrix](https://learn.microsoft.com/en-us/azure/virtual-wan/virtual-wan-overview) confirms `Azure Firewall in hub: ✗ Basic, ✓ Standard`.

---

## 3. Firewall policy design

### 3.1 Policy topology

One **shared policy** (`azfwpol-routemap-lab`) for both EU hub firewalls.

Rationale:
- Lab has no differentiated per-hub security requirements.
- Shared policy reduces drift; single place to update if rules change during validation.
- Both firewalls are Standard tier; policy inheritance from a parent is not needed here.

Policy location: **swedencentral** (same region as hub-eu1; acceptable cross-region attachment to hub-eu2 — MS supports cross-region policy).

### 3.2 Rule collections

Control-plane repro lab — explicit allow-all is correct and expected. Eliminates AzFW as a causal variable for the route-map bug. Tighten only after Phase 3 repro complete.

| Rule Collection Group | Priority | Rule Collection | Action | Rules |
|-----------------------|----------|-----------------|--------|-------|
| DefaultRuleCollectionGroup | 100 | allow-all-lab | Allow | `*` → `*` / Any / `*` |

**VPN BGP note:** With RI PrivateTraffic, BGP TCP 179 (vpngw↔NVA) traverses AzFW. Allow-all covers this. No per-tunnel rule needed for Internet-based VPN (not encrypted ER).

---

## 4. Routing Intent plan — CRITICAL ANALYSIS

### 4.1 Per-hub RI decision

| Hub | InternetTraffic RI | PrivateTraffic RI | Rationale |
|-----|-------------------|------------------|-----------|
| hub-eu1 | **NO** | **YES** | No internet workloads; PrivateTraffic matches customer topology |
| hub-eu2 | **NO** | **YES** | Same |
| hub-us | N/A (no FW) | N/A | Non-secured hub |

### 4.2 What RI PrivateTraffic does to the defaultRouteTable

When RI PrivateTraffic is enabled (via Portal or Firewall Manager), the platform installs these
static routes in the hub's defaultRouteTable:

| Route name | Prefix(es) | Next hop |
|------------|-----------|---------|
| `_policy_PrivateTraffic` | `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` | AzFW (azfw-eu1 / azfw-eu2) |

These routes are for **forwarding only**. They direct private-destined packets through AzFW.
They do NOT, by themselves, define what is *advertised* to connected branches (VPN connections).

### 4.3 Route-map interaction analysis — THE CRITICAL QUESTION

#### Background

`summarize-out` is a per-connection outbound route-map on VPN connections (`cx-onprem1`,
`cx-onprem2`). It applies Replace rules (matchCondition: Contains on spoke /24s → output: summary
prefix) before the hub advertises routes to the NVAs. It operates at the
**per-connection advertisement layer**, not at the defaultRouteTable static-route layer.

#### (a) How RI interacts with summarize-out on egress

When RI PrivateTraffic is enabled, the hub installs `10.0.0.0/8`, `172.16.0.0/12`,
`192.168.0.0/16` in the defaultRouteTable for forwarding. Per MS docs (prefix-advertisement
section), vWAN still advertises **individual prefixes learned from remote hub connections** to
local on-premises when those remote hubs don't have RI. Since hub-us has no RI, spoke /24s
propagate via inter-hub to hub-eu1/eu2 → EU hubs still advertise spoke /24s to their VPN
connections → `summarize-out` route-map sees specifics → summaries produced.

**Expected behavior:** 6/6 summaries preserved after RI.

⚠️ **THE RISK:** The RI RFC1918 aggregate MAY suppress /24 advertisement before the route-map
evaluates them (implementation-level behavior, not fully documented). If so:
- Route-map `Contains` finds no /24s → no Replace rules fire → summaries absent
- This reproduces the customer's missing-summary observation in secured-hub environments
- **This is the PRIMARY MEASUREMENT OBJECTIVE of Phase 3**

**Sequencing implication:** Do NOT enable RI at the same time as the firewall. Enable RI after
the firewall-only gate so Niobe can isolate the causal step.

#### (b) Interaction with branch-to-branch VPN/NVA paths

With RI PrivateTraffic on EU hubs, branch-to-branch traffic (nva1 ↔ hub-eu1 ↔ inter-hub ↔
hub-eu2 ↔ nva2) traverses both EU hub AzFW instances. BGP control plane (TCP 179) between
vpngw-eu1/eu2 and nva1/nva2 also goes through AzFW → covered by allow-all rule.

#### (c) Interaction with active ER gateways

ER connections `conn-er-eu1`/`conn-er-eu2` are Succeeded (per validation.md 2026-07-30 
correction). ER circuits carry no routes currently → minimal impact. With RI, any ER-learned
routes would be forwarded through AzFW; allow-all covers this. ER-to-ER transit note: each EU
hub has ONE ER circuit — the "multiple ER circuits per hub requires support case" restriction
does NOT apply. Standard inter-hub transit works without a support case.

**prepend-in (hub-eu2):** Inbound route-map on VPN connection ingress. RI does not affect
how BGP routes are received from the VPN connection. No impact expected.

### 4.4 RI enablement ordering

Enable RI one hub at a time. This allows Niobe to isolate which hub's RI state causes a summary
to go missing (if the bug reproduces).

```
hub-eu1 RI enabled → validate both hubs → hub-eu2 RI enabled → validate both hubs
```

---

## 5. Subnet / address-space requirements per hub

**vWAN secured hubs do NOT require explicit AzureFirewallSubnet or
AzureFirewallManagementSubnet provisioning.** The hub manages firewall IP allocation internally
from the hub address prefix. The operator does NOT create subnets.

| Hub | Hub prefix | Current consumers | AzFW headroom | Adequate? |
|-----|------------|-------------------|---------------|-----------|
| hub-eu1 | 192.168.2.0/23 | vpngw-eu1 (GW IPs from /23), ergw-eu1 | Platform carves a /26 equiv from the /23 for AzFW instances | **YES** — /23 (512 addrs) is sufficient |
| hub-eu2 | 192.168.4.0/23 | vpngw-eu2, ergw-eu2 | Same | **YES** |

> Source: vWAN docs confirm that for hub-deployed AzFW, subnets are hub-managed and allocated from
> the hub's address prefix. No operator action on subnets.

**Verify remaining space before deploying:** `az network vhub show -g routemap-test-rg -n hub-eu1 --query addressPrefix`
should show 192.168.2.0/23. If a prefix conflict exists, stop and consult Morpheus.

---

## 6. Deploy sequence for Tank

Ordered, idempotent steps. All commands target resource group `routemap-test-rg`.
Subscription ID MUST NOT appear in commands — use `$(az account show --query id -o tsv)` inline
or `az` context is already scoped to the correct subscription.

### Prerequisites check (run before starting)

```bash
# Confirm no custom route tables exist (RI prereq)
az network vhub route-table list -g routemap-test-rg --vhub-name hub-eu1 -o table
az network vhub route-table list -g routemap-test-rg --vhub-name hub-eu2 -o table
# Expected: only defaultRouteTable and noneRouteTable

# Confirm no static routes with nextHop VNetConnection in defaultRouteTable
az network vhub route-table show -g routemap-test-rg --vhub-name hub-eu1 -n defaultRouteTable -o json
az network vhub route-table show -g routemap-test-rg --vhub-name hub-eu2 -n defaultRouteTable -o json
# If any route has "nextHop" pointing to a VNet connection, STOP — RI will be blocked

# Save current route-table state (rollback reference)
az network vhub route-table show -g routemap-test-rg --vhub-name hub-eu1 -n defaultRouteTable -o json > hub-eu1-defaultRT-pre-phase3.json
az network vhub route-table show -g routemap-test-rg --vhub-name hub-eu2 -n defaultRouteTable -o json > hub-eu2-defaultRT-pre-phase3.json
```

---

### Step 1 — Create shared Firewall Policy (< 2 min)

```bash
# 1a — Create policy
az network firewall policy create \
  -g routemap-test-rg \
  -n azfwpol-routemap-lab \
  --location swedencentral \
  --sku Standard \
  -o none

# 1b — Create default rule collection group
az network firewall policy rule-collection-group create \
  -g routemap-test-rg \
  --policy-name azfwpol-routemap-lab \
  -n DefaultRuleCollectionGroup \
  --priority 100 \
  -o none

# 1c — Add allow-all network rule collection
az network firewall policy rule-collection-group collection add-filter-collection \
  -g routemap-test-rg \
  --policy-name azfwpol-routemap-lab \
  --rule-collection-group-name DefaultRuleCollectionGroup \
  -n allow-all-lab \
  --collection-priority 100 \
  --action Allow \
  --rule-name allow-all \
  --rule-type NetworkRule \
  --protocols Any \
  --source-addresses '*' \
  --destination-addresses '*' \
  --destination-ports '*' \
  -o none

# Verify
az network firewall policy show -g routemap-test-rg -n azfwpol-routemap-lab --query "{name:name,sku:sku,provisioningState:provisioningState}" -o json
```

---

### Step 2 — Deploy Azure Firewalls into EU hubs (30–45 min; run in PARALLEL)

> ⚠️ AzFW provisioning into a vWAN hub takes 30–45 minutes. Start both in parallel (separate shells
> or background jobs) to minimize total wait. Do NOT proceed to Step 3 until BOTH are Succeeded.

```bash
# --- Shell A: hub-eu1 ---
az network firewall create \
  -g routemap-test-rg \
  -n azfw-eu1 \
  --location swedencentral \
  --sku AZFW_Hub \
  --tier Standard \
  --vhub hub-eu1 \
  --public-ip-count 1 \
  --firewall-policy azfwpol-routemap-lab \
  -o none

# --- Shell B: hub-eu2 ---
az network firewall create \
  -g routemap-test-rg \
  -n azfw-eu2 \
  --location westeurope \
  --sku AZFW_Hub \
  --tier Standard \
  --vhub hub-eu2 \
  --public-ip-count 1 \
  --firewall-policy azfwpol-routemap-lab \
  -o none
```

> **Alternative (Firewall Manager portal):** Navigate to Azure Firewall Manager → Virtual hubs →
> hub-eu1 → Configure security → Associate policy `azfwpol-routemap-lab`. Either method is
> acceptable; CLI is idempotent and scriptable.

---

### Step 3 — Verify secured hub state

```bash
for hub in hub-eu1 hub-eu2; do
  echo "=== $hub ==="
  az network vhub show -g routemap-test-rg -n $hub \
    --query "{name:name,azureFirewall:azureFirewall.id,sku:sku,provisioningState:provisioningState}" \
    -o json
done
# Expected: azureFirewall != null, provisioningState = Succeeded on both hubs
```

---

### *** NIOBE GATE A — Firewall deployed, NO Routing Intent yet ***
### See §8 (route-collection checklist) for the exact commands Niobe runs here.
### Gate passes if: 6/6 summaries on both hub-eu1 and hub-eu2 VPN connections.
### Gate fails if: any summary is missing → STOP; document and report to Jose.

---

### Step 4 — Enable Routing Intent on hub-eu1 (10–20 min)

```bash
# Get AzFW resource ID (avoids hardcoding subscription ID)
AZFW_EU1_ID=$(az network firewall show -g routemap-test-rg -n azfw-eu1 --query id -o tsv)

az network vhub routing-intent create \
  -g routemap-test-rg \
  --vhub hub-eu1 \
  -n hub-eu1-ri \
  --routing-policies "[{\"name\":\"PrivateTraffic\",\"destinations\":[\"PrivateTraffic\"],\"nextHop\":\"$AZFW_EU1_ID\"}]" \
  -o none

# Verify
az network vhub routing-intent list -g routemap-test-rg --vhub hub-eu1 -o json
# Expected: routingPolicies with PrivateTraffic → azfw-eu1
```

---

### *** NIOBE GATE B — RI on hub-eu1 only ***
### See §8. Gate passes if: 6/6 summaries on BOTH hubs (hub-eu1 AND hub-eu2 VPN connections).
### Gate fails → likely repro trigger found. Document exactly which summary(ies) missing on which hub.
### Hub-eu2 should be unaffected (RI not yet enabled there).

---

### Step 5 — Enable Routing Intent on hub-eu2 (10–20 min)

```bash
AZFW_EU2_ID=$(az network firewall show -g routemap-test-rg -n azfw-eu2 --query id -o tsv)

az network vhub routing-intent create \
  -g routemap-test-rg \
  --vhub hub-eu2 \
  -n hub-eu2-ri \
  --routing-policies "[{\"name\":\"PrivateTraffic\",\"destinations\":[\"PrivateTraffic\"],\"nextHop\":\"$AZFW_EU2_ID\"}]" \
  -o none

# Verify
az network vhub routing-intent list -g routemap-test-rg --vhub hub-eu2 -o json
```

---

### *** NIOBE GATE C — RI on both EU hubs (full Phase 3 steady state) ***
### See §8. PRIMARY REPRO CHECK.
### Expected if bug absent: 6/6 summaries on both hubs.
### Expected if bug present: ≥1 summary missing; document order-dependent pattern.

---

### Step 6 — Post-RI BGP health check

```bash
# Confirm NVA BGP sessions still ESTABLISHED (BGP traverses AzFW with allow-all rule)
# Run on nva1 and nva2 (via SSH or az vm run-command):
# birdc show protocols | grep -E 'vpngw|BGP'
# Expected: both vpngw0 and vpngw1 sessions = Established
```

---

### Rollback plan (if RI must be removed)

```bash
# IMPORTANT: RI changes to defaultRouteTable are NOT automatically reversed.
# Restore from pre-phase3 snapshots captured in Prerequisites step.
az network vhub routing-intent delete -g routemap-test-rg --vhub hub-eu1 -n hub-eu1-ri --yes
az network vhub routing-intent delete -g routemap-test-rg --vhub hub-eu2 -n hub-eu2-ri --yes
# Then manually restore defaultRouteTable routes from saved JSON snapshots.
```

---

## 7. Resiliency analysis (MANDATORY)

This section enumerates single-failure modes for the Phase 3 configuration. This is an **ephemeral
repro lab** — no SLA, no production workloads. Failure modes are catalogued to prevent inadvertent
destruction of repro state and to understand blast radius during validation.

### Failure mode table

| ID | Component | Failure mode | Azure-side reach lost | On-prem-side reach lost | Firewall-in-path consequence | Failover time | Operator action |
|----|-----------|-------------|----------------------|------------------------|------------------------------|---------------|----------------|
| F1 | azfw-eu1 | Single AzFW instance failure (platform-HA event) | Transient; AzFW is 2-instance Active-Active | nva1 may see brief BGP hold-down | RI routes traffic to failed instance transiently → TCP flows reset | ~1–2 min auto-recovery | None; monitor |
| F2 | azfw-eu1 | Full AzFW platform failure (both instances) | ALL private traffic on hub-eu1 blackholed (RI 10.0.0.0/8 route points to down FW) | nva1 BGP sessions drop (BGP TCP through AzFW); nva1 loses all Azure routes | Total hub-eu1 private connectivity loss | Platform recovery; no self-heal | Open Azure support case |
| F3 | azfw-eu2 | Same as F1/F2 for hub-eu2 | Same but hub-eu2 scope | nva2 BGP drops | Same | Same | Same |
| F4 | RI hub-eu1 | RI config state corruption | defaultRouteTable reverts to pre-RI state; private traffic routes direct (bypasses AzFW) | Routes still advertised; NVA connectivity may recover but AzFW inspection skipped | Traffic bypasses AzFW; route-maps still applied | — | Re-apply RI (idempotent Step 4) |
| F5 | vpngw-eu1 | VPN GW instance failure | nva1 VPN tunnels drop; BGP sessions drop | nva1 loses all Azure routes | AzFW still running; no new traffic to inspect | ~1–2 min auto-recovery (GW is Active-Active) | None; BGP reconverges |
| F6 | ergw-eu1 | ER GW failure | ER circuit er-eu1 disconnects | er-eu1 on-prem (if any) loses Azure reach | Not in critical path for Phase 3 repro | Auto-recovery | None for this lab |
| F7 | hub-us (non-secured) | vHub control plane | 12+ spoke VNets disconnect from hub-us; EU hubs stop receiving spoke /24 routes | nva1/nva2 lose all spoke summaries (no specifics → no route-map output) | Not relevant (AzFW still up but no routes through it) | Platform recovery | None; wait for hub-us recovery |
| F8 | inter-hub link eu1↔us | BGP session drop between hubs | hub-eu1 loses spoke route advertisements | nva1 loses spoke summaries; hub-eu2 unaffected | AzFW still up; just no spoke routes | BGP reconverges (minutes) | None; auto-recovery |
| F9 | firewall policy | Policy update error | AzFW enters degraded state; may allow or deny unexpected traffic | No route-map impact; control-plane continues | Traffic may be dropped/allowed unexpectedly | — | Fix policy; re-associate |

### Unacceptable blast radius for lab repro integrity

**F7 (hub-us failure)** has the largest blast radius relative to repro integrity: if hub-us fails
mid-measurement, Niobe loses all spoke routes and cannot distinguish "hub-us down" from "RI
suppressed summaries." Mitigation: Niobe should record hub-us health at each gate.

**F2 (full AzFW failure)** causes BGP session drops on nva1, losing the measurement point.
Mitigation: allow-all rule prevents any false-positive firewall-induced failure. AzFW full failure
is rare (platform HA); if it occurs during Niobe's measurement window, note it and re-run.

### Dormant patches (apply only if Jose authorizes)

| Patch | Description | Complexity | When to apply |
|-------|-------------|-----------|---------------|
| P1 | Add `az network firewall policy rule-collection-group collection add-nat-collection` to log BGP flows for F2 diagnosis | Low | If BGP drops are suspected (AzFW issue vs. platform issue) |
| P2 | Add AzFW diagnostic settings → Log Analytics for AzFWNetworkRule logging | Low | If allow-all proves insufficient and rule debugging is needed |

**Standing rule:** Do not modify deployed state while Tank deploy is in-flight. Apply patches only
at Niobe gate boundaries.

---

## 8. Route-collection checklist for Niobe

Three-layer collection at each gate. Capture to `show-output/` with sequential file numbering.

### Layer 1 — Azure control plane (per gate)

```bash
RG=routemap-test-rg

# L1a: Hub secured state (verify AzFW association + RI state)
for hub in hub-eu1 hub-eu2; do
  echo "=== HUB $hub ==="
  az network vhub show -g $RG -n $hub \
    --query "{name:name,azureFirewall:azureFirewall.id,sku:sku,provisioningState:provisioningState}" -o json
  az network vhub routing-intent list -g $RG --vhub $hub -o json
done

# L1b: Outbound effective routes per VPN connection — THE PRIMARY MEASUREMENT
# hub-eu1 VPN connection (cx-onprem1)
az network vhub route-map get-outbound-routes \
  -g $RG \
  --vhub-name hub-eu1 \
  --connection-type VpnConnection \
  --connection-name cx-onprem1 \
  -o json

# hub-eu2 VPN connection (cx-onprem2)
az network vhub route-map get-outbound-routes \
  -g $RG \
  --vhub-name hub-eu2 \
  --connection-type VpnConnection \
  --connection-name cx-onprem2 \
  -o json

# Summary check: count summaries (expect 6, no /24 leaks)
# Count summary routes (expect 6 entries: /16x4, /17x2)
# Count leaked /24s (expect 0)
```

```bash
# L1c: Route-map state — confirm summarize-out still applied
for hub in hub-eu1 hub-eu2; do
  az network vhub route-map list -g $RG --vhub-name $hub -o table
  az network vhub route-map show -g $RG --vhub-name $hub -n summarize-out -o json
done
# hub-eu2 also:
az network vhub route-map show -g $RG --vhub-name hub-eu2 -n prepend-in -o json
```

```bash
# L1d: Hub defaultRouteTable — capture before and after RI (shows RI-inserted routes)
for hub in hub-eu1 hub-eu2; do
  az network vhub route-table show -g $RG --vhub-name $hub -n defaultRouteTable -o json
done
# Compare pre-RI (from Prerequisites snapshot) vs post-RI
# After RI: expect _policy_PrivateTraffic with 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
```

```bash
# L1e: Firewall provisioning state
az network firewall show -g $RG -n azfw-eu1 --query "{name:name,provisioningState:provisioningState,hubIpAddresses:hubIpAddresses}" -o json
az network firewall show -g $RG -n azfw-eu2 --query "{name:name,provisioningState:provisioningState,hubIpAddresses:hubIpAddresses}" -o json
```

### Layer 2 — NVA RIB (per gate)

```bash
# On nva1 and nva2 (SSH or az vm run-command):
birdc show route where net ~ [10.0.0.0/8]  # summaries or /24s?
birdc show protocols                         # BGP Established?
birdc show route count
# Pass: 6 summary routes, 0 /24 specifics; all BGP sessions Established
# nva2: confirm AS-path has prepended ASNs (prepend-in still applied)
```

### Layer 3 — VNet effective routes (optional)

```bash
# Not strictly needed for control-plane repro; useful if VNet reachability is tested
# az network nic show-effective-route-table -g $RG -n <spoke-nic> -o table
```

### Measurement matrix per gate

| Gate | Measurement | Pass criteria | Fail action |
|------|-------------|---------------|-------------|
| A (FW deployed, no RI) | L1b get-outbound-routes, L2 BIRD | 6/6 summaries on both hubs; 0 /24 leaks; BGP Established | STOP — firewall alone broke route-maps. Investigate policy/AzFW provisioning |
| B (RI on hub-eu1 only) | L1b both hubs, L1d defaultRT, L2 both NVAs | 6/6 on BOTH hubs | If missing: RI on eu1 is the trigger. Document which summary missing, on which hub/NVA. Continue to Gate C anyway? Only if Jose authorizes. |
| C (RI on both hubs — full state) | L1b, L1c, L1d, L2, L1e | 6/6 on both hubs; no /24 leaks | PRIMARY REPRO. Document fully: hub/connection/summary index/NVA evidence |

### Specific comparison commands

```bash
# Summarize-out rule order (to repeat rule-order sensitivity from Phase 1)
az network vhub route-map show -g $RG --vhub-name hub-eu1 -n summarize-out \
  --query "rules[].{name:name,matchCriteria:matchCriteria,actions:actions}" -o json

# Before/after RI on hub-eu1: compare defaultRT
diff hub-eu1-defaultRT-pre-phase3.json \
  <(az network vhub route-table show -g $RG --vhub-name hub-eu1 -n defaultRouteTable -o json)
```

---

## 9. Known risks and gotchas

| Risk | Severity | Details |
|------|----------|---------|
| RI RFC1918 aggregate suppresses spoke /24 advertisement | HIGH | If true, route-map sees no specifics → 0 summaries. Primary research question. |
| BGP drops after RI enablement | HIGH | BGP TCP 179 traverses AzFW. Missing allow-all = sessions drop. Verify policy before enabling RI. |
| RI defaultRouteTable changes are irreversible | MEDIUM | Per MS docs. Save snapshot in Prerequisites step. Rollback = manual restore. |
| NVAs must be started | MEDIUM | Currently deallocated. Must start + recreate XFRM interfaces + initiate tunnels before measurement (see vwan-secured-hub-detection SKILL.md). |
| ER connections active (conn-er-eu1/eu2 Succeeded) | LOW | Carry no routes now; no impact until ER on-prem is connected. |
| Cross-region policy (swedencentral policy → westeurope hub-eu2) | LOW | Supported by Azure. No functional impact for lab. |

---

## 10. Resource summary

| Resource | Name | Type | Region | New in Phase 3? |
|----------|------|------|--------|----------------|
| Firewall Policy | azfwpol-routemap-lab | Microsoft.Network/firewallPolicies | swedencentral | YES |
| Azure Firewall | azfw-eu1 | Microsoft.Network/azureFirewalls | swedencentral | YES |
| Azure Firewall | azfw-eu2 | Microsoft.Network/azureFirewalls | westeurope | YES |
| Routing Intent | hub-eu1-ri | (hub child resource) | swedencentral | YES |
| Routing Intent | hub-eu2-ri | (hub child resource) | westeurope | YES |

Estimated additional cost: ~$3.50/hr (2× AzFW Standard in vWAN hub = ~2× $1.25/hr fixed + data processing). Lab should run 2–4 hours for full validation; total Phase 3 incremental cost ~$7–$14.

---

*Trinity — Azure Network SME*  
*Design-only. Tank deploys. Niobe validates.*

---

## Gate C Result + Gate D Proposal (concurrent-churn)

**Date:** 2026-07-31  **Verdict:** FULL PASS — missing-summary bug NOT reproduced.

### Root-cause of negative result

RI PrivateTraffic and `summarize-out` operate on **orthogonal planes**:

| Layer | Mechanism | Scope |
|-------|-----------|-------|
| RI `_policy_PrivateTraffic` | RFC1918 aggregates in defaultRouteTable → next-hop AzFW | **Data-plane / forwarding** |
| `summarize-out` | Per-connection BGP outbound advertisement set; matches hub-us inter-hub /24s | **Control-plane / BGP advertisement** |

Hub VPN gateway advertisement set derives from **learned BGP routes**, not defaultRouteTable static entries. RI's aggregate is a forwarding directive — invisible to the BGP advertisement pipeline. hub-us (no RI) propagates spoke /24 specifics individually → `Contains` fires → summaries produced. Proof: nva1 BGP timestamps unchanged across all three gates (never reset).

**Methodology gap:** RI applied to a fully converged hub with stable BGP and no concurrent connection churn. Production conditions may differ.

### Gate D — Concurrent-churn variant (DORMANT — await Jose "run Gate D")

**Hypothesis:** Bug fires when RI policy-install races with VPN connection reconvergence. Hub recomputes per-connection advertisement export during RI programming; concurrent BGP session teardown leaves /24 specifics transiently absent from route-map input. Cached zero-match result persists → missing summary after reconvergence. **F-matrix:** F5 (VPN GW reconvergence) + F4 (RI config mid-churn) concurrent.

| Step | Actor | Action | Timing |
|------|-------|--------|--------|
| D0 | Niobe | Confirm 6/6 baseline (Gate C state) | T−5 min |
| D1 | Niobe | Poll nva2 BIRD RIB every 30 s; log timestamps | T=0 |
| D2 | Tank | `sudo swanctl --terminate` on nva2 | T=0 |
| D3 | Tank | **Concurrently** delete+recreate hub-eu2 RI (< 30 s after D2) | T=+30 s |
| D4 | Niobe | Continue polls through reconvergence | T+0 → T+10 min |
| D5 | Tank | `sudo swanctl --initiate` after RI Succeeded | T = RI done |
| D6 | Niobe | Final RIB on nva2 + nva1 (hub-eu1 control). 6/6 or missing? | T+15 min |
| D7 | Niobe/Tank | If no repro: repeat on hub-eu1 / nva1 | T+20 min |

**Repro signal:** Summary absent from BIRD RIB AFTER BGP reconverges (vpngw0+vpngw1 Established) AND RI Succeeded. Transient miss during churn = noise; persistent miss = customer bug.

**Alternative churn trigger:** Disable a Megaport VXC BGP session for 60 s while RI is reprovisioned (if credentials available — exercises ER path, closer to production "re-provision").

**Cost:** ~$0.10 incremental (30–45 min AzFW runtime; no new resources).

**Residual gaps after Gate D:** cross-hub variant (hub-eu1 RI churn + hub-eu2 VPN); VPN GW-side restart; RI enable on fresh hub with in-flight connection.

**Vault backfill: HOLD.** Lab still live; vault update blocked until Jose-authorized teardown.
