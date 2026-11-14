# Faza 2 — raport walidacji cen stooq vs PDF (WIG 2026-03)

**Data rankingu:** 2026-02-27
**Rewizja:** 2026-03-20
**Zakres OHLCV:** 2025-02-27 → 2026-02-27
**Spółek w WIG:** 324
**Mapping ISIN→stooq:** 324
**Z OHLCV:** 324
**Z close na 2026-02-27:** 319

## Histogram |diff_pct|

| Przedział | n spółek |
|---|---|
| <0.1% | 305 |
| 0.1-0.5% | 0 |
| 0.5-1% | 0 |
| 1-2% | 4 |
| 2-5% | 3 |
| 5-10% | 6 |
| 10-25% | 1 |
| 25-50% | 0 |
| 50-100% | 0 |
| >100% | 0 |

## Kategorie

| Kategoria | n spółek | % spółek | % ff_market_cap |
|---|---:|---:|---:|
| OK | 305 | 94.1% | 85.11% |
| Mild | 7 | 2.2% | 5.38% |
| Severe | 7 | 2.2% | 9.49% |
| Split-suspect | 0 | 0.0% | 0.00% |
| no_data | 5 | 1.5% | 0.02% |

## Top 20 spółek po |diff_pct|

| ISIN | Ticker | price_pdf | stooq | diff_pct | kategoria | event_date |
|---|---|---:|---:|---:|---|---|
| PLCRTCH00017 | CREOTECH | 632.0000 | 527.3760 | -16.55% | Severe | 2026-01-02 (Δ=+10.7%) |
| PLBZ00000044 | SANPL | 591.2000 | 543.5690 | -8.06% | Severe | 2025-04-04 (Δ=-8.7%) |
| PLSNKTK00019 | SYNEKTIK | 300.0000 | 276.7380 | -7.75% | Severe | 2025-06-30 (Δ=-16.4%) |
| PLALIOR00045 | ALIOR | 119.5500 | 111.0650 | -7.10% | Severe | 2025-04-04 (Δ=-11.2%) |
| PLBGZ0000010 | BNPPPL | 150.0000 | 140.4260 | -6.38% | Severe | 2025-08-22 (Δ=-7.9%) |
| PLBSK0000017 | INGBSK | 408.5000 | 384.8340 | -5.79% | Severe | 2025-04-04 (Δ=-7.8%) |
| PLAB00000019 | ABPL | 135.4000 | 128.4790 | -5.11% | Severe | 2026-02-26 (Δ=+6.8%) |
| PLATLPL00018 | ATLANTAPL | 21.9000 | 20.8861 | -4.63% | Mild | 2025-06-23 (Δ=-7.1%) |
| PLPCCRK00076 | PCCROKITA | 69.2000 | 66.4843 | -3.92% | Mild | 2026-01-02 (Δ=+5.4%) |
| IT0005239360 | UNICREDIT | 305.6500 | 298.2500 | -2.42% | Mild | 2025-04-10 (Δ=+10.2%) |
| PLLPP0000011 | LPP | 20670.0000 | 20329.5000 | -1.65% | Mild | 2025-12-12 (Δ=+15.3%) |
| NL0015000AU7 | PEPCO | 29.4600 | 29.0230 | -1.48% | Mild | 2025-09-25 (Δ=+13.8%) |
| ES0113900J37 | SANTANDER | 45.6000 | 45.0596 | -1.19% | Mild | 2025-04-04 (Δ=-10.5%) |
| PLPWRMD00011 | IFIRMA | 33.2000 | 32.8340 | -1.10% | Mild | 2025-04-30 (Δ=+9.2%) |
| PLBNFTS00018 | BENEFIT | 3875.0000 | 3875.0000 | +0.00% | OK |  |
| PLKETY000011 | KETY | 1082.0000 | 1082.0000 | +0.00% | OK |  |
| PLHRPHG00023 | HARPER | 5.6600 | 5.6600 | +0.00% | OK |  |
| PLBH00000012 | HANDLOWY | 119.0000 | 119.0000 | +0.00% | OK |  |
| PLASMGR00014 | ASMGROUP | 0.2860 | 0.2860 | +0.00% | OK |  |
| PLTALEX00017 | TALEX | 19.1000 | 19.1000 | +0.00% | OK |  |

## Top 10 spółek po impact_score (|diff_pct| × udział w mcap)

| ISIN | Ticker | diff_pct | ff_market_cap_pdf | impact_score | event_date |
|---|---|---:|---:|---:|---|
| PLBZ00000044 | SANPL | -8.06% | 24,951,596,000 | 0.3219 | 2025-04-04 (Δ=-8.7%) |
| PLBSK0000017 | INGBSK | -5.79% | 13,286,462,500 | 0.1233 | 2025-04-04 (Δ=-7.8%) |
| PLALIOR00045 | ALIOR | -7.10% | 10,627,397,250 | 0.1208 | 2025-04-04 (Δ=-11.2%) |
| PLLPP0000011 | LPP | -1.65% | 26,395,590,000 | 0.0696 | 2025-12-12 (Δ=+15.3%) |
| PLBGZ0000010 | BNPPPL | -6.38% | 5,545,500,000 | 0.0567 | 2025-08-22 (Δ=-7.9%) |
| PLCRTCH00017 | CREOTECH | -16.55% | 1,169,200,000 | 0.0310 | 2026-01-02 (Δ=+10.7%) |
| PLSNKTK00019 | SYNEKTIK | -7.75% | 1,531,500,000 | 0.0190 | 2025-06-30 (Δ=-16.4%) |
| PLAB00000019 | ABPL | -5.11% | 2,120,499,400 | 0.0174 | 2026-02-26 (Δ=+6.8%) |
| NL0015000AU7 | PEPCO | -1.48% | 6,215,765,400 | 0.0148 | 2025-09-25 (Δ=+13.8%) |
| IT0005239360 | UNICREDIT | -2.42% | 568,203,350 | 0.0022 | 2025-04-10 (Δ=+10.2%) |

## Brakujące dane

**Bez mappingu ISIN→stooq:** 0 spółek

**Z mappingiem ale bez OHLCV:** 0 spółek

**Z OHLCV ale bez close na 2026-02-27:** 5 spółek

| ISIN | Ticker | weight_pct |
|---|---|---:|
| PLPANVA00013 | PANOVA | 0.0133% |
| PLERGZB00014 | ERG | 0.0023% |
| PLSKLNW00011 | SKYLINE | 0.0023% |
| PLDGA0000019 | DGA | 0.0019% |
| PLMUZA000019 | MUZA | 0.0010% |

## Rekomendacja dla Fazy 3

**Opcja B (reverse-adjustment dla flagowanych).** 7 spółek z |diff|>5%, łącznie 9.49% ważonego mcap. Pipeline replikacji wymaga korekt dla tych spółek przed obliczeniem sC.

---

## Notatka metodologiczna

- `diff_pct = (stooq_close - price_pdf) / price_pdf × 100`
- Kategoryzacja: OK (<0.5%), Mild (0.5-5.0%), Severe (5.0-50.0%), Split-suspect (≥50.0%)
- Detekcja dyskontynuacji: max |daily return| w 12M; próg odcięcia 3%
- Mianownikiem diff_pct jest cena PDF (ground truth GPW Benchmark, raw).