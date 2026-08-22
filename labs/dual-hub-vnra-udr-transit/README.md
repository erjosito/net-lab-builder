<!-- Blog post: [Managed VNRA Multi-Region UDR Transit: The Silent Peering Trap](https://github.com/erjosito/azure-networking-blog/blob/main/dual-hub-vnra-udr-transit/README.md) -->
<!-- Planned sections: VNRA vs VM NVA comparison table; E1 cross-hub UDR chaining (initial failure + root cause + fix); 5-IP reservation discovery; observability gaps; effective-route API gap (E2); Monitor metrics without diagnostic config (E3); allowVirtualNetworkAccess=false silent-drop lesson; lessons for hub-spoke designs. -->

# Lab: dual-hub-vnra-udr-transit

> **Lab status: CLEANED UP** -- Resource group `rg-dual-hub-vnra-udr-transit` deleted 2026-08-20 (~7 min 54 sec). All 22 resources removed. See `show-output/cleanup/cleanup-evidence.md`.

## Designs Studied

### Design 1: Dual-hub VNRA east-west transit via UDR chain -- PASS (after peering correction)

**Status:** ✅ Recommended (with peering flag caveat)
**Verdict:** Cross-VNRA UDR chaining across globally peered hubs works once all peerings have `allowVirtualNetworkAccess=true`.

**What it is:** Two hub VNets globally peered, one Azure managed `Microsoft.Network/virtualNetworkAppliances` (50 Gbps) per hub, four route tables chaining spoke->VNRA1->VNRA2->spoke for cross-region east-west transit. Managed VNRA is hardware-based (no OS, TTL-invisible) unlike VM NVA.

**Evidence:**
- `show-output/validation/retry-20260819T185118+0200/12-after-fix-test1-to-test2.json` -- E1 PASS (10/10, 0% loss, avg 33 ms)
- `show-output/validation/retry-20260819T185118+0200/13-after-fix-test2-to-test1.json` -- E1 PASS (10/10, 0% loss, avg 31 ms)
- `show-output/validation/retry-20260819T185118+0200/11-peering-access-verified.json` -- all 6 peerings corrected
- `validation.md` -- full validation report

**Why this verdict:** After setting `allowVirtualNetworkAccess=true` on all six peering legs, both test VMs achieved 0% loss. Tracepath shows one visible hop to the remote VM (managed VNRA is TTL-invisible), confirming hardware forwarding. The initial 100% loss was caused entirely by `allowVirtualNetworkAccess=false` on all six peerings -- a silent misconfiguration that presents as Connected/FullyInSync but drops all data-plane traffic.

**Use this design when:** Cross-region east-west transit is needed without deploying VM-based NVA; high-throughput (up to 50 Gbps) transparent forwarding is required; TTL-invisibility (no intermediate hop in tracepath) is acceptable or desirable.

**Avoid this design when:** You need direct effective-route visibility on the VNRA subnet (no API exists -- E2 confirmed gap). Always verify `allowVirtualNetworkAccess=true` on every peering leg before testing.

---

## What This Lab Proves

### E1 -- Cross-VNRA UDR Chaining: PASS (after peering correction)

The dual-hub VNRA transit topology **achieved spoke-to-spoke connectivity after correcting the peering flags.** 0% packet loss both directions, 10/10 packets, avg ~33 ms east-west.

**Initial failure and root cause:** The first validation run (and unchanged retry) showed 100% loss. All eight Azure Monitor metrics were zero on both VNRAs. Root cause: all six VNet peering objects had `allowVirtualNetworkAccess=false` despite Connected/FullyInSync and allowForwardedTraffic=true. This flag silently drops all data-plane traffic across the peering regardless of peering state.

**Fix:** Coordinator set `allowVirtualNetworkAccess=true` on all six peerings, retaining `allowForwardedTraffic=true`. All six verified Connected/FullyInSync with both flags true.

**Control plane confirmed correct throughout:** Spoke VM NIC effective routes showed UDRs Active; Network Watcher next-hop confirmed Azure SDN steers spoke traffic to VNRA; hub VNRA route tables configured correctly. The failure was entirely the peering flag misconfiguration.

**TTL-invisibility confirmed:** Tracepath shows one visible hop directly to the remote VM in each direction. Managed VNRA hardware forwards packets without decrementing TTL -- the VNRA hops (10.1.0.4, 10.2.0.4) do not appear in the path.

### E2 -- Subnet-Scope Effective Route API: CONFIRMED GAP

POST to `VirtualNetworkApplianceSubnet/effectiveRouteTable` and `VirtualNetworkApplianceSubnet/listEffectiveRoutes` both return **HTTP 404** from the regional ARM network backend. There is no programmatic way to inspect effective routes on the VNRA subnet -- not via CLI, not via REST.

### E3 -- Azure Monitor Metrics Without Diagnostic Settings: PARTIAL

Azure Monitor returned **HTTP 200** and **8 metric definitions** (`BytesSent`, `BytesReceived`, `PacketsSent`, `PacketsReceived`, `CurrentTotalFlowsIn/Out`, `CreationRateMaxTotalFlowsIn/Out`) without any diagnostic settings configured. Pre-fix values were all zero (explained by E1 failure -- no traffic reached either VNRA). **Post-fix metrics were not re-queried**, so whether metrics reflect active forwarded traffic is unconfirmed. E3 requires a dedicated post-fix metric query to fully evaluate.

---

## Unexpected Findings

- **`allowVirtualNetworkAccess=false` is a silent killer** -- Peerings show Connected/FullyInSync with allowForwardedTraffic=true yet drop all data-plane traffic. Verify this flag on every peering leg before testing any hub-spoke UDR scenario.
- **VNRA reserves 5 IPs per instance** -- primary + 4 secondary (e.g., 10.1.0.4-10.1.0.8). Undocumented in GA docs. A /28 subnet is risky; /24 is safe.
- **Network Watcher cannot proxy VNRA forwarding context** -- source-ip must match NIC; no spoke NIC proxy for hub VNRA subnet perspective.
- **Auto-created NSGs** on VNRA subnets (Azure-managed, 0 custom rules) and on spoke subnets via `az network nic create` (preventable with `--network-security-group ""`).
- **traceroute not available** on Ubuntu 22.04 minimal -- use `tracepath` instead.

---

## Architecture

```
spoke1-vnet (10.10.0.0/16)          spoke2-vnet (10.20.0.0/16)
  test1-vm (10.10.1.4)                test2-vm (10.20.1.4)
  rt-spoke1: 10.20/16 -> VNRA1        rt-spoke2: 10.10/16 -> VNRA2
         |                                    |
  hub1-vnet (10.1.0.0/16)    <=GLOBAL=>  hub2-vnet (10.2.0.0/16)
  VNRA1 (10.1.0.4, 50 Gbps)            VNRA2 (10.2.0.4, 50 Gbps)
  rt-hub1-vnra: 10.20/16 -> VNRA2      rt-hub2-vnra: 10.10/16 -> VNRA1
```

All peerings require `allowVirtualNetworkAccess=true` + `allowForwardedTraffic=true` on every leg.

---

## Diagrams (Oracle)

Visual documentation under `diagrams/`:

| Diagram | Purpose |
|---------|---------|
| [01-topology-overview.md](diagrams/01-topology-overview.md) | Network topology with regions, VNets, subnets, VMs, and managed VNRAs |
| [02-udr-data-path.md](diagrams/02-udr-data-path.md) | Forward and return packet flows through UDR chain |
| [03-observability-evidence.md](diagrams/03-observability-evidence.md) | Validation probes (S1-S5), observable surfaces, proof vectors |
| [04-cleanup-boundary.md](diagrams/04-cleanup-boundary.md) | Resource dependency tree and deletion sequence |

---

## Evidence

All evidence under `show-output/`:
- `deployment/` -- Tank's deployment artifacts (deploy-run.log, resource outputs)
- `validation/` -- Niobe's validation artifacts (S1-S5 evidence, resource state)
- `validation/retry-20260819T185118+0200/` -- Root cause investigation + fix + post-fix tests (files 01-13)

Key validation files:
- `validation/retry-20260819T185118+0200/12-after-fix-test1-to-test2.json` -- E1 PASS (10/10, 0% loss)
- `validation/retry-20260819T185118+0200/13-after-fix-test2-to-test1.json` -- E1 PASS (10/10, 0% loss)
- `validation/retry-20260819T185118+0200/09-vnra1-metrics.json` -- Pre-fix zero metrics (VNRA1)
- `validation/retry-20260819T185118+0200/09-vnra2-metrics.json` -- Pre-fix zero metrics (VNRA2)
- `validation/retry-20260819T185118+0200/10-peering-access-correction.json` -- Post-fix peering state
- `validation/retry-20260819T185118+0200/11-peering-access-verified.json` -- Verification summary (all 6)
- `validation/s2-test1-to-test2.json` -- Initial E1 failure (100% loss)
- `validation/s3-test1-effective-routes.json` -- Spoke1 effective routes (UDR Active)
- `validation/s5-a1-subnet-effectiveRouteTable.txt` -- E2 evidence (404 body)
- `validation/s5-c-vnra1-metric-definitions.json` -- E3 evidence (8 metrics available)
- `validation/s5-vnra1-get.json` -- VNRA1 GET (5 IPs, Succeeded)
- `validation.md` -- Full validation report

---

## Status

| | |
|---|---|
| Deployed | 2026-08-19 |
| Validated | 2026-08-19 |
| E1 verdict | PASS -- 0% loss after peering correction |
| E2 verdict | CONFIRMED GAP -- 404 from regional backend |
| E3 verdict | PARTIAL -- pre-fix zeros explained; post-fix not re-queried |
| Cleanup authorized | NO -- pending Jose approval |
| Next action | Jose: authorize teardown |

---

## Related Files

- `manifest.md` -- Lab card and scenario definitions
- `design.md` -- Network design (Trinity)
- `deploy-log.md` -- Deployment run log (Tank)
- `lessons-learned.md` -- Lessons and findings (L1-L11)
- `validation.md` -- Full validation report (stage 1-v3 final)
- `diagrams/` -- Topology and data-flow diagrams (Oracle)
- `deploy.ps1` -- Deployment script

