# B1 — certified post-U1.5 baseline

**Captured:** 2026-08-06, immediately after both `vm-nva1` and `vm-nva2` U1.5 applications PASSED
and after this session's diff-summaries were written. This is the **reference baseline for U2's
byte-comparison PASS criterion** ("`ars-hub1` learned and advertised sets byte-identical to the
post-U1.5 baseline **B1**").

## Certified state

- **VM power:** `vm-nva1`, `vm-nva2` = `VM running`; `vm-hub1-ep`, `vm-hub2-ep`, `vm-onprem-ep` =
  `VM deallocated` (unchanged from every prior capture in this lab).
- **`ars-hub1` learned from `peer-nva1`:** `RouteServiceRole_IN_0` = `{0.0.0.0/0}`;
  `RouteServiceRole_IN_1` = `{0.0.0.0/0, 10.40.0.0/16}`. **No `10.30.0.0/27` on either instance.**
- **`ars-hub2` learned from `peer-nva2`:** `RouteServiceRole_IN_0` = `{0.0.0.0/0}`;
  `RouteServiceRole_IN_1` = `{0.0.0.0/0, 10.40.0.0/16}`. **No `10.30.0.0/27` on either instance.**
- **`ars-hub1`/`ars-hub2` advertised sets:** unchanged from every prior capture
  (`10.10.0.0/16`,`10.11.0.0/24`,`10.40.0.0/16` / `10.20.0.0/16`,`10.21.0.0/24`,`10.40.0.0/16`).
- **`vpngw-hub1`/`vpngw-hub2` advertised-to-onprem, `vpngw-onprem` learned:** byte-identical to the
  pre-U1.5 and post-per-NVA captures.
- **VPN connections:** all four `Connected`, 4 tunnels each.
- **NVA NIC effective routes:** `10.30.0.0/27` absent on both `nic-vm-nva1` and `nic-vm-nva2`; the
  U1 `VNetGlobalPeering` cross-hub `/16` entries still present and unchanged.
- **BIRD, both NVAs:** `ars_poland_0`/`ars_poland_1` absent from `show protocols all` entirely, on
  both hosts. `ars_hub1_0/1`, `ars_hub2_0/1` all `Established` with the **same `Since` timestamps**
  recorded since U0 (`07:12:12.272`/`07:12:13.010` on nva1; `07:12:17.496`/`07:12:20.643` on nva2) —
  confirming no session has flapped across either U1.5 reload. `master4` on both NVAs contains
  exactly `{0.0.0.0/0, local RouteServerSubnet /27, local hub /16 + /24 (learned), 10.40.0.0/16}` —
  no `10.30.0.0/27` anywhere.
- **Data plane:** `vm-nva1 ↔ vm-nva2` ICMP, 8/8 received, 0% loss, ~29.9–31.1 ms.

## Verdict

**B1 = clean, certified, matches the expected post-U1.5 shape on every layer captured.** This
baseline is authoritative for U2's PASS/FAIL comparison. Evidence files: `01`–`16` in this directory.
