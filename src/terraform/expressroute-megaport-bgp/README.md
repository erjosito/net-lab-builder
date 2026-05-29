# expressroute-megaport-bgp Terraform

Terraform root module for lab `expressroute-megaport-bgp`: Azure Spain Central VNet + Madrid ExpressRoute circuit/gateway + Megaport Frankfurt MCR/VXCs.

## Prerequisites

- Azure CLI logged in and set to the intended subscription (`az account set --subscription <id>` outside this repo).
- Terraform installed.
- Megaport provider environment variables present in the process running Terraform:
  - `MEGAPORT_ACCESS_KEY`
  - `MEGAPORT_SECRET_KEY`
- SSH public key at `~/.ssh/id_rsa.pub`, or override `ssh_public_key_path`.

Do not commit service keys, Megaport secrets, private SSH keys, or Terraform state files.

## Quickstart

```powershell
cd C:\Users\jomore\Repos\net-lab-builder\src\terraform\expressroute-megaport-bgp
$env:MEGAPORT_ACCESS_KEY = [Environment]::GetEnvironmentVariable('MEGAPORT_ACCESS_KEY', 'User')
$env:MEGAPORT_SECRET_KEY = [Environment]::GetEnvironmentVariable('MEGAPORT_SECRET_KEY', 'User')
$env:ARM_SUBSCRIPTION_ID = az account show --query id -o tsv
terraform init -upgrade
terraform validate
terraform fmt -recursive
terraform plan -out=tfplan
terraform apply tfplan
```

## Design notes

- VM size is `Standard_B2als_v2` and the VM intentionally has no `zone` attribute, allowing Azure to place it in an available Spain Central zone.
- `azurerm_virtual_network.bgp_community` sets Azure VNet community `12076:20031`. If a future AzureRM provider removes this argument, use `azapi_update_resource` against the VNet with API version `2024-05-01` and `properties.bgpCommunities.virtualNetworkCommunity`.
- Megaport MCR PoP defaults to `Equinix Frankfurt FR5` (location ID 131), discovered from the Megaport locations API after the Madrid/Spain market restriction.
- Megaport Terraform provider v1 models Azure VXCs with `megaport_vxc` resources. It maps to Megaport Azure VXC ordering and must remain tied to the parent MCR via `a_end.requested_product_uid`.
- MCR-side outbound community tagging `65031:100` is not exposed by the provider; see `megaport.tf` TODO.

## Cleanup warning

Do not rely on `terraform destroy` for this lab. The required cleanup chain is:

1. Azure ER connection.
2. Azure ER private peering if Azure exposes a removable Megaport-owned peering object.
3. Megaport VXCs.
4. Megaport MCR.
5. Azure resource group.

Phase 3.4 cleanup should perform that manual sequence, leave state intact for validation first, then remove out-of-band deleted resources from Terraform state.

Manifest: `labs/expressroute-megaport-bgp/manifest.md`
