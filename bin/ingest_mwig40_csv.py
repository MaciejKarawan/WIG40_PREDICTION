#!/usr/bin/env python3
"""
Ingest mWIG40 z CSV-ek (rewizje 2025-12-19 i 2026-03-20) do parquet.

Tło: dla rewizji 2025-12 i 2026-03 GPW Benchmark nie publikuje osobnych PDFów
mWIG40 — tylko combined PDF. CSV-ki zostały sparsowane ręcznie z combined PDF.
Skrypt normalizuje 2 lekko różne schematy CSV, mapuje na PortfolioRow/ReserveRow,
appenduje do output/wig_history/index_portfolios.parquet i reserve_lists.parquet.

Uruchomienie:
    .venv/Scripts/python.exe bin/ingest_mwig40_csv.py
"""

from __future__ import annotations

import sys
import logging
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin.gpw_benchmark_scraper import (
    PortfolioRow,
    ReserveRow,
    _parse_pl_float,
    _parse_int_spaces,
    _compute_flags,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

PARQUET_PORTFOLIOS = ROOT / "output" / "wig_history" / "index_portfolios.parquet"
PARQUET_RESERVES   = ROOT / "output" / "wig_history" / "reserve_lists.parquet"

# CSV → (revision_date, ranking_date z PDF WIG)
SOURCES = [
    {
        "csv": ROOT / "data" / "csv" / "mwig40_122025.csv",
        "revision_date": "2025-12-19",
        "ranking_date":  "2025-11-28",
    },
    {
        "csv": ROOT / "data" / "csv" / "mwig40_032026.csv",
        "revision_date": "2026-03-20",
        "ranking_date":  "2026-02-27",
    },
]


def _norm(s: str) -> str:
    return s.strip().lower()


COL_ISIN  = {"kod", "kod isin"}
COL_NAME  = {"nazwa"}
COL_PRICE = {"kurs (zł)", "kurs"}
COL_SHARE = {"liczba akcji"}
COL_WEIGH = {"udział (%)", "udzial (%)", "udział", "udzial"}
COL_TYPE  = {"typ wpisu", "typ wpisu (inferred)"}
COL_LP    = {"lp.", "lp"}


def _resolve_columns(df: pd.DataFrame) -> dict[str, str]:
    """Zwraca mapping {standard_key: actual_column_name}."""
    found: dict[str, str] = {}
    for col in df.columns:
        n = _norm(col)
        if n in COL_ISIN:  found["isin"]   = col
        elif n in COL_NAME:  found["name"]   = col
        elif n in COL_PRICE: found["price"]  = col
        elif n in COL_SHARE: found["shares"] = col
        elif n in COL_WEIGH: found["weight"] = col
        elif n in COL_TYPE:  found["type"]   = col
        elif n in COL_LP:    found["lp"]     = col

    required = {"isin", "name", "price", "shares", "weight", "type"}
    missing = required - found.keys()
    if missing:
        raise ValueError(f"Brakujące kolumny: {missing}; znaleziono: {list(df.columns)}")
    return found


def _is_main_portfolio(typ: str) -> bool:
    """Klasyfikuje wpis: True = portfel główny, False = lista rezerwowa."""
    n = _norm(typ)
    # akceptowane warianty: "portfel główny", "główny portfel"
    return "główny" in n or "glowny" in n


def parse_csv_to_rows(
    csv_path: Path,
    revision_date: str,
    ranking_date: str,
) -> tuple[list[PortfolioRow], list[ReserveRow]]:
    df = pd.read_csv(csv_path, dtype=str).fillna("")
    cols = _resolve_columns(df)

    portfolio: list[PortfolioRow] = []
    reserves:  list[ReserveRow]   = []

    for idx, row in df.iterrows():
        isin   = row[cols["isin"]].strip()
        ticker = row[cols["name"]].strip()
        typ    = row[cols["type"]].strip()
        if not isin or not ticker:
            continue

        shares = _parse_int_spaces(str(row[cols["shares"]]))

        if _is_main_portfolio(typ):
            price  = _parse_pl_float(str(row[cols["price"]]))
            weight = _parse_pl_float(str(row[cols["weight"]]))
            lp     = int(row[cols["lp"]]) if "lp" in cols and row[cols["lp"]] else len(portfolio) + 1
            portfolio.append(PortfolioRow(
                revision_date=revision_date,
                index_name="mWIG40",
                ranking_date=ranking_date,
                lp=lp,
                isin=isin,
                ticker=ticker,
                price=price,
                shares=shares,
                weight_pct=weight,
                flags=_compute_flags(isin, shares, weight),
            ))
        else:
            # lista rezerwowa — nie ma Lp ciągłego z portfelem; numerujemy od 1
            reserves.append(ReserveRow(
                revision_date=revision_date,
                index_name="mWIG40",
                lp=len(reserves) + 1,
                isin=isin,
                ticker=ticker,
                shares=shares,
            ))

    return portfolio, reserves


def append_to_parquet(
    new_portfolio: list[PortfolioRow],
    new_reserves:  list[ReserveRow],
) -> None:
    # --- portfele ---
    existing = pd.read_parquet(PARQUET_PORTFOLIOS)
    new_df = pd.DataFrame([vars(r) for r in new_portfolio])
    new_df["revision_date"] = pd.to_datetime(new_df["revision_date"])
    new_df["ranking_date"]  = pd.to_datetime(new_df["ranking_date"], errors="coerce")

    # idempotencja: usuń istniejące mWIG40 dla rewizji które właśnie ingestujemy
    new_rev_dates = new_df["revision_date"].unique()
    mask_drop = (
        (existing["index_name"] == "mWIG40")
        & (existing["revision_date"].isin(new_rev_dates))
    )
    if mask_drop.any():
        log.info(f"  Usuwam {mask_drop.sum()} istniejących wierszy mWIG40 dla rewizji {list(map(str, new_rev_dates))}")
        existing = existing[~mask_drop]

    combined = pd.concat([existing, new_df], ignore_index=True)
    combined = combined.sort_values(["revision_date", "index_name", "lp"]).reset_index(drop=True)
    combined.to_parquet(PARQUET_PORTFOLIOS, index=False)
    log.info(f"  Zapisano portfele: {PARQUET_PORTFOLIOS} ({len(combined)} wierszy)")

    # --- listy rezerwowe ---
    if not new_reserves:
        return
    existing_r = pd.read_parquet(PARQUET_RESERVES) if PARQUET_RESERVES.exists() else pd.DataFrame()
    new_rdf = pd.DataFrame([vars(r) for r in new_reserves])
    new_rdf["revision_date"] = pd.to_datetime(new_rdf["revision_date"])

    if not existing_r.empty:
        mask_drop_r = (
            (existing_r["index_name"] == "mWIG40")
            & (existing_r["revision_date"].isin(new_rdf["revision_date"].unique()))
        )
        if mask_drop_r.any():
            log.info(f"  Usuwam {mask_drop_r.sum()} istniejących wierszy reserve mWIG40")
            existing_r = existing_r[~mask_drop_r]

    combined_r = pd.concat([existing_r, new_rdf], ignore_index=True)
    combined_r = combined_r.sort_values(["revision_date", "index_name", "lp"]).reset_index(drop=True)
    combined_r.to_parquet(PARQUET_RESERVES, index=False)
    log.info(f"  Zapisano listy rezerwowe: {PARQUET_RESERVES} ({len(combined_r)} wierszy)")


def main() -> None:
    all_portfolio: list[PortfolioRow] = []
    all_reserves:  list[ReserveRow]   = []

    for src in SOURCES:
        csv = src["csv"]
        if not csv.exists():
            log.error(f"  Brak CSV: {csv}")
            continue
        portfolio, reserves = parse_csv_to_rows(
            csv,
            revision_date=src["revision_date"],
            ranking_date=src["ranking_date"],
        )
        log.info(
            f"  {src['revision_date']} mWIG40: "
            f"{len(portfolio)} portfel + {len(reserves)} rezerwa (z {csv.name})"
        )
        if len(portfolio) != 40:
            log.warning(f"  OCZEKIWANO 40 spółek w portfelu, znaleziono {len(portfolio)}")
        all_portfolio.extend(portfolio)
        all_reserves.extend(reserves)

    if not all_portfolio:
        log.error("Brak danych — nic nie appenduję.")
        sys.exit(1)

    append_to_parquet(all_portfolio, all_reserves)
    log.info("Gotowe.")


if __name__ == "__main__":
    main()
