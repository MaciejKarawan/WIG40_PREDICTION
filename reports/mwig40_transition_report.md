# Raport: przejścia do mWIG40

Wygenerowano: `2026-04-19 12:19:27`

## Źródła danych

- Portfele: `output\index_portfolios.parquet`
- Listy rezerwowe: `output\reserve_lists.parquet`
- Raport: `output\mwig40_transition_report.md`

## Zakres analizy

- Rewizje w portfelach: `2021-03-19` -> `2025-09-19`
- Liczba rewizji: `19`
- Eventy wejścia do `mWIG40`: `42`
- Unikalne spółki, które weszły do `mWIG40`: `40`

## Wynik główny: skąd przychodziły nowe wejścia do mWIG40

Macierz poniżej klasyfikuje każdą spółkę według jej statusu w bezpośrednio poprzedniej rewizji.

| Transition                   | Count | Share |
| ---------------------------- | ----- | ----- |
| sWIG80 -> mWIG40             | 32    | 76.2% |
| WIG20 -> mWIG40              | 6     | 14.3% |
| WIG outside sWIG80 -> mWIG40 | 3     | 7.1%  |
| IPO/outside WIG -> mWIG40    | 1     | 2.4%  |

## Wariant z wydzieleniem re-entry

W tej wersji `Re-entry -> mWIG40` ma pierwszeństwo przed klasyfikacją jako `sWIG80 -> mWIG40`, jeśli spółka była już kiedyś wcześniej w `mWIG40`.

| Transition                   | Count | Share |
| ---------------------------- | ----- | ----- |
| sWIG80 -> mWIG40             | 26    | 61.9% |
| WIG20 -> mWIG40              | 6     | 14.3% |
| Re-entry -> mWIG40           | 6     | 14.3% |
| WIG outside sWIG80 -> mWIG40 | 3     | 7.1%  |
| IPO/outside WIG -> mWIG40    | 1     | 2.4%  |

## Czysty awans po wyłączeniu re-entry

Po wyłączeniu `Re-entry -> mWIG40` zostaje `36` eventów wejścia.

| Transition                   | Count | Share |
| ---------------------------- | ----- | ----- |
| sWIG80 -> mWIG40             | 26    | 72.2% |
| WIG20 -> mWIG40              | 6     | 16.7% |
| WIG outside sWIG80 -> mWIG40 | 3     | 8.3%  |
| IPO/outside WIG -> mWIG40    | 1     | 2.8%  |

## Pokrycie przez listę rezerwową mWIG40

| Metric                                           | Count | Share |
| ------------------------------------------------ | ----- | ----- |
| Entered mWIG40 from previous mWIG40 reserve list | 20    | 47.6% |

| Previous bucket              | Reserve hits | Total entries | Share |
| ---------------------------- | ------------ | ------------- | ----- |
| sWIG80 -> mWIG40             | 20           | 32            | 62.5% |
| WIG20 -> mWIG40              | 0            | 6             | 0.0%  |
| WIG outside sWIG80 -> mWIG40 | 0            | 3             | 0.0%  |
| IPO/outside WIG -> mWIG40    | 0            | 1             | 0.0%  |

## Macierz przejść w czasie

| Revision date | sWIG80 -> mWIG40 | WIG20 -> mWIG40 | WIG outside sWIG80 -> mWIG40 | IPO/outside WIG -> mWIG40 |
| ------------- | ---------------- | --------------- | ---------------------------- | ------------------------- |
| 2021-06-18    | 2                | 0               | 0                            | 0                         |
| 2021-09-17    | 0                | 0               | 1                            | 0                         |
| 2021-12-17    | 0                | 0               | 1                            | 0                         |
| 2022-03-18    | 1                | 2               | 0                            | 0                         |
| 2022-06-17    | 1                | 0               | 1                            | 0                         |
| 2022-09-16    | 3                | 0               | 0                            | 0                         |
| 2022-12-16    | 1                | 0               | 0                            | 0                         |
| 2023-03-17    | 2                | 1               | 0                            | 0                         |
| 2023-06-16    | 1                | 0               | 0                            | 0                         |
| 2023-09-15    | 3                | 0               | 0                            | 0                         |
| 2023-12-15    | 2                | 0               | 0                            | 0                         |
| 2024-03-15    | 4                | 1               | 0                            | 0                         |
| 2024-06-21    | 1                | 0               | 0                            | 0                         |
| 2024-09-20    | 2                | 0               | 0                            | 0                         |
| 2024-12-20    | 2                | 0               | 0                            | 1                         |
| 2025-03-21    | 4                | 2               | 0                            | 0                         |
| 2025-06-20    | 2                | 0               | 0                            | 0                         |
| 2025-09-19    | 1                | 0               | 0                            | 0                         |

## Dziennik eventów wejścia do mWIG40

| Revision date | Previous revision | Ticker      | ISIN         | Previous bucket              | Category                     | Was ever in mWIG40 before | In previous mWIG40 reserve | Previous reserve rank | First seen in dataset |
| ------------- | ----------------- | ----------- | ------------ | ---------------------------- | ---------------------------- | ------------------------- | -------------------------- | --------------------- | --------------------- |
| 2021-06-18    | 2021-03-19        | ASBIS       | CY1000031710 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | no                         |                       | 2021-03-19            |
| 2021-06-18    | 2021-03-19        | MABION      | PLMBION00016 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | no                         |                       | 2021-03-19            |
| 2021-09-17    | 2021-06-18        | HUUUGE-S144 | US44853H1086 | WIG outside sWIG80 -> mWIG40 | WIG outside sWIG80 -> mWIG40 | no                        | no                         |                       | 2021-03-19            |
| 2021-12-17    | 2021-09-17        | PEPCO       | NL0015000AU7 | WIG outside sWIG80 -> mWIG40 | WIG outside sWIG80 -> mWIG40 | no                        | no                         |                       | 2021-06-18            |
| 2022-03-18    | 2021-12-17        | MERCATOR    | PLMRCTR00015 | WIG20 -> mWIG40              | WIG20 -> mWIG40              | no                        | no                         |                       | 2021-03-19            |
| 2022-03-18    | 2021-12-17        | MOBRUK      | PLMOBRK00013 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | yes                        | 1.0                   | 2021-03-19            |
| 2022-03-18    | 2021-12-17        | TAURONPE    | PLTAURN00011 | WIG20 -> mWIG40              | WIG20 -> mWIG40              | no                        | no                         |                       | 2021-03-19            |
| 2022-06-17    | 2022-03-18        | BOGDANKA    | PLLWBGD00016 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | yes                        | 1.0                   | 2021-03-19            |
| 2022-06-17    | 2022-03-18        | GRUPRACUJ   | PLGRPRC00015 | WIG outside sWIG80 -> mWIG40 | WIG outside sWIG80 -> mWIG40 | no                        | no                         |                       | 2022-03-18            |
| 2022-09-16    | 2022-06-17        | AUTOPARTN   | PLATPRT00018 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | yes                        | 3.0                   | 2021-03-19            |
| 2022-09-16    | 2022-06-17        | BUMECH      | PLBMECH00012 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | yes                        | 2.0                   | 2021-03-19            |
| 2022-09-16    | 2022-06-17        | STSHOLDING  | PLSTSHL00012 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | no                         |                       | 2022-03-18            |
| 2022-12-16    | 2022-09-16        | ZEPAK       | PLZEPAK00012 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | yes                        | 1.0                   | 2021-03-19            |
| 2023-03-17    | 2022-12-16        | BIOMEDLUB   | PLBMDLB00018 | sWIG80 -> mWIG40             | Re-entry -> mWIG40           | yes                       | yes                        | 1.0                   | 2021-03-19            |
| 2023-03-17    | 2022-12-16        | BNPPPL      | PLBGZ0000010 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | no                         |                       | 2021-03-19            |
| 2023-03-17    | 2022-12-16        | CCC         | PLCCC0000016 | WIG20 -> mWIG40              | WIG20 -> mWIG40              | no                        | no                         |                       | 2021-03-19            |
| 2023-06-16    | 2023-03-17        | CIGAMES     | PLCTINT00018 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | no                         |                       | 2021-03-19            |
| 2023-09-15    | 2023-06-16        | ARCTIC      | PLARTPR00012 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | yes                        | 2.0                   | 2021-03-19            |
| 2023-09-15    | 2023-06-16        | RYVU        | PLSELVT00013 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | yes                        | 3.0                   | 2021-03-19            |
| 2023-09-15    | 2023-06-16        | TIM         | PLTIM0000016 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | yes                        | 4.0                   | 2021-03-19            |
| 2023-12-15    | 2023-09-15        | GREENX      | AU0000198939 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | yes                        | 1.0                   | 2022-03-18            |
| 2023-12-15    | 2023-09-15        | POLIMEXMS   | PLMSTSD00019 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | yes                        | 2.0                   | 2021-03-19            |
| 2024-03-15    | 2023-12-15        | ABPL        | PLAB00000019 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | yes                        | 2.0                   | 2021-03-19            |
| 2024-03-15    | 2023-12-15        | ASSECOPOL   | PLSOFTB00016 | WIG20 -> mWIG40              | WIG20 -> mWIG40              | no                        | no                         |                       | 2021-03-19            |
| 2024-03-15    | 2023-12-15        | COGNOR      | PLCNTSL00014 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | yes                        | 1.0                   | 2021-03-19            |
| 2024-03-15    | 2023-12-15        | RAINBOW     | PLRNBWT00031 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | no                         |                       | 2021-03-19            |
| 2024-03-15    | 2023-12-15        | SYNEKTIK    | PLSNKTK00019 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | no                         |                       | 2021-03-19            |
| 2024-06-21    | 2024-03-15        | BNPPPL      | PLBGZ0000010 | sWIG80 -> mWIG40             | Re-entry -> mWIG40           | yes                       | no                         |                       | 2021-03-19            |
| 2024-09-20    | 2024-06-21        | CYBERFLKS   | PLR220000018 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | yes                        | 1.0                   | 2021-03-19            |
| 2024-09-20    | 2024-06-21        | MIRBUD      | PLMRBUD00015 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | yes                        | 2.0                   | 2021-03-19            |
| 2024-12-20    | 2024-09-20        | CLNPHARMA   | PLCLNPH00015 | sWIG80 -> mWIG40             | Re-entry -> mWIG40           | yes                       | yes                        | 1.0                   | 2021-03-19            |
| 2024-12-20    | 2024-09-20        | VOXEL       | PLVOXEL00014 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | yes                        | 3.0                   | 2021-03-19            |
| 2024-12-20    | 2024-09-20        | ZABKA       | LU2910446546 | IPO/outside WIG -> mWIG40    | IPO/outside WIG -> mWIG40    | no                        | no                         |                       | 2024-12-20            |
| 2025-03-21    | 2024-12-20        | CYFRPLSAT   | PLCFRPT00013 | WIG20 -> mWIG40              | WIG20 -> mWIG40              | no                        | no                         |                       | 2021-03-19            |
| 2025-03-21    | 2024-12-20        | JSW         | PLJSW0000015 | WIG20 -> mWIG40              | WIG20 -> mWIG40              | no                        | no                         |                       | 2021-03-19            |
| 2025-03-21    | 2024-12-20        | LUBAWA      | PLLUBAW00013 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | yes                        | 4.0                   | 2021-03-19            |
| 2025-03-21    | 2024-12-20        | NEWAG       | PLNEWAG00012 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | yes                        | 2.0                   | 2021-03-19            |
| 2025-03-21    | 2024-12-20        | PEP         | PLPLSEP00013 | sWIG80 -> mWIG40             | Re-entry -> mWIG40           | yes                       | no                         |                       | 2021-03-19            |
| 2025-03-21    | 2024-12-20        | VERCOM      | PLVRCM000016 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | yes                        | 3.0                   | 2021-09-17            |
| 2025-06-20    | 2025-03-21        | ASSECOSEE   | PLASSEE00014 | sWIG80 -> mWIG40             | Re-entry -> mWIG40           | yes                       | no                         |                       | 2021-03-19            |
| 2025-06-20    | 2025-03-21        | BNPPPL      | PLBGZ0000010 | sWIG80 -> mWIG40             | Re-entry -> mWIG40           | yes                       | no                         |                       | 2021-03-19            |
| 2025-09-19    | 2025-06-20        | DIAG        | PLDGNST00012 | sWIG80 -> mWIG40             | sWIG80 -> mWIG40             | no                        | no                         |                       | 2025-03-21            |

## Metodologia

- Event wejścia jest definiowany jako `mWIG40(T) - mWIG40(T-1)` między kolejnymi rewizjami.
- `Previous bucket` oznacza wyłącznie status spółki w bezpośrednio poprzedniej rewizji.
- `Re-entry -> mWIG40` oznacza, że spółka nie była w `mWIG40` w `T-1`, ale była tam w jakiejkolwiek wcześniejszej rewizji.
- `IPO/outside WIG -> mWIG40` oznacza brak obecności w `WIG` w poprzedniej rewizji.
- `In previous mWIG40 reserve` sprawdza obecność na liście rezerwowej `mWIG40` z poprzedniej rewizji.
