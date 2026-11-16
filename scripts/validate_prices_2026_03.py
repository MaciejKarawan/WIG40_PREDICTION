#!/usr/scripts/env python3
"""
Faza 2 — walidacja rozbieżności cen stooq (adjusted) vs PDF (raw) dla WIG 2026-03
na dzień rankingu 2026-02-27.

Output:
- data/processed/price_validation_2026_03.csv
- reports/phase_2_price_validation.md
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
OUT_CSV            = ROOT / "data" / "processed" / "price_validation_2026_03.csv"
REPORT_PATH        = ROOT / "reports" / "phase_2_price_validation.md"

# Progi kategoryzacji |diff_pct|
THR_OK    = 0.5
THR_MILD  = 5.0
THR_SEV   = 50.0
# Próg detekcji dyskontynuacji w 12M (|daily return|)
DISCONTINUITY_THR = 0.03

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


def find_discontinuity(series: pd.DataFrame) -> str:
    """Zwraca datę z największym |daily return| (powyżej DISCONTINUITY_THR) lub etykietę."""
    if len(series) < 5:
        return "insufficient_data"
    s = series.sort_values("date").reset_index(drop=True).copy()
    s["ret"] = s["close"].pct_change()
    s["abs_ret"] = s["ret"].abs()
    if s["abs_ret"].dropna().empty:
        return "no_data"
    idx = s["abs_ret"].idxmax()
    if pd.isna(s.loc[idx, "abs_ret"]) or s.loc[idx, "abs_ret"] < DISCONTINUITY_THR:
        return "no_discontinuity"
    return f"{s.loc[idx, 'date']} (Δ={s.loc[idx, 'ret']*100:+.1f}%)"


def main() -> None:
    log.info("Wczytuję dane...")
    df = pd.read_parquet(PARQUET_PORTFOLIOS)
    wig = df[
        (df["revision_date"].astype(str).str[:10] == REVISION_DATE)
        & (df["index_name"] == "WIG")
    ].copy()
    log.info(f"  WIG {REVISION_DATE}: {len(wig)} spółek")

    ohlcv = pd.read_parquet(PARQUET_OHLCV)
    log.info(f"  OHLCV: {len(ohlcv)} wierszy, {ohlcv['isin'].nunique()} ISINów, "
             f"{ohlcv['date'].min()} → {ohlcv['date'].max()}")

    map_df = pd.read_csv(MAP_PATH)
    map_df.columns = [c.strip() for c in map_df.columns]
    ticker_col = "stooq_ticker_final" if "stooq_ticker_final" in map_df.columns else "stooq_ticker"
    mapped_isins = set(map_df[map_df[ticker_col].notna()]["isin"].astype(str))

    # Flagi pokrycia
    ohlcv_isins = set(ohlcv["isin"].unique())
    wig["has_ticker_map"] = wig["isin"].isin(mapped_isins)
    wig["has_ohlcv"]      = wig["isin"].isin(ohlcv_isins)

    log.info(f"  has_ticker_map: {wig['has_ticker_map'].sum()}/{len(wig)}")
    log.info(f"  has_ohlcv:      {wig['has_ohlcv'].sum()}/{len(wig)}")

    # stooq_close na 2026-02-27 (exact match)
    target = pd.to_datetime(RANKING_DATE).date()
    at_target = ohlcv[ohlcv["date"] == target].groupby("isin")["close"].first().rename("stooq_close")
    wig = wig.merge(at_target, on="isin", how="left")
    n_has_target = wig["stooq_close"].notna().sum()
    log.info(f"  ISINów z close na {RANKING_DATE}: {n_has_target}")

    # diff_pct = (stooq - pdf) / pdf × 100  (zgodnie z plan.md)
    wig["price_pdf"] = wig["price"]
    wig["diff_pct"] = (wig["stooq_close"] - wig["price_pdf"]) / wig["price_pdf"] * 100.0
    wig["category"] = wig["diff_pct"].apply(categorize)

    # ff_market_cap_pdf = shares × price_pdf
    wig["ff_market_cap_pdf"] = wig["shares"] * wig["price_pdf"]
    total_mcap = wig["ff_market_cap_pdf"].sum()
    log.info(f"  Sumaryczny ff_market_cap (PDF): {total_mcap:,.0f} PLN")

    # Detekcja daty zdarzenia dla Mild+
    wig["candidate_event_date"] = ""
    nonok = wig[wig["category"].isin(["Mild", "Severe", "Split-suspect"])]
    for isin in nonok["isin"]:
        s = ohlcv[ohlcv["isin"] == isin]
        wig.loc[wig["isin"] == isin, "candidate_event_date"] = find_discontinuity(s)
    log.info(f"  Wyszukano daty zdarzeń dla {len(nonok)} spółek (Mild+)")

    # ---- Zapis CSV ----
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out_cols = [
        "isin", "ticker", "price_pdf", "stooq_close", "diff_pct",
        "category", "candidate_event_date", "ff_market_cap_pdf",
        "has_ticker_map", "has_ohlcv", "shares", "weight_pct",
    ]
    wig[out_cols].to_csv(OUT_CSV, index=False, encoding="utf-8")
    log.info(f"  Zapisano: {OUT_CSV}")

    # ---- Raport ----
    cat_order = ["OK", "Mild", "Severe", "Split-suspect", "no_data"]
    cat_stats = (
        wig.groupby("category")
        .agg(n=("isin", "size"), mcap=("ff_market_cap_pdf", "sum"))
        .reindex(cat_order, fill_value=0)
        .reset_index()
    )
    cat_stats["pct_companies"] = cat_stats["n"] / len(wig) * 100
    cat_stats["pct_mcap"]      = cat_stats["mcap"] / total_mcap * 100

    # Histogram |diff_pct|
    bins = [0, 0.1, 0.5, 1, 2, 5, 10, 25, 50, 100, np.inf]
    bin_labels = ["<0.1%", "0.1-0.5%", "0.5-1%", "1-2%", "2-5%", "5-10%", "10-25%", "25-50%", "50-100%", ">100%"]
    diff_abs = wig["diff_pct"].abs().dropna()
    hist_counts = pd.cut(diff_abs, bins=bins, labels=bin_labels, right=False).value_counts().reindex(bin_labels, fill_value=0)

    # Top 20 absolutnych
    has_diff = wig[wig["diff_pct"].notna()].copy()
    top_abs = has_diff.reindex(has_diff["diff_pct"].abs().sort_values(ascending=False).index).head(20)

    # Top 10 ważonych: weight = (|diff_pct| × ff_market_cap_pdf) / total_mcap
    has_diff["impact_score"] = has_diff["diff_pct"].abs() * has_diff["ff_market_cap_pdf"] / total_mcap
    top_w = has_diff.sort_values("impact_score", ascending=False).head(10)

    # Brakujące
    no_map     = wig[~wig["has_ticker_map"]][["isin", "ticker", "weight_pct"]].sort_values("weight_pct", ascending=False)
    no_ohlcv   = wig[wig["has_ticker_map"] & ~wig["has_ohlcv"]][["isin", "ticker", "weight_pct"]].sort_values("weight_pct", ascending=False)
    no_target  = wig[wig["has_ohlcv"] & wig["stooq_close"].isna()][["isin", "ticker", "weight_pct"]].sort_values("weight_pct", ascending=False)

    # Rekomendacja
    severe = cat_stats[cat_stats["category"].isin(["Severe", "Split-suspect"])]
    n_severe = int(severe["n"].sum())
    pct_mcap_severe = float(severe["pct_mcap"].sum())
    if n_severe < 5 and pct_mcap_severe < 2.0:
        recommendation = (
            f"**Opcja A (stooq jako-jest, bez reverse-adjustment).** "
            f"Tylko {n_severe} spółek w kategoriach Severe+Split-suspect, "
            f"łącznie {pct_mcap_severe:.2f}% ważonego mcap. "
            f"sC liczone na adjusted stooq pozostanie w granicach błędu pomiaru."
        )
    else:
        recommendation = (
            f"**Opcja B (reverse-adjustment dla flagowanych).** "
            f"{n_severe} spółek z |diff|>5%, łącznie {pct_mcap_severe:.2f}% ważonego mcap. "
            f"Pipeline replikacji wymaga korekt dla tych spółek przed obliczeniem sC."
        )

    md = []
    md.append("# Faza 2 — raport walidacji cen stooq vs PDF (WIG 2026-03)")
    md.append("")
    md.append(f"**Data rankingu:** {RANKING_DATE}")
    md.append(f"**Rewizja:** {REVISION_DATE}")
    md.append(f"**Zakres OHLCV:** {ohlcv['date'].min()} → {ohlcv['date'].max()}")
    md.append(f"**Spółek w WIG:** {len(wig)}")
    md.append(f"**Mapping ISIN→stooq:** {wig['has_ticker_map'].sum()}")
    md.append(f"**Z OHLCV:** {wig['has_ohlcv'].sum()}")
    md.append(f"**Z close na {RANKING_DATE}:** {n_has_target}")
    md.append("")
    md.append("## Histogram |diff_pct|")
    md.append("")
    md.append("| Przedział | n spółek |")
    md.append("|---|---|")
    for label, count in hist_counts.items():
        md.append(f"| {label} | {int(count)} |")
    md.append("")
    md.append("## Kategorie")
    md.append("")
    md.append("| Kategoria | n spółek | % spółek | % ff_market_cap |")
    md.append("|---|---:|---:|---:|")
    for _, row in cat_stats.iterrows():
        md.append(f"| {row['category']} | {int(row['n'])} | {row['pct_companies']:.1f}% | {row['pct_mcap']:.2f}% |")
    md.append("")
    md.append("## Top 20 spółek po |diff_pct|")
    md.append("")
    md.append("| ISIN | Ticker | price_pdf | stooq | diff_pct | kategoria | event_date |")
    md.append("|---|---|---:|---:|---:|---|---|")
    for _, row in top_abs.iterrows():
        md.append(
            f"| {row['isin']} | {row['ticker']} | {row['price_pdf']:.4f} | "
            f"{row['stooq_close']:.4f} | {row['diff_pct']:+.2f}% | "
            f"{row['category']} | {row['candidate_event_date']} |"
        )
    md.append("")
    md.append("## Top 10 spółek po impact_score (|diff_pct| × udział w mcap)")
    md.append("")
    md.append("| ISIN | Ticker | diff_pct | ff_market_cap_pdf | impact_score | event_date |")
    md.append("|---|---|---:|---:|---:|---|")
    for _, row in top_w.iterrows():
        md.append(
            f"| {row['isin']} | {row['ticker']} | {row['diff_pct']:+.2f}% | "
            f"{row['ff_market_cap_pdf']:,.0f} | {row['impact_score']:.4f} | "
            f"{row['candidate_event_date']} |"
        )
    md.append("")
    md.append("## Brakujące dane")
    md.append("")
    md.append(f"**Bez mappingu ISIN→stooq:** {len(no_map)} spółek")
    if not no_map.empty:
        md.append("")
        md.append("| ISIN | Ticker | weight_pct |")
        md.append("|---|---|---:|")
        for _, row in no_map.iterrows():
            md.append(f"| {row['isin']} | {row['ticker']} | {row['weight_pct']:.4f}% |")
    md.append("")
    md.append(f"**Z mappingiem ale bez OHLCV:** {len(no_ohlcv)} spółek")
    if not no_ohlcv.empty:
        md.append("")
        md.append("| ISIN | Ticker | weight_pct |")
        md.append("|---|---|---:|")
        for _, row in no_ohlcv.iterrows():
            md.append(f"| {row['isin']} | {row['ticker']} | {row['weight_pct']:.4f}% |")
    md.append("")
    md.append(f"**Z OHLCV ale bez close na {RANKING_DATE}:** {len(no_target)} spółek")
    if not no_target.empty:
        md.append("")
        md.append("| ISIN | Ticker | weight_pct |")
        md.append("|---|---|---:|")
        for _, row in no_target.iterrows():
            md.append(f"| {row['isin']} | {row['ticker']} | {row['weight_pct']:.4f}% |")
    md.append("")
    md.append("## Rekomendacja dla Fazy 3")
    md.append("")
    md.append(recommendation)
    md.append("")
    md.append("---")
    md.append("")
    md.append("## Notatka metodologiczna")
    md.append("")
    md.append(f"- `diff_pct = (stooq_close - price_pdf) / price_pdf × 100`")
    md.append(f"- Kategoryzacja: OK (<{THR_OK}%), Mild ({THR_OK}-{THR_MILD}%), Severe ({THR_MILD}-{THR_SEV}%), Split-suspect (≥{THR_SEV}%)")
    md.append(f"- Detekcja dyskontynuacji: max |daily return| w 12M; próg odcięcia {DISCONTINUITY_THR*100:.0f}%")
    md.append(f"- Mianownikiem diff_pct jest cena PDF (ground truth GPW Benchmark, raw).")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(md), encoding="utf-8")
    log.info(f"  Zapisano raport: {REPORT_PATH}")

    # Quick summary
    print()
    print("=" * 60)
    print("PODSUMOWANIE FAZY 2")
    print("=" * 60)
    print(cat_stats.to_string(index=False))
    print()
    print(f"Brakujące: no_map={len(no_map)}, no_ohlcv={len(no_ohlcv)}, no_target={len(no_target)}")
    print()
    print(f"Rekomendacja: {recommendation}")


if __name__ == "__main__":
    main()
