"""
Download Financial Responsibility Composite (FRC) scores from the
Federal Student Aid / Department of Education data center.

Covers private nonprofit and for-profit institutions.
Years: 2006-2020 (only years with public data per variable_inventory.md)

Sources tried:
  - catalog.data.gov dataset for composite scores
  - studentaid.gov data center

Output: data/raw/frc/frc_{year}.xlsx
"""

import argparse
import sys
from pathlib import Path

import requests

OUT_DIR = Path("data/raw/frc")

# Known direct download URLs from catalog.data.gov and studentaid.gov
# These are the publicly released annual composite score files.
# URL format may vary; we try several patterns per year.
FRC_YEARS = list(range(2006, 2021))

# catalog.data.gov dataset ID for composite scores
# Dataset: "Composite Scores for Private Non-Profit and Proprietary Institutions"
# These direct links come from the catalog.data.gov resource listing.
CATALOG_URLS_BY_YEAR = {
    2020: "https://studentaid.gov/sites/default/files/fsawg/datacenter/library/CompScores2020.xlsx",
    2019: "https://studentaid.gov/sites/default/files/fsawg/datacenter/library/CompScores2019.xlsx",
    2018: "https://studentaid.gov/sites/default/files/fsawg/datacenter/library/CompScores2018.xlsx",
    2017: "https://studentaid.gov/sites/default/files/fsawg/datacenter/library/CompScores2017.xlsx",
    2016: "https://studentaid.gov/sites/default/files/fsawg/datacenter/library/CompScores2016.xlsx",
    2015: "https://studentaid.gov/sites/default/files/fsawg/datacenter/library/CompScores2015.xlsx",
    2014: "https://studentaid.gov/sites/default/files/fsawg/datacenter/library/CompScores2014.xlsx",
    2013: "https://studentaid.gov/sites/default/files/fsawg/datacenter/library/CompScores2013.xlsx",
    2012: "https://studentaid.gov/sites/default/files/fsawg/datacenter/library/CompScores2012.xlsx",
    2011: "https://studentaid.gov/sites/default/files/fsawg/datacenter/library/CompScores2011.xlsx",
    2010: "https://studentaid.gov/sites/default/files/fsawg/datacenter/library/CompScores2010.xlsx",
    2009: "https://studentaid.gov/sites/default/files/fsawg/datacenter/library/CompScores2009.xlsx",
    2008: "https://studentaid.gov/sites/default/files/fsawg/datacenter/library/CompScores2008.xlsx",
    2007: "https://studentaid.gov/sites/default/files/fsawg/datacenter/library/CompScores2007.xlsx",
    2006: "https://studentaid.gov/sites/default/files/fsawg/datacenter/library/CompScores2006.xlsx",
}

MANUAL_INSTRUCTIONS = """
MANUAL DOWNLOAD REQUIRED — FRC Composite Scores
================================================
Automated download failed for some years. Please follow these steps:

1. Go to: https://studentaid.gov/data-center/school/composite-scores
   OR:     https://catalog.data.gov/dataset/composite-scores-for-private-non-profit-and-proprietary-institutions

2. Download the Excel file for each year needed (2006-2020).

3. Save files to: data/raw/frc/frc_{year}.xlsx
   Example: data/raw/frc/frc_2015.xlsx

Notes:
  - Only private nonprofit and for-profit institutions have FRC scores.
  - Per the paper, only ~37% of never-closed institutions have FRC data.
  - Years 2006-2020 per variable_inventory.md.
"""


def try_download(url: str, out_path: Path) -> bool:
    """Try to download a URL. Returns True on success."""
    try:
        resp = requests.get(url, timeout=30, allow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 1000:
            out_path.write_bytes(resp.content)
            return True
        return False
    except requests.RequestException:
        return False


def main():
    parser = argparse.ArgumentParser(description="Download FRC composite scores")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be downloaded without downloading")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("FRC Composite Scores download")
    print(f"Years: {FRC_YEARS[0]}-{FRC_YEARS[-1]}")
    print(f"Output: {OUT_DIR}/\n")

    if args.dry_run:
        for year in FRC_YEARS:
            url = CATALOG_URLS_BY_YEAR.get(year, "URL unknown")
            print(f"  [dry-run] {year}: {url} -> frc_{year}.xlsx")
        return

    failed = []
    for year in FRC_YEARS:
        out_path = OUT_DIR / f"frc_{year}.xlsx"
        if out_path.exists():
            print(f"  [skip] frc_{year}.xlsx already exists")
            continue

        url = CATALOG_URLS_BY_YEAR.get(year)
        if not url:
            print(f"  [skip] No URL known for {year}")
            failed.append(year)
            continue

        print(f"  Downloading {year}... ", end="", flush=True)
        if try_download(url, out_path):
            print(f"ok ({out_path.stat().st_size:,} bytes)")
        else:
            print(f"FAILED ({url})")
            failed.append(year)

    if failed:
        print(f"\n{len(failed)} years failed: {failed}")
        print(MANUAL_INSTRUCTIONS)
        sys.exit(1)
    else:
        print(f"\nAll {len(FRC_YEARS)} FRC files downloaded successfully.")


if __name__ == "__main__":
    main()
