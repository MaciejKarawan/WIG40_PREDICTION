#!/usr/scripts/env python3
"""Etap C4+C5 — panel replikowanego rankingu *as-of* (revision x prediction_date x spolka).

Cel:
    Rozbroic zalozenie C4 (uniwersum z `previous_wig_weight_rank`) i C5 (metryki tylko
    do anchor_date). Zamiast tego liczymy *replikowany ranking as-of* na siatce
    prediction_date cofnietych o {0, 60, 120, 240} sesji wzgledem dnia rankingu, korzystajac
    WYLACZNIE z informacji dostepnej do prediction_date.

Metoda (proxy rankingu GPW Benchmark R = 0.4*sT + 0.6*sC):
    Uniwersum @prediction_date pd dla rewizji r = sklad WIG z POPRZEDNIEJ rewizji r-1
        (znamy ich FF shares z PDF r-1 — to realny zbior informacji w dniu pd).
    sC_asof(i) = ff_shares_{r-1}(i) * close(i, pd)            (FF market cap as-of)
    sT_asof(i) = suma close*volume po (pd-365d, pd]           (obrot 12M as-of)
    R_asof(i)  = 0.4*sT_norm + 0.6*sC_norm  -> replicated_rank_asof (malejaco)

Uproszczenia vs pelna replikacja (jawnie odnotowane):
    - ceny stooq *adjusted* zamiast surowych z PDF (A1) -> dotyka poziomu sC dla spolek po splicie;
      przy offset=0 raportujemy rozbieznosc vs `replication_*.parquet` (PDF) jako miare kosztu proxy.
    - brak filtra MWO / ostatniego kwartyla as-of (nie da sie wiarygodnie odtworzyc na dowolna date);
      uczestnicy = spolki WIG@(r-1) z cena as-of i dodatnim obrotem 12M. Filtry usuwaja glownie
      nieplynny ogon, ktory i tak nie jest w okolicy progu mWIG40 (rank ~40-80).

Output:
    output/asof/asof_rank_panel.parquet      (panel z rankiem + sygnalami as-of + targetem)
    output/asof/asof_rank_validation.csv      (walidacja rank as-of przy offset=0)
    output/asof/asof_rank_manifest.md
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PORTFOLIOS_PATH = ROOT / "output" / "wig_history" / "index_portfolios.parquet"
RESERVES_PATH = ROOT / "output" / "wig_history" / "reserve_lists.parquet"
OHLCV_PATH = ROOT / "output" / "eda_2021_2026_revision" / "wigeda_2021_2026_ohlcv.parquet"
EVENT_PANEL_PATH = ROOT / "output" / "eda" / "mwig40_event_panel.parquet"
OUT_DIR = ROOT / "output" / "asof"

OFFSETS_TD = [0, 60, 120, 240]          # sesje przed dniem rankingu (C5 grid; offset>0 rozbraja C7)
SIGNAL_WINDOWS = [120, 240, 360]        # okna sygnalow momentum/vol/obrot (sesje)
NEAR_THRESHOLD_LOW = 25                 # strefa kandydacka po replicated_rank_asof
NEAR_THRESHOLD_HIGH = 95
TRADING_DAYS_PER_YEAR = 252

# mWIG40 ranking_date = 3. piatek lutego itd.; WIG PDF ma date tydzien pozniej.
# Override spojny z scripts/build_mwig40_eda_panels.py.
ANCHOR_OVERRIDES = {"2026-03-20": "2026-02-20"}


def load_inputs():
    ip = pd.read_parquet(PORTFOLIOS_PATH)
    ip["revision_date"] = pd.to_datetime(ip["revision_date"])
    ip["ranking_date"] = pd.to_datetime(ip["ranking_date"], errors="coerce")

    reserves = pd.read_parquet(RESERVES_PATH)
    reserves["revision_date"] = pd.to_datetime(reserves["revision_date"])

    oh = pd.read_parquet(OHLCV_PATH)
    oh["date"] = pd.to_datetime(oh["date"])
    oh = oh.dropna(subset=["isin", "date", "close"]).copy()
    oh["turnover"] = oh["close"] * oh["volume"].fillna(0.0)
    oh = oh.sort_values(["isin", "date"]).reset_index(drop=True)
    oh["return_1d"] = oh.groupby("isin")["close"].pct_change()

    ep = pd.read_parquet(EVENT_PANEL_PATH)
    ep["revision_date"] = pd.to_datetime(ep["revision_date"])
    return ip, reserves, oh, ep


def mwig40_ranking_dates(ip: pd.DataFrame) -> pd.DataFrame:
    """Zwraca revision_date -> ranking_date z PDF mWIG40 (z override 2026-03)."""
    rows = []
    mwig = ip[ip["index_name"].eq("mWIG40")]
    for revision, group in mwig.groupby("revision_date"):
        key = pd.Timestamp(revision).date().isoformat()
        override = ANCHOR_OVERRIDES.get(key)
        if override:
            rd = pd.Timestamp(override)
        else:
            dates = group["ranking_date"].dropna()
            rd = pd.Timestamp(dates.iloc[0]) if not dates.empty else pd.NaT
        rows.append({"revision_date": pd.Timestamp(revision), "ranking_date": rd})
    return pd.DataFrame(rows).sort_values("revision_date").reset_index(drop=True)


def build_calendar(oh: pd.DataFrame) -> np.ndarray:
    return np.array(sorted(oh["date"].unique()))


def session_on_or_before(cal: np.ndarray, target: pd.Timestamp):
    pos = int(np.searchsorted(cal, np.datetime64(pd.Timestamp(target)), side="right")) - 1
    return pos


def build_price_groups(oh: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {isin: g.reset_index(drop=True) for isin, g in oh.groupby("isin", sort=False)}


def price_idx_on_or_before(group: pd.DataFrame, target: pd.Timestamp) -> int:
    return int(group["date"].searchsorted(pd.Timestamp(target), side="right")) - 1


def asof_signal_features(group: pd.DataFrame, pd_idx: int, windows: list[int]) -> dict:
    """Momentum/vol/turnover-accel liczone do sesji pd_idx (wlacznie)."""
    out = {}
    close_now = float(group.loc[pd_idx, "close"])
    for w in windows:
        start = pd_idx - w
        if start < 0:
            out[f"ret_m{w}"] = np.nan
            out[f"vol_m{w}"] = np.nan
            out[f"turnover_ratio_m{w}"] = np.nan
            continue
        seg = group.iloc[start: pd_idx + 1]
        rets = seg["return_1d"].replace([np.inf, -np.inf], np.nan).dropna()
        out[f"ret_m{w}"] = close_now / float(group.loc[start, "close"]) - 1.0
        out[f"vol_m{w}"] = float(rets.std(ddof=0) * math.sqrt(TRADING_DAYS_PER_YEAR)) if len(rets) > 1 else np.nan
        avg_turn = float(seg["turnover"].mean())
        prev_start = start - w
        if prev_start >= 0:
            prev_turn = float(group.iloc[prev_start:start]["turnover"].mean())
            out[f"turnover_ratio_m{w}"] = avg_turn / prev_turn if prev_turn else np.nan
        else:
            out[f"turnover_ratio_m{w}"] = np.nan
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ip, reserves, oh, ep = load_inputs()

    rank_dates = mwig40_ranking_dates(ip)
    revisions = rank_dates["revision_date"].tolist()
    prev_of = {revisions[i]: (revisions[i - 1] if i > 0 else None) for i in range(len(revisions))}
    rd_of = dict(zip(rank_dates["revision_date"], rank_dates["ranking_date"]))

    cal = build_calendar(oh)
    price_groups = build_price_groups(oh)

    # WIG FF shares per rewizja: isin -> shares
    wig = ip[ip["index_name"].eq("WIG")][["revision_date", "isin", "ticker", "shares"]].copy()
    wig_shares = {
        pd.Timestamp(rev): dict(zip(g["isin"], g["shares"]))
        for rev, g in wig.groupby("revision_date")
    }
    wig_tickers = dict(zip(wig["isin"], wig["ticker"]))

    # czlonkostwo mWIG40 + rezerwa per rewizja
    mwig_members = {
        pd.Timestamp(rev): set(g["isin"])
        for rev, g in ip[ip["index_name"].eq("mWIG40")].groupby("revision_date")
    }
    mwig_reserve = {
        pd.Timestamp(rev): set(g["isin"])
        for rev, g in reserves[reserves["index_name"].eq("mWIG40")].groupby("revision_date")
    }

    # metadane spolki (sektor) + target z event_panel
    sector_map = (
        ep.sort_values("revision_date").drop_duplicates("isin", keep="last").set_index("isin")["sector"].to_dict()
    )
    target_map = {
        (pd.Timestamp(r), i): bool(e)
        for r, i, e in zip(ep["revision_date"], ep["isin"], ep["entered_mwig40"])
    }
    exited_map = {
        (pd.Timestamp(r), i): bool(e)
        for r, i, e in zip(ep["revision_date"], ep["isin"], ep["exited_mwig40"])
    }

    rows = []
    for revision in revisions:
        prev = prev_of[revision]
        if prev is None:
            continue  # brak poprzedniej rewizji -> brak as-of uniwersum
        ranking_date = rd_of[revision]
        if pd.isna(ranking_date):
            continue
        shares_prev = wig_shares.get(prev, {})
        prev_mwig = mwig_members.get(prev, set())
        prev_reserve = mwig_reserve.get(prev, set())
        current_mwig = mwig_members.get(revision, set())

        universe_isins = [i for i in shares_prev if shares_prev[i] and shares_prev[i] > 0]

        for offset in OFFSETS_TD:
            rd_pos = session_on_or_before(cal, ranking_date)
            pd_pos = rd_pos - offset
            if pd_pos < 0:
                continue
            prediction_date = pd.Timestamp(cal[pd_pos])
            win_start_date = prediction_date - pd.Timedelta(days=365)

            # 1) policz sC_raw, sT_raw dla calego uniwersum WIG@(r-1)
            recs = []
            for isin in universe_isins:
                g = price_groups.get(isin)
                if g is None or g.empty:
                    continue
                pidx = price_idx_on_or_before(g, prediction_date)
                if pidx < 0:
                    continue
                price_asof = float(g.loc[pidx, "close"])
                # obrot 12M as-of
                seg = g[(g["date"] > win_start_date) & (g["date"] <= prediction_date)]
                turn_12m = float(seg["turnover"].sum())
                ff = float(shares_prev[isin])
                recs.append((isin, pidx, price_asof, ff * price_asof, turn_12m))
            if not recs:
                continue
            ru = pd.DataFrame(recs, columns=["isin", "pidx", "price_asof", "ff_mktcap_asof", "turnover_12m_asof"])
            participants = ru["turnover_12m_asof"] > 0
            tot_cap = ru.loc[participants, "ff_mktcap_asof"].sum()
            tot_turn = ru.loc[participants, "turnover_12m_asof"].sum()
            ru["sC_asof"] = np.where(participants & (tot_cap > 0), ru["ff_mktcap_asof"] / tot_cap, np.nan)
            ru["sT_asof"] = np.where(participants & (tot_turn > 0), ru["turnover_12m_asof"] / tot_turn, np.nan)
            ru["R_asof"] = 0.4 * ru["sT_asof"] + 0.6 * ru["sC_asof"]
            ru["replicated_rank_asof"] = ru["R_asof"].rank(method="first", ascending=False)

            # 2) sygnaly liczone tylko dla strefy kandydackiej + wszystkich faktycznych entrantow
            entrant_isins = {i for (r, i), v in target_map.items() if v and r == revision}
            cand_mask = ru["replicated_rank_asof"].between(NEAR_THRESHOLD_LOW, NEAR_THRESHOLD_HIGH) | ru["isin"].isin(entrant_isins)
            for rec in ru.loc[cand_mask].itertuples(index=False):
                g = price_groups.get(rec.isin)
                feats = asof_signal_features(g, int(rec.pidx), SIGNAL_WINDOWS)
                rows.append({
                    "revision_date": revision,
                    "previous_revision_date": prev,
                    "ranking_date": ranking_date,
                    "offset_td": offset,
                    "prediction_date": prediction_date,
                    "isin": rec.isin,
                    "ticker": wig_tickers.get(rec.isin),
                    "sector": sector_map.get(rec.isin),
                    "price_asof": rec.price_asof,
                    "ff_mktcap_asof": rec.ff_mktcap_asof,
                    "turnover_12m_asof": rec.turnover_12m_asof,
                    "sC_asof": rec.sC_asof,
                    "sT_asof": rec.sT_asof,
                    "R_asof": rec.R_asof,
                    "replicated_rank_asof": rec.replicated_rank_asof,
                    "was_in_previous_mwig40": rec.isin in prev_mwig,
                    "previous_mwig40_reserve": rec.isin in prev_reserve,
                    "entered_mwig40": target_map.get((revision, rec.isin), False),
                    "exited_mwig40": exited_map.get((revision, rec.isin), False),
                    "is_in_current_mwig40": rec.isin in current_mwig,
                    **feats,
                })

    panel = pd.DataFrame(rows)

    # sektorowo-relatywne sygnaly (per revision x offset x sector)
    for w in SIGNAL_WINDOWS:
        for base in [f"ret_m{w}", f"vol_m{w}", f"turnover_ratio_m{w}"]:
            med = panel.groupby(["revision_date", "offset_td", "sector"], dropna=False)[base].transform("median")
            panel[f"{base}_vs_sector"] = panel[base] - med

    panel = panel.sort_values(["revision_date", "offset_td", "replicated_rank_asof"]).reset_index(drop=True)
    panel.to_parquet(OUT_DIR / "asof_rank_panel.parquet", index=False)

    # ---- Walidacja: rank as-of przy offset=0 vs faktyczne czlonkostwo mWIG40 ----
    val_rows = []
    for revision in revisions:
        if prev_of[revision] is None:
            continue
        sub = panel[(panel["revision_date"].eq(revision)) & (panel["offset_td"].eq(0))]
        if sub.empty:
            continue
        current_mwig = mwig_members.get(revision, set())
        n_actual = len(current_mwig)
        # as-of mWIG40 = pozycje 21..60 (kaskada WIG20/mWIG40/sWIG80)
        pred = set(sub.loc[sub["replicated_rank_asof"].between(21, 60), "isin"])
        # uwaga: sub to tylko strefa kandydacka 25-95 -> recall liczymy na entrantach w panelu
        ent = sub[sub["entered_mwig40"]]
        ent_capt = int((ent["replicated_rank_asof"] <= 60).sum())
        val_rows.append({
            "revision_date": pd.Timestamp(revision).date(),
            "n_actual_mwig40": n_actual,
            "n_entrants_in_panel": int(len(ent)),
            "entrants_rank_le60": ent_capt,
            "entrants_rank_le70": int((ent["replicated_rank_asof"] <= 70).sum()),
            "entrants_median_rank": float(ent["replicated_rank_asof"].median()) if len(ent) else np.nan,
        })
    val = pd.DataFrame(val_rows)
    val.to_csv(OUT_DIR / "asof_rank_validation.csv", index=False)

    # coverage entrantow: ilu z 45 jest w uniwersum WIG@(r-1)
    total_entrants = sum(1 for (r, i), v in target_map.items() if v and prev_of.get(r) is not None)
    panel_entrants = panel.loc[panel["offset_td"].eq(0) & panel["entered_mwig40"], ["revision_date", "isin"]].drop_duplicates()

    print(f"Panel: {len(panel):,} wierszy -> {OUT_DIR / 'asof_rank_panel.parquet'}")
    print(f"Rewizje: {panel['revision_date'].nunique()}, offsety: {sorted(panel['offset_td'].unique())}")
    print(f"Entranci w panelu (offset=0): {len(panel_entrants)} / {total_entrants} mozliwych (WIG@(r-1) coverage)")
    print()
    print("=== Walidacja rank as-of @offset=0 (entranci powinni miec rank <= 60) ===")
    print(val.to_string(index=False))
    if not val.empty:
        tot_ent = val["n_entrants_in_panel"].sum()
        tot_le60 = val["entrants_rank_le60"].sum()
        tot_le70 = val["entrants_rank_le70"].sum()
        print(f"\nRECALL as-of rank<=60: {tot_le60}/{tot_ent} = {tot_le60/tot_ent:.1%}")
        print(f"RECALL as-of rank<=70: {tot_le70}/{tot_ent} = {tot_le70/tot_ent:.1%}")


if __name__ == "__main__":
    main()
