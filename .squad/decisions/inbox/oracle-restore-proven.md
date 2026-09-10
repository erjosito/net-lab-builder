# Oracle decision: artifact restore proof is now first-class evidence

Date: 2026-09-10

## Decision

Treat artifact consumption as proven for both halves of `sql-ltr-backup-migration`, and
separate it explicitly from `RESTORE VERIFYONLY` and from LTR restore.

## Rationale

Jose challenged whether the lab had verified a restore or only an export. The answer before
the second round was only export plus `.bak` readability. The second round restored or
imported real archive artifacts into new databases and verified row counts plus aggregate
checksums against the sources.

## Evidence folded into README

| Path | Result |
|---|---|
| Managed Instance `.bak` | Restored into a new database in 30.5 s. Row count 130000 matched, checksum -1557385128 matched, ROWS allocation 1056 MiB matched. |
| SQL Database BACPAC | Imported with client-side sqlpackage in 198.6 s. Row count 131072 matched, checksum 12517530 matched, ROWS allocation 1104 MiB matched. |

The SQL Database LOG allocation differed after import, 1224 MiB source vs 472 MiB imported.
That is expected after a logical import and is not data loss.

## Boundary kept explicit

The production chain is:

1. LTR backup exists.
2. Restore the LTR backup.
3. Extract a portable artifact.
4. Store the artifact.
5. Later, restore or import the artifact.

Links 3 through 5 are now proven by the lab. Links 1 and 2 remain unverified and unmeasured
because no LTR backup has existed yet.

## Related documentation choices

- Keep R-squared null on the MI two-point timing fits because any two-point fit would be
  tautological.
- State that the TDE decryption slope is fitted on ROWS file GiB from `sys.database_files`.
  Using total file footprint including LOG changes the apparent rate by nearly 2x.
- Document Msg 41901 for `RESTORE ... WITH STATS` on Managed Instance.
- Document MI storage headroom as a hard planning constraint.
- Do not publish the 347.8 s BACPAC download as a throughput planning rate. It was a
  single-stream lab artifact; production should use `azcopy` or another parallel-capable
  transfer tool.
