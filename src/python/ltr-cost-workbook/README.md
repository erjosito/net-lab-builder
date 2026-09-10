# LTR backup storage cost workbook

Generates `ltr-backup-storage-costs.xlsx`, a cost model for parking Azure SQL
long-term retention (LTR) backups in a storage account: what the transfer costs,
and what keeping the artifacts costs over the retention period.

This is the storage half of the picture. The compute half (restore plus export
time) lives in `src/powershell/sql-ltr-export/Get-LtrExportCostEstimate.ps1`.

## Usage

```powershell
pip install -r requirements.txt
python new_ltr_cost_workbook.py --refresh-prices
```

| Flag | Meaning |
| --- | --- |
| `--refresh-prices` | Re-fetch from the Azure retail prices API and rewrite `price-snapshot.json` |
| `--region` | Azure region to price (default `eastus`) |
| `--output` | Output path for the workbook |

Without `--refresh-prices` the cached `price-snapshot.json` is used, so the
workbook is reproducible and its provenance is auditable.

## Sheets

| Sheet | Contents |
| --- | --- |
| Read me | What is modelled, what is verified, what is assumed |
| Parameters | The yellow input cells. Everything else recalculates from these |
| Prices | The raw price snapshot with its retrieval timestamp, volume bands and any substituted rates |
| Cost matrix | Backup count (10 to 800) against database size (5 to 1000 GB), split into transfer / storage / total |
| Tier comparison | All 21 tier and redundancy combinations, including read-back cost |
| Compression sensitivity | How the total moves as the compression ratio moves |

Every cell is a live Excel formula, not a baked value. Change an input and the
whole model recalculates.

## Known simplifications

- **Volume banding.** The model prices everything at the first band (0 to 50 TB).
  Only the **Hot** tier is volume-banded; Cool, Cold and Archive are flat at any
  volume. For Hot scenarios above 50 TB the model is roughly 4 percent
  conservative. The Parameters sheet warns when this applies, and the Prices sheet
  lists the higher bands.
- **Substituted operation rates.** Azure does not publish an operation meter for
  every redundancy. Where one is missing it is taken from the closest published
  redundancy (RA-GZRS from GZRS, not from LRS) and flagged in the Prices sheet's
  Substituted column. Falling back to LRS would make read-access SKUs look cheaper
  than their non-read-access parents, which is wrong.
- **Restore and export compute is excluded.** It is one-time and small. The
  headline cell is labelled "GRAND TOTAL (storage side)" to make that explicit.

## Headline findings

- **Transfer is free in the normal case.** Ingress into Azure Storage is never
  charged, and a subscription boundary is not a network billing boundary. Only a
  region boundary is. A storage account in a different subscription but the same
  region costs $0 to fill.
- **Storage dominates**, typically by 50x or more over everything else.
- **Archive is usually the right tier** for compliance copies that must exist but
  will probably never be read. Caveats: 180-day minimum retention charge, and
  rehydration takes up to 15 hours at standard priority.
- **Retrieval is the forgotten column.** In the default scenario the Archive tier
  costs $62 to store for 7 years and $111 to read back once.
- **Compression is the weakest input** and it scales the largest term. The
  default 4x assumption is unverified; observed ratios spanned 1.02x to 33x.

## Verification

Prices come from the Azure retail prices API, not from memory. Formula output was
checked by recalculating the generated workbook with LibreOffice headless and
comparing against hand calculations:

| Check | Expected | Workbook |
| --- | --- | --- |
| Artifact GB (60 x 50 GB at 4x) | 750 | 750 |
| Archive LRS storage, 84 months | $62.37 | $62.37 |
| Grand total | $64.29 | $64.29 |
| Read back once | $111.00 | $111.00 |
| Matrix corner, 800 backups x 1000 GB | $17,144 | $17,144 |
| Worst case vs default compression | 3.92x | 3.92x |

The destination dropdown's range reference was also checked directly in the
generated OOXML, since openpyxl will happily write a `formula1` that Excel then
rejects.

Retail prices exclude any enterprise agreement discount, reservation or credit.
