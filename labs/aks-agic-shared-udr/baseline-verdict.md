# Read-only baseline verdict

**Verdict: PASS — baseline state verified.**  
**Captured:** 2026-10-09 12:32–12:39 UTC  
**Correlation:** `aks-agic-baseline-20261009T1228Z`  
**Evidence:** [`show-output/baseline-20261009T1228Z/`](show-output/baseline-20261009T1228Z/)

## Decisive evidence

- `EnableApplicationGatewayNetworkIsolation` is `NotRegistered`.
- `aks1` is `Succeeded` / `Running`, Free tier, Kubernetes 1.35, kubenet, `loadBalancer` outbound, pod CIDR `10.244.0.0/16`, service CIDR `10.0.0.0/16`. Its one `Standard_D2as_v5` system node is Ready at `10.21.1.4`; the workload pod `10.244.0.14` is Running.
- AKS and AGIC identities are attached. Direct principal-to-role checks matched the expected AKS Network Contributor grants on `snet-aks` and `rt-shared`, plus AGIC Contributor on `agw1`, Network Contributor on `vnet-spoke`, and Reader on the resource group.
- `snet-aks` and `snet-appgw` both reference `rt-shared`. The table is `Succeeded`, with `0.0.0.0/0 → Internet` and the live pod route `10.244.0.0/24 → VirtualAppliance 10.21.1.4`.
- `agw1` is `Succeeded` / `Running` (`Standard_v2`). Both backend settings report pod `10.244.0.14` Healthy with probe HTTP 200.
- Metrics were returned for 12:21–12:36 UTC. Healthy-host samples reached 1 and unhealthy-host samples 0 from 12:26 onward. `TotalRequests` has explicit zero-valued intervals and non-zero samples; missing `average` fields are treated as absent samples, not zeros.
- Read-only NVA inspection reports NIC forwarding enabled, Linux `ip_forward=1`, cloud-init `done`, SNAT `10.21.0.0/16` via `eth0`, and FORWARD policy `ACCEPT`. The bounded request from `nva1` to private frontend `10.21.2.250` returned HTTP 200.

## Scope and restore state

No Azure, route, Kubernetes, or guest configuration was changed. The verified default route remains Internet; no restore was needed. The private frontend request traverses the peering route and does **not** prove NVA transit, Internet forwarding, or SNAT in the data path. Public-client ingress was not independently recaptured in this checkpoint.

This PASS is the starting-baseline result only. It does not validate either forced-tunnel scenario or the `GatewayManager` exception. Any later test needs its own lease: first `0.0.0.0/0 → NVA` only, and proceed to the GatewayManager route only if both the NVA-source-IP egress check and the backend-health control-plane failure are established.
