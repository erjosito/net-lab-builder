# sap-rise-scoped-peering-fwaas — deploy

IaC lives in `src/terraform/sap-rise-scoped-peering-fwaas/` (reusable module, follows the
`expressroute-megaport-bgp` lab's established Terraform + Megaport provider pattern).
This directory holds the lab-specific glue: `deploy.ps1`, `cleanup.ps1`.

## Prerequisites

- Azure CLI logged in, subscription set.
- Terraform installed (tested with 1.11.4).
- Megaport Terraform provider credentials in HKCU env vars `MEGAPORT_ACCESS_KEY` /
  `MEGAPORT_SECRET_KEY` (rehydrated automatically by both scripts).
- SSH key at `~/.ssh/id_rsa.pub` (required by the VM resource schema; not used for
  network access — no public IPs are deployed, all VM config/diagnostics go through
  `az vm run-command`).

## Deploy

```powershell
cd C:\Users\jomore\Repos\net-lab-builder\labs\sap-rise-scoped-peering-fwaas\deploy
.\deploy.ps1
```

Deploys the S1 baseline (ARS + hub-NVA BGP redistribution active, `summarizedGatewayPrefixes`
unset). ~45-70 min wall-clock, dominated by the `ErGw1AZ` gateway (20-45 min) in parallel
with the Megaport MCR/circuit/VXC chain and Route Server provisioning.

## Scenario toggle (S2)

Both scenarios validate against the same deployed base (design.md section 10):

```powershell
cd C:\Users\jomore\Repos\net-lab-builder\src\terraform\sap-rise-scoped-peering-fwaas
terraform apply -var enable_summarized_gateway_prefixes=true   # S2 capture
terraform apply -var enable_summarized_gateway_prefixes=false  # revert to S1-only
```

Per design.md section 8, disable the hub NVA's BIRD static-route export (via
`az vm run-command`, comment out `protocol static { route 10.60.0.0/16 ... }` and
restart bird) before an S2-only capture, so the two mechanisms aren't conflated.

## Cleanup

```powershell
.\cleanup.ps1
```

Runs `terraform destroy` (dependency graph already encodes manifest.md section 5's
ordering: de-peer → connection delete → gateway delete → circuit delete → VXC delete →
MCR delete → VNets → RG), then a safety-net RG existence check. **Verify Megaport
MCR/VXC are actually gone afterward** — Megaport has no hourly billing, so an orphaned
VXC/MCR costs a full extra month, not a few dollars.

## Deviations from design.md — see decision inbox

`.squad/decisions/inbox/tank-sap-rise-deploy.md` documents:
- Simulated on-prem/CE realized as an Azure VM peered directly to `vnet-hub`, not a
  Megaport MVE or physical CE.
- Bastion dropped in favor of `az vm run-command` for all VM management (no public IPs
  on any lab VM) — a cost reduction, not a scope reduction.
