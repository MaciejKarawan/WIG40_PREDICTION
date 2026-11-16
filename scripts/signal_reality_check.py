#!/usr/scripts/env python3
"""Reality check S1 — czy sygnal ery dev jest realny? (spec: reports/research_log.md, wpis PLAN 2026-07-02)

Testy (reguly decyzyjne zamrozone PRZED runem):
    T1  bootstrap klastrowy po rewizjach -> 95% CI dla equalrev-alfy (score>=3 vs near-threshold)
    T2  permutacja w obrebie rewizji (null: losowa selekcja tej samej licznosci) -> p deflowane (<0.005)
    T3  uczciwy bench TR (sWIG80TR primary, mWIG40TR secondary) -> equalrev-excess + CI
    T4  rezim: rewizje <2024 vs >=2024 + sign-test po rewizjach
    T5  survivorship: ISINy WIG@(r-1) nieobecne w OHLCV (ciche wypadniecie z uniwersum) + delisted w poolu
    T6  leave-one-revision-out dla equalrev-alfy

Wejscie: output/backtests_asof/asof_forward_returns.parquet (Etap 5 — sygnal NIE jest tu modyfikowany)
Wyjscie: output/signal_check/*.csv
"""

from __future__ import annotations
import os

import io
import math
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FR_PATH = ROOT / "output" / "backtests_asof" / "asof_forward_returns.parquet"
PORTFOLIOS_PATH = ROOT / "output" / "wig_history" / "index_portfolios.parquet"
OHLCV_PATH = ROOT / "output" / "eda_2021_2026_revision" / "wigeda_2021_2026_ohlcv.parquet"
BENCH_CACHE = ROOT / "data" / "stooq_cache_bench"
OUT_DIR = ROOT / "output" / "signal_check"

SCORE_MIN = 3                      # prog strategii S1 (handoff: 3, nie 4)
OFFSETS = [0, 60, 120, 240]        # primary=240, secondary=120 (spec)
PRIMARY_OFFSET = 240
N_BOOT = 10_000
N_PERM = 10_000
SEED = 42
OOS_SPLIT = pd.Timestamp("2024-01-01")
BENCH_SYMBOLS = ["swig80tr", "mwig40tr", "wig"]   # wig = fallback kontekstowy
P_DEFLATED = 0.005

STOOQ_CSV_URL = "https://stooq.pl/q/d/l/"
STOOQ_API_KEY = "a3xtYFdVDKUPQ7mN50Ec2Mf1To4BvH69"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


# ---------------------------------------------------------------------------
# Dane
# ---------------------------------------------------------------------------

def load_forward_returns() -> pd.DataFrame:
    fr = pd.read_parquet(FR_PATH)
    for c in ["revision_date", "previous_revision_date", "prediction_date",
              "entry_trading_date", "exit_trading_date"]:
        fr[c] = pd.to_datetime(fr[c])
    need = {"offset_td", "asof_score", "gross_return", "entered_mwig40", "delisted",
            "replicated_rank_asof", "isin", "ticker"}
    missing = need - set(fr.columns)
    if missing:
        raise SystemExit(f"Brak kolumn w {FR_PATH.name}: {missing}")
    return fr


def per_revision_alpha(sub: pd.DataFrame) -> pd.DataFrame:
    """Dla jednego offsetu: alpha_r = mean(score>=3) - mean(pool) w obrebie rewizji."""
    rows = []
    for rev, pool in sub.groupby("revision_date"):
        sel = pool[pool["asof_score"] >= SCORE_MIN]
        if sel.empty:
            continue
        rows.append({
            "revision_date": rev,
            "n_pool": int(len(pool)),
            "n_sel": int(len(sel)),
            "n_sel_entered": int(sel["entered_mwig40"].sum()),
            "pool_mean": float(pool["gross_return"].mean()),
            "sel_mean": float(sel["gross_return"].mean()),
            "alpha": float(sel["gross_return"].mean() - pool["gross_return"].mean()),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# T1 — bootstrap klastrowy po rewizjach
# ---------------------------------------------------------------------------

def bootstrap_ci(values: np.ndarray, n_boot: int, rng: np.random.Generator) -> tuple[float, float]:
    n = len(values)
    idx = rng.integers(0, n, size=(n_boot, n))
    means = values[idx].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


# ---------------------------------------------------------------------------
# T2 — permutacja w obrebie rewizji
# ---------------------------------------------------------------------------

def permutation_test(sub: pd.DataFrame, n_perm: int, rng: np.random.Generator) -> dict:
    """Null: w kazdej rewizji losowa selekcja n_sel z near-threshold poola.

    Zwraca p one-sided dla equalrev-alfy (zwroty) i pooled precision (entered_mwig40).
    """
    pools = []
    for rev, pool in sub.groupby("revision_date"):
        sel = pool[pool["asof_score"] >= SCORE_MIN]
        if sel.empty:
            continue
        pools.append({
            "returns": pool["gross_return"].to_numpy(),
            "entered": pool["entered_mwig40"].to_numpy().astype(bool),
            "k": int(len(sel)),
            "pool_mean": float(pool["gross_return"].mean()),
            "obs_alpha": float(sel["gross_return"].mean() - pool["gross_return"].mean()),
            "obs_entered": int(sel["entered_mwig40"].sum()),
        })
    if not pools:
        return {}
    obs_alpha = float(np.mean([p["obs_alpha"] for p in pools]))
    total_k = sum(p["k"] for p in pools)
    obs_precision = sum(p["obs_entered"] for p in pools) / total_k

    perm_alpha = np.empty(n_perm)
    perm_prec = np.empty(n_perm)
    for i in range(n_perm):
        alphas = np.empty(len(pools))
        entered_cnt = 0
        for j, p in enumerate(pools):
            pick = rng.choice(len(p["returns"]), size=p["k"], replace=False)
            alphas[j] = p["returns"][pick].mean() - p["pool_mean"]
            entered_cnt += int(p["entered"][pick].sum())
        perm_alpha[i] = alphas.mean()
        perm_prec[i] = entered_cnt / total_k
    p_alpha = (1 + int((perm_alpha >= obs_alpha).sum())) / (1 + n_perm)
    p_prec = (1 + int((perm_prec >= obs_precision).sum())) / (1 + n_perm)
    return {
        "n_revisions": len(pools), "n_trades": total_k,
        "obs_equalrev_alpha": obs_alpha, "p_perm_alpha": p_alpha,
        "obs_precision": obs_precision, "p_perm_precision": p_prec,
        "null_alpha_p95": float(np.percentile(perm_alpha, 95)),
        "null_alpha_p99_5": float(np.percentile(perm_alpha, 99.5)),
    }


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return centre - half, centre + half


# ---------------------------------------------------------------------------
# T3 — bench TR ze stooq
# ---------------------------------------------------------------------------

LOCAL_BENCH_DIR = Path(os.environ.get("MWIG_BENCH_DIR", str(ROOT / "data" / "raw" / "benchmarks")))


def fetch_bench(symbol: str, d1: date, d2: date) -> pd.DataFrame | None:
    """Zrodlo benchu: lokalny bulk stooq z projektu MOMENTUM (API stooq gate'owane JS challengem);
    fallback = pobranie CSV z cache/API. Zwraca DataFrame(date, close) lub None."""
    local = LOCAL_BENCH_DIR / f"{symbol}.txt"
    if local.exists():
        df = pd.read_csv(local)
        df.columns = [c.strip("<>").lower() for c in df.columns]
        out = pd.DataFrame({"date": pd.to_datetime(df["date"], format="%Y%m%d"),
                            "close": df["close"].astype(float)})
        out = out[(out["date"] >= pd.Timestamp(d1)) & (out["date"] <= pd.Timestamp(d2))]
        return out.dropna().sort_values("date").reset_index(drop=True)
    BENCH_CACHE.mkdir(parents=True, exist_ok=True)
    cache = BENCH_CACHE / f"{symbol}.csv"
    raw: str | None = None
    if cache.exists() and cache.stat().st_size > 200:
        raw = cache.read_text(encoding="utf-8")
    else:
        try:
            import requests
            url = (f"{STOOQ_CSV_URL}?s={symbol}&d1={d1.strftime('%Y%m%d')}"
                   f"&d2={d2.strftime('%Y%m%d')}&i=d&apikey={STOOQ_API_KEY}")
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
            if resp.status_code == 200 and len(resp.text) > 200:
                raw = resp.text
                cache.write_text(raw, encoding="utf-8")
            time.sleep(1.0)
        except Exception as exc:  # noqa: BLE001 — brak sieci itp.
            print(f"[T3] {symbol}: blad pobierania ({exc})")
            return None
    if raw is None:
        print(f"[T3] {symbol}: brak danych (status/limit stooq)")
        return None
    df = pd.read_csv(io.StringIO(raw))
    cols = {c.lower(): c for c in df.columns}
    date_col = cols.get("data") or cols.get("date")
    close_col = cols.get("zamkniecie") or cols.get("close")
    if date_col is None or close_col is None:
        print(f"[T3] {symbol}: nieoczekiwane kolumny {list(df.columns)}")
        return None
    out = pd.DataFrame({"date": pd.to_datetime(df[date_col]), "close": df[close_col].astype(float)})
    return out.dropna().sort_values("date").reset_index(drop=True)


def bench_return(bench: pd.DataFrame, d_in, d_out) -> float:
    """Zwrot benchu close(on-or-before d_out) / close(on-or-before d_in) - 1."""
    i = int(bench["date"].searchsorted(pd.Timestamp(d_in), side="right")) - 1
    j = int(bench["date"].searchsorted(pd.Timestamp(d_out), side="right")) - 1
    if i < 0 or j < 0 or j <= i:
        return float("nan")
    return float(bench.loc[j, "close"] / bench.loc[i, "close"] - 1.0)


def excess_vs_bench(sub: pd.DataFrame, bench: pd.DataFrame) -> pd.DataFrame:
    """Per rewizja: equalrev excess selekcji i poola vs bench w oknach [entry, exit]."""
    rows = []
    for rev, pool in sub.groupby("revision_date"):
        sel = pool[pool["asof_score"] >= SCORE_MIN]
        if sel.empty:
            continue
        def _ex(df: pd.DataFrame) -> float:
            b = np.array([bench_return(bench, e, x) for e, x in
                          zip(df["entry_trading_date"], df["exit_trading_date"])])
            r = df["gross_return"].to_numpy()
            ok = ~np.isnan(b)
            return float((r[ok] - b[ok]).mean()) if ok.any() else float("nan")
        rows.append({"revision_date": rev, "n_sel": int(len(sel)),
                     "sel_excess": _ex(sel), "pool_excess": _ex(pool)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# T5 — survivorship
# ---------------------------------------------------------------------------

def survivorship_audit(fr: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    ip = pd.read_parquet(PORTFOLIOS_PATH)
    ip["revision_date"] = pd.to_datetime(ip["revision_date"])
    oh = pd.read_parquet(OHLCV_PATH)
    oh["date"] = pd.to_datetime(oh["date"])
    last_price = oh.dropna(subset=["close"]).groupby("isin")["date"].max()
    ohlcv_isins = set(last_price.index)

    wig = ip[ip["index_name"].eq("WIG") & (ip["shares"] > 0)]
    tick = ip.drop_duplicates("isin").set_index("isin")["ticker"].to_dict()

    rev_pairs = (fr[["revision_date", "previous_revision_date"]]
                 .drop_duplicates().sort_values("revision_date"))
    rows = []
    for r in rev_pairs.itertuples(index=False):
        members = set(wig.loc[wig["revision_date"].eq(r.previous_revision_date), "isin"])
        if not members:
            continue
        missing = members - ohlcv_isins
        for isin in sorted(missing):
            rows.append({"revision_date": r.revision_date.date(), "isin": isin,
                         "ticker": tick.get(isin), "category": "brak_w_ohlcv"})
        # serie urwane przed rewizja (potencjalny delisting w oknie panelu)
        present = members & ohlcv_isins
        for isin in sorted(present):
            if last_price[isin] < r.revision_date - pd.Timedelta(days=30):
                rows.append({"revision_date": r.revision_date.date(), "isin": isin,
                             "ticker": tick.get(isin), "category": "seria_urwana_>30d_przed_rewizja",
                             "last_price_date": last_price[isin].date()})
    audit = pd.DataFrame(rows)

    # delisted flaga w poolu / selekcji per offset (z Etapu 5)
    del_rows = []
    for off, sub in fr[fr["gross_return"].notna()].groupby("offset_td"):
        sel = sub[sub["asof_score"] >= SCORE_MIN]
        del_rows.append({"offset_td": int(off),
                         "pool_n": int(len(sub)), "pool_delisted": int(sub["delisted"].sum()),
                         "sel_n": int(len(sel)), "sel_delisted": int(sel["delisted"].sum())})
    return audit, pd.DataFrame(del_rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

RANK_ZONE = (25, 95)   # strefa kandydacka buildera panelu


def run_battery(valid: pd.DataFrame, tag: str, benches: dict[str, pd.DataFrame | None]) -> None:
    """Pelny zestaw T1/T2/T3/T4/T6 na danym wariancie poola; artefakty z suffixem tag."""
    rng = np.random.default_rng(SEED)

    t1_rows, t4_rows, t6_rows, alpha_frames = [], [], [], []
    for off in OFFSETS:
        sub = valid[valid["offset_td"].eq(off)]
        pr = per_revision_alpha(sub)
        if pr.empty:
            continue
        pr.insert(0, "offset_td", off)
        alpha_frames.append(pr)
        a = pr["alpha"].to_numpy()
        lo, hi = bootstrap_ci(a, N_BOOT, rng)
        t1_rows.append({"offset_td": off, "n_revisions": len(pr), "n_trades": int(pr["n_sel"].sum()),
                        "equalrev_alpha": float(a.mean()), "ci95_lo": lo, "ci95_hi": hi,
                        "n_rev_alpha_pos": int((a > 0).sum())})
        for era, mask in [("<2024", pr["revision_date"] < OOS_SPLIT),
                          (">=2024", pr["revision_date"] >= OOS_SPLIT)]:
            e = pr.loc[mask, "alpha"].to_numpy()
            if len(e) == 0:
                continue
            k, n = int((e > 0).sum()), len(e)
            # dokladny binomial sign-test, one-sided P(X >= k | p=0.5)
            p_sign = float(sum(math.comb(n, j) for j in range(k, n + 1)) / 2 ** n)
            t4_rows.append({"offset_td": off, "era": era, "n_revisions": n,
                            "mean_alpha": float(e.mean()), "median_alpha": float(np.median(e)),
                            "n_alpha_pos": k, "p_sign_test": p_sign})
        for i, rev in enumerate(pr["revision_date"]):
            rest = np.delete(a, i)
            t6_rows.append({"offset_td": off, "dropped_revision": pd.Timestamp(rev).date(),
                            "alpha_without": float(rest.mean())})

    pd.concat(alpha_frames, ignore_index=True).to_csv(OUT_DIR / f"alpha_per_revision_{tag}.csv", index=False)
    t1 = pd.DataFrame(t1_rows)
    t1.to_csv(OUT_DIR / f"t1_bootstrap_alpha_{tag}.csv", index=False)
    t4 = pd.DataFrame(t4_rows)
    t4.to_csv(OUT_DIR / f"t4_regime_{tag}.csv", index=False)
    t6 = pd.DataFrame(t6_rows)
    t6.to_csv(OUT_DIR / f"t6_loo_revision_{tag}.csv", index=False)

    t2_rows = []
    for off in OFFSETS:
        sub = valid[valid["offset_td"].eq(off)]
        res = permutation_test(sub, N_PERM, rng)
        if not res:
            continue
        sel = sub[sub["asof_score"] >= SCORE_MIN]
        w_lo, w_hi = wilson_ci(int(sel["entered_mwig40"].sum()), int(len(sel)))
        res.update({"offset_td": off, "precision_wilson_lo": w_lo, "precision_wilson_hi": w_hi})
        t2_rows.append(res)
    t2 = pd.DataFrame(t2_rows)
    t2.to_csv(OUT_DIR / f"t2_permutation_{tag}.csv", index=False)

    t3_rows = []
    for sym, bench in benches.items():
        if bench is None or bench.empty:
            t3_rows.append({"bench": sym, "status": "BRAK DANYCH"})
            continue
        for off in OFFSETS:
            sub = valid[valid["offset_td"].eq(off)]
            ex = excess_vs_bench(sub, bench).dropna(subset=["sel_excess"])
            if ex.empty:
                continue
            v = ex["sel_excess"].to_numpy()
            lo, hi = bootstrap_ci(v, N_BOOT, rng)
            t3_rows.append({"bench": sym, "status": "ok", "offset_td": off, "n_revisions": len(ex),
                            "equalrev_sel_excess": float(v.mean()), "ci95_lo": lo, "ci95_hi": hi,
                            "equalrev_pool_excess": float(ex["pool_excess"].mean())})
    t3 = pd.DataFrame(t3_rows)
    t3.to_csv(OUT_DIR / f"t3_bench_excess_{tag}.csv", index=False)

    print(f"\n{'='*90}\nWARIANT: {tag}\n{'='*90}")
    print("--- T1: equalrev-alfa (score>=3 vs pool), bootstrap po rewizjach ---")
    print(t1.to_string(index=False))
    print("--- T2: permutacje (prog deflowany p<0.005) ---")
    cols = ["offset_td", "n_revisions", "n_trades", "obs_equalrev_alpha", "p_perm_alpha",
            "obs_precision", "p_perm_precision", "precision_wilson_lo", "precision_wilson_hi"]
    print(t2[cols].to_string(index=False))
    print("--- T3: excess vs bench TR ---")
    ok = t3[t3["status"].eq("ok")] if "status" in t3.columns else t3
    print(ok.to_string(index=False))
    print("--- T4: rezim ---")
    print(t4.to_string(index=False))
    print("--- T6: LOO po rewizjach (min/max alfy bez 1 rewizji) ---")
    if not t6.empty:
        print(t6.groupby("offset_td")["alpha_without"].agg(["min", "max"]).to_string())


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fr = load_forward_returns()
    valid = fr[fr["gross_return"].notna()].copy()

    d1, d2 = date(2020, 1, 1), date(2026, 7, 1)
    benches = {s: fetch_bench(s, d1, d2) for s in BENCH_SYMBOLS}

    # diagnostyka look-ahead: trade'y score>=3 poza strefa kandydacka (obecne w panelu
    # tylko dlatego, ze faktycznie weszly -> przeciek targetu do uniwersum)
    zone_mask = valid["replicated_rank_asof"].between(*RANK_ZONE)
    ooz = valid[(valid["asof_score"] >= SCORE_MIN) & ~zone_mask]
    ooz_diag = (ooz.groupby("offset_td")
                .agg(n_trades=("isin", "size"), n_entered=("entered_mwig40", "sum"),
                     mean_return=("gross_return", "mean"), max_return=("gross_return", "max"))
                .reset_index())
    ooz_diag.to_csv(OUT_DIR / "out_of_zone_trades.csv", index=False)
    print("=== Trade'y score>=3 POZA strefa rank 25-95 (kandydaci do look-ahead) ===")
    print(ooz_diag.to_string(index=False))
    if not ooz.empty:
        print(ooz[["offset_td", "revision_date", "ticker", "replicated_rank_asof",
                   "entered_mwig40", "gross_return"]].sort_values("gross_return", ascending=False)
              .head(10).to_string(index=False))

    # wariant 1: pool jak w Etapie 5 (strefa + doklejeni entranci spoza strefy) — DIRTY
    run_battery(valid, "full_panel", benches)
    # wariant 2: point-in-time czysty — pool i selekcja wylacznie w strefie rank 25-95
    run_battery(valid[zone_mask].copy(), "zone_only", benches)

    # ---- T5 — survivorship ----
    audit, delisted = survivorship_audit(fr)
    audit.to_csv(OUT_DIR / "t5_survivorship_missing.csv", index=False)
    delisted.to_csv(OUT_DIR / "t5_delisted_in_pool.csv", index=False)
    print("\n=== T5 — survivorship ===")
    if audit.empty:
        print("Brak brakujacych ISIN-ow WIG@(r-1) w OHLCV.")
    else:
        print(audit.groupby("category").size().to_string())
        per_rev = audit[audit["category"].eq("brak_w_ohlcv")].groupby("revision_date").size()
        print(f"brak_w_ohlcv per rewizja: min={per_rev.min()}, max={per_rev.max()}, "
              f"srednia={per_rev.mean():.1f}, unikalnych ISIN={audit['isin'].nunique()}")
    print("\nDelisted w poolu/selekcji per offset:")
    print(delisted.to_string(index=False))
    print(f"\nArtefakty -> {OUT_DIR}")


if __name__ == "__main__":
    main()
