# Validation matrix

Assertion-level checks for the LTR drain pipeline. `Subs` is the number of subscriptions
required. Evidence goes in `show-output/`.

## A. Survival and enumeration

| # | Assertion | How | Subs | Expected |
|---|---|---|---|---|
| A1 | LTR policy produces a backup | `az sql db ltr-policy set`, then poll | 1 | Backup appears, up to 7 days |
| A2 | Backups survive **database** deletion | `az sql db delete`, re-list | 1 | Still listed |
| A3 | Backups survive **server** deletion | `az sql server delete`, re-list | 1 | Still listed |
| A4 | Default listing hides deleted sources | list without `--database-state All` | 1 | Deleted-source backups **absent** |
| A5 | `--database-state All` reveals them | list with the flag | 1 | All backups present |
| A6 | Backup carries usable provenance | inspect JSON | 1 | `serverName`, `databaseName`, `backupTime`, `backupExpirationTime` populated |

A4 is the one that silently ruins a real drain: the default listing looks empty and the
run appears to succeed with nothing to do.

## B. SQL Database drain

| # | Assertion | How | Subs | Expected |
|---|---|---|---|---|
| B1 | Restore works after source deletion | `ltr-backup restore` to new server | 1 | Database online |
| B2 | Restore SKU can be overridden | restore a Premium source into GP 2 vCore | 1 | Succeeds; validates the cost saving |
| B3 | Restoring below source max size fails | restore 20 GB source into a 2 GB tier | 1 | Clean early failure |
| B4 | Hyperscale cannot cross tiers | restore Hyperscale into GP | 1 | Fails; confirms the documented limit |

B4 needs a Hyperscale database, which `Deploy-LtrLab.ps1` does not create (Hyperscale has
no serverless auto-pause at the low end, so it would bill continuously through the
multi-day LTR wait). Run it only if you actually have Hyperscale sources to migrate: add
one manually with `az sql db create --edition Hyperscale --family Gen5 --capacity 2`, wait
for its LTR backup, and confirm the drain reports the tier hint rather than a raw ARM error.
| B5 | BACPAC export succeeds | `az sql db export` | 1 | Blob written |
| B6 | BACPAC re-imports and matches | `az sql db import`, compare checksums | 1 | Row counts and checksums identical |
| B7 | Temp database is always dropped | kill the run mid-export | 1 | `finally` still drops it |
| B8 | Manifest records every attempt | inspect CSV | 1 | One row per backup, failures included |

B6 is the assertion that actually matters. An artifact that cannot be re-imported is not a
backup, and BACPAC has no equivalent of `RESTORE VERIFYONLY` to catch this early.

## C. Managed Instance drain

| # | Assertion | How | Subs | Expected |
|---|---|---|---|---|
| C1 | COPY_ONLY blocked by service-managed TDE | `BACKUP ... WITH COPY_ONLY` unmodified | 1 | Fails as documented |
| C2 | Disabling TDE unblocks it | `SET ENCRYPTION OFF`, poll to state 1, retry | 1 | Backup succeeds |
| C3 | Decryption polling terminates | watch `sys.dm_database_encryption_keys` | 1 | Reaches `encryption_state = 1` |
| C4 | `RESTORE VERIFYONLY` passes | run against the artifact | 1 | Succeeds |
| C5 | Corruption is detected | flip bytes in the blob, re-verify | 1 | **Fails.** Proves C4 is meaningful |
| C6 | Striping engages above threshold | run with `-GbPerStripe 1` | 1 | Multiple blobs, correct stripe count |
| C7 | Striped set restores | `RESTORE` from all URLs | 1 | Database online |
| C8 | Stripe ceiling is enforced | force > 64 stripes | 1 | Clean error, no partial blobs |
| C9 | Restoring into the existing MI is free | inspect cost analysis | 1 | No new compute line item |

C5 is easy to skip and worth more than C4. A verification step that has never failed has
not been shown to verify anything.

## D. Cross-subscription (the only genuine 2-subscription work)

| # | Assertion | How | Subs | Expected |
|---|---|---|---|---|
| D1 | BACPAC export to storage in sub B | `--storage-uri` pointing at sub B | **2** | Blob written to sub B |
| D2 | MI `BACKUP TO URL` to sub B | SAS credential for sub B container | **2** | Blob written to sub B |
| D3 | Works with no ARM rights on storage | run as a principal with zero RBAC there | 1 or 2 | Succeeds; proves key/SAS auth, not ARM |
| D4 | LTR restore into sub B is refused | attempt cross-subscription restore | **2** | Fails; confirms subscription lock |
| D5 | Same-region transfer is not billed | inspect cost analysis | **2** | No bandwidth line item |

D3 is the single-subscription proxy for D1 and D2. Run it even if a second subscription is
available; it isolates the *mechanism* rather than just the outcome.

**D6 is deliberately absent.** Subscription deletion purging LTR backups is irreversible
and must not be tested. It is taken from documentation.

## E. Cost model calibration

| # | Assertion | How | Subs | Expected |
|---|---|---|---|---|
| E1 | Drain time is linear in size | fit across 1, 5, 20 GB | 1 | R-squared >= 0.90 |
| E2 | Fixed and per-GB terms separate | `Measure-LtrCalibration.ps1` | 1 | Non-negative intercept |
| E3 | Compression varies with data shape | compare the two probes | 1 | Ratios differ substantially |
| E4 | Worst-case ratio is used for budget | re-run estimator with observed worst | 1 | Storage term revised |
| E5 | Estimator predicts a held-out case | predict 5 GB from 1 and 20 GB only | 1 | Within ~25% of measured |

E5 is the honest test of the model. Fitting a line through points it was fitted on proves
nothing; predicting a withheld point does. Run it with:

```powershell
.\Measure-LtrCalibration.ps1 -TimingCsv <manifest.csv> -ExcludeDatabase calib-5gb
```

The fitter drops that database, fits on the remaining sizes, then prints predicted versus
actual and warns if the error exceeds 25%.

**Why three sizes and two shapes.** A single database cannot separate fixed overhead from
per-GB slope, and a single data shape cannot bound compression. A dry run of
`Measure-LtrCalibration.ps1` against synthetic data with known ground truth
(restore = 10 + 0.4/GB, export = 5 + 1.5/GB) recovered both terms exactly at R-squared 1.0,
and reported a compression range of **1.02x to 33x** between the incompressible and
compressible probes. That spread is the point: the estimator's default assumption of 4x
would understate artifact storage roughly fourfold on incompressible data, and storage is
the dominant cost term over a multi-year retention.

## Evidence to capture

- `az sql db ltr-backup list` output before and after each deletion (A2 to A5)
- The C1 failure message verbatim; it is the documented behaviour in the wild
- `RESTORE VERIFYONLY` output for both the intact and corrupted artifact (C4, C5)
- Cost analysis export covering the drain window (C9, D5)
- `calibrated-parameters.json` and the drain manifest CSV (E1 to E5)

Sanitize per `labs/README.md` before committing: subscription IDs, tenant IDs, admin
passwords, storage keys and SAS tokens.
