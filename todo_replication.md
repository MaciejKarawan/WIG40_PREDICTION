# Notatka dla agenta — niedociągnięcia projektu mWIG40

**Projekt:** replikacja rankingu GPW Benchmark (Etap A) + analiza statystyczna predykatów wejścia do mWIG40 (Etap B).
**Zakres notatki:** wyłącznie niedociągnięcia **już oznaczone w `main.tex`** — pominięto usterki redakcyjne dokumentu.

## Zasady czytania

- Każda pozycja ma w nawiasie **marker źródłowy** z dokumentu: `ZAŁOŻENIE` (makro `\todo`), `OTWARTE` (makro `\openq`), `Luki metodologiczne` (sek. 6.6), `Zastrzeżenia` (sek. 5.5) lub `Postawienie zadania` (reszty niepewności trzonu deterministycznego, sek. 1).
- **„Co":** opis wierny dokumentowi (fakt).
- **„Naprawa":** proponowany krok operacyjny — to moja propozycja, nie cytat. Gdzie kierunek naprawy wskazuje sam dokument, oznaczono `(kierunek z dok.)`.
- **Rama nadrzędna:** replikacja jest zwalidowana **wyłącznie dla epoki 4** (od 31.01.2025: rewizje 2025-03 i 2026-03). Wszystko poniżej należy czytać z tym ograniczeniem.
- **Ograniczenie autora notatki:** podstawą była tylko `main.tex` + regulamin (PDF), **bez dostępu do kodu/repo** — naprawy są na poziomie zadań/metodologii, nie konkretnych plików.

---

## A. Dane

### A1. Ceny adjusted vs surowe (Stooq) — bias `s_T` i komponentu obrotu (d) `[ZAŁOŻENIE; Zastrzeżenia; Postawienie zadania]`
- **Co:** Stooq zwraca ceny *adjusted* (skorygowane wstecznie o splity/dywidendy), a GPW Benchmark liczy na cenach surowych. Obrót = `close × volume`, więc dla spółek po splicie obrót nominalny jest zaniżony, po reverse-split — zawyżony. Dotyka `s_T` w replikacji **oraz** komponentu (d) `top_turnover_acceleration_360d` w analizie statystycznej. Zwroty i zmienność (komponenty b, c) są niezmiennicze, więc nietknięte. Ręczny eksport ze Stooq udostępnia flagi nieskorygowane, ale **API ich nie przyjmuje** — potwierdzony ślepy zaułek.
- **Wpływ:** prawdopodobnie częściowo tłumaczy różnicę recall 90 % (2025-03) vs 100 % (2026-03) — w drugim przypadku przy progu nie było spółek po znaczących splitach.
- **Naprawa:**
  1. Pozyskać ceny **surowe (nieskorygowane)** z dostępem programistycznym (alternatywny dostawca **do zidentyfikowania i zweryfikowania** — nie zakładam tu konkretnego, bo nie mam potwierdzenia pokrycia GPW; ewentualnie zautomatyzować ręczny eksport ze Stooq, skoro flagi działają tylko tam).
  2. Najpierw **zmierzyć skalę biasu**: zliczyć spółki ze split/reverse-split w oknach rankingowych 2021–2026 i ile z nich trafia w okolice progu mWIG40 (`(kierunek z dok.)` — „liczba spółek z istotnymi splitami do policzenia osobno").
  3. Przeliczyć `s_T` i komponent (d) na cenach surowych choćby na **podzbiorze rewizji** jako walidację `(kierunek z dok.)`.

### A2. Free-float zaokrąglony do tysiąca w PDF `[Postawienie zadania; sek. 4.5]`
- **Co:** historyczne pakiety FF z PDF GPW są zaokrąglane do tysiąca akcji — różnice nieznaczne, ale systematyczne (rzędu setek akcji na pakiet; walidacja na 5 spółkach: −170 do −655).
- **Naprawa:** traktować jako znany, systematyczny szum poniżej rozdzielczości rankingu. Tylko jeśli różnice rankingowe przy progu zejdą do tego rzędu — pozyskać niezaokrągloną liczbę FF z raportów emitenta / KDPW dla spółek granicznych. **Niski priorytet.**

### A3. Brak historycznego statusu Lista Alertów / Strefa Niskiej Płynności `[Postawienie zadania]`
- **Co:** filtry bazowe wymagają wykluczenia spółek z Listy Alertów / Strefy Niskiej Płynności, ale brak historycznego dostępu do tego statusu na dzień rankingu. Replikacja może błędnie zakwalifikować spółkę, która faktycznie była wykluczona.
- **Naprawa:** pozyskać historyczne komunikaty GPW (Lista Alertów / SNP) i zbudować tabelę *status × spółka × data*; spółki z tym statusem odrzucać w filtrze bazowym. Do czasu pozyskania — świadomość ryzyka błędnej kwalifikacji granicznych spółek.

---

## B. Replikacja rankingu

### B1. Wybór kursu z 5-sesyjnego okna do `s_C` `[ZAŁOŻENIE; OTWARTE; Postawienie zadania]`
- **Co:** regulamin: „losowo wybrany kurs zamknięcia z ostatnich 5 sesji przed dniem rankingu" — konkretna sesja nie jest publicznie znana. W replikacji użyto kursu z dnia rankingu (lub najbliższej sesji). Walidacja empiryczna sugeruje, że odchylenie nie przekracza progu istotnego dla wyniku.
- **Naprawa:** zweryfikować ilościowo: dla każdej zwalidowanej rewizji policzyć ranking dla każdego z 5 możliwych kursów i sprawdzić, czy skład mWIG40 jest **niezmienniczy**. Jeśli tak — udokumentować jako nieistotne. Jeśli nie — oznaczyć spółki wrażliwe na wybór sesji.

### B2. Próg MWO dla rewizji 2026-06 nieopublikowany `[OTWARTE]`
- **Co:** próg MWO obowiązujący dla 2026-06 nie był opublikowany; podstawiono ostatnią znaną wartość. Dokument zaznacza, że progi krążyły wokół podobnych wartości, więc ryzyko prawdopodobnie niskie.
- **Naprawa:** po publikacji progu przez GPW Benchmark — podstawić właściwą wartość i przeliczyć. Test wrażliwości: czy spółki graniczne (ASSECOBS poz. 47, EUROCASH poz. 81) zmieniają kwalifikację MWO w realistycznym zakresie progów. Wartość zastępcza pozostaje **jawnie oznaczona** do czasu publikacji.

### B3. Mechanika epok 0–3 niezwalidowana `[OTWARTE; Zastrzeżenia]`
- **Co:** dla epok 0–3 (przed 31.01.2025) progi bufora, parametryzacja MWO i mechanika wejścia nie są zwalidowane numerycznie. Hipoteza: spółki dobierane „kolejno z pozycji 21–60", bez odrębnego progu wejścia poniżej 50/45 — niepotwierdzona. W regulaminie nie znaleziono informacji o oknach buforowych dla tych epok; temat porzucony wraz z rezygnacją z pełnej walidacji historycznej.
- **Wpływ:** bezpośrednio uruchamia B7.
- **Naprawa (decyzja do podjęcia):**
  - **(a)** odzyskać parametry buforów z regulaminów epok 0–3 (regulaminy historyczne GPW Benchmark) i zwalidować numerycznie na ≥2–3 rewizjach z każdej epoki, **albo**
  - **(b)** świadomie ograniczyć wszystkie wnioski replikacyjne i statystyczne do epoki 4 i tak je etykietować.

### B4. Fast-track — mechanika nieuwzględniona, próg niepewny `[OTWARTE]`
- **Co:** reguła fast-track (od 21.03.2022): debiut z kapitalizacją FF ≥ próg łącznej FF mWIG40 wchodzi nadzwyczajnie. Dokument zawiera **niepewność progu: 2,5 % vs 4 %** (znak zapytania w tekście). Jeden przypadek w danych: Żabka, 2024-12-20.
- **Naprawa:** ustalić obowiązującą wartość progu **i** datę wejścia parametru z regulaminu (nie zgaduję, która wartość — wymaga sprawdzenia źródła). Zaimplementować regułę i zwalidować na przypadku Żabki.

### B5. Wezwania (100 % akcji) — tabela ESPI/KNF nie zbudowana `[OTWARTE]`
- **Co:** reguła wezwań (od 21.06.2024): spółki w trakcie dobrowolnego wezwania na 100 % akcji są wyłączane z rankingu (by uniknąć sztucznego pompowania pozycji obrotami wezwawczymi). Tabela wezwań nie istnieje → spółki w wezwaniu nie są wyłączane.
- **Wpływ:** ryzyko fałszywie negatywnych predykcji.
- **Naprawa:** pozyskać tabelę wezwań (źródło: ESPI/KNF) dla okresu od 21.06.2024 (epoka 3+); spółki w trakcie wezwania a priori wyłączać z rankingu.

### B6. Predykcja 2026-06 liczona na danych do 2026-05-15 zamiast dnia rankingu 2026-05-22 `[OTWARTE]`
- **Co:** ranking policzony na danych do sesji 2026-05-15 (5 sesji przed pełnym dniem rankingu). Predykcja jest wstępna.
- **Naprawa:** po sesji 2026-05-22 przeliczyć na pełnych danych i potwierdzić/skorygować hipotezę ASSECOBS ↔ EUROCASH. Do tego czasu wynik etykietować jako wstępny.

### B7. Metodologia epoki 4 stosowana wstecz w analizie na 21 rewizjach `[OTWARTE]`
- **Co:** analiza statystyczna na 21 rewizjach (2021–2026) używa rankingu liczonego metodologią epoki 4 **także dla okresu, w którym ta metodologia nie obowiązywała**. To konsekwencja B3.
- **Naprawa:** dopóki epoki 0–3 niezwalidowane — albo zawęzić analizę statystyczną do rewizji z epoki 4, albo jawnie oznaczyć wszystkie wyniki sprzed 31.01.2025 jako liczone niewłaściwą dla okresu metodologią (dotyczy **danych**, nie tylko opisu). Docelowo, po walidacji epok 0–3: przeliczyć ranking historyczny właściwą metodologią per epoka.

---

## C. Analiza statystyczna predykatów

### C1. Brak rozróżnienia entrantów „z dołu" vs „z góry" `[Luki metodologiczne]`
- **Co:** awans ze sWIG80 (76 % przypadków) i democja z WIG20 (14 %) to jakościowo różne mechanizmy. Dla spółki spadającej z WIG20 metryka „relatywna siła sektorowa" może działać **w przeciwnym kierunku** (entrant z WIG20 to często ujemne momentum). Analiza łączy obie grupy → tłumi sygnał i zniekształca interpretację post-revision.
- **Naprawa:** rozdzielić na buckety per mechanizm — *promotions* (sWIG80/głębszy WIG), *demotions* (WIG20), *new listings* (event-driven) — i liczyć metryki osobno `(kierunek z dok.)`.

### C2. Mała próbka `[Luki metodologiczne]`
- **Co:** 28 entrantów na 659 obserwacji; dla score ≥ 4 tylko 10 obserwacji. Estymaty precision/recall przy wysokich progach mają szerokie przedziały ufności.
- **Naprawa:**
  1. Rozszerzyć dataset przez przejście na uniwersum *as-of* (→ C4) — odzyskuje 17 „niewidocznych" entrantów (45 vs 28).
  2. Raportować przedziały **Wilsona** przy każdym progu score, nie punktowe precision.
  3. Walidacja **out-of-sample**: train 2021–2023 / test 2024–2026 `(kierunek z dok.)`.

### C3. Brak rozróżnienia reżimów rynkowych `[Luki metodologiczne]`
- **Co:** okres 2021–2026 obejmuje covid, inwazję Rosji na Ukrainę, hossę 2024–2025. Składanie wszystkich rewizji do jednego datasetu zakłada stałość wzorców w różnych reżimach — niesprawdzone.
- **Naprawa:** wprowadzić podział na reżimy (np. po trendzie szerokiego WIG w oknie poprzedzającym rewizję) i sprawdzić stabilność liftów; minimum — raportować lift osobno dla podokresów.

### C4. Uniwersum z poprzedniej rewizji zamiast replikowanego rankingu *as-of* `[Luki metodologiczne]` — **największy punkt zwrotny**
- **Co:** uniwersum diagnostyczne budowane na `previous_wig_weight_rank`, nie na replikowanym rankingu w każdym punkcie czasowym. Spółki, które „wskoczyły" w okolice progu **między** rewizjami, są systematycznie pomijane → pokrycie 62 % i zaniżona precyzja samego konceptu „bliskość progu".
- **Wpływ:** dokument wprost nazywa to **założeniem o największym potencjalnym wpływie** na wyniki — może istotnie zmienić wnioski całej analizy.
- **Naprawa:** przebudować definicję uniwersum z `previous_wig_weight_rank` na `replicated_rank_asof_prediction_date` (wymaga historycznego panelu replikowanego rankingu dynamicznego z Etapu A). Spółka w uniwersum, jeśli jej replikowany ranking na dzień predykcji mieści się w okolicach progu mWIG40 `(kierunek z dok.)`.

### C5. Metryki liczone tylko do `anchor_date` `[Luki metodologiczne]`
- **Co:** lookback jednowymiarowy — jeden offset na rewizję. Brak pomiaru, jak wcześnie sygnał staje się ostry.
- **Naprawa:** zmienić panel z (spółka × rewizja) na (spółka × rewizja × `prediction_date`), siatka offsetów np. `[360, 240, 120, 60, 30, 14, 7, 0]` sesji przed dniem rankingu; metryki liczone do `prediction_date` `(kierunek z dok.)`.

### C6. Fast-track i wezwania niewydzielone w analizie `[Luki metodologiczne]`
- **Co:** oba mechanizmy są event-driven, nie pattern-driven; ich zmieszanie z „normalnymi" awansami pogarsza statystyki sygnałów rynkowych.
- **Naprawa:** oznaczyć/wyłączyć przypadki event-driven w datasecie statystycznym i modelować osobno (spójne z C1, B4, B5).

### C7. Tautologia okna 240–360 z oknem rankingowym `s_T` `[ZAŁOŻENIE; Podsumowanie]` — **krytyczny dla interpretacji**
- **Co:** okno 240–360 sesji niemal pokrywa się z 12-miesięcznym oknem obrotów GPW Benchmark (komponent `s_T`), kończącym się w dniu rankingu. Wysokie momentum/zmienność/obrót w tym oknie są skorelowane z wysoką **bieżącą** pozycją rankingową w tym samym dniu. Obecne wyniki mówią więc o **korelacji z aktualną pozycją rankingową**, nie o **lead-time predykcji**.
- **Naprawa:** liczyć metryki do `prediction_date` **cofniętego** względem dnia rankingu (np. 60/120/240 sesji wcześniej), tak by okno predykcji nie pokrywało się z oknem `s_T` (wymaga C5 + C4). **Do czasu naprawy nie interpretować liftów jako lead-time** — dokument już to zastrzega w Podsumowaniu.

### C8. Komponenty score nieniezależne `[Zastrzeżenia score; sek. 6.5]`
- **Co:** komponenty (b) momentum, (c) zmienność, (d) obrót liczone na tym samym oknie 360 sesji i tych samych OHLCV — odzwierciedlają ten sam wymiar „aktywności rynkowej vs sektor". Empiryczna korelacja **niepoliczona**. Wynik score ≥ 4 (10 obs, Wilson CI ≈ [39 %, 90 %]) jest praktycznie nieinformatywny jako estymator punktowy.
- **Naprawa:** policzyć empiryczną korelację między (b), (c), (d); zastąpić koniunkcję binarną **modelem wagowym** (np. regresja logistyczna) na rozszerzonym, OOS-walidowanym datasecie `(kierunek z dok.)`. Wynik score ≥ 4 traktować jako trop, nie liczbę operacyjną.

---

## Sugerowana kolejność prac

> Ta sekcja to **moja rekomendacja kolejności**, a nie element dokumentu. Niedociągnięcia powyżej są z `main.tex`; ich uszeregowanie — nie.

1. **C4** (uniwersum *as-of*) + **C5** (panel z `prediction_date`) — wspólny fundament; odblokowują C2, C7 i wszystkie metryki rankingowe *as-of*.
2. **C7** — rozbrojenie tautologii lookback/`s_T`; bez tego interpretacja liftów jest niepewna.
3. **A1** (ceny surowe) — największa naprawa po stronie danych; warunek wiarygodności `s_T` i komponentu (d). Krok wstępny: zmierzyć skalę biasu (A1.2).
4. **C2 + C8** — przedziały ufności, walidacja OOS, model wagowy zamiast koniunkcji.
5. **B3 + B7** — decyzja o epokach 0–3 (zwalidować vs zawęzić do epoki 4); inaczej analiza na 21 rewizjach pozostaje obarczona błędem metodologicznym.
6. **B5** (wezwania) + **B4** (fast-track) + **C1/C6** (buckety per mechanizm) — domknięcie obsługi zdarzeń event-driven.
7. **B6 / B2** — przeliczenie predykcji 2026-06 po dniu rankingu i po publikacji progu MWO (niskie ryzyko, ale do domknięcia).
8. **B1 / A3 / A2** — weryfikacje uzupełniające (kurs z 5-sesyjnego okna, status Listy Alertów, zaokrąglenie FF); niski priorytet.
