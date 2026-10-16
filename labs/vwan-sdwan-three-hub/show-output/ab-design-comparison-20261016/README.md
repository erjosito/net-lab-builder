# A/B backbone selection with secured Virtual WAN hubs

All three hubs have Azure Firewall and PrivateTraffic routing intent. These
are synthetic Azure-only DCs. EU and US use peered-VNet BGP connections, not
integrated SD-WAN gateways. Japan uses BGP over S2S VPN. China has only mesh
connectivity and must select another DC as its Azure ingress.

**A means Microsoft backbone preferred. B means customer backbone preferred.**
B1 and B2 are two candidate implementations of B, not of A.

| Configuration | Hub preference | NVA policy | Measured result |
| --- | --- | --- | --- |
| A: Microsoft backbone | ASPath on all hubs | EU/US/JP add three extra own-AS copies for nonlocal DC exports. Azure imports accept foreign DCs and spokes at local-pref 400, above mesh local-pref 300/100. | Firewalls and Azure-facing NVAs select the remote Azure paths. This is a combined policy, not an isolated prepend threshold. |
| B1: customer backbone via HRP | ExpressRoute on all hubs | EU/US add two extra own-AS copies for nonlocal DC exports. Original spoke-only Azure imports and mesh preferences remain. JP adds none. | **Not reproduced:** EU/US firewalls retain the remote Japan path. NVA mesh selections alone do not establish the intended hub decision. VPN HRP was not measured. |
| B2: customer backbone via ASPath | ASPath on all hubs | EU/US nonlocal extra prepends removed; JP still adds none. Original spoke-only Azure imports and mesh preferences remain. | **Route-selection assertions passed:** EU/US select their local mesh Japan route and Japan selects its local mesh EU route through its VPN ingress. |

## Matched evidence

Each scenario directory contains all three firewalls' complete effective-route
tables, all four NVA configurations, full selected/alternative BIRD routes and
Azure export views. Table 2 is the later of two captures spaced by at least
120 seconds; DC-prefix winner stability was checked, not stability of every
control prefix in the full table.

| Observation point | A | B1 | B2 |
| --- | --- | --- | --- |
| EU firewall, full effective table | [Table](../backbone-policy-design-20261016/nva-policy-and-jp-udr/nva-policy-and-jp-udr-eu-table2.txt) | [Table](../ab-b1-customer-20261016/B1/B1-eu-table2.txt) | [Table](../ab-b2-customer-20261016/B2/B2-eu-table2.txt) |
| Japan firewall, full effective table | [Table](../backbone-policy-design-20261016/nva-policy-and-jp-udr/nva-policy-and-jp-udr-jp-table2.txt) | [Table](../ab-b1-customer-20261016/B1/B1-jp-table2.txt) | [Table](../ab-b2-customer-20261016/B2/B2-jp-table2.txt) |
| All NVA selected DC/spoke routes | [Routes](../backbone-policy-design-20261016/nva-policy-and-jp-udr/selected-routes.json) | [Routes](../ab-b1-customer-20261016/B1/selected-routes.json) | [Routes](../ab-b2-customer-20261016/B2/selected-routes.json) |
| EU NVA configuration | [Config](../backbone-policy-design-20261016/nva-policy-and-jp-udr/router-eu.conf) | [Config](../ab-b1-customer-20261016/B1/router-eu.conf) | [Config](../ab-b2-customer-20261016/B2/router-eu.conf) |
| Japan NVA configuration | [Config](../backbone-policy-design-20261016/nva-policy-and-jp-udr/router-jp.conf) | [Config](../ab-b1-customer-20261016/B1/router-jp.conf) | [Config](../ab-b2-customer-20261016/B2/router-jp.conf) |
| China NVA configuration | [Config](../backbone-policy-design-20261016/nva-policy-and-jp-udr/router-cn.conf) | [Config](../ab-b1-customer-20261016/B1/router-cn.conf) | [Config](../ab-b2-customer-20261016/B2/router-cn.conf) |

For B1 the offered EU Japan path is `65011-65011-65011-65013` (four ASNs,
including automatic eBGP insertion). Its firewall still selected
`65520-65520-65013` (three ASNs, Remote Hub). US behaved equivalently.
This one-ASN difference must not be explained using the documented example
where the local path is at least two ASNs longer. The reason for this result
has not been established.

For B2 the selected local EU and US Japan paths are respectively
`65011-65013` and `65012-65013`, with `HubBgpConnection` next hops.
Japan selects `65013-65011` through `VPN_S2S_Gateway` for the EU DC.
These are shorter than the three-ASN remote alternatives.

## Verdicts, restoration and forwarding limits

- [A original report and forwarding limits](../backbone-policy-design-20261016/README.md):
  a temporary five-prefix Japan workload UDR was required for the measured
  Japan workload/EU spoke success. DC-to-DC regressions remain. Some selected
  Japan BIRD routes have `!`, indicating kernel export failure.
- [B1 original verdict](../ab-b1-customer-20261016/customer-verdict.json):
  **INCONCLUSIVE**, intended customer-first hub assertion failed,
  `restored: true`. This is a negative configuration result, not proof that
  ExpressRoute/VPN HRP can never select a local NVA path.
- [B2 original verdict](../ab-b2-customer-20261016/customer-verdict.json):
  **BLOCKED**, because its lease expired during read-only restoration proof.
  The complete `states.B2` capture passed the route-selection assertions;
  all restore commands had completed. The original verdict is preserved.
- [Independent recovery verification](../ab-final-recovery-verification-20261016/verification-verdict.json):
  **PASS**, exact original configuration bytes/metadata, BGP sessions,
  Japan IKE SA count, mixed HRPs and paired firewall winners verified.
- [Original power inventory restored](../ab-router-power-restore-20261016/power-restore-verdict.json):
  **PASS**. Only the four routers started for these controls were deallocated.
  Six workload probes were not started or changed.

B1/B2 performed no new forwarding probes. A successful control-plane
selection must not be promoted to an all-pairs data-plane or symmetry claim.
Neither a finite prepend threshold nor a full three-HRP matrix is established.

## Collection and bounded controller

The secured firewall command is:

```powershell
az network vhub get-effective-routes -n $hub -g $rg `
  --resource-type 'AzureFirewalls' `
  --resource-id $(az network vhub show -g $rg -n $hub --query 'azureFirewall.id' -o tsv) `
  --query 'value[].{Prefix:addressPrefixes[0], ASPath:asPath, NextHopType:nextHopType}' -o table
```

For an unsecured VNet-connection view the discriminator is
`HubVirtualNetworkConnection` (singular).

The [controller](../../deploy/design_customer.py) transforms only the known
EU/US nonlocal export block and rejects unexpected source. Each mutation run
requires a fresh bounded lease, a named accepted baseline and exact restore.
It does not modify IPsec, WireGuard or workload routing.

```powershell
python design_customer.py --variant baseline --lease <read-only-lease>.json --out <fresh-baseline>
python design_customer.py --variant B1 --lease <fresh-six-mutation-lease>.json --out <fresh-B1> --baseline <fresh-baseline>
python design_customer.py --variant B2 --lease <fresh-six-mutation-lease>.json --out <fresh-B2> --baseline <fresh-baseline>
python design_verify.py --lease <fresh-read-only-lease>.json --out <fresh-verification> --baseline <fresh-baseline>
```

Do not replay the closed leases or treat this command list as permission to
skip independent reset verification between scenarios.
