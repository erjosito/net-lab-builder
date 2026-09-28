# vwan-ipsec-over-er-backup

> Blog post: _pending publication_ (Kid)

## Designs studied

### Design D1: One floating BGP adjacency across private and public tunnels - evidence pending

**Status:** _Pending evidence; teaching-only hypothesis._
**Verdict:** No result is claimed until the supported Azure site/link model is attempted and the failure stage is isolated from configuration defects.

**What it is:** Both the private VPN-over-ExpressRoute link and the public Internet VPN link attempt to use the same CPE BGP identity (`65050 / 10.250.254.242`). The experiment asks whether one unchanged adjacency can move between managed vWAN link endpoints.

**Evidence:**
- `show-output/d1-floating/` - pending API, IKE/IPsec, BGP, route, packet and probe captures
- `validation-plan.md` - D1 prerequisite and verdict gates
- `design.md` sections 4-6 - endpoint isolation, four XFRM slots and D1 experiment

**Why this verdict:** Pending execution. An Azure API rejection or a failed BGP re-establishment is meaningful only after underlay reachability, endpoint mapping, PSKs, tunnel state, host routes and FRR syntax are independently proven correct.

**Use this design when:**
- Teaching why managed endpoint and link identity can prevent a traditional floating-neighbor pattern.

**Avoid this design when:**
- Production requires independently observable private and public failure domains.

### Design D2: Separate BGP adjacencies with deterministic preference - provider limitation found

**Status:** _Blocked before scenario execution._
**Verdict:** The four IPsec SAs establish, but the frozen non-APIPA CPE BGP identities cannot produce four independent Azure peer tuples. Azure uses the two default gateway BGP addresses for regular private remote peers, even when four custom APIPA addresses are selected on the connection objects.

**What it is:** The private and public sites use different CPE peer identities (`10.250.254.240` and `10.250.254.241`) and distinct active-active vWAN tunnel tuples. Route policy makes the ER-carried overlay primary and the Internet overlay backup in both directions.

**Evidence:**
- `show-output/d2-separate/` - pending baseline, fault and restore captures
- `validation-plan.md` - D2 path-selection and fault matrix
- `design.md` sections 5, 7 and 10 - four-neighbor model, AS-path/local-preference policy and faults

**Why this verdict:** Live packet capture shows Azure initiating TCP/179 from the two default gateway addresses on both private and public XFRM paths. Microsoft documentation states that the corresponding custom Azure APIPA address is used only when the remote BGP peer is APIPA; regular private peers use the automatically assigned gateway address. This triggers the explicit `design.md` section 13 stop condition because four unique neighbor tuples cannot be routed through four distinct XFRM slots.

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

Niobe must not execute D1/D2/D3 faults against this deployment. The section-13 addressing blocker must first be resolved by an approved design change, such as APIPA CPE BGP identities paired per connection, or by reducing the requirement to the two effective Azure peer addresses. Neither change was authorized in the frozen design.

## Evidence layout

- `show-output/baseline/<timestamp>/`
- `show-output/d1-floating/<timestamp>/`
- `show-output/d2-separate/<fault-or-restore>/<timestamp>/`
- `show-output/d3-prefix/<fault-or-restore>/<timestamp>/`
- `show-output/final-healthy/<timestamp>/`

All committed evidence must pass `scripts/Confirm-Sanitization.ps1`.
