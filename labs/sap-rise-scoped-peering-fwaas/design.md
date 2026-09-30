# sap-rise-scoped-peering-fwaas — Network Design
**Author:** Trinity (Azure Network SME) · **Date:** 2026-09-29 · **Status:** LOCKED — pre-deploy only; no IaC

Source of truth for scope/address plan: `.squad/decisions/inbox/morpheus-sap-rise-lab-scope.md`. This design fills in the networking detail and resolves the S2 open question (§6.3).

---

## 1. Executive Summary

Single region (swedencentral), single ER circuit via one Megaport MCR, single `ErGw1AZ` gateway. Hub↔spoke connectivity is **subnet-scoped VNet peering** (`--peer-complete-vnet false`) limited to each side's NVA subnet — this is the mechanism under test, not a workaround. Two scenarios contrast how to make ExpressRoute advertise the spoke's full `/16` instead of the naturally-peered `/27`:

- **S1** — Azure Route Server (ARS) in the hub + hub NVA (BIRD, ASN 65001) eBGP peer with ARS (65515), redistributing a static route for the spoke supernet. Fixes both the BGP advertisement **and** the data path (ARS injects the return route into the ER Gateway).
- **S2** — `summarizedGatewayPrefixes` set on **vnet-hub** (not the spoke — see §6.2 correction). Fixes the BGP advertisement only. **Does not** restore end-to-end reachability to the non-peered workload subnet — see §6.3, this is the lab's primary teaching point.

Out of scope: NVA filtering logic (both "firewalls" are placeholder Linux VMs), HA/AZ-zone redundancy beyond gateway SKU default, internet egress, DNS.

---

## 2. Address plan

| VNet | Region | Address space | Subnet | CIDR | Usable IPs | Notes |
|---|---|---|---|---|---|---|
| vnet-hub | swedencentral | 10.40.0.0/16 | GatewaySubnet | 10.40.0.0/27 | 27 (5 reserved) | ErGw1AZ; no NSG/UDR (Azure-managed) |
| | | | RouteServerSubnet | 10.40.0.32/27 | 27 (5 reserved) | ARS only; no NSG/UDR permitted |
| | | | snet-hub-nva | 10.40.1.0/27 | 27 (5 reserved) | Hub NVA; IP fwd ON; peered subnet (local) for S1+S2 |
| vnet-sap-rise | swedencentral | 10.60.0.0/16 | snet-spoke-nva | 10.60.0.0/27 | 27 (5 reserved) | Spoke NVA; IP fwd ON; peered subnet (remote) |
| | | | snet-workload | 10.60.1.0/24 | 251 (5 reserved) | SAP workload probe VM; **not** in the peering scope |
| (simulated on-prem) | — | 172.40.100.0/24 | — | — | 251 (5 reserved) | CE-side test prefix, ASN 65000, advertised over the ER private peering |

Azure reserves 5 IPs per subnet (network, gateway `.1`, `.2`, `.3`, broadcast) on every subnet above, including `/27`s — plan already accounts for that; no subnet is oversubscribed.

**PIPs:** ErGw1AZ = 1 Standard PIP (zone-redundant SKU, no AZ pinning requested). ARS = 0 PIPs (ARS has no public IP). NVA/probe VMs = 0 public IPs (SSH via Bastion/jump path is Tank's deploy-time decision, not a design requirement here).

---

## 3. Subnet-level peering spec (the mechanism under test)

Requires subscription feature registration first (still gated in most tenants):

```bash
az feature register --namespace Microsoft.Network --name AllowMultiplePeeringLinksBetweenVnets
az feature show --namespace Microsoft.Network --name AllowMultiplePeeringLinksBetweenVnets --query properties.state
# wait for "Registered", then:
az provider register --namespace Microsoft.Network
```

Two peering objects (one per direction), each scoped to exactly one subnet on each side:

```bash
# hub -> spoke
az network vnet peering create \
  --name peer-hub-to-sap-rise \
  --resource-group <rg> \
  --vnet-name vnet-hub \
  --remote-vnet vnet-sap-rise \
  --peer-complete-vnet false \
  --local-subnet-names snet-hub-nva \
  --remote-subnet-names snet-spoke-nva \
  --allow-vnet-access true \
  --allow-forwarded-traffic true \
  --allow-gateway-transit false \
  --use-remote-gateways false

# spoke -> hub
az network vnet peering create \
  --name peer-sap-rise-to-hub \
  --resource-group <rg> \
  --vnet-name vnet-sap-rise \
  --remote-vnet vnet-hub \
  --peer-complete-vnet false \
  --local-subnet-names snet-spoke-nva \
  --remote-subnet-names snet-hub-nva \
  --allow-vnet-access true \
  --allow-forwarded-traffic true \
  --allow-gateway-transit false \
  --use-remote-gateways false
```

**Gateway transit correction (2026-09-29):** the live Terraform and Azure peering objects use `allowGatewayTransit=false` / `useRemoteGateways=false` on these subnet-scoped peerings. Tank confirmed the earlier transit-enabled variant is rejected/unsupported for this exact pattern, and the lab does not rely on it anyway: the simulated CE harness reaches the hub through its own separate full-VNet peering, while the S1/S2 mechanism under test is the hub-NVA-to-spoke-NVA path plus ARS/ER control-plane behavior. This correction does not weaken §6.3's conclusion; S2 is still advertisement-only because nothing injects the spoke `/16` into a usable downlink route for the non-peered workload subnet.

**Correction 2026-09-30 (live MSEE evidence overturns the prior "confirmed baseline" claim):** the line above previously stated that, with only subnet peering in place and no S1/S2 remediation, ExpressRoute advertises `10.40.1.0/27` and `10.60.0.0/27` (the peered subnets) to on-prem. That claim was never backed by an MSEE capture and turned out to be wrong. A direct test disabling ARS `allowBranchToBranchTraffic` (reproducing the true "no S1 fix" baseline) and reading both MSEE routers plus the ER Gateway's own tables shows only the hub `10.40.0.0/16` supernet and the ExpressRoute link-local `/30`. Neither `10.40.1.0/27` nor `10.60.0.0/27` appears anywhere, on either MSEE path, the gateway's learned-routes table, or its advertised-routes table. Subnet peering by itself does not push any prefix onto the BGP-advertised side of the ER Gateway; the earlier assumption conflated "the peering exists and data-plane connectivity works between the two peered subnets" with "ExpressRoute advertises the peered subnets to on-prem," which is a separate, and in this case false, claim. Evidence: `show-output/s0-baseline-msee-01-route-table-primary.json`, `s0-baseline-msee-02-route-table-secondary.json`, `s0-baseline-msee-03-ergw-learned-routes.json`, `s0-baseline-msee-04-ergw-advertised-routes.json`. The true pre-remediation baseline both S1 and S2 start from is: only the hub `/16` is advertised to on-prem, and the spoke is completely absent, not partially reachable via a `/27`.

**Live CE-topology correction (2026-09-29):** `vm-ce-onprem` is not behind the ER Gateway/MCR for the lab's VM-to-VM reachability probes. It lives in `vnet-onprem-sim` (`172.40.100.0/24`), which is **fully VNet-peered directly to `vnet-hub`** (`peerCompleteVnets=true`, `allowForwardedTraffic=true` both directions). So `vm-ce-onprem` reaches `10.40.1.4` over direct VNet peering, not through the real ExpressRoute/Megaport path or any gateway-transit hop. The CE-side probes therefore validate the Azure-side forwarding chain (`vnet-onprem-sim` -> `vm-hub-nva` -> `vm-spoke-nva` -> workload); the physical ER/Megaport path is evidenced separately by the gateway/circuit route collection in §8.

---

## 4. NSG rules (both NVA subnets — defense-in-depth per Morpheus's caveat)

Non-peered subnets get an inert forward-route entry to the peered subnet under current-release subnet peering (Azure drops rather than delivers) — but NSGs are still required because the inert-route behavior is undocumented Azure internals, not a security control. Minimal, named, ordered.

**`nsg-hub-nva`** (attached to `snet-hub-nva`):

| Pri | Name | Direction | Src | Dst | Port/Proto | Action | Rationale |
|---|---|---|---|---|---|---|---|
| 100 | Allow-ARS-BGP-In | In | 10.40.0.32/27 | VNet | 179/TCP | Allow | S1: ARS→hub NVA eBGP session |
| 110 | Allow-SpokeNVA-In | In | 10.60.0.0/27 | VNet | Any | Allow | Peered-subnet data path (spoke NVA↔hub NVA, both scenarios) |
| 115 | Allow-Workload-In | In | 10.60.1.0/24 | VNet | Any | Allow | Required because workload→CE traffic arrives at `vm-hub-nva` with the **original workload source IP**, not `10.60.0.4`. A `/27`-only spoke rule breaks the workload return leg even when the spoke NVA is the next hop. |
| 120 | Allow-OnpremSim-BGP-In | In | 172.40.100.0/24 | VNet | 179/TCP | Allow | S1: simulated on-prem CE (`vm-ce-onprem`) direct VNet-peered eBGP session to hub NVA (deviation #1) |
| 125 | Allow-OnpremSim-Data-In | In | 172.40.100.0/24 | VNet | Any | Allow | Required for the CE control/data probes. A BGP-only 179/TCP rule is insufficient because the CE VM reaches the hub NVA over direct VNet peering before any onward forwarding to the spoke. |
| 130 | Allow-SSH-Mgmt | In | <mgmt-source> | VNet | 22/TCP | Allow | Operator/Niobe access; scope to jump/Bastion CIDR at deploy time if SSH is used in a future revision |
| 4096 | DenyAllInbound | In | Any | Any | Any | Deny (default) | Explicit deny-by-default backstop |

**`nsg-spoke-nva`** (attached to `snet-spoke-nva`):

| Pri | Name | Direction | Src | Dst | Port/Proto | Action | Rationale |
|---|---|---|---|---|---|---|---|
| 100 | Allow-HubNVA-In | In | 10.40.1.0/27 | VNet | Any | Allow | Peered-subnet data path (hub NVA↔spoke NVA) |
| 105 | Allow-OnpremSim-Forwarded-In | In | 172.40.100.0/24 | VNet | Any | Allow | **Added 2026-09-29 after stage-4 failure.** Forwarded CE traffic traversing the hub keeps its original source IP (`172.40.100.4`), so a hub-subnet-only Allow is too narrow for the subnet-scoped-peering proof ping. |
| 110 | Allow-Workload-In | In | 10.60.1.0/24 | VNet | Any | Allow | Spoke NVA is the workload subnet's forced next hop (§5) — return traffic |
| 120 | Allow-SSH-Mgmt | In | <mgmt-source> | VNet | 22/TCP | Allow | Operator/Niobe access |
| 4096 | DenyAllInbound | In | Any | Any | Any | Deny (default) | Explicit deny-by-default backstop |

No outbound rules beyond platform defaults — both NVAs are placeholders, not stateful filters; the point under test is subnet/route scope, not rule design.

---

## 5. UDR / route table spec

| Subnet | Route table | Route(s) | Why |
|---|---|---|---|
| `snet-workload` | rt-spoke-workload | `0.0.0.0/0` → VirtualAppliance, next hop = spoke NVA private IP (10.60.0.4, first usable) | Only path out for the workload subnet — it is **not** in the peering scope, so it has no other route to hub/on-prem. Also covers `10.40.0.0/16` and `172.40.100.0/24` explicitly if operators want more-specific routes over the `0/0` catch-all (optional; `0/0` is sufficient for this lab). |
| `snet-spoke-nva` | rt-spoke-nva-return | `172.40.100.0/24` → VirtualAppliance, next hop = hub NVA private IP (10.40.1.4) | **Correction 2026-09-29 after stage-4 failure.** The spoke NVA subnet has a peering-derived path only to the hub NVA subnet (`10.40.1.0/27`), not to the separately-peered CE-simulation VNet. It therefore needs an explicit Azure-side return route for CE-sourced probes and for any workload traffic that the spoke NVA SNATs on the way back (§7.5). |
| `snet-hub-nva` | none | — | Peered subnet; system + BGP-learned (S1) routes suffice. |
| `GatewaySubnet` | not applicable | — | Azure does not support attaching a custom route table to `GatewaySubnet` in this configuration. Downlink routing into the hub NVA is driven by BGP (S1, via ARS) or is **absent** (S2 — see §6.3). |
| `RouteServerSubnet` | not applicable | — | ARS-managed; no UDR support. |
| `snet-ce-onprem` (simulated CE harness only) | rt-ce-onprem | `10.60.0.0/16` → VirtualAppliance, next hop = hub NVA private IP (10.40.1.4) | **Added 2026-09-29 (Defect C, S1 re-validation).** The simulated CE is connected to the hub via full VNet peering (deviation #1), not a real ER Gateway/Megaport circuit. VNet peering is not transitive, and ARS only auto-injects BGP-learned routes into subnets of its **own** VNet (`vnet-hub`) — never into a separately-peered VNet like `vnet-onprem-sim`. The CE's own BIRD RIB correctly learns `10.60.0.0/16` over its `hub_nva` eBGP session, but a guest-OS BGP route never programs Azure's SDN forwarding plane (same class of gap as §7.1 Defect 1, recurring here on the CE side). This UDR is accepted as part of the CE-simulation deviation, not a change to the real S1 mechanism under test: it only patches the harness link that stands in for the ER Gateway/Megaport leg, and does not touch or bypass the subnet-scoped peering between `vnet-hub` and `vnet-sap-rise` that is the actual subject of this lab. **Necessary, but not sufficient by itself:** it only gets CE-originated packets into the hub; the hub NSG and the hub VM's own Linux forwarding table must still permit and know the onward path to the spoke (§7.4). |

---

## 6. Gateway / ARS / S2 config spec

### 6.1 S1 — ARS + hub NVA BGP

- ARS: default SKU, deployed to `RouteServerSubnet`, `branch-to-branch traffic` **enabled** (`allowBranchToBranchTraffic = true`). **Correction 2026-09-29 (post S1 re-validation, Defect A):** this section previously said branch-to-branch was disabled "by design" while *also* claiming ARS→gateway route propagation was automatic regardless — those two statements are contradictory, and the disabled setting is what actually broke the data path. Azure Route Server only reflects routes between two different BGP peers (here: the hub NVA and the co-resident ER Gateway) when branch-to-branch is enabled; with it off, ARS learns `10.60.0.0/16` from the hub NVA but never hands it to the gateway, which is exactly what Niobe's re-validation caught (`ergw-sap-rise` `list-bgp-peer-status` showed `routesReceived: 0` from both ARS sessions). There is no single-peer/no-VPN-branches exception to this — "branch" in this property's name refers to any additional BGP speaker ARS reflects between, including a co-resident ExpressRoute Gateway, not just VPN site branches. Flipping this to `true` is the fix; no alternative mechanism exists to get ARS to propagate NVA-learned routes to the gateway.
- BGP peer: hub NVA (10.40.1.4, ASN 65001) ↔ ARS (65515). ARS auto-selects its own peering IPs from `RouteServerSubnet`.
- Hub NVA redistributes a **static route** `10.60.0.0/16 via 10.60.0.4` (spoke NVA IP, reachable over the subnet peering) into eBGP toward ARS. With branch-to-branch enabled, ARS in turn peers automatically with the ER Gateway (co-resident ARS+ERGW BGP relationship is automatic once both exist in the same hub VNet) and propagates the learned `10.60.0.0/16` prefix into the gateway's route table — this is what gives `GatewaySubnet` a real next-hop for downlink (on-prem→spoke) traffic, not just outbound advertisement.

### 6.2 S2 — `summarizedGatewayPrefixes` — **correction to the lab card**

Per current (2026-08 GA) Microsoft documentation, `summarizedGatewayPrefixes` is read **only from the VNet that contains the gateway subnet and gateway** — i.e., **`vnet-hub`**, not the spoke. Setting it on a spoke VNet is explicitly a documented no-op ("if you set this property on spoke (peered) virtual networks, it's ignored"). The lab card's phrasing ("set on the SAP RISE spoke VNet") needs correcting; I'm flagging this to Morpheus in the decision inbox (§9).

```bash
az network vnet update \
  --resource-group <rg> \
  --name vnet-hub \
  --set properties.summarizedGatewayPrefixes="['10.40.0.0/16','10.60.0.0/16']"
```

**CLI correction (2026-09-30, tested live):** the `az network vnet update --set properties.summarizedGatewayPrefixes=...` command above is illustrative of intent only; it does **not** currently work. `summarizedGatewayPrefixes` is not present in the typed VNet model that the installed Azure CLI's `az network vnet` command group serializes against, so the `--set` assignment is silently dropped or rejected depending on CLI version, and no error clearly points at the real cause. The verified working path in this lab was a raw ARM REST PUT against the VNet resource, setting `properties.summarizedGatewayPrefixes.addressPrefixes` directly in the request body (`api-version=2025-07-01` or later), bypassing the CLI's typed model entirely. That is the method actually used to produce the Design B evidence in §8: `az rest --method put --uri "https://management.azure.com/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Network/virtualNetworks/vnet-hub?api-version=2025-07-01" --body @vnet-hub-patch.json` (or equivalent `Invoke-AzRestMethod`/`curl` with a bearer token), where the body is the full VNet resource with `summarizedGatewayPrefixes.addressPrefixes` set to `["10.40.0.0/16","10.60.0.0/16"]`. If a future CLI release adds first-class support for this property, prefer it over the REST workaround; until then, treat the `az network vnet update` form above as the documented intent, not a command you can actually run.

Both entries required: the summarized-prefix list must cover the hub's own address space (per docs — otherwise the hub's own space would still be advertised individually) as well as the spoke's `/16` that the lab wants ExpressRoute to advertise instead of the naturally-peered `/27`. API surface: virtual network API `2025-07-01`+ (property landed there); GA as of 2026-08, no preview flag needed. No ARS/NVA-BGP participation required for the advertisement itself.

### 6.3 Resolution of the open question — S2 is advertisement-only, not a connectivity fix

**Concrete reasoning:**

1. `summarizedGatewayPrefixes` only changes the **content of BGP UPDATE messages** the ER Gateway sends toward on-prem. It has no documented (or plausible, given its property surface is a VNet-level advertisement list, not a routing construct) effect on the gateway's own **inbound** route table, `GatewaySubnet`'s system routes, or the underlying VNet-peering fabric.
2. Downlink reachability (on-prem → `10.60.1.0/24`) requires `GatewaySubnet` to hold a route/next-hop for `10.60.0.0/16` pointing at something that can actually deliver the packet — here, that's the hub NVA (which forwards to the spoke NVA over the subnet-peering link, which then forwards natively within `vnet-sap-rise` to `snet-workload`).
3. In **S1**, that route is injected by ARS (learned via eBGP from the hub NVA's static-route redistribution) — a real control-plane mechanism populating the gateway's routing.
4. In **S2** as scoped (summarized-prefix property only, no ARS, no hub-NVA BGP), **nothing injects an equivalent route into `GatewaySubnet`**. `GatewaySubnet` isn't itself part of the subnet-peering scope (only `snet-hub-nva` is), so it has no fabric path to the spoke beyond the "inert" route Azure leaves behind — which only covers the peered subnet prefix anyway, not the `/16` or the workload `/24`.
5. **Conclusion:** S2, as scoped, is confirmed **advertisement-only**. On-prem's BGP table shows `10.60.0.0/16` (looks fixed), but packets sent toward `10.60.1.0/24` black-hole at/before `GatewaySubnet` — they never reach the hub NVA. Traffic to the already-peered `10.60.0.0/27` (spoke NVA subnet) still works, because that path was never broken.
6. **Documented scope:** S2 is evidenced as **"advertisement-only, not a full connectivity fix"**. A genuinely complete S2 requires layering ARS route-injection back in (converging to S1) or replacing subnet-scoped peering with full VNet peering (defeats the lab's point). I'm documenting the negative result as the teaching point, not adding a hidden third scenario.
7. **Confirmed live (2026-09-30):** points 1-6 above were reasoned from documented behavior at the time this section was written. S2 has since actually been deployed (via the REST-based method in §6.2's CLI correction) and torn down again. MSEE route tables on both primary and secondary paths, and the ER Gateway's own advertised-routes table, all showed `10.60.0.0/16` appear the moment `summarizedGatewayPrefixes` was set on `vnet-hub`, and disappear again the moment it was reverted. Evidence: `show-output/s2-designB-01-vnet-hub-before.json`, `s2-designB-02-vnet-hub-after.json`, `s2-designB-03-msee-route-table-primary.json`, `s2-designB-04-msee-route-table-secondary.json`, `s2-designB-05-ergw-advertised-routes.json`, `s2-designB-06-vnet-hub-reverted.json`, `s2-designB-07-msee-final-verify.json`. This is real, live confirmation of the reasoned prediction above, not just documentation-based inference: on-prem genuinely receives a BGP route to `10.60.0.0/16`, and it is genuinely a phantom route, because no corresponding data-plane path into the spoke was created by this change alone.

---

## 7. NVA config spec

Both NVAs: NIC-level IP forwarding (`az network nic update --ip-forwarding true`) **and** OS-level (`net.ipv4.ip_forward=1` via cloud-init sysctl, per the `azure-lab` skill's `cloud-init-nva-base.yaml` pattern) — both layers required, NIC alone is insufficient.

**Hub NVA (BIRD, ASN 65001)** — needs full BGP config:

```
router id 10.40.1.4;
protocol device {}
protocol direct { interface "eth0"; }
protocol static {
    route 10.60.0.0/16 via 10.60.0.4;   # spoke NVA IP, reachable over subnet peering
}
protocol bgp ars {
    local as 65001;
    neighbor <ARS-peer-ip-1> as 65515;
    neighbor <ARS-peer-ip-2> as 65515;   # ARS always presents 2 peer IPs from RouteServerSubnet
    ipv4 { import none; export where source = RTS_STATIC; };
}
```

**Spoke NVA (ASN 65002)** — BGP-capable per the lab card but **dormant unless later extended**: no eBGP session is required for either S1 or S2 as scoped (the spoke NVA's only job in both scenarios is IP forwarding + the peered-subnet hop). Deploy with IP forwarding + iptables NAT masquerade only (`cloud-init-nva-base.yaml`); do not stand up BIRD on it for v1 — ship the ASN as a config placeholder (`local as 65002;` commented out) so a future extension (e.g., spoke-originated BGP toward a second ARS) doesn't require a redeploy, just an activation.

### 7.1 CORRECTION (2026-09-29, post S1-FAIL) — hub NVA `bird.conf` fixes

Niobe's live S1 validation found the deployed `vm-hub-nva` `bird.conf` (Tank's implementation of §7, extended with a `ce_onprem` BGP protocol not shown in the original skeleton) **fails end-to-end**. Supersedes §7's `protocol static` and `ce_onprem` blocks — three fixes:

**Defect 1 (primary root cause) — recursive next-hop static route never resolves.**
```
BEFORE: route 10.60.0.0/16 via 10.60.0.4;
AFTER:  route 10.60.0.0/16 via 10.60.0.4 dev "eth0" onlink;
```
Bare `via` is *recursive*: BIRD needs an existing RIB route to `10.60.0.4` before installing it. Azure subnet peering delivers that reachability transparently at the SDN layer (`ping` succeeds) but never injects a matching route into the guest kernel table, so BIRD's `kernel1 { learn; }` never sees it and resolution permanently fails — `static_bgp` installs zero routes, so nothing is ever available to export. Fix pattern: any static route whose next hop is reachable only via VNet/subnet peering needs `dev "<iface>" onlink`, never a bare recursive `via`.

**Defect 2 (confirmed authoring bug, not deliberate) — `ce_onprem export none`.**
```
BEFORE: ipv4 { import all; export none; };
AFTER:  ipv4 { import all; export where proto = "static_bgp"; };
```
§6.1/§7 always intended the hub NVA to originate `10.60.0.0/16` to every eBGP peer, ARS included; nothing documents withholding it from on-prem as intentional. Mirrors the `azure_peer` template's filter minus the self-reference.

**Defect 3a — persistent flap on all 3 sessions ("Hold timer expired," alternating across polls), initial hypothesis.** Ruled out: MTU (no mismatch anywhere — all paths are Azure-standard 1500-byte) and gross timer misconfiguration (60s/20s is a standard, non-aggressive pair). Initial hypothesis: Defect 1's endless failed resolution forces a RIB recalc + BGP export re-evaluation on every 10–15s scan; on the `Standard_B2s_v2` **burstable, CPU-credit** fallback SKU (deviation #4), sustained recalc under credit pressure plausibly makes BIRD miss a keepalive past the 60s hold window.

Insurance applied at the time (config-only, patch **P4**): bump hold/keepalive on all three hub-NVA BGP protocols from `60/20` to `180/60`.

**CLOSED 2026-09-29 — Defect 3a confirmed and fixed.** Defect 1's kernel-export fix (the `onlink` static route) removed the RIB-recalc churn entirely; Azure Monitor CPU/credit telemetry on `vm-hub-nva` (round 2) and later on `vm-ce-onprem` (round 4) both showed negligible CPU (<1%) and healthy, monotonically climbing credit balances throughout — ruling out CPU-credit starvation definitively on both VMs. This defect is closed: the hub-side RIB churn was real, the fix removed it, and the CPU-credit hypothesis is neither confirmed as the flap's original mechanism nor needed anymore — the `ars` and `azure_rs_1`/`azure_rs_2` sessions have been stable since. **P4's 180/60 timer bump on the hub side stands** (harmless insurance, and it turned out to matter for a different, related reason — see Defect 3b immediately below).

**Defect 3b — CE-side timer asymmetry (found in round 4, the actual cause of the flap surviving after Defect 1/3a's fix).** After Defect 1 was fixed, one session kept flapping: `ce_onprem` (hub side) / `hub_nva` (CE side). Root cause, confirmed with millisecond-correlated `journalctl -u bird` logs from **both** `vm-hub-nva` and `vm-ce-onprem`, plus a simultaneous `tcpdump`: P4's timer bump was applied only to the **hub's** `ce_onprem` block (`hold time 180; keepalive time 60;`) — `vm-ce-onprem`'s own `bird.conf`, `hub_nva` block, was never touched and was still running the pre-fix `hold time 60; keepalive time 20;`. BGP negotiates the *lower* hold time offered by either side, so the session negotiated to 60s (the CE's value) against a hub now keeping alive only every 60s — zero margin. The CE's own hold timer expired locally every cycle (`Error: Hold timer expired` on the CE, `Received: Hold timer expired` on the hub, identical timestamps), and `tcpdump` showed the CE actively participating right up to a clean, self-initiated FIN at the exact expiry moment. CPU/credit starvation was ruled out on the CE as well.

**Fix applied 2026-09-29:** aligned `vm-ce-onprem`'s `hub_nva` block to the same `hold time 180; keepalive time 60;` as the hub's `ce_onprem` block (symmetric values on both ends of the session — one timer policy, not two). `vm-hub-nva`'s `bird.conf` was **not** touched again. See the round-5 decision (`.squad/decisions/inbox/trinity-s1-defect3b-final.md`) for the exact command. **CLOSED**, pending Tank's standard 10+ minute/4-poll verification showing all three sessions (`ce_onprem`/`hub_nva`, `azure_rs_1`, `azure_rs_2`) simultaneously `Established` on every poll.

**Design rule going forward (redeploy-safety):** the `ce_onprem` (hub) ↔ `hub_nva` (CE) BGP session is a single logical session realized as **two separate `bird.conf` files on two separate VMs** — there is no shared config source between them. **Any future change to this session's `hold time`/`keepalive time` (or any other negotiated BGP timer) must be applied to both `vm-hub-nva`'s `ce_onprem` block AND `vm-ce-onprem`'s `hub_nva` block together, in the same change.** A one-sided edit is silently accepted by BIRD (no config-time error — negotiation just falls back to the lower/looser side) and only surfaces later as an intermittent flap, which is exactly the failure mode that produced Defect 3b. This does not apply to the `ars`/`azure_rs_1`/`azure_rs_2` sessions, which are BIRD↔ARS (a managed Azure PaaS BGP speaker, not another `bird.conf` file) and are not at risk of this specific class of drift.

**SKU note (advisory to Morpheus, superseded):** the non-burstable-SKU escalation path considered for Defect 3a is no longer needed — the flap was fully explained and closed by Defect 1 (RIB churn) and Defect 3b (CE timer asymmetry), not by SKU-level CPU-credit throttling.

### 7.2 `vm-ce-onprem` (simulated CE, ASN 65000) `bird.conf` — documented 2026-09-29, was missing from §7

§7's original skeleton only specified the hub NVA; the simulated on-prem CE (`vm-ce-onprem`,
deviation from §6's "4th VM acting as BGP speaker" open item, resolved by Tank) runs its own BIRD
instance with a `hub_nva` protocol block that is the direct peer of the hub's `ce_onprem` block.
This was never captured in the design doc before Defect 3b's investigation, which is part of why
the timer drift went unnoticed. Documenting it now so a future redeploy doesn't reintroduce it:

```
protocol bgp hub_nva {
    local 172.40.100.4 as 65000;
    neighbor 10.40.1.4 as 65001;
    multihop 2;
    ipv4 {
        import all;
        export where proto = "static_bgp";
    };
    graceful restart on;
    connect retry time 10;
    hold time 180;
    keepalive time 60;
}
```

(`hold time`/`keepalive time` shown post-Defect-3b-fix; see §7.1 Defect 3b above for the pre-fix
values and history.)

**This is one logical BGP session split across two independent config files (`vm-hub-nva`'s
`bird.conf` `ce_onprem` block, and `vm-ce-onprem`'s `bird.conf` `hub_nva` block) with no shared
source of truth between them.** Anyone extending or redeploying this lab must treat any change to
this session's negotiated parameters (timers, `multihop`, ASNs, addressing) as a two-file change,
applied to both VMs together — not just the hub side. BIRD will not error at config-load time on a
one-sided change; it silently negotiates to the looser/lower value offered by either side, and the
mismatch only surfaces later as an intermittent flap (exactly what happened in Defect 3b).

### 7.3 CORRECTION (2026-09-29, post S1 re-validation) — hub NVA `ip_forward` never applied (Defect B)

Niobe's independent re-validation (all BGP/BIRD layers confirmed correct) found `vm-hub-nva`'s live kernel `net.ipv4.ip_forward` was `0`, even though `/etc/sysctl.d/99-ip-forward.conf` correctly specifies `net.ipv4.ip_forward = 1`. The file was written (cloud-init did its job) but never actually loaded into the running kernel — `sysctl -p` was never run against it, or ran before the file existed on disk. This is a pure deployment-application gap, not a design defect: §7's spec (both NIC-level and OS-level IP forwarding required) was correct all along, it just wasn't fully carried out at deploy time. Fix and verification:

```bash
az vm run-command invoke -g <rg> -n vm-hub-nva --command-id RunShellScript \
  --scripts "sysctl -p /etc/sysctl.d/99-ip-forward.conf && cat /proc/sys/net/ipv4/ip_forward"
```

Expected output: `net.ipv4.ip_forward = 1` (echoed by `sysctl -p`) followed by `1` (the live kernel value). **Deploy-time hardening recommendation (to prevent recurrence on any future redeploy of this lab or reuse of `cloud-init-nva-base.yaml`/`cloud-init-nva-bird.yaml`):** add a verification step to `deploy.ps1` immediately after each NVA VM is provisioned that runs `cat /proc/sys/net/ipv4/ip_forward` via `run-command` and fails the deploy script loudly (non-zero exit, red console text) if the value isn't `1` — do not rely on the sysctl file's mere presence as proof it was applied. This closes the same class of "config written but not loaded" gap for good.

### 7.4 CORRECTION (2026-09-29, post Tank A/B/C apply) — CE control ping still fails because the hub data plane is only half-fixed

Tank's A/B/C apply proved the Azure control plane is now clean: ARS reflects `10.60.0.0/16` to the ER Gateway, `ip_forward=1` is live on `vm-hub-nva`, and `nic-ce-onprem` shows the `10.60.0.0/16 -> VirtualAppliance -> 10.40.1.4` UDR as active. Yet the first CE-side control ping still failed (`vm-ce-onprem` -> `10.60.0.4`, 100% loss). The missing pieces are both **hub-side**, and they are independent:

**Correction 2026-09-30 (Defect H, see §7.6): the claim above that "ARS reflects `10.60.0.0/16` to the ER Gateway" was never backed by gateway-side evidence and is incorrect as stated.** It was based on ARS's own learned-routes view (which does show the route, correctly, from the hub NVA) without checking whether the ER Gateway itself actually received anything from ARS. No capture, in this lab, at any point (before or after `allowBranchToBranchTraffic` was toggled to `true`), ever shows the ER Gateway's BGP peer status reporting a nonzero route count from either ARS peer, or the gateway's own learned-routes table containing `10.60.0.0/16`. See §7.6 for the full evidence review and root-cause hypothesis.

**Defect D — `nsg-hub-nva` still blocks the CE data plane, and also blocks the workload return leg.** Because `vm-ce-onprem` is full-VNet-peered directly to `vnet-hub` (§3 correction above), the very first reachability question is simply "can the CE VM reach `10.40.1.4`?" Live evidence says **no**: `vm-ce-onprem` cannot ping `10.40.1.4`, while `vm-hub-nva` can ping `172.40.100.4`. The asymmetry is explained entirely by the hub NSG: its custom Allow rules only admit `10.40.0.32/27`, `10.60.0.0/27`, and `172.40.100.0/24` on **TCP/179 only**, then `DenyAllInbound` at priority 4096 overrides Azure's default `AllowVnetInBound`. That blocks CE-originated ICMP/TCP data traffic before Linux forwarding is even in play. Separately, it also blocks the real pass bar (`vm-workload-probe` -> CE) because the hub sees that traffic with source `10.60.1.4`, not `10.60.0.4`; a spoke-NVA-subnet-only rule is too narrow.

**Defect E — the hub NVA advertises `10.60.0.0/16`, but does not install it in the Linux forwarding table anymore.** The round-3 BGP fix (`protocol kernel export all;` -> `export none;`) was necessary to stop ARS-learned-route poisoning, but it also removed the only guest-OS FIB entry that can steer **non-peered** spoke destinations toward the spoke NVA. Live evidence is explicit: on `vm-hub-nva`, `birdc show route 10.60.0.0/16 all` still shows the correct static route (`via 10.60.0.4 on eth0 onlink`), but `ip route get 10.60.1.4` resolves to the default Azure gateway (`via 10.40.1.1`) and `ping 10.60.1.4` fails, while `ping 10.60.0.4` succeeds. In other words, BIRD can now **advertise** the spoke `/16`, but Linux still cannot **forward** workload-bound traffic to it.

**Correct fix:** re-open `vm-hub-nva`'s `bird.conf` for exactly one line, and only for the kernel-export direction:

```text
BEFORE: protocol kernel { ipv4 { import all; export none; }; learn; scan time 15; }
AFTER:  protocol kernel { ipv4 { import all; export where proto = "static_bgp"; }; learn; scan time 15; }
```

That keeps the round-3 protection (no ARS- or CE-learned routes get pushed back into the guest kernel table), while restoring the single locally-authored static route the hub Linux data plane actually needs. No change is required to `vm-ce-onprem`'s `bird.conf`.

### 7.5 CORRECTION (2026-09-29, post retry-3 stage-4 failure) — the residual defect is now on the spoke side, not the hub

Tank's retry-3 evidence closes the hub-side questions from §7.4:

- `ip route show 10.60.0.0/16` on `vm-hub-nva` now shows `via 10.60.0.4 dev eth0`
- `ip route get 10.60.1.4` resolves `via 10.60.0.4 dev eth0`
- `vm-ce-onprem` now reaches `10.40.1.4` with `0%` loss

So the packet now reaches the hub NVA and the hub has a usable onward route. The remaining stage-4 failure (`vm-ce-onprem` -> `10.60.0.4`) is explained by **two spoke-side omissions that both exist in the deployed state**:

**Defect F — `nsg-spoke-nva` is scoped too narrowly for forwarded CE traffic.** The subnet-scoped peering is live and both peering objects already have `allowForwardedTraffic=true`, but Azure does **not** rewrite the source of a packet just because it crossed an NVA hop. The spoke side therefore sees the CE-originated control ping still sourced from `172.40.100.4`, while the deployed spoke NSG only allows inbound from `10.40.1.0/27` and `10.60.1.0/24`. Without an explicit Allow for `172.40.100.0/24`, the very control ping that proves the spoke NVA subnet is reachable through the peering is blocked at the spoke-subnet boundary.

**Defect G — the spoke NVA subnet has no Azure-side return path to the CE-simulation VNet.** Live guest and effective-route evidence both show `vm-spoke-nva` has only local `10.60.0.0/27` plus default-to-Internet routing; there is no route to `172.40.100.0/24`. Because the CE harness lives in a third VNet (`vnet-onprem-sim`) and subnet-scoped peering is not transitive, the spoke side must carry an explicit `172.40.100.0/24 -> VirtualAppliance -> 10.40.1.4` route on `snet-spoke-nva` to send replies back through the hub NVA. The existing peering-derived route to `10.40.1.0/27` is not enough, because the actual destination is the CE prefix, not the hub subnet itself.

These are not new BGP defects. They are Azure-side spoke-subnet policy and routing gaps specific to the simulated-CE deviation. The next corrective round should therefore be:

1. add an inbound NSG Allow on `nsg-spoke-nva` for `172.40.100.0/24`
2. attach a narrow return-route table to `snet-spoke-nva` with `172.40.100.0/24 -> 10.40.1.4`

Only after those two are in place should stage 4 be expected to pass, which then unlocks the real non-peered workload probe at stage 5.

### 7.6 CORRECTION (2026-09-30, gateway-side BGP evidence review), Defect H: the ER Gateway never actually received `10.60.0.0/16` from ARS, so S1's real ExpressRoute data path was never proven

Jose asked why the option-1 "after fix" MSEE route tables don't show `10.60.0.0/16`, since without it the real data plane over the ExpressRoute circuit cannot possibly work. A direct review of every gateway-side and MSEE-side capture in this lab's evidence set confirms his read is correct, and finds an overclaim in §7.4 above.

**What every capture actually shows:**

- `show-output/s1-reconcile-01-ars-show.json`: `allowBranchToBranchTraffic: true` (the S1 fix, applied). ARS's own `routeTable.routes` is empty (this field is not the relevant signal here; ARS's per-peer learned-routes view is what matters and is checked separately below).
- `show-output/s1-reconcile-02-ergw-bgp-peer-status.json`: the ER Gateway's two BGP sessions to the ARS peer IPs (`10.40.0.37`, `10.40.0.36`) both report `routesReceived: 0`, with `connectedDuration` around 20h20m.
- `show-output/s1-reconcile-03-ergw-learned-routes.json` and `s1-reconcile-04-ergw-advertised-routes.json`: the gateway's own learned- and advertised-routes tables contain only `10.40.0.0/16` (the hub supernet) and the ExpressRoute link-local `/30`. `10.60.0.0/16` appears in neither.
- `show-output/s1-msee-02-route-table-primary.json` and `s1-msee-03-route-table-secondary.json`: the real MSEE-side route tables (via `az network express-route list-route-tables`) match the gateway's own advertised-routes table exactly: only `10.40.0.0/16` (two ECMP next hops) and the link-local `/30`. No `10.60.0.0/16` on either path.
- `show-output/s1-revalidation-09-ars-config-branch-to-branch.json` (captured earlier, different etag, `allowBranchToBranchTraffic: false` at that point): `show-output/s1-revalidation-05-ars-learned-routes.json` shows ARS's own per-instance learned-routes view (`RouteServiceRole_IN_0`/`_1`) correctly holding `10.60.0.0/16` learned from the hub NVA (`10.40.1.4`, AS 65001), proving the hub-NVA-to-ARS eBGP leg was healthy. But `show-output/s1-revalidation-07-er-gateway-bgp-peer-status-poll2.json` and `s1-revalidation-08-er-gateway-learned-routes-poll2.json`, captured in the same round, show the gateway still at `routesReceived: 0` from both ARS peers and no `10.60.0.0/16` in its learned-routes table (expected at that moment, since branch-to-branch was off).

In short: at no point in this lab, with branch-to-branch off or on, does the ER Gateway's own BGP state ever show it receiving `10.60.0.0/16` from ARS. The §7.4 claim that "ARS reflects `10.60.0.0/16` to the ER Gateway" was based on ARS's learned-routes view alone and did not check the gateway side; it does not hold up.

**Root-cause hypothesis (best-supported, not confirmed by a new live test):** the ER Gateway's two BGP sessions to the ARS peers were already long-established before `allowBranchToBranchTraffic` was toggled to `true`. Comparing capture timestamps against each session's own `connectedDuration`: `s1-reconcile-02` was captured 2026-09-30 at approximately 13:10 with a `connectedDuration` of about 20h20m, placing session establishment at roughly 2026-09-29 16:50. `s1-revalidation-07` was captured 2026-09-29 at approximately 19:50 (git commit timestamp) with a `connectedDuration` of about 2h50m, placing establishment at roughly 2026-09-29 17:00 for the same peer pair. Both point to the same continuous, unbroken BGP session, established while branch-to-branch was still off, surviving uninterrupted through the later toggle to `true` and still running at the time of the last capture. Azure Route Server's `allowBranchToBranchTraffic` is a control-plane property change; nothing in the evidence, or in the public Route Server documentation (`azure-learn-microsoft_docs_search`/`microsoft_docs_fetch` reviewed 2026-09-30, "Azure Route Server support for ExpressRoute and Azure VPN" and "Troubleshoot Azure Route Server issues"), states that toggling it forces already-established BGP sessions to reconverge or re-advertise. The working theory is that the reflected route is only pushed to a peer during that peer's own next route refresh or session re-establishment, and an already-Connected, long-uptime session simply never got one after the flag flipped.

**This is a hypothesis, not a confirmed fix.** No new live test was run this round to prove it (per the live-lab policy, no live commands were issued for this analysis). The recommended next diagnostic step, to be run under a proper Tank/Niobe lease, is: with branch-to-branch already `true`, disable and re-enable the ARS-to-hub-NVA BGP peering (or otherwise force the ER Gateway's two BGP sessions to ARS to reset, e.g. via a gateway BGP session reset if the CLI/REST surface supports one), then re-capture `list-bgp-peer-status` and `list-learned-routes` on the gateway. If `routesReceived` goes nonzero and `10.60.0.0/16` appears, that confirms a stale-session/no-reconverge behavior specific to already-established sessions predating the flag change. If it still doesn't appear, the root cause lies elsewhere (e.g. an ARS-side reflection defect independent of session age) and needs further isolation.

**Practical consequence for this lab's claims:** the "after option-1 fix" MSEE route tables correctly show no `10.60.0.0/16`, because the ER Gateway itself never learned that route from ARS, regardless of the branch-to-branch setting's value at capture time. This means **Option 1 (S1), as evidenced in this lab, has not been proven to deliver a working on-prem-to-spoke data path over the real ExpressRoute circuit.** The CE-to-spoke ping tests documented earlier in this lab (§7.1 through §7.5) used the simulated CE harness connected to the hub via direct VNet peering (`vnet-onprem-sim`, deviation #1), not the real MSEE/ExpressRoute path, specifically because that path was a workaround for defects unrelated to this one; those tests never exercised, and therefore never confirmed, the real ER-circuit hop that this section is about. Until the diagnostic step above is run and shows a nonzero `routesReceived` on the gateway from ARS, S1's real ExpressRoute-circuit data path should be treated as unverified, not working.

---

## 8. Route-collection checklist (Niobe) — per scenario

Both scenarios need independent captures because the expected results at the ER Gateway/circuit layer diverge (S1: full route learned + delivered; S2: full route advertised but not delivered).

| # | Layer | Command | S1 expected | S2 expected |
|---|---|---|---|---|
| 1 | ER Gateway learned routes | `az network vnet-gateway list-learned-routes -g <rg> -n <ergw>` | `10.60.0.0/16` present, next hop = ARS/hub NVA | Same prefix may appear as advertised-only; verify learned-routes table too (should NOT show a usable next hop toward spoke workload) |
| 2 | ER Gateway advertised routes | `az network vnet-gateway list-advertised-routes -g <rg> -n <ergw> --peering-name AzurePrivatePeering` | `10.60.0.0/16` advertised | `10.60.0.0/16` advertised (summarized-prefix effect) |
| 3 | ER Circuit route tables | `az network express-route list-route-tables -n <circuit> -g <rg> --peering-name AzurePrivatePeering -o json` (always `-o json`) | Confirms MSEE-side view matches gateway advertisement | Same — confirms MSEE sees the summarized `/16`, decoupled from data-path reality |
| 4 | Megaport MCR | Pull BGP neighbor/session detail from the VXC resource (looking-glass endpoint is unreliable) | Session Established | Session Established (unaffected by S1/S2 choice) |
| 5 | ARS learned routes | `az network routeserver peering list-learned-routes -g <rg> --routeserver <ars> --peering-name hub-nva` | `10.60.0.0/16` learned from hub NVA | N/A — ARS not in the S2 path |
| 6 | ARS advertised routes | `az network routeserver peering list-advertised-routes -g <rg> --routeserver <ars> --peering-name hub-nva` | Confirms ARS→ERGW propagation | N/A |
| 7 | Hub NVA (BIRD + Linux FIB) | `birdc show route` / `birdc show protocols` / `ip route get 10.60.1.x` via `az vm run-command` | `10.60.0.0/16` static + exported to ARS **and** `ip route get 10.60.1.x` resolves `via 10.60.0.4` | BIRD not deployed/active for S2's downlink path — confirms nothing is injecting the route |
| 8 | Hub NVA NIC effective routes | `az network nic show-effective-route-table` | Shows spoke-nva peered-subnet route | Same (peering-derived route unchanged by S2) |
| 9 | Data-plane probe | ICMP/TCP from simulated on-prem (172.40.100.0/24) to `snet-workload` probe VM (10.60.1.x) | **Succeeds** | **Fails** (times out / no route) — this is the evidence artifact for §6.3 |
| 10 | Data-plane control | Same probe to `snet-spoke-nva`'s own IP (already-peered subnet) | Succeeds (both scenarios) | Succeeds (both scenarios) — proves the peered-subnet path itself was never broken, isolating the failure to the non-peered workload subnet only |

---

## 9. Resiliency analysis (mandatory)

**Framing for a lab reader:** this section is written to the "acceptable for a lab" standard — a single-region, single-circuit, single-AZ-gateway topology, chosen deliberately to keep the lab minimal and focused on the peering/advertisement mechanism. A production reader should evaluate: (a) dual-circuit/dual-MCR resiliency (see `dual-er-symmetry` skill and `vwan-dual-er-symmetric` lab for the pattern), (b) zone-redundant ARS/NVA placement, (c) whether a single placeholder NVA per side is acceptable for a production firewall tier (it is not — real deployments need HA pairs).

| # | Failure mode | Blast radius (Azure side) | Blast radius (on-prem side) | Firewall-in-path consequence | Failover time | Operator action |
|---|---|---|---|---|---|---|
| F1 | Hub NVA VM failure | S1: ARS loses its only eBGP peer → learned route for `10.60.0.0/16` ages out/withdraws at BGP hold-timer expiry; downlink to workload subnet fails. Peered-subnet path (hub↔spoke NVA subnets) also breaks since hub NVA is the only device in `snet-hub-nva`. S2: unaffected for the advertisement (property-driven, no NVA dependency) but S2 never had a working data path anyway. | On-prem BGP session to ARS unaffected directly, but the `10.60.0.0/16` route (S1) disappears from on-prem's table after hold-timer expiry (default 90s–180s depending on BGP timers configured). | N/A — NVA is a placeholder, not a stateful filter; no asymmetric-return risk since there's only one NVA per side. | Minutes (BGP hold-timer + redeploy/restart of VM) — no HA pair in v1. | Redeploy/restart hub NVA VM; re-establish BGP session; verify ARS learned-routes repopulate. |
| F2 | Spoke NVA VM failure | `snet-workload`'s only egress (UDR next hop) goes dark — full loss of hub/on-prem reach for the workload subnet. Peered-subnet link (hub↔spoke NVA subnets) also breaks (single device). | On-prem loses reach to `10.60.1.0/24` entirely (both scenarios); reach to `10.60.0.0/27` (spoke NVA subnet itself) also lost since the NVA IP is the only host there. | N/A (placeholder). | Minutes — no HA pair. | Redeploy/restart spoke NVA VM; verify UDR next hop responds (ping/traceroute from workload probe). |
| F3 | ARS failure (S1 only) | Loss of the eBGP session hub-NVA↔ARS → `10.60.0.0/16` route stops being refreshed/propagated to ER Gateway; existing learned route on the gateway ages out at BGP hold-timer. Data path to workload subnet fails (same end state as advertisement never having existed). | On-prem loses the `/16` route after hold-timer; falls back to whatever the baseline peered-subnet advertisement provides (`/27` only, if still present) or nothing. | N/A. | Minutes (ARS control-plane restart is Microsoft-managed; ARS itself has platform-level redundancy, but this specific BGP session/peering config does not). | Verify ARS health via `az network routeserver show`; re-add BGP peering to hub NVA if the peering object itself was affected (not just the VM). |
| F4 | ER Gateway failure | Total loss of the ER path for both scenarios — `GatewaySubnet` resource itself down. Both S1 and S2 lose all on-prem↔Azure reachability, including the previously-working peered-subnet path. | Total loss of Azure reach via this circuit. | N/A. | `ErGw1AZ` is a single-instance SKU (no active-active) — failover is a **platform-managed** restart, typically minutes, but there is no redundant instance to fail over to within this gateway. | None available in v1 (single gateway, single circuit) — escalate to Microsoft support if platform-level; no self-service mitigation short of a second gateway/circuit (see patch catalogue). |
| F5 | BGP session failure (hub-NVA↔ARS/CE, S1) | Config drift, MTU mismatch, or NVA-side BIRD crash. **Confirmed live 2026-09-29, root-caused and closed across two rounds (§7.1 Defects 3a/3b):** all 3 hub-NVA sessions initially flapped Established↔Idle from Defect 1's RIB churn (3a, closed by the `onlink` static-route fix); one session (`ce_onprem`/`hub_nva`) kept flapping afterward due to a CE-side timer mismatch never updated to match the hub's P4 fix (3b, closed by aligning `vm-ce-onprem`'s `hub_nva` block to `180/60`). | Same as F3, for the ARS-facing sessions; for the CE-facing session, on-prem loses the route after its own (now-aligned) 180s hold timer. | N/A. | Both defects closed 2026-09-29; hold/keepalive `180/60` on all 3 hub-NVA sessions **and** on `vm-ce-onprem`'s matching `hub_nva` block (§7.1/§7.2). | `birdc show protocols` on **both** ends of any session that uses a `bird.conf`-to-`bird.conf` peer (not just the hub); if a flap recurs, diff both sides' timers/config for the affected peer before assuming a new root cause. |

### Mitigation patch catalogue (dormant — apply only on Jose's explicit instruction)

| Patch | Mitigates | Delta | Cost impact | Residual gap |
|---|---|---|---|---|
| P1 | F1/F2 (single NVA per side) | Add a second NVA VM per side + Azure Load Balancer (or availability set) in front; BIRD/ARS peering moves to a floating/LB'd address | +2 B-series VMs, +2 Standard LBs (~low, still lab-scale cost) | Stateful-session symmetry not addressed (placeholder NVAs aren't stateful, so this is a non-issue here — but note for anyone reusing this pattern with a real firewall) |
| P2 | F3 (ARS single point for S1's data path) | No native ARS HA knob beyond platform-managed; mitigation is a second ARS peer session from a standby hub NVA, not a second ARS instance | +1 NVA VM (standby BIRD peer) | Adds complexity disproportionate to a teaching lab; recommended only if S1 is promoted beyond lab scope |
| P3 | F4 (single ER Gateway/circuit) | Second `ErGw1AZ` + second Megaport VXC/circuit, per `dual-er-symmetry` skill pattern | Roughly doubles gateway + circuit + MCR-port cost | Requires the symmetry-lever design from that skill (per-circuit advertisement scope) to avoid new asymmetry bugs — out of scope for this lab's teaching point |
| P4 | F5 (BGP flap on burstable SKU / CE timer asymmetry) | **APPLIED 2026-09-29 in two parts, both closed:** (1) hold/keepalive raised 60/20→180/60 on all 3 hub-NVA BGP protocols (Defect 3a insurance, hub side only); (2) `vm-ce-onprem`'s `hub_nva` block aligned to the same 180/60 (Defect 3b fix, closed round 5). Root cause for the residual flap was CE-side drift, not the SKU — no SKU change was needed. | None (config-only) | None outstanding for this lab. If a *future* lab reuses this pattern, remember: any BGP timer change on a `bird.conf`-to-`bird.conf` peer must be applied on both VMs together (§7.2). |

---

## 10. Hand-off spec for Tank

**Resources (region: swedencentral unless noted):**

| Resource | Type | Key properties |
|---|---|---|
| vnet-hub | Microsoft.Network/virtualNetworks | 10.40.0.0/16; `summarizedGatewayPrefixes` set per §6.2 (S2 toggle) |
| vnet-sap-rise | Microsoft.Network/virtualNetworks | 10.60.0.0/16 |
| vnet-onprem-sim | Microsoft.Network/virtualNetworks | 172.40.100.0/24; simulated CE harness, fully VNet-peered to `vnet-hub` |
| 3× subnets in vnet-hub | subnets | GatewaySubnet 10.40.0.0/27, RouteServerSubnet 10.40.0.32/27, snet-hub-nva 10.40.1.0/27 |
| 2× subnets in vnet-sap-rise | subnets | snet-spoke-nva 10.60.0.0/27, snet-workload 10.60.1.0/24 |
| snet-ce-onprem in vnet-onprem-sim | subnet | 172.40.100.0/25; hosts `vm-ce-onprem` |
| peer-hub-to-sap-rise / peer-sap-rise-to-hub | vnetPeerings | Subnet-scoped per §3 exact CLI block — deploy via `az cli` or `az rest` if Bicep/TF provider lacks `peerCompleteVnets`/`localSubnetNames` support yet (verify provider version before assuming ARM/Bicep parity with CLI) |
| peer-onprem-sim-to-hub / peer-hub-to-onprem-sim | vnetPeerings | Full VNet peering, `allowForwardedTraffic=true` both ways; this is the CE harness deviation, not part of the subnet-scoped mechanism under test |
| ergw-sap-rise | virtualNetworkGateways | SKU `ErGw1AZ`, ExpressRoute type, 1 Standard PIP |
| er-circuit-sap-rise | expressRouteCircuits | Megaport MCR provider, 50 Mbps, MeteredData, `AzurePrivatePeering` only |
| Megaport MCR + single VXC | (Megaport provider) | Do not manually configure Azure private peering — Megaport auto-assigns ASN/peering subnets per `megaport-api-auth` skill note; read back `resources.csp_connection[0].interfaces[0].bgpConnections` |
| ars-hub | Microsoft.Network/virtualHubs or routeServers (ARS resource) | Default SKU, `RouteServerSubnet`, branch-to-branch **enabled** (`allowBranchToBranchTraffic = true` — corrected 2026-09-29, §6.1 Defect A) |
| ars-hub-nva-peering | routeServerBgpConnections | Peer to hub NVA private IP, ASN 65001 |
| nsg-hub-nva / nsg-spoke-nva | networkSecurityGroups | Rule tables in §4; on the hub side this explicitly includes workload-subnet and onprem-sim data-plane Allows, and on the spoke side this now also includes the forwarded-CE Allow for `172.40.100.0/24` |
| rt-spoke-workload / rt-spoke-nva-return | routeTables | `rt-spoke-workload`: `0.0.0.0/0` → VirtualAppliance → 10.60.0.4, associated to `snet-workload`; `rt-spoke-nva-return`: `172.40.100.0/24` → VirtualAppliance → 10.40.1.4, associated to `snet-spoke-nva` |
| rt-ce-onprem | routeTables | `10.60.0.0/16` → VirtualAppliance → 10.40.1.4, associated to `snet-ce-onprem` only — **added 2026-09-29 (§5, Defect C)**, harness-only, simulated-CE deviation |
| vm-hub-nva | Standard_B2als_v2, IP-fwd NIC | cloud-init: `cloud-init-nva-bird.yaml`; final `bird.conf` must keep `static_bgp` exported to ARS **and** to the Linux kernel FIB, but must not re-export ARS-learned routes (§7.4) |
| vm-spoke-nva | Standard_B2als_v2, IP-fwd NIC | cloud-init: `cloud-init-nva-base.yaml` (no BIRD — §7) |
| vm-workload-probe | Standard_B2als_v2 | Plain Linux, diagnostic-only, no forwarding needed |
| vm-ce-onprem | Standard_B2als_v2 | Simulated CE / on-prem BGP speaker in `vnet-onprem-sim`, ASN 65000; direct peer of `vm-hub-nva` (§7.2) |

Two IaC toggles Tank needs as first-class variables (not separate deploys), mirroring the `dual-er-symmetry` skill's IaC.2 pattern:
- `var.scenario` (`"s1"` / `"s2"`) gating whether ARS BGP peering + hub-NVA BIRD config is active, or `summarizedGatewayPrefixes` is set on `vnet-hub`. Both can technically coexist for a joint capture, but default to mutually exclusive per §8's independent-capture design.
- `var.hub_nva_asn` / `var.spoke_nva_asn` as variables (65001/65002), not hardcoded, in case a future extension activates the spoke NVA's BGP.

---

## Open items I'm carrying forward

1. **Lab-card correction (§6.2):** `summarizedGatewayPrefixes` must be set on `vnet-hub`, not `vnet-sap-rise`. Recorded in the decision inbox.
2. **CLOSED 2026-09-29 — Simulated on-prem/CE realization.** The live lab uses `vnet-onprem-sim` + `vm-ce-onprem` (ASN 65000), fully VNet-peered directly to `vnet-hub`. This is now a documented deviation, not an open question (§3, §5, §10).
3. **CORRECTION 2026-09-29 — S1 stage-4 failure is now a spoke-side Azure routing/NSG gap, not a remaining hub/BGP problem.** Defects D/E were real and are now closed: the CE can reach the hub, and the hub Linux FIB now points `10.60.0.0/16` at `10.60.0.4`. The residual blocker is downstream of that: `nsg-spoke-nva` needs an explicit Allow for the original CE source prefix (`172.40.100.0/24`), and `snet-spoke-nva` needs its own return UDR for `172.40.100.0/24 -> 10.40.1.4` because the CE harness lives in a third VNet and subnet-scoped peering is not transitive. Full apply/verify spec: `.squad/decisions/inbox/trinity-s1-spoke-reachability-fix.md`.
4. **OPEN 2026-09-30, Defect H (§7.6): S1's real ExpressRoute-circuit data path is unverified.** Gateway-side evidence never shows the ER Gateway receiving `10.60.0.0/16` from ARS (`routesReceived: 0` in every capture, at every point in time, regardless of the `allowBranchToBranchTraffic` value). Best-supported hypothesis: the gateway's BGP sessions to ARS were already long-established before the flag was toggled to `true`, and the toggle does not force those sessions to reconverge or re-advertise. Recommended next diagnostic step: reset the ARS-to-hub-NVA BGP peering (or the gateway's BGP sessions to ARS) under a fresh Tank/Niobe lease and re-capture `list-bgp-peer-status` plus `list-learned-routes` on the gateway. Until that step is run and shows a nonzero route count, S1 has not been proven to work over the real ExpressRoute circuit; only the simulated-CE VNet-peering harness has been confirmed end-to-end.
