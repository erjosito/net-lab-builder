# Managed Instance timing measurements

Date: 2026-09-10T13:20:00+02:00

## Scope and labels

These measurements were taken on the existing Managed Instance. No Managed Instance resize was performed, no public network access was enabled, and no Azure resources were deleted.

| Label | Meaning |
|---|---|
| MEASURED | Directly observed on the live Managed Instance during this run. |
| PROXY | Directly observed, but only as an indicator for another mechanism. |
| UNMEASURED | Not observed in this run. Values are null in machine-readable output. |

## Environment

| Field | Value |
|---|---|
| Managed Instance | `ltrlab552754-mi.8a97d4e15d77.database.windows.net` |
| Resource group | `rg-ltr-lab` |
| Region | `swedencentral` |
| SKU | `GP_Gen5`, 4 vCore |
| Instance storage ceiling | 32 GB total |
| Storage account | `ltrlab552754sa` |
| Container | `mi-backups` |
| Storage controls | Shared keys disabled, SAS disabled, public network access disabled |
| SQL authentication | Entra-only |
| Primary identity | UAMI `ltrlab552754-umi`, clientId `9dab92a8-7084-442e-8617-139fda64b1c9` |
| VM execution path | `az vm run-command invoke` against `ltrlab-vm` |

## Task 1: LTR hedge policy on `mitest`

Status: MEASURED.

The long-term retention policy was set with the Managed Instance command surface:

```powershell
$PSNativeCommandArgumentPassing='Standard'
az sql midb ltr-policy set -g rg-ltr-lab --mi ltrlab552754-mi -n mitest --weekly-retention P12W -o json
```

The command syntax was confirmed from `az sql midb ltr-policy set --help`: Managed Instance uses `--managed-instance/--mi` and `--name/-n`, not `--database`.

| Observation | Value |
|---|---|
| Policy set attempt UTC | 2026-09-10T11:02:07.0811838Z |
| Policy confirmed UTC | 2026-09-10T11:02:29.1634265Z |
| Weekly retention | `P12W` |
| Monthly retention | `PT0S` |
| Yearly retention | `PT0S` |
| Backup storage access tier | `Hot` |
| Immediate LTR backup list check UTC | 2026-09-10T11:02:34.0579569Z |
| Immediate LTR backups found | 0 |

The immediate backup check returned `[]`, which matches the earlier SQL DB observation that no LTR backup appeared shortly after policy enablement.

## Task 2: Service-managed TDE decryption throughput

Status: MEASURED.

Two calibration databases were created with default service-managed TDE enabled, seeded with mixed rows of approximately 75 percent repeated text and 25 percent `CRYPT_GEN_RANDOM` bytes, then decrypted and backed up. The test respected the 32 GB ceiling. Final observed user database allocation after the run was about 10.3 GiB across `mitest`, the two calibration databases, and the PITR proxy copy, plus MI/system overhead.

### Raw measurements

| Database | Payload rows | ROWS file GiB | Total file GiB | ALTER to `encryption_state = 1` | DROP DEK | BACKUP TO URL | Backup blob MiB | Compression vs ROWS file |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `mi_tde_1gb_20260910` | 130000 | 1.0313 | 1.1172 | 25.716 s | 0.047 s | 10.741 s | 250.5625 | 4.21x |
| `mi_tde_5gb_20260910` | 650000 | 5.0156 | 8.8516 | 80.701 s | 0.094 s | 51.986 s | 1247.9375 | 4.12x |

The 5 GB database log grew to 3928 MiB during seeding. That was within the 32 GB instance storage ceiling, so no smaller substitute size was needed.

### Decryption percent progression

`encryption_state = 5` means decryption in progress. `encryption_state = 1` means unencrypted.

| Database | UTC sample | State | Percent complete |
|---|---|---:|---:|
| `mi_tde_1gb_20260910` | 2026-09-10T11:06:19.3711605Z | 5 | 85.6297 |
| `mi_tde_1gb_20260910` | 2026-09-10T11:06:24.4018672Z | 5 | 100.0000 |
| `mi_tde_1gb_20260910` | 2026-09-10T11:06:29.4318409Z | 5 | 100.0000 |
| `mi_tde_1gb_20260910` | 2026-09-10T11:06:34.4647435Z | 1 | 0.0000 |
| `mi_tde_5gb_20260910` | 2026-09-10T11:13:26.1452574Z | 5 | 32.2479 |
| `mi_tde_5gb_20260910` | 2026-09-10T11:13:31.1868582Z | 5 | 48.9145 |
| `mi_tde_5gb_20260910` | 2026-09-10T11:13:36.2143175Z | 5 | 65.5812 |
| `mi_tde_5gb_20260910` | 2026-09-10T11:13:41.2371328Z | 5 | 82.0921 |
| `mi_tde_5gb_20260910` | 2026-09-10T11:13:46.2688635Z | 5 | 98.6030 |
| `mi_tde_5gb_20260910` | 2026-09-10T11:13:51.2923544Z | 5 | 100.0000 |
| `mi_tde_5gb_20260910` | 2026-09-10T11:13:56.3159534Z | 5 | 100.0000 |
| `mi_tde_5gb_20260910` | 2026-09-10T11:14:01.3582725Z | 5 | 100.0000 |
| `mi_tde_5gb_20260910` | 2026-09-10T11:14:06.3805261Z | 5 | 100.0000 |
| `mi_tde_5gb_20260910` | 2026-09-10T11:14:11.4240718Z | 5 | 100.0000 |
| `mi_tde_5gb_20260910` | 2026-09-10T11:14:16.4464766Z | 5 | 100.0000 |
| `mi_tde_5gb_20260910` | 2026-09-10T11:14:21.4708170Z | 5 | 100.0000 |
| `mi_tde_5gb_20260910` | 2026-09-10T11:14:26.4961366Z | 5 | 100.0000 |
| `mi_tde_5gb_20260910` | 2026-09-10T11:14:31.5240630Z | 5 | 100.0000 |
| `mi_tde_5gb_20260910` | 2026-09-10T11:14:36.5570535Z | 1 | 0.0000 |

### Fitted decryption rate

Status: MEASURED, with a caution.

The two points are non-zero and non-degenerate, so a simple two-point line is valid as a coarse planning slope. The rate is based on ROWS file GiB, because the requested calibration sizes targeted data-file allocation and TDE progress tracked the data-file scan. R-squared is set to null because with exactly two points it would be tautological and would overstate confidence.

| Parameter | Value |
|---|---:|
| Fixed term | 0.1914 min |
| Slope | 0.2300 min/GiB |
| Slope | 13.8002 sec/GiB |
| R-squared | null |

Observed backup timing on the same two points was approximately 0.1725 min/GiB against ROWS file GiB, but that is reported as raw measurement support only. The main measured term for planning here is TDE decryption.

## Task 3: MI restore duration using PITR as a proxy

Status: PROXY.

This is not an LTR restore measurement. It is a same-instance PITR restore of `mitest`, used only as an indicative lower-bound proxy for Managed Instance restore machinery. LTR restore remains UNMEASURED and may be slower because LTR backups can live in different storage.

| Field | Value |
|---|---|
| Source database | `mitest` |
| Destination database | `mitest_pitr_proxy_20260910` |
| Source creation time from Azure | 2026-09-10T10:19:39.590000+00:00 |
| Earliest restore point observed | 2026-09-10T10:24:12.090000+00:00 |
| Restore point used | 2026-09-10T10:30:00Z |
| Start UTC | 2026-09-10T11:17:02.5856114Z |
| End UTC | 2026-09-10T11:17:58.1427565Z |
| Wall-clock duration | 55.549 s |
| Destination status | `Online` |
| Destination allocation | 64 MiB ROWS, 40 MiB LOG |

## Remaining unmeasured terms

| Term | Status | Note |
|---|---|---|
| Managed Instance LTR backup availability delay | UNMEASURED | LTR policy was set and the immediate list returned no backups. No multi-day wait was performed. |
| Managed Instance LTR restore duration | UNMEASURED | No LTR backup existed during this run. PITR restore is recorded separately as a PROXY only. |
| Managed Instance TDE decryption above 5 GiB | UNMEASURED | Larger sizes were not attempted to preserve the 32 GB storage ceiling and leave room for the PITR proxy copy. |

