#!/usr/bin/env python3
"""
GPW Benchmark — Historical Portfolio Scraper & Parser
=====================================================

Pobiera i parsuje PDFy historycznych portfeli indeksów z gpwbenchmark.pl
Zakres: od rewizji 2021-03-19 (zmiana metodologii) do najnowszej dostępnej.

Indeksy: WIG, WIG20, mWIG40, sWIG80
Output:  Parquet files w katalogu ./output/

Uruchomienie:
    pip install pdfplumber requests pandas pyarrow
    python gpw_benchmark_scraper.py

Autor: Maciej + Claude (projekt predykatów WIG40)
"""

import re
import time
import logging
import argparse
from pathlib import Path
from datetime import date
from dataclasses import dataclass, field

import requests
import pdfplumber
import pandas as pd

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

BASE_URL = "https://gpwbenchmark.pl/pub/BENCHMARK/files/PDF/historyczne"

# Wszystkie daty rewizji od 2021-03 wzwyż (źródło: HTML strony gpwbenchmark)
# Format: (rok, miesiąc, dzień)
REVISION_DATES = [
    # 2021
    (2021, 3, 19), (2021, 6, 18), (2021, 9, 17), (2021, 12, 17),
    # 2022
    (2022, 3, 18), (2022, 6, 17), (2022, 9, 16), (2022, 12, 16),
    # 2023
    (2023, 3, 17), (2023, 6, 16), (2023, 9, 15), (2023, 12, 15),
    # 2024
    (2024, 3, 15), (2024, 6, 21), (2024, 9, 20), (2024, 12, 20),
    # 2025
    (2025, 3, 21), (2025, 6, 20), (2025, 9, 19),
    # 2025-26 — dla tych rewizji GPW Benchmark publikuje tylko combined PDF
    # (WIG20+mWIG40+sWIG80+WIG30 razem). Scraper parsuje tylko osobne WIG;
    # mWIG40 ingestowany osobno z CSV przez bin/ingest_mwig40_csv.py.
    (2025, 12, 19),
    (2026, 3, 20),
]

INDEX_NAMES = ["WIG", "WIG20", "mWIG40", "sWIG80"]

# Mapowanie nazwy indeksu -> nazwa pliku w URL
INDEX_FILE_MAP = {
    "WIG": "WIG",
    "WIG20": "WIG20",
    "mWIG40": "mWIG40",
    "sWIG80": "sWIG80",
}

PDF_DIR = Path("./data/pdfs")
OUTPUT_DIR = Path("./output/wig_history")

DOWNLOAD_DELAY_SEC = 1.0  # uprzejmość wobec serwera

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DATA CLASSES
# ---------------------------------------------------------------------------

@dataclass
class PortfolioRow:
    revision_date: str          # YYYY-MM-DD
    index_name: str             # WIG, WIG20, mWIG40, sWIG80
    ranking_date: str           # data wg stanu (z nagłówka PDF), YYYY-MM-DD lub "unknown"
    lp: int                     # pozycja w portfelu
    isin: str
    ticker: str
    price: float                # kurs w PLN
    shares: int                 # liczba akcji w pakiecie (proxy free-float)
    weight_pct: float           # udział w indeksie (%)
    flags: str                  # flagi oddzielone przecinkami, lub pusty string


@dataclass
class ReserveRow:
    revision_date: str
    index_name: str
    lp: int                     # pozycja na liście rezerwowej
    isin: str
    ticker: str
    shares: int                 # liczba akcji


# ---------------------------------------------------------------------------
# DOWNLOAD
# ---------------------------------------------------------------------------

def build_pdf_url(year: int, month: int, day: int, index_name: str) -> str:
    """Buduje URL do PDF-a na podstawie daty rewizji i nazwy indeksu."""
    date_str = f"{year:04d}_{month:02d}_{day:02d}"
    file_name = INDEX_FILE_MAP[index_name]
    return f"{BASE_URL}/{date_str}_{file_name}.pdf"


def download_pdf(url: str, dest: Path, session: requests.Session) -> bool:
    """Pobiera PDF jeśli nie istnieje lokalnie. Zwraca True jeśli OK."""
    if dest.exists() and dest.stat().st_size > 0:
        log.debug(f"  Już istnieje: {dest.name}")
        return True

    try:
        resp = session.get(url, timeout=30)
        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/pdf"):
            dest.write_bytes(resp.content)
            log.info(f"  Pobrano: {dest.name} ({len(resp.content) / 1024:.0f} KB)")
            return True
        elif resp.status_code == 200:
            # Niektóre stare pliki mogą nie istnieć — serwer zwraca HTML zamiast PDF
            log.warning(f"  Nie-PDF odpowiedź dla {dest.name} (content-type: {resp.headers.get('content-type')})")
            return False
        else:
            log.warning(f"  HTTP {resp.status_code} dla {url}")
            return False
    except requests.RequestException as e:
        log.error(f"  Błąd pobierania {url}: {e}")
        return False


def download_all(session: requests.Session) -> dict[str, Path]:
    """Pobiera wszystkie PDFy. Zwraca dict: klucz -> ścieżka do pliku."""
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    results = {}

    total = len(REVISION_DATES) * len(INDEX_NAMES)
    done = 0

    for y, m, d in REVISION_DATES:
        for idx in INDEX_NAMES:
            done += 1
            url = build_pdf_url(y, m, d, idx)
            fname = f"{y:04d}_{m:02d}_{d:02d}_{idx}.pdf"
            dest = PDF_DIR / fname
            key = f"{y:04d}-{m:02d}-{d:02d}|{idx}"

            if download_pdf(url, dest, session):
                results[key] = dest
            else:
                log.warning(f"  [{done}/{total}] Brak pliku: {fname}")

            if not dest.exists():
                time.sleep(DOWNLOAD_DELAY_SEC)

    log.info(f"Pobieranie zakończone: {len(results)}/{total} plików")
    return results


# ---------------------------------------------------------------------------
# PARSING
# ---------------------------------------------------------------------------

# Regex: wiersz portfela głównego
# Lp  ISIN  TICKER  PRICE  SHARES  WEIGHT
RE_MAIN_ROW = re.compile(
    r"^(\d+)\s+"                          # Lp
    r"([A-Z]{2}[A-Z0-9]{10})\s+"          # ISIN
    r"([A-Z0-9._-]+)\s+"                  # Ticker
    r"([\d\s]+,\d{4})\s+"                 # Kurs (polska notacja)
    r"([\d\s]+\d{3})\s+"                  # Liczba akcji
    r"(\d+,\d{4})",                        # Udział %
    re.MULTILINE,
)

# Fallback dla PDF-ów, w których pdfplumber gubi separator dziesiętny w kolumnie ceny.
# W trybie layout=True szerokie odstępy między kolumnami pozostają zachowane.
RE_MAIN_ROW_LAYOUT = re.compile(
    r"^\s*(\d+)\s+"
    r"([A-Z]{2}[A-Z0-9]{10})\s+"
    r"([A-Z0-9._-]+)\s+"
    r"(.+?)\s{2,}"
    r"(\d{1,3}(?: \d{3})+)\s+"
    r"(\d+,\d{4})\s*$"
)

# Regex: wiersz listy rezerwowej (bez kursu i udziału)
RE_RESERVE_ROW = re.compile(
    r"(\d+)\s+"
    r"([A-Z]{2}[A-Z0-9]{10})\s+"
    r"([A-Z0-9._]+)\s+"
    r"([\d\s]+000)\s*$",
    re.MULTILINE,
)

# Regex: data "wg stanu na" z nagłówka
RE_RANKING_DATE = re.compile(
    r"wg stanu na (\d{1,2})\s+(stycznia|lutego|marca|kwietnia|maja|czerwca"
    r"|lipca|sierpnia|wrze[śs]nia|pa[źz]dziernika|listopada|grudnia)\s+(\d{4})",
    re.IGNORECASE,
)

MONTH_MAP = {
    "stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4,
    "maja": 5, "czerwca": 6, "lipca": 7, "sierpnia": 8,
    "września": 9, "wrzesnia": 9, "wrze\u015bnia": 9,
    "października": 10, "pazdziernika": 10, "pa\u017adziernika": 10,
    "listopada": 11, "grudnia": 12,
}


def _parse_pl_float(s: str) -> float:
    """Parsuje liczbę w polskim formacie (spacja=tys., przecinek=dziesiętny)."""
    return float(s.replace(" ", "").replace(",", "."))


def _parse_int_spaces(s: str) -> int:
    """Parsuje int ze spacjami jako separatorem tysięcy."""
    return int(s.replace(" ", ""))


def _extract_ranking_date(text: str) -> str:
    """Wyciąga datę rankingu z nagłówka PDF. Zwraca 'unknown' jeśli nie znajdzie."""
    m = RE_RANKING_DATE.search(text)
    if not m:
        return "unknown"
    day = int(m.group(1))
    month_str = m.group(2).lower()
    year = int(m.group(3))
    month = MONTH_MAP.get(month_str)
    if month is None:
        # Próba normalizacji polskich znaków
        for k, v in MONTH_MAP.items():
            if k.startswith(month_str[:4]):
                month = v
                break
    if month is None:
        return "unknown"
    return f"{year:04d}-{month:02d}-{day:02d}"


def _compute_flags(isin: str, shares: int, weight_pct: float) -> str:
    """
    Oblicza flagi dla wiersza portfela.

    WEIGHT_CAPPED:       udział >= 9.95% (pakiet prawdopodobnie zredukowany vs. rzeczywisty FF)
    DUAL_LISTED:         ISIN nie zaczyna się od "PL" (spółka zagraniczna, inne reguły kwalifikacji)
    ROUNDING_MATERIAL:   pakiet < 5000 akcji (zaokrąglenie do 1000 szt. stanowi >1% odchylenia)
    """
    flags = []
    if weight_pct >= 9.95:
        flags.append("WEIGHT_CAPPED")
    if not isin.startswith("PL"):
        flags.append("DUAL_LISTED")
    if shares < 5000:
        flags.append("ROUNDING_MATERIAL")
    return ",".join(flags)


def extract_text_from_pdf(pdf_path: Path, layout: bool = False) -> str:
    """Wyciąga tekst ze wszystkich stron PDF-a używając pdfplumber."""
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=layout)
            if text:
                pages_text.append(text)
    return "\n".join(pages_text)


# Nagłówek strony: "Portfel indeksu <NAZWA> ..."
# Od rewizji 2025-12 GPW Benchmark publikuje wszystkie indeksy WIG* w jednym
# pliku PDF (WIG, WIG140, WIGdiv, WIGdivplus, WIG.MS-BAS, WIG.GAMES5, WIG-Poland,
# WIG-Ukraine itd.). Wymuszamy dokładne dopasowanie nazwy indeksu na stronie,
# żeby uniknąć łapania wierszy z sąsiednich sekcji.
RE_PAGE_HEADER_INDEX = re.compile(r"Portfel indeksu ([A-Za-z0-9.\-]+)")


def extract_text_for_index(pdf_path: Path, index_name: str, layout: bool = False) -> str:
    """Wyciąga tekst tylko ze stron, których nagłówek dotyczy `index_name`.

    Dla starego formatu (1 indeks na PDF) zachowanie identyczne z extract_text_from_pdf —
    wszystkie strony pasują. Dla nowego formatu (wiele indeksów w jednym PDF) bierze
    tylko strony z dokładnie pasującym nagłówkiem.
    """
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=layout)
            if not text:
                continue
            m = RE_PAGE_HEADER_INDEX.search(text[:400])
            if m and m.group(1) != index_name:
                continue  # strona innego indeksu — pomijamy
            pages_text.append(text)
    return "\n".join(pages_text)


def _parse_portfolio_from_layout_text(
    text: str,
    revision_date: str,
    index_name: str,
    ranking_date: str,
) -> list[PortfolioRow]:
    """Fallback parser oparty o zachowany układ kolumn w extract_text(layout=True)."""
    portfolio = []

    for line in text.splitlines():
        m = RE_MAIN_ROW_LAYOUT.match(line)
        if not m:
            continue

        lp = int(m.group(1))
        isin = m.group(2)
        ticker = m.group(3)
        price = _parse_pl_float(m.group(4).strip())
        shares = _parse_int_spaces(m.group(5))
        weight = _parse_pl_float(m.group(6))
        flags = _compute_flags(isin, shares, weight)

        portfolio.append(PortfolioRow(
            revision_date=revision_date,
            index_name=index_name,
            ranking_date=ranking_date,
            lp=lp,
            isin=isin,
            ticker=ticker,
            price=price,
            shares=shares,
            weight_pct=weight,
            flags=flags,
        ))

    return portfolio


def parse_portfolio_pdf(
    pdf_path: Path,
    revision_date: str,
    index_name: str,
) -> tuple[list[PortfolioRow], list[ReserveRow]]:
    """
    Parsuje PDF portfela indeksu.

    Returns:
        (portfolio_rows, reserve_rows)
    """
    text = extract_text_for_index(pdf_path, index_name)

    if not text.strip():
        log.error(f"  Pusty tekst z PDF: {pdf_path.name}")
        return [], []

    ranking_date = _extract_ranking_date(text)

    # ---- Portfel główny ----
    portfolio = []
    for m in RE_MAIN_ROW.finditer(text):
        lp = int(m.group(1))
        isin = m.group(2)
        ticker = m.group(3)
        price = _parse_pl_float(m.group(4))
        shares = _parse_int_spaces(m.group(5))
        weight = _parse_pl_float(m.group(6))
        flags = _compute_flags(isin, shares, weight)

        portfolio.append(PortfolioRow(
            revision_date=revision_date,
            index_name=index_name,
            ranking_date=ranking_date,
            lp=lp,
            isin=isin,
            ticker=ticker,
            price=price,
            shares=shares,
            weight_pct=weight,
            flags=flags,
        ))

    expected_count = EXPECTED_COUNTS.get(index_name)
    if expected_count and len(portfolio) < expected_count:
        layout_text = extract_text_for_index(pdf_path, index_name, layout=True)
        layout_portfolio = _parse_portfolio_from_layout_text(
            layout_text,
            revision_date=revision_date,
            index_name=index_name,
            ranking_date=ranking_date,
        )
        if len(layout_portfolio) > len(portfolio):
            log.info(
                f"  {pdf_path.name}: fallback layout parser "
                f"{len(portfolio)} -> {len(layout_portfolio)} spółek"
            )
            portfolio = layout_portfolio

    # ---- Lista rezerwowa ----
    reserves = []
    # Szukamy sekcji po "Lista rezerwowa" lub "Reserve list"
    reserve_marker = -1
    for marker in ["Lista rezerwowa", "Reserve list"]:
        pos = text.find(marker)
        if pos != -1:
            reserve_marker = pos
            break

    if reserve_marker != -1:
        reserve_text = text[reserve_marker:]
        for m in RE_RESERVE_ROW.finditer(reserve_text):
            lp = int(m.group(1))
            isin = m.group(2)
            ticker = m.group(3)
            shares = _parse_int_spaces(m.group(4))

            reserves.append(ReserveRow(
                revision_date=revision_date,
                index_name=index_name,
                lp=lp,
                isin=isin,
                ticker=ticker,
                shares=shares,
            ))

    return portfolio, reserves


# ---------------------------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------------------------

# Oczekiwana liczba spółek w portfelu per indeks
EXPECTED_COUNTS = {
    "WIG20": 20,
    "mWIG40": 40,
    "sWIG80": 80,
    # WIG jest zmienny (300+), nie walidujemy ściśle
}


def validate_results(
    portfolio_df: pd.DataFrame,
    reserve_df: pd.DataFrame,
) -> list[str]:
    """
    Walidacja sparsowanych danych. Zwraca listę ostrzeżeń.
    """
    warnings = []

    for (rev_date, idx_name), group in portfolio_df.groupby(["revision_date", "index_name"]):
        count = len(group)
        expected = EXPECTED_COUNTS.get(idx_name)

        if expected and count != expected:
            msg = f"  {rev_date} {idx_name}: oczekiwano {expected} spółek, znaleziono {count}"
            warnings.append(msg)

        # Sprawdź duplikaty ISIN
        dupes = group[group.duplicated(subset=["isin"], keep=False)]
        if not dupes.empty:
            msg = f"  {rev_date} {idx_name}: zduplikowane ISIN-y: {dupes['isin'].unique().tolist()}"
            warnings.append(msg)

        # Sprawdź czy suma udziałów jest bliska 100% (z tolerancją na zaokrąglenia)
        if idx_name != "WIG":
            weight_sum = group["weight_pct"].sum()
            if abs(weight_sum - 100.0) > 1.0:
                msg = f"  {rev_date} {idx_name}: suma udziałów = {weight_sum:.2f}% (oczekiwano ~100%)"
                warnings.append(msg)

        # Sprawdź ciągłość Lp
        lps = sorted(group["lp"].tolist())
        expected_lps = list(range(1, count + 1))
        if lps != expected_lps:
            msg = f"  {rev_date} {idx_name}: nieciągłe Lp: {lps[:5]}...{lps[-3:]}"
            warnings.append(msg)

    return warnings


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="GPW Benchmark Historical Portfolio Scraper")
    parser.add_argument("--skip-download", action="store_true",
                        help="Pomiń pobieranie, parsuj istniejące pliki")
    parser.add_argument("--only-index", type=str, default=None,
                        choices=INDEX_NAMES,
                        help="Parsuj tylko wybrany indeks")
    parser.add_argument("--dry-run", action="store_true",
                        help="Pokaż co zostanie pobrane, bez pobierania")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- 1. Lista plików do przetworzenia ----
    indices = [args.only_index] if args.only_index else INDEX_NAMES
    targets = []
    for y, m, d in REVISION_DATES:
        rev_date = f"{y:04d}-{m:02d}-{d:02d}"
        for idx in indices:
            url = build_pdf_url(y, m, d, idx)
            fname = f"{y:04d}_{m:02d}_{d:02d}_{idx}.pdf"
            targets.append((rev_date, idx, url, PDF_DIR / fname))

    if args.dry_run:
        print(f"\nDry run: {len(targets)} plików do pobrania/przetworzenia:")
        for rev_date, idx, url, path in targets:
            exists = "✓" if path.exists() else "✗"
            print(f"  [{exists}] {rev_date} {idx:8s} -> {path.name}")
        return

    # ---- 2. Pobieranie ----
    if not args.skip_download:
        log.info(f"Pobieranie {len(targets)} PDFów...")
        session = requests.Session()
        session.headers.update({
            "User-Agent": "GPW-Research-Bot/1.0 (academic research)",
        })
        downloaded = 0
        for rev_date, idx, url, path in targets:
            PDF_DIR.mkdir(parents=True, exist_ok=True)
            if download_pdf(url, path, session):
                downloaded += 1
            time.sleep(DOWNLOAD_DELAY_SEC)
        log.info(f"Pobrano {downloaded}/{len(targets)} plików")
    else:
        log.info("Pomijam pobieranie (--skip-download)")

    # ---- 3. Parsowanie ----
    log.info("Parsowanie PDFów...")
    all_portfolio: list[PortfolioRow] = []
    all_reserves: list[ReserveRow] = []
    parse_errors: list[str] = []

    for rev_date, idx, url, path in targets:
        if not path.exists():
            log.warning(f"  Brak pliku: {path.name} — pomijam")
            continue

        try:
            portfolio, reserves = parse_portfolio_pdf(path, rev_date, idx)
            all_portfolio.extend(portfolio)
            all_reserves.extend(reserves)

            n_flags = sum(1 for r in portfolio if r.flags)
            log.info(
                f"  {rev_date} {idx:8s}: "
                f"{len(portfolio):3d} spółek, "
                f"{len(reserves):d} rezerwowych, "
                f"{n_flags} z flagami"
            )
        except Exception as e:
            msg = f"  BŁĄD parsowania {path.name}: {e}"
            log.error(msg)
            parse_errors.append(msg)

    # ---- 4. Budowa DataFrame ----
    if not all_portfolio:
        log.error("Brak danych do zapisania!")
        return

    portfolio_df = pd.DataFrame([vars(r) for r in all_portfolio])
    reserve_df = pd.DataFrame([vars(r) for r in all_reserves]) if all_reserves else pd.DataFrame()

    # Typy kolumn
    portfolio_df["revision_date"] = pd.to_datetime(portfolio_df["revision_date"])
    portfolio_df["ranking_date"] = pd.to_datetime(portfolio_df["ranking_date"], errors="coerce")

    if not reserve_df.empty:
        reserve_df["revision_date"] = pd.to_datetime(reserve_df["revision_date"])

    # ---- 5. Walidacja ----
    log.info("Walidacja...")
    warnings = validate_results(portfolio_df, reserve_df)
    if warnings:
        log.warning(f"Znaleziono {len(warnings)} ostrzeżeń:")
        for w in warnings:
            log.warning(w)
    else:
        log.info("Walidacja OK — brak ostrzeżeń")

    # ---- 6. Zapis ----
    portfolio_path = OUTPUT_DIR / "index_portfolios.parquet"
    portfolio_df.to_parquet(portfolio_path, index=False)
    log.info(f"Zapisano portfele: {portfolio_path} ({len(portfolio_df)} wierszy)")

    if not reserve_df.empty:
        reserve_path = OUTPUT_DIR / "reserve_lists.parquet"
        reserve_df.to_parquet(reserve_path, index=False)
        log.info(f"Zapisano listy rezerwowe: {reserve_path} ({len(reserve_df)} wierszy)")

    # ---- 7. Podsumowanie ----
    print("\n" + "=" * 70)
    print("PODSUMOWANIE")
    print("=" * 70)
    print(f"Zakres dat:      {portfolio_df['revision_date'].min().date()} -> "
          f"{portfolio_df['revision_date'].max().date()}")
    print(f"Liczba rewizji:  {portfolio_df['revision_date'].nunique()}")
    print(f"Indeksy:         {sorted(portfolio_df['index_name'].unique())}")
    print(f"Wierszy łącznie: {len(portfolio_df):,}")
    print(f"Unikalne ISIN-y: {portfolio_df['isin'].nunique()}")

    # Statystyki flag
    flagged = portfolio_df[portfolio_df["flags"] != ""]
    if not flagged.empty:
        print(f"\nFlagi:")
        all_flags = flagged["flags"].str.split(",").explode()
        for flag, count in all_flags.value_counts().items():
            print(f"  {flag:25s}: {count:4d} wystąpień")

    if not reserve_df.empty:
        print(f"\nListy rezerwowe: {len(reserve_df)} wierszy "
              f"({reserve_df['revision_date'].nunique()} rewizji)")

    if parse_errors:
        print(f"\nBŁĘDY PARSOWANIA ({len(parse_errors)}):")
        for e in parse_errors:
            print(f"  {e}")

    if warnings:
        print(f"\nOSTRZEŻENIA WALIDACJI ({len(warnings)}):")
        for w in warnings:
            print(f"  {w}")

    # ---- 8. Zapis CSV (human-readable debug) ----
    csv_path = OUTPUT_DIR / "index_portfolios_debug.csv"
    portfolio_df.head(200).to_csv(csv_path, index=False)
    log.info(f"Debug CSV (200 wierszy): {csv_path}")

    print("\nGotowe.")


if __name__ == "__main__":
    main()
