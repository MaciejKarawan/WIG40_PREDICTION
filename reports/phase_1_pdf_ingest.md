# Faza 1 — raport ingestu PDFów (2025-12-19, 2026-03-20)

**Data wykonania:** 2026-05-12
**Zakres:** rozszerzenie `output/wig_history/index_portfolios.parquet` o dwie nowe rewizje (WIG + mWIG40).

## Wynik per (rewizja × indeks)

| Rewizja | Indeks | Wierszy | Ranking date | Nulls | Dup ISIN | Σ weight (%) | Lp max | Flagged | Status |
|---------|--------|---------|--------------|-------|----------|--------------|--------|---------|--------|
| 2025-12-19 | WIG    | 326 | 2025-11-28 | 0 | 0 | 99.9996  | 326 | 29 | ✓ |
| 2025-12-19 | mWIG40 |  40 | 2025-11-28 | 0 | 0 | 100.0002 |  40 |  3 | ✓ |
| 2026-03-20 | WIG    | 324 | 2026-02-27 | 0 | 0 | 100.0003 | 324 | 29 | ✓ |
| 2026-03-20 | mWIG40 |  40 | 2026-02-27 | 0 | 0 |  99.9999 |  40 |  3 | ✓ |

**Listy rezerwowe (mWIG40):** 4 wpisy dla 2025-12-19, 4 wpisy dla 2026-03-20 → łącznie 8 wierszy w `reserve_lists.parquet`.

## Stan parquet

- **Baseline (przed Fazą 1):** 9038 wierszy, 19 rewizji × 4 indeksy.
- **Po Fazie 1:** 9768 wierszy = baseline + 326 (WIG 2025-12) + 40 (mWIG40 2025-12) + 324 (WIG 2026-03) + 40 (mWIG40 2026-03).
- **Stare rewizje:** nieruszone (9038 wierszy zgadza się co do jednego).
- **Pełna walidacja scrapera:** "Walidacja OK — brak ostrzeżeń".

## Diagnozy w trakcie wykonania

### Problem 1: scraper łapał wiersze z wielu indeksów
**Objaw:** WIG 2025-12 → 993 wierszy zamiast ~330; każde Lp pojawiało się 3× w danych; walidacja zgłosiła setki duplikatów ISIN.

**Przyczyna:** od rewizji 2025-12 GPW Benchmark publikuje PDF WIG, który zawiera kompozycje wielu indeksów rodziny WIG w jednym pliku 34-stronicowym (WIG, WIG140, WIGdiv, WIGdivplus, WIG.MS-BAS/ECM/FIN, WIG.GAMES5, WIGind, WIGmed, WIGtechTR, WIG-Poland, WIG-CEE, WIG-Ukraine). Dotychczasowy format (do 2025-09 włącznie) miał tylko jeden indeks na plik.

**Fix:** nowa funkcja `extract_text_for_index(pdf_path, index_name)` filtruje strony po nagłówku "Portfel indeksu <X>" i pobiera tylko strony pasujące dokładnie do `index_name`. `parse_portfolio_pdf` używa jej zamiast `extract_text_from_pdf`. Plik: `bin/gpw_benchmark_scraper.py`.

Lokalizacja sekcji WIG w nowym formacie: strony 0–8 (9 stron, identycznie jak w starym formacie).

### Problem 2: ścieżka OUTPUT_DIR
**Objaw:** scraper domyślnie zapisywał do `./output/`, podczas gdy `mwig_replication.config.INDEX_PORTFOLIOS_PATH` oczekuje `./output/wig_history/`.

**Fix:** `OUTPUT_DIR = Path("./output/wig_history")` w scraperze (linia 63).

### Problem 3: niespójne schematy CSV mWIG40
**Objaw:** `mwig40_122025.csv` i `mwig40_032026.csv` mają lekko różne nagłówki (`Kod` vs `Kod ISIN`, `Typ wpisu` vs `Typ wpisu (Inferred)`, "portfel główny" vs "Główny portfel") choć po inspekcji obie zawierają 8 kolumn (40 + 4 wiersze).

**Fix:** `bin/ingest_mwig40_csv.py` rozwiązuje kolumny case-insensitively przez zestawy aliasów (`COL_ISIN`, `COL_TYPE`, etc.) i normalizuje `Typ wpisu` testem na zawieranie "głów" (pokrywa oba warianty kolejności).

## Out of scope (zgodnie z decyzją użytkownika)

- **WIG20** i **sWIG80** dla rewizji 2025-12-19 i 2026-03-20 — nie wchodzą do parquet. Dane istnieją w combined PDFach (`data/Portfele_WIG20_mWIG40_sWIG80_WIG30_*.pdf`) i mogą zostać dołożone osobno w razie potrzeby (np. dla symulacji przepływów między indeksami w Fazach 3+).

## Zmodyfikowane / utworzone pliki

- **Modyfikacja:** `bin/gpw_benchmark_scraper.py` — `REVISION_DATES` (+2 wpisy), `OUTPUT_DIR`, nowa funkcja `extract_text_for_index`, podmiany `extract_text_from_pdf` → `extract_text_for_index` w `parse_portfolio_pdf`.
- **Modyfikacja:** `mwig_replication/config.py` — szkielet `REVISIONS["2026-03-20"]` (placeholdery liczbowe, do uzupełnienia w Fazie 3b).
- **Nowy:** `bin/ingest_mwig40_csv.py` — ingest 2 CSV-ek do parquet (idempotentny: usuwa istniejące mWIG40 dla rewizji i appenduje świeże).
- **Nowy:** `reports/phase_1_pdf_ingest.md` (ten plik).
- **Zaktualizowany:** `output/wig_history/index_portfolios.parquet`, `output/wig_history/reserve_lists.parquet`.
- **Backup:** `output/wig_history/index_portfolios.parquet.bak` (baseline z 9038 wierszy, można usunąć po akceptacji Fazy 1).

## STOP & REVIEW

Punkt halt — czekam na akceptację przed startem Fazy 2 (walidacja stooq vs PDF dla WIG 2026-03).
