"""
Wczytywanie i podstawowe joinowanie danych wejściowych.

Wszystkie funkcje są deterministyczne (czyste) — bez I/O poza wczytaniem plików.
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import config


@dataclass
class RevisionData:
    """Komplet danych potrzebnych do replikacji jednej rewizji."""

    revision_date: str
    ranking_date: str
    previous_revision: str

    # Skład WIG-u w dniu rewizji (lista uczestników rankingu)
    wig_portfolio: pd.DataFrame
    # Kolumny: isin, ticker, shares (FF), price (z PDF, na dzień rankingu)

    # Faktyczne składy dla walidacji
    actual_mwig40: pd.DataFrame      # ground truth do porównania
    actual_wig20: pd.DataFrame
    actual_swig80: pd.DataFrame
    actual_mwig40_reserve: pd.DataFrame

    # Skład poprzedniej rewizji (do reguł bufora)
    previous_mwig40: pd.DataFrame    # tylko ISIN-y
    previous_wig20: pd.DataFrame
    previous_swig80: pd.DataFrame

    # Mapping ISIN → stooq_ticker (dla joinu z OHLCV)
    ticker_map: pd.DataFrame
    # Kolumny: isin, gpw_name, gpw_short, stooq_ticker

    # OHLCV za 12M poprzedzających dzień rankingu
    ohlcv: pd.DataFrame
    # Kolumny: isin, stooq_ticker, date, open, high, low, close, volume


def _load_index_portfolios() -> pd.DataFrame:
    df = pd.read_parquet(config.INDEX_PORTFOLIOS_PATH)
    df["revision_date"] = pd.to_datetime(df["revision_date"]).dt.strftime("%Y-%m-%d")
    return df


def _load_reserve_lists() -> pd.DataFrame:
    df = pd.read_parquet(config.RESERVE_LISTS_PATH)
    df["revision_date"] = pd.to_datetime(df["revision_date"]).dt.strftime("%Y-%m-%d")
    return df


def _load_ticker_map() -> pd.DataFrame:
    """Wczytuje mapping ISIN → stooq_ticker z CSV.

    Format CSV (nowy): kolumny m.in. isin, stooq_ticker_final, match_status,
    csv_duplicate_isin. Plik może mieć duplikaty ISIN (gdy spółka zmieniała
    ticker w czasie) — dedupujemy preferując wpisy z match_status='matched'.

    Format CSV (stary, fallback): isin, stooq_ticker.

    Returns:
        DataFrame z kolumnami: isin, stooq_ticker (jeden wiersz per ISIN)
    """
    df = pd.read_csv(config.TICKER_MAP_PATH)
    df.columns = [c.strip().lower() for c in df.columns]

    # Mapuj nową nazwę kolumny na wewnętrzną
    if "stooq_ticker_final" in df.columns:
        df = df.rename(columns={"stooq_ticker_final": "stooq_ticker"})

    required = {"isin", "stooq_ticker"}
    if not required.issubset(set(df.columns)):
        raise ValueError(
            f"ticker_isin_stooq_map.csv musi mieć kolumny isin oraz "
            f"stooq_ticker (lub stooq_ticker_final). "
            f"Aktualne: {list(df.columns)}"
        )

    # ---- Deduplikacja po ISIN ----
    # Jeśli są duplikaty, preferujemy:
    # 1. wpisy z match_status == 'matched' (jeśli kolumna istnieje)
    # 2. wpisy z niepustym stooq_ticker
    n_before = len(df)
    n_unique = df["isin"].nunique()

    if n_before > n_unique:
        # Sortuj tak, żeby preferowane wpisy były pierwsze
        if "match_status" in df.columns:
            # 'matched' przed 'unmatched'
            df["_status_priority"] = (df["match_status"] != "matched").astype(int)
            df = df.sort_values(
                ["isin", "_status_priority", "stooq_ticker"],
                na_position="last",
            )
            df = df.drop(columns=["_status_priority"])
        else:
            df = df.sort_values(["isin", "stooq_ticker"], na_position="last")

        df = df.drop_duplicates(subset="isin", keep="first").reset_index(drop=True)

    # Diagnostic: ile spółek bez stooq_ticker
    n_unmapped = df["stooq_ticker"].isna().sum()
    if n_unmapped > 0:
        # Logujemy ale nie crashujemy — te spółki wpadną w `has_ticker_map = False`
        # i zostaną odfiltrowane przez basic_filter.
        pass

    return df[["isin", "stooq_ticker"]]


def _load_ohlcv(revision_date: str) -> pd.DataFrame:
    path = config.ohlcv_path_for_revision(revision_date)
    if not path.exists():
        raise FileNotFoundError(f"Nie znaleziono OHLCV: {path}")
    df = pd.read_parquet(path)

    # Konwersja kolumny date na typ date (nie string)
    df["date"] = pd.to_datetime(df["date"]).dt.date

    # Dedup po (isin, date) — defensywnie, zachowujemy ostatni wpis
    n_before = len(df)
    if df.duplicated(subset=["isin", "date"]).any():
        df = df.drop_duplicates(subset=["isin", "date"], keep="last").reset_index(drop=True)
        n_dropped = n_before - len(df)
        # Logowanie pominięte — nie ma loggera w data_loader; widoczne pośrednio
        # przez liczność OHLCV w pipeline'u

    # Sortowanie aby gwarantować deterministyczne `iloc[-1]` w get_prices_at_ranking_date
    df = df.sort_values(["isin", "date"]).reset_index(drop=True)

    return df


def load_revision(revision_date: str) -> RevisionData:
    """Wczytuje wszystkie dane potrzebne do replikacji rewizji.

    Args:
        revision_date: data rewizji w formacie 'YYYY-MM-DD'

    Returns:
        RevisionData z wszystkimi tabelami gotowymi do dalszego przetwarzania
    """
    params = config.get_revision_params(revision_date)
    ranking_date = params["ranking_date"]
    previous = params["previous_revision"]

    portfolios = _load_index_portfolios()

    # Skład WIG dla rewizji — to są wszystkie spółki uczestniczące w rankingu
    wig = portfolios[
        (portfolios["index_name"] == "WIG")
        & (portfolios["revision_date"] == revision_date)
    ].copy()

    if wig.empty:
        raise ValueError(
            f"Brak portfela WIG dla rewizji {revision_date} w {config.INDEX_PORTFOLIOS_PATH}"
        )

    # Defensywnie: jeśli są duplikaty ISIN w WIG, weź pierwszy
    n_wig_before = len(wig)
    if wig["isin"].duplicated().any():
        wig = wig.drop_duplicates(subset="isin", keep="first").reset_index(drop=True)
        n_wig_dropped = n_wig_before - len(wig)
        # Tu nie logujemy bo data_loader nie ma loggera — później widać w build_universe

    # Faktyczne składy do walidacji
    actual_mwig40 = portfolios[
        (portfolios["index_name"] == "mWIG40")
        & (portfolios["revision_date"] == revision_date)
    ].copy()
    actual_wig20 = portfolios[
        (portfolios["index_name"] == "WIG20")
        & (portfolios["revision_date"] == revision_date)
    ].copy()
    actual_swig80 = portfolios[
        (portfolios["index_name"] == "sWIG80")
        & (portfolios["revision_date"] == revision_date)
    ].copy()

    # Lista rezerwowa mWIG40
    reserves = _load_reserve_lists()
    actual_mwig40_reserve = reserves[
        (reserves["index_name"] == "mWIG40")
        & (reserves["revision_date"] == revision_date)
    ].copy()

    # Składy poprzedniej rewizji (do reguł bufora)
    previous_mwig40 = portfolios[
        (portfolios["index_name"] == "mWIG40")
        & (portfolios["revision_date"] == previous)
    ][["isin", "ticker"]].copy()
    previous_wig20 = portfolios[
        (portfolios["index_name"] == "WIG20")
        & (portfolios["revision_date"] == previous)
    ][["isin", "ticker"]].copy()
    previous_swig80 = portfolios[
        (portfolios["index_name"] == "sWIG80")
        & (portfolios["revision_date"] == previous)
    ][["isin", "ticker"]].copy()

    # Mapping ticker
    ticker_map = _load_ticker_map()

    # OHLCV
    ohlcv = _load_ohlcv(revision_date)

    return RevisionData(
        revision_date=revision_date,
        ranking_date=ranking_date,
        previous_revision=previous,
        wig_portfolio=wig,
        actual_mwig40=actual_mwig40,
        actual_wig20=actual_wig20,
        actual_swig80=actual_swig80,
        actual_mwig40_reserve=actual_mwig40_reserve,
        previous_mwig40=previous_mwig40,
        previous_wig20=previous_wig20,
        previous_swig80=previous_swig80,
        ticker_map=ticker_map,
        ohlcv=ohlcv,
    )


def build_universe(rd: RevisionData) -> pd.DataFrame:
    """Buduje tabelę "uniwersum rankingu" — wszystkie spółki z PDF WIG-u
    poszerzone o stooq_ticker i status danych OHLCV.

    Returns:
        DataFrame z kolumnami:
            isin, ticker_gpw, stooq_ticker, ff_shares, price_pdf,
            has_ohlcv, has_ticker_map
    """
    wig = rd.wig_portfolio[["isin", "ticker", "shares", "price"]].copy()
    wig = wig.rename(columns={
        "ticker": "ticker_gpw",
        "shares": "ff_shares",
        "price":  "price_pdf",
    })

    # Doklej stooq_ticker
    tm = rd.ticker_map[["isin", "stooq_ticker"]].copy()
    universe = wig.merge(tm, on="isin", how="left")
    universe["has_ticker_map"] = universe["stooq_ticker"].notna()

    # Sprawdź dostępność OHLCV
    ohlcv_isins = set(rd.ohlcv["isin"].unique())
    universe["has_ohlcv"] = universe["isin"].isin(ohlcv_isins)

    # Asercja defensywna: po merge nie może być duplikatów ISIN
    if universe["isin"].duplicated().any():
        n_dup = universe["isin"].duplicated().sum()
        n_total = len(universe)
        n_unique = universe["isin"].nunique()
        raise ValueError(
            f"Po build_universe: {n_total} wierszy, ale tylko {n_unique} "
            f"unikalnych ISIN ({n_dup} duplikatów). "
            f"To znaczy że ticker_map ma duplikaty mimo deduplikacji w "
            f"_load_ticker_map. Sprawdź input CSV."
        )

    return universe
