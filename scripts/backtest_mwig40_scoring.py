from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.errors import PerformanceWarning


ROOT = Path(__file__).resolve().parents[1]
EDA_DIR = ROOT / "output" / "eda"
FULL_OHLCV_PATH = ROOT / "output" / "eda_2021_2026_revision" / "wigeda_2021_2026_ohlcv.parquet"
OUT_DIR = ROOT / "output" / "backtests"

EVENT_PANEL_PATH = EDA_DIR / "mwig40_event_panel.parquet"
PRICE_PANEL_PATH = EDA_DIR / "mwig40_price_panel.parquet"

WINDOWS = [20, 60, 120, 180, 240, 300, 360, 420, 480, 540, 600]
SCORE_THRESHOLDS = [3, 4]
EXIT_RANKS = [80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 30]

SCORING_TOP_PERCENTILE = 0.20
WEIGHT_RANK_CENTERS = [15, 70]
WEIGHT_NEIGHBOR_COUNT = 10

TRADING_DAYS_PER_YEAR = 252

warnings.filterwarnings("ignore", category=PerformanceWarning)


@dataclass(frozen=True)
class PriceAtDate:
    date: pd.Timestamp
    close: float


def max_drawdown(values: pd.Series) -> float:
    if values.empty:
        return np.nan
    return float((values / values.cummax() - 1.0).min())


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    event_panel = pd.read_parquet(EVENT_PANEL_PATH)
    for col in ["revision_date", "previous_revision_date", "anchor_date", "anchor_trading_date"]:
        if col in event_panel.columns:
            event_panel[col] = pd.to_datetime(event_panel[col], errors="coerce")

    price_path = FULL_OHLCV_PATH if FULL_OHLCV_PATH.exists() else PRICE_PANEL_PATH
    prices = pd.read_parquet(price_path)
    prices["date"] = pd.to_datetime(prices["date"], errors="coerce")
    prices = prices.dropna(subset=["isin", "date", "close"]).copy()
    prices["turnover"] = prices["close"] * prices["volume"].fillna(0.0)
    prices = prices.sort_values(["isin", "date"]).reset_index(drop=True)
    prices["return_1d"] = prices.groupby("isin")["close"].pct_change()
    return event_panel, prices


def add_cross_revision_rank_features(panel: pd.DataFrame) -> pd.DataFrame:
    frames = []
    rank_maps: dict[pd.Timestamp, pd.Series] = {}
    for revision_date, group in panel.groupby("revision_date", sort=True):
        ranked = group.copy()
        ranked["wig_weight_rank"] = ranked["weight_pct"].rank(method="first", ascending=False).astype("Int64")
        rank_maps[pd.Timestamp(revision_date)] = ranked.set_index("isin")["wig_weight_rank"]
        frames.append(ranked)

    out = pd.concat(frames, ignore_index=True)
    out["previous_wig_weight_rank"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    for revision_date, idx in out.groupby("revision_date").groups.items():
        previous_values = out.loc[idx, "previous_revision_date"].dropna()
        if previous_values.empty:
            continue
        previous_rank_map = rank_maps.get(pd.Timestamp(previous_values.iloc[0]))
        if previous_rank_map is None:
            continue
        out.loc[idx, "previous_wig_weight_rank"] = out.loc[idx, "isin"].map(previous_rank_map).astype("Int64")
    return out


def previous_weight_neighbor_mask(df: pd.DataFrame) -> pd.Series:
    mask = pd.Series(False, index=df.index)
    previous_rank = df["previous_wig_weight_rank"]
    for center in WEIGHT_RANK_CENTERS:
        mask = mask | previous_rank.between(center - WEIGHT_NEIGHBOR_COUNT, center + WEIGHT_NEIGHBOR_COUNT)
    return mask.fillna(False)


def predictive_universe_mask(df: pd.DataFrame) -> pd.Series:
    known_before_revision = df["has_previous_revision"].fillna(False) & ~df["was_in_previous_mwig40"].fillna(False)
    return known_before_revision & (
        df["previous_mwig40_reserve"].fillna(False) | previous_weight_neighbor_mask(df)
    )


def build_price_groups(prices: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        isin: group.sort_values("date").reset_index(drop=True)
        for isin, group in prices.groupby("isin", sort=False)
    }


def price_on_or_before(group: pd.DataFrame, target_date: pd.Timestamp) -> PriceAtDate | None:
    idx = group["date"].searchsorted(pd.Timestamp(target_date), side="right") - 1
    if idx < 0:
        return None
    row = group.loc[idx]
    return PriceAtDate(pd.Timestamp(row["date"]), float(row["close"]))


def compute_anchor_metrics(
    ranked_panel: pd.DataFrame,
    prices: pd.DataFrame,
    windows: list[int],
) -> pd.DataFrame:
    groups = build_price_groups(prices)
    rows = []
    metric_base_cols = []
    for window in windows:
        metric_base_cols.extend(
            [
                f"ret_m{window}td_to_anchor",
                f"vol_m{window}td_ann_to_anchor",
                f"avg_turnover_m{window}td_to_anchor",
                f"turnover_ratio_m{window}td_to_anchor",
            ]
        )

    eligible = ranked_panel.loc[ranked_panel["has_previous_revision"].fillna(False)].copy()
    for item in eligible.itertuples(index=False):
        row = {
            "revision_date": pd.Timestamp(item.revision_date),
            "isin": item.isin,
            "anchor_target_date": pd.Timestamp(item.anchor_date),
        }
        group = groups.get(item.isin)
        if group is None or group.empty or pd.isna(item.anchor_date):
            for col in metric_base_cols:
                row[col] = np.nan
            row["anchor_target_trading_date"] = pd.NaT
            row["anchor_close"] = np.nan
            rows.append(row)
            continue

        idx = group["date"].searchsorted(pd.Timestamp(item.anchor_date), side="right") - 1
        if idx < 0:
            for col in metric_base_cols:
                row[col] = np.nan
            row["anchor_target_trading_date"] = pd.NaT
            row["anchor_close"] = np.nan
            rows.append(row)
            continue

        row["anchor_target_trading_date"] = pd.Timestamp(group.loc[idx, "date"])
        row["anchor_close"] = float(group.loc[idx, "close"])
        for window in windows:
            start_idx = idx - window
            ret_col = f"ret_m{window}td_to_anchor"
            vol_col = f"vol_m{window}td_ann_to_anchor"
            avg_turnover_col = f"avg_turnover_m{window}td_to_anchor"
            turnover_ratio_col = f"turnover_ratio_m{window}td_to_anchor"
            if start_idx < 0:
                row[ret_col] = np.nan
                row[vol_col] = np.nan
                row[avg_turnover_col] = np.nan
                row[turnover_ratio_col] = np.nan
                continue

            segment = group.iloc[start_idx : idx + 1]
            returns = segment["return_1d"].replace([np.inf, -np.inf], np.nan).dropna()
            avg_turnover = float(segment["turnover"].mean())
            row[ret_col] = float(group.loc[idx, "close"] / group.loc[start_idx, "close"] - 1.0)
            row[vol_col] = float(returns.std(ddof=0) * math.sqrt(TRADING_DAYS_PER_YEAR)) if len(returns) > 1 else np.nan
            row[avg_turnover_col] = avg_turnover

            prev_start_idx = start_idx - window
            if prev_start_idx >= 0:
                previous_turnover = float(group.iloc[prev_start_idx:start_idx]["turnover"].mean())
                row[turnover_ratio_col] = avg_turnover / previous_turnover if previous_turnover else np.nan
            else:
                row[turnover_ratio_col] = np.nan

        rows.append(row)

    metrics = pd.DataFrame(rows)
    payload = metrics.drop(columns=["anchor_close"], errors="ignore")
    out = ranked_panel.merge(payload, on=["revision_date", "isin"], how="left")

    for window in windows:
        for col in [
            f"ret_m{window}td_to_anchor",
            f"vol_m{window}td_ann_to_anchor",
            f"turnover_ratio_m{window}td_to_anchor",
        ]:
            median_col = f"{col}_sector_median"
            out[median_col] = out.groupby(["revision_date", "sector"], dropna=False)[col].transform("median")
            out[f"{col}_vs_sector"] = out[col] - out[median_col]

        avg_col = f"avg_turnover_m{window}td_to_anchor"
        median_col = f"{avg_col}_sector_median"
        out[median_col] = out.groupby(["revision_date", "sector"], dropna=False)[avg_col].transform("median")
        with np.errstate(divide="ignore", invalid="ignore"):
            out[f"{avg_col}_rel_sector"] = out[avg_col] / out[median_col] - 1.0

    return out


def add_top_flag_by_revision(
    panel: pd.DataFrame,
    metric: str,
    percentile: float,
    flag_name: str,
) -> pd.DataFrame:
    out = panel.copy()
    flag = pd.Series(False, index=out.index)
    for _, group in out.groupby("revision_date", sort=True):
        valid = group.loc[group[metric].notna()].copy()
        if valid.empty:
            continue
        n_select = max(1, int(math.ceil(len(valid) * percentile)))
        flag.loc[valid.nlargest(n_select, metric).index] = True
    out[flag_name] = flag
    return out


def add_scores(panel: pd.DataFrame, window: int) -> pd.DataFrame:
    out = panel.copy()
    features = {
        "top_momentum": f"ret_m{window}td_to_anchor_vs_sector",
        "top_turnover_accel": f"turnover_ratio_m{window}td_to_anchor_vs_sector",
        "top_volatility": f"vol_m{window}td_ann_to_anchor_vs_sector",
    }
    for flag, metric in features.items():
        out = add_top_flag_by_revision(out, metric, SCORING_TOP_PERCENTILE, flag)

    out["score_previous_reserve"] = out["previous_mwig40_reserve"].fillna(False)
    out["hypothesis_score"] = (
        out["score_previous_reserve"].astype(int)
        + out["top_momentum"].astype(int)
        + out["top_turnover_accel"].astype(int)
        + out["top_volatility"].astype(int)
    )
    out["scoring_window"] = window
    return out


def summarize_scores(scored_by_window: dict[int, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for window, panel in scored_by_window.items():
        total_entrants = int(panel["entered_mwig40"].sum())
        baseline_rate = float(panel["entered_mwig40"].mean())
        for min_score in SCORE_THRESHOLDS:
            selected = panel.loc[panel["hypothesis_score"].ge(min_score)]
            selected_rows = len(selected)
            selected_entrants = int(selected["entered_mwig40"].sum())
            rows.append(
                {
                    "window_td": window,
                    "score_threshold": min_score,
                    "rows_in_universe": len(panel),
                    "available_entrants": total_entrants,
                    "selected_rows": selected_rows,
                    "selected_entrants": selected_entrants,
                    "precision": selected_entrants / selected_rows if selected_rows else np.nan,
                    "recall": selected_entrants / total_entrants if total_entrants else np.nan,
                    "baseline_rate": baseline_rate,
                    "lift": (selected_entrants / selected_rows) / baseline_rate if selected_rows and baseline_rate else np.nan,
                    "selected_unique_isins": int(selected["isin"].nunique()),
                    "selected_revisions": int(selected["revision_date"].nunique()),
                }
            )
    return pd.DataFrame(rows)


def summarize_signal_leads(scored_by_window: dict[int, pd.DataFrame], ranked_panel: pd.DataFrame) -> pd.DataFrame:
    entry_events = (
        ranked_panel.loc[ranked_panel["entered_mwig40"].fillna(False), ["isin", "revision_date", "anchor_target_trading_date"]]
        .dropna(subset=["anchor_target_trading_date"])
        .sort_values(["isin", "revision_date"])
    )
    rows = []
    for window, panel in scored_by_window.items():
        for min_score in SCORE_THRESHOLDS:
            selected = panel.loc[
                panel["hypothesis_score"].ge(min_score)
                & panel["anchor_target_trading_date"].notna()
            ].copy()
            leads = []
            same_revision_entrants = 0
            future_entrants = 0
            for signal in selected.itertuples(index=False):
                future_entries = entry_events.loc[
                    (entry_events["isin"].eq(signal.isin))
                    & (entry_events["revision_date"].ge(pd.Timestamp(signal.revision_date)))
                ]
                if future_entries.empty:
                    continue
                entry = future_entries.iloc[0]
                lead_days = (pd.Timestamp(entry["anchor_target_trading_date"]) - pd.Timestamp(signal.anchor_target_trading_date)).days
                leads.append(lead_days)
                if pd.Timestamp(entry["revision_date"]) == pd.Timestamp(signal.revision_date):
                    same_revision_entrants += 1
                else:
                    future_entrants += 1

            rows.append(
                {
                    "window_td": window,
                    "score_threshold": min_score,
                    "signals": len(selected),
                    "signals_with_eventual_entry": len(leads),
                    "same_revision_entries": same_revision_entrants,
                    "future_entries": future_entrants,
                    "median_lead_days_to_entry_anchor": float(np.median(leads)) if leads else np.nan,
                    "max_lead_days_to_entry_anchor": float(np.max(leads)) if leads else np.nan,
                }
            )
    return pd.DataFrame(rows)


def build_anchor_price_lookup(ranked_panel: pd.DataFrame, price_groups: dict[str, pd.DataFrame]) -> dict[tuple[str, pd.Timestamp], PriceAtDate]:
    lookup: dict[tuple[str, pd.Timestamp], PriceAtDate] = {}
    keys = ranked_panel[["isin", "anchor_date"]].dropna().drop_duplicates()
    for item in keys.itertuples(index=False):
        group = price_groups.get(item.isin)
        if group is None:
            continue
        price = price_on_or_before(group, pd.Timestamp(item.anchor_date))
        if price is not None:
            lookup[(item.isin, pd.Timestamp(item.anchor_date))] = price
    return lookup


def simulate_strategy(
    scored: pd.DataFrame,
    price_groups: dict[str, pd.DataFrame],
    anchor_price_lookup: dict[tuple[str, pd.Timestamp], PriceAtDate],
    rows_by_revision: dict[pd.Timestamp, pd.DataFrame],
    last_price_date: pd.Timestamp,
    score_threshold: int,
    exit_rank: int,
    window: int,
) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame]:
    scored_selected = scored.loc[scored["hypothesis_score"].ge(score_threshold)].copy()
    selected_keys = set(zip(scored_selected["revision_date"], scored_selected["isin"]))
    revisions = sorted(scored["revision_date"].dropna().unique())
    last_revision = pd.Timestamp(revisions[-1]) if revisions else pd.NaT

    positions: dict[str, dict[str, object]] = {}
    trades = []
    nav_rows = []
    nav = 1.0

    previous_revision = None
    previous_holdings: list[str] = []
    previous_prices: dict[str, float] = {}

    for revision in revisions:
        revision = pd.Timestamp(revision)
        current_rows = rows_by_revision.get(revision)
        if current_rows is None:
            continue

        current_prices = {}
        for isin in set(previous_holdings) | set(current_rows.index):
            if isin not in current_rows.index:
                continue
            row = current_rows.loc[isin]
            price = anchor_price_lookup.get((isin, pd.Timestamp(row["anchor_date"])))
            if price is not None:
                current_prices[isin] = price.close

        if previous_revision is not None and previous_holdings:
            period_returns = []
            for isin in previous_holdings:
                if isin in previous_prices and isin in current_prices and previous_prices[isin]:
                    period_returns.append(current_prices[isin] / previous_prices[isin] - 1.0)
            period_return = float(np.mean(period_returns)) if period_returns else 0.0
            nav *= 1.0 + period_return
        else:
            period_return = 0.0

        exited_this_revision = []
        for isin, position in list(positions.items()):
            if isin not in current_rows.index:
                continue
            row = current_rows.loc[isin]
            rank = row.get("wig_weight_rank")
            should_exit = pd.notna(rank) and int(rank) <= exit_rank
            if not should_exit:
                continue
            price = anchor_price_lookup.get((isin, pd.Timestamp(row["anchor_date"])))
            if price is None:
                continue
            ret = price.close / float(position["entry_price"]) - 1.0
            trades.append(
                {
                    **position,
                    "exit_revision_date": revision,
                    "exit_anchor_date": pd.Timestamp(row["anchor_date"]),
                    "exit_trading_date": price.date,
                    "exit_price": price.close,
                    "exit_wig_weight_rank": int(rank),
                    "exit_entered_mwig40": bool(row.get("entered_mwig40", False)),
                    "exit_reason": f"rank<={exit_rank}",
                    "return": ret,
                    "holding_days": (price.date - pd.Timestamp(position["entry_trading_date"])).days,
                    "closed": True,
                }
            )
            exited_this_revision.append(isin)
            del positions[isin]

        revision_signals = scored_selected.loc[scored_selected["revision_date"].eq(revision)]
        for signal in revision_signals.itertuples(index=False):
            if signal.isin in positions:
                continue
            if (revision, signal.isin) not in selected_keys or signal.isin not in current_rows.index:
                continue
            row = current_rows.loc[signal.isin]
            rank = row.get("wig_weight_rank")
            if pd.isna(rank) or int(rank) <= exit_rank:
                continue
            price = anchor_price_lookup.get((signal.isin, pd.Timestamp(row["anchor_date"])))
            if price is None:
                continue
            positions[signal.isin] = {
                "window_td": window,
                "score_threshold": score_threshold,
                "exit_rank": exit_rank,
                "isin": signal.isin,
                "ticker": signal.ticker,
                "sector": signal.sector,
                "entry_revision_date": revision,
                "entry_anchor_date": pd.Timestamp(row["anchor_date"]),
                "entry_trading_date": price.date,
                "entry_price": price.close,
                "entry_wig_weight_rank": int(rank),
                "entry_score": int(signal.hypothesis_score),
                "entry_entered_mwig40": bool(signal.entered_mwig40),
            }

        holdings = sorted(positions)
        previous_prices = {}
        for isin in holdings:
            if isin in current_rows.index:
                row = current_rows.loc[isin]
                price = anchor_price_lookup.get((isin, pd.Timestamp(row["anchor_date"])))
                if price is not None:
                    previous_prices[isin] = price.close

        nav_rows.append(
            {
                "window_td": window,
                "score_threshold": score_threshold,
                "exit_rank": exit_rank,
                "revision_date": revision,
                "period_return": period_return,
                "nav": nav,
                "active_positions": len(positions),
                "new_entries": int(len(revision_signals)),
                "exits": len(exited_this_revision),
            }
        )
        previous_revision = revision
        previous_holdings = holdings

    for isin, position in list(positions.items()):
        group = price_groups.get(isin)
        if group is None or group.empty:
            continue
        price = price_on_or_before(group, last_price_date)
        if price is None:
            continue
        ret = price.close / float(position["entry_price"]) - 1.0
        trades.append(
            {
                **position,
                "exit_revision_date": last_revision,
                "exit_anchor_date": pd.NaT,
                "exit_trading_date": price.date,
                "exit_price": price.close,
                "exit_wig_weight_rank": pd.NA,
                "exit_entered_mwig40": pd.NA,
                "exit_reason": "open_mark_to_market",
                "return": ret,
                "holding_days": (price.date - pd.Timestamp(position["entry_trading_date"])).days,
                "closed": False,
            }
        )

    nav_df = pd.DataFrame(nav_rows)
    trades_df = pd.DataFrame(trades)
    closed = trades_df.loc[trades_df["closed"].fillna(False)] if not trades_df.empty else pd.DataFrame()
    all_trades = trades_df
    active_nav = nav_df.loc[nav_df["active_positions"].gt(0), "nav"] if not nav_df.empty else pd.Series(dtype=float)
    nav_drawdown = (nav_df["nav"] / nav_df["nav"].cummax() - 1.0).min() if not nav_df.empty else np.nan
    active_periods = int(nav_df["active_positions"].gt(0).sum()) if not nav_df.empty else 0
    summary = {
        "window_td": window,
        "score_threshold": score_threshold,
        "exit_rank": exit_rank,
        "portfolio_return": nav - 1.0,
        "max_drawdown": float(nav_drawdown) if pd.notna(nav_drawdown) else np.nan,
        "active_periods": active_periods,
        "avg_active_positions": float(nav_df["active_positions"].mean()) if not nav_df.empty else 0.0,
        "max_active_positions": int(nav_df["active_positions"].max()) if not nav_df.empty else 0,
        "trades_total": int(len(all_trades)),
        "trades_closed": int(len(closed)),
        "trades_open_mtm": int((~all_trades["closed"].fillna(False)).sum()) if not all_trades.empty else 0,
        "closed_mean_return": float(closed["return"].mean()) if not closed.empty else np.nan,
        "closed_median_return": float(closed["return"].median()) if not closed.empty else np.nan,
        "closed_win_rate": float(closed["return"].gt(0).mean()) if not closed.empty else np.nan,
        "all_mean_return_mtm": float(all_trades["return"].mean()) if not all_trades.empty else np.nan,
        "all_median_return_mtm": float(all_trades["return"].median()) if not all_trades.empty else np.nan,
        "all_win_rate_mtm": float(all_trades["return"].gt(0).mean()) if not all_trades.empty else np.nan,
    }
    return summary, nav_df, trades_df


def choose_longest_working_windows(score_summary: pd.DataFrame) -> pd.DataFrame:
    candidates = score_summary.loc[
        score_summary["selected_rows"].ge(5)
        & score_summary["selected_entrants"].ge(1)
        & score_summary["lift"].ge(1.0)
    ].copy()
    if candidates.empty:
        return candidates
    return (
        candidates.sort_values(["score_threshold", "window_td"], ascending=[True, False])
        .groupby("score_threshold", as_index=False)
        .head(1)
        .sort_values("score_threshold")
        .reset_index(drop=True)
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    event_panel, prices = load_inputs()
    ranked = add_cross_revision_rank_features(event_panel)
    scored_source = compute_anchor_metrics(ranked, prices, WINDOWS)
    scored_source["predictive_universe"] = predictive_universe_mask(scored_source)
    hypothesis = scored_source.loc[scored_source["predictive_universe"]].copy()

    scored_by_window = {window: add_scores(hypothesis, window) for window in WINDOWS}
    score_summary = summarize_scores(scored_by_window)
    lead_summary = summarize_signal_leads(scored_by_window, scored_source)
    longest = choose_longest_working_windows(score_summary)

    price_groups = build_price_groups(prices)
    anchor_price_lookup = build_anchor_price_lookup(scored_source, price_groups)
    rows_by_revision = {
        pd.Timestamp(revision): group.set_index("isin")
        for revision, group in scored_source.groupby("revision_date", sort=True)
    }
    last_price_date = pd.Timestamp(prices["date"].max())

    backtest_rows = []
    nav_parts = []
    trade_parts = []

    if longest.empty:
        backtest_specs = [(window, threshold) for window in WINDOWS for threshold in SCORE_THRESHOLDS]
    else:
        backtest_specs = [(int(row.window_td), int(row.score_threshold)) for row in longest.itertuples(index=False)]

    signal_parts = []
    signal_cols = [
        "window_td",
        "score_threshold",
        "revision_date",
        "anchor_date",
        "anchor_target_trading_date",
        "ticker",
        "isin",
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
    ]
    for window, score_threshold in backtest_specs:
        selected = scored_by_window[window].loc[
            scored_by_window[window]["hypothesis_score"].ge(score_threshold)
        ].copy()
        selected["window_td"] = window
        selected["score_threshold"] = score_threshold
        metric_cols = [
            f"ret_m{window}td_to_anchor_vs_sector",
            f"turnover_ratio_m{window}td_to_anchor_vs_sector",
            f"vol_m{window}td_ann_to_anchor_vs_sector",
        ]
        cols = [col for col in signal_cols + metric_cols if col in selected.columns]
        signal_parts.append(selected[cols])

    for window, score_threshold in backtest_specs:
        scored = scored_by_window[window]
        for exit_rank in EXIT_RANKS:
            summary, nav_df, trades_df = simulate_strategy(
                scored=scored,
                price_groups=price_groups,
                anchor_price_lookup=anchor_price_lookup,
                rows_by_revision=rows_by_revision,
                last_price_date=last_price_date,
                score_threshold=score_threshold,
                exit_rank=exit_rank,
                window=window,
            )
            backtest_rows.append(summary)
            if not nav_df.empty:
                nav_parts.append(nav_df)
            if not trades_df.empty:
                trade_parts.append(trades_df)

    backtest_summary = pd.DataFrame(backtest_rows)
    nav = pd.concat(nav_parts, ignore_index=True) if nav_parts else pd.DataFrame()
    trades = pd.concat(trade_parts, ignore_index=True) if trade_parts else pd.DataFrame()
    signals = pd.concat(signal_parts, ignore_index=True) if signal_parts else pd.DataFrame()

    score_summary.to_csv(OUT_DIR / "mwig40_score_window_summary.csv", index=False)
    lead_summary.to_csv(OUT_DIR / "mwig40_score_signal_leads.csv", index=False)
    longest.to_csv(OUT_DIR / "mwig40_score_longest_working_windows.csv", index=False)
    signals.to_csv(OUT_DIR / "mwig40_score_selected_signals.csv", index=False)
    backtest_summary.to_csv(OUT_DIR / "mwig40_score_backtest_summary.csv", index=False)
    nav.to_csv(OUT_DIR / "mwig40_score_backtest_nav.csv", index=False)
    trades.to_csv(OUT_DIR / "mwig40_score_backtest_trades.csv", index=False)

    print("Longest working windows")
    print(longest.to_string(index=False))
    print()
    print("Score summary for longest windows")
    if not longest.empty:
        mask = pd.Series(False, index=score_summary.index)
        for row in longest.itertuples(index=False):
            mask = mask | (
                score_summary["window_td"].eq(row.window_td)
                & score_summary["score_threshold"].eq(row.score_threshold)
            )
        print(score_summary.loc[mask].to_string(index=False))
    print()
    print("Best backtests for longest windows by portfolio_return")
    if not longest.empty:
        mask = pd.Series(False, index=backtest_summary.index)
        for row in longest.itertuples(index=False):
            mask = mask | (
                backtest_summary["window_td"].eq(row.window_td)
                & backtest_summary["score_threshold"].eq(row.score_threshold)
            )
        cols = [
            "window_td",
            "score_threshold",
            "exit_rank",
            "portfolio_return",
            "max_drawdown",
            "active_periods",
            "avg_active_positions",
            "trades_total",
            "trades_closed",
            "closed_median_return",
            "closed_win_rate",
            "all_median_return_mtm",
        ]
        print(
            backtest_summary.loc[mask, cols]
            .sort_values(["score_threshold", "portfolio_return"], ascending=[True, False])
            .groupby("score_threshold")
            .head(5)
            .to_string(index=False)
        )
    print()
    print(f"Wrote outputs to: {OUT_DIR}")


if __name__ == "__main__":
    main()
