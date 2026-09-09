# Draining Azure SQL LTR backups before a subscription is deleted

Scripts and cost model for preserving Azure SQL Database and Azure SQL Managed Instance
**long-term retention (LTR)** backups past the deletion of the subscription that owns them.

## The problem in one paragraph

LTR backups are effectively their own resource, keyed by subscription + region + the
original server/database GUID. They survive deletion of the database, the logical server,
and even the entire managed instance. They do **not** survive deletion of the
**subscription**. Microsoft exposes exactly one operation on an LTR backup, "restore it
into a live database", so there is no way to copy, download or move the underlying blob.
Preserving them therefore requires rehydrating each restore point and re-exporting it as a
portable artifact.

```
LTR backup --restore--> live database --export--> BACPAC / .bak --> blob storage (any subscription)
```

## Verification status

Be honest about what has and has not been proven, because the cost model is only as good
as its inputs.

| Claim | Status | How |
|---|---|---|
| LTR survives DB / server / instance deletion, dies with the subscription | **Verified** | Microsoft Learn |
| LTR restore is subscription-locked; PITR is not | **Verified** | Microsoft Learn |
| Export destination storage may live in another subscription | **Verified** | Auth is storage key / SAS, not ARM |
| Service-managed TDE blocks COPY_ONLY on MI | **Verified** | Microsoft Learn |
| `BACKUP TO URL` caps at 195 GB per stripe, 64 stripes | **Verified** | Microsoft Learn |
| `az` command and parameter surface | **Verified** | Live `az --help`, CLI 2.84.0 |
| SQL DB / MI GP Gen5 compute $/vCore/hr | **Verified** | Retail prices API: $0.152217 |
| Cost model arithmetic | **Verified** | Hand-checked against every printed field |
| Regression fitter recovers known parameters | **Verified** | Synthetic ground truth, R-squared 1.0 |
| Scripts are syntactically valid | **Verified** | PowerShell AST + ScriptDom for T-SQL |
| **Drain scripts run end to end against Azure** | **NOT verified** | Requires the lab |
| **Throughput constants** (min/GB for restore, export, backup) | **NOT verified** | Educated guesses; the lab exists to measure them |
| **Compression ratios** (4.0 BACPAC, 3.0 `.bak`) | **NOT verified** | Depends entirely on your data |

**The compression assumption is the one that matters.** Artifact storage dominates total
cost over a multi-year retention, and it is inversely proportional to the compression
ratio. For 60 backups x 50 GB over 7 years:

| Compression | Artifact GB | Grand total |
|---|---|---|
| 4.0x (default assumption) | 750 | $1,289 |
| 1.02x (incompressible) | 2,941 | $4,971 |

That is a 3.9x swing driven by a number nobody has measured on your data. Budget with the
worst ratio you observe, and price the Archive tier before committing: it cuts the storage
term by roughly 20x and it is the term that dominates.

The throughput constants are far less dangerous. They only affect one-time compute, which
is noise (about 2% of the total for SQL DB, and exactly zero for MI if you drain before
deleting the instance).

## Decision tree

**Before building anything, confirm the old subscription is really going away.**

| Situation | What to do |
|---|---|
| Subscription survives (resources deleted, subscription kept empty) | **Do nothing.** LTR backups persist untouched. You pay only LTR storage and restore on demand. No pipeline needed. |
| Subscription will be deleted | Drain the backups with the scripts here, **before** deletion. |

If the subscription is being deleted, the second question is about timing:

| Situation | Cost impact |
|---|---|
| Source SQL MI **still running** | Restore into it directly. Incremental compute cost is **zero**. |
| Source SQL MI **already deleted** | You must pay for a staging MI for the whole batch. Batch everything into one instance lifetime. |
| Azure SQL Database (any case) | The logical server is free; only the short-lived temp databases cost anything. |

**The single biggest cost lever is draining before you delete the managed instance.**

## Scripts

| Script | Purpose |
|---|---|
| `Get-LtrExportCostEstimate.ps1` | Parameterised incremental cost model. Run this first. |
| `Export-SqlDbLtrBackups.ps1` | Azure SQL Database: LTR -> temp DB -> BACPAC -> blob. |
| `Export-SqlMiLtrBackups.ps1` | Azure SQL MI: LTR -> staged DB -> COPY_ONLY `.bak` (or BACPAC) -> blob. |

All three support `-WhatIf`. Both export scripts write a **manifest CSV** recording which
original server/instance, database and restore point each artifact came from, which is the
provenance evidence auditors actually ask for.

The manifest also doubles as a measurement run. Alongside the provenance columns, each row
records `SourceGb`, `RestoreMinutes`, `ExportMinutes` and `ArtifactGb`. Feed it to
`labs/sql-ltr-backup-migration/deploy/Measure-LtrCalibration.ps1` to replace the
estimator's guessed throughput and compression defaults with numbers measured on your own
data. This matters most for compression: the default assumes 4x, and real data ranges from
barely compressible to better than 30x. Artifact storage dominates the multi-year cost, so
a wrong compression ratio is the single largest source of error in the estimate.

Size and artifact lookups are best-effort. They never fail an export that has already
succeeded, so a blank column means "not measured", not "zero".

### Quick start

```powershell
# 1. Model the cost first.
.\Get-LtrExportCostEstimate.ps1 -BackupCount 60 -AvgDatabaseGb 50

# 2. Dry-run the drain.
.\Export-SqlDbLtrBackups.ps1 -SourceSubscriptionId <guid> -Location eastus `
    -StagingResourceGroup rg-ltr-drain -StagingServer sql-ltr-staging `
    -StagingAdminUser ltradmin -StagingAdminPassword (Read-Host -AsSecureString) `
    -DestStorageUri 'https://archivesa.blob.core.windows.net/sql-ltr' `
    -DestStorageKey $key -WhatIf
```

## Cost shape

Example: **60 restore points, 50 GB average database, 7 year retention, East US PAYG.**

| | SQL DB (BACPAC) | SQL MI, instance alive | SQL MI, instance gone |
|---|---|---|---|
| Staging compute | $28.65 | **$0** | $28.20 |
| Staging storage (transient) | $0.78 | $0.35 | $0.35 |
| Bandwidth, same region | **$0** | **$0** | **$0** |
| Artifact storage (Cool, 7 yr) | $1,260 | $1,680 | $1,680 |
| **Total** | **~$1,289** | **~$1,680** | **~$1,708** |

Three conclusions that are easy to get backwards:

1. **Compute is noise.** Even 95 hours of staging database time costs under $30. Do not
   over-optimise the staging SKU; optimise for the drain finishing without failures.
2. **Bandwidth is usually zero.** See below.
3. **Long-term artifact storage dominates**, by roughly 50x. This is the number worth
   attacking. Moving artifacts to the **Archive** tier drops the same scenario from
   ~$1,289 to **~$92** for SQL DB and from ~$1,680 to **~$84** for MI:

   ```powershell
   .\Get-LtrExportCostEstimate.ps1 -BackupCount 60 -AvgDatabaseGb 50 -BlobGbMonthUsd 0.00099
   ```

   The cost is a multi-hour rehydration delay, which is almost always acceptable for a
   compliance archive that may never be read.

### Bandwidth costs

**Crossing a subscription boundary costs nothing. Crossing a region boundary does.**
Subscriptions are a billing container, not a network boundary.

| Path | Rate | Applies to this pipeline? |
|---|---|---|
| Ingress into blob storage | **$0.00/GB** | Always. Writing the artifact is free. |
| Same region, cross-subscription | **$0.00/GB** | The recommended layout. No charge. |
| Inter-region | $0.02/GB | Only if the destination account is in another region |
| Inter-availability-zone | $0.01/GB | Rarely relevant here |
| Internet egress | ~$0.087/GB after 100 GB/month free | Only if you pull artifacts out of Azure |

So keep the destination storage account **in the same region** as the source, in whichever
subscription you like, and bandwidth is genuinely $0. In the example above, going
cross-region would add only $15-20 anyway; it is a rounding error next to storage.

The LTR restore itself is an internal Azure operation and is never billed as bandwidth.

Model it explicitly with `-ArtifactDestination SameRegion|CrossRegion|Internet`.

### SQL compute costs

There is **no separate charge for the export operation itself**. The BACPAC export service
and MI's `BACKUP TO URL` both run against the database you are already paying for. What you
actually pay for is the *wall-clock lifetime of the staging database*:

- **SQL DB** — the logical server is free. Each temp database is billed per hour at the SKU
  you choose in `-Edition/-Family/-Capacity` (GP Gen5 = $0.15/vCore/hour), from restore
  until you drop it. The scripts drop it in a `finally` block for exactly this reason.
- **SQL MI** — there is no free container. If the source instance still exists, restoring
  into it adds **zero** compute cost because you are already paying for those vCores. If it
  is gone, a staging MI costs from $0.61/hour (GP Gen5, 4 vCore minimum), and those
  instance-hours span the *entire batch*, not one database.
- **Staging storage** — the staged database occupies GP data storage at $0.12/GB/month
  while it exists, prorated. Cents in practice, but not structurally zero. On MI this is
  charged even while the instance is stopped, so never leave staged copies behind.
- **PITR backup storage** — a restored database immediately starts generating its own
  automated backups. Negligible for databases that live hours, but another reason to drop
  them promptly.

Azure Hybrid Benefit applies to a staging MI and removes the SQL licence component
(roughly 55% of the vCore rate). Use `-ApplyAhb` in the estimator.

## Artifact choice: BACPAC vs native COPY_ONLY `.bak`

For **Azure SQL Database** there is no choice: native `.bak` is not available, BACPAC is
the only export format.

For **Azure SQL MI** both are possible and the trade-off is real:

| | BACPAC | COPY_ONLY `.bak` |
|---|---|---|
| Tooling on MI | No managed API. `az sql midb export` **does not exist**. Requires `sqlpackage.exe` with network line-of-sight to the instance. | Native T-SQL, writes straight to blob |
| Blocked by service-managed TDE | No | **Yes** (see below) |
| Fidelity | Schema + data only | Byte-exact, everything |
| Integrity verification | None | `RESTORE VERIFYONLY` + `CHECKSUM` |
| Can fail on unsupported objects | Yes | No |
| Speed | Slow | Fast, compressed |
| Restores to on-premises SQL Server | Yes | Generally no; MI's database version is higher |

`Export-SqlMiLtrBackups.ps1` defaults to **`NativeBak`**, mainly because of
`RESTORE VERIFYONLY`: it lets you prove an artifact is still readable years later without
restoring it. A BACPAC gives no such guarantee, and BACPAC export can fail outright on
objects DacFx does not support, which is more common on MI than on SQL DB.

Use `-ArtifactType Bacpac` if you need to restore to a non-MI target, or if the databases
are small and feature-simple.

## The TDE trap on Managed Instance

From Microsoft's copy-only backup documentation:

> In Azure SQL Managed Instance, copy-only backups can't be created for a database
> encrypted with service-managed Transparent Data Encryption (TDE). Service-managed TDE
> uses internal key for encryption of data, and that key can't be exported, so you
> couldn't restore the backup anywhere else.

TDE is on by default, so this blocks the native path unless handled. `-TdeMode` offers two
answers:

- **`DisableOnStagedCopy`** (default) — `ALTER DATABASE ... SET ENCRYPTION OFF` on the
  throwaway restored copy, back it up, then discard the copy. The original database is
  never touched. Produces a plaintext `.bak`, so protect it with immutable blob storage
  and service-side encryption.
- **`CustomerManagedKey`** — assumes the instance already uses CMK TDE. The `.bak` stays
  encrypted, but **you must preserve that Key Vault key for the full retention period, in
  a vault that outlives the deleted subscription.** Lose the key and every artifact becomes
  permanently unreadable.

The default is deliberate. Customer-managed keys look like the more rigorous option, but
they replace a storage problem with a ten-year key-custody problem, and the vault is
usually sitting in the very subscription being decommissioned.

## Gotchas worth knowing before you start

- **Enumerate with `--database-state All`.** During a decommission the source databases and
  servers are often already deleted; the default listing will not show their backups.
- **LTR restore is subscription-locked.** The staging server or instance must be in the
  same subscription as the backups. Only the *artifact destination* can be elsewhere.
- **Artifact destination can cross subscriptions.** `az sql db export` and MI's
  `BACKUP TO URL` authenticate to storage with a key or SAS, not with ARM, so the
  destination account may live in the new subscription. No blob-copy hop is needed.
- **BACPAC consistency.** A BACPAC is only transactionally consistent from a quiesced
  source. A freshly restored temp database receives no writes, so this path is safe. This
  is a genuine point in favour of the restore-then-export approach.
- **Always drop the staging database.** Both scripts do this in a `finally` block. An
  orphaned temp database keeps billing, and on MI it keeps consuming instance storage.
- **MI stop/start.** General Purpose instances can be stopped, which halts compute and
  licence billing while storage continues. Useful if the drain is spread over days.
- **Azure Hybrid Benefit** applies to a staging MI (`-ApplyAhb` in the estimator) and cuts
  the compute component substantially.
- **Run a recovery drill.** Restore one artifact end to end before deleting anything.
  Microsoft recommends periodic drills for exactly this reason, and an untested compliance
  archive is not a compliance archive.

## Order of operations

1. Confirm the subscription really is being deleted.
2. Run the cost estimate; decide Cool vs Archive tier.
3. Create the destination storage account in the **new** subscription, with immutability
   policy and versioning enabled.
4. Drain SQL MI **first, while the instance is still running** (this is the free window).
5. Drain SQL DB into a staging logical server.
6. Verify: check the manifests, and restore at least one artifact of each type.
7. Only then delete the old subscription.
