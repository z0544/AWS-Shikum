"""
Convert raw Hebrew CP1255 CSV files (suppliers, SKUs, links) into clean UTF-8
CSVs that the agent tool can read directly.

Usage:
    1. Put the 3 raw CSV files inside ./raw_csvs/
    2. Run: python3 convert_csvs.py
    3. Three clean files appear here: sku_catalog.csv, supplier_sku_links.csv, suppliers.csv
"""
import csv
from pathlib import Path

ROOT = Path(__file__).parent
RAW_DIR = ROOT / "raw_csvs"

# Map: substring-to-look-for-in-raw-filename -> (out_filename, normalized_headers, header_marker)
FILE_MAP = [
    (
        "פרוט_מקטים",
        "sku_catalog.csv",
        ["sku", "description", "frequency", "qty_per_period", "max_qty",
         "eligible_type", "amount_type", "base_level", "exception_level",
         "exception_pct", "amount"],
        'מק"ט',
    ),
    (
        "הסכמי_מחירים",
        "supplier_sku_links.csv",
        ["supplier_id_rehab", "supplier_id_modef", "sku",
         "is_active", "suppliers_count"],
        # KMS header may be "מספר ספק שיקום" or "מס' ספק …"
        "מספר ספק",
    ),
    (
        "ספקים_בעלי_הסכם",
        "suppliers.csv",
        ["valid_from", "valid_to", "supplier_id_rehab", "supplier_id_modef",
         "name", "city", "address", "mobile", "work_phone", "landline",
         "email", "profession", "specialization", "sub_specialization",
         "therapeutic_approach"],
        "תחילת תוקף",
    ),
]


def find_raw_file(pattern: str) -> Path | None:
    candidates = [p for p in RAW_DIR.glob("*.csv") if pattern in p.name]
    return candidates[0] if candidates else None


def convert(pattern: str, out_name: str, out_headers: list[str], header_marker: str) -> None:
    raw_path = find_raw_file(pattern)
    if raw_path is None:
        print(f"  ✗ SKIP: no file containing '{pattern}' in {RAW_DIR}")
        return

    print(f"  → reading {raw_path.name} (cp1255)")
    with open(raw_path, "r", encoding="cp1255", errors="replace") as f:
        rows = list(csv.reader(f))

    header_idx = next(
        (i for i, r in enumerate(rows) if any(header_marker in (c or "") for c in r)),
        None,
    )
    if header_idx is None:
        print(f"  ✗ ERROR: could not locate header row in {raw_path.name}")
        return

    n_cols = len(out_headers)
    data_rows: list[list[str]] = []
    for r in rows[header_idx + 1:]:
        if not r or not any((c or "").strip() for c in r):
            continue
        padded = [(c or "").strip() for c in r] + [""] * n_cols
        if not padded[0]:
            continue
        data_rows.append(padded[:n_cols])

    out_path = ROOT / out_name
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(out_headers)
        w.writerows(data_rows)
    print(f"  ✓ wrote {out_path.name} ({len(data_rows)} rows)")


def main() -> None:
    if not RAW_DIR.exists():
        print(f"ERROR: missing dir {RAW_DIR}")
        print("Create it and place the 3 raw CSV files inside, then re-run.")
        return
    print(f"Converting CSVs from {RAW_DIR}\n")
    for pattern, out_name, headers, marker in FILE_MAP:
        convert(pattern, out_name, headers, marker)
    print("\nDone.")


if __name__ == "__main__":
    main()
