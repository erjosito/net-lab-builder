# Design C Phase 1B — Evidence

**Verdict:** ✅ Design C single-CR topology live; Design B asymmetric path resources removed

**Date:** 2026-06-15  
**Operator:** Tank (IaC Engineer)

---

## Plan-Show Summary

```
Plan: 0 to add, 0 to change, 2 to destroy.
```

Resources destroyed:
1. `google_compute_interconnect_attachment.att_b_new` — `att-vwan-symm-b-new` (europe-west4, state=DEFUNCT)
2. `google_compute_router.cr_onprem_b` — `cr-vwan-symm-onprem-b` (europe-west4)

No kill-switch triggered. No Azure, Megaport, subnet, or VM resources touched.

---

## Apply Duration

**~30 seconds** (att_b_new destroyed in 11s, cr_onprem_b destroyed in 11s, sequential)

---

## Pre-Flight Evidence

| Check | Result |
|---|---|
| `att-vwan-symm-b-v2` state | **ACTIVE** |
| `router-vwan-symm-a` BGP peers | **2 peers, both UP** (GCP uses "UP" for established BGP) |
| BGP peer `auto-ia-bgp-att-vwan-symm-a-*` | UP, 8 learned routes |
| BGP peer `auto-ia-bgp-att-vwan-symm-b-*` | UP, 8 learned routes |

---

## Post-Flight Evidence

### BGP Peers (router_a after apply)

```
{ "name": "auto-ia-bgp-att-vwan-symm-a-748c416bf214189", "status": "UP" }
{ "name": "auto-ia-bgp-att-vwan-symm-b-8a45a420e5e4bb7", "status": "UP" }
```

2 peers, both UP. No regression.

### Interconnect Attachments

```
NAME                REGION        STATE   ROUTER
att-vwan-symm-a     europe-west3  ACTIVE  router-vwan-symm-a
att-vwan-symm-b-v2  europe-west3  ACTIVE  router-vwan-symm-a
```

`att-vwan-symm-b-new` is GONE. Only `att_a` and `att_b_v2` remain, both in eu-w3, both on `router_a`.

### Cloud Routers

```
NAME                REGION        NETWORK
router-vwan-symm-a  europe-west3  vpc-vwan-symm-a-103167
```

`cr-vwan-symm-onprem-b` is GONE. Only `router_a` remains.

### Subnets (vpc_a)

```
NAME                       REGION        RANGE
subnet-vwan-symm-a         europe-west3  10.50.1.0/24
subnet-vwan-symm-onprem-b  europe-west4  10.50.2.0/24
```

Both subnets intact. `vm_b` subnet in eu-w4 preserved.

### VMs

```
NAME            ZONE            STATUS   NETWORK_IP
vm-vwan-symm-a  europe-west3-a  RUNNING  10.50.1.2
vm-vwan-symm-b  europe-west4-a  RUNNING  10.50.2.2
```

Both VMs RUNNING. Preserved per Jose's directive.

---

## What's Now Live (Design C topology)

- **router_a** (eu-w3, `vpc-vwan-symm-a-103167`) with **2 PARTNER Interconnect attachments**:
  - `att-vwan-symm-a` → MCR1 (eu-w3, AVAILABILITY_DOMAIN_1) — BGP **UP**
  - `att-vwan-symm-b-v2` → MCR2 (eu-w3, AVAILABILITY_DOMAIN_2) — BGP **UP**
- New Megaport VXC on MCR2 → europe-west3 (paired to `att_b_v2` via key `326ba0de-2aed-4eb2-aaf4-2df34108dc07/europe-west3/2`) — **portal-managed** (not yet in TF)
- `vm_a` (eu-w3-a, 10.50.1.2) + `vm_b` (eu-w4-a, 10.50.2.2) — both RUNNING

---

## What's Gone

| Resource | Type | How removed |
|---|---|---|
| `att-vwan-symm-b-new` | GCP interconnect attachment (eu-w4) | `terraform apply` |
| `cr-vwan-symm-onprem-b` | GCP Cloud Router (eu-w4) | `terraform apply` |
| `megaport_vxc.gcp_b` (UID `2c2fd022-b0ce-438a-aee9-69f27daa43a2`) | TF state entry | `terraform state rm` |

TF code blocks also removed from:
- `src/terraform/vwan-dual-er-symmetric/megaport.tf` (lines 177-195, former `resource "megaport_vxc" "gcp_b"`)
- `src/terraform/vwan-dual-er-symmetric/gcp.tf` (former `cr_onprem_b` + `att_b_new` blocks)
- `src/terraform/vwan-dual-er-symmetric/outputs.tf` (3 output references updated)

---

## Hand-off Note for Niobe

**Ready for Design C asymmetric baseline evidence capture.**

Design C single-CR topology is confirmed live:
- One Cloud Router (`router_a`, eu-w3) with two BGP peers (both UP)
- Two PARTNER attachments both in eu-w3 (DOMAIN_1 and DOMAIN_2 for edge diversity)
- Two VMs in different regions (eu-w3-a and eu-w4-a) for cross-region routing visibility

Suggested capture targets:
- GCP Cloud Router BGP best-path decision (`gcloud compute routers get-status router-vwan-symm-a`)
- Azure vHub effective routes for both hubs
- Traceroute from vm_a → Azure spoke VMs (and return path)
- Traceroute from vm_b → Azure spoke VMs (cross-region return path difference)
