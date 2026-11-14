#!/usr/bin/env python3
"""Etapy C7 -> placebo -> koszty+survivorship -> OOS+outliery na panelu as-of.

Wejscie:
    output/asof/asof_rank_panel.parquet                (z bin/build_asof_rank_panel.py)
    output/eda_2021_2026_revision/wigeda_2021_2026_ohlcv.parquet

Realizuje kolejnosc z reports/strategie_i_poprawny_backtest.md:
    1. C7  — lift/precision predykcji wejscia wg offsetu (0/60/120/240 sesji przed rankingiem).
             Offset=0 ~ tautologia (sygnal pokrywa sie z oknem s_T); offset 240 = prawdziwy lead.
    2. placebo — czy score (rezerwa+momentum+vol+obrot) separuje forward-return ponad
             surowy near-threshold (czysta beta small-capow przy progu)?
    3. koszty+survivorship — strategia S1 (akumulacja kandydatow, wyjscie przy rewizji)
             z kosztami round-trip i JAWNA obsluga brakujacych cen / delistingu.
    4. OOS + outliery — split train(<=2023) / test(>=2024), leave-one-stock-out, benchmark.

Wyjscie: output/backtests_asof/*.csv + raport reports/backtest_asof_wyniki.md
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PANEL_PATH = ROOT / "output" / "asof" / "asof_rank_panel.parquet"
OHLCV_PATH = ROOT / "output" / "eda_2021_2026_revision" / "wigeda_2021_2026_ohlcv.parquet"
OUT_DIR = ROOT / "output" / "backtests_asof"
REPORT_PATH = ROOT / "reports" / "backtest_asof_wyniki.md"

SCORE_WINDOW = 360                 # glowne okno sygnalu (najsilniejsze wg EDA)
TOP_PCT = 0.25                     # top-X% w strefie kandydackiej per (revision, offset)
SCORE_THRESHOLDS = [2, 3]
RANK_ENTRY_ZONE = (40, 70)         # strefa wejscia po replicated_rank_asof
COST_BPS_GRID = [0, 50, 100, 150]  # round-trip w bps
OOS_SPLIT = pd.Timestamp("2024-01-01")
DELIST_TOLERANCE_TD = 15           # ile sesji braku ceny przed rankingiem = delisting


# ---------------------------------------------------------------------------
# Ladowanie + ceny
# ---------------------------------------------------------------------------

def load_panel() -> pd.DataFrame:
    p = pd.read_parquet(PANEL_PATH)
    for c in ["revision_date", "previous_revision_date", "ranking_date", "prediction_date"]:
        p[c] = pd.to_datetime(p[c])
    return p


def load_price_groups() -> tuple[dict[str, pd.DataFrame], pd.Timestamp]:
    oh = pd.read_parquet(OHLCV_PATH)
    oh["date"] = pd.to_datetime(oh["date"])
    oh = oh.dropna(subset=["isin", "date", "close"]).sort_values(["isin", "date"]).reset_index(drop=True)
    groups = {isin: g.reset_index(drop=True) for isin, g in oh.groupby("isin", sort=False)}
    return groups, pd.Timestamp(oh["date"].max())


def entry_next_open(group: pd.DataFrame, prediction_date: pd.Timestamp):
    """Egzekucja t+1: pierwsza sesja PO prediction_date; open jesli jest, inaczej close."""
    pos = int(group["date"].searchsorted(pd.Timestamp(prediction_date), side="right"))
    if pos >= len(group):
        return None
    row = group.loc[pos]
    price = row["open"] if pd.notna(row.get("open")) else row["close"]
    return pd.Timestamp(row["date"]), float(price)


def exit_at_revision(group: pd.DataFrame, revision_date: pd.Timestamp, last_data_date: pd.Timestamp):
    """Cena wyjscia = close na/przed revision_date. Zwraca (date, price, delisted_flag)."""
    pos = int(group["date"].searchsorted(pd.Timestamp(revision_date), side="right")) - 1
    if pos < 0:
        return None
    row = group.loc[pos]
    exit_date = pd.Timestamp(row["date"])
    # delisting: ostatnia dostepna sesja jest znacznie przed rewizja, a dane globalnie sa swiezsze
    gap_sessions = int(group["date"].searchsorted(pd.Timestamp(revision_date), side="right")) - 1 - pos
    delisted = (exit_date < pd.Timestamp(revision_date) - pd.Timedelta(days=10)) and (last_data_date > pd.Timestamp(revision_date))
    return exit_date, float(row["close"]), bool(delisted)


# ---------------------------------------------------------------------------
# Score as-of (rezerwa + top momentum/vol/obrot vs sektor, per revision x offset)
# ---------------------------------------------------------------------------

def add_asof_score(panel: pd.DataFrame, window: int) -> pd.DataFrame:
    out = panel.copy()
    feats = {
        "top_momentum": f"ret_m{window}_vs_sector",
        "top_turnover_accel": f"turnover_ratio_m{window}_vs_sector",
        "top_volatility": f"vol_m{window}_vs_sector",
    }
    for flag, metric in feats.items():
        out[flag] = False
        for _, idx in out.groupby(["revision_date", "offset_td"]).groups.items():
            grp = out.loc[idx]
            valid = grp[grp[metric].notna()]
            if valid.empty:
                continue
            n_sel = max(1, int(math.ceil(len(valid) * TOP_PCT)))
            out.loc[valid.nlargest(n_sel, metric).index, flag] = True
    out["score_reserve"] = out["previous_mwig40_reserve"].fillna(False)
    out["asof_score"] = (
        out["score_reserve"].astype(int)
        + out["top_momentum"].astype(int)
        + out["top_turnover_accel"].astype(int)
        + out["top_volatility"].astype(int)
    )
    return out


# ---------------------------------------------------------------------------
# 1. C7 — lift wg offsetu
# ---------------------------------------------------------------------------

def lift_by_offset(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for offset, grp in panel.groupby("offset_td"):
        base_rate = float(grp["entered_mwig40"].mean())
        n_entrants = int(grp["entered_mwig40"].sum())
        # selekcja A: replikowany rank as-of <= K
        for k in [50, 60, 70]:
            sel = grp[grp["replicated_rank_asof"] <= k]
            prec = float(sel["entered_mwig40"].mean()) if len(sel) else np.nan
            rows.append({
                "offset_td": int(offset), "rule": f"rank_le_{k}", "n_selected": int(len(sel)),
                "n_entrants_selected": int(sel["entered_mwig40"].sum()),
                "precision": prec, "recall": (int(sel["entered_mwig40"].sum()) / n_entrants) if n_entrants else np.nan,
                "baseline_rate": base_rate, "lift": prec / base_rate if base_rate and prec == prec else np.nan,
            })
        # selekcja B: asof_score >= s
        for s in SCORE_THRESHOLDS:
            sel = grp[grp["asof_score"] >= s]
            prec = float(sel["entered_mwig40"].mean()) if len(sel) else np.nan
            rows.append({
                "offset_td": int(offset), "rule": f"score_ge_{s}", "n_selected": int(len(sel)),
                "n_entrants_selected": int(sel["entered_mwig40"].sum()),
                "precision": prec, "recall": (int(sel["entered_mwig40"].sum()) / n_entrants) if n_entrants else np.nan,
                "baseline_rate": base_rate, "lift": prec / base_rate if base_rate and prec == prec else np.nan,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Forward returns: prediction_date(t+1 open) -> revision_date(close)
# ---------------------------------------------------------------------------

def attach_forward_returns(panel: pd.DataFrame, groups, last_data_date) -> pd.DataFrame:
    out = panel.copy()
    entry_p, exit_p, entry_d, exit_d, delisted = [], [], [], [], []
    for r in out.itertuples(index=False):
        g = groups.get(r.isin)
        if g is None or g.empty:
            entry_p.append(np.nan); exit_p.append(np.nan); entry_d.append(pd.NaT); exit_d.append(pd.NaT); delisted.append(False); continue
        e = entry_next_open(g, r.prediction_date)
        x = exit_at_revision(g, r.revision_date, last_data_date)
        if e is None or x is None:
            entry_p.append(np.nan); exit_p.append(np.nan); entry_d.append(pd.NaT); exit_d.append(pd.NaT); delisted.append(False); continue
        ed, ep = e; xd, xp, dl = x
        entry_p.append(ep); exit_p.append(xp); entry_d.append(ed); exit_d.append(xd); delisted.append(dl)
    out["entry_price"] = entry_p
    out["exit_price"] = exit_p
    out["entry_trading_date"] = entry_d
    out["exit_trading_date"] = exit_d
    out["delisted"] = delisted
    out["gross_return"] = out["exit_price"] / out["entry_price"] - 1.0
    out["holding_days"] = (pd.to_datetime(out["exit_trading_date"]) - pd.to_datetime(out["entry_trading_date"])).dt.days
    return out


# ---------------------------------------------------------------------------
# 2. Placebo — czy score separuje forward-return ponad near-threshold beta?
# ---------------------------------------------------------------------------

def placebo_table(fr: pd.DataFrame) -> pd.DataFrame:
    rows = []
    valid = fr[fr["gross_return"].notna()]
    for offset, grp in valid.groupby("offset_td"):
        base = grp["gross_return"]
        bench_mean = float(base.mean())
        for s in SCORE_THRESHOLDS:
            sel = grp[grp["asof_score"] >= s]["gross_return"]
            rows.append({
                "offset_td": int(offset), "bucket": f"score_ge_{s}",
                "n": int(len(sel)), "mean_return": float(sel.mean()) if len(sel) else np.nan,
                "median_return": float(sel.median()) if len(sel) else np.nan,
                "near_threshold_mean": bench_mean,
                "alpha_vs_near_threshold": (float(sel.mean()) - bench_mean) if len(sel) else np.nan,
            })
        # czysta beta near-threshold (placebo)
        rows.append({
            "offset_td": int(offset), "bucket": "near_threshold_all",
            "n": int(len(base)), "mean_return": bench_mean, "median_return": float(base.median()),
            "near_threshold_mean": bench_mean, "alpha_vs_near_threshold": 0.0,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 3. Strategia S1 z kosztami + survivorship; agregaty per (offset, score, cost)
# ---------------------------------------------------------------------------

def run_strategy(fr: pd.DataFrame, offset: int, score_threshold: int, cost_bps: int) -> pd.DataFrame:
    sel = fr[(fr["offset_td"].eq(offset)) & (fr["asof_score"] >= score_threshold)].copy()
    sel = sel[sel["entry_price"].notna() & sel["exit_price"].notna()]
    sel["net_return"] = sel["gross_return"] - cost_bps / 1e4
    sel["offset_td"] = offset
    sel["score_threshold"] = score_threshold
    sel["cost_bps"] = cost_bps
    return sel


def summarize_trades(trades: pd.DataFrame, label: dict) -> dict:
    if trades.empty:
        return {**label, "n_trades": 0}
    r = trades["net_return"]
    # rownowazony portfel per rewizja -> srednia z rewizyjnych srednich (kontrola koncentracji)
    per_rev = trades.groupby("revision_date")["net_return"].mean()
    return {
        **label,
        "n_trades": int(len(trades)),
        "n_unique_stocks": int(trades["isin"].nunique()),
        "n_revisions": int(trades["revision_date"].nunique()),
        "n_delisted": int(trades["delisted"].sum()),
        "mean_return": float(r.mean()),
        "median_return": float(r.median()),
        "win_rate": float((r > 0).mean()),
        "entered_share": float(trades["entered_mwig40"].mean()),
        "equalrev_mean": float(per_rev.mean()),
        "equalrev_total_compounded": float((1 + per_rev).prod() - 1),
        "mean_holding_days": float(trades["holding_days"].mean()),
    }


# ---------------------------------------------------------------------------
# 4. OOS + outliery
# ---------------------------------------------------------------------------

def oos_split(fr: pd.DataFrame, offset: int, score_threshold: int, cost_bps: int) -> pd.DataFrame:
    trades = run_strategy(fr, offset, score_threshold, cost_bps)
    rows = []
    for name, mask in [("train_<=2023", trades["revision_date"] < OOS_SPLIT), ("test_>=2024", trades["revision_date"] >= OOS_SPLIT)]:
        rows.append(summarize_trades(trades[mask], {"split": name, "offset_td": offset, "score_threshold": score_threshold, "cost_bps": cost_bps}))
    return pd.DataFrame(rows)


def leave_one_stock_out(fr: pd.DataFrame, offset: int, score_threshold: int, cost_bps: int) -> pd.DataFrame:
    trades = run_strategy(fr, offset, score_threshold, cost_bps)
    if trades.empty:
        return pd.DataFrame()
    full_mean = float(trades.groupby("revision_date")["net_return"].mean().mean())
    rows = []
    for isin in trades["isin"].unique():
        rest = trades[trades["isin"] != isin]
        per_rev = rest.groupby("revision_date")["net_return"].mean()
        m = float(per_rev.mean()) if len(per_rev) else np.nan
        rows.append({"dropped_isin": isin, "dropped_ticker": trades[trades["isin"].eq(isin)]["ticker"].iloc[0],
                     "n_trades_dropped": int((trades["isin"].eq(isin)).sum()),
                     "equalrev_mean_without": m, "delta_vs_full": m - full_mean})
    return pd.DataFrame(rows).sort_values("delta_vs_full")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    panel = load_panel()
    groups, last_data_date = load_price_groups()
    panel = add_asof_score(panel, SCORE_WINDOW)

    # 1. C7
    lift = lift_by_offset(panel)
    lift.to_csv(OUT_DIR / "asof_lift_by_offset.csv", index=False)

    # forward returns dla calego panelu (potrzebne do placebo + strategii)
    fr = attach_forward_returns(panel, groups, last_data_date)
    fr.to_parquet(OUT_DIR / "asof_forward_returns.parquet", index=False)

    # 2. placebo
    placebo = placebo_table(fr)
    placebo.to_csv(OUT_DIR / "asof_placebo.csv", index=False)

    # 3. strategia: agregaty per (offset, score, cost)
    summ_rows = []
    trade_parts = []
    for offset in sorted(panel["offset_td"].unique()):
        for s in SCORE_THRESHOLDS:
            for cost in COST_BPS_GRID:
                tr = run_strategy(fr, int(offset), s, cost)
                summ_rows.append(summarize_trades(tr, {"offset_td": int(offset), "score_threshold": s, "cost_bps": cost}))
                if cost == 100 and not tr.empty:
                    trade_parts.append(tr)
    strat = pd.DataFrame(summ_rows)
    strat.to_csv(OUT_DIR / "asof_strategy_summary.csv", index=False)
    if trade_parts:
        keep = ["revision_date", "offset_td", "score_threshold", "cost_bps", "isin", "ticker", "sector",
                "replicated_rank_asof", "asof_score", "entered_mwig40", "delisted",
                "entry_trading_date", "entry_price", "exit_trading_date", "exit_price",
                "gross_return", "net_return", "holding_days"]
        all_tr = pd.concat(trade_parts, ignore_index=True)[keep]
        all_tr.to_csv(OUT_DIR / "asof_strategy_trades.csv", index=False)

    # 4. OOS + LOO dla glownej konfiguracji (offset=120, score>=3, cost=100) z fallbackiem
    main_cfg = None
    for offset in [120, 60, 240, 0]:
        if not fr[(fr["offset_td"].eq(offset)) & (fr["asof_score"] >= 3) & fr["entry_price"].notna() & fr["exit_price"].notna()].empty:
            main_cfg = (offset, 3, 100); break
    if main_cfg is None:
        main_cfg = (60, 2, 100)
    oos = oos_split(fr, *main_cfg)
    oos.to_csv(OUT_DIR / "asof_oos_split.csv", index=False)
    loo = leave_one_stock_out(fr, *main_cfg)
    loo.to_csv(OUT_DIR / "asof_leave_one_out.csv", index=False)

    # ---- konsola ----
    pd.set_option("display.width", 200); pd.set_option("display.max_columns", 40)
    print("=== 1. C7 — LIFT WG OFFSETU (offset=0 ~ tautologia; 240 = prawdziwy lead) ===")
    print(lift.to_string(index=False))
    print("\n=== 2. PLACEBO — forward return prediction->rewizja; alpha vs near-threshold beta ===")
    print(placebo.to_string(index=False))
    print("\n=== 3. STRATEGIA S1 — agregaty (equalrev = srednia rewizyjna, kontrola koncentracji) ===")
    cols = ["offset_td", "score_threshold", "cost_bps", "n_trades", "n_unique_stocks", "n_delisted",
            "mean_return", "median_return", "win_rate", "entered_share", "equalrev_mean", "mean_holding_days"]
    print(strat[cols].to_string(index=False))
    print(f"\n=== 4. OOS split (cfg offset={main_cfg[0]}, score>={main_cfg[1]}, cost={main_cfg[2]}bps) ===")
    print(oos.to_string(index=False))
    print("\n=== 4. Leave-one-stock-out (najbardziej wplywowe spolki) ===")
    if not loo.empty:
        print(pd.concat([loo.head(3), loo.tail(3)]).to_string(index=False))
    print(f"\nArtefakty -> {OUT_DIR}")


if __name__ == "__main__":
    main()
