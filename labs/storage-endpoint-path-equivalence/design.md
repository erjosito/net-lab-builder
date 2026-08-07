# storage-endpoint-path-equivalence — Network Design
**Author:** Trinity (Azure Network SME) · **Date:** 2026-08-05 · **Status:** Historical Storage design; superseded by the approved Translator plan in `redesign.md`

> The live deployment no longer uses the Storage experiment described below. Niobe must use `redesign.md` and `deployment.md`.

## 1. Question and hypothesis

Does Azure Storage traffic to the ordinary public Blob FQDN follow the same **observable** data-plane path when a `Microsoft.Storage` service endpoint is enabled, and how does either public case differ from Private Endpoint traffic?

This is a falsifiable comparison, not an assumed answer. “Path” here means customer-observable L3 destination, Azure effective next-hop type, service-observed source identity, authorization result, and flow/service telemetry. It does **not** mean Microsoft’s physical routers, links, or internal underlay.

References: vault [[Services/Private-Link]], [[Topics/UDR-and-Effective-Routes]], [[Topics/VNet-Flow-Logs]], [[Book/Ch09-DNS-and-PaaS]]. Current Microsoft Learn: [service endpoints](https://learn.microsoft.com/azure/virtual-network/virtual-network-service-endpoints-overview), [Storage network rules](https://learn.microsoft.com/azure/storage/common/storage-network-security), [Storage private endpoints](https://learn.microsoft.com/azure/storage/common/storage-private-endpoints), [service endpoint policies](https://learn.microsoft.com/azure/virtual-network/virtual-network-service-endpoint-policies-overview), [VNet flow logs](https://learn.microsoft.com/azure/network-watcher/vnet-flow-logs-overview), and [Blob log schema](https://learn.microsoft.com/azure/storage/blobs/monitor-blob-storage-reference).

## 2. Minimal controlled topology

One VM, subnet, target account, FQDN, blob, identity, and request method are reused sequentially. Connections and DNS caches are cleared between runs; each request carries a unique `x-ms-client-request-id`.

| Resource | Exact setting |
|---|---|
| Region | `swedencentral` |
| VNet | `vnet-endpoint-path`, `10.61.0.0/16`, Azure-provided DNS |
| Client subnet | `snet-client`, `10.61.1.0/24`; VM private IP dynamically allocated and recorded |
| PE subnet | `snet-private-endpoint`, `10.61.2.0/24`; PE network policies disabled for baseline |
| Private endpoint | Target Blob subresource, static `10.61.2.4` |
| VM | Ubuntu 22.04, `Standard_B2ts_v2`, 30-GiB Standard SSD, no PIP |
| Public egress | NAT Gateway on `snet-client`, one Standard static IPv4; record but never publish its value |
| Storage | Target + decoy GPv2 `Standard_LRS`, same region; one private container/blob in each |
| DNS | Zone `privatelink.blob.core.windows.net`; target A record → `10.61.2.4`; VNet link is the S4 switch |
| Telemetry | VNet flow log to same-region Standard_LRS account; target/decoy Blob read/write/delete logs to Log Analytics |

No firewall, NVA, gateway, peering, ExpressRoute, Megaport, Bastion, or public management port. Phase 0 already selected `Standard_B2ts_v2`; no further preflight or deployment is authorized.

## 3. Identity and authorization

- Enable a system-assigned identity on the VM.
- Assign **Storage Blob Data Reader** at each test account scope. Use OAuth through IMDS; never use account keys or SAS.
- Use the same blob `GET` request shape for all positive tests. Client request IDs use `sepath-S<n>-<UTC>` and are the join key for packet capture and `StorageBlobLogs`.
- RBAC is held constant. A 403 is classified using `StatusText`, `AuthenticationType`, and authorization fields so network-policy denial is not mistaken for RBAC denial.

## 4. Routing, DNS, endpoint, and firewall state

### 4.1 Routes

- No route table/UDR is associated with either subnet.
- S1 public traffic uses the public DNS answer and the ordinary effective route selected for that public IP.
- Enabling `Microsoft.Storage` adds more-specific Storage prefixes with next hop `VirtualNetworkServiceEndpoint`; Microsoft documents that these routes override matching UDR/BGP routes.
- Private endpoint traffic targets `10.61.2.4`; the effective route must be VNet-local, not `VirtualNetworkServiceEndpoint`.
- `ip route get` is collected only as guest-OS corroboration. Azure SDN effective routes are authoritative for next-hop classification.

### 4.2 DNS

- S1–S3: the private zone exists but is **not linked** to the VNet. Resolve `<target>.blob.core.windows.net` and its complete CNAME chain immediately before each run. The terminal A/AAAA result must be public.
- Select one S1 IPv4 answer as `PUBLIC_IP_CONTROL`. Pin S1 and S2 target requests to that same address with `curl --resolve` while preserving the unchanged FQDN/SNI. Before S2, confirm the address is still in the live DNS answer set; if not, invalidate the pair and restart at S1 with a new address.
- S4–S5 private run: link the zone to the VNet. The unchanged public FQDN must CNAME to the `privatelink` name and terminate at `10.61.2.4`.
- Never call the `privatelink` hostname directly. Never hard-code a public Storage IP; capture it per run and honor TTL.
- Flush `systemd-resolved`, close keep-alive sessions, and use a fresh process/TCP connection after every transition.

### 4.3 Storage public endpoint rules

| Stage | Target | Decoy | Purpose |
|---|---|---|---|
| Baseline/S1 | `publicNetworkAccess=Enabled`, `defaultAction=Allow` | Same | Public control without relying on same-region IP firewall rules |
| Pre-S2 | Pre-stage target subnet VNet rule with `ignoreMissingVnetServiceEndpoint=true`; default remains Allow | Allow | Rule is inert while default is Allow; avoids changing endpoint and rule in the measured S2 transition |
| S2 onward | Enable service endpoint; then set target `defaultAction=Deny` with its VNet rule retained | Decoy remains Allow | Target proves VNet identity; decoy remains usable for endpoint-policy negative control |
| S5 | Target `publicNetworkAccess=Disabled`, `defaultAction=Deny` | Unchanged | Public exposure negative control |

Azure Storage IP rules cannot be used as this same-region public control; Microsoft documents that same-region requests cannot be restricted by Storage public IP rules. NAT still supplies a stable externally observable egress identity for S1.

### 4.4 Service endpoint and policy

- S1: `snet-client.serviceEndpoints=[]`; no endpoint policy association.
- S2: add only `Microsoft.Storage` to `snet-client`. Wait until provisioning succeeds and old TCP sessions are gone.
- S3: associate one service endpoint policy whose only resource is the target storage account ARM resource ID. The service endpoint remains enabled.
- S4: leave service endpoint and policy attached; link private DNS. This deliberately changes only name resolution/destination. Endpoint policy applies to Storage traffic over service endpoints, not the PE’s VNet-local flow.

## 5. NSG specification

Attach `nsg-client` to `snet-client` after bootstrap tooling (`curl`, `jq`, `dnsutils`, `tcpdump`) is installed. No NIC NSG. No custom inbound allow; VM has no PIP and uses Run Command.

| Pri | Direction | Action | Protocol | Source | Destination | Port | Why |
|---:|---|---|---|---|---|---:|---|
| 100 | Out | Allow | UDP/TCP | VirtualNetwork | `AzurePlatformDNS` | 53 | Azure DNS |
| 110 | Out | Allow | TCP | VirtualNetwork | `AzurePlatformIMDS` | 80 | Managed-identity token |
| 120 | Out | Allow | TCP | VirtualNetwork | `Storage.SwedenCentral` | 443 | Public/SE Storage flows; stable rule attribution |
| 125 | Out | Allow | TCP | `10.61.1.0/24` | `10.61.2.4/32` | 443 | Private endpoint flow |
| 130 | Out | Allow | TCP | VirtualNetwork | `AzureCloud.SwedenCentral` | 443 | VM agent/Run Command control channel |
| 4000 | Out | Deny | Any | Any | Any | Any | Prevent unrelated egress |

Before S1, capture effective NSGs and prove rules 120/125 precede rule 130. If the regional service tags are unavailable in the selected API, use `Storage`/`AzureCloud` and document that forced platform substitution.

## 6. Transition order

1. Deploy topology with Storage public access enabled; PE and private zone may exist, but leave the zone unlinked. Bootstrap VM, then lock NSG.
2. Enable diagnostics and wait for a known probe request to appear in `StorageBlobLogs`.
3. Confirm no service endpoint, no endpoint policy, public DNS, and no stale sockets; run S1.
4. Pre-stage target VNet rule while `defaultAction=Allow`; run a quick unchanged-control request. Then enable only `Microsoft.Storage`, wait for provisioning/connection reset, and run S2.
5. Set target `defaultAction=Deny`; verify target still succeeds through its VNet rule. Associate the target-only endpoint policy and run S3 against target and decoy.
6. Link private DNS, flush caches, and run S4 using the unchanged target FQDN.
7. Record the current public IP before DNS linkage (or resolve with an unlinked external resolver). Set target public network access Disabled; run S5 forced-public and private-DNS probes.

If any transition changes an unlisted property, stop: the paired comparison is invalid until state is restored and recaptured.

## 7. Common evidence harness

For S1/S2 target requests use the pinned harness below. For S3 substitute each account/FQDN and its current public IP. For S4 and S5's normal-private request, remove `--resolve` so private DNS controls the destination.

```bash
RUN="sepath-S2-$(date -u +%Y%m%dT%H%M%SZ)"
FQDN="<TARGET>.blob.core.windows.net"
OUT="$HOME/sepath-output"; mkdir -p "$OUT"
dig +noall +answer "$FQDN"
getent ahostsv4 "$FQDN"
sudo tcpdump -ni eth0 "tcp port 443" -w "${OUT}/${RUN}.pcap" &
PCAP_PID=$!
TOKEN=$(curl -fsS -H Metadata:true \
  'http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fstorage.azure.com%2F' |
  jq -r .access_token)
curl --http1.1 --no-keepalive -sS -D "${OUT}/${RUN}.headers" \
  -H "Authorization: Bearer $TOKEN" -H "x-ms-version: 2023-11-03" \
  -H "x-ms-date: $(LC_ALL=C date -u '+%a, %d %b %Y %H:%M:%S GMT')" \
  -H "x-ms-client-request-id: $RUN" \
  --resolve "${FQDN}:443:${PUBLIC_IP_CONTROL}" \
  "https://${FQDN}/<CONTAINER>/<BLOB>" -o "${OUT}/${RUN}.body"
RC=$?; sudo kill "$PCAP_PID"; wait "$PCAP_PID" 2>/dev/null; exit "$RC"
```

Use `curl --resolve "${FQDN}:443:<PUBLIC_IP>"` only for S5’s forced-public probe; this preserves TLS SNI/Host while bypassing private DNS. Store outputs under the eventual lab `raw-output/`; sanitize IDs/tokens.

Control-plane evidence per state:

```powershell
az network nic show-effective-route-table -g <RG> -n <NIC> -o json
az network watcher show-next-hop -g <RG> --vm <VM> --nic <NIC> \
  --source-ip <VM_PRIVATE_IP> --dest-ip <PUBLIC_IP_CONTROL> -o json
az network nic list-effective-nsg -g <RG> -n <NIC> -o json
az network vnet subnet show -g <RG> --vnet-name vnet-endpoint-path -n snet-client -o json
az storage account show -g <RG> -n <TARGET> --query "{pna:publicNetworkAccess,default:networkRuleSet.defaultAction,vnet:networkRuleSet.virtualNetworkRules}" -o json
az network private-endpoint show -g <RG> -n <PE> -o json
```

Log query (allow ingestion delay; correlate by request ID and narrow UTC window):

```kusto
StorageBlobLogs
| where TimeGenerated between (datetime(<START>) .. datetime(<END>))
| where ClientRequestId startswith "sepath-"
| project TimeGenerated, ClientRequestId, Uri, CallerIpAddress,
          StatusCode, StatusText, AuthenticationType, OperationName
| order by TimeGenerated asc
```

## 8. Executable scenarios and gates

| Scenario | Changed variable | Required evidence | PASS | FAIL |
|---|---|---|---|---|
| **S1 Public control** | None | DNS/CNAME, PCAP destination, effective route/next-hop query, external egress IP, Storage log | Pinned `PUBLIC_IP_CONTROL` is public; next hop is not `VirtualNetworkServiceEndpoint`; GET succeeds; `CallerIpAddress` is not `10.61.1.x` | Private DNS/IP, SE next hop, request failure, or service sees client private IP |
| **S2 Service endpoint paired run** | Enable `Microsoft.Storage` only | Same evidence plus subnet endpoint state | Same FQDN and pinned public IP as S1; matching route becomes `VirtualNetworkServiceEndpoint`; GET succeeds; service sees VM private IP | DNS/IP pair changed, route type unchanged/missing, or source identity remains public |
| **S3 Endpoint-policy authorization** | Attach target-only policy | Target+decoy DNS/PCAP/routes/logs and policy state | Both retain public destinations and SE next hop; target succeeds; decoy is denied | Decoy succeeds, target fails, or either flow leaves SE classification |
| **S4 Private endpoint** | Link private DNS only | CNAME/A, PCAP, effective route, PE connection, Storage log | Same FQDN resolves/captures `10.61.2.4`; next hop is VNet-local; PE connected; GET succeeds | Public destination, SE next hop for `10.61.2.4`, disconnected PE, or failed GET |
| **S5 Public exposure negative control** | Disable target public network access | Forced-public and normal-private requests with distinct IDs | Forced-public request fails and logs/headers show denial; normal FQDN still resolves `10.61.2.4` and succeeds | Public succeeds or private fails |

For each scenario also inspect VNet flow tuples for source/destination/443/direction/state/rule. Flow logs are corroborative: they are L4, delayed, and traffic cannot be captured at the PE itself; Microsoft documents capturing PE traffic at the source VM, where destination is the PE IP.

## 9. Interpretation

Strongest deciding bundle:

1. S1 and S2 use the same public FQDN and pinned public destination IP.
2. S2 changes effective next hop to `VirtualNetworkServiceEndpoint` and Storage sees the VM private IP.
3. S4 changes DNS and packet destination to the PE private IP and uses a VNet-local route.

Therefore strict **observable path equivalence** is falsified if those deltas occur. Similar latency, the absence/presence of traceroute hops, or “Microsoft backbone” wording cannot establish a shared or different physical path. Azure SDN/PaaS can suppress TTL-expired replies and Microsoft does not expose the physical underlay. Do not use traceroute as proof.

## 10. Resiliency analysis and failure modes

| Failure | Blast radius / symptom | Expected recovery | Operator action |
|---|---|---|---|
| NAT Gateway/PIP | S1 public control loses egress; SE/PE may remain reachable | Minutes after platform recovery | Pause; do not compare runs across failure |
| Azure DNS/private-zone link | S4 resolves public or fails | DNS TTL/propagation | Verify link/A record; flush cache; rerun S4 only |
| Service endpoint transition | Existing TCP reset; temporary Storage interruption | Usually seconds/minutes | Expected by Learn; wait, close sockets, recapture state |
| Endpoint policy omission | Decoy unexpectedly succeeds | Immediate after policy correction | Verify association/resource ID; rerun S3 |
| PE NIC/connection | S4/S5 private fails; S1–S3 unaffected | Platform or manual approval recovery | Verify connection/DNS/IP; do not fall back silently |
| Log/flow ingestion delay | Data-plane works but evidence incomplete | Minutes | Extend query window; never infer failure from absent telemetry alone |
| Single VM failure | All active tests stop; no comparison result | VM restart/redeploy minutes | Reuse same NIC/subnet where possible; repeat every scenario after replacement |

This single-VM/single-region shape is intentionally not production-resilient. A production reader should evaluate multi-zone clients, application retry/DNS-cache behavior, multi-region Storage design, PE/DNS failover, telemetry retention, and whether public endpoint fallback is permitted.

Dormant patches (apply only if Jose explicitly approves): **P1** second client VM in the same subnet (+compute cost; reduces host failure only); **P2** second-region client/PE/DNS design (+compute, PE, DNS and storage complexity; tests regional failure, changes the experiment); **P3** Log Analytics export redundancy (+ingestion/storage cost; no data-plane benefit).

## 11. Rollback / cleanup sequence

Rollback a test transition in reverse order:

1. Re-enable target public network access and set `defaultAction=Allow`.
2. Unlink the private DNS zone; flush VM DNS/socket state.
3. Detach the service endpoint policy.
4. Remove the target VNet rule.
5. Remove `Microsoft.Storage` from `snet-client`; wait for provisioning and close sessions.
6. Verify S1 control state before any rerun.

After validation and a separate cleanup approval: remove diagnostic settings/flow log, PE connection/PE, DNS link/zone, endpoint policy, storage accounts, NAT Gateway/PIP, VM/NIC/disk, NSG/VNet, then delete the tagged resource group. Cleanup remains unauthorized.

## 12. Approval gate

**Phase 4 was approved.** ARM resources were deployed, but testing is blocked because subscription automation forces both experiment accounts to disable public network access. See `deployment.md`.
