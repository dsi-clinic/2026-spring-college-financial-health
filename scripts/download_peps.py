"""
Download PEPS (Program Eligibility and Participation System) closed schools data.

Source: U.S. Department of Education / Federal Student Aid
Years: 1996-2023

Output: data/raw/peps/closedschools.xlsx (or .csv if available)
"""

import argparse
import sys
from pathlib import Path

import requests

OUT_DIR = Path("data/raw/peps")

# Known URLs to try in order (ED/FSA sometimes moves files)
# Primary URL (verified working as of April 2026): legacy ed.gov XLS — full history back to 1984
# Note: studentaid.gov/data-center/school/peps300 returned 404 as of April 2026
CANDIDATE_URLS = [
    "https://www.ed.gov/sites/ed/files/offices/OSFAP/PEPS/docs/closedschoolsearch.xls",
    "https://www2.ed.gov/offices/OSFAP/PEPS/docs/closedschoolsearch.xls",
    "https://www2.ed.gov/offices/OSFAP/PEPS/closedschool.xlsx",
    "https://www2.ed.gov/offices/OSFAP/PEPS/closedschool.xls",
]

MANUAL_INSTRUCTIONS = """
MANUAL DOWNLOAD REQUIRED — PEPS Closed Schools Data
====================================================
The automated download failed. Please follow these steps:

1. Go to: https://fsapartners.ed.gov/additional-resources/reports/weekly-closed-school-search-file
   OR try the legacy direct file:
   https://www.ed.gov/sites/ed/files/offices/OSFAP/PEPS/docs/closedschoolsearch.xls

2. Download the "Closed School Search" file (XLS format).

3. Save it to: data/raw/peps/closedschools.xlsx
   (or closedschools.csv if you download CSV)

The file contains all institutions that lost Title IV eligibility,
with columns for OPEID, school name, location, and closure date.
Years needed: 1996-2023 per variable_inventory.md.
"""


def main():
    parser = argparse.ArgumentParser(description="Download PEPS closed schools data")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be downloaded without downloading")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for ext in ("xlsx", "xls", "csv"):
        out_path = OUT_DIR / f"closedschools.{ext}"
        if out_path.exists():
            print(f"[skip] {out_path} already exists")
            return

    if args.dry_run:
        print("[dry-run] would attempt these URLs:")
        for url in CANDIDATE_URLS:
            print(f"  {url}")
        return

    print("PEPS closed schools download")
    print(f"Output: {OUT_DIR}/\n")

    for url in CANDIDATE_URLS:
        print(f"Trying: {url}")
        try:
            resp = requests.get(url, timeout=30, allow_redirects=True)
            if resp.status_code == 200 and len(resp.content) > 1000:
                ext = url.split(".")[-1].lower()
                if ext not in ("xlsx", "xls", "csv"):
                    ext = "xlsx"
                out_path = OUT_DIR / f"closedschools.{ext}"
                out_path.write_bytes(resp.content)
                print(f"[ok] Saved to {out_path} ({len(resp.content):,} bytes)")
                return
            else:
                print(f"  -> HTTP {resp.status_code}, skipping")
        except requests.RequestException as e:
            print(f"  -> Error: {e}, skipping")

    print("\n[FAIL] All download URLs failed.")
    print(MANUAL_INSTRUCTIONS)
    sys.exit(1)


if __name__ == "__main__":
    main()
