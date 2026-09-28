# Bounded APIPA correction audit

**Correlation:** `apipa-correction-20260928-01`

**Window:** 2026-09-28 15:06:24Z through 15:40:50Z
**Result:** failed the explicit Azure packet-source acceptance condition and was completely rolled back without retry.

The `transcript/` directory contains 89 command records reconstructed from the local append-only Copilot CLI session event log. Each record has a sanitized exact command, combined captured output, explicit stdout/stderr recovery notices, UTC/local timestamps, duration, exit code when recoverable, action/state classification, expected effect, and shared tool context. `transcript-manifest.json` is the compact ordered ledger.

## Evidence provenance

- This is a retrospective reconstruction because the bounded attempt began before `Invoke-AuditCommand.ps1` was available.
- The shell tool stored stdout and stderr as one combined result. The exact sanitized combined result is in `*.combined.txt`; `*.stdout.txt` and `*.stderr.txt` state that separate attribution is unavailable rather than inventing it.
- Async gateway operations are merged with every later `read_powershell` result sharing the same shell ID, so their final exit codes and complete elapsed output remain attached to the originating command.
- Failed and negative commands are retained. Eleven records have nonzero exit codes; none are rewritten or omitted.
- The concise outcome evidence remains in [`../../../apipa-remediation-2026-09-28/`](../../../apipa-remediation-2026-09-28/).

## Correlated timeline

| UTC | Record | Action and observed effect |
|---|---|---|
| 15:07:00 | `002` | Captured Azure gateway, public site and public connection objects used for rollback. |
| 15:07:00 | `003` | Captured four established SAs, original FRR peers and routes. Exit 1 is retained because unprivileged hash reads failed after the useful state capture. |
| 15:07:00 | `004` | Confirmed ER provider `Provisioned`, Azure private peering `Succeeded`, GCP Partner BGP Up and live Megaport products. |
| 15:08:06 | `010` | First Terraform plan command failed client-side because PowerShell split the target argument; no provider mutation occurred. |
| 15:08:22 | `012` | Confirmed that the Azure CLI has no supported `vpn-site link update` operation. |
| 15:09:30 | `015` | First gateway apply was rejected atomically with `GatewayCustomBgpIpAddressCannotbeRemoved`; an address still referenced by the private connection could not be removed. |
| 15:10:08 | `017` | Additive gateway plan/apply succeeded after 10m32s, preserving existing custom addresses while adding `169.254.22.2/.3`. |
| 15:20:46 | `032`-`033` | Verified the additive addresses and all four surviving SAs before changing the public site. |
| 15:21:02 | `035` | Direct child-link `PUT` failed with `OperationNotSupported`; no live change. |
| 15:21:34 | `040` | First parent-site `PUT` failed with `LocationRequired`; no live change. |
| 15:21:45 | `044` | Complete parent-site `PUT`, including location, changed the public CPE BGP peer to `169.254.22.1`. |
| 15:22:07 | `047` | First generated connection-update command failed PowerShell parsing before submission; no live change. |
| 15:22:23 | `050` | Parent connection `PUT` succeeded with existing PSK retained through session-private transfer and public mappings changed to `169.254.22.2/.3`. |
| 15:23:18 | `059` | First CPE script invocation failed on Windows CRLF before mutation. |
| 15:23:36 | `062` | LF-normalized CPE correction succeeded: APIPA loopback, four source-specific XFRM routes, FRR neighbors and filtering were applied without restarting StrongSwan. |
| 15:24:08 | `065` | Bounded convergence capture showed `.12` Established, `.13` Active, and both custom public peers Connect with zero messages. Four SAs and all intended route lookups remained healthy. |
| 15:24:08 | `066` | Packet capture proved both public tunnels still received Azure TCP/179 sourced from default peers `10.240.0.12/.13`, not custom peers `.22.2/.3`. This triggered the explicit rollback condition. |
| 15:24:08 | `067` | Confirmed configured Azure mappings and unchanged provider health, narrowing the unresolved configuration/API association without establishing a platform limitation. |
| 15:26:03 | `074`-`075` | Restored the public Azure connection/site mapping and the original CPE loopback, XFRM routes, FRR neighbors and filter state. |
| 15:27:00 | `077` | Removed only the newly added gateway APIPA addresses; operation completed after 10m55s. |
| 15:38:04 | `078`-`080` | Verified restored Azure objects, four established SAs, original CPE configuration, ER/private peering health, GCP Partner BGP Up and unchanged Megaport products. |
| 15:39:50 | `084`-`085` | Regenerated the blocked handoff inventory, passed sanitization and confirmed a full authenticated Terraform plan had no changes. |
| 15:40:50 | `089` | Verified the coherent remediation outcome commit and left unrelated concurrent worktree changes untouched. |

## Control-plane and data-plane conclusion

The authorized correction successfully persisted the intended configuration and preserved every underlay/IPsec dependency, but Azure continued initiating public BGP from its default gateway addresses and the corrected custom public sessions never formed. The acceptance condition required four established sessions with unique private and public tuples, so the attempt failed and rollback was mandatory. This evidence leaves the configuration/API association unresolved; it does not demonstrate that custom APIPA is unsupported.

Post-rollback evidence confirms four established IKE/ESP SAs, healthy Azure/GCP/Megaport provider paths, original public-site and connection mappings, original CPE routes/FRR state, and Terraform closure. No validation fault, retry, resource order or cleanup followed.
