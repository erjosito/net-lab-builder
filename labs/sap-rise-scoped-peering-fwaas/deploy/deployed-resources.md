# Deployed Resources — sap-rise-scoped-peering-fwaas

**Deployed:** 2026-09-29
**Deployed by:** Tank (IaC Engineer), on explicit go-ahead from Jose Moreno
**IaC tool:** Terraform (`src/terraform/sap-rise-scoped-peering-fwaas/`)
**Status:** Live. BGP/control plane remains healthy, and Trinity's spoke-side F1/F2 Azure changes are now applied: `nsg-spoke-nva` has the exact new inbound allow for `172.40.100.0/24`, and `snet-spoke-nva` now has `rt-spoke-nva-return` with the narrow return route `172.40.100.0/24 -> VirtualAppliance -> 10.40.1.4`. Ordered verification steps 1-4 all passed, including the `nic-spoke-nva` effective route table showing the new route as `Active` alongside the existing `10.40.1.0/27 -> VNetPeering` entry. However, the authoritative step-5 CE ping to `10.60.0.4` still failed with `100% packet loss`, and the required fallback diagnostics were captured without attempting another fix. S1 data-plane closure therefore remains open with Trinity, not Niobe. Future multiline VM run-command applies in this lab should use the script-file `@file` pattern, not inline multiline strings from Windows PowerShell.

This file exists so Niobe (and anyone else running diagnostics) can target resources
directly without re-discovery. No secrets, subscription IDs, or service keys are
included below — use `<SUBSCRIPTION_ID>` as a placeholder wherever a full ARM
resource ID is shown.

## Core

| Item | Value |
|---|---|
| Resource Group | `rg-saprise-swedencentral` |
| Region | `swedencentral` |
| Tags | `lab=sap-rise-scoped-peering-fwaas`, `owner=jose`, `ephemeral=true` |
| Correlation ID | `7bb27d99` |

## Networking

| Item | Value |
|---|---|
| Hub VNet | `vnet-hub` (10.40.0.0/16) — `/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-saprise-swedencentral/providers/Microsoft.Network/virtualNetworks/vnet-hub` |
| Spoke VNet | `vnet-sap-rise` (10.60.0.0/16) — `/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-saprise-swedencentral/providers/Microsoft.Network/virtualNetworks/vnet-sap-rise` |
| Simulated on-prem VNet | `vnet-onprem-sim` (172.40.100.0/24) — `/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-saprise-swedencentral/providers/Microsoft.Network/virtualNetworks/vnet-onprem-sim` |
| Peering scope | Subnet-scoped (`peer_complete_virtual_networks_enabled = false`), `snet-hub-nva` ↔ `snet-spoke-nva` only — feature was available on this subscription, no allowlisting blocker encountered |
| Route Server | `ars-hub` — `/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-saprise-swedencentral/providers/Microsoft.Network/virtualHubs/ars-hub` |
| ARS peer IPs (BGP, ASN 65515) | `10.40.0.36`, `10.40.0.37` |
| ARS branch-to-branch | **`allowBranchToBranchTraffic = true`** as of 2026-09-29 S1 data-plane fix apply. Verified `provisioningState: Succeeded`. |
| ARS public IP | `pip-ars-hub` — `135.116.203.23` |
| CE simulation route table | `rt-ce-onprem` with `route-to-spoke`: `10.60.0.0/16 -> VirtualAppliance -> 10.40.1.4`, associated to `vnet-onprem-sim/snet-ce-onprem` on 2026-09-29 |
| Spoke NVA return route table | `rt-spoke-nva-return` with `route-to-onprem-sim-via-hub`: `172.40.100.0/24 -> VirtualAppliance -> 10.40.1.4`, associated to `vnet-sap-rise/snet-spoke-nva` on 2026-09-29 |
| S2 toggle (`summarizedGatewayPrefixes`) | Present in Terraform as a separate flag (`enable_summarized_gateway_prefixes`), currently **`false`** (S1 baseline active). Flip to `true` and re-apply to activate S2 on `vnet-hub` per design.md §6.2's corrected placement. |

## ExpressRoute + Megaport

| Item | Value |
|---|---|
| ER Circuit | `er-sap-rise`, SKU/peering location **Frankfurt** (see deviation note below) |
| ER Gateway | `ergw-sap-rise`, SKU `ErGw1AZ`, `provisioningState: Succeeded` |
| ER Gateway public IP | Auto-assigned by Azure ("HOBO" IP) since azurerm v4.81 no longer allows explicit assignment. Not independently visible via `az network public-ip list`; the gateway's own `ipConfigurations` show the binding is managed internally by Azure. Gateway is confirmed `Succeeded`. |
| Megaport MCR UID | `ee8c1d71-a901-48a7-91ab-67293b239dd9` (location: Equinix Frankfurt FR5) |
| Megaport VXC UID | `72a59981-2bfe-4c87-8440-b0d5981c06cf` |
| Megaport MCR ASN | `64512` |
| Azure peering ASN | `12076` |
| VLAN | `2063` |

## Virtual Machines

| VM | Role | Private IP | ASN | BGP status (at deploy time) |
|---|---|---|---|---|
| `vm-hub-nva` | Hub NVA (BIRD) | `10.40.1.4` | 65001 | Peers with ARS (`azure_rs_1`, `azure_rs_2`) and CE (`ce_onprem`). **2026-09-29 round-3 update:** Trinity's final root-cause fix (`protocol kernel` block `export all;` → `export none;`, stopping BIRD from pushing its full RIB, including overlapping ARS-origin routes for the shared RouteServerSubnet space, into the guest kernel table) was applied by Tank and verified. This confirmed defect is fixed: `ip route show` now shows only clean Azure-fabric-derived entries, and both `azure_rs_1`/`azure_rs_2` stayed continuously `Established` (since ~14:56/14:55) with confirmed bidirectional keepalive traffic across a 4-poll, ~12-minute verification window. **However, the overall pass bar (all three sessions Established simultaneously on every poll) was NOT met**. `ce_onprem` independently cycled Idle → Active → Established → Idle during the same window (`Connection reset by peer`, then `Hold timer expired`), with zero port-179 traffic captured to/from the on-prem-sim IP during a 60s tcpdump taken while it was down. This looks like a second, separate mechanism affecting only `ce_onprem`, not the ARS kernel-poisoning defect Trinity's fix targeted. Escalated back to Trinity per `.squad/decisions/inbox/tank-s1-final-verification.md`. **S1 was not yet ready for Niobe re-validation at that point.** **2026-09-29 data-plane follow-up:** `sysctl -p /etc/sysctl.d/99-ip-forward.conf` was re-applied via `run-command`; `/proc/sys/net/ipv4/ip_forward` now reads `1`. |
| `vm-spoke-nva` | Spoke NVA (forwarding/NAT) | `10.60.0.4` | 65002 | IP forwarding + NAT only per design.md — no BGP required on this node. |
| `vm-workload-probe` | Workload test VM | `10.60.1.4` | n/a | UDR on `snet-workload` forces hub/on-prem-bound traffic via `vm-spoke-nva`. |
| `vm-ce-onprem` | Simulated on-prem CE (BIRD) | `172.40.100.4` | 65000 | Peers with `vm-hub-nva`, advertising `172.40.100.0/24`. **2026-09-29 round-5 update:** Trinity's final root-cause fix for Defect 3b applied by Tank. The `hub_nva` protocol block on this VM (which had never been updated to match the hub's round-1 timer fix) had its `hold time 60; keepalive time 20;` changed to `hold time 180; keepalive time 60;`, matching the hub's `ce_onprem` block. This removed the zero-margin mismatch that was causing the CE to self-expire its hold timer against the hub's 60s keepalive cadence. Verified via a 4-poll, ~14.5-minute window on both VMs: all three sessions (`ce_onprem`/`hub_nva`, `azure_rs_1`, `azure_rs_2`) stayed continuously `Established` with an unchanged `Since` timestamp throughout, zero drops. **PASS.** Backed up on the VM as `/etc/bird/bird.conf.bak-defect3b`. **2026-09-29 data-plane follow-up:** the new UDR on `snet-ce-onprem` is visible in the CE NIC effective route table (`10.60.0.0/16 -> VirtualAppliance -> 10.40.1.4`), but the first required data-plane control ping from this VM to `10.60.0.4` still failed with `5 packets transmitted, 0 received, 100% packet loss`. Per Trinity's lockout instruction, testing stopped there and this was escalated back to Trinity without further changes. |

VM size: `Standard_B2s_v2` (fallback SKU — see deviation note).

VM management: no Bastion deployed; all VM access is via `az vm run-command invoke` (documented deviation). For multiline guest scripts, the standard pattern is now to write the script to a repo file first and invoke it with `--scripts @<file>`; this avoids the heredoc and newline mangling seen with inline multiline strings from Windows PowerShell.

## bird.conf revision history (`vm-hub-nva`)

| Revision | Date | Author | Notes |
|---|---|---|---|
| v1 (original deploy) | 2026-09-29 | Tank | `route 10.60.0.0/16 via 10.60.0.4;` (recursive, unresolvable), `ce_onprem` `export none;`, `hold time 60; keepalive time 20;`. Backed up on the VM as `/etc/bird/bird.conf.bak.20260929`. |
| v2 (S1 fix) | 2026-09-29 | Trinity (design), Tank (applied) | `route 10.60.0.0/16 via 10.60.0.4 % eth0 onlink;` (BIRD 2.0.8-compatible equivalent of Trinity's spec — see deviation note in `.squad/decisions/inbox/tank-s1-fix-applied.md`), `ce_onprem` `export where proto = "static_bgp";`, `hold time 180; keepalive time 60;` on all three BGP protocols. Route-resolution and export-none defects confirmed fixed; BGP session flap persists — CPU-credit theory ruled out. Escalated to Trinity, not yet handed to Niobe. |
| v3 (S1 final flap fix, round 3) | 2026-09-29 | Trinity (design), Tank (applied) | `protocol kernel` block: `export all;` → `export none;`, applied via `az vm run-command invoke` + `birdc configure` (non-disruptive reload, no restart). Confirmed via `ip route show`: guest kernel table now contains only Azure-fabric-derived entries, no ARS-origin `10.40.0.32/27` routes. `azure_rs_1`/`azure_rs_2` confirmed continuously `Established` with bidirectional keepalive traffic across a 4-poll/~12-minute window and a 60s tcpdump. This defect is closed. `ce_onprem` still flaps independently (`Connection reset by peer`, `Hold timer expired`) — a second, separate mechanism, not yet root-caused. Full poll table and evidence in `.squad/decisions/inbox/tank-s1-final-verification.md`. No further changes to `vm-hub-nva`'s `bird.conf` after v3 — it remains correct as-is. |
| v4 (targeted CE reachability re-open, attempted) | 2026-09-29 | Trinity (design), Tank (attempted) | Trinity approved a one-line, non-BGP semantic reopen of the `protocol kernel` block only: `export none;` → `export where proto = "static_bgp";` so the already-correct static spoke route would be exported into the Linux forwarding table. Two new NSG rules were created first, then the hub run-command was invoked with the exact mechanical replace intent. The invocation returned a Python `SyntaxError` before `birdc configure`, so no effective config change was confirmed on the VM. Stage 2 verification immediately failed afterward: `birdc show route 10.60.0.0/16 all` still showed `static_bgp`, but `ip route get 10.60.1.4` still resolved `via 10.40.1.1 dev eth0 src 10.40.1.4`. Per Trinity's stop rule, stages 3-7 were not run. Evidence: `show-output/s1-ce-reachability-fix-20260929T165357Z/`. |
| v5 (targeted CE reachability re-open, corrected retry) | 2026-09-29 | Trinity (design), Tank (applied and verified) | Re-ran **only** Trinity's corrected Defect E script on `vm-hub-nva`, using the same one-line semantic change: `export none;` → `export where proto = "static_bgp";`. The run-command invocation itself completed successfully and no Python syntax error recurred. However, the required immediate stage-2 verification still failed: `birdc show route 10.60.0.0/16 all` continued to show the prefix from `static_bgp`, but `ip route get 10.60.1.4` still resolved `via 10.40.1.1 dev eth0 src 10.40.1.4`, not via `10.60.0.4 dev eth0`. Net result: the corrected retry removed the shell-escaping failure, but the intended Linux FIB effect was still **not** functionally verified. Per Trinity's stop rule, stages 3-7 were not run. Evidence: `show-output/s1-ce-reachability-fix-retry-20260929T170200Z/`. |
| v6 (targeted CE reachability re-open, block-aware retry-2) | 2026-09-29 | Trinity (design), Tank (applied and verified) | Re-ran the latest Defect E script exactly as handed off, including the block-aware regex replace, `bird -p -c /etc/bird/bird.conf`, `birdc configure check`, `birdc configure`, post-edit `grep -n -A6 "^protocol kernel"`, `ip route show 10.60.0.0/16`, `ip route flush cache`, and `ip route get 10.60.1.4`. The Azure run-command wrapper returned `ProvisioningState/succeeded`, but the raw output contained **no stdout at all** from those inner commands, so the edit was not proven to have landed. Immediate stage-2 verification still failed: `birdc show route 10.60.0.0/16 all` showed the `static_bgp` route, `ip route show 10.60.0.0/16` produced no line, and `ip route get 10.60.1.4` still resolved `via 10.40.1.1 dev eth0 src 10.40.1.4`. Per Trinity's stop rule, stages 3-7 were not run. Evidence: `show-output/s1-ce-reachability-fix-retry2-20260929T171313Z/`. |
| v7 (targeted CE reachability re-open, file-based retry-3) | 2026-09-29 | Trinity (design), Tank (applied and verified) | Re-ran the same approved block-aware Defect E logic, but changed the invocation method only: wrote the guest bash script to `deploy/scripts/hub-bird-kernel-export-fix.sh` and invoked it with `az vm run-command invoke --scripts @file` from Windows PowerShell. This avoided the inline-string quoting and newline mangling that had produced empty run-command output on v6. The apply output was finally non-empty and contained the required proof points: `bird -p` configuration parse success, `birdc configure check`, `birdc configure` reporting `Reconfigured`, post-edit `grep -n -A6 "^protocol kernel"` showing `export where proto = "static_bgp";`, `ip route show 10.60.0.0/16` showing `via 10.60.0.4 dev eth0`, and `ip route get 10.60.1.4` resolving `via 10.60.0.4 dev eth0`. Ordered verification then advanced further than any prior retry: **stage 2 PASS**, **stage 3 PASS** (`vm-ce-onprem` ping `10.40.1.4`, `0% packet loss`), then **stage 4 FAIL** (`vm-ce-onprem` ping `10.60.0.4`, `100% packet loss`). Per the stop rule, this is the authoritative stop point; the investigation remains with Trinity. Evidence: `show-output/s1-ce-reachability-fix-retry3-20260929T172057Z/`. |

## bird.conf revision history (`vm-ce-onprem`)

| Revision | Date | Author | Notes |
|---|---|---|---|
| v1 (original deploy) | 2026-09-29 | Tank | `hub_nva` protocol block: `hold time 60; keepalive time 20;` — never updated when the hub's `ce_onprem` block was fixed in round 1, leaving the two ends of the same session on mismatched timers. |
| v2 (Defect 3b final fix, round 5) | 2026-09-29 | Trinity (design), Tank (applied) | `hub_nva` protocol block: `hold time 60;` → `hold time 180;`, `keepalive time 20;` → `keepalive time 60;`, scoped via `sed` to the `hub_nva` block only and applied with `birdc configure` (no service restart). Root cause confirmed by Trinity's correlated `journalctl`/`tcpdump` analysis: the negotiated hold time was the lower of the two sides (60s), leaving zero margin against the hub's 60s keepalive cadence, so the CE was self-expiring its own hold timer and initiating every teardown. Backed up on the VM as `/etc/bird/bird.conf.bak-defect3b`. **This closes Defect 3b — the last open defect in the multi-round S1 BGP investigation (Defects 1, 2, 3a, 3b all now confirmed fixed).** |

## NSG rules — `nsg-hub-nva`

Trinity's round-2 flap diagnosis flagged a suspected gap: no inbound-179 Allow rule from `172.40.100.0/24` (the simulated on-prem CE's subnet) on `nsg-hub-nva`, since `design.md` §4's NSG table only listed the ARS and spoke-NVA rows. **Live check confirms this rule already exists and has been deployed since the original Terraform apply** — `Allow-OnpremSim-BGP-In`, priority 120, source `172.40.100.0/24`, destination `VirtualNetwork`, port 179/TCP, Allow (see `src/terraform/sap-rise-scoped-peering-fwaas/azure-nsg.tf`). No new NSG rule was created; adding a second, redundant rule for the same traffic was skipped as unnecessary. Only `design.md`'s table was out of date and has now been corrected to add this row (renumbering the mgmt-SSH placeholder row to priority 130 to keep it last before the deny-all backstop). Full detail and the live BGP/tcpdump evidence gathered in the same session are in `.squad/decisions/inbox/tank-s1-diagnostics-round2.md`.

As of the targeted CE reachability reopen on 2026-09-29, `nsg-hub-nva` also has these new additive inbound data-plane rules, both created successfully and verified live in stage 1:

| Rule | Priority | Source | Destination | Protocol | Purpose |
|---|---|---|---|---|---|
| `Allow-Workload-In` | 115 | `10.60.1.0/24` | `VirtualNetwork` | `*` | Allow return traffic from the workload subnet to the hub NVA |
| `Allow-OnpremSim-Data-In` | 125 | `172.40.100.0/24` | `VirtualNetwork` | `*` | Allow non-BGP data-plane traffic from the simulated on-prem CE subnet to the hub NVA |

## NSG rules — `nsg-spoke-nva`

Trinity's 2026-09-29 spoke-side follow-up identified that forwarded traffic arriving from the hub
keeps the original CE source prefix, so the spoke-side NSG needed an explicit inbound allow for
`172.40.100.0/24`. Tank applied that exact additive rule and verified it live before continuing:

| Rule | Priority | Source | Destination | Protocol | Purpose |
|---|---|---|---|---|---|
| `Allow-OnpremSim-Forwarded-In` | 105 | `172.40.100.0/24` | `VirtualNetwork` | `*` | Allow forwarded CE-originated traffic to the spoke NVA without relying on source rewrite |

## Known deviations from design.md (see `.squad/decisions/inbox/tank-sap-rise-deploy.md` for full rationale)

1. Simulated on-prem CE deployed as an Azure VM with full VNet peering, not a physical/Megaport MVE CE.
2. No Azure Bastion; VM access via `run-command` only.
3. **Megaport MCR + ExpressRoute peering location moved from Stockholm to Frankfurt** — this Megaport account is not entitled to the Sweden market.
4. VM SKU fallback to `Standard_B2s_v2` (from `Standard_B2als_v2`) due to a transient `AllocationFailed` capacity issue in `swedencentral`.

## S1 BGP investigation — final status (2026-09-29, round 5)

All four defects found across this multi-round investigation are now confirmed fixed and stable:

1. **Defect 1** (route-resolution / `export none;` on hub) — fixed in v2, round 1.
2. **Defect 2** (CE-side session flap, initial timer mismatch symptom) — investigated across rounds 1-2.
3. **Defect 3a** (hub `protocol kernel export all;` poisoning the guest kernel table with ARS-origin routes) — fixed in v3, round 3.
4. **Defect 3b** (CE-side `hub_nva` block never updated to match the hub's round-1 timer fix, causing a zero-margin hold-timer mismatch) — fixed in v2 (CE), round 5, this update.

Strict 4-poll/~14.5-minute verification on round 5 shows all three sessions (`ce_onprem`/`hub_nva`, `azure_rs_1`, `azure_rs_2`) `Established` simultaneously on every poll, no drops. **S1 is ready for Niobe's full re-validation.**

## S1 data-plane follow-up after Niobe re-validation (2026-09-29)

Trinity's consolidated A/B/C fix spec was applied exactly, in order, without touching either VM's
`bird.conf` again:

1. **Defect A, ARS branch-to-branch:** `allowBranchToBranchTraffic` flipped to `true`, verified
   `Succeeded`. `ergw-sap-rise` now shows `routesReceived > 0` from both ARS peers, and
   `10.60.0.0/16` is present in learned routes.
2. **Defect B, hub NVA forwarding:** `sysctl -p /etc/sysctl.d/99-ip-forward.conf` re-applied on
   `vm-hub-nva`; `/proc/sys/net/ipv4/ip_forward` confirmed `1`.
3. **Defect C, CE-simulation UDR:** `rt-ce-onprem` created and associated to
   `vnet-onprem-sim/snet-ce-onprem`; effective route table on `nic-ce-onprem` confirms
   `10.60.0.0/16 -> VirtualAppliance -> 10.40.1.4`.

**Current confirmed state:** control plane stays correct after A/B/C, including a final post-fix
`ergw-sap-rise` learned-routes check that still contains `10.60.0.0/16`. **However, the real
data-plane pass bar still fails**: from `vm-ce-onprem`, the first required control ping to
`10.60.0.4` returned `5 packets transmitted, 0 received, 100% packet loss`. Per Trinity's
instruction to stop on first failed expected verification result, the workload-probe ping was not
attempted and no alternative fix was improvised. Raw evidence is captured under
`show-output/s1-dataplane-fix-20260929T163250Z/`.

## S1 CE reachability targeted re-open (2026-09-29, Trinity-approved D1/D2/E)

Trinity then issued a narrowly scoped follow-up spec for two NSG defects plus one hub-only
`bird.conf` reopen that was explicitly **not** new BGP work:

1. **Defect D1:** created `Allow-OnpremSim-Data-In` on `nsg-hub-nva`, priority `125`, source
   `172.40.100.0/24`.
2. **Defect D2:** created `Allow-Workload-In` on `nsg-hub-nva`, priority `115`, source
   `10.60.1.0/24`.
3. **Defect E:** attempted the approved one-line `protocol kernel` change on `vm-hub-nva` so only
   `static_bgp` would be exported into the Linux kernel FIB.

Verification was run in Trinity's required order and stopped at the first failed expected result:

- **Stage 1:** PASS. Both NSG rules exist with the expected source prefixes and priorities.
- **Stage 2:** FAIL. The hub still resolves `ip route get 10.60.1.4` via the Azure fabric default
  gateway, not via the spoke NVA:
  `10.60.1.4 via 10.40.1.1 dev eth0 src 10.40.1.4`
- **Stages 3-7:** not run, per stop-on-first-failure instruction.

The first hub apply command's raw run-command output showed a Python `SyntaxError` before
`birdc configure`, so that targeted reopen was not confirmed effective. I then re-ran **only** the
corrected Defect E script from Trinity's updated hand-off. That retry invocation completed
successfully, but the required stage-2 hub route verification still failed with the same effective
forwarding result:
`10.60.1.4 via 10.40.1.1 dev eth0 src 10.40.1.4`

Per the same stop-on-first-failure rule:

- **Stage 2:** FAIL again on the corrected retry.
- **Stages 3-7:** still not run.

Tank then ran a third, exact retry using Trinity's block-aware regex script and the stronger
stage-2 check (`ip route show` plus `ip route flush cache` before `ip route get`). That retry also
stopped at stage 2:

- **Apply command:** returned `ProvisioningState/succeeded`, but its raw stdout/stderr was empty, so
  there is still no captured `bird -p`, `birdc configure check`, `birdc configure`, or post-edit
  `grep -n -A6 "^protocol kernel"` evidence proving the edit landed.
- **Stage 2:** FAIL again. `birdc show route 10.60.0.0/16 all` still showed the `static_bgp`
  route, `ip route show 10.60.0.0/16` produced no kernel FIB line, and `ip route get 10.60.1.4`
  still resolved `via 10.40.1.1 dev eth0 src 10.40.1.4`.
- **Stages 3-7:** still not run.

This remains escalated back to Trinity, not Niobe. Raw evidence is now captured under all three:
- `show-output/s1-ce-reachability-fix-20260929T165357Z/`
- `show-output/s1-ce-reachability-fix-retry-20260929T170200Z/`
- `show-output/s1-ce-reachability-fix-retry2-20260929T171313Z/`

Tank then changed **only the invocation method**, not the Defect E edit semantics, for a fourth
attempt:

- Wrote the exact bash apply script to
  `deploy/scripts/hub-bird-kernel-export-fix.sh`
- Invoked it with
  `az vm run-command invoke -g rg-saprise-swedencentral -n vm-hub-nva --command-id RunShellScript --scripts @<local-script-file>`
- Captured full non-empty stdout this time, proving the live file changed and BIRD reloaded cleanly

Authoritative ordered verification on retry-3 then reached a new stop point:

- **Stage 2:** PASS. `birdc show route 10.60.0.0/16 all` still shows `static_bgp`; `ip route show 10.60.0.0/16` now shows `via 10.60.0.4 dev eth0`; after `ip route flush cache`, `ip route get 10.60.1.4` resolves `via 10.60.0.4 dev eth0`.
- **Stage 3:** PASS. `vm-ce-onprem` ping to `10.40.1.4` returned `0% packet loss`.
- **Stage 4:** FAIL. `vm-ce-onprem` ping to `10.60.0.4` returned `5 packets transmitted, 0 received, +5 errors, 100% packet loss`.
- **Stages 5-7:** not part of the ordered verdict, because the stop condition was reached at stage 4.

This means the run-command transport problem is now closed, the hub Linux FIB change is proven
landed, and the residual blocker has moved downstream to the CE-to-spoke-NVA data path. Raw
evidence for this retry is captured under:

- `show-output/s1-ce-reachability-fix-retry3-20260929T172057Z/`

## S1 spoke reachability fix (2026-09-29, Trinity-approved F1/F2)

Trinity then narrowed the remaining blocker to two spoke-side Azure defects and instructed Tank to
change nothing else:

1. **F1:** create `Allow-OnpremSim-Forwarded-In` on `nsg-spoke-nva`, priority `105`, source
   `172.40.100.0/24`, destination `VirtualNetwork`, protocol `*`, direction `Inbound`, access
   `Allow`.
2. **F2:** create `rt-spoke-nva-return`, add only
   `route-to-onprem-sim-via-hub` (`172.40.100.0/24 -> VirtualAppliance -> 10.40.1.4`), and
   associate it to `vnet-sap-rise/snet-spoke-nva`.

Ordered verification for this round was run exactly as specified:

- **Step 1:** PASS. Subnet-scoped peering shape remained unchanged and connected on both sides.
- **Step 2:** PASS. `Allow-OnpremSim-Forwarded-In` exists with the exact requested fields.
- **Step 3:** PASS. `rt-spoke-nva-return` exists, contains only the narrow `172.40.100.0/24`
  route, and is attached to `snet-spoke-nva`.
- **Step 4:** PASS. `nic-spoke-nva` effective routes still show
  `10.40.1.0/27 -> VNetPeering`, and now also show
  `172.40.100.0/24 -> VirtualAppliance -> 10.40.1.4` as `Active`.
- **Step 5:** FAIL. `vm-ce-onprem` ping to `10.60.0.4` still returned
  `5 packets transmitted, 0 received, 100% packet loss`.

Per Trinity's stop rule, Tank did **not** attempt another fix. The required fallback diagnostics
were collected in order:

- **A, `vm-hub-nva`:** `ip route get 10.60.0.4` resolves `via 10.60.0.4 dev eth0`, but
  `ping -c 3 10.60.0.4` returns `Destination Host Unreachable` from `10.40.1.4`.
- **B, `vm-spoke-nva`:** guest Linux still resolves `172.40.100.4 via 10.60.0.1 dev eth0 src 10.60.0.4`;
  during the CE retry, `tcpdump` captured `0 packets` matching `172.40.100.4` or `10.40.1.4`.
- **C, `vm-ce-onprem`:** repeated authoritative ping to `10.60.0.4` remained `100% packet loss`.

This round stops here and remains with Trinity. Steps 6-8 from the success path were not run
because step 5 failed. Raw evidence is captured under:

- `show-output/s1-spoke-reachability-fix-20260929T173839Z/`

## Next steps for Niobe

- Do **not** start S1 end-to-end re-validation from the current state; the CE reachability defect is
  still open and remains with Trinity.
- When ready to test S2, flip `enable_summarized_gateway_prefixes = true` in `src/terraform/sap-rise-scoped-peering-fwaas/variables.tf` and re-apply; this activates `summarizedGatewayPrefixes` on `vnet-hub` per the corrected S2 placement, without touching S1's already-validated BIRD state.
