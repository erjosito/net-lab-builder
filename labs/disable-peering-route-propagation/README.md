# Disable Peering Route Propagation (`disablePeeringRoute`) — Hub-and-Spoke with VPN & NVA

## Status Summary

| Item | Value |
|------|-------|
| **Verdict** | **BLOCKED (Feature Gate) / PASS (Routing Architecture & Workaround Verified)** |
| **Feature Under Test** | Disable peering route propagation (`az network route-table update --disable-peering-route All` / `Microsoft.Network/AllowDisablePeeringRoutes`) |
| **Region** | `swedencentral` |
| **Resource Group** | `rg-disable-peering-routes-lab` (**Active / Retained per user instruction**) |
| **Last Verified State** | Live environment up (`vpngw-hub` `Connected` to `vm-onprem` via StrongSwan IKEv2 + eBGP; `rt-gw` currently configured with the 10-spoke `/16` UDR workaround so stateful NVA traffic passes symmetrically). `Microsoft.Network/AllowDisablePeeringRoutes` remains `Pending` (`approvalType: ApprovalRequired`). |

| Scenario | Description | Verdict | Evidence |
|----------|-------------|---------|----------|
| **S1 — Baseline (`disablePeeringRoute = None`)** | `rt-gw` has only a summarized `10.0.0.0/8 -> 10.0.1.4` UDR; 10 spoke `/16` `VNetPeering` routes override `/8` via LPM and bypass the hub NVA on the forward path. | **PASS** (reproduced asymmetric bypass & stateful NVA failure) | [`s1-nic-vm-hub-probe-routes.txt`](show-output/s1-nic-vm-hub-probe-routes.txt), [`s1-nva-stateless-counters.txt`](show-output/s1-nva-stateless-counters.txt), [`s1-nva-stateful-counters.txt`](show-output/s1-nva-stateful-counters.txt), [`s1-onprem-stateful-test.txt`](show-output/s1-onprem-stateful-test.txt) |
| **S2 — Feature Gate & `/16` UDR Comparison (`rt-gw`)** | Attempted `az network route-table update --disable-peering-route All` on `rt-gw`; verified feature registration gate (`ApprovalRequired`), then validated the 10-route `/16` UDR override restoring symmetric NVA traversal. | **BLOCKED** (on PG feature approval) / **PASS** (symmetric NVA path verified) | [`s2-feature-registration-status.json`](show-output/s2-feature-registration-status.json), [`s2-disable-peering-route-error.txt`](show-output/s2-disable-peering-route-error.txt), [`s2-workaround-nic-vm-hub-probe-routes.txt`](show-output/s2-workaround-nic-vm-hub-probe-routes.txt), [`s2-workaround-nva-stateful-counters.txt`](show-output/s2-workaround-nva-stateful-counters.txt) |
| **S3 — Cross-VNet Next-Hop Constraint (`rt-spoke1`)** | Verified why `disablePeeringRoute = All` cannot be enabled on a spoke subnet route table whose UDR next hop (`10.0.1.4`) lives in the peered hub VNet (`10.0.0.0/16`). | **BLOCKED** (by S2 feature gate; routing dependency confirmed via `nic-vm-spoke1` effective routes) | [`s1-nic-vm-spoke1-routes.txt`](show-output/s1-nic-vm-spoke1-routes.txt) |

## Designs studied

| Design / Scenario | Status | Verdict | Rationale (`design.md`) | Evidence |
|-------------------|--------|---------|-------------------------|----------|
| **D1 (Scenario S1): Summarized `10.0.0.0/8` UDR on `GatewaySubnet` with default peering propagation (`disablePeeringRoute = None`)** | Not Recommended | **PASS** (Negative baseline verified: asymmetric routing drops stateful traffic) | [Section 5 — Scenario S1](design.md#scenario-s1--baseline-disablepeeringroute--none) | [`s1-nic-vm-hub-probe-routes.txt`](show-output/s1-nic-vm-hub-probe-routes.txt), [`s1-nva-stateless-counters.txt`](show-output/s1-nva-stateless-counters.txt), [`s1-nva-stateful-counters.txt`](show-output/s1-nva-stateful-counters.txt) |
| **D2a (Scenario S2 — Preview Feature): Summarized `10.0.0.0/8` UDR on `GatewaySubnet` with `disablePeeringRoute = All`** | Recommended (when feature flag is approved) | **BLOCKED** (`AllowDisablePeeringRoutes` requires manual PG approval: `approvalType: ApprovalRequired`) | [Section 5 — Scenario S2](design.md#scenario-s2--enable-disablepeeringroute--all-on-rt-gw-gatewaysubnet) | [`s2-feature-registration-status.json`](show-output/s2-feature-registration-status.json), [`s2-disable-peering-route-error.txt`](show-output/s2-disable-peering-route-error.txt) |
| **D2b (Scenario S2 — Production Workaround): Explicit per-spoke `/16` UDRs (`10.1.0.0/16`..`10.10.0.0/16 -> 10.0.1.4`) on `GatewaySubnet`** | Recommended (when `AllowDisablePeeringRoutes` is not yet approved and spoke count $\le 400$) | **PASS** (Invalidates all 10 `VNetPeering` routes; symmetric stateful NVA inspection verified) | [Section 5 — Scenario S2](design.md#scenario-s2--enable-disablepeeringroute--all-on-rt-gw-gatewaysubnet) | [`s2-workaround-nic-vm-hub-probe-routes.txt`](show-output/s2-workaround-nic-vm-hub-probe-routes.txt), [`s2-workaround-onprem-stateful-test.txt`](show-output/s2-workaround-onprem-stateful-test.txt), [`s2-workaround-nva-stateful-counters.txt`](show-output/s2-workaround-nva-stateful-counters.txt) |
| **D3 (Scenario S3): Enabling `disablePeeringRoute = All` on Spoke Route Tables (`rt-spoke1`) with Cross-VNet Hub NVA Next Hop** | Not Recommended (Unsupported) | **BLOCKED** (Feature gate; architectural next-hop dependency verified on `nic-vm-spoke1`) | [Section 5 — Scenario S3](design.md#scenario-s3--enable-disablepeeringroute--all-on-spoke-route-table-rt-spoke1--cross-vnet-next-hop-limitation) | [`s1-nic-vm-spoke1-routes.txt`](show-output/s1-nic-vm-spoke1-routes.txt) |

---

## 1. Objective & Problem Statement

In an Azure hub-and-spoke topology with a central Network Virtual Appliance (NVA) in the hub VNet (`10.0.0.0/16`) and a VPN or ExpressRoute Gateway in `GatewaySubnet`, administrators often want to route all ingress traffic from on-premises (`172.16.0.0/16`) to all spokes (`10.1.0.0/16` .. `10.10.0.0/16`) through the hub NVA (`10.0.1.4`) using a single summarized UDR on `GatewaySubnet`:

- `10.0.0.0/8 -> VirtualAppliance 10.0.1.4`

However, peering the hub VNet with 10 spoke VNets automatically injects 10 system routes (`Source: Default`, `NextHopType: VNetPeering`) into every hub subnet, one for each spoke's `/16` prefix (`10.1.0.0/16` .. `10.10.0.0/16`). Because `/16` is more specific than `/8` (Longest Prefix Match), the VPN Gateway routes inbound on-premises-to-spoke packets **directly** to the spoke over VNet peering, bypassing the hub NVA. Meanwhile, outbound spoke-to-on-premises return traffic follows the spoke's `172.16.0.0/16 -> 10.0.1.4` UDR through the hub NVA, causing **asymmetric routing** and immediate connection drops on any stateful firewall.

Azure's **Disable peering route propagation** feature (`disablePeeringRoute: All` on a route table, gated by `Microsoft.Network/AllowDisablePeeringRoutes`) solves this by suppressing `VNetPeering` routes on the associated subnet (`GatewaySubnet`), allowing the single `10.0.0.0/8` summary UDR to match all spoke prefixes without maintaining $N$ individual `/16` UDRs.

---

## 2. Lab Topology

```
+-----------------------------------------------------------------------------------+
| Simulated On-Premises VNet: vnet-onprem (172.16.0.0/16)                           |
|   snet-onprem (172.16.1.0/24)                                                     |
|     [vm-onprem: 172.16.1.4 | StrongSwan IKEv2 + FRR BGP ASN 65010]                |
+-----------------------------------------+-----------------------------------------+
                                          | S2S IPsec VPN + eBGP (vti0)
                                          v
+-----------------------------------------------------------------------------------+
| Hub VNet: vnet-hub (10.0.0.0/16)                                                  |
|                                                                                   |
|   GatewaySubnet (10.0.0.0/24)  <--- Route Table: rt-gw                            |
|     [vpngw-hub: VpnGw1AZ | ASN 65515 | BGP IP 10.0.0.254]                         |
|                                                                                   |
|   snet-hub-probe (10.0.2.0/24) <--- Route Table: rt-gw (effective route observer) |
|     [vm-hub-probe: 10.0.2.4]                                                      |
|                                                                                   |
|   snet-nva (10.0.1.0/24)                                                          |
|     [vm-hub-nva: 10.0.1.4 | IP Forwarding + iptables conntrack/LOG]               |
+-----+-------+-------+-------+-------+-------+-------+-------+-------+-------+-----+
      |       |       |       |       |       |       |       |       |       |
      | VNet Peerings (AllowGatewayTransit = true / UseRemoteGateways = true) |
      v       v       v       v       v       v       v       v       v       v
  +-------+ +---+   +---+   +---+   +---+   +---+   +---+   +---+   +---+  +----+
  |Spoke 1| |S2 |   |S3 |   |S4 |   |S5 |   |S6 |   |S7 |   |S8 |   |S9 |  |S10 |
  |10.1/16| |10.2   |10.3   |10.4   |10.5   |10.6   |10.7   |10.8   |10.9  |10.10
  +---+---+ +---+   +---+   +---+   +---+   +---+   +---+   +---+   +---+  +----+
      |
      +-- snet-workload (10.1.1.0/24) <--- Route Table: rt-spoke1 (BGP prop disabled)
            [vm-spoke1: 10.1.1.4 | Python HTTP server :80]
```

> **Observability tip (`vm-hub-probe`):** Azure does not expose `az network nic show-effective-route-table` for the internal NICs of a managed VPN Gateway (`vpngw-hub`). By associating a lightweight probe subnet (`snet-hub-probe` with `nic-vm-hub-probe`) to the **exact same `rt-gw` route table** attached to `GatewaySubnet`, we can inspect the exact effective route table evaluated by `rt-gw` via CLI while simultaneously validating the live VPN Gateway data plane from `vm-onprem` (`172.16.1.4`) to `vm-spoke1` (`10.1.1.4`).

---

## 3. Experimental Results

### 3.1 VPN & eBGP Baseline (`vm-onprem` <-> `vpngw-hub`)

`vm-onprem` establishes a route-based IKEv2 IPsec tunnel (`vti0`) to `vpngw-hub` and exchanges routes via eBGP (ASN `65010` <-> ASN `65515`). Importantly, `vpngw-hub` advertises the hub prefix (`10.0.0.0/16`) and **all 10 peered spoke prefixes (`10.1.0.0/16` .. `10.10.0.0/16`)** over BGP to `vm-onprem` regardless of what route table is on `GatewaySubnet`:

```text
Neighbor        V         AS   MsgRcvd   MsgSent   TblVer  InQ OutQ  Up/Down State/PfxRcd   PfxSnt Desc
10.0.0.254      4      65515         3         5        0    0    0 00:00:07           11       12 N/A

B>  10.0.0.0/16 [20/0] via 10.0.0.254 (recursive), weight 1, 00:00:07
  *                      via 10.0.0.254, vti0 onlink, weight 1, 00:00:07
B>  10.1.0.0/16 [20/0] via 10.0.0.254 (recursive), weight 1, 00:00:07
...
B>  10.10.0.0/16 [20/0] via 10.0.0.254 (recursive), weight 1, 00:00:07
```

### 3.2 Scenario S1 — Baseline (`disablePeeringRoute = None` with Summarized `10.0.0.0/8` UDR)

With `rt-gw` containing only the summarized `10.0.0.0/8 -> VirtualAppliance 10.0.1.4` UDR, the effective route table on `rt-gw` (`nic-vm-hub-probe`) shows all 10 `VNetPeering` `/16` routes **Active** alongside the `/8` User route:

```text
Source                 State    Address Prefix    Next Hop Type          Next Hop IP
---------------------  -------  ----------------  ---------------------  --------------
Default                Active   10.0.0.0/16       VnetLocal
Default                Active   10.1.0.0/16       VNetPeering
Default                Active   10.2.0.0/16       VNetPeering
...
Default                Active   10.10.0.0/16      VNetPeering
VirtualNetworkGateway  Active   172.16.0.0/16     VirtualNetworkGateway  20.240.221.177
User                   Active   10.0.0.0/8        VirtualAppliance       10.0.1.4
```

When `vm-onprem` (`172.16.1.4`) sends 3 ICMP echo requests and 1 HTTP GET request to `vm-spoke1` (`10.1.1.4`):

1. **Stateless NVA (`iptables -P FORWARD ACCEPT`):**
   - Ping (`3/3`, ~3.5 ms) and HTTP `GET http://10.1.1.4` (`200 OK`) succeed, **but routing is completely asymmetric**.
   - `iptables -L FORWARD -v -n` on `vm-hub-nva` (`10.0.1.4`) proves **0 packets** (`0 bytes`) traversed the NVA from `172.16.0.0/16 -> 10.0.0.0/8`, while **8 packets** (`747 bytes` — 3 ICMP Echo Replies + 5 TCP `SYN-ACK`/`ACK`/`PSH`/`FIN` segments from `10.1.1.4`) traversed the NVA in the reverse direction (`10.0.0.0/8 -> 172.16.0.0/16`).
2. **Stateful NVA (`conntrack` enforcing `NEW` on `SYN` / Echo Request, dropping `ctstate INVALID`):**
   - Ping fails with **100% packet loss** (`3 transmitted, 0 received`) and `curl http://10.1.1.4` **times out**.
   - `vm-hub-nva` kernel logs and counters show `0` forward packets seen and `11` return packets (`ICMP TYPE=0` Echo Replies and `TCP SPT=80 ACK SYN` replies from `10.1.1.4`) dropped by `ctstate INVALID` (`NVA_DROP_ASYM_INVALID`) because the initial `SYN` and Echo Request bypassed the NVA via `VNetPeering`.

### 3.3 Scenario S2 — `AllowDisablePeeringRoutes` Feature Gate & `/16` Override Verification

We registered `Microsoft.Network/AllowDisablePeeringRoutes` and inspected its registration resource via `az feature registration show`:

```json
{
  "name": "AllowDisablePeeringRoutes",
  "properties": {
    "approvalType": "ApprovalRequired",
    "description": "Enabling customers to use newly created feature AllowDisablePeeringRoutes in their routes",
    "providerNamespace": "Microsoft.Network",
    "releaseDate": "2025-08-20T22:51:47.519752+00:00",
    "state": "Pending"
  }
}
```

**Key operational finding:** Unlike self-serve preview flags (`approvalType: AutoApproval`), `Microsoft.Network/AllowDisablePeeringRoutes` has `"approvalType": "ApprovalRequired"` and remains `Pending` until manually approved by the Azure Virtual Network product team. Attempting to set `--disable-peering-route All` while the feature is `Pending` returns:

```text
ERROR: (UnauthorizedClientApplication) Unauthorized client application id DisablePeeringRoute is not supported.
Code: UnauthorizedClientApplication
Message: Unauthorized client application id DisablePeeringRoute is not supported.
```

To verify the exact data-plane state that `disablePeeringRoute = All` achieves—and demonstrate the operational overhead it eliminates—we added the 10 explicit `/16` UDRs (`10.1.0.0/16` .. `10.10.0.0/16 -> VirtualAppliance 10.0.1.4`) to `rt-gw`. Immediately:

- All 10 `Default` `VNetPeering` routes in `rt-gw` transitioned from `Active` to `Invalid`:
  ```text
  Source   State    Address Prefix    Next Hop Type     Next Hop IP
  -------  -------  ----------------  ----------------  -------------
  Default  Active   10.0.0.0/16       VnetLocal
  Default  Invalid  10.1.0.0/16       VNetPeering
  ...
  Default  Invalid  10.10.0.0/16      VNetPeering
  User     Active   10.0.0.0/8        VirtualAppliance  10.0.1.4
  User     Active   10.1.0.0/16       VirtualAppliance  10.0.1.4
  ...
  User     Active   10.10.0.0/16      VirtualAppliance  10.0.1.4
  ```
- Re-running the **stateful NVA** test from `vm-onprem` (`172.16.1.4`) to `vm-spoke1` (`10.1.1.4`) succeeded with **0% packet loss** (`3/3` pings, `HTTP/1.0 200 OK`), and `vm-hub-nva` recorded **8 forward packets (`592 bytes`)** and **8 return packets (`747 bytes`)** with **0 `INVALID` drops**.

### 3.4 Scenario S3 — Spoke Route Table Next-Hop Constraint (`rt-spoke1`)

Examining `nic-vm-spoke1`'s effective routes (`show-output/s1-nic-vm-spoke1-routes.txt`) confirms why `disablePeeringRoute = All` **must not** be enabled on spoke route tables that point to a hub NVA:

```text
Source    State    Address Prefix    Next Hop Type     Next Hop IP
--------  -------  ----------------  ----------------  -------------
Default   Active   10.1.0.0/16       VnetLocal
Default   Active   10.0.0.0/16       VNetPeering
User      Active   172.16.0.0/16     VirtualAppliance  10.0.1.4
User      Active   10.0.0.0/8        VirtualAppliance  10.0.1.4
```

On `vm-spoke1`, the UDR next hop `10.0.1.4` (`vm-hub-nva`) is resolved recursively through the `Default` `10.0.0.0/16 -> VNetPeering` route. If `disablePeeringRoute = All` is enabled on `rt-spoke1`, the `10.0.0.0/16 -> VNetPeering` system route is removed, leaving the Azure SDN fabric in `vnet-spoke1` with no underlay path to reach `10.0.1.4`.

---

## 4. Current Environment State & Next Steps

- **Current state:** All resources in `rg-disable-peering-routes-lab` (`swedencentral`) are **running and retained** per user instruction. `rt-gw` currently has the 10 `/16` spoke UDRs installed and `vm-hub-nva` is in stateful mode so `vm-onprem -> vm-spoke1` traffic is healthy and symmetric.
- **Once `AllowDisablePeeringRoutes` is approved on the subscription:**
  1. Run `az provider register --namespace Microsoft.Network`.
  2. Delete `route-spoke1`..`route-spoke10` from `rt-gw` (leaving only `route-to-spokes-summary` `10.0.0.0/8 -> 10.0.1.4`).
  3. Run `az network route-table update -g rg-disable-peering-routes-lab -n rt-gw --disable-peering-route All`.
  4. Re-run `az network nic show-effective-route-table -g rg-disable-peering-routes-lab -n nic-vm-hub-probe` to observe all 10 `VNetPeering` routes disappear completely without per-spoke `/16` UDRs.
- **Cleanup:** Standing by for user approval before deleting `rg-disable-peering-routes-lab`.
