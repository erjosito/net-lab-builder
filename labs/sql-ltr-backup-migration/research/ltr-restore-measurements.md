# LTR restore measurements

**Date:** 2026-09-11
**Operator:** Tank
**Subscription:** `a8fbd8e1-fb5a-4411-804a-4ac80929c93c`
**Resource group:** `rg-ltr-lab`
**Region:** `swedencentral`
**Server:** `ltrlab552754-sql`
**Harness:** `labs/sql-ltr-backup-migration/deploy/Measure-LtrRestore.ps1`
**Verifier:** `labs/sql-ltr-backup-migration/deploy/Verify-LtrRestoreContents.ps1`
**Raw output:** `labs/sql-ltr-backup-migration/research/ltr-restore-raw-20260911.json`

---

## Headline

**The LTR restore mechanism works. The per GB restore rate is still NOT measured, and
`RestoreMinPerGb` remains `null`.**

Three LTR backups were restored into three new databases. All three succeeded and
reached `Online` with no errors. That is a genuine unblock: `az sql db ltr-backup
restore` has now been exercised end to end in this lab for the first time.

But **all three restored databases are empty.** Data plane verification from
`ltrlab-vm` found zero tables in each one. `dbo.LabPayload` does not exist in any of
the three, against source row counts of 131072, 655360 and 2621440 which all matched
their seed values exactly.

The three restores therefore all moved the same near zero payload. The observed
durations contain **no size information**, and no slope can be derived from them.

A provisional fit was computed before this was discovered:

```
minutes = 3.860445 + 0.037921 * sizeGb      R squared = 0.468043
```

**That fit is discarded.** It is an artifact of the defect described below, not a
property of LTR restore. It has been removed from `calibrated-parameters.json` and is
reproduced here only so that nobody re derives it and mistakes it for a result.

---

## Root cause

The three LTR backups predate the payload.

| Event | UTC |
|---|---|
| Server `ltrlab552754-sql` created | 2026-09-10T07:41:44Z |
| Seeding of the five lab databases begins | shortly after creation |
| **LTR backup content timestamp, `calib-5gb`** | **2026-09-10T08:06:45Z** |
| **LTR backup content timestamp, `calib-20gb`** | **2026-09-10T08:06:46Z** |
| **LTR backup content timestamp, `calib-1gb`** | **2026-09-10T08:07:35Z** |
| LTR policy first attempted, failed on auto pause | 2026-09-10T08:58:38Z |
| LTR policy successfully set on all five databases | 2026-09-10T09:03:35Z |

Two things follow from this table.

First, the `backupTime` values sit roughly **25 minutes after server creation and
almost an hour before the LTR policy was even set.** They are not backups taken in
response to the policy. They are copies of the **first automatic PITR full backup**,
which Azure takes shortly after a database is created. When the LTR policy was
eventually applied, the service copied that pre existing full backup into long term
retention.

Second, that first full backup landed while seeding was still in flight. From
`show-output/02-seed-results.txt` the seeds ran sequentially and took 5.67, 5.54, 5.46,
1.23 and 23.27 minutes. `calib-20gb` alone took 23.27 minutes, so a backup stamped
08:06:46 caught it a few minutes into a seed that did not finish until roughly 08:27.

The net effect is that the captured content is the database as it existed before
`dbo.LabPayload` was created. The restores are faithful. The backups are simply empty.

This also retro explains the shape of the discarded fit. The 5 GiB restore took
269.965 s and the 20 GiB restore took 271.993 s, a difference of **2.028 seconds**
across a nominal 4x size change. At the time that looked like "fixed cost dominates at
small sizes". It was actually "both restores moved the same nothing".

---

## Verification that settled it

Run from `ltrlab-vm` via `az vm run-command invoke`, because the server has
`publicNetworkAccess` disabled and this is a data plane check. Entra only auth using
the `ltrlab552754-umi` user assigned identity, which is the server's Entra admin
(`azureAdOnlyAuthentication: true`). No SQL authentication. No `SecurityControl=Ignore`.

| Database | Tables | Row count | Expected rows | ROWS file GiB | Verdict |
|---|---|---|---|---|---|
| `calib-1gb-ltrrestore-20260911`  | (none) | n/a | 131072 | 0.0313 | **EMPTY** |
| `calib-5gb-ltrrestore-20260911`  | (none) | n/a | 655360 | 0.0313 | **EMPTY** |
| `calib-20gb-ltrrestore-20260911` | (none) | n/a | 2621440 | 0.0313 | **EMPTY** |
| `ltrlab552754-calib-1gb`  | `dbo.LabPayload` | 131072  | 131072  | 1.0781  | FULL_MATCH |
| `ltrlab552754-calib-5gb`  | `dbo.LabPayload` | 655360  | 655360  | 5.0781  | FULL_MATCH |
| `ltrlab552754-calib-20gb` | `dbo.LabPayload` | 2621440 | 2621440 | 20.2031 | FULL_MATCH |

The sources are intact and were never touched. Only the restore targets are empty.

A control plane signal pointed the same way before the VM was started: Azure Monitor
`allocated_data_storage` for all three restored databases sat at an identical
0.0156 GiB across seven consecutive minutes. Three databases of nominally 1, 5 and 20
GiB reporting byte identical allocation is not metric lag, and that is what prompted
the data plane check.

---

## What this run did legitimately measure

### 1. The LTR restore mechanism works

`az sql db ltr-backup restore` succeeded three times out of three, with
`--dest-database`, `--dest-server`, `--dest-resource-group`, `--backup-id` and
`--service-objective`. Backup resource IDs from `az sql db ltr-backup list` were used
**verbatim**; they were never hand assembled, because the `;` separators and the `Hot`
tier suffix are significant. No restore errored.

### 2. An empty database restore floor

This is the one timing constant the run legitimately produced. It is the wall clock
cost of an LTR restore that carries essentially no data, that is, provisioning and
control plane orchestration only.

| Destination database | Submit (UTC) | First `Online` (UTC) | Seconds | Minutes |
|---|---|---|---|---|
| `calib-1gb-ltrrestore-20260911`  | 2026-09-11T07:26:42.0198617Z | 2026-09-11T07:30:14.9188044Z | 212.899 | 3.5483 |
| `calib-5gb-ltrrestore-20260911`  | 2026-09-11T07:30:18.5840740Z | 2026-09-11T07:34:48.5485962Z | 269.965 | 4.4994 |
| `calib-20gb-ltrrestore-20260911` | 2026-09-11T07:34:51.8488252Z | 2026-09-11T07:39:23.8413287Z | 271.993 | 4.5332 |

**Empty database restore floor: about 3.9 minutes, observed range 3.55 to 4.53
minutes.** Recorded as `RestoreEmptyDbFloorMin`.

This is a **lower bound** for any real LTR restore. It must never be used as
`RestoreFixedMin` in a size model. The intercept of a real size model can only be
established once at least one non empty LTR backup has been restored, and the spread
across these three empty restores is itself about 1 minute, which is wider than any
structure the discarded fit claimed to find.

### 3. Source sizes, on a basis confirmed two independent ways

Measured immediately before each restore was submitted.

| Source database | `allocated_data_storage` GiB | `sys.database_files` ROWS GiB | Total file GiB | Data space used GiB | Row count |
|---|---|---|---|---|---|
| `ltrlab552754-calib-1gb`  | 1.0781  | 1.0781  | 2.2734  | 1.0287  | 131072  |
| `ltrlab552754-calib-5gb`  | 5.0781  | 5.0781  | 10.2109 | 5.0563  | 655360  |
| `ltrlab552754-calib-20gb` | 20.2031 | 20.2031 | 26.7734 | 20.1595 | 2621440 |

Byte exact, for hand checking:

| Source database | `allocated_data_storage` bytes | `storage` bytes |
|---|---|---|
| `ltrlab552754-calib-1gb`  | 1157627904  | 1104609280  |
| `ltrlab552754-calib-5gb`  | 5452595200  | 5429198848  |
| `ltrlab552754-calib-20gb` | 21692940288 | 21646147584 |

**The size basis question is settled even though the fit is not.** The Azure Monitor
`allocated_data_storage` metric exactly reproduces both the published `SizesTestedGb`
from the export fit (whose `SizeBasis` was `allocated_8kb_pages`) and the ROWS file
GiB from `sys.database_files`. All three agree to four decimal places on all three
databases.

This matters because the Managed Instance half of the lab was previously bitten here:
the decrypt rate differed by roughly 2x depending on whether it was fitted on the ROWS
basis or the total footprint basis. Note that the total file GiB column above is
substantially larger than ROWS (26.77 versus 20.20 on the 20 GiB database), so the
choice is not cosmetic. Both are recorded so the basis can be re derived later.

**Recommendation for the eventual real measurement: fit on
`allocated_data_storage` / ROWS GiB.** It is the basis `ExportMinPerGb` already uses,
and restore and export slopes must share a basis to be composable into an end to end
drain estimate.

---

## Method, for the record

The method was sound. It was the input data that was defective.

- Backups enumerated with
  `az sql db ltr-backup list --location swedencentral --server ltrlab552754-sql --resource-group rg-ltr-lab -o json`,
  returned `id` values used verbatim.
- Restores run strictly **sequentially**. Parallel restores contend on the same storage
  and control plane path and would corrupt any fit. Same discipline that protected the
  earlier Managed Instance measurements.
- Submit timestamp captured **immediately before** each `az` call was issued.
- Restores issued with `--no-wait`. The blocking call's wall time was never trusted.
  Destination state was polled independently with `az sql db show`.
- Completion timestamp captured immediately after the destination **first reported
  `Online`**.
- All timing calls are control plane, so the disabled `publicNetworkAccess` was not a
  factor and no VM hop was needed for the timings. The VM was only needed afterwards
  for the data plane content verification.

### Precision bound

**Poll interval: 15 seconds.** State was sampled, not streamed, so **every duration
above is accurate to plus or minus 15 seconds.** At the small end 15 s is about 7
percent of the 212.9 s observation. This bound is unchanged by the invalidation and
applies to the empty database floor figures.

### Compute model, held constant on purpose

All three restore targets used an **identical** service objective, `GP_Gen5_4`
(provisioned, General Purpose, Gen5, 4 vCore).

This is a deliberate deviation from the sources, which are serverless `GP_S_Gen5_4`.
Serverless auto pause and auto resume would inject non restore latency, and two probe
databases in this lab were already observed `Paused`. A fit across mixed compute models
is not a fit.

Consequence: the floor figures describe restore into **provisioned** compute. Restore
into serverless was not measured and may be slower on first access.

Related and worth keeping in view: `show-output/03-ltr-policy-findings.txt` records that
LTR policy **cannot be enabled at all** on a serverless database with auto pause
enabled (`LtrConfigPolicyUnsupportedIfAutoPauseEnabled`). The lab databases all run
with `--auto-pause-delay -1` for that reason.

---

## Errors encountered

### Harness naming bug, before any restore was submitted

```
Exception: C:\Users\jomore\Repos\net-lab-builder\labs\sql-ltr-backup-migration\deploy\Measure-LtrRestore.ps1:84
Line |
  84 |  …  $backup) { throw "No LTR backup found for source database $sourceDb" …
     |                ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
     | No LTR backup found for source database ltrlab552754-sql-calib-1gb
```

Cause: the harness composed source database names from the server name
(`ltrlab552754-sql`) instead of the lab prefix (`ltrlab552754`). The convention is
`<prefix>-sql` for the server and `<prefix>-calib-<size>` for databases, so the server
name is not a usable stem. Fixed with an explicit `-Prefix` parameter.

This failed on a guard clause, so **no restore was issued and no Azure resource was
created or modified.** No bearing on the results.

### No restore failed

All three `az sql db ltr-backup restore` calls succeeded and all three destinations
reached `Online`. The invalidation is about backup **content**, not about restore
failure. These are two independent variables and should not be collapsed: the restore
path is proven, the rate is unmeasured.

---

## Forward path

**The three existing LTR backups can never yield a valid restore rate.** Their content
predates seeding and LTR backups are immutable copies. No amount of re restoring them
will produce a size signal.

A valid measurement needs an LTR backup taken **after** the payload was seeded. The
sources were seeded on 2026-09-10 and are still full at 131072 / 655360 / 2621440 rows,
so any future LTR backup should capture real data.

**Timing of that backup is ASSUMED, not measured.** It would be natural to predict the
next weekly cycle under the existing `P12W` policy, but this lab has already recorded
that LTR backup timing here does **not** follow the documentation:
`show-output/03-ltr-policy-findings.txt` shows that enabling the policy did not produce
an immediate copy at either 2 minutes or 25 minutes, and the Managed Instance half
recorded `LtrImmediateBackupCount: 0` as well. The three backups that eventually did
appear had content timestamps that nobody predicted.

So the honest statement is: **a post seed backup is required (proven), and the existing
three can never provide one (proven), but when one arrives is unknown.** Do not schedule
the next round on a predicted weekly boundary. Poll with
`Watch-LtrLabBackups.ps1` and trigger on a `backupTime` later than the seed completion
of roughly 2026-09-10T08:27Z, rather than on a calendar assumption.

When a newer backup appears:

1. Run `Verify-LtrRestoreContents.ps1` logic **first**, or check
   `allocated_data_storage` on the restored target, to confirm the payload actually
   landed.
2. Only then fit a slope.
3. Fit on the `allocated_data_storage` / ROWS GiB basis, to stay composable with
   `ExportMinPerGb`.

**New standing gate, earned the hard way:** any future restore timing run must verify
restored row counts against the source before a slope is fitted. This run demonstrates
that a restore can succeed, report `Online`, produce three clean sequential timings and
yield a plausible looking linear fit while carrying no data whatsoever. Timing alone
cannot detect that. Only a row count can.

Worth considering separately: whether a larger size point, in the hundreds of GiB, is
added when the lab is next rebuilt. At 1 to 20 GiB even a valid transfer term may be
small relative to the roughly 3.9 minute orchestration floor.

---

## Resources, none deleted

Per the standing instruction, **nothing was deleted.** Three new databases exist on
`ltrlab552754-sql` and are left running:

- `calib-1gb-ltrrestore-20260911`  (`GP_Gen5_4`, Online, empty)
- `calib-5gb-ltrrestore-20260911`  (`GP_Gen5_4`, Online, empty)
- `calib-20gb-ltrrestore-20260911` (`GP_Gen5_4`, Online, empty)

These are **provisioned, not serverless**, so unlike the calibration databases they will
not auto pause and will accrue compute cost continuously until a decision is made. They
hold no data and have no further measurement value, so they are the obvious cleanup
candidates, but they have been left in place pending that decision.

`ltrlab-vm` was **started** for the data plane verification. It was found
`deallocated`, and it was returned to `deallocated` afterwards so it would not accrue
cost in a state it was not previously in. Deallocation is not deletion and is reversed
with `az vm start -g rg-ltr-lab -n ltrlab-vm`.

---

## Still not measured

- **`RestoreMinPerGb` for Azure SQL Database.** The objective of this round. Blocked on
  a post seed LTR backup existing.
- **`RestoreFixedMin` for a real size model.** The empty database floor is a lower
  bound, not an intercept.
- **Managed Instance LTR restore.** Unchanged, still `LtrRestoreMeasured: false` in
  `mi-calibrated-parameters.json`. Do not borrow anything above for the MI half.
- **Data intact proof for the LTR restore path.** Proven for the BACPAC and MI `.bak`
  paths in earlier rounds. Cannot be proven here, because the backups had no data to
  preserve.
- **Restore into serverless compute**, and therefore any auto resume latency.
- **Any size above 20.2031 GiB.**
