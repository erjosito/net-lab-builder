> Diagrams: [Topology](diagrams/01-topology.drawio) | [BGP](diagrams/02-bgp-control-plane.mmd) | [Routes](diagrams/03-route-propagation.mmd) | [Cleanup](diagrams/04-cleanup-chain.mmd)

# expressroute-megaport-bgp — validation results

Source checklist: `manifest.md` §6 pass/fail criteria plus §9 validation plan. Evidence is saved under `show-output/`; every file starts with the exact command used.

## Summary

| Area | Result | Notes |
|---|---|---|
| Azure resource inventory | PASS | Core Azure resources are present in the target resource group. |
| Provider gate | PASS | Circuit is `Enabled` and provider state is `Provisioned`; route capture was performed after this gate. |
| Megaport resource state | PASS | MCR and both VXCs are `LIVE`; both VLL resources report `up: 1`. |
| VLAN finding | PASS / observation | Primary and secondary VXCs both report VLAN `100`; this confirms Tank's summary and differs from the preferred `100/200` plan. |
| Azure route propagation | PASS | ER gateway learned routes and VM NIC effective routes include `172.31.100.0/24` via `VirtualNetworkGateway`. |
| ER circuit route-table command | FAIL / anomaly | Both primary and secondary `az network express-route list-route-tables` calls returned `Gateway does not have any Bgp sessions.` |
| MCR route/community evidence | INCONCLUSIVE | Current Megaport GET endpoints did not expose MCR BGP route/community detail; generic VXC resources are the fallback evidence. |
| VM ping/effective NSG | BLOCKED | VM deallocated before these captures; no start/action was taken because this validation is read-only. |

## Checklist

| # | Checklist item | Result | Evidence |
|---:|---|---|---|
| 1 | Circuit is provider-provisioned. | PASS | `show-output/02-er-circuit-show.txt` lines 27, 80 show `Enabled` / `Provisioned`. |
| 2 | BGP sessions are established on both VXC paths. | PASS with caveat | `show-output/06-er-arp-primary.txt`, `07-er-arp-secondary.txt` show ARP on both ER paths; `09-er-gateway-bgp-peer-status.txt` shows two `Connected` gateway BGP sessions with two routes each; `16`/`17` show VXC `LIVE` and `up: 1`. The generic VXC endpoint does not expose an explicit BGP session-status field. |
| 3 | Azure route tables contain the MCR-advertised route. | FAIL / anomaly | `show-output/04-er-route-table-primary.txt`, `05-er-route-table-secondary.txt`, `04a-*`, `05a-*` all return `Gateway does not have any Bgp sessions.` |
| 4 | MCR route evidence contains Azure VNet route `10.31.0.0/16`. | INCONCLUSIVE | `show-output/18-megaport-mcr-looking-glass-bgp-routes.txt` returns no endpoint; `15`/`16`/`17` do not expose route tables. |
| 5 | VM effective route table points MCR prefixes to the virtual network gateway. | PASS | `show-output/13-vm-effective-routes.txt` shows `172.31.100.0/24` and `172.31.101.1/32` with `nextHopType: VirtualNetworkGateway`. |
| 6 | Azure-originated route communities are visible on the MCR side. | INCONCLUSIVE | MCR route-table/community endpoint unavailable (`18`); VXC/MCR product resources do not expose communities. |
| 7 | MCR-originated prefix is accepted by Azure. | PASS | `show-output/10-er-gateway-learned-routes.txt` and `13-vm-effective-routes.txt` show `172.31.100.0/24`. |
| 8 | Record whether Azure preserves/exposes/ignores/strips MCR-originated community. | PASS / documented as not exposed | Azure CLI route outputs expose the prefix but no community field; no evidence of inbound community metadata was visible in Azure outputs. |
| 9 | VM effective routes include `172.31.100.0/24` with next hop `VirtualNetworkGateway`. | PASS | `show-output/13-vm-effective-routes.txt`. |
| 10 | ExpressRoute route table shows MCR-advertised prefixes. | FAIL / anomaly | `show-output/04-er-route-table-primary.txt` and `05-er-route-table-secondary.txt`. |
| 11 | VNet metadata shows custom `VirtualNetworkCommunity = 12076:20031`. | FAIL / not present | `show-output/21-vnet-show-bgp-community.txt` shows only `regionalCommunity: 12076:51013`; no `virtualNetworkCommunity` field was returned. |
| 12 | MCR sees Azure VNet prefix `10.31.0.0/16`. | INCONCLUSIVE | MCR looking-glass endpoint unavailable; product resources do not include BGP route tables. |
| 13 | MCR route detail shows Azure custom and regional communities. | INCONCLUSIVE | Same as #12. |
| 14 | MCR advertised prefix `172.31.100.0/24` is tagged with `65031:100` before handoff. | INCONCLUSIVE | No route-policy or route-table endpoint exposed this field in captured API output. |
| 15 | Kernel route lookup for `172.31.100.0/24` exits via the Azure gateway path. | PARTIAL | `show-output/19-vm-ip-route.txt` shows the VM's OS table/default route, but Azure effective route evidence (`13`) is authoritative for VNet gateway propagation. |
| 16 | If MCR-side loopback/test endpoint is available, ping/traceroute reaches it. | BLOCKED / not applicable | No pingable on-prem target was available, and the VM deallocated before ping capture (`20`, `22`). |
| 17 | If no pingable endpoint exists, route convergence is the pass condition, not ICMP. | PASS | Route convergence is shown in `10` and `13`; ICMP is not used as the success signal. |

## Mandatory command inventory

All required command captures exist. `11a`/`11b` preserve the requested advertised-route peer commands for `169.254.194.42` and `.46`; Azure returned `Couldn't find BGP peering session` for those peer arguments. `11c` tries the gateway peer observed in `09` and also returns no advertised-route session. `20` records the read-only block caused by VM deallocation.
