# D2 full-ER failover and failback

## Baseline

- Four IPsec SAs established: `pri0`, `pri1`, `pub0`, `pub1`.
- Four BGP sessions established.
- Private neighbors `10.240.0.12/.13` were preferred over public neighbors `169.254.21.5` and `169.254.22.5`.
- Payload from `10.253.2.10` to `10.241.0.4` passed.

## Fault

The GCP Megaport VXC was administratively shut down. This removed both MSEE/ExpressRoute paths while leaving Internet VPN transport available.

- First failed payload probe: approximately `2026-09-29T17:51:55Z`.
- First private neighbor withdrawal: approximately `17:54:02Z`.
- Second private neighbor withdrawal and public pair selected: approximately `17:54:15Z`.
- Approximate stale-private-path outage: 140 seconds.
- Both public APIPA neighbors remained established.
- Both public XFRM routes became active.
- Bidirectional payload passed after convergence.

The observed outage was controlled by transport/BGP failure detection, not by the provider administrative-state change itself.

## Restore

The GCP VXC was restored and all provider paths returned healthy. Azure initiated fresh private IKE, but the CPE initially logged that no matching shared key was found for the inbound initiator identity. No PSK, StrongSwan configuration, XFRM interface or Azure VPN secret was changed.

Initiating the already-configured `pri0` and `pri1` children from the CPE recovered both private SAs. Both private BGP sessions then established, the private pair again became best for `10.241.0.0/24`, and five payload probes passed with 0% loss.

## Verdict

D2 successfully provides end-to-end failover from IPsec-over-ER to Internet IPsec and deterministic failback to the private overlay. The measured failure-detection interval must be considered in production convergence objectives.

## Later routing-mode restore note

After the separate D3 experiment, Azure public BGP was re-enabled while the public SAs remained established. The custom APIPA configuration was still present and CPE SYNs traversed both public XFRM interfaces, but Azure did not answer. Tunnel re-establishment was not attempted because the lab invariant forbids further IPsec changes. This later operational state does not alter the completed D2 failover/failback result above.
