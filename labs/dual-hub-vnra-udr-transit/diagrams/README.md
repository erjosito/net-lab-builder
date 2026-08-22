# Diagrams: dual-hub-vnra-udr-transit

Complete visual documentation of the dual-hub Azure Virtual Network Routing Appliance (VNRA) + User-Defined Routes (UDR) lab topology and data flows.

## Quick Links

| Diagram | Purpose | Format |
|---------|---------|--------|
| [01-topology-overview.md](01-topology-overview.md) | Network topology with regions, VNets, subnets, VMs, and managed VNRAs | Mermaid flowchart |
| [02-udr-data-path.md](02-udr-data-path.md) | Forward and return packet flows through UDR chain; empirical gates [E1] | Mermaid sequence (LR) |
| [03-observability-evidence.md](03-observability-evidence.md) | Validation probes (S1-S5), observable surfaces, and proof vectors | Mermaid DAG + tables |
| [04-cleanup-boundary.md](04-cleanup-boundary.md) | Resource dependency tree and deletion sequence; cost optimization notes | Mermaid DAG + phases |

## Key Distinctions

### Managed VNRA vs. VM NVA

| Aspect | Managed VNRA (🖥️ Green) | VM NVA (🖱️ Blue) |
|--------|----------------------|---------|
| Resource Type | `Microsoft.Network/virtualNetworkAppliances` | `Microsoft.Compute/virtualMachines` |
| NIC | None (no user NIC) | User NIC with `enableIPForwarding=true` |
| OS | None (managed hardware) | Ubuntu 22.04 + cloud-init |
| Forwarding | Hardware-based (invisible to TTL/traceroute) | Software-based (visible as hop) |
| API Surface | VNRA GET returns IP + state only | Full VM/NIC APIs |
| Effective Routes | No documented API (**[E2] empirical gap**) | `az network nic show-effective-route-table` |

### Empirical Gates

- **[E1]**: Cross-VNRA UDR chaining (rt-hub1-vnra and rt-hub2-vnra routes)
  - Expected: Ping 0% loss, no VNRA IP hops in traceroute (hardware forwarding invisible)
  - Status: Unproven at lab creation time; validated in S2

- **[E2]**: VNRA subnet effective-route API
  - Expected: 404 or no documented endpoint
  - Status: Investigation required (Production gap documented in design.md)

## Validation Stages (S1-S5)

```
S1: Baseline non-transitivity (no route tables)
  └─> Expected: Ping FAIL

S2: VNRA transit proof (E1 chaining)
  └─> Expected: Ping PASS, no VNRA hops in traceroute

S3: Spoke UDR effective routes (test VM NICs)
  └─> Expected: rt-spoke1 and rt-spoke2 entries visible via CLI

S4: Hub route table config (E1 VNRA chaining)
  └─> Expected: rt-hub1-vnra and rt-hub2-vnra routes listed via CLI

S5: VNRA subnet effective routes (E2 empirical investigation)
  └─> Expected: API 404 or no documented endpoint
```

## Observable Surfaces

| Surface | Tool | Scope | Status |
|---------|------|-------|--------|
| Spoke UDR entries | `az network nic show-effective-route-table` | test1/test2 VM NIC | ✅ Observable |
| Hub route tables | `az network route-table route list` | rt-hub1/2-vnra config | ✅ Observable |
| VNRA resource state | `az rest GET .../virtualNetworkAppliances/vnra1` | VNRA IP + provisioningState | ✅ Observable |
| VNRA effective routes | No documented API | VNRA subnet | ❌ Gap ([E2]) |
| Cross-VNRA chaining | ICMP ping + traceroute absence | Forward/return path | ✅ Proof via [E1] |

## Notes for Validators (Niobe)

1. **S1 window missed in deployment**: To validate baseline non-transitivity, temporarily detach rt-spoke1 and rt-spoke2, run ping tests, then re-attach.

2. **Auto-created NSGs**: 4 NSGs present with only Azure default rules (VirtualNetwork tag traffic allowed). Should not block testing.

3. **Hardware forwarding proof**: Traceroute showing **no hop** at VNRA IPs (10.1.0.4 or 10.2.0.4) definitively proves managed VNRA vs. VM NVA.

4. **Peering constraint**: All three peerings require `allowForwardedTraffic=true`; missing on any leg = silent drop.

