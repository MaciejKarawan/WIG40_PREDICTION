# Handoff — transplant wiedzy z projektu MOMENTUM do WIG40_PREDICTION

> Notatka do wznowienia w nowym kontekście. Stan: 2026-07-02.
> Kontekst źródłowy: `C:\Users\User\Zeszyt\MOMENTUM\main` (CLAUDE.md §2/§4.4/§4.6/§5, MANUAL.md, memory).

> **WYKONANIE (2026-07-02, ta sama data — sesja wznowieniowa):** krok 1 planu (framework) zrealizowany — protokół **P1–P4 w `CLAUDE.md`** (bramka net-2×>0 ∧ CI-lo>0 ∧ uczciwy bench; Sharpe>1,25 nie przeniesiony) + **`reports/research_log.md`** z retro-wpisami Etapów 3–5 (budżet MT ery dev ~1700 konfiguracji).
> **Korekta względem tej notatki:** „dwa otwarte pytania" (C7, placebo) zostały już **kierunkowo rozstrzygnięte w Etapie 5** (`reports/backtest_asof_wyniki.md`, 2026-06-15): score lift ~3 przy lead 240 s. (rank sam w sobie = tautologia), placebo-alfa +14–29 pp. Otwarte pozostają **konfirmacyjnie** — bez CI (C2), bez deflacji MT, OOS = reżim hossy, bench TR niepodpięty; era dev 2021–2026-06 jest skażona selekcją, prawdziwy OOS = rewizje forward ≥2026-09 / backfill <2021. Punkt 6 planu (survivorship uniwersum) nadal otwarty — `n_delisted=0` z Etapu 5 nie obejmuje spółek bez pokrycia w cache. Dalsza kolejność: `CLAUDE.md` „Następne kroki".

## Po co to

Użytkownik chce zaciągnąć skończoną metodologię falsyfikacyjną z MOMENTUM (systematyczny research price-only na GPW) do WIG40_PREDICTION i **sprawdzić wstępny sygnał trzymając ten sam żargon** (rank-IC, net-2×, one-touch holdout, CI Lo, bramka graduacji, positive control / placebo, MT-między-runami, garden of forking paths).

## ROZSTRZYGNIĘTE (2026-07-02): sygnał = S1 (lead trade), gałąź A (przekrojowy)

Użytkownik potwierdził: chodzi o „**wsiąść do pociągu i wyjść przed wejściem do indeksu**" = **S1** z `reports/strategie_i_poprawny_backtest.md` — akumulacja **kandydatów** do mWIG40 budujących siłę względną vs sektor, wyjście w okolicy rewizji. To sygnał **przekrojowy (selekcja spółek)**, NIE long/flat na indeksie. Wcześniejszy wybór „index-timing (long/flat)" był nieporozumieniem terminologicznym (moja etykieta). Gałąź B (szeregowa rękawica) — **nieaktualna, nie budować.**

**Co już wiadomo o S1 (transplant musi uszanować):**
- **Edge w wyprzedzeniu, nie w zdarzeniu** — premia po rewizji ujemna (offset 0 na minusie). Wyjście przed/na wejściu; nigdy trzymać po (anty-strategia §1.3).
- **Próg score ≥ 3, nie ≥ 4** — score≥4 ma lead 0 dni (odpala przy samej rewizji); score≥3 → mediana lead ~91 dni. Do gry z wyprzedzeniem służy 3.
- **Dwa otwarte pytania = nasz positive control:** (C7) czy to realny lead, czy okno sygnału 240–360 pokrywa się z oknem s_T (tautologia „kupuj wysoki bieżący ranking")? (placebo, checklist pkt 4) czy „kandydat do mWIG40" dodaje cokolwiek ponad czyste momentum small-cap near-threshold? Rozstrzygnięcie tych dwóch = warunek, czy S1 istnieje jako strategia.
- **Mała próba + koncentracja:** score≥3 daje ~2 spółki/rewizję, 20 rewizji, 28–45 entrantów; NAV gridu bywał napędzany jedną nazwą (LUBAWA/NEWAG). CI szerokie → Wilson/bootstrap obowiązkowe.

## Kluczowe odkrycie: WIG40_PREDICTION już niezależnie doszedł do lekcji MOMENTUM

Transplant to **NIE przenoszenie kodu** — to zamapowanie *skończonej* maszynerii MOMENTUM na *otwartą* checklistę WIG40 (`strategie_i_poprawny_backtest.md` §4), która pyta o dokładnie to samo:

| MOMENTUM (rozstrzygnięte) | WIG40_PREDICTION (otwarte, ta sama myśl) |
|---|---|
| słabe sygnały = beta nie alfa | **placebo test** (checklist pkt 4): czy „kandydat" dodaje coś ponad momentum small-cap |
| garden of forking paths / run 100752 max-of-N | **1584 komórki gridu** = „gwarantowany overfit maksimum" (pkt 7) |
| pasywny B&H bije aktywne po kosztach | pkt 8: „CAGR 41% w hossie może być betą, nie alfą" |
| net-2× stres kosztowy | pkt 5: prowizja+spread 25–75 bp/stronę, re-run gridu |
| survivorship jako sufit | pkt 3: `price is None → continue`, NAV zawyżony, delisting cicho pomijany |
| CI zamiast punktowego Sharpe | C2: przedziały Wilsona przed każdym parametrem decyzyjnym |
| one-touch holdout | pkt 7: OOS train 2021–23 / test 2024–26, walk-forward po rewizjach |
| koncentracja = zakład na jedną nazwę | §1.4: NAV to LUBAWA/NEWAG, „zakład na jedną spółkę" |

## Rekomendowany plan (gałąź A potwierdzona — S1 przekrojowy)

1. **Transplant frameworku:** przenieść do `CLAUDE.md` WIG40 sekcje protokołu z MOMENTUM — §2 (5 reguł nienegocjowalnych), §4.4 (zamrożony spec przed runem, DoF=0, one-touch holdout, reguła decyzji z góry), §4.6 (research log = kontrola MT między runami), §5.
   - **KRYTYCZNA korekta przy przenoszeniu:** bramka graduacji = **net-2× > 0 ∧ CI-lo(net) > 0 ∧ bije uczciwy bench**. Próg **Sharpe > 1,25 jest WYCOFANY** (power harness: MDE IC 0,092 > realne GPW 0,07 — ślepy, skala USA). Nie przenosić go.
2. **Uczciwy bench:** WIG40 ma przewagę nad MOMENTUM — realny cap-weight TR (mWIG40TR / sWIG80TR) zamiast equal-weight survivorów. Porównanie po kosztach vs po kosztach.
3. **Placebo = nasz positive control:** checklist pkt 4 (portfel near-threshold top-momentum BEZ score vs ZE score) to dokładnie test „czy sygnał to alfa czy przebrane momentum". Zrobić to PRZED sizingiem — jak u nas.
4. **Rank-IC-first (tanio, przed strategią):** czy „score" / momentum sektorowe 240–360d ma istotny, reżimowo-stabilny rank-IC na targecie `entered_mwig40`, po deflacji MT. `signal_ic.py` z MOMENTUM jest adaptowalny (target = wejście do indeksu zamiast forward-return; uniwersum ~326 kandydatów WIG).
5. **Uwaga breadth:** mWIG40 ≈ nasz bucket `top40` (~40 nazw, score≥3 daje ~2 spółki/rewizję). Niski `breadth` → niski sufit IR, ta sama wspólna-beta-bucketu i ryzyko koncentracji co u nas. Mała próba (20 rewizji, 28–45 entrantów) → CI szerokie, wymaga Wilsona/bootstrapa (checklist C2, pkt 6).
6. **survivorship (checklist pkt 3) = nasz blocker #1 w wersji WIG40:** `price is None → continue` cicho pomija delistingi → NAV zawyżony. To realny bug wyceny, nie tylko metodologia. Sprawdzić czy cache stooq zawiera wycofane (MERCATOR, BIOMEDLUB).

## Silniki MOMENTUM do adaptacji (nie przepisywać od zera)

`src/research/` w MOMENTUM: `signal_ic.py` (rank-IC, MT deflacja, cost overlay), `signal_dynamic.py` (`backtest_dynamic`, `metrics_table`, CI Lo), `liquid_retest.py` (holdout 30%, `sharpe_ci`, koszt tiered), `power_control.py` (positive control / MDE). Uniwersum-agnostyczne poza loaderem danych.

## Czego NIE robić

- Nie budować rękawicy long/flat (gałąź B) — sygnał rozstrzygnięty jako przekrojowy (S1).
- Nie przenosić progu Sharpe>1,25.
- Nie zaczynać od kodu — najpierw rozstrzygnąć gałąź A/B, potem framework doc, potem placebo/rank-IC, dopiero potem backtest z CI.

## OSTRZEŻENIE [KOREKTA MIARY 05-07-2026, z MOMENTUM — PRZECZYTAĆ PRZED ADAPTACJĄ SILNIKÓW]

Transplantowana rękawica odziedziczyła wady MIARY wykryte w MOMENTUM 03/05-07-2026
(pełny plan i fakty F1–F8: `MOMENTUM/main/results/ruler_fix_plan.md`; rerun korekcyjny
`20260705_082805_measure_rerun`):

1. **Benchmark bucketowy (F1/F2):** `rets.where(bmask).mean(axis=1)` = codzienny re-EW
   z **same-day membership** (maska z dnia t nakłada zwrot dnia t — look-ahead) i bez
   kosztów. Używać `liquid_retest.bucket_benchmark` (lag członkostwa + rebalans okresowy
   z dryfem + koszty → bench NETTO; bliźniak `daily_ew` do testu parowanego). WIG40 ma
   własny cap-weight TR — tym lepiej, ale NIE porównywać strategii netto z benchem brutto.
2. **Brak rf (F3):** `perf_metrics`/`sharpe_ci` w starej wersji liczyły Sharpe = mean/std
   surowych zwrotów; gotówka (filtr SMA200 → cash) zarabiała 0%. Po transplancie podawać
   `rf_daily` (`src/data/riskfree.py` — stopa referencyjna NBP) i raportować EXCESS.
3. **Porównanie z benchem (F4-pochodne):** absolutne CI-lo>0 przy SE(Sharpe)≈0,36 na
   ~8 latach nie rozdziela niczego. Używać `signal_dynamic.paired_benchmark_test`
   (HAC na dziennych RÓŻNICACH — SE kilkukrotnie mniejsze).
4. **Bramka bez zmierzonej mocy (F4):** przed użyciem jakiejkolwiek bramki graduacji
   zmierzyć jej MDE w konfiguracji testu (`power_control.py --mode C` jako wzorzec).
   Przy breadth mWIG40 (~40 nazw, ~2 spółki/rewizję) sufit IR z Fundamental Law jest
   NISKI — bramka niekalibrowana będzie ślepa dokładnie tak, jak nasza bramka (d).
5. **Splity (F6):** `detect_split_dates` jest matematycznie ślepy na splity (Yahoo close
   i adjclose OBA split-adjusted); łapie tylko dywidendy >20%. Wolumen/dollar-vol
   korygować zdarzeniami (`src/data/yahoo_splits.py`, wolumen wstecz ×ratio).

Werdykt merytoryczny MOMENTUM po korekcie: negatywy STOJĄ (0/42 pod naprawioną miarą),
zmienia się narracja („nieodróżnialne od implementowalnego pasywu", nie „pasyw bije
wszystko") — ale każdy PRZYSZŁY pozytyw w WIG40_PREDICTION liczony starą miarą byłby
niewiarygodny. Przejąć poprawki E1–E2 przed pierwszym własnym werdyktem.
