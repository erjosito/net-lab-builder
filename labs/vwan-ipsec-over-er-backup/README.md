# vwan-ipsec-over-er-backup

> Blog post: _pending publication_ (Kid)

## Designs studied

### Design D1: One ordinary BGP adjacency moved between underlays - rejected

**Status:** Executed under route-only movement and complete ExpressRoute transport loss.
**Verdict:** **Rejected.** Moving the CPE route can keep the unchanged BGP tuple established over the public tunnel only while Azure can still return through ExpressRoute. When all ER transport was removed, the CPE sent repeated TCP/179 SYNs from `10.250.254.242` through `xfrm-pub1`, but Azure returned no SYN-ACK and BGP remained `Connect`.

**What it is:** Configure one normal CPE loopback (`65050 / 10.250.254.242`) and one Azure default vWAN BGP neighbor. Keep the BGP tuple unchanged while switching only the Azure-neighbor `/32` route between the ER/private and Internet/public XFRM tunnels.

**Evidence:**
- `show-output/d1-final-corrected/20260929T073900Z/07-float-observation.txt` - BGP continuity during the route-only asymmetric move while ER remained available
- `show-output/d1-full-er-negative/20260929T124028Z/README.md` - clean full-ER negative proof and restore
- `design.md` section 6 - D1 tuple and peer-route model

**Why this verdict:** The clean outage retry removed every inactive CPE BGP identity, leaving only `.242`; the neighbor route pointed to `xfrm-pub1`; the public SAs remained established; and all Megaport VXCs were down. Packet capture showed outbound `.242 -> 10.240.0.12:179` SYN retransmissions with no response for more than three minutes. Azure has no mechanism to transfer the ER connection's peer identity to the Internet connection.

**Avoid this design when:**
- VPN over the Internet must provide backup after actual ER transport loss.

### Design D2: Separate BGP adjacencies with deterministic preference - validated

**Status:** Full-ER failover and failback executed with four established IPsec SAs and four independent BGP adjacencies.
**Verdict:** **Recommended.** Complete ER loss withdrew the two private adjacencies after their failure-detection timers expired, selected both public APIPA adjacencies, and restored bidirectional payload. Restoring ER and initiating the already-configured private children recovered both private adjacencies, restored private preference, and passed payload with no PSK or StrongSwan configuration change.

**What it is:** Private sessions use Azure defaults `10.240.0.12/.13` from CPE source `10.250.254.240`; public sessions use custom peers `169.254.21.5` and `169.254.22.5` from CPE source `169.254.21.6`. Route policy makes the ER-carried overlay primary and Internet backup.

**Evidence:**
- `show-output/d2-full-er/20260929T174957Z/README.md` - full-ER failover, convergence and failback summary
- session evidence `files/d2-full-er-20260929/` - timestamped failover and failback monitors
- `evidence-index.md` - command-level audit ledger
- `validation-plan.md` - D2 path-selection and fault matrix
- `design.md` sections 5, 7 and 10 - four-neighbor model, AS-path/local-preference policy and faults

**Why this verdict:** Before the fault, all four sessions were established and private local preference `200` beat public local preference `100`. Shutting the single GCP VXC removed both MSEE paths while preserving Internet transport. Payload first failed at about `17:51:55Z`; the last private route withdrew and the public pair became best at about `17:54:15Z`, producing an observed stale-private-path outage of roughly 140 seconds. Payload then passed over public. After ER restoration, the two private children and BGP sessions recovered, the private pair became best again, and a five-packet payload probe passed with 0% loss.

**Operational note:** The subsequent D3-to-D2 routing-mode restore re-enabled Azure public BGP without changing IPsec. Azure retained the custom APIPA configuration, and CPE SYNs traversed both public XFRM interfaces, but Azure did not answer them while the existing public SAs remained established. Restoring those standby sessions may require tunnel re-establishment, which was intentionally not attempted because the lab invariant forbids further IPsec changes. This does not invalidate the earlier complete D2 failover/failback test.

**Use this design when:**
- Private and public transports must have independent health, policy and withdrawal.

### Design D3: ER more-specific BGP routes with Internet static aggregate - validated with blackhole caveat

**Status:** Normal preference, healthy static failover and the mandatory compound failure were executed.
**Verdict:** **Mechanically valid but not production-safe without health-driven route withdrawal.** The `/25` private routes win normally and the public `/24` carries traffic after private BGP withdrawal when Internet transport is healthy. If public transport fails first, the same installed static route blackholes traffic after private withdrawal.

**What it is:** The ER overlay advertises `10.253.3.0/25` and `10.253.3.128/25`; the Internet link retains the covering static `10.253.3.0/24`. Longest-prefix match selects ER while the more-specifics exist, but the static aggregate can remain installed after its transport has failed.

**Evidence:**
- `show-output/d3-prefix/20260929T181517Z/README.md` - normal, healthy failover and compound blackhole proof
- `validation-plan.md` - D3 route hierarchy and blackhole criteria
- `design.md` sections 8-10 - prefix hierarchy, reverse distance-250 route and compound fault

**Why this verdict:** With private BGP active, both `/25`s were advertised and both test sources passed over the private overlay. After private BGP shutdown, the CPE selected its distance-250 public XFRM route and payload passed once Azure's static `10.253.3.0/24` route was configured. In the compound test, public transport was blocked first while private payload still passed; private BGP was then withdrawn, the static public route remained best, both probes failed with 100% loss, and the public-fault counter increased. All four SAs still appeared established, proving that route installation alone did not represent usable backup health.

**Use this design when:**
- A lab needs to demonstrate deterministic longest-prefix behavior and the limits of a health-blind static backup.

**Avoid this design when:**
- Backup route installation must track tunnel or application health automatically.

## Readiness

Azure, GCP, ExpressRoute, Partner Interconnect, the Amsterdam MCR, all three VXCs, and all four IKE/ESP SAs are live. The ignored `config/inventory.json` contains exact resource identifiers, versioned managed-route queries, effective and configured BGP peers, the read-only Megaport collector, application endpoints, and reviewed fault/restore commands.

D1 is complete and rejected. D2 full-ER failover and failback succeeded. D3 normal backup behavior and its stale-static-route blackhole were reproduced. The live lab is back on D2 with all four IPsec SAs, both private BGP adjacencies, private best-path selection and payload healthy. The two public standby BGP adjacencies did not re-establish after the D3-to-D2 Azure BGP-mode toggle; no tunnel restart or IPsec change was attempted.

## Evidence layout

- `show-output/deployment-audit/<correlation-id>/`
- `show-output/deployment-blocker-2026-09-28/`
- `show-output/d1-single-adjacency/`
- `show-output/d2-corrected/<correction-or-fault>/<before|action|during|restore|after|assertion>/`
- `show-output/d3-prefix/<fault-or-restore>/<timestamp>/`
- `show-output/compound/<timestamp>/`
- `show-output/final-healthy/<timestamp>/`

All committed evidence must pass `scripts/Confirm-Sanitization.ps1`.

See `evidence-index.md` for the detailed local audit ledger. The eventual blog post should summarize findings rather than duplicate this command-level record.
