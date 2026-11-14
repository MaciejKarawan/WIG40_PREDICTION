#!/usr/bin/env python3
"""Build a ticker/ISIN sector map from Bankier.pl company profile pages.

Input:
    output/wig_history/index_portfolios.parquet

Output:
    data/reference/sector_map.csv
    data/reference/sector_map_unmatched.csv

The source pages expose company name, macrosector, sector/industry and ISIN in
the "Podstawowe dane" section. The scraper keeps a small HTML cache to make
reruns deterministic and polite.
"""

from __future__ import annotations

import argparse
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORTFOLIOS = ROOT / "output" / "wig_history" / "index_portfolios.parquet"
DEFAULT_OUTPUT = ROOT / "data" / "reference" / "sector_map.csv"
DEFAULT_UNMATCHED = ROOT / "data" / "reference" / "sector_map_unmatched.csv"
DEFAULT_CACHE_DIR = ROOT / "data" / "reference" / "bankier_cache"

BANKIER_URL = "https://www.bankier.pl/gielda/notowania/akcje/{ticker}/podstawowe-dane"


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def slug_ticker(ticker: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "", ticker.strip().upper())


def load_universe(path: Path, revision_date: str | None) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if revision_date:
        df = df[df["revision_date"].astype(str).str[:10].eq(revision_date)].copy()
    out = (
        df[["isin", "ticker"]]
        .dropna()
        .drop_duplicates()
        .sort_values(["ticker", "isin"])
        .reset_index(drop=True)
    )
    return out


def fetch_page(ticker: str, cache_dir: Path, refresh: bool, sleep_s: float) -> tuple[str | None, str, str]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{slug_ticker(ticker)}.html"
    url = BANKIER_URL.format(ticker=slug_ticker(ticker))

    if cache_path.exists() and not refresh:
        return cache_path.read_text(encoding="utf-8", errors="ignore"), url, "cache"

    response = requests.get(
        url,
        timeout=20,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            )
        },
    )
    if response.status_code != 200:
        return None, url, f"http_{response.status_code}"

    # Bankier pages declare UTF-8. `apparent_encoding` may incorrectly guess a
    # legacy encoding and produce mojibake for Polish sector names.
    response.encoding = "utf-8"
    html = response.text
    cache_path.write_text(html, encoding="utf-8")
    if sleep_s > 0:
        time.sleep(sleep_s)
    return html, url, "fetched"


def parse_profile(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    fields: dict[str, str] = {}
    for item in soup.select("li.m-quotes-data-list__item"):
        name_el = item.select_one(".m-quotes-data-list__name")
        content_el = item.select_one(".m-quotes-data-list__content")
        if not name_el or not content_el:
            continue
        name = normalize_text(name_el.get_text(" "))
        value = normalize_text(content_el.get_text(" "))
        if name:
            fields[name] = value

    heading = soup.find(["h1", "h2"], string=re.compile("Informacje podstawowe", re.I))
    company_name = fields.get("Nazwa spółki", "")
    if heading:
        heading_text = normalize_text(heading.get_text(" "))
        match = re.search(r"Informacje podstawowe spółki\s+(.+)$", heading_text, flags=re.I)
        if match:
            company_name = normalize_text(match.group(1))

    def field_value(*labels_or_prefixes: str) -> str:
        lower_fields = {key.lower(): value for key, value in fields.items()}
        for wanted in labels_or_prefixes:
            wanted_lower = wanted.lower()
            if wanted_lower in lower_fields:
                return lower_fields[wanted_lower]
            for key, value in fields.items():
                if key.lower().startswith(wanted_lower):
                    return value
        return ""

    raw_sector_industry = field_value("Sektor/bran")
    sector = raw_sector_industry
    industry = ""
    if "/" in raw_sector_industry:
        sector, industry = [normalize_text(part) for part in raw_sector_industry.split("/", 1)]

    return {
        "company_name": company_name,
        "macrosector": field_value("Makrosektor"),
        "sector": sector,
        "industry": industry,
        "sector_industry": raw_sector_industry,
        "ticker_bankier": field_value("Ticker GPW"),
        "isin_bankier": field_value("ISIN"),
    }


def build_sector_map(
    universe: pd.DataFrame,
    cache_dir: Path,
    refresh: bool,
    sleep_s: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    for idx, row in enumerate(universe.itertuples(index=False), 1):
        ticker = str(row.ticker)
        html, url, fetch_status = fetch_page(ticker, cache_dir, refresh, sleep_s)
        parsed = parse_profile(html) if html else {}

        status = "matched"
        if not html:
            status = fetch_status
        elif not parsed.get("sector") and not parsed.get("macrosector"):
            status = "no_sector"
        elif parsed.get("isin_bankier") and parsed.get("isin_bankier") != row.isin:
            status = "isin_mismatch"

        rows.append(
            {
                "isin": row.isin,
                "ticker": ticker,
                "company_name": parsed.get("company_name", ""),
                "macrosector": parsed.get("macrosector", ""),
                "sector": parsed.get("sector", ""),
                "industry": parsed.get("industry", ""),
                "sector_industry": parsed.get("sector_industry", ""),
                "ticker_bankier": parsed.get("ticker_bankier", ""),
                "isin_bankier": parsed.get("isin_bankier", ""),
                "source": "Bankier.pl / Notoria",
                "source_url": url,
                "fetched_at": fetched_at,
                "match_status": status,
            }
        )

        if idx % 25 == 0:
            print(f"Processed {idx}/{len(universe)} tickers...")

    df = pd.DataFrame(rows)
    matched = df[df["match_status"].eq("matched")].copy()
    unmatched = df[~df["match_status"].eq("matched")].copy()
    return matched, unmatched


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portfolios", type=Path, default=DEFAULT_PORTFOLIOS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--unmatched", type=Path, default=DEFAULT_UNMATCHED)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument(
        "--revision",
        default=None,
        help="Optional YYYY-MM-DD revision filter. Default: all historical tickers.",
    )
    parser.add_argument("--refresh", action="store_true", help="Ignore cached HTML.")
    parser.add_argument("--sleep", type=float, default=0.15, help="Delay after each network fetch.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    universe = load_universe(args.portfolios, args.revision)
    print(f"Universe: {len(universe)} ticker/ISIN pairs")

    matched, unmatched = build_sector_map(
        universe=universe,
        cache_dir=args.cache_dir,
        refresh=args.refresh,
        sleep_s=args.sleep,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    matched.to_csv(args.output, index=False, encoding="utf-8")
    unmatched.to_csv(args.unmatched, index=False, encoding="utf-8")

    print(f"Matched: {len(matched)} -> {args.output}")
    print(f"Unmatched: {len(unmatched)} -> {args.unmatched}")
    if not unmatched.empty:
        print(unmatched[["ticker", "isin", "match_status"]].head(30).to_string(index=False))


if __name__ == "__main__":
    main()
