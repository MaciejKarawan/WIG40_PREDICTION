#!/usr/bin/env python3
"""
Pobiera dane OHLCV ze stooq dla dowolnej rewizji.

Użycie:
    python download_ohlcv.py --revision 2026_03 \
        --date-from 2026-01-01 --date-to 2026-02-20 \
        --isins data/mwig40_032026.csv

    python download_ohlcv.py --revision 2025_03 \
        --date-from 2024-02-01 --date-to 2025-02-28

Ścieżki pochodne od --revision LABEL:
    cache:  data/stooq_cache_LABEL/
    ohlcv:  output/LABEL_revision/wigLABEL_ohlcv.parquet
    log:    output/LABEL_revision/wigLABEL_fetch_log.csv
    isins:  output/wig_LABEL.csv  (fallback gdy --isins nie podane)
"""

import argparse
import io
import logging
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# STAŁE
# ---------------------------------------------------------------------------

STOOQ_CSV_URL  = "https://stooq.pl/q/d/l/"
STOOQ_API_KEY  = "a3xtYFdVDKUPQ7mN50Ec2Mf1To4BvH69"
DOWNLOAD_DELAY = 1.0
TIMEOUT        = 30
MAX_RETRIES    = 2

MAP_PATH = Path("output/maps/ticker_isin_stooq_map.csv")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ŚCIEŻKI
# ---------------------------------------------------------------------------

def make_paths(revision: str) -> dict[str, Path]:
    base = Path(f"output/{revision}_revision")
    return {
        "cache_dir":    Path(f"data/stooq_cache_{revision}"),
        "output_dir":   base,
        "output_ohlcv": base / f"wig{revision}_ohlcv.parquet",
        "output_log":   base / f"wig{revision}_fetch_log.csv",
        "wig_csv":      Path(f"output/wig_{revision}.csv"),
    }


# ---------------------------------------------------------------------------
# ISINy
# ---------------------------------------------------------------------------

ISIN_COLUMN_CANDIDATES = ("isin", "Kod ISIN", "ISIN", "kod_isin", "Kod_ISIN")


def load_isins(path: Path) -> list[str]:
    """Wczytuje ISINy z CSV — auto-wykrywa kolumnę."""
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    for candidate in ISIN_COLUMN_CANDIDATES:
        if candidate in df.columns:
            return df[candidate].dropna().str.strip().unique().tolist()
    raise ValueError(
        f"Nie znaleziono kolumny z ISIN w {path}. "
        f"Kolumny: {list(df.columns)}"
    )


def build_stooq_index(isins: list[str]) -> dict[str, list[str]]:
    """Zwraca {stooq_ticker: [isin, ...]} na podstawie ticker_map."""
    map_df = pd.read_csv(MAP_PATH)
    map_df.columns = [c.strip().lower() for c in map_df.columns]
    if "stooq_ticker_final" in map_df.columns:
        map_df = map_df.rename(columns={"stooq_ticker_final": "stooq_ticker"})

    filtered = map_df[map_df["isin"].isin(isins)][["isin", "stooq_ticker"]].dropna()

    index: dict[str, list[str]] = {}
    for _, row in filtered.iterrows():
        index.setdefault(row["stooq_ticker"], []).append(row["isin"])
    return index


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://stooq.pl/",
    })
    try:
        s.get("https://stooq.pl/", timeout=TIMEOUT)
    except Exception:
        pass
    return s


def build_url(stooq_ticker: str, date_from: date, date_to: date) -> str:
    return (
        f"{STOOQ_CSV_URL}"
        f"?s={stooq_ticker.lower()}"
        f"&d1={date_from.strftime('%Y%m%d')}"
        f"&d2={date_to.strftime('%Y%m%d')}"
        f"&i=d"
        f"&apikey={STOOQ_API_KEY}"
    )


def fetch_ticker(
    stooq_ticker: str,
    date_from: date,
    date_to: date,
    session: requests.Session,
) -> tuple[pd.DataFrame | None, str | None]:
    url = build_url(stooq_ticker, date_from, date_to)

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=TIMEOUT)
            if resp.status_code != 200:
                if attempt < MAX_RETRIES:
                    time.sleep(2.0)
                    continue
                return None, f"HTTP {resp.status_code}"

            text = resp.text.strip()

            if "Przekroczony" in text:
                return None, "daily_limit_exceeded"
            if "Brak danych" in text or "No data" in text:
                return None, "no_data"
            if len(text) < 50:
                return None, f"empty_response ({len(text)} zn)"

            df = pd.read_csv(io.StringIO(text), on_bad_lines="skip")

            col_map_pl = {"Data": "date", "Otwarcie": "open", "Najwyzszy": "high",
                          "Najnizszy": "low", "Zamkniecie": "close", "Wolumen": "volume"}
            col_map_en = {"Date": "date", "Open": "open", "High": "high",
                          "Low": "low", "Close": "close", "Volume": "volume"}

            if "Data" in df.columns:
                df = df.rename(columns=col_map_pl)
            elif "Date" in df.columns:
                df = df.rename(columns=col_map_en)
            else:
                return None, f"unexpected_columns: {list(df.columns)}"

            needed = {"date", "open", "high", "low", "close", "volume"}
            if not needed.issubset(df.columns):
                return None, f"missing_columns: {list(df.columns)}"

            df["date"]   = pd.to_datetime(df["date"]).dt.date
            df["close"]  = pd.to_numeric(df["close"],  errors="coerce")
            df["open"]   = pd.to_numeric(df["open"],   errors="coerce")
            df["high"]   = pd.to_numeric(df["high"],   errors="coerce")
            df["low"]    = pd.to_numeric(df["low"],    errors="coerce")
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
            df = df.dropna(subset=["close"])

            if df.empty:
                return None, "empty_after_normalization"

            return df[["date", "open", "high", "low", "close", "volume"]], None

        except requests.RequestException as e:
            if attempt < MAX_RETRIES:
                time.sleep(2.0)
                continue
            return None, f"request_error: {e}"
        except Exception as e:
            return None, f"error: {type(e).__name__}: {e}"

    return None, "max_retries"


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Pobiera OHLCV ze stooq dla rewizji indeksu.")
    p.add_argument("--revision",  required=True,
                   help="Etykieta rewizji, np. 2026_03 — używana do nazw plików/katalogów.")
    p.add_argument("--date-from", required=True,
                   help="Początek zakresu danych, format YYYY-MM-DD.")
    p.add_argument("--date-to",   required=True,
                   help="Koniec zakresu danych, format YYYY-MM-DD.")
    p.add_argument("--isins",     default=None,
                   help="CSV z ISINami (auto-wykrywa kolumnę). "
                        "Domyślnie: output/wig_{revision}.csv")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    date_from = datetime.strptime(args.date_from, "%Y-%m-%d").date()
    date_to   = datetime.strptime(args.date_to,   "%Y-%m-%d").date()
    paths     = make_paths(args.revision)

    paths["cache_dir"].mkdir(parents=True, exist_ok=True)
    paths["output_dir"].mkdir(parents=True, exist_ok=True)

    # --- 1. ISINy ---
    isins_path = Path(args.isins) if args.isins else paths["wig_csv"]
    if not isins_path.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku z ISINami: {isins_path}")
    isins = load_isins(isins_path)
    log.info(f"ISINów: {len(isins)} (z {isins_path})")

    # --- 2. Mapowanie ISIN -> stooq ticker ---
    stooq_to_isins = build_stooq_index(isins)
    stooq_tickers  = sorted(stooq_to_isins.keys())
    log.info(f"Tickerów do pobrania: {len(stooq_tickers)}, zakres: {date_from} -> {date_to}")

    # --- 3. Sesja HTTP ---
    session = make_session()

    # --- 4. Pobieranie ---
    all_frames: list[pd.DataFrame] = []
    log_rows:   list[dict]         = []

    for i, stooq_ticker in enumerate(stooq_tickers, 1):
        isins_for_ticker = stooq_to_isins[stooq_ticker]
        cache_file = paths["cache_dir"] / f"{stooq_ticker}.parquet"

        if cache_file.exists():
            try:
                df_cached = pd.read_parquet(cache_file)
                for isin in isins_for_ticker:
                    df_isin = df_cached.copy()
                    df_isin["isin"] = isin
                    df_isin["stooq_ticker"] = stooq_ticker
                    all_frames.append(df_isin)
                log.info(f"[{i:3d}/{len(stooq_tickers)}] {stooq_ticker:8s} CACHE ({len(df_cached)} wierszy)")
                for isin in isins_for_ticker:
                    log_rows.append({"stooq_ticker": stooq_ticker, "isin": isin,
                                     "status": "cached", "rows": len(df_cached),
                                     "first_date": str(df_cached["date"].min()),
                                     "last_date":  str(df_cached["date"].max()), "error": ""})
                continue
            except Exception:
                pass

        df, err = fetch_ticker(stooq_ticker, date_from, date_to, session)

        if df is not None:
            df.to_parquet(cache_file, index=False)
            for isin in isins_for_ticker:
                df_isin = df.copy()
                df_isin["isin"] = isin
                df_isin["stooq_ticker"] = stooq_ticker
                all_frames.append(df_isin)
            log.info(
                f"[{i:3d}/{len(stooq_tickers)}] {stooq_ticker:8s} OK "
                f"({len(df)} wierszy, {df['date'].min()} - {df['date'].max()})"
            )
            for isin in isins_for_ticker:
                log_rows.append({"stooq_ticker": stooq_ticker, "isin": isin,
                                 "status": "success", "rows": len(df),
                                 "first_date": str(df["date"].min()),
                                 "last_date":  str(df["date"].max()), "error": ""})
        else:
            log.warning(f"[{i:3d}/{len(stooq_tickers)}] {stooq_ticker:8s} FAIL: {err}")
            if err == "daily_limit_exceeded":
                log.error("!!! Dzienny limit API wyczerpany — przerywam !!!")
                for isin in isins_for_ticker:
                    log_rows.append({"stooq_ticker": stooq_ticker, "isin": isin,
                                     "status": "limit", "rows": 0,
                                     "first_date": "", "last_date": "", "error": err})
                break
            for isin in isins_for_ticker:
                log_rows.append({"stooq_ticker": stooq_ticker, "isin": isin,
                                 "status": "error", "rows": 0,
                                 "first_date": "", "last_date": "", "error": str(err)})

        time.sleep(DOWNLOAD_DELAY)

    # --- 5. Zapis ---
    log_df = pd.DataFrame(log_rows)
    log_df.to_csv(paths["output_log"], index=False, encoding="utf-8")
    log.info(f"Log zapisany -> {paths['output_log']}")

    if all_frames:
        result = pd.concat(all_frames, ignore_index=True)
        cols = ["isin", "stooq_ticker", "date", "open", "high", "low", "close", "volume"]
        result = result[cols].sort_values(["isin", "date"]).reset_index(drop=True)
        result.to_parquet(paths["output_ohlcv"], index=False)
        log.info(
            f"OHLCV zapisany -> {paths['output_ohlcv']} "
            f"({len(result)} wierszy, {result['isin'].nunique()} ISINów)"
        )
    else:
        log.error("Brak danych do zapisania!")

    # --- 6. Podsumowanie ---
    print("\n=== PODSUMOWANIE ===")
    if not log_df.empty:
        print(log_df["status"].value_counts().to_string())
        errors = log_df[log_df["status"].isin(["error", "no_data", "limit"])]
        if not errors.empty:
            print(f"\nNieudane ({len(errors)}):")
            print(errors[["stooq_ticker", "isin", "status", "error"]].to_string(index=False))


if __name__ == "__main__":
    main()
