"""
CLI do replikacji rankingu GPW Benchmark dla wybranej rewizji.

Uruchomienie:
    python -m mwig_replication.replicate_revision --revision 2025-03-21

Output:
    - output/{YYYY_MM}_revision/replication_{YYYY-MM-DD}.parquet
    - output/{YYYY_MM}_revision/replication_{YYYY-MM-DD}.ipynb

Faza A — walidujemy tylko mWIG40.
"""

from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from mwig_replication import config
from mwig_replication import data_loader
from mwig_replication import filters
from mwig_replication import ranking
from mwig_replication import buffer
from mwig_replication import validation
from mwig_replication.notebook_generator import generate_notebook

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def run_replication(revision_date: str) -> tuple[pd.DataFrame, validation.ValidationMetrics]:
    """Wykonuje pełen pipeline replikacji dla danej rewizji.

    Returns:
        (replication_df, metrics)
    """
    params = config.get_revision_params(revision_date)
    log.info(f"=== Replikacja rewizji {revision_date} ===")
    log.info(f"  Epoka: {params['epoch']}, typ: {params['type']}")
    log.info(f"  Dzień rankingu: {params['ranking_date']}")
    log.info(f"  Próg wejścia mWIG40: {params['entry_threshold_mwig40']}")
    log.info(f"  Próg utrzymania mWIG40: {params['maintenance_threshold_mwig40']}")
    log.info(f"  Próg MWO: {params['mwo_threshold_pct']}%")
    if params["eur_pln_rate"] is None:
        log.info("  Kurs EUR/PLN: nie podany — filtr 1 mln EUR pominięty")
    else:
        log.info(f"  Kurs EUR/PLN: {params['eur_pln_rate']}")

    # ---- 1. Wczytaj dane ----
    log.info("KROK 1: Wczytywanie danych...")
    rd = data_loader.load_revision(revision_date)
    log.info(f"  WIG: {len(rd.wig_portfolio)} spółek")
    log.info(f"  Faktyczny mWIG40: {len(rd.actual_mwig40)} spółek")
    log.info(f"  Lista rezerwowa mWIG40: {len(rd.actual_mwig40_reserve)} spółek")
    log.info(f"  Mapa tickerów: {len(rd.ticker_map)} wierszy")
    log.info(f"  OHLCV: {len(rd.ohlcv):,} wierszy, "
             f"{rd.ohlcv['isin'].nunique()} unikalnych ISIN, "
             f"{rd.ohlcv['date'].nunique()} unikalnych dat")
    expected_ohlcv = rd.ohlcv['isin'].nunique() * rd.ohlcv['date'].nunique()
    log.info(f"  Spodziewany rozmiar (ISIN × dat): {expected_ohlcv:,} "
             f"(efektywne wypełnienie: {len(rd.ohlcv) / expected_ohlcv * 100:.1f}%)")
    log.info(f"  Poprzednia mWIG40 ({rd.previous_revision}): "
             f"{len(rd.previous_mwig40)} spółek")

    # ---- 2. Buduj uniwersum ----
    log.info("KROK 2: Budowanie uniwersum...")
    universe = data_loader.build_universe(rd)
    log.info(f"  Uniwersum: {len(universe)} spółek")
    log.info(f"  Z OHLCV: {universe['has_ohlcv'].sum()}")
    log.info(f"  Bez mapowania ticker: {(~universe['has_ticker_map']).sum()}")

    # ---- 3. Filtry bazowe ----
    log.info("KROK 3: Filtry bazowe...")
    df = filters.apply_basic_filters(
        universe,
        rd.ohlcv,
        params["ranking_date"],
        params["eur_pln_rate"],
    )
    n_basic_pass = df["passed_basic"].sum()
    log.info(f"  Po filtrach bazowych: {n_basic_pass}/{len(df)}")

    # ---- 4. Filtr MWO ----
    log.info("KROK 4: Filtr MWO...")
    df = filters.apply_mwo_filter(
        df,
        rd.ohlcv,
        params["ranking_date"],
        params["mwo_threshold_pct"],
    )
    n_mwo_pass = (df["passed_basic"] & df["passed_mwo"]).sum()
    log.info(f"  Po filtrze MWO (i bazowych): {n_mwo_pass}")
    log.info(f"  Z reguły 1 (8/12): {df['passed_mwo_rule1'].sum()}")
    log.info(f"  Z reguły 2 (4/6): "
             f"{(df['passed_mwo_rule2'] & ~df['passed_mwo_rule1']).sum()}")

    # ---- 5. Filtr ostatniego kwartyla ----
    log.info("KROK 5: Filtr ostatniego kwartyla...")
    df = filters.apply_quartile_filter(df)
    n_in_ranking = (
        df["passed_basic"] & df["passed_mwo"] & df["passed_quartile"]
    ).sum()
    log.info(f"  Spółek w rankingu (po wszystkich filtrach): {n_in_ranking}")

    # ---- 6. Liczenie R(i) ----
    log.info("KROK 6: Liczenie sT, sC, R(i)...")
    df = ranking.compute_ranking_components(df, rd.ohlcv, params["ranking_date"])
    df = ranking.assign_ranking_position(df)

    # Sanity check
    n_with_position = df["ranking_position"].notna().sum()
    if n_with_position != n_in_ranking:
        log.warning(
            f"  Niezgodność: {n_in_ranking} przeszło filtry, "
            f"ale {n_with_position} ma pozycję rankingową"
        )

    # ---- 7. Wstępne przypisanie indeksów ----
    log.info("KROK 7: Wstępne przypisanie indeksów (kaskada)...")
    df = ranking.assign_initial_index(df)
    log.info(f"  WIG20:  {(df['initial_index'] == 'WIG20').sum()}")
    log.info(f"  mWIG40: {(df['initial_index'] == 'mWIG40').sum()}")
    log.info(f"  sWIG80: {(df['initial_index'] == 'sWIG80').sum()}")

    # ---- 8. Reguły bufora dla mWIG40 ----
    log.info("KROK 8: Reguły bufora mWIG40...")
    previous_mwig40_isins = set(rd.previous_mwig40["isin"])
    df = buffer.apply_buffer_mwig40(
        df,
        previous_mwig40_isins,
        entry_threshold=params["entry_threshold_mwig40"],
        maintenance_threshold=params["maintenance_threshold_mwig40"],
    )
    n_after_buffer = df["predicted_mwig40"].sum()
    log.info(f"  Po buforach: {n_after_buffer} spółek")

    # ---- 9. Dopełnianie składu ----
    log.info("KROK 9: Dopełnianie składu...")
    df = buffer.apply_fill_up_rule(df, target_size=config.MWIG40_SIZE)
    n_added = df["fill_up_added"].sum()
    n_final = df["predicted_mwig40"].sum()
    log.info(f"  Dosypano: {n_added}, finalnie: {n_final}")

    # ---- 10. Walidacja ----
    log.info("KROK 10: Walidacja...")
    metrics = validation.validate_mwig40(
        replication=df,
        actual_mwig40=rd.actual_mwig40,
        actual_reserve=rd.actual_mwig40_reserve,
    )
    rmse = validation.positional_rmse(metrics)

    log.info(f"  Recall:    {metrics.recall:.2%}  ({metrics.n_correct}/{metrics.n_actual})")
    log.info(f"  Precision: {metrics.precision:.2%}  ({metrics.n_correct}/{metrics.n_predicted})")
    log.info(f"  F1:        {metrics.f1:.2%}")
    if rmse is not None:
        log.info(f"  RMSE pozycyjne: {rmse:.2f} miejsc")
    log.info(f"  False positives: {len(metrics.false_positives)}")
    log.info(f"  False negatives: {len(metrics.false_negatives)}")

    return df, metrics


def main():
    parser = argparse.ArgumentParser(description="Replikacja rankingu GPW Benchmark")
    parser.add_argument("--revision", required=True,
                        help="Data rewizji (YYYY-MM-DD), np. 2025-03-21")
    args = parser.parse_args()

    revision_date = args.revision

    # Sprawdź że parametry istnieją PRZED wczytaniem danych
    try:
        config.get_revision_params(revision_date)
    except ValueError as e:
        log.error(str(e))
        sys.exit(1)

    # Wykonaj pipeline
    try:
        df, metrics = run_replication(revision_date)
    except Exception as e:
        log.exception(f"Błąd podczas replikacji: {e}")
        sys.exit(1)

    # Zapisz output
    output_dir = config.output_dir_for_revision(revision_date)
    output_dir.mkdir(parents=True, exist_ok=True)

    parquet_path = output_dir / f"replication_{revision_date}.parquet"
    notebook_path = output_dir / f"replication_{revision_date}.ipynb"

    # Konwersja typów dla Parquet (uniknięcie problemów z pd.NA)
    df_to_save = df.copy()
    for col in ["ranking_position", "ff_cap_quartile",
                "mwo_n_months_above_threshold",
                "mwo_n_months_above_threshold_last6",
                "n_active_days_3m"]:
        if col in df_to_save.columns:
            df_to_save[col] = pd.to_numeric(df_to_save[col], errors="coerce")
    for col in ["sT", "sC", "ranking_score", "turnover_12m_pln",
                "ff_market_cap_pln", "price_at_ranking"]:
        if col in df_to_save.columns:
            df_to_save[col] = pd.to_numeric(df_to_save[col], errors="coerce")

    df_to_save.to_parquet(parquet_path, index=False)
    log.info(f"Zapisano replikację: {parquet_path}")

    # Wygeneruj notebook
    generate_notebook(
        revision_date=revision_date,
        parquet_path=parquet_path,
        notebook_path=notebook_path,
    )
    log.info(f"Zapisano notebook: {notebook_path}")

    # Krótkie podsumowanie na koniec
    print("\n" + "=" * 60)
    print(f"REPLIKACJA {revision_date}")
    print("=" * 60)
    print(f"Recall:    {metrics.recall:.2%}  ({metrics.n_correct}/{metrics.n_actual})")
    print(f"Precision: {metrics.precision:.2%}")
    print(f"F1:        {metrics.f1:.2%}")
    print(f"\nWyniki: {parquet_path}")
    print(f"Notebook: {notebook_path}")


if __name__ == "__main__":
    main()
