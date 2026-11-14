# Research log — warstwa strategii mWIG40

Kontrola multiple-testing **między runami** (protokół: `CLAUDE.md` P1.2/P3.7; wzór: MOMENTUM `CLAUDE.md` §4.4 krok 5 / §4.6).

Zasady:
- Jeden wpis = jeden run / jedna hipoteza. Wpis powstaje **po każdym runie, również negatywnym**.
- Każdy wpis podaje **licznik przejrzanych konfiguracji** (to budżet MT między runami) i **status kontaminacji** (co wcześniej selekcjonowano na tych samych danych).
- Log czytać **przed** zaprojektowaniem kolejnego testu — każde „spróbujmy jeszcze X" to kolejny test tej samej rodziny.
- Dotyczy warstwy strategii (S1–S4). Deterministyczna replikacja rankingu (Etapy 1–2) ma osobną walidację (recall vs ground truth) i nie wchodzi do tego logu.

**Era dev = rewizje 2021–2026-06** (21 w EDA / 20 w panelu as-of) — na nich selekcjonowano cechy, progi i offsety; żaden split wewnątrz tej ery nie jest OOS. **Holdout = rewizje forward od 2026-09** (paper trade) oraz ewentualny **backfill rewizji sprzed 2021** (nietknięty selekcją; caveat epok B3/B7).

---

## [2026-06-11] [retro] Etap 3 — EDA wejść do mWIG40 = SELEKCJA CECH (początek ery dev)

- **Hipoteza**: eksploracyjna, bez pre-rejestracji — które cechy price-only odróżniają przyszłych entrantów mWIG40.
- **Dane**: 21 rewizji 2021–2026, 45 wejść (28 widocznych w ówczesnym uniwersum `previous_wig_weight_rank` — przed C4), panel ~7k obs.
- **Metoda**: lift/precision po percentylach; ~7 rodzin cech × okna {60,120,240,300,360} × progi (top 10%/25%) + score złożony (rezerwa + momentum + vol + obrót; progi 2/3/4) — **rzędu 10² komórek przejrzanych, bez korekty MT**.
- **Wynik**: momentum sektorowe 240–360 top 10%: lift 5,21; score≥4: precision 70% na **10 obs** (Wilson ≈ [39%, 90%] — punktowo nieinformatywne); score≥3: precision 34%, lift 8,07. Post-rewizyjnie entranci underperformują (do −28 pp / 180 s.).
- **Wniosek**: wybrano score 4-komponentowy i okna 240–360. **Wszystkie późniejsze testy na tych samych rewizjach dziedziczą tę selekcję.**
- **Artefakty**: `notebooks/mwig40_transition_eda.ipynb`, `reports/analiza_statystyczna.md`, `reports/mwig40_transition_report.md`.

## [2026-06-11] [retro] Etap 4 — grid persistence 1584 komórek + exit-by-rank 22 konfiguracje

- **Hipoteza**: eksploracyjna — czy score z Etapu 3 przekłada się na NAV.
- **Metoda**: grid 1584 komórek (okno × progi entry/exit × persystencja) + 22 konfiguracje exit-by-rank; bez kosztów; wejścia AT rewizji (offset ≈ 0).
- **Wynik**: exit-by-rank **22/22 ujemne** (odrzucone); persistence −74%…+570%, max = 6 wejść / NAV ≈ jedna spółka (LUBAWA) = czysty mining maksimum. Diagnostyka „trafione (+11,5%) gorsze od nietrafionych (+21,4%)" — **później zrewidowana** (artefakt pomiaru w offsecie 0; patrz Etap 5).
- **Wniosek**: mining ery dev, żadna komórka nie jest wynikiem. **MT: +~1600 konfiguracji na tych samych rewizjach.**
- **Artefakty**: `output/backtests/*`, `reports/strategie_i_poprawny_backtest.md` §1.4–1.5.

## [2026-06-15] [retro] Etap 5 — panel as-of: C7, placebo, koszty/survivorship, OOS/LOO

- **Hipoteza**: (a) C7 — score ma lead czy jest tautologią okna `s_T`; (b) placebo — czy score dodaje alfę ponad betę near-threshold; (c) koszty + delisting; (d) OOS + outliery. **Bez zamrożonego specu** — score odziedziczony z Etapu 3, offsety/progi dobrane w tym samym runie.
- **Dane**: panel 20 rewizji × offsety {0,60,120,240} sesji (`output/asof/asof_rank_panel.parquet`); pokrycie entrantów 42/45.
- **Wynik**: sam rank tautologiczny (lift 1,69 → 0,83 z offsetem); **score≥3 lift 5,06 → 3,03** (realny lead ~8 m-cy); placebo-alfa +0,8 / +8,0 / +14,4 / **+28,6 pp** (offset 0/60/120/240); S1 offset 0 **ujemny** (−1,0%), offset 120 equalrev +33,0%, offset 240 +70,8%; koszty ~nieistotne (holdy 4–18 m-cy); `n_delisted=0` w trade'ach; OOS test ≥2024: mediana +19,2%, WR 73% (**= hossa small-caps**, C3); LOO: BUMECH −16,9 pp.
- **Wniosek**: kierunkowo — **lead trade, nie event trade**. Konfirmacyjnie NIEzaliczone: bez CI na liczbach decyzyjnych (C2), bez deflacji MT za ścieżkę selekcji, OOS pokrywa się z reżimem hossy, bench TR niepodpięty. **MT: ~10 kombinacji reguła × offset w tym runie** + dziedziczy Etapy 3–4.
- **Artefakty**: `output/backtests_asof/*`, `reports/backtest_asof_wyniki.md`.
- **Uwagi — survivorship (OTWARTE)**: `n_delisted=0` dotyczy pozycji już otwartych; NIE weryfikuje, czy uniwersum near-threshold nie gubi po cichu spółek bez pokrycia w cache OHLCV (spółki wycofane z obrotu w oknie 2021–2026). Do zamknięcia osobnym audytem pokrycia cache vs point-in-time skład WIG.

## [2026-07-02] Decyzja kierunkowa + transplant protokołu (wpis bieżący)

- Sygnał rozstrzygnięty przez użytkownika jako **S1 przekrojowy** (lead trade, gałąź A): akumulacja kandydatów score≥3 z wyprzedzeniem 6–12 m-cy, wyjście przed/na rewizji, nigdy po. Gałąź B (long/flat na indeksie) — **nie budować**. Kontekst: `reports/momentum_transplant_handoff.md`.
- Transplant protokołu MOMENTUM → `CLAUDE.md` P1–P4. Bramka graduacji: **net-2× > 0 ∧ CI-lo(net) > 0 ∧ uczciwy benchmark ∧ stabilność reżimowa**. Próg Sharpe > 1,25 **nie został przeniesiony** (wycofany w MOMENTUM 30-06-2026 — power harness: MDE@80% ≈ IC 0,092 > realne GPW ~0,07).
- Era dev zamknięta definicyjnie (2021–2026-06). Retro-wpisy powyżej = uczciwa księgowość MT: **łącznie ~1700+ konfiguracji przejrzanych na ≤21 rewizjach przed jakimkolwiek testem konfirmacyjnym.**

---

## [2026-07-02] [PLAN — spec zamrożony PRZED policzeniem] Reality check S1: czy sygnał ery dev jest realny?

- **Pytanie**: czy S1 (score≥3, lead 6–12 m-cy) niesie realny sygnał, czy jest artefaktem (i) szumu małej próby, (ii) selekcji/MT, (iii) bety small-cap/hossy, (iv) survivorship, (v) koncentracji. Rama: na erze dev można tylko **falsyfikować** — pozytyw znaczy „przeżył", nie „potwierdzony" (graduacja wymaga OOS forward, P1.1).
- **Dane (bez zmian, zero nowych wariantów sygnału)**: `output/backtests_asof/asof_forward_returns.parquet` (Etap 5: score 4-komponentowy, okno 360, próg ≥3; forward return = t+1 open po prediction_date → close na rewizji). Offset **primary = 240** (najdalej od tautologii C7), secondary = 120 — wybór odziedziczony z Etapu 5/handoffu, nie nowa selekcja. Statystyka primary: **equalrev-alfa** = średnia po rewizjach z [mean(score≥3) − mean(cały near-threshold)] w obrębie rewizji (kontrola koncentracji; selekcja jest podzbiorem poola → alfa konserwatywna).
- **Testy i reguły decyzyjne (z góry)**:
  - **T1 (C2)** — bootstrap klastrowy po rewizjach (10 000, seed 42), 95% CI percentylowe dla equalrev-alfy. **R1 pass: CI-lo > 0 @240 ∧ alfa punktowo > 0 @120.**
  - **T2 (deflacja/permutacja)** — null: losowa selekcja tej samej liczności z near-threshold per rewizja (10 000 perm., seed 42); p one-sided dla equalrev-alfy. **R2 pass: p < 0,005** (deflacja: Bonferroni α=0,05 / N_eff≈10 realnie odrębnych rodzin sygnałów przejrzanych w erze dev; formalna korekta za ~1700 skorelowanych komórek niewykonalna — próg konserwatywny + wymóg spójności T1∧T2∧T3). Secondary: permutacyjne p dla precision `entered_mwig40`.
  - **T3 (uczciwy bench)** — sWIG80TR (primary; segment kandydatów) i mWIG40TR (secondary) ze stooq; excess per trade w oknie [entry, exit]; equalrev-excess @240 + bootstrap CI. **R3 pass: CI-lo(excess vs sWIG80TR) > 0.**
  - **T4 (reżim C3)** — split rewizje <2024 / ≥2024 (jak Etap 5). **R4 violation: znak equalrev-alfy ujemny w którejkolwiek erze.** Dodatkowo sign-test (binomial) po rewizjach.
  - **T5 (survivorship P1.4)** — audyt: (a) ISINy WIG@(r-1) całkiem nieobecne w OHLCV (ciche wypadnięcie z uniwersum w `build_asof_rank_panel.py:206`); (b) serie urwane >15 sesji przed rewizją wśród kandydatów; (c) czy dotyczą poola/selekcji. **R5 red flag: niewyjaśnione braki w strefie kandydackiej.**
  - **T6 (LOO po rewizji)** — equalrev-alfa @240 po usunięciu każdej pojedynczej rewizji. **Red flag: odwrócenie znaku.**
- **Werdykt (mapowanie z góry)**: „realny na erze dev" = R1∧R2∧R3 ∧ ¬R4-violation ∧ ¬R5-flag; „beta w przebraniu" = R1∧R2, ale R3 fail lub R4 violation; „szum małej próby" = R1 lub R2 fail. Wynik KAŻDY pozostaje erą dev.
- **Kod**: `bin/signal_reality_check.py` → `output/signal_check/*` + `reports/sygnal_reality_check.md`. Rank-IC na kontinuum score (kolejka pkt 5) celowo POZA tym runem — testujemy regułę decyzyjną strategii, nie nową rodzinę statystyk.
- **[KOREKTA W TRAKCIE RUNU — konstrukcyjna, nie selekcyjna]**: odkryto **przeciek targetu do uniwersum** w Etapie 5: builder panelu dokleja do strefy 25–95 faktycznych entrantów spoza strefy, a `run_strategy` nie filtruje po ranku → w koszyku @240 były 2 spółki obecne w panelu wyłącznie dlatego, że weszły (BUMECH rank 225 → +1417%; CREOTECH rank 108 → +259%). Dodano wiążący wariant `zone_only` (pool i selekcja tylko rank 25–95 — jedyna konstrukcja point-in-time); `full_panel` raportowany jako dokumentacja artefaktu. To naprawa P1.4/look-ahead, nie nowy stopień swobody sygnału.
- **Wynik (wariant `zone_only`, wiążący)**: primary @240 — **wszystkie bramki FAIL**: alfa −0,3 pp (CI [−13,7; +12,5]), p_perm 0,49, excess vs sWIG80TR −5,0 pp, era <2024 0/4 dodatnich, LOO odwraca znak. Cały „lead 8 m-cy" Etapu 5 = artefakt look-ahead. Secondary @120 — alfa vs pool **+28,4 pp, CI-lo +2,0 pp, p_perm 0,0002** (LOO min +9,9 pp, stabilna), ale **excess vs TR: CI obejmuje 0** (R3-odpowiednik fail; n=15 → niska moc), spójność tylko ≥2024 (8/9 vs 3/6), C7 rozbrojony częściowo. Precision (klasyfikacja): p 0,0001–0,0012 @0–120; @240 p=0,16. Survivorship: **74 ISINy WIG@(r-1) bez OHLCV** (śr. ~27/rewizję; CIECH/ALUMETAL/COMARCH/TIM/PGSSOFT/STSHOLDING/GETINOBLE...) — pool skażony, kierunek mieszany, nieoszacowany.
- **Werdykt wg zamrożonego mapowania**: S1@240 **sfalsyfikowany** (artefakt); S1@120 „szum-nie-szum": realna alfa vs peers, niedowiedziona vs pasywny bench, reżimowo-warunkowa → **nie graduuje** (P2). Mechanizm klasyfikacyjny (kto wejdzie, lead ≤120 sesji) — realny. Pełny raport: `reports/sygnal_reality_check.md`.
- **MT**: 4 offsety × 1 próg × {alfa, precision, 3 benche} w 2 wariantach poola; zero przeszukiwania sygnału; wynik @120 przechodzi też Bonferroniego po offsetach (0,0002 < 0,005/4).

---

## Kolejka (do zalogowania po wykonaniu)

Pkt 2–4 pierwotnej kolejki (survivorship audit, C2/CI, bench TR) wykonane w ramach reality check 2026-07-02 (wpis wyżej). Pozostają / doszły:

1. **B6** — walidacja predykcji 2026-06 vs faktyczne ogłoszenie GPW Benchmark (użytkownik odłożył 2026-07-02: dane rankingowe niekompletne o 5 sesji, niskie ryzyko).
2. **Backfill brakujących 74 ISIN-ów** z bulk stooq MOMENTUM (`d_pl_txt/wse stocks` zawiera delisty) → czysty pool → re-run reality check @120 (jedyna żywa komórka).
3. **Decyzja strategiczna po werdykcie** (użytkownik): zamknąć S1 jako strategię / forward paper-trade S1@120 od rewizji 2026-09 (spec do zamrożenia) / backfill <2021 dla mocy statystycznej (caveat B3/B7).
4. **Rank-IC** na kontinuum score z deflacją — tylko razem z pkt 2 (na skażonym poolu bez wartości dowodowej).
