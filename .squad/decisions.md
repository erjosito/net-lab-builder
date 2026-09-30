## Active Decisions

> Active decisions from all agents (merged by Scribe).
> Pre-merge snapshot archived to `decisions-archive.md` on 2026-09-29T17:43:35Z because `decisions.md` exceeded the Tier-2 ceiling.
> Session inbox files merged and deduplicated: 10.

---

# Decision - sap-rise-scoped-peering-fwaas: S1 scope and deployment deviations remain accepted context

**Date:** 2026-09-29
**By:** Morpheus, Trinity, Tank
**Status:** Active context

## What

- Stage 1 remains the same two-scenario lab: S1 uses ARS plus hub-NVA BGP redistribution, S2 uses advertised gateway prefixes only.
- Tank's live deployment deviations remain accepted context: simulated CE as an Azure VM in `vnet-onprem-sim`, no Bastion, Frankfurt Megaport PoP instead of Stockholm because the account lacks Sweden market entitlement, and VM fallback to `Standard_B2s_v2` after capacity failure.
- The subnet-scoped hub-to-spoke peering design stays intact; the debugging work today did not broaden peering scope or re-open S2 design.

## Why

These deviations explain the real packet path under test, especially the CE-simulation harness. They must stay visible because later defects C and F2 depend on the CE living in a separately peered VNet, not on a real on-prem router behind the ExpressRoute gateway.

---

# Decision - sap-rise-scoped-peering-fwaas: BGP defect chain is closed, but Niobe's re-validation opened data-plane defects A, B, and C

**Date:** 2026-09-29
**By:** Niobe, Trinity, Tank
**Status:** Confirmed and applied

## What

- The earlier S1 BGP flap chain is considered resolved for its own scope. Defects 1, 2, 3a, and 3b were all confirmed closed before Niobe re-ran the full scenario.
- Niobe's independent re-validation then proved the end-to-end data plane still failed even with all three BGP sessions stable. That re-opened S1 with three new defects:
  - **A:** ARS `allowBranchToBranchTraffic` was off, so ARS learned `10.60.0.0/16` from the hub NVA but did not hand it to the co-resident ExpressRoute gateway.
  - **B:** `vm-hub-nva` had `net.ipv4.ip_forward=0` in the running kernel even though the sysctl drop-in existed.
  - **C:** the simulated CE subnet had no Azure-fabric route to the spoke supernet, so the CE-side harness needed a UDR to `10.60.0.0/16 -> 10.40.1.4`.
- Trinity accepted the CE-side UDR as part of the simulation harness, not as a lab-topology redesign.
- Tank applied A, B, and C, and verified the immediate Azure-side checks passed.

## Why

Niobe proved that a stable BGP control plane was necessary but not sufficient. The pass bar is actual CE-to-spoke reachability, so route propagation had to be validated all the way through the ER gateway, the forwarding state on the hub NVA, and the Azure fabric in the CE-simulation VNet.

## Outcome

A, B, and C are considered landed and individually verified, but the authoritative CE-to-spoke-NVA ping still failed after they were applied. That moved the residual fault deeper into the hub-to-spoke data path.

---

# Decision - sap-rise-scoped-peering-fwaas: Hub-side residuals D1, D2, and E are fixed; `az vm run-command invoke --scripts @file` is now the standard apply pattern

**Date:** 2026-09-29
**By:** Trinity, Tank
**Status:** Confirmed and active

## What

- Trinity isolated three more residual defects after A/B/C:
  - **D1:** `nsg-hub-nva` needed an explicit data-plane inbound allow from `172.40.100.0/24`.
  - **D2:** `nsg-hub-nva` needed an explicit inbound allow from the workload subnet `10.60.1.0/24` for the eventual return leg.
  - **E:** `vm-hub-nva` needed its `protocol kernel` block changed from `export none;` to `export where proto = "static_bgp";` so the already-correct static spoke route would be exported into the guest Linux FIB without reintroducing the old ARS kernel-poisoning bug.
- Tank's first two Defect E attempts showed an apply-transport problem, not a design error: inline multiline `az vm run-command invoke --scripts "..."` usage swallowed the heredoc or returned empty proof, so the change was not trustworthy even when Azure reported outer success.
- Retry 3 fixed the transport method by writing the guest script to `labs/sap-rise-scoped-peering-fwaas\deploy\scripts\hub-bird-kernel-export-fix.sh` and invoking it with `az vm run-command invoke --scripts @<file>`.
- With the `@file` pattern, the hub-side proof became authoritative: `birdc configure` succeeded, `ip route show 10.60.0.0/16` showed the expected `proto bird` route via `10.60.0.4`, and `ip route get 10.60.1.4` resolved through the spoke NVA. CE-to-hub ping then passed.

## Why

This separated a tooling/quoting failure from the actual network diagnosis. The fix only counted once the VM-side stdout proved the edit landed and the guest FIB changed.

## Outcome

D1, D2, and E are closed. The operational rule is now explicit for this lab: for multiline guest scripts, write a local script file and call `az vm run-command invoke --scripts @file`; do not trust inline heredoc-style quoting from Windows PowerShell for authoritative applies.

---

# Decision - sap-rise-scoped-peering-fwaas: Spoke-side defects F1 and F2 are applied, but S1 is still open at the final CE-to-spoke hop

**Date:** 2026-09-29
**By:** Trinity, Tank
**Status:** OPEN, escalated to Trinity for next session

## What

- Trinity identified two spoke-side defects after hub-side verification passed:
  - **F1:** `nsg-spoke-nva` needed an explicit inbound allow for the real forwarded source prefix `172.40.100.0/24`.
  - **F2:** `snet-spoke-nva` needed a narrow return route `172.40.100.0/24 -> VirtualAppliance -> 10.40.1.4`.
- Tank applied F1 and F2 exactly as specified and verified the new NSG rule, route table, subnet association, and effective routes were all present.
- The authoritative end-to-end probe still failed: `vm-ce-onprem -> 10.60.0.4` remained `100% packet loss`.
- Fallback diagnostics were captured without attempting another fix:
  - On the hub, `ip route get 10.60.0.4` resolves via `10.60.0.4 dev eth0`, but pinging `10.60.0.4` from the hub side returns `Destination Host Unreachable` from `10.40.1.4`.
  - On the spoke, `ip route get 172.40.100.4` still resolves via the local default gateway `10.60.0.1`, and `tcpdump` saw zero CE or hub packets during the retry window.

## Why

The Azure-side spoke objects now reflect the intended design, but the guest-level evidence still shows the return path is not behaving as the authoritative fix expected. That is the remaining unresolved defect chain.

## Next session gate

Do **not** guess another fix from the coordinator side. Trinity should pick up first and analyze the fallback `tcpdump` and `ip route` evidence in `labs/sap-rise-scoped-peering-fwaas/show-output/s1-spoke-reachability-fix-20260929T173839Z/` before authoring any further change.


---




---

### 2026-09-29T08:49:30.289+02:00: Result-first live-lab governance
**By:** Morpheus

**What:** Adopted `.squad/live-lab-policy.md` as the mandatory contract for the
coordinator and all active agents. Live work now uses one objective, phase,
owner, and bounded lease; Tank mutation and Niobe single-scenario validation
have separate hard budgets; verdicts are returned within five minutes of
decisive output; restore is bounded; STOP drains queued work; child processes
must time out and terminate as a tree; and evidence expansion, diagrams,
documentation, vault backfill, and publication occur only after verdict,
restore, and confirmed owner idle. Ralph monitors checkpoint/cost deadlines,
and incident review is owned separately from live execution.

**Why:** The 2026-09-28 `vwan-ipsec-over-er-backup` incident delayed the
requested result for roughly 20 hours because deployment, remediation,
validation, evidence reconstruction, indexing, documentation, and retries were
queued onto one long-lived agent, including an unbounded child process and
contradictory work after STOP. The new policy preserves full evidence quality
while sequencing it after the requested verdict and safe restore.

