# Link Agent History

## Session: 2026-07-31

### Task
Retrieve two Megaport API secrets (`megaport-api-key`, `megaport-api-secret`) from the private Azure Key Vault `platform-secrets-1138` (swedencentral, RG: `platform`, publicNetworkAccess=Disabled) and persist them as Windows User environment variables on Jose's machine.

### Working Method

**Pattern: MI + IMDS + Temp Private Endpoint + Private DNS → private KV from lab VM**

1. **Verify context** — confirmed subscription `Litware-MngEnvMCAP642473-jomore` and vault URI `https://platform-secrets-1138.vault.azure.net/`.
2. **Jump host**: `nva1` (Ubuntu, swedencentral, RG `routemap-test-rg`), VNet `onprem1-vnet`, subnet `nva`, private IP `10.200.0.4`. nva1 was same-region as the vault.
3. **Managed Identity**: nva1 already had a System-Assigned MI (`principalId: 978fa239-…`). No new identity needed.
4. **RBAC** (vault uses `enableRbacAuthorization=true`): assigned role `Key Vault Secrets User` to nva1 MI at vault scope.
5. **Subnet prep**: disabled `privateEndpointNetworkPolicies` on the `nva` subnet.
6. **Private Endpoint**: created `pe-megaport-kv-temp` in `onprem1-vnet/nva` targeting vault `--group-id vault`. PE allocated private IP `10.200.0.5`.
7. **Private DNS**: zone `privatelink.vaultcore.azure.net` did not pre-exist in either RG — created it in `routemap-test-rg`, linked it to `onprem1-vnet`, attached a DNS zone group to the PE for auto A-record management.
8. **Fetch**: used `az vm run-command invoke` with a shell script that (a) fetches an IMDS token for `https://vault.azure.net`, (b) curls both secrets. DNS resolved correctly (`10.200.0.5`).

### Gotchas Hit

- **Secret name format**: The caller spec used underscore (`MEGAPORT_ACCESS_KEY`) but Key Vault does not allow underscores — actual secret names use hyphens: `megaport-api-key` and `megaport-api-secret`. First fetch returned empty; a list-secrets diagnostic run revealed the real names.
- **Script quoting**: Passing a multi-token shell script inline via PowerShell's `--scripts` string arg caused `Syntax error: end of file unexpected`. Solved by writing the script to a local file and passing `@filepath` to `--scripts`.
- **RBAC propagation**: Completed without hitting a 403 (propagated within ~5 minutes before fetch).
- **Parallelism**: PE creation and RBAC assignment were issued concurrently. DNS steps followed PE creation. Single run-command fetch was the final step.

### Outcome

Both secrets were successfully fetched and persisted as Windows User environment variables via `setx`. Values are masked below.

- `MEGAPORT_ACCESS_KEY` — set, starts `3ehn…`, length 26
- `MEGAPORT_SECRET_KEY` — set, starts `i8pi…`, length 52

### What Was Cleaned Up

| Resource | Action |
|---|---|
| `pe-megaport-kv-temp` (private endpoint) | Deleted |
| `privatelink.vaultcore.azure.net` DNS zone | Deleted (created by this session) |
| `link-nva1-vnet` DNS VNet link | Deleted (created by this session) |
| Key Vault Secrets User role assignment (nva1 MI) | Deleted |
| nva1 System-Assigned Managed Identity | **Left in place** (pre-existing) |

Temp script files `.squad/agents/link/fetch-kv.sh`, `fetch-kv2.sh`, `diag-kv.sh`, `list-secrets.sh` remain locally but contain no secret values.

---

📌 Team update (2026-07-31T11:01:11Z): **Phase 3 Gates A, B, C FULL PASS — Complete Testing Arc**. Gate A (firewall deploy, RI OFF): 6/6 summaries on both NVAs, 0 /24 leaks, BGP Established. Gate B (RI hub-eu1): 6/6 summaries intact, BGP transparent (session timestamps unchanged from Gate A). Gate C (RI hub-eu2, both hubs now RI-ON): 6/6 summaries survive, BGP stable across all three gates. Missing-summary bug NOT reproduced under sequential stable-state enablement. Root-cause analysis (Trinity): RI operates on data-plane forwarding table; summarize-out operates on BGP advertisement set — orthogonal planes. Gate D concurrent-churn variant designed (dormant) to test race between RI policy-install and VPN connection rekey. Evidence: show-output/23–52. Decisions merged: tank-ri-eu1-enable, tank-ri-eu2-enable, niobe-gate-a/b/c, link-megaport-kv-retrieval, trinity-gate-c-analysis. Next: Jose direction on Gate D concurrent-churn variant.
