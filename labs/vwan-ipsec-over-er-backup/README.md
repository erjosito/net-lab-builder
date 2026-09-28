# vwan-ipsec-over-er-backup

> Blog post: _pending publication_ (Kid)

## Designs studied

### Design D1: One ordinary BGP adjacency moved between underlays - recipe pending

**Status:** Not executed. Awaiting Trinity's corrected D1 recipe.
**Verdict:** No result is claimed. D1 does not require custom APIPA and is evaluated independently from the D2 APIPA evidence.

**What it is:** Configure one normal CPE loopback (`65050 / 10.250.254.242`) and one Azure default vWAN BGP neighbor. Keep the BGP tuple unchanged while switching only the Azure-neighbor `/32` route between the ER/private and Internet/public XFRM tunnels.

**Evidence:**
- `design.md` section 6 - current D1 concept, subject to Trinity's corrected recipe
- `validation-plan.md` - D1 isolation and future evidence requirements
- `evidence-index.md` - audit coverage once D1 is authorized

**Why this status:** The APIPA correction attempts answer D2 questions only. They are preserved but are neither pass nor fail evidence for D1. No D1 mutation is authorized until Trinity publishes the corrected operation and reset recipe.

**Use this design when:**
- Testing whether one unchanged ordinary BGP tuple can reconnect when only its Azure-neighbor `/32` reachability moves between same-instance XFRM paths.

**Avoid this design when:**
- Production requires independently observable private and public failure domains.

### Design D2: Separate BGP adjacencies with deterministic preference - correction and authorized retry failed

**Status:** The original bounded attempt and one user-authorized clean retry after local GSA disablement both completed and rolled back.
**Verdict:** Neither attempt produced four unique sessions. Azure persisted the public APIPA peer and custom mappings, but the custom peers did not answer CPE-initiated SYNs while Azure continued initiating public TCP/179 from the default gateway addresses. This is a configuration/API association unresolved pending Trinity review, not a demonstrated platform limitation.

**What it is:** Private sessions use Azure defaults `10.240.0.12/.13` from CPE source `10.250.254.240`; public sessions use custom peers `169.254.22.2/.3` from CPE source `169.254.22.1`. Route policy makes the ER-carried overlay primary and Internet backup.

**Evidence:**
- `show-output/d2-corrected/` - bounded correction, baseline, fault and restore captures
- `evidence-index.md` - command-level audit ledger
- `validation-plan.md` - D2 path-selection and fault matrix
- `design.md` sections 5, 7 and 10 - four-neighbor model, AS-path/local-preference policy and faults

**Why this verdict:** The CPE had the required APIPA loopback, XFRM routes, active FRR neighbors, and four healthy SAs. During both bounded captures, `169.254.22.2/.3` received no BGP messages while public XFRM interfaces received BGP from `10.240.0.12/.13`. The retry additionally proves that CPE SYNs reached both custom peers without SYN-ACK or RST. Disabling local GSA removed the WSL DNS warning but did not change the observed result. The exact configuration/API association remains unresolved, the retry met its explicit rollback condition, and no further retry is allowed without Trinity review.

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

Niobe must not execute D2/D3 faults. The public-link APIPA correction and its sole authorized retry both failed the four-session assertion; the runtime inventory remains `validationAuthorized=false`. D1 remains unexecuted pending Trinity's corrected recipe.

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
