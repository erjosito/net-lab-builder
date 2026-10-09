# Design: AKS kubenet + legacy AppGW v2 shared UDR (Trinity, offline)

Historical planning design (written offline before deployment); see README.md for what was actually deployed and observed. The temporary probe VM/subnet/`rt-probe` described below were NOT deployed. `swedencentral`. Do not touch `EnableApplicationGatewayNetworkIsolation` (NotRegistered); if Registered, pause for Jose. NVA: `ip_forward=1` persisted + `iptables -t nat -A POSTROUTING -s 10.21.0.0/16 -o eth0 -j MASQUERADE`. Internet-client->public frontend is informational only (asymmetric returns); decisive HTTP test = NVA 10.20.1.4 -> private frontend 10.21.2.250 (peering route more specific than 0/0, symmetric). Verify D2as_v5/B2ts_v2 capacity/quota first.


## 1. Topology (exact)
| Item | Value |
|---|---|
| Hub VNet `vnet-hub` | 10.20.0.0/16; `snet-nva` 10.20.1.0/24 |
| NVA `nva1` | Ubuntu, Standard_B2ts_v2 (fallback B2ls_v2), `~/.ssh/id_rsa.pub`, NIC static 10.20.1.4, **NIC IP forwarding on**, Standard static PIP |
| Spoke VNet `vnet-spoke` | 10.21.0.0/16; `snet-aks` 10.21.1.0/24; `snet-appgw` 10.21.2.0/24 (planned temporary `snet-probe` not deployed) |
| Peering | hub<->spoke, both sides allowVirtualNetworkAccess + allowForwardedTraffic = true |
| AKS | Free tier, kubenet, pod 10.244.0.0/16, service 10.0.0.0/16, DNS 10.0.0.10, 1x Standard_D2as_v5, default outbound type loadBalancer (no UDR outboundType claim), user-assigned identity |
| AppGW `agw1` | Standard_v2, autoscale 1-2, public frontend **plus** static private frontend 10.21.2.250, listener :80 |


## 2. Route table and NSG
Create **BYO** `rt-shared` (BGP propagation disabled) before the cluster; attach to `snet-aks` and `snet-appgw`. AKS writes per-node pod routes (`10.244.x.0/24` -> VirtualAppliance node IP) into it; this is the same AKS-managed pod table. Grant the AKS identity `Network Contributor` on `rt-shared` and `snet-aks`.

- Baseline routes: pod routes (AKS-written) + `default` 0.0.0.0/0 -> Internet (supported v2 scenario).
- Treatment routes: `default` changed to 0.0.0.0/0 -> VirtualAppliance 10.20.1.4, plus `gm` GatewayManager (service tag) -> Internet.
- *(Not deployed)* The planned temporary `rt-probe` and probe VM were dropped; NVA transit was proven later by pod egress reporting the NVA public IP.

NSG `nsg-agw` on `snet-appgw`: allow in `GatewayManager` -> any TCP 65200-65535 (prio 100); `Internet` -> 80 (110); `VirtualNetwork` -> 80 (120); AzureLoadBalancer default; keep default outbound Internet allow, no deny rules. NSG `nsg-nva` on `snet-nva`: allow in 10.21.0.0/16 any. No NSG on `snet-aks` (AKS manages the node NSG).

RBAC: AGIC add-on identity (`ingressApplicationGateway` in `MC_*`) -> Contributor on `agw1`, Reader on its RG, Network Contributor on `vnet-spoke` (needs subnets/join/action + read). Enable with `az aks enable-addons -a ingress-appgw --appgw-id <agw1 id>`; confirm `rt-shared` is on `snet-appgw`.

## 3. Baseline B (safe; must pass before treatment)
1. Create hub/spoke/peering and NVA (the planned probe VM gate was not used).
2. Create `rt-shared` (default->Internet), NSGs, AKS, AppGW, add-on, sample app (aspnetapp Deployment/Service/Ingress, class `azure-application-gateway`).
3. Gate: AppGW `provisioningState=Succeeded`, `operationalState=Running`; `az network application-gateway show-backend-health` Healthy to pod IP 10.244.x.x; metrics return data over 5 min; from NVA `curl http://10.21.2.250/` = 200.


## 4. Ordered experiment (Jose's required sequence)

Keep the same route table, pod routes, NSGs, gateway, and workload throughout.
Each mutation and its read-only validation has a separate bounded owner/lease.

1. **Forced-tunnel control:** from verified B, change only `default` to
   `0.0.0.0/0 -> VirtualAppliance 10.20.1.4`. Do not add `gm` yet and do not
   modify the gateway to force revalidation.
2. **Control acceptance gate:** a request originating inside an AKS pod to an
   external source-IP endpoint must report the NVA public IP (prefer corroborating
   NVA NAT counters). Separately query AppGW backend health and capture the exact
   error, timeout, or Unknown state. Observe bounded convergence; an immediate
   healthy response is not proof the control plane remains healthy. HTTP
   data-plane availability alone does not prove control-plane health.
3. **Treatment:** proceed only if pod egress through the NVA and AppGW
   control-plane failure are both established. Preserve the NVA default and add
   only `gm`, `GatewayManager -> Internet`. Do not restore B between control and
   treatment; the verified forced-tunnel state is the treatment's named baseline.
4. **Treatment acceptance gate:** repeat the same pod-originated source-IP
   request and backend-health query. Pod egress must still report the NVA public
   IP and backend-health visibility must recover to known healthy backends.
   Capture time to recovery and any supporting metrics without treating absent
   idle metrics as decisive failure.

Stop if a route write is rejected, either control precondition is unproven, or
the bounded observation interval expires. Report `BLOCKED` or `INCONCLUSIVE`
as appropriate rather than applying the exception anyway. A rejected route is
an admission result, not evidence of a broken running gateway. Do not add a
gateway PUT/tag mutation unless a later, explicitly scoped investigation needs it.
Restore B after the treatment verdict or a stopped control, with read-only restore
verification before any new experiment.

## 5. Stop and restore (<=15 min, same lease)
Stop at first decisive outcome or 10 min observation; no retry or diagnosis.
```
az network route-table route update -g $RG --route-table-name rt-shared -n default --next-hop-type Internet --remove nextHopIpAddress
az network route-table route delete -g $RG --route-table-name rt-shared -n gm
az network application-gateway update -g $RG -n agw1 --set tags.probe=restore
```
Verify: routes = pod routes + default->Internet; AppGW Succeeded/Running; backend Healthy; probe 200; metrics present. Not restored by 15 min => `BLOCKED`, freeze, recovery lease for a different owner.

## 6. Feasibility and open items for Tank
- Docs say v2 0/0 to a virtual appliance is unsupported, and UDRs can break backend health/logs/metrics; no GatewayManager exception is documented. Rejection is likely and a valid result.
- Kubenet is under AKS retirement notice; confirm `az aks create --network-plugin kubenet` is accepted before spend. If not, report BLOCKED; no CNI/Overlay/AGC substitute.

Sources: [AppGW infrastructure configuration](https://learn.microsoft.com/azure/application-gateway/configuration-infrastructure) · [AKS kubenet BYO route table](https://learn.microsoft.com/azure/aks/configure-kubenet) · [Service tags in UDRs](https://learn.microsoft.com/azure/virtual-network/service-tags-overview).


