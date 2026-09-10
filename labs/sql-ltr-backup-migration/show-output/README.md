# Show-output index for sql-ltr-backup-migration lab

Run date: 2026-09-10
Session UTC start: 2026-09-10T07:57:39Z
Resource group: rg-ltr-lab
Subscription: Litware-MngEnvMCAP642473-jomore (<SUBSCRIPTION_ID>)
Region: swedencentral

## Files in this directory

| File | Contents |
|---|---|
| 01-databases-created.txt | az sql db list output after all 5 databases came Online |
| 02-seed-results.txt | Per-database seeding output (row count, allocated GB, time) |
| 03-ltr-policy-findings.txt | LTR policy set results and initial backup check |
| 04-export-results.txt | Per-database sqlpackage export results (sizes, compression, time) |
| 05-calibration-output.txt | Measure-LtrCalibration.ps1 output |
| 06-calibrated-parameters.json | Calibrated JSON output from Measure-LtrCalibration.ps1 |

## Key measurements

### BACPAC compression ratios (sqlpackage, private endpoint, D4s_v5 VM)

| Database | Data shape | Source GB | Artifact GB | Compression |
|---|---|---|---|---|
| probe-compressible | Repeated bytes (synthetic upper bound, not a planning value) | 5.0781 | 0.0349 | 145.3x |
| probe-random | CRYPT_GEN_RANDOM (incompressible) | 5.0781 | 4.9028 | 1.04x |
| calib-1gb | Mixed (realistic blend) | 1.0781 | 0.2538 | 4.25x |
| calib-5gb | Mixed (realistic blend) | 5.0781 | 1.2690 | 4.00x |
| calib-20gb | Mixed (realistic blend) | 20.2031 | 5.0758 | 3.98x |

**Default estimate was 4.0x. Mixed data VALIDATES that default.**
**Worst case for budgeting: 1.04x (random/high-entropy data).**
**Honest planning range: 1.04x (incompressible) to 4.25x (mixed). The 145.3x figure is synthetic; seeding with a single repeated byte pattern is not a data shape any production database has. It brackets the measurement but is not a planning value.**

SizeGb in the manifest is derived from `sys.database_files.size` (allocated 8 KB pages),
not from actual data row sizes. For freshly seeded databases with no deletes or page
splits the difference is small: allocated exceeds target by 1-8% (fill factor, IAM pages,
system structures). The compression ratio is therefore allocated-size-to-artifact, which
is the correct basis for capacity planning (you care about how big the BACPAC is relative
to the SQL file footprint on disk).

### Export throughput (sqlpackage over private endpoint, same region, D4s_v5)

Linear fit on mixed data: `ExportMin = 0.36 + 0.1588 * SizeGb` (R-squared = 0.9995)

| Database | Source GB | Export min | Min/GB observed |
|---|---|---|---|
| calib-1gb | 1.0781 | 0.499 | 0.463 |
| calib-5gb | 5.0781 | 1.202 | 0.237 |
| calib-20gb | 20.2031 | 3.558 | 0.176 |

**Default estimate was 1.20 min/GB. Measured is 0.16 min/GB (7.5x faster).**
This is a private-endpoint environment on a high-memory VM. Public-internet sqlpackage
will be slower; the default may have been measured under different conditions.

### LTR policy findings

- LTR not supported when auto-pause is enabled (LtrConfigPolicyUnsupportedIfAutoPauseEnabled).
- After disabling auto-pause, policy set succeeded on all 5 databases.
- No LTR backups appeared within 2 minutes of policy set (checked at 2026-09-10T09:03:35Z).
- No LTR backups appeared within 25 minutes of policy set (rechecked at 2026-09-10T09:26:08Z).
- Answer to "does enabling LTR immediately copy the latest PITR?": NOT within 25 minutes.
  The documentation says it may take up to 7 days; the immediate-copy path could still
  materialise hours later. Re-check with Watch-LtrLabBackups.ps1.
