"""
Wyliczenie składników rankingu i finalnego score'u R(i).

Mianowniki w sT i sC liczone są TYLKO po spółkach uczestniczących w rankingu
(po wszystkich filtrach: basic + MWO + ostatni kwartyl).
"""

from __future__ import annotations
from datetime import timedelta

import pandas as pd

from . import config


def compute_turnover_12m(
    ohlcv: pd.DataFrame,
    ranking_date: str,
) -> pd.DataFrame:
    """Liczy łączny obrót za 12 miesięcy poprzedzające dzień rankingu.

    Wzór:
        turnover_d = close_d × volume_d
        turnover_12m(i) = Σ_d turnover_d  za d w (ranking_date - 365, ranking_date]

    Returns:
        DataFrame: isin, turnover_12m_pln
    """
    target_date = pd.to_datetime(ranking_date).date()
    start_date = target_date - timedelta(days=365)

    df = ohlcv[
        (ohlcv["date"] >= start_date)
        & (ohlcv["date"] <= target_date)
    ].copy()

    df["turnover_pln"] = df["close"] * df["volume"]

    out = (
        df.groupby("isin")["turnover_pln"]
        .sum()
        .rename("turnover_12m_pln")
        .reset_index()
    )
    return out


def compute_ranking_components(
    df: pd.DataFrame,
    ohlcv: pd.DataFrame,
    ranking_date: str,
) -> pd.DataFrame:
    """Liczy sT, sC, R(i) dla spółek po wszystkich filtrach.

    Mianowniki obu udziałów to suma po SPÓŁKACH UCZESTNICZĄCYCH W RANKINGU
    (czyli passed_basic & passed_mwo & passed_quartile).

    Args:
        df: DataFrame z kolumnami passed_basic, passed_mwo, passed_quartile,
            ff_market_cap_pln
        ohlcv: dane OHLCV za 12M
        ranking_date: data rankingu

    Returns:
        DataFrame z dodanymi kolumnami:
            turnover_12m_pln, sT, sC, ranking_score
    """
    df = df.copy()

    # Doklej obrót 12M dla wszystkich spółek
    turnover = compute_turnover_12m(ohlcv, ranking_date)
    df = df.merge(turnover, on="isin", how="left")
    df["turnover_12m_pln"] = df["turnover_12m_pln"].fillna(0.0)

    # Identyfikujemy spółki uczestniczące w rankingu
    in_ranking = (
        df["passed_basic"]
        & df["passed_mwo"]
        & df["passed_quartile"]
    )

    # Mianowniki — sumy tylko po uczestnikach
    total_turnover = df.loc[in_ranking, "turnover_12m_pln"].sum()
    total_ff_cap = df.loc[in_ranking, "ff_market_cap_pln"].sum()

    # Inicjalizujemy NaN dla nieuczestników
    df["sT"] = pd.NA
    df["sC"] = pd.NA
    df["ranking_score"] = pd.NA

    if total_turnover > 0:
        df.loc[in_ranking, "sT"] = (
            df.loc[in_ranking, "turnover_12m_pln"] / total_turnover
        )

    if total_ff_cap > 0:
        df.loc[in_ranking, "sC"] = (
            df.loc[in_ranking, "ff_market_cap_pln"] / total_ff_cap
        )

    df.loc[in_ranking, "ranking_score"] = (
        config.RANKING_WEIGHT_TURNOVER * df.loc[in_ranking, "sT"].astype(float)
        + config.RANKING_WEIGHT_FF_CAP * df.loc[in_ranking, "sC"].astype(float)
    )

    return df


def assign_ranking_position(df: pd.DataFrame) -> pd.DataFrame:
    """Sortuje spółki uczestniczące w rankingu malejąco po ranking_score
    i przypisuje pozycję 1, 2, 3, ...

    Spółki nieuczestniczące dostają NaN w kolumnie ranking_position.
    """
    df = df.copy()
    df["ranking_position"] = pd.NA

    in_ranking = df["ranking_score"].notna()

    sorted_idx = (
        df.loc[in_ranking]
        .sort_values("ranking_score", ascending=False)
        .index
    )

    for i, idx in enumerate(sorted_idx, 1):
        df.at[idx, "ranking_position"] = i

    df["ranking_position"] = pd.to_numeric(df["ranking_position"], errors="coerce")
    return df


def assign_initial_index(df: pd.DataFrame) -> pd.DataFrame:
    """Przypisuje wstępny indeks na podstawie pozycji w rankingu (kaskada):

    - Pozycje 1-20:    WIG20
    - Pozycje 21-60:   mWIG40
    - Pozycje 61-140:  sWIG80
    - Inne:            None

    Returns:
        DataFrame z dodaną kolumną initial_index
    """
    df = df.copy()
    df["initial_index"] = None

    pos = df["ranking_position"]

    df.loc[pos.between(1, 20), "initial_index"] = "WIG20"
    df.loc[pos.between(21, 60), "initial_index"] = "mWIG40"
    df.loc[pos.between(61, 140), "initial_index"] = "sWIG80"

    return df
