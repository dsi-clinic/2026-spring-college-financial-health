"""
Download IPEDS survey data from NCES.

Surveys downloaded:
  F   - Finance (FASB F1A for private, GASB F2 for public, F3 for-profit)
  EF  - Fall Enrollment
  E12 - 12-Month Enrollment
  S   - Human Resources / Staff
  IC  - Institutional Characteristics

Years: 2002-2023

Output: data/raw/ipeds/{survey}_{year}.csv
"""

import argparse
import io
import sys
import zipfile
from pathlib import Path

import requests
from tqdm import tqdm

BASE_URL = "https://nces.ed.gov/ipeds/datacenter/data"
OUT_DIR = Path("data/raw/ipeds")

# Each entry: (label, list_of_url_stem_templates_to_try_in_order)
# {year} = 4-digit year; {prev} = year-1 (Finance lags by one year at NCES)
# {yr2d} = last 2 digits of year (zero-padded); {next2d} = last 2 digits of year+1
# Older finance files (2002-2020) use F{yr2d}{next2d}_* format (e.g. F0203_F1A).
# Newer files (2021+) use F{year}_* format (e.g. F2021_F1A).
# First matching URL wins.
SURVEYS = {
    # NCES Finance files: older years use 2-digit year-range format (F0203_F1A);
    # newer years use 4-digit year (F2021_F1A). Try both in order.
    "finance_fasb_f1a": ["F{year}_F1A", "F{yr2d}{next2d}_F1A", "F{prev}_F1A", "F{year}_F1A_RV"],
    "finance_fasb_f3":  ["F{year}_F3",  "F{yr2d}{next2d}_F3",  "F{prev}_F3",  "F{year}_F3_RV"],
    "finance_gasb_f2":  ["F{year}_F2",  "F{yr2d}{next2d}_F2",  "F{prev}_F2",  "F{year}_F2_RV"],
    # Fall enrollment: standard pattern works
    "fall_enrollment":  ["EF{year}A",   "EF{year}A_RV"],
    # 12-month enrollment: NCES uses E12_{year} for 2012+; older = EAP{year}
    "enrollment_12mo":  ["E12_{year}",  "E12{year}",   "EAP{year}"],
    # Human Resources
    "hr_staff":         ["S{year}_IS",  "S{year}_IS_RV"],
    "hr_staff_sis":     ["S{year}_SIS", "S{year}_SIS_RV"],
    # Institutional Characteristics
    "inst_char":        ["IC{year}",    "IC{year}_RV"],
}

# Years of interest per the variable inventory
YEARS = list(range(2002, 2024))


def try_one_stem(stem: str, out_path: Path) -> bool:
    """Try downloading one stem URL. Returns True on success."""
    url = f"{BASE_URL}/{stem}.zip"
    resp = requests.get(url, timeout=60, stream=True)
    if resp.status_code == 404:
        return False
    resp.raise_for_status()

    content = b"".join(resp.iter_content(chunk_size=8192))
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv") and not n.startswith("__")]
        if not csv_names:
            return False
        main = next((n for n in csv_names if stem.lower() in n.lower()), csv_names[0])
        with zf.open(main) as src, open(out_path, "wb") as dst:
            dst.write(src.read())
    return True


def download_survey(label: str, stems: list[str], year: int, dry_run: bool) -> bool:
    """Try each stem in order until one succeeds. Returns True on success."""
    out_path = OUT_DIR / f"{label}_{year}.csv"

    if out_path.exists():
        print(f"  [skip] {out_path.name} already exists")
        return True

    yr2d = str((year - 1) % 100).zfill(2)
    next2d = str(year % 100).zfill(2)
    resolved = [s.format(year=year, prev=year - 1, yr2d=yr2d, next2d=next2d) for s in stems]

    if dry_run:
        print(f"  [dry-run] {label}_{year}: would try {resolved[0]}.zip (+ {len(resolved)-1} fallbacks)")
        return True

    for stem in resolved:
        if try_one_stem(stem, out_path):
            print(f"  [ok] {out_path.name}  (via {stem}.zip)")
            return True

    return False


def main():
    parser = argparse.ArgumentParser(description="Download IPEDS survey data")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be downloaded without downloading")
    parser.add_argument("--survey", help="Download only this survey label (e.g. finance_fasb_f1a)")
    parser.add_argument("--year", type=int, help="Download only this year")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    surveys = {k: v for k, v in SURVEYS.items() if args.survey is None or k == args.survey}
    years = [args.year] if args.year else YEARS

    failed = []
    total = len(surveys) * len(years)

    print(f"IPEDS download: {len(surveys)} surveys x {len(years)} years = {total} files")
    print(f"Output: {OUT_DIR}/\n")

    for label, stems in surveys.items():
        print(f"Survey: {label}")
        for year in tqdm(years, desc=label, unit="yr", leave=False):
            ok = download_survey(label, stems, year, args.dry_run)
            if not ok:
                yr2d = str((year - 1) % 100).zfill(2)
                next2d = str(year % 100).zfill(2)
                failed.append((label, year, [s.format(year=year, prev=year - 1, yr2d=yr2d, next2d=next2d) for s in stems]))

    print(f"\nDone. {total - len(failed)}/{total} files downloaded.")

    if failed:
        print(f"\n{len(failed)} files not found — all fallback patterns tried:")
        for label, year, tried in failed[:20]:
            print(f"  {label} {year}: tried {', '.join(tried)}")
        print("\nManual fallback: https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx")
        print("  1. Select 'Survey Year' and the survey component you need")
        print("  2. Download the zip file and place extracted CSV in data/raw/ipeds/")

    if failed and not args.dry_run:
        sys.exit(1)


if __name__ == "__main__":
    main()
