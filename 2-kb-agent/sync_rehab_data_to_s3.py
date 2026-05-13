"""
Upload normalized UTF-8 rehab CSVs to S3 for the AgentCore runtime.

Prerequisites:
  - Run convert_csvs.py first (raw CSVs in ./raw_csvs/) so sku_catalog.csv,
    suppliers.csv, supplier_sku_links.csv exist in this directory.
  - AWS credentials with s3:PutObject on the target bucket/prefix.

Example:
  set REHAB_DATA_S3_BUCKET=my-rehab-data-bucket
  python sync_rehab_data_to_s3.py --bucket %REHAB_DATA_S3_BUCKET%
"""
from __future__ import annotations

import argparse
from pathlib import Path

import boto3

ROOT = Path(__file__).parent
FILES = ["sku_catalog.csv", "suppliers.csv", "supplier_sku_links.csv"]


def main() -> None:
    p = argparse.ArgumentParser(description="Upload rehab catalog CSVs to S3")
    p.add_argument("--bucket", required=True, help="S3 bucket name")
    p.add_argument(
        "--prefix",
        default="rehab-data/v1",
        help="Key prefix without leading slash (default: rehab-data/v1)",
    )
    p.add_argument("--region", default=None, help="Optional bucket region")
    args = p.parse_args()
    prefix = args.prefix.strip().strip("/")
    client_kw = {}
    if args.region:
        client_kw["region_name"] = args.region
    s3 = boto3.client("s3", **client_kw)

    for name in FILES:
        path = ROOT / name
        if not path.exists():
            raise SystemExit(f"Missing file: {path} — run convert_csvs.py first.")
        key = f"{prefix}/{name}" if prefix else name
        s3.upload_file(str(path), args.bucket, key, ExtraArgs={"ContentType": "text/csv; charset=utf-8"})
        print(f"Uploaded s3://{args.bucket}/{key}")

    print("Done. Set on the agent: REHAB_DATA_S3_BUCKET and REHAB_DATA_S3_PREFIX")


if __name__ == "__main__":
    main()
