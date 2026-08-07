# Poland Central Cleanup — Deletion Preview (DRY RUN ONLY)

**Author:** Tank (IaC Engineer)
**Date:** 2026-08-05T16:00:43+02:00
**Requested by:** Jose Moreno
**Status:** ✅ **EXECUTED — 2026-08-05T~19:15+02:00.** All 29 objects in §2 below were deleted exactly
as listed; nothing else was touched. Command-by-command evidence:
[`show-output/cleanup-poland-execution/`](./show-output/cleanup-poland-execution/) (`pre/` baseline
captures, `01`–`04` per-stage command logs, `post/05-post-delete-verification.md`). Confirmed via
structured confirmation referencing this exact 29-object list for
`rg-dual-hub-hubless-region-ars-lab3d001`. Post-delete resource count: **50** (was 61), region
breakdown `swedencentral=20`, `switzerlandnorth=19`, `norwayeast=11`, `polandcentral=0`. See §10 for
the full executed-result record. The remainder of this document (§0–§8 below) is preserved
**unedited** as the original dry-run proposal and approved delete list, per task instruction not to
rewrite historical evidence as if Poland never existed.
**Scope authority:** Jose authorized *investigating and previewing* removal of Poland Central
resources; execution was subsequently approved and carried out per §10.

## 0. Context (no raw subscription ID recorded)

- **Resource group (live, confirmed via `az group list`):** `rg-dual-hub-hubless-region-ars-lab3d001`
  — region `swedencentral`, tags `lab=true`, `ephemeral=true`, `owner=jose`,
  `lab_name=dual-hub-hubless-region-ars`, `correlation_id=lab3d001` (see
  `show-output/cleanup-poland-dry-run/00-context-subscription-rg.md`).
- **Subscription/tenant:** resolved from the active `az account show` context; not written anywhere
  in this document or its captures — use `<SUBSCRIPTION_ID>` / `<TENANT_ID>` placeholders only.
- **Source of expected inventory:** `manifest.md` §1/§3, `deploy/templates/main.bicep`,
  `deploy-log.md`, and this lab's diagrams/evidence.
- **Live resource count at task start:** 61 top-level ARM objects (`az resource list`) + 20 VNet
  peering child objects + 13 ARS BGP-peering/route-map child objects, verified unchanged at task end
  — see `show-output/cleanup-poland-dry-run/08-resource-count-baseline-before-after.md`.

## 1. Expected-vs-live cross-check

| Expected item (manifest.md / main.bicep) | Live? | Discrepancy |
|---|---|---|
| `vnet-poland-ars` (10.30.0.0/24, RouteServerSubnet only) | ✅ Live, `Succeeded` | None |
| `vnet-spoke-c1` (10.31.0.0/24) | ✅ Live, `Succeeded` | None |
| `vnet-spoke-c2` (10.32.0.0/24, prefix-only, no VM) | ✅ Live, `Succeeded` | None — confirmed no VM/NIC in this VNet |
| `ars-poland` (b2b=false) | ✅ Live, `Succeeded`, `allowBranchToBranchTraffic=false` | None |
| `ars-poland` BGP peerings `peer-nva1`/`peer-nva2` | ✅ Both live, `Succeeded` | None |
| `pip-ars-poland` | ✅ Live | None |
| `vm-c1-ep` (Standard_B2ts_v2) | ✅ Live | None |
| `nic-vm-c1-ep` | ✅ Live | None |
| `osdisk-vm-c1-ep` | ✅ Live, `diskState=Reserved` (attached) | None |
| `nsg-ep-poland` | ✅ Live | **NSG is subnet-associated to `vnet-spoke-c1/snet-workload`, not NIC-associated** — changes delete ordering (see §4) |
| 10 peerings on the 3 Poland VNets | ✅ All 10 live, `Connected` | None |
| 6 remote-side peerings on `vnet-hub1`/`vnet-hub2` pointing at Poland | ✅ All 6 live, `Connected` | Confirmed nested/dependent objects per task item 2 — not `location=polandcentral` themselves but reference Poland VNets |
| Route table for spoke-c1/c2 | ❌ **Does not exist** | Manifest's "2 Route Tables" are `rt-spoke-a`/`rt-spoke-b` only (Sweden/Switzerland-scoped); set-C relies on ARS-injected `0.0.0.0/0`, no UDR. **No route-table delete step applies to Poland.** |
| `ars-poland` route-map child object | ❌ **Not live** (empty array) | `.squad/agents/tank/history.md` states the route-map surcharge already applies to all 3 ARS (incl. poland) after prior upgrades, but live ARM shows 0 route-map objects on `ars-poland` vs. 1 each on `ars-hub1`/`ars-hub2`. Flagged as unresolved — does not change the deletion plan (ars-poland is deleted either way) but affects the cost estimate confidence (§6). |
| Overall NSG count | Manifest says 4 NSGs; live = 6 | Pre-existing manifest drift, **unrelated to Poland** (`nsg-ep-poland`, `nsg-ep-hub2`, `nsg-nva-hub2`, `nsg-ep-onprem`, `nsg-ep-general`, `nsg-nva-hub1` all exist). Only `nsg-ep-poland` is in Poland scope; noted here for completeness, not actioned. |

Full captures: `show-output/cleanup-poland-dry-run/01` through `07`.

## 2. Exact delete list (29 objects total)

### 2a. Explicitly commanded deletions (17) — every ID below has `<SUBSCRIPTION_ID>` redacted

| # | Resource name | Type | Location | Redacted resource ID |
|---|---|---|---|---|
| 1 | `peer-hub1-to-poland` | virtualNetworks/virtualNetworkPeerings | swedencentral (parent `vnet-hub1`) | `/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-dual-hub-hubless-region-ars-lab3d001/providers/Microsoft.Network/virtualNetworks/vnet-hub1/virtualNetworkPeerings/peer-hub1-to-poland` |
| 2 | `peer-hub1-to-spoke-c1` | virtualNetworkPeerings | swedencentral (parent `vnet-hub1`) | `.../vnet-hub1/virtualNetworkPeerings/peer-hub1-to-spoke-c1` |
| 3 | `peer-hub1-to-spoke-c2` | virtualNetworkPeerings | swedencentral (parent `vnet-hub1`) | `.../vnet-hub1/virtualNetworkPeerings/peer-hub1-to-spoke-c2` |
| 4 | `peer-hub2-to-poland` | virtualNetworkPeerings | switzerlandnorth (parent `vnet-hub2`) | `.../vnet-hub2/virtualNetworkPeerings/peer-hub2-to-poland` |
| 5 | `peer-hub2-to-spoke-c1` | virtualNetworkPeerings | switzerlandnorth (parent `vnet-hub2`) | `.../vnet-hub2/virtualNetworkPeerings/peer-hub2-to-spoke-c1` |
| 6 | `peer-hub2-to-spoke-c2` | virtualNetworkPeerings | switzerlandnorth (parent `vnet-hub2`) | `.../vnet-hub2/virtualNetworkPeerings/peer-hub2-to-spoke-c2` |
| 7 | `peer-nva1` | virtualHubs/hubRouteTables (ARS BGP peering) | polandcentral (parent `ars-poland`) | `/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-dual-hub-hubless-region-ars-lab3d001/providers/Microsoft.Network/virtualHubs/ars-poland/bgpConnections/peer-nva1` |
| 8 | `peer-nva2` | ARS BGP peering | polandcentral (parent `ars-poland`) | `.../virtualHubs/ars-poland/bgpConnections/peer-nva2` |
| 9 | `ars-poland` | Microsoft.Network/virtualHubs (Route Server) | polandcentral | `/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-dual-hub-hubless-region-ars-lab3d001/providers/Microsoft.Network/virtualHubs/ars-poland` |
| 10 | `vm-c1-ep` | Microsoft.Compute/virtualMachines | polandcentral | `/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-dual-hub-hubless-region-ars-lab3d001/providers/Microsoft.Compute/virtualMachines/vm-c1-ep` |
| 11 | `nic-vm-c1-ep` | Microsoft.Network/networkInterfaces | polandcentral | `/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-dual-hub-hubless-region-ars-lab3d001/providers/Microsoft.Network/networkInterfaces/nic-vm-c1-ep` |
| 12 | `osdisk-vm-c1-ep` | Microsoft.Compute/disks | polandcentral | `/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-dual-hub-hubless-region-ars-lab3d001/providers/Microsoft.Compute/disks/osdisk-vm-c1-ep` |
| 13 | `pip-ars-poland` | Microsoft.Network/publicIPAddresses | polandcentral | `/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-dual-hub-hubless-region-ars-lab3d001/providers/Microsoft.Network/publicIPAddresses/pip-ars-poland` |
| 14 | `vnet-spoke-c1` | Microsoft.Network/virtualNetworks | polandcentral | `/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-dual-hub-hubless-region-ars-lab3d001/providers/Microsoft.Network/virtualNetworks/vnet-spoke-c1` |
| 15 | `vnet-spoke-c2` | Microsoft.Network/virtualNetworks | polandcentral | `.../virtualNetworks/vnet-spoke-c2` |
| 16 | `vnet-poland-ars` | Microsoft.Network/virtualNetworks | polandcentral | `.../virtualNetworks/vnet-poland-ars` |
| 17 | `nsg-ep-poland` | Microsoft.Network/networkSecurityGroups | polandcentral | `/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-dual-hub-hubless-region-ars-lab3d001/providers/Microsoft.Network/networkSecurityGroups/nsg-ep-poland` |

### 2b. Removed automatically as a side effect (12) — no separate command issued

| # | Resource name | Removed by |
|---|---|---|
| 18 | `vm-c1-ep/enablevmAccess` (extension) | Deleting `vm-c1-ep` (#10) |
| 19 | `vm-c1-ep/MDE.Linux` (extension) | Deleting `vm-c1-ep` (#10) |
| 20-23 | `peer-poland-to-hub1`, `peer-poland-to-hub2`, `peer-poland-to-spoke-c1`, `peer-poland-to-spoke-c2` | Deleting `vnet-poland-ars` (#16) |
| 24-26 | `peer-spoke-c1-to-hub1`, `peer-spoke-c1-to-hub2`, `peer-spoke-c1-to-poland` | Deleting `vnet-spoke-c1` (#14) |
| 27-29 | `peer-spoke-c2-to-hub1`, `peer-spoke-c2-to-hub2`, `peer-spoke-c2-to-poland` | Deleting `vnet-spoke-c2` (#15) |

**Total objects removed from the subscription: 29** (17 explicit + 12 side-effect).

## 3. Exact preserve list (summary)

**Everything else in the RG — 50 top-level ARM objects + 4 VNet peerings + 11 ARS BGP-peering/
route-map objects — is preserved, untouched, unassociated, unresized, unstopped:**

| Region | Preserved objects (top-level) | Notes |
|---|---|---|
| swedencentral | `vnet-hub1` (post-cleanup: 1 peering `peer-hub1-to-spoke-a`), `vnet-spoke-a`, `vpngw-hub1`, `ars-hub1` (+ its 1 BGP peering `peer-nva1`, + its route map `rm-hub1-activate`), `vm-nva1`, `vm-hub1-ep`, `nsg-nva-hub1`, `nsg-ep-general`, `rt-spoke-a`, 3 PIPs (2×GW + 1×ARS) | 20 objects |
| switzerlandnorth | `vnet-hub2` (post-cleanup: 1 peering `peer-hub2-to-spoke-b`), `vnet-spoke-b`, `vpngw-hub2`, `ars-hub2` (+ its 1 BGP peering `peer-nva2`, + its route map `rm-hub2-activate`), `vm-nva2`, `vm-hub2-ep`, `nsg-nva-hub2`, `nsg-ep-hub2`, `rt-spoke-b`, 3 PIPs | 19 objects |
| norwayeast | `vnet-onprem`, `vpngw-onprem`, `vm-onprem-ep`, `nsg-ep-onprem`, 2 PIPs | 11 objects |
| (RG-scoped) | `rg-dual-hub-hubless-region-ars-lab3d001` itself | Explicitly excluded from any deletion — RG is never targeted |
| (cross-cutting) | 4 VPN connection objects (`conn-hub1-to-onprem`, `conn-onprem-to-hub1`, `conn-hub2-to-onprem`, `conn-onprem-to-hub2`) | None touch Poland — no VPN GW exists in Poland |

Also explicitly preserved per task item 4: **all hub1/hub2 Route Servers, VPN gateways, NVAs,
set-A/set-B spokes, and on-prem resources** — none of these are on the delete list, and live
evidence (`show-output/cleanup-poland-dry-run/04`, `05`) confirms none of them reference Poland.

## 4. Dependency-safe deletion order (proposed — NOT executed)

Every command is individually named against one resource. No `az group delete`, no wildcard
`--ids $(az resource list ...)`, no recursive path. Commands use `-g/-n` (or `--vnet-name`/
`--routeserver` parent flags) rather than embedding full resource IDs, so nothing here can be
copy-pasted into a broader-scoped call by accident.

```
STAGE 0 — Final pre-delete evidence capture (read-only, run immediately before Stage 1)
  az network routeserver peering list-learned-routes -g rg-dual-hub-hubless-region-ars-lab3d001 --routeserver ars-poland --name peer-nva1
  az network routeserver peering list-learned-routes -g rg-dual-hub-hubless-region-ars-lab3d001 --routeserver ars-poland --name peer-nva2
  az network nic show-effective-route-table -g rg-dual-hub-hubless-region-ars-lab3d001 -n nic-vm-c1-ep
  az vm run-command invoke -g rg-dual-hub-hubless-region-ars-lab3d001 -n vm-c1-ep --command-id RunShellScript --scripts 'ping -c 4 10.40.1.4'
  az resource list -g rg-dual-hub-hubless-region-ars-lab3d001 --query "length(@)"   # baseline count, repeat after Stage 6

STAGE 1 — Remote-side peerings first (hub1/hub2 keep existing, only drop the Poland-pointing side)
  az network vnet peering delete -g rg-dual-hub-hubless-region-ars-lab3d001 --vnet-name vnet-hub1 -n peer-hub1-to-poland
  az network vnet peering delete -g rg-dual-hub-hubless-region-ars-lab3d001 --vnet-name vnet-hub1 -n peer-hub1-to-spoke-c1
  az network vnet peering delete -g rg-dual-hub-hubless-region-ars-lab3d001 --vnet-name vnet-hub1 -n peer-hub1-to-spoke-c2
  az network vnet peering delete -g rg-dual-hub-hubless-region-ars-lab3d001 --vnet-name vnet-hub2 -n peer-hub2-to-poland
  az network vnet peering delete -g rg-dual-hub-hubless-region-ars-lab3d001 --vnet-name vnet-hub2 -n peer-hub2-to-spoke-c1
  az network vnet peering delete -g rg-dual-hub-hubless-region-ars-lab3d001 --vnet-name vnet-hub2 -n peer-hub2-to-spoke-c2

STAGE 2 — Route Server child BGP peerings, then the Route Server
  az network routeserver peering delete -g rg-dual-hub-hubless-region-ars-lab3d001 --routeserver ars-poland -n peer-nva1 --yes
  az network routeserver peering delete -g rg-dual-hub-hubless-region-ars-lab3d001 --routeserver ars-poland -n peer-nva2 --yes
  az network routeserver delete -g rg-dual-hub-hubless-region-ars-lab3d001 -n ars-poland --yes
     # ~10 min per manifest.md §10

STAGE 3 — VM / NIC / disk / PIP dependencies (NSG deferred — see note below)
  az vm delete -g rg-dual-hub-hubless-region-ars-lab3d001 -n vm-c1-ep --yes
     # removes vm-c1-ep/enablevmAccess and vm-c1-ep/MDE.Linux extensions automatically
  az network nic delete -g rg-dual-hub-hubless-region-ars-lab3d001 -n nic-vm-c1-ep
  az disk delete -g rg-dual-hub-hubless-region-ars-lab3d001 -n osdisk-vm-c1-ep --yes
  az network public-ip delete -g rg-dual-hub-hubless-region-ars-lab3d001 -n pip-ars-poland
     # only after ars-poland (Stage 2) is fully deleted — it owns the only ipConfiguration

STAGE 4 — Poland VNets last (also removes the 10 Poland-side peering child objects together with
           their parent VNets — see §2b)
  az network vnet delete -g rg-dual-hub-hubless-region-ars-lab3d001 -n vnet-spoke-c1
  az network vnet delete -g rg-dual-hub-hubless-region-ars-lab3d001 -n vnet-spoke-c2
  az network vnet delete -g rg-dual-hub-hubless-region-ars-lab3d001 -n vnet-poland-ars

STAGE 4b — NSG (deliberately placed AFTER Stage 4, not before)
  az network nsg delete -g rg-dual-hub-hubless-region-ars-lab3d001 -n nsg-ep-poland
     # nsg-ep-poland is associated to vnet-spoke-c1's subnet (not the NIC — confirmed in
     # show-output/cleanup-poland-dry-run/07). Azure refuses to delete an NSG still associated to a
     # subnet, so this MUST run after Stage 4, not in the generic "NSG before VNet" position a
     # template ordering would suggest.
  # No route-table delete step exists for Poland — none applies (§1).

STAGE 5 — Post-delete verification (read-only)
  az resource list -g rg-dual-hub-hubless-region-ars-lab3d001 --query "length(@)"        # expect 61-11=50
  az network vnet list -g rg-dual-hub-hubless-region-ars-lab3d001 --query "[].name" -o tsv  # expect 5 VNets remain
  az network vnet peering list -g rg-dual-hub-hubless-region-ars-lab3d001 --vnet-name vnet-hub1 -o table  # expect 1 (peer-hub1-to-spoke-a)
  az network vnet peering list -g rg-dual-hub-hubless-region-ars-lab3d001 --vnet-name vnet-hub2 -o table  # expect 1 (peer-hub2-to-spoke-b)
  az network routeserver list -g rg-dual-hub-hubless-region-ars-lab3d001 -o table         # expect 2 (ars-hub1, ars-hub2)
  az network vnet-gateway list -g rg-dual-hub-hubless-region-ars-lab3d001 -o table        # expect 3, unchanged
  az network vpn-connection list -g rg-dual-hub-hubless-region-ars-lab3d001 -o table      # expect 4, all Connected, unchanged
  az vm list -g rg-dual-hub-hubless-region-ars-lab3d001 -o table                          # expect 5 (nva1, nva2, hub1-ep, hub2-ep, onprem-ep)
```

## 5. Expected impact

### On the source lab (`dual-hub-hubless-region-ars`)
- **S4 (Δ3 Route-Map Preview)** and **S5 (Prefix-Only Spoke Scale)** in `manifest.md`/`validation.md`
  become permanently non-repeatable in this bed — both scenarios test Poland/set-C behavior
  specifically. S1/S2/S3 (hub1↔hub2 failover/failback via on-prem) are unaffected.
- `manifest.md` §1 Resource Inventory, §6 Cleanup Sequence, §11 Cost, and the README's "4 regions"
  framing would all need a follow-up documentation update **after** any real execution — not part of
  this dry run, flagged for the next Morpheus/Trinity pass.
- Post-cleanup counts: 8→5 VNets, 3→2 Route Servers, 9→8 Standard PIPs, 6→5 VMs, 6→5 disks,
  6→5 NICs, 6→5 NSGs, 20→4 VNet peering objects (10→2 logical pairs), 2 route tables unchanged.

### On the new two-region lab (`dual-hub-interconnect-ars-route-policy`)
- **No functional impact.** That lab's own README already states Poland/set-C is "out of scope
  entirely" and every mention there is "an explicit exclusion or contrast note, never a topology
  dependency." Its TP-HH scenarios (T1-T5) exercise only `vnet-hub1`/`vnet-hub2`, `ars-hub1`/
  `ars-hub2`, `vm-nva1`/`vm-nva2` — none of which are on the delete list, and capture 05 confirms
  ars-hub1/ars-hub2's BGP peerings never referenced Poland.
- The only preserved peerings this lab could ever build on (`peer-hub1-to-spoke-a`,
  `peer-hub2-to-spoke-b`, and any future `hub1↔hub2` peering) are unaffected.

## 6. Rollback reality

**There is no automatic rollback.** Deleting any of the 29 objects in §2 requires full
**redeployment** to recover:
- `main.bicep` (Poland module block) would need to be re-run (~15-20 min for `ars-poland` per
  manifest.md Wave 3, plus VNet/NIC/VM/peering waves).
- The two BGP sessions on `ars-poland` (`peer-nva1`, `peer-nva2`) would re-establish from scratch —
  no state is preserved.
- Any Δ3-specific ARS route-map upgrade state on `ars-poland` (see §1 discrepancy) would need to be
  re-verified; if the surcharge-triggering upgrade is genuinely gone, first re-activation would incur
  the same "~30 min ARS upgrade + surcharge" cost noted in manifest.md §4.
- PSKs, evidence baselines, and BIRD multi-hop config for the Poland leg are **not** backed up by
  this task and would need to be regenerated.
- **Nothing in this dry run creates a backup.** If Jose wants a recovery path, it must be requested
  and executed *before* Stage 1 — e.g., exporting `main.bicep`'s Poland parameters is already done
  (they're in git), but there is no snapshot of live state (BGP tables, disk contents) beyond the
  evidence captured in Stage 0.

## 7. Cost reduction estimate (approximate — MEDIUM/LOW confidence)

Basis: manifest.md §11 (Azure Retail Pricing PAYG USD 2026-08-03, confidence MEDIUM) plus
`.squad/agents/tank/history.md` B3 current run-rate (~$84/day). **Per-unit shares below are derived
by dividing the lab-wide totals by unit count — they are not independently retail-priced per
resource**, so treat this as directional, not exact.

| Poland-scoped cost component | Share of lab-wide total | ≈ $/day |
|---|---|---|
| `ars-poland` (1 of 3 Standard ARS @ $32.40/day total) | 1/3 | **$10.80** |
| `pip-ars-poland` (1 of 9 idle Standard PIPs @ $1.08/day total) | 1/9 | **$0.12** |
| `vm-c1-ep` compute (1 of 6 B2ts_v2 @ $1.58/day total) | 1/6 | **$0.26** |
| `vm-c1-ep` disk + egress share (1 of 6 @ ~$2.00/day total) | 1/6 | **$0.33** |
| `ars-poland` route-map surcharge — **status unresolved, see §1** | uncertain | **+$6.00 (if still billing) or $0 (if not)** |
| **Subtotal, low case (surcharge not billing)** | | **≈ $11.51/day** |
| **Subtotal, high case (surcharge still billing)** | | **≈ $17.51/day** |

**Estimated new run-rate after Poland removal:** ≈ **$66-73/day**, down from the current ≈$84/day
run-rate — an approximate **14-21% reduction**, or **≈ $345-$525/month** (30-day) saved. This
crosses back under the $50/day-and-under intuition only partially — it does **not** bring the bed
back under the $50/day guardrail; hub1/hub2/on-prem alone (2 ARS, 3 VPN GWs) remain the dominant
cost driver.

## 8. Hard confirmation gate

**TANK WILL NOT DELETE ANYTHING UNTIL JOSE MORENO GIVES THIS EXACT CONFIRMATION, VERBATIM:**

```
CONFIRM POLAND DELETE — rg-dual-hub-hubless-region-ars-lab3d001 — 29 objects per
labs/dual-hub-hubless-region-ars/cleanup-poland-dry-run.md dated 2026-08-05 — preserve all
Sweden Central, Switzerland North, Norway East, and shared-RG resources — proceed.
```

Anything short of that exact line (a plain "yes", "go ahead", "do it", etc.) is **not** sufficient —
per the source lab's own Phase-4 approval-gate convention, ambiguity is treated as NO. If Jose
approves a subset (e.g., only the VM/disk/NIC/NSG endpoint, leaving `ars-poland` and the VNets for
later), a revised, re-numbered delete list must be produced first — this gate covers the full
29-object scope in §2 only.

## 9. Validation that no mutation occurred (this task)

- **Azure:** Pre- and post-task `az resource list -g rg-dual-hub-hubless-region-ars-lab3d001` both
  return 61 top-level resources with an identical type breakdown; all 20 VNet peerings, all 13 ARS
  BGP-peering/route-map child objects re-verified unchanged — see
  `show-output/cleanup-poland-dry-run/08-resource-count-baseline-before-after.md`.
- **Local git:** Only new files were added by this task (this document, the 9 `show-output/
  cleanup-poland-dry-run/*.md` captures, README callouts, history/decision-inbox entries). No
  existing IaC (`main.bicep`, modules), manifest, deploy-log, or evidence file was modified. No
  commit was made — changes remain in the working tree for Jose's review.

## 10. Executed result — 2026-08-05

*(This section was added post-execution. §0–§9 above are the original, unedited dry-run proposal.)*

**Confirmation basis:** structured confirmation "Confirm deletion of the exact 29-object dry-run
list" against this document, for `rg-dual-hub-hubless-region-ars-lab3d001`, received and honored as
covering the full §2 scope (all 29 objects, no subset).

**Execution order:** exactly as proposed in §4 (Stage 1 → 2 → 3 → 4 → 4b), no reordering required
beyond what §4 already documented (the NSG-after-VNet correction was already baked into the plan
before execution, not discovered during it).

**Result: all 29/29 objects deleted successfully. Zero failures, zero retries needed.**

| Stage | Objects | Result |
|---|---|---|
| 1 | 6 remote-side peerings (`peer-hub1-to-poland`, `peer-hub1-to-spoke-c1`, `peer-hub1-to-spoke-c2`, `peer-hub2-to-poland`, `peer-hub2-to-spoke-c1`, `peer-hub2-to-spoke-c2`) | ✅ all deleted, verified via list |
| 2 | `peer-nva1`, `peer-nva2` (ars-poland BGP peerings), `ars-poland` (Route Server) | ✅ all deleted; Route Server delete took ~25 min (longer than the ~10 min manifest estimate, documented, not a scope deviation) |
| 3 | `vm-c1-ep` (+ 2 auto-removed extensions), `nic-vm-c1-ep`, `osdisk-vm-c1-ep`, `pip-ars-poland` | ✅ all deleted; `vm-c1-ep` was already deallocated at task start (documented deviation from the Stage-0 evidence-capture assumption — did not block or change the deletion) |
| 4 | `vnet-spoke-c1`, `vnet-spoke-c2`, `vnet-poland-ars` (+ 10 auto-removed nested peerings) | ✅ all deleted |
| 4b | `nsg-ep-poland` | ✅ deleted after Stage 4, as planned (subnet association required VNet deletion first) |

**One documented deviation (non-blocking):** `vm-c1-ep` (and, it turned out, all 5 other preserved
VMs — `vm-nva1`, `vm-nva2`, `vm-hub1-ep`, `vm-hub2-ep`, `vm-onprem-ep`) were already in a
`deallocated` power state at task start — a pre-existing, lab-wide condition unrelated to this
cleanup. This meant the Stage-0 `az vm run-command` ping test and the NIC effective-route-table dump
could not run (both require a running VM) — captured verbatim in
`show-output/cleanup-poland-execution/pre/04-vm-poweroff-deviation-and-skipped-captures.md`. This did
not meet any of the task's STOP conditions (no new dependency, no missing target, no unexpected
replacement, no preserve-object selected), so execution proceeded per the approved list.

**Post-delete verification (full detail:
`show-output/cleanup-poland-execution/post/05-post-delete-verification.md`):**
- Resource count: **50** (was 61, expected 50) ✅
- Region breakdown: `swedencentral=20`, `switzerlandnorth=19`, `norwayeast=11`, `polandcentral=0` ✅
- `vnet-hub1` peerings: `peer-hub1-to-spoke-a` only (1) ✅ · `vnet-hub2` peerings: `peer-hub2-to-spoke-b` only (1) ✅
- Route Servers: `ars-hub1`, `ars-hub2` only (2) ✅ — each with its unchanged 1 BGP peering and 1 inert route map (`rm-hub1-activate`, `rm-hub2-activate`)
- VPN gateways: 3, `Succeeded` ✅ · VPN connections: 4/4 `Connected` ✅
- VMs: 5 (`vm-nva1`, `vm-nva2`, `vm-hub1-ep`, `vm-hub2-ep`, `vm-onprem-ep`) ✅ · NSGs: 5 (was 6) ✅
- Resource group `rg-dual-hub-hubless-region-ars-lab3d001`: present, `Succeeded`, tags unchanged ✅

**Duration:** approximately 65 minutes end-to-end (dominated by the ~25-minute `ars-poland` Route
Server delete).

**Revised run-rate estimate:** see `manifest.md` §11 update and `.squad/decisions/inbox/
tank-poland-cleanup-executed.md` for the recalculated ≈$66-73/day figure (unchanged from the dry-run
§7 estimate — the deletion executed exactly as previewed, so no re-derivation was needed beyond
confirming the route-map-surcharge uncertainty is now moot: `ars-poland` no longer exists, so its
surcharge (if it was ever billing) has definitively stopped either way).

**Git:** no commit made by this task, per instruction.
