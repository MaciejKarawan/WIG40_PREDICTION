"""
Walidacja replikacji — porównanie predicted_mwig40 z faktycznym składem.

Liczy metryki: recall, precision, F1, RMSE pozycyjne. Wskazuje rozbieżności.
"""

from __future__ import annotations
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class ValidationMetrics:
    """Metryki walidacji replikacji."""

    n_actual: int             # Liczba faktycznych członków mWIG40
    n_predicted: int          # Liczba przewidzianych przez nas
    n_correct: int            # True positives — w obu zbiorach

    recall: float             # n_correct / n_actual
    precision: float          # n_correct / n_predicted
    f1: float

    false_positives: pd.DataFrame    # Przewidzieliśmy, nie weszli
    false_negatives: pd.DataFrame    # Weszli, nie przewidzieliśmy
    true_positives: pd.DataFrame     # Trafione

    # Lista rezerwowa
    reserves_we_predicted: pd.DataFrame   # Z listy rezerwowej, my przewidzieliśmy
    reserves_we_did_not: pd.DataFrame     # Z listy rezerwowej, my nie przewidzieliśmy

    # Pozycje rankingowe rzeczywistych członków u nas
    actual_member_positions: pd.DataFrame  # Każda faktyczna spółka + nasza pozycja


def validate_mwig40(
    replication: pd.DataFrame,
    actual_mwig40: pd.DataFrame,
    actual_reserve: pd.DataFrame,
) -> ValidationMetrics:
    """Porównuje przewidziany skład mWIG40 z faktycznym z PDFu.

    Args:
        replication: DataFrame z kolumnami isin, ticker_gpw, ranking_position,
            predicted_mwig40 (i innymi diagnostycznymi)
        actual_mwig40: DataFrame z PDFu mWIG40 (kolumny isin, ticker, lp)
        actual_reserve: DataFrame listy rezerwowej (kolumny isin, ticker, lp)

    Returns:
        ValidationMetrics
    """
    # Zbiory ISIN
    actual_isins = set(actual_mwig40["isin"])
    predicted_isins = set(replication[replication["predicted_mwig40"]]["isin"])
    reserve_isins = set(actual_reserve["isin"])

    # Klasyfikacja
    correct_isins = actual_isins & predicted_isins
    fp_isins = predicted_isins - actual_isins
    fn_isins = actual_isins - predicted_isins

    n_actual = len(actual_isins)
    n_predicted = len(predicted_isins)
    n_correct = len(correct_isins)

    recall = n_correct / n_actual if n_actual > 0 else 0.0
    precision = n_correct / n_predicted if n_predicted > 0 else 0.0
    f1 = (
        2 * recall * precision / (recall + precision)
        if (recall + precision) > 0
        else 0.0
    )

    # Tabele rozbieżności
    fp_df = (
        replication[replication["isin"].isin(fp_isins)]
        [["isin", "ticker_gpw", "ranking_position", "ranking_score"]]
        .sort_values("ranking_position")
    )
    fn_df = (
        actual_mwig40[actual_mwig40["isin"].isin(fn_isins)]
        [["isin", "ticker", "lp"]]
        .merge(
            replication[["isin", "ranking_position", "ranking_score",
                         "passed_basic", "passed_mwo", "passed_quartile",
                         "basic_failure_reason"]],
            on="isin",
            how="left",
        )
        .sort_values("lp")
    )
    tp_df = (
        replication[replication["isin"].isin(correct_isins)]
        [["isin", "ticker_gpw", "ranking_position", "ranking_score"]]
        .merge(
            actual_mwig40[["isin", "lp"]].rename(columns={"lp": "actual_lp"}),
            on="isin",
            how="left",
        )
        .sort_values("ranking_position")
    )

    # Lista rezerwowa
    reserves_predicted = (
        replication[
            replication["isin"].isin(reserve_isins)
            & replication["predicted_mwig40"]
        ]
        [["isin", "ticker_gpw", "ranking_position"]]
    )
    reserves_not_predicted = (
        replication[
            replication["isin"].isin(reserve_isins)
            & ~replication["predicted_mwig40"]
        ]
        [["isin", "ticker_gpw", "ranking_position", "passed_basic",
          "passed_mwo", "passed_quartile"]]
    )

    # Pozycje rankingowe wszystkich faktycznych członków u nas
    actual_positions = (
        actual_mwig40[["isin", "ticker", "lp"]]
        .rename(columns={"lp": "actual_lp"})
        .merge(
            replication[["isin", "ranking_position", "predicted_mwig40"]],
            on="isin",
            how="left",
        )
        .sort_values("actual_lp")
    )

    return ValidationMetrics(
        n_actual=n_actual,
        n_predicted=n_predicted,
        n_correct=n_correct,
        recall=recall,
        precision=precision,
        f1=f1,
        false_positives=fp_df.reset_index(drop=True),
        false_negatives=fn_df.reset_index(drop=True),
        true_positives=tp_df.reset_index(drop=True),
        reserves_we_predicted=reserves_predicted.reset_index(drop=True),
        reserves_we_did_not=reserves_not_predicted.reset_index(drop=True),
        actual_member_positions=actual_positions.reset_index(drop=True),
    )


def positional_rmse(metrics: ValidationMetrics) -> float | None:
    """RMSE pomiędzy faktyczną pozycją (lp w PDFie mWIG40) a naszą pozycją
    rankingową (przeskalowaną — pozycje 21-60 to lp 1-40).

    Liczone tylko dla True Positives.
    """
    tp = metrics.true_positives
    if tp.empty:
        return None

    # Faktyczne lp 1-40, nasza ranking_position jest 21-60+ — przesuwamy
    actual_lp = tp["actual_lp"].values
    our_rank_relative = tp["ranking_position"].values - 20  # nasze 21 → 1, 22 → 2, itd.

    diff = actual_lp - our_rank_relative
    rmse = float(np.sqrt(np.mean(diff ** 2)))
    return rmse
