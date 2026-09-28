# Bounded D2 APIPA remediation result

**Result:** failed acceptance gate and rolled back. No retry was performed.

## Applied once

- Private CPE peer remained `10.250.254.240`.
- Public site peer changed to `169.254.22.1`.
- Azure public custom peers persisted as `169.254.22.2` and `169.254.22.3`.
- Public CPE routes used `xfrm-pub0` and `xfrm-pub1` with source `169.254.22.1`.
- FRR actively connected to both custom public peers.
- StrongSwan, PSKs, all four IPsec SAs, and all provider resources were unchanged.

## Failure evidence

After the bounded convergence wait:

```text
10.240.0.12     Established, 2 prefixes received
10.240.0.13     Active after a transient establishment
169.254.22.2    Connect, 0 messages received
169.254.22.3    Connect, 0 messages received
```

Packet capture on both public XFRM interfaces showed Azure initiating TCP/179 from the default gateway addresses `10.240.0.12/.13` toward the CPE APIPA address. No packets sourced from `169.254.22.2/.3` were observed.

All four route assertions resolved to their intended XFRM interfaces, and all four IKE/ESP SAs remained established. The failure was therefore the explicit provider-addressing condition rather than missing CPE routes, failed IPsec, or degraded underlay.

## Rollback

The public site peer, public connection mappings, CPE loopback/routes/FRR/filter state, and newly added gateway custom addresses were restored to their pre-attempt values.

```text
IKE/ESP SAs: 4 established
ExpressRoute provider state: Provisioned
Azure private peering: Succeeded
GCP Partner BGP: Up
Megaport products: unchanged
Overlay BGP: original four neighbors, not established
```
