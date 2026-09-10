#!/usr/bin/env python3
"""
Build an Excel cost model for parking Azure SQL LTR backups in blob storage.

Answers two questions as a function of backup count and database size:
  1. What does it cost to TRANSFER the artifacts into a storage account?
  2. What does it cost to KEEP them there for the retention period?

Prices come from the Azure retail prices API and are cached in price-snapshot.json
so the workbook is reproducible and its provenance is auditable. The workbook itself
uses live Excel formulas throughout: change an input and everything recalculates.
Nothing is baked in as a dead value.

Usage:
    python new_ltr_cost_workbook.py                    # use the cached snapshot
    python new_ltr_cost_workbook.py --refresh-prices   # re-fetch, then build
    python new_ltr_cost_workbook.py --region westeurope --refresh-prices
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import urllib.parse
import urllib.request

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

RETAIL_API = "https://prices.azure.com/api/retail/prices"
HERE = pathlib.Path(__file__).parent
SNAPSHOT = HERE / "price-snapshot.json"

TIERS = ["Hot", "Cool", "Cold", "Archive"]
REDUNDANCIES = ["LRS", "ZRS", "GRS", "GZRS", "RA-GRS", "RA-GZRS"]

# Bandwidth. Deliberately not scraped: the Standard Data Transfer Out meters are
# banded and region-pair dependent, and picking one automatically would be a guess
# dressed up as a lookup. These are the rates that apply to this scenario.
#   Ingress into a storage account is always free.
#   Same region  -> free. Crossing a SUBSCRIPTION boundary costs nothing; only
#                   crossing a REGION boundary does. This is the key finding.
#   Cross region -> Standard Inter-Region Data Transfer.
#   Internet     -> egress out of Azure, after the first 100 GB/month.
BANDWIDTH = [
    ("Same region (any subscription)", 0.00),
    ("Cross region", 0.02),
    ("Out to the internet", 0.087),
]

# --- Styling ------------------------------------------------------------------
C_HEAD = "1F4E79"     # dark blue
C_SUB = "2E75B6"      # mid blue
C_INPUT = "FFF2CC"    # yellow: editable
C_CALC = "E2EFDA"     # green: calculated
C_WARN = "FCE4D6"     # orange: watch out
C_BAND = "F2F2F2"

F_TITLE = Font(bold=True, size=14, color="FFFFFF")
F_HEAD = Font(bold=True, color="FFFFFF")
F_BOLD = Font(bold=True)
F_NOTE = Font(italic=True, size=9, color="595959")

THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

MONEY = '"$"#,##0.00'
MONEY4 = '"$"#,##0.0000'
MONEY6 = '"$"#,##0.000000'
NUM = "#,##0"
NUM2 = "#,##0.00"


def fetch_all(filter_expr: str) -> list[dict]:
    """Page through the retail API. It returns 100 items per page."""
    items: list[dict] = []
    url = f"{RETAIL_API}?$filter={urllib.parse.quote(filter_expr)}"
    while url:
        with urllib.request.urlopen(url, timeout=60) as resp:
            payload = json.load(resp)
        items.extend(payload.get("Items", []))
        url = payload.get("NextPageLink")
    return items


def refresh_prices(region: str) -> dict:
    """Pull blob storage meters and reduce them to one row per tier+redundancy."""
    print(f"Fetching blob storage prices for {region}...")
    rows = fetch_all(
        f"serviceName eq 'Storage' and armRegionName eq '{region}' "
        f"and priceType eq 'Consumption' and productName eq 'General Block Blob v2'"
    )
    print(f"  {len(rows)} meters returned")

    def pick(tier: str, red: str, kind: str) -> float | None:
        """
        Find one meter. Meter naming is inconsistent: some include the redundancy
        ('Cool LRS Write Operations'), others do not ('Cool Data Retrieval'), so
        match on skuName for redundancy and on meterName only for the operation.
        """
        sku = f"{tier} {red}"
        best = None
        for r in rows:
            if r.get("skuName") != sku:
                continue
            meter = r.get("meterName", "")
            if kind not in meter:
                continue
            # 'Archive Priority Data Retrieval' is a different, pricier product than
            # 'Archive Data Retrieval'. Never silently substitute one for the other.
            if "Priority" in meter and "Priority" not in kind:
                continue
            # Data Stored is banded by volume. Take the first band (0 to 50 TB) as
            # the headline rate and record the higher bands separately.
            if kind == "Data Stored" and float(r.get("tierMinimumUnits", 0)) != 0:
                continue
            price = float(r["retailPrice"])
            if best is None or price < best:
                best = price
        return best

    def bands(tier: str, red: str) -> list[dict]:
        """Volume bands for Data Stored, if this meter is banded at all."""
        out = []
        for r in rows:
            if r.get("skuName") != f"{tier} {red}":
                continue
            if "Data Stored" not in r.get("meterName", ""):
                continue
            out.append({"from_gb": float(r.get("tierMinimumUnits", 0)),
                        "usd_gb_month": float(r["retailPrice"])})
        return sorted(out, key=lambda b: b["from_gb"])

    table = []
    for tier in TIERS:
        for red in REDUNDANCIES:
            stored = pick(tier, red, "Data Stored")
            if stored is None:
                continue  # e.g. Archive has no ZRS/GZRS
            table.append(
                {
                    "key": f"{tier} {red}",
                    "tier": tier,
                    "redundancy": red,
                    "stored_usd_gb_month": stored,
                    "bands": bands(tier, red),
                    "write_usd_per_10k": pick(tier, red, "Write Operations"),
                    "read_usd_per_10k": pick(tier, red, "Read Operations"),
                    "retrieval_usd_gb": pick(tier, red, "Data Retrieval") or 0.0,
                    "substituted": [],
                }
            )

    # Operation meters are not published for every redundancy. Where one is missing,
    # substitute along the redundancy relationship that actually holds: a read-access
    # SKU prices its operations like its non-read-access parent (RA-GZRS like GZRS),
    # and only as a last resort like LRS. Falling straight back to LRS produces
    # nonsense such as RA-GZRS writes costing less than GZRS writes.
    by_key = {r["key"]: r for r in table}
    fallback_order = {
        "RA-GZRS": ["GZRS", "ZRS", "LRS"],
        "RA-GRS": ["GRS", "LRS"],
        "GZRS": ["ZRS", "LRS"],
        "GRS": ["LRS"],
        "ZRS": ["LRS"],
        "LRS": [],
    }
    for r in table:
        for col in ("write_usd_per_10k", "read_usd_per_10k", "retrieval_usd_gb"):
            if r[col]:
                continue
            # A genuine zero is meaningful for retrieval (Hot has no retrieval charge),
            # so only substitute when the meter was absent entirely.
            if col == "retrieval_usd_gb" and r["tier"] == "Hot":
                r[col] = 0.0
                continue
            for red in fallback_order.get(r["redundancy"], ["LRS"]):
                donor = by_key.get(f"{r['tier']} {red}")
                if donor and donor.get(col):
                    r[col] = donor[col]
                    r["substituted"].append(f"{col} from {red}")
                    break
            if r[col] is None:
                r[col] = 0.0

    snap = {
        "retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "region": region,
        "currency": "USD",
        "source": RETAIL_API,
        "product": "General Block Blob v2",
        "note": (
            "Data Stored is the first volume band (0-50 TB). Only the Hot tier is "
            "volume-banded; Cool, Cold and Archive are flat. Operation meters are not "
            "published for every redundancy; missing ones are substituted from the "
            "closest published redundancy and flagged in the Substituted column."
        ),
        "storage": sorted(table, key=lambda r: (TIERS.index(r["tier"]), r["redundancy"])),
        "bandwidth": [{"destination": d, "usd_per_gb": p} for d, p in BANDWIDTH],
        "private_link": fetch_private_link(),
        "private_dns": fetch_private_dns(),
    }
    SNAPSHOT.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    print(f"  wrote {SNAPSHOT.name}")
    return snap


def fetch_private_link() -> dict:
    """
    Private Link meters are published against armRegionName 'Global', not against a
    specific region, so the region filter used for storage must NOT be applied here.
    Getting this wrong returns an empty set and silently prices the endpoint at zero.
    """
    print("Fetching Private Link prices (region 'Global')...")
    rows = fetch_all(
        "productName eq 'Virtual Network Private Link' and priceType eq 'Consumption' "
        "and armRegionName eq 'Global'"
    )
    print(f"  {len(rows)} meters returned")

    def meter(name: str) -> list[dict]:
        out = [
            {"from_gb": float(r.get("tierMinimumUnits", 0)),
             "price": float(r["retailPrice"]),
             "unit": r.get("unitOfMeasure")}
            for r in rows if r.get("meterName") == name
        ]
        return sorted(out, key=lambda b: b["from_gb"])

    ep = meter("Standard Private Endpoint")
    ing = meter("Standard Data Processed - Ingress")
    egr = meter("Standard Data Processed - Egress")
    return {
        "endpoint_usd_hour": ep[0]["price"] if ep else None,
        "ingress_usd_gb": ing[0]["price"] if ing else None,
        "egress_usd_gb": egr[0]["price"] if egr else None,
        "ingress_bands": ing,
        "egress_bands": egr,
    }


def fetch_private_dns() -> dict:
    """
    A private endpoint for blob storage normally needs a privatelink.blob.core.windows.net
    private DNS zone. Azure DNS prices this by geography zone rather than by Azure region;
    'Zone 1' covers the commercial regions this model targets.
    """
    print("Fetching Azure private DNS prices...")
    rows = fetch_all("serviceName eq 'Azure DNS' and priceType eq 'Consumption'")
    print(f"  {len(rows)} meters returned")

    def pick(meter_name: str, tier_min: float) -> float | None:
        for pref in ("Zone 1", "", None):
            for r in rows:
                if r.get("meterName") != meter_name:
                    continue
                if float(r.get("tierMinimumUnits", 0)) != tier_min:
                    continue
                reg = r.get("armRegionName") or ""
                if pref is None or reg == pref:
                    return float(r["retailPrice"])
        return None

    return {
        "zone_usd_month_first25": pick("Private Zone", 0.0),
        "zone_usd_month_over25": pick("Private Zone", 25.0),
        "queries_usd_per_million": pick("Private Queries", 0.0),
    }


# --- Sheet helpers ------------------------------------------------------------
def title_row(ws, text: str, width: int, fill: str = C_HEAD) -> None:
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=width)
    c = ws.cell(row=1, column=1, value=text)
    c.font = F_TITLE
    c.fill = PatternFill("solid", fgColor=fill)
    c.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 24


def header_cells(ws, row: int, values: list[str], start: int = 1) -> None:
    for i, v in enumerate(values):
        c = ws.cell(row=row, column=start + i, value=v)
        c.font = F_HEAD
        c.fill = PatternFill("solid", fgColor=C_SUB)
        c.border = BOX
        c.alignment = Alignment(horizontal="center", wrap_text=True)


def label(ws, row: int, text: str, note: str | None = None) -> None:
    ws.cell(row=row, column=1, value=text).font = F_BOLD
    if note:
        ws.cell(row=row, column=3, value=note).font = F_NOTE


def widths(ws, spec: dict[str, int]) -> None:
    for col, w in spec.items():
        ws.column_dimensions[col].width = w


# --- Sheets -------------------------------------------------------------------
def sheet_readme(wb: Workbook, snap: dict) -> None:
    ws = wb.create_sheet("Read me")
    title_row(ws, "Azure SQL LTR backups: transfer and long-term storage cost", 2)
    widths(ws, {"A": 34, "B": 96})

    blocks = [
        ("What this models", ""),
        ("", "The cost of draining Azure SQL Database / Managed Instance long-term retention (LTR) "
             "backups into a storage account and keeping them there. Use it when the subscription "
             "that owns the LTR backups is going to be deleted."),
        ("", "LTR backups survive deletion of the database, the server and the instance. They do NOT "
             "survive deletion of the SUBSCRIPTION. If the subscription can be kept alive, you do not "
             "need this pipeline at all, and that is almost always the cheaper answer."),
        ("", ""),
        ("The transfer answer", ""),
        ("", "Transferring the backups into a storage account is FREE in the normal case."),
        ("", "Ingress into Azure Storage is never charged. A subscription boundary is not a billing "
             "boundary for network traffic; only a REGION boundary is. So if the destination storage "
             "account is in the same region as the source, transfer costs $0 even when it belongs to "
             "a completely different subscription or tenant."),
        ("", "You only pay if you cross regions ($0.02/GB) or send the data out to the internet "
             "($0.087/GB). Write operations cost a few cents and are included for completeness."),
        ("", ""),
        ("The real cost", ""),
        ("", "Long-term storage dominates, typically by a factor of 50 or more over everything else. "
             "The two levers that matter are the storage TIER and the COMPRESSION RATIO."),
        ("", ""),
        ("How to use it", ""),
        ("", "1. Open 'Parameters' and set the yellow cells. Everything else recalculates."),
        ("", "2. 'Cost matrix' sweeps backup count against database size."),
        ("", "3. 'Tier comparison' shows what each storage tier costs for your scenario, including "
             "what it costs to read the data back."),
        ("", "4. 'Compression sensitivity' shows how much the answer moves with the one number "
             "nobody has measured yet."),
        ("", "5. 'Private endpoint variant' adds the cost of reaching the storage account "
             "privately. It is additive and does not change the other sheets."),
        ("", ""),
        ("Private endpoints", ""),
        ("", "If you reach the storage account over a private endpoint, the endpoint bills by "
             "the hour for as long as it exists, whether or not anything is using it. Over a "
             "multi-year retention that standing charge can exceed the cost of the data itself. "
             "The fix is to create the endpoint for the drain, delete it, and re-create it if "
             "someone ever needs to read the archive."),
        ("", ""),
        ("Confidence", ""),
        ("", "VERIFIED: all prices, taken from the Azure retail prices API (see 'Prices' for the "
             "exact retrieval timestamp). Transfer and storage arithmetic."),
        ("", "ASSUMED: the compression ratio. This is the weakest input and it drives the largest "
             "term. Measured ratios in testing ranged from 1.02x on incompressible data to 33x on "
             "highly repetitive data, against a default assumption of 4x. Budget with the worst "
             "ratio you actually observe."),
        ("", "EXCLUDED: the compute cost of restoring each backup before exporting it. It is small "
             "and one-time. See Get-LtrExportCostEstimate.ps1 in the toolkit for that half."),
        ("", ""),
        ("Prices retrieved", f"{snap['retrieved_utc']}  |  region: {snap['region']}  |  {snap['currency']}"),
        ("Caveat", "Retail prices exclude any enterprise agreement discount, reservation or credit."),
    ]
    r = 3
    for head, body in blocks:
        if head:
            ws.cell(row=r, column=1, value=head).font = Font(bold=True, color=C_HEAD)
        if body:
            c = ws.cell(row=r, column=2, value=body)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            ws.row_dimensions[r].height = max(15, 13 * (len(body) // 95 + 1))
        r += 1


def sheet_prices(wb: Workbook, snap: dict) -> tuple[int, int]:
    """Returns (last storage row, first bandwidth data row)."""
    ws = wb.create_sheet("Prices")
    title_row(ws, "Price snapshot from the Azure retail prices API", 9)
    widths(ws, {"A": 34, "B": 12, "C": 14, "D": 20, "E": 20, "F": 20, "G": 22,
                "H": 22, "I": 30})

    c = ws.cell(row=2, column=1, value=(
        f"Retrieved {snap['retrieved_utc']} for region '{snap['region']}' in {snap['currency']}. "
        f"Product: {snap['product']}. {snap['note']}"))
    c.font = F_NOTE
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=9)

    header_cells(ws, 4, [
        "Key", "Tier", "Redundancy", "Stored $/GB/month",
        "Write $/10k ops", "Read $/10k ops", "Retrieval $/GB",
        "Volume banded?", "Substituted rates",
    ])

    r = 5
    for row in snap["storage"]:
        ws.cell(row=r, column=1, value=row["key"])
        ws.cell(row=r, column=2, value=row["tier"])
        ws.cell(row=r, column=3, value=row["redundancy"])
        ws.cell(row=r, column=4, value=row["stored_usd_gb_month"]).number_format = MONEY6
        ws.cell(row=r, column=5, value=row["write_usd_per_10k"]).number_format = MONEY4
        ws.cell(row=r, column=6, value=row["read_usd_per_10k"]).number_format = MONEY4
        ws.cell(row=r, column=7, value=row["retrieval_usd_gb"]).number_format = MONEY4

        bands = [b for b in row.get("bands", []) if b["from_gb"] > 0]
        if bands:
            desc = "; ".join(
                f"over {b['from_gb']:,.0f} GB: ${b['usd_gb_month']:.6f}" for b in bands)
            bc = ws.cell(row=r, column=8, value=desc)
            bc.font = F_NOTE
            bc.fill = PatternFill("solid", fgColor=C_WARN)
        else:
            ws.cell(row=r, column=8, value="flat").font = F_NOTE

        sub = row.get("substituted") or []
        if sub:
            sc = ws.cell(row=r, column=9, value="; ".join(sub))
            sc.font = F_NOTE
            sc.fill = PatternFill("solid", fgColor=C_WARN)

        for col in range(1, 10):
            ws.cell(row=r, column=col).border = BOX
            if row["tier"] == "Archive" and col <= 7:
                ws.cell(row=r, column=col).fill = PatternFill("solid", fgColor=C_BAND)
        r += 1
    last = r - 1

    bw_head = r + 2
    ws.cell(row=bw_head - 1, column=1,
            value="Bandwidth (egress out of the source region)").font = F_BOLD
    header_cells(ws, bw_head, ["Destination", "$/GB"])
    bw_first = bw_head + 1
    for i, b in enumerate(snap["bandwidth"]):
        ws.cell(row=bw_first + i, column=1, value=b["destination"]).border = BOX
        c = ws.cell(row=bw_first + i, column=2, value=b["usd_per_gb"])
        c.number_format = MONEY4
        c.border = BOX
    foot = bw_first + len(snap["bandwidth"]) + 1
    ws.cell(row=foot, column=1, value=(
        "Ingress into Azure Storage is always free. A subscription boundary costs nothing; "
        "only a region boundary does.")).font = F_NOTE
    ws.cell(row=foot + 1, column=1, value=(
        "Volume banding: the rest of this workbook prices everything at the first band. "
        "Only the Hot tier is banded, and the discount above 50 TB is roughly 4 percent, so "
        "for Hot scenarios above 50 TB the workbook is slightly conservative. Cool, Cold and "
        "Archive are flat at any volume.")).font = F_NOTE

    pl = snap.get("private_link") or {}
    dns = snap.get("private_dns") or {}
    pe_head = foot + 3
    ws.cell(row=pe_head - 1, column=1,
            value="Private endpoint and private DNS").font = F_BOLD
    header_cells(ws, pe_head, ["Item", "Rate"])
    pe_first = pe_head + 1
    pe_rows = [
        ("Private endpoint ($/hour)", pl.get("endpoint_usd_hour"), MONEY4),
        ("Data processed, ingress ($/GB)", pl.get("ingress_usd_gb"), MONEY4),
        ("Data processed, egress ($/GB)", pl.get("egress_usd_gb"), MONEY4),
        ("Private DNS zone ($/month, first 25)", dns.get("zone_usd_month_first25"), MONEY4),
        ("Private DNS queries ($/million)", dns.get("queries_usd_per_million"), MONEY4),
    ]
    for i, (name, val, fmt) in enumerate(pe_rows):
        ws.cell(row=pe_first + i, column=1, value=name).border = BOX
        c = ws.cell(row=pe_first + i, column=2, value=val if val is not None else 0.0)
        c.number_format = fmt
        c.border = BOX
        if val is None:
            c.fill = PatternFill("solid", fgColor=C_WARN)

    pe_foot = pe_first + len(pe_rows) + 1
    ing_bands = [b for b in (pl.get("ingress_bands") or []) if b["from_gb"] > 0]
    band_txt = ("; ".join(f"over {b['from_gb']:,.0f} GB: ${b['price']}" for b in ing_bands)
                or "no higher bands published")
    ws.cell(row=pe_foot, column=1, value=(
        "Private endpoint meters are published against region 'Global', not against an Azure "
        "region, so they are identical everywhere in the commercial cloud. Data processed is "
        f"volume-banded ({band_txt}); this workbook prices the first band, which holds for "
        "anything under 1 PB.")).font = F_NOTE
    ws.cell(row=pe_foot + 1, column=1, value=(
        "Azure DNS prices private zones by geography zone rather than by region. These are the "
        "'Zone 1' rates, which cover the commercial regions this model targets.")).font = F_NOTE

    ws.freeze_panes = "A5"
    return last, bw_first, pe_first


def sheet_parameters(wb: Workbook, snap: dict, price_last: int, bw_first: int) -> None:
    ws = wb.create_sheet("Parameters", 1)
    title_row(ws, "Parameters  (edit the yellow cells)", 4)
    widths(ws, {"A": 44, "B": 16, "C": 66, "D": 4})

    bw_last = bw_first + len(snap["bandwidth"]) - 1
    dest_rng = f"Prices!$A${bw_first}:$A${bw_last}"
    rate_rng = f"Prices!$B${bw_first}:$B${bw_last}"
    key_rng = f"Prices!$A$5:$A${price_last}"

    def inp(row, name, value, note, fmt=None):
        label(ws, row, name, note)
        c = ws.cell(row=row, column=2, value=value)
        c.fill = PatternFill("solid", fgColor=C_INPUT)
        c.border = BOX
        c.font = F_BOLD
        if fmt:
            c.number_format = fmt
        return c

    def calc(row, name, formula, note, fmt=MONEY):
        label(ws, row, name, note)
        c = ws.cell(row=row, column=2, value=formula)
        c.fill = PatternFill("solid", fgColor=C_CALC)
        c.border = BOX
        c.number_format = fmt
        return c

    ws.cell(row=3, column=1, value="INPUTS").font = Font(bold=True, color=C_HEAD)
    inp(4, "Number of LTR backups", 60, "How many restore points you must preserve.", NUM)
    inp(5, "Average database size (GB)", 50, "Source size, before compression.", NUM2)
    inp(6, "Compression ratio", 4.0,
        "Source GB per artifact GB. THE weakest assumption. Measured 1.02x to 33x.", NUM2)
    inp(7, "Retention (months)", 84, "84 = 7 years.", NUM)
    inp(8, "Storage tier", "Archive", "Hot / Cool / Cold / Archive.")
    inp(9, "Redundancy", "LRS", "LRS / ZRS / GRS / GZRS / RA-GRS / RA-GZRS.")
    inp(10, "Artifact destination", snap["bandwidth"][0]["destination"],
        "Same region is free, even across subscriptions.")
    inp(11, "Upload block size (MB)", 4,
        "MI BACKUP TO URL uses 4 MB. Only affects the small write-operations term.", NUM)

    dv_tier = DataValidation(type="list", formula1=f'"{",".join(TIERS)}"', allow_blank=False)
    dv_red = DataValidation(type="list", formula1=f'"{",".join(REDUNDANCIES)}"', allow_blank=False)
    dv_dest = DataValidation(type="list", formula1=dest_rng, allow_blank=False)
    for dv, cell in ((dv_tier, "B8"), (dv_red, "B9"), (dv_dest, "B10")):
        ws.add_data_validation(dv)
        dv.add(ws[cell])

    ws.cell(row=13, column=1, value="RESOLVED RATES").font = Font(bold=True, color=C_HEAD)
    calc(14, "Storage $/GB/month",
         f'=IFERROR(INDEX(Prices!$D$5:$D${price_last},MATCH($B$8&" "&$B$9,{key_rng},0)),"not offered")',
         "Looked up from the price snapshot. Archive has no ZRS.", MONEY6)
    calc(15, "Write $/10k operations",
         f'=IFERROR(INDEX(Prices!$E$5:$E${price_last},MATCH($B$8&" "&$B$9,{key_rng},0)),0)',
         "", MONEY4)
    calc(16, "Transfer $/GB",
         f'=IFERROR(INDEX({rate_rng},MATCH($B$10,{dest_rng},0)),0)',
         "Egress. Zero unless you cross a region boundary.", MONEY4)

    ws.cell(row=18, column=1, value="VOLUMES").font = Font(bold=True, color=C_HEAD)
    calc(19, "Total source data (GB)", "=$B$4*$B$5", "Backups x average size.", NUM)
    calc(20, "Total artifact data (GB)", "=IF($B$6>0,$B$19/$B$6,0)",
         "What actually lands in blob storage.", NUM)
    calc(21, "Write operations", "=IF($B$11>0,ROUNDUP($B$20*1024/$B$11,0),0)",
         "One block per upload chunk.", NUM)

    ws.cell(row=23, column=1, value="COSTS").font = Font(bold=True, color=C_HEAD)
    calc(24, "Transfer: bandwidth", "=$B$20*$B$16", "Zero for same-region destinations.")
    calc(25, "Transfer: write operations", "=$B$21/10000*$B$15", "Nearly always trivial.")
    calc(26, "Transfer: TOTAL (one time)", "=$B$24+$B$25", "The whole cost of getting the data in.")
    calc(27, "Storage per month", "=$B$20*$B$14", "")
    calc(28, "Storage over full retention", "=$B$27*$B$7", "The number that actually matters.")

    c = calc(30, "GRAND TOTAL (storage side)", "=$B$26+$B$28",
             "Transfer plus retention. Does NOT include restore/export compute.")
    c.font = Font(bold=True, size=12)
    c.fill = PatternFill("solid", fgColor=C_WARN)
    ws.cell(row=30, column=1).font = Font(bold=True, size=12)

    calc(32, "Transfer as % of total", "=IFERROR($B$26/$B$30,0)",
         "Usually a rounding error next to storage.", "0.0%")
    calc(33, "Cost to read it all back once",
         f'=$B$20*IFERROR(INDEX(Prices!$G$5:$G${price_last},MATCH($B$8&" "&$B$9,{key_rng},0)),0)'
         f'+$B$21/10000*IFERROR(INDEX(Prices!$F$5:$F${price_last},MATCH($B$8&" "&$B$9,{key_rng},0)),0)',
         "The Archive trap: cheap to keep, not free to retrieve.")
    ws.cell(row=33, column=2).fill = PatternFill("solid", fgColor=C_WARN)

    c = ws.cell(row=35, column=1, value=(
        "Restore/export compute is NOT included here; it is one-time and small. "
        "See Get-LtrExportCostEstimate.ps1 for that half of the model."))
    c.font = F_NOTE
    ws.merge_cells(start_row=35, start_column=1, end_row=35, end_column=3)

    label(ws, 37, "Banding check")
    c = ws.cell(row=37, column=2, value=(
        '=IF(AND($B$8="Hot",$B$20>51200),'
        '"Hot is volume-banded above 50 TB and this scenario exceeds it. '
        'The figures above use the first-band rate, so they are about 4% conservative.",'
        '"OK - no volume banding applies at this tier and volume.")'))
    c.font = F_NOTE
    c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=37, start_column=2, end_row=38, end_column=3)


def sheet_matrix(wb: Workbook) -> None:
    ws = wb.create_sheet("Cost matrix")
    title_row(ws, "Cost by number of backups and database size", 9)
    widths(ws, {"A": 24})
    for i in range(2, 11):
        ws.column_dimensions[get_column_letter(i)].width = 13

    sizes = [5, 10, 25, 50, 100, 250, 500, 1000]
    counts = [10, 25, 50, 100, 200, 400, 800]

    c = ws.cell(row=2, column=1, value=(
        "Uses the compression ratio, retention, tier and destination from 'Parameters'. "
        "Rows are backup counts; columns are average database size in GB."))
    c.font = F_NOTE
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=9)

    def block(top: int, heading: str, formula: str, tint: str) -> int:
        c = ws.cell(row=top, column=1, value=heading)
        c.font = Font(bold=True, size=11, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=tint)
        ws.merge_cells(start_row=top, start_column=1, end_row=top, end_column=1 + len(sizes))

        header_cells(ws, top + 1, ["Backups \\ Size (GB)"] + [str(s) for s in sizes])
        for ri, n in enumerate(counts):
            r = top + 2 + ri
            hc = ws.cell(row=r, column=1, value=n)
            hc.font = F_BOLD
            hc.number_format = NUM
            hc.fill = PatternFill("solid", fgColor=C_BAND)
            hc.border = BOX
            for ci, s in enumerate(sizes):
                cell = ws.cell(row=r, column=2 + ci, value=formula.format(n=n, s=s))
                cell.number_format = MONEY
                cell.border = BOX
        return top + 2 + len(counts) + 1

    art = "({n}*{s}/Parameters!$B$6)"
    transfer = (f"{art}*Parameters!$B$16"
                f"+ROUNDUP({art}*1024/Parameters!$B$11,0)/10000*Parameters!$B$15")
    storage = f"{art}*Parameters!$B$14*Parameters!$B$7"

    nxt = block(4, "1. TRANSFER COST (one time)  -  bandwidth plus write operations",
                f"={transfer}", C_SUB)
    nxt = block(nxt + 1, "2. STORAGE COST over the full retention period",
                f"={storage}", C_SUB)
    nxt = block(nxt + 1, "3. TOTAL  -  transfer plus storage",
                f"={transfer}+{storage}", "C00000")

    c = ws.cell(row=nxt + 1, column=1, value=(
        "If block 1 is all zeros, that is correct: same-region transfer is free, including "
        "into a storage account in a different subscription."))
    c.font = F_NOTE
    ws.merge_cells(start_row=nxt + 1, start_column=1, end_row=nxt + 1, end_column=9)
    c = ws.cell(row=nxt + 2, column=1, value=(
        "Every cell uses the first-band storage rate. Only the Hot tier is volume-banded, so "
        "if the tier on 'Parameters' is Hot, cells whose artifact volume exceeds 50 TB "
        "(count x size / compression > 51,200 GB) overstate the cost by roughly 4 percent. "
        "Cool, Cold and Archive are flat at any volume."))
    c.font = F_NOTE
    ws.merge_cells(start_row=nxt + 2, start_column=1, end_row=nxt + 3, end_column=9)
    ws.freeze_panes = "B3"


def sheet_tiers(wb: Workbook, snap: dict, price_last: int) -> None:
    ws = wb.create_sheet("Tier comparison")
    title_row(ws, "What each storage tier costs for the current scenario", 7)
    widths(ws, {"A": 22, "B": 18, "C": 18, "D": 22, "E": 20, "F": 18, "G": 22})

    c = ws.cell(row=2, column=1, value=(
        "Scenario comes from 'Parameters'. 'Read back once' is what it costs to retrieve every "
        "artifact a single time: the column people forget until an auditor asks."))
    c.font = F_NOTE
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=7)

    header_cells(ws, 4, [
        "Tier + redundancy", "Stored $/GB/mo", "Storage / month",
        "Storage over retention", "Transfer (one time)", "TOTAL", "Read back once",
    ])

    r = 5
    for row in snap["storage"]:
        pr = f'MATCH("{row["key"]}",Prices!$A$5:$A${price_last},0)'
        ws.cell(row=r, column=1, value=row["key"]).font = F_BOLD
        ws.cell(row=r, column=2,
                value=f"=INDEX(Prices!$D$5:$D${price_last},{pr})").number_format = MONEY6
        ws.cell(row=r, column=3, value=f"=Parameters!$B$20*$B{r}").number_format = MONEY
        ws.cell(row=r, column=4, value=f"=$C{r}*Parameters!$B$7").number_format = MONEY
        ws.cell(row=r, column=5,
                value=f"=Parameters!$B$20*Parameters!$B$16"
                      f"+Parameters!$B$21/10000*INDEX(Prices!$E$5:$E${price_last},{pr})"
                ).number_format = MONEY
        ws.cell(row=r, column=6, value=f"=$D{r}+$E{r}").number_format = MONEY
        ws.cell(row=r, column=6).font = F_BOLD
        ws.cell(row=r, column=7,
                value=f"=Parameters!$B$20*INDEX(Prices!$G$5:$G${price_last},{pr})"
                      f"+Parameters!$B$21/10000*INDEX(Prices!$F$5:$F${price_last},{pr})"
                ).number_format = MONEY
        for col in range(1, 8):
            ws.cell(row=r, column=col).border = BOX
            if row["tier"] == "Archive":
                ws.cell(row=r, column=col).fill = PatternFill("solid", fgColor=C_CALC)
        r += 1

    c = ws.cell(row=r + 1, column=1, value=(
        "Archive rows are highlighted: they are almost always the right answer for compliance "
        "copies that must exist but will probably never be read. Two caveats. Rehydration takes "
        "up to 15 hours at standard priority, and there is a 180-day minimum retention charge, so "
        "deleting early still bills you for 180 days."))
    c.font = F_NOTE
    c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=r + 1, start_column=1, end_row=r + 3, end_column=7)
    ws.freeze_panes = "A5"


def sheet_sensitivity(wb: Workbook) -> None:
    ws = wb.create_sheet("Compression sensitivity")
    title_row(ws, "How much the answer moves with the compression ratio", 5)
    widths(ws, {"A": 16, "B": 16, "C": 24, "D": 18, "E": 56})

    c = ws.cell(row=2, column=1, value=(
        "Compression is the least certain input and it scales the largest term. Everything else "
        "comes from 'Parameters'. Budget with the worst ratio you actually measure, not the "
        "average you hope for."))
    c.font = F_NOTE
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=5)

    header_cells(ws, 4, ["Compression", "Artifact GB", "Storage over retention",
                         "TOTAL", "What this looks like in practice"])

    notes = [
        (1.0, "No compression at all."),
        (1.02, "Measured worst case: already-compressed or encrypted data."),
        (1.5, "Pessimistic."),
        (2.0, "Conservative planning number."),
        (3.0, "Typical native .bak with COMPRESSION."),
        (4.0, "Default assumption in the toolkit. Unverified."),
        (6.0, "Optimistic; text-heavy schemas."),
        (10.0, "Very repetitive data."),
        (33.0, "Measured best case: highly repetitive test data. Do not plan on this."),
    ]
    first = 5
    r = first
    row_of = {}
    for ratio, note in notes:
        row_of[ratio] = r
        ws.cell(row=r, column=1, value=ratio).number_format = NUM2
        ws.cell(row=r, column=2, value=f"=Parameters!$B$19/$A{r}").number_format = NUM
        ws.cell(row=r, column=3,
                value=f"=$B{r}*Parameters!$B$14*Parameters!$B$7").number_format = MONEY
        ws.cell(row=r, column=4,
                value=f"=$C{r}+$B{r}*Parameters!$B$16"
                      f"+ROUNDUP($B{r}*1024/Parameters!$B$11,0)/10000*Parameters!$B$15"
                ).number_format = MONEY
        ws.cell(row=r, column=5, value=note).font = F_NOTE
        for col in range(1, 6):
            ws.cell(row=r, column=col).border = BOX
        fill = None
        if ratio == 4.0:
            fill = C_INPUT
        elif ratio == 1.02:
            fill = C_WARN
        if fill:
            for col in range(1, 5):
                ws.cell(row=r, column=col).fill = PatternFill("solid", fgColor=fill)
        r += 1

    ws.cell(row=r + 1, column=1, value="Worst case vs default assumption:").font = F_BOLD
    ws.merge_cells(start_row=r + 1, start_column=1, end_row=r + 1, end_column=3)
    c = ws.cell(row=r + 1, column=4,
                value=f"=IFERROR($D{row_of[1.02]}/$D{row_of[4.0]},0)")
    c.number_format = '0.0"x"'
    c.font = F_BOLD
    c.fill = PatternFill("solid", fgColor=C_WARN)

    c = ws.cell(row=r + 3, column=1, value=(
        "Yellow is the toolkit default. Orange is the measured worst case. The gap between them "
        "is the single largest source of error in this model."))
    c.font = F_NOTE
    ws.merge_cells(start_row=r + 3, start_column=1, end_row=r + 3, end_column=5)


def sheet_private_endpoint(wb: Workbook, pe_first: int) -> None:
    """
    Strictly additive. Nothing on this sheet feeds back into 'Parameters', the
    'Cost matrix' or 'Tier comparison', so the baseline model and its published
    verification figures are unaffected by anything here.
    """
    ws = wb.create_sheet("Private endpoint variant")
    title_row(ws, "Variant: reaching the storage account over a private endpoint", 6)
    widths(ws, {"A": 46, "B": 16, "C": 66, "D": 16, "E": 16, "F": 16})

    R_EP, R_ING, R_EGR, R_ZONE, R_QRY = (pe_first, pe_first + 1, pe_first + 2,
                                         pe_first + 3, pe_first + 4)

    c = ws.cell(row=2, column=1, value=(
        "A private endpoint is not a one-off charge. It bills by the hour for as long as it "
        "exists, which changes the shape of the answer completely: for a compliance archive "
        "the endpoint can easily cost more than the data it protects. This sheet is additive; "
        "it does not alter the baseline model on the other sheets."))
    c.font = F_NOTE
    c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=2, start_column=1, end_row=3, end_column=6)

    def inp(row, name, value, note, fmt=None):
        label(ws, row, name, note)
        c = ws.cell(row=row, column=2, value=value)
        c.fill = PatternFill("solid", fgColor=C_INPUT)
        c.border = BOX
        c.font = F_BOLD
        if fmt:
            c.number_format = fmt
        return c

    def calc(row, name, formula, note, fmt=MONEY):
        label(ws, row, name, note)
        c = ws.cell(row=row, column=2, value=formula)
        c.fill = PatternFill("solid", fgColor=C_CALC)
        c.border = BOX
        c.number_format = fmt
        return c

    ws.cell(row=5, column=1, value="INPUTS").font = Font(bold=True, color=C_HEAD)
    inp(6, "Number of private endpoints", 1,
        "One per storage sub-resource. Blob only = 1; blob + dfs = 2.", NUM)
    inp(7, "Endpoint lifetime (months)", 84,
        "How long the endpoint EXISTS, which is not necessarily the retention period.", NUM)
    inp(8, "Hours per month", 730, "Azure's standard billing month.", NUM)
    inp(9, "Dedicated private DNS zone?", "Yes",
        "No if you already own privatelink.blob.core.windows.net; then its marginal cost is 0.")
    inp(10, "DNS queries per month (millions)", 0.1,
        "An idle archive generates very few.", NUM2)
    inp(11, "Drain traffic traverses the endpoint?", "No",
        "See the note at the bottom. Usually No, because the export is service-side.")
    inp(12, "Read-back traverses the endpoint?", "Yes",
        "If you retrieve the artifacts from inside your VNet, it does.")

    for formula, cell in (('"Yes,No"', "B9"), ('"Yes,No"', "B11"), ('"Yes,No"', "B12")):
        dv = DataValidation(type="list", formula1=formula, allow_blank=False)
        ws.add_data_validation(dv)
        dv.add(ws[cell])

    ws.cell(row=14, column=1, value="RATES (from the Prices sheet)").font = Font(bold=True, color=C_HEAD)
    calc(15, "Private endpoint $/hour", f"=Prices!$B${R_EP}", "", MONEY4)
    calc(16, "Data processed, ingress $/GB", f"=Prices!$B${R_ING}", "", MONEY4)
    calc(17, "Data processed, egress $/GB", f"=Prices!$B${R_EGR}", "", MONEY4)
    calc(18, "Private DNS zone $/month", f"=Prices!$B${R_ZONE}", "", MONEY4)
    calc(19, "Private DNS queries $/million", f"=Prices!$B${R_QRY}", "", MONEY4)

    ws.cell(row=21, column=1, value="COSTS").font = Font(bold=True, color=C_HEAD)
    calc(22, "Endpoint hours", "=$B$6*$B$7*$B$8*$B$15",
         "The standing charge. Usually the largest term on this sheet.")
    calc(23, "Private DNS zone", '=IF($B$9="Yes",$B$7*$B$18,0)', "")
    calc(24, "Private DNS queries", "=$B$7*$B$10*$B$19", "")
    calc(25, "Data processed on the drain (ingress)",
         '=IF($B$11="Yes",Parameters!$B$20*$B$16,0)',
         "Zero when the export is service-side, which is the normal case.")
    calc(26, "Data processed on one full read-back (egress)",
         '=IF($B$12="Yes",Parameters!$B$20*$B$17,0)', "")

    c = calc(27, "TOTAL private endpoint add-on", "=SUM($B$22:$B$26)", "")
    c.font = Font(bold=True, size=12)
    c.fill = PatternFill("solid", fgColor=C_WARN)
    ws.cell(row=27, column=1).font = Font(bold=True, size=12)

    ws.cell(row=29, column=1, value="COMPARED WITH THE BASELINE").font = Font(bold=True, color=C_HEAD)
    calc(30, "Storage-side total (from Parameters)", "=Parameters!$B$30", "")
    calc(31, "Private endpoint add-on", "=$B$27", "")
    c = calc(32, "COMBINED", "=$B$30+$B$31", "")
    c.font = Font(bold=True, size=12)
    calc(33, "Add-on as a multiple of the storage-side cost",
         "=IFERROR($B$31/$B$30,0)",
         "Above 1 means the plumbing costs more than the data.", '0.0"x"')
    ws.cell(row=33, column=2).fill = PatternFill("solid", fgColor=C_WARN)

    ws.cell(row=35, column=1, value="SCENARIOS").font = Font(bold=True, color=C_HEAD)
    header_cells(ws, 36, ["Scenario", "Endpoint months", "Endpoint + DNS",
                          "Data processed", "Add-on total", "Combined"])
    scenarios = [
        ("No private endpoint at all", 0),
        ("Endpoint only during the drain (1 month)", 1),
        ("Endpoint kept for 3 months", 3),
        ("Endpoint kept for the full retention", None),
    ]
    r = 37
    for name, months in scenarios:
        m = "$B$7" if months is None else str(months)
        ws.cell(row=r, column=1, value=name).font = F_BOLD
        ws.cell(row=r, column=2, value=f"={m}" if months is None else months).number_format = NUM
        ws.cell(row=r, column=3,
                value=f'=$B$6*{m}*$B$8*$B$15+IF($B$9="Yes",{m}*$B$18,0)+{m}*$B$10*$B$19'
                ).number_format = MONEY
        ws.cell(row=r, column=4, value=f"=IF({m}=0,0,$B$25+$B$26)").number_format = MONEY
        ws.cell(row=r, column=5, value=f"=$C{r}+$D{r}").number_format = MONEY
        ws.cell(row=r, column=5).font = F_BOLD
        ws.cell(row=r, column=6, value=f"=Parameters!$B$30+$E{r}").number_format = MONEY
        for col in range(1, 7):
            ws.cell(row=r, column=col).border = BOX
        if months == 1:
            for col in range(1, 7):
                ws.cell(row=r, column=col).fill = PatternFill("solid", fgColor=C_CALC)
        r += 1

    ws.cell(row=r + 1, column=1,
            value="ADD-ON BY ENDPOINT LIFETIME AND COUNT").font = Font(bold=True, color=C_HEAD)
    counts = [1, 2, 4, 8]
    header_cells(ws, r + 2, ["Lifetime (months) \\ endpoints"] + [str(n) for n in counts])
    lifetimes = [0, 1, 3, 6, 12, 24, 60, 84]
    mr = r + 3
    for i, months in enumerate(lifetimes):
        row = mr + i
        hc = ws.cell(row=row, column=1, value=months)
        hc.font = F_BOLD
        hc.fill = PatternFill("solid", fgColor=C_BAND)
        hc.border = BOX
        for j, n in enumerate(counts):
            cell = ws.cell(row=row, column=2 + j, value=(
                f'={n}*{months}*$B$8*$B$15'
                f'+IF($B$9="Yes",{months}*$B$18,0)+{months}*$B$10*$B$19'
                f'+IF({months}=0,0,$B$25+$B$26)'))
            cell.number_format = MONEY
            cell.border = BOX

    fr = mr + len(lifetimes) + 1
    notes = [
        ("Why the drain usually does NOT cross the endpoint:",
         "'az sql db export' and the Managed Instance 'BACKUP TO URL' statement are executed by "
         "the SQL service itself, not by a machine in your VNet, so the write does not traverse "
         "your private endpoint and is not charged as data processed. The toggle above exists "
         "because it does traverse the endpoint if you stage the artifacts through your own VM "
         "or self-hosted sqlpackage."),
        ("The trap this creates:",
         "If you lock the storage account to private endpoints only, that same service-side "
         "write is BLOCKED. You need the 'Allow trusted Microsoft services' network exception, "
         "or a resource-instance rule scoped to the SQL server or instance. Otherwise the drain "
         "fails and the private endpoint is not the reason you would expect."),
        ("The actionable conclusion:",
         "Do not leave the endpoint running for the retention period. Create it for the drain, "
         "delete it, and re-create it in minutes on the day someone actually needs to read the "
         "archive. A deleted endpoint costs nothing, and the blobs are unaffected."),
        ("Not modelled here:",
         "The VNet itself, any VM you stage through, and any VPN or ExpressRoute gateway you "
         "need to reach the endpoint from on-premises. A gateway starts around $0.19/hour, "
         "which dwarfs everything on this sheet. If you need one purely for this, model it "
         "separately and it will change your conclusion."),
    ]
    for i, (head, body) in enumerate(notes):
        row = fr + i * 2
        ws.cell(row=row, column=1, value=head).font = Font(bold=True, color=C_HEAD)
        c = ws.cell(row=row, column=2, value=body)
        c.font = F_NOTE
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=row, start_column=2, end_row=row + 1, end_column=6)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh-prices", action="store_true",
                    help="re-fetch prices from the Azure retail API before building")
    ap.add_argument("--region", default="eastus", help="Azure region for pricing")
    ap.add_argument("--output", default=str(HERE / "ltr-backup-storage-costs.xlsx"))
    args = ap.parse_args()

    if args.refresh_prices or not SNAPSHOT.exists():
        snap = refresh_prices(args.region)
    else:
        snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        print(f"Using cached prices from {snap['retrieved_utc']} ({snap['region']})")

    wb = Workbook()
    wb.remove(wb.active)

    sheet_readme(wb, snap)
    price_last, bw_first, pe_first = sheet_prices(wb, snap)
    sheet_parameters(wb, snap, price_last, bw_first)   # inserted at index 1
    sheet_matrix(wb)
    sheet_tiers(wb, snap, price_last)
    sheet_sensitivity(wb)
    sheet_private_endpoint(wb, pe_first)

    wb.active = 0
    out = pathlib.Path(args.output)
    wb.save(out)
    print(f"Wrote {out}")
    print(f"  sheets: {', '.join(wb.sheetnames)}")


if __name__ == "__main__":
    main()
