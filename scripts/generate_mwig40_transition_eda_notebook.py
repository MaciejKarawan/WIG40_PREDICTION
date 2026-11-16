#!/usr/scripts/env python3
"""Generate the mWIG40 transition EDA notebook."""

from __future__ import annotations

import argparse
from pathlib import Path
from textwrap import dedent

import nbformat as nbf


DEFAULT_OUTPUT = Path("notebooks/mwig40_transition_eda.ipynb")


def md(source: str) -> nbf.NotebookNode:
    return nbf.v4.new_markdown_cell(dedent(source).strip() + "\n")


def code(source: str) -> nbf.NotebookNode:
    return nbf.v4.new_code_cell(dedent(source).strip() + "\n")


def build_notebook() -> nbf.NotebookNode:
    cells = [
        md(
            """
            # mWIG40 transition EDA

            Notebook roboczy do eksploracji rewizji mWIG40. Obejmuje:

            1. parametry,
            2. wczytanie danych i sanity check,
            3. widok jednej rewizji i parametryzowane otoczenie kandydatow,
            4. wykresy dla rewizji,
            5. drilldown po jednej spolce,
            6. test hipotezy dla wszystkich rewizji 2021-2026.

            Okna czasowe i otoczenie kandydatow sa ustawiane w komorce konfiguracyjnej.
            Wykresy dzialaja na dynamicznych oknach liczonych z `price_panel`, wiec nie sa
            przywiazane na stale do okna 60 sesji.
            """
        ),
        md(
            """
            ## 1. Parametry

            Najczesciej zmieniaj:

            - `REVISION_DATE` - formalna data rewizji,
            - `FOCUS_TICKER` - spolka do drilldownu,
            - `PRE_WINDOWS`, `POST_ANCHOR_WINDOWS`, `POST_REVISION_WINDOWS`, `POST_FACT_WINDOWS` - okna w dniach sesyjnych,
            - `CONTEXT` - definicja otoczenia kandydatow blisko progu.

            Dla wykresow czasowych zakres osi X jest liczony jako:

            - start: `-max(PRE_WINDOWS)`,
            - koniec: `max(POST_...)`.
            """
        ),
        code(
            """
            from pathlib import Path
            import math
            import warnings

            import numpy as np
            import pandas as pd
            from IPython.display import Markdown, display

            warnings.filterwarnings("ignore", category=FutureWarning)

            PROJECT_ROOT = Path.cwd()
            if not (PROJECT_ROOT / "output" / "eda" / "mwig40_event_panel.parquet").exists():
                PROJECT_ROOT = PROJECT_ROOT.parent

            EDA_DIR = PROJECT_ROOT / "output" / "eda"

            EVENT_PANEL_PATH = EDA_DIR / "mwig40_event_panel.parquet"
            SECTOR_PEER_PANEL_PATH = EDA_DIR / "mwig40_sector_peer_panel.parquet"
            PRICE_PANEL_PATH = EDA_DIR / "mwig40_price_panel.parquet"
            SUMMARY_PATH = EDA_DIR / "mwig40_eda_panel_summary.csv"
            FULL_OHLCV_PATH = PROJECT_ROOT / "output" / "eda_2021_2026_revision" / "wigeda_2021_2026_ohlcv.parquet"

            pd.set_option("display.max_columns", 160)
            pd.set_option("display.max_rows", 160)
            pd.set_option("display.float_format", lambda x: f"{x:,.4f}")

            try:
                import matplotlib.pyplot as plt

                HAS_MATPLOTLIB = True
                plt.rcParams.update(
                    {
                        "figure.figsize": (12, 6),
                        "axes.grid": True,
                        "grid.alpha": 0.25,
                        "axes.spines.top": False,
                        "axes.spines.right": False,
                    }
                )
            except Exception as exc:
                HAS_MATPLOTLIB = False
                print(f"Matplotlib unavailable: {exc}. Tables will still work.")
            """
        ),
        code(
            """
            REVISION_DATE = "2026-03-20"
            FOCUS_TICKER = "CREOTECH"  # None -> first entrant in selected revision

            # Trading-day windows. You can change these and rerun from this cell down.
            # PRIMARY_WINDOWS drive the cross-revision hypothesis test.
            PRIMARY_WINDOWS = [7, 14, 30, 60, 120]
            PRE_WINDOWS = PRIMARY_WINDOWS.copy()
            POST_ANCHOR_WINDOWS = [5, 20]
            POST_REVISION_WINDOWS = [5, 20]
            POST_FACT_WINDOWS = [1, 3, 7, 14, 30, 60, 120]
            POST_FACT_SECTOR_TOP_PERCENTILE = 0.10

            # Rolling windows used in the focus drilldown.
            ROLLING_VOL_WINDOWS = [20, 60]
            ROLLING_TURNOVER_WINDOWS = [20, 60]

            # Windows used in comparison plots. They do not have to equal PRE_WINDOWS,
            # but every value should have enough price history.
            WINDOWS_TO_COMPARE = PRIMARY_WINDOWS.copy()

            # Cross-revision hypothesis-test universe.
            UNIVERSE_MODE = "near_threshold"  # "near_threshold" or "all_wig_candidates"
            WEIGHT_RANK_CENTERS = [15, 70]
            WEIGHT_NEIGHBOR_COUNT = 10
            TOP_PERCENTILES = [0.10, 0.20, 0.30]
            SCORING_WINDOW = 60
            SCORING_TOP_PERCENTILE = 0.20
            USE_CURRENT_RESERVE_AS_FEATURE = False

            # Parametryzowane otoczenie kandydatow.
            CONTEXT = {
                "include_entrants": True,
                "include_exits": True,
                "include_previous_reserve": True,
                "include_current_reserve": True,
                "include_same_sector_peers": True,
                "include_weight_neighbors": True,
                # Approximate WIG weight ranks around WIG20/mWIG40 and mWIG40/sWIG80 borders.
                "weight_rank_centers": WEIGHT_RANK_CENTERS,
                "weight_neighbor_count": WEIGHT_NEIGHBOR_COUNT,
                # Sector peers are capped per sector to keep plots readable.
                "max_sector_peers_per_sector": 25,
            }

            # Price chart normalization:
            # - "window_start": first visible trading day in the chart is 100.
            # - "target_date": anchor/revision trading day is 100.
            NORMALIZE_MODE = "window_start"
            NORMALIZE_BASE = 100.0
            PLOT_TOP_N_LINES = 28
            """
        ),
        md(
            """
            ## 2. Wczytanie danych i sanity check

            Notebook korzysta z przygotowanych paneli:

            - `mwig40_event_panel.parquet`,
            - `mwig40_sector_peer_panel.parquet`,
            - `mwig40_price_panel.parquet`,
            - `mwig40_eda_panel_summary.csv`.
            """
        ),
        code(
            """
            event_panel = pd.read_parquet(EVENT_PANEL_PATH)
            sector_peer_panel = pd.read_parquet(SECTOR_PEER_PANEL_PATH)
            price_panel = pd.read_parquet(PRICE_PANEL_PATH)
            summary = pd.read_csv(SUMMARY_PATH, parse_dates=["revision_date", "anchor_date"])
            if FULL_OHLCV_PATH.exists():
                hypothesis_price_panel = pd.read_parquet(FULL_OHLCV_PATH)
                HYPOTHESIS_PRICE_SOURCE = "full_ohlcv"
            else:
                hypothesis_price_panel = price_panel.copy()
                HYPOTHESIS_PRICE_SOURCE = "eda_price_panel"

            for col in ["revision_date", "previous_revision_date", "anchor_date", "anchor_trading_date"]:
                if col in event_panel.columns:
                    event_panel[col] = pd.to_datetime(event_panel[col], errors="coerce")
            if "revision_date" in sector_peer_panel.columns:
                sector_peer_panel["revision_date"] = pd.to_datetime(sector_peer_panel["revision_date"], errors="coerce")
            price_panel["date"] = pd.to_datetime(price_panel["date"], errors="coerce")
            hypothesis_price_panel["date"] = pd.to_datetime(hypothesis_price_panel["date"], errors="coerce")

            for df in [event_panel, sector_peer_panel, price_panel, hypothesis_price_panel]:
                for col in ["ticker", "stooq_ticker", "sector", "macrosector", "industry"]:
                    if col in df.columns:
                        df[col] = df[col].fillna("").astype(str)

            revision_dates = sorted(event_panel["revision_date"].dropna().unique())
            revision_dates_str = [pd.Timestamp(x).date().isoformat() for x in revision_dates]

            data_overview = pd.DataFrame(
                [
                    {
                        "dataset": "event_panel",
                        "rows": len(event_panel),
                        "columns": event_panel.shape[1],
                        "unique_isins": event_panel["isin"].nunique(),
                        "date_min": event_panel["revision_date"].min().date(),
                        "date_max": event_panel["revision_date"].max().date(),
                    },
                    {
                        "dataset": "sector_peer_panel",
                        "rows": len(sector_peer_panel),
                        "columns": sector_peer_panel.shape[1],
                        "unique_isins": sector_peer_panel.get("peer_isin", pd.Series(dtype=str)).nunique(),
                        "date_min": sector_peer_panel["revision_date"].min().date(),
                        "date_max": sector_peer_panel["revision_date"].max().date(),
                    },
                    {
                        "dataset": "price_panel",
                        "rows": len(price_panel),
                        "columns": price_panel.shape[1],
                        "unique_isins": price_panel["isin"].nunique(),
                        "date_min": price_panel["date"].min().date(),
                        "date_max": price_panel["date"].max().date(),
                    },
                    {
                        "dataset": f"hypothesis_price_panel ({HYPOTHESIS_PRICE_SOURCE})",
                        "rows": len(hypothesis_price_panel),
                        "columns": hypothesis_price_panel.shape[1],
                        "unique_isins": hypothesis_price_panel["isin"].nunique(),
                        "date_min": hypothesis_price_panel["date"].min().date(),
                        "date_max": hypothesis_price_panel["date"].max().date(),
                    },
                ]
            )

            display(data_overview)
            display(Markdown("**Coverage by revision:**"))
            display(summary.tail(12))
            """
        ),
        code(
            """
            missing_files = [
                str(path)
                for path in [EVENT_PANEL_PATH, SECTOR_PEER_PANEL_PATH, PRICE_PANEL_PATH, SUMMARY_PATH]
                if not path.exists()
            ]
            if missing_files:
                raise FileNotFoundError("Missing EDA files: " + ", ".join(missing_files))

            if pd.Timestamp(REVISION_DATE) not in set(revision_dates):
                raise ValueError(f"Unknown REVISION_DATE={REVISION_DATE}. Available: {revision_dates_str}")

            def positive_int_list(name, values):
                if not values or any((not isinstance(v, int)) or v <= 0 for v in values):
                    raise ValueError(f"{name} must be a non-empty list of positive integers")
                return sorted(set(values))

            PRIMARY_WINDOWS = positive_int_list("PRIMARY_WINDOWS", PRIMARY_WINDOWS)
            PRE_WINDOWS = positive_int_list("PRE_WINDOWS", PRE_WINDOWS)
            POST_ANCHOR_WINDOWS = positive_int_list("POST_ANCHOR_WINDOWS", POST_ANCHOR_WINDOWS)
            POST_REVISION_WINDOWS = positive_int_list("POST_REVISION_WINDOWS", POST_REVISION_WINDOWS)
            POST_FACT_WINDOWS = positive_int_list("POST_FACT_WINDOWS", POST_FACT_WINDOWS)
            ROLLING_VOL_WINDOWS = positive_int_list("ROLLING_VOL_WINDOWS", ROLLING_VOL_WINDOWS)
            ROLLING_TURNOVER_WINDOWS = positive_int_list("ROLLING_TURNOVER_WINDOWS", ROLLING_TURNOVER_WINDOWS)
            WINDOWS_TO_COMPARE = positive_int_list("WINDOWS_TO_COMPARE", WINDOWS_TO_COMPARE)
            WEIGHT_RANK_CENTERS = positive_int_list("WEIGHT_RANK_CENTERS", WEIGHT_RANK_CENTERS)
            if not 0 < POST_FACT_SECTOR_TOP_PERCENTILE <= 1:
                raise ValueError("POST_FACT_SECTOR_TOP_PERCENTILE must be in (0, 1]")
            if UNIVERSE_MODE not in {"near_threshold", "all_wig_candidates"}:
                raise ValueError("UNIVERSE_MODE must be 'near_threshold' or 'all_wig_candidates'")
            if USE_CURRENT_RESERVE_AS_FEATURE:
                raise ValueError("USE_CURRENT_RESERVE_AS_FEATURE must remain False for predictive testing")
            if SCORING_WINDOW not in PRIMARY_WINDOWS:
                raise ValueError("SCORING_WINDOW must be one of PRIMARY_WINDOWS")
            if NORMALIZE_MODE not in {"window_start", "target_date"}:
                raise ValueError("NORMALIZE_MODE must be 'window_start' or 'target_date'")

            PLOT_PRE_DAYS = max(PRE_WINDOWS)
            PLOT_POST_ANCHOR_DAYS = max(POST_ANCHOR_WINDOWS)
            PLOT_POST_REVISION_DAYS = max(POST_REVISION_WINDOWS)

            display(
                Markdown(
                    f"Selected revision: `{REVISION_DATE}`. "
                    f"Time plots use `-{PLOT_PRE_DAYS}` to `+{PLOT_POST_ANCHOR_DAYS}` trading days around anchor "
                    f"and `-{PLOT_PRE_DAYS}` to `+{PLOT_POST_REVISION_DAYS}` around revision. "
                    f"Price normalization mode: `{NORMALIZE_MODE}`."
                )
            )
            """
        ),
        md(
            """
            ## Funkcje pomocnicze

            Funkcje ponizej buduja koszyk rewizji, dynamicznie licza metryki z `price_panel`
            i tworza wykresy. Po zmianie parametrow w sekcji 1 rerun od tego miejsca wystarczy.
            """
        ),
        code(
            """
            def max_drawdown(close):
                if close.empty:
                    return np.nan
                return float((close / close.cummax() - 1.0).min())


            def primary_role(role_text):
                priority = [
                    "focus",
                    "entered_mwig40",
                    "exited_mwig40",
                    "previous_mwig40_reserve",
                    "current_mwig40_reserve",
                    "weight_neighbor",
                    "sector_peer",
                ]
                roles = set(role_text.split(";")) if role_text else set()
                for role in priority:
                    if role in roles:
                        return role
                return "other"


            ROLE_ORDER = {
                "focus": 0,
                "entered_mwig40": 1,
                "exited_mwig40": 2,
                "previous_mwig40_reserve": 3,
                "current_mwig40_reserve": 4,
                "weight_neighbor": 5,
                "sector_peer": 6,
                "other": 9,
            }


            ROLE_COLORS = {
                "focus": "#111111",
                "entered_mwig40": "#006BA4",
                "exited_mwig40": "#B13A32",
                "previous_mwig40_reserve": "#7A5195",
                "current_mwig40_reserve": "#F0A202",
                "weight_neighbor": "#4D7C0F",
                "sector_peer": "#8C8C8C",
                "other": "#999999",
            }


            def add_role(role_map, isins, role):
                for isin in pd.Series(list(isins)).dropna().astype(str):
                    role_map.setdefault(isin, set()).add(role)


            def latest_price_metadata():
                return (
                    price_panel.sort_values("date")
                    .drop_duplicates("isin", keep="last")[
                        ["isin", "ticker", "stooq_ticker", "macrosector", "sector", "industry"]
                    ]
                )


            def build_revision_context(revision_date, focus_ticker=None):
                revision = pd.Timestamp(revision_date)
                focus = event_panel.loc[event_panel["revision_date"].eq(revision)].copy()
                if focus.empty:
                    raise ValueError(f"No event_panel rows for {revision_date}")

                focus["wig_weight_rank"] = (
                    focus["weight_pct"].rank(method="first", ascending=False).astype("Int64")
                    if "weight_pct" in focus.columns
                    else pd.Series(pd.NA, index=focus.index, dtype="Int64")
                )
                previous_revision_values = focus["previous_revision_date"].dropna()
                if not previous_revision_values.empty:
                    previous_revision = pd.Timestamp(previous_revision_values.iloc[0])
                    previous_focus = event_panel.loc[event_panel["revision_date"].eq(previous_revision)].copy()
                    previous_focus["previous_wig_weight_rank"] = (
                        previous_focus["weight_pct"].rank(method="first", ascending=False).astype("Int64")
                        if "weight_pct" in previous_focus.columns
                        else pd.Series(pd.NA, index=previous_focus.index, dtype="Int64")
                    )
                    previous_rank_map = previous_focus.set_index("isin")["previous_wig_weight_rank"]
                    focus["previous_wig_weight_rank"] = focus["isin"].map(previous_rank_map).astype("Int64")
                else:
                    focus["previous_wig_weight_rank"] = pd.Series(pd.NA, index=focus.index, dtype="Int64")

                effective_focus_ticker = focus_ticker.upper() if focus_ticker else None
                if not effective_focus_ticker:
                    entrants = focus.loc[focus["entered_mwig40"]].sort_values(["ticker", "isin"])
                    effective_focus_ticker = entrants["ticker"].iloc[0] if not entrants.empty else None

                role_map = {}

                if CONTEXT.get("include_entrants", True):
                    add_role(role_map, focus.loc[focus["entered_mwig40"], "isin"], "entered_mwig40")
                if CONTEXT.get("include_exits", True):
                    add_role(role_map, focus.loc[focus["exited_mwig40"], "isin"], "exited_mwig40")
                if CONTEXT.get("include_previous_reserve", True):
                    add_role(role_map, focus.loc[focus["previous_mwig40_reserve"], "isin"], "previous_mwig40_reserve")
                if CONTEXT.get("include_current_reserve", True):
                    add_role(role_map, focus.loc[focus["current_mwig40_reserve"], "isin"], "current_mwig40_reserve")

                if effective_focus_ticker:
                    focus_match = focus.loc[focus["ticker"].str.upper().eq(effective_focus_ticker)]
                    if not focus_match.empty:
                        add_role(role_map, focus_match["isin"], "focus")
                    else:
                        display(Markdown(f"`FOCUS_TICKER={effective_focus_ticker}` is not present in this revision."))

                if CONTEXT.get("include_weight_neighbors", True) and "wig_weight_rank" in focus.columns:
                    neighbor_count = int(CONTEXT.get("weight_neighbor_count", 10))
                    centers = CONTEXT.get("weight_rank_centers", [20, 60])
                    for center in centers:
                        mask = focus["wig_weight_rank"].between(center - neighbor_count, center + neighbor_count)
                        add_role(role_map, focus.loc[mask, "isin"], "weight_neighbor")

                if CONTEXT.get("include_same_sector_peers", True):
                    anchor_isins = set(role_map)
                    anchor_sectors = set(
                        focus.loc[focus["isin"].isin(anchor_isins), "sector"].replace("", np.nan).dropna()
                    )
                    max_per_sector = int(CONTEXT.get("max_sector_peers_per_sector", 25))
                    for sector in sorted(anchor_sectors):
                        peers = (
                            focus.loc[focus["sector"].eq(sector)]
                            .sort_values(["weight_pct", "ticker"], ascending=[False, True])
                            .head(max_per_sector)
                        )
                        add_role(role_map, peers["isin"], "sector_peer")

                if not role_map:
                    raise ValueError("Context is empty. Loosen CONTEXT settings.")

                context = focus.loc[focus["isin"].isin(role_map)].copy()
                context["context_role"] = context["isin"].map(lambda isin: ";".join(sorted(role_map.get(isin, set()))))
                context["primary_role"] = context["context_role"].map(primary_role)
                context["role_order"] = context["primary_role"].map(ROLE_ORDER).fillna(9).astype(int)
                context = context.sort_values(["role_order", "sector", "wig_weight_rank", "ticker", "isin"]).reset_index(drop=True)

                return focus.reset_index(drop=True), context


            def enrich_price_data(price_df):
                out = price_df.sort_values(["isin", "date"]).copy()
                out["turnover"] = out["close"] * out["volume"]
                out["return_1d"] = out.groupby("isin")["close"].pct_change()

                for window in sorted(set(ROLLING_VOL_WINDOWS + ROLLING_TURNOVER_WINDOWS + PRE_WINDOWS + WINDOWS_TO_COMPARE)):
                    min_periods = max(5, min(window, math.ceil(window / 3)))
                    out[f"rolling_vol_{window}td_ann"] = (
                        out.groupby("isin")["return_1d"]
                        .transform(lambda s: s.rolling(window, min_periods=min_periods).std(ddof=0) * math.sqrt(252))
                    )
                    out[f"rolling_avg_turnover_{window}td"] = (
                        out.groupby("isin")["turnover"]
                        .transform(lambda s: s.rolling(window, min_periods=min_periods).mean())
                    )
                return out


            price_enriched = enrich_price_data(price_panel)
            """
        ),
        code(
            """
            def compute_dynamic_metrics(
                price_df,
                universe,
                target_date,
                pre_windows,
                post_windows,
                target_label,
            ):
                rows = []
                universe_cols = ["isin", "ticker", "sector", "macrosector", "industry"]
                universe_meta = universe[universe_cols].drop_duplicates("isin")

                price_groups = {
                    isin: group.sort_values("date").reset_index(drop=True)
                    for isin, group in price_df.loc[price_df["isin"].isin(universe_meta["isin"])].groupby("isin", sort=False)
                }

                for meta in universe_meta.itertuples(index=False):
                    group = price_groups.get(meta.isin)
                    row = {
                        "isin": meta.isin,
                        "ticker": meta.ticker,
                        "sector": meta.sector,
                        "macrosector": meta.macrosector,
                        "industry": meta.industry,
                        f"{target_label}_target_date": pd.Timestamp(target_date),
                    }
                    if group is None or group.empty:
                        row[f"{target_label}_target_trading_date"] = pd.NaT
                        rows.append(row)
                        continue

                    idx = group["date"].searchsorted(pd.Timestamp(target_date), side="right") - 1
                    if idx < 0:
                        row[f"{target_label}_target_trading_date"] = pd.NaT
                        rows.append(row)
                        continue

                    row[f"{target_label}_target_trading_date"] = group.loc[idx, "date"]
                    row[f"{target_label}_close"] = group.loc[idx, "close"]
                    row[f"{target_label}_pre_trading_days_available"] = int(idx)
                    row[f"{target_label}_post_trading_days_available"] = int(len(group) - idx - 1)

                    for window in pre_windows:
                        start_idx = idx - window
                        if start_idx >= 0:
                            segment = group.iloc[start_idx : idx + 1].copy()
                            returns = segment["return_1d"].dropna()
                            avg_turnover = segment["turnover"].mean()
                            row[f"ret_m{window}td_to_{target_label}"] = group.loc[idx, "close"] / group.loc[start_idx, "close"] - 1.0
                            row[f"vol_m{window}td_ann_to_{target_label}"] = (
                                returns.std(ddof=0) * math.sqrt(252) if len(returns) > 1 else np.nan
                            )
                            row[f"avg_turnover_m{window}td_to_{target_label}"] = avg_turnover
                            row[f"max_drawdown_m{window}td_to_{target_label}"] = max_drawdown(segment["close"])

                            prev_start_idx = start_idx - window
                            if prev_start_idx >= 0:
                                previous_turnover = group.iloc[prev_start_idx:start_idx]["turnover"].mean()
                                row[f"turnover_ratio_m{window}td_to_{target_label}"] = (
                                    avg_turnover / previous_turnover
                                    if previous_turnover and not pd.isna(previous_turnover)
                                    else np.nan
                                )
                            else:
                                row[f"turnover_ratio_m{window}td_to_{target_label}"] = np.nan
                        else:
                            row[f"ret_m{window}td_to_{target_label}"] = np.nan
                            row[f"vol_m{window}td_ann_to_{target_label}"] = np.nan
                            row[f"avg_turnover_m{window}td_to_{target_label}"] = np.nan
                            row[f"max_drawdown_m{window}td_to_{target_label}"] = np.nan
                            row[f"turnover_ratio_m{window}td_to_{target_label}"] = np.nan

                    for window in post_windows:
                        end_idx = idx + window
                        if end_idx < len(group):
                            segment = group.iloc[idx : end_idx + 1].copy()
                            returns = segment["return_1d"].dropna()
                            row[f"ret_p{window}td_from_{target_label}"] = group.loc[end_idx, "close"] / group.loc[idx, "close"] - 1.0
                            row[f"vol_p{window}td_ann_from_{target_label}"] = (
                                returns.std(ddof=0) * math.sqrt(252) if len(returns) > 1 else np.nan
                            )
                            row[f"avg_turnover_p{window}td_from_{target_label}"] = segment["turnover"].mean()
                        else:
                            row[f"ret_p{window}td_from_{target_label}"] = np.nan
                            row[f"vol_p{window}td_ann_from_{target_label}"] = np.nan
                            row[f"avg_turnover_p{window}td_from_{target_label}"] = np.nan

                    rows.append(row)

                out = pd.DataFrame(rows)
                metric_cols = [
                    col
                    for col in out.columns
                    if col.startswith(("ret_", "vol_", "avg_turnover_", "max_drawdown_", "turnover_ratio_"))
                ]
                for col in metric_cols:
                    median_col = f"{col}_sector_median"
                    out[median_col] = out.groupby("sector")[col].transform("median")
                    out[f"{col}_vs_sector"] = out[col] - out[median_col]
                    with np.errstate(divide="ignore", invalid="ignore"):
                        out[f"{col}_rel_sector"] = out[col] / out[median_col] - 1.0
                return out


            def build_relative_window(
                price_df,
                universe,
                target_date,
                pre_days,
                post_days,
                target_label,
            ):
                rows = []
                meta = universe[["isin", "ticker", "sector", "primary_role", "context_role"]].drop_duplicates("isin")
                groups = {
                    isin: group.sort_values("date").reset_index(drop=True)
                    for isin, group in price_df.loc[price_df["isin"].isin(meta["isin"])].groupby("isin", sort=False)
                }
                for item in meta.itertuples(index=False):
                    group = groups.get(item.isin)
                    if group is None or group.empty:
                        continue
                    idx = group["date"].searchsorted(pd.Timestamp(target_date), side="right") - 1
                    if idx < 0:
                        continue
                    lo = max(0, idx - pre_days)
                    hi = min(len(group), idx + post_days + 1)
                    window = group.iloc[lo:hi].copy()
                    if NORMALIZE_MODE == "window_start":
                        base_idx = lo
                    elif NORMALIZE_MODE == "target_date":
                        base_idx = idx
                    else:
                        raise ValueError("NORMALIZE_MODE must be 'window_start' or 'target_date'")
                    base_close = group.loc[base_idx, "close"]
                    window["relative_day"] = np.arange(lo, hi) - idx
                    window["target_date"] = pd.Timestamp(target_date)
                    window["target_label"] = target_label
                    window["target_trading_date"] = group.loc[idx, "date"]
                    window["normalization_mode"] = NORMALIZE_MODE
                    window["normalization_date"] = group.loc[base_idx, "date"]
                    window["normalized_close"] = window["close"] / base_close * NORMALIZE_BASE
                    window["ticker"] = item.ticker
                    window["sector"] = item.sector
                    window["primary_role"] = item.primary_role
                    window["context_role"] = item.context_role
                    rows.append(window)

                if not rows:
                    return pd.DataFrame()
                out = pd.concat(rows, ignore_index=True)
                out["sector_median_normalized_close"] = out.groupby(["sector", "relative_day"])["normalized_close"].transform("median")
                for window in sorted(set(ROLLING_VOL_WINDOWS + ROLLING_TURNOVER_WINDOWS)):
                    vol_col = f"rolling_vol_{window}td_ann"
                    turnover_col = f"rolling_avg_turnover_{window}td"
                    if vol_col in out.columns:
                        out[f"{vol_col}_sector_median"] = out.groupby(["sector", "relative_day"])[vol_col].transform("median")
                        out[f"{vol_col}_vs_sector"] = out[vol_col] - out[f"{vol_col}_sector_median"]
                    if turnover_col in out.columns:
                        out[f"{turnover_col}_sector_median"] = out.groupby(["sector", "relative_day"])[turnover_col].transform("median")
                        out[f"{turnover_col}_rel_sector"] = out[turnover_col] / out[f"{turnover_col}_sector_median"] - 1.0
                return out
            """
        ),
        code(
            """
            def format_metric_table(df):
                pct_cols = [
                    col
                    for col in df.columns
                    if col.startswith(("ret_", "vol_", "max_drawdown_", "turnover_ratio_"))
                    or col.endswith(("_vs_sector", "_rel_sector"))
                    or "return" in col
                    or col.endswith("_share")
                    or col in {"precision", "recall", "baseline_rate", "entry_rate"}
                ]
                money_cols = [col for col in df.columns if col.startswith("avg_turnover_")]
                rank_cols = [col for col in df.columns if col.endswith("_rank") or col == "wig_weight_rank"]
                fmt = {col: "{:.2%}" for col in pct_cols}
                fmt.update({col: "{:,.0f}" for col in money_cols})
                fmt.update({col: "{:.0f}" for col in rank_cols})
                return df.style.format(fmt, na_rep="")


            def selected_lines_for_plot(context, max_lines=PLOT_TOP_N_LINES):
                prioritized = context.sort_values(["role_order", "sector", "wig_weight_rank", "ticker"]).copy()
                return prioritized.head(max_lines)


            def plot_normalized_prices(window_df, context, title):
                if not HAS_MATPLOTLIB:
                    return
                if window_df.empty:
                    print("No price data for this chart.")
                    return

                selected = selected_lines_for_plot(context)
                plot_df = window_df.loc[window_df["isin"].isin(selected["isin"])].copy()
                fig, ax = plt.subplots(figsize=(13, 6))

                for item in selected.itertuples(index=False):
                    series = plot_df.loc[plot_df["isin"].eq(item.isin)].sort_values("relative_day")
                    if series.empty:
                        continue
                    color = ROLE_COLORS.get(item.primary_role, "#999999")
                    linewidth = 2.8 if item.primary_role in {"focus", "entered_mwig40"} else 1.2
                    alpha = 0.95 if item.primary_role in {"focus", "entered_mwig40"} else 0.45
                    ax.plot(
                        series["relative_day"],
                        series["normalized_close"],
                        label=f"{item.ticker} ({item.primary_role})",
                        color=color,
                        linewidth=linewidth,
                        alpha=alpha,
                    )

                sectors_to_show = selected.loc[selected["primary_role"].isin(["focus", "entered_mwig40"]), "sector"].dropna().unique()
                for sector in sectors_to_show:
                    sector_series = (
                        window_df.loc[window_df["sector"].eq(sector)]
                        .groupby("relative_day", as_index=False)["normalized_close"]
                        .median()
                        .sort_values("relative_day")
                    )
                    if not sector_series.empty:
                        ax.plot(
                            sector_series["relative_day"],
                            sector_series["normalized_close"],
                            linestyle="--",
                            linewidth=2.0,
                            color="#222222",
                            alpha=0.65,
                            label=f"sector median: {sector}",
                        )

                ax.axvline(0, color="#222222", linewidth=1.2)
                ax.axhline(NORMALIZE_BASE, color="#555555", linewidth=0.8, alpha=0.55)
                ax.set_title(title)
                ax.set_xlabel("Trading days relative to target date")
                label = "window start" if NORMALIZE_MODE == "window_start" else "target date"
                ax.set_ylabel(f"Close indexed to {label} = {NORMALIZE_BASE:.0f}")
                ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1), borderaxespad=0)
                plt.tight_layout()
                plt.show()


            def plot_metric_vs_sector_bars(
                metrics,
                context,
                column_template,
                windows,
                title,
                comparison_suffix="_vs_sector",
            ):
                if not HAS_MATPLOTLIB:
                    return

                selected = context.loc[~context["primary_role"].eq("sector_peer")].copy()
                if selected.empty:
                    selected = context.copy()
                selected = selected.sort_values(["role_order", "wig_weight_rank", "ticker"]).head(20)

                metric_values = metrics.drop(columns=["ticker", "sector", "macrosector", "industry"], errors="ignore")
                merged = selected[["isin", "ticker", "primary_role", "role_order"]].merge(metric_values, on="isin", how="left")
                fig, axes = plt.subplots(len(windows), 1, figsize=(12, max(3.5, 3.2 * len(windows))), squeeze=False)
                axes = axes.ravel()

                for ax, window in zip(axes, windows):
                    base_col = column_template.format(w=window)
                    col = f"{base_col}{comparison_suffix}"
                    if col not in merged.columns:
                        ax.set_visible(False)
                        continue
                    plot_df = merged[["ticker", "primary_role", col]].dropna().sort_values(col)
                    if plot_df.empty:
                        ax.set_visible(False)
                        continue
                    colors = [ROLE_COLORS.get(role, "#999999") for role in plot_df["primary_role"]]
                    ax.barh(plot_df["ticker"], plot_df[col], color=colors, alpha=0.82)
                    ax.axvline(0, color="#222222", linewidth=1.0)
                    ax.set_title(f"{title} - {window}td")
                    ax.set_xlabel(col)

                plt.tight_layout()
                plt.show()


            def plot_focus_rolling(window_df, focus_ticker, metric_col, sector_col, title):
                if not HAS_MATPLOTLIB:
                    return
                if window_df.empty or metric_col not in window_df.columns:
                    print(f"No data for {metric_col}.")
                    return

                focus_rows = window_df.loc[window_df["ticker"].str.upper().eq(focus_ticker.upper())].sort_values("relative_day")
                if focus_rows.empty:
                    print(f"No focus rows for {focus_ticker}.")
                    return

                sector = focus_rows["sector"].dropna().iloc[0]
                sector_rows = (
                    window_df.loc[window_df["sector"].eq(sector)]
                    .groupby("relative_day", as_index=False)[metric_col]
                    .median()
                    .sort_values("relative_day")
                )

                fig, ax = plt.subplots(figsize=(12, 4.8))
                ax.plot(focus_rows["relative_day"], focus_rows[metric_col], label=focus_ticker, color="#111111", linewidth=2.5)
                if not sector_rows.empty:
                    ax.plot(
                        sector_rows["relative_day"],
                        sector_rows[metric_col],
                        label=f"sector median: {sector}",
                        color="#006BA4",
                        linestyle="--",
                        linewidth=2.0,
                    )
                if sector_col in focus_rows.columns:
                    ax2 = ax.twinx()
                    ax2.plot(
                        focus_rows["relative_day"],
                        focus_rows[sector_col],
                        label=f"{focus_ticker} vs sector",
                        color="#B13A32",
                        alpha=0.45,
                        linewidth=1.5,
                    )
                    ax2.set_ylabel("vs sector")
                ax.axvline(0, color="#222222", linewidth=1.0)
                ax.set_title(title)
                ax.set_xlabel("Trading days relative to anchor")
                ax.legend(loc="upper left")
                plt.tight_layout()
                plt.show()
            """
        ),
        md(
            """
            ## 3. Widok jednej rewizji i otoczenie kandydatow

            `context_role` moze zawierac kilka etykiet naraz, np. spolka moze byc jednoczesnie
            na poprzedniej liscie rezerwowej i w okolicy wagowego progu. `wig_weight_rank`
            oraz `previous_wig_weight_rank` to przyblizenie pozycji w WIG na podstawie wagi,
            a nie oficjalny ranking regulaminowy.
            """
        ),
        code(
            """
            revision_focus, revision_context = build_revision_context(REVISION_DATE, FOCUS_TICKER)

            anchor_date = revision_focus["anchor_date"].dropna().iloc[0]
            previous_revision_date = revision_focus["previous_revision_date"].dropna().iloc[0] if revision_focus["previous_revision_date"].notna().any() else pd.NaT

            display(
                Markdown(
                    f"**Revision:** `{pd.Timestamp(REVISION_DATE).date()}`  |  "
                    f"**Previous:** `{previous_revision_date.date() if pd.notna(previous_revision_date) else None}`  |  "
                    f"**Anchor:** `{pd.Timestamp(anchor_date).date()}`"
                )
            )

            role_summary = (
                revision_context.groupby("primary_role")
                .agg(rows=("isin", "count"), unique_sectors=("sector", "nunique"))
                .reset_index()
                .sort_values("primary_role")
            )
            display(role_summary)

            context_cols = [
                "ticker",
                "isin",
                "sector",
                "previous_index",
                "current_index",
                "previous_wig_weight_rank",
                "wig_weight_rank",
                "weight_pct",
                "context_role",
                "previous_mwig40_reserve_rank",
                "current_mwig40_reserve_rank",
                "ret_m20td",
                "ret_m60td",
                "ret_m120td",
                "ret_m60td_vs_sector",
                "vol_m60td_ann",
                "turnover_ratio_m60td_vs_prev",
                "max_drawdown_m60td",
            ]
            context_cols = [col for col in context_cols if col in revision_context.columns]
            display(format_metric_table(revision_context[context_cols]))
            """
        ),
        code(
            """
            entrants_table = revision_focus.loc[revision_focus["entered_mwig40"]].copy()
            reserve_table = revision_focus.loc[
                revision_focus["previous_mwig40_reserve"] | revision_focus["current_mwig40_reserve"]
            ].copy()
            exits_table = revision_focus.loc[revision_focus["exited_mwig40"]].copy()

            display(Markdown("**Entrants:**"))
            display(
                format_metric_table(
                    entrants_table[
                        [
                            col
                            for col in [
                                "ticker",
                                "sector",
                                "previous_index",
                                "previous_mwig40_reserve",
                                "previous_mwig40_reserve_rank",
                                "previous_wig_weight_rank",
                                "wig_weight_rank",
                                "ret_m20td",
                                "ret_m60td",
                                "ret_m120td",
                                "ret_m60td_vs_sector",
                                "vol_m60td_ann",
                                "avg_turnover_m60td",
                                "turnover_ratio_m60td_vs_prev",
                            ]
                            if col in entrants_table.columns
                        ]
                    ]
                )
            )

            display(Markdown("**Reserve list and near-candidates:**"))
            display(
                format_metric_table(
                    reserve_table[
                        [
                            col
                            for col in [
                                "ticker",
                                "sector",
                                "previous_index",
                                "current_index",
                                "previous_mwig40_reserve_rank",
                                "previous_wig_weight_rank",
                                "current_mwig40_reserve_rank",
                                "wig_weight_rank",
                                "ret_m20td",
                                "ret_m60td",
                                "ret_m120td",
                                "ret_m60td_vs_sector",
                                "vol_m60td_ann",
                                "turnover_ratio_m60td_vs_prev",
                            ]
                            if col in reserve_table.columns
                        ]
                    ].sort_values(["previous_mwig40_reserve_rank", "current_mwig40_reserve_rank", "ticker"], na_position="last")
                )
            )

            if not exits_table.empty:
                display(Markdown("**Exits:**"))
                display(
                    format_metric_table(
                        exits_table[
                            [
                                col
                                for col in [
                                    "ticker",
                                    "sector",
                                    "previous_index",
                                    "current_index",
                                    "previous_wig_weight_rank",
                                    "wig_weight_rank",
                                    "ret_m20td",
                                    "ret_m60td",
                                    "ret_m120td",
                                    "ret_m60td_vs_sector",
                                    "vol_m60td_ann",
                                ]
                                if col in exits_table.columns
                            ]
                        ]
                    )
                )
            """
        ),
        md(
            """
            ## 4. Wykresy dla rewizji

            Normalizacja kursu zalezy od `NORMALIZE_MODE` ustawionego w sekcji parametrów:

            - `NORMALIZE_MODE = "window_start"`: pierwsza widoczna sesja na wykresie = 100,
            - `NORMALIZE_MODE = "target_date"`: anchor/revision trading date = 100.

            Domyslnie uzywamy `"window_start"`, bo dla hipotezy o zachowaniu przed rewizja
            czytelniej pokazuje, ktore spolki narosly najmocniej od poczatku badanego okna.

            Sekcja pokazuje:

            - kursy przed i po anchor,
            - kursy przed i po formalnej rewizji,
            - zwroty, zmiennosc i obrot wzgledem sektora,
            - okna post-anchor i post-rewizja.
            """
        ),
        code(
            """
            anchor_metrics_all = compute_dynamic_metrics(
                price_enriched,
                revision_focus,
                pd.Timestamp(anchor_date),
                pre_windows=PRE_WINDOWS,
                post_windows=POST_ANCHOR_WINDOWS,
                target_label="anchor",
            )
            revision_post_metrics_all = compute_dynamic_metrics(
                price_enriched,
                revision_focus,
                pd.Timestamp(REVISION_DATE),
                pre_windows=[],
                post_windows=POST_REVISION_WINDOWS,
                target_label="revision",
            )

            anchor_context_metrics = revision_context.merge(
                anchor_metrics_all.drop(columns=["ticker", "sector", "macrosector", "industry"], errors="ignore"),
                on="isin",
                how="left",
            )
            revision_post_context_metrics = revision_context.merge(
                revision_post_metrics_all.drop(columns=["ticker", "sector", "macrosector", "industry"], errors="ignore"),
                on="isin",
                how="left",
            )

            pre_cols = ["ticker", "sector", "primary_role", "previous_wig_weight_rank", "wig_weight_rank"]
            for window in WINDOWS_TO_COMPARE:
                pre_cols.extend(
                    [
                        f"ret_m{window}td_to_anchor",
                        f"ret_m{window}td_to_anchor_vs_sector",
                        f"vol_m{window}td_ann_to_anchor",
                        f"vol_m{window}td_ann_to_anchor_vs_sector",
                        f"turnover_ratio_m{window}td_to_anchor",
                        f"turnover_ratio_m{window}td_to_anchor_vs_sector",
                    ]
                )
            pre_cols = [col for col in pre_cols if col in anchor_context_metrics.columns]

            display(Markdown("**Dynamic pre-anchor metrics for context universe:**"))
            display(
                format_metric_table(
                    anchor_context_metrics.sort_values(["role_order", "wig_weight_rank", "ticker"])[pre_cols]
                )
            )
            """
        ),
        code(
            """
            anchor_window = build_relative_window(
                price_enriched,
                revision_context,
                pd.Timestamp(anchor_date),
                pre_days=PLOT_PRE_DAYS,
                post_days=PLOT_POST_ANCHOR_DAYS,
                target_label="anchor",
            )
            revision_window = build_relative_window(
                price_enriched,
                revision_context,
                pd.Timestamp(REVISION_DATE),
                pre_days=PLOT_PRE_DAYS,
                post_days=PLOT_POST_REVISION_DAYS,
                target_label="revision",
            )

            plot_normalized_prices(
                anchor_window,
                revision_context,
                title=f"Normalized close around anchor date {pd.Timestamp(anchor_date).date()}",
            )
            plot_normalized_prices(
                revision_window,
                revision_context,
                title=f"Normalized close around revision date {REVISION_DATE}",
            )
            """
        ),
        code(
            """
            plot_metric_vs_sector_bars(
                anchor_metrics_all,
                revision_context,
                column_template="ret_m{w}td_to_anchor",
                windows=WINDOWS_TO_COMPARE,
                title="Pre-anchor return vs sector median",
                comparison_suffix="_vs_sector",
            )

            plot_metric_vs_sector_bars(
                anchor_metrics_all,
                revision_context,
                column_template="vol_m{w}td_ann_to_anchor",
                windows=WINDOWS_TO_COMPARE,
                title="Pre-anchor realized volatility vs sector median",
                comparison_suffix="_vs_sector",
            )

            plot_metric_vs_sector_bars(
                anchor_metrics_all,
                revision_context,
                column_template="turnover_ratio_m{w}td_to_anchor",
                windows=WINDOWS_TO_COMPARE,
                title="Pre-anchor turnover acceleration vs sector median",
                comparison_suffix="_vs_sector",
            )

            plot_metric_vs_sector_bars(
                anchor_metrics_all,
                revision_context,
                column_template="avg_turnover_m{w}td_to_anchor",
                windows=WINDOWS_TO_COMPARE,
                title="Pre-anchor average turnover relative to sector median",
                comparison_suffix="_rel_sector",
            )
            """
        ),
        code(
            """
            post_anchor_cols = ["ticker", "sector", "primary_role", "previous_wig_weight_rank", "wig_weight_rank"]
            for window in POST_ANCHOR_WINDOWS:
                post_anchor_cols.extend(
                    [
                        f"ret_p{window}td_from_anchor",
                        f"ret_p{window}td_from_anchor_vs_sector",
                        f"vol_p{window}td_ann_from_anchor",
                        f"vol_p{window}td_ann_from_anchor_vs_sector",
                        f"avg_turnover_p{window}td_from_anchor",
                        f"avg_turnover_p{window}td_from_anchor_rel_sector",
                    ]
                )
            post_anchor_cols = [col for col in post_anchor_cols if col in anchor_context_metrics.columns]

            display(Markdown("**Post-anchor windows:**"))
            display(
                format_metric_table(
                    anchor_context_metrics.sort_values(["role_order", "wig_weight_rank", "ticker"])[post_anchor_cols]
                )
            )

            post_revision_cols = ["ticker", "sector", "primary_role", "previous_wig_weight_rank", "wig_weight_rank"]
            for window in POST_REVISION_WINDOWS:
                post_revision_cols.extend(
                    [
                        f"ret_p{window}td_from_revision",
                        f"ret_p{window}td_from_revision_vs_sector",
                        f"vol_p{window}td_ann_from_revision",
                        f"vol_p{window}td_ann_from_revision_vs_sector",
                        f"avg_turnover_p{window}td_from_revision",
                        f"avg_turnover_p{window}td_from_revision_rel_sector",
                    ]
                )
            post_revision_cols = [col for col in post_revision_cols if col in revision_post_context_metrics.columns]

            display(Markdown("**Post-revision windows:**"))
            display(
                format_metric_table(
                    revision_post_context_metrics.sort_values(["role_order", "wig_weight_rank", "ticker"])[post_revision_cols]
                )
            )
            """
        ),
        code(
            """
            for window in POST_ANCHOR_WINDOWS:
                plot_metric_vs_sector_bars(
                    anchor_metrics_all,
                    revision_context,
                    column_template=f"ret_p{window}td_from_anchor".replace(str(window), "{w}", 1),
                    windows=[window],
                    title="Post-anchor return vs sector median",
                    comparison_suffix="_vs_sector",
                )

            for window in POST_REVISION_WINDOWS:
                plot_metric_vs_sector_bars(
                    revision_post_metrics_all,
                    revision_context,
                    column_template=f"ret_p{window}td_from_revision".replace(str(window), "{w}", 1),
                    windows=[window],
                    title="Post-revision return vs sector median",
                    comparison_suffix="_vs_sector",
                )
            """
        ),
        md(
            """
            ## 5. Drilldown po spolce

            `FOCUS_TICKER` steruje ta sekcja. Jezeli `FOCUS_TICKER = None`, notebook wybierze
            pierwsza spolke wchodzaca do mWIG40 w danej rewizji.

            Drilldown pokazuje spolke na tle sektora: kurs, rolling volatility i rolling turnover.
            """
        ),
        code(
            """
            if FOCUS_TICKER:
                effective_focus_ticker = FOCUS_TICKER.upper()
            else:
                candidates = revision_context.loc[revision_context["primary_role"].eq("entered_mwig40"), "ticker"]
                effective_focus_ticker = candidates.iloc[0].upper() if not candidates.empty else revision_context["ticker"].iloc[0].upper()

            focus_row = revision_focus.loc[revision_focus["ticker"].str.upper().eq(effective_focus_ticker)].copy()
            if focus_row.empty:
                display(Markdown(f"No focus row for `{effective_focus_ticker}` in revision `{REVISION_DATE}`."))
            else:
                focus_sector = focus_row["sector"].iloc[0]
                focus_peer_context = revision_focus.loc[revision_focus["sector"].eq(focus_sector)].copy()
                focus_peer_context["context_role"] = "sector_peer"
                focus_peer_context["primary_role"] = "sector_peer"
                focus_peer_context["role_order"] = ROLE_ORDER["sector_peer"]
                focus_peer_context.loc[focus_peer_context["ticker"].str.upper().eq(effective_focus_ticker), "context_role"] = "focus"
                focus_peer_context.loc[focus_peer_context["ticker"].str.upper().eq(effective_focus_ticker), "primary_role"] = "focus"
                focus_peer_context.loc[focus_peer_context["ticker"].str.upper().eq(effective_focus_ticker), "role_order"] = ROLE_ORDER["focus"]
                focus_peer_context["wig_weight_rank"] = focus_peer_context["weight_pct"].rank(method="first", ascending=False).astype("Int64")
                focus_peer_context = (
                    focus_peer_context.sort_values(["role_order", "weight_pct", "ticker"], ascending=[True, False, True])
                    .head(max(PLOT_TOP_N_LINES, int(CONTEXT.get("max_sector_peers_per_sector", 25))))
                    .reset_index(drop=True)
                )

                display(Markdown(f"**Focus:** `{effective_focus_ticker}` | sector: `{focus_sector}`"))
                focus_cols = [
                    col
                    for col in [
                        "ticker",
                        "isin",
                        "sector",
                        "previous_index",
                        "current_index",
                        "entered_mwig40",
                        "previous_mwig40_reserve",
                        "previous_mwig40_reserve_rank",
                        "previous_wig_weight_rank",
                        "current_mwig40_reserve_rank",
                        "wig_weight_rank",
                        "ret_m20td",
                        "ret_m60td",
                        "ret_m120td",
                        "ret_m60td_vs_sector",
                        "vol_m60td_ann",
                        "turnover_ratio_m60td_vs_prev",
                        "max_drawdown_m60td",
                    ]
                    if col in focus_row.columns
                ]
                display(format_metric_table(focus_row[focus_cols]))
            """
        ),
        code(
            """
            if not focus_row.empty:
                focus_window = build_relative_window(
                    price_enriched,
                    focus_peer_context,
                    pd.Timestamp(anchor_date),
                    pre_days=PLOT_PRE_DAYS,
                    post_days=PLOT_POST_ANCHOR_DAYS,
                    target_label="anchor",
                )

                plot_normalized_prices(
                    focus_window,
                    focus_peer_context,
                    title=f"{effective_focus_ticker}: normalized close vs sector around anchor",
                )

                for window in ROLLING_VOL_WINDOWS:
                    metric_col = f"rolling_vol_{window}td_ann"
                    plot_focus_rolling(
                        focus_window,
                        effective_focus_ticker,
                        metric_col=metric_col,
                        sector_col=f"{metric_col}_vs_sector",
                        title=f"{effective_focus_ticker}: rolling volatility {window}td vs sector",
                    )

                for window in ROLLING_TURNOVER_WINDOWS:
                    metric_col = f"rolling_avg_turnover_{window}td"
                    plot_focus_rolling(
                        focus_window,
                        effective_focus_ticker,
                        metric_col=metric_col,
                        sector_col=f"{metric_col}_rel_sector",
                        title=f"{effective_focus_ticker}: rolling average turnover {window}td vs sector",
                    )
            """
        ),
        code(
            """
            if not focus_row.empty:
                focus_anchor_metrics = compute_dynamic_metrics(
                    price_enriched,
                    focus_peer_context,
                    pd.Timestamp(anchor_date),
                    pre_windows=PRE_WINDOWS,
                    post_windows=POST_ANCHOR_WINDOWS,
                    target_label="anchor",
                )
                focus_metric_cols = ["ticker", "sector"]
                for window in WINDOWS_TO_COMPARE:
                    focus_metric_cols.extend(
                        [
                            f"ret_m{window}td_to_anchor",
                            f"ret_m{window}td_to_anchor_vs_sector",
                            f"vol_m{window}td_ann_to_anchor",
                            f"vol_m{window}td_ann_to_anchor_vs_sector",
                            f"avg_turnover_m{window}td_to_anchor_rel_sector",
                            f"turnover_ratio_m{window}td_to_anchor",
                            f"turnover_ratio_m{window}td_to_anchor_vs_sector",
                            f"max_drawdown_m{window}td_to_anchor",
                        ]
                    )
                focus_metric_cols = [col for col in focus_metric_cols if col in focus_anchor_metrics.columns]

                focus_display = focus_anchor_metrics.loc[
                    focus_anchor_metrics["ticker"].str.upper().eq(effective_focus_ticker), focus_metric_cols
                ]
                peer_display = (
                    focus_anchor_metrics.loc[~focus_anchor_metrics["ticker"].str.upper().eq(effective_focus_ticker), focus_metric_cols]
                    .sort_values(f"ret_m{WINDOWS_TO_COMPARE[-1]}td_to_anchor_vs_sector" if f"ret_m{WINDOWS_TO_COMPARE[-1]}td_to_anchor_vs_sector" in focus_metric_cols else "ticker", ascending=False)
                    .head(15)
                )

                display(Markdown("**Focus dynamic metrics:**"))
                display(format_metric_table(focus_display))
                display(Markdown("**Top sector peers by selected long-window return vs sector:**"))
                display(format_metric_table(peer_display))
            """
        ),
        md(
            """
            ## 6. Test hipotezy: wszystkie rewizje 2021-2026

            Testujemy panel `spolka x rewizja`, z targetem `entered_mwig40`.
            Pierwsza rewizja jest wykluczona, bo nie ma poprzedniej rewizji do porownania.

            Wersja predykcyjna nie uzywa `current_mwig40_reserve`. Universe `near_threshold`
            jest budowany tylko z informacji znanych przed rewizja:

            - poprzednia lista rezerwowa mWIG40,
            - poprzednia pozycja wagowa w WIG blisko progow `WEIGHT_RANK_CENTERS`,
            - brak czlonkostwa w mWIG40 w poprzedniej rewizji.

            Statystyki cenowe sa liczone dynamicznie z OHLCV dla `PRIMARY_WINDOWS`.
            """
        ),
        code(
            """
            display(
                Markdown(
                    "**Hypothesis-test config:** "
                    f"`UNIVERSE_MODE={UNIVERSE_MODE}`, "
                    f"`PRIMARY_WINDOWS={PRIMARY_WINDOWS}`, "
                    f"`WEIGHT_RANK_CENTERS={WEIGHT_RANK_CENTERS}`, "
                    f"`WEIGHT_NEIGHBOR_COUNT={WEIGHT_NEIGHBOR_COUNT}`, "
                    f"`USE_CURRENT_RESERVE_AS_FEATURE={USE_CURRENT_RESERVE_AS_FEATURE}`"
                )
            )

            hypothesis_price_enriched = hypothesis_price_panel.sort_values(["isin", "date"]).copy()
            hypothesis_price_enriched["turnover"] = hypothesis_price_enriched["close"] * hypothesis_price_enriched["volume"]
            hypothesis_price_enriched["return_1d"] = hypothesis_price_enriched.groupby("isin")["close"].pct_change()

            display(
                pd.DataFrame(
                    [
                        {
                            "source": HYPOTHESIS_PRICE_SOURCE,
                            "rows": len(hypothesis_price_enriched),
                            "unique_isins": hypothesis_price_enriched["isin"].nunique(),
                            "date_min": hypothesis_price_enriched["date"].min().date(),
                            "date_max": hypothesis_price_enriched["date"].max().date(),
                        }
                    ]
                )
            )
            """
        ),
        code(
            """
            def add_cross_revision_rank_features(panel):
                frames = []
                rank_maps = {}
                for revision_date, group in panel.groupby("revision_date", sort=True):
                    ranked = group.copy()
                    ranked["wig_weight_rank"] = (
                        ranked["weight_pct"].rank(method="first", ascending=False).astype("Int64")
                        if "weight_pct" in ranked.columns
                        else pd.Series(pd.NA, index=ranked.index, dtype="Int64")
                    )
                    rank_maps[pd.Timestamp(revision_date)] = ranked.set_index("isin")["wig_weight_rank"]
                    frames.append(ranked)

                out = pd.concat(frames, ignore_index=True)
                out["previous_wig_weight_rank"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
                for revision_date, idx in out.groupby("revision_date").groups.items():
                    previous_values = out.loc[idx, "previous_revision_date"].dropna()
                    if previous_values.empty:
                        continue
                    previous_revision = pd.Timestamp(previous_values.iloc[0])
                    previous_rank_map = rank_maps.get(previous_revision)
                    if previous_rank_map is None:
                        continue
                    out.loc[idx, "previous_wig_weight_rank"] = out.loc[idx, "isin"].map(previous_rank_map).astype("Int64")
                return out


            def previous_weight_neighbor_mask(df):
                mask = pd.Series(False, index=df.index)
                previous_rank = df["previous_wig_weight_rank"]
                for center in WEIGHT_RANK_CENTERS:
                    mask = mask | previous_rank.between(center - WEIGHT_NEIGHBOR_COUNT, center + WEIGHT_NEIGHBOR_COUNT)
                return mask.fillna(False)


            def build_predictive_universe_mask(df):
                known_before_revision = df["has_previous_revision"].fillna(False) & ~df["was_in_previous_mwig40"].fillna(False)
                if UNIVERSE_MODE == "all_wig_candidates":
                    return known_before_revision
                if UNIVERSE_MODE == "near_threshold":
                    return known_before_revision & (
                        df["previous_mwig40_reserve"].fillna(False) | previous_weight_neighbor_mask(df)
                    )
                raise ValueError(f"Unsupported UNIVERSE_MODE: {UNIVERSE_MODE}")


            def compute_cross_revision_anchor_metrics(ranked_panel):
                parts = []
                for revision_date, group in ranked_panel.groupby("revision_date", sort=True):
                    if not bool(group["has_previous_revision"].iloc[0]):
                        continue
                    anchor_values = group["anchor_date"].dropna()
                    if anchor_values.empty:
                        continue
                    metrics = compute_dynamic_metrics(
                        hypothesis_price_enriched,
                        group,
                        pd.Timestamp(anchor_values.iloc[0]),
                        pre_windows=PRIMARY_WINDOWS,
                        post_windows=[],
                        target_label="anchor",
                    )
                    metrics["revision_date"] = pd.Timestamp(revision_date)
                    parts.append(metrics)
                return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


            ranked_event_panel = add_cross_revision_rank_features(event_panel)
            cross_revision_metrics = compute_cross_revision_anchor_metrics(ranked_event_panel)

            metric_merge_cols = ["revision_date", "isin"]
            metric_payload = cross_revision_metrics.drop(
                columns=["ticker", "sector", "macrosector", "industry"],
                errors="ignore",
            )
            hypothesis_all = ranked_event_panel.merge(metric_payload, on=metric_merge_cols, how="left")
            hypothesis_all["predictive_universe"] = build_predictive_universe_mask(hypothesis_all)
            hypothesis_panel = hypothesis_all.loc[hypothesis_all["predictive_universe"]].copy()

            total_entrants = int(hypothesis_all.loc[hypothesis_all["has_previous_revision"], "entered_mwig40"].sum())
            covered_entrants = int(hypothesis_panel["entered_mwig40"].sum())
            coverage_summary = pd.DataFrame(
                [
                    {
                        "universe_mode": UNIVERSE_MODE,
                        "rows": len(hypothesis_panel),
                        "revision_count": hypothesis_panel["revision_date"].nunique(),
                        "unique_isins": hypothesis_panel["isin"].nunique(),
                        "entrants_in_universe": covered_entrants,
                        "all_entrants_after_baseline": total_entrants,
                        "entrant_coverage": covered_entrants / total_entrants if total_entrants else np.nan,
                        "base_entry_rate_in_universe": hypothesis_panel["entered_mwig40"].mean(),
                    }
                ]
            )
            display(coverage_summary)

            display(Markdown("**Entrants not covered by predictive universe:**"))
            missed_entrants = hypothesis_all.loc[
                hypothesis_all["has_previous_revision"]
                & hypothesis_all["entered_mwig40"]
                & ~hypothesis_all["predictive_universe"],
                [
                    "revision_date",
                    "ticker",
                    "sector",
                    "previous_index",
                    "previous_mwig40_reserve",
                    "previous_mwig40_reserve_rank",
                    "previous_wig_weight_rank",
                    "wig_weight_rank",
                ],
            ].sort_values(["revision_date", "ticker"])
            display(format_metric_table(missed_entrants))
            """
        ),
        code(
            """
            predictor_metric_specs = []
            for window in PRIMARY_WINDOWS:
                predictor_metric_specs.extend(
                    [
                        (f"ret_m{window}td_to_anchor_vs_sector", "high"),
                        (f"vol_m{window}td_ann_to_anchor_vs_sector", "high"),
                        (f"avg_turnover_m{window}td_to_anchor_rel_sector", "high"),
                        (f"turnover_ratio_m{window}td_to_anchor_vs_sector", "high"),
                        (f"max_drawdown_m{window}td_to_anchor_vs_sector", "high"),
                    ]
                )
            predictor_metric_specs = [
                (col, direction)
                for col, direction in predictor_metric_specs
                if col in hypothesis_panel.columns
            ]
            predictor_metric_cols = [col for col, _ in predictor_metric_specs]

            def summarize_predictors(panel, metric_cols):
                rows = []
                for col in metric_cols:
                    valid = panel.loc[panel[col].notna()].copy()
                    entrants = valid.loc[valid["entered_mwig40"]]
                    others = valid.loc[~valid["entered_mwig40"]]
                    rows.append(
                        {
                            "metric": col,
                            "n": len(valid),
                            "entrants_n": len(entrants),
                            "non_entrants_n": len(others),
                            "entrant_median": entrants[col].median(),
                            "non_entrant_median": others[col].median(),
                            "median_diff": entrants[col].median() - others[col].median(),
                            "entrant_mean": entrants[col].mean(),
                            "non_entrant_mean": others[col].mean(),
                            "mean_diff": entrants[col].mean() - others[col].mean(),
                        }
                    )
                return pd.DataFrame(rows)

            predictor_summary = summarize_predictors(hypothesis_panel, predictor_metric_cols)
            display(Markdown("**Entrants vs non-entrants: predictor distributions**"))
            display(format_metric_table(predictor_summary.sort_values("median_diff", ascending=False)))
            """
        ),
        code(
            """
            def top_percentile_lift(panel, metric_specs, percentiles):
                rows = []
                for metric, direction in metric_specs:
                    for percentile in percentiles:
                        selected_parts = []
                        valid_parts = []
                        for revision_date, group in panel.groupby("revision_date", sort=True):
                            valid = group.loc[group[metric].notna()].copy()
                            if valid.empty:
                                continue
                            n_select = max(1, int(math.ceil(len(valid) * percentile)))
                            selected = (
                                valid.nlargest(n_select, metric)
                                if direction == "high"
                                else valid.nsmallest(n_select, metric)
                            )
                            selected_parts.append(selected)
                            valid_parts.append(valid)
                        if not valid_parts:
                            continue
                        selected_all = pd.concat(selected_parts, ignore_index=True)
                        valid_all = pd.concat(valid_parts, ignore_index=True)
                        selected_rows = len(selected_all)
                        selected_entrants = int(selected_all["entered_mwig40"].sum())
                        available_rows = len(valid_all)
                        available_entrants = int(valid_all["entered_mwig40"].sum())
                        precision = selected_entrants / selected_rows if selected_rows else np.nan
                        recall = selected_entrants / available_entrants if available_entrants else np.nan
                        baseline = available_entrants / available_rows if available_rows else np.nan
                        rows.append(
                            {
                                "metric": metric,
                                "top_percentile": percentile,
                                "selected_rows": selected_rows,
                                "selected_entrants": selected_entrants,
                                "available_entrants": available_entrants,
                                "precision": precision,
                                "recall": recall,
                                "baseline_rate": baseline,
                                "lift": precision / baseline if baseline else np.nan,
                            }
                        )
                return pd.DataFrame(rows)

            lift_table = top_percentile_lift(hypothesis_panel, predictor_metric_specs, TOP_PERCENTILES)
            display(Markdown("**Hit-rate / lift for top-percentile rules by revision**"))
            display(
                format_metric_table(
                    lift_table.sort_values(["lift", "recall", "selected_entrants"], ascending=[False, False, False]).head(40)
                )
            )
            """
        ),
        code(
            """
            def add_top_flag_by_revision(panel, metric, percentile, flag_name, direction="high"):
                out = pd.Series(False, index=panel.index)
                for revision_date, group in panel.groupby("revision_date", sort=True):
                    valid = group.loc[group[metric].notna()].copy()
                    if valid.empty:
                        continue
                    n_select = max(1, int(math.ceil(len(valid) * percentile)))
                    selected_idx = (
                        valid.nlargest(n_select, metric).index
                        if direction == "high"
                        else valid.nsmallest(n_select, metric).index
                    )
                    out.loc[selected_idx] = True
                panel[flag_name] = out
                return panel


            score_panel = hypothesis_panel.copy()
            scoring_features = {
                "top_momentum": f"ret_m{SCORING_WINDOW}td_to_anchor_vs_sector",
                "top_turnover_accel": f"turnover_ratio_m{SCORING_WINDOW}td_to_anchor_vs_sector",
                "top_volatility": f"vol_m{SCORING_WINDOW}td_ann_to_anchor_vs_sector",
            }
            for flag, metric in scoring_features.items():
                if metric in score_panel.columns:
                    score_panel = add_top_flag_by_revision(score_panel, metric, SCORING_TOP_PERCENTILE, flag, "high")
                else:
                    score_panel[flag] = False

            score_panel["score_previous_reserve"] = score_panel["previous_mwig40_reserve"].fillna(False)
            score_panel["hypothesis_score"] = (
                score_panel["score_previous_reserve"].astype(int)
                + score_panel["top_momentum"].astype(int)
                + score_panel["top_turnover_accel"].astype(int)
                + score_panel["top_volatility"].astype(int)
            )

            total_entrants_in_score = int(score_panel["entered_mwig40"].sum())
            baseline_score_rate = score_panel["entered_mwig40"].mean()
            score_rows = []
            for min_score in range(1, 5):
                selected = score_panel.loc[score_panel["hypothesis_score"].ge(min_score)]
                selected_rows = len(selected)
                selected_entrants = int(selected["entered_mwig40"].sum())
                score_rows.append(
                    {
                        "rule": f"hypothesis_score >= {min_score}",
                        "selected_rows": selected_rows,
                        "selected_entrants": selected_entrants,
                        "available_entrants": total_entrants_in_score,
                        "precision": selected_entrants / selected_rows if selected_rows else np.nan,
                        "recall": selected_entrants / total_entrants_in_score if total_entrants_in_score else np.nan,
                        "baseline_rate": baseline_score_rate,
                        "lift": (selected_entrants / selected_rows) / baseline_score_rate
                        if selected_rows and baseline_score_rate
                        else np.nan,
                    }
                )

            score_summary = pd.DataFrame(score_rows)
            display(Markdown("**Simple rule score: previous reserve + top momentum + top turnover + top volatility**"))
            display(format_metric_table(score_summary))

            display(Markdown("**Highest scoring candidates**"))
            candidate_cols = [
                "revision_date",
                "ticker",
                "sector",
                "entered_mwig40",
                "previous_index",
                "previous_mwig40_reserve",
                "previous_mwig40_reserve_rank",
                "previous_wig_weight_rank",
                "wig_weight_rank",
                "hypothesis_score",
                "top_momentum",
                "top_turnover_accel",
                "top_volatility",
                f"ret_m{SCORING_WINDOW}td_to_anchor_vs_sector",
                f"turnover_ratio_m{SCORING_WINDOW}td_to_anchor_vs_sector",
                f"vol_m{SCORING_WINDOW}td_ann_to_anchor_vs_sector",
            ]
            candidate_cols = [col for col in candidate_cols if col in score_panel.columns]
            display(
                format_metric_table(
                    score_panel[candidate_cols]
                    .sort_values(["hypothesis_score", "entered_mwig40", f"ret_m{SCORING_WINDOW}td_to_anchor_vs_sector"], ascending=[False, False, False])
                    .head(50)
                )
            )
            """
        ),
        code(
            """
            sector_metric_cols = [
                f"ret_m{SCORING_WINDOW}td_to_anchor_vs_sector",
                f"turnover_ratio_m{SCORING_WINDOW}td_to_anchor_vs_sector",
                f"vol_m{SCORING_WINDOW}td_ann_to_anchor_vs_sector",
            ]
            sector_metric_cols = [col for col in sector_metric_cols if col in hypothesis_panel.columns]
            sector_agg = {
                "isin": "count",
                "entered_mwig40": "sum",
            }
            for col in sector_metric_cols:
                sector_agg[col] = "median"

            sector_summary = (
                hypothesis_panel.groupby("sector", dropna=False)
                .agg(sector_agg)
                .rename(columns={"isin": "candidate_rows", "entered_mwig40": "entrants"})
                .reset_index()
            )
            sector_summary["entry_rate"] = sector_summary["entrants"] / sector_summary["candidate_rows"]
            display(Markdown("**Sector summary in predictive universe**"))
            display(format_metric_table(sector_summary.sort_values(["entrants", "entry_rate"], ascending=[False, False])))

            def plot_pivot_heatmap(pivot, title, cmap="Blues"):
                if not HAS_MATPLOTLIB or pivot.empty:
                    return
                fig_width = max(10, 0.45 * len(pivot.columns))
                fig_height = max(4, 0.35 * len(pivot.index))
                fig, ax = plt.subplots(figsize=(fig_width, fig_height))
                data = pivot.fillna(0).to_numpy()
                im = ax.imshow(data, aspect="auto", cmap=cmap)
                ax.set_xticks(np.arange(len(pivot.columns)))
                ax.set_xticklabels([str(c)[:10] for c in pivot.columns], rotation=45, ha="right")
                ax.set_yticks(np.arange(len(pivot.index)))
                ax.set_yticklabels(pivot.index)
                ax.set_title(title)
                fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
                plt.tight_layout()
                plt.show()

            top_sectors = (
                hypothesis_panel.groupby("sector")["entered_mwig40"]
                .sum()
                .sort_values(ascending=False)
                .head(18)
                .index
            )
            entrants_heatmap = (
                hypothesis_panel.loc[hypothesis_panel["sector"].isin(top_sectors)]
                .pivot_table(index="sector", columns="revision_date", values="entered_mwig40", aggfunc="sum")
                .sort_index()
            )
            plot_pivot_heatmap(entrants_heatmap, "Entrants by sector and revision", cmap="Blues")

            momentum_col = f"ret_m{SCORING_WINDOW}td_to_anchor_vs_sector"
            if momentum_col in hypothesis_panel.columns:
                momentum_heatmap = (
                    hypothesis_panel.loc[hypothesis_panel["sector"].isin(top_sectors)]
                    .pivot_table(index="sector", columns="revision_date", values=momentum_col, aggfunc="median")
                    .sort_index()
                )
                plot_pivot_heatmap(momentum_heatmap, f"Median {momentum_col} by sector and revision", cmap="RdYlGn")
            """
        ),
        md(
            """
            ## 7. Efekt po ogloszeniu rewizji

            Ta sekcja odpowiada na pytanie: co dzieje sie z wycena spolek po fakcie,
            czyli po `revision_date`. Domyslnie liczymy reakcje w oknach:

            `POST_FACT_WINDOWS = [1, 3, 7, 14, 30, 60, 120]`

            Metryki sa liczone od ostatniej sesji `<= revision_date` do kolejnych sesji
            w przyszlosci. Dla najnowszych rewizji dlugie okna moga byc puste, jezeli
            nie ma jeszcze wystarczajacej historii po rewizji.

            Dodatkowo porownujemy reakcje entrantow z top `POST_FACT_SECTOR_TOP_PERCENTILE`
            spolek z tego samego sektora. Referencja top-sector jest liczona per
            rewizja, sektor i okno, z wykluczeniem samej analizowanej spolki.
            """
        ),
        code(
            """
            def add_sector_top_percentile_reference(panel, windows, percentile):
                out = panel.copy()
                for window in windows:
                    ret_col = f"ret_p{window}td_from_revision"
                    if ret_col not in out.columns:
                        continue
                    ref_col = f"{ret_col}_sector_top{int(percentile * 100)}_median"
                    diff_col = f"{ret_col}_vs_sector_top{int(percentile * 100)}"
                    out[ref_col] = np.nan

                    for (_, sector), idx in out.groupby(["revision_date", "sector"], dropna=False).groups.items():
                        values = out.loc[idx, ret_col]
                        for row_idx in idx:
                            peer_values = values.drop(index=row_idx).dropna()
                            if peer_values.empty:
                                continue
                            n_top = max(1, int(math.ceil(len(peer_values) * percentile)))
                            out.at[row_idx, ref_col] = peer_values.nlargest(n_top).median()

                    out[diff_col] = out[ret_col] - out[ref_col]
                return out


            def compute_post_fact_metrics(panel):
                parts = []
                for revision_date, group in panel.groupby("revision_date", sort=True):
                    if not bool(group["has_previous_revision"].iloc[0]):
                        continue
                    metrics = compute_dynamic_metrics(
                        hypothesis_price_enriched,
                        group,
                        pd.Timestamp(revision_date),
                        pre_windows=[],
                        post_windows=POST_FACT_WINDOWS,
                        target_label="revision",
                    )
                    metrics["revision_date"] = pd.Timestamp(revision_date)
                    parts.append(metrics)
                return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


            post_fact_metrics = compute_post_fact_metrics(ranked_event_panel)
            post_payload = post_fact_metrics.drop(columns=["ticker", "sector", "macrosector", "industry"], errors="ignore")
            post_fact_all = ranked_event_panel.merge(post_payload, on=["revision_date", "isin"], how="left")
            post_fact_all = add_sector_top_percentile_reference(
                post_fact_all,
                POST_FACT_WINDOWS,
                POST_FACT_SECTOR_TOP_PERCENTILE,
            )
            post_fact_panel = post_fact_all.loc[
                post_fact_all["has_previous_revision"].fillna(False)
                & post_fact_all["is_in_current_mwig40"].fillna(False)
            ].copy()

            post_fact_panel["post_fact_group"] = np.select(
                [
                    post_fact_panel["entered_mwig40"].fillna(False),
                    post_fact_panel["was_in_previous_mwig40"].fillna(False) & post_fact_panel["is_in_current_mwig40"].fillna(False),
                ],
                ["entrant", "incumbent_mwig40"],
                default="other_current_mwig40",
            )

            display(
                pd.DataFrame(
                    [
                        {
                            "rows": len(post_fact_panel),
                            "revision_count": post_fact_panel["revision_date"].nunique(),
                            "entrants": int(post_fact_panel["entered_mwig40"].sum()),
                            "incumbents": int(post_fact_panel["post_fact_group"].eq("incumbent_mwig40").sum()),
                            "windows": POST_FACT_WINDOWS,
                        }
                    ]
                )
            )
            """
        ),
        code(
            """
            post_summary_rows = []
            sector_top_suffix = f"top{int(POST_FACT_SECTOR_TOP_PERCENTILE * 100)}"
            for window in POST_FACT_WINDOWS:
                ret_col = f"ret_p{window}td_from_revision"
                ret_vs_col = f"{ret_col}_vs_sector"
                ret_top_ref_col = f"{ret_col}_sector_{sector_top_suffix}_median"
                ret_vs_top_col = f"{ret_col}_vs_sector_{sector_top_suffix}"
                vol_col = f"vol_p{window}td_ann_from_revision"
                turnover_col = f"avg_turnover_p{window}td_from_revision_rel_sector"
                if ret_col not in post_fact_panel.columns:
                    continue

                valid = post_fact_panel.loc[post_fact_panel[ret_col].notna()].copy()
                entrants = valid.loc[valid["post_fact_group"].eq("entrant")]
                incumbents = valid.loc[valid["post_fact_group"].eq("incumbent_mwig40")]
                post_summary_rows.append(
                    {
                        "window_td": window,
                        "valid_rows": len(valid),
                        "entrant_n": len(entrants),
                        "incumbent_n": len(incumbents),
                        "entrant_median_return": entrants[ret_col].median(),
                        "incumbent_median_return": incumbents[ret_col].median(),
                        "entrant_minus_incumbent_median": entrants[ret_col].median() - incumbents[ret_col].median(),
                        "entrant_mean_return": entrants[ret_col].mean(),
                        "incumbent_mean_return": incumbents[ret_col].mean(),
                        "entrant_median_return_vs_sector": entrants[ret_vs_col].median() if ret_vs_col in valid.columns else np.nan,
                        f"entrant_median_return_vs_sector_{sector_top_suffix}": entrants[ret_vs_top_col].median()
                        if ret_vs_top_col in valid.columns
                        else np.nan,
                        f"sector_{sector_top_suffix}_median_return": entrants[ret_top_ref_col].median()
                        if ret_top_ref_col in valid.columns
                        else np.nan,
                        "entrant_median_vol": entrants[vol_col].median() if vol_col in valid.columns else np.nan,
                        "entrant_median_turnover_rel_sector": entrants[turnover_col].median() if turnover_col in valid.columns else np.nan,
                        "positive_entrant_share": entrants[ret_col].gt(0).mean() if len(entrants) else np.nan,
                    }
                )

            post_fact_summary = pd.DataFrame(post_summary_rows)
            display(Markdown("**Post-revision returns: entrants vs existing mWIG40 members**"))
            display(format_metric_table(post_fact_summary))
            """
        ),
        code(
            """
            entrant_post_cols = [
                "revision_date",
                "ticker",
                "sector",
                "previous_index",
                "previous_mwig40_reserve",
                "previous_mwig40_reserve_rank",
                "previous_wig_weight_rank",
                "wig_weight_rank",
            ]
            for window in POST_FACT_WINDOWS:
                entrant_post_cols.extend(
                    [
                        f"ret_p{window}td_from_revision",
                        f"ret_p{window}td_from_revision_vs_sector",
                        f"ret_p{window}td_from_revision_vs_sector_top{int(POST_FACT_SECTOR_TOP_PERCENTILE * 100)}",
                        f"vol_p{window}td_ann_from_revision",
                    ]
                )
            entrant_post_cols = [col for col in entrant_post_cols if col in post_fact_panel.columns]

            entrants_post_fact = (
                post_fact_panel.loc[post_fact_panel["entered_mwig40"], entrant_post_cols]
                .sort_values(["revision_date", "ticker"])
                .reset_index(drop=True)
            )
            display(Markdown("**Entrants: post-revision reaction by window**"))
            display(format_metric_table(entrants_post_fact))
            """
        ),
        code(
            """
            if HAS_MATPLOTLIB and not post_fact_summary.empty:
                fig, ax = plt.subplots(figsize=(11, 5.5))
                x = np.arange(len(post_fact_summary))
                width = 0.38
                ax.bar(
                    x - width / 2,
                    post_fact_summary["entrant_median_return"],
                    width,
                    label="Entrants",
                    color="#006BA4",
                    alpha=0.85,
                )
                ax.bar(
                    x + width / 2,
                    post_fact_summary["incumbent_median_return"],
                    width,
                    label="Incumbent mWIG40",
                    color="#8C8C8C",
                    alpha=0.85,
                )
                ax.axhline(0, color="#222222", linewidth=1.0)
                ax.set_xticks(x)
                ax.set_xticklabels(post_fact_summary["window_td"].astype(str))
                ax.set_xlabel("Trading days after revision date")
                ax.set_ylabel("Median return")
                ax.set_title("Post-revision median return: entrants vs incumbent mWIG40")
                ax.legend()
                plt.tight_layout()
                plt.show()

                fig, ax = plt.subplots(figsize=(11, 5.5))
                top_col = f"entrant_median_return_vs_sector_top{int(POST_FACT_SECTOR_TOP_PERCENTILE * 100)}"
                ax.plot(
                    post_fact_summary["window_td"],
                    post_fact_summary["entrant_median_return_vs_sector"],
                    marker="o",
                    color="#006BA4",
                    linewidth=2.2,
                    label="vs sector median",
                )
                if top_col in post_fact_summary.columns:
                    ax.plot(
                        post_fact_summary["window_td"],
                        post_fact_summary[top_col],
                        marker="o",
                        color="#B13A32",
                        linewidth=2.2,
                        label=f"vs sector top {int(POST_FACT_SECTOR_TOP_PERCENTILE * 100)}% median",
                    )
                ax.axhline(0, color="#222222", linewidth=1.0)
                ax.set_xscale("log")
                ax.set_xticks(post_fact_summary["window_td"])
                ax.set_xticklabels(post_fact_summary["window_td"].astype(str))
                ax.set_xlabel("Trading days after revision date")
                ax.set_ylabel("Entrant return vs sector reference")
                ax.set_title("Post-revision entrant return vs sector references")
                ax.legend()
                plt.tight_layout()
                plt.show()
            """
        ),
        code(
            """
            post_sector_rows = []
            for window in POST_FACT_WINDOWS:
                ret_col = f"ret_p{window}td_from_revision"
                ret_vs_col = f"{ret_col}_vs_sector"
                ret_vs_top_col = f"{ret_col}_vs_sector_top{int(POST_FACT_SECTOR_TOP_PERCENTILE * 100)}"
                if ret_col not in post_fact_panel.columns:
                    continue
                entrant_rows = post_fact_panel.loc[post_fact_panel["entered_mwig40"] & post_fact_panel[ret_col].notna()]
                if entrant_rows.empty:
                    continue
                sector_part = (
                    entrant_rows.groupby("sector")
                    .agg(
                        entrant_n=("isin", "count"),
                        median_return=(ret_col, "median"),
                        mean_return=(ret_col, "mean"),
                        median_return_vs_sector=(ret_vs_col, "median") if ret_vs_col in entrant_rows.columns else (ret_col, "median"),
                        median_return_vs_sector_top10=(ret_vs_top_col, "median")
                        if ret_vs_top_col in entrant_rows.columns
                        else (ret_col, "median"),
                        positive_share=(ret_col, lambda s: s.gt(0).mean()),
                    )
                    .reset_index()
                )
                sector_part["window_td"] = window
                post_sector_rows.append(sector_part)

            post_fact_sector_summary = (
                pd.concat(post_sector_rows, ignore_index=True)
                if post_sector_rows
                else pd.DataFrame()
            )

            display(Markdown("**Sector view: entrant post-revision reaction**"))
            display(
                format_metric_table(
                    post_fact_sector_summary.sort_values(["window_td", "entrant_n", "median_return_vs_sector"], ascending=[True, False, False])
                )
            )

            if HAS_MATPLOTLIB and not post_fact_sector_summary.empty:
                selected_window = 30 if 30 in POST_FACT_WINDOWS else POST_FACT_WINDOWS[min(len(POST_FACT_WINDOWS) - 1, 0)]
                sector_plot = post_fact_sector_summary.loc[
                    post_fact_sector_summary["window_td"].eq(selected_window)
                ].sort_values("median_return_vs_sector_top10")
                if not sector_plot.empty:
                    fig, ax = plt.subplots(figsize=(11, max(4, 0.35 * len(sector_plot))))
                    ax.barh(sector_plot["sector"], sector_plot["median_return_vs_sector_top10"], color="#006BA4", alpha=0.85)
                    ax.axvline(0, color="#222222", linewidth=1.0)
                    ax.set_title(f"Entrant post-revision return vs sector top 10% median, {selected_window}td")
                    ax.set_xlabel("Median return vs sector top 10%")
                    plt.tight_layout()
                    plt.show()
            """
        ),
    ]

    nb = nbf.v4.new_notebook()
    nb["cells"] = cells
    nb["metadata"] = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "pygments_lexer": "ipython3",
        },
    }
    return nb


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    notebook = build_notebook()
    nbf.write(notebook, args.output)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
