# Faza A — replikacja historyczna mWIG40: podsumowanie progresu

## 1\. Cel i kontekst

**Cel pierwotny:** historyczna replikacja rankingu mWIG40 dla 19 rewizji w okresie 2021-03-19 → 2025-09-19, jako proof-of-concept przed Fazą B (modelowanie predykcji następnego składu).

**Status:** zatrzymane na rewizji 2025-03-21 z wynikiem **F1 = 90%** (wynik 36/40). Decyzja o pivocie do trybu real-time.

\---

## 2\. Co zostało zrealizowane

### Metodologia

* Epoki metodologiczne (5 sztuk, granice w §3)
* Filtry: bazowe (FF, transakcje 3M, próg 1 mln EUR), MWO (8/12 + 4/6), ostatni kwartyl
* Ranking: `R(i) = 0.4·sT + 0.6·sC`
* Reguły bufora mWIG40 (próg wejścia 50, utrzymania 70 — od 31.01.2025)
* Reguła dopełniania do 40 spółek

### Dane historyczne

* `output/wig\_history/index\_portfolios.parquet` — 19 rewizji × 4 indeksy (WIG, WIG20, mWIG40, sWIG80), zescrapowane i sparsowane z PDFów GPW Benchmark
* `output/wig\_history/reserve\_lists.parquet` — listy rezerwowe per rewizja
* `output/maps/ticker\_isin\_stooq\_map.csv` — mapping ISIN → stooq\_ticker (431 wierszy)
* `output/2025\_03\_revision/wig2025\_03\_ohlcv.parquet` — OHLCV dzienny dla 330 spółek WIG, 02.2024 → 02.2025

### Walidacja na 2025-03

* **Recall: 90.00%** (36/40)
* 4 false positives, 4 false negatives — z dokładną diagnostyką per spółka

\---

## 3\. Co odkryliśmy w trakcie

### Ustalenia metodologiczne

**5 epok metodologicznych** (granice — daty wejścia w życie nowych regulacji):

1. epoka 0 — przed 2022-03-21
2. epoka 1 — od 2022-03-21
3. epoka 2 — od 2023-06-19
4. epoka 3 — od 2024-06-21
5. epoka 4 — od 2025-01-31

**Konkretne odkrycia:**

* Progi wejścia 50/utrzymania 70 dla mWIG40 obowiązują **dopiero od 31.01.2025**. Wcześniej obowiązywała formuła "kolejno z miejsc 21-60" (do potwierdzenia numerycznego).
* MWO **formalnie przeparametryzowane w 06.2023**, ale **praktycznie publikowane kwartalnie dopiero od 06.2024**.
* **Reguła dopełniania składu** sformalizowana w komunikacie z 19.06.2023.

### Ustalenia techniczne

* **Stooq CSV API zwraca tylko ceny adjusted**.
* **DINOPL 10:1**: PDF GPW pokazuje 485-495 zł, stooq 48 zł — split przeniesiony wstecznie przez stooq, niewidoczny dla GPW Benchmark.
* **Niespójność dat między PDFami GPW dla tej samej rewizji:**

  * PDF **WIG** ma `ranking\_date = 2025-02-28` (tydzień przed datą rewizji 2025-03-21)
  * PDF **WIG20 / mWIG40 / sWIG80** mają `ranking\_date = 2025-02-21` (faktyczny dzień rankingu)
* **Pakiety FF:**

  * W PDF WIG to **surowy free-float** (potwierdzone na 5 spółkach: PKOBP 666 mln szt vs WIG20 724 mln szt — WIG ma wartości przed cap'owaniem)
  * W PDF mWIG40 mogą być **cap'owane do 10%** udziału w indeksie

  \---

  ## 4\. Blocker który uniemożliwił 100% recall

  Do liczenia rankingu `R(i) = 0.4·sT + 0.6·sC` potrzebujemy **surowych cen z 21.02** (data rankingu mWIG40). Aktualna sytuacja źródeł:

|Źródło|Liczba spółek|Ceny|Data|Status|
|-|-:|-|-|-|
|PDF mWIG40 + WIG20 + sWIG80|**140**|surowe (raw)|21.02 ✓|OK, ale tylko podzbiór WIG|
|PDF WIG|**330**|surowe (raw)|**28.02 ✗**|zła data — tydzień przesunięcia.|
|Stooq CSV API|**330**|**adjusted ✗**|21.02 ✓|skażone splitami/dywidendami|

**Sedno problemu:** dla 190 spółek z WIG (poza WIG20+mWIG40+sWIG80) **nie mamy surowych cen na 21.02**. To uderza w `ff\_market\_cap\_pln` i tym samym w `sC`, a w konsekwencji w `R(i)` i kaskadowe przypisanie do indeksów.

\---

## 5\. Kroki potrzebne do dokończenia historycznej replikacji

### Krok 1 — pozyskać surowe ceny historyczne (3 opcje do rozważenia)

|Opcja|Plus|Minus|
|-|-|-|
|**A.** Scraper HTML stooq|bez kosztu, dane na 21.02|kruche (zmiana layoutu HTML); niepewne czy raw|
|**B.** Inny dostawca (bossa.pl, infostrefa, GPW Data Feed)|jakość danych|osobny pipeline|
|**C.** Komercyjny dataset GPW Benchmark / Refinitiv / Bloomberg|autorytatywne, dokładnie te ceny których używa GPW|koszt|

### Krok 2 — pozyskać brakujące progi MWO dla rewizji 2021-03 → 2022-12 (8 rewizji)

* Archiwum komunikatów GPW Benchmark
* Ewentualnie jawne wyliczenie z surowych OHLCV (jeśli mamy raw volumes)

### Krok 3 — walidacja replikacji na wszystkich 19 rewizjach

## 6\. Pivot do real-time — predykcja rewizji 2026-06-19

Po historycznej walidacji na 2026-03 (recall ~90%) pivot do trybu prospektywnego: zamiast szukać 100% recall wstecz, replikujemy najbliższą rewizję kwartalną (planowany ranking 22.05.2026, ogłoszenie ok. 19.06.2026), bez ground truth ale z pełnym pipelinem produkcyjnym.

### 6.1. Pozyskanie aktualnego uniwersum

* **Scraper biznesradar** (`scrape_wig_biznesradar.py`) — parsuje stronę `biznesradar.pl/gielda/indeks:WIG` do DataFrame z 326 spółkami obecnie w WIG. Kolumny: `ticker_short`, `ticker_long`, `name`, `price`, `volume`, `turnover`, `weight_pct`.
* Zapisany snapshot: `data/biznesradar/WIG_20260513_2207.parquet` (+ równolegle WIG20, mWIG40, sWIG80 z tej samej sesji).
* Sanity check: Σweight ≈ 100.001%, liczba spółek w mWIG40/WIG20 zgodna z indeksami.

### 6.2. OHLCV ze stooq dla okna rankingu

* Skrypt `download_ohlcv_2026_06.py` — inkrementalny: bierze 322/326 tickerów z istniejącej `data/stooq_cache_eda_2021_2026` (covers do 2026-04-30), dla każdej spółki fetchuje deltę z (last_date+1) do `--date-to`. Dla 4 nowych spółek (CRQ Creotech Quantum, GNS Niewiadów, S2B Syn2Bio, SCW Scanway) pełen fetch.
* Window: 2025-05-22 → 2026-05-22 (12M okno rankingowe).
* Limit API stooq trafia po ~150 requestach — skrypt jest wznawialny (cache target).
* Output: `data/stooq_cache_2026_06/` (326 plików parquet) + `output/2026_06_revision/wig2026_06_ohlcv.parquet` (77 866 wierszy, 326 tickerów, ostatnia sesja 2026-05-15).

### 6.3. Mapping tickerów biznesradar → stooq → ISIN

* 322/326 mapowanych przez `output/maps/ticker_isin_stooq_map.csv` (ticker_short = gpw_short).
* 4 brakujące (CRQ, GNS, S2B, SCW) — ISIN-y dopisane ręcznie po lookupie na biznesradar (`PLCTHQM00018`, `PLVNTCP00019`, `PLSNBIO00013`, `PLSCWAY00018`), stooq tickery = lowercase ticker_short.
* Backfill w OHLCV parquet (kolumna `isin`).

### 6.4. Parsing PDF WIG20 dla 2026-03-20 (poprzedniej rewizji)

* `index_portfolios.parquet` dla rewizji 2026-03-20 miał tylko WIG i mWIG40 (WIG20 brakował). Predykcja bez bufora WIG20 dawała fałszywe rotacje (3 spółki z marcowego mWIG40 fałszywie awansowały do WIG20).
* Rozszerzony `bin/ingest_wig20_combined.py` o źródło `Portfele_..._2026_03_05.pdf` page 0 → dodano 20 spółek WIG20 + 2 z listy rezerwowej.
* Po reingest predykcja jest stabilna (top 20 WIG20 to dokładnie marcowy skład, wszystkich 20 utrzymanych via buffer maintenance).

### 6.5. Konfiguracja rewizji 2026-06-19

W `mwig_replication/config.py` dodano `REVISIONS['2026-06-19']`:

```
ranking_date:       2026-05-22
previous_revision:  2026-03-20
type:               quarterly
epoch:              4
entry_threshold_wig20:        10
maintenance_threshold_wig20:  30
entry_threshold_mwig40:       45
maintenance_threshold_mwig40: 80
mwo_threshold_pct:            0.0100
```

Progi z `THRESHOLDS_EPOCH_4_QUARTERLY` (kwartalna: węższy entry, szerszy maintenance niż roczna 50/70). Asymetria progów 45/80 jest implicit'em bufora 46-80 z pkt 5.4.13 regulaminu — strefa ochrony dla dotychczasowych uczestników.

### 6.6. Skrypt predykcji `mwig_replication/predict_revision.py`

Równoległy orchestrator do `replicate_revision.py`, ale dla trybu prospektywnego (bez ground truth):

* **Universe** — z scrapu biznesradar (`build_universe_from_biznesradar`), nie z PDF WIG (którego dla 2026-06 jeszcze nie ma).
* **FF shares derived** — z biznesradar `weight_pct` × `TOTAL_FF_CAP` / `current_price`. `TOTAL_FF_CAP` obliczone z reference tickera **KGHM** (niecappowany blue chip): `ref_ff_shares (z marca) × ref_current_price / (ref_weight / 100)` ≈ 651.6 mld PLN.
* **Cena na dzień rankingu** — `close` stooq z najbliższej sesji ≤ ranking_date (2026-05-15, bo stooq nie ma jeszcze 22.05).
* **Previous mWIG40/WIG20** — z istniejącego `index_portfolios.parquet` (rewizja 2026-03-20).
* **Walidacja** — pomijana (brak ground truth do czerwca 2026).
* **Reużywa istniejących modułów**: `filters.py`, `ranking.py`, `buffer.py` bez zmian — tylko input data podstawiany.

Output: `output/2026_06_revision/prediction_2026-06-19.parquet` (326 wierszy z pełną diagnostyką), CSV z top 40, oraz wygenerowany notebook diagnostyczny (`prediction_2026-06-19.ipynb`) przez nowy `generate_prediction_notebook` w `notebook_generator.py`.

### 6.7. Wynik predykcji dla 2026-06-19

**Pipeline funnel:**

|Krok|Pozostało|
|-|-:|
|Universe (biznesradar)|326|
|Po filtrach bazowych|326|
|Po MWO (8/12 lub 4/6)|301|
|Po ostatnim kwartylu|225|

**Predicted mWIG40 (kompozycja):**

* 25 spółek z entry zone (pozycje 1-45 bez WIG20)
* 14 spółek z maintenance buffer (pozycje 46-80, was_in_mwig40_before=True)
* 1 spółka via fill-up (pkt 5.4.14 regulaminu): **ASSECOBS** na pozycji 47 — najlepsza pozycja w strefie 46-80 spoza dotychczasowego składu

**Δ vs 2026-03-20:**

* **WCHODZI** (1): **ASSECOBS** (Asseco Business Solutions, pos 47, fill-up)
* **WYCHODZI** (1): **EUROCASH** (pos 81, spadek poza próg maintenance 80 → do sWIG80)
* WIG20: bez zmian (wszystkie 20 marcowych utrzymane)

### 6.8. Zastrzeżenia metodologiczne

1. **Stooq adjusted vs raw**: cena na dzień rankingu = close stooq (skorygowany o splity/dywidendy wstecznie). GPW Benchmark używa cen surowych. Dla `sT` (turnover) close×volume jest niezmiennicze, więc OK. Dla `sC` (FF market cap) jest błąd proporcjonalny — ale ponieważ FF derived też używa tej samej skali cen, błędy się częściowo skracają w mianowniku sumarycznym.
2. **FF derived z biznesradar weight_pct** zamiast bezpośrednio z PDF: zakłada stałość KGHM FF shares między marcem a majem (brak split/buyback). Do zweryfikowania ESPI/raportami bieżącymi.
3. **Ranking_date 2026-05-22 vs ostatnia dostępna sesja stooq 2026-05-15**: brakuje 5 sesji. Re-run po 22.05 poprawi obraz.
4. **`apply_fill_up_rule` w `buffer.py` nie ogranicza do strefy 46-80**: per pkt 5.4.14 powinno wybierać tylko z 46-80, a per 5.4.15 dopiero z 81+ gdyby brakło. W naszym przypadku deficit=1 i kandydat (pos 47) i tak mieści się w 46-80, więc nieistotne. Do dotwardzenia w refaktorze.
5. **Synthetic ranking_date dla pkt 5.4.13**: regulamin mówi „4 tygodnie przed dniem korekty" — dla rewizji 19.06.2026 to 22.05.2026 (piątek). Ustawione w configu.

## 7\. Otwarte pytania / TODO

* Walidacja hipotezy mechaniki wejścia w epokach 0–3 ("kolejno z miejsc 21-60") — jak dokładnie GPW dobierał spółki w tym okresie
* Tabela wezwań ESPI/KNF (epoka 3+) — kiedy spółki są wykluczane mimo spełnienia rankingu
* Re-run predykcji po 22.05.2026 z pełnymi 12M danych do dnia rankingu
* Weryfikacja stałości FF KGHM (marzec→maj 2026) przez ESPI — jeśli się zmieniła, dotwardzić wybór reference tickera (np. mediana z 5 niecappowanych blue chipów)
* Wzmocnienie `apply_fill_up_rule` o ograniczenie strefy 46-80 (pkt 5.4.14), oddzielną gałąź dla pkt 5.4.15 (gdy w 46-80 brak kandydatów)
* Walidacja predykcji 2026-06-19 po ogłoszeniu faktycznego składu przez GPW Benchmark (czerwiec 2026)

