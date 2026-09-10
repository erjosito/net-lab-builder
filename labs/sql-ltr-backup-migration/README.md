# Lab: SQL LTR backup migration

Validates the tooling in `src/powershell/sql-ltr-export/` and the assumptions it rests on,
before it is pointed at real production data ahead of a subscription deletion.

**Short answer to "can this be tested in one subscription?": yes, about 90% of it.**
Only two assumptions genuinely need a second subscription, one of them is cheap to add,
and one of them must never be tested at all.

## Scenarios

| # | Scenario | Subscriptions needed |
|---|---|---|
| 1 | LTR backups survive deletion of database, server and managed instance | 1 |
| 2 | Deleted-source backups are still enumerable and restorable | 1 |
| 3 | SQL DB drain: LTR -> temp DB -> BACPAC -> blob, round-tripped back | 1 |
| 4 | MI drain: TDE blocker, workaround, COPY_ONLY, `RESTORE VERIFYONLY` | 1 |
| 5 | Striping path for databases above 195 GB | 1 (see trick below) |
| 6 | Artifact destination in a different subscription | **2** (storage only) |
| 7 | LTR restore is subscription-locked (negative test) | **2**, optional |
| 8 | Subscription deletion purges LTR | **Never test.** Irreversible. |

## What genuinely requires cross-subscription

Only **scenario 6**, and it is the cheap one: it needs a *storage account* in a second
subscription and nothing else. No SQL resources, no second instance. The claim being tested
is that `az sql db export` and MI's `BACKUP TO URL` authenticate to storage with a key or
SAS rather than through ARM, so the subscription boundary is irrelevant to them.

If a second subscription is genuinely unavailable, this can be approximated convincingly in
one subscription by removing every ARM path to the storage account and leaving only the SAS:

- grant the SQL server / MI managed identity **no** RBAC role on the storage account
- run the drain as a principal with **no** ARM permission on the storage account
- set the storage firewall to default-deny, allowing only trusted Azure services

If the export still succeeds under those conditions, ARM authorisation demonstrably played
no part, which is the actual mechanism in question. That is a strong proxy, not a proof.
Prefer the real second subscription; a storage account costs cents.

**Scenario 7** is a negative test of documented behaviour ("The database can be restored to
any existing server or managed instance under the same subscription as the original
database"). Worth running once if a second subscription is handy, purely to confirm the
failure is clean and early rather than a partial restore. Low value otherwise.

**Scenario 8 must not be tested.** Subscription deletion is irreversible and would destroy
the very backups under study. Take it from the documentation.

## The trick for scenario 5

Do not provision a 200 GB database to test striping. Force the code path on a small
database instead by shrinking the stripe threshold:

```powershell
.\Export-SqlMiLtrBackups.ps1 ... -GbPerStripe 1
```

A 3 GB staged database then produces a 3-way striped backup, exercising the multi-URL
`BACKUP` and `RESTORE VERIFYONLY` syntax, the stripe-count arithmetic and the manifest
`Stripes` field. Only the 195 GB boundary value itself goes untested, and that value comes
from a documented platform limit rather than from our logic.

## The scheduling constraint that dominates this lab

**LTR backups cannot be created on demand.** From the LTR documentation:

> The timing of individual LTR backups is controlled by Microsoft. You can't manually create
> an LTR backup or control the timing of the backup creation. After you configure an LTR
> policy, it might take up to seven days before the first LTR backup shows up on the list of
> available backups.

There is one mitigation, also documented: when an LTR policy is enabled **for the first
time** on a database, the most recent existing PITR full backup is copied into long-term
storage. So seeding early and waiting is the only reliable approach.

This splits the lab into two phases separated by days, which is unusual for this repo's
labs and needs to be planned for rather than discovered:

| Phase | Activity | Elapsed |
|---|---|---|
| Seed | Create resources, load data, enable LTR policies, then **stop and wait** | Day 0 |
| Poll | `az sql db ltr-backup list` until backups appear | Day 0 to Day 7 |
| Execute | Delete sources, run both drain scripts, verify | Day N |
| Teardown | Delete everything, including LTR policies | Day N |

Do not let the managed instance idle at full price during the wait. General Purpose
instances support stop/start, which halts compute and licence billing while storage
continues, so stop it between the seed and execute phases.

## Cost of the lab

**Database half only** (scenarios 1, 2, 3, 5):

| Item | Estimate |
|---|---|
| SQL DB serverless, 60-minute auto-pause, ~3 active hours | ~$1 |
| Data storage for ~36 GB across five databases, one week | ~$1 |
| Storage, LTR and artifacts | <$1 |
| **Total** | **~$5 to $10** |

**Adding the Managed Instance** (scenario 4):

| Item | Estimate |
|---|---|
| MI, GP Gen5 4 vCore, running continuously for a 7-day wait | ~$102 |
| MI storage | ~$1 |
| **Total** | **~$110, plus 2 to 4 hours of provisioning time** |

The MI figure is not a typo and it cannot be reduced by stopping the instance between
phases. A stopped instance takes no automated backups, and a skipped LTR backup is never
backfilled, so the instance has to stay up for the whole wait. Earlier drafts of this table
assumed otherwise and understated the MI cost by roughly a factor of sixteen.

Keep test databases small, single-digit GB. The lab validates mechanics, not throughput.
Throughput numbers for the real estimate should be calibrated separately by measuring the
first production database and feeding the result back into `Get-LtrExportCostEstimate.ps1`.

## Deliberately out of scope

- Subscription deletion behaviour (scenario 8).
- Real-world restore durations. Lab databases are too small to extrapolate from.
- Customer-managed-key TDE. The tooling defaults to `DisableOnStagedCopy` precisely to
  avoid introducing a Key Vault key that must outlive the old subscription; testing the CMK
  path is only worthwhile if you have decided to accept that key-custody burden.

See `validation.md` for the assertion-level matrix.

## Cost model

`cost-model/` holds an Excel model of the transfer and long-term storage cost of the
artifacts this lab produces, plus a variant for reaching the storage account over a private
endpoint. See [`cost-model/README.md`](cost-model/README.md). It is the storage half of the
picture; `src/powershell/sql-ltr-export/Get-LtrExportCostEstimate.ps1` is the compute half.

## How this lab deviates from the repo convention

`labs/README.md` describes the convention for this folder, and it assumes an **Azure
Networking** lab following an eight-phase lifecycle with a specific artifact set. This lab
deliberately departs from it in four ways. They are listed here so the gaps read as choices
rather than omissions.

| Convention | This lab | Why |
|---|---|---|
| Azure Networking subject matter | Azure SQL Database and Managed Instance backup retention | The question asked was a database one. The rest of the repo's tooling and structure still applied, so it was reused rather than duplicated elsewhere. |
| `design.md` with mechanism trade-offs and an F-table / M-table resiliency analysis | Absent | Those sections model failure and recovery of a running network topology. This lab has no topology and no traffic; its subject is the lifecycle of a backup artifact. The equivalent reasoning lives in the decision tree and the BACPAC vs native `.bak` comparison in `src/powershell/sql-ltr-export/README.md`. |
| `## Designs studied` section with recommended and not-recommended designs | Covered by the scenario table above and by `validation.md` | The unit of study here is an assertion to be proved or disproved, not a design to be recommended. Scenario 8 is an explicit "never do this". |
| `lessons-learned.md`, `show-output/`, `screenshots/` | Not yet created | These are execution artifacts and **this lab has never been run**. Creating them now would mean inventing evidence. They should be written during phase 3. |
| `diagrams/` | Absent | There is no topology to draw. A diagram would add nothing over the phase table. |

One convention this lab does follow exactly: **sanitization**. No subscription IDs, tenant
IDs, server names or admin passwords appear in any committed file, and the deploy scripts
take the admin password as a `SecureString` parameter rather than embedding one.

## Lab environment

Provisioned by `deploy/Deploy-LtrLab.ps1`. Single subscription, one free logical server,
five databases, one storage account. The managed instance is opt-in because it alone
costs more than everything else combined.

| Database | Size | Data shape | Why it exists |
|---|---|---|---|
| `calib-1gb` | 1 GB | mixed | Anchors the fixed-overhead term |
| `calib-5gb` | 5 GB | mixed | Middle point; also the held-out prediction test |
| `calib-20gb` | 20 GB | mixed | Anchors the per-GB slope |
| `probe-compressible` | 5 GB | repeated bytes | Upper bound on compression ratio |
| `probe-random` | 5 GB | `CRYPT_GEN_RANDOM` | Lower bound: incompressible worst case |

**Why three sizes.** Drain time is modelled as `minutes = Fixed + (PerGb * SizeGb)`. One
size cannot separate those terms: any single measurement is explained equally well by a
large fixed cost or a steep slope. Three sizes spanning an order of magnitude let
`Measure-LtrCalibration.ps1` recover both by least squares, and the R-squared tells you
whether the linear assumption holds at all.

**Why two data shapes.** The estimator assumes BACPAC compresses ~4x. That number is pure
guesswork and it multiplies the dominant cost term. A dry run of the fitter against
synthetic ground truth reported a compression range of **1.02x to 33x** between the two
probes. If your data resembles the random probe, artifact storage costs roughly four times
the default estimate. Bracketing this is worth two small databases.

The databases are serverless with a 60-minute auto-pause, so the multi-day wait for LTR
backups costs storage only.

## Pre-flight results

Phase 0 has been run. Nothing has been deployed to Azure.

Quotas below were read from the lab subscription in `swedencentral`.

| Check | Result |
|---|---|
| `Test-LabSql.ps1` | PASS, `Seed-LabData.sql` parses as 4 batches |
| `Test-DrainHelpers.ps1` | PASS, 9 of 9 |
| Regional SQL server quota | 0 of 250 |
| Regional vCore quota, SQL DB | 0 of 500 |
| MI subnet quota | 0 of 8 |
| MI vCore quota | 0 of 960 |
| MI free offer instances | 0 of 1, available |
| MI free vCore hours currently granted | 0 |

Two prerequisites are not satisfied by a fresh clone:

1. **The `SqlServer` PowerShell module.** Phase 1 seeds data through `Invoke-Sqlcmd`.
   Install it with `Install-Module SqlServer -Scope CurrentUser`.
2. **An admin password**, supplied interactively as a `SecureString`. It is never written
   to the repo.

### Finding: the toolkit assumed SQL authentication, and that can be denied outright

The first live deployment attempt **failed**, and the failure is more useful than a success
would have been.

Creating the logical server was rejected by Azure Policy:

```
(RequestDisallowedByPolicy) Resource 'ltrlab...-sql' was disallowed by policy.
policyDefinitionName: AzureSQL_WithoutAzureADOnlyAuthentication_Deny
policyDefinitionDisplayName: SFI-ID4.2.2 SQL DB - Safe Secrets Standard
```

The governing management group denies any `Microsoft.Sql/servers` whose
`properties.administrators.azureADOnlyAuthentication` is not `True`. In other words
**SQL authentication is forbidden**, and every script here was written around an admin
username and password.

A companion policy, `AzureSQLMI_WithoutAzureADOnlyAuthentication_Deny`, applies the same
rule to Managed Instances, so this is not something the MI half escapes.

The policy does expose an escape hatch, a `SecurityControl=Ignore` tag on the resource or
resource group. **Do not use it.** It suppresses a tenant security control to make a lab
convenient, and the compliant path exists.

The compliant path, which is what this lab now uses:

| Concern | SQL auth approach | Entra-only approach |
|---|---|---|
| Server admin | `-u/-p` | `--enable-ad-only-auth` plus an external admin principal |
| Seeding | `Invoke-Sqlcmd -Credential` | `Invoke-Sqlcmd -AccessToken` |
| BACPAC export | `--auth-type SQL` | `--auth-type ManagedIdentity` |
| Storage auth | account key | `--storage-key-type ManagedIdentity` plus RBAC |

Export under Entra-only authentication requires a **user-assigned managed identity attached
at the logical server level**, granted `Storage Blob Data Contributor` on the artifact
storage account and made a database user in each database being exported. A
system-assigned identity, a database-scoped identity, or a service principal will not do,
and the feature is still in preview.

**Carry this into production planning.** If the subscription holding the LTR backups sits
under similar governance, a drain runbook built on SQL authentication will fail at the
first step, and the fallback of "just enable SQL auth temporarily" is exactly what the
policy exists to prevent.

### Run the SQL Database half first

The lab is worth splitting. Scenarios 1, 2, 3 and 5 need only Azure SQL Database, whose
databases are serverless with a 60-minute auto-pause, so the multi-day wait costs storage
only, on the order of $5 to $10.

Scenario 4 needs a Managed Instance, and it is a different proposition entirely:

- The minimum is 4 General Purpose vCores, roughly **$102 for a seven-day wait**, plus two
  to four hours simply to provision.
- **The instance cannot be stopped to reduce that.** A stopped instance takes no automated
  backups, and a skipped LTR backup is never backfilled, so stopping it during the wait
  destroys the very thing the wait exists to produce.
- **The free offer does not rescue this, and is actively dangerous here.** A free instance
  is available (720 vCore hours per month for 12 months, one per subscription), but it
  defaults to a 9-to-5 weekday schedule specifically to conserve those credits. That
  schedule is exactly the stopped-instance trap above: the instance would be off for
  roughly two thirds of every week and the LTR backup would likely never be produced. Run
  it always-on and a seven-day wait consumes 672 of the 720 monthly hours, leaving almost
  no margin before the instance auto-stops and silently breaks the run. Use a paid instance
  and treat the free offer as unsuitable for this particular lab.

Since the two drain scripts share most of their logic, running the Database half first
falsifies the shared assumptions, above all the compression ratio, for about 8 percent of
the cost of doing both.

## Running the lab

| Phase | Script | Duration |
|---|---|---|
| 0. Pre-flight | `Test-LabSql.ps1`, `Test-DrainHelpers.ps1` | seconds |
| 1. Seed | `Deploy-LtrLab.ps1` | ~1 hour (data load) |
| 2. Wait | `Watch-LtrLabBackups.ps1` | hours to 7 days |
| 3. Execute | delete sources, then the drain scripts in `src/powershell/sql-ltr-export/` | ~2 hours |
| 4. Calibrate | `Measure-LtrCalibration.ps1` | minutes |
| 5. Teardown | `Remove-LtrLab.ps1` | minutes |

```powershell
cd labs\sql-ltr-backup-migration\deploy

# Phase 0: parse the T-SQL before spending an hour finding a typo the hard way
.\Test-LabSql.ps1
# ...and prove the instrumentation helpers parse az output correctly. They fail soft
# to blank, so a parsing bug would silently leave phase 4 with nothing to fit.
.\Test-DrainHelpers.ps1

# Phase 1
.\Deploy-LtrLab.ps1 -ResourceGroup rg-ltr-lab -Location eastus `
    -AdminUser ltrlab -AdminPassword (Read-Host -AsSecureString) -WhatIf

# Phase 2 (poll; do not proceed until backups appear)
.\Watch-LtrLabBackups.ps1 -Location eastus -Server <server>

# Phase 3: prove survival, then drain
az sql db delete -g rg-ltr-lab -s <server> -n <db> --yes
.\Watch-LtrLabBackups.ps1 -Location eastus -Server <server> -Once   # must still list

# Phase 4: the drain manifest IS the measurement run
.\Measure-LtrCalibration.ps1 -TimingCsv ..\..\..\ltr-export-manifest-*.csv

# Phase 5 (deletes the LTR backups too; the resource group alone is not enough)
.\Remove-LtrLab.ps1 -ResourceGroup rg-ltr-lab -Location eastus -Server <server>
```

**The drain scripts instrument themselves.** Each manifest row carries `SourceGb`,
`RestoreMinutes`, `ExportMinutes` and `ArtifactGb` alongside the provenance fields, so
phase 4 reads the manifest directly. There is no separate timing file to assemble by hand,
and the model is fitted against the *measured* size of each restored copy rather than the
size the seed script was asked for. Those two numbers routinely differ, and the difference
lands in the per-GB slope if you ignore it.

**Teardown is not just a resource-group delete.** LTR backups deliberately outlive their
source resources, so `Remove-LtrLab.ps1` clears the policies and deletes the backups
explicitly. Skipping it leaves them billing for the full 12-week retention.

