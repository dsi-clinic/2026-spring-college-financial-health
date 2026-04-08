"""
Download BEA (Bureau of Economic Analysis) county-level data.

Tables:
  CAINC1 - Annual personal income summary: personal income, population,
            per capita personal income by county

Years: 1969-2022 (BEA CAINC1 starts at 1969; variable_inventory needs 1967-2022)

Note: BEA county data starts at 1969 for most series (not 1967 as listed in
the variable inventory). Scripts downloads all available years.

API docs: https://apps.bea.gov/api/_pdf/bea_web_service_api_user_guide.pdf
API key:  https://apps.bea.gov/api/signup/ (free, instant)

Set BEA_API_KEY in .env before running.

Output: data/raw/bea/bea_cainc1_all_counties.json
        data/raw/bea/bea_cainc1_all_counties.csv
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://apps.bea.gov/api/data"
OUT_DIR = Path("data/raw/bea")

# CAINC1: Personal Income Summary
# LineCode 1 = personal income, 2 = population, 3 = per capita personal income
LINE_CODES = {
    "1": "personal_income",
    "2": "population",
    "3": "per_capita_personal_income",
}


def check_api_key() -> str:
    key = os.getenv("BEA_API_KEY", "").strip()
    if not key or key == "your_key_here":
        print("[ERROR] BEA_API_KEY not set in .env")
        print()
        print("To get a free API key:")
        print("  1. Go to https://apps.bea.gov/api/signup/")
        print("  2. Register with your email (instant approval)")
        print("  3. Add BEA_API_KEY=your_key to .env")
        sys.exit(1)
    return key


def fetch_linecode(api_key: str, line_code: str, label: str) -> list[dict]:
    """Fetch one line code for all counties, all available years."""
    params = {
        "UserID": api_key,
        "method": "GetData",
        "datasetname": "Regional",
        "TableName": "CAINC1",
        "LineCode": line_code,
        "GeoFips": "COUNTY",  # all counties
        "Year": "ALL",
        "ResultFormat": "JSON",
    }
    print(f"  Fetching {label} (LineCode {line_code}) for all counties, all years...", end="", flush=True)
    resp = requests.get(API_BASE, params=params, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    if "BEAAPI" not in data or "Results" not in data["BEAAPI"]:
        print(f"\n  [ERROR] Unexpected response: {str(data)[:200]}")
        return []

    results = data["BEAAPI"]["Results"].get("Data", [])
    for row in results:
        row["series"] = label
    print(f" {len(results):,} rows")
    return results


def main():
    parser = argparse.ArgumentParser(description="Download BEA county income and population data")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be downloaded without downloading")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    json_path = OUT_DIR / "bea_cainc1_all_counties.json"
    csv_path = OUT_DIR / "bea_cainc1_all_counties.csv"

    if json_path.exists() and csv_path.exists():
        print(f"[skip] {json_path.name} and {csv_path.name} already exist")
        return

    api_key = check_api_key()

    print("BEA CAINC1 download (county personal income and population)")
    print(f"Output: {OUT_DIR}/\n")

    if args.dry_run:
        print("[dry-run] would fetch CAINC1 line codes:")
        for lc, label in LINE_CODES.items():
            print(f"  LineCode {lc}: {label}")
        print(f"  -> {json_path.name}")
        return

    all_rows = []
    for line_code, label in LINE_CODES.items():
        rows = fetch_linecode(api_key, line_code, label)
        all_rows.extend(rows)

    json_path.write_text(json.dumps(all_rows, indent=2))
    print(f"\n[ok] {json_path.name} ({len(all_rows):,} total rows)")

    if all_rows:
        # Collect all fieldnames across all rows (some rows have extra fields like NoteRef)
        fieldnames = sorted({k for row in all_rows for k in row.keys()})
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"[ok] {csv_path.name}")

    print("\nNote: CAINC1 county data starts at 1969 (BEA historical data)")
    print("  Variable inventory lists 1967 but 1969 is the earliest available.")


if __name__ == "__main__":
    main()
