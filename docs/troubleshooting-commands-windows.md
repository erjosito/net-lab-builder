# Network troubleshooting commands — Windows / PowerShell companion

> 📖 Linux / macOS users: see [`troubleshooting-commands-linux.md`](./troubleshooting-commands-linux.md) for the bash version of the same commands.

This is the self-contained Windows/PowerShell equivalent of the Linux troubleshooting doc. Every command in this file is ready to run on Windows — no need to keep the Linux doc open.

---

## 0. Setup

### Conventions

```powershell
# Azure
$env:RG = "rg-vwan-symm-103167"
$env:VHUB1 = "vhub-..."
$env:ERGW1 = "ergw-vhub1-..."
$env:ERCKT1 = "erckt-vhub1-..."
$env:AZFW1 = "azfw-vhub1-..."
$env:NIC = "nic-spoke1-..."
$env:VPNGW1 = "vpngw-vhub1-..."

# Megaport (HTTP API token via /v2/login)
$env:MP_TOKEN = "ey..."
$env:MCR1_UID = "00000000-0000-0000-0000-000000000000"
$env:VXC_UID = "00000000-0000-0000-0000-000000000000"
$env:MP_API = "https://api.megaport.com"

# GCP
$env:GCP_PROJECT = "gcp-vwan-symm-103167"
$env:ROUTER_A = "router-vwan-symm-a"
$env:REGION_A = "europe-west3"

# Prompt for secret without echo (Megaport credentials)
$secret = Read-Host "Megaport Secret" -AsSecureString
$plainSecret = [System.Net.NetworkCredential]::new('', $secret).Password
```

**Placeholder convention:** Commands in this document use `<YOUR_...>` tokens for values that vary per lab (e.g., `<YOUR_VPC>`, `<YOUR_ATTACHMENT_NAME>`, `<YOUR_VM_NAME>`). Replace these with your actual resource names before running commands.

**jq tip:** prefix any `gcloud`/`az`/`curl` command with `-o json` (Azure CLI) or `--format=json` (gcloud) and pipe to `jq -r '… | @tsv'`. `@tsv` beats manual `join("\t")` because it escapes embedded tabs/newlines.

---

## 0.1 Install utilities via winget

| Tool | Notes |
|---|---|
| **PowerShell 7+** | `winget install Microsoft.PowerShell` — Highly recommended. Most gotchas in this doc disappear on PS 7+. Run as `pwsh`. |
| **curl.exe** | Windows 10 1803+ / 11 ship it natively. Verify: `curl.exe --version`. Winget NOT needed unless your curl is very old. |
| **jq** | `winget install jqlang.jq` — verify: `jq --version` |
| **Git for Windows** | `winget install Git.Git` — provides bash, grep, awk at `Program Files\Git\bin` |
| **ripgrep** | `winget install BurntSushi.ripgrep.MSVC` — optional; faster than `Select-String` |

Restart PowerShell after install (or `. $PROFILE` in current session).

---

## 0.2 Which PowerShell are you running?

Check your version first:

```powershell
$PSVersionTable.PSVersion
```

- **PowerShell 7+ (modern, runs as `pwsh`):** No `curl` alias. `curl` resolves to `curl.exe` natively. Jump to §0.3 for the real gotchas.
- **Windows PowerShell 5.1 (pre-installed on Windows 10/11, runs as `powershell`):** Has a `curl` → `Invoke-WebRequest` alias. See §0.2.1.

**Recommendation:** Install PowerShell 7+ via `winget install Microsoft.PowerShell`. Most gotchas vanish on the modern version.

### 0.2.1 The curl/wget alias trap (Windows PowerShell 5.1 only)

If stuck on PS 5.1, `curl` resolves to `Invoke-WebRequest` (a PowerShell cmdlet). Symptoms: "parameter not found" errors on `-s`, `-X`, etc.

Diagnose: `Get-Command curl` → if `Alias`, trap applies.

Fixes (pick one):
- Type `curl.exe` always
- `Remove-Item Alias:curl -Force` in `$PROFILE`
- Upgrade to PS 7+

---

## 0.3 Bash → PowerShell command pitfalls

⚠️ **Most common copy-paste failure:** The **backslash line-continuation** (`\` at end of line from bash scripts). PowerShell treats `\` as a literal character (path separator), NOT line continuation. Command parses as one long invalid line. Use backtick (`` ` ``) instead — but backticks are fragile (trailing whitespace breaks them). **Preferred: one-line the entire command.** *(Source: Jose live-test 2026-06-15, lab #2)*

```powershell
# ❌ Backslash doesn't work in PowerShell (bash-only)
curl.exe -s -X POST \
  "$apiUrl/v2/login" \
  -d "username=$user&password=$pass"

# ✅ Backtick works (PowerShell line continuation)
curl.exe -s -X POST `
  "$apiUrl/v2/login" `
  -d "username=$user&password=$pass"

# ✅ Preferred: one-line (no fragile backticks)
curl.exe -s -X POST "$apiUrl/v2/login" -d "username=$user&password=$pass"
```

Other pitfalls:

| Bash | PowerShell | Fix |
|---|---|---|
| `$VAR` (env var reference) | PS treats `$VAR` as a local variable, NOT an env var. If undefined → empty string → curl sends `username=&password=` → 401 | Use `$env:VAR` for env vars. Or: `$MP_USER = $env:MP_USER` first. **This is the #2 trap.** |
| `export VAR=foo` | Not a PS command | `$env:VAR = "foo"` (process scope) or `[System.Environment]::SetEnvironmentVariable('VAR','foo','User')` (persist) |
| `` `subshell` `` | PS escape char, not substitution | Use `$(command)` instead |
| `<<EOF...EOF` heredoc | Syntax error | PS here-string: `$body = @"..."@` then `-d $body` |
| `&` in quoted string | If double-quoted, call operator; if unquoted, background job. E.g., `-d "x=1&y=2"` tries to run `y=2` as a command | Use single quotes: `-d 'x=1&y=2'` |
| `2>&1` | Works identically ✅ |
| `cmd \| tee file` | Works but flush differs | `cmd \| Out-File file` (or `\| Tee-Object file`) |
| `find . -name X` | PS has no `find` | `Get-ChildItem -Recurse -Filter X` |

---

## 1. Azure CLI — Virtual WAN

| Goal | Command |
|---|---|
| List vHubs in a RG | `az network vhub list -g $env:RG -o table` |
| Effective routes on vHub (default route table) | `az network vhub get-effective-routes -g $env:RG -n $env:VHUB1 --resource-type RouteTable --resource-id $(az network vhub route-table show -g $env:RG --vhub-name $env:VHUB1 -n defaultRouteTable --query id -o tsv) -o json \| jq -r '.value[] \| [.addressPrefixes[0], .nextHopType, (.nextHops \| join(",")), .asPath] \| @tsv'` |
| Effective routes from one connection's perspective | `az network vhub get-effective-routes -g $env:RG -n $env:VHUB1 --resource-type ExpressRouteConnection --resource-id <conn-id>` |
| List all vHub connections (VNet, ER, VPN) | `az network vhub connection list -g $env:RG --vhub-name $env:VHUB1 -o table` |
| Hub route-table propagation map | `az network vhub route-table show -g $env:RG --vhub-name $env:VHUB1 -n defaultRouteTable -o json \| jq '.labels, .propagatingConnections'` |

**Gotcha:** `get-effective-routes` may briefly return `{"value":[]}` for vWAN secured hubs even when MSEE routes are fully present — fresh hubs (< 10 min) or mid-publish route intents trigger it. Retry every 30 s for up to 5 min before chasing a real bug. The MSEE route-table evidence (§3) is the authoritative Azure-layer fallback. (Confirmed `labs/vwan-dual-er-symmetric/`, 2026-06-15.)

---

## 2. Azure CLI — ExpressRoute Gateway

Use `vnet-gateway` for classic VNet-attached ER gateways; use `vhub bgpconnection` for vWAN-hub-attached ER.

| Goal | Command |
|---|---|
| Learned routes on classic ER GW | `az network vnet-gateway list-learned-routes -g $env:RG -n $env:ERGW1 -o json \| jq -r '.value[] \| [.network, .nextHop, .sourcePeer, .origin, .asPath, .weight] \| @tsv'` |
| Advertised routes to one BGP peer | `az network vnet-gateway list-advertised-routes -g $env:RG -n $env:ERGW1 --peer 169.254.21.1 -o json \| jq -r '.value[] \| [.network, .asPath] \| @tsv'` |
| BGP peer status on classic ER GW | `az network vnet-gateway list-bgp-peer-status -g $env:RG -n $env:ERGW1 -o table` |
| List ER connections on vHub gateway | `az network express-route gateway connection list -g $env:RG --gateway-name $env:ERGW1 -o table` |
| vWAN-hub-side BGP peers (newer API) | `az network vhub bgpconnection list -g $env:RG --vhub-name $env:VHUB1 -o table` |

**Gotcha:** `list-learned-routes` returns up to ~500 routes per call. For large tables, filter at jq with `select(.network \| startswith("10."))`. The `asPath` field is a single space-separated string — split with `(.asPath \| split(" "))` if you need to compute hop count.

---

## 3. Azure CLI — ExpressRoute Circuit

| Goal | Command |
|---|---|
| List circuits in subscription | `az network express-route list -o table` |
| Circuit state + bandwidth + provider | `az network express-route show -g $env:RG -n $env:ERCKT1 -o json \| jq '{name, serviceProviderProvisioningState, circuitProvisioningState, bandwidthInMbps, sku:.sku.tier, peerings:[.peerings[].name]}'` |
| Private peering route table — primary path | `az network express-route list-route-tables -g $env:RG -n $env:ERCKT1 --peering-name AzurePrivatePeering --path primary -o json \| jq -r '.value[] \| [.network, .nextHop, .locPrf, .weight, .path] \| @tsv'` |
| Same — secondary path | `az network express-route list-route-tables -g $env:RG -n $env:ERCKT1 --peering-name AzurePrivatePeering --path secondary -o json \| jq -r '.value[] \| [.network, .nextHop, .locPrf, .weight, .path] \| @tsv'` |
| Route table summary (prefix count + next-hop ASN distribution) | `az network express-route list-route-tables-summary -g $env:RG -n $env:ERCKT1 --peering-name AzurePrivatePeering --path primary -o table` |
| ARP table on primary peering | `az network express-route list-arp-tables -g $env:RG -n $env:ERCKT1 --peering-name AzurePrivatePeering --path primary -o table` |
| List peerings on a circuit | `az network express-route peering list -g $env:RG --circuit-name $env:ERCKT1 -o table` |
| Peering details (BGP IPs, ASN, MD5 presence) | `az network express-route peering show -g $env:RG --circuit-name $env:ERCKT1 -n AzurePrivatePeering -o json \| jq '{state, peerASN, primaryPeerAddressPrefix, secondaryPeerAddressPrefix, vlanId, sharedKey: (if .sharedKey then "<set>" else null end)}'` |

**Gotcha #1 — `-o table` is broken for route tables.** `az network express-route list-route-tables -o table` prints headers with empty rows. **Always use `-o json`** and pipe to jq.

**Gotcha #2 — circuit `Provisioned` ≠ BGP session up.** If the circuit reports `Provisioned` but `list-route-tables` returns `"BGP sessions are not enabled"`, give it ~60 s after Megaport hand-off; the MSEE peering takes longer to come up than the circuit provisioning signal.

**Gotcha #3 — `.path` is the AS-path, not the URL parameter.** The output field `.path` is the route's BGP AS-path string like `65515 65520 65520 E`. The trailing letter is the origin attribute (`E` = EBGP, `I` = IBGP, `?` = incomplete). Easy to confuse with the `--path primary` query parameter.

**Gotcha #4 — vWAN-hub ER circuits.** When the ER circuit is attached to a vWAN hub (not a classic VNet GW), the MSEE route-table CLI still works the same way — it queries the circuit-side BGP table, not the Azure GW.

---

## 4. Azure CLI — VPN Gateway (S2S/P2S)

| Goal | Command |
|---|---|
| List VPN connections | `az network vpn-connection list -g $env:RG -o table` |
| Connection state (tunnel up/down, BGP up/down, bytes) | `az network vpn-connection show -g $env:RG -n <conn-name> -o json \| jq '{name, connectionStatus, ingressBytes:.ingressBytesTransferred, egressBytes:.egressBytesTransferred, enableBgp}'` |
| Learned routes on VPN GW | `az network vnet-gateway list-learned-routes -g $env:RG -n $env:VPNGW1 -o json \| jq -r '.value[] \| [.network, .nextHop, .asPath] \| @tsv'` |
| BGP peer status on VPN GW | `az network vnet-gateway list-bgp-peer-status -g $env:RG -n $env:VPNGW1 -o table` |

---

## 5. Azure CLI — Azure Firewall

| Goal | Command |
|---|---|
| List firewalls in RG | `az network firewall list -g $env:RG -o table` |
| Firewall public + private IPs | `az network firewall show -g $env:RG -n $env:AZFW1 -o json \| jq -r '.ipConfigurations[] \| [.name, .privateIPAddress, (.publicIPAddress.id // "-")] \| @tsv'` |
| Rule collection groups (Policy mode) | `az network firewall policy rule-collection-group list --policy-name <policy> -g $env:RG -o table` |
| Inspect one rule collection (verbose) | `az network firewall policy rule-collection-group show --policy-name <policy> -g $env:RG -n <rcg> -o json \| jq '.ruleCollections[] \| {name, priority, action:.action.type, rules:[.rules[].name]}'` |

**Runtime hit counters / flow logs:** Azure Firewall doesn't expose rule-hit counts via CLI. Use Log Analytics KQL — see `AZFWNetworkRule`, `AZFWApplicationRule`, `AZFWNatRule` tables. CLI surface only shows configuration.

---

## 6. Azure CLI — VM NIC

| Goal | Command |
|---|---|
| Effective routes on a NIC | `az network nic show-effective-route-table -g $env:RG -n $env:NIC -o json \| jq -r '.value[] \| [.addressPrefix[0], .nextHopType, (.nextHopIpAddress // "-"), .source, .state] \| @tsv'` |
| Effective NSG rules on a NIC (which rules match) | `az network nic list-effective-nsg -g $env:RG -n $env:NIC -o json \| jq '.value[].effectiveSecurityRules[] \| {name, direction, access, priority, sourceAddressPrefix, destinationAddressPrefix, destinationPortRange}'` |

**Gotcha:** `show-effective-route-table` requires the VM to be **running**. Stopped (deallocated) VMs return `"NIC must be associated with a running VM"`.

---

## 7. Megaport HTTP API — auth + MCR + VXC

Get a session token first:

```powershell
$cred = @{
    username = $env:MP_USER
    password = $plainSecret
}
$resp = Invoke-RestMethod -Method Post -Uri "$env:MP_API/v2/login" `
  -ContentType 'application/x-www-form-urlencoded' `
  -Body $cred
$env:MP_TOKEN = $resp.data.session
```

Or use `Invoke-RestMethod` (alias `irm`):

```powershell
$headers = @{ 'X-Auth-Token' = $env:MP_TOKEN }
irm -Uri "$env:MP_API/v2/products" -Headers $headers | ConvertFrom-Json
```

| Goal | Command |
|---|---|
| List MCRs in account | `$headers = @{ 'X-Auth-Token' = $env:MP_TOKEN }; (irm -Uri "$env:MP_API/v2/products" -Headers $headers).data \| Where-Object productType -eq "MCR2" \| Select-Object productUid, productName, provisioningStatus, @{N="location";E={$_.locationDetail.name}} \| Format-Table` |
| Show one MCR (config + interfaces) | `irm -Uri "$env:MP_API/v2/product/$env:MCR1_UID" -Headers $headers \| Select-Object @{N="name";E={$_.data.productName}}, @{N="status";E={$_.data.provisioningStatus}}, @{N="asn";E={$_.data.config.mcrAsn}}, @{N="location";E={$_.data.locationDetail.name}}` |
| MCR BGP routes — looking glass *(broken in our experience; see gotcha #2 below)* | `irm -Uri "$env:MP_API/v2/product/mcr2/$env:MCR1_UID/diagnostics/routes/bgp" -Headers $headers -SkipHttpErrorCheck \| Select-Object @{N="network";E={$_.data.network}}, @{N="nextHop";E={$_.data.nextHop}}, @{N="asPath";E={$_.data.asPath}}, @{N="source";E={$_.data.source}}` |
| MCR static routes (config side, not RIB) | `(irm -Uri "$env:MP_API/v2/product/$env:MCR1_UID" -Headers $headers).data.resources.virtual_router.staticRoutes \| Select-Object prefix, nextHop \| Format-Table` |
| List VXCs in account | `(irm -Uri "$env:MP_API/v2/products" -Headers $headers).data \| Where-Object productType -eq "VXC" \| Select-Object productUid, productName, provisioningStatus, @{N="aLoc";E={$_.aEnd.locationDetail.name}}, @{N="bLoc";E={$_.bEnd.locationDetail.name}} \| Format-Table` |
| VXC BGP sessions (combined selector) | `$vxc = irm -Uri "$env:MP_API/v2/product/$env:VXC_UID" -Headers $headers; ($vxc.data.resources.csp_connection ?? $vxc.data.aEnd.partnerConfig) \| ForEach-Object { $_.interfaces } \| ForEach-Object { $_.bgpConnections } \| Select-Object localIpAddress, peerIpAddress, peerAsn, sessionState, exportPolicy, importPolicy \| Format-Table` |
| VXC BGP raw block (when the combined selector misses) | `(irm -Uri "$env:MP_API/v2/product/$env:VXC_UID" -Headers $headers).data.resources.csp_connection[0].interfaces[0].bgpConnections \| Format-Table` |

**Gotcha #1 — BGP block lives in different places per VXC type.** Azure VXCs put it under `resources.csp_connection[0].interfaces[0].bgpConnections`. GCP VXCs may have separate entries per Interconnect attachment. MCR-to-MCR VXCs put it under `aEnd.partnerConfig.interfaces`. The combined selector above tries the common locations.

**Gotcha #2 — Looking glass is broken (confirmed).** `/diagnostics/routes/bgp` returned `"no endpoint"` / empty body in lab #1 (`labs/expressroute-megaport-bgp/`, 2026-05) under healthy ESTABLISHED sessions. That failure was the trigger for the pre-gate review ceremony in `.squad/ceremonies.md`. Treat it as **unreliable** and authoritative session state comes from the VXC `bgpConnections.sessionState` field ("ESTABLISHED" / "IDLE" / "ACTIVE"). If you re-test the looking glass and get a non-empty response, append the date + lab to this gotcha; reliability may improve someday. — Re-tested 2026-06-15 in lab #2 (`labs/vwan-dual-er-symmetric/`) against both MCR1 + MCR2: looking-glass **still not reachable**, but for a new reason — `POST /v2/login` returned HTTP 401 (credentials rejected) before any MCR endpoint could be called. New failure mode: Megaport API credentials in `platform-secrets-1138` may have expired or rotated since deploy-time. Evidence: `labs/vwan-dual-er-symmetric/show-output/win-validation-2026-06-15/`.

**Gotcha #3 — `productType` casing matters.** `"MCR2"` (literal string) for MCR; `"VXC"` for cross-connects. `select(.productType=="MCR")` returns zero results.

### 7.1 Troubleshooting login failures

**Validation (2026-06-15):** KV credentials returned HTTP 401 — regenerate in Megaport portal if needed. Check HKCU env vars `$env:MEGAPORT_ACCESS_KEY` / `$env:MEGAPORT_SECRET_KEY` if present (may differ from KV).

If `/v2/login` returns an error:

1. **Re-run without jq** to see the raw response:
   ```powershell
   $cred = @{ username = $env:MP_USER; password = $plainSecret }
   Invoke-WebRequest -Method Post -Uri "$env:MP_API/v2/login" `
     -ContentType 'application/x-www-form-urlencoded' -Body $cred -ErrorAction Ignore | Select-Object -ExpandProperty Content
   ```

2. **Common failures:**
   - `"Invalid email or password"` → Credentials rotated (regenerate in Megaport portal)
   - Lockout message → Wait 30 min, contact admin
   - Connection timeout → Check firewall allows `api.megaport.com:443`

---

## 8. gcloud — Cloud Router (BGP)

| Goal | Command |
|---|---|
| List routers in a region | `gcloud compute routers list --filter="region:$env:REGION_A" --format="table(name, region, network.basename(), bgp.asn)"` |
| Router config (BGP + advertised) | `gcloud compute routers describe $env:ROUTER_A --region=$env:REGION_A --format=json \| jq '{name, asn:.bgp.asn, advertiseMode:.bgp.advertiseMode, advertisedRanges:.bgp.advertisedIpRanges, peers:[.bgpPeers[].name]}'` |
| Best routes (post-selection) | `gcloud compute routers get-status $env:ROUTER_A --region=$env:REGION_A --format=json \| jq -r '.result.bestRoutesForRouter[] \| [.destRange, .routeType, .nextHopIp, (.priority\|tostring)] \| @tsv'` |
| **Learned routes per peer, with AS path** | `gcloud compute routers get-status $env:ROUTER_A --region=$env:REGION_A --format=json \| jq -r '.result.bgpPeerStatus[] \| .name as $peer \| .learnedRoutes[]? \| [$peer, .destRange, .routeType, .nextHopIp, (.asPath \| @json // "-")] \| @tsv'` |
| BGP peer status (up/down, uptime, counters) | `gcloud compute routers get-status $env:ROUTER_A --region=$env:REGION_A --format=json \| jq -r '.result.bgpPeerStatus[] \| [.name, .ipAddress, (.peerIpAddress // "-"), .status, .state, (.uptime // "-"), (.numLearnedRoutes\|tostring)] \| @tsv'` |
| Routes advertised to a specific peer | `gcloud compute routers get-status $env:ROUTER_A --region=$env:REGION_A --format=json \| jq -r '.result.bgpPeerStatus[] \| select(.name=="<YOUR_BGP_PEER_NAME>") \| .advertisedRoutes[]? \| [.destRange, (.asPath \| @json // "-")] \| @tsv'` |

**Gotcha #1 — `.asPath` shape varies.** Sometimes an object (`{asns: [...], asPathSegmentType: "AS_SEQUENCE"}`), sometimes an array, sometimes absent. The `@json` trick renders whatever's there as a single TSV cell instead of crashing jq.

**Gotcha #2 — PARTNER Interconnect forces CR ASN to `16550`.** No matter what you set in TF/console, the CR ASN advertised to the peer over a PARTNER attachment is `16550` (Google's globally-shared PARTNER ASN). Don't fight it — `peerAsn` (the MCR side) is what you can actually control.

**Gotcha #3 — `numLearnedRoutes` includes filtered routes.** If you set an import policy, the count can be higher than what shows in `learnedRoutes[]`. Trust `.learnedRoutes[] | length`, not `.numLearnedRoutes`.

---

## 9. gcloud — Interconnect attachments + VPC routes

| Goal | Command |
|---|---|
| List Interconnect attachments | `gcloud compute interconnects attachments list --format="table(name, region, type, edgeAvailabilityDomain, state, pairingKey)"` |
| One attachment in detail | `gcloud compute interconnects attachments describe <YOUR_ATTACHMENT_NAME> --region=$env:REGION_A --format=json \| jq '{name, state, type, bandwidth, pairingKey, vlanTag8021q, cloudRouterIpAddress, customerRouterIpAddress, partnerAsn}'` |
| Effective VPC routes (what the data plane sees) | `gcloud compute routes list --filter="network:<YOUR_VPC>" --format="table(name, destRange, nextHopIp, nextHopGateway.basename(), nextHopVpnTunnel.basename(), priority)"` |
| Firewalls applied to a VPC | `gcloud compute firewall-rules list --filter="network:<YOUR_VPC>" --format="table(name, direction, priority, sourceRanges[0], targetTags[0], allowed[0].map().firewall_rule())"` |

**Gotcha — VPC routing mode (`REGIONAL` vs `GLOBAL`) is invisible in `routes list` output.** A route learned by Router-A (region-X) won't appear in region-Y's VM forwarding table unless the VPC has `routing_mode=GLOBAL`. Check the VPC's mode first: `gcloud compute networks describe <YOUR_VPC> --format='value(routingConfig.routingMode)'`.

---

## 10. Diagnostic patterns — combining the layers

### Pattern A — "Is prefix X reachable from VM Y, and what path will it take?"

Walk the layers top-down. Each command filters for one prefix so the output stays human-sized.

```powershell
$PREFIX = "10.50.1.0/24"

# 1. Effective routes on the VM's NIC (Azure side)
az network nic show-effective-route-table -g $env:RG -n $env:NIC -o json | jq -r --arg p $PREFIX '.value[] | select(.addressPrefix[0]==$p) | [.nextHopType, (.nextHopIpAddress // "-"), .source] | @tsv'

# 2. Hub's view (does the hub know the prefix?)
az network vhub get-effective-routes -g $env:RG -n $env:VHUB1 --resource-type RouteTable `
  --resource-id $(az network vhub route-table show -g $env:RG --vhub-name $env:VHUB1 -n defaultRouteTable --query id -o tsv) `
  -o json | jq -r --arg p $PREFIX '.value[] | select(.addressPrefixes[0]==$p) | [.nextHopType, (.nextHops|join(",")), .asPath] | @tsv'

# 3. ER GW learned-routes (which MSEE peer is providing it?)
az network vnet-gateway list-learned-routes -g $env:RG -n $env:ERGW1 -o json | jq -r --arg p $PREFIX '.value[] | select(.network==$p) | [.network, .nextHop, .asPath] | @tsv'

# 4. MSEE route table (is the MCR advertising it?)
az network express-route list-route-tables -g $env:RG -n $env:ERCKT1 --peering-name AzurePrivatePeering --path primary -o json | jq -r --arg p $PREFIX '.value[] | select(.network==$p) | [.nextHop, .path] | @tsv'

# 5. GCP CR — is the prefix being advertised to MCR?
gcloud compute routers get-status $env:ROUTER_A --region=$env:REGION_A --format=json | jq -r --arg p $PREFIX '.result.bgpPeerStatus[].advertisedRoutes[]? | select(.destRange==$p) | [.destRange, (.asPath|@json)] | @tsv'
```

Empty output at any layer = the prefix isn't propagating past that point. That's your break.

### Pattern B — "BGP session went down — which side?"

Quick health check across the chain:

| Layer | Command | "Up" looks like |
|---|---|---|
| ER circuit peering (config) | `az network express-route peering show -g $env:RG --circuit-name $env:ERCKT1 -n AzurePrivatePeering -o json \| jq '.state'` | `"Enabled"` |
| ER circuit BGP (presence test) | `az network express-route list-route-tables-summary -g $env:RG -n $env:ERCKT1 --peering-name AzurePrivatePeering --path primary -o json \| jq '.value\|length'` | `> 0` |
| ER GW BGP peers | `az network vnet-gateway list-bgp-peer-status -g $env:RG -n $env:ERGW1 -o json \| jq -r '.value[] \| [.neighbor, .state, .connectedDuration] \| @tsv'` | state = `Connected` |
| MCR VXC (Megaport view) | `$h = @{ 'X-Auth-Token' = $env:MP_TOKEN }; (irm -Uri "$env:MP_API/v2/product/$env:VXC_UID" -Headers $h).data.resources.csp_connection[0].interfaces[0].bgpConnections \| Select-Object peerIpAddress, sessionState` | sessionState = `ESTABLISHED` |
| GCP CR | `gcloud compute routers get-status $env:ROUTER_A --region=$env:REGION_A --format=json \| jq -r '.result.bgpPeerStatus[] \| [.name, .status, .state] \| @tsv'` | status = `UP`, state = `Established` |

### Pattern C — "Is traffic asymmetric? Are firewall flows dropping mid-session?"

When you suspect AzFW drops because forward and return packets hit different firewall instances:

1. Get the route the source VM uses to reach the destination (Pattern A, step 1).
2. Get the route the destination VM uses to reach the source (run Pattern A in reverse).
3. Compare the egress hub for each direction. If they differ → asymmetric. Each AzFW instance maintains its own state table; only the one that saw the SYN will accept the SYN-ACK back.

The fix is at the routing layer (prepending, prefix filters, hub-to-hub routing intent) — not at the firewall.

---

## 11. Quick aliases worth dropping into your $PROFILE

```powershell
# Azure
function er-routes {
  param([string]$RG, [string]$Circuit, [string]$Path = "primary")
  az network express-route list-route-tables -g $RG -n $Circuit --peering-name AzurePrivatePeering --path $Path -o json | jq -r ".value[] | [.network, .nextHop, .path] | @tsv"
}

function hub-routes {
  param([string]$RG, [string]$VHub)
  $routeTableId = az network vhub route-table show -g $RG --vhub-name $VHub -n defaultRouteTable --query id -o tsv
  az network vhub get-effective-routes -g $RG -n $VHub --resource-type RouteTable --resource-id $routeTableId -o json | jq -r ".value[] | [.addressPrefixes[0], .nextHopType, (.nextHops | join(\",\")), .asPath] | @tsv"
}

# GCP
function cr-learned {
  param([string]$Router, [string]$Region)
  gcloud compute routers get-status $Router --region=$Region --format=json | jq -r ".result.bgpPeerStatus[] | .name as \$p | .learnedRoutes[]? | [\$p, .destRange, .routeType, .nextHopIp, (.asPath | @json // \"-\")] | @tsv"
}

function cr-best {
  param([string]$Router, [string]$Region)
  gcloud compute routers get-status $Router --region=$Region --format=json | jq -r ".result.bestRoutesForRouter[] | [.destRange, .routeType, .nextHopIp] | @tsv"
}

# Megaport
function mp-vxc-bgp {
  param([string]$VXC_UID)
  $headers = @{ 'X-Auth-Token' = $env:MP_TOKEN }
  (irm -Uri "$env:MP_API/v2/product/$VXC_UID" -Headers $headers).data.resources.csp_connection[0].interfaces[0].bgpConnections | Select-Object peerIpAddress, peerAsn, sessionState
}
```

Usage:

- `er-routes rg-vwan-symm-103167 erckt-vhub1-... -Path primary`
- `hub-routes rg-vwan-symm-103167 vhub-...`
- `cr-learned router-a europe-west3`
- `mp-vxc-bgp $env:VXC_UID`

---

## 12. Maintenance notes

- **Why TSV and not table?** Most CLIs have an `-o table` mode, but column widths truncate AS-paths and FQDNs, and you can't `grep`/`awk` the output cleanly. TSV via jq is pipe-friendly across all three CLIs.
- **Why no `--query` JMESPath?** Azure CLI's `--query` is fine for one-shot filtering, but `jq` works identically across `az`, `gcloud`, and raw `curl` — fewer mental contexts to switch.
- **Adding a command?** Validate it against a live lab before merging. The MSEE route-table `-o table` bug, the looking-glass empty-response bug, and the `get-effective-routes` cold-start bug are real and not in MS Learn — call them out in the gotcha column with a source citation per `docs/README.md` rule #3.

## 13. Windows VM diagnostics

| Task | PowerShell |
|---|---|
| Routes | `Get-NetRoute -PolicyStore ActiveStore \| Where-Object NextHop -ne '0.0.0.0' \| Format-Table DestinationPrefix, NextHop, InterfaceAlias -AutoSize` |
| IPs | `Get-NetIPAddress -AddressFamily IPv4 \| Format-Table IPAddress, PrefixLength, InterfaceAlias` |
| Traceroute | `Test-NetConnection <ip> -TraceRoute` |
| DNS | `Resolve-DnsName <name> -Type A \| Format-Table Name, IPAddress, TTL` |
| TCP conns | `Get-NetTCPConnection -State Established \| Format-Table LocalAddress, LocalPort, RemoteAddress, RemotePort` |
| Packets (admin) | `pktmon start --capture --comp nics --pkt-size 0` |

---

## 14. PowerShell function wrappers

```powershell
function vhub-eff { param([string] $RG, [string] $Hub)
  $id = az network vhub route-table show -g $RG --vhub-name $Hub -n defaultRouteTable --query id -o tsv
  az network vhub get-effective-routes -g $RG -n $Hub --resource-type RouteTable --resource-id $id -o json | ConvertFrom-Json | Select-Object -ExpandProperty value | Format-Table addressPrefixes, asPath }

function mp-vxc-bgp { param([string] $VxcUid)
  curl.exe -s "$env:MP_API/v2/product/$VxcUid" -H "X-Auth-Token: $env:MP_TOKEN" | jq '.data.resources.csp_connection[0].interfaces[0].bgpConnections' }

function er-routes { param([string] $Circuit, [string] $RG)
  az network express-route route-table summary -g $RG -n $Circuit --peering-type AzurePrivatePeering -o json | ConvertFrom-Json | Select-Object -ExpandProperty value | Format-Table @{N='prefix'; E={$_[0].network}} }
```

---

## 15. PowerShell gotchas

- **curl alias:** Use `curl.exe`. Permanent: `Remove-Item Alias:curl -Force` in `$PROFILE`.
- **`&` in body:** Single-quote: `-d 'x=1&y=2'`.
- **Codes:** `Invoke-WebRequest` captures; `Invoke-RestMethod` throws (use `-SkipHttpErrorCheck`).
- **Admin:** pktmon, `Get-NetTCPConnection -IncludeAllProcesses` need elevation.

---

## 16. Contribution rules

Cross-lab, append not rewrite, cite sources, table format, no secrets, update index.
