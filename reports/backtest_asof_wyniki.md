# Backtest as-of (C4+C5 → C7 → placebo → koszty/survivorship → OOS/outliery)

> **⚠️ KOREKTA 2026-07-02 — patrz `reports/sygnal_reality_check.md`.** Wynik offsetu 240 („realny lead 8 m-cy", „trafieni +88,8% median") był **artefaktem look-ahead**: panel dokleja do strefy kandydackiej faktycznych entrantów spoza strefy (BUMECH rank 225 +1417%, CREOTECH rank 108 +259%), a strategia nie filtrowała po ranku. Po ograniczeniu do strefy point-in-time (rank 25–95) alfa @240 = −0,3 pp (p=0,49). Przeżywa tylko @120: alfa vs pool +28,4 pp (CI-lo +2,0 pp, p=0,0002), ale bez dowiedzionej przewagi nad sWIG80TR/mWIG40TR i spójna dopiero od 2024. Dodatkowo `n_delisted=0` NIE zamyka survivorship: 74 ISINy WIG@(r-1) w ogóle nie mają OHLCV → pool skażony.

Data: 2026-06-15
Kod: `bin/build_asof_rank_panel.py` (panel) + `bin/backtest_asof.py` (analiza).
Artefakty: `output/asof/*`, `output/backtests_asof/*`.

Zbudowano zgodnie z kolejnością z `reports/strategie_i_poprawny_backtest.md`. Każdy etap ma osobny artefakt CSV/parquet.

---

## 0. Co zbudowano (fundament C4+C5)

Panel `rewizja × prediction_date × spółka` (`output/asof/asof_rank_panel.parquet`, 5 700 wierszy, 20 rewizji) z **replikowanym rankingiem as-of**:

- `R_asof = 0.4·sT_asof + 0.6·sC_asof`, gdzie `sT` = obrót 12M z ciągłego OHLCV liczony **do prediction_date**, `sC` = ostatnio opublikowane FF shares (PDF rewizji r-1) × cena as-of.
- Siatka `prediction_date` = {0, 60, 120, 240} sesji **przed** dniem rankingu. Offset 0 ≈ stan tautologiczny (okno sygnału pokrywa się z oknem `s_T`); offset 240 = prawdziwy lead 8 m-cy.

**Walidacja proxy (offset 0):** wszyscy entranci pokryci przez uniwersum WIG@(r-1) mają `replicated_rank_asof ≤ 70` (**100%**), ≤60 (85.7%) — proxy lokuje realnych entrantów dokładnie wokół progów bufora 45/50–70/80. Pokrycie entrantów: **42/45** (3 to debiuty spoza WIG@(r-1) — event-driven). To rozbraja C4: uniwersum jest teraz replikowanym rankingiem as-of, nie `previous_wig_weight_rank`.

Uproszczenia (jawne): ceny stooq *adjusted* zamiast surowych z PDF (A1 — dotyka poziomu `sC`, nie zwrotów); brak filtra MWO/kwartyla as-of (usuwają niepłynny ogon, nieistotny przy progu).

---

## 1. C7 — czy sygnał ma lead-time, czy to tautologia? (`asof_lift_by_offset.csv`)

Lift = precyzja predykcji wejścia / baseline. **Rozdziela się rank od score:**

| reguła | offset 0 | offset 60 | offset 120 | offset 240 |
|---|---|---|---|---|
| `replicated_rank ≤ 60` | 1.69 | 1.41 | 1.06 | **0.83** |
| `asof_score ≥ 3` | 5.06 | 4.38 | 3.81 | **3.03** |

**Wniosek:** sam replikowany rank jest **tautologiczny** — przy lead 240 sesji lift spada do ~1 (=baseline, zero informacji), dokładnie jak ostrzegał C7. Ale **score sektorowo-relatywny (momentum 360 vs sektor + vol + obrót + rezerwa) zachowuje lift ~3 nawet przy lead 8 m-cy**. Część liftu z offset=0 (5.06→3.03) była tautologiczna, ale istotny rdzeń predykcyjny przeżywa. **To częściowo rehabilituje sygnał momentum jako mający realny lead-time.**

---

## 2. Placebo — czy score bije czystą betę near-threshold? (`asof_placebo.csv`)

Forward return `prediction_date(t+1 open) → rewizja(close)`; alpha = score − cały near-threshold.

| offset | score≥3 mean | near-threshold all | **alpha** |
|---|---|---|---|
| 0 | −0.0% | −0.8% | +0.8 pp |
| 60 | +10.1% | +2.1% | +8.0 pp |
| 120 | +20.6% | +6.2% | **+14.4 pp** |
| 240 | +44.7% | +16.1% | **+28.6 pp** |

Score **dodaje dodatnią alfę ponad near-threshold** i rośnie ona z horyzontem. Ale uwaga: sama beta near-threshold jest duża na długim horyzoncie (+16% przy 240s) — to small-cap momentum/beta, nie efekt indeksowy. Score dokłada alfę **na wierzchu**.

---

## 3. ⚠️ Rewizja głównego wniosku poprzedniego raportu — pre-inclusion run-up

Poprzedni raport (`strategie_i_poprawny_backtest.md`, §1.5) twierdził: *„zysk NIE pochodzi z wejścia do indeksu — transakcje trafione (+11.5%) są gorsze od nietrafionych (+21.4%)"*. **To był artefakt pomiaru w dniu zdarzenia (offset 0).** Panel as-of pokazuje co innego przy lead (forward return, mediana odporna na outliery):

| offset | entered=TAK (mean / **median**) | entered=NIE (mean / median) |
|---|---|---|
| 0 | +8.7% / +1.5% | −0.7% / −1.8% |
| 60 | +35.5% / +14.4% | +3.6% / +2.3% |
| 120 | +60.9% / **+39.0%** | +10.1% / +5.3% |
| 240 | +173.9% / **+88.8%** | +20.1% / +15.0% |

**Im dłuższy lead, tym większa przewaga spółek poprawnie wytypowanych jako przyszli entranci.** Przy lead 240 sesji mediana trafionych +88.8% vs nietrafionych +15.0% — różnica 6× **odporna na outliery (mediana, nie średnia)**. Istnieje **pre-inclusion run-up**, a score sektorowo-momentum potrafi go złapać z wyprzedzeniem.

**Pojednanie z poprzednim wnioskiem:** w samym dniu zdarzenia (offset 0) przewaga jest minimalna (+8.7% mean, near-threshold flat) — wcześniejszy backtest persistence wchodził AT rewizji (offset ≈ 0), gdzie momentum jest już skonsumowane → stąd „trafione gorsze". **Edge jest w wyprzedzeniu, nie w zdarzeniu.** To trade lead 6–12 m-cy, nie event trade.

---

## 4. Strategia S1 z kosztami + survivorship (`asof_strategy_summary.csv`)

S1 = kup score≥3 w prediction_date (t+1 open), sprzedaj przy rewizji. `equalrev` = średnia z rewizyjnych średnich (kontrola koncentracji).

| offset | score | n_trades | n_stocks | n_delisted | mean (100bps) | median | win rate | **equalrev** | hold (dni) |
|---|---|---|---|---|---|---|---|---|---|
| 0 | ≥3 | 87 | 32 | 0 | **−1.0%** | −2.2% | 44% | −2.2% | 25 |
| 60 | ≥3 | 85 | 30 | 0 | +9.1% | +4.0% | 58% | +10.1% | 114 |
| 120 | ≥3 | 73 | 25 | 0 | +19.6% | +12.6% | 66% | **+33.0%** | 201 |
| 240 | ≥3 | 62 | 25 | 0 | +43.7% | +13.6% | 61% | +70.8% | 377 |

- **Zdarzenie nie płaci:** offset 0 jest **ujemny** (−1.0%, ~24 dni) — potwierdza brak premii w oknie ranking→implementacja. Klasyczny index effect na GPW nieobecny.
- **Koszty nieistotne:** 50–150 bps round-trip zjada ~0.5–1.5 pp przy holdach 4–18 m-cy. Strategia nie jest cost-sensitive (bo nie jest high-frequency).
- **Survivorship:** `n_delisted = 0` we wszystkich konfiguracjach — w tej próbie żadna spółka near-threshold nie wypadła z notowań w trakcie holdu. NAV **nie** jest zawyżony przez ciche pomijanie (problem `price is None` z poprzednich backtestów tu nie występuje, bo jawnie sprawdzam).

---

## 5. OOS + outliery (`asof_oos_split.csv`, `asof_leave_one_out.csv`)

Konfiguracja: offset 120, score≥3, 100 bps.

- **OOS:** train ≤2023 (18 trades, 6 rewizji): equalrev +48.9% ale **mediana −7.5%, win rate 44%** — napędzane outlierami, szum. Test ≥2024 (55 trades, 9 rewizji): equalrev +22.5%, **mediana +19.2%, win rate 73%** — solidne, ale pokrywa się z **hossą small-caps 2024–2026** (żywy problem reżimu C3).
- **Leave-one-stock-out:** usunięcie BUMECH: equalrev 0.33 → 0.16 (**−16.9 pp**) — pojedyncza najwpływowsza spółka. NEWAG −2.4 pp. Efekt **przeżywa** usunięcie dowolnej jednej spółki (wciąż +16% bez BUMECH), ale jest skoncentrowany.

---

## 6. Werdykt

| Pytanie | Odpowiedź |
|---|---|
| Czy replikowany rank ma lead-time? | **Nie** — sam rank to tautologia (lift→1 przy 240s). |
| Czy score sektorowo-momentum ma lead-time? | **Tak** — lift ~3 przy lead 8 m-cy; alfa +14–29 pp vs near-threshold. |
| Czy istnieje pre-inclusion run-up? | **Tak** — trafieni entranci +88.8% median vs +15% (240s); rewiduje wcześniejsze „efekt nie istnieje". |
| Czy zdarzenie (wejście) płaci? | **Nie** — offset 0 ujemny; brak klasycznego index effectu na GPW. |
| Czy to alfa, czy beta small-caps? | **Mieszanka** — duża część to beta near-threshold (+16% @240s), score dokłada alfę na wierzchu. |
| Czy wynik jest solidny? | **Warunkowo** — mała próba (5–18 trafień/próg), koncentracja (BUMECH −17pp), reżim hossy (OOS test = bull). |

**Strategia, która przeżywa dane: lead trade, nie event trade.** Kupuj 6–12 m-cy przed rewizją spółki ze score≥3 (momentum 240–360 vs sektor + rezerwa) w okolicy progu replikowanego rankingu as-of; trzymaj przez run-up; nie licz na samo zdarzenie wejścia. Koszty i delisting nie są tu zabójcami; **zabójcami są mała próba i zależność od reżimu hossy** — dlatego liczby traktować jako trop kierunkowy, nie parametr produkcyjny (potrzeba Wilson CI / dłuższej historii — C2/C8).

### Co zostało nierozbrojone (następne kroki)
- **A1** — `sC_asof` na cenach adjusted; zmierzyć ile spółek przy progu miało splity w oknie.
- **C1/C6** — buckety mechanizmów (demotions z WIG20 mają odwrócone momentum) — tu zmieszane.
- **C2/C8** — Wilson CI, model wagowy zamiast koniunkcji, dłuższa historia dla mocy statystycznej.
- **C3** — rozbicie na reżimy (test ≥2024 = hossa); efekt poza hossą niezweryfikowany.
