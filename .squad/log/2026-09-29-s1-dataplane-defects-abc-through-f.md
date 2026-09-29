# Session Log: S1 data-plane defects A through F

**Date:** 2026-09-29
**Status:** OPEN - CE to spoke-NVA reachability still fails at the final hop
**Lab:** `labs/sap-rise-scoped-peering-fwaas`

## What was fixed today

- **A:** ARS branch-to-branch enabled. ExpressRoute gateway then learned `10.60.0.0/16` from ARS.
- **B:** `vm-hub-nva` forwarding fixed live and `deploy.ps1` now checks `/proc/sys/net/ipv4/ip_forward` for both NVAs.
- **C:** CE-simulation UDR added so `snet-ce-onprem` sends `10.60.0.0/16` to `10.40.1.4`.
- **D1 / D2:** hub NSG gaps closed for `172.40.100.0/24` and `10.60.1.0/24`.
- **E:** hub `bird.conf` kernel-export change landed and was proven in the Linux FIB. This also closed the Azure run-command quoting issue by standardizing on `az vm run-command invoke --scripts @file` for multiline guest scripts.
- **F1 / F2:** spoke NSG allow plus spoke return route were both applied and verified present.

Each of A, B, C, D1, D2, and E now has the expected hop-specific proof. The remaining failure is not a replay of the earlier BGP defects.

## What remains open

The authoritative CE probe still fails at the last hop:

- `vm-ce-onprem -> 10.60.0.4` still returns `100% packet loss`.
- The hub-side fallback shows `Destination Host Unreachable` from `10.40.1.4` when probing `10.60.0.4`.
- The spoke guest still resolves `172.40.100.4` through its own default gateway instead of back through the hub, and its fallback `tcpdump` saw zero matching packets during the retry window.

Fallback diagnostics were captured and should be treated as the starting point for the next session:
`labs/sap-rise-scoped-peering-fwaas/show-output/s1-spoke-reachability-fix-20260929T173839Z/`

Next session should start with Trinity analyzing that `tcpdump` and `ip route` evidence before attempting any new fix.

## Health report

- `decisions.md` before: 117910 bytes
- `decisions.md` after: 6793 bytes
- inbox files processed: 10
- history files summarized: `morpheus/history.md`, `trinity/history.md`, `tank/history.md`, `niobe/history.md`
