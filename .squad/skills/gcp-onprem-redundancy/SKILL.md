# SKILL: GCP on-prem Redundancy via Single GLOBAL-routing VPC

**Confidence:** LOW (first observation, 2026-06-15, lab `vwan-dual-er-symmetric`)  
**Owner:** Trinity  
**Pattern status:** Candidate — validate with Niobe in Design B post-apply evidence before promoting to HIGH.

---

## Pattern summary

Simulating an on-prem multi-region network on GCP using **one VPC with GLOBAL dynamic routing** instead of two separate REGIONAL VPCs. Each GCP region has its own Cloud Router (CR) and Interconnect attachment, but they share a single VPC. GLOBAL routing makes each CR's learned BGP routes (from its Megaport MCR) available VPC-wide — any VM in any region can route via any CR.

## When to use

- Lab requires GCP-as-on-prem simulation with two regional attachment points (two MCRs / two ER circuits).
- Failover between MCRs is desired without adding cross-region Megaport VXCs.
- Design A (two REGIONAL VPCs) was tried first and found to require P2 cross-region VXC patches for failover.

## Topology shape

```
vpc_onprem  (GLOBAL routing)
├── subnet-eu-w3  10.50.1.0/24
│   ├── Cloud Router A  (ASN 16550, eu-w3)  ↔ MCR1 via att_a
│   └── VM-A
└── subnet-eu-w4  10.50.2.0/24
    ├── Cloud Router B  (ASN 16550, eu-w4)  ↔ MCR2 via att_b
    └── VM-B
```

BGP: each CR has ONE peer (its own MCR). No cross-region VXCs.

## CR advertise configuration

Both CRs must advertise **both** GCP subnets for full bidirectional failover:

```hcl
# Cloud Router A (eu-w3) — advertises both subnets
bgp {
  asn            = 16550     # required for PARTNER Interconnect
  advertise_mode = "CUSTOM"
  advertised_ip_ranges {
    range       = "10.50.1.0/24"   # native (eu-w3)
    description = "VM-A subnet native"
  }
  advertised_ip_ranges {
    range       = "10.50.2.0/24"   # remote (eu-w4), via GLOBAL routing
    description = "VM-B subnet via GLOBAL routing — failover path for Azure→VM-B"
  }
}
```

Same pattern for Cloud Router B (eu-w4) advertising both subnets.

## Required MCR prepend policies (two axes)

| Axis | MCR | Prefixes getting 3× prepend | Direction | Purpose |
|---|---|---|---|---|
| Axis 1 (Mechanism B, existing) | MCR1 | Hub2+Spoke3/4 prefixes | MCR→GCP | GCP VMs prefer MCR1 for Hub1, MCR2 for Hub2 |
| Axis 1 (Mechanism B, existing) | MCR2 | Hub1+Spoke1/2 prefixes | MCR→GCP | Symmetric |
| **Axis 2 (Design B new)** | **MCR1** | **10.50.2.0/24 (VM-B subnet)** | **MCR→Azure** | Hub1 prefers MCR2/Hub2 path for VM-B; prevents ECMP |
| **Axis 2 (Design B new)** | **MCR2** | **10.50.1.0/24 (VM-A subnet)** | **MCR→Azure** | Hub2 prefers MCR1/Hub1 path for VM-A |

## Key GCP provider gotcha

`google_compute_network.routing_mode` — check whether your GCP Terraform provider version treats this as ForceNew:
- **Provider 4.x+:** In-place update supported. `terraform plan` shows `~ update`. att_a pairing_key unchanged.
- **Provider 3.x:** ForceNew. Full cascade destroy of vpc_a and dependents. Must create new VPC (`vpc_onprem`) fresh and re-pair all attachments.

**Always run `terraform plan` first. If `-/+` appears on `google_compute_network`, switch to fresh-VPC strategy.**

## Attachment transfer — GCP hard constraint

GCP Partner Interconnect attachments **cannot be transferred** to a different Cloud Router after creation. When migrating from Design A (two VPCs) to Design B (one VPC):
- `att_a`: no change needed if vpc_a routing_mode is updated in-place.
- `att_b`: **must be destroyed + recreated** on the new Cloud Router in vpc_onprem. New `pairing_key` is generated. Megaport VXC `gcp_b` must be updated with the new pairing_key (in-place Megaport update, not VXC destroy).

## Failover behavior with GLOBAL routing

| Event | GCP VM path | Azure path | Converges in |
|---|---|---|---|
| MCR1 / CR-A down | VM-A reroutes via CR-B→MCR2 (Hub1 prefixes with 3× prepend, but only path) | Hub1 falls back to Hub2→MCR2 for 10.50.1.0/24 | ~90 s BGP hold-timer |
| MCR2 / CR-B down | VM-B reroutes via CR-A→MCR1 | Hub2 falls back to Hub1→MCR1 for 10.50.2.0/24 | ~90 s |

Mid-session TCP flows RESET at failover. Stateless/retriable traffic survives.

## Cross-region flow asymmetry [UNVALIDATED]

In steady state, cross-region flows (VM-B↔Hub1, VM-A↔Hub2) traverse two Azure Firewalls per direction. The path ordering is consistent (same FWs see both directions of a TCP connection), but stateful FW drop behavior must be validated with live TCP traffic. This is the primary unknown of the pattern.

## Validation evidence required

- GCP CR `get-status` for both CRs: confirm both advertise both subnets.
- Azure Hub effective routes: confirm 10.50.1.0/24 and 10.50.2.0/24 each have two BGP paths (preferred + prepended).
- Failover test: suspend CR-A BGP, confirm VM-A→Hub1 reconverges within 120 s.
- Cross-region TCP assert: Spoke1↔VM-B and Spoke3↔VM-A — zero AzFW drops.

## Related

- `labs/vwan-dual-er-symmetric/design.md` §2 (Design B full spec)
- `labs/vwan-dual-er-symmetric/show-output/spof-before/` (Design A baseline)
- `.squad/skills/dual-er-symmetry/SKILL.md` (Azure-side Mechanism A/B symmetry)
