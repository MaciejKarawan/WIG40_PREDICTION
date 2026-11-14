#!/usr/bin/env python3
"""
Re-walidacja cen po dostarczeniu manualnych danych unadjusted (data/manual/unadjusted_2026_03/).

- Dla ISINów z manualnym plikiem: stooq_close ← manual close na 2026-02-27 (lub ostatni dostępny)
- Dla ISINów bez close 2026-02-27 w parquet: fallback do ostatniego dostępnego close ze stooq
- Reszta: bez zmian (stooq adjusted)
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

REVISION_DATE = "2026-03-20"
RANKING_DATE  = "2026-02-27"

PARQUET_PORTFOLIOS = ROOT / "output" / "wig_history" / "index_portfolios.parquet"
PARQUET_OHLCV      = ROOT / "output" / "2026_03_revision" / "wig2026_03_ohlcv.parquet"
MAP_PATH           = ROOT / "output" / "maps" / "ticker_isin_stooq_map.csv"
MANUAL_DIR         = ROOT / "data" / "manual" / "unadjusted_2026_03"
OUT_CSV            = ROOT / "data" / "processed" / "price_validation_2026_03_postmanual.csv"
REPORT_PATH        = ROOT / "reports" / "phase_2_price_validation_postmanual.md"

THR_OK    = 0.5
THR_MILD  = 5.0
THR_SEV   = 50.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def categorize(d: float) -> str:
    if pd.isna(d):
        return "no_data"
    a = abs(d)
    if a < THR_OK:   return "OK"
    if a < THR_MILD: return "Mild"
    if a < THR_SEV:  return "Severe"
    return "Split-suspect"


def load_manual_files() -> dict[str, pd.DataFrame]:
    """Zwraca {stooq_ticker: df[date, close]} dla wszystkich plików w MANUAL_DIR."""
    out = {}
    for fp in sorted(MANUAL_DIR.glob("*_d.csv")):
        ticker = fp.stem.removesuffix("_d").lower()
        df = pd.read_csv(fp)
        df.columns = [c.strip() for c in df.columns]
        # PL columns: Data, Otwarcie, Najwyzszy, Najnizszy, Zamkniecie, Wolumen
        df = df.rename(columns={"Data": "date", "Zamkniecie": "close"})
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        out[ticker] = df[["date", "close"]].dropna()
    return out


def main() -> None:
    log.info("Wczytuję dane...")
    df = pd.read_parquet(PARQUET_PORTFOLIOS)
    wig = df[
        (df["revision_date"].astype(str).str[:10] == REVISION_DATE)
        & (df["index_name"] == "WIG")
    ].copy()
    log.info(f"  WIG {REVISION_DATE}: {len(wig)} spółek")

    ohlcv = pd.read_parquet(PARQUET_OHLCV)
    map_df = pd.read_csv(MAP_PATH)
    map_df.columns = [c.strip() for c in map_df.columns]
    ticker_col = "stooq_ticker_final"
    # mapowanie stooq_ticker (lower) → ISIN
    map_df["_t"] = map_df[ticker_col].astype(str).str.lower()
    ticker_to_isin = dict(zip(map_df["_t"], map_df["isin"].astype(str)))

    manual = load_manual_files()
    log.info(f"  Manualnych plików: {len(manual)}")
    manual_isin_close: dict[str, tuple[float, str, str]] = {}  # isin → (close, date_used, source)
    unmatched_files = []
    for tk, mdf in manual.items():
        isin = ticker_to_isin.get(tk)
        if not isin:
            unmatched_files.append(tk)
            continue
        target = pd.to_datetime(RANKING_DATE).date()
        hit = mdf[mdf["date"] == target]
        if len(hit) > 0:
            c = float(hit["close"].iloc[0])
            manual_isin_close[isin] = (c, str(target), "manual_exact")
        else:
            last = mdf[mdf["date"] <= target].sort_values("date").tail(1)
            if len(last) > 0:
                c = float(last["close"].iloc[0])
                d = str(last["date"].iloc[0])
                manual_isin_close[isin] = (c, d, "manual_last")
    log.info(f"  Mapowanych manualnych ISIN: {len(manual_isin_close)}; unmatched files: {unmatched_files}")

    # Stooq close exact na 2026-02-27
    target = pd.to_datetime(RANKING_DATE).date()
    at_target = ohlcv[ohlcv["date"] == target].groupby("isin")["close"].first().to_dict()

    # Stooq last available close ≤ target (fallback dla no_data)
    ohlcv_le = ohlcv[ohlcv["date"] <= target].sort_values("date")
    last_by_isin = ohlcv_le.groupby("isin").agg(close=("close", "last"), date=("date", "last")).to_dict("index")

    # Rozstrzygnięcie ceny dla każdej spółki
    def resolve(isin):
        if isin in manual_isin_close:
            c, d, src = manual_isin_close[isin]
            return c, d, src
        if isin in at_target:
            return at_target[isin], str(target), "stooq_exact"
        if isin in last_by_isin:
            r = last_by_isin[isin]
            return float(r["close"]), str(r["date"]), "stooq_last"
        return np.nan, "", "no_data"

    res = wig["isin"].apply(resolve)
    wig["price_used"]  = res.apply(lambda x: x[0])
    wig["date_used"]   = res.apply(lambda x: x[1])
    wig["price_source"] = res.apply(lambda x: x[2])

    wig["price_pdf"] = wig["price"]
    wig["diff_pct"] = (wig["price_used"] - wig["price_pdf"]) / wig["price_pdf"] * 100.0
    wig["category"] = wig["diff_pct"].apply(categorize)
    wig["ff_market_cap_pdf"] = wig["shares"] * wig["price_pdf"]
    total_mcap = wig["ff_market_cap_pdf"].sum()

    cat_order = ["OK", "Mild", "Severe", "Split-suspect", "no_data"]
    cat_stats = (
        wig.groupby("category")
        .agg(n=("isin", "size"), mcap=("ff_market_cap_pdf", "sum"))
        .reindex(cat_order, fill_value=0)
        .reset_index()
    )
    cat_stats["pct_companies"] = cat_stats["n"] / len(wig) * 100
    cat_stats["pct_mcap"]      = cat_stats["mcap"] / total_mcap * 100

    # Source stats
    src_stats = wig.groupby("price_source").size().rename("n").reset_index()

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    wig[["isin","ticker","price_pdf","price_used","date_used","price_source",
         "diff_pct","category","ff_market_cap_pdf","shares","weight_pct"]].to_csv(OUT_CSV, index=False, encoding="utf-8")
    log.info(f"  Zapisano: {OUT_CSV}")

    # Top spółek po |diff| (Mild+) — pokazujemy czy manual wyczyścił rozjazdy
    has_diff = wig[wig["diff_pct"].notna()].copy()
    top_abs = has_diff.reindex(has_diff["diff_pct"].abs().sort_values(ascending=False).index).head(20)

    has_diff["impact_score"] = has_diff["diff_pct"].abs() * has_diff["ff_market_cap_pdf"] / total_mcap

    # Manual-only przegląd
    manual_view = wig[wig["price_source"].str.startswith("manual")][
        ["isin","ticker","price_pdf","price_used","date_used","price_source","diff_pct","category"]
    ].sort_values("diff_pct", key=lambda s: s.abs(), ascending=False)

    md = []
    md.append("# Faza 2 (post-manual) — walidacja cen po dostawie unadjusted")
    md.append("")
    md.append(f"**Data rankingu:** {RANKING_DATE}")
    md.append(f"**Plików manualnych:** {len(manual)} | zmapowanych do ISIN: {len(manual_isin_close)}")
    if unmatched_files:
        md.append(f"**Unmatched files:** {unmatched_files}")
    md.append("")
    md.append("## Źródło ceny użytej do walidacji")
    md.append("")
    md.append("| Source | n |")
    md.append("|---|---:|")
    for _, r in src_stats.iterrows():
        md.append(f"| {r['price_source']} | {int(r['n'])} |")
    md.append("")
    md.append("## Kategorie (po podmianie)")
    md.append("")
    md.append("| Kategoria | n spółek | % spółek | % ff_market_cap |")
    md.append("|---|---:|---:|---:|")
    for _, row in cat_stats.iterrows():
        md.append(f"| {row['category']} | {int(row['n'])} | {row['pct_companies']:.1f}% | {row['pct_mcap']:.2f}% |")
    md.append("")
    md.append("## Spółki z danymi manualnymi (audyt)")
    md.append("")
    md.append("| ISIN | Ticker | price_pdf | price_used | date_used | source | diff_pct | kategoria |")
    md.append("|---|---|---:|---:|---|---|---:|---|")
    for _, r in manual_view.iterrows():
        md.append(f"| {r['isin']} | {r['ticker']} | {r['price_pdf']:.4f} | {r['price_used']:.4f} | "
                  f"{r['date_used']} | {r['price_source']} | {r['diff_pct']:+.2f}% | {r['category']} |")
    md.append("")
    md.append("## Top 20 |diff_pct| po podmianie")
    md.append("")
    md.append("| ISIN | Ticker | price_pdf | price_used | source | diff_pct | kategoria |")
    md.append("|---|---|---:|---:|---|---:|---|")
    for _, row in top_abs.iterrows():
        md.append(f"| {row['isin']} | {row['ticker']} | {row['price_pdf']:.4f} | "
                  f"{row['price_used']:.4f} | {row['price_source']} | {row['diff_pct']:+.2f}% | {row['category']} |")
    md.append("")

    # Pozostałe nieusunięte rozbieżności (Mild+) — wymagają dosłania
    leftover = wig[wig["category"].isin(["Mild","Severe","Split-suspect"])]
    md.append(f"## Pozostałe rozbieżności Mild+ ({len(leftover)} spółek)")
    md.append("")
    if len(leftover) > 0:
        md.append("| ISIN | Ticker | source | diff_pct | kategoria | weight_pct |")
        md.append("|---|---|---|---:|---|---:|")
        for _, r in leftover.sort_values("diff_pct", key=lambda s: s.abs(), ascending=False).iterrows():
            md.append(f"| {r['isin']} | {r['ticker']} | {r['price_source']} | {r['diff_pct']:+.2f}% | "
                      f"{r['category']} | {r['weight_pct']:.4f}% |")
    md.append("")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(md), encoding="utf-8")
    log.info(f"  Zapisano raport: {REPORT_PATH}")

    print()
    print("=" * 70)
    print("POST-MANUAL VALIDATION")
    print("=" * 70)
    print(cat_stats.to_string(index=False))
    print()
    print("Source breakdown:")
    print(src_stats.to_string(index=False))
    print()
    print(f"Manual mapped: {len(manual_isin_close)} | Unmatched files: {unmatched_files}")


if __name__ == "__main__":
    main()
