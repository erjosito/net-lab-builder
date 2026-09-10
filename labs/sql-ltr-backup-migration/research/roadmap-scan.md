# Roadmap scan: Azure SQL LTR backup migration

Scan date: 2026-09-10. Sources: Microsoft Learn, official GitHub docs repos. Public sources only.

---

## Bottom line

**One established assumption is now verifiably resolved. No other finding changes the recommended drain process.**

The last load-bearing unverified item, MI `BACKUP TO URL` with `IDENTITY = 'MANAGED IDENTITY'`, is confirmed GA for Azure SQL Managed Instance PaaS. Official Microsoft Learn pages show both the credential syntax and a worked COPY_ONLY backup example under a dedicated "Managed identity" tab scoped to Azure SQL Managed Instance.

All other conclusions stand. LTR backups remain subscription-locked. The SQL Database export-over-private-link and export-with-managed-identity features are both in preview, both apply to SQL Database only (not MI), and neither removes the fundamental drain requirement. The MI database copy/move feature is GA but moves live databases, not LTR backup chains, and requires both instances to be in the same Azure region.

---

## Findings table

| # | Feature | Applies to | Status | Date confirmed | Source URL | Effect on our process |
|---|---|---|---|---|---|---|
| 1 | MI `BACKUP TO URL` with `IDENTITY = 'MANAGED IDENTITY'` | Azure SQL Managed Instance (PaaS) | GA | 2025-09-15 (page), 2026-07-16 (T-SQL diff page) | https://learn.microsoft.com/en-us/azure/azure-sql/managed-instance/restore-database-to-sql-server; https://learn.microsoft.com/en-us/azure/azure-sql/managed-instance/transact-sql-tsql-differences-sql-server | **CHANGES PROCESS**: Resolves the unverified assumption. Managed identity IS supported for MI BACKUP TO URL. No SAS token or shared key needed. Assign Storage Blob Data Contributor to the MI's managed identity, then create credential with `IDENTITY = 'MANAGED IDENTITY'`, then run BACKUP...WITH COPY_ONLY. |
| 2 | SQL Database import/export via private link | Azure SQL Database only (not MI) | Public preview | 2025-11-06 | https://learn.microsoft.com/en-us/azure/azure-sql/database/database-import-export-private-link | Does not change process. This allows the managed export service to connect inbound via a private endpoint instead of the public endpoint, addressing the public-network-access constraint. However: (a) storage authentication in the documented examples still uses storage access keys, so the `allowSharedKeyAccess=false` constraint is not addressed by this feature alone; (b) it is in preview, a planning risk for a compliance workload; (c) service-managed private endpoints must be manually approved, adding an interactive step. sqlpackage from in-VNet compute remains the lower-risk path. |
| 3 | SQL Database import/export with managed identity authentication | Azure SQL Database only (not MI) | Public preview | 2026-03-02 (page), 2026-08-27 (last updated) | https://learn.microsoft.com/en-us/azure/azure-sql/database/database-import-export-managed-identity | Does not change process alone. This removes the need for storage account keys and allows CLI/PowerShell export even when `allowSharedKeyAccess=false` on storage. BUT: it is the same inbound-connecting managed service, so `publicNetworkAccess=Disabled` on the SQL server is still a constraint unless combined with the private link feature (finding 2). Combining both is not documented as a tested path. Both features are in preview. |
| 4 | MI database copy/move across subscriptions (same tenant) | Azure SQL Managed Instance (PaaS) | GA | 2025-09-15 | https://learn.microsoft.com/en-us/azure/azure-sql/managed-instance/database-copy-move-how-to | Does not remove the LTR drain requirement. This feature (`az sql midb copy/move` with `--dest-sub-id`) moves LIVE databases across subscriptions, not LTR backups. The page explicitly states "Database copy and move operations don't copy or move PITR backups." LTR backups also stay behind. Additionally, the source and destination MI must be in the same Azure region. Useful context for the broader migration, but orthogonal to the LTR compliance archive problem. |
| 5 | LTR backup cross-subscription restore | Azure SQL Database, Azure SQL Managed Instance | Not available | 2026-09-10 | https://learn.microsoft.com/en-us/azure/azure-sql/database/long-term-retention-overview | No change. The LTR overview page still states restore is only available "under the same subscription as the original database." No new portability announced. |
| 6 | LTR backup immutability on Managed Instance | Azure SQL Managed Instance | Not available | 2026-09-10 | https://learn.microsoft.com/en-us/azure/azure-sql/database/long-term-retention-overview | No change. The page explicitly notes "In Azure SQL Managed Instance, it's not currently possible to configure backups as immutable." The same page suggests copy-only backups to your own storage as the workaround, which aligns with the current drain approach. |

---

## Detail: Finding 1 (highest value)

### What the docs say

The page "Restore a Database to SQL Server from Azure SQL Managed Instance" (`restore-database-to-sql-server`) includes a section "Take a backup on SQL Managed Instance" with two explicitly labeled tabs: "Managed identity" and "SAS token". The Managed identity tab shows:

```sql
CREATE CREDENTIAL [https://<mystorageaccountname>.blob.core.windows.net/<containername>]
WITH IDENTITY = 'MANAGED IDENTITY';
```

Followed immediately by:

```sql
BACKUP DATABASE [SampleDB]
TO URL = 'https://<mystorageaccountname>.blob.core.windows.net/<containername>/SampleDB.bak'
WITH COPY_ONLY;
```

The page applies to: Azure SQL Managed Instance (explicitly, page title and Applies-to badge).

The T-SQL differences page (`transact-sql-tsql-differences-sql-server`, last updated 2026-07-16) states under Backup:

> "To back up or restore a database to/from an Azure storage, you can authenticate using either managed identity or shared access signature (SAS)."

And under Credential:

> "Managed identity, Azure Key Vault and SHARED ACCESS SIGNATURE identities are supported."

### Reconciliation with the confusing "CREDENTIAL isn't supported" note

The same T-SQL differences page lists "`FILE_SNAPSHOT` and `CREDENTIAL` aren't supported" under BACKUP WITH options. This refers to the explicit `WITH CREDENTIAL = <credname>` syntax in the BACKUP statement (old-style, SQL Server 2008 era). The modern approach, used since SQL Server 2016, creates a server-scoped credential object whose name matches the URL prefix; SQL Server then looks up that credential implicitly when executing BACKUP TO URL. The worked example on the "Restore to SQL Server" page confirms this: there is no `WITH CREDENTIAL` in the BACKUP statement.

### What this means for the governance scenario

The managed identity path requires:
- The MI's system-assigned or user-assigned managed identity granted `Storage Blob Data Contributor` on the storage account
- A server-scoped credential created with `IDENTITY = 'MANAGED IDENTITY'`
- `BACKUP DATABASE ... TO URL ... WITH COPY_ONLY`

No SAS token. No storage account key. `allowSharedKeyAccess=false` is no longer a blocker for the MI path. The BACKUP TO URL writes outbound from inside the instance, so `publicNetworkAccess=Disabled` on the MI was already irrelevant. The only remaining network constraint is that the MI must have outbound reachability to the storage account's private endpoint (or public endpoint if storage allows it).

### Identity string capitalisation

The MI-specific page uses `'MANAGED IDENTITY'` (all caps). SQL Server on Azure VM and Arc pages use `'Managed Identity'` (mixed case). In practice, T-SQL string comparisons for credential identity are case-insensitive. Use `'Managed Identity'` as it is more widely documented and matches the MI link/backup pages as well as the VM/Arc pages.

---

## Detail: Finding 2 and 3 (SQL Database export path)

These two features are distinct. They address different constraints:

| Constraint | Private link import/export (finding 2) | Managed identity import/export (finding 3) |
|---|---|---|
| `publicNetworkAccess=Disabled` on SQL server | YES, addressed by service-managed private endpoint | NO, same inbound service, same constraint |
| `allowSharedKeyAccess=false` on storage | NOT addressed (documented examples use storage access keys) | YES, managed identity RBAC replaces key/SAS |
| SQL authentication disabled | Not specifically addressed | YES, `AuthenticationType=ManagedIdentity` removes SQL admin password |
| Preview status | Preview | Preview |

Neither feature alone satisfies all three governance constraints that the customer's environment enforces simultaneously. Combining them is not documented as a tested path. Until GA and until a combined path is documented, sqlpackage from in-VNet compute remains the recommended route for the SQL Database drain.

---

## Searched and found nothing

The following were explicitly searched and yielded no positive result for the question being asked. This is not a gap in the search; these items were checked and are definitively not available as of scan date.

| Search target | Sources checked | Finding |
|---|---|---|
| Azure Backup for Azure SQL DB/MI LTR (Azure Backup vault covering LTR backups) | learn.microsoft.com, Azure Updates query | Azure Backup does not manage Azure SQL LTR backups. Azure Business Continuity Center surfaces SQL LTR backups but does not add portability or cross-subscription move capability. |
| LTR backup soft-delete or subscription-deletion grace period | learn.microsoft.com LTR overview, automated backups pages | No soft-delete and no grace period announced. LTR backup purge on subscription deletion remains immediate and irrecoverable. |
| Cross-subscription LTR restore for SQL DB or MI | learn.microsoft.com LTR overview and configure pages | Explicitly and repeatedly states "under the same subscription." No announced change. |
| Cross-subscription PITR restore | learn.microsoft.com | Not available. PITR restore is also subscription-locked. |
| Azure Resource Mover support for LTR backups | learn.microsoft.com Resource Mover docs | LTR backups are not a movable resource type. Azure Resource Mover does not list SQL LTR backup objects. |
| LTR backup export to storage (without restore) | learn.microsoft.com | No export-without-restore capability exists or is announced. The only operation on an LTR backup remains "restore it to a live database." |
| MI `BACKUP TO URL` with any identity other than SAS or managed identity | learn.microsoft.com T-SQL differences page, MI credential docs | Access keys are explicitly not supported for MI backup/restore URL authentication ("Using Access keys for these scenarios isn't supported"). SAS and managed identity are the two supported options. |
| `az sql db export` working with both public network disabled AND shared key disabled (without the two new preview features) | learn.microsoft.com, lab evidence in README | No such path exists. The two preview features (findings 2 and 3) are the only announced directions, and neither alone covers all three governance constraints. |
| SQL DB database copy cross-subscription | learn.microsoft.com database-copy page | SQL Database copy does not support cross-subscription. Only MI supports cross-subscription copy (finding 4). |
| Subscription-level backup retention or "backup vault" that outlives subscription deletion | learn.microsoft.com, Azure Updates | No such capability. Azure Backup vaults are subscription-scoped resources and are deleted with the subscription. |

---

## Notes on source reliability and preview risk

All findings above are sourced from official Microsoft Learn pages. The scan date for each finding is 2026-09-10.

Findings 2 and 3 are explicitly labeled "preview" in the page title and in the Note callouts on those pages. Preview features carry Microsoft's standard preview disclaimer: not covered by SLA, subject to change or removal, not recommended for production use. For a compliance workload with a hard deadline (subscription deletion), a preview feature that could be withdrawn or behave unexpectedly during the drain window is a material planning risk. The established sqlpackage-from-in-VNet path (finding from README) does not carry this risk.

Finding 1 (MI managed identity BACKUP TO URL) does not carry a preview label on the relevant pages. It is presented as a standard capability alongside SAS credentials on the same page, with no preview callout.

Finding 4 (MI database copy/move cross-subscription) is GA and is mentioned here for completeness. It does not change the LTR drain requirement.
