# AKS kubenet + AGIC shared-UDR lab

**Status: HISTORICAL PLANNING CARD; the lab was deployed and tested.** See [README.md](README.md) for actual results. Original text below is kept as planned: the preflight found the feature `NotRegistered` and B2ts_v2/B2ls_v2/D2as_v5 unrestricted in `swedencentral` (B1ls/B1s absent); capacity was then confirmed by deployment.

## Question and topology

Test whether adding `GatewayManager` service-tag → `Internet` to a shared route table makes legacy Application Gateway v2 control-plane health survive a `0.0.0.0/0 → hub NVA` route. The same table is attached to both AKS node and Application Gateway subnets. This is an unsupported-combination experiment, not a production recommendation; do not presume the exception works.

Use **legacy** Application Gateway behavior: never register/unregister `Microsoft.Network/EnableApplicationGatewayNetworkIsolation`, configure its per-gateway capabilities, or substitute network isolation/private deployment. A public frontend does not imply that feature.

- `swedencentral`: hub `10.20.0.0/16` (NVA `10.20.1.0/24`); peered spoke `10.21.0.0/16` (AKS `10.21.1.0/24`, App Gateway `10.21.2.0/24`, preferably `/24`). Kubenet pod CIDR `10.244.0.0/16`; service CIDR non-overlapping.
- Attach one shared route table to both spoke subnets. Preserve AKS-managed per-node pod routes. NVA requires Azure NIC and Linux IP forwarding plus SNAT.
- AKS Free control plane, one non-zonal system node: **`Standard_D2as_v5` (2 vCPU/8 GiB)**. AKS system pools require ≥2 vCPU/4 GiB and prohibit B-series. Catalog passed; capacity/quota/version checks pending.
- NVA: cheapest skill-ladder candidate **`Standard_B2ts_v2` (2 vCPU/1 GiB)**; unrestricted catalog, capacity pending. If memory is inadequate, next `B2ls_v2`.
- Public `Standard_v2` App Gateway + AGIC AKS add-on; Kubenet is supported, CNI/Overlay out of scope. No AGC. Grant AKS identity subnet/route-table rights and AGIC identity App Gateway/VNet rights. AKS creates separate `MC_*` node RG. No ExpressRoute/Megaport.

## Decisive order / stop and restore

1. **Baseline:** same Kubenet/AGIC topology and shared table, pod routes intact, no forced `0/0 → NVA`. Verify gateway `Succeeded`, healthy AKS backends, public HTTP ingress, and gateway metrics/logs.
2. **Negative control:** add `0/0 → NVA` only. Verify a pod-originated Internet request reports the NVA public IP and separately establish gateway control-plane failure using backend-health queries. If either condition is unproven, stop; do not add the exception.
3. **Treatment:** preserve the verified forced-tunnel control state and add only `GatewayManager → Internet`. Repeat the same checks: pod egress must still use the NVA and backend-health visibility must recover. Restore the Internet-route baseline after the verdict. Keep routing mutations and read-only validation in separate bounded leases.

Each variant: ≤10-minute observation after route change; restore and verify within 15 minutes. If restore fails, stop as blocked. Assess control-plane/telemetry separately from public-client ingress/return traffic: a successful HTTP request alone is not a control-plane pass.

**Feasibility warning:** Microsoft says a non-isolated v2 gateway cannot have a `0/0` UDR next-hop virtual appliance; forced tunneling is unsupported and can break management/provisioning. Kubenet pod routes on the App Gateway subnet are separately supported. Service tags are valid UDR prefixes, but Microsoft does not document a `GatewayManager` route as an exception that makes forced tunneling supported. Creation rejection is a valid decisive result.

## Cost and time (rough, not a quote)

| Resource | Estimate while running |
|---|---:|
| AKS Free control plane + 1 D2as_v5 node/disk | ~$0.10–0.16/hour |
| Standard_v2 App Gateway + public IP | ~$0.25–0.45/hour |
| B2ts_v2 NVA + disk/public IP | ~$0.04–0.10/hour |
| VNets/route table | No hourly charge; peering/data transfer usage-based |
| **Total** | **~$0.40–0.75/hour (~$10–18/day)** |

Excludes egress, log ingestion, tax, regional variance. Provisioning budget: **30–60 minutes**. Confirm exact prices before deployment; delete only under the separate cleanup approval gate.

## Planned gates (historical) and sources

Coordinator: perform live-capacity checks for both VM sizes; confirm quota, supported AKS version, identity scopes, and a safely stageable/restorable AKS outbound-type/UDR configuration preserving pod routes. Feature currently `NotRegistered`; do not change it. If that changes to `Registered`, pause for Jose’s decision before gateway creation.

Microsoft Learn: [App Gateway UDR support](https://learn.microsoft.com/azure/application-gateway/configuration-infrastructure) · [Network isolation opt-in](https://learn.microsoft.com/azure/application-gateway/application-gateway-private-deployment) · [Kubenet/custom route tables](https://learn.microsoft.com/azure/aks/configure-kubenet) · [AGIC support](https://learn.microsoft.com/azure/application-gateway/ingress-controller-overview) · [AKS system-pool SKU restrictions](https://learn.microsoft.com/azure/aks/quotas-skus-regions) · [Service tags in UDRs](https://learn.microsoft.com/azure/virtual-network/service-tags-overview).

## Observed summary

Deployed as one D2as_v5 AKS node, Standard_v2 gateway and B2ts_v2 NVA. Literal `0/0 → NVA` was rejected (ApplicationGatewaySubnetUserDefinedRouteNotAllowed); split `0/1`+`128/1` routes were accepted and made backend health `Unknown`; adding `GatewayManager → Internet` returned it to `Healthy` (unsupported, observed only). Treatment retained; no cleanup run. Details in [README.md](README.md).
