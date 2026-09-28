# vwan-ipsec-over-er-backup

> Blog post: _pending publication_ (Kid)

## Designs studied

### Design D1: One floating BGP adjacency across private and public tunnels - rejected offline

**Status:** Teaching-only; rejected without a live D1 mutation.
**Verdict:** VPN-over-ER requires a regular-private CPE BGP peer while connection-specific custom vWAN peers require APIPA, so one unchanged identity cannot float across both supported link models.

**What it is:** Both the private VPN-over-ExpressRoute link and the public Internet VPN link attempt to use the same CPE BGP identity (`65050 / 10.250.254.242`). The experiment asks whether one unchanged adjacency can move between managed vWAN link endpoints.

**Evidence:**
- `show-output/deployment-blocker-2026-09-28/` - live peer-source discovery
- `evidence-index.md` - audit coverage and transcript gaps
- `validation-plan.md` - D1 prerequisite and verdict gates
- `design.md` sections 4-6 - endpoint isolation, four XFRM slots and D1 experiment

**Why this verdict:** The live deployment proved that regular-private peers collapse both path classes onto the same two default Azure BGP sources. Changing the ER peer to APIPA would violate the documented VPN-over-ER boundary. Trinity therefore rejected D1 offline and prohibited a live mutation.

**Use this design when:**
- Teaching why managed endpoint and link identity can prevent a traditional floating-neighbor pattern.

**Avoid this design when:**
- Production requires independently observable private and public failure domains.

### Design D2: Separate BGP adjacencies with deterministic preference - bounded correction failed

**Status:** One authorized attempt completed and rolled back.
**Verdict:** The corrected mixed private/APIPA model did not produce four unique sessions. Azure persisted the public APIPA peer and custom mappings but continued sourcing public TCP/179 from the default gateway addresses.

**What it is:** Private sessions use Azure defaults `10.240.0.12/.13` from CPE source `10.250.254.240`; public sessions use custom peers `169.254.22.2/.3` from CPE source `169.254.22.1`. Route policy makes the ER-carried overlay primary and Internet backup.

**Evidence:**
- `show-output/d2-corrected/` - bounded correction, baseline, fault and restore captures
- `evidence-index.md` - command-level audit ledger
- `validation-plan.md` - D2 path-selection and fault matrix
- `design.md` sections 5, 7 and 10 - four-neighbor model, AS-path/local-preference policy and faults

**Why this verdict:** The CPE had the required APIPA loopback, XFRM routes, active FRR neighbors, and four healthy SAs. During the bounded capture, `169.254.22.2/.3` received no messages while public XFRM interfaces received BGP SYNs from `10.240.0.12/.13`. The attempt met its explicit rollback condition and was not retried.

**Use this design when:**
- Private and public transports must have independent health, policy and withdrawal.

### Design D3: ER more-specific BGP routes with Internet static aggregate - evidence pending

**Status:** _Pending evidence; deterministic but health-blind candidate._
**Verdict:** No result is claimed until longest-prefix selection, normal backup behavior and the Internet-down-then-primary-down blackhole sequence are captured.

**What it is:** The ER overlay advertises `10.253.3.0/25` and `10.253.3.128/25`; the Internet link retains the covering static `10.253.3.0/24`. Longest-prefix match selects ER while the more-specifics exist, but the static aggregate can remain installed after its transport has failed.

**Evidence:**
- `show-output/d3-prefix/` - pending normal, compound-fault and restore captures
- `validation-plan.md` - D3 route hierarchy and blackhole criteria
- `design.md` sections 8-10 - prefix hierarchy, reverse distance-250 route and compound fault

**Why this verdict:** Pending execution. The compound test must first make the Internet backup unusable, then withdraw the ER/BGP more-specifics and prove whether the still-installed aggregate blackholes traffic.

**Use this design when:**
- A lab needs to demonstrate deterministic longest-prefix behavior and the limits of a health-blind static backup.

**Avoid this design when:**
- Backup route installation must track tunnel or application health automatically.

## Readiness

Azure, GCP, ExpressRoute, Partner Interconnect, the Amsterdam MCR, all three VXCs, and all four IKE/ESP SAs are live. The ignored `config/inventory.json` contains exact resource identifiers, versioned managed-route queries, effective and configured BGP peers, the read-only Megaport collector, application endpoints, and reviewed fault/restore commands.

Niobe must not execute D2/D3 faults. The bounded public-link APIPA correction failed its four-session assertion and the runtime inventory remains `validationAuthorized=false`. D1 remains prohibited.

## Evidence layout

- `show-output/deployment-audit/<correlation-id>/`
- `show-output/deployment-blocker-2026-09-28/`
- `show-output/d1-rejected-offline/`
- `show-output/d2-corrected/<correction-or-fault>/<before|action|during|restore|after|assertion>/`
- `show-output/d3-prefix/<fault-or-restore>/<timestamp>/`
- `show-output/compound/<timestamp>/`
- `show-output/final-healthy/<timestamp>/`

All committed evidence must pass `scripts/Confirm-Sanitization.ps1`.

See `evidence-index.md` for the detailed local audit ledger. The eventual blog post should summarize findings rather than duplicate this command-level record.
