# Propozycje strategii giełdowych + wymagania poprawnego backtestu

> **⚠️ KOREKTA 2026-07-02 — patrz `reports/sygnal_reality_check.md`.** Rewizja wniosku z aktualizacji 2026-06-15 (poniżej): „+88,8% median przy lead 240s" było artefaktem look-ahead (entranci spoza strefy kandydackiej doklejeni do panelu). Po korekcie point-in-time: S1 jako lead trade 8+ m-cy **sfalsyfikowany**; przeżywa tylko lead ~120 sesji jako alfa vs peer-pool (+28 pp, p=0,0002), bez dowiedzionej przewagi nad indeksami TR, spójna tylko w hossie 2024+.
>
> **AKTUALIZACJA 2026-06-15 — patrz `reports/backtest_asof_wyniki.md`.** Backtest as-of (panel C4+C5, rozbrojone C7) **rewiduje wniosek §1.5**. „Zysk nie pochodzi z wejścia do indeksu / trafione gorsze" było artefaktem pomiaru w **dniu zdarzenia** (offset 0). Przy **lead 6–12 m-cy** spółki poprawnie wytypowane jako entranci dają **medianę +88.8% vs +15%** nietrafionych (240 sesji). Istnieje pre-inclusion run-up, a score sektorowo-momentum ma realny lead-time (lift ~3 przy 240s). **Edge jest w wyprzedzeniu, nie w zdarzeniu** — S1 to lead trade, nie event trade. Ograniczenia: mała próba, koncentracja (BUMECH), reżim hossy 2024–26.

Data: 2026-06-11
Źródła: `reports/analiza_statystyczna.md`, `output/backtests/*` (grid persistence, backtest exit-by-rank, leady sygnałów, trades), `todo_replication.md`, `bin/backtest_mwig40_scoring.py`, `bin/backtest_mwig40_score_persistence.py`, `reports/mwig40_transition_report.md`.

---

## 1. Synteza dowodów (co faktycznie wiemy)

### 1.1 Sygnał przed rewizją jest silny, ale obciążony tautologią C7

- `ret_m360td_to_anchor_vs_sector`, top 10%: lift 5.21, precision 22.4%, recall 60%.
- Score złożony (rezerwa + momentum + vol + obrót, okno 360): score ≥ 4 → precision 70%, lift 16.5 (10 obs); okna 240–300 jeszcze lepsze (precision 77.8%, lift 18.3, 9 obs).
- **Zastrzeżenie C7**: okna 240–360 sesji pokrywają się z 12M oknem `s_T` GPW. Wysoki score ≈ wysoka *bieżąca* pozycja rankingowa. Lift nie dowodzi lead-time'u predykcji.

### 1.2 Lead sygnału zależy od progu

Z `mwig40_score_signal_leads.csv`:

- score ≥ 4 przy oknach 240–360: **mediana lead = 0 dni** — sygnał odpala dopiero przy rewizji, przy której spółka wchodzi. Wysoka precyzja, brak wyprzedzenia.
- score ≥ 3: mediana lead ≈ **91 dni** (jedna rewizja wcześniej), max do 910 dni.

Wniosek operacyjny: do gry "z wyprzedzeniem" nadaje się próg 3 (szersza, brudniejsza lista), nie próg 4.

### 1.3 Po rewizji premia nie istnieje (jest ujemna)

Mediany entrantów od `revision_date`: −0.85% (1 s.), −2.0% (14 s.), −8.3% (120 s.), −10.2% (180 s.). Względem incumbentów mWIG40: do −12.8 pp (180 s.). Względem top 10% własnego sektora: do **−28.6 pp** (180 s.).

### 1.4 Backtesty Etapu 4: wynik diagnostyczny negatywny-do-niejednoznacznego

**Backtest exit-by-rank** (`mwig40_score_backtest_summary.csv`): wszystkie 22 konfiguracje **ujemne** (−9.7% do −31.7% NAV) mimo dodatnich średnich zwrotów z pojedynczych transakcji. Reguła "trzymaj aż rank ≤ X" trzyma przegranych bez końca — odrzucona.

**Backtest persistence** (`mwig40_score_persistence_grid.csv`, 1584 konfiguracje): rozrzut od **−74% do +570%**. Najlepsza konfiguracja (okno 360, entry score≥2 przez 4 rewizje, exit score≤0 przez 4 rewizje): +570%, CAGR 67%, maxDD −12.6% — ale to **6 wejść, 3 zamknięte transakcje**, a NAV przez większość ścieżki to **jedna pozycja (LUBAWA, +319%, boom zbrojeniowy)**. To zakład na jedną spółkę, nie strategia. Konfiguracja z większą próbą (okno 120, score≥3, exit przy spadku score): +442%, CAGR 41%, 32 wejścia, WR 53% — ciekawsza, ale nadal bez kosztów i z koncentracją zysku w NEWAG (+108%) i BOGDANKA (+86%).

### 1.5 Kluczowa diagnostyka: zysk NIE pochodzi z wejścia do indeksu

Na zdeduplikowanych transakcjach z całego gridu (1361 zamkniętych):

| Spółka faktycznie weszła do mWIG40 przy rewizji wejścia w pozycję? | n | śr. zwrot | mediana | win rate |
|---|---|---|---|---|
| TAK | 80 | **+11.5%** | +3.5% | 52.5% |
| NIE | 1281 | **+21.4%** | +7.9% | 61.8% |

Transakcje "trafione" (spółka weszła) są **gorsze** niż "nietrafione". Top transakcje gridu (NEWAG +534%, LUBAWA +319%) miały `entered_mwig40=False` w momencie wejścia. To spójne z 1.3: momentum jest skonsumowane do dnia rankingu, a P&L backtestów to **generyczne momentum sektorowe small-caps w okolicy progu**, nie efekt indeksowy.

---

## 2. Proponowane strategie

Uporządkowane od najlepiej do najsłabiej wspartej danymi.

### S1. "Wsiąść do pociągu przed stacją" — akumulacja kandydatów z wyprzedzeniem

**Teza**: kupuj spółki, które od miesięcy budują relatywną siłę vs sektor i zbliżają się do progu wejścia; sprzedaj w okolicy ogłoszenia/rewizji, bo tam alfa się kończy.

- **Universe**: spółki blisko progu wejścia wg replikowanego rankingu *as-of* (do czasu C4: poprzednia rezerwa lub rank wagowy 60–80 / 5–25).
- **Sygnał**: score ≥ 3 (momentum 240–360 vs sektor + vol + obrót + rezerwa) — próg 3, nie 4, ze względu na lead (1.2). Opcjonalnie wymóg utrzymania przez 2 kolejne rewizje (filtr szumu).
- **Wejście**: na otwarciu sesji po dniu rankingu (nie na zamknięciu dnia rankingu — patrz checklist pkt 10).
- **Wyjście**: w okno ogłoszenie→rewizja (likwidacja w płynność flow trackerów) **albo** przy spadku score poniżej 2 — nigdy "trzymaj po wejściu do indeksu" (1.3) ani "trzymaj do rank ≤ X" (1.4).
- **Status dowodowy**: kierunkowo najlepiej wsparta, ale skażona C7 — dopóki metryki nie będą liczone do cofniętego `prediction_date`, nie wiemy, czy to coś więcej niż "kupuj to, co już wysoko w rankingu". Wymaga panelu C4+C5 przed jakimkolwiek sizingiem.

### S2. Event trade na ogłoszenie (okno ogłoszenie → implementacja)

**Teza**: klasyczny index effect — long przewidziane wejścia / unikanie (short) przewidzianych wyjść, zamknięcie w dniu rewizji, gdy fundusze pasywne rebalansują.

- **Problem**: to okno **nie zostało zmierzone** — EDA liczy POST od `revision_date` (implementacji), a okna POST_ANCHOR [5, 20] nie weszły do raportu. Ujemne mediany 1–14 sesji po rewizji sugerują, że efekt na GPW jest słaby lub nieobecny (pasywne AUM na mWIG40 jest małe). **Najpierw zmierzyć, potem ewentualnie grać** (checklist pkt 9).
- **Przypadek żywy (2026-06)**: predykcja ASSECOBS in (poz. 47, fill-up) / EUROCASH out (poz. 81); ogłoszenie oczekiwane 2026-06-19. Naturalny **paper trade walidacyjny**: zanotować dziś hipotetyczne wejście, zamknąć na implementacji, porównać z benchmarkiem. Przed jakimkolwiek realnym ruchem: przeliczyć predykcję na pełnych danych do 2026-05-22 (B6 — dane stooq powinny już być dostępne).

### S3. Overlay "unikaj świeżych entrantów" (strona krótka / alokacyjna)

**Teza**: świeży entrant przegrywa z incumbentami o ~13 pp i z top 10% sektora o ~29 pp w 180 sesji — najmocniejszy statystycznie wynik całej analizy.

- **Wersja long-only (implementowalna od zaraz)**: w portfelu polskich mid/small-caps nie kupować spółek przez 2–3 kwartały po wejściu do mWIG40; jeśli trzymane z fazy kandydackiej (S1) — rotować do liderów sektora zamiast trzymać entranta.
- **Wersja long/short (papierowa)**: long top 10% sektora ex-entrant / short entrant, horyzont 120–180 sesji. Na GPW borrow na mid-capach jest drogi i często niedostępny — traktować jako test na papierze, nie produkt.
- **Status dowodowy**: duży, spójny efekt w wielu oknach; nadal bez podziału na mechanizmy (demotions z WIG20 mogą zaburzać — C1) i bez kosztów shortowania.

### S4. Strona wyjść (deletions) — do zbadania, nie do grania

Predykcja wyjścia (typ EUROCASH) + podaż trackerów przy rewizji to hipoteza lustrzana do S2, ale **analiza wyjść nie została wykonana** (EDA targetuje tylko `entered_mwig40`). Krok wstępny: powtórzyć panel z targetem `exited_mwig40` i zmierzyć zachowanie po wypadnięciu. Dopiero potem rozmowa o strategii.

### Anty-strategie (wprost sfalsyfikowane przez wyniki)

1. **Kup po ogłoszeniu i trzymaj** — ujemne mediany vs wszystkie benchmarki (1.3).
2. **Trzymaj aż spółka osiągnie rank X** — 22/22 konfiguracji ujemnych (1.4).
3. **Wiara w +570% z gridu** — 6 transakcji, jedna spółka motorem, brak kosztów, maksimum z 1584 komórek (data mining).

---

## 3. Ograniczenia wykonawcze wspólne dla wszystkich strategii

- **Płynność**: kandydaci są z definicji przy progu MWO — płynność marginalna. Pozycje limitowane udziałem w ADV (np. ≤ 10–20% dziennego obrotu); LUBAWA przy 2–3 PLN i szerokim spreadzie to realny koszt wejścia/wyjścia.
- **Koszty**: realistycznie 50–150 bp round-trip (prowizja + spread + impact) dla tych spółek; przy medianie zwrotu +8%/kwartał koszty zjadają istotną część przewagi.
- **Koncentracja**: score ≥ 3 daje ~2 spółki na rewizję; ryzyko idiosynkratyczne dominuje — potrzebne limity per spółka/sektor i akceptacja, że "portfel" bywa 1–3 pozycjami.
- **Short na GPW**: praktycznie niewykonalny na mid/small-capach — krótkie nogi tylko jako unikanie/niedoważenie.
- **Mała próba**: 20 rewizji, 28–45 entrantów; każda liczba precision/lift wymaga przedziału Wilsona (C2), zanim stanie się parametrem decyzyjnym.

---

## 4. Checklist poprawnego backtestu

Mapowanie na `todo_replication.md` + nowe punkty znalezione w kodzie backtestów.

1. **[C7 — krytyczny]** Rozbroić tautologię: liczyć sygnały do `prediction_date` cofniętego o 60/120/240 sesji względem dnia rankingu, tak by okno sygnału nie pokrywało się z oknem `s_T`. Bez tego nie wiadomo, czy strategia ma jakikolwiek lead, czy kupuje "bieżący ranking".
2. **[C4+C5 — fundament]** Universe z `replicated_rank_asof(prediction_date)` zamiast `previous_wig_weight_rank`; panel `rewizja × prediction_date × spółka`. Odzyskuje 17/45 pominiętych entrantów i pozwala na wejścia między rewizjami (obecnie wejścia możliwe tylko w dniu rankingu — sztucznie gruba siatka czasowa).
3. **[NOWE — survivorship / brakujące ceny]** W obu backtestach `price is None → continue`: pozycja bez ceny znika z wyceny okresu i **nie może zostać zamknięta** (delisting/zawieszenie = cicho pomijane). Dodać jawną obsługę delistingów (wymuszona sprzedaż po ostatniej cenie lub zero) i zweryfikować, czy cache stooq w ogóle zawiera spółki wycofane (MERCATOR, BIOMEDLUB itp.). Obecny NAV jest zawyżony o nieznaną wielkość.
4. **[NOWE — placebo test]** Wynik 1.5 sugeruje, że etykieta "kandydat do mWIG40" nic nie dodaje ponad momentum. Test: portfel losowych spółek near-threshold z top-momentum **bez** filtra score vs portfel ze score. Jeśli różnica nieistotna — strategia redukuje się do momentum small-cap i cała maszyneria replikacji nie jest potrzebna do tradingu (pozostaje potrzebna do S2/S4).
5. **[NOWE — koszty i ADV]** Prowizja + spread (np. 25–75 bp/stronę) + limit udziału w ADV; re-run gridu; raportować, które konfiguracje przeżywają. Bez tego żadna liczba z `output/backtests/` nie jest porównywalna z benchmarkiem.
6. **[NOWE — odporność na outliery]** Leave-one-stock-out (bez LUBAWA, bez NEWAG), leave-one-revision-out, bootstrap CI dla CAGR. Konfiguracja, której znak zależy od jednej spółki, jest szumem.
7. **[C2+C8 — wielokrotne testowanie]** 1584 komórki gridu na ~20 rewizjach i 6–32 transakcjach = gwarantowany overfit maksimum. Raportować pełny rozkład gridu (nie max), przedziały Wilsona, walidacja OOS train 2021–2023 / test 2024–2026 lub walk-forward po rewizjach; docelowo model wagowy (logit) zamiast koniunkcji binarnej.
8. **[NOWE — benchmark]** NAV porównywać z sWIG80TR / mWIG40TR oraz strategią buy&hold universe'u — CAGR 41% w hossie small-caps 2023–2025 może być betą, nie alfą.
9. **[NOWE — okno ogłoszenia]** Zmierzyć osobno zwroty: dzień rankingu → ogłoszenie oraz ogłoszenie → implementacja (daty ogłoszeń są w zebranych PDFach/komunikatach GPW Benchmark). To jedyne okno, w którym może żyć klasyczny index effect (S2) — dziś niezmierzone.
10. **[NOWE — look-ahead na wejściu]** Sygnał używa zamknięcia dnia rankingu, a wejście jest po tym samym zamknięciu. Przesunąć egzekucję na otwarcie t+1.
11. **[A1 — ceny adjusted]** Komponent obrotu (`turnover_ratio`) liczony na adjusted close × wolumen — skażony splitami. Najpierw zmierzyć skalę (ile spółek ze splitami w oknach 2021–2026 trafia w okolice progu), potem ewentualnie przeliczyć na cenach surowych.
12. **[C1/C6 + B4/B5 — buckety mechanizmów]** Oddzielić awanse z sWIG80 (76%) od demotions z WIG20 (14%) i przypadków event-driven (fast-track, wezwania). Dla demotions znak momentum jest odwrócony — mieszanie tłumi sygnał i zaburza S3.
13. **[B3/B7 — epoki]** Ranking sprzed 2025-01 liczony metodologią epoki 4. Decyzja: zwalidować epoki 0–3 albo zawęzić backtest do epoki 4 (ale to ~5 rewizji — brak mocy statystycznej). Ten trade-off trzeba podjąć jawnie, nie domyślnie.
14. **[B6/B2 — higiena predykcji 2026-06]** Przed użyciem predykcji w S2: przeliczyć na pełnych danych do 2026-05-22 i po publikacji progu MWO.

### Rekomendowana kolejność

1. C4+C5 (panel as-of) → 2. C7 (cofnięte prediction_date) → 3. placebo test (pkt 4) → 4. koszty + survivorship (pkt 3, 5) → 5. OOS + outliery (pkt 6, 7) → dopiero potem decyzja, czy S1 istnieje jako strategia, czy jest momentum w przebraniu.

Punkt 9 (okno ogłoszenia) jest tani i niezależny — można zrobić równolegle; rozstrzyga o S2 przed rewizją 2026-09.

---

## 5. Konkluzja

Dane **nie wspierają** strategii "graj samo zdarzenie wejścia do indeksu": premia po rewizji jest ujemna, a zyski backtestów pochodzą z momentum, nie z trafności predykcji (transakcje trafione są gorsze od nietrafionych). Najbliższa obrony jest S1 (akumulacja kandydatów z wyprzedzeniem, wyjście przy rewizji) — ale jej istnienie jako odrębnej strategii rozstrzygnie dopiero panel as-of + rozbrojenie C7 + placebo vs czyste momentum. Najmocniejszy pewny wynik jest negatywny/alokacyjny (S3): nie kupuj świeżych entrantów, a jeśli trzymasz kandydata — sprzedaj w okolicy rewizji. Wartość maszynerii replikacyjnej na dziś to przede wszystkim S2/S4 (event window) — pod warunkiem zmierzenia okna ogłoszenie→implementacja, czego jeszcze nie zrobiono.
