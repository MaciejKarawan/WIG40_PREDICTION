"""
Predykcja składu mWIG40 dla nadchodzącej rewizji (bez ground truth).

Różnica względem replicate_revision:
- Universe ładowane z scrapu biznesradar (nie z PDF WIG)
- FF shares derived z biznesradar weight_pct + reference ticker (KGHM)
- Cena na dzień rankingu: close stooq z najbliższej sesji <= ranking_date
- Previous mWIG40/WIG20 z istniejącego index_portfolios.parquet
- Bez walidacji (nie ma jeszcze faktycznego składu)

Uruchomienie:
    python -m mwig_replication.predict_revision --revision 2026-06-19
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from . import config, filters, ranking, buffer
from .notebook_generator import generate_prediction_notebook

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

MANUAL_ISIN_BACKFILL = {
    "CRQ": "PLCTHQM00018",
    "GNS": "PLVNTCP00019",
    "S2B": "PLSNBIO00013",
    "SCW": "PLSCWAY00018",
}

# Reference ticker dla derywacji TOTAL_FF_CAP — niecapped, duża spółka, stabilny FF
REFERENCE_TICKER = "KGH"


def derive_total_ff_cap(
    biznesradar: pd.DataFrame,
    previous_wig: pd.DataFrame,
    reference_short: str = REFERENCE_TICKER,
) -> float:
    """Liczy TOTAL_WIG_FF_CAP z reference tickera:

        TOTAL = ref_ff_shares × ref_current_price / (ref_current_weight_pct / 100)

    ref_ff_shares pochodzi z PDF poprzedniej rewizji (stabilne dla blue chipów).
    """
    br_ref = biznesradar[biznesradar["ticker_short"].str.upper() == reference_short.upper()]
    if br_ref.empty:
        raise RuntimeError(f"Brak {reference_short} w biznesradar — wybierz inny reference.")
    ref_price = float(br_ref["price"].iloc[0])
    ref_weight = float(br_ref["weight_pct"].iloc[0])

    # Znajdź ref w poprzedniej rewizji WIG (ticker matching przez nazwę spółki lub mapę)
    # Mapowanie: KGH → KGHM w gpw ticker
    ref_long = br_ref["ticker_long"].iloc[0]
    prev_ref = previous_wig[previous_wig["ticker"].str.upper() == ref_long.upper()]
    if prev_ref.empty:
        raise RuntimeError(
            f"Brak {ref_long} w previous WIG ({reference_short}). "
            f"Dostępne tickery próbka: {previous_wig['ticker'].head(10).tolist()}"
        )
    ref_ff_shares = float(prev_ref["shares"].iloc[0])

    total = ref_ff_shares * ref_price / (ref_weight / 100.0)
    log.info(
        f"  TOTAL_FF_CAP derived from {reference_short} ({ref_long}): "
        f"ff_shares={ref_ff_shares:,.0f} × price={ref_price:.2f} / (weight={ref_weight:.4f}%/100) "
        f"= {total/1e9:.2f} mld PLN"
    )
    return total


def build_universe_from_biznesradar(
    biznesradar_path: Path,
    ticker_map_path: Path,
    previous_wig: pd.DataFrame,
) -> pd.DataFrame:
    """Buduje universe DataFrame z scrapu biznesradar.

    Returns:
        DataFrame z kolumnami zgodnymi z `replicate_revision.build_universe`:
            isin, ticker_gpw, stooq_ticker, ff_shares, price_pdf, has_ohlcv, has_ticker_map
    """
    br = pd.read_parquet(biznesradar_path)
    mp = pd.read_csv(ticker_map_path)

    br["ts"] = br["ticker_short"].str.upper().str.strip()
    mp["gs"] = mp["gpw_short"].astype(str).str.upper().str.strip()
    mp_dd = (
        mp.dropna(subset=["stooq_ticker_final"])
        .drop_duplicates("gs")[["gs", "stooq_ticker_final", "isin"]]
    )
    j = br.merge(mp_dd, left_on="ts", right_on="gs", how="left")
    miss = j["stooq_ticker_final"].isna()
    j.loc[miss, "stooq_ticker_final"] = j.loc[miss, "ts"].map(
        {k: v.lower() for k, v in MANUAL_ISIN_BACKFILL.items()}
        | {k: k.lower() for k in MANUAL_ISIN_BACKFILL}
    )
    j.loc[miss, "isin"] = j.loc[miss, "ts"].map(MANUAL_ISIN_BACKFILL)
    # Backfill stooq_ticker = lower(ticker_short) for any still missing
    miss2 = j["stooq_ticker_final"].isna()
    j.loc[miss2, "stooq_ticker_final"] = j.loc[miss2, "ts"].str.lower()

    if j["isin"].isna().any():
        bad = j[j["isin"].isna()][["ticker_short", "ticker_long"]]
        raise RuntimeError(f"Brak ISIN dla:\n{bad.to_string(index=False)}")

    # Wylicz TOTAL_FF_CAP
    total_ff_cap = derive_total_ff_cap(br, previous_wig)

    # Derive ff_shares per spółka
    j["ff_market_cap_proxy"] = (j["weight_pct"] / 100.0) * total_ff_cap
    j["ff_shares"] = (j["ff_market_cap_proxy"] / j["price"]).round().astype("int64")

    universe = pd.DataFrame({
        "isin": j["isin"],
        "ticker_gpw": j["ticker_long"],
        "stooq_ticker": j["stooq_ticker_final"],
        "ff_shares": j["ff_shares"],
        "price_pdf": j["price"],  # cena z biznesradar = surowa (raw), pasuje do logiki PDF
        "weight_pct_biznesradar": j["weight_pct"],
        "has_ticker_map": True,
    })
    return universe


def load_ohlcv(revision_date: str) -> pd.DataFrame:
    """Wczytuje OHLCV z output/{YYYY_MM}_revision/wig{YYYY_MM}_ohlcv.parquet
    i normalizuje kolumny do (isin, stooq_ticker, date, open, high, low, close, volume).
    """
    path = config.ohlcv_path_for_revision(revision_date)
    if not path.exists():
        raise FileNotFoundError(f"Nie ma OHLCV: {path}")
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"]).dt.date

    # Dedup
    if df.duplicated(subset=["isin", "date"]).any():
        df = df.drop_duplicates(subset=["isin", "date"], keep="last")
    df = df.sort_values(["isin", "date"]).reset_index(drop=True)
    return df


def get_close_at_ranking(ohlcv: pd.DataFrame, ranking_date: str) -> pd.DataFrame:
    """Dla każdej ISIN zwraca close z dnia rankingu (lub najbliższy wcześniejszy)."""
    target = pd.to_datetime(ranking_date).date()
    sub = ohlcv[ohlcv["date"] <= target].copy()
    last = sub.sort_values("date").groupby("isin").tail(1)
    return last[["isin", "close", "date"]].rename(
        columns={"close": "close_at_ranking", "date": "close_at_ranking_date"}
    )


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--revision", required=True, help="np. 2026-06-19")
    p.add_argument(
        "--biznesradar",
        default="data/biznesradar/WIG_20260513_2207.parquet",
        help="Ścieżka do scrapu biznesradar WIG",
    )
    args = p.parse_args()

    revision_date = args.revision
    params = config.get_revision_params(revision_date)
    ranking_date = params["ranking_date"]
    prev_rev = params["previous_revision"]

    log.info(f"=== Predykcja rewizji {revision_date} ({params['type']}) ===")
    log.info(f"  Dzień rankingu: {ranking_date}")
    log.info(f"  Poprzednia rewizja: {prev_rev}")
    log.info(f"  Próg wejścia mWIG40: {params['entry_threshold_mwig40']}")
    log.info(f"  Próg utrzymania mWIG40: {params['maintenance_threshold_mwig40']}")
    log.info(f"  Próg MWO: {params['mwo_threshold_pct']}%")

    # ---- 1. Wczytaj poprzednie składy ----
    portfolios = pd.read_parquet(config.INDEX_PORTFOLIOS_PATH)
    portfolios["revision_date"] = pd.to_datetime(portfolios["revision_date"]).dt.strftime("%Y-%m-%d")
    previous_wig = portfolios[
        (portfolios["index_name"] == "WIG") & (portfolios["revision_date"] == prev_rev)
    ].copy()
    previous_mwig40 = portfolios[
        (portfolios["index_name"] == "mWIG40") & (portfolios["revision_date"] == prev_rev)
    ][["isin", "ticker"]].copy()
    previous_wig20 = portfolios[
        (portfolios["index_name"] == "WIG20") & (portfolios["revision_date"] == prev_rev)
    ][["isin", "ticker"]].copy()
    if previous_wig20.empty:
        # 2026-03-20 nie ma WIG20 w naszym parquet — zakładamy że nie ma poprzedniego WIG20
        # (kaskada zacznie się od pozycji 1..15 i wszystkie wejdą bez bufora)
        log.warning(f"  Brak previous WIG20 dla {prev_rev}, zakładam pusty zbiór")

    log.info(f"  Previous WIG: {len(previous_wig)}, mWIG40: {len(previous_mwig40)}, WIG20: {len(previous_wig20)}")

    # ---- 2. Universe z biznesradar ----
    log.info("KROK 1: Budowanie uniwersum z biznesradar...")
    universe = build_universe_from_biznesradar(
        Path(args.biznesradar),
        config.TICKER_MAP_PATH,
        previous_wig,
    )
    log.info(f"  Uniwersum: {len(universe)} spółek")

    # ---- 3. OHLCV ----
    log.info("KROK 2: Wczytywanie OHLCV...")
    ohlcv = load_ohlcv(revision_date)
    log.info(f"  OHLCV: {len(ohlcv):,} wierszy, {ohlcv['isin'].nunique()} ISINów, "
             f"{ohlcv['date'].min()} -> {ohlcv['date'].max()}")

    # Doklej has_ohlcv
    ohlcv_isins = set(ohlcv["isin"].unique())
    universe["has_ohlcv"] = universe["isin"].isin(ohlcv_isins)
    log.info(f"  Z OHLCV: {universe['has_ohlcv'].sum()}/{len(universe)}")

    # ---- 4. Podmień price_pdf na close stooq z dnia rankingu ----
    # W predykcji nie mamy PDF na ranking_date — bierzemy close stooq (raw, nieadjusted).
    # UWAGA: stooq zwraca adjusted close. To znana rozbieżność (patrz CLAUDE.md).
    # Dla predykcji akceptujemy ten kompromis (alternatywa: użyć biznesradar price,
    # ale to cena "live" — bierzemy raczej close stooq z ranking_date dla deterministyczności).
    log.info(f"KROK 3: Cena na dzień rankingu (close stooq <= {ranking_date})...")
    close_rd = get_close_at_ranking(ohlcv, ranking_date)
    universe = universe.merge(close_rd, on="isin", how="left")
    # Update price_pdf na close stooq (gdzie dostępne); inaczej zachowaj biznesradar price
    mask_have_close = universe["close_at_ranking"].notna()
    universe.loc[mask_have_close, "price_pdf"] = universe.loc[mask_have_close, "close_at_ranking"]
    log.info(f"  Cena podmieniona na close stooq dla {mask_have_close.sum()}/{len(universe)}")
    if (~mask_have_close).any():
        miss_tickers = universe[~mask_have_close]["ticker_gpw"].tolist()
        log.warning(f"  Brak close stooq dla: {miss_tickers}")

    # ---- 5. Filtry bazowe ----
    log.info("KROK 4: Filtry bazowe...")
    df = filters.apply_basic_filters(universe, ohlcv, ranking_date, params["eur_pln_rate"])
    log.info(f"  Po basic: {df['passed_basic'].sum()}/{len(df)}")
    reasons = df[~df["passed_basic"]]["basic_failure_reason"].value_counts()
    if not reasons.empty:
        log.info(f"  Powody odrzucenia: {dict(reasons)}")

    # ---- 6. MWO ----
    log.info("KROK 5: Filtr MWO...")
    df = filters.apply_mwo_filter(df, ohlcv, ranking_date, params["mwo_threshold_pct"])
    log.info(f"  Po basic+MWO: {(df['passed_basic'] & df['passed_mwo']).sum()}")
    log.info(f"  Z reguły 1 (8/12): {df['passed_mwo_rule1'].sum()}")
    log.info(f"  Z reguły 2 (4/6, sole): "
             f"{(df['passed_mwo_rule2'] & ~df['passed_mwo_rule1']).sum()}")

    # ---- 7. Kwartyl ----
    log.info("KROK 6: Filtr ostatniego kwartyla...")
    df = filters.apply_quartile_filter(df)
    n_in_ranking = (df["passed_basic"] & df["passed_mwo"] & df["passed_quartile"]).sum()
    log.info(f"  W rankingu: {n_in_ranking}")

    # ---- 8. Ranking ----
    log.info("KROK 7: sT, sC, R(i)...")
    df = ranking.compute_ranking_components(df, ohlcv, ranking_date)
    df = ranking.assign_ranking_position(df)
    df = ranking.assign_initial_index(df)
    log.info(f"  WIG20 init: {(df['initial_index']=='WIG20').sum()}, "
             f"mWIG40 init: {(df['initial_index']=='mWIG40').sum()}, "
             f"sWIG80 init: {(df['initial_index']=='sWIG80').sum()}")

    # ---- 9. Bufor WIG20 (kaskada) ----
    log.info("KROK 8a: Bufor WIG20...")
    prev_wig20_isins = set(previous_wig20["isin"])
    df = buffer.apply_buffer_wig20(
        df, prev_wig20_isins,
        entry_threshold=params["entry_threshold_wig20"],
        maintenance_threshold=params["maintenance_threshold_wig20"],
    )
    df = buffer.apply_fill_up_wig20(df, target_size=buffer.WIG20_SIZE)
    log.info(f"  WIG20 final: {df['predicted_wig20'].sum()}")

    # ---- 10. Bufor mWIG40 ----
    log.info("KROK 8b: Bufor mWIG40...")
    prev_mwig40_isins = set(previous_mwig40["isin"])
    df = buffer.apply_buffer_mwig40(
        df, prev_mwig40_isins,
        entry_threshold=params["entry_threshold_mwig40"],
        maintenance_threshold=params["maintenance_threshold_mwig40"],
    )
    log.info(f"  Po buforze: {df['predicted_mwig40'].sum()}")

    df = buffer.apply_fill_up_rule(df, target_size=config.MWIG40_SIZE)
    df = buffer.apply_cap_down_mwig40(
        df, entry_threshold=params["entry_threshold_mwig40"],
        target_size=config.MWIG40_SIZE,
    )
    log.info(f"  mWIG40 final: {df['predicted_mwig40'].sum()}, "
             f"dosypano: {df['fill_up_added'].sum()}, capped: {df['capped_down'].sum()}")

    # ---- 11. Output ----
    out_dir = config.output_dir_for_revision(revision_date)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Konwersje typów dla Parquet
    df_out = df.copy()
    for col in ["ranking_position", "ff_cap_quartile",
                "mwo_n_months_above_threshold", "mwo_n_months_above_threshold_last6",
                "n_active_days_3m"]:
        if col in df_out.columns:
            df_out[col] = pd.to_numeric(df_out[col], errors="coerce")
    for col in ["sT", "sC", "ranking_score", "turnover_12m_pln",
                "ff_market_cap_pln", "price_at_ranking"]:
        if col in df_out.columns:
            df_out[col] = pd.to_numeric(df_out[col], errors="coerce")

    parquet_path = out_dir / f"prediction_{revision_date}.parquet"
    df_out.to_parquet(parquet_path, index=False)
    log.info(f"Zapisano: {parquet_path}")

    # Predicted mWIG40 — top-40 dla porównania
    predicted = (
        df[df["predicted_mwig40"]]
        .sort_values("ranking_position")
        [["ticker_gpw", "isin", "ranking_position", "ranking_score", "sT", "sC",
          "was_in_mwig40_before", "fill_up_added", "capped_down"]]
        .reset_index(drop=True)
    )
    csv_path = out_dir / f"prediction_{revision_date}_mwig40.csv"
    predicted.to_csv(csv_path, index=False, encoding="utf-8")
    log.info(f"Predicted mWIG40 -> {csv_path}")

    # Notebook diagnostyczny
    notebook_path = out_dir / f"prediction_{revision_date}.ipynb"
    generate_prediction_notebook(
        revision_date=revision_date,
        parquet_path=parquet_path,
        notebook_path=notebook_path,
        previous_revision=prev_rev,
    )
    log.info(f"Notebook -> {notebook_path}")

    # Delta vs poprzednia
    prev_mwig40_isins_set = set(previous_mwig40["isin"])
    pred_isins = set(predicted["isin"])
    entrants = predicted[~predicted["isin"].isin(prev_mwig40_isins_set)]
    exits = previous_mwig40[~previous_mwig40["isin"].isin(pred_isins)]

    print("\n" + "=" * 70)
    print(f"PREDYKCJA mWIG40 dla rewizji {revision_date}")
    print("=" * 70)
    print(f"\nTop 40 (predicted mWIG40):")
    print(predicted.to_string(index=False, max_colwidth=20))
    print(f"\n--- Delta vs {prev_rev} ---")
    print(f"WCHODZĄ ({len(entrants)}):")
    print(entrants[["ticker_gpw", "isin", "ranking_position"]].to_string(index=False))
    print(f"\nWYCHODZĄ ({len(exits)}):")
    print(exits.to_string(index=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
