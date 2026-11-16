#!/usr/scripts/env python3
"""Consolidate raw sector scrape, ISIN-based aliases and manual overrides."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW = ROOT / "data" / "reference" / "sector_map_raw_bankier.csv"
DEFAULT_UNMATCHED = ROOT / "data" / "reference" / "sector_map_raw_bankier_unmatched.csv"
DEFAULT_OVERRIDES = ROOT / "data" / "reference" / "sector_map_manual_overrides.csv"
DEFAULT_OUTPUT = ROOT / "data" / "reference" / "sector_map.csv"
DEFAULT_REMAINING = ROOT / "data" / "reference" / "sector_map_unmatched_remaining.csv"


def read_csv_if_exists(path: Path) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path).fillna("")
    return pd.DataFrame()


def fill_aliases_by_isin(raw: pd.DataFrame, unmatched: pd.DataFrame) -> pd.DataFrame:
    if raw.empty or unmatched.empty:
        return pd.DataFrame(columns=raw.columns)

    raw_by_isin = (
        raw.sort_values(["isin", "ticker"])
        .drop_duplicates("isin", keep="first")
        .set_index("isin")
    )
    rows: list[dict[str, object]] = []
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    for row in unmatched.itertuples(index=False):
        if row.isin not in raw_by_isin.index:
            continue
        source_row = raw_by_isin.loc[row.isin].to_dict()
        copied = source_row.copy()
        copied["isin"] = row.isin
        copied["ticker"] = row.ticker
        copied["source"] = f"Bankier.pl / Notoria; copied_by_isin_from_{source_row['ticker']}"
        copied["source_url"] = source_row.get("source_url", "")
        copied["fetched_at"] = now
        copied["match_status"] = "copied_by_isin"
        rows.append(copied)

    return pd.DataFrame(rows, columns=raw.columns)


def consolidate(
    raw_path: Path,
    unmatched_path: Path,
    overrides_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = read_csv_if_exists(raw_path)
    unmatched = read_csv_if_exists(unmatched_path)
    overrides = read_csv_if_exists(overrides_path)

    alias_rows = fill_aliases_by_isin(raw, unmatched)
    combined = pd.concat([raw, alias_rows, overrides], ignore_index=True)

    if combined.empty:
        return combined, unmatched

    # Manual override wins, then exact scrape, then copied alias.
    priority = {"manual_override": 0, "matched": 1, "copied_by_isin": 2}
    combined["_priority"] = combined["match_status"].map(priority).fillna(9)
    combined = (
        combined.sort_values(["isin", "ticker", "_priority"])
        .drop_duplicates(["isin", "ticker"], keep="first")
        .drop(columns="_priority")
        .sort_values(["ticker", "isin"])
        .reset_index(drop=True)
    )

    covered_pairs = set(zip(combined["isin"], combined["ticker"]))
    remaining = unmatched[
        ~unmatched.apply(lambda row: (row["isin"], row["ticker"]) in covered_pairs, axis=1)
    ].copy()

    return combined, remaining


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--unmatched", type=Path, default=DEFAULT_UNMATCHED)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--remaining", type=Path, default=DEFAULT_REMAINING)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    combined, remaining = consolidate(args.raw, args.unmatched, args.overrides)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(args.output, index=False, encoding="utf-8")
    remaining.to_csv(args.remaining, index=False, encoding="utf-8")

    print(f"Sector map: {len(combined)} rows -> {args.output}")
    print(f"Remaining unmatched: {len(remaining)} rows -> {args.remaining}")
    if not remaining.empty:
        print(remaining[["ticker", "isin", "match_status"]].head(40).to_string(index=False))


if __name__ == "__main__":
    main()
