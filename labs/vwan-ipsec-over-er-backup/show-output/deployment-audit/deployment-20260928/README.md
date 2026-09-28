# Deployment audit transcript

**Correlation:** `deployment-20260928-01`

**Window:** 2026-09-28 08:32:23Z through 13:22:39Z
**Records:** 341 commands, including 40 nonzero exits retained as negative evidence.

The `transcript/` directory reconstructs the Azure, GCP, Megaport, Terraform and CPE deployment/configuration history from the local append-only Copilot CLI session log. Every record contains the exact sanitized command, UTC/local timestamps, duration, exit code, expected effect, combined captured output and shared tool context.

The historical shell runner retained stdout and stderr as one combined result. `*.combined.txt` preserves that exact sanitized result; `*.stdout.txt` and `*.stderr.txt` explicitly state that separate attribution cannot be recovered. Async gateway and Terraform operations include all later reads sharing the same shell ID.

## Milestone correlation

| UTC | Record | Milestone |
|---|---|---|
| 09:22:39 | `071` | Validated the frozen manifest, budget envelope and scoped file set. |
| 09:31:54 | `093` | Created and validated the new isolated, billing-linked GCP project and enabled required APIs. |
| 09:41:18 | `104` | Initialized and validated the Terraform stack. |
| 09:45:32-10:27:50 | `112`-`169` | Deployed Azure/GCP foundations and monitored the long-running vWAN VPN/ER gateways. Failed deployment attempts and provider diagnostics remain recorded. |
| 10:35:21 | `172` | Recorded the second `e2-small` capacity/resource failure. |
| 10:36:14 | `173` | Successfully placed `e2-small` in `europe-north2-c`; no `e2-medium` fallback was used. |
| 10:40:49-11:35:32 | `185`-`190` | Repaired CPE startup configuration, reran it in place, rebooted and verified the corrected StrongSwan/FRR host baseline. |
| 11:37:31-11:53:18 | `192`-`230` | Converged live foundation state and reached an authenticated Terraform no-change plan. |
| 12:04:52-12:05:32 | `262`-`265` | Populated the runtime inventory, installed reviewed CPE controls and smoke-tested the read-only Megaport collector. |
| 12:29:51 | `304` | Queried enabled markets and captured the live MCR/VXC quote. |
| 12:31:17 | `306` | Compared Amsterdam PoPs after nearer enabled markets failed compatibility/availability checks. |
| 12:33:44 | `309` | Produced the final provider plan within the authorized cost envelope. |
| 12:34:24 | `310` | Ordered the Amsterdam MCR, two Azure VXCs and one GCP VXC, then connected ExpressRoute. |
| 12:58:27 | `311`-`312` | Confirmed ER provider `Provisioned`, Azure private peering and GCP Partner attachment/BGP health. |
| 12:59:34-13:03:44 | `316`, `318` | Preserved failed Azure CLI VPN-connection creation attempts that led to the explicit REST fallback. |
| 13:10:50 | `324` | Created the D2 VPN bundle with versioned Azure REST operations. |
| 13:19:02 | `332` | Generated runtime PSKs and applied the VPN connection secrets without committing them. |
| 13:19:42-13:20:23 | `333`, `336` | Preserved CPE runtime failures that exposed line-ending/configuration issues. |
| 13:21:06 | `339`-`341` | Captured initial CPE, Azure VPN and GCP provider state before the custom-peer/blocker investigation continued in `deployment-blocker-2026-09-28/transcript/`. |

## Scope and linkage

The deployment transcript ends where the dedicated original-blocker correlation begins. The two datasets intentionally overlap only at the handoff from initial VPN/CPE state to custom BGP-address investigation:

- deployment/configuration: `deployment-20260928-01`;
- original non-APIPA blocker: `nonapipa-blocker-20260928-01`;
- bounded APIPA correction and rollback: `apipa-correction-20260928-01`.

No provider operation was rerun to create this audit record. The importer only read the historical local session log and wrote sanitized repository evidence.
