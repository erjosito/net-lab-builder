# Addressing and ASN inventory: vwan-dual-er-symmetric

Actual deployed values, sourced from Niobe's captures
(`show-output/spof-before/00-path-matrix.md`,
`show-output/design-c-mechC2-symmetric-2026-06-16/02-gcp-cr-bestroutes-table.txt`).
Two values differ from the original plan in `design.md` section 1.4; see footnotes.

## IP prefix plan

| Component | Prefix | Region | Notes |
|---|---|---|---|
| Hub1 (vWAN) | `10.10.0.0/23` | A: swedencentral | Auto-allocated AzFW / ER GW / RouteServer subnets |
| Hub2 (vWAN) | `10.20.0.0/23` | B: northeurope | Same shape as Hub1 |
| Spoke1 | `10.11.0.0/24` (VM subnet `10.11.0.0/26`) | A | One lab VM |
| Spoke2 | `10.12.0.0/24` (VM subnet `10.12.0.0/26`) | A | One lab VM |
| Spoke3 | `10.21.0.0/24` (VM subnet `10.21.0.0/26`) | B | One lab VM |
| Spoke4 | `10.22.0.0/24` (VM subnet `10.22.0.0/26`) | B | One lab VM |
| GCP VPC subnet eu-w3 | `10.50.1.0/24` | GCP europe-west3 | `vm_a` at `10.50.1.2` |
| GCP VPC subnet eu-w4 | `10.50.2.0/24` | GCP europe-west4 | `vm_b` at `10.50.2.2` (single GLOBAL-routing VPC in Design C) |
| Reserved spare | `10.99.0.0/16` | unallocated | Future anomaly spokes |
| ER private-peering linknets | `169.254.x.x/30` | n/a | Megaport auto-assigned (see peer IPs below) |

## ASN map (as deployed)

| Component | ASN | Role |
|---|---|---|
| MCR1 (Frankfurt FR5) | `65001` | Megaport MCR, Region A |
| MCR2 (Amsterdam AM1) | `65002` | Megaport MCR, Region B |
| GCP Cloud Router (`router_a`, eu-w3) | `16550` | Mandatory GCP Partner-Interconnect ASN (see note 1) |
| Hub1 / Hub2 vWAN BGP (MSEE-facing) | `65515` | vWAN-reserved hub peering ASN (see note 2) |
| vWAN inter-hub propagation marker | `65520` | AS-path prepend marker for cross-hub routes, not a peering ASN |
| MSEE / Azure (ER private peering) | `12076` | Microsoft public ASN, fixed for all ER private peering |
| Symmetry prepend ASN (vWAN Route Maps) | `64496` | RFC 5398 documentation ASN; prepended 3x (Mech C1) / 5x (Mech C2) |

Note 1: `design.md` section 1.4 planned `65003` for the Cloud Router, but GCP PARTNER
Interconnect forces `16550`, so that is the deployed value.

Note 2: `design.md` section 1.4 called the hub ASN `65520`; the live captures confirm the
hub peering ASN is `65515`, and `65520` is only the cross-hub AS-path prepend marker.

## BGP peer / linknet IPs

| Session | ASNs | Peer IPs |
|---|---|---|
| MCR1 to MSEE1 (primary / secondary) | 65001 to 12076 | `169.254.150.121` / `169.254.150.125` |
| MCR2 to MSEE2 (primary / secondary) | 65002 to 12076 | `169.254.148.89` / `169.254.148.93` |
| MCR1 to GCP CR | 65001 to 16550 | `169.254.159.194` to `169.254.159.193` |
| MCR2 to GCP CR | 65002 to 16550 | `169.254.93.154` (Design C re-pair; was `169.254.87.242` in Design B) |
| Hub1 vWAN to MSEE | 65515 to 12076 | `10.10.0.12`, `10.10.0.13` |
| Hub2 vWAN to MSEE | 65515 to 12076 | `10.20.0.12`, `10.20.0.13` |

## Prepend evidence

The symmetry prepend is visible in the GCP Cloud Router best-route table. For `10.11.0.0/24`
(a Region A spoke), the home path via MCR1 wins on AS-path length while the standby path via
MCR2 carries the `64496` prepend:

```
destRange    nextHopIp       asPath
10.11.0.0/24 169.254.159.194 65001 12076
10.11.0.0/24 169.254.93.154  65002 12076 64496 64496 64496 64496 64496
```
