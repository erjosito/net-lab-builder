# D1 full-ExpressRoute outage negative proof

## Verdict

Option 1 is not a viable ER-to-Internet failover design in this vWAN topology.

The CPE can move its unchanged BGP peer route from the ER-backed tunnel to the
Internet-backed tunnel. Azure does not move the corresponding CPE peer identity
from the ER VPN connection to the Internet VPN connection after ER transport is
removed.

## Clean test conditions

- IPsec configuration and PSKs were unchanged.
- The CPE retained only the D1 BGP identity `10.250.254.242`; inactive `.240`,
  `.241`, and APIPA BGP identities were absent.
- The route to Azure peer `10.240.0.12/32` used `xfrm-pub1` with source
  `10.250.254.242`.
- The Megaport Azure primary, Azure secondary, and GCP VXCs reported
  `shutdown=true`, `up=false`, and BGP status `0`.
- The Internet-backed SAs remained established.

## Observation

From `2026-09-29T12:40:28Z`, FRR remained in `Connect` with zero BGP messages.
The public-tunnel capture recorded repeated TCP SYNs such as:

```text
10.250.254.242.<ephemeral> > 10.240.0.12.179: Flags [S]
```

No SYN-ACK or other response from `10.240.0.12` appeared during the bounded
observation. This is the expected failure when Azure retains the BGP peer
identity on the ER VPN connection.

An earlier capture was excluded because a leftover `10.250.254.241` loopback
allowed the BGP-enabled public connection to initiate a different session. The
clean retry removed that identity before collecting the verdict evidence.

## Restore

- All VXCs were set to `shutdown=false` and returned `up=true`, BGP status `1`.
- The ER VPN site peer was restored to `10.250.254.240`.
- The Internet VPN site peer was restored to `169.254.21.6`.
- `pri0`, `pri1`, `pub0`, and `pub1` remained established.
- All four D2 BGP adjacencies re-established.

The tested reversible provider fault uses Megaport's direct VXC update API:

```text
PUT /v3/product/vxc/{uid}/
{"shutdown":true}
```

Restore uses the same request with `false`. The repository wrapper is
`deploy/Invoke-LabFault.ps1`; `-Fault gcp-vxc` is the simplest complete ER
transport fault because one GCP VXC carries both MSEE paths.
