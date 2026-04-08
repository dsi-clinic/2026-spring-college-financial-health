"""
Download BLS LAUS (Local Area Unemployment Statistics) county unemployment data.

Series: unemployment rate for all US counties
Series ID format: LAUCN{state_fips2}{county_fips3}0000000003
  (the trailing 3 = unemployment rate; 4 = unemployed persons; 5 = employed; 6 = labor force)

Years: 1990-2022 (per variable_inventory.md)

API docs: https://www.bls.gov/developers/api_features.htm
API key:  https://www.bls.gov/developers/ (optional, v2 gives higher limits)
  V1 (no key): 25 series per query, 500 queries/day
  V2 (with key): 50 series per query, 500 queries/day

Set BLS_API_KEY in .env for v2 access (recommended for ~3,200 counties).

Output: data/raw/bls/bls_laus_county_unemployment.json
        data/raw/bls/bls_laus_county_unemployment.csv
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

OUT_DIR = Path("data/raw/bls")

START_YEAR = 1990
END_YEAR = 2022

# BLS LAUS series suffix for unemployment rate
# Series ID format: LAUCN{state2}{county3}000000000{measure}
# measure: 3=unemployment rate, 4=unemployed, 5=employed, 6=labor force
SERIES_MEASURE = "3"

# County FIPS data: (state_fips, county_fips, state_abbr, county_name)
# This is a subset for testing. The full list is fetched from Census at runtime.
CENSUS_COUNTY_URL = "https://api.census.gov/data/2020/dec/pl?get=NAME&for=county:*&in=state:*"


def get_county_fips() -> list[tuple[str, str]]:
    """Return list of (state_fips2, county_fips3) for all US counties."""
    fips_path = OUT_DIR / "_county_fips.json"
    if fips_path.exists():
        return json.loads(fips_path.read_text())

    print("Fetching county FIPS codes from Census... ", end="", flush=True)
    resp = requests.get(CENSUS_COUNTY_URL, timeout=30)
    resp.raise_for_status()
    raw = resp.json()
    # raw[0] = headers: ['NAME', 'state', 'county']
    counties = [(row[1].zfill(2), row[2].zfill(3)) for row in raw[1:]]
    fips_path.write_text(json.dumps(counties))
    print(f"{len(counties)} counties")
    return counties


def build_series_ids(counties: list[tuple[str, str]]) -> list[str]:
    # Correct format: LAUCN + 2-digit state + 3-digit county + 000000000 (9 zeros) + 1-digit measure
    # Example: LAUCN010010000000003 (Alabama, Autauga County, unemployment rate)
    return [f"LAUCN{sf}{cf}000000000{SERIES_MEASURE}" for sf, cf in counties]


def fetch_batch(series_ids: list[str], start_year: int, end_year: int, api_key: str) -> list[dict]:
    """Fetch one batch of series IDs from BLS API."""
    payload = {
        "seriesid": series_ids,
        "startyear": str(start_year),
        "endyear": str(end_year),
    }
    if api_key:
        payload["registrationkey"] = api_key
        url = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    else:
        url = "https://api.bls.gov/publicAPI/v1/timeseries/data/"

    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") != "REQUEST_SUCCEEDED":
        return []

    rows = []
    for series in data.get("Results", {}).get("series", []):
        sid = series["seriesID"]
        state_fips = sid[6:8]
        county_fips = sid[8:11]
        for obs in series.get("data", []):
            rows.append({
                "series_id": sid,
                "state_fips": state_fips,
                "county_fips": county_fips,
                "year": int(obs["year"]),
                "period": obs["period"],
                "value": obs["value"],
                "footnotes": ",".join(f.get("code", "") for f in obs.get("footnotes", []) if f),
            })
    return rows


def main():
    parser = argparse.ArgumentParser(description="Download BLS LAUS county unemployment data")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be downloaded without downloading")
    parser.add_argument("--limit-counties", type=int, help="Limit to first N counties (for testing)")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    json_path = OUT_DIR / "bls_laus_county_unemployment.json"
    csv_path = OUT_DIR / "bls_laus_county_unemployment.csv"

    if json_path.exists() and csv_path.exists():
        print(f"[skip] {json_path.name} and {csv_path.name} already exist")
        return

    api_key = os.getenv("BLS_API_KEY", "").strip()
    if not api_key or api_key == "your_key_here":
        api_key = ""
        batch_size = 25
        print("Note: No BLS_API_KEY set — using v1 API (25 series/batch, slower).")
        print("  Sign up at https://www.bls.gov/developers/ for v2 access (50 series/batch).\n")
    else:
        batch_size = 50

    counties = get_county_fips()
    if args.limit_counties:
        counties = counties[: args.limit_counties]
        print(f"[test mode] Limited to {len(counties)} counties")

    all_series = build_series_ids(counties)

    print(f"BLS LAUS download: {len(all_series)} county series, {START_YEAR}-{END_YEAR}")
    print(f"Batches: {len(all_series) // batch_size + 1} x {batch_size} series each")
    print(f"Output: {OUT_DIR}/\n")

    # BLS API returns max 20 years per request; chunk years into 20-year windows
    year_ranges = []
    y = START_YEAR
    while y <= END_YEAR:
        year_ranges.append((y, min(y + 19, END_YEAR)))
        y += 20

    if args.dry_run:
        print(f"[dry-run] would fetch {len(all_series)} series in {len(all_series) // batch_size + 1} batches")
        print(f"  Year ranges: {year_ranges}")
        return

    all_rows = []
    batches = [all_series[i : i + batch_size] for i in range(0, len(all_series), batch_size)]

    for start_yr, end_yr in year_ranges:
        print(f"Years {start_yr}-{end_yr}:")
        for batch in tqdm(batches, desc=f"{start_yr}-{end_yr}", unit="batch"):
            rows = fetch_batch(batch, start_yr, end_yr, api_key)
            all_rows.extend(rows)
            time.sleep(0.5)  # respect BLS rate limits

    json_path.write_text(json.dumps(all_rows, indent=2))
    print(f"\n[ok] {json_path.name} ({len(all_rows):,} observation rows)")

    if all_rows:
        fieldnames = list(all_rows[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"[ok] {csv_path.name}")

    print("\nNote: BLS LAUS annual data uses period 'M13' (annual average).")
    print("  Filter on period == 'M13' when merging with IPEDS data.")


if __name__ == "__main__":
    main()
