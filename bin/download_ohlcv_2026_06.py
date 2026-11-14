#!/usr/bin/env python3
"""
Pobiera/uzupełnia OHLCV ze stooq dla rewizji czerwcowej 2026 (ranking 2026-05-22).

- Universe: scrape biznesradar WIG (326 tickerów).
- Baza: stooq_cache_eda_2021_2026 (kończy się 2026-04-30).
- Delta: dla każdego tickera w cache fetch od (last_date+1) do --date-to.
- Pełny fetch: dla 4 tickerów których nie ma w eda cache (CRQ/GNS/S2B/SCW).
- Wynik: data/stooq_cache_2026_06/ + output/2026_06_revision/wig2026_06_ohlcv.parquet
"""
from __future__ import annotations

import argparse
import io
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

STOOQ_URL = "https://stooq.pl/q/d/l/"
STOOQ_API_KEY = "a3xtYFdVDKUPQ7mN50Ec2Mf1To4BvH69"
DELAY = 1.0
TIMEOUT = 30
RETRIES = 2

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

MANUAL_MAP = {"CRQ": "crq", "GNS": "gns", "S2B": "s2b", "SCW": "scw"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("dl2026_06")


def build_universe(br_path: Path, map_path: Path) -> pd.DataFrame:
    br = pd.read_parquet(br_path)
    mp = pd.read_csv(map_path)
    br["ts"] = br["ticker_short"].str.upper().str.strip()
    mp["gs"] = mp["gpw_short"].astype(str).str.upper().str.strip()
    mp_dd = mp.dropna(subset=["stooq_ticker_final"]).drop_duplicates("gs")[["gs", "stooq_ticker_final", "isin"]]
    j = br.merge(mp_dd, left_on="ts", right_on="gs", how="left")
    miss = j["stooq_ticker_final"].isna()
    j.loc[miss, "stooq_ticker_final"] = j.loc[miss, "ts"].map(MANUAL_MAP)
    j.loc[miss, "isin"] = None
    if j["stooq_ticker_final"].isna().any():
        bad = j[j["stooq_ticker_final"].isna()][["ticker_short", "ticker_long"]]
        raise RuntimeError(f"Niemapowane tickery:\n{bad.to_string(index=False)}")
    return j[["ticker_short", "ticker_long", "name", "weight_pct", "stooq_ticker_final", "isin"]].rename(
        columns={"stooq_ticker_final": "stooq_ticker"}
    )


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Referer": "https://stooq.pl/", "Accept-Language": "pl-PL,pl;q=0.9"})
    try:
        s.get("https://stooq.pl/", timeout=TIMEOUT)
    except Exception:
        pass
    return s


def fetch(ticker: str, d_from: date, d_to: date, sess: requests.Session) -> tuple[pd.DataFrame | None, str | None]:
    url = f"{STOOQ_URL}?s={ticker.lower()}&d1={d_from.strftime('%Y%m%d')}&d2={d_to.strftime('%Y%m%d')}&i=d&apikey={STOOQ_API_KEY}"
    for attempt in range(RETRIES + 1):
        try:
            r = sess.get(url, timeout=TIMEOUT)
            if r.status_code != 200:
                if attempt < RETRIES:
                    time.sleep(2.0)
                    continue
                return None, f"HTTP {r.status_code}"
            txt = r.text.strip()
            if "Przekroczony" in txt:
                return None, "daily_limit_exceeded"
            if "Brak danych" in txt or "No data" in txt:
                return None, "no_data"
            if len(txt) < 50:
                return None, f"empty ({len(txt)} zn)"
            df = pd.read_csv(io.StringIO(txt), on_bad_lines="skip")
            if "Data" in df.columns:
                df = df.rename(columns={"Data": "date", "Otwarcie": "open", "Najwyzszy": "high",
                                        "Najnizszy": "low", "Zamkniecie": "close", "Wolumen": "volume"})
            elif "Date" in df.columns:
                df = df.rename(columns={"Date": "date", "Open": "open", "High": "high",
                                        "Low": "low", "Close": "close", "Volume": "volume"})
            else:
                return None, f"unexpected_cols: {list(df.columns)}"
            need = {"date", "open", "high", "low", "close", "volume"}
            if not need.issubset(df.columns):
                return None, f"missing_cols: {list(df.columns)}"
            df["date"] = pd.to_datetime(df["date"]).dt.date
            for c in ("open", "high", "low", "close"):
                df[c] = pd.to_numeric(df[c], errors="coerce")
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
            df = df.dropna(subset=["close"])
            if df.empty:
                return None, "empty_after_norm"
            return df[["date", "open", "high", "low", "close", "volume"]], None
        except requests.RequestException as e:
            if attempt < RETRIES:
                time.sleep(2.0)
                continue
            return None, f"req_error: {e}"
        except Exception as e:
            return None, f"err: {type(e).__name__}: {e}"
    return None, "max_retries"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date-from", default="2025-05-22")
    p.add_argument("--date-to", default="2026-05-22")
    p.add_argument("--biznesradar", default="data/biznesradar/WIG_20260513_2207.parquet")
    p.add_argument("--map", default="output/maps/ticker_isin_stooq_map.csv")
    p.add_argument("--source-cache", default="data/stooq_cache_eda_2021_2026")
    p.add_argument("--target-cache", default="data/stooq_cache_2026_06")
    p.add_argument("--out-dir", default="output/2026_06_revision")
    p.add_argument("--label", default="2026_06")
    args = p.parse_args()

    d_from = datetime.strptime(args.date_from, "%Y-%m-%d").date()
    d_to = datetime.strptime(args.date_to, "%Y-%m-%d").date()
    src_cache = Path(args.source_cache)
    tgt_cache = Path(args.target_cache)
    tgt_cache.mkdir(parents=True, exist_ok=True)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    univ = build_universe(Path(args.biznesradar), Path(args.map))
    log.info(f"Universe: {len(univ)} tickerów (z biznesradar)")
    log.info(f"Okno: {d_from} -> {d_to}")

    sess = make_session()
    log_rows = []
    all_frames = []

    for i, row in enumerate(univ.itertuples(index=False), 1):
        t = row.stooq_ticker
        ts_short = row.ticker_short
        tgt_file = tgt_cache / f"{t}.parquet"
        src_file = src_cache / f"{t}.parquet"

        # 1. Load existing data (from target if already processed, else from source)
        existing = None
        if tgt_file.exists():
            try:
                existing = pd.read_parquet(tgt_file)
            except Exception:
                existing = None
        elif src_file.exists():
            try:
                existing = pd.read_parquet(src_file)
            except Exception:
                existing = None

        # 2. Determine fetch range
        if existing is not None and not existing.empty:
            existing = existing.copy()
            existing["date"] = pd.to_datetime(existing["date"]).dt.date
            last_date = existing["date"].max()
            fetch_from = last_date + timedelta(days=1)
        else:
            fetch_from = d_from
            last_date = None

        if fetch_from > d_to:
            # Already complete — just copy/save
            combined = existing[(existing["date"] >= d_from) & (existing["date"] <= d_to)].copy()
            combined.to_parquet(tgt_file, index=False)
            status = "complete_from_cache"
            new_rows = 0
            log.info(f"[{i:3d}/{len(univ)}] {ts_short:8s} {t:8s} {status} ({len(combined)} wierszy, ostatnia {last_date})")
        else:
            df_new, err = fetch(t, fetch_from, d_to, sess)
            if df_new is None:
                if err == "daily_limit_exceeded":
                    log.error("!!! Dzienny limit API !!!")
                    log_rows.append({"ticker_short": ts_short, "stooq": t, "status": "limit",
                                     "last_existing": str(last_date) if last_date else "",
                                     "fetch_from": str(fetch_from), "new_rows": 0, "error": err})
                    break
                if err == "no_data":
                    # No new data in range — keep existing
                    if existing is not None:
                        combined = existing[(existing["date"] >= d_from) & (existing["date"] <= d_to)].copy()
                        combined.to_parquet(tgt_file, index=False)
                        status = "no_new_data"
                        new_rows = 0
                        log.info(f"[{i:3d}/{len(univ)}] {ts_short:8s} {t:8s} {status} (last {last_date})")
                    else:
                        status = "no_data_full"
                        new_rows = 0
                        log.warning(f"[{i:3d}/{len(univ)}] {ts_short:8s} {t:8s} {status}")
                else:
                    status = f"error: {err}"
                    new_rows = 0
                    log.warning(f"[{i:3d}/{len(univ)}] {ts_short:8s} {t:8s} {status}")
                log_rows.append({"ticker_short": ts_short, "stooq": t, "status": status.split(":")[0],
                                 "last_existing": str(last_date) if last_date else "",
                                 "fetch_from": str(fetch_from), "new_rows": new_rows, "error": err or ""})
            else:
                if existing is not None:
                    combined = pd.concat([existing, df_new], ignore_index=True)
                    combined = combined.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)
                else:
                    combined = df_new.copy()
                combined = combined[(combined["date"] >= d_from) & (combined["date"] <= d_to)].copy()
                combined.to_parquet(tgt_file, index=False)
                status = "delta" if existing is not None else "full"
                new_rows = len(df_new)
                log.info(f"[{i:3d}/{len(univ)}] {ts_short:8s} {t:8s} {status} (+{new_rows} wierszy, {df_new['date'].min()} -> {df_new['date'].max()})")
                log_rows.append({"ticker_short": ts_short, "stooq": t, "status": status,
                                 "last_existing": str(last_date) if last_date else "",
                                 "fetch_from": str(fetch_from), "new_rows": new_rows, "error": ""})
                time.sleep(DELAY)
                continue

            time.sleep(DELAY)

        # Note: for cache-only branches log_rows is appended below
        if status in ("complete_from_cache",):
            log_rows.append({"ticker_short": ts_short, "stooq": t, "status": status,
                             "last_existing": str(last_date) if last_date else "",
                             "fetch_from": str(fetch_from), "new_rows": 0, "error": ""})

    # Build combined OHLCV parquet
    for row in univ.itertuples(index=False):
        t = row.stooq_ticker
        fp = tgt_cache / f"{t}.parquet"
        if not fp.exists():
            continue
        d = pd.read_parquet(fp)
        d["stooq_ticker"] = t
        d["ticker_short"] = row.ticker_short
        d["isin"] = row.isin
        all_frames.append(d)

    log_df = pd.DataFrame(log_rows)
    log_path = out_dir / f"wig{args.label}_fetch_log.csv"
    log_df.to_csv(log_path, index=False, encoding="utf-8")
    log.info(f"Log -> {log_path}")

    if all_frames:
        result = pd.concat(all_frames, ignore_index=True)
        cols = ["ticker_short", "stooq_ticker", "isin", "date", "open", "high", "low", "close", "volume"]
        result = result[cols].sort_values(["ticker_short", "date"]).reset_index(drop=True)
        ohlcv_path = out_dir / f"wig{args.label}_ohlcv.parquet"
        result.to_parquet(ohlcv_path, index=False)
        log.info(f"OHLCV -> {ohlcv_path} ({len(result):,} wierszy, {result['ticker_short'].nunique()} tickerów)")
    else:
        log.error("Brak danych!")

    print("\n=== PODSUMOWANIE ===")
    if not log_df.empty:
        print(log_df["status"].value_counts().to_string())
        bad = log_df[log_df["status"].isin(["error", "limit", "no_data_full"])]
        if not bad.empty:
            print("\nProblemy:")
            print(bad[["ticker_short", "stooq", "status", "error"]].to_string(index=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
