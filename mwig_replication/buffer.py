"""
Reguły bufora — progi wejścia / utrzymania + dopełnianie składu.

WIG20: entry=15, maintenance=25.
mWIG40: entry=50, maintenance=70 (epoka 4).
"""

from __future__ import annotations
import pandas as pd

from . import config

WIG20_SIZE = 20


def apply_buffer_wig20(
    df: pd.DataFrame,
    previous_wig20_isins: set[str],
    entry_threshold: int,
    maintenance_threshold: int,
) -> pd.DataFrame:
    """Reguły bufora WIG20.

    - Pozycje 1..entry_threshold:                  zawsze w WIG20
    - Pozycje entry_threshold+1..maintenance_threshold:
        tylko jeśli były w WIG20 w poprzedniej rewizji
    - Pozycje powyżej maintenance_threshold:        nie w WIG20 z bufora
      (mogą jednak wejść przez fill_up jeśli WIG20 ma <20 spółek)

    Args:
        entry_threshold:       np. 15 (epoka 4 annual)
        maintenance_threshold: np. 25 (epoka 4 annual)
    """
    df = df.copy()
    df["was_in_wig20_before"] = df["isin"].isin(previous_wig20_isins)
    df["predicted_wig20"] = False

    pos = df["ranking_position"]

    in_zone = pos.between(1, entry_threshold)
    df.loc[in_zone, "predicted_wig20"] = True

    buffer_zone = pos.between(entry_threshold + 1, maintenance_threshold)
    df.loc[buffer_zone & df["was_in_wig20_before"], "predicted_wig20"] = True

    return df


def apply_fill_up_wig20(
    df: pd.DataFrame,
    target_size: int = WIG20_SIZE,
) -> pd.DataFrame:
    """Dosypuje do `target_size` (=20) spółkami z najwyższych pozostałych pozycji
    rankingu (nieprzypisanymi do WIG20 z entry/buffer).
    """
    df = df.copy()
    df["fill_up_wig20_added"] = False

    deficit = target_size - df["predicted_wig20"].sum()
    if deficit <= 0:
        return df

    candidates = df[
        ~df["predicted_wig20"]
        & df["ranking_position"].notna()
    ].sort_values("ranking_position")

    to_add = candidates.head(deficit)
    df.loc[to_add.index, "predicted_wig20"] = True
    df.loc[to_add.index, "fill_up_wig20_added"] = True

    return df


def apply_buffer_mwig40(
    df: pd.DataFrame,
    previous_mwig40_isins: set[str],
    entry_threshold: int,
    maintenance_threshold: int,
) -> pd.DataFrame:
    """Reguły bufora mWIG40 (epoka 4):

    - Wykluczamy spółki już przypisane do WIG20 (kaskada).
    - Pozycje rankingu 1..entry_threshold (nie w WIG20):       zawsze w mWIG40.
    - Pozycje rankingu entry_threshold+1..maintenance_threshold (nie w WIG20):
        tylko jeśli były w mWIG40 w poprzedniej rewizji.
    """
    df = df.copy()
    df["was_in_mwig40_before"] = df["isin"].isin(previous_mwig40_isins)
    df["predicted_mwig40"] = False

    pos = df["ranking_position"]
    not_in_wig20 = ~df.get("predicted_wig20", pd.Series(False, index=df.index)).astype(bool)

    in_zone = (pos >= 1) & (pos <= entry_threshold) & not_in_wig20
    df.loc[in_zone, "predicted_mwig40"] = True

    buffer_zone = pos.between(entry_threshold + 1, maintenance_threshold) & not_in_wig20
    df.loc[buffer_zone & df["was_in_mwig40_before"], "predicted_mwig40"] = True

    return df


def apply_fill_up_rule(
    df: pd.DataFrame,
    target_size: int = config.MWIG40_SIZE,
) -> pd.DataFrame:
    """Dopełnianie mWIG40 do `target_size` (=40).

    Kandydaci: spółki nieprzypisane do WIG20 ani mWIG40, mające ranking_position.
    """
    df = df.copy()
    df["fill_up_added"] = False

    deficit = target_size - df["predicted_mwig40"].sum()
    if deficit <= 0:
        return df

    not_in_wig20 = ~df.get("predicted_wig20", pd.Series(False, index=df.index)).astype(bool)

    candidates = df[
        ~df["predicted_mwig40"]
        & not_in_wig20
        & df["ranking_position"].notna()
    ].sort_values("ranking_position")

    to_add = candidates.head(deficit)
    df.loc[to_add.index, "predicted_mwig40"] = True
    df.loc[to_add.index, "fill_up_added"] = True

    return df


def apply_cap_down_mwig40(
    df: pd.DataFrame,
    entry_threshold: int,
    target_size: int = config.MWIG40_SIZE,
) -> pd.DataFrame:
    """Cap-down: jeśli po buforach mWIG40 ma > target_size spółek, wyrzuca
    spółki ze strefy bufora (rank > entry_threshold) z najgorszymi pozycjami.
    Spółki ze strefy entry (rank <= entry_threshold) są chronione.
    """
    df = df.copy()
    df["capped_down"] = False

    excess = df["predicted_mwig40"].sum() - target_size
    if excess <= 0:
        return df

    pos = df["ranking_position"]
    buffer_picks = df[
        df["predicted_mwig40"]
        & (pos > entry_threshold)
    ].sort_values("ranking_position", ascending=False)

    to_remove = buffer_picks.head(excess)
    df.loc[to_remove.index, "predicted_mwig40"] = False
    df.loc[to_remove.index, "capped_down"] = True

    return df
