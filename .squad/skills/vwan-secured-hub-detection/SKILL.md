# SKILL: vWAN Secured-Hub & Routing Intent Detection

**Author:** Niobe  
**Created:** 2026-07-30T13:35:49+02:00  
**Applies to:** Any lab using Azure Virtual WAN with potential Azure Firewall / Routing Intent (Phase 3 style)

---

## Purpose

Detect whether a vWAN hub is a **secured virtual hub** (Azure Firewall embedded) and whether **Routing Intent** is configured, as evidence that Phase 3 work has started.

---

## Detection Commands

### 1. Check for Azure Firewalls in RG

```bash
az network firewall list -g <resource-group> -o table
```
- Empty output = no firewalls = Phase 3 NOT started.
- Non-empty = firewall exists; check which hub it's associated with.

### 2. Check for Firewall Policies

```bash
az network firewall policy list -g <resource-group> -o table
```
- Firewall policies may exist without a deployed firewall (pre-staged). Empty = Phase 3 not started.

### 3. Check Hub Secure State (firewall association)

```bash
az network vhub show -g <resource-group> -n <hub-name> \
  --query "{name:name,azureFirewall:azureFirewall,securityProviderName:securityProviderName,sku:sku,provisioningState:provisioningState}" \
  -o json
```
- `azureFirewall: null` → hub is NOT secured.
- `azureFirewall: {id: "/subscriptions/..."}` → hub IS secured (firewall deployed).
- `sku` will be `"Standard"` for a secured hub; may be `null` for plain hub.

### 4. Check Routing Intent (PREVIEW command)

```bash
# NOTE: Use --vhub (not --vhub-name) for this preview command
az network vhub routing-intent list -g <resource-group> --vhub <hub-name> -o json
```
- `[]` = no routing intent configured.
- Non-empty JSON = routing intent exists; inspect `routingPolicies` for `InternetTraffic` / `PrivateTraffic` and their `nextHop` (should point to an Azure Firewall resource ID).

**CLI gotcha:** The flag is `--vhub`, NOT `--vhub-name`. Using `--vhub-name` returns: `ERROR: the following arguments are required: --vhub`

### 5. Quick 3-hub sweep (loop)

```bash
for hub in hub-us hub-eu1 hub-eu2; do
  echo "=== $hub ==="
  az network vhub routing-intent list -g routemap-test-rg --vhub $hub -o json
done
```

---

## Interpretation Matrix

| azureFirewall | Routing Intent | Firewall resource | Phase 3 state |
|---------------|----------------|-------------------|---------------|
| null | [] | absent | NOT started |
| resource ID | [] | present | Partially started (FW deployed, RI not yet) |
| resource ID | policies present | present | Fully started |
| null | [] | absent (but policy exists) | Pre-staged only |

---

## Expected Secured-Hub vs Non-Secured Hub Diff

**Non-secured hub** (`az network vhub show`):
```json
{
  "azureFirewall": null,
  "securityProviderName": null,
  "sku": null
}
```

**Secured hub:**
```json
{
  "azureFirewall": { "id": "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/.../azureFirewalls/azfw-hub-us" },
  "securityProviderName": null,
  "sku": "Standard"
}
```

---

## Additional Gotcha: ExpressRoute Gateway Connections Field

When auditing ER gateways via `az network express-route gateway show`, the connections field
is named `expressRouteConnections`, NOT `connections`.

**Wrong query (returns null):**
```bash
az network express-route gateway show -g <rg> -n <gw> --query "connections" -o json
# Returns: null  (even when connections exist!)
```

**Correct query:**
```bash
az network express-route gateway show -g <rg> -n <gw> \
  --query "{name:name,provisioningState:provisioningState,connections:expressRouteConnections[].{name:name,provisioningState:provisioningState}}" \
  -o json
# Returns actual connections list
```

**Quick diagnostic:**
```bash
# Dump full JSON and search for connection entries to find correct field names
az network express-route gateway show -g <rg> -n <gw> -o json | findstr -i "connection"
```

## NVA Post-Deallocation Startup Sequence

When NVAs using swanctl with if_id XFRM interfaces are deallocated and restarted:

1. **Load swanctl connections** (strongswan-starter uses ipsec.conf; swanctl.conf needs manual load):
   ```bash
   swanctl --load-all
   ```
2. **Initiate tunnels manually** (`start_action = trap` does NOT auto-connect):
   ```bash
   swanctl --initiate --child s2s0 --ike vng0
   swanctl --initiate --child s2s1 --ike vng1
   ```
3. **Recreate XFRM interfaces** (NOT persistent across reboots):
   ```bash
   ip link add xfrm41 type xfrm dev eth0 if_id 41
   ip link set xfrm41 up
   ip route add <hub-vpngw-instance0-ip>/32 dev xfrm41
   ip link add xfrm42 type xfrm dev eth0 if_id 42
   ip link set xfrm42 up
   ip route add <hub-vpngw-instance1-ip>/32 dev xfrm42
   ```
4. **Wait for BGP convergence** (~30-60 seconds after tunnel establishment).


When filing evidence for a Phase 3 audit:
- File `XX-phase3-audit-firewalls-and-routing-intent.txt` — results of commands 1–4 above for all hubs
- File `XX-phase3-audit-resource-inventory.txt` — `az resource list -g <rg> -o table` with type-count summary to show/absence of `Microsoft.Network/azureFirewalls` and `Microsoft.Network/firewallPolicies`
- Always redact subscription IDs to `<SUBSCRIPTION_ID>`
