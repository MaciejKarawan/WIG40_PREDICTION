# mWIG40 Index Composition: Replication, Prediction & Signal Testing

**End-to-end research pipeline for the Warsaw Stock Exchange mid-cap index (mWIG40). It reconstructs GPW Benchmark's index-revision rules, predicts upcoming index changes, and tests with a pre-registered falsification protocol whether "buy future index entrants" is a real trading signal.**

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![pandas](https://img.shields.io/badge/pandas-parquet-150458?logo=pandas)
![Topic](https://img.shields.io/badge/topic-quant%20research%20%7C%20market%20microstructure-blueviolet)

## Why this project

Stocks that join an index attract passive inflows. If the next revision can be predicted early, the question becomes whether that prediction is worth money. The project has three layers:

1. **Replicate**: rebuild GPW Benchmark's ranking and buffer rules from regulations and published portfolios
2. **Predict**: run the same pipeline forward to forecast the next quarterly revision before it is announced
3. **Test the trading idea honestly**: point-in-time panels, cluster bootstrap, permutation tests, survivorship audit and an explicit multiple-testing budget

## 1. Rule replication

- Scraped and parsed GPW Benchmark PDFs: **19 revisions (2021-03 → 2025-09) × 4 indices** (WIG, WIG20, mWIG40, sWIG80) plus reserve lists
- Implemented the ranking `R(i) = 0.4·s_T + 0.6·s_C` (turnover and free-float market-cap shares), eligibility filters (free float, 3-month trading, liquidity) and the entry/maintenance buffers
- Mapped **5 methodological epochs** by tracing regulation changes (2022-03, 2023-06, 2024-06, 2025-01) and extracted a changelog from the rulebooks
- **≈90% recall (36/40)** reconstructing the mWIG40 composition for the March 2025 revision, with a per-stock diagnosis of every miss
- Diagnosed the data issues that limit full replication: adjusted vs. raw prices (e.g. a 10:1 split that the vendor back-propagates), inconsistent ranking dates across GPW PDFs, and capped vs. raw free-float packages

## 2. Forward prediction

The same modules (`filters`, `ranking`, `buffer`) run on a live universe scraped from biznesradar.pl (326 WIG stocks) with incremental OHLCV downloads. This produced a forecast of the June 2026 revision before its announcement, with a full funnel: 326 → 301 after the minimum-turnover (MWO) filter → 225 after the last-quartile filter → predicted 40 constituents, including expected entries and exits and a generated diagnostic notebook.

## 3. Is there a tradable signal? A pre-registered reality check

Exploratory work (EDA on 21 revisions and 45 entries, with >1,700 configurations examined) suggested that a 4-component price-based score could anticipate entrants up to 8 months ahead. Before confirming it, the test specification and decision rules were **frozen in a research log**, and the tests were then run:

| Test | Method |
|---|---|
| T1 | Equal-weighted-by-revision alpha vs. near-threshold peers, **cluster bootstrap** by revision (10k) |
| T2 | **Within-revision permutation test**, with a threshold deflated for multiple testing (p < 0.005) |
| T3 | Excess return vs. a fair **total-return benchmark** (sWIG80TR, mWIG40TR) |
| T4 | Regime split (<2024 vs. ≥2024) + sign test |
| T5 | **Survivorship audit** of the point-in-time universe |
| T6 | Leave-one-revision-out stability |

**What it found**
- A **look-ahead leak** in the earlier backtest: the panel builder appended actual future entrants from outside the candidate zone, so two trades (+1417% and +259%) carried the whole "8-month lead" result. After fixing it to a strictly point-in-time universe, the headline signal is **falsified** (alpha −0.3 pp, CI [−13.7; +12.5], permutation p = 0.49).
- At a ~6-month lead the score still shows **+28.4 pp alpha vs. peers** (CI lower bound +2.0 pp, p = 0.0002, stable under leave-one-out). It does **not** beat a passive TR benchmark with statistical confidence, and it holds only in the 2024+ small-cap bull market, so it does not graduate.
- As a **classifier of who will enter** the index, the score is highly significant up to ~6 months ahead (precision permutation p = 0.0001–0.0012).
- The audit found 74 ISINs missing from the price cache. This contamination of the peer pool is documented rather than hidden.

The conclusion: the value lies in **predicting index composition**, not in a trading strategy. Earlier reports are kept as research history next to the corrections (see [`reports/README.md`](reports/README.md)).

## Repository structure

```
src/mwig_replication/   config (revisions, epochs, thresholds), data_loader, filters,
                        ranking, buffer, replicate_revision, predict_revision,
                        validation, notebook_generator
scripts/                scraping (GPW Benchmark, biznesradar, bankier sector map), ingestion,
                        price validation, EDA panels, as-of backtests, signal_reality_check
reports/                research log, reality check, EDA and backtest reports, regulation changelog
docs/                   progress summary, data pipeline, replication to-dos
data/                   index CSVs, reference sector maps, manual price snapshots
notebooks/              transition EDA
```

## How to run

```bash
python -m pip install -e .
python -m mwig_replication.replicate_revision --help
```

The full pipeline depends on scraped GPW Benchmark PDFs and price caches, which are not all included. [`docs/data-pipeline.md`](docs/data-pipeline.md) lists the inputs each step expects. Tests: `python -m unittest discover -s tests`.

> Research code, not investment advice. Reports are written in Polish.
