> Diagrams: _(pending Oracle dispatch)_

# vwan-dual-er-symmetric: validation skeleton

> 📝 **Blog post:** _pending publication_ (Kid)

**Lab slug:** `vwan-dual-er-symmetric`
**Drafted:** 2026-06-15T09:53:31+02:00
**Status:** pre-deploy skeleton: fill in evidence at lab live time.
**Scenarios:** S1-S5 (per Morpheus draft)
**Expected show-output file count:** ~30-35

---

## Pre-deploy gates (sign-off checklist)

- [ ] `validation.md` skeleton committed ✅ (this dispatch: 2026-06-15)
- [ ] `design.md` from Trinity available: three-layer route-collection plan finalized. **BLOCKER: not yet landed.**
- [ ] `manifest.md` from Morpheus available: scenarios locked, pass/fail criteria explicit. **BLOCKER: not yet landed.**
- [ ] Tank's `terraform plan` reviewed: confirm these outputs exist: RG name, VM names, hub names (`hub1`/`hub2`), ER circuit names (`er1-<pop>`/`er2-<pop>`), MCR UIDs, Hub FW private IPs, spoke VM NIC names.

---

## Summary (fill in post-deploy)

| Area | Result | Notes |
|---|---|---|
| S1: Spoke1 ↔ GCP via Region-A symmetric |: | |
| S2: Spoke3 ↔ GCP via Region-B symmetric |: | |
| S3: Cross-region Spoke1 ↔ Spoke3 two-firewall |: | |
| S4: Asymmetric-routing failure injection |: | |
| S5: Hub-to-hub partition (stretch) |: | |

---

## S1: Symmetric Spoke1 ↔ GCP via Region-A path

**Objective:** Confirm Spoke1-VM traffic to GCP traverses Hub1 firewall in both directions; Hub2 firewall has no entries for this flow; ER path uses Circuit1/MCR1 only.

| # | Assertion | Verbatim command | Expected result | Pass/Fail | Evidence path |
|---:|---|---|---|---|---|
| 1 | Spoke1-VM NIC effective-route-table shows GCP prefix → Hub1 FW next-hop. | `az network nic show-effective-route-table --resource-group <RG> --name <spoke1-vm-nic> -o table` | One route matching GCP-prefix (`<gcp-subnet-prefix>`) with `nextHopType=VirtualAppliance`, `nextHopIp=<hub1-fw-private-ip>`. | | `show-output/01-effective-routes-spoke1-vm.txt` |
| 2 | Hub1 inbound routes for GCP prefix show source = ER GW (Circuit1). | `ERGW_CX_ID=$(az network express-route gateway connection list --gateway-name <hub1ergw-name> -g <RG> --query 'value[0].id' -o tsv)` then: `az rest --method post --uri "https://management.azure.com/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RG>/providers/Microsoft.Network/virtualHubs/<hub1-name>/inboundRoutes?api-version=2025-07-01" --body "{\"resourceUri\": \"$ERGW_CX_ID\", \"connectionType\": \"ExpressRouteConnection\"}"` (async: poll Location header) | Route to GCP prefix with `connectionId` containing `hub1ergw-…`; `routeOrigin` = ER connection. | | `show-output/02-hub1-inbound-routes.json` |
| 3 | Hub2 effective routes for Spoke1 prefix show next-hop = hub-to-hub interconnect, NOT Hub2's own ER GW (no bowtie). | `az network vhub get-effective-routes --resource-type RouteTable --resource-id <hub2-defaultRT-id> -g <RG> -n <hub2-name> --query 'value[].{Prefix:addressPrefixes[0],NextHopType:nextHopType,NextHop:nextHops[0],Origin:routeOrigin}' -o table` | Route for `<spoke1-prefix>` shows `routeOrigin` identifying Hub1 / inter-hub link, **not** Hub2's ExpressRoute GW. | | `show-output/03-hub2-effective-routes.json` |
| 4 | Hub1 ER GW BGP-connection advertised-routes to Circuit1 list Region-A spoke prefixes only. | `BGP_CX=$(az network vhub bgpconnection list --vhub-name <hub1-name> -g <RG> --query '[0].name' -o tsv)` then: `az rest --method post --uri "https://management.azure.com/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RG>/providers/Microsoft.Network/virtualHubs/<hub1-name>/bgpConnections/${BGP_CX}/advertisedRoutes?api-version=2025-07-01"` (async) | Only `<spoke1-prefix>`, `<spoke2-prefix>`, `<hub1-prefix>` present. `<spoke3-prefix>`, `<spoke4-prefix>`, `<hub2-prefix>` must NOT appear. | | `show-output/04-hub1ergw-advertised.json` |
| 5 | MCR1 VXC exports to GCP-facing VXC only Region-A spoke prefixes. | Megaport REST: `GET https://api.megaport.com/v2/product/<mcr1-uid>` to get VXC list; then MCR looking-glass (if available): `POST https://api.megaport.com/v2/product/<mcr1-uid>/lookingglass/bgp` with `{"vxcUid":"<gcp-vxc-uid>","type":"advertised"}`. Fallback if looking-glass unavailable: document VXC `ipAddresses` and `bgpConfig.prefixLists` from VXC resource. | Only `<spoke1-prefix>` and `<spoke2-prefix>` (Region-A) exported toward GCP VXC. `<spoke3-prefix>`, `<spoke4-prefix>` absent. | | `show-output/05-mcr1-gcp-export.json` |
| 6 | Data-plane: Spoke1-VM → GCP-VM HTTP succeeds; return path GCP → Spoke1 also succeeds. | `az vm run-command invoke -g <RG> -n <spoke1-vm-name> --command-id RunShellScript --scripts "curl -sv --max-time 5 http://<gcp-vm1-private-ip>:80 2>&1 \| head -20"` | HTTP 200 or TCP connect established (SYN-ACK visible in `-sv` output). No `Connection refused` / `No route to host`. | | `show-output/06-spoke1-to-gcp-curl.txt` |
| 7 | Hub1 FW logs show flow; Hub2 FW has ZERO entries for this Spoke1↔GCP flow. | Hub1 KQL: `AzureDiagnostics \| where Category == "AzureFirewallNetworkRule" \| where TimeGenerated > ago(30m) \| where msg_s contains "<spoke1-vm-ip>" and msg_s contains "<gcp-vm1-private-ip>" \| project TimeGenerated, msg_s`: run against **Hub1** FW Log Analytics workspace; repeat against **Hub2** FW workspace and confirm zero hits. | Hub1 FW: ≥1 `Allow` entries with Spoke1 source IP and GCP dest IP. Hub2 FW: 0 entries for this IP pair. | | `show-output/07-firewall-logs-s1.txt` |

---

## S2: Symmetric Spoke3 ↔ GCP via Region-B path

**Objective:** Mirror of S1 with Hub2 / Circuit2 / MCR2 / Spoke3-VM substituted. Confirms per-region ER affinity holds in both directions.

| # | Assertion | Verbatim command | Expected result | Pass/Fail | Evidence path |
|---:|---|---|---|---|---|
| 8 | Spoke3-VM NIC effective-route-table shows GCP prefix → Hub2 FW next-hop. | `az network nic show-effective-route-table --resource-group <RG> --name <spoke3-vm-nic> -o table` | Route to GCP-prefix with `nextHopType=VirtualAppliance`, `nextHopIp=<hub2-fw-private-ip>`. | | `show-output/08-effective-routes-spoke3-vm.txt` |
| 9 | Hub2 inbound routes for GCP prefix show source = Circuit2/MCR2. | `ERGW2_CX_ID=$(az network express-route gateway connection list --gateway-name <hub2ergw-name> -g <RG> --query 'value[0].id' -o tsv)` then: `az rest --method post --uri "https://management.azure.com/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RG>/providers/Microsoft.Network/virtualHubs/<hub2-name>/inboundRoutes?api-version=2025-07-01" --body "{\"resourceUri\": \"$ERGW2_CX_ID\", \"connectionType\": \"ExpressRouteConnection\"}"` | Route to GCP prefix with `connectionId` containing `hub2ergw-…`. | | `show-output/09-hub2-inbound-routes.json` |
| 10 | Hub1 effective routes for Spoke3 prefix show next-hop = hub-to-hub, NOT Hub1's ER GW. | `az network vhub get-effective-routes --resource-type RouteTable --resource-id <hub1-defaultRT-id> -g <RG> -n <hub1-name> --query 'value[].{Prefix:addressPrefixes[0],NextHopType:nextHopType,NextHop:nextHops[0],Origin:routeOrigin}' -o table` | `<spoke3-prefix>` origin = Hub2/inter-hub, not Hub1's ER. | | `show-output/10-hub1-effective-routes.json` |
| 11 | Hub2 ER GW BGP-connection advertised-routes list Region-B prefixes only. | `BGP_CX2=$(az network vhub bgpconnection list --vhub-name <hub2-name> -g <RG> --query '[0].name' -o tsv)` then advertised-routes REST (same pattern as #4 with hub2). | Only `<spoke3-prefix>`, `<spoke4-prefix>`, `<hub2-prefix>`. Region-A spokes absent. | | `show-output/11-hub2ergw-advertised.json` |
| 12 | MCR2 VXC exports to GCP-facing VXC only Region-B prefixes. | Same Megaport REST pattern as #5 with `<mcr2-uid>`. | Only `<spoke3-prefix>` and `<spoke4-prefix>` exported. Region-A prefixes absent. | | `show-output/12-mcr2-gcp-export.json` |
| 13 | Data-plane: Spoke3-VM → GCP-VM HTTP succeeds; return path also succeeds. | `az vm run-command invoke -g <RG> -n <spoke3-vm-name> --command-id RunShellScript --scripts "curl -sv --max-time 5 http://<gcp-vm2-private-ip>:80 2>&1 \| head -20"` | HTTP 200 or TCP connect established. | | `show-output/13-spoke3-to-gcp-curl.txt` |
| 14 | Hub2 FW logs show flow; Hub1 FW has ZERO entries for this Spoke3↔GCP flow. | Same KQL pattern as #7 against Hub2 FW and Hub1 FW workspaces; filter on Spoke3-VM IP + GCP VM2 IP. | Hub2 FW: ≥1 Allow. Hub1 FW: 0 entries. | | `show-output/14-firewall-logs-s2.txt` |

---

## S3: Cross-region Spoke1 ↔ Spoke3 (symmetric two-firewall)

**Objective:** East-west traffic between spokes in different regions must transit both Hub1 FW (Spoke1 side) and Hub2 FW (Spoke3 side). Both firewalls must log the flow. Hub-to-hub inter-link must carry the traffic, not any ER path.

| # | Assertion | Verbatim command | Expected result | Pass/Fail | Evidence path |
|---:|---|---|---|---|---|
| 15 | Spoke1 effective route to Spoke3 prefix → next-hop = Hub1 FW. | `az network nic show-effective-route-table --resource-group <RG> --name <spoke1-vm-nic> -o table` | Route for `<spoke3-prefix>` with `nextHopType=VirtualAppliance`, `nextHopIp=<hub1-fw-private-ip>`. | | `show-output/15-spoke1-nic-to-spoke3.txt` |
| 16 | Hub1 outbound route for Spoke3 prefix → next-hop = vHub-to-vHub interconnect (toward Hub2). | `az rest --method post --uri "https://management.azure.com/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RG>/providers/Microsoft.Network/virtualHubs/<hub1-name>/outboundRoutes?api-version=2025-07-01" --body "{\"resourceUri\": \"<hub1-ergw-cx-id>\", \"connectionType\": \"ExpressRouteConnection\"}"` | `<spoke3-prefix>` next-hop points to inter-hub link resource ID, not Hub1's own ER GW. | | `show-output/16-hub1-outbound-routes.json` |
| 17 | Hub2 inbound for Spoke3 prefix arriving from Hub1 side, next forwarded to Hub2 FW. | `az rest --method post --uri "https://management.azure.com/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RG>/providers/Microsoft.Network/virtualHubs/<hub2-name>/inboundRoutes?api-version=2025-07-01" --body "{\"resourceUri\": \"<hub2-vnet-cx-spoke3-id>\", \"connectionType\": \"HubVirtualNetworkConnection\"}"` | Route for `<spoke1-prefix>` arriving with origin = Hub1 / inter-hub. Next-hop after Hub2 = Hub2 FW. | | `show-output/17-hub2-inbound-spoke3.json` |
| 18 | Hub2 outbound route for Spoke3 → next-hop = Spoke3 VNet connection (final delivery). | `az rest --method post --uri "https://management.azure.com/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RG>/providers/Microsoft.Network/virtualHubs/<hub2-name>/outboundRoutes?api-version=2025-07-01" --body "{\"resourceUri\": \"<hub2-vnet-cx-spoke3-id>\", \"connectionType\": \"HubVirtualNetworkConnection\"}"` | `<spoke3-prefix>` next-hop = Spoke3 VNet connection, not ER or inter-hub. | | `show-output/18-hub2-outbound-spoke3.json` |
| 19 | Reverse path (Spoke3 → Spoke1): Spoke3 effective route to Spoke1 prefix → Hub2 FW. | `az network nic show-effective-route-table --resource-group <RG> --name <spoke3-vm-nic> -o table` | Route for `<spoke1-prefix>` with `nextHopType=VirtualAppliance`, `nextHopIp=<hub2-fw-private-ip>`. | | `show-output/19-spoke3-nic-to-spoke1.txt` |
| 20 | Data-plane: Spoke1-VM → Spoke3-VM HTTP succeeds; return path also succeeds. | `az vm run-command invoke -g <RG> -n <spoke1-vm-name> --command-id RunShellScript --scripts "curl -sv --max-time 5 http://<spoke3-vm-ip>:80 2>&1 \| head -20"` | HTTP 200 or TCP connect established. | | `show-output/20-spoke1-to-spoke3-curl.txt` |
| 21 | Hub1 FW AND Hub2 FW both log the Spoke1↔Spoke3 flow (one entry each, both directions consistent). | Same KQL pattern as #7; filter on `<spoke1-vm-ip>` and `<spoke3-vm-ip>`; run against Hub1 FW and Hub2 FW workspaces separately. | Hub1 FW: ≥1 Allow (Spoke1 source). Hub2 FW: ≥1 Allow (Spoke3 source). Neither firewall shows a Drop for this flow. | | `show-output/21-firewall-logs-s3.txt` |

---

## S4: Asymmetric-routing failure injection (optional; run last: perturbs state)

**Objective:** Demonstrate the failure mode that traffic-symmetry prevents. Temporarily reconfigure MCR1 to advertise Region-B prefixes to GCP, break per-region affinity, and capture the stateful-drop that results. Revert after capture and re-verify S1 to confirm restored symmetry.

**⚠️ Run this scenario LAST. It actively breaks routing and will impact S1-S3 traffic until reverted.**

### Phase A: Inject asymmetry

| # | Assertion / Action | Verbatim command | Expected result | Pass/Fail | Evidence path |
|---:|---|---|---|---|---|
| 20 | Pre-injection baseline: confirm S1 data-plane still passing (GCP→Spoke1 symmetric). | Re-run S1 assertion #6 and #7 commands. | S1 passes (PASS carry-forward from steady-state). | | `show-output/20-s4-pre-inject-s1-baseline.txt` |
| 21 | Inject: expand MCR1 prefix-list to include `<spoke3-prefix>` / `<spoke4-prefix>` toward GCP VXC. | Megaport REST PUT on `<mcr1-uid>` VXC BGP config to add Region-B prefixes to export policy. Exact payload: `{"bgpConnections": [{"id": "<gcp-vxc-bgp-id>", "exportPolicy": {"prefixList": ["<spoke1-prefix>","<spoke2-prefix>","<spoke3-prefix>","<spoke4-prefix>"]}}]}` _(exact field names confirmed from MCR API at lab time)_. | MCR1 now advertises Region-B prefixes toward GCP; GCP Cloud Router learns both Region-A and Region-B via MCR1. | | `show-output/21-s4-mcr1-inject.json` |
| 22 | Confirm GCP Cloud Router has now learned Region-B prefixes via MCR1 (wrong path). | `gcloud compute routers get-status <router1-name> --region=<gcp-region1> --format=json \| jq -r '.result.bestRoutesForRouter[] \| {destRange,routeType,nextHopIp} \| join("\t")'` | `<spoke3-prefix>` and `<spoke4-prefix>` now appear in router1 best routes. Smoke signal that asymmetry is in place. | | `show-output/22-s4-gcp-router1-learned-after-inject.json` |
| 23 | Data-plane test: Spoke3-VM → GCP-VM2: SYN leaves via Hub2 FW; GCP return SYN-ACK comes back via MCR1 → Hub1; Hub1 FW drops (no connection state). | `az vm run-command invoke -g <RG> -n <spoke3-vm-name> --command-id RunShellScript --scripts "curl -sv --max-time 10 http://<gcp-vm2-private-ip>:80 2>&1 \| head -30"` | Curl hangs or times out. No HTTP response. Spoke3-VM sees SYN sent but no SYN-ACK returned. | | `show-output/23-s4-spoke3-to-gcp-asymmetric-curl.txt` |
| 24 | NSG flow logs: Spoke3-VM NIC shows outbound SYN; no return inbound. | `az network watcher flow-log list --location <hub2-region> -g <RG> -o table` then: confirm spoke3 NIC NSG has flow log enabled → query Log Analytics: `AzureNetworkAnalytics_CL \| where FlowType_s == "ExternalPublic" or SubType_s == "FlowLog" \| where SrcIP_s == "<spoke3-vm-ip>" \| project TimeGenerated, FlowDirection_s, L4Protocol_s, DestIP_s, FlowStatus_s` | Outbound flow from Spoke3 IP to GCP IP visible; NO matching inbound return. | | `show-output/24-s4-nsg-flow-logs-spoke3.txt` |
| 25 | Hub2 FW log: SYN-out accepted (Spoke3→GCP). Hub1 FW log: return packet DROPPED (no matching state). | Same KQL as #7 but for Spoke3↔GCP2 flow pair. Run against Hub2 FW (connection accepted) and Hub1 FW (drop / stateful reject). | Hub2 FW: Allow on Spoke3→GCP-IP. Hub1 FW: Drop or no-match on GCP-IP→Spoke3 return. This is the proof of the failure mode. | | `show-output/25-s4-firewall-logs-asymmetric.txt` |

### Phase B: Revert and verify

| # | Assertion / Action | Verbatim command | Expected result | Pass/Fail | Evidence path |
|---:|---|---|---|---|---|
| 26 | Revert MCR1 export policy to Region-A prefixes only. | Megaport REST PUT: restore original prefix-list (Region-A only) on GCP-facing VXC. | MCR1 stops advertising `<spoke3-prefix>`/`<spoke4-prefix>`. | | `show-output/26-s4-mcr1-revert.json` |
| 27 | GCP Cloud Router no longer shows Region-B prefixes via MCR1. | Re-run `gcloud compute routers get-status` command from #22. | `<spoke3-prefix>` and `<spoke4-prefix>` absent from router1 best routes (or reverted to MCR2 path). | | `show-output/27-s4-gcp-router1-post-revert.json` |
| 28 | S1 data-plane restored: Spoke1 → GCP succeeds, Hub1 FW logs Accept, Hub2 FW zero entries. | Re-run S1 assertions #6 and #7 verbatim. | Pass. Symmetry restored. | | `show-output/28-s4-s1-post-revert-verify.txt` |

---

## S5: Hub-to-hub partition (stretch goal: skip unless Morpheus calls for it)

**Objective:** Remove inter-hub link and verify that cross-region (Spoke1↔Spoke3) connectivity breaks gracefully; no black-hole routing; ER paths do not silently take over as an unintended hub-to-hub path.

_Details to be filled from Morpheus manifest. Commands and assertions TBD at lab time._

| # | Assertion | Verbatim command | Expected result | Pass/Fail | Evidence path |
|---:|---|---|---|---|---|
| 29 | Spoke1 → Spoke3 connectivity fails after hub partition. | `az vm run-command invoke … --scripts "curl -sv --max-time 5 http://<spoke3-vm-ip>:80 2>&1"` | Connection refused / timeout. No black-hole (traceroute shows max-TTL). | | `show-output/29-s5-spoke1-to-spoke3-partition.txt` |
| 30 | ER paths do NOT silently become an inter-hub bypass. | Re-run S1 effective-routes (#3) and Hub1 advertised-routes (#4) to confirm Region-A still only in Hub1. | Unchanged from S1 steady-state. No cross-contamination. | | `show-output/30-s5-er-no-bypass.json` |
| 31 | Restore inter-hub link; cross-region connectivity recovers. | Morpheus/Tank action: re-link hubs. Re-run S3 data-plane (#20). | S3 passes. | | `show-output/31-s5-recovery-verify.txt` |

---

## Three-layer route-collection checklist

_Trinity's `design.md` "1.6 Three-layer route-collection plan" will finalize exact resource IDs and ordering. The layers below are the expected capture set; refresh numbers post-Trinity dispatch._

| Layer | Description | Commands / action | File(s) | Captured |
|---|---|---|---|---|
| **A** | VM NIC effective routes × 4 (one per spoke VM) | `az network nic show-effective-route-table -g <RG> --name <nic-name> -o table` × 4 | `show-output/01-effective-routes-spoke1-vm.txt`, `08-…spoke3-vm.txt`, `A3-spoke2-vm.txt`, `A4-spoke4-vm.txt` | ☐ |
| **B1** | Hub1 effective routes (DefaultRouteTable) | `az network vhub get-effective-routes --resource-type RouteTable --resource-id <hub1-defaultRT-id> -g <RG> -n <hub1-name> -o table` | `show-output/10-hub1-effective-routes.json` | ☐ |
| **B2** | Hub1 inbound routes (ER connection) | REST POST `/virtualHubs/<hub1-name>/inboundRoutes` body `ExpressRouteConnection` | `show-output/02-hub1-inbound-routes.json` | ☐ |
| **B3** | Hub1 outbound routes (ER connection) | REST POST `/virtualHubs/<hub1-name>/outboundRoutes` body `ExpressRouteConnection` | `show-output/16-hub1-outbound-routes.json` | ☐ |
| **B4** | Hub2 effective routes (DefaultRouteTable) | Same as B1 with `<hub2-name>` | `show-output/03-hub2-effective-routes.json` | ☐ |
| **B5** | Hub2 inbound routes (ER connection) | REST POST `/virtualHubs/<hub2-name>/inboundRoutes` | `show-output/09-hub2-inbound-routes.json` | ☐ |
| **B6** | Hub2 outbound routes (ER connection) | REST POST `/virtualHubs/<hub2-name>/outboundRoutes` | `show-output/18-hub2-outbound-spoke3.json` _(reuse or separate capture)_ | ☐ |
| **C1** | Hub1 ER GW BGP-connection advertised routes | REST POST `/virtualHubs/<hub1-name>/bgpConnections/<bgp-cx>/advertisedRoutes` | `show-output/04-hub1ergw-advertised.json` | ☐ |
| **C2** | Hub1 ER GW BGP-connection learned routes | REST POST `/virtualHubs/<hub1-name>/bgpConnections/<bgp-cx>/learnedRoutes` | `show-output/C2-hub1ergw-learned.json` | ☐ |
| **C3** | Hub2 ER GW BGP-connection advertised routes | Same as C1 with hub2 | `show-output/11-hub2ergw-advertised.json` | ☐ |
| **C4** | Hub2 ER GW BGP-connection learned routes | REST POST `/virtualHubs/<hub2-name>/bgpConnections/<bgp-cx2>/learnedRoutes` | `show-output/C4-hub2ergw-learned.json` | ☐ |
| **D1** | ER Circuit1 route table (primary) | `az network express-route list-route-tables --name <circuit1-name> -g <RG> --path primary --peering-name AzurePrivatePeering -o json` | `show-output/D1-er-circuit1-route-table-primary.json` | ☐ |
| **D2** | ER Circuit2 route table (primary) | `az network express-route list-route-tables --name <circuit2-name> -g <RG> --path primary --peering-name AzurePrivatePeering -o json` | `show-output/D2-er-circuit2-route-table-primary.json` | ☐ |
| **E1** | MCR1 BGP routes toward GCP VXC (looking-glass) | `POST https://api.megaport.com/v2/product/<mcr1-uid>/lookingglass/bgp` `{"vxcUid":"<gcp-vxc-uid>","type":"advertised"}`: fallback: GET VXC resource | `show-output/05-mcr1-gcp-export.json` | ☐ |
| **E2** | MCR2 BGP routes toward GCP VXC (looking-glass) | Same with `<mcr2-uid>` | `show-output/12-mcr2-gcp-export.json` | ☐ |
| **F1** | GCP Cloud Router1 learned + best routes | `gcloud compute routers get-status <router1-name> --region=<gcp-region1> --format=json \| jq -r '.result.bestRoutesForRouter[] \| {destRange,routeType,nextHopIp} \| join("\t")'` | `show-output/F1-gcp-router1-routes.json` | ☐ |
| **F2** | GCP Cloud Router2 learned + best routes | Same with `<router2-name>` and `<gcp-region2>` | `show-output/F2-gcp-router2-routes.json` | ☐ |
| **G1** | Hub1 Azure Firewall logs (KQL) | `AzureDiagnostics \| where Category == "AzureFirewallNetworkRule" \| where TimeGenerated > ago(2h) \| project TimeGenerated, msg_s \| order by TimeGenerated desc \| limit 500`: run against Hub1 FW Log Analytics workspace | `show-output/07-firewall-logs-s1.txt` _(reused / extended)_ | ☐ |
| **G2** | Hub2 Azure Firewall logs (KQL) | Same KQL against Hub2 FW Log Analytics workspace | `show-output/14-firewall-logs-s2.txt` _(reused / extended)_ | ☐ |

**Total expected files in `show-output/` at lab end: ~30-35.** Lab #1 had 30 files; this lab is roughly twice the topology scope.

---

## Post-deploy validation order

1. **Wait for routing-intent rollout** (10-20 min after vhub apply: per Trinity's gotcha on RI propagation delay; do NOT capture routes before this window).
2. **Run Layer A-G steady-state capture** (three-layer route collection: all ~20 files).
3. **Run S1 and S2 data-plane tests** (Spoke1↔GCP and Spoke3↔GCP).
4. **Run S3 data-plane test** (Spoke1↔Spoke3 cross-region).
5. **Run S4 asymmetric-injection** (LAST: perturbs state; capture full Phase A + Phase B).
6. **Run S5 hub-partition** (if Morpheus calls for it: also state-perturbing).
7. **Final steady-state capture** after S4/S5 revert.
8. **Sign off:** all assertions Pass (or documented anomaly with explanation), all evidence files present, sanitization sweep complete.

---

## Sanitization checklist (pre-commit: every file in `show-output/`)

| Item | Replace with | Verified |
|---|---|---|
| Subscription ID GUIDs in resource IDs | `<SUBSCRIPTION_ID>` | ☐ |
| ER service keys (UUIDs from circuit provisioning) | `<ER_SERVICE_KEY_REDACTED>` | ☐ |
| Megaport API keys / secrets (Authorization header, `apiKey` field) | `<MEGAPORT_API_KEY_REDACTED>` | ☐ |
| VM admin passwords (visible in run-command output) | `<REDACTED>` | ☐ |
| GCP service account key JSON | `<GCP_SA_KEY_REDACTED>` | ☐ |
| Base64-encoded access keys / SAS tokens / JWTs | `<TOKEN_REDACTED>` | ☐ |

---

## Lab-live deliverables (after deploy: separate dispatch)

- `show-output/` (~30-35 files, numbered, one command per file)
- `screenshots/`: effective-routes blade per VM (×4), Azure FW analytics (×2), vWAN hub topology view (×2), NSG flow log analytics
- `lessons-learned.md`
- `README.md` finalization (replace placeholders with actual outcomes, blog link)
- `validation.md` fill-in (Pass/Fail + evidence paths: this file)

---

_Niobe: Lab Validator & Diagnostics | pre-deploy skeleton | 2026-06-15T09:53:31+02:00_
