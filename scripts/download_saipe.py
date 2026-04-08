"""
Download Census SAIPE (Small Area Income and Poverty Estimates) county data.

Variables:
  SAEPOVALL_PT   - estimated number of people in poverty
  SAEPOVRTALL_PT - estimated poverty rate (all ages)
  SAEMHI_PT      - median household income estimate

Geography: all US counties
Years: 1997-2022 (per variable_inventory.md)

API docs: https://www.census.gov/programs-surveys/saipe/data/api.html
API key:  https://api.census.gov/data/key_signup.html (optional, free)
  Without a key: up to 500 queries/day (sufficient for this task).

Set CENSUS_API_KEY in .env to increase rate limits (optional).

Output: data/raw/saipe/saipe_{year}.json
        data/raw/saipe/saipe_all_years.csv  (combined flat file)
"""

import argparse
import csv
import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

API_BASE = "https://api.census.gov/data/timeseries/poverty/saipe"
OUT_DIR = Path("data/raw/saipe")

VARIABLES = "NAME,SAEPOVALL_PT,SAEPOVRTALL_PT,SAEMHI_PT,STABREV,COUNTY"
YEARS = list(range(1997, 2023))


def fetch_year(year: int, api_key: str) -> list[dict]:
    """Fetch SAIPE county data for one year. Returns list of row dicts."""
    params = {
        "get": VARIABLES,
        "for": "county:*",
        "YEAR": year,
    }
    if api_key:
        params["key"] = api_key

    resp = requests.get(API_BASE, params=params, timeout=30)
    resp.raise_for_status()
    raw = resp.json()

    headers = raw[0]
    rows = []
    for row in raw[1:]:
        d = dict(zip(headers, row))
        d["year"] = year
        rows.append(d)
    return rows


def main():
    parser = argparse.ArgumentParser(description="Download Census SAIPE county poverty data")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be downloaded without downloading")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    api_key = os.getenv("CENSUS_API_KEY", "").strip()
    if not api_key or api_key == "your_key_here":
        api_key = ""
        print("Note: No CENSUS_API_KEY set — using unauthenticated access (500 queries/day limit).")
        print("  Sign up at https://api.census.gov/data/key_signup.html for higher limits.\n")

    combined_path = OUT_DIR / "saipe_all_years.csv"
    years_to_download = [y for y in YEARS if not (OUT_DIR / f"saipe_{y}.json").exists()]

    if not years_to_download:
        print(f"[skip] All {len(YEARS)} years already downloaded")
        return

    print(f"Census SAIPE download: {len(years_to_download)} years")
    print(f"Output: {OUT_DIR}/\n")

    if args.dry_run:
        for y in years_to_download:
            print(f"  [dry-run] {y}: GET {API_BASE}?YEAR={y}&for=county:* -> saipe_{y}.json")
        return

    all_rows = []
    fieldnames = None

    # Load already-downloaded years into combined
    for year in YEARS:
        json_path = OUT_DIR / f"saipe_{year}.json"
        if json_path.exists() and year not in years_to_download:
            rows = json.loads(json_path.read_text())
            all_rows.extend(rows)
            if not fieldnames and rows:
                fieldnames = list(rows[0].keys())

    for year in tqdm(years_to_download, desc="SAIPE years", unit="yr"):
        json_path = OUT_DIR / f"saipe_{year}.json"
        try:
            rows = fetch_year(year, api_key)
            json_path.write_text(json.dumps(rows, indent=2))
            all_rows.extend(rows)
            if not fieldnames and rows:
                fieldnames = list(rows[0].keys())
            time.sleep(0.1)  # be polite to Census API
        except requests.HTTPError as e:
            print(f"\n  [warn] {year}: HTTP {e.response.status_code} — skipping")

    if all_rows and fieldnames:
        all_rows_sorted = sorted(all_rows, key=lambda r: (r.get("year", 0), r.get("state", ""), r.get("county", "")))
        with open(combined_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows_sorted)
        print(f"\n[ok] {combined_path.name} ({len(all_rows):,} county-year rows)")

    print(f"[ok] Individual year files in {OUT_DIR}/")


if __name__ == "__main__":
    main()
