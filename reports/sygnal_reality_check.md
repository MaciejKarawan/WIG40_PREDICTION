# Reality check S1 — czy sygnał ery dev jest realny?

Data: 2026-07-02
Spec (zamrożony przed runem): `reports/research_log.md`, wpis [PLAN 2026-07-02]
Kod: `bin/signal_reality_check.py` → `output/signal_check/*` (warianty `full_panel` / `zone_only`)
Dane: `output/backtests_asof/asof_forward_returns.parquet` (Etap 5, sygnał niemodyfikowany); bench TR z lokalnego bulk stooq projektu MOMENTUM (`mwig40tr`, `swig80tr`, `wig`; 2020-01→2026-06-18 — API stooq gate'owane challengem JS, pobranie programistyczne niemożliwe)

---

## 0. Odkrycie nadrzędne — przeciek targetu do uniwersum (look-ahead w Etapie 5)

Builder panelu (`bin/build_asof_rank_panel.py`) dokleja do strefy kandydackiej (rank 25–95) **wszystkich faktycznych entrantów**, także tych spoza strefy (po to, by mierzyć pokrycie). Backtest Etapu 5 (`run_strategy`) selekcjonuje po `score≥3` **bez filtra ranku** — więc do koszyka trafiały spółki, których obecność w panelu jest **uwarunkowana przyszłym wejściem**. Non-entranci spoza strefy w panelu nie istnieją — asymetria dokłada wyłącznie przyszłych zwycięzców.

Skala: **2 trade'y** (oba @240, oba entranci):

| rewizja | ticker | rank_asof @240 | zwrot |
|---|---|---|---|
| 2022-09-16 | BUMECH | **225** | **+1417%** |
| 2026-03-20 | CREOTECH | 108 | +259% |

Te 2 trade'y niosły **cały** wynik offsetu 240. Wariant `zone_only` (pool i selekcja wyłącznie w strefie 25–95 — jedyna konstrukcja definiowalna bez znajomości przyszłości) jest wiążący; `full_panel` raportowany jako dokumentacja artefaktu.

## 1. Wyniki na wariancie point-in-time (`zone_only`)

**T1 — equalrev-alfa (score≥3 vs near-threshold pool), bootstrap klastrowy po rewizjach (10k, seed 42):**

| offset | n_rev | n_trades | alfa | 95% CI | rewizje z alfą > 0 |
|---|---|---|---|---|---|
| 0 | 19 | 87 | −0,2 pp | [−2,3; +2,0] | 8/19 |
| 60 | 17 | 85 | +9,0 pp | [−2,4; +22,1] | 11/17 |
| **120** | 15 | 73 | **+28,4 pp** | **[+2,0; +70,1]** | 11/15 |
| **240** | 13 | 60 | **−0,3 pp** | [−13,7; +12,5] | 6/13 |

**T2 — permutacje w obrębie rewizji (null: losowa selekcja tej samej liczności; próg deflowany p < 0,005):**

| offset | p (alfa zwrotowa) | precision | p (precision) | Wilson 95% precision |
|---|---|---|---|---|
| 0 | 0,55 | 14,9% | 0,0001 | [8,9%; 23,9%] |
| 60 | 0,0045 | 12,9% | 0,0001 | [7,4%; 21,7%] |
| **120** | **0,0002** | 11,0% | **0,0012** | [5,7%; 20,2%] |
| **240** | **0,49** | 5,0% | 0,16 | [1,7%; 13,7%] |

**T3 — excess vs uczciwy bench TR (equalrev po rewizjach):**

| offset | vs sWIG80TR | 95% CI | vs mWIG40TR | pool vs sWIG80TR |
|---|---|---|---|---|
| 120 | +25,4 pp | **[−3,0; +69,3]** | +25,4 pp | −3,0 pp |
| 240 | −5,0 pp | [−19,4; +8,7] | −9,2 pp | −4,7 pp |

**T4 — reżim:** @120 era <2024: 3/6 rewizji dodatnich (sign-test p=0,66, mediana +5,6 pp); era ≥2024: **8/9 dodatnich** (p=0,02, mediana +14,7 pp). @240: <2024 **0/4** dodatnich; ≥2024 mediana +9,7 pp (p=0,25).

**T6 — LOO po rewizjach:** @120 min +9,9 pp (bez 2022-09/BUMECH; znak stabilny), @240 min **−3,8 pp** (znak się odwraca).

**T5 — survivorship:** 74 unikalne ISINy WIG@(r-1) **całkiem bez danych** w OHLCV (śr. ~27/rewizję przy poolu ~71; m.in. CIECH, ALUMETAL, COMARCH, TIM, PGSSOFT, STSHOLDING — wezwania; GETINOBLE — upadłość). Nie mogą wejść ani do poola, ani do selekcji; rank nieznany (brak cen) → **nieoszacowane, mieszane skrzywienie poola** (brakujące tendery zaniżają pool → alfa zawyżona; brakujące bankructwa zawyżają pool → alfa zaniżona). Serii urwanych >30 dni przed rewizją brak; `delisted` w poolu 3–5/offset, w selekcji 0 (obsłużone jawnie).

## 2. Werdykt wg zamrożonych reguł (primary: offset 240)

| Reguła | Wynik | Status |
|---|---|---|
| R1: CI-lo(alfa) > 0 @240 | −13,7 pp | **FAIL** |
| R2: p_perm < 0,005 @240 | 0,49 | **FAIL** |
| R3: CI-lo(excess vs sWIG80TR) > 0 @240 | −19,4 pp | **FAIL** |
| R4: znak alfy w obu erach | @240 <2024: 0/4 dodatnich | **VIOLATION** |
| R5: survivorship bez flag | 74 brakujące ISINy | **RED FLAG** |
| T6: stabilność LOO | @240 odwraca znak | **RED FLAG** |

**S1 jako „lead trade 8+ miesięcy" (offset 240) jest sfalsyfikowany** — i to nie jako szum: wynik Etapu 5 był artefaktem look-ahead (2 spółki spoza strefy dołączone do uniwersum bo weszły). Po korekcie sygnału @240 nie ma śladu (alfa −0,3 pp, precision p=0,16).

**Komórka @120 (lead ~6 m-cy) przeżywa część bramek**: alfa vs peer-pool +28,4 pp, CI-lo +2,0 pp, p=0,0002 (żadna pojedyncza rewizja jej nie niesie — LOO min +9,9 pp). ALE: (a) **nie wykazuje przewagi nad pasywnym sWIG80TR/mWIG40TR** (CI obejmuje 0; przy n=15 rewizji test ma niską moc — szerokość CI ±35 pp; „brak dowodu" ≠ „dowód braku", P1.5); (b) spójność dopiero od 2024-06 (osiem kolejnych dodatnich rewizji = hossa small-caps; 2023 to seria ujemna); (c) offset 120 tylko częściowo rozbraja tautologię C7 (okno sygnału 360 sesji nachodzi na okno s_T w ~połowie); (d) pool skażony survivorship (74 ISINy).

**Mechanizm klasyfikacyjny (kto wejdzie) jest realny przy leadzie ≤120 sesji**: permutacyjne p dla precision 0,0001–0,0012 przy offset 0–120 — score przewiduje wejścia dużo lepiej niż losowanie z near-threshold. Przy 240 już nie (p=0,16).

## 3. Co z wniosków Etapu 5 przeżywa, a co umiera

| Wniosek Etapu 5 | Status po reality check |
|---|---|
| Zdarzenie nie płaci (offset 0 ≈ 0) | **przeżywa** |
| Sam rank = tautologia (C7) | **przeżywa** (nietykane) |
| Score przewiduje wejścia z wyprzedzeniem | **przeżywa dla leadu ≤120 sesji**; @240 pada |
| „Realny lead 8 m-cy, lift ~3 @240" | **umiera** — lift @240 niesiony przez doklejonych entrantów spoza strefy |
| „Trafieni +88,8% median @240 — pre-inclusion run-up" | **umiera jako sygnał handlowy** — run-up entrantów istnieje, ale spółek spoza strefy nie dało się kupić jako kandydatów; przyczynowość odwrócona (weszły, BO urosły) |
| Placebo-alfa rośnie z horyzontem (+28,6 pp @240) | **umiera @240**; @120 (+14,4 pp → tu: +28,4 pp equalrev) **przeżywa statystycznie** z zastrzeżeniami (b)–(d) |
| Koszty nieistotne | przeżywa (holdy długie) |
| `n_delisted=0` → NAV niezawyżony | **osłabione** — prawda dla otwartych pozycji, ale pool gubi 74 ISINy bez danych |

## 4. Odpowiedź na pytanie „czy naiwnie badane strategie niosą prawdziwy sygnał?"

**Jako strategia zwrotowa — nie wykazano; wariant flagowy (lead 8 m-cy) wprost sfalsyfikowany.** Jedyna żywa komórka to S1@120: statystycznie mocna alfa względem rówieśników near-threshold, która (1) nie udowodniła przewagi nad pasywnym indeksem TR, (2) jest reżimowo-warunkowa (spójna tylko w hossie 2024+), (3) częściowo tautologiczna (C7), (4) liczona na skażonym poolu. **Jako sygnał klasyfikacyjny (predykcja składu) — tak**, do ~6 miesięcy naprzód, wysoce istotnie.

## 5. Opcje dalszej pracy (decyzja użytkownika)

1. **Zamknąć S1 jako strategię** — wartość projektu = predykcja składu (trzon deterministyczny + klasyfikacja ≤120 sesji), nie trading.
2. **Forward test S1@120** — zamrozić spec (strefa 25–95, score≥3, wejście t+1 open @120 sesji przed rankingiem, wyjście na rewizji, reguła decyzyjna z góry) i paper-trade'ować od rewizji 2026-09 (pierwszy prawdziwy OOS); przy ~4 rewizjach/rok rozstrzygnięcie zajmie lata.
3. **Naprawić survivorship + backfill** — 74 brakujące ISINy prawdopodobnie są w bulk stooq MOMENTUM (`d_pl_txt/wse stocks` zawiera delisty); dociągnięcie ich do OHLCV czyści pool; backfill rewizji <2021 dołożyłby mocy statystycznej (caveat epok B3/B7).
4. **Rank-IC na kontinuum score** (kolejka pkt 5) — pozostaje niewykonane; wobec werdyktu @240 sensowne tylko razem z (3).
