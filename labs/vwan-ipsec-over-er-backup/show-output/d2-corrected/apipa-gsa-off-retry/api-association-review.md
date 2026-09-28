# Custom APIPA configuration/API association review

**Interpretation:** The bounded retry failed its four-session acceptance criterion, but the evidence does not establish a vWAN platform limitation. Custom vWAN APIPA is intended for remote APIPA-only devices. The observed result is therefore classified as **configuration/API association unresolved pending Trinity review**.

## Evidence coverage

| State | Evidence | Coverage |
|---|---|---|
| Before retry | `baseline/20260928T184047551Z-query-before.*` | Full sanitized Azure CLI JSON for the VPN gateway, public VPN site, public VPN connection and private VPN connection. Azure CLI version is preserved, but its internally selected GET API versions were not logged. |
| Active retry | `action/20260928T194251951Z-assertion-during.*`, `action/20260928T194324020Z-configuration-action.*`, `action/20260928T194346544Z-configuration-action.*`, `acceptance/20260928T194504166Z-assertion-assertion.*` | Confirms gateway custom APIPA persistence, site-link peer `169.254.22.1`, connection-link selections `.22.2/.3`, successful provisioning and healthy SAs. These were targeted reads, not full GET bodies. |
| Post-rollback closure | `rollback/20260928T202232067Z-query-after.*` | Full sanitized GET JSON using explicit API version `2025-09-01` for the VPN gateway, public VPN site, public and private VPN connections with embedded link connections, and virtual hub. |

The full active-retry GET bodies were not captured before rollback. A later GET cannot recreate them, so this remains an explicit evidence gap. The targeted active-state reads prove the intended values were persisted, but they do not prove that every parent/child association field was represented exactly as Azure evaluated it.

## Creation and update ordering

| UTC interval | Operation | API/tool evidence |
|---|---|---|
| 18:40:47-18:41:14 | Capture full gateway, site and both connection baselines | Azure CLI `show`; CLI version preserved |
| 18:44:13-19:42:28 | Add `.22.2/.3` to the VPN gateway custom BGP lists | Terraform/AzureRM; underlying ARM API version was not emitted |
| 19:42:51-19:43:08 | Confirm gateway additions persisted and four SAs survived | Azure CLI targeted GET |
| 19:43:24-19:43:35 | Update complete parent VPN Site with public link peer `169.254.22.1` | Parent `PUT`, API `2025-09-01` |
| 19:43:46-19:44:15 | Update complete parent public VPN connection with embedded link mappings `.22.2/.3` | Parent `PUT`, API `2025-09-01` |
| 19:44:31-19:44:42 | Apply CPE APIPA loopback, XFRM routes and FRR neighbors | GCP SSH; StrongSwan not restarted |
| 19:45:04-19:46:22 | Run the single bounded acceptance window and targeted Azure reads | Azure CLI targeted GET plus concurrent packet capture |
| 19:46:48-19:47:09 | Restore CPE, public connection and public site | Connection/site parent `PUT`, API `2025-09-01` |
| 19:47:23-20:02:13 | Remove only the retry-added gateway APIPA addresses | Terraform/AzureRM |
| 20:02:38-20:02:59 | Confirm the original mappings and gateway lists were restored | Azure CLI targeted GET |
| 20:22:32-20:22:53 | Capture full post-rollback resource JSON | Explicit GET API `2025-09-01` |

## Provisioning and association observations

- During the active retry, the selected site peer, connection-link custom peer mappings and gateway custom BGP lists were all readable with the intended values.
- The connection and link provisioning states reported `Succeeded`; all four IKE/ESP SAs remained established.
- The post-rollback full GET snapshot reports `Succeeded` for the VPN gateway, VPN site, both VPN connections and embedded link connections. The virtual hub reports provisioning `Succeeded` and routing `Provisioned`.
- CPE-initiated SYNs reached `.22.2/.3`, but neither custom peer returned SYN-ACK or RST. Azure simultaneously initiated BGP from defaults `.12/.13`.

These facts narrow the issue but do not resolve whether the active parent/child resource association, mutation order, API representation, or another configuration dependency prevented the custom peers from answering. Trinity review is required before any new experiment.

No retry, convergence extension or configuration mutation was performed for this review. The only new provider operation was the read-only post-rollback GET snapshot.
