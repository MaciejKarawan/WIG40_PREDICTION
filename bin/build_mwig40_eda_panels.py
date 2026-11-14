#!/usr/bin/env python3
"""Build historical EDA panels for mWIG40 transition research.

Inputs:
    output/wig_history/index_portfolios.parquet
    output/wig_history/reserve_lists.parquet
    output/eda_2021_2026_revision/wigeda_2021_2026_ohlcv.parquet
    data/reference/sector_map.csv

Outputs:
    output/eda/mwig40_event_panel.parquet
    output/eda/mwig40_sector_peer_panel.parquet
    output/eda/mwig40_price_panel.parquet
    output/eda/mwig40_eda_panel_summary.csv
"""

from __future__ import annotations

import argparse
import importlib.util
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORTFOLIOS = ROOT / "output" / "wig_history" / "index_portfolios.parquet"
DEFAULT_RESERVES = ROOT / "output" / "wig_history" / "reserve_lists.parquet"
DEFAULT_SECTOR_MAP = ROOT / "data" / "reference" / "sector_map.csv"
DEFAULT_OHLCV = ROOT / "output" / "eda_2021_2026_revision" / "wigeda_2021_2026_ohlcv.parquet"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "eda"

ANCHOR_OVERRIDES = {
    # WIG PDF has 2026-02-27 in index_portfolios, but the replication and
    # corrected WIG prices are anchored to 2026-02-20.
    "2026-03-20": "2026-02-20",
}

PRE_WINDOWS = (20, 60, 120)
POST_WINDOWS = (5, 20)
SECTOR_RELATIVE_COLUMNS = (
    "ret_m20td",
    "ret_m60td",
    "ret_m120td",
    "vol_m20td_ann",
    "vol_m60td_ann",
    "vol_m120td_ann",
    "max_drawdown_m60td",
    "max_drawdown_m120td",
    "turnover_ratio_m20td_vs_prev",
    "turnover_ratio_m60td_vs_prev",
    "turnover_ratio_m120td_vs_prev",
)


def load_transition_module():
    module_path = ROOT / "bin" / "analyze_mwig40_transitions.py"
    spec = importlib.util.spec_from_file_location("mwig40_transitions", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalize_dates(portfolios: pd.DataFrame, reserves: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    portfolios = portfolios.copy()
    reserves = reserves.copy()
    portfolios["revision_date"] = pd.to_datetime(portfolios["revision_date"])
    portfolios["ranking_date"] = pd.to_datetime(portfolios["ranking_date"], errors="coerce")
    reserves["revision_date"] = pd.to_datetime(reserves["revision_date"])
    return portfolios, reserves


def build_revision_anchors(portfolios: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for revision_date, group in portfolios.groupby("revision_date"):
        revision_key = pd.Timestamp(revision_date).date().isoformat()
        override = ANCHOR_OVERRIDES.get(revision_key)
        if override:
            anchor_date = pd.Timestamp(override)
            anchor_source = "override"
        else:
            mwig_dates = group.loc[group["index_name"].eq("mWIG40"), "ranking_date"].dropna()
            if not mwig_dates.empty:
                anchor_date = pd.Timestamp(mwig_dates.iloc[0])
                anchor_source = "mwig40_ranking_date"
            else:
                wig_dates = group.loc[group["index_name"].eq("WIG"), "ranking_date"].dropna()
                anchor_date = pd.Timestamp(wig_dates.iloc[0]) if not wig_dates.empty else pd.Timestamp(revision_date)
                anchor_source = "wig_ranking_date" if not wig_dates.empty else "revision_date_fallback"

        rows.append(
            {
                "revision_date": pd.Timestamp(revision_date),
                "anchor_date": anchor_date,
                "anchor_source": anchor_source,
            }
        )
    return pd.DataFrame(rows).sort_values("revision_date").reset_index(drop=True)


def max_drawdown(values: pd.Series) -> float:
    if values.empty:
        return np.nan
    return float((values / values.cummax() - 1.0).min())


def metrics_for_series(group: pd.DataFrame, anchor_date: pd.Timestamp) -> dict[str, object]:
    group = group.sort_values("date").reset_index(drop=True).copy()
    group["turnover"] = group["close"] * group["volume"]
    group["return_1d"] = group["close"].pct_change()

    anchor_idx = group["date"].searchsorted(anchor_date, side="right") - 1
    if anchor_idx < 0:
        return {
            "anchor_trading_date": pd.NaT,
            "anchor_close": np.nan,
            "pre_trading_days_available": 0,
            "post_trading_days_available": 0,
        }

    row: dict[str, object] = {
        "anchor_trading_date": group.loc[anchor_idx, "date"],
        "anchor_close": group.loc[anchor_idx, "close"],
        "pre_trading_days_available": int(anchor_idx),
        "post_trading_days_available": int(len(group) - anchor_idx - 1),
    }

    for window in PRE_WINDOWS:
        start_idx = anchor_idx - window
        if start_idx >= 0:
            segment = group.iloc[start_idx : anchor_idx + 1].copy()
            returns = segment["return_1d"].dropna()
            row[f"ret_m{window}td"] = group.loc[anchor_idx, "close"] / group.loc[start_idx, "close"] - 1.0
            row[f"vol_m{window}td_ann"] = returns.std(ddof=0) * math.sqrt(252) if len(returns) > 1 else np.nan
            row[f"avg_turnover_m{window}td"] = segment["turnover"].mean()
            row[f"max_drawdown_m{window}td"] = max_drawdown(segment["close"])

            prev_start_idx = start_idx - window
            if prev_start_idx >= 0:
                previous_segment = group.iloc[prev_start_idx:start_idx].copy()
                previous_turnover = previous_segment["turnover"].mean()
                row[f"turnover_ratio_m{window}td_vs_prev"] = (
                    segment["turnover"].mean() / previous_turnover
                    if previous_turnover and not pd.isna(previous_turnover)
                    else np.nan
                )
            else:
                row[f"turnover_ratio_m{window}td_vs_prev"] = np.nan
        else:
            row[f"ret_m{window}td"] = np.nan
            row[f"vol_m{window}td_ann"] = np.nan
            row[f"avg_turnover_m{window}td"] = np.nan
            row[f"max_drawdown_m{window}td"] = np.nan
            row[f"turnover_ratio_m{window}td_vs_prev"] = np.nan

    for window in POST_WINDOWS:
        end_idx = anchor_idx + window
        if end_idx < len(group):
            segment = group.iloc[anchor_idx : end_idx + 1].copy()
            returns = segment["return_1d"].dropna()
            row[f"ret_p{window}td"] = group.loc[end_idx, "close"] / group.loc[anchor_idx, "close"] - 1.0
            row[f"vol_p{window}td_ann"] = returns.std(ddof=0) * math.sqrt(252) if len(returns) > 1 else np.nan
        else:
            row[f"ret_p{window}td"] = np.nan
            row[f"vol_p{window}td_ann"] = np.nan

    return row


def build_membership_maps(portfolios: pd.DataFrame) -> dict[tuple[pd.Timestamp, str], set[str]]:
    return {
        (pd.Timestamp(revision), index_name): set(group["isin"])
        for (revision, index_name), group in portfolios.groupby(["revision_date", "index_name"])
    }


def build_reserve_rank_map(reserves: pd.DataFrame, index_name: str) -> dict[tuple[pd.Timestamp, str], int]:
    out: dict[tuple[pd.Timestamp, str], int] = {}
    subset = reserves[reserves["index_name"].eq(index_name)]
    for row in subset.itertuples(index=False):
        out[(pd.Timestamp(row.revision_date), row.isin)] = int(row.lp)
    return out


def build_sector_map_for_rows(rows: pd.DataFrame, sector_map: pd.DataFrame) -> pd.DataFrame:
    exact_cols = ["isin", "ticker", "macrosector", "sector", "industry"]
    available_exact = [c for c in exact_cols if c in sector_map.columns]
    out = rows.merge(sector_map[available_exact].drop_duplicates(["isin", "ticker"]), on=["isin", "ticker"], how="left")

    missing_sector = out["sector"].isna() if "sector" in out.columns else pd.Series(True, index=out.index)
    if missing_sector.any() and "isin" in sector_map.columns:
        fallback = (
            sector_map[[c for c in ["isin", "macrosector", "sector", "industry"] if c in sector_map.columns]]
            .drop_duplicates("isin")
            .rename(
                columns={
                    "macrosector": "macrosector_fallback",
                    "sector": "sector_fallback",
                    "industry": "industry_fallback",
                }
            )
        )
        out = out.merge(fallback, on="isin", how="left")
        for col in ("macrosector", "sector", "industry"):
            fallback_col = f"{col}_fallback"
            if col not in out.columns:
                out[col] = out[fallback_col]
            else:
                out[col] = out[col].fillna(out[fallback_col])
            out = out.drop(columns=fallback_col)

    return out


def previous_index_for_isin(isin: str, previous_date: pd.Timestamp | None, membership: dict[tuple[pd.Timestamp, str], set[str]]) -> str:
    if previous_date is None:
        return "no_previous_revision"
    for index_name in ("WIG20", "mWIG40", "sWIG80", "WIG"):
        if isin in membership.get((previous_date, index_name), set()):
            return index_name
    return "outside_wig"


def current_index_for_isin(isin: str, revision_date: pd.Timestamp, membership: dict[tuple[pd.Timestamp, str], set[str]]) -> str:
    for index_name in ("WIG20", "mWIG40", "sWIG80", "WIG"):
        if isin in membership.get((revision_date, index_name), set()):
            return index_name
    return "outside_wig"


def build_event_panel(
    portfolios: pd.DataFrame,
    reserves: pd.DataFrame,
    sector_map: pd.DataFrame,
    ohlcv: pd.DataFrame,
    anchors: pd.DataFrame,
    events: pd.DataFrame,
) -> pd.DataFrame:
    membership = build_membership_maps(portfolios)
    mwig_reserve_rank = build_reserve_rank_map(reserves, "mWIG40")
    revision_dates = sorted(portfolios["revision_date"].dropna().unique())
    previous_by_revision = {
        pd.Timestamp(revision_dates[pos]): pd.Timestamp(revision_dates[pos - 1]) if pos > 0 else None
        for pos in range(len(revision_dates))
    }

    entry_event_cols = [
        "revision_date",
        "isin",
        "previous_bucket",
        "category",
        "was_ever_in_mwig40_before",
        "in_previous_mwig40_reserve",
        "previous_mwig40_reserve_rank",
    ]
    event_lookup = events.copy()
    event_lookup["revision_date"] = pd.to_datetime(event_lookup["revision_date"])
    event_lookup = event_lookup[entry_event_cols]
    event_lookup = event_lookup.rename(
        columns={
            "in_previous_mwig40_reserve": "event_in_previous_mwig40_reserve",
            "previous_mwig40_reserve_rank": "event_previous_mwig40_reserve_rank",
        }
    )

    base_rows = portfolios[portfolios["index_name"].eq("WIG")][
        ["revision_date", "ranking_date", "isin", "ticker", "price", "shares", "weight_pct", "flags"]
    ].drop_duplicates(["revision_date", "isin"])
    base_rows = base_rows.merge(anchors, on="revision_date", how="left")
    base_rows = build_sector_map_for_rows(base_rows, sector_map)

    reserve_flags = reserves[reserves["index_name"].eq("mWIG40")][["revision_date", "isin", "lp"]].copy()
    reserve_flags = reserve_flags.rename(columns={"lp": "current_mwig40_reserve_rank"})

    rows: list[dict[str, object]] = []
    ohlcv_by_isin = {isin: group for isin, group in ohlcv.groupby("isin", sort=False)}

    for row in base_rows.itertuples(index=False):
        revision_date = pd.Timestamp(row.revision_date)
        previous_date = previous_by_revision.get(revision_date)
        has_previous_revision = previous_date is not None
        isin = row.isin
        ohlcv_group = ohlcv_by_isin.get(isin)
        metric_values = metrics_for_series(ohlcv_group, pd.Timestamp(row.anchor_date)) if ohlcv_group is not None else {}

        previous_mwig = membership.get((previous_date, "mWIG40"), set()) if has_previous_revision else set()
        current_mwig = membership.get((revision_date, "mWIG40"), set())
        previous_reserve_rank = mwig_reserve_rank.get((previous_date, isin)) if has_previous_revision else None
        current_reserve_rank = mwig_reserve_rank.get((revision_date, isin))

        rows.append(
            {
                "revision_date": revision_date,
                "previous_revision_date": previous_date,
                "has_previous_revision": has_previous_revision,
                "anchor_date": pd.Timestamp(row.anchor_date),
                "anchor_source": row.anchor_source,
                "isin": isin,
                "ticker": row.ticker,
                "price_pdf": row.price,
                "shares_ff": row.shares,
                "weight_pct": row.weight_pct,
                "flags": row.flags,
                "macrosector": getattr(row, "macrosector", None),
                "sector": getattr(row, "sector", None),
                "industry": getattr(row, "industry", None),
                "previous_index": previous_index_for_isin(isin, previous_date, membership),
                "current_index": current_index_for_isin(isin, revision_date, membership),
                "was_in_previous_mwig40": isin in previous_mwig,
                "is_in_current_mwig40": isin in current_mwig,
                "entered_mwig40": has_previous_revision and isin in current_mwig and isin not in previous_mwig,
                "exited_mwig40": has_previous_revision and isin in previous_mwig and isin not in current_mwig,
                "previous_mwig40_reserve": previous_reserve_rank is not None,
                "previous_mwig40_reserve_rank": previous_reserve_rank,
                "current_mwig40_reserve": current_reserve_rank is not None,
                "current_mwig40_reserve_rank": current_reserve_rank,
                "has_ohlcv": ohlcv_group is not None,
                **metric_values,
            }
        )

    panel = pd.DataFrame(rows)
    panel = panel.merge(event_lookup, on=["revision_date", "isin"], how="left")
    panel["candidate_universe"] = (
        panel["entered_mwig40"]
        | panel["exited_mwig40"]
        | panel["previous_mwig40_reserve"]
        | panel["current_mwig40_reserve"]
    )

    for col in SECTOR_RELATIVE_COLUMNS:
        if col not in panel.columns:
            continue
        median_col = f"{col}_sector_median"
        relative_col = f"{col}_vs_sector"
        panel[median_col] = np.nan
        for (_, sector), idx in panel.groupby(["revision_date", "sector"]).groups.items():
            if pd.isna(sector):
                continue
            values = panel.loc[idx, col]
            for row_idx in idx:
                peer_values = values.drop(index=row_idx).dropna()
                panel.at[row_idx, median_col] = peer_values.median() if not peer_values.empty else np.nan
        panel[relative_col] = panel[col] - panel[median_col]

    return panel.sort_values(["revision_date", "ticker", "isin"]).reset_index(drop=True)


def build_sector_peer_panel(event_panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    metric_cols = [
        col
        for col in event_panel.columns
        if col.startswith(("ret_m", "vol_m", "avg_turnover_m", "max_drawdown_m", "turnover_ratio_m"))
    ]

    for revision_date, revision_group in event_panel.groupby("revision_date"):
        entrants = revision_group[revision_group["entered_mwig40"]].copy()
        for entrant in entrants.itertuples(index=False):
            if pd.isna(getattr(entrant, "sector", None)):
                continue
            peers = revision_group[
                revision_group["sector"].eq(entrant.sector) & ~revision_group["isin"].eq(entrant.isin)
            ].copy()
            for peer in peers.itertuples(index=False):
                row = {
                    "revision_date": revision_date,
                    "anchor_date": entrant.anchor_date,
                    "entrant_isin": entrant.isin,
                    "entrant_ticker": entrant.ticker,
                    "entrant_previous_index": entrant.previous_index,
                    "entrant_category": getattr(entrant, "category", None),
                    "sector": entrant.sector,
                    "industry": getattr(entrant, "industry", None),
                    "peer_isin": peer.isin,
                    "peer_ticker": peer.ticker,
                    "peer_current_index": peer.current_index,
                    "peer_previous_index": peer.previous_index,
                    "peer_entered_mwig40": peer.entered_mwig40,
                    "peer_previous_mwig40_reserve": peer.previous_mwig40_reserve,
                }
                for col in metric_cols:
                    row[f"entrant_{col}"] = getattr(entrant, col, np.nan)
                    row[f"peer_{col}"] = getattr(peer, col, np.nan)
                    row[f"{col}_entrant_minus_peer"] = getattr(entrant, col, np.nan) - getattr(peer, col, np.nan)
                rows.append(row)

    return pd.DataFrame(rows).sort_values(["revision_date", "entrant_ticker", "peer_ticker"]).reset_index(drop=True)


def build_summary(event_panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for revision_date, group in event_panel.groupby("revision_date"):
        rows.append(
            {
                "revision_date": revision_date,
                "anchor_date": group["anchor_date"].iloc[0],
                "wig_rows": len(group),
                "has_ohlcv_rows": int(group["has_ohlcv"].sum()),
                "entered_mwig40": int(group["entered_mwig40"].sum()),
                "previous_mwig40_reserve": int(group["previous_mwig40_reserve"].sum()),
                "current_mwig40_reserve": int(group["current_mwig40_reserve"].sum()),
                "ret_m60td_available": int(group["ret_m60td"].notna().sum()) if "ret_m60td" in group else 0,
                "ret_m120td_available": int(group["ret_m120td"].notna().sum()) if "ret_m120td" in group else 0,
                "ret_p20td_available": int(group["ret_p20td"].notna().sum()) if "ret_p20td" in group else 0,
            }
        )
    return pd.DataFrame(rows)


def build_manifest(
    output_dir: Path,
    event_panel: pd.DataFrame,
    sector_peer_panel: pd.DataFrame,
    price_panel: pd.DataFrame,
    summary: pd.DataFrame,
    ohlcv_path: Path,
) -> str:
    revision_start = event_panel["revision_date"].min().date().isoformat()
    revision_end = event_panel["revision_date"].max().date().isoformat()
    price_start = pd.to_datetime(price_panel["date"]).min().date().isoformat()
    price_end = pd.to_datetime(price_panel["date"]).max().date().isoformat()

    return f"""# mWIG40 EDA Dataset

Generated by `bin/build_mwig40_eda_panels.py`.

## Scope

- Revisions: {revision_start} to {revision_end} ({event_panel['revision_date'].nunique()} revision dates)
- Price history: {price_start} to {price_end}
- Event panel rows: {len(event_panel):,}
- Entrants after baseline revision: {int(event_panel['entered_mwig40'].sum())}
- Candidate rows: {int(event_panel['candidate_universe'].sum())}
- Unique candidate ISINs: {event_panel.loc[event_panel['candidate_universe'], 'isin'].nunique()}
- Sector peer rows: {len(sector_peer_panel):,}
- Price rows: {len(price_panel):,}

## Files

- `{output_dir / 'mwig40_event_panel.parquet'}`: one row per WIG company and revision, with mWIG40 membership flags, reserve-list flags, anchor date, pre/post metrics, and sector-relative metrics.
- `{output_dir / 'mwig40_sector_peer_panel.parquet'}`: one row per entrant-sector peer pair, useful for direct comparison between entrants and same-sector companies.
- `{output_dir / 'mwig40_price_panel.parquet'}`: historical OHLCV for candidate companies and sector peers, enriched with ticker and sector metadata.
- `{output_dir / 'mwig40_eda_panel_summary.csv'}`: compact per-revision coverage summary.
- `{ohlcv_path}`: broader downloaded OHLCV source used to build the EDA panels.

## Notebook Load Snippet

```python
from pathlib import Path
import pandas as pd

ROOT = Path.cwd()
EDA_DIR = ROOT / "output" / "eda"

event_panel = pd.read_parquet(EDA_DIR / "mwig40_event_panel.parquet")
sector_peer_panel = pd.read_parquet(EDA_DIR / "mwig40_sector_peer_panel.parquet")
price_panel = pd.read_parquet(EDA_DIR / "mwig40_price_panel.parquet")
summary = pd.read_csv(EDA_DIR / "mwig40_eda_panel_summary.csv", parse_dates=["revision_date", "anchor_date"])

event_panel["revision_date"] = pd.to_datetime(event_panel["revision_date"])
event_panel["anchor_date"] = pd.to_datetime(event_panel["anchor_date"])
price_panel["date"] = pd.to_datetime(price_panel["date"])
```

## Suggested First Filters

```python
REVISION_DATE = pd.Timestamp("{revision_end}")
FOCUS = event_panel[event_panel["revision_date"].eq(REVISION_DATE)]
ENTRANTS = FOCUS[FOCUS["entered_mwig40"]]
CANDIDATES = FOCUS[FOCUS["candidate_universe"]]
RESERVE = FOCUS[FOCUS["previous_mwig40_reserve"] | FOCUS["current_mwig40_reserve"]]
```

## Notes

- `entered_mwig40` and `exited_mwig40` are disabled for the first revision because there is no previous revision in the selected range.
- `anchor_date` uses the mWIG40 ranking date when available. The 2026-03-20 revision is overridden to 2026-02-20 to match the corrected replication and price anchor.
- Sector-relative columns end with `_vs_sector` and are calculated against the median of other companies in the same sector for the same revision.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portfolios", type=Path, default=DEFAULT_PORTFOLIOS)
    parser.add_argument("--reserves", type=Path, default=DEFAULT_RESERVES)
    parser.add_argument("--sector-map", type=Path, default=DEFAULT_SECTOR_MAP)
    parser.add_argument("--ohlcv", type=Path, default=DEFAULT_OHLCV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.ohlcv.exists():
        raise FileNotFoundError(f"Missing OHLCV file: {args.ohlcv}")

    transitions = load_transition_module()
    portfolios, reserves = transitions.load_inputs(args.portfolios, args.reserves)
    portfolios, reserves = normalize_dates(portfolios, reserves)
    events = transitions.build_transition_events(portfolios.copy(), reserves.copy())
    sector_map = pd.read_csv(args.sector_map).fillna("")
    ohlcv = pd.read_parquet(args.ohlcv)
    ohlcv["date"] = pd.to_datetime(ohlcv["date"])
    ohlcv = ohlcv.sort_values(["isin", "date"]).reset_index(drop=True)
    anchors = build_revision_anchors(portfolios)

    event_panel = build_event_panel(portfolios, reserves, sector_map, ohlcv, anchors, events)
    sector_peer_panel = build_sector_peer_panel(event_panel)

    relevant_isins = set(event_panel.loc[event_panel["candidate_universe"], "isin"])
    relevant_isins |= set(sector_peer_panel.get("peer_isin", pd.Series(dtype=str)).dropna())
    price_panel = ohlcv[ohlcv["isin"].isin(relevant_isins)].copy()
    latest_metadata = (
        event_panel.sort_values("revision_date")
        .drop_duplicates("isin", keep="last")[["isin", "ticker", "macrosector", "sector", "industry"]]
    )
    price_panel = price_panel.merge(latest_metadata, on="isin", how="left")
    price_panel = price_panel[
        ["isin", "ticker", "stooq_ticker", "macrosector", "sector", "industry", "date", "open", "high", "low", "close", "volume"]
    ]

    summary = build_summary(event_panel)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    event_panel.to_parquet(args.output_dir / "mwig40_event_panel.parquet", index=False)
    sector_peer_panel.to_parquet(args.output_dir / "mwig40_sector_peer_panel.parquet", index=False)
    price_panel.to_parquet(args.output_dir / "mwig40_price_panel.parquet", index=False)
    summary.to_csv(args.output_dir / "mwig40_eda_panel_summary.csv", index=False, encoding="utf-8")
    manifest = build_manifest(args.output_dir, event_panel, sector_peer_panel, price_panel, summary, args.ohlcv)
    (args.output_dir / "mwig40_eda_dataset_manifest.md").write_text(manifest, encoding="utf-8")

    print(f"Event panel: {len(event_panel):,} rows -> {args.output_dir / 'mwig40_event_panel.parquet'}")
    print(f"Sector peer panel: {len(sector_peer_panel):,} rows -> {args.output_dir / 'mwig40_sector_peer_panel.parquet'}")
    print(f"Price panel: {len(price_panel):,} rows -> {args.output_dir / 'mwig40_price_panel.parquet'}")
    print(f"Summary: {args.output_dir / 'mwig40_eda_panel_summary.csv'}")
    print(f"Manifest: {args.output_dir / 'mwig40_eda_dataset_manifest.md'}")
    print()
    print(summary.tail(8).to_string(index=False))


if __name__ == "__main__":
    main()
