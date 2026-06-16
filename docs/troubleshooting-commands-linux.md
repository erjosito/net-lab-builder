# Network troubleshooting commands — quick reference

> 📖 Windows / PowerShell users: see [`troubleshooting-commands-windows.md`](./troubleshooting-commands-windows.md) for PS-specific syntax (curl alias trap, `$env:VAR`, backslash→backtick line continuation).

A human-facing cheat sheet for the network layers `net-lab-builder` touches: Azure (vWAN, ExpressRoute, VPN, AzFW), Megaport (MCR, VXC), GCP (Cloud Router, Interconnect), Linux NVAs. Every command is shaped for **table-formatted output via `jq`** so you can eyeball state without scrolling JSON.

This page is the canonical command reference. **If a command on this page is wrong, fix it in place** — see `docs/README.md` for contribution rules.

## Conventions

These shell variables are assumed to exist. Adapt names to your lab.

```bash
# Azure
export RG=rg-vwan-symm-103167
export VHUB1=vhub-...
export ERGW1=ergw-vhub1-...
export ERCKT1=erckt-vhub1-...
export AZFW1=azfw-vhub1-...
export NIC=nic-spoke1-...
export VPNGW1=vpngw-vhub1-...

# Megaport (HTTP API token via /v2/login)
export MP_TOKEN=ey...
export MCR1_UID=00000000-0000-0000-0000-000000000000
export VXC_UID=00000000-0000-0000-0000-000000000000
export MP_API=https://api.megaport.com

# GCP
export GCP_PROJECT=gcp-vwan-symm-103167
export ROUTER_A=router-vwan-symm-a
export REGION_A=europe-west3
```

**Placeholder convention:** Commands in this document use `<YOUR_...>` tokens for values that vary per lab (e.g., `<YOUR_VPC>`, `<YOUR_ATTACHMENT_NAME>`, `<YOUR_VM_NAME>`). Replace these with your actual resource names before running commands.

**jq tip:** prefix any `gcloud`/`az`/`curl` command with `-o json` (Azure CLI) or `--format=json` (gcloud) and pipe to `jq -r '… | @tsv'`. `@tsv` beats manual `join("\t")` because it escapes embedded tabs/newlines.

---

## 1. Azure CLI — Virtual WAN

| Goal | Command |
|---|---|
| List vHubs in a RG | `az network vhub list -g $RG -o table` |
| Effective routes on vHub (default route table) | `az network vhub get-effective-routes -g $RG -n $VHUB1 --resource-type RouteTable --resource-id $(az network vhub route-table show -g $RG --vhub-name $VHUB1 -n defaultRouteTable --query id -o tsv) -o json \| jq -r '.value[] \| [.addressPrefixes[0], .nextHopType, (.nextHops \| join(",")), .asPath] \| @tsv'` |
| Effective routes from one connection's perspective | `az network vhub get-effective-routes -g $RG -n $VHUB1 --resource-type ExpressRouteConnection --resource-id <conn-id>` |
| List all vHub connections (VNet, ER, VPN) | `az network vhub connection list -g $RG --vhub-name $VHUB1 -o table` |
| Hub route-table propagation map | `az network vhub route-table show -g $RG --vhub-name $VHUB1 -n defaultRouteTable -o json \| jq '.labels, .propagatingConnections'` |

**Gotcha:** `get-effective-routes` may briefly return `{"value":[]}` for vWAN secured hubs even when MSEE routes are fully present — fresh hubs (< 10 min) or mid-publish route intents trigger it. Retry every 30 s for up to 5 min before chasing a real bug. The MSEE route-table evidence (§3) is the authoritative Azure-layer fallback. (Confirmed `labs/vwan-dual-er-symmetric/`, 2026-06-15.)

---

## 2. Azure CLI — ExpressRoute Gateway

Use `vnet-gateway` for classic VNet-attached ER gateways; use `vhub bgpconnection` for vWAN-hub-attached ER.

| Goal | Command |
|---|---|
| Learned routes on classic ER GW | `az network vnet-gateway list-learned-routes -g $RG -n $ERGW1 -o json \| jq -r '.value[] \| [.network, .nextHop, .sourcePeer, .origin, .asPath, .weight] \| @tsv'` |
| Advertised routes to one BGP peer | `az network vnet-gateway list-advertised-routes -g $RG -n $ERGW1 --peer 169.254.21.1 -o json \| jq -r '.value[] \| [.network, .asPath] \| @tsv'` |
| BGP peer status on classic ER GW | `az network vnet-gateway list-bgp-peer-status -g $RG -n $ERGW1 -o table` |
| List ER connections on vHub gateway | `az network express-route gateway connection list -g $RG --gateway-name $ERGW1 -o table` |
| vWAN-hub-side BGP peers (newer API) | `az network vhub bgpconnection list -g $RG --vhub-name $VHUB1 -o table` |

**Gotcha:** `list-learned-routes` returns up to ~500 routes per call. For large tables, filter at jq with `select(.network | startswith("10."))`. The `asPath` field is a single space-separated string — split with `(.asPath | split(" "))` if you need to compute hop count.

---

## 3. Azure CLI — ExpressRoute Circuit

| Goal | Command |
|---|---|
| List circuits in subscription | `az network express-route list -o table` |
| Circuit state + bandwidth + provider | `az network express-route show -g $RG -n $ERCKT1 -o json \| jq '{name, serviceProviderProvisioningState, circuitProvisioningState, bandwidthInMbps, sku:.sku.tier, peerings:[.peerings[].name]}'` |
| Private peering route table — primary path | `az network express-route list-route-tables -g $RG -n $ERCKT1 --peering-name AzurePrivatePeering --path primary -o json \| jq -r '.value[] \| [.network, .nextHop, .locPrf, .weight, .path] \| @tsv'` |
| Same — secondary path | `az network express-route list-route-tables -g $RG -n $ERCKT1 --peering-name AzurePrivatePeering --path secondary -o json \| jq -r '.value[] \| [.network, .nextHop, .locPrf, .weight, .path] \| @tsv'` |
| Route table summary (prefix count + next-hop ASN distribution) | `az network express-route list-route-tables-summary -g $RG -n $ERCKT1 --peering-name AzurePrivatePeering --path primary -o table` |
| ARP table on primary peering | `az network express-route list-arp-tables -g $RG -n $ERCKT1 --peering-name AzurePrivatePeering --path primary -o table` |
| List peerings on a circuit | `az network express-route peering list -g $RG --circuit-name $ERCKT1 -o table` |
| Peering details (BGP IPs, ASN, MD5 presence) | `az network express-route peering show -g $RG --circuit-name $ERCKT1 -n AzurePrivatePeering -o json \| jq '{state, peerASN, primaryPeerAddressPrefix, secondaryPeerAddressPrefix, vlanId, sharedKey: (if .sharedKey then "<set>" else null end)}'` |

**Gotcha #1 — `-o table` is broken for route tables.** `az network express-route list-route-tables -o table` prints headers with empty rows. **Always use `-o json`** and pipe to jq.

**Gotcha #2 — circuit `Provisioned` ≠ BGP session up.** If the circuit reports `Provisioned` but `list-route-tables` returns `"BGP sessions are not enabled"`, give it ~60 s after Megaport hand-off; the MSEE peering takes longer to come up than the circuit provisioning signal.

**Gotcha #3 — `.path` is the AS-path, not the URL parameter.** The output field `.path` is the route's BGP AS-path string like `65515 65520 65520 E`. The trailing letter is the origin attribute (`E` = EBGP, `I` = IBGP, `?` = incomplete). Easy to confuse with the `--path primary` query parameter.

**Gotcha #4 — vWAN-hub ER circuits.** When the ER circuit is attached to a vWAN hub (not a classic VNet GW), the MSEE route-table CLI still works the same way — it queries the circuit-side BGP table, not the Azure GW.

---

## 4. Azure CLI — VPN Gateway (S2S/P2S)

| Goal | Command |
|---|---|
| List VPN connections | `az network vpn-connection list -g $RG -o table` |
| Connection state (tunnel up/down, BGP up/down, bytes) | `az network vpn-connection show -g $RG -n <conn-name> -o json \| jq '{name, connectionStatus, ingressBytes:.ingressBytesTransferred, egressBytes:.egressBytesTransferred, enableBgp}'` |
| Learned routes on VPN GW | `az network vnet-gateway list-learned-routes -g $RG -n $VPNGW1 -o json \| jq -r '.value[] \| [.network, .nextHop, .asPath] \| @tsv'` |
| BGP peer status on VPN GW | `az network vnet-gateway list-bgp-peer-status -g $RG -n $VPNGW1 -o table` |

---

## 5. Azure CLI — Azure Firewall

| Goal | Command |
|---|---|
| List firewalls in RG | `az network firewall list -g $RG -o table` |
| Firewall public + private IPs | `az network firewall show -g $RG -n $AZFW1 -o json \| jq -r '.ipConfigurations[] \| [.name, .privateIPAddress, (.publicIPAddress.id // "-")] \| @tsv'` |
| Rule collection groups (Policy mode) | `az network firewall policy rule-collection-group list --policy-name <policy> -g $RG -o table` |
| Inspect one rule collection (verbose) | `az network firewall policy rule-collection-group show --policy-name <policy> -g $RG -n <rcg> -o json \| jq '.ruleCollections[] \| {name, priority, action:.action.type, rules:[.rules[].name]}'` |

**Runtime hit counters / flow logs:** Azure Firewall doesn't expose rule-hit counts via CLI. Use Log Analytics KQL — see `AZFWNetworkRule`, `AZFWApplicationRule`, `AZFWNatRule` tables. CLI surface only shows configuration.

---

## 6. Azure CLI — VM NIC

| Goal | Command |
|---|---|
| Effective routes on a NIC | `az network nic show-effective-route-table -g $RG -n $NIC -o json \| jq -r '.value[] \| [.addressPrefix[0], .nextHopType, (.nextHopIpAddress // "-"), .source, .state] \| @tsv'` |
| Effective NSG rules on a NIC (which rules match) | `az network nic list-effective-nsg -g $RG -n $NIC -o json \| jq '.value[].effectiveSecurityRules[] \| {name, direction, access, priority, sourceAddressPrefix, destinationAddressPrefix, destinationPortRange}'` |

**Gotcha:** `show-effective-route-table` requires the VM to be **running**. Stopped (deallocated) VMs return `"NIC must be associated with a running VM"`.

---

## 7. Megaport HTTP API — auth + MCR + VXC

Megaport has no first-party CLI we trust for this surface area. Use the HTTP API. Get a session token first:

```bash
export MP_TOKEN=$(curl -s -X POST "$MP_API/v2/login" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d "username=$MP_USER&password=$MP_PASS" | jq -r '.data.session')
```

| Goal | Command |
|---|---|
| List MCRs in account | `curl -s -H "X-Auth-Token: $MP_TOKEN" "$MP_API/v2/products" \| jq -r '.data[] \| select(.productType=="MCR2") \| [.productUid, .productName, .provisioningStatus, .locationDetail.name] \| @tsv'` |
| Show one MCR (config + interfaces) | `curl -s -H "X-Auth-Token: $MP_TOKEN" "$MP_API/v2/product/$MCR1_UID" \| jq '{name:.data.productName, status:.data.provisioningStatus, asn:.data.config.mcrAsn, location:.data.locationDetail.name}'` |
| MCR BGP routes — looking glass *(broken in our experience; see gotcha #2 below)* | `curl -s -H "X-Auth-Token: $MP_TOKEN" "$MP_API/v2/product/mcr2/$MCR1_UID/diagnostics/routes/bgp" \| jq -r '.data[]? \| [.network, .nextHop, .asPath, .source] \| @tsv'` |
| MCR static routes (config side, not RIB) | `curl -s -H "X-Auth-Token: $MP_TOKEN" "$MP_API/v2/product/$MCR1_UID" \| jq -r '.data.resources.virtual_router.staticRoutes[]? \| [.prefix, .nextHop] \| @tsv'` |
| List VXCs in account | `curl -s -H "X-Auth-Token: $MP_TOKEN" "$MP_API/v2/products" \| jq -r '.data[] \| select(.productType=="VXC") \| [.productUid, .productName, .provisioningStatus, .aEnd.locationDetail.name, .bEnd.locationDetail.name] \| @tsv'` |
| VXC BGP sessions (combined selector) | `curl -s -H "X-Auth-Token: $MP_TOKEN" "$MP_API/v2/product/$VXC_UID" \| jq -r '(.data.resources.csp_connection // .data.aEnd.partnerConfig // empty) \| .interfaces[]?.bgpConnections[]? \| [.localIpAddress, .peerIpAddress, .peerAsn, .sessionState, (.exportPolicy // "-"), (.importPolicy // "-")] \| @tsv'` |
| VXC BGP raw block (when the combined selector misses) | `curl -s -H "X-Auth-Token: $MP_TOKEN" "$MP_API/v2/product/$VXC_UID" \| jq '.data.resources.csp_connection[0].interfaces[0].bgpConnections'` |

**Gotcha #1 — BGP block lives in different places per VXC type.** Azure VXCs put it under `resources.csp_connection[0].interfaces[0].bgpConnections`. GCP VXCs may have separate entries per Interconnect attachment. MCR-to-MCR VXCs put it under `aEnd.partnerConfig.interfaces`. The combined selector above tries the common locations.

**Gotcha #2 — Looking glass is broken (confirmed).** `/diagnostics/routes/bgp` returned `"no endpoint"` / empty body in lab #1 (`labs/expressroute-megaport-bgp/`, 2026-05) under healthy ESTABLISHED sessions. That failure was the trigger for the pre-gate review ceremony in `.squad/ceremonies.md`. Treat it as **unreliable** and authoritative session state comes from the VXC `bgpConnections.sessionState` field ("ESTABLISHED" / "IDLE" / "ACTIVE"). If you re-test the looking glass and get a non-empty response, append the date + lab to this gotcha; reliability may improve someday. — Re-tested 2026-06-15 in lab #2 (`labs/vwan-dual-er-symmetric/`) against both MCR1 + MCR2: looking-glass **still not reachable**, but for a new reason — `POST /v2/login` returned HTTP 401 (credentials rejected) before any MCR endpoint could be called. New failure mode: Megaport API credentials in `platform-secrets-1138` may have expired or rotated since deploy-time. Evidence: `labs/vwan-dual-er-symmetric/show-output/looking-glass-test-2026-06-15/`.

**Gotcha #3 — `productType` casing matters.** `"MCR2"` (literal string) for MCR; `"VXC"` for cross-connects. `select(.productType=="MCR")` returns zero results.

---

## 8. gcloud — Cloud Router (BGP)

| Goal | Command |
|---|---|
| List routers in a region | `gcloud compute routers list --filter="region:$REGION_A" --format="table(name, region, network.basename(), bgp.asn)"` |
| | <!-- Validated 2026-06-15 WSL: works (output: 01-validation-results.txt) --> |
| Router config (BGP + advertised) | `gcloud compute routers describe $ROUTER_A --region=$REGION_A --format=json \| jq '{name, asn:.bgp.asn, advertiseMode:.bgp.advertiseMode, advertisedRanges:.bgp.advertisedIpRanges, peers:[.bgpPeers[].name]}'` |
| | <!-- Validated 2026-06-15 WSL: works (output: 01-validation-results.txt) --> |
| Best routes (post-selection) | `gcloud compute routers get-status $ROUTER_A --region=$REGION_A --format=json \| jq -r '.result.bestRoutesForRouter[] \| [.destRange, .routeType, .nextHopIp, (.priority\|tostring)] \| @tsv'` |
| | <!-- Validated 2026-06-15 WSL: works (output: 01-validation-results.txt) --> |
| **Learned routes per peer, with AS path** | `gcloud compute routers get-status $ROUTER_A --region=$REGION_A --format=json \| jq -r '.result.bgpPeerStatus[] \| .name as $peer \| .learnedRoutes[]? \| [$peer, .destRange, .routeType, .nextHopIp, (.asPath \| @json // "-")] \| @tsv'` |
| | <!-- Validated 2026-06-15 WSL: works (output: 01-validation-results.txt; empty result is correct) --> |
| BGP peer status (up/down, uptime, counters) | `gcloud compute routers get-status $ROUTER_A --region=$REGION_A --format=json \| jq -r '.result.bgpPeerStatus[] \| [.name, .ipAddress, (.peerIpAddress // "-"), .status, .state, (.uptime // "-"), (.numLearnedRoutes\|tostring)] \| @tsv'` |
| | <!-- Validated 2026-06-15 WSL: works (output: 01-validation-results.txt) --> |
| Routes advertised to a specific peer | `gcloud compute routers get-status $ROUTER_A --region=$REGION_A --format=json \| jq -r '.result.bgpPeerStatus[] \| select(.name=="<YOUR_BGP_PEER_NAME>") \| .advertisedRoutes[]? \| [.destRange, (.asPath \| @json // "-")] \| @tsv'` |
| | <!-- Validated 2026-06-15 WSL: works with placeholder fix (output: 01-validation-results.txt) --> |

**Gotcha #1 — `.asPath` shape varies.** Sometimes an object (`{asns: [...], asPathSegmentType: "AS_SEQUENCE"}`), sometimes an array, sometimes absent. The `@json` trick renders whatever's there as a single TSV cell instead of crashing jq.

**Gotcha #2 — PARTNER Interconnect forces CR ASN to `16550`.** No matter what you set in TF/console, the CR ASN advertised to the peer over a PARTNER attachment is `16550` (Google's globally-shared PARTNER ASN). Don't fight it — `peerAsn` (the MCR side) is what you can actually control.

**Gotcha #3 — `numLearnedRoutes` includes filtered routes.** If you set an import policy, the count can be higher than what shows in `learnedRoutes[]`. Trust `.learnedRoutes[] | length`, not `.numLearnedRoutes`.

---

## 9. gcloud — Interconnect attachments + VPC routes

| Goal | Command |
|---|---|
| List Interconnect attachments | `gcloud compute interconnects attachments list --format="table(name, region, type, edgeAvailabilityDomain, state, pairingKey)"` |
| | <!-- Validated 2026-06-15 WSL: works (output: 01-validation-results.txt) --> |
| One attachment in detail | `gcloud compute interconnects attachments describe <YOUR_ATTACHMENT_NAME> --region=$REGION_A --format=json \| jq '{name, state, type, bandwidth, pairingKey, vlanTag8021q, cloudRouterIpAddress, customerRouterIpAddress, partnerAsn}'` |
| | <!-- Validated 2026-06-15 WSL: works with placeholder fix (output: 01-validation-results.txt) --> |
| Effective VPC routes (what the data plane sees) | `gcloud compute routes list --filter="network:<YOUR_VPC>" --format="table(name, destRange, nextHopIp, nextHopGateway.basename(), nextHopVpnTunnel.basename(), priority)"` |
| | <!-- Validated 2026-06-15 WSL: CRITICAL FIX — hardcoded vpc-onprem replaced with <YOUR_VPC> (output: 01-validation-results.txt) --> |
| Firewalls applied to a VPC | `gcloud compute firewall-rules list --filter="network:<YOUR_VPC>" --format="table(name, direction, priority, sourceRanges[0], targetTags[0], allowed[0].map().firewall_rule())"` |
| | <!-- Validated 2026-06-15 WSL: FIXED — original used deprecated get-effective-firewalls; replaced with firewall-rules list (output: 01-validation-results.txt) --> |

**Gotcha — VPC routing mode (`REGIONAL` vs `GLOBAL`) is invisible in `routes list` output.** A route learned by Router-A (region-X) won't appear in region-Y's VM forwarding table unless the VPC has `routing_mode=GLOBAL`. Check the VPC's mode first: `gcloud compute networks describe <YOUR_VPC> --format='value(routingConfig.routingMode)'`.
<!-- Validated 2026-06-15 WSL: works with placeholder fix (output: 01-validation-results.txt; confirmed GLOBAL mode) -->

---

## 10. Linux NVA — BIRD + kernel + sockets

For NVAs running BIRD 2 (per `cloud-init-nva-bird.yaml`):

| Goal | Command |
|---|---|
| BGP protocol state | `birdc show protocols \| awk 'NR==1 \|\| /BGP/'` |
| BGP session details (one neighbor) | `birdc show protocols all <name>` |
| Routes received from one neighbor | `birdc show route protocol <name>` |
| All routes in BIRD's RIB | `birdc show route` |
| Routes BIRD installed in kernel | `ip route show proto bird` |
| Full kernel routing table | `ip -4 route show table all \| column -t` |
| Active TCP sessions on BGP port | `ss -tnp '( sport = :179 or dport = :179 )'` |

---

## 11. Diagnostic patterns — combining the layers

### Pattern A — "Is prefix X reachable from VM Y, and what path will it take?"

Walk the layers top-down. Each command filters for one prefix so the output stays human-sized.

```bash
PREFIX=10.50.1.0/24

# 1. Effective routes on the VM's NIC (Azure side)
az network nic show-effective-route-table -g $RG -n $NIC -o json | \
  jq -r --arg p $PREFIX '.value[] | select(.addressPrefix[0]==$p) | [.nextHopType, (.nextHopIpAddress // "-"), .source] | @tsv'

# 2. Hub's view (does the hub know the prefix?)
az network vhub get-effective-routes -g $RG -n $VHUB1 --resource-type RouteTable \
  --resource-id $(az network vhub route-table show -g $RG --vhub-name $VHUB1 -n defaultRouteTable --query id -o tsv) \
  -o json | jq -r --arg p $PREFIX '.value[] | select(.addressPrefixes[0]==$p) | [.nextHopType, (.nextHops|join(",")), .asPath] | @tsv'

# 3. ER GW learned-routes (which MSEE peer is providing it?)
az network vnet-gateway list-learned-routes -g $RG -n $ERGW1 -o json | \
  jq -r --arg p $PREFIX '.value[] | select(.network==$p) | [.network, .nextHop, .asPath] | @tsv'

# 4. MSEE route table (is the MCR advertising it?)
az network express-route list-route-tables -g $RG -n $ERCKT1 --peering-name AzurePrivatePeering --path primary -o json | \
  jq -r --arg p $PREFIX '.value[] | select(.network==$p) | [.nextHop, .path] | @tsv'

# 5. GCP CR — is the prefix being advertised to MCR?
gcloud compute routers get-status $ROUTER_A --region=$REGION_A --format=json | \
  jq -r --arg p $PREFIX '.result.bgpPeerStatus[].advertisedRoutes[]? | select(.destRange==$p) | [.destRange, (.asPath|@json)] | @tsv'
```

Empty output at any layer = the prefix isn't propagating past that point. That's your break.

### Pattern B — "BGP session went down — which side?"

Quick health check across the chain:

| Layer | Command | "Up" looks like |
|---|---|---|
| ER circuit peering (config) | `az network express-route peering show -g $RG --circuit-name $ERCKT1 -n AzurePrivatePeering -o json \| jq '.state'` | `"Enabled"` |
| ER circuit BGP (presence test) | `az network express-route list-route-tables-summary -g $RG -n $ERCKT1 --peering-name AzurePrivatePeering --path primary -o json \| jq '.value\|length'` | `> 0` |
| ER GW BGP peers | `az network vnet-gateway list-bgp-peer-status -g $RG -n $ERGW1 -o json \| jq -r '.value[] \| [.neighbor, .state, .connectedDuration] \| @tsv'` | state = `Connected` |
| MCR VXC (Megaport view) | `curl ... /v2/product/$VXC_UID \| jq -r '.data.resources.csp_connection[0].interfaces[0].bgpConnections[] \| [.peerIpAddress, .sessionState] \| @tsv'` | sessionState = `ESTABLISHED` |
| GCP CR | `gcloud compute routers get-status $ROUTER_A --region=$REGION_A --format=json \| jq -r '.result.bgpPeerStatus[] \| [.name, .status, .state] \| @tsv'` | status = `UP`, state = `Established` |

### Pattern C — "Is traffic asymmetric? Are firewall flows dropping mid-session?"

When you suspect AzFW drops because forward and return packets hit different firewall instances:

1. Get the route the source VM uses to reach the destination (Pattern A, step 1).
2. Get the route the destination VM uses to reach the source (run Pattern A in reverse).
3. Compare the egress hub for each direction. If they differ → asymmetric. Each AzFW instance maintains its own state table; only the one that saw the SYN will accept the SYN-ACK back.

The fix is at the routing layer (prepending, prefix filters, hub-to-hub routing intent) — not at the firewall.

### Pattern D — "Prove asymmetric routing with firewall logs (dual-hub ER + GCP)"

**Context:** Design B Phase 1 (`vwan-dual-er-symmetric`, 2026-06-15). Two GCP Cloud Routers advertise both GCP subnets into both MCRs. Without AS-PATH prepend tiebreaker, Azure's BGP selects the direct ER path (shorter AS-path) for each prefix; GCP's GLOBAL VPC uses regional routing (VM-B in eu-w4 always returns via eu-w4's Cloud Router).

**Step 1: ER circuit route table scan — is the same GCP prefix on both ER circuits?**

```bash
# If BOTH prefixes appear on BOTH ER circuits → multiple paths → asymmetry is mathematically possible.
# In Design A (Mechanism A, filter lists): each ER shows only its "home" prefix.
for ERCKT in er-vwan-symm-stockholm er-vwan-symm-amsterdam; do
  echo "=== $ERCKT ==="
  az network express-route list-route-tables -g $RG -n $ERCKT \
    --peering-name AzurePrivatePeering --path primary -o json \
    | jq -r '.value[] | select(.network | startswith("10.50")) | [.network, .nextHop, .path] | @tsv'
done
```

**Step 2: GCP GLOBAL VPC multi-router bestRoutes scan — does each router see both MCR paths?**

```bash
# bestRoutes (all VPC routes) shows BOTH MCR paths for each Azure prefix.
# bestRoutesForRouter shows THIS router's best-path selection.
# Priority difference (0 vs 213) = not ECMP. Always one MCR wins per region.
for ROUTER in router-vwan-symm-a cr-vwan-symm-onprem-b; do
  REGION=$(gcloud compute routers describe $ROUTER --project=$GCP_PROJECT --format='value(region)' | sed 's|.*/||')
  echo "=== $ROUTER ($REGION) ==="
  gcloud compute routers get-status $ROUTER --region=$REGION --project=$GCP_PROJECT --format=json \
    | jq -r '.result.bestRoutesForRouter[] | select(.destRange | startswith("10.1")) | [.destRange, .nextHopIp, (.asPaths[0].asLists|@json), .routeStatus] | @tsv'
done
```

**Step 3: Two-VM differential connectivity test — the minimal proof**

```bash
# Run the SAME test from BOTH hubs. If one succeeds and one fails:
#   - Policy is NOT the issue (policy is hub-wide, not VM-specific)
#   - Asymmetric routing IS the issue
# nm: nc returns exit 0 on success, non-zero on timeout.
az vm run-command invoke -g $RG -n vm-spoke1 --command-id RunShellScript \
  --scripts 'nc -zv -w 5 10.50.2.2 22 2>&1; echo "Exit: $?"'
az vm run-command invoke -g $RG -n vm-spoke3 --command-id RunShellScript \
  --scripts 'nc -zv -w 5 10.50.2.2 22 2>&1; echo "Exit: $?"'
# spoke1 (Hub1) timeout + spoke3 (Hub2) success = asymmetric routing proved.
```

**Step 4: Firewall KQL correlation — find the "absent AzFW" signature**

```kql
// Run against the shared Log Analytics workspace.
// Asymmetric routing signature: AzFW-A logs forward SYN; AzFW-B logs ZERO entries for the same flow.
// Azure Firewall does NOT log TCP stateful drops — the absence IS the evidence.
AzureDiagnostics
| where ResourceType == "AZUREFIREWALLS"
| where TimeGenerated > ago(30m)
| where msg_s contains "10.50.2.2" or msg_s contains "10.50.1.2"
| project TimeGenerated, Resource, msg_s
| order by TimeGenerated asc
```

```bash
az monitor log-analytics query -w <workspace-id> --analytics-query "$(cat above_kql)" -o json \
  | jq -r '.[] | select(.msg_s != null) | [.TimeGenerated, .Resource, .msg_s] | @tsv'
```

**Interpretation guide:**

| Pattern | Meaning |
|---|---|
| Only AzFW1 entries for flow A→B | Forward path via Hub1; return SYN-ACK silently dropped at AzFW2 (no state) |
| Only AzFW2 entries for flow A→B | Symmetric via Hub2; both directions logged at AzFW2 |
| Both AzFW1 and AzFW2 entries for same 5-tuple | ECMP/hash-pinning split — rare, indicates routing instability |

**Key gotcha:** Azure Firewall does NOT emit a log entry for packets dropped by the TCP stateful engine (SYN-ACK without matching SYN, RST/FIN without established state). Only policy-matched packets (ALLOW or DENY by rule) appear in `AzureDiagnostics`. The absence of AzFW2 entries for a flow whose SYN was logged at AzFW1 is therefore the proof of asymmetric routing with stateful drop — not a logging gap.

Evidence: `labs/vwan-dual-er-symmetric/show-output/design-b-phase1-asymmetric-2026-06-15/` (2026-06-15).

---

## 12. Quick aliases worth dropping into your shell

```bash
# Azure
alias er-routes='_f(){ az network express-route list-route-tables -g "$1" -n "$2" --peering-name AzurePrivatePeering --path "${3:-primary}" -o json | jq -r ".value[] | [.network, .nextHop, .path] | @tsv"; }; _f'
alias hub-routes='_f(){ az network vhub get-effective-routes -g "$1" -n "$2" --resource-type RouteTable --resource-id $(az network vhub route-table show -g "$1" --vhub-name "$2" -n defaultRouteTable --query id -o tsv) -o json | jq -r ".value[] | [.addressPrefixes[0], .nextHopType, (.nextHops | join(\",\")), .asPath] | @tsv"; }; _f'

# GCP
alias cr-learned='_f(){ gcloud compute routers get-status "$1" --region="$2" --format=json | jq -r ".result.bgpPeerStatus[] | .name as \$p | .learnedRoutes[]? | [\$p, .destRange, .routeType, .nextHopIp, (.asPath | @json // \"-\")] | @tsv"; }; _f'
alias cr-best='_f(){ gcloud compute routers get-status "$1" --region="$2" --format=json | jq -r ".result.bestRoutesForRouter[] | [.destRange, .routeType, .nextHopIp] | @tsv"; }; _f'

# Megaport
alias mp-vxc-bgp='_f(){ curl -s -H "X-Auth-Token: $MP_TOKEN" "$MP_API/v2/product/$1" | jq -r ".data.resources.csp_connection[0].interfaces[0].bgpConnections[]? | [.peerIpAddress, .peerAsn, .sessionState] | @tsv"; }; _f'
```

Usage:

- `er-routes rg-vwan-symm-103167 erckt-vhub1-...` (defaults to primary path)
- `cr-learned router-a europe-west3`
- `mp-vxc-bgp $VXC_UID`

---

## Maintenance notes

- **Why TSV and not table?** Most CLIs have an `-o table` mode, but column widths truncate AS-paths and FQDNs, and you can't `grep`/`awk` the output cleanly. TSV via jq is pipe-friendly across all three CLIs.
- **Why no `--query` JMESPath?** Azure CLI's `--query` is fine for one-shot filtering, but `jq` works identically across `az`, `gcloud`, and raw `curl` — fewer mental contexts to switch.
- **Adding a command?** Validate it against a live lab before merging. The MSEE route-table `-o table` bug, the looking-glass empty-response bug, and the `get-effective-routes` cold-start bug are real and not in MS Learn — call them out in the gotcha column with a source citation per `docs/README.md` rule #3.
