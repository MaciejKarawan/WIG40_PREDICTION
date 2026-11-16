"""
Filtry kwalifikacyjne — bazowe, MWO, ostatni kwartyl.

Wszystkie filtry zwracają DataFrame z dodaną kolumną boolean `passed_xxx`.
Nie usuwają wierszy — chcemy zachować pełną diagnostykę dla wszystkich spółek.
"""

from __future__ import annotations
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from . import config


# ---------------------------------------------------------------------------
# Pomocnicze: kursy z OHLCV
# ---------------------------------------------------------------------------

def get_price_at_date(ohlcv: pd.DataFrame, isin: str, target_date: str) -> float | None:
    """Zwraca close z konkretnego dnia. Jeśli brak, zwraca None.

    UWAGA: nie cofa się do wcześniejszej sesji — wymaga dokładnej daty.
    """
    target = pd.to_datetime(target_date).date()
    rows = ohlcv[(ohlcv["isin"] == isin) & (ohlcv["date"] == target)]
    if rows.empty:
        return None
    return float(rows["close"].iloc[0])


def get_prices_at_ranking_date(
    ohlcv: pd.DataFrame,
    isins: list[str],
    ranking_date: str,
) -> pd.DataFrame:
    """Dla każdej spółki zwraca close z dnia rankingu (lub najbliższy wcześniejszy).

    Returns:
        DataFrame z kolumnami: isin, price_at_ranking
    """
    target = pd.to_datetime(ranking_date).date()

    out = []
    for isin in isins:
        spolka = ohlcv[ohlcv["isin"] == isin].sort_values("date")
        if spolka.empty:
            out.append({"isin": isin, "price_at_ranking": None})
            continue

        # Bierzemy close z dnia rankingu albo najbliższego wcześniejszego
        on_or_before = spolka[spolka["date"] <= target]
        if on_or_before.empty:
            out.append({"isin": isin, "price_at_ranking": None})
        else:
            out.append({
                "isin": isin,
                "price_at_ranking": float(on_or_before["close"].iloc[-1]),
            })

    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# Filtr 1: bazowy
# ---------------------------------------------------------------------------

def apply_basic_filters(
    universe: pd.DataFrame,
    ohlcv: pd.DataFrame,
    ranking_date: str,
    eur_pln_rate: float | None,
) -> pd.DataFrame:
    """Stosuje filtry bazowe i dodaje kolumnę passed_basic.

    Filtry:
    - has_ohlcv (musi mieć dane stooq dla rankingu — potrzebne do MWO/turnover)
    - has_ticker_map
    - FF * price >= 1 mln EUR (jeśli kurs EUR/PLN podany)
    - Min. 1 transakcja w ostatnich 3M (volume > 0 w jakimkolwiek dniu)

    Pomijamy (zgodnie z metodyką):
    - FF > 10% wszystkich akcji (brak danych o łącznej liczbie akcji)

    UWAGA: dla kapitalizacji FF używamy ceny z PDF GPW Benchmark (price_pdf),
    nie ze stooq. Stooq podaje ceny adjusted (skorygowane wstecznie o dywidendy
    i splity), które są niezgodne z surowymi cenami używanymi przez GPW Benchmark
    do liczenia indeksu. Dla MWO i obrotu 12M stooq jest OK, bo close × volume
    jest niezmiennicze względem korekt.

    Returns:
        DataFrame z dodanymi kolumnami: price_at_ranking, ff_market_cap_pln,
        had_transaction_3m, passed_basic, basic_failure_reason
    """
    df = universe.copy()

    # Cena z PDF GPW Benchmark — surowa cena z dnia rankingu
    df["price_at_ranking"] = df["price_pdf"]

    # Diagnostycznie też dolicz cenę adjusted ze stooq — do późniejszej analizy rozbieżności
    stooq_prices = get_prices_at_ranking_date(ohlcv, df["isin"].tolist(), ranking_date)
    stooq_prices = stooq_prices.rename(columns={"price_at_ranking": "price_at_ranking_stooq_adjusted"})
    df = df.merge(stooq_prices, on="isin", how="left")

    # FF market cap (PLN)
    df["ff_market_cap_pln"] = df["ff_shares"] * df["price_at_ranking"]

    # Filtr: transakcja w ostatnich 3M
    target_date = pd.to_datetime(ranking_date).date()
    three_months_ago = target_date - timedelta(days=90)

    recent_volume = (
        ohlcv[
            (ohlcv["date"] >= three_months_ago)
            & (ohlcv["date"] <= target_date)
            & (ohlcv["volume"] > 0)
        ]
        .groupby("isin")
        .size()
        .rename("n_active_days_3m")
        .reset_index()
    )
    df = df.merge(recent_volume, on="isin", how="left")
    df["n_active_days_3m"] = df["n_active_days_3m"].fillna(0).astype(int)
    df["had_transaction_3m"] = df["n_active_days_3m"] > 0

    # Filtr: FF * price >= 1 mln EUR (jeśli kurs podany)
    if eur_pln_rate is not None and eur_pln_rate > 0:
        threshold_pln = config.EUR_THRESHOLD_MILLIONS * 1_000_000 * eur_pln_rate
        df["passed_eur_threshold"] = df["ff_market_cap_pln"] >= threshold_pln
    else:
        # Brak kursu — pomijamy filtr (wszyscy przechodzą)
        df["passed_eur_threshold"] = True

    # Składamy passed_basic
    df["passed_basic"] = (
        df["has_ohlcv"]
        & df["has_ticker_map"]
        & df["had_transaction_3m"]
        & df["passed_eur_threshold"]
        & df["price_at_ranking"].notna()
    )

    # Powód odrzucenia (do diagnostyki)
    def _failure_reason(row):
        if not row["has_ticker_map"]:
            return "no_ticker_map"
        if not row["has_ohlcv"]:
            return "no_ohlcv"
        if pd.isna(row["price_at_ranking"]):
            return "no_price_at_ranking"
        if not row["had_transaction_3m"]:
            return "no_transactions_3m"
        if not row["passed_eur_threshold"]:
            return "below_eur_threshold"
        return ""

    df["basic_failure_reason"] = df.apply(_failure_reason, axis=1)

    return df


# ---------------------------------------------------------------------------
# Filtr 2: MWO
# ---------------------------------------------------------------------------

def compute_mwo(
    ohlcv: pd.DataFrame,
    ff_shares_map: dict[str, int],
    ranking_date: str,
) -> pd.DataFrame:
    """Liczy MWO (mediana DWO per miesiąc) dla każdej spółki za 12M wstecz.

    Wzór:
        DWO(i, d) = volume(i, d) / ff_shares(i) × 100
        MWO(i, m) = mediana DWO za miesiąc m

    Args:
        ohlcv: tabela OHLCV (isin, date, volume)
        ff_shares_map: dict isin → liczba akcji w pakiecie indeksowym
        ranking_date: data rankingu (data ostatniego dnia 12M okna)

    Returns:
        DataFrame długi: isin, year_month, mwo_pct
    """
    target_date = pd.to_datetime(ranking_date).date()
    start_date = target_date - timedelta(days=365)

    df = ohlcv[
        (ohlcv["date"] >= start_date)
        & (ohlcv["date"] <= target_date)
    ].copy()

    # DWO per dzień
    df["ff_shares"] = df["isin"].map(ff_shares_map)
    df = df[df["ff_shares"].notna() & (df["ff_shares"] > 0)]
    df["dwo_pct"] = df["volume"] / df["ff_shares"] * 100.0

    # MWO per miesiąc — mediana DWO
    df["year_month"] = df["date"].apply(lambda d: f"{d.year}-{d.month:02d}")
    mwo = df.groupby(["isin", "year_month"])["dwo_pct"].median().reset_index()
    mwo = mwo.rename(columns={"dwo_pct": "mwo_pct"})

    return mwo


def apply_mwo_filter(
    df: pd.DataFrame,
    ohlcv: pd.DataFrame,
    ranking_date: str,
    mwo_threshold_pct: float,
) -> pd.DataFrame:
    """Sprawdza filtr MWO i dodaje kolumny diagnostyczne.

    Logika:
    - Etap 1: spółka przechodzi jeśli MWO >= próg w 8 z 12 miesięcy
    - Etap 2: jeśli etap 1 nie OK, sprawdza 4 z ostatnich 6 miesięcy

    Args:
        df: DataFrame uniwersum (z passed_basic)
        ohlcv: dane OHLCV
        ranking_date: data rankingu
        mwo_threshold_pct: próg w jednostce DWO (np. 0.0100 dla 0,01%)

    Returns:
        DataFrame z dodanymi kolumnami:
            mwo_n_months_above_threshold,
            mwo_n_months_above_threshold_last6,
            passed_mwo_rule1, passed_mwo_rule2, passed_mwo
    """
    df = df.copy()

    # Mapping isin → ff_shares
    ff_shares_map = dict(zip(df["isin"], df["ff_shares"]))

    # Liczymy MWO dla wszystkich spółek (długi format: isin × year_month)
    mwo_df = compute_mwo(ohlcv, ff_shares_map, ranking_date)

    if mwo_df.empty:
        df["mwo_n_months_above_threshold"] = 0
        df["mwo_n_months_above_threshold_last6"] = 0
        df["passed_mwo_rule1"] = False
        df["passed_mwo_rule2"] = False
        df["passed_mwo"] = False
        return df

    # Sortuj month'y aby ostatnie 6 wziąć poprawnie
    mwo_df = mwo_df.sort_values(["isin", "year_month"])

    # Etap 1: 8 z 12
    mwo_df["above_threshold"] = mwo_df["mwo_pct"] >= mwo_threshold_pct
    n_above = mwo_df.groupby("isin")["above_threshold"].sum().rename("mwo_n_months_above_threshold")

    # Etap 2: 4 z ostatnich 6
    last6_above = (
        mwo_df.groupby("isin")
        .tail(config.MWO_RULE2_LOOKBACK)
        .groupby("isin")["above_threshold"]
        .sum()
        .rename("mwo_n_months_above_threshold_last6")
    )

    df = df.merge(n_above, on="isin", how="left")
    df = df.merge(last6_above, on="isin", how="left")
    df["mwo_n_months_above_threshold"] = df["mwo_n_months_above_threshold"].fillna(0).astype(int)
    df["mwo_n_months_above_threshold_last6"] = df["mwo_n_months_above_threshold_last6"].fillna(0).astype(int)

    df["passed_mwo_rule1"] = df["mwo_n_months_above_threshold"] >= config.MWO_RULE1_REQUIRED
    df["passed_mwo_rule2"] = df["mwo_n_months_above_threshold_last6"] >= config.MWO_RULE2_REQUIRED
    df["passed_mwo"] = df["passed_mwo_rule1"] | df["passed_mwo_rule2"]

    return df


# ---------------------------------------------------------------------------
# Filtr 3: ostatni kwartyl
# ---------------------------------------------------------------------------

def apply_quartile_filter(df: pd.DataFrame) -> pd.DataFrame:
    """Filtr ostatniego kwartyla — odrzuca dolne 25% spółek po ff_market_cap.

    UWAGA: stosujemy TYLKO do spółek które przeszły filtry bazowe + MWO.
    Mianownik kwartyla to liczność tej grupy.

    Returns:
        DataFrame z dodanymi kolumnami:
            ff_cap_quartile (1-4, 1 = najniższy), passed_quartile
    """
    df = df.copy()
    df["ff_cap_quartile"] = pd.NA
    df["passed_quartile"] = False

    # Tylko spółki po basic + MWO uczestniczą w obliczeniu kwartyla
    eligible = df[df["passed_basic"] & df["passed_mwo"]].copy()

    if eligible.empty:
        return df

    # Kwartyle
    eligible["ff_cap_quartile"] = pd.qcut(
        eligible["ff_market_cap_pln"],
        q=4,
        labels=[1, 2, 3, 4],
    ).astype(int)

    # Kwartyl 1 = najniższy = odrzucony
    eligible["passed_quartile"] = eligible["ff_cap_quartile"] >= 2

    # Wgraj z powrotem
    df = df.drop(columns=["ff_cap_quartile", "passed_quartile"])
    df = df.merge(
        eligible[["isin", "ff_cap_quartile", "passed_quartile"]],
        on="isin",
        how="left",
    )
    df["passed_quartile"] = df["passed_quartile"].fillna(False).astype(bool)

    return df
