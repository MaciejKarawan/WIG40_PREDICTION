#!/usr/scripts/env python3
"""
Ingest WIG20 z combined PDF (`Portfele_WIG20_mWIG40_sWIG80_WIG30_*.pdf`) do parquet.

Tło: dla rewizji 2025-12-19 i 2026-03-20 GPW Benchmark nie publikuje osobnych PDFów
WIG20 — tylko combined. Standardowy scraper łapie tylko 'Portfel indeksu <X>',
a combined ma 'Portfel indeksów <X> i <X>TR' — stąd dedykowany ingest dla page 0.

Uruchomienie:
    .venv/Scripts/python.exe scripts/ingest_wig20_combined.py
"""

from __future__ import annotations

import sys
import logging
from pathlib import Path

import pandas as pd
import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.gpw_benchmark_scraper import (
    PortfolioRow,
    ReserveRow,
    RE_MAIN_ROW,
    RE_MAIN_ROW_LAYOUT,
    RE_RESERVE_ROW,
    _parse_pl_float,
    _parse_int_spaces,
    _compute_flags,
    _extract_ranking_date,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

PARQUET_PORTFOLIOS = ROOT / "output" / "wig_history" / "index_portfolios.parquet"
PARQUET_RESERVES   = ROOT / "output" / "wig_history" / "reserve_lists.parquet"

# Źródła: (PDF, page index dla WIG20, revision_date)
SOURCES = [
    {
        "pdf": ROOT / "data" / "Portfele_WIG20_mWIG40_sWIG80_WIG30_2025_12_04.pdf",
        "page": 0,
        "revision_date": "2025-12-19",
    },
    {
        "pdf": ROOT / "data" / "Portfele_WIG20_mWIG40_sWIG80_WIG30_2026_03_05.pdf",
        "page": 0,
        "revision_date": "2026-03-20",
    },
]


def parse_wig20_from_page(pdf_path: Path, page_idx: int, revision_date: str) -> tuple[list[PortfolioRow], list[ReserveRow], str]:
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_idx]
        text_default = page.extract_text() or ""
        text_layout  = page.extract_text(layout=True) or ""

    ranking_date = _extract_ranking_date(text_default)
    log.info(f"  Ranking date z nagłówka: {ranking_date}")

    portfolio: list[PortfolioRow] = []
    seen_lp = set()

    for m in RE_MAIN_ROW.finditer(text_default):
        lp, isin, ticker, price_s, shares_s, weight_s = m.groups()
        lp = int(lp)
        if lp in seen_lp:
            continue
        seen_lp.add(lp)
        price = _parse_pl_float(price_s)
        shares = _parse_int_spaces(shares_s)
        weight = _parse_pl_float(weight_s)
        portfolio.append(PortfolioRow(
            revision_date=revision_date,
            index_name="WIG20",
            ranking_date=ranking_date,
            lp=lp,
            isin=isin,
            ticker=ticker,
            price=price,
            shares=shares,
            weight_pct=weight,
            flags=_compute_flags(isin, shares, weight),
        ))

    # Fallback layout — gdyby default zgubił komaśniki
    if len(portfolio) < 20:
        log.warning(f"  Default regex znalazł tylko {len(portfolio)} wierszy, próbuję layout...")
        for line in text_layout.split("\n"):
            m = RE_MAIN_ROW_LAYOUT.match(line)
            if not m:
                continue
            lp, isin, ticker, price_s, shares_s, weight_s = m.groups()
            lp = int(lp)
            if lp in seen_lp:
                continue
            seen_lp.add(lp)
            price = _parse_pl_float(price_s.strip().replace(" ", ""))
            shares = _parse_int_spaces(shares_s)
            weight = _parse_pl_float(weight_s)
            portfolio.append(PortfolioRow(
                revision_date=revision_date,
                index_name="WIG20",
                ranking_date=ranking_date,
                lp=lp,
                isin=isin,
                ticker=ticker,
                price=price,
                shares=shares,
                weight_pct=weight,
                flags=_compute_flags(isin, shares, weight),
            ))

    portfolio.sort(key=lambda r: r.lp)

    # Lista rezerwowa
    reserves: list[ReserveRow] = []
    seen_r = set()
    for m in RE_RESERVE_ROW.finditer(text_default):
        lp_s, isin, ticker, shares_s = m.groups()
        if isin in seen_r:
            continue
        # Pomijamy wiersze które wpadły już do portfela głównego
        if isin in {p.isin for p in portfolio}:
            continue
        seen_r.add(isin)
        reserves.append(ReserveRow(
            revision_date=revision_date,
            index_name="WIG20",
            lp=len(reserves) + 1,
            isin=isin,
            ticker=ticker,
            shares=_parse_int_spaces(shares_s),
        ))

    return portfolio, reserves, ranking_date


def append_to_parquet(new_portfolio: list[PortfolioRow], new_reserves: list[ReserveRow]) -> None:
    existing = pd.read_parquet(PARQUET_PORTFOLIOS)
    new_df = pd.DataFrame([vars(r) for r in new_portfolio])
    new_df["revision_date"] = pd.to_datetime(new_df["revision_date"])
    new_df["ranking_date"]  = pd.to_datetime(new_df["ranking_date"], errors="coerce")

    new_rev_dates = new_df["revision_date"].unique()
    mask_drop = (
        (existing["index_name"] == "WIG20")
        & (existing["revision_date"].isin(new_rev_dates))
    )
    if mask_drop.any():
        log.info(f"  Usuwam {mask_drop.sum()} istniejących wierszy WIG20 dla {list(map(str, new_rev_dates))}")
        existing = existing[~mask_drop]

    combined = pd.concat([existing, new_df], ignore_index=True)
    combined = combined.sort_values(["revision_date", "index_name", "lp"]).reset_index(drop=True)
    combined.to_parquet(PARQUET_PORTFOLIOS, index=False)
    log.info(f"  Zapisano: {PARQUET_PORTFOLIOS} ({len(combined)} wierszy)")

    if not new_reserves:
        return
    existing_r = pd.read_parquet(PARQUET_RESERVES) if PARQUET_RESERVES.exists() else pd.DataFrame()
    new_rdf = pd.DataFrame([vars(r) for r in new_reserves])
    new_rdf["revision_date"] = pd.to_datetime(new_rdf["revision_date"])

    if not existing_r.empty:
        mask_drop_r = (
            (existing_r["index_name"] == "WIG20")
            & (existing_r["revision_date"].isin(new_rdf["revision_date"].unique()))
        )
        if mask_drop_r.any():
            log.info(f"  Usuwam {mask_drop_r.sum()} istniejących wierszy reserve WIG20")
            existing_r = existing_r[~mask_drop_r]

    combined_r = pd.concat([existing_r, new_rdf], ignore_index=True)
    combined_r = combined_r.sort_values(["revision_date", "index_name", "lp"]).reset_index(drop=True)
    combined_r.to_parquet(PARQUET_RESERVES, index=False)
    log.info(f"  Zapisano reserves: {PARQUET_RESERVES} ({len(combined_r)} wierszy)")


def main():
    all_p, all_r = [], []
    for src in SOURCES:
        if not src["pdf"].exists():
            log.error(f"  Brak PDF: {src['pdf']}")
            sys.exit(1)
        log.info(f"Parsuję {src['pdf'].name} page {src['page']} → WIG20 {src['revision_date']}")
        p, r, rd = parse_wig20_from_page(src["pdf"], src["page"], src["revision_date"])
        log.info(f"  Portfel: {len(p)} wierszy, lista rezerwowa: {len(r)}")
        if len(p) != 20:
            log.warning(f"  OCZEKIWANO 20 wierszy WIG20, znaleziono {len(p)}")
        all_p.extend(p)
        all_r.extend(r)

    if not all_p:
        log.error("Brak danych — nic nie appenduję.")
        sys.exit(1)

    append_to_parquet(all_p, all_r)
    log.info("Gotowe.")


if __name__ == "__main__":
    main()
