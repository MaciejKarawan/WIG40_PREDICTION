#!/usr/bin/env python3
"""
Aktualizuje kolumnę `price` w index_portfolios.parquet dla WIG 2026-03-20:
zamiana ceny snapshotowej (2026-02-27) na close z 2026-02-20 (data rankingu wg metodyki GPW).

Źródło ceny (priorytet):
1. data/manual/unadjusted_2026_03/<ticker>_d.csv (14 spółek z reverse-adjustment)
2. stooq OHLCV — exact match na 2026-02-20
3. stooq OHLCV — last available ≤ 2026-02-20 (fallback dla 5 brakujących)

Backup parquet: index_portfolios.parquet.bak_pre_priceupdate
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

REVISION_DATE = "2026-03-20"
RANKING_DATE  = "2026-02-20"

PARQUET    = ROOT / "output" / "wig_history" / "index_portfolios.parquet"
OHLCV      = ROOT / "output" / "2026_03_revision" / "wig2026_03_ohlcv.parquet"
MAP_PATH   = ROOT / "output" / "maps" / "ticker_isin_stooq_map.csv"
MANUAL_DIR = ROOT / "data" / "manual" / "unadjusted_2026_03"
BACKUP     = PARQUET.with_suffix(".parquet.bak_pre_priceupdate")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def load_manual(target_date) -> dict[str, tuple[float, str]]:
    """{stooq_ticker → (close, date_used)} dla pliku manualnego."""
    out = {}
    for fp in sorted(MANUAL_DIR.glob("*_d.csv")):
        tk = fp.stem.removesuffix("_d").lower()
        df = pd.read_csv(fp)
        df.columns = [c.strip() for c in df.columns]
        df = df.rename(columns={"Data": "date", "Zamkniecie": "close"})
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df = df.dropna(subset=["close"])
        hit = df[df["date"] == target_date]
        if len(hit) > 0:
            out[tk] = (float(hit["close"].iloc[0]), str(target_date))
        else:
            last = df[df["date"] <= target_date].sort_values("date").tail(1)
            if len(last) > 0:
                out[tk] = (float(last["close"].iloc[0]), str(last["date"].iloc[0]))
    return out


def main():
    target = pd.to_datetime(RANKING_DATE).date()

    log.info(f"Backup parquet → {BACKUP.name}")
    shutil.copy2(PARQUET, BACKUP)

    df = pd.read_parquet(PARQUET)
    n_before = len(df)
    log.info(f"Parquet: {n_before} wierszy, {df['revision_date'].nunique()} rewizji")

    mask = (df["revision_date"].astype(str).str[:10] == REVISION_DATE) & (df["index_name"] == "WIG")
    n_target = mask.sum()
    log.info(f"WIG {REVISION_DATE}: {n_target} wierszy do aktualizacji")

    ohlcv = pd.read_parquet(OHLCV)
    map_df = pd.read_csv(MAP_PATH)
    map_df.columns = [c.strip() for c in map_df.columns]
    map_df["_t"] = map_df["stooq_ticker_final"].astype(str).str.lower()
    ticker_to_isin = dict(zip(map_df["_t"], map_df["isin"].astype(str)))
    isin_to_ticker = {v: k for k, v in ticker_to_isin.items()}

    manual_by_ticker = load_manual(target)
    log.info(f"Manualnych spółek (close ≤ {RANKING_DATE}): {len(manual_by_ticker)}")

    at_target = ohlcv[ohlcv["date"] == target].groupby("isin")["close"].first().to_dict()
    last_le = (
        ohlcv[ohlcv["date"] <= target]
        .sort_values("date")
        .groupby("isin")
        .agg(close=("close", "last"), date=("date", "last"))
        .to_dict("index")
    )

    new_prices = {}
    sources = {"manual_exact": 0, "manual_last": 0, "stooq_exact": 0, "stooq_last": 0, "no_data": 0}

    for isin in df.loc[mask, "isin"]:
        tk = isin_to_ticker.get(isin)
        if tk and tk in manual_by_ticker:
            c, d = manual_by_ticker[tk]
            new_prices[isin] = c
            sources["manual_exact" if d == str(target) else "manual_last"] += 1
        elif isin in at_target:
            new_prices[isin] = at_target[isin]
            sources["stooq_exact"] += 1
        elif isin in last_le:
            new_prices[isin] = float(last_le[isin]["close"])
            sources["stooq_last"] += 1
        else:
            new_prices[isin] = np.nan
            sources["no_data"] += 1

    old_prices = df.loc[mask, ["isin", "price"]].set_index("isin")["price"].to_dict()
    df.loc[mask, "price"] = df.loc[mask, "isin"].map(new_prices)

    n_after = len(df)
    assert n_after == n_before, f"Liczba wierszy się zmieniła: {n_before} → {n_after}"

    df.to_parquet(PARQUET, index=False)
    log.info(f"Zapisano: {PARQUET}")

    print()
    print("=" * 60)
    print("ŹRÓDŁA NOWYCH CEN")
    print("=" * 60)
    for k, v in sources.items():
        print(f"  {k:14s}: {v}")
    print()

    # Sanity: pokaz diff dla manualnych spółek (3 największe)
    log.info("Sample old → new (manual spółki, top 5 |Δ|):")
    diffs = []
    for isin, old in old_prices.items():
        new = new_prices.get(isin)
        if new is None or pd.isna(new) or pd.isna(old):
            continue
        diffs.append((isin, old, new, (new - old) / old * 100))
    diffs.sort(key=lambda x: abs(x[3]), reverse=True)
    for isin, old, new, pct in diffs[:5]:
        log.info(f"  {isin}: {old:.2f} → {new:.2f} ({pct:+.2f}%)")


if __name__ == "__main__":
    main()
