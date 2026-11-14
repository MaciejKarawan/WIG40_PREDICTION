# Raport roboczy: analiza wejść do mWIG40

## Cel analizy

Celem analizy jest sprawdzenie, czy przed rewizjami mWIG40 da się zidentyfikować powtarzalne wzorce rynkowe u spółek, które później wchodzą do indeksu.

Interesują nas przede wszystkim:

- spółki wchodzące do mWIG40,
- spółki z list rezerwowych,
- spółki blisko progów rankingowych,
- zachowanie kursu, zmienności i obrotu przed rewizją,
- porównanie spółek z ich sektorami,
- reakcja kursu po fakcie rewizji,
- kierunek dalszej analizy z użyciem replikowanego rankingu w czasie rzeczywistym.

Najważniejszy praktyczny cel jest operacyjny:

```text
wykryć spółkę, która zaczyna być realnym kandydatem do wejścia do mWIG40,
zanim rynek w pełni zdyskontuje ten fakt
```

## Zakres danych

Analiza obejmuje rewizje od `2021-03-19` do `2026-03-20`.

Dane wejściowe:

- historyczne składy indeksów WIG20, mWIG40, sWIG80 i WIG,
- historyczne listy rezerwowe,
- mapa sektorów,
- dane OHLCV dla spółek z WIG,
- panel zdarzeń `spółka x rewizja`,
- sektorowy panel porównawczy,
- panel cenowy dla kandydatów i peerów sektorowych.

Podstawowe liczby:

- 21 rewizji,
- 45 faktycznych wejść do mWIG40 po wyłączeniu rewizji bazowej,
- pełny OHLCV: 563 424 wiersze,
- 359 ISIN w pełnym OHLCV,
- panel eventów: 7 028 wierszy,
- universe `near_threshold` w obecnym teście diagnostycznym: 659 obserwacji,
- liczba unikalnych ISIN w universe `near_threshold`: 89,
- liczba entrantów w universe `near_threshold`: 28,
- liczba wszystkich entrantów po rewizji bazowej: 45.

## Co zostało zrobione

Zbudowaliśmy notebook EDA:

```text
notebooks/mwig40_transition_eda.ipynb
```

Notebook ma obecnie 7 sekcji:

1. Parametry
2. Wczytanie danych i sanity check
3. Widok jednej rewizji i otoczenie kandydatów
4. Wykresy dla rewizji
5. Drilldown po spółce
6. Test hipotezy dla wszystkich rewizji 2021-2026
7. Efekt po ogłoszeniu rewizji

Notebook wykonuje się kontrolnie bez błędów.

## Parametryzacja

Najważniejsze parametry w notebooku:

```python
REVISION_DATE = "2026-03-20"
FOCUS_TICKER = "CREOTECH"

PRIMARY_WINDOWS = [7, 14, 30, 60, 120]
PRE_WINDOWS = PRIMARY_WINDOWS.copy()

POST_ANCHOR_WINDOWS = [5, 20]
POST_REVISION_WINDOWS = [5, 20]
POST_FACT_WINDOWS = [1, 3, 7, 14, 30, 60, 120]
POST_FACT_SECTOR_TOP_PERCENTILE = 0.10

UNIVERSE_MODE = "near_threshold"
WEIGHT_RANK_CENTERS = [15, 70]
WEIGHT_NEIGHBOR_COUNT = 10

TOP_PERCENTILES = [0.10, 0.20, 0.30]
SCORING_WINDOW = 60
SCORING_TOP_PERCENTILE = 0.20

USE_CURRENT_RESERVE_AS_FEATURE = False
```

Okna są parametryzowalne. Najnowsze wnioski jakościowe uwzględniają również uruchomienie analizy z dłuższymi oknami, w tym do `360` sesji. Nie zmieniamy założenia, że `current_mwig40_reserve` nie jest dozwoloną zmienną predykcyjną.

## Jedna rewizja: analiza eksploracyjna

Dla wybranej rewizji notebook pokazuje:

- spółki, które weszły do mWIG40,
- spółki, które wyszły,
- poprzednią listę rezerwową,
- bieżącą listę rezerwową,
- spółki z okolic progów wagowych,
- peerów sektorowych.

Dla spółek dodaliśmy m.in.:

- `previous_mwig40_reserve_rank`,
- `current_mwig40_reserve_rank`,
- `previous_wig_weight_rank`,
- `wig_weight_rank`,
- sektor,
- poprzedni indeks,
- obecny indeks,
- stopy zwrotu,
- zmienność,
- obrót,
- drawdown,
- metryki względem sektora.

## Normalizacja wykresów

Dodaliśmy parametr:

```python
NORMALIZE_MODE = "window_start"
```

Działa w dwóch trybach:

```python
NORMALIZE_MODE = "window_start"
```

Pierwsza widoczna sesja na wykresie = `100`.

```python
NORMALIZE_MODE = "target_date"
```

Anchor/revision trading date = `100`.

Domyślnie używamy `window_start`, bo lepiej pokazuje, ile spółka urosła lub spadła od początku badanego okna.

## Test hipotezy: obecna wersja diagnostyczna

Obecna sekcja 6 testuje panel:

```text
spółka x rewizja
```

Target:

```python
entered_mwig40 == True
```

Pierwsza rewizja `2021-03-19` jest wykluczona, bo nie ma wcześniejszego punktu porównania.

Obecny universe `near_threshold` obejmuje spółki, które:

```text
nie były wcześniej w mWIG40
i
(
  były na poprzedniej liście rezerwowej mWIG40
  albo miały previous_wig_weight_rank blisko progów [15, 70]
)
```

„Blisko” oznacza:

```python
WEIGHT_NEIGHBOR_COUNT = 10
```

czyli okolice:

- rankingi `5-25` wokół progu `15`,
- rankingi `60-80` wokół progu `70`.

To jest wersja diagnostyczna. Docelowo universe powinien być budowany na podstawie replikowanego rankingu `as-of`, a nie na podstawie poprzedniej rewizji.

## Pokrycie obecnego universe

Dla obecnego universe `near_threshold`:

- liczba obserwacji: 659,
- liczba rewizji: 20,
- liczba unikalnych ISIN: 89,
- liczba entrantów w universe: 28,
- liczba wszystkich entrantów po rewizji bazowej: 45,
- pokrycie: 28 / 45 = 62.2%.

Tego pokrycia nie należy traktować jako oceny jakości procesu predykcyjnego. Jest to informacja o selektywności obecnego universe opartego o poprzednią rewizję.

W podejściu docelowym pokrycie powinno być liczone względem pytania:

```text
czy entrant był blisko progu w replikowanym rankingu na prediction_date?
```

## Interpretacja tabeli lift

Tabela lift odpowiada na pytanie:

```text
Jeśli w każdej rewizji wybiorę top X% spółek po danej metryce,
to czy w tej grupie entrantów jest więcej niż przeciętnie?
```

Kolumny:

- `metric` - badana metryka,
- `top_percentile` - wybierany procent kandydatów w każdej rewizji,
- `selected_rows` - liczba wybranych obserwacji,
- `selected_entrants` - ile z nich faktycznie weszło do mWIG40,
- `available_entrants` - ile entrantów było dostępnych dla tej metryki,
- `precision` - udział entrantów w wybranej grupie,
- `recall` - jaki procent wszystkich dostępnych entrantów złapaliśmy,
- `baseline_rate` - bazowa częstość wejścia w universe,
- `lift` - ile razy lepiej niż baseline.

Przykład interpretacji:

```text
ret_m360td_to_anchor_vs_sector, top 10%
selected_rows = 67
selected_entrants = 15
available_entrants = 25
precision = 22.4%
recall = 60.0%
baseline_rate = 4.3%
lift = 5.21
```

Interpretacja:

```text
Top 10% kandydatów po 360-sesyjnym momentum względem sektora
miało ponad 5 razy większe zagęszczenie entrantów niż cały universe.
```

Lift nie oznacza, że strategia ma 100% skuteczności. Oznacza, że dana metryka dobrze wzbogaca shortlistę w przyszłych entrantów.

## Główna aktualizacja: dłuższe okna dają wyższy lift

Po przesunięciu okien analitycznych dalej wstecz, szczególnie do `360` sesji, sygnał staje się wyraźnie mocniejszy.

To przesuwa interpretację z:

```text
rynek zaczyna grać wejście do mWIG40 tuż przed rewizją
```

na:

```text
spółki, które później wchodzą do mWIG40,
często są już od wielu miesięcy relatywnie silniejsze od sektora
```

Nie wygląda to wyłącznie jak krótki efekt „pod rewizję”. Bardziej przypomina dłuższy proces:

```text
fundamentalna / płynnościowa / rynkowa poprawa spółki
-> poprawa rankingu
-> wejście w obszar kandydatów
-> wejście do mWIG40
-> późniejszy brak premii lub mean reversion
```

## Najlepsze metryki po rozszerzeniu okien

Najwyższe lifty w wariancie z dłuższymi oknami:

```text
ret_m360td_to_anchor_vs_sector, top 10%:
lift 5.21
precision 22.4%
recall 60.0%

vol_m360td_ann_to_anchor_vs_sector, top 10%:
lift 4.17
precision 17.9%
recall 48.0%

vol_m180td_ann_to_anchor_vs_sector, top 10%:
lift 3.85
precision 15.5%
recall 44.0%

vol_m240td_ann_to_anchor_vs_sector, top 10%:
lift 3.85
precision 15.5%
recall 44.0%

ret_m240td_to_anchor_vs_sector, top 10%:
lift 3.50
precision 14.1%
recall 40.0%

turnover_ratio_m240td_to_anchor_vs_sector, top 10%:
lift 3.46
precision 16.7%
recall 40.0%
```

## Wniosek o momentum

Dłuższe momentum sektorowe jest obecnie najmocniejszym sygnałem.

Szczególnie istotne są:

```text
ret_m360td_to_anchor_vs_sector
ret_m240td_to_anchor_vs_sector
ret_m180td_to_anchor_vs_sector
ret_m120td_to_anchor_vs_sector
```

Wniosek:

```text
wejścia do mWIG40 są często poprzedzone długim okresem relatywnej siły względem sektora
```

Rynek nie odkrywa tych spółek dopiero przy rewizji. One często wcześniej przez wiele miesięcy zachowują się lepiej niż podobne spółki.

## Wniosek o zmienności

Zmienność również poprawia się w dłuższych oknach:

```text
vol_m360td_ann_to_anchor_vs_sector
vol_m240td_ann_to_anchor_vs_sector
vol_m180td_ann_to_anchor_vs_sector
```

Dla `vol_m360td_ann_to_anchor_vs_sector`, top 10%:

```text
lift: 4.17
precision: 17.9%
recall: 48.0%
```

Wniosek:

```text
przed wejściem do mWIG40 spółki często mają podwyższoną aktywność cenową względem sektora
```

Zmienność sama w sobie nie wystarcza jako sygnał, bo może oznaczać zarówno pozytywny trend, jak i chaotyczny ruch. Najlepiej traktować ją jako potwierdzenie momentum.

## Wniosek o obrocie

Obrót wygląda lepiej w dłuższych oknach niż w krótkich.

Najlepszy wynik:

```text
turnover_ratio_m240td_to_anchor_vs_sector, top 10%
lift: 3.46
precision: 16.7%
recall: 40.0%
```

Dla `turnover_ratio_m360td_to_anchor_vs_sector`:

```text
top 10%:
lift: 2.60
precision: 12.2%
recall: 30.0%

top 20%:
lift: 2.36
precision: 11.1%
recall: 50.0%
```

Wniosek:

```text
obrót jest bardziej użyteczny jako długoterminowe potwierdzenie zainteresowania spółką
niż jako krótkoterminowy impuls
```

## Aktualizacja score

Po użyciu dłuższego okna, np. `SCORING_WINDOW = 360`, prosty score wygląda wyraźnie mocniej.

Score:

```text
previous reserve
+ top momentum 360d
+ top turnover acceleration 360d
+ top volatility 360d
```

Wyniki:

```text
score >= 1:
selected_rows: 292
selected_entrants: 24
precision: 8.2%
recall: 85.7%
lift: 1.93

score >= 2:
selected_rows: 99
selected_entrants: 19
precision: 19.2%
recall: 67.9%
lift: 4.52

score >= 3:
selected_rows: 35
selected_entrants: 12
precision: 34.3%
recall: 42.9%
lift: 8.07

score >= 4:
selected_rows: 10
selected_entrants: 7
precision: 70.0%
recall: 25.0%
lift: 16.47
```

To jest ważny wynik.

Wniosek:

```text
długi horyzont znacząco poprawia jakość bardzo krótkiej shortlisty
```

Przy `score >= 4` mamy tylko 10 obserwacji, ale 7 z nich to faktyczne wejścia. Kombinacja:

```text
poprzednia rezerwa
+ bardzo mocne długoterminowe momentum
+ podwyższona aktywność cenowa
+ potwierdzenie obrotem
```

może być bardzo silnym, choć rzadkim sygnałem.

## Zmiana interpretacji strategii

Wcześniejsza hipoteza brzmiała:

```text
spółki zachowują się lepiej przed rewizją,
bo rynek zaczyna dyskontować wejście
```

Po wydłużeniu okien interpretacja jest subtelniejsza:

```text
spółki, które później wchodzą do mWIG40,
często są już wcześniej zwycięzcami w swoim sektorze
```

Wejście do indeksu może być bardziej konsekwencją wcześniejszego trendu niż jego główną przyczyną.

Potencjalna strategia nie powinna skupiać się wyłącznie na samym zdarzeniu rewizji, tylko na wcześniejszym procesie:

```text
długoterminowa relatywna siła
+ poprawa rankingu
+ wejście w okolice progu
+ potwierdzenie obrotem i zmiennością
```

## Analiza post-revision

Dla reakcji po rewizji używamy parametryzowanych okien:

```python
POST_FACT_WINDOWS = [1, 3, 7, 14, 30, 60, 120]
```

W testach jakościowych uruchamialiśmy też dłuższe okna, w tym do `360` sesji.

Liczymy reakcję od `revision_date`.

Metryki obejmują:

- zwrot entrantów po rewizji,
- porównanie z istniejącymi członkami mWIG40,
- porównanie z medianą sektora,
- porównanie z top 10% spółek z sektora.

## Entrant vs incumbent mWIG40 po rewizji

Po rozszerzeniu okien post-revision widać, że entranty w dłuższym terminie radzą sobie słabiej niż istniejący członkowie mWIG40.

Medianowe zwroty entrantów po rewizji:

```text
1 sesja:    -0.85%
3 sesje:   -1.69%
7 sesji:   -0.53%
14 sesji:  -2.00%
30 sesji:   0.00%
60 sesji:  -0.20%
120 sesji: -8.29%
180 sesji: -10.15%
240 sesji: -3.78%
360 sesji: -1.11%
```

Różnica względem incumbentów mWIG40:

```text
1 sesja:    -1.03 pp
3 sesje:   -2.31 pp
14 sesji:  -3.31 pp
120 sesji: -10.71 pp
180 sesji: -12.78 pp
360 sesji: -7.82 pp
```

Wniosek:

```text
kupowanie po rewizji i trzymanie długo nie wygląda jak atrakcyjna hipoteza bazowa
```

## Entrant vs top 10% sektora po rewizji

Dodaliśmy porównanie entrantów względem top 10% spółek z tego samego sektora.

Referencja top 10% jest liczona per:

```text
revision_date x sector x window
```

z wykluczeniem samej analizowanej spółki.

Medianowe różnice entrantów względem top 10% sektora:

```text
1 sesja:    -2.09 pp
3 sesje:   -2.32 pp
7 sesji:   -1.08 pp
14 sesji:  -7.90 pp
30 sesji:  -5.76 pp
60 sesji:  -9.93 pp
120 sesji: -15.04 pp
180 sesji: -28.62 pp
240 sesji: -19.88 pp
360 sesji: -22.94 pp
```

To jest mocny argument przeciwko strategii:

```text
kup po rewizji i trzymaj długo
```

Po rewizji entranty nie tylko nie biją incumbentów mWIG40, ale też wyraźnie przegrywają z najlepszymi spółkami z własnego sektora.

## Interpretacja post-revision

Najbardziej prawdopodobna interpretacja:

```text
momentum, które doprowadziło spółkę do wejścia do mWIG40,
jest w dużej mierze zrealizowane przed rewizją
```

Po wejściu do indeksu:

- część inwestorów realizuje zysk,
- część efektu jest już zdyskontowana,
- spółka może przechodzić z fazy dynamicznego reratingu do fazy normalizacji,
- najlepsze spółki sektora mogą nadal kontynuować trend, ale entrant jako grupa nie jest już liderem.

To dobrze pasuje do obserwacji:

```text
długie okna pre-revision mają wysoki lift
długie okna post-revision pokazują underperformance
```

## Najważniejszy zaktualizowany wniosek

Obecnie najlepsza hipoteza brzmi:

```text
Wejście do mWIG40 jest często końcowym etapem dłuższego procesu relatywnej siły,
a nie początkiem atrakcyjnego okresu inwestycyjnego.
```

Albo bardziej strategicznie:

```text
trzeba wejść w pociąg zanim rynek w pełni zauważy,
że spółka staje się kandydatem do mWIG40
```

Dłuższe okna mówią, że ten proces zaczyna się znacznie wcześniej niż kilka tygodni przed rewizją.

## Co zmienia replikacja rankingu w czasie rzeczywistym

To jest kluczowy kolejny krok.

Skoro umiemy replikować ranking w dowolnym momencie, nie powinniśmy docelowo budować universe na podstawie poprzedniej rewizji.

Powinniśmy budować panel:

```text
revision_date x prediction_date x spółka
```

Dla każdej rewizji wybieramy kilka dat predykcji, np.:

```python
PREDICTION_OFFSETS_TD = [360, 240, 120, 60, 30, 14, 7, 0]
```

Dla każdej takiej daty replikujemy ranking `as-of`.

## Docelowa definicja universe

Docelowy universe powinien być oparty o:

```text
replicated_rank_asof_prediction_date
```

a nie o:

```text
previous_wig_weight_rank
```

Przykład:

```text
spółka jest blisko progu wejścia do mWIG40 według rankingu z prediction_date
```

Dopiero wtedy liczymy:

```text
ret_m{window}td_to_prediction_date_vs_sector
vol_m{window}td_to_prediction_date_vs_sector
turnover_ratio_m{window}td_to_prediction_date_vs_sector
```

i sprawdzamy, czy spółka faktycznie weszła przy najbliższej rewizji.

## Proponowany panel real-time

Docelowy panel powinien mieć kolumny:

```text
revision_date
prediction_date
isin
ticker
sector
current_index_asof
replicated_rank_asof
distance_to_mwig40_entry_threshold
distance_to_mwig40_exit_threshold
is_near_threshold
previous_mwig40_reserve
entered_mwig40_at_revision
ret_m360td_to_prediction_vs_sector
ret_m240td_to_prediction_vs_sector
ret_m120td_to_prediction_vs_sector
ret_m60td_to_prediction_vs_sector
vol_m360td_to_prediction_vs_sector
turnover_ratio_m240td_to_prediction_vs_sector
rank_improvement_360td
rank_improvement_180td
rank_improvement_60td
days_near_threshold
first_day_near_threshold
```

Target:

```python
entered_mwig40_at_revision
```

## Proponowane bucket’y

Nie powinniśmy traktować wszystkich wejść identycznie.

Warto rozdzielić przypadki:

```text
promotion candidates from sWIG80/WIG
demotion candidates from WIG20
new listings / outside WIG
large rank movers
previous reserve
```

Wejście z WIG20 do mWIG40 to inny mechanizm niż awans z okolic sWIG80.

Docelowo warto mieć osobne score:

```text
score_promotions
score_demotions
score_new_or_outside
```

## Proponowany score real-time

Wersja operacyjna:

```text
near replicated threshold
+ sector-relative long-term momentum
+ rank improvement
+ volatility/activity confirmation
+ turnover confirmation
+ previous reserve as auxiliary feature
```

Przykładowo:

```python
score = (
    near_threshold_score
    + top_sector_momentum_score
    + rank_improvement_score
    + top_volatility_score
    + turnover_confirmation_score
    + previous_reserve_score
)
```

## Najważniejsze wnioski

1. Momentum względem sektora wygląda jak realny sygnał.
2. Po wydłużeniu okien najmocniej wygląda momentum 240-360 sesji.
3. `ret_m360td_to_anchor_vs_sector` daje najwyższy lift w obecnej analizie diagnostycznej.
4. Zmienność względem sektora również niesie informację, szczególnie w dłuższych oknach.
5. Obrót samodzielnie jest słabszy, ale w dłuższych oknach może poprawiać score.
6. Score oparty o długie okna znacząco poprawia jakość bardzo krótkiej shortlisty.
7. Po fakcie entranty jako grupa nie dają dodatniej premii.
8. Po rewizji entranty przegrywają nie tylko z incumbentami mWIG40, ale też z top 10% spółek z sektora.
9. Część false positives wygląda jak sygnały z wyprzedzeniem, dlatego warto testować horyzont 1-2 kolejnych rewizji.
10. Obecny test jest diagnostyczny, a docelowy backtest powinien używać replikowanego rankingu `as-of`.
11. Kolejny etap powinien przejść z panelu `spółka x rewizja` na `spółka x rewizja x prediction_date`.

## Najbliższy dalszy kierunek

1. Zbudować historyczny panel replikowanego rankingu `as-of` dla dat predykcji.
2. Dodać dłuższe offsety predykcyjne, np. `[360, 240, 120, 60, 30, 14, 7, 0]`.
3. Liczyć wszystkie metryki do `prediction_date`, nie do `anchor_date`.
4. Zdefiniować universe na podstawie `replicated_rank_asof`.
5. Testować wejście w najbliższej rewizji oraz w horyzoncie 1-2 rewizji.
6. Rozdzielić przypadki awansu, spadku z WIG20 i nowych spółek.
7. Przebudować lift/score na real-time setting.
8. Oddzielić problem predykcji wejścia do mWIG40 od problemu strategii inwestycyjnej.

## Konkluzja

Obecne wyniki sugerują, że:

```text
sygnał predykcyjny jest silny przed rewizją,
szczególnie w długich oknach 240-360 sesji,
ale po rewizji premia jest już w dużej części wyczerpana
```

To oznacza, że potencjalna strategia nie powinna polegać na kupowaniu po ogłoszeniu wejścia do mWIG40. Bardziej obiecujący kierunek to wcześniejsze wykrywanie spółek, które od wielu miesięcy poprawiają pozycję rankingową i mają relatywną siłę względem sektora, zanim staną się oczywistymi kandydatami do indeksu.
