"""
Download College Scorecard data via the public REST API.

Fields collected per institution:
  - id, school.name, school.state, school.city
  - school.opeid, school.opeid6
  - school.ownership (sector: public/private nonprofit/for-profit)
  - school.predominant_degree
  - school.hcm2 (Heightened Cash Monitoring Level 2 flag)
  - school.under_investigation
  - school.operating (whether currently operating)
  - latest.student.size (enrollment proxy)

API docs: https://collegescorecard.ed.gov/data/api-documentation/
API key:  https://api.data.gov/signup/ (free)

Set SCORECARD_API_KEY in .env before running.

Output: data/raw/scorecard/scorecard_latest.json (all institutions, all available years)
        data/raw/scorecard/scorecard_latest.csv  (flat CSV version)
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

API_BASE = "https://api.data.gov/ed/collegescorecard/v1/schools"
OUT_DIR = Path("data/raw/scorecard")

FIELDS = ",".join([
    "id",
    "school.name",
    "school.state",
    "school.city",
    "school.opeid",
    "school.opeid6",
    "school.ownership",
    "school.predominant_degree",
    "school.hcm2",
    "school.under_investigation",
    "school.operating",
    "school.zip",
    "school.accreditor",
    "school.institutional_characteristics.level",
    "latest.student.size",
    "latest.student.enrollment.all",
])

PAGE_SIZE = 100


def check_api_key() -> str:
    key = os.getenv("SCORECARD_API_KEY", "").strip()
    if not key or key == "your_key_here":
        print("[ERROR] SCORECARD_API_KEY not set in .env")
        print()
        print("To get a free API key:")
        print("  1. Go to https://api.data.gov/signup/")
        print("  2. Fill out the form (instant approval)")
        print("  3. Add SCORECARD_API_KEY=your_key to .env")
        sys.exit(1)
    return key


def fetch_all_institutions(api_key: str, dry_run: bool) -> list[dict]:
    if dry_run:
        print(f"[dry-run] would GET {API_BASE} with page_size={PAGE_SIZE}, fields={FIELDS[:60]}...")
        return []

    params = {
        "api_key": api_key,
        "fields": FIELDS,
        "per_page": PAGE_SIZE,
        "page": 0,
    }

    # First request to get total
    resp = requests.get(API_BASE, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    total = data["metadata"]["total"]
    results = data["results"]
    pages = (total + PAGE_SIZE - 1) // PAGE_SIZE

    print(f"Total institutions: {total:,} across {pages} pages")

    pbar = tqdm(total=pages, desc="pages", unit="page")
    pbar.update(1)

    for page in range(1, pages):
        params["page"] = page
        resp = requests.get(API_BASE, params=params, timeout=30)
        resp.raise_for_status()
        results.extend(resp.json()["results"])
        pbar.update(1)

    pbar.close()
    return results


def main():
    parser = argparse.ArgumentParser(description="Download College Scorecard data")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be downloaded without downloading")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    json_path = OUT_DIR / "scorecard_latest.json"
    csv_path = OUT_DIR / "scorecard_latest.csv"

    if json_path.exists() and csv_path.exists():
        print(f"[skip] {json_path.name} and {csv_path.name} already exist")
        return

    api_key = check_api_key()

    print("College Scorecard download")
    print(f"Output: {OUT_DIR}/\n")

    institutions = fetch_all_institutions(api_key, args.dry_run)

    if args.dry_run:
        return

    json_path.write_text(json.dumps(institutions, indent=2))
    print(f"[ok] {json_path.name} ({len(institutions):,} institutions)")

    import csv
    if institutions:
        keys = sorted(institutions[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(institutions)
        print(f"[ok] {csv_path.name}")

    print(f"\nNote: The Scorecard API returns the latest snapshot.")
    print("For historical year-by-year data, download the full data files from:")
    print("  https://collegescorecard.ed.gov/data/")
    print("  (Click 'Download Data' -> 'All Data Files' -> zip of all years)")


if __name__ == "__main__":
    main()
