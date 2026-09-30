# D3 prefix preference and compound failure

## Configuration

- Private site BGP advertised:
  - `10.253.3.0/25`
  - `10.253.3.128/25`
- Public site BGP was disabled.
- Azure public site static address space was `10.253.3.0/24`.
- The CPE retained a public-XFRM route to `10.241.0.0/24` at distance 250.
- eBGP distance 20 preferred the private overlay in normal operation.
- All four existing IPsec SAs remained established throughout routing-only transitions.

## Normal state

Both private BGP sessions established and advertised both `/25`s. The CPE selected both private XFRM paths to `10.241.0.0/24`. Probes sourced from `10.253.3.10` and `10.253.3.138` each passed with 0% loss.

## Healthy static backup

Both private BGP neighbors were administratively shut down without changing IPsec. The CPE selected its distance-250 public XFRM route. After the Azure static aggregate was corrected from the previous D2 prefix to `10.253.3.0/24`, payload over the public tunnel passed.

## Compound failure

1. Private BGP was restored; the private route again became best and payload passed.
2. Public IKE/NAT-T/ESP transport was blocked on the CPE.
3. Payload continued to pass over the private overlay.
4. Both private BGP neighbors were then shut down.

The CPE retained and selected the public distance-250 route, but probes from both D3 source addresses failed with 100% loss. The public-fault packet counter increased while `swanctl --list-sas` still listed all four SAs as established.

## Verdict

D3 provides deterministic longest-prefix preference and a usable static backup while that backup is healthy. It is health-blind: a stale static aggregate remains installed when the public data plane is unusable and blackholes traffic after private BGP withdrawal. Production use requires external health automation that removes and restores the static routes based on tunnel and end-to-end payload health.
