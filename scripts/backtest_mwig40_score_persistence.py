from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from backtest_mwig40_scoring import (
    OUT_DIR,
    ROOT,
    WINDOWS,
    add_cross_revision_rank_features,
    add_scores,
    build_price_groups,
    compute_anchor_metrics,
    load_inputs,
    predictive_universe_mask,
    price_on_or_before,
)


ENTRY_SCORE_THRESHOLDS = [2, 3, 4]
ENTRY_STREAKS = [1, 2, 3, 4]
EXIT_SCORE_THRESHOLDS = [0, 1, 2, 3]
EXIT_STREAKS = [1, 2, 3, 4]


def build_revision_anchor_dates(panel: pd.DataFrame) -> dict[pd.Timestamp, pd.Timestamp]:
    out = {}
    for revision, group in panel.groupby("revision_date", sort=True):
        values = group["anchor_date"].dropna()
        if values.empty:
            continue
        out[pd.Timestamp(revision)] = pd.Timestamp(values.iloc[0])
    return out


def price_for_revision(
    price_groups: dict[str, pd.DataFrame],
    revision_anchor_dates: dict[pd.Timestamp, pd.Timestamp],
    isin: str,
    revision: pd.Timestamp,
):
    anchor_date = revision_anchor_dates.get(pd.Timestamp(revision))
    group = price_groups.get(isin)
    if anchor_date is None or group is None or group.empty:
        return None
    return price_on_or_before(group, anchor_date)


def build_score_maps(scored: pd.DataFrame) -> dict[pd.Timestamp, pd.DataFrame]:
    return {
        pd.Timestamp(revision): group.sort_values("ticker").drop_duplicates("isin").set_index("isin")
        for revision, group in scored.groupby("revision_date", sort=True)
    }


def close_position(position: dict[str, object], revision: pd.Timestamp, price, score: int, reason: str) -> dict[str, object]:
    return {
        **position,
        "exit_revision_date": revision,
        "exit_trading_date": price.date,
        "exit_price": price.close,
        "exit_score": score,
        "exit_reason": reason,
        "return": price.close / float(position["entry_price"]) - 1.0,
        "holding_days": (price.date - pd.Timestamp(position["entry_trading_date"])).days,
        "closed": reason != "open_mark_to_market",
    }


def summarize_strategy(
    params: dict[str, int],
    nav_rows: list[dict[str, object]],
    trades: list[dict[str, object]],
) -> dict[str, object]:
    nav = pd.DataFrame(nav_rows)
    trades_df = pd.DataFrame(trades)
    closed = trades_df.loc[trades_df["closed"].fillna(False)] if not trades_df.empty else pd.DataFrame()
    final_nav = float(nav["nav"].iloc[-1]) if not nav.empty else 1.0
    drawdown = float((nav["nav"] / nav["nav"].cummax() - 1.0).min()) if not nav.empty else np.nan
    active_periods = int(nav["active_positions"].gt(0).sum()) if not nav.empty else 0
    active_period_share = active_periods / len(nav) if len(nav) else 0.0

    years = np.nan
    cagr = np.nan
    if not trades_df.empty:
        start = pd.Timestamp(trades_df["entry_trading_date"].min())
        end = pd.Timestamp(nav["valuation_date"].iloc[-1]) if not nav.empty else pd.Timestamp(trades_df["exit_trading_date"].max())
        years = max((end - start).days / 365.25, 0.0)
        if years > 0 and final_nav > 0:
            cagr = final_nav ** (1.0 / years) - 1.0

    return {
        **params,
        "portfolio_return": final_nav - 1.0,
        "cagr": cagr,
        "max_drawdown": drawdown,
        "active_periods": active_periods,
        "active_period_share": active_period_share,
        "avg_active_positions": float(nav["active_positions"].mean()) if not nav.empty else 0.0,
        "max_active_positions": int(nav["active_positions"].max()) if not nav.empty else 0,
        "entries": int(len(trades_df)),
        "closed_trades": int(len(closed)),
        "open_mtm_trades": int((~trades_df["closed"].fillna(False)).sum()) if not trades_df.empty else 0,
        "closed_mean_return": float(closed["return"].mean()) if not closed.empty else np.nan,
        "closed_median_return": float(closed["return"].median()) if not closed.empty else np.nan,
        "closed_win_rate": float(closed["return"].gt(0).mean()) if not closed.empty else np.nan,
        "all_mean_return_mtm": float(trades_df["return"].mean()) if not trades_df.empty else np.nan,
        "all_median_return_mtm": float(trades_df["return"].median()) if not trades_df.empty else np.nan,
        "all_win_rate_mtm": float(trades_df["return"].gt(0).mean()) if not trades_df.empty else np.nan,
        "years_from_first_trade": years,
    }


def simulate_persistence_strategy(
    score_maps: dict[pd.Timestamp, pd.DataFrame],
    price_groups: dict[str, pd.DataFrame],
    revision_anchor_dates: dict[pd.Timestamp, pd.Timestamp],
    last_price_date: pd.Timestamp,
    window: int,
    entry_x: int,
    entry_n: int,
    exit_y: int,
    exit_m: int,
) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame]:
    revisions = sorted(revision_anchor_dates)

    positions: dict[str, dict[str, object]] = {}
    entry_streak: dict[str, int] = {}
    entry_last_revision_idx: dict[str, int] = {}
    exit_streak: dict[str, int] = {}

    previous_holdings: list[str] = []
    previous_prices: dict[str, float] = {}
    nav = 1.0
    nav_rows: list[dict[str, object]] = []
    trades: list[dict[str, object]] = []

    for revision_idx, revision in enumerate(revisions):
        score_table = score_maps.get(revision, pd.DataFrame())
        valuation_date = revision_anchor_dates[revision]

        current_prices = {}
        for isin in previous_holdings:
            price = price_for_revision(price_groups, revision_anchor_dates, isin, revision)
            if price is not None:
                current_prices[isin] = price.close

        if previous_holdings:
            period_returns = [
                current_prices[isin] / previous_prices[isin] - 1.0
                for isin in previous_holdings
                if isin in current_prices and isin in previous_prices and previous_prices[isin]
            ]
            period_return = float(np.mean(period_returns)) if period_returns else 0.0
            nav *= 1.0 + period_return
        else:
            period_return = 0.0

        exited = []
        for isin, position in list(positions.items()):
            score = int(score_table.loc[isin, "hypothesis_score"]) if isin in score_table.index else 0
            if score <= exit_y:
                exit_streak[isin] = exit_streak.get(isin, 0) + 1
            else:
                exit_streak[isin] = 0

            if exit_streak[isin] >= exit_m:
                price = price_for_revision(price_groups, revision_anchor_dates, isin, revision)
                if price is None:
                    continue
                trades.append(close_position(position, revision, price, score, f"score<={exit_y}_for_{exit_m}rev"))
                exited.append(isin)
                del positions[isin]
                exit_streak.pop(isin, None)

        entries = []
        if not score_table.empty:
            candidates = score_table.loc[score_table["hypothesis_score"].ge(entry_x)].copy()
            for isin, signal in candidates.iterrows():
                if entry_last_revision_idx.get(isin) == revision_idx - 1:
                    entry_streak[isin] = entry_streak.get(isin, 0) + 1
                else:
                    entry_streak[isin] = 1
                entry_last_revision_idx[isin] = revision_idx

                if entry_streak[isin] < entry_n or isin in positions:
                    continue
                price = price_for_revision(price_groups, revision_anchor_dates, isin, revision)
                if price is None:
                    continue
                positions[isin] = {
                    "window_td": window,
                    "entry_x": entry_x,
                    "entry_n": entry_n,
                    "exit_y": exit_y,
                    "exit_m": exit_m,
                    "isin": isin,
                    "ticker": signal.get("ticker"),
                    "sector": signal.get("sector"),
                    "entry_revision_date": revision,
                    "entry_trading_date": price.date,
                    "entry_price": price.close,
                    "entry_score": int(signal["hypothesis_score"]),
                    "entry_wig_weight_rank": int(signal["wig_weight_rank"]) if pd.notna(signal.get("wig_weight_rank")) else pd.NA,
                    "entry_entered_mwig40": bool(signal.get("entered_mwig40", False)),
                }
                exit_streak[isin] = 0
                entries.append(isin)

        holdings = sorted(positions)
        previous_prices = {}
        for isin in holdings:
            price = price_for_revision(price_groups, revision_anchor_dates, isin, revision)
            if price is not None:
                previous_prices[isin] = price.close

        nav_rows.append(
            {
                "window_td": window,
                "entry_x": entry_x,
                "entry_n": entry_n,
                "exit_y": exit_y,
                "exit_m": exit_m,
                "valuation_date": valuation_date,
                "revision_date": revision,
                "period_return": period_return,
                "nav": nav,
                "active_positions": len(positions),
                "entries": len(entries),
                "exits": len(exited),
            }
        )
        previous_holdings = holdings

    if previous_holdings:
        final_returns = []
        final_prices = {}
        for isin in previous_holdings:
            group = price_groups.get(isin)
            if group is None or group.empty:
                continue
            price = price_on_or_before(group, last_price_date)
            if price is None:
                continue
            final_prices[isin] = price
            if isin in previous_prices and previous_prices[isin]:
                final_returns.append(price.close / previous_prices[isin] - 1.0)

        final_period_return = float(np.mean(final_returns)) if final_returns else 0.0
        nav *= 1.0 + final_period_return
        nav_rows.append(
            {
                "window_td": window,
                "entry_x": entry_x,
                "entry_n": entry_n,
                "exit_y": exit_y,
                "exit_m": exit_m,
                "valuation_date": last_price_date,
                "revision_date": pd.NaT,
                "period_return": final_period_return,
                "nav": nav,
                "active_positions": len(positions),
                "entries": 0,
                "exits": 0,
            }
        )

        for isin, position in positions.items():
            price = final_prices.get(isin)
            if price is not None:
                trades.append(close_position(position, pd.NaT, price, -1, "open_mark_to_market"))

    params = {
        "window_td": window,
        "entry_x": entry_x,
        "entry_n": entry_n,
        "exit_y": exit_y,
        "exit_m": exit_m,
    }
    summary = summarize_strategy(params, nav_rows, trades)
    return summary, pd.DataFrame(nav_rows), pd.DataFrame(trades)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    event_panel, prices = load_inputs()
    ranked = add_cross_revision_rank_features(event_panel)
    scored_source = compute_anchor_metrics(ranked, prices, WINDOWS)
    scored_source["predictive_universe"] = predictive_universe_mask(scored_source)
    hypothesis = scored_source.loc[scored_source["predictive_universe"]].copy()

    price_groups = build_price_groups(prices)
    revision_anchor_dates = build_revision_anchor_dates(scored_source.loc[scored_source["has_previous_revision"].fillna(False)])
    last_price_date = pd.Timestamp(prices["date"].max())
    scored_by_window = {window: add_scores(hypothesis, window) for window in WINDOWS}
    score_maps_by_window = {
        window: build_score_maps(scored)
        for window, scored in scored_by_window.items()
    }

    summary_rows = []
    nav_parts = []
    trade_parts = []

    for window, score_maps in score_maps_by_window.items():
        for entry_x in ENTRY_SCORE_THRESHOLDS:
            for entry_n in ENTRY_STREAKS:
                for exit_y in EXIT_SCORE_THRESHOLDS:
                    if exit_y >= entry_x:
                        continue
                    for exit_m in EXIT_STREAKS:
                        summary, nav, trades = simulate_persistence_strategy(
                            score_maps=score_maps,
                            price_groups=price_groups,
                            revision_anchor_dates=revision_anchor_dates,
                            last_price_date=last_price_date,
                            window=window,
                            entry_x=entry_x,
                            entry_n=entry_n,
                            exit_y=exit_y,
                            exit_m=exit_m,
                        )
                        summary_rows.append(summary)
                        if not nav.empty:
                            nav_parts.append(nav)
                        if not trades.empty:
                            trade_parts.append(trades)

    summary = pd.DataFrame(summary_rows)
    nav = pd.concat(nav_parts, ignore_index=True) if nav_parts else pd.DataFrame()
    trades = pd.concat(trade_parts, ignore_index=True) if trade_parts else pd.DataFrame()

    summary.to_csv(OUT_DIR / "mwig40_score_persistence_grid.csv", index=False)
    nav.to_csv(OUT_DIR / "mwig40_score_persistence_nav.csv", index=False)
    trades.to_csv(OUT_DIR / "mwig40_score_persistence_trades.csv", index=False)

    printable_cols = [
        "window_td",
        "entry_x",
        "entry_n",
        "exit_y",
        "exit_m",
        "portfolio_return",
        "cagr",
        "max_drawdown",
        "entries",
        "closed_trades",
        "all_median_return_mtm",
        "all_win_rate_mtm",
        "avg_active_positions",
    ]
    print("Top strategies, min 3 entries, by portfolio_return")
    print(
        summary.loc[summary["entries"].ge(3), printable_cols]
        .sort_values(["portfolio_return", "max_drawdown"], ascending=[False, False])
        .head(20)
        .to_string(index=False)
    )
    print()
    print("Top strategies, min 3 entries, max drawdown no worse than -25%")
    print(
        summary.loc[summary["entries"].ge(3) & summary["max_drawdown"].ge(-0.25), printable_cols]
        .sort_values(["portfolio_return", "max_drawdown"], ascending=[False, False])
        .head(20)
        .to_string(index=False)
    )
    print()
    print(f"Wrote outputs to: {OUT_DIR}")


if __name__ == "__main__":
    main()
