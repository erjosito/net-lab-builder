# Sanitized deployed-state and design-blocker evidence

Captured on 2026-09-28. Subscription IDs, service and pairing keys, provider product IDs, credentials, tokens, PSKs, and other GUIDs are intentionally omitted.

## Healthy deployed layers

```text
Azure vHub: Succeeded; ASPath; 10.240.0.0/24
Azure VPN gateway: Succeeded
Azure ExpressRoute gateway and connection: Succeeded
ExpressRoute circuit: Provisioned; private peering Succeeded
Azure workload: 10.241.0.4

GCP CPE: RUNNING; e2-small; europe-north2-c; forwarding enabled
GCP Partner attachment: ACTIVE
GCP Cloud Router BGP: Established
GCP advertisement toward Megaport: 10.250.0.10/32 only

Megaport MCR: LIVE/UP; Equinix Amsterdam AM1; 1000 Mbps
Azure primary VXC: LIVE/UP; 50 Mbps; Stockholm primary endpoint
Azure secondary VXC: LIVE/UP; 50 Mbps; Stockholm secondary endpoint
GCP VXC: LIVE/UP; 50 Mbps
```

## IPsec smoke

All four IKEv2 SAs and route-based ESP children established. The negotiated suites were:

```text
IKE: AES-256 / SHA-256 / MODP1024
ESP: AES-256 / SHA-256
private paths: native ESP
public paths: ESP-in-UDP NAT-T
```

## BGP blocker proof

The two connection objects selected four distinct custom Azure APIPA addresses, one per instance and path class. The remote site peers remained the frozen regular private identities.

Packet capture on the four XFRM interfaces showed Azure TCP/179 SYNs arriving on every intended tunnel, but sourced from only the two automatically assigned gateway BGP addresses:

```text
private instance 0 and public instance 0: same effective Azure source
private instance 1 and public instance 1: same effective Azure source
configured custom APIPA sources: not used
```

Microsoft documentation states that a regular private remote peer causes VPN Gateway to use its automatically assigned gateway BGP address; the corresponding custom Azure APIPA address is used when the remote peer is APIPA. This conflicts with the frozen design's non-APIPA CPE identities and four-unique-tuple requirement.

`design.md` section 13 therefore stops experiment execution. FRR was not weakened to accept ambiguous duplicate neighbors, and no D1/D2/D3 fault was run.

## Commitment

The pre-order Megaport rack-rate quote was EUR 991.80/month. Azure and GCP managed networking and compute charges remain live. Cleanup was not run.
